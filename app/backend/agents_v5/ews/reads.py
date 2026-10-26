"""Thin read-only adapters over the Early Warning release, Borrower 360, the branch/RM domain and the EWS ECL-impact
frame, for the triage agent (PLAN_R11_AGENTS A1: engines compute, the agent plans).

Every function reads; none writes. All reads go through `backend.ews_domain.reader` (which refuses any path outside
the EWS release) or the module's own public functions. Each returns plain dicts keyed by borrower, plus the number of
rows it scanned so the run's rows budget (A5) can be enforced.
"""
from __future__ import annotations

from typing import Any

from backend.ews_domain import ews_rules as ews
from backend.ews_domain import reader as rd

from backend.agents_v5.ews import reads_retail as R

DOMAIN = "corporate"
SUPPORTED = ("corporate", "retail")


class NotOnThisBuild(Exception):
    """A read the books on this build cannot answer (reported by the tool, skipped by the plan)."""


def check_domain(domain: str) -> str:
    if domain not in SUPPORTED:
        raise NotOnThisBuild(f"The triage agent covers the corporate and retail books; {domain!r} is not one of them.")
    return domain


def periods(domain: str = DOMAIN) -> list[str]:
    return rd.periods(check_domain(domain))


def resolve(domain: str, period: str) -> tuple[str, str]:
    chosen, prior, _ = rd.resolve_period(check_domain(domain), period or "")
    return chosen, prior


def _f(v: Any) -> float | None:
    if v is None:
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if x != x else x


def _in(owners: list[str]) -> str:
    return "list_contains(?, borrower_id)"


def warned_min(domain: str = DOMAIN) -> int:
    return ews.floor(domain, "moderate")


# ---------------------------------------------------------------- the warned population

def warned(domain: str, period: str, *, sector: str = "", sub_sector: str = "", borrower: str = "") -> dict[str, Any]:
    """Borrowers in scope at `period` with their worst score, band, stage and exposure (one row per borrower)."""
    if domain == "retail":
        return R.warned(period, sector=sector, sub_sector=sub_sector, borrower=borrower)
    period, prior = resolve(domain, period)
    where, params = ['reporting_quarter = ?'], [period]
    if sector:
        where.append("sector = ?")
        params.append(sector)
    if sub_sector:
        where.append("sub_sector = ?")
        params.append(sub_sector)
    if borrower:
        where.append("(borrower_id = ? OR borrower_name ILIKE ?)")
        params.extend([borrower, borrower])
    rows = rd.q(f"""SELECT borrower_id, ANY_VALUE(borrower_name) AS borrower_name, ANY_VALUE(sector) AS sector,
                           ANY_VALUE(sub_sector) AS sub_sector, MAX(ews_score) AS score, MAX(stage) AS stage,
                           MAX(dpd_days) AS dpd, SUM(ead_sar_mn) AS ead, SUM(ecl_sar_mn) AS ecl, COUNT(*) AS facilities,
                           BOOL_OR(default_flag = 1) AS defaulted
                    FROM {rd.exposure(domain)} WHERE {' AND '.join(where)} GROUP BY 1""", params)
    floor = warned_min(domain)
    for r in rows:
        r["band"] = ews.band_of(domain, r["score"])
        r["warned"] = int(r["score"] or 0) >= floor
        r["ead"], r["ecl"] = _f(r["ead"]) or 0.0, _f(r["ecl"]) or 0.0
    return {"period": period, "prior_period": prior, "rows": rows, "rows_scanned": sum(int(r["facilities"]) for r in rows),
            "warned_min": floor}


# ---------------------------------------------------------------- rules fired and the score trend

