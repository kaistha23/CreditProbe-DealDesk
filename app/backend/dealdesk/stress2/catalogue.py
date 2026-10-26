"""The R12 scenario ladder and the sector sensitivities, as Data Domains relations (PLAN_R12 §1.5, I19, I20, O5, O6).

Scenarios (`dd_stress_scenario`) are rows: one per scenario version, bank or deal scope, with the family,
severity, shocks (JSON), basis and the maker-checker trail. Sensitivities (`dd_stress_sensitivity`) are rows:
one per (sensitivity, sector, version) with value, band, unit, method and source. Session T publishes calibrated
versions later; `sensitivities()` always reads whichever approved version is current.

The seed (`SEED_VERSION`) is the R11 expert table (data/dealdesk/params/v1/stress_scenarios.json) re-cut as a
ladder: every family runs mild -> moderate -> severe, rating -1/-2/-3 notches is its own family, the combined
moderate case is the mild shocks together and the combined severe case the moderate ones together, revenue
shock included (O5). The seed is published once to the relations (`ensure_seeded`) so that every figure
the ladder uses is read back from Data Domains, never from the JSON at run time.
"""
from __future__ import annotations

import functools
import json
from typing import Any

from backend.dealdesk import paths
from backend.dealdesk.stress2 import store

SEED_VERSION = "R12-L1"
SENS_SEED_VERSION = 1
R11_FILE = paths.params_dir() / "v1" / "stress_scenarios.json"
FAMILIES = [("macro", "Macro"), ("sector", "Sector"), ("borrower", "Borrower"), ("collateral", "Collateral"),
            ("rating", "Rating"), ("combined", "Combined"), ("custom", "Your scenarios")]
FAMILY_LABEL = dict(FAMILIES)
SEVERITIES = ("mild", "moderate", "severe")
SOURCE_R11 = "Risk Models expert assumption (stress_scenarios.json v1, R11)"


@functools.lru_cache(maxsize=1)
def r11_table() -> dict[str, Any]:
    return json.loads(R11_FILE.read_text())


# ------------------------------------------------------------------ the seed: sensitivities

def _by_sector(d: dict[str, Any], scale: float = 1.0) -> dict[str, float]:
    out = {"*": float(d.get("default", 0.0)) * scale}
    out.update({k: float(v) * scale for k, v in d.get("by_sector", {}).items()})
    return out


SENS_META = {
    "oil_revenue_beta": ("Revenue change per 1% fall in oil", "revenue % per 1% oil fall",
                         "Oil -> revenue: the sector's revenue change for each 1% Brent falls below plan (GCC oil transmission)."),
    "gdp_revenue_beta": ("Revenue change per 1% fall in non-oil GDP", "revenue % per 1% GDP fall",
                         "Non-oil GDP -> revenue: the sector's GDP beta (0.5 for utilities and healthcare to 3.0 for construction)."),
    "fixed_cost_share": ("Fixed-cost share of revenue", "share of revenue",
                         "Operating leverage: EBITDA change = revenue change x (EBITDA margin + fixed-cost share)."),
    "largest_customer_share": ("Largest customer's share of revenue", "share of revenue",
                               "Used where the deal file gives no customer split."),
    "project_revenue_share": ("Project-milestone share of revenue", "share of revenue",
                              "Share of annual revenue tied to milestones that a delay defers."),
    "sector_downturn_revenue": ("Own-sector downturn: revenue", "revenue change",
                                "The moderate own-sector downturn (construction downturn or trading slowdown)."),
    "sector_downturn_receivable_days": ("Own-sector downturn: receivable days", "days",
                                        "Delayed government, developer or buyer payments in the sector's downturn."),
    "sector_downturn_margin_bps": ("Own-sector downturn: EBITDA margin", "bps", "Margin squeeze in the sector's downturn."),
    "real_estate_revenue_beta": ("Revenue change per 1% fall in real-estate prices", "revenue % per 1% price fall",
                                 "Rents and construction starts follow real-estate prices."),
    "short_term_funding_spread_bps": ("Short-term funding spread", "bps",
                                      "Working capital absorbed by longer receivable days is funded at the benchmark plus this spread."),
}


