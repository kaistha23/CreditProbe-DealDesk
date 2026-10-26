"""Time the Cockpit's Ask on its 5 suggested questions per book (INBOX Item 3, B1).

Usage (needs the one app running and a valid key in the Cockpit's environment;
on the Mac the key comes from the Keychain through ops/cockpit.sh):

    .venv/bin/python ops/ask_timing.py [cockpit_api] [--mode standard|deep] [--book corporate|retail]

For each question: starts a run through the frozen Cockpit API (POST /runs),
polls it to a terminal state, and reads its event log. Records the time to a
terminal state, the final state, how many answer validations failed (and the
validator's messages), and how many model generations ran. Writes
evidence/v5/cockpit/ask_timing-<utc>.json. GET/POST to the public API only;
nothing frozen is changed.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

V5 = Path(__file__).resolve().parents[1]
ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
API = (ARGS[0] if ARGS else "http://127.0.0.1:8500").rstrip("/") + "/api/v1/cockpit-v4"
MODE = sys.argv[sys.argv.index("--mode") + 1] if "--mode" in sys.argv else "standard"
BOOKS = [sys.argv[sys.argv.index("--book") + 1]] if "--book" in sys.argv else ["corporate", "retail"]
#: The suggested questions as the Cockpit offers them
#: (frontend/src/components/cockpit-v4/domain-meta.ts PROMPT_TEMPLATES).
PROMPTS = {
    "corporate": ["What is driving Stage 2 and ECL growth?", "Which sectors deteriorated most this quarter?",
                  "Show EAD by sector for the latest quarter.", "Which borrowers were downgraded this quarter?",
                  "Why is risk building across the corporate book?"],
    "retail": ["Which products saw the largest Stage 2 increase this month?", "Where is delinquency building?",
               "Which behavioural score bands deteriorated most?", "Show retail EAD by product for the latest month.",
               "Why is risk building across the retail book?"],
}
LIMIT_SECONDS = 420


def call(path: str, body: dict | None = None):
    req = urllib.request.Request(API + path, method="POST" if body is not None else "GET",
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def one(book: str, question: str) -> dict:
    t0 = time.time()
    try:
        run = call("/runs", {"question": question, "domain": book, "mode": MODE})
    except Exception as e:  # noqa: BLE001
        return {"book": book, "question": question, "state": "not_started", "error": str(e)[:300]}
    run_id = run.get("run_id") or run.get("id")
    state = {}
    while time.time() - t0 < LIMIT_SECONDS:
        state = call(f"/runs/{run_id}")
        if state.get("terminal"):
            break
        time.sleep(1.0)
    seconds = round(time.time() - t0, 1)
    try:
        events = call(f"/runs/{run_id}/events")
    except Exception:  # noqa: BLE001
        events = {}
    items = events.get("events", events if isinstance(events, list) else [])
    text = [json.dumps(e) for e in items]
    rejected = [t for t in text if "ANSWER_VALIDATED" in t and ("reject" in t.lower() or "fail" in t.lower())]
    return {"book": book, "question": question, "run_id": run_id, "state": state.get("state"),
            "seconds": seconds, "terminal": bool(state.get("terminal")),
            "failed_validations": len(rejected), "validation_messages": [t[:400] for t in rejected],
            "generations": sum(1 for t in text if "GENERATION" in t.upper() and "START" in t.upper()),
            "events": len(items)}


def main() -> int:
    out = {"api": API, "mode": MODE, "utc": datetime.now(timezone.utc).isoformat(), "runs": []}
    for book in BOOKS:
        for q in PROMPTS[book]:
            r = one(book, q)
            out["runs"].append(r)
            print(f"{book:9s} {r.get('seconds', '-'):>6}s  {r.get('state')!s:12s} "
                  f"failed validations {r.get('failed_validations', '-')}  {q}", flush=True)
    path = V5 / "evidence" / "v5" / "cockpit" / f"ask_timing-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1))
    print(f"written {path.relative_to(V5)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
