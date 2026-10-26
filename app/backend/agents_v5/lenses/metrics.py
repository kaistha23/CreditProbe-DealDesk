"""Monitored metrics: one definition shape, one series function, one decomposition (read-only on the lens engine).

A monitored metric (`MDef`) is either an existing catalogue metric over a scope, or one of a few portfolio measures
that an existing lens tile already shows (a segment's share of EAD = the breakdown tile; top-20 share and sector HHI =
the concentration tile; 30+ DPD still in Stage 1 and 90+ DPD not in Stage 3 = the regulatory tile's CBUAE CRM
checks; the largest obligor against the single-name limit = the top-names tile). Every value is a DuckDB query on
the lens engine's relations (backend.lenses_v5.engine.ENGINE), with its SQL kept as evidence.

Every metric is written as row-additive parts where it can be: value = SUM(num) / SUM(den) x scale (den empty for a
sum). That makes the change between two periods decompose exactly by any dimension or by borrower:
    r1 - r0 = sum_i (dN_i - r0 * dD_i) / D1     (ratios and EAD-weighted averages)
    r1 - r0 = sum_i dN_i                         (sums)
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from typing import Any

from backend.lenses_v5.catalogue import DIMS, METRICS
from backend.lenses_v5.engine import ENGINE, TABLE, _q

ANN = {"corporate": 4, "retail": 12}
STEP = {"corporate": 1, "retail": 3}          # the back-test grid is quarterly for both books (retail: every 3rd month)


@dataclass
class MDef:
    key: str                                   # stable id within a set (hash of the definition)
    label: str
    unit: str
    book: str
    kind: str                                  # catalogue | share | max_share | top20 | hhi | crm_check | single_name
    metric: str = ""                           # catalogue key (kind catalogue) or the base metric of a share
    filters: list[dict[str, Any]] = field(default_factory=list)       # the scope
    segment: dict[str, Any] | None = None       # {dim, values}: share = EAD(segment) / EAD(scope)
    better: str = "lower"
    article: str = ""                          # a regulatory reference when it has one
    source: str = "Books"

    def public(self) -> dict[str, Any]:
        return asdict(self)


def mkey(d: dict[str, Any]) -> str:
    sig = json.dumps({k: d.get(k) for k in ("book", "kind", "metric", "filters", "segment")}, sort_keys=True)
    return "m-" + hashlib.sha1(sig.encode()).hexdigest()[:10]


def mdef(**k: Any) -> MDef:
    d = MDef(key="", **k)
    d.key = mkey(asdict(d))
    return d


def from_dict(d: dict[str, Any]) -> MDef:
    return MDef(**{k: d[k] for k in MDef.__dataclass_fields__ if k in d})


# ------------------------------------------------------------------ periods
def grid(book: str, as_of: str = "", n: int = 12) -> list[str]:
    """The last n observation points up to as_of on the quarterly grid (retail: every third month back from as_of)."""
    ps = ENGINE.periods(book)
    p = as_of if as_of in ps else ps[-1]
    i = ps.index(p)
    step = STEP[book]
    out = [ps[j] for j in range(i, -1, -step)][:n]
    return list(reversed(out))


# ------------------------------------------------------------------ row-level parts
def _where(book: str, filters: list[dict[str, Any]] | None) -> str:
    return ENGINE.where(book, filters)


def parts(d: MDef) -> tuple[str, str, float] | None:
    """(num, den, scale) as row-level SQL expressions, or None when the metric is not row-additive."""
    if d.kind == "share":
        seg = d.segment or {}
        cond = ENGINE.where(d.book, [seg])
        return f"CASE WHEN {cond} THEN ead_sar_mn ELSE 0 END", "ead_sar_mn", 100.0
    if d.kind != "catalogue":
        return None
    m = METRICS[d.metric]

    def _sum(mm: Any) -> str | None:
        if mm.kind != "sum":
            return None
        return f"CASE WHEN {mm.cond} THEN {mm.expr} ELSE 0 END" if mm.cond else f"COALESCE({mm.expr}, 0)"
    if m.kind == "sum":
        return _sum(m), "", 1.0  # type: ignore[return-value]
    if m.kind == "wavg":
        c = f"{m.expr} IS NOT NULL" + (f" AND {m.cond}" if m.cond else "")
        return f"CASE WHEN {c} THEN {m.expr} * ead_sar_mn ELSE 0 END", f"CASE WHEN {c} THEN ead_sar_mn ELSE 0 END", m.scale
    if m.kind == "ratio":
        n, dd = _sum(METRICS[m.num]), _sum(METRICS[m.den])
        if n and dd:
            return n, dd, m.scale
    return None


# ------------------------------------------------------------------ series
def series(d: MDef, periods: list[str]) -> tuple[dict[str, float | None], str]:
    """The metric's value at each period, and the SQL that computed it."""
    T = TABLE[d.book]
    w = _where(d.book, d.filters)
    pin = ", ".join(_q(p) for p in periods)
    out: dict[str, float | None] = {p: None for p in periods}
    if d.kind == "catalogue" and METRICS[d.metric].kind in ("distinct", "cor", "scorecard", "dealdesk") or (d.kind == "catalogue" and parts(d) is None):
        if METRICS[d.metric].kind == "cor":
            # the engine computes cost of risk against the period before; on the retail quarterly grid we need the
            # quarter-on-quarter figure, so compute it from ECL and write-offs over the grid step
            return _cor(d, periods)
        rows, sql = ENGINE.series(d.book, d.filters, periods, [d.metric])
        for r in rows:
            out[r["period"]] = r.get(d.metric)
        return out, sql
    if d.kind == "crm_check":
        for p in periods:
            c = crm(d.book, p).get(d.metric)
            if c is None:
                continue
            if d.filters:   # the checks run on the whole book; keep the breaches of borrowers in scope
                ids = {r["owner_id"] for r in ENGINE.q(f"SELECT DISTINCT owner_id FROM {T} WHERE period = {_q(p)} AND {w}")}
                out[p] = float(sum(v for k, v in c["by_borrower"].items() if k in ids))
            else:
                out[p] = float(c["breaches"])
        return out, f"backend.regulatory.crm_checks.run_book('{d.book}', period, checks=({d.metric!r},)) for each period"
    if d.kind == "top20":
        sql = (f"WITH o AS (SELECT period, owner_id, SUM(ead_sar_mn) AS e FROM {T} WHERE period IN ({pin}) AND {w} GROUP BY 1, 2), "
               f"r AS (SELECT period, e, ROW_NUMBER() OVER (PARTITION BY period ORDER BY e DESC) AS rk, SUM(e) OVER (PARTITION BY period) AS tot FROM o) "
               f"SELECT period, SUM(CASE WHEN rk <= 20 THEN e END) / MAX(tot) * 100 AS v FROM r GROUP BY 1 ORDER BY 1")
    elif d.kind == "hhi":
        dim = (d.segment or {}).get("dim") or "sector"
        sql = (f"WITH s AS (SELECT period, {DIMS[dim].sql} AS k, SUM(ead_sar_mn) AS e FROM {T} WHERE period IN ({pin}) AND {w} GROUP BY 1, 2) "
               f"SELECT period, SUM(POWER(e / tot * 100, 2)) AS v FROM (SELECT period, e, SUM(e) OVER (PARTITION BY period) AS tot FROM s) GROUP BY 1 ORDER BY 1")
    elif d.kind == "max_share":
        dim = (d.segment or {}).get("dim") or "sector"
        sql = (f"WITH s AS (SELECT period, {DIMS[dim].sql} AS k, SUM(ead_sar_mn) AS e FROM {T} WHERE period IN ({pin}) AND {w} GROUP BY 1, 2) "
               f"SELECT period, MAX(e / tot * 100) AS v FROM (SELECT period, e, SUM(e) OVER (PARTITION BY period) AS tot FROM s) GROUP BY 1 ORDER BY 1")
    elif d.kind == "single_name":
        sql = (f"SELECT period, MAX(e) AS v FROM (SELECT period, owner_id, SUM(ead_sar_mn) AS e FROM {T} WHERE period IN ({pin}) AND {w} "
               f"GROUP BY 1, 2) GROUP BY 1 ORDER BY 1")
    else:
        p = parts(d)
        assert p is not None
        num, den, scale = p
        val = f"SUM({num}) / NULLIF(SUM({den}), 0) * {scale}" if den else f"SUM({num}) * {scale}"
        sql = f"SELECT period, {val} AS v FROM {T} WHERE period IN ({pin}) AND {w} GROUP BY 1 ORDER BY 1"
    for r in ENGINE.q(sql):
        out[r["period"]] = _clean(r["v"])
    return out, sql


