"""Admin console logic: View-as preview (A1), workflow simulation (A1), Agent Operations (A3), the AI Studio test
bench (A4), the parameter register and data feeds (A5), and the merged audit log (A6)."""
from __future__ import annotations

import json
import re
import sqlite3
import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from backend.access import dims, enforce, policy as pol
from backend.admin import seed, store
from backend.v5common.edition import is_dealdesk

V5 = Path(__file__).resolve().parents[2]


# ------------------------------------------------------------------ View as user (A1)
@lru_cache(maxsize=1)
def _exposure() -> dict[str, pd.DataFrame]:
    c = pd.read_parquet(dims.LAKE / dims.CORP / "corp_facility_quarter.parquet",
                        columns=["borrower_id", "reporting_quarter", "ead_sar_mn", "ecl_sar_mn", "stage"])
    c = c[c["reporting_quarter"] == "2026Q2"].groupby("borrower_id", as_index=False).agg(
        ead_sar_mn=("ead_sar_mn", "sum"), ecl_sar_mn=("ecl_sar_mn", "sum"), stage=("stage", "max"))
    r = pd.read_parquet(dims.LAKE / dims.RET / "retail_account_month.parquet",
                        columns=["customer_id", "reporting_month", "ead_sar_mn", "ecl_sar_mn", "stage"])
    r = r[r["reporting_month"] == "2026-08"].groupby("customer_id", as_index=False).agg(
        ead_sar_mn=("ead_sar_mn", "sum"), ecl_sar_mn=("ecl_sar_mn", "sum"), stage=("stage", "max"))
    return {"corporate": c, "retail": r}


def preview(username: str, with_core: dict[str, Any] | None = None) -> dict[str, Any]:
    """Exactly what a user would see: modules, actions, and per book the customers, EAD and ECL inside their policy,
    with a sample of the rows as they would be shown (masked where the policy masks)."""
    core = with_core or pol.core_user(username) or {}
    with store.db() as con:
        prof = store.find_live(con, "user", username)
    prof_body = (prof or {}).get("body", {})
    p = pol.build(username, core, prof_body)
    books = []
    for book in ("corporate", "retail"):
        key = dims.KEY[book]
        exp = _exposure()[book]
        total = {"customers": int(len(exp)), "ead_sar_mn": float(exp["ead_sar_mn"].sum()),
                 "ecl_sar_mn": float(exp["ecl_sar_mn"].sum())}
        if not p.allows_book(book):
            books.append({"book": book, "visible": False, "total": total, "seen": {"customers": 0, "ead_sar_mn": 0.0,
                                                                                    "ecl_sar_mn": 0.0}, "sample": []})
            continue
        ids = p.allowed_ids(book)
        seen = exp if ids is None else exp[exp[key].astype(str).isin(ids)]
        d = dims.frame(book)
        top = seen.sort_values("ead_sar_mn", ascending=False).head(8)
        sample = []
        for _, r in top.iterrows():
            rid = str(r[key])
            dim = d.loc[rid] if rid in d.index else None
            row = {"id": enforce.mask_id(rid) if p.mask_ids else rid, "ead_sar_mn": round(float(r["ead_sar_mn"]), 2),
                   "stage": int(r["stage"])}
            if dim is not None:
                if book == "corporate":
                    row.update({"name": enforce.MASKED_NAME if p.mask_names else str(dim["borrower_name"]),
                                "sector": dim["sector"], "region": dim["region"], "branch": dim.get("branch_name"),
                                "rm": dim.get("rm_name")})
                else:
                    row.update({"name": enforce.MASKED_NAME if p.mask_names else f"Customer {rid}",
                                "segment": dim["segment"], "region": dim["region"], "branch": dim.get("branch_name")})
            sample.append(row)
        books.append({"book": book, "visible": True, "total": total,
                      "seen": {"customers": int(len(seen)), "ead_sar_mn": float(seen["ead_sar_mn"].sum()),
                               "ecl_sar_mn": float(seen["ecl_sar_mn"].sum())}, "sample": sample})
    return {"user": {"username": username, "name": core.get("name") or prof_body.get("name") or username,
                     "role": prof_body.get("role", ""), "team": prof_body.get("team", ""), "rm_id": prof_body.get("rm_id", ""),
                     "is_admin": bool(core.get("is_admin"))},
            "policy": p.describe(),
            "modules": [{"key": k, "label": v, "allowed": p.allows_module(k)} for k, v in pol.modules().items()],
            "actions": [{"key": k, "label": v, "allowed": p.allows_action(k)} for k, v in pol.ACTIONS.items()],
            "cockpit": {"books": [b for b in ("corporate", "retail") if p.allows_book(b)],
                        "row_level": "book only (frozen Cockpit; row-level would need a registered exception)"},
            "books": books}


