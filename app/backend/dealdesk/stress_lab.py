"""Stress Lab (PLAN_R11 Session S): scenario stress, reverse stress and structure resilience for one deal.

Every scenario runs through the existing engine (`engine.analyse`), never a copy of it:

  shocks      data/dealdesk/params/v1/stress_scenarios.json (macro, sector, obligor, collateral, rating,
              combined; custom specs parsed from text). The R5 table stress.json is not used or changed.
  financials  revenue, EBITDA margin, receivable days, project delay and customer loss move the latest audited
              year on a copy of the proposal (revenue, EBITDA with operating leverage, total debt and debt
              service for the working capital absorbed); the engine then computes DSCR and Debt/EBITDA.
  collateral  a change on every item goes through the engine's `collateral_shock`; a change on one type
              (real estate) revalues those items on the copy.
  rates       the engine's `rate_shock_bps` (floating pricing and the obligor's existing debt).
  rating      scenario notches + the notches the stressed financials imply (rating overlay bands), scored
              by the engine's PD model at the stressed grade; Stage from the SICR rules in the table.
  PD path     Session F's forward-risk P(Stage 2 next quarter) where `backend.dealdesk.forward_risk` is
              present, else the engine's PD only.

Reverse stress (breakevens): the smallest move in revenue, EBITDA margin, collateral value or the rate
that takes DSCR below 1.0, breaches the LTV limit, takes RAROC below the hurdle or moves the deal to
Stage 2. DSCR, LTV and the rating overlay are exact closed forms of the engine's own formulas (checked
against the engine in tests); RAROC is the engine itself (a notch ladder, or bisection on the driver).
"""
from __future__ import annotations

import copy
import functools
import json
import math
import re
from typing import Any, Callable

import numpy as np

from backend.dealdesk import constraints as cons
from backend.dealdesk import engine, params, paths, pd_model
from backend.dealdesk.seed import GRADES

FILE = paths.params_dir() / "v1" / "stress_scenarios.json"
METRIC_CELLS = ("dscr", "debt_ebitda", "ltv", "covenants", "rating", "stage", "raroc", "limits")
CELL_LABELS = {"dscr": "DSCR", "debt_ebitda": "Debt/EBITDA", "ltv": "LTV", "covenants": "Covenants", "rating": "Rating / PD",
               "stage": "Stage", "raroc": "RAROC", "limits": "Limits"}
DRIVERS = {"revenue_pct": ("Revenue", "%"), "ebitda_margin_bps": ("EBITDA margin", "bps"),
           "collateral_pct": ("Collateral value", "%"), "rate_bps": ("Benchmark rate", "bps")}
CRITERIA = {"dscr": "DSCR below 1.0", "ltv": "LTV above the limit", "raroc": "RAROC below the hurdle", "stage2": "Stage 2"}
TOL = {"revenue_pct": 1e-4, "ebitda_margin_bps": 0.1, "collateral_pct": 1e-4, "rate_bps": 0.1}


# ------------------------------------------------------------------ the scenario table

@functools.lru_cache(maxsize=1)
def table() -> dict[str, Any]:
    return json.loads(FILE.read_text())


def _by_id() -> dict[str, dict[str, Any]]:
    return {s["id"]: s for s in table()["scenarios"]}


def _tr(key: str) -> dict[str, Any]:
    return table()["transmission"][key]


def _sectoral(v: Any, sector: str) -> Any:
    if isinstance(v, dict) and ("default" in v or "by_sector" in v):
        return v.get("by_sector", {}).get(sector, v.get("default", 0))
    return v


def scenarios_catalogue() -> dict[str, Any]:
    """GET /stress/scenarios: the groups and scenarios as stored (shocks, basis, severity) plus the transmission."""
    t = table()
    return {"name": t["name"], "version": t["version"], "owner": t["owner"], "effective_from": t["effective_from"],
            "approved_by": t["approved_by"], "description": t["description"], "groups": t["groups"],
            "shock_keys": t["shock_keys"], "transmission": t["transmission"], "scenarios": t["scenarios"],
            "custom_examples": ["revenue -20% and rates +150 bps", "collateral -35% and downgrade 2 notches",
                                "oil -40%", "project delay 9 months", "EBITDA margin -200 bps and receivable days +45"]}


# ------------------------------------------------------------------ resolving a scenario for one obligor

EMPTY = {"revenue_pct": 0.0, "ebitda_margin_bps": 0.0, "receivable_days": 0.0, "rate_bps": 0.0, "collateral": {},
         "notches": 0, "guarantee_unenforceable": False}


