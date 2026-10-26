"""Session D's one door to Data Domains (PLAN_R12 §0): every relation D reads or writes goes through here.

Session E's reader and publisher (`backend.dealdesk.data`: `dd_read(relation, **filters)`, `publish(relation, rows,
mode, actor)`; contract docs/v5/R12_DATA_CONTRACT.md) answer whenever the relation is in E's contract. D keeps its
own row shape internally; `MAP` converts to and from the contract's columns (extra fields D needs and the contract
has no column for travel in the relation's json column under `_meta`). A relation outside E's contract
(`dd_monitoring_alert`), or a checkout without E's branch, lands in a local staging store under
var/dealdesk/r12_stress/<relation>.jsonl with the same internal shape; `backend()` says which one answered.

Pending maker-checker items (a bank scenario awaiting its checker is a contract row with status draft; an expert
sensitivity override awaiting its checker) are operational state: the override queue stays in staging and only
the approved version is published to `dd_stress_sensitivity`.
"""
from __future__ import annotations

import json
import math
import threading
from datetime import datetime, timezone
from typing import Any, Callable, Iterable

from backend.dealdesk import paths

OWNED = ("dd_stress_scenario", "dd_stress_sensitivity", "dd_stress_result", "dd_monitoring_plan", "dd_monitoring_alert",
         "dd_stress_sensitivity_pending", "dd_condition", "dd_review_finding")
_LOCK = threading.Lock()


def _e():
    """Session E's data module, or None (not merged)."""
    try:
        from backend.dealdesk.data import store as d  # type: ignore[attr-defined]
        from backend.dealdesk.data import schema as s  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 - E not merged: local staging
        return None
    return d, s


def _registered(relation: str) -> bool:
    e = _e()
    if e is None:
        return False
    d, s = e
    if relation in s.RELATIONS:
        return True
    try:
        d.relation_path(relation)
        return True
    except Exception:  # noqa: BLE001
        return False


def backend(relation: str | None = None) -> str:
    if relation is None:
        return "data_domains" if _e() else "staging"
    return "data_domains" if _registered(relation) and relation != "dd_stress_sensitivity_pending" else "staging"


def _staging(relation: str):
    p = paths.VAR / "r12_stress"
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{relation}.jsonl"


def _clean(v: Any) -> Any:
    if isinstance(v, float) and not math.isfinite(v):
        return None
    return v


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _eq(a: Any, b: Any) -> bool:
    if a is None:
        return b is None
    if isinstance(b, bool):
        return bool(a) == b
    if isinstance(b, (int, float)):
        try:
            return float(a) == float(b)
        except (TypeError, ValueError):
            return False
    return str(a) == str(b)


def decode(v: Any) -> Any:
    """A JSON-encoded column back to its value."""
    if isinstance(v, str) and v[:1] in "[{":
        try:
            return json.loads(v)
        except ValueError:
            return v
    return v


# ------------------------------------------------------------------ internal <-> contract

def _j(v: Any) -> Any:
    return decode(v) if isinstance(v, str) else v


SOURCE_CODE = {"ICAAP": "icaap", "SAMA": "sama", "CBUAE": "cbuae", "CBO": "cbo"}
STATUS_TO = {"pending_approval": "draft"}
STATUS_FROM = {"draft": "pending_approval"}
VERDICT_CODE = {"Restructure": "restructure", "Approve with enhanced monitoring": "approve_enhanced",
                "Approve, standard monitoring": "approve_standard", "Approve": "approve"}
VERDICT_LABEL = {v: k for k, v in VERDICT_CODE.items()}
FREQ = {3: "quarterly", 6: "semi_annual", 12: "annual"}
FREQ_M = {v: k for k, v in FREQ.items()}
BREAK_CODE = {"dscr": "dscr", "covenants": "covenant", "stage": "stage2", "raroc": "hurdle", "limits": "limit",
              "debt_ebitda": "leverage", "ltv": "ltv", "rating": "rating"}
BREAK_CELL = {v: k for k, v in BREAK_CODE.items()}
#: D's sensitivity ids <-> the contract's drivers; scale: contract beta = D value x scale
SENS_DRIVER = {"oil_revenue_beta": ("oil", -100.0), "gdp_revenue_beta": ("non_oil_gdp", -100.0),
               "fixed_cost_share": ("fixed_cost_share", 1.0), "largest_customer_share": ("largest_customer_share", 1.0),
               "project_revenue_share": ("project_share", 1.0), "real_estate_revenue_beta": ("real_estate", -100.0),
               "sector_downturn_revenue": ("sector_downturn_revenue", 1.0),
               "sector_downturn_receivable_days": ("sector_downturn_receivable_days", 1.0),
               "sector_downturn_margin_bps": ("sector_downturn_margin_bps", 1.0),
               "short_term_funding_spread_bps": ("short_term_funding_spread_bps", 1.0), "rates": ("rates", 1.0)}
