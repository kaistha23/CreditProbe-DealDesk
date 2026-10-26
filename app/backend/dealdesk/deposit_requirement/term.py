"""The Deposit requirement term: model, validation, words, and the engine's two channels.

Term keys (flat, beside the engine's other levers; neutral values leave every earlier result unchanged):

    deposit_type          "none" | "lien_cash" (lien-marked cash collateral) | "relationship" (operating balances);
                          a size with type "none" is read as lien-marked cash (the "require a deposit" lever's default)
    deposit_pct           the deposit as a % of the limit (used when deposit_amount is 0)
    deposit_amount        the deposit in the deal currency, millions (0 = use deposit_pct)
    deposit_tenor_months  the maintenance period in months (0 = the life of the facility)
    deposit_facility      the facility it secures: "" or "proposed" (this facility), "all" (all the obligor's facilities,
                          this one included), or an existing facility id (then it secures that facility, not this one)

Engine (backend/dealdesk/engine.py calls `lien_cash` and `relationship_value`):

    lien-marked cash   D_t = deposit x hold x (1 - haircut) x cover_t, haircut from `lgd.collateral.lien_deposit`
                       (Risk Models). D_t joins the cash in the LGD recoveries (R) and is netted from the SA exposure,
                       exactly as the cash margin is; EAD net of the deposit = max(0, EAD_t - D_t) is reported. With a 0%
                       haircut over the whole tenor it prices exactly as a cash margin of the same percentage.
    operating balances V_t = balance x max(FTP credit - profit paid, 0) x realisation x cover_t x (1 - zakat), the FTP credit
                       from `uae_desk.deposit_ftp_credit` (Treasury, the deposits.py rate), the profit paid on required
                       balances from `relationship.deposit_requirement`, the realisation of a committed balance from
                       `relationship.committed_realisation` (the committed cross-sell's). V_t is added to relationship
                       RAP only: deal RAROC is unchanged, relationship RAROC rises.

cover_t is the share of year t inside the maintenance period (1 for every year when the period is the life of the facility).
"""
from __future__ import annotations

from typing import Any

import numpy as np

KEYS = ("deposit_type", "deposit_pct", "deposit_amount", "deposit_tenor_months", "deposit_facility")
NEUTRAL: dict[str, Any] = {"deposit_type": "none", "deposit_pct": 0, "deposit_amount": 0, "deposit_tenor_months": 0, "deposit_facility": ""}
TYPES = {"none": "None", "lien_cash": "Lien-marked cash collateral", "relationship": "Operating balances (relationship deposits)"}
THIS = ("", "proposed", "this")
LIEN_ROW = "lien_deposit"  # the haircut row in the lgd table


def _f(x: Any) -> float:
    try:
        return float(x or 0.0)
    except (TypeError, ValueError):
        return 0.0


def normalise(t: dict[str, Any] | None) -> dict[str, Any] | None:
    """The term in one dict, or None when the terms carry no deposit requirement."""
    t = t or {}
    typ = t.get("deposit_type") or "none"
    pct, amt = _f(t.get("deposit_pct")), _f(t.get("deposit_amount"))
    if pct <= 0 and amt <= 0:
        return None
    if typ == "none":  # "require a deposit" alone (a size with no type): a lien-marked cash deposit, the lever's default
        typ = "lien_cash"
    if typ not in ("lien_cash", "relationship"):
        return None
    return {"type": typ, "label": TYPES[typ], "pct": pct, "amount": amt, "basis": "amount" if amt > 0 else "pct",
            "tenor_months": int(_f(t.get("deposit_tenor_months"))), "facility": str(t.get("deposit_facility") or "")}


def from_terms(t: dict[str, Any] | None) -> dict[str, Any] | None:
    return normalise(t)


