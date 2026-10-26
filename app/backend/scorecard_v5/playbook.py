"""The hand-off into Playbook (docs/v5/PLAYBOOK_API.md, contract v1).

A validation becomes one section of a report: a conclusion paragraph, key figures, the red / amber / green
verdict table, the main tables and charts (Plotly figure plus a PNG), a callout for what needs action, and the
Word validation report attached. `import_section` sends it with the caller's own session cookie; the service
on 8506 does the rest. A service that is down is reported as such, never as a stack trace.
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
from backend.scorecard_v5 import report_docx

FORMAT_MAP = {"pct": "pct", "pct2": "pct", "num": "num", "num4": "num4", "int": "int", "text": "text", "rag": "text"}
KEY_TABLES = {"disc_segment", "cal_grade", "cal_period", "csi_var", "var_table", "ovr_outcome"}
KEY_CHARTS = ["roc", "cap", "gini_trend", "oe_grade", "oe_trend", "psi_trend", "csi_bar", "score_dist", "iv_bar", "ovr_outcome"]
WORD = {"green": "green", "amber": "amber", "red": "red"}


def base() -> str:
    return (os.environ.get("PLAYBOOK_API_ORIGIN") or "http://127.0.0.1:8506").rstrip("/")


def _call(path: str, request: Request, body: dict | None = None, key: str = "") -> tuple[int, dict[str, Any]]:
    headers = {"Content-Type": "application/json"}
    token = request.cookies.get(COOKIE)
    if token:
        headers["Cookie"] = f"{COOKIE}={token}"
    if key:
        headers["Idempotency-Key"] = key[:80]
    req = urllib.request.Request(base() + path, data=json.dumps(body).encode() if body is not None else None, headers=headers,
                                 method="POST" if body is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310 - the Playbook service on loopback
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode()).get("detail", "")
        except Exception:  # noqa: BLE001
            detail = ""
        raise HTTPException(e.code if e.code in (400, 401, 403, 404, 413, 422) else 502, detail or "Playbook could not complete that request. Please try again in a moment.") from e
    except (urllib.error.URLError, OSError) as e:
        raise HTTPException(502, "Playbook is temporarily unavailable. The validation is saved; please add it to a report in a moment.") from e


def reports(request: Request) -> dict[str, Any]:
    return _call("/api/v1/playbook/reports?status=draft&status=in_review&editable=true", request)[1]


def source(v: dict[str, Any]) -> dict[str, Any]:
    sc = v["result"]["scorecard"]
    s = v["result"]["summary"]
    c = s["counts"]
    return {"type": "scorecard-validation", "id": v["validation_id"], "label": v["title"][:200], "href": f"/scorecard-validation?validation={v['validation_id']}",
            "summary": f"{c['green']} green, {c['amber']} amber, {c['red']} red tests; overall {s['overall']}.",
            "meta": {"book": sc["book"], "period": v["as_of"], "scorecard": sc["scorecard_id"]}}


def section(v: dict[str, Any], png: bool = True) -> dict[str, Any]:
    res = v["result"]
    sc = res["scorecard"]
    s = res["summary"]
    smp = res["sample"]
    tests = {x["id"]: x for sec in res["sections"] for x in sec["tests"]}
    review = v["review"]
    concl = report_docx.CONCLUSIONS.get(review.get("conclusion", ""), "")
    blocks: list[dict[str, Any]] = [{"kind": "paragraph", "text": (
        f"The **{sc['name']} v{sc['version']}** was validated as of {v['as_of']}: {s['counts']['green']} tests green, {s['counts']['amber']} amber, "
        f"{s['counts']['red']} red, on {smp['monitoring']['n']:,} monitoring observations and {smp['monitoring']['defaults']:,} defaults "
        f"({smp['monitoring']['from']} to {smp['monitoring']['to']})." + (f" Reviewer conclusion: **{concl}**." if concl else " The validation is pending review."))}]
    kp = []
    for tid, label in (("gini", "Gini"), ("ks", "KS"), ("oe_ratio", "Observed / expected"), ("psi", "Score PSI")):
        x = tests.get(tid)
        if x and isinstance(x["value"], (int, float)):
            kp.append({"label": label, "value": x["value"], "format": FORMAT_MAP.get(x["format"], "num"), "status": x["status"] if x["status"] in WORD else None})
    kp.append({"label": "Red tests", "value": s["counts"]["red"], "format": "int", "status": "red" if s["counts"]["red"] else "green"})
    blocks.append({"kind": "kpis", "items": [{k: v_ for k, v_ in i.items() if v_ is not None} for i in kp]})
    rag = []
    for x in tests.values():
        if x["status"] not in WORD:
            continue
        val = x["value"]
        fmt = FORMAT_MAP.get(x["format"], "num")
        comment = x["comment"]
        if not isinstance(val, (int, float)) or isinstance(val, bool):
            # PLAYBOOK_API.md 3.2: a verdict's value is a number or null; a worded result
            # ("3 red, 0 amber of 8") travels in the comment so nothing is lost.
            comment = f"{val}. {comment}".strip(". ") if val not in (None, "") else comment
            val, fmt = None, "text"
        rag.append({"test": x["label"][:200], "value": val, "format": fmt, "threshold": x["threshold"][:300], "status": x["status"], "comment": comment[:600]})
    blocks.append({"kind": "rag", "title": "Test verdicts", "items": rag[:60]})
    if res["findings"]:
        red = [f for f in res["findings"] if f["status"] == "red"]
        blocks.append({"kind": "callout", "tone": "critical" if red else "warning",
                       "text": ("Needs action: " + "; ".join(f"{f['label']}" for f in res["findings"][:6]) + ".")[:2000]})
    for sec in res["sections"]:
        for t in sec["tables"]:
            if t["id"] in KEY_TABLES:
                cols = [{"key": c["key"], "label": c["label"], "format": FORMAT_MAP.get(c["format"], "text")} for c in t["columns"]][:30]
                rows = [{c["key"]: (str(r.get(c["key"], "")).upper() if c["format"] == "rag" else r.get(c["key"])) for c in t["columns"]} for r in t["rows"][:500]]
                blocks.append({"kind": "table", "title": t["title"], "columns": cols, "rows": rows, "note": t.get("note", "")})
    charts = {c["id"]: c for sec in res["sections"] for c in sec["charts"]}
    for cid in KEY_CHARTS:
        c = charts.get(cid)
        if c:
            b: dict[str, Any] = {"kind": "chart", "title": c["title"], "figure": c["figure"], "note": c.get("note", "")}
            if png:
                b["png_base64"] = base64.b64encode(report_docx.figure_png(c["figure"])).decode()
            blocks.append(b)
    return {"title": f"{sc['name']}: validation as of {v['as_of']}", "position": "end", "blocks": blocks}


def import_section(request: Request, v: dict[str, Any], body: dict[str, Any], docx: bytes | None) -> dict[str, Any]:
    payload: dict[str, Any] = {"source": source(v), "section": section(v)}
    if body.get("report_id"):
        payload["report_id"] = body["report_id"]
    else:
        nr = dict(body.get("new_report") or {})
        nr.setdefault("title", f"{v['result']['scorecard']['name']}: validation {v['as_of']}")
        nr["template"] = nr.get("template") or "validation-report"
        nr.setdefault("book", v["result"]["scorecard"]["book"])
        payload["new_report"] = nr
    if docx:
        payload["attachment"] = {"name": f"{v['validation_id']}.docx", "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                 "file_base64": base64.b64encode(docx).decode()}
    status, out = _call("/api/v1/playbook/imports", request, payload, key=f"scorecard-{v['validation_id']}-{body.get('report_id') or 'new'}")
    return {"status": status, **out}
