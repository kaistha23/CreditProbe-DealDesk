"""R10 C4: send real prompts to every conversational box's API and record question -> answer -> render.

Run with the v5 services up (ops/v5.sh start). Signs in by minting a session for the first admin user directly
in the identity store (no password is read, printed or passed). Writes docs/v5/R10_CHAT_AUDIT.json; the
markdown log is docs/v5/R10_CHAT_AUDIT.md.
"""
from __future__ import annotations

import json
import secrets
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TOKEN = ""


def session() -> str:
    from backend.identity_v5 import store as ids
    ids.ensure()
    with ids.db() as con:
        row = con.execute("SELECT username FROM users WHERE is_admin=1 ORDER BY username LIMIT 1").fetchone()
        tok = secrets.token_urlsafe(32)
        con.execute("INSERT INTO sessions(token_hash, username, view_as, created_at, expires_at) VALUES(?,?,?,?,?)",
                    (ids._hash_token(tok), row["username"], None, ids.now(), ids._later(120)))
        con.commit()
    return tok


def call(method: str, url: str, body: dict | None = None, timeout: float = 180) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json",
                                                                         "Cookie": f"cp_session={TOKEN}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {}
    except Exception as e:  # noqa: BLE001
        return 0, {"error": str(e)}


def poll(base: str, run: dict, key: str = "terminal") -> dict:
    rid = run.get("run_id")
    for _ in range(900):
        _, r = call("GET", f"{base}/runs/{rid}")
        if r.get(key) or r.get("state") in ("completed", "failed", "waiting_for_user", "refused", "cancelled"):
            return r
        time.sleep(0.2)
    return {"state": "timeout"}


def summarise(obj) -> tuple[str, list[str]]:
    """First readable text and the block types."""
    blocks = []
    text = ""
    if isinstance(obj, dict) and obj.get("turns") and isinstance(obj["turns"], list):
        obj = obj["turns"][-1]
    if isinstance(obj, dict) and isinstance(obj.get("messages"), list) and obj["messages"]:
        m = obj["messages"][-1]
        kinds = [a.get("kind", "?") for a in (m.get("actions") or [])]
        for a in m.get("actions") or []:
            kinds += ["table"] * len(a.get("tables") or []) + ["chart"] * len(a.get("charts") or [])
        return " ".join(str(m.get("text") or "").split())[:220], (["message"] if m.get("role") == "assistant" else []) + kinds
    if isinstance(obj, dict) and isinstance(obj.get("report"), dict) and not obj.get("answer"):
        rep = obj["report"]
        return f"report created: {rep.get('title')} ({rep.get('section_count')} sections)", ["report"]
    ans = obj.get("answer") if isinstance(obj, dict) else None
    src = ans if isinstance(ans, dict) else obj
    for b in (src or {}).get("blocks", []) or []:
        blocks.append(b.get("type", "?"))
        if not text:
            for k in ("text", "markdown", "md", "headline", "summary"):
                if isinstance(b.get(k), str) and b[k].strip():
                    text = b[k]
                    break
            if not text and b.get("type") == "proposal":
                text = "; ".join(s.get("restatement", "") for s in b.get("steps", []))
            if not text and b.get("type") == "result":
                c = (b.get("result") or {}).get("cards") or {}
                text = f"ECL change {c.get('change')} SAR m"
    if not text:
        for k in ("text", "answer", "reply", "headline"):
            v = (src or {}).get(k)
            if isinstance(v, str) and v.strip():
                text = v
                break
    return " ".join(text.split())[:220], blocks


RESULTS: list[dict] = []


def record(box: str, q: str, status: int, obj: dict, ok: bool | None = None):
    text, blocks = summarise(obj)
    good = ok if ok is not None else (status in (200, 201, 202) and bool(text or blocks) and "error" not in blocks
                                      and not text.startswith(("id:", "Something went wrong")))
    RESULTS.append({"box": box, "question": q, "status": status, "answer": text, "blocks": blocks, "ok": good})
    print(f"[{'OK ' if good else 'FAIL'}] {box}: {q[:70]} -> {status} {blocks[:6]} {text[:120]}")


def whatif():
    base = "http://127.0.0.1:8503/api/v1/whatif"
    q1 = "downgrade 2 notches and increase PD by 1.2 and reduce LGD by 1.2"
    s, t = call("POST", f"{base}/threads", {"domain": "corporate", "question": q1})
    r = poll(base, t.get("run", {})) if s == 201 or t.get("run") else t
    record("What-If", q1, s, r, ok="proposal" in summarise(r)[1] and "PD +20%" in summarise(r)[0])
    tid = t.get("thread_id")
    for q in ("execute with the delta method", "how likely is this?", "which sectors drive the ECL change?"):
        s, run = call("POST", f"{base}/threads/{tid}/runs", {"question": q})
        r = poll(base, run)
        record("What-If", q, s, r)


def convo(box: str, base: str, domain: str, prompts: list[str], scope: dict | None = None):
    s, t = call("POST", f"{base}/threads", {"domain": domain, "scope": scope or {}, "question": prompts[0]})
    tid = (t.get("thread") or {}).get("thread_id")
    r = poll(base, t.get("run") or {}) if t.get("run") else t
    record(box, prompts[0], s, r)
    for q in prompts[1:]:
        s, run = call("POST", f"{base}/threads/{tid}/runs", {"question": q})
        r = poll(base, run)
        record(box, q, s, r)