def rules_and_trend(domain: str, period: str, owners: list[str], points: int = 6) -> dict[str, Any]:
    if domain == "retail":
        return R.rules_and_trend(period, owners, points)
    period, _ = resolve(domain, period)
    all_p = periods(domain)
    window = all_p[max(0, all_p.index(period) - points + 1): all_p.index(period) + 1]
    rows = rd.q(f"""SELECT borrower_id, reporting_quarter AS period, MAX(ews_score) AS score,
                           string_agg(ews_reasons, '; ') AS reasons_raw, COUNT(*) AS n
                    FROM {rd.exposure(domain)}
                    WHERE {_in(owners)} AND list_contains(?, reporting_quarter) GROUP BY 1, 2""", [owners, window])
    label_to_id = {r["label"]: r["id"] for r in ews.RULES[domain]}
    weights = {r["id"]: r["weight"] for r in ews.RULES[domain]}
    by: dict[str, dict[str, dict[str, Any]]] = {}
    for r in rows:
        by.setdefault(r["borrower_id"], {})[r["period"]] = r
    out: dict[str, Any] = {}
    for o in owners:
        hist = by.get(o, {})
        series = [{"period": p, "score": int(hist[p]["score"]) if p in hist else None} for p in window]
        now = hist.get(period) or {}
        labels = sorted({x.strip() for x in (now.get("reasons_raw") or "").split(";") if x.strip()})
        fired = [{"rule_id": label_to_id.get(lbl, lbl), "label": lbl, "weight": weights.get(label_to_id.get(lbl, ""))}
                 for lbl in labels]
        scores = [s["score"] for s in series if s["score"] is not None]
        prev = series[-2]["score"] if len(series) >= 2 else None
        out[o] = {"score": int(now.get("score") or 0), "band": ews.band_of(domain, now.get("score")),
                  "rules": fired, "series": series,
                  "change": (int(now.get("score") or 0) - prev) if prev is not None else None,
                  "rising_periods": _rising(scores),
                  "peak": max(scores) if scores else None}
    return {"period": period, "window": window, "by_owner": out,
            "rows_scanned": sum(int(r["n"]) for r in rows), "ruleset": ews.RULESET_VERSION}


def _rising(scores: list[int]) -> int:
    n = 0
    for a, b in zip(scores[::-1][1:], scores[::-1]):
        if b > a:
            n += 1
        else:
            break
    return n


# ---------------------------------------------------------------- Borrower 360 evidence

