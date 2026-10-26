"""R11 R4: conditions become tracked triggers.

Every condition precedent, covenant and watch item a review produces becomes a trigger: what, data source, threshold
(the check), due date, owner and status. A trigger with a data check is evaluated against the review evidence each time
it is read (status from data: met, open, due, overdue); one without is manual and keeps the status the user sets.
Triggers persist in the Deal Desk store (var/dealdesk/dealdesk.sqlite, table review_conditions); a user's edits to
status, owner, due date and note survive re-capture.
"""
from __future__ import annotations

import calendar
import datetime as dt
import json
import re
import sqlite3
import threading
from typing import Any

from backend.dealdesk import paths
from backend.dealdesk.review_facts import facts as _facts, resolve
from backend.dealdesk.review_rules import evaluate, render

_LOCK = threading.Lock()
STATUSES = ("open", "due", "overdue", "met", "waived", "breached")
DUE_WINDOW_DAYS = 30


def today() -> dt.date:
    return dt.date.today()


def _db() -> sqlite3.Connection:
    con = sqlite3.connect(paths.store_path())
    con.execute("CREATE TABLE IF NOT EXISTS review_conditions (id TEXT PRIMARY KEY, deal_id TEXT, body TEXT, created TEXT, updated TEXT)")
    con.execute("CREATE TABLE IF NOT EXISTS review_condition_log (id TEXT, field TEXT, old TEXT, new TEXT, by TEXT, at TEXT)")
    return con


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40]


def _month_end(d: dt.date) -> dt.date:
    return d.replace(day=calendar.monthrange(d.year, d.month)[1])


def resolve_due(due: str, as_of: str) -> tuple[str | None, str]:
    """('2026-11-30', 'by 30 Nov 2026') from '+60d', an ISO date, 'monthly', 'annual' or text such as 'before drawdown'."""
    base = max(dt.date.fromisoformat(as_of[:10]), today())
    s = (due or "").strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        d = dt.date.fromisoformat(s)
        return d.isoformat(), f"by {d.day} {d.strftime('%b %Y')}"
    m = re.fullmatch(r"\+(\d+)d", s)
    if m:
        d = dt.date.fromisoformat(as_of[:10]) + dt.timedelta(days=int(m.group(1)))
        return d.isoformat(), f"by {d.day} {d.strftime('%b %Y')} ({m.group(1)} days)"
    if s == "monthly":
        d = _month_end(base)
        return d.isoformat(), f"monthly, next {d.day} {d.strftime('%b %Y')}"
    if s == "annual":
        d = dt.date(base.year, 12, 31)
        return d.isoformat(), "annual (FY accounts)"
    return None, s


def _trigger(deal_id: str, rule_id: str, cond: dict[str, Any], f: dict[str, Any], origin: str) -> dict[str, Any]:
    due_date, due_text = resolve_due(cond.get("due", ""), f["as_of"])
    return {"id": f"{deal_id}:{rule_id}:{_slug(cond['what'])}", "deal_id": deal_id, "deal_name": f["subject"]["name"],
            "rule_id": rule_id, "kind": cond.get("kind", "watch"), "what": cond["what"], "source": cond.get("source", ""),
            "check": cond.get("check"), "inputs": cond.get("inputs") or {}, "due_date": due_date, "due_text": due_text,
            "owner": cond.get("owner", "RM"), "origin": origin, "note": "", "status_override": None}


