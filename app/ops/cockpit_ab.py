#!/usr/bin/env python3
"""Cockpit speed A/B (PLAN_R2 item 2): the same questions, asked live, timed.

Drives a running Cockpit V4 API exactly as the UI does (POST /threads, POST
/runs in Standard mode, then the run's own committed trace) and records, per
answer: total time, time per stage, model calls, failed validations with
their messages, and whether the answer published.

Every live Ask is appended to evidence/v5/cockpit/ask_runs.jsonl BEFORE the
next one starts, and nothing is sent once that file holds CAP runs (60 for
the night, PLAN_R2 section 0). Nothing here prints or reads the API key; the
Cockpit under test reads its own.

    ops/cockpit_ab.py --label roundh --api http://127.0.0.1:8424 [--only Q1,Q5]
    ops/cockpit_ab.py --label v5 --api http://127.0.0.1:8500
    ops/cockpit_ab.py --report        # the side-by-side table from the log
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

V5 = Path(__file__).resolve().parents[1]
LOG = V5 / "evidence" / "v5" / "cockpit" / "ask_runs.jsonl"
CAP = 60
PREFIX = "/api/v1/cockpit-v4"
TERMINAL = {"COMPLETED", "PARTIAL", "WAITING_FOR_USER", "REFERRED",
            "UNSUPPORTED", "FAILED", "CANCELLED", "EXPIRED", "INTERRUPTED"}

#: Four of the five suggested questions per book (frontend/src/components/
#: cockpit-v4/domain-meta.ts), on each book's own period noun, including the
#: two Anne timed on 10 Oct.
QUESTIONS = [
    ("Q1", "corporate", "What is driving Stage 2 and ECL growth?"),
    ("Q2", "corporate", "Which sectors deteriorated most this quarter?"),
    ("Q3", "corporate", "Show EAD by sector for the latest quarter."),
    ("Q4", "corporate", "Why is risk building across the corporate book?"),
    ("Q5", "retail", "Which products saw the largest Stage 2 increase this month?"),
    ("Q6", "retail", "Where is delinquency building?"),
    ("Q7", "retail", "Show retail EAD by product for the latest month."),
    ("Q8", "retail", "Why is risk building across the retail book?"),
]


def call(api: str, method: str, path: str, body: dict | None = None,
         headers: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(api + PREFIX + path, data=data, method=method,
                                 headers={"Content-Type": "application/json",
                                          **(headers or {})})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read() or b"{}")


def used() -> int:
    return sum(1 for _ in LOG.open()) if LOG.exists() else 0


def stages(events: list[dict]) -> dict:
    """Split the run's own trace into the four stages Anne asked about.

    understanding  the first model call (reading the question, planning)
    query          from there to the start of the model call that writes the
                   first answer: SQL execution plus any further analysis round
    finalize       that answer-writing model call
    validation     from the first answer check to the published answer,
                   including any correction round a rejection cost
    """
    t = lambda e: e.get("elapsed_ms", 0) / 1000.0  # noqa: E731
    calls, open_at = [], None
    for e in events:
        if e["event_type"] == "model.requested":
            open_at = t(e)
        elif e["event_type"] == "model.response_received" and open_at is not None:
            calls.append((open_at, t(e)))
            open_at = None
    publish = [t(e) for e in events if e["event_type"] == "tool.requested"
               and e.get("stage") == "publishing"]
    total = max((t(e) for e in events), default=0.0)
    # A run the supervisor settles (deadline) restarts `elapsed_ms` on its
    # own events, so the clock time between the first and last event wins.
    stamps = [datetime.fromisoformat(e["occurred_at"]) for e in events if e.get("occurred_at")]
    if len(stamps) > 1:
        total = max(total, (max(stamps) - min(stamps)).total_seconds())
    out = {"total_s": round(total, 1), "model_calls": len(calls),
           "model_call_s": [round(b - a, 1) for a, b in calls]}
    if not calls:
        return out
    first_end = calls[0][1]
    if publish:
        writer = max((c for c in calls if c[1] <= publish[0]), key=lambda c: c[1])
        out["understanding_s"] = round(calls[0][1] - calls[0][0], 1)
        out["query_s"] = round(max(writer[0] - first_end, 0.0), 1) if writer != calls[0] else 0.0
        out["finalize_s"] = round(writer[1] - writer[0], 1) if writer != calls[0] else 0.0
        out["validation_s"] = round(total - publish[0], 1)
    return out


def ask(api: str, label: str, qid: str, domain: str, question: str) -> dict:
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    thread = call(api, "POST", "/threads", {"domain": domain})
    run = call(api, "POST", "/runs",
               {"question": question, "thread_id": thread["thread_id"],
                "mode": "standard", "domain": domain},
               {"Idempotency-Key": uuid.uuid4().hex})
    run_id = run.get("run_id") or run.get("run", {}).get("run_id")
    wall = time.monotonic()
    state = ""
    while time.monotonic() - wall < 420:
        state = str(call(api, "GET", f"/runs/{run_id}").get("state", ""))
        if state in TERMINAL:
            break
        time.sleep(1.0)
    wall_s = round(time.monotonic() - wall, 1)
    time.sleep(5)  # let a model call the deadline overtook land in the trace
    trace = call(api, "GET", f"/runs/{run_id}/trace")
    events = trace.get("events", [])
    rejections = []
    for e in events:
        if e["event_type"] == "answer.validated" and e.get("status") == "rejected":
            problems = []
            if e.get("detail_ref"):
                try:
                    detail = call(api, "GET", f"/runs/{run_id}/details/{e['detail_ref']}")
                    problems = (detail.get("body") or detail).get("problems") or []
                except Exception:  # noqa: BLE001
                    problems = []
            rejections.append({"at_s": round(e.get("elapsed_ms", 0) / 1000, 1),
                               "problems": [str(p)[:400] for p in problems]
                               or [e.get("public_message", "")]})
    failures = [{"event": e["event_type"], "stage": e.get("stage"),
                 "message": str(e.get("public_message", ""))[:300]}
                for e in events if e["event_type"] in ("tool.failed", "run.failed")]
    budget = trace.get("budget") or {}
    record = {
        "at": started, "build": label, "api": api, "question_id": qid,
        "domain": domain, "question": question, "mode": "standard",
        "run_id": run_id, "state": state or trace.get("state"),
        "error_code": trace.get("error_code", ""),
        "published": any(e["event_type"] == "answer.ready" for e in events),
        "wall_s": wall_s, **stages(events),
        "failed_validations": len(rejections), "rejections": rejections,
        "failures": failures,
        "answer_corrections": (budget.get("answer_corrections") or [0])[0],
        "spend_usd": (budget.get("spend") or {}).get("committed_usd"),
        "release": (trace.get("release") or {}).get("release_id"),
    }
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def report(labels: list[str]) -> str:
    rows = [json.loads(line) for line in LOG.open()] if LOG.exists() else []
    last = {}
    for r in rows:
        if r.get("wall_s", 0) > r.get("total_s", 0) + 5:   # trace read before it settled
            r["total_s"] = r["wall_s"]
        last[(r["build"], r["question_id"])] = r
    lines = ["| Q | Question | " + " | ".join(
        f"{b}: total s (und / query / final / valid) · calls · rejected · published"
        for b in labels) + " |", "|---|---|" + "---|" * len(labels)]
    for qid, _, q in QUESTIONS:
        cells = []
        for b in labels:
            r = last.get((b, qid))
            if not r:
                cells.append("—")
                continue
            cells.append(
                f"**{r.get('total_s', '?')}** ({r.get('understanding_s', '–')} / "
                f"{r.get('query_s', '–')} / {r.get('finalize_s', '–')} / "
                f"{r.get('validation_s', '–')}) · {r.get('model_calls')} · "
                f"{r.get('failed_validations')} · {'yes' if r.get('published') else 'NO'}")
        lines.append(f"| {qid} | {q} | " + " | ".join(cells) + " |")
    med = []
    for b in labels:
        ts = [last[(b, q)]["total_s"] for q, _, _ in QUESTIONS if (b, q) in last]
        rej = sum(last[(b, q)]["failed_validations"] for q, _, _ in QUESTIONS if (b, q) in last)
        med.append(f"median **{statistics.median(ts):.1f} s** over {len(ts)}, "
                   f"{rej} failed validation(s)" if ts else "—")
    lines.append("| | **Median / total rejections** | " + " | ".join(med) + " |")
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--label")
    p.add_argument("--api")
    p.add_argument("--only", default="")
    p.add_argument("--report", nargs="*")
    a = p.parse_args()
    if a.report is not None:
        print(report(a.report or ["roundh", "v5"]))
        return 0
    chosen = [q for q in QUESTIONS if not a.only or q[0] in a.only.split(",")]
    for qid, domain, question in chosen:
        if used() >= CAP:
            print(f"STOP: {CAP} live Ask runs already logged in {LOG}; nothing sent.")
            return 2
        r = ask(a.api.rstrip("/"), a.label, qid, domain, question)
        print(f"{a.label} {qid} {r['state']:<10} total {r.get('total_s')}s "
              f"und {r.get('understanding_s')} query {r.get('query_s')} "
              f"final {r.get('finalize_s')} valid {r.get('validation_s')} "
              f"calls {r['model_calls']} rejected {r['failed_validations']} "
              f"published {r['published']}  [{used()}/{CAP}]", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
