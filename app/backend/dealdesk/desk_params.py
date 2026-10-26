"""Admin -> Deal Desk Parameters (PLAN_R9 Session E, E1): the UAE desk table and the catalogue.

The engine's own tables (backend.dealdesk.params) stay as they are; this module adds the R9 table
`uae_desk` (AED FTP curve, deposit FTP credit rates, corporate tax 9%, tenor caps, sector appetite,
maximum leverage and the proposal-review assumptions), versioned the same way: the seed is v1 here,
every edit writes var/dealdesk/params/uae_desk/vN.json with an effective date, who and why.

`catalogue()` is what the Admin page shows: every editable parameter, its table, current value,
an (i) with "Why it is required" and "Where it comes from in the bank".
"""
from __future__ import annotations

import copy
import json
import threading
from datetime import datetime, timezone
from typing import Any

from backend.dealdesk import params, paths

_LOCK = threading.Lock()
NAME = "uae_desk"

SEED: dict[str, Any] = {
    "name": "UAE desk parameters", "owner": "Finance", "version": "v1", "effective_from": "2026-10-01",
    "approved_by": "CFO",
    "rows": {
        "ftp_aed": {"tenors": [0.25, 1, 2, 3, 5, 7, 10], "base": [0.0440, 0.0425, 0.0405, 0.0395, 0.0390, 0.0395, 0.0405],
                    "liquidity_premium_bps": [5, 10, 20, 30, 45, 60, 75]},
        "deposit_ftp_credit": {"AED": 0.0400, "SAR": 0.0480, "USD": 0.0370},
        "corporate_tax": 0.09,
        "cost_of_equity": 0.125,
        "opex_to_income": 0.28,
        "fee_recognition_years": 1.0,
        "lgd_unsecured": 0.45,
        "risk_weight_by_rating": {"AAA": 0.2, "AA+": 0.2, "AA": 0.2, "AA-": 0.2, "A+": 0.5, "A": 0.5, "A-": 0.5,
                                  "BBB+": 1.0, "BBB": 1.0, "BBB-": 1.0, "BB+": 1.0, "BB": 1.0, "BB-": 1.0,
                                  "B+": 1.5, "B": 1.5, "B-": 1.5, "CCC+": 1.5, "CCC": 1.5, "CCC-": 1.5, "CC": 1.5, "C": 1.5},
        "tenor_cap_years": {"Working capital": 1, "Guarantees": 3, "Term finance": 7, "Vehicle finance": 5, "Real estate": 10},
        "sector_appetite": {"Construction": "Selective", "Trading": "Selective", "Real Estate": "Restricted",
                            "Manufacturing": "Grow", "Healthcare": "Grow", "Government and GRE": "Grow"},
        "max_leverage": 4.0,
        "max_backlog_cover": 3.0,
        "cash_flow_cover": 1.25,
        "aed_sar": 1.021,
    },
}

#: (table, key, label, kind, why, where)
_ROWS: list[tuple[str, str, str, str, str, str]] = [
    ("returns", "hurdle", "Hurdle rate by segment", "rate_map",
     "The return on capital a deal must clear; the Deal Desk verdict compares RAROC with it.",
     "Set by the CFO from the cost of equity and the bank's ROE target; approved by ALCO or the Board in the annual plan."),
    ("returns", "hurdle_sector", "Hurdle override by sector", "rate_map",
     "Sectors under selective appetite carry a higher hurdle.",
     "Finance, from the risk appetite statement; approved with the annual plan."),
    (NAME, "cost_of_equity", "Cost of equity", "rate",
     "Discount rate for SVA and the floor for the hurdle.", "Finance (CAPM on the bank's share price, or the parent's)."),
    ("capital", "capital_ratio_target", "Capital ratio (allocation)", "rate",
     "Capital held per unit of RWA: the denominator of RAROC.", "Finance capital planning (ICAAP target CET1 plus buffers)."),
    (NAME, "ftp_aed", "FTP curve AED", "curve",
     "The cost of funds charged to each funded deal by tenor.", "Treasury ALM desk: EIBOR swap curve plus the bank's liquidity premium."),
    ("ftp", "base", "FTP curves SAR and USD", "curve_map",
     "The cost of funds for SAR and USD deals.", "Treasury ALM desk: SAIBOR / SOFR curves plus liquidity premia."),
    (NAME, "deposit_ftp_credit", "Deposit FTP credit rates", "rate_map",
     "The value of deposits to the relationship: balances earn FTP credit minus the profit paid.",
     "Treasury: the FTP credit for stable (core) deposits by currency, from the behavioural deposit study."),
    (NAME, "risk_weight_by_rating", "Risk weights by rating", "rate_map",
     "Regulatory capital for each exposure.", "Basel / CBUAE standardised approach tables (Finance regulatory reporting)."),
    ("ccf", "performance_lg", "CCF: performance guarantees", "ccf",
     "Converts guarantees and undrawn limits into exposure.", "CBUAE capital regulation (standardised CCFs), Risk Models."),
    ("ccf", "financial_lg", "CCF: financial guarantees", "ccf",
     "Financial guarantees are full credit substitutes.", "CBUAE capital regulation, Risk Models."),
    ("pd_master_scale", "", "PD master scale", "table",
     "Maps each rating to a probability of default for EL and capital.", "Risk Models: the validated rating model calibration."),
    (NAME, "lgd_unsecured", "LGD unsecured", "rate",
     "Loss if default happens with no collateral.", "Risk Models: workout LGD study."),
    ("lgd", "collateral", "LGD haircuts by collateral", "table",
     "Collateral value after haircut reduces LGD.", "Risk Models and Collateral Management: valuation and recovery history."),
    (NAME, "opex_to_income", "Opex allocation (cost to income)", "rate",
     "Operating cost charged to each deal.", "Finance cost allocation (activity-based costing for Corporate Banking)."),
    (NAME, "fee_recognition_years", "Fee recognition (years)", "number",
     "Upfront fees are spread over this many years in RAROC.", "Finance: IFRS 9 effective-interest policy."),
    (NAME, "corporate_tax", "Corporate tax", "rate",
     "RAROC is after tax; the UAE corporate tax rate is 9%.", "Tax department: UAE Federal Decree-Law No. 47 of 2022."),
    (NAME, "tenor_cap_years", "Tenor caps by product", "number_map",
     "The longest tenor credit policy allows per product.", "Credit Policy (Risk), approved by the Board Risk Committee."),
    (NAME, "sector_appetite", "Sector appetite", "text_map",
     "Grow, Selective or Restricted per sector; sets the hurdle override and the approval route.",
     "Risk appetite statement, approved by the Board."),
    (NAME, "max_leverage", "Maximum leverage (net debt / EBITDA)", "number",
     "Debt capacity check in the review.", "Credit Policy (Risk)."),
    (NAME, "max_backlog_cover", "Maximum backlog cover (x revenue)", "number",
     "Contractors whose backlog is many times revenue cannot execute it.", "Credit Policy for contractors (Risk)."),
]


