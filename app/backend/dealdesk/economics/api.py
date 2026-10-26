"""R14 E API: the Deal Desk engines (prefix /api/v1/dealdesk/engines), mounted by one include_router line in the R14
block of backend/dealdesk/api.py. Signatures in docs/STATUS_R14_E.md ("ENGINES API"); kept stable for sessions f, p, i, g.

  GET  /engines/period
  GET  /engines/{pid}/approval?structure=ask|recommended|counter:<id>
  GET  /engines/{pid}/economics?structure=
  GET  /engines/{pid}/raroc-bridge?structure=
  GET  /engines/{pid}/capacity?structure=
  GET  /engines/{pid}/findings
  GET  /engines/{pid}/counter-offer
  GET  /engines/{pid}/why-fails
  POST /engines/{pid}/evaluate          {"structure": "ask"|"recommended"|"counter:<id>"|{terms}, "label": "..."}
  POST /engines/{pid}/structure/{what}  {"structure": {...terms}}  what = approval|economics|capacity (a user structure)
  GET  /engines/{pid}/summary?structure=   everything a tile row needs in one call (POST {structure} for a user structure)
"""
from __future__ import annotations

import math
from typing import Any, Callable

from fastapi import APIRouter, Body, HTTPException, Query

PREFIX = "/api/v1/dealdesk/engines"
router = APIRouter(prefix=PREFIX, tags=["r14-engines"])


def _clean(x: Any) -> Any:
    if isinstance(x, float):
        return None if (math.isnan(x) or math.isinf(x)) else x
    if isinstance(x, dict):
        return {str(k): _clean(v) for k, v in x.items() if not str(k).startswith("_")}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    try:
        import numpy as np
        if isinstance(x, np.generic):
            return _clean(x.item())
        if isinstance(x, np.ndarray):
            return _clean(x.tolist())
    except Exception:  # noqa: BLE001
        pass
    return x


def _run(fn: Callable[[], Any]) -> Any:
    from backend.dealdesk.economics.deal import UnknownDeal
    try:
        return _clean(fn())
    except UnknownDeal as e:
        raise HTTPException(404, f"unknown deal {e}") from e
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


def _spec(structure: str | None) -> Any:
    return None if structure in (None, "", "ask") else structure


@router.get("/period")
def period() -> dict[str, Any]:
    from backend.dealdesk.economics import reporting_period
    return reporting_period()


@router.get("/{pid}/approval")
def approval(pid: str, structure: str | None = Query(None)) -> dict[str, Any]:
    from backend.dealdesk.approval import approval_authority
    return _run(lambda: approval_authority(pid, _spec(structure)))


@router.get("/{pid}/economics")
def economics(pid: str, structure: str | None = Query(None)) -> dict[str, Any]:
    from backend.dealdesk.economics import economics as E
    return _run(lambda: E(pid, _spec(structure)))


@router.get("/{pid}/raroc-bridge")
def bridge(pid: str, structure: str | None = Query(None)) -> dict[str, Any]:
    from backend.dealdesk.economics import raroc_bridge
    return _run(lambda: raroc_bridge(pid, _spec(structure)))


@router.get("/{pid}/capacity")
def capacity(pid: str, structure: str | None = Query(None)) -> dict[str, Any]:
    from backend.dealdesk.capacity import capacity as C
    return _run(lambda: C(pid, _spec(structure)))


@router.get("/{pid}/findings")
def findings(pid: str) -> dict[str, Any]:
    from backend.dealdesk.findings import deal_findings
    return _run(lambda: deal_findings(pid))


@router.get("/{pid}/counter-offer")
def counter(pid: str) -> dict[str, Any]:
    from backend.dealdesk.findings import counter_offer
    return _run(lambda: counter_offer(pid))


@router.get("/{pid}/why-fails")
def why(pid: str) -> dict[str, Any]:
    from backend.dealdesk.findings import why_ask_fails
    return _run(lambda: why_ask_fails(pid))


