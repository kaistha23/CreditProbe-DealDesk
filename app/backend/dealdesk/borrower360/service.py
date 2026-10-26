"""Round B: Borrower 360 inside every deal and every customer file (not a separate screen).

    for_deal(pid)     the 360 of a deal's borrower
    for_cif(cif)      the 360 of a customer by the Bank's id (CIF / obligor id): Deal Desk's links to a borrower land here

What the Bank holds and what the uploads taught, in sections; every fact carries its source and date:

    deals        LOS: the deals and proposals on the desk, past credit decisions, business requests and credit responses written
                 (deal_desk.dd_deal + the live status, governance.gov_decision, the request and response stores)
    core         core banking: accounts, balances, conduct, returned cheques (deal_desk.dd_customer_account / dd_account_conduct /
                 dd_returned_cheque), or the deposit behaviour Deal Desk prices with (backend/dealdesk/deposits.py)
    limits       limits and utilisation: the limit tree (deal_desk.dd_facility_limit) or the book's facilities (cockpit.corp_facility_quarter)
    bureau       credit bureau: SIMAH-style reports, CBRBR and other banks' lines (bureau.*), or the book's bureau series
    collateral   collateral and security (deal_desk.dd_security, or the book's collateral)
    group        group and related parties (borrower_360.b360_entity, rel_group_quarter, the book's relationships)
    financials   the Bank's spread of the financials (deal_desk.dd_financials_detail, or the corporate book)
    learned      what the uploads taught: every link and figure the documents showed (Round G's graph), with document, page and date
    signals      counterparty exposure (Round G)

Reuses the readers that exist: backend/b360/service.py (the corporate book's tabs), backend/dealdesk/customer_packs.bank,
backend/dealdesk/group/sources (Data Domains with lineage). Writes nothing; cached ten minutes per subject.
"""
from __future__ import annotations

import re
import threading
import time
from typing import Any, Callable

from backend.dealdesk.graph.text import dmy

TTL = 600
_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_LOCK = threading.RLock()
AS_OF_Q = "2026Q2"
AS_OF_DATE = "2026-06-30"


class NotFound(LookupError):
    pass


# ------------------------------------------------------------------------------------------------ small builders

def src(kind: str, label: str, *, relation: str = "", domain: str = "", date: str = "", doc_id: str = "", doc_label: str = "",
        page: Any = None, line: Any = None, synthetic: bool = False, edge_id: str = "") -> dict[str, Any]:
    out = {"kind": kind, "label": label, "date": date or None, "date_label": dmy(date) if date else None}
    for k, v in (("relation", relation), ("domain", domain), ("doc_id", doc_id), ("doc_label", doc_label), ("page", page), ("line", line),
                 ("edge_id", edge_id)):
        if v not in (None, ""):
            out[k] = v
    if synthetic:
        out["synthetic"] = True
    return out


def rel_src(relation: str, label: str, date: str = AS_OF_DATE) -> dict[str, Any]:
    from backend.dealdesk.group import sources as S
    dom = (S.locate(relation) or {}).get("domain") or ""
    return src("bank", label, relation=relation, domain=dom, date=date)


def fact(label: str, value: Any, unit: str, source: dict[str, Any], note: str = "") -> dict[str, Any]:
    out = {"label": label, "value": value, "unit": unit, "source": source}
    if note:
        out["note"] = note
    return out


def col(key: str, label: str, unit: str = "text") -> dict[str, str]:
    return {"key": key, "label": label, "unit": unit}


def table(tid: str, title: str, columns: list[dict[str, str]], rows: list[dict[str, Any]], source: dict[str, Any]) -> dict[str, Any]:
    return {"id": tid, "title": title, "columns": columns, "rows": rows, "source": source}


def section(key: str, title: str, facts: list[dict[str, Any]] | None = None, tables: list[dict[str, Any]] | None = None,
            words: list[str] | None = None, empty: str = "") -> dict[str, Any]:
    facts, tables = facts or [], [t for t in (tables or []) if t["rows"]]
    return {"key": key, "title": title, "facts": facts, "tables": tables, "plain_words": words or [],
            "empty": "" if (facts or tables) else (empty or "Nothing held for this customer."), "n": len(facts) + sum(len(t["rows"]) for t in tables)}


def _read(rel: str, **flt: Any) -> list[dict[str, Any]]:
    from backend.dealdesk.group import sources as S
    try:
        return S.records(S.read(rel, **flt))
    except Exception:  # noqa: BLE001
        return []


def _num(v: Any) -> float | None:
    try:
        x = float(v)
        return None if x != x else x
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------------------------------------ the subject

def _deal_rows() -> list[dict[str, Any]]:
    from backend.dealdesk import deal_list
    try:
        return deal_list.all_rows()
    except Exception:  # noqa: BLE001
        return []


def _pack_by_cif(cif: str) -> dict[str, Any] | None:
    from backend.dealdesk import customer_packs as CP
    return next((c for c in CP._customers() if c.get("cif") == cif), None)  # noqa: SLF001


def _pack_by_pid(pid: str) -> dict[str, Any] | None:
    from backend.dealdesk import customer_packs as CP
    return next((c for c in CP._customers() if c.get("proposal_id") == pid), None)  # noqa: SLF001


