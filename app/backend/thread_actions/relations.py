"""Data Domains relations of the thread actions (R16 t, M7), registered by backend/dealdesk/data/schema.py.

    ta_memo     one row per Word memo / note / paper written from a thread (any module)
    ta_action   one row per thread action taken (share, trace, word, report, memo)

Pure data (standard library only), like schema.py. The demo rows (fictional, deterministic) are `demo_rows()`;
the runtime writer is backend/thread_actions/store.py (upsert, actor "t").
"""
from __future__ import annotations

from typing import Any

TA_DIR = "data/thread_actions/ta-v1"
DOMAIN = "thread_actions"
DOMAIN_LABEL = ("Thread actions",
                "R16 t (M7): what was done with the answers in every module's threads: the Word memos, notes and papers "
                "written from a thread, and each Share, Trace, Word and Add-to-report action.")


def register(ns: dict[str, Any]) -> None:
    """Add the two relations to schema.py's RELATIONS / MANIFEST / FOLDER_TEXT / DOMAIN_TEXT (called at its end)."""
    _r, PERIOD = ns["_r"], ns["PERIOD"]
    ns["MANIFEST"][TA_DIR] = "manifest.json"
    ns["FOLDER_TEXT"][TA_DIR] = ("ta-v1 (R16 t)", "Thread actions")
    ns["DOMAIN_TEXT"][DOMAIN] = DOMAIN_LABEL
    w = "t (backend/thread_actions/store.py, on every Word memo and thread action)"
    ns["RELATIONS"].update({
        "ta_memo": _r(DOMAIN, TA_DIR, "Thread memos", "one row per memo, note or paper written from a thread", ["memo_id", PERIOD],
            "Every Word document written from a thread's answers (the Word button or a 'write a memo' request), in any module: "
            "what it covers, for whom, how many answers, tables and sources it carries, and the hash of the file.", [
            ("memo_id", "text", "", "Memo identifier (TM-yyyymmdd-xxxxxx)."),
            ("module", "text", "", "Module of the thread: cockpit, noor, dealdesk, whatif, lenses, ews, b360, scorecard, playbook, intel."),
            ("thread_id", "text", "", "Thread (or run, panel) the memo was written from."),
            ("scope", "text", "", "answer (one answer) or thread (every answer in the thread)."),
            ("kind", "text", "", "memo, note or paper (the word the user asked for)."),
            ("title", "text", "", "Title of the document (the thread's subject)."),
            ("addressee", "text", "", "Addressee if one was named (e.g. CRO), else blank."),
            ("trigger", "text", "", "word_button or memo_intent (typed 'write a memo' in the thread)."),
            ("request_text", "text", "", "What the user typed when the memo came from a request (blank for the button)."),
            ("answers", "int", "", "Answers written up."),
            ("tables", "int", "", "Tables carried into the document."),
            ("sources", "int", "", "Sources listed in its trace section."),
            ("relations_named", "json", "", "Data Domains relations the trace section names."),
            ("created_by", "text", "", "User who asked for it (fictional demo users)."),
            ("created_at", "ts", "", "UTC time it was written."),
            ("file_sha256", "text", "", "SHA-256 of the .docx (var/thread_actions/memos/<memo_id>.docx)."),
            ("file_bytes", "int", "bytes", "Size of the .docx."),
        ], owner="t", writers=w),
        "ta_action": _r(DOMAIN, TA_DIR, "Thread actions log", "one row per action on a thread answer", ["action_id", PERIOD],
            "Each Share, Trace, Word, Add-to-report and memo-request action on an answer, in any module: who, when, on which "
            "thread and answer, and what it produced (a memo id, a mail, a Playbook report).", [
            ("action_id", "text", "", "Action identifier (TA-yyyymmdd-xxxxxx)."),
            ("module", "text", "", "Module of the thread."),
            ("thread_id", "text", "", "Thread (or run, panel) the action was taken on."),
            ("answer_id", "text", "", "Answer (turn, run) the action was taken on; blank for the whole thread."),
            ("action", "text", "", "share, trace, word, report or memo_intent."),
            ("target", "text", "", "What it produced or reached: memo id, mail recipients, Playbook report id."),
            ("created_by", "text", "", "User (fictional demo users)."),
            ("created_at", "ts", "", "UTC time of the action."),
        ], owner="t", writers=w),
    })


def demo_rows() -> dict[str, list[dict[str, Any]]]:
    """Fictional, deterministic seed rows (one memo from the Deal Desk thread of M7 and its actions)."""
    at = "2026-10-21T15:40:00Z"
    return {
        "ta_memo": [{
            "memo_id": "TM-20261021-000001", "module": "dealdesk", "thread_id": "desk-seed-hard-limits", "scope": "thread",
            "kind": "memo", "title": "Which proposals breach a hard limit", "addressee": "CRO", "trigger": "memo_intent",
            "request_text": "prepare a memo to the CRO", "answers": 1, "tables": 1, "sources": 2,
            "relations_named": '["dd_deal", "dd_policy_clause"]', "created_by": "anne", "created_at": at,
            "file_sha256": "", "file_bytes": 0}],
        "ta_action": [
            {"action_id": "TA-20261021-000001", "module": "dealdesk", "thread_id": "desk-seed-hard-limits", "answer_id": "",
             "action": "memo_intent", "target": "TM-20261021-000001", "created_by": "anne", "created_at": at},
            {"action_id": "TA-20261021-000002", "module": "dealdesk", "thread_id": "desk-seed-hard-limits", "answer_id": "t1",
             "action": "trace", "target": "2 relations", "created_by": "anne", "created_at": at},
        ],
    }