def validate(t: dict[str, Any], prefix: str = "terms") -> list[dict[str, str]]:
    """Field errors in the validate_terms shape (absent keys = neutral)."""
    e: list[dict[str, str]] = []

    def bad(k: str, msg: str) -> None:
        e.append({"field": f"{prefix}.{k}", "message": msg})

    if t.get("deposit_type", "none") not in TYPES:
        bad("deposit_type", f"one of {', '.join(TYPES)}")
    for k, (lo, hi) in {"deposit_pct": (0, 100), "deposit_amount": (0, 1e6), "deposit_tenor_months": (0, 240)}.items():
        if k in t:
            v = t[k]
            if not isinstance(v, (int, float)) or isinstance(v, bool) or not (lo <= v <= hi):
                bad(k, f"a number in [{lo:g}, {hi:g}]")
    if not isinstance(t.get("deposit_facility", ""), (str, type(None))):
        bad("deposit_facility", "a facility id, 'proposed' or 'all'")
    return e


def check_facility(p: dict[str, Any], t: dict[str, Any]) -> list[dict[str, str]]:
    f = str(t.get("deposit_facility") or "")
    if f in THIS or f == "all":
        return []
    ids = [x.get("facility_id") for x in p.get("obligor", {}).get("existing_facilities") or [] if x.get("facility_id")]
    if f not in ids:
        return [{"field": "terms.deposit_facility", "message": f"'proposed', 'all' or one of the obligor's facilities {ids}"}]
    return []


def secures_this(term: dict[str, Any]) -> bool:
    return term["facility"] in THIS or term["facility"] == "all"


def cover(tenor_months: int, T: int) -> np.ndarray:
    """Share of each year inside the maintenance period (0 months = the life of the facility)."""
    if tenor_months <= 0:
        return np.ones(T)
    return np.clip(tenor_months / 12.0 - np.arange(T), 0.0, 1.0)


def gross_sar(term: dict[str, Any], A_full_sar: float, fx: float) -> float:
    """The deposit in SAR m: the stated amount, else the % of the full limit."""
    return term["amount"] * fx if term["basis"] == "amount" else A_full_sar * term["pct"] / 100.0


# ------------------------------------------------------------------ the engine's channels

def lien_cash(p: dict[str, Any], t: dict[str, Any], A_full_sar: float, hold: float, T: int, lgd_rows: dict[str, Any],
              fx: float) -> tuple[np.ndarray, dict[str, Any] | None]:
    """Recognised lien-marked cash a year (SAR m) on this facility, and its record."""
    term = normalise(t)
    if term is None or term["type"] != "lien_cash":
        return np.zeros(T), None
    row = lgd_rows["collateral"].get(LIEN_ROW) or lgd_rows["collateral"]["cash"]
    h = float(row["haircut"])
    gross = gross_sar(term, A_full_sar, fx)
    held = gross * hold
    cv = cover(term["tenor_months"], T)
    on = secures_this(term)
    rec = held * (1.0 - h) * cv if on else np.zeros(T)
    return rec, {"gross_sar_mn": gross, "held_sar_mn": held, "haircut": h, "cover": [float(x) for x in cv], "secures_this": on,
                 "recognised_by_year": [float(x) for x in rec], "haircut_row": f"lgd.collateral.{LIEN_ROW if LIEN_ROW in lgd_rows['collateral'] else 'cash'}"}


