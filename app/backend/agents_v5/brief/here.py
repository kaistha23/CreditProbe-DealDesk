"""R15 a (L9): Noor answers in the page context: the deal, the step and the stress run on screen.

R14 UAT (DD-02, Stress step): "how is this failing on all stress scenario?" went to What-If and opened a book-level
thread (EAD SAR 154bn…). Now the router reads the page context first. On a deal page a question is answered there,
about that deal, unless it asks about the book or explicitly for a book scenario; "this", "it", "here" are the object
on screen. For a deal's Stress step the answer explains the run on screen: which structures, which scenario breaks
first at each severity, the driver chain (revenue → EBITDA → DSCR / leverage) and the cheapest fix (Stress-proof).

Deterministic (N4): a cue table equal to `frontend/src/components/noor/noor-context.ts` (HERE-BEGIN … HERE-END, kept
equal by tests/v5/noor/test_r15_here.py) and rule-based writers over the Deal Desk engines (N2: one engine per fact):
the stress matrix (`stressproof.matrix.run`, the R12 Stress Lab ladder) and the stress-proof solver
(`stressproof.solver.solve`, read only: nothing is added to the structure set until the user presses Stress-proof).
"""
from __future__ import annotations

import re
import threading
from typing import Any

# HERE-BEGIN (the cues; equal to noor-context.ts)
HERE_CUES: dict[str, tuple[str, ...]] = {
    "book": (
        r"\b(the|our|whole|entire|total) (book|portfolio)\b",
        r"\bbook[- ](level|wide)\b",
        r"\bbank[- ]wide\b",
        r"\bacross (the )?(book|portfolio|bank|sectors|all (deals|borrowers|clients))\b",
        r"\b(all|every) (our )?(borrowers|obligors|clients|counterparties|sectors)\b",
        r"\bin what[- ]if\b",
        r"\b(open|start|run|create|build) (a |an )?(new )?(book )?(what[- ]if|scenario)\b",
        r"\bwhat[- ]if (the|oil|gdp|rates?|brent|unemployment)\b",
    ),
    "deictic": (
        r"\b(this|it|its|it's|here|these|those|that one|this one|on screen|on the screen)\b",
    ),
    "stress": (
        r"\bstress(ed|es|ing)?\b",
        r"\bscenarios?\b",
        r"\b(fail|fails|failing|failed|break|breaks|breaking|broke|survive|survives|surviving)\b",
        r"\b(mild|moderate|severe)\b",
        r"\bstress[- ]?proof\b",
        r"\b(shock|shocks|downturn)\b",
    ),
    "deal_terms": (
        r"\b(raroc|sva|pricing|priced|price|margin|approval|approve|approver|hurdle|fees?|tenor|amount|collateral|guarantee|limit)\b",
    ),
    "elsewhere": (
        r"\b(build|create|make|design|set up)\b.{0,40}\b(dashboard|lens)\b",
    ),
}
# HERE-END

_C = {k: tuple(re.compile(p, re.I) for p in v) for k, v in HERE_CUES.items()}
SEVERITIES = ("mild", "moderate", "severe")
STEP_LABEL = {"proposal": "Proposal", "review": "Review", "analysis": "Analysis", "structure": "Structure", "stress": "Stress",
              "recommendation": "Recommendation", "monitoring": "Monitoring"}


def _any(kind: str, q: str) -> bool:
    return any(p.search(q) for p in _C[kind])


def step_label(step: str | None) -> str:
    return STEP_LABEL.get(step or "", (step or "").capitalize())


def route_here(question: str, context: dict[str, Any] | None) -> dict[str, Any]:
    """{here: bool, topic?, reason}: answered on the page (a deal) or by the usual routes (with the reason why)."""
    q = " ".join(str(question or "").split())
    ctx = context or {}
    deal = str(ctx.get("deal_id") or "")
    if not q or not deal:
        return {"here": False, "reason": None}
    if _any("elsewhere", q):
        return {"here": False, "reason": f"Asks for a dashboard, so Lenses builds it rather than answering on {deal}."}
    if _any("book", q) and deal.lower() not in q.lower():
        return {"here": False, "reason": f"Asks about the book, not {deal}, so the book engines answer it."}
    step = ctx.get("step")
    on_stress = step == "stress" or bool(ctx.get("stress_on_screen"))
    topic = "stress" if _any("stress", q) or (on_stress and _any("deictic", q) and not _any("deal_terms", q)) else "deal"
    where = f"{deal}, {step_label(step)} step" if step else deal
    return {"here": True, "topic": topic,
            "reason": f"About the stress run on screen ({where})." if topic == "stress" else f"About the deal on screen ({where})."}


