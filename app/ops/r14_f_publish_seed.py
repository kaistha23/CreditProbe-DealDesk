"""R14 F: publish only the three deal-flow relations (dd_structure_set, dd_stress_proof, dd_monitoring_proposal) with the
data build's stamp and actor, so `python -m backend.dealdesk.data.build --check` matches without republishing the
other relations (which later sessions have published on top of the build).

    PYTHONPATH=. .venv/bin/python ops/r14_f_publish_seed.py
"""
from __future__ import annotations

import json

from backend.dealdesk.data import build, schema, store
from backend.dealdesk.stressproof import seed


def _reset(rel: str) -> None:
    """Back to 'never published', so the seed is version 1 like the rest of the build (rel_version is in the content hash)."""
    path = store.relation_path(rel)
    if path.exists():
        path.unlink()
    folder = schema.RELATIONS[rel]["folder"]
    mp = store.manifest_path(folder)
    m = json.loads(mp.read_text())
    if m.get("relations", {}).pop(rel, None) is not None:
        mp.write_text(json.dumps(m, indent=1, ensure_ascii=False) + "\n")
    store._CACHE.clear()


if __name__ == "__main__":
    rows = seed.rows(build.STAMP)
    for rel, rs in rows.items():
        _reset(rel)
        r = store.publish(rel, rs, mode="replace", actor=build.ACTOR, at=build.STAMP)
        print(f"{rel:28s} {r['rows']} rows (version {r['version']})")