def _cor(d: MDef, periods: list[str]) -> tuple[dict[str, float | None], str]:
    """Cost of risk at each grid point: the lens engine's trailing-12-month figure (R13 L), in bps."""
    vals, sql = ENGINE.cost_of_risk(d.book, d.filters, periods)
    out: dict[str, float | None] = {p: None for p in periods}
    for (p, _k), v in vals.items():
        out[p] = round(v["bps"], 1)
    return out, sql


def _clean(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) or math.isinf(f) else round(f, 4)


def value(d: MDef, period: str) -> tuple[float | None, str]:
    s, sql = series(d, [period])
    return s.get(period), sql


def at_stake(d: MDef, period: str) -> dict[str, float]:
    """Materiality: the EAD and ECL the metric speaks for, as shares of the book (0-1)."""
    T = TABLE[d.book]
    tot = ENGINE.q(f"SELECT SUM(ead_sar_mn) AS e, SUM(ecl_sar_mn) AS l FROM {T} WHERE period = {_q(period)}")[0]
    cond = ""
    if d.kind == "share":
        cond = ENGINE.where(d.book, [d.segment or {}])
    elif d.kind == "crm_check":
        c = crm(d.book, period).get(d.metric, {})
        return {"ead": (c.get("ead") or 0) / (tot["e"] or 1), "ecl": (c.get("ecl") or 0) / (tot["l"] or 1)}
    elif d.kind == "catalogue":
        m = METRICS[d.metric]
        base = METRICS[m.num] if m.kind == "ratio" else m
        cond = base.cond if base.kind in ("sum", "distinct") else ""
        if base.kind == "sum" and not base.cond and base.expr not in ("1",) and "ead" not in base.expr and "ecl" not in base.expr:
            cond = f"{base.expr} > 0"          # a count of events (covenant breaches): the exposures that have one
        if d.metric in ("ead", "ecl", "coverage", "cost_of_risk", "pd", "lgd", "ecl_pd20", "ecl_pd20_uplift", "obligors", "exposures"):
            cond = ""
    elif d.kind in ("top20", "max_share"):
        r = series(d, [period])[0].get(period) or 0
        return {"ead": r / 100, "ecl": r / 100}
    elif d.kind == "hhi":
        return {"ead": 1.0, "ecl": 1.0}
    elif d.kind == "single_name":
        r = series(d, [period])[0].get(period) or 0
        return {"ead": r / (tot["e"] or 1), "ecl": 0.0}
    w = " AND ".join(c for c in (_where(d.book, d.filters), cond) if c and c != "TRUE") or "TRUE"
    r = ENGINE.q(f"SELECT SUM(ead_sar_mn) AS e, SUM(ecl_sar_mn) AS l FROM {T} WHERE period = {_q(period)} AND {w}")[0]
    return {"ead": (r["e"] or 0) / (tot["e"] or 1), "ecl": (r["l"] or 0) / (tot["l"] or 1)}


