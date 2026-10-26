#!/usr/bin/env python3
"""R14 session p: warm the bank-form proposal's pipeline-fit cache (f's pipeline test takes 15-50 s per deal the first time) for the deals of
the demo, so "Prepare the credit proposal" answers in seconds.

    .venv/bin/python ops/r14_p_warm.py [R12-TWA R12-TWB DD-06 R14-RWQ]
"""
from __future__ import annotations

import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))


def main(pids: list[str]) -> int:
    from backend.dealdesk.house_style.bankform import feed
    for pid in pids or ["R12-TWA", "R12-TWB", "DD-06", "R14-RWQ"]:
        t = time.time()
        F = feed.feed(pid)
        print(f"{pid}: pipeline fit {'ready' if F.pipeline else 'not available'} in {time.time() - t:.1f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
