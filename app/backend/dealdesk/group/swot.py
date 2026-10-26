"""SWOT in Structure, and the weakness-to-mitigant map (PLAN_R12 §1.4, I24, I16-3).

Every point is financial or qualitative, carries the number and the period behind it and links to its evidence:
a Data Domains relation and row keys, a review finding of this session (`finding_id`) or a deal metric. The writer is
deterministic (N6): the sentences are built from the numbers, in the proposal voice (prior year in brackets,
attribution where the figure is the business's), and are the same on every run.

Published to `dd_swot` (one row per point) through E's publisher.

The weakness-to-mitigant map takes each weakness and threat and shows which structure lever or condition answers it,
for the ask or for any structure U passes in (the optimiser's recommended structure, or the user's own).
"""
from __future__ import annotations


from typing import Any

from backend.dealdesk import params
from backend.dealdesk.group import conduct as C, deal, exposure as X, facts as F, flags as FL, sources as S

AS_OF = deal.AS_OF

#: Sectors and the external drivers that move them (geopolitical / market effects, proposal section 16). The
#: driver names match the Stress Lab families (macro: oil, non-oil GDP, rates; routes and input costs).
SECTOR_DRIVERS: dict[str, str] = {
    "Construction": "government and giga-project spending tied to the oil price, payment delays from employers and steel and cement input costs",
    "Real Estate": "rates (SAIBOR) and off-plan demand, with project delays",
    "Trading": "shipping routes through the Red Sea and the Strait of Hormuz, freight and insurance costs, and import lead times",
    "Wholesale and Retail Trade": "shipping routes through the Red Sea, freight costs and consumer demand",
    "Manufacturing": "feedstock and energy prices, export routes and demand from the oil and gas supply chain",
    "Petrochemicals": "the oil price, feedstock allocation and export routes",
    "Oil and Gas": "the oil price and OPEC+ production quotas",
    "Transport and Logistics": "regional shipping routes, fuel costs and trade volumes",
    "Healthcare": "government reimbursement timing and the pace of privatisation",
    "Hospitality": "tourism flows and regional security",
    "Utilities": "tariff reform and government payment timing",
}
DEFAULT_DRIVER = "the oil price through government spending, and SAIBOR"


def _src(relation: str, **keys: Any) -> dict[str, Any]:
    loc = S.locate(relation) or {}
    return {"domain": loc.get("domain"), "relation": relation, "keys": {k: v for k, v in keys.items() if v is not None}}


def _pct(x: float | None, d: int = 1) -> str:
    return "n/a" if x is None else f"{100 * x:.{d}f}%"


def _m(x: float | None) -> str:
    return "n/a" if x is None else f"SAR {x:,.1f}m"


def _financials(pid: str) -> list[dict[str, Any]]:
    rows = S.records(S.read("dd_obligor_financials", None, proposal_id=pid))
    if rows:
        return sorted(rows, key=lambda r: (r["year"], r.get("kind") != "actual"))
    p = deal.get(pid)  # a deal not in the relation yet (user-added): the proposal's own file
    return [{"proposal_id": pid, "year": y["year"], "kind": y["kind"], "revenue_sar_mn": y["revenue"], "ebitda_sar_mn": y["ebitda"],
             "total_debt_sar_mn": y["total_debt"], "debt_service_sar_mn": y["debt_service"], "net_worth_sar_mn": y["net_worth"],
             "current_ratio_x": y.get("current_ratio"), "source": y.get("source", "proposal")} for y in p["financials"]["years"]]


def _result(pid: str, view: str = "ask") -> dict[str, Any] | None:
    r = S.records(S.read("dd_result", None, proposal_id=pid, view=view))
    return r[0] if r else None


