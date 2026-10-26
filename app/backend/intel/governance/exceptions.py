"""R13 IE item 19: exception intelligence.

Every approved policy exception and what happened after it (worst stage, max DPD, default, rating drift over the four
quarters after the decision, read from the book), and loss and migration rates by exception type against
non-exception peers. Peers are risk-matched: the expected rate for an exception type is the non-exception rate in
each rating band, weighted by the type's own band mix, so a type that is simply given to weaker borrowers is not
blamed for their rating. Rates carry 95% Wilson intervals and n; observed/expected carries a Poisson interval.
Verdict per type: tighten (O/E interval above 1 and n >= 30), watch (O/E >= 1.25 or n < 30), keep.
"""
from __future__ import annotations

import json
from typing import Any

import pandas as pd

from backend.v5common.ratings import rank as rrank

from . import common as C

TYPE_LABEL = {
    "dscr": "DSCR below 1.25x", "leverage": "Debt/EBITDA above limit", "current_ratio": "Current ratio below 1.10x",
    "rating": "Rated below B- (new money)", "collateral_cover": "Collateral cover below 125%",
    "pricing": "RAROC below 12% hurdle", "late_financials": "Audited financials late",
    "perfection_deferral": "Security perfection deferred",
}
MIN_N = 30
REL = ["gov_decision", "gov_policy_exception", "corp_facility_quarter", "corp_borrower_quarter"]


def band(rating: str) -> str:
    r = rrank(rating)
    if r <= rrank("BBB-"):
        return "Investment grade"
    if r <= rrank("BB-"):
        return "BB"
    if r <= rrank("B-"):
        return "B"
    return "CCC and below"


def _frame() -> pd.DataFrame:
    d = C.decisions_with_outcomes()
    if d.empty or "default_12m" not in d:
        return pd.DataFrame()
    d = d[(d["decision"] != "declined") & d["default_12m"].notna()].copy()
    d["types"] = d["exception_types"].map(lambda s: s if isinstance(s, list) else json.loads(s or "[]"))
    d["band"] = d["rating_at_decision"].map(band)
    return d


def _expected(grp: pd.DataFrame, peers: pd.DataFrame, col: str) -> float:
    """Risk-matched expected count: peers' rate per band x the group's count per band (pooled peer rate if a band has no peers)."""
    pooled = peers[col].mean() if len(peers) else 0.0
    pr = peers.groupby("band")[col].mean()
    return float(sum(cnt * pr.get(b, pooled) for b, cnt in grp["band"].value_counts().items()))


def _verdict(n: int, oe: float, lo: float) -> str:
    if n >= MIN_N and lo > 1.0:
        return "tighten"
    if oe >= 1.25 or n < MIN_N:
        return "watch"
    return "keep"


def by_type(d: pd.DataFrame | None = None) -> list[dict[str, Any]]:
    d = _frame() if d is None else d
    if d.empty:
        return []
    peers = d[d["exception_count"] == 0]
    out = []
    for t, label in TYPE_LABEL.items():
        g_all = d[d["types"].map(lambda xs: t in xs)]
        g_sole = g_all[g_all["exception_count"] == 1]
        # judge a type on decisions where it was the only exception when there are enough of them,
        # so a type that travels with a stronger one is not blamed for it
        sole = len(g_sole) >= MIN_N
        g = g_sole if sole else g_all
        n = len(g)
        if n == 0:
            out.append({"type": t, "label": label, "n": 0, "verdict": "no history",
                        "note": "No approved exception of this type in the history."})
            continue
        k_def, k_mig = int(g["default_12m"].sum()), int(g["migrated_12m"].sum())
        e_def, e_mig = _expected(g, peers, "default_12m"), _expected(g, peers, "migrated_12m")
        oe = k_def / e_def if e_def else 0.0
        lo, hi = C.poisson_ratio_ci(k_def, e_def)
        moe = k_mig / e_mig if e_mig else 0.0
        mlo, mhi = C.poisson_ratio_ci(k_mig, e_mig)
        filt = {"exception_type": t, "decision": "not declined"}
        out.append({
            "type": t, "label": label, "n": n, "n_all": int(len(g_all)), "n_sole": int(len(g_sole)),
            "judged_on": "sole exception" if sole else "all decisions carrying it",
            "default": C.rate(k_def, n), "migration": C.rate(k_mig, n),
            "expected_default_pct": round(100 * e_def / n, 2), "expected_migration_pct": round(100 * e_mig / n, 2),
            "oe_default": round(oe, 2), "oe_default_ci": [round(lo, 2), round(hi, 2)],
            "oe_migration": round(moe, 2), "oe_migration_ci": [round(mlo, 2), round(mhi, 2)],
            "mean_notches": round(float(g["notches_12m"].mean()), 2), "mean_max_dpd": round(float(g["max_dpd"].mean()), 1),
            "basis_mix": {b: int(c) for b, c in g["band"].value_counts().items()},
            "measured_on": "book" if t in ("dscr", "leverage", "current_ratio", "rating") else "seeded",
            "verdict": _verdict(n, oe, lo),
            "figure": C.computed(100 * k_def / n, "%", REL, n, "12-month default rate of decisions carrying this exception", filt),
        })
    return out


