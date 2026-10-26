"""Where the Deal Desk thread layer reads, writes and listens."""
from __future__ import annotations

import os
import pathlib

V5 = pathlib.Path(__file__).resolve().parents[2]


def _path(var: str, default: pathlib.Path) -> pathlib.Path:
    return pathlib.Path(os.environ.get(var) or default).expanduser().resolve()


def store() -> pathlib.Path:
    return _path("DEALDESK_THREAD_STORE", V5 / "var" / "dealdesk" / "dealdesk_threads.sqlite")


API_PORT = int(os.environ.get("DEALDESK_API_PORT") or 8508)
UI_ORIGINS = [o.strip() for o in (os.environ.get("DEALDESK_CORS_ORIGINS")
                                  or "http://127.0.0.1:5500,http://localhost:5500").split(",") if o.strip()]
