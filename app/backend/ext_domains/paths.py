"""Where the external (Bureau, Open Banking) domains live. Synthetic data."""
from __future__ import annotations

import os
import pathlib

V5 = pathlib.Path(__file__).resolve().parents[2]
SOURCE_LAKE = pathlib.Path(os.environ.get("EXT_SOURCE_LAKE") or V5 / "data" / "cockpit_v4_lake").resolve()
EXTERNAL = pathlib.Path(os.environ.get("EXT_DATASETS") or V5 / "data" / "external").resolve()
BUREAU = "bureau-saudi-v1"
OPEN_BANKING = "open-banking-saudi-v1"
SEED = 20261010
