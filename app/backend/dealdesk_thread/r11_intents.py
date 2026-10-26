"""PLAN_R11 U3: the R11 thread intents of the Deal Desk conversation.

Each intent calls a new R11 engine API (prefix /api/v1/dealdesk, in-process through `engine`) and answers in the
thread's style: the answer first, in one line, then the evidence. Every figure is copied from a tool result of the
turn, so the shared validator can trace it.

  forward_risk      "what is the chance of Stage 2", "30+ next quarter"           POST /proposals/{id}/forward-risk (F)
  ews_deal          "run early warning on this deal"                              POST /proposals/{id}/forward-risk (F3)
  stress_lab        "stress this deal with oil −30%", "what breaks first", custom POST /proposals/{id}/stress (S)
  pipeline_test     "test against pipeline", "does this make the cut"             POST /proposals/{id}/pipeline-test (L)
  pipeline_optimise "optimise the pipeline"                                       POST /pipeline/optimise (L)
  review            "review the memo", "what's wrong with this proposal"          POST /proposals/{id}/review (R)
  committee_sheet   "draft the committee sheet"                                   POST /proposals/{id}/review (R6)

The existing intents (optimise, stress on the R4 scenarios, draft, ...) keep their phrasings: `intent_of` here is
consulted first and only claims a question that names an R11 subject.
"""
from __future__ import annotations

import re
from typing import Any

from backend.convo.spec import PlanStep, Tool, ToolContext, ToolResult
from backend.dealdesk import fmt as F
from backend.dealdesk_thread import engine

R11_INTENTS = ("forward_risk", "ews_deal", "stress_lab", "pipeline_test", "pipeline_optimise", "review", "committee_sheet")
NEEDS_PROPOSAL = {"forward_risk", "ews_deal", "stress_lab", "pipeline_test", "review", "committee_sheet"}

# ------------------------------------------------------------------ intents

_COMMITTEE = re.compile(r"committee (?:decision )?(?:sheet|paper|note|pack)|decision sheet|credit committee summary|"
                        r"(?:draft|prepare|write)\b.*\bfor (?:the )?(?:credit )?committee", re.I)
_REVIEW = re.compile(r"(?:review|check|audit|verify|scrutini[sz]e|challenge)\s+(?:the|this|our)\s+(?:credit\s+)?(?:memo|proposal|paper)|"
                     r"memo review|proposal review|"
                     r"what'?s wrong with (?:the|this) (?:memo|proposal|paper|deal)|"
                     r"(?:issues|problems|gaps|contradictions|inconsistenc\w+|red flags) (?:in|with) (?:the|this) (?:credit )?(?:memo|proposal|paper)|"
                     r"(?:memo|proposal) (?:findings|issues)|does the memo (?:hold up|stack up|tie)", re.I)
_PIPE_OPT = re.compile(r"optimi[sz]e (?:the |our )?(?:whole )?pipeline|pipeline optimi[sz]|"
                       r"(?:select|pick|choose) the best deals|best (?:set of )?deals (?:from|in) the pipeline|"
                       r"which (?:pending )?deals should we approve|best deals from (?:a|the) bunch", re.I)
_PIPE_TEST = re.compile(r"test (?:it |this(?: deal)? |the deal )?against (?:the )?pipeline|pipeline test|"
                        r"make the cut|makes the cut|(?:fit|fits|rank) (?:in|into|against) the pipeline|"
                        r"against (?:the |all )?(?:other )?pending deals|which deals (?:does|would) it displace|"
                        r"compete for (?:capital|rwa)", re.I)
_EWS = re.compile(r"early[- ]warning|\bews\b|warning signals?|warning (?:score|band)", re.I)
_FORWARD = re.compile(r"stage\s*(?:2|two)\b|\b30\s*\+|\b30\s*(?:\+\s*)?dpd|thirty days|days past due|past due next|"
                      r"forward risk|ecl (?:next quarter|in (?:a year|four quarters|4 quarters))|expected ecl|forward ecl|"
                      r"(?:chance|probability|likelihood|odds) (?:of|that) (?:it|this|the deal)?\s*(?:migrat|slip|go(?:es)? bad|default|turn)|"
                      r"stage migration|migrate to stage", re.I)
_STRESS_LAB = re.compile(r"stress (?:this |the )?(?:deal|structure|proposal|it) (?:with|for|under|by)|stress lab|"
                         r"\boil\b|(?:saibor|eibor|rates?|interest)\s*(?:\+|up|rise|rises|go up|shock|−|-)?\s*\d+\s*(?:bps|bp)|"
                         r"revenue\s*(?:falls?|drops?|down|declines?|−|-|by)\s*\d|revenue\s*[−-]\s*\d|"
                         r"what breaks first|breaks first|reverse stress|distance to failure|how far can|"
                         r"\bgdp\b|largest customer|project delay|margin squeeze|severe (?:case|scenario)|combined scenario|"
                         r"real estate prices|guarantee unenforceable|which scenarios", re.I)


