"""Credit proposals: the 15 seeded ones (data/dealdesk/proposals.json) and those users add (var/dealdesk).

A status change or a new proposal is written to the Deal Desk store only; the seeded file is
never modified. Proposals are validated against the schema in docs/v5/DEALDESK_API.md.
"""
from __future__ import annotations

import copy
import functools
import json
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any

from backend.dealdesk import paths
from backend.dealdesk.seed import GRADES, MASTER_SCALE
from backend.v5common.ratings import rank

STATUSES = ("new", "in_review", "counter_offered", "approved", "declined")
FACILITY_TYPES = ("term_loan", "revolver", "performance_lg", "financial_lg", "trade_lc")
STRUCTURES = ("conventional", "murabaha", "tawarruq", "ijara", "musharaka")
PROFILES = ("equal", "bullet", "balloon", "sculpted")
COVENANTS = ("none", "standard", "enhanced")
COLLATERAL_TYPES = ("cash", "real_estate", "plant_equipment", "receivables", "shares", "vehicles")
GUARANTEE_TYPES = ("corporate", "personal", "government", "kafalah", "bank")
_LOCK = threading.Lock()


class ProposalError(ValueError):
    def __init__(self, errors: list[dict[str, str]]):
        super().__init__("; ".join(f"{e['field']}: {e['message']}" for e in errors))
        self.errors = errors


@functools.lru_cache(maxsize=1)
def _seeded() -> dict[str, dict[str, Any]]:
    d = json.loads((paths.DATA / "proposals.json").read_text())
    return {p["proposal_id"]: p for p in d["proposals"]}


def _db() -> sqlite3.Connection:
    con = sqlite3.connect(paths.store_path())
    con.execute("CREATE TABLE IF NOT EXISTS proposals (id TEXT PRIMARY KEY, body TEXT, created TEXT, owner TEXT)")
    con.execute("CREATE TABLE IF NOT EXISTS status (id TEXT, status TEXT, note TEXT, by TEXT, at TEXT)")
    return con


def _status_overrides(con: sqlite3.Connection) -> dict[str, str]:
    out: dict[str, str] = {}
    for pid, st in con.execute("SELECT id, status FROM status ORDER BY rowid"):
        out[pid] = st
    return out


def all_proposals() -> dict[str, dict[str, Any]]:
    out = {k: copy.deepcopy(v) for k, v in _seeded().items()}
    with _LOCK:
        con = _db()
        try:
            for pid, body in con.execute("SELECT id, body FROM proposals ORDER BY id"):
                out[pid] = json.loads(body)
            for pid, st in _status_overrides(con).items():
                if pid in out:
                    out[pid]["status"] = st
        finally:
            con.close()
    return out


def get(pid: str) -> dict[str, Any]:
    p = all_proposals().get(pid)
    if p is None:
        # PLAN_R12 §1.2 (I21, Session U): one deal registry; a pipeline-set (PL-xx) or R12 demo deal resolves here too.
        from backend.dealdesk import registry_lookup
        return registry_lookup.extra_proposal(pid)
    return p


def fx(currency: str) -> float:
    from backend.dealdesk import params
    return 1.0 if currency == "SAR" else float(params.rows("capital")["usd_sar"])


def summary(p: dict[str, Any]) -> dict[str, Any]:
    a, ob = p["ask"], p["obligor"]
    return {"proposal_id": p["proposal_id"], "status": p["status"], "obligor_name": ob["name"],
            "obligor_id": ob["obligor_id"], "existing": bool(ob.get("existing")), "sector": ob["sector"],
            "rating": ob["internal_rating"], "rm": p["rm"], "facility_type": a["facility_type"], "structure": a["structure"],
            "currency": a["currency"], "amount": a["amount"], "amount_sar_mn": round(a["amount"] * fx(a["currency"]), 4),
            "tenor_years": a["tenor_years"], "received": p["received"], "case": p.get("case", "")}


def listing(status: str = "", sector: str = "", rating: str = "", rm: str = "", min_amount: float | None = None,
            max_amount: float | None = None, q: str = "") -> list[dict[str, Any]]:
    rows = [summary(p) for p in all_proposals().values()]
    if status:
        rows = [r for r in rows if r["status"] == status]
    if sector:
        rows = [r for r in rows if r["sector"].lower() == sector.lower()]
    if rating:
        rows = [r for r in rows if r["rating"] == rating]
    if rm:
        rows = [r for r in rows if r["rm"].lower() == rm.lower()]
    if min_amount is not None:
        rows = [r for r in rows if r["amount_sar_mn"] >= min_amount]
    if max_amount is not None:
        rows = [r for r in rows if r["amount_sar_mn"] <= max_amount]
    if q:
        ql = q.lower()
        rows = [r for r in rows if ql in r["obligor_name"].lower() or ql in r["proposal_id"].lower()]
    return sorted(rows, key=lambda r: r["proposal_id"])