def _in_book(cif: str) -> bool:
    if not re.fullmatch(r"CB\d+", cif or ""):
        return False
    try:
        from backend.b360 import service as B
        return bool(B.periods_of("corporate", cif))
    except Exception:  # noqa: BLE001
        return False


def subject_for_deal(pid: str) -> dict[str, Any]:
    from backend.dealdesk.group import deal as D
    try:
        p = D.get(pid)
    except KeyError as e:
        raise NotFound(f"No deal {pid}.") from e
    ob = p.get("obligor") or {}
    return {"cif": str(ob.get("obligor_id") or ""), "name": ob.get("name") or pid, "cr_number": re.sub(r"\D", "", str(ob.get("cr_number") or "")),
            "group_id": ob.get("group_id") or "", "group_name": ob.get("group_name") or "", "sector": ob.get("sector") or "",
            "rating": ob.get("internal_rating") or "", "existing": bool(ob.get("existing")), "proposal_id": pid, "pack": _pack_by_pid(pid)}


def subject_for_cif(cif: str) -> dict[str, Any]:
    cif = (cif or "").strip()
    if not cif:
        raise NotFound("No customer id given.")
    deals = [r for r in _deal_rows() if r.get("obligor_id") == cif]
    if deals:
        lead = sorted(deals, key=lambda r: str(r.get("received") or ""), reverse=True)[0]
        s = subject_for_deal(lead["proposal_id"])
        s["proposal_id"] = ""  # the customer's 360, not one deal's
        return s
    pack = _pack_by_cif(cif)
    ents = [e for e in _read("b360_entity") if e.get("borrower_id") == cif or e.get("entity_id") == cif]
    if _in_book(cif):
        from backend.b360 import service as B
        pr = B.profile("corporate", cif, B.resolve("corporate", cif, ""))
        return {"cif": cif, "name": pr.get("name") or cif, "cr_number": "", "group_id": pr.get("group_id") or "", "group_name": pr.get("group_name") or "",
                "sector": pr.get("segment") or "", "rating": pr.get("rating") or "", "existing": True, "proposal_id": "", "pack": pack}
    if pack:
        return {"cif": cif, "name": pack["name"], "cr_number": pack.get("cr_number") or "", "group_id": pack.get("group_id") or "",
                "group_name": pack.get("group_name") or "", "sector": pack.get("sector") or "", "rating": "", "existing": True, "proposal_id": "", "pack": pack}
    if ents:
        e = ents[0]
        return {"cif": cif, "name": e["entity_name"], "cr_number": re.sub(r"\D", "", str(e.get("licence_no") or "")), "group_id": e.get("group_id") or "",
                "group_name": e.get("group_name") or "", "sector": e.get("activity") or "", "rating": "", "existing": bool(e.get("borrower_id")),
                "proposal_id": "", "pack": None}
    from backend.dealdesk.graph import build, store as G
    build.ensure()
    n = G.by_cif(cif)
    if n:
        return {"cif": cif, "name": n["name"], "cr_number": n.get("cr") or "", "group_id": "", "group_name": "", "sector": (n.get("attrs") or {}).get("sector") or "",
                "rating": (n.get("attrs") or {}).get("rating") or "", "existing": False, "proposal_id": "", "pack": None}
    raise NotFound(f"No customer with id {cif} in Deal Desk, the Bank's data or the documents read.")


# ------------------------------------------------------------------------------------------------ sections

def _book_tab(cif: str, key: str) -> dict[str, Any] | None:
    if not _in_book(cif):
        return None
    from backend.b360 import service as B
    try:
        return B.tab("corporate", cif, B.resolve("corporate", cif, ""), key)
    except Exception:  # noqa: BLE001
        return None


def _book_period(cif: str) -> tuple[str, str]:
    from backend.b360 import service as B
    q = B.resolve("corporate", cif, "")
    return q, B.as_of(q)


def _from_tab(tab: dict[str, Any], relation: str, label: str, date: str, keep: tuple[str, ...] | None = None, max_rows: int = 12) -> tuple[list, list]:
    s = rel_src(relation, label, date)
    facts = [fact(f["label"], f["value"], f.get("unit") or "text", s) for f in tab.get("summary") or [] if f.get("value") not in (None, "")]
    tables = []
    for t in tab.get("tables") or []:
        if keep and t["id"] not in keep:
            continue
        tables.append(table(t["id"], t["title"], t["columns"], (t.get("rows") or [])[:max_rows], s))
    return facts, tables


