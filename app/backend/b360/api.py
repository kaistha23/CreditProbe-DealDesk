"""Borrower 360 API (v5 module 2): `uvicorn backend.b360.api:app --port 8502`.

Read-only. Every response is built from the v5 releases by `service`; nothing
is stored. Routes, under /api/v1/b360:

  GET /health
  GET /search?domain=&q=&period=&limit=        by id or name; empty q ranks the book
  GET /list?domain=&period=&q=&<filters>&sort=&dir=&offset=&limit=
                                                the full book list, paged server-side (booklist)
  GET /list/options?domain=&period=             the values every list filter can take, with counts
  GET /list/export.xlsx?<as /list>&columns=     the filtered, sorted list as a workbook
  GET /customers/{id}?domain=&period=           profile and every tab
  GET /customers/{id}/tab/{tab}?domain=&period= one tab
  GET /customers/{id}/graph?domain=&period=&depth=      the relationship graph and its analytics
  GET /customers/{id}/graph/export.xlsx?domain=&period= the relationships as an Excel workbook
  GET /customers/{id}/export.xlsx?domain=&period=&tab=
                                                one sheet per tab (or the one), plus About
"""
from __future__ import annotations

from typing import Any

from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from backend.access import install
from fastapi.responses import Response

from backend.b360 import booklist, cohort as b360cohort, excel, graph as relgraph, intel, paths, service
from backend.b360.store import NotFound, book_periods
from backend.ews_domain import ews_rules as ews
from backend.house_style import generated_by

PREFIX = "/api/v1/b360"

app = FastAPI(title="CreditProbe v5 Borrower 360", version="1.0.0")
# PLAN_R5 A1: the caller's data access policy on every route (before CORS, so CORS stays outermost).
install(app, "borrower_360")
app.add_middleware(CORSMiddleware, allow_credentials=True, allow_origins=paths.UI_ORIGINS, allow_methods=["GET", "POST"], allow_headers=["*"],
                   expose_headers=["Content-Disposition"])
# PLAN_R13 §I Session IC: network and events (event translator, contagion map, employer exposure)
app.include_router(__import__("backend.intel.network.api", fromlist=["router"]).router)


def _domain(domain: str) -> str:
    if domain not in service.SPEC:
        raise HTTPException(400, f"{domain!r} is not a Borrower 360 book; use corporate or retail.")
    return domain


def _guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except NotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get(PREFIX + "/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "service": "borrower-360", "port": paths.API_PORT,
            "books": {d: {"release": s["book"], "ews_release": s["ews_release"],
                          "periods": [book_periods(d)[0], book_periods(d)[-1]],
                          "tabs": service.tab_keys(d)} for d, s in service.SPEC.items()},
            "external": {"bureau": paths.BUREAU, "open_banking": paths.OPEN_BANKING},
            "ews_ruleset": ews.RULESET_VERSION, "read_only": True}


@app.get(PREFIX + "/search")
def search(domain: str = Query("corporate"), q: str = Query(""), period: str = Query(""),
           limit: int = Query(25, ge=1, le=200)) -> dict[str, Any]:
    return _guard(service.search, _domain(domain), q, period, limit)


def _view(domain: str, period: str, q: str, segment: str, subsegment: str, region: str, branch: str, product: str,
          band: str, stage: str, ews_band: str, dpd: str, ead_min: float | None, ead_max: float | None,
          sort: str, dir: str, extra: dict[str, str] | None = None) -> booklist.View:
    return booklist.View(_domain(domain), period, q,
                         {"segment": segment, "subsegment": subsegment, "region": region, "branch": branch,
                          "product": product, "band": band, "stage": stage, "ews": ews_band, "dpd": dpd,
                          **(extra or {})},
                         ead_min, ead_max, sort, dir)


def _extra(request: Request) -> dict[str, str]:
    """PLAN_R9 B: the P2 filters (sicr, utp, watch, rm, card) read from the query string."""
    return {k: request.query_params.get(k, "") for k in ("sicr", "utp", "watch", "rm", "card")}


@app.get(PREFIX + "/list")
def book_list(request: Request, domain: str = Query("corporate"), period: str = Query(""), q: str = Query(""),
              segment: str = Query(""), subsegment: str = Query(""), region: str = Query(""), branch: str = Query(""),
              product: str = Query(""), band: str = Query(""), stage: str = Query(""), ews_band: str = Query("", alias="ews"),
              dpd: str = Query(""), ead_min: float | None = Query(None), ead_max: float | None = Query(None),
              sort: str = Query(""), dir: str = Query(""), offset: int = Query(0, ge=0),
              limit: int = Query(50, ge=1, le=500)) -> dict[str, Any]:
    v = _view(domain, period, q, segment, subsegment, region, branch, product, band, stage, ews_band, dpd,
              ead_min, ead_max, sort, dir, _extra(request))
    return _guard(booklist.page, v, offset, limit)


