"""What-If accuracy back-test (PLAN_R14 §m (7)): the What-If ECL estimate against the full ECL engine, quarter by quarter.

    python -m backend.whatif_v5.backtest          run on every pair of consecutive quarters and write the report

For each pair of consecutive quarters (t, t+1) of the corporate What-If domain (20 quarters, so 19 one-quarter steps):
  * population: the facilities present in both quarters (new lending and repayments are not a model error);
  * the What-If estimate: the Delta method run at t with the macro moves that actually happened between t and t+1, as a
    one-year shock (Brent: % change of the quarterly average of the EIA monthly prices; non-oil real GDP growth and
    3-month SAIBOR: change of the four-quarter-ending rate, `backend.scenarios.data.macro_at_quarter`);
  * the full engine: the reported final ECL at t+1 of the same facilities (`whatif_corporate.ecl_final`, which reconciles
    to the book's IFRS 9 engine);
  * error = estimate − actual, in SAR m and in % of the actual; the naive benchmark holds the ECL at t.
Statistics: mean absolute error (% of actual), P95 absolute error, the worst quarter, the mean signed error (bias) and
the share of quarters where the What-If beats holding the ECL flat. The rows are published as `whatif_backtest`
(Data Domains, deal_desk folder) and summarised in docs/v5/WHATIF_BACKTEST.md. Deterministic (N4): no model, no seed.
"""
from __future__ import annotations

import functools
import json
import math
import time
from typing import Any

import numpy as np

from backend.whatif_v5 import paths

BOOK = "corporate"
METHOD = "delta"
VERSION = 1
OUT = paths.V5 / "data" / "whatif_v5" / "backtest" / "whatif_backtest.json"
DOC = paths.V5 / "docs" / "v5" / "WHATIF_BACKTEST.md"


def _macro_moves(q0: str, q1: str) -> dict[str, float]:
    from backend.scenarios import data
    a, b = data.macro_at_quarter(q0), data.macro_at_quarter(q1)
    from backend.whatif_v5.domain import mev
    bm = mev.brent_monthly()

    def qavg(q: str) -> float:
        y, n = (int(x) for x in q.split("Q"))
        ms = [f"{y}-{m:02d}" for m in range(3 * n - 2, 3 * n + 1)]
        return float(np.mean([bm[m] for m in ms if m in bm.index]))
    brent = (qavg(q1) / qavg(q0) - 1) * 100
    return {"brent": round(brent, 3), "gdp_nonoil": round(b["gdp_nonoil"] - a["gdp_nonoil"], 4),
            "saibor_3m": round((b["saibor_3m"] - a["saibor_3m"]) * 100, 2)}


def _scenario(q0: str, moves: dict[str, float]):
    from backend.whatif_v5.models.scenario import Scenario, Scope, Shocks, Step
    sh = Shocks(mev={k: v for k, v in moves.items() if abs(v) > 1e-9}, horizon=1)
    step = Step(instruction="realised macro moves", restatement="the macro moves that happened over the quarter",
                shocks=sh, scope=Scope())
    return Scenario(domain=BOOK, period=q0, steps=[step], name=f"back-test {q0}")


def step(q0: str, q1: str) -> dict[str, Any]:
    from backend.whatif_v5.domain import store
    from backend.whatif_v5.models import engine, runner
    f0, f1 = store.frame(BOOK, q0), store.frame(BOOK, q1)
    common = set(f0["exposure_id"]) & set(f1["exposure_id"])
    pop = f0["exposure_id"].isin(common).to_numpy()
    moves = _macro_moves(q0, q1)
    sc = _scenario(q0, moves)
    start = float(f0.loc[pop, "ecl_final"].sum())
    actual = float(f1.loc[f1["exposure_id"].isin(common), "ecl_final"].sum())
    if any(abs(v) > 1e-9 for v in moves.values()):
        res = engine.run(sc, runner.method(METHOD), f0, pop, runner.LABELS[BOOK])
        est = float(res["cards"]["scenario_ecl"])
        start_whatif = float(res["cards"]["start_ecl"])
    else:
        est = start_whatif = start
    err = est - actual
    naive = start - actual
    return {"from_quarter": q0, "to_quarter": q1, "version": VERSION, "book": BOOK, "method": METHOD,
            "facilities": int(pop.sum()), "brent_move_pct": moves["brent"], "gdp_nonoil_move_pp": moves["gdp_nonoil"],
            "saibor_move_bps": moves["saibor_3m"], "ecl_start_mn": round(start, 3), "ecl_start_whatif_mn": round(start_whatif, 3),
            "ecl_estimate_mn": round(est, 3), "ecl_actual_mn": round(actual, 3), "error_mn": round(err, 3),
            "error_pct": round(err / actual * 100, 4) if actual else None, "abs_error_pct": round(abs(err) / actual * 100, 4) if actual else None,
            "naive_error_mn": round(naive, 3), "naive_abs_error_pct": round(abs(naive) / actual * 100, 4) if actual else None,
            "beats_naive_flag": int(abs(err) < abs(naive))}


def stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    a = np.array([r["abs_error_pct"] for r in rows], float)
    s = np.array([r["error_pct"] for r in rows], float)
    nv = np.array([r["naive_abs_error_pct"] for r in rows], float)
    w = rows[int(a.argmax())]
    return {"n_quarters": len(rows), "mean_abs_error_pct": round(float(a.mean()), 2), "p95_abs_error_pct": round(float(np.quantile(a, 0.95)), 2),
            "worst_abs_error_pct": round(float(a.max()), 2), "worst_quarter": f"{w['from_quarter']}→{w['to_quarter']}",
            "worst_error_mn": w["error_mn"], "mean_error_pct": round(float(s.mean()), 2),
            "median_abs_error_pct": round(float(np.median(a)), 2),
            "naive_mean_abs_error_pct": round(float(nv.mean()), 2), "naive_p95_abs_error_pct": round(float(np.quantile(nv, 0.95)), 2),
            "beats_naive": int(sum(r["beats_naive_flag"] for r in rows)),
            "mean_abs_error_mn": round(float(np.mean([abs(r["error_mn"]) for r in rows])), 1)}


def run(write: bool = True) -> dict[str, Any]:
    from backend.whatif_v5.domain import store
    t0 = time.time()
    qs = store.periods(BOOK)
    rows = [step(a, b) for a, b in zip(qs[:-1], qs[1:])]
    st = stats(rows)
    rep = {"relation": "whatif_backtest", "version": VERSION, "book": BOOK, "method": METHOD, "window": f"{qs[0]}–{qs[-1]}",
           "quarters": len(qs), "steps": len(rows), "rows": rows, "stats": st, "line": line(st, len(qs)),
           "seconds": round(time.time() - t0, 1),
           "method_note": ("What-If Delta method at quarter t with the macro moves realised to t+1 (Brent, non-oil GDP, SAIBOR; "
                           "one-year shock) against the full engine's final ECL at t+1 on the facilities present in both "
                           "quarters; naive = ECL held at t.")}
    if write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(rep, indent=1))
        DOC.write_text(doc(rep))
    load.cache_clear()
    return rep


def line(st: dict[str, Any], quarters: int) -> str:
    """The one sentence the tour, the brief and the What-If panel may quote (measured, N5)."""
    return (f"Back-tested on {st['n_quarters']} quarter-to-quarter steps over {quarters} quarters, the What-If estimate of the "
            f"corporate book's ECL was within {st['mean_abs_error_pct']:.1f}% of the full ECL engine on average (P95 "
            f"{st['p95_abs_error_pct']:.1f}%, worst {st['worst_abs_error_pct']:.1f}% in {st['worst_quarter']}); holding the ECL "
            f"flat misses by {st['naive_mean_abs_error_pct']:.1f}% on average.")


@functools.lru_cache(maxsize=1)
def load() -> dict[str, Any] | None:
    return json.loads(OUT.read_text()) if OUT.exists() else None


def relation_rows() -> list[dict[str, Any]]:
    rep = load()
    return [dict(r) for r in rep["rows"]] if rep else []


def doc(rep: dict[str, Any]) -> str:
    st = rep["stats"]
    out = ["# What-If accuracy back-test", "",
           f"Relation `whatif_backtest` (version {rep['version']}, {st['n_quarters']} rows). Produced by "
           "`python -m backend.whatif_v5.backtest` (deterministic; PLAN_R14 §m (7)).", "",
           "## What is measured", "", rep["method_note"], "",
           "## Result", "", rep["line"], "",
           "| Statistic | What-If | Naive (ECL held) |", "|---|---|---|",
           f"| Mean absolute error, % of actual ECL | {st['mean_abs_error_pct']:.2f}% | {st['naive_mean_abs_error_pct']:.2f}% |",
           f"| P95 absolute error | {st['p95_abs_error_pct']:.2f}% | {st['naive_p95_abs_error_pct']:.2f}% |",
           f"| Worst quarter | {st['worst_abs_error_pct']:.2f}% ({st['worst_quarter']}, SAR {st['worst_error_mn']:+,.1f}m) | |",
           f"| Mean signed error (bias) | {st['mean_error_pct']:+.2f}% | |",
           f"| Quarters where What-If beats naive | {st['beats_naive']} of {st['n_quarters']} | |", "",
           "## By quarter", "",
           "| From → to | Facilities | Brent move | Non-oil GDP move | SAIBOR move | ECL start (SAR m) | What-If estimate | Full engine | Error | Error % |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rep["rows"]:
        out.append(f"| {r['from_quarter']} → {r['to_quarter']} | {r['facilities']:,} | {r['brent_move_pct']:+.1f}% | "
                   f"{r['gdp_nonoil_move_pp']:+.2f} pp | {r['saibor_move_bps']:+.0f} bps | {r['ecl_start_mn']:,.1f} | "
                   f"{r['ecl_estimate_mn']:,.1f} | {r['ecl_actual_mn']:,.1f} | {r['error_mn']:+,.1f} | {r['error_pct']:+.2f}% |")
    out += ["", "## What this back-test cannot tell us", "",
            "- The full engine's ECL at t+1 also moves with rating migrations, staging and idiosyncratic defaults the macro "
            "drivers do not carry; the What-If is given only the macro moves, so the error includes everything else that "
            "happened to the same facilities over the quarter.",
            "- 19 steps over one partial cycle (2021Q3–2026Q2): the statistics are indicative, not a validation sample.",
            "- The corporate book only; the retail What-If (20 months) is not back-tested here.", ""]
    return "\n".join(out)


if __name__ == "__main__":
    rep = run()
    print(rep["line"])
    print(json.dumps(rep["stats"], indent=1))
    print(f"{rep['seconds']} s")
