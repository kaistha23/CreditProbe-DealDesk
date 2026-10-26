"""Forward risk for a proposed deal (PLAN_R11 Session F, F2 and F3).

For each structure in the Optimise output (asked, recommended, the alternatives):

  * P(Stage 2 or worse next quarter) and P(30+ DPD next quarter) from the transition models
    (`transition_model`), scored on the feature row the deal would have on the book;
  * a 4-quarter path of Stage 1/2/3 probabilities: a quarterly Markov chain whose Stage 1 row is the
    model (Stage 3 from the engine's 12-month PD), whose Stage 2 row is the book's observed cure rate
    and the pd_migration default rate `sicr_notches` below the rating, and Stage 3 absorbing;
  * Day-1 ECL, expected ECL next quarter and in 4 quarters, each the sum over stages of the stage
    probability times the stage ECL from the engine's own PD, LGD and EAD (Stage 1: the 12-month EL;
    Stage 2: the remaining lifetime EL; Stage 3: EAD x LGD);
  * the top 5 drivers (tree contributions in log-odds, plain-language labels);
  * the ECL-optimal structure and the lever that cuts P(Stage 2) most per bp of RAROC given up;
  * the Early Warning rules and score (backend/ews_domain, read-only) on the obligor after the deal.

Pure Python, numpy and pandas; reads the books and the exported models read-only.
"""
from __future__ import annotations

import functools
import math
from typing import Any

import numpy as np

from backend.dealdesk import engine, params, paths
from backend.dealdesk import transition_model as tm
from backend.v5common.ratings import rank

QUARTERS = 4
STRUCTURE_ROLES = ("asked", "recommended", "alternative")
ROLE_ORDER = {r: i for i, r in enumerate(STRUCTURE_ROLES)}
LEVERS = (
    ("cash_margin", "Cash margin +20 pts", lambda t: {**t, "cash_margin_pct": min(100.0, float(t.get("cash_margin_pct") or 0) + 20.0)}),
    ("amount", "Amount -25%", lambda t: {**t, "amount": round(float(t["amount"]) * 0.75, 4)}),
    ("tenor", "Tenor -1 year", lambda t: {**t, "tenor_years": max(1, int(t["tenor_years"]) - 1),
                                          "grace_years": min(int(t.get("grace_years") or 0), max(0, int(t["tenor_years"]) - 2))}),
    ("utilisation", "Utilisation -20 pts", lambda t: {**t, "utilisation_pct": max(0.0, float(t.get("utilisation_pct") or 0) - 20.0)}),
    ("covenants", "Enhanced covenants", lambda t: {**t, "covenant_package": "enhanced"}),
)


# ------------------------------------------------------------------ the obligor in the books (read-only)

@functools.lru_cache(maxsize=1)
def _ews_recent():
    import pandas as pd
    from backend.ews_domain import paths as ews_paths
    path = ews_paths.DATASETS / ews_paths.EWS_CORP / "ews_corp_exposure.parquet"
    e = pd.read_parquet(path)
    qs = sorted(e["reporting_quarter"].unique())
    return e[e["reporting_quarter"].isin(qs[-4:])].copy(), qs[-1]


@functools.lru_cache(maxsize=1)
def _borrowers_now():
    import pandas as pd
    b = pd.read_parquet(paths.book_relation("corp_borrower_quarter"))
    last = sorted(b["reporting_quarter"].unique())[-1]
    return b[b["reporting_quarter"] == last].set_index("borrower_id")


