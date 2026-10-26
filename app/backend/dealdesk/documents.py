"""PLAN_R12 §1.3 point 1 (I26): the document checklist per deal, from rules (product × segment × policy, clause cited).

  rules()                    data/dealdesk/params/v1/documents.json
  checklist(deal_id)         every required item with status received / pending / expired / waived, date, expiry, the clause,
                             who it is for (entity, UBO, guarantor, collateral, project, other bank), counts and completeness
  set_status(deal_id, item_id, status, date, note, by)   a reviewer's or RM's update (kept in the Deal Desk store, logged)
  publish(deal_id)           the checklist as rows of dd_document (Data Domains), through E's publisher

Status precedence: the user's update, then the deal's dd_document rows in Data Domains, then the evidence in the deal file
(received with a date; expired when older than the rule's validity), else pending.
"""
from __future__ import annotations

import datetime as dt
import functools
import json
import re
import sqlite3
import threading
from typing import Any

from backend.dealdesk import paths

STATUSES = ("received", "pending", "expired", "waived")
_LOCK = threading.Lock()


@functools.lru_cache(maxsize=1)
def rulebook() -> dict[str, Any]:
    return json.loads((paths.params_dir() / "v1" / "documents.json").read_text())


def rules() -> list[dict[str, Any]]:
    return rulebook()["rules"]


def today() -> dt.date:
    return dt.date.today()


def _db() -> sqlite3.Connection:
    con = sqlite3.connect(paths.store_path())
    con.execute("CREATE TABLE IF NOT EXISTS r12_documents (deal_id TEXT, item_id TEXT, status TEXT, doc_date TEXT, note TEXT, by TEXT, at TEXT,"
                " PRIMARY KEY (deal_id, item_id))")
    con.execute("CREATE TABLE IF NOT EXISTS r12_document_log (deal_id TEXT, item_id TEXT, old TEXT, new TEXT, note TEXT, by TEXT, at TEXT)")
    return con


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-")[:40]


def _match(lst: list[str], v: str) -> bool:
    return "*" in lst or v in lst


def applicable(subject: dict[str, Any]) -> list[dict[str, Any]]:
    prod, seg = subject.get("product") or "corporate", subject.get("segment") or "corporate"
    case = subject.get("case_type") or "*"
    return [r for r in rules() if _match(r.get("products") or ["*"], prod) and _match(r.get("segments") or ["*"], seg)
            and (case == "*" or _match(r.get("case_types") or ["*"], case) or (case == "renewal_and_new" and "renewal" in (r.get("case_types") or [])))]


def _targets(rule: dict[str, Any], d: dict[str, Any]) -> list[dict[str, str]]:
    g, scope = d["group"], rule.get("scope", "subject")
    subj = d["subject"]["name"]
    ents = [e for e in g.get("entities") or [] if e.get("role") in ("borrower", "group")] or [{"name": subj}]
    if scope == "each_group_entity":
        return [{"for": e["name"], "kind": "entity"} for e in ents]
    if scope == "each_ubo":
        return [{"for": u["name"], "kind": "ubo"} for u in g.get("ubos") or []] or [{"for": "Shareholders and UBOs", "kind": "ubo"}]
    if scope == "each_bank":
        return [{"for": b, "kind": "bank"} for b in dict.fromkeys(x["bank"] for x in d["bureau"].get("other_banks") or [] if x.get("bank"))]
    if scope == "each_guarantor":
        return [{"for": x["name"], "kind": "guarantor"} for x in g.get("guarantors") or [] if x.get("name")]
    if scope == "each_collateral":
        return [{"for": f"{x.get('type') or 'collateral'} {x.get('id') or ''}".strip(), "kind": "collateral"} for x in g.get("collateral") or []]
    if scope == "each_project":
        return [{"for": x["name"], "kind": "project"} for x in g.get("projects") or []]
    return [{"for": subj, "kind": "deal"}]


def _add_days(d: dt.date, n: int) -> dt.date:
    return d + dt.timedelta(days=n)


def _stored(deal_id: str) -> dict[str, dict[str, Any]]:
    with _LOCK, _db() as con:
        con.row_factory = sqlite3.Row
        return {r["item_id"]: dict(r) for r in con.execute("SELECT * FROM r12_documents WHERE deal_id=?", (deal_id,))}