def preview_draft(body: dict[str, Any], username: str) -> dict[str, Any]:
    """What a user would see if a draft policy applied to them (alone): for the policy editor's live preview."""
    core = pol.core_user(username) or {"books": ["corporate", "retail"]}
    with store.db() as con:
        prof = (store.find_live(con, "user", username) or {}).get("body", {})
    p = pol.build(username, {**core, "is_admin": False}, prof, [body])
    out = {}
    for book in ("corporate", "retail"):
        exp = _exposure()[book]
        ids = p.allowed_ids(book)
        seen = exp.iloc[0:0] if not p.allows_book(book) else exp if ids is None else exp[exp[dims.KEY[book]].astype(str).isin(ids)]
        out[book] = {"customers": int(len(seen)), "of": int(len(exp)), "ead_sar_mn": float(seen["ead_sar_mn"].sum()),
                     "of_ead_sar_mn": float(exp["ead_sar_mn"].sum())}
    return {"username": username, "policy": p.describe(), "books": out}


# ------------------------------------------------------------------ workflow simulation (A1)
@lru_cache(maxsize=1)
def _doa() -> dict[str, Any]:
    return json.loads((V5 / "data" / "dealdesk" / "params" / "v1" / "doa.json").read_text())


def _proposals() -> list[dict[str, Any]]:
    try:
        p = pd.read_parquet(V5 / "data" / "dealdesk" / "dd-saudi-v1" / "dd_proposal.parquet")
        return p.head(15).to_dict("records")
    except Exception:  # noqa: BLE001
        return []


def samples() -> dict[str, list[dict[str, Any]]]:
    """Sample objects a workflow can be simulated on, per object type, from the real domains."""
    corp = dims.corporate()
    crit: list[str] = []
    try:
        from backend.ews_domain import reader
        rel = reader.exposure("corporate")
        rows = reader.q(f"SELECT borrower_id, MAX(ews_score) AS s FROM {rel} WHERE ews_band='critical' AND "
                        f"reporting_quarter=(SELECT MAX(reporting_quarter) FROM {rel}) GROUP BY 1 ORDER BY s DESC, borrower_id")
        crit = [r["borrower_id"] for r in rows]
    except Exception:  # noqa: BLE001
        crit = ["CB00398", "CB00513"]
    # Names in the portfolios of the RMs who sign in come first (the RM demo), then the highest scores.
    signed = {"RM0005", "RM0011"}
    crit = sorted(crit, key=lambda b: (0 if b in corp.index and corp.loc[b, "rm_id"] in signed else 1, crit.index(b)))[:8]
    ews = []
    for bid in crit:
        if bid in corp.index:
            d = corp.loc[bid]
            ews.append({"id": bid, "label": f"{bid} {d['borrower_name']} ({d['sector']}, {d['region']})", "band": "critical",
                        "rm_id": d["rm_id"], "rm_name": d["rm_name"], "branch": d["branch_name"]})
    deals = []
    for p in _proposals():
        pid = str(p.get("proposal_id"))
        amount = float(p.get("requested_amount_sar_mn") or p.get("amount_sar_mn") or 0)
        deals.append({"id": pid, "label": f"{pid} {p.get('obligor_name') or p.get('borrower_name') or ''}".strip(),
                      "exposure_after_sar_mn": float(p.get("exposure_after_sar_mn") or amount),
                      "rating": str(p.get("rating") or p.get("obligor_rating") or "BBB-"),
                      "rm_name": str(p.get("rm_name") or p.get("rm") or ""), "soft_breaches": int(p.get("soft_breaches") or 0)})
    if is_dealdesk():
        return {"deal_proposal": deals,
                "playbook_report": [{"id": "PB-DD06", "label": "DD-06 committee paper", "owner": "khalid.alotaibi"}],
                "parameter_table": [{"id": "dd-ftp", "label": "Deal Desk FTP curve v1 -> v2", "owner": "abdullah.alzahrani", "materiality": "medium"}]}
    return {
        "ews_name": ews,
        "deal_proposal": deals,
        "playbook_report": [{"id": "PB-Q2-CC", "label": "Q2 2026 credit committee pack", "owner": "khalid.alotaibi"},
                            {"id": "PB-CONS", "label": "Construction sector review", "owner": "sara.aldosari"}],
        "whatif_scenario": [{"id": "WI-OIL40", "label": "Oil price -40% (corporate)", "owner": "abdullah.alzahrani"}],
        "parameter_table": [{"id": "dd-ftp", "label": "Deal Desk FTP curve v1 -> v2", "owner": "abdullah.alzahrani", "materiality": "medium"},
                            {"id": "ews-rules", "label": "Early Warning rule set gw-ews-1.3.0 threshold change", "owner": "lama.almutairi",
                             "materiality": "high"}],
    }


