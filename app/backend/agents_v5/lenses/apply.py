"""What approval does (A4): create or update the monitoring lens in the Lenses store and set the schedule.

Called only from the approval decision (`agent.decide`) after an approver with the right role says yes; nothing else
in the package writes to the Lenses store. The lens is an ordinary lens (owner = the requester), tagged
`monitoring-agent`, keyed `monitor:<scope>` so a later approval for the same scope commits a new version of the same
lens (undo and versions work as for any lens) instead of creating another one.
"""
from __future__ import annotations

import time
from typing import Any

from backend.lenses_v5 import planner
from backend.lenses_v5.engine import ENGINE
from backend.lenses_v5.store import Store

#: corporate quarter-end releases, retail month-end releases (UTC, the 2nd at 06:00); a run on a release already
#: evaluated marks its alerts as repeats and notifies nobody
CRON = {"corporate": "0 6 2 1,4,7,10 *", "retail": "0 6 2 * *"}


def _same_scope(m: dict[str, Any], filters: list[dict[str, Any]]) -> bool:
    mf = m["def"].get("filters") or []
    return all(f in mf for f in filters)


def lens_spec(book: str, filters: list[dict[str, Any]], label: str, metrics: list[dict[str, Any]]) -> dict[str, Any]:
    """Every accepted metric shown by its definition: a KPI (catalogue or custom ratio) and a trend tile, or the existing
    tile that carries it (concentration, top names, regulatory, sector breakdown). Book-level measures in a scoped set
    (a sector's share of the book in a sector lens) stay on the panel: inside the lens scope they would read 100%."""
    kpis: list[str] = []
    tiles: list[dict[str, Any]] = []
    custom: list[dict[str, Any]] = []
    seen: set[str] = set()
    for m in metrics:
        dfn = m.get("definition") or {}
        if not _same_scope(m, filters):
            continue
        extra = [f for f in (m["def"].get("filters") or []) if f not in filters]
        if dfn.get("custom_metric"):
            c = dfn["custom_metric"]
            if c["key"] not in {x["key"] for x in custom}:
                custom.append(c)
        k = dfn.get("kpi")
        if k and not extra and k not in kpis:
            kpis.append(k)
        t = dict(dfn.get("tile") or {})
        if not t:
            continue
        sig = f"{t.get('type')}|{t.get('metrics')}|{t.get('dim')}|{extra}"
        if sig in seen:
            continue
        seen.add(sig)
        if extra:
            t["filters"] = extra
        tiles.append({"id": planner._new_id(), **t})  # noqa: SLF001
    for k in ("ead", "ecl"):
        if k not in kpis:
            kpis.insert(0, k)
    spec = {"book": book, "filters": filters, "period": ENGINE.as_of(book), "scope_label": planner.scope_label(book, filters),
            "title": label, "kpis": kpis[:10], "tiles": tiles, "compare": None, "custom_metrics": custom,
            "request": f"Monitoring agent: {label}"}
    return planner.normalise(spec)


def team_of(username: str) -> str:
    try:
        from backend.identity_v5.directory import seed_users
        return next((u.get("team", "") for u in seed_users() if u["username"] == username), "")
    except Exception:  # noqa: BLE001
        return ""


def apply_set(*, store: Store, scope_key: str, book: str, filters: list[dict[str, Any]], label: str, metrics: list[dict[str, Any]],
              owner: str, team: str, approver: str) -> dict[str, Any]:
    spec = lens_spec(book, filters, label, metrics)
    team = team or team_of(owner)
    key = f"monitor:{scope_key}"
    cur = store.keyed("lens", key)
    change = f"Monitoring set approved by {approver}: {len(metrics)} metrics"
    if cur is None:
        lens = store.create(owner=owner, team=team, spec=spec, name=label, description="Built by the Monitoring agent from an approved monitoring set.",
                            tags=["monitoring-agent"], saved=True, template_key=key, change=change)
        created = True
        version = 1
    else:
        version = store.commit(cur["lens_id"], spec, change, approver)
        lens = store.lens(cur["lens_id"])
        created = False
    # the approver (and anyone who decided it) can open the lens the alerts link to; the owner's team sees it as saved
    if approver and approver != owner and not approver.startswith(("agent:", "approvals")):
        store.share(lens["lens_id"], "user", approver, owner)  # type: ignore[index]
    try:
        from backend.lenses_v5.seed import thumb
        store.update(lens["lens_id"], thumb=thumb(spec))  # type: ignore[index]
    except Exception:  # noqa: BLE001 - a thumbnail never blocks the approval
        pass
    return {"lens_id": lens["lens_id"], "created": created, "version": version, "tiles": len(spec["tiles"]), "kpis": spec["kpis"],  # type: ignore[index]
            "at": time.time()}
