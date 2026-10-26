"""RWA finder (R14 backlog #16): capital savings in the corporate book, each with its SAR RWA and capital effect.

Base: collateral.col_crwa per exposure, RWA = (EAD - CRM) x RW (the collateral domain's standardised-style weights).
Per facility the savings are applied in sequence so nothing is counted twice:

  A. Exposure class
     defaulted_provisioned  Stage 3 at 150% whose ECL (ecl_runs, current run) is at least 20% of EAD -> 100%
                            (Basel III SA CRE20.88; assumption defaulted_rw_provisioned)
     sme_corporate          performing, RW 100% (the unrated-corporate weight), obligor revenue up to the SME threshold
                            -> 85% (sa_risk_weights.sme_corporate)
  B. Unused undrawn limits  committed revolving, overdraft, working-capital and trade lines whose utilisation stayed at or
                            below the threshold in each of the last 4 quarters: cut the limit to the 4-quarter peak drawn
                            plus a buffer; EAD falls by the cut x the facility's own CCF ((EAD - drawn) / undrawn)
  C. Guarantees not recognised  col_guarantee (perfected or not) whose guarantor (an obligor of the book, not in Stage 3)
                            carries a lower risk weight than the exposure: the covered unsecured part takes the guarantor's
                            weight (substitution). Perfected -> recognisable now; not perfected -> after perfection;
                            guarantor in the obligor's own connected group -> to confirm (wrong-way risk).
Capital effect = RWA saving x capital.capital_ratio_target.

Also reported, not counted as savings: CRM already recognised on collateral whose registration is Pending or Not
registered (col_item), i.e. RWA that would come back if that collateral were derecognised (capital at risk).
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from backend.intel.portfolio import common as C

CATEGORIES = {
    "defaulted_provisioned": "Defaulted, provisioned: 150% to 100%",
    "sme_corporate": "SME corporate class: 100% to 85%",
    "unused_undrawn": "Unused undrawn limit cut",
    "guarantee_recognisable": "Perfected guarantee not recognised",
    "guarantee_after_perfection": "Guarantee to perfect",
    "guarantee_intra_group": "Intra-group guarantee (to confirm)",
}
STATUS = {"defaulted_provisioned": "recognisable", "sme_corporate": "to_confirm", "unused_undrawn": "after_action",
          "guarantee_recognisable": "recognisable", "guarantee_after_perfection": "after_action",
          "guarantee_intra_group": "to_confirm"}
REVOLVING = ("revolving_credit", "overdraft", "working_capital", "trade_finance")


def _history(lin: C.Lineage) -> pd.DataFrame:
    h = C.read(lin, "cockpit", "corp_facility_quarter", ["facility_id", "reporting_quarter", "utilisation_pct", "drawn_sar_mn"])
    qs = sorted(h["reporting_quarter"].unique())[-4:]
    h = h[h["reporting_quarter"].isin(qs)]
    return h.groupby("facility_id").agg(util_max=("utilisation_pct", "max"), drawn_peak=("drawn_sar_mn", "max"),
                                        quarters=("reporting_quarter", "nunique"))


def compute(limit: int = 30) -> dict[str, Any]:
    lin = C.Lineage()
    m = C.book().copy()
    C.book_lineage(lin)
    k = C.capital_ratio(lin)
    ecl = C.read(lin, "ecl_runs", "ecl_facility", ["exposure_id", "ecl_sar_mn", "book"], period=("run_id", C.RUN_CURRENT))
    ecl = ecl[ecl["book"] == "corporate"].set_index("exposure_id")["ecl_sar_mn"]
    m["ecl_run"] = m["facility_id"].map(ecl).fillna(m["ecl_sar_mn"])
    prov = C.A("defaulted_rw_provisioned", lin)
    prov_min = float(C._assumptions()["rows"]["defaulted_rw_provisioned"]["provision_min"])
    sme_max = float(C.A("sme_revenue_max_sar_mn", lin))
    sme_rw = float(C.A("sme_rw", lin))
    lin.param("sa_risk_weights", "sme_corporate")
    u_max = float(C.A("unused_utilisation_max", lin)) * 100
    buf = float(C.A("unused_buffer", lin))

    ead0 = m["ead_sar_mn"].to_numpy(float)
    crm = m["crm_sar_mn"].to_numpy(float)
    rw0 = m["risk_weight_pct"].to_numpy(float) / 100
    net0 = np.maximum(ead0 - crm, 0)
    # A. class
    cov = np.where(ead0 > 0, m["ecl_run"].to_numpy(float) / np.where(ead0 > 0, ead0, 1), 0)
    is_def = (m["stage"].to_numpy() >= 3) & (rw0 >= 1.5 - 1e-9) & (cov >= prov_min)
    is_sme = (m["stage"].to_numpy() < 3) & (np.abs(rw0 - 1.0) < 1e-9) & (m["revenue_sar_mn"].to_numpy(float) <= sme_max)
    rw1 = np.where(is_def, float(prov), np.where(is_sme, sme_rw, rw0))
    dA = net0 * (rw0 - rw1)
    # B. unused undrawn
    hist = _history(lin)
    hm = m[["facility_id"]].join(hist, on="facility_id")
    und = m["undrawn_sar_mn"].to_numpy(float)
    ccf_i = np.where(und > 0, (ead0 - m["drawn_sar_mn"].to_numpy(float)) / np.where(und > 0, und, 1), 0).clip(0, 1)
    unused = (m["product_type"].isin(REVOLVING).to_numpy() & (m["stage"].to_numpy() < 3)
              & (hm["quarters"].fillna(0).to_numpy() >= 4) & (hm["util_max"].fillna(100).to_numpy() <= u_max))
    keep = hm["drawn_peak"].fillna(0).to_numpy(float) * (1 + buf)
    cut = np.where(unused, np.clip(m["limit_sar_mn"].to_numpy(float) - keep, 0, und), 0.0)
    ead1 = ead0 - cut * ccf_i
    net1 = np.maximum(ead1 - crm, 0)
    dB = (net0 - net1) * rw1
    # C. guarantees
    g = C.read(lin, "collateral", "col_guarantee", ["exposure_id", "obligor_id", "guarantor_cif", "guarantor_name",
                                                    "amount_sar_mn", "perfected", "book"])
    g = g[g["book"] == "corporate"]
    bor = C.read(lin, "cockpit", "corp_borrower_quarter", ["borrower_id", "rating_current", "connected_group_id"],
                 period=("reporting_quarter", C.AS_OF_QUARTER))
    rat = bor.set_index("borrower_id")["rating_current"]
    from backend.dealdesk import portfolio
    grp = portfolio.frames()["borrower"].set_index("borrower_id")["connected_group_id"]
    s3 = set(m.loc[m["stage"] >= 3, "borrower_id"])
    g = g.assign(rw_g=g["guarantor_cif"].map(rat).map(C.CRWA_RW).astype(float) / 100,
                 intra=g["guarantor_cif"].map(grp).to_numpy() == g["obligor_id"].map(grp).to_numpy(),
                 g_def=g["guarantor_cif"].isin(s3))
    g = g[g["rw_g"].notna() & ~g["g_def"]]
    g["kind"] = np.where(g["intra"], "guarantee_intra_group",
                         np.where(g["perfected"] == 1, "guarantee_recognisable", "guarantee_after_perfection"))
    idx = pd.Series(np.arange(len(m)), index=m["facility_id"])
    g = g[g["exposure_id"].isin(idx.index)].sort_values(["exposure_id", "rw_g"])
    left = net1.copy()
    g_rows = []
    for r in g.itertuples(index=False):
        i = int(idx[r.exposure_id])
        if rw1[i] <= r.rw_g + 1e-9 or left[i] <= 0:
            continue
        covd = min(float(r.amount_sar_mn), left[i])
        left[i] -= covd
        g_rows.append((i, r.kind, covd * (rw1[i] - r.rw_g), covd, r.guarantor_name, r.rw_g))

    items: list[dict[str, Any]] = []

    def item(i: int, cat: str, d_rwa: float, detail: str) -> None:
        r = m.iloc[i]
        items.append({"facility_id": r["facility_id"], "borrower_id": r["borrower_id"], "borrower_name": r["borrower_name"],
                      "sector": r["sector"], "rating": r["rating_current"], "stage": int(r["stage"]),
                      "category": cat, "category_label": CATEGORIES[cat], "status": STATUS[cat],
                      "ead_sar_mn": float(ead0[i]), "rwa_now_sar_mn": float(r["crwa_sar_mn"]), "rw_now": float(rw0[i]),
                      "rwa_saving_sar_mn": float(d_rwa), "capital_saving_sar_mn": float(d_rwa * k), "detail": detail})

    for i in np.where(dA > 1e-6)[0]:
        if is_def[i]:
            item(i, "defaulted_provisioned", dA[i], f"ECL covers {C.pct(cov[i], 0)} of EAD (at least {C.pct(prov_min, 0)}): 150% to 100%")
        else:
            item(i, "sme_corporate", dA[i], f"revenue {C.sar(float(m['revenue_sar_mn'].iloc[i]))} up to the SAR {sme_max:.0f}m SME threshold: 100% to 85%")
    for i in np.where(dB > 1e-6)[0]:
        item(i, "unused_undrawn", dB[i], f"utilisation at most {u_max:.0f}% for 4 quarters; cut the limit by {C.sar(float(cut[i]))} "
             f"to {C.sar(float(keep[i]))} (CCF {ccf_i[i]:.2f})")
    for i, kind, d, covd, gname, rwg in g_rows:
        item(i, kind, d, f"{gname} guarantees {C.sar(covd)} of the unsecured part at {rwg:.0%} instead of {rw1[i]:.0%}")

    df = pd.DataFrame(items)
    rwa_tot = float(m["crwa_sar_mn"].sum())
    by_cat = []
    if len(df):
        for cat, gg in df.groupby("category"):
            by_cat.append({"category": cat, "label": CATEGORIES[cat], "status": STATUS[cat], "facilities": int(len(gg)),
                           "rwa_saving_sar_mn": float(gg["rwa_saving_sar_mn"].sum()),
                           "capital_saving_sar_mn": float(gg["capital_saving_sar_mn"].sum())})
        by_cat.sort(key=lambda x: -x["rwa_saving_sar_mn"])
    by_status = {s: float(df.loc[df["status"] == s, "rwa_saving_sar_mn"].sum()) if len(df) else 0.0
                 for s in ("recognisable", "after_action", "to_confirm")}

    # capital at risk: CRM on unregistered collateral
    ci = C.read(lin, "collateral", "col_item", ["exposure_id", "value_sar_mn", "haircut_pct", "registration_status", "book", "type"])
    ci = ci[(ci["book"] == "corporate")]
    ci = ci.assign(net=ci["value_sar_mn"] * (1 - ci["haircut_pct"] / 100))
    unreg = ci[ci["registration_status"] != "Registered"].groupby("exposure_id")["net"].sum()
    allc = ci.groupby("exposure_id")["net"].sum()
    fid = m["facility_id"]
    share_unreg = (fid.map(unreg).fillna(0) / fid.map(allc).replace(0, np.nan)).fillna(0).to_numpy()
    at_risk_rwa = float((crm * share_unreg * rw0).sum())
    at_risk_n = int((share_unreg > 0).sum())

    total = sum(by_status.values())
    rows = sorted(items, key=lambda r: -r["rwa_saving_sar_mn"])[:limit]
    summary = _write(by_cat, by_status, total, k, rwa_tot, at_risk_rwa, at_risk_n, rows)
    kpis = [C.kpi("rwa_saving", "RWA saving found", total, "SAR m", f"{C.pct(total / rwa_tot)} of corporate CRWA"),
            C.kpi("capital_saving", "Capital effect", total * k, "SAR m", f"at {C.pct(k)}"),
            C.kpi("recognisable", "Recognisable now", by_status["recognisable"], "SAR m RWA"),
            C.kpi("after_action", "After an action", by_status["after_action"], "SAR m RWA"),
            C.kpi("at_risk", "RWA at risk (unregistered collateral)", at_risk_rwa, "SAR m", f"{at_risk_n} facilities")]
    limits = [
        "Risk weights follow the collateral domain's col_crwa (internal-rating based standardised-style weights); external "
        "ratings are not in Data Domains, so class changes keyed on ratings are labelled to confirm.",
        "SME status uses obligor revenue from the corporate book; group turnover (which SAMA may require) is not applied.",
        "Guarantee substitution assumes the guarantee is direct, irrevocable and unconditional; the register does not hold its terms.",
        "Undrawn cuts assume the client accepts a lower limit; unconditionally cancellable conversion (CCF "
        f"{C.A('ucc_ccf'):.0%}) is an alternative not counted.",
        "Capital effect is at the capital ratio target; the CET1 ratio uplift needs the bank-wide RWA, which is not in Data Domains.",
    ]
    method = ["Per facility: class change, then undrawn cut, then guarantee substitution, each on the result of the step before.",
              "RWA saving x capital_ratio_target = capital effect.",
              "Capital at risk: CRM x share of the facility's collateral not registered x current RW (not netted from savings)."]
    return C.envelope("rwa", "RWA finder", summary[0], summary, kpis, rows, limits, method, lin,
                      {"by_category": by_cat, "by_status": by_status, "rwa_total_sar_mn": rwa_tot,
                       "at_risk": {"rwa_sar_mn": at_risk_rwa, "capital_sar_mn": at_risk_rwa * k, "facilities": at_risk_n}})


def _write(by_cat, by_status, total, k, rwa_tot, at_risk, at_risk_n, rows) -> list[str]:
    if total <= 0:
        return ["No capital saving found in the corporate book on the current registers."]
    out = [f"The book carries {C.sar(total, 0)} of RWA it could save ({C.pct(total / rwa_tot)} of corporate CRWA), "
           f"{C.sar(total * k)} of capital at {C.pct(k)}; {C.sar(by_status['recognisable'], 0)} is recognisable now."]
    top = by_cat[:3]
    out.append("Largest sources: " + "; ".join(f"{c['label']} {C.sar(c['rwa_saving_sar_mn'], 0)} on {c['facilities']} facilities"
                                              for c in top) + ".")
    if rows:
        r = rows[0]
        out.append(f"Biggest single item: {r['borrower_name']} {r['facility_id']}, {r['detail']}, saving "
                   f"{C.sar(r['rwa_saving_sar_mn'])} RWA.")
    if by_status["after_action"] > 0:
        out.append(f"{C.sar(by_status['after_action'], 0)} needs an action first (perfect guarantees, cut unused limits); "
                   f"{C.sar(by_status['to_confirm'], 0)} needs a classification check.")
    if at_risk > 0:
        out.append(f"Watch the other way: {C.sar(at_risk, 0)} of RWA relief rests on collateral not yet registered "
                   f"({at_risk_n} facilities).")
    return out[:5]