def _doa_level(exposure: float, rating: str, soft: int) -> dict[str, Any]:
    from backend.v5common import ratings
    order = getattr(ratings, "ORDER", None) or getattr(ratings, "SCALE", None)
    def rank(r: str) -> int:
        try:
            return list(order).index(r) if order else 0
        except ValueError:
            return 0
    for row in _doa()["rows"]:
        if exposure <= row["max_exposure"] and soft <= row["max_soft"] and (not order or rank(rating) <= rank(row["min_rating"])):
            return row
    return _doa()["rows"][-1]


def _who(assignee: dict[str, Any], obj: dict[str, Any], users: list[dict[str, Any]]) -> str:
    t = assignee.get("type")
    names = {u["username"]: u["name"] for u in users}
    if t == "user":
        return names.get(assignee.get("value"), assignee.get("value", ""))
    if t == "role":
        hits = [u["name"] for u in users if u.get("role") == assignee.get("value")]
        role = next((r["name"] for r in seed.ROLES if r["id"] == assignee.get("value")), assignee.get("value"))
        return f"{role} ({', '.join(hits[:3])})" if hits else role
    if t == "team":
        team = next((x["name"] for x in seed.TEAMS if x["id"] == assignee.get("value")), assignee.get("value"))
        return f"Team {team}"
    if t == "rm_of_object":
        return f"RM {obj.get('rm_name') or 'of the borrower'}"
    if t == "owner_of_object":
        return names.get(obj.get("owner", ""), obj.get("owner") or "the object's owner")
    if t == "doa_level":
        return obj.get("_doa_level", "DOA level")
    if t == "doa_next":
        return obj.get("_doa_next", "next DOA level")
    return str(assignee.get("value") or t)


def _cond_ok(conds: list[dict[str, Any]], obj: dict[str, Any]) -> bool:
    for c in conds or []:
        v = obj.get(c.get("field"))
        op, want = c.get("op", "="), c.get("value")
        if op == "=" and str(v) != str(want):
            return False
        if op == "in" and v not in (want or []):
            return False
        if op == ">" and not (v is not None and float(v) > float(want)):
            return False
        if op == ">=" and not (v is not None and float(v) >= float(want)):
            return False
    return True