def b360_evidence(domain: str, period: str, owners: list[str]) -> dict[str, Any]:
    """Exposure, group, rating, financials, collateral and covenants per borrower at `period` (the B360 facts, read
    from the same EWS release the Early Warning screen shows)."""
    if domain == "retail":
        return R.b360_evidence(period, owners)
    period, prior = resolve(domain, period)
    exp = rd.q(f"""SELECT borrower_id, SUM(ead_sar_mn) AS ead, SUM(limit_sar_mn) AS limit_, SUM(drawn_sar_mn) AS drawn,
                          SUM(ecl_sar_mn) AS ecl, MAX(stage) AS stage, MAX(dpd_days) AS dpd, COUNT(*) AS facilities,
                          SUM(covenant_breaches) AS covenant_breaches, MAX(collateral_ltv_pct) AS ltv_max,
                          SUM(collateral_value_sar_mn) AS collateral, MIN(rating_notches_moved) AS notches,
                          MAX(watchlist_flag) AS watchlist, MAX(sicr_flag) AS sicr, MAX(cure_flag) AS cured,
                          MAX(past_due_flag) AS past_due, MAX(quarters_in_stage) AS quarters_in_stage,
                          ANY_VALUE(region) AS region, ANY_VALUE(relationship_tier) AS tier
                   FROM {rd.exposure(domain)} WHERE reporting_quarter = ? AND {_in(owners)} GROUP BY 1""",
               [period, owners])
    own = rd.q(f"""SELECT borrower_id, borrower_name, group_id, group_name, sector, sub_sector, rating_current,
                          rating_previous, rating_notches_moved, rating_outlook, revenue_sar_mn, ebitda_sar_mn,
                          dscr_x, leverage_x, interest_cover_x, current_ratio_x, ebitda_margin_pct, restructured_flag,
                          watchlist_flag, watchlist_reason, quarters_on_watchlist, qualitative_score
                   FROM {rd.owner(domain)} WHERE reporting_quarter = ? AND {_in(owners)}""", [period, owners])
    cov = rd.q(f"""SELECT borrower_id, covenant_type, threshold_value, observed_value, headroom_pct, breach_flag,
                          waiver_flag, waiver_status, consecutive_breaches
                   FROM {rd.support(domain, 'covenant')} WHERE reporting_quarter = ? AND {_in(owners)}
                   ORDER BY borrower_id, covenant_type""", [period, owners])
    col = rd.q(f"""SELECT borrower_id, COUNT(*) AS items, SUM(market_value_sar_mn) AS market_value,
                          SUM(allocated_value_sar_mn) AS allocated, MAX(ltv_pct) AS ltv_max,
                          MAX(valuation_age_quarters) AS valuation_age, string_agg(DISTINCT collateral_type, ', ') AS types
                   FROM {rd.support(domain, 'collateral')} WHERE reporting_quarter = ? AND {_in(owners)} GROUP BY 1""",
               [period, owners])
    prior_mv = {r["borrower_id"]: _f(r["mv"]) for r in rd.q(
        f"""SELECT borrower_id, SUM(market_value_sar_mn) AS mv FROM {rd.support(domain, 'collateral')}
            WHERE reporting_quarter = ? AND {_in(owners)} GROUP BY 1""", [prior, owners])} if prior else {}
    for r in col:
        before = prior_mv.get(r["borrower_id"])
        r["market_value_prior"] = before
        r["value_change_pct"] = (100.0 * (_f(r["market_value"]) / before - 1)) if before and r["market_value"] else None
    rm = rd.q(f"""SELECT borrower_id, branch_name, business_unit, rm_id, rm_name FROM {rd.branch(domain)}
                  WHERE reporting_quarter = ? AND {_in(owners)}""", [period, owners])
    out: dict[str, dict[str, Any]] = {o: {"covenants": []} for o in owners}
    for r in exp:
        out[r.pop("borrower_id")].update({"exposure": {k: (_f(v) if k not in ("region", "tier") else v) for k, v in r.items()}})
    for r in own:
        out[r.pop("borrower_id")].update({"owner": r})
    for r in cov:
        out[r.pop("borrower_id")]["covenants"].append(r)
    for r in col:
        out[r.pop("borrower_id")].update({"collateral": r})
    for r in rm:
        out[r.pop("borrower_id")].update({"rm": r})
    # The group: the worst stage of the OTHER members of each borrower's group at this period.
    groups = sorted({(v.get("owner") or {}).get("group_id") for v in out.values()} - {None})
    peers = rd.q(f"""SELECT o.group_id, e.borrower_id, MAX(e.stage) AS stage, MAX(e.ews_score) AS score
                     FROM {rd.exposure(domain)} e JOIN (SELECT borrower_id, group_id FROM {rd.owner(domain)}
                                                     WHERE reporting_quarter = ?) o USING (borrower_id)
                     WHERE e.reporting_quarter = ? AND list_contains(?, o.group_id) GROUP BY 1, 2""",
                 [period, period, groups]) if groups else []
    by_group: dict[str, list[dict[str, Any]]] = {}
    for p in peers:
        by_group.setdefault(p["group_id"], []).append(p)
    for o, v in out.items():
        gid = (v.get("owner") or {}).get("group_id")
        others = [p for p in by_group.get(gid, []) if p["borrower_id"] != o]
        worst = max(others, key=lambda p: (p["stage"], p["score"]), default=None)
        v["group"] = {"group_id": gid, "group_name": (v.get("owner") or {}).get("group_name"),
                      "members": len(others) + 1,
                      "worst_other_stage": int(worst["stage"]) if worst else None,
                      "worst_other": worst["borrower_id"] if worst else None}
        v["open_conditions"] = {"available": False,
                                "note": "Deal Desk conditions tracking (R11 Session R) is not on this build."}
        v["links"] = {"borrower_360": f"/borrower-360?domain={domain}&customer_id={o}&period={period}",
                      "early_warning": f"/early-warning?domain={domain}&customer={o}&period={period}"}
    scanned = (sum(int(r.get("facilities") or 0) for r in exp) + len(own) + len(cov) + 2 * len(col) + len(rm)
               + len(peers))
    return {"period": period, "by_owner": out, "rows_scanned": scanned}


