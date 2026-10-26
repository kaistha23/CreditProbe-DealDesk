"""PLAN_R12 I16-1 / I17: RM queries through Mail, replies threaded back (relation dd_query).

  raise_query(deal_id, question, kind, ref_id, to, by)   sends the query as a Mail message from the reviewer to the RM, with a
                                                         `document` object that opens the deal's Review step, and records it
  sync(deal_id)                                          reads each query's Mail thread; a message from anyone but the sender is
                                                         the reply (status answered, reply text and time kept)
  answer(query_id, text, by)                             the RM answers from Deal Desk: a reply in the same Mail thread
  close(query_id, by, note) / reopen                     the reviewer closes the item (or a received document closes it)
  listing(deal_id)                                       every query with its thread, open / answered / closed counts

Mail is the Core service's store (backend.mail_v5.store on the Core sqlite, the same file the Core service on :8505 uses).
When Mail cannot be reached the query is kept with status "queued" and sent on the next sync.
"""
from __future__ import annotations

import datetime as dt
import html
import re
import sqlite3
import threading
import uuid
from typing import Any

from backend.dealdesk import paths

_LOCK = threading.Lock()
STATUSES = ("queued", "sent", "answered", "closed")
KINDS = ("document", "finding", "information")
DEFAULT_RM = "nawaf.alotaibi"
DEFAULT_REVIEWER = "sara.aldosari"


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _db() -> sqlite3.Connection:
    con = sqlite3.connect(paths.store_path())
    con.row_factory = sqlite3.Row
    con.execute("CREATE TABLE IF NOT EXISTS r12_queries (query_id TEXT PRIMARY KEY, deal_id TEXT, kind TEXT, ref_id TEXT, question TEXT,"
                " to_user TEXT, from_user TEXT, thread_id TEXT, message_id TEXT, status TEXT, sent_at TEXT, answered_at TEXT, reply_text TEXT,"
                " reply_by TEXT, closed_at TEXT, closed_by TEXT, note TEXT, created_at TEXT)")
    return con


def _mail():
    from backend.identity_v5 import store as ids
    from backend.mail_v5 import store as mail_store
    return ids, mail_store


def users() -> dict[str, dict[str, Any]]:
    try:
        ids, _ = _mail()
        with ids.db() as con:
            return ids.user_map(con)
    except Exception:  # noqa: BLE001
        from backend.identity_v5 import directory
        return {u: {"username": u} for u in directory.USERNAMES}


def rm_for(deal_id: str) -> str:
    """The deal's RM (dd_deal.rm) when it names a directory user, else the default RM."""
    try:
        from backend.dealdesk.review2 import publish as P
        rows = P.read("dd_deal", proposal_id=deal_id)
        name = str((rows[0].get("rm") if rows else "") or "").strip().lower()
        if name:
            for u, r in users().items():
                if name in (u.lower(), str(r.get("name") or "").lower()):
                    return u
    except Exception:  # noqa: BLE001
        pass
    return default_rm()


def default_rm() -> str:
    um = users()
    rms = [u for u, r in um.items() if "relationship" in str(r.get("role") or "").lower()]
    return DEFAULT_RM if DEFAULT_RM in rms or not rms else rms[0]


def _deal_name(deal_id: str) -> str:
    try:
        from backend.dealdesk.review2 import source as S
        return S.deal_file(deal_id)["subject"]["name"]
    except Exception:  # noqa: BLE001
        return deal_id


def _obj(deal_id: str, qid: str, name: str, question: str) -> dict[str, Any]:
    return {"type": "document", "id": f"dealdesk-query:{qid}", "label": f"{name}: credit query"[:200],
            "href": f"/deal-desk/{deal_id}?step=review&query={qid}", "summary": question[:400],
            "meta": {"deal_id": deal_id, "query_id": qid, "module": "dealdesk"}}


def _send(row: dict[str, Any]) -> dict[str, Any]:
    ids, ms = _mail()
    name = _deal_name(row["deal_id"])
    subject = f"Credit query: {name} ({row['deal_id']})"
    body = (f"<p>Credit review query on <strong>{html.escape(name)}</strong> ({html.escape(row['deal_id'])}):</p>"
            f"<p>{html.escape(row['question'])}</p><p>Please reply to this message; the reply is threaded back into the Deal Desk review.</p>")
    with ids.db() as con:
        res = ms.send(con, row["from_user"], [row["to_user"]], [], subject, body,
                      [{"kind": "object", "object": _obj(row["deal_id"], row["query_id"], name, row["question"])}])
    return res


