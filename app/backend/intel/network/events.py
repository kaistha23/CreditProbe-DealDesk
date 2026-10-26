"""Event translator (R14 backlog #8): a shock this morning -> the names it hits, the ECL and Stage 2 hit, who to call.

1. Read the event: picked (`family` + parameters) or free text ("oil falls 30%", "Red Sea disruption, severe",
   "Tuwaiq First Properties delays payments to contractors", "downgrade construction"). Free text goes through the
   What-If compound parser (`whatif_v5.chat.language.read`) for macro moves and sectors, plus this module's patterns for
   the families What-If has no words for (Red Sea, a named developer delaying payments).
2. Map it to shocked drivers, each with its stated assumption and the calibration it came from (calibration.py: R13
   §S when present, else the What-If engine's current calibration, said so).
3. Find the borrowers hit: directly (the drivers' scope) and through the network (suppliers that lose a customer,
   buyers that lose a supplier, contractors paid by a delayed developer, and the retail customers they employ).
4. Run the scenario through the What-If engine (whatif_bridge): ECL and Stage 2 before and after, by borrower.
5. Rank who to call today, each with the reason and the call to make. Publish as a computed view with lineage.
"""
from __future__ import annotations

import re
from typing import Any

import pandas as pd

from backend.b360.store import clean, rows
from backend.intel.network import calibration, common, links, whatif_bridge as wb, writer

FAMILIES: dict[str, dict[str, Any]] = {
    "oil": {"label": "Oil price move", "example": "What if oil falls 30% this morning?",
            "params": {"pct": "Brent move in % of its level (negative = fall); default from the severity"}},
    "gdp": {"label": "Non-oil GDP slowdown", "example": "Non-oil GDP 3% below plan",
            "params": {"pp": "change in non-oil real GDP growth, pp"}},
    "rates": {"label": "Rates rise", "example": "Rates up 200 bps", "params": {"bps": "policy-rate move, bps"}},
    "red_sea": {"label": "Red Sea shipping disruption", "example": "Red Sea disruption, severe",
                "params": {}},
    "developer_delay": {"label": "A developer delays payments to its contractors",
                        "example": "Tuwaiq First Properties delays payments to contractors",
                        "params": {"borrower_id": "the developer (book id) or its name", "days": "payment delay, days"}},
    "sector_downgrade": {"label": "Sector downgrade", "example": "Downgrade the hospitality sector",
                         "params": {"sector": "a corporate book sector"}},
}
#: Red Sea: sectors that ship through Bab el-Mandeb, with the share of the severity's sector stress they take.
RED_SEA_SECTORS = {"Transport and Logistics": 1.0, "Wholesale Trade": 0.5, "Retail Trade": 0.5, "Manufacturing": 0.25,
                   "Chemicals": 0.25}
#: second ring: dependency thresholds (share of the supplier's revenue / the buyer's purchases) and the notch it costs
SUPPLIER_REVENUE_SHARE = 20.0
BUYER_PURCHASE_SHARE = 30.0
#: developer delay: contractor notches by the share of its revenue the developer pays
CONTRACTOR_BANDS = ((30.0, 0), (10.0, -1))   # >= 30%: the severity's notches; 10-30%: one fewer (at least 1)
CALL_LIST = 10
SEVERITY_WORDS = r"\b(mild|moderate|severe|extreme)\b"
RED_SEA_RE = r"\b(red\s+sea|houthi\w*|bab[\s-]?el[\s-]?mandeb|suez|shipping\s+(?:disruption|route|lanes?|crisis)|freight\s+(?:disruption|rates?))\b"
DELAY_RE = r"\b(delay\w*|late|slow\w*|stop\w*|withhold\w*|suspend\w*|not\s+pay\w*|stretch\w*)\b"
DOWNGRADE_RE = r"\b(downgrad\w*|sector\s+(?:stress|downturn|shock|crisis)|stress\s+(?:the\s+)?\w+\s+sector|outlook\s+negative)\b"


class EventError(ValueError):
    pass


# ------------------------------------------------------------------ 1. read the event

