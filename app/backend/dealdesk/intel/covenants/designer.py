"""Covenant designer (R14 backlog #2): covenants and thresholds calibrated so that, in the bank's own history, a breach comes
2–3 quarters before Stage 2 or default.

Data (registered relations, read-only):
  * cockpit.corp_borrower_quarter — each borrower's covenant metrics by quarter (leverage, DSCR, interest cover, current ratio,
    EBITDA): the value a covenant at any threshold would have been tested on;
  * cockpit.corp_facility_quarter — outcomes: the first quarter any facility of the borrower reached Stage 2 or 3 or defaulted;
  * cockpit.corp_covenant_quarter — the covenants the bank actually set, with their thresholds and breaches (the as-set track record).

Method (deterministic):
  1. Events: borrowers with at least `MIN_CLEAN` quarters in Stage 1 before their first Stage 2 / default quarter E.
  2. For a candidate threshold t, a quarter is "in breach" when the metric is on the wrong side of t.
     Lead time = E − the first breach quarter in the run-up window [E − 6, E − 1]; no breach in the window = missed.
  3. Hit rate (early) = share of events with lead ≥ 2 quarters; on-time = share with lead 2–3; median lead over detected events.
     False-alarm rate = share of Stage 1 borrower-quarters with no event in the next 4 quarters that are in breach.
     Precision = share of breaching Stage 1 quarters followed by an event within 4 quarters.
  4. Candidates are quantiles of the metric over Stage 1 quarters. Proposed = among candidates whose median lead is 2–3 quarters
     and whose false-alarm rate is ≤ `MAX_FALSE_ALARM`, the one maximising early hit rate − false-alarm rate (ties: more headroom
     for the deal). Recommended when its early hit rate is at least `MIN_EARLY_HIT`.
  5. The same statistics are reported for the template thresholds (the deal's covenant package, else policy CP-2.1, else the
     book's median as-set threshold) and for the bank's as-set covenants (corp_covenant_quarter.breach_flag).
Population: the deal's sector when it has at least `MIN_EVENTS` events, else the whole corporate book (stated).

R14 G (K32): client fit.
  6. Bounds: a proposed level stays inside `BOUNDS` (e.g. leverage at most 6.0x): a book quantile outside them is never proposed.
  7. Minimum headroom (parameter, default `MIN_HEADROOM_PCT` = 15% from today's value): among the candidates, only levels that
     leave the client at least that cushion are eligible; when none does, the proposed level is set at exactly the minimum
     headroom (inside the bounds) and its statistics are measured the same way. The statistical best (old rule, any headroom)
     is kept beside it, so the trade-off between early hits, false alarms and headroom is shown, not hidden.
  8. Verdict is one of Recommend / Not recommended; "beats template" is stated only for a recommended level against a template
     that itself warns on at least `MEANINGFUL_TEMPLATE_HIT` of events (beating a template that never warns says nothing).
  9. Findings: a template that fires on more than `TEMPLATE_FA_CAP` of good borrowers, or warns early on fewer than
     `MEANINGFUL_TEMPLATE_HIT` of bad ones, is reported as mis-calibrated.
"""
from __future__ import annotations

import functools
import math
from typing import Any

import numpy as np
import pandas as pd

from backend.intel.calls import reads

MIN_CLEAN = 2
WINDOW = 4
HORIZON = 4
MAX_FALSE_ALARM = 0.10
LEAD_TARGET = (2.0, 3.0)
MIN_EARLY_HIT = 0.25
MIN_EVENTS = 30
MIN_HEADROOM_PCT = 15.0
MEANINGFUL_TEMPLATE_HIT = 0.10
TEMPLATE_FA_CAP = 0.30
#: covenant -> (lowest, highest) level the designer may propose (a covenant outside these is not a usable covenant)
BOUNDS: dict[str, tuple[float, float]] = {"dscr": (1.0, 3.0), "leverage": (1.5, 6.0), "interest_cover": (1.0, 8.0),
                                          "current_ratio": (0.8, 2.5), "ebitda_floor": (50.0, 100.0)}