def b360_profile(domain: str, period: str, owner: str) -> dict[str, Any]:
    """The Borrower 360 profile itself (one borrower; `backend.b360.service.profile`)."""
    from backend.b360 import service
    return service.profile(domain, owner, period)


# ---------------------------------------------------------------- account conduct (open banking fields of the release)

def conduct(domain: str, period: str, owners: list[str]) -> dict[str, Any]:
    if domain == "retail":
        return R.conduct(period, owners)
    period, prior = resolve(domain, period)
    rows = rd.q(f"""SELECT borrower_id, reporting_quarter AS period,
                           MAX(operating_inflows_sar_mn) AS inflows, MIN(inflow_trend_pct) AS inflow_trend_pct,
                           MIN(balance_buffer_months) AS buffer_months, MAX(returned_payments_q) AS returned,
                           MAX(utilisation_pct) FILTER (WHERE product_type = 'overdraft') AS od_util,
                           COUNT(*) FILTER (WHERE product_type = 'overdraft') AS od_lines, COUNT(*) AS n
                    FROM {rd.exposure(domain)}
                    WHERE {_in(owners)} AND list_contains(?, reporting_quarter) GROUP BY 1, 2""",
                [owners, [p for p in (period, prior) if p]])
    rev = {r["borrower_id"]: _f(r["revenue_sar_mn"]) for r in rd.q(
        f"SELECT borrower_id, revenue_sar_mn FROM {rd.owner(domain)} WHERE reporting_quarter = ? AND {_in(owners)}",
        [period, owners])}
    by: dict[str, dict[str, dict[str, Any]]] = {}
    for r in rows:
        by.setdefault(r["borrower_id"], {})[r["period"]] = r
    out = {}
    for o in owners:
        now, before = by.get(o, {}).get(period, {}), by.get(o, {}).get(prior, {})
        inflows = _f(now.get("inflows"))
        revenue = rev.get(o)
        # Turnover through the bank against revenue: the quarter's operating inflows x 4 over annual revenue.
        routing = (100.0 * inflows * 4 / revenue) if inflows is not None and revenue else None
        out[o] = {"inflows_q": inflows, "inflow_trend_pct": _f(now.get("inflow_trend_pct")),
                  "turnover_to_revenue_pct": routing, "buffer_months": _f(now.get("buffer_months")),
                  "returned_payments_q": int(now.get("returned") or 0),
                  "returned_payments_prior": int(before.get("returned") or 0) if before else None,
                  "overdraft_utilisation_pct": _f(now.get("od_util")), "overdraft_lines": int(now.get("od_lines") or 0),
                  "overdraft_utilisation_prior": _f(before.get("od_util")) if before else None,
                  "revenue_sar_mn": revenue}
    return {"period": period, "by_owner": out, "rows_scanned": sum(int(r["n"]) for r in rows) + len(rev),
            "basis": "Open Banking fields of the EWS release (operating inflows, trend, balance buffer, returned "
                     "payments) and overdraft utilisation; turnover to revenue = quarterly inflows × 4 ÷ annual revenue."}


# ---------------------------------------------------------------- the bureau

def bureau(domain: str, period: str, owners: list[str]) -> dict[str, Any]:
    if domain == "retail":
        return R.bureau(period, owners)
    period, _ = resolve(domain, period)
    rows = rd.q(f"""SELECT borrower_id, MAX(external_exposure_sar_mn) AS ext_exposure, MAX(external_dpd_days) AS ext_dpd,
                           MAX(external_default_flag) AS ext_default, MAX(enquiries_q) AS enquiries, COUNT(*) AS n
                    FROM {rd.exposure(domain)} WHERE reporting_quarter = ? AND {_in(owners)} GROUP BY 1""",
                [period, owners])
    out = {o: {"available": False} for o in owners}
    for r in rows:
        avail = any(r[k] is not None for k in ("ext_exposure", "ext_dpd", "ext_default", "enquiries"))
        out[r["borrower_id"]] = {"available": avail, "external_exposure_sar_mn": _f(r["ext_exposure"]),
                                 "external_dpd_days": int(r["ext_dpd"] or 0), "external_default": bool(r["ext_default"]),
                                 "enquiries_q": int(r["enquiries"] or 0)}
    return {"period": period, "by_owner": out, "rows_scanned": sum(int(r["n"]) for r in rows),
            "basis": "Bureau fields of the EWS release (keyed to the spine)."}


