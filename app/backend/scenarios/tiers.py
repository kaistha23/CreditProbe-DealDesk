"""The monitoring-tier distribution across every demo deal (dd_deal), under the R12 ladder (R12-L1, hand-set
severities) and under the calibrated ladder (R13-S1), through the same Stress Lab run and the same R12 tier rule
(`backend/dealdesk/stress2/verdict.py`). Written to docs/v5/r13_scenarios/tiers.json and read by the memo and STATUS.

    python -m backend.scenarios.tiers
"""
from __future__ import annotations

import collections
import contextlib
import json
import os
from concurrent.futures import ProcessPoolExecutor
from typing import Any

from backend.scenarios import ladder as sl13

OUT = sl13.calibrate.data.wpaths.V5 / "docs" / "v5" / "r13_scenarios" / "tiers.json"


@contextlib.contextmanager
def ladder_set(which: str):
    """which = 'R12' (the latest version of each scenario outside set R13-S1) or 'R13' (the version in force)."""
    from backend.dealdesk.stress2 import catalogue as cat
    orig = cat.scenarios
    if which == "R13":
        yield
        return
    if which == "R13rel":
        rel = sl13.calibrate.calibrate_all()["revenue_relative"]["values"]
        ids = dict(zip(("rev_10", "rev_20", "rev_30"), sl13.SEV))

        def r13rel(proposal_id: str | None = None) -> list[dict[str, Any]]:
            out = []
            for r in orig(proposal_id):
                if r["scenario_id"] in ids:
                    r = {**r, "shocks": {"revenue_pct": -round(rel[ids[r["scenario_id"]]] / 100.0, 4)}}
                out.append(r)
            return out
        cat.scenarios = r13rel
        try:
            yield
        finally:
            cat.scenarios = orig
        return

    def r12(proposal_id: str | None = None) -> list[dict[str, Any]]:
        rows = [r for r in cat.all_scenario_rows() if r.get("set_id") != sl13.SET_ID]
        bank = [r for r in rows if r.get("scope") == "bank" and r.get("status") in ("approved", "retired")]
        cur = [r for r in cat._latest(bank, lambda r: r["scenario_id"]).values() if r.get("status") != "retired"]
        order = {r["scenario_id"]: i for i, r in enumerate(cat.seed_ladder())}
        return sorted(cur, key=lambda r: order.get(r["scenario_id"], 999))
    cat.scenarios = r12
    try:
        yield
    finally:
        cat.scenarios = orig


def _one(args: tuple[str, str]) -> dict[str, Any]:
    pid, which = args
    from backend.dealdesk.data import deals
    from backend.dealdesk.stress2 import ladder
    with ladder_set(which):
        try:
            r = ladder.run(deals.get(pid), None, publish=False, reverse=False, include_chain=False)
        except Exception as e:  # noqa: BLE001 - a deal that cannot run is reported, not hidden
            return {"proposal_id": pid, "set": which, "error": str(e)[:200]}
    v = r["verdict"]
    return {"proposal_id": pid, "set": which, "obligor": r["obligor"], "sector": r["sector"], "tier": r["tier"]["tier"],
            "verdict": v["verdict"], "worst": v["worst_breaking_severity"], "why": v["why"], "drivers": v["driver_labels"],
            "breaking": v["breaking"]}


def compare(write: bool = True, workers: int | None = None) -> dict[str, Any]:
    from backend.dealdesk.data import store
    pids = [r["proposal_id"] for r in store.dd_read("dd_deal")]
    jobs = [(p, w) for w in ("R12", "R13", "R13rel") for p in pids]
    n = workers or max(1, min(8, (os.cpu_count() or 2)))
    with ProcessPoolExecutor(max_workers=n) as ex:
        res = list(ex.map(_one, jobs))
    out: dict[str, Any] = {}
    for w in ("R12", "R13", "R13rel"):
        rows = [r for r in res if r["set"] == w]
        out[{"R12": "before", "R13": "after", "R13rel": "revenue_relative"}[w]] = {
            "set": {"R12": "R12-L1", "R13": sl13.SET_ID, "R13rel": sl13.SET_ID + " with revenue rows at the bank's relative-shortfall percentiles"}[w],
            "deals": rows,
            "counts": dict(collections.Counter(r.get("tier", "error") for r in rows)),
            "worst": dict(collections.Counter(r.get("worst", "error") for r in rows)),
            "first_driver": dict(collections.Counter((r.get("drivers") or ["none"])[0] for r in rows))}
    b = {r["proposal_id"]: r for r in out["before"]["deals"]}
    out["changes"] = [{"proposal_id": r["proposal_id"], "before": b[r["proposal_id"]].get("tier"), "after": r.get("tier"),
                       "why_after": r.get("why")} for r in out["after"]["deals"] if b[r["proposal_id"]].get("tier") != r.get("tier")]
    out["n_deals"] = len(pids)
    if write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    return out


def load() -> dict[str, Any] | None:
    return json.loads(OUT.read_text()) if OUT.exists() else None


if __name__ == "__main__":
    rep = compare()
    print("before", rep["before"]["counts"], rep["before"]["worst"])
    print("after ", rep["after"]["counts"], rep["after"]["worst"])
    print("first driver after", rep["after"]["first_driver"])
    print("revenue relative", rep["revenue_relative"]["counts"], rep["revenue_relative"]["worst"])


#: scenario ids whose size in R13-S1 still rests on an expert magnitude (fallback, or a calibrated ratio on the expert downturn)
def _expert_ids() -> set[str]:
    out = set()
    for r in sl13.calibrated_rows():
        if not r["source"].startswith("calibrated") or r["family"] == "sector":
            out.add(r["scenario_id"])
    return out


def diagnose(rep: dict[str, Any]) -> dict[str, Any]:
    """Why each deal is High: the structure fails before stress, or the mildest breaking scenario rests on data or on an
    expert value."""
    exp = _expert_ids()
    out = {}
    for k in ("before", "after", "revenue_relative"):
        if k not in rep:
            continue
        d = {"base_fail": 0, "base_fail_pricing": 0, "mild_data": 0, "mild_expert": 0, "moderate": 0, "high": 0, "mild_by": {}}
        for x in rep[k]["deals"]:
            if x.get("tier") == "High":
                d["high"] += 1
            if str(x.get("why", "")).startswith("the structure already fails"):
                d["base_fail"] += 1
                d["base_fail_pricing"] += "RAROC" in x["why"]
                continue
            if x.get("worst") == "mild":
                ids = x["breaking"].get("mild", [])
                if all(i in exp for i in ids):
                    d["mild_expert"] += 1
                else:
                    d["mild_data"] += 1
                for i in ids:
                    d["mild_by"][i] = d["mild_by"].get(i, 0) + 1
            elif x.get("worst") == "moderate":
                d["moderate"] += 1
        out[k] = d
    return out
