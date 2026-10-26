"""Soak test for the R6 descriptor leak (R6 Session Q): drive the running v5 stack and watch every
service's open-descriptor count.

    ops/v5.sh start                                   (in a shell with `ulimit -n 256`, as on the Mac)
    .venv/bin/python ops/soak_fd.py --minutes 25      (CP_TEST_PASSWORD or USERS_LOCAL.md for the sign-in)

Every service is found by its port. Each cycle calls every parameter-free GET route each service
publishes (its OpenAPI), skipping exports and streams, and asks What-If, Lenses and Admin a question so
their polling workers claim and answer runs. Once a minute it records each service's open descriptors
(/proc/<pid>/fd on Linux, `lsof -p` on the Mac) and whether its health check answers. Writes a JSON
report under var/soak/ and prints a table. Exit 1 when a service died or its count grew.
Nothing outside var/ is written; no secret is printed.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

V5 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V5))

SERVICES = {  # name: (port, health path)
    "cockpit": (8500, "/health"),
    "ews": (8501, "/api/v1/ews/health"),
    "b360": (8502, "/api/v1/b360/health"),
    "whatif": (8503, "/api/v1/whatif/health"),
    "data_builder": (8504, "/api/v1/data/health"),
    "workspace": (8505, "/api/v1/workspace/health"),
    "playbook": (8506, "/api/v1/playbook/health"),
    "scorecard": (8507, "/api/v1/scorecard/health"),
    "dealdesk": (8508, "/api/v1/dealdesk/desk/health"),
    "lenses": (8509, "/api/v1/lenses/health"),
    "admin": (8510, "/api/v1/admin/health"),
    "queries": (8516, "/api/v1/queries/health"),
    "agents": (8517, "/api/v1/agents/health"),  # R11 agents_v5 (PLAN_R11_AGENTS, added by Session M)
}
SKIP = ("export", "download", "docx", "pdf", "xlsx", "csv", "stream", "events", "logout", "reset", "rebuild", "/eval")
QUESTIONS = ["What happens to ECL if PD rises 20%?", "Show stage 2 by region", "Which sectors drive the change?",
             "Explain the largest movers", "What is the as-of date?"]


def pid_on(port: int) -> int | None:
    out = subprocess.run(["lsof", "-nP", f"-tiTCP:{port}", "-sTCP:LISTEN"], capture_output=True, text=True).stdout.split()
    return int(out[0]) if out else None


def fds(pid: int) -> int | None:
    d = Path(f"/proc/{pid}/fd")
    try:
        if d.is_dir():
            return len(os.listdir(d))
        out = subprocess.run(["lsof", "-p", str(pid)], capture_output=True, text=True).stdout.splitlines()
        return max(len(out) - 1, 0)
    except OSError:
        return None


def soft_limit(pid: int) -> str:
    try:
        for line in Path(f"/proc/{pid}/limits").read_text().splitlines():
            if line.startswith("Max open files"):
                return line.split()[3]
    except OSError:
        pass
    return "?"


class Client:
    def __init__(self, cookie: str):
        self.cookie = cookie
        self.calls = 0
        self.errors: dict[str, int] = {}
        self.lock = threading.Lock()

    def call(self, url: str, body: dict | None = None, timeout: float = 30) -> tuple[int, object]:
        req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json", "Cookie": f"cp_session={self.cookie}"},
                                     method="POST" if body is not None else "GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - loopback only
                status, raw = r.status, r.read()
        except urllib.error.HTTPError as e:
            status, raw = e.code, e.read()
        except (urllib.error.URLError, OSError) as e:
            status, raw = 0, str(e).encode()
        with self.lock:
            self.calls += 1
            if status == 0 or status >= 500:
                key = f"{status} {url.split('?')[0]}"
                self.errors[key] = self.errors.get(key, 0) + 1
        try:
            return status, json.loads(raw or b"null")
        except ValueError:
            return status, None


def routes(c: Client, port: int) -> list[str]:
    st, spec = c.call(f"http://127.0.0.1:{port}/openapi.json")
    if st != 200 or not isinstance(spec, dict):
        return []
    out = []
    for path, ops in (spec.get("paths") or {}).items():
        if "get" not in ops or "{" in path or any(s in path.lower() for s in SKIP):
            continue
        if any(p.get("required") for p in ops["get"].get("parameters", []) if p.get("in") == "query"):
            continue
        out.append(path)
    return sorted(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=25)
    ap.add_argument("--sample", type=float, default=60, help="seconds between descriptor samples")
    args = ap.parse_args()

    from ops.core_login import login
    c = Client(login("anne")["cookie"])
    pids = {n: pid_on(p) for n, (p, _) in SERVICES.items()}
    missing = [n for n, p in pids.items() if p is None]
    if missing:
        print("not running:", ", ".join(missing))
    table = {n: routes(c, SERVICES[n][0]) for n, p in pids.items() if p}
    slow: set[str] = set()
    print("routes per service:", {n: len(r) for n, r in table.items()})
    print("open-file limit per service:", {n: soft_limit(p) for n, p in pids.items() if p})

    stop = time.time() + args.minutes * 60
    samples: list[dict] = []
    asked = {"whatif": 0, "lenses": 0, "admin": 0}

    def sample(label: str) -> None:
        row = {"t": datetime.now(timezone.utc).strftime("%H:%M:%S"), "label": label, "calls": c.calls}
        for n, pid in pids.items():
            if not pid:
                continue
            port, health = SERVICES[n]
            alive = Path(f"/proc/{pid}").exists() if Path("/proc").is_dir() else subprocess.run(
                ["kill", "-0", str(pid)], capture_output=True).returncode == 0
            st, _ = c.call(f"http://127.0.0.1:{port}{health}", timeout=15)
            row[n] = {"fds": fds(pid) if alive else None, "alive": alive, "health": st}
        samples.append(row)
        print(row["t"], label, "calls", row["calls"], " ".join(
            f"{n}={v['fds']}{'' if v['health'] == 200 else '!' + str(v['health'])}" for n, v in row.items() if isinstance(v, dict)),
            flush=True)

    def ask() -> None:
        q = random.choice(QUESTIONS)
        st, _ = c.call("http://127.0.0.1:8503/api/v1/whatif/threads", {"domain": "retail", "question": q}, timeout=60)
        asked["whatif"] += 200 <= st < 300
        st, _ = c.call("http://127.0.0.1:8509/api/v1/lenses/convo/threads",
                       {"domain": "lenses", "scope": {"book": "retail"}, "question": q}, timeout=60)
        asked["lenses"] += 200 <= st < 300
        st, _ = c.call("http://127.0.0.1:8510/api/v1/admin/convo/threads",
                       {"domain": "admin", "scope": {}, "question": "Which workflows are active?"}, timeout=60)
        asked["admin"] += 200 <= st < 300

    def driver() -> None:
        while time.time() < stop:
            for n, paths in table.items():
                port = SERVICES[n][0]
                for p in paths:
                    if time.time() >= stop:
                        return
                    if p in slow:
                        continue
                    t0 = time.time()
                    c.call(f"http://127.0.0.1:{port}{p}")
                    if time.time() - t0 > 8:
                        slow.add(p)

    sample("start")
    workers = [threading.Thread(target=driver, daemon=True) for _ in range(2)]
    for w in workers:
        w.start()
    next_sample = time.time() + args.sample
    next_ask = time.time()
    while time.time() < stop:
        if time.time() >= next_ask:
            ask()
            next_ask = time.time() + 20
        if time.time() >= next_sample:
            sample("run")
            next_sample += args.sample
        time.sleep(1)
    for w in workers:
        w.join(timeout=60)
    time.sleep(3)
    sample("end")

    first, last = samples[0], samples[-1]
    verdict = {}
    for n in pids:
        if not pids[n]:
            continue
        counts = [s[n]["fds"] for s in samples if s[n]["fds"] is not None]
        died = not last[n]["alive"] or last[n]["health"] != 200
        half = max(len(counts) // 2, 1)
        # A leak climbs without bound; a pool or the GC levels off. Flat = the second half's peak is within 10
        # of the first half's (the Cockpit's per-thread connections rise while its thread pool fills, then level).
        growth = (max(counts[half:]) - max(counts[:half])) if len(counts) > 1 else None
        verdict[n] = {"start": first[n]["fds"], "end": last[n]["fds"], "max": max(counts) if counts else None,
                      "second_half_growth": growth, "died": died}
    ok = all(not v["died"] and (v["second_half_growth"] is not None and v["second_half_growth"] <= 10)
             for v in verdict.values())
    report = {"minutes": args.minutes, "calls": c.calls, "asked": asked, "server_errors": c.errors,
              "slow_routes_skipped": sorted(slow), "routes": {n: len(r) for n, r in table.items()},
              "verdict": verdict, "pass": ok, "samples": samples}
    out = V5 / "var" / "soak" / f"soak-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1))
    print(json.dumps({k: v for k, v in report.items() if k != "samples"}, indent=1))
    print("SOAK", "PASS" if ok else "FAIL", out.relative_to(V5))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