GRID = (0.02, 0.03, 0.05, 0.075, 0.10, 0.125, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50)

#: covenant -> metric column, direction ("min": breach when below; "max": breach when above), book type, policy template
COVENANTS: dict[str, dict[str, Any]] = {
    "dscr": {"label": "DSCR (minimum)", "column": "dscr_x", "dir": "min", "book_type": "DSCR", "policy": 1.20, "policy_ref": "CP-2.1: DSCR at least 1.20x", "unit": "x"},
    "leverage": {"label": "Debt / EBITDA (maximum)", "column": "leverage_x", "dir": "max", "book_type": "Leverage", "policy": 4.0, "policy_ref": "CP-2.1: leverage at most 4.0x", "unit": "x"},
    "interest_cover": {"label": "Interest cover (minimum)", "column": "interest_cover_x", "dir": "min", "book_type": "Interest Cover", "policy": None, "policy_ref": "", "unit": "x"},
    "current_ratio": {"label": "Current ratio (minimum)", "column": "current_ratio_x", "dir": "min", "book_type": "Current Ratio", "policy": None, "policy_ref": "", "unit": "x"},
    "ebitda_floor": {"label": "EBITDA floor (% of EBITDA a year earlier)", "column": "ebitda_pct_prior", "dir": "min", "book_type": "Minimum EBITDA", "policy": None, "policy_ref": "", "unit": "%"},
}
#: the deal's covenant package names -> designer keys
PACKAGE_NAMES = {"dscr": "dscr", "net debt / ebitda": "leverage", "debt / ebitda": "leverage", "leverage": "leverage", "debt_ebitda": "leverage",
                 "interest cover": "interest_cover", "interest_cover": "interest_cover", "current ratio": "current_ratio", "current_ratio": "current_ratio"}


@functools.lru_cache(maxsize=1)
def _panel() -> dict[str, Any]:
    """Borrower × quarter matrices of each metric, stage-1 mask, and the event quarter per borrower."""
    b = reads.read("cockpit", "corp_borrower_quarter", ["borrower_id", "reporting_quarter", "sector", "leverage_x", "dscr_x", "interest_cover_x",
                                                         "current_ratio_x", "ebitda_sar_mn"])
    f = reads.read("cockpit", "corp_facility_quarter", ["borrower_id", "reporting_quarter", "stage", "default_flag"])
    quarters = sorted(b.reporting_quarter.astype(str).unique())
    qi = {q: i for i, q in enumerate(quarters)}
    borrowers = sorted(b.borrower_id.unique())
    bi = {x: i for i, x in enumerate(borrowers)}
    nb, nq = len(borrowers), len(quarters)
    rows = b.borrower_id.map(bi).to_numpy()
    cols = b.reporting_quarter.astype(str).map(qi).to_numpy()
    mats: dict[str, np.ndarray] = {}
    for c in ("leverage_x", "dscr_x", "interest_cover_x", "current_ratio_x", "ebitda_sar_mn"):
        m = np.full((nb, nq), np.nan)
        m[rows, cols] = b[c].astype(float).to_numpy()
        mats[c] = m
    eb = mats["ebitda_sar_mn"]
    prior = np.full_like(eb, np.nan)
    prior[:, 4:] = eb[:, :-4]
    with np.errstate(divide="ignore", invalid="ignore"):
        mats["ebitda_pct_prior"] = np.where(prior > 0, eb / prior * 100.0, np.nan)
    bad = ((f.stage.astype(float) >= 2) | (f.default_flag.astype(float) > 0)).astype(int)
    g = pd.DataFrame({"b": f.borrower_id.map(bi), "q": f.reporting_quarter.astype(str).map(qi), "bad": bad}).groupby(["b", "q"]).bad.max()
    badm = np.zeros((nb, nq), dtype=bool)
    idx = g[g > 0].index
    badm[idx.get_level_values(0).to_numpy(), idx.get_level_values(1).to_numpy()] = True
    first_bad = np.where(badm.any(axis=1), badm.argmax(axis=1), -1)
    sector = b.drop_duplicates("borrower_id").set_index("borrower_id").sector.reindex(borrowers).to_numpy()
    return {"quarters": quarters, "borrowers": borrowers, "mats": mats, "bad": badm, "first_bad": first_bad, "sector": sector}