def book_obligor(obligor_id: str | None) -> dict[str, Any] | None:
    """The obligor's facilities and signals at the as-of quarter, or None when it is new to the bank."""
    if not obligor_id:
        return None
    e, last = _ews_recent()
    mine = e[e["borrower_id"] == obligor_id]
    now = mine[mine["reporting_quarter"] == last]
    if now.empty:
        return None
    b = _borrowers_now()
    br = b.loc[obligor_id].to_dict() if obligor_id in b.index else {}
    worst = now.sort_values("ews_score", ascending=False).iloc[0]
    reasons = sorted({r.strip() for s in now["ews_reasons"].fillna("") for r in str(s).split(";") if r.strip()})
    return {
        "quarter": last, "facilities": int(len(now)),
        "limit": float(now["limit_sar_mn"].sum()), "drawn": float(now["drawn_sar_mn"].sum()), "ead": float(now["ead_sar_mn"].sum()),
        "dpd_now": float(now["dpd_days"].max()), "dpd_max_4q": float(mine["dpd_days"].max()), "stage_max": float(now["stage"].max()),
        "sicr": float(now["sicr_flag"].max()), "default": float(now["default_flag"].max()), "watchlist": float(now["watchlist_flag"].max()),
        "rating_notches_moved": float(now["rating_notches_moved"].min()), "covenant_breaches": float(now["covenant_breaches"].max()),
        "external_dpd_days": float(now["external_dpd_days"].max()), "enquiries_q": float(now["enquiries_q"].max()),
        "inflow_trend_pct": float(now["inflow_trend_pct"].min()), "balance_buffer_months": float(now["balance_buffer_months"].min()),
        "returned_payments_q": float(now["returned_payments_q"].max()),
        "ews_score": int(worst["ews_score"]), "ews_band": str(worst["ews_band"]), "ews_reasons": reasons,
        "ews_ruleset": str(worst["ews_ruleset_version"]),
        "ratios": {k: (None if br.get(k) is None or (isinstance(br.get(k), float) and math.isnan(br[k])) else float(br[k]))
                   for k in ("leverage_x", "dscr_x", "interest_cover_x", "current_ratio_x", "ebitda_margin_pct")},
        "rating": br.get("rating_current"),
    }


# ------------------------------------------------------------------ the feature row of a deal

def _fin(p: dict[str, Any]) -> dict[str, Any]:
    return engine.latest_actual(p)


def _sector_now(sector: str) -> dict[str, float]:
    m = tm.meta()
    for r in m["sector_as_of"]:
        if r["sector"] == sector:
            return {k: float(r[k]) for k in ("sec_s2_share", "sec_dpd30_share", "sec_s2_flow", "sec_dpd30_flow") if r.get(k) is not None}
    return dict(m["book_as_of"])


