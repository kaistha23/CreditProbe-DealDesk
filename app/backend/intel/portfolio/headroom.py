"""Growth headroom map (R14 backlog #14): where the bank can still lend next quarter, by sector x rating band and by
connected group, within risk appetite, capital and concentration, with the hurdle each slice clears.

For each slice s (sector x rating bucket) the engine finds the largest new Stage 1 lending X_s (SAR m EAD) such that
every portfolio metric of the risk-appetite statement it moves stays within its level (appetite, trigger or limit):

    sector share        (S_sec + X) / (T + X)                   <= sector_policy, sector_appetite (RE, Construction)
    RE + construction   (S_rc + X) / (T + X)                    <= re_construction_share (RE and Construction only)
    rating bucket share (S_b + X) / (T + X)                     <= rating_bucket[b]
    sub-IG share        (S_subIG + X) / (T + X)                 <= sub_ig_share (BB, B, CCC-C only)
    sector HHI          sum_k ((S_k + X 1[k=sec]) / (T + X))^2  <= sector_hhi
    cost of risk        (EL_perf + X el_s) / (EAD_perf + X)     <= cost_of_risk_bps
    BU RWA budget       X rw_s                                  <= bu_rwa_budget.appetite_sar_mn
    BU EL budget        X el_s                                  <= bu_el_budget.appetite_sar_mn
    minimum rating      CCC-C: no new money (min_rating.new_to_bank B-)

el_s and rw_s are the slice's EAD-weighted performing 12-month EL rate (PD x LGD, corporate book) and CRWA risk weight
(collateral domain col_crwa, net of the slice's average mitigation). Each constraint is solved alone by bisection
(each is monotone or convex in X); the slice headroom is the smallest, and the constraint that gives it is binding.
A metric already beyond its level allows only lending that does not worsen it ("non-worsening"), and is flagged.
Slices are alternatives, not additive: lending in one slice uses the shared BU budgets and moves every share.

Hurdle: returns.hurdle (sector override) against the slice's current RAROC (Book drift engine, EAD-weighted median of
performing facilities) and the margin uplift the median facility needs to clear it (from the Book's dRAROC/dmargin).

Groups: connected group EAD against group_connected (SAR) and group_large_exposure (% of Tier 1) at the same level.
"""
from __future__ import annotations

import functools
from typing import Any

import numpy as np
import pandas as pd

from backend.intel.portfolio import common as C

LEVELS = ("appetite", "trigger", "limit")
X_MAX = 50_000.0


def _level(row: dict[str, Any], level: str, key: str | None = None) -> float | None:
    if key is not None:
        tab = row.get({"appetite": "appetites", "trigger": "triggers", "limit": "limits"}[level], {})
        v = tab.get(key)
        return None if v is None else float(v)
    if level == "limit":
        v = row.get("limit")
    else:
        v = row.get(level)
    return None if v is None else float(v)


def _max_x(metric, cap: float) -> tuple[float, bool]:
    """Largest X in [0, X_MAX] with metric(X) <= cap; if metric(0) > cap, the largest X that does not worsen it."""
    m0 = metric(0.0)
    already = m0 > cap + 1e-12
    c = m0 if already else cap
    if metric(X_MAX) <= c + 1e-12:
        return X_MAX, already
    lo, hi = 0.0, X_MAX
    if metric(1e-6) > c + 1e-12:
        return 0.0, already
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if metric(mid) <= c + 1e-12:
            lo = mid
        else:
            hi = mid
    return lo, already


@functools.lru_cache(maxsize=1)
def _book_raroc() -> pd.DataFrame | None:
    """The Book's RAROC now per facility (backend/dealdesk/book): None if the Book cannot be built here."""
    try:
        from backend.dealdesk.book import core
        f, _ = core.frame()
        f = f[(f["source"] == "book") & (~f["defaulted"].astype(bool))]
        return f[["facility_id", "raroc_now", "slope_margin", "orig_margin_pct", "ead_sar_mn"]].copy()
    except Exception:  # noqa: BLE001 - the map still answers on appetite and capital
        return None


def _wmedian(v: pd.Series, w: pd.Series) -> float | None:
    ok = v.notna() & w.notna() & np.isfinite(v)
    if not ok.any():
        return None
    v, w = v[ok].to_numpy(dtype=float), w[ok].to_numpy(dtype=float)
    o = np.argsort(v)
    cw = np.cumsum(w[o])
    return float(v[o][np.searchsorted(cw, 0.5 * cw[-1])])