def intent_of(q: str, has_proposal: bool) -> str | None:
    """The R11 intent of a question, or None to leave it to the R4-R10 intents."""
    if _COMMITTEE.search(q):
        return "committee_sheet" if has_proposal else "portfolio"
    if _REVIEW.search(q):
        return "review" if has_proposal else "portfolio"
    if _PIPE_OPT.search(q):
        return "pipeline_optimise"
    if _PIPE_TEST.search(q):
        return "pipeline_test" if has_proposal else "pipeline_optimise"
    if _EWS.search(q):
        return "ews_deal" if has_proposal else None
    if _FORWARD.search(q):
        return "forward_risk" if has_proposal else None
    if _STRESS_LAB.search(q):
        return "stress_lab" if has_proposal else None
    return None


# ------------------------------------------------------------------ custom shocks in plain language

def _num(m: re.Match | None) -> float | None:
    return float(m.group(1).replace(",", "")) if m else None


def parse_shocks(q: str) -> dict[str, float]:
    """'revenue −20% and rates +150 bps', 'oil -30%', 'collateral value down 40%', 'two notches'. Signs follow the words."""
    low = q.lower().replace("−", "-").replace("–", "-")
    out: dict[str, float] = {}

    def pct_after(word: str) -> float | None:
        m = re.search(f"(?:{word})" + r"[^0-9%]{0,24}?(-|\+)?\s*(\d+(?:\.\d+)?)\s*%", low)
        if not m:
            return None
        v = float(m.group(2))
        up = m.group(1) == "+" or re.search(f"(?:{word})" + r"[^0-9]{0,24}?(?:up|rise|rises|increase|higher)", low)
        return v if up else -v
    for key, word in (("revenue_pct", r"revenue|sales|turnover"), ("oil_pct", r"\boil"), ("collateral_pct", r"collateral(?: value)?"),
                      ("real_estate_pct", r"real estate prices?|property prices?"), ("gdp_pct", r"\bgdp")):
        v = pct_after(word)
        if v is not None:
            out[key] = v
    m = re.search(r"(?:saibor|eibor|rates?|interest(?: rates?)?)[^0-9]{0,16}?(-|\+)?\s*(\d+)\s*(?:bps|bp)", low)
    if m:
        out["rate_bps"] = -float(m.group(2)) if m.group(1) == "-" or re.search(r"rates?[^0-9]{0,16}(?:down|cut|fall)", low) else float(m.group(2))
    m = re.search(r"(?:ebitda )?margin[^0-9]{0,20}?(-|\+)?\s*(\d+)\s*(?:bps|bp)", low)
    if m:
        out["ebitda_margin_bps"] = float(m.group(2)) if m.group(1) == "+" else -float(m.group(2))
    m = re.search(r"(one|two|three|1|2|3)\s*notch", low)
    if m:
        out["notches"] = float({"one": 1, "two": 2, "three": 3}.get(m.group(1), m.group(1)))
    m = re.search(r"delay(?:ed)?[^0-9]{0,12}(\d+)\s*months?|(\d+)[- ]months? (?:project )?delay", low)
    if m:
        out["project_delay_months"] = float(m.group(1) or m.group(2))
    if re.search(r"largest customer", low):
        out["largest_customer_lost"] = 1.0
    if re.search(r"guarantee unenforceable", low):
        out["guarantee_unenforceable"] = 1.0
    return out


NAMED_SCENARIO = (("severe", r"severe|combined"), ("oil_30", r"\boil\b"), ("rates_200", r"(?:saibor|eibor|rates?)\s*\+?\s*200\b"),
                  ("gdp_3", r"\bgdp\b"), ("re_20", r"real estate prices"), ("construction_downturn", r"construction downturn"),
                  ("trading_slowdown", r"trading slowdown"), ("customer_loss", r"largest customer"),
                  ("guarantee_void", r"guarantee unenforceable"), ("delay_6", r"\b6[- ]months? (?:project )?delay|delay(?:ed)? (?:by )?6 months"),
                  ("delay_12", r"\b12[- ]months? (?:project )?delay|delay(?:ed)? (?:by )?12 months"),
                  ("margin_300", r"margin squeeze"))
# Library scenarios that a named question maps to exactly (no custom shock needed).
LIBRARY_ONLY = {"oil_pct", "gdp_pct", "real_estate_pct", "largest_customer_lost", "guarantee_unenforceable", "project_delay_months"}


# ------------------------------------------------------------------ formatting (figures copied from the results)

def pct(x: Any, d: int | None = None) -> str:
    return "n/a" if not isinstance(x, (int, float)) or isinstance(x, bool) else F.pct(x, d)


