"""R12 Session U (PLAN_R12 §1.2, I17, I30): the deal workflow, the role views and the landing cards.

One deal file, one workflow:

    Draft (business) → Submitted → In review (credit) ⇄ Queries → Recommended → Committee → Approved with conditions

(and Declined, from review or committee; a renewal from the Book reopens the deal as "Renewal opened"). Every
handover is an event: who, which role, from, to, when and a note. The app writes each event to its own store
(var/dealdesk, operational) and publishes it to the Data Domains relation `dd_workflow_event` through the Deal Desk
publisher (PLAN_R12 §0 rule 2; columns per docs/v5/R12_DATA_CONTRACT.md), and sets `dd_deal.workflow_state`. Reads
prefer the registered relations (through the shared reader `dd_read`) and add the local events not yet published.
Before Session E's package is merged, the same code runs on the local store alone (feature check).

The view is chosen by login role (the Users & Teams roles in backend/identity_v5/directory.py), not by a button:
relationship managers see "Prepare"; credit and risk roles see "Review"; the Administrator sees Review and may
act on both sides (the existing "view as" switch re-renders the deal as another user would see it).

    GET  /workflow                         states, transitions and the caller's view
    GET  /proposals/{id}/workflow          the deal's state, history, banner and the transitions the caller may take
    POST /proposals/{id}/workflow          {to, note?} -> the new event (403 when the role may not, 409 when not allowed)
    GET  /landing/cards                    the six landing cards with counts and their filtered rows
"""
from __future__ import annotations

import datetime as dt
import sqlite3
import threading
import uuid
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query, Request

from backend.dealdesk import paths

PREFIX = "/api/v1/dealdesk"
RELATION = "dd_workflow_event"
_LOCK = threading.Lock()
_TABLE = "workflow_event_r12"
_COLS = ("event_id", "proposal_id", "seq", "from_state", "to_state", "actor", "actor_role", "at", "note")

# ------------------------------------------------------------------ states and transitions

STATES: list[dict[str, str]] = [
    {"key": "draft", "label": "Draft", "side": "business"},
    {"key": "submitted", "label": "Submitted", "side": "business"},
    {"key": "in_review", "label": "In review", "side": "credit"},
    {"key": "queries", "label": "Queries", "side": "business"},
    {"key": "recommended", "label": "Recommended", "side": "credit"},
    {"key": "committee", "label": "Committee", "side": "credit"},
    {"key": "approved", "label": "Approved with conditions", "side": "credit"},
    {"key": "declined", "label": "Declined", "side": "credit"},
    {"key": "renewal_opened", "label": "Renewal opened", "side": "business"},
]
STATE_KEYS = tuple(s["key"] for s in STATES)
LABEL = {s["key"]: s["label"] for s in STATES}

#: (from, to) -> (who may take it: "rm" | "credit" | "committee", the action label)
TRANSITIONS: dict[tuple[str, str], tuple[str, str]] = {
    ("draft", "submitted"): ("rm", "Submit to credit"),
    ("renewal_opened", "submitted"): ("rm", "Submit the renewal"),
    ("submitted", "draft"): ("rm", "Withdraw to draft"),
    ("submitted", "in_review"): ("credit", "Pick up for review"),
    ("in_review", "queries"): ("credit", "Send queries to RM"),
    ("queries", "in_review"): ("rm", "Answer queries"),
    ("in_review", "recommended"): ("credit", "Recommend"),
    ("in_review", "declined"): ("credit", "Decline"),
    ("recommended", "in_review"): ("credit", "Reopen review"),
    ("recommended", "committee"): ("credit", "Send to committee"),
    ("committee", "approved"): ("committee", "Approve with conditions"),
    ("committee", "declined"): ("committee", "Decline"),
    ("committee", "in_review"): ("committee", "Return to review"),
}

#: The R11 proposal status a deal without workflow events starts from.
FROM_STATUS = {"new": "submitted", "in_review": "in_review", "counter_offered": "recommended",
               "approved": "approved", "declined": "declined"}
#: ...and the R11 status a workflow state sets on a Deal Desk proposal.
TO_STATUS = {"draft": "new", "submitted": "new", "renewal_opened": "new", "in_review": "in_review", "queries": "in_review",
             "recommended": "counter_offered", "committee": "counter_offered", "approved": "approved", "declined": "declined"}
