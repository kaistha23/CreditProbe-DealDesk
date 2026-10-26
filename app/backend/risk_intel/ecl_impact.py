"""P3 Early Warning -> ECL Intelligence: the ECL if the current warnings come true (PLAN_R9 C1).

For every warned name (customer band = its worst exposure's band: Critical, High, Medium, Low):
    ECL if defaulted   = max(current ECL, EAD x LGD)          (Stage 3, LGD-based)
    expected ECL       = p x ECL if defaulted + (1 - p) x current ECL     p = PD of the name's bucket (Admin)
    severe case        = every Critical and High name at 90+ DPD (ECL if defaulted), Medium and Low at expected.
Corporate is computed per borrower; Retail at segment (product) level from the same account rows.
Amounts in SAR million, as the books publish them. Read-only on the Early Warning release.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from backend.ews_domain import reader as rd
from backend.risk_intel import store

BUCKETS = ("critical", "high", "moderate", "low")
PACK = {"pack": "P3 Early Warning → ECL Intelligence", "rule_id": "P3-ECL-01",
        "article": "CBUAE CRM Art. 7.11 (SICR indicators), Art. 9.21 (provisioning)",
        "confidence": "Medium: bucket PDs are a management estimate",
        "trace": "Early Warning release × book ECL fields (EAD, LGD, ECL) at the as-of period"}


def _book_totals(domain: str, period: str) -> dict[str, float]:
    spec = rd.domain_spec(domain)
    r = rd.q(f'SELECT SUM(ead_sar_mn) AS ead, SUM(ecl_sar_mn) AS ecl FROM {rd.exposure(domain)} WHERE "{spec["period"]}" = ?', [period])[0]
    return {"ead": float(r["ead"] or 0), "ecl": float(r["ecl"] or 0)}


def _frame(domain: str, period: str = "") -> tuple[pd.DataFrame, str]:
    spec = rd.domain_spec(domain)
    P, O = spec["period"], spec["owner_key"]
    rel = rd.exposure(domain)
    if not period:
        period = rd.q(f'SELECT MAX("{P}") AS p FROM {rel}')[0]["p"]
    seg = spec["segment"]
    name = f'"{spec["owner_name"]}"' if spec.get("owner_name") else f'"{O}"'
    rows = rd.q(f'''SELECT "{O}" AS owner, {name} AS owner_name, "{seg}" AS segment, ead_sar_mn AS ead,
                           ecl_sar_mn AS ecl, lgd_pct, stage, dpd_days, ews_band, ews_score, ews_reasons
                    FROM {rel} WHERE "{P}" = ?''', [period])
    f = pd.DataFrame(rows)
    if f.empty:
        return f, period
    f["lgd"] = f["lgd_pct"].astype(float) / 100.0
    f["ecl_def"] = (f["ead"] * f["lgd"]).where(lambda s: s > f["ecl"], f["ecl"])
    rank = {b: i for i, b in enumerate(BUCKETS)}
    f["_r"] = f["ews_band"].map(rank).fillna(99)
    worst = f.groupby("owner")["_r"].min()
    f["bucket"] = f["owner"].map(worst).map(lambda r: BUCKETS[int(r)] if r < 99 else "none")
    # The name's bucket is its worst band over all its exposures; already-defaulted exposures (Stage 3 or 90+ DPD)
    # carry lifetime ECL already, so they are not "warnings that may come true" and are left out (their floors are in
    # P6 coverage).
    f = f[(f["stage"] < 3) & (f["dpd_days"] < 90)].copy()
    return f, period


def _agg(g: pd.DataFrame, pds: dict[str, float]) -> dict[str, float]:
    p = g["bucket"].map(pds).fillna(0.0)
    cur = float(g["ecl"].sum())
    exp_ = float((p * g["ecl_def"] + (1 - p) * g["ecl"]).sum())
    sev_mask = g["bucket"].isin(["critical", "high"])
    expected_each = p * g["ecl_def"] + (1 - p) * g["ecl"]
    severe = float(g.loc[sev_mask, "ecl_def"].sum() + expected_each[~sev_mask].sum())
    return {"names": int(g["owner"].nunique()), "exposures": int(len(g)), "ead": float(g["ead"].sum()),
            "current_ecl": cur, "ecl_if_defaulted": float(g["ecl_def"].sum()), "expected_ecl": exp_,
            "uplift": exp_ - cur, "severe_ecl": severe, "severe_uplift": severe - cur}


def impact(domain: str = "corporate", period: str = "", segment: str = "") -> dict[str, Any]:
    domain = "retail" if domain == "retail" else "corporate"
    cfg = store.pd_by_bucket()
    pds = {k: float(cfg["values"][k]) / 100.0 for k in BUCKETS}
    f, period = _frame(domain, period)
    bt = _book_totals(domain, period)
    book_ecl, book_ead = bt["ecl"], bt["ead"]
    if segment:
        f = f[f["segment"] == segment]
    flagged = f[f["bucket"].isin(BUCKETS)]
    total = _agg(flagged, pds) if not flagged.empty else _agg(f.head(0).assign(bucket=[]), pds)
    by_bucket = []
    for b in BUCKETS:
        g = flagged[flagged["bucket"] == b]
        row = {"bucket": b, "label": store.BUCKET_LABELS[b], "pd_pct": cfg["values"][b], **_agg(g, pds)}
        by_bucket.append(row)
    by_segment = []
    for s, g in flagged.groupby("segment"):
        by_segment.append({"segment": str(s), **_agg(g, pds),
                           "by_bucket": {b: float(((pds[b] * g.loc[g.bucket == b, "ecl_def"]) + (1 - pds[b]) * g.loc[g.bucket == b, "ecl"]).sum()
                                                  - g.loc[g.bucket == b, "ecl"].sum()) for b in BUCKETS}})
    by_segment.sort(key=lambda r: -r["uplift"])
    top: list[dict[str, Any]] = []
    if domain == "corporate" and not flagged.empty:
        o = flagged.assign(p=flagged["bucket"].map(pds))
        o = o.assign(exp=o["p"] * o["ecl_def"] + (1 - o["p"]) * o["ecl"])
        g = o.groupby(["owner", "owner_name", "segment", "bucket"], as_index=False).agg(
            ead=("ead", "sum"), current_ecl=("ecl", "sum"), ecl_if_defaulted=("ecl_def", "sum"),
            expected_ecl=("exp", "sum"), stage=("stage", "max"), dpd=("dpd_days", "max"),
            reasons=("ews_reasons", lambda s: "; ".join(sorted({x for v in s for x in str(v).split("; ") if x}))[:240]))
        g["uplift"] = g["expected_ecl"] - g["current_ecl"]
        g = g.sort_values("uplift", ascending=False).head(10)
        top = [{k: (v.item() if hasattr(v, "item") else v) for k, v in r.items()} for r in g.to_dict("records")]
    labels = {"segment": "Sector" if domain == "corporate" else "Product",
              "names": "borrowers" if domain == "corporate" else "customers"}
    return {"domain": domain, "period": period, "segment": segment or None, "currency": "SAR", "unit": "SAR million",
            "pd_by_bucket": cfg, "total": total, "by_bucket": by_bucket, "by_segment": by_segment,
            "top_contributors": top, "book": {"ead": book_ead, "ecl": book_ecl}, "labels": labels,
            "method": ("Expected ECL = Σ [p × ECL if defaulted (Stage 3, EAD × LGD) + (1 − p) × current ECL] over the "
                       "performing exposures of flagged names (Stage 3 and 90+ DPD exposures already carry lifetime ECL and are "
                       "left out), p = the 12-month default probability of the name's warning bucket "
                       "(management estimate, editable in Admin → Settings). Severe case: every Critical and High "
                       "name at 90+ days past due (Stage 3), Medium and Low at their expected ECL."),
            "powered_by": PACK}


def owners_in_scope(domain: str, buckets: list[str], period: str = "", segment: str = "") -> list[str]:
    f, _ = _frame(domain, period)
    if segment:
        f = f[f["segment"] == segment]
    return sorted(f.loc[f["bucket"].isin(buckets or ["critical", "high"]), "owner"].unique().tolist())