def seed_sensitivities() -> list[dict[str, Any]]:
    t = r11_table()
    sc = {s["id"]: s for s in t["scenarios"]}
    tr = t["transmission"]
    vals: dict[str, dict[str, float]] = {
        "oil_revenue_beta": _by_sector(sc["oil_30"]["shocks"]["revenue_pct"], 1 / 30.0),
        "gdp_revenue_beta": _by_sector(sc["gdp_3"]["shocks"]["revenue_pct"], 1 / 3.0),
        "fixed_cost_share": _by_sector(tr["fixed_cost_share"]),
        "largest_customer_share": _by_sector(tr["largest_customer_share"]),
        "project_revenue_share": _by_sector(tr["project_revenue_share"]),
        "real_estate_revenue_beta": _by_sector(sc["re_20"]["shocks"]["revenue_pct"], 1 / 20.0),
        "short_term_funding_spread_bps": {"*": float(tr["short_term_funding_spread_bps"]["value"])},
    }
    # the own-sector downturn: the sector scenario the R11 severe case picks (none: no own-sector downturn)
    own = sc["severe"]["sector_scenario"]["by_sector"]
    rev, days, mbps = {"*": 0.0}, {"*": 0.0}, {"*": 0.0}
    for sector, sid in own.items():
        s = sc[sid]["shocks"]
        rev[sector] = float(s["revenue_pct"].get("by_sector", {}).get(sector, 0.0))
        days[sector] = float((s.get("receivable_days") or {}).get("by_sector", {}).get(sector, 0.0))
        mbps[sector] = float((s.get("ebitda_margin_bps") or {}).get("by_sector", {}).get(sector, 0.0))
    vals.update({"sector_downturn_revenue": rev, "sector_downturn_receivable_days": days, "sector_downturn_margin_bps": mbps})
    rows = []
    for sid, by in vals.items():
        lab, unit, basis = SENS_META[sid]
        for sector, v in by.items():
            rows.append({"sensitivity_id": sid, "sector": sector, "value": v, "lower": None, "upper": None, "unit": unit,
                         "label": lab, "basis": basis, "method": "expert", "source": SOURCE_R11, "version": SENS_SEED_VERSION,
                         "status": "approved", "published_by": "Risk Models (seed)", "published_at": "2026-10-12T00:00:00+00:00",
                         "n_obs": None, "flag": "expert value: not estimated from data"})
    return rows


# ------------------------------------------------------------------ the seed: the ladder

def _sc(sid: str, family: str, sev: str, label: str, shocks: dict[str, Any], basis: str) -> dict[str, Any]:
    return {"scenario_id": sid, "family": family, "severity": sev, "label": label, "shocks": shocks, "basis": basis}


