"""R11 smoke (PLAN_R11 Session M): every v5 service healthy, then one call per R11 surface.

    .venv/bin/python ops/smoke_r11.py [--services-only]

CHECKS lists the services the demo needs, including the R11 agents service (agents_v5, 8517). The R11 calls run on
DD-01 (Optimise, forward risk, Stress Lab, pipeline test, review, house-style draft) and the Committee Preparation
agent with the deterministic planner. Prints one line per check and "n of N checks passed"; exit 1 on any failure.
No secret is read or printed.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request

CHECKS = [  # name, port, health path
    ("cockpit", 8500, "/health"),
    ("ews", 8501, "/api/v1/ews/health"),
    ("b360", 8502, "/api/v1/b360/health"),
    ("whatif", 8503, "/api/v1/whatif/health"),
    ("data_builder", 8504, "/api/v1/data/health"),
    ("workspace", 8505, "/api/v1/workspace/health"),
    ("playbook", 8506, "/api/v1/playbook/health"),
    ("scorecard", 8507, "/api/v1/scorecard/health"),
    ("dealdesk", 8508, "/api/v1/dealdesk/desk/health"),
    ("lenses", 8509, "/api/v1/lenses/health"),
    ("admin", 8510, "/api/v1/admin/health"),
    ("queries", 8516, "/api/v1/queries/health"),
    ("agents", 8517, "/api/v1/agents/health"),
]
DD = "http://127.0.0.1:8508/api/v1/dealdesk"
AG = "http://127.0.0.1:8517/api/v1/agents"
results: list[tuple[str, bool, str]] = []


def call(method: str, url: str, body: dict | None = None, timeout: float = 180) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw[:1] in (b"{", b"[") else {})
    except urllib.error.HTTPError as e:
        return e.code, {}
    except Exception as e:  # noqa: BLE001 - a smoke reports, it does not raise
        return 0, {"error": type(e).__name__}


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  ' + detail) if detail else ''}", flush=True)


def main() -> int:
    only = "--services-only" in sys.argv
    for name, port, path in CHECKS:
        st, _ = call("GET", f"http://127.0.0.1:{port}{path}", timeout=10)
        check(f"service {name} ({port})", st == 200, f"HTTP {st}")
    if not only:
        t = time.time()
        st, fr = call("POST", f"{DD}/proposals/DD-01/forward-risk", {})
        check("forward risk DD-01", st == 200 and bool(fr.get("answer")), f"{time.time() - t:.1f}s")
        t = time.time()
        st, sr = call("POST", f"{DD}/proposals/DD-01/stress", {})
        check("Stress Lab DD-01", st == 200 and bool(sr.get("answer")), f"{time.time() - t:.1f}s")
        t = time.time()
        st, pt = call("POST", f"{DD}/proposals/DD-01/pipeline-test", {})
        check("pipeline test DD-01", st == 200 and "verdict" in pt, f"{time.time() - t:.1f}s")
        st, ra = call("GET", f"{DD}/risk-appetite")
        check("risk appetite", st == 200 and bool(ra.get("rows")), f"{len(ra.get('rows') or [])} rows")
        t = time.time()
        st, rv = call("POST", f"{DD}/proposals/PRP-A-GMC/review", {})
        check("review Case A", st == 200 and bool(rv.get("findings")), f"{len(rv.get('findings') or [])} findings, {time.time() - t:.1f}s")
        t = time.time()
        st, dr = call("POST", f"{DD}/proposals/DD-01/draft", {})
        check("house-style draft DD-01", st == 200 and bool(dr.get("sections")), f"{time.time() - t:.1f}s")
        st, ag = call("GET", AG)
        ids = sorted(a.get("agent_id") or a.get("id") or "" for a in (ag.get("agents") or [])) if isinstance(ag, dict) else []
        check("agents registered", {"dealdesk.committee", "ews.triage", "whatif.scenarios", "lenses.monitoring"} <= set(ids),
              ", ".join(ids))
        t = time.time()
        st, run = call("POST", f"{AG}/dealdesk.committee/runs",
                       {"goal": "Prepare DD-01 for committee", "context": {"proposal_id": "DD-01"}, "planner": "deterministic", "wait": True}, 300)
        check("Committee Preparation agent DD-01 (deterministic)", st == 200 and run.get("status") in ("completed", "partial"),
              f"{run.get('status')} {time.time() - t:.1f}s")
    n = sum(ok for _, ok, _ in results)
    print(f"{n} of {len(results)} checks passed")
    return 0 if n == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
