"""Shared by the three IC engines: book readers, risk appetite, lineage, and the computed-view publisher.

Reads only registered releases: the corporate book and Early Warning (through Borrower 360's read-only DuckDB),
the relationship domain rel-saudi-v1, and the Deal Desk relations (dd_project, dd_facility_limit,
bureau_entity_report, b360_entity, b360_edge) through Session E's reader. Nothing here writes a release; the
results are published as computed views (`publish_view`) with their lineage, under var/intel/network.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
from functools import lru_cache
from typing import Any

from backend.b360 import paths as b360paths
from backend.b360.store import book_periods, clean, rows
from backend.ews_domain import ews_rules as ews

V5 = b360paths.V5
MONEY = "SAR million"

#: Data Domains labels for the relations the IC engines read (N5: every number names its source).
SOURCES: dict[str, dict[str, str]] = {
    "corp_borrower": {"domain": "Corporate book", "release": b360paths.CORP_BOOK, "relation": "corp_borrower_quarter"},
    "corp_facility": {"domain": "Corporate book", "release": b360paths.CORP_BOOK, "relation": "corp_facility_quarter"},
    "ews_corp": {"domain": "Early Warning", "release": b360paths.EWS_CORP, "relation": "ews_corp_exposure"},
    "rel_edge": {"domain": "Relationships", "release": b360paths.RELATIONSHIPS, "relation": "rel_edge_quarter"},
    "rel_group": {"domain": "Relationships", "release": b360paths.RELATIONSHIPS, "relation": "rel_group_quarter"},
    "rel_shared": {"domain": "Relationships", "release": b360paths.RELATIONSHIPS, "relation": "rel_shared_collateral"},
    "rel_employer": {"domain": "Relationships", "release": b360paths.RELATIONSHIPS, "relation": "rel_employer_month"},
    "ret_account": {"domain": "Retail book", "release": b360paths.RET_BOOK, "relation": "retail_account_month"},
    "dd_project": {"domain": "Deal Desk products", "release": "dd-saudi-v1", "relation": "dd_project"},
    "dd_facility_limit": {"domain": "Deal Desk", "release": "dd-saudi-v1", "relation": "dd_facility_limit"},
    "dd_deal": {"domain": "Deal Desk", "release": "dd-saudi-v1", "relation": "dd_deal"},
    "bureau_entity_report": {"domain": "Bureau", "release": "bureau-r12-v1", "relation": "bureau_entity_report"},
    "b360_entity": {"domain": "Borrower 360", "release": "b360-saudi-v1", "relation": "b360_entity"},
    "whatif_corporate": {"domain": "What-If", "release": "var/whatif_v5/corporate", "relation": "whatif_corporate_<period>"},
    "risk_appetite": {"domain": "Deal Desk parameters", "release": "params/v1", "relation": "risk_appetite"},
    "branch_corporate_quarter": {"domain": "Branches and RMs", "release": "branch-saudi-v1", "relation": "branch_corporate_quarter"},
}
BRANCH_FILE = V5 / "data" / "branches" / "branch-saudi-v1" / "branch_corporate_quarter.parquet"


def relationship_managers(period: str, ids: list[str]) -> dict[str, dict[str, Any]]:
    """RM, branch and business unit per borrower (Data Domains: Branches and RMs). Empty when the release is absent."""
    if not ids or not BRANCH_FILE.is_file():
        return {}
    import duckdb
    con = duckdb.connect(":memory:")
    try:
        cur = con.execute(f"""SELECT borrower_id, rm_id, rm_name, branch_name, business_unit
                              FROM read_parquet('{BRANCH_FILE.as_posix()}')
                              WHERE reporting_quarter = ? AND list_contains(?, borrower_id)""", [period, sorted(set(ids))])
        names = [d[0] for d in cur.description]
        return {r[0]: dict(zip(names, r)) for r in cur.fetchall()}
    finally:
        con.close()


def src(name: str, period: str | None = None, columns: list[str] | tuple[str, ...] = (), **key: Any) -> dict[str, Any]:
    s = dict(SOURCES[name])
    if period:
        s["period"] = period
    if columns:
        s["columns"] = list(columns)
    if key:
        s["key"] = {k: v for k, v in key.items() if v is not None}
    return s


def derived(method: str, *inputs: dict[str, Any]) -> dict[str, Any]:
    return {"derived": method, "inputs": list(inputs)}


def latest_quarter() -> str:
    return book_periods("corporate")[-1]


def resolve_quarter(period: str | None) -> str:
    qs = book_periods("corporate")
    if not period:
        return qs[-1]
    if period not in qs:
        raise ValueError(f"{period} is not a corporate book quarter ({qs[0]}–{qs[-1]}).")
    return period


def month_of_quarter(period: str) -> str:
    y, q = int(period[:4]), int(period[-1])
    return f"{y}-{3 * q:02d}"


def borrowers(period: str, ids: list[str] | None = None) -> dict[str, dict[str, Any]]:
    """Book attributes per borrower: name, sector, rating, EAD, ECL, worst stage, EAD-weighted PD and LGD, EWS band."""
    where = "" if ids is None else "AND list_contains(?, b.borrower_id)"
    args: list[Any] = [period] + ([] if ids is None else [sorted(set(ids))])
    fargs: list[Any] = [period] + ([] if ids is None else [sorted(set(ids))])
    fwhere = "" if ids is None else "AND list_contains(?, borrower_id)"
    got = rows(f"""
        WITH f AS (SELECT borrower_id, COUNT(*) AS facilities, SUM(ead_sar_mn) AS ead, SUM(ecl_sar_mn) AS ecl,
                          MAX(stage) AS worst_stage, MAX(dpd_days) AS worst_dpd,
                          SUM(ead_sar_mn * pd_pit_12m) / NULLIF(SUM(ead_sar_mn), 0) AS pd12,
                          SUM(ead_sar_mn * lgd_pct) / NULLIF(SUM(ead_sar_mn), 0) AS lgd_pct,
                          SUM(CASE WHEN stage = 2 THEN ead_sar_mn ELSE 0 END) AS ead_s2
                   FROM corp_facility WHERE reporting_quarter = ? {fwhere} GROUP BY 1),
             e AS (SELECT borrower_id, MAX(ews_score) AS score FROM ews_corp WHERE reporting_quarter = ? GROUP BY 1)
        SELECT b.borrower_id, b.borrower_name, b.sector, b.sub_sector, b.region, b.rating_current, b.watchlist_flag,
               b.group_id, b.group_name, b.relationship_tier, f.facilities, f.ead, f.ecl, f.worst_stage, f.worst_dpd,
               f.pd12, f.lgd_pct, f.ead_s2, e.score
        FROM corp_borrower b LEFT JOIN f USING (borrower_id) LEFT JOIN e USING (borrower_id)
        WHERE b.reporting_quarter = ? {where}""", fargs + [period] + args)
    out: dict[str, dict[str, Any]] = {}
    for r in got:
        r["ead"] = float(r["ead"] or 0.0)
        r["ecl"] = float(r["ecl"] or 0.0)
        r["ews_band"] = ews.band_of("corporate", r.get("score"))
        out[r["borrower_id"]] = r
    return out


def find_borrower(period: str, text: str, sectors: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
    """Book borrowers whose id equals, or whose name contains, `text` (case-insensitive); largest first."""
    t = (text or "").strip()
    if not t:
        return []
    sec = "" if not sectors else "AND list_contains(?, b.sector)"
    args: list[Any] = [period, t.upper(), f"%{t.lower()}%"] + ([list(sectors)] if sectors else [])
    return rows(f"""SELECT b.borrower_id, b.borrower_name, b.sector,
                           (SELECT SUM(ead_sar_mn) FROM corp_facility f WHERE f.reporting_quarter = b.reporting_quarter
                              AND f.borrower_id = b.borrower_id) AS ead
                    FROM corp_borrower b WHERE b.reporting_quarter = ?
                      AND (upper(b.borrower_id) = ? OR lower(b.borrower_name) LIKE ?) {sec}
                    ORDER BY ead DESC NULLS LAST, b.borrower_id LIMIT 12""", args)


@lru_cache(maxsize=1)
def appetite() -> dict[str, dict[str, Any]]:
    """Risk appetite rows the IC engines test against (Deal Desk parameters, params/v1/risk_appetite.json)."""
    p = V5 / "data" / "dealdesk" / "params" / "v1" / "risk_appetite.json"
    doc = json.loads(p.read_text())
    keep = ("single_name", "group_connected", "sector_policy", "re_construction_share", "top20_obligor_share")
    out = {r["name"]: r for r in doc["rows"] if r["name"] in keep}
    try:
        from backend.dealdesk.products import policy
        emp = float(policy.v("project.employer_concentration_max", "contracting"))
    except Exception:  # noqa: BLE001 - the guide value is the documented default
        emp = 0.60
    out["employer_backlog"] = {"name": "employer_backlog", "label": "Top-2 employers' share of a contractor's backlog",
                               "limit": emp, "unit": "share", "kind": "guide",
                               "basis": "Deal Desk products policy project.employer_concentration_max (contracting)"}
    return out


def status_against(value: float, row: dict[str, Any]) -> str:
    """within / appetite / trigger / limit for a 'max' metric with appetite < trigger < limit."""
    if row.get("limit") is not None and value > float(row["limit"]):
        return "over limit"
    if row.get("trigger") is not None and value > float(row["trigger"]):
        return "over trigger"
    if row.get("appetite") is not None and value > float(row["appetite"]):
        return "over appetite"
    return "within appetite"


# ------------------------------------------------------------------ computed views (N5 lineage)

def var_root() -> pathlib.Path:
    return pathlib.Path(os.environ.get("INTEL_NETWORK_VAR") or (V5 / "var" / "intel" / "network")).resolve()


def content_hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(clean(obj), sort_keys=True, default=str).encode()).hexdigest()


def publish_view(view: str, key: str, body: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    """Write the result as a computed view with lineage (no contract relation exists for it). Never raises.

    The file holds the inputs, the lineage and the result; its name is the view and a hash of the inputs, so the
    same question always lands in the same file and the content hash proves the result is reproducible.
    """
    ref = {"view": f"intel_network_{view}", "key": key, "inputs_sha256": content_hash(inputs)[:16]}
    try:
        body_hash = content_hash(body)
        d = var_root() / view
        d.mkdir(parents=True, exist_ok=True)
        f = d / f"{ref['inputs_sha256']}.json"
        f.write_text(json.dumps(clean({"view": ref["view"], "key": key, "inputs": inputs, "content_sha256": body_hash,
                                       "lineage": body.get("lineage"), "result": body}), indent=1, default=str))
        ref.update({"path": f.relative_to(V5).as_posix() if f.is_relative_to(V5) else f.as_posix(),
                    "content_sha256": body_hash, "published": True})
    except Exception as exc:  # noqa: BLE001 - publishing is best effort; the answer still stands
        ref.update({"published": False, "reason": type(exc).__name__})
    return ref
