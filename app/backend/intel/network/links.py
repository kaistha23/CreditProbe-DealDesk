"""Relationship links the IC engines walk (rel-saudi-v1 at a quarter, through Borrower 360's read-only store).

Coverage (stated in every answer): supplier and customer links are observed only through payments routed via the
bank (SUPPLIES edges carry the share of the buyer's purchases and of the supplier's revenue the bank saw); a
counterparty that banks elsewhere is invisible. Guarantees, group links and shared collateral are as booked.
"""
from __future__ import annotations

from typing import Any

from backend.b360.store import rows

CONTRACTOR_SECTOR = "Construction"


def supplies_into(period: str, buyers: list[str]) -> list[dict[str, Any]]:
    """SUPPLIES edges whose buyer is in `buyers` (the buyer pays the supplier: a contractor paid by an employer)."""
    if not buyers:
        return []
    return rows("""SELECT e.edge_id, e.source_borrower_id AS supplier_id, e.target_borrower_id AS buyer_id,
                          e.purchase_share_pct, e.revenue_share_pct, e.annual_value_sar_mn, s.sector AS supplier_sector
                   FROM rel_edge e JOIN corp_borrower s ON s.borrower_id = e.source_borrower_id
                        AND s.reporting_quarter = e.reporting_quarter
                   WHERE e.reporting_quarter = ? AND e.rel_type = 'SUPPLIES' AND list_contains(?, e.target_borrower_id)
                   ORDER BY e.edge_id""", [period, sorted(set(buyers))])


def supplies_from(period: str, suppliers: list[str]) -> list[dict[str, Any]]:
    """SUPPLIES edges whose supplier is in `suppliers` (the buyers that depend on them)."""
    if not suppliers:
        return []
    return rows("""SELECT e.edge_id, e.source_borrower_id AS supplier_id, e.target_borrower_id AS buyer_id,
                          e.purchase_share_pct, e.revenue_share_pct, e.annual_value_sar_mn, b.sector AS buyer_sector
                   FROM rel_edge e JOIN corp_borrower b ON b.borrower_id = e.target_borrower_id
                        AND b.reporting_quarter = e.reporting_quarter
                   WHERE e.reporting_quarter = ? AND e.rel_type = 'SUPPLIES' AND list_contains(?, e.source_borrower_id)
                   ORDER BY e.edge_id""", [period, sorted(set(suppliers))])


def guarantees_by(period: str, guarantor: str) -> list[dict[str, Any]]:
    return rows("""SELECT e.edge_id, e.source_borrower_id AS guarantor_id, e.target_borrower_id AS obligor_id, e.facility_id,
                          e.guarantee_amount_sar_mn, e.relation_detail,
                          f.ead_sar_mn AS facility_ead, f.lgd_pct AS facility_lgd_pct
                   FROM rel_edge e LEFT JOIN corp_facility f ON f.facility_id = e.facility_id
                        AND f.reporting_quarter = e.reporting_quarter
                   WHERE e.reporting_quarter = ? AND e.rel_type = 'GUARANTEES' AND e.source_borrower_id = ?
                   ORDER BY e.edge_id""", [period, guarantor])


def group_members(period: str, borrower: str) -> list[dict[str, Any]]:
    return rows("""SELECT * FROM rel_group WHERE reporting_quarter = ? AND group_id =
                   (SELECT group_id FROM rel_group WHERE reporting_quarter = ? AND borrower_id = ? LIMIT 1)
                   ORDER BY borrower_id""", [period, period, borrower])


def shared_collateral(period: str, borrower: str) -> list[dict[str, Any]]:
    return rows("""SELECT s.collateral_id, s.collateral_type, s.borrower_id, s.facility_id, s.market_value_sar_mn,
                          s.claim_sar_mn, s.allocation_pct
                   FROM rel_shared s WHERE s.reporting_quarter = ? AND s.collateral_id IN
                     (SELECT collateral_id FROM rel_shared WHERE reporting_quarter = ? AND borrower_id = ?)
                   ORDER BY s.collateral_id, s.borrower_id""", [period, period, borrower])


def workforce(month: str, employers: list[str]) -> dict[str, Any]:
    """Retail customers the bank sees salaried by these corporates (rel_employer), with their exposure."""
    if not employers:
        return {"customers": 0, "accounts": 0, "exposure": 0.0, "stage2_exposure": 0.0, "month": month}
    m = rows("SELECT MAX(reporting_month) AS m FROM rel_employer WHERE reporting_month <= ?", [month])[0]["m"]
    if not m:
        return {"customers": 0, "accounts": 0, "exposure": 0.0, "stage2_exposure": 0.0, "month": month}
    w = rows("""WITH c AS (SELECT DISTINCT customer_id FROM rel_employer WHERE reporting_month = ?
                           AND list_contains(?, employer_borrower_id))
                SELECT (SELECT COUNT(*) FROM c) AS customers, COUNT(a.account_id) AS accounts,
                       SUM(a.ead_sar_mn) AS ead, SUM(CASE WHEN a.stage >= 2 THEN a.ead_sar_mn ELSE 0 END) AS ead_s2
                FROM ret_account a WHERE a.reporting_month = ? AND a.customer_id IN (SELECT customer_id FROM c)""",
             [m, sorted(set(employers)), m])[0]
    return {"customers": int(w["customers"] or 0), "accounts": int(w["accounts"] or 0), "exposure": float(w["ead"] or 0.0),
            "stage2_exposure": float(w["ead_s2"] or 0.0), "month": m}


def coverage(period: str) -> dict[str, Any]:
    """How much of the corporate book the relationship domain covers at the quarter (for the data-limits line)."""
    r = rows("""WITH b AS (SELECT DISTINCT borrower_id FROM corp_borrower WHERE reporting_quarter = ?),
                     s AS (SELECT source_borrower_id AS id FROM rel_edge WHERE reporting_quarter = ? AND rel_type = 'SUPPLIES'
                           UNION SELECT target_borrower_id FROM rel_edge WHERE reporting_quarter = ? AND rel_type = 'SUPPLIES'),
                     a AS (SELECT source_borrower_id AS id FROM rel_edge WHERE reporting_quarter = ?
                           UNION SELECT target_borrower_id FROM rel_edge WHERE reporting_quarter = ?)
                SELECT (SELECT COUNT(*) FROM b) AS borrowers,
                       (SELECT COUNT(*) FROM b WHERE borrower_id IN (SELECT id FROM s)) AS with_supply_link,
                       (SELECT COUNT(*) FROM b WHERE borrower_id IN (SELECT id FROM a)) AS with_any_link""",
             [period] * 5)[0]
    n = r["borrowers"] or 0
    return {"borrowers": n, "with_supply_link": r["with_supply_link"], "with_any_link": r["with_any_link"],
            "supply_link_pct": 100 * r["with_supply_link"] / n if n else 0.0,
            "any_link_pct": 100 * r["with_any_link"] / n if n else 0.0}
