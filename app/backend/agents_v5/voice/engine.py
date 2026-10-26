"""R16 v: the offline neural voices (Kokoro-82M for English, Piper ar_JO Kareem for Arabic), loaded lazily.

Everything runs on this computer with onnxruntime: no text and no audio leaves the machine. The add-on is optional:
`status()` reports what is installed without loading a model; `speak()` raises `NotInstalled` when the packages or the
model files are missing, and the API turns that into a 503 the frontend reads as "use the browser's voice, with a note".

Model files are looked up, in order, under `$CP_TTS_HOME`, `var/tts/` (the download script and the Mac pack put them
there) and `vendor/tts/`. Audio is cached as WAV under `var/tts_cache/` (or `$CP_TTS_CACHE`) by a hash of the engine,
model, voice, speed, pacing version and the spoken text, so a line is synthesised once.
"""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import threading
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.agents_v5.voice import cloud, pacing

V5 = Path(__file__).resolve().parents[3]

KOKORO_MODELS = ("kokoro-v1.0.onnx", "kokoro-v1.0.fp16.onnx", "kokoro-v1.0.int8.onnx")   # best first
KOKORO_VOICES = "voices-v1.0.bin"
PIPER_MODEL = "ar_JO-kareem-medium.onnx"
MAX_CHARS = 4000
CACHE_MAX_BYTES = 600 * 1024 * 1024
SPEED_RANGE = (0.5, 1.5)
#: Kareem reads slowly at his own pace (about 75 words a minute in a brief); 0.85 brings him to a natural pace at speed 1.
PIPER_BASE_LENGTH = 0.85


class NotInstalled(RuntimeError):
    """The add-on (a package or a model file) is not on this computer."""


@dataclass(frozen=True)
class Voice:
    id: str
    engine: str          # "kokoro" | "piper" (offline) | "azure" (R16 v2: optional cloud, off by default)
    name: str            # what the sampler shows
    lang: str            # BCP 47, e.g. en-US, en-GB, ar-JO
    group: str           # "en" | "ar-gulf" (the sampler's language)
    gender: str          # "male" | "female"
    accent: str
    note: str = ""

    @property
    def where(self) -> str:
        """R16 v2: "offline" (runs on this computer) or "cloud" (the text leaves the machine)."""
        return "cloud" if self.engine == "azure" else "offline"

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "engine": self.engine, "name": self.name, "lang": self.lang, "group": self.group,
                "gender": self.gender, "accent": self.accent, "note": self.note, "where": self.where,
                **({"label": cloud.LABEL} if self.where == "cloud" else {})}


