"""R14 x: regenerate the R10 Deal Desk build files after a merge conflict on them.

    .venv/bin/python ops/r14_x_dd_regen.py

Builds the Deal Desk domain into a scratch folder (as `ops/dealdesk_build.py --check` does) and copies only the
R10 priced-result files the build writes under `dd-saudi-v1/` and `manifest.json` into `data/dealdesk`. Unlike
`ops/dealdesk_build.py` without `--check`, it never deletes `data/dealdesk/dd-saudi-v1` (which also holds every
R12-R14 relation). Afterwards `ops/dealdesk_build.py --check` passes by construction.
"""
from __future__ import annotations

import pathlib
import shutil
import sys
import tempfile

V5 = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V5))
sys.path.insert(0, str(V5 / "ops"))

import dealdesk_build  # noqa: E402
from backend.dealdesk import paths  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory() as d:
        root = pathlib.Path(d) / "dealdesk"
        m = dealdesk_build.build(root)
        n = 0
        # Only the priced results and the manifest: parameter files are edited after the build by their owners
        # (e.g. R11 L's appetite/trigger levels in params/v1/risk_appetite.json) and must never be overwritten here.
        for rel in [k for k in m["files"] if k.startswith("dd-saudi-v1/")] + ["manifest.json"]:
            src = root / rel
            if not src.is_file():
                continue
            dst = paths.DATA / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if not dst.exists() or dst.read_bytes() != src.read_bytes():
                shutil.copy2(src, dst)
                n += 1
                print("updated", rel)
    print(f"R14 x regen: {n} file(s) updated in {paths.DATA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