def dealdesk():
    base = "http://127.0.0.1:8508/api/v1/dealdesk/desk"
    s, lst = call("GET", "http://127.0.0.1:8508/api/v1/dealdesk/proposals")
    items = lst.get("proposals") or []
    pid = items[0].get("proposal_id") if items else None
    for q in ("What RAROC does this deal make against the hurdle?", "What tenor and margin should we offer?",
              "What are the main risks in this proposal?"):
        s, r = call("POST", f"{base}/proposals/{pid}/thread", {"question": q}) if pid else (0, {})
        record("Deal Desk", q, s, r)
    s, r = call("POST", f"{base}/ask", {"question": "Which pending deals are below the hurdle rate?"})
    record("Deal Desk (desk ask)", "Which pending deals are below the hurdle rate?", s, r)


def playbook():
    base = "http://127.0.0.1:8506/api/v1/playbook"
    s, r = call("POST", f"{base}/threads", {"text": "Draft a credit memo for CB01312"})
    record("Playbook (ask box)", "Draft a credit memo for CB01312", s, r)
    rid = r.get("report_id") or (r.get("report") or {}).get("id") or r.get("id")
    s, rep = call("GET", f"{base}/reports/{rid}") if rid else (0, {})
    secs = (rep.get("report") or rep).get("sections") or []
    sid = secs[0].get("id") if secs else None
    for q in ("Summarise the borrower's exposure and rating", "What are the key risks? Show a table",
              "Write two sentences on the recommendation"):
        s, a = call("POST", f"{base}/reports/{rid}/sections/{sid}/thread", {"text": q}) if sid else (0, {})
        record("Playbook (section side panel)", q, s, a)


def scorecard():
    base = "http://127.0.0.1:8507/api/v1/scorecard"
    q0 = "Validate the Retail Application Scorecard v2.1"
    s, t = call("POST", f"{base}/threads", {"question": q0})
    tid = t.get("thread_id") or (t.get("thread") or {}).get("thread_id")
    record("Scorecard", q0, s, t)
    for q in ("run it", "What are the findings?", "Explain the red tests", "what is PSI?"):
        s, r = call("POST", f"{base}/threads/{tid}/messages", {"text": q, "question": q})
        record("Scorecard", q, s, r)


def projects():
    base = "http://127.0.0.1:8505/api/v1/workspace"
    s, lst = call("GET", f"{base}/projects")
    items = lst.get("projects") or lst.get("items") or []
    pid = items[0]["id"] if items else None
    q0 = "What is the corporate ECL and which sector carries the most?"
    s, t = call("POST", f"{base}/projects/{pid}/threads", {"title": "", "question": q0}) if pid else (0, {})
    msgs = t.get("messages") or []
    last = msgs[-1] if msgs else {}
    record("Projects", q0, s, {"text": last.get("text") or last.get("body") or ""}, ok=s == 201 and bool(msgs and msgs[-1].get("role") == "assistant") and bool(last.get("text") or last.get("body")))
    tid = t.get("id") or t.get("thread_id")
    for q in ("How many borrowers are on the watchlist?", "Summarise this project in three bullets"):
        s, t2 = call("POST", f"{base}/projects/{pid}/threads/{tid}/messages", {"text": q})
        msgs = t2.get("messages") or []
        last = msgs[-1] if msgs else {}
        record("Projects", q, s, {"text": last.get("text") or last.get("body") or ""}, ok=s == 201 and bool(msgs and msgs[-1].get("role") == "assistant") and bool(last.get("text") or last.get("body")))


def main():
    global TOKEN
    TOKEN = session()
    for fn in (whatif, dealdesk, playbook, scorecard, projects,
               lambda: convo("Lenses (no lens open)", "http://127.0.0.1:8509/api/v1/lenses/convo", "lenses",
                             ["What should I add next?"]),
               lambda: convo("Lenses", "http://127.0.0.1:8509/api/v1/lenses/convo", "lenses",
                             ["What should I add next?", "Explain the first tile", "Show NPL ratio by sector"],
                             {"lens_id": (call("GET", "http://127.0.0.1:8509/api/v1/lenses/lenses")[1].get("featured") or [{}])[0].get("lens_id", "")}),
               lambda: convo("Admin", "http://127.0.0.1:8510/api/v1/admin/convo", "admin",
                             ["What can nawaf.alotaibi see?", "Who changed the access policies this week?",
                              "Create a workflow so Critical Early Warning names need an RM action plan within 5 days"])):
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            RESULTS.append({"box": getattr(fn, "__name__", "?"), "question": "(harness)", "status": 0,
                            "answer": f"harness error: {e}", "blocks": [], "ok": False})
            print("HARNESS", fn, e)
    out = ROOT / "docs/v5/R10_CHAT_AUDIT.json"
    out.write_text(json.dumps(RESULTS, indent=1))
    print(f"{sum(r['ok'] for r in RESULTS)} of {len(RESULTS)} OK -> {out}")


if __name__ == "__main__":
    main()
