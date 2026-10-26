"""The current portfolio for marginal limits: the live corporate book at its latest quarter, read-only.

Marginal metric = this snapshot + the deal. The snapshot keeps EAD (SAR million) by obligor,
connected group (the relationship domain's ownership groups, rel-saudi-v1), sector, sub-sector, rating bucket and collateral type, and the borrower records used to
pre-fill existing-borrower proposals.
"""
from __future__ import annotations

import functools
import hashlib
from typing import Any

import pandas as pd

from backend.dealdesk import paths
from backend.dealdesk.seed import bucket

COLLATERAL_KEY = {"Cash Deposit": "cash", "Real Estate": "real_estate", "Plant and Equipment": "plant_equipment",
                  "Receivables": "receivables", "Corporate Guarantee": "corporate_guarantee"}


REL_GROUPS = paths.V5 / "data" / "relationships" / "rel-saudi-v1" / "rel_group_quarter.parquet"
#: A legacy book group this large is the generator's sector-sized artefact (docs/v5/EWS_UAT.md), not a
#: connected group: its members are grouped by the relationship domain instead, or stand alone.
LEGACY_GROUP_MAX_BORROWERS = 20


def _read(name: str, cols: list[str] | None = None) -> pd.DataFrame:
    d = pd.read_parquet(paths.book_relation(name), columns=cols)
    return d[d["reporting_quarter"] == paths.AS_OF].reset_index(drop=True)


@functools.lru_cache(maxsize=1)
def frames() -> dict[str, pd.DataFrame]:
    f = _read("corp_facility_quarter")
    b = _read("corp_borrower_quarter")
    c = _read("corp_collateral_quarter")
    rel = pd.read_parquet(REL_GROUPS)
    rel = rel[rel["reporting_quarter"] == paths.AS_OF]
    b = b.copy()
    size = b.groupby("group_id")["borrower_id"].transform("nunique")
    rg = rel.set_index("borrower_id")[["group_id", "group_name"]]
    cg = b["borrower_id"].map(rg["group_id"])
    cn = b["borrower_id"].map(rg["group_name"])
    small = size <= LEGACY_GROUP_MAX_BORROWERS
    b["connected_group_id"] = cg.where(cg.notna(), b["group_id"].where(small, b["borrower_id"]))
    b["connected_group_name"] = cn.where(cn.notna(), b["group_name"].where(small, b["borrower_name"]))
    return {"facility": f, "borrower": b, "collateral": c}


@functools.lru_cache(maxsize=1)
def snapshot() -> dict[str, Any]:
    fr = frames()
    f, b, c = fr["facility"], fr["borrower"], fr["collateral"]
    m = f.merge(b[["borrower_id", "connected_group_id", "connected_group_name", "rating_current"]], on="borrower_id", how="left")
    m = m.rename(columns={"connected_group_id": "group_id", "connected_group_name": "group_name"})
    m = m.merge(c[["facility_id", "collateral_type"]], on="facility_id", how="left")
    m["bucket"] = m["rating_current"].map(bucket)
    m["collateral_key"] = m["collateral_type"].map(COLLATERAL_KEY).fillna("none")
    perf = m["stage"] < 3
    el = float((m.loc[perf, "pd_pit_12m"] * m.loc[perf, "lgd_pct"] / 100.0 * m.loc[perf, "ead_sar_mn"]).sum())
    groups = m.groupby("group_id").agg(ead=("ead_sar_mn", "sum"), name=("group_name", "first"),
                                        borrowers=("borrower_id", "nunique"))
    digest = hashlib.sha256(pd.util.hash_pandas_object(m[["facility_id", "ead_sar_mn"]], index=False).values.tobytes()).hexdigest()
    return {
        "as_of": paths.AS_OF, "release": paths.CORP_RELEASE,
        "total_ead": float(m["ead_sar_mn"].sum()),
        "facilities": int(len(m)), "borrowers": int(m["borrower_id"].nunique()),
        "el_12m_performing": el,
        "by_obligor": m.groupby("borrower_id")["ead_sar_mn"].sum().to_dict(),
        "by_group": {k: float(v) for k, v in groups["ead"].items()},
        "group_names": groups["name"].to_dict(),
        "group_borrowers": {k: int(v) for k, v in groups["borrowers"].items()},
        "by_sector": m.groupby("sector")["ead_sar_mn"].sum().to_dict(),
        "by_sub_sector": m.groupby("sub_sector")["ead_sar_mn"].sum().to_dict(),
        "by_bucket": m.groupby("bucket")["ead_sar_mn"].sum().to_dict(),
        "by_collateral": m.groupby("collateral_key")["ead_sar_mn"].sum().to_dict(),
        "digest": digest[:16],
    }


def borrower(borrower_id: str) -> dict[str, Any] | None:
    """An existing borrower's record at the as-of quarter, with its facilities and collateral."""
    fr = frames()
    b = fr["borrower"]
    row = b[b["borrower_id"] == borrower_id]
    if row.empty:
        return None
    r = row.iloc[0].to_dict()
    f = fr["facility"][fr["facility"]["borrower_id"] == borrower_id]
    c = fr["collateral"][fr["collateral"]["borrower_id"] == borrower_id]
    return {"record": r, "facilities": f.to_dict("records"), "collateral": c.to_dict("records"),
            "ead": float(f["ead_sar_mn"].sum())}


def borrower_history(borrower_id: str) -> pd.DataFrame:
    """Every quarter of a borrower's record (for the 3-year financial history)."""
    d = pd.read_parquet(paths.book_relation("corp_borrower_quarter"))
    return d[d["borrower_id"] == borrower_id].sort_values("reporting_quarter").reset_index(drop=True)


def obligor_ead(obligor_id: str) -> float:
    return float(snapshot()["by_obligor"].get(obligor_id, 0.0))


def group_ead(group_id: str | None) -> float:
    return float(snapshot()["by_group"].get(group_id, 0.0)) if group_id else 0.0


def summary() -> dict[str, Any]:
    s = snapshot()
    tot = s["total_ead"]
    top = sorted(s["by_group"].items(), key=lambda kv: -kv[1])[:20]

    def rows(d: dict[str, float]) -> list[dict[str, Any]]:
        return [{"key": k, "ead": round(float(v), 4), "share": float(v) / tot} for k, v in sorted(d.items(), key=lambda kv: -kv[1])]

    return {"as_of": s["as_of"], "release": s["release"], "total_ead": round(tot, 4), "facilities": s["facilities"],
            "borrowers": s["borrowers"], "el_12m_performing": round(s["el_12m_performing"], 4),
            "by_sector": rows(s["by_sector"]), "by_rating_bucket": rows(s["by_bucket"]),
            "by_collateral_type": rows(s["by_collateral"]),
            "top_groups": [{"key": k, "name": s["group_names"].get(k, ""), "ead": round(v, 4), "share": v / tot,
                            "borrowers": s["group_borrowers"].get(k, 0)} for k, v in top]}
