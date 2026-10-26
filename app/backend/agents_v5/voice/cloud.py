"""R16 v2: the OPTIONAL cloud voice provider (Azure Speech), for regional voices no offline model covers.

Off by default. It is configured only when both `CP_TTS_CLOUD_KEY` and `CP_TTS_CLOUD_REGION` are set in the Deal Desk
service's environment (the key is never logged, returned or written anywhere). Even then a cloud voice is used only
when its id (`azure:<ShortName>`) is asked for explicitly: by a Listen click on its row in Settings -> Voice, or because
an administrator chose it for a language. It is never a default and never a fallback (engine.voice_for).

The text of the line spoken is sent to Microsoft's speech service in the configured region, so the sampler labels
every cloud row "Cloud – text leaves the machine; demo with fictional data only".

Why these voices: no offline neural model exists for Saudi Arabic, Emirati (Gulf) Arabic or Indian English in the
Piper catalogue (Arabic is ar_JO Kareem only; English is en_GB and en_US only) or in Kokoro v1.0 (American and British
English, Spanish, French, Hindi, Italian, Brazilian Portuguese, Japanese, Mandarin; no Arabic, no Indian English).
Checked 21 Oct 2026 against rhasspy/piper VOICES.md, OHF-Voice/piper1-gpl docs/VOICES.md and hexgrad/kokoro
pipeline.py (LANG_CODES).
"""
from __future__ import annotations

import os
import urllib.error
import urllib.request
from typing import Any
from xml.sax.saxutils import escape

from backend.agents_v5.voice import pacing

PROVIDER = "Azure Speech"
LABEL = "Cloud – text leaves the machine; demo with fictional data only"
PREFIX = "azure:"
TIMEOUT_S = 20
OUTPUT_FORMAT = "riff-24khz-16bit-mono-pcm"


class CloudOff(RuntimeError):
    """The cloud provider is not configured (no key or region) or could not be reached."""


def configured() -> bool:
    return bool(os.environ.get("CP_TTS_CLOUD_KEY", "").strip() and os.environ.get("CP_TTS_CLOUD_REGION", "").strip())


def region() -> str:
    r = os.environ.get("CP_TTS_CLOUD_REGION", "").strip().lower()
    return "".join(ch for ch in r if ch.isalnum())[:32]


def status() -> dict[str, Any]:
    """Whether the cloud voices can play here. Never includes the key."""
    on = configured()
    return {"provider": PROVIDER, "configured": on, "region": region() if on else None, "label": LABEL,
            "why": None if on else "Cloud voices are off: CP_TTS_CLOUD_KEY and CP_TTS_CLOUD_REGION are not set for the "
                                   "Deal Desk service (off by default).",
            "how_to_enable": "Set CP_TTS_CLOUD_KEY (an Azure Speech key) and CP_TTS_CLOUD_REGION (e.g. uaenorth) in the "
                             "Deal Desk service's environment and restart it. Demo with fictional data only."}


def short_name(voice_id: str) -> str:
    return voice_id[len(PREFIX):] if voice_id.startswith(PREFIX) else voice_id


def ssml(parts: list[pacing.Sentence], lang: str, name: str, speed: float) -> str:
    """The SSML Azure reads: our paced sentences, our pauses, the speed as a prosody rate."""
    pct = round((speed - 1.0) * 100)
    body = "".join(f"{escape(s.text)}<break time=\"{int(round(s.pause * 1000))}ms\"/>" for s in parts)
    return (f"<speak version=\"1.0\" xmlns=\"http://www.w3.org/2001/10/synthesis\" xml:lang=\"{escape(lang)}\">"
            f"<voice name=\"{escape(name)}\"><prosody rate=\"{pct:+d}%\">{body}</prosody></voice></speak>")


def synthesize(parts: list[pacing.Sentence], lang: str, voice_id: str, speed: float, opener: Any = None) -> bytes:
    """WAV bytes (24 kHz mono) from Azure Speech. Raises CloudOff when not configured or the service fails."""
    if not configured():
        raise CloudOff("Cloud voices are off here (CP_TTS_CLOUD_KEY / CP_TTS_CLOUD_REGION not set).")
    url = f"https://{region()}.tts.speech.microsoft.com/cognitiveservices/v1"
    req = urllib.request.Request(url, data=ssml(parts, lang, short_name(voice_id), speed).encode("utf-8"), method="POST",
                                 headers={"Ocp-Apim-Subscription-Key": os.environ["CP_TTS_CLOUD_KEY"].strip(),
                                          "Content-Type": "application/ssml+xml",
                                          "X-Microsoft-OutputFormat": OUTPUT_FORMAT, "User-Agent": "CreditProbe-v5"})
    try:
        with (opener or urllib.request.urlopen)(req, timeout=TIMEOUT_S) as r:
            audio = r.read()
    except urllib.error.HTTPError as e:
        raise CloudOff(f"The cloud speech service refused the request ({e.code}).") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise CloudOff("The cloud speech service could not be reached from this computer.") from None
    if not audio.startswith(b"RIFF"):
        raise CloudOff("The cloud speech service did not return audio.")
    return audio
