"""Integration points of the paper workspace for the rounds built beside it (documented in docs/v5/ROUND_WT.md).

Round K (analysts' rules): register a rule provider. Each provider is called with the document's context and returns the rules
that apply to it; the provenance view lists them per section ("Rules applied") and the Word annex prints them.

    from backend.dealdesk.paperws import hooks
    hooks.RULE_PROVIDERS.append(lambda ctx: [{"rule_id": "R-12", "text": "Lead the synopsis with DSCR", "author": "anne",
                                              "at": "2026-10-24T09:00:00Z", "scope": "me", "section": "synopsis"}])
    # ctx = {"kind": "proposal" | "request", "proposal_id": str, "ws_id": str, "owner": str, "sections": [keys]}
    # a rule with no "section" applies to the whole paper

Round K also listens to every applied instruction (server side; the UI hook is onInstructionApplied in
frontend/src/components/v5/dealdesk/paperws/hooks.ts):

    hooks.INSTRUCTION_LISTENERS.append(lambda ev: ...)
    # ev = {"ws_id", "kind", "proposal_id", "section", "heading", "instruction", "author", "version", "at"}

Round A (agentic intake): open a workspace on a paper it wrote (the section/blocks model) with
POST /paper-workspaces {"kind": "request", "paper": {...}}, or register a named source:

    hooks.PAPER_SOURCES["agent_draft"] = lambda ref: load_the_agent_draft(ref)   # -> paper dict
    # then POST /paper-workspaces {"kind": "request", "source": "agent_draft", "ref": "<id>"}

A provider or listener that raises is skipped (a rule store problem never breaks the document).
"""
from __future__ import annotations

from typing import Any, Callable

RULE_PROVIDERS: list[Callable[[dict[str, Any]], list[dict[str, Any]]]] = []
INSTRUCTION_LISTENERS: list[Callable[[dict[str, Any]], None]] = []
PAPER_SOURCES: dict[str, Callable[[str], dict[str, Any]]] = {}


def rules(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for fn in list(RULE_PROVIDERS):
        try:
            for r in fn(ctx) or []:
                if isinstance(r, dict) and r.get("text"):
                    out.append({"rule_id": str(r.get("rule_id") or r.get("id") or ""), "text": str(r["text"]), "author": str(r.get("author") or ""),
                                "at": str(r.get("at") or r.get("created_at") or ""), "scope": str(r.get("scope") or ""),
                                "section": str(r.get("section") or "")})
        except Exception:  # noqa: BLE001
            continue
    return out


def instruction_applied(ev: dict[str, Any]) -> None:
    for fn in list(INSTRUCTION_LISTENERS):
        try:
            fn(ev)
        except Exception:  # noqa: BLE001
            continue
