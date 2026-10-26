"""Feedback from the Book to origination (PLAN_R12 §1.6, I8 part 4).

* **Rating-linked margin ratchet** (a Deal Desk lever, `margin_ratchet_bps_per_notch`): the margin steps by n bps per
  notch the rating moves; origination RAROC prices the expected migration from the one-year migration matrix
  (`pd_migration`), so a ratchet recovers what PD migration takes from the book (`expected_notches`).
* **Sector hurdle overrides proposed from observed drift**: for each sector, the EAD-weighted RAROC the seasoned book
  loses to PD migration per year since origination; pricing to a hurdle that much higher keeps a new deal above
  hurdle at its first annual review. Proposals go through maker-checker: a maker proposes, a different checker
  approves, and the approval writes the next version of the `returns` table (`hurdle_sector`) with the reason.
* **Actual promise realisation** replaces the flat 90% when `relationship.committed_realisation_basis` = "actual"
  (`promises.committed_realisation`).
"""
from __future__ import annotations

import functools
import json
import threading
from datetime import datetime, timezone
from typing import Any

import numpy as np

from backend.dealdesk import params
from backend.dealdesk.book import drift, promises, sources

_LOCK = threading.Lock()


# ------------------------------------------------------------------ margin ratchet

@functools.lru_cache(maxsize=64)
def _expected(rating: str, years: int, _ver: str) -> tuple[float, ...]:
    mig = params.rows("pd_migration")
    grades = [r["from"] for r in mig]
    if rating not in grades:
        return tuple([0.0] * years)
    cols = grades + ["D"]
    m = np.array([[r["to"].get(c, 0.0) for c in cols] for r in mig] + [[0.0] * len(grades) + [1.0]])
    idx = np.arange(len(cols), dtype=float)
    idx[-1] = len(grades) - 1  # default counts as the last grade (no ratchet beyond it)
    v = np.zeros(len(cols))
    v[grades.index(rating)] = 1.0
    out = []
    start = float(grades.index(rating))
    for _ in range(years):
        out.append(float(v @ idx) - start)  # expected notches moved at the start of each year (0 in year 1)
        v = v @ m
    return tuple(out)


def expected_notches(rating: str, years: int) -> np.ndarray:
    """Expected notches of downgrade (positive) at the start of each year, from the migration matrix."""
    ver = str(params.table("pd_migration").get("version"))
    return np.array(_expected(rating, int(years), ver))


# ------------------------------------------------------------------ sector hurdle overrides

def hurdle_overrides(ref: str | None = None) -> dict[str, Any]:
    f = drift.frame(ref)
    bp = drift.book_params()
    ret = params.rows("returns")
    seasoned = f[~f.defaulted & (f.months_elapsed >= 12)]
    out = []
    for sec, g in seasoned.groupby("sector"):
        w = g.ead_sar_mn
        years = (g.months_elapsed / 12).clip(lower=1)
        per_year = float((w * g.d_pd_migration / years).sum() / w.sum())
        cur = float(ret.get("hurdle_sector", {}).get(sec, ret["hurdle"]["Corporate Banking"]))
        uplift = round(max(0.0, -per_year) * 200) / 200  # nearest 0.5 point
        proposed = len(g) >= int(bp["hurdle_override_min_facilities"]) and -per_year >= float(bp["hurdle_override_min_drift"])
        out.append({"sector": sec, "facilities": int(len(g)), "ead_sar_mn": float(w.sum()), "pd_migration_drift_pa": per_year,
                    "current_hurdle": cur, "proposed_hurdle": round(cur + uplift, 4) if proposed else None, "uplift": uplift if proposed else 0.0,
                    "share_below_hurdle_now": float((w * ~g.above_now).sum() / w.sum()),
                    "text": (f"{sec}: the seasoned book loses {-per_year * 100:.1f} points of RAROC a year to rating migration; "
                             f"a hurdle of {cur + uplift:.1%} (from {cur:.1%}) keeps a new deal above hurdle at its first review"
                             if proposed else f"{sec}: migration drift {-per_year * 100:.1f} points a year, below the threshold for an override")})
    out.sort(key=lambda r: r["pd_migration_drift_pa"])
    return {"sectors": out, "proposals": proposals(), "method": __doc__.split("\n\n")[1].strip()}


#: hurdle-override proposals are Book findings in the shared findings relation (maker-checker state in `status`)
FINDINGS = "dd_review_finding"
_STATUS = {"open": "proposed", "resolved": "approved", "superseded": "rejected"}


