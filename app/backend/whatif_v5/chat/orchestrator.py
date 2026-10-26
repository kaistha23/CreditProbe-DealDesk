"""One What-If turn: understand -> plan -> compute -> attribute -> assess -> validate -> publish.

Forked from the Cockpit's orchestration loop (`backend/cockpit_v4/orchestration.py`,
frozen, copied in spirit, never imported) and restricted to the What-If domain:
the only tools are describe_scope, interpret_statement, run_scenario,
compare_models, assess_likelihood and write_commentary, and every one reads
the What-If domain (or the Early Warning cohort it was handed) and nothing else.

The planner is deterministic (the statement reader decides the intent and the
shocks); the assistant model, when the Mac's key is present, writes the
brainstorm replies and the commentary and reads statements the reader could
not, and everything it returns is validated before it is used.

PLAN_R4 A1: questions (data, distributions, history, MEVs, models, likelihood,
how a figure is made) are answered by the forked Cockpit agent on the What-If
domain (backend/convo, `convo_domain.DOMAIN`). A scenario statement becomes a
PROPOSAL (structured shocks restated, nothing run); it executes only when the
user presses Execute scenario (`::execute`) or writes "execute" / "run it",
and the model (Delta or XGBoost) is asked then if not chosen. "Rerun with the
other model" and "compare both models" are explicit run requests.

Thread state (JSON on the thread):
  scenario   the current scenario (steps), or None
  method     "delta" | "xgboost" | None (asked before the first run)
  pending    a proposed scenario waiting for Execute (and the model choice)
  execute_requested  Execute was pressed and the model question is open
  history    earlier scenarios (for "undo")
  last       {"method", "run_key"} of the last result
"""
from __future__ import annotations

import functools
import json
import re
import time
import traceback
from typing import Any

from backend.v5common import emphasis
from backend.whatif_v5 import cohorts, likelihood
from backend.whatif_v5.chat import commentary as cm
from backend.whatif_v5.chat import events as ev
from backend.convo import provider as convo_provider
from backend.whatif_v5.chat import language, library, provider
from backend.whatif_v5.chat import states as st
from backend.whatif_v5.chat.cohort import summary as cohort_summary
from backend.whatif_v5.chat import compose
from backend.whatif_v5.domain import mev, store as dstore
from backend.v5common import ratings
from backend.whatif_v5.models import runner
from backend.whatif_v5.models.scenario import DRIVER_LABELS, DRIVERS, Scenario, ShockError, Step, describe_shocks, parse_shocks, Scope

METHOD_NAMES = {"delta": "Delta method", "xgboost": "XGBoost"}
EXECUTE_RE = re.compile(r"^\s*(::execute\b|execute\b|run (it|this|that|the (scenario|proposal|shocks?))\b|run now\b|"
                        r"go ahead\b|yes,? (run|execute|go)\b|please (run|execute)\b|do it\b)|\bexecute (it|this|the scenario)\b",
                        re.I)
QUESTION_RE = re.compile(r"^\s*(why|how(?! likely)|explain|which|who|where|when|is|are|does|do|did|can|could|should|"
                         r"would|tell me|show me|list|describe|give me|what(?!\s+(if|happens|would happen)\b))\b", re.I)
OTHER = {"delta": "xgboost", "xgboost": "delta"}


class Refusal(ValueError):
    """A turn that cannot be answered as asked, with a reason the user can act on."""


@functools.lru_cache(maxsize=4)
def vocabulary(domain: str) -> dict[str, Any]:
    f = dstore.frame(domain)
    return {"segments": sorted(f["segment"].astype(str).unique()),
            "subsegments": sorted(f["subsegment"].astype(str).unique())}


def read_ctx(thread: dict, state: dict) -> dict[str, Any]:
    v = vocabulary(thread["domain"])
    return {"domain": thread["domain"], "segments": v["segments"], "subsegments": v["subsegments"],
            "labels": runner.LABELS[thread["domain"]], "has_scenario": bool(state.get("scenario") or state.get("pending"))}


def _text(md: str) -> dict:
    return {"type": "text", "markdown": md}


def understood_block(steps: list[Step], reading_notes: list[str], unread: list[str], method: str | None,
                     population: str, kind: str = "") -> dict:
    labels = None
    return {"type": "understood", "kind": kind, "population": population,
            "steps": [{"restatement": s.restatement, "scope": s.scope.to_dict(), "shocks": s.shocks.to_dict()} for s in steps],
            "assumptions": reading_notes, "unread": unread,
            "method": METHOD_NAMES.get(method or "", ""), "_": labels}


def _fmt_pct(v: float) -> str:
    return f"{v:+.1f}%"


def collateral_blocks(res: dict, lab: dict, head: str) -> list[dict]:
    d = res["distribution"]
    rows = res["by_segment"]
    worst = rows[0] if rows else None
    seg = lab["segment"].lower()
    md = [head, "\n\n"]
    if not res["observations"]:
        md.append("The book carries no collateral value history in scope, so the size below comes from real estate prices.")
    else:
        wq = min(rows, key=lambda r: r["worst_qoq_change_pct"])
        md.append(f"Over {len(res['periods']) - 1} quarters, the collateral value behind the {lab['book'].lower()} book (the same "
                  f"exposures, quarter on quarter) moved by a median of **{_fmt_pct(d['median'])}** a quarter by {seg}, "
                  f"between {_fmt_pct(d['p5'])} (5th percentile) and {_fmt_pct(d['p95'])} (95th); the worst single quarter "
                  f"was {_fmt_pct(wq['worst_qoq_change_pct'])} ({wq['segment']}).")
        if worst and worst["worst_4q_change_pct"] < 0:
            md.append(f" The weakest {seg}, **{worst['segment']}**, lost {_fmt_pct(worst['worst_4q_change_pct'])} over its "
                      "worst four quarters.")
        elif worst:
            md.append(f" No {seg} lost value over any four quarters: the weakest four-quarter change was "
                      f"{_fmt_pct(worst['worst_4q_change_pct'])} ({worst['segment']}), so the book's own history is too "
                      "mild to size a stress on.")
    md.append(f"\n\nA decent, severe-but-plausible collateral shock is **{res['recommended_pct']:g}%**: {res['basis']}, "
              "rounded up to the next 5% and kept within 10% to 40%.")
    cols = [{"key": "segment", "label": lab["segment"]}, {"key": "avg_qoq_change_pct", "label": "Average quarterly change (%)"},
            {"key": "worst_qoq_change_pct", "label": "Worst quarter (%)"}, {"key": "best_qoq_change_pct", "label": "Best quarter (%)"},
            {"key": "worst_4q_change_pct", "label": "Worst four quarters (%)"}, {"key": "quarters", "label": "Quarters"}]
    out = [_text("".join(md)),
           {"type": "table", "title": f"Collateral value change by {lab['segment'].lower()}, quarter on quarter",
            "columns": cols, "rows": ratings.order_table(cols, [{k: (round(v, 2) if isinstance(v, float) else v) for k, v in r.items()} for r in rows]),
            "row_count": len(rows)}]
    if rows:
        out.append({"type": "chart", "title": f"Worst four-quarter collateral change by {lab['segment'].lower()} (%)", "kind": "hbar",
                    "x": "segment", "y": ["worst_4q_change_pct"], "labels": {"worst_4q_change_pct": "Worst four quarters (%)",
                                                                              "segment": lab["segment"]},
                    "rows": [{"segment": r["segment"], "worst_4q_change_pct": round(r["worst_4q_change_pct"], 2)} for r in rows[:15]]})
    return out


