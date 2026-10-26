"""Deal Desk agent "Committee Preparation" (PLAN_R11_AGENTS G2).

Goal: "Prepare DD-xx (or an uploaded proposal, or a prepared case) for committee".

The written plan (deterministic planner) by goal type:
- every deal: ingest -> spreading -> analysis -> Optimise -> forward risk -> stress -> pipeline test ->
  proposal review -> precedent -> house-style draft -> propose the conditions to track;
- **new to bank**: no conduct step (said explicitly in the plan notes);
- **existing client**: + conduct (book exposure, stage, DPD, bureau);
- **renewal**: + conduct + comparison with the last approval;
- **prepared case** (PRP-A-GMC, PRP-B-ASB; not in the pricing engine): ingest -> review -> precedent ->
  propose conditions; the engine steps are skipped explicitly.

It adapts after each result:
- a review finding whose rule carries a term lever (cash margin, tranching, optimise) -> a counter-proposal
  search with that condition fixed;
- a stress failure -> a structure search for resilience over the Optimise structures;
- a pipeline displacement -> the pipeline-level comparison;
- the Stress Lab not on this build -> the existing Analysis stress table.

Output: the committee pack (recommendation and why, counter-proposal with numbers, forward risk, stress,
pipeline fit, findings by severity, conditions, open questions for the RM, items it could not verify,
timing), the house-style draft, and proposals (conditions to track; a counter-offer to send to the RM).
"""
from __future__ import annotations

import re
from typing import Any

from backend.agentic.registry import Agent
from backend.agents_v5.dealdesk import tools as DT
from backend.agents_v5.runtime import (
    Adaptation,
    AgentDef,
    Conclusion,
    Finding,
    Plan,
    ProposalSpec,
    Run,
    Step,
    get_tool,
    register_agent,
)
from backend.agents_v5.runtime.types import DONE, FAILED, SKIPPED

AGENT_ID = "dealdesk.committee"
NEW, EXISTING, RENEWAL, CASE = "new_to_bank", "existing_client", "renewal", "prepared_case"
GOAL_TYPES = {NEW: "a new-to-bank borrower (no conduct history)",
              EXISTING: "new money for an existing client (conduct from the book)",
              RENEWAL: "a renewal (conduct, and the ask against the last approval)",
              CASE: "a prepared proposal case reviewed from its memo (not in the pricing engine)"}
PID_RE = re.compile(r"\b(DD-\d{1,3}|PRP-[A-Z]-[A-Z]{2,4}|UP-[\w-]+|U-[\w-]+)\b", re.I)
LEVER_TERMS = {"cash_margin": lambda lv: {"cash_margin_pct": float(lv.get("value") or 10)},
               "tranche_funded": lambda lv: {"funded_share_pct": round(float(lv.get("share") or 0.5) * 100)},
               "optimise": lambda lv: {}}
SEV_ORDER = {"critical": 0, "major": 1, "minor": 2, "info": 3}

SPEC = Agent(
    agent_id=AGENT_ID, business_name="Committee Preparation",
    purpose="Prepares a credit proposal for committee: analysis, Optimise, forward risk, stress, pipeline fit, "
            "proposal review, precedent and a house-style draft, ending in a committee pack with a recommendation.",
    when_to_use=("Prepare DD-xx for committee", "Prepare an uploaded proposal for committee"),
    when_not_to_use=("Pricing a single what-if structure (use Optimise)",),
    allowed_capabilities=("deal_analysis", "optimise", "forward_risk", "stress", "pipeline", "review", "drafting"),
    allowed_tools=DT.TOOL_NAMES, allowed_data_domains=("dealdesk", "corporate_book"),
    maximum_steps=22, timeout_seconds=600, max_model_calls=6, max_rows_scanned=50_000_000,
    human_approval_requirements=("dealdesk.conditions", "dealdesk.counter_offer"),
    owner="Credit Risk", autonomy_level=1)


def proposal_id(goal: str, ctx: dict[str, Any]) -> str:
    pid = str(ctx.get("proposal_id") or "").strip()
    if not pid:
        m = PID_RE.search(goal or "")
        pid = m.group(1).upper() if m else ""
    return pid