def sar(x: Any) -> str:
    if not isinstance(x, (int, float)) or isinstance(x, bool):
        return "n/a"
    sign, a = ("−" if x < 0 else ""), abs(float(x))
    return sign + (f"SAR {a / 1000:,.2f}bn" if a >= 1000 else f"SAR {a:,.1f}m" if a >= 10 else f"SAR {a:,.2f}m")


def g(d: Any, *names: str, default: Any = None) -> Any:
    """The first present key of `names` in `d` (dotted paths allowed): the writers read the R11 results defensively."""
    if not isinstance(d, dict):
        return default
    for n in names:
        cur: Any = d
        for part in n.split("."):
            cur = cur.get(part) if isinstance(cur, dict) else None
            if cur is None:
                break
        if cur is not None:
            return cur
    return default


def _pid(ctx: ToolContext, args: dict) -> str:
    pid = str(args.get("proposal_id") or ctx.scope.get("proposal_id") or "")
    if not pid:
        raise ValueError("Name a proposal (DD-nn), or open one from the pipeline.")
    return pid


def _terms(ctx: ToolContext) -> dict | None:
    return (ctx.state or {}).get("terms")


# ------------------------------------------------------------------ tools

def t_forward_risk(ctx: ToolContext, args: dict) -> ToolResult:
    pid = _pid(ctx, args)
    r = engine.post(f"/proposals/{pid}/forward-risk", {"terms": _terms(ctx)})
    rows = [{"structure": g(s, "label", "name", "key"), "p_stage2_next_q": g(s, "p_stage2_next_q", "p_stage2"),
             "p_dpd30_next_q": g(s, "p_dpd30_next_q", "p_dpd30"), "ecl_day1": g(s, "ecl_day1", "day1_ecl"),
             "ecl_4q": g(s, "ecl_4q", "expected_ecl_4q")} for s in g(r, "structures", default=[]) or []]
    return ToolResult(summary="Forward risk on the deal's structures", data=r, rows=rows or None)


def t_stress_lab(ctx: ToolContext, args: dict) -> ToolResult:
    """S2: the Stress Lab on the thread's terms (else the engine's recommended structure); `custom` is the typed shock
    text (S parses it: "revenue -20% and rates +150 bps") or a shock spec."""
    pid = _pid(ctx, args)
    body: dict[str, Any] = {"terms": _terms(ctx), "resilience": True, "breakevens": True}
    if args.get("custom"):
        body["custom"] = args["custom"]
    if args.get("scenarios"):
        body["scenarios"] = args["scenarios"]
    r = engine.post(f"/proposals/{pid}/stress", body)
    rows = [{"scenario": g(x, "label", "name", "id"), "survives": g(x, "survives"), "dscr": g(x, "metrics.dscr", "dscr"),
             "lifetime_raroc": g(x, "metrics.lifetime_raroc", "lifetime_raroc")} for x in g(r, "scenarios", "rows", default=[]) or []]
    return ToolResult(summary="Stress Lab on the structure", data=r, rows=rows or None)


def t_pipeline_test(ctx: ToolContext, args: dict) -> ToolResult:
    pid = _pid(ctx, args)
    r = engine.post(f"/proposals/{pid}/pipeline-test", {"terms": _terms(ctx)})
    return ToolResult(summary="Tested against the pending pipeline", data=r)


def t_pipeline_optimise(ctx: ToolContext, args: dict) -> ToolResult:
    r = engine.post("/pipeline/optimise", {k: v for k, v in args.items() if k in ("deal_ids", "rwa_budget", "el_budget")})
    rows = [{"deal": g(d, "proposal_id", "deal_id", "id"), "obligor": g(d, "obligor_name", "obligor", "name"),
             "decision": g(d, "decision", "option"), "sva": g(d, "sva")} for d in g(r, "decisions", "deals", default=[]) or []]
    return ToolResult(summary="The pipeline optimised", data=r, rows=rows or None)


def t_review(ctx: ToolContext, args: dict) -> ToolResult:
    pid = _pid(ctx, args)
    r = engine.post(f"/proposals/{pid}/review", {})
    rows = [{"severity": g(f, "severity"), "finding": g(f, "title", "label", "finding"), "verdict": g(f, "verdict")}
            for f in g(r, "findings", default=[]) or []]
    return ToolResult(summary="The memo reviewed against the books and policy", data=r, rows=rows or None)


def t_committee_sheet(ctx: ToolContext, args: dict) -> ToolResult:
    pid = _pid(ctx, args)
    r = engine.get(f"/proposals/{pid}/review/sheet")
    return ToolResult(summary="The committee decision sheet", data=r)


