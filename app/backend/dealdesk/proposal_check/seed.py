"""dd_proposal_quality demo rows for the R12 data build (`backend/dealdesk/data/build.py` calls `build_rows(rows)`): the proposal
check run on the demo pack (the half-baked and the corrected RM proposal for R14-RWQ), read against the build's own rows
(`source.use`), so a rebuild is byte-stable and needs no published data."""
from __future__ import annotations

import pathlib
from typing import Any

PACK = pathlib.Path(__file__).resolve().parents[3] / "data" / "dealdesk" / "demo_proposals"
FILES = ("R14-RWQ_RM_proposal_half_baked.docx", "R14-RWQ_RM_proposal_corrected.docx")


def build_rows(rows: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """`rows` = the build's relations; the demo deal's rows (demo_deal.all_rows, published after the build) are added in memory only."""
    from backend.dealdesk.house_style.bankform import source as S
    from backend.dealdesk.proposal_check import demo_deal, engine, parse
    out: list[dict[str, Any]] = []
    extra = demo_deal.all_rows()
    view = {k: list(v) + extra.get(k, []) for k, v in rows.items()} | {k: v for k, v in extra.items() if k not in rows}
    with S.use(view):
        for f in FILES:
            p = PACK / f
            if p.exists():
                out += engine.run("R14-RWQ", parse.read_docx(p.read_bytes(), p.name))["rows"]
    return out