def pd_qoq_blocks(res: dict, lab: dict, head: str) -> list[dict]:
    o = res["overall"]
    rows = res["by_segment"]
    md = (f"{head}\n\nAcross the {lab['book'].lower()} book, the EAD-weighted 12-month PD of performing exposures moved by "
          f"an average of **{_fmt_pct(o['avg_qoq_change_pct'])} a quarter** (**{o['avg_qoq_change_bps']:+.0f} bps**) over "
          f"{o['quarters']} quarters; it rose in {res['positive_quarters']} of them and stands at {o['pd_latest_pct']:.2f}%.")
    if rows:
        hi, lo = rows[0], rows[-1]
        md += (f" By {lab['segment'].lower()}, the fastest riser is **{hi['segment']}** ({_fmt_pct(hi['avg_qoq_change_pct'])} a "
               f"quarter) and the calmest **{lo['segment']}** ({_fmt_pct(lo['avg_qoq_change_pct'])}). "
               f"A PD shock of +15% is about {15 / max(abs(o['avg_qoq_change_pct']), 0.01):.1f} average quarters of drift.")
    cols = [{"key": "segment", "label": lab["segment"]}, {"key": "pd_latest_pct", "label": "PD now (%)"},
            {"key": "avg_qoq_change_pct", "label": "Average quarterly change (%)"},
            {"key": "avg_qoq_change_bps", "label": "Average quarterly change (bps)"},
            {"key": "latest_qoq_change_pct", "label": "Latest quarter (%)"}, {"key": "worst_qoq_change_pct", "label": "Largest rise (%)"}]
    table_rows = ratings.order_table(cols, [{k: (round(v, 2) if isinstance(v, float) else v) for k, v in r.items()} for r in [*rows, o]])
    return [_text(md),
            {"type": "table", "title": f"Quarter-on-quarter PD change by {lab['segment'].lower()}", "columns": cols,
             "rows": table_rows, "row_count": len(table_rows)},
            {"type": "chart", "title": "Book PD by quarter (%)", "kind": "line", "x": "period", "y": ["pd_pct"],
             "labels": {"pd_pct": "12-month PD (%)", "period": "Quarter"},
             "rows": [{"period": r["period"], "pd_pct": round(r["pd_pct"], 2)} for r in res["series"]]}]


def method_question(scenario: Scenario) -> dict:
    return {"type": "question", "key": "method",
            "text": "Which model should run this scenario?",
            "options": [
                {"label": "Delta method", "send": "execute with the delta method",
                 "detail": "Moves the bank's own PD, LGD and EAD inputs deterministically; starts exactly at the reported ECL."},
                {"label": "XGBoost", "send": "execute with xgboost",
                 "detail": "Machine-learning models trained on 20 periods; a scenario changes the inputs and the models predict. "
                           "Its own starting ECL is shown next to the reported one."},
                {"label": "Both, side by side", "send": "execute and compare both models",
                 "detail": "Runs the scenario with each model and compares them."}]}


def population_label(thread: dict) -> str:
    lab = runner.LABELS[thread["domain"]]
    return f"the Early Warning cohort {thread['cohort_id']}" if thread.get("cohort_id") else f"the {lab['book'].lower()} book"


def slim(result: dict) -> dict:
    keep = ("run_id", "method", "method_name", "method_version", "cards", "waterfall", "reconciliation", "by_scenario",
            "by_segment", "by_rating", "rating_order", "migration", "top_movers", "attribution_by_segment", "drivers",
            "domain", "period", "labels", "scenario", "steps", "population", "scenario_weights", "seconds")
    return {k: result[k] for k in keep if k in result}


def proposal_chips(method: str | None) -> list[dict]:
    return [{"label": "Execute scenario", "send": "::execute"},
            {"label": "How likely is this?", "send": "how likely is this?"},
            {"label": "Explain the levers", "send": "How will these shocks flow into ECL?"}]


def suggestions_after(method: str, has_cohort: bool) -> list[dict]:
    other = METHOD_NAMES[OTHER[method]]
    return [{"label": f"Rerun with {other}", "send": f"rerun with {other.lower()}"},
            {"label": "Compare both models", "send": "compare both models side by side"},
            {"label": "1.5x more severe", "send": "make it 1.5x more severe"},
            {"label": "Also LGD +5pp", "send": "also add LGD +5pp"},
            {"label": "How likely is this?", "send": "how likely is this?"},
            {"label": "Save this scenario", "send": "save this scenario"}]


# ------------------------------------------------------------------ the turn