OBJ = {"type": "object"}
PID = {"proposal_id": {"type": "string"}}
TOOLS = [
    Tool("forward_risk", "Forward risk of the deal per Optimise structure: P(Stage 2 next quarter), P(30+ DPD next quarter), the four-quarter "
         "stage path, Day-1 and expected ECL, drivers, the ECL-optimal structure, and the Early Warning rules on the obligor after the deal.",
         {"type": "object", "properties": PID}, t_forward_risk, message="Scoring forward risk and early warning"),
    Tool("stress_lab", "Stress Lab: run the scenario library (macro, sector, obligor, collateral, rating, combined) or `custom` shocks "
         "(revenue_pct, rate_bps, oil_pct, collateral_pct, ebitda_margin_bps, notches, ...) on the structure; per scenario DSCR, LTV, "
         "covenant headroom, PD, stage, ECL, RAROC, SVA; the breakevens (reverse stress) and structure resilience.",
         {"type": "object", "properties": {**PID, "custom": OBJ, "scenarios": {"type": "array"}}}, t_stress_lab, message="Running the Stress Lab"),
    Tool("pipeline_test", "Test the deal (the thread's structure, else the recommended one) against every pending deal and limit: does it make "
         "the cut, its rank by SVA per RWA, deals displaced, its marginal effect on each risk-appetite limit, the limit that binds first.",
         {"type": "object", "properties": PID}, t_pipeline_test, message="Testing against the pipeline"),
    Tool("pipeline_optimise", "Select the best set of pending deals under every hard limit and the RWA and EL budgets, maximising SVA: the "
         "decision per deal, the portfolio against risk appetite, the frontier and the shadow price of the binding constraints.",
         {"type": "object", "properties": {"deal_ids": {"type": "array"}, "rwa_budget": {"type": "number"}, "el_budget": {"type": "number"}}},
         t_pipeline_optimise, message="Optimising the pipeline"),
    Tool("review_memo", "Review the credit memo: claims checked against the books, internal consistency, policy and DoA, connected parties; "
         "findings by severity, the recommended decision, counter-proposals and conditions (the committee decision sheet).",
         {"type": "object", "properties": PID}, t_review, message="Reviewing the memo"),
    Tool("committee_sheet", "The one-page committee decision sheet: the ask, findings by severity, the recommended decision and approval "
         "level, the counter-proposal and the conditions.", {"type": "object", "properties": PID}, t_committee_sheet,
         message="Drafting the committee sheet"),
]


def plan_steps(intent: str, q: str, ctx: ToolContext) -> list[PlanStep]:
    if intent in ("forward_risk", "ews_deal"):
        return [PlanStep("forward_risk", {})]
    if intent == "stress_lab":
        shocks = parse_shocks(q)
        named = [k for k, pat in NAMED_SCENARIO if re.search(pat, q, re.I)]
        # A named library scenario runs the library and is read from it; any other figure is a custom shock, sent as
        # the user's own words (S parses them and reports what it did not understand).
        custom = q.strip() if shocks and not (named and set(shocks) <= LIBRARY_ONLY) else ""
        ctx.state["_r11_named"] = named
        ctx.state["_r11_custom"] = bool(custom)
        return [PlanStep("stress_lab", {"custom": custom} if custom else {})]
    if intent == "pipeline_test":
        return [PlanStep("pipeline_test", {})]
    if intent == "pipeline_optimise":
        return [PlanStep("pipeline_optimise", {})]
    if intent == "committee_sheet":
        return [PlanStep("committee_sheet", {})]
    return [PlanStep("review_memo", {})]


# ------------------------------------------------------------------ writers

def _res(results: list[dict], tool: str) -> tuple[dict | None, str]:
    for r in results:
        if r["tool"] == tool:
            if r["error"]:
                return None, str(r["out"].get("error") or "")
            return (r["out"].get("data") or r["out"]), ""
    return None, ""


def _unavailable(what: str, err: str) -> dict:
    """The engine refused or the R11 API is not in this build: one plain sentence, no figures."""
    low = err.lower()
    why = "this proposal has no memo to review" if "memo" in low and "not" in low else "the engine could not compute it for this deal"
    return {"markdown": f"{what} is not in this answer: {why}. The Deal Desk step shows the same analysis on the screen.",
            "suggestions": ["Why does the ask fail?", "Optimise"]}


def _band(x: Any) -> str:
    return str(x).replace("_", " ").capitalize() if x else "n/a"


def _structure(r: dict, which: str = "recommended") -> dict:
    ss = g(r, "structures", default=[]) or []
    for s in ss:
        if str(g(s, "key", "role", default="")).lower() == which or str(g(s, "label", default="")).lower() == which:
            return s
    return ss[0] if ss else r


def _ecl(x: dict, k: str) -> Any:
    """F: ecl{day1,next_q,q4}; flat aliases tolerated."""
    return g(x, f"ecl.{k}", {"day1": "ecl_day1", "next_q": "ecl_next_q", "q4": "ecl_4q"}[k])


