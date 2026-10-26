"""K4: the Stage 3 wholesale provision floor (CRM-9.23) explained, from the facilities behind the check.

The check (backend.regulatory.crm_checks.c_stage3_floor_wholesale) computes per Stage 3 facility: EAD, the secured
value after the Table 4 haircut for its months in Stage 3 (Art. 10.8; only the collateral types Table 4 lists count),
the unsecured portion, and the floor (Art. 9.23): 25% of the unsecured portion up to 48 months in Stage 3, then 100%
of the unsecured portion plus 25% of the secured portion. A facility breaches when ECL < floor.

This view re-uses the check's own arithmetic and adds, per facility, the same floor computed with the bank's OWN
haircuts and without the 4-year step-up, so the shortfall can be laid out in layers (the "bridge"):

    floor = base layer (25% of the unsecured portion, bank's own haircuts)
          + step-up layer (after 48 months: the rest of the unsecured portion + 25% of the secured)
          + haircut layer (the floor added by applying the Table 4 haircut instead of the bank's own)

The bank's ECL is laid against the layers from the bottom up; what it leaves uncovered in each layer is that driver's
share of the shortfall. Two reassignments follow, each stated: a facility held in Stage 3 for more than 60 months has
its whole shortfall shown as "held over 5 years, not written off" (Art. 12.5: it should have left the balance sheet),
and the part of the haircut layer resting on collateral valued longer ago than Art. 10.11 allows is shown as "stale
valuation". The base-layer shortfall is the bank's LGD below the floor on the unsecured portion. The drivers sum to
the check's total shortfall exactly (tested).
"""
from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from backend.agents_v5.brief import readers as R
from backend.agents_v5.brief.items import fmt
from backend.regulatory import crm_checks as C
from backend.regulatory.issues import common as K

CHECK_ID = "CRM-9.23"
ISSUE_ID = f"crm:{CHECK_ID}"
VINTAGES = (("lt1", "Under 1 year", 0, 11), ("1to2", "1–2 years", 12, 23), ("2to4", "2–4 years", 24, 48),
            ("ge4", "Over 4 years (step-up applies)", 49, 10 ** 6))
DRIVERS = {
    "stepup": ("4-year step-up not applied", "Art. 9.23: after 48 months in Stage 3 the floor is 100% of the "
               "unsecured portion plus 25% of the secured; the provision stayed near the first-4-years level.", ""),
    "haircut": ("Collateral haircut below Table 4", "Art. 10.8: after 48 months real estate and guarantees take at least "
                "80% (100% after 60); the bank's own 25–40% haircuts count more collateral than the rule allows.",
                "crm:CRM-10.8"),
    "stale": ("Stale collateral valuation", "Art. 10.11: Stage 3 real estate valued in the last 12 months (motor "
              "vehicles 6); collateral valued earlier cannot support the provision.", "crm:CRM-10.11"),
    "lgd": ("LGD model below the floor on unsecured lending", "The bank's own Stage 3 LGD leaves less than 25% of the "
            "unsecured portion provided.", ""),
    "writeoff": ("Held over 5 years, not written off", "Art. 12.5: a Stage 3 exposure is written off after 5 years "
                 "unless the Board signs an exception; it still sits on the balance sheet under-provided.",
                 "crm:CRM-12.5"),
}


SHORT = {"stepup": "Step-up", "haircut": "Haircut", "stale": "Stale valuation", "lgd": "LGD model",
         "writeoff": "Not written off"}


def _vintage(m: int) -> str:
    for key, _lab, lo, hi in VINTAGES:
        if lo <= m <= hi:
            return key
    return "ge4"


