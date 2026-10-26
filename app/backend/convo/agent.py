"""One conversational turn on one domain: understand -> plan -> query -> answer -> validate -> publish.

Forked from the Cockpit's analyst loop (`backend/cockpit_v4/orchestration.py`,
frozen; copied in spirit, never imported). The same discipline:

  * the model sees the domain's catalog, knowledge index and tools, and works
    through tool calls: `inspect_catalog`, `run_query` (SQL on the domain's locked
    session), `read_knowledge`, the domain's own tools (its engines), and finally
    `finalize_answer`;
  * the SQL that runs is the SQL it wrote; a refused or failed query goes back to
    it named, and it writes the replacement -- nothing here repairs a query;
  * every figure in the answer must be in this turn's evidence (validate.py); one
    correction round, then unverified sentences are removed before publishing;
  * every loop step consumes the step budget; at the last step only
    `finalize_answer` is offered;
  * action tools (those that change something: run a scenario, write a report)
    are offered only on a turn the user asked to execute.

With no model key the domain's deterministic planner produces the tool calls and
the answer, through the same dispatch and the same validation.

`Agent` is usable inline by a module that has its own thread store (What-If calls
it with its own emitter); `answer()` is the worker entry for the generic store.
"""
from __future__ import annotations

import json
import re
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable

from backend.convo import events as ev
from backend.convo import provider as prov
from backend.convo import session as sess
from backend.convo import states as st
from backend.convo import validate as val
from backend import access
from backend.v5common import ratings
from backend.v5common import emphasis
from backend.access import studio
from backend.convo import runlog
from backend.convo import identity
from backend.convo import efficiency
from backend.convo.spec import Domain, Plan, PlanStep, ToolContext, ToolResult
from backend.regulatory import crm_tool

MODEL_ROWS = 40          # rows of a result the model sees (the artifact keeps up to session.MAX_ROWS)
TABLE_ROWS = 50          # rows a published table shows
HISTORY_TURNS = 6

FINALIZE = {
    "name": "finalize_answer",
    "description": ("Publish the answer. Call exactly once, after the queries and tools that produced every figure. "
                    "`markdown` is the answer for a credit professional: lead with the direct answer, then the "
                    "explanation, with every figure taken from a result of this turn. `tables` and `charts` show "
                    "artifacts (results of run_query or tools) by artifact_id."),
    "input_schema": {"type": "object", "required": ["markdown"], "properties": {
        "markdown": {"type": "string"},
        "tables": {"type": "array", "items": {"type": "object", "required": ["artifact_id"], "properties": {
            "artifact_id": {"type": "string"}, "title": {"type": "string"},
            "columns": {"type": "array", "items": {"type": "string"}}}}},
        "charts": {"type": "array", "items": {"type": "object", "required": ["artifact_id", "x", "y"], "properties": {
            "artifact_id": {"type": "string"}, "title": {"type": "string"},
            "kind": {"type": "string", "enum": ["bar", "hbar", "line", "stacked", "grouped", "combo"]},
            "x": {"type": "string"}, "y": {"type": "array", "items": {"type": "string"}},
            "y2": {"type": "string"}}}},
        "suggestions": {"type": "array", "maxItems": 4, "items": {"type": "string"}}}}}

BUILTINS = [
    {"name": "inspect_catalog", "description": "The domain's relations, their grain and columns (with descriptions).",
     "input_schema": {"type": "object", "properties": {"relation": {"type": "string"}}}},
    {"name": "run_query", "description": ("Run one read-only DuckDB SQL query (SELECT or WITH) on the domain's "
                                          "relations. Returns an artifact_id, the columns and the rows."),
     "input_schema": {"type": "object", "required": ["sql"], "properties": {
         "sql": {"type": "string"}, "purpose": {"type": "string"}}}},
    {"name": "read_knowledge", "description": "Read a method note of this module (how a figure is made, formulas, rules).",
     "input_schema": {"type": "object", "required": ["topic"], "properties": {"topic": {"type": "string"}}}},
    {"name": "read_policy", "description": ("Read the policy in force (the active pack in Policy Docs): the regulatory "
                                            "paragraphs (the CBUAE Credit Risk Management Standards, cited as "
                                            "'CBUAE CRM Art. 7.8') and the Bank's credit policy clauses a question "
                                            "reaches, with the pack version."),
     "input_schema": {"type": "object", "required": ["question"], "properties": {"question": {"type": "string"}}}},
    {"name": "crm_breaches", "description": crm_tool.DESCRIPTION, "input_schema": crm_tool.SCHEMA},
]