def simulate(workflow: dict[str, Any], obj: dict[str, Any], start: str | None = None) -> dict[str, Any]:
    """Walk a workflow on a sample object: who gets each step, when it is due, when it escalates and to whom."""
    with store.db() as con:
        users = [u["body"] for u in store.live_list(con, "user")]
    obj = dict(obj)
    if workflow.get("object_type") == "deal_proposal":
        lvl = _doa_level(float(obj.get("exposure_after_sar_mn") or 0), str(obj.get("rating") or "BBB-"),
                         int(obj.get("soft_breaches") or 0))
        rows = _doa()["rows"]
        nxt = next((r for r in rows if r["rank"] == lvl["rank"] + 1), lvl)
        obj["_doa_level"] = lvl["level"]
        obj["_doa_next"] = nxt["level"]
    t0 = datetime.fromisoformat((start or "2026-10-12T08:00:00").replace("Z", ""))
    trig = workflow.get("trigger") or {}
    fires = _cond_ok(trig.get("conditions") or [], obj)
    timeline, t = [], t0
    for i, s in enumerate(workflow.get("steps") or []):
        if not _cond_ok(s.get("condition") or [], obj):
            timeline.append({"step": s.get("name"), "kind": s.get("kind"), "skipped": True,
                             "why": "condition not met: " + ", ".join(f"{c['field']} {c['op']} {c['value']}" for c in s.get("condition") or [])})
            continue
        sla = float(s.get("sla_days") or 0)
        due = t + timedelta(days=sla)
        esc = s.get("escalate_after_days")
        timeline.append({
            "n": i + 1, "step": s.get("name"), "kind": s.get("kind"), "assignee": _who(s.get("assignee") or {}, obj, users),
            "starts": t.strftime("%a %d %b %H:%M"), "due": due.strftime("%a %d %b %H:%M"), "sla_days": sla,
            "escalates": ((t + timedelta(days=float(esc))).strftime("%a %d %b %H:%M") if esc not in (None, "") else None),
            "escalate_to": _who(s.get("escalate_to") or {}, obj, users) if s.get("escalate_to") else None,
            "delegation": bool(s.get("delegation")), "notify": ["My workspace", "Mail"] if s.get("kind") != "notify" else ["Mail"],
            "note": s.get("note", "")})
        t = due
    return {"workflow": workflow.get("name"), "object": obj, "fires": fires,
            "trigger": trig, "timeline": timeline,
            "total_days": round((t - t0).total_seconds() / 86400, 1),
            "doa": {"level": obj.get("_doa_level"), "next": obj.get("_doa_next")} if obj.get("_doa_level") else None}


# ------------------------------------------------------------------ Agent Operations (A3)
def runs(con: sqlite3.Connection) -> list[dict[str, Any]]:
    from backend.convo import runlog, telemetry
    # Deal Desk edition: the tokens of every turn, from the per-call telemetry (joined on the run id), so Agent
    # Operations shows what each turn cost in tokens on Opus or on the open model; an open model's cost is 0.
    tokens: dict[str, dict[str, Any]] = {}
    try:
        tokens = {t["run_id"]: t for t in telemetry.per_run() if t.get("run_id")}
    except Exception:  # noqa: BLE001 - no telemetry yet
        tokens = {}
    live = []
    for r in runlog.read():
        t = tokens.get(r.get("run_id") or "", {})
        tin, tout = int(t.get("input_tokens") or r.get("tokens_in", 0) or 0), int(t.get("output_tokens") or r.get("tokens_out", 0) or 0)
        live.append({**r, "tokens_in": tin, "tokens_out": tout, "model_ms": int(t.get("model_ms") or 0), "model_calls": int(t.get("calls") or 0),
                     "provider": t.get("provider") or "", "experiment": t.get("experiment") or "",
                     "cost_usd": r.get("cost_usd") or _cost(t.get("provider") or "", t.get("model") or r.get("model") or "", tin, tout),
                     "figures_validated": r.get("figures_validated", 0), "seeded": False})
    out = live + store.seeded_runs(con)
    if is_dealdesk():
        # the edition's Agent Operations: the modules in the product only (a run log kept from the full product
        # may hold What-If, Lenses or Scorecard turns)
        keep = {"cockpit", "deal_desk", "dealdesk", "playbook", "projects", "admin", "brief", "noor", "mail", "policy_docs", "data_builder", ""}
        out = [r for r in out if str(r.get("module") or "").lower().replace("-", "_").replace(" ", "_") in keep]
    out.sort(key=lambda r: r.get("at", ""), reverse=True)
    return out