def classify(goal: str, ctx: dict[str, Any]) -> str:
    pid = proposal_id(goal, ctx)
    if not pid:
        raise ValueError("Name the proposal (DD-xx) in the goal or pass context.proposal_id.")
    ctx["proposal_id"] = pid
    if DT.is_case(pid):
        return CASE
    from backend.dealdesk import proposals
    p = proposals.get(pid)
    o = p["obligor"]
    if not o.get("existing"):
        return NEW
    if "renew" in str(p.get("purpose") or "").lower() or DT.renewed_facilities(p):
        return RENEWAL
    return EXISTING


def _available(name: str) -> bool:
    t = get_tool(name)
    return bool(t and t.is_available()[0])


def deterministic_plan(goal: str, gt: str, ctx: dict[str, Any]) -> Plan:
    pid = ctx["proposal_id"]
    a = {"proposal_id": pid}
    p = Plan(goal=goal, agent=AGENT_ID, planner="deterministic", goal_type=gt)
    p.add("dd_ingest", a, "Read the proposal: obligor, ask, relationship")
    if gt == CASE:
        p.notes.append("Prepared case: reviewed from its memo; the pricing engine steps (analysis, Optimise, forward "
                       "risk, stress, pipeline, house-style draft) do not apply.")
        p.add("dd_review", a, "Claims ledger, findings, policy and DoA, connected parties, counter-proposals")
        p.add("dd_precedent", a, "How similar deals behaved")
        p.add("dd_propose_conditions", a, "Conditions to track, for a credit officer to approve")
        return p
    p.add("dd_spreading", a, "Spread the financials")
    if gt == NEW:
        p.notes.append("New to bank: no conduct step (no account history in the books).")
    else:
        p.add("dd_conduct", a, "Book exposure, stage, DPD history, conduct and bureau")
    if gt == RENEWAL:
        p.add("dd_last_approval", a, "Compare the ask with the last approval")
    p.add("dd_analysis", a, "RAROC, SVA, RWA, ECL and approval level as asked")
    p.add("dd_optimise", a, "All structures and the recommended deal")
    p.add("dd_forward_risk", a, "P(Stage 2), P(30+) next quarter, expected ECL, EWS on the deal")
    if _available("dd_stress_lab"):
        p.add("dd_stress_lab", a, "Scenarios, breakevens and resilience")
    else:
        p.notes.append("Stress Lab not available on this build: the existing Analysis stress table is used.")
        p.add("dd_stress_table", a, "The Analysis stress table")
    p.add("dd_pipeline_test", a, "Does it make the cut against the pipeline and limits")
    p.add("dd_review", a, "Claims ledger, findings, policy and DoA, connected parties, counter-proposals")
    p.add("dd_precedent", a, "How similar deals behaved")
    p.add("dd_house_style_draft", a, "The proposal drafted in the house style")
    p.add("dd_propose_conditions", a, "Conditions to track, for a credit officer to approve")
    return p


def required_tools(gt: str, ctx: dict[str, Any]) -> list[str]:
    if gt == CASE:
        return ["dd_ingest", "dd_review"]
    return ["dd_ingest", "dd_analysis", "dd_optimise", "dd_review"]


def adapt(run: Run, step: Step) -> list[Adaptation]:
    pid = run.context.get("proposal_id")
    out: list[Adaptation] = []
    if step.tool == "dd_review" and run.plan and run.plan.goal_type != CASE:
        seen = 0
        for f in (step.output or {}).get("findings") or []:
            lv = f.get("lever") or {}
            fn = LEVER_TERMS.get(lv.get("type"))
            if fn is None or seen >= 2:
                continue
            seen += 1
            out.append(Adaptation("dd_counter_search", {"proposal_id": pid, "fixed": fn(lv),
                                                        "condition": lv.get("label") or lv.get("type")},
                                  f"Review finding {f.get('rule_id')} ({f.get('severity')}) implies: "
                                  f"{lv.get('label')}", f"review:{f.get('rule_id')}->counter_search"))
    if step.tool == "dd_stress_lab":
        sm = (step.output or {}).get("summary") or {}
        sev = sm.get("severe") or {}
        if sm.get("failed") or sev.get("survives") is False:
            out.append(Adaptation("dd_resilience_search", {"proposal_id": pid, "scenarios": list(sm.get("failed") or [])},
                                  f"Fails {len(sm.get('failed') or [])} scenarios: search the structures for resilience",
                                  "stress:failure->resilience_search"))
    if step.tool == "dd_pipeline_test":
        d = step.output or {}
        disp = d.get("displaces") or d.get("displaced") or []
        if disp:
            out.append(Adaptation("dd_pipeline_compare", {"proposal_id": pid, "forced": True},
                                  f"It displaces {len(disp)} pipeline deals: compare at pipeline level",
                                  "pipeline:displacement->pipeline_compare"))
    return out


