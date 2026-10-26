"""R13 IE: seed the fictional credit-decision history into Data Domains (governance domain).

Deterministic: every random draw comes from a generator keyed on the decision id, so re-running gives the same rows.
What is read from the book (real demo data): borrower, sector, rating, PD, DSCR, leverage and current ratio at the
decision quarter (corp_borrower_quarter), limits (corp_facility_quarter), RM and branch (branch_corporate_quarter) and
the DoA table (dd_parameter doa). What is seeded: which borrower-quarters had a decision, the approval steps and their
timing, level outcomes, non-financial exceptions, proposal quality, queries, conditions and promises.
Outcomes are never written: the engines read them from the book.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import random
from typing import Any

import pandas as pd

from backend.dealdesk.data import publish
from backend.dealdesk.data.store import dd_frame
from backend.v5common.ratings import rank as rrank

from . import common as C

FIRST_Q, LAST_Q = "2021Q4", "2025Q2"  # every decision has four book quarters after it
AT = "2026-10-19T10:00:00Z"
POLICY = "POL-CR-01"
LEVERAGE_TOLERANCE = 2.5  # see BASIS: book leverage runs above clause 4.3 for most obligors

BASIS = ("Seeded: decision, steps, timings, quality, queries, conditions, promises and non-financial exceptions. "
         "From the book: borrower, rating, PD, DSCR, leverage, current ratio, limits, RM and branch at the decision quarter.")

MITIGANT = {
    "dscr": "Cash sweep and DSRA of 6 months", "leverage": "Deleveraging covenant within 24 months",
    "current_ratio": "Working-capital line capped at 80% of eligible receivables", "rating": "Full cash collateral on new money",
    "collateral_cover": "Additional corporate guarantee from the parent", "pricing": "Ancillary business commitment",
    "late_financials": "Audited statements as condition subsequent within 60 days",
    "perfection_deferral": "Security perfected within 60 days (clause 7.5)",
}
CLAUSE = {"dscr": "4.2", "leverage": "4.3", "current_ratio": "4.4", "rating": "4.1", "collateral_cover": "7.6",
          "pricing": "9.1", "late_financials": "3.3", "perfection_deferral": "7.5"}
SEEDED_P = {"collateral_cover": 0.05, "pricing": 0.07, "late_financials": 0.06, "perfection_deferral": 0.04}
LEVEL_DAYS = {0: 4.0, 1: 2.0, 2: 3.5, 3: 6.0, 4: 10.0, 5: 18.0}       # mean calendar days at each level
LEVEL_CHANGE = {1: 0.09, 2: 0.07, 3: 0.015, 4: 0.12, 5: 0.05}          # chance the level amends terms
TRADING = ("Construction", "Retail Trade", "Wholesale Trade")


def _rng(key: str) -> random.Random:
    return random.Random(int(hashlib.sha256(key.encode()).hexdigest()[:16], 16))


def doa_levels() -> list[dict[str, Any]]:
    p = dd_frame("dd_parameter", table_name="doa")
    lv: dict[str, dict[str, Any]] = {}
    for r in p.itertuples(index=False):
        if "." not in str(r.param_key):
            continue
        name, k = str(r.param_key).rsplit(".", 1)
        lv.setdefault(name, {"level": name})
        lv[name][k] = r.value_num if pd.notna(r.value_num) else r.value_text
    out = [{"level": v["level"], "rank": int(v["rank"]), "max_exposure": float(v["max_exposure"]),
            "max_soft": int(float(v["max_soft"])), "min_rating": str(v["min_rating"])} for v in lv.values()]
    return sorted(out, key=lambda x: x["rank"])


def required_rank(levels: list[dict[str, Any]], limit: float, rating: str, n_exc: int) -> int:
    for lv in levels:
        if limit <= lv["max_exposure"] and rrank(rating) <= rrank(lv["min_rating"]) and n_exc <= lv["max_soft"]:
            return lv["rank"]
    return levels[-1]["rank"]


def _rm_traits(rm_id: str) -> dict[str, float]:
    g = _rng("rm:" + rm_id)
    return {"quality": g.uniform(58, 90), "queries": g.uniform(0.6, 3.2), "cond_met": g.uniform(0.62, 0.97),
            "promise": g.uniform(0.35, 0.95), "decline": g.uniform(0.02, 0.07)}


def _date(q: str, g: random.Random) -> dt.date:
    y, n = int(q[:4]), int(q[-1])
    start = dt.date(y, 3 * (n - 1) + 1, 1)
    return start + dt.timedelta(days=g.randint(5, 60))


def build() -> dict[str, pd.DataFrame]:
    levels = doa_levels()
    lname = {lv["rank"]: lv["level"] for lv in levels}
    b = C.borrowers()
    f = C.facilities()
    br = dd_frame("branch_corporate_quarter", columns=["borrower_id", "reporting_quarter", "rm_id", "rm_name",
                                                       "branch_id", "branch_name", "region"])
    lim = f.groupby(["borrower_id", "reporting_quarter"]).agg(limit=("limit_sar_mn", "sum"),
                                                                dflt=("default_flag", "max")).reset_index()
    qi0, qi1 = C.q_index(FIRST_Q), C.q_index(LAST_Q)
    b = b[b["reporting_quarter"].map(C.q_index).between(qi0, qi1)]
    m = b.merge(lim, on=["borrower_id", "reporting_quarter"]).merge(br, on=["borrower_id", "reporting_quarter"], how="left")
    m = m[(m["dflt"] == 0) & m["rm_id"].notna()]
    # one annual review per borrower, plus a second decision a year later for about a third of them
    picks = []
    for bid, g in m.groupby("borrower_id"):
        qs = sorted(g["reporting_quarter"].unique(), key=C.q_index)
        r = _rng("pick:" + bid)
        q = qs[r.randrange(len(qs))]
        picks.append((bid, q, "renewal" if r.random() < 0.7 else "increase"))
        q2 = C.q_add(q, 4)
        if r.random() < 0.35 and q2 in set(qs):
            picks.append((bid, q2, "renewal"))
    idx = m.set_index(["borrower_id", "reporting_quarter"])
    dec, stp, exc = [], [], []
    for i, (bid, q, case) in enumerate(sorted(picks, key=lambda t: (C.q_index(t[1]), t[0])), start=1):
        row = idx.loc[(bid, q)]
        did = f"GD-{i:05d}"
        g = _rng(did)
        tr = _rm_traits(str(row["rm_id"]))
        # exceptions: financial ones measured on the book, others seeded
        ex: list[tuple[str, float | None, float | None, str, str]] = []
        if pd.notna(row["dscr_x"]) and row["dscr_x"] < 1.25:
            ex.append(("dscr", float(row["dscr_x"]), 1.25, "x", "book"))
        if pd.notna(row["leverage_x"]) and row["leverage_x"] > 3.5 * LEVERAGE_TOLERANCE:
            ex.append(("leverage", float(row["leverage_x"]), 3.5, "x", "book"))
        if row["sector"] in TRADING and pd.notna(row["current_ratio_x"]) and row["current_ratio_x"] < 1.10:
            ex.append(("current_ratio", float(row["current_ratio_x"]), 1.10, "x", "book"))
        if rrank(row["rating_current"]) > rrank("B-"):
            ex.append(("rating", float(rrank(row["rating_current"])), float(rrank("B-")), "rating rank", "book"))
        for t, p in SEEDED_P.items():
            if g.random() < p:
                ex.append((t, None, None, "", "seeded"))
        req = required_rank(levels, float(row["limit"]), str(row["rating_current"]), len(ex))
        # steps: credit review (rank 0) then every level up to the required one
        day = _date(q, g)
        submitted = day
        decision, changed_any = "approved", False
        rec = "approve"
        for seq, rk in enumerate([0] + list(range(1, req + 1)), start=1):
            days = round(max(0.5, g.gammavariate(2.0, LEVEL_DAYS[rk] / 2.0) * (1.25 if ex and rk >= 3 else 1.0)), 1)
            out = "concur"
            pdec = tr["decline"] * (1 + 6 * float(row["pd_ttc_12m"] or 0)) * (
                0.3 if rrank(row["rating_current"]) <= rrank("BB-") else 1.0) if rk == req else 0.0
            if rk == 0:
                q_n = max(0, round(g.gauss(tr["queries"] * (1.3 if ex else 1.0), 0.8)))
                out = "recommend_decline" if g.random() < tr["decline"] * 0.6 else "concur"
                rec = "decline" if out == "recommend_decline" else "approve"
                out = "concur"
            else:
                q_n = 1 if g.random() < 0.15 else 0
                if rk == req and g.random() < pdec:
                    out = "decline" if rec == "approve" else "concur"
                elif rec == "decline" and rk == req:
                    out = "overturn" if g.random() < 0.55 else "decline"
                elif g.random() < LEVEL_CHANGE.get(rk, 0.05) * (1.6 if ex and rk == req else 1.0) * (
                        0.4 if rk == req and rrank(row["rating_current"]) <= rrank("BB-") else 1.0):
                    out = "amend"
            changed = out in ("amend", "decline", "overturn")
            changed_any |= changed
            end = day + dt.timedelta(days=days)
            stp.append({"step_id": f"{did}-S{seq}", "decision_id": did, "seq": seq, "level_rank": rk,
                        "level_name": "Credit Risk review" if rk == 0 else lname[rk], "received_on": day.isoformat(),
                        "decided_on": end.isoformat(), "days": days, "input": rec, "output": out,
                        "changed_flag": int(changed), "queries_raised": int(q_n if rk == 0 else q_n)})
            if rk == req:
                if out == "decline" or (rec == "decline" and out != "overturn"):
                    decision = "declined"
            day = end
        n_cond = 0 if decision == "declined" else g.randint(0, 2) + (2 if ex else 0) + (1 if changed_any else 0)
        met = sum(g.random() < tr["cond_met"] for _ in range(n_cond))
        n_prom = 0 if decision == "declined" else (1 if g.random() < 0.45 else 0) + (1 if g.random() < 0.15 else 0)
        dlv = sum(g.random() < tr["promise"] for _ in range(n_prom))
        qual = max(20.0, min(99.0, g.gauss(tr["quality"], 7.0) - 3 * len(ex)))
        if decision != "declined" and n_cond:
            decision = "approved_with_conditions"
        dec.append({
            "decision_id": did, "borrower_id": bid, "borrower_name": row["borrower_name"], "decision_quarter": q,
            "decided_on": day.isoformat(), "case_type": case, "sector": row["sector"], "rm_id": row["rm_id"],
            "rm_name": row["rm_name"], "branch_id": row["branch_id"], "branch_name": row["branch_name"],
            "region": row["region"], "limit_sar_mn": round(float(row["limit"]), 3), "rating_at_decision": row["rating_current"],
            "pd_at_decision": float(row["pd_ttc_12m"]), "dscr_at_decision": float(row["dscr_x"]),
            "leverage_at_decision": float(row["leverage_x"]), "required_level_rank": req, "required_level": lname[req],
            "decision": decision, "exception_count": len(ex) if decision != "declined" else 0,
            "exception_types": json.dumps([e[0] for e in ex] if decision != "declined" else []),
            "proposal_quality_score": round(qual, 1), "review_queries": int(stp[-(req + 1)]["queries_raised"]),
            "conditions_set": n_cond, "conditions_met": met, "conditions_breached": n_cond - met,
            "promises_made": n_prom, "promises_delivered": dlv, "turnaround_days": float((day - submitted).days),
            "seed_basis": BASIS})
        if decision != "declined":
            for j, (t, meas, thr, unit, basis) in enumerate(ex, start=1):
                exc.append({"exception_id": f"{did}-X{j}", "decision_id": did, "borrower_id": bid, "decision_quarter": q,
                            "exception_type": t, "policy_id": POLICY, "clause": CLAUSE[t], "measured": meas,
                            "threshold": thr, "unit": unit, "basis": basis, "approved_by_level": lname[req],
                            "mitigant": MITIGANT[t]})
    return {"gov_decision": pd.DataFrame(dec), "gov_approval_step": pd.DataFrame(stp),
            "gov_policy_exception": pd.DataFrame(exc)}


def seed() -> dict[str, Any]:
    out = {}
    for rel, df in build().items():
        out[rel] = publish(rel, df, mode="replace", actor="IE seed (fictional history)", at=AT)
    C._frame.cache_clear()
    C._outcomes.cache_clear()
    return out