def compute(level: str = "appetite", top_groups: int = 15) -> dict[str, Any]:
    if level not in LEVELS:
        raise ValueError(f"level must be one of {LEVELS}")
    lin = C.Lineage()
    m = C.book()
    C.book_lineage(lin)
    L = C.appetite_rows()
    for k in ("sector_policy", "sector_appetite", "re_construction_share", "rating_bucket", "sub_ig_share", "sector_hhi",
              "cost_of_risk_bps", "bu_rwa_budget", "bu_el_budget", "min_rating", "group_connected", "group_large_exposure"):
        lin.param("risk_appetite", k)

    T = float(m["ead_sar_mn"].sum())
    by_sec = m.groupby("sector")["ead_sar_mn"].sum()
    by_b = m.groupby("bucket")["ead_sar_mn"].sum()
    rc_secs = L["re_construction_share"].get("sectors", ["Real Estate", "Construction"])
    S_rc = float(by_sec.reindex(rc_secs).fillna(0).sum())
    S_sub = float(by_b.reindex(["BB", "B", "CCC-C"]).fillna(0).sum())
    perf = m[m["stage"] < 3]
    el_perf = float((perf["pd_pit_12m"] * perf["lgd_pct"] / 100 * perf["ead_sar_mn"]).sum())
    ead_perf = float(perf["ead_sar_mn"].sum())
    shares = (by_sec / T).to_dict()
    hhi0 = float(sum(v * v for v in shares.values()))

    rw_budget = float(L["bu_rwa_budget"]["appetite_sar_mn" if level == "appetite" else
                                          "trigger_sar_mn" if level == "trigger" else "headroom_sar_mn"])
    el_budget = float(L["bu_el_budget"]["appetite_sar_mn" if level == "appetite" else
                                         "trigger_sar_mn" if level == "trigger" else "headroom_sar_mn"])
    cor_cap = _level(L["cost_of_risk_bps"], level) / 1e4
    hhi_cap = _level(L["sector_hhi"], level)
    sub_cap = _level(L["sub_ig_share"], level)
    rc_cap = _level(L["re_construction_share"], level)
    pol_cap = _level(L["sector_policy"], level)

    rr = _book_raroc()
    if rr is not None:
        lin.add("ecl_runs", "ecl_facility", period=C.RUN_CURRENT, columns=["rating"])
        lin.add("origination", "orig_facility", columns=["orig_margin_pct", "hurdle_rate_pct"])
        lin.add("ews", "corp_exposure", period=C.AS_OF_QUARTER, columns=["limit_sar_mn", "drawn_sar_mn", "pd_pit_12m", "lgd_pct"])
    mr = m.merge(rr[["facility_id", "raroc_now", "slope_margin", "orig_margin_pct"]], on="facility_id", how="left") if rr is not None else m

    rows: list[dict[str, Any]] = []
    for (sec, bk), g in mr[mr["stage"] < 3].groupby(["sector", "bucket"]):
        ead_g = float(g["ead_sar_mn"].sum())
        el_rate = float((g["pd_pit_12m"] * g["lgd_pct"] / 100 * g["ead_sar_mn"]).sum() / ead_g) if ead_g else 0.0
        rw = float(g["crwa_sar_mn"].sum() / ead_g) if ead_g else 1.0
        S_sec = float(by_sec.get(sec, 0.0))
        S_b = float(by_b.get(bk, 0.0))
        cons: list[dict[str, Any]] = []

        def add(name: str, label: str, metric, cap: float | None, unit: str) -> None:
            if cap is None:
                return
            x, already = _max_x(metric, cap)
            cons.append({"name": name, "label": label, "cap": cap, "now": metric(0.0), "unit": unit,
                         "headroom_sar_mn": x, "already_beyond": already})

        add("sector_policy", f"Sector share ({sec})", lambda x: (S_sec + x) / (T + x), pol_cap, "share")
        if sec in L["sector_appetite"].get("limits", {}):
            add("sector_appetite", f"Sector appetite ({sec})", lambda x: (S_sec + x) / (T + x),
                _level(L["sector_appetite"], level, sec), "share")
        if sec in rc_secs:
            add("re_construction_share", "Real estate and construction", lambda x: (S_rc + x) / (T + x), rc_cap, "share")
        add("rating_bucket", f"Rating bucket {bk}", lambda x: (S_b + x) / (T + x), _level(L["rating_bucket"], level, bk), "share")
        if bk != "IG":
            add("sub_ig_share", "Sub-investment-grade share", lambda x: (S_sub + x) / (T + x), sub_cap, "share")

        def hhi(x: float, sec=sec) -> float:
            t = T + x
            return float(sum(((v + (x if k == sec else 0.0)) / t) ** 2 for k, v in by_sec.items()))
        add("sector_hhi", "Sector concentration (HHI)", hhi, hhi_cap, "index")
        add("cost_of_risk_bps", "Expected cost of risk", lambda x: (el_perf + x * el_rate) / (ead_perf + x), cor_cap, "rate")
        add("bu_rwa_budget", "BU RWA budget", lambda x: x * rw, rw_budget, "SAR m")
        add("bu_el_budget", "BU EL budget", lambda x: x * el_rate, el_budget, "SAR m")
        if bk == "CCC-C":
            cons.append({"name": "min_rating", "label": "Minimum rating (no new money below B-)", "cap": None, "now": None,
                         "unit": "rating", "headroom_sar_mn": 0.0, "already_beyond": False})
        bind = min(cons, key=lambda c: c["headroom_sar_mn"])
        head = float(bind["headroom_sar_mn"])
        h, hsrc = C.hurdle(sec)
        r_med = _wmedian(g["raroc_now"], g["ead_sar_mn"]) if "raroc_now" in g else None
        need_bps = None
        if r_med is not None and "slope_margin" in g:
            sl = _wmedian(g["slope_margin"], g["ead_sar_mn"])
            if sl and sl > 0:
                need_bps = max(0.0, (h - r_med) / sl * 1e4)
        clears = None if r_med is None else bool(r_med >= h)
        share_above = None
        if "raroc_now" in g:
            ok = g["raroc_now"].notna()
            if ok.any():
                share_above = float(g.loc[ok & (g["raroc_now"] >= h), "ead_sar_mn"].sum() / g.loc[ok, "ead_sar_mn"].sum())
        rows.append({
            "sector": sec, "bucket": bk, "slice": f"{sec} · {bk}", "book_ead_sar_mn": ead_g,
            "headroom_sar_mn": head, "binding": bind["name"], "binding_label": bind["label"],
            "binding_already_beyond": bool(bind["already_beyond"]),
            "rwa_used_sar_mn": head * rw, "capital_used_sar_mn": head * rw * C.capital_ratio(),
            "el_rate_bps": el_rate * 1e4, "risk_weight": rw,
            "hurdle": h, "hurdle_source": hsrc, "raroc_median": r_med, "clears_hurdle": clears,
            "ead_share_above_hurdle": share_above, "margin_uplift_bps": need_bps,
            "constraints": cons,
        })
    rows.sort(key=lambda r: (-r["headroom_sar_mn"], r["slice"]))
    C.capital_ratio(lin)

    # connected groups
    gcap = _level(L["group_connected"], level)
    t1 = C.tier1(lin)
    le_pct = float(L["group_large_exposure"]["appetite_pct_tier1" if level == "appetite" else
                                              "trigger_pct_tier1" if level == "trigger" else "limit_pct_tier1"])
    gr = m.groupby("connected_group_id").agg(name=("connected_group_name", "first"), ead=("ead_sar_mn", "sum"),
                                             members=("borrower_id", "nunique"))
    gr = gr[gr["members"] >= 2]
    cap_g = min(gcap, le_pct * t1)
    gr["headroom"] = (cap_g - gr["ead"]).clip(lower=0)
    gr["binding"] = np.where(gcap <= le_pct * t1, "group_connected", "group_large_exposure")
    gr["utilisation"] = gr["ead"] / cap_g
    n_over = int((gr["ead"] > cap_g).sum())
    gr = gr.sort_values(["utilisation", "ead"], ascending=False).head(top_groups)
    groups = [{"group_id": k, "group_name": r["name"], "members": int(r["members"]), "ead_sar_mn": float(r["ead"]),
               "cap_sar_mn": cap_g, "headroom_sar_mn": float(r["headroom"]), "binding": r["binding"],
               "over_cap_sar_mn": max(0.0, float(r["ead"]) - cap_g), "utilisation": float(r["utilisation"])}
              for k, r in gr.iterrows()]

    c_sub = float(sub_cap)
    ig_first = max(0.0, (S_sub - c_sub * T) / c_sub)
    kp = {
        "ig_before_sub_ig_sar_mn": ig_first, "sub_ig_per_ig": c_sub / (1 - c_sub), "groups_over_cap": n_over,
        "book_ead": T, "cost_of_risk_bps": el_perf / ead_perf * 1e4, "sub_ig_share": S_sub / T, "hhi": hhi0,
        "re_construction_share": S_rc / T,
    }
    open_rows = [r for r in rows if r["headroom_sar_mn"] > 1.0]
    best_clear = [r for r in open_rows if r["clears_hurdle"]]
    beyond = sorted({(c["label"] if c["name"] != "sector_appetite" else c["label"]) for r in rows for c in r["constraints"] if c["already_beyond"] and c["name"] in
                     ("sub_ig_share", "cost_of_risk_bps", "re_construction_share", "sector_appetite", "rating_bucket")})
    summary = _write(level, rows, open_rows, best_clear, groups, kp, L, beyond)
    kpis = [
        C.kpi("open_slices", "Slices with headroom", len(open_rows), "count", f"{len(open_rows)} of {len(rows)}"),
        C.kpi("best_clearing", "Largest slice clearing hurdle", best_clear[0]["headroom_sar_mn"] if best_clear else 0.0, "SAR m",
              best_clear[0]["slice"] if best_clear else "none"),
        C.kpi("rwa_budget", "BU RWA budget at " + level, rw_budget, "SAR m"),
        C.kpi("cost_of_risk", "Cost of risk now", kp["cost_of_risk_bps"], "bps", f"{level} {cor_cap * 1e4:.0f} bps"),
        C.kpi("sub_ig", "Sub-IG share now", kp["sub_ig_share"], "share", f"{level} {C.pct(sub_cap)}"),
    ]
    limits = [
        "Slices are alternatives, not additive: each is solved alone against the shared BU RWA and EL budgets.",
        "New lending is assumed Stage 1 at the slice's current EL rate and CRWA risk weight; pricing, tenor, region, "
        "collateral type and structure (Islamic share) of the new business are not known in advance and are not constrained here.",
        "RAROC now is the Book drift engine's one-year RAROC on the existing facilities of the slice; it is a guide to the "
        "hurdle a new deal would clear at today's pricing, not a quote." if rr is not None else
        "The Book drift engine could not be built here, so hurdle clearance is not shown.",
        "Group headroom uses the relationship domain's connected groups (two or more members) and Tier 1 from the capital "
        "parameter table; an approved group cap tighter than the policy limit (Deal Desk group exposure) is not applied here.",
    ]
    method = [
        "Each risk-appetite metric is recomputed with the slice's new lending added; the largest X keeping it at or under "
        f"its {level} level is found by bisection; the slice headroom is the smallest X and its constraint is binding.",
        "A metric already beyond its level allows only lending that does not worsen it.",
        "Hurdle: returns.hurdle (sector override) vs EAD-weighted median RAROC now; margin uplift = (hurdle - RAROC) / dRAROC/dmargin.",
    ]
    return C.envelope("headroom", "Growth headroom map", summary[0], summary, kpis, rows, limits, method, lin,
                      {"level": level, "groups": groups, "book": kp})