@functools.lru_cache(maxsize=1)
def _book_as_set() -> pd.DataFrame:
    """The bank's as-set covenants: breach per borrower × quarter × type, and the median threshold per type and sector."""
    c = reads.read("cockpit", "corp_covenant_quarter", ["borrower_id", "reporting_quarter", "sector", "covenant_type", "threshold_value", "breach_flag"])
    return c


def _population(sector: str | None) -> tuple[np.ndarray, str, int]:
    P = _panel()
    events_all = (P["first_bad"] >= MIN_CLEAN)
    if sector:
        m = P["sector"] == sector
        n_ev = int((events_all & m).sum())
        if n_ev >= MIN_EVENTS:
            return m, f"{sector} borrowers in the corporate book", n_ev
    return np.ones(len(P["borrowers"]), dtype=bool), "the whole corporate book" + (f" ({sector} has fewer than {MIN_EVENTS} events)" if sector else ""), int(events_all.sum())


def _breach(m: np.ndarray, t: float, direction: str) -> np.ndarray:
    with np.errstate(invalid="ignore"):
        return (m < t) if direction == "min" else (m > t)


def evaluate(breach: np.ndarray, pop: np.ndarray) -> dict[str, Any]:
    """Lead time, hit rates and false alarms of a breach matrix (borrower × quarter) on the population."""
    P = _panel()
    fb = P["first_bad"]
    nq = breach.shape[1]
    ev = np.where(pop & (fb >= MIN_CLEAN))[0]
    leads = []
    for i in ev:
        E = fb[i]
        lo = max(0, E - WINDOW)
        w = breach[i, lo:E]
        if w.any():
            leads.append(E - (lo + int(np.argmax(w))))
        else:
            leads.append(0)
    leads_a = np.array(leads) if leads else np.zeros(0)
    n_ev = len(ev)
    detected = leads_a[leads_a > 0]
    # Stage-1 borrower-quarters and whether an event follows within HORIZON quarters
    q = np.arange(nq)[None, :]
    stage1 = ~P["bad"] & pop[:, None]
    fbm = fb[:, None]
    follows = (fbm > q) & (fbm <= q + HORIZON)
    quiet = stage1 & ~follows & (q <= nq - 1 - HORIZON) & ((fbm < 0) | (fbm > q + HORIZON))
    with np.errstate(invalid="ignore"):
        fa = float(breach[quiet].mean()) if quiet.any() else np.nan
        br1 = breach & stage1 & (q <= nq - 1 - HORIZON)
        prec = float(follows[br1].mean()) if br1.any() else np.nan
    return {"events": n_ev, "detected": int(len(detected)),
            "hit_rate": float((leads_a >= 1).mean()) if n_ev else np.nan,
            "early_hit_rate": float((leads_a >= 2).mean()) if n_ev else np.nan,
            "on_time_rate": float(((leads_a >= 2) & (leads_a <= 3)).mean()) if n_ev else np.nan,
            "median_lead_q": float(np.median(detected)) if len(detected) else np.nan,
            "false_alarm_rate": fa, "precision": prec, "quiet_quarters": int(quiet.sum())}


