"""The Scorecard Validation assistant: choose a scorecard, agree the plan, run it, review, report.

Deterministic (no model call): it reads the user's sentence for a scorecard, plan changes, a request to
run, or a question about a finished validation, and answers from the domain and the results. Every
number it quotes comes from `engine`. A thread carries a small state:

    stage         choose -> plan -> ran
    scorecard_id  the scorecard under validation
    plan          the agreed plan (windows, segment cut, test groups, threshold overrides)
    validation_id the finished validation, once run
"""
from __future__ import annotations

import re
from typing import Any

from backend.scorecard_v5 import engine
from backend.scorecard_v5.domain import build

GROUP_WORDS = {
    "discrimination": ["discrimination", "gini", "ks", "roc", "cap", "auc", "ranking"],
    "calibration": ["calibration", "accuracy", "hosmer", "binomial", "brier", "traffic", "observed", "expected"],
    "stability": ["stability", "psi", "csi", "drift", "population"],
    "variables": ["variable", "variables", "iv", "woe", "vif", "correlation", "monoton"],
    "overrides": ["override", "overrides"],
}
WHAT = {
    "discrimination": "Gini and AUC, KS, the ROC and CAP curves, and Gini by segment: does the score still rank good above bad?",
    "calibration": "Observed against expected default rate overall, by grade and by period; binomial traffic light by grade; Hosmer-Lemeshow; Brier skill.",
    "stability": "Score PSI and drift by period, CSI by variable, and the segment mix against the development sample.",
    "variables": "Information value, WoE monotonicity, correlation between variables and VIF.",
    "overrides": "How often the score is overridden, in which direction, and how upgrades performed.",
}
GLOSSARY = {
    "gini": "Gini (2 × AUC − 1) is how well the score ranks defaults below non-defaults: 0 is no better than chance, 1 is perfect.",
    "auc": "AUC is the probability that a random default scores lower than a random non-default; Gini = 2 × AUC − 1.",
    "ks": "KS is the largest gap between the cumulative share of defaults and of non-defaults when accounts are ordered by score.",
    "psi": "PSI compares the score distribution now with development: under 0.10 stable, 0.10 to 0.25 a moderate shift, over 0.25 a major shift.",
    "csi": "CSI is the PSI of one variable's bins: it shows which input moved when the score distribution moves.",
    "hosmer": "Hosmer-Lemeshow tests whether observed defaults match the expected defaults across all grades at once; with large samples it is strict, so read it with the grade table.",
    "binomial": "The binomial test asks, for one grade, how likely it is to see this many defaults if the grade PD were right. A small p-value means the PD is too low.",
    "brier": "The Brier score is the mean squared error of the predicted PD; the skill score compares it with always predicting the development default rate.",
    "woe": "Weight of evidence is ln(share of non-defaults ÷ share of defaults) in a bin; a higher WoE means a safer bin.",
    "iv": "Information value sums the WoE-weighted gap between non-defaults and defaults over the bins: under 0.02 not predictive, 0.02 to 0.10 weak, above 0.10 useful.",
    "vif": "The variance inflation factor shows how much a variable is explained by the others; above 5 is a concern, above 10 is collinear.",
    "cap": "The CAP curve shows the share of defaults captured as you go down the riskiest share of the population.",
    "roc": "The ROC curve plots the share of defaults caught against the share of non-defaults flagged as the cut-off moves.",
    "matured": "A period is matured once its 12-month window has closed, so its default flag is final. Outcome tests use only matured periods; stability tests use every period.",
    "override": "An override is a credit officer approving against a weak grade (upgrade) or declining against a strong one (downgrade).",
}
SEG_WORDS = {"product": "product", "region": "region", "sector": "sector", "channel": "origination_channel", "employment": "employment_type",
             "segment": "customer_segment", "tier": "relationship_tier"}