def write_forward(q: str, results: list[dict], ctx: ToolContext) -> dict:
    r, err = _res(results, "forward_risk")
    if r is None:
        return _unavailable("Forward risk", err)
    s = _structure(r)
    ews = g(r, "ews", default={}) or {}
    ans = g(r, "answer", default=None)
    if isinstance(ans, str) and ans:
        lines = [f"**{ans}**"]
    else:
        p2, p30 = g(s, "p_stage2_next_q", "p_stage2"), g(s, "p_dpd30_next_q", "p_dpd30")
        book2, book30 = g(r, "book.p_stage2_next_q"), g(r, "book.p_dpd30_next_q")
        lines = [f"**{g(s, 'label', default='Recommended')} structure: {pct(p2)} chance of Stage 2 next quarter**"
                 + (f" (book {pct(book2)})" if book2 is not None else "") + f", {pct(p30)} of 30+ DPD"
                 + (f" (book {pct(book30)})" if book30 is not None else "") + (f"; EWS band {_band(g(ews, 'band'))}." if ews else ".")]
    e1, en, e4 = _ecl(s, "day1"), _ecl(s, "next_q"), _ecl(s, "q4")
    if e1 is not None or e4 is not None:
        lines.append(f"**ECL from day one:** Day-1 {sar(e1)}" + (f", expected next quarter {sar(en)}" if en is not None else "")
                     + f", expected in four quarters {sar(e4)}.")
    ss = g(r, "structures", default=[]) or []
    if len(ss) > 1:
        lines.append("**By structure:**")
        for x in ss[:5]:
            lines.append(f"- {g(x, 'label', 'name', 'key')}: Stage 2 {pct(g(x, 'p_stage2_next_q', 'p_stage2'))}, 30+ DPD "
                         f"{pct(g(x, 'p_dpd30_next_q', 'p_dpd30'))}, expected ECL in four quarters {sar(_ecl(x, 'q4'))}.")
    opt = g(r, "ecl_optimal", default=None)
    if isinstance(opt, dict) and g(opt, "label", "name"):
        lines.append(f"**ECL-optimal structure:** {g(opt, 'label', 'name')}, the lowest expected four-quarter ECL that still clears the hurdle"
                     + (f" ({sar(g(opt, 'ecl_q4'))})." if g(opt, "ecl_q4") is not None else "."))
    lever = g(r, "best_lever", default=None)
    if isinstance(lever, dict) and g(lever, "label", "lever"):
        lines.append(f"**Lever:** {g(lever, 'label', 'lever')} cuts the Stage 2 chance most per bp of RAROC given up.")
    drivers = g(s, "drivers", default=[]) or []
    if drivers:
        lines.append("**What drives it:** " + "; ".join(
            f"{g(d, 'label', 'feature')} ({g(d, 'direction')})" if isinstance(d, dict) and g(d, "direction") else str(g(d, "label", "feature", default=d))
            for d in drivers[:5]) + ".")
    return {"markdown": "\n".join(lines), "suggestions": ["Run early warning on this deal", "Stress this deal with oil −30%", "Test against pipeline"]}


def write_ews(q: str, results: list[dict], ctx: ToolContext) -> dict:
    r, err = _res(results, "forward_risk")
    if r is None:
        return _unavailable("Early warning on the deal", err)
    e = g(r, "ews", default={}) or {}
    if not e:
        return _unavailable("Early warning on the deal", "")
    fired = g(e, "fired", "rules_fired", "rules", default=[]) or []
    lines = [f"**EWS band {_band(g(e, 'band'))}** after the deal, score {F.num(g(e, 'score'))}"
             + (f"; {g(e, 'vs_book', 'book_comparison')}." if isinstance(g(e, "vs_book", "book_comparison"), str) else ".")]
    if fired:
        lines.append(f"**Rules fired ({len(fired)}):**")
        for x in fired[:8]:
            v = g(x, "value")
            vals = g(x, "values", default=None)
            if isinstance(vals, dict) and vals:
                v = ", ".join(f"{k.replace('_', ' ')} {F.num(w) if isinstance(w, (int, float)) and not isinstance(w, bool) else w}" for k, w in list(vals.items())[:3])
            lines.append(f"- {g(x, 'label', 'rule', 'id')}" + (f" (weight {F.num(g(x, 'weight'))})" if g(x, "weight") is not None else "")
                         + (f": {v}" if isinstance(v, str) else f": {F.num(v)}" if v is not None else ""))
    else:
        lines.append("No Early Warning rule fires on the obligor as it would stand after the deal.")
    cur = g(e, "current", "current_status", default=None)
    if isinstance(cur, dict) and cur:
        lines.append(f"**In the EWS book today:** band {_band(g(cur, 'band'))}, score {F.num(g(cur, 'score'))}.")
    return {"markdown": "\n".join(lines), "suggestions": ["What is the chance of Stage 2 next quarter?", "What breaks first?"]}