def features(p: dict[str, Any], a: dict[str, Any], book: dict[str, Any] | None) -> tuple[dict[str, float], dict[str, str]]:
    """(feature row, basis of each feature) for the deal as it would stand on the book after booking."""
    m = tm.meta()
    enc = m["encodings"]
    ob = p["obligor"]
    t = a["terms"]
    rating = ob["internal_rating"]
    met = a["metrics"]
    ead = float(met["ead_y1"]) or 1e-9
    cover = (float(a["lgd"]["collateral_recognised_sar_mn"]) + float(a["lgd"]["cash_margin_sar_mn"])) / ead * 100.0
    fin = _fin(p)
    nan = float("nan")
    row: dict[str, float] = {
        "grade_rank": float(rank(rating)), "log_pd_ttc": math.log(max(1e-5, _master_pd(rating))),
        "sector_code": float(enc["sector"].get(ob["sector"], nan)), "region_code": float(enc["region"].get(ob.get("region", ""), nan)),
        "product_code": float(enc["product"].get(tm.PRODUCT_OF_FACILITY.get(t["facility_type"], ""), nan)),
        "funded": tm.FUNDED_OF_FACILITY.get(t["facility_type"], 1.0),
        "log_limit": math.log1p(float(met["amount_sar_mn"])), "utilisation_pct": float(t.get("utilisation_pct") or 0.0),
        "collateral_cover_pct": float(min(cover, 1000.0)),
        # the obligor's ratios before the deal, on the book's scale (D15): post-deal leverage and DSCR act through the
        # engine's limits and the Early Warning covenant test, as everywhere else in Deal Desk
        "leverage_x": float(fin["total_debt"]) / float(fin["ebitda"]) if fin.get("ebitda") else nan,
        "dscr_x": float(fin["ebitda"]) / float(fin["debt_service"]) if fin.get("debt_service") else nan,
        "ebitda_margin_pct": float(fin["ebitda"]) / float(fin["revenue"]) * 100.0 if fin.get("revenue") else nan,
        **_sector_now(ob["sector"]),
    }
    basis = {"grade_rank": f"internal rating {rating}", "log_pd_ttc": f"master-scale TTC PD of {rating}",
             "utilisation_pct": "structure: utilisation", "collateral_cover_pct": "structure: recognised collateral + cash margin / EAD (engine)",
             "log_limit": "structure: amount", "leverage_x": f"debt / EBITDA before the deal, audited {fin.get('year')}",
             "dscr_x": f"EBITDA / debt service before the deal, audited {fin.get('year')}",
             "ebitda_margin_pct": f"latest audited year {fin.get('year')}", "sec_s2_share": f"sector book {m['as_of']}"}
    if book is not None:
        row.update({"obl_dpd_max_4q": book["dpd_max_4q"], "obl_stage_max": book["stage_max"], "watchlist_flag": book["watchlist"],
                    "rating_notches_moved": book["rating_notches_moved"], "external_dpd_days": book["external_dpd_days"],
                    "enquiries_q": book["enquiries_q"], "inflow_trend_pct": book["inflow_trend_pct"],
                    "balance_buffer_months": book["balance_buffer_months"], "returned_payments_q": book["returned_payments_q"]})
        for k in ("leverage_x", "dscr_x", "ebitda_margin_pct"):
            if book["ratios"].get(k) is not None:
                row[k] = book["ratios"][k]
                basis[k] = f"book {ob.get('obligor_id')} {book['quarter']} (before the deal)"
        basis["obligor"] = f"book {ob.get('obligor_id')} {book['quarter']}: {book['facilities']} facilities, EWS signals"
    else:
        neu = m["neutral"]
        ext = {"clear": 0.0, "watch": 0.0, "adverse": 90.0}.get(str(ob.get("simah_flag", "")).lower(), neu["external_dpd_days"])
        row.update({"obl_dpd_max_4q": 0.0, "obl_stage_max": 1.0, "watchlist_flag": 0.0, "rating_notches_moved": 0.0,
                    "external_dpd_days": ext, "enquiries_q": neu["enquiries_q"], "inflow_trend_pct": neu["inflow_trend_pct"],
                    "balance_buffer_months": neu["balance_buffer_months"], "returned_payments_q": neu["returned_payments_q"]})
        basis["obligor"] = (f"new to bank: no DPD history, Stage 1; bureau past-due from the SIMAH flag '{ob.get('simah_flag')}'; "
                            f"enquiries and open-banking signals at the book's {m['neutral_basis']}")
    for k in ("ebitda_margin_pct", "leverage_x", "dscr_x"):
        if row.get(k) is None or row[k] != row[k]:
            row[k] = m["neutral"][k]
            basis[k] = m["neutral_basis"]
    return row, basis


def _master_pd(rating: str) -> float:
    for r in params.rows("pd_master_scale"):
        if r["rating"] == rating:
            return float(r["pd_ttc"])
    raise KeyError(rating)


# ------------------------------------------------------------------ chain and ECL

def _q(annual: float) -> float:
    return 1.0 - (1.0 - min(max(annual, 0.0), 0.9999)) ** 0.25


def chain_matrix(p_s2: float, pd_12m: float, rating: str) -> tuple[np.ndarray, dict[str, Any]]:
    """Quarterly 3-state matrix (rows from, columns to: Stage 1, 2, 3)."""
    from backend.dealdesk import pd_model
    m = tm.meta()["chain"]
    k = int(params.table("pd_migration").get("sicr_notches", 3))
    grades = pd_model.GRADES
    r2 = grades[min(len(grades) - 1, grades.index(rating) + k)] if rating in grades else rating
    s1_s3 = _q(pd_12m)
    s1_s2 = max(0.0, p_s2 - s1_s3)
    pd2 = float(pd_model.matrix_hazards(r2, 1)[0]) if r2 in grades else 0.25
    s2_s3 = _q(pd2)
    s2_s1 = float(m["s2_to_s1"])
    P = np.array([[1 - s1_s2 - s1_s3, s1_s2, s1_s3], [s2_s1, 1 - s2_s1 - s2_s3, s2_s3], [0.0, 0.0, 1.0]])
    basis = {"s1_to_s2": "transition model P(Stage 2+) less the Stage 3 share", "s1_to_s3": "engine 12-month PD, quarterly",
             "s2_to_s1": f"book cure rate {s2_s1:.4f} ({m['basis']})",
             "s2_to_s3": f"pd_migration 1-year PD at {r2} ({k} notches below {rating}, the SICR threshold), quarterly",
             "s3": "absorbing (no cure assumed within 4 quarters)"}
    return P, basis