#: List prices per million tokens (input, output) for the hosted models; an open model on the bank's own box is 0.
_PRICES = {"opus": (15.0, 75.0), "sonnet": (3.0, 15.0), "haiku": (1.0, 5.0)}


def _cost(provider: str, model: str, tokens_in: int, tokens_out: int) -> float:
    if provider and provider != "anthropic":
        return 0.0
    m = (model or "").lower()
    for k, (pi, po) in _PRICES.items():
        if k in m:
            return round((tokens_in * pi + tokens_out * po) / 1_000_000, 4)
    return 0.0


def _pct(vals: list[float], q: float) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    k = max(0, min(len(s) - 1, int(round(q * (len(s) - 1)))))
    return float(s[k])


def daily(all_runs: list[dict[str, Any]]) -> dict[str, Any]:
    by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_mod: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in all_runs:
        by_day[r["at"][:10]].append(r)
        by_mod[r.get("module", "")].append(r)
    days = []
    for d in sorted(by_day):
        rs = by_day[d]
        lat = [float(r.get("latency_ms") or 0) for r in rs]
        days.append({"day": d, "runs": len(rs), "p50_ms": _pct(lat, 0.5), "p95_ms": _pct(lat, 0.95),
                     "cost_usd": round(sum(float(r.get("cost_usd") or 0) for r in rs), 4),
                     "refused": sum(1 for r in rs if r.get("outcome") == "refused"),
                     "failed": sum(1 for r in rs if str(r.get("outcome", "")).startswith("failed"))})
    mods = []
    for m in sorted(by_mod):
        rs = by_mod[m]
        lat = [float(r.get("latency_ms") or 0) for r in rs]
        mods.append({"module": m, "runs": len(rs), "p50_ms": _pct(lat, 0.5), "p95_ms": _pct(lat, 0.95),
                     "cost_usd": round(sum(float(r.get("cost_usd") or 0) for r in rs), 4),
                     "refusal_rate": round(sum(1 for r in rs if r.get("outcome") == "refused") / len(rs), 4),
                     "failure_rate": round(sum(1 for r in rs if str(r.get("outcome", "")).startswith("failed")) / len(rs), 4)})
    return {"days": days, "modules": mods}


# ------------------------------------------------------------------ AI Studio test bench (A4)
def system_prompt(cfg: dict[str, Any]) -> str:
    g = "\n".join(f"- {x['term']}: {x['meaning']}" for x in cfg.get("glossary") or [])
    rails = cfg.get("guardrails") or {}
    style = cfg.get("answer_style") or {}
    return "\n\n".join(x for x in [
        cfg.get("instructions", ""), f"House tone: {cfg.get('tone', '')}",
        f"Glossary:\n{g}" if g else "",
        "Knowledge: " + "; ".join(cfg.get("knowledge") or []),
        "Tools allowed: " + ", ".join(cfg.get("tools") or []),
        "Guardrails: " + "; ".join(k.replace("_", " ") for k, v in rails.items() if v is True)
        + (f"; at most {rails['max_steps']} steps" if rails.get("max_steps") else ""),
        f"Answer style: {style.get('length', 'medium')} length; tables {'on' if style.get('tables') else 'off'}; "
        f"charts {'on' if style.get('charts') else 'off'}."] if x)


_OUT_OF_SCOPE = re.compile(r"\b(weather|football|bitcoin|another bank|competitor'?s|stock tip|recipe)\b", re.I)


def bench(cfg: dict[str, Any], question: str) -> dict[str, Any]:
    """How a configuration would take a question: the composed instructions, the tools it may call for it, and
    whether a guardrail refuses it. The live configuration and a draft are run side by side."""
    tools = cfg.get("tools") or []
    ql = question.lower()
    wanted = [t for t in tools if any(w in ql for w in t.split("_") if len(w) > 3)] or ["run_query"]
    refused = bool((cfg.get("guardrails") or {}).get("scope_refusal")) and bool(_OUT_OF_SCOPE.search(question))
    killed = bool(cfg.get("kill_switch"))
    model = "planner (kill switch on)" if killed else cfg.get("model")
    return {"model": model, "model_display": seed.model_display(model),
            "system_prompt": system_prompt(cfg), "prompt_chars": len(system_prompt(cfg)),
            "tools_planned": [] if refused else ["inspect_catalog", *wanted, "finalize_answer"],
            "refused": refused,
            "refusal": "Outside this module's data: the assistant declines and says where to ask instead." if refused else "",
            "answer_style": cfg.get("answer_style"), "guardrails": cfg.get("guardrails")}


