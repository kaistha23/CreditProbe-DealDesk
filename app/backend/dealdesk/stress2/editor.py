"""The scenario editor (I22-3, I19-3, I19-4): build a scenario for one deal or for the bank, versioned, with
maker-checker for bank scope; load the bank's ICAAP or regulator (SAMA, CBUAE, CBO) sets from a CSV or JSON template;
expert sensitivity overrides with maker-checker. Every change is a new row in `dd_stress_scenario` /
`dd_stress_sensitivity` (append-only: a version is never edited, a new one supersedes it).

    deal scope   in force at once for that deal (the maker owns the deal's file); shown under "Your scenarios"
    bank scope   pending until a checker other than the maker approves it; then in force for every deal
"""
from __future__ import annotations

import csv
import io
import json
import re
from typing import Any

from backend.dealdesk.stress2 import catalogue as cat
from backend.dealdesk.stress2 import store


class EditorError(ValueError):
    def __init__(self, errors: list[dict[str, str]]):
        super().__init__("; ".join(e["message"] for e in errors))
        self.errors = errors


NUMERIC = {"oil_pct": (-90, 90), "gdp_pct": (-20, 20), "sector_downturn": (0, 3), "revenue_pct": (-0.95, 0.5),
           "ebitda_margin_bps": (-3000, 1000), "customer_loss_share": (0, 1), "receivable_days": (0, 365), "delay_months": (0, 36),
           "rate_bps": (-500, 1000), "collateral_pct": (-0.9, 0.5), "real_estate_pct": (-90, 50), "notches": (0, 8)}
AUTHORITIES = ("ICAAP", "SAMA", "CBUAE", "CBO", "Internal")


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")[:40] or "scenario"


def validate(sc: dict[str, Any]) -> dict[str, Any]:
    err: list[dict[str, str]] = []
    fam = sc.get("family") or "custom"
    if fam not in dict(cat.FAMILIES):
        err.append({"field": "family", "message": f"family must be one of {', '.join(f for f, _ in cat.FAMILIES)}"})
    sev = sc.get("severity")
    if sev not in cat.SEVERITIES:
        err.append({"field": "severity", "message": "severity must be mild, moderate or severe"})
    label = str(sc.get("label") or "").strip()
    if not label:
        err.append({"field": "label", "message": "a label is required"})
    shocks = sc.get("shocks") or {}
    if isinstance(shocks, str):
        try:
            shocks = json.loads(shocks)
        except ValueError:
            err.append({"field": "shocks", "message": "shocks must be JSON"})
            shocks = {}
    clean: dict[str, Any] = {}
    for k, v in shocks.items():
        if k not in cat.SHOCK_KEYS:
            err.append({"field": f"shocks.{k}", "message": f"unknown shock {k}; one of {', '.join(cat.SHOCK_KEYS)}"})
            continue
        if v in (None, "", 0, 0.0, False):
            continue
        if k == "compose":
            if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
                err.append({"field": "shocks.compose", "message": "compose is a list of scenario ids"})
            else:
                clean[k] = v
        elif k == "guarantee_unenforceable":
            clean[k] = bool(v) if not isinstance(v, str) else v.strip().lower() in ("1", "true", "yes", "y")
        else:
            try:
                f = float(v)
            except (TypeError, ValueError):
                err.append({"field": f"shocks.{k}", "message": f"{k} must be a number"})
                continue
            lo, hi = NUMERIC[k]
            if not lo <= f <= hi:
                err.append({"field": f"shocks.{k}", "message": f"{k} must be between {lo} and {hi}"})
                continue
            clean[k] = int(f) if k == "notches" else f
    if not clean and not err:
        err.append({"field": "shocks", "message": "the scenario has no shock"})
    if err:
        raise EditorError(err)
    return {"family": fam, "severity": sev, "label": label, "shocks": clean, "basis": str(sc.get("basis") or "").strip() or
            "Built in the scenario editor."}


