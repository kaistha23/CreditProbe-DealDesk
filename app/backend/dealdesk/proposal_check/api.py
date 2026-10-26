"""R14 session p: the proposal-check API (prefix /api/v1/dealdesk), included in backend/dealdesk/api.py (# R14 routers).

    GET  /proposal-check/demo                                the demo pack: files, the answer key (K31 point 3)
    GET  /proposal-check/demo/{file}                         download a demo-pack file (Word / JSON)
    POST /proposal-check/upload?proposal_id=                 multipart Word upload; the deal is detected from the header block when not given
    POST /proposals/{pid}/proposal-check?demo=half|corrected run the check: an uploaded file, the demo file, or what is on file
    GET  /proposals/{pid}/proposal-check                     the last result for the deal (runs it on what is on file when none)
    GET  /proposals/{pid}/proposal-check/annotated.docx      the RM's Word with comments in the margin + the query list
    GET  /proposals/{pid}/proposal-check/queries.docx        the query list alone
    POST /proposals/{pid}/proposal-check/send-back           "Send back to RM": records the queries sent (body {to?, queries?: [n]})
    POST /proposal-check/batch                               "Check all pending proposals" (K33): ranked table, RM view; publishes dd_proposal_quality
    GET  /proposal-check/batch                               the last batch (runs it when none)
    GET  /proposal-check/batch.xlsx                          the batch table and the RM view in Excel
    POST /proposal-check/batch/send-all?rm=                  send every open query of one RM's proposals
    GET  /proposal-check/rm-quality                          RM averages from the latest check per deal in dd_proposal_quality (RM track record)
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, File, HTTPException, Query, UploadFile
from fastapi.responses import Response

from backend.dealdesk.house_style.bankform import ctx
from backend.dealdesk.proposal_check import annotate, batch, demo_pack, engine, store

PREFIX = "/api/v1/dealdesk"
router = APIRouter(prefix=PREFIX, tags=["dealdesk-proposal-check"])
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_ORIG: dict[str, tuple[bytes, str]] = {}


def public(res: dict[str, Any]) -> dict[str, Any]:
    """The result without its Data Domains rows; passes summarised."""
    out = {k: v for k, v in res.items() if k not in ("rows", "passes")}
    out["passes_n"] = len(res.get("passes", []))
    out["checks_n"] = len(res.get("defects", [])) + len(res.get("observations", [])) + out["passes_n"]
    out["sent"] = store.sent(res["proposal_id"])
    out["links"] = {"annotated": f"{PREFIX}/proposals/{res['proposal_id']}/proposal-check/annotated.docx",
                    "queries": f"{PREFIX}/proposals/{res['proposal_id']}/proposal-check/queries.docx"}
    return out


def _file(data: bytes, name: str, mime: str) -> Response:
    return Response(content=data, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{name}"'})


def _run_bytes(data: bytes, name: str, pid: str | None) -> dict[str, Any]:
    try:
        res = engine.check_docx(data, name, pid)
    except LookupError as e:
        raise HTTPException(422, str(e)) from None
    except ctx.NotFound as e:
        raise HTTPException(404, str(e).strip("'\"")) from None
    _ORIG[res["proposal_id"]] = (data, name)
    store.remember(res)
    store.publish(res["rows"])
    return res


@router.get("/proposal-check/demo")
def demo() -> dict[str, Any]:
    import json
    key = demo_pack.OUT / "answer_key.json"
    files = sorted(p.name for p in demo_pack.OUT.glob("*") if p.is_file()) if demo_pack.OUT.exists() else []
    return {"proposal_id": demo_pack.PID, "customer": demo_pack.NAME, "files": files,
            "half_baked": f"{PREFIX}/proposal-check/demo/{demo_pack.HALF}", "corrected": f"{PREFIX}/proposal-check/demo/{demo_pack.FIXED}",
            "answer_key": json.loads(key.read_text()) if key.exists() else None}


@router.get("/proposal-check/demo/{name}")
def demo_file(name: str) -> Response:
    p = demo_pack.OUT / name
    if "/" in name or ".." in name or not p.exists():
        raise HTTPException(404, f"No demo file {name}")
    return _file(p.read_bytes(), name, DOCX if name.endswith(".docx") else "application/json")


@router.post("/proposal-check/upload")
async def upload(file: UploadFile = File(...), proposal_id: str | None = Query(None)) -> dict[str, Any]:
    data = await file.read()
    if not (file.filename or "").lower().endswith(".docx"):
        raise HTTPException(415, "Upload the proposal as a Word file (.docx).")
    res = _run_bytes(data, file.filename or "proposal.docx", proposal_id)
    store.save_upload(res["proposal_id"], file.filename or "proposal.docx", data)
    return public(res)


@router.post("/proposals/{pid}/proposal-check")
async def check(pid: str, demo: str | None = Query(None, pattern="^(half|corrected)$"), file: UploadFile | None = File(None)) -> dict[str, Any]:
    if file is not None:
        data = await file.read()
        res = _run_bytes(data, file.filename or "proposal.docx", pid)
        store.save_upload(pid, file.filename or "proposal.docx", data)
        return public(res)
    if demo:
        name = demo_pack.HALF if demo == "half" else demo_pack.FIXED
        p = demo_pack.OUT / name
        if not p.exists():
            raise HTTPException(404, "The demo pack is not built (python -m backend.dealdesk.proposal_check.demo_pack).")
        return public(_run_bytes(p.read_bytes(), name, pid))
    return public(_on_file(pid))


NO_PROPOSAL = "No RM proposal on file for this deal yet."


def _on_file(pid: str, use_record: bool = False) -> dict[str, Any]:
    try:
        res = engine.check_record(pid, use_record=use_record)
    except engine.NoProposal:
        raise HTTPException(404, NO_PROPOSAL) from None
    except (ctx.NotFound, KeyError):  # never the raw backend message on screen (L7)
        raise HTTPException(404, NO_PROPOSAL) from None
    store.remember(res)
    return res


@router.get("/proposals/{pid}/proposal-check")
def last(pid: str, use: str | None = Query(None, pattern="^record$")) -> dict[str, Any]:
    if use == "record":  # R15 b (L7): "Use the submission record" on a deal with no RM paper
        return public(_on_file(pid, use_record=True))
    return public(store.last(pid) or _on_file(pid))


def _original(pid: str, res: dict[str, Any]) -> tuple[bytes, str] | None:
    if pid in _ORIG and _ORIG[pid][1] == res["document"]:
        return _ORIG[pid]
    up = store.latest_upload(pid)
    if up and up[1] == res["document"]:
        return up
    for p in (demo_pack.OUT / res["document"], engine.memo_path(pid)):
        if p is not None and p.exists() and p.name == res["document"]:
            return p.read_bytes(), p.name
    return None


@router.get("/proposals/{pid}/proposal-check/annotated.docx")
def annotated_docx(pid: str) -> Response:
    res = store.last(pid) or _on_file(pid)
    orig = _original(pid, res)
    data, name = annotate.annotated(*orig[:1], res) if orig else annotate.queries_docx(res)
    return _file(data, name, DOCX)


@router.get("/proposals/{pid}/proposal-check/queries.docx")
def queries_docx(pid: str) -> Response:
    data, name = annotate.queries_docx(store.last(pid) or _on_file(pid))
    return _file(data, name, DOCX)


@router.post("/proposals/{pid}/proposal-check/send-back")
def send_back(pid: str, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    res = store.last(pid) or _on_file(pid)
    pick = set(body.get("queries") or [q["n"] for q in res["queries"]])
    qs = [q for q in res["queries"] if q["n"] in pick]
    rec = store.send_back(pid, res["run_id"], qs, to=str(body.get("to") or res["rm"] or "RM"), by=str(body.get("by") or "credit reviewer"))
    sent_ids = {q["check"] for q in qs}
    rows = [r | {"status": "sent_to_rm", "checked_at": rec["at"]} for r in res["rows"] if r["result"] == "defect" and r["check"] in sent_ids]
    if rows:
        store.publish(rows, actor="p:send-back")
    return {"sent": rec, "message": f"{len(qs)} queries sent back to {rec['to']} on {rec['at'][:10]}."}


@router.post("/proposal-check/batch")
def batch_run() -> dict[str, Any]:
    return batch.run_all(publish=True)


@router.get("/proposal-check/batch")
def batch_last() -> dict[str, Any]:
    return batch.last() or batch.run_all(publish=False)


@router.get("/proposal-check/batch.xlsx")
def batch_xlsx() -> Response:
    b = batch.last() or batch.run_all(publish=False)
    data, name = annotate.batch_xlsx(b["table"], b["rm"])
    return _file(data, name, XLSX)


@router.post("/proposal-check/batch/send-all")
def batch_send_all(rm: str = Query(...)) -> dict[str, Any]:
    b = batch.last() or batch.run_all(publish=False)
    done = []
    for r in b["table"]:
        if r["rm"] == rm and r["queries_open"]:
            res = store.last(r["proposal_id"])
            if res:
                done.append(store.send_back(r["proposal_id"], res["run_id"], res["queries"], to=rm))
    return {"rm": rm, "proposals": len(done), "queries": sum(len(x["queries"]) for x in done),
            "message": f"{sum(len(x['queries']) for x in done)} queries on {len(done)} proposals sent to {rm}."}


@router.get("/proposal-check/rm-quality")
def rm_quality() -> dict[str, Any]:
    """Per RM: proposals checked, average proposal score and critical defects, from the latest proposal_score row per deal in
    dd_proposal_quality (what the governance RM track record reads, K33 -> #21)."""
    from backend.dealdesk.house_style.bankform import source as S
    last: dict[str, dict[str, Any]] = {}
    for r in S.read("dd_proposal_quality", check="proposal_score"):
        pid = str(r.get("proposal_id"))
        if pid not in last or str(r.get("checked_at") or "") > str(last[pid].get("checked_at") or ""):
            last[pid] = r
    by: dict[str, list[dict[str, Any]]] = {}
    for r in last.values():
        by.setdefault(str(r.get("rm") or "—"), []).append(r)
    rows = [{"rm": rm, "proposals": len(rs), "average_score": round(sum(float(x.get("score") or 0) for x in rs) / len(rs), 1),
             "defects": sum(int(x.get("defects_n") or 0) for x in rs), "deals": sorted(str(x.get("proposal_id")) for x in rs)} for rm, rs in by.items()]
    return {"source": "dd_proposal_quality (latest proposal_score per deal)", "rows": sorted(rows, key=lambda r: (r["average_score"], r["rm"]))}
