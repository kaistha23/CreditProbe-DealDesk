"""Run states (forked from the Cockpit's `states.py`).

    ACCEPTED -> RUNNING -> COMPLETED            an answer was published
                        -> WAITING_FOR_USER     the thread asked something back
                        -> FAILED               nothing could be published (stated)

Forward only, compare-and-swap on `version`; a terminal run never changes again.
"""
from __future__ import annotations

ACCEPTED = "accepted"
RUNNING = "running"
COMPLETED = "completed"
WAITING_FOR_USER = "waiting_for_user"
FAILED = "failed"

WORKING = (ACCEPTED, RUNNING)
TERMINAL = (COMPLETED, WAITING_FOR_USER, FAILED)
TRANSITIONS = {ACCEPTED: (RUNNING, FAILED), RUNNING: (COMPLETED, WAITING_FOR_USER, FAILED)}

ERROR_CODES = {
    "CONVO_THREAD_NOT_FOUND": "No such thread.",
    "CONVO_NOT_ALLOWED": "This thread belongs to someone else.",
    "CONVO_BUSY": "A turn is still running on this thread.",
    "CONVO_UNKNOWN_DOMAIN": "No such conversational domain.",
    "CONVO_INTERNAL": "Something went wrong while answering; the thread is unchanged.",
}


def can_move(frm: str, to: str) -> bool:
    return to in TRANSITIONS.get(frm, ())