def combine(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Compose two resolved shocks: revenue and collateral changes compound; bps, days and notches add."""
    coll = dict(a["collateral"])
    for k, v in b["collateral"].items():
        coll[k] = (1 + coll.get(k, 0.0)) * (1 + v) - 1
    return {"revenue_pct": (1 + a["revenue_pct"]) * (1 + b["revenue_pct"]) - 1,
            "ebitda_margin_bps": a["ebitda_margin_bps"] + b["ebitda_margin_bps"],
            "receivable_days": a["receivable_days"] + b["receivable_days"], "rate_bps": a["rate_bps"] + b["rate_bps"],
            "collateral": coll, "notches": int(a["notches"]) + int(b["notches"]),
            "guarantee_unenforceable": bool(a["guarantee_unenforceable"] or b["guarantee_unenforceable"])}


def resolve(spec: dict[str, Any], sector: str) -> dict[str, Any]:
    """A scenario's (or custom) shock spec as concrete numbers for an obligor in `sector`."""
    if spec.get("compose"):
        out = copy.deepcopy(EMPTY)
        byid = _by_id()
        for sid in spec["compose"]:
            if sid == "@sector":
                sid = _sectoral(spec["sector_scenario"], sector)
            out = combine(out, resolve(byid[sid], sector))
        return out
    s = spec.get("shocks", spec)
    out = copy.deepcopy(EMPTY)
    out["revenue_pct"] = float(_sectoral(s.get("revenue_pct", 0.0), sector))
    out["ebitda_margin_bps"] = float(_sectoral(s.get("ebitda_margin_bps", 0.0), sector))
    out["receivable_days"] = float(_sectoral(s.get("receivable_days", 0.0), sector))
    out["rate_bps"] = float(_sectoral(s.get("rate_bps", 0.0), sector))
    out["notches"] = int(_sectoral(s.get("notches", 0), sector))
    out["guarantee_unenforceable"] = bool(s.get("guarantee_unenforceable", False))
    c = s.get("collateral_pct")
    if isinstance(c, dict):
        out["collateral"] = {k: float(v) for k, v in c.items()}
    elif c:
        out["collateral"] = {"*": float(c)}
    if s.get("customer_loss"):
        share = float(_sectoral(_tr("largest_customer_share"), sector))
        out = combine(out, {**EMPTY, "revenue_pct": -share, "collateral": {}})
    if s.get("delay_months"):
        m = float(s["delay_months"])
        share = float(_sectoral(_tr("project_revenue_share"), sector))
        out = combine(out, {**EMPTY, "revenue_pct": -share * min(m, 12.0) / 12.0, "receivable_days": share * m * 365.0 / 12.0,
                            "collateral": {}})
    return out


def is_null(r: dict[str, Any]) -> bool:
    return (abs(r["revenue_pct"]) < 1e-12 and abs(r["ebitda_margin_bps"]) < 1e-12 and abs(r["receivable_days"]) < 1e-12
            and abs(r["rate_bps"]) < 1e-12 and not any(abs(v) > 1e-12 for v in r["collateral"].values())
            and not r["notches"] and not r["guarantee_unenforceable"])


def _m(s: str) -> str:
    """A typographic minus for display."""
    return re.sub(r"(^|[\s(])-(?=\d)", lambda m: m.group(1) + "\u2212", s)


def describe(r: dict[str, Any]) -> list[str]:
    """The resolved shocks as short readable items (for the drawer and the thread)."""
    return [_m(x) for x in _describe(r)]


def _describe(r: dict[str, Any]) -> list[str]:
    out = []
    if abs(r["revenue_pct"]) > 1e-12:
        out.append(f"Revenue {r['revenue_pct'] * 100:+.1f}%")
    if abs(r["ebitda_margin_bps"]) > 1e-12:
        out.append(f"EBITDA margin {r['ebitda_margin_bps']:+.0f} bps")
    if abs(r["receivable_days"]) > 1e-12:
        out.append(f"Receivable days {r['receivable_days']:+.0f}")
    if abs(r["rate_bps"]) > 1e-12:
        out.append(f"Benchmark rate {r['rate_bps']:+.0f} bps")
    for k, v in r["collateral"].items():
        if abs(v) > 1e-12:
            out.append(f"{'Collateral' if k == '*' else k.replace('_', ' ').capitalize() + ' collateral'} {v * 100:+.0f}%")
    if r["notches"]:
        out.append(f"Rating -{r['notches']} notch{'es' if r['notches'] > 1 else ''}")
    if r["guarantee_unenforceable"]:
        out.append("Guarantee unenforceable")
    return out


# ------------------------------------------------------------------ custom shocks from text

_NUM = r"([+\-−–]?\s*\d+(?:\.\d+)?)"
_DOWN = re.compile(r"\b(fall|falls|drop|drops|down|decline|declines|lower|cut|loses?|squeeze)\b")
_UP = re.compile(r"\b(up|rise|rises|increase|increases|higher|hike|widen|widens)\b")


def _num(s: str) -> float:
    return float(s.replace("−", "-").replace("–", "-").replace(" ", ""))


_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
          "eleven": 11, "twelve": 12, "eighteen": 18, "a single": 1, "a": 1}


def _words_to_digits(t: str) -> str:
    """'two notches', 'a six-month delay' -> '2 notches', 'a 6-month delay' (only before a notch or month word)."""
    keys = sorted(_WORDS, key=len, reverse=True)
    pat = r"\b(" + "|".join(re.escape(k) for k in keys) + r")(?=[\s-]*(?:notch|notches|month|months)\b)"
    return re.sub(pat, lambda m: str(_WORDS[m.group(1)]), t)


def parse_custom(text: str) -> dict[str, Any]:
    """'revenue -20% and rates +150 bps' -> {"shocks": {...}, "parsed": [...], "unparsed": [...]}.

    A stress move without a sign is taken in its adverse direction (revenue, margin and collateral down,
    rates and receivable days up, notches down)."""
    low = _words_to_digits(text.lower().replace("−", "-").replace("–", "-"))
    parts = [x.strip() for x in re.split(r"\band\b|,|;|\+(?=\s*[a-z])|&|\bwith\b|\bplus\b", low) if x.strip()]
    sh: dict[str, Any] = {}
    parsed, unparsed = [], []
    byid = _by_id()

    def signed(v: float, part: str, adverse: int) -> float:
        """An explicit sign wins; else a word (falls, up); else the adverse direction."""
        if re.search(r"[+\-]\s*\d", part):
            return v
        if _DOWN.search(part):
            return -abs(v)
        if _UP.search(part):
            return abs(v)
        return abs(v) * adverse

    for part in parts:
        hit = False
        m = re.search(r"(oil|brent)[^\d+\-]*" + _NUM + r"\s*%", part)
        if m:
            k = abs(_num(m.group(2))) / 30.0
            sh.setdefault("_scale", []).append(("oil_30", k))
            parsed.append(f"Oil -{abs(_num(m.group(2))):g}% (oil -30% transmission x {k:.2f})")
            hit = True
        m = re.search(r"\bgdp[^\d+\-]*" + _NUM + r"\s*%", part)
        if m and not hit:
            k = abs(_num(m.group(1))) / 3.0
            sh.setdefault("_scale", []).append(("gdp_3", k))
            parsed.append(f"GDP -{abs(_num(m.group(1))):g}% (GDP -3% betas x {k:.2f})")
            hit = True
        m = re.search(r"(margin)[^\d+\-]*" + _NUM + r"\s*(bps|bp|basis points|%|pts|points)", part)
        if m and not hit:
            v = _num(m.group(2)) * (100.0 if m.group(3) in ("%", "pts", "points") else 1.0)
            v = signed(v, part, -1)
            sh["ebitda_margin_bps"] = sh.get("ebitda_margin_bps", 0.0) + v
            parsed.append(f"EBITDA margin {v:+.0f} bps")
            hit = True
        m = re.search(r"(revenue|revenues|sales|turnover|top line)[^\d+\-]*" + _NUM + r"\s*%", part)
        if m and not hit:
            v = signed(_num(m.group(2)) / 100.0, part, -1)
            sh["revenue_pct"] = (1 + sh.get("revenue_pct", 0.0)) * (1 + v) - 1
            parsed.append(f"Revenue {v * 100:+.0f}%")
            hit = True
        m = re.search(r"(rate|rates|saibor|eibor|sofr|benchmark|interest|profit rate)[^\d+\-]*" + _NUM + r"\s*(bps|bp|basis points|%)", part)
        if m and not hit:
            v = _num(m.group(2)) * (100.0 if m.group(3) == "%" else 1.0)
            v = signed(v, part, 1)
            sh["rate_bps"] = sh.get("rate_bps", 0.0) + v
            parsed.append(f"Benchmark rate {v:+.0f} bps")
            hit = True
        m = re.search(r"(real estate|property|land)[^\d+\-]*" + _NUM + r"\s*%", part)
        if m and not hit:
            v = signed(_num(m.group(2)) / 100.0, part, -1)
            sh.setdefault("collateral_pct", {})
            if not isinstance(sh["collateral_pct"], dict):
                sh["collateral_pct"] = {"*": sh["collateral_pct"]}
            sh["collateral_pct"]["real_estate"] = v
            parsed.append(f"Real estate collateral {v * 100:+.0f}%")
            hit = True
        m = re.search(r"(collateral|security|asset values?)[^\d+\-]*" + _NUM + r"\s*%", part)
        if m and not hit:
            v = signed(_num(m.group(2)) / 100.0, part, -1)
            c = sh.get("collateral_pct", {})
            c = c if isinstance(c, dict) else {"*": c}
            c["*"] = v
            sh["collateral_pct"] = c
            parsed.append(f"Collateral {v * 100:+.0f}%")
            hit = True
        m = re.search(r"(\d+)\s*notch|notch(?:es)?[^\d]*(\d+)|downgrade[^\d]*(\d+)", part)
        if m and not hit:
            n = int(next(g for g in m.groups() if g))
            sh["notches"] = sh.get("notches", 0) + abs(n)
            parsed.append(f"Rating -{abs(n)} notch{'es' if abs(n) > 1 else ''}")
            hit = True
        m = re.search(r"(receivable|debtor|dso|collection)[^\d+\-]*" + _NUM + r"\s*(days?)?", part)
        if m and not hit:
            v = abs(_num(m.group(2)))
            sh["receivable_days"] = sh.get("receivable_days", 0.0) + v
            parsed.append(f"Receivable days +{v:g}")
            hit = True
        m = re.search(r"delay[^\d]*(\d+(?:\.\d+)?)\s*-?\s*(months?|m\b)|(\d+(?:\.\d+)?)\s*-?\s*months?\b[^\d]*delay", part)
        if m and not hit:
            v = float(m.group(1) or m.group(3))
            sh["delay_months"] = sh.get("delay_months", 0.0) + v
            parsed.append(f"Project delay {v:g} months")
            hit = True
        if not hit and re.search(r"(largest|biggest|main|key|top)\s+(customer|client|buyer)", part):
            sh["customer_loss"] = True
            parsed.append("Largest customer lost")
            hit = True
        if not hit and re.search(r"guarantee", part) and re.search(r"unenforce|fail|void|not enforce|invalid|lost|no ", part):
            sh["guarantee_unenforceable"] = True
            parsed.append("Guarantee unenforceable")
            hit = True
        if not hit:
            for sid, s in byid.items():
                lab = s["label"].lower()
                if sid in ("construction_downturn", "trading_slowdown", "severe") and (lab in part or sid.replace("_", " ") in part):
                    sh.setdefault("_scale", []).append((sid, 1.0))
                    parsed.append(s["label"])
                    hit = True
                    break
        if not hit:
            m = re.search(r"(rate|rates|saibor|eibor|sofr|benchmark|interest|profit rate)[^\d+\-]*" + _NUM + r"(?!\s*(?:%|bps|bp|basis))", part)
            if m:
                v = _num(m.group(2))
                v = v * 100.0 if abs(v) < 10 else v  # "+2" reads as points, "+150" as bps
                v = signed(v, part, 1)
                sh["rate_bps"] = sh.get("rate_bps", 0.0) + v
                parsed.append(f"Benchmark rate {v:+.0f} bps")
                hit = True
        if not hit and (re.search(r"\d", part) or re.search(
                r"revenue|sales|margin|ebitda|rate|saibor|eibor|collateral|security|notch|downgrad|receivable|debtor|delay|customer|guarantee|oil|gdp|real estate|property", part)):
            # a figure or a shock word that was not understood is reported; filler ("stress this deal") is not
            unparsed.append(part)
    return {"text": text, "shocks": sh, "parsed": [_m(x) for x in parsed], "unparsed": unparsed, "ok": bool(parsed)}