def sec_deals(sj: dict[str, Any]) -> dict[str, Any]:
    cif = sj["cif"]
    mine = [r for r in _deal_rows() if r.get("obligor_id") == cif and cif]
    if not mine and sj.get("proposal_id"):
        mine = [r for r in _deal_rows() if r.get("proposal_id") == sj["proposal_id"]]
    reg = {r["proposal_id"]: r for r in _read("dd_deal", proposal_id=[m["proposal_id"] for m in mine])} if mine else {}
    rows = [{"proposal_id": r["proposal_id"], "received": str(r.get("received") or ""), "status": r.get("status"), "amount_sar_mn": r.get("amount_sar_mn"),
             "rm": r.get("rm") or "", "committee_date": str((reg.get(r["proposal_id"]) or {}).get("committee_date") or ""),
             "case_type": (reg.get(r["proposal_id"]) or {}).get("case_type") or r.get("case") or "", "source": r.get("source_label") or "",
             "current": r["proposal_id"] == sj.get("proposal_id")} for r in mine]
    dec = sorted(_read("gov_decision", borrower_id=cif), key=lambda r: str(r.get("decided_on") or ""), reverse=True)[:8] if cif else []
    drows = [{"decided_on": str(r.get("decided_on") or ""), "case_type": r.get("case_type"), "decision": str(r.get("decision") or "").replace("_", " "),
              "limit_sar_mn": r.get("limit_sar_mn"), "rating_at_decision": r.get("rating_at_decision"), "required_level": r.get("required_level"),
              "turnaround_days": r.get("turnaround_days")} for r in dec]
    papers: list[dict[str, Any]] = []
    try:
        from backend.dealdesk.rm_request import store as RS
        ids = {m["proposal_id"] for m in mine}
        for p in RS.listing():
            if (p.get("proposal_id") and p["proposal_id"] in ids) or (p.get("customer") and str(p["customer"]).lower() == str(sj["name"]).lower()):
                papers.append({"kind": "Business request", "id": p["request_id"], "written": str(p.get("written_at") or "")[:10], "by": p.get("rm") or "",
                               "status": p.get("status") or "", "amount_sar_mn": p.get("total_proposed")})
    except Exception:  # noqa: BLE001
        pass
    try:
        from backend.dealdesk.credit_response import service as CR
        for c in CR.cases():
            if (c.get("proposal_id") and c["proposal_id"] in {m["proposal_id"] for m in mine}) or str(c.get("customer") or "").lower() == str(sj["name"]).lower():
                papers.append({"kind": "Credit response", "id": c["case_id"], "written": str(c.get("created") or "")[:10], "by": c.get("by") or "",
                               "status": c.get("decision") or c.get("status") or "", "amount_sar_mn": None})
    except Exception:  # noqa: BLE001
        pass
    facts = []
    if mine:
        facts.append(fact("Deals on the desk", len(mine), "count", rel_src("dd_deal", "Deal register (LOS)", max(r["received"] for r in rows) or AS_OF_DATE)))
        last = sorted(rows, key=lambda r: r["received"], reverse=True)[0]
        facts.append(fact("Latest", f"{last['proposal_id']} · {str(last['status'] or '').replace('_', ' ')}", "text",
                          rel_src("dd_deal", "Deal register (LOS)", last["received"] or AS_OF_DATE)))
    if drows:
        facts.append(fact("Past credit decisions", len(dec), "count", rel_src("gov_decision", "Credit decisions (history)", drows[0]["decided_on"])))
    words = []
    if mine:
        words.append(f"{len(mine)} deal{'s' if len(mine) != 1 else ''} on the desk for {sj['name']}; "
                     + ", ".join(f"{r['proposal_id']} {str(r['status'] or '').replace('_', ' ')}" for r in rows[:4]) + ".")
    if drows:
        words.append(f"{len(dec)} past credit decision{'s' if len(dec) != 1 else ''} in the Bank's history, the latest on {dmy(drows[0]['decided_on'])}: "
                     f"{drows[0]['decision']} ({drows[0]['case_type']}).")
    if papers:
        words.append(f"{len(papers)} paper{'s' if len(papers) != 1 else ''} written for this customer (business requests and credit responses).")
    return section("deals", "Deals, proposals and decisions (LOS)", facts, [
        table("deals", "Deals on the desk", [col("proposal_id", "Deal"), col("received", "Received", "date"), col("status", "Status"),
                                             col("case_type", "Case"), col("amount_sar_mn", "Asked", "sar_mn"), col("rm", "RM"),
                                             col("committee_date", "Committee", "date")], rows, rel_src("dd_deal", "Deal register (LOS)")),
        table("decisions", "Past credit decisions", [col("decided_on", "Decided", "date"), col("case_type", "Case"), col("decision", "Decision"),
                                                     col("limit_sar_mn", "Limit", "sar_mn"), col("rating_at_decision", "Rating"),
                                                     col("required_level", "Authority"), col("turnaround_days", "Days", "number")], drows,
              rel_src("gov_decision", "Credit decisions (history)")),
        table("papers", "Papers written", [col("kind", "Paper"), col("id", "Id"), col("written", "Written", "date"), col("by", "By"), col("status", "Status"),
                                           col("amount_sar_mn", "Proposed", "sar_mn")], papers, src("engine", "Deal Desk papers (business requests, credit responses)")),
    ], words, "No deal, decision or paper on record for this customer.")


def _pid_for_bank(sj: dict[str, Any]) -> str:
    """The deal whose R12/R16 bank relations describe this customer (the Bank's file is keyed by proposal)."""
    if sj.get("proposal_id"):
        return sj["proposal_id"]
    mine = [r for r in _deal_rows() if r.get("obligor_id") == sj["cif"]]
    return mine[0]["proposal_id"] if mine else ((sj.get("pack") or {}).get("proposal_id") or "")


