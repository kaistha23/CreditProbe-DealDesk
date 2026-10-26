"""The Early Warning domain API — an EWS-only app on its own port.

Why it is its own app. The Cockpit that the user is working in is frozen and
its code is protected, so `backend/cockpit_v4/app.py` is not touched and this
router is not mounted into it. This app has no Cockpit worker, no Cockpit
bootstrap and no external provider: it answers the restored Early Warning
screens out of the two independent EWS releases and nothing else.

The response shapes are the ones the restored screens already read
(`/early-warning`, `/canonical/drill`, `/canonical/model`, `/grid/*`), so the
components are ported unchanged in behaviour and only the reader underneath
them is new.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import pathlib
import sqlite3
import time
from typing import Any, Iterator

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from backend.access import install
from fastapi.responses import JSONResponse, Response

from backend.ews_domain import ews_catalogue as cat
from backend.ews_domain import ews_rules as ews
from backend.ews_domain import reader as rd

PREFIX = "/api/v1/ews-domain/workspace"
TENANT = "ews-preview"
from backend.ews_domain.paths import API_PORT, STORE, UI_ORIGINS  # noqa: E402

#: The receivers this handoff needs are queued, not restored. Every contract
#: this app hands out says so, in these words, and no endpoint here writes to
#: or reads from the Cockpit.
RECEIVERS = {
    "borrower_360": {"module": "Borrower 360", "status": "PENDING_RESTORATION"},
    "what_if": {"module": "What-If", "status": "PENDING_RESTORATION"},
    "investigation": {"module": "Cockpit investigation", "status": "PENDING_RESTORATION"},
}


@contextlib.contextmanager
def _store() -> Iterator[sqlite3.Connection]:
    """One connection per call, committed and then closed.

    `with sqlite3.connect(...) as c:` only commits; the connection sits in a
    reference cycle until the cyclic GC runs, so a polling screen leaked one
    descriptor per call until the process hit its open-file limit (R6 Session Q)."""
    STORE.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(STORE, timeout=10)
    try:
        c.execute("CREATE TABLE IF NOT EXISTS cohort ("
                  "object_id TEXT PRIMARY KEY, created_at REAL, body TEXT)")
        yield c
        c.commit()
    except BaseException:
        c.rollback()
        raise
    finally:
        c.close()


def fingerprint(domain_id: str) -> str:
    spec = rd.domain_spec(domain_id)
    return hashlib.sha256(
        f"{spec['release_id']}|{spec['source_release_id']}|{ews.RULESET_VERSION}"
        .encode()).hexdigest()[:16]


def identity(domain_id: str, period: str = "") -> dict[str, Any]:
    spec = rd.domain_spec(domain_id)
    chosen, prior, all_periods = rd.resolve_period(domain_id, period)
    return {"domain_id": domain_id, "release_id": spec["release_id"],
            "fingerprint": fingerprint(domain_id), "tenant_id": TENANT,
            "period": chosen, "prior_period": prior, "periods": all_periods,
            "ruleset": ews.RULESET_VERSION,
            "exposure_grain": spec["exposure_grain"],
            "owner_grain": spec["owner_grain"]}


def _where(domain_id: str, period: str, filters: list[dict[str, Any]],
           ) -> tuple[str, list[Any], list[str]]:
    spec = rd.domain_spec(domain_id)
    clause, params, described = rd.compile_filters(domain_id, filters)
    return (f'"{spec["period"]}" = ? AND ({clause})', [period, *params], described)


def _num(v: Any) -> float:
    return float(v or 0)


# ---- the Early Warning feed ------------------------------------------------

def early_warning_feed(domain_id: str, reason: str, period: str, dpd: str,
                       ) -> dict[str, Any]:
    spec = rd.domain_spec(domain_id)
    ident = identity(domain_id, period)
    chosen = ident["period"]
    exp = rd.exposure(domain_id)
    only_reason = rd.reason_filter(domain_id, reason)
    dpd_f = rd.dpd_filter(domain_id, dpd)
    page = [*only_reason, *dpd_f]

    w, p, described = _where(domain_id, chosen, page)
    bands = [{"value": r["value"], "n": r["n"], "ead_sar_mn": _num(r["ead_sar_mn"]),
              "ecl_sar_mn": _num(r["ecl_sar_mn"])}
             for r in rd.q(
                 f'SELECT ews_band AS value, COUNT(*) AS n, SUM(ead_sar_mn) AS ead_sar_mn, '
                 f'SUM(ecl_sar_mn) AS ecl_sar_mn FROM {exp} WHERE {w} '
                 f"AND ews_band <> 'none' GROUP BY 1 ORDER BY 1", p)]

    seg = spec["segment"]
    rows = rd.q(f'SELECT "{seg}" AS segment, ews_band AS value, COUNT(*) AS n, '
                f'SUM(ead_sar_mn) AS ead_sar_mn, SUM(ecl_sar_mn) AS ecl_sar_mn '
                f"FROM {exp} WHERE {w} AND ews_band <> 'none' GROUP BY 1, 2 ORDER BY 1, 2", p)
    by_segment: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_segment.setdefault(str(r["segment"]), []).append(
            {"value": r["value"], "n": r["n"], "ead_sar_mn": _num(r["ead_sar_mn"]),
             "ecl_sar_mn": _num(r["ecl_sar_mn"])})

    # The reasons chart carries the page's past-due filter but NOT its own rule
    # filter, so every rule stays selectable — the restored behaviour.
    rw, rp, _ = _where(domain_id, chosen, dpd_f)
    reasons = [{"reason": r["reason"], "n": r["n"], "ead": _num(r["ead_sar_mn"])}
               for r in rd.q(
                   "SELECT trim(reason) AS reason, COUNT(*) AS n, SUM(ead_sar_mn) AS ead_sar_mn FROM ("
                   f"SELECT ead_sar_mn, unnest(string_split(ews_reasons, '; ')) AS reason "
                   f"FROM {exp} WHERE {rw} AND ews_reasons <> '') "
                   "WHERE trim(reason) <> '' GROUP BY 1 ORDER BY 2 DESC", rp)]

    dpd_bands: list[dict[str, Any]] = []
    has_dpd = "dpd_days" in rd.columns(domain_id)
    if has_dpd:
        for band in rd.DPD_BANDS:
            bw, bp, _ = _where(domain_id, chosen,
                               [{"column": "dpd_days", "op": "between",
                                 "values": [band["low"], band["high"]]}, *only_reason])
            brows = [{"value": r["value"], "n": r["n"],
                      "ead_sar_mn": _num(r["ead_sar_mn"]), "ecl_sar_mn": _num(r["ecl_sar_mn"])}
                     for r in rd.q(
                         "SELECT ews_band AS value, COUNT(*) AS n, SUM(ead_sar_mn) AS ead_sar_mn, "
                         f"SUM(ecl_sar_mn) AS ecl_sar_mn FROM {exp} WHERE {bw} "
                         "GROUP BY 1 ORDER BY 1", bp)]
            severe = [r for r in brows if r["value"] in rd.SEVERE]
            dpd_bands.append({
                **{k: band[k] for k in ("key", "label", "low", "high")},
                "bands": [r for r in brows if r["value"] != "none"],
                "n": sum(int(r["n"]) for r in brows),
                "ead_sar_mn": sum(r["ead_sar_mn"] for r in brows),
                "severe_n": sum(int(r["n"]) for r in severe),
                "severe_ead_sar_mn": sum(r["ead_sar_mn"] for r in severe)})

    # The whole history the release carries — all 20 periods, from its own
    # portfolio series, not a window of the last few.
    pcol = spec["period"]
    trend = [{"period": r[pcol], "value": _num(r["severe_ead_sar_mn"])}
             for r in rd.q(f'SELECT "{pcol}", SUM(severe_ead_sar_mn) AS severe_ead_sar_mn '
                           f"FROM {rd.series(domain_id, 'portfolio')} GROUP BY 1 ORDER BY 1")]

    severe_w, severe_p, _ = _where(
        domain_id, chosen, [*page, {"column": "ews_band", "op": "in", "values": list(rd.SEVERE)}])
    top = rd.q(f"SELECT * FROM {exp} WHERE {severe_w} ORDER BY ews_score DESC, "
               f'ead_sar_mn DESC LIMIT 50', severe_p)
    total = rd.q(f"SELECT COUNT(*) AS n FROM {exp} WHERE {severe_w}", severe_p)[0]["n"]

    return {**ident, "rules": ews.describe(domain_id),
            "segment_dimension": spec["segment_label"],
            "bands": bands,
            "by_segment": [{"segment": k, "bands": v} for k, v in sorted(by_segment.items())],
            "reasons": reasons, "top": top, "severe_total": total,
            "severe_ead_trend": trend, "reason": reason,
            "dpd": dpd, "dpd_bands": dpd_bands, "dpd_available": has_dpd,
            "dpd_overlap": rd.DPD_OVERLAP,
            "filters": page, "filter_description": "; ".join(described),
            "model_calls": 0,
            "handoff_receivers": RECEIVERS}


# ---- the drill -------------------------------------------------------------

def ladder(domain_id: str) -> list[dict[str, Any]]:
    spec = rd.domain_spec(domain_id)
    return [
        {"id": "segment", "column": spec["segment"], "label": spec["segment_label"].title(),
         "grain": "segment", "alternate": spec["alternate"]},
        {"id": "subsegment", "column": spec["subsegment"],
         "label": spec["subsegment_label"].title(), "grain": "segment"},
        {"id": "owner", "column": spec["owner_key"],
         "label": spec["owner_grain"].title(), "grain": "owner"},
        {"id": "exposure", "column": spec["key"],
         "label": spec["exposure_grain"].title(), "grain": "exposure"},
    ]


def _path_filters(domain_id: str, path: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rungs = {r["id"]: r for r in ladder(domain_id)}
    out = []
    for step in path or []:
        rung = rungs.get(str(step.get("level")))
        if rung is None:
            raise rd.ReadRefused(f"{step.get('level')!r} is not a rung of the "
                                 f"{domain_id} ladder.")
        out.append({"column": rung["column"], "op": "eq", "value": step.get("value")})
    return out


def _totals(domain_id: str, period: str, filters: list[dict[str, Any]]) -> dict[str, Any]:
    spec = rd.domain_spec(domain_id)
    o = spec["owner_key"]
    w, p, _ = _where(domain_id, period, filters)
    r = rd.q(
        f'SELECT COUNT(*) AS exposures, COUNT(DISTINCT "{o}") AS owners, '
        "SUM(ead_sar_mn) AS ead_sar_mn, SUM(ecl_sar_mn) AS ecl_sar_mn, "
        "SUM(CASE WHEN bad THEN ead_sar_mn ELSE 0 END) AS bad_ead_sar_mn, "
        f'COUNT(DISTINCT CASE WHEN bad THEN "{o}" END) AS bad_owners, '
        "SUM(CASE WHEN bad THEN 1 ELSE 0 END) AS bad_exposures, "
        "SUM(CASE WHEN warned_performing THEN ead_sar_mn ELSE 0 END) AS warned_performing_ead_sar_mn, "
        f'COUNT(DISTINCT CASE WHEN warned_performing THEN "{o}" END) AS warned_performing_owners, '
        "SUM(CASE WHEN warned_performing THEN 1 ELSE 0 END) AS warned_performing_exposures "
        f"FROM (SELECT *, (stage = 3 OR default_flag = 1) AS bad, "
        "(ews_band IN ('critical', 'high') AND NOT (stage = 3 OR default_flag = 1)) "
        f"AS warned_performing FROM {rd.exposure(domain_id)} WHERE {w})", p)[0]
    return {k: (int(v or 0) if "sar" not in k else _num(v)) for k, v in r.items()}


def drill_feed(body: dict[str, Any]) -> dict[str, Any]:
    domain_id = str(body.get("domain") or "retail")
    spec = rd.domain_spec(domain_id)
    ident = identity(domain_id, str(body.get("period") or ""))
    period = ident["period"]
    path = list(body.get("path") or [])
    reason = str(body.get("reason") or "")
    dpd = str(body.get("dpd") or "")
    bands = list(body.get("bands") or [])
    alternate = bool(body.get("alternate"))
    search = str(body.get("search") or "")
    limit = min(int(body.get("limit") or 50), 200)

    base = [*_path_filters(domain_id, path), *rd.reason_filter(domain_id, reason),
            *rd.dpd_filter(domain_id, dpd)]
    rungs = ladder(domain_id)
    depth = len(path)
    level = dict(rungs[min(depth, len(rungs) - 1)])
    column_in_use = (level.get("alternate") or level["column"]) if (alternate and depth == 0) \
        else level["column"]
    level["column_in_use"] = column_in_use

    totals = _totals(domain_id, period, base)
    w, p, described = _where(domain_id, period, base)
    exp = rd.exposure(domain_id)
    o = spec["owner_key"]

    band_rows = rd.q(
        f'SELECT ews_band AS value, COUNT(*) AS exposures, COUNT(DISTINCT "{o}") AS owners_touching, '
        "SUM(ead_sar_mn) AS ead_sar_mn, SUM(ecl_sar_mn) AS ecl_sar_mn "
        f"FROM {exp} WHERE {w} GROUP BY 1", p)
    worst = rd.q(
        "SELECT band AS value, COUNT(*) AS owners FROM ("
        f'SELECT "{o}" AS owner, max(ews_score) AS s, '
        "arg_max(ews_band, ews_score) AS band "
        f"FROM {exp} WHERE {w} GROUP BY 1) GROUP BY 1", p)
    worst_by = {r["value"]: int(r["owners"]) for r in worst}
    order = {b: i for i, b in enumerate([*rd.BANDS, "none"])}
    bands_out = sorted(
        [{"value": r["value"], "owners": worst_by.get(r["value"], 0),
          "owners_touching": int(r["owners_touching"]), "exposures": int(r["exposures"]),
          "ead_sar_mn": _num(r["ead_sar_mn"]), "ecl_sar_mn": _num(r["ecl_sar_mn"])}
         for r in band_rows], key=lambda r: order.get(r["value"], 99))

    stage_mix = [{"value": r["value"], "n": int(r["n"]), "ead_sar_mn": _num(r["ead_sar_mn"]),
                  "ecl_sar_mn": _num(r["ecl_sar_mn"])}
                 for r in rd.q("SELECT stage AS value, COUNT(*) AS n, SUM(ead_sar_mn) AS ead_sar_mn, "
                               f"SUM(ecl_sar_mn) AS ecl_sar_mn FROM {exp} WHERE {w} "
                               "GROUP BY 1 ORDER BY 1", p)]

    overview = {**ident, "totals": totals, "bands": bands_out, "stage_mix": stage_mix,
                "filter_description": "; ".join(described) or f"all {spec['exposure_grain']}s"}

    reasons_out = _reasons(domain_id, period, base)

    next_level: list[dict[str, Any]] | None = None
    level_history: dict[str, list[dict[str, Any]]] = {}
    level_reasons: dict[str, list[dict[str, Any]]] = {}
    if level["grain"] != "exposure":
        next_level = _level_rows(domain_id, period, base, column_in_use, o)
        values = [r["value"] for r in next_level[:24]]
        level_history = _level_history(domain_id, base, column_in_use, values, o)
        for v in values:
            level_reasons[str(v) if v is not None else ""] = _reasons(
                domain_id, period, [*base, {"column": column_in_use, "op": "eq", "value": v}],
                limit=4)

    owners = None
    if level["grain"] in ("owner", "exposure") or depth >= 2:
        owners = _owner_page(domain_id, period, base, search, limit)

    return {"ladder": rungs, "depth": depth, "level": level, "path": path,
            "reason": reason, "overview": overview, "reasons": reasons_out,
            "next_level": next_level, "level_history": level_history,
            "level_reasons": level_reasons,
            "history": _overview_history(domain_id, base, o),
            "owners": owners, "bands_in_use": bands, "model_calls": 0}


def _reasons(domain_id: str, period: str, filters: list[dict[str, Any]],
             limit: int = 20) -> list[dict[str, Any]]:
    spec = rd.domain_spec(domain_id)
    w, p, _ = _where(domain_id, period, filters)
    rows = rd.q(
        f'SELECT trim(reason) AS reason, COUNT(*) AS exposures, COUNT(DISTINCT "{spec["owner_key"]}") AS owners, '
        "SUM(ead_sar_mn) AS ead_sar_mn FROM ("
        f'SELECT "{spec["owner_key"]}", ead_sar_mn, unnest(string_split(ews_reasons, \'; \')) AS reason '
        f"FROM {rd.exposure(domain_id)} WHERE {w} AND ews_reasons <> '') "
        f"WHERE trim(reason) <> '' GROUP BY 1 ORDER BY 2 DESC LIMIT {limit}", p)
    meta = {r["label"]: r for r in ews.describe(domain_id)}
    return [{"id": meta.get(r["reason"], {}).get("id", ""), "reason": r["reason"],
             "weight": int(meta.get(r["reason"], {}).get("weight", 0)),
             "limitation": meta.get(r["reason"], {}).get("limitation", ""),
             "exposures": int(r["exposures"]), "owners": int(r["owners"]),
             "ead_sar_mn": _num(r["ead_sar_mn"])} for r in rows]


def _level_rows(domain_id: str, period: str, filters: list[dict[str, Any]],
                column: str, o: str) -> list[dict[str, Any]]:
    w, p, _ = _where(domain_id, period, filters)
    return [{"value": r["value"], **{k: (int(v or 0) if "sar" not in k and k != "worst_ews_score"
                                         else (_num(v) if "sar" in k else
                                               (None if v is None else int(v))))
                                     for k, v in r.items() if k != "value"}}
            for r in rd.q(
                f'SELECT "{column}" AS value, COUNT(*) AS exposures, COUNT(DISTINCT "{o}") AS owners, '
                "SUM(ead_sar_mn) AS ead_sar_mn, SUM(ecl_sar_mn) AS ecl_sar_mn, "
                f'COUNT(DISTINCT CASE WHEN warned THEN "{o}" END) AS warned_owners, '
                "SUM(CASE WHEN warned THEN ead_sar_mn ELSE 0 END) AS warned_ead_sar_mn, "
                f'COUNT(DISTINCT CASE WHEN bad THEN "{o}" END) AS bad_owners, '
                "SUM(CASE WHEN bad THEN 1 ELSE 0 END) AS bad_exposures, "
                "SUM(CASE WHEN bad THEN ead_sar_mn ELSE 0 END) AS bad_ead_sar_mn, "
                "SUM(CASE WHEN bad THEN ecl_sar_mn ELSE 0 END) AS bad_ecl_sar_mn, "
                f'COUNT(DISTINCT CASE WHEN warned AND NOT bad THEN "{o}" END) AS warned_performing_owners, '
                "SUM(CASE WHEN warned AND NOT bad THEN ead_sar_mn ELSE 0 END) AS warned_performing_ead_sar_mn, "
                f'COUNT(DISTINCT CASE WHEN ews_band = \'critical\' THEN "{o}" END) AS critical_owners, '
                "max(ews_score) AS worst_ews_score FROM ("
                "SELECT *, (ews_band IN ('critical', 'high')) AS warned, "
                "(stage = 3 OR default_flag = 1) AS bad "
                f"FROM {rd.exposure(domain_id)} WHERE {w}) "
                "GROUP BY 1 ORDER BY warned_ead_sar_mn DESC NULLS LAST", p)]


def _level_history(domain_id: str, filters: list[dict[str, Any]], column: str,
                   values: list[Any], o: str) -> dict[str, list[dict[str, Any]]]:
    if not values:
        return {}
    spec = rd.domain_spec(domain_id)
    pcol = spec["period"]
    clause, params, _ = rd.compile_filters(
        domain_id, [f for f in filters if f["column"] != column])
    marks = ", ".join("?" for _ in values)
    rows = rd.q(
        f'SELECT "{pcol}" AS period, "{column}" AS value, COUNT(*) AS exposures, '
        f'COUNT(DISTINCT "{o}") AS owners, SUM(ead_sar_mn) AS ead_sar_mn, '
        "SUM(ecl_sar_mn) AS ecl_sar_mn, "
        f'COUNT(DISTINCT CASE WHEN ews_band IN (\'critical\', \'high\') THEN "{o}" END) AS warned_owners, '
        "SUM(CASE WHEN ews_band IN ('critical', 'high') THEN ead_sar_mn ELSE 0 END) AS warned_ead_sar_mn "
        f"FROM {rd.exposure(domain_id)} WHERE ({clause}) AND \"{column}\" IN ({marks}) "
        "GROUP BY 1, 2 ORDER BY 1", [*params, *values])
    out: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        key = str(r["value"]) if r["value"] is not None else ""
        out.setdefault(key, []).append(
            {"period": r["period"], "exposures": int(r["exposures"]), "owners": int(r["owners"]),
             "ead_sar_mn": _num(r["ead_sar_mn"]), "ecl_sar_mn": _num(r["ecl_sar_mn"]),
             "warned_owners": int(r["warned_owners"]),
             "warned_ead_sar_mn": _num(r["warned_ead_sar_mn"])})
    return out


def _overview_history(domain_id: str, filters: list[dict[str, Any]], o: str,
                      ) -> list[dict[str, Any]]:
    spec = rd.domain_spec(domain_id)
    pcol = spec["period"]
    clause, params, _ = rd.compile_filters(domain_id, filters)
    return [{"period": r["period"], "owners": int(r["owners"]), "bad_owners": int(r["bad_owners"]),
             "warned_performing_owners": int(r["warned_performing_owners"]),
             "exposures": int(r["exposures"]), "ead_sar_mn": _num(r["ead_sar_mn"]),
             "ecl_sar_mn": _num(r["ecl_sar_mn"]),
             "warned_ead_sar_mn": _num(r["warned_ead_sar_mn"]),
             "bad_ead_sar_mn": _num(r["bad_ead_sar_mn"])}
            for r in rd.q(
                f'SELECT "{pcol}" AS period, COUNT(DISTINCT "{o}") AS owners, '
                f'COUNT(DISTINCT CASE WHEN bad THEN "{o}" END) AS bad_owners, '
                f'COUNT(DISTINCT CASE WHEN warned AND NOT bad THEN "{o}" END) AS warned_performing_owners, '
                "COUNT(*) AS exposures, SUM(ead_sar_mn) AS ead_sar_mn, SUM(ecl_sar_mn) AS ecl_sar_mn, "
                "SUM(CASE WHEN warned THEN ead_sar_mn ELSE 0 END) AS warned_ead_sar_mn, "
                "SUM(CASE WHEN bad THEN ead_sar_mn ELSE 0 END) AS bad_ead_sar_mn FROM ("
                "SELECT *, (ews_band IN ('critical', 'high')) AS warned, "
                "(stage = 3 OR default_flag = 1) AS bad "
                f"FROM {rd.exposure(domain_id)} WHERE ({clause})) GROUP BY 1 ORDER BY 1", params)]


OWNER_FIELDS = {
    "corporate": ["borrower_name", "sector", "sub_sector", "region", "relationship_tier"],
    "retail": ["customer_segment", "employment_type", "region", "product", "score_band"],
}


def _owner_page(domain_id: str, period: str, filters: list[dict[str, Any]],
                search: str, limit: int) -> dict[str, Any]:
    spec = rd.domain_spec(domain_id)
    o = spec["owner_key"]
    f = list(filters)
    if search:
        f = [*f, {"column": o, "op": "contains", "value": search}]
    w, p, _ = _where(domain_id, period, f)
    fields = [c for c in OWNER_FIELDS[domain_id] if c in rd.columns(domain_id)]
    picks = ", ".join(f'any_value("{c}") AS "{c}"' for c in fields)
    rows = rd.q(
        f'SELECT "{o}" AS owner_id, {picks + ", " if picks else ""}'
        "COUNT(*) AS exposures, SUM(ead_sar_mn) AS ead_sar_mn, SUM(ecl_sar_mn) AS ecl_sar_mn, "
        "max(ews_score) AS ews_score, arg_max(ews_band, ews_score) AS ews_band, "
        "max(stage) AS worst_stage, max(dpd_days) AS worst_dpd_days "
        f"FROM {rd.exposure(domain_id)} WHERE {w} GROUP BY 1 "
        f"ORDER BY ews_score DESC, ead_sar_mn DESC LIMIT {limit}", p)
    total = rd.q(f'SELECT COUNT(DISTINCT "{o}") AS owners, COUNT(*) AS exposures, '
                 "SUM(ead_sar_mn) AS ead_sar_mn, SUM(ecl_sar_mn) AS ecl_sar_mn "
                 f"FROM {rd.exposure(domain_id)} WHERE {w}", p)[0]
    return {**identity(domain_id, period), "owner_column": o, "fields": fields,
            "rows": rows,
            "total": {"owners": int(total["owners"]), "exposures": int(total["exposures"]),
                      "ead_sar_mn": _num(total["ead_sar_mn"]),
                      "ecl_sar_mn": _num(total["ecl_sar_mn"])},
            "sort": "ews_score", "desc": True, "offset": 0, "limit": limit,
            "search": search}


# ---- the model card --------------------------------------------------------

def model_meta(domain_id: str, period: str) -> dict[str, Any]:
    spec = rd.domain_spec(domain_id)
    ident = identity(domain_id, period)
    chosen = ident["period"]
    available = set(rd.columns(domain_id))
    exp = rd.exposure(domain_id)
    pcol = spec["period"]
    o = spec["owner_key"]

    rules: list[dict[str, Any]] = []
    live = no_match = 0
    for rule in ews.describe(domain_id):
        needed = ews._columns(rule["sql"])
        missing = sorted(needed - available)
        evaluated = not missing
        tripped = owners_tripped = None
        if evaluated:
            r = rd.q(f'SELECT COUNT(*) AS n, COUNT(DISTINCT "{o}") AS owners FROM {exp} '
                     f'WHERE "{pcol}" = ? AND ({rule["sql"]})', [chosen])[0]
            tripped, owners_tripped = int(r["n"]), int(r["owners"])
            if tripped:
                live += 1
            else:
                no_match += 1
        rules.append({
            "id": rule["id"], "label": rule["label"], "weight": int(rule["weight"]),
            "expression": rule["sql"], "inputs": sorted(needed),
            "missing_columns": missing, "evaluated": evaluated,
            "limitation": rule.get("limitation", ""),
            "exposures_tripped": tripped, "owners_tripped": owners_tripped,
            "status": ("live" if tripped else "live_no_match") if evaluated else "not_evaluated"})

    cov = rd.q("SELECT COUNT(*) AS exposures, "
               "SUM(CASE WHEN ews_score IS NULL THEN 1 ELSE 0 END) AS unscored_exposures, "
               f'COUNT(DISTINCT "{o}") AS owners FROM {exp} WHERE "{pcol}" = ?', [chosen])[0]
    obs = rd.q("SELECT ews_band AS band, COUNT(*) AS exposures, "
               f'COUNT(DISTINCT "{o}") AS owners, min(ews_score) AS observed_min_score, '
               "max(ews_score) AS observed_max_score, avg(ews_score) AS observed_mean_score, "
               f'SUM(ead_sar_mn) AS ead_sar_mn FROM {exp} WHERE "{pcol}" = ? GROUP BY 1', [chosen])
    floors = {name: floor for floor, name in ews.bands(domain_id)}
    score_bands = sorted(
        [{"band": r["band"], "min_score_required": floors.get(r["band"]),
          "exposures": int(r["exposures"]), "owners": int(r["owners"]),
          "observed_min_score": None if r["observed_min_score"] is None else int(r["observed_min_score"]),
          "observed_max_score": None if r["observed_max_score"] is None else int(r["observed_max_score"]),
          "observed_mean_score": None if r["observed_mean_score"] is None else round(float(r["observed_mean_score"]), 3),
          "ead_sar_mn": _num(r["ead_sar_mn"])} for r in obs],
        key=lambda r: -(r["min_score_required"] or 0))

    catalogue = cat.catalogue(domain_id)
    catalogue = {**catalogue, **{k: ident[k] for k in
                                ("domain_id", "release_id", "fingerprint", "tenant_id",
                                 "period", "prior_period", "periods", "ruleset",
                                 "exposure_grain", "owner_grain")}}
    for signal in catalogue.get("signals", []):
        missing = [i for i in signal.get("inputs", [])
                   if i.get("canonical_field") and i["canonical_field"] not in available]
        signal["missing_on_this_release"] = [i["canonical_field"] for i in missing]
        signal["evaluable_on_this_release"] = not missing

    return {**ident,
            "bands": [{"band": name, "min_score": floor} for floor, name in ews.bands(domain_id)],
            "rules": rules, "rules_evaluated": live + no_match, "rules_live": live,
            "rules_no_match": no_match, "rules_total": len(rules),
            "coverage": {"exposures": int(cov["exposures"]),
                         "unscored_exposures": int(cov["unscored_exposures"] or 0),
                         "owners": int(cov["owners"])},
            "model_calls": 0,
            "basis": ("Severity is the sum of the severity weights of the rules an "
                      "exposure trips, banded. A weight is not a coefficient and the "
                      "rule set makes no model call."),
            "score_observations": {"bands": score_bands,
                                   "how": "Observed on this release at this period.",
                                   "layers": 1, "model_calls": 0},
            "catalogue": catalogue,
            "reference": cat.reference_compatibility(domain_id),
            "log": {"ruleset": ews.RULESET_VERSION, "release_id": ident["release_id"],
                    "fingerprint": ident["fingerprint"], "period": chosen,
                    "entries": [{"version": v, "status": rs["status"], "effective": rs["effective"],
                                 "change": rs["change"],
                                 "band_floors": dict(zip(("moderate", "high", "critical"),
                                                         rs["band_floors"][domain_id])),
                                 "rules": [{"id": r["id"], "sql": r["sql"], "weight": r["weight"]}
                                           for r in rs["rules"][domain_id]],
                                 "applied_to_periods": ident["periods"] if rs["status"] == "active" else [],
                                 "source": "backend/ews_domain/ews_rules.py",
                                 "evidence": ("EWS_PACKAGE_MANIFEST.json" if rs["status"] == "active"
                                              else "evidence/v5/ews/calibration/ruleset_1_1_0.json (before)")}
                                for v, rs in ews.RULESETS.items()],
                    "history_available": True, "history_relations": [],
                    "disclosure": ("This release is scored with the active rule set only. The superseded "
                                   "version is recorded with its rules and band floors; its results at the "
                                   "as-of date are in the calibration evidence.")},
            "performance_metrics": {
                "available": False,
                "statement": ("No accuracy, AUC, KS, Gini or backtest result exists for "
                              "this rule set in any preserved file, so none is shown."),
            }}


# ---- the governed grid -----------------------------------------------------

GROUPS = {"ews_band": "Early warning", "ews_score": "Early warning",
          "ews_reasons": "Early warning", "ews_ruleset_version": "Early warning",
          "ead_sar_mn": "Exposure", "ecl_sar_mn": "Impairment",
          "dpd_days": "Delinquency", "stage": "Impairment"}
HIDE = {"tenant_id", "ews_release_id", "source_release_id", "source_table",
        "ews_grain", "source_dataset_release_id", "domain_id"}


def grid_schema(domain_id: str) -> dict[str, Any]:
    spec = rd.domain_spec(domain_id)
    ident = identity(domain_id, "")
    cols = rd.columns(domain_id)
    headline = [spec["key"], spec["owner_key"], spec["period"], spec["segment"],
                spec["subsegment"], "ews_band", "ews_score", "ews_reasons",
                "ead_sar_mn", "ecl_sar_mn", "stage", "dpd_days", "utilisation_pct"]
    columns = []
    for name, typ in cols.items():
        numeric = typ in ("NUMBER", "FLOAT", "DOUBLE", "DECIMAL") or "INT" in typ
        columns.append({
            "key": name, "label": name.replace("_", " ").replace(" sar mn", " (SAR mn)").strip().capitalize(),
            "type": "number" if numeric else "string",
            "unit": "SAR mn" if name.endswith("_sar_mn") else ("%" if name.endswith("_pct") else
                                                               ("days" if name.endswith("_days") else "")),
            "filter": "range" if numeric else "category",
            "group": GROUPS.get(name, "Book"),
            "description": "", "visible": name in headline})
    return {**{k: ident[k] for k in ("domain_id", "release_id", "fingerprint", "period",
                                     "prior_period", "periods")},
            "grain": spec["exposure_grain"], "grain_plural": spec["exposure_grain"] + "s",
            "owner_plural": spec["owner_grain"] + "s", "key": spec["key"],
            "owner": spec["owner_key"],
            "columns": [c for c in columns if c["key"] not in HIDE],
            "ews_ruleset": ews.RULESET_VERSION}


def grid_query(body: dict[str, Any]) -> dict[str, Any]:
    started = time.time()
    domain_id = str(body.get("domain") or "retail")
    spec = rd.domain_spec(domain_id)
    ident = identity(domain_id, str(body.get("period") or ""))
    period = ident["period"]
    filters = [f for f in (body.get("filters") or [])
               if f.get("column") != spec["period"]]
    sort = str(body.get("sort") or "ews_score")
    if sort not in rd.columns(domain_id):
        raise rd.ReadRefused(f"{sort!r} is not a column of this release.")
    desc = bool(body.get("desc", True))
    offset = max(int(body.get("offset") or 0), 0)
    limit = min(int(body.get("limit") or 50), 500)
    w, p, described = _where(domain_id, period, filters)
    exp = rd.exposure(domain_id)
    rows = rd.q(f'SELECT * FROM {exp} WHERE {w} ORDER BY "{sort}" '
                f'{"DESC" if desc else "ASC"} NULLS LAST LIMIT {limit} OFFSET {offset}', p)
    o = spec["owner_key"]
    s = rd.q(f'SELECT COUNT(*) AS entities, COUNT(DISTINCT "{o}") AS owners, '
             "SUM(ead_sar_mn) AS ead, SUM(ecl_sar_mn) AS ecl "
             f"FROM {exp} WHERE {w}", p)[0]
    stage_mix = [{"stage": r["stage"], "n": int(r["n"]), "ead": _num(r["ead"]), "ecl": _num(r["ecl"])}
                 for r in rd.q("SELECT stage, COUNT(*) AS n, SUM(ead_sar_mn) AS ead, "
                               f"SUM(ecl_sar_mn) AS ecl FROM {exp} WHERE {w} GROUP BY 1 ORDER BY 1", p)]
    band_mix = [{"band": r["ews_band"], "n": int(r["n"]), "ead": _num(r["ead"])}
                for r in rd.q("SELECT ews_band, COUNT(*) AS n, SUM(ead_sar_mn) AS ead "
                              f"FROM {exp} WHERE {w} GROUP BY 1 ORDER BY 1", p)]
    return {"domain_id": domain_id, "release_id": ident["release_id"],
            "fingerprint": ident["fingerprint"], "period": period,
            "filters": body.get("filters") or [],
            "filter_description": "; ".join(described) or f"all {spec['exposure_grain']}s",
            "sort": sort, "desc": desc, "offset": offset, "limit": limit,
            "rows": rows, "total": int(s["entities"]),
            "summary": {"entities": int(s["entities"]), "owners": int(s["owners"]),
                        "ead": _num(s["ead"]), "ecl": _num(s["ecl"]),
                        "stage_mix": stage_mix, "band_dimension": "ews_band",
                        "band_mix": band_mix, "period": period},
            "server_ms": round((time.time() - started) * 1000, 1)}


# ---- cohorts and the queued handoffs ---------------------------------------

def cohort(body: dict[str, Any]) -> dict[str, Any]:
    domain_id = str(body.get("domain") or "retail")
    spec = rd.domain_spec(domain_id)
    ident = identity(domain_id, str(body.get("period") or ""))
    period = ident["period"]
    segment = str(body.get("segment") or "")
    bands = [b for b in (body.get("bands") or list(rd.SEVERE)) if b in rd.BANDS] or list(rd.SEVERE)
    reason = str(body.get("reason") or "")
    dpd = str(body.get("dpd") or "")
    filters = [*rd.bands_filter(bands), *rd.reason_filter(domain_id, reason),
               *rd.dpd_filter(domain_id, dpd)]
    if segment:
        filters.append({"column": spec["segment"], "op": "eq", "value": segment})
    w, p, described = _where(domain_id, period, filters)
    exp = rd.exposure(domain_id)
    o = spec["owner_key"]
    s = rd.q(f'SELECT COUNT(*) AS entities, COUNT(DISTINCT "{o}") AS owners, '
             "SUM(ead_sar_mn) AS ead, SUM(ecl_sar_mn) AS ecl "
             f"FROM {exp} WHERE {w}", p)[0]
    members = [r["key"] for r in rd.q(
        f'SELECT "{spec["key"]}" AS key FROM {exp} WHERE {w} ORDER BY 1', p)]
    owners = [r["owner"] for r in rd.q(
        f'SELECT DISTINCT "{o}" AS owner FROM {exp} WHERE {w} ORDER BY 1', p)]
    membership_hash = hashlib.sha256("\n".join(members).encode()).hexdigest()
    predicate = json.dumps({"domain": domain_id, "period": period, "filters": filters},
                           sort_keys=True)
    predicate_hash = hashlib.sha256(predicate.encode()).hexdigest()
    stage_mix = [{"stage": r["stage"], "n": int(r["n"]), "ead": _num(r["ead"]), "ecl": _num(r["ecl"])}
                 for r in rd.q("SELECT stage, COUNT(*) AS n, SUM(ead_sar_mn) AS ead, "
                               f"SUM(ecl_sar_mn) AS ecl FROM {exp} WHERE {w} GROUP BY 1 ORDER BY 1", p)]
    band_mix = [{"band": r["ews_band"], "n": int(r["n"]), "ead": _num(r["ead"])}
                for r in rd.q("SELECT ews_band, COUNT(*) AS n, SUM(ead_sar_mn) AS ead "
                              f"FROM {exp} WHERE {w} GROUP BY 1 ORDER BY 1", p)]
    object_id = "ews-cohort-" + predicate_hash[:12]
    cohort_body = {
        "name": f"{domain_id} {'/'.join(bands)}{(' · ' + segment) if segment else ''}"
                f"{(' · ' + reason) if reason else ''}{(' · ' + dpd + ' DPD') if dpd else ''}",
        "description": f"Frozen from Early Warning on {ident['release_id']} at {period}.",
        "domain_id": domain_id, "release_id": ident["release_id"],
        "fingerprint": ident["fingerprint"], "period": period,
        "grain": spec["exposure_grain"], "owner_grain": spec["owner_grain"],
        "selection": "row", "filters": filters,
        "filter_description": "; ".join(described),
        "membership_hash": membership_hash, "predicate_hash": predicate_hash,
        "counts": {"entities": int(s["entities"]), "owners": int(s["owners"])},
        "ead": _num(s["ead"]), "ecl": _num(s["ecl"]),
        "stage_mix": stage_mix, "band_mix": band_mix, "band_dimension": "ews_band",
        "source": {"kind": "early_warning", "label": f"EWS rule set {ews.RULESET_VERSION}"},
        "member_ids_preview": members[:25],
        "owner_ids_preview": owners[:25],
        "handoff": handoff(domain_id, period, segment, bands, reason, dpd,
                           object_id, membership_hash, int(s["entities"]), int(s["owners"])),
    }
    obj = {"object_id": object_id, "version": 1, "kind": "cohort",
           "title": cohort_body["name"], "status": "frozen", "domain_id": domain_id,
           "release_id": ident["release_id"], "fingerprint": ident["fingerprint"],
           "period": period, "owner_id": "ews-preview",
           "body": cohort_body,
           "lineage": {"source": "ews-domain-preview", "reader": "backend/ews_domain/reader.py",
                       "cockpit_written": False, "cockpit_read": False},
           "permissions": {"read": ["ews-preview"]}, "trace_refs": [], "tags": ["early-warning"],
           "content_hash": membership_hash, "seeded": False, "created_at": time.time()}
    with _store() as c:
        c.execute("INSERT OR REPLACE INTO cohort VALUES (?, ?, ?)",
                  (object_id, obj["created_at"], json.dumps(obj, default=str)))
    return obj


def handoff(domain_id: str, period: str, segment: str, bands: list[str], reason: str,
            dpd: str, cohort_id: str, membership_hash: str, entities: int,
            owners: int) -> dict[str, Any]:
    """The context a queued receiver will need, carried but not executed.

    Borrower 360 and What-If are not restored. This is the contract their
    screens will be handed: the same population, named by the same ids and the
    same period, with the receiver's status stated as pending. Nothing here
    reads or writes the Cockpit.
    """
    spec = rd.domain_spec(domain_id)
    return {
        "domain_id": domain_id, "domain": domain_id,
        "release_id": spec["release_id"], "ruleset": ews.RULESET_VERSION,
        "period": period, "period_grain": spec["period_label"],
        "exposure_grain": spec["exposure_grain"], "owner_grain": spec["owner_grain"],
        "exposure_id_field": spec["key"], "owner_id_field": spec["owner_key"],
        "filter": {"segment_dimension": spec["segment"], "segment": segment,
                   "bands": bands, "reason": reason, "dpd": dpd},
        "signals": [r["id"] for r in ews.describe(domain_id)],
        "signals_live": [r["id"] for r in ews.describe(domain_id)
                         if not (ews._columns(r["sql"]) - set(rd.columns(domain_id)))],
        "signals_not_live": [r["id"] for r in ews.describe(domain_id)
                             if (ews._columns(r["sql"]) - set(rd.columns(domain_id)))],
        "cohort_id": cohort_id, "cohort_digest": membership_hash,
        "counts": {"exposures": entities, "owners": owners},
        "receivers": RECEIVERS,
        "availability": ("The population, the period and the filter are carried. "
                         "Borrower 360 and What-If are queued for restoration, so "
                         "nothing opens them yet and no scenario has been run."),
        "cockpit_write": False, "cockpit_read": False,
    }


# ---- the app ---------------------------------------------------------------

app = FastAPI(title="Early Warning domain (preview)", version="ews-preview-1",
              docs_url=None, redoc_url=None)
# PLAN_R5 A1: the caller's data access policy on every route (before CORS, so CORS stays outermost).
install(app, "early_warning")
app.add_middleware(CORSMiddleware, allow_origins=UI_ORIGINS,
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(rd.ReadRefused)
async def refused(_: Request, exc: rd.ReadRefused) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": {
        "error_code": "EWS_READ_REFUSED", "message": str(exc)}})


@app.get(PREFIX + "/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "app": "ews-domain-preview", "port": API_PORT,
            "ruleset": ews.RULESET_VERSION,
            "datasets_root": str(rd.DATASETS),
            "domains": {d: rd.domain_spec(d)["release_id"] for d in rd.DOMAINS},
            "reads_cockpit": False, "writes_cockpit": False, "model_calls": 0}


@app.get(PREFIX + "/early-warning")
async def get_early_warning(domain: str = Query("retail"), reason: str = Query(""),
                            period: str = Query(""), dpd: str = Query("")) -> dict[str, Any]:
    return early_warning_feed(domain, reason, period, dpd)


@app.post(PREFIX + "/early-warning/cohort")
async def post_cohort(body: dict[str, Any]) -> dict[str, Any]:
    return cohort(body)


@app.post(PREFIX + "/early-warning/handoff")
async def post_handoff(body: dict[str, Any]) -> dict[str, Any]:
    c = cohort(body)
    return {"cohort": {"object_id": c["object_id"], "counts": c["body"]["counts"]},
            "context": c["body"]["handoff"]}


@app.post(PREFIX + "/canonical/drill")
async def post_drill(body: dict[str, Any]) -> dict[str, Any]:
    return drill_feed(body)


@app.get(PREFIX + "/canonical/model")
async def get_model(domain: str = Query("retail"), period: str = Query("")) -> dict[str, Any]:
    return model_meta(domain, period)


@app.get(PREFIX + "/canonical/signals")
async def get_signals(domain: str = Query("retail"), period: str = Query("")) -> dict[str, Any]:
    return model_meta(domain, period)["catalogue"]


@app.get(PREFIX + "/grid/schema")
async def get_grid_schema(domain: str = Query("retail")) -> dict[str, Any]:
    return grid_schema(domain)


@app.post(PREFIX + "/grid/query")
async def post_grid_query(body: dict[str, Any]) -> dict[str, Any]:
    return grid_query(body)


@app.get(PREFIX + "/objects/{object_id}")
async def get_object(object_id: str) -> dict[str, Any]:
    with _store() as c:
        row = c.execute("SELECT body FROM cohort WHERE object_id = ?",
                        (object_id,)).fetchone()
    if not row:
        raise HTTPException(404, {"error_code": "NOT_FOUND",
                                  "message": f"{object_id} is not a saved EWS cohort."})
    return json.loads(row[0])


# ---- v5: the drill the Early Warning screens read --------------------------
#
# portfolio -> segment -> (classification) -> sub-segment -> customers ->
# customer, for both books. See drill.py for the counting rules.

from backend.ews_domain import drill  # noqa: E402

DRILL = "/api/v1/ews"


@app.get(DRILL + "/health")
async def drill_health() -> dict[str, Any]:
    return {"status": "ok", "app": "creditprobe-v5-early-warning", "port": API_PORT,
            "ruleset": ews.RULESET_VERSION,
            "releases": {d: rd.domain_spec(d)["release_id"] for d in rd.DOMAINS},
            "as_of": {d: rd.periods(d)[-1] for d in rd.DOMAINS},
            "reads_cockpit": False, "writes_cockpit": False, "model_calls": 0}


@app.get(DRILL + "/meta")
async def drill_meta(domain: str = Query("corporate")) -> dict[str, Any]:
    return drill.meta(domain)


@app.get(DRILL + "/level")
async def drill_level(domain: str = Query("corporate"), period: str = Query(""),
                      segment: str = Query(""), classification: str = Query(""),
                      subsegment: str = Query("")) -> dict[str, Any]:
    return drill.level(domain, period, segment, classification, subsegment)


@app.get(DRILL + "/crm")
async def drill_crm(domain: str = Query("corporate"), limit: int = Query(8, ge=0, le=200)) -> dict[str, Any]:
    """R7 (C3.3): the CBUAE CRM compliance card on the Early Warning home: the checks on this book at its latest
    period, breaches by article, and the largest breaches (deterministic, `backend.regulatory.crm_checks`)."""
    from backend.regulatory import crm_checks

    if domain not in ("corporate", "retail"):
        raise rd.ReadRefused("domain is corporate or retail.")
    res = crm_checks.run()
    checks = [c for c in res["checks"] if c["book"] == domain]
    rows = [r for r in res["breaches"] if r["book"] == domain]
    arts: dict[str, dict[str, Any]] = {}
    for c in checks:
        a = arts.setdefault(c["article"], {"article": c["article"], "title": c["title"], "breaches": 0,
                                           "ead_sar_mn": 0.0, "ecl_sar_mn": 0.0, "shortfall_sar_mn": 0.0})
        a["breaches"] += c["breaches"]
        if c["level"] == "book":  # a book-level rule: its measure, not an exposure in breach
            hit = next((r for r in rows if r["check_id"] == c["check_id"]), None)
            a["note"] = (f"Stage 3 is {hit['measured']}% of EAD (above {hit['required']:g}%)" if hit else
                         "Stage 3 within 5% of EAD")
            continue
        for k in ("ead_sar_mn", "ecl_sar_mn", "shortfall_sar_mn"):
            a[k] = round(a[k] + c[k], 4)
    return {"domain": domain, "period": res["periods"][domain], "document": res["document"], "href": res["href"],
            "breaches": len(rows), "checks": len(checks), "checks_in_breach": sum(1 for c in checks if c["breaches"]),
            "high": sum(1 for r in rows if r["severity"] == "high"),
            "ead_sar_mn": round(sum(r["ead_sar_mn"] for r in rows if r["entity_type"] != "book"), 4),
            "ecl_sar_mn": round(sum(r["ecl_sar_mn"] for r in rows if r["entity_type"] != "book"), 4),
            "shortfall_sar_mn": round(sum(r["shortfall_sar_mn"] for r in rows), 4),
            "by_article": sorted(arts.values(), key=lambda a: [int(x) for x in a["article"].split("Art. ")[1].split(".")]),
            "check_rows": checks, "top": rows[:limit], "not_checked": res["not_checked"],
            "ask": "Which exposures breach the CBUAE CRM standards?"}


def _dims(raw: str) -> dict[str, str] | None:
    """The level drill filter, sent as JSON ({"region": "Riyadh", ...})."""
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except ValueError as exc:
        raise rd.ReadRefused("dims must be a JSON object of level filters.") from exc
    if not isinstance(value, dict):
        raise rd.ReadRefused("dims must be a JSON object of level filters.")
    return {str(k): str(v) for k, v in value.items()}


@app.get(DRILL + "/levels")
async def drill_levels(domain: str = Query("corporate")) -> dict[str, Any]:
    from backend.ews_domain import levels
    return levels.levels_meta(domain)


@app.get(DRILL + "/levels/view")
async def drill_levels_view(domain: str = Query("corporate"), level: str = Query(""), period: str = Query(""),
                            dims: str = Query("")) -> dict[str, Any]:
    from backend.ews_domain import levels
    return levels.view(domain, level or levels.DEFAULT_LEVEL.get(domain, ""), period, _dims(dims))


@app.get(DRILL + "/customers")
async def drill_customers(domain: str = Query("corporate"), period: str = Query(""),
                          segment: str = Query(""), classification: str = Query(""),
                          subsegment: str = Query(""), cohort: str = Query("warned"),
                          reason: str = Query(""), layer: str = Query(""), dpd: str = Query(""),
                          stage: int = Query(0), band_min: str = Query(""), search: str = Query(""),
                          limit: int = Query(25, ge=1, le=500),
                          offset: int = Query(0, ge=0), dims: str = Query("")) -> dict[str, Any]:
    return drill.customers(domain, period, segment, classification, subsegment, cohort, reason,
                           layer, dpd, stage or None, band_min, search, limit, offset, dims=_dims(dims))


@app.get(DRILL + "/customers/{customer_id}")
async def drill_customer(customer_id: str, domain: str = Query("corporate"),
                         period: str = Query("")) -> dict[str, Any]:
    try:
        return drill.customer(domain, customer_id, period)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail={"error_code": "EWS_CUSTOMER_NOT_FOUND",
                                                     "message": str(exc)}) from exc


@app.get(DRILL + "/segment-analysis")
async def drill_segment_analysis(domain: str = Query("corporate"), period: str = Query(""),
                                 segment: str = Query(""), classification: str = Query(""),
                                 subsegment: str = Query(""), dims: str = Query(""),
                                 limit: int = Query(10, ge=1, le=50)) -> dict[str, Any]:
    """R16 m (M2): the analysis of a card's warned population (drivers, rules fired, top names, ECL and stage
    effect, actions), deterministic, from the same release the drill reads."""
    from backend.ews_domain import segment_analysis
    return segment_analysis.analyse(domain, period, segment, classification, subsegment, _dims(dims), limit)


@app.post(DRILL + "/export")
async def drill_export(body: dict[str, Any]) -> dict[str, Any]:
    return drill.export(body, _store)


@app.get(DRILL + "/cohorts/{object_id}")
async def drill_cohort(object_id: str) -> dict[str, Any]:
    with _store() as c:
        row = c.execute("SELECT body FROM cohort WHERE object_id = ?", (object_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail={"error_code": "EWS_COHORT_NOT_FOUND",
                                                     "message": f"{object_id} is not a saved cohort."})
    obj = json.loads(row[0])
    obj.pop("exposure_ids", None)
    return obj


# ---------------------------------------------------------------- v5/next (INBOX Item 3, phase A)

@app.get(DRILL + "/export.xlsx")
async def drill_export_xlsx(domain: str = Query("corporate"), period: str = Query(""),
                            segment: str = Query(""), classification: str = Query(""),
                            subsegment: str = Query(""), cohort: str = Query("all"),
                            reason: str = Query(""), layer: str = Query(""), dpd: str = Query(""),
                            stage: int = Query(0), band_min: str = Query(""), search: str = Query(""),
                            customer_id: str = Query(""), dims: str = Query(""),
                            request: Request = None) -> Response:
    """The rows on screen, as a house-style workbook: Customers, Exposures, Rules fired, About."""
    from backend.ews_domain import excel_export
    from backend.house_style import generated_by
    body, name = excel_export.workbook(domain, period, segment, classification, subsegment, cohort,
                                       reason, layer, dpd, stage or None, band_min, search, customer_id,
                                       generated_by=generated_by(request) if request is not None else "",
                                       dims=_dims(dims))
    return Response(body, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{name}"',
                             "Access-Control-Expose-Headers": "Content-Disposition"})


@app.get(DRILL + "/model-card")
async def drill_model_card(domain: str = Query("corporate"), period: str = Query("")) -> dict[str, Any]:
    """The rule set as a standard model card (summary, sources, layers, rules, bands, performance, log)."""
    from backend.ews_domain import model_card
    return model_card.model_card(domain, period)


# PLAN_R9 Session C: P3 (ECL of warnings), P4 (Accepted Risk Watch), P6 (ECL diagnostics) under /api/v1/ews/intel.
from backend.risk_intel.api import router as _risk_intel_router  # noqa: E402

app.include_router(_risk_intel_router)