def relationship_value(p: dict[str, Any], t: dict[str, Any], A_full_sar: float, T: int, currency: str, zakat: float,
                       rel_rows: dict[str, Any], realisation: float, fx: float) -> tuple[np.ndarray, dict[str, Any] | None]:
    """Funding value of the required operating balances a year, after zakat (SAR m), and its record."""
    term = normalise(t)
    if term is None or term["type"] != "relationship":
        return np.zeros(T), None
    from backend.dealdesk import desk_params
    ftp_credit = float(desk_params.rows()["deposit_ftp_credit"].get(currency, desk_params.rows()["deposit_ftp_credit"]["SAR"]))
    dr = rel_rows.get("deposit_requirement") or {}
    paid = float(dr.get("profit_paid_rate", 0.0))
    bal = gross_sar(term, A_full_sar, fx)
    cv = cover(term["tenor_months"], T)
    spread = max(ftp_credit - paid, 0.0)
    val = bal * spread * realisation * cv * (1.0 - zakat)
    return val, {"balance_sar_mn": bal, "ftp_credit": ftp_credit, "profit_paid": paid, "spread": spread, "realisation": realisation,
                 "cover": [float(x) for x in cv], "value_by_year": [float(x) for x in val], "value_pa_before_zakat": bal * spread * realisation}


def engine_effect(t: dict[str, Any], lien: dict[str, Any] | None, rel: dict[str, Any] | None, ead: np.ndarray, disc: np.ndarray,
                  pv_cap: float, A_full_sar: float, currency: str, versions: dict[str, str]) -> dict[str, Any] | None:
    """The `deposit` block of an analysis: what the engine used and what it did."""
    term = normalise(t)
    if term is None:
        return None
    T = len(ead)
    out: dict[str, Any] = {**term, "currency": currency, "limit_sar_mn": A_full_sar,
                           "maintenance": "the life of the facility" if term["tenor_months"] <= 0 else f"{term['tenor_months']} months",
                           "years_covered": float(sum(cover(term["tenor_months"], T)))}
    if lien is not None:
        rec = np.asarray(lien["recognised_by_year"])
        net = np.maximum(0.0, ead - rec)
        out.update({"channel": "risk mitigation (EAD net of the deposit, LGD and RWA)", "amount_sar_mn": lien["gross_sar_mn"],
                    "held_sar_mn": lien["held_sar_mn"], "haircut": lien["haircut"], "secures_this_facility": lien["secures_this"],
                    "recognised_y1_sar_mn": float(rec[0]) if T else 0.0, "ead_y1": float(ead[0]) if T else 0.0,
                    "ead_net_y1": float(net[0]) if T else 0.0, "recognised_by_year": lien["recognised_by_year"],
                    "parameters": {"haircut": f"{lien['haircut_row']} (lgd {versions.get('lgd', 'v1')}, Risk Models)"},
                    "formula": (f"Lien-marked cash {lien['gross_sar_mn']:,.2f}m x hold x (1 - haircut {lien['haircut']:.0%}) x the share of each "
                                f"year maintained = {float(rec[0]) if T else 0.0:,.2f}m recognised in year one: it joins the cash in the LGD "
                                f"recoveries and is netted from the SA exposure; EAD net of the deposit {float(net[0]) if T else 0.0:,.2f}m.")})
        if not lien["secures_this"]:
            out["note"] = f"The deposit secures existing facility {term['facility']}, not this facility: no effect on this deal's EAD, LGD or RWA."
    if rel is not None:
        val = np.asarray(rel["value_by_year"])
        pv = float((disc * val).sum())
        out.update({"channel": "funding value in relationship RAROC", "amount_sar_mn": rel["balance_sar_mn"],
                    "ftp_credit": rel["ftp_credit"], "profit_paid": rel["profit_paid"], "realisation": rel["realisation"],
                    "funding_value_pa_sar_mn": rel["value_pa_before_zakat"], "funding_value_by_year": rel["value_by_year"],
                    "pv_funding_value_sar_mn": pv, "relationship_raroc_uplift": pv / pv_cap if pv_cap > 0 else None,
                    "parameters": {"ftp_credit": "uae_desk.deposit_ftp_credit (Treasury)",
                                   "profit_paid": f"relationship.deposit_requirement (relationship {versions.get('relationship', 'v1')}, Finance)",
                                   "realisation": f"relationship.committed_realisation (relationship {versions.get('relationship', 'v1')}, Finance)"},
                    "formula": (f"Operating balances {rel['balance_sar_mn']:,.2f}m x (FTP credit {rel['ftp_credit']:.2%} - profit paid "
                                f"{rel['profit_paid']:.2%}) x realisation {rel['realisation']:.0%} = {rel['value_pa_before_zakat']:,.3f}m a year "
                                f"while maintained; present value after zakat {pv:,.3f}m, added to relationship RAP (deal RAROC unchanged).")})
    return out


