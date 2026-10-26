"""R16 v: the neural voice API, mounted on the Deal Desk service (one line in its `# R16 routers` block).

    GET  /api/v1/voice/status    what is installed: {available, engines: {kokoro, piper}, missing, voices}
    GET  /api/v1/voice/voices    the neural voices for Settings -> Voice (with `installed`)
    POST /api/v1/voice/speak     {text, voice?, lang?, speed?} -> audio/wav (cached by text hash);
                                 503 {available: false, reason} when the add-on is not installed

Speech is synthesised on this computer (onnxruntime); the text never leaves it. Nothing here speaks on its own: the
frontend calls `speak` only from a click on a speaker or a Listen button (R16 M1).

R16 v2: a cloud voice (`azure:…`, Saudi / Emirati Arabic, Indian English) is spoken only when its id is sent
explicitly and the service has CP_TTS_CLOUD_KEY / CP_TTS_CLOUD_REGION; its text then goes to Azure Speech
(`X-Voice-Where: cloud`). Off by default: 503 with the reason.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import JSONResponse, Response

from backend.agents_v5.voice import engine

router = APIRouter(prefix="/api/v1/voice", tags=["voice"])


@router.get("/status")
def get_status() -> dict[str, Any]:
    return engine.status()


@router.get("/voices")
def get_voices() -> dict[str, Any]:
    st = engine.status()
    return {"available": st["available"], "engines": st["engines"], "voices": st["voices"]}


@router.post("/speak")
def post_speak(body: dict[str, Any] = Body(default={})) -> Response:
    text = body.get("text")
    if not isinstance(text, str) or not text.strip():
        raise HTTPException(422, "text: what Noor should say.")
    try:
        out = engine.speak(text, voice_id=body.get("voice") or None, lang=body.get("lang") or None,
                           speed=body.get("speed", 1.0))
    except engine.NotInstalled as e:
        return JSONResponse({"available": False, "reason": str(e), "missing": engine.status()["missing"]}, status_code=503)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    return Response(content=out["audio"], media_type="audio/wav",
                    headers={"X-Voice-Cache": "hit" if out["cached"] else "miss", "X-Voice-Key": out["key"],
                             "X-Voice-Id": out["voice"], "X-Voice-Where": out.get("where", "offline"),
                             "Cache-Control": "private, max-age=86400"})