# ------------------------------------------------------------------ Settings: parameter register, feeds (A5)
def parameter_register() -> list[dict[str, Any]]:
    out = []
    pdir = V5 / "data" / "dealdesk" / "params" / "v1"
    for f in sorted(pdir.glob("*.json")):
        try:
            d = json.loads(f.read_text())
        except ValueError:
            continue
        acr = {"ccf": "CCF", "doa": "DOA", "ftp": "FTP", "lgd": "LGD", "pd": "PD", "sa": "SA", "opex": "Opex"}
        nm = " ".join(acr.get(w.lower(), w.capitalize()) for w in str(d.get("name", f.stem)).replace("_", " ").split())
        out.append({"id": f"dd-{f.stem}", "module": "Deal Desk", "name": nm,
                    "owner": d.get("owner", "Risk"), "version": d.get("version", "v1"), "effective_from": d.get("effective_from", ""),
                    "approved_by": d.get("approved_by", ""), "description": d.get("description", ""),
                    "source": f"data/dealdesk/params/v1/{f.name}", "workflow": "WF-PARAM"})
    if is_dealdesk():
        return out   # the edition's parameter tables are Deal Desk's
    try:
        m = json.loads((V5 / "data" / "ews" / "EWS_PACKAGE_MANIFEST.json").read_text())
        rs = m.get("ruleset_version") or m.get("rule_set") or "gw-ews-1.3.0"
    except Exception:  # noqa: BLE001
        rs = "gw-ews-1.3.0"
    out.append({"id": "ews-rules", "module": "Early Warning", "name": "Early Warning rule set", "owner": "Credit Risk Management",
                "version": str(rs), "effective_from": "2026-10-01", "approved_by": "Faisal Al-Qahtani (Head of Risk)",
                "description": "Rules, weights and band thresholds that score every exposure.", "source": "backend/ews_domain",
                "workflow": "WF-PARAM"})
    out.append({"id": "whatif-models", "module": "What-If", "name": "PD/LGD satellite models and MEV paths", "owner": "Model Validation",
                "version": "whatif-v1", "effective_from": "2026-09-30", "approved_by": "Lama Al-Mutairi (Model Validation)",
                "description": "Delta and XGBoost PD models, LGD-collateral haircuts, macro scenario paths.",
                "source": "var/whatif_v5 (built by ops/whatif_build_domain.py)", "workflow": "WF-PARAM"})
    for sc in ("RET-APP", "RET-BEH", "SME-ANN"):
        out.append({"id": f"sc-{sc.lower()}", "module": "Scorecard Validation", "name": f"Scorecard {sc} thresholds",
                    "owner": "Model Validation", "version": "v1", "effective_from": "2026-07-01",
                    "approved_by": "Lama Al-Mutairi (Model Validation)",
                    "description": "Red/amber/green thresholds for discrimination, calibration and stability tests.",
                    "source": "backend/scorecard_v5", "workflow": "WF-PARAM"})
    return out


