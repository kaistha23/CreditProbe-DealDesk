"""The method appendix of the Deal Desk Word report (PLAN_R5 D6, screen 09).

For every metric and every chart: the formula, the inputs with their values for this deal, the parameter
tables used (owner, version) and a worked line with this deal's numbers. It follows docs/v5/DEALDESK_METHOD.md
section by section. Every value comes from the engine calls of the report (`gather`): the analysis of the
structure the report recommends, the parameter tables, the tornado, the grid and the optimisation.

`entries(g)` returns plain data (title, formula, inputs, parameters, worked, note) so the Word builder, the
Playbook section and the tests read one source.
"""
from __future__ import annotations

from typing import Any

from backend.dealdesk import fmt

pct, sar, bps, times, num = fmt.pct, fmt.sar, fmt.bps, fmt.times, fmt.num


def _par(g: dict[str, Any], *names: str) -> list[dict[str, str]]:
    tabs = {t["name"]: t for t in g.get("param_tables", [])}
    return [{"table": n, "owner": tabs.get(n, {}).get("owner", ""), "version": tabs.get(n, {}).get("version", "")} for n in names]


def entries(g: dict[str, Any]) -> list[dict[str, Any]]:
    cur = g["cur"]
    t, m, r = cur["terms"], cur["metrics"], cur["rates"]
    s1 = cur["schedule"][0]
    p1 = cur["pnl"][0]
    c1 = cur["capital"]["by_year"][0]
    lg = cur["lgd"]
    pdx = cur["pd"] or {}
    T = len(cur["pnl"])
    A = m["amount_sar_mn"]
    held = m.get("held_sar_mn", A)
    hurdle = m["hurdle"]
    B1, O1, U1 = s1["drawn_start"], s1["unfunded_avg"], s1["undrawn_avg"]
    cov = (pdx.get("covenant_overlay") or {})
    lv = cur.get("levers") or {}
    out: list[dict[str, Any]] = []

    def add(title: str, formula: str, inputs: list[tuple[str, str]], params: list[dict[str, str]], worked: str, note: str = "") -> None:
        out.append({"title": title, "formula": formula, "inputs": [{"name": a, "value": b} for a, b in inputs],
                    "parameters": params, "worked": fmt.tidy(worked), "note": note})

    # ---- exposure
    add("Exposure at default (EAD) and CCF",
        "EAD_t = drawn B_t + CCF_econ(undrawn) × undrawn_t + CCF_econ(type) × unfunded O_t",
        [("Facility amount", sar(A)), ("Held by the bank (hold level)", f"{sar(held)} ({pct(lv.get('hold', 1))})"),
         ("Drawn, year 1", sar(B1)), ("Undrawn, year 1", sar(U1)), ("Unfunded outstanding, year 1", sar(O1))],
        _par(g, "ccf"),
        f"EAD year 1 = {sar(B1)} + CCF × {sar(U1)} + CCF × {sar(O1)} = {sar(s1['ead'])}.")
    rec = lg.get("collateral_recognised_sar_mn", 0.0)
    coll = "; ".join(f"{c['type'].replace('_', ' ')} {sar(c['value_sar_mn'])} × (1 − {pct(c['haircut'])}) × 1.08^−{num(c['recovery_years'])}"
                     f" = {sar(c['recognised_sar_mn'])}" for c in lg.get("collateral", [])) or "none"
    add("Loss given default (LGD)",
        "LGD_t = max(floor, max(0, EAD_t − R) / EAD_t × unsecured LGD × structure × covenant); "
        "R = Σ collateral × (1 − haircut) × (1 + 8%)^−recovery years + cash margin",
        [("Unsecured LGD", pct(lg["unsecured"])), ("Floor", pct(lg["floor"])), ("Structure multiplier", times(lg["structure_multiplier"])),
         ("Covenant LGD multiplier", times(lg["covenant_multiplier"])), ("Collateral items", coll),
         ("Cash margin", sar(lg.get("cash_margin_sar_mn", 0.0))), ("Recognised recovery R", sar(rec))],
        _par(g, "lgd", "covenant_packages", "covenant_items", "credit_protection"),
        f"LGD year 1 = max({pct(lg['floor'])}, max(0, {sar(s1['ead'])} − {sar(rec)}) / {sar(s1['ead'])} × {pct(lg['unsecured'])} × "
        f"{times(lg['structure_multiplier'])} × {times(lg['covenant_multiplier'])}) = {pct(m['lgd_y1'])}.")
    ts = pdx.get("term_structure") or []
    add("PD term structure",
        "Marginal PD_t = model hazard h_t × survival_{t−1} × covenant PD multiplier (years 1–5 from the What-If XGBoost model, "
        "50/20/30 base/upturn/downturn; later years: year-5 hazard × the migration matrix's shape); cumulative = Σ marginal",
        [("Model", str(pdx.get("model_version", ""))), ("Model PD, 12 months", pct(pdx.get("model_pd_12m"))),
         ("Master-scale PD (comparison)", pct(pdx.get("master_scale_pd_12m"))),
         ("Covenant PD multiplier", times(cov.get("pd_multiplier", 1.0))),
         ("Marginal PD by year", ", ".join(f"Y{x['year']} {pct(x['marginal'])}" for x in ts)),
         ("Cumulative PD at maturity", pct(ts[-1]["cumulative"]) if ts else "–")],
        _par(g, "pd_master_scale", "pd_migration", "covenant_packages", "covenant_items"),
        f"Year 1: model marginal {pct(ts[0]['model_marginal']) if ts else '–'} × {times(cov.get('pd_multiplier', 1.0))} = "
        f"{pct(ts[0]['marginal']) if ts else '–'}; cumulative over {T} years {pct(ts[-1]['cumulative']) if ts else '–'}.",
        note="Deal terms never enter the model; the out-of-range check and the monotonicity log are in the model card.")
    gtee = lg.get("guarantee")
    ins = lg.get("insurance")
    add("Expected loss (EL)",
        "EL_t = EAD_t × [(1 − c − i) × PD_t × LGD_t + c × min(PD_t LGD_t, PD_g,t LGD_g) + i × min(PD_t LGD_t, PD_ins,t LGD_ins)]; "
        "lifetime EL = Σ EL_t (undiscounted) and its present value at the hurdle",
        [("Guarantee cover c", pct(gtee["coverage"]) if gtee else "0%"),
         ("Guarantor", f"{gtee['guarantor']} ({gtee['rating']}), LGD {pct(gtee['lgd'])}" if gtee else "None"),
         ("Credit insurance cover i", pct(ins["cover"]) if ins else "0%"), ("EAD year 1", sar(s1["ead"])),
         ("PD year 1", pct(m["pd_12m"])), ("LGD year 1", pct(m["lgd_y1"]))],
        _par(g, "lgd", "credit_protection", "pd_migration"),
        f"EL year 1 = {sar(s1['ead'])} × {pct(m['pd_12m'])} × {pct(m['lgd_y1'])}"
        + (" (on the uncovered share; the covered share at the lower loss rate)" if (gtee or ins) else "")
        + f" = {sar(m['el_y1'])}; lifetime {sar(m['el_lifetime'])}, PV {sar(m['el_lifetime_pv'])}; day-one Stage 1 ECL {sar(m['day_one_ecl'])}.",
        note="Economic view: EL is the credit cost. The accounting view replaces it by the day-one ECL plus the allowance change; never both.")
    # ---- capital
    add("Risk-weighted assets (RWA)",
        "RWA_t = max(0, SA exposure_t − eligible cash) × [(1 − c − i) × RW + c × min(RW, RW_g) + i × min(RW, RW_ins)]; "
        "SA exposure_t = B_t + CCF_reg × undrawn_t + CCF_reg × O_t",
        [("Obligor risk weight", pct(cur["capital"]["rw_obligor"])), ("SA exposure, year 1", sar(c1["exposure_sa"])),
         ("Cash margin (eligible)", sar(lg.get("cash_margin_sar_mn", 0.0)))],
        _par(g, "sa_risk_weights", "ccf", "credit_protection"),
        f"RWA year 1 = {sar(c1['exposure_sa'])} less eligible cash × {pct(cur['capital']['rw_obligor'])} (with substitution) = {sar(c1['rwa'])}; "
        f"density {pct(m.get('rwa_density_y1'))}.")
    add("Capital",
        "Capital_t = basis(regulatory RWA_t × 13.5%, economic EAD_t × IRB K(TTC PD, LGD_t, M_t), or the larger) + 15% × gross income_t",
        [("Capital basis", str(cur["capital"]["basis"])), ("Capital ratio target", pct(cur["capital"]["capital_ratio"])),
         ("TTC PD (master scale)", pct(pdx.get("ttc_pd"))), ("Maturity M, year 1", f"{num(c1['maturity'])} years")],
        _par(g, "capital", "pd_master_scale"),
        f"Year 1: regulatory {sar(c1['regulatory'])}, economic {sar(c1['economic'])}, operational {sar(c1['operational'])}; "
        f"capital = {sar(c1['capital'])}.")
    # ---- P&L lines
    add("Profit income",
        "Profit income_t = B_t × (client base rate + margin); floating: 3M SAIBOR/SOFR; fixed: swap at tenor",
        [("Base rate", pct(r["base"])), ("Margin", bps(t["margin_bps"])), ("Rate type", str(r.get("rate_type", "floating")))],
        _par(g, "ftp"),
        f"Year 1 = {sar(B1)} × ({pct(r['base'])} + {pct(r['margin'])}) = {sar(p1['profit_income'])}.")
    add("Fees",
        "Fees_t = (upfront × held amount + arranger skim × sold share) × (B_t + O_t) / Σ(B + O) + commitment fee × undrawn_t "
        "+ commission × O_t + prepayment fee × CPR × B_t",
        [("Upfront fee", bps(t["upfront_fee_bps"])), ("Commitment fee", bps(t["commitment_fee_bps"])), ("Commission", bps(t["commission_bps"])),
         ("Prepayment fee", bps(t.get("prepayment_fee_bps", 0))), ("Expected prepayment rate (CPR)", pct(r.get("prepayment_cpr", 0.0))),
         ("Arranger skim on sold share", sar(lv.get("arranger_skim_sar_mn", 0.0)))],
        _par(g, "market_bounds", "pricing_behaviour"),
        f"Year 1 = {sar(p1['fee_income'])} fees + {sar(p1['commitment_fee'])} commitment + {sar(p1['commission'])} commission = "
        f"{sar(p1['fee_income'] + p1['commitment_fee'] + p1['commission'])}.")
    add("Funds transfer pricing (FTP)",
        "FTP_t = B_t × (base + liquidity premium at tenor + ALM fixed-rate premium) + contingent charges on undrawn and unfunded",
        [("Base", pct(r["base"])), ("Liquidity premium", pct(r["liquidity_premium"])), ("ALM premium", pct(r.get("alm_premium", 0.0)))],
        _par(g, "ftp", "pricing_behaviour"),
        f"Year 1 = {sar(B1)} × ({pct(r['base'])} + {pct(r['liquidity_premium'])} + {pct(r.get('alm_premium', 0.0))}) + contingent = {sar(p1['ftp'])}.")
    add("Operating cost (opex)",
        "Opex_t = servicing fixed + servicing bps × (B_t + O_t) + covenant and review monitoring + insurance premium; "
        "year 1 adds origination fixed + origination bps × held amount",
        [("Monitoring p.a.", sar(lv.get("monitoring_sar_mn_pa", 0.0))), ("Covenant package", str(t["covenant_package"])),
         ("Review cycle", str(lv.get("review_cycle", "Annual review")))],
        _par(g, "opex", "covenant_items", "credit_protection"),
        f"Year 1 = {sar(p1['opex'])} (of which insurance premium {sar(p1.get('insurance_premium', 0.0))}).")
    zr = (p1["zakat"] / (p1["rap"] + p1["zakat"])) if (p1["rap"] + p1["zakat"]) else 0.10
    add("Zakat", "Zakat_t = zakat rate × pre-zakat profit_t", [("Zakat rate", pct(zr))], _par(g, "returns"),
        f"Year 1 = {pct(zr)} × {sar(p1['rap'] + p1['zakat'])} = {sar(p1['zakat'])}.")
    add("Capital benefit", "Capital benefit_t = capital_t × 5.0% (return credited on allocated capital)",
        [("Capital, year 1", sar(p1["capital"]))], _par(g, "returns"),
        f"Year 1 = {sar(p1['capital'])} × 5.0% = {sar(p1['capital_benefit'])}.")
    add("Risk-adjusted profit (RAP)",
        "RAP_t = profit income + fees − FTP − opex − credit cost + capital benefit − zakat",
        [], _par(g, "returns"),
        f"Year 1 = {sar(p1['profit_income'])} + {sar(p1['fee_income'] + p1['commitment_fee'] + p1['commission'])} − {sar(p1['ftp'])} − "
        f"{sar(p1['opex'])} − {sar(p1['credit_cost'])} + {sar(p1['capital_benefit'])} − {sar(p1['zakat'])} = {sar(p1['rap'])}.")
    add("Lifetime RAROC",
        "RAROC = Σ DF_t × RAP_t / Σ DF_t × Capital_t, DF_t = (1 + hurdle)^−t",
        [("Hurdle", pct(hurdle)), ("PV risk-adjusted profit", sar(m["pv_rap"])), ("PV capital", sar(m["pv_capital"]))],
        _par(g, "returns"),
        f"RAROC = {sar(m['pv_rap'])} / {sar(m['pv_capital'])} = {pct(m['lifetime_raroc'])} against the {pct(hurdle)} hurdle; "
        f"relationship RAROC {pct(m['relationship_raroc'])} (ancillary income after realisation).")
    add("Shareholder value added (SVA)",
        "SVA = Σ DF_t × (RAP_t − hurdle × Capital_t); the bar is SVA ≥ 0",
        [("Hurdle", pct(hurdle))], _par(g, "returns"),
        f"SVA = {sar(m['pv_rap'])} − {pct(hurdle)} × {sar(m['pv_capital'])} = {sar(m['sva'])}.")
    if g["ask"]["metrics"].get("breakeven_margin_bps") is not None:
        add("Breakeven margin", "The margin with SVA = 0, other terms as asked (SVA is affine in the margin; secant to 1e-10)",
            [("Ask margin", bps(g["p"]["ask"]["margin_bps"]))], _par(g, "returns"),
            f"Breakeven = {bps(g['ask']['metrics']['breakeven_margin_bps'])} against {bps(g['p']['ask']['margin_bps'])} asked.")
    # ---- charts
    wf = cur["waterfall"]
    add("Chart: RAROC waterfall",
        "Each bar is the present value at the hurdle of one P&L line over the life, signed as it hits profit; the last bar is PV(RAP)",
        [(w["step"], sar(w["value"])) for w in wf], _par(g, "returns"),
        " ".join(f"{w['step']} {sar(w['value'])};" for w in wf[:-1]) + f" total {sar(wf[-1]['value'])}.")
    hm = g.get("heatmap")
    if hm:
        add("Chart: iso-RAROC heatmap",
            f"Each cell = lifetime RAROC from a full engine run at that {'commission' if hm.get('x') == 'commission_bps' else 'margin'} × tenor, "
            "every other term as in the structure; the dashed contour is RAROC = hurdle; × marks the ask",
            [("Commissions" if hm.get("x") == "commission_bps" else "Margins", ", ".join(bps(x) for x in hm["x_values"])), ("Tenors", ", ".join(f"{num(y)}y" for y in hm["y_values"]))],
            _par(g, "returns", "ftp"),
            f"At the structure's {'commission' if hm.get('x') == 'commission_bps' else 'margin'} and tenor the cell reads {pct(m['lifetime_raroc'])}; cells at or above {pct(hurdle)} clear.")
    tor = g.get("tornado")
    if tor:
        add("Chart: lever tornado",
            "Each bar = lifetime RAROC with one lever moved down and up (others fixed); bars sorted by span",
            [(b["lever"], f"{pct(b['low'])} to {pct(b['high'])}") for b in tor["bars"]], _par(g, "market_bounds", "pricing_behaviour", "credit_protection"),
            f"Base {pct(tor['base_raroc'])}; the widest bar is {tor['bars'][0]['lever']} ({pct(tor['bars'][0]['low'])} to {pct(tor['bars'][0]['high'])}).")
    curve = g.get("amount_curve")
    if curve:
        add("Chart: RAROC against amount",
            "Lifetime RAROC from a full engine run at each amount, other terms fixed; the dashed line is the hurdle",
            [(f"{num(x)}m", pct(v)) for x, v in zip(curve["x_values"], curve["values"])], _par(g, "returns"),
            f"At the structure's amount, {pct(m['lifetime_raroc'])}.")
    o = g.get("opt")
    if o:
        fr = o.get("frontier") or []
        w = o.get("weights") or {}
        add("Chart: Pareto frontier",
            "Points are verified engine solutions that clear the hurdle and every hard limit; a point is kept if no other is both closer "
            "to the ask and higher in SVA. Distance = Σ weight × normalised change (amount cut / ask, tenor cut / ask tenor, margin "
            "increase / market range, added collateral and cash / amount, fee increases / 100 bps)",
            [("Weights", ", ".join(f"{k} {num(v)}" for k, v in w.items())), ("Frontier points", fmt.count(len(fr)))],
            _par(g, "market_bounds", "risk_appetite"),
            (f"Closest to ask: distance {num(o['closest']['distance'])}, SVA {sar(o['closest']['metrics']['sva'])}; "
             f"maximum value: SVA {sar(o['max_sva']['metrics']['sva'])}." if o.get("closest") and o.get("max_sva")
             else "No structure clears; the minimum relaxation per lever is reported instead."))
    else:
        w = (g.get("meta") or {}).get("default_weights") or {}
        add("Chart: Pareto frontier",
            "Points are verified engine solutions that clear the hurdle and every hard limit; a point is kept if no other is both closer "
            "to the ask and higher in SVA. Distance = Σ weight × normalised change (amount cut / ask, tenor cut / ask tenor, margin "
            "increase / market range, added collateral and cash / amount, fee increases / 100 bps)",
            [("Default weights", ", ".join(f"{k} {num(v)}" for k, v in w.items()) or "amount 5, tenor 4, margin 3, collateral 2, fees 1")],
            _par(g, "market_bounds", "risk_appetite"),
            f"The ask is at distance 0 with SVA {sar(g['ask']['metrics']['sva'])}; the frontier is drawn once the thread is optimised.")
    al = g.get("alts")
    if al and al.get("alternatives"):
        a0 = al["alternatives"][0]
        add("Chart: why each alternative works (lever contributions)",
            "Each bar is the Shapley contribution of one changed lever to the RAROC gain from the ask: the average, over every order of "
            "applying the changes, of the RAROC change when that lever is applied; the bars add up to the total gain",
            [(c["label"], f"{pct(c['raroc_pts'], signed=True)} RAROC") for c in a0["contributions"]], _par(g, "pricing_behaviour", "credit_protection"),
            f"{a0['label']}: RAROC {pct(g['ask']['metrics']['lifetime_raroc'])} → {pct(a0['metrics']['lifetime_raroc'])}.")
    st = g["stress"]
    add("Stress",
        "Each scenario reruns the full engine: rating −1/−2 notches (PD, TTC PD and rating-based limits), collateral value −20%/−30%, "
        "SAIBOR +200 bps (client DSCR on deal and existing debt), utilisation 100% with CCF +25 pts; robustness = notches of downgrade "
        "before RAROC falls below the hurdle",
        [(x["label"], f"RAROC {pct(x['lifetime_raroc'])}, SVA {sar(x['sva'])}") for x in st["rows"]], _par(g, "stress"),
        f"Robust to {st['robustness_notches']} notches of downgrade.")
    return out


__all__ = ["entries"]
