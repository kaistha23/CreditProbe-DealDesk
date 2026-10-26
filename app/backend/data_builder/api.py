"""The Data Builder API -- "Browse the data" over every v5 data domain.

Its own app on its own port (8504 by default). It reads the domains' parquet
releases and manifests read-only through `store` and imports nothing from the
Cockpit (backend.cockpit_v4) or the spine (backend.spine).

    GET /api/v1/data/health
    GET /api/v1/data/domains
    GET /api/v1/data/relations/{domain}/{relation}/schema
    GET /api/v1/data/relations/{domain}/{relation}/rows
    GET /api/v1/data/relations/{domain}/{relation}/export.csv
    GET /api/v1/data/relations/{domain}/{relation}/export.xlsx
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import re
from collections.abc import Iterator
from typing import Any

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from backend.access import install
from fastapi.responses import JSONResponse, Response, StreamingResponse

from backend.data_builder import store
from backend.house_style import Meta, generated_by, stream
from backend.house_style.xlsx import Col
from backend.data_builder.paths import UI_ORIGINS
from backend.data_builder.registry import DOMAINS

PREFIX = "/api/v1/data"
XLSX_ROW_CAP = 200_000

app = FastAPI(title="CreditProbe v5 Data Domains", version="1.0.0",
              description="Browse every v5 data domain, read-only.")
# PLAN_R5 A1: the caller's data access policy on every route (before CORS, so CORS stays outermost).
install(app, "data_builder")
app.add_middleware(CORSMiddleware, allow_credentials=True, allow_origins=UI_ORIGINS, allow_methods=["GET"], allow_headers=["*"],
                   expose_headers=["Content-Disposition", "X-Total-Rows", "X-Exported-Rows"])


@app.exception_handler(store.Refused)
async def _refused(_: Request, exc: store.Refused) -> JSONResponse:
    return JSONResponse({"detail": str(exc)}, status_code=exc.status)


def _view(domain: str, relation: str, period: str | None, compare_period: str | None, search: str | None,
          filters: str | None, columns: str | None, sort: str | None, desc: bool) -> store.Plan:
    store.spec(domain, relation)  # 404 before anything else
    return store.Plan(store.View(domain=domain, relation=relation, period=(period or None) if period != "all" else None,
                                 compare_period=compare_period or None, search=search or "",
                                 filters=store.parse_filters(filters), columns=store.parse_columns(columns),
                                 sort=sort or None, desc=desc))


_P = {
    "period": Query(None, description="A period of the relation; omitted or 'all' for every period."),
    "compare_period": Query(None, description="A second period, shown side by side with deltas."),
    "search": Query(None, description="Free text, matched across the text and ID columns."),
    "filters": Query(None, description='JSON list of {"column", "op", "value"}; op in '
                                       + "|".join(store.OPS) + "."),
    "columns": Query(None, description="Comma-separated subset of columns to show."),
    "sort": Query(None), "desc": Query(False),
}


@app.get(f"{PREFIX}/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "service": "data_builder", "domains": len(DOMAINS),
            "relations": sum(len(d["relations"]) for d in DOMAINS.values())}


@app.get(f"{PREFIX}/domains")
def domains() -> dict[str, Any]:
    return store.domains_payload()


@app.get(f"{PREFIX}/relations/{{domain}}/{{relation}}/schema")
def relation_schema(domain: str, relation: str) -> dict[str, Any]:
    rel = store.spec(domain, relation)
    f = store.facts(domain, relation)
    return {"domain": domain, "domain_label": DOMAINS[domain]["label"], "relation": relation,
            "relation_label": rel["label"], "book": rel["book"], "release_id": store.release_of(rel),
            "period_column": rel.get("period_column"), "key_columns": rel["key_columns"],
            "periods": f["periods"], "latest_period": f["latest_period"], "rows": f["rows"],
            "columns": store.schema(domain, relation)}


@app.get(f"{PREFIX}/relations/{{domain}}/{{relation}}/rows")
def relation_rows(domain: str, relation: str,
                  period: str | None = _P["period"], compare_period: str | None = _P["compare_period"],
                  search: str | None = _P["search"], filters: str | None = _P["filters"],
                  columns: str | None = _P["columns"], sort: str | None = _P["sort"], desc: bool = _P["desc"],
                  limit: int = Query(50, ge=1, le=store.MAX_PAGE), offset: int = Query(0, ge=0)) -> dict[str, Any]:
    plan = _view(domain, relation, period, compare_period, search, filters, columns, sort, desc)
    return {**plan.describe_view(), "total": plan.count(), "limit": limit, "offset": offset,
            "columns": plan.out_columns, "rows": plan.page(limit, offset)}


def _filename(plan: store.Plan, ext: str) -> str:
    parts = [plan.view.domain, plan.view.relation, plan.period or "all-periods"]
    if plan.compare:
        parts += ["vs", plan.compare]
    return re.sub(r"[^A-Za-z0-9._-]+", "-", "_".join(parts)) + f".{ext}"


def _headers(plan: store.Plan, ext: str, total: int, exported: int) -> dict[str, str]:
    return {"Content-Disposition": f'attachment; filename="{_filename(plan, ext)}"',
            "X-Total-Rows": str(total), "X-Exported-Rows": str(exported)}


@app.get(f"{PREFIX}/relations/{{domain}}/{{relation}}/export.csv")
def export_csv(domain: str, relation: str,
               period: str | None = _P["period"], compare_period: str | None = _P["compare_period"],
               search: str | None = _P["search"], filters: str | None = _P["filters"],
               columns: str | None = _P["columns"], sort: str | None = _P["sort"],
               desc: bool = _P["desc"]) -> StreamingResponse:
    plan = _view(domain, relation, period, compare_period, search, filters, columns, sort, desc)
    total = plan.count()

    def body() -> Iterator[bytes]:
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow([c["name"] for c in plan.out_columns])
        for batch in plan.stream():
            w.writerows(batch)
            yield buf.getvalue().encode("utf-8")
            buf.seek(0)
            buf.truncate()
        tail = buf.getvalue()
        if tail:
            yield tail.encode("utf-8")

    return StreamingResponse(body(), media_type="text/csv; charset=utf-8",
                             headers=_headers(plan, "csv", total, total))


@app.get(f"{PREFIX}/relations/{{domain}}/{{relation}}/export.xlsx")
def export_xlsx(domain: str, relation: str, request: Request,
                period: str | None = _P["period"], compare_period: str | None = _P["compare_period"],
                search: str | None = _P["search"], filters: str | None = _P["filters"],
                columns: str | None = _P["columns"], sort: str | None = _P["sort"],
                desc: bool = _P["desc"]) -> Response:
    plan = _view(domain, relation, period, compare_period, search, filters, columns, sort, desc)
    total = plan.count()
    exported = min(total, XLSX_ROW_CAP)
    rel = store.spec(domain, relation)
    book = "retail" if "retail" in relation else "corporate" if ("corp" in relation or "corporate" in domain) else ""
    meta = Meta(f"Data Domains · {rel['label']}", book=book, period=plan.period or "All periods",
                subject=f"{DOMAINS[domain]['label']} · {relation}" + (f" · compared with {plan.compare}" if plan.compare else ""),
                generated_by=generated_by(request))
    cols = [Col(c["name"], c["name"], _kind(c)) for c in plan.out_columns]
    data = stream.Sheet("Data", meta, cols, (row for batch in plan.stream(cap=XLSX_ROW_CAP) for row in batch),
                        title=f"{rel['label']} · {plan.period or 'All periods'}")

    note = ("All matching rows." if exported == total else
            f"Capped: the first {exported:,} of {total:,} matching rows (Excel export limit). "
            "Use Export CSV for every row.")
    about = stream.about(meta, [
        ("Domain", f"{DOMAINS[domain]['label']} ({domain})"),
        ("Relation", f"{rel['label']} ({relation})"),
        ("Release", store.release_of(rel)),
        ("Period", plan.period or "All periods"),
        ("Compared with", plan.compare or "-"),
        ("Compare basis", plan.describe_view()["compare_basis"] or "-"),
        ("Search", plan.view.search or "-"),
        ("Filters", json.dumps(plan.view.filters) if plan.view.filters else "-"),
        ("Columns", ", ".join(c["name"] for c in plan.out_columns)),
        ("Sort", f"{plan.view.sort} {'descending' if plan.view.desc else 'ascending'}" if plan.view.sort
         else "Key columns"),
        ("Matching rows", total),
        ("Rows in this file", exported),
        ("Row cap", note),
        ("Service", "CreditProbe v5 Data Domains (read-only)"),
    ])

    dic = stream.Sheet("Dictionary", meta, [Col("name", "Column"), Col("type", "Type"), Col("unit", "Unit"),
                                            Col("description", "Description"), Col("source", "Source")],
                       ([c["name"], c["type"], c.get("unit", ""), c.get("description", ""), c.get("source", "")]
                        for c in plan.out_columns), title=f"Dictionary · {rel['label']}", widths={4: 90})

    return Response(stream.write([about, data, dic], meta),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers=_headers(plan, "xlsx", total, exported))


#: Data Builder units to house-style number formats.
_UNIT_KIND = {"sar million": "sar_mn", "sar thousand": "sar_k", "percent": "pct", "pct": "pct", "%": "pct",
              "probability_0_1": "prob", "bps": "bps", "count": "int", "days": "days", "months": "months",
              "times": "x", "x": "x", "pp": "num", "percentage points": "num", "rcy": "num", "index": "num",
              "notches": "num", "points": "num"}


def _kind(col: dict[str, Any]) -> str:
    if col.get("type") in ("text", "string", "varchar", "date"):
        return "rating" if "rating" in col["name"] or "grade" in col["name"] else "text"
    return _UNIT_KIND.get(str(col.get("unit") or "").lower(), "")
