"""Marginal risk-appetite and regulatory limits, and the Delegation of Authority (spec 3.5).

Every portfolio limit is measured after the deal: the live corporate book (portfolio.snapshot)
plus the deal's year-1 EAD (SAR million), including the borrower's own existing exposure and
its connected group's. Each result: value, limit, headroom, hard/soft, pass/breach.
"""
from __future__ import annotations

from typing import Any

from backend.dealdesk import params, portfolio
from backend.dealdesk.seed import GRADES, bucket
from backend.v5common.ratings import rank

DEFINITIONS = {
    "single_name": "Obligor EAD after the deal (existing book EAD + the deal's year-1 EAD) against the single obligor limit.",
    "group_connected": "Connected group EAD after the deal (the group's book EAD + the deal) against the connected group limit.",
    "group_large_exposure": "Connected group EAD after the deal against 25% of Tier 1 (SAMA large exposures).",
    "sector_policy": "Sector share of the corporate book after the deal: (sector EAD + deal) / (book EAD + deal).",
    "sector_appetite": "Sector share after the deal against the risk-appetite sector cap, where the sector has one.",
    "rating_bucket": "Share of the book in the obligor's rating bucket after the deal.",
    "collateral_type": "Share of book EAD secured by the collateral type after the deal (deals pledging that type).",
    "min_rating": "The obligor's internal rating against the minimum rating for new money.",
    "max_tenor": "Tenor against the maximum tenor for the obligor's rating bucket.",
    "ltv": "Real-estate finance: funded amount / market value of the real estate pledged.",
    "dscr": "Latest actual EBITDA / (existing debt service + the deal's largest scheduled annual debt service).",
    "debt_ebitda": "(Latest actual total debt + funded amount) / latest actual EBITDA.",
    "balloon": "Share of a term loan repaid at maturity (bullet = 100%).",
    "bu_rwa_budget": "The deal's year-1 RWA against the Corporate Banking new-business RWA headroom.",
    "bu_el_budget": "The deal's year-1 expected loss against the new-business EL headroom.",
    "structure": "The Islamic structure must be allowed for the facility type; Ijara needs an asset (real estate or plant).",
}


def _limits() -> dict[str, dict[str, Any]]:
    return {x["name"]: x for x in params.rows("risk_appetite")}


def _row(name: str, label: str, scope: str, value: Any, limit: Any, kind: str, unit: str, basis: str,
         higher_is_worse: bool = True, before: Any = None, deal: Any = None) -> dict[str, Any]:
    if value is None or limit is None:
        status, head = "pass", None
    elif unit == "rating":
        head = rank(limit) - rank(value)
        status = "pass" if head >= 0 else "breach"
    else:
        head = (limit - value) if higher_is_worse else (value - limit)
        status = "pass" if head >= -1e-9 else "breach"
    return {"name": name, "label": label, "scope": scope, "value": value, "limit": limit, "headroom": head, "unit": unit,
            "kind": kind, "status": status, "basis": basis, "before": before, "deal": deal}


