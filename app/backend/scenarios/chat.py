"""What-If answers from the scenario engine (PLAN_R13 §S.4, J6): a headline by severity, then the evidence (data window,
method, percentile, observed frequency, model fit) and a "what this data cannot tell us" line; follow-ups
"How likely is this?", "Show the method" and "Write the methodology memo". Every sentence has a deterministic writer.

Blocks: one `text` block (the headline in markdown, so any client shows it) and one `scenario_set` block (the
structured headline table and evidence the What-If thread renders); the follow-ups add `text` and `scenario_memo`.
"""
from __future__ import annotations

import re
from typing import Any

from backend.scenarios import data, engine

SEVS = ("mild", "moderate", "severe")
SEV_LABEL = {"mild": "Mild", "moderate": "Moderate", "severe": "Severe"}
MEMO_PATH = "/api/v1/whatif/scenario-engine/memo.docx"

ASK_RE = re.compile(
    r"\b(mild|moderate)\b[^.?!]{0,60}\b(moderate|severe)\b[^.?!]{0,60}\bsevere\b|\b(three|all three|3) severit(y|ies)\b|"
    r"\bdata[- ]driven (scenario|scenarios|stress|severit\w*)\b|\bcalibrated (scenario|scenarios|severit\w*|stress)\b|"
    r"\bscenario engine\b", re.I)
MEMO_RE = re.compile(r"\b(write|draft|produce|generate|give me)?\s*(the |a )?methodology (memo|note|paper|document)\b", re.I)
METHOD_RE = re.compile(r"^\s*(show|explain)( me)? the (method|methodology|maths|math|workup)\b", re.I)
LIKELY_RE = re.compile(r"^\s*how likely\b", re.I)

CHIPS = [{"label": "How likely is this?", "send": "How likely is this?"},
         {"label": "Show the method", "send": "Show the method"},
         {"label": "Write the methodology memo", "send": "Write the methodology memo"}]


def route(q: str, state: dict[str, Any] | None = None) -> str | None:
    """'scenarios' | 'likelihood' | 'method' | 'memo' | None. Follow-ups only after a scenario-engine answer."""
    s = (q or "").strip()
    st = state or {}
    if s.startswith("::scn "):
        k = s.split(" ", 1)[1].strip()
        return k if k in ("scenarios", "likelihood", "method", "memo") else None
    if MEMO_RE.search(s) and "methodology" in s.lower():
        return "memo"
    if ASK_RE.search(s):
        return "scenarios"
    if st.get("last_kind") == "scenario_set":
        if LIKELY_RE.search(s):
            return "likelihood"
        if METHOD_RE.search(s):
            return "method"
    return None


def _m(x: float) -> str:
    return f"SAR {x:,.0f}m"


def _bn(x: float) -> str:
    return f"SAR {x / 1000:,.1f}bn" if abs(x) >= 1000 else _m(x)


def _pct(x: float, dp: int = 1) -> str:
    return f"{x * 100:.{dp}f}%"


def _one_in(p_tail: float) -> str:
    return f"about 1 year in {1 / p_tail:.0f}" if p_tail > 0 else "beyond the observed history"


def headline(res: dict[str, Any]) -> str:
    t = res["translation"]
    e0 = t["mild"]["ecl_start"]
    parts = ", ".join(f"{_m(t[s]['ecl_change'])} {s}" for s in SEVS)
    s2 = " / ".join(_pct(t[s]["stage2_share_stressed"]) for s in SEVS)
    cap = " / ".join(_bn(t[s]["capital_impact"]) for s in SEVS)
    return (f"**Corporate book, calibrated severities ({t['mild']['as_of']}):** ECL rises {parts} from {_m(e0)}; "
            f"Stage 2 goes from {_pct(t['mild']['stage2_share_start'])} of EAD to {s2}; capital needed {cap} "
            f"(mild / moderate / severe).")


