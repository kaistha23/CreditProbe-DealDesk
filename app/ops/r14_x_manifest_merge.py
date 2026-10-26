"""R14 x: resolve a merge conflict in an R12 Data Domains manifest (e.g. data/dealdesk/dd-saudi-v1/manifest_r12.json).

    .venv/bin/python ops/r14_x_manifest_merge.py data/dealdesk/dd-saudi-v1/manifest_r12.json

Reads "ours" (stage 2) and "theirs" (stage 3) from the git index, keeps the union of the relations (a relation
on both sides keeps the entry with the higher version, then the later publish time; its history is the union of
both histories by (version, published_at)), and regenerates the column dictionary from the merged schema.py.
Writes the file; the caller `git add`s it. No relation published by either session is lost.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

V5 = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V5))


def stage(n: int, path: str) -> dict:
    out = subprocess.run(["git", "show", f":{n}:{path}"], cwd=V5, capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def merge(ours: dict, theirs: dict) -> dict:
    m = dict(ours)
    for k, v in theirs.items():
        if k not in ("relations", "dictionary"):
            m.setdefault(k, v)
    rels = dict(ours.get("relations", {}))
    for name, t in theirs.get("relations", {}).items():
        o = rels.get(name)
        if o is None:
            rels[name] = t
            continue
        win = max((o, t), key=lambda e: (int(e.get("version", 0)), str(e.get("published_at", ""))))
        hist = {(h.get("version"), h.get("published_at")): h for h in o.get("history", []) + t.get("history", [])}
        win = dict(win)
        win["history"] = sorted(hist.values(), key=lambda h: (int(h.get("version", 0)), str(h.get("published_at", ""))))[-50:]
        rels[name] = win
    m["relations"] = dict(sorted(rels.items()))
    return m


def main() -> int:
    path = sys.argv[1]
    merged = merge(stage(2, path), stage(3, path))
    from backend.dealdesk.data import schema as S
    folder = pathlib.Path(path).parent.name
    for f, name in S.MANIFEST.items():
        if pathlib.Path(f).name == folder or str(f).endswith(folder):
            try:
                merged["dictionary"] = S.dictionary(f)
            except Exception as e:  # noqa: BLE001
                print("dictionary not regenerated:", e)
            break
    (V5 / path).write_text(json.dumps(merged, indent=1, ensure_ascii=False) + "\n")
    print(f"merged {path}: {len(merged['relations'])} relations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