PERIOD = re.compile(r"\b(20\d\d-\d\d|20\d\dq[1-4])\b", re.I)
RUN = re.compile(r"\b(run|go ahead|go|start|proceed|execute|looks good|that works|agreed|yes|do it|validate now|kick off|launch)\b", re.I)


def _norm_period(p: str) -> str:
    return p.upper() if "q" in p.lower() else p


def _pct(v: float) -> str:
    return f"{v * 100:.1f}%"


def _scorecard_from(text: str) -> str | None:
    t = text.lower()
    if re.search(r"\bsme\b|small and medium|corporate scorecard", t):
        return "SME-ANN"
    if re.search(r"behaviou?r", t):
        return "RET-BEH"
    if re.search(r"\bapp(lication)?\b", t):
        return "RET-APP"
    for sid in build.SCORECARDS:
        if sid.lower() in t:
            return sid
    return None


def choose_block() -> dict[str, Any]:
    return {"type": "choose", "scorecards": engine.scorecards()}


def readiness(sid: str) -> list[str]:
    sc = engine.scorecards_by_id()[sid]
    sp = engine.domain(sid).spec
    unit = "accounts" if sc["book"] == "retail" else "borrowers"
    open_n = len([p for p in sp["periods"] if p > sp["last_matured"]])
    per = "months" if sc["frequency"] == "monthly" else "quarters"
    out = [f"{sc['rows']:,} scored {unit}-{ 'months' if sc['frequency'] == 'monthly' else 'quarters'} keyed to the {sc['book']} book, {sp['periods'][0]} to {sp['periods'][-1]}.",
           f"Development sample {sc['development'][0]} to {sc['development'][1]}: {sp['development_rows']:,} observations and {sp['development_defaults']:,} defaults.",
           f"Outcomes (default within 12 months) are final up to {sp['last_matured']}; the {open_n} {per} after it are still open, so they enter the stability tests only."]
    if sc["has_overrides"]:
        out.append("The data records credit-officer overrides, so the override tests can run.")
    else:
        out.append("The data records no overrides for this scorecard, so the override tests will report not applicable.")
    return out


def plan_block(plan: dict[str, Any], note: str = "") -> dict[str, Any]:
    sid = plan["scorecard_id"]
    th = engine.thresholds_for(sid, plan.get("thresholds"))
    groups = []
    keys = {"discrimination": ["gini", "gini_change", "ks", "gini_segment"], "calibration": ["oe_ratio", "binomial", "hl", "brier"],
            "stability": ["psi", "csi", "drift", "mix"], "variables": ["iv", "monotone", "corr", "vif"], "overrides": ["override_rate", "override_upgrade"]}
    for g in engine.GROUPS:
        groups.append({"group": g, "title": engine.GROUP_TITLES[g], "what": WHAT[g], "enabled": bool(plan["tests"].get(g)),
                       "thresholds": [{"label": th[k]["label"], "text": th[k]["text"]} for k in keys[g]]})
    return {"type": "plan", "plan": plan, "groups": groups, "note": note, "readiness": readiness(sid),
            "segment_options": engine.segment_options(sid)}


