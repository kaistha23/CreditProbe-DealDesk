"""R14 i: the fictional demo rows of the two relations session i registers (built by backend.dealdesk.data.build).

  dd_external_turnover  open-banking inflows at other banks (monthly, by bank) and VAT-return taxable sales (quarterly)
                        for every deal with a reported revenue, for the last 12 months of account conduct
                        (2025-07 .. 2026-06). Fictional seed (consented open-banking data is not in the demo bank):
                        each deal gets a coverage target (inflows / VAT-inclusive revenue) - twin A 0.78 (revenue not
                        supported by cash), twin B 0.93, DD-06 0.97, the rest 0.88 to 1.04 by a hash of the deal id -
                        and the other banks fill what this bank's own turnover does not; VAT declared sales follow
                        their own target (twin A 0.84 of reported revenue). Deterministic: no clock, no randomness.
  dd_deal_intel         one catalogue row per D6-D13 feature (what it is, where it lives, its method and sources);
                        engine results per deal are published as later versions by `ops/r14_i_publish.py`.
"""
from __future__ import annotations

import hashlib
from typing import Any

MONTHS = [f"2025-{m:02d}" for m in range(7, 13)] + [f"2026-{m:02d}" for m in range(1, 7)]
QUARTERS = [("2025Q3", "2025-07-01", "2025-09-30"), ("2025Q4", "2025-10-01", "2025-12-31"), ("2026Q1", "2026-01-01", "2026-03-31"),
            ("2026Q2", "2026-04-01", "2026-06-30")]
BANKS = ("Coastal Commerce Bank", "Northern Gulf Bank", "Peninsula Trade Bank", "Red Sea Investment Bank", "Desert Crescent Bank")
VAT = 0.15
TARGET = {"R12-TWA": 0.78, "R12-TWB": 0.93, "DD-06": 0.97}
VAT_TARGET = {"R12-TWA": 0.84, "R12-TWB": 0.97, "DD-06": 0.99}
RETRIEVED = "2026-10-18T06:00:00Z"


def _h(*parts: str) -> float:
    """A deterministic number in [0, 1) from the parts."""
    d = hashlib.sha256("|".join(parts).encode()).hexdigest()
    return int(d[:12], 16) / float(16 ** 12)


def _revenue(pid: str, deal: dict[str, Any], fin_detail: list[dict[str, Any]]) -> float | None:
    fd = [r for r in fin_detail if r["proposal_id"] == pid and r.get("entity_scope") == "standalone" and r.get("period_kind") == "audited"
          and r.get("revenue_mn") is not None]
    if fd:
        return float(max(fd, key=lambda r: r["year"])["revenue_mn"])
    from backend.dealdesk.data.store import dd_read
    try:
        of = [r for r in dd_read("dd_obligor_financials", proposal_id=pid) if r.get("kind") == "actual"]
    except Exception:  # noqa: BLE001
        of = []
    if of:
        return float(max(of, key=lambda r: r["year"])["revenue_sar_mn"])
    try:
        from backend.dealdesk.data import deals
        ys = [y for y in deals.get(pid)["financials"]["years"] if y["kind"] == "actual" and y.get("revenue")]
        return float(ys[-1]["revenue"]) if ys else None
    except Exception:  # noqa: BLE001
        return None


def own_turnover(pid: str, obligor: str, conduct: list[dict[str, Any]] | None = None) -> tuple[float, str, int]:
    """(credit turnover at this bank over MONTHS, relation, months found)."""
    if conduct is None:
        from backend.dealdesk.data.store import dd_read
        try:
            conduct = dd_read("dd_account_conduct", proposal_id=pid)
        except Exception:  # noqa: BLE001
            conduct = []
    rs = [r for r in conduct if r.get("proposal_id") == pid and r["month"] in MONTHS]
    if rs:
        return sum(float(r["credit_turnover_mn"] or 0) for r in rs), "dd_account_conduct", len(rs)
    if str(obligor).startswith("CB"):
        from backend.dealdesk.data.store import dd_frame
        try:
            dm = dd_frame("dep_month", obligor_id=obligor)
            dm = dm[dm["month"].isin(MONTHS)]
            return float(dm["credit_turnover_sar_mn"].sum()), "dep_month", int(len(dm))
        except Exception:  # noqa: BLE001
            return 0.0, "dep_month", 0
    return 0.0, "", 0


