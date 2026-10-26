"""Read-only adapters for the RETAIL book (customer grain, monthly), mirroring `reads.py` for the corporate book.

Same contract: every function reads through `backend.ews_domain.reader` (which refuses any path outside the EWS
release) and returns plain dicts keyed by customer id (`borrower_id` in the agent's vocabulary) plus `rows_scanned`.
A customer's segment for peers is the product and sub-product of its largest exposure.
"""
from __future__ import annotations

from typing import Any

from backend.ews_domain import ews_rules as ews
from backend.ews_domain import reader as rd

D = "retail"
P, O = "reporting_month", "customer_id"


def _f(v: Any) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if x != x else x


IN = f"list_contains(?, {O})"


def resolve(period: str) -> tuple[str, str]:
    chosen, prior, _ = rd.resolve_period(D, period or "")
    return chosen, prior


def periods() -> list[str]:
    return rd.periods(D)


def warned(period: str, *, sector: str = "", sub_sector: str = "", borrower: str = "") -> dict[str, Any]:
    period, prior = resolve(period)
    rows = rd.q(f"""SELECT {O} AS borrower_id, NULL AS borrower_name,
                           arg_max(product, ead_sar_mn) AS sector, arg_max(sub_product, ead_sar_mn) AS sub_sector,
                           MAX(ews_score) AS score, MAX(stage) AS stage, MAX(dpd_days) AS dpd, SUM(ead_sar_mn) AS ead,
                           SUM(ecl_sar_mn) AS ecl, COUNT(*) AS facilities, BOOL_OR(default_flag = 1) AS defaulted
                    FROM {rd.exposure(D)} WHERE {P} = ? {"AND " + O + " = ?" if borrower else ""} GROUP BY 1""",
                [period, *([borrower] if borrower else [])])
    if sector:
        rows = [r for r in rows if r["sector"] == sector]
    if sub_sector:
        rows = [r for r in rows if r["sub_sector"] == sub_sector]
    floor = ews.floor(D, "moderate")
    for r in rows:
        r["band"] = ews.band_of(D, r["score"])
        r["warned"] = int(r["score"] or 0) >= floor
        r["ead"], r["ecl"] = _f(r["ead"]) or 0.0, _f(r["ecl"]) or 0.0
    return {"period": period, "prior_period": prior, "rows": rows,
            "rows_scanned": sum(int(r["facilities"]) for r in rows), "warned_min": floor}


def rules_and_trend(period: str, owners: list[str], points: int = 6) -> dict[str, Any]:
    period, _ = resolve(period)
    allp = periods()
    window = allp[max(0, allp.index(period) - points + 1): allp.index(period) + 1]
    rows = rd.q(f"""SELECT {O} AS o, {P} AS p, MAX(ews_score) AS score, string_agg(ews_reasons, '; ') AS r, COUNT(*) AS n
                    FROM {rd.exposure(D)} WHERE {IN} AND list_contains(?, {P}) GROUP BY 1, 2""", [owners, window])
    label_to_id = {r["label"]: r["id"] for r in ews.RULES[D]}
    weights = {r["id"]: r["weight"] for r in ews.RULES[D]}
    by: dict[str, dict[str, Any]] = {}
    for r in rows:
        by.setdefault(r["o"], {})[r["p"]] = r
    out = {}
    for o in owners:
        h = by.get(o, {})
        series = [{"period": p, "score": int(h[p]["score"]) if p in h else None} for p in window]
        now = h.get(period) or {}
        labels = sorted({x.strip() for x in (now.get("r") or "").split(";") if x.strip()})
        prev = series[-2]["score"] if len(series) >= 2 else None
        out[o] = {"score": int(now.get("score") or 0), "band": ews.band_of(D, now.get("score")),
                  "rules": [{"rule_id": label_to_id.get(x, x), "label": x, "weight": weights.get(label_to_id.get(x, ""))}
                            for x in labels],
                  "series": series, "change": (int(now.get("score") or 0) - prev) if prev is not None else None}
    return {"period": period, "window": window, "by_owner": out, "rows_scanned": sum(int(r["n"]) for r in rows),
            "ruleset": ews.RULESET_VERSION}