# ------------------------------------------------------------------ the committee pack

def _pct(x: float) -> str:
    return f"{x:.1%}"


def _m(x: float) -> str:
    return f"{x:,.2f}m"


def conclude(run: Run) -> Conclusion:
    plan = run.plan
    S = {t: run.done(t) for t in DT.TOOL_NAMES}
    out = lambda t: (S[t].output or {}) if S.get(t) else {}  # noqa: E731
    fig = lambda t: (S[t].figures or {}) if S.get(t) else {}  # noqa: E731
    sid = lambda t: S[t].id if S.get(t) else ""  # noqa: E731
    ing = out("dd_ingest")
    pid = run.context.get("proposal_id")
    name = ing.get("name") or pid
    findings: list[Finding] = []
    lines: list[str] = []
    why: list[dict[str, Any]] = []
    proposals: list[ProposalSpec] = []
    ccy = ing.get("currency") or "SAR"

    # --- review findings (by severity)
    rv = out("dd_review")
    for f in sorted(rv.get("findings") or [], key=lambda f: SEV_ORDER.get(f.get("severity") or "info", 3)):
        findings.append(Finding(title=f.get("title") or f.get("rule_id"), severity=f.get("severity") or "info",
                                detail=f.get("finding") or "", evidence=[sid("dd_review") + ":" + str(f.get("rule_id"))],
                                kind="review", data={"rule_id": f.get("rule_id"), "policy_ref": f.get("policy_ref"),
                                                     "crm_article": f.get("crm_article"), "verdict": f.get("verdict")}))

    # --- the numbers
    an, af = out("dd_analysis"), fig("dd_analysis")
    op, of = out("dd_optimise"), fig("dd_optimise")
    fr, ff = out("dd_forward_risk"), fig("dd_forward_risk")
    st, sf = out("dd_stress_lab"), fig("dd_stress_lab")
    rs, rsf = out("dd_resilience_search"), fig("dd_resilience_search")
    ptf = fig("dd_pipeline_test")
    prf = fig("dd_precedent")
    dr, drf = out("dd_house_style_draft"), fig("dd_house_style_draft")
    rvf = fig("dd_review")
    is_case = plan.goal_type == CASE if plan else False

    ask_clears = bool(af) and bool((an.get("metrics") or {}).get("clears_hurdle")) and not an.get("hard_breaches")
    rec = op.get("closest") or op.get("max_sva") if op else None
    crit, major = int(rvf.get("critical", 0)), int(rvf.get("major", 0))
    severe_fails = bool(st) and ((st.get("summary") or {}).get("severe") or {}).get("survives") is False
    stress_fails = int(sf.get("failed", 0) or 0)

    # --- counter-proposal: review counter (priced) > resilience > counter searches > Optimise recommended
    counter: dict[str, Any] | None = None
    cps = ((rv.get("counter") or {}).get("counter_proposals") or [])
    if cps and isinstance(cps[0].get("raroc"), (int, float)):
        c = cps[0]
        counter = {"label": c.get("title"), "source": "review", "step": sid("dd_review"), "raroc": c["raroc"],
                   "sva": c.get("sva"), "ecl": c.get("ecl_day1"), "amount": c.get("amount"), "hurdle": c.get("hurdle"),
                   "conditions": list(c.get("terms") or []) + list(c.get("conditions_precedent") or [])[:4],
                   "figure_keys": {"raroc": "cp_raroc", "sva": "cp_sva", "amount": "cp_amount", "ecl": "cp_ecl"}}
    if counter is None and rs.get("best") and severe_fails or (counter is None and rs.get("best") and stress_fails
                                                               and not ask_clears):
        b = rs["best"]
        counter = {"label": b["label"], "source": "resilience", "step": sid("dd_resilience_search"), "raroc": b["raroc"],
                   "sva": b["sva"], "terms": b["terms"], "conditions": [],
                   "figure_keys": {"raroc": "best_raroc", "sva": "best_sva"}}
    searches = [s for s in (plan.steps if plan else []) if s.tool == "dd_counter_search" and s.status == DONE
                and s.figures.get("feasible")]
    if counter is None and searches:
        s = max(searches, key=lambda s: s.figures.get("sva", -1e9))
        st_ = (s.output or {}).get("structure") or {}
        counter = {"label": f"With {(s.output or {}).get('condition')}", "source": "counter_search", "step": s.id,
                   "raroc": s.figures["raroc"], "sva": s.figures["sva"], "ecl": s.figures.get("ecl"),
                   "amount": s.figures.get("amount"), "terms": st_.get("terms"),
                   "conditions": [(s.output or {}).get("condition")],
                   "figure_keys": {"raroc": "raroc", "sva": "sva", "ecl": "ecl", "amount": "amount"}}
    if counter is None and rec and not ask_clears:
        rm = rec["metrics"]
        counter = {"label": rec.get("label") or "Optimise recommended", "source": "optimise", "step": sid("dd_optimise"),
                   "raroc": rm["lifetime_raroc"], "sva": rm["sva"], "ecl": rm.get("day_one_ecl"),
                   "amount": rm["amount_sar_mn"], "terms": rec.get("terms"),
                   "conditions": [c if isinstance(c, str) else c.get("label") or str(c) for c in rec.get("changes") or []],
                   "figure_keys": {"raroc": "rec_raroc", "sva": "rec_sva", "ecl": "rec_ecl", "amount": "rec_amount"}}

    # --- recommendation
    if is_case:
        decision = (rv.get("answer") or {}).get("decision") or "Review incomplete"
    elif crit > 0:
        decision = "Do not approve as proposed"
    elif ask_clears and not severe_fails:
        decision = "Approve as proposed" + (" with conditions" if rvf.get("conditions") else "")
    elif counter is not None:
        decision = "Approve on the counter-proposal"
    elif af:
        decision = "Decline as structured"
    else:
        decision = "Not enough evidence to recommend"

    # narrative, every figure cited
    lines.append(f"{decision} for {name} ({pid}).")
    if af:
        s = sid("dd_analysis")
        lines.append(f"As asked, RAROC is {_pct(af['lifetime_raroc'])} against a hurdle of {_pct(af['hurdle'])} "
                     f"and SVA is {ccy} {_m(af['sva'])} [{s}].")
        why.append({"text": f"As asked: RAROC {_pct(af['lifetime_raroc'])} vs hurdle {_pct(af['hurdle'])}",
                    "evidence": [s], "good": ask_clears})
        if an.get("hard_breaches"):
            why.append({"text": "Hard limit breaches as asked: " + ", ".join(an["hard_breaches"]), "evidence": [s],
                        "good": False})
            findings.append(Finding("Hard limit breached as asked", "major", ", ".join(an["hard_breaches"]), [s],
                                    "limits"))
    if crit or major:
        s = sid("dd_review")
        lines.append(f"The review found {crit} critical and {major} major findings [{s}]." if crit else
                     f"The review found {major} major {'finding' if major == 1 else 'findings'} [{s}].")
        why.append({"text": f"Review: {crit} critical, {major} major findings", "evidence": [s], "good": crit == 0})
    if counter:
        k = counter["figure_keys"]
        s = counter["step"]
        txt = f"The counter-proposal gives RAROC {_pct(counter['raroc'])}"
        if isinstance(counter.get("sva"), (int, float)) and "sva" in k:
            txt += f", SVA {ccy} {_m(counter['sva'])}"
        if isinstance(counter.get("ecl"), (int, float)) and "ecl" in k:
            txt += f", Day-1 ECL {ccy} {counter['ecl']:,.3f}m"
        lines.append(txt + f" [{s}].")
    if ff:
        s = sid("dd_forward_risk")
        t = f"Next quarter the chance of Stage 2 is {_pct(ff['p_stage2_next_q'])}"
        if "book_p_stage2" in ff:
            t += f" (book {_pct(ff['book_p_stage2'])})"
        t += f" and of 30+ DPD {_pct(ff.get('p_dpd30_next_q', 0))}"
        lines.append(t + f" [{s}].")
        if "book_p_stage2" in ff and ff["p_stage2_next_q"] > ff["book_p_stage2"]:
            findings.append(Finding("Forward risk above the book", "major",
                                    "P(Stage 2) next quarter is above the book average.", [s], "forward_risk"))
        ews = (fr.get("ews") or {})
        if ews.get("band") in ("high", "red", "amber", "medium"):
            findings.append(Finding(f"Early warning band {ews.get('band')} on the deal", "major",
                                    ", ".join(r.get("label", r.get("id", "")) if isinstance(r, dict) else str(r)
                                              for r in ews.get("rules_fired") or [])[:300], [s], "ews"))
    if sf:
        s = sid("dd_stress_lab")
        lines.append(f"Under stress it survives {int(sf.get('survived', 0))} of {int(sf.get('applicable', 0))} "
                     f"scenarios [{s}].")
        if stress_fails:
            findings.append(Finding(f"Fails {stress_fails} stress scenarios", "major" if severe_fails else "minor",
                                    "; ".join((st.get("summary") or {}).get("failed_labels") or [])[:400], [s], "stress"))
        if rsf and rs.get("best"):
            r = sid("dd_resilience_search")
            lines.append(f"The most resilient Optimise structure survives {int(rsf['best_survived'])} "
                         f"of {int(rsf['of'])} of those scenarios [{r}].")
    if ptf:
        s = sid("dd_pipeline_test")
        if ptf.get("makes_cut"):
            t = "It makes the cut against the pipeline"
            if "rank" in ptf and "ranked" in ptf:
                t += f", ranking {int(ptf['rank'])} of {int(ptf['ranked'])} by SVA per unit of RWA"
        else:
            t = "It does not make the cut against the pipeline"
        if ptf.get("displaced"):
            n = int(ptf["displaced"])
            t += f" and displaces {n} pending {'deal' if n == 1 else 'deals'}"
        lines.append(t + f" [{s}].")
        if not ptf.get("makes_cut"):
            findings.append(Finding("Does not make the cut against the pipeline", "major",
                                    S["dd_pipeline_test"].summary, [s], "pipeline"))
    if prf:
        s = sid("dd_precedent")
        lines.append(f"Of {int(prf['n'])} similar deals, {int(prf['stage2'])} reached Stage 2 within "
                     f"{int(prf['quarters'])} quarters [{s}].")
    if drf:
        lines.append(f"The house-style draft scores {drf['style_score']:.1f} [{sid('dd_house_style_draft')}].")

    # --- open questions and what could not be verified
    not_verified: list[dict[str, Any]] = []
    for s in plan.steps if plan else []:
        if s.status == SKIPPED:
            not_verified.append({"item": s.tool.replace("dd_", "").replace("_", " "), "reason": s.summary,
                                 "step": s.id})
        elif s.status == FAILED:
            not_verified.append({"item": s.tool.replace("dd_", "").replace("_", " "), "reason": s.error, "step": s.id})
    questions: list[dict[str, Any]] = []
    for c in (rv.get("unverifiable_checks") or [])[:8]:
        questions.append({"question": f"Provide evidence for: {c.get('title')}", "rule_id": c.get("rule_id"),
                          "evidence": [sid("dd_review")]})
        not_verified.append({"item": c.get("title"), "reason": "unverifiable from the data", "step": sid("dd_review")})
    for f in rv.get("findings") or []:
        if f.get("verdict") == "contradicted" and len(questions) < 12:
            questions.append({"question": f"Explain: {f.get('finding') or f.get('title')}", "rule_id": f.get("rule_id"),
                              "evidence": [sid("dd_review")]})
    conditions = [{"id": c.get("id"), "what": c.get("what"), "kind": c.get("kind"), "owner": c.get("owner"),
                   "due": c.get("due_text") or c.get("due_date"), "status": c.get("status"), "source": c.get("source")}
                  for c in ((rv.get("conditions") or {}).get("items") or [])]

    sev_txt = ", ".join(t for t in ((f"{crit} critical" if crit else ""), (f"{major} major" if major else "")) if t)
    noun = "finding" if crit + major == 1 else "findings"
    headline = f"{decision}" + (f": {sev_txt} {noun}" if sev_txt else "") + (
        f"; counter-proposal {counter['label']}" if counter else "")
    pack = {
        "headline": headline, "decision": decision, "proposal_id": pid, "name": name, "goal_type": plan.goal_type if plan else "",
        "why": why,
        "counter_proposal": ({k: v for k, v in counter.items() if k != "figure_keys"} if counter else None),
        "forward_risk": ({"answer": fr.get("answer"), "figures": ff, "step": sid("dd_forward_risk"),
                          "ecl_optimal": fr.get("ecl_optimal"), "ews": {k: (fr.get("ews") or {}).get(k) for k in
                                                                         ("band", "score", "vs_book", "basis")}}
                         if ff else None),
        "stress": ({"answer": st.get("answer"), "figures": sf, "step": sid("dd_stress_lab"),
                    "resilience": rs.get("best") and {k: rs["best"][k] for k in ("label", "survived", "of", "raroc")}}
                   if sf else ({"answer": S["dd_stress_table"].summary, "step": sid("dd_stress_table")}
                               if S.get("dd_stress_table") else None)),
        "pipeline": ({"answer": S["dd_pipeline_test"].summary, "figures": ptf, "step": sid("dd_pipeline_test")} if ptf
                     else {"answer": ("Not applicable: a prepared case is reviewed from its memo" if is_case else
                                      next((s.summary for s in (plan.steps if plan else [])
                                            if s.tool == "dd_pipeline_test"), "Not run")), "available": False}),
        "analysis": ({"figures": af, "approval": an.get("approval"), "step": sid("dd_analysis")} if af else None),
        "optimise": ({"figures": of, "recommended": rec and {"label": rec.get("label"), "metrics": rec.get("metrics"),
                                                             "changes": rec.get("changes")},
                      "step": sid("dd_optimise")} if op else None),
        "findings_by_severity": {sev: [f.to_dict() for f in findings if f.severity == sev] for sev in SEV_ORDER},
        "conditions": conditions,
        "open_questions": questions,
        "not_verified": not_verified,
        "precedent": ({"figures": prf, "step": sid("dd_precedent"), "summary": S["dd_precedent"].summary} if prf else None),
        "draft": ({"draft_id": dr.get("draft_id"), "title": dr.get("title"), "score": dr.get("score"),
                   "docx": dr.get("docx"), "step": sid("dd_house_style_draft")} if dr else None),
        "doa": rv.get("doa") and {"level": rv["doa"].get("level"), "basis": rv["doa"].get("basis")},
        "review_sheet_docx": f"/api/v1/dealdesk/proposals/{pid}/review/sheet.docx" if rv else None,
    }
    if counter and not decision.startswith("Approve as proposed"):
        proposals.append(ProposalSpec(
            kind="dealdesk.counter_offer", approver_role="CREDIT_OFFICER",
            title=f"Send counter-offer to the RM for {pid}: {counter['label']}",
            change={"proposal_id": pid, "offer": {k: counter.get(k) for k in ("label", "raroc", "sva", "ecl", "amount",
                                                                               "terms", "conditions", "source")}},
            reason=headline, evidence=[counter["step"]]))
    return Conclusion(findings=sorted(findings, key=lambda f: SEV_ORDER.get(f.severity, 3)),
                      narrative=" ".join(lines), output=pack, proposals=proposals)


SYSTEM = """You plan the Deal Desk "Committee Preparation" agent of CreditProbe, for a Chief Credit Officer.
Prepare the named proposal for credit committee. The pack needs: the analysis as asked, the Optimise structures and the
recommended deal, forward risk, stress, the pipeline test, the proposal review, precedent and the house-style draft,
then the conditions to track. Adapt to the borrower: a new-to-bank borrower has no conduct history (no dd_conduct);
an existing client gets dd_conduct; a renewal also gets dd_last_approval. Prepared cases (PRP-...) are reviewed from
their memo only. Inputs are {"proposal_id": "..."}; leave terms out (the tools take the recommended structure from
Optimise)."""


def register() -> None:
    DT.register()
    register_agent(AgentDef(spec=SPEC, module="dealdesk", goal_types=GOAL_TYPES, classify=classify,
                            deterministic_plan=deterministic_plan, conclude=conclude, adapt=adapt,
                            required_tools=required_tools,
                            scope_of=lambda ctx: str(ctx.get("proposal_id") or ""), system_prompt=SYSTEM,
                            href=lambda run: f"/deal-desk/{run.context.get('proposal_id')}?agent_run={run.run_id}"))