def resolve_custom(spec: dict[str, Any], sector: str) -> dict[str, Any]:
    base = {k: v for k, v in spec.items() if not k.startswith("_")}
    out = resolve({"shocks": base}, sector)
    byid = _by_id()
    for sid, k in spec.get("_scale", []):
        r = resolve(byid[sid], sector)
        if sid in ("oil_30", "gdp_3"):
            r = {**r, "revenue_pct": r["revenue_pct"] * k}
        out = combine(out, r)
    return out


# ------------------------------------------------------------------ applying shocks: the stressed proposal

def _latest_index(p: dict[str, Any]) -> int:
    ys = p["financials"]["years"]
    return max(i for i, y in enumerate(ys) if y["kind"] == "actual")


def _ref_rate(p: dict[str, Any], t: dict[str, Any]) -> float:
    ftp = params.rows("ftp")
    return float(np.interp(ftp["reference_tenor"], ftp["tenors"], ftp["base"][t["currency"]]))


def stressed_financials(p: dict[str, Any], t: dict[str, Any], r: dict[str, Any]) -> dict[str, Any]:
    """The latest audited year after the revenue, margin and working-capital shocks (rates are the engine's)."""
    y = p["financials"]["years"][_latest_index(p)]
    sector = p["obligor"]["sector"]
    rev0, e0 = float(y["revenue"]), float(y["ebitda"])
    m0 = e0 / rev0 if rev0 else 0.0
    # R12 D: the ladder passes the fixed-cost share and spread it read from dd_stress_sensitivity (deal facts first)
    fixed = float(r["_fixed_cost_share"]) if r.get("_fixed_cost_share") is not None else float(_sectoral(_tr("fixed_cost_share"), sector))
    d_rev = rev0 * r["revenue_pct"]
    rev1 = rev0 + d_rev
    e1 = e0 + d_rev * (m0 + fixed) + rev1 * r["ebitda_margin_bps"] / 1e4
    wc = rev0 * r["receivable_days"] / 365.0
    st_rate = _ref_rate(p, t) + _spread(r)
    return {**y, "revenue": rev1, "ebitda": e1, "total_debt": float(y["total_debt"]) + wc,
            "debt_service": float(y["debt_service"]) + wc * st_rate, "working_capital_funded": wc,
            "ebitda_margin": e1 / rev1 if rev1 else None, "base": {"revenue": rev0, "ebitda": e0, "total_debt": float(y["total_debt"]),
                                                                  "debt_service": float(y["debt_service"])}}


def _spread(r: dict[str, Any]) -> float:
    """The short-term funding spread (decimal): the ladder's (dd_stress_sensitivity) when given, else the R11 table."""
    if r.get("_st_spread_bps") is not None:
        return float(r["_st_spread_bps"]) / 1e4
    return float(_tr("short_term_funding_spread_bps")["value"]) / 1e4