def _versions(sid: str) -> list[dict[str, Any]]:
    return [r for r in cat.all_scenario_rows() if r["scenario_id"] == sid]


def save(sc: dict[str, Any], *, scope: str, maker: str, proposal_id: str | None = None, reason: str = "",
         scenario_id: str | None = None, set_id: str | None = None, source: str = "scenario editor") -> dict[str, Any]:
    if scope not in ("deal", "bank"):
        raise EditorError([{"field": "scope", "message": "scope is deal or bank"}])
    if scope == "deal" and not proposal_id:
        raise EditorError([{"field": "proposal_id", "message": "a deal scenario needs the deal"}])
    if not maker:
        raise EditorError([{"field": "maker", "message": "the maker is required"}])
    v = validate(sc)
    sid = scenario_id or sc.get("scenario_id") or ("deal_" if scope == "deal" else "bank_") + _slug(v["label"])
    prior = _versions(sid)
    if prior:
        other = {r.get("scope") for r in prior}
        if scope not in other:
            raise EditorError([{"field": "scenario_id", "message": f"{sid} exists in {', '.join(sorted(map(str, other)))} scope"}])
        if scope == "deal" and any(r.get("proposal_id") not in (None, proposal_id) for r in prior):
            raise EditorError([{"field": "scenario_id", "message": f"{sid} belongs to another deal"}])
    ver = max((r["version"] for r in prior), default=0) + 1
    now = store.now()
    row = {"scenario_id": sid, "version": ver, "set_id": set_id or ("deal:" + proposal_id if scope == "deal" else "bank-editor"),
           "scope": scope, "proposal_id": proposal_id if scope == "deal" else None, **v, "source": source,
           "status": "approved" if scope == "deal" else "pending_approval", "maker": maker, "made_at": now,
           "checker": maker if scope == "deal" else None, "checked_at": now if scope == "deal" else None,
           "reason": reason or ("New scenario" if ver == 1 else "Revised")}
    store.publish("dd_stress_scenario", [row])
    return row


def pending() -> list[dict[str, Any]]:
    rows = cat.all_scenario_rows()
    decided = {(r["scenario_id"], r["version"]) for r in rows if r.get("status") in ("approved", "rejected", "retired")}
    return [r for r in rows if r.get("status") == "pending_approval" and (r["scenario_id"], r["version"]) not in decided]


def decide(scenario_id: str, version: int, *, checker: str, approve: bool, reason: str = "") -> dict[str, Any]:
    p = next((r for r in pending() if r["scenario_id"] == scenario_id and r["version"] == int(version)), None)
    if p is None:
        raise EditorError([{"field": "scenario_id", "message": f"no pending version {version} of {scenario_id}"}])
    if not checker:
        raise EditorError([{"field": "checker", "message": "the checker is required"}])
    if checker == p.get("maker"):
        raise EditorError([{"field": "checker", "message": "maker-checker: the checker must not be the maker"}])
    row = {**p, "status": ("retired" if p.get("retire") else "approved") if approve else "rejected", "checker": checker,
           "checked_at": store.now(), "reason": reason or p.get("reason", "")}
    store.publish("dd_stress_scenario", [row])
    return row


def retire(scenario_id: str, *, maker: str, reason: str, proposal_id: str | None = None) -> dict[str, Any]:
    prior = _versions(scenario_id)
    if not prior:
        raise EditorError([{"field": "scenario_id", "message": f"no scenario {scenario_id}"}])
    last = max(prior, key=lambda r: r["version"])
    scope = last.get("scope")
    now = store.now()
    row = {**last, "version": last["version"] + 1, "status": "retired" if scope == "deal" else "pending_approval", "retire": True,
           "maker": maker, "made_at": now, "checker": maker if scope == "deal" else None, "checked_at": now if scope == "deal" else None,
           "reason": reason or "Retired"}
    store.publish("dd_stress_scenario", [row])
    return row


def history(scenario_id: str) -> list[dict[str, Any]]:
    return sorted(_versions(scenario_id), key=lambda r: (r["version"], str(r.get("checked_at") or r.get("made_at") or "")))


