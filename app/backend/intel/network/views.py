"""R14 G (R13 IC gap 2): the network views registered in Data Domains.

The contagion map and employer exposure compute each answer as a view under var/intel/network (R13 IC). R14 registers the
published views as three relations of the "network_intel" domain (backend/dealdesk/data/schema.py, NETWORK):

  net_contagion_view   one row per published focal borrower: totals of "if it fails, who else is hit"
  net_contagion_link   one row per focal and linked borrower: channel, why, exposure, at risk, notches, ECL change
  net_employer_view    one row per project employer: contractors, attributable and combined exposure against appetite

Published set: the `N_FOCAL` largest corporate borrowers by EAD at the book quarter plus the UAT demo names (`DEMO_FOCAL`), at
the moderate severity; the top `N_EMPLOYER` employers of the ranking. `ops/r14_publish_network_views.py` runs the engines,
writes the committed snapshot (`snapshot.json` in the release folder) and publishes the relations; the R12 build reads the
snapshot (`build_rows`) so `build --check` does not depend on what the engines compute later. Engine answers name the
registered row (`registered`) when their focal borrower or employer is in it, and say whether it was recomputed since.
"""
from __future__ import annotations

import json
import pathlib
from typing import Any

from backend.dealdesk.data import schema as S

V5 = pathlib.Path(__file__).resolve().parents[3]
SNAPSHOT = V5 / "data/intel/network-saudi-v1/snapshot.json"  # build source of the net_* relations (lineage ALLOWED)
N_FOCAL = 10
N_EMPLOYER = 15
DEMO_FOCAL = ("CB00039", "CB00001")
SEVERITY = "moderate"
ACTOR = "R14 G network views"
RELS = ("net_contagion_view", "net_contagion_link", "net_employer_view")


def focal_set(period: str) -> list[str]:
    from backend.intel.network import common
    b = common.borrowers(period)
    top = sorted(b.values(), key=lambda r: (-r["ead"], r["borrower_id"]))[:N_FOCAL]
    ids = [r["borrower_id"] for r in top]
    return ids + [x for x in DEMO_FOCAL if x in b and x not in ids]


def compute() -> dict[str, list[dict[str, Any]]]:
    """Run the engines on the published set; rows of the three relations (engine output, deterministic)."""
    from backend.intel.network import common, contagion, employer
    period = common.latest_quarter()
    views, links = [], []
    for bid in focal_set(period):
        o = contagion.contagion(bid, period, SEVERITY, publish=True)
        t = o["totals"]
        v = o.get("view") or {}
        views.append({"focal_borrower_id": bid, "focal_name": o["focal"]["name"], "book_quarter": o["period"], "severity": SEVERITY,
                      "names_hit": int(t["names"]), "exposure_sar_mn": round(float(t["exposure"]), 6),
                      "at_risk_sar_mn": round(float(t["at_risk"]), 6), "d_ecl_focal_sar_mn": round(float(t["d_ecl_focal"]), 6),
                      "d_ecl_second_sar_mn": round(float(t["d_ecl_second"]), 6), "to_stage2": int(t["to_stage2"]),
                      "to_stage3": int(t["to_stage3"]), "headline": o["text"]["headline"],
                      "inputs_sha256": v.get("inputs_sha256") or "", "content_sha256": v.get("content_sha256") or ""})
        for n in o["names"]:
            links.append({"focal_borrower_id": bid, "borrower_id": n["borrower_id"], "name": n["name"],
                          "channels": json.dumps(n.get("channels") or []), "why": n.get("why") or "",
                          "exposure_sar_mn": round(float(n.get("exposure") or 0), 6), "at_risk_sar_mn": round(float(n.get("at_risk") or 0), 6),
                          "notches": int(n.get("notches") or 0), "d_ecl_sar_mn": round(float(n.get("d_ecl") or 0), 6)})
    emp = []
    for r in employer.ranking(period, limit=N_EMPLOYER)["rows"]:
        emp.append({"employer_id": r["employer_id"], "name": r["name"], "sector": r.get("sector") or "", "contractors": int(r["contractors"]),
                    "contractor_ead_sar_mn": round(float(r["contractor_ead"]), 6), "attributable_sar_mn": round(float(r["attributable"]), 6),
                    "own_ead_sar_mn": round(float(r["own_ead"] or 0), 6), "combined_sar_mn": round(float(r["combined"]), 6),
                    "utilisation_pct": round(float(r["utilisation_pct"] or 0), 4), "status": r.get("status") or ""})
    return {"net_contagion_view": views, "net_contagion_link": links, "net_employer_view": emp}


def write_snapshot(rows: dict[str, list[dict[str, Any]]]) -> pathlib.Path:
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(json.dumps({"actor": ACTOR, "severity": SEVERITY, "relations": rows}, indent=1, sort_keys=True))
    return SNAPSHOT


def build_rows() -> dict[str, list[dict[str, Any]]]:
    """The committed snapshot's rows (what the R12 build publishes); empty relations when no snapshot is committed."""
    if not SNAPSHOT.exists():
        return {r: [] for r in RELS}
    d = json.loads(SNAPSHOT.read_text())["relations"]
    return {r: d.get(r, []) for r in RELS}


def publish(rows: dict[str, list[dict[str, Any]]] | None = None) -> dict[str, Any]:
    from backend.dealdesk.data.store import publish as _pub
    rows = rows if rows is not None else build_rows()
    return {r: _pub(r, rows[r], mode="replace", actor=ACTOR)["rows"] for r in RELS}


def registered(relation: str, **key: Any) -> dict[str, Any] | None:
    """The registered row for a focal borrower / employer, as a Data Domains source (None when not in the published set)."""
    try:
        from backend.dealdesk.data.store import dd_read, trace
        got = dd_read(relation, **key)
    except Exception:  # noqa: BLE001 - relation not yet published: the answer stands without it
        return None
    if not got:
        return None
    row = got[0]
    src = trace(relation, row)
    src["label"] = S.RELATIONS[relation]["label"]
    return {"source": src, "row": row}