def build(pid: str, fx: dict[str, Any] | None = None, cd: dict[str, Any] | None = None, ev: dict[str, Any] | None = None,
          cap: dict[str, Any] | None = None) -> dict[str, Any]:
    p = deal.get(pid)
    ob = p["obligor"]
    fx = fx or F.build(pid)
    cd = cd or C.build(pid)
    if cap is None:
        try:
            cap = X.cap_test(pid)
        except Exception:  # noqa: BLE001
            cap = None
    ev = ev or FL.evaluate(pid, fx, cd, cap)
    by_code = {f["code"]: f for f in ev["flags"]}
    pts: list[dict[str, Any]] = []

    def add(q: str, kind: str, theme: str, text: str, evidence: list[dict[str, Any]], link: dict[str, Any] | None = None,
            value: Any = None) -> None:
        pts.append({"quadrant": q, "kind": kind, "theme": theme, "text": text, "evidence": evidence, "link": link or {},
                    "metric": value})

    # ---------------------------------------------------------------- financial
    fin = _financials(pid)
    acts = [r for r in fin if r.get("kind") == "actual"]
    proj = [r for r in fin if r.get("kind") != "actual"]
    fsrc = lambda y: _src("dd_obligor_financials", proposal_id=pid, year=y)  # noqa: E731
    if len(acts) >= 2:
        a1, a0 = acts[-1], acts[-2]
        g = a1["revenue_sar_mn"] / a0["revenue_sar_mn"] - 1 if a0["revenue_sar_mn"] else None
        if g is not None:
            t = f"Revenue {'rose' if g >= 0 else 'fell'} {abs(100 * g):.1f}% to {_m(a1['revenue_sar_mn'])} in FY{a1['year']} (PY {_m(a0['revenue_sar_mn'])})."
            if g >= 0.10:
                add("strength", "financial", "growth", t, [fsrc([a0["year"], a1["year"]])], {"type": "metric", "step": "analysis"}, g)
            elif g < 0:
                add("weakness", "financial", "growth", t, [fsrc([a0["year"], a1["year"]])], {"type": "metric", "step": "analysis"}, g)
        m1 = a1["ebitda_sar_mn"] / a1["revenue_sar_mn"] if a1["revenue_sar_mn"] else None
        m0 = a0["ebitda_sar_mn"] / a0["revenue_sar_mn"] if a0["revenue_sar_mn"] else None
        if m1 is not None:
            t = f"EBITDA margin {_pct(m1)} in FY{a1['year']} (PY {_pct(m0)}), EBITDA {_m(a1['ebitda_sar_mn'])}."
            if m1 >= 0.15:
                add("strength", "financial", "profitability", t, [fsrc(a1["year"])], {"type": "metric", "step": "analysis"}, m1)
            elif m1 < 0.08 or (m0 and m1 < m0 - 0.03):
                add("weakness", "financial", "profitability", t, [fsrc([a0["year"], a1["year"]])], {"type": "metric", "step": "analysis"}, m1)
        cr = a1.get("current_ratio_x")
        if cr is not None:
            t = f"Current ratio {cr:.2f}x at FY{a1['year']} (PY {a0.get('current_ratio_x') or 0:.2f}x)."
            if cr >= 1.5:
                add("strength", "financial", "liquidity", t, [fsrc(a1["year"])], {"type": "metric", "step": "analysis"}, cr)
            elif cr < 1.0:
                add("weakness", "financial", "liquidity", t, [fsrc(a1["year"])], {"type": "metric", "step": "analysis"}, cr)
        nw1, nw0 = a1.get("net_worth_sar_mn"), a0.get("net_worth_sar_mn")
        if nw1 is not None and nw0:
            g = nw1 / nw0 - 1
            if g >= 0.10:
                add("strength", "financial", "capital", f"Net worth grew {100 * g:.1f}% to {_m(nw1)} in FY{a1['year']} (PY {_m(nw0)}).",
                    [fsrc([a0["year"], a1["year"]])], {"type": "metric", "step": "analysis"}, g)
            elif g < -0.05:
                add("weakness", "financial", "capital", f"Net worth fell {abs(100 * g):.1f}% to {_m(nw1)} in FY{a1['year']} (PY {_m(nw0)}).",
                    [fsrc([a0["year"], a1["year"]])], {"type": "metric", "step": "analysis"}, g)
        # extensions E publishes on dd_obligor_financials (auditor, opinion, concentration, related parties)
        op = S.pick(a1, "audit_opinion", "opinion")
        if op and str(op).lower().startswith("qualif"):
            basis = S.pick(a1, "qualification_basis", default="basis not provided")
            add("weakness", "financial", "audit quality", f"FY{a1['year']} audit opinion qualified by {S.pick(a1, 'auditor', default='the auditor')}: {basis}.",
                [fsrc(a1["year"])], {"type": "fact", "step": "review"}, op)
        rp = S.pick(a1, "related_party_balances_sar_mn", "due_from_related_parties_sar_mn")
        if rp and nw1:
            share = rp / nw1
            if share >= 0.2:
                add("weakness", "financial", "related-party balances", f"Due from related parties {_m(rp)} at FY{a1['year']}, {_pct(share)} of net worth "
                    f"(adjusted net worth {_m(nw1 - rp)} if netted off).", [fsrc(a1["year"])], {"type": "metric", "step": "review"}, share)
        top = S.pick(a1, "top_receivables_share_pct", "receivables_top_n_pct", "top_n_concentration_pct")
        if top is not None and top >= 50:
            add("weakness", "qualitative", "concentration of receivables", f"Top customers hold {top:.0f}% of receivables at FY{a1['year']}.",
                [fsrc(a1["year"])], {"type": "metric", "step": "review"}, top)
    if proj and acts:
        pr = proj[-1]
        g = (pr["revenue_sar_mn"] / acts[-1]["revenue_sar_mn"]) ** (1 / max(1, pr["year"] - acts[-1]["year"])) - 1 if acts[-1]["revenue_sar_mn"] else None
        if g is not None and g > 0:
            add("opportunity", "financial", "growth plan", f"Revenue projected at {_m(pr['revenue_sar_mn'])} by FY{pr['year']} ({100 * g:.1f}% a year), "
                f"as per business ({pr.get('source') or 'projection'}).", [fsrc(pr["year"])], {"type": "fact", "step": "proposal"}, g)
    # deal metrics: the priced result (dd_result), else the engine on the ask
    res = _result(pid, "ask")
    try:
        from backend.dealdesk import engine
        m = engine.analyse(p)["metrics"]
    except Exception:  # noqa: BLE001
        m = {}
    rsrc = _src("dd_result", proposal_id=pid, view="ask") if res else {"domain": "deal_desk", "relation": "dd_proposal",
                                                                        "keys": {"proposal_id": pid}, "computed": "engine.analyse"}
    L = {x["name"]: x for x in params.rows("risk_appetite")}
    de = m.get("debt_ebitda_post")
    if de is not None:
        lim = float(L["debt_ebitda"]["limit"])
        t = f"Debt / EBITDA {de:.2f}x after the deal (policy limit {lim:.2f}x)."
        if de <= 2.5:
            add("strength", "financial", "leverage", t, [rsrc], {"type": "metric", "step": "analysis", "id": "debt_ebitda"}, de)
        elif de >= 0.8 * lim:
            add("weakness", "financial", "leverage", t, [rsrc], {"type": "metric", "step": "analysis", "id": "debt_ebitda"}, de)
    ds = m.get("dscr_post")
    if ds is not None:
        lim = float(L["dscr"]["limit"])
        t = f"DSCR {ds:.2f}x after the deal (policy floor {lim:.2f}x)."
        if ds >= 1.5:
            add("strength", "financial", "debt service", t, [rsrc], {"type": "metric", "step": "analysis", "id": "dscr"}, ds)
        elif ds < lim + 0.15:
            add("weakness", "financial", "debt service", t, [rsrc], {"type": "metric", "step": "analysis", "id": "dscr"}, ds)
    rar = (res or {}).get("lifetime_raroc_pct")
    hur = (res or {}).get("hurdle_pct")
    if rar is None and m.get("lifetime_raroc") is not None:
        rar, hur = 100 * m["lifetime_raroc"], 100 * m["hurdle"]
    if rar is not None and hur is not None:
        t = f"Lifetime RAROC {rar:.1f}% on the ask against a hurdle of {hur:.1f}%."
        if rar >= hur + 2:
            add("strength", "financial", "returns", t, [rsrc], {"type": "metric", "step": "analysis", "id": "raroc"}, rar)
        elif rar < hur:
            add("weakness", "financial", "returns", t, [rsrc], {"type": "metric", "step": "analysis", "id": "raroc"}, rar)

    # ---------------------------------------------------------------- qualitative
    st, sh, bd = fx["structure"], fx["shareholders"], fx["board"]
    if bd["rows"]:
        top = bd["rows"][0]
        if not any(b["linked_to_stressed"] for b in bd["rows"]):
            add("strength", "qualitative", "management", f"Board and key persons identified ({bd['people']}), led by {top['name']} "
                f"({', '.join(top['roles'])}); no link to a stressed borrower.", bd["source"], {"type": "fact", "step": "review"}, bd["people"])
    big = [r for r in sh["rows"] if (r.get("pct") or 0) >= 50]
    if big:
        add("strength", "qualitative", "ownership", f"Ownership concentrated in {big[0]['name']} ({big[0]['pct']:.1f}%), "
            f"identified as {'ultimate beneficial owner' if big[0]['ubo'] else 'the controlling shareholder'}.", sh["source"],
            {"type": "fact", "step": "review"}, big[0]["pct"])
    if not st["standalone"] and st.get("members", 1) > 1:
        add("strength", "qualitative", "group support", f"Member of {st['group_name']} ({st['members']} companies in the bank's book"
            + (f", parent {st['parent']['name']}" if st.get("parent") else "") + ").", st["source"][:1], {"type": "fact", "step": "structure"},
            st["members"])
    for code, q, theme in (("GOV-OWNERSHIP-CHANGE", "threat", "ownership change"), ("GOV-INSIDER", "weakness", "governance"),
                           ("GOV-UBO-UNIDENTIFIED", "weakness", "governance"), ("GOV-KEYPERSON-LINK", "weakness", "management"),
                           ("GOV-CONN-CLASSIFIED", "threat", "connected parties"), ("GOV-CONN-LITIGATION", "threat", "connected parties"),
                           ("GOV-CONN-ARREARS", "threat", "connected parties"), ("GOV-SHARED-COLLATERAL", "weakness", "collateral"),
                           ("GOV-GUARANTEE-UNPERFECTED", "weakness", "collateral"), ("GOV-GROUP-CAP", "threat", "group exposure"),
                           ("CON-RETURNED-CHEQUES", "weakness", "track record"), ("CON-PAST-DUE", "weakness", "track record"),
                           ("CON-OVERUTILISATION", "weakness", "track record"), ("CON-ROUTING", "weakness", "track record"),
                           ("CON-TURNOVER-DECLINE", "weakness", "track record"), ("CON-BUREAU", "threat", "bureau"),
                           ("CON-BUREAU-COURT", "threat", "bureau")):
        f = by_code.get(code)
        if f:
            add(q, "qualitative", theme, f["detail"], f["evidence"], {"type": "finding", "id": f["finding_id"], "step": "review"}, f["code"])
    rel = cd["relationship"]
    pdq = cd["past_dues"]
    if rel.get("years") and rel["years"] >= 5 and pdq["max_dpd_8q"] == 0 and cd["returned_cheques"]["count_12m"] < 3:
        add("strength", "qualitative", "track record", f"Relationship since {rel['since']} ({rel['years']} years) with no past dues in the "
            f"{len(pdq['quarters'])} quarters to {AS_OF} and {cd['returned_cheques']['count_12m']} returned cheque(s) in 12 months.",
            [cd["source"][0], cd["source"][3]], {"type": "fact", "step": "review"}, rel["years"])
    tv = cd["turnover"]
    if tv.get("routing_compliant") is True:
        add("strength", "qualitative", "track record", f"Routing undertaking met: {tv['routing_actual_x']:.2f}x the limits against "
            f"{tv['routing_required_x']:.1f}x required ({tv['routing_achieved_pct']:.0f}%).", [cd["source"][2]], {"type": "fact", "step": "review"},
            tv["routing_achieved_pct"])
    if tv.get("credit_turnover_12m_sar_mn") and tv.get("avg_balance_12m_sar_mn") is not None:
        bal_share = tv["avg_balance_12m_sar_mn"] / tv["credit_turnover_12m_sar_mn"]
        if bal_share < 0.05:
            add("opportunity", "qualitative", "deposits and cross-sell", f"Average balances {_m(tv['avg_balance_12m_sar_mn'])} on credit turnover of "
                f"{_m(tv['credit_turnover_12m_sar_mn'])} in 12 months ({_pct(bal_share)}): room for cash management and liability business.",
                [cd["source"][1]], {"type": "metric", "step": "structure"}, bal_share)
    # market position and concentration from the book and Borrower 360
    sec = ob.get("sector")
    snap = S.records(S.read("dd_portfolio_snapshot", None, dimension="sector", dimension_key=sec))
    if snap:
        s0 = snap[0]
        lp = S.pick(s0, "limit_pct")
        sp = S.pick(s0, "share_pct")
        if lp and sp is not None and sp >= 0.85 * lp:
            add("threat", "qualitative", "market position", f"{sec} is {sp:.1f}% of the corporate book against a {lp:.1f}% limit at {AS_OF}: "
                "little sector headroom for growth.", [_src("dd_portfolio_snapshot", dimension="sector", dimension_key=sec)],
                {"type": "metric", "step": "analysis"}, sp)
    oid = deal.focal_id(p)
    if oid:
        sup = S.records(S.read("rel_edge_quarter", ["source_borrower_id", "target_borrower_id", "purchase_share_pct", "revenue_share_pct"],
                               reporting_quarter=AS_OF, rel_type="SUPPLIES", source_borrower_id=oid))
        if sup:
            top = max(sup, key=lambda r: r["revenue_share_pct"] or 0)
            if (top["revenue_share_pct"] or 0) >= 30:
                nm = F.borrower_attrs([top["target_borrower_id"]]).get(top["target_borrower_id"], {}).get("name", top["target_borrower_id"])
                add("weakness", "qualitative", "customer concentration", f"Largest customer in the bank's book, {nm}, takes {top['revenue_share_pct']:.1f}% "
                    f"of revenue ({AS_OF}).", [_src("rel_edge_quarter", reporting_quarter=AS_OF, rel_type="SUPPLIES", source_borrower_id=oid)],
                    {"type": "fact", "step": "structure"}, top["revenue_share_pct"])
    proj_rows = S.records(S.read("dd_project", None, proposal_id=pid))
    if proj_rows:
        tot = sum(float(S.pick(r, "contract_value_revised_mn", "contract_value_original_mn", "contract_value_revised_sar_mn", "contract_value_sar_mn", default=0) or 0) for r in proj_rows)
        by_emp: dict[str, float] = {}
        for r in proj_rows:
            by_emp[str(S.pick(r, "employer", default="n/a"))] = by_emp.get(str(S.pick(r, "employer", default="n/a")), 0.0) + float(
                S.pick(r, "contract_value_revised_mn", "contract_value_original_mn", "contract_value_revised_sar_mn", "contract_value_sar_mn", default=0) or 0)
        top2 = sorted(by_emp.items(), key=lambda kv: -kv[1])[:2]
        if tot and sum(v for _, v in top2) / tot >= 0.6:
            add("weakness", "qualitative", "concentration of backlog", f"Two employers hold {100 * sum(v for _, v in top2) / tot:.0f}% of the "
                f"financed backlog of {_m(tot)}: {', '.join(k for k, _ in top2)}.", [_src("dd_project", proposal_id=pid)],
                {"type": "fact", "step": "structure"}, sum(v for _, v in top2) / tot)
    drv = SECTOR_DRIVERS.get(sec or "", DEFAULT_DRIVER)
    add("threat", "qualitative", "geopolitics and market", f"{sec or 'The sector'} is exposed to {drv}; the Stress Lab macro family runs these "
        "shocks on this deal.", [_src("dd_proposal", proposal_id=pid)], {"type": "metric", "step": "stress"}, sec)
    if cap and not cap.get("increase_ask") and cap.get("headroom_after") is not None and cap["headroom_after"] > 0:
        add("opportunity", "qualitative", "group headroom", f"{_m(cap['headroom_after'])} of group headroom left under the {cap['binding']} "
            f"of {_m(cap['binding_limit'])} after the deal: room for the group's other companies.", cap["source"],
            {"type": "metric", "step": "structure"}, cap["headroom_after"])

    order = {"strength": 0, "weakness": 1, "opportunity": 2, "threat": 3}
    pts.sort(key=lambda x: (order[x["quadrant"]], x["kind"] != "financial"))
    count = {k: 0 for k in order}
    for x in pts:
        count[x["quadrant"]] += 1
        x["id"] = f"{pid}-SW-{x['quadrant'][0].upper()}{count[x['quadrant']]:02d}"
    quad = {k: [x for x in pts if x["quadrant"] == k] for k in order}
    return {"proposal_id": pid, "obligor": ob["name"], "as_of": AS_OF, "points": pts, "quadrants": quad,
            "counts": {k: len(v) for k, v in quad.items()}, "summary": _summary(ob["name"], quad), "writer": "deterministic"}


