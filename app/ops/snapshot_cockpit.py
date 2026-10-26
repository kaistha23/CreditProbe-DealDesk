"""Snapshot every deterministic Cockpit read endpoint to JSON files.

Usage: python ops/snapshot_cockpit.py <api_base> <out_dir>

GET only. Captures the session, domains, ECL and attention for both books,
plus every attention item's detail. These are the panels a user sees before
asking anything, and none of them calls a model (`model_calls: 0`).
"""
import json
import sys
import urllib.request
from pathlib import Path

DOMAINS = ("corporate", "retail")


def get(base: str, path: str):
    with urllib.request.urlopen(base.rstrip("/") + path, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main(base: str, out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    prefix = "/api/v1/cockpit-v4"
    written = 0

    def save(name, payload):
        nonlocal written
        (out / f"{name}.json").write_text(json.dumps(payload, indent=1, sort_keys=True))
        written += 1

    save("domains", get(base, f"{prefix}/domains"))
    for domain in DOMAINS:
        save(f"ecl_{domain}", get(base, f"{prefix}/ecl?domain={domain}"))
        attention = get(base, f"{prefix}/attention?domain={domain}")
        save(f"attention_{domain}", attention)
        items = list(attention.get("segments_requiring_attention") or []) + \
            list(attention.get("ecl_highlights") or [])
        for index, item in enumerate(items):
            save(f"attention_{domain}_item{index:02d}",
                 get(base, f"{prefix}/attention/{item['item_id']}?domain={domain}"))
    print(f"{written} snapshots -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], Path(sys.argv[2])))