def stage_path(P: np.ndarray, quarters: int = QUARTERS) -> list[dict[str, float]]:
    v = np.array([1.0, 0.0, 0.0])
    out = [{"quarter": 0, "s1": 1.0, "s2": 0.0, "s3": 0.0}]
    for q in range(1, quarters + 1):
        v = v @ P
        out.append({"quarter": q, "s1": float(v[0]), "s2": float(v[1]), "s3": float(v[2])})
    return out


def stage_ecl(a: dict[str, Any], year_index: int) -> dict[str, float]:
    """Stage ECLs at the start of a year of the facility's life, from the engine's own EL, EAD and LGD (SAR m)."""
    el = np.asarray(a["_arrays"]["el"], dtype=float)
    ead = np.asarray(a["_arrays"]["ead"], dtype=float)
    lgd = np.asarray(a["lgd"]["by_year"], dtype=float)
    y = int(year_index)
    if y >= len(el):
        return {"s1": 0.0, "s2": 0.0, "s3": 0.0}
    return {"s1": float(el[y]), "s2": float(el[y:].sum()), "s3": float(ead[y] * lgd[y])}


def expected_ecl(path_point: dict[str, float], ecl: dict[str, float]) -> float:
    return float(path_point["s1"] * ecl["s1"] + path_point["s2"] * ecl["s2"] + path_point["s3"] * ecl["s3"])


# ------------------------------------------------------------------ one structure

def _drivers(contrib: np.ndarray, row: dict[str, float], top: int = 5) -> list[dict[str, Any]]:
    c = contrib[:-1]
    order = np.argsort(-np.abs(c))
    out = []
    for j in order[:top]:
        if abs(c[j]) < 1e-6:
            continue
        name = tm.FEATURE_NAMES[j]
        v = row.get(name)
        out.append({"feature": name, "label": tm.LABELS[name], "value": None if v is None or v != v else _shown(name, v),
                    "contribution": float(c[j]), "direction": "raises" if c[j] > 0 else "lowers",
                    "structure_term": name in tm.STRUCTURE_FEATURES})
    return out


def _shown(name: str, v: float) -> Any:
    enc = tm.meta()["encodings"]
    inv = {"sector_code": "sector", "region_code": "region", "product_code": "product"}
    if name in inv:
        return next((k for k, i in enc[inv[name]].items() if i == int(v)), None)
    if name == "log_limit":
        return round(math.expm1(v), 3)
    if name == "log_pd_ttc":
        return round(math.exp(v), 6)
    if name == "grade_rank":
        from backend.v5common.ratings import RATING_ORDER
        return RATING_ORDER[int(v)] if 0 <= int(v) < len(RATING_ORDER) else v
    return round(float(v), 4)


def score_structure(p: dict[str, Any], terms: dict[str, Any] | None, book: dict[str, Any] | None, kw: dict[str, Any],
                    drivers: bool = True) -> dict[str, Any]:
    a = engine.analyse(p, terms, **kw)
    row, basis = features(p, a, book)
    s2 = tm.score("stage2", [row], with_contributions=drivers)
    d30 = tm.score("dpd30", [row])
    p_s2_model = float(s2["p"][0])
    p_30 = float(d30["p"][0])
    # IFRS 9's 30-days-past-due backstop: a facility 30+ DPD is Stage 2, so P(Stage 2+) is at least P(30+)
    p_s2 = max(p_s2_model, p_30)
    rating = a["pd"]["rating_used"] if a.get("pd") else p["obligor"]["internal_rating"]
    P, chain_basis = chain_matrix(p_s2, float(a["metrics"]["pd_12m"]), rating)
    path = stage_path(P)
    e0, e1 = stage_ecl(a, 0), stage_ecl(a, 1)
    by_q = [{"quarter": pt["quarter"], "expected_ecl": expected_ecl(pt, e0 if pt["quarter"] < 4 else e1),
             "stage_ecl": e0 if pt["quarter"] < 4 else e1} for pt in path]
    met = a["metrics"]
    return {
        "terms": a["terms"], "analysis": a,
        "metrics": {"lifetime_raroc": met["lifetime_raroc"], "sva": met["sva"], "clears_hurdle": met["clears_hurdle"], "hurdle": met["hurdle"],
                    "pd_12m": met["pd_12m"], "lgd_y1": met["lgd_y1"], "ead_y1": met["ead_y1"], "day_one_ecl": met["day_one_ecl"],
                    "amount_sar_mn": met["amount_sar_mn"]},
        "p_stage2_next_q": p_s2, "p_stage2_model": p_s2_model, "p_dpd30_next_q": p_30,
        "backstop_applied": p_30 > p_s2_model,
        "stage_path": path, "chain": {"matrix": P.tolist(), "basis": chain_basis},
        "ecl": {"day1": by_q[0]["expected_ecl"], "next_q": by_q[1]["expected_ecl"], "q4": by_q[4]["expected_ecl"],
                "by_quarter": by_q, "engine_day_one_ecl": met["day_one_ecl"]},
        "drivers": _drivers(s2["contributions"][0], row) if drivers else [],
        "features": {k: (None if v != v else v) for k, v in row.items()}, "feature_basis": basis,
    }