def peers_summary(d: pd.DataFrame) -> dict[str, Any]:
    p = d[d["exception_count"] == 0]
    e = d[d["exception_count"] > 0]
    return {"exception": {"n": len(e), "default": C.rate(int(e["default_12m"].sum()), len(e)),
                          "migration": C.rate(int(e["migrated_12m"].sum()), len(e))},
            "no_exception": {"n": len(p), "default": C.rate(int(p["default_12m"].sum()), len(p)),
                             "migration": C.rate(int(p["migrated_12m"].sum()), len(p))}}


def ledger(d: pd.DataFrame, limit: int = 60, exception_type: str | None = None) -> list[dict[str, Any]]:
    """Every approved exception with what happened after (newest first; `limit` rows)."""
    ex = C.exceptions()
    if ex.empty:
        return []
    if exception_type:
        ex = ex[ex["exception_type"] == exception_type]
    m = ex.merge(d[["decision_id", "borrower_name", "rm_name", "branch_name", "rating_at_decision", "worst_stage", "max_dpd",
                    "default_12m", "notches_12m", "outcome_quarter", "stage_at_decision"]], on="decision_id", how="inner")
    m = m.assign(qi=m["decision_quarter"].map(C.q_index)).sort_values(["qi", "exception_id"], ascending=[False, True]).head(limit)
    rows = []
    for r in m.to_dict("records"):
        rows.append({
            "exception_id": r["exception_id"], "decision_id": r["decision_id"], "borrower_id": r["borrower_id"],
            "borrower_name": r["borrower_name"], "quarter": r["decision_quarter"], "type": r["exception_type"],
            "label": TYPE_LABEL.get(r["exception_type"], r["exception_type"]), "clause": r["clause"],
            "measured": C.fig("gov_policy_exception", r, "measured", r.get("unit") or ""),
            "approved_by": r["approved_by_level"], "mitigant": r["mitigant"], "rm": r["rm_name"], "branch": r["branch_name"],
            "after": {"stage_at_decision": int(r["stage_at_decision"]), "worst_stage": int(r["worst_stage"]),
                      "max_dpd": int(r["max_dpd"]), "default": int(r["default_12m"]), "notches": int(r["notches_12m"]),
                      "to_quarter": r["outcome_quarter"],
                      "source": {"relation": "corp_facility_quarter", "filter": {"borrower_id": r["borrower_id"]},
                                 "period": f"{C.q_add(r['decision_quarter'], 1)}..{r['outcome_quarter']}"}},
        })
    return rows


def write(types: list[dict[str, Any]], peers: dict[str, Any]) -> list[str]:
    """Deterministic writer: 3-5 lines naming what matters, with numbers."""
    lines = []
    e, p = peers["exception"], peers["no_exception"]
    if e["n"] and p["n"]:
        lines.append(f"{e['n']:,} approved decisions carried at least one policy exception; their 12-month default rate was "
                     f"{e['default']['pct']:.1f}% (95% CI {e['default']['ci_low_pct']:.1f}–{e['default']['ci_high_pct']:.1f}%) "
                     f"against {p['default']['pct']:.1f}% for {p['n']:,} decisions without one.")
    tighten = [t for t in types if t.get("verdict") == "tighten"]
    tighten.sort(key=lambda t: -t["oe_default"])
    for t in tighten[:2]:
        lines.append(f"Tighten {t['label']} ({t['judged_on']}, n={t['n']}): defaults ran {t['oe_default']:.2f}× the "
                     f"risk-matched peer rate (CI {t['oe_default_ci'][0]:.2f}–{t['oe_default_ci'][1]:.2f}), "
                     f"{t['default']['pct']:.1f}% observed vs {t['expected_default_pct']:.1f}% expected.")
    keep = [t for t in types if t.get("verdict") == "keep" and t["n"] >= MIN_N]
    if keep:
        k = min(keep, key=lambda t: t["oe_default"])
        lines.append(f"{k['label']} exceptions performed in line with or better than peers "
                     f"({k['oe_default']:.2f}× expected, n={k['n']}); the mitigants recorded appear to work.")
    thin = [t["label"] for t in types if 0 < t.get("n", 0) < MIN_N]
    if thin:
        lines.append(f"Too few cases to judge ({', '.join(thin)}; fewer than {MIN_N} each): kept on watch.")
    lines.append("Loss here means default within 12 months; the book has too few resolved defaults to measure realised LGD.")
    return lines[:5]


def analyse(exception_type: str | None = None, limit: int = 60) -> dict[str, Any]:
    d = _frame()
    if d.empty:
        return {"available": False, "lines": ["No decision history in Data Domains (governance domain is empty)."],
                "data_note": C.SEED_NOTE}
    types = by_type(d)
    peers = peers_summary(d)
    return {
        "available": True, "kind": "exception_intelligence", "as_of": C.AS_OF_QUARTER,
        "window": f"{C.OUTCOME_QUARTERS} quarters after each decision",
        "lines": write(types, peers), "peers": peers, "types": types,
        "tighten": [t["type"] for t in types if t.get("verdict") == "tighten"],
        "ledger": ledger(d, limit, exception_type), "ledger_total": int(len(C.exceptions())),
        "method": __doc__.strip().split("\n\n", 1)[1].replace("\n", " "),
        "data_note": C.SEED_NOTE,
    }