def _severity(text: str, given: str | None) -> str:
    if given:
        if given not in calibration.LEVELS:
            raise EventError(f"Severity is one of {', '.join(calibration.LEVELS)}.")
        return given
    m = re.search(SEVERITY_WORDS, text or "", re.I)
    if m:
        w = m.group(1).lower()
        return "severe" if w == "extreme" else w
    return "moderate"


def _sector_words(text: str) -> list[str]:
    from backend.whatif_v5.chat.language import SECTOR_SYNONYMS
    t = (text or "").lower()
    found: list[str] = []
    for word, sector in sorted(SECTOR_SYNONYMS.items(), key=lambda kv: -len(kv[0])):
        if word == "it":
            continue
        if re.search(rf"\b{re.escape(word)}\b", t) and sector not in found:
            found.append(sector)
    return found


def _named_developer(period: str, text: str) -> dict[str, Any] | None:
    m = re.search(r"\bCB\d{5}\b", text or "", re.I)
    if m:
        hit = common.find_borrower(period, m.group(0).upper())
        return hit[0] if hit else None
    t = (text or "").lower()
    names = rows("""SELECT borrower_id, borrower_name, sector FROM corp_borrower WHERE reporting_quarter = ?
                    ORDER BY length(borrower_name) DESC, borrower_id""", [period])
    for r in names:
        if r["borrower_name"] and r["borrower_name"].lower() in t:
            return r
    return None


def _named_dd_employer(text: str) -> dict[str, Any] | None:
    """A Deal Desk project employer (b360_entity, role employer) named in the text, by its first two words or more."""
    from backend.intel.network.employer import _dd
    t = (text or "").lower()
    for e in sorted((x for x in _dd("b360_entity") if x.get("role") == "employer"), key=lambda x: -len(str(x["entity_name"]))):
        words = str(e["entity_name"]).lower().split()
        if words and " ".join(words[:2]) in t:
            return e
    return None


def _macro_from_text(text: str) -> dict[str, float]:
    """Macro moves the What-If compound parser reads in the text ({mev key: move})."""
    try:
        from backend.whatif_v5.chat import language
        from backend.whatif_v5.models import runner
        f = wb.frame("")
        ctx = {"domain": "corporate", "segments": sorted(f["segment"].astype(str).unique()),
               "subsegments": sorted(f["subsegment"].astype(str).unique()), "labels": runner.LABELS["corporate"],
               "has_scenario": False}
        rd = language.read(text, ctx)
        mev: dict[str, float] = {}
        for st in rd.steps:
            for k, v in (st.shocks.mev or {}).items():
                mev[k] = mev.get(k, 0.0) + float(v)
        return mev
    except Exception:  # noqa: BLE001 - the patterns below still read the common cases
        out: dict[str, float] = {}
        m = re.search(r"\b(oil|brent|crude)\b[^.;\d-]*?([-−+]?\d+(?:\.\d+)?)\s?%", text or "", re.I)
        if m:
            v = float(m.group(2).replace("−", "-"))
            down = re.search(r"\b(fall|falls|drop|drops|down|plunge|crash|lower|decline)\w*", text, re.I)
            out["brent"] = -abs(v) if (down or v < 0) else abs(v)
        return out