def _write(level, rows, open_rows, best_clear, groups, kp, L, beyond) -> list[str]:
    out = []
    tot = sum(r["headroom_sar_mn"] for r in open_rows)
    if open_rows:
        top = open_rows[:3]
        out.append(f"Within {level}, {len(open_rows)} of {len(rows)} sector-rating slices can still take new lending next quarter; "
                   f"the widest are " + ", ".join(f"{r['slice']} ({C.sar(r['headroom_sar_mn'], 0)}, bound by the {r['binding_label']})"
                                                    for r in top) + ".")
    else:
        out.append(f"No sector-rating slice has headroom within {level}; every slice is bound by a metric already at or beyond its level.")
    if best_clear:
        b = best_clear[0]
        out.append(f"Best growth that also clears the hurdle: {b['slice']}, up to {C.sar(b['headroom_sar_mn'], 0)} at a median RAROC "
                   f"of {C.pct(b['raroc_median'])} against a {C.pct(b['hurdle'], 0)} hurdle.")
    miss = [r for r in open_rows if r["clears_hurdle"] is False and r["margin_uplift_bps"] is not None]
    if miss:
        r = max(miss, key=lambda r: r["headroom_sar_mn"])
        out.append(f"{r['slice']} has room ({C.sar(r['headroom_sar_mn'], 0)}) but today's pricing does not clear its "
                   f"{C.pct(r['hurdle'], 0)} hurdle: the median facility needs about {C.bps(r['margin_uplift_bps'])} more margin.")
    if beyond:
        out.append(f"Already beyond {level}: " + "; ".join(beyond) + f". Sub-IG is {C.pct(kp['sub_ig_share'])} and cost of risk "
                   f"{kp['cost_of_risk_bps']:.1f} bps" + (f", so any sub-IG slice opens only after about {C.sar(kp['ig_before_sub_ig_sar_mn'], 0)} "
                   f"of IG lending, then {kp['sub_ig_per_ig']:.2f} of sub-IG per 1 of IG." if kp["ig_before_sub_ig_sar_mn"] > 0.5 else "."))
    if groups:
        g = groups[0]
        if g["over_cap_sar_mn"] > 0:
            out.append(f"{kp['groups_over_cap']} connected group(s) are over the {C.sar(g['cap_sar_mn'], 0)} {level} cap and closed to new money; "
                       f"the largest excess is {g['group_name']} at {C.sar(g['ead_sar_mn'], 0)} ({C.sar(g['over_cap_sar_mn'], 0)} over).")
        else:
            out.append(f"Tightest connected group: {g['group_name']} at {C.sar(g['ead_sar_mn'], 0)} of a {C.sar(g['cap_sar_mn'], 0)} cap "
                       f"({C.sar(g['headroom_sar_mn'], 0)} left).")
    del tot
    return out[:5]
