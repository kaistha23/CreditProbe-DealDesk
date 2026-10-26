"""R14 E (K18, K19, K25 #4, D14): the ONE approval-authority engine (N2: one engine per fact).

Every tile, step, opinion and paper reads the level from here:

* the engine tiles, offers, counter-proposals, Stress Lab and the thread read `constraints.approval(p, a)`, which
  now delegates to `for_proposal(p, a)`;
* the Review (R11 workspace and review2) reads `review_rules.required_doa(f, checks)`, which delegates to
  `for_proposal(...)` for Deal Desk deals (and to `decide(...)` for prepared cases);
* everything else calls `approval_authority(pid, structure)` (backend.dealdesk.approval).

The rule (Delegation of Authority, dd_parameter `doa`, data/dealdesk/params/v1/doa.json): the level is the highest
that any one of these needs:
  1. exposure after the deal = the obligor's existing exposure + the new limit (SAR) against each row's max exposure;
  2. the obligor's internal rating against each row's minimum rating;
  3. the number of exceptions (soft-limit breaches + policy exceptions) against each row's max_soft;
  4. each policy exception's own minimum level (pricing below the hurdle -> rules.json CONS-07 doa_rank, CRO);
  5. a hard-limit breach -> Board Credit Committee (only the Board can approve an exception to a hard limit);
  6. SIMAH adverse -> at least the `simah_adverse_min_rank` level.
"""
from __future__ import annotations

import contextvars
import functools
import json
import threading
import time
from typing import Any, Iterable

from backend.dealdesk import params
from backend.dealdesk.seed import GRADES

SOURCE = "Delegation of Authority (dd_parameter doa, data/dealdesk/params/v1/doa.json) via backend.dealdesk.approval"
BASIS_LABEL = {"exposure": "Exposure after the deal", "rating": "Obligor rating", "exceptions": "Number of exceptions",
               "exception": "Policy exception", "hard_limit": "Hard limit breached", "simah": "SIMAH adverse", "rule": "Review rule"}
PRICING_CODE = "CONS-07"
# structure-dependent review rules: re-evaluated on the structure itself, never taken from the ask's checks
STRUCTURAL_RULES = {"CONS-05", "CONS-06", "CONS-07"}

_GUARD: contextvars.ContextVar[bool] = contextvars.ContextVar("approval_guard", default=False)
_CHECKS: dict[tuple[str, str], tuple[float, list[dict[str, Any]]]] = {}
_LOCK = threading.Lock()
TTL = 900.0


def _doa() -> dict[str, Any]:
    return params.table("doa")


def _rows() -> list[dict[str, Any]]:
    return sorted(_doa()["rows"], key=lambda r: int(r["rank"]))


def level_of(rank: int) -> str:
    rows = _rows()
    return next((r["level"] for r in rows if int(r["rank"]) == int(rank)), rows[-1]["level"])


def top_rank() -> int:
    return int(_rows()[-1]["rank"])


@functools.lru_cache(maxsize=1)
def _rule_ranks() -> dict[str, int]:
    from backend.dealdesk.review_ledger import REVIEW_DIR
    try:
        rs = json.loads((REVIEW_DIR / "rules.json").read_text())["rules"]
    except Exception:  # noqa: BLE001 - the rule book is optional for the engine
        return {}
    return {r["id"]: int(r["doa_rank"]) for r in rs if r.get("doa_rank")}


def pricing_rank() -> int:
    return _rule_ranks().get(PRICING_CODE, 3)


def _mn(x: float) -> str:
    return f"SAR {x:,.1f}m"