def read_event(req: dict[str, Any], period: str) -> dict[str, Any]:
    """The event as family + parameters + severity, from a picked event or free text."""
    text = str(req.get("text") or "").strip()
    fam = req.get("family")
    params = dict(req.get("params") or {})
    if fam and fam not in FAMILIES:
        raise EventError(f"Unknown event family {fam!r}; pick one of {', '.join(FAMILIES)}.")
    sev = _severity(text, req.get("severity"))
    parsed: list[str] = []
    if not fam:
        if not text:
            raise EventError("Describe the event or pick one (oil, red_sea, developer_delay, sector_downgrade, gdp, rates).")
        if re.search(RED_SEA_RE, text, re.I):
            fam = "red_sea"
            parsed.append("Red Sea shipping disruption")
        else:
            delay = re.search(DELAY_RE, text, re.I)
            dev = _named_developer(period, text) if delay else None
            dde = _named_dd_employer(text) if delay and not dev else None
            if dde:
                fam = "developer_delay"
                params.update({"entity_id": dde["entity_id"], "name": dde["entity_name"]})
                d = re.search(r"(\d+)\s*days?", text)
                if d:
                    params.setdefault("days", int(d.group(1)))
                parsed.append(f"{dde['entity_name']} (Deal Desk project employer) delays payments")
            elif dev:
                fam = "developer_delay"
                params.setdefault("borrower_id", dev["borrower_id"])
                d = re.search(r"(\d+)\s*days?", text)
                if d:
                    params.setdefault("days", int(d.group(1)))
                parsed.append(f"{dev['borrower_name']} ({dev['borrower_id']}) delays payments")
            else:
                mev = _macro_from_text(text)
                secs = _sector_words(text)
                if "brent" in mev:
                    fam, params["pct"] = "oil", mev["brent"]
                    parsed.append(f"oil {mev['brent']:+g}%")
                elif "gdp_nonoil" in mev or "gdp_real" in mev:
                    fam, params["pp"] = "gdp", mev.get("gdp_nonoil", mev.get("gdp_real"))
                    parsed.append(f"GDP {params['pp']:+g}pp")
                elif "repo" in mev or "saibor_3m" in mev:
                    fam, params["bps"] = "rates", mev.get("repo", mev.get("saibor_3m"))
                    parsed.append(f"rates {params['bps']:+g} bps")
                elif secs and (re.search(DOWNGRADE_RE, text, re.I) or len(text.split()) <= 6):
                    fam, params["sector"] = "sector_downgrade", secs[0]
                    parsed.append(f"{secs[0]} downgrade")
                elif re.search(r"\b(oil|brent|crude)\b", text, re.I):
                    fam = "oil"
                    parsed.append("oil (magnitude from the severity)")
        if not fam:
            raise EventError("I could not tie this to an event I can translate. Try: oil −30%, Red Sea disruption, "
                             "a named developer delaying payments, or a sector downgrade.")
    return {"family": fam, "label": FAMILIES[fam]["label"], "severity": sev, "params": params, "text": text,
            "parsed": parsed, "picked": bool(req.get("family"))}


# ------------------------------------------------------------------ 2. drivers and 3. scope

def _driver(key: str, label: str, value: float, unit: str, scope: str, assumption: str, basis: str) -> dict[str, Any]:
    return {"driver": key, "label": label, "value": value, "unit": unit, "scope": scope, "assumption": assumption,
            "basis": basis}


