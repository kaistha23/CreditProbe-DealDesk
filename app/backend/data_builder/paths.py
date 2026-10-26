"""Where the Data Builder service reads and listens -- in one place.

The service reads only files under `<v5>/data` (override with
DATA_BUILDER_ROOT for a test checkout); it writes nothing.
"""
from __future__ import annotations

import os
import pathlib

V5 = pathlib.Path(os.environ.get("DATA_BUILDER_ROOT") or pathlib.Path(__file__).resolve().parents[2]).resolve()
DATA = (V5 / "data").resolve()

API_PORT = int(os.environ.get("DATA_BUILDER_PORT") or 8504)
UI_ORIGINS = [o.strip() for o in (os.environ.get("DATA_BUILDER_CORS_ORIGINS")
                                  or "http://127.0.0.1:5500,http://localhost:5500").split(",")
              if o.strip()]

__all__ = ["API_PORT", "DATA", "UI_ORIGINS", "V5"]