def facilities(period: str | None = None) -> tuple[pd.DataFrame, str]:
    """Every Stage 3 corporate facility with the check's floor and the layers of the bridge."""
    ctx = C.context("corporate", period)
    s3 = ctx.fac[ctx.fac["stage"] == 3].copy()
    months = {r["facility_id"]: C._months_in_stage3(ctx, r) for _, r in s3.iterrows()}
    col = ctx.collateral[ctx.collateral["facility_id"].isin(s3["facility_id"])] if ctx.collateral is not None else None
    reg: dict[str, float] = {}
    own: dict[str, float] = {}
    stale_own: dict[str, float] = {}
    mv_by_type: dict[str, dict[str, float]] = {}
    hc_gap: dict[str, int] = {}
    if col is not None:
        for _, c in col.iterrows():
            fid = c["facility_id"]
            mv = float(c["market_value_sar_mn"])
            mv_by_type.setdefault(fid, {})
            mv_by_type[fid][c["collateral_type"]] = mv_by_type[fid].get(c["collateral_type"], 0.0) + mv
            need = C._haircut_min(c["collateral_type"], months.get(fid, 0))
            if need is None:
                continue  # not in Table 4: evaluated case by case, not counted as secured (as the check does)
            o = float(c["haircut_pct"]) if not pd.isna(c.get("haircut_pct")) else 0.0
            reg[fid] = reg.get(fid, 0.0) + mv * (1 - max(need, o) / 100)
            own[fid] = own.get(fid, 0.0) + mv * (1 - o / 100)
            if o + 1e-9 < need:
                hc_gap[fid] = hc_gap.get(fid, 0) + 1
            lim = C.VALUATION_MAX_MONTHS.get(c["collateral_type"])
            if lim is not None and float(c["valuation_age_months"]) > lim:
                stale_own[fid] = stale_own.get(fid, 0.0) + mv * (1 - o / 100)
    rows = []
    for _, r in s3.iterrows():
        fid, ead, ecl, m = r["facility_id"], float(r["ead_sar_mn"]), float(r["ecl_sar_mn"]), months[r["facility_id"]]
        s_reg, s_own = min(ead, reg.get(fid, 0.0)), min(ead, own.get(fid, 0.0))
        u_reg, u_own = ead - s_reg, ead - s_own
        floor = 0.25 * u_reg if m <= 48 else u_reg + 0.25 * s_reg
        floor_own = 0.25 * u_own if m <= 48 else u_own + 0.25 * s_own
        base = 0.25 * u_own
        layers = {"lgd": base, "stepup": floor_own - base, "haircut": floor - floor_own}
        short = floor - ecl if ecl + 1e-9 < floor else 0.0
        part = {k: 0.0 for k in DRIVERS}
        if short > 0:
            cover = ecl
            for k in ("lgd", "stepup", "haircut"):
                take = min(max(cover, 0.0), layers[k])
                part[k] = layers[k] - take
                cover -= take
            if m > C.WRITE_OFF_YEARS * 12:
                part = {k: 0.0 for k in DRIVERS} | {"writeoff": short}
            elif stale_own.get(fid) and own.get(fid):
                moved = part["haircut"] * min(1.0, stale_own[fid] / own[fid])
                part["haircut"] -= moved
                part["stale"] = moved
            # Close the float residue on the largest part so each facility's parts sum to its shortfall.
            gap = short - sum(part.values())
            if abs(gap) > 0:
                kmax = max(part, key=lambda k: part[k])
                part[kmax] += gap
        types = mv_by_type.get(fid, {})
        main_type = max(types, key=lambda t: (types[t], t)) if types else "Unsecured"
        rows.append({"facility_id": fid, "borrower_id": r["borrower_id"], "ead": ead, "ecl": ecl, "months": m,
                     "vintage": _vintage(m), "secured": s_reg, "secured_own": s_own, "unsecured": u_reg,
                     "floor": floor, "shortfall": short, "breach": short > 0, "collateral_type": main_type,
                     "haircut_gaps": hc_gap.get(fid, 0), **{f"d_{k}": v for k, v in part.items()}})
    cols = ["facility_id", "borrower_id", "ead", "ecl", "months", "vintage", "secured", "secured_own", "unsecured",
            "floor", "shortfall", "breach", "collateral_type", "haircut_gaps", *[f"d_{k}" for k in DRIVERS]]
    return pd.DataFrame(rows, columns=cols), ctx.period