def policy_context(question: str) -> dict[str, Any] | None:
    """The policy a question reaches, retrieved by the server (as the Cockpit does), or None for a question that
    names no policy topic. R7: the CBUAE CRM Standards and the Bank's clauses, from the active pack."""
    from backend.playbook_v5 import policy

    if not policy.POLICY_WORDS.search(question or ""):
        return None
    try:
        out = policy.lookup_pack(policy.active_pack_file(), question)
    except Exception:  # noqa: BLE001 - a missing pack never breaks a turn
        return None
    return out if out["regulatory"] or out["bank_clauses"] else None


def label(col: str) -> str:
    """Column name -> header (ead_sar_mn -> EAD (SAR mn))."""
    words = {"ead": "EAD", "ecl": "ECL", "pd": "PD", "lgd": "LGD", "ccf": "CCF", "id": "ID", "sar": "SAR", "mn": "mn",
             "pct": "%", "pp": "pp", "dpd": "DPD", "psi": "PSI", "iv": "IV", "woe": "WoE", "ks": "KS", "auc": "AUC",
             "ttc": "TTC", "pit": "PIT", "mev": "MEV", "gdp": "GDP", "cet1": "CET1", "rwa": "RWA", "ltv": "LTV",
             "sicr": "SICR", "ews": "EWS", "rm": "RM", "12m": "12m", "bps": "bps"}
    parts = [p for p in re.split(r"[_\s]+", str(col)) if p]
    out = [words.get(p.lower(), p.capitalize() if i == 0 else p) for i, p in enumerate(parts)]
    s = " ".join(out)
    s = re.sub(r"\bSAR mn\b", "(SAR mn)", s)
    return s or str(col)


@dataclass
class Outcome:
    blocks: list[dict[str, Any]]
    suggestions: list[dict[str, str]]
    state: dict[str, Any]
    title: str = ""
    source: str = ""
    evidence: list[dict[str, Any]] = field(default_factory=list)
    validation: dict[str, Any] = field(default_factory=dict)
    terminal: str = st.COMPLETED