def seed_ladder() -> list[dict[str, Any]]:
    L = [
        _sc("oil_15", "macro", "mild", "Oil −15%", {"oil_pct": -15}, "Brent 15% below the planning price for four quarters; revenue moves by the sector's oil beta."),
        _sc("oil_30", "macro", "moderate", "Oil −30%", {"oil_pct": -30}, "Brent 30% below plan: government capex and petrochemical prices fall."),
        _sc("oil_45", "macro", "severe", "Oil −45%", {"oil_pct": -45}, "Brent 45% below plan, a 2015-scale shock."),
        _sc("gdp_1_5", "macro", "mild", "Non-oil GDP −1.5%", {"gdp_pct": -1.5}, "Real non-oil GDP 1.5% below plan; revenue moves by the sector's GDP beta."),
        _sc("gdp_3", "macro", "moderate", "Non-oil GDP −3%", {"gdp_pct": -3}, "Real non-oil GDP 3% below plan."),
        _sc("gdp_4_5", "macro", "severe", "Non-oil GDP −4.5%", {"gdp_pct": -4.5}, "Real non-oil GDP 4.5% below plan, a recession."),
        _sc("rates_100", "macro", "mild", "Rates +100 bps", {"rate_bps": 100}, "SAIBOR / EIBOR up 100 bps in parallel: floating pricing and the obligor's existing debt reprice."),
        _sc("rates_200", "macro", "moderate", "Rates +200 bps", {"rate_bps": 200}, "Benchmark up 200 bps in parallel."),
        _sc("rates_300", "macro", "severe", "Rates +300 bps", {"rate_bps": 300}, "Benchmark up 300 bps in parallel."),
        _sc("sector_mild", "sector", "mild", "Own-sector slowdown", {"sector_downturn": 0.5}, "Half the sector's downturn: revenue, receivable days and margin."),
        _sc("sector_moderate", "sector", "moderate", "Own-sector downturn", {"sector_downturn": 1.0}, "The sector's downturn (construction downturn or trading slowdown)."),
        _sc("sector_severe", "sector", "severe", "Own-sector crisis", {"sector_downturn": 1.5}, "One and a half times the sector's downturn."),
        _sc("rev_10", "borrower", "mild", "Revenue −10%", {"revenue_pct": -0.10}, "Revenue 10% below the latest audited year, with operating leverage."),
        _sc("rev_20", "borrower", "moderate", "Revenue −20%", {"revenue_pct": -0.20}, "Revenue 20% below the latest audited year."),
        _sc("rev_30", "borrower", "severe", "Revenue −30%", {"revenue_pct": -0.30}, "Revenue 30% below the latest audited year."),
        _sc("margin_150", "borrower", "mild", "EBITDA margin −150 bps", {"ebitda_margin_bps": -150}, "Input costs rise faster than prices: margin 1.5 points lower."),
        _sc("margin_300", "borrower", "moderate", "EBITDA margin −300 bps", {"ebitda_margin_bps": -300}, "Margin 3 points lower on the same revenue."),
        _sc("margin_450", "borrower", "severe", "EBITDA margin −450 bps", {"ebitda_margin_bps": -450}, "Margin 4.5 points lower."),
        _sc("cust_33", "borrower", "mild", "Largest customer cuts a third", {"customer_loss_share": 1 / 3}, "The largest customer buys a third less."),
        _sc("cust_67", "borrower", "moderate", "Largest customer cuts two thirds", {"customer_loss_share": 2 / 3}, "The largest customer buys two thirds less."),
        _sc("cust_100", "borrower", "severe", "Largest customer lost", {"customer_loss_share": 1.0}, "The largest customer stops buying."),
        _sc("paydelay_30", "borrower", "mild", "Payments 30 days slower", {"receivable_days": 30}, "Customers pay 30 days later; the gap is funded with short-term debt."),
        _sc("paydelay_60", "borrower", "moderate", "Payments 60 days slower", {"receivable_days": 60}, "Customers pay 60 days later."),
        _sc("paydelay_90", "borrower", "severe", "Payments 90 days slower", {"receivable_days": 90}, "Customers pay 90 days later."),
        _sc("delay_3", "borrower", "mild", "Project delay 3 months", {"delay_months": 3}, "Milestone revenue slips 3 months; the work done is carried as receivables."),
        _sc("delay_6", "borrower", "moderate", "Project delay 6 months", {"delay_months": 6}, "Milestone revenue slips 6 months."),
        _sc("delay_12", "borrower", "severe", "Project delay 12 months", {"delay_months": 12}, "Milestone revenue slips 12 months."),
        _sc("coll_20", "collateral", "mild", "Collateral −20%", {"collateral_pct": -0.20}, "Every pledged item revalued 20% lower."),
        _sc("coll_30", "collateral", "moderate", "Collateral −30%", {"collateral_pct": -0.30}, "Every pledged item revalued 30% lower."),
        _sc("coll_40", "collateral", "severe", "Collateral −40%", {"collateral_pct": -0.40}, "Every pledged item revalued 40% lower (distressed market)."),
        _sc("re_10", "collateral", "mild", "Real-estate prices −10%", {"real_estate_pct": -10}, "Pledged real estate revalued 10% lower; real-estate revenue follows."),
        _sc("re_20", "collateral", "moderate", "Real-estate prices −20%", {"real_estate_pct": -20}, "Pledged real estate revalued 20% lower."),
        _sc("re_30", "collateral", "severe", "Real-estate prices −30%", {"real_estate_pct": -30}, "Pledged real estate revalued 30% lower."),
        _sc("guarantee_void", "collateral", "severe", "Guarantee unenforceable", {"guarantee_unenforceable": True}, "The guarantee or credit insurance cannot be called: the deal stands on the obligor alone."),
        _sc("notch_1", "rating", "mild", "Rating −1 notch", {"notches": 1}, "One-notch downgrade applied directly: PD, capital, ECL, stage and pricing at the lower grade."),
        _sc("notch_2", "rating", "moderate", "Rating −2 notches", {"notches": 2}, "Two-notch downgrade applied directly."),
        _sc("notch_3", "rating", "severe", "Rating −3 notches", {"notches": 3}, "Three-notch downgrade, the policy's SICR threshold."),
        _sc("combined_moderate", "combined", "moderate", "Combined moderate",
            {"compose": ["oil_15", "rates_100", "rev_10", "coll_20"]},
            "The mild shocks together: oil −15%, rates +100 bps, revenue −10% and collateral −20%."),
        _sc("combined_severe", "combined", "severe", "Combined severe",
            {"compose": ["oil_30", "rates_200", "sector_moderate|gdp_3", "coll_30", "rev_20"]},
            "The moderate shocks together: oil −30%, rates +200 bps, the obligor's own-sector downturn (GDP −3% where the sector has none), collateral −30% and revenue −20% (O5: the revenue shock is in the severe case)."),
    ]
    rows = []
    for s in L:
        rows.append({"scenario_id": s["scenario_id"], "version": 1, "set_id": SEED_VERSION, "scope": "bank", "proposal_id": None,
                     "family": s["family"], "severity": s["severity"], "label": s["label"], "shocks": s["shocks"], "basis": s["basis"],
                     "source": "R12 ladder seed from " + SOURCE_R11, "status": "approved", "maker": "Risk Models (seed)",
                     "made_at": "2026-10-19T00:00:00+00:00", "checker": "Head of Risk Models (seed)",
                     "checked_at": "2026-10-19T00:00:00+00:00", "reason": "R12 ladder (PLAN_R12 §1.5)"})
    return rows