def stressed_case(p: dict[str, Any], t: dict[str, Any], r: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """(proposal copy, terms, engine shocks) for a resolved shock. Notches are added by the caller."""
    q = copy.deepcopy(p)
    i = _latest_index(q)
    fin = stressed_financials(p, t, r)
    q["financials"]["years"][i] = {k: v for k, v in fin.items() if k not in ("base", "working_capital_funded", "ebitda_margin")}
    for c in q["security"]["collateral"]:
        v = r["collateral"].get(c["type"])
        if v is not None and c.get("value") is not None:
            c["value"] = float(c["value"]) * (1 + v)
    tt = dict(t)
    if r["guarantee_unenforceable"]:
        tt["guarantee_id"] = None
        tt["guarantee_coverage_pct"] = 0
        tt["insurance_cover_pct"] = 0
    sh = {"rate_shock_bps": r["rate_bps"], "collateral_shock": r["collateral"].get("*", 0.0)}
    return q, tt, sh


# ------------------------------------------------------------------ closed forms of the engine's client ratios

class Mirror:
    """DSCR, Debt/EBITDA, LTV and interest cover after a shock, from one base engine run (no PD needed).

    Reproduces engine.analyse: DSCR = EBITDA / (debt service + rate x total debt + max client debt service),
    where the client's debt service on a floating deal moves with the rate on the drawn balance."""

    def __init__(self, p: dict[str, Any], t: dict[str, Any], base: dict[str, Any]):
        self.p, self.t = p, t
        tt = base["terms"]
        self.hold = float(tt["hold_pct"]) / 100.0
        self.floating = tt["rate_type"] != "fixed"
        self.deal_ds = np.array([s["debt_service"] for s in base["schedule"]])
        self.drawn = np.array([s["drawn_avg"] for s in base["schedule"]])
        held = float(base["metrics"]["held_sar_mn"])
        f_share = 0.0 if tt["facility_type"] in engine.UNFUNDED else float(tt["funded_share_pct"]) / 100.0
        self.f_full = held * f_share / self.hold if self.hold > 0 else held * f_share
        items = {c["collateral_id"]: c for c in p["security"]["collateral"]}
        self.re_items = [float(items[c].get("value") or 0.0) * engine.fx(items[c].get("currency", "SAR"))
                         for c in tt.get("collateral_ids", []) if items[c]["type"] == "real_estate"]
        self.ref_rate = _ref_rate(p, tt)
        self.rate0 = float(base["rates"]["client_rate"])

    def ratios(self, r: dict[str, Any]) -> dict[str, Any]:
        fin = stressed_financials(self.p, self.t, r)
        dr = r["rate_bps"] / 1e4
        ds_deal = (self.deal_ds + (self.drawn * dr if self.floating else 0.0)) / (self.hold if self.hold > 0 else 1.0)
        denom = fin["debt_service"] + dr * fin["total_debt"] + (float(ds_deal.max()) if len(ds_deal) else 0.0)
        e = fin["ebitda"]
        dscr = e / denom if denom > 0 else float("inf")
        de = (fin["total_debt"] + self.f_full) / e if e > 0 else float("inf")
        rv = sum(self.re_items) * (1 + r["collateral"].get("real_estate", 0.0)) * (1 + r["collateral"].get("*", 0.0))
        ltv = (self.f_full / rv if rv > 0 else float("inf")) if self.re_items else None
        spread = _spread(r)
        interest = (fin["total_debt"] * (self.ref_rate + spread + dr)
                    + float((self.drawn[0] * (self.rate0 + (dr if self.floating else 0.0))) / (self.hold or 1.0) if len(self.drawn) else 0.0))
        ic = e / interest if interest > 0 else float("inf")
        return {"dscr": dscr, "debt_ebitda": de, "ltv": ltv, "interest_cover": ic, "ebitda": e, "revenue": fin["revenue"],
                "total_debt": fin["total_debt"], "working_capital_funded": fin["working_capital_funded"], "fin": fin}


def band_position(v: float, bands: list[float], higher_is_worse: bool, cap: float) -> float:
    """Where a ratio sits on the band ladder, continuously: 0 at the best band's edge, +1 per band-width of deterioration
    (linear inside a band; past the last edge the last band's width continues), capped. Monotone in the ratio."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return 0.0
    e = sorted(bands) if higher_is_worse else sorted(bands, reverse=True)
    worse = (lambda x, y: x > y) if higher_is_worse else (lambda x, y: x < y)
    if not math.isfinite(v):
        return cap if (v > 0) == higher_is_worse else 0.0
    if not worse(v, e[0]):
        return 0.0
    for i in range(1, len(e)):
        if not worse(v, e[i]):
            return i - 1 + (v - e[i - 1]) / (e[i] - e[i - 1])
    w = e[-1] - e[-2]
    return float(min(cap, len(e) - 1 + (v - e[-1]) / w))


def implied_notches(base_r: dict[str, Any], st_r: dict[str, Any]) -> int:
    """Rating overlay: one notch for each full band-width the obligor's DSCR or Debt/EBITDA deteriorates from where it
    stands today (the larger of the two; never an upgrade). Measured from today's position, so a small move that happens
    to cross a band edge costs nothing until the deterioration is a full band wide."""
    ov = _tr("rating_overlay")
    cap = float(ov.get("max_notches", 8))
    db, lb = ov["dscr_bands"], ov["debt_ebitda_bands"]
    d = band_position(st_r["dscr"], db, False, cap) - band_position(base_r["dscr"], db, False, cap)
    l_ = band_position(st_r["debt_ebitda"], lb, True, cap) - band_position(base_r["debt_ebitda"], lb, True, cap)
    if st_r["ebitda"] <= 0 < base_r["ebitda"]:
        l_ = max(l_, cap - band_position(base_r["debt_ebitda"], lb, True, cap))
    return int(math.floor(max(0.0, d, l_) + 1e-9) * int(ov["notches_per_band"]))


def grade_after(rating: str, notches: int) -> str:
    i = GRADES.index(rating) if rating in GRADES else len(GRADES) - 1
    return GRADES[int(np.clip(i + notches, 0, len(GRADES) - 1))]


def stage_for(rating0: str, total_notches: int, dscr: float) -> tuple[int, str]:
    sr = _tr("stage_rules")
    sicr = int(params.table("pd_migration").get("sicr_notches", 3))
    g = grade_after(rating0, total_notches)
    moved = GRADES.index(g) - (GRADES.index(rating0) if rating0 in GRADES else 0)
    if g in sr["stage3_grades"]:
        return 3, f"rating {g}: unlikely to pay"
    if moved >= sicr:
        return 2, f"{moved} notches below origination (SICR threshold {sicr})"
    if dscr is not None and dscr < float(sr["stage2_dscr_below"]):
        return 2, f"DSCR {dscr:.2f}x below {float(sr['stage2_dscr_below']):.1f}x"
    return 1, "performing, no significant increase in credit risk"


# ------------------------------------------------------------------ Session F's PD path (optional)

def _forward_module():
    try:
        from backend.dealdesk import forward_risk  # type: ignore[attr-defined]
        return forward_risk
    except Exception:  # noqa: BLE001 - Session F not merged: the engine's PD only
        return None


def forward_path(p: dict[str, Any], t: dict[str, Any], notches: int, shocks: dict[str, Any] | None = None,
                 kw: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """P(Stage 2) and P(30+ DPD) next quarter from Session F's forward-risk model on the stressed deal, when present.

    `p` is the stressed proposal copy and `shocks` the engine shocks of the scenario (rates, all-collateral); the
    stressed grade is set on the obligor so F's features (grade, PD, post-deal DSCR and leverage, EBITDA margin,
    collateral cover) all see the stress. F's `score_structure(p, terms, book, kw)` is the in-process form of its API
    contract (POST /proposals/{id}/forward-risk); any failure falls back to the engine's PD only."""
    fr = _forward_module()
    if fr is None:
        return None
    q = p
    if notches:
        q = {**p, "obligor": {**p["obligor"], "internal_rating": grade_after(p["obligor"]["internal_rating"], notches)}}
    f = getattr(fr, "score_structure", None)
    if callable(f):
        try:
            book = fr.book_obligor(q["obligor"].get("obligor_id")) if q["obligor"].get("existing") and hasattr(fr, "book_obligor") else None
            k = dict(kw or {})
            sh = {kk: v for kk, v in (shocks or {}).items() if kk != "notches" and v}
            if sh:
                k.update({"shocks": sh, "validate": False})
            out = f(q, t, book, k, drivers=False)
            return {"source": "forward_risk.score_structure", "p_stage2_next_q": float(out["p_stage2_next_q"]),
                    "p_dpd30_next_q": None if out.get("p_dpd30_next_q") is None else float(out["p_dpd30_next_q"])}
        except Exception:  # noqa: BLE001 - F's model unavailable for this deal: the engine's PD only
            return None
    for name in ("structure_forward", "forward_for_terms", "deal_forward"):
        g = getattr(fr, name, None)
        if not callable(g):
            continue
        try:
            out = g(q, t)
        except Exception:  # noqa: BLE001
            continue
        if isinstance(out, dict) and out.get("p_stage2_next_q") is not None:
            p30 = out.get("p_dpd30_next_q")
            return {"source": f"forward_risk.{name}", "p_stage2_next_q": float(out["p_stage2_next_q"]),
                    "p_dpd30_next_q": None if p30 is None else float(p30)}
    return None


