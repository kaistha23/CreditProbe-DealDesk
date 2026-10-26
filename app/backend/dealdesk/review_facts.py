"""R11 R2: the evidence a review checks claims against, for one subject.

A subject is either a prepared proposal case (PRP-A-GMC, PRP-B-ASB: proposal_cases.py plus the bank's
evidence in data/dealdesk/review/evidence/<case>.json) or a Deal Desk proposal (DD-01..15 and user
proposals: proposals.json, the corporate book at the as-of quarter, the deposits domain).

`facts(subject_id)` returns one nested dict; rules in rules.json address it by dotted path
("case.financials.backlog", "ev.projects", "book.ead", "memo.approve_all").
"""
from __future__ import annotations

import functools
import json
import re
from typing import Any

from backend.dealdesk import desk_params, params, paths, proposal_review, proposals
from backend.dealdesk.proposal_cases import AS_OF as CASE_AS_OF, CASES
from backend.dealdesk.review_ledger import REVIEW_DIR, _slug, claim_index, ledger

#: The book quarter's end date (DD proposals are checked against the 2026Q2 book).
BOOK_AS_OF = "2026-06-30"
REVIEW_AS_OF = "2026-10-13"


def is_case(sid: str) -> bool:
    return sid in CASES


def known(sid: str) -> bool:
    if is_case(sid):
        return True
    try:
        proposals.get(sid)
        return True
    except KeyError:
        return False


# ------------------------------------------------------------------ memo bytes

def uploaded_memo_path(sid: str):
    import re as _re
    return paths.VAR / "review_memos" / (_re.sub(r"[^A-Za-z0-9_-]", "_", sid) + ".docx")


def save_uploaded_memo(sid: str, data: bytes) -> None:
    """A memo uploaded for review (POST /proposals/{id}/review/memo): kept in var/dealdesk/review_memos and read first."""
    f = uploaded_memo_path(sid)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(data)
    _ledger_cached.cache_clear()


def memo_bytes(sid: str) -> bytes | None:
    up = uploaded_memo_path(sid)
    if up.exists():
        return up.read_bytes()
    if is_case(sid):
        f = paths.V5 / "demo_inputs" / "proposals" / CASES[sid]["file_name"]
        return f.read_bytes() if f.exists() else proposal_review.proposal_docx(sid)
    f = paths.DATA / "memos" / f"{sid}.docx"
    if f.exists():
        return f.read_bytes()
    try:
        mp = proposals.memo_path(sid)
        if mp and mp.exists():
            return mp.read_bytes()
    except Exception:  # noqa: BLE001 - no stored memo for this proposal
        pass
    try:  # a user proposal without a memo file: the house-style memo written from its record
        from backend.dealdesk_thread.ingest import write_memo
        return write_memo(proposals.get(sid))
    except Exception:  # noqa: BLE001
        return None


@functools.lru_cache(maxsize=64)
def _ledger_cached(sid: str, size: int) -> dict[str, Any]:
    data = memo_bytes(sid)
    return ledger(data) if data else {"lines": [], "claims": [], "sections": [], "counts": {"lines": 0, "figures": 0, "assertions": 0}}


def memo_ledger(sid: str) -> dict[str, Any]:
    data = memo_bytes(sid)
    return _ledger_cached(sid, len(data or b""))


# ------------------------------------------------------------------ book (DD proposals)

@functools.lru_cache(maxsize=1)
def _book() -> tuple[Any, Any]:
    import pandas as pd
    fac = pd.read_parquet(paths.book_relation("corp_facility_quarter"),
                          columns=["borrower_id", "borrower_name", "reporting_quarter", "ead_sar_mn", "stage", "dpd_days", "facility_id"])
    bor = pd.read_parquet(paths.book_relation("corp_borrower_quarter"),
                          columns=["borrower_id", "reporting_quarter", "rating_current", "watchlist_flag", "sector", "group_id"])
    return fac, bor


