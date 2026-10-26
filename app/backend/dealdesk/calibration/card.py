"""The model card of the calibrated stress sensitivities: docs/v5/R12_STRESS_CALIBRATION.md, written from the estimate.

    python -m backend.dealdesk.calibration.card       # re-estimate, write calibrated_v1.json and the card
"""
from __future__ import annotations

from typing import Any

from backend.dealdesk import paths
from backend.dealdesk.calibration import sensitivity as S

CARD = paths.V5 / "docs" / "v5" / "R12_STRESS_CALIBRATION.md"


def _p(x: float, d: int = 1) -> str:
    return f"{100 * x:+.{d}f}%"


def _row(r: dict[str, Any]) -> str:
    used = "calibrated" if not r["fallback"] else "**expert (flag)**"
    return (f"| {r['sector']} | {r['estimate']:+.3f} [{r['ci_low']:+.3f}, {r['ci_high']:+.3f}] | {r['r2']:.2f} / {r['partial_r2']:.2f} | "
            f"{r['n']} q, {r['n_borrowers']:,} borrowers | {_p(r['stress_revenue_pct_estimate'], 2)} "
            f"[{_p(r['stress_revenue_pct_ci_low'], 2)}, {_p(r['stress_revenue_pct_ci_high'], 2)}] | {_p(r['expert_stress_revenue_pct'])} | "
            f"{used}: {_p(r['stress_revenue_pct'], 2)} | {'' if not r['fallback'] else r['reason']} |")


def _names(xs: list[str]) -> str:
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]


def _top(rows: list[dict[str, Any]], expert: bool = False, k: int = 3) -> str:
    cal = sorted([r for r in rows if r["driver"] == "gdp_nonoil" and not r["fallback"] and r["sector"] != "default"],
                 key=lambda r: r["stress_revenue_pct_estimate"])[:k]
    key = "expert_stress_revenue_pct" if expert else "stress_revenue_pct_estimate"
    vals = sorted(abs(100 * r[key]) for r in cal)
    rng = f"{vals[0]:.1f}–{vals[-1]:.1f}% of revenue"
    return rng if expert else f"{_names([r['sector'] for r in cal])} about {rng}"


