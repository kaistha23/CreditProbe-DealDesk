#!/usr/bin/env python3
"""Round E gate: the golden Deal Desk questions' figures, captured on the deterministic planner.

    .venv/bin/python ops/round_e_golden.py capture   # writes tests/v5/convo_efficiency/golden_figures.json
    .venv/bin/python ops/round_e_golden.py check     # recomputes and compares; exit 1 on any difference

Each golden question (ops/model_lab.py QUESTIONS, the 21 of tests/v5/dealdesk_ui/test_convo.py) is answered on a fresh
thread with no model (the deterministic planner, the engine in-process). The record keeps, per question: the intent,
the engine tools called, and every figure in the answer's text and tables, in order. The efficiency work (prompt
caching, engine first, compact prompts, capped rows, summarised history) must leave every one of them unchanged.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

V5 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V5))
os.environ.setdefault("DEALDESK_VAR", tempfile.mkdtemp(prefix="round-e-golden-"))
FIXTURE = V5 / "tests" / "v5" / "convo_efficiency" / "golden_figures.json"


def questions() -> list[tuple[str, str | None, str]]:
    import importlib.util
    spec = importlib.util.spec_from_file_location("model_lab", V5 / "ops" / "model_lab.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)  # type: ignore[union-attr]
    return list(m.QUESTIONS)


def figures_of(answer: dict[str, Any]) -> list[str]:
    from backend.convo.validate import numbers
    out: list[str] = []
    for b in answer.get("blocks") or []:
        if b.get("markdown"):
            out.extend(tok for tok, _, _ in numbers(b["markdown"]))
        for row in b.get("rows") or []:
            cells = row if isinstance(row, list) else list(row.values()) if isinstance(row, dict) else []
            for c in cells:
                out.extend(tok for tok, _, _ in numbers(str(c)))
    return out


def compute() -> list[dict[str, Any]]:
    from backend.convo import provider
    from backend.dealdesk_thread import convo, engine
    from backend.dealdesk_thread.store import Store

    provider.set_override(None)
    os.environ["CONVO_ASSISTANT_MODEL"] = "off"
    out = []
    with tempfile.TemporaryDirectory(prefix="round-e-") as d:
        for i, (intent, pid, q) in enumerate(questions()):
            store = Store(str(Path(d) / f"t{i}.sqlite"))
            p = engine.get(f"/proposals/{pid}")["proposal"] if pid else None
            a = convo.answer(store, p, q, {})
            out.append({"proposal_id": pid, "question": q, "intent": a.get("intent"), "tools": a.get("tools"),
                        "figures": figures_of(a), "passed": (a.get("validation") or {}).get("passed")})
    return out


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "check"
    got = compute()
    if cmd == "capture":
        FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        FIXTURE.write_text(json.dumps(got, indent=1, ensure_ascii=False) + "\n")
        print(f"captured {len(got)} questions, {sum(len(r['figures']) for r in got)} figures -> {FIXTURE}")
        return 0
    want = json.loads(FIXTURE.read_text())
    bad = [(w["question"], w["proposal_id"]) for w, g in zip(want, got) if w != g]
    print(f"{len(got)} questions, {sum(len(r['figures']) for r in got)} figures; {len(bad)} differ")
    for b in bad:
        print("  DIFFERS:", b)
    return 1 if bad or len(want) != len(got) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
