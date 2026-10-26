"""The renewal autopilot queue: every renewal due in the window, prepared and classified (R14 backlog #5).

Clean renewals carry their one-page note; exceptions carry the criteria that fired and the full paper on request. Ordered
exceptions first by EAD (what the CCO must look at), then clean ones by renewal date.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from backend.dealdesk.book import core, sources as book_sources
from backend.dealdesk.intel.renewal import criteria, note, pack
from backend.intel.calls import reads

LIMITS = [
    "Renewal dates come from the Book (origination date + tenor, or the deal's review date); facilities without either are not in the queue.",
    "Financials are the latest quarter of the corporate book (cockpit.corp_borrower_quarter) against the same quarter a year earlier; "
    "audited statements and the RM's projections are not part of the refresh.",
    "Conduct is monthly (deposits.dep_month): a salary run paid late inside the same month cannot be seen; a missed month can.",
    "The stress tier is read from dd_monitoring_plan: most back-book facilities have no stress run on file, so the tier criteria rarely fire.",
    "Approval conditions and review findings exist only for facilities with a Deal Desk file.",
]


def _label(i: str) -> str:
    return criteria.BY_ID[i]["label"]


def _lower(s: str) -> str:
    """Sentence case inside a sentence, keeping acronyms (IFRS, DSCR, RAROC)."""
    w = s.split(" ", 1)
    return s if w[0].isupper() and len(w[0]) > 1 else s[:1].lower() + s[1:]


def _line(r: pd.Series) -> str:
    if r.classification == "clean":
        extra = f"; renew with: {', '.join(_label(i) for i in r.commercial_fired)}" if r.commercial_fired else ""
        return f"Clean: all credit criteria pass{extra}"
    return "; ".join(_label(i) for i in r.credit_fired[:3]) + (f" (+{len(r.credit_fired) - 3} more)" if len(r.credit_fired) > 3 else "")


def queue(days: int = pack.WINDOW_DAYS, cls: str = "all", q: str = "", sector: str = "", limit: int = 50, offset: int = 0,
          ref: str | None = None, scope: str = "material") -> dict[str, Any]:
    """scope='material' (default, R14 G): renewals of names whose relationship EAD is at or above the J9 materiality floor
    (Deal Desk Parameters → relationship · book), the same rule as the landing's Renewals counter; scope='all': the whole back book."""
    if cls not in ("all", "clean", "exception"):
        raise ValueError("cls must be all, clean or exception")
    if scope not in ("material", "all"):
        raise ValueError("scope must be material or all")
    t, pending = pack.prepare(ref, days)
    floor = float(core.materiality()["materiality_floor_sar_mn"])
    whole_n, whole_ead = int(len(t)), float(t.ead_sar_mn.sum()) if len(t) else 0.0
    if scope == "material" and len(t):
        rel = t.relationship_ead_sar_mn if "relationship_ead_sar_mn" in t else t.groupby("borrower_id").ead_sar_mn.transform("sum")
        t = t[rel >= floor]
    counts = {k: int((t.classification == k).sum()) for k in ("clean", "exception")}
    ead = {k: float(t.loc[t.classification == k, "ead_sar_mn"].sum()) for k in ("clean", "exception")}
    by_crit = {c["id"]: int(t.fired.map(lambda x, i=c["id"]: i in x).sum()) for c in criteria.CRITERIA}
    s = t
    if cls != "all":
        s = s[s.classification == cls]
    if q:
        ql = q.lower()
        s = s[s.borrower_name.str.lower().str.contains(ql, regex=False) | s.facility_id.str.lower().str.contains(ql, regex=False)]
    if sector:
        s = s[s.sector == sector]
    s = s.assign(_x=(s.classification == "exception").astype(int)).sort_values(["_x", "ead_sar_mn", "days_to_renewal"], ascending=[False, False, True])
    page = s.iloc[offset: offset + limit]
    rows = []
    for _, r in page.iterrows():
        rows.append({"facility_id": r.facility_id, "borrower_id": r.borrower_id, "borrower_name": r.borrower_name, "sector": r.sector,
                     "product": r.product_type, "renewal_date": r.renewal_date, "days_to_renewal": r.days_to_renewal,
                     "ead_sar_mn": r.ead_sar_mn, "limit_sar_mn": r.limit_sar_mn, "stage": r.stage, "rating_now": r.rating_now,
                     "ews_band": r.ews_band, "classification": r.classification, "fired": list(r.credit_fired), "commercial": list(r.commercial_fired),
                     "line": _line(r), "proposal_id": reads.py(r.proposal_id) if isinstance(r.proposal_id, str) else None,
                     "output": "one-page note" if r.classification == "clean" else "full paper"})
    refd = str(t.ref_date.iloc[0]) if len(t) else ""
    names = int(t.borrower_id.nunique()) if len(t) else 0
    what = (f"{len(t):,} material renewals ({names:,} names with relationship EAD at least SAR {floor:,.0f}m)" if scope == "material"
            else f"{len(t):,} renewals")
    summary = (f"{what} due in the next {days} days (SAR {t.ead_sar_mn.sum():,.0f}m EAD): {counts['clean']:,} clean on a one-page "
               f"note, {counts['exception']:,} exceptions for the CCO (SAR {ead['exception']:,.0f}m).") if len(t) else f"No {'material ' if scope == 'material' else ''}renewals due in the next {days} days."
    top = sorted(((k, v) for k, v in by_crit.items() if v and criteria.BY_ID[k]["kind"] == "credit"), key=lambda kv: -kv[1])[:3]
    if top:
        summary += " Most common exception reasons: " + ", ".join(f"{_lower(_label(k))} ({v:,})" for k, v in top) + "."
    if scope == "material" and whole_n > len(t):
        summary += f" The other {whole_n - len(t):,} renewals in the back book (smaller names) are in the full list."
    return reads.clean({"window_days": days, "ref_date": refd, "scope": scope, "materiality_floor_sar_mn": floor, "names": names,
                        "whole_book_total": whole_n, "whole_book_ead_sar_mn": whole_ead, "as_of": str(t.as_of_quarter.iloc[0]) if len(t) else "", "summary": summary,
                        "counts": counts, "ead_sar_mn": ead, "total": int(len(s)), "by_criterion": by_crit, "criteria": criteria.describe(),
                        "rows": rows, "offset": offset, "limit": limit, "pending": pending, "data_limits": LIMITS,
                        "sources": reads.lineage() + book_sources.lineage(), "sectors": sorted(x for x in t.sector.dropna().unique().tolist() if x)})


