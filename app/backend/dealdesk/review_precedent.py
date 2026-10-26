"""R11 R5: precedent. Similar deals in the corporate book and how they performed.

Similar = same sector, internal rating within N notches, exposure within a size band of the deal, plus the
features in data/dealdesk/review/precedent.json that the book can test (leverage, DSCR, watchlist). A feature the
book does not hold (backlog cover, related-party share) is listed as not used, never guessed.

Outcome: of the borrowers that were Stage 1 and under 30 days past due at the anchor quarter, how many reached
Stage 2 or worse, and how many went 30+ days past due, within the next 4 and 8 quarters: "n of N", against the
book's rate for all Stage 1 borrowers at the same anchor. When fewer than the minimum match, the size band and then
the rating band are widened, and the result says which match was used.
"""
from __future__ import annotations

import functools
import json
from typing import Any

from backend.dealdesk import paths
from backend.dealdesk.review_ledger import REVIEW_DIR
from backend.dealdesk.seed import GRADES


@functools.lru_cache(maxsize=1)
def config() -> dict[str, Any]:
    return json.loads((REVIEW_DIR / "precedent.json").read_text())


@functools.lru_cache(maxsize=1)
def _panel():
    import pandas as pd
    fac = pd.read_parquet(paths.book_relation("corp_facility_quarter"),
                          columns=["borrower_id", "reporting_quarter", "ead_sar_mn", "stage", "dpd_days"])
    g = fac.groupby(["borrower_id", "reporting_quarter"]).agg(ead=("ead_sar_mn", "sum"), stage=("stage", "max"), dpd=("dpd_days", "max")).reset_index()
    bor = pd.read_parquet(paths.book_relation("corp_borrower_quarter"),
                          columns=["borrower_id", "borrower_name", "reporting_quarter", "sector", "rating_current", "leverage_x", "dscr_x", "watchlist_flag"])
    df = g.merge(bor, on=["borrower_id", "reporting_quarter"], how="left")
    quarters = sorted(df.reporting_quarter.unique())
    return df, quarters


def _outcomes(df, quarters, anchor_i: int, horizon: int):
    a = df[df.reporting_quarter == quarters[anchor_i]]
    a = a[(a.stage == 1) & (a.dpd < 30)]
    win = df[df.reporting_quarter.isin(quarters[anchor_i + 1: anchor_i + 1 + horizon])]
    w = win.groupby("borrower_id").agg(stage_max=("stage", "max"), dpd_max=("dpd", "max")).reset_index()
    a = a.merge(w, on="borrower_id", how="left")
    a["s2"] = a.stage_max.fillna(1) >= 2
    a["d30"] = a.dpd_max.fillna(0) >= 30
    return a


def precedent(subject: dict[str, Any], features: dict[str, Any] | None = None) -> dict[str, Any]:
    """subject: sector, rating, amount_sar (deal size), and optional feature values (leverage, dscr, watchlist, unfunded_share)."""
    cfg = config()
    df, quarters = _panel()
    sector = cfg["sector_map"].get(subject["sector"], subject["sector"])
    feats = features or {}
    try:
        gi = GRADES.index(subject["rating"])
    except ValueError:
        gi = None
    used_feats, not_used = [], []
    for ft in cfg["features"]:
        v = feats.get(ft["subject_key"])
        if ft.get("book_column") is None:
            if v:
                not_used.append({"feature": ft["label"], "reason": ft["reason"]})
            continue
        if v is None:
            continue
        on = (v > ft["threshold"]) if ft["op"] == ">" else (v < ft["threshold"]) if ft["op"] == "<" else bool(v)
        if on:
            used_feats.append(ft)
    out: dict[str, Any] = {"sector": sector, "rating": subject["rating"], "horizons": [], "features_used": [f["label"] for f in used_feats],
                           "features_not_in_book": not_used}
    steps = cfg["relax"]
    for h in cfg["horizons"]:
        ai = len(quarters) - 1 - h
        if ai < 0:
            continue
        base = _outcomes(df, quarters, ai, h)
        chosen = None
        for st in steps:
            m = base[base.sector == sector]
            if gi is not None:
                lo, hi = max(0, gi - st["notches"]), min(len(GRADES) - 1, gi + st["notches"])
                m = m[m.rating_current.isin(GRADES[lo:hi + 1])]
            if st.get("size_band"):
                s = float(subject.get("amount_sar") or 0)
                if s > 0:
                    lo_s, hi_s = s / st["size_band"], s * st["size_band"]
                    m = m[(m.ead >= lo_s) & (m.ead <= hi_s)]
            if st.get("features", True):
                for ft in used_feats:
                    col = ft["book_column"]
                    m = m[(m[col] > ft["threshold"])] if ft["op"] == ">" else m[(m[col] < ft["threshold"])] if ft["op"] == "<" else m[m[col] == 1]
            if len(m) >= cfg["min_n"]:
                chosen = (st, m)
                break
        if chosen is None:
            st, m = steps[-1], base[base.sector == sector]
        else:
            st, m = chosen
        N = int(len(m))
        n2, n30 = int(m.s2.sum()), int(m.d30.sum())
        bN = int(len(base))
        out["horizons"].append({
            "quarters": h, "anchor": quarters[ai], "window": f"{quarters[ai + 1]}–{quarters[min(ai + h, len(quarters) - 1)]}",
            "match": st["label"], "N": N, "stage2": n2, "dpd30": n30,
            "stage2_rate": n2 / N if N else None, "dpd30_rate": n30 / N if N else None,
            "book_N": bN, "book_stage2_rate": float(base.s2.mean()) if bN else None, "book_dpd30_rate": float(base.d30.mean()) if bN else None,
            "examples": [{"borrower_id": r.borrower_id, "name": r.borrower_name, "rating": r.rating_current, "ead": round(float(r.ead), 2),
                          "stage2": bool(r.s2), "dpd30": bool(r.d30)}
                         for r in m.sort_values("ead", ascending=False).head(8).itertuples()]})
    h4 = next((x for x in out["horizons"] if x["quarters"] == 4), None)
    if h4 and h4["N"]:
        out["line"] = (f"{h4['stage2']} of {h4['N']} similar {sector.lower()} borrowers ({h4['match']}) reached Stage 2 within 4 quarters "
                       f"({h4['stage2_rate']:.0%}, book {h4['book_stage2_rate']:.0%}); {h4['dpd30']} of {h4['N']} went 30+ days past due.")
    else:
        out["line"] = "No similar borrowers in the book."
    out["basis"] = ("Corporate book (corp_facility_quarter, corp_borrower_quarter): borrowers Stage 1 and under 30 DPD at the anchor quarter, "
                    "outcomes over the following quarters; matching rules in data/dealdesk/review/precedent.json.")
    return out