def _dist(b: dict) -> str:
    u = str(g(b, "unit", default="") or "")
    v = F.num(g(b, "distance", "value"))
    return f"{v}{u}" if u in ("%", "x") else f"{v} {u}".strip()


def _status_of(s: dict) -> str:
    st = str(g(s, "status", "result", default="")).lower()
    return "breach" if st in ("breach", "fail", "failed", "red") else "amber" if st in ("amber", "warning", "watch") else "pass"


def _survives(x: dict) -> bool:
    sv = g(x, "survives", default=None)
    return bool(sv) if sv is not None else _status_of(x) != "breach"


def write_stress_lab(q: str, results: list[dict], ctx: ToolContext) -> dict:
    r, err = _res(results, "stress_lab")
    if r is None:
        return _unavailable("The Stress Lab", err)
    sc = [x for x in g(r, "scenarios", "rows", default=[]) or [] if g(x, "applicable", default=True)]
    named = ctx.state.get("_r11_named") or []
    custom = ctx.state.get("_r11_custom")
    focus = [x for x in sc if str(g(x, "id", default="")).lower() in named]
    if custom:
        focus = [x for x in sc if str(g(x, "id", default="")) == "custom" or str(g(x, "group", default="")) == "custom"] or focus
    ans = g(r, "answer", default=None)
    fails = [x for x in sc if not _survives(x)]
    lines = []
    if isinstance(ans, str) and ans:
        lines.append(f"**{ans}**")
    elif sc:
        lines.append(f"**Survives {len(sc) - len(fails)} of {len(sc)} scenarios**"
                     + (f"; fails {', '.join(str(g(x, 'label', 'id')) for x in fails[:3])}." if fails else "."))
    for x in focus[:4]:
        fo = [str(c).replace("_", " ") for c in g(x, "fails_on", default=[]) or []]
        lines.append(f"- **{'Your shock' if str(g(x, 'id')) == 'custom' else g(x, 'label', 'id')}:** DSCR {F.times(g(x, 'metrics.dscr', 'dscr'))}, "
                     f"lifetime RAROC {pct(g(x, 'metrics.lifetime_raroc', 'lifetime_raroc'))}, rating {g(x, 'metrics.rating', default='n/a')}, "
                     f"Stage {g(x, 'metrics.stage', 'stage', default='n/a')}: " + (f"fails {', '.join(fo)}." if fo else "holds."))
    cu = g(r, "custom", default=None)
    if custom and isinstance(cu, dict) and cu.get("unparsed"):
        lines.append("Not understood in the shock: " + ", ".join(map(str, cu["unparsed"])) + ".")
    be = g(r, "breakevens", "breakeven", default=[]) or []
    firsts = [b for b in be if isinstance(b, dict) and isinstance(g(b, "first.value"), (int, float))]
    if firsts:
        b0 = sorted(firsts, key=lambda b: abs(_scaled(b)))[0]
        lines.append(f"**What breaks first:** {g(b0, 'label')}, {_be_value(b0)} before {g(b0, 'first.label')}.")
        for b in firsts:
            if b is not b0:
                lines.append(f"- {g(b, 'label')}: {_be_value(b)} to {g(b, 'first.label')}.")
    else:
        plain = sorted([b for b in be if isinstance(b, dict) and isinstance(g(b, "distance", "value"), (int, float))],
                       key=lambda b: abs(g(b, "distance", "value")))
        if plain:
            lines.append(f"**What breaks first:** {g(plain[0], 'label')}, {_dist(plain[0])} before {g(plain[0], 'threshold', default='the threshold')}.")
    res = g(r, "resilience", default=None)
    if isinstance(res, dict) and isinstance(g(res, "verdict", "summary"), str):
        lines.append(f"**Asked against recommended:** {g(res, 'verdict', 'summary')}")
    if not lines:
        return _unavailable("The Stress Lab", "")
    return {"markdown": "\n".join(lines), "suggestions": ["What breaks first?", "Revenue −20% and rates +150 bps", "Test against pipeline"]}


def _scaled(b: dict) -> float:
    """A breakeven's distance as a share of its search range, so revenue % and rate bps compare."""
    v = float(g(b, "first.value"))
    rg = g(b, "range", default=None)
    span = max(abs(float(rg[0])), abs(float(rg[1]))) if isinstance(rg, (list, tuple)) and len(rg) == 2 and any(rg) else 1.0
    return v / span if span else v


def _be_value(b: dict) -> str:
    v, u = g(b, "first.value"), str(g(b, "unit", default="") or "")
    if u in ("share", "ratio", "pct", "%") and abs(float(v)) <= 1.5:   # S: "%" drivers carry fractions (-0.27 = -27%)
        return F.pct(v, signed=True)
    if u == "bps":
        return F.bps(v, signed=True).replace("-", "−")
    return f"{F.num(v)}{u}" if u in ("%", "x") else f"{F.num(v)} {u}".strip()


