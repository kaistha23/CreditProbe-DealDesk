"""Where the Core service keeps its state. Movable by environment variable."""
from __future__ import annotations

import os
import pathlib

V5 = pathlib.Path(__file__).resolve().parents[2]


def store_path() -> pathlib.Path:
    """The Core sqlite store (users, sessions, audit, mail). Read on every call so a test can point elsewhere."""
    return pathlib.Path(os.environ.get("CORE_STORE") or V5 / "var" / "core" / "core.sqlite").expanduser().resolve()


def files_dir() -> pathlib.Path:
    return store_path().parent / (store_path().stem + "_files")


def users_local_path() -> pathlib.Path:
    """Initial passwords. Outside the repository, so it can never be committed."""
    env = os.environ.get("CP_USERS_LOCAL")
    if env:
        return pathlib.Path(env).expanduser().resolve()
    return pathlib.Path.home() / "CreditProbe_Workspace" / "USERS_LOCAL.md"


UI_ORIGINS = [o.strip() for o in (os.environ.get("WORKSPACE_CORS_ORIGINS")
                                  or "http://127.0.0.1:5500,http://localhost:5500").split(",") if o.strip()]