def _edit_dir():
    return paths.VAR / "params" / NAME


def table() -> dict[str, Any]:
    with _LOCK:
        d = _edit_dir()
        if d.exists():
            vs = sorted(d.glob("v*.json"), key=lambda q: int(q.stem[1:]))
            if vs:
                return json.loads(vs[-1].read_text())
        return copy.deepcopy(SEED)


def rows() -> dict[str, Any]:
    return table()["rows"]


def history() -> list[dict[str, Any]]:
    out = [{"version": "v1", "effective_from": SEED["effective_from"], "by": SEED["approved_by"], "reason": "Seeded"}]
    d = _edit_dir()
    if d.exists():
        for q in sorted(d.glob("v*.json"), key=lambda q: int(q.stem[1:])):
            t = json.loads(q.read_text())
            out.append({"version": t["version"], "effective_from": t["effective_from"], "by": t["edited"]["by"], "reason": t["edited"]["reason"]})
    return out


def edit(new_rows: dict[str, Any], user: str, reason: str) -> dict[str, Any]:
    if not reason or not reason.strip():
        raise params.ParamError(NAME, ["a reason is required"])
    tab = table()
    errs = []
    t = float(new_rows.get("corporate_tax", -1))
    if not 0 <= t < 0.5:
        errs.append("corporate_tax must be in [0, 50%)")
    if any(not (0 <= float(v) < 0.3) for v in new_rows.get("deposit_ftp_credit", {}).values()):
        errs.append("deposit FTP credit rates must be in [0, 30%)")
    if float(new_rows.get("max_leverage", 0)) <= 0:
        errs.append("max_leverage must be positive")
    if errs:
        raise params.ParamError(NAME, errs)
    prev = tab["version"]
    num = int(prev[1:]) + 1
    now = datetime.now(timezone.utc)
    tab.update({"rows": new_rows, "version": f"v{num}", "effective_from": now.strftime("%Y-%m-%d"), "approved_by": user,
                "edited": {"by": user, "at": now.isoformat(timespec="seconds"), "reason": reason.strip(), "previous": prev}})
    d = _edit_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / f"v{num}.json").write_text(json.dumps(tab, indent=1))
    return tab


def _value(tab: str, key: str) -> Any:
    r = rows() if tab == NAME else params.rows(tab)
    return r if not key else r.get(key)


def catalogue() -> list[dict[str, Any]]:
    out = []
    for tab, key, label, kind, why, where in _ROWS:
        meta = table() if tab == NAME else params.table(tab)
        out.append({"table": tab, "key": key, "label": label, "kind": kind, "value": _value(tab, key), "why": why, "where": where,
                    "version": meta["version"], "effective_from": meta["effective_from"], "owner": meta["owner"],
                    "editable": kind in ("rate", "number", "rate_map", "number_map", "ccf")})
    return out


def set_value(tab: str, key: str, value: Any, user: str, reason: str) -> dict[str, Any]:
    """Edit one catalogue row: writes the next version of its table, effective today, applied immediately."""
    if not any(t == tab and k == key for t, k, *_ in _ROWS):
        raise params.ParamError(tab, [f"'{key}' is not an editable Deal Desk parameter"])
    if tab == NAME:
        r = copy.deepcopy(rows())
        r[key] = value
        return edit(r, user, reason)
    r = copy.deepcopy(params.rows(tab))
    r[key] = value
    return params.edit(tab, r, user, reason)
