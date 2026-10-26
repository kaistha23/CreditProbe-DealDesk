"""Rescale the v5 corporate book's money columns by one constant factor.

Why: the frozen generator draws facility limits of SAR 140-1,450 million and
the population grew from 97 to 5,412 borrowers without resizing them, so the
book carries SAR 15.4 trillion of EAD -- about five times the whole Saudi
banking system. The label ("SAR million") is right; the magnitudes are not.

What: every column whose schema unit is `rcy` (reporting-currency amount)
is multiplied by FACTOR, in all four corporate relations and all 20
quarters. Nothing else changes: IDs, ratings, PDs, LGDs, percentages,
multiples, counts, stages and flags are copied byte for byte. Because the
factor is uniform, every ratio between two amounts (coverage, LTV, shares,
movements) and every ranking is unchanged.

Where: v5 only. The original release is first copied, untouched, to
data/reference/original/<release>/ and stays there as the reconciliation
source. The Desktop originals are never touched.

The release id stays `v4-saudi-corporate-20q-v4` because the frozen code
pins it (domains.DEFAULT_RELEASES). The manifest records the new
fingerprint, the factor and the original fingerprint, so the book says what
was done to it.

Usage: python ops/rescale_corporate.py            (idempotent; refuses to
       rescale a book that is already rescaled)
"""
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

V5 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V5))

from backend.cockpit_v4 import domains as dom  # noqa: E402
from backend.cockpit_v4 import lake  # noqa: E402
from backend.cockpit_v4 import schema as schema_mod  # noqa: E402

RELEASE = "v4-saudi-corporate-20q-v4"
ORIGINAL_FINGERPRINT = "c79d0fdf8753576f391f2a6bb84f281595e7445291a558abe639f6a43e22a740"
FACTOR = 0.01
LAKE = V5 / "data" / "cockpit_v4_lake" / RELEASE
REFERENCE = V5 / "data" / "reference" / "original" / RELEASE


def money_columns(relation: str) -> list[str]:
    spec = schema_mod.relation(dom.CORPORATE, relation)
    return [f.name for f in spec.fields if f.unit == "rcy"]


#: The two credit-policy limits that are AMOUNTS. They were calibrated to the
#: oversized book (a SAR 25bn single-obligor limit), and the book's planted
#: concentration pattern -- a connected group over CP-1.2 while no single name
#: is over CP-1.1 -- only keeps its answer if the limits move with the book.
#: Exact text substitutions; ops/frozen_guard.py accepts this file only when
#: its diff from the base is exactly these.
POLICY = V5 / "backend" / "cockpit_v4" / "credit_policy.json"
POLICY_SUBSTITUTIONS = (
    ("may not exceed SAR 25,000 million.", "may not exceed SAR 250 million."),
    ('"single_obligor_ead_sar_mn": 25000}', '"single_obligor_ead_sar_mn": 250}'),
    ("may not exceed SAR 50,000 million.", "may not exceed SAR 500 million."),
    ('"connected_group_ead_sar_mn": 50000}', '"connected_group_ead_sar_mn": 500}'),
)


def rescale_policy(text: str) -> str:
    for before, after in POLICY_SUBSTITUTIONS:
        if after in text:
            continue
        assert text.count(before) == 1, before
        text = text.replace(before, after)
    return text


def main() -> int:
    POLICY.write_text(rescale_policy(POLICY.read_text(encoding="utf-8")), encoding="utf-8")
    manifest_path = LAKE / lake.MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if "v5_rescale" in (manifest.get("notes") or {}):
        print("Already rescaled:", manifest["notes"]["v5_rescale"]["factor"])
        return 0
    if manifest["release_fingerprint"] != ORIGINAL_FINGERPRINT:
        print("STOP: the lake book is not the original Round H book.")
        return 1

    # Keep the original bytes as the reconciliation source.
    if not REFERENCE.exists():
        REFERENCE.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(LAKE, REFERENCE)

    written: list[Path] = []
    scaled: dict[str, list[str]] = {}
    for relation in schema_mod.relation_names(dom.CORPORATE):
        spec = schema_mod.relation(dom.CORPORATE, relation)
        frame = pd.read_parquet(REFERENCE / f"{relation}.parquet")
        columns = money_columns(relation)
        for column in columns:
            frame[column] = frame[column].astype("float64") * FACTOR
        frame = frame[list(spec.columns)]  # the schema's order, as publish() writes
        path = LAKE / f"{relation}.parquet"
        frame.to_parquet(path, index=False)
        written.append(path)
        scaled[relation] = columns

    notes = dict(manifest.get("notes") or {})
    notes["v5_rescale"] = {
        "factor": FACTOR,
        "applied_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "original_release_fingerprint": ORIGINAL_FINGERPRINT,
        "columns_scaled": scaled,
        "reason": ("Magnitudes only. The frozen generator sized each facility "
                   "for a 97-borrower book; at 5,412 borrowers it carried "
                   "SAR 15.4tn of EAD. Scaled to a mid-size Saudi bank's "
                   "corporate book. IDs, ratios, PDs, stages and rankings "
                   "unchanged; see docs/v5/RESCALE.md."),
    }
    manifest["notes"] = notes
    manifest["release_fingerprint"] = lake._digest(written)  # noqa: SLF001
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True, default=str),
                             encoding="utf-8")
    print("rescaled", RELEASE, "x", FACTOR, "->", manifest["release_fingerprint"][:16])
    return 0


if __name__ == "__main__":
    sys.exit(main())