def structure_risk(p: dict[str, Any], terms: dict[str, Any] | None = None, el_view: str = "economic",
                   capital_basis: str | None = None) -> dict[str, Any]:
    """For other R11 sessions (pipeline limits, stress, review): one structure's P(Stage 2), P(30+), stage path and
    expected ECL, without drivers, levers or early warning. Pure; reads the books and the models read-only."""
    book = book_obligor(p["obligor"].get("obligor_id")) if p["obligor"].get("existing") else None
    r = score_structure(p, terms, book, {"el_view": el_view, "capital_basis": capital_basis}, drivers=False)
    return {k: r[k] for k in ("p_stage2_next_q", "p_dpd30_next_q", "stage_path", "ecl")} | {"model": tm.meta()["version"]}


# ------------------------------------------------------------------ early warning on the post-deal obligor

def _py(sql: str) -> str:
    import re
    s = re.sub(r"\bAND\b", " and ", sql)
    s = re.sub(r"\bOR\b", " or ", s)
    s = re.sub(r"\bIN\b", " in ", s)
    s = re.sub(r"(?<![<>!=])=(?!=)", "==", s)
    return s


def ews_post_deal(p: dict[str, Any], a: dict[str, Any], book: dict[str, Any] | None) -> dict[str, Any]:
    from backend.ews_domain import ews_rules as er
    ob = p["obligor"]
    t = a["terms"]
    met = a["metrics"]
    amt = float(met["amount_sar_mn"])
    util_deal = float(t.get("utilisation_pct") or 0.0) / 100.0
    new_drawn = amt * util_deal
    breaches = []
    for c in p.get("security", {}).get("covenants", []):
        thr = float(c["threshold"])
        if c["type"] == "DSCR" and np.isfinite(met["dscr_post"]) and met["dscr_post"] < thr:
            breaches.append({"covenant": "DSCR", "threshold": thr, "post_deal": met["dscr_post"]})
        if c["type"] in ("Net debt / EBITDA", "Debt / EBITDA") and np.isfinite(met["debt_ebitda_post"]) and met["debt_ebitda_post"] > thr:
            breaches.append({"covenant": c["type"], "threshold": thr, "post_deal": met["debt_ebitda_post"]})
    if book is not None:
        lim, drawn = book["limit"] + amt, book["drawn"] + new_drawn
        row = {"watchlist_flag": book["watchlist"], "rating_notches_moved": book["rating_notches_moved"],
               "covenant_breaches": max(book["covenant_breaches"], float(len(breaches))), "dpd_days": book["dpd_now"],
               "sicr_flag": book["sicr"], "utilisation_pct": drawn / lim * 100.0 if lim > 0 else 0.0, "stage": book["stage_max"],
               "default_flag": book["default"], "external_dpd_days": book["external_dpd_days"], "enquiries_q": book["enquiries_q"],
               "inflow_trend_pct": book["inflow_trend_pct"], "balance_buffer_months": book["balance_buffer_months"],
               "returned_payments_q": book["returned_payments_q"]}
        src = f"book {ob.get('obligor_id')} {book['quarter']} with the deal added"
    else:
        ext = {"clear": 0.0, "watch": 0.0, "adverse": 90.0}.get(str(ob.get("simah_flag", "")).lower())
        row = {"watchlist_flag": 0.0, "rating_notches_moved": 0.0, "covenant_breaches": float(len(breaches)), "dpd_days": 0.0,
               "sicr_flag": 0.0, "utilisation_pct": util_deal * 100.0, "stage": 1.0, "default_flag": 0.0, "external_dpd_days": ext}
        src = "new to bank: the deal alone; bureau from the SIMAH flag; open-banking signals not available"
    fired, not_evaluable, checked = [], [], []
    for r in er.RULES["corporate"]:
        cols = er._columns(r["sql"])
        if not cols <= {k for k, v in row.items() if v is not None}:
            not_evaluable.append({"id": r["id"], "label": r["label"], "missing": sorted(cols - set(row))})
            continue
        hit = bool(eval(_py(r["sql"]), {"__builtins__": {}}, dict(row)))  # noqa: S307 - the repository's own rule text
        rec = {"id": r["id"], "label": r["label"], "weight": int(r["weight"]), "rule": r["sql"],
               "values": {c: row[c] for c in sorted(cols)}}
        checked.append({**rec, "fired": hit})
        if hit:
            fired.append(rec)
    score = sum(r["weight"] for r in fired)
    band = er.band_of("corporate", score)
    eb = tm.meta()["ews_book"]
    counts = np.asarray(eb["scores"], dtype=float)
    share_le = float(counts[: min(len(counts), score + 1)].sum() / counts.sum()) if counts.sum() else None
    return {"ruleset": er.RULESET_VERSION, "score": int(score), "band": band, "fired": fired, "checked": checked,
            "not_evaluable": not_evaluable, "covenant_breaches_post_deal": breaches, "basis": src,
            "book": {"as_of": tm.meta()["as_of"], "borrowers": eb["borrowers"], "share_at_or_below": share_le,
                     "band_share": eb["band_share"], "median_score": eb["score_percentiles"]["50"]},
            "current": None if book is None else {"quarter": book["quarter"], "score": book["ews_score"], "band": book["ews_band"],
                                                   "reasons": book["ews_reasons"], "ruleset": book["ews_ruleset"]}}