def _deal_metrics(deal: str) -> dict[str, Any]:
    """Today's values of each metric for the deal (Deal Desk file) or a book facility / borrower (corporate book)."""
    out: dict[str, Any] = {"id": deal, "sector": None, "values": {}, "template": {}, "name": deal, "kind": None}
    if deal.startswith("CF") or deal.startswith("CB"):
        f = reads.read("cockpit", "corp_facility_quarter", ["facility_id", "borrower_id"])
        bid = deal if deal.startswith("CB") else (f.loc[f.facility_id == deal, "borrower_id"].iloc[0] if (f.facility_id == deal).any() else None)
        if bid is None:
            raise KeyError(deal)
        P = _panel()
        i = P["borrowers"].index(bid)
        q = P["quarters"][-1]
        out.update(kind="book", sector=P["sector"][i], borrower_id=bid, name=bid)
        for k, c in COVENANTS.items():
            v = P["mats"][c["column"]][i, -1]
            out["values"][k] = reads.num(v, reads.src("cockpit", "corp_borrower_quarter", {"borrower_id": bid, "reporting_quarter": q},
                                                      c["column"] if k != "ebitda_floor" else "ebitda_sar_mn", q,
                                                      "EBITDA / EBITDA four quarters earlier" if k == "ebitda_floor" else None), c["unit"])
        b = reads.read("cockpit", "corp_borrower_quarter", ["borrower_id", "borrower_name"])
        nm = b.loc[b.borrower_id == bid, "borrower_name"]
        out["name"] = nm.iloc[0] if len(nm) else bid
        return out
    try:
        from backend.dealdesk.data import deals
        p = deals.get(deal)
    except (ImportError, KeyError):
        from backend.dealdesk import proposals
        p = proposals.get(deal)
    if not p:
        raise KeyError(deal)
    ob = p.get("obligor") or {}
    out.update(kind="deal", sector=ob.get("sector"), name=ob.get("name") or deal)
    years = [y for y in (p.get("financials") or {}).get("years", []) if y.get("kind") == "actual"]
    if years:
        y = years[-1]
        S = reads.src("deal_desk", "dd_obligor_financials", {"proposal_id": deal, "year": y.get("year")}, "", y.get("year"))
        def _s(col: str, method: str | None = None) -> dict[str, Any]:
            return {**S, "column": col, **({"method": method} if method else {})}
        eb, td, ds = y.get("ebitda"), y.get("total_debt"), y.get("debt_service")
        if eb and ds:
            out["values"]["dscr"] = reads.num(eb / ds, _s("ebitda, debt_service", "EBITDA / debt service"), "x")
        if eb and td is not None:
            out["values"]["leverage"] = reads.num(td / eb, _s("total_debt, ebitda", "total debt / EBITDA"), "x")
        if y.get("current_ratio"):
            out["values"]["current_ratio"] = reads.num(y["current_ratio"], _s("current_ratio"), "x")
        if len(years) >= 2 and years[-2].get("ebitda"):
            out["values"]["ebitda_floor"] = reads.num(eb / years[-2]["ebitda"] * 100, _s("ebitda", "EBITDA / prior-year EBITDA"), "%")
    bid = ob.get("obligor_id")
    P = _panel()
    if isinstance(bid, str) and bid in P["borrowers"]:  # the obligor is in the corporate book: fill what the file lacks
        i = P["borrowers"].index(bid)
        q = P["quarters"][-1]
        for k, c in COVENANTS.items():
            if k in out["values"]:
                continue
            v = P["mats"][c["column"]][i, -1]
            if v == v:
                out["values"][k] = reads.num(v, reads.src("cockpit", "corp_borrower_quarter", {"borrower_id": bid, "reporting_quarter": q},
                                                          c["column"] if k != "ebitda_floor" else "ebitda_sar_mn", q,
                                                          "EBITDA / EBITDA four quarters earlier" if k == "ebitda_floor" else None), c["unit"])
    for c in ((p.get("security") or {}).get("covenants") or []):
        k = PACKAGE_NAMES.get(str(c.get("type", "")).lower())
        if k and c.get("threshold") is not None:
            out["template"][k] = float(c["threshold"])
    return out


def _template(key: str, deal_tpl: dict[str, float], sector: str | None) -> tuple[float | None, str]:
    c = COVENANTS[key]
    if key in deal_tpl:
        return deal_tpl[key], "the deal's covenant package"
    if c["policy"] is not None:
        return float(c["policy"]), f"policy {c['policy_ref']}"
    a = _book_as_set()
    s = a[a.covenant_type == c["book_type"]]
    if key == "ebitda_floor" or not len(s):
        return None, "no template threshold"
    if sector and (s.sector == sector).any():
        s = s[s.sector == sector]
    return float(s.threshold_value.median()), f"median as-set threshold in the book ({sector or 'all sectors'})"


