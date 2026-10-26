"""Seeded Admin content (PLAN_R5 A7): 6 roles, 12 users across 7 teams, 4 data access policies, 5 approval
workflows, studio configurations for every module, settings, 40 AI runs and a few changes waiting for a checker.

Users are the Core directory's 12 sign-ins (`backend.identity_v5.directory`), keyed by username (sync test:
tests/v5/test_sync_admin.py). RMs carry their RM ID and base branch from the Branches and RMs domain.
"""
from __future__ import annotations

import random
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.v5common.edition import is_dealdesk

SEED_VERSION_FULL = "admin-seed-1"
SEED_VERSION_DEALDESK = "admin-seed-1-dd"
#: Deal Desk edition: the modules in the product (backend.access.policy.MODULES keys). Policies, roles, the studio
#: and the seeded runs are narrowed to these; the full product's seed is unchanged under V5_EDITION=full.
DEALDESK_MODULES = ("cockpit", "deal_desk", "playbook", "policy_docs", "projects", "mail", "data_builder", "admin")


def seed_version() -> str:
    return SEED_VERSION_DEALDESK if is_dealdesk() else SEED_VERSION_FULL


def _mods(mods: list[str]) -> list[str]:
    """A module list as the edition allows it ("*" stays "*")."""
    if not is_dealdesk() or mods == ["*"]:
        return list(mods)
    return [m for m in mods if m in DEALDESK_MODULES]
AS_OF = datetime(2026, 10, 11, 18, 0, tzinfo=timezone.utc)