def b360_evidence(period: str, owners: list[str]) -> dict[str, Any]:
    period, prior = resolve(period)
    exp = rd.q(f"""SELECT {O} AS o, SUM(ead_sar_mn) AS ead, SUM(limit_sar_mn) AS limit_, SUM(balance_sar_mn) AS balance,
                          SUM(ecl_sar_mn) AS ecl, MAX(stage) AS stage, MAX(dpd_days) AS dpd, COUNT(*) AS facilities,
                          string_agg(DISTINCT product, ', ') AS products, MAX(cure_flag) AS cured,
                          MAX(collateral_ltv_pct) FILTER (WHERE secured_flag = 1) AS ltv_max,
                          arg_max(product, collateral_ltv_pct) FILTER (WHERE secured_flag = 1) AS ltv_product,
                          MAX(months_on_book) AS months_on_book
                   FROM {rd.exposure(D)} WHERE {P} = ? AND {IN} GROUP BY 1""", [period, owners])
    own = rd.q(f"""SELECT {O} AS o, customer_segment, employment_type, region, tenure_months, accounts_held,
                          behaviour_score, behaviour_score_previous, behaviour_score_change, score_band, score_band_previous,
                          score_migration
                   FROM {rd.owner(D)} WHERE {P} = ? AND {IN}""", [period, owners])
    br = rd.q(f"SELECT {O} AS o, branch_id, branch_name FROM {rd.branch(D)} WHERE {P} = ? AND {IN}", [period, owners])
    out: dict[str, dict[str, Any]] = {o: {"covenants": []} for o in owners}
    for r in exp:
        out[r.pop("o")]["exposure"] = {k: (v if k in ("products", "ltv_product") else _f(v)) for k, v in r.items()}
    for r in own:
        out[r.pop("o")]["owner"] = r
    for r in br:
        o = r.pop("o")
        out[o]["rm"] = {"rm_name": f"{r['branch_name']} branch (retail collections)" if r.get("branch_name") else None,
                        "rm_id": r.get("branch_id"), "branch_name": r.get("branch_name")}
    for o, v in out.items():
        v["group"] = {}
        v["open_conditions"] = {"available": False, "note": "Retail customers carry no Deal Desk conditions."}
        v["links"] = {"borrower_360": f"/borrower-360?domain=retail&customer_id={o}&period={period}",
                      "early_warning": f"/early-warning?domain=retail&customer={o}&period={period}"}
    return {"period": period, "by_owner": out,
            "rows_scanned": sum(int(r.get("facilities") or 0) for r in exp) + len(own) + len(br)}


def conduct(period: str, owners: list[str]) -> dict[str, Any]:
    period, _ = resolve(period)
    rows = rd.q(f"""SELECT {O} AS o, MAX(salary_interruption_flag) AS salary_interrupted, MAX(salaried_flag) AS salaried,
                           MIN(inflow_trend_pct) AS inflow_trend_pct, MIN(balance_buffer_months) AS buffer_months,
                           MAX(returned_payments_3m) AS returned, MAX(gambling_bnpl_spend_share_pct) AS gambling_bnpl,
                           MAX(overlimit_flag) AS overlimit, MIN(payment_ratio_pct) AS payment_ratio,
                           MIN(payment_ratio_change_3m) AS payment_ratio_change, MAX(missed_payments_12m) AS missed,
                           MAX(delinquency_streak_months) AS streak, MAX(utilisation_pct) AS util,
                           MAX(total_inflows_sar_k) AS inflows_k, COUNT(*) AS n
                    FROM {rd.exposure(D)} WHERE {P} = ? AND {IN} GROUP BY 1""", [period, owners])
    out = {o: {} for o in owners}
    for r in rows:
        o = r.pop("o")
        out[o] = {"salary_interrupted": bool(r["salary_interrupted"]), "salaried": bool(r["salaried"]),
                  "inflow_trend_pct": _f(r["inflow_trend_pct"]), "buffer_months": _f(r["buffer_months"]),
                  "returned_payments_q": int(r["returned"] or 0), "gambling_bnpl_share_pct": _f(r["gambling_bnpl"]),
                  "overlimit": bool(r["overlimit"]), "payment_ratio_pct": _f(r["payment_ratio"]),
                  "payment_ratio_change_3m": _f(r["payment_ratio_change"]), "missed_payments_12m": int(r["missed"] or 0),
                  "delinquency_streak_months": int(r["streak"] or 0), "utilisation_pct": _f(r["util"]),
                  "inflows_sar_k": _f(r["inflows_k"])}
    return {"period": period, "by_owner": out, "rows_scanned": sum(int(r["n"]) for r in rows),
            "basis": "Open Banking and behaviour fields of the retail EWS release (salary credit, inflows, buffer, "
                     "returned payments, spend mix, payment ratio, missed payments)."}


def bureau(period: str, owners: list[str]) -> dict[str, Any]:
    period, _ = resolve(period)
    rows = rd.q(f"""SELECT {O} AS o, MIN(bureau_score) AS score, MAX(external_dpd_days) AS dpd,
                           MAX(new_external_default) AS new_default, MAX(enquiries_3m) AS enq,
                           MAX(external_balance_sar_mn) AS bal, MAX(external_leverage_x) AS lev, COUNT(*) AS n
                    FROM {rd.exposure(D)} WHERE {P} = ? AND {IN} GROUP BY 1""", [period, owners])
    out = {o: {"available": False} for o in owners}
    for r in rows:
        out[r["o"]] = {"available": r["score"] is not None or r["dpd"] is not None, "bureau_score": _f(r["score"]),
                       "external_dpd_days": int(r["dpd"] or 0), "external_default": bool(r["new_default"]),
                       "enquiries_q": int(r["enq"] or 0), "external_exposure_sar_mn": _f(r["bal"]),
                       "external_leverage_x": _f(r["lev"])}
    return {"period": period, "by_owner": out, "rows_scanned": sum(int(r["n"]) for r in rows),
            "basis": "Bureau fields of the retail EWS release (keyed to the spine)."}


