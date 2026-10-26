"""The tour's live numbers (PLAN_R14 session t, K36 (4) claims discipline, N3, N5).

Every figure Noor says in the tour is a `Fact`: a value read at run time from a relation registered in Data Domains
(through the brief's reader, `backend.agents_v5.brief.readers.read`, so there is no side door), or from a committed
build artefact (the What-If domain manifest, the Lenses catalogue), with its source stamp: domain, relation, method,
keys and period. A fact that cannot be read on this build is absent, and the script writer drops the clause that
needed it; nothing is ever filled in from memory or rounded up into a claim.

`collect()` returns `{fact_id: Fact}`; every reader is independent and never raises.
"""
from __future__ import annotations

import json
import logging
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from backend.agents_v5.brief.readers import latest_period, read

logger = logging.getLogger(__name__)
V5 = Path(__file__).resolve().parents[3]

# The deal the tour opens: the R12 twin A demo deal (fictional), the richest deal file on the demo build.
TOUR_DEAL = "R12-TWA"


@dataclass
class Fact:
    id: str
    value: Any
    en: str            # how it is said in English ("SAR 1.73bn", "442")
    ar: str            # how it is said in Arabic ("1.73 مليار ريال", "442")
    domain: str
    relation: str
    method: str        # how the number was computed, in one line
    keys: dict[str, Any] = field(default_factory=dict)
    period: str = ""

    def public(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------- formatting (deterministic, no locale)

def _trim(x: float, dp: int) -> str:
    s = f"{x:,.{dp}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


def sar_en(mn: float) -> str:
    """SAR millions as spoken on screen: SAR 1.73bn, SAR 878.5m, SAR 0.4m."""
    if abs(mn) >= 1000:
        return f"SAR {_trim(mn / 1000, 2)}bn"
    return f"SAR {_trim(mn, 1)}m"


def sar_ar(mn: float) -> str:
    if abs(mn) >= 1000:
        return f"{_trim(mn / 1000, 2)} مليار ريال"
    return f"{_trim(mn, 1)} مليون ريال"


def count(n: int) -> str:
    return f"{int(n):,}"


def pct(x: float, dp: int = 1) -> str:
    return f"{_trim(x, dp)}%"


def _ok(v: Any) -> bool:
    return v is not None and not (isinstance(v, float) and math.isnan(v))


# ---------------------------------------------------------------- the readers

def _registry() -> dict[str, Fact]:
    from backend.data_builder.registry import DOMAINS
    n_dom = len(DOMAINS)
    n_rel = sum(len(s.get("relations") or {}) for s in DOMAINS.values())
    m = "count of the domains and relations registered in Data Domains (backend/data_builder/registry.py)"
    return {
        "domains": Fact("domains", n_dom, count(n_dom), count(n_dom), "data_domains", "registry", m),
        "relations": Fact("relations", n_rel, count(n_rel), count(n_rel), "data_domains", "registry", m),
    }


def _book() -> dict[str, Fact]:
    p = latest_period("ews", "corp_exposure")
    r = read("ews", "corp_exposure", where="reporting_quarter = ?", args=[p],
             columns="count(distinct borrower_id) AS b, sum(ead_sar_mn) AS ead, sum(ecl_sar_mn) AS ecl, "
                     "sum(CASE WHEN stage = 2 THEN ead_sar_mn ELSE 0 END) / sum(ead_sar_mn) AS s2")
    if not r.rows or not _ok(r.rows[0].get("b")):
        return {}
    x = r.rows[0]
    keys = {"reporting_quarter": p}
    out = {
        "book_borrowers": Fact("book_borrowers", int(x["b"]), count(x["b"]), count(x["b"]), "ews", "corp_exposure",
                               "distinct borrower_id in the latest quarter", keys, p),
        "book_ead": Fact("book_ead", float(x["ead"]), sar_en(x["ead"]), sar_ar(x["ead"]), "ews", "corp_exposure",
                         "sum of ead_sar_mn in the latest quarter", keys, p),
        "book_ecl": Fact("book_ecl", float(x["ecl"]), sar_en(x["ecl"]), sar_ar(x["ecl"]), "ews", "corp_exposure",
                         "sum of ecl_sar_mn in the latest quarter", keys, p),
        "book_period": Fact("book_period", p, p, p, "ews", "corp_exposure", "latest reporting_quarter", keys, p),
    }
    if _ok(x.get("s2")):
        out["book_stage2"] = Fact("book_stage2", float(x["s2"]) * 100, pct(x["s2"] * 100), pct(x["s2"] * 100),
                                  "ews", "corp_exposure", "Stage 2 EAD / total EAD in the latest quarter", keys, p)
    return out


def _ews() -> dict[str, Fact]:
    p = latest_period("ews", "corp_series_portfolio")
    r = read("ews", "corp_series_portfolio", where="reporting_quarter = ? AND ews_band = 'critical'",
             args=[p], columns="sum(owners) AS owners, sum(ead_sar_mn) AS ead")
    if not r.rows or not _ok(r.rows[0].get("owners")):
        return {}
    x = r.rows[0]
    keys = {"reporting_quarter": p, "ews_band": "critical"}
    return {
        "ews_names": Fact("ews_names", int(x["owners"]), count(x["owners"]), count(x["owners"]), "ews",
                          "corp_series_portfolio", "borrowers (owners) in the critical early-warning band",
                          keys, p),
        "ews_ead": Fact("ews_ead", float(x["ead"]), sar_en(x["ead"]), sar_ar(x["ead"]), "ews", "corp_series_portfolio",
                        "EAD in the critical early-warning band", keys, p),
    }


def _b360() -> dict[str, Fact]:
    p = latest_period("borrower_360", "rel_group_quarter")
    r = read("borrower_360", "rel_group_quarter", where="reporting_quarter = ?", args=[p],
             columns="count(DISTINCT group_id) AS g, count(DISTINCT borrower_id) AS b")
    if not r.rows or not _ok(r.rows[0].get("g")):
        return {}
    x = r.rows[0]
    return {"groups": Fact("groups", int(x["g"]), count(x["g"]), count(x["g"]), "borrower_360", "rel_group_quarter",
                           "distinct groups in the latest quarter", {"reporting_quarter": p}, p)}


def _whatif() -> dict[str, Fact]:
    """The What-If accuracy, measured. Session m's back-test relation when it is on the build; else the domain's own
    reconciliation (the starting ECL equals the book's ECL in every period), which is a different, weaker claim and is
    worded as such."""
    out: dict[str, Fact] = {}
    try:
        man = json.loads((V5 / "data" / "whatif_v5" / "corporate" / "manifest.json").read_text())
        rec = man.get("reconciliation") or {}
        periods = man.get("periods") or []
        if rec.get("ecl_final_equals_book") is True and periods:
            out["whatif_periods"] = Fact(
                "whatif_periods", len(periods), count(len(periods)), count(len(periods)), "what_if", "whatif_corporate",
                f"periods in the What-If domain whose starting ECL equals the book's ECL (manifest reconciliation, "
                f"max abs error {rec.get('ecl_abs_err')})", {"manifest": "data/whatif_v5/corporate/manifest.json"},
                f"{periods[0]}–{periods[-1]}")
    except Exception as e:  # noqa: BLE001
        logger.info("tour: What-If manifest not readable: %s", e)
    bt = backtest()
    if bt:
        out.update(bt)
    return out


def backtest() -> dict[str, Fact]:
    """Session m's `whatif_backtest` relation (What-If ECL estimate vs the full ECL engine per quarter). Columns are
    read by name: a per-quarter absolute error in percent (`abs_err_pct`, `abs_error_pct`, `error_pct`), or the two
    ECL columns (`ecl_whatif`, `ecl_engine`) from which it is computed. Absent or unreadable → {} (clause omitted)."""
    from backend.agents_v5.brief.readers import domain_of
    dom = domain_of("whatif_backtest")
    if not dom:
        return {}
    r = read(dom, "whatif_backtest")
    if not r.rows:
        return {}
    cols = set(r.rows[0])
    if "version" in cols:   # the latest version of the back-test only
        top = max(int(x["version"] or 0) for x in r.rows)
        r.rows = [x for x in r.rows if int(x["version"] or 0) == top]
    errs: list[float] = []
    col = next((c for c in ("abs_error_pct", "abs_err_pct", "error_pct", "err_pct") if c in cols), None)
    if col:
        errs = [abs(float(x[col])) for x in r.rows if _ok(x.get(col))]
    else:
        a = next((c for c in ("ecl_estimate_mn", "ecl_whatif", "whatif_ecl", "ecl_estimate") if c in cols), None)
        b = next((c for c in ("ecl_actual_mn", "ecl_engine", "engine_ecl", "ecl_full") if c in cols), None)
        if a and b:
            errs = [abs(float(x[a]) / float(x[b]) - 1) * 100 for x in r.rows
                    if _ok(x.get(a)) and _ok(x.get(b)) and float(x[b])]
    if not errs:
        return {}
    errs.sort()
    mean = sum(errs) / len(errs)
    worst = errs[-1]
    m = f"What-If ECL vs the full ECL engine, absolute error per quarter ({col or 'from the two ECL columns'})"
    return {
        "bt_quarters": Fact("bt_quarters", len(errs), count(len(errs)), count(len(errs)), dom, "whatif_backtest",
                            "quarter-to-quarter steps in the back-test", {}),
        "bt_mean": Fact("bt_mean", mean, pct(mean, 2), pct(mean, 2), dom, "whatif_backtest", "mean of " + m, {}),
        "bt_worst": Fact("bt_worst", worst, pct(worst, 2), pct(worst, 2), dom, "whatif_backtest", "worst " + m, {}),
    }


def _lenses() -> dict[str, Fact]:
    from backend.lenses_v5 import catalogue as c
    dims = {d.key if hasattr(d, "key") else str(d) for book in ("corporate", "retail") for d in c.dims_for(book)}
    n = len(dims)
    return {"lens_dims": Fact("lens_dims", n, count(n), count(n), "lenses", "catalogue",
                              "distinct dimensions in the Lenses catalogue, corporate and retail "
                              "(backend/lenses_v5/catalogue.py)")}


def _deal() -> dict[str, Fact]:
    out: dict[str, Fact] = {}
    r = read("deal_desk", "dd_deal", columns="count(*) AS n, "
             "sum(CASE WHEN status IN ('new', 'in_review', 'counter_offered') THEN 1 ELSE 0 END) AS pending")
    if r.rows and _ok(r.rows[0].get("n")):
        x = r.rows[0]
        out["deals_pending"] = Fact("deals_pending", int(x["pending"]), count(x["pending"]), count(x["pending"]),
                                    "deal_desk", "dd_deal", "deals with status new, in review or counter-offered")
    d = read("deal_desk", "dd_deal", where="proposal_id = ?", args=[TOUR_DEAL],
             columns="obligor_name, proposed_limits_mn")
    if d.rows:
        x = d.rows[0]
        out["deal_name"] = Fact("deal_name", x["obligor_name"], x["obligor_name"], x["obligor_name"], "deal_desk",
                                "dd_deal", "obligor_name", {"proposal_id": TOUR_DEAL})
        if _ok(x.get("proposed_limits_mn")):
            out["deal_ask"] = Fact("deal_ask", float(x["proposed_limits_mn"]), sar_en(x["proposed_limits_mn"]),
                                   sar_ar(x["proposed_limits_mn"]), "deal_desk", "dd_deal", "proposed_limits_mn",
                                   {"proposal_id": TOUR_DEAL})
    f = read("deal_desk", "dd_review_finding", where="proposal_id = ?", args=[TOUR_DEAL],
             columns="count(*) AS n, sum(CASE WHEN severity = 'critical' THEN 1 ELSE 0 END) AS crit")
    if f.rows and f.rows[0].get("n"):
        x = f.rows[0]
        k = {"proposal_id": TOUR_DEAL}
        out["deal_findings"] = Fact("deal_findings", int(x["n"]), count(x["n"]), count(x["n"]), "deal_desk",
                                    "dd_review_finding", "findings on the deal, every category", k)
        out["deal_critical"] = Fact("deal_critical", int(x["crit"] or 0), count(x["crit"] or 0), count(x["crit"] or 0),
                                    "deal_desk", "dd_review_finding", "findings with severity critical", k)
    out.update(proposal_check())
    s = read("deal_desk", "dd_stress_result", where="proposal_id = ?", args=[TOUR_DEAL],
             columns="count(DISTINCT scenario_id) AS n")
    if s.rows and s.rows[0].get("n"):
        out["deal_scenarios"] = Fact("deal_scenarios", int(s.rows[0]["n"]), count(s.rows[0]["n"]),
                                     count(s.rows[0]["n"]), "deal_desk", "dd_stress_result",
                                     "distinct stress scenarios run on the deal", {"proposal_id": TOUR_DEAL})
    return out


PQ_DEMO = ("R14-RWQ", "R14-DEMO")   # session p's demo pack deal (fictional; renamed during R14), checked at build time


def proposal_check() -> dict[str, Fact]:
    """Session p's proposal check (`dd_proposal_quality`): the checked proposal the tour opens (p's demo deal when it
    is there, else the proposal with the most defects in one run), and that run's defects. Absent → {}."""
    r = read("deal_desk", "dd_proposal_quality",
             where="result = 'defect'", columns="proposal_id, run_id, count(*) AS n, "
             "sum(CASE WHEN severity = 'critical' THEN 1 ELSE 0 END) AS crit",
             group="proposal_id, run_id", order="n DESC, run_id")
    if r.status != "ok" or not r.rows:
        return {}
    runs = [x for x in r.rows if x.get("proposal_id") in PQ_DEMO] or r.rows
    best = runs[0]
    pid = str(best["proposal_id"])
    k = {"proposal_id": pid, "run_id": best["run_id"], "result": "defect"}
    out = {"pq_deal": Fact("pq_deal", pid, pid, pid, "deal_desk", "dd_proposal_quality", "the checked proposal", k),
           "pq_defects": Fact("pq_defects", int(best["n"]), count(best["n"]), count(best["n"]), "deal_desk",
                              "dd_proposal_quality", "defects found in the check run with the most defects", k),
           "pq_critical": Fact("pq_critical", int(best["crit"] or 0), count(best["crit"] or 0), count(best["crit"] or 0),
                               "deal_desk", "dd_proposal_quality", "of which severity critical", k)}
    d = read("deal_desk", "dd_deal", where="proposal_id = ?", args=[pid], columns="obligor_name")
    if d.rows and d.rows[0].get("obligor_name"):
        nm = str(d.rows[0]["obligor_name"])
        out["pq_deal_name"] = Fact("pq_deal_name", nm, nm, nm, "deal_desk", "dd_deal", "obligor_name", {"proposal_id": pid})
    return out


def _monitoring() -> dict[str, Fact]:
    """Session f's `dd_monitoring_proposal` (names proposed for monitoring); absent → {}."""
    r = read("deal_desk", "dd_monitoring_proposal", columns="count(*) AS n")
    if r.status == "ok" and r.rows and r.rows[0].get("n"):
        n = int(r.rows[0]["n"])
        en = f"{count(n)} name is" if n == 1 else f"{count(n)} names are"
        return {"monitoring_proposals": Fact("monitoring_proposals", n, en, count(n), "deal_desk",
                                             "dd_monitoring_proposal", "count of monitoring proposals")}
    return {}


def _policies() -> dict[str, Fact]:
    out: dict[str, Fact] = {}
    r = read("deal_desk", "dd_policy_clause", columns="count(*) AS n")
    if r.rows and r.rows[0].get("n"):
        n = int(r.rows[0]["n"])
        out["policy_clauses"] = Fact("policy_clauses", n, count(n), count(n), "deal_desk", "dd_policy_clause",
                                     "clauses of the credit policy on file")
    from backend.data_builder.registry import DOMAINS
    n_sc = len((DOMAINS.get("scorecard") or {}).get("relations") or {})
    if n_sc:
        out["scorecards"] = Fact("scorecards", n_sc, count(n_sc), count(n_sc), "scorecard", "registry",
                                 "scorecards registered in Data Domains")
    b = read("brf", "brf_return", columns="count(*) AS n")
    if b.rows and b.rows[0].get("n"):
        n = int(b.rows[0]["n"])
        out["brf_returns"] = Fact("brf_returns", n, count(n), count(n), "brf", "brf_return", "regulatory returns built")
    try:
        n = 0
        for f in sorted((V5 / "backend" / "playbook_v5" / "data").glob("*.json")):
            n += len(json.loads(f.read_text()).get("sections") or [])
        if n:
            out["rule_sections"] = Fact("rule_sections", n, count(n), count(n), "playbook", "regulations",
                                        "sections of the regulator's documents loaded in Playbook "
                                        "(backend/playbook_v5/data/*.json)")
    except Exception as e:  # noqa: BLE001
        logger.info("tour: playbook data not readable: %s", e)
    return out


def _governance() -> dict[str, Fact]:
    r = read("governance", "gov_decision", columns="count(*) AS n")
    if not r.rows or not r.rows[0].get("n"):
        return {}
    n = int(r.rows[0]["n"])
    return {"decisions": Fact("decisions", n, count(n), count(n), "governance", "gov_decision",
                              "credit decisions on file (demo seed)")}


READERS: tuple[Callable[[], dict[str, Fact]], ...] = (
    _registry, _book, _ews, _b360, _whatif, _lenses, _deal, _monitoring, _policies, _governance)


def collect() -> dict[str, Fact]:
    out: dict[str, Fact] = {}
    for fn in READERS:
        try:
            out.update(fn() or {})
        except Exception as e:  # noqa: BLE001 - one source never stops the tour
            logger.info("tour: %s failed: %s", fn.__name__, e)
    return out