#: The contract's actor_role vocabulary, for display.
ROLE_LABEL = {"rm": "Relationship manager", "credit_reviewer": "Credit reviewer", "credit_head": "Head of credit",
              "cro": "Chief risk officer", "committee": "Committee", "system": "System"}


def _norm_role(role: str) -> str:
    return (role or "").strip().lower()


def side_of(user: dict[str, Any] | None) -> str:
    """'admin', 'rm', 'credit' or 'viewer' from the Users & Teams role of the (effective) user."""
    if not user:
        return "viewer"
    if user.get("is_admin"):
        return "admin"
    r = _norm_role(user.get("role", ""))
    if "relationship manager" in r or r in ("rm", "business"):
        return "rm"
    if any(k in r for k in ("credit", "risk", "committee", "cro", "analyst")):
        return "credit"
    return "viewer"


def view_of(user: dict[str, Any] | None) -> str:
    """The deal-page view for the user: 'prepare' (business) or 'review' (credit, admin, read-only roles)."""
    return "prepare" if side_of(user) == "rm" else "review"


def _who(side: str, by: str) -> bool:
    if side == "admin":
        return True
    return side == by or (by == "committee" and side == "credit")


def may(side: str, frm: str, to: str) -> bool:
    t = TRANSITIONS.get((frm, to))
    return bool(t) and _who(side, t[0])


def allowed(side: str, frm: str) -> list[dict[str, str]]:
    return [{"to": to, "label": label, "by": who} for (f, to), (who, label) in TRANSITIONS.items()
            if f == frm and _who(side, who)]


def actor_role(user: dict[str, Any] | None, by: str) -> str:
    """The contract's actor_role for a move: the side that takes it, refined by the Users & Teams title."""
    if by == "rm":
        return "rm"
    if by == "committee":
        return "committee"
    r = _norm_role((user or {}).get("role", ""))
    if "head of credit" in r:
        return "credit_head"
    if "head of risk" in r or "cro" in r:
        return "cro"
    return "credit_reviewer"


# ------------------------------------------------------------------ Data Domains (feature-checked) and the local store

def _reader():
    """E's shared reader `dd_read(relation, **filters)` when Session E's package is merged, else None."""
    try:
        from backend.dealdesk.data import store
        return store.dd_read
    except Exception:  # noqa: BLE001 - feature check
        return None


def _publisher():
    try:
        from backend.dealdesk.data import store
        return store.publish
    except Exception:  # noqa: BLE001 - feature check
        return None


def _read(relation: str, **filters: Any) -> list[dict[str, Any]]:
    rd = _reader()
    if rd is None:
        return []
    try:
        return list(rd(relation, **filters))
    except Exception:  # noqa: BLE001 - a relation not registered or empty reads as no rows
        return []


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _db() -> sqlite3.Connection:
    con = sqlite3.connect(paths.store_path())
    con.execute(f"CREATE TABLE IF NOT EXISTS {_TABLE} (event_id TEXT PRIMARY KEY, proposal_id TEXT, seq INTEGER, from_state TEXT,"
                " to_state TEXT, actor TEXT, actor_role TEXT, at TEXT, note TEXT, published INTEGER DEFAULT 0)")
    return con


def _local(pid: str | None = None, unpublished: bool = False) -> list[dict[str, Any]]:
    with _LOCK:
        con = _db()
        try:
            q = f"SELECT {', '.join(_COLS)} FROM {_TABLE}"
            where, args = [], []
            if pid:
                where.append("proposal_id = ?")
                args.append(pid)
            if unpublished:
                where.append("published = 0")
            if where:
                q += " WHERE " + " AND ".join(where)
            return [dict(zip(_COLS, r)) for r in con.execute(q + " ORDER BY at, seq", args)]
        finally:
            con.close()


def _set_deal_state(pid: str, state: str) -> None:
    """dd_deal.workflow_state follows the latest event (the whole row is republished, only that column changes)."""
    pub = _publisher()
    rows = _read("dd_deal", proposal_id=pid, parse_json=False)
    if pub is None or not rows:
        return
    row = {k: v for k, v in rows[0].items() if k not in ("rel_version", "published_at")}
    row["workflow_state"] = state
    pub("dd_deal", [row], mode="upsert", actor="U")


