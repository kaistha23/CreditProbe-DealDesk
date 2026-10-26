"""R16 x: the demo click-through (Part A and Part B) on the production build, screens in docs/v5/r16_review/x/.

  .venv/bin/python ops/r16_x_walk.py [--ui http://127.0.0.1:5500] [--sizes 1440x900] [--parts a,b]

Re-uses the sessions' own click walks (every screen reached by clicking; only the first page is a goto) with their screens
redirected to docs/v5/r16_review/x/<part>/:
  a_word, a_pdf, a_images  customer 1 (Dar Al Naseem): New proposal → Customer documents, the whole pack as Word, as PDF, as photos
                           → checklist, cross-checks, the Bank's data (Borrower 360 pull) → the deal → Customer file   (session i)
  a_request                customer 1: upload path → Business request → ask + RM notes from ASK.md typed → Write → Trace,
                           Share, Word download                                                                       (session b)
  b_photos, b_pdf          customer 2 (Sawaed Al Bina): Credit response → the business request as photos (or PDF) + the
                           documents → Read and respond → steps → credit response → RM brief → Word / PDF          (session c)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

V5 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V5))
sys.path.insert(0, str(V5 / "ops"))

OUT = V5 / "docs" / "v5" / "r16_review" / "x"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ui", default="http://127.0.0.1:5500")
    ap.add_argument("--sizes", default="1440x900")
    ap.add_argument("--parts", default="a_word,a_pdf,a_images,a_request,b_photos,b_pdf")
    a = ap.parse_args()
    sizes = [tuple(int(x) for x in s.split("x")) for s in a.sizes.split(",")]
    results: dict[str, int] = {}
    for part in a.parts.split(","):
        out = OUT / part
        out.mkdir(parents=True, exist_ok=True)
        try:
            if part.startswith("a_") and part != "a_request":
                import r16_i_walkthrough as W
                W.OUT = out
                results[part] = W.run(a.ui, sizes, ["c1"], {"a_word": "docx", "a_pdf": "pdf", "a_images": "images"}[part])
            elif part == "a_request":
                import r16_b_walkthrough as W
                W.OUT = out
                W.PART_A = True
                results[part] = W.run(a.ui, sizes, ["c1"])
            else:
                import r16_c_walk as W
                W.OUT = out
                results[part] = W.run(a.ui, sizes, part == "b_photos")
        except Exception as e:  # noqa: BLE001 - record and go on with the next part
            results[part] = 99
            (out / "error.txt").write_text(f"{type(e).__name__}: {e}\n")
        print(part, "rc", results[part], flush=True)
    (OUT / "summary.json").write_text(json.dumps(results, indent=1))
    return 0 if all(v == 0 for v in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