def decide(exposure_after_sar_mn: float, rating: str, *, exceptions: Iterable[dict[str, Any]] = (),
           soft_breaches: Iterable[dict[str, Any]] = (), hard_breaches: Iterable[dict[str, Any]] = (),
           simah: str | None = None, exposure_detail: str | None = None) -> dict[str, Any]:
    """The DoA core. exceptions: [{code, label, rank?}]; soft/hard breaches: [{name, label}]. Returns level, rank, the
    binding reason, every reason with the level it needs, and the rule sentence."""
    rows = _rows()
    exceptions, soft, hard = list(exceptions), list(soft_breaches), list(hard_breaches)
    reasons: list[dict[str, Any]] = []
    exp = float(exposure_after_sar_mn or 0.0)
    r_exp = next((r for r in rows if exp <= float(r["max_exposure"])), rows[-1])
    prev = next((r for r in reversed(rows) if int(r["rank"]) < int(r_exp["rank"])), None)
    band = (f"above {_mn(float(prev['max_exposure']))}" if prev else f"up to {_mn(float(r_exp['max_exposure']))}")
    reasons.append({"basis": "exposure", "rank": int(r_exp["rank"]),
                    "detail": (exposure_detail or f"Exposure after the deal {_mn(exp)}") + f" ({band})"})
    try:
        gi = GRADES.index(rating)
        r_rt = next(r for r in rows if gi <= GRADES.index(r["min_rating"]))
        reasons.append({"basis": "rating", "rank": int(r_rt["rank"]), "detail": f"Rating {rating} (row minimum {r_rt['min_rating']})"})
    except (ValueError, StopIteration):
        pass
    n_exc = len(soft) + len(exceptions)
    if n_exc > 1 or soft:  # one exception with its own level says it once (below)
        r_soft = next((r for r in rows if n_exc <= int(r["max_soft"])), rows[-1])
        names = [s.get("label") or s.get("name") for s in soft] + [e.get("label") or e.get("code") for e in exceptions]
        reasons.append({"basis": "exceptions", "rank": int(r_soft["rank"]),
                        "detail": f"{n_exc} exception{'s' if n_exc != 1 else ''}: " + "; ".join(str(n) for n in names)})
    for e in exceptions:
        if e.get("rank"):
            reasons.append({"basis": "exception", "rank": int(e["rank"]), "code": e.get("code"),
                            "detail": str(e.get("label") or e.get("code"))})
    for h in hard:
        reasons.append({"basis": "hard_limit", "rank": top_rank(), "code": h.get("name"),
                        "detail": f"Hard limit breached: {h.get('label') or h.get('name')} (only the {level_of(top_rank())} can approve the exception)"})
    adv_rank = int(_doa().get("simah_adverse_min_rank", 4))
    if simah == "adverse":
        reasons.append({"basis": "simah", "rank": adv_rank, "detail": "SIMAH adverse"})
    for r in reasons:
        r["level"] = level_of(r["rank"])
        r["label"] = BASIS_LABEL.get(r["basis"], r["basis"])
    # the binding reason: the highest rank; among equals the first listed (exposure, rating, exceptions, ...)
    top = max(reasons, key=lambda r: r["rank"])
    rank = int(top["rank"])
    level = level_of(rank)
    rule = f"{top['detail']} → {level}"
    return {"level": level, "rank": rank, "rule": rule, "binding": top, "reasons": reasons,
            "exposure_after_sar_mn": exp, "approvable": not hard,
            "hard_breaches": [h.get("name") for h in hard], "soft_breaches": [s.get("name") for s in soft],
            "exceptions": [{"code": e.get("code"), "label": e.get("label"), "rank": e.get("rank"),
                            "level": level_of(int(e["rank"])) if e.get("rank") else None} for e in exceptions],
            "source": SOURCE}


# ------------------------------------------------------------------ deal-level review exceptions (cached)

def _version() -> str:
    try:
        return params.version_tag()
    except Exception:  # noqa: BLE001
        return "?"


def deal_checks(pid: str) -> list[dict[str, Any]]:
    """Every review rule check (review_rules.run on review_facts.facts) for the deal, cached per deal and parameter
    version; [] while the review facts are being built (recursion guard) or for an unknown deal."""
    if _GUARD.get() or not pid:
        return []
    key = (pid, _version())
    with _LOCK:
        hit = _CHECKS.get(key)
    if hit and time.time() - hit[0] < TTL:
        return hit[1]
    tok = _GUARD.set(True)
    try:
        from backend.dealdesk import review_facts as RF
        from backend.dealdesk import review_rules as RR
        checks = RR.run(RF.facts(pid)) if RF.known(pid) else []
    except Exception:  # noqa: BLE001 - no memo or rule book: the structural reasons alone
        checks = []
    finally:
        _GUARD.reset(tok)
    with _LOCK:
        _CHECKS[key] = (time.time(), checks)
    return checks