# ------------------------------------------------------------------ the request

def default_structures(p: dict[str, Any], kw: dict[str, Any]) -> list[dict[str, Any]]:
    """The Optimise structures in the order the screen shows them, when the caller sends none."""
    from backend.dealdesk import optimizer
    opt = optimizer.optimize(p, el_view=kw.get("el_view", "economic"), capital_basis=kw.get("capital_basis"))
    out = []
    for s, role, label in ([(opt.get("closest"), "recommended", "Closest to the ask"), (opt.get("max_sva"), "alternative", "Maximum value")]
                           + [(x, "alternative", x.get("label", "Alternative")) for x in (opt.get("alternatives") or [])]):
        if s:
            out.append({"label": label, "role": role, "terms": s["terms"]})
    return out


def _role(s: dict[str, Any]) -> str:
    """The structure's role, from `role` or, as Session U sends it, from `key` (ask, recommended, alternative_n)."""
    if s.get("role") in STRUCTURE_ROLES:
        return s["role"]
    k = str(s.get("key") or "").lower()
    return "asked" if k in ("ask", "asked") else "recommended" if k == "recommended" else "alternative"


def _sig(t: dict[str, Any]) -> str:
    def norm(v: Any) -> str:
        if isinstance(v, bool) or v is None:
            return str(v)
        if isinstance(v, (int, float)):
            return f"{float(v):.6f}"
        if isinstance(v, (list, tuple)):
            return "[" + ",".join(norm(x) for x in v) + "]"
        return str(v)
    return repr(sorted((k, norm(v)) for k, v in t.items()))


