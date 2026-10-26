"""R16 v: fetch and verify the neural voice model files (vendor/tts/MANIFEST.tsv -> var/tts/).

    python -m ops.r16_tts_files verify            # check var/tts against the manifest (sha256); exit 1 if a required file is bad
    python -m ops.r16_tts_files fetch [--hq]      # download what is missing (GitHub releases), then verify
    python -m ops.r16_tts_files pack DIR          # copy the verified files into DIR (the Mac pack: var/r16_tts/)
    python -m ops.r16_tts_files unpack DIR        # copy the files from a pack DIR into var/tts and verify (offline)

`--hq` also fetches the full-precision Kokoro model (kokoro-v1.0.onnx, 325 MB), which the engine prefers to int8.
Standard library only. Downloads honour HTTPS_PROXY and SSL_CERT_FILE.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

V5 = Path(__file__).resolve().parents[1]
MANIFEST = V5 / "vendor" / "tts" / "MANIFEST.tsv"


def dest() -> Path:
    p = Path(os.environ.get("CP_TTS_HOME") or (V5 / "var" / "tts"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def manifest() -> tuple[list[dict], dict]:
    files, sherpa = [], {}
    for line in MANIFEST.read_text().splitlines():
        if line.startswith("#SHERPA\t"):
            _, name, sha, size, url = line.split("\t")
            sherpa = {"name": name, "sha": sha, "size": int(size), "urls": url.split()}
            continue
        if not line.strip() or line.startswith("#"):
            continue
        name, sha, size, req, src = line.split("\t")
        files.append({"name": name, "sha": sha, "size": int(size), "required": req == "yes", "src": src.split()})
    return files, sherpa


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def ok(p: Path, f: dict) -> bool:
    return p.is_file() and (not f["size"] or p.stat().st_size == f["size"]) and sha256(p) == f["sha"]


def download(urls: list[str], to: Path) -> bool:
    for u in urls:
        try:
            print(f"  fetching {u}", flush=True)
            with urllib.request.urlopen(u, timeout=60) as r, to.open("wb") as out:  # noqa: S310 (fixed https URLs)
                shutil.copyfileobj(r, out, 1 << 20)
            return True
        except Exception as e:  # noqa: BLE001
            print(f"  could not fetch it: {e}", flush=True)
    return False


def verify(quiet: bool = False) -> bool:
    files, _ = manifest()
    good = True
    for f in files:
        p = dest() / f["name"]
        state = "ok" if ok(p, f) else ("missing" if not p.exists() else "BAD CHECKSUM")
        if state != "ok" and f["required"]:
            good = False
        if not quiet:
            print(f"  {f['name']:<34} {state}{'' if f['required'] else ' (optional)'}")
    return good


def fetch(hq: bool) -> bool:
    files, sherpa = manifest()
    d = dest()
    need_sherpa = False
    for f in files:
        p = d / f["name"]
        if ok(p, f) or (not f["required"] and not hq):
            continue
        if f["src"] == ["sherpa"]:
            need_sherpa = True
            continue
        tmp = p.with_suffix(p.suffix + ".part")
        if download(f["src"], tmp) and ok(tmp, f):
            tmp.replace(p)
        else:
            tmp.unlink(missing_ok=True)
            print(f"  {f['name']}: not fetched or checksum wrong")
    if need_sherpa and sherpa:
        with tempfile.TemporaryDirectory() as td:
            arc = Path(td) / sherpa["name"]
            if download(sherpa["urls"], arc) and ok(arc, {"sha": sherpa["sha"], "size": sherpa["size"]}):
                with tarfile.open(arc, "r:bz2") as t:
                    for m in t.getmembers():
                        base = Path(m.name).name
                        if m.isfile() and base in {f["name"] for f in files if f["src"] == ["sherpa"]}:
                            src = t.extractfile(m)
                            if src is not None:
                                with (d / base).open("wb") as out:
                                    shutil.copyfileobj(src, out)
            else:
                print("  the Piper Arabic voice archive was not fetched or its checksum is wrong")
    return verify()


def copy_all(src: Path, dst: Path) -> None:
    files, _ = manifest()
    dst.mkdir(parents=True, exist_ok=True)
    for f in files:
        p = src / f["name"]
        if ok(p, f):
            shutil.copy2(p, dst / f["name"])
            print(f"  copied {f['name']}")
    shutil.copy2(MANIFEST, dst / "MANIFEST.tsv")


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "verify"
    if cmd == "verify":
        return 0 if verify() else 1
    if cmd == "fetch":
        return 0 if fetch("--hq" in argv) else 1
    if cmd == "pack" and len(argv) > 1:
        copy_all(dest(), Path(argv[1]))
        return 0
    if cmd == "unpack" and len(argv) > 1:
        copy_all(Path(argv[1]), dest())
        return 0 if verify() else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
