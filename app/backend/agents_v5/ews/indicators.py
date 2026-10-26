"""CBUAE CRM SICR and UTP indicators, evaluated on one borrower's evidence (the triage agent's indicator engine).

Every indicator names its clause in the CBUAE Credit Risk Management Standards as the policy pack holds it
(`backend/playbook_v5/data/cbuae_crm.json`: Art. 6 unlikeliness to pay, Art. 7 SICR), the evidence fields it read,
their values and the threshold. Thresholds are the bank's stated triage criteria (`THRESHOLDS`), shown on every
indicator so a reviewer can see why it fired. Nothing here writes; nothing here invents a figure.
"""
from __future__ import annotations

import functools
import json
import pathlib
from typing import Any

PACK = pathlib.Path(__file__).resolve().parents[2] / "playbook_v5" / "data" / "cbuae_crm.json"

#: The triage criteria (one place; every indicator prints the one it used).
THRESHOLDS: dict[str, float] = {
    "dpd_sicr": 30,             # Art. 7.8: more than 30 days past due
    "dpd_utp": 90,              # Art. 6.4: more than 90 days past due on a material obligation
    "dpd_nonpayment": 60,       # Art. 6.9 l: a practice of non-payment on due dates
    "returned_liquidity": 2,    # Art. 7.11 a: rising liquidity risk (returned payments in the quarter)
    "returned_nonpayment": 3,   # Art. 6.9 l: practice of non-payment
    "buffer_months": 1.0,       # Art. 7.11 a: operating balance under one month of obligations
    "inflow_fall_pct": -30,     # Art. 7.11 a: operating inflows down 30% or more on the year
    "turnover_to_revenue_pct": 40,  # Art. 6.9 m: limited inflows (turnover routed through the bank under 40% of revenue)
    "od_util_pct": 100,         # Art. 6.9 m: an overdraft constantly up to or above its limit
    "dscr": 1.0,                # Art. 7.11 a: deterioration of financial performance (DSCR under 1.0x)
    "collateral_fall_sicr": -10,  # Art. 7.11 b: collateral market value down 10% or more on the quarter
    "collateral_fall_utp": -25,   # Art. 6.9 h: a significant deterioration in the value of collateral (25%+)
    "downgrade_notches": 2,     # Art. 7.11 e: downgrade of two notches or more in the quarter
    "bureau_dpd": 30,           # Art. 7.11 e: past due at another lender (credit bureau)
    "covenant_consecutive": 2,  # Art. 6.9 d: a material covenant in breach two tests running, not waived
    # retail (Art. 6.10 and 7.9)
    "retail_ltv_pct": 85,       # Art. 6.10 d: secured LTV above the internal limit
    "retail_missed_12m": 3,     # Art. 6.6: a pattern of missed payments (3+ in 12 months, 2+ months running)
    "retail_streak_months": 2,
    "retail_inflow_fall_pct": -40,  # Art. 7.9: account inflows down 40% or more in 3 months
    "retail_payment_ratio_pct": 30,  # Art. 7.9: payment ratio under 30% and down 10 points in 3 months
    "retail_payment_ratio_drop": -10,
    "retail_bureau_score": 580,  # Art. 7.9: bureau score under 580
    "retail_gambling_bnpl_pct": 15,  # Art. 7.9: gambling and BNPL spend 15% or more of outflows
    "retail_score_bands_down": 2,   # Art. 7.9: behaviour score down two bands or more
}


@functools.lru_cache(maxsize=1)
def clauses() -> dict[str, dict[str, str]]:
    data = json.loads(PACK.read_text())
    return {c["number"]: {"clause": c["clause"], "title": c["title"], "rule": c["rule"]} for c in data["clauses"]}


def cite(number: str, letter: str = "") -> dict[str, str]:
    c = clauses().get(number, {})
    rule = c.get("rule", "")
    excerpt = rule
    if letter:
        key = f"{letter}. "
        i = rule.find(key)
        if i >= 0:
            j = rule.find(". ", i + len(key) + 3)
            nxt = [rule.find(f"{chr(ord(letter) + 1)}. ", i + 1), rule.find("\n", i + 1)]
            ends = [x for x in nxt if x > i]
            excerpt = rule[i: min(ends) if ends else (j + 1 if j > 0 else len(rule))].strip()
    return {"ref": f"CBUAE CRM Art. {number}{(' ' + letter) if letter else ''}", "title": c.get("title", ""),
            "excerpt": excerpt[:320], "source": c.get("clause", ""),
            "document": "Credit Risk Management Standards (Central Bank of the UAE), policy pack pd_cbuae_crm"}