@router.post("/{pid}/evaluate")
def evaluate(pid: str, body: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    from backend.dealdesk.findings import evaluate_structure
    return _run(lambda: evaluate_structure(pid, _spec(body.get("structure")), body.get("label")))


@router.post("/{pid}/structure/{what}")
def structure(pid: str, what: str, body: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    from backend.dealdesk.approval import approval_authority
    from backend.dealdesk.capacity import capacity as C
    from backend.dealdesk.economics import economics as E
    fn = {"approval": approval_authority, "economics": E, "capacity": C}.get(what)
    if fn is None:
        raise HTTPException(404, f"unknown engine {what}")
    return _run(lambda: fn(pid, _spec(body.get("structure"))))


RETURN_VIEWS = [
    ("deal", "Deal only (used for approval)", "The deal's own risk-adjusted profit over its capital, over its life. Nothing outside this facility counts."),
    ("relationship", "Whole relationship (for pricing talks)",
     "Adds the cross-sell income in the business case (after realisation and zakat) on the same capital."),
    ("relationship_deposits", "Relationship + deposits (for pricing talks)",
     "Also adds the value of the client's deposits: average balance × (FTP credit − profit paid) + flow fees, after the behavioural "
     "haircut, as a present value over the tenor on the same capital."),
]


def approval_basis() -> str:
    """The bank's chosen return basis for the approval test (policy setting, default the deal's own RAROC)."""
    import json
    from pathlib import Path
    try:
        b = json.loads((Path(__file__).with_name("return_basis.json")).read_text()).get("approval_basis", "deal")
    except (OSError, ValueError):
        b = "deal"
    return b if b in {k for k, _, _ in RETURN_VIEWS} else "deal"


def return_views(bridge: dict[str, Any], hurdle: float | None) -> dict[str, Any]:
    """R15 b (L13 (2), L8 (a)): the three labelled return views of one deal, from the one RAROC bridge (N2)."""
    steps = bridge.get("steps") or []
    basis = approval_basis()
    out = []
    for i, (key, label, line) in enumerate(RETURN_VIEWS):
        st = steps[i] if i < len(steps) else None
        r = st.get("raroc") if st else None
        out.append({"key": key, "label": label, "line": line, "raroc": r, "formula": (st or {}).get("what"),
                    "clears": (r is not None and hurdle is not None and r >= hurdle - 1e-12), "used_for_approval": key == basis})
    what = {"deal": "the deal's own RAROC", "relationship": "the whole-relationship RAROC",
            "relationship_deposits": "the relationship RAROC with deposits"}[basis]
    return {"basis": basis, "views": out,
            "rule": f"The approval test uses {what} (the bank's policy setting). The other views are for pricing negotiation only."}


FEATURE_WORDS = {
    "segment_code": "segment", "subsegment_code": "sub-segment", "product_code": "product", "collateral_code": "collateral type",
    "grade_rank": "rating grade", "pd_ttc": "through-the-cycle PD", "pd_12m_input": "starting PD", "lgd_input": "LGD",
    "secured_share": "secured share", "haircut_pct": "collateral haircut", "log_ead": "exposure size", "ccf": "credit conversion factor",
    "undrawn_share": "undrawn share", "nfo": "non-funded share", "leverage_x": "leverage", "dscr_x": "DSCR", "current_ratio_x": "current ratio",
}


def _and(xs: list[str]) -> str:
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]


def pd_range_note(oor: dict[str, Any] | None, master_pd: float | None) -> dict[str, Any] | None:
    """R15 b (L13 (4)): what "outside the training range" means and what was done about it, in plain words."""
    if not oor or oor.get("status") == "in_range":
        return None
    feats = [f for f in oor.get("features") or [] if f.get("status") != "in_range"]
    words = list(dict.fromkeys(FEATURE_WORDS.get(str(f.get("feature")), str(f.get("feature")).replace("_", " ")) for f in feats[:4]))
    names = _and(words) if words else "some inputs"
    edge = oor.get("status") == "edge"
    ms = f"{master_pd * 100:.2f}%" if isinstance(master_pd, (int, float)) else "n/a"
    return {"label": "PD less certain: borrower at the edge of the model's range" if edge else "PD less certain: borrower outside the model's range",
            "meaning": (f"This borrower's {names} {'is' if len(words) == 1 else 'are'} {'at the edge of' if edge else 'outside'} the values the PD model was fitted on, "
                        "so the model's PD is less reliable here."),
            "done": (f"No extra floor or overlay is added for this: the model holds its score flat beyond the fitted range, and the "
                     f"bank's master-scale PD for the rating ({ms}) is shown beside it as the cross-check. Treat the PD as indicative.")}


def summary_of(pid: str, structure: Any = None) -> dict[str, Any]:
    """Everything the tile row and the Recommendation header need, from the engines, in one call."""
    from backend.dealdesk.approval import approval_authority
    from backend.dealdesk.capacity import capacity as C
    from backend.dealdesk.economics import economics as E
    from backend.dealdesk.findings import deal_findings
    e = E(pid, structure)
    ap = approval_authority(pid, structure)
    cap = C(pid, structure)
    fs = deal_findings(pid)
    return {"proposal_id": e["proposal_id"], "structure": e["structure"], "period": e["period"],
            "raroc": e["raroc"], "sva": e["sva"], "basis": e["basis"], "el": e["el"], "rwa": e["rwa"], "pd": e["pd"], "lgd": e["lgd"],
            "ead_y1": e["ead_y1"], "bands": e["bands"], "bridge": e["bridge"],
            "approval": {k: ap[k] for k in ("level", "rank", "rule", "binding", "reasons", "exposure_after_sar_mn", "expected_days",
                                            "documents_missing", "approvable", "exceptions")},
            "capacity": {k: cap[k] for k in ("method", "method_label", "formula", "capacity_sar_mn", "ask_sar_mn", "within", "severity",
                                             "finding_title")},
            "pd_range": _pd_range(pid, structure, e),
            "findings": {"counts": fs["counts"], "chips": fs["chips"], "verdict": fs["verdict"]},
            "return_views": return_views(e["bridge"], e["raroc"].get("hurdle")),
            "capacity_cross_check": _cross_check(cap)}


def _pd_range(pid: str, structure: Any, e: dict[str, Any]) -> dict[str, Any] | None:
    from backend.dealdesk.economics import deal as D
    try:
        oor = (D.analysis(pid, D.structure_terms(pid, structure)["terms"]).get("pd") or {}).get("out_of_range")
    except Exception:  # noqa: BLE001  (a user structure the resolver does not know: no chip text, never an error)
        return None
    return pd_range_note(oor, (e.get("pd") or {}).get("master_scale_12m"))


def _cross_check(cap: dict[str, Any]) -> list[dict[str, Any]]:
    """R15 b (L13 (3)): one capacity number per product; the other measures are labelled cross-checks, never a second answer."""
    alt = cap.get("alt") or {}
    out = []
    if cap.get("method") == "borrowing_base":
        out.append({"label": "Cross-check: DSCR and leverage", "value_sar_mn": min(v for v in (alt.get("ebitda_based_sar_mn"), alt.get("cash_flow_based_sar_mn"))
                                                                                if isinstance(v, (int, float))) if any(isinstance(v, (int, float)) for v in alt.values()) else None,
                    "line": "The lower of the leverage and cash-flow limits; not used to size a working-capital line."})
    else:
        if isinstance(alt.get("ebitda_based_sar_mn"), (int, float)):
            out.append({"label": "Cross-check: leverage limit alone", "value_sar_mn": alt["ebitda_based_sar_mn"],
                        "line": "What the leverage ceiling alone would allow; capacity is the lower of this and the cash-flow limit, "
                                "so it is not a second answer."})
    return out


@router.get("/{pid}/summary")
def summary(pid: str, structure: str | None = Query(None)) -> dict[str, Any]:
    return _run(lambda: summary_of(pid, _spec(structure)))


@router.post("/{pid}/summary")
def summary_post(pid: str, body: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    """The same summary for a user structure ({"structure": {terms}})."""
    return _run(lambda: summary_of(pid, _spec(body.get("structure"))))