def _flush() -> None:
    """Publish every local event not yet in `dd_workflow_event` (one version), then the deals' latest states."""
    pub = _publisher()
    rows = _local(unpublished=True)
    if pub is None or not rows:
        return
    try:
        pub(RELATION, [{k: r[k] for k in _COLS} for r in rows], mode="upsert", actor="U")
    except Exception:  # noqa: BLE001 - the operational store keeps the events; the next move publishes them
        return
    with _LOCK:
        con = _db()
        try:
            con.executemany(f"UPDATE {_TABLE} SET published = 1 WHERE event_id = ?", [(r["event_id"],) for r in rows])
            con.commit()
        finally:
            con.close()
    last: dict[str, str] = {}
    for r in rows:
        last[r["proposal_id"]] = r["to_state"]
    for pid, st in last.items():
        try:
            _set_deal_state(pid, st)
        except Exception:  # noqa: BLE001 - the event is the record
            pass


def events(pid: str | None = None) -> list[dict[str, Any]]:
    """Every workflow event (or one deal's), oldest first: the published relation plus the local events not in it."""
    out: dict[str, dict[str, Any]] = {}
    for r in (_read(RELATION, proposal_id=pid) if pid else _read(RELATION)):
        if r.get("event_id"):
            out[str(r["event_id"])] = {k: r.get(k) for k in _COLS}
    for e in _local(pid):
        out.setdefault(str(e["event_id"]), e)
    rows = [e for e in out.values() if not pid or e.get("proposal_id") == pid]
    for e in rows:
        e["at"] = str(e.get("at") or "")
    return sorted(rows, key=lambda e: (e["at"], int(e.get("seq") or 0), str(e["event_id"])))


# ------------------------------------------------------------------ deal state

def _register() -> dict[str, dict[str, Any]]:
    """dd_deal rows by deal (workflow state, received and committee dates), when E's register is there."""
    try:
        from backend.dealdesk.data import deals
        return {r["proposal_id"]: r for r in deals.register()}
    except Exception:  # noqa: BLE001 - feature check
        return {}


def initial_state(p: dict[str, Any], reg: dict[str, Any] | None = None) -> str:
    """The state of a deal with no workflow event: dd_deal.workflow_state when set, else from its R11 status
    (a pipeline-set application is Submitted)."""
    ws = str((reg or {}).get("workflow_state") or "")
    if ws in STATE_KEYS:
        return ws
    if p.get("source") == "pipeline":
        return "submitted"
    return FROM_STATUS.get(str(p.get("status", "new")), "submitted")


def received_at(p: dict[str, Any], reg: dict[str, Any] | None = None) -> str:
    return str((reg or {}).get("received_date") or p.get("received") or "")


def state_of(p: dict[str, Any], evs: list[dict[str, Any]] | None = None, reg: dict[str, Any] | None = None) -> dict[str, Any]:
    pid = p["proposal_id"]
    evs = [e for e in (evs if evs is not None else events(pid)) if e.get("proposal_id") == pid]
    st = evs[-1]["to_state"] if evs else initial_state(p, reg)
    since = evs[-1]["at"] if evs else received_at(p, reg)
    entered_review = next((e["at"] for e in reversed(evs) if e.get("to_state") == "in_review"), None)
    return {"state": st, "label": LABEL.get(st, st), "since": since, "events": len(evs), "entered_review": entered_review}


def transition(pid: str, to: str, user: dict[str, Any] | None, note: str = "") -> dict[str, Any]:
    from backend.dealdesk import proposals
    if to not in STATE_KEYS:
        raise ValueError(f"to: one of {', '.join(STATE_KEYS)}")
    p = proposals.get(pid)  # KeyError when unknown (DD, PL and R12 deals alike)
    evs = events(pid)
    cur = state_of(p, evs, _register().get(pid))["state"]
    side = side_of(user)
    if (cur, to) not in TRANSITIONS:
        raise LookupError(f"{LABEL.get(cur, cur)} cannot move to {LABEL[to]}.")
    if not may(side, cur, to):
        raise PermissionError(f"Your role cannot take “{TRANSITIONS[(cur, to)][1]}”.")
    seq = max([int(e.get("seq") or 0) for e in evs] + [0]) + 1
    e = {"event_id": f"wf-{uuid.uuid4().hex[:12]}", "proposal_id": pid, "seq": seq, "from_state": cur, "to_state": to,
         "actor": (user or {}).get("username", ""), "actor_role": actor_role(user, TRANSITIONS[(cur, to)][0]),
         "at": _now(), "note": note[:500]}
    with _LOCK:
        con = _db()
        try:
            con.execute(f"INSERT INTO {_TABLE} ({', '.join(_COLS)}, published) VALUES ({', '.join('?' * len(_COLS))}, 0)",
                        tuple(e[k] for k in _COLS))
            con.commit()
        finally:
            con.close()
    _flush()
    # The R11 proposal status follows the workflow for a Deal Desk proposal (the pipeline and the filters read it).
    st = TO_STATUS.get(to)
    if st and pid in proposals.all_proposals() and p.get("status") != st:
        try:
            proposals.set_status(pid, st, note=f"workflow: {LABEL[to]}", by=e["actor"])
        except Exception:  # noqa: BLE001 - the workflow event is the record; the status is a convenience
            pass
    return e