def write_pipeline_test(q: str, results: list[dict], ctx: ToolContext) -> dict:
    r, err = _res(results, "pipeline_test")
    if r is None:
        return _unavailable("The pipeline test", err)
    cut = g(r, "makes_cut", "makes_the_cut", "in_set", default=None)
    rank, n = g(r, "rank"), g(r, "of", "pending", "n_deals")
    lines = [("**It makes the cut**" if cut else "**It does not make the cut**" if cut is not None else "**Pipeline test**")
             + (f": rank {F.num(rank)}" + (f" of {F.num(n)}" if n is not None else "") + " by SVA per unit of RWA" if rank is not None else "")
             + "."]
    disp = g(r, "displaces", "displaced", default=[]) or []
    if disp:
        lines.append("**Displaces:** " + "; ".join(str(g(d, "obligor_name", "label", "proposal_id", default=d)) for d in disp[:5]) + ".")
    elif cut:
        lines.append("It displaces no pending deal.")
    bind = g(r, "binds_first", "binding_first", "first_binding", default=None)
    if bind:
        lines.append(f"**Binds first:** {g(bind, 'label', 'limit', default=bind) if isinstance(bind, dict) else bind}.")
    for x in (g(r, "limits", "marginal", default=[]) or [])[:5]:
        if isinstance(x, dict) and g(x, "label"):
            lines.append(f"- {g(x, 'label')}: {g(x, 'before_text', default=pct(g(x, 'before')))} → {g(x, 'after_text', default=pct(g(x, 'after')))} "
                         f"({g(x, 'status', default='')})".replace(" ()", ""))
    return {"markdown": "\n".join(lines), "suggestions": ["Optimise the pipeline", "What is the chance of Stage 2 next quarter?"]}


def write_pipeline_optimise(q: str, results: list[dict], ctx: ToolContext) -> dict:
    r, err = _res(results, "pipeline_optimise")
    if r is None:
        return _unavailable("The pipeline optimisation", err)
    head = g(r, "headline", "summary", default=None)
    dec = g(r, "decisions", "deals", default=[]) or []
    appr = [d for d in dec if str(g(d, "decision", "option", default="")).lower() not in ("decline", "declined")]
    lines = [f"**{head}**" if isinstance(head, str) and head else
             f"**Approve {len(appr)} of {len(dec)} deals:** SVA {sar(g(r, 'total_sva', 'sva'))}, RWA {sar(g(r, 'rwa_used', 'rwa'))}"
             f" of {sar(g(r, 'rwa_budget'))} budget."]
    sp = g(r, "shadow_prices", "shadow", default=[]) or []
    for x in sp[:2]:
        if isinstance(x, dict) and g(x, "text"):
            lines.append(f"- {g(x, 'text')}")
    # The approved deals first (highest SVA first), then the declines: the CCO reads the selection before the misses.
    ordered = sorted(dec, key=lambda d: (str(g(d, "decision", "option", default="")).lower() in ("decline", "declined"),
                                         -(g(d, "sva", default=0) or 0) if isinstance(g(d, "sva"), (int, float)) else 0))
    for d in ordered[:8]:
        lines.append(f"- {g(d, 'proposal_id', 'deal_id', 'id')} {g(d, 'obligor_name', 'obligor', default='')}: "
                     f"{str(g(d, 'decision', 'option', default='')).replace('_', ' ')}"
                     + (f", SVA {sar(g(d, 'sva'))}" if g(d, "sva") is not None else "") + (f" — {g(d, 'reason')}" if g(d, "reason") else ""))
    return {"markdown": "\n".join(lines), "suggestions": ["Test against pipeline", "Which proposals breach a hard limit?"]}


SEVERITIES = ("critical", "major", "minor")


def _findings(r: dict) -> list[dict]:
    """R: findings as a list (workspace) or by severity (sheet), most severe first."""
    fs = g(r, "findings", default=[]) or []
    if isinstance(fs, dict):
        fs = [{**f, "severity": k} for k in SEVERITIES for f in fs.get(k) or []]
    order = {k: i for i, k in enumerate(SEVERITIES)}
    return sorted([f for f in fs if isinstance(f, dict)], key=lambda f: order.get(str(g(f, "severity", default="")).lower(), 3))


def money(x: Any, ccy: str) -> str:
    return sar(x) if ccy == "SAR" else (F.amount(x, ccy) if isinstance(x, (int, float)) and not isinstance(x, bool) else "n/a")