def deal_rule_exceptions(pid: str, checks: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """The deal-level policy exceptions from the review rule book (failed rules with a DoA rank, and rules whose verdict
    is 'exception'), excluding the structure-dependent rules (pricing, DSCR, leverage), which are re-evaluated on the
    structure."""
    if checks is None:
        checks = deal_checks(pid)
    out = []
    for c in checks:
        if c.get("rule_id") in STRUCTURAL_RULES:
            continue
        failed = c.get("verdict") in ("contradicted", "exception")
        if not failed:
            continue
        rk = (c.get("doa") or {}).get("rank")
        if c.get("verdict") == "exception" or rk:
            out.append({"code": c.get("rule_id"), "label": f"{c.get('rule_id')} {c.get('title')}", "rank": rk})
    return out


def clear_cache() -> None:
    with _LOCK:
        _CHECKS.clear()
    _rule_ranks.cache_clear()


# ------------------------------------------------------------------ one proposal, one structure

def existing_exposure(p: dict[str, Any]) -> float:
    return float((p.get("obligor") or {}).get("existing_exposure_sar_mn") or 0.0)


def exposure_after(p: dict[str, Any], new_limit_sar_mn: float) -> tuple[float, str]:
    """Obligor exposure after the deal = existing exposure + the new limit (SAR). A prepared review case uses the group
    exposure after the deal when the case carries it (the case's own DoA basis)."""
    ex = existing_exposure(p)
    if p.get("case") == "proposal_review":
        try:
            from backend.dealdesk.proposal_cases import CASES
            from backend.dealdesk import desk_params
            c = CASES.get(p["proposal_id"]) or {}
            g = (c.get("group_cap") or {}).get("group_exposure_after")
            if g:
                v = max(float(new_limit_sar_mn), float(g) * float(desk_params.rows()["aed_sar"]))
                return v, f"Group exposure after the deal {_mn(v)}"
        except Exception:  # noqa: BLE001
            pass
    v = ex + float(new_limit_sar_mn)
    return v, f"Exposure after the deal {_mn(v)} (existing {_mn(ex)} + new limit {_mn(float(new_limit_sar_mn))})"


def pricing_exception(m: dict[str, Any]) -> dict[str, Any] | None:
    if m.get("clears_hurdle", True):
        return None
    r, h = m.get("lifetime_raroc"), m.get("hurdle")
    lab = f"Pricing below hurdle: RAROC {r:.1%} vs {h:.1%}" if isinstance(r, (int, float)) and isinstance(h, (int, float)) else "Pricing below hurdle"
    return {"code": PRICING_CODE, "label": lab, "rank": pricing_rank()}


def for_proposal(p: dict[str, Any], a: dict[str, Any], checks: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """The approval level of one analysed structure (`a` = engine.analyse(p, terms) with its constraints)."""
    m = a["metrics"]
    cs = a.get("constraints") or []
    soft = [c for c in cs if c["status"] == "breach" and c["kind"] == "soft"]
    hard = [c for c in cs if c["status"] == "breach" and c["kind"] == "hard"]
    exc = []
    pe = pricing_exception(m)
    if pe:
        exc.append(pe)
    pid = p.get("proposal_id") or ""
    exc += deal_rule_exceptions(pid, checks)
    new_limit = float(m.get("amount_sar_mn") or 0.0)
    exp, detail = exposure_after(p, new_limit)
    ob = p.get("obligor") or {}
    out = decide(exp, ob.get("internal_rating", ""), exceptions=exc, soft_breaches=soft, hard_breaches=hard,
                 simah=ob.get("simah_flag"), exposure_detail=detail)
    out["existing_exposure_sar_mn"] = existing_exposure(p)
    out["new_limit_sar_mn"] = new_limit
    return out
