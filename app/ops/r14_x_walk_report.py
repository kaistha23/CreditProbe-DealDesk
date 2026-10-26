"""R14 x: one table over every session walk run on the merged build (docs/v5/r14_review/x/<session>/...).

    .venv/bin/python ops/r14_x_walk_report.py      -> docs/v5/r14_review/x/report.md (+ prints it)

Per report: steps, found, page errors, console errors, development overlay, pages wider than the viewport (document
width > viewport width: the sideways-scroll test), and the steps not found with their error.
"""
from __future__ import annotations

import json
import pathlib

V5 = pathlib.Path(__file__).resolve().parents[1]
X = V5 / "docs" / "v5" / "r14_review" / "x"


def rows_of(rep):
    if isinstance(rep, list):
        return [r for r in rep if isinstance(r, dict)]
    if isinstance(rep, dict):
        for k in ("steps", "results", "runs", "shots"):
            if isinstance(rep.get(k), list):
                return [r for r in rep[k] if isinstance(r, dict)]
        return [v for v in rep.values() if isinstance(v, dict)]
    return []


def found(r):
    for k in ("found", "ok", "passed"):
        if k in r:
            v = r[k]
            return v not in (False, 0, "False", "false", None)
    return r.get("status", "done") in ("done", "ok", None)


def lit(v):
    """Some reports store values as their Python repr (e.g. "[]", "{'portal': False, ...}")."""
    if isinstance(v, str) and v[:1] in "[{(" :
        try:
            return __import__("ast").literal_eval(v)
        except Exception:  # noqa: BLE001
            return v
    return v


def n_list(v):
    v = lit(v)
    return len(v) if isinstance(v, (list, tuple)) else (1 if v not in (None, False, 0, "", "None", "False") and not isinstance(v, (bool, int, float)) else 0)


def overlay(r):
    v = lit(r.get("dev_overlay", r.get("overlay")))
    if isinstance(v, dict):
        return bool(v.get("portal") or v.get("badge") or v.get("issues"))
    return v in (True, "True", "true", 1)


def wide(r):
    p = r.get("probe")
    if isinstance(p, str):
        try:
            p = eval(p, {}, {})  # noqa: S307 - our own report text (a dict repr)
        except Exception:  # noqa: BLE001
            p = None
    if isinstance(p, dict) and p.get("docWidth") and p.get("vw"):
        return p["docWidth"] > p["vw"]
    if "sideways" in r:
        return bool(r["sideways"])
    return False


def main() -> int:
    lines = ["| Report | Steps | Found | Page errors | Console errors | Dev overlay | Wider than viewport | Not found |",
             "|---|---|---|---|---|---|---|---|"]
    tot = [0, 0, 0, 0, 0, 0]
    for p in sorted(X.rglob("*.json")):
        if p.name in ("summary.json", "demo_check.json", "voice.json"):
            continue
        try:
            rep = json.loads(p.read_text())
        except Exception:  # noqa: BLE001
            continue
        rows = rows_of(rep)
        if not rows:
            continue
        st = len(rows)
        fo = sum(1 for r in rows if found(r))
        pe = sum(n_list(r.get("page_errors")) + (n_list(r.get("errors")) if "page_errors" not in r else 0) for r in rows)
        ce = sum(n_list(r.get("console_errors")) for r in rows)
        ov = sum(1 for r in rows if overlay(r))
        wd = sum(1 for r in rows if wide(r))
        miss = [f"{r.get('step') or r.get('run')} {r.get('size', '')}".strip() for r in rows if not found(r)]
        for i, v in enumerate((st, fo, pe, ce, ov, wd)):
            tot[i] += v
        lines.append(f"| `{p.relative_to(V5)}` | {st} | {fo} | {pe} | {ce} | {ov} | {wd} | {', '.join(miss) or '—'} |")
    lines.append(f"| **Total** | **{tot[0]}** | **{tot[1]}** | **{tot[2]}** | **{tot[3]}** | **{tot[4]}** | **{tot[5]}** | |")
    out = "\n".join(lines) + "\n"
    (X / "report.md").write_text("# R14 x walk report\n\n" + out)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
