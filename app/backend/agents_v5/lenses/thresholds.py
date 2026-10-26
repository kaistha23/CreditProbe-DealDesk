"""Threshold logic and the 8-quarter back-test (PLAN_R11_AGENTS K2).

Four kinds of threshold, each evaluated only on what was known at the time:
  absolute   the value crosses a fixed level (a regulatory trigger: Stage 3 above 5%, any 30+ DPD still in Stage 1)
  change     the move against the previous observation exceeds k (percentage points for shares, bps for cost of risk,
             a relative % for amounts and counts)
  zscore     the move is more than k standard deviations from the metric's own recent moves (its last 8 changes)
  appetite   the value is past the risk-appetite trigger (amber) or limit (red); the distance to the limit is reported

`backtest` replays a threshold over the last 8 quarterly observations and reports the alert rate and the quarters it
would have fired, so the noise of a proposed metric is visible before anyone approves it. `calibrate` picks the
change or z-score parameter that gives a useful rate (target 1-3 alerts in 8 quarters) from a short grid, and says
which grid point it chose.
"""
from __future__ import annotations

import math
import statistics
from typing import Any

RELATIVE_UNITS = ("sar_mn", "count")
N_BACKTEST = 8
TARGET = (1, 3)        # alerts in 8 quarters that make a threshold useful


def adverse(better: str) -> str:
    return {"lower": "up", "higher": "down"}.get(better, "both")


def _delta(v1: float, v0: float, unit: str) -> float | None:
    if unit in RELATIVE_UNITS:
        return None if not v0 else (v1 - v0) / abs(v0) * 100
    return v1 - v0


def _hit(x: float, k: float, direction: str) -> bool:
    return x >= k if direction == "up" else x <= -k if direction == "down" else abs(x) >= k


def evaluate(values: list[float | None], th: dict[str, Any], unit: str) -> dict[str, Any]:
    """Does the threshold fire at the last point of `values` (oldest first)? Uses only the values given."""
    logic, direction = th["logic"], th.get("direction", "up")
    v = values[-1] if values else None
    if v is None:
        return {"fired": False, "measure": None, "reason": "no value"}
    if logic == "absolute":
        lv = float(th["level"])
        fired = v >= lv if direction != "down" else v <= lv
        return {"fired": fired, "measure": v, "level": lv, "severity": "high" if fired else ""}
    if logic == "appetite":
        trig, lim = float(th["trigger"]), float(th["limit"])
        sev = "red" if v >= lim else "amber" if v >= trig else ""
        return {"fired": bool(sev), "measure": v, "severity": sev, "distance_to_limit": round((lim - v) / lim * 100, 2) if lim else None}
    prev = values[-2] if len(values) > 1 else None
    if prev is None:
        return {"fired": False, "measure": None, "reason": "no previous value"}
    dlt = _delta(v, prev, unit)
    if dlt is None:
        return {"fired": False, "measure": None, "reason": "previous value is zero"}
    if logic == "change":
        k = float(th["k"])
        return {"fired": _hit(dlt, k, direction), "measure": round(dlt, 4), "k": k}
    if logic == "zscore":
        hist = [_delta(b, a, unit) for a, b in zip(values[:-2], values[1:-1], strict=False) if a is not None and b is not None]
        hist = [h for h in hist if h is not None][-int(th.get("history", 8)):]
        if len(hist) < 4:
            return {"fired": False, "measure": None, "reason": "fewer than 4 past moves"}
        mu = statistics.fmean(hist)
        sd = statistics.pstdev(hist)
        if sd <= 1e-9:
            # a metric that never moved: any move is unusual; measure it against a tiny spread
            sd = max(abs(mu) * 0.05, 1e-6)
        z = (dlt - mu) / sd
        return {"fired": _hit(z, float(th["k"]), direction), "measure": round(z, 2), "move": round(dlt, 4), "k": float(th["k"])}
    raise ValueError(f"unknown threshold logic {logic}")


