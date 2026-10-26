"""The What-If domain for the shared conversational layer (backend/convo, PLAN_R4 A1).

Questions in a What-If thread are answered by the forked Cockpit agent on this
domain: the What-If facility/account data at the thread's period (or its Early
Warning cohort), its 20-period history, the MEV store and its scenario paths,
the scenario library, the last result of the thread, and the method notes. The
scenario engine is a tool: the agent can read a statement into shocks (a
proposal), recompute the thread's last result, measure the collateral LGD
channel and check likelihood, but it never executes a scenario. Execution
happens only on the Execute button or an explicit "execute" / "run it"
(orchestrator.Turn.on_execute).
"""
from __future__ import annotations

import functools
import re
from typing import Any

import numpy as np
import pandas as pd

from backend.convo.spec import Domain, Plan, PlanStep, Relation, Tool, ToolContext, ToolResult
from backend.whatif_v5 import likelihood
from backend.whatif_v5.chat import language
from backend.whatif_v5.domain import mev, store as dstore
from backend.whatif_v5.models import cards, engine, runner
from backend.whatif_v5.models.scenario import DRIVER_LABELS, Scenario, describe_shocks

COLS = ["exposure_id", "owner_id", "owner_name", "segment", "subsegment", "product", "stage", "dpd", "grade", "nfo",
        "behaviour_score", "collateral_type", "collateral_value", "haircut_pct", "collateral_allocated", "secured_share",
        "limit", "drawn", "undrawn", "ead", "ccf", "pd_ttc", "pd_12m", "pd_lifetime", "lgd_pct_book", "ecl_12m",
        "ecl_lifetime", "ecl_final"]
COLUMN_NOTES = {
    "exposure_id": "facility (corporate) or account (retail) ID, as in the books", "owner_id": "borrower or customer ID",
    "segment": "sector (corporate) or product (retail)", "stage": "IFRS 9 stage 1/2/3", "dpd": "days past due",
    "grade": "rating grade (corporate) or score band (retail)", "nfo": "notches below the rating at origination",
    "collateral_value": "collateral market value, SAR mn", "haircut_pct": "collateral haircut, %",
    "collateral_allocated": "haircut-adjusted collateral allocated to this exposure, capped at EAD, SAR mn",
    "secured_share": "collateral_allocated / EAD (0-1)", "ead": "exposure at default, SAR mn",
    "ccf": "credit conversion factor (0-1)", "pd_12m": "scenario-weighted 12-month PD (0-1)",
    "pd_lifetime": "scenario-weighted lifetime PD (0-1)", "lgd_pct_book": "the book's LGD, %",
    "ecl_final": "reported ECL, SAR mn (12-month for Stage 1, lifetime for Stages 2-3)",
    "limit": "SAR mn", "drawn": "SAR mn", "undrawn": "SAR mn"}


def _scope(scope: dict[str, Any]) -> tuple[str, str, str]:
    book = scope.get("domain") or "corporate"
    return book, scope.get("period") or dstore.as_of(book), scope.get("cohort_id") or ""


def _exposures(scope: dict[str, Any]) -> pd.DataFrame:
    book, period, cohort = _scope(scope)
    f = dstore.frame(book, period)
    if cohort:
        sc = Scenario(domain=book, period=period, steps=[], cohort_id=cohort)
        mask, _ = runner.population(sc, f)
        f = f[mask]
    return f[[c for c in COLS if c in f.columns]].reset_index(drop=True)


@functools.lru_cache(maxsize=4)
def _history(book: str) -> pd.DataFrame:
    h = dstore.history(book, ["segment", "stage", "ead", "ecl_final", "pd_12m", "lgd_pct_book", "secured_share", "dpd"])
    h["w_pd"] = h["pd_12m"] * h["ead"]
    h["w_lgd"] = h["lgd_pct_book"] * h["ead"]
    g = h.groupby(["period", "segment"])
    out = pd.DataFrame({
        "exposures": g.size(), "ead": g["ead"].sum(), "ecl": g["ecl_final"].sum(),
        "stage1": g["stage"].apply(lambda s: int((s == 1).sum())), "stage2": g["stage"].apply(lambda s: int((s == 2).sum())),
        "stage3": g["stage"].apply(lambda s: int((s == 3).sum())),
        "pd_12m_avg": g["w_pd"].sum() / g["ead"].sum(), "lgd_avg_pct": g["w_lgd"].sum() / g["ead"].sum()}).reset_index()
    return out


@functools.lru_cache(maxsize=1)
def _mev_history() -> pd.DataFrame:
    t = mev.annual_table()
    t = t.assign(name=t["series"].map(lambda k: mev.BY_KEY[k].name),
                 unit=t["series"].map(lambda k: getattr(mev.BY_KEY[k], "unit", "") or ""))
    return t[["series", "name", "year", "kind", "value", "unit"]].reset_index(drop=True)


