"""Worked examples for the Admin product knowledge pages (G6), computed on the live Admin domain and the books."""
from __future__ import annotations

from typing import Any
from backend.v5common.edition import is_dealdesk


def _mn(v: float) -> str:
    from backend.common.format import sar   # G5: the shared formatter
    return sar(v)


def example(key: str) -> dict[str, Any] | None:
    from backend.access.policy import MODULES
    from backend.admin import logic, seed, store

    if key in ("admin_view_as", "admin_overview"):
        pv = logic.preview("nawaf.alotaibi")
        c = next(b for b in pv["books"] if b["book"] == "corporate")
        top = c["sample"][0] if c["sample"] else {}
        text = (f"Nawaf Al-Otaibi is an RM at Riyadh Olaya (RM0005) under “Riyadh RMs see only their portfolio”. "
                f"View as user shows that he sees {c['seen']['customers']:,} of {c['total']['customers']:,} corporate "
                f"borrowers, {_mn(c['seen']['ead_sar_mn'])} of {_mn(c['total']['ead_sar_mn'])} EAD, and no retail book; "
                f"his largest borrower is {top.get('id', '')} {top.get('name', '')} ({_mn(float(top.get('ead_sar_mn', 0)))}). "
                + ("Deal Desk and every assistant answer show him only those borrowers; Data Domains and Admin are closed "
                   "to him, and he cannot approve or run models." if is_dealdesk() else
                   "Early Warning, Customer 360, Deal Desk and every assistant answer show him only those borrowers; "
                   "What-If, Data Domains and Admin are closed to him, and he cannot approve or run models."))
        if key == "admin_overview":
            with store.db() as con:
                n = {k: len(store.live_list(con, k)) for k in ("policy", "workflow", "user")}
                pend = len(store.changes(con, status="submitted"))
            text = (f"Admin holds {n['policy']} data access policies, {n['workflow']} approval workflows and "
                    f"{n['user']} users; {pend} changes wait for an approver. " + text)
        return {"title": "What an RM sees", "text": text,
                "links": [{"label": "Open View as user", "href": "/workflow?tab=access"}]}
    if key == "admin_workflow_ews" and is_dealdesk():
        with store.db() as con:
            wf = store.get_live(con, "workflow", "WF-DD-DOA")["body"]
        sample = next(iter(logic.samples().get("deal_proposal") or []), {"id": "DD-01", "label": "DD-01"})
        sim = logic.simulate(wf, sample)
        s1 = sim["timeline"][0]
        return {"title": "A proposal's route to approval",
                "text": (f"Simulating “{wf['name']}” on {sample['label']}: the first step goes to {s1['assignee']}, due {s1['due']}; "
                         f"without it, it escalates on {s1['escalates']} to {s1['escalate_to']}. The route takes {sim['total_days']:g} days end to end."),
                "links": [{"label": "Open Approval workflows", "href": "/workflow?tab=workflows"}]}
    if key == "admin_workflow_ews":
        with store.db() as con:
            wf = store.get_live(con, "workflow", "WF-EWS-CRIT")["body"]
        sample = next(iter(logic.samples().get("ews_name") or []), {"id": "CB00398", "label": "CB00398"})
        sim = logic.simulate(wf, sample)
        s1 = sim["timeline"][0]
        return {"title": "A Critical Early Warning name",
                "text": (f"Simulating “{wf['name']}” on {sample['label']}: the RM action plan goes to {s1['assignee']}, "
                         f"due {s1['due']}; without it, it escalates on {s1['escalates']} to {s1['escalate_to']}, who then "
                         f"decides on the watchlist. The route takes {sim['total_days']:g} days end to end."),
                "links": [{"label": "Open Approval workflows", "href": "/workflow?tab=workflows"}]}
    if key == "admin_users":
        users = seed.users()
        rms = [u for u in users if u["role"] == "rm"]
        return {"title": "The directory", "text": (f"{len(users)} users in {len(seed.TEAMS)} teams and {len(seed.ROLES)} roles; "
                                                   f"{len(rms)} RMs sign in ({', '.join(u['name'] + ' ' + u['rm_id'] for u in rms)})."),
                "links": [{"label": "Open Users and Teams", "href": "/users"}]}
    if key == "admin_agent_ops":
        with store.db() as con:
            rs = logic.runs(con)
        d = logic.daily(rs)
        worst = max(d["modules"], key=lambda m: m["refusal_rate"]) if d["modules"] else None
        refused = sum(1 for r in rs if r.get("outcome") == "refused")
        return {"title": "The AI run log", "text": (f"{len(rs):,} AI runs are logged across {len(d['modules'])} modules; "
                                                    f"{refused} were refused"
                                                    + (f", most often in {MODULES.get(worst['module'], worst['module'])} ({worst['refusal_rate'] * 100:.1f}%)" if worst and worst['refusal_rate'] else "")
                                                    + ". Clicking a run shows each process step's time and the tools it called."),
                "links": [{"label": "Open Agent Operations", "href": "/agent-operations"}]}
    if key == "admin_studio":
        return {"title": "Testing a change", "text": (("Pick Deal Desk, switch Answers to short and ask “Optimise DD-02 to clear the hurdle” "
                                                       "in the Test bench: the live and draft configurations show the instructions the model "
                                                       "receives and the tools they plan, side by side, before you submit the draft.") if is_dealdesk() else
                                                      ("Pick What-If, switch Answers to short and ask “Increase PD by 15% with staging "
                                                      "effect” in the Test bench: the live and draft configurations show the instructions "
                                                      "the model receives and the tools they plan, side by side, before you submit the draft.")),
                "links": [{"label": "Open AI Studio", "href": "/ai-studio"}]}
    if key == "admin_settings":
        reg = logic.parameter_register()
        return {"title": "The parameter register", "text": (f"{len(reg)} owned parameter tables are registered, for example "
                                                            + "; ".join(f"{p['name']} ({p['module']}, {p['version']}, owner {p['owner']})" for p in reg[:3]) + "."),
                "links": [{"label": "Open Settings", "href": "/settings"}]}
    if key == "admin_audit":
        with store.db() as con:
            ev = logic.audit_events(con, logic.runs(con))
        cats: dict[str, int] = {}
        for e in ev:
            cats[e["category"]] = cats.get(e["category"], 0) + 1
        return {"title": "The trail", "text": (f"The log holds {len(ev):,} events: " + ", ".join(f"{n:,} {c}" for c, n in sorted(cats.items())) + "."),
                "links": [{"label": "Open the Audit log", "href": "/audit-log"}]}
    return None