DRIVER_SENS = {v[0]: k for k, v in SENS_DRIVER.items()}
ALL_SECTORS = ("*", "default", "All", "all", "ALL", "")


def _source_code(src: str) -> str:
    s = str(src or "")
    for k, v in SOURCE_CODE.items():
        if s.startswith(f"import: {k}"):
            return v
    return "seed" if "seed" in s.lower() else "user"


def scn_to(r: dict[str, Any]) -> dict[str, Any]:
    meta = {k: r.get(k) for k in ("basis", "set_id", "reason", "made_at", "checked_at", "retire", "source") if r.get(k) is not None}
    meta["status"] = r.get("status")
    return {"scenario_id": r["scenario_id"], "version": int(r["version"]), "family": r["family"], "severity": r["severity"],
            "label": r["label"], "scope": r.get("scope") or "bank", "proposal_id": r.get("proposal_id"),
            "shocks_json": {**(r.get("shocks") or {}), "_meta": meta}, "source": _source_code(r.get("source", "")),
            "owner": "Risk Models" if (r.get("scope") or "bank") == "bank" else (r.get("maker") or "deal team"),
            "status": STATUS_TO.get(r.get("status"), r.get("status")), "maker": r.get("maker"), "checker": r.get("checker"),
            "effective_date": str(r.get("checked_at") or r.get("made_at") or "")[:10] or None}


def scn_from(c: dict[str, Any]) -> dict[str, Any]:
    sh = dict(_j(c.get("shocks_json")) or {})
    meta = sh.pop("_meta", {}) or {}
    st = meta.get("status") or STATUS_FROM.get(c.get("status"), c.get("status"))
    return {"scenario_id": c["scenario_id"], "version": int(c.get("version") or 1), "family": c.get("family"),
            "severity": c.get("severity"), "label": c.get("label"), "scope": c.get("scope") or "bank", "proposal_id": c.get("proposal_id"),
            "shocks": sh, "basis": meta.get("basis") or "", "set_id": meta.get("set_id") or c.get("source"),
            "reason": meta.get("reason") or "", "made_at": meta.get("made_at") or c.get("published_at"),
            "checked_at": meta.get("checked_at") or (c.get("published_at") if st == "approved" else None),
            "retire": meta.get("retire"), "source": meta.get("source") or c.get("source"), "status": st,
            "maker": c.get("maker"), "checker": c.get("checker"), "rel_version": c.get("rel_version")}


def sens_to(r: dict[str, Any]) -> dict[str, Any]:
    drv, scale = SENS_DRIVER.get(r["sensitivity_id"], (r["sensitivity_id"], 1.0))
    sector = "default" if r["sector"] in ALL_SECTORS else r["sector"]
    lo, hi = r.get("lower"), r.get("upper")
    b = lambda v: None if v is None else float(v) * scale  # noqa: E731
    lo2, hi2 = b(lo), b(hi)
    if lo2 is not None and hi2 is not None and lo2 > hi2:
        lo2, hi2 = hi2, lo2
    return {"sensitivity_id": f"{sector}:{drv}", "version": int(r["version"]), "sector": sector, "driver": drv,
            "beta": float(r["value"]) * scale, "band_low": lo2, "band_high": hi2, "method": r.get("method") or "expert",
            "n_obs": r.get("n_obs"), "r2": r.get("r2"), "source": r.get("source"), "owner": r.get("published_by") or r.get("owner"),
            "effective_date": str(r.get("published_at") or "")[:10] or None, "model_card_ref": r.get("model_card_ref")}