# ------------------------------------------------------------------ running one scenario

class Lab:
    """One proposal and one structure: the base engine run, the mirror, and cached engine runs."""

    def __init__(self, p: dict[str, Any], terms: dict[str, Any] | None, el_view: str = "economic", capital_basis: str | None = None,
                 label: str = "Asked"):
        self.p = p
        self.kw = {"el_view": el_view, "capital_basis": capital_basis}
        self.t = engine.merge_terms(p, terms)
        self.raw_terms = dict(terms or {})  # R12 D: terms outside the engine's set (the rating-linked margin ratchet)
        self.label = label
        self.base = engine.analyse(p, self.t, **self.kw)
        self.mirror = Mirror(p, self.t, self.base)
        self.base_r = self.mirror.ratios(copy.deepcopy(EMPTY))
        self.rating0 = p["obligor"]["internal_rating"]
        self.base_breaches = {(c["name"], c.get("scope")) for c in cons.breaches(self.base["constraints"])}
        self._sva_by_notch: dict[int, float] = {}
        self.evals = 1
        self.forward_source: str | None = None

    def run_engine(self, r: dict[str, Any], notches: int) -> dict[str, Any]:
        q, tt, sh = stressed_case(self.p, self.t, r)
        sh["notches"] = notches
        self.evals += 1
        try:
            return engine.analyse(q, tt, shocks=sh, validate=False, **self.kw)
        except StopIteration:
            # beyond the last IPRE LTV bucket of sa_risk_weights: hold the real-estate value at the bucket's edge
            edge = float(params.rows("sa_risk_weights")["ipre_ltv"][-1]["max_ltv"])
            rv = sum(self.mirror.re_items)
            need = self.mirror.f_full / edge / rv if rv > 0 else 1.0
            cur = (1 + r["collateral"].get("real_estate", 0.0)) * (1 + r["collateral"].get("*", 0.0))
            r2 = {**r, "collateral": {**r["collateral"], "real_estate": (1 + r["collateral"].get("real_estate", 0.0)) * need / cur - 1}}
            q, tt, sh = stressed_case(self.p, self.t, r2)
            sh["notches"] = notches
            return engine.analyse(q, tt, shocks=sh, validate=False, **self.kw)

    def sva_at_notches(self, n: int) -> float:
        if n not in self._sva_by_notch:
            self._sva_by_notch[n] = self.run_engine(copy.deepcopy(EMPTY), n)["metrics"]["sva"]
        return self._sva_by_notch[n]

    # -------------------------------------------------- one scenario
    def scenario(self, sid: str, spec: dict[str, Any], r: dict[str, Any]) -> dict[str, Any]:
        st = self.mirror.ratios(r)
        imp = implied_notches(self.base_r, st)
        total = int(r["notches"]) + imp
        a = self.run_engine(r, total) if not is_null(r) else self.base
        m = a["metrics"]
        b = self.base["metrics"]
        stage, why = stage_for(self.rating0, total, m["dscr_post"])
        ecl, ecl_basis = self._ecl(m, stage)
        covs = self._covenants({"dscr": m["dscr_post"], "debt_ebitda": m["debt_ebitda_post"], "interest_cover": st["interest_cover"]})
        brs = cons.breaches(a["constraints"])
        new = [c for c in brs if (c["name"], c.get("scope")) not in self.base_breaches]
        lim = {"breaches": [c["name"] for c in brs], "new_hard": [c["name"] for c in new if c["kind"] == "hard"],
               "new_soft": [c["name"] for c in new if c["kind"] == "soft"],
               "new_labels": [f"{c['label']} ({c['scope']})" if c.get("scope") else c["label"] for c in new],
               "approval_level": a["approval"]["level"], "approval_rank": a["approval"]["rank"],
               "approval_change": a["approval"]["rank"] - self.base["approval"]["rank"]}
        q, tt, sh = stressed_case(self.p, self.t, r)
        fwd = forward_path(q, tt, total, sh, self.kw)
        if fwd:
            self.forward_source = fwd["source"]
        ltv_limit = next((float(c["limit"]) for c in a["constraints"] if c["name"] == "ltv"), None)
        dscr_limit = next((float(c["limit"]) for c in a["constraints"] if c["name"] == "dscr"), None)
        de_limit = next((float(c["limit"]) for c in a["constraints"] if c["name"] == "debt_ebitda"), None)
        rating = a["pd"]["rating_used"] if a.get("pd") else grade_after(self.rating0, total)
        min_rating_breach = any(c["name"] == "min_rating" and c["status"] == "breach" for c in a["constraints"])
        res = {
            "id": sid, "group": spec.get("group", "custom"), "label": spec.get("label", sid), "severity": spec.get("severity", "custom"),
            "basis": spec.get("basis", ""), "shocks": describe(r), "resolved": r, "applicable": not is_null(r),
            "financials": {"revenue": st["revenue"], "ebitda": st["ebitda"], "total_debt": st["total_debt"],
                           "working_capital_funded": st["working_capital_funded"],
                           "base_revenue": self.base_r["revenue"], "base_ebitda": self.base_r["ebitda"]},
            "metrics": {"dscr": m["dscr_post"], "debt_ebitda": m["debt_ebitda_post"], "ltv": m["ltv"], "interest_cover": st["interest_cover"],
                        "pd_12m": m["pd_12m"], "rating": rating, "notches": {"scenario": int(r["notches"]), "implied": imp, "total": total},
                        "stage": stage, "stage_reason": why, "ecl": ecl, "ecl_basis": ecl_basis, "lifetime_raroc": m["lifetime_raroc"],
                        "hurdle": m["hurdle"], "sva": m["sva"], "rwa_y1": m["rwa_y1"], "el_y1": m["el_y1"], "lgd_y1": m["lgd_y1"],
                        "ead_y1": m["ead_y1"], "clears_hurdle": m["clears_hurdle"]},
            "deltas": {"dscr": _d(m["dscr_post"], b["dscr_post"]), "pd_12m": m["pd_12m"] - b["pd_12m"],
                       "lifetime_raroc": m["lifetime_raroc"] - b["lifetime_raroc"], "sva": m["sva"] - b["sva"],
                       "rwa_y1": m["rwa_y1"] - b["rwa_y1"], "ecl": ecl - self._ecl(b, 1)[0]},
            "covenants": covs, "limits": lim, "forward": fwd,
            "thresholds": {"dscr_limit": dscr_limit, "debt_ebitda_limit": de_limit, "ltv_limit": ltv_limit},
        }
        res["cells"] = self._cells(res, min_rating_breach)
        res["fails_on"] = [k for k, v in res["cells"].items() if v == "breach"]
        res["survives"] = not res["fails_on"]
        return res

    def _ecl(self, m: dict[str, Any], stage: int) -> tuple[float, str]:
        if stage == 1:
            return float(m["el_y1"]), "Stage 1: 12-month ECL (year-1 EAD x PD x LGD)"
        if stage == 2:
            return float(m["el_lifetime_pv"]), "Stage 2: lifetime ECL (sum of yearly EAD x marginal PD x LGD, PV at the hurdle)"
        return float(m["ead_y1"]) * float(m["lgd_y1"]), "Stage 3: EAD x LGD (credit-impaired)"

    def _covenants(self, v: dict[str, Any]) -> list[dict[str, Any]]:
        amber = float(_tr_bands()["amber_headroom"])
        out = []
        for c in self.p["security"].get("covenants", []):
            typ = c["type"]
            th = float(c["threshold"])
            if typ.lower().startswith("dscr"):
                val, lo = v["dscr"], True
            elif "ebitda" in typ.lower() and "debt" in typ.lower():
                val, lo = v["debt_ebitda"], False
            elif "interest" in typ.lower():
                val, lo = v["interest_cover"], True
            else:
                out.append({"type": typ, "threshold": th, "value": None, "headroom": None, "status": "not_modelled",
                            "basis": "Not a ratio the Stress Lab moves"})
                continue
            if val is None or (isinstance(val, float) and not math.isfinite(val)):
                head = None if val is None else (float("inf") if lo else float("-inf"))
            else:
                head = (val - th) / th if lo else (th - val) / th
            status = "breach" if head is not None and head < -1e-12 else "amber" if head is not None and head < amber else "pass"
            if val is not None and isinstance(val, float) and not math.isfinite(val):
                status = "pass" if lo else "breach"
            out.append({"type": typ, "threshold": th, "value": val, "headroom": head, "status": status,
                        "basis": ("Net debt approximated by total debt (no cash split in the proposal)" if not lo and "net" in typ.lower()
                                  else "Interest estimated: debt at benchmark + short-term spread, plus the deal's year-1 profit"
                                  if "interest" in typ.lower() else "Engine DSCR after the deal")})
        return out

    def _cells(self, s: dict[str, Any], min_rating_breach: bool) -> dict[str, str]:
        bands = _tr_bands()
        amber = float(bands["amber_headroom"])
        m, th = s["metrics"], s["thresholds"]
        cells = {}
        d = m["dscr"]
        if d is None or d < 1.0 or (th["dscr_limit"] and d < th["dscr_limit"] - 1e-12):
            cells["dscr"] = "breach"
        elif th["dscr_limit"] and d < th["dscr_limit"] * (1 + amber):
            cells["dscr"] = "amber"
        elif any(c["status"] in ("breach",) for c in s["covenants"] if c["type"].lower().startswith("dscr")):
            cells["dscr"] = "amber"
        else:
            cells["dscr"] = "pass"
        de = m["debt_ebitda"]
        if de is None or (th["debt_ebitda_limit"] and de > th["debt_ebitda_limit"] + 1e-12):
            cells["debt_ebitda"] = "breach"
        elif th["debt_ebitda_limit"] and de > th["debt_ebitda_limit"] * (1 - amber):
            cells["debt_ebitda"] = "amber"
        else:
            cells["debt_ebitda"] = "pass"
        if m["ltv"] is None or not th["ltv_limit"]:
            cells["ltv"] = "na" if m["ltv"] is None else "pass"
        elif m["ltv"] > th["ltv_limit"] + 1e-12:
            cells["ltv"] = "breach"
        elif m["ltv"] > th["ltv_limit"] * (1 - amber):
            cells["ltv"] = "amber"
        else:
            cells["ltv"] = "pass"
        cv = [c["status"] for c in s["covenants"]]
        cells["covenants"] = "na" if not cv or all(x == "not_modelled" for x in cv) else (
            "breach" if "breach" in cv else "amber" if "amber" in cv else "pass")
        cells["rating"] = "breach" if min_rating_breach else "amber" if m["notches"]["total"] > 0 else "pass"
        cells["stage"] = "pass" if m["stage"] == 1 else "breach"
        h = m["hurdle"]
        r_ = m["lifetime_raroc"]
        if r_ is None or not m["clears_hurdle"]:
            cells["raroc"] = "breach"
        elif r_ < h + float(bands["raroc_amber_pts"]):
            cells["raroc"] = "amber"
        else:
            cells["raroc"] = "pass"
        lim = s["limits"]
        cells["limits"] = "breach" if lim["new_hard"] else "amber" if (lim["new_soft"] or lim["approval_change"] > 0) else "pass"
        return cells

    def base_row(self) -> dict[str, Any]:
        r = self.scenario("base", {"group": "base", "label": "Base (no stress)", "severity": "none",
                                   "basis": "The structure as analysed, no shock."}, copy.deepcopy(EMPTY))
        return r

    # -------------------------------------------------- reverse stress
    def _shock(self, driver: str, x: float) -> dict[str, Any]:
        r = copy.deepcopy(EMPTY)
        if driver == "collateral_pct":
            r["collateral"] = {"*": x}
        else:
            r[driver] = x
        return r

    def _fails(self, driver: str, crit: str, x: float) -> bool | None:
        r = self._shock(driver, x)
        st = self.mirror.ratios(r)
        if crit == "dscr":
            return st["dscr"] < 1.0
        if crit == "ltv":
            lim = self._ltv_limit()
            if st["ltv"] is None or lim is None:
                return None
            return st["ltv"] > lim + 1e-12
        n = implied_notches(self.base_r, st)
        if crit == "stage2":
            return stage_for(self.rating0, n, st["dscr"])[0] >= 2
        if crit == "raroc":
            if driver in ("revenue_pct", "ebitda_margin_bps"):
                return self.sva_at_notches(n) < 0
            return self.run_engine(r, n)["metrics"]["sva"] < 0
        raise KeyError(crit)

    def _ltv_limit(self) -> float | None:
        """The LTV limit where the engine applies it (real-estate finance), else none."""
        return next((float(c["limit"]) for c in self.base["constraints"] if c["name"] == "ltv"), None)

    def breakevens(self) -> list[dict[str, Any]]:
        rng = table()["transmission"]["breakeven_ranges"]
        out = []
        for drv, (lab, unit) in DRIVERS.items():
            lo_, hi_ = (float(v) for v in rng[drv])
            crits = []
            for crit, clab in CRITERIA.items():
                if drv == "collateral_pct" and crit in ("dscr", "stage2"):
                    continue
                if drv != "collateral_pct" and crit == "ltv":
                    continue
                if drv == "collateral_pct" and not self.t.get("collateral_ids") and not float(self.t.get("receivables_assignment_pct") or 0):
                    crits.append({"criterion": crit, "label": clab, "status": "na", "value": None,
                                  "note": "No collateral is pledged in this structure."})
                    continue
                crits.append(self._solve(drv, crit, clab, lo_, hi_))
            # the first test a stress on this driver breaks; tests already failing before any shock are listed apart
            found = [c for c in crits if c["status"] == "found"]
            first = min(found, key=lambda c: abs(c["value"])) if found else None
            out.append({"driver": drv, "label": lab, "unit": unit, "range": [lo_, hi_], "criteria": crits,
                        "first": None if first is None else {"criterion": first["criterion"], "label": first["label"], "value": first["value"]},
                        "failing_now": [c["label"] for c in crits if c["status"] == "already"]})
        return out

    def _solve(self, drv: str, crit: str, clab: str, lo: float, hi: float) -> dict[str, Any]:
        f0 = self._fails(drv, crit, lo)
        if f0 is None:
            return {"criterion": crit, "label": clab, "status": "na", "value": None,
                    "note": "No real estate pledged: LTV does not apply." if crit == "ltv" else "Not applicable."}
        if f0:
            return {"criterion": crit, "label": clab, "status": "already", "value": lo, "note": "Fails before any shock."}
        if not self._fails(drv, crit, hi):
            return {"criterion": crit, "label": clab, "status": "beyond", "value": None, "limit_of_search": hi,
                    "note": f"Not reached within {_fmt_driver(drv, hi)}."}
        a, b = lo, hi
        tol = TOL[drv]
        while abs(b - a) > tol:
            mid = (a + b) / 2
            if self._fails(drv, crit, mid):
                b = mid
            else:
                a = mid
        return {"criterion": crit, "label": clab, "status": "found", "value": b, "passes_at": a, "tolerance": tol}


