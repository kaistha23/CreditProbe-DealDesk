"""The scenario recommender, conditioned on the current regime (R14 K12 (2), (3); PLAN_R14 §m (3), (4)).

    from backend.scenarios import recommend
    rec = recommend.recommend("corporate")     # {"regime", "revenue", "ideas", "text", "evidence"}

Rules (deterministic, N4):
  * Every answer opens with the current-regime block (`regime.block`).
  * In a high-oil regime (supply-shock, rising or high: `regime.is_high`) the first scenarios are the **conflict and trade
    disruption** (non-oil demand and revenue fall by sector, freight and input cost, payment delays from government and
    contractors, FX / liquidity) and the **oil reversal from today's level** sized on the post-spike reversals; an
    unconditional oil fall from the long-run average is never offered. When the revenue channel shows the book's stress
    comes from revenue (`revenue.by_sector()["revenue_led"]`), the revenue fall by sector leads.
  * Otherwise (normal, low or slump regime) the calibrated one-year severities from history apply (mild P75, moderate
    P92, severe), oil first only when the regime is normal.
Sizes: revenue fall by sector -> sector credit-cycle stress at the calibrated mild (turnover fall 10-20%) or moderate
(20% or more) severity (§S `sector_cycle`); non-oil GDP, SAIBOR, sector PD multiplier and rating at their calibrated
severities; oil reversal = today's level back to the pre-shock level, written against the What-If base path (the IMF
oil-price assumption), so the base path is not double counted. Every size names its source.
"""
from __future__ import annotations

from typing import Any

from backend.scenarios import regime, revenue

TRADE_SECTORS = ("Transport and Logistics", "Wholesale Trade", "Manufacturing", "Chemicals")
PAYMENT_SECTORS = ("Construction",)


def _cal() -> dict[str, dict[str, Any]]:
    from backend.scenarios import calibrate
    return calibrate.calibrate_all()


def _v(cal: dict, key: str, sev: str) -> float:
    return float(cal[key]["values"][sev])


def _r5(x: float) -> int:
    return int(round(x / 5.0) * 5)


def _base_path_oil(year: int) -> tuple[float | None, int]:
    """The What-If base-path Brent level in the year the reversal lands (the IMF assumption where the year is projected)."""
    from backend.whatif_v5.domain import mev
    a = mev.filled()
    y = year + 1 if (year + 1) in a.index else year
    return (float(a.loc[y, "brent"]) if y in a.index else None), y


def oil_reversal_idea(r: dict[str, Any], sev: str = "moderate") -> dict[str, Any]:
    rv = r["reversal"][sev]
    today = r["brent"]["latest"]["value"]
    base, y = _base_path_oil(int(r["as_of"][:4]))
    rel = (rv["to_usd"] / base - 1) * 100 if base else rv["fall_pct"]
    rel = round(min(-1.0, rel))
    hist = ", ".join(f"{h['label']} {h['fall_pct']:.0f}%" for h in r["reversal"]["history"])
    why = (f"Brent USD {today:.0f} → {rv['to_usd']:.0f} ({rv['fall_pct']:.0f}% from today; {rv['basis']}). Past post-spike "
           f"reversals: {hist}. The What-If base path already carries the IMF oil assumption (USD {base:.0f} in {y}), so the "
           f"shock against it is {rel:+.0f}%.") if base else f"Brent USD {today:.0f} → {rv['to_usd']:.0f} ({rv['basis']})."
    short = (f"{rv['fall_pct']:.0f}% from today, back to the pre-shock level; 2022–23 fell 39%"
             + (f"; {rel:+.0f}% against the IMF base path" if base else ""))
    return {"key": f"oil_reversal_{sev}", "label": f"Oil reversal: USD {today:.0f} → {rv['to_usd']:.0f}",
            "send": f"oil price {rel:g}%", "why": short, "detail": why, "family": "oil_reversal", "severity": sev,
            "sizes": {"from_usd": today, "to_usd": rv["to_usd"], "fall_from_today_pct": rv["fall_pct"],
                      "shock_vs_base_path_pct": rel, "base_path_usd": base, "base_path_year": y}}


