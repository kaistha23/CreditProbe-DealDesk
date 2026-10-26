"""Build the v5 product knowledge pack: docs/product_knowledge + worked examples computed on the current books.

Usage: .venv/bin/python ops/build_product_knowledge.py [--if-needed] [--out PATH]

Writes var/product_knowledge/pack_v5.json (COCKPIT_PRODUCT_KNOWLEDGE_V5 overrides). The Cockpit's product-help
path reads it when that variable is set (registered exception FX-A4); ops/v5.sh sets it and builds the pack.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.ai_work import knowledge  # noqa: E402


def main() -> int:
    out = Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else knowledge.PACK
    if "--if-needed" in sys.argv and out.exists():
        newest = max(p.stat().st_mtime for p in knowledge.DOCS.glob("*.md"))
        if out.stat().st_mtime >= newest:
            print(f"product knowledge pack up to date: {out}")
            return 0
    path = knowledge.write_pack(out)
    print(f"product knowledge pack written: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
