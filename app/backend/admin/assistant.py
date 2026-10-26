"""The Admin assistant (PLAN_R5 Session A): a conversational domain on the shared layer (backend/convo) that explains
the Admin console and drafts configuration from plain words. It never makes anything live: a draft goes through
maker-checker like any change made by hand (the answer carries a "Save as draft" card).

  "Create a workflow so Critical Early Warning names need an RM action plan within 5 days, escalate to the Head of
   Credit after 10"           -> draft_workflow (and a simulation on a real Critical name)
  "Riyadh RMs should only see their own portfolio, without exports"   -> draft_policy (with its preview)
  "What can nawaf.alotaibi see?"                                      -> preview_access
  "What is Agent Operations?"                                         -> read_knowledge
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd

from backend.access import dims
from backend.admin import logic, seed, store
from backend.convo.spec import Domain, Plan, PlanStep, Relation, Tool, ToolContext, ToolResult
from backend.v5common.edition import is_dealdesk

V5 = Path(__file__).resolve().parents[2]
PK = V5 / "docs" / "product_knowledge"

CHARTER = ("You are the Admin assistant of CreditProbe at a Saudi bank. You explain the Admin console (data access "
           "policies, approval workflows, users and teams, Agent Operations, AI Studio, settings, the audit log) and "
           "draft configuration from the administrator's words with the draft_workflow and draft_policy tools. A draft "
           "is never live: it goes through maker-checker (draft, submit, approve by another Admin or CRO). Answer from "
           "the Admin relations, tools and notes only; every figure from a query or tool of this turn.")


def _knowledge() -> dict[str, str]:
    out = {}
    for name in ("admin", "admin_data_access", "admin_workflow", "admin_users", "admin_agent_operations",
                 "admin_ai_studio", "admin_settings", "admin_audit_log"):
        f = PK / f"{name}.md"
        if f.exists():
            out[name.replace("admin_", "").replace("_", " ") if name != "admin" else "admin console"] = f.read_text()
    out.setdefault("maker-checker", "Every configuration change is drafted, submitted, then approved by a second person "
                                    "(an Admin or a CRO) before it goes live. The maker cannot approve their own change.")
    return out


def _live_df(kind: str, flat) -> pd.DataFrame:
    with store.db() as con:
        rows = [flat(x["body"], x) for x in store.live_list(con, kind)]
    return pd.DataFrame(rows)


def relations(scope: dict[str, Any]) -> list[Relation]:
    def pol_flat(b, x):
        return {"policy_id": b["id"], "name": b.get("name"), "status": b.get("status"), "books": ", ".join(b.get("books") or []),
                "scope": "; ".join(f"{bk}: " + ", ".join(f"{f}={'/'.join(v)}" for f, v in (sc or {}).items()) for bk, sc in (b.get("scope") or {}).items()) or "whole book",
                "modules": ", ".join(b.get("modules") or []), "export": (b.get("actions") or {}).get("export", True),
                "masks_names": (b.get("mask") or {}).get("obligor_name", False),
                "assigned_teams": ", ".join((b.get("assignees") or {}).get("teams") or []),
                "assigned_roles": ", ".join((b.get("assignees") or {}).get("roles") or []), "version": x["version"]}

    def wf_flat(b, x):
        return {"workflow_id": b["id"], "name": b.get("name"), "object_type": b.get("object_type"), "steps": len(b.get("steps") or []),
                "sla_days_total": sum(float(s.get("sla_days") or 0) for s in b.get("steps") or []), "version": x["version"]}

    def user_flat(b, x):
        return {"username": b["username"], "name": b.get("name"), "role": b.get("role"), "team": b.get("team"),
                "rm_id": b.get("rm_id"), "status": b.get("status"), "last_activity": b.get("last_activity")}

    def runs_df(_s):
        with store.db() as con:
            rs = logic.runs(con)
        return pd.DataFrame([{"run_id": r["run_id"], "at": r["at"], "module": r.get("module"), "user": r.get("user"),
                              "outcome": r.get("outcome"), "latency_ms": r.get("latency_ms"), "cost_usd": r.get("cost_usd", 0)}
                             for r in rs])

    def changes_df(_s):
        with store.db() as con:
            cs = store.changes(con)
        return pd.DataFrame([{k: c[k] for k in ("change_id", "kind", "object_id", "op", "title", "status", "maker", "checker",
                                                 "created_at")} for c in cs])

    return [
        Relation("policies", "Live data access policies, one row each", lambda s: _live_df("policy", pol_flat), "policy"),
        Relation("workflows", "Live approval workflows", lambda s: _live_df("workflow", wf_flat), "workflow"),
        Relation("users", "Users with their admin role and team", lambda s: _live_df("user", user_flat), "user"),
        Relation("changes", "Configuration changes and their maker-checker status", changes_df, "change"),
        Relation("ai_runs", "AI runs in every module (Agent Operations)", runs_df, "run"),
    ]


# ------------------------------------------------------------------ parsing plain words into configuration
_ACTORS = [
    (r"head of credit", {"type": "user", "value": "noura.alharbi"}, "Head of Credit"),
    (r"head of risk|\bcro\b|chief risk", {"type": "user", "value": "faisal.alqahtani"}, "Head of Risk"),
    (r"model validat|validator", {"type": "role", "value": "validator"}, "Model Validation"),
    (r"analyst", {"type": "role", "value": "analyst"}, "Credit analyst"),
    (r"\brms?\b|relationship manager", {"type": "rm_of_object"}, "RM"),
    (r"admin", {"type": "role", "value": "admin"}, "Admin"),
]
_OBJECTS = [(r"early warning|\bews\b|watchlist", "ews_name"), (r"deal|proposal|\bdoa\b", "deal_proposal"),
            (r"report|playbook|committee pack", "playbook_report"), (r"scenario|what-?if", "whatif_scenario"),
            (r"parameter", "parameter_table")]


def _actor(text: str) -> tuple[dict[str, Any], str] | None:
    for pat, a, label in _ACTORS:
        if re.search(pat, text, re.I):
            return a, label
    return None


def parse_workflow(text: str) -> dict[str, Any]:
    t = text.strip()
    obj = next((o for pat, o in _OBJECTS if re.search(pat, t, re.I)), "ews_name")
    band = next((b for b in ("critical", "high") if re.search(rf"\b{b}\b", t, re.I)), None)
    steps: list[dict[str, Any]] = []
    # first obligation: "<actor> <task> within N days"
    m = re.search(r"need[s]?\s+(?:an?\s+)?(.+?)\s+within\s+(\d+)\s*(?:working\s+)?days?", t, re.I) or \
        re.search(r"(.+?)\s+within\s+(\d+)\s*days?", t, re.I)
    task = (m.group(1) if m else "Review").strip(" ,.")
    sla = float(m.group(2)) if m else 5.0
    who = _actor(task) or _actor(t) or ({"type": "rm_of_object"}, "RM")
    name = re.sub(r"^(an?|the)\s+", "", task, flags=re.I)
    name = name[0].upper() + name[1:] if name else "Action"
    esc = re.search(r"escalat\w*\s+(?:it\s+)?to\s+(?:the\s+)?(.+?)\s+after\s+(\d+)", t, re.I)
    esc_to, esc_after, esc_label = None, None, ""
    if esc:
        a = _actor(esc.group(1))
        if a:
            esc_to, esc_label = a
        esc_after = float(esc.group(2))
    steps.append({"id": "s1", "name": name, "kind": "action", "assignee": who[0], "sla_days": sla,
                  "escalate_after_days": esc_after, "escalate_to": esc_to, "condition": [], "delegation": True, "note": ""})
    ap = re.search(r"then\s+(?:the\s+)?(.+?)\s+(?:approves|decides|signs off)(?:\s+within\s+(\d+)\s*days?)?", t, re.I)
    if ap and _actor(ap.group(1)):
        a, label = _actor(ap.group(1))
        steps.append({"id": "s2", "name": f"{label} decision", "kind": "approve", "assignee": a,
                      "sla_days": float(ap.group(2) or 3), "escalate_after_days": None, "escalate_to": None, "condition": [],
                      "delegation": True, "note": ""})
    elif esc_to is not None and obj == "ews_name":
        steps.append({"id": "s2", "name": "Watchlist decision", "kind": "approve", "assignee": esc_to, "sla_days": 3.0,
                      "escalate_after_days": None, "escalate_to": None, "condition": [], "delegation": True, "note": ""})
    label = {"ews_name": "Early Warning names", "deal_proposal": "Deal Desk proposals", "playbook_report": "Playbook reports",
             "whatif_scenario": "What-If scenarios", "parameter_table": "Parameter-table changes"}[obj]
    wname = f"{band.title() + ' ' if band else ''}{label}: {name if re.match(r"^[A-Z]{2}", name) else name[0].lower() + name[1:]}"
    desc = f"{name} within {sla:g} days" + (f"; escalates to the {esc_label} after {esc_after:g} days" if esc_after else "") + "."
    return {"name": wname, "status": "active", "object_type": obj, "description": desc,
            "trigger": {"event": {"ews_name": "ews_band_changed", "deal_proposal": "proposal_submitted",
                                  "playbook_report": "report_submitted", "whatif_scenario": "scenario_marked_official",
                                  "parameter_table": "parameter_change_drafted"}[obj],
                        "conditions": [{"field": "band", "op": "=", "value": band}] if band and obj == "ews_name" else []},
            "steps": steps, "drafted_from": t}


def parse_policy(text: str) -> dict[str, Any]:
    t = text.strip()
    opts = dims.options()
    has_retail = bool(re.search(r"\bretail\b", t, re.I))
    has_corp = bool(re.search(r"\bcorporate\b|\brms?\b|relationship manager|portfolio|sector", t, re.I))
    books = ["corporate", "retail"] if (has_retail and has_corp) or not (has_retail or has_corp) else \
        (["retail"] if has_retail else ["corporate"])
    scope: dict[str, dict[str, list[str]]] = {}
    for b in books:
        sc: dict[str, list[str]] = {}
        regions = [r for r in opts[b]["regions"] if re.search(rf"\b{re.escape(r)}\b", t, re.I)]
        if regions and not re.search(r"\b(riyadh)\s+rms?\b", t, re.I):
            sc["regions"] = regions
        if b == "corporate":
            secs = [s for s in opts[b]["sectors"] if re.search(rf"\b{re.escape(s)}\b", t, re.I)]
            if secs:
                sc["sectors"] = secs
            if re.search(r"own portfolio|their portfolio|own borrowers|their own", t, re.I):
                sc["rm_ids"] = ["own"]
        segs = [s for s in opts[b]["segments"] if re.search(rf"\b{re.escape(s)}\b", t, re.I)]
        if segs:
            sc["segments"] = segs
        if sc:
            scope[b] = sc
    read_only = bool(re.search(r"read[- ]only|cannot change|no changes", t, re.I))
    actions = {"export": not (read_only or re.search(r"(without|no|not)\s+export", t, re.I)),
               "send": not (read_only or re.search(r"(without|no|not)\s+(send|shar)", t, re.I)),
               "approve": not read_only and not re.search(r"\brms?\b", t, re.I),
               "run_model": not read_only and not re.search(r"\brms?\b", t, re.I)}
    mask = {"obligor_name": bool(re.search(r"mask\w*\s+(obligor\s+)?names?|names?\s+masked|hide\s+names?", t, re.I)),
            "obligor_id": bool(re.search(r"mask\w*\s+ids?|ids?\s+masked", t, re.I))}
    roles = [r for r, pat in (("rm", r"\brms?\b|relationship manager"), ("auditor", r"auditor|audit"),
                              ("validator", r"validator"), ("analyst", r"analyst")) if re.search(pat, t, re.I)]
    teams = ["T-RMC"] if re.search(r"riyadh\s+rms?", t, re.I) else []
    name = t[0].upper() + t[1:]
    name = re.sub(r"\s+should\s+", " ", name)[:80].rstrip(". ")
    return {"name": name, "status": "active", "description": t, "books": books, "scope": scope,
            "modules": ["cockpit", "early_warning", "borrower_360", "deal_desk", "projects", "mail", "playbook"] if "rm" in roles else ["*"],
            "actions": actions, "mask": mask,
            "assignees": {"users": [], "roles": [] if teams else roles, "teams": teams}, "drafted_from": t}


# ------------------------------------------------------------------ tools
def t_draft_workflow(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    wf = parse_workflow(str(args.get("text") or ctx.question))
    sample = next(iter(logic.samples().get(wf["object_type"]) or []), {"id": "sample", "label": "sample"})
    sim = logic.simulate(wf, sample)
    rows = [{"step": s.get("n"), "name": s["step"], "assignee": s.get("assignee"), "due": s.get("due"),
             "escalates": s.get("escalates") or "", "escalate_to": s.get("escalate_to") or ""} for s in sim["timeline"] if not s.get("skipped")]
    return ToolResult(summary=f"Drafted workflow '{wf['name']}' with {len(wf['steps'])} steps; simulated on {sample.get('label')}.",
                      data={"workflow": wf, "simulated_on": sample.get("label"), "total_days": sim["total_days"]}, rows=rows,
                      blocks=[{"type": "admin_draft", "kind": "workflow", "title": wf["name"], "body": wf, "simulation": sim}],
                      title=wf["name"])


def t_draft_policy(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    pol = parse_policy(str(args.get("text") or ctx.question))
    who = "nawaf.alotaibi" if "rm" in pol["assignees"]["roles"] or "T-RMC" in pol["assignees"]["teams"] else \
        "hind.alsubaie" if "auditor" in pol["assignees"]["roles"] else "sara.aldosari"
    pv = logic.preview_draft(pol, who)
    rows = [{"book": b, "customers_visible": v["customers"], "customers_in_book": v["of"],
             "ead_visible_sar_mn": round(v["ead_sar_mn"], 1), "ead_in_book_sar_mn": round(v["of_ead_sar_mn"], 1)}
            for b, v in pv["books"].items()]
    return ToolResult(summary=f"Drafted policy '{pol['name']}'; previewed for {who}.",
                      data={"policy": pol, "previewed_for": who}, rows=rows,
                      blocks=[{"type": "admin_draft", "kind": "policy", "title": pol["name"], "body": pol, "preview": pv}],
                      title=pol["name"])


def t_preview_access(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    q = str(args.get("username") or "")
    with store.db() as con:
        users = [u["body"] for u in store.live_list(con, "user")]
    u = next((x for x in users if x["username"] == q), None) or next(
        (x for x in users if q and (q.lower() in x["name"].lower() or x["name"].split()[0].lower() in q.lower())), None)
    if u is None:
        u = next((x for x in users if re.search(re.escape(x["name"].split()[0]), ctx.question, re.I)
                  or x["username"] in ctx.question), users[0])
    pv = logic.preview(u["username"])
    rows = [{"book": b["book"], "visible": b["visible"], "customers_visible": b["seen"]["customers"],
             "customers_in_book": b["total"]["customers"], "ead_visible_sar_mn": round(b["seen"]["ead_sar_mn"], 1),
             "ead_in_book_sar_mn": round(b["total"]["ead_sar_mn"], 1)} for b in pv["books"]]
    return ToolResult(summary=f"What {u['name']} sees under {len(pv['policy']['policies']) or 'no'} policies.",
                      data={"user": pv["user"], "policies": pv["policy"]["policies"],
                            "modules_blocked": [m["label"] for m in pv["modules"] if not m["allowed"]],
                            "actions_blocked": [a["label"] for a in pv["actions"] if not a["allowed"]],
                            "masks_names": pv["policy"]["mask"]["obligor_name"]}, rows=rows,
                      blocks=[{"type": "admin_preview", "username": u["username"], "preview": pv}])


TOOLS = [
    Tool("draft_workflow", "Draft an approval workflow from plain words (steps, assignees, SLA, escalation) and simulate it "
         "on a real sample object. Returns a draft card; nothing goes live.",
         {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}, t_draft_workflow,
         message="Drafting the workflow"),
    Tool("draft_policy", "Draft a data access policy from plain words (books, sector/region/branch/RM scope, modules, "
         "actions, masking) and preview what it shows. Returns a draft card; nothing goes live.",
         {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}, t_draft_policy,
         message="Drafting the policy"),
    Tool("preview_access", "What a user would see: modules, actions, customers and EAD visible per book.",
         {"type": "object", "properties": {"username": {"type": "string"}}}, t_preview_access,
         message="Previewing the user's access"),
]


# ------------------------------------------------------------------ deterministic planner
def _fmt(v: float) -> str:
    return f"{v:,.1f}"


def planner(question: str, ctx: ToolContext) -> Plan:
    q = question.lower()
    if re.search(r"workflow|escalat|within \d+ days|sign-?off|approval (chain|route)", q) and \
            not re.search(r"\b(who (changed|edited|approved|made)|what changed|recent(ly)? changes?|pending|awaiting)\b", q):
        def write(res):
            r = res[0]
            if r["error"]:
                return {"markdown": f"I could not draft that workflow: {r['error']}"}
            wf = r["out"]["data"]["workflow"]
            lines = [f"I drafted **{wf['name']}** with {len(wf['steps'])} step{'s' if len(wf['steps']) != 1 else ''}. It is a draft: save it, then submit it "
                     "for approval by another Admin or CRO before it goes live."]
            for i, s in enumerate(wf["steps"], 1):
                lines.append(f"{i}. **{s['name']}**: due in {s['sla_days']:g} days"
                             + (f", escalates after {s['escalate_after_days']:g} days" if s.get("escalate_after_days") else ""))
            lines.append(f"Simulated on {r['out']['data']['simulated_on']}: the route takes {r['out']['data']['total_days']:g} days end to end.")
            return {"markdown": "\n".join(lines), "tables": [{"artifact_id": r["out"]["artifact_id"], "title": "Simulated route"}],
                    "suggestions": ["Simulate it on another name", "Who approves Deal Desk proposals above SAR 100 m?"]}
        return Plan([PlanStep("draft_workflow", {"text": question})], write)
    if re.search(r"(see only|only see|should see|policy|mask|read-only|restrict|access to)", q) and not re.search(r"what can|view as", q) \
            and not re.search(r"\b(who (changed|edited|approved|made)|changes|changed|pending|awaiting)\b", q):
        def write(res):
            r = res[0]
            if r["error"]:
                return {"markdown": f"I could not draft that policy: {r['error']}"}
            p = r["out"]["data"]["policy"]
            acts = [k.replace("_", " ") for k, v in p["actions"].items() if not v]
            md = (f"I drafted the policy **{p['name']}**: books {', '.join(p['books'])}"
                  + "".join(f"; {b} scope " + ", ".join(f"{f} = {', '.join(v)}" for f, v in sc.items()) for b, sc in p["scope"].items())
                  + (f"; not allowed: {', '.join(acts)}" if acts else "")
                  + ("; obligor names masked" if p["mask"]["obligor_name"] else "") + ". "
                  + f"Previewed for {r['out']['data']['previewed_for']} below. Save it as a draft, then submit it for approval.")
            return {"markdown": md, "tables": [{"artifact_id": r["out"]["artifact_id"], "title": "What the policy shows"}]}
        return Plan([PlanStep("draft_policy", {"text": question})], write)
    if re.search(r"what can|view as|sees?\b|access of", q):
        m = re.search(r"([a-z]+\.[a-z]+)", q)
        def write(res):
            r = res[0]
            if r["error"]:
                return {"markdown": f"I could not preview that user: {r['error']}"}
            d = r["out"]["data"]
            pols = ", ".join(p["name"] for p in d["policies"]) or "no policy (the books on their profile)"
            md = (f"**{d['user']['name']}** sees CreditProbe under {pols}."
                  + (f" Modules not open: {', '.join(d['modules_blocked'])}." if d["modules_blocked"] else " Every module is open.")
                  + (f" Not allowed: {', '.join(d['actions_blocked'])}." if d["actions_blocked"] else "")
                  + (" Obligor names are masked." if d["masks_names"] else ""))
            return {"markdown": md, "tables": [{"artifact_id": r["out"]["artifact_id"], "title": "Rows visible per book"}]}
        return Plan([PlanStep("preview_access", {"username": m.group(1) if m else ""})], write)
    if re.search(r"\b(who (changed|edited|approved|made)|recent(ly)? changes?|what changed|changes? (this|last|in the)|"
                 r"pending (approvals?|changes?)|awaiting approval|maker|checker)\b", q):
        # R10 C4: answered from the change log, not a knowledge card.
        sql = ("SELECT change_id, kind, title, op, status, maker, checker, created_at FROM changes "
               "ORDER BY created_at DESC LIMIT 20")

        def write_changes(res):
            r = res[0]
            if r["error"]:
                return {"markdown": f"I could not read the change log: {r['error']}"}
            rows = r["out"].get("rows") or []
            if not rows:
                return {"markdown": "No configuration change has been made yet: the change log is empty."}
            kinds = "policy" if "polic" in q else "workflow" if "workflow" in q else ""
            sel = [x for x in rows if not kinds or x.get("kind") == kinds] or rows
            pend = [x for x in sel if str(x.get("status")) in ("draft", "submitted", "pending")]
            top = sel[0]
            md = (f"**{len(sel)}** recent {kinds + ' ' if kinds else ''}change{'s' if len(sel) != 1 else ''} in the log; "
                  f"**{len(pend)}** still awaiting approval. The latest: **{top.get('title')}** ({top.get('kind')}, "
                  f"{top.get('status')}) by {top.get('maker') or 'unknown'}"
                  + (f", checked by {top.get('checker')}" if top.get("checker") else "") + f" on {str(top.get('created_at'))[:10]}.")
            return {"markdown": md, "tables": [{"artifact_id": r["out"]["artifact_id"], "title": "Recent configuration changes"}]}
        return Plan([PlanStep("run_query", {"sql": sql, "purpose": "Recent configuration changes"})], write_changes)
    topic = next((k for k in ("agent operations", "ai studio", "data access", "workflow", "users", "settings", "audit log")
                  if k in q or (k == "users" and "team" in q)), "admin console")
    if "lens" in q:
        topic = "admin console"

    def write(res):
        r = res[0]
        text = r["out"].get("text", "") if not r["error"] else ""
        if not text:
            return {"markdown": "Admin runs CreditProbe: data access, workflows, users, AI operations and settings."}
        # skip the card's front matter (id:, name:, screen:, keywords:, example:) and headings
        body = [ln for ln in text.splitlines() if ln.strip() and not ln.startswith("#") and ln.strip() != "---"
                and not re.match(r"^\s*(id|name|screen|keywords|example|examples|aliases|tags)\s*:", ln)][:8]
        return {"markdown": "\n".join(body)}
    return Plan([PlanStep("read_knowledge", {"topic": topic})], write)


def suggestions(scope: dict[str, Any], state: dict[str, Any]) -> list[dict[str, str]]:
    first = ({"label": "Large proposals: CRO approval in 5 days", "send": "Create a workflow so proposals above SAR 100 m need the CRO's approval within 5 days, escalate to the Executive Credit Committee after 10"}
             if is_dealdesk() else
             {"label": "Critical EWS names: RM action plan in 5 days", "send": "Create a workflow so Critical Early Warning names need an RM action plan within 5 days, escalate to the Head of Credit after 10"})
    return [first,
            {"label": "What can Nawaf see?", "send": "What can nawaf.alotaibi see?"},
            {"label": "Auditor read-only, names masked", "send": "Auditors should have read-only access with obligor names masked"},
            {"label": "What is Agent Operations?", "send": "What is Agent Operations?"}]


DOMAIN = Domain(key="admin", title="Admin", charter=CHARTER, relations=relations, tools=TOOLS, knowledge=_knowledge(),
                planner=planner, scope_label=lambda s: "the Admin console", scope_key=lambda s: f"admin|{int(__import__('time').time() // 30)}",
                suggestions=suggestions, max_steps=6)
