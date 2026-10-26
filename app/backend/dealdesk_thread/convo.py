"""The Deal Desk conversation (DEAL_DESK_PROMPT section 5, PLAN_R4 G2).

A domain on the shared conversational layer (`backend/convo`, the fork of the
frozen Cockpit architecture: understand, plan, query, answer, validate,
publish), scoped to the Deal Desk domain and read-only portfolio headroom.
The assistant's tools are the engine API (DEALDESK_API.md): every figure in an
answer comes from one of these calls, carries its trace ID, and the layer's
validator removes any figure that is not in a result of the turn. The
optimiser runs only when the user presses Optimise or asks to optimise.

With the model key the assistant (Opus) plans the calls and writes; without
it the deterministic planner below reads the intent, calls the same tools and
writes the same commentary through the same validation.

Intents: ingest, optimise with constraints in plain language, explain,
what-if on terms, compare, stress, draft (risk opinion, conditions precedent,
covenants), portfolio headroom, and a summary of the proposal.

PLAN_R11 U3 adds (r11_intents.py): forward risk (Stage 2 / 30+ DPD next
quarter), early warning on the deal, the Stress Lab (named and custom shocks,
what breaks first), test against pipeline, optimise the pipeline, memo review
and the committee decision sheet.
"""
from __future__ import annotations

import re
from typing import Any

import pandas as pd

from backend.convo import provider as prov
from backend.convo.agent import Agent
from backend.convo.spec import Domain, Plan, PlanStep, Relation, Tool, ToolContext, ToolResult
from backend.convo.validate import numbers
from backend.dealdesk import fmt as F
from backend.dealdesk_thread import engine
from backend.dealdesk_thread import r11_intents as r11
from backend.v5common import ratings

RATINGS = ["AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB", "BBB-", "BB+", "BB", "BB-", "B+", "B", "B-", "CCC", "CC", "C"]
FIELD_LABEL = {"amount": "amount", "tenor_years": "tenor", "grace_years": "grace", "margin_bps": "margin", "upfront_fee_bps": "upfront fee",
               "commitment_fee_bps": "commitment fee", "commission_bps": "commission", "cash_margin_pct": "cash margin",
               "guarantee_coverage_pct": "guarantee cover", "collateral_ids": "collateral", "structure": "structure",
               "balloon_pct": "balloon", "guarantee_id": "guarantee", "prepayment_fee_bps": "prepayment fee", "hold_pct": "hold level",
               "rate_type": "rate", "insurance_cover_pct": "credit insurance cover", "receivables_assignment_pct": "assigned receivables",
               "covenant_items": "covenants", "review_cycle_months": "review cycle", "cross_sell": "cross-sell commitments",
               "amortisation": "amortisation", "covenant_package": "covenant package", "facility_type": "facility type",
               "funded_share_pct": "funded share"}
GUARANTEE_NAME = {"REQ-PARENT": "a parent guarantee", "REQ-BANK": "a bank guarantee", "REQ-SOVEREIGN": "a sovereign guarantee",
                  "REQ-ECA": "export credit agency cover"}


# ------------------------------------------------------------------ formatting (figures copied from engine results)

def pct(x: float | None, d: int | None = None) -> str:
    return "n/a" if x is None else F.pct(x, d)


def sar(x: float | None) -> str:
    if x is None:
        return "n/a"
    if abs(x) < 0.005:
        x = 0.0
    sign, a = ("−" if x < 0 else ""), abs(x)
    return sign + (f"SAR {a / 1000:,.2f}bn" if a >= 1000 else f"SAR {a:,.1f}m" if a >= 10 else f"SAR {a:,.2f}m")


CONSTRAINT_LABEL = {"single_name": "Single name", "group_large_exposure": "Group large exposure", "group_internal": "Group internal limit",
                    "sector": "Sector concentration", "rating_bucket": "Rating bucket", "collateral_type": "Collateral-type concentration",
                    "min_rating": "Minimum rating", "max_tenor": "Maximum tenor for the grade", "ltv": "Maximum LTV", "dscr": "Minimum DSCR",
                    "debt_ebitda": "Maximum Debt/EBITDA", "balloon": "Maximum balloon", "bu_rwa_budget": "Business-unit RWA budget",
                    "bu_el_budget": "Business-unit EL budget", "hurdle": "RAROC hurdle", "margin_bps": "Margin",
                    "market_margin_cap": "Market margin cap", "market_fee_cap": "Market fee cap", "group_connected": "Connected group",
                    "sector_policy": "Sector policy limit", "sector_appetite": "Sector appetite", "amount_floor": "Minimum amount share",
                    "amount": "Amount", "structure": "Structure"}


def relax_value(x: dict, v: float | None) -> str:
    if v is None:
        return "not reachable"
    u = x["unit"]
    if u in ("ratio", "share"):
        return pct(v)
    if u == "notch":
        return RATINGS[max(0, min(len(RATINGS) - 1, int(-v)))]
    if u == "SAR m":
        return sar(v)
    if isinstance(v, str):
        return v
    if u == "bps":
        return F.bps(v)
    if u == "x":
        return F.times(v)
    return f"{F.num(v)} {u}".strip()


def amt(x: float, ccy: str) -> str:
    return F.amount(x, ccy)


def cval(c: dict, v: Any = None) -> str:
    v = c["value"] if v is None else v
    u = c.get("unit", "")
    if v is None:
        return "n/a"
    if isinstance(v, str):
        return v
    if u in ("share", "ratio"):
        return pct(v)
    if u == "x":
        return F.times(v)
    if u == "SAR m":
        return sar(v)
    if u == "years":
        return f"{F.num(v)} years"
    if u == "notch":
        return RATINGS[max(0, min(len(RATINGS) - 1, int(-v)))]
    return f"{F.num(v)} {u}".strip()


def lever_value(f: str, v: Any, ccy: str = "SAR") -> str:
    """A lever value in words (G5): bps integer, % to 1 decimal, amounts in the deal currency."""
    if v is None:
        return "none"
    if isinstance(v, list):
        return ", ".join(str(x).replace("_", " ") for x in v) or "none"
    if isinstance(v, str):
        return GUARANTEE_NAME.get(v, v.replace("_", " "))
    if f == "amount":
        return amt(v, ccy)
    if f.endswith("bps"):
        return F.bps(v)
    if f.endswith("pct"):
        return f"{round(float(v), 1):g}%"
    if f in ("tenor_years", "grace_years"):
        return f"{F.num(v)} years"
    if f == "review_cycle_months":
        return f"{F.num(v)} months"
    return F.num(v)


def change_text(c: dict, ccy: str) -> str:
    f = c["field"]
    if f == "collateral_ids":
        return "additional collateral pledged"
    if f == "guarantee_id":
        return f"{GUARANTEE_NAME.get(c['value'], 'guarantee')} added" if c["value"] else "guarantee released"
    lab = FIELD_LABEL.get(f, f.replace("_", " "))
    return f"{lab} {lever_value(f, c['ask'], ccy)} → {lever_value(f, c['value'], ccy)}"


# ------------------------------------------------------------------ the engine as tools

def _pid(ctx: ToolContext, args: dict) -> str:
    pid = str(args.get("proposal_id") or ctx.scope.get("proposal_id") or "")
    if not pid:
        raise ValueError("Name a proposal (DD-nn), or open one from the pipeline.")
    return pid


def _terms(ctx: ToolContext) -> dict | None:
    return (ctx.state or {}).get("terms")


def t_get_proposal(ctx: ToolContext, args: dict) -> ToolResult:
    pid = _pid(ctx, args)
    r = engine.get(f"/proposals/{pid}")
    p = r["proposal"]
    ob = p["obligor"]
    return ToolResult(summary=f"{pid}: {ob['name']}, {ob['sector']}, rating {ob['internal_rating']}",
                      data={"trace_id": r["trace_id"], "obligor": {k: ob[k] for k in ("name", "sector", "region", "internal_rating", "existing",
                                                                                    "existing_exposure_sar_mn", "group_name", "simah_flag")},
                            "ask": p["ask"], "purpose": p.get("purpose", "")})


def t_compute(ctx: ToolContext, args: dict) -> ToolResult:
    pid = _pid(ctx, args)
    which = args.get("terms_from") or "changes"
    base = None if which == "ask" else (_terms(ctx) or None)
    terms = {**(base or {}), **(args.get("changes") or {})} or None
    r = engine.post("/compute", {"proposal_id": pid, "terms": terms})
    m = r["metrics"]
    rows = [{"constraint": c["label"], "value": cval(c), "limit": cval(c, c["limit"]), "kind": c["kind"], "status": c["status"]}
            for c in r["constraints"]]
    return ToolResult(summary=f"Lifetime RAROC {pct(m['lifetime_raroc'])} against a hurdle of {pct(m['hurdle'])}",
                      data={"trace_id": r["trace_id"], "terms": r["terms"], "metrics": m, "approval": r["approval"],
                            "constraints": r["constraints"], "waterfall": r["waterfall"], "pd": {k: r["pd"][k] for k in ("model_pd_12m", "master_scale_pd_12m")}},
                      rows=rows)


