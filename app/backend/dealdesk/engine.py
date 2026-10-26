"""The Deal Desk engine: one deterministic calculation from a proposal and a term set.

    analyse(proposal, terms, el_view, capital_basis) -> Analysis (docs/v5/DEALDESK_API.md)

Annual buckets t = 1..T, payments at year end, money in SAR million.

  Schedule   funded part: drawn B_t at the start of year t (term loan: fully drawn, grace, then
             equal / bullet / balloon; revolver: limit x utilisation, bullet); unfunded part (LG/LC):
             outstanding O = limit x usage, flat to maturity.
  EAD_t      B_t + CCF_econ(undrawn) x undrawn_t + CCF_econ(type) x O_t
  LGD_t      max(floor, max(0, EAD_t - R) / EAD_t x LGD_unsecured x structure x covenant_lgd)
             R = sum of selected collateral x (1 - haircut) x (1 + r)^-recovery_years + cash margin
  PD_t       marginal PD from the What-If XGBoost model (pd_model) x covenant_pd
  Guarantee  covered share c: EL and economic capital on the guarantor (its master-scale PD and
             LGD); SA risk weight of the guarantor where it is eligible (government, Kafalah, bank)
  EL_t       EAD_t x [(1 - c) PD_t LGD_t + c PD_g,t LGD_g]
  RWA_t      SA: max(0, E_t - cash) x [(1 - c) RW + c RW_g], E_t = B_t + CCF_reg undrawn + CCF_reg O_t
  Capital_t  basis(RWA_t x ratio, IRB-proxy K_t x EAD_t on TTC PD) + alpha x gross income_t
  P&L_t      profit income + fees (upfront amortised by exposure, EIR approximation) + commitment fee
             + commission - FTP - opex - credit cost + capital benefit - zakat = RAP_t
  Metrics    lifetime RAROC = PV(RAP) / PV(capital); SVA = PV(RAP - hurdle x capital), PV at the hurdle
             breakeven margin: SVA is affine in the margin, solved exactly from two evaluations

The credit cost is EL_t (economic view, default) or the accounting view (day-one Stage 1 ECL plus
the expected change in the allowance, Stage 2 migration from the matrix, plus expected write-offs);
the two are never both deducted.
"""
from __future__ import annotations

import copy
import math
from typing import Any

import numpy as np
from scipy.special import ndtr, ndtri

from backend.dealdesk import params, pd_model, portfolio
from backend.dealdesk.seed import GRADES, bucket
from backend.v5common.ratings import rank

TERM_KEYS = ("facility_type", "structure", "currency", "amount", "tenor_years", "grace_years", "amortisation", "balloon_pct",
             "margin_bps", "upfront_fee_bps", "commitment_fee_bps", "commission_bps", "utilisation_pct", "funded_share_pct",
             "unfunded_type", "cash_margin_pct", "collateral_ids", "guarantee_id", "guarantee_coverage_pct", "covenant_package",
             # R5 D4: the rest of the risk manager's levers (neutral values in levers.NEUTRAL)
             "prepayment_fee_bps", "rate_type", "hold_pct", "insurance_cover_pct", "receivables_assignment_pct",
             "covenant_items", "review_cycle_months", "cross_sell",
             # R12-I: rating-linked margin ratchet (Book feedback to origination)
             "margin_ratchet_bps_per_notch",
             # Round D: the Deposit requirement term (backend/dealdesk/deposit_requirement)
             "deposit_type", "deposit_pct", "deposit_amount", "deposit_tenor_months", "deposit_facility")
UNFUNDED = ("performance_lg", "financial_lg", "trade_lc")
Z999 = float(ndtri(0.999))


class TermsError(ValueError):
    def __init__(self, errors: list[dict[str, str]]):
        super().__init__("; ".join(f"{e['field']}: {e['message']}" for e in errors))
        self.errors = errors


def merge_terms(p: dict[str, Any], terms: dict[str, Any] | None) -> dict[str, Any]:
    from backend.dealdesk.levers import NEUTRAL
    t = copy.deepcopy(p["ask"])
    for k, v in NEUTRAL.items():
        t.setdefault(k, copy.deepcopy(v))
    for k, v in (terms or {}).items():
        if k in TERM_KEYS:
            t[k] = v
    for k in ("tenor_years", "grace_years"):
        if isinstance(t.get(k), float) and t[k].is_integer():
            t[k] = int(t[k])
    if t.get("guarantee_id") in ("", "none"):
        t["guarantee_id"] = None
    return t