def translate(ev: dict[str, Any], period: str, cal: dict[str, Any]) -> dict[str, Any]:
    """Drivers, What-If steps and the direct set of borrowers (with channel) for the event."""
    fam, sev, p = ev["family"], ev["severity"], ev["params"]
    D = cal["drivers"]
    basis = cal["label"]
    drivers: list[dict[str, Any]] = []
    steps = []
    direct: dict[str, dict[str, Any]] = {}     # borrower -> {channel, reason}
    assumptions: list[str] = []
    book_wide = False
    if fam == "oil":
        pct = float(p.get("pct")) if p.get("pct") is not None else round(float(D["brent"][sev]), 1)
        drivers.append(_driver("brent", "Brent", pct, "% of level", "whole book",
                               "Brent moves by this much from its current level and stays there for two years; each "
                               "sector's cycle index follows through the What-If cycle model's oil betas.",
                               "stated in the event" if p.get("pct") is not None else f"{basis}: {sev}"))
        steps.append(wb.step(f"Brent {pct:+g}%", {"mev": {"brent": pct}, "horizon": 2}))
        assumptions.append("Only oil moves: GDP, rates and real-estate prices are held at plan (no joint draw until §S "
                           "joint scenarios merge).")
        book_wide = True
    elif fam == "gdp":
        pp = float(p.get("pp")) if p.get("pp") is not None else round(float(D["gdp_nonoil"][sev]), 2)
        drivers.append(_driver("gdp_nonoil", "Non-oil real GDP growth", pp, "pp", "whole book",
                               "Non-oil GDP growth is this much lower for two years; sectors follow their cycle betas.",
                               "stated in the event" if p.get("pp") is not None else f"{basis}: {sev}"))
        steps.append(wb.step(f"Non-oil GDP {pp:+g}pp", {"mev": {"gdp_nonoil": pp}, "horizon": 2}))
        book_wide = True
    elif fam == "rates":
        bps = float(p.get("bps")) if p.get("bps") is not None else round(float(D["repo"][sev]))
        drivers.append(_driver("repo", "Policy rate", bps, "bps", "whole book",
                               "The policy rate (and SAIBOR with it) moves by this much for two years.",
                               "stated in the event" if p.get("bps") is not None else f"{basis}: {sev}"))
        steps.append(wb.step(f"Rates {bps:+g} bps", {"mev": {"repo": bps}, "horizon": 2}))
        book_wide = True
    elif fam == "red_sea":
        sd = round(float(D["sector_sd"][sev]), 2)
        for sector, w in RED_SEA_SECTORS.items():
            drivers.append(_driver("sector", f"{sector} cycle index", round(sd * w, 3), "sd", sector,
                                   f"Freight, insurance and transit time rise on Asia–Europe routes; {sector} takes "
                                   f"{w:.0%} of the {sev} sector stress ({sd:g} sd).", f"{basis}: sector stress {sev}"))
            steps.append(wb.step(f"Red Sea: {sector} {sd * w:+.2f} sd", {"sector": round(sd * w, 3)}, segments=[sector]))
        assumptions.append("The Brent rise a disruption usually brings is left out: for a Saudi book it lowers losses, "
                           "and leaving it out keeps the hit conservative.")
        assumptions.append("Sector shares of the stress are expert (transport and logistics in full, wholesale and retail trade at "
                           "half, manufacturing and chemicals at a quarter); no history in the book isolates a shipping shock.")
        for r in rows("SELECT borrower_id, sector FROM corp_borrower WHERE reporting_quarter = ? AND list_contains(?, sector)",
                      [period, list(RED_SEA_SECTORS)]):
            direct[r["borrower_id"]] = {"channel": "direct", "reason": f"{r['sector']}: ships through the Red Sea"}
    elif fam == "sector_downgrade":
        sector = p.get("sector")
        valid = [r["sector"] for r in rows("SELECT DISTINCT sector FROM corp_borrower WHERE reporting_quarter = ?", [period])]
        if sector not in valid:
            secs = _sector_words(str(sector or ""))
            sector = secs[0] if secs else None
        if sector not in valid:
            raise EventError(f"Name a corporate book sector: {', '.join(sorted(valid))}.")
        p["sector"] = sector
        sd = round(float(D["sector_sd"][sev]), 2)
        notch = 1 if sev != "mild" else 0
        drivers.append(_driver("sector", f"{sector} cycle index", sd, "sd", sector,
                               f"The sector's credit cycle turns by {sd:g} sd ({sev}).", f"{basis}: sector stress {sev}"))
        shocks: dict[str, Any] = {"sector": sd}
        if notch:
            drivers.append(_driver("rating", "Rating", notch, "notch", sector,
                                   "Agencies and the bank's own reviews move the sector one notch down.", "expert"))
            shocks["rating"] = notch
        steps.append(wb.step(f"{sector} downgrade ({sev})", shocks, segments=[sector]))
        for r in rows("SELECT borrower_id FROM corp_borrower WHERE reporting_quarter = ? AND sector = ?", [period, sector]):
            direct[r["borrower_id"]] = {"channel": "direct", "reason": f"in {sector}"}
    elif fam == "developer_delay" and p.get("entity_id") and not p.get("borrower_id"):
        dd = _deal_desk_delay(p, sev, D)
        drivers.extend(dd["drivers"])
        assumptions.extend(dd["assumptions"])
        return {"drivers": drivers, "steps": steps, "direct": direct, "assumptions": assumptions, "book_wide": False,
                "deal_desk": dd["projects"], "deal_desk_calls": dd["calls"]}
    elif fam == "developer_delay":
        bid = str(p.get("borrower_id") or "").strip()
        hit = common.find_borrower(period, bid)
        if not hit:
            raise EventError(f"No book borrower matches {bid!r}; name the developer or give its CB id.")
        dev = hit[0]
        p["borrower_id"], p["name"] = dev["borrower_id"], dev["borrower_name"]
        days = int(p.get("days") or D["payment_delay_days"][sev])
        p["days"] = days
        notches = int(D["notches"][sev])
        dev_notch = max(1, notches - 1)
        drivers.append(_driver("rating", f"{dev['borrower_name']} rating", dev_notch, "notch", dev["borrower_id"],
                               f"A developer that stops paying certificates for {days} days is itself under strain: "
                               f"{writer.n(dev_notch, 'notch', 'notches')} down.", f"{basis}: rating notches {sev}"))
        steps.append(wb.step(f"{dev['borrower_name']} −{dev_notch} notch", {"rating": dev_notch}, owners=[dev["borrower_id"]]))
        direct[dev["borrower_id"]] = {"channel": "direct", "reason": f"delays payments to its contractors by {days} days"}
        contractors = links.supplies_into(period, [dev["borrower_id"]])
        by_notch: dict[int, list[str]] = {}
        for e in contractors:
            share = float(e["revenue_share_pct"] or 0.0)
            n = 0
            for thr, adj in CONTRACTOR_BANDS:
                if share >= thr:
                    n = max(1, notches + adj)
                    break
            tag = "contractor" if e["supplier_sector"] == links.CONTRACTOR_SECTOR else "supplier"
            direct[e["supplier_id"]] = {"channel": tag, "share_pct": share, "notches": n,
                                        "reason": f"{share:.1f}% of its revenue is paid by {dev['borrower_name']}"}
            if n:
                by_notch.setdefault(n, []).append(e["supplier_id"])
        for n, ids in sorted(by_notch.items()):
            drivers.append(_driver("rating", "Rating of contractors and suppliers paid by the developer", n, "notch",
                                   f"{len(ids)} borrower{'s' if len(ids) != 1 else ''}",
                                   f"Certificates unpaid for {days} days strain working capital: {writer.n(n, 'notch', 'notches')} where the "
                                   f"developer pays {'30% or more' if n == notches else '10–30%'} of revenue.",
                                   f"{basis}: rating notches {sev}"))
            steps.append(wb.step(f"Paid by {dev['borrower_name']}: −{n} notch", {"rating": n}, owners=ids))
        assumptions.append(f"Contractors paid less than {CONTRACTOR_BANDS[-1][0]:.0f}% of their revenue by the developer "
                           "are listed but not shocked.")
    return {"drivers": drivers, "steps": steps, "direct": direct, "assumptions": assumptions, "book_wide": book_wide}


