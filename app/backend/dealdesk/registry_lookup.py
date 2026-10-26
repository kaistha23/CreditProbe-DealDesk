"""R12 Session U (PLAN_R12 §1.2, I21): one deal registry for Deal Desk proposals (DD-xx, uploads), the pending
pipeline set (PL-xx) and the R12 demo deals (R12-xxx).

Every deal opens the same deal page. `proposals.get` falls back to `extra_proposal` here, so the bundle, the
thread, Optimise, Stress and Review resolve a PL or R12 deal exactly as they resolve a DD one. Once Session E's
data layer is merged, the pipeline set and the demo deals are read from Data Domains (`dd_pipeline`, `dd_deal`)
through the shared reader; before, the pipeline set comes from the R11 pipeline module (feature check).

The pipeline banner reads the optimiser's decision and reason for the deal: the latest pipeline run that included
it, else the default run (every pending deal, the budgets from the risk appetite).
"""
from __future__ import annotations

import copy
from typing import Any


def _e_deals():
    try:
        from backend.dealdesk.data import deals
        return deals
    except Exception:  # noqa: BLE001 - feature check: Session E's data layer
        return None


def pipeline_set() -> dict[str, dict[str, Any]]:
    """The PL set: dd_pipeline through E's reader when it has rows, else the R11 pipeline set."""
    d = _e_deals()
    if d is not None:
        try:
            got = d.pipeline_set()
            if got:
                for p in got.values():
                    p.setdefault("source", "pipeline")
                return got
        except Exception:  # noqa: BLE001
            pass
    from backend.dealdesk import pipeline
    return pipeline.seeded_set()


def demo_set() -> dict[str, dict[str, Any]]:
    """The R12 demo deals (twins, syndicated, escrow, SME) from dd_deal.proposal_json; empty before E's merge."""
    d = _e_deals()
    if d is None:
        return {}
    try:
        out = d._demo()
    except Exception:  # noqa: BLE001
        return {}
    for p in out.values():
        p.setdefault("source", "r12_demo")
    return out


def extra_proposal(pid: str) -> dict[str, Any]:
    """A pipeline-set application or an R12 demo deal by ID (KeyError when neither). Never calls `proposals.get`,
    so `proposals.get` can fall back here without a loop."""
    for s in (pipeline_set(), demo_set()):
        if pid in s:
            return copy.deepcopy(s[pid])
    raise KeyError(pid)


#: R12 S1 name kept for callers written against the first version.
pipeline_proposal = extra_proposal


def source(pid: str) -> str:
    """"pipeline", "r12_demo", "dealdesk" or "" when unknown."""
    from backend.dealdesk import proposals
    if pid in proposals.all_proposals():
        return "dealdesk"
    if pid in pipeline_set():
        return "pipeline"
    if pid in demo_set():
        return "r12_demo"
    return ""


def resolve(pid: str) -> dict[str, Any]:
    """The deal as the deal page reads it, whichever set holds it, with its source. KeyError when unknown."""
    from backend.dealdesk import proposals
    src = source(pid)
    if not src:
        raise KeyError(pid)
    return {"proposal": proposals.get(pid), "source": src}


def all_deals() -> list[dict[str, Any]]:
    """Every deal the desk knows: Deal Desk proposals (seeded and uploaded), the R12 demo deals, then the pipeline set."""
    from backend.dealdesk import proposals
    dd = sorted(proposals.all_proposals().values(), key=lambda p: p["proposal_id"])
    seen = {p["proposal_id"] for p in dd}
    demo = [copy.deepcopy(p) for k, p in sorted(demo_set().items()) if k not in seen]
    seen |= {p["proposal_id"] for p in demo}
    pl = [copy.deepcopy(p) for k, p in sorted(pipeline_set().items()) if k not in seen]
    for p in pl:
        p.setdefault("source", "pipeline")
    return dd + demo + pl


def _decision_row(res: dict[str, Any], pid: str) -> dict[str, Any] | None:
    for d in res.get("decisions", []):
        if d.get("proposal_id") == pid:
            return d
    return None


def pipeline_decision(pid: str, compute: bool = True) -> dict[str, Any] | None:
    """The optimiser's decision on a pending deal: approve or decline, the structure, the reason and what gets it in.
    The latest cached run that included the deal answers first; otherwise the default run is solved (cached after).
    None when the deal is not pending in the pipeline."""
    from backend.dealdesk import pipeline
    hit, res_used = None, None
    for res in reversed(list(pipeline._RESULTS.values())):
        hit = _decision_row(res, pid)
        if hit:
            res_used = res
            break
    if hit is None:
        if not compute:
            return None
        try:
            from backend.dealdesk.r11_pipeline_api import _SOLVE_LOCK
            with _SOLVE_LOCK:
                res_used = pipeline.optimise(frontier=False, gets_in=True)
        except KeyError:
            return None
        hit = _decision_row(res_used, pid)
        if hit is None:
            return None
    o = hit.get("option") or {}
    return {
        "proposal_id": pid,
        "decision": hit.get("decision"),
        "structure": o.get("label") if o else None,
        "amount_sar_mn": o.get("amount_sar_mn") if o else None,
        "reason": hit.get("reason", ""),
        "gets_in": (hit.get("gets_in") or {}).get("text") if hit.get("gets_in") else None,
        "headline": (res_used or {}).get("headline", ""),
    }


def banner(pid: str, compute: bool = True) -> dict[str, Any]:
    """What the deal page shows above the steps for a deal opened from the pipeline."""
    src = source(pid)
    out: dict[str, Any] = {"proposal_id": pid, "source": src, "in_pipeline": False, "decision": None,
                           "back_href": "/deal-desk?mode=pipeline"}
    if not src:
        return out
    from backend.dealdesk import pipeline
    out["in_pipeline"] = pid in {p["proposal_id"] for p in pipeline.pending()}
    if out["in_pipeline"]:
        out["decision"] = pipeline_decision(pid, compute=compute)
    return out


__all__ = ["all_deals", "banner", "demo_set", "extra_proposal", "pipeline_decision", "pipeline_proposal", "pipeline_set",
           "resolve", "source"]