def sector_peers(period: str, sub_sectors: list[str]) -> dict[str, Any]:
    period, prior = resolve(period)
    floor = ews.floor(D, "moderate")
    rows = rd.q(f"""WITH b AS (SELECT {P} AS p, {O} AS o, arg_max(product, ead_sar_mn) AS sector,
                                      arg_max(sub_product, ead_sar_mn) AS sub, MAX(ews_score) AS s
                               FROM {rd.exposure(D)} WHERE list_contains(?, {P}) GROUP BY 1, 2)
                    SELECT p, sector, sub, COUNT(*) AS names, COUNT(*) FILTER (WHERE s >= ?) AS warned
                    FROM b GROUP BY 1, 2, 3""", [[x for x in (period, prior) if x], floor])
    tot = {p: (sum(r["warned"] for r in rows if r["p"] == p), sum(r["names"] for r in rows if r["p"] == p))
           for p in (period, prior) if p}
    book = {p: (100.0 * w / n if n else 0.0) for p, (w, n) in tot.items()}
    out = {}
    for s in sub_sectors:
        now = next((r for r in rows if r["p"] == period and r["sub"] == s), None)
        before = next((r for r in rows if r["p"] == prior and r["sub"] == s), None)
        if not now:
            continue
        share = 100.0 * now["warned"] / now["names"] if now["names"] else 0.0
        sp = (100.0 * before["warned"] / before["names"]) if before and before["names"] else None
        out[s] = {"sector": now["sector"], "names": int(now["names"]), "warned": int(now["warned"]),
                  "warned_share_pct": share, "warned_share_prior_pct": sp, "book_warned_share_pct": book[period],
                  "median_inflow_trend_pct": None,
                  "sector_stress": bool(share >= 1.5 * book[period] and (sp is None or share > sp))}
    return {"period": period, "by_sub_sector": out, "rows_scanned": sum(int(r["names"]) for r in rows),
            "basis": "Product stress = the sub-product's warned share is at least 1.5× the book's and rising on the month."}


def changes(period: str, owners: list[str]) -> dict[str, Any]:
    period, prior = resolve(period)
    if not prior:
        return {"period": period, "prior_period": "", "by_owner": {o: {"new": True} for o in owners}, "rows_scanned": 0}
    rows = rd.q(f"""SELECT {O} AS o, {P} AS p, MAX(ews_score) AS score, MAX(dpd_days) AS dpd, MAX(stage) AS stage,
                           MAX(cure_flag) AS cured, string_agg(ews_reasons, '; ') AS r, ANY_VALUE(customer_score_band) AS band,
                           COUNT(*) AS n
                    FROM {rd.exposure(D)} WHERE {IN} AND list_contains(?, {P}) GROUP BY 1, 2""", [owners, [period, prior]])
    by: dict[str, dict[str, Any]] = {}
    for r in rows:
        by.setdefault(r["o"], {})[r["p"]] = r
    out = {}
    for o in owners:
        now, before = by.get(o, {}).get(period, {}), by.get(o, {}).get(prior)
        rs = lambda r: {x.strip() for x in ((r or {}).get("r") or "").split(";") if x.strip()}  # noqa: E731
        if not before:
            out[o] = {"new": True, "prior_period": prior}
            continue
        out[o] = {"new": False, "prior_period": prior, "score_prior": int(before["score"] or 0),
                  "score_change": int(now.get("score") or 0) - int(before["score"] or 0),
                  "dpd_prior": int(before["dpd"] or 0), "dpd_now": int(now.get("dpd") or 0),
                  "stage_prior": int(before["stage"] or 0), "stage_now": int(now.get("stage") or 0),
                  "rating_prior": before.get("band"), "rating_now": now.get("band"),
                  "new_reasons": sorted(rs(now) - rs(before)), "cleared_reasons": sorted(rs(before) - rs(now)),
                  "cured_flag": bool(now.get("cured")),
                  "dpd_cured": int(before["dpd"] or 0) > 0 and int(now.get("dpd") or 0) == 0}
    return {"period": period, "prior_period": prior, "by_owner": out, "rows_scanned": sum(int(r["n"]) for r in rows)}


def lifetime_ecl(period: str, owners: list[str]) -> dict[str, float]:
    return {r["o"]: _f(r["life"]) or 0.0 for r in rd.q(
        f"""SELECT {O} AS o, SUM(ecl_lifetime_sar_mn) AS life FROM {rd.exposure(D)}
            WHERE {P} = ? AND {IN} AND stage < 3 AND dpd_days < 90 GROUP BY 1""", [period, owners])}


__all__ = ["b360_evidence", "bureau", "changes", "conduct", "lifetime_ecl", "resolve", "rules_and_trend",
           "sector_peers", "warned"]