class Turn:
    def __init__(self, store, run: dict, thread: dict):
        self.store = store
        self.run = run
        self.thread = thread
        self.state: dict[str, Any] = json.loads(json.dumps(thread.get("state") or {}))
        from backend.convo.trace import TraceRecorder
        # The process trace (PLAN_R5 G4): every stage also lands in the answer's `trace`.
        self.em = TraceRecorder(f"tr-{run['run_id']}", inner=ev.Emitter(store, run["run_id"]))
        self.blocks: list[dict] = []
        self.suggestions: list[dict] = []
        self.terminal = st.COMPLETED
        self.title: str | None = None
        self.display = run["question"]
        self.tools: list[dict] = []
        self.evidence: list[dict] = []

    # tools ------------------------------------------------------------
    def tool(self, name: str, fn, **detail):
        t0 = time.monotonic()
        self.em.emit(ev.TOOL_STARTED, self.em.open_stage, "running", name.replace("_", " "), {"tool": name, **detail})
        try:
            out = fn()
        except Exception as e:
            self.em.emit(ev.TOOL_FAILED, self.em.open_stage, "failed", str(e)[:300], {"tool": name})
            raise
        ms = int((time.monotonic() - t0) * 1000)
        self.tools.append({"tool": name, "ms": ms})
        self.em.emit(ev.TOOL_COMPLETED, self.em.open_stage, "completed", name.replace("_", " "), {"tool": name, "ms": ms})
        return out

    def scenario_obj(self, d: dict | None) -> Scenario | None:
        return Scenario.from_dict(d) if d else None

    def new_scenario(self, steps: list[Step]) -> Scenario:
        return Scenario(domain=self.thread["domain"], period=self.thread["period"] or dstore.as_of(self.thread["domain"]),
                        steps=steps, cohort_id=self.thread.get("cohort_id") or "")

    def set_scenario(self, sc: Scenario) -> None:
        if self.state.get("scenario"):
            hist = self.state.setdefault("history", [])
            hist.append(self.state["scenario"])
            del hist[:-10]
        self.state["scenario"] = sc.to_dict()
        if not self.thread.get("title") or self.thread["title"] in ("New What-If thread", ""):
            self.title = ("; ".join(s.restatement for s in sc.steps))[:90]

    # results ------------------------------------------------------------
    def compute(self, sc: Scenario, method: str) -> dict:
        self.em.stage("computing", f"Re-measuring ECL with the {METHOD_NAMES[method]}")
        try:
            result = self.tool("run_scenario", lambda: runner.run(sc, method), method=method)
        except runner.RunError as e:
            raise Refusal(str(e)) from e
        self.em.stage("attributing", "Attributing the change (exact Shapley over the drivers)")
        self.em.emit(ev.TOOL_COMPLETED, "attributing", "completed", "attribution reconciles"
                     if result["reconciliation"]["reconciles"] else "attribution difference",
                     {"tool": "attribute", "difference": result["reconciliation"]["difference"]})
        return result

    def publish_result(self, sc: Scenario, method: str, intro: str = "") -> dict:
        result = self.compute(sc, method)
        self.em.stage("assessing", "Checking the scenario against history")
        lik = self.tool("assess_likelihood", lambda: likelihood.assess(sc))
        self.em.stage("validating", "Writing and checking the commentary")
        com = self.tool("write_commentary", lambda: cm.commentary(result, lik))
        if intro:
            self.blocks.append(_text(intro))
        if not any(b.get("type") == "regime" for b in self.blocks):
            try:   # R14 m (K12): the current regime and the macro vintage, read first in every scenario answer
                from backend.scenarios import regime as reg_
                self.blocks.append({**reg_.block(), "compact": True})
            except Exception:  # noqa: BLE001 - a result never fails on the regime block
                pass
        self.blocks.append({"type": "result", "result": slim(result)})
        self.blocks.append({"type": "commentary", **com})
        self.blocks.append({"type": "likelihood", **lik})
        self.state["last"] = {"method": method, "run_key": result["run_id"], "scenario_ecl": result["cards"]["scenario_ecl"],
                              "start_ecl": result["cards"]["start_ecl"], "change_pct": result["cards"]["change_pct"]}
        self.suggestions = suggestions_after(method, bool(self.thread.get("cohort_id")))
        return result

    def propose(self, sc: Scenario, assumptions: list[str], unread: list[str], reading_method: str = "",
                kind: str = "new") -> None:
        """Restate the scenario as structured shocks; nothing runs until Execute."""
        from backend.whatif_v5.chat.convo_domain import proposal_block
        if reading_method:
            self.state["method"] = reading_method
        self.em.stage("planning", "Restating the scenario as shocks")
        self.state["pending"] = sc.to_dict()
        self.state["execute_requested"] = False
        self.blocks.append(proposal_block(sc, assumptions, unread, self.state.get("method"), population_label(self.thread), kind))
        if not self.thread.get("title") or self.thread["title"] in ("New What-If thread", ""):
            self.title = ("; ".join(s.restatement for s in sc.steps))[:90]
        self.suggestions = proposal_chips(self.state.get("method"))

    def run_or_ask(self, sc: Scenario, reading_method: str = "") -> None:
        """Execute `sc` now (the user asked to), or ask the model first."""
        if reading_method:
            self.state["method"] = reading_method
        method = self.state.get("method")
        self.em.stage("planning", "Planning the scenario")
        if not method:
            self.state["pending"] = sc.to_dict()
            self.state["execute_requested"] = True
            self.blocks.append(method_question(sc))
            self.suggestions = []
            self.terminal = st.WAITING_FOR_USER
            return
        self.state["pending"] = None
        self.state["execute_requested"] = False
        self.set_scenario(sc)
        self.publish_result(sc, method)

    def on_execute(self, method: str = "", compare: bool = False) -> None:
        sc = self.scenario_obj(self.state.get("pending") or self.state.get("scenario"))
        self.display = "Execute scenario" if self.run["question"].strip().startswith("::execute") else self.run["question"]
        if sc is None:
            self.blocks.append(_text("There is nothing to execute yet. Describe a scenario, for example "
                                     "*reduce collateral by 20%* or *PD +30% for Construction*."))
            self.suggestions = brainstorm_chips(self.thread)
            return
        lab = runner.LABELS[sc.domain]
        if compare:
            self.state["pending"] = None
            self.state["execute_requested"] = False
            self.set_scenario(sc)
            self.state.setdefault("method", "delta")
            if not self.state.get("method"):
                self.state["method"] = "delta"
            self.blocks.append(_text("**Executing** " + "; ".join(s.restatement for s in sc.steps) + " with both models."))
            self.em.stage("planning")
            self.comparison(sc)
            return
        if method:
            self.state["method"] = method
        if self.state.get("method"):
            self.blocks.append(_text("**Executing** " + "; ".join(
                "; ".join(describe_shocks(s.shocks, lab)) + f" on {s.scope.describe(lab)}" for s in sc.steps)
                + (" with the **Delta method**." if self.state["method"] == "delta" else " with **XGBoost**.")))
        self.run_or_ask(sc)

    def comparison(self, sc: Scenario) -> None:
        a = self.compute(sc, "delta")
        b = self.compute(sc, "xgboost")
        self.em.stage("assessing", "Checking the scenario against history")
        lik = self.tool("assess_likelihood", lambda: likelihood.assess(sc))
        self.em.stage("validating", "Comparing the two models")
        rows = []
        for key, label in (("reported_ecl", "Reported ECL"), ("start_ecl", "Start recomputed by the model"),
                           ("scenario_ecl", "Scenario ECL"), ("change", "Change"), ("change_pct", "Change %"),
                           ("coverage_after", "Coverage after %"), ("capital_cet1_after_pct", "CET1 after % (illustrative)")):
            rows.append({"label": label, "delta": a["cards"][key], "xgboost": b["cards"][key],
                         "kind": "pct" if key.endswith("pct") or key.startswith("coverage") else "money"})
        drv = []
        for d in DRIVERS:
            va = next((w["value"] for w in a["waterfall"] if w["key"] == d), 0.0)
            vb = next((w["value"] for w in b["waterfall"] if w["key"] == d), 0.0)
            if abs(va) > 1e-12 or abs(vb) > 1e-12:
                drv.append({"driver": DRIVER_LABELS[d], "delta": va, "xgboost": vb})
        seg = {r["segment"]: {"segment": r["segment"], "delta": r["change"], "xgboost": 0.0} for r in a["by_segment"]}
        for r in b["by_segment"]:
            seg.setdefault(r["segment"], {"segment": r["segment"], "delta": 0.0, "xgboost": 0.0})["xgboost"] = r["change"]
        spread = b["cards"]["change"] - a["cards"]["change"]
        self.blocks.append({"type": "comparison", "rows": rows, "drivers": drv,
                            "segments": sorted(seg.values(), key=lambda r: -abs(r["delta"]))[:10],
                            "moves": {"delta": a["cards"]["moves"], "xgboost": b["cards"]["moves"]},
                            "results": {"delta": slim(a), "xgboost": slim(b)}})
        self.blocks.append({"type": "commentary", "source": "deterministic", "text": (
            f"**Delta vs XGBoost.** The Delta method moves ECL by {cm.money(a['cards']['change'])} "
            f"({a['cards']['change_pct']:+.1f}%) and XGBoost by {cm.money(b['cards']['change'])} "
            f"({b['cards']['change_pct']:+.1f}%): a spread of {cm.money(spread)}. XGBoost starts from its own "
            f"recomputed ECL ({cm.money(b['cards']['start_ecl'])} against {cm.money(b['cards']['reported_ecl'])} reported). "
            "The drivers table shows where they part.")})
        self.blocks.append({"type": "likelihood", **lik})
        self.state["last"] = {"method": self.state.get("method") or "delta", "run_key": a["run_id"], "compared": True}
        self.suggestions = [{"label": "1.5x more severe", "send": "make it 1.5x more severe"},
                            {"label": "How likely is this?", "send": "how likely is this?"},
                            {"label": "Save this scenario", "send": "save this scenario"}]

    # entry points ------------------------------------------------------
    def go(self) -> dict:
        q = self.run["question"].strip()
        self.em.emit(ev.RUN_STARTED, "accepted", "running", "Started")
        self.em.stage("understanding")
        if q.startswith("::library "):
            self.open_library(q.split(" ", 1)[1].strip())
        elif q.startswith("::cohort"):
            self.open_cohort()
        elif q.startswith("::custom "):
            self.custom(q.split(" ", 1)[1])
        else:
            self.typed(q)
        self.context_first()
        return self.finish()

    def context_first(self) -> None:
        """R16 m (M4): a thread opened from a starter, a card or a library item first shows its subject's facts.

        On the opening turn of a thread whose answer proposes a scenario (or the calibrated scenario set), the context
        answer about the scenario's subject (its sector / product scope, or the whole book) goes before everything
        else. Early Warning cohort threads open on the cohort card instead; later turns are unchanged."""
        kinds = {b.get("type") for b in self.blocks}
        if self.thread.get("cohort_id") or kinds & {"context", "cohort"} or not kinds & {"proposal", "scenario_set"}:
            return
        if self.store.turns(self.thread["thread_id"]):
            return
        from backend.whatif_v5.chat import subject
        scopes = subject.scopes_of(self.state.get("pending") or self.state.get("scenario")) if "proposal" in kinds else None
        try:
            self.em.stage("querying", "Reading the subject's facts")
            block = self.tool("describe_subject", lambda: subject.subject_context(self.thread, scopes))
        except Exception:  # noqa: BLE001 - the context is an addition; the proposal stands without it
            return
        at = 0
        while at < len(self.blocks) and self.blocks[at].get("type") == "regime":
            at += 1                            # R14 m (K12): the current regime strip stays the first thing read
        self.blocks.insert(at, block)

    def finish(self) -> dict:
        self.em.stage("publishing")
        answer = {"blocks": self.blocks, "suggestions": self.suggestions, "question_display": self.display,
                  "state": {"has_scenario": bool(self.state.get("scenario")), "method": self.state.get("method"),
                            "pending": bool(self.state.get("pending")),
                            "waiting": self.terminal == st.WAITING_FOR_USER,
                            "steps": [s["restatement"] for s in (self.state.get("scenario") or {}).get("steps", [])]},
                  "tools": self.tools, "planner": convo_provider.describe(), **({"evidence": self.evidence} if self.evidence else {})}
        return answer

    def typed(self, q: str) -> None:
        from backend.scenarios import chat as scn
        kind = scn.route(q, self.state)
        if kind:
            return self.on_scenario_engine(kind)
        self.state.pop("last_kind", None)
        if EXECUTE_RE.search(q):
            low = q.lower()
            m = next((k for k, pat in language.METHOD_WORDS.items() if re.search(pat, q, re.I)), "")
            return self.on_execute(m, compare=bool(re.search(r"\b(compare|both|side by side)\b", low)))
        ctx = read_ctx(self.thread, self.state)
        msg = compose.split(q)
        if msg.mixed:
            # PLAN_R5 T3: questions AND a scenario (or several questions) in one message: every part is answered.
            return self.mixed(msg, ctx)
        if QUESTION_RE.search(q):
            return self.converse(q)
        reading = self.tool("interpret_statement", lambda: language.read(q, ctx))
        if reading.period:
            try:
                self.thread["period"] = dstore.resolve_period(self.thread["domain"], reading.period)
                self.state["period_changed"] = self.thread["period"]
            except dstore.DomainError as e:
                raise Refusal(str(e)) from e
        intent = reading.intent
        if intent in ("help", "brainstorm", "unclear", "explain", "likelihood"):
            return self.converse(q)
        if intent == "choose_method" and self.state.get("execute_requested") and self.state.get("pending"):
            return self.on_execute(reading.method)
        handler = getattr(self, f"on_{intent}", None)
        if handler is None:
            return self.converse(q)
        handler(reading)

    # the scenario engine (PLAN_R13 §S.4) ------------------------------------
    def on_scenario_engine(self, kind: str) -> None:
        """Calibrated mild / moderate / severe with their evidence, or a follow-up (likelihood, method, memo)."""
        from backend.scenarios import chat as scn
        stage = {"scenarios": "Calibrating mild, moderate and severe from history",
                 "likelihood": "Measuring the severities against history", "method": "Writing out the method",
                 "memo": "Writing the methodology memo"}[kind]
        self.em.stage("computing", stage)
        blocks = self.tool("scenario_engine", lambda: scn.answer(kind, self.thread["domain"]), kind=kind)
        self.blocks.extend(blocks)
        self.state["last_kind"] = "scenario_set"
        self.suggestions = [c for c in scn.CHIPS if not (kind == "memo" and c["label"].startswith("Write"))]
        if kind == "scenarios" and (not self.thread.get("title") or self.thread["title"] in ("New What-If thread", "")):
            self.title = "Calibrated stress: mild, moderate, severe"

    # mixed messages (PLAN_R5 T3) ------------------------------------------
    def _cohort_ids(self) -> set[str] | None:
        if not self.thread.get("cohort_id"):
            return None
        book = self.thread["domain"]
        period = self.thread.get("period") or dstore.as_of(book)
        f = dstore.frame(book, period)
        mask, _ = runner.population(Scenario(domain=book, period=period, steps=[], cohort_id=self.thread["cohort_id"]), f)
        return set(f.loc[mask, "exposure_id"].astype(str))

    def mixed(self, msg: "compose.Message", ctx: dict) -> None:
        """Answer each question as its own part, then propose the whole scenario (sized by the answers); wait for Execute."""
        book = self.thread["domain"]
        lab = runner.LABELS[book]
        self.em.stage("planning", f"Splitting the message: {len(msg.questions)} question(s) and the scenario")
        ids = self._cohort_ids()
        recommended: float | None = None
        n = len(msg.questions)
        for i, part in enumerate(msg.questions, 1):
            head = f"**{'Question ' + str(i) + ' of ' + str(n) + ': ' if n > 1 else ''}{part.text.rstrip('?')}?**"
            if part.topic == "collateral_size":
                self.em.stage("querying", "Collateral value history by segment")
                res = self.tool("collateral_history", lambda: compose.collateral_history(book, ids))
                recommended = res["recommended_pct"]
                self.blocks.extend(collateral_blocks(res, lab, head))
            elif part.topic == "pd_qoq":
                self.em.stage("querying", "Quarter-on-quarter PD by segment")
                res = self.tool("pd_quarterly", lambda: compose.pd_quarterly(book, ids))
                self.blocks.extend(pd_qoq_blocks(res, lab, head))
            else:
                self.blocks.append(_text(head))
                self.converse(part.text)
                self.em.stage("planning", "Back to the remaining parts")
        scen = [p for p in msg.statements if compose.LEVER_WORDS.search(p.text)]
        if not scen:
            self.suggestions = self.suggestions or brainstorm_chips(self.thread)
            return
        if recommended is None and any(compose.open_collateral(p.text) for p in scen):
            # A collateral cut with no size: size it from the book's own history, and say so.
            self.em.stage("querying", "Sizing the collateral cut from history")
            res = self.tool("collateral_history", lambda: compose.collateral_history(book, ids))
            recommended = res["recommended_pct"]
            self.blocks.append(_text(f"**Collateral size.** You did not give a size, so I used **{recommended:g}%**: {res['basis']}."))
        text = compose.scenario_text(msg, recommended)
        self.em.stage("planning", "Restating the scenario as shocks")
        reading = self.tool("interpret_statement", lambda: language.read(text, ctx))
        if not reading.steps:
            self.blocks.append(_text("I could not turn “" + text + "” into shocks yet. " + " ".join(reading.unread)))
            self.suggestions = brainstorm_chips(self.thread)
            return
        assumptions = list(reading.assumptions)
        if recommended is not None:
            assumptions.append(f"Collateral market value {recommended:g}%, the size recommended above from the book's history.")
        if compose.wants_staging(msg):
            assumptions.append("Staging effect included: every exposure is re-staged under the SICR rules after the shocks "
                               "(PD at least the SICR multiple of its start, DPD 30/90, rating), so Stage 1 to 2 and 2 to 3 "
                               "moves come out of the PD shock itself and show in the result.")
        if reading.period:
            try:
                self.thread["period"] = dstore.resolve_period(book, reading.period)
            except dstore.DomainError:
                pass
        base = self.scenario_obj(self.state.get("pending") or self.state.get("scenario"))
        steps = (base.steps + reading.steps) if reading.intent == "stack" and base is not None else reading.steps
        sc = self.new_scenario(steps)
        self.propose(sc, assumptions, reading.unread, reading.method, "new")
        if not self.state.get("method"):
            self.blocks.append({"type": "question", "key": "method",
                                "text": "Which model should run it? Pick one; nothing runs until you press Execute scenario.",
                                "options": [{"label": "Delta method", "send": "use the delta method",
                                             "detail": "Moves the bank's own PD, LGD and EAD inputs; starts at the reported ECL."},
                                            {"label": "XGBoost", "send": "use xgboost",
                                             "detail": "The trained models predict under the shocked inputs."}]})
        self.state["execute_requested"] = False

    def converse(self, q: str) -> None:
        """A question: the forked Cockpit agent on the What-If domain answers it from real queries."""
        from backend.convo.agent import Agent
        from backend.whatif_v5.chat.convo_domain import DOMAIN
        scope = {"domain": self.thread["domain"], "period": self.thread.get("period") or dstore.as_of(self.thread["domain"]),
                 "cohort_id": self.thread.get("cohort_id") or ""}
        history = self.store.turns(self.thread["thread_id"])
        agent = Agent(DOMAIN, thread=self.thread, scope=scope, state=self.state, question=q, emitter=self.em,
                      history=history, user={"username": self.run.get("owner") or ""})
        out = agent.run()
        # R14 m (K12): the current-regime block is read first in every scenario answer
        self.blocks.extend([b for b in out.blocks if b.get("type") == "regime"] + [b for b in out.blocks if b.get("type") != "regime"])
        self.state.update(out.state)
        if out.state.get("pending"):
            self.state["execute_requested"] = False
            if not self.thread.get("title") or self.thread["title"] in ("New What-If thread", ""):
                sc = Scenario.from_dict(out.state["pending"])
                self.title = ("; ".join(s.restatement for s in sc.steps))[:90]
            self.suggestions = proposal_chips(self.state.get("method"))
        else:
            self.suggestions = out.suggestions
        self.tools.extend({"tool": t["tool"], "ms": t.get("ms", 0)} for t in agent.trace if "tool" in t)
        self.evidence = out.evidence

    # intents ------------------------------------------------------------
    def on_help(self, reading) -> None:
        lab = runner.LABELS[self.thread["domain"]]
        self.blocks.append(_text(
            "**What you can say.** Describe a scenario in plain words and I turn it into shocks, run it on "
            f"{population_label(self.thread)} and break the ECL change into its drivers. For example:\n\n"
            f"- *increase PD by 30% for {vocabulary(self.thread['domain'])['segments'][0]}*\n- *LGD +5pp*\n"
            f"- *downgrade by 2 {'bands' if self.thread['domain'] == 'retail' else 'notches'}*\n- *oil price -40%*\n"
            f"- *only {lab['exposure'].lower()} {dstore.frame(self.thread['domain'])['exposure_id'].iloc[0]}: downgrade 3 "
            f"{'bands' if self.thread['domain'] == 'retail' else 'notches'}*\n\n"
            "After a result you can **rerun with the other model**, **make it more severe**, **also add** another "
            "shock (stacking), start a **new scenario instead**, **undo**, ask **how likely** it is, or **save** it."))
        self.suggestions = brainstorm_chips(self.thread)

    def on_brainstorm(self, reading) -> None:
        self.em.stage("planning", "Brainstorming the scenario")
        ideas = self.tool("describe_scope", lambda: brainstorm(self.thread))
        text = ideas["text"]
        if provider.available():
            got = provider.structured("brainstorm", BRAINSTORM_SYSTEM, json.dumps({"question": self.run["question"], **ideas["evidence"]}),
                                      BRAINSTORM_TOOL)
            if got and got.get("text") and not cm.check(got["text"], ideas["evidence"]):
                text = got["text"]
        if ideas.get("regime"):
            self.blocks.append(ideas["regime"])          # R14 m: the current regime, read first
        self.blocks.append(_text(text))
        self.blocks.append({"type": "ideas", "ideas": ideas["ideas"]})
        self.suggestions = [{"label": i["label"], "send": i["send"]} for i in ideas["ideas"][:4]]

    def on_unclear(self, reading) -> None:
        self.blocks.append({"type": "question", "key": "clarify",
                            "text": "I could not turn that into a scenario yet. " + " ".join(reading.unread),
                            "options": [{"label": c["label"], "send": c["send"]} for c in brainstorm_chips(self.thread)[:3]]})
        self.terminal = st.WAITING_FOR_USER

    def on_choose_method(self, reading) -> None:
        m = reading.method
        self.state["method"] = m
        pending = self.scenario_obj(self.state.get("pending"))
        if pending:
            self.display = f"Use the {METHOD_NAMES[m]}"
            self.blocks.append(_text(f"The **{METHOD_NAMES[m]}** will run this scenario. Press **Execute scenario** "
                                     "(or say *run it*) to run it."))
            self.suggestions = proposal_chips(m)
        elif self.state.get("scenario"):
            self.blocks.append(_text(f"The **{METHOD_NAMES[m]}** is now this thread's model. Press **Execute scenario** "
                                     "to rerun the current scenario with it."))
            self.suggestions = proposal_chips(m)
        else:
            self.blocks.append(_text(f"The **{METHOD_NAMES[m]}** will run the scenarios in this thread. Describe a scenario."))
            self.suggestions = brainstorm_chips(self.thread)

    def _understood(self, steps: list[Step], reading, kind: str) -> None:
        self.blocks.append(understood_block(steps, reading.assumptions, reading.unread,
                                            reading.method or self.state.get("method"), population_label(self.thread), kind))

    def on_scenario(self, reading) -> None:
        sc = self.new_scenario(reading.steps)
        self.propose(sc, reading.assumptions, reading.unread, reading.method, "new")

    on_new = on_scenario

    def on_stack(self, reading) -> None:
        base = self.scenario_obj(self.state.get("pending") or self.state.get("scenario"))
        if base is None:
            return self.on_scenario(reading)
        sc = self.new_scenario(base.steps + reading.steps)
        self.propose(sc, reading.assumptions + [f"Stacked on the current scenario: {len(sc.steps)} step(s), applied additively."],
                     reading.unread, reading.method, "stack")

    def on_intensify(self, reading) -> None:
        base = self.scenario_obj(self.state.get("pending") or self.state.get("scenario"))
        if base is None:
            raise Refusal("There is no scenario in this thread to make more or less severe yet. Describe one first.")
        f = reading.factor or 1.5
        steps = [Step(instruction=s.instruction, restatement="; ".join(describe_shocks(s.shocks.scaled(f), runner.LABELS[base.domain]))
                      + f" on {s.scope.describe(runner.LABELS[base.domain])}", shocks=s.shocks.scaled(f), scope=s.scope)
                 for s in base.steps]
        sc = self.new_scenario(steps)
        self.propose(sc, reading.assumptions + [f"Every shock x{f:g} (rating notches rounded, at least one)."], [],
                     "", "intensify")

    def on_undo(self, reading) -> None:
        if self.state.get("pending"):
            self.state["pending"] = None
            self.state["execute_requested"] = False
            self.blocks.append(_text("Dropped the proposal that was not executed."))
            self.suggestions = brainstorm_chips(self.thread)
            return
        hist = self.state.get("history") or []
        if not hist:
            if self.state.get("scenario"):
                self.state["scenario"] = None
                self.blocks.append(_text("Removed the scenario; the thread is empty again. Describe a new one."))
            else:
                self.blocks.append(_text("Nothing to undo."))
            self.suggestions = brainstorm_chips(self.thread)
            return
        prev = Scenario.from_dict(hist.pop())
        self.state["scenario"] = prev.to_dict()
        self.blocks.append(_text("Back to the previous scenario: " + "; ".join(s.restatement for s in prev.steps) + "."))
        if self.state.get("method"):
            self.publish_result(prev, self.state["method"])

    def on_other_model(self, reading) -> None:
        sc = self.scenario_obj(self.state.get("scenario"))
        if sc is None:
            raise Refusal("There is no result in this thread to rerun yet. Describe a scenario first.")
        current = (self.state.get("last") or {}).get("method") or self.state.get("method") or "delta"
        target = reading.method if reading.method and reading.method != current else OTHER[current]
        self.display = self.run["question"]
        self.blocks.append(_text(f"Rerunning the same scenario with **{METHOD_NAMES[target]}**, side by side with the "
                                 f"**{METHOD_NAMES[current]}**."))
        self.state["method"] = target
        self.comparison(sc)
        self.state["last"]["method"] = target

    def on_compare(self, reading) -> None:
        sc = self.scenario_obj(self.state.get("scenario") or self.state.get("pending"))
        if sc is None:
            raise Refusal("There is no scenario to compare yet. Describe one first.")
        if self.state.get("pending"):
            self.state["pending"] = None
            self.set_scenario(sc)
            self.state.setdefault("method", "delta")
            if not self.state.get("method"):
                self.state["method"] = "delta"
        self.em.stage("planning")
        self.comparison(sc)

    def on_likelihood(self, reading) -> None:
        sc = self.scenario_obj(self.state.get("scenario") or self.state.get("pending"))
        if sc is None:
            raise Refusal("There is no scenario yet; describe one and I will check it against history.")
        self.em.stage("assessing", "Checking the scenario against history")
        lik = self.tool("assess_likelihood", lambda: likelihood.assess(sc))
        self.blocks.append({"type": "likelihood", **lik})
        self.suggestions = suggestions_after(self.state.get("method") or "delta", False)[:3]

    def on_explain(self, reading) -> None:
        sc = self.scenario_obj(self.state.get("scenario"))
        if sc is None or not self.state.get("method"):
            raise Refusal("There is no result to explain yet.")
        result = self.compute(sc, self.state["method"])
        self.em.stage("validating")
        self.blocks.append({"type": "attribution", "waterfall": result["waterfall"],
                            "by_segment": result["attribution_by_segment"], "drivers": result["drivers"],
                            "reconciliation": result["reconciliation"], "labels": result["labels"]})
        self.blocks.append({"type": "commentary", **cm.commentary(result, None)})
        self.suggestions = suggestions_after(self.state["method"], False)

    def on_save(self, reading) -> None:
        sc = self.scenario_obj(self.state.get("scenario"))
        if sc is None:
            raise Refusal("There is no scenario to save yet.")
        method = self.state.get("method") or "delta"
        result = runner.run(sc, method)
        row = save_scenario(self.store, self.thread, sc, method, result, reading.name or self.thread.get("title") or "")
        self.blocks.append({"type": "saved", "scenario_id": row["scenario_id"], "name": row["name"],
                            "text": f"Saved to the scenario repository as **{row['name']}** ({METHOD_NAMES[method]}, "
                                    f"ECL change {cm.money(row['change'])})."})
        self.suggestions = [{"label": "Word report", "send": "word report"}]

    def on_report(self, reading) -> None:
        if not self.state.get("scenario"):
            raise Refusal("There is no scenario to report on yet.")
        self.blocks.append({"type": "report", "text": "The 5-page Word report for the current scenario is ready to download."})

    # library, cohort, custom ----------------------------------------------
    def open_library(self, sid: str) -> None:
        row = self.store.scenario(sid)
        if row is None:
            raise Refusal(f"{sid} is not in the scenario library.")
        sc = Scenario.from_dict(row["scenario"])
        sc.period = self.thread["period"] or row["period"]
        if self.thread.get("cohort_id"):
            sc.cohort_id = self.thread["cohort_id"]
        self.display = f"Open: {row['name']}"
        self.title = row["name"]
        lab = runner.LABELS[sc.domain]
        desc = [f"**{row['name']}**" + (" (standard scenario)" if row["standard"] else
                                        f" (saved by {row['owner'] or 'a user'})"), row.get("description") or ""]
        self.blocks.append(_text("\n\n".join(d for d in desc if d)))
        self.blocks.append({"type": "understood", "kind": "library", "population": population_label(self.thread),
                            "steps": [{"restatement": "; ".join(describe_shocks(s.shocks, lab)) + f" on {s.scope.describe(lab)}"}
                                      for s in sc.steps], "assumptions": [], "unread": [],
                            "method": METHOD_NAMES[row["method"] or "delta"]})
        self.state["method"] = row["method"] or "delta"
        self.blocks.pop()                      # the definition is restated in the proposal
        self.propose(sc, [], [], "", "library")

    def open_cohort(self) -> None:
        cid = self.thread.get("cohort_id")
        try:
            s = self.tool("describe_scope", lambda: cohort_summary(cid))
        except cohorts.CohortError as e:
            raise Refusal(str(e)) from e
        b360 = str(cid).startswith("b360-cohort-")   # PLAN_R9 B5: a Borrower 360 selection
        origin = "Borrower 360 selection" if b360 else "Early Warning cohort"
        self.display = f"Open the {origin}"
        self.title = (s["title"] if b360 else f"Early Warning cohort: {s['title']}") if s.get("title") else origin
        self.thread["period"] = s["period"]
        # R16 m (M2/M4): an Early Warning cohort thread opens on its population's facts -- the same segment analysis
        # the card shows (compact), before "Describe a scenario".
        analysis = None if b360 else self.tool("segment_analysis", lambda: _cohort_segment_analysis(cid))
        self.blocks.append({"type": "cohort", **s, "labels": runner.LABELS[s["domain"]],
                            **({"analysis": analysis} if analysis else {})})
        self.blocks.append(_text(
            f"Everything in this thread now runs on these {s['exposures']:,} {runner.LABELS[s['domain']]['exposures'].lower()} "
            f"of {s['owners']:,} {runner.LABELS[s['domain']]['owners'].lower()} (frozen by {'Borrower 360' if b360 else 'Early Warning'} at {s['period']}). "
            + ("The segment analysis above shows who is warned, why, and the ECL if the warnings come true. " if analysis else "")
            + "Describe a scenario, or pick one below."))
        self.suggestions = brainstorm_chips(self.thread)

    def custom(self, body: str) -> None:
        try:
            d = json.loads(body)
            sh = parse_shocks(d.get("shocks"))
            scope = Scope.from_dict(d.get("scope"))
        except (ValueError, ShockError) as e:
            raise Refusal(f"The custom shocks could not be read: {e}") from e
        lab = runner.LABELS[self.thread["domain"]]
        rest = "; ".join(describe_shocks(sh, lab)) + f" on {scope.describe(lab)}"
        step = Step(instruction="Custom shocks", restatement=rest, shocks=sh, scope=scope)
        self.display = f"Custom shocks: {rest}"
        mode = d.get("mode", "new")
        from types import SimpleNamespace
        reading = SimpleNamespace(steps=[step], assumptions=[], unread=[], method=d.get("method", ""), intent=mode)
        (self.on_stack if mode == "stack" else self.on_scenario)(reading)
        if d.get("execute"):
            self.on_execute(d.get("method", ""))