def _edit_plan(plan: dict[str, Any], text: str) -> tuple[bool, list[str]]:
    """Apply what the sentence asks to the plan. Returns (changed, what changed)."""
    t = text.lower()
    said: list[str] = []
    sid = plan["scorecard_id"]
    sp = engine.domain(sid).spec
    has_ovr = build.SCORECARDS[sid]["has_overrides"]
    mentioned = [g for g, words in GROUP_WORDS.items() if any(re.search(rf"\b{w}", t) for w in words)]
    if re.search(r"\b(only|just)\b", t) and mentioned:
        plan["tests"] = {g: (g in mentioned and (g != "overrides" or has_ovr)) for g in engine.GROUPS}
        said.append("Only " + ", ".join(engine.GROUP_TITLES[g].lower() for g in mentioned) + " will run.")
    elif re.search(r"\b(skip|exclude|drop|without|remove|leave out|no need)\b", t) and mentioned:
        for g in mentioned:
            plan["tests"][g] = False
        said.append("Left out: " + ", ".join(engine.GROUP_TITLES[g].lower() for g in mentioned) + ".")
    elif re.search(r"\b(include|add|also|with|bring back|restore)\b", t) and mentioned:
        for g in mentioned:
            if g == "overrides" and not has_ovr:
                said.append("This scorecard's data has no overrides, so that test group stays not applicable.")
                continue
            plan["tests"][g] = True
        said.append("Included: " + ", ".join(engine.GROUP_TITLES[g].lower() for g in mentioned if g != "overrides" or has_ovr) + ".")
    if re.search(r"\ball (the )?tests\b|\beverything\b|\bfull\b", t):
        plan["tests"] = {g: (g != "overrides" or has_ovr) for g in engine.GROUPS}
        said.append("All test groups are on.")
    m = re.search(r"\bby\s+(product|region|sector|channel|employment|segment|tier)\b", t)
    if m:
        col = SEG_WORDS[m.group(1)]
        if col in engine.segment_options(sid):
            plan["segment_by"] = col
            said.append(f"Segment cut: {col.replace('_', ' ')}.")
        else:
            said.append(f"This scorecard cannot be cut by {m.group(1)}; the options are {', '.join(o.replace('_', ' ') for o in engine.segment_options(sid))}.")
    periods = [_norm_period(p) for p in PERIOD.findall(text)]
    periods = [p for p in periods if p in sp["periods"]]
    if re.search(r"as[- ]of|at the end of|reporting date", t) and periods:
        plan["as_of"] = periods[-1]
        said.append(f"As-of period: {plan['as_of']}.")
    elif re.search(r"monitoring", t) and len(periods) == 2:
        a, b = sorted(periods)
        plan["monitoring"] = [a, b]
        said.append(f"Monitoring window: {a} to {b}.")
    elif re.search(r"develop", t) and len(periods) == 2:
        a, b = sorted(periods)
        plan["development"] = [a, b]
        said.append(f"Development window: {a} to {b}.")
    elif len(periods) == 1 and not said:
        plan["as_of"] = periods[0]
        said.append(f"As-of period: {periods[0]}.")
    if re.search(r"latest matured|last matured", t):
        plan["monitoring"] = [plan["monitoring"][0], sp["last_matured"]]
        said.append(f"Monitoring runs to the latest matured period, {sp['last_matured']}.")
    th = engine.thresholds_for(sid, plan.get("thresholds"))
    m = re.search(r"\b(gini|ks|psi|csi|vif|override rate)\b[^0-9]{0,40}?(\d*\.?\d+)\s*(%?)", t)
    if m and re.search(r"threshold|green|limit|tighten|loosen|raise|lower|set|at least|no more than|trigger", t):
        key = {"override rate": "override_rate"}.get(m.group(1), m.group(1))
        if key in th and th[key]["kind"] in ("high", "low"):
            val = float(m.group(2)) / (100 if m.group(3) or (th[key]["format"] == "pct" and float(m.group(2)) > 1) else 1)
            old = th[key]
            gap = abs(old["green"] - old["amber"])
            new = {"green": val, "amber": val - gap if old["kind"] == "high" else val + gap}
            plan.setdefault("thresholds", {})[key] = new
            said.append(f"{old['label']}: green now {val:g}{' (as a fraction)' if old['format'] == 'pct' else ''}, amber {new['amber']:.4g}.")
    return bool(said), said


class Context:
    """What the assistant needs from the service: finished results, earlier validations, and a way to run one."""

    def result(self, validation_id: str) -> dict[str, Any] | None:  # pragma: no cover - interface
        raise NotImplementedError

    def prior(self, scorecard_id: str, before_id: str) -> list[dict[str, Any]]:  # pragma: no cover - interface
        raise NotImplementedError

    def run(self, plan: dict[str, Any]) -> dict[str, Any]:  # pragma: no cover - interface
        raise NotImplementedError

    def turns(self) -> list[dict[str, Any]]:
        """The thread's settled turns (the conversation's memory)."""
        return []