def t_why_fails(ctx: ToolContext, args: dict) -> ToolResult:
    """R14 E (K24): why the ask fails, from the findings engine: every finding (review rules, dd_review_finding incl.
    financial quality), capacity, covenant headroom, pricing, limits and the approval authority."""
    pid = _pid(ctx, args)
    r = engine.get(f"/engines/{pid}/why-fails")
    return ToolResult(summary=r["headline"], data={"headline": r["headline"], "lines": r["lines"], "verdict": r["verdict"],
                                                   "counts": r["counts"]},
                      rows=[{"severity": x["severity"], "kind": x["kind"], "text": x["text"]} for x in r["lines"]])


def t_optimise(ctx: ToolContext, args: dict) -> ToolResult:
    pid = _pid(ctx, args)
    fixed, bounds = dict(args.get("fixed") or {}), dict(args.get("bounds") or {})
    excluded = set(bounds.pop("exclude_collateral_types", None) or [])
    if excluded:
        # The engine takes collateral as a held lever: the ask's pledges without the excluded types.
        p = engine.get(f"/proposals/{pid}")["proposal"]
        kinds = {c["collateral_id"]: c["type"] for c in p["security"]["collateral"]}
        fixed["collateral_ids"] = [c for c in p["ask"].get("collateral_ids") or [] if kinds.get(c) not in excluded]
    req = {"proposal_id": pid, "objective": "both", "fixed": fixed, "bounds": bounds, "allow_soft": bool(args.get("allow_soft"))}
    r = engine.post("/optimize", req)
    st = {"optimisation": {"trace_id": r["trace_id"], "feasible": r["feasible"]}, "optimise_request": req}
    return ToolResult(summary="Feasible" if r["feasible"] else "No feasible structure", data=r, state=st,
                      rows=[{"offer": o["label"], "lifetime_raroc": o["metrics"]["lifetime_raroc"], "sva": o["metrics"]["sva"],
                             "distance": o["distance"], "approval": o["approval"]["level"]}
                            for o in [r.get("closest"), r.get("max_sva"), *(r.get("counter_offers") or [])] if o])


def t_stress(ctx: ToolContext, args: dict) -> ToolResult:
    pid = _pid(ctx, args)
    r = engine.post("/stress", {"proposal_id": pid, "terms": _terms(ctx), "scenario": args.get("scenario") or "all"})
    return ToolResult(summary=f"Robust to {r['robustness_notches']} notches", data=r,
                      rows=[{"scenario": x["label"], "lifetime_raroc": x["lifetime_raroc"], "sva": x["sva"], "clears_hurdle": x["clears_hurdle"]}
                            for x in r["rows"]])


def t_headroom(ctx: ToolContext, args: dict) -> ToolResult:
    dim = args.get("dimension") or ""
    if dim:
        r = engine.get("/headroom", dimension=dim)
        return ToolResult(summary=f"Portfolio headroom by {dim}", data=r, rows=r.get("rows") or [])
    pid = _pid(ctx, args)
    r = engine.get("/headroom", proposal_id=pid)
    return ToolResult(summary="The obligor's headroom", data=r, rows=r.get("limits") or [])


def t_explain(ctx: ToolContext, args: dict) -> ToolResult:
    name = str(args.get("name") or "")
    pid = ctx.scope.get("proposal_id") or ""
    r = engine.get(f"/constraints/{name}", proposal_id=pid)
    return ToolResult(summary=r.get("definition") or name, data=r)


def t_compare(ctx: ToolContext, args: dict) -> ToolResult:
    pid = _pid(ctx, args)
    sets = args.get("term_sets") or []
    r = engine.post("/compare", {"proposal_id": pid, "term_sets": sets})
    return ToolResult(summary="Compared", data=r, rows=[{"structure": x["label"], "lifetime_raroc": x["metrics"]["lifetime_raroc"],
                                                         "sva": x["metrics"]["sva"], "approval": x["approval"]["level"]} for x in r["rows"]])


def t_breakeven(ctx: ToolContext, args: dict) -> ToolResult:
    pid = _pid(ctx, args)
    r = engine.post("/breakeven", {"proposal_id": pid, "terms": _terms(ctx), "lever": args.get("lever") or "margin_bps"})
    return ToolResult(summary=f"Breakeven {r.get('value')} {r.get('unit')}", data=r)


def t_alternatives(ctx: ToolContext, args: dict) -> ToolResult:
    """R5 D4: 2-4 alternative structures over the full lever set, and the minimum change on each single lever."""
    pid = _pid(ctx, args)
    r = engine.post("/alternatives", {"proposal_id": pid, "terms": _terms(ctx), "fixed": args.get("fixed") or {},
                                      "bounds": args.get("bounds") or {}, "allow_soft": bool(args.get("allow_soft"))})
    return ToolResult(summary=f"{len(r['alternatives'])} alternative structures", data=r,
                      rows=[{"structure": a["label"], "lifetime_raroc": a["metrics"]["lifetime_raroc"], "sva": a["metrics"]["sva"],
                             "approval": a["approval"]["level"]} for a in r["alternatives"]])


OBJ = {"type": "object"}
TOOLS = [
    Tool("get_proposal", "The proposal: obligor, the ask, purpose.", {"type": "object", "properties": {"proposal_id": {"type": "string"}}}, t_get_proposal),
    Tool("compute_terms", "Compute lifetime RAROC, SVA, capital, EL, limits and the approval level for a term set. `changes` are merged onto "
         "the thread's current terms (or the ask when terms_from='ask'). Never optimises.",
         {"type": "object", "properties": {"proposal_id": {"type": "string"}, "terms_from": {"type": "string", "enum": ["ask", "changes"]},
                                           "changes": OBJ}}, t_compute, message="Computing the structure"),
    Tool("optimise", "Run the optimiser: the closest-to-ask structure that clears the hurdle and every hard limit, the maximum-SVA structure, "
         "counter-offers, the frontier, binding constraints, or the minimum relaxation. Only when the user asks to optimise or restructure. "
         "`fixed` holds terms at a value; `bounds` narrows ranges (e.g. {margin_bps:[lo,hi]}, {exclude_collateral_types:[...]}).",
         {"type": "object", "properties": {"proposal_id": {"type": "string"}, "fixed": OBJ, "bounds": OBJ, "allow_soft": {"type": "boolean"}}},
         t_optimise, message="Optimising the structure"),
    Tool("stress", "Stress the current structure: downgrade_1, downgrade_2, collateral_20, collateral_30, saibor_200, utilisation, or all.",
         {"type": "object", "properties": {"proposal_id": {"type": "string"}, "scenario": {"type": "string"}}}, t_stress, message="Stressing"),
    Tool("headroom", "Portfolio headroom by dimension (sector, rating_bucket, collateral_type, group), or the obligor's limits.",
         {"type": "object", "properties": {"dimension": {"type": "string"}, "proposal_id": {"type": "string"}}}, t_headroom, message="Reading headroom"),
    Tool("explain_constraint", "The definition of a constraint and the deal's value against it.",
         {"type": "object", "required": ["name"], "properties": {"name": {"type": "string"}}}, t_explain),
    Tool("compare", "Compare 2 to 5 term sets side by side: [{label, terms}].",
         {"type": "object", "required": ["term_sets"], "properties": {"proposal_id": {"type": "string"}, "term_sets": {"type": "array"}}}, t_compare),
    Tool("alternatives", "Alternative structures over the full lever set (pricing, structure, risk mitigation, covenants): 2-4 structures that "
         "clear the hurdle with their changed terms, RAROC, SVA, approval and lever contributions, plus the minimum change on each single "
         "lever that clears alone. Use for 'what are my options', 'which levers', 'minimum change'. Never runs the full optimiser.",
         {"type": "object", "properties": {"proposal_id": {"type": "string"}, "fixed": OBJ, "bounds": OBJ, "allow_soft": {"type": "boolean"}}},
         t_alternatives, message="Searching the levers"),
    Tool("breakeven", "The value of one lever at which lifetime RAROC equals the hurdle, others held.",
         {"type": "object", "properties": {"proposal_id": {"type": "string"}, "lever": {"type": "string"}}}, t_breakeven),
    Tool("why_fails", "Why the ask fails: every critical and major finding (review rules, published review findings incl. financial "
         "quality, conduct, bureau, governance, documents), capacity against the ask, covenant headroom, price, limits and the approval "
         "authority. Use for any 'why does it fail', 'why not approve', 'what is wrong with this deal'.",
         {"type": "object", "properties": {"proposal_id": {"type": "string"}}}, t_why_fails, message="Reading every finding"),  # R14 E
    *r11.TOOLS,
]

