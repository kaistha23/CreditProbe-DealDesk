"""R16 b: the business request API (prefix /api/v1/dealdesk), included in backend/dealdesk/api.py (# R16 routers).

    GET  /business-requests/customers              customers a request can be written for (demo customers; existing / new to bank)
    GET  /business-requests/customer/{ref}         the customer file in brief: checklist, the Bank's limits and conduct, what the ask can name
    POST /business-requests                        {customer, ask, notes?, rm?, documents?, missing?} -> the request (saved; same inputs, same id)
    GET  /business-requests?proposal_id=           requests written, newest first
    GET  /business-requests/{rid}                  one request (sections, figures with sources, plain words, links)
    GET  /business-requests/{rid}.docx             the request in Word (bank form)
    GET  /business-requests/{rid}/trace            every figure printed: section, label, value, source
    POST /business-requests/{rid}/share            {to: [usernames], note?} records the share (the UI sends it through CreditProbe Mail)
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query, Request
from fastapi.responses import Response

from backend.dealdesk.rm_request import inputs as I
from backend.dealdesk.rm_request import paper as PA
from backend.dealdesk.rm_request import render as RD
from backend.dealdesk.rm_request import store as ST
from backend.dealdesk.rm_request import writers as WR

PREFIX = "/api/v1/dealdesk"
router = APIRouter(prefix=PREFIX, tags=["dealdesk-business-request"])
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
BASE = f"{PREFIX}/business-requests"


def _user(request: Request | None) -> str:
    if request is None:
        return ""
    try:
        from backend.house_style import generated_by
        return generated_by(request) or ""
    except Exception:  # noqa: BLE001
        return ""


def links(rid: str) -> dict[str, str]:
    return {"self": f"{BASE}/{rid}", "docx": f"{BASE}/{rid}.docx", "trace": f"{BASE}/{rid}/trace", "share": f"{BASE}/{rid}/share",
            "open": f"/deal-desk?br={rid}"}


@router.get("/business-requests/customers")
def customers_list() -> dict[str, Any]:
    out = []
    for c in I.customers():
        out.append({k: c.get(k) for k in ("key", "proposal_id", "cif", "name", "short", "cr_number", "city", "sector", "sub_sector", "case", "case_label", "group_name")}
                   | {"existing": bool(c.get("cif"))})
    return {"customers": out}


def _file(ref: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    body = body or {}
    try:
        return I.load(ref, documents=body.get("documents"), missing=body.get("missing"), customer=body.get("customer_fields"))
    except I.NotFound as e:
        raise HTTPException(404, str(e).strip("'\"")) from None


@router.get("/business-requests/customer/{ref}")
def customer_file(ref: str) -> dict[str, Any]:
    cf = _file(ref)
    w = WR.W(cf, {"items": []}, {"lines": []})
    rows = WR.facility_rows(w)
    cond = sorted(cf["bank"].get("dd_account_conduct", []), key=lambda r: str(r.get("month") or ""))[-12:]
    cl = I.checklist(cf)
    c = cf["customer"]
    return {"customer": c, "origin": cf["origin"], "existing": bool(c.get("existing")),
            "facilities": [{"facility": r["facility"], "existing_mn": r["existing"], "outstanding_mn": r["outstanding"], "source": r["src"]} for r in rows],
            "conduct_12m": {"credit_turnover_mn": round(sum(WR.num(r.get("credit_turnover_mn")) or 0 for r in cond), 1) if cond else None,
                            "returned_cheques_n": int(sum(WR.num(r.get("returned_cheques_n")) or 0 for r in cond)) if cond else None,
                            "source": "Data Domains · dd_account_conduct" if cond else ""},
            "accounts_n": len(cf["bank"].get("dd_customer_account", [])),
            "checklist": cl, "documents_n": len(cf["documents"]),
            "counts": {s: sum(1 for x in cl if x["status"] == s) for s in ("received", "expired", "missing")},
            "requests": ST.listing(c.get("proposal_id")),
            "ask_hint": _hint(c, rows)}


def _hint(c: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    if rows:
        r = rows[0]
        return f"Renew all and increase the {r['facility'].lower()} to SAR {((r['existing'] or 0) * 1.3):,.0f}m"
    return "New SAR 20m working capital limit, 12 months"


@router.post("/business-requests")
def write_request(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    ref = str(body.get("customer") or body.get("proposal_id") or "").strip()
    ask = str(body.get("ask") or "").strip()
    if not ref:
        raise HTTPException(422, "customer: name the customer (key, proposal id, CIF or CR number)")
    if not ask:
        raise HTTPException(422, "ask: type the ask (for example: renew the facilities and increase the overdraft to SAR 60m)")
    cf = _file(ref, body)
    rm = str(body.get("rm") or _user(request) or "Relationship manager")
    p = PA.write(cf, ask, str(body.get("notes") or ""), rm=rm, written=str(body.get("as_of") or I.AS_OF))
    from backend.dealdesk.rules import hook as rules_hook  # Round K: the RM's, their team's and the bank's rules
    p = rules_hook.on_paper(p, rules_hook.username(request), "request")
    p["written_at"] = ST.now()
    saved = ST.save(p)
    return {**p, "links": links(p["request_id"]), "saved": saved}


@router.get("/business-requests")
def list_requests(proposal_id: str | None = Query(None)) -> dict[str, Any]:
    return {"requests": ST.listing(proposal_id)}


def _get(rid: str) -> dict[str, Any]:
    p = ST.get(rid)
    if p is None:
        raise HTTPException(404, f"no business request {rid}")
    return p


@router.get("/business-requests/{rid}.docx")
def request_docx(rid: str, request: Request) -> Response:
    data, name = RD.docx(_get(rid), generated_by=_user(request))
    return Response(content=data, media_type=DOCX, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/business-requests/{rid}/trace")
def request_trace(rid: str) -> dict[str, Any]:
    p = _get(rid)
    return {"request_id": rid, "figures": p["figures"], "notes_used": p["notes_used"], "untraced": p.get("untraced") or [],
            "sources": sorted({f["source"] for f in p["figures"]})}


@router.post("/business-requests/{rid}/share")
def request_share(rid: str, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    p = _get(rid)
    to = [str(x) for x in (body.get("to") or []) if x]
    prev = [x for x in str(p.get("shared_with") or "").split(",") if x]
    who = ",".join(dict.fromkeys(prev + to))
    saved = ST.save(p, status="shared" if who else p.get("status") or "written", shared_with=who)
    return {"request_id": rid, "shared_with": who.split(",") if who else [], "saved": saved}


@router.get("/business-requests/{rid}")
def request_get(rid: str) -> dict[str, Any]:
    p = _get(rid)
    return {**p, "links": links(rid)}
