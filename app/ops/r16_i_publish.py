"""R16 i: publish the customer-file relations' demo rows (same actor and stamp as backend.dealdesk.data.build, so
`build --check` compares equal), then regenerate the data contract document.

    .venv/bin/python ops/r16_i_publish.py --seed
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))


def seed() -> None:
    from backend.dealdesk.data import build, contract, store
    from backend.dealdesk.intake import seed as s
    for rel, rs in s.build().items():
        r = store.publish(rel, rs, mode="replace", actor=build.ACTOR, at=build.STAMP)
        print(f"{rel}: {r['rows']} rows, version {r.get('version')}")
    contract.main()


if __name__ == "__main__":
    if "--seed" in sys.argv[1:]:
        seed()
    else:
        print(__doc__)