KNOWLEDGE = {
    "raroc": "Lifetime RAROC = PV(risk-adjusted profit) / PV(capital). Risk-adjusted profit = profit income + fees − FTP − opex − EL − zakat "
             "+ capital benefit. SVA = PV(risk-adjusted profit − hurdle × capital). The bar is RAROC ≥ hurdle (SVA ≥ 0), not RAROC > 0.",
    "lgd": "Facility LGD = max(floor, (EAD − Σ haircut-adjusted collateral) / EAD × unsecured LGD), with the structure adjustment "
           "(Ijara lowers it). Guarantees substitute the guarantor on the covered portion.",
    "pd": "The obligor's 12-month PD comes from the corporate XGBoost model (What-If domain, read-only), obligor features only; deal terms "
          "never enter it except post-deal leverage and DSCR. Economic capital uses the through-the-cycle PD of the master scale.",
    "optimiser": "Closest to ask minimises the weighted distance from the ask (amount cut, then tenor cut, then margin increase, then added "
                 "collateral, then fees) subject to RAROC ≥ hurdle and every hard limit; soft limits only when escalation is on.",
    "approval": "The approval level comes from the one approval-authority engine (Delegation of Authority): the highest level that any of "
                "exposure after the deal (existing + new limit), rating, the number of exceptions, a policy exception (pricing below the "
                "hurdle: CRO), a hard-limit breach (Board Credit Committee) or SIMAH needs; the binding rule is stated with the level.",
    "levers": "The risk manager's levers and the RAROC channel each moves. Pricing: margin, upfront/arrangement fee, commitment fee on "
              "undrawn, prepayment fee (income). Structure: tenor (FTP, PD horizon, IRB maturity), amortisation equal/sculpted/balloon and "
              "grace (average exposure), amount and hold level/sell-down (concentration and capital; arranger skim on the sold share), "
              "facility type and funded share (CCF), fixed or floating rate (FTP: ALM premium). Risk mitigation: cash margin (EAD net of "
              "cash: RWA and LGD), collateral (LGD), guarantees from a parent, bank, sovereign or ECA (PD substitution on the covered "
              "part), credit insurance (LGD and capital relief), assignment of receivables (LGD). Covenants: leverage, DSCR, cash sweep, "
              "dividend lock-up, negative pledge (PD/LGD overlay, capped), shorter review cycle (PD and effective maturity). "
              "Relationship: cross-sell commitments raise relationship RAROC, not deal RAROC. Each lever has an owned parameter table.",
}

CHARTER = ("You are the Deal Desk assistant of a Saudi bank's credit risk function. A credit risk manager is restructuring a credit "
           "proposal so it clears the RAROC hurdle and stays inside risk appetite and the regulatory limits. You explain, test structures "
           "and draft; the Deal Desk engine computes every figure. Never compute RAROC, capital, EL or a limit yourself and never choose "
           "terms yourself: call the tools and quote their results. Run `optimise` only when the user asks to optimise or restructure. "
           "After an analysis, comment briefly: the ask, whether it clears the hurdle and appetite, what binds, the recommended structure "
           "and what changed, the trade-off against the next-best alternative, and the required approval level. Amounts are SAR million "
           "unless the deal currency is stated; ratios are percentages. Write every number as the house formatter does (PLAN_R5 G5): "
           "amounts as SAR m or bn with 1-2 decimals, percentages with 1-2 decimals (never a fraction such as 0.28 for 28%), ratios "
           "such as DSCR with 2 decimals, bps as whole numbers; tables with plain-words headers and units, never column keys. "
           "For a deal below the hurdle, use `alternatives` to name the structures that clear it and the levers that clear alone. "
           "Forward risk (Stage 2 or 30+ DPD next quarter, ECL path, early warning on the deal) is `forward_risk`; named or custom "
           "scenarios and what breaks first are `stress_lab`; the pending pipeline is `pipeline_test` and `pipeline_optimise`; the "
           "memo's findings and the committee decision sheet are `review_memo`. Answer first in one line, then the evidence.")


def relations(scope: dict) -> list[Relation]:
    def proposals(_s: dict) -> pd.DataFrame:
        rows = engine.get("/proposals")["proposals"]
        return pd.DataFrame(rows)

    def checks(_s: dict) -> pd.DataFrame:
        out = []
        for p in engine.get("/proposals")["proposals"]:
            r = engine.post("/compute", {"proposal_id": p["proposal_id"]})
            out.append({"proposal_id": p["proposal_id"], "obligor_name": p["obligor_name"], "lifetime_raroc": r["metrics"]["lifetime_raroc"],
                        "clears_hurdle": r["metrics"]["clears_hurdle"], "approval": r["approval"]["level"], "trace_id": r["trace_id"],
                        "hard_breaches": ", ".join(c["label"] for c in r["constraints"] if c["status"] == "breach" and c["kind"] == "hard"),
                        "soft_breaches": ", ".join(c["label"] for c in r["constraints"] if c["status"] == "breach" and c["kind"] == "soft")})
        return pd.DataFrame(out)
    return [Relation("proposals", "The Deal Desk proposal pipeline (one row per proposal)", load=proposals, grain="proposal",
                     columns={"amount_sar_mn": "the ask in SAR million", "case": "the test case the proposal represents"}),
            Relation("proposal_checks", "Each proposal's ask computed by the engine: lifetime RAROC, the hurdle, limit breaches",
                     load=checks, grain="proposal", columns={"hard_breaches": "hard limits breached at the ask, comma-separated",
                                                             "soft_breaches": "soft limits breached at the ask"})]


# ------------------------------------------------------------------ the deterministic planner

def read_number(pattern: str, q: str) -> float | None:
    m = re.search(pattern, q, re.I)
    return float(m.group(1).replace(",", "")) if m else None


def parse_terms(q: str) -> dict[str, Any]:
    """Plain-language terms: 'SAIBOR + 250', '30% cash margin', 'tenor 4 years', '80m', 'no real-estate collateral'."""
    out: dict[str, Any] = {}
    v = read_number(r"(?:saibor|sofr|margin)\s*(?:\+|of|at|to|is|=)?\s*(\d+)\s*(?:bps|bp)?", q)
    if v is not None:
        out["margin_bps"] = int(v)
    v = read_number(r"(\d+(?:\.\d+)?)\s*%\s*cash", q) or read_number(r"cash margin\s*(?:of|at|to)?\s*(\d+(?:\.\d+)?)", q)
    if v is not None:
        out["cash_margin_pct"] = v
    v = read_number(r"(\d+)\s*[- ]?(?:years?|yrs?)\b", q)
    if v is not None and re.search(r"tenor|year", q, re.I):
        out["tenor_years"] = int(v)
    v = read_number(r"(?:amount|keep (?:it|the amount) at|at|to)\s*(?:sar|usd)?\s*(\d[\d,]*(?:\.\d+)?)\s*(?:m|mn|million)\b", q) \
        or read_number(r"\b(\d[\d,]*(?:\.\d+)?)\s*(?:m|mn|million)\b", q)
    if v is not None:
        out["amount"] = v
    v = read_number(r"(?:upfront|arrangement) fee\s*(?:of|at|to)?\s*(\d+)", q)
    if v is not None:
        out["upfront_fee_bps"] = int(v)
    # R5 D4: the rest of the lever set
    v = read_number(r"(?:prepayment|early settlement) fee\s*(?:of|at|to)?\s*(\d+)", q) or read_number(r"(\d+)\s*(?:bps|bp)\s*(?:prepayment|early settlement)", q)
    if v is not None:
        out["prepayment_fee_bps"] = int(v)
    v = read_number(r"(?:hold|keep)\s*(?:only)?\s*(\d+(?:\.\d+)?)\s*%", q)
    if v is None:
        sd = read_number(r"sell(?:[- ]down|ing down)?\s*(\d+(?:\.\d+)?)\s*%", q) or read_number(r"(\d+(?:\.\d+)?)\s*%\s*sell[- ]?down", q)
        v = 100 - sd if sd is not None else None
    if v is not None:
        out["hold_pct"] = v
    if re.search(r"\bfixed[- ]rate\b|\bfixed pricing\b|\bat a fixed\b", q, re.I):
        out["rate_type"] = "fixed"
    v = read_number(r"(\d+(?:\.\d+)?)\s*%\s*(?:credit )?insurance", q) or read_number(r"(?:credit )?insurance (?:cover )?(?:of|at|to)?\s*(\d+(?:\.\d+)?)\s*%", q)
    if v is not None:
        out["insurance_cover_pct"] = v
    v = read_number(r"(?:assign(?:ment of|ed)?|assigning)\s*(?:the )?(?:contract proceeds|receivables)?\s*(?:of|at)?\s*(\d+(?:\.\d+)?)\s*%", q) \
        or read_number(r"(\d+(?:\.\d+)?)\s*%\s*(?:of )?(?:the )?(?:contract proceeds|receivables)\s*assigned", q)
    if v is not None:
        out["receivables_assignment_pct"] = v
    for pat, gid in ((r"\beca\b|export credit", "REQ-ECA"), (r"bank guarantee", "REQ-BANK"), (r"sovereign|ministry of finance", "REQ-SOVEREIGN"),
                     (r"parent (?:company )?guarantee", "REQ-PARENT")):
        if re.search(pat, q, re.I):
            out["guarantee_id"] = gid
            cv = read_number(r"(\d+(?:\.\d+)?)\s*%\s*(?:cover|guarantee|eca|bank|sovereign|parent)", q) or read_number(r"(?:cover|covering|coverage)\s*(?:of|on|at|for)?\s*(\d+(?:\.\d+)?)\s*%", q) \
                or read_number(r"\bon\s*(\d+(?:\.\d+)?)\s*%", q)
            out["guarantee_coverage_pct"] = cv if cv is not None else 50
            break
    items = [k for k, pat in (("leverage", r"leverage covenant"), ("dscr", r"dscr covenant"), ("cash_sweep", r"cash sweep"),
                              ("dividend_lockup", r"dividend lock[- ]?up|dividend block"), ("negative_pledge", r"negative pledge")) if re.search(pat, q, re.I)]
    if items:
        out["covenant_items"] = items
    if re.search(r"semi[- ]annual review|six[- ]monthly review|6[- ]month(?:ly)? review", q, re.I):
        out["review_cycle_months"] = 6
    elif re.search(r"quarterly review", q, re.I):
        out["review_cycle_months"] = 3
    if re.search(r"sculpt", q, re.I):
        out["amortisation"] = "sculpted"
    lines = [k for k, pat in (("payroll", r"payroll"), ("cash_management", r"cash management|operating account"), ("fx", r"\bfx\b"),
                              ("trade", r"\btrade\b")) if re.search(pat, q, re.I)]
    if lines and re.search(r"cross[- ]sell|commit", q, re.I):
        out["cross_sell"] = lines
    return out


