"""Assemble the bank-form credit proposal from the registry, and check it.

    paper = write("DD-31")                         # deterministic (N6); polish=True asks the model to tighten wording when a key exists
    paper["sections"]                              # [{key, n, heading, voice, part, blocks, gaps, needs, contract_met, method}]
    paper["coverage"]  -> coverage.check(paper)    # [] when all 20 anatomy sections and the CreditProbe sections are present
    paper["voice"]     -> voice.check_paper(paper) # [] when every prose sentence keeps the voice
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.dealdesk.house_style.bankform import coverage, ctx, polish, registry, voice


def section(D: ctx.Deal, spec: registry.Section) -> dict[str, Any]:
    try:
        blocks, gaps = spec.writer(D)
        method = "deterministic"
    except Exception as e:  # noqa: BLE001 - one section's data problem never takes the paper down
        blocks, gaps, method = ([{"t": "p", "text": f"{spec.heading} not available: the data could not be read as at {ctx.d(D.as_of) or D.as_of} "
                                                    f"({type(e).__name__}).", "exempt": False}], [f"writer error {type(e).__name__}"], "error")
    unmet = [r for r in spec.needs if not D.rows(r)]
    return {"key": spec.key, "n": spec.n, "heading": spec.heading, "voice": "credit" if spec.voice == "creditprobe" else spec.voice,
            "part": spec.part, "blocks": blocks, "gaps": list(dict.fromkeys(gaps + unmet)), "needs": list(spec.needs), "uses": list(spec.uses),
            "contract_met": not unmet, "method": method,
            "sources": sorted({D.src(r) for r in (*spec.needs, *spec.uses) if D.rows(r)})}


def write(pid: str, order: str = "proposal", polish_text: bool = False, D: ctx.Deal | None = None, structure: Any = None,
          feed_on: bool = True) -> dict[str, Any]:
    """structure: None = the deal's selected structure (session f), "ask", "recommended", "counter:<id>" or a terms dict (R14 K26)."""
    D = D or ctx.load(pid)
    from backend.dealdesk.house_style.bankform import source as _S
    if getattr(_S._LOCAL, "override", None) is not None:  # noqa: SLF001 - a preview / test over given rows: the engines cannot see them
        feed_on = False
    if feed_on and getattr(D, "feed", None) is None:
        from backend.dealdesk.house_style.bankform import feed as FD
        try:
            D.feed = FD.feed(pid, structure)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001 - no engine: the R12 writers
            D.feed = None  # type: ignore[attr-defined]
    from backend.dealdesk.deposit_requirement.docs import apply_to_paper  # Round D: the Deposit requirement term's rows
    apply_to_paper(D)
    tpl = template_of(pid)
    keys, required = registry.for_template(tpl, registry.PROPOSAL_ORDER if order == "proposal" else registry.COMMITTEE_ORDER)
    secs = [section(D, registry.BY_KEY[k]) for k in keys]
    if polish_text:
        secs = [polish.section(s) for s in secs]
    te, to, tp = __import__("backend.dealdesk.house_style.bankform.writers", fromlist=["totals"]).totals(D)
    paper = {"proposal_id": pid, "kind": "bank_form_proposal", "order": order, "title": f"Credit proposal · {D.name}",
             "customer": D.name, "group": D.group, "currency": D.ccy, "as_of": D.as_of, "as_of_label": ctx.d(D.get("as_of")) or str(D.as_of),
             "request_kind": D.get("request_kind", "case_type", default=""), "rating": D.get("internal_rating", default=""), "sector": D.get("sector", default=""),
             "totals": {"existing": te, "outstanding": to, "proposed": tp},
             "created": datetime.now(timezone.utc).isoformat(timespec="seconds"), "sections": secs,
             "relations": {k: {"status": v, "rows": len(D.rows(k))} for k, v in sorted(D.status.items())},
             "product": (tpl or {}).get("product", "corporate"), "lane": (tpl or {}).get("lane", "full"), "required": required,
             "feed": D.feed.summary() if getattr(D, "feed", None) is not None else None,  # type: ignore[attr-defined]
             "header_line": header_line(D)}
    paper["coverage"] = coverage.check(paper)
    paper["voice"] = voice.check_paper(paper)
    paper["density"] = voice.score(paper)
    paper["gaps"] = [{"section": s["key"], "heading": s["heading"], "missing": s["gaps"]} for s in secs if s["gaps"]]
    paper["methods"] = sorted({s["method"] for s in secs})
    return paper


def template_of(pid: str) -> dict[str, Any] | None:
    """The deal's product template (Session E's products/templates.py), None before it exists."""
    try:
        from backend.dealdesk.products import templates
        return templates.for_deal(pid)
    except Exception:  # noqa: BLE001
        return None


def summary(paper: dict[str, Any]) -> dict[str, Any]:
    """The paper without its blocks (list views, the dialog header)."""
    return {k: v for k, v in paper.items() if k != "sections"} | {
        "sections": [{k: s[k] for k in ("key", "n", "heading", "voice", "part", "gaps", "contract_met", "method")} for s in paper["sections"]]}


def header_line(D: ctx.Deal) -> list[tuple[str, str]]:
    """The compact header block repeated on every page (SIB_GAP_AUDIT A1)."""
    from backend.dealdesk.house_style.bankform.source import first
    kind = str(first(D.p, "request_kind", "case_type", default="")).replace("_", " ")
    return [("Customer", D.name), ("CIF", str(first(D.p, "cif", "obligor_id", default="–"))), ("Group", str(first(D.p, "group_no", "group_id", default="–"))),
            ("Date", ctx.d(D.get("as_of")) or str(D.as_of)), ("Request", kind.capitalize() or "–"),
            ("Rating", f"{first(D.p, 'internal_rating', default='–')} / {first(D.p, 'proposed_rating', 'internal_rating', default='–')}"),
            ("Ref", f"{D.pid}-BFP")]