def _deal_desk_delay(p: dict[str, Any], sev: str, D: dict[str, Any]) -> dict[str, Any]:
    """A Deal Desk project employer delays: its contractors' projects, certificates, LGs and the RM to call."""
    from backend.intel.network.employer import _dd, deal_desk_projects
    days = int(p.get("days") or D["payment_delay_days"][sev])
    p["days"] = days
    projects, calls = [], {}
    for pr in deal_desk_projects(p.get("name"), p.get("entity_id")):
        lgs = [x for x in _dd("dd_facility_limit", proposal_id=pr["proposal_id"]) if x.get("project_id") == pr["project_id"]]
        kids = [x for x in lgs if x.get("product_code")] or lgs
        lg = sum(float(x.get("outstanding_mn") or 0.0) for x in kids if not x.get("funded_flag"))
        deal = (_dd("dd_deal", proposal_id=pr["proposal_id"]) or [{}])[0]
        due, ret = float(pr.get("due_mn") or 0.0), float(pr.get("retention_mn") or 0.0)
        projects.append({"project_id": pr["project_id"], "project": pr["project_name"], "proposal_id": pr["proposal_id"],
                         "contractor_id": pr["obligor_id"], "contractor": deal.get("obligor_name"), "due": due, "retention": ret,
                         "backlog": float(pr.get("backlog_mn") or 0.0), "lg_outstanding": lg,
                         "payment_delay_days": pr.get("payment_delay_days"), "rm": deal.get("rm")})
        c = calls.setdefault(pr["obligor_id"], {"borrower_id": pr["obligor_id"], "name": deal.get("obligor_name"),
                                                "sector": "Construction", "channel": "contractor", "ead": 0.0, "d_ecl": 0.0,
                                                "to_stage2": 0, "to_stage3": 0, "ews_band": None, "rating": None,
                                                "rm": deal.get("rm"), "rm_id": None, "branch": deal.get("branch"),
                                                "due": 0.0, "lg": 0.0, "projects": [],
                                                "href": f"/deal-desk/{pr['proposal_id']}"})
        c["due"] += due
        c["lg"] += lg
        c["ead"] += lg
        c["projects"].append(pr["project_name"])
    out_calls = []
    for c in calls.values():
        c["reason"] = (f"{p['name']} owes {writer.m(c.pop('due'))} certified but unpaid on "
                       f"{writer.n(len(c['projects']), 'project')} ({', '.join(c.pop('projects'))}); "
                       f"LGs outstanding {writer.m(c.pop('lg'))}; delay assumed {days} days.")
        c["action"] = ACTION["contractor"]
        out_calls.append(c)
    drivers = [_driver("payment_delay_days", f"{p['name']} payments to contractors", days, "days", p.get("entity_id", ""),
                       f"Certificates are paid {days} days late; the contractor funds the gap and its LGs may be called.",
                       "stated in the event" if p.get("days") else f"payment delay {sev}")]
    assumptions = [f"{p['name']} is a Deal Desk project employer, not a corporate book borrower; its contractors are Deal "
                   "Desk obligors outside the What-If book, so no book ECL is run: the answer is the projects, the amounts "
                   "certified but unpaid, the LGs at risk and the relationship manager to call."]
    return {"drivers": drivers, "assumptions": assumptions, "projects": projects, "calls": out_calls}