def intent_of(q: str, has_proposal: bool) -> str:
    r11_intent = r11.intent_of(q, has_proposal)  # PLAN_R11 U3: an R11 subject first; the R4-R10 phrasings fall through
    if r11_intent:
        return r11_intent
    low = q.lower()
    if re.search(r"\b(memo|upload|ingest|extract)\b", low):
        return "ingest"
    if re.search(r"\bdraft\b|risk opinion|conditions precedent|\bcovenants?\b.*(recommend|draft|propos)", low):
        return "draft"
    if re.search(r"\bcompare\b|side by side|versus|\bvs\.?\b", low):
        return "compare" if has_proposal else "portfolio"
    if re.search(r"alternative structure|other structures|what are (?:my|our|the) options|which levers?|what levers?|minimum change|"
                 r"single lever|lever alone|how (?:else )?can (?:we|i) (?:make|get) (?:it|this) (?:clear|work)", low):
        return "alternatives" if has_proposal else "portfolio"
    if re.search(r"optimi[sz]e|restructur|counter[- ]?offer|won'?t accept|will not accept|what do we need|keep the amount|keep it at|"
                 r"no real[- ]estate|without real[- ]estate|find (a|the) structure|"
                 # R10 C4: "what tenor and margin should we offer?" asks for the best structure
                 r"should we offer|can we offer|best (?:tenor|margin|rate|pricing|price|structure)|"
                 r"what (?:tenor|margin|pricing|price|rate)s?\b.*\b(?:offer|propose|quote|charge)", low):
        return "optimise" if has_proposal else "portfolio"
    if re.search(r"downgrad|\bnotch|\bstress|collateral value|saibor \+\s*200|utilisation shock|how does (this|it) hold", low):
        return "stress" if has_proposal else "portfolio"
    if re.search(r"\bcompare\b|side by side|versus|\bvs\.?\b", low):
        return "compare" if has_proposal else "portfolio"
    if re.search(r"breakeven|break-even", low):
        return "breakeven" if has_proposal else "portfolio"
    if re.search(r"headroom|portfolio|concentration|rwa budget|which proposals|pipeline|how many proposals|breach a hard", low) and \
            not re.search(r"\bwhat if\b", low):
        return "portfolio"
    if re.search(r"\bwhat if\b|\bif we\b|\btry\b|\bwith\b.*\b(margin|cash|tenor|amount|fee|hold|insurance|guarantee|covenant|review|sell)\b|"
                 r"\bsell[- ]?down\b|\bfixed rate\b", low) and has_proposal and parse_terms(q):
        return "whatif"
    if re.search(r"\bwhy\b|\bfail|\bbind|\bexplain|trade[- ]?off|constraint|limit|\brisks?\b|weakness|concern|red flag", low):
        return "explain" if has_proposal else "portfolio"
    return "summary" if has_proposal else "portfolio"


def planner(question: str, ctx: ToolContext) -> Plan:
    has = bool(ctx.scope.get("proposal_id"))
    intent = intent_of(question, has)
    steps: list[PlanStep] = []
    q = question
    if intent == "ingest":
        return Plan(steps=[], write=lambda r: {"markdown": "Use **New proposal → Upload a memo** on the Deal Desk page. The memo is read into the "
                                                           "proposal form with the source and a confidence for every field; confirm it and the "
                                                           "analysis opens.", "suggestions": ["Why does the ask fail?"]})
    if intent in r11.R11_INTENTS:
        return Plan(steps=r11.plan_steps(intent, q, ctx), write=lambda r: r11.WRITERS[intent](q, r, ctx))
    if intent == "portfolio":
        low = q.lower()
        dims = [d for d, pat in (("collateral_type", r"real[- ]estate|collateral"), ("sector", r"sector|concentration"),
                                 ("rating_bucket", r"rating"), ("group", r"group")) if re.search(pat, low)] or ["sector"]
        steps = [PlanStep("headroom", {"dimension": d}) for d in dims[:2]]
        if re.search(r"breach|clear|fail", low):
            steps = [PlanStep("run_query", {"sql": "SELECT proposal_id, obligor_name, lifetime_raroc, clears_hurdle, hard_breaches, soft_breaches, approval, trace_id "
                                                   "FROM proposal_checks WHERE " + ("hard_breaches <> ''" if "hard" in low else
                                                   "soft_breaches <> ''" if "soft" in low else "NOT clears_hurdle OR hard_breaches <> ''")
                                                   + " ORDER BY proposal_id", "purpose": "proposals breaching"})]
        elif re.search(r"which proposals|pipeline|how many", low):
            steps.append(PlanStep("run_query", {"sql": "SELECT proposal_id, obligor_name, sector, rating, amount_sar_mn, status FROM proposals "
                                                       "ORDER BY amount_sar_mn DESC", "purpose": "the pipeline"}))
        return Plan(steps=steps, write=lambda r: write_portfolio(q, r))
    steps = [PlanStep("get_proposal", {}), PlanStep("compute_terms", {"terms_from": "ask"})]
    if intent == "optimise":
        fixed, bounds = constraints_from(q)
        steps.append(PlanStep("optimise", {"fixed": fixed, "bounds": bounds, "allow_soft": bool(re.search(r"escalat|soft", q, re.I))}))
    elif intent == "whatif":
        steps.append(PlanStep("compute_terms", {"changes": parse_terms(q)}))
        if ctx.state.get("terms"):
            steps.append(PlanStep("compute_terms", {"changes": {}}))
    elif intent == "stress":
        sc = "downgrade_2" if re.search(r"two|2", q) and re.search(r"notch|downgrad", q, re.I) else \
             "downgrade_1" if re.search(r"one|1", q) and re.search(r"notch|downgrad", q, re.I) else "all"
        steps.append(PlanStep("stress", {"scenario": "all"}))
        ctx.state["_scenario"] = sc
    elif intent == "compare":
        steps.append(PlanStep("optimise", {}))
    elif intent == "alternatives":
        fixed, bounds = constraints_from(q)
        steps.append(PlanStep("alternatives", {"fixed": fixed, "bounds": bounds, "allow_soft": bool(re.search(r"escalat|soft", q, re.I))}))
    elif intent == "breakeven":
        steps.append(PlanStep("breakeven", {"lever": "margin_bps"}))
    elif intent == "draft":
        steps.append(PlanStep("compute_terms", {"changes": {}}))
        steps.append(PlanStep("stress", {"scenario": "all"}))
    elif intent == "explain":
        steps.append(PlanStep("breakeven", {"lever": "margin_bps"}))
        if re.search(r"\bfail|not approv|declin|what is wrong|why not\b", q, re.I):
            steps.append(PlanStep("why_fails", {}))  # R14 E (K24): reads all findings, capacity and covenants
        low = q.lower().replace("-", " ")
        for name, lab in CONSTRAINT_LABEL.items():
            if name not in ("hurdle", "margin_bps") and (name.replace("_", " ") in low or lab.lower() in low):
                steps.append(PlanStep("explain_constraint", {"name": name}))
                break
    return Plan(steps=steps, write=lambda r: WRITERS[intent](q, r, ctx))