#: The neural voices offered in Settings -> Voice. Male first (Anne asked for a calm male voice); female options after.
VOICES: tuple[Voice, ...] = (
    Voice("am_michael", "kokoro", "Michael", "en-US", "en", "male", "American", "warm, calm"),
    Voice("am_adam", "kokoro", "Adam", "en-US", "en", "male", "American", "deep, steady"),
    Voice("bm_george", "kokoro", "George", "en-GB", "en", "male", "British", "measured, mature"),
    Voice("bm_lewis", "kokoro", "Lewis", "en-GB", "en", "male", "British", "low, unhurried"),
    Voice("bm_daniel", "kokoro", "Daniel", "en-GB", "en", "male", "British", "clear, neutral"),
    Voice("bm_fable", "kokoro", "Fable", "en-GB", "en", "male", "British", "lively"),
    Voice("am_eric", "kokoro", "Eric", "en-US", "en", "male", "American", "plain, businesslike"),
    Voice("am_liam", "kokoro", "Liam", "en-US", "en", "male", "American", "young, friendly"),
    Voice("am_onyx", "kokoro", "Onyx", "en-US", "en", "male", "American", "very deep"),
    Voice("am_fenrir", "kokoro", "Fenrir", "en-US", "en", "male", "American", "firm"),
    Voice("am_echo", "kokoro", "Echo", "en-US", "en", "male", "American", "soft"),
    Voice("am_puck", "kokoro", "Puck", "en-US", "en", "male", "American", "bright"),
    Voice("af_heart", "kokoro", "Heart", "en-US", "en", "female", "American", "warm, the most natural"),
    Voice("af_bella", "kokoro", "Bella", "en-US", "en", "female", "American", "expressive"),
    Voice("af_nicole", "kokoro", "Nicole", "en-US", "en", "female", "American", "close, quiet"),
    Voice("af_sarah", "kokoro", "Sarah", "en-US", "en", "female", "American", "clear"),
    Voice("af_sky", "kokoro", "Sky", "en-US", "en", "female", "American", "light"),
    Voice("bf_emma", "kokoro", "Emma", "en-GB", "en", "female", "British", "composed"),
    Voice("bf_isabella", "kokoro", "Isabella", "en-GB", "en", "female", "British", "warm"),
    Voice("bf_alice", "kokoro", "Alice", "en-GB", "en", "female", "British", "crisp"),
    Voice("bf_lily", "kokoro", "Lily", "en-GB", "en", "female", "British", "gentle"),
    Voice("ar_JO-kareem-medium", "piper", "Kareem", "ar-JO", "ar-gulf", "male", "Levantine (Jordan)",
          "the only offline Arabic neural voice in Piper; there is no female ar_JO voice"),
    # R16 v2: regional voices no offline model covers (see cloud.py). Optional cloud, off by default, used only if chosen.
    Voice("azure:ar-SA-HamedNeural", "azure", "Hamed", "ar-SA", "ar-gulf", "male", "Saudi", "Azure neural, Saudi Arabic"),
    Voice("azure:ar-SA-ZariyahNeural", "azure", "Zariyah", "ar-SA", "ar-gulf", "female", "Saudi", "Azure neural, Saudi Arabic"),
    Voice("azure:ar-AE-HamdanNeural", "azure", "Hamdan", "ar-AE", "ar-gulf", "male", "UAE (Gulf)", "Azure neural, Emirati Arabic"),
    Voice("azure:ar-AE-FatimaNeural", "azure", "Fatima", "ar-AE", "ar-gulf", "female", "UAE (Gulf)", "Azure neural, Emirati Arabic"),
    Voice("azure:en-IN-PrabhatNeural", "azure", "Prabhat", "en-IN", "en", "male", "Indian", "Azure neural, Indian English"),
    Voice("azure:en-IN-NeerjaNeural", "azure", "Neerja", "en-IN", "en", "female", "Indian", "Azure neural, Indian English"),
)
BY_ID = {v.id: v for v in VOICES}

#: R16 v2: per regional variety, whether an offline neural model exists (checked against the Piper and Kokoro
#: catalogues on 21 Oct 2026; nothing is invented). Shown in Settings -> Voice as "why not offline".
OFFLINE_CATALOGUE: dict[str, str] = {
    "ar-SA": "No offline neural voice for Saudi Arabic: Piper's only Arabic voice is ar_JO Kareem; Kokoro has no Arabic.",
    "ar-AE": "No offline neural voice for Emirati (Gulf) Arabic: Piper's only Arabic voice is ar_JO Kareem; Kokoro has no Arabic.",
    "en-IN": "No offline neural voice for Indian English: Piper has en_GB and en_US only; Kokoro has American and British "
             "English (its Hindi voices speak Hindi, not Indian English).",
}


def homes() -> list[Path]:
    out = [Path(p) for p in [os.environ.get("CP_TTS_HOME", "")] if p]
    return out + [V5 / "var" / "tts", V5 / "vendor" / "tts"]


def find(name: str) -> Path | None:
    for h in homes():
        p = h / name
        if p.is_file() and p.stat().st_size > 0:
            return p
    return None


def kokoro_model() -> Path | None:
    pref = os.environ.get("CP_TTS_KOKORO_MODEL", "")
    for name in ([pref] if pref else []) + list(KOKORO_MODELS):
        p = find(name)
        if p:
            return p
    return None


def _has(mod: str) -> bool:
    try:
        return importlib.util.find_spec(mod) is not None
    except (ImportError, ValueError):
        return False


