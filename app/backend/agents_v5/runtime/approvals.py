"""The approvals bridge (A4): an agent proposes; a person decides; only then is it applied.

Reuses `backend.agentic.approvals` semantics: the record exists before the action, the
approver role comes from the agent definition (never the proposer), one decision only
(`AlreadyDecided`), and `NotAuthorised` for a role below the gate. Added here:
- **maker-checker**: the person who started the run cannot approve its proposals;
- **expiry**: a pending proposal past `expires_at` is EXPIRED and can no longer be approved;
- credit roles (RM, CREDIT_OFFICER, CCO) ranked next to the agentic roles;
- **appliers**: the owning module registers `register_applier(kind, fn)`; approval calls it.
  With no applier the decision is recorded and nothing changes.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from backend.agentic import approvals as AG
from backend.agents_v5.runtime import notify, store
from backend.agents_v5.runtime.types import new_id, now_iso

TABLE = "approvals"
PENDING, APPROVED, REJECTED, EXPIRED = AG.PENDING, AG.APPROVED, AG.REJECTED, AG.EXPIRED
DECISIONS = (APPROVED, REJECTED)
NotAuthorised = AG.NotAuthorised
AlreadyDecided = AG.AlreadyDecided

#: agentic ranks plus the credit hierarchy (RM < credit officer < CCO); ADMIN sits with CCO.
ROLE_RANK: dict[str, int] = {**AG.ROLE_RANK, "RM": 1, "CREDIT_OFFICER": 2, "RISK_MANAGER": 2, "CCO": 3,
                             "CRO": 3}
#: identity roles (backend.identity_v5) to ranks
IDENTITY_ROLES = {"ADMINISTRATOR": "ADMIN", "USER": "ANALYST"}

_APPLIERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {}


class MakerChecker(PermissionError):
    """The maker of a change tried to check it."""


class Expired(ValueError):
    pass


def norm_role(role: str) -> str:
    r = str(role or "").strip().upper().replace(" ", "_")
    return IDENTITY_ROLES.get(r, r)


def register_applier(kind: str, fn: Callable[[dict[str, Any]], dict[str, Any]]) -> None:
    _APPLIERS[kind] = fn


def _now() -> datetime:
    return datetime.now(UTC)


def propose(change: dict[str, Any], approver_role: str, *, kind: str = "", title: str = "", reason: str = "",
            evidence: list[str] | None = None, agent: str = "", run_id: str = "", maker: str = "",
            scope: str = "", expires_hours: int = 72, risk: str = "medium") -> dict[str, Any]:
    """Queue a proposed change. Returns the pending approval row. Nothing is applied here."""
    role = norm_role(approver_role)
    if role not in ROLE_RANK:
        raise ValueError(f"Unknown approver role {approver_role!r}.")
    pid = new_id("apr")
    row = {"id": pid, "kind": kind or str(change.get("kind") or "change"), "title": (title or kind)[:300],
           "reason": reason, "change": change, "evidence": list(evidence or []), "agent": agent, "run_id": run_id,
           "maker": maker or f"agent:{agent}", "approver_role": role, "scope": scope, "risk": risk,
           "status": PENDING, "created_at": now_iso(),
           "expires_at": (_now() + timedelta(hours=max(1, int(expires_hours)))).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "decided_by": "", "decided_role": "", "decided_at": "", "note": "", "applied": None}
    store.put(TABLE, pid, row)
    notify.send(f"Approval needed: {row['title']}", reason or row["title"], f"/trace/agent/{run_id}" if run_id else "/",
                audience_role=role)
    return row


def _expire(row: dict[str, Any]) -> dict[str, Any]:
    if row.get("status") == PENDING and row.get("expires_at", "9") < now_iso():
        row["status"] = EXPIRED
    return row


def get(pid: str) -> dict[str, Any] | None:
    row = store.table(TABLE).get(pid)
    return _expire(dict(row)) if row else None


def listing(*, agent: str = "", status: str = "", run_id: str = "", scope: str = "") -> list[dict[str, Any]]:
    rows = [_expire(dict(r)) for r in store.table(TABLE).values()]
    rows = [r for r in rows if (not agent or r["agent"] == agent) and (not status or r["status"] == status)
            and (not run_id or r["run_id"] == run_id) and (not scope or r["scope"] == scope)]
    return sorted(rows, key=lambda r: r["created_at"], reverse=True)


def may_decide(role: str, row: dict[str, Any]) -> bool:
    return ROLE_RANK.get(norm_role(role), -1) >= ROLE_RANK.get(row["approver_role"], 99)


def decide(pid: str, *, decision: str, user: str, role: str, note: str = "") -> dict[str, Any]:
    decision = {"approve": APPROVED, "reject": REJECTED}.get(decision, decision)
    if decision not in DECISIONS:
        raise ValueError(f"'{decision}' is not a decision; approve or reject.")
    row = get(pid)
    if row is None:
        raise KeyError(pid)
    if row["status"] == EXPIRED:
        raise Expired(f"This proposal expired at {row['expires_at']}; the agent must propose it again.")
    if row["status"] != PENDING:
        raise AlreadyDecided(f"This proposal was already {row['status']}.")
    if not may_decide(role, row):
        raise NotAuthorised(f"{row['title']} needs {row['approver_role']} approval; "
                            f"{norm_role(role) or 'this role'} cannot decide it.")
    if user and user == row.get("maker"):
        raise MakerChecker("The person who asked for this run cannot approve its proposals (maker-checker).")
    if not user:
        raise NotAuthorised("A decision needs a signed-in person.")

    applied: dict[str, Any] | None = None
    if decision == APPROVED:
        fn = _APPLIERS.get(row["kind"])
        if fn is None:
            applied = {"applied": False, "note": "Recorded. No automatic apply for this kind of change."}
        else:
            t0 = time.monotonic()
            try:
                applied = {"applied": True, "result": fn(row["change"]), "ms": int((time.monotonic() - t0) * 1000)}
            except Exception as e:  # noqa: BLE001 - recorded on the approval, never swallowed
                applied = {"applied": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}

    def _set(r: dict[str, Any]) -> dict[str, Any]:
        r.update({"status": decision, "decided_by": user, "decided_role": norm_role(role), "decided_at": now_iso(),
                  "note": note, "applied": applied})
        return r

    return store.update(TABLE, pid, _set) or row