def _domain_rows(deal_id: str) -> list[dict[str, Any]]:
    """The deal's dd_document rows other writers published (E's demo checklist); B's own rows (B-) are skipped."""
    from backend.dealdesk.review2 import publish as P
    return [r for r in P.read("dd_document", proposal_id=deal_id) if not str(r.get("document_id") or "").startswith("B-")]


def _row_for(rows: list[dict[str, Any]], rule: dict[str, Any], party: str, kind: str) -> dict[str, Any] | None:
    p = party.strip().lower()
    same = [r for r in rows if r.get("rule_id") == rule["id"] or (r.get("doc_type") and r.get("doc_type") == rule.get("doc_type"))]
    hit = next((r for r in same if str(r.get("entity_name") or "").strip().lower() == p), None)
    if hit is None and kind == "deal" and len(same) == 1:
        hit = same[0]
    return hit


def checklist(deal_id: str, d: dict[str, Any] | None = None) -> dict[str, Any]:
    from backend.dealdesk.review2 import source as S
    d = d or S.deal_file(deal_id)
    stored, dom = _stored(deal_id), _domain_rows(deal_id)
    now = today()
    items = []
    for r in applicable(d["subject"]):
        ev_key = (r.get("evidence") or "").split(".")[-1]
        ev = (d.get("documents") or {}).get(ev_key) or {}
        targets = _targets(r, d)
        have = {t["for"].strip().lower() for t in targets}
        for x in dom:  # E's rows for this rule whose party the deal file does not list
            if (x.get("rule_id") == r["id"] or x.get("doc_type") == r.get("doc_type")) and str(x.get("entity_name") or "").strip().lower() not in have \
                    and x.get("entity_name") and r.get("scope") != "subject":
                targets.append({"for": str(x["entity_name"]), "kind": r.get("scope", "subject").replace("each_", "")})
                have.add(str(x["entity_name"]).strip().lower())
        for t in targets:
            iid = f"{r['id']}:{_slug(t['for'])}"
            pev = ((d.get("documents") or {}).get(f"{ev_key}_by_party") or {}).get(t["for"].strip().lower())
            ev_t = pev or ev
            status, date, note, src, expires = "pending", None, ev_t.get("note"), "rule", None
            if ev_t:
                src = "evidence"
                if ev_t.get("received"):
                    status, date = "received", ev_t.get("date")
            row = _row_for(dom, r, t["for"], t["kind"])
            if row:
                src = "data-domains"
                status = str(row.get("status") or status).lower()
                date = row.get("doc_date") or row.get("received_date") or (None if status != "received" else date)
                note = row.get("note") or (None if status == "received" else note)
                expires = row.get("expiry_date")
            if date and not expires and r.get("validity_days"):
                try:
                    expires = _add_days(dt.date.fromisoformat(str(date)[:10]), int(r["validity_days"])).isoformat()
                except ValueError:
                    expires = None
            if status == "received" and expires and dt.date.fromisoformat(str(expires)[:10]) < now:
                status, note = "expired", f"Dated {date}, expired on {expires}"
            s_ = stored.get(iid)
            by = at = None
            if s_:
                status, date, note, by, at, src = s_["status"], s_["doc_date"] or date, s_["note"] or note, s_["by"], s_["at"], "user"
            items.append({"item_id": iid, "rule_id": r["id"], "doc_type": r.get("doc_type"), "name": r["name"], "group": r["group"], "for": t["for"],
                          "for_kind": t["kind"], "status": status if status in STATUSES else "pending", "date": date, "expires": expires,
                          "clause": r["clause"], "policy": f"{rulebook()['policy']['name']} {rulebook()['policy']['version']}",
                          "mandatory": bool(r.get("mandatory", True)), "severity": r.get("severity", "major"), "note": note,
                          "updated_by": by, "updated_at": at, "status_source": src,
                          "source": ({"relation": "dd_document", "key": {"document_id": row.get("document_id")}, "period": row.get("reporting_quarter")}
                                     if row else {"relation": "dd_document_rule", "key": {"rule_id": r["id"]}, "period": None})})
    counts = {s: sum(1 for i in items if i["status"] == s) for s in STATUSES}
    mand = [i for i in items if i["mandatory"]]
    missing = [i for i in mand if i["status"] in ("pending", "expired")]
    done = sum(1 for i in mand if i["status"] in ("received", "waived"))
    comp = round(done / len(mand), 4) if mand else 1.0
    return {"deal_id": deal_id, "product": d["subject"].get("product"), "segment": d["subject"].get("segment"),
            "policy": rulebook()["policy"], "rules_version": rulebook()["version"], "items": items, "counts": counts,
            "missing": [i["item_id"] for i in missing], "missing_count": len(missing), "completeness": comp,
            "headline": (f"{len(missing)} of {len(mand)} required documents missing or expired" if missing else f"All {len(mand)} required documents received or waived")
                        + f"; completeness {comp * 100:.0f}%.",
            "badge": len(missing)}