# ---------------------------------------------------------------- peers in the same sector

def sector_peers(domain: str, period: str, sub_sectors: list[str]) -> dict[str, Any]:
    if domain == "retail":
        return R.sector_peers(period, sub_sectors)
    period, prior = resolve(domain, period)
    floor = warned_min(domain)
    rows = rd.q(f"""WITH b AS (SELECT reporting_quarter AS p, sector, sub_sector, borrower_id, MAX(ews_score) AS s,
                                      MIN(inflow_trend_pct) AS inflow
                               FROM {rd.exposure(domain)} WHERE list_contains(?, reporting_quarter) GROUP BY 1, 2, 3, 4)
                    SELECT p, sector, sub_sector, COUNT(*) AS names, COUNT(*) FILTER (WHERE s >= ?) AS warned,
                           MEDIAN(inflow) AS median_inflow_trend FROM b GROUP BY 1, 2, 3""",
                [[x for x in (period, prior) if x], floor])
    book = {p: (sum(r["warned"] for r in rows if r["p"] == p), sum(r["names"] for r in rows if r["p"] == p))
            for p in (period, prior) if p}
    book_share = {p: (100.0 * w / n if n else 0.0) for p, (w, n) in book.items()}
    out = {}
    for s in sub_sectors:
        now = next((r for r in rows if r["p"] == period and r["sub_sector"] == s), None)
        before = next((r for r in rows if r["p"] == prior and r["sub_sector"] == s), None)
        if not now:
            continue
        share = 100.0 * now["warned"] / now["names"] if now["names"] else 0.0
        share_prior = (100.0 * before["warned"] / before["names"]) if before and before["names"] else None
        stressed = share >= 1.5 * book_share[period] and (share_prior is None or share > share_prior)
        out[s] = {"sector": now["sector"], "names": int(now["names"]), "warned": int(now["warned"]),
                  "warned_share_pct": share, "warned_share_prior_pct": share_prior,
                  "book_warned_share_pct": book_share[period], "median_inflow_trend_pct": _f(now["median_inflow_trend"]),
                  "sector_stress": bool(stressed)}
    return {"period": period, "by_sub_sector": out, "rows_scanned": sum(int(r["names"]) for r in rows),
            "basis": "Sector stress = the sub-sector's warned share is at least 1.5× the book's and rising on the quarter."}


# ---------------------------------------------------------------- what changed since last period

def changes(domain: str, period: str, owners: list[str]) -> dict[str, Any]:
    if domain == "retail":
        return R.changes(period, owners)
    period, prior = resolve(domain, period)
    if not prior:
        return {"period": period, "prior_period": "", "by_owner": {o: {"new": True} for o in owners}, "rows_scanned": 0}
    rows = rd.q(f"""SELECT borrower_id, reporting_quarter AS p, MAX(ews_score) AS score, MAX(dpd_days) AS dpd,
                           MAX(stage) AS stage, MIN(rating_notches_moved) AS notches, MAX(cure_flag) AS cured,
                           string_agg(ews_reasons, '; ') AS reasons_raw, COUNT(*) AS n
                    FROM {rd.exposure(domain)} WHERE {_in(owners)} AND list_contains(?, reporting_quarter)
                    GROUP BY 1, 2""", [owners, [period, prior]])
    rat = {(r["borrower_id"], r["p"]): r["rating_current"] for r in rd.q(
        f"""SELECT borrower_id, reporting_quarter AS p, rating_current FROM {rd.owner(domain)}
            WHERE {_in(owners)} AND list_contains(?, reporting_quarter)""", [owners, [period, prior]])}
    by: dict[str, dict[str, dict[str, Any]]] = {}
    for r in rows:
        by.setdefault(r["borrower_id"], {})[r["p"]] = r
    out = {}
    for o in owners:
        now, before = by.get(o, {}).get(period, {}), by.get(o, {}).get(prior)
        rs = lambda r: {x.strip() for x in ((r or {}).get("reasons_raw") or "").split(";") if x.strip()}  # noqa: E731
        if not before:
            out[o] = {"new": True, "prior_period": prior}
            continue
        out[o] = {"new": False, "prior_period": prior,
                  "score_prior": int(before["score"] or 0), "score_change": int(now.get("score") or 0) - int(before["score"] or 0),
                  "dpd_prior": int(before["dpd"] or 0), "dpd_now": int(now.get("dpd") or 0),
                  "stage_prior": int(before["stage"] or 0), "stage_now": int(now.get("stage") or 0),
                  "rating_prior": rat.get((o, prior)), "rating_now": rat.get((o, period)),
                  "new_reasons": sorted(rs(now) - rs(before)), "cleared_reasons": sorted(rs(before) - rs(now)),
                  "cured_flag": bool(now.get("cured")),
                  "dpd_cured": int(before["dpd"] or 0) > 0 and int(now.get("dpd") or 0) == 0}
    return {"period": period, "prior_period": prior, "by_owner": out, "rows_scanned": sum(int(r["n"]) for r in rows)}