def evaluate(p: dict[str, Any], a: dict[str, Any]) -> list[dict[str, Any]]:
    L = _limits()
    s = portfolio.snapshot()
    ob = p["obligor"]
    t = a["terms"]
    m = a["metrics"]
    deal = float(m["ead_y1"])
    tot = s["total_ead"] + deal
    out = []

    x = L["single_name"]
    before = portfolio.obligor_ead(ob["obligor_id"]) if ob.get("existing") else 0.0
    out.append(_row("single_name", x["label"], ob["name"], before + deal, x["limit"], x["kind"], x["unit"], x["basis"], before=before, deal=deal))

    gb = portfolio.group_ead(ob.get("group_id"))
    if not ob.get("existing") and not str(ob.get("group_id", "")).startswith("CG"):
        gb = 0.0
    gx = _group_limits(p)  # R12-C: the group's approved cap and, for a group outside the book, its Data Domains exposure
    if gx and gx.get("before_sar_mn") is not None and gb == 0.0:  # R12-C
        gb = float(gx["before_sar_mn"])  # R12-C
    x = L["group_connected"]
    out.append(_row("group_connected", x["label"], ob.get("group_name", ""), gb + deal, x["limit"], x["kind"], x["unit"], x["basis"], before=gb, deal=deal))
    gcap = (gx or {}).get("cap")  # R12-C: an approved group exposure cap tighter than the connected group limit binds instead
    if gcap is not None and gcap["limit_sar_mn"] < float(x["limit"]) - 1e-9:  # R12-C
        out[-1] = _row("group_connected", f"{x['label']} (approved cap)", ob.get("group_name", ""), gb + deal,  # R12-C
                       gcap["limit_sar_mn"], x["kind"], x["unit"], _cap_basis(gcap, x), before=gb, deal=deal)  # R12-C
        out[-1]["cap"] = gcap  # R12-C
    x = L["group_large_exposure"]
    t1 = float(params.rows("capital")["tier1_sar_mn"])
    out.append(_row("group_large_exposure", x["label"], ob.get("group_name", ""), gb + deal, x["limit_pct_tier1"] * t1, x["kind"],
                    x["unit"], f"{x['basis']} (Tier 1 SAR {t1:,.0f}m)", before=gb, deal=deal))

    sec = ob["sector"]
    sb = float(s["by_sector"].get(sec, 0.0))
    share = (sb + deal) / tot
    x = L["sector_policy"]
    out.append(_row("sector_policy", x["label"], sec, share, x["limit"], x["kind"], x["unit"], x["basis"], before=sb / s["total_ead"], deal=deal))
    x = L["sector_appetite"]
    if sec in x["limits"]:
        out.append(_row("sector_appetite", x["label"], sec, share, x["limits"][sec], x["kind"], x["unit"], x["basis"], before=sb / s["total_ead"], deal=deal))

    bk = bucket(ob["internal_rating"])
    x = L["rating_bucket"]
    bb = float(s["by_bucket"].get(bk, 0.0))
    out.append(_row("rating_bucket", x["label"], bk, (bb + deal) / tot, x["limits"][bk], x["kind"], x["unit"], x["basis"],
                    before=bb / s["total_ead"], deal=deal))

    x = L["collateral_type"]
    types = {c["type"] for c in a["lgd"]["collateral"]}
    for ct, lim in x["limits"].items():
        if ct in types:
            cb = float(s["by_collateral"].get(ct, 0.0))
            out.append(_row("collateral_type", x["label"], ct.replace("_", " "), (cb + deal) / tot, lim, x["kind"], x["unit"], x["basis"],
                            before=cb / s["total_ead"], deal=deal))

    x = L["min_rating"]
    r = ob["internal_rating"]
    kind = x["kind"]
    if ob.get("existing") and rank(x["existing"]) < rank(r) <= rank(x["existing_soft"]):
        kind = "soft"
    out.append(_row("min_rating", x["label"], r, r, x["existing"] if ob.get("existing") else x["new_to_bank"], kind, "rating", x["basis"]))
    if kind == "soft":
        out[-1]["limit"] = x["existing_soft"]
        out[-1]["status"] = "breach"

    x = L["max_tenor"]
    out.append(_row("max_tenor", x["label"], bk, int(t["tenor_years"]), x["limits"][bk], x["kind"], x["unit"], x["basis"]))

    x = L["ltv"]
    if ob.get("real_estate_finance"):
        ltv = m.get("ltv")
        out.append(_row("ltv", x["label"], "real-estate finance", 9.99 if ltv is None else ltv, x["limit"], x["kind"], x["unit"], x["basis"]))

    x = L["dscr"]
    out.append(_row("dscr", x["label"], ob["name"], m["dscr_post"], x["limit"], x["kind"], x["unit"], x["basis"], higher_is_worse=False))
    x = L["debt_ebitda"]
    out.append(_row("debt_ebitda", x["label"], ob["name"], m["debt_ebitda_post"], x["limit"], x["kind"], x["unit"], x["basis"]))

    if t["facility_type"] == "term_loan":
        x = L["balloon"]
        bal = 1.0 if t["amortisation"] == "bullet" else float(t["balloon_pct"]) / 100 if t["amortisation"] == "balloon" else 0.0
        out.append(_row("balloon", x["label"], "term loan", bal, x["limit"], x["kind"], x["unit"], x["basis"]))

    x = L["bu_rwa_budget"]
    out.append(_row("bu_rwa_budget", x["label"], p.get("business_unit", "Corporate Banking"), float(m["rwa_y1"]), x["headroom_sar_mn"],
                    x["kind"], x["unit"], x["basis"]))
    x = L["bu_el_budget"]
    out.append(_row("bu_el_budget", x["label"], p.get("business_unit", "Corporate Banking"), float(m["el_y1"]), x["headroom_sar_mn"],
                    x["kind"], x["unit"], x["basis"]))

    st = params.rows("structures")
    ok = t["structure"] in st[t["facility_type"]]
    if ok and t["structure"] == "ijara":
        ok = bool(types & set(st["ijara_requires"]))
    out.append({"name": "structure", "label": "Structure", "scope": f"{t['structure']} {t['facility_type']}", "value": t["structure"],
                "limit": "allowed", "headroom": None, "unit": "", "kind": "hard", "status": "pass" if ok else "breach",
                "basis": "Shariah and Risk structures table", "before": None, "deal": None})
    return out


