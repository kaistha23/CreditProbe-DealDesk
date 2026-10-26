"""Run states of a What-If turn (forked from the Cockpit's `states.py`, re-keyed).

    ACCEPTED -> RUNNING -> COMPLETED            an answer was published
                        -> WAITING_FOR_USER     the thread asked something (model choice, a size)
                        -> FAILED               nothing could be published (the error is stated)

A run moves forward only (compare-and-swap on `version` in the store); a
terminal run never changes again.
"""
from __future__ import annotations

ACCEPTED = "accepted"
RUNNING = "running"
COMPLETED = "completed"
WAITING_FOR_USER = "waiting_for_user"
FAILED = "failed"

WORKING = (ACCEPTED, RUNNING)
TERMINAL = (COMPLETED, WAITING_FOR_USER, FAILED)
ANSWER_BEARING = (COMPLETED, WAITING_FOR_USER)
TRANSITIONS = {ACCEPTED: (RUNNING, FAILED), RUNNING: (COMPLETED, WAITING_FOR_USER, FAILED)}

ERROR_CODES = {
    "WHATIF_RUN_REFUSED": "The scenario could not be run as stated.",
    "WHATIF_THREAD_NOT_FOUND": "No such thread.",
    "WHATIF_NOT_ALLOWED": "This thread belongs to someone else.",
    "WHATIF_INTERNAL": "Something went wrong while answering; the thread is unchanged.",
    "WHATIF_BUSY": "A turn is still running on this thread.",
}


def can_move(frm: str, to: str) -> bool:
    return to in TRANSITIONS.get(frm, ())
