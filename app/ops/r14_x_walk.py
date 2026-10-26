"""R14 x: the merged branch's click-through walk, built from every R14 session's own walk (all clicks, no typed URLs
after the first page), with the screens written to docs/v5/r14_review/x/<session>/ instead of the session's folder.

    .venv/bin/python ops/r14_x_walk.py u n r e m f p i g t      # sessions in this order (default: all)
    .venv/bin/python ops/r14_x_walk.py --ui http://127.0.0.1:5500 f

Each session script runs unchanged except for its output folder (its `OUT = ...` line is pointed at x/<session>);
the sizes are 1440x900 and 1280x800 (the tour: EN and AR at both). Every script asserts no page error, no console error,
no development overlay and no sideways scroll on its own steps; this driver collects their reports into
docs/v5/r14_review/x/summary.json (per session: exit code, steps, found, page errors, overlay, sideways scroll).
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
import time
import traceback

V5 = pathlib.Path(__file__).resolve().parents[1]
X = V5 / "docs" / "v5" / "r14_review" / "x"
SCRIPTS = {
    "u": "ops/r14_u_walkthrough.py", "n": "ops/r14_n_walkthrough.py", "r": "ops/r14_r_walkthrough.py",
    "e": "ops/r14_e_shots.py", "m": "ops/r14_m_shots.py", "f": "ops/r14_f_walkthrough.py", "p": "ops/r14_p_shots.py",
    "i": "ops/r14_i_shots.py", "g": "ops/r14_g_walkthrough.py", "t": "ops/r14_t_tour_walk.py",
}
REPORTS = ("walkthrough.json", "shots.json", "walk.json")


def run_one(key: str, ui: str) -> int:
    path = V5 / SCRIPTS[key]
    import os
    out = X / key / os.environ.get("R14_X_SUB", "")  # R14_X_SUB: one tour run per invocation (memory), its own folder
    out.mkdir(parents=True, exist_ok=True)
    src = path.read_text()
    src, n = re.subn(r"^OUT = .*$", f"OUT = __import__('pathlib').Path({str(out)!r})", src, count=1, flags=re.M)
    assert n == 1, f"{path}: no OUT line"
    argv = [str(path), "--ui", ui]
    if key == "t":
        import os
        argv += ["--runs", os.environ.get("R14_X_T_RUNS", "en@1440x900,ar@1440x900,en@1280x800,ar@1280x800")]
        if os.environ.get("R14_X_T_NO_VOICE"):
            argv += ["--no-voice-check"]
    else:
        import os
        argv += ["--sizes", os.environ.get("R14_X_SIZES", "1440x900,1280x800")]
        if os.environ.get("R14_X_ONLY"):
            argv += ["--only", os.environ["R14_X_ONLY"]]
    old = sys.argv
    sys.argv = argv
    try:
        exec(compile(src, str(path), "exec"), {"__name__": "__main__", "__file__": str(path)})  # noqa: S102 - our own script
        return 0
    except SystemExit as e:
        return int(e.code or 0) if not isinstance(e.code, str) else 1
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        return 2
    finally:
        sys.argv = old


def summarise(key: str, rc: int, secs: float) -> dict:
    rep = None
    import os
    sub = os.environ.get("R14_X_SUB", "")
    for name in REPORTS:
        p = X / key / sub / name
        if p.exists():
            try:
                rep = json.loads(p.read_text())
            except Exception:  # noqa: BLE001
                rep = None
            break
    rows = rep if isinstance(rep, list) else (rep or {}).get("steps") or (rep or {}).get("results") or []
    if isinstance(rep, dict) and not rows:
        rows = [v for v in rep.values() if isinstance(v, dict)]
    def cnt(pred):
        return sum(1 for r in rows if isinstance(r, dict) and pred(r))
    return {"session": key, "exit_code": rc, "seconds": round(secs), "steps": len(rows),
            "found": cnt(lambda r: r.get("found", r.get("ok", True)) not in (False, 0)),
            "page_errors": sum(len(r.get("page_errors") or r.get("errors") or []) if isinstance(r.get("page_errors") or r.get("errors"), list) else 0 for r in rows if isinstance(r, dict)),
            "report": next((str((X / key / sub / n).relative_to(V5)) for n in REPORTS if (X / key / sub / n).exists()), None)}


def main() -> int:
    args = sys.argv[1:]
    ui = "http://127.0.0.1:5500"
    if "--ui" in args:
        i = args.index("--ui")
        ui = args[i + 1]
        del args[i:i + 2]
    keys = args or list(SCRIPTS)
    X.mkdir(parents=True, exist_ok=True)
    sp = X / "summary.json"
    summary = json.loads(sp.read_text()) if sp.exists() else {}
    worst = 0
    for k in keys:
        t0 = time.time()
        print(f"== R14 x walk: session {k} ({SCRIPTS[k]}) at {time.strftime('%H:%M:%S', time.gmtime())} UTC", flush=True)
        rc = run_one(k, ui)
        import os
        sk = k + (f"/{os.environ['R14_X_SUB']}" if os.environ.get("R14_X_SUB") else "")
        summary[sk] = summarise(k, rc, time.time() - t0)
        print(json.dumps(summary[sk]), flush=True)
        sp.write_text(json.dumps(summary, indent=1) + "\n")
        worst = max(worst, rc)
    return worst


if __name__ == "__main__":
    raise SystemExit(main())