# ------------------------------------------------------------------ decomposition
def decompose(d: MDef, p0: str, p1: str, by: str, top: int = 6) -> dict[str, Any]:
    """The change r(p1) - r(p0) split by a dimension (`sector`, `rating_current`, ...) or by `borrower`.

    Contributions add up to the total change exactly for row-additive metrics; for the concentration measures the
    borrower split is the change of each name's EAD inside the top 20 (or in the largest name)."""
    T = TABLE[d.book]
    w = _where(d.book, d.filters)
    key = "owner_id" if by == "borrower" else DIMS[by].sql
    label = "ANY_VALUE(owner_name)" if by == "borrower" else "MIN(k)"
    pp = f"period IN ({_q(p0)}, {_q(p1)})"
    v0, v1 = value(d, p0)[0], value(d, p1)[0]
    total = None if v0 is None or v1 is None else round(v1 - v0, 4)
    p = parts(d)
    if d.kind == "crm_check":
        return _decompose_crm(d, p0, p1, by, top, total)
    if d.kind == "catalogue" and METRICS[d.metric].kind == "cor":
        return _decompose_cor(d, p0, p1, by, key, top, total)
    if p is None:
        # sums by segment of the metric's own figure (distinct counts, concentration: EAD of names)
        if d.kind == "catalogue" and METRICS[d.metric].kind == "distinct":
            m = METRICS[d.metric]
            c = f" AND {m.cond}" if m.cond else ""
            nm = "ANY_VALUE(owner_name)" if by == "borrower" else "k"
            sql = (f"SELECT k, {nm} AS name, COUNT(DISTINCT CASE WHEN period = {_q(p1)}{c} THEN owner_id END) - "
                   f"COUNT(DISTINCT CASE WHEN period = {_q(p0)}{c} THEN owner_id END) AS c "
                   f"FROM (SELECT *, {key} AS k FROM {T} WHERE {pp} AND {w}) GROUP BY k ORDER BY ABS(c) DESC NULLS LAST LIMIT {top}")
        else:
            # concentration measures: the EAD change of the names that matter now
            sql = (f"SELECT owner_id AS k, ANY_VALUE(owner_name) AS name, SUM(CASE WHEN period = {_q(p1)} THEN ead_sar_mn ELSE 0 END) - "
                   f"SUM(CASE WHEN period = {_q(p0)} THEN ead_sar_mn ELSE 0 END) AS c FROM {T} WHERE {pp} AND {w} GROUP BY 1 "
                   f"ORDER BY ABS(c) DESC NULLS LAST LIMIT {top}") if by == "borrower" else (
                   f"SELECT {key} AS k, {key} AS name, SUM(CASE WHEN period = {_q(p1)} THEN ead_sar_mn ELSE 0 END) - "
                   f"SUM(CASE WHEN period = {_q(p0)} THEN ead_sar_mn ELSE 0 END) AS c FROM {T} WHERE {pp} AND {w} GROUP BY 1 "
                   f"ORDER BY ABS(c) DESC NULLS LAST LIMIT {top}")
        rows = ENGINE.q(sql)
        unit = "count" if d.kind == "catalogue" else "sar_mn"
        return {"by": by, "p0": p0, "p1": p1, "total": total, "unit_of_contribution": unit, "additive": False,
                "rows": [{"key": str(r["k"]), "name": str(r["name"] if r["name"] is not None else r["k"]), "contribution": _clean(r["c"])} for r in rows],
                "sql": sql}
    num, den, scale = p
    if den:
        sql = (f"WITH g AS (SELECT {key} AS k, {label.replace('MIN(k)', f'MIN({key})')} AS name, "
               f"SUM(CASE WHEN period = {_q(p1)} THEN {num} ELSE 0 END) AS n1, SUM(CASE WHEN period = {_q(p0)} THEN {num} ELSE 0 END) AS n0, "
               f"SUM(CASE WHEN period = {_q(p1)} THEN {den} ELSE 0 END) AS d1, SUM(CASE WHEN period = {_q(p0)} THEN {den} ELSE 0 END) AS d0 "
               f"FROM {T} WHERE {pp} AND {w} GROUP BY 1), t AS (SELECT SUM(n0) / NULLIF(SUM(d0), 0) AS r0, SUM(d1) AS D1 FROM g) "
               f"SELECT g.k, g.name, ((g.n1 - g.n0) - t.r0 * (g.d1 - g.d0)) / NULLIF(t.D1, 0) * {scale} AS c, "
               f"(g.n1 - g.n0) / NULLIF(t.D1, 0) * {scale} AS rate_part, -t.r0 * (g.d1 - g.d0) / NULLIF(t.D1, 0) * {scale} AS mix_part "
               f"FROM g, t ORDER BY ABS(c) DESC NULLS LAST")
    else:
        sql = (f"SELECT {key} AS k, {label.replace('MIN(k)', f'MIN({key})')} AS name, "
               f"(SUM(CASE WHEN period = {_q(p1)} THEN {num} ELSE 0 END) - SUM(CASE WHEN period = {_q(p0)} THEN {num} ELSE 0 END)) * {scale} AS c, "
               f"NULL AS rate_part, NULL AS mix_part FROM {T} WHERE {pp} AND {w} GROUP BY 1 ORDER BY ABS(c) DESC NULLS LAST")
    allrows = ENGINE.q(sql)
    explained = sum((r["c"] or 0) for r in allrows)
    rows = [{"key": str(r["k"]), "name": str(r["name"] if r["name"] is not None else r["k"]), "contribution": _clean(r["c"]),
             "numerator_part": _clean(r["rate_part"]), "denominator_part": _clean(r["mix_part"])} for r in allrows[:top]]
    return {"by": by, "p0": p0, "p1": p1, "total": total, "sum_of_parts": _clean(explained), "additive": True,
            "unit_of_contribution": d.unit, "rows": rows, "segments": len(allrows), "sql": sql + f" LIMIT {top} (shown)"}


