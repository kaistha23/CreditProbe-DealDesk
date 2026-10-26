"""P6 ECL Diagnostics Intelligence (PLAN_R9 C3): what moved ECL, input errors, CBUAE coverage, shocks.

All amounts SAR million. Reads the two ECL runs (prior 2026Q2, current 2026Q3) through `runs`; the current run equals
the books at their as-of. Deterministic: the same runs always give the same answer.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from backend.risk_intel import runs

PACK = {"pack": "P6 ECL Diagnostics Intelligence", "confidence": "High: arithmetic on the two ECL runs"}
STEPS = ("new_business", "repayments", "stage_transfers", "pd", "lgd", "macro", "overlays", "write_offs")
STEP_LABELS = {"new_business": "New business", "repayments": "Repayments and drawdowns",
               "stage_transfers": "Stage transfers", "pd": "PD (obligor-specific)", "lgd": "LGD",
               "macro": "Macro (sector-wide PD shift)", "overlays": "Overlays", "write_offs": "Write-offs"}
STEP_INFO = {
    "new_business": "ECL of exposures in the current run that were not in the prior run.",
    "repayments": "Exposures that left the book (not written off) plus the effect of EAD changes on continuing exposures at prior PD and LGD.",
    "stage_transfers": "The whole ECL change of continuing exposures whose stage changed.",
    "pd": "Same-stage exposures: the PD change net of the sector-wide shift, at current EAD and prior LGD.",
    "lgd": "Same-stage exposures: the LGD change at current EAD and current PD.",
    "macro": "Same-stage exposures: the sector's average PD change (the forward-looking macro shift).",
    "overlays": "Change in post-model overlays between the runs.",
    "write_offs": "ECL released on exposures written off between the runs.",
}


def _clean(v: Any) -> Any:
    if isinstance(v, (np.floating, float)):
        return None if not np.isfinite(v) else float(v)
    if isinstance(v, np.integer):
        return int(v)
    return v


def _records(df: pd.DataFrame) -> list[dict[str, Any]]:
    return [{k: _clean(v) for k, v in r.items()} for r in df.to_dict("records")]


def _pair(bk: str = "corporate") -> pd.DataFrame:
    cur = runs.ecl_run(runs.CURRENT, bk)
    pri = runs.ecl_run(runs.PRIOR, bk)
    keep = ["exposure_id", "obligor_id", "ead_sar_mn", "pd_12m_pct", "pd_lifetime_pct", "lgd_pct", "stage", "ecl_sar_mn",
            "overlay_sar_mn", "dpd_days", "limit_sar_mn"]
    keep_c = keep + [c for c in ("rating", "sector", "collateral_sar_mn") if c in cur.columns]
    keep_p = keep + [c for c in ("rating", "collateral_sar_mn") if c in pri.columns]
    j = cur[keep_c].merge(pri[keep_p], on="exposure_id", how="outer", suffixes=("", "_p"), indicator=True)
    return j


def _names(bk: str) -> dict[str, str]:
    from backend.spine.books import book
    b = book(bk)
    if bk != "corporate":
        return {}
    f = pd.read_parquet(b.path(b.customer_relation), columns=[b.customer_key, b.period_column, "borrower_name"],
                        filters=[(b.period_column, "=", b.as_of)])
    return dict(zip(f[b.customer_key], f["borrower_name"]))


def waterfall(bk: str = "corporate", top: int = 5) -> dict[str, Any]:
    j = _pair(bk)
    j["obligor_id"] = j["obligor_id"].fillna(j["obligor_id_p"])
    new = j["_merge"] == "left_only"
    gone = j["_merge"] == "right_only"
    both = j["_merge"] == "both"
    contrib = pd.DataFrame(0.0, index=j.index, columns=list(STEPS))
    contrib.loc[new, "new_business"] = j.loc[new, "ecl_sar_mn"]
    # Exposures that left: written off (prior Stage 3) or repaid.
    wo = gone & (j["stage_p"] == 3)
    contrib.loc[wo, "write_offs"] = -j.loc[wo, "ecl_sar_mn_p"]
    contrib.loc[gone & ~wo, "repayments"] = -j.loc[gone & ~wo, "ecl_sar_mn_p"]
    b = j[both].copy()
    moved = b["stage"] != b["stage_p"]
    contrib.loc[b.index[moved], "stage_transfers"] = (b.loc[moved, "ecl_sar_mn"] - b.loc[moved, "ecl_sar_mn_p"]).values
    s = b[~moved].copy()
    # Effective PD so that ECL = EAD x PDe x LGD exactly in each run; the identity makes the steps add up.
    lg0 = (s["lgd_pct_p"] / 100).clip(lower=1e-9)
    lg1 = (s["lgd_pct"] / 100).clip(lower=1e-9)
    e0 = s["ead_sar_mn_p"].clip(lower=1e-12)
    e1 = s["ead_sar_mn"].clip(lower=1e-12)
    ov0 = s["overlay_sar_mn_p"].fillna(0)
    ov1 = s["overlay_sar_mn"].fillna(0)
    p0 = ((s["ecl_sar_mn_p"] - ov0) / (e0 * lg0)).where(s["ead_sar_mn_p"] > 0, 0.0)
    p1 = ((s["ecl_sar_mn"] - ov1) / (e1 * lg1)).where(s["ead_sar_mn"] > 0, 0.0)
    ead_eff = (s["ead_sar_mn"] - s["ead_sar_mn_p"]) * p0 * lg0
    dp = p1 - p0
    if "sector" in s.columns:
        w = s["ead_sar_mn"].clip(lower=0)
        sect = (dp * w).groupby(s["sector"]).sum() / w.groupby(s["sector"]).sum().replace(0, np.nan)
        dp_macro = s["sector"].map(sect).fillna(0.0)
    else:
        dp_macro = pd.Series(float((dp * s["ead_sar_mn"]).sum() / max(s["ead_sar_mn"].sum(), 1e-9)), index=s.index)
    macro_eff = s["ead_sar_mn"] * dp_macro * lg0
    pd_eff = s["ead_sar_mn"] * (dp - dp_macro) * lg0
    lgd_eff = s["ead_sar_mn"] * p1 * (lg1 - lg0)
    contrib.loc[s.index, "repayments"] = ead_eff.values
    contrib.loc[s.index, "pd"] = pd_eff.values
    contrib.loc[s.index, "macro"] = macro_eff.values
    contrib.loc[s.index, "lgd"] = lgd_eff.values
    contrib.loc[s.index, "overlays"] = (ov1 - ov0).values
    opening = float(j["ecl_sar_mn_p"].fillna(0).sum())
    closing = float(j["ecl_sar_mn"].fillna(0).sum())
    resid = closing - opening - float(contrib.values.sum())
    names = _names(bk)
    bars = []
    for st in STEPS:
        c = contrib[st]
        by_ob = c.groupby(j["obligor_id"]).sum()
        lead = by_ob.reindex(by_ob.abs().sort_values(ascending=False).index).head(top)
        bars.append({"key": st, "label": STEP_LABELS[st], "info": STEP_INFO[st], "value": float(c.sum()),
                     "exposures": int((c.abs() > 1e-9).sum()),
                     "top_clients": [{"obligor_id": k, "name": names.get(k, k), "value": float(v)} for k, v in lead.items()
                                     if abs(v) > 1e-9]})
    return {"book": bk, "prior_run": runs.PRIOR, "current_run": runs.CURRENT, "opening": opening, "closing": closing,
            "change": closing - opening, "bars": bars, "residual": resid, "source": runs.source(),
            "method": ("Exposures matched by ID across the two runs. New and departed exposures first; continuing "
                       "exposures that changed stage carry their whole change as a stage transfer; same-stage "
                       "exposures are split EAD → PD → LGD with ECL = EAD × PD × LGD + overlay, PD split into the "
                       "sector-wide shift (macro) and the obligor-specific remainder."),
            "powered_by": {**PACK, "rule_id": "P6-MOV-01", "article": "CBUAE CRM Art. 9 (provisioning governance)"}}


# ------------------------------------------------------------------ input anomaly check

RULES = (
    ("pd_no_rating", "PD changed with no rating change", "PD 12m at least doubled (and rose 0.1pp or more) while the "
     "rating and stage are unchanged.", True),
    ("lgd_no_collateral", "LGD changed with no collateral change", "LGD moved by 10pp or more while the collateral "
     "value moved by less than 10%.", True),
    ("ead_over_limit", "EAD above the limit", "EAD exceeds the approved limit by more than 5% (a limit-feed error; "
     "ECL is unaffected, so it does not on its own require a rerun).", False),
    ("stage_vs_dpd", "Stage inconsistent with days past due", "90+ DPD not in Stage 3 (Art 6.4) or 30+ DPD in "
     "Stage 1 (Art 7.8).", True),
    ("missing_collateral", "Missing collateral value", "A facility that held collateral in the prior run has no "
     "collateral value in the current run while its LGD is unchanged.", True),
    ("stage3_zero_ecl", "Stage 3 with zero ECL", "A Stage 3 exposure with EAD above zero carries no ECL, in either run "
     "(a zero in the prior run overstates the movement).", True),
)


def anomalies(bk: str = "corporate") -> dict[str, Any]:
    j = _pair(bk)
    b = j[j["_merge"] != "right_only"].copy()
    both = b["_merge"] == "both"
    hits: dict[str, pd.Series] = {}
    p0, p1 = b["pd_12m_pct_p"], b["pd_12m_pct"]
    # Retail carries no rating: the rule applies to rated (corporate) exposures only.
    same_rating = (b["rating"] == b["rating_p"]) if "rating" in b.columns and "rating_p" in b.columns else pd.Series(False, index=b.index)
    ratio = (p1 / p0.where(p0 > 0)).fillna(1.0)
    hits["pd_no_rating"] = both & same_rating & (b["stage"] == b["stage_p"]) & (b["stage"] < 3) & \
        ((p1 - p0) >= 0.1) & (ratio >= 2.0)
    if "collateral_sar_mn" in b.columns and "collateral_sar_mn_p" in b.columns:
        c0, c1 = b["collateral_sar_mn_p"], b["collateral_sar_mn"]
        same_col = (c1 - c0).abs() <= 0.10 * c0.abs().clip(lower=1e-9)
        hits["lgd_no_collateral"] = both & same_col & ((b["lgd_pct"] - b["lgd_pct_p"]).abs() >= 10)
        hits["missing_collateral"] = both & (c0 > 0) & (c1.isna() | (c1 <= 0)) & ((b["lgd_pct"] - b["lgd_pct_p"]).abs() < 0.5)
    else:
        hits["lgd_no_collateral"] = pd.Series(False, index=b.index)
        hits["missing_collateral"] = pd.Series(False, index=b.index)
    hits["ead_over_limit"] = (b["limit_sar_mn"] > 0) & (b["ead_sar_mn"] > 1.05 * b["limit_sar_mn"])
    hits["stage_vs_dpd"] = ((b["dpd_days"] > 90) & (b["stage"] < 3)) | ((b["dpd_days"] > 30) & (b["stage"] == 1))
    hits["stage3_zero_ecl"] = ((b["stage"] == 3) & (b["ead_sar_mn"] > 0) & (b["ecl_sar_mn"].fillna(0) <= 0)) | \
        (both & (b["stage_p"] == 3) & (b["ead_sar_mn_p"] > 0) & (b["ecl_sar_mn_p"].fillna(0) <= 0))
    total_ecl = float(b["ecl_sar_mn"].sum())
    names = _names(bk)
    checks, rows = [], []
    planted = {str(a.get("exposure_id")): a for a in runs.anomalies() if str(a.get("book", bk)) == bk}
    rerun_rules = 0
    found_total = 0
    for key, label, rule, input_error in RULES:
        m = hits[key].fillna(False)
        sub = b[m]
        # ECL at stake: Stage 3 zero ECL -> EAD x LGD; others -> the ECL of the exposure.
        stake = float((sub["ead_sar_mn"] * sub["lgd_pct"] / 100).sum()) if key == "stage3_zero_ecl" else float(sub["ecl_sar_mn"].sum())
        checks.append({"key": key, "label": label, "rule": rule, "count": int(m.sum()), "input_error": input_error,
                       "ecl_at_stake": stake, "ead": float(sub["ead_sar_mn"].sum())})
        if input_error and m.sum():
            rerun_rules += 1
        sub = sub.assign(_pl=sub["exposure_id"].astype(str).isin(planted)).sort_values(["_pl", "ecl_sar_mn"], ascending=False)
        found_planted_all = int(sub["_pl"].sum())
        found_total += found_planted_all
        for r in sub.head(25).to_dict("records"):
            rows.append({"check": key, "label": label, "exposure_id": r["exposure_id"], "obligor_id": r["obligor_id"],
                         "name": names.get(r["obligor_id"], r["obligor_id"]), "stage": _clean(r["stage"]),
                         "dpd_days": _clean(r["dpd_days"]), "ead": _clean(r["ead_sar_mn"]), "ecl": _clean(r["ecl_sar_mn"]),
                         "prior": _clean(r.get("pd_12m_pct_p") if key == "pd_no_rating" else r.get("lgd_pct_p") if key == "lgd_no_collateral" else r.get("collateral_sar_mn_p") if key == "missing_collateral" else r.get("limit_sar_mn") if key == "ead_over_limit" else None),
                         "current": _clean(r.get("pd_12m_pct") if key == "pd_no_rating" else r.get("lgd_pct") if key == "lgd_no_collateral" else r.get("collateral_sar_mn") if key == "missing_collateral" else r.get("ead_sar_mn") if key == "ead_over_limit" else None),
                         "field": {"pd_no_rating": "PD 12m %", "lgd_no_collateral": "LGD %", "missing_collateral": "Collateral, SAR m",
                                   "ead_over_limit": "Limit → EAD, SAR m"}.get(key, ""),
                         "planted": str(r["exposure_id"]) in planted})
    input_errors = sum(c["count"] for c in checks if c["input_error"])
    stake = sum(c["ecl_at_stake"] for c in checks if c["input_error"])
    material = (input_errors >= 3 or stake >= 0.001 * max(total_ecl, 1e-9)
                or any(c["key"] == "stage3_zero_ecl" and c["count"] for c in checks))
    verdict = "Rerun recommended" if input_errors and material else "Rerun not required"
    found_planted = found_total
    share = 100 * stake / max(total_ecl, 1e-9)
    why = (f"{input_errors} input errors across {rerun_rules} checks put {'under SAR 0.1m' if stake < 0.05 else f'SAR {stake:,.1f}m'} of ECL in question "
           f"({'under 0.01' if share < 0.01 else f'{share:.2f}'}% of the run's ECL). The run used inputs that contradict their own "
           "drivers; correct them and rerun the ECL engine before sign-off."
           if verdict == "Rerun recommended" else
           "No material input error: the data-quality exceptions do not change ECL and are fixed at source.")
    return {"book": bk, "run": runs.CURRENT, "prior_run": runs.PRIOR, "verdict": verdict, "why": why,
            "input_errors": input_errors, "data_quality": sum(c["count"] for c in checks if not c["input_error"]),
            "planted_listed": len(planted), "planted_found": found_planted, "checks": checks, "rows": rows,
            "total_ecl": total_ecl, "source": runs.source(),
            "powered_by": {**PACK, "rule_id": "P6-ERR-02", "article": "CBUAE CRM Art. 9.21 (robust, documented methodologies)"}}


# ------------------------------------------------------------------ CBUAE coverage

def coverage(bk: str = "corporate") -> dict[str, Any]:
    cur = runs.ecl_run(runs.CURRENT, bk)
    rw = runs.crwa(bk)
    crwa = float(rw["crwa_sar_mn"].sum())
    s12 = float(cur.loc[cur["stage"] < 3, "ecl_sar_mn"].sum())
    req = 0.015 * crwa
    floors: dict[str, Any] = {"breaches": 0, "shortfall": 0.0, "stage3_ecl": float(cur.loc[cur["stage"] == 3, "ecl_sar_mn"].sum()),
                              "stage3_ead": float(cur.loc[cur["stage"] == 3, "ead_sar_mn"].sum()), "top": []}
    try:
        from backend.regulatory import crm_checks as k
        cid = "CRM-9.23" if bk == "corporate" else "CRM-9.24"
        br = [x for x in k.run_book(bk) if getattr(x, "check_id", None) == cid or (isinstance(x, dict) and x.get("check_id") == cid)]
        recs = [x if isinstance(x, dict) else x.__dict__ for x in br]
        floors["breaches"] = len(recs)
        floors["shortfall"] = float(sum((r.get("required") or 0) - (r.get("measured") or 0) for r in recs))
        floors["top"] = sorted([{"entity_id": r.get("entity_id"), "borrower_id": r.get("borrower_id"),
                                 "ecl": r.get("measured"), "floor": r.get("required"),
                                 "shortfall": (r.get("required") or 0) - (r.get("measured") or 0)} for r in recs],
                               key=lambda r: -r["shortfall"])[:10]
        floors["article"] = "CBUAE CRM Art. 9.23" if bk == "corporate" else "CBUAE CRM Art. 9.24"
    except Exception as e:  # noqa: BLE001
        floors["error"] = f"Stage 3 floor check unavailable: {type(e).__name__}"
    return {"book": bk, "run": runs.CURRENT, "crwa": crwa, "stage12_ecl": s12, "required_9_21": req,
            "coverage_pct_of_crwa": 100 * s12 / crwa if crwa else None, "shortfall_9_21": max(0.0, req - s12),
            "meets_9_21": s12 >= req, "stage3": floors,
            "total_shortfall": max(0.0, req - s12) + floors["shortfall"],
            "crwa_source": "col_crwa (Data Domains)" if runs._a() is not None else
            "EAD × standardised corporate risk weight by rating (20/50/100/150%), pending the collateral domain",
            "powered_by": {**PACK, "rule_id": "P6-FLR-03", "article": "CBUAE CRM Art. 9.21, 9.23"}}


# ------------------------------------------------------------------ shocks

def shocks(bk: str = "corporate", pd_pct: float = 20.0, lgd_pp: float = 5.0, macro_pct: float = 0.0,
           top: int = 10) -> dict[str, Any]:
    """PD x (1 + pd% + macro% x sector beta), LGD + pp (capped at 100%), ECL rescaled; Stage 3 PD is held at 100%."""
    cur = runs.ecl_run(runs.CURRENT, bk).copy()
    lgd0 = (cur["lgd_pct"] / 100).clip(lower=1e-9)
    lgd1 = (cur["lgd_pct"] / 100 + lgd_pp / 100).clip(upper=1.0, lower=0.0)
    beta = pd.Series(1.0, index=cur.index)
    if "sector" in cur.columns:
        hi = {"Construction": 1.6, "Real Estate": 1.5, "Hospitality": 1.4, "Retail Trade": 1.2, "Transport": 1.2}
        beta = cur["sector"].map(hi).fillna(1.0)
    pf = (1 + pd_pct / 100 + macro_pct / 100 * beta).clip(lower=0)
    pf = pf.where(cur["stage"] < 3, 1.0)
    ead = cur["ead_sar_mn"]
    new = (cur["ecl_sar_mn"] * pf * (lgd1 / lgd0)).clip(upper=ead * lgd1).where(ead > 0, cur["ecl_sar_mn"])
    new = new.where(new >= cur["ecl_sar_mn"] if (pd_pct >= 0 and lgd_pp >= 0 and macro_pct >= 0) else True, cur["ecl_sar_mn"])
    cur["shocked"] = new
    cur["delta"] = new - cur["ecl_sar_mn"]
    names = _names(bk)
    g = cur.groupby("obligor_id")[["ecl_sar_mn", "shocked", "delta", "ead_sar_mn"]].sum().sort_values("delta", ascending=False).head(top)
    by_stage = cur.groupby("stage")[["ecl_sar_mn", "shocked"]].sum().reset_index()
    by_sector = (cur.groupby("sector")[["ecl_sar_mn", "shocked", "delta"]].sum().sort_values("delta", ascending=False).reset_index()
                 if "sector" in cur.columns else pd.DataFrame())
    return {"book": bk, "run": runs.CURRENT, "shock": {"pd_pct": pd_pct, "lgd_pp": lgd_pp, "macro_pct": macro_pct},
            "base_ecl": float(cur["ecl_sar_mn"].sum()), "shocked_ecl": float(new.sum()), "delta": float(cur["delta"].sum()),
            "by_stage": _records(by_stage), "by_sector": _records(by_sector.head(12)) if len(by_sector) else [],
            "top_movers": [{"obligor_id": k, "name": names.get(k, k), **{c: float(v) for c, v in r.items()}} for k, r in g.iterrows()],
            "method": "PD × (1 + PD shock + macro shock × sector beta), LGD + shock (cap 100%), ECL capped at EAD × LGD; "
                      "Stage 3 PD stays at 100%.",
            "powered_by": {**PACK, "rule_id": "P6-MOV-01", "article": "CBUAE CRM Art. 9 (forward-looking information)"}}
