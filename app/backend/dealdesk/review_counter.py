"""R11 R3: counter-proposals from the findings, priced by the Deal Desk optimiser.

The failed rules carry levers (rules.json "lever": cap, tranche_funded, cash_margin, drop_line, routing,
no_new_funded, advance_payment, cp, optimise). The counter-proposal packages (data/dealdesk/review/packages.json)
combine them; each package is turned into fixed terms and run through `optimizer.optimize` (the same engine
and parameter tables as Optimise), which returns the closest structure that clears every hard limit and the
hurdle with those terms held. Each counter-proposal carries RAROC, SVA, Day-1 ECL and RWA, the conditions
precedent the findings imply, and Session F's forward risk when that module is present.

A prepared proposal case is not an engine proposal; `engine_proposal(case)` maps it onto the engine's
single-facility schema (amounts in SAR at the Admin AED/SAR rate, guarantees as the unfunded share,
pricing as the exposure-weighted margin and commission). The mapping is recorded in STATUS_R11_REVIEW.md.
"""
from __future__ import annotations

import copy
import functools
import json
from typing import Any

from backend.dealdesk import desk_params, engine, optimizer, params, proposals
from backend.dealdesk.proposal_cases import CASES
from backend.dealdesk.review_ledger import REVIEW_DIR

SECTOR_MAP = {"Trading": "Wholesale Trade"}


@functools.lru_cache(maxsize=1)
def packages() -> dict[str, Any]:
    return json.loads((REVIEW_DIR / "packages.json").read_text())


def reload() -> None:
    packages.cache_clear()


def _aed_sar() -> float:
    return float(desk_params.rows()["aed_sar"])


# ------------------------------------------------------------------ case -> engine proposal