def _tr_bands() -> dict[str, Any]:
    return _tr("bands")


def _d(a: Any, b: Any) -> float | None:
    if a is None or b is None or not (math.isfinite(a) and math.isfinite(b)):
        return None
    return a - b


def _fmt_driver(drv: str, v: float) -> str:
    if drv in ("revenue_pct", "collateral_pct"):
        return f"{v * 100:+.0f}%"
    return f"{v:+.0f} bps"


# ------------------------------------------------------------------ the whole Stress Lab result

def _summary(rows: list[dict[str, Any]], base: dict[str, Any] | None = None) -> dict[str, Any]:
    """Survived: no breach at all. Holds: no breach beyond those the structure already has before stress."""
    pre = set(base["fails_on"]) if base else set()
    for r in rows:
        r["new_fails"] = [c for c in r["fails_on"] if c not in pre]
    app = [r for r in rows if r["applicable"]]
    surv = [r for r in app if r["survives"]]
    failed = [r for r in app if not r["survives"]]
    sev = next((r for r in rows if r["id"] == "severe"), None)
    return {"applicable": len(app), "survived": len(surv), "holds": len([r for r in app if not r["new_fails"]]),
            "base_fails": sorted(pre, key=METRIC_CELLS.index), "failed": [r["id"] for r in failed],
            "failed_labels": [f"{r['label']} ({', '.join(CELL_LABELS[c] for c in r['fails_on'])})" for r in failed],
            "severe": None if sev is None else {"survives": sev["survives"], "fails_on": sev["fails_on"], "new_fails": sev["new_fails"],
                                                "lifetime_raroc": sev["metrics"]["lifetime_raroc"], "dscr": sev["metrics"]["dscr"],
                                                "stage": sev["metrics"]["stage"], "rating": sev["metrics"]["rating"]},
            "worst_raroc": min((r["metrics"]["lifetime_raroc"] for r in app if r["metrics"]["lifetime_raroc"] is not None), default=None),
            "worst_dscr": min((r["metrics"]["dscr"] for r in app if r["metrics"]["dscr"] is not None), default=None),
            "max_ecl": max((r["metrics"]["ecl"] for r in app), default=None),
            "stage2_count": len([r for r in app if r["metrics"]["stage"] >= 2])}


