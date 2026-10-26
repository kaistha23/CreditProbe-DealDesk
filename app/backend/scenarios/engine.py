"""The scenario engine in one call: calibration, joint scenarios, satellite models, the book translation, and the
reproducibility record (relations with their hashes, package versions, code path). Deterministic: the same files
give the same numbers (the copula's draws use a fixed seed)."""
from __future__ import annotations

import functools
import hashlib
import platform
import subprocess
from importlib import metadata
from typing import Any

from backend.scenarios import VERSION, calibrate, data, joint, satellite, translate

CODE_PATH = ["backend/scenarios/data.py", "backend/scenarios/calibrate.py", "backend/scenarios/joint.py",
             "backend/scenarios/satellite.py", "backend/scenarios/translate.py", "backend/scenarios/ladder.py"]
PACKAGES = ("numpy", "pandas", "scipy", "pyarrow", "python-docx", "matplotlib")


def _sha(path: str) -> str:
    p = data.wpaths.V5 / path
    if not p.exists():
        return ""
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _git() -> str:
    try:
        return subprocess.run(["git", "-C", str(data.wpaths.V5), "rev-parse", "--short", "HEAD"], capture_output=True,
                              text=True, timeout=5).stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def reproducibility() -> dict[str, Any]:
    rels = [{"relation": rel, "file": path, "sha256_16": _sha(path)} for rel, path in data.RELATIONS.values()]
    pk = {}
    for p in PACKAGES:
        try:
            pk[p] = metadata.version(p)
        except metadata.PackageNotFoundError:
            pk[p] = "not installed"
    code = [{"file": c, "sha256_16": _sha(c)} for c in CODE_PATH]
    fp = hashlib.sha256("|".join([r["sha256_16"] for r in rels] + [c["sha256_16"] for c in code]).encode()).hexdigest()[:12]
    return {"engine_version": VERSION, "relations": rels, "packages": pk, "python": platform.python_version(),
            "code": code, "commit": _git(), "fingerprint": fp, "seed": joint.SEED, "draws": joint.N_DRAWS,
            "command": "python -m backend.scenarios.publish   (recomputes and republishes every relation)"}


def _slim_fit(f: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in f.items() if not k.startswith("_") and k not in ("fitted", "actual", "rows")}


@functools.lru_cache(maxsize=1)
def build() -> dict[str, Any]:
    cal = calibrate.calibrate_all()
    j = joint.build()
    fits = satellite.fit_all()
    tr = translate.by_severity()
    return {"version": VERSION, "window": data.window(), "limits": data.limits(), "calibration": cal, "joint": j,
            "satellite": {"pd": _slim_fit(fits["pd"]), "migration": _slim_fit(fits["migration"]), "backtest": fits["backtest"]},
            "translation": tr, "resolved_defaults": data.resolved_defaults(), "reproducibility": reproducibility(),
            "percentiles": {"mild": calibrate.P_MILD, "moderate": calibrate.P_MOD, "moderate_band": list(calibrate.P_MOD_BAND),
                            "severe": calibrate.P_SEV, "min_obs": calibrate.MIN_OBS, "rule_band": list(calibrate.RULE_BAND)}}


def reset() -> None:
    for fn in (build, calibrate.calibrate_all, calibrate.drivers_by_key, joint.build, joint.history, satellite.fit_all,
               satellite.panel, translate.by_severity, translate.book):
        fn.cache_clear()