# ------------------------------------------------------------------ validation

def validate_terms(t: dict[str, Any], prefix: str = "terms") -> list[dict[str, str]]:
    e: list[dict[str, str]] = []

    def bad(field: str, msg: str) -> None:
        e.append({"field": f"{prefix}.{field}", "message": msg})

    if t.get("facility_type") not in FACILITY_TYPES:
        bad("facility_type", f"one of {', '.join(FACILITY_TYPES)}")
    if t.get("structure") not in STRUCTURES:
        bad("structure", f"one of {', '.join(STRUCTURES)}")
    if t.get("currency") not in ("SAR", "USD"):
        bad("currency", "SAR or USD")
    if t.get("amortisation") not in PROFILES:
        bad("amortisation", f"one of {', '.join(PROFILES)}")
    if t.get("covenant_package") not in COVENANTS:
        bad("covenant_package", f"one of {', '.join(COVENANTS)}")
    num = {"amount": (0.01, 1e6), "tenor_years": (1, 10), "grace_years": (0, 9), "balloon_pct": (0, 100),
           "margin_bps": (0, 2000), "upfront_fee_bps": (0, 1000), "commitment_fee_bps": (0, 500), "commission_bps": (0, 1000),
           "utilisation_pct": (0, 100), "funded_share_pct": (0, 100), "cash_margin_pct": (0, 100),
           "guarantee_coverage_pct": (0, 100)}
    for k, (lo, hi) in num.items():
        v = t.get(k)
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not (lo <= v <= hi):
            bad(k, f"a number in [{lo}, {hi}]")
    if not e:
        if int(t["tenor_years"]) != t["tenor_years"] or int(t["grace_years"]) != t["grace_years"]:
            bad("tenor_years", "tenor and grace are whole years")
        if t["grace_years"] >= t["tenor_years"]:
            bad("grace_years", "grace must be shorter than the tenor")
        if t.get("unfunded_type") not in ("performance_lg", "financial_lg", "trade_lc"):
            bad("unfunded_type", "performance_lg, financial_lg or trade_lc")
    if not isinstance(t.get("collateral_ids", []), list):
        bad("collateral_ids", "a list of collateral ids")
    # R5 D4 levers (absent = neutral)
    num2 = {"prepayment_fee_bps": (0, 1000), "hold_pct": (1, 100), "insurance_cover_pct": (0, 100), "receivables_assignment_pct": (0, 100)}
    for k, (lo, hi) in num2.items():
        if k in t:
            v = t[k]
            if not isinstance(v, (int, float)) or isinstance(v, bool) or not (lo <= v <= hi):
                bad(k, f"a number in [{lo}, {hi}]")
    if t.get("rate_type", "floating") not in ("floating", "fixed"):
        bad("rate_type", "floating or fixed")
    if t.get("review_cycle_months", 12) not in (12, 6, 3):
        bad("review_cycle_months", "12, 6 or 3")
    from backend.dealdesk import params as _params
    items = _params.rows("covenant_items")["items"]
    ci = t.get("covenant_items", [])
    if not isinstance(ci, list) or any(x not in items for x in ci):
        bad("covenant_items", f"a list drawn from {', '.join(items)}")
    cs = t.get("cross_sell", [])
    lines = _params.rows("relationship")["lines"]
    if not isinstance(cs, list) or any(x not in lines for x in cs):
        bad("cross_sell", f"a list drawn from {', '.join(lines)}")
    from backend.dealdesk.deposit_requirement.term import validate as _deposit  # Round D
    e += _deposit(t, prefix)
    return e


