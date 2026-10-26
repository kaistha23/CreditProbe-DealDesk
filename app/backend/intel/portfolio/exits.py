"""Exit and sell-down list (R14 backlog #15): names to reduce, sell down or not renew, ranked by capital and ECL freed
per unit of relationship value lost.

Universe: performing obligors (no Stage 3 facility; Stage 3 names belong to the workout optimiser) that meet at least one
reason to shrink: RAROC now below hurdle on the obligor's EAD-weighted book, Early Warning band high or critical, a
connected group over its cap, or the obligor sitting in a rating bucket or sector already beyond risk appetite.

Per obligor (SAR m, the facility rows of the corporate book at 2026Q2 joined to the Book's RAROC engine):
    capital  = CRWA (collateral.col_crwa) x capital_ratio_target
    ECL      = ECL of the current run (ecl_runs.ecl_facility 2026Q3)
    value    = margin x drawn + fees now + cross-sell realised (Book drift engine) + deposits x deposit_spread (deposits.dep_derived)
               + undrawn x commitment_fee (expert assumption)
Action (first that applies):
    not renew   any facility renews within the window and RAROC now is below hurdle: the renewing facilities leave
    sell down   obligor EAD >= sell_down_min: sell_down_share of every facility, at the bucket's sale discount
    reduce      cancel undrawn commitments (CCF released) and amortise to the group cap where the group is over
Freed = share of capital and ECL leaving with the reduced EAD; value lost = the same share of the relationship value
(cross-sell and deposits leave in full on not renew). Score = (capital + ECL freed - sale loss) / value lost.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from backend.intel.portfolio import common as C
from backend.intel.portfolio.headroom import _book_raroc


def _frame(lin: C.Lineage) -> pd.DataFrame:
    m = C.book()
    C.book_lineage(lin)
    ecl = C.read(lin, "ecl_runs", "ecl_facility", ["exposure_id", "ecl_sar_mn", "book"], period=("run_id", C.RUN_CURRENT))
    ecl = ecl[ecl["book"] == "corporate"].rename(columns={"exposure_id": "facility_id", "ecl_sar_mn": "ecl_run_sar_mn"})
    m = m.merge(ecl[["facility_id", "ecl_run_sar_mn"]], on="facility_id", how="left")
    m["ecl_run_sar_mn"] = m["ecl_run_sar_mn"].fillna(m["ecl_sar_mn"])
    rr = _book_raroc()
    cols = ["facility_id", "raroc_now", "orig_margin_pct"]
    if rr is not None:
        from backend.dealdesk.book import core
        f, _ = core.frame()
        x = f[f["source"] == "book"][["facility_id", "raroc_now", "orig_margin_pct", "fee_now_sar_mn", "xs_realised_sar_mn",
                                       "ews_band", "months_to_renewal", "renewal_kind", "capital_now_sar_mn"]]
        m = m.merge(x, on="facility_id", how="left")
        lin.add("ews", "corp_exposure", period=C.AS_OF_QUARTER, columns=["ews_band"])
        lin.add("origination", "orig_facility", columns=["orig_margin_pct", "orig_fees_sar_mn", "orig_date"])
    else:
        for c in cols[1:] + ["fee_now_sar_mn", "xs_realised_sar_mn", "ews_band", "months_to_renewal", "renewal_kind"]:
            m[c] = np.nan
    dep = C.read(lin, "deposits", "dep_derived", ["obligor_id", "avg_relationship_deposits_sar_mn", "book"])
    dep = dep[dep["book"] == "corporate"].groupby("obligor_id")["avg_relationship_deposits_sar_mn"].mean()
    m["deposits_sar_mn"] = m["borrower_id"].map(dep).fillna(0.0)
    return m


def compute(limit: int = 25, min_freed: float = 1.0) -> dict[str, Any]:
    lin = C.Lineage()
    m = _frame(lin)
    k = C.capital_ratio(lin)
    L = C.appetite_rows()
    lin.param("risk_appetite", "group_connected")
    lin.param("risk_appetite", "rating_bucket")
    lin.param("risk_appetite", "sector_appetite")
    win = float(C.A("renewal_window_months", lin))
    sd_min = float(C.A("sell_down_min_ead_sar_mn", lin))
    sd_share = float(C.A("sell_down_share", lin))
    disc = C.A("sale_discount_by_bucket", lin)
    dspread = float(C.A("deposit_spread", lin))
    ccf = 0.4  # ccf.undrawn_committed.regulatory
    lin.param("ccf", "undrawn_committed")

    T = float(m["ead_sar_mn"].sum())
    by_b = m.groupby("bucket")["ead_sar_mn"].sum() / T
    beyond_b = {b for b, v in by_b.items() if v > float(L["rating_bucket"]["appetites"].get(b, 1.0))}
    by_s = m.groupby("sector")["ead_sar_mn"].sum() / T
    beyond_s = {s for s, v in by_s.items() if v > float(L["sector_appetite"]["appetites"].get(s, 1.0))}
    gcap = float(L["group_connected"]["appetite"])
    g_ead = m.groupby("connected_group_id")["ead_sar_mn"].sum()
    g_n = m.groupby("connected_group_id")["borrower_id"].nunique()
    over = {g: float(v - gcap) for g, v in g_ead.items() if v > gcap and g_n.get(g, 0) >= 2}

    m["hurdle"] = m["sector"].map(lambda s: C.hurdle(s)[0])
    C.hurdle("", lin)
    m["income"] = (m["orig_margin_pct"].fillna(0) / 100 * m["drawn_sar_mn"] + m["fee_now_sar_mn"].fillna(0)
                   + m["xs_realised_sar_mn"].fillna(0))
    m["capital"] = m["crwa_sar_mn"] * k
    cfee = float(C.A("commitment_fee", lin))
    s3 = set(m.loc[m["stage"] >= 3, "borrower_id"])
    m = m[~m["borrower_id"].isin(s3)].copy()
    m["w_raroc"] = m["raroc_now"].fillna(0) * m["ead_sar_mn"]
    m["ead_raroc"] = m["ead_sar_mn"].where(m["raroc_now"].notna(), 0.0)
    m["has_raroc"] = m["raroc_now"].notna()
    m["drawn_inc"] = m["orig_margin_pct"].fillna(0) / 100 * m["drawn_sar_mn"]
    m["ren"] = m["months_to_renewal"].notna() & (m["months_to_renewal"] <= win)
    for c in ("ead_sar_mn", "capital", "ecl_run_sar_mn", "income"):
        m[f"ren_{c}"] = m[c].where(m["ren"], 0.0)
    m["ren_months"] = m["months_to_renewal"].where(m["ren"])
    ag = m.groupby("borrower_id").agg(
        name=("borrower_name", "first"), sector=("sector", "first"), bucket=("bucket", "first"), rating=("rating_current", "first"),
        grp=("connected_group_id", "first"), grp_name=("connected_group_name", "first"), tier=("relationship_tier", "first"),
        ead=("ead_sar_mn", "sum"), n=("facility_id", "size"), w_raroc=("w_raroc", "sum"), ead_raroc=("ead_raroc", "sum"), has_raroc=("has_raroc", "any"),
        hurdle=("hurdle", "first"), band=("ews_band", "first"), cap=("capital", "sum"), ecl=("ecl_run_sar_mn", "sum"),
        dep=("deposits_sar_mn", "first"), income=("income", "sum"), xs=("xs_realised_sar_mn", "sum"),
        fee=("fee_now_sar_mn", "sum"), drawn_inc=("drawn_inc", "sum"), und=("undrawn_sar_mn", "sum"),
        ren_n=("ren", "sum"), ren_ead=("ren_ead_sar_mn", "sum"), ren_cap=("ren_capital", "sum"), ren_ecl=("ren_ecl_run_sar_mn", "sum"),
        ren_inc=("ren_income", "sum"), ren_months=("ren_months", "min"))
    ag = ag[ag["ead"] > 0]
    rows: list[dict[str, Any]] = []
    for bid, a in ag.iterrows():
        ead = float(a["ead"])
        r_now = float(a["w_raroc"] / a["ead_raroc"]) if a["has_raroc"] and a["ead_raroc"] > 0 else None
        h = float(a["hurdle"])
        band = None if pd.isna(a["band"]) else str(a["band"])
        bk, sec, grp = str(a["bucket"]), str(a["sector"]), a["grp"]
        reasons = []
        if r_now is not None and r_now < h:
            reasons.append(f"RAROC {C.pct(r_now)} below {C.pct(h, 0)} hurdle")
        if band in ("high", "critical"):
            reasons.append(f"Early Warning {band}")
        if grp in over:
            reasons.append(f"group over cap by {C.sar(over[grp], 0)}")
        if bk in beyond_b:
            reasons.append(f"rating bucket {bk} beyond appetite")
        if sec in beyond_s:
            reasons.append(f"{sec} beyond sector appetite")
        if not reasons:
            continue
        cap, ecl, dep, income, xs = float(a["cap"]), float(a["ecl"]), float(a["dep"]), float(a["income"]), float(a["xs"] or 0)
        value = income + dep * dspread + float(a["und"]) * cfee
        loss = 0.0
        if a["ren_n"] > 0 and r_now is not None and r_now < h:
            action = "not_renew"
            red = float(a["ren_ead"])
            share = red / ead
            cap_f, ecl_f = float(a["ren_cap"]), float(a["ren_ecl"])
            v_lost = float(a["ren_inc"]) + (dep * dspread + float(a["und"]) * cfee if share >= 0.999 else dep * dspread * share)
            how = (f"let {int(a['ren_n'])} facilit{'y' if a['ren_n'] == 1 else 'ies'} run off at renewal "
                   f"(next in {float(a['ren_months']):.0f} months)")
        elif ead >= sd_min:
            action = "sell_down"
            share = sd_share
            red = ead * share
            cap_f, ecl_f = cap * share, ecl * share
            loss = red * float(disc.get(bk, disc["CCC-C"]))
            v_lost = income * share + float(a["und"]) * cfee * share
            how = f"sell {C.pct(share, 0)} ({C.sar(red)}) at about {C.pct(disc.get(bk, 0.0), 0)} below par"
        else:
            action = "reduce"
            und = float(a["und"])
            extra = over.get(grp, 0.0) * ead / float(g_ead.get(grp, ead)) if grp in over else 0.0
            red = min(ead, und * ccf + extra)
            share = red / ead
            cap_f, ecl_f = cap * share, ecl * share
            v_lost = und * cfee + float(a["drawn_inc"]) * (extra / ead)
            how = f"cancel {C.sar(und)} undrawn" + (f" and amortise {C.sar(extra)} to bring the group under cap" if extra else "")
        freed = cap_f + ecl_f - loss
        if red <= 0.01 or freed < min_freed:
            continue
        score = freed / max(v_lost, 0.01)
        rows.append({"borrower_id": bid, "borrower_name": str(a["name"]), "sector": sec, "bucket": bk,
                     "rating": str(a["rating"]), "group_id": grp, "group_name": str(a["grp_name"]),
                     "relationship_tier": str(a["tier"]),
                     "ead_sar_mn": ead, "facilities": int(a["n"]), "raroc_now": r_now, "hurdle": h, "ews_band": band,
                     "action": action, "how": how, "ead_reduced_sar_mn": red, "capital_freed_sar_mn": cap_f,
                     "ecl_freed_sar_mn": ecl_f, "sale_loss_sar_mn": loss, "net_freed_sar_mn": freed,
                     "relationship_value_lost_sar_mn": v_lost, "relationship_value_sar_mn": value,
                     "score": score, "reasons": reasons})
    rows.sort(key=lambda r: (-r["score"], r["borrower_id"]))
    top = rows[:limit]
    tot = {a: {"names": sum(1 for r in top if r["action"] == a),
               "capital": sum(r["capital_freed_sar_mn"] for r in top if r["action"] == a),
               "ecl": sum(r["ecl_freed_sar_mn"] for r in top if r["action"] == a)} for a in ("not_renew", "sell_down", "reduce")}
    cap_top = sum(r["capital_freed_sar_mn"] for r in top)
    ecl_top = sum(r["ecl_freed_sar_mn"] for r in top)
    val_top = sum(r["relationship_value_lost_sar_mn"] for r in top)
    summary = _write(top, rows, tot, cap_top, ecl_top, val_top, k)
    kpis = [C.kpi("candidates", "Names with a reason to shrink", len(rows), "count"),
            C.kpi("capital_freed", f"Capital freed, top {len(top)}", cap_top, "SAR m"),
            C.kpi("ecl_freed", f"ECL released, top {len(top)}", ecl_top, "SAR m"),
            C.kpi("value_lost", "Relationship value lost a year", val_top, "SAR m"),
            C.kpi("ratio", "Freed per 1 of value lost", (cap_top + ecl_top) / val_top if val_top else None, "x")]
    limits = [
        "Relationship value is the lending margin, fees and realised cross-sell (Book drift engine) plus deposits at an assumed "
        f"{C.pct(dspread, 1)} spread; FX, trade and payroll income not routed through cross-sell promises are not in Data Domains.",
        "Sale discounts by rating bucket are expert assumptions: the bank has no loan-sale history (backend/intel/portfolio/assumptions.json).",
        "ECL freed is the provision released if the exposure leaves at the current run's coverage; a sale below carrying value books the discount as a loss.",
        "Stage 3 names are excluded: their options are compared by the workout optimiser.",
    ]
    method = [f"Materiality: only actions freeing at least {C.sar(min_freed)} net (capital + ECL - sale loss) are listed.",
              "Universe: performing obligors with at least one reason to shrink (below hurdle, EWS high/critical, group over cap, "
              "bucket or sector beyond appetite).",
              "Action rule: not renew (renewal in window and below hurdle) > sell down (EAD at least the desk minimum) > reduce (undrawn and group excess).",
              "Score = (capital freed + ECL released - sale loss) / annual relationship value lost; ties by obligor id."]
    return C.envelope("exits", "Exit and sell-down list", summary[0], summary, kpis, top, limits, method, lin,
                      {"totals_by_action": tot, "universe": len(rows)})


def _write(top, rows, tot, cap_top, ecl_top, val_top, k) -> list[str]:
    if not top:
        return ["No performing name meets a reason to shrink at the current appetite and hurdle."]
    out = [f"{len(rows)} performing names have a reason to shrink and a material action; the top {len(top)} free {C.sar(cap_top)} of capital and "
           f"release {C.sar(ecl_top)} of ECL for {C.sar(val_top, 2)} of annual relationship value."]
    a = top[0]
    out.append(f"Start with {a['borrower_name']} ({a['rating']}, {a['sector']}): {a['how']}; frees "
               f"{C.sar(a['capital_freed_sar_mn'] + a['ecl_freed_sar_mn'] - a['sale_loss_sar_mn'], 2)} net for "
               f"{C.sar(a['relationship_value_lost_sar_mn'], 2)} a year ({'; '.join(a['reasons'])}).")
    parts = [f"{v['names']} {lab}" for lab, v in (("not renew", tot["not_renew"]), ("sell down", tot["sell_down"]),
                                                   ("reduce", tot["reduce"])) if v["names"]]
    out.append("Mix of the top list: " + ", ".join(parts) + ".")
    strat = [r for r in top if r["relationship_tier"] == "Strategic"]
    if strat:
        out.append(f"{len(strat)} of them are Strategic relationships; the RM should confirm the cross-sell before the exit is agreed.")
    return out