def _ind(code: str, kind: str, strength: str, art: str, letter: str, label: str, fields: dict[str, Any],
         threshold: str, source: str) -> dict[str, Any]:
    return {"code": code, "kind": kind, "strength": strength, "label": label, "fields": fields,
            "threshold": threshold, "source": source, "article": cite(art, letter)}


_BANDS = "ABCDE"


def assess_retail(e: dict[str, Any]) -> list[dict[str, Any]]:
    """Indicators fired for one retail customer (Art. 6.4, 6.6, 6.8 e, 6.10 and 7.8, 7.9)."""
    T = THRESHOLDS
    x, o = e.get("exposure") or {}, e.get("owner") or {}
    c, b, ch = e.get("conduct") or {}, e.get("bureau") or {}, e.get("changes") or {}
    peers = e.get("peers") or {}
    out: list[dict[str, Any]] = []
    dpd = int(x.get("dpd") or 0)
    if dpd > T["dpd_utp"]:
        out.append(_ind("UTP-DPD90", "utp", "hard", "6.4", "", f"{dpd} days past due (over 90)", {"dpd_days": dpd},
                        "> 90 DPD", "b360.evidence"))
    if b.get("external_default"):
        out.append(_ind("UTP-EXT-DEFAULT", "utp", "hard", "6.8", "e", "New default at another lender (bureau)",
                        {"new_external_default": True, "external_dpd_days": b.get("external_dpd_days")},
                        "new external default", "bureau.external"))
    if c.get("salary_interrupted"):
        infl, buf = c.get("inflow_trend_pct"), c.get("buffer_months")
        dried = infl is not None and infl <= T["retail_inflow_fall_pct"] and buf is not None and buf < T["buffer_months"]
        hard = dpd > T["dpd_sicr"] or dried
        out.append(_ind("UTP-INCOME", "utp", "hard" if hard else "soft", "6.10", "a",
                        "Salary credit missing" + (" with more than 30 days in arrears" if dpd > T["dpd_sicr"] else
                                                   " and inflows down 40%+ with under a month of buffer" if dried else "")
                        + ": the source of repayment is distressed",
                        {"salary_interruption_flag": 1, "dpd_days": dpd, "inflow_trend_pct": infl, "buffer_months": buf},
                        "salary interruption; hard with 30+ DPD or inflows down 40%+ and buffer under 1 month",
                        "conduct.account"))
    if (c.get("missed_payments_12m") or 0) >= T["retail_missed_12m"] and \
            (c.get("delinquency_streak_months") or 0) >= T["retail_streak_months"]:
        out.append(_ind("UTP-NONPAYMENT", "utp", "soft", "6.6", "",
                        f"{c['missed_payments_12m']} missed payments in 12 months, {c['delinquency_streak_months']} months running",
                        {"missed_payments_12m": c["missed_payments_12m"],
                         "delinquency_streak_months": c["delinquency_streak_months"]},
                        "3+ missed in 12 months and 2+ months running", "conduct.account"))
    ltv = x.get("ltv_max")
    if ltv is not None and ltv > T["retail_ltv_pct"]:
        out.append(_ind("UTP-COLLATERAL", "utp", "soft", "6.10", "d",
                        f"Secured LTV {ltv:.0f}% above the internal limit ({x.get('ltv_product') or 'secured product'})",
                        {"collateral_ltv_pct": ltv}, "LTV > 85%", "b360.evidence"))
    if T["dpd_sicr"] < dpd <= T["dpd_utp"]:
        out.append(_ind("SICR-DPD30", "sicr", "hard", "7.8", "", f"{dpd} days past due (over 30): SICR presumption",
                        {"dpd_days": dpd}, "> 30 DPD", "b360.evidence"))
    liq = {}
    if (c.get("returned_payments_q") or 0) >= T["returned_liquidity"]:
        liq["returned_payments_3m"] = c["returned_payments_q"]
    if c.get("buffer_months") is not None and c["buffer_months"] < T["buffer_months"]:
        liq["buffer_months"] = c["buffer_months"]
    if c.get("inflow_trend_pct") is not None and c["inflow_trend_pct"] <= T["retail_inflow_fall_pct"]:
        liq["inflow_trend_pct"] = c["inflow_trend_pct"]
    if liq:
        out.append(_ind("SICR-LIQUIDITY", "sicr", "soft", "7.9", "",
                        "Account conduct weakening (" + ", ".join(
                            {"returned_payments_3m": "returned payments", "buffer_months": "balance buffer under 1 month",
                             "inflow_trend_pct": "inflows down 40%+"}[k] for k in liq) + ")",
                        liq, "returned ≥ 2, buffer < 1 month or inflows ≤ −40% in 3 months", "conduct.account"))
    pr, prc = c.get("payment_ratio_pct"), c.get("payment_ratio_change_3m")
    if pr is not None and prc is not None and pr < T["retail_payment_ratio_pct"] and prc <= T["retail_payment_ratio_drop"]:
        out.append(_ind("SICR-MINPAY", "sicr", "soft", "7.9", "", f"Paying {pr:.0f}% of the due amount, down {-prc:.0f} points",
                        {"payment_ratio_pct": pr, "payment_ratio_change_3m": prc}, "ratio < 30% and down 10+ points",
                        "conduct.account"))
    now, was = str(o.get("score_band") or ""), str(o.get("score_band_previous") or "")
    if now in _BANDS and was in _BANDS and _BANDS.index(now) - _BANDS.index(was) >= T["retail_score_bands_down"]:
        out.append(_ind("SICR-BEHAVIOUR", "sicr", "soft", "7.9", "", f"Behaviour score band fell from {was} to {now}",
                        {"score_band": now, "score_band_previous": was}, "down 2+ bands", "b360.evidence"))
    bs = b.get("bureau_score")
    if (bs is not None and bs < T["retail_bureau_score"]) or \
            (int(b.get("external_dpd_days") or 0) > T["bureau_dpd"] and not b.get("external_default")):
        out.append(_ind("SICR-BUREAU", "sicr", "soft", "7.9", "",
                        "Bureau deterioration (" + ", ".join(
                            ([f"score {bs:.0f}"] if bs is not None and bs < T["retail_bureau_score"] else [])
                            + ([f"{int(b['external_dpd_days'])} DPD at another lender"]
                               if int(b.get("external_dpd_days") or 0) > T["bureau_dpd"] else [])) + ")",
                        {"bureau_score": bs, "external_dpd_days": b.get("external_dpd_days")},
                        "score < 580 or > 30 DPD elsewhere", "bureau.external"))
    g = c.get("gambling_bnpl_share_pct")
    if g is not None and g >= T["retail_gambling_bnpl_pct"]:
        out.append(_ind("SICR-SPEND", "sicr", "soft", "7.9", "", f"Gambling and BNPL {g:.0f}% of spending",
                        {"gambling_bnpl_spend_share_pct": g}, "≥ 15% of outflows", "conduct.account"))
    if c.get("overlimit"):
        out.append(_ind("SICR-OVERLIMIT", "sicr", "soft", "7.9", "", "Card or line over its limit",
                        {"overlimit_flag": 1}, "over limit", "conduct.account"))
    if peers.get("sector_stress"):
        out.append(_ind("SICR-SECTOR", "sicr", "context", "7.12", "",
                        f"Product stress: {peers.get('warned_share_pct', 0):.0f}% of the sub-product warned "
                        f"(book {peers.get('book_warned_share_pct', 0):.0f}%) and rising",
                        {k: peers.get(k) for k in ("names", "warned", "warned_share_pct", "book_warned_share_pct")},
                        "warned share ≥ 1.5× book and rising", "ews.sector_peers"))
    return out