def _check(p: dict[str, Any], t: dict[str, Any]) -> None:
    from backend.dealdesk.proposals import validate_terms
    e = validate_terms(t)
    rat = t.get("margin_ratchet_bps_per_notch", 0)  # R12-I
    rmax = float(params.rows("pricing_behaviour").get("margin_ratchet_max_bps_per_notch", 0))
    if not isinstance(rat, (int, float)) or isinstance(rat, bool) or not (0 <= rat <= rmax):
        e.append({"field": "terms.margin_ratchet_bps_per_notch", "message": f"a number in [0, {rmax:g}]"})
    ids = {c["collateral_id"] for c in p["security"]["collateral"]}
    for cid in t.get("collateral_ids", []):
        if cid not in ids:
            e.append({"field": "terms.collateral_ids", "message": f"{cid} is not one of the obligor's items {sorted(ids)}"})
    from backend.dealdesk.deposit_requirement.term import check_facility  # Round D
    e += check_facility(p, t)
    if t.get("guarantee_id") and t["guarantee_id"] not in {g["guarantee_id"] for g in p["security"]["guarantees"]}:
        cat = params.rows("credit_protection")["guarantee_catalogue"]
        c = cat.get(t["guarantee_id"])
        if c is None or (c.get("requires_group") and not p["obligor"].get("group_id")):
            e.append({"field": "terms.guarantee_id", "message": f"{t['guarantee_id']} is not one of the obligor's guarantees "
                                                               f"or a requested protection ({', '.join(cat)})"})
    if e:
        raise TermsError(e)


def fx(currency: str) -> float:
    return 1.0 if currency == "SAR" else float(params.rows("capital")["usd_sar"])


def hurdle_for(p: dict[str, Any]) -> float:
    r = params.rows("returns")
    sec = r.get("hurdle_sector", {}).get(p["obligor"]["sector"])
    return float(sec if sec is not None else r["hurdle"].get(p.get("business_unit", "Corporate Banking"), r["hurdle"]["Corporate Banking"]))


def _interp(x: float, xs: list[float], ys: list[float]) -> float:
    return float(np.interp(x, xs, ys))


def latest_actual(p: dict[str, Any]) -> dict[str, Any]:
    ys = [y for y in p["financials"]["years"] if y["kind"] == "actual"]
    return ys[-1]


def irb_k(pd_: float, lgd: float, m: float, ec: dict[str, Any] | None = None) -> float:
    """Basel IRB corporate capital requirement K with the maturity adjustment (the economic-capital proxy).

    Asset correlation R = r_min x w + r_max x (1 - w), w = (1 - e^(-k PD)) / (1 - e^(-k)); confidence,
    correlation bounds, k and the PD floor come from the `capital.economic` parameters."""
    ec = ec or {}
    conf = float(ec.get("confidence", 0.999))
    r_min, r_max, kk = float(ec.get("correlation_min", 0.12)), float(ec.get("correlation_max", 0.24)), float(ec.get("correlation_k", 50.0))
    pd_ = min(max(pd_, float(ec.get("pd_floor", 0.0003))), 0.9999)
    e = (1 - math.exp(-kk * pd_)) / (1 - math.exp(-kk))
    r = r_min * e + r_max * (1 - e)
    b = (0.11852 - 0.05478 * math.log(pd_)) ** 2
    z = Z999 if conf == 0.999 else float(ndtri(conf))
    k = lgd * float(ndtr((ndtri(pd_) + math.sqrt(r) * z) / math.sqrt(1 - r))) - pd_ * lgd
    return max(0.0, k * (1 + (m - 2.5) * b) / (1 - 1.5 * b))


def guarantor_pd(rating: str, years: int) -> np.ndarray:
    mh = pd_model.matrix_hazards(rating, years)
    surv = np.cumprod(1 - mh)
    prev = np.concatenate([[1.0], surv[:-1]])
    return mh * prev


# ------------------------------------------------------------------ the calculation