# ------------------------------------------------------------------ words

def facility_words(term: dict[str, Any], p: dict[str, Any] | None = None, facility_label: str = "the proposed facility") -> str:
    f = term["facility"]
    if f in THIS:
        return facility_label
    if f == "all":
        return "all the obligor's facilities"
    prod = next((x.get("product") for x in ((p or {}).get("obligor") or {}).get("existing_facilities") or [] if x.get("facility_id") == f), None)
    return f"existing facility {f}" + (f" ({str(prod).replace('_', ' ')})" if prod else "")


def amount_words(term: dict[str, Any], ccy: str, limit_ccy: float | None, amount_ccy: float | None = None) -> str:
    """The amount in words. `amount_ccy` is the engine's figure (analysis["deposit"]); without it only the stated inputs are printed."""
    lim = f"the {ccy} {limit_ccy:,.1f}m limit" if limit_ccy else "the limit"
    if amount_ccy is not None:
        return f"{ccy} {amount_ccy:,.1f}m" + (f" ({term['pct']:,.0f}% of {lim})" if term["basis"] == "pct" else "")
    if term["basis"] == "amount":
        return f"{ccy} {term['amount']:,.1f}m"
    return f"{term['pct']:,.0f}% of {lim}"


def maintenance_words(term: dict[str, Any], tenor_years: Any = None) -> str:
    if term["tenor_months"] <= 0:
        return "for the life of the facility" + (f" ({int(tenor_years)} years)" if tenor_years else "")
    m = term["tenor_months"]
    return f"for {m} months" + (f" ({m / 12:g} years)" if m % 12 == 0 and m >= 12 else "")


def describe(t: dict[str, Any] | None, ccy: str = "SAR", limit_ccy: float | None = None, tenor_years: Any = None,
             p: dict[str, Any] | None = None, facility_label: str = "the proposed facility", amount_ccy: float | None = None) -> str | None:
    """One sentence for a paper: what, how much, how long, which facility (the amount is the engine's when given)."""
    term = normalise(t)
    if term is None:
        return None
    amt = amount_words(term, ccy, limit_ccy, amount_ccy)
    fac = facility_words(term, p, facility_label)
    if term["type"] == "lien_cash":
        return (f"Lien-marked cash deposit of {amt}, held with the Bank under lien in the Bank's favour {maintenance_words(term, tenor_years)}, "
                f"securing {fac}")
    return (f"Operating balances of not less than {amt} on average, maintained with the Bank {maintenance_words(term, tenor_years)}, "
            f"supporting {fac}")


def short(t: dict[str, Any] | None, ccy: str = "SAR", amount_ccy: float | None = None) -> str:
    """The term sheet cell (the amount is the engine's when given)."""
    term = normalise(t)
    if term is None:
        return "None"
    kind = "Lien-marked cash" if term["type"] == "lien_cash" else "Operating balances"
    amt = f"{ccy} {term['amount']:,.1f}m" if term["basis"] == "amount" else f"{term['pct']:,.0f}% of limit"
    if term["basis"] == "pct" and amount_ccy is not None:
        amt += f" ({ccy} {amount_ccy:,.1f}m)"
    per = "life of facility" if term["tenor_months"] <= 0 else f"{term['tenor_months']} months"
    return f"{kind} · {amt} · {per}"


__all__ = ["KEYS", "NEUTRAL", "TYPES", "normalise", "from_terms", "validate", "check_facility", "describe", "short", "lien_cash",
           "relationship_value", "engine_effect"]