def _as_set(key: str, pop_sectors: set[str] | None) -> dict[str, Any] | None:
    """How the bank's own covenants of this type performed (corp_covenant_quarter.breach_flag)."""
    c = COVENANTS[key]
    a = _book_as_set()
    s = a[a.covenant_type == c["book_type"]]
    if not len(s):
        return None
    P = _panel()
    bi = {x: i for i, x in enumerate(P["borrowers"])}
    qi = {q: i for i, q in enumerate(P["quarters"])}
    g = s.groupby(["borrower_id", "reporting_quarter"]).breach_flag.max()
    m = np.zeros(P["bad"].shape, dtype=bool)
    keep = g[g > 0].reset_index()
    r = keep.borrower_id.map(bi)
    q = keep.reporting_quarter.astype(str).map(qi)
    ok = r.notna() & q.notna()
    m[r[ok].astype(int).to_numpy(), q[ok].astype(int).to_numpy()] = True
    has = np.zeros(len(P["borrowers"]), dtype=bool)
    hb = s.borrower_id.map(bi).dropna().astype(int).unique()
    has[hb] = True
    pop = has & (np.isin(P["sector"], list(pop_sectors)) if pop_sectors else True)
    st = evaluate(m, pop)
    st["borrowers_with_covenant"] = int(pop.sum())
    st["median_threshold"] = float(s.threshold_value.median())
    return st


def _headroom(cur: float | None, t: float, direction: str) -> float | None:
    if cur is None or t == 0:
        return None
    return ((cur - t) / abs(t) * 100.0) if direction == "min" else ((t - cur) / abs(t) * 100.0)


def _at_headroom(cur: float, h: float, direction: str, unit: str) -> float:
    """The level that leaves exactly h% headroom from today's value (headroom measured on the threshold, as `_headroom`)."""
    t = cur / (1 + h / 100.0) if direction == "min" else cur / (1 - h / 100.0) if h < 100 else cur * 10
    k = 1 if unit == "%" else 100  # round away from today's value so the cushion is never below h after rounding
    return (math.floor(t * k) if direction == "min" else math.ceil(t * k)) / k


def _clip(key: str, t: float) -> float:
    lo, hi = BOUNDS[key]
    return min(hi, max(lo, t))