def _history(evs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{**e, "from_label": LABEL.get(str(e.get("from_state") or ""), str(e.get("from_state") or "")),
             "to_label": LABEL.get(str(e["to_state"]), str(e["to_state"])),
             "role_label": ROLE_LABEL.get(str(e.get("actor_role") or ""), str(e.get("actor_role") or ""))} for e in evs]


def deal_view(pid: str, user: dict[str, Any] | None, compute_banner: bool = True) -> dict[str, Any]:
    from backend.dealdesk import proposals, registry_lookup
    p = proposals.get(pid)
    evs = events(pid)
    st = state_of(p, evs, _register().get(pid))
    side = side_of(user)
    return {
        "proposal_id": pid,
        **st,
        "states": STATES,
        "history": _history(evs),
        "view": view_of(user), "side": side,
        "actions": allowed(side, st["state"]),
        "banner": registry_lookup.banner(pid, compute=compute_banner),
    }


# ------------------------------------------------------------------ the landing cards (I30)

CARD_DEFS: list[dict[str, Any]] = [
    {"key": "to_review", "title": "New deals to review", "source": "workflow",
     "info": "Submitted by business, not yet picked up by credit; oldest first. From the workflow events (dd_workflow_event) and the deal register (dd_deal)."},
    {"key": "in_review", "title": "In review", "source": "workflow",
     "info": "Deals credit is reviewing, and those with queries open to the RM (dd_query), with the days in review."},
    {"key": "committee", "title": "Ready for committee / decided", "source": "workflow",
     "info": "Recommended, at committee (with the committee date from dd_deal), or approved with conditions."},
    {"key": "going_bad", "title": "Existing deals going bad", "source": "book",
     "info": "Material names only: tier High, or relationship EAD above the materiality floor (Deal Desk Parameters, relationship · book) "
             "with Early Warning high or critical or RAROC drifted below hurdle by the drift gap. The whole-book list stays on the Book."},
    {"key": "renewals", "title": "Renewals and reviews due", "source": "book",
     "info": "Material names renewing or due for review in the next 90 days, relationship EAD above the materiality floor. From the Book."},
    {"key": "conditions", "title": "Conditions and covenants due", "source": "conditions",
     "info": "Conditions and covenants due or overdue this month across the reviewed deals (dd_condition)."},
]
CARD_STATES = {"to_review": ("submitted",), "in_review": ("in_review", "queries"), "committee": ("recommended", "committee", "approved")}


def _days(since: str | None, today: dt.date) -> int | None:
    try:
        d = dt.date.fromisoformat(str(since)[:10])
    except ValueError:
        return None
    return max(0, (today - d).days)


def _book_card(key: str) -> dict[str, Any] | None:
    """Session I's Book feed for a landing card, when merged: `backend.dealdesk.book.landing_card(key)` returning
    {count, rows?, line?}. None (the card shows 0 with its link) until then."""
    try:
        from backend.dealdesk import book  # type: ignore[attr-defined]
        fn = getattr(book, "landing_card", None)
        if fn is None:
            return None
        out = fn(key)
        return out if isinstance(out, dict) else None
    except Exception:  # noqa: BLE001 - feature check
        return None


def _open_queries() -> dict[str, int]:
    """Open query threads per deal: the latest message of each thread in dd_query says open."""
    last: dict[str, dict[str, Any]] = {}
    for r in _read("dd_query"):
        q = str(r.get("query_id"))
        if q not in last or int(r.get("seq") or 0) >= int(last[q].get("seq") or 0):
            last[q] = r
    out: dict[str, int] = {}
    for r in last.values():
        if str(r.get("status") or "") == "open":
            out[str(r.get("proposal_id"))] = out.get(str(r.get("proposal_id")), 0) + 1
    return out


