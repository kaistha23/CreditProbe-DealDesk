"""Runs IC scenarios through the What-If v5 engine (Delta method) and returns the per-facility result.

`runner.run` returns book totals and the top 25 movers only; the event translator and the contagion map need every
borrower hit, so this calls the same engine steps `engine.run` calls (`build_context` -> `method.start` -> `evaluate`
with no driver, then with every driver of the scenario plus re-staging) and keeps the per-row arrays. Same engine,
same calibration, same staging rules: the totals equal What-If's `start_ecl` / `scenario_ecl` for the same scenario.
"""
from __future__ import annotations

import time
from typing import Any

import numpy as np
import pandas as pd

from backend.whatif_v5.domain import store as wstore
from backend.whatif_v5.models import engine, runner
from backend.whatif_v5.models.scenario import Scenario, Scope, Step, parse_shocks

METHOD = "delta"


class BridgeError(RuntimeError):
    pass


def frame(period: str) -> pd.DataFrame:
    try:
        return wstore.frame("corporate", wstore.resolve_period("corporate", period))
    except wstore.DomainError as e:
        raise BridgeError(f"The What-If data domain is not built: {e} (ops/whatif_build_domain.py --if-needed).") from e


def step(instruction: str, shocks: dict[str, Any], *, segments: list[str] | None = None, owners: list[str] | None = None,
         exposures: list[str] | None = None) -> Step:
    return Step(instruction=instruction, restatement=instruction, shocks=parse_shocks(shocks),
                scope=Scope(segments=list(segments or []), owners=sorted(set(owners or [])),
                            exposures=sorted(set(exposures or []))))


def run(period: str, steps: list[Step], name: str = "") -> dict[str, Any]:
    """Per-facility before/after for the scenario; `rows` is a DataFrame (owner_id, segment, ead, ecl0, ecl1, stage0, stage1)."""
    t0 = time.time()
    f = frame(period)
    per = str(f["period"].iloc[0]) if len(f) else period
    sc = Scenario(domain="corporate", period=per, steps=steps, name=name)
    pop = np.ones(len(f), dtype=bool)
    m = runner.method(METHOD)
    ctx = engine.build_context(sc, f, pop)
    ctx.start = m.start(ctx)
    ctx.base_h = engine.hazards(ctx.start.mpd)
    cache: dict = {}
    drivers = [d for d in engine.DRIVERS if d in sc.drivers()]
    if drivers and "staging" not in drivers:
        drivers.append("staging")
    v0 = engine.evaluate(ctx, m, frozenset(), cache)
    v1 = engine.evaluate(ctx, m, frozenset(drivers), cache)
    g = ctx.frame
    out = pd.DataFrame({"exposure_id": g["exposure_id"].to_numpy(), "owner_id": g["owner_id"].to_numpy(),
                        "owner_name": g["owner_name"].to_numpy(), "segment": g["segment"].astype(str).to_numpy(),
                        "ead0": g["ead"].to_numpy(dtype=float), "ead1": v1["ead"], "ecl0": v0["ecl"], "ecl1": v1["ecl"],
                        "stage0": v0["stage"].astype(int), "stage1": v1["stage"].astype(int),
                        "pd0": v0["pd12"], "pd1": v1["pd12"]})
    in_scope = np.zeros(len(g), dtype=bool)
    for msk in ctx.masks:
        in_scope |= msk
    out["in_scope"] = in_scope
    return {"period": per, "rows": out, "drivers": drivers, "method": METHOD,
            "method_version": getattr(m, "version", ""), "scenario": sc.to_dict(), "seconds": round(time.time() - t0, 2)}


def totals(rows: pd.DataFrame) -> dict[str, Any]:
    s2b, s2a = rows["stage0"] == 2, rows["stage1"] == 2
    e0, e1 = float(rows["ecl0"].sum()), float(rows["ecl1"].sum())
    return {"ecl_before": e0, "ecl_after": e1, "ecl_change": e1 - e0, "ecl_change_pct": 100 * (e1 - e0) / e0 if e0 else None,
            "stage2_before_n": int(s2b.sum()), "stage2_after_n": int(s2a.sum()),
            "stage2_ead_before": float(rows.loc[s2b, "ead0"].sum()), "stage2_ead_after": float(rows.loc[s2a, "ead1"].sum()),
            "to_stage2_n": int(((rows["stage0"] == 1) & (rows["stage1"] == 2)).sum()),
            "to_stage3_n": int(((rows["stage0"] < 3) & (rows["stage1"] == 3)).sum()),
            "to_stage2_ead": float(rows.loc[(rows["stage0"] == 1) & (rows["stage1"] == 2), "ead1"].sum()),
            "to_stage3_ead": float(rows.loc[(rows["stage0"] < 3) & (rows["stage1"] == 3), "ead1"].sum()),
            "facilities": int(len(rows)), "ead": float(rows["ead0"].sum())}


def by_owner(rows: pd.DataFrame) -> pd.DataFrame:
    r = rows.assign(dEcl=rows["ecl1"] - rows["ecl0"], up2=(rows["stage0"] == 1) & (rows["stage1"] == 2),
                    up3=(rows["stage0"] < 3) & (rows["stage1"] == 3))
    g = r.groupby("owner_id", sort=False).agg(name=("owner_name", "first"), sector=("segment", "first"), ead=("ead0", "sum"),
                                              ecl0=("ecl0", "sum"), ecl1=("ecl1", "sum"), d_ecl=("dEcl", "sum"),
                                              to_stage2=("up2", "sum"), to_stage3=("up3", "sum"),
                                              stage0=("stage0", "max"), stage1=("stage1", "max"))
    return g


def source(period: str) -> dict[str, Any]:
    return {"domain": "What-If", "relation": f"whatif_corporate_{period}", "release": "var/whatif_v5/corporate",
            "method": f"What-If v5 {METHOD} (engine.build_context/evaluate)", "period": period}