def sens_from(c: dict[str, Any]) -> dict[str, Any]:
    drv = c.get("driver") or str(c.get("sensitivity_id", ":")).split(":")[-1]
    sid = DRIVER_SENS.get(drv, drv)
    scale = SENS_DRIVER.get(sid, (drv, 1.0))[1]
    sector = c.get("sector")
    sector = "*" if sector in ALL_SECTORS or sector is None else sector
    u = lambda v: None if v is None else float(v) / scale  # noqa: E731
    lo, hi = u(c.get("band_low")), u(c.get("band_high"))
    if lo is not None and hi is not None and lo > hi:
        lo, hi = hi, lo
    return {"sensitivity_id": sid, "sector": sector, "value": float(c.get("beta") or 0.0) / scale, "lower": lo, "upper": hi,
            "method": c.get("method") or "expert", "source": c.get("source") or "", "version": int(c.get("version") or 1),
            "status": "approved", "published_by": c.get("owner"), "published_at": c.get("published_at") or c.get("effective_date"),
            "n_obs": c.get("n_obs"), "r2": c.get("r2"), "model_card_ref": c.get("model_card_ref"), "rel_version": c.get("rel_version")}


def res_to(r: dict[str, Any]) -> dict[str, Any]:
    br = r.get("breaks") or []
    return {"result_id": f"{r['run_id']}:{r.get('context', 'stress_run')}:{r['scenario_id']}", "proposal_id": r["proposal_id"],
            "run_id": r["run_id"], "scenario_id": r["scenario_id"], "scenario_version": r.get("scenario_version"),
            "family": r.get("family"), "severity": r.get("severity"), "applicable_flag": 1 if r.get("applicable", True) else 0,
            "revenue_change_pct": None if r.get("revenue_change") is None else float(r["revenue_change"]) * 100,
            "ebitda_mn": r.get("ebitda"), "dscr_x": r.get("dscr"), "leverage_x": r.get("debt_ebitda"),
            "ltv_pct": None if r.get("ltv_cover") is None else float(r["ltv_cover"]) * 100, "rating": r.get("rating"),
            "pd_12m": r.get("pd_12m"), "stage": r.get("stage"), "ecl_mn": r.get("ecl_sar_mn"),
            "raroc_pct": None if r.get("raroc") is None else float(r["raroc"]) * 100,
            "covenant_breach_flag": 1 if "covenants" in (r.get("fails_on") or []) else 0,
            "breaks": ";".join(BREAK_CODE.get(b, b) for b in br) or None, "run_at": r.get("run_at"),
            "param_version": r.get("sensitivity_version")}


def res_from(c: dict[str, Any]) -> dict[str, Any]:
    parts = str(c.get("result_id") or "").split(":")
    ctx = parts[1] if len(parts) >= 3 else "stress_run"
    return {"run_id": c.get("run_id"), "context": ctx, "proposal_id": c.get("proposal_id"), "scenario_id": c.get("scenario_id"),
            "scenario_version": c.get("scenario_version"), "family": c.get("family"), "severity": c.get("severity"),
            "applicable": bool(c.get("applicable_flag", 1)), "revenue_change": None if c.get("revenue_change_pct") is None else c["revenue_change_pct"] / 100,
            "ebitda": c.get("ebitda_mn"), "dscr": c.get("dscr_x"), "debt_ebitda": c.get("leverage_x"),
            "ltv_cover": None if c.get("ltv_pct") is None else c["ltv_pct"] / 100, "rating": c.get("rating"), "pd_12m": c.get("pd_12m"),
            "stage": c.get("stage"), "ecl_sar_mn": c.get("ecl_mn"), "raroc": None if c.get("raroc_pct") is None else c["raroc_pct"] / 100,
            "breaks": [BREAK_CELL.get(b, b) for b in str(c.get("breaks") or "").split(";") if b],
            "run_at": c.get("run_at"), "sensitivity_version": c.get("param_version"), "result_id": c.get("result_id"),
            "rel_version": c.get("rel_version")}


def plan_to(r: dict[str, Any]) -> dict[str, Any]:
    th = r.get("ews_thresholds") or {}
    trig = [{**t, "operator": t.get("op")} for t in (r.get("triggers") or [])]
    over = {**th, "_meta": {k: r.get(k) for k in ("obligor_name", "sector", "driver_labels", "verdict", "run_id", "sensitivity_version",
                                                   "source", "version", "condition", "set_on") if r.get(k) is not None}}
    return {"plan_id": r["plan_id"], "proposal_id": r["proposal_id"], "obligor_id": r.get("obligor_id"),
            "facility_ref": r.get("facility_id") or "ALL", "tier": r["tier"],
            "stress_verdict": VERDICT_CODE.get(r.get("verdict"), r.get("verdict")),
            "worst_breaking_severity": r.get("worst_breaking_severity"), "drivers": r.get("drivers") or [], "named_triggers": trig,
            "ews_threshold_overrides": over, "review_frequency": FREQ.get(int(r.get("review_frequency_months") or 12), "annual"),
            "next_review_date": r.get("next_review_date"), "set_by": r.get("set_by"), "set_at": r.get("set_at"),
            "reason": r.get("reason"), "status": r.get("status") or "active", "previous_tier": r.get("previous_tier")}


