"""D10 Revenue truth check: reported revenue against the cash that actually came in, at this bank and at other banks
(open banking), and against the sales declared for VAT; the gap and what it implies.

Method (deterministic)
  * Reported revenue: the latest audited full year of the subject entity (dd_financials_detail, standalone, audited),
    else the latest actual year of dd_obligor_financials, else the proposal's financials (dd_deal).
  * Inflows over the last 12 months of account data (2025-07 .. 2026-06):
      this bank     dd_account_conduct.credit_turnover_mn (R12 obligors) or deposits.dep_month.credit_turnover_sar_mn
                    (book obligors); new-to-bank names have none
      other banks   dd_external_turnover open_banking rows (credit inflows, less transfers between own accounts)
  * Sales-backed inflows = (this bank + other banks - own-account transfers) / 1.15 (receipts include 15% VAT).
  * Coverage = sales-backed inflows / reported revenue. Supported >= 95%; partly supported 85-95%; not supported < 85%.
    Gap = reported revenue - sales-backed inflows (only when positive).
  * VAT check: taxable sales declared in the four quarterly VAT returns (dd_external_turnover vat_return) / revenue.
  * What it implies: if the gap is revenue that does not exist, EBITDA falls by the gap x the EBITDA margin; DSCR and
    Debt/EBITDA are restated on the selected structure (the deal's own debt service and debt, engine.analyse).
"""
from __future__ import annotations

import functools
import json
from typing import Any

from backend.dealdesk import engine
from backend.dealdesk.intel2 import common as C
from backend.dealdesk.intel2 import seed as S

VAT = S.VAT
SUPPORTED, PARTLY = 0.95, 0.85


def _revenue_fig(pid: str) -> tuple[float | None, dict[str, Any] | None, str]:
    fd = [r for r in C.rows("dd_financials_detail", proposal_id=pid) if r.get("entity_scope") == "standalone" and r.get("period_kind") == "audited"
          and r.get("revenue_mn") is not None]
    if fd:
        r = max(fd, key=lambda r: r["year"])
        return float(r["revenue_mn"]), C.rfig("dd_financials_detail", r, "revenue_mn", "SAR m", f"Reported revenue {r['period_label']} (audited)"), r["period_label"]
    of = [r for r in C.rows("dd_obligor_financials", proposal_id=pid) if r.get("kind") == "actual"]
    if of:
        r = max(of, key=lambda r: r["year"])
        return float(r["revenue_sar_mn"]), C.bfig("dd_obligor_financials", r, "revenue_sar_mn", "SAR m", f"Reported revenue FY{r['year']}"), f"FY{r['year']}"
    try:
        p = C.proposal(pid)
        ys = [y for y in p["financials"]["years"] if y["kind"] == "actual" and y.get("revenue")]
        if ys:
            return float(ys[-1]["revenue"]), C.efig(pid, float(ys[-1]["revenue"]), "SAR m", f"Reported revenue FY{ys[-1]['year']}", "proposal financials"), f"FY{ys[-1]['year']}"
    except Exception:  # noqa: BLE001
        pass
    return None, None, ""