def proposals() -> list[dict[str, Any]]:
    """The maker-checker log of sector hurdle overrides (dd_review_finding rows I-HO-…)."""
    try:
        t = sources.dd(FINDINGS)
    except sources.DataPending:
        return []
    if not len(t) or "finding_id" not in t.columns:
        return []
    t = t[t.finding_id.astype(str).str.startswith("I-HO-")].sort_values("finding_id")
    out = []
    for r in t.to_dict("records"):
        meta = {}
        try:
            meta = json.loads(r.get("claim_text") or "{}")
        except ValueError:
            pass
        out.append({"id": r["finding_id"], "sector": meta.get("sector"), "current_hurdle": r.get("claim_value"),
                    "proposed_hurdle": r.get("evidence_value"), "evidence": r.get("finding_text"), "maker": r.get("raised_by"),
                    "reason": meta.get("reason"), "proposed_at": r.get("raised_at"), "status": _STATUS.get(r.get("status"), r.get("status")),
                    "checker": meta.get("checker"), "decided_at": r.get("resolved_at"), "note": meta.get("note"),
                    "returns_version": meta.get("returns_version")})
    return out


def _finding(row: dict[str, Any], status: str) -> dict[str, Any]:
    meta = {k: row.get(k) for k in ("sector", "reason", "checker", "note", "returns_version")}
    return {"finding_id": row["id"], "proposal_id": "BOOK", "review_point": 9, "category": "drift", "severity": "medium",
            "title": f"Sector hurdle override {row['status']}: {row['sector']} {row['current_hurdle']:.1%} -> {row['proposed_hurdle']:.1%}",
            "finding_text": row["evidence"], "claim_text": json.dumps(meta), "claim_value": row["current_hurdle"],
            "evidence_value": row["proposed_hurdle"], "evidence_unit": "fraction", "evidence_domain": "deal_desk",
            "evidence_relation": "dd_raroc_drift", "evidence_key": f"sector={row['sector']}", "status": status,
            "rating_notch": 0, "raised_by": row["maker"], "raised_at": row["proposed_at"], "resolved_at": row.get("decided_at")}


def propose(sector: str, hurdle: float, maker: str, reason: str) -> dict[str, Any]:
    if not reason or not reason.strip():
        raise ValueError("a reason is required")
    if not (0.0 < float(hurdle) < 0.5):
        raise ValueError("the hurdle must be in (0, 50%)")
    sectors = {r["sector"]: r for r in hurdle_overrides()["sectors"]}
    if sector not in sectors:
        raise ValueError(f"{sector} is not a sector of the book")
    with _LOCK:
        rows = proposals()
        if any(r["sector"] == sector and r["status"] == "proposed" for r in rows):
            raise ValueError(f"{sector} already has a proposal waiting for a checker")
        row = {"id": f"I-HO-{len(rows) + 1:03d}", "sector": sector, "current_hurdle": sectors[sector]["current_hurdle"],
               "proposed_hurdle": float(hurdle), "evidence": sectors[sector]["text"], "maker": maker, "reason": reason.strip(),
               "proposed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "status": "proposed"}
        sources.publish(FINDINGS, [_finding(row, "open")])
    return row


def decide(pid: str, checker: str, approve: bool, note: str = "") -> dict[str, Any]:
    with _LOCK:
        row = next((r for r in proposals() if r["id"] == pid), None)
        if row is None:
            raise KeyError(pid)
        if row["status"] != "proposed":
            raise ValueError(f"{pid} is already {row['status']}")
        if checker.strip().lower() == str(row["maker"]).strip().lower():
            raise ValueError("maker-checker: the checker must be a different person from the maker")
        row.update({"status": "approved" if approve else "rejected", "checker": checker, "note": note,
                    "decided_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        if approve:
            r = params.rows("returns")
            new = json.loads(json.dumps(r))
            new.setdefault("hurdle_sector", {})[row["sector"]] = row["proposed_hurdle"]
            tab = params.edit("returns", new, checker, f"Book sector hurdle override {row['id']} ({row['sector']}): {row['reason']}")
            row["returns_version"] = tab["version"]
            from backend.dealdesk.book import core
            core.refresh()
        sources.publish(FINDINGS, [_finding(row, "resolved" if approve else "superseded")])
    return row


def realisation() -> dict[str, Any]:
    rel = params.rows("relationship")
    act = promises.realisation()
    return {"basis": rel.get("committed_realisation_basis", "flat"), "flat": float(rel["committed_realisation"]),
            "actual": act["share"], "promises": act["promises"], "by_kind": act.get("by_kind", {}),
            "in_use": promises.committed_realisation(rel), "min_promises": int(rel.get("actual_min_promises", 5))}
