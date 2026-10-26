"""Seed the R12 demo deals' derived Data Domains relations (orchestrator, 19 Oct 2026).

Review findings (B), group facts / governance findings / SWOT (C) and the stress ladder results (D) are published at
runtime when a user opens those steps. The demo papers (F) read them from Data Domains, so a paper written before those
steps were opened says "not available". This runs the three steps once for every R12 demo deal through the same API the
UI calls and leaves the published relations in data/ to be committed. Idempotent: re-running replaces the same rows.

    python3 ops/r12_seed_demo.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from backend.dealdesk.api import app  # noqa: E402
from backend.dealdesk.data import store  # noqa: E402
from backend.dealdesk.group import service as group  # noqa: E402

P = "/api/v1/dealdesk"


def main() -> int:
    c = TestClient(app)
    deals = [r["proposal_id"] for r in store.dd_read("dd_deal")]
    bad = 0
    for pid in deals:
        r = c.post(f"{P}/review2/{pid}", json={"refresh": True})
        g = group.publish(pid)
        s = c.post(f"{P}/proposals/{pid}/stress2", json={"publish": True})
        ok = r.status_code == 200 and s.status_code == 200
        bad += not ok
        tier = (s.json().get("tier") or {}).get("tier") if s.status_code == 200 else s.text[:120]
        print(f"{pid}: review {r.status_code}, group findings {g.get('findings', {}).get('rows')}, "
              f"stress {s.status_code} tier {tier}")
    for rel in ("dd_review_finding", "dd_swot", "dd_stress_result", "dd_monitoring_plan"):
        rows = store.dd_read(rel)
        print(rel, len(rows), sorted({x.get("proposal_id") for x in rows if x.get("proposal_id")}))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