def raise_query(deal_id: str, question: str, kind: str = "information", ref_id: str | None = None, to: str | None = None,
                by: str | None = None) -> dict[str, Any]:
    question = re.sub(r"\s+", " ", (question or "").strip())
    if not question:
        raise ValueError("A query needs a question.")
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}")
    with _LOCK, _db() as con:
        dup = con.execute("SELECT query_id FROM r12_queries WHERE deal_id=? AND ref_id=? AND status IN ('queued','sent')", (deal_id, ref_id)).fetchone() if ref_id else None
    if dup:
        return get(dup["query_id"])
    row = {"query_id": "q_" + uuid.uuid4().hex[:10], "deal_id": deal_id, "kind": kind, "ref_id": ref_id, "question": question[:2000],
           "to_user": to or rm_for(deal_id), "from_user": by or DEFAULT_REVIEWER, "thread_id": None, "message_id": None, "status": "queued",
           "sent_at": None, "answered_at": None, "reply_text": None, "reply_by": None, "closed_at": None, "closed_by": None, "note": None,
           "created_at": _now()}
    if row["to_user"] == row["from_user"]:
        row["to_user"] = default_rm() if row["from_user"] != default_rm() else DEFAULT_REVIEWER
    try:
        res = _send(row)
        row.update(thread_id=res["thread_id"], message_id=res["message_id"], status="sent", sent_at=_now())
    except Exception as e:  # noqa: BLE001 - Mail unavailable: keep the query, send on the next sync
        row["note"] = f"Mail not reachable: {str(e)[:160]}"
    with _LOCK, _db() as con:
        con.execute(f"INSERT INTO r12_queries ({','.join(row)}) VALUES ({','.join('?' * len(row))})", tuple(row.values()))
    publish(deal_id)
    return get(row["query_id"])


def get(qid: str) -> dict[str, Any]:
    with _LOCK, _db() as con:
        r = con.execute("SELECT * FROM r12_queries WHERE query_id=?", (qid,)).fetchone()
    if r is None:
        raise KeyError(qid)
    return _view(dict(r))


def _view(r: dict[str, Any]) -> dict[str, Any]:
    r["mail_href"] = f"/messages?folder=all&thread={r['thread_id']}" if r.get("thread_id") else None
    r["source"] = {"relation": "dd_query", "key": {"query_id": r["query_id"]}, "period": None}
    return r


def _rows(deal_id: str | None) -> list[dict[str, Any]]:
    with _LOCK, _db() as con:
        q = "SELECT * FROM r12_queries" + (" WHERE deal_id=?" if deal_id else "") + " ORDER BY created_at"
        return [dict(r) for r in con.execute(q, (deal_id,) if deal_id else ())]


def _update(qid: str, **ch: Any) -> None:
    with _LOCK, _db() as con:
        con.execute(f"UPDATE r12_queries SET {', '.join(f'{k}=?' for k in ch)} WHERE query_id=?", (*ch.values(), qid))


def sync(deal_id: str | None = None) -> dict[str, Any]:
    """Send queued queries; pull replies from each Mail thread."""
    sent = answered = 0
    for r in _rows(deal_id):
        if r["status"] == "queued":
            try:
                res = _send(r)
                _update(r["query_id"], thread_id=res["thread_id"], message_id=res["message_id"], status="sent", sent_at=_now(), note=None)
                sent += 1
            except Exception:  # noqa: BLE001
                continue
        elif r["status"] == "sent" and r["thread_id"]:
            try:
                ids, ms = _mail()
                with ids.db() as con:
                    t = ms.thread_detail(con, r["thread_id"], r["from_user"])
            except Exception:  # noqa: BLE001
                continue
            replies = [m for m in t["messages"] if (m["sender"] or {}).get("username") != r["from_user"]]
            if replies:
                m = replies[-1]
                text = ms.strip_quotes(m.get("body_html") or "") if hasattr(ms, "strip_quotes") else m.get("body_text")
                text = re.sub(r"<[^>]+>", " ", text or m.get("body_text") or "")
                _update(r["query_id"], status="answered", answered_at=m["sent_at"], reply_text=re.sub(r"\s+", " ", html.unescape(text)).strip()[:2000],
                        reply_by=(m["sender"] or {}).get("username"))
                answered += 1
    if sent or answered:
        for d in {r["deal_id"] for r in _rows(deal_id)}:
            publish(d)
    return {"sent": sent, "answered": answered}