# ---------------------------------------------------------------- the EWS ECL-impact computation, per name

def ecl_impact(domain: str, period: str, owners: list[str]) -> dict[str, Any]:
    """Per borrower: the existing EWS ECL-impact figures (`backend.risk_intel.ecl_impact`, p = the bucket PD from
    Admin), the book's lifetime ECL (Stage 2 move) and ECL if defaulted (Stage 3 move)."""
    from backend.risk_intel import ecl_impact as ei
    from backend.risk_intel import store

    period, _ = resolve(domain, period)
    cfg = store.pd_by_bucket()
    pds = {k: float(cfg["values"][k]) / 100.0 for k in ei.BUCKETS}
    f, period = ei._frame(domain, period)
    f = f[f["owner"].isin(owners)]
    life = R.lifetime_ecl(period, owners) if domain == "retail" else {r["borrower_id"]: _f(r["life"]) or 0.0 for r in rd.q(
        f"""SELECT borrower_id, SUM(ecl_lifetime_sar_mn) AS life FROM {rd.exposure(domain)}
            WHERE reporting_quarter = ? AND {_in(owners)} AND stage < 3 AND dpd_days < 90 GROUP BY 1""",
        [period, owners])}
    out = {}
    for o, g in f.groupby("owner"):
        agg = ei._agg(g, pds)
        bucket = str(g["bucket"].iloc[0])
        out[o] = {"bucket": bucket, "pd_pct": float(cfg["values"].get(bucket, 0.0)) if bucket in ei.BUCKETS else 0.0,
                  "ead": agg["ead"], "current_ecl": agg["current_ecl"], "expected_ecl": agg["expected_ecl"],
                  "expected_uplift": agg["uplift"], "ecl_if_defaulted": agg["ecl_if_defaulted"],
                  "stage3_uplift": agg["ecl_if_defaulted"] - agg["current_ecl"],
                  "lifetime_ecl": life.get(o, 0.0), "stage2_uplift": max(0.0, life.get(o, 0.0) - agg["current_ecl"])}
    return {"period": period, "by_owner": out, "rows_scanned": int(len(f)) + len(life),
            "method": ei.PACK, "pd_by_bucket": cfg.get("values"),
            "basis": ("EWS ECL impact (P3-ECL-01): expected ECL = p × ECL if defaulted + (1 − p) × current ECL over the "
                      "performing exposures; Stage 2 move = book lifetime ECL − current ECL; Stage 3 move = ECL if "
                      "defaulted (max of current ECL and EAD × LGD) − current ECL.")}


__all__ = ["DOMAIN", "NotOnThisBuild", "b360_evidence", "b360_profile", "bureau", "changes", "check_domain", "conduct",
           "ecl_impact", "periods", "resolve", "rules_and_trend", "sector_peers", "warned", "warned_min"]