def sec_core(sj: dict[str, Any]) -> dict[str, Any]:
    pid = _pid_for_bank(sj)
    cif = sj["cif"]
    accts = [a for a in _read("dd_customer_account", proposal_id=pid) if a.get("obligor_id") == cif] if pid else []
    conduct = sorted(_read("dd_account_conduct", proposal_id=pid, obligor_id=cif), key=lambda r: str(r.get("month") or "")) if pid else []
    cheques = _read("dd_returned_cheque", proposal_id=pid) if pid else []
    facts, tables, words = [], [], []
    if accts or conduct:
        last12 = conduct[-12:]
        d_last = (str(last12[-1].get("month")) + "-28") if last12 else AS_OF_DATE
        if accts:
            s = rel_src("dd_customer_account", "Customer accounts (core banking)", AS_OF_DATE)
            facts += [fact("Accounts", len(accts), "count", s), fact("Balances", round(sum(_num(a.get("balance_mn")) or 0 for a in accts), 3), "sar_mn", s),
                      fact("Customer since", min(str(a.get("opened") or "")[:10] for a in accts), "date", s)]
            tables.append(table("accounts", "Accounts", [col("account_no", "Account"), col("label", "Type"), col("balance_mn", "Balance", "sar_mn"),
                                                         col("avg_balance_12m_mn", "Average, 12m", "sar_mn"), col("credits_12m_mn", "Credits, 12m", "sar_mn"),
                                                         col("opened", "Opened", "date")],
                                [{k: a.get(k) for k in ("account_no", "label", "balance_mn", "avg_balance_12m_mn", "credits_12m_mn", "opened")} for a in accts], s))
        if last12:
            s = rel_src("dd_account_conduct", "Account conduct (core banking)", d_last)
            ct = round(sum(_num(r.get("credit_turnover_mn")) or 0 for r in last12), 3)
            util = round(sum(_num(r.get("utilisation_pct")) or 0 for r in last12) / len(last12), 1)
            rc = int(sum(_num(r.get("returned_cheques_n")) or 0 for r in last12))
            pdd = int(max((_num(r.get("past_due_days_max")) or 0 for r in last12), default=0))
            facts += [fact("Credit turnover, 12 months", ct, "sar_mn", s), fact("Average utilisation, 12 months", util, "pct", s),
                      fact("Returned cheques, 12 months", rc, "count", s), fact("Worst days past due, 12 months", pdd, "days", s)]
            tables.append(table("conduct", "Conduct, last 12 months", [col("month", "Month"), col("credit_turnover_mn", "Credits", "sar_mn"),
                                                                       col("avg_balance_mn", "Average balance", "sar_mn"), col("utilisation_pct", "Utilisation", "pct"),
                                                                       col("returned_cheques_n", "Returned cheques", "number"), col("past_due_days_max", "Days past due", "number")],
                                [{k: r.get(k) for k in ("month", "credit_turnover_mn", "avg_balance_mn", "utilisation_pct", "returned_cheques_n", "past_due_days_max")}
                                 for r in reversed(last12)], s))
            words.append(f"Credit turnover SAR {ct:,.1f}m and average utilisation {util:,.0f}% over the 12 months to {dmy(d_last)[3:]}; "
                         f"{rc} returned cheque{'s' if rc != 1 else ''}, worst {pdd} days past due.")
        if cheques:
            s = rel_src("dd_returned_cheque", "Returned cheques (core banking)")
            tables.append(table("cheques", "Returned cheques", [col("cheque_date", "Date", "date"), col("amount_mn", "Amount", "sar_mn"),
                                                                col("reason", "Reason"), col("obligor_id", "Account holder")],
                                [{k: r.get(k) for k in ("cheque_date", "amount_mn", "reason", "obligor_id")} for r in cheques][:12], s))
        return section("core", "Core banking: accounts and conduct", facts, tables, words)
    # the deposits domain (core banking months and counterparties), read as Deal Desk's account-behaviour panel reads it
    if sj.get("existing") and cif:
        try:
            from backend.dealdesk import deposits
            dm = deposits._domain(cif)  # noqa: SLF001 - the deposits domain reader (Data Domains: deposits)
        except Exception:  # noqa: BLE001
            dm = None
        if dm and dm.get("months"):
            ms = dm["months"][-12:]
            d_last = str(ms[-1]["month"]) + "-28"
            s = src("bank", "Deposits (core banking)", relation="deposit_months", domain="deposits", date=d_last)
            ct = round(sum(_num(m.get("credit_turnover_sar_mn")) or 0 for m in ms), 3)
            ab = round(sum(_num(m.get("avg_balance_sar_mn")) or 0 for m in ms) / len(ms), 3)
            rc = int(sum(_num(m.get("cheques_returned_count")) or 0 for m in ms))
            ex = int(sum(_num(m.get("excess_days")) or 0 for m in ms))
            facts = [fact("Average balance, 12 months", ab, "sar_mn", s), fact("Credit turnover, 12 months", ct, "sar_mn", s),
                     fact("Returned cheques, 12 months", rc, "count", s), fact("Days over limit, 12 months", ex, "days", s)]
            cols = [col("month", "Month"), col("avg_balance_sar_mn", "Average balance", "sar_mn"), col("credit_turnover_sar_mn", "Credits", "sar_mn"),
                    col("debit_turnover_sar_mn", "Debits", "sar_mn"), col("cheques_returned_count", "Returned cheques", "number"),
                    col("excess_days", "Days over limit", "number"), col("peak_od_use_pct", "Peak overdraft use", "pct")]
            tables = [table("months", "Account months, last 12", cols, [{c["key"]: m.get(c["key"]) for c in cols} for m in reversed(ms)], s)]
            if dm.get("counterparties"):
                tables.append(table("payments", "Largest payers and payees (latest month)",
                                    [col("rank", "Rank", "number"), col("counterparty_name", "Counterparty"), col("direction", "In / out"),
                                     col("amount_sar_mn", "Amount", "sar_mn"), col("category", "Category")],
                                    [{k: c.get(k) for k in ("rank", "counterparty_name", "direction", "amount_sar_mn", "category")} for c in dm["counterparties"][:8]],
                                    src("bank", "Deposits (core banking)", relation="deposit_counterparties", domain="deposits", date=d_last)))
            return section("core", "Core banking: accounts and conduct", facts, tables,
                           [f"Average balance SAR {ab:,.1f}m and credit turnover SAR {ct:,.1f}m over the 12 months to {dmy(d_last)[3:]}; "
                            f"{rc} returned cheque{'s' if rc != 1 else ''}, {ex} day{'s' if ex != 1 else ''} over limit."])
    return section("core", "Core banking: accounts and conduct", empty=("New to bank: no accounts with the Bank." if not sj.get("existing")
                                                                       else "No account data published for this customer in Data Domains."))


