"""R13 IE item 21: RM track record.

By RM (or branch): proposal quality, review queries, conditions met, promises delivered, and how their approved
decisions performed afterwards, risk-adjusted. Risk adjustment: observed defaults in the four quarters after each
approval against expected defaults (sum of the 12-month PD at the decision, scaled so the whole history's O/E is 1), O/E with a Poisson interval, so an RM
who books weaker borrowers is judged against the risk taken. Composite score 0-100: the percentile rank of each
measure across RMs with enough history (quality 25%, conditions met 20%, promises delivered 15%, fewer queries 10%,
O/E 30%). Fewer than MIN_N approved decisions is flagged thin and left out of the ranking.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from . import common as C

MIN_N = 15
WEIGHTS = {"quality": 0.25, "conditions": 0.20, "promises": 0.15, "queries": 0.10, "oe": 0.30}
REL = ["gov_decision", "corp_facility_quarter"]


def _table(group: str) -> pd.DataFrame:
    d = C.decisions_with_outcomes()
    if d.empty or "default_12m" not in d:
        return pd.DataFrame()
    key = "rm_id" if group == "rm" else "branch_id"
    name = "rm_name" if group == "rm" else "branch_name"
    a = d[d["decision"] != "declined"]
    g_all = d.groupby(key)
    g = a.groupby(key)
    t = pd.DataFrame({
        "name": g_all[name].agg(lambda s: s.mode().iat[0]),
        "decisions": g_all.size(),
        "declined": g_all["decision"].agg(lambda s: int((s == "declined").sum())),
        "quality": g_all["proposal_quality_score"].mean(),
        "queries": g_all["review_queries"].mean(),
        "approved": g.size(),
        "cond_set": g["conditions_set"].sum(), "cond_met": g["conditions_met"].sum(),
        "prom_made": g["promises_made"].sum(), "prom_dlv": g["promises_delivered"].sum(),
        "defaults": g["default_12m"].sum(), "expected": g["pd_at_decision"].sum(),
        "migrated": g["migrated_12m"].sum(), "limit_sar_mn": g["limit_sar_mn"].sum(),
    }).fillna(0)
    # calibrate: the through-the-cycle PD understates the 2023-24 downturn, so scale expected defaults until the
    # whole history's O/E is 1; an RM's O/E then reads against the bank, at the risk that RM took
    cal = float(a["default_12m"].sum()) / float(a["pd_at_decision"].sum()) if a["pd_at_decision"].sum() else 1.0
    t["expected"] = t["expected"] * cal
    t.attrs["calibration"] = cal
    if group == "rm":
        t["branch"] = d.groupby(key)["branch_name"].agg(lambda s: s.mode().iat[0])
    else:
        t["region"] = d.groupby(key)["region"].agg(lambda s: s.mode().iat[0])
    t["cond_rate"] = t["cond_met"] / t["cond_set"].where(t["cond_set"] > 0)
    t["prom_rate"] = t["prom_dlv"] / t["prom_made"].where(t["prom_made"] > 0)
    t["oe"] = t["defaults"] / t["expected"].where(t["expected"] > 0)
    t["thin"] = t["approved"] < MIN_N
    ok = ~t["thin"]
    pr = lambda s, asc=True: s[ok].rank(pct=True, ascending=asc)  # noqa: E731
    score = (WEIGHTS["quality"] * pr(t["quality"]) + WEIGHTS["conditions"] * pr(t["cond_rate"].fillna(t["cond_rate"].median()))
             + WEIGHTS["promises"] * pr(t["prom_rate"].fillna(t["prom_rate"].median()))
             + WEIGHTS["queries"] * pr(t["queries"], asc=False) + WEIGHTS["oe"] * pr(t["oe"].fillna(1.0), asc=False))
    t["score"] = (100 * score).round(1)
    return t.reset_index().rename(columns={key: "id"})


def _row(r: dict[str, Any], group: str) -> dict[str, Any]:
    lo, hi = C.poisson_ratio_ci(int(r["defaults"]), float(r["expected"]))
    filt = {"rm_id" if group == "rm" else "branch_id": r["id"]}
    cs, cm = int(r["cond_set"]), int(r["cond_met"])
    pm, pdl = int(r["prom_made"]), int(r["prom_dlv"])
    return {
        "id": r["id"], "name": r["name"], ("branch" if group == "rm" else "region"): r.get("branch", r.get("region")),
        "decisions": int(r["decisions"]), "approved": int(r["approved"]), "declined": int(r["declined"]),
        "limit_sar_mn": round(float(r["limit_sar_mn"]), 1),
        "quality": C.computed(r["quality"], "0-100", ["gov_decision"], int(r["decisions"]), "mean proposal quality score", filt),
        "queries_per_file": round(float(r["queries"]), 2),
        "conditions": C.rate(cm, cs) if cs else None,
        "promises": C.rate(pdl, pm) if pm else None,
        "defaults": int(r["defaults"]), "expected_defaults": round(float(r["expected"]), 2),
        "oe": None if pd.isna(r["oe"]) else round(float(r["oe"]), 2), "oe_ci": [round(lo, 2), round(hi, 2)],
        "migrated": int(r["migrated"]),
        "score": None if r["thin"] else float(r["score"]), "thin": bool(r["thin"]),
        "flag": ("thin history" if r["thin"] else
                 "worse than risk taken" if lo > 1.0 else "better than risk taken" if hi < 1.0 and r["defaults"] >= 0 else ""),
    }


def write(rows: list[dict[str, Any]], group: str) -> list[str]:
    ranked = [r for r in rows if r["score"] is not None]
    who = "RMs" if group == "rm" else "branches"
    if not ranked:
        return [f"No {who} with at least {MIN_N} approved decisions."]
    ranked.sort(key=lambda r: -r["score"])
    top, low = ranked[0], ranked[-1]
    lines = [f"{len(ranked)} {who} have at least {MIN_N} approved decisions; {len(rows) - len(ranked)} more are too thin to rank."]
    def desc(r: dict[str, Any]) -> str:
        c = f"{r['conditions']['pct']:.0f}% of conditions met" if r["conditions"] else "no conditions set"
        return (f"{r['name']} (score {r['score']:.0f}): quality {r['quality']['value']:.0f}, {c}, defaults "
                f"{r['oe']:.2f}× expected over {r['approved']} approvals")
    lines.append("Strongest: " + desc(top) + ".")
    lines.append("Weakest: " + desc(low) + ".")
    worse = [r for r in ranked if r["flag"] == "worse than risk taken"]
    if worse:
        lines.append(f"{len(worse)} {who} default more than their risk explains (O/E interval above 1): "
                     + ", ".join(r["name"] for r in worse[:4]) + ".")
    lines.append("Risk-adjusted: defaults are set against the PD each borrower carried at approval, scaled to the bank's own "
                 "default experience over the history.")
    return lines[:5]


def live_files(rm: str | None = None) -> list[dict[str, Any]]:
    """Today's Deal Desk files by RM: conditions and promises on the current deals (dd_deal, dd_condition, dd_promise)."""
    deals = C.frame("dd_deal", ["proposal_id", "rm", "branch", "status"])
    if deals.empty:
        return []
    cond = C.frame("dd_condition", ["condition_id", "proposal_id", "status"])
    prom = C.frame("dd_promise", ["promise_id", "proposal_id", "status"])
    fnd = C.frame("dd_review_finding", ["finding_id", "proposal_id", "severity"])
    out = []
    for name, g in deals.groupby("rm"):
        if rm and name != rm:
            continue
        ids = set(g["proposal_id"])
        c = cond[cond["proposal_id"].isin(ids)]
        p = prom[prom["proposal_id"].isin(ids)]
        f = fnd[fnd["proposal_id"].isin(ids)]
        out.append({"rm": name, "files": len(ids), "conditions": int(len(c)),
                    "conditions_met": int((c["status"] == "met").sum()),
                    "conditions_not_complied": int(c["status"].isin(["not_complied", "breached"]).sum()),
                    "promises": int(len(p)), "promises_met": int((p["status"] == "met").sum()),
                    "findings_high": int(f["severity"].isin(["critical", "high"]).sum()),
                    "source": {"relations": ["dd_deal", "dd_condition", "dd_promise", "dd_review_finding"], "filter": {"rm": name}}})
    return sorted(out, key=lambda r: -r["files"])


def analyse(group: str = "rm", limit: int = 100) -> dict[str, Any]:
    group = "branch" if group == "branch" else "rm"
    t = _table(group)
    if t.empty:
        return {"available": False, "lines": ["No decision history in Data Domains (governance domain is empty)."],
                "data_note": C.SEED_NOTE}
    cal = t.attrs.get("calibration", 1.0)
    rows = [_row(r, group) for r in t.to_dict("records")]
    rows.sort(key=lambda r: (r["score"] is None, -(r["score"] or 0)))
    return {"available": True, "kind": "rm_track_record", "group": group, "as_of": C.AS_OF_QUARTER,
            "lines": write(rows, group), "rows": rows[:limit], "total": len(rows), "min_n": MIN_N, "weights": WEIGHTS, "pd_calibration": round(cal, 3),
            "live": live_files() if group == "rm" else [],
            "method": __doc__.strip().split("\n\n", 1)[1].replace("\n", " "), "data_note": C.SEED_NOTE}
