"""The facts of each pending deal that the policy checks read. Figures are the engine's: the Deal Desk engine
(`engine.analyse`) on the deal's proposal record, never a model.

    rows = pending()        # one dict per pending deal (new, in review, counter-offered), cached under var/dealdesk/rulebook/
    one(pid)                # the same for one deal (any status)

Each fact carries the source it came from (`sources`). A deal the engine cannot price keeps the facts it has; the checks
mark the rest "not given".
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import threading
from datetime import date
from typing import Any, Iterator

from backend.dealdesk import paths

AS_OF = date(2026, 10, 18)  # the demo's today (proposal_check.engine.AS_OF)
_LOCK = threading.RLock()
_MEM: dict[str, Any] = {}
_OVERRIDE: list[list[dict[str, Any]] | None] = [None]


@contextlib.contextmanager
def use(rows: list[dict[str, Any]]) -> Iterator[None]:
    """Tests: read these facts instead of the pipeline."""
    prev = _OVERRIDE[0]
    _OVERRIDE[0] = rows
    try:
        yield
    finally:
        _OVERRIDE[0] = prev


def _cache_file():
    d = paths.VAR / "rulebook"
    d.mkdir(parents=True, exist_ok=True)
    return d / "deal_facts.json"


def _pending_rows() -> list[dict[str, Any]]:
    from backend.dealdesk.proposal_check import batch
    return batch.pending()


def one(pid: str, deal: dict[str, Any] | None = None) -> dict[str, Any]:
    from backend.dealdesk import engine, proposals
    deal = deal or {}
    out: dict[str, Any] = {"proposal_id": pid, "customer": deal.get("obligor_name") or "", "rm": deal.get("rm") or "",
                           "status": deal.get("status") or "", "sources": {}}
    try:
        p = proposals.get(pid)
    except Exception as e:  # noqa: BLE001
        out["error"] = f"no proposal record ({type(e).__name__})"
        return out
    ob, ask = p.get("obligor") or {}, p.get("ask") or {}
    out.update({"customer": out["customer"] or ob.get("name") or "", "rm": out["rm"] or p.get("rm") or "", "status": out["status"] or p.get("status") or "",
                "sector": ob.get("sector") or "", "rating": ob.get("internal_rating") or "", "facility_type": ask.get("facility_type") or "",
                "amount": ask.get("amount"), "currency": ask.get("currency") or p.get("currency") or "SAR", "tenor_years": ask.get("tenor_years"),
                "existing": bool(ob.get("existing"))})
    out["sources"].update({k: "proposal record (Deal Desk)" for k in ("sector", "rating", "facility_type", "amount", "tenor_years")})
    col = [c for c in (p.get("security") or {}).get("collateral", []) if c.get("pledged_in_ask", True)]
    cv = sum(float(c.get("value") or 0) for c in col)
    out["collateral_value"] = cv or None
    out["collateral_cover"] = round(cv / float(ask["amount"]), 4) if cv and ask.get("amount") else None
    out["ltv"] = round(float(ask["amount"]) / cv, 4) if cv and ask.get("amount") else None
    dates = [str(c["valuation_date"])[:10] for c in col if c.get("valuation_date")]
    if dates:
        oldest = min(dates)
        out["valuation_date"] = oldest
        out["valuation_age_days"] = (AS_OF - date.fromisoformat(oldest)).days
        out["sources"]["valuation_age_days"] = f"oldest valuation of the pledged collateral ({oldest}) to {AS_OF.isoformat()}"
    if cv:
        out["sources"]["collateral_cover"] = "pledged collateral value / amount asked (proposal record)"
        out["sources"]["ltv"] = "amount asked / pledged collateral value (proposal record)"
    try:
        m = engine.analyse(p)["metrics"]
        out.update({"dscr_post": m.get("dscr_post"), "debt_ebitda_post": m.get("debt_ebitda_post"), "lifetime_raroc": m.get("lifetime_raroc"),
                    "hurdle": m.get("hurdle")})
        for k in ("dscr_post", "debt_ebitda_post", "lifetime_raroc", "hurdle"):
            out["sources"][k] = "Deal Desk engine (engine.analyse on the proposal record)"
    except Exception as e:  # noqa: BLE001 - a deal the engine cannot price keeps its other facts
        out["engine_error"] = f"{type(e).__name__}: {str(e)[:120]}"
    return out


def _key(rows: list[dict[str, Any]]) -> str:
    sig = json.dumps(sorted((str(r["proposal_id"]), str(r.get("status")), str(r.get("published_at") or "")) for r in rows))
    try:
        from backend.dealdesk import desk_params
        sig += json.dumps(desk_params.rows(), sort_keys=True, default=str)
    except Exception:  # noqa: BLE001
        pass
    return hashlib.sha1(sig.encode()).hexdigest()[:16]


def pending(refresh: bool = False) -> list[dict[str, Any]]:
    if _OVERRIDE[0] is not None:
        return [dict(r) for r in _OVERRIDE[0]]
    with _LOCK:
        rows = _pending_rows()
        key = _key(rows)
        if not refresh and _MEM.get("key") == key:
            return [dict(r) for r in _MEM["rows"]]
        f = _cache_file()
        if not refresh and f.exists():
            try:
                c = json.loads(f.read_text())
                if c.get("key") == key:
                    _MEM.update(c)
                    return [dict(r) for r in c["rows"]]
            except ValueError:
                pass
        out = [one(str(d["proposal_id"]), d) for d in rows]
        c = {"key": key, "rows": out, "as_of": AS_OF.isoformat()}
        f.write_text(json.dumps(c, default=str))
        _MEM.clear()
        _MEM.update(c)
        return [dict(r) for r in out]


def for_deal(pid: str) -> dict[str, Any]:
    for r in pending():
        if r["proposal_id"] == pid:
            return r
    return one(pid)