def sec_limits(sj: dict[str, Any]) -> dict[str, Any]:
    pid = _pid_for_bank(sj)
    lim = _read("dd_facility_limit", proposal_id=pid) if pid else []
    if lim:
        s = rel_src("dd_facility_limit", "Facility limit tree (LOS)")
        tot = next((r for r in lim if r.get("level") == 0), None)
        facts = []
        if tot:
            facts = [fact("Limits", tot.get("existing_mn"), "sar_mn", s), fact("Outstanding", tot.get("outstanding_mn"), "sar_mn", s)]
            if _num(tot.get("existing_mn")):
                facts.append(fact("Utilisation", round(100 * (_num(tot.get("outstanding_mn")) or 0) / _num(tot.get("existing_mn")), 1), "pct", s,
                                  "outstanding over limits, stated"))
        rows = [{k: r.get(k) for k in ("limit_name", "level", "existing_mn", "outstanding_mn", "proposed_mn", "expiry_date")} for r in lim]
        return section("limits", "Limits and utilisation", facts, [table("limits", "Limit tree", [
            col("limit_name", "Limit"), col("level", "Level", "number"), col("existing_mn", "Existing", "sar_mn"), col("outstanding_mn", "Outstanding", "sar_mn"),
            col("proposed_mn", "Proposed", "sar_mn"), col("expiry_date", "Expiry", "date")], rows, s)])
    tab = _book_tab(sj["cif"], "facilities")
    if tab:
        q, d = _book_period(sj["cif"])
        f, t = _from_tab(tab, "corp_facility_quarter", f"Corporate book facilities ({q})", d)
        return section("limits", "Limits and utilisation", f, t)
    return section("limits", "Limits and utilisation", empty="No limits with the Bank." if not sj.get("existing") else "No limit data published.")


def sec_bureau(sj: dict[str, Any]) -> dict[str, Any]:
    pid = _pid_for_bank(sj)
    facts, tables = [], []
    rep = _read("bureau_entity_report", proposal_id=pid) if pid else []
    if rep:
        d = max(str(r.get("report_date") or "") for r in rep) or AS_OF_DATE
        s = rel_src("bureau_entity_report", "Bureau reports", d)
        tables.append(table("reports", "Bureau reports (entities and owners)", [col("entity_name", "Name"), col("entity_kind", "Kind"), col("report_date", "Report", "date"),
                                                                              col("score", "Score", "number"), col("outstanding_mn", "Outstanding", "sar_mn"),
                                                                              col("overdue_mn", "Overdue", "sar_mn"), col("overdue_days_max", "Days overdue", "number"),
                                                                              col("court_cases_n", "Court cases", "number"), col("worst_status", "Worst status")],
                            [{k: r.get(k) for k in ("entity_name", "entity_kind", "report_date", "score", "outstanding_mn", "overdue_mn", "overdue_days_max",
                                                    "court_cases_n", "worst_status")} for r in rep], s))
    cb = _read("bureau_cbrbr", proposal_id=pid) if pid else []
    if cb:
        s = rel_src("bureau_cbrbr", "Central-bank risk bureau (CBRBR)")
        cols = [c for c in cb[0].keys() if c not in ("proposal_id", "reporting_quarter", "rel_version", "published_at")][:8]
        tables.append(table("cbrbr", "CBRBR", [col(c, c.replace("_", " ").capitalize(), "sar_mn" if c.endswith("_mn") else "text") for c in cols],
                            [{c: r.get(c) for c in cols} for r in cb], s))
    ob = _read("other_bank_facility", proposal_id=pid) if pid else []
    if ob:
        s = rel_src("other_bank_facility", "Other banks' facilities")
        facts.append(fact("Other banks", len({r["bank_name"] for r in ob}), "count", s))
        facts.append(fact("Other banks' limits", round(sum(_num(r.get("declared_limit_mn")) or 0 for r in ob), 3), "sar_mn", s))
        tables.append(table("other_banks", "Other banks' facilities", [col("bank_name", "Bank"), col("entity_name", "Borrower"), col("facility_types", "Facilities"),
                                                                       col("declared_limit_mn", "Limit", "sar_mn"), col("declared_outstanding_mn", "Outstanding", "sar_mn"),
                                                                       col("bureau_outstanding_mn", "Per bureau", "sar_mn"), col("reconciliation_note", "Note")],
                            [{k: r.get(k) for k in ("bank_name", "entity_name", "facility_types", "declared_limit_mn", "declared_outstanding_mn",
                                                    "bureau_outstanding_mn", "reconciliation_note")} for r in ob], s))
    if not tables:
        tab = _book_tab(sj["cif"], "bureau")
        if tab:
            q, d = _book_period(sj["cif"])
            f, t = _from_tab(tab, "bureau_corp_quarter", f"Bureau series in the book ({q})", d, keep=("history",), max_rows=8)
            return section("bureau", "Credit bureau", f, t)
    return section("bureau", "Credit bureau", facts, tables, empty="No bureau data held by the Bank; see the SIMAH reports the uploads taught below.")