# ------------------------------------------------------------------ number words (the Deal Desk's own formats)

def _x(v: Any) -> str:
    return "–" if v is None else f"{float(v):.2f}x"


def _pct(v: Any, dp: int = 1) -> str:
    return "–" if v is None else f"{float(v) * 100:.{dp}f}%"


def _limit_of(first_text: str) -> str:
    """'X (mild) breaks first: DSCR 1.06x against 1.20x; …' → 'DSCR 1.06x against 1.20x; …'."""
    return first_text.split("breaks first: ", 1)[1].rstrip(".") if "breaks first: " in first_text else ""


def chain(s: dict[str, Any]) -> str:
    """The driver chain of the structure's first break: the shock (revenue, receivables, margin) → EBITDA → DSCR and
    leverage against their limits, from the matrix interpretation (the Stress Lab ladder's own steps)."""
    it = s.get("interpretation") or {}
    why = str(it.get("why") or "")
    parts = [p.strip() for p in why.split("; ") if p.strip()]
    shock = parts[0] if parts else ""
    ebitda = "; ".join(parts[1:]) if len(parts) > 1 else ""
    tests = _limit_of(str(it.get("first") or ""))
    base = f"DSCR {_x(s.get('dscr'))} before stress"
    bits = [b for b in (shock.replace("revenue", "Revenue", 1) if shock.startswith("revenue") else shock, ebitda, tests) if b]
    return " → ".join(bits) + (f" ({base})" if tests else "")


def _counts(s: dict[str, Any]) -> dict[str, tuple[int, int]]:
    out: dict[str, tuple[int, int]] = {}
    for sev in SEVERITIES:
        at = [r for r in s.get("scenarios") or [] if r.get("applicable") and r.get("severity") == sev]
        out[sev] = (sum(1 for r in at if r.get("breaks")), len(at))
    return out


# ------------------------------------------------------------------ the stress run on screen

def _matrix(pid: str, keys: list[str] | None) -> dict[str, Any]:
    from backend.dealdesk.stressproof import matrix as MX
    try:
        return MX.run(pid, keys or None)
    except KeyError:
        return MX.run(pid, None)


