"""The v5 module test gate (CLAUDE.md). One command, one evidence file.

Usage: .venv/bin/python -m ops.gate <module> [--skip-cockpit-suite]

  1. frozen guard        ops/frozen_guard.py
  2. sync                tests/v5/test_sync_*.py
  3. module tests        tests/v5/<module>, plus the module's own runners
  4. Cockpit regression  tests/cockpit_v4 (all pass except the DECLARED tests
                         that hard-code pre-rescale magnitudes -- and those
                         must still fail, or something else changed), and the
                         live Cockpit panels equal the post-rescale baseline
  5. browser smoke       ops/browser_smoke.py against the running one app
  6. UAT sweep           ops/uat_sweep.py: every UAT step and control, both books

Needs the one app running (ops/v5.sh start). Writes
evidence/v5/gate/<module>-<utc>.json. Exit 1 if any item fails.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

V5 = Path(__file__).resolve().parents[1]
PY = str(V5 / ".venv/bin/python")
# The browser smoke test needs Playwright: on the Mac the workspace venv carries
# it; on Linux (ops/setup_linux.sh) it is in .venv. BROWSER_PY overrides both.
BROWSER_PY = (os.environ.get("BROWSER_PY")
              or next((str(p) for p in (V5.parent / ".venv/bin/python", V5 / ".venv/bin/python")
                       if p.exists() and subprocess.run([str(p), "-c", "import playwright"],
                                                        capture_output=True).returncode == 0), PY))
OUT = V5 / "evidence" / "v5" / "gate"
VAR = V5 / "var" / "pytest"

#: Cockpit tests that assert the pre-rescale magnitudes (docs/v5/RESCALE.md).
DECLARED_COCKPIT_EXCEPTIONS = {
    "tests/cockpit_v4/test_release_history.py::test_the_content_of_the_current_releases_is_what_was_published[v4-saudi-corporate-20q-v4]",
    "tests/cockpit_v4/test_credit_policy.py::test_a_clause_id_is_the_most_precise_way_in",
    "tests/cockpit_v4/test_credit_policy.py::test_a_policy_question_arrives_with_its_clauses_already_attached",
    "tests/cockpit_v4/test_live_uat_matrix_revision.py::test_the_policy_settles_the_measure_l16_was_believed_to_leave_open",
    "tests/cockpit_v4/test_misread_as_product_help.py::test_a_published_answer_carries_the_policy_receipt",
    "tests/cockpit_v4/test_misread_as_product_help.py::test_a_threshold_presented_as_a_limit_with_no_clause_is_refused",
    "tests/cockpit_v4/test_misread_as_product_help.py::test_the_policy_question_reaches_cp_1_1_deterministically",
    "tests/cockpit_v4/test_misread_as_product_help.py::test_the_refusal_says_what_to_do_about_it",
}
# Every policy-literal exception above has a generated twin at the v5 limits
# (ops/make_rescaled_policy_test.py -> tests/cockpit_v4/test_v5_rescaled_*.py)
# that runs in the same suite and must PASS; only the content-digest test has
# no twin (its equivalent is the rescale reconciliation and lake.verify).

MODULES = {
    "queries": {
        # R9 Session F (P7 regulatory response): Queries and BRF studio service, the queries/brf domains.
        "pytest": ["tests/v5/queries", "tests/v5/test_sync_queries_brf.py"],
        "runners": [
            ("queries/brf domain build check", [PY, "-m", "ops.build_queries_domains", "--check"], {}),
            ("frontend unit tests", ["node", "--test", "--experimental-strip-types", "src/**/*.test.ts"], {"__cwd": "frontend"}),
            ("frontend typecheck", ["npx", "tsc", "-p", "tsconfig.gate.json", "--noEmit"], {"__cwd": "frontend"}),
        ],
    },
    "dealdesk": {
        # Deal Desk engine (DEAL_DESK_PROMPT.md phases A-C): module tests, the golden workbook, the domain build check.
        "pytest": ["tests/v5/dealdesk", "tests/dealdesk", "tests/v5/test_ratings.py", "tests/v5/data_builder"],
        "runners": [
            ("Deal Desk domain build check", [PY, "ops/dealdesk_build.py", "--check"], {}),
        ],
    },
    "dealdesk-ui": {
        # Deal Desk phases D-F (Session C2): thread layer, conversation (backend/convo), outputs (Mail, Playbook,
        # Word); the frontend unit tests and typecheck; the UAT sweep part `dealdesk` only.
        "pytest": ["tests/v5/dealdesk_ui", "tests/v5/convo", "tests/v5/playbook", "tests/v5/core", "tests/v5/house_style"],
        "runners": [
            ("frontend unit tests", ["node", "--test", "--experimental-strip-types", "src/**/*.test.ts"], {"__cwd": "frontend"}),
            ("frontend typecheck", ["npx", "tsc", "--noEmit", "-p", "tsconfig.gate.json"], {"__cwd": "frontend"}),
        ],
        "sweep": ["--only", "dealdesk"],
    },
    "ews": {
        # Early Warning plus every v5/next module service (INBOX Item 3).
        "pytest": ["tests/v5/ews", "tests/v5/test_ratings.py", "tests/v5/b360", "tests/v5/whatif",
                   "tests/v5/data_builder", "tests/v5/core", "tests/v5/attention", "tests/v5/house_style", "tests/v5/scorecard",
                   *(["tests/v5/workspace"] if (V5 / "tests/v5/workspace").exists() else []),
                   *(["tests/v5/playbook"] if (V5 / "tests/v5/playbook").exists() else []),
                   *(["tests/v5/convo"] if (V5 / "tests/v5/convo").exists() else []),
                   *(["tests/v5/ai_work"] if (V5 / "tests/v5/ai_work").exists() else [])],
        "runners": [
            ("EWS data suite (restoration)", [PY, "backend/ews_domain/run_data_tests.py"], {}),
            ("EWS live API suite (restoration)", [PY, "backend/ews_domain/run_ui_api_tests.py"],
             {"EWS_API_BASE": "http://127.0.0.1:8501"}),
            ("frontend unit tests", ["node", "--test", "--experimental-strip-types", "src/**/*.test.ts"],
             {"__cwd": "frontend"}),
        ],
    },
}

# PLAN_R5 Session T (v5/r5-threads): the shared thread, its adoption, What-If questions, number formatting.
MODULES["threads"] = {
    "pytest": ["tests/v5/convo", "tests/v5/whatif", "tests/v5/scorecard", "tests/v5/playbook", "tests/v5/ai_work",
               "tests/v5/core", "tests/v5/house_style", "tests/v5/test_format.py"],
    "runners": [
        ("frontend unit tests", ["node", "--test", "--experimental-strip-types", "src/**/*.test.ts"], {"__cwd": "frontend"}),
        ("frontend typecheck", ["npx", "tsc", "--noEmit", "-p", "tsconfig.gate.json"], {"__cwd": "frontend"}),
    ],
    "sweep": ["--only", "r5-threads"],
}

# PLAN_R5 Session L: Lenses (service 8509): its tests, the convo layer, the frontend unit tests and typecheck, and the
# UAT sweep part `lenses`.
MODULES["lenses"] = {
    "pytest": ["tests/v5/lenses", "tests/v5/convo", "tests/v5/house_style", "tests/v5/core"],
    "runners": [
        ("frontend unit tests", ["node", "--test", "--experimental-strip-types", "src/**/*.test.ts"], {"__cwd": "frontend"}),
        ("frontend typecheck", ["npx", "tsc", "--noEmit", "-p", "tsconfig.gate.json"], {"__cwd": "frontend"}),
    ],
    "sweep": ["--only", "lenses"],
}

# PLAN_R5 Session A: the Admin console and data access. backend/access sits in every v5 service and in backend/convo,
# so the gate runs every module's tests (the R4 set) plus the Admin tests; the sweep part is `admin`.
MODULES["admin"] = {
    "pytest": ["tests/v5/admin", *[p for p in ["tests/v5/ews", "tests/v5/test_ratings.py", "tests/v5/b360", "tests/v5/whatif",
                                                "tests/v5/data_builder", "tests/v5/core", "tests/v5/attention", "tests/v5/house_style",
                                                "tests/v5/scorecard", "tests/v5/workspace", "tests/v5/playbook", "tests/v5/convo",
                                                "tests/v5/ai_work", "tests/v5/dealdesk", "tests/dealdesk", "tests/v5/dealdesk_ui",
                                                "tests/v5/test_format.py"]
                                    if (V5 / p).exists()]],
    "runners": [
        ("Admin domain build check", [PY, "-m", "backend.admin.build", "--check"], {}),
        ("frontend unit tests", ["node", "--test", "--experimental-strip-types", "src/**/*.test.ts"], {"__cwd": "frontend"}),
        ("frontend typecheck", ["npx", "tsc", "--noEmit", "-p", "tsconfig.gate.json"], {"__cwd": "frontend"}),
    ],
    "sweep": ["--only", "admin"],
}

# The R4 merge gate (PLAN_R4): every session's module tests and runners in one run, on v5/r4.
MODULES["r4"] = {
    "pytest": sorted({*MODULES["ews"]["pytest"], *MODULES["dealdesk"]["pytest"], *MODULES["dealdesk-ui"]["pytest"]},
                     key=[*MODULES["ews"]["pytest"], *MODULES["dealdesk"]["pytest"], *MODULES["dealdesk-ui"]["pytest"]].index),
    "runners": [*MODULES["ews"]["runners"], MODULES["dealdesk"]["runners"][0], MODULES["dealdesk-ui"]["runners"][1]],
}

# PLAN_R5 Session D (v5/r5-dealdesk): the Deal Desk engine with the full lever set and the golden workbook, the thread layer
# (trace, recent analyses, Word report with the proposal in full and the method appendix), product knowledge (G6), the frontend,
# and the UAT sweep part `dealdesk` (G4 thread, G5 raw-number scan on every Deal Desk screen).
MODULES["r5-dealdesk"] = {
    "pytest": [*MODULES["dealdesk"]["pytest"], *MODULES["dealdesk-ui"]["pytest"], "tests/v5/ai_work"],
    "runners": [*MODULES["dealdesk"]["runners"], *MODULES["dealdesk-ui"]["runners"]],
    "sweep": ["--only", "dealdesk"],
}


# PLAN_R5 P5: the R5 merge gate on v5/r5. Every session's module tests and runners in one run; the sweep is the whole
# sweep (every part, R4's and R5's).
_R5_SETS = [MODULES[k] for k in ("ews", "dealdesk", "dealdesk-ui", "threads", "lenses", "admin", "r5-dealdesk")
            if k in MODULES]
MODULES["r5"] = {
    "pytest": list(dict.fromkeys(p for m in _R5_SETS for p in m["pytest"])),
    "runners": list({r[0]: r for m in _R5_SETS for r in m["runners"]}.values()),
}


def run(cmd: list[str], env: dict | None = None, cwd: Path = V5, timeout: int = 7200) -> tuple[int, str]:
    e = {**os.environ, "TMPDIR": str(VAR), **(env or {})}
    p = subprocess.run(cmd, cwd=cwd, env=e, capture_output=True, text=True, timeout=timeout)
    return p.returncode, (p.stdout + p.stderr)[-3000:]


def pytest_chunked(paths: list[str], name: str) -> tuple[int, set[str], str]:
    """One pytest process per path, results added up (PLAN_R5 Session E): the whole module list in one
    process needs about 3.5 GB and was killed by the 8 GB cloud container's memory limit."""
    total, failed, tails = 0, set(), []
    for i, path in enumerate(paths):
        t, f, tail = pytest([path], f"{name}-{i:02d}")
        if t == 0:
            failed.add(f"{path}::<no test result: the run did not complete>")
        total += t
        failed |= f
        tails.append(tail[-300:])
    return total, failed, "\n".join(tails)[-3000:]