def sec_collateral(sj: dict[str, Any]) -> dict[str, Any]:
    pid = _pid_for_bank(sj)
    sec = _read("dd_security", proposal_id=pid) if pid else []
    if sec:
        s = rel_src("dd_security", "Security and support (LOS)")
        cols = [c for c in ("security_type", "description", "provider", "value_mn", "coverage_pct", "status", "valuation_date") if c in sec[0]]
        if not cols:
            cols = [c for c in sec[0].keys() if c not in ("proposal_id", "reporting_quarter", "rel_version", "published_at")][:7]
        return section("collateral", "Collateral and security", [fact("Security items", len(sec), "count", s)],
                       [table("security", "Security and support", [col(c, c.replace("_", " ").capitalize(), "sar_mn" if c.endswith("_mn") else "text") for c in cols],
                              [{c: r.get(c) for c in cols} for r in sec], s)])
    tab = _book_tab(sj["cif"], "collateral")
    if tab:
        q, d = _book_period(sj["cif"])
        f, t = _from_tab(tab, "corp_collateral_quarter", f"Corporate book collateral ({q})", d, keep=("items",))
        return section("collateral", "Collateral and security", f, t)
    return section("collateral", "Collateral and security", empty="No collateral held by the Bank.")


def sec_group(sj: dict[str, Any]) -> dict[str, Any]:
    ents = [e for e in _read("b360_entity") if sj.get("group_id") and e.get("group_id") == sj["group_id"]]
    if not ents:
        me = [e for e in _read("b360_entity") if e.get("borrower_id") == sj["cif"] or e.get("entity_id") == sj["cif"]]
        if me:
            ents = [e for e in _read("b360_entity") if e.get("group_id") == me[0].get("group_id")]
    if ents:
        s = rel_src("b360_entity", "Group entities (the Bank's file)")
        bad = [e for e in ents if str(e.get("credit_status") or "performing") != "performing"]
        rows = [{"entity_name": e["entity_name"], "role": e.get("role"), "borrower_id": e.get("borrower_id") or "",
                 "credit_status": str(e.get("credit_status") or "").replace("_", " "), "note": e.get("credit_status_note") or ""} for e in ents]
        words = [f"{len(ents)} entities in {ents[0].get('group_name') or 'the group'}; "
                 + (f"{len(bad)} not performing: " + "; ".join(f"{e['entity_name']} ({str(e['credit_status']).replace('_', ' ')})" for e in bad[:3]) + "."
                    if bad else "all performing.")]
        return section("group", "Group and related parties", [fact("Group", ents[0].get("group_name"), "text", s), fact("Entities", len(ents), "count", s),
                                                                fact("Not performing", len(bad), "count", s)],
                       [table("entities", "Group entities", [col("entity_name", "Entity"), col("role", "Role"), col("borrower_id", "Bank id"),
                                                             col("credit_status", "Standing"), col("note", "Note")], rows, s)], words)
    tab = _book_tab(sj["cif"], "group")
    if tab:
        q, d = _book_period(sj["cif"])
        f, t = _from_tab(tab, "rel_group_quarter", f"Group membership ({q})", d, keep=("members",))
        rel = _book_tab(sj["cif"], "relationships")
        if rel:
            f2, t2 = _from_tab(rel, "rel_edge_quarter", f"Relationships in the book ({q})", d, keep=("suppliers", "customers", "guarantees"))
            t += t2
        return section("group", "Group and related parties", f[:6], t)
    return section("group", "Group and related parties", empty="No group recorded by the Bank; see what the uploads taught below.")