# ------------------------------------------------------------------ the relations

_SEEDED: set[str] = set()


def ensure_seeded() -> None:
    """Publish the R12 seed once, without overwriting anything already there.

    Scenarios: a ladder row whose id is new is published as version 1; where the relation already holds that id from
    another set (Session E's seed of the R11 table), the ladder row is published as the next version; R11 scenarios the
    ladder replaces (construction_downturn, trading_slowdown, customer_loss, severe) get a retired version.
    Sensitivities: only (sensitivity, sector) pairs the relation does not hold yet are added, as version 1."""
    key = store.backend("dd_stress_scenario") + "|" + str(paths.VAR) + "|" + _root_tag()
    if key in _SEEDED:
        return
    _SEEDED.add(key)
    have = store.read("dd_stress_scenario")
    by: dict[str, list[dict[str, Any]]] = {}
    for r in have:
        by.setdefault(r["scenario_id"], []).append(r)
    add = []
    ladder_ids = set()
    for r in seed_ladder():
        ladder_ids.add(r["scenario_id"])
        prior = by.get(r["scenario_id"], [])
        if any(p.get("set_id") == SEED_VERSION for p in prior):
            continue
        add.append({**r, "version": max((int(p.get("version") or 1) for p in prior), default=0) + 1})
    for sid in R11_REPLACED:
        prior = by.get(sid, [])
        if prior and not any(p.get("status") == "retired" for p in prior):
            last = max(prior, key=lambda p: int(p.get("version") or 1))
            add.append({**last, "version": int(last.get("version") or 1) + 1, "status": "retired", "retire": True,
                        "set_id": SEED_VERSION, "maker": "Risk Models (seed)", "checker": "Head of Risk Models (seed)",
                        "reason": "Replaced by the R12 ladder (sector family and combined cases)",
                        "made_at": "2026-10-19T00:00:00+00:00", "checked_at": "2026-10-19T00:00:00+00:00"})
    if add:
        store.publish("dd_stress_scenario", add, actor="seed")
    hs = {(r["sensitivity_id"], r["sector"]) for r in store.read("dd_stress_sensitivity")}
    sadd = [r for r in seed_sensitivities() if (r["sensitivity_id"], r["sector"]) not in hs]
    if sadd:
        store.publish("dd_stress_sensitivity", sadd, actor="seed")


