"""R13 IB routes: renewal autopilot (prefix /api/v1/dealdesk/intel/renewals).

  GET  /renewals                    ?days=90&cls=all|clean|exception&q=&sector=&limit=&offset=&ref_date=   the queue
  GET  /renewals/criteria           the clean/exception criteria (id, label, operator, threshold, source, kind)
  GET  /renewals/{fid}              the prepared annual review + the one-page note (clean) or the paper action (exception)
  GET  /renewals/{fid}/note.md      the one-page note, Markdown
  GET  /renewals/{fid}/note.docx    the one-page note, Word (house-style renderer)
  POST /renewals/{fid}/paper        exception: the full R12 paper on the deal's file (opens the renewal file if needed)

Mounted by one line in the "# R13 routers" block of backend/dealdesk/api.py. Additive only (N1).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse, Response

from backend.dealdesk.intel.renewal import criteria, pack, queue

PREFIX = "/api/v1/dealdesk/intel/renewals"
router = APIRouter(prefix=PREFIX, tags=["dealdesk-intel-renewal"])


def _user(request: Request) -> str:
    try:
        from backend.identity_v5.client import current_user
        u = current_user(request) or {}
        return u.get("display_name") or u.get("username") or "Renewal autopilot"
    except Exception:  # noqa: BLE001
        return "Renewal autopilot"


def _err(fn, *a: Any, **k: Any) -> Any:
    try:
        return fn(*a, **k)
    except KeyError as e:
        raise HTTPException(404, f"No facility {e.args[0]} in the Book.") from None
    except LookupError as e:
        raise HTTPException(409, str(e)) from None
    except ValueError as e:
        raise HTTPException(422, str(e)) from None


@router.get("")
def get_queue(days: int = Query(pack.WINDOW_DAYS, ge=1, le=366), cls: str = "all", q: str = "", sector: str = "",
              limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0), ref_date: str | None = None,
              scope: str = Query("material", pattern="^(material|all)$")) -> dict[str, Any]:
    return _err(queue.queue, days, cls, q, sector, limit, offset, ref_date, scope)


@router.get("/criteria")
def get_criteria() -> dict[str, Any]:
    return {"criteria": criteria.describe(), "rule": "Exception when any credit criterion fires; commercial criteria become renewal conditions on the note."}


@router.get("/{fid}")
def get_item(fid: str, ref_date: str | None = None) -> dict[str, Any]:
    return _err(queue.item, fid, ref_date)


@router.get("/{fid}/note.md", response_class=PlainTextResponse)
def get_note_md(fid: str, ref_date: str | None = None) -> str:
    it = _err(queue.item, fid, ref_date)
    if "note" not in it:
        raise HTTPException(409, f"{fid} is an exception: it gets the full paper, not a one-page note.")
    return it["note"]["markdown"]


@router.get("/{fid}/note.docx")
def get_note_docx(fid: str, ref_date: str | None = None) -> Response:
    data, name = _err(queue.note_docx, fid, ref_date)
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.post("/{fid}/paper")
def post_paper(fid: str, request: Request, ref_date: str | None = None) -> dict[str, Any]:
    return _err(queue.paper, fid, _user(request), ref_date)