def _scenario_line(res: dict[str, Any], sev: str) -> str:
    j = res["joint"]["joint"][sev]
    v = j["values"]
    rate = v["saibor"]
    return (f"Oil −{v['brent']:.0f}%, real GDP −{v['gdp_real']:.1f} pp, non-oil GDP −{v['gdp_nonoil']:.1f} pp, "
            + (f"SAIBOR +{rate:.0f} bps" if rate >= 5 else "SAIBOR flat") + f" ({j['basis']})")


def evidence(res: dict[str, Any]) -> list[dict[str, str]]:
    w = res["window"]
    cal = res["calibration"]
    pdm = res["satellite"]["pd"]
    mig = res["satellite"]["migration"]
    b = cal["brent"]
    bf = b["estimate"]["freq"]["moderate"]
    used = [k for k, c in pdm["coef"].items() if c["identified"]]
    nog = pdm["coef"]["gdp_nonoil"]
    from backend.scenarios.calibrate import SENSITIVITY_ONLY, SHORT
    live = [r for k, r in cal.items() if k not in SENSITIVITY_ONLY]
    emp = [r for r in live if r["method"] == "empirical"]
    fb = [r for r in live if r["method"] == "fallback"]
    oos = pdm["oos"]
    return [
        {"key": "window", "label": "Data window",
         "text": f"Macro {w['macro_from']}–{w['macro_to']} ({w['macro_years'] - 1} annual moves; non-oil GDP from {w['nonoil_from']}, "
                 f"SAIBOR from {w['saibor_from']}); bank history {w['bank_from']}–{w['bank_to']} ({w['bank_quarters']} quarters, "
                 f"{pdm['n']} sector-quarters)."},
        {"key": "method", "label": "Method",
         "text": "Each driver's one-year adverse move: mild P75, moderate P92 (P90–P93), severe max(P96, worst observed "
                 "episode); drivers drawn jointly with a Gaussian copula on their rank correlation and checked against 2009, "
                 "2015–16 and 2020; sector PD and Stage 1→2 migration from pooled ridge panels with sector effects; "
                 "translated facility by facility to PD, LGD, EAD, ECL, stage and IRB capital."},
        {"key": "percentile", "label": "Percentile and frequency",
         "text": f"Brent one-year fall: mild {b['display']['mild']}, moderate {b['display']['moderate']}, severe {b['display']['severe']}; "
                 f"a fall at least moderate happened in {bf['count']} of {bf['of']} years ({', '.join(bf['labels'])}). "
                 f"{len(emp)} of {len(live)} drivers are calibrated on data; {len(fb)} keep a labelled expert value "
                 f"({', '.join(SHORT.get(r['key'], r['key']) for r in fb)})."},
        {"key": "fit", "label": "Model fit",
         "text": f"PD model: n {pdm['n']}, R² {pdm['r2']:.2f} (within sector {pdm['r2_within']:.2f}); non-oil GDP "
                 f"{nog['beta']:+.4f} per pp (s.e. {nog['se']:.4f}) on the probit; used terms: "
                 f"{', '.join(pdm['coef'][k]['label'] for k in used) or 'none'}; out of sample (last 4 quarters) RMSE "
                 f"{oos['rmse']:.0f} bps against {oos['rmse_naive']:.0f} bps for holding the last value"
                 f"{' (beats it)' if oos['beats_naive'] else ' (does not beat it: read the size as indicative)'}. "
                 f"Migration model: n {mig['n']}, R² {mig['r2']:.2f}."},
        {"key": "cannot", "label": "What this data cannot tell us", "text": res["limits"]["cannot"]},
    ]