def capture_from(deal_id: str, f: dict[str, Any], checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The triggers a review implies: failed rules' conditions, plus a Deal Desk proposal's own covenants."""
    out: dict[str, dict[str, Any]] = {}
    for c in checks:
        if c.get("condition") and c["verdict"] in ("contradicted", "exception"):
            t = _trigger(deal_id, c["rule_id"], c["condition"], f, origin=f"Finding {c['rule_id']}: {c['title']}")
            out.setdefault(t["id"], t)
    if f["subject"]["kind"] == "dd":
        cov_checks = {"dscr": ("metrics.dscr_post", ">="), "net_debt_ebitda": ("metrics.debt_ebitda_post", "<=")}
        for cov in f["dd"]["security"].get("covenants") or []:
            key = re.sub(r"[^a-z]+", "_", cov["type"].lower()).strip("_")
            path_op = cov_checks.get(key)
            cond = {"kind": "covenant", "what": f"{cov['type']} {'at least' if (path_op or ('', '>='))[1] == '>=' else 'at most'} {cov['threshold']:.2f}x",
                    "source": "Financial spreading (annual accounts)", "due": "annual", "owner": "RM"}
            if path_op:
                cond["inputs"] = {"v": path_op[0]}
                cond["check"] = f"v {path_op[1]} {float(cov['threshold'])}"
            t = _trigger(deal_id, "COVENANT", cond, f, origin="Proposal covenant package")
            out.setdefault(t["id"], t)
        from backend.dealdesk.deposit_requirement.docs import review_condition  # Round D: the proposal's deposit requirement
        dep = review_condition(f)
        if dep:
            t = _trigger(deal_id, "DEPOSIT", dep, f, origin="Proposal deposit requirement")
            out.setdefault(t["id"], t)
    return list(out.values())


def evaluate_trigger(t: dict[str, Any], f: dict[str, Any] | None) -> dict[str, Any]:
    t = dict(t)
    value, data_ok = None, None
    if t.get("check") and f is not None:
        try:
            names = {"as_of": f["as_of"], **{k: resolve(f, p) for k, p in (t.get("inputs") or {}).items()}}
            data_ok = bool(evaluate(t["check"], names))
            value = {k: names[k] for k in (t.get("inputs") or {})}
        except Exception:  # noqa: BLE001 - data not available: manual
            data_ok = None
    t["evaluation"] = "data" if data_ok is not None else "manual"
    t["data_value"] = value
    d = dt.date.fromisoformat(t["due_date"]) if t.get("due_date") else None
    if t.get("status_override") in ("met", "waived", "breached"):
        st = t["status_override"]
    elif data_ok:
        st = "met"
    elif d and d < today():
        st = "overdue"
    elif d and (d - today()).days <= DUE_WINDOW_DAYS:
        st = "due"
    elif not d and re.search(r"before (committee|drawdown)", t.get("due_text", "")):
        st = "due"
    else:
        st = "open"
    if data_ok is False and t["kind"] == "covenant" and d and d < today():
        st = "breached"
    t["status"] = st
    t["what"] = render(t["what"], value or {}) if "{" in t["what"] else t["what"]
    return t


# ------------------------------------------------------------------ store

def upsert(triggers: list[dict[str, Any]], deal_id: str | None = None) -> None:
    """Insert or refresh triggers. With `deal_id`, that deal's triggers no longer implied by its review are dropped,
    unless a user has edited them."""
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    with _LOCK:
        con = _db()
        try:
            if deal_id:
                keep = {t["id"] for t in triggers}
                for cid, body in con.execute("SELECT id, body FROM review_conditions WHERE deal_id = ?", (deal_id,)).fetchall():
                    if cid not in keep and not (json.loads(body).get("user_edited") or {}):
                        con.execute("DELETE FROM review_conditions WHERE id = ?", (cid,))
            for t in triggers:
                row = con.execute("SELECT body FROM review_conditions WHERE id = ?", (t["id"],)).fetchone()
                if row:
                    old = json.loads(row[0])
                    edited = old.get("user_edited") or {}
                    for k in edited:
                        t[k] = old.get(k)
                    t["user_edited"] = edited
                    con.execute("UPDATE review_conditions SET body = ?, updated = ? WHERE id = ?", (json.dumps(t), now, t["id"]))
                else:
                    con.execute("INSERT INTO review_conditions VALUES (?, ?, ?, ?, ?)", (t["id"], t["deal_id"], json.dumps(t), now, now))
            con.commit()
        finally:
            con.close()


def stored(deal_id: str | None = None) -> list[dict[str, Any]]:
    with _LOCK:
        con = _db()
        try:
            q = "SELECT body FROM review_conditions" + (" WHERE deal_id = ?" if deal_id else "") + " ORDER BY id"
            return [json.loads(b) for (b,) in con.execute(q, (deal_id,) if deal_id else ())]
        finally:
            con.close()


def patch(cid: str, changes: dict[str, Any], by: str = "") -> dict[str, Any]:
    allowed = {"status": "status_override", "owner": "owner", "note": "note", "due_date": "due_date"}
    with _LOCK:
        con = _db()
        try:
            row = con.execute("SELECT body FROM review_conditions WHERE id = ?", (cid,)).fetchone()
            if not row:
                raise KeyError(cid)
            t = json.loads(row[0])
            now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
            for k, v in changes.items():
                if k not in allowed:
                    continue
                if k == "status" and v not in STATUSES and v not in (None, "", "auto"):
                    raise ValueError(f"status must be one of {', '.join(STATUSES)} or 'auto'")
                if k == "due_date" and v:
                    dt.date.fromisoformat(str(v))
                field = allowed[k]
                v = None if (k == "status" and v in ("", "auto")) else v
                con.execute("INSERT INTO review_condition_log VALUES (?, ?, ?, ?, ?, ?)", (cid, field, json.dumps(t.get(field)), json.dumps(v), by, now))
                t[field] = v
                if k == "due_date" and v:
                    d = dt.date.fromisoformat(str(v))
                    t["due_text"] = f"by {d.day} {d.strftime('%b %Y')}"
                    t.setdefault("user_edited", {})["due_text"] = True
                t.setdefault("user_edited", {})[field] = True
            con.execute("UPDATE review_conditions SET body = ?, updated = ? WHERE id = ?", (json.dumps(t), now, cid))
            con.commit()
        finally:
            con.close()
    return t


def history(cid: str) -> list[dict[str, Any]]:
    with _LOCK:
        con = _db()
        try:
            return [{"field": f, "old": json.loads(o), "new": json.loads(n), "by": b, "at": a}
                    for (f, o, n, b, a) in con.execute("SELECT field, old, new, by, at FROM review_condition_log WHERE id = ? ORDER BY rowid", (cid,))]
        finally:
            con.close()


def summarise(items: list[dict[str, Any]]) -> dict[str, Any]:
    due = [t for t in items if t["status"] in ("due", "overdue", "breached")]
    deals = sorted({t["deal_id"] for t in due})
    by = {s: sum(1 for t in items if t["status"] == s) for s in STATUSES}
    line = (f"Conditions due: {len(due)} across {len(deals)} deal{'s' if len(deals) != 1 else ''}"
            + (f" · {by['overdue']} overdue" if by["overdue"] else "") + (f" · {by['breached']} breached" if by["breached"] else "")
            if due else "Conditions due: none")
    return {"total": len(items), "due": len(due), "deals_due": deals, "by_status": by, "line": line,
            "data_evaluated": sum(1 for t in items if t.get("evaluation") == "data")}


_FACTS: dict[str, tuple[float, dict[str, Any] | None]] = {}
FACTS_TTL = 300.0


def facts_for(deal_id: str) -> dict[str, Any] | None:
    import time
    hit = _FACTS.get(deal_id)
    if hit and time.time() - hit[0] < FACTS_TTL:
        return hit[1]
    try:
        f = _facts(deal_id)
    except Exception:  # noqa: BLE001 - the deal's evidence is not available: its triggers read as manual
        f = None
    _FACTS[deal_id] = (time.time(), f)
    return f


def remember_facts(deal_id: str, f: dict[str, Any]) -> None:
    import time
    _FACTS[deal_id] = (time.time(), f)


def listing(deal_id: str | None = None) -> dict[str, Any]:
    items = stored(deal_id)
    out = [evaluate_trigger(t, facts_for(t["deal_id"])) for t in items]
    order = {"breached": 0, "overdue": 1, "due": 2, "open": 3, "met": 4, "waived": 5}
    out.sort(key=lambda t: (order.get(t["status"], 9), t.get("due_date") or "9999", t["deal_id"]))
    return {"items": out, "summary": summarise(out), "as_of": today().isoformat(),
            "basis": "Triggers captured from each review's findings and covenants; status from the review evidence where a data check exists, else manual."}