#: A question or an analysis request: answered by the forked Cockpit agent on the Scorecard domain
#: (PLAN_R4 A2), unless it is a plan edit or a run request.
ASK = re.compile(r"^\s*(why|how|what|which|who|where|when|is|are|does|do|did|can|could|should|would|explain|tell me|show|"
                 r"list|describe|give me|diagnos\w*|analy[sz]e|break down|walk me through)\b|\?\s*$|\b(gini by|gini per|psi (for|of)|"
                 r"csi (for|of)|override analysis|segment gini|calibration by grade|what is wrong)\b", re.I)
PLAN_VERBS = re.compile(r"\b(skip|exclude|drop|only|just|include|cut the segments|as[- ]of|monitoring (from|window)|"
                        r"development (from|window)|threshold|set the|run it|run the validation|rerun|re-run|change the plan)\b", re.I)


def converse(state: dict[str, Any], text: str, ctx: "Context", answer: dict[str, Any]) -> dict[str, Any]:
    """Answer a question with the forked Cockpit agent on the Scorecard domain (real queries, checked figures)."""
    from backend.convo.agent import Agent
    from backend.scorecard_v5 import convo_domain

    class _Quiet:
        open_stage = ""

        def emit(self, *a, **k):
            return None

        def stage(self, name, message=""):
            self.open_stage = name

    convo_domain.RESULT = ctx.result
    scope = {"scorecard_id": state.get("scorecard_id"), "validation_id": state.get("validation_id"),
             "plan": state.get("plan")}
    out = Agent(convo_domain.DOMAIN, thread={}, scope=scope, state=state, question=text, emitter=_Quiet(),
                history=ctx.turns()).run()
    answer["blocks"].extend(out.blocks)
    answer["suggestions"] = out.suggestions
    answer["evidence"] = out.evidence
    return answer


