"""The Lenses domain on the shared conversational layer (backend/convo; PLAN_R5 L1.2-L1.4, G4).

One thread per lens. The assistant plans and builds the dashboard (`build_lens`), edits it by conversation
(`edit_lens`: "add DSCR distribution", "remove the map", "show by region instead", "compare with Real Estate",
"switch to retail personal finance"), explains any tile (`explain_tile`: its query, figures and reading),
suggests next tiles (`suggest_tiles`) and turns a tile into a Cockpit thread or a What-If cohort
(`tile_to_thread`). Every figure it writes comes from the engine queries of the turn (the validator enforces it).
With no model key the deterministic planner below runs the same tools.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

import pandas as pd

from backend.convo.spec import Domain, Plan, PlanStep, Relation, Tool, ToolContext, ToolResult
from backend.lenses_v5 import fmt, planner
from backend.lenses_v5.catalogue import DIMS, METRICS
from backend.lenses_v5.engine import ENGINE, TABLE, LensError
from backend.lenses_v5.render import render
from backend.lenses_v5.tiles import Ctx, run_tile

#: Set by the API to its store (tests set their own).
STORE: Callable[[], Any] = lambda: None

EDIT = re.compile(r"^\s*(please\s+)?(add|remove|delete|drop|hide|include|put|switch|change|move|compare|show\b.*\bby\b|break\b.*\bby\b|split\b.*\bby\b)", re.I)
EXPLAIN = re.compile(r"\b(explain|what does|what is|why|how is|how was|walk me through|tell me about)\b", re.I)
SUGGEST = re.compile(r"\b(suggest|what else|what next|next tile|recommend|ideas|add next|should i add|could i add)\b", re.I)
UNDO = re.compile(r"^\s*(please\s+)?(undo|redo|revert|go back)\b", re.I)
HANDOFF = re.compile(r"\b(cockpit thread|cockpit|what-if cohort|what if cohort|whatif|what-if)\b", re.I)


def _lens(ctx: ToolContext) -> tuple[dict[str, Any], dict[str, Any]]:
    st = STORE()
    lid = ctx.scope.get("lens_id", "")
    lens = st.lens(lid) if st and lid else None
    if lens is None:
        raise LensError("This thread has no lens.")
    return lens, st.spec(lid)


def _kpi_data(r: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"metric": k["label"], "value": k["value"], "shown": k["display"], "change": k["change"], "change_shown": k["change_display"]}
            for k in r["kpis"] if k.get("value") is not None]


def _commit(ctx: ToolContext, lens: dict[str, Any], spec: dict[str, Any], change: str) -> int:
    st = STORE()
    return st.commit(lens["lens_id"], spec, change, ctx.user.get("username", "") or "assistant")


# ------------------------------------------------------------------ tools
def t_build(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    lens, spec = _lens(ctx)
    version = lens["head"]
    if args.get("tiles"):
        new = planner.normalise({**spec, "tiles": args["tiles"], **({"kpis": args["kpis"]} if args.get("kpis") else {})})
        if new["tiles"]:
            spec = new
            version = _commit(ctx, lens, spec, "Planned by the assistant")
    r = render(spec, cache_key=f"{lens['lens_id']}:{version}")
    tiles = [{"tile_id": t["id"], "title": t["title"], "type": t["type"]} for t in r["tiles"]]
    summary = (f"Built '{spec['title']}' on the {spec['book']} book as of {r['period']}: {len(r['kpis'])} KPIs, {r['charts']} charts, "
               f"{len(r['tiles'])} tiles, {r['untraced']} untraced figures.")
    return ToolResult(summary=summary, data={"title": spec["title"], "scope": r["scope_label"], "period": r["period"], "kpis": _kpi_data(r),
                                             "tiles": tiles, "commentary": r["commentary"]["markdown"],
                                             "interpretation": {"headline": r["interpretation"]["headline"],
                                                                "lines": [x["text"] for x in r["interpretation"]["lines"]]}},
                      rows=[{"tile": t["title"], "type": t["type"]} for t in r["tiles"]],
                      blocks=[{"type": "lens_update", "lens_id": lens["lens_id"], "version": version, "change": "built"}],
                      state={"built": True, "version": version}, title=spec["title"][:80])


def t_edit(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    lens, spec = _lens(ctx)
    cmd0 = str(args.get("command") or ctx.question)
    if UNDO.search(cmd0) and not args.get("op"):
        st = STORE()
        step = 1 if re.search(r"\bredo\b", cmd0, re.I) else -1
        before = lens["head"]
        version = st.move_head(lens["lens_id"], step)
        if version == before:
            raise LensError("There is nothing to " + ("redo." if step > 0 else "undo."))
        new = st.spec(lens["lens_id"])
        r = render(new, cache_key=f"{lens['lens_id']}:{version}")
        ch = [f"{'Redone' if step > 0 else 'Undone'}: the lens is back at version {version}"]
        return ToolResult(summary=ch[0], data={"changes": ch, "version": version, "book": new["book"], "scope": r["scope_label"],
                                               "tiles": len(r["tiles"]), "charts": r["charts"], "kpis": _kpi_data(r)},
                          blocks=[{"type": "lens_update", "lens_id": lens["lens_id"], "version": version, "change": ch[0]}],
                          state={"version": version})
    if args.get("op"):
        new, change = planner.apply_op(spec, args["op"])
        changes = [change]
    else:
        cmd = str(args.get("command") or ctx.question)
        new, changes = planner.apply_command(spec, cmd)
    version = _commit(ctx, lens, new, "; ".join(changes)[:300])
    r = render(new, cache_key=f"{lens['lens_id']}:{version}")
    return ToolResult(summary="; ".join(changes), data={"changes": changes, "version": version, "book": new["book"], "scope": r["scope_label"],
                                                        "tiles": len(r["tiles"]), "charts": r["charts"], "kpis": _kpi_data(r)},
                      blocks=[{"type": "lens_update", "lens_id": lens["lens_id"], "version": version, "change": "; ".join(changes)}],
                      state={"version": version})


def _pick_tile(spec: dict[str, Any], words: str) -> dict[str, Any] | None:
    w = words.lower()
    for t in spec["tiles"]:
        if t["id"] in words:
            return t
    hits = planner._find_tiles(spec, w)
    if hits:
        return hits[0]
    best, score = None, 0
    for t in spec["tiles"]:
        title = (t.get("title") or planner.describe(t)).lower()
        s = sum(1 for x in re.findall(r"[a-z0-9]+", w) if len(x) > 2 and x in title)
        if s > score:
            best, score = t, s
    return best


def t_explain(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    lens, spec = _lens(ctx)
    t = _pick_tile(spec, str(args.get("tile") or ctx.question))
    if t is None:
        t = spec["tiles"][0] if spec["tiles"] else None
    if t is None:
        return ToolResult(summary="The lens has no tiles.", data={})
    r = run_tile(t, Ctx(spec))
    rows = (r.get("table") or {}).get("rows") or []
    cols = (r.get("table") or {}).get("columns") or []
    return ToolResult(summary=f"Tile '{r['title']}' ({r['type']}) on {spec['book']} as of {r['trace']['period']}: {len(rows)} rows.",
                      data={"tile_id": t["id"], "title": r["title"], "type": r["type"], "columns": cols, "sql": r["trace"]["sql"],
                            "sources": r["trace"]["sources"], "badges": r.get("badges")},
                      rows=rows[:40])


def t_suggest(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    lens, spec = _lens(ctx)
    have = {(t["type"], t.get("column"), t.get("dim"), t.get("metric")) for t in spec["tiles"]}
    b = spec["book"]
    ideas = []
    cands = [("Add DSCR distribution", ("distribution", "dscr_x", None, None)), ("Add leverage distribution", ("distribution", "leverage_x", None, None)),
             ("Add LTV distribution", ("distribution", "collateral_ltv_pct", None, None)), ("Add stage migration", ("migration", None, None, None)),
             ("Add concentration", ("concentration", None, None, None)), ("Add ECL by relationship manager", ("breakdown", None, "rm_name", "ecl")),
             ("Add cost of risk by region", ("breakdown", None, "region", "cost_of_risk")), ("Add warned obligors by branch", ("breakdown", None, "branch_name", "warned")),
             ("Add roll rates", ("roll_rate", None, None, None)), ("Add vintage curves", ("vintage", None, None, None)),
             ("Add 30+ DPD share by sub-product", ("breakdown", None, "sub_product", "dpd30_share")),
             ("Add behaviour score distribution", ("distribution", "behaviour_score", None, None)),
             ("Add Deal Desk average RAROC by sector", ("breakdown", None, "sector", "dd_raroc"))]
    for text, sig in cands:
        tile = planner.tile_from_words(text[4:], b)
        if tile is None or sig in have:
            continue
        if planner.normalise({**spec, "tiles": [tile]})["tiles"]:
            ideas.append(text)
    if spec.get("compare") is None:
        other = "Real Estate" if b == "corporate" and not any("Real Estate" in f["values"] for f in spec["filters"]) else ("Construction" if b == "corporate" else "Credit Card")
        ideas.append(f"Compare with {other}")
    return ToolResult(summary=f"{len(ideas)} tiles could be added.", data={"ideas": ideas[:6]})


def _ews_cohort(spec: dict[str, Any]) -> str:
    body: dict[str, Any] = {"domain": spec["book"], "cohort": "all", "period": ""}
    dims: dict[str, str] = {}
    for f in spec["filters"]:
        if f["dim"] in ("sector", "product"):
            body["segment"] = f["values"][0]
        elif f["dim"] in ("sub_sector", "sub_product"):
            body["subsegment"] = f["values"][0]
        elif f["dim"] == "region":
            dims["region"] = f["values"][0]
    if dims:
        body["dims"] = dims
    base = (os.environ.get("EWS_API_ORIGIN") or "http://127.0.0.1:8501").rstrip("/")
    req = urllib.request.Request(base + "/api/v1/ews/export", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310 - the EWS service on loopback
            return str(json.loads(resp.read().decode()).get("object_id") or "")
    except (urllib.error.URLError, OSError, ValueError):
        return ""


def t_handoff(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    lens, spec = _lens(ctx)
    target = "whatif" if re.search(r"what.?if", str(args.get("target") or ctx.question), re.I) else "cockpit"
    t = _pick_tile(spec, str(args.get("tile") or ctx.question)) or (spec["tiles"][0] if spec["tiles"] else None)
    title = (t.get("title") or planner.describe(t)) if t else spec["title"]
    if target == "cockpit":
        q = f"{title} for {spec.get('scope_label') or spec['book']} as of {spec.get('period') or ENGINE.as_of(spec['book'])}"
        href = "/?q=" + urllib.parse.quote(q)
        return ToolResult(summary=f"A Cockpit thread for '{title}' opens with the question prefilled.", data={"target": "cockpit", "question": q},
                          blocks=[{"type": "lens_link", "label": "Open in the Cockpit", "href": href, "target": "cockpit"}])
    cid = _ews_cohort(spec)
    href = f"/what-if?cohort={cid}" if cid else f"/what-if?domain={spec['book']}"
    return ToolResult(summary=("The lens scope is saved as an Early Warning cohort; What-If opens a thread on it." if cid else
                               "What-If opens on the whole book; the cohort could not be saved just now."),
                      data={"target": "whatif", "cohort_id": cid},
                      blocks=[{"type": "lens_link", "label": "Open as a What-If cohort", "href": href, "target": "whatif"}])


# ------------------------------------------------------------------ relations
def _tiles_rel(scope: dict[str, Any]) -> pd.DataFrame:
    st = STORE()
    lid = scope.get("lens_id", "")
    if not st or not st.lens(lid):
        return pd.DataFrame(columns=["tile_id", "title", "label", "value"])
    spec = st.spec(lid)
    r = render(spec, cache_key=f"{lid}:{st.lens(lid)['head']}")
    rows = [{"tile_id": "kpi", "title": "KPI row", "label": k["label"], "value": k["value"]} for k in r["kpis"]]
    for t in r["tiles"]:
        tab = t.get("table") or {}
        cols = tab.get("columns") or []
        if len(cols) < 2:
            continue
        lab = cols[0]["key"]
        for row in (tab.get("rows") or [])[:60]:
            for c in cols[1:]:
                v = row.get(c["key"])
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    rows.append({"tile_id": t["id"], "title": t["title"], "label": f"{row.get(lab)} · {c['label']}", "value": float(v)})
    return pd.DataFrame(rows, columns=["tile_id", "title", "label", "value"])


def _scope_rel(scope: dict[str, Any]) -> pd.DataFrame:
    st = STORE()
    lid = scope.get("lens_id", "")
    if not st or not st.lens(lid):
        # R10 C4: no lens open (the assistant asked from the Lenses home) -> an empty relation with its columns,
        # never a column-less frame (duckdb refuses those and the whole turn failed).
        return pd.DataFrame(columns=["exposure_id", "owner_id", "segment", "ead_sar_mn", "ecl_sar_mn", "stage"])
    spec = st.spec(lid)
    b = spec["book"]
    p = spec.get("period") or ENGINE.as_of(b)
    cols = ("exposure_id, owner_id, owner_name, sector, sub_sector, region, branch_name, rm_name, rating_current, stage, ead_sar_mn, ecl_sar_mn, "
            "pd_pit_12m, lgd_pct, dpd_days, ews_band, dscr_x, leverage_x") if b == "corporate" else \
        "exposure_id, owner_id, product, sub_product, region, branch_name, stage, ead_sar_mn, ecl_sar_mn, pd_pit_12m, lgd_pct, dpd_days, ews_band, behaviour_score"
    from backend.lenses_v5.engine import _q
    return pd.DataFrame(ENGINE.q(f"SELECT {cols} FROM {TABLE[b]} WHERE period = {_q(p)} AND {ENGINE.where(b, spec['filters'])}"))


def relations(scope: dict[str, Any]) -> list[Relation]:
    return [Relation("lens_figures", "Every figure on the lens now: the KPI row and each tile's table, one row per value", _tiles_rel,
                     grain="tile x label", columns={"tile_id": "tile id ('kpi' for the KPI row)", "label": "row and column of the tile", "value": "the figure"}),
            Relation("scope_exposures", "The exposures in the lens scope at its as-of period (facility or account level)", _scope_rel,
                     grain="exposure", columns={"ead_sar_mn": "EAD in SAR m", "ecl_sar_mn": "ECL in SAR m", "ews_band": "Early Warning band"})]


def _scope_key(scope: dict[str, Any]) -> str:
    st = STORE()
    lid = scope.get("lens_id", "")
    lens = st.lens(lid) if st and lid else None
    return f"{lid}:{lens['head'] if lens else 0}"


# ------------------------------------------------------------------ the deterministic planner (no model key)
def plan(question: str, ctx: ToolContext) -> Plan:
    q = question.strip()
    if not ctx.state.get("built"):
        return Plan([PlanStep("build_lens", {"request": q})], _write_build)
    if HANDOFF.search(q) and re.search(r"\b(turn|open|send|make|as a|into)\b", q, re.I):
        return Plan([PlanStep("tile_to_thread", {"tile": q, "target": q})], _write_handoff)
    if SUGGEST.search(q):
        return Plan([PlanStep("suggest_tiles", {})], _write_suggest)
    if EDIT.search(q) or UNDO.search(q):
        return Plan([PlanStep("edit_lens", {"command": q})], _write_edit)
    if EXPLAIN.search(q):
        return Plan([PlanStep("explain_tile", {"tile": q})], _write_explain)
    return Plan([PlanStep("explain_tile", {"tile": q})], _write_explain)


def _out(results: list[dict[str, Any]]) -> dict[str, Any]:
    r = results[0]
    if r["error"]:
        return {"error": r["out"].get("error", "")}
    return r["out"].get("data") or {}


def _err(d: dict[str, Any]) -> dict[str, Any] | None:
    if "error" in d:
        msg = re.sub(r"^\w+Error: ", "", d["error"])
        return {"markdown": f"I could not do that: {msg}", "suggestions": ["What should I add next?", "Explain the first tile"]}
    return None


def _write_build(results: list[dict[str, Any]]) -> dict[str, Any]:
    """R13 L (J8): the build answer is short — what was built, where the scope stands, the movements that matter."""
    d = _out(results)
    if e := _err(d):
        return e
    it = d.get("interpretation") or {}
    head = f"**{d['title']}** · {d['scope']} · as of {d['period']}"
    # R14 G (carried J8 gap): the interpretation is shown once, at the top of the dashboard; the assistant does not
    # repeat it beside the dashboard. It says what it built and what it can do next.
    body = []
    if it.get("headline") or it.get("lines"):
        n = len(it.get("lines") or []) + (1 if it.get("headline") else 0)
        body.append(f"The reading of this lens ({n} line{'s' if n != 1 else ''}) is at the top of the dashboard.")
    elif d.get("commentary"):
        body.append(d["commentary"])
    foot = f"{len(d['kpis'])} KPIs and {len(d['tiles'])} tiles on the lens; the (i) on each shows its query. Ask me to add, compare or explain a tile."
    corp = "Average DSCR" in json.dumps(d["kpis"])
    return {"markdown": "\n\n".join([head, "\n".join(body), foot]).replace("\n\n\n", "\n\n"),
            "suggestions": ["Add DSCR distribution" if corp else "Add behaviour score distribution", "Show by region instead",
                            "Compare with Real Estate" if corp else "Compare with Personal Finance", "What should I add next?"]}


def _write_edit(results: list[dict[str, Any]]) -> dict[str, Any]:
    d = _out(results)
    if e := _err(d):
        return e
    ch = d["changes"]
    lines = ["Done. " + "; ".join(ch) + "."]
    lines.append(f"The lens now has {d['tiles']} tiles on {d['scope']} (version {d['version']}).")
    return {"markdown": "\n\n".join(lines), "suggestions": ["Undo that", "What should I add next?", "Explain the first tile"]}


def _write_explain(results: list[dict[str, Any]]) -> dict[str, Any]:
    d = _out(results)
    if e := _err(d):
        return e
    if not d:
        return {"markdown": "The lens has no tiles yet."}
    rows = results[0]["artifact"]["rows"] if results[0].get("artifact") else []
    cols = d.get("columns") or []
    lines = [f"**{d['title']}** is a {d['type'].replace('_', ' ')} tile computed from {', '.join(d['sources'][:2])}."]
    if rows and len(cols) >= 2:
        lab, val = cols[0], cols[1]
        num = [r for r in rows if isinstance(r.get(val["key"]), (int, float))]
        if num and d["type"] not in ("trend", "compare", "mix_trend", "vintage"):
            top = sorted(num, key=lambda r: -(r[val["key"]] or 0))[:3]
            lines.append("The largest values: " + "; ".join(f"{r[lab['key']]} at {fmt.fmt_value(r[val['key']], val['unit'])}" for r in top) + ".")
        elif num:
            a, b = num[0], num[-1]
            lines.append(f"{val['label']} moved from {fmt.fmt_value(a[val['key']], val['unit'])} in {a[lab['key']]} "
                         f"to {fmt.fmt_value(b[val['key']], val['unit'])} in {b[lab['key']]}.")
    for bd in d.get("badges") or []:
        lines.append(f"{bd['label']}: {bd['display']}.")
    lines.append("The query behind it is under the (i) on the tile.")
    return {"markdown": "\n\n".join(lines), "tables": [{"artifact_id": results[0]["out"]["artifact_id"], "title": d["title"]}] if rows else [],
            "suggestions": ["Turn this into a Cockpit thread", "Open as a What-If cohort", "What should I add next?"]}


def _write_suggest(results: list[dict[str, Any]]) -> dict[str, Any]:
    d = _out(results)
    if e := _err(d):
        return e
    ideas = d.get("ideas") or []
    return {"markdown": "Tiles that would add to this lens:\n\n" + "\n".join(f"- {i}" for i in ideas), "suggestions": ideas[:4]}


def _write_handoff(results: list[dict[str, Any]]) -> dict[str, Any]:
    d = _out(results)
    if e := _err(d):
        return e
    if d.get("target") == "cockpit":
        return {"markdown": f"The Cockpit opens with this question: *{d['question']}*. Use the button below."}
    return {"markdown": "The lens scope is ready as a What-If cohort. Use the button below to open the What-If thread." if d.get("cohort_id")
            else "What-If opens on the book; pick the cohort there."}


KNOWLEDGE = {
    "coverage": "ECL coverage = ECL / EAD x 100, in percent.",
    "cost of risk": "Cost of risk (12m) = over the last 12 months (4 quarters), (ECL build + new write-offs) / average EAD, in bps; flows are taken "
                    "exposure by exposure and a written-off balance is counted once.",
    "npl": "NPL ratio = Stage 3 EAD / EAD x 100. Stage 3 is credit-impaired (default).",
    "warned": "Warned = Early Warning band moderate, high or critical (rule set of the EWS release). High or critical are the severe bands.",
    "hhi": "HHI = sum of squared obligor shares of EAD (shares in percent), 0 to 10,000; above 1,500 is concentrated.",
    "lens": "A lens is a live dashboard: a KPI row, 8-14 charts, a top-names table and a commentary, each figure a query on the books with its trace.",
    "custom ratio": "A custom ratio is numerator / denominator from the catalogue (amounts or counts), the numerator optionally filtered, validated by running it on the book.",
}

DOMAIN = Domain(
    key="lenses",
    title="Lenses",
    charter=("You are the Lenses assistant of CreditProbe, a Saudi bank's credit risk platform. You build and edit live dashboards (lenses) "
             "on the corporate book (quarterly) and the retail book (monthly). Use build_lens on the first turn, edit_lens for any change to the "
             "lens (pass the user's words as `command`), explain_tile to explain a tile, suggest_tiles for ideas, and tile_to_thread to open a tile "
             "in the Cockpit or as a What-If cohort. Every figure you write must come from a tool result of this turn. Amounts are SAR m or bn, "
             "percentages with 1-2 decimals, bps as integers. Keep answers short: what you built or changed, and the two or three figures that matter."),
    relations=relations,
    tools=[
        Tool("build_lens", "Plan and build the lens for the thread's request (the KPI row, 8-14 charts, top names, commentary). Optional `tiles` and `kpis` "
             "replace the planner's choice; tiles use types trend, breakdown, mix_trend, top_names, distribution, migration, roll_rate, vintage, "
             "concentration, reasons, compare.",
             {"type": "object", "properties": {"request": {"type": "string"}, "tiles": {"type": "array", "items": {"type": "object"}},
                                               "kpis": {"type": "array", "items": {"type": "string"}}}}, t_build, message="Planning and building the lens"),
        Tool("edit_lens", "Change the lens: add, remove, show by, compare with, switch to (a command in the user's words), or a structured `op`.",
             {"type": "object", "properties": {"command": {"type": "string"}, "op": {"type": "object"}}}, t_edit, message="Editing the lens"),
        Tool("explain_tile", "One tile's figures, query and sources (pick it by id or words).", {"type": "object", "properties": {"tile": {"type": "string"}}},
             t_explain, message="Reading the tile"),
        Tool("suggest_tiles", "Tiles that would add to this lens.", {"type": "object", "properties": {}}, t_suggest, message="Looking for next tiles"),
        Tool("tile_to_thread", "Open a tile in the Cockpit (a thread with the question prefilled) or as a What-If cohort of the lens scope.",
             {"type": "object", "properties": {"tile": {"type": "string"}, "target": {"type": "string", "enum": ["cockpit", "whatif"]}}}, t_handoff,
             message="Preparing the hand-off"),
    ],
    knowledge=KNOWLEDGE,
    planner=plan,
    scope_label=lambda s: f"lens {s.get('lens_id', '')}",
    scope_key=_scope_key,
    suggestions=lambda s, st: [{"label": "What should I add next?", "send": "What should I add next?"},
                               {"label": "Show by region instead", "send": "Show by region instead"},
                               {"label": "Explain the first tile", "send": "Explain the first tile"}],
    state_brief=lambda st: f"The lens is built (version {st.get('version', 1)})." if st.get("built") else "The lens is not built yet: call build_lens first.",
    max_steps=6,
)

__all__ = ["DOMAIN", "STORE", "LensError", "DIMS", "METRICS"]