def forward_risk(p: dict[str, Any], structures: list[dict[str, Any]] | None = None, el_view: str = "economic",
                 capital_basis: str | None = None, levers: bool = True) -> dict[str, Any]:
    kw = {"el_view": el_view, "capital_basis": capital_basis}
    book = book_obligor(p["obligor"].get("obligor_id")) if p["obligor"].get("existing") else None
    asked_terms = engine.merge_terms(p, None)
    req = list(structures or []) or default_structures(p, kw)
    items, seen = [], set()
    for s in [{"label": "As asked", "role": "asked", "key": "ask", "terms": asked_terms}] + req:
        terms = engine.merge_terms(p, s.get("terms"))
        sig = _sig(terms)
        role = _role(s)
        if sig in seen:
            # the same terms under another role (e.g. the recommendation is the ask): keep one row, note both roles
            for it in items:
                if it["_sig"] == sig and role != it["role"]:
                    it.setdefault("also", []).append(s.get("label") or role)
                    if role == "recommended":
                        it["is_recommended"] = True
            continue
        seen.add(sig)
        r = score_structure(p, terms, book, kw)
        r.update({"label": s.get("label") or role.capitalize(), "role": role, "_sig": sig,
                  "key": str(s.get("key") or (role if role != "alternative" else f"alternative_{len(items)}"))})
        # flat aliases for the thread layer
        r.update({"ecl_day1": r["ecl"]["day1"], "ecl_next_q": r["ecl"]["next_q"], "ecl_4q": r["ecl"]["q4"]})
        items.append(r)
    for i in items:
        i["is_recommended"] = bool(i.get("is_recommended")) or i["role"] == "recommended"
    rec = (next((i for i in items if i["role"] == "recommended"), None) or next((i for i in items if i["is_recommended"]), None)
           or next((i for i in items if i["role"] == "asked"), items[0]))
    asked = next(i for i in items if i["role"] == "asked")
    # ECL-optimal: the lowest expected 4-quarter ECL among the structures that clear the hurdle
    clearing = [i for i in items if i["metrics"]["clears_hurdle"]]
    opt = min(clearing, key=lambda i: (i["ecl"]["q4"], -i["metrics"]["sva"])) if clearing else None
    lever = best_lever(p, rec, book, kw) if levers else None
    m = tm.meta()
    book_rates = {"p_stage2_next_q": m["models"]["stage2"]["book_mean_predicted_as_of"],
                  "p_dpd30_next_q": m["models"]["dpd30"]["book_mean_predicted_as_of"],
                  "observed_stage2": m["models"]["stage2"]["book_rate_last_observed"],
                  "observed_dpd30": m["models"]["dpd30"]["book_rate_last_observed"],
                  "observed_quarter": m["models"]["stage2"]["book_rate_last_quarter"],
                  "basis": (f"model mean over the Stage 1 (under 30 DPD) facilities of the book at {m['as_of']}; observed: the "
                            f"{m['models']['stage2']['book_rate_last_quarter']} to next-quarter transition rate")}
    ews = ews_post_deal(p, rec["analysis"], book)
    ews["rules_fired"] = [{**f, "value": ", ".join(f"{k} {_num(v)}" for k, v in f["values"].items())} for f in ews["fired"]]
    if ews["book"]["share_at_or_below"] is not None:
        ews["vs_book"] = (f"{ews['book']['share_at_or_below'] * 100:.0f}% of the book's {ews['book']['borrowers']:,} borrowers "
                          f"score at or below this at {ews['book']['as_of']}")
    if lever and lever.get("best"):
        lever["label"] = lever["best"]["label"]
    for i in items:
        i.pop("analysis", None)
        i.pop("_sig", None)
        i["ecl_optimal"] = opt is not None and i is opt
    items.sort(key=lambda i: ROLE_ORDER[i["role"]])
    out = {
        "proposal_id": p["proposal_id"], "as_of": m["as_of"], "obligor": {"name": p["obligor"]["name"], "existing": bool(book),
                                                                         "rating": p["obligor"]["internal_rating"], "sector": p["obligor"]["sector"]},
        "answer": answer_line(rec, book_rates, ews),
        "headline": {"label": rec["label"], "role": rec["role"], "is_recommended": rec["is_recommended"], "p_stage2_next_q": rec["p_stage2_next_q"],
                     "p_dpd30_next_q": rec["p_dpd30_next_q"], "ecl_day1": rec["ecl"]["day1"], "ecl_q4": rec["ecl"]["q4"],
                     "ews_band": ews["band"], "ews_score": ews["score"]},
        "book": book_rates, "structures": items,
        "ecl_optimal": None if opt is None else {"label": opt["label"], "role": opt["role"], "ecl_q4": opt["ecl"]["q4"],
                                                 "lifetime_raroc": opt["metrics"]["lifetime_raroc"],
                                                 "reason": "lowest expected ECL in 4 quarters among the structures that clear the hurdle"},
        "best_lever": lever, "ews": ews, "asked_label": asked["label"],
        "model": {"version": m["version"], "trained": m["trained"], "as_of": m["as_of"], "card": "/api/v1/dealdesk/forward-risk/model-card"},
        "validation": validate(items),
        "method": ("Transition models: gradient-boosted trees on the corporate facility-quarter book, isotonic calibration, scored by a "
                   "numpy evaluator. Stage path: quarterly 3-state chain (Stage 1 row from the model and the engine PD; Stage 2 row from "
                   "the book cure rate and pd_migration). Expected ECL = sum of stage probability x stage ECL from the engine's PD, LGD "
                   "and EAD (Stage 1 12-month EL, Stage 2 remaining lifetime EL, Stage 3 EAD x LGD)."),
    }
    return out