def set_status(deal_id: str, item_id: str, status: str, date: str | None = None, note: str | None = None, by: str = "") -> dict[str, Any]:
    if status not in STATUSES:
        raise ValueError(f"status must be one of {', '.join(STATUSES)}")
    if status == "waived" and not (note or "").strip():
        raise ValueError("A waiver needs a reason.")
    cur = next((i for i in checklist(deal_id)["items"] if i["item_id"] == item_id), None)
    if cur is None:
        raise KeyError(item_id)
    at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    with _LOCK, _db() as con:
        con.execute("INSERT OR REPLACE INTO r12_documents VALUES (?,?,?,?,?,?,?)", (deal_id, item_id, status, date, note, by, at))
        con.execute("INSERT INTO r12_document_log VALUES (?,?,?,?,?,?,?)", (deal_id, item_id, cur["status"], status, note, by, at))
    publish(deal_id)
    return next(i for i in checklist(deal_id)["items"] if i["item_id"] == item_id)


def history(deal_id: str, item_id: str | None = None) -> list[dict[str, Any]]:
    with _LOCK, _db() as con:
        con.row_factory = sqlite3.Row
        q = "SELECT * FROM r12_document_log WHERE deal_id=?" + (" AND item_id=?" if item_id else "") + " ORDER BY at"
        return [dict(r) for r in con.execute(q, (deal_id, item_id) if item_id else (deal_id,))]


def rows(deal_id: str) -> list[dict[str, Any]]:
    """The checklist as dd_document rows (R12_DATA_CONTRACT); B's rows carry document_id B-<deal>-<item>."""
    c = checklist(deal_id)
    return [{"document_id": f"B-{deal_id}-{i['item_id']}", "proposal_id": deal_id, "rule_id": i["rule_id"], "doc_type": i["doc_type"],
             "doc_label": i["name"], "entity_id": None, "entity_name": i["for"], "status": i["status"], "doc_date": i["date"],
             "expiry_date": i["expires"], "received_date": i["date"] if i["status"] == "received" else None,
             "waived_by": i["updated_by"] if i["status"] == "waived" else None, "note": i["note"], "file_ref": None} for i in c["items"]]


def rule_rows() -> list[dict[str, Any]]:
    """documents.json as dd_document_rule rows."""
    pol = rulebook()["policy"]
    return [{"rule_id": r["id"], "product": ";".join(r.get("products") or ["*"]), "segment": ";".join(r.get("segments") or ["*"]),
             "case_type": ";".join(r.get("case_types") or ["*"]), "doc_type": r.get("doc_type"), "doc_label": r["name"], "scope": r.get("scope", "subject"),
             "validity_days": int(r.get("validity_days") or 0), "mandatory_flag": 1 if r.get("mandatory", True) else 0,
             "policy_id": pol["id"], "clause": r["clause"]} for r in rules()]


_RULES_PUBLISHED = {"done": False}


def publish_rules() -> dict[str, Any]:
    from backend.dealdesk.review2 import publish as P
    return P.publish("dd_document_rule", rule_rows(), key=("rule_id",))


def publish(deal_id: str) -> dict[str, Any]:
    from backend.dealdesk.review2 import publish as P
    if not _RULES_PUBLISHED["done"]:
        publish_rules()  # upsert: a no-op when dd_document_rule already carries this rule book
        _RULES_PUBLISHED["done"] = True
    return P.publish("dd_document", rows(deal_id), key=("document_id",))