def respond(state: dict[str, Any], text: str, ctx: Context) -> dict[str, Any]:
    """One turn. Mutates `state`. `ctx.run(plan)` runs the validation and returns {validation_id, summary, sample}."""
    t = text.strip()
    low = t.lower()
    stage = state.get("stage", "choose")
    answer: dict[str, Any] = {"blocks": [], "suggestions": [], "question_display": t}
    B = answer["blocks"]

    def text_block(md: str) -> None:
        B.append({"type": "text", "markdown": md})

    sid = _scorecard_from(low)
    if stage in ("plan", "ran") and not sid and not re.search(r"\b(which|list)\b.*\bscorecards\b|another scorecard|switch", low) and ASK.search(t) and not PLAN_VERBS.search(t) and \
            not re.search(r"compare with|previous validation|last validation|word|docx|playbook|share|mail|review|sign[- ]?off", low):
        return converse(state, t, ctx, answer)

    if re.search(r"\b(which|what|list|show)\b.*\bscorecards?\b|\bwhat can you validate\b|\bchoose\b|\bswitch\b|\banother scorecard\b", low) and not sid:
        state.update({"stage": "choose"})
        text_block("These are the scorecards in the validation library. Choose one and I will propose a plan.")
        B.append(choose_block())
        answer["suggestions"] = [{"label": s["name"], "send": f"Validate the {s['name']}"} for s in engine.scorecards()]
        return answer

    if stage == "ran" and not sid:
        return _after_run(state, t, low, answer, ctx)

    if sid and (stage in ("choose", "ran") or sid != state.get("scorecard_id")):
        state.update({"stage": "plan", "scorecard_id": sid, "plan": engine.default_plan(sid), "validation_id": None})
        sc = engine.scorecards_by_id()[sid]
        if FULL.search(low):
            # R16 M8: "run a full MMSG validation of the SME scorecard" runs the full plan at once and writes the report.
            text_block(f"**{sc['name']} v{sc['version']}**: a full validation in the MMSG structure, on the standard plan (every test group, the latest data).")
            B.append(plan_block(state["plan"]))
            return _run(state, state["plan"], answer, ctx)
        if stage == "choose":
            # R16 m (M4): a validation thread opens on the scorecard's facts (Gini, PSI, last validation), then the plan.
            try:
                from backend.scorecard_v5 import facts as facts_
                prior = ctx.prior(sid, "")
                for p in prior[:1]:
                    p.setdefault("overall", ((ctx.result(p["validation_id"]) or {}).get("summary") or {}).get("overall", ""))
                B.extend(facts_.facts(sid, prior)["blocks"])
            except Exception:  # noqa: BLE001 - the facts are an addition; the plan still opens
                pass
        text_block(f"**{sc['name']} v{sc['version']}** — {sc['description']}\n\nI have read the data before proposing anything. "
                   "Here is the plan I would run; tell me what to change, or say **run it**.")
        B.append(plan_block(state["plan"]))
        text_block(_questions(sid))
        answer["suggestions"] = _plan_chips(state["plan"])
        return answer

    if stage == "choose":
        text_block("Which scorecard should we validate? I can validate the retail application scorecard, the retail behavioural scorecard or the SME scorecard.")
        B.append(choose_block())
        answer["suggestions"] = [{"label": s["name"], "send": f"Validate the {s['name']}"} for s in engine.scorecards()]
        return answer

    plan = state["plan"]
    changed, said = _edit_plan(plan, t)
    wants_run = bool(RUN.search(low)) and not (changed and not re.search(r"\b(run|go ahead|proceed|execute|start|kick off|launch)\b", low))
    if changed:
        text_block("Plan updated.\n\n" + "\n".join(f"- {s}" for s in said))
        B.append(plan_block(plan))
        answer["suggestions"] = _plan_chips(plan)
        if not wants_run:
            return answer
    if wants_run:
        if not any(plan["tests"].values()):
            text_block("Every test group is switched off. Include at least one before I run.")
            answer["suggestions"] = _plan_chips(plan)
            return answer
        return _run(state, plan, answer, ctx)
    if low in ("help", "?") or not changed:
        text_block("You can change the plan (\"skip overrides\", \"only calibration and stability\", \"cut by region\", \"as of 2025-08\", "
                   "\"monitoring from 2025-05 to 2025-08\", \"set the Gini green threshold to 0.45\"), or say **run it**.")
        B.append(plan_block(plan))
        answer["suggestions"] = _plan_chips(plan)
    return answer


FULL = re.compile(r"\b(full|mmsg|complete)\b.*\bvalidat|\bvalidat\w*\b.*\b(report|mmsg|in word|word document|docx)\b", re.I)


def _run(state: dict[str, Any], plan: dict[str, Any], answer: dict[str, Any], ctx: "Context") -> dict[str, Any]:
    B = answer["blocks"]
    out = ctx.run(plan)
    state.update({"stage": "ran", "validation_id": out["validation_id"]})
    s = out["summary"]
    B.append({"type": "text", "markdown": f"The validation has run on {out['sample']['monitoring']['n']:,} monitoring observations "
                                          f"({out['sample']['monitoring']['defaults']:,} defaults) and the {out['sample']['as_of']['n']:,} observations at {plan['as_of']}. "
                                          f"Verdicts: **{s['counts']['green']} green, {s['counts']['amber']} amber, {s['counts']['red']} red** "
                                          f"({'no test is red' if not s['counts']['red'] else 'red tests need an action'}). Review the results below, then record your conclusion."})
    B.append({"type": "validation", "validation_id": out["validation_id"], "charts": list(out.get("key_charts") or engine.KEY_CHARTS)})
    # R16 M8: the MMSG validation report (Word) and the maker-checker conclusion, under every run.
    B.append({"type": "mmsg", "validation_id": out["validation_id"],
              "text": "The MMSG validation report is written: scope, data, conceptual soundness, discrimination, calibration, stability, benchmarking, "
                      "overrides, use test, findings with severity and remediation, and the conclusion. The conclusion needs a maker and a checker."})
    answer["suggestions"] = _post_chips(s)
    return answer