def _answer(summary: dict[str, Any], bes: list[dict[str, Any]], rows: list[dict[str, Any]], base: dict[str, Any] | None = None) -> str:
    """One line, answer first: how many scenarios it survives, what breaks it, and the revenue distance to DSCR 1.0."""
    s = summary
    parts = []
    pre = s["base_fails"]
    key = "new_fails" if pre else "fails_on"
    if pre:
        parts.append("Fails " + ", ".join(CELL_LABELS[c] for c in pre) + " before any stress")
        parts.append(f"otherwise holds in {s['holds']} of {s['applicable']} scenarios")
    else:
        parts.append(f"Survives {s['survived']} of {s['applicable']} scenarios")
    failed = [r for r in rows if r["applicable"] and r[key]]
    if failed:
        def short(r: dict[str, Any]) -> str:
            lab = "the severe case" if r["id"] == "severe" else r["label"]
            return f"{lab} ({', '.join(CELL_LABELS[c] for c in r[key][:2])})"
        shown = sorted(failed, key=lambda r: (r["id"] != "severe", -len(r[key])))[:2]
        more = len(failed) - len(shown)
        parts.append("fails " + " and ".join(short(r) for r in shown) + (f" and {more} more" if more > 0 else ""))
    rev = next((b for b in bes if b["driver"] == "revenue_pct"), None)
    if rev:
        d = next((c for c in rev["criteria"] if c["criterion"] == "dscr"), None)
        if d and d["status"] == "found":
            parts.append(f"revenue can fall {abs(d['value']) * 100:.0f}% before DSCR < 1.0")
        elif d and d["status"] == "already":
            parts.append("DSCR is below 1.0 before any shock")
        elif d and d["status"] == "beyond":
            parts.append("DSCR stays above 1.0 even with revenue down 95%")
    return _m("; ".join(parts) + ".")


