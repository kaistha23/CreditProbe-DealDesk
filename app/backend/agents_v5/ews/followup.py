"""Follow-up on later runs (E3): is the trigger cured, has it worsened, is the action overdue? Escalate per the ladder.

Ladder: the relationship manager owns an action first; once it is overdue it goes to the credit officer; once it is
more than `CCO_AFTER_DAYS` days overdue, or the name worsens while an action is already with the credit officer, it
goes to the CCO. A worsening (a more severe verdict than last run) escalates one level at once.
"""
from __future__ import annotations

import datetime as dt
import functools
from typing import Any

from backend.agents_v5.ews.decide import DUE_DAYS, RANK

LADDER = ("RM", "CREDIT_OFFICER", "CCO")
LADDER_LABEL = {"RM": "Relationship manager", "CREDIT_OFFICER": "Credit officer", "CCO": "Chief Credit Officer"}
#: Days past the due date after which an overdue action goes from the credit officer to the CCO.
CCO_AFTER_DAYS = 14
TITLES = {"CREDIT_OFFICER": "Corporate Credit Manager", "CCO": "Head of Credit"}
RETAIL_TITLES = {"CREDIT_OFFICER": "Retail Credit Manager", "CCO": "Head of Credit"}


@functools.lru_cache(maxsize=2)
def _people(domain: str = "corporate") -> dict[str, str]:
    """The named credit officer and CCO from the v5 user directory (fictional users)."""
    try:
        from backend.identity_v5 import directory
        rows = directory._ROWS  # noqa: SLF001 -- a read of the static seed table
    except Exception:  # noqa: BLE001
        rows = []
    out = {}
    for role, title in (RETAIL_TITLES if domain == "retail" else TITLES).items():
        hit = next((r for r in rows if r[3] == title), None)
        out[role] = f"{hit[1]} ({title})" if hit else LADDER_LABEL[role]
    return out


def owner_for(role: str, rm_name: str | None, domain: str = "corporate") -> str:
    return (rm_name or "Relationship manager") if role == "RM" else _people(domain)[role]


def review(names: dict[str, dict[str, Any]], previous: dict[str, dict[str, Any]], actions: list[dict[str, Any]],
           today: dt.date, defaulted: set[str] | None = None) -> list[dict[str, Any]]:
    """One outcome per followed name. `names`: this run's verdict per borrower (verdict, rm, still_warned).
    Returns outcomes with the escalation to apply (`escalate_to`) or the closure (`close`)."""
    out = []
    by_name: dict[str, list[dict[str, Any]]] = {}
    for a in actions:
        by_name.setdefault(a["borrower_id"], []).append(a)
    for owner in sorted(set(by_name) | {k for k, v in previous.items() if v["verdict"] in ("watchlist", "sicr", "utp")}):
        now = names.get(owner)
        prev = previous.get(owner)
        acts = by_name.get(owner, [])
        if now is None and owner in (defaulted or set()):
            out.append({"borrower_id": owner, "outcome": "defaulted", "previous": prev["verdict"] if prev else None,
                        "current": None, "close": [a["id"] for a in acts], "actions": acts,
                        "why": "Now Stage 3 or in default: the action passes to recovery and provisioning."})
            continue
        if now is None:
            out.append({"borrower_id": owner, "outcome": "not_reviewed",
                        "why": "Not in this run's scope or budget; carried to the next run.", "actions": acts})
            continue
        was = prev["verdict"] if prev else (acts[0]["verdict"] if acts else None)
        cur = now["verdict"]
        rec: dict[str, Any] = {"borrower_id": owner, "borrower_name": now.get("borrower_name"),
                               "previous": was, "current": cur, "actions": acts}
        if cur == "noise" or (not now.get("still_warned") and cur == "watch"):
            rec.update(outcome="cured", why=f"Trigger cured: was {was}, now {cur} ({now.get('reason', '')}).",
                       close=[a["id"] for a in acts])
            out.append(rec)
            continue
        worse = was is not None and RANK[cur] > RANK[was]
        if not acts:
            rec.update(outcome="worsened" if worse else "unchanged",
                       why=(f"Worsened from {was} to {cur}." if worse else f"Still {cur}."))
            out.append(rec)
            continue
        a = max(acts, key=lambda r: (r["level"], r["id"]))
        due = dt.date.fromisoformat(a["due"])
        over = (today - due).days
        target = a["level"]
        reasons = []
        if over > 0:
            target = max(target, 1)
            reasons.append(f"action due {a['due']} is {over} days overdue")
        if over > CCO_AFTER_DAYS:
            target = max(target, 2)
        if worse:
            target = max(target, min(2, a["level"] + 1))
            reasons.append(f"worsened from {was} to {cur}")
        target = min(target, 2)
        if target > a["level"]:
            role = LADDER[target]
            rec.update(outcome="escalated", escalate_to=role, action_id=a["id"], overdue_days=max(0, over),
                       worsened=worse, role_label=LADDER_LABEL[role],
                       owner=owner_for(role, a.get("owner"), a.get("domain") or "corporate"),
                       new_due=(today + dt.timedelta(days=DUE_DAYS.get(cur, 10))).isoformat(),
                       why="Escalated to the " + LADDER_LABEL[role].lower() + ": " + "; ".join(reasons) + ".")
        elif worse:
            rec.update(outcome="worsened", why=f"Worsened from {was} to {cur}; already with the {LADDER_LABEL[LADDER[a['level']]].lower()}.")
        elif over > 0:
            rec.update(outcome="overdue", why=f"Action {over} days overdue; already with the {LADDER_LABEL[LADDER[a['level']]].lower()}.")
        else:
            rec.update(outcome="on_track", why=f"Still {cur}; action with the {LADDER_LABEL[LADDER[a['level']]].lower()}, due {a['due']}.")
        out.append(rec)
    return out


__all__ = ["CCO_AFTER_DAYS", "LADDER", "LADDER_LABEL", "owner_for", "review"]
