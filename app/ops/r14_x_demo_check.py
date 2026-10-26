"""R14 x: the demo proposal check, three times, against the running Deal Desk service (as the UI's upload does).

    .venv/bin/python ops/r14_x_demo_check.py [--api http://127.0.0.1:8508]

Uploads the half-baked RM proposal (data/dealdesk/demo_proposals/R14-RWQ_RM_proposal_half_baked.docx) to
POST /api/v1/dealdesk/proposals/R14-RWQ/proposal-check three times, then the corrected one once, and checks:
all 12 planted defect types of answer_key.json caught on every run, the three results identical (defects, score,
sections), each run under 60 s, and the corrected version scoring higher. Writes docs/v5/r14_review/x/demo_check.json.
A minted session cookie is used (no password read or printed).
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys
import time

import requests

V5 = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V5 / "ops"))
from r11_ui_shots import mint  # noqa: E402

PACK = V5 / "data" / "dealdesk" / "demo_proposals"
OUT = V5 / "docs" / "v5" / "r14_review" / "x" / "demo_check.json"


def run(api: str, s: requests.Session, name: str) -> tuple[dict, float]:
    t0 = time.time()
    with open(PACK / name, "rb") as fh:
        r = s.post(f"{api}/api/v1/dealdesk/proposals/R14-RWQ/proposal-check", files={"file": (name, fh,
                   "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}, timeout=300)
    secs = time.time() - t0
    r.raise_for_status()
    return r.json(), secs


def main() -> int:
    api = sys.argv[sys.argv.index("--api") + 1] if "--api" in sys.argv else "http://127.0.0.1:8508"
    key = json.loads((PACK / "answer_key.json").read_text())
    want = {d["defect_type"] for d in key["defects"]}
    s = requests.Session()
    s.cookies.set("cp_session", mint(), domain="127.0.0.1", path="/")
    runs = []
    for i in range(3):
        res, secs = run(api, s, key["document"])
        got = {d.get("defect_type") for d in res.get("defects", [])}
        sig = hashlib.sha256(json.dumps({"defects": res.get("defects"), "score": res.get("score"),
                                         "sections": res.get("sections")}, sort_keys=True, default=str).encode()).hexdigest()
        runs.append({"run": i + 1, "seconds": round(secs, 2), "score": res.get("score"), "grade": res.get("grade"),
                     "defects": len(res.get("defects", [])), "planted_caught": len(want & got), "missed": sorted(want - got),
                     "signature": sig})
        print(runs[-1], flush=True)
    corr, csecs = run(api, s, key["corrected"])
    rep = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "deal": key["proposal_id"], "planted": len(want),
           "runs": runs, "corrected": {"seconds": round(csecs, 2), "score": corr.get("score"), "grade": corr.get("grade")},
           "all_12_every_run": all(r["planted_caught"] == len(want) for r in runs),
           "identical": len({r["signature"] for r in runs}) == 1,
           "under_60s": all(r["seconds"] < 60 for r in runs),
           "corrected_scores_higher": (corr.get("score") or 0) > (runs[0]["score"] or 0)}
    rep["pass"] = rep["all_12_every_run"] and rep["identical"] and rep["under_60s"] and rep["corrected_scores_higher"]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rep, indent=1) + "\n")
    print("DEMO PROPOSAL CHECK", "PASS" if rep["pass"] else "FAIL", json.dumps({k: rep[k] for k in
          ("all_12_every_run", "identical", "under_60s", "corrected_scores_higher")}))
    return 0 if rep["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