def _model_lgd(ids: list[str], period: str) -> tuple[float | None, dict[str, Any]]:
    """EAD-weighted LGD the bank's model gives these facilities (cockpit.corp_facility_quarter.lgd_pct)."""
    if not ids:
        return None, {}
    num_, den = 0.0, 0.0
    for part in K._chunks(sorted(ids)):
        ph = ", ".join("?" for _ in part)
        r = R.read("cockpit", "corp_facility_quarter", columns="sum(lgd_pct * ead_sar_mn) AS w, sum(ead_sar_mn) AS e",
                   where=f"facility_id IN ({ph}) AND reporting_quarter = ?", args=[*part, period])
        if r.rows:
            num_ += float(r.rows[0].get("w") or 0.0)
            den += float(r.rows[0].get("e") or 0.0)
    v = num_ / den if den else None
    if v is not None and v <= 1.0:
        v *= 100.0
    return (round(v, 2) if v is not None else None,
            K.src("cockpit", "corp_facility_quarter", {"facility_id": f"{len(ids)} breaching facilities"}, "lgd_pct",
                  period, "EAD-weighted mean"))


def comparison(df: pd.DataFrame) -> dict[str, Any]:
    b = df[df["breach"]]
    ead, ecl, fl = float(b["ead"].sum()), float(b["ecl"].sum()), float(b["floor"].sum())
    bank = K.pct(ecl, ead) or 0.0
    req = K.pct(fl, ead) or 0.0
    n, sf = int(len(b)), float(b["shortfall"].sum())
    return {"n": n, "ead": ead, "ecl": ecl, "floor": fl, "shortfall": sf, "bank_pct": bank, "req_pct": req,
            "sentence": (f"Bank holds Stage 3 LGD of {bank:.1f}% (ECL ÷ EAD, PD = 1) against a regulatory minimum of "
                         f"{req:.1f}% (floor ÷ EAD) on {n:,} exposures: {fmt(sf, 'SAR mn')} short.")}


def line(period: str | None = None) -> str:
    """The brief line (K4 (1)): both rates named."""
    df, _ = facilities(period)
    return comparison(df)["sentence"]


