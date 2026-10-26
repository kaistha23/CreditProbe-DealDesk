"""The risk manager's full lever set (PLAN_R5 D4, Anne's lever list, screens 16-17).

Each lever has a group (the term panel's sections), the RAROC channel it moves, the owned
parameter table that drives it (with its source), its neutral value (what a proposal that does
not use it carries, so the engine's earlier results are unchanged) and its bounds, which come from
the market (pricing, by rating bucket) and from policy (limits, catalogues).

`catalogue(p)` is what `/meta` and the term panel read for a proposal; `bounds(p, key)` is what the
optimiser and the single-lever search use.
"""
from __future__ import annotations

from typing import Any

from backend.dealdesk import params
from backend.dealdesk.seed import GRADES, bucket

GROUPS = ("Pricing", "Structure", "Risk mitigation", "Covenants and conditions", "Relationship")

#: neutral values of the levers added in R5 (a proposal that does not set them carries these)
NEUTRAL: dict[str, Any] = {
    "prepayment_fee_bps": 0, "rate_type": "floating", "hold_pct": 100, "insurance_cover_pct": 0,
    "receivables_assignment_pct": 0, "covenant_items": [], "review_cycle_months": 12, "cross_sell": [],
    "margin_ratchet_bps_per_notch": 0,  # R12-I
    # Round D: the Deposit requirement term (backend/dealdesk/deposit_requirement/term.py)
    "deposit_type": "none", "deposit_pct": 0, "deposit_amount": 0, "deposit_tenor_months": 0, "deposit_facility": "",
}

#: key, label, group, channel, parameter table, unit, kind
_LEVERS: list[tuple[str, str, str, str, str, str, str]] = [
    ("margin_bps", "Margin over SAIBOR / SOFR", "Pricing", "Income", "market_bounds", "bps", "continuous"),
    ("upfront_fee_bps", "Upfront / arrangement fee", "Pricing", "Income (front-loaded: helps short tenors most)", "market_bounds", "bps", "continuous"),
    ("commitment_fee_bps", "Commitment fee on undrawn", "Pricing", "Income on undrawn exposure", "market_bounds", "bps", "continuous"),
    ("commission_bps", "LG/LC commission", "Pricing", "Income on unfunded exposure", "market_bounds", "bps", "continuous"),
    # R12-I: Book feedback to origination
    ("margin_ratchet_bps_per_notch", "Rating-linked margin ratchet", "Pricing",
     "Income: the margin steps with each notch of migration (prices the expected migration)", "pricing_behaviour", "bps per notch", "continuous"),
    ("prepayment_fee_bps", "Prepayment / early settlement fee", "Pricing", "Income (protects lifetime income)", "pricing_behaviour", "bps", "continuous"),
    ("tenor_years", "Tenor", "Structure", "FTP, PD horizon, IRB maturity", "risk_appetite", "years", "discrete"),
    ("amortisation", "Amortisation profile", "Structure", "Average exposure: EL and capital", "pricing_behaviour", "", "choice"),
    ("balloon_pct", "Balloon share", "Structure", "Average exposure: EL and capital", "risk_appetite", "%", "continuous"),
    ("grace_years", "Grace period", "Structure", "Average exposure (lengthens it)", "risk_appetite", "years", "discrete"),
    ("amount", "Amount", "Structure", "Concentration and capital", "market_bounds", "m", "continuous"),
    ("hold_pct", "Hold level (sell-down)", "Structure", "Concentration and capital; arranger skim on the sold share", "pricing_behaviour", "%", "continuous"),
    ("facility_type", "Facility type", "Structure", "CCF, so EAD and RWA", "structures", "", "choice"),
    ("funded_share_pct", "Funded share", "Structure", "CCF, so EAD and RWA", "ccf", "%", "continuous"),
    ("structure", "Islamic structure", "Structure", "LGD (structure adjustment)", "lgd", "", "choice"),
    ("rate_type", "Fixed or floating rate", "Structure", "FTP (ALM fixed-rate premium); client DSCR under rate stress", "pricing_behaviour", "", "choice"),
    ("cash_margin_pct", "Cash margin / cash collateral", "Risk mitigation", "EAD net of cash, so RWA and LGD", "lgd", "%", "continuous"),
    # Round D: "require a deposit" (lien-marked cash, or operating balances for the relationship)
    ("deposit_type", "Deposit requirement: lien-marked cash or operating balances", "Risk mitigation",
     "Lien-marked cash: EAD net of the deposit, so LGD, RWA and EL; operating balances: funding value in relationship RAROC", "lgd", "", "choice"),
    ("deposit_pct", "Deposit requirement (% of limit)", "Risk mitigation",
     "Lien-marked cash: EAD net of the deposit, so LGD, RWA and EL; operating balances: funding value in relationship RAROC", "lgd", "% of limit", "continuous"),
    ("collateral_ids", "Collateral package (type and LTV)", "Risk mitigation", "LGD; capital only if eligible CRM", "lgd", "", "set"),
    ("guarantee_id", "Guarantee (parent, bank, sovereign, ECA)", "Risk mitigation", "PD substitution on the covered part", "credit_protection", "", "choice"),
    ("guarantee_coverage_pct", "Guarantee cover", "Risk mitigation", "PD substitution on the covered part", "credit_protection", "%", "continuous"),
    ("insurance_cover_pct", "Credit insurance cover", "Risk mitigation", "LGD and capital relief (premium is a cost)", "credit_protection", "%", "continuous"),
    ("receivables_assignment_pct", "Assignment of contract proceeds / receivables", "Risk mitigation", "LGD", "credit_protection", "%", "continuous"),
    ("covenant_package", "Covenant package", "Covenants and conditions", "PD and LGD overlay", "covenant_packages", "", "choice"),
    ("covenant_items", "Covenants: leverage, DSCR, cash sweep, dividend lock-up, negative pledge", "Covenants and conditions",
     "PD and LGD overlay (capped)", "covenant_items", "", "set"),
    ("review_cycle_months", "Review cycle", "Covenants and conditions", "PD (early trigger) and effective maturity", "covenant_items", "months", "choice"),
    ("cross_sell", "Cross-sell commitments", "Relationship", "Relationship RAROC, not deal RAROC", "relationship", "", "set"),
]


