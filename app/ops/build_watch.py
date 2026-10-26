"""Build the `watch` data domain (PLAN_R9 Session C, P4 Accepted Risk Watch).

    .venv/bin/python -m ops.build_watch

Writes data/watch/watch-v1/{watch_client,watch_item}.parquet + manifest.json. Deterministic: the same books always
give the same bytes. Names: the corporate borrowers that Session A's `classification` marks "Accepted Risk Watch"
when that domain is present, else the warned (Medium/High) performing borrowers with the largest exposure, spread
across sectors; plus the two proposal cases (PLAN_R9 §Proposals), which are UAE and in AED.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from backend.spine.books import book

V5 = Path(__file__).resolve().parents[1]
OUT = V5 / "data" / "watch" / "watch-v1"
REF_DATE = "2026-10-13"
AED_TO_SAR = 3.75 / 3.6725
N_BOOK = 20

#: EWS reason fragment -> (trigger, metric, frequency, critical, article)
TEMPLATES = (
    ("Covenant breach", ("Covenant back within threshold", "DSCR and leverage covenants at the next covenant review", "Quarterly", True, "CBUAE CRM Art. 7.11(a)")),
    ("returned payments", ("No further returned payments", "Returned cheques and debits in the account", "Monthly", False, "CBUAE CRM Art. 7.11(f)")),
    ("Operating inflows fell", ("Operating inflows recover to 80% of last year", "Credit turnover in the operating account", "Monthly", False, "CBUAE CRM Art. 7.11(b)")),
    ("High utilisation", ("Utilisation below 90%", "Average utilisation of the working-capital lines", "Monthly", False, "CBUAE CRM Art. 7.11(b)")),
    ("Rating", ("No further rating downgrade", "Internal rating at the next review", "Quarterly", True, "CBUAE CRM Art. 7.11(e)")),
    ("Past due", ("Arrears cleared within 30 days", "Days past due on every facility", "Monthly", True, "CBUAE CRM Art. 7.8")),
    ("Operating balance", ("Operating balance above one month of obligations", "Month-end balance against obligations", "Monthly", False, "CBUAE CRM Art. 7.11(b)")),
)
DEFAULT_ITEMS = (
    ("Audited financials received within 120 days", "FY2026 audited financial statements", "Annual", False, "CBUAE CRM Art. 7.11(f)"),
    ("Sector outlook reviewed", "Sector review at the watch committee", "Quarterly", False, "CBUAE CRM Art. 7.12"),
)
RATIONALES = (
    "Warning signals are liquidity-driven and short-dated; collateral cover and the sponsor's support keep credit risk "
    "within appetite. No significant increase since origination on the quantitative PD criterion.",
    "The deterioration is sector-wide rather than obligor-specific; the obligor's debt service has been met in full "
    "and the rating has moved less than the SICR threshold.",
    "The covenant shortfall is technical and was waived by the committee with a cure plan; cash flows still cover "
    "obligations. Not a SICR under Art 7.11; tracked as accepted risk with dated triggers.",
)

PROPOSALS = (
    {"watch_id": "ARW-P01", "obligor_id": "UAE-GMC-001", "name": "Gulf Meridian Contracting LLC", "group": "Meridian Holding",
     "sector": "Construction", "tier": 1, "currency": "AED", "exposure": 476.6, "pd12": 2.5, "pdl": 9.0, "lgd": 45.0,
     "rationale": "Approved with the counter-proposal structure (cap tied to Project 5; guarantees now, funded lines "
                  "tranched after the Project 2 collection). Project delays and working-capital strain are recorded as "
                  "accepted risk: watchlist, not Stage 2, because no payment has been missed to the bank, the bid-bond "
                  "line is contingent and the parent guarantee is being perfected. Revisit on any missed trigger.",
     "items": (("Project 2 payment received", "AED 23m certified payments collected", "2026-11-30", "Monthly", True, "due"),
               ("Extensions of time formalised", "EoT letters for Projects 1–3", "2027-01-11", "Monthly", False, "on track"),
               ("FY2026 audit by an approved auditor", "Auditor appointment letter", "2026-12-31", "Annual", True, "on track"),
               ("Parent guarantee perfected", "Executed guarantee and fresh legal opinion", "2026-12-13", "Monthly", True, "on track"),
               ("Retentions reclassified", "AED 79m retentions aged and reclassified", "2026-12-31", "Quarterly", False, "on track"),
               ("No further affiliate cheque returns", "Bureau returned cheques, Dubai affiliate", "2026-10-31", "Monthly", False, "due"),
               ("Funded usage within the stressed path", "Funded usage vs AED 80m lines", "2026-10-31", "Monthly", False, "on track"))},
    {"watch_id": "ARW-P02", "obligor_id": "UAE-ASB-001", "name": "Al Sahel Building Materials Trading LLC", "group": "Al Sahel",
     "sector": "Trading", "tier": 1, "currency": "AED", "exposure": 25.0, "pd12": 3.5, "pdl": 11.0, "lgd": 55.0,
     "rationale": "Renewal approved with routing kept at 2× and monthly tracking; the vehicle limit declined as "
                  "structured. The connected-obligor risk (Sahel Transport, Marwan Steel) and the qualified audit are "
                  "accepted risk pending the Art 6.12 economic-dependency assessment; no SICR while the borrower's "
                  "own facilities perform.",
     "items": (("Cross-default assessment answered", "Art 6.12 economic-dependency assessment", "2026-10-10", "One-off", True, "missed"),
               ("Monthly routing ≥ 1×", "Turnover routed vs the limit", "2026-10-31", "Monthly", False, "due"),
               ("Related-party receivable reduced by AED 20m", "Due from related parties", "2026-12-31", "Quarterly", False, "on track"),
               ("No connected-obligor deterioration", "Marwan Steel and group entities at CBRBR", "2026-10-31", "Monthly", True, "on track"),
               ("Vehicles registered before drawdown", "Registration to the borrower", "2026-11-30", "One-off", False, "on track"))},
)


def _h(*parts: object) -> int:
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:8], 16)


def _a_watch_names() -> list[str]:
    try:
        from backend.r9_data import read as r9  # type: ignore
        c = r9.classification("corporate")
        return sorted(c.loc[c["watch_status"] == "Accepted Risk Watch", "obligor_id"].unique().tolist())
    except Exception:  # noqa: BLE001 - domain not merged
        return []


def _due(ref: str, days: int) -> str:
    return (pd.Timestamp(ref) + pd.Timedelta(days=days)).strftime("%Y-%m-%d")


def frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    b = book("corporate")
    pc = b.period_column
    fac = pd.read_parquet(b.path(b.exposure_relation), filters=[(pc, "=", b.as_of)],
                          columns=["facility_id", "borrower_id", "ead_sar_mn", "ecl_sar_mn", "stage", "pd_pit_12m",
                                   "pd_lifetime", "lgd_pct", "dpd_days"])
    bor = pd.read_parquet(b.path(b.customer_relation), filters=[(pc, "=", b.as_of)],
                          columns=["borrower_id", "borrower_name", "group_name", "sector", "rating_current"])
    ews = pd.read_parquet(V5 / "data/ews/ews-saudi-corporate-20q-v4e2/ews_corp_exposure.parquet",
                          columns=["borrower_id", "reporting_quarter", "ews_score", "ews_band", "ews_reasons"],
                          filters=[("reporting_quarter", "=", b.as_of)])
    ob = ews.groupby("borrower_id").agg(score=("ews_score", "max"),
                                        reasons=("ews_reasons", lambda s: "; ".join(sorted({x for v in s for x in str(v).split("; ") if x}))))
    agg = fac.assign(e1=fac.ead_sar_mn * fac.pd_pit_12m * fac.lgd_pct / 100,
                     e2=fac.ead_sar_mn * fac.pd_lifetime * fac.lgd_pct / 100).groupby("borrower_id").agg(
        exposure=("ead_sar_mn", "sum"), ecl=("ecl_sar_mn", "sum"), stage=("stage", "max"), dpd=("dpd_days", "max"),
        facilities=("facility_id", "count"))
    # ECL if moved to Stage 2: lifetime ECL on Stage 1 facilities, current ECL elsewhere.
    s1 = fac[fac.stage == 1]
    life = (s1.ead_sar_mn * s1.pd_lifetime * s1.lgd_pct / 100).groupby(s1.borrower_id).sum()
    cur1 = s1.ecl_sar_mn.groupby(s1.borrower_id).sum()
    agg["ecl_stage2"] = agg["ecl"] - agg.index.map(cur1).fillna(0) + agg.index.map(life).fillna(0)
    agg = agg.join(ob).join(bor.set_index("borrower_id"))
    names = _a_watch_names()
    if names:
        pick = agg.loc[[n for n in names if n in agg.index]].sort_values("exposure", ascending=False).head(23)
    else:
        cand = agg[(agg.stage == 1) & (agg.dpd < 30) & (agg.score >= 4) & (agg.score < 10)].sort_values("exposure", ascending=False)
        pick = cand.groupby("sector", group_keys=False).head(2).sort_values("exposure", ascending=False).head(N_BOOK)
    clients, items = [], []
    for n, (oid, r) in enumerate(pick.iterrows(), 1):
        tier = 1 if n <= 6 else 2 if n <= 13 else 3
        wid = f"ARW-{n:03d}"
        approved = _due(REF_DATE, -(60 + _h(oid, "a") % 240))
        clients.append({"watch_id": wid, "obligor_id": oid, "book": "corporate", "source": "book", "name": r.borrower_name,
                        "group_name": r.group_name, "sector": r.sector, "rating": r.rating_current, "tier": tier,
                        "currency": "SAR", "exposure_sar_mn": round(float(r.exposure), 6), "ecl_sar_mn": round(float(r.ecl), 6),
                        "ecl_stage2_sar_mn": round(float(r.ecl_stage2), 6), "exposure_ccy_mn": round(float(r.exposure), 6),
                        "stage": int(r.stage), "ews_score": int(r.score), "approved_on": approved,
                        "approved_by": ("Credit Committee" if tier == 1 else "CRO") ,
                        "no_sicr_rationale": RATIONALES[_h(oid) % len(RATIONALES)], "period": b.as_of})
        reasons = str(r.reasons or "")
        chosen = [t for frag, t in TEMPLATES if frag.lower() in reasons.lower()][:3]
        chosen += list(DEFAULT_ITEMS)[: max(0, 2 - len(chosen)) + 1]
        for k, (trig, metric, freq, crit, art) in enumerate(chosen[:4], 1):
            x = _h(oid, k)
            off = (x % 120) - 30
            # Status: a few names deliberately escalate (2+ missed, or a critical item missed).
            if n in (3, 9) and k <= 2:
                status, off = "missed", -(10 + x % 40)
            elif n == 15 and crit:
                status, off = "missed", -(5 + x % 20)
            elif off < 0:
                status, off = "on track", 30 + x % 60
            else:
                status = "due" if off <= 21 else "on track"
            items.append({"item_id": f"{wid}-{k}", "watch_id": wid, "obligor_id": oid, "trigger": trig, "metric": metric,
                          "due_date": _due(REF_DATE, off), "frequency": freq, "status": status, "critical": bool(crit),
                          "article": art, "evidence": f"Early Warning: {reasons.split('; ')[0]}" if reasons else "Approval memo",
                          "period": b.as_of})
    for p in PROPOSALS:
        sar = p["exposure"] * AED_TO_SAR
        ecl1 = sar * p["pd12"] / 100 * p["lgd"] / 100
        ecl2 = sar * p["pdl"] / 100 * p["lgd"] / 100
        clients.append({"watch_id": p["watch_id"], "obligor_id": p["obligor_id"], "book": "corporate", "source": "proposal",
                        "name": p["name"], "group_name": p["group"], "sector": p["sector"], "rating": "BB-", "tier": p["tier"],
                        "currency": "AED", "exposure_sar_mn": round(sar, 6), "ecl_sar_mn": round(ecl1, 6),
                        "ecl_stage2_sar_mn": round(ecl2, 6), "exposure_ccy_mn": p["exposure"], "stage": 1, "ews_score": 0,
                        "approved_on": "2026-09-28", "approved_by": "Credit Committee", "no_sicr_rationale": p["rationale"],
                        "period": b.as_of})
        for k, (trig, metric, due, freq, crit, status) in enumerate(p["items"], 1):
            items.append({"item_id": f"{p['watch_id']}-{k}", "watch_id": p["watch_id"], "obligor_id": p["obligor_id"],
                          "trigger": trig, "metric": metric, "due_date": due, "frequency": freq, "status": status,
                          "critical": crit, "article": "CBUAE CRM Art. 6.12" if "Cross-default" in trig else "CBUAE CRM Art. 7.11",
                          "evidence": "Proposal review (Deal Desk)", "period": b.as_of})
    return pd.DataFrame(clients), pd.DataFrame(items)


DICTIONARY = {
    "watch_id": "Accepted Risk Watch entry ID.", "obligor_id": "Borrower ID (CB… in the book; UAE-… for proposal cases).",
    "source": "book (a borrower of the corporate book) or proposal (a Deal Desk proposal case, AED).",
    "tier": "1 (closest to SICR, monthly committee), 2, 3.", "exposure_sar_mn": {"description": "Exposure, SAR million (AED converted at the peg).", "unit": "SAR million"},
    "ecl_sar_mn": {"description": "Current ECL.", "unit": "SAR million"},
    "ecl_stage2_sar_mn": {"description": "ECL if moved to Stage 2 (lifetime PD on Stage 1 facilities).", "unit": "SAR million"},
    "no_sicr_rationale": "Why the concern was accepted without a SICR at approval.",
    "trigger": "The watch item: what must happen.", "due_date": "When it must happen.",
    "status": "on track / due (within 21 days) / missed.", "critical": "A missed critical item escalates on its own.",
    "book": "The credit book the client belongs to (corporate).",
    "name": "Client name.", "group_name": "Parent group name.", "sector": "Economic sector of the client.",
    "rating": "Internal rating at the as-of quarter.", "currency": "Currency of the original exposure (SAR or AED).",
    "exposure_ccy_mn": "Exposure in the original currency, million.", "stage": "Worst IFRS 9 stage of the client's facilities.",
    "ews_score": "Early Warning score (highest over the client's exposures).", "approved_on": "Date the concern was accepted at approval.",
    "approved_by": "Committee or officer that accepted it.", "period": "The book's as-of quarter (YYYYQn).",
    "item_id": "Watch item ID.", "metric": "What is measured to judge the trigger.", "frequency": "How often the item is checked.",
    "article": "CBUAE CRM article the item relates to.", "evidence": "Where the concern came from.",
}


def main() -> None:
    c, i = frames()
    OUT.mkdir(parents=True, exist_ok=True)
    c.to_parquet(OUT / "watch_client.parquet", index=False)
    i.to_parquet(OUT / "watch_item.parquet", index=False)
    man = {"domain_id": "watch", "release_id": "watch-v1", "as_of": book("corporate").as_of, "reference_date": REF_DATE,
           "row_counts": {"watch_client": len(c), "watch_item": len(i)}, "dictionary": DICTIONARY,
           "built_with": "ops/build_watch.py"}
    (OUT / "manifest.json").write_text(json.dumps(man, indent=1, sort_keys=True))
    print(json.dumps(man["row_counts"]))


if __name__ == "__main__":
    main()
