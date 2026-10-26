"""The Admin data domain release (PLAN_R5 A7): the seeded Admin content as parquet, registered in Data Builder.

    .venv/bin/python -m backend.admin.build [--check]

Writes data/admin/admin-saudi-v1/{admin_users, admin_roles, admin_teams, admin_policies, admin_policy_scope,
admin_workflow_steps, admin_studio, admin_ai_runs}.parquet and manifest.json. Deterministic (the seed is fixed);
`--check` rebuilds into memory and fails if the committed files differ. Keyed to Core users (username), the
Branches and RMs domain (rm_id, branch_id) and the books' dimension values (policy scope), as the sync test checks.
The live Admin store (var/admin) starts from the same seed and then moves by maker-checker changes.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

from backend.admin import seed

V5 = Path(__file__).resolve().parents[2]
RELEASE = "admin-saudi-v1"
OUT = V5 / "data" / "admin" / RELEASE
SNAPSHOT = "2026-10-11"

DICTIONARY = {
    "snapshot": "The date of the Admin configuration snapshot.",
    "username": "The user's sign-in name: the Core directory's stable ID.",
    "name": "Display name.", "title": "Job title.", "department": "Department.",
    "role": "Admin role: admin, cro, analyst, rm, auditor or validator.", "team": "Admin team ID (T-...).",
    "core_team": "The team key on the Core directory (admin, risk, corporate, retail, validation, audit).",
    "rm_id": "The user's relationship-manager ID in the Branches and RMs domain (RMs only).",
    "branch_id": "The user's base branch (RMs only).", "status": "active, invited, deactivated or retired.",
    "books": "Books on the user's profile, comma-separated.", "last_activity": "Last time the user was active (UTC).",
    "role_id": "Role ID.", "description": "What it is for.", "modules": "Modules opened, comma-separated (* = all).",
    "permissions": "Admin permissions of the role, comma-separated.", "team_id": "Team ID.", "lead": "Team lead (username).",
    "policy_id": "Data access policy ID.", "policy_name": "Policy name.",
    "export": "1 when the policy allows exports, otherwise 0.", "send": "1 when the policy allows sending through Mail.",
    "approve": "1 when the policy allows approving in workflows.", "run_model": "1 when the policy allows running models.",
    "mask_obligor_name": "1 when obligor names are masked.", "mask_obligor_id": "1 when obligor IDs are masked.",
    "assigned_users": "Users the policy is assigned to.", "assigned_roles": "Roles the policy is assigned to.",
    "assigned_teams": "Teams the policy is assigned to.", "book": "corporate or retail.",
    "field": "The dimension the policy restricts (sectors, regions, branches, rm_ids, segments...).",
    "value": "One allowed value of that dimension ('own' = the user's own).",
    "workflow_id": "Approval workflow ID.", "workflow_name": "Workflow name.", "object_type": "What the workflow routes.",
    "step_no": "Step number in the workflow.", "step_name": "Step name.", "kind": "action, review, approve or notify.",
    "assignee": "Who the step goes to.", "sla_days": "Days allowed for the step.", "escalate_after_days": "Days before escalation.",
    "escalate_to": "Who the step escalates to.", "module": "Module key.", "model": "Model the assistant uses (display name, e.g. LLM model 1.1; real IDs in the Admin config).",
    "tools": "Tools the assistant may call, comma-separated.", "kill_switch": "1 when the assistant is switched to planner mode.",
    "read_only": "1 when the configuration is frozen (the Cockpit).", "run_id": "AI run ID.", "at": "When the run started (UTC).",
    "user": "Who asked.", "question": "The question.", "outcome": "completed, refused or failed.",
    "latency_ms": "End-to-end latency in milliseconds.", "tokens_in": "Model input tokens.", "tokens_out": "Model output tokens.",
    "cost_usd": "Model cost in US dollars.", "figures_validated": "Figures the validator checked.",
    "figures_removed": "Figures the validator removed.",
}


def frames() -> dict[str, pd.DataFrame]:
    s = SNAPSHOT
    users = pd.DataFrame([{"snapshot": s, "username": u["username"], "name": u["name"], "title": u["title"],
                           "department": u["department"], "role": u["role"], "team": u["team"], "core_team": u["core_team"],
                           "rm_id": u["rm_id"], "branch_id": u["branch_id"], "status": u["status"],
                           "books": ",".join(u["books"]), "last_activity": u["last_activity"]} for u in seed.users()])
    roles = pd.DataFrame([{"snapshot": s, "role_id": r["id"], "name": r["name"], "description": r["description"],
                           "modules": ",".join(r["modules"]), "permissions": ",".join(r["permissions"])} for r in seed.ROLES])
    teams = pd.DataFrame([{"snapshot": s, "team_id": t["id"], "name": t["name"], "core_team": t["core_team"], "lead": t["lead"],
                           "description": t["description"]} for t in seed.TEAMS])
    pols = pd.DataFrame([{"snapshot": s, "policy_id": p["id"], "policy_name": p["name"], "status": p["status"],
                          "description": p["description"], "books": ",".join(p["books"]), "modules": ",".join(p["modules"]),
                          **{a: int(bool(p["actions"].get(a, True))) for a in ("export", "send", "approve", "run_model")},
                          "mask_obligor_name": int(p["mask"]["obligor_name"]), "mask_obligor_id": int(p["mask"]["obligor_id"]),
                          "assigned_users": ",".join(p["assignees"]["users"]), "assigned_roles": ",".join(p["assignees"]["roles"]),
                          "assigned_teams": ",".join(p["assignees"]["teams"])} for p in seed.POLICIES])
    scope = pd.DataFrame([{"snapshot": s, "policy_id": p["id"], "book": b, "field": f, "value": v}
                          for p in seed.POLICIES for b, sc in (p.get("scope") or {}).items() for f, vals in sc.items() for v in vals],
                         columns=["snapshot", "policy_id", "book", "field", "value"])

    def who(a):
        if not a:
            return ""
        return f"{a.get('type')}:{a.get('value', '')}".rstrip(":")
    steps = pd.DataFrame([{"snapshot": s, "workflow_id": w["id"], "workflow_name": w["name"], "object_type": w["object_type"],
                           "step_no": i + 1, "step_name": st["name"], "kind": st["kind"], "assignee": who(st["assignee"]),
                           "sla_days": float(st["sla_days"]), "escalate_after_days": float(st["escalate_after_days"] or 0),
                           "escalate_to": who(st.get("escalate_to"))} for w in seed.WORKFLOWS for i, st in enumerate(w["steps"])])
    studio = pd.DataFrame([{"snapshot": s, "module": c["module"], "name": c["title"], "model": seed.model_display(c["model"]),
                            "tools": ",".join(c["tools"]), "kill_switch": int(c["kill_switch"]), "read_only": int(c["read_only"])}
                           for c in seed.studio()])
    runs = pd.DataFrame([{"snapshot": s, "run_id": r["run_id"], "at": r["at"], "module": r["module"], "user": r["user"],
                          "question": r["question"], "outcome": r["outcome"], "latency_ms": int(r["latency_ms"]),
                          "tokens_in": int(r["tokens_in"]), "tokens_out": int(r["tokens_out"]), "cost_usd": float(r["cost_usd"]),
                          "figures_validated": int(r["figures_validated"]), "figures_removed": int(r["figures_removed"])}
                         for r in seed.ai_runs()])
    return {"admin_users": users, "admin_roles": roles, "admin_teams": teams, "admin_policies": pols,
            "admin_policy_scope": scope, "admin_workflow_steps": steps, "admin_studio": studio, "admin_ai_runs": runs}


KEYS = {"admin_users": ["username"], "admin_roles": ["role_id"], "admin_teams": ["team_id"], "admin_policies": ["policy_id"],
        "admin_policy_scope": ["policy_id", "book", "field", "value"], "admin_workflow_steps": ["workflow_id", "step_no"],
        "admin_studio": ["module"], "admin_ai_runs": ["run_id"]}


def _digest(df: pd.DataFrame) -> str:
    return hashlib.sha256(df.to_csv(index=False).encode()).hexdigest()


def manifest(fr: dict[str, pd.DataFrame]) -> dict:
    return {"release_id": RELEASE, "domain_label": "Admin", "origin": "SYNTHETIC_DEMO",
            "not_client_data": "Synthetic demonstration configuration generated by CreditProbe v5 (backend/admin/seed.py).",
            "builder": "backend/admin/build.py", "snapshot": SNAPSHOT,
            "keyed_to": {"core_users": "username", "branches": {"release": "branch-saudi-v1", "keys": ["rm_id", "branch_id"]}},
            "dictionary": DICTIONARY,
            "relations": {k: {"file": f"{k}.parquet", "rows": len(v), "columns": list(v.columns), "keys": KEYS[k],
                              "sha256_csv": _digest(v)} for k, v in fr.items()}}


def build() -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    fr = frames()
    for k, v in fr.items():
        v.to_parquet(OUT / f"{k}.parquet", index=False)
    (OUT / "manifest.json").write_text(json.dumps(manifest(fr), indent=1, ensure_ascii=False) + "\n")
    return OUT


def check() -> int:
    fr = frames()
    m = json.loads((OUT / "manifest.json").read_text())
    bad = [k for k, v in fr.items() if m["relations"].get(k, {}).get("sha256_csv") != _digest(v)
           or _digest(pd.read_parquet(OUT / f"{k}.parquet")) != _digest(v)]
    print("ADMIN DOMAIN " + ("OK" if not bad else f"DIFFERS: {bad}"))
    return 1 if bad else 0


if __name__ == "__main__":
    if "--check" in sys.argv:
        raise SystemExit(check())
    print(f"Admin domain written: {build()}")