def table_source(name: str) -> dict[str, Any]:
    t = params.table(name)
    return {"table": name, "owner": t["owner"], "version": t["version"], "source": t.get("source") or t.get("policy") or t.get("description", "")}


def guarantee_options(p: dict[str, Any]) -> list[dict[str, Any]]:
    """The obligor's own guarantees plus the protection the risk manager may ask for."""
    out = [{"id": g["guarantee_id"], "label": f"{g.get('guarantor') or g['type'].title()} ({g['type']}, {g['guarantor_rating']})",
            "type": g["type"], "rating": g["guarantor_rating"], "offered": bool(g.get("offered_in_ask")), "requested": False}
           for g in p["security"]["guarantees"]]
    cat = params.rows("credit_protection")["guarantee_catalogue"]
    for gid, c in cat.items():
        if c.get("requires_group") and not p["obligor"].get("group_id"):
            continue
        out.append({"id": gid, "label": c["label"], "type": c["type"], "rating": requested_rating(p, gid), "offered": False, "requested": True})
    return out


def requested_rating(p: dict[str, Any], gid: str) -> str:
    c = params.rows("credit_protection")["guarantee_catalogue"][gid]
    if c.get("rating"):
        return c["rating"]
    i = GRADES.index(p["obligor"]["internal_rating"])
    return GRADES[max(0, i - int(c.get("rating_uplift_notches", 1)))]