def recommended_terms(p: dict[str, Any], el_view: str = "economic", capital_basis: str | None = None) -> tuple[dict[str, Any] | None, str]:
    """The Optimise recommended structure as the deal view picks it (closest to the ask, else maximum value, else the
    first alternative), cached per proposal and parameter version."""
    return _recommended(p["proposal_id"], params.version_tag(), el_view, capital_basis or "")


@functools.lru_cache(maxsize=64)
def _recommended(pid: str, _v: str, el_view: str, cb: str) -> tuple[dict[str, Any] | None, str]:
    from backend.dealdesk import optimizer, proposals
    p = proposals.get(pid)
    r = optimizer.optimize(p, el_view=el_view, capital_basis=cb or None)
    for k, lab in (("closest", "Closest to the ask"), ("max_sva", "Maximum value")):
        if r.get(k):
            return r[k]["terms"], lab
    for a in r.get("alternatives") or []:
        return a["terms"], a.get("label", "Alternative")
    return None, ""


def run(p: dict[str, Any], terms: dict[str, Any] | None = None, *, scenario_ids: list[str] | None = None,
        custom: str | dict[str, Any] | None = None, recommended: dict[str, Any] | None = None, resilience: bool = True,
        breakevens: bool = True, el_view: str = "economic", capital_basis: str | None = None,
        structure_label: str | None = None) -> dict[str, Any]:
    """POST /proposals/{id}/stress."""
    sector = p["obligor"]["sector"]
    byid = _by_id()
    ids = list(byid) if not scenario_ids else scenario_ids
    bad = [i for i in ids if i not in byid]
    if bad:
        raise engine.TermsError([{"field": "scenarios", "message": f"unknown {', '.join(bad)}; one of {', '.join(byid)}"}])
    specs: list[tuple[str, dict[str, Any], dict[str, Any]]] = [(i, byid[i], resolve(byid[i], sector)) for i in ids]
    cust = None
    if custom:
        if isinstance(custom, str):
            cust = parse_custom(custom)
            if not cust["ok"]:
                raise engine.TermsError([{"field": "custom", "message": "no shock recognised; try 'revenue -20% and rates +150 bps'"}])
            cspec = cust["shocks"]
            label = "Custom: " + custom.strip()[:60]
        else:
            cspec = custom
            cust = {"text": None, "shocks": custom, "parsed": describe(resolve_custom(custom, sector)), "unparsed": [], "ok": True}
            label = "Custom"
        r = resolve_custom(cspec, sector)
        specs.append(("custom", {"group": "custom", "label": label, "severity": "custom",
                                 "basis": "Typed by the user: " + "; ".join(cust["parsed"])}, r))

    asked_terms = engine.merge_terms(p, None)
    chosen = engine.merge_terms(p, terms)
    lab = Lab(p, chosen, el_view, capital_basis, structure_label or ("Asked" if chosen == asked_terms else "Selected"))
    base = lab.base_row()
    rows = [lab.scenario(i, s, r) for i, s, r in specs]
    summ = _summary(rows, base)
    bes = lab.breakevens() if breakevens else []
    out: dict[str, Any] = {
        "proposal_id": p["proposal_id"], "obligor": p["obligor"]["name"], "sector": sector,
        "structure": {"label": lab.label, "terms": lab.t},
        "base": base, "scenarios": rows, "summary": summ, "breakevens": bes,
        "answer": _answer(summ, bes, rows, base), "custom": cust,
        "cells": [{"key": k, "label": CELL_LABELS[k]} for k in METRIC_CELLS],
        "pd_source": lab.forward_source or "engine",
        "pd_basis": ("Session F forward-risk P(Stage 2) next quarter at the stressed grade, alongside the engine PD"
                     if lab.forward_source else
                     "Engine PD: the What-If XGBoost model re-scored at the stressed grade (scenario notches + rating overlay)"),
        "basis": {"scenarios": f"stress_scenarios.json {table()['version']} ({table()['owner']}, effective {table()['effective_from']})",
                  "engine": "engine.analyse on a stressed copy of the proposal; rate, notch and all-collateral shocks through engine shocks",
                  "overlay": _tr("rating_overlay")["basis"], "stage": _tr("stage_rules")["basis"], "bands": _tr("bands")["basis"],
                  "param_versions": params.versions()},
        "evaluations": lab.evals,
    }
    if resilience:
        rec_t, rec_lab = (recommended, "Recommended") if recommended else recommended_terms(p, el_view, capital_basis)
        res = {"asked": None, "recommended": None, "verdict": ""}
        structs = [("asked", asked_terms, "Asked")]
        if rec_t is not None:
            structs.append(("recommended", engine.merge_terms(p, rec_t), rec_lab or "Recommended"))
        for key, tt, lb in structs:
            if tt == lab.t:
                rs, sm = rows, summ
            else:
                try:
                    lb2 = Lab(p, tt, el_view, capital_basis, lb)
                except engine.TermsError:
                    continue
                rs = [lb2.scenario(i, s, r) for i, s, r in specs]
                sm = _summary(rs, lb2.base_row())
                out["evaluations"] += lb2.evals
            res[key] = {"label": lb, "terms": tt, "summary": sm,
                        "rows": [{"id": r["id"], "label": r["label"], "survives": r["survives"], "fails_on": r["fails_on"],
                                  "new_fails": r["new_fails"], "lifetime_raroc": r["metrics"]["lifetime_raroc"], "sva": r["metrics"]["sva"],
                                  "dscr": r["metrics"]["dscr"], "stage": r["metrics"]["stage"], "ecl": r["metrics"]["ecl"],
                                  "applicable": r["applicable"]} for r in rs]}
        res["same_structure"] = res["recommended"] is not None and res["recommended"]["terms"] == asked_terms
        res["verdict"] = _verdict(res)
        out["resilience"] = res
    return out


def _verdict(res: dict[str, Any]) -> str:
    a, r = res.get("asked"), res.get("recommended")
    if a is None:
        return ""
    if r is None:
        return f"Asked structure survives {a['summary']['survived']} of {a['summary']['applicable']}; the optimiser found no recommended structure."
    if res.get("same_structure"):
        return f"The recommended structure is the ask: it survives {a['summary']['survived']} of {a['summary']['applicable']} scenarios."
    sa, sr = a["summary"]["severe"], r["summary"]["severe"]
    sev = ""
    if sa and sr:
        if sr["survives"] and not sa["survives"]:
            sev = "only the recommended structure survives the severe case"
        elif sa["survives"] and not sr["survives"]:
            sev = "only the asked structure survives the severe case"
        elif sa["survives"] and sr["survives"]:
            sev = "both survive the severe case"
        else:
            sev = "neither survives the severe case"
    return (f"Recommended survives {r['summary']['survived']} of {r['summary']['applicable']}, asked "
            f"{a['summary']['survived']} of {a['summary']['applicable']}" + (f"; {sev}." if sev else "."))


__all__ = ["table", "scenarios_catalogue", "resolve", "combine", "parse_custom", "resolve_custom", "run", "Lab", "Mirror",
           "implied_notches", "stage_for", "stressed_financials", "recommended_terms"]
