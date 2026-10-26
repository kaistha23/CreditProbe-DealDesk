"""R16 v: Noor's human-sounding voice, an OFFLINE neural text-to-speech add-on served by the Deal Desk service.

English: Kokoro-82M (ONNX, `kokoro-onnx`); Arabic: Piper (ar_JO Kareem, `piper-tts`). Both run on this computer with
onnxruntime; no text leaves the machine. The add-on is optional: with its packages or model files absent the API says
so (`/api/v1/voice/status`) and the browser's own voice reads instead, with a note.

    pacing.py   text -> what is spoken: numbers as words ("SAR 1.48 bn" -> "one point four eight billion riyals"),
                short sentences, pauses at commas and full stops
    engine.py   the two engines, loaded lazily; WAV out; a cache by text hash under var/tts_cache
    api.py      GET /api/v1/voice/status, GET /api/v1/voice/voices, POST /api/v1/voice/speak
"""
