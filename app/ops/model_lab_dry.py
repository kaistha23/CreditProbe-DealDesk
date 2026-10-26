#!/usr/bin/env python3
"""The model lab's dry run (Round E): calls and input tokens per Deal Desk question, before and after, with no model.

    .venv/bin/python ops/model_lab.py dry                      # both modes, the 21 golden questions
    .venv/bin/python ops/model_lab.py dry --efficiency off     # the "before" prompts only

In-process (the engine in-process, no service, no key). Each golden question is answered three ways:

  planner   the deterministic planner (no model): the reference answer and its figures
  off       CONVO_EFFICIENCY=off: the analysis loop as it was before Round E, with a stand-in model that follows the
            planner's plan, one tool call per step (as Opus did, 4.9 calls per question on average), then publishes
            the planner's answer through finalize_answer
  on        CONVO_EFFICIENCY=on: the same stand-in; known questions go engine first (one writing call, which
            returns the engine's draft), free-form questions go through the compact loop

Tokens are ESTIMATED from the request the provider receives (characters / 4 over system, tool schemas and messages,
as JSON), with Anthropic prompt caching modelled: the cacheable head (system head and tool schemas, and inside the
loop the previous step's whole prompt) is a cache write the first time and a cache read after (5-minute TTL, all
within one run). "Input" is uncached input; "billable" is input + 1.25 x cache write + 0.1 x cache read. The figures of
each answer are compared with the planner's (and with tests/v5/convo_efficiency/golden_figures.json).

Writes var/model_lab/dry_<mode>.json and var/model_lab/dry_compare.md.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

V5 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V5))
sys.path.insert(0, str(V5 / "ops"))
os.environ.setdefault("DEALDESK_VAR", tempfile.mkdtemp(prefix="model-lab-dry-"))
os.environ.setdefault("CONVO_TELEMETRY_DIR", tempfile.mkdtemp(prefix="model-lab-dry-tel-"))
LAB = V5 / "var" / "model_lab"


def est(x: Any) -> int:
    s = x if isinstance(x, str) else json.dumps(x, default=str, ensure_ascii=False)
    return max(1, round(len(s) / 4))


class Replay:
    """A stand-in model: follows the planner's plan one tool call per step, then publishes the planner's answer.
    Records the estimated tokens of every request, with Anthropic prompt caching modelled."""

    name = "replay"

    def __init__(self, plan_steps: list[Any], final: dict[str, Any], seen: set[str]):
        self.steps = list(plan_steps)
        self.final = final          # the planner's finalize_answer input: markdown, tables, charts (artifact ids)
        self.seen = seen            # cache keys written earlier in the run
        self.calls: list[dict[str, Any]] = []
        self._prev_prompt = 0       # the previous loop step's whole prompt (cached when the step marked it)

    def model(self) -> str:
        return "replay"

    def step(self, purpose: str, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]):
        from backend.convo import efficiency
        from backend.convo.provider import Reply

        req = efficiency.anthropic_request(system, tools, messages, purpose)
        total = est(req["system"]) + est(req["tools"]) + est(req["messages"])
        cache_read = cache_write = 0
        if efficiency.enabled():
            head = req["system"][0]["text"] if isinstance(req["system"], list) and req["system"] and \
                req["system"][0].get("cache_control") else ""
            prefix = est(head) + est(req["tools"]) if head else est(req["tools"])
            key = hashlib.sha1((head + json.dumps([t.get("name") for t in tools])).encode()).hexdigest()
            if self._prev_prompt and purpose != efficiency.WRITE_PURPOSE:
                cache_read = min(self._prev_prompt, total)
            elif key in self.seen:
                cache_read = prefix
            else:
                cache_write = prefix
                self.seen.add(key)
            self._prev_prompt = total if purpose in efficiency.LOOP_PURPOSES else 0
            if purpose in efficiency.LOOP_PURPOSES:
                cache_write += max(0, total - cache_read - (prefix if cache_write else 0))
        names = [t["name"] for t in tools]
        if self.steps and names != ["finalize_answer"]:
            s = self.steps.pop(0)
            blocks = [{"type": "tool_use", "id": f"r{len(self.calls)}", "name": s.tool, "input": dict(s.args)}]
        else:
            fin = {k: v for k, v in self.final.items() if k in ("markdown", "tables", "charts", "suggestions")}
            if purpose == efficiency.WRITE_PURPOSE:
                try:
                    fin = {"markdown": json.loads(messages[-1]["content"])["engine_draft"]}
                except Exception:  # noqa: BLE001
                    pass
            blocks = [{"type": "tool_use", "id": f"r{len(self.calls)}", "name": "finalize_answer", "input": fin}]
        out_tokens = est(blocks)
        uncached = total - cache_read - cache_write
        self.calls.append({"purpose": purpose, "prompt_tokens": total, "input_tokens": uncached, "cache_read": cache_read,
                           "cache_write": cache_write, "output_tokens": out_tokens,
                           "billable": round(uncached + 1.25 * cache_write + 0.1 * cache_read)})
        return Reply(content=blocks, stop_reason="tool_use", usage={})


def run_mode(mode: str, questions: list[tuple[str, str | None, str]]) -> dict[str, Any]:
    from backend.convo import provider
    from backend.convo.agent import Agent
    from backend.convo.spec import ToolContext
    from backend.dealdesk_thread import convo, engine
    from backend.dealdesk_thread.store import Store
    import round_e_golden as g

    rows = []
    seen: set[str] = set()
    with tempfile.TemporaryDirectory(prefix=f"dry-{mode}-") as d:
        for i, (intent, pid, q) in enumerate(questions):
            p = engine.get(f"/proposals/{pid}")["proposal"] if pid else None
            os.environ["CONVO_EFFICIENCY"] = "on"
            provider.set_override(None)
            os.environ["CONVO_ASSISTANT_MODEL"] = "off"
            held: dict[str, Any] = {}
            orig = Agent._deterministic

            def keep(self, _orig=orig, _held=held):   # the planner's final answer, with its artifact ids
                out = _orig(self)
                _held.update(out)
                return out
            Agent._deterministic = keep
            try:
                ref = convo.answer(Store(str(Path(d) / f"ref{i}.sqlite")), p, q, {})
            finally:
                Agent._deterministic = orig
            if mode == "planner":
                rows.append({"proposal_id": pid, "question": q, "intent": ref["intent"], "calls": 0, "prompt_tokens": 0,
                             "input_tokens": 0, "cache_read": 0, "cache_write": 0, "output_tokens": 0, "billable": 0,
                             "source": ref["source"], "figures": g.figures_of(ref), "figures_equal": True})
                continue
            os.environ["CONVO_EFFICIENCY"] = mode
            ctx = ToolContext(domain=convo.DOMAIN, thread={}, state={}, scope={"proposal_id": pid} if pid else {}, user={},
                              question=q, execute=False)
            try:
                steps = convo.planner(q, ctx).steps
            except Exception:  # noqa: BLE001
                steps = []
            rp = Replay(steps, held, seen)
            provider.set_override(rp)
            try:
                a = convo.answer(Store(str(Path(d) / f"{mode}{i}.sqlite")), p, q, {})
            finally:
                provider.set_override(None)
            figs = g.figures_of(a)
            tot = {k: sum(c[k] for c in rp.calls) for k in ("prompt_tokens", "input_tokens", "cache_read", "cache_write",
                                                             "output_tokens", "billable")}
            rows.append({"proposal_id": pid, "question": q, "intent": a["intent"], "calls": len(rp.calls), **tot,
                         "purposes": [c["purpose"] for c in rp.calls], "source": a["source"], "figures": figs,
                         "figures_equal": figs == g.figures_of(ref), "passed": (a.get("validation") or {}).get("passed")})
    os.environ["CONVO_EFFICIENCY"] = "on"
    n = len(rows) or 1
    head = {"questions": len(rows), "calls_per_question": round(sum(r["calls"] for r in rows) / n, 2),
            "prompt_tokens_per_question": round(sum(r["prompt_tokens"] for r in rows) / n),
            "input_tokens_per_question": round(sum(r["input_tokens"] for r in rows) / n),
            "cache_read_per_question": round(sum(r["cache_read"] for r in rows) / n),
            "cache_write_per_question": round(sum(r["cache_write"] for r in rows) / n),
            "billable_per_question": round(sum(r["billable"] for r in rows) / n),
            "answers_with_same_figures": sum(1 for r in rows if r["figures_equal"])}
    return {"mode": mode, "headline": head, "rows": rows}


# Free-form questions (the planner does not know their type): the model loop, with the compact prompt after Round E
FREE: list[tuple[str, str | None, str]] = [
    ("free", "DD-01", "Who is the borrower and how big is the existing exposure?"),
    ("free", "DD-03", "Is the pricing reasonable for this name?"),
    ("free", None, "List the five largest asks in the book with their RAROC"),
    ("free", None, "Give me the average RAROC of the deals that clear"),
]


def markdown(off: dict[str, Any] | None, on: dict[str, Any] | None, golden_ok: bool | None) -> str:
    lines = ["# Model lab, dry run: Deal Desk questions before and after Round E", "",
             "Estimated tokens (characters / 4), stand-in model following the planner's plan; prompt caching modelled.", ""]
    if off and on:
        ho, hn = off["headline"], on["headline"]
        lines += ["| Per question | Before (efficiency off) | After (efficiency on) |", "|---|---|---|"]
        for k, lab in (("calls_per_question", "Model calls"), ("prompt_tokens_per_question", "Prompt tokens sent"),
                       ("input_tokens_per_question", "Uncached input tokens"), ("cache_read_per_question", "Cache read tokens"),
                       ("cache_write_per_question", "Cache write tokens"), ("billable_per_question", "Billable-equivalent input tokens")):
            lines.append(f"| {lab} | {ho[k]:,} | {hn[k]:,} |")
        lines.append(f"| Answers with the planner's figures | {ho['answers_with_same_figures']} / {ho['questions']} | "
                     f"{hn['answers_with_same_figures']} / {hn['questions']} |")
        if golden_ok is not None:
            lines.append(f"| Planner figures equal to the golden capture | {'yes' if golden_ok else 'NO'} | |")
        lines += ["", "| Deal | Question | Calls b/a | Prompt tokens b/a | Billable b/a | Same figures b/a |", "|---|---|---|---|---|---|"]
        for ro, rn in zip(off["rows"], on["rows"]):
            lines.append(f"| {ro['proposal_id'] or 'desk'} | {ro['question'][:55]} | {ro['calls']} / {rn['calls']} | "
                         f"{ro['prompt_tokens']:,} / {rn['prompt_tokens']:,} | {ro['billable']:,} / {rn['billable']:,} | "
                         f"{'yes' if ro['figures_equal'] else 'NO'} / {'yes' if rn['figures_equal'] else 'NO'} |")
    return "\n".join(lines) + "\n"


def main(mode: str = "both", extra: list[tuple[str, str | None, str]] | None = None) -> int:
    import round_e_golden as g

    qs = g.questions() + list(extra or [])
    LAB.mkdir(parents=True, exist_ok=True)
    out: dict[str, Any] = {}
    modes = ["off", "on"] if mode == "both" else [mode]
    for m in modes:
        out[m] = run_mode(m, qs)
        (LAB / f"dry_{m}.json").write_text(json.dumps(out[m], indent=1, ensure_ascii=False))
        h = out[m]["headline"]
        print(f"{m:4}: {h['calls_per_question']} calls, {h['prompt_tokens_per_question']:,} prompt tokens "
              f"({h['input_tokens_per_question']:,} uncached, {h['cache_read_per_question']:,} cache read, "
              f"{h['cache_write_per_question']:,} cache write; billable ~{h['billable_per_question']:,}) per question; "
              f"same figures {h['answers_with_same_figures']}/{h['questions']}")
    golden_ok = None
    if not extra:
        planner = run_mode("planner", qs)
        want = json.loads(g.FIXTURE.read_text())
        golden_ok = [r["figures"] for r in planner["rows"]] == [w["figures"] for w in want]
        print(f"planner figures equal to the golden capture: {golden_ok}")
    if mode == "both" and not extra:
        free = {m: run_mode(m, FREE) for m in ("off", "on")}
        for m in free:
            (LAB / f"dry_free_{m}.json").write_text(json.dumps(free[m], indent=1, ensure_ascii=False))
            h = free[m]["headline"]
            print(f"free-form {m:4}: {h['calls_per_question']} calls, {h['prompt_tokens_per_question']:,} prompt tokens, "
                  f"billable ~{h['billable_per_question']:,} per question; same figures {h['answers_with_same_figures']}/{h['questions']}")
        out["free_off"], out["free_on"] = free["off"], free["on"]
    if "off" in out and "on" in out:
        md = markdown(out["off"], out["on"], golden_ok)
        if "free_off" in out:
            md += "\n## Free-form questions (the model loop)\n\n" + markdown(out["free_off"], out["free_on"], None).split("\n", 4)[4]
        (LAB / "dry_compare.md").write_text(md)
        print(md)
    bad = [r for m in out.values() for r in m["rows"] if not r["figures_equal"]]
    return 1 if bad or golden_ok is False else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "both"))
