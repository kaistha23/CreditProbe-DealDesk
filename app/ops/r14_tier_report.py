"""R14 tier report (PLAN_R14 §m (6); R13 gap J5 "tier High on 44 of 49 demo deals").

    .venv/bin/python ops/r14_tier_report.py                 every dd_deal, both ladders, write the report
    .venv/bin/python ops/r14_tier_report.py --deals R12-TWA,DD-06 --workers 2

Runs the Deal Desk Stress Lab (backend/dealdesk/stress2/ladder.run, the R12 tier rule in stress2/verdict.py) on every
deal in `dd_deal` under two ladders, through the same code path:
  * R14  the ladder in force: set R13-S1 with the regime-conditioned rows (oil reversal from today's level, trade
         disruption as the combined rows) when the current regime is high-oil (backend/scenarios/regime.py);
  * R13  the same set with the R13 unconditioned rows (oil falls from history, the joint-copula combined rows).
It reads the deals and the approval, capacity and covenant engines as merged on the branch it runs on, so session x
re-runs it after merging session e's covenant headroom and capacity fixes (PLAN_R14 §x). Writes
docs/v5/r14_scenarios/tiers.json and tiers.md: tier counts, worst breaking severity, first driver, and why each High
deal is High (fails before any stress / mild break on a data-sized driver / mild break on an expert-sized driver).
Deterministic: no model, no seed; the same branch gives the same report.
"""
from __future__ import annotations

import argparse
import collections
import contextlib
import json
import os
import pathlib
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from typing import Any

V5 = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V5))
OUT = V5 / "docs" / "v5" / "r14_scenarios"
SETS = ("R14", "R13")


@contextlib.contextmanager
def ladder(which: str):
    """R14 = the catalogue as published; R13 = the oil and combined rows replaced by their unconditioned R13 versions."""
    from backend.dealdesk.stress2 import catalogue as cat
    from backend.scenarios import ladder as sl
    if which == "R14":
        yield
        return
    orig = cat.scenarios
    r13 = {r["scenario_id"]: r for r in sl.calibrated_rows(conditioned=False)}
    swap = {k for k in r13 if k.startswith("oil_") or k.startswith("combined_")}

    def scenarios(proposal_id: str | None = None) -> list[dict[str, Any]]:
        out = []
        for r in orig(proposal_id):
            if r["scenario_id"] in swap and r.get("set_id") == sl.SET_ID:
                x = r13[r["scenario_id"]]
                r = {**r, "shocks": x["shocks"], "label": x["label"], "basis": x["basis"]}
            out.append(r)
        return out
    cat.scenarios = scenarios
    try:
        yield
    finally:
        cat.scenarios = orig


def one(args: tuple[str, str]) -> dict[str, Any]:
    pid, which = args
    from backend.dealdesk.data import deals
    from backend.dealdesk.stress2 import ladder as dl
    with ladder(which):
        try:
            r = dl.run(deals.get(pid), None, publish=False, reverse=False, include_chain=False)
        except Exception as e:  # noqa: BLE001 - a deal that cannot run is reported, never hidden
            return {"proposal_id": pid, "set": which, "error": str(e)[:240]}
    v = r["verdict"]
    return {"proposal_id": pid, "set": which, "obligor": r["obligor"], "sector": r["sector"], "tier": r["tier"]["tier"],
            "verdict": v["verdict"], "worst": v["worst_breaking_severity"], "why": v["why"], "drivers": v["driver_labels"],
            "breaking": v["breaking"]}


def classify(x: dict[str, Any], expert: set[str]) -> str:
    if x.get("error"):
        return "error"
    if str(x.get("why", "")).startswith("the structure already fails"):
        return "fails before stress"
    if x.get("worst") == "mild":
        ids = (x.get("breaking") or {}).get("mild", [])
        return "mild break, expert-sized driver" if ids and all(i in expert for i in ids) else "mild break, data-sized driver"
    if x.get("worst") == "moderate":
        return "breaks at moderate"
    if x.get("worst") == "severe":
        return "breaks at severe only"
    return "no break"


def expert_ids() -> set[str]:
    from backend.scenarios import ladder as sl
    return {r["scenario_id"] for r in sl.calibrated_rows() if r["source"].startswith("fallback") or r["family"] == "sector"}