def validate(p: dict[str, Any]) -> list[dict[str, str]]:
    e: list[dict[str, str]] = []
    ob = p.get("obligor") or {}
    for k in ("name", "sector", "internal_rating"):
        if not ob.get(k):
            e.append({"field": f"obligor.{k}", "message": "required"})
    if ob.get("internal_rating") and ob["internal_rating"] not in GRADES:
        e.append({"field": "obligor.internal_rating", "message": "a grade AAA..C"})
    if ob.get("external_rating") not in (None, "") and ob["external_rating"] not in GRADES:
        e.append({"field": "obligor.external_rating", "message": "a grade AAA..C, or empty for unrated"})
    ys = (p.get("financials") or {}).get("years") or []
    if not any(y.get("kind") == "actual" for y in ys):
        e.append({"field": "financials.years", "message": "at least one actual year"})
    for y in ys:
        for k in ("revenue", "ebitda", "total_debt", "debt_service"):
            if not isinstance(y.get(k), (int, float)):
                e.append({"field": f"financials.{y.get('year')}.{k}", "message": "a number (SAR m)"})
    e += validate_terms(p.get("ask") or {}, "ask")
    sec = p.get("security") or {}
    ids = set()
    for c in sec.get("collateral", []):
        f = f"security.collateral.{c.get('collateral_id')}"
        if not c.get("collateral_id"):
            e.append({"field": "security.collateral", "message": "every item needs a collateral_id"})
        if c.get("type") not in COLLATERAL_TYPES:
            e.append({"field": f, "message": f"type one of {', '.join(COLLATERAL_TYPES)}"})
        v = c.get("value")
        if not isinstance(v, (int, float)) or isinstance(v, bool) or v < 0:
            e.append({"field": f, "message": "value: a number >= 0 (millions)"})
        if c.get("currency", "SAR") not in ("SAR", "USD"):
            e.append({"field": f, "message": "currency SAR or USD"})
        ids.add(c.get("collateral_id"))
    for cid in (p.get("ask") or {}).get("collateral_ids", []):
        if cid not in ids:
            e.append({"field": "ask.collateral_ids", "message": f"{cid} is not in security.collateral"})
    gids = set()
    for g in sec.get("guarantees", []):
        f = f"security.guarantees.{g.get('guarantee_id')}"
        if not g.get("guarantee_id"):
            e.append({"field": "security.guarantees", "message": "every guarantee needs a guarantee_id"})
        if g.get("type") not in GUARANTEE_TYPES:
            e.append({"field": f, "message": f"type one of {', '.join(GUARANTEE_TYPES)}"})
        if not g.get("guarantor"):
            e.append({"field": f, "message": "guarantor: the guarantor's name"})
        if g.get("guarantor_rating") not in GRADES:
            e.append({"field": f, "message": "guarantor_rating: a grade AAA..C"})
        cv = g.get("coverage_pct")
        if not isinstance(cv, (int, float)) or isinstance(cv, bool) or not 0 <= cv <= 100:
            e.append({"field": f, "message": "coverage_pct: a number in [0, 100]"})
        gids.add(g.get("guarantee_id"))
    gid = (p.get("ask") or {}).get("guarantee_id")
    if gid and gid not in gids:
        e.append({"field": "ask.guarantee_id", "message": f"{gid} is not in security.guarantees"})
    return e


def create(p: dict[str, Any], owner: str = "") -> dict[str, Any]:
    p = copy.deepcopy(p)
    p.setdefault("status", "new")
    p.setdefault("rm", owner or "")
    p.setdefault("business_unit", "Corporate Banking")
    p.setdefault("received", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    sec = p.setdefault("security", {})
    sec.setdefault("collateral", [])
    sec.setdefault("guarantees", [])
    sec.setdefault("covenant_package", (p.get("ask") or {}).get("covenant_package", "standard"))
    sec.setdefault("covenants", [])
    p.setdefault("business_case", {"ancillary_income_sar_mn_pa": {}})
    ob = p.setdefault("obligor", {})
    ob.setdefault("existing", False)
    ob.setdefault("simah_flag", "clear")
    ob.setdefault("segment", ob.get("sector", ""))
    if ob.get("internal_rating") in MASTER_SCALE:
        ob["pd_master_scale"] = MASTER_SCALE[ob["internal_rating"]]
    ob.setdefault("existing_exposure_sar_mn", 0.0)
    errs = validate(p)
    if errs:
        raise ProposalError(errs)
    with _LOCK:
        con = _db()
        try:
            n = con.execute("SELECT COUNT(*) FROM proposals").fetchone()[0]
            pid = f"DD-{101 + n:03d}"
            p["proposal_id"] = pid
            if not ob.get("obligor_id"):
                ob["obligor_id"] = f"DN{101 + n:03d}"
            if not ob.get("group_id"):
                ob["group_id"] = f"DG{101 + n:03d}"
            if not ob.get("group_name"):
                ob["group_name"] = ob["name"]
            p["deal_currency"] = p["ask"]["currency"]
            con.execute("INSERT INTO proposals VALUES (?, ?, ?, ?)",
                        (pid, json.dumps(p), datetime.now(timezone.utc).isoformat(), owner))
            con.commit()
        finally:
            con.close()
    return p


def set_status(pid: str, status: str, note: str = "", by: str = "") -> dict[str, Any]:
    if status not in STATUSES:
        raise ProposalError([{"field": "status", "message": f"one of {', '.join(STATUSES)}"}])
    get(pid)
    with _LOCK:
        con = _db()
        try:
            con.execute("INSERT INTO status VALUES (?, ?, ?, ?, ?)", (pid, status, note, by, datetime.now(timezone.utc).isoformat()))
            con.commit()
        finally:
            con.close()
    return get(pid)


def memo_path(pid: str):
    p = get(pid)
    path = paths.DATA / "memos" / p.get("memo", "")
    return path if p.get("memo") and path.exists() else None


__all__ = ["STATUSES", "all_proposals", "create", "get", "listing", "set_status", "summary", "validate", "validate_terms", "rank"]