def revenue_idea(rv: dict[str, Any], cal: dict, sev_scale: str = "") -> dict[str, Any] | None:
    falling = [x for x in rv["sectors"] if x["sector"] in rv["falling"]]
    if not falling:
        return None
    hard = [x["sector"] for x in falling if x["turnover_yoy_pct"] <= -20]
    soft = [x["sector"] for x in falling if x["turnover_yoy_pct"] > -20]
    mod, mild = _v(cal, "sector_cycle", "moderate"), _v(cal, "sector_cycle", "mild")
    nog = _v(cal, "gdp_nonoil", "mild")
    parts = []
    if hard:
        parts.append(f"sector stress +{mod:.2f}sd for {', '.join(hard)}")
    if soft:
        parts.append(f"sector stress +{mild:.2f}sd for {', '.join(soft)}")
    parts.append(f"non-oil GDP -{nog:.1f}pp")
    secs = "; ".join(f"{x['sector']} {x['turnover_yoy_pct']:+.0f}% (EAD SAR {x['ead_mn'] / 1000:,.1f}bn)" for x in falling)
    why = (f"Account turnover y/y ({rv['window']['turnover']}): {secs}. Sectors down 20% or more take the calibrated moderate "
           f"sector stress ({mod:.2f} sd), 10–20% the mild ({mild:.2f} sd); with the mild non-oil slowdown ({nog:.1f} pp, §S).")
    short = "Account turnover y/y: " + ", ".join(f"{x['sector']} {x['turnover_yoy_pct']:+.0f}%" for x in falling[:4])
    return {"key": "revenue_by_sector", "detail": why, "label": "Revenue fall by sector (" + ", ".join(x["sector"] for x in falling[:2])
            + (" …" if len(falling) > 2 else "") + ")", "send": " and ".join(parts), "why": short, "family": "revenue",
            "severity": "moderate", "sizes": {"sectors": [{"sector": x["sector"], "turnover_yoy_pct": x["turnover_yoy_pct"],
                                                         "stress_sd": mod if x["sector"] in hard else mild} for x in falling]}}


def trade_disruption_idea(rv: dict[str, Any], cal: dict) -> dict[str, Any]:
    pdm = _v(cal, "pd_multiplier", "moderate")
    pdp = round((pdm - 1) * 100)
    rate = _r5(_v(cal, "saibor", "moderate"))
    exist = {x["sector"] for x in rv["sectors"]}
    trade = [s for s in TRADE_SECTORS if s in exist]
    pay = [s for s in PAYMENT_SECTORS if s in exist]
    parts = [f"PD +{pdp}% for {', '.join(trade)}"] if trade else []
    if pay:
        parts.append(f"downgrade by 1 notch for {', '.join(pay)}")
    parts.append(f"rates +{rate}bps")
    why = (f"Export-route and shipping disruption: freight and input costs on trade-exposed sectors (sector PD ×{pdm:.2f}, the "
           f"bank's own P92 one-year move), payment delays from government and contractors (Construction 1 notch; receivable "
           f"days are a Stress Lab lever, not a What-If one), FX / liquidity tightening (SAIBOR +{rate} bps, P92 since 2007).")
    short = "Freight and input costs, payment delays from government and contractors, FX / liquidity"
    return {"key": "trade_disruption", "label": "Conflict and trade disruption", "send": " and ".join(parts), "why": short,
            "detail": why,
            "family": "trade_disruption", "severity": "moderate",
            "sizes": {"pd_multiplier": pdm, "rate_bps": rate, "sectors": trade, "payment_delay_sectors": pay}}


def severe_disruption_idea(rv: dict[str, Any], cal: dict, r: dict[str, Any]) -> dict[str, Any]:
    sev = _v(cal, "sector_cycle", "severe")
    nog = _v(cal, "gdp_nonoil", "moderate")
    rate = _r5(_v(cal, "saibor", "severe"))
    secs = rv["falling"] or ["Construction", "Real Estate"]
    return {"key": "disruption_severe", "label": "Severe: the disruption deepens",
            "send": f"sector stress +{sev:.2f}sd for {', '.join(secs)} and non-oil GDP -{nog:.1f}pp and rates +{rate}bps",
            "why": "The disruption lasts past the IMF's March 2027 reopening assumption",
            "detail": (f"The disruption lasts past the IMF's March 2027 reopening assumption: the falling-revenue sectors at the "
                    f"calibrated severe sector stress ({sev:.2f} sd), the moderate non-oil slowdown ({nog:.1f} pp) and SAIBOR "
                    f"+{rate} bps (severe)."),
            "family": "trade_disruption", "severity": "severe", "sizes": {"stress_sd": sev, "gdp_nonoil_pp": nog, "rate_bps": rate}}


def history_ideas(cal: dict, top: str) -> list[dict[str, Any]]:
    """Normal regime: the calibrated one-year severities from history (oil and GDP moved together, J5)."""
    b = {s: round(_v(cal, "brent", s)) for s in ("mild", "moderate", "severe")}
    g = {s: _v(cal, "gdp_nonoil", s) for s in ("mild", "moderate")}
    return [
        {"key": "hist_mild", "label": f"Mild: oil -{b['mild']}%, non-oil GDP -{g['mild']:.1f}pp",
         "send": f"oil price -{b['mild']}% and non-oil GDP -{g['mild']:.1f}pp", "why": "the calibrated mild year (P75, §S)",
         "family": "oil_fall", "severity": "mild"},
        {"key": "hist_moderate", "label": f"Moderate: oil -{b['moderate']}%, non-oil GDP -{g['moderate']:.1f}pp",
         "send": f"oil price -{b['moderate']}% and non-oil GDP -{g['moderate']:.1f}pp", "why": "the calibrated moderate year (P92, §S)",
         "family": "oil_fall", "severity": "moderate"},
        {"key": "sector_severe", "label": f"Severe {top} stress", "send": f"severe stress in the {top} sector and PD +25% for {top}",
         "why": "the largest ECL sector", "family": "sector", "severity": "severe"},
        {"key": "credit_drift", "label": "1-notch downgrade, LGD +3pp", "send": "downgrade by 1 notch and LGD +3pp",
         "why": "a broad credit drift", "family": "rating", "severity": "mild"},
    ]