def second_ring(period: str, direct: dict[str, dict[str, Any]], names: dict[str, str]) -> tuple[dict[str, dict[str, Any]], list]:
    """Suppliers that lose a customer and buyers that lose a supplier among the directly hit (one notch each)."""
    ids = list(direct)
    ring: dict[str, dict[str, Any]] = {}
    for e in links.supplies_into(period, ids):
        s = e["supplier_id"]
        if s in direct or (e["revenue_share_pct"] or 0) < SUPPLIER_REVENUE_SHARE:
            continue
        cur = ring.get(s)
        if not cur or (e["revenue_share_pct"] or 0) > cur["share_pct"]:
            ring[s] = {"channel": "supplier", "share_pct": float(e["revenue_share_pct"]), "via": e["buyer_id"],
                       "reason": f"sells {e['revenue_share_pct']:.1f}% of its revenue to {names.get(e['buyer_id'], e['buyer_id'])}"}
    for e in links.supplies_from(period, ids):
        b = e["buyer_id"]
        if b in direct or b in ring or (e["purchase_share_pct"] or 0) < BUYER_PURCHASE_SHARE:
            continue
        ring[b] = {"channel": "customer", "share_pct": float(e["purchase_share_pct"]), "via": e["supplier_id"],
                   "reason": f"buys {e['purchase_share_pct']:.1f}% of its inputs from {names.get(e['supplier_id'], e['supplier_id'])}"}
    steps = []
    if ring:
        steps.append(wb.step("Second ring: −1 notch", {"rating": 1}, owners=list(ring)))
    return ring, steps


# ------------------------------------------------------------------ 5. who to call

ACTION = {
    "direct": "Confirm order book, cash runway and covenant headroom under the event; agree a monitoring date.",
    "contractor": "Confirm certified-but-unpaid amounts and retention from the developer, LG call risk and liquidity.",
    "supplier": "Check receivables from the affected buyer, alternative buyers and the cash gap.",
    "customer": "Check supply continuity from the affected supplier and the cost of switching.",
    "macro": "Review the borrower's sensitivity to the move and its headroom; agree a monitoring date.",
}