# ------------------------------------------------------------------ ICAAP / regulator sets

TEMPLATE_COLUMNS = ["scenario_id", "family", "severity", "label", "basis"] + [k for k in cat.SHOCK_KEYS if k != "compose"]


def template(fmt: str = "csv") -> dict[str, Any]:
    """An empty set to fill: the columns, two example rows marked as examples, and the rules."""
    ex = [{"scenario_id": "example_baseline_adverse", "family": "macro", "severity": "moderate",
           "label": "Example: adverse (replace with the published figures)", "basis": "Example row: replace with the authority's scenario text",
           "oil_pct": -25, "gdp_pct": -2, "rate_bps": 150},
          {"scenario_id": "example_severely_adverse", "family": "combined", "severity": "severe",
           "label": "Example: severely adverse (replace with the published figures)", "basis": "Example row",
           "oil_pct": -40, "gdp_pct": -4, "rate_bps": 250, "real_estate_pct": -25, "collateral_pct": -0.2}]
    rules = {"set": "name of the set, e.g. 'ICAAP 2026' or 'SAMA 2026 stress test'", "authority": list(AUTHORITIES),
             "columns": {k: cat.SHOCK_KEYS.get(k, "") for k in TEMPLATE_COLUMNS},
             "severity": list(cat.SEVERITIES), "families": [f for f, _ in cat.FAMILIES]}
    if fmt == "json":
        return {"format": "json", "content": json.dumps({"set": "ICAAP 2026", "authority": "ICAAP", "scenarios": ex}, indent=1), "rules": rules}
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=TEMPLATE_COLUMNS)
    w.writeheader()
    for r in ex:
        w.writerow({k: r.get(k, "") for k in TEMPLATE_COLUMNS})
    return {"format": "csv", "content": buf.getvalue(), "rules": rules}