def stress_answer(question: str, ctx: dict[str, Any], m: dict[str, Any] | None = None) -> dict[str, Any]:
    pid = str(ctx["deal_id"])
    m = m or _matrix(pid, [str(k) for k in ctx.get("structures") or []])
    obligor = str((m.get("obligor") or {}).get("name") if isinstance(m.get("obligor"), dict) else m.get("obligor") or "")
    cols = m["structures"]
    stressed = [c for c in cols if c.get("stressed")]
    labels = ", ".join(c["label"] for c in cols)
    on = f"On screen: {pid}" + (f" ({obligor})" if obligor else "") + f", Stress step, {len(cols)} structure{'s' if len(cols) != 1 else ''}: {labels}."
    lines = [on]
    rows = []
    for c in cols:
        if not c.get("stressed"):
            lines.append(f"{c['label']}: not stressed, it fails before any stress ({c.get('base_reason') or 'base case'}).")
            rows.append({"structure": c["label"], "key": c["key"], "status": "fails_before_stress", "survives_up_to": "none",
                         "cells": {sev: {"passes": None, "first": "fails before stress"} for sev in SEVERITIES}})
            continue
        n = _counts(c)
        broke = sum(b for b, _ in n.values())
        total = sum(t for _, t in n.values())
        up = c.get("survives_up_to") or "none"
        held = "survives every applicable scenario" if broke == 0 else (
            "breaks at the mildest shock" if up == "none" else f"holds up to {up}")
        firsts = []
        cells = {}
        for cell in c.get("cells") or []:
            fb = cell.get("first_break")
            sev = cell["severity"]
            b, t = n.get(sev, (0, 0))
            cells[sev] = {"passes": bool(cell.get("passes")), "first": fb["label"] if fb else ("no applicable scenario" if not cell.get("scenarios") else "nothing breaks"),
                          "tests": fb["test_labels"] if fb else [], "breaking": b, "applicable": t, "min_dscr": cell.get("min_dscr")}
            if fb:
                firsts.append(f"{sev} {fb['label']} ({', '.join(fb['test_labels'][:2])})")
        lines.append(f"{c['label']}: {held}; {broke} of {total} applicable scenarios break it."
                     + (f" First to break: {'; '.join(firsts)}." if firsts else ""))
        rows.append({"structure": c["label"], "key": c["key"], "status": "stressed", "survives_up_to": up, "cells": cells,
                     "broken": broke, "applicable": total})
    worst = next((c for c in stressed if c.get("interpretation", {}).get("why")), None)
    if worst:
        lines.append(f"Why ({worst['label']}): {chain(worst)}.")
    drivers = m.get("drivers") or []
    weak = [c for c in stressed if (c.get("survives_up_to") or "none") in ("none", "mild")]
    target = "moderate"
    fix_from = None
    if weak:
        sel = next((c for c in weak if c.get("role") == "recommended"), weak[0])
        fix_from = sel["key"]
        lines.append(f"Cheapest fix: the Stress-proof solver's smallest change set for {sel['label']} to survive {target} "
                     "(amount, covenants, pricing, security) is below; nothing is added until you press Stress-proof.")
    elif stressed:
        lines.append("Every stressed structure holds to moderate; severe is monitored, not designed for.")
    plain = [
        f"This answers on {pid}'s stress run on screen, not the book.",
        (f"{weak[0]['label']} breaks at {_first_sev(weak[0])} shocks." if weak else "The stressed structures hold to moderate shocks."),
        (f"It breaks through {drivers[0].lower()} first: revenue falls, EBITDA falls, so DSCR and leverage cross their limits."
         if drivers and worst else "Each cell is a pass or fail on DSCR, leverage, covenants, rating, stage and hard limits."),
        ("Stress-proof finds the cheapest change that survives a moderate shock." if weak else "Severe shocks are watched through monitoring."),
    ]
    reg = m.get("regime") or {}
    return {"topic": "stress", "deal_id": pid, "obligor": obligor, "step": "stress", "keys": m.get("keys") or [c["key"] for c in cols],
            "title": f"{pid} under stress: the run on screen", "lines": lines, "plain_words": plain, "rows": rows,
            "drivers": drivers, "fix_from": fix_from, "fix_target": target if fix_from else None,
            "regime": str(reg.get("label") or ""), "regime_line": m.get("regime_line") or "",
            "basis": f"Deal Desk stress matrix on {pid} ({m.get('basis') or 'stress2 ladder'}); sensitivities {m.get('sensitivity_version') or 'current'}.",
            "actions": [{"label": "Open Stress-proof", "kind": "scroll", "target": '[data-testid="flow-stress-proof"]',
                         "href": f"/deal-desk/{pid}?step=stress"},
                        {"label": "Ask about the book in What-If instead", "kind": "book"}],
            "spoken": " ".join(lines[1:4])}


def _first_sev(c: dict[str, Any]) -> str:
    return next((x["severity"] for x in c.get("cells") or [] if x.get("first_break")), "mild")


_FIX: dict[tuple[str, str, str], dict[str, Any]] = {}
_FIX_LOCK = threading.Lock()


