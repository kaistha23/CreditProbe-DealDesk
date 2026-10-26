"""Lenses to Mail (share, refresh notes) and to Playbook (a report section with the lens figures).

Both calls carry the caller's own session cookie to the Core service (8505, Mail) and the Playbook service
(8506), as every v5 module does. A service that is down is reported as such.
"""
from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from typing import Any

from fastapi import HTTPException, Request

from backend.identity_v5.client import COOKIE
from backend.identity_v5.directory import seed_users


def _call(base: str, path: str, request: Request, body: dict | None = None, key: str = "", what: str = "") -> tuple[int, dict[str, Any]]:
    headers = {"Content-Type": "application/json"}
    token = request.cookies.get(COOKIE)
    if token:
        headers["Cookie"] = f"{COOKIE}={token}"
    if key:
        headers["Idempotency-Key"] = key[:80]
    req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None, headers=headers,
                                 method="POST" if body is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310 - v5 services on loopback
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode()).get("detail", "")
        except Exception:  # noqa: BLE001
            detail = ""
        if isinstance(detail, dict):
            detail = detail.get("message", "")
        raise HTTPException(e.code if e.code in (400, 401, 403, 404, 409, 413, 422) else 502, detail or f"{what} could not complete that request. Please try again in a moment.") from e
    except (urllib.error.URLError, OSError) as e:
        raise HTTPException(502, f"{what} is temporarily unavailable. The lens is saved; please try again in a moment.") from e


def core() -> str:
    return (os.environ.get("CORE_API_ORIGIN") or "http://127.0.0.1:8505").rstrip("/")


def playbook() -> str:
    return (os.environ.get("PLAYBOOK_API_ORIGIN") or "http://127.0.0.1:8506").rstrip("/")


def expand(users: list[str], teams: list[str], exclude: str = "") -> list[str]:
    known = {u["username"]: u for u in seed_users()}
    out = [u for u in users if u in known]
    for t in teams:
        out += [u["username"] for u in seed_users() if u["team"] == t]
    seen, res = set(), []
    for u in out:
        if u not in seen and u != exclude:
            seen.add(u)
            res.append(u)
    return res


def mail_object(lens: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    return {"type": "lens", "id": lens["lens_id"], "label": lens["name"][:200], "href": f"/lenses/{lens['lens_id']}",
            "summary": f"{spec.get('scope_label', '')} · {len(spec.get('tiles') or [])} tiles"[:300], "meta": {"book": spec["book"]}}


def mail_share(request: Request, users: list[str], note: str, obj: dict[str, Any]) -> dict[str, Any]:
    return _call(core(), "/api/v1/mail/share", request, {"to": users, "note": note[:4000], "objects": [obj]}, what="Mail")[1]


def playbook_reports(request: Request) -> dict[str, Any]:
    return _call(playbook(), "/api/v1/playbook/reports?status=draft&status=in_review&editable=true", request, what="Playbook")[1]


def source(lens: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    return {"type": "lens", "id": lens["lens_id"], "label": lens["name"][:200], "href": f"/lenses/{lens['lens_id']}",
            "summary": f"Lens on {spec.get('scope_label', '')} as of {spec.get('period', '')}", "meta": {"book": spec["book"], "period": spec.get("period", "")}}


_FMT = {"sar_mn": "sar", "pct": "pct", "bps": "bps", "count": "int", "ratio": "num", "score": "num", "days": "int"}


def _val(v: Any, unit: str) -> Any:
    if v is None:
        return None
    if unit == "sar_mn":
        return float(v) * 1e6
    if unit == "pct":
        return float(v) / 100
    return v


def section(lens: dict[str, Any], spec: dict[str, Any], r: dict[str, Any], png: bool = True) -> dict[str, Any]:
    """The lens as one Playbook section (PLAYBOOK_API.md contract v1): commentary, KPIs, charts, the top-names table."""
    from backend.lenses_v5.exports import figure_png
    blocks: list[dict[str, Any]] = [{"kind": "paragraph", "text": r["commentary"]["markdown"][:7900] or lens["name"]}]
    blocks.append({"kind": "kpis", "items": [{"label": k["label"][:80], "value": _val(k["value"], k["unit"]), "format": _FMT.get(k["unit"], "num")}
                                             for k in r["kpis"] if k["value"] is not None][:8]})
    for t in r["tiles"]:
        if t.get("error"):
            continue
        if t.get("figure") and len(blocks) < 40:
            b: dict[str, Any] = {"kind": "chart", "title": t["title"][:200], "figure": t["figure"], "note": f"Lens {lens['name']} · {r['period']}"}
            if png:
                try:
                    b["png_base64"] = base64.b64encode(figure_png(t["figure"], t["title"])).decode()
                except Exception:  # noqa: BLE001 - the Plotly figure travels anyway
                    pass
            blocks.append(b)
        elif t["type"] == "top_names" and t.get("table"):
            cols = [{"key": c["key"], "label": c["label"][:80], "format": _FMT.get(c["unit"], "text")} for c in t["table"]["columns"]]
            rows = [{c["key"]: _val(row.get(c["key"]), next(x["unit"] for x in t["table"]["columns"] if x["key"] == c["key"])) for c in cols}
                    for row in t["table"]["rows"][:50]]
            blocks.append({"kind": "table", "title": t["title"][:200], "columns": cols, "rows": rows})
    return {"title": f"{lens['name']} ({r['period']})", "position": "end", "blocks": blocks[:60]}


def playbook_import(request: Request, lens: dict[str, Any], spec: dict[str, Any], r: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {"source": source(lens, spec), "section": section(lens, spec, r)}
    if body.get("report_id"):
        payload["report_id"] = body["report_id"]
    else:
        nr = dict(body.get("new_report") or {})
        nr.setdefault("title", f"{lens['name']}: lens report")
        nr["template"] = nr.get("template") or "portfolio-review"
        nr.setdefault("book", spec["book"])
        payload["new_report"] = nr
    status, out = _call(playbook(), "/api/v1/playbook/imports", request, payload, key=f"lens-{lens['lens_id']}-{lens['head']}-{body.get('report_id') or 'new'}",
                        what="Playbook")
    return {"status": status, **out}
