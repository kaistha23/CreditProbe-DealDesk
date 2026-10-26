"""Re-run chosen items of the v5 gate (ops/gate.py) and write their own evidence file.

Usage: .venv/bin/python -m ops.gate_items <module> <item>[,<item>...]     items: 1 2 3 4a 4b 5 6 6p

Item 6p is the UAT sweep run part by part (`ops/uat_sweep.py --only <part>`, every part the full sweep runs, in its
order): the same steps and checks, but between parts any service the container's memory limit stopped is started
again, and the module services are restarted when memory runs low. The parts' results are summed into one report
(evidence/v5/gate/<module>-sweep-parts-<utc>.json) with every failing step listed.

For a gate whose items were already run once at the same commit, after an item failed for a reason outside the code
(the cloud container's memory) or after a fix that touches only that item. Same commands, same pass rules as
ops/gate.py; with GATE_PAUSE_COCKPIT=1 the Cockpit API and UI are stopped for 3 and 4a and started again after.
The evidence (evidence/v5/gate/<module>-items-<utc>.json) names the items run, so it is never read as a full gate.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

from ops import gate as g


def sweep_parts() -> list[str]:
    """The part names of ops/uat_sweep.py, in the order the full sweep runs them (SWEEP_PARTS=a,b: only those)."""
    import re
    if os.environ.get("SWEEP_PARTS"):
        return os.environ["SWEEP_PARTS"].split(",")
    src = (g.V5 / "ops/uat_sweep.py").read_text()
    body = src[src.index('for name, part in [("cockpit"'):]
    body = body[: body.index("if \"--only\" in sys.argv")]
    names: list[str] = []
    for m in re.finditer(r'\("([a-z0-9_-]+)", lambda|for book in BOOKS|for p in \(([^)]*)\)', body):
        if m.group(1):
            names.append(m.group(1))
        elif m.group(0).startswith("for book"):
            names += ["corporate", "retail"]
        else:
            names += [f"r4-{x}" for x in re.findall(r'"([a-z0-9_-]+)"', m.group(2))]
    return names


def _free_mb() -> int:
    for ln in open("/proc/meminfo"):
        if ln.startswith("MemAvailable:"):
            return int(ln.split()[1]) // 1024
    return 10_000


def _ui_up() -> bool:
    return g.run(["curl", "-fsS", "-o", "/dev/null", "-m", "90", "http://127.0.0.1:5500/login"], timeout=120)[0] == 0


def heal() -> list[str]:
    """Start again whatever the memory limit stopped; restart the module services when memory is low."""
    did = []
    if _free_mb() < 2500:
        g.run(["bash", "ops/v5.sh", "stop-modules"], timeout=300)
        did.append(f"modules restarted ({_free_mb()} MB free)")
    status = g.run(["bash", "ops/v5.sh", "status"], timeout=300)[1]
    if not _ui_up():
        g.run(["bash", "ops/cockpit.sh", "stop"], timeout=300)
        did.append("Cockpit API and UI restarted")
    if "down" in status or did:
        subprocess.run(["bash", "ops/v5.sh", "start"], cwd=g.V5, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=900)
        did.append("ops/v5.sh start")
        for _ in range(60):
            if _ui_up():
                break
            time.sleep(5)
    return did


def run_parts(module: str) -> tuple[bool, str, dict]:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_root = g.VAR / f"sweep_parts_{stamp}"
    steps, notes = [], []
    for part in sweep_parts():
        did = heal()
        if did:
            notes.append({"before": part, "did": did})
        out = out_root / part
        out.mkdir(parents=True, exist_ok=True)
        g.run([g.BROWSER_PY, "ops/uat_sweep.py", "--only", part], {"SWEEP_OUT": str(out)}, timeout=5400)
        try:
            rep = json.loads((out / "uat_sweep.json").read_text())
            for st in rep["results"]:
                st["part"] = part
            steps += rep["results"]
        except (OSError, ValueError, KeyError):
            steps.append({"part": part, "pass": False, "checks": [{"check": "part report written", "pass": False}],
                          "title": f"part {part} wrote no report"})
        print(f"  part {part}: {sum(1 for x in steps if x.get('part') == part and x['pass'])}/"
              f"{sum(1 for x in steps if x.get('part') == part)} steps", flush=True)
    failed = [x for x in steps if not x["pass"]]
    checks = sum(len(x.get("checks") or []) for x in steps)
    report = {"module": module, "utc": stamp, "steps": len(steps), "checks": checks, "failed_steps": len(failed),
              "passed": not failed, "healing": notes, "failed": failed, "parts": sweep_parts()}
    (g.OUT / f"{module}-sweep-parts-{stamp}.json").write_text(json.dumps(report, indent=1, default=str))
    return not failed, f"{len(steps) - len(failed)}/{len(steps)} sweep steps passed ({checks} checks), in parts", report


def main() -> int:
    module, wanted = sys.argv[1], set(sys.argv[2].split(","))
    g.VAR.mkdir(parents=True, exist_ok=True)
    items: list[dict] = []

    def item(name, ok, detail="", seconds=0.0):
        items.append({"item": name, "pass": bool(ok), "detail": detail, "seconds": round(seconds, 1)})
        print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""), flush=True)

    spec = g.MODULES[module]
    if "1" in wanted:
        t = time.time(); code, tail = g.run([g.PY, "ops/frozen_guard.py"])
        item("1. frozen guard", code == 0, tail.strip().splitlines()[-1], time.time() - t)
    if "2" in wanted:
        files = sorted(str(p.relative_to(g.V5)) for p in (g.V5 / "tests/v5").glob("test_sync_*.py"))
        t = time.time(); total, failed, _ = g.pytest(files, "sync")
        item("2. sync tests", total > 0 and not failed, f"{total - len(failed)}/{total}", time.time() - t)
    # GATE_PAUSE_COCKPIT=1 stops the Cockpit API and UI for 3 and 4a; =all stops every service (the Cockpit test
    # test_domains.py alone needs more than 4 GB) and starts the Early Warning API for the live API runner.
    mode = os.environ.get("GATE_PAUSE_COCKPIT", "")
    pause = mode in ("1", "all") and bool(wanted & {"3", "4a"})
    if pause:
        g.run(["bash", "ops/v5.sh", "stop"] if mode == "all" else ["bash", "ops/cockpit.sh", "stop"], timeout=600)
    if "3" in wanted:
        t = time.time(); total, failed, _ = g.pytest(spec["pytest"], module)
        item(f"3a. {module} tests", total > 0 and not failed,
             f"{total - len(failed)}/{total}" + (f" failed: {sorted(failed)}" if failed else ""), time.time() - t)
        if mode == "all":
            g.run(["bash", "ops/v5.sh", "start-ews"], timeout=600)
        for name, cmd, env in spec["runners"]:
            env = dict(env)
            cwd = g.V5 / env.pop("__cwd") if "__cwd" in env else g.V5
            t = time.time(); code, tail = g.run(cmd, env, cwd)
            summary = [ln for ln in tail.splitlines() if any(k in ln for k in ("passed", "pass ", "tests ", "fail "))][-3:]
            item(f"3b. {name}", code == 0, " | ".join(s.strip() for s in summary), time.time() - t)
    if "4a" in wanted:
        if mode == "all":
            g.run(["bash", "ops/v5.sh", "stop-ews"], timeout=600)
        t = time.time(); total, failed, _ = g.pytest(["tests/cockpit_v4"], "cockpit_v4")
        unexpected = sorted(failed - g.DECLARED_COCKPIT_EXCEPTIONS)
        vanished = sorted(g.DECLARED_COCKPIT_EXCEPTIONS - failed)
        item("4a. Cockpit suite tests/cockpit_v4", total > 1000 and not unexpected and not vanished,
             f"{total - len(failed)}/{total} pass; {len(failed & g.DECLARED_COCKPIT_EXCEPTIONS)} declared exceptions"
             + (f"; UNEXPECTED failures: {unexpected}" if unexpected else "")
             + (f"; declared exceptions now passing: {vanished}" if vanished else ""), time.time() - t)
        g.run(["git", "checkout", "--", "docs/cockpit_v4/evidence"])
    if pause:
        t = time.time()
        subprocess.Popen(["bash", "ops/v5.sh", "start"], cwd=g.V5, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
        ready = False
        for _ in range(120):
            time.sleep(5)
            if g.run(["curl", "-fsS", "-o", "/dev/null", "-m", "60", "http://127.0.0.1:5500/login"], timeout=90)[0] == 0:
                ready = True
                break
        item("4-. Cockpit API and UI started again", ready, "http://127.0.0.1:5500", time.time() - t)
    if "4b" in wanted:
        t = time.time()
        snap = g.VAR / "gate_snapshots"
        code1, _ = g.run([g.PY, "ops/snapshot_cockpit.py", "http://127.0.0.1:8500", str(snap)])
        code2, tail = g.run([g.PY, "ops/compare_snapshots.py", "evidence/v5/foundation/after_ews_story", str(snap), "1.0",
                             str(g.VAR / "gate_snapshot_compare.json")])
        item("4b. Cockpit panels equal the post-rescale baseline", code1 == 0 and code2 == 0,
             [ln for ln in tail.splitlines() if "PROBLEMS" in ln][-1:][0] if "PROBLEMS" in tail else tail[-200:],
             time.time() - t)
    if "5" in wanted:
        t = time.time(); code, tail = g.run([g.BROWSER_PY, "ops/browser_smoke.py"])
        item("5. browser smoke", code == 0, [ln for ln in tail.splitlines() if "checks passed" in ln][-1:][0]
             if "checks passed" in tail else tail[-300:], time.time() - t)
    if "6" in wanted:
        t = time.time(); code, tail = g.run([g.BROWSER_PY, "ops/uat_sweep.py", *spec.get("sweep", [])])
        item("6. UAT sweep", code == 0, [ln for ln in tail.splitlines() if "sweep steps passed" in ln][-1:][0]
             if "sweep steps passed" in tail else tail[-300:], time.time() - t)

    if "6p" in wanted:
        t = time.time(); ok, detail, _ = run_parts(module)
        item("6. UAT sweep (in parts)", ok, detail, time.time() - t)

    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=g.V5, capture_output=True, text=True).stdout.strip()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report = {"module": module, "commit": sha, "utc": stamp, "items_run": sorted(wanted),
              "passed": all(i["pass"] for i in items), "items": items}
    g.OUT.mkdir(parents=True, exist_ok=True)
    (g.OUT / f"{module}-items-{stamp}.json").write_text(json.dumps(report, indent=1))
    print(("ITEMS PASS" if report["passed"] else "ITEMS FAIL") + f" · {module} {sorted(wanted)} @ {sha} · "
          f"evidence/v5/gate/{module}-items-{stamp}.json")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