def cheapest_fix(pid: str, from_key: str, target: str = "moderate") -> dict[str, Any]:
    """The smallest change set that lets `from_key` survive `target` (the stress-proof solver, read only), cached."""
    from backend.dealdesk.stressproof import solver as SV
    k = (pid, from_key, target)
    with _FIX_LOCK:
        if k in _FIX:
            return _FIX[k]
    sol = SV.solve(pid, from_key, target)
    ch = sol.get("changes") or []
    unc = sol.get("uncured") or []
    label = (sol.get("start") or {}).get("label") or from_key
    if ch and not unc:
        line = f"Cheapest fix for {label} to survive {target}: " + "; ".join(c["text"] for c in ch) + "."
    elif ch:
        line = (f"Stress-proofing {label} to {target} changes: " + "; ".join(c["text"] for c in ch[:3])
                + f". It still does not survive: {unc[0]}. Not curable by structure alone: accept and monitor, or decline.")
    else:
        line = f"No change to {label} helps against {target}: " + (unc[0] if unc else "the obligor's own finances break") + "."
    asks = [c["client"] for c in ch if c.get("client")]
    out = {"deal_id": pid, "from_key": from_key, "target": target, "line": line, "changes": [
        {"text": c["text"], "client": c.get("client") or "", "cost": c.get("cost") or ""} for c in ch],
        "uncured": unc, "asks": asks, "survives": bool(ch and not unc),
        "basis": "Stress-proof solver (stressproof.solver.solve), read only: press Stress-proof on the page to add it."}
    with _FIX_LOCK:
        _FIX[k] = out
    return out


# ------------------------------------------------------------------ the deal on screen (another step)

def deal_answer(question: str, ctx: dict[str, Any]) -> dict[str, Any]:
    from backend.dealdesk.stressproof import structures as ST
    pid = str(ctx["deal_id"])
    s = ST.structure_set(pid)
    obligor = s.get("obligor") or {}
    name = obligor.get("name", "") if isinstance(obligor, dict) else str(obligor)
    rows = s["rows"]
    sel = next((r for r in rows if r["key"] == s.get("selected")), rows[0] if rows else None)
    ask = next((r for r in rows if r["key"] == "ask"), None)
    step = ctx.get("step")
    lines = [f"On screen: {pid}" + (f" ({name})" if name else "") + (f", {step_label(step)} step." if step else ".")]
    for r in [x for x in (ask, sel) if x] if sel is not ask else [sel]:
        appr = (r.get("approval") or {}).get("level") if isinstance(r.get("approval"), dict) else r.get("approval")
        verdict = (f"fails before stress ({r['not_recommendable_reason']})" if r.get("fails_before_stress")
                   else "clears the hurdle" if r.get("clears_hurdle") else "below the hurdle")
        lines.append(f"{r['label']}: SAR {float(r.get('amount_sar_mn') or 0):,.1f}m, RAROC {_pct(r.get('raroc'), 2)} against the "
                     f"{_pct(r.get('hurdle'))} hurdle, DSCR {_x(r.get('dscr'))}, {verdict}" + (f"; approval {appr}." if appr else "."))
    if sel and sel.get("covenant_tightest"):
        lines.append(f"Tightest covenant on {sel['label']}: {sel['covenant_tightest']}.")
    lines.append("Ask about its stress, structure or numbers here; Deal Desk's desk thread answers anything wider.")
    plain = [f"This answers on {pid}, the deal on screen.",
             f"The selected structure is {sel['label'] if sel else 'not set'}.",
             "The numbers come from the Deal Desk engine, the same as on the page."]
    return {"topic": "deal", "deal_id": pid, "obligor": name, "step": step, "title": f"{pid}: the deal on screen", "lines": lines,
            "plain_words": plain, "rows": [], "basis": "Deal Desk structure set (stressproof.structures), the same rows as the page.",
            "actions": [{"label": "Ask Deal Desk's desk thread instead", "kind": "dealdesk"},
                        {"label": "Ask about the book instead", "kind": "book"}],
            "spoken": " ".join(lines[:3])}


def answer(question: str, context: dict[str, Any], *, force: bool = False) -> dict[str, Any]:
    """POST /api/v1/noor/here: the answer on the page. `force` (the "Answer here instead" button) skips the book cue."""
    r = route_here(question, context)
    if not r["here"] and not (force and (context or {}).get("deal_id")):
        return {"here": False, "reason": r["reason"]}
    topic = r.get("topic") or ("stress" if (context or {}).get("step") == "stress" else "deal")
    out = stress_answer(question, context) if topic == "stress" else deal_answer(question, context)
    return {"here": True, "reason": r.get("reason") or f"Answered on {context.get('deal_id')}, as asked.", "question": question, **out}
