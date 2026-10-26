"""R13 IE item 22: DoA calibration.

Where approval levels add delay without changing decisions. For every level of the delegation of authority
(dd_parameter doa) the engine reads each past file's approval steps (gov_approval_step): days at the level, and what
the level did, both when it only passed the file up (pass-through) and when it was the deciding level. A level
"changes" a file when it amends terms, declines or overturns the recommendation. Rates carry 95% Wilson intervals.

Redesign rules (deterministic):
  1. Pass-through sign-off: a level whose pass-through change rate has an upper bound below 5% (n >= 30) and that
     holds files for 2 days or more stops signing files it does not decide (it is copied, not asked).
  2. Delegation lift: for each deciding level, files rated BB- or better that it decided with no change (n >= 30,
     change rate upper bound below 8%): the level below takes them up to the 75th percentile of their limits,
     rounded to SAR 5 million. The control given up is counted: files in that band where the level did change something.
Days saved are medians per file times files per year over the history.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from backend.v5common.ratings import rank as rrank

from . import common as C
from .seed import doa_levels

MIN_N = 30
PASS_MAX_CHANGE = 0.05
LIFT_MAX_CHANGE = 0.08
REL = ["gov_approval_step", "gov_decision", "dd_parameter"]


def _frame() -> pd.DataFrame:
    s, d = C.steps(), C.decisions()
    if s.empty or d.empty:
        return pd.DataFrame()
    m = s.merge(d[["decision_id", "required_level_rank", "limit_sar_mn", "rating_at_decision", "decision",
                   "decision_quarter", "exception_count", "turnaround_days"]], on="decision_id")
    m["role"] = np.where(m["level_rank"] == 0, "review",
                         np.where(m["level_rank"] == m["required_level_rank"], "deciding", "pass-through"))
    m["changed"] = m["changed_flag"].astype(int)
    return m


def by_level(m: pd.DataFrame) -> list[dict[str, Any]]:
    out = []
    total_days = float(m.groupby("decision_id")["days"].sum().sum())
    for (rk, name), g in m.groupby(["level_rank", "level_name"]):
        pt, dc = g[g["role"] == "pass-through"], g[g["role"] == "deciding"]
        row = {"rank": int(rk), "level": name, "files": int(len(g)),
               "median_days": round(float(g["days"].median()), 1), "p75_days": round(float(g["days"].quantile(.75)), 1),
               "share_of_turnaround_pct": round(100 * float(g["days"].sum()) / total_days, 1) if total_days else None,
               "pass_through": {"n": int(len(pt)), "changed": C.rate(int(pt["changed"].sum()), len(pt)) if len(pt) else None,
                                "median_days": round(float(pt["days"].median()), 1) if len(pt) else None},
               "deciding": {"n": int(len(dc)), "changed": C.rate(int(dc["changed"].sum()), len(dc)) if len(dc) else None,
                            "declined": C.rate(int((dc["output"] == "decline").sum()), len(dc)) if len(dc) else None,
                            "overturned": C.rate(int((dc["output"] == "overturn").sum()), len(dc)) if len(dc) else None,
                            "amended": C.rate(int((dc["output"] == "amend").sum()), len(dc)) if len(dc) else None},
               "figure": C.computed(float(g["days"].median()), "days", REL, len(g), "median calendar days at the level",
                                    {"level_rank": int(rk)})}
        out.append(row)
    return sorted(out, key=lambda r: r["rank"])


def _years(m: pd.DataFrame) -> float:
    q = m["decision_quarter"].map(C.q_index)
    return max(1.0, (q.max() - q.min() + 1) / 4)


def proposals(m: pd.DataFrame, levels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    yrs = _years(m)
    names = {lv["rank"]: lv["level"] for lv in levels}
    # rule 1: pass-through sign-off adds days without changing files
    for (rk, name), g in m[m["role"] == "pass-through"].groupby(["level_rank", "level_name"]):
        n, k = len(g), int(g["changed"].sum())
        lo, hi = C.wilson(k, n)
        med = float(g["days"].median())
        if n >= MIN_N and hi < PASS_MAX_CHANGE and med >= 2.0:
            out.append({"rule": "pass_through", "level": name, "rank": int(rk), "n": n, "changed": C.rate(k, n),
                        "change": f"{name} stops signing files it does not decide; it is copied for information.",
                        "days_saved_per_file": round(med, 1), "files_per_year": round(n / yrs),
                        "days_saved_per_year": round(med * n / yrs), "control_given_up": k,
                        "why": f"It changed {k:,} of {n:,} files it passed up ({100 * k / n:.1f}%, upper bound {100 * hi:.1f}%) "
                               f"and held each for a median {med:.1f} days."})
    # rule 2: delegation lift for well-rated files the deciding level never changes
    cur = {lv["rank"]: lv for lv in levels}
    for rk in sorted(m["required_level_rank"].unique()):
        if rk <= 1 or rk - 1 not in cur:
            continue
        g = m[(m["role"] == "deciding") & (m["level_rank"] == rk)]
        g = g[g["rating_at_decision"].map(rrank) <= rrank("BB-")]
        g = g[g["exception_count"] == 0]
        n, k = len(g), int(g["changed"].sum())
        if n < MIN_N:
            continue
        lo, hi = C.wilson(k, n)
        if hi >= LIFT_MAX_CHANGE:
            continue
        unchanged = g[g["changed"] == 0]
        new_cap = float(np.ceil(unchanged["limit_sar_mn"].quantile(.75) / 5.0) * 5.0)
        old_cap = float(cur[rk - 1]["max_exposure"])
        if new_cap <= old_cap:
            continue
        lower = names[rk - 1]
        moved = g[g["limit_sar_mn"] <= new_cap]
        days = m[(m["decision_id"].isin(moved["decision_id"])) & (m["level_rank"] == rk)]["days"]
        out.append({"rule": "delegation_lift", "level": lower, "rank": int(rk - 1), "from_level": names[rk], "n": n,
                    "changed": C.rate(k, n),
                    "change": f"{lower} decides files rated BB- or better with no policy exception up to SAR {new_cap:,.0f}m "
                              f"(today SAR {old_cap:,.0f}m and {cur[rk - 1]['min_rating']} or better; these go to {names[rk]}).",
                    "param": {"table": "doa", "key": f"{lower}.max_exposure", "from": old_cap, "to": new_cap,
                              "min_rating_from": cur[rk - 1]["min_rating"], "min_rating_to": "BB-",
                              "condition": "rating BB- or better and no policy exception"},
                    "files_per_year": round(len(moved) / yrs), "days_saved_per_file": round(float(days.median()), 1) if len(days) else 0,
                    "days_saved_per_year": round(float(days.sum()) / yrs),
                    "control_given_up": int(moved["changed"].sum()),
                    "why": f"{names[rk]} changed {k:,} of {n:,} such files ({100 * k / n:.1f}%, upper bound {100 * hi:.1f}%)."})
    return out


def write(levels: list[dict[str, Any]], props: list[dict[str, Any]], m: pd.DataFrame) -> list[str]:
    tt = m.drop_duplicates("decision_id")["turnaround_days"]
    lines = [f"{m['decision_id'].nunique():,} files: median turnaround {tt.median():.0f} days (P75 {tt.quantile(.75):.0f})."]
    slow = max((lv for lv in levels if lv["rank"] > 0), key=lambda lv: lv["share_of_turnaround_pct"] or 0)
    lines.append(f"{slow['level']} holds the largest share of time: {slow['share_of_turnaround_pct']:.0f}% of all days, "
                 f"median {slow['median_days']:.1f} days per file.")
    for p in props[:2]:
        lines.append(f"{p['change']} {p['why']} Saves about {p['days_saved_per_year']:,} file-days a year; "
                     f"{p['control_given_up']} past changes would have been forgone.")
    if not props:
        lines.append("No level meets the redesign rules: every level changes enough files to earn its time.")
    return lines[:5]


def analyse() -> dict[str, Any]:
    m = _frame()
    if m.empty:
        return {"available": False, "lines": ["No approval history in Data Domains (governance domain is empty)."],
                "data_note": C.SEED_NOTE}
    levels_cfg = doa_levels()
    lv = by_level(m)
    props = proposals(m, levels_cfg)
    return {"available": True, "kind": "doa_calibration", "as_of": C.AS_OF_QUARTER, "lines": write(lv, props, m),
            "levels": lv, "proposals": props,
            "doa_today": [{**x, "source": {"relation": "dd_parameter", "filter": {"table_name": "doa"}}} for x in levels_cfg],
            "method": __doc__.strip().split("\n\n", 1)[1].replace("\n", " "), "data_note": C.SEED_NOTE}