R11_REPLACED = ("construction_downturn", "trading_slowdown", "customer_loss", "severe")


def _root_tag() -> str:
    import os
    return os.environ.get("DEALDESK_R12_ROOT", "")


def _decode_scn(r: dict[str, Any]) -> dict[str, Any]:
    r = dict(r)
    r["shocks"] = store.decode(r.get("shocks")) or {}
    r["version"] = int(r.get("version") or 1)
    return r


def all_scenario_rows() -> list[dict[str, Any]]:
    ensure_seeded()
    return [_decode_scn(r) for r in store.read("dd_stress_scenario")]


def _latest(rows: list[dict[str, Any]], key) -> dict[Any, dict[str, Any]]:
    out: dict[Any, dict[str, Any]] = {}
    for r in rows:
        k = key(r)
        if k not in out or (r["version"], str(r.get("checked_at") or r.get("made_at") or "")) > (
                out[k]["version"], str(out[k].get("checked_at") or out[k].get("made_at") or "")):
            out[k] = r
    return out


def scenarios(proposal_id: str | None = None) -> list[dict[str, Any]]:
    """The ladder in force for a deal: the latest approved version of every bank scenario, plus the deal's own
    scenarios (deal scope: no checker needed). Retired scenarios (status retired) drop out."""
    rows = all_scenario_rows()
    bank = [r for r in rows if r.get("scope") == "bank" and r.get("status") in ("approved", "retired")]
    deal = [r for r in rows if r.get("scope") == "deal" and proposal_id and r.get("proposal_id") == proposal_id
            and r.get("status") in ("approved", "retired")]
    cur = list(_latest(bank, lambda r: r["scenario_id"]).values()) + list(_latest(deal, lambda r: r["scenario_id"]).values())
    cur = [r for r in cur if r.get("status") != "retired"]
    fam = [f for f, _ in FAMILIES]
    sev = {"mild": 0, "moderate": 1, "severe": 2}
    order = {r["scenario_id"]: i for i, r in enumerate(seed_ladder())}
    # by family, then the seed's sub-family order (oil mild, moderate, severe; then GDP ...); added scenarios after
    cur.sort(key=lambda r: (fam.index(r["family"]) if r["family"] in fam else len(fam), order.get(r["scenario_id"], 999),
                            sev.get(r["severity"], 3), r["scenario_id"]))
    return cur


def scenario(sid: str, proposal_id: str | None = None) -> dict[str, Any] | None:
    return next((r for r in scenarios(proposal_id) if r["scenario_id"] == sid), None)


# ------------------------------------------------------------------ sensitivities: the current version
#
# A version is an integer per (sensitivity, sector): the seed is 1, Session T's calibrations and approved expert
# overrides publish higher ones. The current value of a pair is its highest version; a run records the highest
# version it used. Pending overrides wait in the app's own store (`dd_stress_sensitivity_pending`), never in the
# relation.

def _sens_rows() -> list[dict[str, Any]]:
    ensure_seeded()
    return store.read("dd_stress_sensitivity")


