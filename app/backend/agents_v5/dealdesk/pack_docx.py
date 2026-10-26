"""The committee pack as a Word file, through the house report pattern (backend.house_style.docx)."""
from __future__ import annotations

import re
from typing import Any

from backend.agents_v5.runtime.types import Run


def _pct(v: Any) -> str:
    return f"{v:.1%}" if isinstance(v, (int, float)) else "–"


def _m(v: Any, dp: int = 2) -> str:
    return f"{v:,.{dp}f}m" if isinstance(v, (int, float)) else "–"


def pack_docx(run: Run, generated_by: str = "") -> tuple[bytes, str]:
    from backend.house_style import Meta
    from backend.house_style import docx as hd
    p = run.output or {}
    pid = p.get("proposal_id") or run.scope
    meta = Meta(f"Committee pack · {p.get('name') or pid}", book="corporate", period=(run.finished_at or "")[:10],
                subject=f"{pid} · prepared by the Committee Preparation agent", generated_by=generated_by,
                reference=run.run_id)
    doc = hd.document(meta, kind="Committee pack", subtitle=f"{p.get('name') or pid} · {pid}", cover="block")
    hd.heading(doc, "1. Recommendation")
    hd.para(doc, p.get("headline") or p.get("decision") or "", bold=True)
    if p.get("why"):
        hd.bullets(doc, [f"{w['text']} ({', '.join(w['evidence'])})" for w in p["why"]])
    if run.narrative:
        hd.para(doc, run.narrative)
    cp = p.get("counter_proposal")
    if cp:
        hd.heading(doc, "2. Counter-proposal")
        hd.table(doc, ["Structure", "RAROC", "SVA", "Day-1 ECL", "Amount"],
                 [[cp.get("label"), _pct(cp.get("raroc")), _m(cp.get("sva")), _m(cp.get("ecl"), 3), _m(cp.get("amount"), 1)]])
        conds = [c for c in cp.get("conditions") or [] if c]
        if conds:
            hd.bullets(doc, conds)
    hd.heading(doc, "3. Forward risk, stress and pipeline")
    hd.bullets(doc, [f"Forward risk: {(p.get('forward_risk') or {}).get('answer') or 'not run'}",
                     f"Stress: {(p.get('stress') or {}).get('answer') or 'not run'}",
                     f"Pipeline fit: {(p.get('pipeline') or {}).get('answer') or 'not run'}",
                     f"Precedent: {(p.get('precedent') or {}).get('summary') or 'not run'}"])
    hd.heading(doc, "4. Findings by severity")
    rows = [[sev, f.get("title"), (f.get("detail") or "")[:240], ", ".join(f.get("evidence") or [])]
            for sev, fs in (p.get("findings_by_severity") or {}).items() for f in fs]
    if rows:
        hd.table(doc, ["Severity", "Finding", "Detail", "Evidence"], rows, size=7.5)
    else:
        hd.para(doc, "No findings.")
    if p.get("conditions"):
        hd.heading(doc, "5. Conditions")
        hd.table(doc, ["Condition", "Owner", "Due", "Status"],
                 [[c.get("what"), c.get("owner"), c.get("due"), c.get("status")] for c in p["conditions"]], size=7.5)
    if p.get("open_questions"):
        hd.heading(doc, "6. Open questions for the RM")
        hd.bullets(doc, [q["question"] for q in p["open_questions"]], numbered=True)
    if p.get("not_verified"):
        hd.heading(doc, "7. Items not verified")
        hd.bullets(doc, [f"{x['item']}: {x['reason']}" for x in p["not_verified"]])
    hd.heading(doc, "8. How this pack was prepared")
    steps = (run.plan.steps if run.plan else [])
    hd.table(doc, ["Step", "Tool", "Status", "Output", "Time"],
             [[s.id, s.tool, s.status, (s.summary or s.error)[:200], f"{s.duration_ms / 1000:.1f}s"] for s in steps], size=7)
    hd.note(doc, f"Planner: {run.plan.planner if run.plan else '–'}. Run {run.run_id}; total "
                 f"{run.duration_ms / 1000:.1f}s. Every figure comes from the engine step cited.")
    safe = re.sub(r"[^\w-]+", "-", f"Committee-pack-{pid}")[:80].strip("-")
    return hd.to_bytes(doc), f"{safe}.docx"