def _t(days: float = 0, hours: float = 0) -> str:
    return (AS_OF - timedelta(days=days, hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")


ALL_ACTIONS = {"export": True, "send": True, "approve": True, "run_model": True}

def _roles() -> list[dict[str, Any]]:
    return [
        {"id": "admin", "name": "Admin", "description": "Runs CreditProbe: access policies, workflows, users, AI configuration and settings.",
         "modules": ["*"], "permissions": ["configure", "approve_changes", "view_audit"]},
        {"id": "cro", "name": "CRO", "description": "Senior credit and risk officers: see both books, approve credit, scenarios and parameter changes.",
         "modules": ["*"], "permissions": ["approve_credit", "approve_changes", "view_audit"]},
        {"id": "analyst", "name": "Credit Risk Analyst", "description": "Analyses the books, runs scenarios, drafts reports and credit proposals.",
         "modules": ["*"], "permissions": ["draft"]},
        {"id": "rm", "name": "RM", "description": ("Relationship managers: their own portfolio, their deals and proposals." if is_dealdesk() else
                                                    "Relationship managers: their own portfolio, Early Warning actions and proposals."),
         "modules": _mods(["cockpit", "early_warning", "borrower_360", "deal_desk", "projects", "mail", "playbook"]), "permissions": ["draft"]},
        {"id": "auditor", "name": "Auditor", "description": "Internal audit: reads everything, changes nothing; obligor names masked.",
         "modules": ["*"], "permissions": ["view_audit"]},
        {"id": "validator", "name": "Model Validator", "description": ("Independent model validation: Deal Desk's models and parameter changes." if is_dealdesk() else
                                                                       "Independent model validation: scorecards, What-If models, parameter changes."),
         "modules": ["*"], "permissions": ["draft", "approve_models"]},
    ]

TEAMS: list[dict[str, Any]] = [
    {"id": "T-ADM", "name": "Administration", "core_team": "admin", "lead": "anne", "description": "CreditProbe administration."},
    {"id": "T-CRM", "name": "Credit Risk Management", "core_team": "risk", "lead": "faisal.alqahtani",
     "description": "Head of Risk, Head of Credit and portfolio risk."},
    {"id": "T-CORP", "name": "Corporate Credit", "core_team": "corporate", "lead": "khalid.alotaibi",
     "description": "Corporate credit managers and analysts."},
    {"id": "T-RET", "name": "Retail Credit", "core_team": "retail", "lead": "reem.alshehri", "description": "Retail credit."},
    {"id": "T-MV", "name": "Model Validation", "core_team": "validation", "lead": "lama.almutairi",
     "description": "Independent validation of scorecards and IFRS 9 models."},
    {"id": "T-RMC", "name": "Corporate Banking Central (Riyadh RMs)", "core_team": "corporate", "lead": "nawaf.alotaibi",
     "description": "Relationship managers based at BR-RUH-01 Riyadh Olaya.", "branch_id": "BR-RUH-01", "business_unit": "Corporate Banking Central"},
    {"id": "T-IA", "name": "Internal Audit", "core_team": "audit", "lead": "hind.alsubaie", "description": "Third line of defence."},
]

# username -> (admin role, team, rm_id, branch_id, last activity days ago)
_PROFILE = {
    "anne": ("admin", "T-ADM", "", "", 0.01),
    "faisal.alqahtani": ("cro", "T-CRM", "", "", 0.2),
    "noura.alharbi": ("cro", "T-CRM", "", "", 0.4),
    "khalid.alotaibi": ("analyst", "T-CORP", "", "", 0.6),
    "reem.alshehri": ("analyst", "T-RET", "", "", 1.2),
    "abdullah.alzahrani": ("analyst", "T-CRM", "", "", 0.9),
    "sara.aldosari": ("analyst", "T-CORP", "", "", 0.3),
    "omar.alghamdi": ("analyst", "T-RET", "", "", 2.5),
    "lama.almutairi": ("validator", "T-MV", "", "", 1.1),
    "nawaf.alotaibi": ("rm", "T-RMC", "RM0005", "BR-RUH-01", 0.7),
    "abeer.alomari": ("rm", "T-RMC", "RM0011", "BR-RUH-01", 3.0),
    "hind.alsubaie": ("auditor", "T-IA", "", "", 5.0),
}


def users() -> list[dict[str, Any]]:
    from backend.identity_v5 import directory

    out = []
    for u in directory.seed_users():
        role, team, rm, branch, days = _PROFILE[u["username"]]
        out.append({"id": u["username"], "username": u["username"], "name": u["name"], "title": u["title"],
                    "department": u["department"], "core_team": u["team"], "books": u["books"], "role": role,
                    "team": team, "rm_id": rm, "branch_id": branch, "status": "active", "last_activity": _t(days),
                    "delegate": "noura.alharbi" if u["username"] == "faisal.alqahtani" else ""})
    return out


def _policies() -> list[dict[str, Any]]:
    return [
        {"id": "POL-RM-OWN", "name": "Riyadh RMs see only their portfolio", "status": "active",
         "description": "Relationship managers at Riyadh Olaya see the corporate borrowers they manage, nothing else. "
                        "They can export their own portfolio and send it; they do not approve or run models.",
         "books": ["corporate"], "scope": {"corporate": {"rm_ids": ["own"]}},
         "modules": _mods(["cockpit", "early_warning", "borrower_360", "deal_desk", "projects", "mail", "playbook"]),
         "actions": {"export": True, "send": True, "approve": False, "run_model": False},
         "mask": {"obligor_name": False, "obligor_id": False},
         "assignees": {"users": [], "roles": [], "teams": ["T-RMC"]}},
        {"id": "POL-AUDIT", "name": "Auditor read-only, names masked", "status": "active",
         "description": "Internal Audit reads both books and every module except Admin configuration, with obligor names "
                        "masked. No export, sending, approval or model run.",
         "books": ["corporate", "retail"], "scope": {},
         "modules": _mods(["cockpit", "early_warning", "borrower_360", "what_if", "scorecard", "deal_desk", "lenses",
                           "playbook", "policy_docs", "projects", "mail", "data_builder"]),
         "actions": {"export": False, "send": False, "approve": False, "run_model": False},
         "mask": {"obligor_name": True, "obligor_id": False},
         "assignees": {"users": [], "roles": ["auditor"], "teams": []}},
        {"id": "POL-RETAIL", "name": "Retail Credit sees the retail book", "status": "active",
         "description": "Retail credit managers and analysts work on the retail book only.",
         "books": ["retail"], "scope": {}, "modules": ["*"], "actions": dict(ALL_ACTIONS),
         "mask": {"obligor_name": False, "obligor_id": False},
         "assignees": {"users": [], "roles": [], "teams": ["T-RET"]}},
        {"id": "POL-CORP", "name": "Corporate Credit sees the corporate book", "status": "active",
         "description": "Corporate credit managers and analysts work on the corporate book; Admin is not included.",
         "books": ["corporate"], "scope": {},
         "modules": _mods(["cockpit", "early_warning", "borrower_360", "what_if", "scorecard", "deal_desk", "lenses", "playbook",
                           "policy_docs", "projects", "mail", "data_builder"]),
         "actions": dict(ALL_ACTIONS), "mask": {"obligor_name": False, "obligor_id": False},
         "assignees": {"users": [], "roles": [], "teams": ["T-CORP"]}},
    ]


def _step(sid, name, kind, assignee, sla, esc_after=None, esc_to=None, condition=None, delegation=True, note=""):
    return {"id": sid, "name": name, "kind": kind, "assignee": assignee, "sla_days": sla,
            "escalate_after_days": esc_after, "escalate_to": esc_to, "condition": condition or [],
            "delegation": delegation, "note": note}


def _full_workflows() -> list[dict[str, Any]]:
    return [
        {"id": "WF-DD-DOA", "name": "Deal Desk approval by DOA", "status": "active", "object_type": "deal_proposal",
         "description": "A credit proposal is reviewed by Credit and approved at the Delegation of Authority level its "
                        "exposure after the deal, rating and soft breaches require (Deal Desk DOA table v1).",
         "trigger": {"event": "proposal_submitted", "conditions": []},
         "steps": [
             _step("s1", "RM submits the proposal", "action", {"type": "rm_of_object"}, 1),
             _step("s2", "Credit analysis", "review", {"type": "role", "value": "analyst"}, 2, 4, {"type": "user", "value": "khalid.alotaibi"}),
             _step("s3", "Approval at the DOA level", "approve", {"type": "doa_level"}, 3, 5, {"type": "doa_next"},
                   note="Corporate Credit Manager up to SAR 25 m; Head of Credit 100 m; CRO 175 m; Executive Credit Committee 250 m; Board above."),
             _step("s4", "Notify the RM and Deal Desk", "notify", {"type": "rm_of_object"}, 0)]},
        {"id": "WF-PB-SIGN", "name": "Playbook report review and sign-off", "status": "active", "object_type": "playbook_report",
         "description": "A committee pack or portfolio review goes from its author to a reviewer, then to the Head of Risk for sign-off.",
         "trigger": {"event": "report_submitted", "conditions": []},
         "steps": [
             _step("s1", "Author submits for review", "action", {"type": "owner_of_object"}, 1),
             _step("s2", "Reviewer comments", "review", {"type": "user", "value": "noura.alharbi"}, 3, 5, {"type": "user", "value": "faisal.alqahtani"}),
             _step("s3", "Sign-off", "approve", {"type": "user", "value": "faisal.alqahtani"}, 2, 4, {"type": "role", "value": "admin"})]},
        {"id": "WF-WI-OFFICIAL", "name": "What-If scenario approval for official use", "status": "active", "object_type": "whatif_scenario",
         "description": "A scenario used for ICAAP, budget or committee figures is validated by Model Validation and approved by the CRO.",
         "trigger": {"event": "scenario_marked_official", "conditions": []},
         "steps": [
             _step("s1", "Analyst documents the scenario", "action", {"type": "owner_of_object"}, 2),
             _step("s2", "Model Validation review", "review", {"type": "role", "value": "validator"}, 5, 7, {"type": "user", "value": "faisal.alqahtani"}),
             _step("s3", "CRO approval", "approve", {"type": "user", "value": "faisal.alqahtani"}, 3, 5, {"type": "role", "value": "admin"})]},
        {"id": "WF-EWS-CRIT", "name": "Critical Early Warning names: RM action plan", "status": "active", "object_type": "ews_name",
         "description": "Every borrower banded Critical by Early Warning needs an RM action plan within 5 days; after 10 days "
                        "without one it escalates to the Head of Credit, who decides on the watchlist.",
         "trigger": {"event": "ews_band_changed", "conditions": [{"field": "band", "op": "=", "value": "critical"}]},
         "steps": [
             _step("s1", "RM action plan", "action", {"type": "rm_of_object"}, 5, 10, {"type": "user", "value": "noura.alharbi"}),
             _step("s2", "Watchlist decision", "approve", {"type": "user", "value": "noura.alharbi"}, 3, 5, {"type": "user", "value": "faisal.alqahtani"}),
             _step("s3", "Notify Credit Risk Management", "notify", {"type": "team", "value": "T-CRM"}, 0)]},
        {"id": "WF-PARAM", "name": "Parameter-table change", "status": "active", "object_type": "parameter_table",
         "description": "A change to an owned parameter table (Deal Desk, Early Warning rule set, What-If, Scorecard) is "
                        "proposed by its owner, reviewed by Model Validation and approved by the CRO before it goes live.",
         "trigger": {"event": "parameter_change_drafted", "conditions": []},
         "steps": [
             _step("s1", "Owner proposes the change", "action", {"type": "owner_of_object"}, 1),
             _step("s2", "Model Validation review", "review", {"type": "role", "value": "validator"}, 5, 8, {"type": "user", "value": "faisal.alqahtani"}),
             _step("s3", "CRO approval", "approve", {"type": "user", "value": "faisal.alqahtani"}, 3, 5, {"type": "role", "value": "admin"},
                   condition=[{"field": "materiality", "op": "in", "value": ["medium", "high"]}]),
             _step("s4", "Publish the new version", "notify", {"type": "role", "value": "admin"}, 1)]},
    ]

def _workflows() -> list[dict[str, Any]]:
    """The edition's workflows: the Deal Desk edition has no What-If scenario or Early Warning workflow."""
    wfs = _full_workflows()
    if not is_dealdesk():
        return wfs
    wfs = [w for w in wfs if w["object_type"] not in ("whatif_scenario", "ews_name")]
    for w in wfs:
        if w["id"] == "WF-PARAM":
            w["description"] = ("A change to an owned parameter table (Deal Desk's pricing, DOA, LGD, FTP and PD tables) is proposed by "
                                "its owner, reviewed by Model Validation and approved by the CRO before it goes live.")
    return wfs


_FULL_STUDIO_MODULES = [
    ("cockpit", "Cockpit", True), ("what_if", "What-If", False), ("playbook", "Playbook", False),
    ("deal_desk", "Deal Desk", False), ("lenses", "Lenses", False), ("scorecard", "Scorecard Validation", False),
    ("projects", "Projects", False),
]


def _studio_modules() -> list[tuple[str, str, bool]]:
    return [m for m in _FULL_STUDIO_MODULES if m[0] in DEALDESK_MODULES] if is_dealdesk() else list(_FULL_STUDIO_MODULES)
_TOOLS = {   # each module's own assistant tools (the builtins run_query, read_knowledge, finalize_answer are always on)
    "cockpit": ["run_query", "read_policy", "attention_items", "open_borrower"],
    "what_if": ["scenario_ideas", "propose_scenario", "collateral_mechanics", "last_result", "assess_likelihood", "model_card"],
    "playbook": ["section_outline", "read_report", "restructure_report"],
    "deal_desk": ["get_proposal", "compute_terms", "optimise", "stress", "headroom", "explain_constraint", "compare", "breakeven"],
    "lenses": ["build_lens", "edit_lens", "explain_tile", "suggest_tiles", "tile_to_thread"],
    "scorecard": ["diagnose", "segment_gini", "variable_psi", "override_analysis", "calibration_by_grade"],
    "projects": ["search_documents"],
}
def _glossary() -> list[dict[str, Any]]:
    return [
        {"term": "SICR", "meaning": "Significant increase in credit risk: the IFRS 9 trigger from Stage 1 to Stage 2."},
        {"term": "DOA", "meaning": "Delegation of Authority: who may approve a credit at a given exposure and rating."},
        {"term": "RAROC", "meaning": "Risk-adjusted return on capital: risk-adjusted profit over economic capital."},
        {"term": "SIMAH", "meaning": "The Saudi credit bureau."},
        {"term": "Watchlist", "meaning": ("Borrowers under closer monitoring after a credit decision." if is_dealdesk() else
                                          "Borrowers under closer monitoring after an Early Warning decision.")},
    ]


#: PLAN_R6 B6: the UI never shows a vendor model name. Display name -> real model ID; the first is the main model.
#: Held in the Admin config (Settings, "LLM model names"); frontend/src/lib/v5/model-names.ts mirrors it.
MODEL_NAMES: dict[str, str] = {"LLM model 1.1": "claude-opus-5", "LLM model 1.2": "claude-sonnet-5"}


def model_display(model_id: str | None, mapping: dict[str, str] | None = None) -> str:
    """The display name of a model ID ("LLM model 1.1"/"1.2"); an unknown vendor ID maps by family, and text with
    no vendor name (e.g. "planner (kill switch on)") is returned unchanged."""
    raw = str(model_id or "").strip()
    if not raw:
        return ""
    for disp, mid in (mapping or MODEL_NAMES).items():
        if raw.lower() in (str(mid).lower(), disp.lower()):
            return disp
    low = raw.lower()
    names = list(MODEL_NAMES)
    if "opus" in low:
        return names[0]
    if "sonnet" in low:
        return names[1]
    if re.search(r"claude|anthropic|haiku|gpt|openai|gemini|llama", low):
        return "LLM model"
    return raw


def studio() -> list[dict[str, Any]]:
    out = []
    for key, title, frozen in _studio_modules():
        out.append({
            "id": key, "module": key, "title": title, "read_only": frozen,
            "model": "claude-opus-5",
            "instructions": (f"You are the {title} assistant of a Saudi bank's credit risk function. Answer from the "
                             f"{title} data only, every figure from a query of this turn. Be direct and precise, "
                             "in the bank's house tone: short sentences, SAR millions, no speculation."),
            "tone": "Professional and concise; lead with the answer, then the evidence.",
            "glossary": _glossary(),
            "knowledge": ["Credit Policy CP-2026 (active pack)", "SAMA circular C-2026-03"] + (
                ["Deal Desk method (DEALDESK_METHOD)"] if key == "deal_desk" else []),
            "tools": list(_TOOLS[key]), "known_tools": list(_TOOLS[key]),
            "guardrails": {"no_untraced_figure": True, "scope_refusal": True, "max_steps": 8,
                           "refuse_outside_domain": True},
            "answer_style": {"length": "medium", "tables": True, "charts": key != "projects"},
            "kill_switch": False,
        })
    return out


SETTINGS: list[dict[str, Any]] = [
    {"id": "bank_profile", "name": "Bank profile", "body": {
        "bank_name": "Riyadh Commercial Bank", "short_name": "RCB", "reporting_currency": "SAR",
        "amount_unit": "SAR million", "fiscal_year_start": "01-01", "calendar": "Gregorian",
        "as_of": {"corporate": "2026Q2", "retail": "2026-08", "common": "2026Q2 (June 2026)"}, "logo": "monogram"}},
    {"id": "house_style", "name": "House style for exports", "body": {
        "primary": "#1F3A5F", "accent": "#B08D57", "font": "Calibri", "header_block": True, "about_sheet": True,
        "word_cover_page": True, "page_numbers": True, "number_formats": {"amount": "SAR m, 1 decimal", "percent": "1 decimal",
                                                                             "bps": "integer", "ratio": "2 decimals"}}},
    {"id": "notifications", "name": "Notifications and mail", "body": {
        "workflow_assignments": "mail_and_workspace", "sla_reminder_hours_before": 24, "escalation_mail": True,
        "daily_digest": "07:30", "sender": "CreditProbe <creditprobe@rcb.local>"}},
    {"id": "model_names", "name": "LLM model names", "body": dict(MODEL_NAMES)},
    {"id": "retention", "name": "Retention", "body": {
        "audit_log_years": 7, "ai_run_logs_days": 400, "threads_days": 730, "exports_days": 90, "drafts_days": 30}},
]

#: Changes waiting for a checker (made by others, so the Administrator can approve them).
def _full_pending() -> list[dict[str, Any]]:
    return [
        {"kind": "policy", "op": "create", "maker": "noura.alharbi", "title": "Makkah desk: Makkah region only",
         "body": {"id": "POL-MAKKAH", "name": "Makkah desk sees the Makkah region", "status": "active",
                  "description": "The Makkah regional credit desk sees Makkah borrowers and customers in both books.",
                  "books": ["corporate", "retail"], "scope": {"corporate": {"regions": ["Makkah"]}, "retail": {"regions": ["Makkah"]}},
                  "modules": ["*"], "actions": dict(ALL_ACTIONS), "mask": {"obligor_name": False, "obligor_id": False},
                  "assignees": {"users": [], "roles": [], "teams": []}}},
        {"kind": "workflow", "op": "update", "maker": "faisal.alqahtani", "title": "EWS critical names: escalate after 8 days",
         "object_id": "WF-EWS-CRIT", "patch": {"steps.0.escalate_after_days": 8}},
    ]


def _pending() -> list[dict[str, Any]]:
    out = _full_pending()
    if is_dealdesk():   # the pending change in the edition is to the DOA workflow
        out[1] = {"kind": "workflow", "op": "update", "maker": "faisal.alqahtani", "title": "DOA approval: escalate after 4 days",
                  "object_id": "WF-DD-DOA", "patch": {"steps.2.escalate_after_days": 4}}
    return out

# ------------------------------------------------------------------ AI runs
_FULL_QUESTIONS = {
    "cockpit": ["Why did Construction ECL rise this quarter?", "Top 10 Stage 2 borrowers by EAD", "Show retail Stage 2 build by product",
                "What is our largest single-name concentration?", "Which sectors breach the appetite limit?"],
    "what_if": ["Oil price -40% with a two-notch downgrade for Petrochemicals", "Increase PD by 15% with staging effect",
                "What is a decent collateral haircut for Real Estate?", "Run the severe macro scenario on retail"],
    "playbook": ["Draft the executive summary of the Q2 credit committee pack", "Add the Construction ECL table to section 3",
                 "Summarise the Real Estate concentration for the board"],
    "deal_desk": ["Optimise DD-02 to clear the hurdle", "What approval level does DD-01 need?", "Price a SAR 120 m 5-year term loan for CB00398"],
    "lenses": ["Construction sector dashboard", "Makkah retail cards", "Stage 2 migration by RM"],
    "scorecard": ["What is wrong with my scorecard?", "PSI for the debt-burden variable", "Validate the SME scorecard"],
    "projects": ["Give me 5 high-alert Early Warning clients in Stage 1", "Summarise the project documents"],
}
_DEALDESK_QUESTIONS = {
    "cockpit": ["Which proposals breach a hard limit?", "What is going to committee this month?", "Which conditions are overdue?",
                "Where is the real-estate appetite against its limit?", "Which deals are waiting on Credit's queries?"],
    "playbook": ["Draft the executive summary of DD-06's committee paper", "Add the counter-offer table to section 3",
                 "Summarise the Real Estate concentration for the committee"],
    "deal_desk": ["Optimise DD-02 to clear the hurdle", "What approval level does DD-01 need?", "Price a SAR 120 m 5-year term loan for CB00398",
                  "How much real-estate headroom is left?", "Stress DD-06 at a 20% collateral haircut"],
    "projects": ["Summarise the DD-06 pack", "Which documents in this deal mention the guarantor?"],
}


def _questions() -> dict[str, list[str]]:
    return _DEALDESK_QUESTIONS if is_dealdesk() else _FULL_QUESTIONS
_USERS = ["anne", "faisal.alqahtani", "noura.alharbi", "khalid.alotaibi", "sara.aldosari", "abdullah.alzahrani",
          "reem.alshehri", "omar.alghamdi", "lama.almutairi", "nawaf.alotaibi"]
STAGES = ["understanding", "planning", "querying", "answering", "validating", "publishing"]


def ai_runs(n: int = 40) -> list[dict[str, Any]]:
    rng = random.Random(20261011)
    qs = _questions()
    mods = list(qs)
    out = []
    for i in range(n):
        m = mods[i % len(mods)] if i < 28 else rng.choice(mods)
        q = qs[m][(i // len(mods)) % len(qs[m])]
        model = "claude-opus-5" if m in ("cockpit", "what_if", "deal_desk", "playbook") else "claude-sonnet-5"
        outcome = "completed"
        if i in (7, 19, 31):
            outcome = "refused"
        elif i in (12, 26):
            outcome = "failed"
        ms = [rng.randint(300, 900), rng.randint(500, 2500), rng.randint(400, 3500), rng.randint(2000, 9000),
              rng.randint(200, 1200), rng.randint(80, 300)]
        if outcome != "completed":
            ms = ms[:3] + [0, 0, 0]
        steps, at = [], 0
        for s, d in zip(STAGES, ms):
            if d:
                steps.append({"stage": s, "at_ms": at, "ms": d})
                at += d
        tin, tout = rng.randint(6000, 24000), rng.randint(500, 2500)
        price = (15, 75) if "opus" in model else (3, 15)
        tools = ["inspect_catalog", "run_query"] + rng.sample(_TOOLS[m][1:], k=min(2, len(_TOOLS[m]) - 1)) + ["finalize_answer"]
        figures = rng.randint(4, 18) if outcome == "completed" else 0
        out.append({
            "run_id": f"AR-S{i + 1:03d}", "at": _t(days=(n - i) * 0.17, hours=rng.random()), "module": m, "domain": m,
            "user": _USERS[i % len(_USERS)], "question": q, "mode": "ask", "steps": steps, "tools": tools if outcome == "completed" else tools[:2],
            "source": "model", "model": model, "model_display": model_display(model), "latency_ms": at, "outcome": outcome,
            "tokens_in": tin, "tokens_out": tout, "cost_usd": round((tin * price[0] + tout * price[1]) / 1e6, 4),
            "figures_validated": figures, "figures_removed": 1 if i in (4, 22) else 0,
            "refusal_reason": ("Outside the module's data: the question asks for another bank's figures." if outcome == "refused" else
                               "The model call timed out after 3 retries; the planner answered instead." if outcome == "failed" else ""),
            "seeded": True})
    return out


#: Scripted evaluation questions per module, with the tools a correct trace calls.
def _evals() -> dict[str, list[dict[str, Any]]]:
    out = dict(_FULL_EVALS)
    if is_dealdesk():
        out = {k: v for k, v in out.items() if k in DEALDESK_MODULES}
        out["admin"] = [dict(e) for e in out.get("admin", [])]
        out["admin"][0]["q"] = ("Create a workflow so proposals above SAR 100 m need the CRO's approval within 5 days, "
                                "escalate to the Executive Credit Committee after 10")
    return out


_FULL_EVALS: dict[str, list[dict[str, Any]]] = {
    "what_if": [
        {"q": "Propose a scenario: increase PD by 15% with stage implication", "expect_tools": ["propose_scenario"]},
        {"q": "How did you equate a collateral reduction with an LGD increase? Explain the collateral mechanics", "expect_tools": ["collateral_mechanics"]},
        {"q": "What is the average increment in PDs between quarters?", "expect_tools": ["inspect_catalog"]},
    ],
    "scorecard": [
        {"q": "What is wrong with my scorecard? Diagnose it", "expect_tools": ["diagnose"]},
        {"q": "PSI for one variable", "expect_tools": ["variable_psi"]},
    ],
    "deal_desk": [
        {"q": "Compute the terms of DD-01", "expect_tools": ["compute_terms"]},
        {"q": "Optimise DD-02", "expect_tools": ["optimise"]},
    ],
    "admin": [
        {"q": "Create a workflow so Critical Early Warning names need an RM action plan within 5 days, escalate to the Head of Credit after 10",
         "expect_tools": ["draft_workflow"]},
        {"q": "What can nawaf.alotaibi see?", "expect_tools": ["preview_access"]},
        {"q": "What is Agent Operations?", "expect_tools": ["read_knowledge"]},
        {"q": "Riyadh RMs should only see their own portfolio, without exports", "expect_tools": ["draft_policy"]},
    ],
}


#: The edition's view of the seed, resolved on every access (`seed.ROLES`, `seed.WORKFLOWS`, …), so the edition switch
#: (V5_EDITION, read at call time) works whenever the store seeds, including in tests that pin an edition after import.
_LAZY = {"ROLES": _roles, "POLICIES": _policies, "WORKFLOWS": _workflows, "STUDIO_MODULES": _studio_modules,
         "GLOSSARY": _glossary, "PENDING": _pending, "EVALS": _evals, "SEED_VERSION": seed_version, "_QUESTIONS": _questions}


def __getattr__(name: str) -> Any:
    if name in _LAZY:
        return _LAZY[name]()
    raise AttributeError(name)