def _mev_paths(scope: dict[str, Any]) -> pd.DataFrame:
    book, period, _ = _scope(scope)
    sy = int(np.floor(mev.period_year_fraction(period) + 0.5))
    p = mev.paths_from(sy)
    rows = []
    for s in ("base", "upturn", "downturn"):
        lv = p[s]
        for year, r in lv.iterrows():
            for k, v in r.items():
                if pd.notna(v):
                    rows.append({"scenario": s, "weight": mev.WEIGHTS[s], "year": int(year), "series": k,
                                 "name": mev.BY_KEY[k].name, "value": float(v)})
    return pd.DataFrame(rows)


def relations(scope: dict[str, Any]) -> list[Relation]:
    book, period, cohort = _scope(scope)
    lab = runner.LABELS[book]
    pop = f"Early Warning cohort {cohort}" if cohort else f"the {lab['book'].lower()} book"
    return [
        Relation("exposures", f"One row per {lab['exposure'].lower()} of {pop} at {period}: IFRS 9 inputs, collateral, "
                              "EAD and reported ECL (the What-If domain, equal to the books)", _exposures,
                 grain=lab["exposure"].lower(), columns=COLUMN_NOTES),
        Relation("history", f"{lab['book']} book by period and {lab['segment'].lower()} over all "
                            f"{len(dstore.periods(book))} periods: exposures, EAD, ECL, stage counts, EAD-weighted "
                            "12-month PD and LGD", lambda s: _history(_scope(s)[0]), grain="period x segment",
                 columns={"ead": "SAR mn", "ecl": "SAR mn", "pd_12m_avg": "0-1", "lgd_avg_pct": "%"}),
        Relation("mev_history", "Saudi macroeconomic variables, annual since 1990 (history) and IMF projections",
                 lambda s: _mev_history(), grain="series x year",
                 columns={"kind": "history | projection", "value": "in the series unit"}),
        Relation("mev_paths", "The base / upturn / downturn MEV paths (weights 50/20/30) for the next 5 years",
                 _mev_paths, grain="scenario x year x series"),
    ]


# ------------------------------------------------------------------ tools

def _scenario_of(state: dict[str, Any], which: str = "any") -> Scenario | None:
    d = state.get("pending") if which in ("any", "pending") else None
    d = d or (state.get("scenario") if which in ("any", "current") else None)
    return Scenario.from_dict(d) if d else None


def _vocab(book: str) -> dict[str, list[str]]:
    f = dstore.frame(book)
    return {"segments": sorted(f["segment"].astype(str).unique()), "subsegments": sorted(f["subsegment"].astype(str).unique())}


def proposal_block(sc: Scenario, assumptions: list[str], unread: list[str], method: str | None, population: str,
                   kind: str = "new") -> dict[str, Any]:
    lab = runner.LABELS[sc.domain]
    return {"type": "proposal", "kind": kind, "population": population,
            "steps": [{"restatement": "; ".join(describe_shocks(s.shocks, lab)) + f" on {s.scope.describe(lab)}",
                       "shocks": s.shocks.to_dict(), "scope": s.scope.to_dict(),
                       "levers": sorted(s.shocks.drivers()) + ([f"{s.shocks.horizon}y horizon"] if s.shocks.horizon else [])}
                      for s in sc.steps],
            "assumptions": assumptions, "unread": unread,
            "method": {"delta": "Delta method", "xgboost": "XGBoost"}.get(method or "", ""),
            "needs_method": not method}


