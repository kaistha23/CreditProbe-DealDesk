#!/usr/bin/env python3
"""R15 x: warm everything the client demo script opens (docs/v5/DEMO_SCRIPT.md), so no screen is cold in front of the client.

    .venv/bin/python ops/r15_demo_warm.py            # after ops/demo.sh start (≈ 3–6 min the first time, seconds after)
    .venv/bin/python ops/r15_demo_warm.py --quick    # skip the slow optional items (DD-02, DD-06)

It calls the running services over HTTP on 127.0.0.1 (the same ports as ops/v5.sh), so the caches it fills are the
services' own in-process caches, exactly what the UI then reads. Standard library only (N9: nothing installed). No
password is read or printed: the Deal Desk, Noor, Early Warning, Borrower 360, agents and What-If read endpoints the
script calls need no session. It never changes a decision: no approval, no monitoring proposal, no stage change. It
does not create Lenses or What-If threads (those would appear in the client's "Recent" lists).

Order: the slowest first (Deal Desk structure sets, recommendation, bank-form proposal), then stress and Noor's
answer on the stress run with its cheapest fix, the proposal checks, the brief's issue view, Early Warning, the
triage agent, Who to call, Borrower 360, the inspection pack, What-If and Lenses reads; it ends with the
**half-baked** proposal check on R14-RWQ so that is the run the client sees first (DEMO_SCRIPT step 10).

Each line prints OK / SLOW (> 20 s) / FAILED with the time; exit code 1 if anything failed.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

H = "http://127.0.0.1"
P = {k: int(os.environ.get(v, d)) for k, v, d in [
    ("dealdesk", "DEALDESK_API_PORT", 8508), ("ews", "EWS_API_PORT", 8501), ("b360", "B360_API_PORT", 8502),
    ("whatif", "WHATIF_API_PORT", 8503), ("lenses", "LENSES_API_PORT", 8509), ("agents", "AGENTS_API_PORT", 8517),
    ("data", "DATA_BUILDER_PORT", 8504)]}

# The deals the script opens (fictional): the deal to committee, the half-baked RM proposal, the monitoring queue deal.
DEAL = "R12-TWA"
RWQ = "R14-RWQ"
SLOW_S = 20.0
results: list[tuple[str, str, float, str]] = []


def call(label: str, svc: str, path: str, body: dict | None = None, method: str | None = None,
         timeout: float = 300.0, raw: bool = False) -> object | None:
    url = f"{H}:{P[svc]}{path}"
    data = None if body is None else json.dumps(body).encode()
    if raw and body is None and method == "POST":
        data = b""
    req = urllib.request.Request(url, data=data, method=method or ("POST" if data is not None else "GET"),
                                 headers={"Content-Type": "application/json"} if data is not None else {})
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - fixed loopback origin
            out = r.read()
        s = time.time() - t
        status = "SLOW" if s > SLOW_S else "OK"
        results.append((label, status, s, ""))
        print(f"{status:6} {s:6.1f} s  {label}", flush=True)
        try:
            return json.loads(out or b"null")
        except ValueError:
            return None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        s = time.time() - t
        why = getattr(e, "code", "") or getattr(e, "reason", "") or e
        results.append((label, "FAILED", s, str(why)))
        print(f"FAILED {s:6.1f} s  {label}: {why}", flush=True)
        return None


def health() -> bool:
    ok = True
    for svc, path in [("dealdesk", "/api/v1/dealdesk/desk/health"), ("ews", "/api/v1/ews/health"), ("b360", "/api/v1/b360/health"),
                      ("whatif", "/api/v1/whatif/health"), ("lenses", "/api/v1/lenses/health"),
                      ("agents", "/api/v1/agents/health")]:
        try:
            with urllib.request.urlopen(f"{H}:{P[svc]}{path}", timeout=10):  # noqa: S310
                pass
        except Exception as e:  # noqa: BLE001
            print(f"STOP?  {svc} is not answering on {P[svc]} ({e}); start the demo first (ops/demo.sh start).")
            ok = ok and svc not in ("dealdesk",)
    return ok


def deal(pid: str, full: bool = True) -> None:
    dd = f"/api/v1/dealdesk/proposals/{pid}"
    call(f"{pid} structure set (first open of the deal: 20–100 s cold)", "dealdesk", f"{dd}/structure-set")
    call(f"{pid} review", "dealdesk", f"{dd}/review", {"refresh": False})
    if not full:
        return
    call(f"{pid} thread and analysis", "dealdesk", f"/api/v1/dealdesk/desk/proposals/{pid}/analysis")
    for part in ("account_behaviour", "group/swot"):
        call(f"{pid} {part}", "dealdesk", f"{dd}/{part}")
    for part in ("capacity", "raroc-bridge"):
        call(f"{pid} {part}", "dealdesk", f"/api/v1/dealdesk/engines/{pid}/{part}")
    call(f"{pid} recommendation (up to 100 s cold)", "dealdesk", f"{dd}/recommendation-r14")
    call(f"{pid} bank-form credit proposal (≈ 60 s cold)", "dealdesk", f"{dd}/credit-proposal")


def main(argv: list[str]) -> int:
    quick = "--quick" in argv
    t0 = time.time()
    print("Warming the R15 demo (docs/v5/DEMO_SCRIPT.md) ...", flush=True)
    if not health():
        return 1

    # Act 3 first: the slow Deal Desk computations.
    deal(DEAL)
    call(f"{DEAL} stress run (Recommended + Ask)", "dealdesk", f"/api/v1/dealdesk/proposals/{DEAL}/stress-matrix",
         {"keys": ["recommended", "ask"], "force": []})
    q = "how is this failing on all stress scenario?"
    call(f"Noor on {DEAL} Stress (step 15)", "dealdesk", "/api/v1/noor/here",
         {"question": q, "context": {"deal_id": DEAL, "step": "stress", "structures": ["recommended", "ask"]}})
    call(f"Noor cheapest fix on {DEAL} (10–20 s cold)", "dealdesk", "/api/v1/noor/here/fix",
         {"deal_id": DEAL, "from_key": "recommended", "target": "moderate"})
    deal(RWQ, full=False)
    call("Check all pending proposals (≈ 13 s)", "dealdesk", "/api/v1/dealdesk/proposal-check/batch", method="POST", raw=True)
    call(f"{RWQ} corrected proposal check", "dealdesk", f"/api/v1/dealdesk/proposals/{RWQ}/proposal-check?demo=corrected",
         method="POST", raw=True)
    if not quick:
        for pid in ("DD-06", "DD-02"):
            deal(pid, full=False)

    # Act 4.
    call("Monitoring page", "dealdesk", "/api/v1/dealdesk/monitoring/page")
    call("Book (going bad)", "dealdesk", "/api/v1/dealdesk/book")
    call("Inspection responder: auditor sample", "dealdesk", "/api/v1/intel/governance/inspection",
         {"request": "The auditor asks for the approvals, conditions and stage history of the 5 largest Stage 3 "
                     "borrowers in Construction", "sample": []})

    # Acts 1 and 2.
    call("Brief line 1 issue view (CRM-9.23)", "dealdesk", "/api/v1/regulatory/issues/crm%3ACRM-9.23")
    for path in ("/api/v1/ews/meta", "/api/v1/ews/level", "/api/v1/ews/crm", "/api/v1/ews/intel/ecl-impact"):
        call(f"Early Warning {path.rsplit('/', 1)[-1]}", "ews", path)
    run = call("Triage agent run (deterministic, ≈ 6 s)", "agents", "/api/v1/agents/ews.triage/runs",
               {"goal": "Triage this period's warnings", "context": {"domain": "corporate", "period": "2026Q2"},
                "planner": "auto"})
    rid = (run.get("run_id") or run.get("id")) if isinstance(run, dict) else None
    if rid:
        for _ in range(60):
            r = call(f"triage run {rid} status", "agents", f"/api/v1/agents/runs/{rid}", timeout=30)
            results.pop()  # status polls are not items
            st = (r or {}).get("status") if isinstance(r, dict) else None
            if st and st not in ("planning", "running", "queued"):
                print(f"       triage run finished: {st}", flush=True)
                break
            time.sleep(2)
    call("Who to call", "dealdesk", "/api/v1/intel/calls")
    call("Borrower 360 list", "b360", "/api/v1/b360/list")
    for cid in ("CB00002", "CB01312"):
        call(f"Borrower 360 {cid}", "b360", f"/api/v1/b360/customers/{cid}")
        call(f"Borrower 360 {cid} classification", "b360", f"/api/v1/b360/customers/{cid}/classification")
    for path in ("/api/v1/whatif/meta", "/api/v1/whatif/library"):
        call(f"What-If {path.rsplit('/', 1)[-1]}", "whatif", path)
    call("Lenses catalogue", "lenses", "/api/v1/lenses/meta")
    call("Lenses list", "lenses", "/api/v1/lenses/lenses")

    # Last: the half-baked run, so it is the one on screen when the client first sees the Proposal check.
    call(f"{RWQ} half-baked proposal check (the run the client sees)", "dealdesk",
         f"/api/v1/dealdesk/proposals/{RWQ}/proposal-check?demo=half", method="POST", raw=True)

    bad = [r for r in results if r[1] == "FAILED"]
    slow = [r for r in results if r[1] == "SLOW"]
    print(f"\nDone in {time.time() - t0:.0f} s: {len(results)} items, {len(slow)} slow (now warm), {len(bad)} failed.")
    for label, _, _, why in bad:
        print(f"  FAILED: {label}: {why}")
    if not bad:
        print("Ready. Run it again if the Mac slept or a service was restarted.")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
