"""The deal a group view is about: one lookup for Deal Desk proposals and pipeline deals (PLAN_R12 I21).

U's `backend.dealdesk.registry_lookup` resolves DD and PL deals alike once merged; until then the R11
proposals store answers (DD-nn, DD-1nn) and the pipeline set (PL-nn).
"""
from __future__ import annotations

from typing import Any

from backend.dealdesk import paths

AS_OF = paths.AS_OF


def get(pid: str) -> dict[str, Any]:
    """The proposal dict (R11 shape: obligor, ask, financials, security). KeyError when unknown."""
    try:
        from backend.dealdesk.data import deals  # Session E: one deal registry (DD, PL, R12 demo deals)
        return deals.get(pid)
    except KeyError:
        pass  # e.g. a PL deal before dd_pipeline is populated: the R11 pipeline store below
    except Exception:  # noqa: BLE001 -- not merged: U's lookup, then the R11 stores
        pass
    try:
        from backend.dealdesk import registry_lookup  # Session U
        fn = getattr(registry_lookup, "get", None) or getattr(registry_lookup, "resolve", None)
        if fn is not None:
            p = fn(pid)
            if p:
                return p
    except KeyError:
        raise
    except Exception:  # noqa: BLE001 -- not merged yet
        pass
    from backend.dealdesk import proposals
    try:
        return proposals.get(pid)
    except KeyError:
        if str(pid).upper().startswith("PL"):
            from backend.dealdesk import pipeline
            for fn_name in ("get", "deal", "proposal"):
                fn = getattr(pipeline, fn_name, None)
                if fn is not None:
                    try:
                        p = fn(pid)
                    except Exception:  # noqa: BLE001
                        continue
                    if isinstance(p, dict) and "obligor" in p:
                        return p
        raise


def focal_id(p: dict[str, Any]) -> str:
    return str(p["obligor"].get("obligor_id") or "")