def _row(fid: str, ref: str | None = None, days: int = pack.WINDOW_DAYS) -> pd.Series:
    t, _ = pack.prepare(ref, days)
    m = t[t.facility_id == fid]
    if not len(m):
        f, _ = core.frame(ref)
        if not (f.facility_id == fid).any():
            raise KeyError(fid)
        raise LookupError(f"{fid} is not due for renewal in the next {days} days.")
    return m.iloc[0]


def item(fid: str, ref: str | None = None, days: int = pack.WINDOW_DAYS) -> dict[str, Any]:
    """One renewal: the prepared review, and its output (the note when clean; the paper link when an exception)."""
    r = _row(fid, ref, days)
    rv = pack.review(r)
    out: dict[str, Any] = {"review": rv, "classification": rv["classification"]}
    if rv["classification"] == "clean":
        out["note"] = note.write(rv, {"text": r.get("action_text") if isinstance(r.get("action_text"), str) else None})
    else:
        out["paper"] = {"available": True, "action": f"POST /api/v1/dealdesk/intel/renewals/{fid}/paper",
                        "proposal_id": rv.get("proposal_id"),
                        "text": "Exception: the full proposal and committee paper are prepared from the deal's file "
                                + ("(on file)." if rv.get("proposal_id") else "(the renewal file is opened from the Book first).")}
    out["sources"] = reads.lineage() + book_sources.lineage()
    return reads.clean(out)


def note_docx(fid: str, ref: str | None = None) -> tuple[bytes, str]:
    r = _row(fid, ref)
    rv = pack.review(r)
    if rv["classification"] != "clean":
        raise LookupError(f"{fid} is an exception: it gets the full paper, not a one-page note.")
    return note.docx(rv, note.write(rv, {"text": r.get("action_text") if isinstance(r.get("action_text"), str) else None}))


def paper(fid: str, by: str, ref: str | None = None) -> dict[str, Any]:
    r = _row(fid, ref)
    if r.classification != "exception":
        raise LookupError(f"{fid} is clean: it gets the one-page note.")
    res = note.full_paper(fid, by)
    res["fired"] = [{"id": i, "label": _label(i)} for i in r.credit_fired]
    return reads.clean(res)


def _np(x: Any) -> Any:
    return None if isinstance(x, float) and np.isnan(x) else x