class Agent:
    def __init__(self, domain: Domain, *, thread: dict[str, Any], scope: dict[str, Any], state: dict[str, Any],
                 question: str, emitter, mode: str = "ask", user: dict[str, Any] | None = None,
                 history: list[dict[str, Any]] | None = None, sink: Callable[[str, str, dict], None] | None = None,
                 provider: prov.Provider | None = None):
        self.domain = domain
        self.thread = thread
        self.scope = scope
        self.state = json.loads(json.dumps(state or {}))
        self.question = question
        from backend.convo.trace import tee
        self.em = tee(emitter)
        self.mode = mode
        self.user = user or {}
        self.history = history or []
        self.sink = sink
        self.provider = provider if provider is not None else prov.default()
        # Admin -> AI Studio / Agent Operations: a module's kill switch falls back to planner mode (PLAN_R5 A3).
        if provider is None and self.provider is not None and studio.killed(domain.key):
            self.provider = None
        # AI Studio's live model for the module (approved through maker-checker), on the model path only.
        if provider is None and isinstance(self.provider, prov.Anthropic) and studio.model(domain.key):
            self.provider = prov.Anthropic()
            self.provider.model_override = studio.model(domain.key)
        # The caller's data access policy (PLAN_R5 A1): every relation and tool result of the turn is filtered.
        self.policy = access.for_user(self.user) if self.user.get("username") else access.current()
        self.artifacts: dict[str, dict[str, Any]] = {}
        self.evidence = val.Evidence()
        self.evidence.add(question)
        self.tool_blocks: list[dict[str, Any]] = []
        self.state_updates: dict[str, Any] = {}
        self.title = ""
        self.trace: list[dict[str, Any]] = []
        self._n = {"q": 0, "t": 0}
        self.session: sess.Session | None = None

    # ------------------------------------------------------------ context
    def ctx(self) -> ToolContext:
        return ToolContext(domain=self.domain, thread=self.thread, state={**self.state, **self.state_updates},
                           scope=self.scope, user=self.user, question=self.question, execute=self.mode == "execute")

    def tools_for_model(self, final_only: bool = False) -> list[dict[str, Any]]:
        if final_only:
            return [FINALIZE]
        out = list(BUILTINS)
        off = studio.disabled_tools(self.domain.key)   # AI Studio: tools the bank switched off for this module
        for t in self.domain.tools:
            if (t.action and self.mode != "execute") or t.name in off:
                continue
            out.append({"name": t.name, "description": t.description, "input_schema": t.input_schema})
        out.append(FINALIZE)
        return out

    def catalog_text(self) -> str:
        lines = []
        for r in self.session.catalog():
            cols = ", ".join(f"{c['name']} {c['type']}" + (f" ({c['description']})" if c["description"] else "")
                             for c in r["columns"])
            lines.append(f"- {r['relation']} ({r['rows']:,} rows; grain: {r['grain'] or 'one row per record'}): "
                         f"{r['description']}\n  columns: {cols}")
        return "\n".join(lines)

    def system(self) -> str:
        d = self.domain
        topics = ", ".join(sorted(d.knowledge)) or "none"
        brief = d.state_brief({**self.state, **self.state_updates}) or "No earlier result in this thread."
        acts = [t.name for t in d.tools if t.action]
        if acts:
            mode = (f"The user asked to EXECUTE in this turn: the action tools ({', '.join(acts)}) are available."
                    if self.mode == "execute" else
                    f"This is a question turn: the action tools ({', '.join(acts)}) are NOT available. Never claim "
                    "you ran or changed anything. If the user describes a change, use the reading/proposal tools to "
                    "restate it and say it runs when they press Execute or say 'run it'.")
        else:
            mode = ""
        who = identity.charter_line()   # PLAN_R9 G6: every v5 assistant describes CreditProbe the same way
        if efficiency.enabled():   # Round E: cacheable head (digest, worked examples) | per-question tail
            return self._system_efficient(mode, topics, brief, who)
        return (f"{d.charter}\n\n"
                f"You are working in CreditProbe's {d.title} module on {d.scope_label(self.scope)}.\n\n"
                + (f"{who}\n\n" if who else "") +
                "How you work (the Cockpit's discipline): understand the question; plan which relations, notes and "
                "tools answer it; query; then call finalize_answer once. Every figure you write must come from a "
                "run_query result, a tool result or a knowledge note of THIS turn -- never estimate, recall or "
                "invent a number; the server checks every figure against the results and removes any it cannot "
                "find. Prefer one or two well-aimed queries over many. If the data cannot answer, say exactly what "
                "is missing. Write for a bank's credit committee: direct, specific, no filler, no disclaimers about "
                "being an AI, no notes about provenance. Use markdown (short paragraphs, bullets, bold for the key "
                "figure). " + emphasis.RULE + " Money is in SAR millions unless a column says otherwise. Show a table or chart when the "
                "answer is a list or a comparison.\n\n"
                f"{mode}\n\nRelations (DuckDB, SQL SELECT only):\n{self.catalog_text()}\n\n"
                f"Knowledge notes (read_knowledge): {topics}\n\nThread context: {brief}"
                + self._policy_block()
                + studio.addendum(d.key))

    def _system_efficient(self, mode: str, topics: str, brief: str, who: str) -> str:
        d = self.domain
        ex = efficiency.hooks(d.key).examples
        head = (f"{d.charter}\n\n"
                f"You are working in CreditProbe's {d.title} module.\n\n"
                + (f"{who}\n\n" if who else "") +
                "How you work: plan which relations, notes and tools answer the question; call them (several in one "
                "step when they do not depend on each other); then call finalize_answer once. Every figure you write "
                "must come from a run_query result, a tool result or a knowledge note of THIS turn -- never estimate, "
                "recall or invent a number; the server checks every figure and removes any it cannot find. Prefer one "
                "or two well-aimed calls over many; a tool result shows at most 20 rows with a summary of the rest. "
                "If the data cannot answer, say exactly what is missing. Write for a bank's credit committee: direct, "
                "specific, no filler, no disclaimers about being an AI, no notes about provenance. Use markdown (short "
                "paragraphs, bullets, bold for the key figure). " + emphasis.RULE + " Money is in SAR millions unless "
                "a column says otherwise. Show a table or chart when the answer is a list or a comparison.\n\n"
                f"{mode}\n\nRelations (DuckDB, SQL SELECT only; inspect_catalog gives the types):\n"
                f"{efficiency.catalog_digest(self.session.catalog()) if self.session is not None else self.catalog_text()}\n\nKnowledge notes (read_knowledge): {topics}"
                + (f"\n\nWorked examples:\n{ex}" if ex else "") + studio.addendum(d.key))
        _, older = efficiency.history_split(self.history, answer_text)
        tail = (f"This turn is on {d.scope_label(self.scope)}.\n\nThread context: {brief}"
                + (f"\n\n{older}" if older else "") + self._policy_block())
        return head + efficiency.BREAK + tail

    def _policy_block(self) -> str:
        found = policy_context(self.question)
        crm = ""
        if crm_tool.is_crm_question(self.question):
            crm = ("\n\nCompliance: this question asks about breaches of the CBUAE Credit Risk Management Standards. "
                   "Call crm_breaches (filter by article, book or entity as the question does) and answer from its "
                   "result: each breach by its article id and title in bold, the entity, measured vs required, EAD/ECL.")
        if not found:
            return ("\n\nPolicy: read_policy returns the policy in force (regulatory paragraphs of the CBUAE Credit "
                    "Risk Management Standards, and the Bank's clauses) when a question asks what a policy or "
                    "regulation says; crm_breaches lists the exposures that breach the Standards." + crm)
        self.evidence.add(json.dumps(found, ensure_ascii=False))
        return ("\n\nPolicy in force, retrieved for this question (active pack " + str(found["pack_version"]) + "). "
                "Answer what the policy or regulation says from these paragraphs only, quoting each by its id and "
                "title in bold (e.g. **CBUAE CRM Art. 7.8 DPD indicator**) and naming the pack version; "
                "what they do not cover, say is not in it:\n" + json.dumps(found, ensure_ascii=False) + crm)

    def messages(self) -> list[dict[str, Any]]:
        msgs: list[dict[str, Any]] = []
        eff = efficiency.enabled()   # Round E: the last 2 turns verbatim; earlier ones are one line each in the system tail
        recent = efficiency.history_split(self.history, answer_text)[0] if eff else self.history[-HISTORY_TURNS:]
        for t in recent:
            q = str(t.get("question") or "").strip()
            a = answer_text(t.get("answer") or {})[:efficiency.ANSWER_CHARS if eff else 1500]
            if q and a:
                msgs.append({"role": "user", "content": q})
                msgs.append({"role": "assistant", "content": a})
        msgs.append({"role": "user", "content": self.question})
        return msgs

    # ------------------------------------------------------------ tools
    def _aid(self, kind: str) -> str:
        self._n[kind] += 1
        return f"{kind}{self._n[kind]}"

    def dispatch(self, name: str, args: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        """Run one tool. Returns (what the model sees, is_error)."""
        t0 = time.monotonic()
        stage = "querying" if name in ("run_query", "inspect_catalog") else "planning" if name == "read_knowledge" else "querying"
        self.em.stage(stage)
        tool = self.domain.tool(name)
        msg = (tool.message if tool and tool.message else
               {"run_query": "Querying " + (str(args.get("purpose") or "")[:80] or "the data"),
                "inspect_catalog": "Reading the catalog", "read_knowledge": f"Reading the note on {args.get('topic', '')}",
                "read_policy": "Reading the policy in force",
                "crm_breaches": "Checking the books against the CBUAE CRM Standards"}
               .get(name, name.replace("_", " ")))
        self.em.emit(ev.TOOL_STARTED, self.em.open_stage, "running", msg, {"tool": name})
        try:
            out = self._run_tool(name, args, tool)
            err = False
        except sess.QueryRefused as e:
            out, err = {"error": str(e), "failed_check": e.check}, True
        except Exception as e:  # noqa: BLE001 - a tool failure goes back to the author, named
            out, err = {"error": f"{type(e).__name__}: {str(e)[:300]}"}, True
        ms = int((time.monotonic() - t0) * 1000)
        self.trace.append({"tool": name, "args": _short(args), "ms": ms, "ok": not err,
                           **({"error": out.get("error")} if err else {}),
                           **({"artifact_id": out.get("artifact_id")} if out.get("artifact_id") else {})})
        self.em.emit(ev.TOOL_FAILED if err else ev.TOOL_COMPLETED, self.em.open_stage, "failed" if err else "completed",
                     (out.get("error", "")[:200] if err else msg), {"tool": name, "ms": ms})
        return out, err

    def _run_tool(self, name: str, args: dict[str, Any], tool) -> dict[str, Any]:
        if name == "inspect_catalog":
            cat = self.session.catalog()
            rel = str(args.get("relation") or "")
            return {"relations": [c for c in cat if not rel or c["relation"] == rel]}
        if name == "run_query":
            res = self.session.query(str(args.get("sql") or ""))
            aid = self._aid("q")
            art = {"kind": "query", "sql": args.get("sql"), "purpose": args.get("purpose", ""), **res}
            self._keep(aid, art)
            self.evidence.add_rows(res["rows"])
            return {"artifact_id": aid, "columns": res["columns"], "row_count": res["row_count"],
                    "truncated": res["truncated"], "rows": res["rows"][:MODEL_ROWS],
                    **({"note": f"first {MODEL_ROWS} of {res['row_count']} rows shown"} if res["row_count"] > MODEL_ROWS else {})}
        if name == "read_policy":
            from backend.playbook_v5 import policy

            out = policy.lookup_pack(policy.active_pack_file(), str(args.get("question") or self.question))
            self.evidence.add(json.dumps(out, ensure_ascii=False))
            return out
        if name == "crm_breaches":
            out = crm_tool.run(dict(args or {}))
            if self.policy.row_restricted:   # never rows outside the caller's policy (PLAN_R5 A1)
                out["breaches"] = access.filter_rows(out["breaches"], self.policy)
            aid = self._aid("t")
            self._keep(aid, {"kind": "tool", "tool": name, "summary": crm_tool.summary_line(out), "data": {},
                             "columns": list(out["breaches"][0].keys()) if out["breaches"] else [],
                             "rows": out["breaches"]})
            self.evidence.add(json.dumps({k: v for k, v in out.items() if k != "breaches"}, ensure_ascii=False))
            self.evidence.add_rows(out["breaches"])
            self.evidence.add_rows(out["checks"])
            return {"artifact_id": aid, **out}
        if name == "read_knowledge":
            topic = str(args.get("topic") or "").strip()
            key = topic if topic in self.domain.knowledge else next(
                (k for k in self.domain.knowledge if k.lower() in topic.lower() or topic.lower() in k.lower()), "")
            if not key:
                return {"error": f"No note on '{topic}'. Notes: {', '.join(sorted(self.domain.knowledge))}."}
            text = self.domain.knowledge[key]
            self.evidence.add(text)
            return {"topic": key, "text": text}
        if tool is None:
            raise ValueError(f"'{name}' is not a tool of the {self.domain.title} domain.")
        if tool.name in studio.disabled_tools(self.domain.key):
            raise PermissionError(f"{name} is switched off for this module in AI Studio.")
        if tool.action and self.mode != "execute":
            raise PermissionError(f"{name} changes something and runs only when the user asks to execute.")
        r: ToolResult = tool.fn(self.ctx(), dict(args or {}))
        if self.policy.row_restricted:   # a tool never returns rows outside the caller's policy (PLAN_R5 A1)
            r.rows = access.filter_rows(r.rows, self.policy)
            r.data = access.filter_json(r.data, self.policy)
            r.blocks = access.filter_json(r.blocks, self.policy)
        aid = self._aid("t")
        self._keep(aid, {"kind": "tool", "tool": name, "summary": r.summary, "data": r.data,
                         "columns": list(r.rows[0].keys()) if r.rows else [], "rows": r.rows or []})
        self.evidence.add(r.data)
        self.evidence.add(r.summary)
        self.evidence.add_rows(r.rows)
        for b in r.blocks:
            self.evidence.add(b)
        self.tool_blocks.extend(r.blocks)
        if r.state:
            self.state_updates.update(r.state)
        if r.title:
            self.title = r.title
        out = {"artifact_id": aid, "summary": r.summary, "data": r.data}
        if r.rows:
            out["columns"] = list(r.rows[0].keys())
            out["rows"] = r.rows[:MODEL_ROWS]
        return out

    def _keep(self, aid: str, art: dict[str, Any]) -> None:
        self.artifacts[aid] = art
        if self.sink:
            try:
                self.sink(aid, art["kind"], art)
            except Exception:  # noqa: BLE001 - the evidence copy is best effort; the answer keeps its own
                pass

    # ------------------------------------------------------------ the loop
    def run(self) -> Outcome:
        from backend.convo import telemetry
        clock = runlog.StageClock(self.em)
        self.em, t0, outcome, out = clock, time.monotonic(), "completed", None
        run_id = telemetry.new_run_id()   # the same id on the Agent Operations row and on every model call of the turn
        try:
            with access.use(self.policy), telemetry.use(run_id=run_id, module=studio.module_of(self.domain.key),
                                                          domain=self.domain.key,
                                                          thread_id=str((self.thread or {}).get("thread_id") or (self.thread or {}).get("id") or "")):
                out = self._run()
            if out.source == "deterministic" and self.provider is None and studio.killed(self.domain.key):
                outcome = "planner (kill switch)"
            return out
        except Exception as e:  # noqa: BLE001
            outcome = f"failed: {type(e).__name__}"
            raise
        finally:
            self.em = clock._inner  # noqa: SLF001
            runlog.record(run_id=run_id, module=studio.module_of(self.domain.key), domain=self.domain.key,
                          user=self.user.get("username") or self.policy.username or "", question=self.question[:500],
                          mode=self.mode, steps=clock.close(), tools=[t.get("tool") or t.get("name") for t in self.trace
                                                                      if isinstance(t, dict)],
                          source=(out.source if out else ""), model=(self.provider.model() if self.provider else "planner"),
                          latency_ms=round((time.monotonic() - t0) * 1000), outcome=outcome,
                          figures_removed=len((out.validation.get("removed") if out else None) or []),
                          policy=self.policy.fingerprint)

    def _run(self) -> Outcome:
        self.em.stage("understanding", f"Reading the {self.domain.title} data")
        self.session = sess.open_session(self.domain, self.scope, self.policy)
        if self.provider is None:
            final, source = self._deterministic(), "deterministic"
            final = self._validate_final(final, correct=None)
        elif efficiency.engine_first(self.domain.key, self.question, self.ctx()):
            final, source = self._engine_first()   # Round E: the planner's calls, then one writing call
        else:
            final, source = self._model_loop(), "model"
        return self._publish(final, source)

    def _deterministic(self) -> dict[str, Any]:
        self.em.stage("planning", "Planning the analysis")
        if crm_tool.is_crm_question(self.question):  # R7 C3: every assistant answers a compliance question
            out, err = self.dispatch("crm_breaches", crm_tool.parse(self.question))
            self.em.stage("answering")
            if err:
                return {"markdown": "The CBUAE CRM checks could not run: " + str(out.get("error", ""))}
            tables = [{"artifact_id": out["artifact_id"], "title": "Breaches of the CBUAE CRM Standards"}] \
                if out["breaches"] else []
            return {"markdown": crm_tool.markdown(out), "tables": tables}
        if self.domain.planner is None:
            return {"markdown": "Ask about the data in this module; the assistant model is not available here."}
        plan: Plan = self.domain.planner(self.question, self.ctx())
        results = []
        for step in plan.steps:
            out, err = self.dispatch(step.tool, step.args)
            results.append({"tool": step.tool, "args": step.args, "out": out, "error": err,
                            "artifact": self.artifacts.get(out.get("artifact_id", ""))})
        self.em.stage("answering")
        return plan.write(results)

    def _engine_first(self) -> tuple[dict[str, Any], str]:
        """Round E: a question type the planner knows. The engine runs the planner's calls (no model), the planner's
        writer drafts from the results, then ONE model call writes the answer from the results and the draft. A model
        text with a figure that is not in the results, or that drops a figure of the draft's headline, is not
        published: the engine's draft is."""
        self.em.stage("planning", "Planning the analysis")
        plan: Plan = self.domain.planner(self.question, self.ctx())
        results = []
        for step in plan.steps:
            out, err = self.dispatch(step.tool, step.args)
            results.append({"tool": step.tool, "args": step.args, "out": out, "error": err,
                            "artifact": self.artifacts.get(out.get("artifact_id", ""))})
        self.em.stage("answering")
        draft = self._validate_final(plan.write(results), correct=None)
        if not plan.steps or not self.artifacts:
            return draft, "deterministic"
        system = efficiency.writer_system(self.domain.charter, self.domain.scope_label(self.scope),
                                          emphasis.RULE + studio.addendum(self.domain.key))
        msgs = [{"role": "user", "content": efficiency.writer_message(self.question, results, draft.get("markdown", ""))}]
        self.em.emit(ev.MODEL_REQUESTED, self.em.open_stage, "running", "Writing the answer",
                     {"purpose": efficiency.WRITE_PURPOSE})
        try:
            reply = self.provider.step(efficiency.WRITE_PURPOSE, system, msgs, [FINALIZE])
        except prov.ProviderFailure as e:
            self.trace.append({"model": "failed", "error": str(e), "fallback": "engine draft"})
            return draft, "deterministic"
        self.em.emit(ev.MODEL_RESPONSE, self.em.open_stage, "completed", "Model replied",
                     {"tools": [u["name"] for u in reply.tool_uses()], **reply.usage})
        use = next((u for u in reply.tool_uses() if u["name"] == "finalize_answer"), None)
        text = str(((use or {}).get("input") or {}).get("markdown") or (reply.text() if use is None else "")).strip()
        bad = self.evidence.unverified(text) if text else ["(no answer)"]
        dropped = efficiency.keeps_headline(draft.get("markdown", ""), text) if text else []
        if bad or dropped:
            self.trace.append({"engine_first": "model text not published", "unverified": bad, "dropped": dropped})
            return draft, "deterministic"
        sugg = [s for s in ((use or {}).get("input") or {}).get("suggestions") or [] if isinstance(s, str)] \
            or draft.get("suggestions") or []
        final = {"markdown": text, "tables": draft.get("tables") or [], "charts": draft.get("charts") or [],
                 "suggestions": sugg}
        return self._validate_final(final, correct=None), "model"

    def _model_loop(self) -> dict[str, Any]:
        system = self.system()
        msgs = self.messages()
        corrected = False
        final: dict[str, Any] | None = None
        self.em.stage("planning", "Planning the analysis")
        for step in range(self.domain.max_steps):
            last = step == self.domain.max_steps - 1
            purpose = "FINAL_ANSWER" if last else ("ANSWER_CORRECTION" if corrected and final is None and step else "ANALYSIS_ACTION")
            self.em.emit(ev.MODEL_REQUESTED, self.em.open_stage, "running",
                         "Writing the answer" if last else "Preparing the next action", {"purpose": purpose})
            try:
                reply = self.provider.step(purpose, system, msgs, self.tools_for_model(final_only=last))
            except prov.ProviderFailure as e:
                self.trace.append({"model": "failed", "error": str(e)})
                return self._fallback_answer(str(e))
            self.em.emit(ev.MODEL_RESPONSE, self.em.open_stage, "completed", "Model replied",
                         {"tools": [u["name"] for u in reply.tool_uses()], **reply.usage})
            msgs.append({"role": "assistant", "content": reply.content})
            uses = reply.tool_uses()
            if not uses:
                text = reply.text()
                cand = {"markdown": text or "I could not form an answer from the data."}
                return self._validate_final(cand, correct=None)
            results = []
            done: dict[str, Any] | None = None
            for u in uses:
                if u["name"] == "finalize_answer":
                    self.em.stage("validating")
                    cand = dict(u.get("input") or {})
                    problems = self._problems(cand)
                    if problems and not corrected:
                        corrected = True
                        results.append({"type": "tool_result", "tool_use_id": u["id"], "is_error": True,
                                        "content": json.dumps(problems)})
                        self.em.emit(ev.ANSWER_VALIDATED, "validating", "failed", "Correcting figures not found in the results",
                                     {"problems": problems})
                    else:
                        done = self._validate_final(cand, correct=problems)
                        results.append({"type": "tool_result", "tool_use_id": u["id"], "content": "published"})
                    continue
                out, err = self.dispatch(u["name"], dict(u.get("input") or {}))
                if efficiency.enabled():   # Round E: 20 rows and a summary of the whole result reach the model
                    art = self.artifacts.get(str(out.get("artifact_id") or "")) or {}
                    view, summ = efficiency.model_view(out, art.get("rows") if out.get("rows") is not None else None)
                    if summ:
                        self.evidence.add(summ)
                    content = efficiency.tool_content(view)
                else:
                    content = json.dumps(out, default=str)[:24000]
                results.append({"type": "tool_result", "tool_use_id": u["id"], "is_error": err, "content": content})
            if done is not None:
                return done
            msgs.append({"role": "user", "content": results})
        return self._fallback_answer("The step budget ran out before an answer was written.")

    def _fallback_answer(self, reason: str) -> dict[str, Any]:
        """The model failed or ran out of steps: publish what was computed, never an invented sentence."""
        self.trace.append({"fallback": reason})
        if self.domain.planner is not None and not self.artifacts:
            return self._validate_final(self._deterministic(), correct=None)
        tables = [{"artifact_id": a, "title": (v.get("purpose") or v.get("summary") or "")[:120]}
                  for a, v in self.artifacts.items() if v.get("rows")][:3]
        return {"markdown": "Here are the results computed for this question." if tables else
                "I could not complete this answer. Ask again, or narrow the question.", "tables": tables}

    def _problems(self, cand: dict[str, Any]) -> dict[str, Any]:
        bad = self.evidence.unverified(str(cand.get("markdown") or ""))
        refs = []
        for t in (cand.get("tables") or []) + (cand.get("charts") or []):
            a = self.artifacts.get(str(t.get("artifact_id")))
            if a is None:
                refs.append(f"{t.get('artifact_id')} is not an artifact of this turn")
                continue
            cols = set(a.get("columns") or [])
            for c in (t.get("columns") or []) + ([t["x"]] if t.get("x") else []) + list(t.get("y") or []) + \
                     ([t["y2"]] if t.get("y2") else []):
                if c not in cols:
                    refs.append(f"{c} is not a column of {t.get('artifact_id')}")
        out: dict[str, Any] = {}
        if bad:
            out["unverified_figures"] = bad
            out["instruction"] = ("These figures are not in any result of this turn. Query them, or remove them; "
                                  "then call finalize_answer again.")
        if refs:
            out["bad_references"] = refs
        return out

    def _validate_final(self, cand: dict[str, Any], correct) -> dict[str, Any]:
        self.em.stage("validating")
        md = str(cand.get("markdown") or "").strip()
        bad = self.evidence.unverified(md)
        removed = []
        if bad:
            md2 = val.strip_unverified(md, bad)
            removed = bad
            md = md2 or "The figures for this answer could not be confirmed from the data; ask again or narrow the question."
        cand = {**cand, "markdown": md}
        cand["tables"] = [t for t in (cand.get("tables") or []) if self._ref_ok(t)]
        cand["charts"] = [c for c in (cand.get("charts") or []) if self._ref_ok(c)]
        cand["_removed"] = removed
        self.em.emit(ev.ANSWER_VALIDATED, "validating", "completed",
                     "Every figure checked" if not removed else "Figures not found in the results were removed",
                     {"removed": removed})
        return cand

    def _ref_ok(self, t: dict[str, Any]) -> bool:
        a = self.artifacts.get(str(t.get("artifact_id")))
        if a is None or not a.get("rows"):
            return False
        cols = set(a.get("columns") or [])
        need = list(t.get("columns") or []) + ([t["x"]] if t.get("x") else []) + list(t.get("y") or []) + \
            ([t["y2"]] if t.get("y2") else [])
        return all(c in cols for c in need)

    # ------------------------------------------------------------ publish
    def _publish(self, final: dict[str, Any], source: str) -> Outcome:
        self.em.stage("publishing")
        blocks: list[dict[str, Any]] = [{"type": "answer", "markdown": emphasis.emphasise(final.get("markdown", "")), "source": source,
                                         **({"model": self.provider.model()} if self.provider else {})}]
        for t in final.get("tables") or []:
            a = self.artifacts[t["artifact_id"]]
            cols = t.get("columns") or a["columns"]
            blocks.append({"type": "table", "title": t.get("title") or "", "artifact_id": t["artifact_id"],
                           "columns": [{"key": c, "label": label(c)} for c in cols],
                           # PLAN_R6 E3: a table by rating grade reads AAA to D, never by value
                           "rows": ratings.order_table(cols, [{c: r.get(c) for c in cols} for r in a["rows"][:TABLE_ROWS]]),
                           "row_count": len(a["rows"])})
        for c in final.get("charts") or []:
            a = self.artifacts[c["artifact_id"]]
            keep = [c["x"], *c.get("y", []), *([c["y2"]] if c.get("y2") else [])]
            blocks.append({"type": "chart", "title": c.get("title") or "", "kind": c.get("kind") or "bar",
                           "x": c["x"], "y": list(c.get("y") or []), "y2": c.get("y2") or "",
                           "labels": {k: label(k) for k in keep},
                           "rows": ratings.order_chart_rows(c["x"], [{k: r.get(k) for k in keep} for r in a["rows"][:60]])})
        blocks.extend(self.tool_blocks)
        sugg = [{"label": s[:60], "send": s} for s in (final.get("suggestions") or []) if isinstance(s, str) and s.strip()][:4]
        if not sugg:
            sugg = self.domain.suggestions(self.scope, {**self.state, **self.state_updates})[:4]
        evidence = [{"artifact_id": a, "kind": v["kind"], "sql": v.get("sql"), "tool": v.get("tool"),
                     "purpose": v.get("purpose") or v.get("summary") or "", "row_count": len(v.get("rows") or [])}
                    for a, v in self.artifacts.items()]
        return Outcome(blocks=blocks, suggestions=sugg, state=self.state_updates, title=self.title, source=source,
                       evidence=evidence, validation={"removed": final.get("_removed") or []})


def answer_text(answer: dict[str, Any]) -> str:
    """The prose of a published answer (for the model's memory of the thread)."""
    parts = []
    for b in answer.get("blocks") or []:
        for k in ("markdown", "text"):
            if isinstance(b.get(k), str) and b[k].strip():
                parts.append(b[k].strip())
        if b.get("type") in ("understood", "proposal"):
            parts.extend(s.get("restatement", "") for s in b.get("steps") or [])
    return "\n\n".join(p for p in parts if p)


def _short(args: dict[str, Any]) -> dict[str, Any]:
    return {k: (v[:600] if isinstance(v, str) else v) for k, v in (args or {}).items()}


# ------------------------------------------------------------------ worker entry (generic store)

def answer(store, run_id: str, registry: dict[str, Domain]) -> None:
    run = store.run(run_id)
    thread = store.thread(run["thread_id"])
    from backend.convo.trace import TraceRecorder
    em = TraceRecorder(f"tr-{run_id}", inner=ev.Emitter(store, run_id))
    em.emit(ev.RUN_STARTED, "accepted", "running", "Started")
    domain = registry.get(thread["domain"])
    try:
        if domain is None:
            raise KeyError(f"Unknown domain {thread['domain']}")
        agent = Agent(domain, thread=thread, scope=thread["scope"], state=thread["state"], question=run["question"],
                      emitter=em, mode=run.get("mode") or "ask", history=store.turns(thread["thread_id"]),
                      user={"username": run.get("owner") or ""},
                      sink=lambda aid, kind, payload: store.put_artifact(run_id, aid, kind, payload))
        out = agent.run()
        ans = {"blocks": out.blocks, "suggestions": out.suggestions, "question_display": run["question"],
               "evidence": out.evidence, "validation": out.validation, "planner": prov.describe(), "source": out.source,
               "tools": agent.trace}
        ans["trace"] = em.finish()
        state = {**thread["state"], **out.state}
        title = out.title or (run["question"][:90] if thread["title"] in ("", "New thread") else None)
        store.save_thread(thread["thread_id"], state=state, title=title)
        store.append_turn(thread["thread_id"], run_id, run["question"], ans)
        em.close()
        em.emit(ev.ANSWER_READY, "publishing", "completed", "Answer ready", {"state": out.terminal})
        store.settle(run_id, out.terminal, ans)
    except Exception as e:  # noqa: BLE001 - the turn fails visibly, the thread is unchanged
        ans = {"blocks": [{"type": "error", "text": "Something went wrong while answering; the thread is unchanged."}],
               "suggestions": [], "question_display": run["question"], "trace": em.finish(failed=True)}
        store.append_turn(thread["thread_id"], run_id, run["question"], ans)
        em.close()
        em.emit(ev.RUN_FAILED, "", "failed", "The turn failed",
                {"error": type(e).__name__, "trace": traceback.format_exc()[-1500:]})
        store.settle(run_id, st.FAILED, ans, error_code="CONVO_INTERNAL", error=str(e)[:500])


__all__ = ["Agent", "Outcome", "answer", "answer_text", "label", "PlanStep", "Plan"]
