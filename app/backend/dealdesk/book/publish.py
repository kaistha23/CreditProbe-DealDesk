"""Publish the Book's derived relations through E's publisher (PLAN_R12 §0 rule 2):
`dd_raroc_drift` (origination vs now with attribution, one row per facility and period) and `dd_promise`
(promises measured against deposits). Run by `POST /book/publish` and `python -m backend.dealdesk.book.publish`.
"""
from __future__ import annotations

from typing import Any

from backend.dealdesk.book import core, drift, promises, sources


def run(ref: str | None = None) -> dict[str, Any]:
    f, pending = core.frame(ref)
    d = sources.publish("dd_raroc_drift", drift.drift_rows(f))
    p = sources.publish("dd_promise", promises.publish_rows(promises.frame(f, pending)))
    core.refresh()
    drift.universe.cache_clear()
    return {"dd_raroc_drift": d, "dd_promise": p, "pending": pending}


if __name__ == "__main__":  # pragma: no cover
    import json
    print(json.dumps(run(), default=str, indent=1)[:2000])