def parse_set(content: str, fmt: str | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    content = content.strip()
    fmt = fmt or ("json" if content[:1] in "{[" else "csv")
    meta: dict[str, Any] = {}
    if fmt == "json":
        d = json.loads(content)
        if isinstance(d, list):
            items = d
        else:
            items = d.get("scenarios") or []
            meta = {k: d.get(k) for k in ("set", "authority") if d.get(k)}
    else:
        items = list(csv.DictReader(io.StringIO(content)))
    out = []
    for it in items:
        shocks = dict(it.get("shocks") or {})
        for k in cat.SHOCK_KEYS:
            if k in it and it[k] not in (None, ""):
                shocks[k] = it[k]
        out.append({"scenario_id": (it.get("scenario_id") or "").strip() or None, "family": (it.get("family") or "macro").strip(),
                    "severity": (it.get("severity") or "").strip(), "label": (it.get("label") or "").strip(),
                    "basis": (it.get("basis") or "").strip(), "shocks": shocks})
    return meta, out


def import_set(content: str, *, set_name: str, authority: str, maker: str, fmt: str | None = None,
               scope: str = "bank", proposal_id: str | None = None) -> dict[str, Any]:
    """Load a set: every row validated first (all or nothing), then saved as pending (bank) versions in one set."""
    if authority not in AUTHORITIES:
        raise EditorError([{"field": "authority", "message": f"authority is one of {', '.join(AUTHORITIES)}"}])
    if not set_name:
        raise EditorError([{"field": "set", "message": "the set needs a name"}])
    try:
        meta, items = parse_set(content, fmt)
    except (ValueError, csv.Error) as e:
        raise EditorError([{"field": "content", "message": f"cannot read the file: {e}"}]) from None
    if not items:
        raise EditorError([{"field": "content", "message": "the file has no scenario rows"}])
    errs = []
    for i, it in enumerate(items, start=1):
        try:
            validate(it)
        except EditorError as e:
            errs += [{"field": f"row {i}: {x['field']}", "message": x["message"]} for x in e.errors]
    if errs:
        raise EditorError(errs)
    sid_prefix = _slug(authority + "_" + set_name)
    set_id = f"{authority}:{set_name}"
    saved = []
    for it in items:
        sid = f"{sid_prefix}__{_slug(it['scenario_id'] or it['label'])}"
        it = {**it, "label": f"{it['label']} ({authority})" if authority not in it["label"] else it["label"],
              "basis": (it["basis"] + " " if it["basis"] else "") + f"[{set_id}]"}
        saved.append(save(it, scope=scope, maker=maker, proposal_id=proposal_id, scenario_id=sid, set_id=set_id,
                          reason=f"Imported {set_id}", source=f"import: {set_id}"))
    return {"set_id": set_id, "rows": len(saved), "status": saved[0]["status"], "scenarios": saved}


# ------------------------------------------------------------------ expert sensitivity overrides

def propose_sensitivity(sensitivity_id: str, sector: str, value: float, *, maker: str, reason: str) -> dict[str, Any]:
    """An expert override waits in the app's store until a checker approves it; then it is published to
    `dd_stress_sensitivity` as the pair's next version (the values in force never include an unchecked number)."""
    if sensitivity_id not in cat.SENS_META:
        raise EditorError([{"field": "sensitivity_id", "message": f"one of {', '.join(cat.SENS_META)}"}])
    if not maker or not reason:
        raise EditorError([{"field": "reason", "message": "an expert override needs the maker and a reason"}])
    cur = cat.Sensitivities().get(sensitivity_id, sector)
    n = len({r["version"] for r in store.read("dd_stress_sensitivity_pending")}) + 1
    ver = f"override-{n}"
    lab, unit, basis = cat.SENS_META[sensitivity_id]
    row = {"version": ver, "sensitivity_id": sensitivity_id, "sector": sector, "value": float(value), "previous_value": cur["value"],
           "previous_version": cur.get("version"), "lower": None, "upper": None, "unit": unit, "label": lab, "basis": basis,
           "method": "expert", "source": f"expert override by {maker}: {reason}", "status": "pending_approval", "maker": maker,
           "made_at": store.now(), "reason": reason}
    store.publish("dd_stress_sensitivity_pending", [row])
    return {"version": ver, "status": "pending_approval", "rows": 1, "based_on": cur.get("version"), "previous_value": cur["value"]}


def decide_sensitivity(version: str, *, checker: str, approve: bool, reason: str = "") -> dict[str, Any]:
    pend = [r for r in store.read("dd_stress_sensitivity_pending", version=version) if r.get("status") == "pending_approval"]
    if not pend:
        raise EditorError([{"field": "version", "message": f"no pending sensitivity override {version}"}])
    if not checker or checker == pend[0].get("maker"):
        raise EditorError([{"field": "checker", "message": "maker-checker: the checker must not be the maker"}])
    now = store.now()
    done = [{**r, "status": "approved" if approve else "rejected", "checker": checker, "checked_at": now,
             "reason": reason or r.get("reason")} for r in pend]
    store.publish("dd_stress_sensitivity_pending", done)
    out = {"version": version, "status": "approved" if approve else "rejected", "rows": len(done)}
    if approve:
        have = store.read("dd_stress_sensitivity")
        pub = []
        for r in pend:
            v = max((int(h["version"]) for h in have if h["sensitivity_id"] == r["sensitivity_id"] and h["sector"] == r["sector"]), default=0) + 1
            pub.append({"sensitivity_id": r["sensitivity_id"], "sector": r["sector"], "value": r["value"], "lower": None, "upper": None,
                        "method": "expert", "source": f"{r['source']} (checked by {checker})", "version": v, "status": "approved",
                        "published_by": checker, "published_at": now, "n_obs": None, "label": r.get("label"), "unit": r.get("unit"),
                        "basis": r.get("basis")})
        store.publish("dd_stress_sensitivity", pub, actor="editor")
        out["published_versions"] = [p["version"] for p in pub]
    return out
