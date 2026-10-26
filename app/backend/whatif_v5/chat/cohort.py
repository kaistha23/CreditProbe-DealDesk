"""An Early Warning cohort, summarised for the What-If thread it opens (6.6).

The cohort is the one Early Warning froze (its exposure ids and membership hash
are checked by `cohorts.open_cohort`). The summary reads the What-If domain for
the exposures' IFRS 9 figures and the Early Warning release (read-only) for the
warning band and reasons of each exposure at the cohort's period.
"""
from __future__ import annotations

import collections
from typing import Any

import duckdb
import pandas as pd

from backend.v5common import ratings
from backend.whatif_v5 import cohorts, paths
from backend.whatif_v5.domain import store

EWS_DIR = paths.V5 / "data" / "ews"
EWS_FILES = {"corporate": ("ews-saudi-corporate-20q-v4e2", "ews_corp_exposure.parquet", "facility_id", "reporting_quarter"),
             "retail": ("ews-saudi-retail-20m-v5e1", "ews_retail_exposure.parquet", "account_id", "reporting_month")}
BAND_ORDER = ["critical", "high", "moderate", "low", "none"]


def _ews(domain: str, period: str, ids: list[str]) -> pd.DataFrame:
    rel, name, key, pcol = EWS_FILES[domain]
    path = EWS_DIR / rel / name
    if not path.exists() or not ids:
        return pd.DataFrame(columns=["exposure_id", "ews_band", "ews_reasons"])
    con = duckdb.connect()
    try:
        return con.execute(f"""SELECT "{key}" AS exposure_id, ews_band, ews_reasons FROM '{path}'
                               WHERE "{pcol}" = ? AND "{key}" IN (SELECT unnest(?::VARCHAR[]))""", [period, ids]).df()
    finally:
        con.close()


def _reasons(v: Any) -> list[str]:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return []
    if isinstance(v, (list, tuple)):
        return [str(x) for x in v]
    s = str(v)
    for sep in ("|", ";", ","):
        if sep in s:
            return [x.strip() for x in s.split(sep) if x.strip()]
    return [s.strip()] if s.strip() else []


def summary(cohort_id: str) -> dict[str, Any]:
    frozen = cohorts.open_cohort(cohort_id)
    domain, period = frozen["domain_id"], frozen["period"]
    ids = list(frozen["exposure_ids"])
    f = store.frame(domain, period)
    f = f[f["exposure_id"].isin(set(ids))]
    e = _ews(domain, period, ids)
    f = f.merge(e, on="exposure_id", how="left")
    stage = {str(s): {"n": int((f["stage"] == s).sum()), "ead": float(f.loc[f["stage"] == s, "ead"].sum()),
                      "ecl": float(f.loc[f["stage"] == s, "ecl_final"].sum())} for s in (1, 2, 3)}
    if domain == "corporate":
        mix = f.groupby("grade")["ead"].agg(["size", "sum"])
        grades = [{"grade": g, "n": int(mix.loc[g, "size"]), "ead": float(mix.loc[g, "sum"])}
                  for g in ratings.ordered(mix.index)]
    else:
        mix = f.groupby("grade")["ead"].agg(["size", "sum"])
        grades = [{"grade": g, "n": int(mix.loc[g, "size"]), "ead": float(mix.loc[g, "sum"])}
                  for g in sorted(mix.index)]
    segs = f.groupby("segment").agg(n=("exposure_id", "size"), ead=("ead", "sum"), ecl=("ecl_final", "sum"))
    segs = segs.sort_values("ead", ascending=False)
    reasons: collections.Counter = collections.Counter()
    for v in f.get("ews_reasons", pd.Series(dtype=object)):
        reasons.update(_reasons(v))
    bands = f["ews_band"].fillna("none").astype(str).str.lower() if "ews_band" in f else pd.Series(dtype=str)
    band_rows = [{"band": b, "n": int((bands == b).sum()), "ead": float(f.loc[bands == b, "ead"].sum())}
                 for b in BAND_ORDER if (bands == b).any()]
    return {
        "cohort_id": cohort_id, "title": frozen.get("title", ""), "domain": domain, "period": period,
        "ruleset": frozen.get("ruleset", ""), "owners": int(f["owner_id"].nunique()), "exposures": int(len(f)),
        "exposures_frozen": len(ids), "ead": float(f["ead"].sum()), "ecl": float(f["ecl_final"].sum()),
        "coverage_pct": float(f["ecl_final"].sum() / f["ead"].sum() * 100) if f["ead"].sum() else 0.0,
        "stage_mix": stage, "grade_mix": grades,
        "segments": [{"segment": str(i), "n": int(r.n), "ead": float(r.ead), "ecl": float(r.ecl)} for i, r in segs.head(8).iterrows()],
        "top_reasons": [{"reason": r, "n": int(n)} for r, n in reasons.most_common(6)],
        "bands": band_rows, "membership_hash": frozen.get("membership_hash", ""),
    }