# ------------------------------------------------------------------ CBUAE CRM checks (backend.regulatory.crm_checks)
_CRM: dict[tuple[str, str], dict[str, Any]] = {}
CRM_IDS = {"corporate": ("CRM-6.4", "CRM-7.8", "CRM-6.12", "CRM-9.23", "CRM-9.30", "CRM-10.8"),
           "retail": ("CRM-6.4", "CRM-7.8", "CRM-9.24", "CRM-10.11")}


def crm(book: str, period: str) -> dict[str, Any]:
    """The CRM checks of one book and period: breaches (facilities or accounts), EAD, ECL, shortfall, by borrower."""
    key = (book, period)
    if key not in _CRM:
        from backend.regulatory import crm_checks as C
        checks = tuple(c for c in C.CHECKS if c.id in CRM_IDS[book] and book in c.books)
        try:
            rows = C.run_book(book, period, checks=checks)
        except Exception:  # noqa: BLE001 - a period the checks cannot read counts as unknown, not as zero
            _CRM[key] = {}
            return _CRM[key]
        out: dict[str, Any] = {c.id: {"breaches": 0, "ead": 0.0, "ecl": 0.0, "shortfall": 0.0, "by_borrower": {}, "title": c.title,
                                      "article": c.article} for c in checks}
        for b in rows:
            o = out[b.check_id]
            o["breaches"] += 1
            o["ead"] += b.ead_sar_mn or 0
            o["ecl"] += b.ecl_sar_mn or 0
            o["shortfall"] += b.shortfall_sar_mn or 0
            o["by_borrower"][b.borrower_id] = o["by_borrower"].get(b.borrower_id, 0) + 1
        _CRM[key] = out
    return _CRM[key]