# ------------------------------------------------------------------ brainstorm

BRAINSTORM_SYSTEM = ("You are the What-If assistant of a Saudi bank's credit-risk system. Help the user shape a "
                     "scenario: granularity (book, sector, borrower, facility), realism and severity relative to "
                     "history. Use ONLY the figures in the evidence. At most 120 words, plain English." + " " + emphasis.RULE)
BRAINSTORM_TOOL = {"name": "brainstorm", "description": "Reply to the user.",
                   "input_schema": {"type": "object", "required": ["text"], "properties": {"text": {"type": "string"}}}}


def brainstorm_chips(thread: dict) -> list[dict]:
    try:   # R14 m (K12): in a high-oil regime the chips are the regime's scenarios, never an oil fall from the average
        from backend.scenarios import recommend as rec_, regime as reg_
        if reg_.is_high():
            return [{"label": i["label"], "send": i["send"]} for i in rec_.recommend(thread["domain"])["ideas"][:4]]
    except Exception:  # noqa: BLE001 - the static chips below stay available
        pass
    if thread["domain"] == "corporate":
        return [{"label": "Oil -40%", "send": "oil price -40%"},
                {"label": "Construction PD +30%", "send": "increase PD by 30% for Construction"},
                {"label": "2-notch downgrade", "send": "downgrade by 2 notches"},
                {"label": "LGD +5pp", "send": "LGD +5pp"}]
    return [{"label": "Unemployment +2pp", "send": "unemployment +2pp"},
            {"label": "Credit card PD +50%", "send": "credit cards PD +50%"},
            {"label": "1 score band worse", "send": "downgrade by 1 band"},
            {"label": "House prices -20%", "send": "house prices -20% and mortgage LGD +5pp"}]