def _questions(sid: str) -> str:
    sc = engine.scorecards_by_id()[sid]
    qs = [f"Should the segment cut stay on **{sc['segment_options'][0].replace('_', ' ')}**, or would you rather see {', '.join(o.replace('_', ' ') for o in sc['segment_options'][1:]) or 'nothing else'}?",
          f"Do you want the as-of period at the latest, **{sc['as_of']}**, or at the last month with a closed outcome, **{sc['last_matured']}**?"]
    if sc["has_overrides"]:
        qs.append("Override tests are included. Say \"skip overrides\" if the committee does not need them.")
    return f"{len(qs)} things to settle:\n\n" + "\n".join(f"- {q}" for q in qs)


def _plan_chips(plan: dict[str, Any]) -> list[dict[str, str]]:
    sid = plan["scorecard_id"]
    sc = engine.scorecards_by_id()[sid]
    chips = [{"label": "Run the validation", "send": "Run it"}]
    if sc["has_overrides"]:
        chips.append({"label": "Skip overrides" if plan["tests"].get("overrides") else "Include overrides",
                      "send": "Skip overrides" if plan["tests"].get("overrides") else "Include overrides"})
    opts = [o for o in sc["segment_options"] if o != plan["segment_by"]]
    if opts:
        word = {v: k for k, v in SEG_WORDS.items()}.get(opts[0], opts[0])
        chips.append({"label": f"Cut by {opts[0].replace('_', ' ')}", "send": f"Cut the segments by {word}"})
    chips.append({"label": f"As of {sc['last_matured']}", "send": f"As of {sc['last_matured']}"})
    chips.append({"label": "Calibration and stability only", "send": "Only calibration and stability"})
    return chips


def _post_chips(summary: dict[str, Any]) -> list[dict[str, str]]:
    chips = [{"label": "What are the findings?", "send": "What are the findings?"}]
    if summary["counts"]["red"]:
        chips.append({"label": "Explain the red tests", "send": "Explain the red tests"})
    chips += [{"label": "What should we do?", "send": "What are the recommended actions?"},
              {"label": "Compare with the last validation", "send": "Compare with the last validation"},
              {"label": "Change the plan and rerun", "send": "Change the plan and run it again"}]
    return chips