def constraints_from(q: str) -> tuple[dict, dict]:
    fixed: dict[str, Any] = {}
    bounds: dict[str, Any] = {}
    low = q.lower()
    m = re.search(r"(?:above|over|more than|max(?:imum)?|beyond)\s*(?:saibor|sofr)?\s*\+?\s*(\d+)", low)
    if m:
        bounds["margin_bps"] = [0, int(m.group(1))]
    m = re.search(r"keep (?:the amount|it|amount) at\s*(?:sar|usd)?\s*(\d[\d,]*(?:\.\d+)?)", low)
    if m:
        fixed["amount"] = float(m.group(1).replace(",", ""))
    m = re.search(r"keep (?:the )?tenor at\s*(\d+)", low)
    if m:
        fixed["tenor_years"] = int(m.group(1))
    if re.search(r"no real[- ]estate|without real[- ]estate", low):
        bounds["exclude_collateral_types"] = ["real_estate"]
    if re.search(r"no cash margin|without cash margin", low):
        fixed["cash_margin_pct"] = 0
    return fixed, bounds


def _out(results: list[dict], tool: str, n: int = 0) -> dict:
    hits = [r["out"] for r in results if r["tool"] == tool and not r["error"]]
    if len(hits) <= n:
        err = next((r["out"].get("error") for r in results if r["tool"] == tool and r["error"]), None)
        raise LookupError(err or f"{tool} returned nothing")
    return hits[n].get("data") or hits[n]


def _ask_lines(p: dict, a: dict) -> list[str]:
    ob, ask, m = p["obligor"], p["ask"], a["metrics"]
    hard = [c for c in a["constraints"] if c["status"] == "breach" and c["kind"] == "hard"]
    soft = [c for c in a["constraints"] if c["status"] == "breach" and c["kind"] == "soft"]
    lines = [f"**The ask:** {amt(ask['amount'], ask['currency'])} over {ask['tenor_years']} years at "
             f"{'SOFR' if ask['currency'] == 'USD' else 'SAIBOR'} + {ask['margin_bps']} bps for {ob['name']} ({ob['internal_rating']})."]
    verdict = "clears" if m["clears_hurdle"] else "does not clear"
    lines.append(f"**Hurdle:** lifetime RAROC {pct(m['lifetime_raroc'])} {verdict} the {pct(m['hurdle'])} hurdle; SVA {sar(m['sva'])}.")
    if hard:
        lines.append("**Appetite:** hard limits breached: " + "; ".join(f"{c['label']} {cval(c)} against {cval(c, c['limit'])}" for c in hard) + ".")
    elif soft:
        lines.append("**Appetite:** hard limits pass; soft breaches for escalation: " + "; ".join(f"{c['label']} {cval(c)} against {cval(c, c['limit'])}" for c in soft) + ".")
    else:
        lines.append("**Appetite:** every limit passes.")
    return lines


def write_optimise(q: str, r: list[dict], ctx: ToolContext) -> dict:
    p, a, o = _out(r, "get_proposal"), _out(r, "compute_terms"), _out(r, "optimise")
    ccy = p["ask"]["currency"]
    lines = _ask_lines(p, a)
    if not o["feasible"]:
        rel = o.get("relaxation") or []
        lines.append("**No structure clears** inside the market bounds and hard limits. The minimum relaxation, lever by lever:")
        for x in rel:
            lines.append(f"- {CONSTRAINT_LABEL.get(x['lever'], x['lever'].replace('_', ' '))}: {relax_value(x, x['from'])} → "
                         f"{relax_value(x, x['to'])}{' (beyond the market range)' if x.get('beyond_market') else ''}")
        lines.append("This is the decline rationale unless a limit owner relaxes one of these.")
        single = _single_lines(o, ccy)
        if single:
            lines.append("**Levers that clear alone:**")
            lines += single
        return {"markdown": "\n".join(lines), "suggestions": ["Draft the credit risk opinion", "How much sector headroom is left?"]}
    c, best = o["closest"], o["max_sva"]
    ch = [change_text(x, ccy) for x in c["changes"]]
    if not ch:
        lines.append(f"**Recommended:** the ask as it stands; it clears at {pct(c['metrics']['lifetime_raroc'])}.")
    else:
        lines.append(f"**Recommended (closest to the ask):** {'; '.join(ch)}. Lifetime RAROC {pct(c['metrics']['lifetime_raroc'])}, SVA {sar(c['metrics']['sva'])}.")
    binding = o.get("binding") or []
    if binding:
        # the shadow prices are on the screen and in the report; the commentary names what binds
        lines.append("**What binds:** " + "; ".join(dict.fromkeys(CONSTRAINT_LABEL.get(b["constraint"], b["constraint"]) for b in binding)) + ".")
    nxt = (o.get("counter_offers") or [None])[0] or best
    if nxt:
        lines.append(f"**Trade-off:** the next alternative, {nxt['label'].lower()}, gives RAROC {pct(nxt['metrics']['lifetime_raroc'])} and SVA "
                     f"{sar(nxt['metrics']['sva'])} with {'; '.join(change_text(x, ccy) for x in nxt['changes']) or 'no change'}.")
    if o.get("alternatives"):
        lines.append("**Other structures that clear, mixing levers:**")
        lines += _alt_lines(o, ccy, 3)
    lines.append(f"**Approval:** {c['approval']['level']}.")
    return {"markdown": "\n".join(lines), "suggestions": ["Compare the counter-offers", "How does this hold if they're downgraded two notches?",
                                                         "Draft the credit risk opinion"]}


def _alt_lines(al: dict, ccy: str, n: int = 4) -> list[str]:
    lines = []
    for a in al.get("alternatives", [])[:n]:
        why = ", ".join(f"{FIELD_LABEL.get(c['lever'], c['label'].lower())} {F.pct(c['raroc_pts'], signed=True)}" for c in a["contributions"][:3])
        lines.append(f"- **{a['label']}:** {'; '.join(change_text(c, ccy) for c in a['changes'])}. RAROC {pct(a['metrics']['lifetime_raroc'])}, "
                     f"SVA {sar(a['metrics']['sva'])}, approval {a['approval']['level']}. Why it works: {why}.")
    return lines


def _single_lines(al: dict, ccy: str, n: int = 6) -> list[str]:
    hits = [x for x in al.get("single_lever", []) if x.get("clears_alone")][:n]
    return [f"- {x['label']}: {lever_value(x['lever'], x['from'], ccy)} → {lever_value(x['lever'], x['to'], ccy)}"
            f"{' (' + x['note'] + ')' if x.get('note') else ''}, RAROC {pct(x['lifetime_raroc'])}" for x in hits]


def write_alternatives(q: str, r: list[dict], ctx: ToolContext) -> dict:
    p, a, al = _out(r, "get_proposal"), _out(r, "compute_terms"), _out(r, "alternatives")
    ccy = p["ask"]["currency"]
    lines = _ask_lines(p, a)
    if al.get("base_clears"):
        lines.append("The structure already clears the hurdle and every limit: no lever needs to move.")
        return {"markdown": "\n".join(lines), "suggestions": ["How does this hold if they're downgraded two notches?", "Draft the credit risk opinion"]}
    if al.get("alternatives"):
        lines.append(f"**{len(al['alternatives'])} structures clear the hurdle:**")
        lines += _alt_lines(al, ccy)
    else:
        lines.append("**No mixed structure clears** inside the lever bounds; the optimiser's minimum relaxation is the decline rationale.")
    single = _single_lines(al, ccy)
    if single:
        lines.append("**Minimum change on one lever alone:**")
        lines += single
    alone = [x["label"].lower() for x in al.get("single_lever", []) if not x.get("clears_alone")]
    if alone:
        lines.append(f"Cannot clear alone: {', '.join(alone[:6])}.")
    return {"markdown": "\n".join(lines), "suggestions": ["Optimise", "Compare the counter-offers", "Draft the credit risk opinion"]}


