"""The model telemetry over HTTP (Deal Desk edition, model lab): mounted on the Deal Desk service (port 8508).

    GET  {prefix}/telemetry                 the gateway in force (provider, model, base URL, quant, experiment) and totals
    GET  {prefix}/telemetry/calls           the latest rows (?run_id= ?experiment= ?model= ?purpose= ?limit=)
    GET  {prefix}/telemetry/runs            one line per turn: calls, tokens, model time, stages (?experiment=)
    GET  {prefix}/telemetry/summary         tokens and latency by ?by=experiment,model,purpose (any COLUMNS)
    GET  {prefix}/telemetry/export.csv      every row as CSV (?experiment=)
    GET  {prefix}/telemetry/health          is the OpenAI-compatible server reachable and what does it serve

Read-only; the rows are what backend/convo/telemetry.py recorded. The key is never in a row.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse

from backend.convo import provider as prov
from backend.convo import telemetry


def install(app: Any, prefix: str, module: str) -> None:
    """Mount the routes and tag every model call made while serving a request with the module, the request path
    and a request id (the Agent's own run id replaces the request id for a thread turn, see agent.py)."""
    app.include_router(router(prefix))

    @app.middleware("http")
    async def _tag_model_calls(request, call_next):  # type: ignore[no-untyped-def]
        with telemetry.use(module=module, request_path=request.url.path, run_id="RQ-" + telemetry.new_run_id()[3:]):
            return await call_next(request)


def router(prefix: str) -> APIRouter:
    r = APIRouter(prefix=prefix + "/telemetry", tags=["telemetry"])

    def _where(run_id: str | None, experiment: str | None, model: str | None, purpose: str | None) -> dict[str, Any]:
        w = {"run_id": run_id, "experiment": experiment, "model": model, "purpose": purpose}
        return {k: v for k, v in w.items() if v}

    @r.get("")
    def overview() -> dict[str, Any]:
        totals = telemetry.summary(("provider",))
        return {"gateway": prov.describe(), "totals": totals, "log": str(telemetry.log_path()), "db": str(telemetry.db_path())}

    @r.get("/calls")
    def calls(run_id: str | None = None, experiment: str | None = None, model: str | None = None,
              purpose: str | None = None, limit: int = Query(200, ge=1, le=5000)) -> dict[str, Any]:
        rows = telemetry.rows(_where(run_id, experiment, model, purpose), limit=limit)
        return {"rows": rows, "count": len(rows)}

    @r.get("/runs")
    def runs(experiment: str | None = None, model: str | None = None) -> dict[str, Any]:
        rows = telemetry.per_run(_where(None, experiment, model, None))
        return {"runs": rows, "count": len(rows)}

    @r.get("/summary")
    def summary(by: str = "experiment,model,purpose", experiment: str | None = None, model: str | None = None) -> dict[str, Any]:
        cols = tuple(c.strip() for c in by.split(",") if c.strip())
        return {"by": list(cols), "rows": telemetry.summary(cols, _where(None, experiment, model, None))}

    @r.get("/export.csv", response_class=PlainTextResponse)
    def export(experiment: str | None = None, model: str | None = None) -> str:
        return telemetry.export_csv(_where(None, experiment, model, None))

    @r.get("/health")
    def health() -> dict[str, Any]:
        from backend.convo import openai_provider
        out: dict[str, Any] = {"gateway": prov.describe()}
        if openai_provider.enabled():
            out["server"] = openai_provider.health()
        return out

    return r