def pytest(paths: list[str], name: str) -> tuple[int, set[str], str]:
    # GATE_PYTEST_CHUNKS=1 (the cloud container, 8 GB shared with the running stack): one pytest process per path,
    # so one process never holds every module's data at once; the counts and failures are summed.
    if os.environ.get("GATE_PYTEST_CHUNKS") == "1" and len(paths) == 1 and (V5 / paths[0]).is_dir():
        files = sorted(str(f.relative_to(V5)) for f in (V5 / paths[0]).glob("test_*.py"))
        if len(files) > 40:  # a large suite (tests/cockpit_v4): groups of 12 files, one process each
            paths = [" ".join(files[i:i + 12]) for i in range(0, len(files), 12)]
    if os.environ.get("GATE_PYTEST_CHUNKS") == "1" and len(paths) > 1:
        total, failed, tails = 0, set(), []
        for i, p in enumerate(paths):
            t, f, tail = pytest([p], f"{name}-{i:02d}")
            if t == 0 and " " in p:  # a group that did not finish (memory): its files one by one
                for j, one in enumerate(p.split(" ")):
                    t1, f1, tail = pytest([one], f"{name}-{i:02d}-{j:02d}")
                    t, f = t + t1, f | f1 | ({f"{one}::<no result: pytest did not finish>"} if t1 == 0 else set())
            total, failed = total + t, failed | f
            if t == 0:
                failed.add(f"{p}::<no result: pytest did not finish>")
            tails.append(tail[-300:])
        return total, failed, "\n".join(tails)[-3000:]
    xml = VAR / f"{name}.xml"
    xml.unlink(missing_ok=True)  # a killed run must not read the last run's results
    code, tail = run([PY, "-m", "pytest", *[x for p in paths for x in p.split(" ")], "-q", "-p", "no:cacheprovider",
                      f"--basetemp={VAR / ('bt-' + name)}", f"--junitxml={xml}"])
    failed = set()
    total = 0
    if xml.exists():
        for case in ET.parse(xml).getroot().iter("testcase"):
            total += 1
            if case.find("failure") is not None or case.find("error") is not None:
                f = case.get("file") or case.get("classname", "").replace(".", "/") + ".py"
                failed.add(f"{f}::{case.get('name')}")
    return total, failed, tail


