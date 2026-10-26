"""R14 G: run the contagion and employer engines on the published set, write the committed snapshot and publish the three
network_intel relations (net_contagion_view, net_contagion_link, net_employer_view) to Data Domains.

Usage: .venv/bin/python ops/r14_publish_network_views.py [--snapshot-only | --publish-only]
Deterministic; safe to re-run (mode replace). The R12 build (`python -m backend.dealdesk.data.build`) republishes the same
rows from the snapshot.
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from backend.intel.network import views  # noqa: E402

if __name__ == "__main__":
    if "--publish-only" in sys.argv:
        print(json.dumps(views.publish(), indent=1))
    else:
        rows = views.compute()
        print("snapshot:", views.write_snapshot(rows), {k: len(v) for k, v in rows.items()})
        if "--snapshot-only" not in sys.argv:
            print(json.dumps(views.publish(rows), indent=1))