def plan_from(c: dict[str, Any]) -> dict[str, Any]:
    over = dict(_j(c.get("ews_threshold_overrides")) or {})
    meta = over.pop("_meta", {}) or {}
    trig = []
    for t in (_j(c.get("named_triggers")) or []):
        t = dict(t)
        t.setdefault("op", t.get("operator"))
        t.setdefault("trigger_id", "T-" + str(t.get("metric", "x")).upper())
        t.setdefault("action", "alert" if c.get("tier") == "High" else "watch")
        t.setdefault("unit", "")
        t.setdefault("source", "")
        trig.append(t)
    pid = str(c.get("plan_id") or "")
    try:
        own = pid.startswith(f"MP-{c.get('proposal_id')}-")
        ver = int(meta.get("version") or (pid.rsplit("-", 1)[-1] if own else 1))
    except ValueError:
        ver = 1
    from backend.dealdesk.stress2.verdict import DRIVER_LABEL
    drivers = _j(c.get("drivers")) or []
    return {"plan_id": pid, "proposal_id": c.get("proposal_id"), "facility_id": c.get("facility_ref"), "obligor_id": c.get("obligor_id"),
            "obligor_name": meta.get("obligor_name"), "sector": meta.get("sector"), "tier": c.get("tier"),
            "verdict": meta.get("verdict") or VERDICT_LABEL.get(c.get("stress_verdict"), c.get("stress_verdict")),
            "worst_breaking_severity": c.get("worst_breaking_severity"), "drivers": drivers,
            "driver_labels": meta.get("driver_labels") or [DRIVER_LABEL.get(d, str(d).replace("_", " ").capitalize()) for d in drivers],
            "triggers": trig, "ews_thresholds": over or None, "review_frequency_months": FREQ_M.get(c.get("review_frequency"), 12),
            "next_review_date": c.get("next_review_date"), "set_by": c.get("set_by"), "set_at": c.get("set_at"),
            "set_on": meta.get("set_on") or str(c.get("set_at") or "")[:10], "reason": c.get("reason"),
            "source": meta.get("source") or "Deal Desk", "run_id": meta.get("run_id"), "sensitivity_version": meta.get("sensitivity_version"),
            "status": c.get("status") or "active", "version": ver, "previous_tier": c.get("previous_tier"),
            "condition": meta.get("condition"), "rel_version": c.get("rel_version")}


MAP: dict[str, tuple[Callable, Callable]] = {"dd_stress_scenario": (scn_to, scn_from), "dd_stress_sensitivity": (sens_to, sens_from),
                                             "dd_stress_result": (res_to, res_from), "dd_monitoring_plan": (plan_to, plan_from)}
#: internal filter -> contract column (pushed down to E's reader; the rest is filtered after mapping)
PUSH = {"dd_stress_scenario": {"scenario_id", "scope", "proposal_id"}, "dd_stress_result": {"run_id", "proposal_id", "scenario_id"},
        "dd_monitoring_plan": {"proposal_id", "obligor_id", "plan_id"}, "dd_stress_sensitivity": {"sector"}}


def read(relation: str, **filters: Any) -> list[dict[str, Any]]:
    """Rows of a relation in D's internal shape, filtered by equality (None filters are ignored)."""
    flt = {k: v for k, v in filters.items() if v is not None}
    if backend(relation) == "data_domains":
        d, s = _e()
        push = {k: v for k, v in flt.items() if k in PUSH.get(relation, set()) or (relation not in MAP and relation in s.RELATIONS
                                                                                   and k in s.column_names(relation))}
        try:
            rows = d.dd_read(relation, **push)
        except KeyError:
            rows = []
        if relation not in MAP and relation not in s.RELATIONS:
            # a registered relation outside E's contract (e.g. an R11 relation): filter in Python
            pass
        conv = MAP.get(relation, (None, lambda r: r))[1]
        out = [conv(dict(r)) for r in rows]
        return [r for r in out if all(_eq(r.get(k), v) for k, v in flt.items())]
    f = _staging(relation)
    if not f.exists():
        return []
    with _LOCK:
        lines = f.read_text().splitlines()
    out = [json.loads(x) for x in lines if x.strip()]
    return [r for r in out if all(_eq(r.get(k), v) for k, v in flt.items())]