def _counter_line(c: dict, ccy: str) -> str:
    return (f"**Counter-proposal:** {g(c, 'title', 'label', default='restructured')}: lifetime RAROC {pct(g(c, 'raroc', 'lifetime_raroc', 'metrics.lifetime_raroc'))}"
            f", SVA {money(g(c, 'sva', 'metrics.sva'), ccy)}" + (f", Day-1 ECL {money(g(c, 'ecl_day1'), ccy)}" if g(c, "ecl_day1") is not None else "")
            + (f"; approval {g(c, 'approval')}" if isinstance(g(c, "approval"), str) else "") + ".")


def _headline(r: dict) -> str | None:
    a = g(r, "answer", default=None)
    if isinstance(a, dict):
        return g(a, "headline", "decision")
    return a if isinstance(a, str) and a else g(r, "headline", default=None)


def write_review(q: str, results: list[dict], ctx: ToolContext) -> dict:
    r, err = _res(results, "review_memo")
    if r is None:
        return _unavailable("The memo review", err)
    fs = _findings(r)
    head = _headline(r)
    counts = {k: sum(1 for f in fs if str(g(f, "severity", default="")).lower() == k) for k in SEVERITIES}
    lines = [f"**{head}**" if head else f"**{len(fs)} findings:** " + ", ".join(f"{n} {k}" for k, n in counts.items() if n) + "."]
    if head and fs:
        lines.append(f"**Findings:** " + ", ".join(f"{n} {k}" for k, n in counts.items() if n) + "; approval "
                     + str(g(r, "answer.approval", "doa.level", default="per the Delegation of Authority")) + ".")
    for f in fs[:8]:
        lines.append(f"- **{str(g(f, 'severity', default='')).capitalize()}** · {g(f, 'title', 'label')}"
                     + (f" ({str(g(f, 'verdict')).replace('_', ' ')})" if g(f, "verdict") else "")
                     + (f": {g(f, 'finding')}" if isinstance(g(f, "finding"), str) else ""))
    if len(fs) > 8:
        lines.append(f"{len(fs) - 8} more in the Review step.")
    ccy = str(g(r, "counter.ask.currency", "currency", default="SAR"))
    cp = g(r, "counter.counter_proposals", "counter_proposals", default=[]) or []
    if cp and isinstance(cp[0], dict):
        lines.append(_counter_line(cp[0], ccy))
    return {"markdown": "\n".join(lines), "suggestions": ["Draft the committee sheet", "What breaks first?", "Test against pipeline"]}


def write_committee(q: str, results: list[dict], ctx: ToolContext) -> dict:
    r, err = _res(results, "committee_sheet")
    if r is None:
        return _unavailable("The committee decision sheet", err)
    a = g(r, "answer", default={}) or {}
    ccy = str(g(r, "currency", default="SAR"))
    md = ["### Committee decision sheet"]
    dec = g(a, "decision") if isinstance(a, dict) else a
    if dec:
        hl = g(a, "headline") if isinstance(a, dict) else None
        md.append(f"**Recommended decision:** {hl if hl and str(hl).startswith(str(dec)) else dec}."
                  + (f" **Approval:** {g(r, 'doa.level', 'answer.approval')}." if g(r, "doa.level", "answer.approval") else ""))
    ask = g(r, "ask", default=None)
    if isinstance(ask, dict) and isinstance(ask.get("lines"), list):
        md.append("**The ask:** " + "; ".join(f"{x.get('name')} {money(x.get('proposed'), ccy)}" for x in ask["lines"][:6] if isinstance(x, dict)) + ".")
    elif isinstance(ask, str):
        md.append(f"**The ask:** {ask}")
    fs = _findings(r)
    if fs:
        md.append("**Findings by severity:**")
        md += [f"- {str(g(f, 'severity', default='')).capitalize()}: {g(f, 'title', 'label')}" + (f" ({g(f, 'ref', 'policy')})" if g(f, "ref", "policy") else "")
               for f in fs[:12]]
    cp = g(r, "counter_proposal", default=None) or (g(r, "counter_proposals", default=[]) or [None])[0]
    if isinstance(cp, dict):
        md.append(_counter_line(cp, ccy))
    conds = g(r, "conditions", default=[]) or []
    if conds:
        md.append("**Conditions:**")
        md += [f"- {g(c, 'what', 'label', 'text', default=c) if isinstance(c, dict) else c}" + (f" ({g(c, 'due')})" if isinstance(c, dict) and g(c, "due") else "")
               for c in conds[:10]]
    return {"markdown": "\n".join(md), "suggestions": ["Review the memo", "Test against pipeline"]}


WRITERS = {"forward_risk": write_forward, "ews_deal": write_ews, "stress_lab": write_stress_lab, "pipeline_test": write_pipeline_test,
           "pipeline_optimise": write_pipeline_optimise, "review": write_review, "committee_sheet": write_committee}

# The deal view's step an answer opens (thread.tsx R11_ACTION_STEP).
ACTION = {"stress_lab": "stress_lab", "review": "review", "committee_sheet": "committee_sheet"}