def status() -> dict[str, Any]:
    """What is installed (no model is loaded). `available` per engine; `missing` says what to install, in words."""
    if os.environ.get("CP_TTS_DISABLED") == "1":
        return {"available": False, "engines": {"kokoro": False, "piper": False, "azure": False},
                "missing": ["turned off (CP_TTS_DISABLED=1)"], "offline": True, "voices": [], "cloud": cloud.status(),
                "offline_catalogue": OFFLINE_CATALOGUE}
    missing: list[str] = []
    ort = _has("onnxruntime")
    k_pkg, p_pkg = _has("kokoro_onnx"), _has("piper")
    k_model, k_voices, p_model = kokoro_model(), find(KOKORO_VOICES), find(PIPER_MODEL)
    p_conf = find(PIPER_MODEL + ".json")
    if not ort:
        missing.append("the onnxruntime package")
    if not k_pkg:
        missing.append("the kokoro-onnx package")
    if not p_pkg:
        missing.append("the piper-tts package")
    if not k_model:
        missing.append("the Kokoro model (kokoro-v1.0.onnx or kokoro-v1.0.int8.onnx)")
    if not k_voices:
        missing.append(f"the Kokoro voices ({KOKORO_VOICES})")
    if not p_model or not p_conf:
        missing.append(f"the Piper Arabic voice ({PIPER_MODEL} and its .json)")
    eng = {"kokoro": bool(ort and k_pkg and k_model and k_voices), "piper": bool(ort and p_pkg and p_model and p_conf)}
    cst = cloud.status()
    why = {"kokoro": "The offline English add-on (Kokoro) is not installed here.",
           "piper": "The offline Arabic add-on (Piper) is not installed here.", "azure": cst["why"]}
    allv = eng | {"azure": bool(cst["configured"])}
    return {"available": any(eng.values()), "engines": allv, "missing": missing, "offline": True,
            "model": {"kokoro": k_model.name if k_model else None, "piper": PIPER_MODEL if p_model else None},
            "voices": [v.as_dict() | {"installed": allv[v.engine], "why": None if allv[v.engine] else why[v.engine]}
                       for v in VOICES],
            "cloud": cst, "offline_catalogue": OFFLINE_CATALOGUE,
            "how_to_install": "ops/r16_install_tts.sh (offline: wheels in vendor/wheels, models in var/tts)"}


# ------------------------------------------------------------------------------------------------ engines (lazy)

_LOCK = threading.RLock()
_KOKORO: Any = None
_PIPER: Any = None


def _kokoro() -> Any:
    global _KOKORO
    with _LOCK:
        if _KOKORO is None:
            model, voices = kokoro_model(), find(KOKORO_VOICES)
            if not (model and voices and _has("kokoro_onnx") and _has("onnxruntime")):
                raise NotInstalled("The English neural voice (Kokoro) is not installed on this computer.")
            from kokoro_onnx import Kokoro  # noqa: PLC0415 (optional add-on)
            _KOKORO = Kokoro(str(model), str(voices))
        return _KOKORO


def _piper() -> Any:
    global _PIPER
    with _LOCK:
        if _PIPER is None:
            model = find(PIPER_MODEL)
            if not (model and find(PIPER_MODEL + ".json") and _has("piper") and _has("onnxruntime")):
                raise NotInstalled("The Arabic neural voice (Piper) is not installed on this computer.")
            from piper import PiperVoice  # noqa: PLC0415 (optional add-on)
            _PIPER = PiperVoice.load(str(model), config_path=str(find(PIPER_MODEL + ".json")))
        return _PIPER


def _pcm16(samples: Any) -> bytes:
    import numpy as np  # noqa: PLC0415
    a = np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0)
    return (a * 32767.0).astype("<i2").tobytes()


def _silence(seconds: float, rate: int) -> bytes:
    return b"\x00\x00" * int(max(0.0, seconds) * rate)


