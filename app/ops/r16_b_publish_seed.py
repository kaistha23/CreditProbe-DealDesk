"""R16 b: republish the demo row of dd_business_request after a writer change, as the data build writes it (actor and stamp of
the build), so `python -m backend.dealdesk.data.build --check` stays PASS. Regenerates docs/v5/R12_DATA_CONTRACT.md.

    .venv/bin/python ops/r16_b_publish_seed.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.dealdesk.data import build, contract, store  # noqa: E402
from backend.dealdesk.rm_request import seed  # noqa: E402

def _reset() -> None:
    """Drop the relation's manifest entry first, so the demo row is version 1 like every relation the build writes (the build
    check compares content, version column included)."""
    import json
    folder = build.S.RELATIONS["dd_business_request"]["folder"]
    p = store.manifest_path(folder)
    m = json.loads(p.read_text())
    if m.get("relations", {}).pop("dd_business_request", None) is not None:
        p.write_text(json.dumps(m, indent=1, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    _reset()
    print(store.publish("dd_business_request", seed.build_rows(build.STAMP), mode="replace", actor=build.ACTOR, at=build.STAMP))
    contract.main()