def sensitivity_versions() -> list[dict[str, Any]]:
    by: dict[int, dict[str, Any]] = {}
    for r in _sens_rows():
        v = int(r["version"])
        e = by.setdefault(v, {"version": v, "status": "approved", "method": set(), "sources": set(), "published_at": None,
                              "published_by": r.get("published_by"), "rows": 0})
        e["rows"] += 1
        e["method"].add(r.get("method") or "expert")
        e["sources"].add(r.get("source") or "")
        if str(r.get("published_at") or "") > str(e["published_at"] or ""):
            e["published_at"] = r.get("published_at")
    pend: dict[str, dict[str, Any]] = {}
    for r in store.read("dd_stress_sensitivity_pending"):
        if r.get("status") != "pending_approval":
            continue
        e = pend.setdefault(str(r["version"]), {"version": r["version"], "status": "pending_approval", "method": {"expert override"},
                                                "sources": {r.get("source") or ""}, "published_at": None, "maker": r.get("maker"),
                                                "reason": r.get("reason"), "rows": 0})
        e["rows"] += 1
    out = [{**e, "method": sorted(e["method"]), "sources": sorted(x for x in e["sources"] if x)} for e in list(by.values()) + list(pend.values())]
    return sorted(out, key=lambda e: (e["status"] != "approved", str(e["version"])))


def current_sensitivity_version() -> int:
    vs = [int(r["version"]) for r in _sens_rows()]
    return max(vs) if vs else SENS_SEED_VERSION


class Sensitivities:
    """The values in force: for each (sensitivity, sector) its highest version (at most `version` when given)."""

    def __init__(self, version: int | str | None = None):
        cap = int(version) if version not in (None, "") else None
        self.rows: dict[tuple[str, str], dict[str, Any]] = {}
        for r in _sens_rows():
            v = int(r["version"])
            if cap is not None and v > cap:
                continue
            k = (r["sensitivity_id"], r["sector"])
            if k not in self.rows or v > int(self.rows[k]["version"]):
                self.rows[k] = r
        self.version = max((int(r["version"]) for r in self.rows.values()), default=SENS_SEED_VERSION)

    def get(self, sid: str, sector: str) -> dict[str, Any]:
        r = self.rows.get((sid, sector)) or self.rows.get((sid, "*"))
        if r is None:
            return {"sensitivity_id": sid, "sector": sector, "value": 0.0, "source": "not defined", "version": self.version,
                    "method": "none", "label": SENS_META.get(sid, (sid,))[0], "unit": "", "basis": "", "lower": None, "upper": None}
        lab, unit, basis = SENS_META.get(sid, (sid, "", ""))
        return {"label": lab, "unit": unit, "basis": basis, **{k: v for k, v in r.items() if v is not None},
                "value": float(r["value"]), "matched_sector": r["sector"], "lower": r.get("lower"), "upper": r.get("upper")}

    def label(self) -> str:
        return f"v{self.version}"

    def value(self, sid: str, sector: str) -> float:
        return float(self.get(sid, sector)["value"])


def catalogue(proposal_id: str | None = None) -> dict[str, Any]:
    sc = scenarios(proposal_id)
    return {"families": [{"id": f, "label": l} for f, l in FAMILIES], "severities": list(SEVERITIES),
            "scenarios": sc, "seed_version": SEED_VERSION, "sensitivity_version": current_sensitivity_version(),
            "sensitivity_versions": sensitivity_versions(), "backend": store.backend("dd_stress_scenario"),
            "shock_keys": SHOCK_KEYS}


SHOCK_KEYS = {
    "oil_pct": "Oil price change in % (−30 = Brent 30% below plan); revenue moves by the sector's oil beta.",
    "gdp_pct": "Non-oil GDP change in % (−3); revenue moves by the sector's GDP beta.",
    "sector_downturn": "Multiple of the obligor's own-sector downturn (0.5, 1, 1.5).",
    "revenue_pct": "Revenue change as a decimal (−0.2 = revenue 20% lower).",
    "ebitda_margin_bps": "EBITDA margin change in bps of revenue.",
    "customer_loss_share": "Share of the largest customer's revenue lost (1 = all).",
    "receivable_days": "Extra receivable days, funded with short-term debt.",
    "delay_months": "Project delay in months.",
    "rate_bps": "Benchmark rate change in bps.",
    "collateral_pct": "Change in every pledged item's value (decimal).",
    "real_estate_pct": "Real-estate price change in % (pledged real estate and real-estate revenue).",
    "notches": "Rating downgrade in notches, applied directly.",
    "guarantee_unenforceable": "The guarantee and credit insurance give no protection.",
    "compose": "A list of scenario ids applied together ('a|b' takes b where a does not apply).",
}