def corporate_ideas(r: dict[str, Any], rv: dict[str, Any], top: str) -> list[dict[str, Any]]:
    cal = _cal()
    if not regime.is_high(r):
        ideas = history_ideas(cal, top)
        if r["regime"] in ("oil_slump", "low_oil"):
            ideas = ideas[2:] + ideas[:2]      # oil has already fallen: credit and sector drivers first
        rev = revenue_idea(rv, cal)
        if rev and rv["revenue_led"]:
            ideas.insert(0, rev)
        return ideas
    ideas: list[dict[str, Any]] = []
    rev = revenue_idea(rv, cal)
    trade = trade_disruption_idea(rv, cal)
    if rev and rv["revenue_led"]:
        ideas += [rev, trade]
    else:
        ideas += [trade] + ([rev] if rev else [])
    ideas.append(oil_reversal_idea(r, "moderate"))
    ideas.append(severe_disruption_idea(rv, cal, r))
    return ideas


def retail_ideas(r: dict[str, Any]) -> list[dict[str, Any]]:
    cal = _cal()
    rate = _r5(_v(cal, "saibor", "moderate"))
    ideas = [{"key": "rates", "label": f"Rates +{rate}bps", "send": f"rates +{rate}bps",
              "why": "FX / liquidity tightening (SAIBOR P92 since 2007)", "family": "rates", "severity": "moderate"},
             {"key": "unemployment", "label": "Unemployment +1pp", "send": "unemployment +1pp", "why": "non-oil demand falls",
              "family": "labour", "severity": "mild"}]
    if regime.is_high(r):
        ideas.insert(0, {"key": "disruption_retail", "label": "Trade disruption: jobs and prices",
                         "send": f"unemployment +2pp and rates +{rate}bps",
                         "why": "conflict and trade disruption hit private-sector jobs and funding costs", "family": "trade_disruption",
                         "severity": "moderate"})
        ideas.append(oil_reversal_idea(r, "moderate"))
    else:
        ideas.append({"key": "recession", "label": "Recession", "send": "recession with unemployment up 2pp and oil -30%",
                      "why": "a 2020-type year", "family": "recession", "severity": "severe"})
    ideas.append({"key": "house_prices", "label": "House prices -20%", "send": "house prices -20% and mortgage LGD +5pp",
                  "why": "real-estate correction (expert size: 11 annual index moves)", "family": "collateral", "severity": "moderate"})
    return ideas


def recommend(domain: str = "corporate", top: str = "Construction") -> dict[str, Any]:
    r = regime.current()
    rv = revenue.by_sector()
    ideas = corporate_ideas(r, rv, top) if domain == "corporate" else retail_ideas(r)
    lead = ideas[0]
    intro = ("**What I would run first, given today's regime.** " if regime.is_high(r)
             else "**Scenarios calibrated on history.** ")
    order = "; ".join(f"{i + 1}. {x['label']}" for i, x in enumerate(ideas[:4]))
    body = "\n\n".join(x for x in [revenue.summary_line(rv) if domain == "corporate" else "",
                                   intro + order + f". The first: {lead.get('detail') or lead['why']}"] if x)
    text = regime.markdown(r) + "\n\n" + body
    ev = {"regime": r["regime"], "regime_label": r["label"], "brent_usd": r["brent"]["latest"]["value"],
          "brent_date": r["brent"]["latest"]["date"], "brent_12m_pct": r["brent"]["change_12m_pct"],
          "brent_3m_pct": r["brent"]["change_3m_pct"], "brent_percentile_35y": r["brent"]["percentile_35y"],
          "revenue_led": rv["revenue_led"], "falling_sectors": rv["falling"], "falling_ead_share_pct": rv["falling_ead_share_pct"],
          "first_idea": lead["key"], "vintage": r["vintage_line"]}
    return {"regime": regime.block(r), "revenue": rv, "ideas": ideas, "text": text, "body": body, "evidence": ev}


def first_is_unconditional_oil_fall(rec: dict[str, Any]) -> bool:
    """The K12 test predicate: the lead idea is an oil fall from the history (not a reversal from today's level)."""
    return rec["ideas"][0].get("family") == "oil_fall"