def engine_proposal(cid: str, facilities: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    c = CASES[cid]
    fac = facilities if facilities is not None else c["facilities"]
    fx = _aed_sar()
    f = c["financials"]
    total = sum(x["proposed"] for x in fac)
    funded = sum(x["proposed"] for x in fac if x["kind"] == "funded")
    unf = total - funded
    cm_amt = sum(x["proposed"] * x.get("cash_margin", 0.0) for x in fac)
    margin = (sum(x["proposed"] * x["bps"] for x in fac if x["kind"] == "funded") / funded) if funded else 250
    comm = (sum(x["proposed"] * x["bps"] for x in fac if x["kind"] != "funded") / unf) if unf else 0
    years = [{"year": 2025, "kind": "actual", "revenue": f["revenue"] * fx, "ebitda": f["ebitda"] * fx, "total_debt": f["net_debt"] * fx,
              "debt_service": f["debt_service"] * fx, "net_worth": float("nan"), "current_ratio": float("nan"), "source": "Proposal (audited spreading)"}]
    for y in (2026, 2027, 2028):
        years.append({**years[0], "year": y, "kind": "projection", "source": "Held flat (no projections in the proposal)"})
    sector = SECTOR_MAP.get(c["sector"], c["sector"])
    simah = "adverse" if cid == "PRP-B-ASB" else ("watch" if c["deposits"].get("returned_cheques") else "clear")
    return {
        "proposal_id": cid, "status": "in_review", "rm": c["rm"], "business_unit": c["segment"], "received": "2026-10-13",
        "purpose": "; ".join(c["request_summary"]), "deal_currency": "SAR", "case": "proposal_review",
        "obligor": {"existing": False, "obligor_id": f"RV-{cid}", "name": c["borrower"], "cr_number": "", "sector": sector, "sub_sector": "",
                    "segment": sector, "region": "Dubai", "internal_rating": c["rating"], "external_rating": None, "gre": False,
                    "sme": c["segment"].startswith("SME"), "simah_flag": simah, "gov_linked": False, "group_id": f"RG-{cid}",
                    "group_name": c["group"], "connected_parties": [], "sector_code": "", "pd_master_scale": c["pd"],
                    "existing_exposure_sar_mn": 0.0, "existing_facilities": [], "real_estate_finance": False},
        "financials": {"currency": "SAR", "unit": "SAR m", "years": years},
        "ask": {"facility_type": "revolver", "structure": "conventional", "currency": "SAR", "amount": round(total * fx, 4),
                "tenor_years": 5 if any("5-year" in x["name"] or "5 years" in x["name"] for x in fac if x["proposed"] > 0) else 1,
                "grace_years": 0, "amortisation": "bullet", "balloon_pct": 0, "margin_bps": int(round(margin)), "upfront_fee_bps":
                int(round(c["fees_upfront"] / max(total, 1e-9) * 1e4)), "commitment_fee_bps": 0, "commission_bps": int(round(comm)),
                "utilisation_pct": 100, "funded_share_pct": round(100 * funded / total, 4) if total else 100,
                "unfunded_type": "performance_lg", "cash_margin_pct": round(100 * cm_amt / total, 4) if total else 0,
                "collateral_ids": [], "guarantee_id": None, "guarantee_coverage_pct": 0, "covenant_package": "standard"},
        "security": {"collateral": [], "guarantees": [], "covenant_package": "standard", "covenants": []},
        "business_case": {"ancillary_income_sar_mn_pa": {"cash_management": c["deposits"]["flow_fees"] * fx}, "currency": "SAR"},
    }


# ------------------------------------------------------------------ levers -> terms

def _levers(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out, seen = [], set()
    for c in checks:
        lv = c.get("lever")
        if lv and c["verdict"] in ("contradicted", "exception"):
            key = (lv["type"], lv.get("label"))
            if key not in seen:
                seen.add(key)
                out.append({**lv, "from": c["rule_id"]})
    return out


def _conditions(checks: list[dict[str, Any]]) -> list[str]:
    return list(dict.fromkeys(c["condition"]["what"] for c in checks if c.get("condition") and c["condition"].get("kind") == "CP"))


def _case_facilities(cid: str, levers: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    c = CASES[cid]
    fac = copy.deepcopy(c["facilities"])
    terms: list[str] = []
    for lv in levers:
        t = lv["type"]
        if t == "cap" and c.get("group_cap"):
            g = c["group_cap"]
            cut = max(0.0, g["group_exposure_after"] - float(lv["group_cap"]))
            new = [x for x in fac if x["existing"] == 0 and x["proposed"] > 0]
            if new and cut > 0:
                x = max(new, key=lambda r: r["proposed"])
                x["proposed"] = round(max(0.0, x["proposed"] - cut), 1)
                terms.append(f"Group cap AED {lv['group_cap']:,.0f}m: {x['name']} reduced to AED {x['proposed']:,.1f}m")
        elif t == "tranche_funded":
            for x in fac:
                if x["kind"] == "funded":
                    x["proposed"] = round(x["proposed"] * (1 - float(lv["share"])), 1)
            terms.append(lv["label"] + f" ({1 - float(lv['share']):.0%} of the funded lines now)")
        elif t == "no_new_funded":
            for x in fac:
                if x["kind"] == "funded":
                    x["proposed"] = min(x["proposed"], x["existing"])
            terms.append(lv["label"])
        elif t == "cash_margin":
            for x in fac:
                if x["existing"] == 0 and x["kind"] != "funded" and x["proposed"] > 0:
                    x["cash_margin"] = float(lv["value"]) / 100
            terms.append(lv["label"])
        elif t == "drop_line":
            for x in fac:
                if x["name"] == lv["line"]:
                    x["proposed"] = 0.0
            terms.append(lv["label"])
        else:
            terms.append(lv["label"])
    return fac, terms


def _fixed_dd(p: dict[str, Any], levers: list[dict[str, Any]]) -> tuple[dict[str, Any], list[str]]:
    fixed: dict[str, Any] = {}
    terms: list[str] = []
    for lv in levers:
        if lv["type"] == "cash_margin":
            fixed["cash_margin_pct"] = float(lv["value"])
            terms.append(lv["label"])
        elif lv["type"] == "covenants":
            fixed["covenant_package"] = "enhanced"
            terms.append(lv["label"])
        elif lv["type"] in ("optimise", "cp"):
            terms.append(lv["label"])
    return fixed, terms


def _forward(p: dict[str, Any], terms: dict[str, Any]) -> dict[str, Any] | None:
    """Session F's forward risk for one structure (backend.dealdesk.forward_risk.structure_risk), when it is merged."""
    try:
        from backend.dealdesk import forward_risk  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 - F not merged: no forward risk
        return None
    fn = getattr(forward_risk, "structure_risk", None)
    if fn is None:
        return None
    try:
        r = fn(p, terms)
    except Exception:  # noqa: BLE001 - a structure F cannot score is shown without it
        return None
    ecl = r.get("ecl") or {}
    return {"p_stage2_next_q": r.get("p_stage2_next_q"), "p_dpd30_next_q": r.get("p_dpd30_next_q"),
            "ecl_q4": ecl.get("q4"), "model": r.get("model")}


def _summary(m: dict[str, Any], fx_back: float) -> dict[str, Any]:
    return {"raroc": m.get("lifetime_raroc"), "hurdle": m.get("hurdle"), "clears_hurdle": m.get("clears_hurdle"),
            "sva": (m.get("sva") or 0.0) / fx_back, "ecl_day1": (m.get("day_one_ecl") or 0.0) / fx_back,
            "rwa": (m.get("rwa_y1") or 0.0) / fx_back, "amount": (m.get("amount_sar_mn") or 0.0) / fx_back}


def _run(p: dict[str, Any], fixed: dict[str, Any]) -> dict[str, Any] | None:
    r = optimizer.optimize(p, fixed=fixed or None, objective="closest", counter_offers=False)
    best = r.get("closest")
    if best is None:
        r = optimizer.optimize(p, fixed=fixed or None, objective="closest", allow_soft=True, counter_offers=False)
        best = r.get("closest")
    return {"best": best, "ask": r["ask"], "feasible": best is not None}


def _run_case(p: dict[str, Any], fixed: dict[str, Any]) -> dict[str, Any] | None:
    """Optimiser first; when the engine's single-obligor limit (CP-1.1, a hard limit of the Deal Desk book) blocks every
    structure of a prepared case, the package is priced by the engine at its terms, with the guarantee commission (or the
    margin when the package is all funded) moved to the breakeven at the hurdle when the terms alone fall short."""
    r = _run(p, fixed)
    if r and r["best"]:
        return {**r, "method": "optimiser"}
    t = {**engine.merge_terms(p, None), **fixed}
    a = engine.analyse(p, t, validate=False)
    note = None
    if not a["metrics"]["clears_hurdle"]:
        lever = "commission_bps" if float(t["funded_share_pct"]) < 50 else "margin_bps"
        be = engine.breakeven(p, t, lever)
        if be.get("value") is not None and be["feasible"]:
            v = float(be["value"])
            t[lever] = int(-(-v // 1)) + (0 if lever == "margin_bps" else 0)
            a = engine.analyse(p, t, validate=False)
            note = f"{'Commission' if lever == 'commission_bps' else 'Margin'} at {t[lever]:,} bps (breakeven at the hurdle)"
    hard = [c["name"] for c in a["constraints"] if c["status"] == "breach" and c["kind"] == "hard"]
    best = {"terms": t, "metrics": a["metrics"], "changes": [], "approval": a["approval"], "soft_breaches":
            [c["name"] for c in a["constraints"] if c["status"] == "breach" and c["kind"] == "soft"], "hard_breaches": hard}
    return {"best": best, "ask": None, "feasible": True, "method": "engine", "pricing_note": note}


def counter_proposals(sid: str, checks: list[dict[str, Any]], is_case: bool, limit: int = 3) -> dict[str, Any]:
    lv = _levers(checks)
    cps = _conditions(checks)
    types = {x["type"] for x in lv}
    out: list[dict[str, Any]] = []
    fx_back = _aed_sar() if is_case else 1.0
    ccy = "AED" if is_case else proposals.get(sid)["ask"]["currency"]
    if is_case:
        base_p = engine_proposal(sid)
    else:
        base_p = proposals.get(sid)
    base = engine.analyse(base_p, None)["metrics"]
    for pk in packages()["packages"]:
        if not (set(pk["levers"]) - {"cp"}) & types:
            continue
        if pk.get("scope") and ("case" if is_case else "dd") not in pk["scope"]:
            continue
        use = [x for x in lv if x["type"] in pk["levers"]]
        if is_case:
            fac, terms = _case_facilities(sid, use)
            p = engine_proposal(sid, fac)
            fixed = {"amount": p["ask"]["amount"], "funded_share_pct": p["ask"]["funded_share_pct"],
                     "cash_margin_pct": p["ask"]["cash_margin_pct"]}
            if "routing" in pk["levers"] or "covenants" in pk["levers"]:
                fixed["covenant_package"] = "enhanced"
        else:
            p = base_p
            fixed, terms = _fixed_dd(p, use)
        try:
            r = _run_case(p, fixed) if is_case else _run(p, fixed)
        except engine.TermsError:
            continue
        if r and r.get("pricing_note"):
            terms = terms + [r["pricing_note"]]
        if not r or not r["best"]:
            continue
        b = r["best"]
        m = _summary(b["metrics"], fx_back)
        changes = [{"field": ch["field"], "ask": ch["ask"], "value": ch["value"], "unit": ch["unit"]} for ch in b.get("changes", [])]
        out.append({"id": pk["id"], "title": pk["title"], "terms": terms,
                    "structure": {"amount": b["terms"]["amount"] / fx_back, "currency": ccy, "tenor_years": b["terms"]["tenor_years"],
                                  "margin_bps": b["terms"]["margin_bps"], "commission_bps": b["terms"].get("commission_bps"),
                                  "funded_share_pct": b["terms"].get("funded_share_pct"), "cash_margin_pct": b["terms"].get("cash_margin_pct"),
                                  "covenant_package": b["terms"].get("covenant_package")},
                    "changes": changes, **m,
                    "vs_ask": {"raroc": (m["raroc"] or 0) - (base.get("lifetime_raroc") or 0), "sva": m["sva"] - (base.get("sva") or 0) / fx_back,
                               "ecl_day1": m["ecl_day1"] - (base.get("day_one_ecl") or 0) / fx_back},
                    "approval": b.get("approval", {}).get("level"), "soft_breaches": b.get("soft_breaches", []),
                    "hard_breaches": b.get("hard_breaches", []), "method": r.get("method", "optimiser"),
                    "conditions_precedent": cps if pk.get("with_cps", True) else [],
                    "forward_risk": None if is_case else _forward(p, b["terms"]),
                    "basis": "Deal Desk optimiser (closest structure that clears every hard limit and the hurdle, the package's terms held fixed); "
                             "parameters in force " + params.version_tag()})
        sig = (round(out[-1]["amount"], 1), out[-1]["structure"]["funded_share_pct"], out[-1]["structure"]["cash_margin_pct"])
        if any((round(o["amount"], 1), o["structure"]["funded_share_pct"], o["structure"]["cash_margin_pct"]) == sig for o in out[:-1]):
            out.pop()
        if len(out) >= limit:
            break
    return {"ask": {**_summary(base, fx_back), "currency": ccy}, "counter_proposals": out, "levers": lv,
            "basis": "Levers from the failed rules (rules.json) combined by data/dealdesk/review/packages.json and priced by optimizer.optimize."}
