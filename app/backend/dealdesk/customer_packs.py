"""R16 d: customer packs (the four fictional customers' document packs) and the Bank's file on existing customers.

    GET /api/v1/dealdesk/customer-packs                     the packs: customer, case, the ask and RM notes to type, counts
    GET /api/v1/dealdesk/customer-packs/by-cr/{cr_number}   which pack / existing customer a CR number belongs to
    GET /api/v1/dealdesk/customer-packs/{key}               one pack: document checklist (received / expired / missing) with files
    GET /api/v1/dealdesk/customer-packs/{key}/file?path=    download one file of the pack (Word, PDF, photo)
    GET /api/v1/dealdesk/customer-packs/{key}/bank          what the Bank holds (existing customers): accounts, limits, conduct,
                                                           group, returned cheques, every figure traced to its Data Domains relation

Reads data/dealdesk/demo_customers/ (CONTRACT.md there) and the registered relations through the R12 readers; writes
nothing. Deterministic: the same files give the same answers.
"""
from __future__ import annotations

import json
import pathlib
import re
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from backend.dealdesk.data.store import dd_read, trace

V5 = pathlib.Path(__file__).resolve().parents[2]
ROOT = V5 / "data" / "dealdesk" / "demo_customers"
PREFIX = "/api/v1/dealdesk/customer-packs"
router = APIRouter(prefix=PREFIX, tags=["dealdesk-customer-packs"])