def publish(relation: str, rows: Iterable[dict[str, Any]], actor: str = "D") -> dict[str, Any]:
    """Publish rows (internal shape) to a relation D writes; upsert on the contract's keys."""
    if relation not in OWNED:
        raise PermissionError(f"Session D does not publish {relation}")
    rows = [{k: _clean(v) for k, v in r.items()} for r in rows]
    if not rows:
        return {"relation": relation, "rows": 0, "backend": backend(relation)}
    if backend(relation) == "data_domains":
        d, _s = _e()
        conv = MAP.get(relation, (lambda r: r, None))[0]
        crow = [conv(r) for r in rows]
        res = d.publish(relation, crow, mode="upsert", actor=f"D:{actor}")
        return {"relation": relation, "rows": len(rows), "backend": "data_domains", "version": res.get("version")}
    f = _staging(relation)
    key = KEYS.get(relation)
    with _LOCK:
        old = [json.loads(x) for x in f.read_text().splitlines() if x.strip()] if f.exists() else []
        if key:
            new_k = {tuple(str(r.get(k)) for k in key) for r in rows}
            old = [r for r in old if tuple(str(r.get(k)) for k in key) not in new_k]
        with open(f, "w") as fh:
            for r in old + rows:
                fh.write(json.dumps(r, default=str) + "\n")
    return {"relation": relation, "rows": len(rows), "backend": "staging"}


#: upsert keys of the internal rows (the contract's keys, in D's names) for the staging store
KEYS = {"dd_stress_scenario": ("scenario_id", "version"), "dd_stress_sensitivity": ("sensitivity_id", "sector", "version"),
        "dd_stress_result": ("run_id", "context", "scenario_id"), "dd_monitoring_plan": ("plan_id",),
        "dd_monitoring_alert": ("alert_id",), "dd_stress_sensitivity_pending": ("version", "sensitivity_id", "sector"),
        "dd_condition": ("condition_id",), "dd_review_finding": ("finding_id",)}


def trace(relation: str, row: dict[str, Any]) -> dict[str, Any] | None:
    """Lineage of a contract row (E's trace), or None in staging."""
    e = _e()
    if e is None or backend(relation) != "data_domains":
        return None
    try:
        return e[0].trace(relation, MAP[relation][0](row) if relation in MAP else row)
    except Exception:  # noqa: BLE001
        return None


def reset_staging() -> None:
    """Tests: empty the local staging store."""
    p = paths.VAR / "r12_stress"
    if p.exists():
        for f in p.glob("*.jsonl"):
            f.unlink()


def deal(pid: str) -> dict[str, Any]:
    """Any deal (DD proposal, PL pipeline application, R12 demo) through Session E's one deal registry; the R11
    proposals module when E is not merged. KeyError when unknown."""
    try:
        from backend.dealdesk.data import deals  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        deals = None
    if deals is not None:
        try:
            return deals.get(pid)
        except KeyError:
            raise
        except Exception:  # noqa: BLE001 - E's registry unavailable: the R11 proposals
            pass
    from backend.dealdesk import proposals
    return proposals.get(pid)


def lineage(relation: str) -> dict[str, Any]:
    """{domain, relation, period} of a relation for the (i) / Trace / Open in Data Domains link."""
    e = _e()
    dom = None
    if e is not None and relation:
        try:
            dom = e[0].domain_of(relation)
        except Exception:  # noqa: BLE001
            dom = None
    return {"domain": dom, "relation": relation, "period": paths.AS_OF}


def source(relation: str, key: dict[str, Any], column: str | None = None) -> dict[str, Any] | None:
    """A Data Domains source for one figure (E's lineage shape), or None in staging."""
    if backend(relation) != "data_domains":
        return None
    li = lineage(relation)
    return {"domain": li["domain"], "relation": relation, "key": {k: v for k, v in key.items() if v is not None},
            "period": li["period"], **({"column": column} if column else {})}


def sens_source(r: dict[str, Any]) -> dict[str, Any] | None:
    """The source of one sensitivity row (D's shape) in dd_stress_sensitivity."""
    if r.get("version") is None or not r.get("sensitivity_id"):
        return None
    drv = SENS_DRIVER.get(r["sensitivity_id"], (r["sensitivity_id"], 1.0))[0]
    sector = r.get("matched_sector") or r.get("sector")
    sector = "default" if sector in ALL_SECTORS or sector is None else sector
    return source("dd_stress_sensitivity", {"sensitivity_id": f"{sector}:{drv}", "version": int(r["version"])}, "beta")