def feeds() -> list[dict[str, Any]]:
    out = []
    def manifest(path: Path) -> dict[str, Any]:
        try:
            return json.loads(path.read_text())
        except Exception:  # noqa: BLE001
            return {}
    rows = [
        ("Corporate book", "data/cockpit_v4_lake/v4-saudi-corporate-20q-v4", "2026Q2"),
        ("Retail book", "data/cockpit_v4_lake/v4-saudi-retail-20m-v5", "2026-08"),
        ("Early Warning (corporate)", "data/ews/ews-saudi-corporate-20q-v4e2", "2026Q2"),
        ("Early Warning (retail)", "data/ews/ews-saudi-retail-20m-v5e1", "2026-08"),
        ("Branches and RMs", "data/branches/branch-saudi-v1", "2026Q2"),
        ("Bureau (SIMAH)", "data/external/bureau-saudi-v1", "2026Q2"),
        ("Open Banking", "data/external/open-banking-saudi-v1", "2026-08"),
        ("Deal Desk proposals", "data/dealdesk/dd-saudi-v1", "2026Q2"),
    ]
    if is_dealdesk():   # the edition's data releases: what Deal Desk reads
        rows = [r for r in rows if not r[0].startswith("Early Warning") and r[0] != "Open Banking"]
    for label, rel, period in rows:
        p = V5 / rel
        m = manifest(p / "manifest.json")
        files = list(p.glob("*.parquet")) if p.exists() else []
        mt = max((f.stat().st_mtime for f in files), default=0)
        out.append({"feed": label, "release": m.get("release_id") or p.name, "as_of": period, "files": len(files),
                    "status": "loaded" if files else "missing",
                    "loaded_at": datetime.fromtimestamp(mt, timezone.utc).strftime("%Y-%m-%d %H:%M") if mt else ""})
    return out


# ------------------------------------------------------------------ Audit log (A6)
_CORE_LABEL = {"login": "Signed in", "logout": "Signed out", "login_failed": "Sign-in failed", "login_locked": "Sign-in locked",
               "view_as": "Viewed as", "admin_read": "Read a mailbox", "send": "Sent mail", "share": "Shared"}
_ADMIN_LABEL = {"change_drafted": "Drafted a change", "change_submitted": "Submitted a change", "change_approved": "Approved a change",
                "change_rejected": "Rejected a change", "change_withdrawn": "Withdrew a change", "kill_switch_on": "Kill switch on",
                "kill_switch_off": "Kill switch off", "evaluation_run": "Ran an evaluation", "password_reset": "Reset a password",
                "export": "Exported"}


def _category(action: str) -> str:
    a = action.lower()
    if a.startswith("login") or a == "logout":
        return "sign-in"
    if "export" in a:
        return "export"
    if a.startswith("change_approved") or a.startswith("change_rejected"):
        return "approval"
    if a.startswith("change_") or a.startswith("kill_switch") or a == "password_reset":
        return "configuration"
    if a == "ai_run":
        return "ai run"
    if a in ("send", "share", "admin_read", "view_as"):
        return "access"
    return "other"


def audit_events(con: sqlite3.Connection, all_runs: list[dict[str, Any]], limit: int = 2000) -> list[dict[str, Any]]:
    out = []
    for e in store.audit_list(con, limit):
        out.append({"at": e["at"], "actor": e["actor"], "action": e["action"], "label": _ADMIN_LABEL.get(e["action"], e["action"]),
                    "category": _category(e["action"]), "object": f"{store.KINDS.get(e['kind'], e['kind'])} {e['target']}".strip(),
                    "detail": e["detail"], "source": "admin"})
    core = pol._ro(pol.core_store_path())  # noqa: SLF001
    if core is not None:
        try:
            for r in core.execute("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,)):
                out.append({"at": r["at"], "actor": r["actor"] or "", "action": r["action"],
                            "label": _CORE_LABEL.get(r["action"], r["action"].replace("_", " ").capitalize()),
                            "category": _category(r["action"]), "object": r["target"] or "",
                            "detail": json.loads(r["detail"] or "{}"), "source": "core",
                            **({"on_behalf_of": r["effective_user"]} if r["effective_user"] and r["effective_user"] != r["actor"] else {})})
        except sqlite3.Error:
            pass
        finally:
            core.close()
    for r in all_runs:
        out.append({"at": r["at"], "actor": r.get("user", ""), "action": "ai_run", "label": "AI run",
                    "category": "ai run", "object": f"{r.get('module', '')}: {str(r.get('question', ''))[:90]}",
                    "detail": {"run_id": r.get("run_id"), "outcome": r.get("outcome"), "latency_ms": r.get("latency_ms")},
                    "source": "agent"})
    out.sort(key=lambda e: e["at"], reverse=True)
    return out[:limit]