def markdown(est: dict[str, Any]) -> str:
    sm, sa, ru = est["summary"], est["sample"], est["rules"]
    rows = est["rows"]
    gdp = [r for r in rows if r["driver"] == "gdp_nonoil" and r["sector"] != "default"]
    wrong = [r["sector"] for r in gdp if r["fallback"] and r["estimate"] <= 0]
    weak = [r["sector"] for r in gdp if r["fallback"] and r["estimate"] > 0]
    out = [
        "# R12 stress sensitivity calibration: model card (I19-2)",
        "",
        f"**Version `{est['version']}` (source \"{est['source']}\")**, published to Data Domains as a new `dd_stress_sensitivity` "
        "version through Session E's publisher; Session D's Stress Lab engine reads it. Built by "
        "`backend/dealdesk/calibration/sensitivity.py`; coefficients in `backend/dealdesk/calibration/calibrated_v1.json`; this card is "
        "written by `python -m backend.dealdesk.calibration.card` (the same files always give the same numbers).",
        "",
        "## Answer first",
        "",
        f"- **{sm['calibrated']} of {sm['rows']} sector × driver sensitivities are estimated from the bank's own history; "
        f"{sm['fallback']} keep the expert value and are flagged.**",
        f"- **Oil:** {sm['calibrated_by_driver']['oil']} of {len(rows) // 2} sectors calibrated. Over {sa['from']}–{sa['to']} the bank's "
        "borrower revenues show no oil effect that can be told from zero in any sector, although Brent moved from "
        f"{sa['observed']['oil']['min']:+.0f}% to {sa['observed']['oil']['max']:+.0f}% year on year. The oil sensitivities in "
        "`stress_scenarios.json` (oil −30% → Construction −12%, Chemicals −15% …) therefore stay as **untested expert assumptions**.",
        f"- **Non-oil GDP:** {sm['calibrated_by_driver']['gdp_nonoil']} of {len(rows) // 2} rows calibrated (book-wide default included). "
        f"The estimated betas are much smaller than the expert ones: a 3-point non-oil GDP shortfall costs {_top(rows)} in this history, "
        f"against {_top(rows, expert=True)} in the expert table. "
        + (f"{_names(wrong)} move against the cycle in this history (wrong sign) and keep the expert value. " if wrong else "")
        + (f"{_names(weak)} keep the expert value because the fit is too weak. " if weak else ""),
        "- **Read with care:** the sample is one expansion (non-oil growth between "
        f"{sa['observed']['gdp_nonoil']['min']:.1f}% and {sa['observed']['gdp_nonoil']['max']:.1f}%), with no contraction; a 3-point shortfall "
        f"is about {gdp[0]['shock_reach']:.1f}× the largest slowdown seen, so every GDP row is flagged **extrapolated**. A history that includes a "
        "downturn would very likely give larger betas. Risk Models can override any row (maker-checker), and every row carries "
        "the expert value beside the estimate.",
        "",
        "## Data (PLAN_R12 §0)",
        "",
        "| Input | Relation / file | Use |",
        "|---|---|---|",
        f"| Borrower financials history | Data Domains `cockpit.corp_borrower_quarter` (`{est['sources']['book'].split('(')[-1].rstrip(')')}`): "
        "`revenue_sar_mn`, `sector`, by borrower and quarter, 2021Q3–2026Q2 | sector year-on-year revenue growth on a balanced panel |",
        f"| Brent | {est['sources']['brent']} (public) | quarterly average, year-on-year log change |",
        f"| Real non-oil GDP | {est['sources']['gdp_nonoil']} (public) | four-quarter-ending growth (annual rates weighted by quarter) |",
        "",
        "The macro series are the public files the What-If MEV already uses; they are not yet a registered Data Domains relation "
        "(Session E owns the registry: recorded as a gap in `docs/STATUS_R12_TRY.md`). No other source is read.",
        "",
        "## Method",
        "",
        f"- **Sample:** {sa['n']} quarters, {sa['from']} to {sa['to']} (year-on-year windows need four earlier quarters). "
        f"Left out: {', '.join(sa['left_out']) or 'none'} (their window needs the 2026 GDP projection, not history).",
        "- **Dependent variable:** g = 100 × ln(Σ revenue_t / Σ revenue_t−4) over the sector's borrowers with revenue in both quarters.",
        "- **Regression:** g = a + b_oil × oil + b_gdp × gdp, OLS; **Newey-West** standard errors with "
        f"{ru['hac_lags']} lags (the year-on-year windows overlap); **{int(100 * ru['ci_level'])}% bands** with Student t "
        f"({sa['n'] - 3} degrees of freedom).",
        "- **Robustness:** the same regression on borrower-level growth, pooled within the sector, standard errors clustered by quarter "
        "(`panel_estimate` in the relation); the two agree closely.",
        "- **Stress value:** the revenue change at the scenario shock: `oil_30` (Brent −30%, log change ln 0.7) and `gdp_3` "
        "(non-oil GDP 3 points below plan), with the band carried through.",
        f"- **When the expert value stays (flagged):** fewer than {ru['min_n']} quarters; the 90% band includes zero; the wrong sign; "
        f"R² below {ru['min_r2']:.2f}; the driver's own partial R² below {ru['min_partial_r2']:.2f}; or the shock more than "
        f"{ru['max_reach']:.1f}× the largest adverse move in the sample. The row then has `fallback = true`, `source = \"expert (fallback)\"` "
        "and the reason in `flag`.",
        "",
        "## Results: oil (Brent −30%)",
        "",
        "| Sector | Elasticity [90% band] | R² / partial | n | Revenue at shock [band] | Expert | Used | Why expert |",
        "|---|---|---|---|---|---|---|---|",
        *[_row(r) for r in rows if r["driver"] == "oil"],
        "",
        "## Results: real non-oil GDP (3 points below plan)",
        "",
        "| Sector | Beta [90% band] | R² / partial | n | Revenue at shock [band] | Expert | Used | Why expert |",
        "|---|---|---|---|---|---|---|---|",
        *[_row(r) for r in rows if r["driver"] == "gdp_nonoil"],
        "",
        "## The relation (`dd_stress_sensitivity`, version 2 = calibrated v1)",
        "",
        "Session E's contract keys a sensitivity by `sensitivity_id` (`<sector>:<driver>`) and `version`; E seeded version 1 from "
        "`stress_scenarios.json` (`method = expert`). Calibrated v1 publishes **version 2** of the oil and non-oil GDP rows "
        "(15 sectors with `default`, two drivers): `beta` is the value the engine uses (revenue % change per 1% fall in Brent, or "
        "per 1 point of non-oil GDP growth below plan); `method = regression` with `band_low`, `band_high` (90%), `n_obs` and `r2` "
        "where the data carries it; otherwise `method = expert`, the expert `beta` again, no band, and `source` starting "
        "\"expert (fallback)\" with the reason and the estimate that was rejected. `owner` is \"Risk Models (calibrated v1, R12 Session T)\", "
        "`model_card_ref` points here. The other drivers (fixed-cost, largest-customer and project shares) stay at version 1. "
        "The engine reads the highest version per `sensitivity_id` (`backend.dealdesk.calibration.publish.latest`). The full estimate "
        "(partial R², the borrower-panel estimate, the shock reach, the extrapolation flag) is in `calibrated_v1.json`.",
        "",
        "## Limits",
        "",
        "1. One expansion, 14 usable quarters (about 3.5 non-overlapping years): the bands are conditional on a short sample, and the "
        "GDP regressor is built from annual data (5 calendar years), so its information is thinner than 14 points suggest.",
        "2. Revenue only. Margin, receivable days and the largest-customer and project shares keep the expert assumptions.",
        "3. No listed-company or public sector series are in the repo, so the plan's \"plus public data\" part is limited to the "
        "two macro series.",
        "4. The relation records both values; replacing the expert value in the Stress Lab is Session D's engine reading this "
        "version. An expert override goes through maker-checker (D's scenario editor).",
        "",
    ]
    return "\n".join(out)


def build() -> dict[str, Any]:
    est = S.estimate()
    S.write(est)
    CARD.write_text(markdown(est))
    return est


if __name__ == "__main__":  # pragma: no cover
    import sys
    e = build()
    print(e["summary"])
    if "--publish" in sys.argv:
        print(S.publish_version(e))