def design(deal: str, min_headroom_pct: float = MIN_HEADROOM_PCT) -> dict[str, Any]:
    """Proposed covenants and thresholds for a deal (Deal Desk proposal id) or a book facility/borrower (CF…/CB…)."""
    mh = float(min_headroom_pct)
    d = _deal_metrics(deal)
    pop, pop_label, n_ev = _population(d["sector"])
    P = _panel()
    pop_sectors = {d["sector"]} if pop_label.startswith(str(d["sector"])) else None
    rows: list[dict[str, Any]] = []
    for key, c in COVENANTS.items():
        m = P["mats"][c["column"]]
        stage1 = ~P["bad"] & pop[:, None]
        vals = m[stage1 & ~np.isnan(m)]
        if len(vals) < 50:
            continue
        qs = GRID if c["dir"] == "min" else tuple(1 - g for g in GRID)
        lo, hi = BOUNDS[key]
        cands = sorted({round(float(np.quantile(vals, g)), 2) for g in qs})
        out_of_bounds = [t for t in cands if not lo <= t <= hi]
        cands = sorted({t for t in cands if lo <= t <= hi} | ({_clip(key, t) for t in out_of_bounds} if out_of_bounds else set()))
        cur = (d["values"].get(key) or {}).get("value")
        def _stats(t: float) -> dict[str, Any]:
            st = evaluate(_breach(m, t, c["dir"]), pop)
            st["threshold"] = t
            st["score"] = (st["early_hit_rate"] or 0) - (st["false_alarm_rate"] or 0)
            hd = _headroom(cur, t, c["dir"])
            if hd is not None:
                st["deal_headroom_pct"] = hd
            return st
        grid = [_stats(t) for t in cands]
        def _pick(pool: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, bool]:
            feasible = [g for g in pool if g["false_alarm_rate"] == g["false_alarm_rate"] and g["false_alarm_rate"] <= MAX_FALSE_ALARM]
            on_target = [g for g in feasible if g["median_lead_q"] == g["median_lead_q"] and LEAD_TARGET[0] <= g["median_lead_q"] <= LEAD_TARGET[1]]
            if not pool:
                return None, False
            return max(on_target or feasible or pool, key=lambda g: (round(g["score"], 3), g.get("deal_headroom_pct") or 0.0)), bool(on_target)
        stat_best, stat_on = _pick(grid)
        stat_best = dict(stat_best)
        stat_best["lead_on_target"] = stat_on
        fit = [g for g in grid if cur is None or (g.get("deal_headroom_pct") is not None and g["deal_headroom_pct"] >= mh - 1e-9)]
        best, on = _pick(fit)
        set_by_headroom = False
        if best is None:  # no book level leaves the cushion: set the level at exactly the minimum headroom (inside the bounds)
            t_h = _clip(key, _at_headroom(float(cur), mh, c["dir"], c["unit"]))
            best = _stats(t_h)
            on = bool(best["median_lead_q"] == best["median_lead_q"] and LEAD_TARGET[0] <= best["median_lead_q"] <= LEAD_TARGET[1])
            set_by_headroom = True
            if t_h not in cands:
                grid.append(best)
                grid.sort(key=lambda g: g["threshold"])
        best = dict(best)
        best["lead_on_target"] = on
        best["set_by_headroom"] = set_by_headroom
        best["bounded"] = bool(best["threshold"] in (lo, hi) and out_of_bounds and best["threshold"] in {_clip(key, t) for t in out_of_bounds})
        tpl, tpl_src = _template(key, d["template"], d["sector"])
        tpl_stats = evaluate(_breach(m, tpl, c["dir"]), pop) if tpl is not None else None
        if tpl_stats is not None:
            tpl_stats["threshold"] = tpl
            if cur is not None:
                tpl_stats["deal_headroom_pct"] = ((cur - tpl) / abs(tpl) * 100.0) if c["dir"] == "min" else ((tpl - cur) / abs(tpl) * 100.0)
        trade = sorted(({"threshold": g["threshold"], "headroom_pct": g.get("deal_headroom_pct"), "early_hit_rate": g["early_hit_rate"],
                         "false_alarm_rate": g["false_alarm_rate"]} for g in grid), key=lambda x: (x["headroom_pct"] is None, x["headroom_pct"] or 0))
        rows.append({"covenant": key, "label": c["label"], "direction": c["dir"], "unit": c["unit"], "current": d["values"].get(key),
                     "proposed": best, "statistical_best": stat_best, "bounds": {"low": lo, "high": hi}, "trade_off": trade,
                     "template": tpl_stats, "template_source": tpl_src, "as_set": _as_set(key, pop_sectors), "grid": grid})
    # recommend: covenants whose proposed threshold warns early on at least a third of events within the false-alarm cap
    findings: list[dict[str, Any]] = []
    for r in rows:
        p = r["proposed"]
        cur = (r.get("current") or {}).get("value")
        r["already_breached"] = bool(p.get("deal_headroom_pct") is not None and p["deal_headroom_pct"] < 0)
        lo, hi = r["bounds"]["low"], r["bounds"]["high"]
        outside = cur is not None and not (lo <= cur <= hi) and (
            (r["direction"] == "max" and cur > hi) or (r["direction"] == "min" and cur < lo))
        thin = cur is not None and p.get("deal_headroom_pct") is not None and p["deal_headroom_pct"] < mh - 1e-6
        r["recommended"] = bool(p["false_alarm_rate"] <= MAX_FALSE_ALARM and (p["early_hit_rate"] or 0) >= MIN_EARLY_HIT and p["lead_on_target"]
                                and not r["already_breached"] and not thin and not outside)
        r["why_not"] = (None if r["recommended"] else
                        f"the client is at {_fmt(cur, r['unit'])} today, outside the usable range {_fmt(lo, r['unit'])}–{_fmt(hi, r['unit'])}: "
                        "not a usable covenant until it moves back" if outside else
                        "the client is already on the wrong side of this level today" if r["already_breached"] else
                        f"leaves only {p['deal_headroom_pct']:.0f}% headroom (minimum {mh:.0f}%)" if thin else
                        f"no threshold has a 2–3 quarter median lead within {MAX_FALSE_ALARM:.0%} false alarms" if not p["lead_on_target"] else
                        f"warns 2+ quarters early on only {p['early_hit_rate']:.0%} of events (minimum {MIN_EARLY_HIT:.0%})"
                        if (p["early_hit_rate"] or 0) < MIN_EARLY_HIT else
                        f"false alarms {p['false_alarm_rate']:.0%} above the {MAX_FALSE_ALARM:.0%} cap")
        t = r["template"]
        meaningful = bool(t is not None and t["early_hit_rate"] == t["early_hit_rate"] and t["early_hit_rate"] >= MEANINGFUL_TEMPLATE_HIT)
        r["template_meaningful"] = meaningful
        r["beats_template"] = bool(r["recommended"] and meaningful and p["score"] > (t["early_hit_rate"] or 0) - (t["false_alarm_rate"] or 0) + 1e-9)
        r["verdict"] = "Recommend" if r["recommended"] else "Not recommended"
        if t is not None and t["false_alarm_rate"] == t["false_alarm_rate"] and t["false_alarm_rate"] > TEMPLATE_FA_CAP:
            findings.append({"covenant": r["covenant"], "kind": "template_too_tight", "severity": "major",
                             "title": f"Template {r['label'].split(' (')[0]} {_fmt(t['threshold'], r['unit'])} is mis-calibrated: "
                                      f"it would fire on {t['false_alarm_rate']:.0%} of good borrowers",
                             "text": f"The bank's standard level ({r['template_source']}) is breached in {t['false_alarm_rate']:.0%} of quarters of borrowers "
                                     f"that did not go bad, so a breach says little; it warned 2+ quarters early on {t['early_hit_rate']:.0%} of bad cases."})
        elif t is not None and t["early_hit_rate"] == t["early_hit_rate"] and t["early_hit_rate"] < MEANINGFUL_TEMPLATE_HIT:
            findings.append({"covenant": r["covenant"], "kind": "template_too_loose", "severity": "minor",
                             "title": f"Template {r['label'].split(' (')[0]} {_fmt(t['threshold'], r['unit'])} almost never warns: "
                                      f"{t['early_hit_rate']:.0%} of bad cases caught early",
                             "text": f"The bank's standard level ({r['template_source']}) is too loose to warn: it caught {t['early_hit_rate']:.0%} of "
                                     "Stage 2 or default events 2+ quarters ahead."})
        r["trade_off_line"] = _trade_line(r, mh)
        r["text"] = _text(r)
    rows.sort(key=lambda r: (not r["recommended"], -(r["proposed"]["score"] or 0)))
    rec = [r for r in rows if r["recommended"]]
    best_hit = max((r["statistical_best"]["early_hit_rate"] or 0 for r in rows), default=0.0)
    coverage_note = (f"Even the best covenant level catches only {best_hit:.0%} of bad cases 2+ quarters early: covenants are a partial warning "
                     "and work alongside Early Warning, not instead of it.")
    lines = [f"{r['label']}: {_fmt(r['proposed']['threshold'], r['unit'])} — warned 2+ quarters ahead on {r['proposed']['early_hit_rate']:.0%} of "
             f"{r['proposed']['events']:,} Stage 2/default events (median lead {r['proposed']['median_lead_q']:.0f} quarters), "
             f"false alarms {r['proposed']['false_alarm_rate']:.0%}" for r in rec[:4] if r["proposed"]["median_lead_q"] == r["proposed"]["median_lead_q"]]
    summary = (f"Proposed package for {d['name']} ({len(rec)} covenant{'s' if len(rec) != 1 else ''}, each at least {mh:.0f}% from today's value), "
               f"calibrated on {pop_label}: " + "; ".join(lines) + "."
               if rec else f"No covenant warns 2–3 quarters early on at least {MIN_EARLY_HIT:.0%} of events within a {MAX_FALSE_ALARM:.0%} false-alarm rate "
                 f"and at least {mh:.0f}% headroom in {pop_label}.")
    limits = [f"History is {len(P['quarters'])} quarters ({P['quarters'][0]}–{P['quarters'][-1]}), one partial credit cycle: rates carry wide bands; "
              f"{n_ev:,} events in the population.",
              "Outcome is the first Stage 2/3 or default quarter of any of the borrower's facilities (cockpit.corp_facility_quarter); "
              "a borrower already in Stage 2 at the start of the window is not an event.",
              f"False alarms are measured only on quarters with a full {HORIZON}-quarter outcome window.",
              "Metrics are the book's quarterly ratios; a covenant tested on audited annual accounts would warn later than shown."]
    if d["kind"] == "deal" and not d["values"]:
        limits.append("The deal has no actual-year financials: headroom against the proposed thresholds is not computed.")
    return reads.clean({"deal": deal, "name": d["name"], "sector": d["sector"], "population": pop_label, "events": n_ev,
                        "method": {"window_quarters": WINDOW, "horizon_quarters": HORIZON, "max_false_alarm": MAX_FALSE_ALARM, "target_lead": "2–3 quarters",
                                   "objective": f"median lead 2–3 quarters; maximise early hit rate − false-alarm rate within the false-alarm cap, leaving the client at least {mh:.0f}% headroom from today",
                                   "min_early_hit": MIN_EARLY_HIT, "min_headroom_pct": mh},
                        "min_headroom_pct": mh, "bounds": {k: {"low": v[0], "high": v[1]} for k, v in BOUNDS.items()},
                        "summary": summary, "coverage_note": coverage_note, "findings": findings,
                        "covenants": rows, "data_limits": limits, "sources": reads.lineage()})