def write_whatif(q: str, r: list[dict], ctx: ToolContext) -> dict:
    p, ask = _out(r, "get_proposal"), _out(r, "compute_terms", 0)
    new = _out(r, "compute_terms", 1)
    m, m0 = new["metrics"], ask["metrics"]
    changes = parse_terms(q)
    desc = ", ".join(lever_value(k, v) if k == "guarantee_id" else f"{FIELD_LABEL.get(k, k)} {lever_value(k, v, p['ask']['currency'])}"
                     for k, v in changes.items())
    lines = [f"**With {desc}:** lifetime RAROC {pct(m['lifetime_raroc'])} (ask {pct(m0['lifetime_raroc'])}), SVA {sar(m['sva'])} (ask {sar(m0['sva'])}), "
             f"RWA {sar(m['rwa_y1'])}, EL {sar(m['el_lifetime_pv'])} in present value.",
             f"It {'clears' if m['clears_hurdle'] else 'does not clear'} the {pct(m['hurdle'])} hurdle; approval {new['approval']['level']}."]
    br = [c for c in new["constraints"] if c["status"] == "breach"]
    if br:
        lines.append("Breaches: " + "; ".join(f"{c['label']} ({c['kind']}) {cval(c)} against {cval(c, c['limit'])}" for c in br) + ".")
    return {"markdown": "\n".join(lines), "suggestions": ["Optimise", "How does this hold if they're downgraded two notches?"]}


def write_stress(q: str, r: list[dict], ctx: ToolContext) -> dict:
    p, s = _out(r, "get_proposal"), _out(r, "stress")
    sc = ctx.state.get("_scenario", "all")
    rows = [x for x in s["rows"] if sc == "all" or x["scenario"] == sc] or s["rows"]
    lines = [f"Base: lifetime RAROC {pct(s['base']['lifetime_raroc'])}, SVA {sar(s['base']['sva'])} on the {'recommended' if ctx.state.get('terms') else 'asked'} terms."]
    for x in rows:
        lines.append(f"- **{x['label']}:** RAROC {pct(x['lifetime_raroc'])}, SVA {sar(x['sva'])}"
                     f"{', client DSCR ' + F.times(x['dscr_post']) if x.get('dscr_post') else ''} — "
                     f"{'still clears' if x['clears_hurdle'] else 'falls below'} the hurdle.")
    lines.append(f"**Robustness:** {s['robustness_notches']} notches of downgrade before RAROC falls below the hurdle.")
    return {"markdown": "\n".join(lines), "suggestions": ["Optimise", "Draft the credit risk opinion"]}


def write_compare(q: str, r: list[dict], ctx: ToolContext) -> dict:
    p, a, o = _out(r, "get_proposal"), _out(r, "compute_terms"), _out(r, "optimise")
    if not o["feasible"]:
        return write_optimise(q, r, ctx)
    ccy = p["ask"]["currency"]
    opts = [o["closest"], o["max_sva"], *(o.get("counter_offers") or [])][:4]
    lines = [f"| Structure | RAROC | SVA | Approval | Changes |", "|---|---|---|---|---|",
             f"| Ask | {pct(a['metrics']['lifetime_raroc'])} | {sar(a['metrics']['sva'])} | {a['approval']['level']} | — |"]
    for x in opts:
        lines.append(f"| {x['label']} | {pct(x['metrics']['lifetime_raroc'])} | {sar(x['metrics']['sva'])} | {x['approval']['level']} | "
                     f"{'; '.join(change_text(c, ccy) for c in x['changes']) or 'none'} |")
    return {"markdown": "\n".join(lines), "suggestions": ["Draft the credit risk opinion", "How does this hold if they're downgraded two notches?"]}


def write_breakeven(q: str, r: list[dict], ctx: ToolContext) -> dict:
    p, b = _out(r, "get_proposal"), _out(r, "breakeven")
    ask = p["ask"]
    if b.get("value") is None:
        return {"markdown": "No margin brings lifetime RAROC to the hurdle with the other terms as they are.", "suggestions": ["Optimise"]}
    return {"markdown": f"The breakeven margin is **{F.bps(b['value'])}**: at that margin lifetime RAROC equals the hurdle with the other terms held. "
                        f"The ask is {F.bps(ask['margin_bps'])}.", "suggestions": ["Optimise", "Why does the ask fail?"]}


def _why_fails_lines(r: list[dict]) -> list[str] | None:
    """R14 E (K24): the findings engine's answer, when the plan read it."""
    try:
        w = _out(r, "why_fails")
    except LookupError:
        return None
    out = [f"**{w['headline']}**"]
    for x in w["lines"]:
        tag = {"critical": "Critical", "major": "Major"}.get(x["severity"])
        out.append(f"- {('**' + tag + ':** ') if tag else ''}{x['text']}" + (f" Cure: {x['cure']}" if x.get("cure") else ""))
    out.append(f"{w['counts']['line']} (findings engine: review rules, dd_review_finding, capacity, covenants).")
    return out


def write_explain(q: str, r: list[dict], ctx: ToolContext) -> dict:
    p, a = _out(r, "get_proposal"), _out(r, "compute_terms")
    wf = _why_fails_lines(r)
    if wf:
        lines = wf
        try:
            b = _out(r, "breakeven")
            if b.get("value") is not None:
                lines.append(f"**Breakeven margin:** {F.bps(b['value'])} against the asked {F.bps(p['ask']['margin_bps'])}.")
        except LookupError:
            pass
        return {"markdown": "\n".join(lines), "suggestions": ["Show the counter-offer", "Optimise", "Compare the counter-offers"]}
    lines = _ask_lines(p, a)
    w = {x["step"]: x["value"] for x in a["waterfall"]}
    if w:
        lines.append(f"**Why:** in present value, profit income {sar(w.get('Profit income'))} and fees {sar(w.get('Fees'))} against FTP "
                     f"{sar(abs(w.get('FTP', 0)))}, opex {sar(abs(w.get('Opex', 0)))} and expected loss {sar(abs(w.get('Expected loss', 0)))} leave "
                     f"risk-adjusted profit of {sar(w.get('Risk-adjusted profit'))} on capital of {sar(a['metrics']['capital_y1'])} in year one.")
    try:
        b = _out(r, "breakeven")
        if b.get("value") is not None:
            lines.append(f"**Breakeven margin:** {F.bps(b['value'])} against the asked {F.bps(p['ask']['margin_bps'])}.")
    except LookupError:
        pass
    for res in r:
        if res["tool"] == "explain_constraint" and not res["error"]:
            e = res["out"]["data"]
            deal = e.get("deal") or {}
            extra = f" For this deal: {cval(deal)} against {cval(deal, deal['limit'])} ({deal['kind']}, {deal['status']})." if deal else ""
            lines.append(f"**{CONSTRAINT_LABEL.get(e['name'], e['name'])}:** {e.get('definition', '')}{extra}")
    lines.append(f"**Approval:** {a['approval']['level']}.")
    return {"markdown": "\n".join(lines), "suggestions": ["Optimise", "What if we take 30% cash margin?", "Compare the counter-offers"]}


def write_summary(q: str, r: list[dict], ctx: ToolContext) -> dict:
    out = write_explain(q, r, ctx)
    return out