def _decompose_crm(d: MDef, p0: str, p1: str, by: str, top: int, total: float | None) -> dict[str, Any]:
    a = crm(d.book, p0).get(d.metric, {}).get("by_borrower", {})
    b = crm(d.book, p1).get(d.metric, {}).get("by_borrower", {})
    delta = {k: b.get(k, 0) - a.get(k, 0) for k in set(a) | set(b)}
    T = TABLE[d.book]
    ids = [k for k, v in delta.items() if v]
    names: dict[str, tuple[str, str]] = {}
    if ids:
        dim = "owner_name" if by == "borrower" else DIMS[by].sql
        q = (f"SELECT owner_id, ANY_VALUE({dim}) AS k FROM {T} WHERE period IN ({_q(p0)}, {_q(p1)}) "
             f"AND owner_id IN ({', '.join(_q(i) for i in ids[:5000])}) GROUP BY 1")
        names = {r["owner_id"]: str(r["k"]) for r in ENGINE.q(q)}  # type: ignore[misc]
    if by == "borrower":
        rows = sorted(({"key": k, "name": names.get(k, k), "contribution": float(v)} for k, v in delta.items() if v),
                      key=lambda r: -abs(r["contribution"]))
    else:
        agg: dict[str, float] = {}
        for k, v in delta.items():
            if v:
                g = names.get(k, "Not set")
                agg[g] = agg.get(g, 0) + v
        rows = sorted(({"key": g, "name": g, "contribution": float(v)} for g, v in agg.items()), key=lambda r: -abs(r["contribution"]))
    return {"by": by, "p0": p0, "p1": p1, "total": total, "sum_of_parts": float(sum(delta.values())), "additive": True,
            "unit_of_contribution": "count", "rows": rows[:top], "segments": len(rows),
            "sql": f"crm_checks.run_book('{d.book}', {p0!r} and {p1!r}, checks=({d.metric!r},)) by borrower"}