def brainstorm(thread: dict) -> dict[str, Any]:
    domain = thread["domain"]
    f = dstore.frame(domain, thread["period"] or "")
    lab = runner.LABELS[domain]
    seg = f.groupby("segment")["ecl_final"].sum().sort_values(ascending=False)
    top = seg.index[0]
    a = mev.annual()
    brent = (a["brent"] / a["brent"].shift(1) - 1).loc[:2025].dropna() * 100
    gdp = a["gdp_real"].loc[:2025].dropna()
    repo = (a["repo"] - a["repo"].shift(1)).loc[:2025].dropna() * 100
    from backend.whatif_v5.likelihood import _yoy_series, panel
    p = panel(domain)
    notch = _yoy_series(p, "grade_rank")
    ev_ = {"largest_segment_by_ecl": top, "its_ecl": cm.money(float(seg.iloc[0])),
           "worst_oil_year": int(brent.idxmin()), "worst_oil_fall_pct": round(float(brent.min()), 1),
           "worst_gdp_year": int(gdp.idxmin()), "worst_gdp_growth_pct": round(float(gdp.min()), 1),
           "largest_repo_rise_bps": round(float(repo.max())), "its_year": int(repo.idxmax()),
           "worst_avg_notch_move_in_a_year": round(float(notch.max()), 2) if len(notch) else None,
           "periods": len(dstore.periods(domain))}
    # R14 m (K12): the ideas are conditioned on the current regime and the revenue channel (backend/scenarios/recommend);
    # the regime block is read first, and in a high-oil regime no oil fall from the long-run average is offered.
    from backend.scenarios import recommend as rec_
    rec = rec_.recommend(domain, top=top)
    guide = (f"**Shaping it yourself.** Decide *where* (the whole {lab['book'].lower()} book, a {lab['segment'].lower()} such as "
             f"{top}, the largest by ECL at {ev_['its_ecl']}, one {lab['owner'].lower()} or one {lab['exposure'].lower()}), "
             f"*what moves* (PD, LGD, CCF/EAD, rating, a sector stress, or a macro variable that moves them all) and *how hard*.")
    text = rec["body"] + "\n\n" + guide          # the regime itself is the `regime` block, rendered first
    ideas = [{k: i[k] for k in ("label", "send", "why", "family", "severity", "key") if k in i} for i in rec["ideas"]]
    ev_.update(rec["evidence"])
    return {"text": text, "ideas": ideas, "evidence": ev_, "regime": rec["regime"], "revenue_line": rec_.revenue.summary_line(rec["revenue"])}


