"""Register (or refresh) a frozen-file exception: its patch against the base, and its entry in frozen_exceptions.json.

Usage: .venv/bin/python ops/register_exception.py FX-4a frontend/src/components/cockpit-v4/attention-drawer.tsx \
           "what it does" "who approved" [--base v5/r2-base]

The patch is `git diff` of the file against the base ref (in FX-1's format); the registered hashes are the base file's
(ops/frozen_manifest.json is the authority for it) and the file's current content. ops/frozen_guard.py then proves the
file is exactly base + this patch. Run it again after any further change to the file.
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    base = sys.argv[sys.argv.index("--base") + 1] if "--base" in sys.argv else "v5/r2-base"
    if "--base" in sys.argv:
        args = [a for a in args if a != base]
    fx, path, what, approved = args
    out = subprocess.run(["git", "diff", "-U3", base, "--", path], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    lines = out.splitlines(keepends=True)
    start = next(i for i, ln in enumerate(lines) if ln.startswith("--- a/"))
    patch = ROOT / "docs" / "v5" / "frozen_exceptions" / f"{fx}.patch"
    patch.write_text("".join(lines[start:]))
    base_bytes = subprocess.run(["git", "show", f"{base}:{path}"], cwd=ROOT, capture_output=True, check=True).stdout
    entry = {"id": fx, "path": path, "patch": str(patch.relative_to(ROOT)),
             "base_sha256": hashlib.sha256(base_bytes).hexdigest(),
             "patched_sha256": hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), "what": what, "approved_by": approved}
    reg = ROOT / "ops" / "frozen_exceptions.json"
    data = json.loads(reg.read_text())
    data["exceptions"] = [e for e in data["exceptions"] if e["id"] != fx] + [entry]
    reg.write_text(json.dumps(data, indent=1) + "\n")
    print(f"{fx}: {path} registered ({len(patch.read_text().splitlines())} patch lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