def backtest(grid: list[str], series: dict[str, float | None], th: dict[str, Any], unit: str, n: int = N_BACKTEST) -> dict[str, Any]:
    """Replay over the last n points of the grid; each point sees only its own past."""
    vals = [series.get(p) for p in grid]
    fired, evaluated = [], []
    start = max(1, len(grid) - n)
    for i in range(start, len(grid)):
        r = evaluate(vals[: i + 1], th, unit)
        if r.get("measure") is None and th["logic"] not in ("absolute", "appetite"):
            continue
        if vals[i] is None:
            continue
        evaluated.append(grid[i])
        if r["fired"]:
            fired.append(grid[i])
    rate = len(fired) / len(evaluated) if evaluated else None
    return {"quarters": len(evaluated), "fired": len(fired), "rate": None if rate is None else round(rate, 3),
            "fired_periods": fired, "evaluated_periods": evaluated, "label": label(len(fired), len(evaluated))}


def label(fired: int, quarters: int) -> str:
    if not quarters:
        return "no history to back-test"
    return f"{fired} of {quarters} quarters"


def noise(bt: dict[str, Any]) -> str:
    """never | quiet | useful | noisy | constant"""
    q, f = bt.get("quarters") or 0, bt.get("fired") or 0
    if not q:
        return "untested"
    if f == 0:
        return "never"
    if f >= q - 1 and q >= 4:
        return "constant"
    if f / q > 0.5:
        return "noisy"
    return "useful"


def calibrate(grid: list[str], series: dict[str, float | None], unit: str, direction: str) -> dict[str, Any]:
    """Pick the change or z-score threshold with a useful back-tested alert rate. Returns the threshold, its back-test
    and the grid it searched (shown in the rationale)."""
    vals = [series.get(p) for p in grid]
    moves = [abs(d) for a, b in zip(vals[:-1], vals[1:], strict=False) if a is not None and b is not None and (d := _delta(b, a, unit)) is not None]
    tried: list[dict[str, Any]] = []
    if moves:
        med = statistics.median(moves)
        base = _nice(med)
        for mult in (1.0, 1.5, 2.0, 3.0):
            k = _nice(base * mult) if base > 0 else 0.1 * mult
            th = {"logic": "change", "direction": direction, "k": k}
            tried.append({"threshold": th, "backtest": backtest(grid, series, th, unit)})
    for k in (1.5, 2.0, 2.5):
        th = {"logic": "zscore", "direction": direction, "k": k, "history": 8}
        tried.append({"threshold": th, "backtest": backtest(grid, series, th, unit)})
    lo, hi = TARGET

    def score(t: dict[str, Any]) -> tuple[float, int]:
        bt = t["backtest"]
        f = bt["fired"]
        inside = lo <= f <= hi
        # prefer inside the target, then near 2 alerts, then the simpler change logic
        return (0 if inside else 1) + abs(f - 2) * 0.1, 0 if t["threshold"]["logic"] == "change" else 1
    best = min(tried, key=score) if tried else None
    return {"chosen": best, "searched": [{"logic": t["threshold"]["logic"], "k": t["threshold"]["k"], "fired": t["backtest"]["fired"],
                                          "quarters": t["backtest"]["quarters"]} for t in tried]}


def _nice(x: float) -> float:
    """Round a step to 1, 2 or 5 x 10^n so thresholds read well (0.5pp, 2%, 20 bps)."""
    if x <= 0 or math.isnan(x):
        return 0.0
    e = math.floor(math.log10(x))
    f = x / 10 ** e
    n = 1 if f < 1.5 else 2 if f < 3.5 else 5 if f < 7.5 else 10
    return round(n * 10 ** e, 6)


def describe(th: dict[str, Any], unit: str) -> str:
    d = {"up": "rises", "down": "falls", "both": "moves"}[th.get("direction", "up")]
    u = {"pct": "pp", "bps": " bps", "ratio": "", "score": " points", "days": " days"}.get(unit, "%")
    if th["logic"] == "absolute":
        return f"Alert when the value {'is at or above' if th.get('direction', 'up') != 'down' else 'is at or below'} {_fmt(th['level'], unit)}"
    if th["logic"] == "appetite":
        return f"Amber at the risk-appetite trigger {_fmt(th['trigger'], unit)}, red at the limit {_fmt(th['limit'], unit)}"
    if th["logic"] == "change":
        return f"Alert when it {d} by {th['k']:g}{u} or more against the previous quarter"
    return f"Alert when the quarter's move is {th['k']:g} standard deviations beyond its last 8 moves"


def _fmt(v: float, unit: str) -> str:
    from backend.lenses_v5 import fmt
    return fmt.fmt_value(v, unit)