def _band_rows(df: pd.DataFrame, key: str, labels: list[tuple[str, str]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    out = []
    for k, lab in labels:
        g = df[df[key] == k]
        if g.empty:
            continue
        out.append(_agg(g, lab))
    return out, _agg(df, "All Stage 3")


def _agg(g: pd.DataFrame, lab: str) -> dict[str, Any]:
    ead, ecl, fl = float(g["ead"].sum()), float(g["ecl"].sum()), float(g["floor"].sum())
    return {"name": lab, "n": int(len(g)), "n_breach": int(g["breach"].sum()), "ead": K.r2(ead),
            "bank_lgd_pct": K.pct(ecl, ead), "floor_pct": K.pct(fl, ead), "shortfall": K.r2(g["shortfall"].sum())}


COLS = [("name", "", "text"), ("n", "Stage 3", "n"), ("n_breach", "Below floor", "n"),
        ("ead", "EAD", "SAR mn"), ("bank_lgd_pct", "Bank LGD", "%"),
        ("floor_pct", "Floor", "%"), ("shortfall", "Shortfall", "SAR mn")]
COL_NOTE = ("Stage 3 = facilities in Stage 3; Below floor = those whose ECL is under the floor; Bank LGD = ECL ÷ EAD "
            "(PD = 1 in Stage 3); Floor = the Art. 9.23 floor ÷ EAD. ")


def view(today: date | None = None, period: str | None = None) -> dict[str, Any]:
    today = today or date.today()
    df, period = facilities(period)
    ck = C.BY_ID[CHECK_ID]
    cmp_ = comparison(df)
    b = df[df["breach"]].copy()
    if b.empty:  # nothing below the floor: the compliant view, not a SAR 0 top-up
        from backend.regulatory.issues import checks
        return checks._empty(ck, "corporate", period)
    model_lgd, model_src = _model_lgd(list(b["facility_id"]), period)
    s_crm = K.src("regulatory", "crm_breach", {"check_id": CHECK_ID, "book": "corporate"}, "shortfall_sar_mn", period)
    s_fac = K.src("cockpit", "corp_facility_quarter", {"stage": 3, "reporting_quarter": period}, "ecl_sar_mn", period)
    s_col = K.src("cockpit", "corp_collateral_quarter", {"reporting_quarter": period}, "haircut_pct", period)

    # Bank vs floor, by vintage and by collateral type (all Stage 3, so the compliant years show too).
    vint, vtot = _band_rows(df, "vintage", [(k, lab) for k, lab, _a, _b in VINTAGES])
    types = sorted(df["collateral_type"].unique(), key=lambda t: (-float(df[df["collateral_type"] == t]["shortfall"].sum()), t))
    ctyp, ctot = _band_rows(df, "collateral_type", [(t, t) for t in types])
    tables = [K.table("by_vintage", "Bank vs floor by time in Stage 3", COLS, vint, vtot,
                      COL_NOTE + "Every Stage 3 facility; the floor steps up after 48 months."),
              K.table("by_collateral", "Bank vs floor by main collateral type", COLS, ctyp, ctot,
                      COL_NOTE + "Main type = the largest collateral item by market value. Receivables, plant and equipment and "
                      "cash are not in Table 4 and count as unsecured for the floor (Art. 10.8).")]

    # The bridge.
    steps = []
    for k in ("stepup", "haircut", "stale", "lgd", "writeoff"):
        lab, why, link = DRIVERS[k]
        g = b[b[f"d_{k}"] > 1e-9]
        steps.append({"key": k, "label": lab, "value": float(b[f"d_{k}"].sum()), "explain": why,
                      "facilities": int(len(g)), "ead": K.r2(g["ead"].sum()),
                      "rows": list(g.sort_values(f"d_{k}", ascending=False)["facility_id"].head(10)),
                      "link": {"issue": link, "href": K.issue_href(link)} if link else None,
                      "source": {**s_crm, "method": f"per facility, the uncovered part of the {k} layer"}})
    bridge = K.bridge(f"Where the {fmt(cmp_['shortfall'], 'SAR mn')} comes from", cmp_["shortfall"], steps,
                      "The floor is built in layers (25% of the unsecured portion with the bank's own haircuts; the "
                      "4-year step-up; the extra floor from the Table 4 haircut). The bank's ECL fills the layers from "
                      "the bottom; the uncovered part of each layer is its driver. Facilities over 60 months in Stage 3 "
                      "are shown whole under 'not written off'; the haircut layer on out-of-date valuations under "
                      "'stale valuation'. The parts sum to the check's shortfall.")

    # Exposures, top by shortfall.
    names = K.borrower_names(b["borrower_id"], period)
    bor = K.borrower_frame(period)
    top = b.sort_values(["shortfall", "ead"], ascending=False).head(25)
    exp_rows = []
    for _, r in top.iterrows():
        main = max(DRIVERS, key=lambda k: (r[f"d_{k}"], k))
        exp_rows.append({"facility_id": r["facility_id"], "borrower_id": r["borrower_id"],
                         "name": names.get(r["borrower_id"], r["borrower_id"]),
                         "href": f"/borrower-360?id={r['borrower_id']}",
                         "sector": str((bor.get(r["borrower_id"]) or {}).get("sector") or ""),
                         "years": round(r["months"] / 12, 1), "ead": K.r2(r["ead"]), "secured": K.r2(r["secured"]),
                         "bank_lgd_pct": K.pct(r["ecl"], r["ead"]), "floor_pct": K.pct(r["floor"], r["ead"]),
                         "shortfall": K.r2(r["shortfall"]), "driver": SHORT[main]})
    exposures = K.table("exposures", f"The {min(25, len(b))} largest shortfalls of {len(b):,}",
                        [("name", "Borrower", "text"), ("facility_id", "Facility", "text"),
                         ("years", "Years in S3", ""), ("ead", "EAD", "SAR mn"),
                         ("secured", "Secured", "SAR mn"), ("bank_lgd_pct", "Bank LGD", "%"),
                         ("floor_pct", "Floor", "%"), ("shortfall", "Shortfall", "SAR mn"),
                         ("driver", "Main driver", "text")], exp_rows,
                        note="Secured = collateral after the Table 4 haircut; Bank LGD = ECL ÷ EAD; Floor = floor ÷ EAD.")

    conc = K.concentration(b.to_dict("records"), "shortfall", period, label="Shortfall")
    impact = K.impact_rows(cmp_["shortfall"])

    by_v = {r["name"]: r for r in vint}
    old = by_v.get("Over 4 years (step-up applies)") or {}
    step = {s["key"]: s for s in bridge["steps"]}
    hc_n = int((b["haircut_gaps"] > 0).sum())
    wo = b[b["d_writeoff"] > 0]
    old_sf = float(old.get("shortfall") or 0.0)
    where = ("all of it on facilities over 4 years in Stage 3" if abs(old_sf - cmp_["shortfall"]) < 0.01 else
             f"{fmt(old_sf, 'SAR mn')} of it on facilities over 4 years in Stage 3")
    actions = [K.action(1, f"Top up Stage 3 provisions by {fmt(cmp_['shortfall'], 'SAR mn')} before the quarter's ECL "
                           f"run, {where}",
                        "provisioning", today, 21, "The floor is a minimum; until it is met the book breaches Art. 9.23.",
                        K.fig("Top-up", K.r2(cmp_["shortfall"]), "SAR mn", s_crm))]
    if hc_n:
        actions.append(K.action(len(actions) + 1, f"Re-haircut the collateral on {hc_n:,} facilities to Table 4 (80% "
                                f"after 48 months, 100% after 60) and record the case-by-case value of receivables",
                                "collateral", today, 45, "The bank's own haircuts count more collateral than Art. 10.8 "
                                "allows.", K.fig("Shortfall from haircuts", step["haircut"]["value"], "SAR mn", s_crm),
                                {"label": "CRM-10.8 issue", "href": K.issue_href("crm:CRM-10.8")}))
    actions.append(K.action(len(actions) + 1, "Raise an LGD model change request: apply the Art. 9.23 floor and the "
                            "4-year step-up as a post-model floor on Stage 3 LGD", "model", today, 90,
                            f"The model's Stage 3 LGD on these facilities averages {model_lgd or 0:.1f}%, below the "
                            f"{cmp_['req_pct']:.1f}% the floor needs." if model_lgd is not None else
                            "The model's Stage 3 LGD sits below the floor.",
                            K.fig("Model LGD", model_lgd, "%", model_src) if model_lgd is not None else None))
    if len(wo):
        actions.append(K.action(len(actions) + 1, f"Put {K.words(len(wo), 'facility', 'facilities')} held over 5 years in Stage 3 "
                                f"({fmt(float(wo['ead'].sum()), 'SAR mn')} EAD) to the Board: write off or sign an "
                                "exception", "board", today, 30, "Art. 12.5(b).",
                                K.fig("EAD over 5 years", K.r2(wo["ead"].sum()), "SAR mn", s_fac),
                                {"label": "CRM-12.5 issue", "href": K.issue_href("crm:CRM-12.5")}))

    shares = sorted(((s["share_pct"] or 0.0, s["label"]) for s in bridge["steps"]), reverse=True)
    lead = shares[0] if shares else (0.0, "")
    headline = (f"{ck.id} ({ck.article.replace(C.PREFIX + ' ', '')}): {len(b):,} Stage 3 facilities with "
                f"{fmt(cmp_['ead'], 'SAR mn')} EAD carry {fmt(cmp_['shortfall'], 'SAR mn')} less provision than the "
                f"wholesale floor at {period}.")
    plain = [
        "This checks that provisions on loans in default meet the regulator's minimum.",
        f"On {len(b):,} loans the bank holds {cmp_['bank_pct']:.0f}% of the balance against a minimum of "
        f"{cmp_['req_pct']:.0f}%: {fmt(cmp_['shortfall'], 'SAR mn')} short.",
        f"{K.lead_phrase(lead[0])} ({lead[0]:.0f}%): {lead[1].lower()}.",
        "Top up provisions now, re-haircut the collateral and set the minimum in the loss model.",
    ]
    return {
        "id": ISSUE_ID, "kind": "provision_floor", "check_id": CHECK_ID, "module": "Regulatory intelligence",
        "title": ck.title, "period": period, "severity": "critical" if cmp_["shortfall"] > 100 else "high",
        "headline": headline, "plain_words": plain,
        "rule": {"article": ck.article, "text": ck.rule, "href": f"{K.POLICY_HREF}&clause={ck.article}",
                 "detail": "Table 4 (Art. 10.8) minimum haircut on real estate and guarantees by months in Stage 3: "
                           "20% up to 24, 40% to 36, 60% to 48, 80% to 60, 100% after 60. Receivables, plant and "
                           "equipment and cash are not in the table."},
        "comparison": {"sentence": cmp_["sentence"],
                       "bank": K.fig("Bank's Stage 3 LGD (ECL ÷ EAD, PD = 1)", cmp_["bank_pct"], "%",
                                     {**s_crm, "column": "ecl_sar_mn ÷ ead_sar_mn"}),
                       "required": K.fig("Regulatory minimum (floor ÷ EAD)", cmp_["req_pct"], "%",
                                         {**s_crm, "column": "(ecl_sar_mn + shortfall_sar_mn) ÷ ead_sar_mn"}),
                       "model": K.fig("Bank's LGD model on the same facilities", model_lgd, "%", model_src)
                       if model_lgd is not None else None,
                       "figures": [K.fig("Exposures", cmp_["n"], "", s_crm), K.fig("EAD", K.r2(cmp_["ead"]), "SAR mn", s_crm),
                                   K.fig("ECL held", K.r2(cmp_["ecl"]), "SAR mn", s_crm),
                                   K.fig("Floor", K.r2(cmp_["floor"]), "SAR mn", s_crm),
                                   K.fig("Shortfall", K.r2(cmp_["shortfall"]), "SAR mn", s_crm)]},
        "tables": tables, "bridge": bridge, "concentration": conc, "impact": impact, "actions": actions,
        "exposures": exposures,
        "source": {"label": "Source: regulatory.crm_breach", "domain": "regulatory", "relation": "crm_breach",
                   "href": f"/data-builder?domain=regulatory&relation=crm_breach&check_id={CHECK_ID}"},
        "cannot_tell": [
            "Recoveries in progress, legal action and restructuring talks are not in the book: a name close to "
            "recovery may justify a Board exception rather than a full top-up.",
            "Receivables, plant and equipment and cash are not in Table 4; they count as unsecured here (Art. 10.8 "
            "says case by case). Valuations the bank holds outside the book could support more.",
            "Valuation age is held in quarters (months = quarters × 3).",
            "Cash collateral is outside Table 4 and the check counts it as unsecured; cash that is pledged and "
            "blocked would lower the floor on those facilities.",
            "The CET1 effect is pre-tax and pre-zakat, on credit RWA only.",
        ],
        "trace": [s_crm, s_fac, s_col, *conc["source"]],
    }