def _after_run(state: dict[str, Any], t: str, low: str, answer: dict[str, Any], ctx: Context) -> dict[str, Any]:
    B = answer["blocks"]
    vid = state.get("validation_id")
    res = ctx.result(vid) if vid else None
    if not res:
        B.append({"type": "text", "markdown": "I cannot find the validation for this thread."})
        return answer
    secs = res["sections"]
    tests = [x for s in secs for x in s["tests"]]
    by_id = {x["id"]: x for x in tests}
    if re.search(r"again|rerun|re-run|change the plan|new plan|different (plan|window|cut)", low):
        state["stage"] = "plan"
        B.append({"type": "text", "markdown": "The plan is open again. Change what you need and say **run it**; the earlier validation stays on record."})
        B.append(plan_block(state["plan"]))
        answer["suggestions"] = _plan_chips(state["plan"])
        return answer
    if re.search(r"compare|previous|last (validation|time)|earlier", low):
        prior = ctx.prior(state["scorecard_id"], vid)
        if not prior:
            B.append({"type": "text", "markdown": "There is no earlier validation of this scorecard to compare with."})
        else:
            p = prior[0]
            pr = ctx.result(p["validation_id"]) or {}
            ptests = {x["id"]: x for s in pr.get("sections", []) for x in s["tests"]}
            rows = []
            for x in tests:
                o = ptests.get(x["id"])
                if o and o["status"] != x["status"]:
                    rows.append(f"- {x['label']}: **{o['status']}** → **{x['status']}**")
            B.append({"type": "text", "markdown": f"Compared with the validation at {p['as_of']} ({p['created']}):\n\n" + ("\n".join(rows) if rows else "No test changed colour.")})
        answer["suggestions"] = _post_chips(res["summary"])
        return answer
    for key, text in GLOSSARY.items():
        if re.search(rf"\b(what is|what does|define|meaning of|explain)\b.*\b{key}", low) or re.search(rf"\b{key}\b.*\b(mean|stand for)\b", low):
            B.append({"type": "text", "markdown": f"**{key.upper() if len(key) < 5 else key.title()}.** {text}"})
            hit = next((x for x in tests if x["id"] == key or x["id"].startswith(key)), None)
            if hit:
                B.append({"type": "text", "markdown": f"On this validation: {hit['comment']} Verdict **{hit['status']}** ({hit['threshold']})."})
            answer["suggestions"] = _post_chips(res["summary"])
            return answer
    if re.search(r"red|amber|explain|why|issues?|problems?|findings?|concerns?|wrong", low):
        want = "red" if "red" in low else "amber" if "amber" in low else None
        fs = [f for f in res["findings"] if (not want or f["status"] == want)]
        if not fs:
            B.append({"type": "text", "markdown": "No test is " + (want or "red or amber") + "."})
        else:
            B.append({"type": "text", "markdown": f"{len(fs)} test(s) need attention, red first:"})
            B.append({"type": "findings", "items": fs})
        answer["suggestions"] = _post_chips(res["summary"])
        return answer
    if re.search(r"action|recommend|next step|what should|remediat|do about", low):
        fs = res["findings"]
        if not fs:
            B.append({"type": "text", "markdown": "Every test is green, so the recommendation is to keep the scorecard in use and re-run at the next reporting date."})
        else:
            B.append({"type": "text", "markdown": "Recommended actions, in order of severity:\n\n" + "\n".join(f"{i + 1}. **{f['label']}** ({f['status']}). {f['action']}" for i, f in enumerate(fs))})
        answer["suggestions"] = _post_chips(res["summary"])
        return answer
    if re.search(r"word|docx|report|document|pack|memo|mmsg", low):
        B.append({"type": "mmsg", "validation_id": vid, "text": "The MMSG validation report (Word) for this validation, with its conclusion and the maker-checker record."})
        B.append({"type": "report", "validation_id": vid, "text": "The Word validation report is built from this validation and the review note. Download it, share it through Mail, or add it to a Playbook report with the buttons above."})
        return answer
    if re.search(r"playbook|add to report", low):
        B.append({"type": "text", "markdown": "Use **Add to report** above the thread: it asks which Playbook report to add to (or starts a validation report), then sends the results, charts and verdicts, with the Word report attached."})
        return answer
    if re.search(r"share|mail|send", low):
        B.append({"type": "text", "markdown": "Use **Share** above the thread to send this validation through CreditProbe Mail, with the Word report if you wish."})
        return answer
    if re.search(r"review|conclusion|sign[- ]?off|approve", low):
        B.append({"type": "text", "markdown": "Record the conclusion in the **Review** panel under the results: choose fit for use, fit with conditions or not fit, add your note, and mark it reviewed. The Word report carries it."})
        return answer
    s = res["summary"]
    B.append({"type": "text", "markdown": f"This validation has {s['counts']['green']} green, {s['counts']['amber']} amber and {s['counts']['red']} red tests. "
                                         "Ask me for the findings, to explain a test or a measure (\"what is PSI?\"), for the recommended actions, a comparison with the last validation, or to change the plan and rerun."})
    answer["suggestions"] = _post_chips(s)
    return answer
