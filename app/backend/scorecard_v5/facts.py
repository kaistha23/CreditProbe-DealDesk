"""R16 m (M4): the facts a scorecard validation thread opens with, before the plan.

"Validate the SME scorecard" first shows where the scorecard stands: the Gini on the default plan's monitoring
sample (closed 12-month outcomes) against development, the score PSI at the latest period against the development
deciles, the defaults behind them, and the last validation on record (date, as-of, verdict). Each figure uses the
validation engine's own statistics (`engine._disc`, `engine._psi`, the same deciles as the stability test) on the
scorecard domain (`engine.domain(sid).frame`); thresholds are `engine.thresholds_for(sid)`. Deterministic.

    facts(sid, prior)  -> {"headline": str, "rows": [...], "blocks": [text, table]}
"""
from __future__ import annotations

from typing import Any

import numpy as np

from backend.scorecard_v5 import engine

STATUS_WORD = {engine.GREEN: "green", engine.AMBER: "amber", engine.RED: "red"}


def _word(st: str) -> str:
    return STATUS_WORD.get(st, "not rated")


def facts(sid: str, prior: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """`prior`: earlier validations of this scorecard, newest first, as `Context.prior` lists them
    ({validation_id, as_of, created, overall?})."""
    d = engine.domain(sid)
    sc = engine.scorecards_by_id()[sid]
    plan = engine.default_plan(sid)
    th = engine.thresholds_for(sid)
    f = d.frame
    d0, d1 = plan["development"]
    m0, m1 = plan["monitoring"]
    as_of = plan["as_of"]
    dev = f[(f.period >= d0) & (f.period <= d1)]
    mon = f[(f.period >= m0) & (f.period <= m1) & f.matured]
    dm, dd = engine._disc(mon), engine._disc(dev[dev.matured])
    cuts = np.unique(np.quantile(dev.score.to_numpy(dtype=float), np.linspace(0, 1, 11)[1:-1]))

    def bins(g) -> np.ndarray:
        return np.bincount(np.searchsorted(cuts, g.score.to_numpy(dtype=float), side="right"), minlength=len(cuts) + 1).astype(float)

    psi = engine._psi(bins(dev), bins(f[f.period == as_of]))
    psi_st = engine.rate(psi, th["psi"])
    rows: list[dict[str, Any]] = []
    if dm and dd:
        g_st = engine.rate(dm["gini"], th["gini"])
        rows.append({"measure": "Gini, monitoring sample", "value": f"{dm['gini']:.1%}", "status": _word(g_st),
                     "basis": f"{m0} to {m1}, {dm['n']:,} observations, {dm['defaults']:,} defaults; {th['gini']['text']}"})
        rows.append({"measure": "Gini, development sample", "value": f"{dd['gini']:.1%}", "status": "",
                     "basis": f"{d0} to {d1}, {dd['n']:,} observations, {dd['defaults']:,} defaults"})
    rows.append({"measure": f"Score PSI at {as_of}", "value": f"{psi:.3f}", "status": _word(psi_st),
                 "basis": f"against the development score deciles; {th['psi']['text']}"})
    last = prior[0] if prior else None
    rows.append({"measure": "Last validation", "value": last["created"] if last else "none on record",
                 "status": str(last.get("overall") or "") if last else "",
                 "basis": f"as of {last['as_of']}" if last else "this would be the first validation in the register"})
    gini_txt = (f"its Gini is **{dm['gini']:.1%}** on the monitoring sample ({_word(engine.rate(dm['gini'], th['gini']))}; "
                f"{dd['gini']:.1%} in development)") if dm and dd else "too few closed outcomes to measure its Gini"
    head = (f"**{sc['name']} v{sc['version']} today:** {gini_txt}, the score PSI at {as_of} is **{psi:.3f}** ({_word(psi_st)}), "
            + (f"and it was last validated on {last['created']} (as of {last['as_of']})." if last else "and it has no validation on record yet."))
    table = {"type": "table", "title": f"{sc['name']}: where it stands", "row_count": len(rows),
             "columns": [{"key": "measure", "label": "Measure"}, {"key": "value", "label": "Value"},
                         {"key": "status", "label": "Rating"}, {"key": "basis", "label": "Basis"}], "rows": rows}
    src = f"Source: scorecard domain {sid} ({sc['rows']:,} scored rows, {sc['periods'][0]} to {sc['periods'][1]}) and the validation register."
    return {"headline": head, "rows": rows, "psi": psi, "gini": dm["gini"] if dm else None,
            "gini_development": dd["gini"] if dd else None, "last": last,
            "blocks": [{"type": "text", "markdown": head + "\n\n" + src}, table]}


__all__ = ["facts"]
