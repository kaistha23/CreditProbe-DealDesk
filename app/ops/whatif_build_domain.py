"""Build (or check) the What-If IFRS 9 data domain.

    .venv/bin/python ops/whatif_build_domain.py            build both books into var/whatif_v5 (about 1 minute)
    .venv/bin/python ops/whatif_build_domain.py --if-needed build only when a period file is missing, or when
                                                           the committed manifest changed since the last build
                                                           (a new book release, e.g. the R5 Early Warning story)
    .venv/bin/python ops/whatif_build_domain.py --check    rebuild into a scratch folder and compare the
                                                           control totals with the committed manifest

The Parquet files are deterministic outputs of the v5 books and the MEV store, so
they are rebuilt rather than committed; data/whatif_v5/<book>/manifest.json holds the
per-period control totals every rebuild must reproduce.
"""
from __future__ import annotations

import math
import pathlib
import sys
import tempfile

V5 = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V5))

from backend.whatif_v5.domain import build, store  # noqa: E402


def missing(book: str) -> bool:
    try:
        periods = store.periods(book)
    except store.DomainError:
        return True
    return any(not (store.files_dir(book) / f"{p}.parquet").exists() for p in periods)


def _stamp_path(book: str) -> pathlib.Path:
    return V5 / "var" / "whatif_v5_stamps" / f"{book}.manifest.sha256"


def _manifest_sha(book: str) -> str:
    import hashlib
    return hashlib.sha256((store.book_dir(book) / "manifest.json").read_bytes()).hexdigest()


def stale(book: str) -> bool:
    """The local build predates the committed manifest (or was never stamped)."""
    p = _stamp_path(book)
    return not p.exists() or p.read_text().strip() != _manifest_sha(book)


def main() -> int:
    args = sys.argv[1:]
    if "--check" in args:
        import json
        bad = 0
        for book in store.BOOKS:
            committed = json.loads((store.book_dir(book) / "manifest.json").read_text())["control_totals"]
            with tempfile.TemporaryDirectory(dir=V5 / "var") as tmp:
                man = build.build_book(book, out_dir=pathlib.Path(tmp) / book, meta_dir=pathlib.Path(tmp) / "meta",
                                       log=lambda *_: None)
            for p, tot in committed.items():
                for k, v in tot.items():
                    got = man["control_totals"][p][k]
                    if not math.isclose(got, v, rel_tol=1e-9, abs_tol=1e-9):
                        bad += 1
                        print(f"DIFF {book} {p} {k}: committed {v} rebuilt {got}")
        print("CHECK PASS" if not bad else f"CHECK FAIL ({bad} differences)")
        return 1 if bad else 0
    for book in store.BOOKS:
        if "--if-needed" in args and not missing(book) and not stale(book):
            print(f"What-If {book} domain present and current.")
            continue
        print(f"Building the What-If {book} domain ...")
        # The build rewrites the committed metadata (manifest, cycle model). Keep the committed bytes, so a
        # rebuild on another machine (last-bit float differences) never leaves the checkout dirty; the sync
        # tests check the rebuilt Parquet against the committed control totals.
        kept = {f: (store.book_dir(book) / f).read_bytes() for f in ("manifest.json", "cycle_model.json")
                if (store.book_dir(book) / f).exists()}
        man = build.build_book(book)
        for f, b in kept.items():
            (store.book_dir(book) / f).write_bytes(b)
        print(f"  {man['rows']:,} rows over {len(man['periods'])} periods; reconciliation {man['reconciliation']}")
        _stamp_path(book).parent.mkdir(parents=True, exist_ok=True)
        _stamp_path(book).write_text(_manifest_sha(book) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