def model_read(q: str, ctx: dict) -> language.Reading | None:
    """The assistant model reads a statement the deterministic reader could not; its shocks are validated."""
    tool = {"name": "propose_scenario", "description": "Structured shocks for the statement, or none.",
            "input_schema": {"type": "object", "properties": {"steps": {"type": "array", "items": {"type": "object", "properties": {
                "shocks": {"type": "object"}, "scope": {"type": "object"}, "restatement": {"type": "string"}}}}}}}
    system = ("Turn the user's statement into What-If shocks. Shock schema: pd {mode: relative|pp|bps, value}, lgd {mode: "
              "pp|relative, value}, ccf {mode: pp|relative, value}, ead (% number), rating (notches, + = downgrade), sector "
              "(sd of stress, + = stress), mev {series: move} with series in " + ", ".join(mev.BY_KEY) +
              ", stage [{from,to,share}]. Scope: segments, subsegments, owners, exposures, stages. Segments available: "
              + ", ".join(ctx["segments"]) + ". If the statement is not a scenario, return no steps.")
    got = provider.structured("interpret", system, q, tool)
    if not got or not got.get("steps"):
        return None
    steps = []
    for s in got["steps"][:5]:
        try:
            sh = parse_shocks(s.get("shocks"))
            sc = Scope.from_dict(s.get("scope"))
        except (ShockError, ValueError, TypeError):
            return None
        if not sh.drivers():
            continue
        lab = runner.LABELS[ctx["domain"]]
        steps.append(Step(instruction=q, restatement="; ".join(describe_shocks(sh, lab)) + f" on {sc.describe(lab)}",
                          shocks=sh, scope=sc))
    if not steps:
        return None
    return language.Reading(intent="new" if ctx.get("has_scenario") else "scenario", steps=steps,
                            assumptions=[])