def report(pids: list[str] | None = None, workers: int | None = None, write: bool = True) -> dict[str, Any]:
    from backend.dealdesk.data import store
    from backend.scenarios import regime
    t0 = time.time()
    pids = pids or [r["proposal_id"] for r in store.dd_read("dd_deal")]
    jobs = [(p, w) for w in SETS for p in pids]
    n = workers or max(1, min(4, os.cpu_count() or 2))
    with ProcessPoolExecutor(max_workers=n) as ex:
        res = list(ex.map(one, jobs))
    exp = expert_ids()
    r = regime.current()
    out: dict[str, Any] = {"generated_by": "ops/r14_tier_report.py", "n_deals": len(pids), "regime": r["label"],
                           "regime_as_of": r["as_of"], "sets": {}}
    for w in SETS:
        rows = [x for x in res if x["set"] == w]
        for x in rows:
            x["why_high"] = classify(x, exp) if x.get("tier") == "High" else None
        out["sets"][w] = {
            "label": {"R14": "R13-S1 with the regime-conditioned rows (in force)", "R13": "R13-S1 unconditioned (as merged in R13)"}[w],
            "counts": dict(sorted(collections.Counter(x.get("tier", "error") for x in rows).items())),
            "worst": dict(collections.Counter(str(x.get("worst", "error")) for x in rows)),
            "why_high": dict(collections.Counter(x["why_high"] for x in rows if x.get("why_high"))),
            "first_driver": dict(collections.Counter((x.get("drivers") or ["none"])[0] for x in rows)),
            "deals": rows}
    b = {x["proposal_id"]: x for x in out["sets"]["R13"]["deals"]}
    out["changes"] = [{"proposal_id": x["proposal_id"], "r13": b[x["proposal_id"]].get("tier"), "r14": x.get("tier"),
                       "why_r14": x.get("why")} for x in out["sets"]["R14"]["deals"] if b[x["proposal_id"]].get("tier") != x.get("tier")]
    out["seconds"] = round(time.time() - t0, 1)
    if write:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "tiers.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
        (OUT / "tiers.md").write_text(markdown(out))
    return out


def markdown(o: dict[str, Any]) -> str:
    lines = ["# R14 tier report", "", f"Generated by `ops/r14_tier_report.py` over {o['n_deals']} demo deals (`dd_deal`); "
             f"regime: {o['regime']} (as of {o['regime_as_of']}).", "", "| Ladder | High | Medium | Standard | Other |", "|---|---|---|---|---|"]
    for w, s in o["sets"].items():
        c = s["counts"]
        other = sum(v for k, v in c.items() if k not in ("High", "Medium", "Standard"))
        lines.append(f"| {s['label']} | {c.get('High', 0)} | {c.get('Medium', 0)} | {c.get('Standard', 0)} | {other} |")
    for w, s in o["sets"].items():
        lines += ["", f"## {s['label']}", "", "Why each High deal is High:", ""]
        lines += [f"- {k}: {v}" for k, v in sorted(s["why_high"].items(), key=lambda kv: -kv[1])]
        lines += ["", "Worst breaking severity: " + ", ".join(f"{k} {v}" for k, v in s["worst"].items()),
                  "", "First driver: " + ", ".join(f"{k} {v}" for k, v in sorted(s["first_driver"].items(), key=lambda kv: -kv[1])[:6])]
    lines += ["", "## Deals whose tier changed (R13 → R14)", ""]
    lines += [f"- {c['proposal_id']}: {c['r13']} → {c['r14']} ({c['why_r14']})" for c in o["changes"]] or ["- none"]
    lines += ["", "## Every deal (R14 ladder)", "", "| Deal | Obligor | Sector | Tier | Worst | Why High |", "|---|---|---|---|---|---|"]
    for x in o["sets"]["R14"]["deals"]:
        lines.append(f"| {x['proposal_id']} | {x.get('obligor', '')} | {x.get('sector', '')} | {x.get('tier', x.get('error', ''))} | "
                     f"{x.get('worst', '')} | {x.get('why_high') or ''} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--deals", default="")
    ap.add_argument("--workers", type=int, default=0)
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args(argv)
    o = report([d for d in a.deals.split(",") if d] or None, a.workers or None, write=not a.no_write)
    for w, s in o["sets"].items():
        print(f"{w}: {s['counts']}  worst {s['worst']}  why High {s['why_high']}")
    print(f"{len(o['changes'])} deals changed tier; {o['seconds']} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