def scenario_block(res: dict[str, Any]) -> dict[str, Any]:
    t = res["translation"]
    rows = []
    for s in SEVS:
        x = t[s]
        rows.append({"severity": s, "label": SEV_LABEL[s], "scenario": _scenario_line(res, s),
                     "ecl_start": x["ecl_start"], "ecl_stressed": x["ecl_stressed"], "ecl_change": x["ecl_change"],
                     "ecl_band": x["ecl_band"], "ecl_change_pct": x["ecl_change_pct"],
                     "stage2_start": x["stage2_share_start"], "stage2": x["stage2_share_stressed"],
                     "pd_start": x["pd_start"], "pd": x["pd_stressed"], "capital": x["capital_impact"],
                     "lgd_add_pp": x["lgd_add_pp"], "frequency": {"mild": "about 1 year in 4", "moderate": "about 1 in 10 to 15",
                                                                  "severe": "1 in 25 or rarer"}[s]})
    top = t["severe"]["sectors"][:3]
    return {"type": "scenario_set", "book": "corporate", "as_of": t["mild"]["as_of"], "rows": rows, "evidence": evidence(res),
            "supports": res["limits"]["supports"], "cannot": res["limits"]["cannot"],
            "top_sectors": [{"sector": s["sector"], "ecl_change": s["ecl_change"]} for s in top],
            "relations": ["dd_scenario_calibration", "dd_scenario_joint", "dd_satellite_model", "dd_scenario_result"],
            "engine_version": res["version"], "fingerprint": res["reproducibility"]["fingerprint"], "memo_href": MEMO_PATH}


def answer_scenarios(domain: str = "corporate") -> list[dict[str, Any]]:
    res = engine.build()
    blocks: list[dict[str, Any]] = []
    if domain != "corporate":
        blocks.append({"type": "text", "markdown": (
            "The scenario engine's satellite models are estimated on the corporate book (20 quarters, 14 sectors). The retail "
            "book's 20 months are not yet modelled, so the result below is the corporate book; the macro severities apply to both.")})
    from backend.scenarios import conditioned, regime, revenue
    r = regime.current()
    blocks.insert(0, regime.block(r))                      # R14 m (K12): the current regime, read first
    blocks.append({"type": "text", "markdown": headline(res)})
    sb = scenario_block(res)
    if regime.is_high(r):
        rv = r["reversal"]
        sb["regime_note"] = (f"In the {r['label']} the oil leg is a reversal from today's level, not a fall from the long-run "
                             f"average: mild {rv['mild']['fall_pct']:.0f}% (USD {rv['mild']['to_usd']:.0f}), moderate "
                             f"{rv['moderate']['fall_pct']:.0f}% (USD {rv['moderate']['to_usd']:.0f}), severe "
                             f"{rv['severe']['fall_pct']:.0f}% (USD {rv['severe']['to_usd']:.0f}). The PD satellite model finds no "
                             "oil term beyond growth on 20 quarters, so the book moves through growth: the ECL above is the joint "
                             "growth and rate year, which is also the conflict and trade disruption with oil staying high.")
        for row in sb["rows"]:
            fam = conditioned.families(r)
            row["scenario_history"] = row["scenario"]
            row["scenario"] = (conditioned.scenario_line(fam["reversal"][row["severity"]]["values"])
                               + " (or the disruption: " + (lambda t: t[:1].lower() + t[1:])(conditioned.scenario_line(fam["disruption"][row["severity"]]["values"])) + ")")
    sb["evidence"].insert(0, {"key": "regime", "label": "Current regime",
                              "text": f"{r['label'][:1].upper()}{r['label'][1:]} ({r['rule']}). {r['vintage_line']}"})
    sb["evidence"].insert(1, {"key": "conditional", "label": "Conditional on today's level",
                              "text": conditioned.conditional_brent()["text"]})
    sb["evidence"].insert(2, {"key": "revenue", "label": "Revenue channel", "text": revenue.summary_line()})
    blocks.append(sb)
    return blocks


def answer_likelihood() -> list[dict[str, Any]]:
    res = engine.build()
    j = res["joint"]
    cal = res["calibration"]
    lines = ["**How likely is this?** Measured on history, not a forecast probability."]
    for s, tail in (("mild", 0.25), ("moderate", 0.08), ("severe", 0.04)):
        lines.append(f"- **{SEV_LABEL[s]}** ({_one_in(tail)}): {_scenario_line(res, s)}.")
    an = ", ".join(f"{a['year']} at P{a['percentile'] * 100:.0f}" for a in j["analogues"])
    lines.append(f"- **Where history sits on the same scale:** {an}.")
    for k in ("brent", "gdp_nonoil", "saibor"):
        r = cal[k]
        f = r["estimate"]["freq"]["severe"]
        lines.append(f"- {r['label']}: severe {r['display']['severe']} was reached in {f['count']} of {f['of']} years"
                     + (f" ({', '.join(f['labels'])})" if f["labels"] else "") + ".")
    lines.append(f"- What this data cannot tell us: {res['limits']['cannot']}")
    return [{"type": "text", "markdown": "\n".join(lines)}]


