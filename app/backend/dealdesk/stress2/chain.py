"""The transmission chain of one scenario (I19-1): shock -> revenue -> EBITDA -> ratios -> rating -> PD -> stage ->
ECL / RAROC / covenants, each step with its number and its source (relation and row). Deal facts replace sector
defaults where the deal file has them, and the step says so (I19-5).

`explain(proposal_id, scenario_id)` answers "how was this scenario built" for the Deal Desk thread and Noor, from
the chain alone (deterministic, N6).
"""
from __future__ import annotations

import re
from typing import Any

from backend.dealdesk import stress_lab as sl


def _x(v: Any) -> str:
    if v is None:
        return "–"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if f != f or f in (float("inf"), float("-inf")):
        return "n/m"
    return f"{f:.2f}x"


def _p(v: Any, dp: int = 1) -> str:
    return "–" if v is None else f"{float(v) * 100:.{dp}f}%"


def _m(v: Any) -> str:
    return "–" if v is None else f"{float(v):,.1f} m"


def chain(lab: sl.Lab, row: dict[str, Any], base: dict[str, Any]) -> list[dict[str, Any]]:
    p = lab.p
    m, f, b = row["metrics"], row["financials"], base["metrics"]
    yr = next(y for y in reversed(p["financials"]["years"]) if y["kind"] == "actual")
    fin_src = f"{yr.get('source', 'Financial statements')} {yr['year']}"
    out: list[dict[str, Any]] = []

    from backend.dealdesk.stress2 import store
    lin: dict[str, dict[str, Any]] = {}

    def add(stage: str, label: str, before: Any, after: Any, display: str, source: str, relation: str, row_: str, **kw: Any) -> None:
        if relation and relation not in lin:
            lin[relation] = store.lineage(relation)
        li = lin.get(relation, {})
        out.append({"stage": stage, "label": label, "before": before, "after": after, "display": sl._m(display), "source": source,
                    "relation": relation, "row": row_, "domain": li.get("domain"), "period": li.get("period"), **kw})

    for s in row.get("steps", []):
        if s["step"] == "Parts that do not apply":
            add("shock", "Not applied", None, None, s["display"], "", "", "")
            continue
        add("shock", s["step"] + (f" ({s['part']})" if s.get("part") else ""), None, s["value"], s["display"], s["source"],
            s["relation"], s["row"], deal_fact=s.get("deal_fact", False), band=s.get("band"), trace=s.get("trace"))
    res = row.get("resolved") or {}
    fc = row.get("fixed_cost_share")
    add("revenue", "Revenue", f["base_revenue"], f["revenue"], f"{_m(f['base_revenue'])} -> {_m(f['revenue'])}", fin_src,
        "dd_obligor_financials", f"{p['proposal_id']} {yr['year']}")
    m0 = f["base_ebitda"] / f["base_revenue"] if f["base_revenue"] else 0
    lev = lab.p["obligor"]["sector"]
    add("ebitda", "EBITDA (operating leverage)", f["base_ebitda"], f["ebitda"],
        f"{_m(f['base_ebitda'])} -> {_m(f['ebitda'])}: revenue change x (margin {m0 * 100:.1f}% + fixed-cost share)"
        + (" plus the margin shock" if res.get("ebitda_margin_bps") else ""),
        f"fixed-cost share for {lev} (dd_stress_sensitivity fixed_cost_share)" + (f" = {fc * 100:.0f}%" if fc is not None else ""),
        "dd_stress_sensitivity", f"fixed_cost_share / {lev}")
    if f.get("working_capital_funded"):
        add("ebitda", "Working capital funded", 0.0, f["working_capital_funded"], f"{_m(f['working_capital_funded'])} of new short-term debt",
            "short-term funding spread (dd_stress_sensitivity)", "dd_stress_sensitivity", "short_term_funding_spread_bps")
    add("ratios", "DSCR after the deal", b["dscr"], m["dscr"], f"{_x(b['dscr'])} -> {_x(m['dscr'])}", "engine: EBITDA / (debt service + deal debt service)",
        "dd_result", "engine.analyse")
    add("ratios", "Debt/EBITDA", b["debt_ebitda"], m["debt_ebitda"], f"{_x(b['debt_ebitda'])} -> {_x(m['debt_ebitda'])}", "engine",
        "dd_result", "engine.analyse")
    if m.get("ltv_cover") is not None:
        add("ratios", "LTV (all collateral)", b.get("ltv_cover"), m["ltv_cover"], f"{_p(b.get('ltv_cover'))} -> {_p(m['ltv_cover'])}",
            "funded exposure / pledged collateral after the shock", "dd_collateral_guarantee", ",".join(lab.t.get("collateral_ids", [])))
    n = m["notches"]
    add("rating", "Rating", lab.rating0, m["rating"],
        f"{lab.rating0} -> {m['rating']}: {n['scenario']} notch{'es' if n['scenario'] != 1 else ''} from the scenario + {n['implied']} from the stressed ratios",
        sl._tr("rating_overlay")["basis"][:160], "dd_parameter", "stress rating_overlay")
    add("pd", "PD 12 months", b["pd_12m"], m["pd_12m"], f"{_p(b['pd_12m'], 2)} -> {_p(m['pd_12m'], 2)}",
        "What-If PD model re-scored at the stressed grade", "dd_parameter", "pd_master_scale")
    add("stage", "IFRS 9 stage", 1, m["stage"], f"Stage {m['stage']}: {m['stage_reason']}", sl._tr("stage_rules")["basis"][:160],
        "dd_parameter", "pd_migration.sicr_notches")
    add("ecl", "ECL", b["ecl"], m["ecl"], f"{_m(b['ecl'])} -> {_m(m['ecl'])}: {m['ecl_basis']}",
        "engine EAD x PD x LGD", "dd_result", "engine.analyse")
    chk = row.get("raroc_check") or {}
    for s in chk.get("steps", []):
        add("raroc", s["step"], None, s["raroc"], f"RAROC {_p(s['raroc'])}" + (f" ({(s['delta'] or 0) * 100:+.2f} pts)" if s.get("delta") is not None else ""),
            s["basis"], "dd_result", "stress2.raroc_check")
    add("raroc", "Checked stressed RAROC against the hurdle", b.get("lifetime_raroc"), m["lifetime_raroc"],
        f"{_p(m['lifetime_raroc'])} against a {_p(m['hurdle'])} hurdle ({'clears' if m['clears_hurdle'] else 'below'})", "engine + O4 check",
        "dd_parameter", "returns.hurdle")
    for c in row.get("covenants", []):
        if c["status"] == "not_modelled":
            continue
        add("covenants", f"Covenant {c['type']}", c["threshold"], c["value"], f"{c['type']} {_x(c['value'])} against {_x(c['threshold'])}: {c['status']}",
            c["basis"], "dd_proposal", f"{p['proposal_id']} covenants")
    return out


