"""The Deal Desk edition's seed of the desk-thread store (PLAN_DEALDESK_EDITION Round C).

On the service's first start, when the store holds no desk threads: two desk threads answered through the same
conversation path POST /desk/ask uses (the deterministic planner, so no model is called at startup), and two saved
analyses computed by the engine (DD-02's counter-offer at SAIBOR + 250, DD-06's recommended structure). Everything is
wrapped: seeding never stops the service. Only in the Deal Desk edition; the full product's store starts empty.
"""
from __future__ import annotations

import os
from typing import Any

SEED_USER: dict[str, Any] = {"username": "khalid", "team": "corporate"}
QUESTIONS = ("Which proposals breach a hard limit?", "How much real-estate headroom is left this quarter?")
ANALYSES = (("DD-02", "Counter-offer at SAIBOR + 250", {"margin_bps": 250}),
            ("DD-06", "Recommended structure", {"margin_bps": 190, "commitment_fee_bps": 30.3, "cash_margin_pct": 30}))


def _desk_threads(store: Any) -> int:
    from backend.dealdesk_thread import convo
    from backend.dealdesk_thread import store as store_mod

    done = 0
    for q in QUESTIONS:
        try:
            th = store.create_desk_thread(SEED_USER["username"], q)
            key = store_mod.desk_key(th["thread_id"])
            answer = convo.answer(store, None, q, SEED_USER, history=store.turns(key))
            store.add_turn(key, SEED_USER["username"], q, answer)
            store.touch_desk_thread(th["thread_id"])
            done += 1
        except Exception:  # noqa: BLE001 - one question failing does not stop the others
            continue
    return done


def _analyses(store: Any) -> int:
    from backend.dealdesk_thread import engine

    done = 0
    for pid, name, terms in ANALYSES:
        try:
            p = engine.get(f"/proposals/{pid}")["proposal"]
            res = engine.post("/compute", {"proposal_id": pid, "terms": terms})
            store.save_analysis(pid, SEED_USER["username"], str(SEED_USER.get("team") or ""), name,
                                {"terms": res["terms"], "metrics": res["metrics"], "approval": res["approval"],
                                 "trace_id": res.get("trace_id"), "obligor": p["obligor"]["name"], "optimisation_trace": None})
            done += 1
        except Exception:  # noqa: BLE001
            continue
    return done


def apply(store: Any) -> dict[str, int]:
    """Seed the store when the edition is Deal Desk and it has no desk threads yet. Never raises."""
    out = {"threads": 0, "analyses": 0}
    try:
        from backend.v5common.edition import is_dealdesk
        if not is_dealdesk() or store.desk_threads(None, 1):
            return out
        was = os.environ.get("CONVO_ASSISTANT_MODEL")
        os.environ["CONVO_ASSISTANT_MODEL"] = "off"  # seeded content: the deterministic planner, no model cost at startup
        try:
            out["threads"] = _desk_threads(store)
        finally:
            if was is None:
                os.environ.pop("CONVO_ASSISTANT_MODEL", None)
            else:
                os.environ["CONVO_ASSISTANT_MODEL"] = was
        if not store.analyses():
            out["analyses"] = _analyses(store)
    except Exception:  # noqa: BLE001 - seeding never stops the service
        pass
    return out