def main() -> int:
    module = sys.argv[1] if len(sys.argv) > 1 else "ews"
    skip_suite = "--skip-cockpit-suite" in sys.argv
    # --low-memory (the 8 GB cloud container): the tests run with the app stopped, then the app is started for the
    # panels, the browser smoke and the sweep. Same items, same evidence; only the order of the app's lifetime moves.
    low_memory = "--low-memory" in sys.argv
    if low_memory:
        run([str(V5 / "ops/v5.sh"), "stop"], timeout=600)
    VAR.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    items: list[dict] = []

    def item(name, ok, detail="", seconds=0.0):
        items.append({"item": name, "pass": bool(ok), "detail": detail, "seconds": round(seconds, 1)})
        print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""), flush=True)

    t = time.time(); code, tail = run([PY, "ops/frozen_guard.py"])
    item("1. frozen guard", code == 0, tail.strip().splitlines()[-1], time.time() - t)

    sync_files = sorted(str(p.relative_to(V5)) for p in (V5 / "tests/v5").glob("test_sync_*.py"))
    t = time.time(); total, failed, _ = pytest(sync_files, "sync")
    item("2. sync tests", total > 0 and not failed, f"{total - len(failed)}/{total}" + (f" failed: {sorted(failed)}" if failed else ""), time.time() - t)

    spec = MODULES[module]
    t = time.time(); total, failed, _ = pytest_chunked(spec["pytest"], module)
    item(f"3a. {module} tests", total > 0 and not failed, f"{total - len(failed)}/{total}" + (f" failed: {sorted(failed)}" if failed else ""), time.time() - t)
    for name, cmd, env in spec["runners"]:
        env = dict(env)
        cwd = V5 / env.pop("__cwd") if "__cwd" in env else V5
        t = time.time(); code, tail = run(cmd, env, cwd)
        summary = [ln for ln in tail.splitlines() if any(k in ln for k in ("passed", "pass ", "tests ", "fail "))][-3:]
        item(f"3b. {name}", code == 0, " | ".join(s.strip() for s in summary), time.time() - t)

    if skip_suite:
        item("4a. Cockpit suite tests/cockpit_v4", False, "SKIPPED (--skip-cockpit-suite): gate not complete")
    else:
        # In batches of test files (memory: see pytest_chunked); the same tests, the same exception rule.
        files = sorted(str(p.relative_to(V5)) for p in (V5 / "tests/cockpit_v4").glob("test_*.py"))
        batches = [" ".join(files[i:i + 8]) for i in range(0, len(files), 8)]
        t = time.time(); total, failed, _ = pytest_chunked(batches, "cockpit_v4")
        unexpected = sorted(failed - DECLARED_COCKPIT_EXCEPTIONS)
        vanished = sorted(DECLARED_COCKPIT_EXCEPTIONS - failed)
        item("4a. Cockpit suite tests/cockpit_v4", total > 1000 and not unexpected and not vanished,
             f"{total - len(failed)}/{total} pass; {len(failed & DECLARED_COCKPIT_EXCEPTIONS)} declared exceptions"
             + (f"; UNEXPECTED failures: {unexpected}" if unexpected else "")
             + (f"; declared exceptions now passing: {vanished}" if vanished else ""), time.time() - t)
        # The suite writes run evidence into tracked files; put them back.
        run(["git", "checkout", "--", "docs/cockpit_v4/evidence"])

    if low_memory:
        code, tail = run([str(V5 / "ops/v5.sh"), "start"], timeout=1200)
        print(("" if code == 0 else "WARNING: ") + "app started for items 4b-6", flush=True)
    # GATE_BEFORE_LIVE: a command run before the live items (4b-6), for a host too small to keep every service up
    # through the test suites (the cloud container): it starts the one app. Unset on the Mac, where nothing changes.
    if os.environ.get("GATE_BEFORE_LIVE"):
        run(["bash", "-c", os.environ["GATE_BEFORE_LIVE"]], timeout=1800)

    t = time.time()
    # The suite can push the 8 GB container to its limit and the kernel may stop a service: bring back any
    # service that is down before the live checks (ops/v5.sh start starts only what is not running).
    sys.path.insert(0, str(V5 / "ops"))
    from uat_sweep_parts import ensure_services  # noqa: PLC0415
    ensure_services()
    snap = VAR / "gate_snapshots"
    code1, _ = run([PY, "ops/snapshot_cockpit.py", "http://127.0.0.1:8500", str(snap)])
    code2, tail = run([PY, "ops/compare_snapshots.py", "evidence/v5/foundation/after_ews_story", str(snap), "1.0",
                       str(VAR / "gate_snapshot_compare.json")])
    item("4b. Cockpit panels equal the baseline (post-rescale + the registered EWS story, PLAN_R5 E)", code1 == 0 and code2 == 0,
         [ln for ln in tail.splitlines() if "PROBLEMS" in ln][-1:][0] if "PROBLEMS" in tail else tail[-200:], time.time() - t)

    t = time.time(); code, tail = run([BROWSER_PY, "ops/browser_smoke.py"])
    item("5. browser smoke", code == 0, [ln for ln in tail.splitlines() if "checks passed" in ln][-1:][0]
         if "checks passed" in tail else tail[-300:], time.time() - t)

    # 6. The UAT sweep (INBOX Item 3): every UAT step and every control, both books.
    # GATE_SWEEP_PARTS=1: the same sweep, part by part in fresh browser processes (ops/uat_sweep_parts.py),
    # for a machine whose memory one long browser session exhausts.
    sweep_cmd = ([BROWSER_PY, "ops/uat_sweep_parts.py"] if os.environ.get("GATE_SWEEP_PARTS") == "1"
                 and not spec.get("sweep") else [BROWSER_PY, "ops/uat_sweep.py", *spec.get("sweep", [])])
    t = time.time(); code, tail = run(sweep_cmd)
    item("6. UAT sweep", code == 0, [ln for ln in tail.splitlines() if "sweep steps passed" in ln][-1:][0]
         if "sweep steps passed" in tail else tail[-300:], time.time() - t)

    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=V5, capture_output=True, text=True).stdout.strip()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report = {"module": module, "commit": sha, "utc": stamp, "passed": all(i["pass"] for i in items),
              "declared_cockpit_exceptions": sorted(DECLARED_COCKPIT_EXCEPTIONS), "items": items}
    (OUT / f"{module}-{stamp}.json").write_text(json.dumps(report, indent=1))
    print(("GATE PASS" if report["passed"] else "GATE FAIL") + f" · {module} @ {sha} · evidence/v5/gate/{module}-{stamp}.json")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