def _wav(pcm: bytes, rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def _synth_kokoro(voice: Voice, parts: list[pacing.Sentence], speed: float) -> tuple[bytes, int]:
    k = _kokoro()
    rate = 24000
    lang = "en-gb" if voice.lang == "en-GB" else "en-us"
    out = bytearray(_silence(0.08, rate))
    for s in parts:
        samples, rate = k.create(s.text, voice=voice.id, speed=speed, lang=lang, sentence_pause=0.0, clause_pause=0.16)
        out += _pcm16(samples) + _silence(s.pause, rate)
    return bytes(out), rate


def _synth_piper(parts: list[pacing.Sentence], speed: float) -> tuple[bytes, int]:
    from piper import SynthesisConfig  # noqa: PLC0415
    v = _piper()
    rate = int(v.config.sample_rate)
    cfg = SynthesisConfig(length_scale=round(PIPER_BASE_LENGTH / speed, 3), noise_scale=0.6, noise_w_scale=0.75)
    out = bytearray(_silence(0.08, rate))
    for s in parts:
        for chunk in v.synthesize(s.text, cfg):
            out += chunk.audio_int16_bytes
        out += _silence(s.pause, rate)
    return bytes(out), rate


# ------------------------------------------------------------------------------------------------ cache + speak

def cache_dir() -> Path:
    p = Path(os.environ.get("CP_TTS_CACHE") or (V5 / "var" / "tts_cache"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def clean_speed(speed: Any) -> float:
    try:
        x = float(speed)
    except (TypeError, ValueError):
        x = 1.0
    return round(min(SPEED_RANGE[1], max(SPEED_RANGE[0], x)), 2)


def voice_for(voice_id: str | None, lang: str | None) -> Voice:
    if voice_id and voice_id in BY_ID:
        return BY_ID[voice_id]
    if voice_id:
        raise ValueError(f"Unknown neural voice: {voice_id[:40]}.")
    return BY_ID["ar_JO-kareem-medium"] if str(lang or "").startswith("ar") else BY_ID["am_michael"]


def cache_key(voice: Voice, speed: float, spoken: list[pacing.Sentence]) -> str:
    model = ("azure" if voice.engine == "azure"
             else kokoro_model().name if voice.engine == "kokoro" and kokoro_model() else PIPER_MODEL)
    blob = json.dumps([pacing.PACING_VERSION, voice.engine, model, voice.id, speed, PIPER_BASE_LENGTH if voice.engine == "piper" else 1,
                       [(s.text, s.pause) for s in spoken]], ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def speak(text: str, voice_id: str | None = None, lang: str | None = None, speed: Any = 1.0) -> dict[str, Any]:
    """WAV bytes for `text`: {audio, key, cached, voice, seconds, spoken}. Raises ValueError, NotInstalled."""
    text = str(text or "").strip()
    if not text:
        raise ValueError("Nothing to say.")
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS]
    voice = voice_for(voice_id, lang)
    spd = clean_speed(speed)
    spoken = pacing.sentences(text, "ar" if voice.group == "ar-gulf" else "en")
    if not spoken:
        raise ValueError("Nothing to say.")
    key = cache_key(voice, spd, spoken)
    path = cache_dir() / f"{key}.wav"
    if path.is_file():
        audio = path.read_bytes()
        try:
            os.utime(path)
        except OSError:
            pass
        return {"audio": audio, "key": key, "cached": True, "voice": voice.id, "spoken": [s.text for s in spoken]}
    t0 = time.monotonic()
    if voice.engine == "azure":   # R16 v2: only ever reached when this cloud voice's id was asked for explicitly
        try:
            audio = cloud.synthesize(spoken, voice.lang, voice.id, spd)
        except cloud.CloudOff as e:
            raise NotInstalled(str(e)) from None
        _store(path, audio)
        return {"audio": audio, "key": key, "cached": False, "voice": voice.id, "spoken": [s.text for s in spoken],
                "took": round(time.monotonic() - t0, 2), "where": "cloud"}
    with _LOCK:
        pcm, rate = _synth_piper(spoken, spd) if voice.engine == "piper" else _synth_kokoro(voice, spoken, spd)
    audio = _wav(pcm, rate)
    _store(path, audio)
    return {"audio": audio, "key": key, "cached": False, "voice": voice.id, "spoken": [s.text for s in spoken],
            "seconds": round(len(pcm) / 2 / rate, 2), "took": round(time.monotonic() - t0, 2)}


def _store(path: Path, audio: bytes) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(audio)
    tmp.replace(path)
    _prune()


def _prune() -> None:
    """Keep the cache under CACHE_MAX_BYTES (least recently played first out)."""
    try:
        files = sorted(cache_dir().glob("*.wav"), key=lambda p: p.stat().st_mtime)
        total = sum(p.stat().st_size for p in files)
        while files and total > CACHE_MAX_BYTES:
            p = files.pop(0)
            total -= p.stat().st_size
            p.unlink(missing_ok=True)
    except OSError:
        pass


def reset_for_tests() -> None:
    global _KOKORO, _PIPER
    with _LOCK:
        _KOKORO = _PIPER = None
