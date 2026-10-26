"""Cohorts frozen by Early Warning's "Export to What-If", opened by id.

Early Warning stores each exported population -- the exact exposure ids, with
a membership hash -- in its own sqlite store (table `cohort`, JSON column
`body`, key `exposure_ids`). The public cohort endpoint leaves the ids out, so
What-If reads them from the store itself, READ-ONLY (`mode=ro`): this module
never writes to the Early Warning service or its store.

The membership hash is recomputed from the ids that were read, and the run
refuses a cohort whose ids no longer hash to what Early Warning froze.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any

from backend.whatif_v5 import paths


class CohortError(LookupError):
    """A cohort that cannot be opened, with the reason."""


PUBLIC_KEYS = ("object_id", "kind", "status", "title", "domain_id", "release_id", "period", "ruleset",
               "membership_hash", "counts", "exposure", "ecl", "stage_mix", "customer_ids", "request",
               "created_at")


def _store_for(object_id: str):
    """PLAN_R9 B5: Borrower 360 selections (b360-cohort-...) live in Borrower 360's own store."""
    if object_id.startswith("b360-cohort-"):
        from backend.b360 import cohort as b360cohort
        return b360cohort.store_path()
    return paths.ews_store()


def _read(object_id: str) -> dict[str, Any]:
    store = _store_for(object_id)
    if not store.exists():
        raise CohortError(f"Cohort {object_id} cannot be opened: no cohort has been saved yet.")
    uri = f"file:{store}?mode=ro"
    try:
        con = sqlite3.connect(uri, uri=True, timeout=5)
        try:
            row = con.execute("SELECT body FROM cohort WHERE object_id = ?", (object_id,)).fetchone()
        finally:
            con.close()
    except sqlite3.Error as e:
        raise CohortError("The Early Warning cohort could not be read just now. Please try again in a moment.") from e
    if not row:
        raise CohortError(f"{object_id} is not a cohort Early Warning has exported.")
    return json.loads(row[0])


def open_cohort(object_id: str) -> dict[str, Any]:
    """The frozen cohort with its exposure ids, after checking the membership hash."""
    said = str(object_id or "").strip()
    if not (said.startswith("ews-cohort-") or said.startswith("b360-cohort-")) or len(said) > 64:
        raise CohortError(f"'{object_id}' is not an Early Warning cohort id.")
    body = _read(said)
    ids = [str(x) for x in body.get("exposure_ids") or []]
    digest = hashlib.sha256("\n".join(ids).encode()).hexdigest()
    if body.get("membership_hash") and digest != body["membership_hash"]:
        raise CohortError(f"Cohort {said}'s exposure ids no longer match its membership hash; it was not opened.")
    body["exposure_ids"] = ids
    body["membership_verified"] = bool(body.get("membership_hash"))
    return body


def public(body: dict[str, Any]) -> dict[str, Any]:
    out = {k: body.get(k) for k in PUBLIC_KEYS if k in body}
    out["membership_verified"] = body.get("membership_verified", False)
    out["source"] = ("Borrower 360 store (read-only)" if str(body.get("object_id", "")).startswith("b360-cohort-")
                     else "Early Warning store (read-only)")
    return out


__all__ = ["CohortError", "open_cohort", "public"]
