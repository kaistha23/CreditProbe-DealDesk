"""R12 Session E: publishers that move the R11 operational stores into Data Domains (PLAN_R12 §0 "How written decisions
reach Data Domains"). The app keeps writing its own store; these functions publish what it holds as relations.

    from backend.dealdesk.data import bridge
    bridge.publish_r11_conditions()           # var/dealdesk sqlite review_conditions -> dd_condition (source = r11)
    bridge.publish_workflow(pid, from_state, to_state, actor, role, note)   # one dd_workflow_event row
    bridge.publish_monitoring_plan(plan)      # dd_monitoring_plan with supersede-on-change

Call them from the owning module after a write (B, D, U); they never edit the R11 store.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from backend.dealdesk.data.store import dd_read, publish

_STATUS = {"met": "met", "waived": "waived", "breached": "breached", "overdue": "not_complied", "due": "open", "open": "open"}
_KIND = {"covenant": "covenant", "watch": "monitoring", "cp": "cp", "undertaking": "undertaking", "reporting": "reporting"}


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def r11_condition_rows(triggers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """review_conditions triggers (evaluated) -> dd_condition rows."""
    out = []
    for t in triggers:
        out.append({"condition_id": t["id"], "proposal_id": t["deal_id"], "limit_id": "ALL", "kind": _KIND.get(t.get("kind"), "monitoring"),
                    "text": t.get("what", ""), "owner": t.get("owner", ""), "due_date": t.get("due_date") or "",
                    "frequency": "annual" if "annual" in (t.get("due_text") or "") else ("monthly" if "monthly" in (t.get("due_text") or "") else "once"),
                    "trigger_metric": ",".join((t.get("inputs") or {}).values()), "trigger_operator": "", "trigger_threshold": None,
                    "measured_value": None, "measured_at": "", "status": _STATUS.get(t.get("status") or "open", "open"), "source": "r11",
                    "prior_committee_ref": "", "set_by": t.get("origin", ""), "set_at": ""})
    return out


def publish_r11_conditions(deal_id: str | None = None, actor: str = "r11-bridge") -> dict[str, Any]:
    from backend.dealdesk import review_conditions as rc
    trig = [rc.evaluate_trigger(t, rc.facts_for(t["deal_id"])) for t in rc.stored(deal_id)]
    rows = r11_condition_rows(trig)
    where = {"source": "r11", **({"proposal_id": deal_id} if deal_id else {})}
    return publish("dd_condition", rows, mode="replace_where", where=where, actor=actor)


def publish_workflow(pid: str, from_state: str, to_state: str, actor: str, role: str, note: str = "", at: str | None = None) -> dict[str, Any]:
    seq = 1 + max([r["seq"] or 0 for r in dd_read("dd_workflow_event", proposal_id=pid)] or [0])
    return publish("dd_workflow_event", [{"event_id": f"WF-{pid}-{seq:02d}", "proposal_id": pid, "seq": seq, "from_state": from_state,
                                          "to_state": to_state, "actor": actor, "actor_role": role, "at": at or _now(), "note": note}],
                   mode="append", actor=actor)


def publish_monitoring_plan(plan: dict[str, Any], actor: str = "D") -> dict[str, Any]:
    """A new active plan for a deal; the previous active plan becomes superseded (previous_tier filled in)."""
    if not plan.get("reason"):
        raise ValueError("a monitoring tier needs a reason")
    pid = plan["proposal_id"]
    old = [r for r in dd_read("dd_monitoring_plan", proposal_id=pid, parse_json=False) if r.get("status") == "active"]
    rows = []
    for r in old:
        r = {k: v for k, v in r.items() if k not in ("rel_version", "published_at")}
        r["status"] = "superseded"
        rows.append(r)
    new = dict(plan)
    new.setdefault("plan_id", f"MP-{pid}-{_now().replace(':', '').replace('-', '')}")
    new.setdefault("set_at", _now())
    new["status"] = "active"
    new.setdefault("previous_tier", old[-1]["tier"] if old else "")
    rows.append(new)
    return publish("dd_monitoring_plan", rows, mode="upsert", actor=actor)