# R12-C: the approved group exposure cap (Session C, backend/dealdesk/group/exposure.py). None when Data Domains
# holds no approved cap for the group, so the R11 constraint set and the optimiser's outputs are unchanged.
def _group_limits(p: dict[str, Any]) -> dict[str, Any] | None:  # R12-C
    try:  # R12-C
        from backend.dealdesk.group import exposure as _gx  # R12-C
        return _gx.group_limits(p)  # R12-C
    except Exception:  # noqa: BLE001 -- R12-C: nothing readable: the connected group limit alone applies
        return None  # R12-C


def _cap_basis(gcap: dict[str, Any], x: dict[str, Any]) -> str:  # R12-C
    who = f", approved by {gcap['approved_by']}" if gcap.get("approved_by") else ""  # R12-C
    ref = f" ({gcap['committee_ref']})" if gcap.get("committee_ref") else ""  # R12-C
    return f"Approved group exposure cap SAR {gcap['limit_sar_mn']:,.1f}m{who}{ref}; tighter than {x['basis']}"  # R12-C


def breaches(cs: list[dict[str, Any]], kind: str | None = None) -> list[dict[str, Any]]:
    return [c for c in cs if c["status"] == "breach" and (kind is None or c["kind"] == kind)]


def approval(p: dict[str, Any], a: dict[str, Any]) -> dict[str, Any]:
    """R14 E: the one approval-authority engine (backend.dealdesk.approval.core): exposure after the deal (existing +
    new limit), rating, exceptions (soft breaches, pricing below the hurdle, review policy exceptions), hard limits
    and SIMAH. `reasons` stays a list of sentences (binding reason first); `reason_rows` carries the structured rows."""
    from backend.dealdesk.approval.core import for_proposal  # R14 E
    d = for_proposal(p, a)
    rows = sorted(d["reasons"], key=lambda r: -int(r["rank"]))
    return {"level": d["level"], "rank": d["rank"], "reasons": [f"{r['detail']} → {r['level']}" for r in rows],
            "approvable": d["approvable"], "hard_breaches": d["hard_breaches"], "soft_breaches": d["soft_breaches"],
            "rule": d["rule"], "binding": d["binding"], "reason_rows": d["reasons"], "exceptions": d["exceptions"],
            "exposure_after_sar_mn": d["exposure_after_sar_mn"], "existing_exposure_sar_mn": d["existing_exposure_sar_mn"],
            "new_limit_sar_mn": d["new_limit_sar_mn"], "source": d["source"]}


def explain(name: str) -> dict[str, Any]:
    L = _limits()
    if name not in DEFINITIONS:
        raise KeyError(name)
    x = L.get(name, {})
    return {"name": name, "label": x.get("label", name.replace("_", " ").capitalize()), "definition": DEFINITIONS[name],
            "kind": x.get("kind", "hard"), "limit": {k: v for k, v in x.items() if k in ("limit", "limits", "limit_pct_tier1",
                                                                                        "headroom_sar_mn", "new_to_bank", "existing", "existing_soft")},
            "unit": x.get("unit", ""), "basis": x.get("basis", ""), "owner": params.table("risk_appetite")["owner"],
            "version": params.table("risk_appetite")["version"], "rating_order": GRADES}