def call_list(per: pd.DataFrame, chan: dict[str, dict[str, Any]], attrs: dict[str, dict[str, Any]], period: str,
              n: int = CALL_LIST) -> list[dict[str, Any]]:
    hit = per[(per["d_ecl"] > 1e-6) | (per["to_stage2"] > 0) | (per["to_stage3"] > 0)].copy()
    if hit.empty:
        return []
    hit["moved"] = (hit["to_stage2"] + hit["to_stage3"]) > 0
    hit = hit.sort_values(["moved", "d_ecl", "ead"], ascending=[False, False, False]).head(n)
    out = []
    rms = common.relationship_managers(period, list(hit.index))
    for bid, r in hit.iterrows():
        c = chan.get(bid, {"channel": "macro", "reason": "moves with the macro driver through its sector beta"})
        a = attrs.get(bid, {})
        why = [c["reason"]]
        if r["to_stage3"]:
            why.append(writer.n(int(r['to_stage3']), 'facility', 'facilities') + " would default")
        elif r["to_stage2"]:
            why.append(writer.n(int(r['to_stage2']), 'facility', 'facilities') + " would move to Stage 2")
        why.append(f"ECL +SAR {r['d_ecl']:,.2f}m on EAD SAR {r['ead']:,.1f}m")
        if a.get("ews_band") in ("high", "critical"):
            why.append(f"already {a['ews_band']} in Early Warning")
        out.append({"borrower_id": bid, "name": r["name"], "sector": r["sector"], "channel": c["channel"],
                    "ead": float(r["ead"]), "d_ecl": float(r["d_ecl"]), "to_stage2": int(r["to_stage2"]),
                    "to_stage3": int(r["to_stage3"]), "ews_band": a.get("ews_band"), "rating": a.get("rating_current"),
                    "reason": "; ".join(why) + ".", "action": ACTION[c["channel"]],
                    "rm": (rms.get(bid) or {}).get("rm_name"), "rm_id": (rms.get(bid) or {}).get("rm_id"),
                    "branch": (rms.get(bid) or {}).get("branch_name"),
                    "href": f"/borrower-360?domain=corporate&customer_id={bid}"})
    return out


# ------------------------------------------------------------------ the whole job