def analyse(p: dict[str, Any], terms: dict[str, Any] | None = None, el_view: str = "economic",
            capital_basis: str | None = None, shocks: dict[str, Any] | None = None, pd_override: dict[str, Any] | None = None,
            validate: bool = True) -> dict[str, Any]:
    """The full analysis of one term set. `shocks` (stress): notches, collateral_shock, rate_shock_bps,
    utilisation_pct, ccf_add. `pd_override` (golden workbook): {"marginal": [...], "ttc": x} replaces the model.
    `validate=False` is for the engine's own probes (breakeven, tornado), which may step outside the input ranges."""
    t = merge_terms(p, terms)
    if validate:
        _check(p, t)
    sh = shocks or {}
    P = params.current()
    lg, ccf, rw, cap, ftp, opx, ret = (P[k]["rows"] for k in ("lgd", "ccf", "sa_risk_weights", "capital", "ftp", "opex", "returns"))
    cov = P["covenant_packages"]["rows"]
    pb, cpt, cvi, rel = (P[k]["rows"] for k in ("pricing_behaviour", "credit_protection", "covenant_items", "relationship"))
    basis = capital_basis or cap["basis"]
    ob = p["obligor"]
    X = fx(t["currency"])
    A_full = float(t["amount"]) * X
    hold = float(t["hold_pct"]) / 100.0          # sell-down: the bank holds this share of the facility
    A = A_full * hold
    T = int(t["tenor_years"])
    g = int(t["grace_years"])
    years = np.arange(1, T + 1)
    util = float(sh.get("utilisation_pct", t["utilisation_pct"])) / 100.0
    ftype = t["facility_type"]
    f_share = 0.0 if ftype in UNFUNDED else float(t["funded_share_pct"]) / 100.0
    utype = ftype if ftype in UNFUNDED else t["unfunded_type"]
    F, U = A * f_share, A * (1 - f_share)

    # schedule
    drawn = np.zeros(T)
    principal = np.zeros(T)
    undrawn = np.zeros(T)
    if F > 0 and ftype == "term_loan":
        bal = F
        n = T - g
        balloon = (1.0 if t["amortisation"] == "bullet" else float(t["balloon_pct"]) / 100.0 if t["amortisation"] == "balloon" else 0.0)
        if t["amortisation"] == "sculpted":
            # principal sculpted to the obligor's cash-flow growth: weights (1 + g)^k over the amortising years
            w = np.array([(1 + float(pb["sculpt_growth"])) ** k for k in range(n)])
            amort_by = F * w / w.sum()
        else:
            amort_by = np.full(n, F * (1 - balloon) / n)
        for i in range(T):
            drawn[i] = bal
            pay = (amort_by[i - g] if i >= g else 0.0) + (F * balloon if i == T - 1 else 0.0)
            pay = min(pay, bal)
            principal[i] = pay
            bal -= pay
    elif F > 0:  # revolver: limit x utilisation, bullet
        drawn[:] = F * util
        undrawn[:] = F * (1 - util)
        principal[-1] = F * util
        balloon = 1.0
    else:
        balloon = 0.0
    outstanding = np.full(T, U * (util if U > 0 else 0.0))
    ccf_u_econ = min(1.0, ccf["undrawn_committed"]["economic"] + sh.get("ccf_add", 0.0))
    ccf_o_econ = min(1.0, ccf[utype]["economic"] + sh.get("ccf_add", 0.0))
    ead = drawn + ccf_u_econ * undrawn + ccf_o_econ * outstanding

    # collateral and LGD
    cshock = 1.0 + float(sh.get("collateral_shock", 0.0))
    items = {c["collateral_id"]: c for c in p["security"]["collateral"]}
    recog = 0.0
    re_value = 0.0
    coll_rows = []
    for cid in t.get("collateral_ids", []):
        c = items[cid]
        par = lg["collateral"][c["type"]]
        v = float(c.get("value") or 0.0) * fx(c.get("currency", "SAR")) * cshock
        r_ = v * (1 - par["haircut"]) * (1 + lg["recovery_discount_rate"]) ** (-par["recovery_years"])
        recog += r_
        if c["type"] == "real_estate":
            re_value += v
        coll_rows.append({"collateral_id": cid, "type": c["type"], "value_sar_mn": v, "haircut": par["haircut"],
                          "recovery_years": par["recovery_years"], "recognised_sar_mn": r_})
    ra_pct = float(t["receivables_assignment_pct"]) / 100.0
    if ra_pct > 0:
        rp = cpt["receivables_assignment"]
        v = A * ra_pct * cshock
        r_ = v * (1 - rp["haircut"]) * (1 + lg["recovery_discount_rate"]) ** (-rp["recovery_years"])
        recog += r_
        coll_rows.append({"collateral_id": "ASSIGN", "type": "receivables_assignment", "value_sar_mn": v, "haircut": rp["haircut"],
                          "recovery_years": rp["recovery_years"], "recognised_sar_mn": r_})
    cash = A * float(t["cash_margin_pct"]) / 100.0
    from backend.dealdesk.deposit_requirement import term as DT  # Round D: lien-marked cash deposit, recognised as cash
    lien, lien_info = DT.lien_cash(p, t, A_full, hold, T, lg, X)
    recog_total = recog + cash + lien
    pk = cov["packages"][t["covenant_package"]]
    capm = float(cov["cap"])
    rc = cvi["review_cycles"][str(int(t["review_cycle_months"]))]
    pd_raw, lgd_raw = float(pk["pd_multiplier"]) * float(rc["pd_multiplier"]), float(pk["lgd_multiplier"])
    for it in t.get("covenant_items") or []:
        pd_raw *= float(cvi["items"][it]["pd_multiplier"])
        lgd_raw *= float(cvi["items"][it]["lgd_multiplier"])
    pd_mult = float(np.clip(pd_raw, 1 - capm, 1 + capm))
    lgd_mult = float(np.clip(lgd_raw, 1 - capm, 1 + capm))
    lgd_unsec = float(lg["unsecured"]["senior"])
    struct = float(lg["structure"][t["structure"]])
    floor = float(lg["floor"])
    lgd_pre = np.where(ead > 0, np.maximum(0.0, ead - recog_total) / np.where(ead > 0, ead, 1.0) * lgd_unsec * struct, 0.0)
    lgd_t = np.maximum(floor, lgd_pre * lgd_mult)

    # PD
    notches = int(sh.get("notches", 0))
    if pd_override is not None:
        marg = np.asarray(pd_override["marginal"][:T], dtype=float)
        ttc = float(pd_override["ttc"])
        o = None
        rating = ob["internal_rating"]
    else:
        o = pd_model.obligor_pd(p, notches)
        rating = o["rating"]
        ts = pd_model.term_structure(o["hazards"], rating, T)
        marg = ts["marginal"][:T]
        ttc = o["pd_ttc"]
    pd_t = np.clip(marg * pd_mult, 0.0, 1.0)

    # guarantee
    gid = t.get("guarantee_id")
    cvg = float(t["guarantee_coverage_pct"]) / 100.0 if gid else 0.0
    gr = None
    gcat = cpt["guarantee_catalogue"]
    if gid:
        if gid in gcat and gid not in {x["guarantee_id"] for x in p["security"]["guarantees"]}:
            from backend.dealdesk.levers import requested_rating
            c = gcat[gid]
            gr = {"guarantee_id": gid, "type": c["type"], "guarantor": c["label"], "guarantor_rating": requested_rating(p, gid),
                  "requested": True}
        else:
            gr = next(x for x in p["security"]["guarantees"] if x["guarantee_id"] == gid)
        gpd = guarantor_pd(gr["guarantor_rating"], T) if pd_override is None else np.asarray(pd_override["guarantor_marginal"][:T])
        glgd = float(gcat[gid]["lgd"]) if gr.get("requested") else float(lg["guarantor_lgd"][gr["type"]])
        gttc = pd_model.master_pd(gr["guarantor_rating"]) if pd_override is None else float(pd_override["guarantor_ttc"])
    else:
        gpd, glgd, gttc = np.zeros(T), 0.0, 0.0
    # R14 E (K24): PD/LGD substitution only when the guarantor is rated better than the obligor. A guarantor rated the
    # same or weaker gives no PD, LGD, capital or risk-weight benefit (the guarantee stays a condition, not a CRM).
    g_cvg_offered = cvg
    g_subst = bool(gr) and rank(gr["guarantor_rating"]) < rank(rating)
    if gr and not g_subst:
        cvg = 0.0
    # Substitution only where it helps: the covered share carries the lower of the two loss rates
    # (and below, the lower capital charge and risk weight).
    covered_rate = np.minimum(pd_t * lgd_t, gpd * glgd) if cvg else np.zeros(T)
    # credit insurance: a second protected share on an A-rated insurer, never more than what is uncovered
    ins = cpt["credit_insurance"]
    civ = min(float(t["insurance_cover_pct"]) / 100.0, 1.0 - cvg)
    if civ > 0:
        ipd = guarantor_pd(ins["insurer_rating"], T) if pd_override is None else np.asarray(pd_override["insurer_marginal"][:T])
        ilgd = float(ins["lgd"])
        ittc = pd_model.master_pd(ins["insurer_rating"]) if pd_override is None else float(pd_override["insurer_ttc"])
        ins_rate = np.minimum(pd_t * lgd_t, ipd * ilgd)
    else:
        ipd, ilgd, ittc, ins_rate = np.zeros(T), 0.0, 0.0, np.zeros(T)
    unc = 1 - cvg - civ
    el = ead * (unc * pd_t * lgd_t + cvg * covered_rate + civ * ins_rate)

    # regulatory capital (SA)
    ccf_u_reg = ccf["undrawn_committed"]["regulatory"]
    ccf_o_reg = ccf[utype]["regulatory"]
    expo = drawn + ccf_u_reg * undrawn + ccf_o_reg * outstanding
    if ob.get("sovereign"):
        rw_obl = rw["sovereign"]
    elif ob.get("gre"):
        rw_obl = rw["gre"]
    elif ob.get("real_estate_finance") and re_value > 0:
        ltv0 = F / re_value if re_value else 9.0
        rw_obl = next(b["rw"] for b in rw["ipre_ltv"] if ltv0 <= b["max_ltv"])
    elif ob.get("sme"):
        rw_obl = rw["sme_corporate"]
    elif ob.get("external_rating"):
        rw_obl = rw["corporate_by_external"].get(ob["external_rating"], rw["corporate_unrated"])
    else:
        rw_obl = rw["corporate_unrated"]
    rw_g = (gcat[gid]["sa_rw"] if gr and gr.get("requested") else rw["guarantor"].get(gr["type"])) if gr else None
    # Eligible financial collateral: the cash margin (held in the deal's currency) and pledged cash items,
    # the latter with the currency-mismatch haircut when their currency differs from the deal's.
    cash_items = sum(float(items[cid].get("value") or 0.0) * fx(items[cid].get("currency", "SAR")) * cshock
                     * (1 - (rw["fx_mismatch_haircut"] if items[cid].get("currency", "SAR") != t["currency"] else 0.0))
                     for cid in t.get("collateral_ids", []) if items[cid]["type"] == "cash")
    cash_adj = cash + cash_items + lien
    expo_net = np.maximum(0.0, expo - cash_adj)
    rw_i = min(rw_obl, float(ins["sa_rw"])) if civ > 0 else rw_obl
    if rw_g is not None and cvg > 0:
        rwa = expo_net * ((1 - cvg - civ) * rw_obl + cvg * min(rw_obl, rw_g) + civ * rw_i)
    else:
        rwa = expo_net * ((1 - civ) * rw_obl + civ * rw_i)
    reg_cap = rwa * float(cap["capital_ratio_target"])

    # economic capital (IRB proxy, TTC PD)
    ec = cap["economic"]
    m_t = np.clip(T - years + 1, ec["maturity_floor"], ec["maturity_cap"]).astype(float)
    if rc.get("maturity_cap") is not None:
        # a shorter review cycle (with repricing and call rights) shortens the effective maturity
        m_t = np.maximum(float(ec["maturity_floor"]), np.minimum(m_t, float(rc["maturity_cap"])))
    econ_cap = np.array([ead[i] * ((1 - cvg - civ) * irb_k(ttc, lgd_t[i], m_t[i], ec)
                                   + (cvg * min(irb_k(ttc, lgd_t[i], m_t[i], ec), irb_k(gttc, glgd, m_t[i], ec)) if cvg else 0.0)
                                   + (civ * min(irb_k(ttc, lgd_t[i], m_t[i], ec), irb_k(ittc, ilgd, m_t[i], ec)) if civ else 0.0))
                         for i in range(T)])

    # pricing, FTP, income
    cur = t["currency"]
    fixed = t["rate_type"] == "fixed"
    if fixed:
        # fixed rate: client and FTP priced off the swap curve at the tenor, match-funded (no repricing under a rate shock);
        # Treasury charges the ALM fixed-rate premium
        base = _interp(T, ftp["tenors"], ftp["base"][cur])
        alm = float(pb["fixed_rate_alm_premium_bps"][cur]) / 1e4
    else:
        base = _interp(ftp["reference_tenor"], ftp["tenors"], ftp["base"][cur]) + float(sh.get("rate_shock_bps", 0.0)) / 1e4
        alm = 0.0
    lp = _interp(T, ftp["tenors"], ftp["liquidity_premium_bps"][cur]) / 1e4
    margin = float(t["margin_bps"]) / 1e4
    margin_path = margin
    rat = float(t.get("margin_ratchet_bps_per_notch") or 0.0)
    if rat:  # R12-I: the ratchet steps the margin by the expected notches of migration at the start of each year
        from backend.dealdesk.book.feedback import expected_notches
        margin_path = margin + rat / 1e4 * expected_notches(ob["internal_rating"], T)
    profit_income = drawn * (base + margin_path)
    expo_fee = drawn + outstanding
    upfront = A * float(t["upfront_fee_bps"]) / 1e4 + (A_full - A) * float(pb["arranger_skim_bps"]) / 1e4
    fee_income = upfront * expo_fee / expo_fee.sum() if expo_fee.sum() > 0 else np.zeros(T)
    # prepayment fee: expected early-settled principal (CPR of the rating bucket) x the fee; the schedule is kept contractual
    cpr = float(pb["prepayment_cpr"][bucket(ob["internal_rating"])]) if ftype == "term_loan" else 0.0
    prepay_fee = drawn * cpr * float(t["prepayment_fee_bps"]) / 1e4
    fee_income = fee_income + prepay_fee
    commitment = undrawn * float(t["commitment_fee_bps"]) / 1e4
    commission = outstanding * float(t["commission_bps"]) / 1e4
    cb = ftp["contingent_bps"]
    ftp_cost = drawn * (base + lp + alm) + undrawn * cb["undrawn_committed"] / 1e4 + outstanding * cb[utype] / 1e4
    seg = "gre" if ob.get("gre") else "sme" if ob.get("sme") else "corporate"
    ox = opx[seg]
    mon = float(rc["monitoring"]) + sum(float(cvi["items"][it]["monitoring"]) for it in t.get("covenant_items") or [])
    premium = civ * ead * float(ins["premium_bps"]) / 1e4 if civ > 0 else np.zeros(T)
    opex = (ox["servicing_fixed"] + ox["servicing_bps"] / 1e4 * (drawn + outstanding) + opx["covenant_monitoring"][t["covenant_package"]]
            + mon + premium)
    opex = np.asarray(opex, dtype=float)
    opex[0] += ox["origination_fixed"] + ox["origination_bps"] / 1e4 * A
    gross = profit_income - ftp_cost + fee_income + commitment + commission
    op_cap = cap["operational"]["alpha"] * np.maximum(0.0, gross)
    credit_cap = {"regulatory": reg_cap, "economic": econ_cap, "max": np.maximum(reg_cap, econ_cap)}[basis]
    capital = credit_cap + op_cap

    # expected loss views
    day_one = float(el[0])
    if el_view == "accounting":
        q = pd_model.stage2_probability(rating, T) if pd_override is None else np.asarray(pd_override.get("stage2", np.zeros(T)))[:T]
        surv = 1 - np.cumsum(pd_t)
        allowance = np.zeros(T)
        for i in range(T):
            if i == T - 1:
                break
            s_i = max(surv[i], 1e-12)
            cond = pd_t[i + 1:] / s_i  # PD in later years conditional on surviving year i
            loss = ead[i + 1:] * (unc * cond * lgd_t[i + 1:] + cvg * covered_rate[i + 1:] / s_i + civ * ins_rate[i + 1:] / s_i)
            ecl12, ecllt = float(loss[0]), float(loss.sum())
            allowance[i] = surv[i] * ((1 - q[i]) * ecl12 + q[i] * ecllt)
        prev = np.concatenate([[day_one], allowance[:-1]])
        ecl_change = allowance - prev
        credit_cost = el + ecl_change
        credit_cost[0] += day_one
    else:
        ecl_change = np.zeros(T)
        credit_cost = el.copy()

    cbr = float(ret["capital_benefit_rate"])
    cap_benefit = capital * cbr
    pre_zakat = profit_income + fee_income + commitment + commission - ftp_cost - opex - credit_cost + cap_benefit
    zakat = float(ret["zakat_rate"]) * pre_zakat
    rap = pre_zakat - zakat
    h = hurdle_for(p)
    disc = (1 + h) ** (-years.astype(float))
    pv_rap = float((disc * rap).sum())
    pv_cap = float((disc * capital).sum())
    lifetime = pv_rap / pv_cap if pv_cap > 0 else float("nan")
    sva = float((disc * (rap - h * capital)).sum())
    committed = set(t.get("cross_sell") or [])
    from backend.dealdesk.book.promises import committed_realisation  # R12-I: flat 90% or actual realisation (parameter)
    rel_real = committed_realisation(rel)
    anc = sum(v * (rel_real if k in committed else float(ret["ancillary_realisation"]))
              for k, v in p.get("business_case", {}).get("ancillary_income_sar_mn_pa", {}).items())
    anc_t = np.full(T, anc * (1 - float(ret["zakat_rate"])))
    rel_dep, rel_info = DT.relationship_value(p, t, A_full, T, cur, float(ret["zakat_rate"]), rel, rel_real, X)  # Round D
    rel_rap = rap + anc_t + rel_dep
    rel_raroc = float((disc * rel_rap).sum()) / pv_cap if pv_cap > 0 else float("nan")
    rel_sva = float((disc * (rel_rap - h * capital)).sum())

    # client debt capacity after the deal
    fin = latest_actual(p)
    rate_shock = float(sh.get("rate_shock_bps", 0.0)) / 1e4
    existing_ds = float(fin["debt_service"]) + rate_shock * float(fin["total_debt"])
    sched_principal = principal.copy()
    if ftype == "term_loan" and F > 0:
        sched_principal[-1] -= F * balloon
    else:
        sched_principal[:] = 0.0
    deal_ds = sched_principal + profit_income
    # the client services the whole facility, whatever share the bank holds
    client_ds = deal_ds / hold if hold > 0 else deal_ds
    ds_max = float(client_ds.max()) if T else 0.0
    dscr_post = float(fin["ebitda"]) / (existing_ds + ds_max) if (existing_ds + ds_max) > 0 else float("inf")
    F_full = F / hold if hold > 0 else F
    debt_ebitda_post = (float(fin["total_debt"]) + F_full) / float(fin["ebitda"]) if fin["ebitda"] > 0 else float("inf")
    ltv = F_full / re_value if re_value > 0 else None

    pnl = [{"year": int(years[i]), "profit_income": float(profit_income[i]), "fee_income": float(fee_income[i]),
            "commitment_fee": float(commitment[i]), "commission": float(commission[i]), "ftp": float(ftp_cost[i]),
            "opex": float(opex[i]), "el": float(el[i]), "day_one_ecl": day_one if i == 0 else 0.0,
            "ecl_change": float(ecl_change[i]), "credit_cost": float(credit_cost[i]), "capital_benefit": float(cap_benefit[i]),
            "zakat": float(zakat[i]), "rap": float(rap[i]), "prepayment_fee": float(prepay_fee[i]), "insurance_premium": float(premium[i]), "capital": float(capital[i]),
            "raroc": float(rap[i] / capital[i]) if capital[i] > 0 else None, "discount": float(disc[i]),
            "ancillary": float(anc_t[i])} for i in range(T)]
    pv = lambda v: float((disc * v).sum())  # noqa: E731
    waterfall = [{"step": "Profit income", "value": pv(profit_income)},
                 {"step": "Fees", "value": pv(fee_income + commitment + commission)},
                 {"step": "FTP", "value": -pv(ftp_cost)}, {"step": "Opex", "value": -pv(opex)},
                 {"step": "Expected loss" if el_view == "economic" else "Credit cost (accounting)", "value": -pv(credit_cost)},
                 {"step": "Zakat", "value": -pv(zakat)}, {"step": "Capital benefit", "value": pv(cap_benefit)},
                 {"step": "Risk-adjusted profit", "value": pv_rap, "total": True}]
    schedule = [{"year": int(years[i]), "drawn_start": float(drawn[i]), "drawn_end": float(drawn[i] - principal[i]),
                 "drawn_avg": float(drawn[i]), "undrawn_avg": float(undrawn[i]), "unfunded_avg": float(outstanding[i]),
                 "ead": float(ead[i]), "principal": float(principal[i]), "profit_paid": float(profit_income[i]),
                 "debt_service": float(deal_ds[i])} for i in range(T)]
    out = {
        "terms": t, "el_view": el_view, "capital_basis": basis, "fx_to_sar": X, "hurdle": h,
        "metrics": {"amount_sar_mn": A_full, "held_sar_mn": A, "lifetime_raroc": lifetime, "hurdle": h, "clears_hurdle": bool(sva >= -1e-6),  # R14 m: SAR 1 of SVA (a root found to 1e-10 re-runs within it)
                    "sva": sva, "relationship_raroc": rel_raroc, "relationship_sva": rel_sva,
                    "rwa_y1": float(rwa[0]), "capital_y1": float(capital[0]), "el_y1": float(el[0]),
                    "el_lifetime_pv": pv(el), "el_lifetime": float(el.sum()), "day_one_ecl": day_one, "pd_12m": float(pd_t[0]),
                    "lgd_y1": float(lgd_t[0]), "ead_y1": float(ead[0]), "dscr_post": dscr_post,
                    "debt_ebitda_post": debt_ebitda_post, "ltv": ltv, "pv_rap": pv_rap, "pv_capital": pv_cap,
                    "rwa_density_y1": float(rwa[0] / A) if A else None,
                    "ead_net_y1": float(max(0.0, ead[0] - lien[0])) if T else 0.0},  # Round D: EAD net of a lien-marked deposit
        "pd": None if o is None else {
            "model_version": pd_model.model_meta()["version"], "model_pd_12m": o["pd_12m"], "rating_used": rating,
            "master_scale_pd_12m": o["master_scale_pd_12m"], "ttc_pd": ttc,
            "term_structure": [{"year": int(years[i]), "marginal": float(pd_t[i]), "cumulative": float(pd_t[: i + 1].sum()),
                                "model_marginal": float(marg[i]), "source": "model" if i < 5 else "model year 5 x migration shape"}
                               for i in range(T)],
            "reference_profile": o["provenance"], "out_of_range": o["out_of_range"], "monotonicity": o["monotonicity"],
            "covenant_overlay": {"package": t["covenant_package"], "pd_multiplier": pd_mult, "lgd_multiplier": lgd_mult}},
        "lgd": {"unsecured": lgd_unsec, "structure_multiplier": struct, "covenant_multiplier": lgd_mult, "floor": floor,
                "collateral": coll_rows, "cash_margin_sar_mn": cash, "collateral_recognised_sar_mn": float(recog + cash + (lien[0] if T else 0.0)),
                "lien_deposit_sar_mn": float(lien[0]) if T else 0.0,
                "guarantee": None if not gr else {"guarantee_id": gid, "type": gr["type"], "guarantor": gr.get("guarantor", ""),
                                                  "rating": gr["guarantor_rating"], "coverage": cvg, "lgd": glgd,
                                                  "coverage_offered": g_cvg_offered, "substitution": g_subst, "obligor_rating": rating,
                                                  "substitution_rule": ("guarantor rated better than the obligor: PD/LGD substitution applied"
                                                                        if g_subst else f"guarantor {gr['guarantor_rating']} not better than the obligor "
                                                                        f"{rating}: no PD/LGD substitution (R14 guarantor rule)"),
                                                  "sa_rw": rw_g, "pd_y1": float(gpd[0]), "requested": bool(gr.get("requested"))},
                "insurance": None if civ <= 0 else {"cover": civ, "insurer_rating": ins["insurer_rating"], "lgd": ilgd,
                                                    "sa_rw": float(ins["sa_rw"]), "premium_bps": float(ins["premium_bps"]), "pd_y1": float(ipd[0])},
                "by_year": [float(x) for x in lgd_t], "before_covenant": [float(x) for x in np.maximum(floor, lgd_pre)]},
        "schedule": schedule,
        "capital": {"basis": basis, "rw_obligor": rw_obl, "capital_ratio": float(cap["capital_ratio_target"]),
                    "by_year": [{"year": int(years[i]), "exposure_sa": float(expo[i]), "rwa": float(rwa[i]),
                                 "regulatory": float(reg_cap[i]), "economic": float(econ_cap[i]), "operational": float(op_cap[i]),
                                 "capital": float(capital[i]), "maturity": float(m_t[i])} for i in range(T)]},
        "pnl": pnl, "waterfall": waterfall,
        "rates": {"base": base, "liquidity_premium": lp, "margin": margin, "client_rate": base + margin, "rate_type": t["rate_type"],
                  "alm_premium": alm, "prepayment_cpr": cpr},
        "levers": {"hold": hold, "arranger_skim_sar_mn": (A_full - A) * float(pb["arranger_skim_bps"]) / 1e4,
                   "covenant_pd_multiplier_raw": pd_raw, "covenant_lgd_multiplier_raw": lgd_raw, "review_cycle": rc["label"],
                   "monitoring_sar_mn_pa": mon, "cross_sell_committed": sorted(committed), "ancillary_pa_after_realisation": anc},
        "deposit": DT.engine_effect(t, lien_info, rel_info, ead, disc, pv_cap, A_full, t["currency"], params.versions()),  # Round D
        "_arrays": {"ead": ead, "rwa": rwa, "el": el, "drawn": drawn, "outstanding": outstanding},
    }
    from backend.dealdesk import constraints
    pc = p
    if notches and rating != ob["internal_rating"]:
        # under a downgrade stress the rating-based limits and the approval level see the stressed grade
        pc = {**p, "obligor": {**ob, "internal_rating": rating}}
    out["constraints"] = constraints.evaluate(pc, out)
    out["approval"] = constraints.approval(pc, out)
    out["param_versions"] = params.versions()
    return out