def bounds(p: dict[str, Any], key: str) -> dict[str, Any]:
    """Market and policy bounds of one lever for this proposal."""
    mb = params.rows("market_bounds")
    bk = bucket(p["obligor"]["internal_rating"])
    ask = p["ask"]
    pb = params.rows("pricing_behaviour")
    cp = params.rows("credit_protection")
    ra = {x["name"]: x for x in params.rows("risk_appetite")}
    if key in ("margin_bps", "upfront_fee_bps", "commitment_fee_bps", "commission_bps"):
        lo, hi = mb["by_bucket"][bk][key]
        if key == "margin_bps":
            add = mb.get("sector_margin_addon_bps", {}).get(p["obligor"]["sector"], 0)
            lo, hi = lo + add, hi + add
        a = float(ask.get(key, 0))
        return {"min": min(lo, a), "max": max(hi, a), "source": "market"}
    if key == "prepayment_fee_bps":
        return {"min": 0, "max": pb["prepayment_fee_max_bps"], "source": "market"}
    if key == "margin_ratchet_bps_per_notch":  # R12-I
        return {"min": 0, "max": pb.get("margin_ratchet_max_bps_per_notch", 0), "source": "market"}
    if key == "tenor_years":
        return {"min": 1, "max": int(ra["max_tenor"]["limits"][bk]), "source": "policy"}
    if key == "grace_years":
        return {"min": 0, "max": max(0, int(ask["tenor_years"]) - 1), "source": "policy"}
    if key == "balloon_pct":
        return {"min": 0, "max": float(ra["balloon"]["limit"]) * 100, "source": "policy"}
    if key == "amount":
        return {"min": float(ask["amount"]) * float(mb["min_amount_share"]), "max": float(ask["amount"]), "source": "policy"}
    if key == "hold_pct":
        return {"min": float(pb["hold_min_pct"]), "max": 100, "source": "policy"}
    if key == "cash_margin_pct":
        return {"min": 0, "max": 30, "source": "market"}
    if key == "guarantee_coverage_pct":
        return {"min": 0, "max": 100, "source": "policy"}
    if key == "deposit_pct":  # Round D: the lien-marked deposit's bounds (lgd.collateral.lien_deposit); operating balances' in relationship
        lien = params.rows("lgd")["collateral"].get("lien_deposit") or {}
        relb = params.rows("relationship").get("deposit_requirement") or {}
        typ = ask.get("deposit_type") or "none"
        hi = float(relb.get("max_pct", 50)) if typ == "relationship" else float(lien.get("max_pct", 30))
        return {"min": 0, "max": max(hi, float(ask.get("deposit_pct") or 0)), "source": "policy",
                "by_type": {"lien_cash": [0, float(lien.get("max_pct", 30))], "relationship": [0, float(relb.get("max_pct", 50))]}}
    if key == "insurance_cover_pct":
        return {"min": 0, "max": float(cp["credit_insurance"]["max_cover_pct"]), "source": "market"}
    if key == "receivables_assignment_pct":
        return {"min": 0, "max": float(cp["receivables_assignment"]["max_pct"]), "source": "policy"}
    if key == "funded_share_pct":
        return {"min": 0, "max": 100, "source": "policy"}
    return {}


def options(p: dict[str, Any], key: str) -> list[Any]:
    if key == "amortisation":
        return ["equal", "sculpted", "balloon", "bullet"]
    if key == "rate_type":
        return ["floating", "fixed"]
    if key == "deposit_type":  # Round D
        return ["none", "lien_cash", "relationship"]
    if key == "review_cycle_months":
        return [12, 6, 3]
    if key == "covenant_items":
        return list(params.rows("covenant_items")["items"])
    if key == "cross_sell":
        return list(p.get("business_case", {}).get("ancillary_income_sar_mn_pa", {}))
    if key == "guarantee_id":
        return [None] + [g["id"] for g in guarantee_options(p)]
    if key == "covenant_package":
        return list(params.rows("covenant_packages")["packages"])
    if key == "facility_type":
        return list(params.rows("structures"))[:5]
    if key == "structure":
        return list(params.rows("structures").get(p["ask"]["facility_type"], []))
    if key == "collateral_ids":
        return [c["collateral_id"] for c in p["security"]["collateral"]]
    return []


def catalogue(p: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    out = []
    for key, label, group, channel, tab, unit, kind in _LEVERS:
        row = {"key": key, "label": label, "group": group, "channel": channel, "unit": unit, "kind": kind,
               "parameters": table_source(tab), "neutral": NEUTRAL.get(key)}
        if p is not None:
            row["bounds"] = bounds(p, key)
            row["options"] = options(p, key)
            row["ask"] = p["ask"].get(key, NEUTRAL.get(key))
        out.append(row)
    return out


__all__ = ["GROUPS", "NEUTRAL", "catalogue", "bounds", "options", "guarantee_options", "requested_rating"]
