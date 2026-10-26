"""The financial-quality grade A-D from the flagged signals (PLAN_R13 §Q).

Points per flagged signal: critical 4, high 3, medium 2, low 1 (info 0). Then:

  D   two or more critical signals, or a critical signal with 8+ points, or 14+ points
  C   one critical signal, or 7+ points
  B   3+ points
  A   otherwise

Coverage is the share of signals that could be assessed from Data Domains. Below 40% the grade is marked "limited": it
says what the data on file shows, not that the statements are clean.
"""
from __future__ import annotations

from typing import Any

POINTS = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}
MEANING = {"A": "no material quality concern in the data on file",
           "B": "isolated concerns to monitor",
           "C": "material concerns: adjust the figures before relying on them",
           "D": "the reported figures cannot be relied on without independent verification"}
LIMITED = 0.40


def grade(signals: list[dict[str, Any]]) -> dict[str, Any]:
    flagged = [s for s in signals if s.get("flag") is True]
    assessable = [s for s in signals if s.get("flag") is not None]
    pts = sum(POINTS.get(s["severity"], 0) for s in flagged)
    crit = sum(1 for s in flagged if s["severity"] == "critical")
    if crit >= 2 or (crit and pts >= 8) or pts >= 14:
        g = "D"
    elif crit or pts >= 7:
        g = "C"
    elif pts >= 3:
        g = "B"
    else:
        g = "A"
    cov = len(assessable) / len(signals) if signals else 0.0
    by_sev = {k: sum(1 for s in flagged if s["severity"] == k) for k in ("critical", "high", "medium", "low")}
    return {"grade": g, "meaning": MEANING[g], "points": pts, "flagged": len(flagged), "assessable": len(assessable), "signals": len(signals),
            "coverage": round(cov, 4), "limited": cov < LIMITED, "by_severity": by_sev,
            "rule": "points: critical 4, high 3, medium 2, low 1; D: 2+ critical, or critical with 8+ points, or 14+ points; C: 1 critical or 7+ points; B: 3+ points; A otherwise"}
