"""R14 i shared plumbing: the structure the panels read, traced figures, Data Domains reads, plain words.

Reuses the R13 IA plumbing (backend.dealdesk.intel.approval.common: deal resolution, cached engine runs, figures whose
source is a Data Domains row or an engine run on the dd_deal row). Adds:

  * `structure(pid, which, terms)` - the structure a panel works on (PLAN_R14 K29 #4 "questions read the selected
    structure"): explicit terms (the page's own) > the structure the user selected (session f's selection, read
    through `_selected_hook` when it exists) > the Optimise recommended structure (stress_lab.recommended_terms,
    the same one the deal view shows) > the ask. The label says which one was used.
  * `bfig` - a figure from a row of any registered relation (cockpit, deposits, origination, bureau ...).
  * `plain(what, proposes, todo)` - the "In plain words" block (K34): three lines, at most ~60 words, deterministic.
"""
from __future__ import annotations

import functools
import json
import math
from typing import Any

from backend.dealdesk.data import store
from backend.dealdesk.intel.approval import common as C

UnknownDeal = C.UnknownDeal
resolve_id = C.resolve_id
proposal = C.proposal
analysis = C.analysis
rows = C.rows
fig = C.fig
efig = C.efig
rfig = C.rfig
pct = C.pct
mn = C.mn
row_source = C.row_source
deal_source = C.deal_source

LABEL = {"terms": "Your structure", "selected": "Selected structure", "recommended": "Recommended structure", "ask": "The ask"}


# ------------------------------------------------------------------ the structure a panel reads

def _selected_hook(pid: str) -> tuple[dict[str, Any] | None, str, str]:
    """Session f's structure set (dd_structure_set, published when the user selects a structure): the selected row,
    else f's Recommended row (the Review counter-proposal). (terms, label, kind); (None, "", "") before f is merged."""
    rows = C.rows("dd_structure_set", proposal_id=pid)
    sel = next((r for r in rows if int(r.get("selected_flag") or 0)), None)
    if sel and isinstance(sel.get("terms_json"), dict):
        return sel["terms_json"], f"Selected structure: {sel.get('label') or sel['structure_key']}", "selected"
    rec = next((r for r in rows if r.get("role") == "recommended"), None)
    if rec and isinstance(rec.get("terms_json"), dict):
        return rec["terms_json"], LABEL["recommended"], "recommended"
    return None, "", ""


@functools.lru_cache(maxsize=128)
def _recommended(pid: str, pv: str) -> str:
    from backend.dealdesk import stress_lab
    try:
        t, lab = stress_lab.recommended_terms(proposal(pid))
    except Exception:  # noqa: BLE001 - no recommended structure: the ask is used
        t, lab = None, ""
    return json.dumps([t, lab], default=str)


def structure(pid: str, which: str = "selected", terms: dict[str, Any] | None = None) -> dict[str, Any]:
    """{"kind", "label", "terms" (None = the ask), "note"} for the panel's structure."""
    pid = resolve_id(pid)
    if terms:
        return {"kind": "terms", "label": LABEL["terms"], "terms": terms, "note": "Terms passed by the page."}
    if which in ("selected", "recommended"):
        if which == "selected":
            t, lab, kind = _selected_hook(pid)
            if t:
                return {"kind": kind, "label": lab, "terms": t,
                        "note": "The structure selected on the Structure step." if kind == "selected" else
                        "No structure selected yet: the Recommended structure of the structure set is used."}
        from backend.dealdesk import params
        t, lab = json.loads(_recommended(pid, json.dumps(params.versions(), sort_keys=True)))
        if t:
            return {"kind": "recommended", "label": LABEL["recommended"], "terms": t,
                    "note": f"No structure selected yet: the Optimise recommended structure ({lab.lower() or 'closest to the ask'}) is used."}
    return {"kind": "ask", "label": LABEL["ask"], "terms": None, "note": "The terms as asked."}


def terms_of(st: dict[str, Any]) -> Any:
    """What a deal_source records as the terms of a figure: 'ask' or the term dict."""
    return st["terms"] if st.get("terms") else "ask"


# ------------------------------------------------------------------ figures from any registered relation

def bfig(relation: str, row: dict[str, Any], column: str, unit: str = "", label: str = "") -> dict[str, Any]:
    src = store.trace(relation, row)
    src["column"] = column
    v = row.get(column)
    if hasattr(v, "item"):
        v = v.item()
    if isinstance(v, float) and math.isnan(v):
        v = None
    return fig(v, unit, src, label)


def frame(relation: str, **filters: Any):
    """A registered relation's rows as a DataFrame (empty when unpublished)."""
    import pandas as pd
    try:
        return store.dd_frame(relation, **filters)
    except Exception:  # noqa: BLE001
        return pd.DataFrame()


def records(df) -> list[dict[str, Any]]:  # noqa: ANN001
    if df is None or len(df) == 0:
        return []
    out = []
    for r in df.astype(object).where(df.notna(), None).to_dict("records"):
        out.append({k: (v.item() if hasattr(v, "item") else v) for k, v in r.items()})
    return out


def finite(x: Any) -> float | None:
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


# ------------------------------------------------------------------ plain words (K34)

MAX_WORDS = 60  # K34 (session u's checkPlainWords)


def clip(s: str, n: int) -> str:
    """At most n words, ending with an ellipsis when cut."""
    w = s.split()
    return s if len(w) <= n else " ".join(w[:n]).rstrip(",;:.") + "…"


def plain(what: str, proposes: str, todo: str) -> dict[str, Any]:
    """The 'In plain words' block: what this is, what it proposes here (with its numbers), what to do (<= 60 words)."""
    lines = [s.strip() for s in (what, proposes, todo) if s and s.strip()]
    while sum(len(x.split()) for x in lines) > MAX_WORDS:
        i = max(range(len(lines)), key=lambda k: len(lines[k].split()))
        over = sum(len(x.split()) for x in lines) - MAX_WORDS
        lines[i] = clip(lines[i], max(6, len(lines[i].split()) - over))
    return {"lines": lines, "words": sum(len(s.split()) for s in lines)}


def bps(x: float | None, dp: int = 0) -> str:
    return "n/a" if x is None else f"{x:,.{dp}f} bps"


def ordinal(x: float | None) -> str:
    if x is None:
        return "n/a"
    n = int(round(x))
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def the(st: dict[str, Any]) -> str:
    """'the recommended structure', 'your structure', 'the ask' (for sentences)."""
    lab = st["label"]
    return "your structure" if lab == LABEL["terms"] else ("the " + lab[:1].lower() + lab[1:])


def cache_key() -> str:
    """Engine results are cached on this: parameter versions and the versions of the relations a selection or a review
    changes (structure set, findings, conditions), so a new selection is read at once."""
    from backend.dealdesk import params
    vs = {}
    for rel in ("dd_structure_set", "dd_review_finding", "dd_condition", "dd_stress_result"):
        try:
            vs[rel] = store.version_of(rel)
        except Exception:  # noqa: BLE001 - not registered on this branch
            vs[rel] = 0
    return json.dumps([params.versions(), vs], sort_keys=True, default=str)