def _cor_parts(d: MDef, p: str, key: str, by: str) -> dict[str, tuple[str, float, float, float]]:
    """Each segment's part of the book's trailing-12-month cost of risk at p: (its ECL build + new write-offs over the
    window) / the book's average EAD x 10,000 (annualised when the window is shorter than a year). Parts add up to the
    book's figure, so their changes add up to the change of the book's cost of risk."""
    n = ANN[d.book]
    ps = ENGINE.periods(d.book)
    j = ps.index(p)
    lo = ps[max(0, j - n)]
    rows, _ = ENGINE.cor_flows(d.book, d.filters, lo, p, key)
    win = [q for q in ps[max(0, j - n + 1): j + 1] if q != lo]
    eads: dict[str, float] = {}
    seg: dict[str, list[float]] = {}
    for r in rows:
        eads[r["period"]] = eads.get(r["period"], 0.0) + (r["ead"] or 0.0)
        if r["period"] in win:
            s_ = seg.setdefault(str(r["k"]), [0.0, 0.0])
            s_[0] += r["build"] or 0.0
            s_[1] += r["wo"] or 0.0
    pts = [eads[q] for q in ps[max(0, j - n): j + 1] if eads.get(q)]
    if not pts or not win:
        return {}
    avg = sum(pts) / len(pts)
    names: dict[str, str] = {}
    if by == "borrower" and seg:
        T = TABLE[d.book]
        names = {str(r["k"]): str(r["n"]) for r in ENGINE.q(
            f"SELECT owner_id AS k, ANY_VALUE(owner_name) AS n FROM {T} WHERE period BETWEEN {_q(lo)} AND {_q(p)} GROUP BY 1")}
    f = 10000 * n / len(win) / avg
    return {k: (names.get(k, k), (b + w) * f, b, w) for k, (b, w) in seg.items()}


def _decompose_cor(d: MDef, p0: str, p1: str, by: str, key: str, top: int, total: float | None) -> dict[str, Any]:
    """The change of the trailing-12-month cost of risk by part: each part's share of the figure at p1 minus its share
    at p0, so the parts add up to the change of the book's cost of risk."""
    now = _cor_parts(d, p1, key, by)
    before = _cor_parts(d, p0, key, by)
    rows = []
    for k in set(now) | set(before):
        n = now.get(k, (before.get(k, (k,))[0], 0.0, 0.0, 0.0))
        b = before.get(k, (n[0], 0.0, 0.0, 0.0))
        rows.append({"key": k, "name": n[0], "contribution": _clean(n[1] - b[1]), "now_bps": _clean(n[1]), "before_bps": _clean(b[1]),
                     "ecl_build": _clean(n[2]), "write_offs": _clean(n[3])})
    rows.sort(key=lambda r: -abs(r["contribution"] or 0))
    return {"by": by, "p0": p0, "p1": p1, "total": total, "sum_of_parts": _clean(sum(r["contribution"] or 0 for r in rows)), "additive": True,
            "unit_of_contribution": "bps", "rows": rows[:top], "segments": len(rows),
            "sql": f"trailing-12-month cost of risk parts at {p1} minus at {p0} by {by} (ECL build + new write-offs over the book's average EAD)"}


def driver(d: MDef, p0: str, p1: str) -> dict[str, Any]:
    """Numerator against denominator: did the risk grow, or did the book around it shrink? (ratios and averages)"""
    p = parts(d)
    if p is None or not p[1]:
        return {"available": False}
    num, den, scale = p
    T = TABLE[d.book]
    sql = (f"SELECT SUM(CASE WHEN period = {_q(p1)} THEN {num} ELSE 0 END) AS n1, SUM(CASE WHEN period = {_q(p0)} THEN {num} ELSE 0 END) AS n0, "
           f"SUM(CASE WHEN period = {_q(p1)} THEN {den} ELSE 0 END) AS d1, SUM(CASE WHEN period = {_q(p0)} THEN {den} ELSE 0 END) AS d0 "
           f"FROM {T} WHERE period IN ({_q(p0)}, {_q(p1)}) AND {_where(d.book, d.filters)}")
    r = ENGINE.q(sql)[0]
    if not r["d1"] or not r["d0"]:
        return {"available": False}
    r0 = r["n0"] / r["d0"]
    num_part = (r["n1"] - r["n0"]) / r["d1"] * scale
    den_part = -r0 * (r["d1"] - r["d0"]) / r["d1"] * scale
    return {"available": True, "numerator_change": _clean(r["n1"] - r["n0"]), "denominator_change": _clean(r["d1"] - r["d0"]),
            "numerator_part": _clean(num_part), "denominator_part": _clean(den_part),
            "main": "numerator" if abs(num_part) >= abs(den_part) else "denominator", "sql": sql}