def _conditions_card(today: dt.date) -> dict[str, Any]:
    """Conditions due or overdue: `dd_condition` through the reader once populated, else the R11 tracker."""
    rows = _read("dd_condition")
    if not rows:
        feed = _book_card("conditions")
        if feed is not None:
            return {"count": int(feed.get("count", 0) or 0), "overdue": 0, "deals": 0, "source": "book", "line": feed.get("line", "")}
    if rows:
        def is_due(r: dict[str, Any]) -> bool:
            s = str(r.get("status") or "").lower()
            if s in ("met", "waived", "closed", "satisfied"):
                return False
            if s in ("due", "overdue", "breached"):
                return True
            d = str(r.get("due_date") or "")[:10]
            return bool(d) and d < (today.replace(day=28) + dt.timedelta(days=4)).replace(day=1).isoformat()
        due = [r for r in rows if is_due(r)]
        over = [r for r in due if str(r.get("status") or "").lower() in ("overdue", "breached")
                or (str(r.get("due_date") or "")[:10] and str(r.get("due_date"))[:10] < today.isoformat())]
        return {"count": len(due), "overdue": len(over), "deals": len({r.get("proposal_id") for r in due}), "source": "dd_condition"}
    try:
        from backend.dealdesk import review_conditions as rc
        summ = rc.listing()["summary"]
        by = summ.get("by_status", {})
        return {"count": int(summ.get("due", 0) or 0), "overdue": int((by.get("overdue", 0) or 0) + (by.get("breached", 0) or 0)),
                "deals": len(summ.get("deals_due", [])), "source": "conditions"}
    except Exception:  # noqa: BLE001
        return {"count": 0, "overdue": 0, "deals": 0, "source": "conditions"}


def landing_cards(today: dt.date | None = None) -> dict[str, Any]:
    from backend.dealdesk import proposals, registry_lookup
    today = today or dt.date.today()
    reg = _register()
    by_deal: dict[str, list[dict[str, Any]]] = {}
    for e in events():
        by_deal.setdefault(str(e.get("proposal_id")), []).append(e)
    queries = _open_queries()
    rows: dict[str, list[dict[str, Any]]] = {k: [] for k in CARD_STATES}
    for p in registry_lookup.all_deals():
        pid = p["proposal_id"]
        r = reg.get(pid, {})
        st = state_of(p, by_deal.get(pid, []), r)
        card = next((c for c, states in CARD_STATES.items() if st["state"] in states), None)
        if not card:
            continue
        s = proposals.summary(p)
        rows[card].append({
            "proposal_id": pid, "obligor_name": r.get("obligor_name") or s.get("obligor_name", ""), "sector": s.get("sector", ""),
            "rating": s.get("rating", ""), "amount_sar_mn": s.get("amount_sar_mn"), "rm": r.get("rm") or s.get("rm", ""),
            "state": st["state"], "state_label": st["label"], "since": st["since"],
            "days": _days(st["entered_review"] or st["since"], today), "queries_open": queries.get(pid, 0),
            "committee_date": r.get("committee_date"), "product": r.get("product") or "corporate",
            "source": {"pipeline": "Pipeline set", "r12_demo": "Deal Desk"}.get(str(p.get("source") or ""), "Deal Desk"),
            "href": f"/deal-desk/{pid}",
        })
    rows["to_review"].sort(key=lambda x: (str(x["since"] or "9999"), x["proposal_id"]))
    rows["in_review"].sort(key=lambda x: (-(x["days"] or 0), x["proposal_id"]))
    order = {"committee": 0, "recommended": 1, "approved": 2}
    rows["committee"].sort(key=lambda x: (order.get(x["state"], 3), str(x["committee_date"] or "9999"), x["proposal_id"]))
    cards = []
    for d in CARD_DEFS:
        c: dict[str, Any] = {k: d[k] for k in ("key", "title", "source", "info")}
        if d["key"] in CARD_STATES:
            rs = rows[d["key"]]
            c.update(count=len(rs), rows=rs, href=f"/deal-desk?card={d['key']}", available=True)
            if d["key"] == "to_review":
                c["sub"] = f"Oldest {rs[0]['days']} days" if rs and rs[0]["days"] is not None else "None waiting"
            elif d["key"] == "in_review":
                c["sub"] = f"{sum(1 for x in rs if x['state'] == 'queries' or x['queries_open'])} with queries open"
            else:
                c["sub"] = f"{sum(1 for x in rs if x['state'] == 'approved')} approved with conditions"
        elif d["source"] == "book":
            feed = _book_card(d["key"])
            filt = "material_going_bad" if d["key"] == "going_bad" else "material_renewals"
            c.update(count=int((feed or {}).get("count", 0) or 0), rows=(feed or {}).get("rows", []),
                     href=(feed or {}).get("href") or f"/deal-desk?tab=book&filter={filt}", available=feed is not None,
                     sub=(feed or {}).get("line") or ("From the Book" if feed is not None else "Book not connected yet"))
        else:
            cc = _conditions_card(today)
            c.update(count=cc["count"], rows=[], href="/deal-desk/review?view=conditions", available=True,
                     sub=f"{cc['overdue']} overdue" if cc.get("overdue") else "None overdue")
        cards.append(c)
    sme = _sme_card()
    if sme is not None:
        cards.append(sme)
    return {"as_of": paths.AS_OF, "today": today.isoformat(), "cards": cards}