def _fmt(v: float, unit: str) -> str:
    return f"{v:,.0f}%" if unit == "%" else f"{v:,.2f}x"


def _trade_line(r: dict[str, Any], mh: float) -> str:
    """The trade-off in one line: the client-fit level against the statistical best (any headroom)."""
    p, b, u = r["proposed"], r["statistical_best"], r["unit"]
    def _h(x: dict[str, Any]) -> str:
        return f", {x['deal_headroom_pct']:.0f}% headroom" if x.get("deal_headroom_pct") is not None else ""
    s = (f"At {_fmt(p['threshold'], u)}{_h(p)}: early warning on {p['early_hit_rate']:.0%}, false alarms {p['false_alarm_rate']:.0%}")
    if abs(b["threshold"] - p["threshold"]) > 1e-9:
        s += (f"; the statistical best {_fmt(b['threshold'], u)}{_h(b)} would catch {b['early_hit_rate']:.0%} with "
              f"{b['false_alarm_rate']:.0%} false alarms, but " + (f"leaves less than {mh:.0f}% cushion" if b.get("deal_headroom_pct") is not None
                                                                    and b["deal_headroom_pct"] < mh else "scores no better"))
    return s + "."


def _text(r: dict[str, Any]) -> str:
    p, t = r["proposed"], r["template"]
    s = f"{r['label']} at {_fmt(p['threshold'], r['unit'])}"
    if t is not None:
        delta = ""
        if t["early_hit_rate"] == t["early_hit_rate"]:
            delta = (f"; the template {_fmt(t['threshold'], r['unit'])} ({r['template_source']}) warns 2+ quarters early on "
                     f"{t['early_hit_rate']:.0%} with {t['false_alarm_rate']:.0%} false alarms")
        s += delta
    cur = (r.get("current") or {}).get("value")
    if cur is not None and p.get("deal_headroom_pct") is not None:
        s += f"; the borrower is at {_fmt(cur, r['unit'])} today ({p['deal_headroom_pct']:+.0f}% headroom)"
    if r.get("why_not"):
        s += f"; not recommended: {r['why_not']}"
    if r["already_breached"]:
        s += "; the borrower is already on the wrong side of this threshold today"
    return s