def sec_financials(sj: dict[str, Any]) -> dict[str, Any]:
    pid = _pid_for_bank(sj)
    fin = _read("dd_financials_detail", proposal_id=pid) if pid else []
    fin = [r for r in fin if not r.get("entity_id") or r.get("entity_id") in (sj["cif"], "") or str(r.get("entity_role") or "subject") == "subject"] or fin
    if fin:
        s = rel_src("dd_financials_detail", "Financials spread by the Bank")
        cols = [c for c in ("period_label", "revenue_mn", "gross_profit_mn", "ebitda_mn", "net_profit_mn", "total_assets_mn", "total_equity_mn",
                            "total_debt_mn") if c in fin[0]]
        return section("financials", "Financials (the Bank's spread)", [], [table("spread", "Financials", [
            col(c, c.replace("_mn", "").replace("_", " ").capitalize(), "sar_mn" if c.endswith("_mn") else "text") for c in cols],
            [{c: r.get(c) for c in cols} for r in fin][:8], s)])
    tab = _book_tab(sj["cif"], "financials")
    if tab:
        q, d = _book_period(sj["cif"])
        f, t = _from_tab(tab, "corp_borrower_quarter", f"Corporate book financials ({q})", d, keep=("history",), max_rows=8)
        return section("financials", "Financials (the Bank's spread)", f, t)
    return section("financials", "Financials (the Bank's spread)", empty="No financials spread by the Bank; see the figures the uploads taught below.")


REL_LABEL = {"has_buyer": "Buyer", "has_supplier": "Supplier", "guaranteed_by": "Guarantor", "has_shareholder": "Shareholder",
             "has_director": "Director / manager", "has_ubo": "Ultimate owner", "borrows_from": "Lender", "banks_with": "Bank account",
             "has_project": "Project", "pledges": "Collateral", "member_of": "Group", "has_employer": "Employer", "related_party": "Related party",
             "contagion_link": "Linked borrower", "employer": "Employer", "consultant": "Consultant"}