def _num(v: Any) -> str:
    if v is None:
        return "n/a"
    f = float(v)
    return f"{f:,.0f}" if f == int(f) else f"{f:,.2f}"


def answer_line(rec: dict[str, Any], book: dict[str, Any], ews: dict[str, Any]) -> str:
    who = ("Recommended structure" if rec["role"] == "recommended" else "Recommended structure (the ask)" if rec.get("is_recommended")
           else "As asked (no structure clears the hurdle)" if not rec["metrics"]["clears_hurdle"] else "As asked")
    return (f"{who}: {rec['p_stage2_next_q'] * 100:.1f}% chance of Stage 2 next quarter (book {book['p_stage2_next_q'] * 100:.1f}%), "
            f"{rec['p_dpd30_next_q'] * 100:.1f}% of 30+ DPD; EWS band {ews['band'].capitalize() if ews['band'] != 'none' else 'None'}.")


def best_lever(p: dict[str, Any], base: dict[str, Any], book: dict[str, Any] | None, kw: dict[str, Any]) -> dict[str, Any] | None:
    """One lever at a time on the reference structure: the largest fall in P(Stage 2) per bp of RAROC given up."""
    rows = []
    for key, label, f in LEVERS:
        if key == "utilisation" and base["terms"].get("facility_type") == "term_loan":
            continue  # a term loan is drawn in full: utilisation is not a lever
        t2 = f(dict(base["terms"]))
        if _sig(t2) == _sig(base["terms"]):
            continue
        try:
            r = score_structure(p, t2, book, kw, drivers=False)
        except engine.TermsError:
            continue
        d_s2 = r["p_stage2_next_q"] - base["p_stage2_next_q"]
        d_bps = (r["metrics"]["lifetime_raroc"] - base["metrics"]["lifetime_raroc"]) * 1e4
        cost = max(0.0, -d_bps)
        rows.append({"lever": key, "label": label, "d_stage2": d_s2, "d_raroc_bps": d_bps, "d_ecl_q4": r["ecl"]["q4"] - base["ecl"]["q4"],
                     "stage2_cut_per_bp": (-d_s2 / cost) if cost > 1e-9 and d_s2 < 0 else None,
                     "free": d_s2 < 0 and d_bps >= 0, "clears_hurdle": r["metrics"]["clears_hurdle"]})
    cuts = [r for r in rows if r["d_stage2"] < -1e-6]
    if not cuts:
        return {"reference": base["label"], "best": None, "levers": rows,
                "note": "No single lever lowers P(Stage 2) on this structure."}
    free = [r for r in cuts if r["free"]]
    best = min(free, key=lambda r: r["d_stage2"]) if free else max(cuts, key=lambda r: r["stage2_cut_per_bp"] or 0.0)
    return {"reference": base["label"], "best": best, "levers": rows}


def validate(items: list[dict[str, Any]]) -> dict[str, Any]:
    probs_ok = all(0.0 <= i[k] <= 1.0 for i in items for k in ("p_stage2_next_q", "p_dpd30_next_q"))
    paths_ok = all(abs(pt["s1"] + pt["s2"] + pt["s3"] - 1.0) < 1e-9 and min(pt["s1"], pt["s2"], pt["s3"]) >= -1e-12
                   for i in items for pt in i["stage_path"])
    day1_ok = all(abs(i["ecl"]["day1"] - i["ecl"]["engine_day_one_ecl"]) < 1e-9 for i in items)
    return {"probabilities_in_unit_interval": probs_ok, "stage_paths_sum_to_one": paths_ok, "day1_ecl_equals_engine": day1_ok}