def translate_event(req: dict[str, Any], publish: bool = True) -> dict[str, Any]:
    period = common.resolve_quarter(req.get("period"))
    cal = calibration.table()
    ev = read_event(req, period)
    tr = translate(ev, period, cal)
    attrs = common.borrowers(period)
    names = {k: v["borrower_name"] for k, v in attrs.items()}
    direct = tr["direct"]
    ring, ring_steps = ({}, []) if tr["book_wide"] else second_ring(period, direct, names)
    steps = tr["steps"] + ring_steps
    res = wb.run(period, steps, name=ev["label"])
    rowsdf = res["rows"]
    tot = wb.totals(rowsdf)
    per = wb.by_owner(rowsdf)
    chan = {**direct, **ring}
    # channel summary
    channels: list[dict[str, Any]] = []
    for ch in ("direct", "contractor", "supplier", "customer"):
        ids = [k for k, v in chan.items() if v["channel"] == ch and k in per.index]
        if ids:
            sub = per.loc[ids]
            channels.append({"channel": ch, "borrowers": len(ids), "ead": float(sub["ead"].sum()),
                             "d_ecl": float(sub["d_ecl"].sum()), "to_stage2": int(sub["to_stage2"].sum()),
                             "to_stage3": int(sub["to_stage3"].sum())})
    if tr["book_wide"]:
        moved = per[per["d_ecl"] > 1e-6]
        channels.append({"channel": "macro", "borrowers": int(len(moved)), "ead": float(moved["ead"].sum()),
                         "d_ecl": float(moved["d_ecl"].sum()), "to_stage2": int(moved["to_stage2"].sum()),
                         "to_stage3": int(moved["to_stage3"].sum())})
    # by sector
    sec = per.groupby("sector").agg(ead=("ead", "sum"), d_ecl=("d_ecl", "sum"), to_stage2=("to_stage2", "sum"))
    by_sector = [{"sector": s, "ead": float(r["ead"]), "d_ecl": float(r["d_ecl"]), "to_stage2": int(r["to_stage2"])}
                 for s, r in sec.sort_values("d_ecl", ascending=False).iterrows() if r["d_ecl"] > 1e-6][:8]
    # borrowers hit (top 50 by ECL change)
    hit = per[(per["d_ecl"] > 1e-6) | per.index.isin(list(chan))].sort_values(["d_ecl", "ead"], ascending=False)
    borrowers = []
    for bid, r in hit.head(50).iterrows():
        c = chan.get(bid, {"channel": "macro", "reason": "sector beta to the macro driver"})
        borrowers.append({"borrower_id": bid, "name": r["name"], "sector": r["sector"], "channel": c["channel"],
                          "reason": c["reason"], "share_pct": c.get("share_pct"), "notches": c.get("notches"),
                          "ead": float(r["ead"]), "ecl_before": float(r["ecl0"]), "ecl_after": float(r["ecl1"]),
                          "d_ecl": float(r["d_ecl"]), "to_stage2": int(r["to_stage2"]), "to_stage3": int(r["to_stage3"]),
                          "ews_band": attrs.get(bid, {}).get("ews_band")})
    # employers: retail customers salaried by the hit corporates
    hit_ids = list(chan) if chan else [b for b in per.index if per.loc[b, "d_ecl"] > 1e-6]
    wf = links.workforce(common.month_of_quarter(period), hit_ids)
    calls = tr.get("deal_desk_calls", []) + call_list(per, chan, attrs, period)
    cov = links.coverage(period)
    limits = [
        f"Relationship coverage: {cov['supply_link_pct']:.1f}% of the {cov['borrowers']:,} corporate borrowers have a "
        "supplier or customer link in rel-saudi-v1; supplier links are observed only through payments routed via the bank, "
        "so a counterparty banking elsewhere is not seen.",
        "Second-ring effects are one notch on borrowers that sell ≥20% of revenue to, or buy ≥30% of inputs from, a "
        "directly hit name; deeper rings are not run." if not tr["book_wide"] else
        "A book-wide macro move reaches every borrower through its sector's cycle beta; supplier links are not added "
        "on top (they are already in the sector betas).",
        "Retail customers employed by the hit corporates are counted, not stressed: the retail book is not in this run.",
        "The relationship manager on each call is from the Branches and RMs domain at the quarter.",
        cal["note"],
    ]
    lineage = [common.src("corp_borrower", period, ["sector", "rating_current"]),
               common.src("corp_facility", period, ["ead_sar_mn", "ecl_sar_mn", "stage"]),
               common.src("rel_edge", period, ["rel_type", "revenue_share_pct", "purchase_share_pct"]),
               common.src("rel_employer", common.month_of_quarter(period)),
               common.src("ews_corp", period, ["ews_score"]), wb.source(res["period"]),
               {"domain": "Calibration", "relation": cal["source"], "path": cal.get("path"), "label": cal["label"]}]
    out: dict[str, Any] = {
        "period": res["period"], "event": ev, "severity": ev["severity"], "calibration":
            {k: cal[k] for k in ("source", "label", "note", "path")},
        "drivers": tr["drivers"], "assumptions": tr["assumptions"],
        "impact": tot, "channels": channels, "by_sector": by_sector, "borrowers": borrowers,
        "affected": {"direct": sum(1 for v in chan.values() if v["channel"] in ("direct", "contractor")),
                     "network": len(ring), "with_ecl_change": int((per["d_ecl"] > 1e-6).sum())},
        "employers": {"retail_workforce": wf}, "call_list": calls, "limits": limits, "coverage": cov,
        "deal_desk": tr.get("deal_desk", []),
        "engine": {"method": res["method"], "drivers": res["drivers"], "seconds": res["seconds"],
                   "steps": [s.to_dict() for s in steps]},
        "lineage": lineage, "money_unit": common.MONEY,
        "sources": {"impact": common.derived("What-If engine per-facility evaluate, summed", wb.source(res["period"])),
                    "call_list": common.derived("rank: stage move, then ECL change, then EAD",
                                                wb.source(res["period"]), common.src("ews_corp", period),
                                                common.src("branch_corporate_quarter", period, ["rm_id", "rm_name"]))},
    }
    out["text"] = writer.event_text(out)
    if publish:
        out["view"] = common.publish_view("event", ev["family"], out, {"req": {k: req.get(k) for k in
                                                                                ("text", "family", "params", "severity", "period")},
                                                                         "calibration": cal["source"]})
    return clean(out)


def catalogue() -> dict[str, Any]:
    cal = calibration.table()
    return clean({"families": [{"family": k, **v} for k, v in FAMILIES.items()], "severities": list(calibration.LEVELS),
                  "calibration": {k: cal[k] for k in ("source", "label", "note", "path")},
                  "magnitudes": cal["drivers"]})