def assess(e: dict[str, Any]) -> list[dict[str, Any]]:
    """Indicators fired for one borrower. `e` is the merged evidence: `exposure`, `owner`, `covenants`, `collateral`,
    `group`, `conduct`, `bureau`, `peers`, `changes`, `rules`; `domain` "retail" uses the retail indicators."""
    if e.get("domain") == "retail":
        return assess_retail(e)
    T = THRESHOLDS
    x, o = e.get("exposure") or {}, e.get("owner") or {}
    c, b = e.get("conduct") or {}, e.get("bureau") or {}
    g, peers, ch = e.get("group") or {}, e.get("peers") or {}, e.get("changes") or {}
    out: list[dict[str, Any]] = []
    dpd = int(x.get("dpd") or 0)

    # ---- unlikeliness to pay (Art. 6)
    if dpd > T["dpd_utp"]:
        out.append(_ind("UTP-DPD90", "utp", "hard", "6.4", "", f"{dpd} days past due (over 90)",
                        {"dpd_days": dpd}, "> 90 DPD", "b360.evidence"))
    if b.get("external_default"):
        out.append(_ind("UTP-EXT-DEFAULT", "utp", "hard", "6.8", "e", "Classified as defaulted by another lender (bureau)",
                        {"external_default": True, "external_dpd_days": b.get("external_dpd_days")},
                        "external default flag", "bureau.external"))
    if o.get("restructured_flag") and (dpd > 0 or (o.get("dscr_x") is not None and float(o["dscr_x"]) < T["dscr"])):
        out.append(_ind("UTP-DISTRESSED-RESTR", "utp", "hard", "6.8", "i",
                        "Restructured while past due or with DSCR under 1.0x (distressed restructuring)",
                        {"restructured_flag": 1, "dpd_days": dpd, "dscr_x": o.get("dscr_x")},
                        "restructured and (DPD > 0 or DSCR < 1.0x)", "b360.evidence"))
    ret = int(c.get("returned_payments_q") or 0)
    if dpd >= T["dpd_nonpayment"] or ret >= T["returned_nonpayment"]:
        out.append(_ind("UTP-NONPAYMENT", "utp", "hard", "6.9", "l",
                        "A practice of non-payment on due dates (returned payments or 60+ DPD)",
                        {"returned_payments_q": ret, "dpd_days": dpd}, "returned ≥ 3 in the quarter or DPD ≥ 60",
                        "conduct.account"))
    material = [v for v in e.get("covenants") or []
                if v.get("breach_flag") and not v.get("waiver_flag")
                and int(v.get("consecutive_breaches") or 0) >= T["covenant_consecutive"]]
    if material:
        out.append(_ind("UTP-COVENANT", "utp", "soft", "6.9", "d",
                        f"Material covenant breach not waived, {max(int(v['consecutive_breaches']) for v in material)} tests running",
                        {"covenants": [{k: v.get(k) for k in ("covenant_type", "threshold_value", "observed_value",
                                                              "consecutive_breaches")} for v in material]},
                        "breach, no waiver, ≥ 2 consecutive tests", "b360.evidence"))
    od, ttr = c.get("overdraft_utilisation_pct"), c.get("turnover_to_revenue_pct")
    if od is not None and od >= T["od_util_pct"] and (
            (ttr is not None and ttr < T["turnover_to_revenue_pct"])
            or (c.get("inflow_trend_pct") is not None and c["inflow_trend_pct"] <= T["inflow_fall_pct"])):
        out.append(_ind("UTP-OVERDRAFT", "utp", "soft", "6.9", "m",
                        "Overdraft at or above its limit with limited or falling inflows",
                        {"overdraft_utilisation_pct": od, "turnover_to_revenue_pct": ttr,
                         "inflow_trend_pct": c.get("inflow_trend_pct")},
                        "OD utilisation ≥ 100% and (turnover < 40% of revenue or inflows ≤ −30%)", "conduct.account"))
    col = e.get("collateral") or {}
    fall = col.get("value_change_pct")
    if fall is not None and fall <= T["collateral_fall_utp"]:
        out.append(_ind("UTP-COLLATERAL", "utp", "soft", "6.9", "h",
                        f"Collateral value down {-fall:.0f}% on the quarter",
                        {"market_value_sar_mn": col.get("market_value"), "market_value_prior": col.get("market_value_prior"),
                         "value_change_pct": fall}, "market value down 25% or more q/q", "b360.evidence"))

    # ---- significant increase in credit risk (Art. 7)
    if T["dpd_sicr"] < dpd <= T["dpd_utp"]:
        out.append(_ind("SICR-DPD30", "sicr", "hard", "7.8", "", f"{dpd} days past due (over 30): SICR presumption",
                        {"dpd_days": dpd}, "> 30 DPD", "b360.evidence"))
    if o.get("restructured_flag"):
        out.append(_ind("SICR-DEFERRAL", "sicr", "hard", "7.7", "",
                        "Restructured / deferred instalments (deferral indicator)",
                        {"restructured_flag": 1}, "restructured flag", "b360.evidence"))
    breaches = [v for v in e.get("covenants") or [] if v.get("breach_flag")]
    if breaches or int(x.get("covenant_breaches") or 0) > 0:
        out.append(_ind("SICR-COVENANT", "sicr", "soft", "7.11", "a",
                        f"Breach of quantitative covenants ({', '.join(sorted({v['covenant_type'] for v in breaches})) or 'reported on the facility'})",
                        {"covenants_in_breach": len(breaches) or int(x.get("covenant_breaches") or 0),
                         "waived": sum(1 for v in breaches if v.get("waiver_flag"))},
                        "any covenant test in breach", "b360.evidence"))
    liq = {}
    if ret >= T["returned_liquidity"]:
        liq["returned_payments_q"] = ret
    if c.get("buffer_months") is not None and c["buffer_months"] < T["buffer_months"]:
        liq["buffer_months"] = c["buffer_months"]
    if c.get("inflow_trend_pct") is not None and c["inflow_trend_pct"] <= T["inflow_fall_pct"]:
        liq["inflow_trend_pct"] = c["inflow_trend_pct"]
    if liq:
        out.append(_ind("SICR-LIQUIDITY", "sicr", "soft", "7.11", "a",
                        "Rising liquidity risk in account conduct (" + ", ".join(
                            {"returned_payments_q": "returned payments", "buffer_months": "balance buffer under 1 month",
                             "inflow_trend_pct": "inflows down 30%+"}[k] for k in liq) + ")",
                        liq, "returned ≥ 2, buffer < 1 month or inflows ≤ −30% y/y", "conduct.account"))
    if o.get("dscr_x") is not None and float(o["dscr_x"]) < T["dscr"]:
        out.append(_ind("SICR-FINANCIALS", "sicr", "soft", "7.11", "a", f"DSCR {float(o['dscr_x']):.2f}x, under 1.0x",
                        {"dscr_x": o["dscr_x"], "leverage_x": o.get("leverage_x")}, "DSCR < 1.0x", "b360.evidence"))
    if fall is not None and T["collateral_fall_utp"] < fall <= T["collateral_fall_sicr"]:
        out.append(_ind("SICR-COLLATERAL", "sicr", "soft", "7.11", "b", f"Collateral value down {-fall:.0f}% on the quarter",
                        {"market_value_sar_mn": col.get("market_value"), "market_value_prior": col.get("market_value_prior"),
                         "value_change_pct": fall}, "market value down 10% or more q/q", "b360.evidence"))
    if peers.get("sector_stress"):
        # Context, not a count: a sector move alone does not make a name SICR; it tells the reader it is not alone.
        out.append(_ind("SICR-SECTOR", "sicr", "context", "7.11", "c",
                        f"Economic difficulty in the sector: {peers.get('warned_share_pct', 0):.0f}% of peers warned "
                        f"(book {peers.get('book_warned_share_pct', 0):.0f}%) and rising",
                        {k: peers.get(k) for k in ("names", "warned", "warned_share_pct", "warned_share_prior_pct",
                                                   "book_warned_share_pct")},
                        "warned share ≥ 1.5× book and rising", "ews.sector_peers"))
    notches = x.get("notches")
    if notches is not None and -float(notches) >= T["downgrade_notches"]:
        out.append(_ind("SICR-DOWNGRADE", "sicr", "soft", "7.11", "e",
                        f"Downgraded {int(-float(notches))} notches this quarter ({o.get('rating_previous')} to {o.get('rating_current')})",
                        {"rating_notches_moved": notches, "rating_previous": o.get("rating_previous"),
                         "rating_current": o.get("rating_current")}, "≥ 2 notches down", "b360.evidence"))
    if int(b.get("external_dpd_days") or 0) > T["bureau_dpd"] and not b.get("external_default"):
        out.append(_ind("SICR-BUREAU", "sicr", "soft", "7.11", "e",
                        f"Past due {int(b['external_dpd_days'])} days at another lender (bureau)",
                        {"external_dpd_days": b["external_dpd_days"], "external_exposure_sar_mn": b.get("external_exposure_sar_mn")},
                        "> 30 DPD at another lender", "bureau.external"))
    if g.get("worst_other_stage") is not None and int(g["worst_other_stage"]) >= 3:
        out.append(_ind("SICR-GROUP", "sicr", "soft", "7.11", "h",
                        f"Another member of {g.get('group_name') or 'the group'} is in default (Stage {g['worst_other_stage']})",
                        {"group_id": g.get("group_id"), "member": g.get("worst_other"), "stage": g["worst_other_stage"]},
                        "a group member at Stage 3 (proxy for a parent worse than SICR)", "b360.evidence"))
    return out


__all__ = ["THRESHOLDS", "assess", "assess_retail", "cite", "clauses"]