@app.get(PREFIX + "/list/options")
def book_list_options(domain: str = Query("corporate"), period: str = Query("")) -> dict[str, Any]:
    return _guard(booklist.options, _domain(domain), period)


@app.get(PREFIX + "/list/export.xlsx")
def book_list_export(request: Request, domain: str = Query("corporate"), period: str = Query(""), q: str = Query(""),
                     segment: str = Query(""), subsegment: str = Query(""), region: str = Query(""),
                     branch: str = Query(""), product: str = Query(""), band: str = Query(""), stage: str = Query(""),
                     ews_band: str = Query("", alias="ews"), dpd: str = Query(""), ead_min: float | None = Query(None),
                     ead_max: float | None = Query(None), sort: str = Query(""), dir: str = Query(""),
                     columns: str = Query("")) -> Response:
    v = _view(domain, period, q, segment, subsegment, region, branch, product, band, stage, ews_band, dpd,
              ead_min, ead_max, sort, dir, _extra(request))
    keys = [k for k in columns.split(",") if k.strip()]
    data, name = _guard(excel.list_workbook, v, keys, generated_by(request))
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.get(PREFIX + "/cards")
def book_cards(domain: str = Query("corporate"), period: str = Query("")) -> dict[str, Any]:
    """PLAN_R9 B1: SICR, UTP, EWS Critical/High, Stage 2/3, Restructured, Accepted Risk Watch, Bank Watchlist,
    Missing financials: count, exposure and % of book, each a list filter (card=)."""
    return _guard(booklist.cards, _domain(domain), period)


@app.post(PREFIX + "/cohort", status_code=201)
def post_cohort(body: dict[str, Any] = Body(...)) -> dict[str, Any]:  # noqa: B008
    """PLAN_R9 B5: freeze the filtered list or the ids given as a What-If population ({domain, period, ids?, query?})."""
    d = _domain(str(body.get("domain") or "corporate"))
    return _guard(b360cohort.freeze, d, str(body.get("period") or ""), list(body.get("ids") or []), dict(body.get("query") or {}))


@app.get(PREFIX + "/customers/{customer_id}/classification")
def customer_classification(customer_id: str, domain: str = Query("corporate"), period: str = Query("")) -> dict[str, Any]:
    """PLAN_R9 B4: the SICR and UTP reasons with article, evidence, value, date and source (Powered by P2)."""
    return _guard(intel.customer, _domain(domain), customer_id, period)


@app.get(PREFIX + "/customers/{customer_id}")
def customer(customer_id: str, domain: str = Query("corporate"), period: str = Query("")) -> dict[str, Any]:
    return _guard(service.customer, _domain(domain), customer_id, period)


@app.get(PREFIX + "/customers/{customer_id}/tab/{tab}")
def customer_tab(customer_id: str, tab: str, domain: str = Query("corporate"),
                 period: str = Query("")) -> dict[str, Any]:
    return _guard(service.tab, _domain(domain), customer_id, period, tab)


@app.get(PREFIX + "/customers/{customer_id}/graph")
def customer_graph(customer_id: str, domain: str = Query("corporate"), period: str = Query(""),
                   depth: int = Query(1, ge=1, le=2)) -> dict[str, Any]:
    return _guard(relgraph.build, _domain(domain), customer_id, period, depth)


@app.get(PREFIX + "/customers/{customer_id}/graph/export.xlsx")
def graph_export(customer_id: str, request: Request, domain: str = Query("corporate"), period: str = Query(""),
                 depth: int = Query(1, ge=1, le=2)) -> Response:
    data, name = _guard(excel.relationships_workbook, _domain(domain), customer_id, period, depth,
                        generated_by(request))
    return Response(content=data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.get(PREFIX + "/customers/{customer_id}/export.xlsx")
def export(customer_id: str, request: Request, domain: str = Query("corporate"), period: str = Query(""),
           tab: str = Query("")) -> Response:
    d = _domain(domain)
    if tab and tab not in service.tab_keys(d):
        raise HTTPException(404, f"{tab!r} is not a Borrower 360 tab for {d}; tabs are {service.tab_keys(d)}.")
    data, name = _guard(excel.workbook, d, customer_id, period, tab, generated_by(request))
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})
