"""Where a workspace's first version comes from, in the one section/blocks model.

    proposal(pid, structure=None)   Credit's credit proposal: the bank-form writer (bankform/paper.write) on the selected structure
    request(rid)                    the RM's business request saved by R16 b (rm_request/store)
    given(paper)                    a paper another round wrote (Round A's agent draft), checked for the model's shape
"""
from __future__ import annotations

from typing import Any

from backend.dealdesk.paperws import hooks


class SourceError(ValueError):
    pass


BLOCK_TYPES = {"p", "h", "bullets", "numbered", "table", "kv", "sign", "box"}


def _parts_proposal(paper: dict[str, Any]) -> list[dict[str, Any]]:
    from backend.dealdesk.house_style.bankform import render_bank
    return [{"key": x["key"], "title": x["title"], "subtitle": x["subtitle"], "sections": [s["key"] for s in x["sections"]]}
            for x in render_bank.parts(paper)]


def proposal(pid: str, structure: Any = None) -> dict[str, Any]:
    from backend.dealdesk.house_style.bankform import ctx, paper as bf
    try:
        p = bf.write(pid, structure=structure)
    except ctx.NotFound as e:
        raise SourceError(str(e).strip("'\"")) from None
    p["doc_kind"] = "proposal"
    p["parts"] = _parts_proposal(p)
    st = ((p.get("feed") or {}).get("structure") or {})
    p["structure_terms"] = st.get("terms") or (structure if isinstance(structure, dict) else {})
    p["structure_key"] = st.get("key") or (structure if isinstance(structure, str) else "")
    return p


def rewrite_proposal(pid: str, terms: dict[str, Any]) -> dict[str, Any]:
    """The structure step's re-render: the same writer on new terms (the engine prices them; no figure is computed here)."""
    return proposal(pid, structure=dict(terms))


def request(rid: str) -> dict[str, Any]:
    from backend.dealdesk.rm_request import store as ST
    p = ST.get(rid)
    if p is None:
        raise SourceError(f"no business request {rid}")
    p = dict(p)
    p["doc_kind"] = "request"
    return p


def given(paper: dict[str, Any], kind: str) -> dict[str, Any]:
    secs = paper.get("sections")
    if not isinstance(secs, list) or not secs:
        raise SourceError("paper.sections: a list of sections is required")
    out = []
    for i, s in enumerate(secs):
        if not isinstance(s, dict) or not s.get("key") or not isinstance(s.get("blocks"), list):
            raise SourceError(f"paper.sections[{i}]: key and blocks are required")
        for b in s["blocks"]:
            if not isinstance(b, dict) or b.get("t") not in BLOCK_TYPES:
                raise SourceError(f"paper.sections[{i}] ({s['key']}): unknown block {str(b)[:60]}")
        out.append({"n": s.get("n"), "heading": s.get("heading") or s["key"], "voice": s.get("voice") or ("business" if kind == "request" else "credit"),
                    "part": s.get("part") or "anatomy", "gaps": list(s.get("gaps") or []), **s})
    p = {**paper, "sections": out, "doc_kind": kind}
    p.setdefault("customer", "")
    p.setdefault("proposal_id", str(paper.get("proposal_id") or ""))
    p.setdefault("parts", [{"key": "all", "title": "BUSINESS REQUEST" if kind == "request" else "CREDIT PROPOSAL", "subtitle": "",
                            "sections": [s["key"] for s in out if s["key"] != "header"]}])
    return p


def named(source: str, ref: str) -> dict[str, Any]:
    fn = hooks.PAPER_SOURCES.get(source)
    if fn is None:
        raise SourceError(f"no paper source {source!r}")
    return fn(ref)