def breakeven_margin(p: dict[str, Any], terms: dict[str, Any] | None = None, **kw: Any) -> float | None:
    """The margin (bps) at which SVA = 0 (lifetime RAROC = hurdle), other terms as given.

    SVA is affine in the margin wherever gross income is positive (the operational-risk charge is
    alpha x max(0, gross income)), so the secant step is exact there; it is iterated to 1e-10."""
    t = merge_terms(p, terms)
    if t["facility_type"] in UNFUNDED or float(t["funded_share_pct"]) == 0:
        return None
    sva = lambda m: analyse(p, {**t, "margin_bps": m}, validate=False, **kw)["metrics"]["sva"]  # noqa: E731
    m0, m1 = float(t["margin_bps"]), float(t["margin_bps"]) + 100.0
    s0, s1 = sva(m0), sva(m1)
    for _ in range(30):
        if abs(s1 - s0) < 1e-14:
            return None
        m2 = m1 - s1 * (m1 - m0) / (s1 - s0)
        m0, s0, m1 = m1, s1, m2
        s1 = sva(m1)
        if abs(s1) < 1e-10:
            break
    return m1


def breakeven(p: dict[str, Any], terms: dict[str, Any] | None, lever: str, **kw: Any) -> dict[str, Any]:
    """The lever value at which SVA = 0, others fixed (bisection on a monotone lever)."""
    t = merge_terms(p, terms)
    units = {"margin_bps": "bps", "upfront_fee_bps": "bps", "amount": f"{t['currency']} m", "tenor_years": "years",
             "cash_margin_pct": "%", "guarantee_coverage_pct": "%", "commission_bps": "bps"}
    if lever not in units:
        raise TermsError([{"field": "lever", "message": f"one of {', '.join(units)}"}])
    at_ask = analyse(p, t, **kw)["metrics"]["sva"]
    if lever == "margin_bps":
        v = breakeven_margin(p, t, **kw)
        return {"lever": lever, "value": v, "unit": "bps", "feasible": v is not None and v >= 0, "at_ask": t[lever], "sva_at_ask": at_ask}
    lo, hi = {"upfront_fee_bps": (0, 1000), "amount": (0.01, float(t["amount"]) * 3), "tenor_years": (1, 10),
              "cash_margin_pct": (0, 100), "guarantee_coverage_pct": (0, 100), "commission_bps": (0, 1000)}[lever]
    if lever == "guarantee_coverage_pct" and not t.get("guarantee_id"):
        gs = p["security"]["guarantees"]
        if not gs:
            return {"lever": lever, "value": None, "unit": "%", "feasible": False, "at_ask": 0, "sva_at_ask": at_ask,
                    "note": "The obligor has no guarantee available."}
        t["guarantee_id"] = gs[0]["guarantee_id"]

    def f(x: float) -> float:
        v = int(round(x)) if lever == "tenor_years" else x
        tt = {**t, lever: v}
        if lever == "tenor_years" and tt["grace_years"] >= v:
            tt["grace_years"] = v - 1
        return analyse(p, tt, validate=False, **kw)["metrics"]["sva"]

    if lever == "tenor_years":
        vals = [(n, f(n)) for n in range(1, 11)]
        ok = [n for n, s in vals if s >= 0]
        return {"lever": lever, "value": (min(ok) if at_ask < 0 else max(ok)) if ok else None, "unit": "years",
                "feasible": bool(ok), "at_ask": t[lever], "sva_at_ask": at_ask, "values": vals}
    flo, fhi = f(lo), f(hi)
    if (flo >= 0) == (fhi >= 0):
        return {"lever": lever, "value": None, "unit": units[lever], "feasible": flo >= 0, "at_ask": t[lever], "sva_at_ask": at_ask,
                "note": "SVA does not change sign over the lever's range."}
    a, b = lo, hi
    for _ in range(60):
        mid = (a + b) / 2
        if (f(mid) >= 0) == (flo >= 0):
            a = mid
        else:
            b = mid
    return {"lever": lever, "value": (a + b) / 2, "unit": units[lever], "feasible": True, "at_ask": t[lever], "sva_at_ask": at_ask}


def public(a: dict[str, Any]) -> dict[str, Any]:
    """The API shape: drops internal arrays, makes floats JSON-safe."""
    out = {k: v for k, v in a.items() if not k.startswith("_")}
    return _clean(out)


def _clean(x: Any) -> Any:
    if isinstance(x, dict):
        return {k: _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    if isinstance(x, (np.floating, float)):
        f = float(x)
        return None if not math.isfinite(f) else f
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.bool_):
        return bool(x)
    if isinstance(x, np.ndarray):
        return _clean(x.tolist())
    return x


__all__ = ["analyse", "breakeven", "breakeven_margin", "merge_terms", "public", "TermsError", "GRADES", "bucket", "rank", "portfolio"]