def save_scenario(store, thread: dict, sc: Scenario, method: str, result: dict, name: str) -> dict:
    c = result["cards"]
    owner = thread.get("owner") or ""
    return store.save_scenario({
        "owner": owner, "team": thread.get("team") or "", "name": (name or "Saved scenario")[:120],
        "description": "; ".join(s.restatement for s in sc.steps), "domain": sc.domain, "period": sc.period,
        "method": method, "scenario": sc.to_dict(), "summary": {"cards": c, "waterfall": result["waterfall"],
                                                                "run_key": result["run_id"]},
        "ecl_before": c["start_ecl"], "ecl_after": c["scenario_ecl"], "change": c["change"], "change_pct": c["change_pct"],
        "tags": sorted({d for d in result["drivers"] if d != "staging"}) + ([sc.domain]),
        "thread_id": thread["thread_id"], "cohort_id": sc.cohort_id})


# ------------------------------------------------------------------ worker entry

def answer(store, run_id: str) -> None:
    run = store.run(run_id)
    thread = store.thread(run["thread_id"])
    turn = Turn(store, run, thread)
    try:
        ans = turn.go()
        ans["trace"] = turn.em.finish()
        store.save_thread_state(thread["thread_id"], turn.state, title=turn.title, period=turn.thread.get("period"))
        store.append_turn(thread["thread_id"], run_id, turn.display, ans)
        turn.em.close()
        turn.em.emit(ev.ANSWER_READY, "publishing", "completed", "Answer ready", {"state": turn.terminal})
        store.settle(run_id, turn.terminal, ans)
    except Refusal as e:
        ans = {"blocks": [{"type": "refusal", "text": str(e)}], "suggestions": brainstorm_chips(thread),
               "question_display": turn.display, "state": {"has_scenario": bool(turn.state.get("scenario"))},
               "trace": turn.em.finish()}
        store.append_turn(thread["thread_id"], run_id, turn.display, ans)
        turn.em.close()
        turn.em.emit(ev.ANSWER_READY, "publishing", "completed", "Answered with a refusal", {"state": st.COMPLETED})
        store.settle(run_id, st.COMPLETED, ans)
    except Exception as e:  # noqa: BLE001 - the turn fails visibly, the thread is unchanged
        detail = traceback.format_exc()[-1500:]
        ans = {"blocks": [{"type": "error", "text": "Something went wrong while answering; the thread is unchanged. "
                                                    f"({type(e).__name__})"}],
               "suggestions": [], "question_display": turn.display, "state": {}, "trace": turn.em.finish(failed=True)}
        store.append_turn(thread["thread_id"], run_id, turn.display, ans)
        turn.em.close()
        turn.em.emit(ev.RUN_FAILED, "", "failed", "The turn failed", {"error": type(e).__name__, "trace": detail})
        store.settle(run_id, st.FAILED, ans, error_code="WHATIF_INTERNAL", error=str(e)[:500])


_ = re


# ------------------------------------------------------------------ R16 m (M2): the cohort's segment analysis

def _cohort_segment_analysis(cohort_id: str) -> dict[str, Any] | None:
    """The compact Early Warning segment analysis of the population an Early Warning card froze.

    The frozen cohort carries the request it was exported with (book, period, scope, cohort); the analysis is the
    Early Warning service's own deterministic engine (`backend.ews_domain.segment_analysis`) on that scope and period,
    read-only. None for a single-customer export, a Borrower 360 selection, or when the analysis cannot be read (the
    thread still opens on the cohort tiles)."""
    try:
        frozen = cohorts.open_cohort(cohort_id)
        req = frozen.get("request") or {}
        if not req or req.get("customer_id"):
            return None
        scope = req.get("scope") or {}
        from backend.ews_domain import segment_analysis
        full = segment_analysis.analyse(str(req.get("domain") or frozen.get("domain_id")), str(req.get("period") or frozen.get("period") or ""),
                                        scope.get("segment") or "", scope.get("classification") or "",
                                        scope.get("subsegment") or "", scope.get("dims") or None)
        return segment_analysis.compact(full)
    except Exception:  # noqa: BLE001 - the analysis is an addition; the cohort thread opens without it
        return None