def sec_learned(sj: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    from backend.dealdesk.graph import build, store as G
    build.ensure()
    node = None
    if sj.get("proposal_id"):
        d = G.deal(sj["proposal_id"])
        node = d["node_id"] if d else None
    if not node and sj.get("cif"):
        n = G.by_cif(sj["cif"])
        node = n["node_id"] if n else None
    if not node and (sj.get("name") or sj.get("cr_number")):
        with G.conn() as c:
            n = G.find(c, sj.get("name") or "", "company", cr=sj.get("cr_number") or "")
        node = n["node_id"] if n else None
    if not node:
        return section("learned", "What the uploads taught", empty="No document has been read for this customer yet."), None
    edges = [e for e in G.edges_of([node]) if e["source_kind"] in ("upload", "agent") and (e["src"] == node or e["dst"] == node)]
    others = G.nodes({e["dst"] if e["src"] == node else e["src"] for e in edges})
    links = []
    for e in edges:
        o = others.get(e["dst"] if e["src"] == node else e["src"]) or {}
        rl = REL_LABEL.get(e["rel"], e["rel"])
        if e["dst"] == node:
            rl = {"has_supplier": "Buys from this customer", "has_buyer": "Sells to this customer", "guaranteed_by": "Guaranteed by this customer"}.get(e["rel"], rl)
        a = e.get("attrs") or {}
        detail = "; ".join(str(x) for x in (f"{a['pct']}%" if a.get("pct") not in (None, "") else "", f"{a['share_pct']}% share" if a.get("share_pct") not in (None, "") else "",
                                             a.get("role") or "", a.get("product") or "", a.get("status") or "", a.get("relationship") or "") if x)
        links.append({"relation": rl, "name": o.get("name") or "", "kind": o.get("kind") or "", "detail": detail,
                      "document": e.get("doc_label") or e.get("source_label"), "page": e.get("page"), "line": e.get("line"), "date": e.get("seen_date"),
                      "by": e.get("author") or "", "synthetic": bool(e.get("synthetic")), "edge_id": e["edge_id"]})
    figs = []
    for f in G.facts_of(node):
        figs.append({"label": f["label"], "period": f.get("period") or "", "value": f["value_num"] if f["value_num"] is not None else f["value_text"],
                     "unit": {"SAR": "sar", "%": "pct", "date": "date"}.get(f.get("unit") or "", "text"), "document": f.get("doc_label"), "page": f.get("page"),
                     "line": f.get("line"), "date": f.get("seen_date"), "by": f.get("author") or ""})
    sts = [s for s in G.statuses_of([node]).get(node, []) if s["source_kind"] in ("upload", "agent")]
    docs = sorted({(lk["document"], lk["date"]) for lk in links if lk["document"]} | {(f["document"], f["date"]) for f in figs if f["document"]},
                  key=lambda x: str(x[0]))
    s_up = src("upload", "Documents read (intake reader)", date=max((str(x[1] or "") for x in docs), default=""))
    facts = ([fact("Documents read", len(docs), "count", s_up), fact("Links learned", len(links), "count", s_up), fact("Figures learned", len(figs), "count", s_up)]
             if (links or figs) else [])
    for s in sts[:3]:
        facts.append(fact("Standing per the documents", s["status"].replace("_", " "), "text",
                          src("upload", s.get("source_label") or "Document", doc_label=s.get("doc_label") or "", page=s.get("page"), date=s.get("seen_date") or ""),
                          s.get("note") or ""))
    words = []
    if links:
        by: dict[str, int] = {}
        for lk in links:
            by[lk["relation"]] = by.get(lk["relation"], 0) + 1
        words.append(f"{len(docs)} documents read taught {len(links)} links: " + ", ".join(f"{n} {k.lower()}{'s' if n != 1 and not k.endswith('s') else ''}"
                                                                                        for k, n in sorted(by.items(), key=lambda kv: -kv[1])[:6]) + ".")
    if figs:
        words.append(f"{len(figs)} figures copied as read (financial statements, bureau, CR, Nitaqat), each with its document and page.")
    tables = [
        table("links", "Links the documents showed", [col("relation", "Relation"), col("name", "Name"), col("detail", "Detail"), col("document", "Document"),
                                                      col("page", "Page", "number"), col("date", "Date", "date")], links,
              src("upload", "Documents read (intake reader)")),
        table("figures", "Figures the documents showed", [col("label", "Figure"), col("period", "Period"), col("value", "Value", "@unit"),
                                                          col("document", "Document"), col("page", "Page", "number"), col("date", "Date", "date")],
              [{**f, "unit": f["unit"]} for f in figs], src("upload", "Documents read (intake reader)")),
    ]
    return section("learned", "What the uploads taught", facts, tables, words, "No document has been read for this customer yet."), node


# ------------------------------------------------------------------------------------------------ assembly

SECTIONS: list[tuple[str, Callable[[dict[str, Any]], dict[str, Any]]]] = [
    ("deals", sec_deals), ("core", sec_core), ("limits", sec_limits), ("bureau", sec_bureau), ("collateral", sec_collateral),
    ("group", sec_group), ("financials", sec_financials)]


def _build(sj: dict[str, Any]) -> dict[str, Any]:
    t0 = time.time()
    out_secs = []
    for key, fn in SECTIONS:
        try:
            out_secs.append(fn(sj))
        except Exception as e:  # noqa: BLE001 - one source never takes the 360 down
            out_secs.append(section(key, key.capitalize(), empty=f"Not available: {type(e).__name__}: {str(e)[:120]}"))
    node = None
    try:
        learned, node = sec_learned(sj)
    except Exception as e:  # noqa: BLE001
        learned = section("learned", "What the uploads taught", empty=f"Not available: {type(e).__name__}: {str(e)[:120]}")
    out_secs.append(learned)
    from backend.dealdesk.graph import signals as SG
    sig = SG.for_node(node, sj.get("proposal_id") or "") if node else []
    pack = sj.get("pack")
    held = [s for s in out_secs if s["key"] != "learned" and s["n"]]
    words = [f"{sj['name']}{' (' + sj['cif'] + ')' if sj.get('cif') else ''}: "
             + ("an existing customer of the Bank" if sj.get("existing") else "new to the Bank")
             + (f", {sj['sector']}" if sj.get("sector") else "") + (f", group {sj['group_name']}" if sj.get("group_name") else "") + ".",
             f"The Bank holds {', '.join(s['title'].split(':')[0].split(' (')[0].lower() for s in held) or 'nothing yet'}; "
             f"{learned['n']} facts learned from the documents."]
    if node:  # the customer's own standing, as the documents and the Bank's data show it
        from backend.dealdesk.graph import store as G
        own = [x for x in G.statuses_of([node]).get(node, []) if x["status"] in ("default", "classified", "past_due", "restructured", "watch")]
        if own:
            st = own[0]
            words.append(f"Standing: {st['status'].replace('_', ' ')} — {st.get('note') or ''} ({st.get('doc_label') or st.get('source_label', '').split(' (')[0]}, "
                         f"{dmy(st.get('seen_date') or '')}).")
    hi = [s for s in sig if s["severity"] == "high"]
    if sig:
        words.append(f"Counterparty exposure: {len(sig)} signal{'s' if len(sig) != 1 else ''}"
                     + (f", {len(hi)} high; first: {hi[0]['title']}." if hi else f"; first: {sig[0]['title']}."))
    return {"subject": {k: sj.get(k) for k in ("cif", "name", "cr_number", "group_id", "group_name", "sector", "rating", "existing", "proposal_id")}
            | {"pack_key": (pack or {}).get("key"), "node_id": node},
            "as_of": AS_OF_DATE, "as_of_label": dmy(AS_OF_DATE), "plain_words": words, "sections": out_secs,
            "signals": sig, "signals_summary": SG.summary(sig), "ms": int((time.time() - t0) * 1000)}


def _cached(key: str, fn: Callable[[], dict[str, Any]], refresh: bool) -> dict[str, Any]:
    with _LOCK:
        hit = _CACHE.get(key)
        if hit and not refresh and time.time() - hit[0] < TTL:
            return hit[1]
    out = fn()
    with _LOCK:
        _CACHE[key] = (time.time(), out)
    return out


def for_deal(pid: str, refresh: bool = False) -> dict[str, Any]:
    return _cached(f"deal:{pid}", lambda: _build(subject_for_deal(pid)), refresh)


def for_cif(cif: str, refresh: bool = False) -> dict[str, Any]:
    return _cached(f"cif:{cif}", lambda: _build(subject_for_cif(cif)), refresh)


def clear() -> None:
    with _LOCK:
        _CACHE.clear()