def _sme_card() -> dict[str, Any] | None:
    """PLAN_R12 §1.8: the SME fast-track card, from Session P's lane (`products.sme.counts()`) when merged."""
    try:
        from backend.dealdesk.products import sme  # type: ignore[attr-defined]
        c = sme.counts()
    except Exception:  # noqa: BLE001 - feature check
        return None
    return {"key": "sme", "title": "SME fast track", "source": "products", "count": int(c.get("count", 0) or 0), "rows": [],
            "info": "SME programme applications in the fast-track lane: scorecard, policy rules, DoA by amount (dd_sme_application).",
            "href": "/deal-desk#sme-fast-track", "available": True, "sub": str(c.get("sub") or "")}


# ------------------------------------------------------------------ the API

router = APIRouter(prefix=PREFIX, tags=["dealdesk-r12-workflow"])


def _user(request: Request) -> dict[str, Any] | None:
    try:
        from backend.identity_v5.client import current_user
        return current_user(request)
    except Exception:  # noqa: BLE001 - the engine answers without the Core service
        return None


@router.get("/workflow")
def workflow_meta(request: Request) -> dict[str, Any]:
    u = _user(request)
    return {"states": STATES, "transitions": [{"from": f, "to": t, "by": w, "label": lab} for (f, t), (w, lab) in TRANSITIONS.items()],
            "view": view_of(u), "side": side_of(u), "user": (u or {}).get("username", ""), "role": (u or {}).get("role", "")}


@router.get("/proposals/{pid}/workflow")
def get_deal_workflow(pid: str, request: Request, banner: int = Query(default=1)) -> dict[str, Any]:
    try:
        return deal_view(pid, _user(request), compute_banner=bool(banner))
    except KeyError:
        raise HTTPException(404, f"No proposal {pid}.") from None


@router.post("/proposals/{pid}/workflow")
def post_deal_workflow(pid: str, request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    u = _user(request)
    try:
        e = transition(pid, str(body.get("to", "")), u, str(body.get("note", "") or ""))
    except KeyError:
        raise HTTPException(404, f"No proposal {pid}.") from None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from None
    except LookupError as exc:
        raise HTTPException(409, str(exc)) from None
    return {"event": e, **deal_view(pid, u, compute_banner=False)}


@router.get("/landing/cards")
def get_landing_cards() -> dict[str, Any]:
    return landing_cards()


def documents_missing(pid: str) -> dict[str, Any]:
    """The action bar's "Documents (n)": pending or expired documents of the deal in `dd_document` (I26)."""
    rows = _read("dd_document", proposal_id=pid)
    missing = [r for r in rows if str(r.get("status") or "") in ("pending", "expired")]
    return {"proposal_id": pid, "required": len(rows), "missing": len(missing) if rows else None,
            "source": "dd_document" if rows else None}


@router.get("/proposals/{pid}/documents/missing")
def get_documents_missing(pid: str) -> dict[str, Any]:
    return documents_missing(pid)


__all__ = ["STATES", "TRANSITIONS", "allowed", "deal_view", "events", "landing_cards", "may", "router", "side_of", "state_of",
           "transition", "view_of"]