def answer_method() -> list[dict[str, Any]]:
    res = engine.build()
    pdm = res["satellite"]["pd"]
    mig = res["satellite"]["migration"]
    jt = res["joint"]
    k = jt["keys"]
    rho = jt["spearman"][k.index("brent")][k.index("gdp_real")]
    terms = "; ".join(f"{c['label']} {c['beta']:+.4f} (s.e. {c['se']:.4f}, {'used' if c['identified'] else 'not used: ' + c['why'].split(':')[0]})"
                      for c in pdm["coef"].values())
    md = "\n".join([
        "**The method, as the engine ran it.**",
        "1. **Severity.** For each driver the one-year adverse moves a₁…aₙ give Q(p), the empirical quantile (linear "
        "interpolation): mild = Q(0.75), moderate = Q(0.92), severe = max(Q(0.96), worst observed episode). Fewer than "
        f"{res['percentiles']['min_obs']} independent observations, or a driver the data cannot measure, keeps a labelled expert value.",
        f"2. **Joint scenarios.** Spearman correlations (oil fall with real GDP slowdown {rho:+.2f}) become the copula correlation "
        f"r = 2 sin(πρ/6); {jt['n_draws']:,} draws z ~ N(0, R) (seed {jt['seed']}) map back through each empirical margin; the "
        "joint mild / moderate / severe is the median year in the composite-index band P73–77 / P90–93 / P96–98.",
        f"3. **Satellite models.** Φ⁻¹(PD_st) = α + a_s + Σ β_k x_kt + e_st and logit(m_st) likewise, ridge (λ chosen by "
        f"leave-one-year-out), standard errors clustered by quarter. PD model: n {pdm['n']}, R² {pdm['r2']:.2f}, λ {pdm['lambda_b']:g}; "
        f"{terms}. Migration model: n {mig['n']}, R² {mig['r2']:.2f}, λ {mig['lambda_b']:g}.",
        "4. **Translation.** PD₁₂' = Φ(Φ⁻¹(PD₁₂) + Σ β_k Δx_k); lifetime PD by the hazard ratio; extra Stage 2 = "
        "[1 − (1 − m')⁴] − [1 − (1 − m)⁴] of Stage 1 EAD, highest stressed PD first; LGD' = LGD + expert add-on; "
        "EAD' = EAD + Δu × limit; ECL by stage; capital = ΔECL + 15% × ΔRWA (IRB corporate formula).",
        f"Reproducibility: engine {res['version']}, fingerprint {res['reproducibility']['fingerprint']}, relations "
        "dd_scenario_calibration, dd_scenario_joint, dd_satellite_model, dd_scenario_result.",
        f"What this data cannot tell us: {res['limits']['cannot']}",
    ])
    return [{"type": "text", "markdown": md}]


def answer_memo() -> list[dict[str, Any]]:
    res = engine.build()
    return [{"type": "text", "markdown": ("**Methodology memo ready.** Word, house style: purpose and scope, data and its limits, "
                                          "driver distributions, percentile choices, joint dependence, satellite models with "
                                          "standard errors and back-test, translation, results by severity, sensitivity, "
                                          f"limitations and reproducibility. {res['limits']['short']}")},
            {"type": "scenario_memo", "href": MEMO_PATH, "label": "Download the methodology memo (Word)",
             "engine_version": res["version"], "fingerprint": res["reproducibility"]["fingerprint"]}]


def answer(kind: str, domain: str = "corporate") -> list[dict[str, Any]]:
    if kind == "scenarios":
        return answer_scenarios(domain)
    if kind == "likelihood":
        return answer_likelihood()
    if kind == "method":
        return answer_method()
    if kind == "memo":
        return answer_memo()
    raise KeyError(kind)


def data_note() -> str:
    return data.limits()["short"]
