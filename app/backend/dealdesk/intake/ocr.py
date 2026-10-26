"""R16 i: OCR for photographed and scanned pages (PLAN_R16 dependency exception).

Engine order: rapidocr-onnxruntime (vendored wheels, the Mac's engine; CPU; models inside the wheel), then the system
Tesseract when it is installed (cloud fallback), else a plain error. `CP_OCR_ENGINE=rapidocr|tesseract` forces one.

The page is turned upright (EXIF), deskewed from the text boxes' own angle, and the boxes are re-assembled into lines in
reading order; boxes far apart on one line are joined with " | " so a photographed table reads like a Word table row.
rapidocr drops some spaces in English ("Companyname:AlWaha"); `respace` puts the common ones back and every matcher in
the intake compares labels and names with spaces removed, so a dropped space never loses a field.

    python -m backend.dealdesk.intake.ocr --selftest      renders a skewed page, reads it back, prints the lines
"""
from __future__ import annotations

import functools
import io
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()
MAX_SIDE = 2200


class OcrError(RuntimeError):
    pass


@functools.lru_cache(maxsize=1)
def _rapid():
    try:
        from rapidocr_onnxruntime import RapidOCR  # type: ignore
    except Exception:  # noqa: BLE001 - not installed: the caller falls back
        return None
    try:
        return RapidOCR()
    except Exception:  # noqa: BLE001
        return None


def _tesseract_ok() -> bool:
    return bool(shutil.which("tesseract"))


def status() -> dict[str, Any]:
    forced = os.environ.get("CP_OCR_ENGINE", "").strip().lower()
    rapid = _rapid() is not None
    tess = _tesseract_ok()
    engine = ""
    if forced == "tesseract" and tess:
        engine = "tesseract"
    elif forced == "rapidocr" and rapid:
        engine = "rapidocr"
    elif rapid:
        engine = "rapidocr"
    elif tess:
        engine = "tesseract"
    return {"available": bool(engine), "engine": engine, "rapidocr": rapid, "tesseract": tess,
            "install": "" if engine else "ops/r16_install_ocr.sh (offline, from vendor/wheels)"}


# ---------------------------------------------------------------------------------------------------- image prep
def _load(data: bytes):
    from PIL import Image, ImageOps
    im = Image.open(io.BytesIO(data))
    im = ImageOps.exif_transpose(im)
    if im.mode not in ("RGB", "L"):
        im = im.convert("RGB")
    w, h = im.size
    s = max(w, h)
    if s > MAX_SIDE:
        f = MAX_SIDE / s
        im = im.resize((int(w * f), int(h * f)))
    elif s < 1000:  # tiny phone thumbnails: upscale so the recogniser sees letters
        f = 1400 / s
        im = im.resize((int(w * f), int(h * f)))
    return im


def _np(im):
    import numpy as np
    return np.array(im.convert("RGB"))[:, :, ::-1].copy()  # BGR for OpenCV


# ---------------------------------------------------------------------------------------------------- lines
def _box_geom(box) -> tuple[float, float, float, float, float]:
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = box
    ang = math.degrees(math.atan2(y1 - y0, x1 - x0))
    cx, cy = (x0 + x1 + x2 + x3) / 4, (y0 + y1 + y2 + y3) / 4
    h = (math.hypot(x3 - x0, y3 - y0) + math.hypot(x2 - x1, y2 - y1)) / 2
    w = (math.hypot(x1 - x0, y1 - y0) + math.hypot(x2 - x3, y2 - y3)) / 2
    return ang, cx, cy, h, w


