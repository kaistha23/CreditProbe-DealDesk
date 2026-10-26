"""PLAN_R5 P5: trial-merge the six R5 branches in a throwaway worktree and report conflicts per owner.

Usage: .venv/bin/python ops/r5_trial_merge.py [--keep]

Merges origin/v5/r5-{threads, ews-story, dealdesk, lenses, admin, ui} in the plan's order onto origin/v5/r5-base,
in var/trial_merge (a git worktree, so the running stack and the checkout are untouched). A branch that conflicts
is recorded with its conflicting files and the branches already merged that touch them, then aborted, and the
trial carries on with the next. Prints a markdown table for the STATUS file. Nothing is pushed.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

V5 = Path(__file__).resolve().parents[1]
WT = V5 / "var" / "trial_merge"
ORDER = ["threads", "ews-story", "dealdesk", "lenses", "admin", "ui"]
OWNER = {"threads": "T", "ews-story": "E", "dealdesk": "D", "lenses": "L", "admin": "A", "ui": "P"}


def git(*args: str, cwd: Path = V5, check: bool = True) -> str:
    p = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and p.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {p.stderr.strip()[:400]}")
    return p.stdout.strip()


def main() -> int:
    git("fetch", "-q", "origin")
    if WT.exists():
        git("worktree", "remove", "--force", str(WT), check=False)
    git("worktree", "add", "--detach", str(WT), "origin/v5/r5-base")
    git("config", "user.email", "session-p@creditprobe.local", cwd=WT)
    git("config", "user.name", "Session P trial merge", cwd=WT)
    base = git("rev-parse", "--short", "origin/v5/r5-base")
    touched: dict[str, set[str]] = {}
    rows = []
    for b in ORDER:
        ref = f"origin/v5/r5-{b}"
        tip = git("rev-parse", "--short", ref, check=False) or "missing"
        ahead = git("rev-list", "--count", f"origin/v5/r5-base..{ref}", check=False) or "0"
        files = set(git("diff", "--name-only", f"origin/v5/r5-base...{ref}", check=False).splitlines())
        touched[b] = files
        if ahead == "0":
            rows.append((b, tip, ahead, "nothing to merge", ""))
            continue
        p = subprocess.run(["git", "merge", "--no-ff", "--no-edit", "-m", f"trial: merge {ref}", ref], cwd=WT,
                           capture_output=True, text=True)
        if p.returncode == 0:
            rows.append((b, tip, ahead, "clean", ""))
            continue
        conf = git("diff", "--name-only", "--diff-filter=U", cwd=WT, check=False).splitlines()
        git("merge", "--abort", cwd=WT, check=False)
        detail = "; ".join(f"`{f}` (also " + (", ".join(OWNER[o] for o in ORDER[:ORDER.index(b)]
                                                         if f in touched.get(o, set())) or "base") + ")" for f in conf)
        rows.append((b, tip, ahead, f"CONFLICT ({len(conf)} files)", detail))
    print(f"Trial merge onto origin/v5/r5-base @ {base}\n")
    print("| Branch | Owner | Tip | Commits | Result | Conflicting files (other owners touching them) |")
    print("|---|---|---|---|---|---|")
    for b, tip, ahead, res, det in rows:
        print(f"| v5/r5-{b} | {OWNER[b]} | {tip} | {ahead} | {res} | {det} |")
    shared: dict[str, list[str]] = {}
    for b, fs in touched.items():
        for f in fs:
            shared.setdefault(f, []).append(OWNER[b])
    overlap = sorted((f, o) for f, o in shared.items() if len(o) > 1)
    if overlap:
        print("\nFiles changed by more than one branch (merge watch list):\n")
        for f, o in overlap:
            print(f"- `{f}`: {', '.join(o)}")
    if "--keep" not in sys.argv:
        git("worktree", "remove", "--force", str(WT), check=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