def write_draft(q: str, r: list[dict], ctx: ToolContext) -> dict:
    p, ask, rec, s = _out(r, "get_proposal"), _out(r, "compute_terms", 0), _out(r, "compute_terms", 1), _out(r, "stress")
    ob, t, m = p["obligor"], rec["terms"], rec["metrics"]
    ccy = t["currency"]
    changed = ctx.state.get("terms") is not None
    soft = [c for c in rec["constraints"] if c["status"] == "breach" and c["kind"] == "soft"]
    hard = [c for c in rec["constraints"] if c["status"] == "breach" and c["kind"] == "hard"]
    supports = bool(m["clears_hurdle"]) and not hard
    stance = "Risk supports" if supports else "Risk does not support"
    para = (f"{stance} the facility for {ob['name']} ({ob['internal_rating']}) "
            f"{'on the restructured terms' if changed else 'as asked'}: {amt(t['amount'], ccy)} over {t['tenor_years']} years at "
            f"{'SOFR' if ccy == 'USD' else 'SAIBOR'} + {F.bps(t['margin_bps'])}, upfront fee {F.bps(t['upfront_fee_bps'])}"
            f"{', cash margin ' + lever_value('cash_margin_pct', t['cash_margin_pct']) if t.get('cash_margin_pct') else ''}"
            f"{', held at ' + lever_value('hold_pct', t['hold_pct']) + ' after sell-down' if t.get('hold_pct', 100) < 100 else ''}"
            f"{', ' + GUARANTEE_NAME.get(t['guarantee_id'], 'a guarantee') + ' on ' + lever_value('guarantee_coverage_pct', t['guarantee_coverage_pct']) if t.get('guarantee_id') else ''}"
            f"{', credit insurance on ' + lever_value('insurance_cover_pct', t['insurance_cover_pct']) if t.get('insurance_cover_pct') else ''}. "
            f"Lifetime RAROC is {pct(m['lifetime_raroc'])} against the {pct(m['hurdle'])} hurdle (ask {pct(ask['metrics']['lifetime_raroc'])}), "
            f"SVA {sar(m['sva'])}, year-one RWA {sar(m['rwa_y1'])} and day-one ECL {sar(m['day_one_ecl'])}. "
            f"The structure holds for {s['robustness_notches']} notches of downgrade. "
            + ("Hard limits breached: " + "; ".join(f"{c['label']} at {cval(c)} against {cval(c, c['limit'])}" for c in hard) + ". " if hard else "")
            + ("Soft limits requiring escalation: " + "; ".join(f"{c['label']} at {cval(c)} against {cval(c, c['limit'])}" for c in soft) + ". " if soft else
               "Every risk-appetite limit is met. " if not hard else "")
            + ("" if supports else "A restructured structure from the optimiser (alternatives that clear the hurdle and the limits) is "
                                   "required before approval. ")
            + f"Approval authority: {rec['approval']['level']}.")
    cps = ["Executed facility agreement and security documents in the agreed form.",
           "Board resolution of the obligor approving the facility and the security.",
           "Valuation of pledged collateral by a bank-approved valuer, not older than 12 months." if t.get("collateral_ids") else
           "Confirmation that no security is required under the approved structure.",
           "Guarantee executed by the guarantor." if t.get("guarantee_id") else "Clean SIMAH report on the obligor and its connected parties.",
           f"Cash margin of {lever_value('cash_margin_pct', t['cash_margin_pct'])} placed with the bank before first drawdown." if t.get("cash_margin_pct") else
           "Evidence of the purpose of the facility."]
    review = {12: "annually", 6: "semi-annually", 3: "quarterly"}.get(int(t.get("review_cycle_months", 12)), "annually")
    cov = [f"Minimum DSCR of {F.times(c['limit'])}, tested {review}." for c in rec["constraints"] if c["name"] == "dscr"] + \
          [f"Maximum Debt/EBITDA of {F.times(c['limit'])}, tested {review}." for c in rec["constraints"] if c["name"] == "debt_ebitda"] + \
          [{"cash_sweep": "Cash sweep of excess cash flow to prepayment.", "dividend_lockup": "Dividend lock-up while a covenant is in breach.",
            "negative_pledge": "Negative pledge and pari passu undertaking.", "leverage": "Leverage covenant with an early-warning trigger.",
            "dscr": "DSCR covenant with an early-warning trigger."}.get(x, x) for x in t.get("covenant_items") or []] + \
          [f"Covenant package: {t.get('covenant_package', 'standard')}.", "Annual audited financial statements within 120 days of year end."]
    md = (f"### Credit risk opinion\n{para}\n\n### Conditions precedent\n" + "\n".join(f"- {x}" for x in cps)
          + "\n\n### Covenants\n" + "\n".join(f"- {x}" for x in cov))
    return {"markdown": md, "suggestions": ["How does this hold if they're downgraded two notches?", "Compare the counter-offers"]}


def write_portfolio(q: str, r: list[dict]) -> dict:
    lines = []
    for res in r:
        if res["tool"] == "headroom" and not res["error"]:
            d = res["out"]["data"]
            dim = d.get("dimension", "")
            low = q.lower().replace("-", " ")
            rows = d.get("rows") or []
            focus = [x for x in rows if x["key"].replace("_", " ").lower() in low] or rows
            lines.append(f"**Headroom by {dim.replace('_', ' ')}:**")
            for x in focus[:8]:
                lim = x.get("limit")
                head = x.get("headroom_sar_mn", x.get("headroom"))
                tail = (f" against a cap of {pct(lim)}; headroom {sar(head)}." if lim is not None and lim <= 1 and head is not None else
                        f" against a limit of {sar(lim)}; headroom {sar(head)}." if lim is not None and head is not None else "; no cap set.")
                lines.append(f"- {str(x['key']).replace('_', ' ').capitalize()}: exposure {sar(x['ead'])} ({pct(x['share'])} of the book){tail}")
        if res["tool"] == "run_query" and not res["error"]:
            rows = (res.get("artifact") or {}).get("rows") or res["out"].get("rows") or []
            if rows and "hard_breaches" in rows[0]:
                lines.append(f"**{len(rows)} proposals** {'breach a hard limit' if 'hard' in q.lower() else 'need attention'} at the ask:")
                for x in rows:
                    why = x["hard_breaches"] or x["soft_breaches"] or "below the hurdle"
                    lines.append(f"- {x['proposal_id']} {x['obligor_name']}: {why}; lifetime RAROC {pct(x['lifetime_raroc'])}.")
            else:
                lines.append(f"The pipeline holds {len(rows)} proposals; open one to see its limits after the deal.")
    charts = [{"artifact_id": res["out"]["artifact_id"], "kind": "hbar", "x": "key", "y": ["ead"],
               "title": f"Exposure by {res['out']['data'].get('dimension', '').replace('_', ' ')}, SAR million"}
              for res in r if res["tool"] == "headroom" and not res["error"] and res["out"].get("artifact_id") and (res["out"]["data"].get("rows") or [])]
    return {"markdown": "\n".join(lines) or "Ask about headroom by sector, collateral type, rating bucket or group.",
            "tables": [{"artifact_id": res["out"]["artifact_id"]} for res in r if res["tool"] == "run_query" and not res["error"]][:1],
            "charts": charts[:1],
            "suggestions": ["How much sector headroom is left?", "Which proposals breach a hard limit?"]}


WRITERS = {"alternatives": write_alternatives, "optimise": write_optimise, "whatif": write_whatif, "stress": write_stress, "compare": write_compare,
           "breakeven": write_breakeven, "explain": write_explain, "summary": write_summary, "draft": write_draft}

DOMAIN = Domain(
    key="dealdesk", title="Deal Desk", charter=CHARTER, relations=relations, tools=TOOLS, knowledge=KNOWLEDGE, planner=planner,
    scope_label=lambda s: f"proposal {s['proposal_id']}" if s.get("proposal_id") else "the Deal Desk pipeline and portfolio headroom",
    scope_key=lambda s: "pipeline",
    suggestions=lambda s, st: [{"label": "Why does the ask fail?", "send": "Why does the ask fail?"}, {"label": "Optimise", "send": "Optimise"}],
    state_brief=lambda st: (f"The thread's working terms: {st['terms']}" if st.get("terms") else "The thread is on the asked terms."),
    max_steps=8,
)


from backend.dealdesk_thread import round_e  # noqa: E402,F401  Round E: engine first for known questions, worked examples


# ------------------------------------------------------------------ the turn (inline, on the thread store)

class _Emitter:
    open_stage = ""

    def emit(self, *a: Any, **k: Any) -> None:
        pass

    def stage(self, name: str, message: str = "") -> None:
        self.open_stage = name


def describe() -> dict[str, Any]:
    return prov.describe()


# ------------------------------------------------------------------ PLAN_R6 D2: ask for what is missing

SECURITY_WORDS = re.compile(r"collateral|security|secured|guarant|kafalah|covenant|dscr|leverage|cash margin|pledge|mortgage|"
                            r"assignment|unsecured|no security|none offered|nothing offered", re.I)


def security_missing(p: dict) -> list[str]:
    """What the proposal does not state: collateral, guarantee, covenants."""
    sec = p.get("security") or {}
    out = []
    if not sec.get("collateral"):
        out.append("collateral")
    if not sec.get("guarantees"):
        out.append("guarantee")
    if not sec.get("covenants"):
        out.append("covenants")
    return out


def security_lines(p: dict) -> str:
    """Collateral and covenants, always shown in the analysis (PLAN_R6 D2)."""
    sec = p.get("security") or {}
    ccy = (p.get("ask") or {}).get("currency", "SAR")
    coll = "; ".join(f"{str(c.get('type', '')).replace('_', ' ')} {sar(c.get('value'))}" for c in sec.get("collateral") or []) or "none offered"
    guar = "; ".join(f"{g.get('type', '')} guarantee{(' from ' + g['guarantor']) if g.get('guarantor') else ''}, {g.get('coverage_pct', 0):g}% cover"
                     for g in sec.get("guarantees") or []) or "none offered"
    def _cov(c: dict) -> str:
        t = str(c.get("type", "")).replace("_", " ")
        th = c.get("threshold")
        side = "at least" if re.search(r"dscr|cover", t, re.I) else "at most"
        return f"{t} {side} {th:g}x" if isinstance(th, (int, float)) else t
    cov = "; ".join(_cov(c) for c in sec.get("covenants") or [])
    cov = cov or f"none stated (package: {sec.get('covenant_package', 'none')})"
    assumed = p.get("assumed") or []
    out = f"**Security.** Collateral: {coll}. Guarantee: {guar}. **Covenants:** {cov}."
    if assumed:
        out += " **Assumed:** " + "; ".join(assumed) + "."
    del ccy
    return out