def lines_from_boxes(result: list[Any]) -> list[str]:
    """[(box, text, score)] → text lines in reading order (deskewed), wide gaps joined with ' | '."""
    items = []
    for r in result or []:
        box, text, score = r[0], str(r[1]), float(r[2])
        if not text.strip() or score < 0.45:
            continue
        ang, cx, cy, h, w = _box_geom(box)
        items.append({"t": text.strip(), "ang": ang, "cx": cx, "cy": cy, "h": max(h, 1.0), "w": w})
    if not items:
        return []
    angs = sorted(i["ang"] for i in items if i["w"] > 3 * i["h"]) or [0.0]
    skew = angs[len(angs) // 2]
    if abs(skew) > 20:
        skew = 0.0
    a = math.radians(-skew)
    for i in items:  # rotate the centres so text lines become horizontal
        i["x"] = i["cx"] * math.cos(a) - i["cy"] * math.sin(a)
        i["y"] = i["cx"] * math.sin(a) + i["cy"] * math.cos(a)
    items.sort(key=lambda i: i["y"])
    rows: list[list[dict[str, Any]]] = []
    for it in items:
        if rows:
            last = rows[-1]
            ly = sum(x["y"] for x in last) / len(last)
            lh = sum(x["h"] for x in last) / len(last)
            if abs(it["y"] - ly) < 0.55 * max(lh, it["h"]):
                last.append(it)
                continue
        rows.append([it])
    out = []
    for row in rows:
        row.sort(key=lambda i: i["x"])
        parts: list[str] = []
        prev = None
        for it in row:
            if prev is not None:
                gap = (it["x"] - it["w"] / 2) - (prev["x"] + prev["w"] / 2)
                parts.append(" | " if gap > 1.6 * max(it["h"], prev["h"]) else " ")
            parts.append(it["t"])
            prev = it
        out.append("".join(parts))
    return out


_FIX = [
    (re.compile(r"(?<=[a-z])(?=[A-Z])"), " "),              # camel joins: "BuildingSupplies" → "Building Supplies"
    (re.compile(r"\bA[Ii](?=[A-Z][a-z])"), "Al "),          # "AIFardan" → "Al Fardan" (l read as I)
    (re.compile(r"\bA[Ii](?=\s[A-Z][a-z])"), "Al"),         # "AI Waha" / "Ai Noor" → "Al …"
    (re.compile(r"(?<=[A-Za-z]):(?=\S)"), ": "),            # "name:Al" → "name: Al"
    (re.compile(r"(?<=\b[A-Z]\d)(?=[A-Z][a-z])"), " "),        # "P1Eastern" → "P1 Eastern"
    (re.compile(r"(?<=[A-Za-z])(?=\d{2,})"), " "),          # "SAR5,000" → "SAR 5,000"
    (re.compile(r"(?<=\d)%(?=[A-Za-z])"), "% "),
    (re.compile(r",(?=[A-Za-z])"), ", "),                      # "roads,logistics" → "roads, logistics" (never inside numbers)
    (re.compile(r"(?<=[a-z])\((?=[a-z])"), " ("),               # "contracting(buildings" → "contracting (buildings"
    (re.compile(r"[ \t]{2,}"), " "),
]


def respace(line: str) -> str:
    import unicodedata
    line = unicodedata.normalize("NFKC", line)  # full-width brackets and digits from the recogniser → ASCII
    for rx, rep in _FIX:
        line = rx.sub(rep, line)
    return line.strip()


# ---------------------------------------------------------------------------------------------------- engines
def _rapid_lines(im) -> list[str]:
    """rapidocr in a child process per page (Deal Desk edition, integration of Round A): the ONNX session and the page
    image take ~1–2 GB at peak, on top of the Deal Desk service's own ~2 GB. In a child the memory is returned after
    every page, and an out-of-memory kill fails that page only, never the service. CP_OCR_INPROC=1 keeps the old
    in-process path (the child itself uses it)."""
    if os.environ.get("CP_OCR_INPROC", "").strip() != "1":
        return _rapid_lines_child(im)
    return _rapid_lines_inproc(im)


def _rapid_lines_child(im) -> list[str]:
    import json
    import sys
    with tempfile.TemporaryDirectory(prefix="intake-ocr-") as td:
        p = Path(td) / "p.png"
        im.save(p)
        env = {**os.environ, "CP_OCR_INPROC": "1", "OMP_NUM_THREADS": os.environ.get("OMP_NUM_THREADS", "2")}
        try:
            r = subprocess.run([sys.executable, "-m", "backend.dealdesk.intake.ocr", "--page", str(p)], capture_output=True,
                               text=True, timeout=300, env=env, cwd=str(Path(__file__).resolve().parents[3]))
        except subprocess.TimeoutExpired as e:
            raise OcrError("OCR of this page took longer than 5 minutes") from e
    if r.returncode != 0:
        why = "it ran out of memory" if r.returncode in (-9, 137) else (r.stderr.strip().splitlines() or ["error"])[-1][:160]
        raise OcrError(f"OCR of this page failed ({why})")
    try:
        return list(json.loads(r.stdout.strip().splitlines()[-1]))
    except (ValueError, IndexError) as e:
        raise OcrError("OCR returned no text") from e


def _rapid_lines_inproc(im) -> list[str]:
    eng = _rapid()
    if eng is None:
        raise OcrError("rapidocr is not installed")
    with _LOCK:  # one onnx session; serialise (the CPU is the limit anyway)
        res, _ = eng(_np(im))
    return [respace(x) for x in lines_from_boxes(res or [])]


def _tess_lines(im) -> list[str]:
    with tempfile.TemporaryDirectory(prefix="intake-ocr-") as td:
        p = Path(td) / "p.png"
        im.save(p)
        env = {**os.environ, "OMP_THREAD_LIMIT": "1"}
        r = subprocess.run(["tesseract", str(p), "stdout", "--psm", "4"], capture_output=True, text=True, timeout=180, env=env)
    return [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]


def image_lines(data: bytes) -> tuple[list[str], str]:
    """OCR one image → (lines, engine). Raises OcrError when no engine is installed."""
    st = status()
    if not st["available"]:
        raise OcrError("This is a photo or scan and OCR is not installed on this laptop. Run ops/r16_install_ocr.sh "
                       "(offline, a minute), or upload the Word or PDF version.")
    im = _load(data)
    if st["engine"] == "rapidocr":
        lines = _rapid_lines(im)
        if sum(len(x) for x in lines) < 20:  # nearly nothing: try once upright-rotated by 90° (a sideways phone photo)
            alt = _rapid_lines(im.rotate(90, expand=True))
            if sum(len(x) for x in alt) > sum(len(x) for x in lines):
                lines = alt
        return lines, "rapidocr"
    return _tess_lines(im), "tesseract"


def pdf_scan_lines(data: bytes) -> tuple[list[str], str, int]:
    """A PDF without a text layer: OCR each page's embedded image(s) (pure Python via pypdf); Poppler when present."""
    import pypdf
    rd = pypdf.PdfReader(io.BytesIO(data))
    lines: list[str] = []
    engine = ""
    pages = len(rd.pages)
    for page in rd.pages:
        imgs = []
        try:
            imgs = list(page.images)
        except Exception:  # noqa: BLE001 - odd image filters: fall through to Poppler
            imgs = []
        if imgs:
            big = max(imgs, key=lambda i: len(i.data))
            ls, engine = image_lines(big.data)
            lines.extend(ls)
            lines.append("")
        elif shutil.which("pdftoppm"):
            with tempfile.TemporaryDirectory(prefix="intake-pdf-") as td:
                src = Path(td) / "in.pdf"
                w = pypdf.PdfWriter()
                w.add_page(page)
                with open(src, "wb") as fh:
                    w.write(fh)
                subprocess.run(["pdftoppm", "-r", "200", "-png", str(src), str(Path(td) / "p")], check=True, capture_output=True, timeout=120)
                for png in sorted(Path(td).glob("p*.png")):
                    ls, engine = image_lines(png.read_bytes())
                    lines.extend(ls)
    return lines, engine or status()["engine"], pages


# ---------------------------------------------------------------------------------------------------- self-test
def _selftest() -> int:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    im = Image.new("RGB", (1240, 900), "white")
    d = ImageDraw.Draw(im)
    font = None
    for f in ("/System/Library/Fonts/Supplemental/Arial.ttf", "/Library/Fonts/Arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if Path(f).exists():
            font = ImageFont.truetype(f, 28)
            break
    font = font or ImageFont.load_default()
    rows = ["COMMERCIAL REGISTRATION", "Company name: Qasr Al Noor Trading Co.", "CR number: 1010999001", "Expiry date: 2027-03-13"]
    for i, t in enumerate(rows):
        d.text((90, 120 + 70 * i), t, fill="black", font=font)
    im = im.rotate(2.0, expand=True, fillcolor=(80, 80, 80)).filter(ImageFilter.GaussianBlur(0.6))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=75)
    lines, eng = image_lines(buf.getvalue())
    print(f"engine={eng}")
    for ln in lines:
        print("  ", ln)
    ok = any("1010999001" in ln.replace(" ", "") for ln in lines)
    print("SELFTEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    if "--page" in sys.argv:  # the child of _rapid_lines_child: one page image → its lines as one JSON line
        import json as _json
        from PIL import Image as _Image
        _im = _Image.open(sys.argv[sys.argv.index("--page") + 1])
        _im.load()
        print(_json.dumps(_rapid_lines_inproc(_im), ensure_ascii=False))
        sys.exit(0)
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    print(status())
