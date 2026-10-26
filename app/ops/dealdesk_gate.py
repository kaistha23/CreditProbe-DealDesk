"""The Deal Desk engine gate where the one app is not running (a cloud container).

    python3 ops/dealdesk_gate.py

Runs gate items 1-3 of ops/gate.py for the `dealdesk` module: the frozen guard, every sync
test, the Deal Desk module tests (tests/v5/dealdesk, tests/dealdesk golden workbook) and the
domain build check. Items 4-6 (Cockpit live panels, browser smoke, UI sweep) need the one app
(`python -m ops.gate dealdesk` on the Mac). Writes evidence/v5/gate/dealdesk-engine-<utc>.json.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

V5 = Path(__file__).resolve().parents[1]
OUT = V5 / "evidence" / "v5" / "gate"


def run(cmd: list[str]) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=V5, capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr)


def main() -> int:
    items = []

    def item(name: str, code: int, out: str, t0: float) -> None:
        lines = [ln for ln in out.strip().splitlines() if ln.strip()]
        last = [ln for ln in lines if " passed" in ln or " failed" in ln or "PASS" in ln or "FAIL" in ln][-1:] or lines[-1:] or [""]
        items.append({"item": name, "pass": code == 0, "detail": last[0][:400], "seconds": round(time.time() - t0, 1)})
        print(("PASS " if code == 0 else "FAIL ") + name + f"  [{last[0][:200]}]", flush=True)

    py = sys.executable
    t = time.time(); c, o = run([py, "ops/frozen_guard.py"]); item("1. frozen guard", c, o, t)
    sync = sorted(str(p.relative_to(V5)) for p in (V5 / "tests/v5").glob("test_sync_*.py"))
    t = time.time(); c, o = run([py, "-m", "pytest", "-p", "no:cacheprovider", *sync]); item("2. sync tests", c, o, t)
    t = time.time(); c, o = run([py, "-m", "pytest", "-p", "no:cacheprovider", "tests/v5/dealdesk", "tests/dealdesk", "tests/v5/data_builder",
                                 "tests/v5/test_ratings.py"]); item("3a. dealdesk tests", c, o, t)
    t = time.time(); c, o = run([py, "ops/dealdesk_build.py", "--check"]); item("3b. domain build check", c, o, t)
    # R5: the thread layer (conversation, Word report with the proposal in full and the method appendix, Playbook section)
    t = time.time(); c, o = run([py, "-m", "pytest", "-p", "no:cacheprovider", "tests/v5/dealdesk_ui"]); item("3c. dealdesk thread tests", c, o, t)
    ok = all(i["pass"] for i in items)
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=V5, capture_output=True, text=True).stdout.strip()
    (OUT / f"dealdesk-engine-{stamp}.json").write_text(json.dumps(
        {"module": "dealdesk", "scope": "engine gate items 1-3 (no one-app in this runtime)", "commit": commit,
         "at": stamp, "pass": ok, "items": items}, indent=1))
    print("DEALDESK ENGINE GATE", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