def external_turnover(rows: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    deals = rows.get("dd_deal") or []
    fin = rows.get("dd_financials_detail") or []
    conduct = rows.get("dd_account_conduct") or []
    obf = rows.get("other_bank_facility") or []
    out: list[dict[str, Any]] = []
    for d in sorted(deals, key=lambda r: r["proposal_id"]):
        pid, ob = d["proposal_id"], d.get("obligor_id") or ""
        rev = _revenue(pid, d, fin)
        if not rev or rev <= 0:
            continue
        own, _, _ = own_turnover(pid, ob, conduct)
        tgt = TARGET.get(pid, round(0.88 + 0.16 * _h(pid, "cov"), 3))
        vt = VAT_TARGET.get(pid, round(0.95 + 0.06 * _h(pid, "vat"), 3))
        need = tgt * rev * (1 + VAT)
        banks = sorted({r["bank_name"] for r in obf if r["proposal_id"] == pid and float(r.get("declared_limit_mn") or 0) > 0})
        if not banks:
            k = int(_h(pid, "banks") * len(BANKS))
            banks = sorted({BANKS[k], BANKS[(k + 2) % len(BANKS)]})
        other = max(need - own, 0.05 * need)
        wts = [0.5 + _h(pid, b, "w") for b in banks]
        tw = sum(wts)
        for b, w in zip(banks, wts):
            share = other * w / tw
            ms = [0.85 + 0.3 * _h(pid, b, m) for m in MONTHS]
            sm = sum(ms)
            for m, x in zip(MONTHS, ms):
                inflow = round(share * x / sm, 4)
                transfers = round(inflow * (0.02 + 0.04 * _h(pid, b, m, "t")), 4)
                out.append({"turnover_id": f"XT-{pid}-{b.split()[0][:4].upper()}-{m}", "proposal_id": pid, "obligor_id": ob,
                            "source_kind": "open_banking", "provider": b, "period": m, "period_start": f"{m}-01",
                            "period_end": f"{m}-28", "credit_inflows_mn": inflow, "own_account_transfers_mn": transfers,
                            "taxable_sales_mn": None, "consent_ref": f"OBC-{pid}-{b.split()[0][:3].upper()}",
                            "retrieved_at": RETRIEVED,
                            "note": "Open-banking account information (consented), credit inflows by month; fictional demo seed."})
        for q, s, e in QUARTERS:
            out.append({"turnover_id": f"XT-{pid}-VAT-{q}", "proposal_id": pid, "obligor_id": ob, "source_kind": "vat_return",
                        "provider": "VAT return (tax authority)", "period": q, "period_start": s, "period_end": e, "credit_inflows_mn": None,
                        "own_account_transfers_mn": None, "taxable_sales_mn": round(vt * rev / 4 * (0.94 + 0.12 * _h(pid, q, "vat")), 4),
                        "consent_ref": f"VAT-{pid}", "retrieved_at": RETRIEVED,
                        "note": "Taxable sales declared in the quarterly VAT return; fictional demo seed."})
    return out


CATALOGUE = [
    ("D6", "Negotiation frontier", "Structure", "What each concession (10% cash margin, a year of tenor, SAR 10m of amount) is worth in bps of price, "
     "and three counter-offers the client is likely to accept, ranked by value to the bank.", "engine.analyse on the selected structure"),
    ("D7", "Default pre-mortem", "Analysis + Recommendation", "The three most likely ways the deal goes bad: driver, probability a year, speed and "
     "the trigger that warns first.", "dd_stress_result, dd_scenario_calibration, dd_monitoring_plan, D12"),
    ("D8", "Precedent explorer", "Review (with Decision consistency)", "The five closest past deals: decision, conditions, performance; "
     "similarity basis stated; flags an inconsistent decision.", "gov_decision, corp_facility_quarter, col_item, dd_deal, dd_condition"),
    ("D9", "Pricing benchmark", "Proposal + Structure", "Percentile of the proposed margin against the book for the same rating, sector, "
     "product and tenor, and the breakeven margin.", "orig_facility, corp_facility_quarter, engine.breakeven_margin"),
    ("D10", "Revenue truth check", "Proposal check + Financial quality", "Reported revenue against account turnover at this bank, other banks "
     "(open banking) and VAT-return sales: the gap and what it implies.", "dd_financials_detail, dd_account_conduct, dep_month, dd_external_turnover"),
    ("D11", "Renewal diff", "Proposal step on renewals", "What changed since the last approval: financials, conduct, rating, conditions, "
     "covenants, group exposure.", "dd_reference, dd_financials_detail, dd_account_conduct, dd_condition, dd_group_exposure"),
    ("D12", "Group contagion on the deal", "Review + Group & SWOT", "Connected parties in Stage 3 or litigation, their exposure, and what "
     "their failure does to this deal.", "group facts (Borrower 360, cockpit), engine.analyse with notches"),
    ("D13", "Committee rehearsal", "More - Committee questions", "The questions committee will ask on the selected structure, each with a "
     "suggested answer and its evidence, and whether the proposal already answers it.", "R13 committee challenger, findings, conditions"),
]


def catalogue_rows() -> list[dict[str, Any]]:
    return [{"result_id": f"CAT-{code}", "proposal_id": "", "feature": code, "feature_label": label, "item_seq": 0, "item_kind": "catalogue",
             "label": label, "value": None, "unit": "", "text": what, "structure": "", "basis_json": [src], "where": where,
             "engine_version": "r14-i1", "run_at": "2026-10-19T18:00:00Z"} for code, label, where, what, src in CATALOGUE]


def build(rows: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    return {"dd_external_turnover": external_turnover(rows), "dd_deal_intel": catalogue_rows()}
