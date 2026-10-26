"""Noor's introduction tour (PLAN_R14 session t, K36/K36a), mounted on the Deal Desk service beside Noor's brief.

    GET /api/v1/tour/script?lang=en|ar&persona=   the whole tour: steps (route, selectors, action, caption, voice,
                                                 duration), the facts every figure came from, and the claims audit
    GET /api/v1/tour/facts                       the live numbers alone, each with its source stamp
    GET /api/v1/tour/health

Deterministic (N4): no model is called; same data, same script. The brief lines in step 3 are the reader's own brief
(persona from their role; administrators and demo accounts may pass `persona`, as for the brief).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request

from backend.agents_v5.tour import facts as F
from backend.agents_v5.tour import script as S

router = APIRouter(prefix="/api/v1/tour", tags=["tour"])


def _persona(request: Request, asked: str) -> str:
    try:
        from backend.agents_v5.brief.api import _persona as brief_persona, _who
        return brief_persona(_who(request), asked)
    except Exception:  # noqa: BLE001
        return asked or "cro"


@router.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "version": S.VERSION, "steps": len(S.STEPS)}


@router.get("/script")
def get_script(request: Request, lang: str = Query("en"), persona: str = Query("")) -> dict[str, Any]:
    p = _persona(request, persona)
    brief = None
    try:
        from backend.agents_v5.brief import service
        brief = service.brief(persona=p, user=_user(request), top=5)
    except Exception:  # noqa: BLE001 - the brief clauses are dropped, the tour still plays
        brief = None
    out = S.script(lang=lang, persona=p, brief=brief)
    out["persona"] = p
    return out


@router.get("/facts")
def get_facts() -> dict[str, Any]:
    fs = F.collect()
    return {"facts": {k: v.public() for k, v in sorted(fs.items())}, "n": len(fs)}


def _user(request: Request) -> dict[str, Any]:
    try:
        from backend.agents_v5.brief.api import _who
        return _who(request)
    except Exception:  # noqa: BLE001
        return {}