def narrate(row: dict[str, Any]) -> str:
    """'How was this scenario built': the chain in sentences."""
    ch = row.get("chain") or []
    if not row.get("applicable"):
        return f"{row['label']} does not apply to this deal: {row.get('na_reason', '').replace('Not applicable to this deal: ', '')}"
    shocks = [c for c in ch if c["stage"] == "shock" and c["label"] != "Not applied"]
    parts = [f"{row['label']} ({row['severity']}, {row.get('family')} family) was built in {len(ch)} steps."]
    if shocks:
        parts.append("The shock: " + "; ".join(f"{c['display']} [{'deal file' if c.get('deal_fact') else c['source'].split(':')[0]}]" for c in shocks) + ".")
    get = {c["label"]: c for c in ch}
    for lab in ("Revenue", "EBITDA (operating leverage)", "DSCR after the deal", "Debt/EBITDA", "Rating", "PD 12 months", "IFRS 9 stage", "ECL"):
        if lab in get:
            parts.append(f"{lab}: {get[lab]['display']}.")
    fin = get.get("Checked stressed RAROC against the hurdle")
    if fin:
        parts.append(f"RAROC (PD, capital, ECL and the pricing ratchet at the stressed rating): {fin['display']}.")
    cov = [c for c in ch if c["stage"] == "covenants"]
    if cov:
        parts.append("Covenants: " + "; ".join(c["display"] for c in cov) + ".")
    deal = [c for c in ch if c.get("deal_fact")]
    if deal:
        parts.append("Deal facts used instead of sector defaults: " + "; ".join(c["source"] for c in deal) + ".")
    return " ".join(parts)