def t_propose(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    book, period, cohort = _scope(ctx.scope)
    v = _vocab(book)
    r = language.read(str(args.get("statement") or ctx.question),
                      {"domain": book, **v, "labels": runner.LABELS[book], "has_scenario": False})
    if not r.steps:
        return ToolResult(summary="No shock could be read from the statement.", data={"unread": r.unread})
    sc = Scenario(domain=book, period=period, steps=r.steps, cohort_id=cohort)
    method = r.method or ctx.state.get("method")
    block = proposal_block(sc, r.assumptions, r.unread, method, _population(ctx.scope))
    return ToolResult(summary="Proposal: " + " | ".join(s["restatement"] for s in block["steps"]),
                      data={"steps": block["steps"], "assumptions": r.assumptions, "unread": r.unread,
                            "method": method or "not chosen", "executes_on": "the Execute button or 'run it'"},
                      blocks=[block], state={"pending": sc.to_dict(), **({"method": r.method} if r.method else {})})


def _population(scope: dict[str, Any]) -> str:
    book, period, cohort = _scope(scope)
    return f"the Early Warning cohort {cohort}" if cohort else f"the {runner.LABELS[book]['book'].lower()} book"


def collateral_rows(book: str, f: pd.DataFrame, coll_pct: float, hair_pp: float, by: str = "collateral_type") -> tuple[list[dict], dict]:
    n = len(f)
    ch = engine.collateral_channel(book, f, np.full(n, coll_pct), np.full(n, hair_pp), dstore.frame(book))
    live = f["stage"].to_numpy() < 3
    d = pd.DataFrame({by: f[by].to_numpy(), "ead": f["ead"].to_numpy(float), "mv": f["collateral_value"].to_numpy(float),
                      "c0": ch["c0"], "c1": ch["c1"], "haircut": f["haircut_pct"].to_numpy(float),
                      "s0": ch["s0"], "s1": ch["s1"], "dlgd": ch["dlgd"], "lgd": f["lgd_pct_book"].to_numpy(float) / 100,
                      "live": live})
    rows = []
    for k, g in d.groupby(by):
        e = g["ead"].sum()
        if e <= 0:
            continue
        w = g["ead"] / e
        rows.append({by: k, "exposures": int(len(g)), "ead_sar_mn": round(float(e), 1),
                     "haircut_pct": round(float((g["haircut"] * w).sum()), 1),
                     "collateral_before_sar_mn": round(float(g["c0"].sum()), 1),
                     "collateral_after_sar_mn": round(float(g["c1"].sum()), 1),
                     "secured_share_before_pct": round(float(g["c0"].sum() / e * 100), 1),
                     "secured_share_after_pct": round(float(g["c1"].sum() / e * 100), 1),
                     "lgd_before_pct": round(float((g["lgd"] * w).sum() * 100), 1),
                     "lgd_change_pp": round(float((g["dlgd"] * w).sum() * 100), 2),
                     "lgd_after_pct": round(float(((g["lgd"] + g["dlgd"]).clip(0, 1) * w).sum() * 100), 1)})
    rows.sort(key=lambda r: -r["ead_sar_mn"])
    e = float(d["ead"].sum())
    tot = {"exposures": int(n), "ead_sar_mn": round(e, 1), "unsecured_lgd_pct": round(ch["lgd_u"] * 100, 1),
           "collateral_before_sar_mn": round(float(d["c0"].sum()), 1), "collateral_after_sar_mn": round(float(d["c1"].sum()), 1),
           "secured_share_before_pct": round(float(d["c0"].sum() / e * 100), 1) if e else 0.0,
           "secured_share_after_pct": round(float(d["c1"].sum() / e * 100), 1) if e else 0.0,
           "lgd_change_pp": round(float((d["dlgd"] * d["ead"]).sum() / e * 100), 2) if e else 0.0,
           "collateral_pct": coll_pct, "haircut_pp": hair_pp}
    return rows, tot


def t_collateral(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    book, period, _ = _scope(ctx.scope)
    sc = _scenario_of(ctx.state)
    coll = args.get("collateral_pct")
    hair = args.get("haircut_pp")
    if coll is None and hair is None:
        if sc is not None:
            coll = sum(s.shocks.collateral for s in sc.steps)
            hair = sum(s.shocks.haircut for s in sc.steps)
        if not coll and not hair:
            coll = -20.0
    coll, hair = float(coll or 0.0), float(hair or 0.0)
    f = _exposures(ctx.scope)
    seg = str(args.get("segment") or "")
    if seg:
        f = f[(f["segment"] == seg) | (f["subsegment"] == seg)]
    rows, tot = collateral_rows(book, f, coll, hair)
    return ToolResult(summary=(f"Collateral channel for collateral value {coll:+g}% and haircut {hair:+g}pp on "
                               f"{_population(ctx.scope)}{' (' + seg + ')' if seg else ''} at {period}"),
                      data={"formula": "dLGD = LGD_unsecured x (s0 - s1); s = min(EAD, cover x (1+dC)(1-h-dh)/(1-h)) / EAD",
                            "totals": tot}, rows=rows)


def t_last_result(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    sc = _scenario_of(ctx.state, "current")
    method = (ctx.state.get("last") or {}).get("method") or ctx.state.get("method")
    if sc is None or not method:
        return ToolResult(summary="This thread has no executed scenario yet.", data={"executed": False})
    r = runner.run(sc, method)
    c = r["cards"]
    bars = [{"driver": b["label"], "sar_mn": round(b["value"], 2)} for b in r["waterfall"] if b["kind"] == "driver"
            and b.get("active")]
    segs = sorted(r["by_segment"], key=lambda x: -abs(x["change"]))[:10]
    return ToolResult(summary=f"Last result ({r['method_name']}): " + "; ".join(s["restatement"] for s in r["steps"]),
                      data={"method": r["method_name"], "reported_ecl_sar_mn": round(c["reported_ecl"], 2),
                            "start_ecl_sar_mn": round(c["start_ecl"], 2), "scenario_ecl_sar_mn": round(c["scenario_ecl"], 2),
                            "change_sar_mn": round(c["change"], 2), "change_pct": round(c["change_pct"], 2),
                            "coverage_before_pct": round(c["coverage_before"], 3), "coverage_after_pct": round(c["coverage_after"], 3),
                            "stage_moves": c["moves"], "drivers": bars,
                            "reconciles": r["reconciliation"]["reconciles"]},
                      rows=[{"segment": s["segment"], "change_sar_mn": round(s["change"], 2)} for s in segs])


def t_likelihood(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    sc = _scenario_of(ctx.state)
    if sc is None:
        return ToolResult(summary="No scenario in the thread to assess.", data={})
    lik = likelihood.assess(sc)
    return ToolResult(summary=lik.get("label", ""), data={"label": lik.get("label"), "items": lik.get("items", [])[:6]},
                      blocks=[{"type": "likelihood", **lik}])


def t_model_card(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    book, _, _ = _scope(ctx.scope)
    m = "xgboost" if str(args.get("method", "")).lower().startswith("x") else "delta"
    card = cards.card(book, m)
    keep = {k: card[k] for k in list(card)[:12] if isinstance(card[k], (str, int, float, list, dict))}
    return ToolResult(summary=f"Model card: {card.get('name', m)}", data=_trim(keep))


def _trim(x: Any, depth: int = 0) -> Any:
    if isinstance(x, dict):
        return {k: _trim(v, depth + 1) for k, v in list(x.items())[:25]}
    if isinstance(x, list):
        return [_trim(v, depth + 1) for v in x[:15]]
    if isinstance(x, str):
        return x[:600]
    return x


def t_ideas(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    from backend.whatif_v5.chat import orchestrator
    book, period, cohort = _scope(ctx.scope)
    ideas = orchestrator.brainstorm({"domain": book, "period": period, "cohort_id": cohort})
    return ToolResult(summary="Scenario ideas conditioned on the current regime", data={"evidence": ideas["evidence"],
                                                                                       "ideas": ideas["ideas"], "domain": book},
                      blocks=[b for b in (ideas.get("regime"),) if b] + [{"type": "ideas", "ideas": ideas["ideas"]}])


TOOLS = [
    Tool("scenario_ideas", "Mild, historical and severe scenario ideas for this book, calibrated on the worst moves in "
         "the MEV and rating history (shown as chips the user can turn into proposals).",
         {"type": "object", "properties": {}}, t_ideas, message="Calibrating ideas on history"),
    Tool("propose_scenario", "Read a scenario statement into structured shocks (levers: PD, LGD, collateral value, "
         "haircut, CCF/EAD, rating, sector stress, MEV, stage moves) with its scope. Publishes a proposal the user "
         "executes with the Execute button; it does NOT run the scenario.",
         {"type": "object", "required": ["statement"], "properties": {"statement": {"type": "string"}}}, t_propose,
         message="Reading the statement into shocks"),
    Tool("collateral_mechanics", "The collateral-to-LGD channel on this book: secured share before/after and the LGD "
         "change by collateral type for a collateral value move (%) and/or haircut move (pp). Defaults to the thread's "
         "scenario, else collateral -20%.",
         {"type": "object", "properties": {"collateral_pct": {"type": "number"}, "haircut_pp": {"type": "number"},
                                           "segment": {"type": "string"}}}, t_collateral,
         message="Measuring the collateral LGD channel"),
    Tool("last_result", "The thread's last executed scenario result: ECL before/after, Shapley drivers, stage moves, "
         "change by segment.", {"type": "object", "properties": {}}, t_last_result, message="Reading the last result"),
    Tool("assess_likelihood", "Check the thread's scenario against the book's and the MEVs' own history.",
         {"type": "object", "properties": {}}, t_likelihood, message="Checking history"),
    Tool("model_card", "The Delta or XGBoost model card (method, validation, limitations).",
         {"type": "object", "properties": {"method": {"type": "string", "enum": ["delta", "xgboost"]}}}, t_model_card,
         message="Reading the model card"),
]

# ------------------------------------------------------------------ knowledge

KNOWLEDGE = {
    "collateral_lgd": (
        "Collateral and LGD in What-If. Collateral value and haircut are their own levers, separate from LGD. "
        "Per exposure: allocated collateral C0 is the haircut-adjusted collateral value, capped at EAD; secured share "
        "s0 = C0 / EAD. A collateral value move dC (e.g. -20%) and a haircut move dh (pp) change the haircut-adjusted "
        "cover by k = (1 + dC) x (1 - h - dh) / (1 - h), so C1 = min(EAD, cover0 x k), where cover0 is C0, or the full "
        "haircut-adjusted value MV x (1 - h) when C0 is capped at EAD (over-collateralised exposures absorb part of "
        "the fall). The newly unsecured slice (s0 - s1) loses at the unsecured LGD: dLGD = LGD_unsecured x (s0 - s1), "
        f"added to every scenario and year of the LGD term structure. LGD_unsecured is {engine.CORP_UNSECURED_LGD * 100:.0f}% "
        "for corporate (the foundation-IRB senior unsecured LGD; the corporate book holds no unsecured facilities to "
        "measure one on) and, for retail, the EAD-weighted LGD of the book's unsecured accounts. With no shock C1 = C0 "
        "and LGD is unchanged. Both methods (Delta and XGBoost) apply the same channel, because the book's LGD history "
        "does not identify a collateral elasticity. The waterfall shows it as its own Collateral bar. Real-estate "
        "price shocks (an MEV) move real-estate collateral through the same idea: LGD x (1 - secured share x price move). "
        "An earlier reading of 'reduce collateral by 20%' as 'LGD +20%' was a parser error: it is now a collateral shock."),
    "delta_method": (
        "Delta method: starts from the stored PD and LGD term structures (3 scenarios x 5 years) so its starting ECL "
        "equals the reported ECL exactly. PD shocks move every annual hazard (relative %, pp or bps); LGD shocks add pp "
        "or scale; CCF shocks move EAD through the undrawn amount; rating notches scale hazards by the masterscale "
        "TTC PD ratio of the new grade; sector stress and MEVs shift the credit-cycle index Z and every hazard as "
        "Phi(Phi^-1(h) - sqrt(rho/(1-rho)) dZ), with downturn LGD x (1 - 0.10 dZ); then staging is re-assessed."),
    "xgboost": (
        "XGBoost: models for PIT PD by scenario and year (log-odds with the bank's 12-month PD as offset) and LGD, "
        "trained on the What-If domain's 20 periods, random and out-of-time 70/30 splits, fixed seed, sealed model "
        "files. A scenario changes the features (grade, notches, TTC PD, cycle index from the MEVs) and the models "
        "predict; the starting ECL recomputed by the model is shown next to the reported one (model error)."),
    "waterfall": (
        "The waterfall: reported ECL -> starting ECL recomputed by the chosen model -> one bar per driver (PD, LGD, "
        "Collateral, CCF/EAD, Staging, Rating, Sector, Macro) -> scenario ECL. Driver bars are exact Shapley values "
        "over the drivers the scenario uses (2^k evaluations): order-neutral, a driver that did not move is exactly "
        "0, and the bars add up to the change to floating-point precision."),
    "staging": (
        f"Staging after a shock: Stage 3 at DPD >= 90 or default; Stage 2 at DPD >= 30, rating CCC/CC, "
        f"{engine.CORP_SICR_NOTCHES}+ notches below origination (corporate) or behaviour score below "
        f"{engine.RETAIL_SCORE_FLOOR:.0f} (retail, {engine.RETAIL_BAND_WIDTH:.0f} points per band); plus Rule B: the "
        f"12-month PD at least x{engine.RULE_B_RATIO:g} its starting value and at least "
        f"+{engine.RULE_B_FLOOR * 100:.1f}pp. A shock never cures a stage."),
    "scenario_weights": (
        f"ECL is the weighted average over three macro scenarios: base {mev.WEIGHTS['base'] * 100:.0f}%, upturn "
        f"{mev.WEIGHTS['upturn'] * 100:.0f}%, downturn {mev.WEIGHTS['downturn'] * 100:.0f}%, each with 5-year MEV paths "
        "(base = IMF WEO projections; upturn/downturn = base +/- a historical-volatility shock calibrated on 1990-2025)."),
    "how_whatif_works": (
        "How What-If works: describe a change in plain words; the assistant restates it as structured shocks with "
        "their scope (a proposal). Nothing runs until you press Execute scenario or say 'execute' / 'run it'; it then "
        "asks Delta or XGBoost if you have not chosen. The result shows ECL before and after, the Shapley waterfall, "
        "staging moves, segments, likelihood against history and a checked commentary. Follow-ups: 'also ...' stacks a "
        "step, 'instead ...' starts a new scenario, 'make it 1.5x more severe', 'rerun with XGBoost', 'compare both "
        "models', 'undo', 'save'. Questions about the data, the models or a result are answered from real queries."),
    "levers": (
        "Distinct levers: PD (relative %, pp, bps), LGD (pp or relative %), collateral value (% of market value), "
        "haircut (pp), CCF (pp or relative) and EAD (%), rating (notches; retail score bands), sector stress (sd of "
        "the cycle index), MEVs (Brent %, GDP pp, unemployment pp, repo/SAIBOR bps, real-estate prices %, ...), and "
        "stage migrations (share of a stage moved)."),
}


# ------------------------------------------------------------------ the deterministic planner

def _money(v: float) -> str:
    a = abs(v)
    s = "-" if v < 0 else ""
    return f"{s}SAR {a / 1000:,.2f}bn" if a >= 1000 else f"{s}SAR {a:,.1f}m"


MEV_WORDS = {"gdp_nonoil": r"non[- ]?oil", "brent": r"\b(oil|brent|crude)\b", "gdp_real": r"\bgdp\b|economic growth",
             "cpi": r"inflation|\bcpi\b", "unemployment": r"unemployment|jobless", "saibor_3m": r"saibor",
             "repo": r"\brepo\b|policy rate|interest rate", "gov_spend": r"government (spending|expenditure)",
             "re_price": r"(real estate|property|house|housing) prices?", "current_account": r"current account",
             "credit_growth": r"credit growth|lending growth"}


def planner(q: str, ctx: ToolContext) -> Plan:
    low = q.lower()
    book, period, _ = _scope(ctx.scope)
    lab = runner.LABELS[book]
    pend = _scenario_of(ctx.state, "pending")
    if pend is not None and re.search(r"lever|flow|how will|what will|how would|explain (the|this) (proposal|scenario)", low):
        drivers = pend.drivers()
        topics = (["collateral_lgd"] if "collateral" in drivers else []) + \
            (["delta_method"] if drivers & {"pd", "lgd", "ccf", "rating", "sector", "mev"} else []) + \
            (["scenario_weights"] if "mev" in drivers else []) + ["staging", "waterfall"]
        cstep = next((s for s in pend.steps if s.shocks.collateral or s.shocks.haircut), None)
        seg = (cstep.scope.segments or cstep.scope.subsegments or [""])[0] if cstep else ""
        steps = ([PlanStep("collateral_mechanics", {"segment": seg} if seg else {})] if "collateral" in drivers else []) + \
            [PlanStep("read_knowledge", {"topic": t}) for t in topics]
        return Plan(steps, lambda res: _write_levers(res, pend, book, period))
    if re.search(r"collateral|haircut|secured", low):
        return Plan([PlanStep("collateral_mechanics", {}), PlanStep("read_knowledge", {"topic": "collateral_lgd"})],
                    lambda res: _write_collateral(res, book, period))
    if re.search(r"\b(why|what drove|drivers?|explain|break.?down|waterfall|walk me through)\b", low) and \
            ctx.state.get("scenario"):
        return Plan([PlanStep("last_result", {}), PlanStep("read_knowledge", {"topic": "waterfall"})], _write_last)
    if re.search(r"how likely|likelihood|plausib|ever happened", low):
        if _scenario_of(ctx.state) is None:
            return Plan([], lambda res: {"markdown": "There is no scenario in this thread yet. Describe one and I will "
                                                     "check it against the book's and the MEVs' own history."})
        return Plan([PlanStep("assess_likelihood", {})],
                    lambda res: {"markdown": f"**Likelihood.** {res[0]['out'].get('summary', '')}"})
    if re.search(r"brainstorm|ideas?|suggest|what (scenario|stress)|propose|severe should|realistic scenario", low):
        return Plan([PlanStep("scenario_ideas", {})],
                    lambda res: {"markdown": orchestrator_text(res[0]["out"].get("data") or {}, lab)})
    if re.search(r"how does|how do i|what can|help|how to use|work\b", low):
        return Plan([PlanStep("read_knowledge", {"topic": "how_whatif_works"}), PlanStep("read_knowledge", {"topic": "levers"})],
                    lambda res: {"markdown": res[0]["out"].get("text", "") + "\n\n" + res[1]["out"].get("text", "")})
    m = next((k for k, pat in MEV_WORDS.items() if re.search(pat, low)), "")
    if m or re.search(r"\b(mev|macro)", low):
        key = m or "brent"
        sql = (f"SELECT year, value FROM mev_history WHERE series = '{key}' AND kind = 'history' ORDER BY year")
        return Plan([PlanStep("run_query", {"sql": sql, "purpose": f"{mev.BY_KEY[key].name} history"})],
                    lambda res: _write_mev(res, key))
    if re.search(r"\b(model|delta|xgboost|xgb)\b", low):
        meth = "xgboost" if re.search(r"xgb|xgboost", low) else "delta"
        return Plan([PlanStep("read_knowledge", {"topic": "xgboost" if meth == "xgboost" else "delta_method"}),
                     PlanStep("model_card", {"method": meth})],
                    lambda res: {"markdown": res[0]["out"].get("text", "")})
    sql = ("SELECT segment, COUNT(*) AS exposures, SUM(ead) AS ead_sar_mn, SUM(ecl_final) AS ecl_sar_mn, "
           "SUM(ecl_final) / NULLIF(SUM(ead), 0) * 100 AS coverage_pct, "
           "SUM(CASE WHEN stage = 2 THEN ead ELSE 0 END) / NULLIF(SUM(ead), 0) * 100 AS stage2_ead_pct "
           "FROM exposures GROUP BY segment ORDER BY ecl_sar_mn DESC")
    return Plan([PlanStep("run_query", {"sql": sql, "purpose": f"ECL and EAD by {lab['segment'].lower()}"})],
                lambda res: _write_overview(res, lab, period))


def orchestrator_text(d: dict[str, Any], lab: dict) -> str:
    e = d.get("evidence") or {}
    if not e:
        return "Here are scenario ideas for this book."
    if e.get("regime"):
        # R14 m (K12): the regime-conditioned recommendation, regime first
        from backend.scenarios import recommend
        return recommend.recommend(d.get("domain") or "corporate", top=e.get("largest_segment_by_ecl") or "Construction")["body"]
    return (f"**Shaping the scenario.** Decide *where* (the whole {lab['book'].lower()} book, a {lab['segment'].lower()} "
            f"such as {e['largest_segment_by_ecl']}, the largest by ECL at {e['its_ecl']}, one {lab['owner'].lower()} or one "
            f"{lab['exposure'].lower()}), *what moves* (PD, LGD, collateral, CCF/EAD, rating, a sector stress or a macro "
            f"variable) and *how hard*, against history: Brent fell {abs(e['worst_oil_fall_pct']):g}% in "
            f"{e['worst_oil_year']}; real GDP growth reached {e['worst_gdp_growth_pct']:g}% in {e['worst_gdp_year']}; the "
            f"repo rate rose {e['largest_repo_rise_bps']:g}bps in {e['its_year']}. Pick an idea below; it is restated as "
            "shocks and runs when you press Execute scenario.")


def _rows(res: dict) -> list[dict]:
    return (res.get("artifact") or {}).get("rows") or []


def _write_collateral(res: list[dict], book: str, period: str) -> dict[str, Any]:
    out = res[0]["out"]
    tot = (out.get("data") or {}).get("totals") or {}
    rows = _rows(res[0])
    if not tot:
        return {"markdown": "The collateral channel could not be measured on this population."}
    top = rows[0] if rows else None
    md = [f"**Collateral is a lever of its own, not an LGD shock.** A collateral value move of "
          f"{tot['collateral_pct']:+g}%" + (f" with haircuts {tot['haircut_pp']:+g}pp" if tot["haircut_pp"] else "") +
          " changes how much of each exposure is secured, and only the newly unsecured part takes a higher loss:",
          "- Secured share: s = min(EAD, haircut-adjusted collateral) / EAD, with haircut-adjusted collateral = "
          "market value x (1 - haircut).",
          "- After the shock: C1 = min(EAD, cover x (1 + dC) x (1 - h - dh) / (1 - h)).",
          f"- LGD change: dLGD = LGD_unsecured x (s0 - s1), with LGD_unsecured = {tot['unsecured_lgd_pct']:g}% for this book.",
          f"**On this book at {period}:** collateral counted against EAD falls from {_money(tot['collateral_before_sar_mn'])} "
          f"to {_money(tot['collateral_after_sar_mn'])}, the secured share from {tot['secured_share_before_pct']:g}% to "
          f"{tot['secured_share_after_pct']:g}%, and the EAD-weighted LGD rises by {tot['lgd_change_pp']:g}pp."]
    if top:
        md.append(f"The largest collateral type, {top['collateral_type']} (haircut {top['haircut_pct']:g}%), goes from "
                  f"{top['secured_share_before_pct']:g}% to {top['secured_share_after_pct']:g}% secured, so its LGD moves "
                  f"{top['lgd_change_pp']:+g}pp. Over-collateralised exposures absorb part of the fall, so the LGD rise is "
                  "smaller than a flat LGD shock of the same size.")
    md.append("Press **Execute scenario** to run it through the ECL engine.")
    return {"markdown": "\n\n".join([md[0], "\n".join(md[1:4]), *md[4:]]),
            "tables": [{"artifact_id": out["artifact_id"], "title": "Collateral channel by collateral type",
                        "columns": ["collateral_type", "ead_sar_mn", "haircut_pct", "secured_share_before_pct",
                                    "secured_share_after_pct", "lgd_change_pp"]}] if rows else [],
            "charts": [{"artifact_id": out["artifact_id"], "kind": "grouped", "x": "collateral_type",
                        "y": ["secured_share_before_pct", "secured_share_after_pct"],
                        "title": "Secured share before and after (% of EAD)"}] if rows else []}


def _write_levers(res: list[dict], sc: Scenario, book: str, period: str) -> dict[str, Any]:
    lab = runner.LABELS[book]
    head = ("**The proposal:** " + "; ".join("; ".join(describe_shocks(s.shocks, lab)) + f" on {s.scope.describe(lab)}"
                                             for s in sc.steps) + ". Nothing has run yet.")
    out: dict[str, Any] = {"markdown": head}
    notes = [r["out"].get("text", "") for r in res if r["tool"] == "read_knowledge" and r["out"].get("text")]
    coll = next((r for r in res if r["tool"] == "collateral_mechanics"), None)
    if coll is not None:
        w = _write_collateral([coll], book, period)
        out["markdown"] += "\n\n" + w["markdown"].rsplit("\n\n", 1)[0]
        out["tables"], out["charts"] = w.get("tables", []), w.get("charts", [])
        notes = notes[1:]
    out["markdown"] += "\n\n" + "\n\n".join(notes) + "\n\nPress **Execute scenario** to run it."
    return out


def _write_last(res: list[dict]) -> dict[str, Any]:
    d = res[0]["out"].get("data") or {}
    if not d.get("drivers"):
        return {"markdown": res[0]["out"].get("summary", "No result yet.")}
    drv = sorted([b for b in d["drivers"] if abs(b["sar_mn"]) >= 0.05], key=lambda b: -abs(b["sar_mn"]))
    md = (f"**{d['method']}.** ECL moves from {_money(d['start_ecl_sar_mn'])} to {_money(d['scenario_ecl_sar_mn'])} "
          f"({d['change_pct']:+.2f}%). " + "; ".join(f"{b['driver']} {_money(b['sar_mn'])}" for b in drv[:5]) +
          ". The driver bars are exact Shapley values and add up to the change.")
    return {"markdown": md, "tables": [{"artifact_id": res[0]["out"]["artifact_id"], "title": "Change by segment"}]
            if _rows(res[0]) else []}


def _write_mev(res: list[dict], key: str) -> dict[str, Any]:
    rows = _rows(res[0])
    if not rows:
        return {"markdown": "No history for that series."}
    lo = min(rows, key=lambda r: r["value"])
    hi = max(rows, key=lambda r: r["value"])
    last = rows[-1]
    name = mev.BY_KEY[key].name
    return {"markdown": f"**{name}** since {rows[0]['year']}: lowest {lo['value']:,.2f} in {lo['year']}, highest "
                        f"{hi['value']:,.2f} in {hi['year']}, {last['value']:,.2f} in {last['year']}.",
            "charts": [{"artifact_id": res[0]["out"]["artifact_id"], "kind": "line", "x": "year", "y": ["value"],
                        "title": name}]}


def _write_overview(res: list[dict], lab: dict, period: str) -> dict[str, Any]:
    rows = _rows(res[0])
    if not rows:
        return {"markdown": "No data in scope."}
    top = rows[0]
    tot_ecl = sum(r["ecl_sar_mn"] for r in rows)
    tot_ead = sum(r["ead_sar_mn"] for r in rows)
    return {"markdown": f"**{top['segment']}** carries the most ECL at {_money(top['ecl_sar_mn'])} "
                        f"({top['ecl_sar_mn'] / tot_ecl * 100:.1f}% of {_money(tot_ecl)}), coverage {top['coverage_pct']:.2f}%. "
                        f"The {lab['book'].lower()} book holds {_money(tot_ead)} of EAD at {period}.",
            "tables": [{"artifact_id": res[0]["out"]["artifact_id"], "title": f"ECL by {lab['segment'].lower()}"}],
            "charts": [{"artifact_id": res[0]["out"]["artifact_id"], "kind": "hbar", "x": "segment", "y": ["ecl_sar_mn"],
                        "title": f"ECL by {lab['segment'].lower()} (SAR mn)"}]}


# ------------------------------------------------------------------ the domain

def state_brief(state: dict[str, Any]) -> str:
    parts = []
    if state.get("pending"):
        sc = Scenario.from_dict(state["pending"])
        parts.append("Proposed, not executed: " + " | ".join(s.restatement for s in sc.steps))
    if state.get("scenario"):
        sc = Scenario.from_dict(state["scenario"])
        parts.append("Last executed scenario: " + " | ".join(s.restatement for s in sc.steps))
    if state.get("method"):
        parts.append(f"Model chosen: {state['method']}")
    last = state.get("last") or {}
    if last.get("change_pct") is not None:
        parts.append(f"Last result: ECL change {last['change_pct']:+.2f}% ({last.get('method')})")
    return ". ".join(parts)


def suggestions(scope: dict[str, Any], state: dict[str, Any]) -> list[dict[str, str]]:
    book = scope.get("domain") or "corporate"
    out = [{"label": "How does collateral move LGD?", "send": "How does a collateral reduction change LGD on this book?"},
           {"label": "Where is ECL concentrated?", "send": "Where is ECL concentrated in this book?"}]
    if state.get("scenario"):
        out.insert(0, {"label": "What drove the change?", "send": "What drove the ECL change?"})
    out.append({"label": "Oil price history", "send": "How has the oil price moved since 1990?"} if book == "corporate"
               else {"label": "Unemployment history", "send": "How has unemployment moved?"})
    return out


CHARTER = ("You are the What-If assistant in CreditProbe, a Saudi bank's credit-risk system: an IFRS 9 scenario analyst "
           "who explains ECL, its drivers and the scenario engine, explores the book's data, distributions, history and "
           "MEVs, and helps the user shape realistic scenarios. You never execute a scenario: when the user describes "
           "a change, call propose_scenario so it is restated as structured shocks, and say it runs on Execute.")

DOMAIN = Domain(key="whatif", title="What-If", charter=CHARTER, relations=relations, tools=TOOLS, knowledge=KNOWLEDGE,
                planner=planner, state_brief=state_brief, suggestions=suggestions,
                scope_label=lambda s: f"{_population(s)} at {_scope(s)[1]}",
                scope_key=lambda s: "|".join(_scope(s)))

_ = DRIVER_LABELS
