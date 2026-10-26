"""P6: the demo run, timed. Writes the committed demo proposals and timings under data/dealdesk/house_style/onboarding/:

    proposed_*.json   what the fictional policy, the demo committee memos and the house's memos teach (PROPOSED)
    timings.json      upload -> reviewed draft, and draft -> review with findings, for Case A and DD-01

    python -m backend.dealdesk.house_style.onboarding.build

The run uses a scratch store (a temporary DEALDESK_VAR), so it neither reads nor leaves runtime state. The checker step
accepts every automatically checkable rule and every committee question (as the demo checker would); the human review
time is not part of the timing, the system time is.
"""
from __future__ import annotations

import json
import os
import pathlib
import platform
import sys
import tempfile
import time


def main() -> dict:
    tmp = tempfile.mkdtemp(prefix="onboard-")
    os.environ["DEALDESK_VAR"] = tmp
    from backend.dealdesk import paths
    paths.VAR = pathlib.Path(tmp)
    from backend.dealdesk.house_style.onboarding import service as S
    out_dir = S.COMMITTED
    runs = []
    for pid in ("PRP-A-GMC", "DD-01"):
        t0 = time.perf_counter()
        pol, memos, house = S.demo_inputs()
        s = S.learn(pol, memos, by="maker (uploader)", memo_docs=house)
        t_learn = time.perf_counter()
        acc = [i for i in s["items"] if i.get("rule") and i["checkability"] == "auto" and not i.get("conflict")] + s["committee"]
        for i in acc:
            S.decide(s["session_id"], i["id"], "accept", by="checker")
        t_acc = time.perf_counter()
        dr = S.draft_review(pid)
        t_end = time.perf_counter()
        runs.append({"proposal_id": pid, "learn_s": round(t_learn - t0, 2), "accept_s": round(t_acc - t_learn, 2),
                     "accepted": len(acc), "draft_s": dr["timings"]["draft_s"], "draft_to_review_s": dr["timings"]["draft_to_review_s"],
                     "upload_to_reviewed_draft_s": round(t_end - t0, 2), "version": dr["version"],
                     "review_headline": (dr["review"]["headline"] or {}).get("headline") if isinstance(dr["review"]["headline"], dict) else dr["review"]["headline"],
                     "review_findings": dr["review"]["findings"], "policy_findings": dr["review"]["policy_findings"],
                     "open_committee_questions": len(dr["review"]["open_questions"]),
                     "answered_committee_questions": sum(1 for a in dr["committee_answers"] if a["status"] == "answered")})
        last = s
    sess = S.get(last["session_id"])
    for f in (S.root() / "sessions" / last["session_id"]).glob("proposed_*.json"):
        obj = json.loads(f.read_text())
        obj["session_id"] = "example (fictional policy)"
        (out_dir / f.name).write_text(json.dumps(obj, indent=1, ensure_ascii=False, default=str) + "\n")
    timings = {"runs": runs, "host": platform.machine(), "python": sys.version.split()[0],
               "documents": [d["name"] for d in sess["documents"]][:8] + ([f"... {len(sess['documents']) - 8} more"] if len(sess["documents"]) > 8 else []),
               "summary": sess["summary"]["text"], "note": "system time; the checker's reading time is not included"}
    (out_dir / "timings.json").write_text(json.dumps(timings, indent=1) + "\n")
    return timings


if __name__ == "__main__":  # pragma: no cover
    print(json.dumps(main(), indent=1))