def explain(proposal_id: str, scenario_id: str, terms: dict[str, Any] | None = None) -> dict[str, Any]:
    """For the Deal Desk thread and Noor: {answer, chain, row}."""
    from backend.dealdesk.stress2 import catalogue as cat, ladder, store
    p = store.deal(proposal_id)
    sid = resolve_scenario_id(scenario_id, proposal_id)
    if sid is None:
        names = ", ".join(s["label"] for s in cat.scenarios(proposal_id)[:6])
        return {"answer": f"No scenario called '{scenario_id}' for {proposal_id}. Try one of: {names}.", "chain": [], "row": None}
    out = ladder.run(p, terms, scenario_ids=[sid], reverse=False, publish=False)
    row = out["rows"][0]
    return {"answer": narrate(row), "chain": row.get("chain", []), "row": {k: row.get(k) for k in ("id", "label", "family", "severity", "applicable", "na_reason")},
            "sensitivity_version": out["sensitivity_version"]}


def resolve_scenario_id(text: str, proposal_id: str | None = None) -> str | None:
    """A scenario id or a label in words ('oil -30%', 'combined severe', 'rating -2 notches')."""
    from backend.dealdesk.stress2 import catalogue as cat
    sc = cat.scenarios(proposal_id)
    t = (text or "").strip().lower().replace("−", "-").replace("–", "-")
    for s in sc:
        if s["scenario_id"].lower() == t:
            return s["scenario_id"]
    norm = lambda x: "".join(ch for ch in x.lower().replace("−", "-") if ch.isalnum() or ch in "-%.")  # noqa: E731
    nt = norm(t)
    for s in sc:
        if norm(s["label"]) and norm(s["label"]) in nt:
            return s["scenario_id"]
    words = set(t.replace("%", " ").split())
    best = max(sc, key=lambda s: len(words & set(s["label"].lower().replace("−", "-").replace("%", " ").split())), default=None)
    if best and len(words & set(best["label"].lower().replace("−", "-").replace("%", " ").split())) >= 2:
        return best["scenario_id"]
    return None


_ASK = re.compile(r"\b(how (?:was|is|were|did)|explain|walk me through|built|build|chain|transmission|where does)\b.*\b(scenario|stress|shock|oil|gdp|rates?|revenue|notch|downgrade|combined|severe|collateral|customer|delay)\b", re.I)


def is_stress_question(question: str) -> bool:
    """For the Deal Desk thread and Noor's router: is this 'how was this scenario built'?"""
    return bool(_ASK.search(question or ""))


def answer_question(proposal_id: str, question: str, terms: dict[str, Any] | None = None) -> dict[str, Any]:
    """The Deal Desk thread / Noor entry point: 'how was the oil −30% scenario built', 'explain combined severe'.
    Returns {answer, scenario_id, chain, question}; the answer is deterministic (N6) and comes from the chain."""
    from backend.dealdesk.stress2 import catalogue as cat
    q = (question or "").strip()
    m = re.search(r"(?:how (?:was|is|were)|explain|build of|built)\s+(?:the\s+)?(.+?)(?:\s+scenario)?(?:\s+built)?\s*\??$", q, re.I)
    target = (m.group(1) if m else q).strip()
    sid = resolve_scenario_id(target, proposal_id) or resolve_scenario_id(q, proposal_id)
    if sid is None:
        names = ", ".join(s["label"] for s in cat.scenarios(proposal_id)[:8])
        return {"answer": f"Which scenario? For example: {names}.", "scenario_id": None, "chain": [], "question": question}
    out = explain(proposal_id, sid, terms)
    return {**out, "scenario_id": sid, "question": question}


def traced_figures(row: dict[str, Any]) -> list[dict[str, Any]]:
    """The chain's figures that point at one Data Domains row ({value, source}, E's lineage shape)."""
    out = []
    for c in row.get("chain") or []:
        if c.get("trace") and isinstance(c.get("after"), (int, float)) and not isinstance(c.get("after"), bool):
            out.append({"label": c["label"], "value": float(c["after"]), "source": c["trace"]})
    return out