def _summary(name: str, q: dict[str, list[dict[str, Any]]]) -> str:
    s = len(q["strength"])
    w = len(q["weakness"])
    o = len(q["opportunity"])
    t = len(q["threat"])
    head = f"{name}: {s} strength{'s' if s != 1 else ''}, {w} weakness{'es' if w != 1 else ''}, {o} opportunit{'ies' if o != 1 else 'y'}, {t} threat{'s' if t != 1 else ''}."
    if q["weakness"]:
        head += f" Main weakness: {q['weakness'][0]['text']}"
    return head


def rows(sw: dict[str, Any], mt: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """The SWOT as rows of `dd_swot` (contract), with the mitigant of each weakness and threat from `mt`."""
    by_id = {r["swot_id"]: r for r in (mt or {}).get("rows", [])}
    out = []
    for x in sw["points"]:
        e0 = x["evidence"][0] if x["evidence"] else {}
        keys = e0.get("keys", {})
        m = by_id.get(x["id"])
        mit_text = mit_ref = None
        covered = None
        if m:
            covered = 0 if m["status"] == "open" else 1
            mit_text = " ".join([s["text"] for s in m["structure"]] + [c["text"] for c in m["conditions"]]) or m.get("suggestion")
            mit_ref = ";".join(c["condition_id"] for c in m["conditions"]) or (",".join(s["lever"] for s in m["structure"]) or None)
        out.append({"swot_id": x["id"], "proposal_id": sw["proposal_id"], "quadrant": x["quadrant"][0].upper(), "kind": x["kind"],
                    "topic": x["theme"].replace(" ", "_"), "text": x["text"], "evidence_relation": e0.get("relation"),
                    "evidence_key": ";".join(f"{k}={','.join(map(str, v)) if isinstance(v, (list, tuple)) else v}" for k, v in keys.items()),
                    "finding_id": x["link"].get("id") if x["link"].get("type") == "finding" else None,
                    "mitigant_text": mit_text, "mitigant_ref": mit_ref, "covered_flag": covered, "reporting_quarter": sw["as_of"]})
    return out


# ===================================================================== weakness -> mitigant


def _answer(t: dict[str, Any], ask: dict[str, Any], theme: str, p: dict[str, Any]) -> list[dict[str, Any]]:
    """The structure levers in `t` that answer a weakness of `theme`, as {lever, text} (empty when none does)."""
    out = []
    coll_types = {c["collateral_id"]: c["type"] for c in p["security"]["collateral"]}
    added = [c for c in t.get("collateral_ids", []) if c not in ask.get("collateral_ids", [])]
    steps = {"none": 0, "standard": 1, "enhanced": 2}
    cov_up = steps.get(t.get("covenant_package"), 0) > steps.get(ask.get("covenant_package"), 0)
    has_cov = steps.get(t.get("covenant_package"), 0) >= 1
    if theme in ("leverage", "debt service", "capital", "profitability", "growth", "liquidity", "related-party balances", "audit quality"):
        if t["amount"] < ask["amount"] - 1e-6:
            out.append({"lever": "amount", "text": f"Amount reduced to {t['amount']:,.1f}m (ask {ask['amount']:,.1f}m)."})
        if t["tenor_years"] < ask["tenor_years"] and theme != "debt service":
            out.append({"lever": "tenor", "text": f"Tenor shortened to {t['tenor_years']} years (ask {ask['tenor_years']})."})
        if theme == "debt service" and (t.get("grace_years", 0) < ask.get("grace_years", 0) or t["tenor_years"] > ask["tenor_years"]):
            out.append({"lever": "repayment", "text": f"Repayment re-profiled: {t['tenor_years']} years, {t.get('grace_years', 0)} grace."})
        if cov_up or (has_cov and theme in ("leverage", "debt service")):
            out.append({"lever": "covenants", "text": f"Covenant package {t['covenant_package']}" + (f" (ask {ask['covenant_package']})" if cov_up else "") + ": "
                        + ("Debt / EBITDA and DSCR tested semi-annually" + ("; cash sweep and negative pledge" if t["covenant_package"] == "enhanced" else "") + ".")})
    if theme in ("collateral", "connected parties", "group exposure", "track record", "returns", "concentration of receivables",
                 "customer concentration", "concentration of backlog", "leverage", "debt service"):
        if added:
            out.append({"lever": "collateral", "text": "Additional security: " + ", ".join(f"{c} ({coll_types.get(c, '')})" for c in added) + "."})
        if t.get("cash_margin_pct", 0) > ask.get("cash_margin_pct", 0):
            out.append({"lever": "cash margin", "text": f"Cash margin {t['cash_margin_pct']:.0f}% (ask {ask.get('cash_margin_pct', 0):.0f}%)."})
        if t.get("guarantee_id") and t.get("guarantee_id") != ask.get("guarantee_id"):
            out.append({"lever": "guarantee", "text": f"Guarantee {t['guarantee_id']} covering {t.get('guarantee_coverage_pct', 0):.0f}%."})
        if (t.get("receivables_assignment_pct") or 0) > (ask.get("receivables_assignment_pct") or 0):
            out.append({"lever": "assignment", "text": f"Assignment of receivables {t['receivables_assignment_pct']:.0f}%."})
    if theme in ("concentration of receivables", "customer concentration", "concentration of backlog"):
        rec = [c for c in t.get("collateral_ids", []) if coll_types.get(c) == "receivables"]
        if rec and not any(o["lever"] == "collateral" for o in out):
            out.append({"lever": "assignment", "text": f"Receivables assigned ({', '.join(rec)}), so collections route to the bank."})
    if theme == "returns":
        for k, lab in (("margin_bps", "Margin"), ("upfront_fee_bps", "Upfront fee"), ("commission_bps", "Commission")):
            if t.get(k, 0) > ask.get(k, 0) + 1e-6:
                out.append({"lever": "pricing", "text": f"{lab} {t[k]:.0f} bps (ask {ask[k]:.0f})."})
    if theme == "group exposure" and t["amount"] < ask["amount"] - 1e-6 and not any(o["lever"] == "amount" for o in out):
        out.append({"lever": "amount", "text": f"Amount held to {t['amount']:,.1f}m (ask {ask['amount']:,.1f}m) to stay within the group cap."})
    return out


#: what answers a weakness when the structure does not: a condition (from the flags) or a suggested lever
SUGGEST = {
    "leverage": "Reduce the amount or shorten the tenor; add a Debt / EBITDA covenant (standard or enhanced package).",
    "debt service": "Re-profile the repayment (sculpted or longer tenor), remove the grace period, or add a cash sweep (enhanced package).",
    "profitability": "Add a margin test to the covenants and review the pricing ratchet.",
    "growth": "Tie the limit to audited revenue; review at the interim results.",
    "liquidity": "Add a current-ratio covenant and a minimum cash balance.",
    "capital": "Subordinate shareholder loans; restrict dividends while leverage is above the covenant.",
    "returns": "Raise the margin or fees, or add collateral to lower the LGD (Optimise).",
    "collateral": "Perfect the security before limit loading; replace shared collateral with a first-ranking charge.",
    "group exposure": "Hold the amount within the group cap, or put the increase-cap ask to its approval authority.",
    "concentration of receivables": "Assign receivables of the largest customers; add a concentration covenant.",
    "customer concentration": "Assign the receivables of the largest customer; add a concentration covenant.",
    "concentration of backlog": "Finance against certified payment certificates only; cover-ratio covenant on remaining contract proceeds.",
    "related-party balances": "Subordinate and freeze related-party balances; no inter-group use of the facility.",
    "audit quality": "Require an auditor from the approved panel and audited accounts within 120 days.",
    "geopolitics and market": "Run the Stress Lab macro family on this deal; a driver that breaks at moderate severity becomes a named monitoring trigger.",
    "market position": "Hold the amount within the sector headroom; price for the sector add-on.",
    "bureau": "Updated bureau reports for every group entity and UBO prior to limit loading.",
}


def mitigants(pid: str, terms: dict[str, Any] | None = None, label: str = "ask", sw: dict[str, Any] | None = None,
              ev: dict[str, Any] | None = None) -> dict[str, Any]:
    """Each weakness and threat with what answers it: the structure (`terms`, default the ask), a condition, or nothing yet."""
    from backend.dealdesk import engine
    p = deal.get(pid)
    ask = engine.merge_terms(p, None)
    t = engine.merge_terms(p, terms) if terms else ask
    sw = sw or build(pid)
    if ev is None:
        ev = FL.evaluate(pid)
    cond_by_finding = {c["source_finding"]: c for c in ev["conditions"]}
    ubo_pg = next((c for c in ev["conditions"] if c["source_finding"].endswith("GOV-UBO-PG")), None)
    rows = []
    for x in sw["points"]:
        if x["quadrant"] not in ("weakness", "threat"):
            continue
        by_structure = _answer(t, ask, x["theme"], p)
        cond = cond_by_finding.get(x["link"].get("id")) if x["link"].get("type") == "finding" else None
        conds = [c for c in (cond, ubo_pg if x["theme"] in ("governance", "connected parties", "ownership change", "management", "track record") else None) if c]
        status = "answered by the structure" if by_structure else "answered by a condition" if conds else "open"
        rows.append({"swot_id": x["id"], "quadrant": x["quadrant"], "theme": x["theme"], "weakness": x["text"], "status": status,
                     "structure": by_structure, "conditions": [{"condition_id": c["condition_id"], "text": c["text"], "kind": c["kind"],
                                                                 "due": c["due"]} for c in conds],
                     "suggestion": None if status != "open" else SUGGEST.get(x["theme"], "Monitor through the review cycle; no structure lever applies."),
                     "link": x["link"]})
    n_open = sum(1 for r in rows if r["status"] == "open")
    return {"proposal_id": pid, "structure_label": label, "terms": {k: t.get(k) for k in ("amount", "tenor_years", "grace_years", "amortisation",
                                                                                        "margin_bps", "covenant_package", "collateral_ids",
                                                                                        "guarantee_id", "cash_margin_pct")},
            "rows": rows, "counts": {"total": len(rows), "structure": sum(1 for r in rows if r["status"] == "answered by the structure"),
                                     "condition": sum(1 for r in rows if r["status"] == "answered by a condition"), "open": n_open},
            "headline": (f"{len(rows) - n_open} of {len(rows)} weaknesses and threats answered by the {label} structure or its conditions"
                         + (f"; {n_open} open." if n_open else ".")) if rows else "No weakness or threat to answer."}
