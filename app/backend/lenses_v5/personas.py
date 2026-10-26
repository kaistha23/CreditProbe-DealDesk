"""R16 M5: the lens planner by persona -- a request naming an audience gets that audience's dashboard.

"CRO dashboard" and "dashboard for an analyst" used to give the same corporate lens. Now a request that names a
persona first gets a **metric plan**: for every measure its definition, its formula, the SQL that will run and the
relation it reads, and, for a measure the data cannot support, "not available" with why (never an invented figure).
The user approves the plan ("Build this dashboard", with measures ticked in or out) and the lens is built from it;
the approved plan is kept inside the lens spec (`spec["plan"]`, the existing lens store; no new relation).

  cro       risk appetite and limits, ECL and cost-of-risk trend, concentration (sector, single name, top 20),
            Stage 2/3 migration, capital (RWA / CET1: not in the books), top risks
  analyst   borrower-level drill, rating migration matrix, DPD buckets, model inputs (PD, LGD, EAD distributions),
            data quality (missing and stale fields), watchlist movement
  cco       rating mix, downgrades and covenants, DSCR / leverage (behaviour score / LTV in retail), Early Warning reasons
  rm_head   by relationship manager and branch: warned names, ECL, 30+ DPD, the names to call

Deterministic (N4): the same request on the same data gives the same plan (ids, order, SQL). Every SQL is the
engine's own query for that tile or KPI (`tiles.run_tile` / `ENGINE.series`), so it runs on the relations the
engine already reads (corp, ret).
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from backend.lenses_v5 import planner
from backend.lenses_v5.catalogue import METRICS
from backend.lenses_v5.engine import ENGINE, LensError
from backend.lenses_v5.explain import metric_formula
from backend.lenses_v5.tiles import CHARTS, Ctx, run_tile

RELATION = {"corporate": "corp", "retail": "ret"}
RELATION_NOTE = {"corporate": "Lenses relation corp: one row per corporate facility-quarter (Early Warning release, with "
                              "branch, RM and rating) joined to corp_borrower_quarter (DSCR, leverage)",
                 "retail": "Lenses relation ret: one row per retail account-month (Early Warning release, with behaviour and branch)"}


@dataclass
class PM:
    """One measure of a persona plan. `tile` maps a book to the tile spec (None: not available on that book, `na` says why)."""
    id: str
    label: str
    definition: str
    formula: str
    tile: dict[str, dict[str, Any] | None] = field(default_factory=dict)
    na: dict[str, str] = field(default_factory=dict)


@dataclass
class Persona:
    key: str
    label: str
    short: str
    words: tuple[str, ...]
    purpose: str
    kpis: dict[str, list[str]]
    measures: list[PM]


def _both(t: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {"corporate": t, "retail": t}


CAPITAL_NA = ("not available: the lens relations carry no RWA or CET1 column. What-If's capital view is an illustrative IRB "
              "estimate on an assumed 15% CET1, not the bank's capital, so it is not shown as a CRO figure.")

PERSONAS: dict[str, Persona] = {p.key: p for p in [
    Persona("cro", "Chief Risk Officer (CRO)", "CRO",
            ("cro", "chief risk officer", "risk committee", "board risk", "brc"),
            "appetite and limits, loss and cost of risk, concentration, staging, capital and top risks",
            {"corporate": ["ead", "ecl", "coverage", "cost_of_risk", "stage3_share", "severe_ead_share"],
             "retail": ["ead", "ecl", "coverage", "cost_of_risk", "stage3_share", "severe_ead_share"]},
            [PM("appetite_utilisation", "Risk appetite: utilisation of limits",
                "Each risk-appetite row the books can measure (sector, rating bucket, single name, top 20, HHI, Stage 2 share), "
                "its value now against its appetite, trigger and limit (risk_appetite.json v1, read-only).",
                "Utilisation = value now ÷ limit × 100; past trigger when value ≥ trigger, past limit when value ≥ limit.",
                {"corporate": {"type": "appetite", "chart": "bullet"}, "retail": None},
                {"retail": "not available: the risk-appetite statement covers the corporate book; the retail book has no limits to measure."}),
             PM("ecl_cor_trend", "ECL and cost of risk trend",
                "The recognised ECL and the trailing-12-month cost of risk over the last eight quarters (twelve months in retail).",
                "ECL = Σ ecl_sar_mn; cost of risk = Σ last 12 months (ECL build + new write-offs) ÷ average EAD × 10,000 bps.",
                _both({"type": "trend", "metrics": ["ecl", "cost_of_risk"], "chart": "line"})),
             PM("sector_concentration", "Concentration by sector",
                "EAD by sector (retail: by product) at the as-of period, sized by share of the book.",
                "EAD(segment) = Σ ead_sar_mn where the segment matches; share = EAD(segment) ÷ EAD(book).",
                {"corporate": {"type": "breakdown", "metric": "ead", "dim": "sector", "chart": "treemap", "title": "Concentration by sector (EAD)"},
                 "retail": {"type": "breakdown", "metric": "ead", "dim": "product", "chart": "treemap", "title": "Concentration by product (EAD)"}}),
             PM("single_name_top20", "Single-name concentration: top 20",
                "The 20 largest obligors' share of EAD, with the top-20 share and the obligor HHI.",
                "Share = EAD(obligor) ÷ EAD(scope) × 100; HHI = Σ share²; top-20 share = Σ the 20 largest shares.",
                _both({"type": "concentration", "top": 20, "chart": "hbar"})),
             PM("stage_migration", "Stage 1 → 2 → 3 migration",
                "Where the EAD of each stage at the prior period sits now: the Stage 2 and Stage 3 inflows.",
                "Cell = Σ EAD now of exposures in stage a at the prior period and stage b now ÷ row total × 100.",
                _both({"type": "migration", "chart": "heatmap"})),
             PM("stage_mix", "Stage mix over time",
                "The share of EAD in Stage 1, 2 and 3 over the window.",
                "Share = EAD(stage) ÷ EAD(scope) × 100, per period.",
                _both({"type": "mix_trend", "metric": "ead", "dim": "stage", "chart": "stacked100", "title": "Stage mix (share of EAD)"})),
             PM("capital", "Capital: RWA and CET1 effect", "Risk-weighted assets and the CET1 ratio effect of the book.",
                "RWA = 12.5 × K × EAD; CET1 ratio = CET1 capital ÷ RWA.", {"corporate": None, "retail": None},
                {"corporate": CAPITAL_NA, "retail": CAPITAL_NA}),
             PM("top_risks", "Top risks: high or critical names",
                "The 20 obligors with the largest EAD in a high or critical Early Warning band, with stage, rating, ECL and coverage.",
                "Rank by Σ ead_sar_mn where ews_band ∈ {high, critical}, per obligor.",
                _both({"type": "top_names", "metric": "high_critical_ead", "top": 20, "title": "Top risks: high or critical names"}))]),
    Persona("analyst", "Credit risk analyst", "Analyst",
            ("analyst", "analysts", "risk analyst", "credit analyst", "analyst view", "portfolio analyst"),
            "borrower-level drill, rating migration, delinquency buckets, model inputs, data quality and watchlist movement",
            {"corporate": ["obligors", "exposures", "pd", "lgd", "dpd30_share", "watchlist"],
             "retail": ["obligors", "exposures", "pd", "lgd", "dpd30_share", "missed_payments"]},
            [PM("borrower_drill", "Borrower-level drill (top 50 by ECL)",
                "The 50 obligors with the largest ECL, each with stage, Early Warning band, rating, EAD, ECL and coverage; a row opens Borrower 360.",
                "Per obligor: Σ ecl_sar_mn, Σ ead_sar_mn, coverage = ECL ÷ EAD × 100.",
                _both({"type": "top_names", "metric": "ecl", "top": 50, "title": "Borrower drill: top 50 by ECL"})),
             PM("rating_migration", "Rating migration matrix",
                "Obligors by rating at the prior period against now (retail: accounts by behaviour score band).",
                "Cell = count of obligors rated a at the prior period and b now ÷ row total × 100.",
                _both({"type": "rating_migration", "chart": "heatmap"})),
             PM("dpd_buckets", "Days-past-due buckets",
                "EAD and obligors by days past due: current, 1-29, 30-59, 60-89, 90-179 and 180+.",
                "EAD(bucket) = Σ ead_sar_mn where dpd_days falls in the bucket.",
                _both({"type": "distribution", "column": "dpd_days", "chart": "bar", "title": "Days-past-due buckets (EAD)"})),
             PM("pd_distribution", "Model input: PD distribution",
                "EAD by 12-month point-in-time PD band.",
                "EAD(band) = Σ ead_sar_mn where pd_pit_12m × 100 falls in the band.",
                _both({"type": "distribution", "column": "pd_pit_12m", "chart": "bar"})),
             PM("lgd_distribution", "Model input: LGD distribution",
                "EAD by LGD band.", "EAD(band) = Σ ead_sar_mn where lgd_pct falls in the band.",
                _both({"type": "distribution", "column": "lgd_pct", "chart": "bar"})),
             PM("ead_distribution", "Model input: EAD distribution",
                "Facilities (retail: accounts) by size of EAD.", "EAD(band) = Σ ead_sar_mn where the exposure's EAD falls in the band.",
                _both({"type": "distribution", "column": "ead_sar_mn", "chart": "bar"})),
             PM("data_quality", "Data quality: missing and stale fields",
                "For each model input: values missing at the as-of period, and values stale (unchanged on each of the last four periods).",
                "Missing % = (rows − non-null rows) ÷ rows × 100; stale = exposures present in all four periods with one distinct value.",
                _both({"type": "data_quality", "chart": "table"})),
             PM("watchlist_movement", "Watchlist movement",
                "Obligors on the watchlist at the prior period, added, removed and on it now (retail has no watchlist flag: the "
                "Early Warning watch, band moderate or worse, is used).",
                "Added = on now and not at the prior period; removed = on at the prior period and not now.",
                _both({"type": "watchlist_movement", "chart": "bar"}))]),
    Persona("cco", "Chief Credit Officer (CCO)", "CCO",
            ("cco", "chief credit officer", "credit committee", "head of credit"),
            "rating mix, downgrades and covenants, repayment capacity and Early Warning reasons",
            {"corporate": ["ead", "pd", "dscr", "downgraded", "covenant_breaches", "warned"],
             "retail": ["ead", "pd", "behaviour_score", "dpd90_share", "missed_payments", "warned"]},
            [PM("rating_mix", "EAD by rating", "EAD by current rating in the global order (retail: behaviour score band).",
                "EAD(grade) = Σ ead_sar_mn where the grade matches.",
                {"corporate": {"type": "breakdown", "metric": "ead", "dim": "rating_current", "chart": "bar"},
                 "retail": {"type": "breakdown", "metric": "ead", "dim": "score_band", "chart": "bar"}}),
             PM("downgrades_trend", "Downgrades and covenant breaches",
                "Obligors downgraded each quarter and covenant breaches (retail: accounts with a missed payment and 90+ DPD share).",
                "Downgraded = count of obligors with rating_notches_moved > 0; breaches = Σ covenant_breaches.",
                {"corporate": {"type": "trend", "metrics": ["downgraded", "covenant_breaches"], "chart": "bar"},
                 "retail": {"type": "trend", "metrics": ["missed_payments", "dpd90_share"], "chart": "bar"}}),
             PM("capacity_distribution", "Repayment capacity",
                "EAD by DSCR band (retail: by behaviour score band).", "EAD(band) = Σ ead_sar_mn where the value falls in the band.",
                {"corporate": {"type": "distribution", "column": "dscr_x", "chart": "hbar"},
                 "retail": {"type": "distribution", "column": "behaviour_score", "chart": "hbar"}}),
             PM("leverage_distribution", "Leverage (retail: LTV)", "EAD by debt / EBITDA band (retail: by collateral LTV).",
                "EAD(band) = Σ ead_sar_mn where the value falls in the band.",
                {"corporate": {"type": "distribution", "column": "leverage_x", "chart": "hbar"},
                 "retail": {"type": "distribution", "column": "collateral_ltv_pct", "chart": "hbar"}}),
             PM("ews_reasons", "Early Warning reasons", "The reasons behind warned obligors, by count and EAD.",
                "Obligors(reason) = count of distinct warned obligors whose reasons include it.",
                _both({"type": "reasons", "chart": "hbar"})),
             PM("stage2_by_segment", "Stage 2 share by segment", "Stage 2 share of EAD by sector (retail: product).",
                "Stage 2 share = Σ EAD where stage = 2 ÷ Σ EAD × 100.",
                {"corporate": {"type": "breakdown", "metric": "stage2_share", "dim": "sector", "chart": "hbar"},
                 "retail": {"type": "breakdown", "metric": "stage2_share", "dim": "product", "chart": "hbar"}})]),
    Persona("rm_head", "Branch or RM head", "RM head",
            ("branch head", "branch manager", "head of branch", "rm head", "head of rms", "rm dashboard", "rm view", "for an rm",
             "for my rms", "team leader", "regional head"),
            "warned names, ECL and delinquency by relationship manager and branch, and the names to call",
            {"corporate": ["ead", "ecl", "warned", "high_critical", "dpd30_share", "obligors"],
             "retail": ["ead", "ecl", "warned", "high_critical", "dpd30_share", "obligors"]},
            [PM("warned_by_rm", "Warned obligors by RM", "Warned obligors (Early Warning moderate or worse) by relationship manager (retail: by branch).",
                "Count of distinct obligors with ews_band ∈ {moderate, high, critical}.",
                {"corporate": {"type": "breakdown", "metric": "warned", "dim": "rm_name", "chart": "hbar"},
                 "retail": {"type": "breakdown", "metric": "warned", "dim": "branch_name", "chart": "hbar"}}),
             PM("ecl_by_branch", "ECL by branch", "ECL by branch at the as-of period.", "ECL(branch) = Σ ecl_sar_mn.",
                _both({"type": "breakdown", "metric": "ecl", "dim": "branch_name", "chart": "hbar"})),
             PM("dpd30_by_branch", "30+ DPD share by branch", "The share of EAD 30 or more days past due, by branch.",
                "30+ DPD share = Σ EAD where dpd_days ≥ 30 ÷ Σ EAD × 100.",
                _both({"type": "breakdown", "metric": "dpd30_share", "dim": "branch_name", "chart": "bar"})),
             PM("warned_trend", "Warned obligors trend", "Warned and high-or-critical obligors over the window.",
                "Counts of distinct obligors by Early Warning band, per period.",
                _both({"type": "trend", "metrics": ["warned", "high_critical"], "chart": "line"})),
             PM("names_to_call", "Names to call", "The 20 warned obligors with the largest EAD.",
                "Rank by Σ ead_sar_mn where ews_band ∈ {moderate, high, critical}.",
                _both({"type": "top_names", "metric": "warned_ead", "top": 20, "title": "Names to call (warned, by EAD)"}))]),
]}

#: The order a request is read in: the more specific words first ("risk analyst" is the analyst, not the CRO).
ORDER = ("analyst", "rm_head", "cco", "cro")


def detect(text: str) -> str:
    """The persona a request names, or ''."""
    t = " " + (text or "").lower() + " "
    for key in ORDER:
        if any(planner._has(t, w) for w in PERSONAS[key].words):
            return key
    return ""


def personas_public() -> list[dict[str, Any]]:
    return [{"key": p.key, "label": p.label, "short": p.short, "purpose": p.purpose} for p in PERSONAS.values()]


def _tile_id(mid: str) -> str:
    return f"p-{mid.replace('_', '-')}"


def _kpi_row(key: str, book: str, filters: list[dict[str, Any]], period: str) -> dict[str, Any]:
    m = METRICS[key]
    _rows, sql = ENGINE.series(book, filters, [period], [key])
    return {"id": f"kpi:{key}", "kind": "kpi", "label": m.label, "definition": m.description or m.label,
            "formula": metric_formula(key), "sql": sql, "relation": RELATION[book], "sources": list(ENGINE.sources.get(book, [])[:2]),
            "tile_type": "kpi", "chart": "kpi", "available": True, "reason": "", "include": True, "metric": key}


def plan(text: str, book: str = "", persona: str = "", filters: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    """The metric plan for the persona the request names (or `persona`), on the book the request names (or `book`).
    None when no persona is named."""
    key = persona if persona in PERSONAS else detect(text)
    if not key:
        return None
    P = PERSONAS[key]
    if filters is not None and book in ("corporate", "retail"):
        b = book          # an existing lens keeps its book and scope
    else:
        b = planner.detect_book(text, default=book if book in ("corporate", "retail") else "corporate")
    flt = planner.detect_filters(text, b) if filters is None else [f for f in filters if f.get("values")]
    label = planner.scope_label(b, flt)
    period = ENGINE.as_of(b)
    spec0 = {"book": b, "filters": flt, "period": period, "scope_label": label, "kpis": [], "tiles": [], "custom_metrics": []}
    ctx = Ctx(spec0, period)
    rows: list[dict[str, Any]] = []
    for k in P.kpis[b]:
        if k in METRICS and b in METRICS[k].books:
            rows.append(_kpi_row(k, b, flt, period))
    for m in P.measures:
        t = m.tile.get(b)
        row = {"id": m.id, "kind": "tile", "label": m.label, "definition": m.definition, "formula": m.formula, "sql": "",
               "relation": RELATION[b], "sources": list(ENGINE.sources.get(b, [])[:2]), "tile_type": (t or {}).get("type", ""),
               "chart": (t or {}).get("chart", ""), "available": False, "reason": m.na.get(b, ""), "include": False}
        if t is not None:
            tile = {"id": _tile_id(m.id), **copy.deepcopy(t)}
            if not planner.normalise({**spec0, "tiles": [tile]})["tiles"]:
                row["reason"] = f"not available: the {b} book cannot run a {t['type'].replace('_', ' ')} tile."
            else:
                try:
                    out = run_tile(tile, ctx)
                    sql = (out.get("trace") or {}).get("sql") or ""
                    has_rows = bool((out.get("table") or {}).get("rows"))
                    rel = (out.get("trace") or {}).get("relations") or [RELATION[b]]
                    row.update({"sql": sql, "relation": rel[0], "chart": out.get("chart") or row["chart"], "available": has_rows,
                                "include": has_rows, "reason": "" if has_rows else "not available: the query returns no rows in this scope.",
                                "tile": tile})
                except LensError as e:
                    row["reason"] = f"not available: {e}"
        if not row["available"] and not row["reason"].startswith("not available"):
            row["reason"] = "not available: " + (row["reason"] or "no data")
        rows.append(row)
    avail = [r for r in rows if r["kind"] == "tile" and r["available"]]
    gaps = [r for r in rows if not r["available"]]
    book_word = "corporate" if b == "corporate" else "retail"
    where = "" if label.endswith(" book") else f" ({label})"
    art = "an" if P.short.startswith(("A", "E", "I", "O", "U", "RM")) else "a"
    words = [f"This plan builds {art} {P.short} dashboard on the {book_word} book{where}, as of {period}.",
             f"{len(avail)} charts or tables and {sum(r['kind'] == 'kpi' for r in rows)} key figures: {P.purpose}.",
             (f"{len(gaps)} measure{'s' if len(gaps) > 1 else ''} the data cannot support {'are' if len(gaps) > 1 else 'is'} marked not available."
              if gaps else "Every measure runs on the books, with its formula and query."),
             "Untick what you do not need, then build."]
    return {"persona": key, "persona_label": P.label, "short": P.short, "book": b, "filters": flt, "scope_label": label, "period": period,
            "title": f"{P.short} dashboard · {label}", "request": text, "plain_words": words, "relation_note": RELATION_NOTE[b],
            "metrics": rows}


def spec_from_plan(p: dict[str, Any], include: list[str] | None = None) -> dict[str, Any]:
    """The lens spec the approved plan builds: the KPI strip and the tiles of the included, available measures, in plan order.
    The plan itself (definitions, formulas, SQL, what was left out and why) is kept in the spec."""
    want = set(include) if include is not None else {r["id"] for r in p["metrics"] if r["include"]}
    chosen = [r for r in p["metrics"] if r["available"] and r["id"] in want]
    if not any(r["kind"] == "tile" for r in chosen):
        raise LensError("Pick at least one chart or table to build the dashboard.")
    kept = [{k: v for k, v in r.items() if k != "tile"} | {"include": r in chosen} for r in p["metrics"]]
    spec = {"book": p["book"], "filters": p["filters"], "period": p["period"], "scope_label": p["scope_label"], "title": p["title"],
            "kpis": [r["metric"] for r in chosen if r["kind"] == "kpi"], "tiles": [copy.deepcopy(r["tile"]) for r in chosen if r["kind"] == "tile"],
            "compare": None, "custom_metrics": [], "request": p.get("request", ""),
            "plan": {"persona": p["persona"], "persona_label": p["persona_label"], "period": p["period"], "metrics": kept,
                     "plain_words": p["plain_words"], "relation_note": p["relation_note"]}}
    return planner.normalise(spec)


def apply_to(spec: dict[str, Any], persona: str, include: list[str] | None = None) -> tuple[dict[str, Any], str]:
    """An existing lens re-planned for a persona (the assistant's "make this a CRO dashboard"): same book and scope."""
    if persona not in PERSONAS:
        raise LensError(f"'{persona}' is not a persona I can plan for.")
    p = plan(spec.get("request") or "", spec["book"], persona=persona, filters=spec.get("filters") or [])
    assert p is not None
    new = spec_from_plan(p, include)
    new["title"] = spec.get("title") or new["title"]
    new["request"] = spec.get("request", "")
    return new, f"Rebuilt for the {PERSONAS[persona].label} from the approved metric plan"


def tile_ids(spec_or_plan: dict[str, Any]) -> list[str]:
    """Measure ids of a plan's included tiles (the test compares personas on these)."""
    if "metrics" in spec_or_plan:
        return [r["id"] for r in spec_or_plan["metrics"] if r["kind"] == "tile" and r["include"]]
    return [t["id"] for t in spec_or_plan.get("tiles") or []]


def chart_kinds(spec: dict[str, Any]) -> set[str]:
    return {t.get("chart") or CHARTS[t["type"]][0] for t in spec.get("tiles") or []}


def mentions(text: str) -> bool:
    return bool(detect(text))

