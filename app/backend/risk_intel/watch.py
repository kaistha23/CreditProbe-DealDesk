"""P4 Accepted Risk Intelligence (PLAN_R9 C2): the Accepted Risk Watch read model over the `watch` domain.

Escalation rule (P4-ESC-02): two or more missed items, or one missed critical item -> Bank Watchlist and a SICR
assessment. Exposure on the list and the ECL if Tier 1 moved to Stage 2. Names added from Early Warning are kept
in the action store and shown beside the seeded list.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from backend.risk_intel import store

V5 = Path(__file__).resolve().parents[2]
DIR = V5 / "data" / "watch" / "watch-v1"
PACK = {"pack": "P4 Accepted Risk Intelligence", "rule_id": "P4-ESC-02",  # + a Stage 3 facility escalates (Art 6.12)
        "article": "CBUAE CRM Art. 7.11 (SICR indicators), Art. 7.10 (rebuttals)", "confidence": "High: rule-based"}


def _clean(v: Any) -> Any:
    if hasattr(v, "item"):
        return v.item()
    return v


def tables() -> tuple[pd.DataFrame, pd.DataFrame]:
    return pd.read_parquet(DIR / "watch_client.parquet"), pd.read_parquet(DIR / "watch_item.parquet")


def escalation(items: list[dict[str, Any]], stage: int = 1) -> dict[str, Any]:
    missed = [i for i in items if i["status"] == "missed"]
    crit = [i for i in missed if i.get("critical")]
    esc = len(missed) >= 2 or bool(crit) or stage >= 3
    why = ""
    if len(missed) >= 2:
        why = f"{len(missed)} missed items"
    elif crit:
        why = f"critical item missed: {crit[0]['trigger']}"
    elif stage >= 3:
        why = "another facility of the obligor is in Stage 3 (cross-default assessment, Art 6.12)"
    return {"escalate": esc, "why": why, "missed": len(missed), "due": sum(1 for i in items if i["status"] == "due"),
            "action": "Move to Bank Watchlist and request a SICR assessment" if esc else ""}


def view(tier: int | None = None) -> dict[str, Any]:
    c, it = tables()
    by = {k: [{kk: _clean(vv) for kk, vv in r.items()} for r in g.sort_values("due_date").to_dict("records")]
          for k, g in it.groupby("watch_id")}
    added = [a for a in store.actions() if a["kind"] == "accepted_risk_watch"]
    rows = []
    for r in c.to_dict("records"):
        r = {k: _clean(v) for k, v in r.items()}
        r["items"] = by.get(r["watch_id"], [])
        r["escalation"] = escalation(r["items"], int(r.get("stage") or 1))
        rows.append(r)
    seen = {r["obligor_id"] for r in rows}
    for a in added:
        if a.get("obligor_id") in seen:
            continue
        seen.add(a.get("obligor_id"))
        rows.append({"watch_id": a["id"], "obligor_id": a.get("obligor_id"), "book": "corporate", "source": "early_warning",
                     "name": a.get("name") or a.get("obligor_id"), "sector": a.get("sector", ""), "tier": int(a.get("tier", 2)),
                     "currency": "SAR", "exposure_sar_mn": float(a.get("exposure") or 0), "ecl_sar_mn": float(a.get("ecl") or 0),
                     "ecl_stage2_sar_mn": float(a.get("ecl") or 0), "stage": a.get("stage", 1), "approved_on": a["at"][:10],
                     "approved_by": a.get("by", ""), "no_sicr_rationale": a.get("rationale") or "Added from Early Warning; rationale to be recorded at the watch committee.",
                     "items": [], "escalation": escalation([])})
    if tier:
        rows = [r for r in rows if int(r["tier"]) == int(tier)]
    rows.sort(key=lambda r: (not r["escalation"]["escalate"], r["tier"], -r["exposure_sar_mn"]))
    tiers = []
    for t in (1, 2, 3):
        g = [r for r in rows if int(r["tier"]) == t]
        tiers.append({"tier": t, "names": len(g), "exposure": sum(r["exposure_sar_mn"] for r in g),
                      "ecl": sum(r["ecl_sar_mn"] for r in g), "ecl_stage2": sum(r["ecl_stage2_sar_mn"] for r in g),
                      "escalate": sum(1 for r in g if r["escalation"]["escalate"])})
    t1 = tiers[0]
    all_items = [i for r in rows for i in r["items"]]
    return {"as_of": "2026-10-13", "names": len(rows), "exposure": sum(r["exposure_sar_mn"] for r in rows),
            "ecl": sum(r["ecl_sar_mn"] for r in rows), "tiers": tiers,
            "tier1_stage2": {"current_ecl": t1["ecl"], "stage2_ecl": t1["ecl_stage2"], "uplift": t1["ecl_stage2"] - t1["ecl"]},
            "items": {"total": len(all_items), "on_track": sum(1 for i in all_items if i["status"] == "on track"),
                      "due": sum(1 for i in all_items if i["status"] == "due"),
                      "missed": sum(1 for i in all_items if i["status"] == "missed")},
            "escalations": sum(1 for r in rows if r["escalation"]["escalate"]), "clients": rows,
            "rule": ("Two or more missed items, or one missed critical item, or a facility of the obligor in Stage 3 → "
                     "Bank Watchlist and SICR assessment."),
            "currency_note": "Amounts in SAR million; the two UAE proposal cases are AED converted at the peg (1 AED = 1.0211 SAR).",
            "powered_by": PACK}