def security_question(p: dict, missing: list[str]) -> dict[str, Any]:
    ask = p.get("ask") or {}
    what = {"collateral": "Is any collateral offered (type and value)?", "guarantee": "Is there a guarantee (type and guarantor)?",
            "covenants": "What covenants are proposed (DSCR minimum, Debt/EBITDA maximum)?"}
    md = (f"Before I optimise {p['obligor']['name']}'s {amt(ask.get('amount', 0), ask.get('currency', 'SAR'))} request, the proposal does not state its "
          f"{', '.join(missing)}. Security and covenants move LGD, capital and the approval level, so they change the answer.\n\n"
          + "\n".join(f"- {what[m]}" for m in missing)
          + "\n\nReply with the terms (for example \"real estate collateral SAR 60m, DSCR covenant 1.3x\"), or say **no security offered** "
            "and I will optimise on that basis.")
    sugg = ["No security offered: optimise as it stands", "Real estate collateral worth 60% of the amount, DSCR covenant 1.3x",
            "Corporate guarantee from the parent, 100% cover"]
    return {"intent": "clarify", "blocks": [{"type": "text", "markdown": md}],
            "suggestions": [{"label": x[:60], "send": x} for x in sugg], "trace_ids": [],
            "validation": {"checked": 0, "untraced": [], "passed": True}, "source": "deterministic", "tools": ["get_proposal"]}


def answer(store: Any, proposal: dict | None, question: str, user: dict, history: list[dict] | None = None) -> dict[str, Any]:
    pid = proposal["proposal_id"] if proposal else None
    state = dict(store.state(pid)) if pid else {}
    if proposal and intent_of(question, True) in ("optimise", "alternatives", "compare") \
            and not state.get("security_asked") and not SECURITY_WORDS.search(question):
        missing = security_missing(proposal)
        if len(missing) == 3:  # PLAN_R6 D2: no collateral, guarantee or covenant data at all
            st = store.state(pid)
            st["security_asked"] = True
            store.set_state(pid, st)
            return security_question(proposal, missing)
    thread = {"thread_id": pid or "desk", "title": pid or "Deal Desk", "domain": "dealdesk", "scope": {"proposal_id": pid}, "state": state}
    hist = [{"question": t["question"], "answer": {"blocks": t["answer"].get("blocks") or []}} for t in (history or [])]
    agent = Agent(DOMAIN, thread=thread, scope={"proposal_id": pid} if pid else {}, state=state, question=question,
                  emitter=_Emitter(), user=user, history=hist)
    out = agent.run()
    intent = intent_of(question, bool(pid))
    traces = []
    for a in agent.artifacts.values():
        d = a.get("data") or {}
        if isinstance(d, dict) and d.get("trace_id"):
            traces.append(d["trace_id"])
        traces.extend(str(r["trace_id"]) for r in (a.get("rows") or []) if isinstance(r, dict) and r.get("trace_id"))
    md = next((b.get("markdown", "") for b in out.blocks if b.get("type") == "answer"), "")
    checked = len(numbers(md))
    removed = out.validation.get("removed") or []
    blocks = []
    for b in out.blocks:
        if b.get("type") == "answer":
            # D7: every number in the commentary through G5 (long decimals from a model's prose rounded)
            blocks.append({"type": "draft" if intent in ("draft", "committee_sheet") else "text", "markdown": F.tidy(b.get("markdown", ""))})
        elif b.get("type") == "table":
            # D2/D7: plain-words headers with units, every cell through the G5 formatter (no raw keys, no raw decimals)
            cols = [c for c in b["columns"] if c["key"] != "trace_id"]
            blocks.append({"type": "table", "title": b.get("title", ""),
                           "header": [F.header(c["key"]) if (c.get("label") or c["key"]).replace(" ", "_").lower() == c["key"].lower() else c["label"]
                                      for c in cols],
                           # R6 E2: the keys too, so the renderer can format any cell that still arrives raw
                           "keys": [c["key"] for c in cols],
                           "rows": [[F.auto(r.get(c["key"]), c["key"]) for c in cols] for r in ratings.order_table(cols, b["rows"])]})
        elif b.get("type") == "chart":
            blocks.append({"type": "chart", "title": b.get("title", ""), "kind": b.get("kind") or "bar", "x": b["x"], "y": b.get("y") or [],
                           "labels": {k: F.header(k) for k in (b.get("labels") or {})} or {},
                           "rows": [{k: (round(v, 2) if isinstance(v, float) else v) for k, v in r.items()} for r in ratings.order_chart_rows(b["x"], (b.get("rows") or [])[:12])]})
    if proposal and intent not in ("portfolio", "ingest", "draft", *r11.R11_INTENTS):
        blocks.append({"type": "text", "markdown": security_lines(proposal)})
    from backend.dealdesk import chips as _chips  # R12 G (I9): follow-up chips in banker language only
    res: dict[str, Any] = {"intent": intent, "blocks": blocks, "suggestions": _chips.clean(out.suggestions, intent, bool(pid)), "trace_ids": traces,
                           "validation": {"checked": checked, "untraced": removed, "passed": not removed}, "source": out.source,
                           "tools": [t.get("tool") for t in agent.trace if t.get("tool")]}
    if pid and intent in r11.ACTION:
        res["action"] = r11.ACTION[intent]
    if pid and out.state:
        upd = {k: v for k, v in out.state.items() if not k.startswith("_")}
        if upd.get("optimisation"):
            res["action"] = "optimise"
            res["optimise_request"] = {k: upd.get("optimise_request", {}).get(k) for k in ("fixed", "bounds", "allow_soft")}
            st = store.state(pid)
            st["optimisation"] = upd["optimisation"]
            store.set_state(pid, st)
    return res


def _opt_summary(o: dict) -> dict:
    """What Recent analyses shows for an optimisation: the outcome and the closest structure's RAROC and approval."""
    c = o.get("closest") or {}
    return {"feasible": bool(o.get("feasible")), "lifetime_raroc": (c.get("metrics") or {}).get("lifetime_raroc"),
            "sva": (c.get("metrics") or {}).get("sva"), "approval": (c.get("approval") or {}).get("level"),
            "alternatives": len(o.get("alternatives") or []), "trace_id": o.get("trace_id")}


def optimise_turn(store: Any, proposal: dict, settings: dict, user: dict) -> tuple[dict, dict]:
    """The Optimise button: one optimiser call, and the commentary on it as a thread turn (the same writer and the
    same figure check as a chat turn). Returns (the engine's optimisation, the answer)."""
    from backend.convo.validate import Evidence, strip_unverified
    from backend.convo import trace as _trace
    pid = proposal["proposal_id"]
    _trace.step("planning", "Reading the optimiser settings")
    rec = engine.Recorder()
    p = rec.get(f"/proposals/{pid}")["proposal"]
    _trace.step("querying", "Running the optimiser over the full lever set")
    ask = rec.post("/compute", {"proposal_id": pid})
    req = {"proposal_id": pid, "objective": "both", "fixed": settings.get("fixed") or {}, "bounds": settings.get("bounds") or {},
           "allow_soft": bool(settings.get("allow_soft"))}
    if settings.get("weights"):
        req["weights"] = settings["weights"]
    opt = rec.post("/optimize", req)
    results = [{"tool": "get_proposal", "out": {"data": {"obligor": p["obligor"], "ask": p["ask"]}}, "error": False},
               {"tool": "compute_terms", "out": {"data": ask}, "error": False},
               {"tool": "optimise", "out": {"data": opt}, "error": False}]
    ctx = ToolContext(domain=DOMAIN, thread={}, state={}, scope={"proposal_id": pid}, user=user, question="Optimise", execute=False)
    _trace.step("answering", "Writing the commentary")
    out = write_optimise("Optimise", results, ctx)
    _trace.step("validating", "Checking every figure against the engine results")
    ev = Evidence()
    for c in rec.calls:
        ev.add(c["result"])
    md = out["markdown"]
    bad = ev.unverified(md)
    if bad:
        md = strip_unverified(md, bad)
    missing = security_missing(p)
    if len(missing) == 3:
        md = (f"No {', '.join(missing)} {'is' if len(missing) == 1 else 'are'} stated in the proposal, so this optimisation assumes none "
              "beyond the levers the optimiser may add. Is any security offered? What covenants are proposed?\n\n" + md)
    md += "\n\n" + security_lines(p)
    answer = {"intent": "optimise", "blocks": [{"type": "text", "markdown": md}],
              "suggestions": [{"label": x[:60], "send": x} for x in out.get("suggestions") or []],
              "trace_ids": rec.trace_ids, "validation": {"checked": len(numbers(md)), "untraced": bad, "passed": not bad},
              "source": "deterministic", "tools": ["get_proposal", "compute_terms", "optimise"], "action": "optimise",
              "optimise_request": {k: req.get(k) for k in ("fixed", "bounds", "allow_soft", "weights")},
              "summary": _opt_summary(opt)}
    st = store.state(pid)
    st["optimisation"] = {"trace_id": opt["trace_id"], "feasible": opt["feasible"]}
    st["optimise_request"] = answer["optimise_request"]
    store.set_state(pid, st)
    return opt, answer