MEDIA = {".pdf": "application/pdf", ".jpg": "image/jpeg", ".png": "image/png",
         ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
STATUS_LABEL = {"received": "Received", "expired": "Expired", "missing": "Missing"}


def _customers() -> list[dict[str, Any]]:
    f = ROOT / "customers.json"
    return json.loads(f.read_text())["customers"] if f.exists() else []


def _customer(key: str) -> dict[str, Any]:
    c = next((c for c in _customers() if c["key"] == key), None)
    if c is None:
        raise HTTPException(404, f"No customer pack {key!r}.")
    return c


def _manifest(c: dict[str, Any]) -> dict[str, Any]:
    f = ROOT / c["folder"] / "manifest.json"
    if not f.exists():
        raise HTTPException(404, f"The pack of {c['name']} is not generated.")
    return json.loads(f.read_text())


def _quote_after(md: str, heading: str) -> str:
    """The first '> ' block after a '## <heading>' line of ASK.md."""
    m = re.search(rf"^## {re.escape(heading)}.*?$(.*?)(?=^## |\Z)", md, flags=re.M | re.S)
    if not m:
        return ""
    lines = [ln[2:].strip() for ln in m.group(1).splitlines() if ln.startswith("> ")]
    return lines[0] if lines else ""


def _ask(c: dict[str, Any]) -> dict[str, str]:
    f = ROOT / c["folder"] / "ASK.md"
    md = f.read_text() if f.exists() else ""
    ask = _quote_after(md, "The ask") or _quote_after(md, "What Anne types")
    return {"ask": ask, "rm_notes": _quote_after(md, "RM notes")}


def plain_words(packs: list[dict[str, Any]]) -> list[str]:
    n_docs = sum(p["counts"]["documents"] for p in packs)
    return [f"{len(packs)} customer files, {n_docs} documents in Word and PDF, with photos of the key pages to try the upload.",
            "Existing customers carry the Bank's own data (accounts, limits, conduct, group); new-to-bank customers have documents only.",
            "Each pack shows what to type (the ask and the RM notes) and which documents are expired or missing on purpose."]


def packs() -> dict[str, Any]:
    out = []
    for c in _customers():
        mf = ROOT / c["folder"] / "manifest.json"
        if not mf.exists():
            continue
        m = json.loads(mf.read_text())
        docs = m["documents"]
        out.append({"key": c["key"], "customer_name": c["name"], "cr_number": c["cr_number"], "proposal_id": c["proposal_id"], "cif": c["cif"] or None,
                    "existing": bool(c["cif"]), "case": c["case_label"], "sector": c["sector"], "city": c["city"], "part": c["part"],
                    **_ask(c), "business_request": bool(m.get("business_request")),
                    "counts": {"documents": len(docs), "images": sum(len(d["files"]["images"]) for d in docs),
                               "expired": sum(1 for d in docs if d["status_expected"] == "expired"), "missing": len(m.get("missing") or [])}})
    as_of = json.loads((ROOT / "customers.json").read_text())["as_of"] if (ROOT / "customers.json").exists() else None
    return {"packs": out, "plain_words": plain_words(out), "as_of": as_of}


def _label(code: str) -> str:
    try:
        from ops.r16_customers.doctypes import BY_CODE
        return BY_CODE[code].label
    except Exception:  # noqa: BLE001 - the ops package is optional on a server
        return code.replace("_", " ").capitalize()


def pack_detail(key: str) -> dict[str, Any]:
    c = _customer(key)
    m = _manifest(c)
    rows = []
    for d in m["documents"]:
        rows.append({"doc_id": d["doc_id"], "doc_type": d["doc_type"], "label": _label(d["doc_type"]), "subject": d.get("subject"), "title": d["title"],
                     "issuer": d.get("issuer"), "issue_date": d.get("issue_date"), "expiry_date": d.get("expiry_date"),
                     "status": d["status_expected"], "status_label": STATUS_LABEL[d["status_expected"]], "files": d["files"]})
    for x in m.get("missing") or []:
        rows.append({"doc_id": None, "doc_type": x["doc_type"], "label": _label(x["doc_type"]), "subject": x.get("subject"), "title": _label(x["doc_type"]),
                     "issuer": None, "issue_date": None, "expiry_date": None, "status": "missing", "status_label": "Missing", "why": x.get("why"), "files": None})
    extra = {k: m.get(k) for k in ("business_request", "reference") if m.get(k)}
    if "business_request" in extra:
        extra["business_request"] = {k: v for k, v in extra["business_request"].items() if k != "fields"}
    return {"key": key, "customer_name": c["name"], "cr_number": c["cr_number"], "proposal_id": c["proposal_id"], "cif": c["cif"] or None,
            "existing": bool(c["cif"]), "case": c["case_label"], **_ask(c), "documents": rows, **extra,
            "plain_words": [f"{sum(1 for r in rows if r['status'] == 'received')} documents received, "
                            f"{sum(1 for r in rows if r['status'] == 'expired')} expired and {sum(1 for r in rows if r['status'] == 'missing')} missing.",
                            "Download any file as Word, PDF or a photo and upload it on New proposal; the checklist there should match this one."]}


def file_path(key: str, rel: str) -> pathlib.Path:
    c = _customer(key)
    base = (ROOT / c["folder"]).resolve()
    p = (base / rel).resolve()
    if base not in p.parents or not p.is_file() or p.suffix.lower() not in MEDIA:
        raise HTTPException(404, "No such file in this pack.")
    return p


def by_cr(cr_number: str) -> dict[str, Any]:
    cr = re.sub(r"\D", "", cr_number or "")
    c = next((c for c in _customers() if c["cr_number"] == cr), None)
    if c is None:
        return {"cr_number": cr, "found": False, "existing": False}
    return {"cr_number": cr, "found": True, "key": c["key"], "customer_name": c["name"], "existing": bool(c["cif"]), "cif": c["cif"] or None,
            "proposal_id": c["proposal_id"]}


def _t(rel: str, row: dict[str, Any]) -> dict[str, Any]:
    return trace(rel, row)


def bank(key: str) -> dict[str, Any]:
    """The Bank's file on an existing customer, every block traced (relation, key, version)."""
    c = _customer(key)
    if not c["cif"]:
        return {"key": key, "customer_name": c["name"], "existing": False, "plain_words": ["New to bank: the Bank holds no accounts or limits for this customer."]}
    pid, cif = c["proposal_id"], c["cif"]
    accts = dd_read("dd_customer_account", proposal_id=pid)
    limits = [r for r in dd_read("dd_facility_limit", proposal_id=pid)]
    conduct = sorted(dd_read("dd_account_conduct", proposal_id=pid, obligor_id=cif), key=lambda r: r["month"])
    last12 = conduct[-12:]
    ents = [e for e in dd_read("b360_entity") if e["group_id"] == c["group_id"]]
    cheques = dd_read("dd_returned_cheque", proposal_id=pid)
    total = next((r for r in limits if r["level"] == 0), None)
    own = [a for a in accts if a["obligor_id"] == cif]
    summary = {"accounts_n": len(own), "balances_mn": round(sum(a["balance_mn"] for a in own), 3),
               "deposits_mn": round(sum(a["balance_mn"] for a in own if a["account_type"] == "deposit"), 3),
               "credit_turnover_12m_mn": round(sum(r["credit_turnover_mn"] for r in last12), 3),
               "avg_utilisation_12m_pct": round(sum(r["utilisation_pct"] for r in last12) / max(len(last12), 1), 1),
               "limits_mn": total["existing_mn"] if total else None, "outstanding_mn": total["outstanding_mn"] if total else None,
               "returned_cheques_12m": sum(r["returned_cheques_n"] for r in last12), "past_due_days_max_12m": max((r["past_due_days_max"] for r in last12), default=0)}
    connected = [e for e in ents if e.get("credit_status") not in (None, "", "performing")]
    words = [f"Customer since {accts[0]['opened'][:4] if accts else '—'}: {summary['accounts_n']} accounts with SAR {summary['balances_mn']:,.1f}m, "
             f"credit turnover SAR {summary['credit_turnover_12m_mn']:,.1f}m in 12 months.",
             f"Limits SAR {summary['limits_mn']:,.1f}m, SAR {summary['outstanding_mn']:,.1f}m used; "
             f"{summary['returned_cheques_12m']} returned {'cheque' if summary['returned_cheques_12m'] == 1 else 'cheques'} and "
             + (f"worst {summary['past_due_days_max_12m']} days past due" if summary['past_due_days_max_12m'] else "no past dues") + " on its own accounts in 12 months.",
             (f"Watch the group: {connected[0]['entity_name']} — {connected[0]['credit_status_note']}." if connected else "No group company in difficulty.")]
    return {"key": key, "customer_name": c["name"], "existing": True, "cif": cif, "proposal_id": pid, "summary": summary, "plain_words": words,
            "accounts": [{**a, "trace": _t("dd_customer_account", a)} for a in accts],
            "limits": [{**r, "trace": _t("dd_facility_limit", r)} for r in limits],
            "conduct_12m": [{**r, "trace": _t("dd_account_conduct", r)} for r in last12],
            "group": [{**e, "trace": _t("b360_entity", e)} for e in ents],
            "returned_cheques": [{**r, "trace": _t("dd_returned_cheque", r)} for r in cheques],
            "borrower_360": {"customer_id": cif, "domain": "corporate"}}


@router.get("")
def get_packs() -> dict[str, Any]:
    return packs()


@router.get("/by-cr/{cr_number}")
def get_by_cr(cr_number: str) -> dict[str, Any]:
    return by_cr(cr_number)


@router.get("/{key}")
def get_pack(key: str) -> dict[str, Any]:
    return pack_detail(key)


@router.get("/{key}/file")
def get_file(key: str, path: str = Query(...)) -> FileResponse:
    p = file_path(key, path)
    return FileResponse(p, media_type=MEDIA[p.suffix.lower()], filename=p.name)


@router.get("/{key}/bank")
def get_bank(key: str) -> dict[str, Any]:
    return bank(key)
