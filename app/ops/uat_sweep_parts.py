"""Run the UAT sweep part by part, each in its own browser process, and merge the report.

Same parts, same steps, same checks as `ops/uat_sweep.py` (which runs them in one browser). Why: the cloud
container has 8 GB; one long browser session plus every v5 service ran out of memory (PLAN_R5 Session E,
gate of 2026-10-11 23:09 UTC: "Page crashed" and services killed by the kernel). Between parts every v5 service
is health-checked, and `ops/v5.sh start` brings back any that is down (it starts only what is not running).

    .venv/bin/python ops/uat_sweep_parts.py        writes evidence/v5/ews/uat_sweep/{uat_sweep.json,SUMMARY.md,*.png}
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

V5 = Path(__file__).resolve().parents[1]
OUT = V5 / "evidence" / "v5" / "ews" / "uat_sweep"
WORK = V5 / "var" / "sweep_parts"
GROUPS = [
    "cockpit,corporate,retail,modules", "core,share,graph", "attention,labels", "workspace,work,exports",
    "home,cohort", "mail", "scorecard", "playbook", "ai_work", "dealdesk", "r4-cards", "r4-b360", "r4-ews",
    "r4-scorecard,r4-g1", "r4-data", "r5-ews-story",
]
HEALTH = {8500: "/api/v1/cockpit-v4/domains", 8501: "/api/v1/ews/health", 5500: "/"}
PORTS = (8502, 8503, 8504, 8505, 8506, 8507, 8508)


def up(port: int, path: str = "/") -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=60):
            return True
    except urllib.error.HTTPError:
        return True  # it answered
    except Exception:  # noqa: BLE001
        return False


def ensure_services() -> None:
    down = [p for p, path in HEALTH.items() if not up(p, path)] + [p for p in PORTS if not up(p)]
    if down:
        # ops/cockpit.sh refuses to start the Cockpit API while the UI holds 5500, so a Cockpit API or UI that
        # is down means a full stop and start; a module service alone is started by ops/v5.sh start.
        full = any(p in down for p in (8500, 5500))
        print(f"  services down {down}: ops/v5.sh {'stop + start' if full else 'start'}", flush=True)
        if full:
            subprocess.run(["ops/v5.sh", "stop"], cwd=V5, capture_output=True, text=True, timeout=600)
        subprocess.run(["ops/v5.sh", "start"], cwd=V5, capture_output=True, text=True, timeout=900)


def main() -> int:
    py = sys.executable
    if WORK.exists():
        shutil.rmtree(WORK)
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.png"):
        old.unlink()
    steps, records, seconds, started = [], {}, 0, None
    for i, group in enumerate(GROUPS):
        ensure_services()
        out = WORK / f"{i:02d}"
        print(f"[{i + 1}/{len(GROUPS)}] {group}", flush=True)
        subprocess.run([py, "ops/uat_sweep.py", "--only", group], cwd=V5, env={**os.environ, "SWEEP_OUT": str(out)},
                       capture_output=True, text=True, timeout=5400)
        try:
            rep = json.loads((out / "uat_sweep.json").read_text())
        except Exception as e:  # noqa: BLE001
            steps.append({"n": 0, "book": "-", "uat_step": "-", "title": f"part {group} produced no report",
                          "pass": False, "checks": [{"check": "report written", "pass": False,
                                                     "expected": "uat_sweep.json", "seen": str(e)[:200]}],
                          "errors": []})
            continue
        started = started or rep.get("started_utc")
        seconds += rep.get("seconds", 0)
        records.update(rep.get("records") or {})
        for x in rep["results"]:
            steps.append(x)
        for png in out.glob("*.png"):
            shutil.copy(png, OUT / f"p{i:02d}_{png.name}")
        print(f"   {rep['steps'] - rep['failed_steps']}/{rep['steps']} steps", flush=True)
    for n, x in enumerate(steps, 1):
        x["n"] = n
    failed = [x for x in steps if not x["pass"]]
    checks = sum(len(x["checks"]) for x in steps)
    report = {"runner": "ops/uat_sweep_parts.py", "groups": GROUPS, "started_utc": started, "seconds": seconds,
              "steps": len(steps), "checks": checks, "failed_steps": len(failed), "passed": not failed,
              "records": records, "results": steps}
    (OUT / "uat_sweep.json").write_text(json.dumps(report, indent=1, default=str))
    lines = [f"# UAT sweep: {len(steps) - len(failed)}/{len(steps)} steps passed, {checks} checks", "",
             f"Run part by part (ops/uat_sweep_parts.py) · {started} · {seconds} s", "",
             "| # | Book | UAT step | Step | Checks | Errors | Result |", "|---|---|---|---|---|---|---|"]
    for x in steps:
        lines.append(f"| {x['n']} | {x['book']} | {x['uat_step']} | {x['title']} | "
                     f"{sum(c['pass'] for c in x['checks'])}/{len(x['checks'])} | {len(x['errors'])} | "
                     f"{'PASS' if x['pass'] else 'FAIL'} |")
    (OUT / "SUMMARY.md").write_text("\n".join(lines) + "\n")
    print(f"\n{len(steps) - len(failed)}/{len(steps)} sweep steps passed ({checks} checks)")
    for x in failed[:30]:
        bad = [c for c in x["checks"] if not c["pass"]]
        print(f"  FAIL [{x['n']}] {x['book']} {x['title']}: {bad[:2]} {x['errors'][:2]}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
