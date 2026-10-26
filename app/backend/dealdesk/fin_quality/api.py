"""R13 Session Q routes: the financial-quality detector (prefix /api/v1/dealdesk/fin-quality).

  GET  /book/{fid}            a back-book facility up for renewal (the Book renewal row)
  GET  /book?ids=F1,F2        compact summaries for several Book rows (grade, flagged, top 3)
  GET  /{pid}                 a deal: grade A-D, every signal with number, threshold, source relation and period
  GET  /{pid}/paragraph       the "Financial quality" sentences of the synopsis and the committee paper
  POST /{pid}/publish         flagged signals and the grade -> dd_review_finding (category financial_quality)

Mounted by one line in the "# R12 routers" block of backend/dealdesk/api.py. Additive only (N1).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from backend.dealdesk.fin_quality import engine as E
from backend.dealdesk.fin_quality import publishing as PB

PREFIX = "/api/v1/dealdesk/fin-quality"
router = APIRouter(prefix=PREFIX, tags=["dealdesk-fin-quality"])


def _known(pid: str) -> bool:
    from backend.dealdesk.review2 import publish as P
    return bool(P.read("dd_deal", columns=["proposal_id"], proposal_id=pid))


@router.get("/book/{fid}")
def book_one(fid: str) -> dict[str, Any]:
    try:
        return E.assess_book(fid)
    except KeyError:
        raise HTTPException(404, f"No facility {fid} in the Book") from None


@router.get("/book")
def book_many(ids: str = Query("", description="comma-separated facility ids")) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for fid in [x.strip() for x in ids.split(",") if x.strip()][:100]:
        try:
            out[fid] = E.summary(E.assess_book(fid))
        except KeyError:
            out[fid] = None
    return {"items": out}


@router.get("/{pid}")
def deal(pid: str) -> dict[str, Any]:
    if not _known(pid):
        raise HTTPException(404, f"No deal {pid} in dd_deal")
    return E.assess(pid)


@router.get("/{pid}/paragraph")
def paragraph(pid: str) -> dict[str, Any]:
    if not _known(pid):
        raise HTTPException(404, f"No deal {pid} in dd_deal")
    return {"proposal_id": pid, "heading": "Financial quality", "sentences": E.paragraph(pid)}


@router.post("/{pid}/publish")
def publish(pid: str) -> dict[str, Any]:
    if not _known(pid):
        raise HTTPException(404, f"No deal {pid} in dd_deal")
    return PB.publish(pid)
