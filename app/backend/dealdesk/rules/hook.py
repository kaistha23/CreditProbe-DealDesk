"""The seams the drafting paths call. Each is one line at the call site:

    house-style credit proposal   service.create_draft / regenerate:  d = hook.on_house_draft(d, by)
                                  draft._model (the prompt):          "analyst_rules": hook.model_rules(section_key)
    the RM's credit request       rm_request.api.write_request:       p = hook.on_paper(p, user, "request")
    the bank-form credit proposal papers_api._paper:                  p = hook.on_paper(p, user, "proposal")

and Round W's living document calls `apply_to(doc, username, document)` after each instruction it applies, and mounts the
"Save this as a rule?" prompt (frontend `components/v5/rules/save-rule-prompt.tsx`) on its onInstructionApplied hook.
"""
from __future__ import annotations

import contextlib
import contextvars
from typing import Any, Iterator

from backend.dealdesk.rules import apply as AP
from backend.dealdesk.rules import store

_ACTIVE: contextvars.ContextVar[list[dict[str, Any]] | None] = contextvars.ContextVar("dealdesk_rules_active", default=None)


def username(request: Any) -> str:
    """The signed-in user's username (empty without the Core service)."""
    if request is None:
        return ""
    try:
        from backend.identity_v5.client import current_user
        return (current_user(request) or {}).get("username", "") or ""
    except Exception:  # noqa: BLE001
        return ""


def rules_for(user: str, document: str) -> list[dict[str, Any]]:
    try:
        return store.for_document(user, document)
    except Exception:  # noqa: BLE001 - a broken rules store never stops a document
        return []


@contextlib.contextmanager
def drafting(user: str, document: str = "proposal") -> Iterator[list[dict[str, Any]]]:
    """While a document is drafted, the model path reads the writer's rules (model_rules)."""
    rules = rules_for(user, document)
    token = _ACTIVE.set(rules)
    try:
        yield rules
    finally:
        _ACTIVE.reset(token)


def model_rules(section: str = "") -> list[str]:
    """The rules as instructions for the model writing `section` (empty outside a drafting block)."""
    rules = _ACTIVE.get()
    return AP.instructions(rules, section) if rules else []


def apply_to(doc: dict[str, Any], user: str, document: str, model_used: bool = False,
             rules: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    rules = rules_for(user, document) if rules is None else rules
    out, applied = AP.apply(doc, rules, model_used=model_used)
    out["rules_applied"] = applied
    out["rules_summary"] = AP.summary(applied)
    out["rules_for"] = {"username": user, "name": store.person(user)["name"] if user else "", "document": document}
    return out


def on_house_draft(d: dict[str, Any], user: str) -> dict[str, Any]:
    try:
        return apply_to(d, user, "proposal", model_used="model" in (d.get("methods") or []))
    except Exception:  # noqa: BLE001
        return d


def on_paper(p: dict[str, Any], user: str, document: str) -> dict[str, Any]:
    try:
        return apply_to(p, user, document)
    except Exception:  # noqa: BLE001
        return p


# ------------------------------------------------------------------ Round W/T's paper workspace (docs/v5/ROUND_WT.md)

def rule_provider(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    """paperws.hooks.RULE_PROVIDERS: the rules in force for the workspace's owner on this document ("Rules applied",
    provenance, the Word annex). ctx = {"kind", "proposal_id", "ws_id", "owner", "sections"}."""
    doc = "request" if ctx.get("kind") == "request" else "proposal"
    return [{"rule_id": r["id"], "text": r["text"], "author": r["author_name"] or r["author"], "at": r["created_at"], "scope": r["scope"],
             "section": r.get("section") or ""} for r in rules_for(str(ctx.get("owner") or ""), doc)]


def register_with_paper_workspace() -> bool:
    """Plug the rules into Round W's workspace when it is present (after the merge); a no-op before."""
    try:
        from backend.dealdesk.paperws import hooks as pw  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001 - Round W not merged yet
        return False
    if rule_provider not in pw.RULE_PROVIDERS:
        pw.RULE_PROVIDERS.append(rule_provider)
    return True