@functools.lru_cache(maxsize=64)
def _revenue(pid: str, which: str, tkey: str, pv: str) -> str:
    st = C.structure(pid, which, json.loads(tkey) or None)
    p = C.proposal(pid)
    tsrc = {"structure": st["kind"]}
    ob = p["obligor"].get("obligor_id") or ""
    deal_row = C.C.register_row(pid)
    ob = deal_row.get("obligor_id") or ob
    rev, rev_fig, period = _revenue_fig(pid)
    own, own_rel, own_n = S.own_turnover(pid, ob)
    if own_rel == "dd_account_conduct":
        r0 = C.rows("dd_account_conduct", proposal_id=pid)
        own_src = C.row_source("dd_account_conduct", r0[0], "credit_turnover_mn") if r0 else None
    elif own_rel == "dep_month" and own_n:
        r0 = C.records(C.frame("dep_month", obligor_id=ob).head(1))
        own_src = C.bfig("dep_month", r0[0], "credit_turnover_sar_mn")["source"] if r0 else None
    else:
        own_src = None
    ext = C.rows("dd_external_turnover", proposal_id=pid)
    ob_rows = [r for r in ext if r["source_kind"] == "open_banking"]
    vat_rows = [r for r in ext if r["source_kind"] == "vat_return"]
    banks: dict[str, dict[str, Any]] = {}
    for r in ob_rows:
        b = banks.setdefault(r["provider"], {"inflows": 0.0, "transfers": 0.0, "months": 0, "row": r})
        b["inflows"] += float(r["credit_inflows_mn"] or 0)
        b["transfers"] += float(r["own_account_transfers_mn"] or 0)
        b["months"] += 1
    other = sum(b["inflows"] for b in banks.values())
    transfers = sum(b["transfers"] for b in banks.values())
    vat = sum(float(r["taxable_sales_mn"] or 0) for r in vat_rows)
    backed = (own + other - transfers) / (1 + VAT)
    cov = backed / rev if rev else None
    gap = max(0.0, rev - backed) if rev else None
    vat_cov = vat / rev if rev and vat_rows else None
    verdict = ("no data" if cov is None or (not ob_rows and not own_n) else "supported" if cov >= SUPPORTED else
               "partly supported" if cov >= PARTLY else "not supported")
    a = C.analysis(pid, st["terms"])
    la = engine.latest_actual(p)
    ebitda, rv = C.finite(la.get("ebitda")), C.finite(la.get("revenue"))
    margin = (ebitda / rv) if ebitda and rv else None
    implied = None
    if gap and margin and ebitda:
        cut = gap * margin * (rv / rev if rev and rv else 1.0)  # gap in the proposal's revenue units
        e2 = max(ebitda - cut, 1e-9)
        ds, lev = C.finite(a["metrics"]["dscr_post"]), C.finite(a["metrics"]["debt_ebitda_post"])
        implied = {"ebitda_cut": C.efig(pid, round(cut, 4), "SAR m", "EBITDA if the gap is revenue that does not exist (cut)", "intel2.revenue", tsrc),
                   "dscr_after": C.efig(pid, round(ds * e2 / ebitda, 4) if ds is not None else None, "x", "DSCR restated", "intel2.revenue", tsrc),
                   "leverage_after": C.efig(pid, round(lev * ebitda / e2, 4) if lev is not None else None, "x", "Debt/EBITDA restated", "intel2.revenue", tsrc),
                   "dscr_now": C.efig(pid, ds, "x", "DSCR on the reported figures", "engine.analyse", tsrc),
                   "leverage_now": C.efig(pid, lev, "x", "Debt/EBITDA on the reported figures", "engine.analyse", tsrc)}
    src_ob = C.row_source("dd_external_turnover", ob_rows[0], "credit_inflows_mn") if ob_rows else None
    src_vat = C.row_source("dd_external_turnover", vat_rows[0], "taxable_sales_mn") if vat_rows else None
    lines = []
    if own_src:
        lines.append({"label": "This bank (credit turnover)", "kind": "own", "value": C.fig(round(own, 4), "SAR m", own_src, f"Credit turnover at this bank, {own_n} months")})
    for name, b in sorted(banks.items()):
        lines.append({"label": f"{name} (open banking)", "kind": "other_bank", "months": b["months"],
                      "value": C.fig(round(b["inflows"], 4), "SAR m", C.row_source("dd_external_turnover", b["row"], "credit_inflows_mn"), f"Inflows at {name}")})
    if transfers and src_ob:
        lines.append({"label": "Less: transfers between own accounts", "kind": "transfers", "value": C.fig(round(-transfers, 4), "SAR m", src_ob, "Own-account transfers")})
    tot_src = own_src or src_ob or C.deal_source(pid)
    out_lines = {"inflows": lines,
                 "sales_backed": C.fig(round(backed, 4), "SAR m", tot_src, "Sales-backed inflows (net of VAT)"),
                 "revenue": rev_fig,
                 "coverage": C.fig(round(cov, 4) if cov is not None else None, "share", tot_src, "Inflows / reported revenue"),
                 "gap": C.fig(round(gap, 4) if gap is not None else None, "SAR m", tot_src, "Revenue not backed by inflows"),
                 "vat_sales": C.fig(round(vat, 4), "SAR m", src_vat, "Taxable sales declared (4 VAT returns)") if src_vat else None,
                 "vat_coverage": C.fig(round(vat_cov, 4), "share", src_vat, "VAT sales / reported revenue") if src_vat and vat_cov is not None else None}
    name = p["obligor"]["name"]
    if verdict == "no data":
        head = f"No account inflows are on file for {name}, so reported revenue cannot be checked against cash."
        pl = C.plain("This checks the revenue in the accounts against the money that actually came into the client's bank accounts.",
                     "There is no account or open-banking data for this client yet.", "Ask the client for open-banking consent before committee.")
    else:
        head = (f"{name} reports revenue of {C.mn(rev)} ({period}); the cash that came in over the last 12 months backs {C.pct(cov, 0)} of it "
                f"({C.mn(backed)} after VAT, {len(banks)} other bank{'s' if len(banks) != 1 else ''} by open banking"
                + (f", {C.mn(own)} at this bank" if own_n else "") + f"): {verdict}."
                + (f" Gap {C.mn(gap)}." if gap and verdict != "supported" else "")
                + (f" VAT returns declare {C.pct(vat_cov, 0)} of the revenue." if vat_cov is not None else "")
                + (f" If the gap is not real revenue, DSCR falls from {implied['dscr_now']['value']:.2f}x to {implied['dscr_after']['value']:.2f}x."
                   if implied and verdict != "supported" and implied["dscr_now"]["value"] and implied["dscr_after"]["value"] else ""))
        pl = C.plain(
            "This checks the revenue in the accounts against the money that actually came into the client's bank accounts.",
            f"Cash in covers {C.pct(cov, 0)} of the reported {C.mn(rev, dp=0)}" + (f": {C.mn(gap, dp=0)} is not backed." if gap and verdict != "supported" else "."),
            ("Ask the RM to explain the gap and size the deal on the cash figure." if verdict == "not supported" else
             "Ask for the bank statements behind the gap." if verdict == "partly supported" else "Revenue is backed by cash; no action."))
    out = {"proposal_id": pid, "obligor": name, "structure": {k: st[k] for k in ("kind", "label", "note")}, "headline": head, "plain": pl,
           "verdict": verdict, "period": {"revenue": period, "inflows": f"{S.MONTHS[0]} to {S.MONTHS[-1]}"}, **out_lines,
           "implied": implied if verdict in ("partly supported", "not supported") else None,
           "monthly": _monthly(pid, ob_rows, own_rel, ob),
           "note": "Open-banking inflows and VAT returns are a fictional demo seed (dd_external_turnover); this bank's turnover is the bank's own data.",
           "method": __doc__.split("Method", 1)[1].strip()}
    return json.dumps(out, default=str)


def _monthly(pid: str, ob_rows: list[dict[str, Any]], own_rel: str, ob: str) -> list[dict[str, Any]]:
    own = {}
    if own_rel == "dd_account_conduct":
        own = {r["month"]: float(r["credit_turnover_mn"] or 0) for r in C.rows("dd_account_conduct", proposal_id=pid)}
    elif own_rel == "dep_month":
        f = C.frame("dep_month", obligor_id=ob)
        own = dict(zip(f["month"], f["credit_turnover_sar_mn"].astype(float))) if len(f) else {}
    oth: dict[str, float] = {}
    for r in ob_rows:
        oth[r["period"]] = oth.get(r["period"], 0.0) + float(r["credit_inflows_mn"] or 0)
    return [{"month": m, "this_bank": round(own.get(m, 0.0), 4), "other_banks": round(oth.get(m, 0.0), 4)} for m in S.MONTHS]


def revenue(pid: str, which: str = "selected", terms: dict[str, Any] | None = None) -> dict[str, Any]:
    from backend.dealdesk import params
    pid = C.resolve_id(pid)
    C.proposal(pid)
    return json.loads(_revenue(pid, which, json.dumps(terms or {}, sort_keys=True, default=str), C.cache_key()))
