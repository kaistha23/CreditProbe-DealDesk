"""The Deal Desk engine API -- its own app on its own port (8508), prefix /api/v1/dealdesk.

The contract is docs/v5/DEALDESK_API.md. These are the only functions the conversational layer
may call; every response carries a calculation trace ID (GET /traces/{id}).

Reads the Deal Desk domain, the corporate book and the What-If PD model read-only. Writes only
var/dealdesk (traces, user proposals, status changes, parameter versions).
"""
from __future__ import annotations

from typing import Any

from fastapi import Body, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from backend.dealdesk import deposits, desk_params, origination_raroc, proposal_review
from backend.dealdesk import alternatives, constraints, engine, levers, optimizer, params, paths, pd_model, portfolio, proposals, trace
from backend.dealdesk.seed import GRADES

PREFIX = "/api/v1/dealdesk"
VERSION = "dealdesk-engine-1.0.0"

app = FastAPI(title="CreditProbe Deal Desk", version=VERSION)
app.add_middleware(CORSMiddleware, allow_origins=paths.UI_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


def _user(request: Request) -> dict[str, Any]:
    try:
        from backend.identity_v5.client import current_user
        return current_user(request) or {}
    except Exception:  # noqa: BLE001 - the engine answers without the Core service
        return {}


def _proposal(pid: str) -> dict[str, Any]:
    try:
        return proposals.get(pid)
    except KeyError:
        raise HTTPException(404, f"No proposal {pid}.") from None


def _traced(call: str, request: Request, inputs: dict[str, Any], out: dict[str, Any]) -> dict[str, Any]:
    out = engine.public(out)
    tid = trace.record(call, inputs, out, params.versions(), pd_model.model_meta()["version"], _user(request).get("username", ""))
    return {"trace_id": tid, **out}


@app.exception_handler(engine.TermsError)
async def _terms_error(_: Request, exc: engine.TermsError):
    return JSONResponse(status_code=422, content={"detail": str(exc), "errors": exc.errors})


@app.exception_handler(proposals.ProposalError)
async def _proposal_error(_: Request, exc: proposals.ProposalError):
    return JSONResponse(status_code=422, content={"detail": str(exc), "errors": exc.errors})


@app.exception_handler(params.ParamError)
async def _param_error(_: Request, exc: params.ParamError):
    return JSONResponse(status_code=422, content={"detail": str(exc), "errors": [{"field": exc.table, "message": e} for e in exc.errors]})


# ------------------------------------------------------------------ service

@app.get("/health")
@app.get(PREFIX + "/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "service": "dealdesk", "version": VERSION, "model_version": pd_model.model_meta()["version"],
            "param_version": params.version_tag(), "proposals": len(proposals.all_proposals()), "as_of": paths.AS_OF}


@app.get(PREFIX + "/meta")
def meta() -> dict[str, Any]:
    ps = proposals.all_proposals().values()
    return {"facility_types": list(proposals.FACILITY_TYPES), "structures": list(proposals.STRUCTURES),
            "amortisation": list(proposals.PROFILES), "covenant_packages": list(proposals.COVENANTS),
            "collateral_types": list(proposals.COLLATERAL_TYPES), "guarantee_types": list(proposals.GUARANTEE_TYPES),
            "statuses": list(proposals.STATUSES), "rating_order": GRADES,
            "sectors": sorted({p["obligor"]["sector"] for p in ps}), "rms": sorted({p["rm"] for p in ps}),
            "stress_scenarios": {k: v["label"] for k, v in params.rows("stress").items()},
            "levers": list(engine.TERM_KEYS), "breakeven_levers": ["margin_bps", "upfront_fee_bps", "amount", "tenor_years",
                                                                   "cash_margin_pct", "guarantee_coverage_pct"],
            "default_weights": optimizer.DEFAULT_WEIGHTS, "el_views": ["economic", "accounting"],
            "capital_bases": ["regulatory", "economic", "max"], "constraints": sorted(constraints.DEFINITIONS),
            "units": {"money": "SAR m", "rates": "bps in terms, decimals in outputs"}, "as_of": paths.AS_OF,
            "lever_groups": list(levers.GROUPS), "lever_catalogue": levers.catalogue()}


@app.get(PREFIX + "/levers")
def lever_catalogue(request: Request, proposal_id: str = "") -> dict[str, Any]:
    """R5 D4: every lever with its group, channel, owned parameter table and source, and (for a
    proposal) its market and policy bounds, options and the ask's value."""
    p = _proposal(proposal_id) if proposal_id else None
    out = {"groups": list(levers.GROUPS), "levers": levers.catalogue(p)}
    if p is not None:
        out["guarantee_options"] = levers.guarantee_options(p)
        out["proposal_id"] = p["proposal_id"]
    return _traced("levers", request, {"proposal_id": proposal_id}, out)


@app.post(PREFIX + "/alternatives")
def alternative_structures(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """R5 D4: 2-4 alternative structures that clear the hurdle (lever contributions) and the minimum
    change on each single lever, from the ask or from `terms`."""
    p = _proposal(body.get("proposal_id", ""))
    optimizer.split_bounds(body.get("bounds"))
    r = alternatives.analyse_alternatives(p, body.get("terms"), body.get("fixed"), body.get("bounds"),
                                          bool(body.get("allow_soft", False)), **_kw(body))
    r["proposal_id"] = p["proposal_id"]
    return _traced("alternatives", request, body, r)


# ------------------------------------------------------------------ proposals

@app.get(PREFIX + "/proposals")
def list_proposals(request: Request, status: str = "", sector: str = "", rating: str = "", rm: str = "",
                   min_amount: float | None = None, max_amount: float | None = None, q: str = "") -> dict[str, Any]:
    rows = proposals.listing(status, sector, rating, rm, min_amount, max_amount, q)
    return _traced("list_proposals", request, {"status": status, "sector": sector, "rating": rating, "rm": rm,
                                               "min_amount": min_amount, "max_amount": max_amount, "q": q}, {"proposals": rows})


@app.get(PREFIX + "/deals")
def list_deals(request: Request, status: str = "", sector: str = "", rating: str = "", rm: str = "", source: str = "",
               min_amount: float | None = None, max_amount: float | None = None, q: str = "") -> dict[str, Any]:
    """R14 U (K17): every deal the desk knows (dd_deal + uploads, live status), the same filters, fuzzy search."""
    from backend.dealdesk import deal_list
    args = {"status": status, "sector": sector, "rating": rating, "rm": rm, "source": source,
            "min_amount": min_amount, "max_amount": max_amount, "q": q}
    return _traced("list_deals", request, args, deal_list.listing(**args))


@app.get(PREFIX + "/deals/find")
def find_deal(request: Request, q: str = "") -> dict[str, Any]:
    """R14 U (K17): the deal a free-text question names (id or fuzzy obligor name), or null."""
    from backend.dealdesk import deal_list
    return _traced("find_deal", request, {"q": q}, {"deal": deal_list.find_named(q)})


@app.get(PREFIX + "/proposals/{pid}")
def get_proposal(pid: str, request: Request) -> dict[str, Any]:
    return _traced("get_proposal", request, {"proposal_id": pid}, {"proposal": _proposal(pid)})


@app.post(PREFIX + "/proposals")
def create_proposal(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    p = proposals.create(body, owner=_user(request).get("username", ""))
    return _traced("create_proposal", request, {"proposal": body}, {"proposal": p})


@app.post(PREFIX + "/proposals/{pid}/status")
def set_status(pid: str, request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    _proposal(pid)
    p = proposals.set_status(pid, str(body.get("status", "")), str(body.get("note", "")), _user(request).get("username", ""))
    return _traced("set_status", request, {"proposal_id": pid, **body}, {"proposal": p})


@app.get(PREFIX + "/proposals/{pid}/memo.docx")
def memo(pid: str) -> Response:
    _proposal(pid)
    path = proposals.memo_path(pid)
    if path is None:
        raise HTTPException(404, f"{pid} has no memo.")
    return Response(path.read_bytes(), media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={"Content-Disposition": f'attachment; filename="{pid}.docx"'})


# ------------------------------------------------------------------ engine

def _kw(body: dict[str, Any]) -> dict[str, Any]:
    ev = body.get("el_view") or "economic"
    cb = body.get("capital_basis") or None
    if ev not in ("economic", "accounting"):
        raise engine.TermsError([{"field": "el_view", "message": "economic or accounting"}])
    if cb not in (None, "regulatory", "economic", "max"):
        raise engine.TermsError([{"field": "capital_basis", "message": "regulatory, economic or max"}])
    return {"el_view": ev, "capital_basis": cb}


@app.post(PREFIX + "/compute")
def compute(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    p = _proposal(body.get("proposal_id", ""))
    kw = _kw(body)
    a = engine.analyse(p, body.get("terms"), **kw)
    a["proposal_id"] = p["proposal_id"]
    be = engine.breakeven_margin(p, a["terms"], **kw)
    a["metrics"]["breakeven_margin_bps"] = be
    return _traced("compute", request, body, a)


@app.post(PREFIX + "/optimize")
def optimize(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    p = _proposal(body.get("proposal_id", ""))
    obj = body.get("objective") or "both"
    if obj not in ("closest", "max_sva", "both"):
        raise engine.TermsError([{"field": "objective", "message": "closest, max_sva or both"}])
    r = optimizer.optimize(p, body.get("fixed"), body.get("bounds"), body.get("weights"), obj, bool(body.get("allow_soft", False)),
                           **_kw(body))
    r["proposal_id"] = p["proposal_id"]
    return _traced("optimize", request, body, r)


@app.post(PREFIX + "/frontier")
def frontier(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    p = _proposal(body.get("proposal_id", ""))
    r = optimizer.optimize(p, body.get("fixed"), body.get("bounds"), body.get("weights"), "both", bool(body.get("allow_soft", False)),
                           counter_offers=False, **_kw(body))
    return _traced("frontier", request, body, {"proposal_id": p["proposal_id"], "feasible": r["feasible"], "frontier": r["frontier"]})


@app.post(PREFIX + "/stress")
def stress(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    p = _proposal(body.get("proposal_id", ""))
    r = optimizer.stress(p, body.get("terms"), body.get("scenario") or "all", **_kw(body))
    r["proposal_id"] = p["proposal_id"]
    return _traced("stress", request, body, r)


@app.post(PREFIX + "/compare")
def compare(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    p = _proposal(body.get("proposal_id", ""))
    sets = body.get("term_sets") or []
    if not 2 <= len(sets) <= 5:
        raise engine.TermsError([{"field": "term_sets", "message": "2 to 5 term sets"}])
    kw = _kw(body)
    rows = []
    for i, s in enumerate(sets):
        a = engine.analyse(p, s.get("terms"), **kw)
        rows.append({"label": s.get("label") or f"Option {i + 1}", "terms": a["terms"], "metrics": a["metrics"],
                     "approval": a["approval"], "breaches": [c["name"] for c in constraints.breaches(a["constraints"])]})
    diffs = [{"field": k, "values": [r["terms"][k] for r in rows]} for k in engine.TERM_KEYS
             if len({repr(r["terms"][k]) for r in rows}) > 1]
    return _traced("compare", request, body, {"proposal_id": p["proposal_id"], "rows": rows, "differences": diffs})


@app.post(PREFIX + "/breakeven")
def breakeven(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    p = _proposal(body.get("proposal_id", ""))
    r = engine.breakeven(p, body.get("terms"), str(body.get("lever", "margin_bps")), **_kw(body))
    r["proposal_id"] = p["proposal_id"]
    return _traced("breakeven", request, body, r)


@app.post(PREFIX + "/grid")
def grid(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    p = _proposal(body.get("proposal_id", ""))
    xv = body.get("x_values") or []
    yv = body.get("y_values")
    if not xv or len(xv) * (len(yv) if yv else 1) > 400:
        raise engine.TermsError([{"field": "x_values", "message": "1 to 400 grid points"}])
    r = optimizer.grid(p, body.get("terms"), body.get("x", "margin_bps"), xv, body.get("y"), yv, body.get("metric", "lifetime_raroc"), **_kw(body))
    return _traced("grid", request, body, r)


@app.post(PREFIX + "/tornado")
def tornado(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    p = _proposal(body.get("proposal_id", ""))
    return _traced("tornado", request, body, optimizer.tornado(p, body.get("terms"), **_kw(body)))


@app.get(PREFIX + "/headroom")
def headroom(request: Request, obligor_id: str = "", proposal_id: str = "", dimension: str = "") -> dict[str, Any]:
    s = portfolio.snapshot()
    L = {x["name"]: x for x in params.rows("risk_appetite")}
    tot = s["total_ead"]
    if dimension:
        if dimension not in ("sector", "rating_bucket", "collateral_type", "group"):
            raise engine.TermsError([{"field": "dimension", "message": "sector, rating_bucket, collateral_type or group"}])
        src = {"sector": s["by_sector"], "rating_bucket": s["by_bucket"], "collateral_type": s["by_collateral"], "group": s["by_group"]}[dimension]
        rows = []
        for k, v in sorted(src.items(), key=lambda kv: -kv[1])[: 50 if dimension == "group" else None]:
            if dimension == "sector":
                lim = L["sector_appetite"]["limits"].get(k, L["sector_policy"]["limit"])
                kind = "soft" if k in L["sector_appetite"]["limits"] else "hard"
                rows.append({"key": k, "ead": v, "share": v / tot, "limit": lim, "headroom_share": lim - v / tot,
                             "headroom_sar_mn": (lim * tot - v) / (1 - lim), "kind": kind})
            elif dimension == "rating_bucket":
                lim = L["rating_bucket"]["limits"].get(k)
                rows.append({"key": k, "ead": v, "share": v / tot, "limit": lim, "headroom_share": None if lim is None else lim - v / tot,
                             "headroom_sar_mn": None if lim is None or lim >= 1 else (lim * tot - v) / (1 - lim), "kind": "soft"})
            elif dimension == "collateral_type":
                lim = L["collateral_type"]["limits"].get(k)
                rows.append({"key": k, "ead": v, "share": v / tot, "limit": lim, "headroom_share": None if lim is None else lim - v / tot,
                             "headroom_sar_mn": None if lim is None else (lim * tot - v) / (1 - lim), "kind": "soft"})
            else:
                lim = L["group_connected"]["limit"]
                rows.append({"key": k, "name": s["group_names"].get(k, ""), "ead": v, "share": v / tot, "limit": lim,
                             "headroom_sar_mn": lim - v, "kind": "hard"})
        return _traced("headroom", request, {"dimension": dimension}, {"dimension": dimension, "as_of": s["as_of"], "total_ead": tot, "rows": rows})
    if proposal_id:
        p = _proposal(proposal_id)
        ob = p["obligor"]
    else:
        rec = portfolio.borrower(obligor_id)
        if rec is None:
            raise HTTPException(404, f"No obligor {obligor_id} in the corporate book.")
        r = rec["record"]
        ob = {"obligor_id": obligor_id, "existing": True, "group_id": r["connected_group_id"], "group_name": r["connected_group_name"],
              "sector": r["sector"], "internal_rating": r["rating_current"], "name": r["borrower_name"]}
    own = portfolio.obligor_ead(ob["obligor_id"]) if ob.get("existing") else 0.0
    grp = portfolio.group_ead(ob.get("group_id")) if (ob.get("existing") or str(ob.get("group_id", "")).startswith("CG")) else 0.0
    sec = float(s["by_sector"].get(ob["sector"], 0.0))
    t1 = float(params.rows("capital")["tier1_sar_mn"])
    lim_sec = L["sector_appetite"]["limits"].get(ob["sector"])
    rows = [
        {"name": "single_name", "label": L["single_name"]["label"], "used": own, "limit": L["single_name"]["limit"],
         "headroom": L["single_name"]["limit"] - own, "unit": "SAR m", "kind": "hard"},
        {"name": "group_connected", "label": L["group_connected"]["label"], "used": grp, "limit": L["group_connected"]["limit"],
         "headroom": L["group_connected"]["limit"] - grp, "unit": "SAR m", "kind": "hard", "scope": ob.get("group_name", "")},
        {"name": "group_large_exposure", "label": L["group_large_exposure"]["label"], "used": grp,
         "limit": L["group_large_exposure"]["limit_pct_tier1"] * t1, "headroom": L["group_large_exposure"]["limit_pct_tier1"] * t1 - grp,
         "unit": "SAR m", "kind": "hard"},
        {"name": "sector_policy", "label": L["sector_policy"]["label"], "used": sec / tot, "limit": L["sector_policy"]["limit"],
         "headroom": L["sector_policy"]["limit"] - sec / tot, "headroom_sar_mn": (L["sector_policy"]["limit"] * tot - sec) / (1 - L["sector_policy"]["limit"]),
         "unit": "share", "kind": "hard", "scope": ob["sector"]},
    ]
    if lim_sec is not None:
        rows.append({"name": "sector_appetite", "label": L["sector_appetite"]["label"], "used": sec / tot, "limit": lim_sec,
                     "headroom": lim_sec - sec / tot, "headroom_sar_mn": (lim_sec * tot - sec) / (1 - lim_sec), "unit": "share", "kind": "soft",
                     "scope": ob["sector"]})
    return _traced("headroom", request, {"obligor_id": obligor_id, "proposal_id": proposal_id},
                   {"obligor": {"obligor_id": ob["obligor_id"], "name": ob.get("name"), "existing_ead_sar_mn": own,
                                "group_id": ob.get("group_id"), "group_ead_sar_mn": grp}, "limits": rows})


@app.get(PREFIX + "/constraints/{name}")
def explain_constraint(name: str, request: Request, proposal_id: str = "") -> dict[str, Any]:
    try:
        out = constraints.explain(name)
    except KeyError:
        raise HTTPException(404, f"No constraint {name}. Known: {', '.join(sorted(constraints.DEFINITIONS))}.") from None
    if proposal_id:
        a = engine.analyse(_proposal(proposal_id))
        out["deal"] = [c for c in a["constraints"] if c["name"] == name]
    return _traced("explain_constraint", request, {"name": name, "proposal_id": proposal_id}, out)


@app.get(PREFIX + "/portfolio")
def portfolio_view(request: Request) -> dict[str, Any]:
    return _traced("portfolio", request, {}, portfolio.summary())


@app.get(PREFIX + "/model_card")
def model_card(request: Request, proposal_id: str = "") -> dict[str, Any]:
    p = _proposal(proposal_id) if proposal_id else None
    return _traced("model_card", request, {"proposal_id": proposal_id}, pd_model.model_card(p))


@app.get(PREFIX + "/params")
def list_params(request: Request) -> dict[str, Any]:
    tabs = [{"name": t["name"], "owner": t["owner"], "version": t["version"], "effective_from": t["effective_from"],
             "approved_by": t.get("approved_by", ""), "description": t.get("description", "")} for t in params.current().values()]
    return _traced("params", request, {}, {"version": params.version_tag(), "tables": tabs})


@app.get(PREFIX + "/params/{name}")
def get_params(name: str, request: Request) -> dict[str, Any]:
    try:
        t = params.table(name)
    except KeyError:
        raise HTTPException(404, f"No parameter table {name}.") from None
    return _traced("params_table", request, {"name": name}, {"table": t})


@app.put(PREFIX + "/params/{name}")
def put_params(name: str, request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    u = _user(request)
    if not u.get("is_admin"):
        raise HTTPException(403, "Only an Administrator can edit parameter tables.")
    try:
        params.table(name)
    except KeyError:
        raise HTTPException(404, f"No parameter table {name}.") from None
    t = params.edit(name, body.get("rows"), u.get("name") or u.get("username", ""), str(body.get("reason", "")))
    return _traced("params_edit", request, {"name": name, "reason": body.get("reason")}, {"table": t})


# ------------------------------------------------------------------ R9 E1: Admin -> Deal Desk Parameters

@app.get(PREFIX + "/desk_params")
def desk_param_catalogue() -> dict[str, Any]:
    return {"rows": desk_params.catalogue(), "history": desk_params.history(), "version": params.version_tag()}


@app.put(PREFIX + "/desk_params")
def desk_param_edit(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    u = _user(request)
    if not u.get("is_admin"):
        raise HTTPException(403, "Only an Administrator can edit Deal Desk parameters.")
    t = desk_params.set_value(str(body.get("table", "")), str(body.get("key", "")), body.get("value"),
                              u.get("name") or u.get("username", "") or "Administrator", str(body.get("reason", "")))
    return {"version": t["version"], "effective_from": t["effective_from"], "rows": desk_params.catalogue(),
            "cases": proposal_review.cases()}


# ------------------------------------------------------------------ R9 E2: deposits in Deal Desk

@app.get(PREFIX + "/proposals/{pid}/account_behaviour")
def account_behaviour(pid: str) -> dict[str, Any]:
    _proposal(pid)
    return deposits.behaviour(pid)


# ------------------------------------------------------------------ R9 E4: Portfolio RAROC at origination

@app.get(PREFIX + "/portfolio_raroc")
def portfolio_raroc() -> dict[str, Any]:
    return origination_raroc.run()


# ------------------------------------------------------------------ R9 E3: proposal review (P7)

def _case(cid: str) -> str:
    if cid not in proposal_review.CASES:
        raise HTTPException(404, f"No proposal review {cid}.")
    return cid


@app.get(PREFIX + "/review/cases")
def review_cases() -> dict[str, Any]:
    return {"cases": proposal_review.cases(), "powered_by": proposal_review.PACK}


@app.get(PREFIX + "/review/{cid}")
def review_case(cid: str) -> dict[str, Any]:
    return proposal_review.review(_case(cid))


@app.post(PREFIX + "/review/upload")
async def review_upload(file: UploadFile = File(...)) -> dict[str, Any]:
    data = await file.read()
    try:
        return proposal_review.upload(file.filename or "proposal.docx", data)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None


@app.get(PREFIX + "/review/{cid}/opinion.docx")
def review_opinion(cid: str) -> Response:
    c = proposal_review.CASES[_case(cid)]
    return Response(proposal_review.opinion_docx(cid),
                    media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={"Content-Disposition": f'attachment; filename="Review_opinion_{c["borrower"].replace(" ", "_")}.docx"'})


@app.get(PREFIX + "/review/{cid}/proposal.docx")
def review_proposal_file(cid: str) -> Response:
    c = proposal_review.CASES[_case(cid)]
    return Response(proposal_review.proposal_docx(cid),
                    media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={"Content-Disposition": f'attachment; filename="{c["file_name"]}"'})


@app.post(PREFIX + "/review/{cid}/query")
def review_query(cid: str, request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Send an information gap to the RM as a query (recorded under var/dealdesk/review_queries.jsonl)."""
    import json
    from datetime import datetime, timezone
    r = proposal_review.review(_case(cid))
    gap = next((g for g in r["gaps"] if g["id"] == body.get("gap_id")), None)
    if gap is None:
        raise HTTPException(404, "No such information gap.")
    rec = {"case_id": cid, "gap_id": gap["id"], "to": proposal_review.CASES[cid]["rm"], "query": gap["item"],
           "by": _user(request).get("username", "") or "reviewer", "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "status": "Sent to RM"}
    paths.VAR.mkdir(parents=True, exist_ok=True)
    with open(paths.VAR / "review_queries.jsonl", "a") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


@app.get(PREFIX + "/traces/{tid}")
def get_trace(tid: str) -> dict[str, Any]:
    t = trace.get(tid)
    if t is None:
        raise HTTPException(404, f"No trace {tid}.")
    return t


_ = Query


# R11 routers
app.include_router(__import__("backend.dealdesk.r11_forward_api", fromlist=["router"]).router)  # R11 F forward risk
app.include_router(__import__("backend.dealdesk.r11_stress_api", fromlist=["router"]).router)  # Session S: Stress Lab
app.include_router(__import__("backend.dealdesk.r11_pipeline_api", fromlist=["router"]).router)  # R11 L pipeline
app.include_router(__import__("backend.dealdesk.r11_review_api", fromlist=["router"]).router)  # Session R: proposal review
app.include_router(__import__("backend.dealdesk.r11_style_api", fromlist=["router"]).router)  # Session P: house-style drafting
app.include_router(__import__("backend.dealdesk.house_style.onboarding.api", fromlist=["router"]).router)  # Session O: P6 learn from documents

# R12 routers
app.include_router(__import__("backend.dealdesk.workflow", fromlist=["router"]).router)  # R12 U: workflow, role views, landing cards
app.include_router(__import__("backend.dealdesk.review2.api", fromlist=["router"]).router)  # R12 B: review, documents, queries
app.include_router(__import__("backend.dealdesk.group.api", fromlist=["router"]).router)  # R12 C: group, governance, conduct, SWOT
app.include_router(__import__("backend.dealdesk.stress2.api", fromlist=["router"]).router)  # R12 D: stress ladder, editor, monitoring tier
app.include_router(__import__("backend.dealdesk.r12_params_api", fromlist=["router"]).router)  # R12 G: parameters and policy
app.include_router(__import__("backend.dealdesk.book.api", fromlist=["router"]).router)  # R12 I: Book
app.include_router(__import__("backend.dealdesk.products.api", fromlist=["router"]).router)  # R12 P products
app.include_router(__import__("backend.dealdesk.house_style.papers_api", fromlist=["router"]).router)  # R12 F: bank-form proposal and committee paper
app.include_router(__import__("backend.dealdesk.try_docs.api", fromlist=["router"]).router)  # R12 T: try it on your documents + calibration
app.include_router(__import__("backend.agents_v5.brief.api", fromlist=["router"]).router)  # R12 N1: Noor brief

# R13 routers
app.include_router(__import__("backend.dealdesk.fin_quality.api", fromlist=["router"]).router)  # R13 Q: financial-quality detector
app.include_router(__import__("backend.dealdesk.intel.approval.api", fromlist=["router"]).router)  # R13 IA: approval intelligence
app.include_router(__import__("backend.dealdesk.intel.renewal.api", fromlist=["router"]).router)  # R13 IB: renewal autopilot
app.include_router(__import__("backend.dealdesk.intel.covenants.api", fromlist=["router"]).router)  # R13 IB: covenant designer
app.include_router(__import__("backend.intel.calls.api", fromlist=["router"]).router)  # R13 IB: who to call today
# R13 ID: portfolio steering (growth headroom, exits, RWA finder, ECL bridge, workout)
app.include_router(__import__("backend.intel.portfolio.api", fromlist=["router"]).router)  # R13 ID
app.include_router(__import__("backend.intel.governance.api", fromlist=["router"]).router)  # R13 IE: governance and team

# R14 routers
app.include_router(__import__("backend.dealdesk.economics.api", fromlist=["router"]).router)  # R14 E: engines (approval, economics, capacity, findings)
app.include_router(__import__("backend.dealdesk.stressproof.api", fromlist=["router"]).router)  # R14 F: structure set, stress matrix, stress-proofing, recommendation, monitoring
app.include_router(__import__("backend.dealdesk.proposal_check.api", fromlist=["router"]).router)  # R14 p: proposal check and batch check
app.include_router(__import__("backend.dealdesk.intel2.api", fromlist=["router"]).router)  # R14 i: deal intelligence D6-D13
app.include_router(__import__("backend.regulatory.issues.api", fromlist=["router"]).router)  # R14 r: regulatory issue views
app.include_router(__import__("backend.agents_v5.tour.api", fromlist=["router"]).router)  # R14 T: Noor's introduction tour

# R16 b: the RM business request
app.include_router(__import__("backend.dealdesk.rm_request.api", fromlist=["router"]).router)  # R16 b: RM business request (bank form)
# R16 routers
app.include_router(__import__("backend.dealdesk.intake.api", fromlist=["router"]).router)  # R16 i: customer file (document intake)
app.include_router(__import__("backend.dealdesk.credit_response.api", fromlist=["router"]).router)  # R16 c: credit response from a business request
app.include_router(__import__("backend.dealdesk.customer_packs", fromlist=["router"]).router)  # R16 d: customer packs, the Bank's file
# Deal Desk edition, Rounds B and G: Borrower 360 in every deal and customer file; the graph and cross-deal signals
app.include_router(__import__("backend.dealdesk.borrower360.api", fromlist=["router"]).router)  # Round B
app.include_router(__import__("backend.dealdesk.graph.api", fromlist=["router"]).router)  # Round G
app.include_router(__import__("backend.dealdesk.agent_intake.api", fromlist=["router"]).router)  # Round A: the agentic intake (Credit Request Agent)
app.include_router(__import__("backend.dealdesk.intelligence_studio.api", fromlist=["router"]).router)  # Round S: Intelligence Studio
# R16 v router
app.include_router(__import__("backend.agents_v5.voice.api", fromlist=["router"]).router)  # R16 v: offline neural voice (Kokoro, Piper)
# Deal Desk edition, Rounds K and P
app.include_router(__import__("backend.dealdesk.rules.api", fromlist=["router"]).router)  # Round K: the analysts' rules
app.include_router(__import__("backend.dealdesk.rulebook.api", fromlist=["router"]).router)  # Round P: Policy Docs as the rulebook
# Deal Desk edition, Rounds W and T: the living request and proposal, with provenance
app.include_router(__import__("backend.dealdesk.paperws.api", fromlist=["router"]).router)  # Round W/T: paper workspace
