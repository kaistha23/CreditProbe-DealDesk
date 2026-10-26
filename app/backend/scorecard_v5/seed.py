"""One completed validation per scorecard, seeded on first start (PLAN_R3 S2).

Each seed is a real thread: the same assistant, the same engine, the same plan, run on the domain. The two
older ones are reviewed; the retail behavioural one waits for its review so the review step can be shown.
Seeds belong to no one (everyone sees them) and are tagged `seed` in the store only.
"""
from __future__ import annotations

import time

from backend.scorecard_v5 import assistant, engine

DAY = 86400.0
SCRIPT = [
    ("SME-ANN", "I want to validate the SME scorecard", ["Cut the segments by sector and run it", "What are the findings?"], 9,
     {"conclusion": "not_fit", "note": "Calibration is red in the two latest matured years and the score distribution has moved far from development, driven by the qualitative score. "
                                      "Ranking power is intact, so recalibrate the grade PDs and redevelop the qualitative-score bins before the scorecard is relied on for pricing.",
      "reviewer": "Lama Al-Mutairi"}),
    ("RET-APP", "Validate the retail application scorecard", ["Run it"], 5,
     {"conclusion": "conditions", "note": "Discrimination holds. Buy Now Pay Later is now a fifth of new accounts and was absent from development, so the product mix is red; "
                                          "approve use with a BNPL overlay until a segment scorecard is built.",
      "reviewer": "Lama Al-Mutairi"}),
    ("RET-BEH", "Validate the retail behavioural scorecard", ["Run it", "Explain the red tests"], 2, None),
]


class _Ctx(assistant.Context):
    def __init__(self, store, thread_id: str, now: float):
        self.store, self.thread_id, self.now = store, thread_id, now

    def result(self, validation_id):
        v = self.store.validation(validation_id)
        return v["result"] if v else None

    def prior(self, scorecard_id, before_id):
        return []

    def run(self, plan):
        res = engine.run(plan)
        sc = res["scorecard"]
        v = self.store.add_validation(thread_id=self.thread_id, scorecard_id=plan["scorecard_id"], owner="", team="", seed=True, at=self.now,
                                      title=f"{sc['name']} v{sc['version']}: validation as of {plan['as_of']}", plan=res["plan"], result=res)
        return {"validation_id": v["validation_id"], "summary": res["summary"], "sample": res["sample"]}


def ensure(store) -> None:
    if store.has_seed():
        return
    now = time.time()
    for sid, first, rest, days_ago, review in SCRIPT:
        at = now - days_ago * DAY
        t = store.create_thread(owner="", team="", created_at=at)
        state = dict(t["state"])
        ctx = _Ctx(store, t["thread_id"], at)
        for k, text in enumerate([first, *rest]):
            answer = assistant.respond(state, text, ctx)
            store.add_turn(t["thread_id"], text, answer, at=at + 60 * (k + 1))
        name = engine.scorecards_by_id()[sid]["name"]
        store.save_thread(t["thread_id"], state, title=f"{name} validation", scorecard_id=sid, at=at + 600)
        if review:
            vid = state["validation_id"]
            store.set_review(vid, {"status": "reviewed", "conclusion": review["conclusion"], "note": review["note"], "reviewer": review["reviewer"],
                                   "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(at + 3600))})