def _book_obligor(oid: str) -> dict[str, Any] | None:
    fac, bor = _book()
    f = fac[(fac.borrower_id == oid) & (fac.reporting_quarter == paths.AS_OF)]
    b = bor[(bor.borrower_id == oid) & (bor.reporting_quarter == paths.AS_OF)]
    if f.empty and b.empty:
        return None
    qs = sorted(fac.reporting_quarter.unique())[-4:]
    f4 = fac[(fac.borrower_id == oid) & (fac.reporting_quarter.isin(qs))]
    return {"ead": round(float(f.ead_sar_mn.sum()), 4), "facilities": int(len(f)), "stage_max": int(f.stage.max()) if len(f) else 1,
            "dpd_max_4q": int(f4.dpd_days.max()) if len(f4) else 0,
            "rating": str(b.rating_current.iloc[0]) if len(b) else None,
            "watchlist": bool(b.watchlist_flag.iloc[0]) if len(b) else False,
            "name": str(f.borrower_name.iloc[0]) if len(f) else ""}


def _connected(p: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    me = p["obligor"].get("obligor_id")
    for cid in p["obligor"].get("connected_parties") or []:
        if cid == me:
            continue
        b = _book_obligor(cid)
        if b:
            out.append({"id": cid, **b})
    return out


def _seeded_conduct(pid: str, ids: set[str]) -> dict[str, Any] | None:
    """R16 x: the Bank's own account conduct of the deal (dd_account_conduct, seeded per obligor and month) for the subject
    only: a connected party's cheques are not the borrower's. None when the deal has no such rows (R12-R15 deals)."""
    try:
        from backend.dealdesk.data import store
        rows = store.dd_read("dd_account_conduct", proposal_id=pid)
    except Exception:  # noqa: BLE001 - relation not built
        return None
    if len({str(r.get("obligor_id")) for r in rows if r.get("obligor_id")}) < 2:
        # one obligor only (R12-R15 deals): nothing to separate, the account fixture stays the source as before
        return None
    ids = {str(x) for x in ids if x}
    if not any(str(r.get("obligor_id")) in ids for r in rows):
        try:
            from backend.dealdesk.data import store
            ids |= {str(d.get("cif")) for d in store.dd_read("dd_deal", proposal_id=pid) if d.get("cif")}
        except Exception:  # noqa: BLE001
            pass
    mine = sorted((r for r in rows if str(r.get("obligor_id")) in ids), key=lambda r: str(r.get("month") or ""))
    if not mine:
        return None
    last12 = mine[-12:]
    return {"months": len(last12), "returned_cheques": int(sum(r.get("returned_cheques_n") or r.get("returned_cheques") or 0 for r in last12)),
            "returned_cheques_sar_mn": round(float(sum(r.get("returned_cheques_mn") or 0 for r in last12)), 4),
            "excess_days": int(max([r.get("past_due_days_max") or 0 for r in last12] or [0])),
            "obligor_id": str(last12[-1].get("obligor_id")), "period": f"{last12[0].get('month')} to {last12[-1].get('month')}",
            "source": f"dd_account_conduct ({last12[-1].get('obligor_id')}, {len(last12)} months to {last12[-1].get('month')})"}


def _conduct(pid: str, ids: set[str] | None = None) -> dict[str, Any] | None:
    seeded = _seeded_conduct(pid, ids or set())
    if seeded is not None:
        return seeded
    try:
        from backend.dealdesk import deposits
        r = deposits.behaviour(pid)
    except Exception:  # noqa: BLE001 - deposits domain not built: conduct unverifiable
        return None
    m = r.get("months") or []
    if not m:
        return None
    last12 = m[-12:]
    return {"months": len(last12), "returned_cheques": int(sum(x.get("cheques_returned_count") or 0 for x in last12)),
            "returned_cheques_sar_mn": round(float(sum(x.get("cheques_returned_sar_mn") or 0 for x in last12)), 4),
            "excess_days": int(sum(x.get("excess_days") or 0 for x in last12)), "source": r.get("source", "Deposits domain")}


# ------------------------------------------------------------------ facts

def _memo_facts(cl: list[dict[str, Any]]) -> dict[str, Any]:
    return {k: c["value"] for k, c in claim_index(cl).items()}


def _params() -> dict[str, Any]:
    return {"desk": desk_params.rows(), "doa": params.rows("doa"), "returns": params.rows("returns"),
            "aed_sar": float(desk_params.rows()["aed_sar"])}


def _case_facts(cid: str, cl: list[dict[str, Any]]) -> dict[str, Any]:
    c = CASES[cid]
    ev = json.loads((REVIEW_DIR / "evidence" / f"{cid}.json").read_text())
    approved = json.loads((REVIEW_DIR / "approved_auditors.json").read_text())["auditors"]
    los = {_slug(f["name"]): f for f in c["facilities"]}
    rp = proposal_review.raroc(c, c["facilities"])
    return {"subject": {"kind": "case", "id": cid, "name": c["borrower"], "group": c["group"], "sector": c["sector"],
                        "rating": c["rating"], "tier": c["tier"], "currency": c["currency"], "as_of": CASE_AS_OF,
                        "amount_ccy": sum(f["proposed"] for f in c["facilities"]),
                        "amount_sar": sum(f["proposed"] for f in c["facilities"]) * float(desk_params.rows()["aed_sar"]),
                        "existing_ccy": sum(f["existing"] for f in c["facilities"])},
            "case": c, "ev": ev, "los": los, "approved_auditors": approved,
            "economics": {"raroc": rp["raroc"], "hurdle": rp["hurdle"], "clears": rp["clears_hurdle"]},
            "memo": _memo_facts(cl), "params": _params(), "as_of": CASE_AS_OF}


def _fin_by_col(p: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for y in p["financials"]["years"]:
        out[str(y["year"]) + ("_p" if y["kind"] != "actual" else "")] = y
    return out


def _dd_facts(pid: str, cl: list[dict[str, Any]]) -> dict[str, Any]:
    p = proposals.get(pid)
    o, a = p["obligor"], p["ask"]
    fx = proposals.fx(a["currency"])
    book = _book_obligor(o["obligor_id"]) if o.get("existing") else None
    acts = [y for y in p["financials"]["years"] if y["kind"] == "actual"]
    last = acts[-1] if acts else p["financials"]["years"][0]
    covenants = {re.sub(r"[^a-z]+", "_", c["type"].lower()).strip("_"): c["threshold"] for c in p["security"].get("covenants") or []}
    try:
        from backend.dealdesk import engine
        m = engine.analyse(p, None)["metrics"]
        metrics = {k: m.get(k) for k in ("dscr_post", "debt_ebitda_post", "ltv", "lifetime_raroc", "hurdle", "clears_hurdle", "sva",
                                           "day_one_ecl", "rwa_y1", "amount_sar_mn")}
    except Exception:  # noqa: BLE001
        metrics = {}
    return {"subject": {"kind": "dd", "id": pid, "name": o["name"], "group": o.get("group_name"), "sector": o["sector"],
                        "rating": o["internal_rating"], "tier": "", "currency": a["currency"], "as_of": BOOK_AS_OF,
                        "amount_ccy": a["amount"], "amount_sar": a["amount"] * fx,
                        "existing_ccy": o.get("existing_exposure_sar_mn", 0.0) / fx},
            "dd": p, "obligor": o, "ask": a, "fin": _fin_by_col(p), "fin_last": last, "covenants": covenants,
            "collateral": p["security"].get("collateral") or [], "guarantees": p["security"].get("guarantees") or [],
            "book": book, "connected": _connected(p) if o.get("existing") else [], "conduct": _conduct(pid, {o.get("obligor_id"), o.get("cif"), o.get("book_id"), p.get("cif")}),
            "metrics": metrics, "memo": _memo_facts(cl), "params": _params(), "as_of": BOOK_AS_OF}


def facts(sid: str) -> dict[str, Any]:
    led = memo_ledger(sid)
    f = _case_facts(sid, led["claims"]) if is_case(sid) else _dd_facts(sid, led["claims"])
    f["ledger"] = led
    return f


def resolve(f: dict[str, Any], path: str) -> Any:
    """A dotted path into the facts; KeyError when any step is missing (-> unverifiable)."""
    cur: Any = f
    for part in path.split("."):
        if isinstance(cur, dict):
            if part not in cur:
                raise KeyError(path)
            cur = cur[part]
        elif isinstance(cur, list) and part.isdigit():
            i = int(part)
            if i >= len(cur):
                raise KeyError(path)
            cur = cur[i]
        else:
            raise KeyError(path)
    return cur