def answer(qid: str, text: str, by: str | None = None) -> dict[str, Any]:
    r = get(qid)
    by = by or r["to_user"]
    text = (text or "").strip()
    if not text:
        raise ValueError("An answer needs text.")
    if r["thread_id"] and r["message_id"]:
        try:
            ids, ms = _mail()
            with ids.db() as con:
                ms.send(con, by, [r["from_user"]], [], "", f"<p>{html.escape(text)}</p>", [], mode="reply", thread_id=r["thread_id"],
                        in_reply_to=r["message_id"])
        except Exception:  # noqa: BLE001 - the answer is kept in Deal Desk even if Mail refuses it
            pass
    _update(qid, status="answered", answered_at=_now(), reply_text=text[:2000], reply_by=by)
    publish(r["deal_id"])
    return get(qid)


def close(qid: str, by: str = "", note: str | None = None) -> dict[str, Any]:
    r = get(qid)
    _update(qid, status="closed", closed_at=_now(), closed_by=by or r["from_user"], note=note)
    publish(r["deal_id"])
    return get(qid)


def reopen(qid: str, by: str = "") -> dict[str, Any]:
    r = get(qid)
    _update(qid, status="answered" if r.get("reply_text") else ("sent" if r.get("thread_id") else "queued"), closed_at=None, closed_by=None)
    publish(r["deal_id"])
    return get(qid)


def close_for_ref(deal_id: str, ref_id: str, by: str = "", note: str = "") -> int:
    n = 0
    for r in _rows(deal_id):
        if r["ref_id"] == ref_id and r["status"] != "closed":
            close(r["query_id"], by, note)
            n += 1
    return n


def listing(deal_id: str | None = None, do_sync: bool = True) -> dict[str, Any]:
    if do_sync:
        try:
            sync(deal_id)
        except Exception:  # noqa: BLE001
            pass
    items = [_view(r) for r in _rows(deal_id)]
    c = {s: sum(1 for i in items if i["status"] == s) for s in STATUSES}
    open_n = c["queued"] + c["sent"]
    return {"deal_id": deal_id, "items": items, "counts": c, "open": open_n,
            "headline": (f"{open_n} quer{'y' if open_n == 1 else 'ies'} open with the RM, {c['answered']} answered awaiting review, {c['closed']} closed."
                         if items else "No queries raised.")}


def publish(deal_id: str) -> dict[str, Any]:
    """Each query thread as dd_query rows (R12_DATA_CONTRACT): seq 1 the query to the RM, seq 2 the RM's reply."""
    from backend.dealdesk.review2 import publish as P
    st = {"queued": "open", "sent": "open", "answered": "answered", "closed": "closed"}
    out = []
    for r in _rows(deal_id):
        base = {"query_id": r["query_id"], "proposal_id": r["deal_id"],
                "finding_id": r["ref_id"] if r["kind"] == "finding" else None,
                "document_id": f"B-{r['deal_id']}-{r['ref_id']}" if r["kind"] == "document" and r["ref_id"] else None,
                "subject": f"Credit query: {r['deal_id']}", "status": st.get(r["status"], "open")}
        out.append({**base, "seq": 1, "direction": "to_rm", "author": r["from_user"], "author_role": "credit_reviewer",
                    "sent_at": r["sent_at"] or r["created_at"], "body": r["question"], "mail_ref": r["message_id"] or r["thread_id"]})
        if r.get("reply_text"):
            out.append({**base, "seq": 2, "direction": "from_rm", "author": r["reply_by"], "author_role": "rm", "sent_at": r["answered_at"],
                        "body": r["reply_text"], "mail_ref": r["thread_id"]})
    return P.publish("dd_query", out, key=("query_id", "seq"))
