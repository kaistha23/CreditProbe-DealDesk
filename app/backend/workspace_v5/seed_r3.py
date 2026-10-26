"""The S3-2 seed (PLAN_R3, Anne's definitions): saved analyses, investigation threads and projects.

  analyses        EAD by sector (corporate, 2026Q2, from the Cockpit) · Retail Stage 2 build (retail, 2026-08, from the
                  Cockpit) · What-If: oil -40% (corporate, Delta method) · and the Construction ECL by sub-sector cut
                  the investigation and Mail already link to
  investigations  Construction ECL rise (corporate, 2026Q1 -> 2026Q2) · Retail risk build-up (retail)
  projects        Construction sector deep-dive Q2 2026 (corporate only, with documents) · Retail Stage 2 review
                  (retail and Early Warning)

Every figure is computed here from the books (backend.workspace_v5.compute), the Early Warning release or the What-If
engine, at seed time; nothing is typed in. Fixed ids and timestamps; INSERT OR IGNORE throughout.
"""
from __future__ import annotations

import io
import sqlite3
from datetime import datetime, timezone
from typing import Any

from backend.workspace_v5 import compute, responder, store
from backend.workspace_v5.book import mn, pct

P1, P0 = "2026Q2", "2026Q1"
R1, R0 = "2026-08", "2026-05"

A_SECTOR = "ead-by-sector-2026q2"
A_SUBSECTOR = "construction-ecl-by-subsector-2026q1-q2"
A_RETAIL_S2 = "retail-stage2-build-2026-08"
A_OIL = "whatif-oil-minus-40-corporate"
INV_CONSTRUCTION = "construction-ecl-rise-q2-2026"
INV_RETAIL = "retail-risk-build-up-2026"
PRJ_CONSTRUCTION = "construction-deep-dive-q2-2026"
PRJ_RETAIL = "retail-stage2-review"

KHALID, SARA, ABDULLAH, NOURA = "khalid.alotaibi", "sara.aldosari", "abdullah.alzahrani", "noura.alharbi"
REEM, OMAR, FAISAL, LAMA = "reem.alshehri", "omar.alghamdi", "faisal.alqahtani", "lama.almutairi"

SECTOR_SPEC = {"engine": "book", "book": "corporate", "by": "sector",
               "measures": ["ead", "share_pct", "ecl", "coverage_pct", "owners"], "sort": "ead"}
SUBSECTOR_SPEC = {"engine": "book", "book": "corporate", "by": "sub_sector", "measures": ["ead", "ecl", "coverage_pct",
                                                                                            "stage3_ecl"],
                  "filters": {"sector": ["Construction"]}, "sort": "ecl", "chart_measure": "ecl"}
RETAIL_S2_SPEC = {"engine": "book", "book": "retail", "by": "product",
                  "measures": ["ead", "stage2_ead", "stage2_share_pct", "stage2_count", "stage2_ecl"],
                  "sort": "stage2_ead", "chart_measure": "stage2_ead"}


def oil_spec() -> dict[str, Any]:
    from backend.whatif_v5.chat import library
    entry = next(e for e in library.STANDARD["corporate"] if e["key"] == "oil-shock")
    sc = library.scenario_for("corporate", entry, P1)
    return {"engine": "whatif", "book": "corporate", "method": "delta", "scenario": sc.to_dict()}


def _fig(result: dict[str, Any], key: str) -> float:
    return next(f["value"] for f in result["figures"] if f["key"] == key)


def _rows(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    t = result["table"]
    return {str(r[t["key"]]): r for r in t["rows"]}


def _table_artifact(title: str, result: dict[str, Any]) -> dict[str, Any]:
    t = result["table"]
    return {"kind": "table", "title": title, "columns": t["columns"], "rows": t["rows"], "totals": t.get("totals"),
            "source": result["source"], "period": result["period"]}


def _figures_artifact(title: str, figures: list[dict[str, Any]], period: str) -> dict[str, Any]:
    return {"kind": "figures", "title": title, "figures": figures, "period": period}


def _chart_artifact(result: dict[str, Any]) -> dict[str, Any]:
    c, t = result["chart"], result["table"]
    return {"kind": "chart", "title": c["title"], "chart": c,
            "points": [{"label": str(r[c["x"]]), "value": r[c["y"]]} for r in t["rows"]],
            "unit": next(col["unit"] for col in t["columns"] if col["key"] == c["y"])}


def _answer(result: dict[str, Any], narrative: str, headline: str | None = None) -> dict[str, Any]:
    out = {"narrative": narrative, "figures": result["figures"], "table": result["table"], "chart": result["chart"],
           "period": result["period"], "engine": result["engine"], "source": result["source"]}
    if headline:
        out["headline"] = headline  # R10 Q2: the answer to the question, key figure bold (else written from the result)
    return out


# --------------------------------------------------------------- analyses


def _analyses(con: sqlite3.Connection) -> dict[str, Any]:
    out: dict[str, Any] = {}
    sec = compute.compute(SECTOR_SPEC, P1)
    rows = sec["table"]["rows"]
    top = rows[:3]
    narrative = (f"Corporate book at {P1}: EAD {mn(_fig(sec, 'ead'))} across {len(rows)} sectors and "
                 f"{int(_fig(sec, 'owners')):,} borrowers. The largest sectors are "
                 + "; ".join(f"{r['sector']} {mn(r['ead'])} ({pct(r['share_pct'])})" for r in top)
                 + f". ECL {mn(_fig(sec, 'ecl'))}, coverage {pct(_fig(sec, 'coverage_pct'), 2)}.")
    store.create_analysis(con, ABDULLAH, title="EAD by sector", question=f"What is EAD by sector in {P1}?",
                          origin="cockpit", book="corporate", period=P1, answer=_answer(sec, narrative),
                          spec=SECTOR_SPEC, origin_link={"type": "cockpit-thread", "label": "Cockpit · Corporate",
                                                         "href": "/?domain=corporate"},
                          notes="Facility-level EAD and ECL summed by sector; SAR million.", source=sec["source"],
                          analysis_id=A_SECTOR, at="2026-07-02T10:00:00Z", demo=True)
    con.execute("UPDATE analyses SET project_id=? WHERE id=?", ("q2-2026-committee-pack", A_SECTOR))
    out["sector"] = sec

    sub1, sub0 = compute.compute(SUBSECTOR_SPEC, P1), compute.compute(SUBSECTOR_SPEC, P0)
    r0 = _rows(sub0)
    moves = sorted(((k, v["ecl"] - r0.get(k, {}).get("ecl", 0.0)) for k, v in _rows(sub1).items()),
                   key=lambda x: -x[1])
    narrative = (f"Construction ECL by sub-sector at {P1}: total {mn(_fig(sub1, 'ecl'))} against "
                 f"{mn(_fig(sub0, 'ecl'))} at {P0}. Largest rise: {moves[0][0]} (+{mn(moves[0][1])}), then "
                 f"{moves[1][0]} (+{mn(moves[1][1])}). Refresh to {P0} for the side-by-side.")
    lead_sub = max(_rows(sub1).items(), key=lambda kv: kv[1]["ecl"])
    sub_head = (f"**{lead_sub[0]}** drives the most Construction ECL at {P1}: **{mn(lead_sub[1]['ecl'])}** of "
                f"{mn(_fig(sub1, 'ecl'))}; the largest rise since {P0} is {moves[0][0]} (**+{mn(moves[0][1])}**).")
    store.create_analysis(con, SARA, title="Construction ECL by sub-sector",
                          question=f"Which Construction sub-sectors drive the ECL at {P1}?", origin="cockpit",
                          book="corporate", period=P1, answer=_answer(sub1, narrative, sub_head), spec=SUBSECTOR_SPEC,
                          origin_link={"type": "investigation", "label": "Investigation · Construction ECL rise",
                                       "href": f"/investigations/{INV_CONSTRUCTION}"},
                          notes="Largest ECL first; SAR million.", source=sub1["source"], analysis_id=A_SUBSECTOR,
                          at="2026-07-03T09:15:00Z", demo=True)
    con.execute("UPDATE analyses SET investigation_id=?, project_id=? WHERE id=?",
                (INV_CONSTRUCTION, PRJ_CONSTRUCTION, A_SUBSECTOR))
    out["sub1"], out["sub0"] = sub1, sub0

    s2, s2b = compute.compute(RETAIL_S2_SPEC, R1), compute.compute(RETAIL_S2_SPEC, R0)
    lead = s2["table"]["rows"][0]
    narrative = (f"Retail book at {R1}: Stage 2 EAD {mn(_fig(s2, 'stage2_ead'))}, "
                 f"{pct(_fig(s2, 'stage2_share_pct'), 2)} of EAD ({int(_fig(s2, 'stage2_count')):,} accounts), against "
                 f"{mn(_fig(s2b, 'stage2_ead'))} ({pct(_fig(s2b, 'stage2_share_pct'), 2)}) at {R0}. {lead['product']} "
                 f"holds the most Stage 2 EAD: {mn(lead['stage2_ead'])}.")
    s2_head = (f"Stage 2 has built up to **{mn(_fig(s2, 'stage2_ead'))}** (**{pct(_fig(s2, 'stage2_share_pct'), 2)}** of "
               f"EAD) at {R1}, from {mn(_fig(s2b, 'stage2_ead'))} ({pct(_fig(s2b, 'stage2_share_pct'), 2)}) at {R0}; "
               f"{lead['product']} holds the most ({mn(lead['stage2_ead'])}).")
    store.create_analysis(con, REEM, title="Retail Stage 2 build",
                          question=f"How much has Stage 2 built up in the retail book by product at {R1}?",
                          origin="cockpit", book="retail", period=R1, answer=_answer(s2, narrative, s2_head),
                          spec=RETAIL_S2_SPEC, origin_link={"type": "cockpit-thread", "label": "Cockpit · Retail",
                                                            "href": "/?domain=retail"},
                          notes="Account-level EAD by product; Stage 2 per IFRS 9 stage in the book; SAR million.",
                          source=s2["source"], analysis_id=A_RETAIL_S2, at="2026-09-04T07:30:00Z", demo=True)
    con.execute("UPDATE analyses SET project_id=? WHERE id=?", (PRJ_RETAIL, A_RETAIL_S2))
    out["s2"], out["s2b"] = s2, s2b

    spec = oil_spec()
    oil = compute.compute(spec, P1)
    f = {x["key"]: x["value"] for x in oil["figures"]}
    lead = oil["table"]["rows"][0]
    narrative = (f"Oil price -40% (Brent 40% below the base path in every year) on the corporate book at {P1}, Delta "
                 f"method: ECL {mn(f['reported_ecl'])} → {mn(f['scenario_ecl'])} (+{mn(f['change'])}, "
                 f"+{pct(f['change_pct'], 2)}); coverage {pct(f['coverage_before'], 2)} → "
                 f"{pct(f['coverage_after'], 2)}. {lead['segment']} moves most (+{mn(lead['change'])}).")
    store.create_analysis(con, KHALID, title="What-If: oil -40%", question="What if the oil price falls 40%?",
                          origin="whatif", book="corporate", period=P1, answer=_answer(oil, narrative), spec=spec,
                          origin_link={"type": "whatif-thread", "label": "What-If · Corporate · Oil price shock",
                                       "href": "/what-if?domain=corporate"},
                          notes="Scenario ECL is the probability-weighted ECL over base, upturn and downturn paths.",
                          source=oil["source"], analysis_id=A_OIL, at="2026-07-06T11:20:00Z", demo=True)
    out["oil"] = oil
    return out


# --------------------------------------------------------- investigations


def _investigations(con: sqlite3.Connection, a: dict[str, Any], facts: dict[str, Any]) -> None:
    s1, s0 = facts["s1"], facts["s0"]
    stages = {r["stage"]: r for r in facts["stages"]}
    sub1 = a["sub1"]
    top = compute.book_result({"engine": "book", "book": "corporate", "by": "sub_sector", "measures": ["ecl"],
                               "filters": {"sector": ["Construction"]}}, P1)
    stage_spec = {"engine": "book", "book": "corporate", "by": "stage", "measures": ["ead", "ecl"],
                  "filters": {"sector": ["Construction"]}}
    st1, st0 = compute.compute(stage_spec, P1), compute.compute(stage_spec, P0)
    d_ecl = s1["ecl"] - s0["ecl"]
    turns = [
        {"role": "user", "text": f"Why did Construction ECL rise in {P1}?", "at": "2026-07-03T08:31:00Z"},
        {"role": "assistant", "at": "2026-07-03T08:31:40Z",
         "text": (f"Construction ECL rose from {mn(s0['ecl'])} at {P0} to {mn(s1['ecl'])} at {P1} "
                  f"(+{mn(d_ecl)}, +{pct(100 * d_ecl / s0['ecl'])}) while EAD moved only from {mn(s0['ead'])} to "
                  f"{mn(s1['ead'])}. Coverage went from {pct(s0['coverage_pct'], 2)} to {pct(s1['coverage_pct'], 2)}. "
                  f"Stage 3 carries it: stage 3 ECL {mn(stages[3]['ecl_before'])} → {mn(stages[3]['ecl_after'])}."),
         "artifacts": [_figures_artifact("Construction, corporate book", [
             {"key": "ecl_2026Q1", "label": f"ECL {P0}", "value": s0["ecl"], "unit": "sar_mn"},
             {"key": "ecl_2026Q2", "label": f"ECL {P1}", "value": s1["ecl"], "unit": "sar_mn"},
             {"key": "ead_2026Q2", "label": f"EAD {P1}", "value": s1["ead"], "unit": "sar_mn"},
             {"key": "coverage_2026Q2", "label": f"Coverage {P1}", "value": s1["coverage_pct"], "unit": "pct"}], P1),
             _table_artifact(f"Construction by IFRS 9 stage, {P0}", st0),
             _table_artifact(f"Construction by IFRS 9 stage, {P1}", st1)]},
        {"role": "user", "text": "Which sub-sectors drive it?", "at": "2026-07-03T08:35:00Z"},
        {"role": "assistant", "at": "2026-07-03T08:35:30Z",
         "text": (f"By sub-sector at {P1} the ECL is largest in " + "; ".join(
             f"{r['sub_sector']} {mn(r['ecl'])}" for r in top["table"]["rows"][:3]) + ". The saved analysis "
             "'Construction ECL by sub-sector' keeps the cut and refreshes it to any quarter."),
         "artifacts": [_table_artifact(f"Construction ECL by sub-sector, {P1}", sub1), _chart_artifact(sub1),
                       {"kind": "object", "type": "analysis", "id": A_SUBSECTOR,
                        "label": "Analysis · Construction ECL by sub-sector", "href": f"/analyses/{A_SUBSECTOR}"}]},
        {"role": "user", "text": "Which borrower should the committee look at first?", "at": "2026-07-04T09:20:00Z"},
        {"role": "assistant", "at": "2026-07-04T09:20:40Z",
         "text": (f"CB01045 {facts['b1']['name']}: exposure {mn(facts['b1']['exposure'])} at {P1} over "
                  f"{facts['b1']['facilities']} facilities, rating {facts['b1']['rating_previous']} → "
                  f"{facts['b1']['rating']}, outlook {facts['b1']['rating_outlook']}, on the watchlist for "
                  f"{facts['b1']['quarters_on_watchlist']} quarters."),
         "artifacts": [{"kind": "object", "type": "borrower", "id": "CB01045",
                        "label": f"Borrower 360 · CB01045 {facts['b1']['name']}",
                        "href": "/borrower-360?domain=corporate&customer_id=CB01045&period=2026Q2"}]},
    ]
    con.execute("UPDATE investigations SET source=?, turns=?, continue_href=? WHERE id=?",
                (store._j({"type": "early-warning-list", "id": "corporate:Construction",
                           "label": "Early Warning · Corporate · Construction",
                           "href": "/early-warning?domain=corporate&segment=Construction"}),
                 store._j(store._clean_turns(turns, "2026-07-03T08:31:00Z")),
                 "/early-warning?domain=corporate&segment=Construction", INV_CONSTRUCTION))
    con.execute("UPDATE investigations SET project_id=? WHERE id=?", (PRJ_CONSTRUCTION, INV_CONSTRUCTION))

    s2, s2b = a["s2"], a["s2b"]
    b1, b0 = _rows(s2), _rows(s2b)
    ews_now = responder.ews_answer("retail", R1, None)
    ews_then = responder.ews_answer("retail", R0, None)
    from backend.whatif_v5.chat import library
    entry = next(e for e in library.STANDARD["retail"] if e["key"] == "unemployment")
    sc = library.scenario_for("retail", entry, R1)
    wi = compute.compute({"engine": "whatif", "book": "retail", "method": "delta", "scenario": sc.to_dict()}, R1)
    wf = {x["key"]: x["value"] for x in wi["figures"]}
    moves = sorted(((k, v["stage2_ead"] - b0.get(k, {}).get("stage2_ead", 0.0)) for k, v in b1.items()),
                   key=lambda x: -x[1])
    rturns = [
        {"role": "user", "text": f"Where is Stage 2 building in the retail book, {R0} to {R1}?",
         "at": "2026-09-04T07:10:00Z"},
        {"role": "assistant", "at": "2026-09-04T07:10:30Z",
         "text": (f"Stage 2 EAD rose from {mn(_fig(s2b, 'stage2_ead'))} ({pct(_fig(s2b, 'stage2_share_pct'), 2)} of "
                  f"EAD) at {R0} to {mn(_fig(s2, 'stage2_ead'))} ({pct(_fig(s2, 'stage2_share_pct'), 2)}) at {R1}. "
                  "Largest builds: " + "; ".join(f"{k} +{mn(v)}" for k, v in moves[:3]) + "."),
         "artifacts": [_table_artifact(f"Retail Stage 2 by product, {R0}", s2b),
                       _table_artifact(f"Retail Stage 2 by product, {R1}", s2), _chart_artifact(s2)]},
        {"role": "user", "text": "Does Early Warning see it too?", "at": "2026-09-04T07:14:00Z"},
        {"role": "assistant", "at": "2026-09-04T07:14:20Z", "text": f"{ews_now['text']}\n\nAt {R0}: {ews_then['text']}",
         "artifacts": [{"kind": "object", "type": "early-warning-list", "id": "retail", "label": "Early Warning · Retail",
                        "href": "/early-warning?domain=retail"}]},
        {"role": "user", "text": "What if unemployment rises 2pp?", "at": "2026-09-04T07:20:00Z"},
        {"role": "assistant", "at": "2026-09-04T07:20:40Z",
         "text": (f"What-If '{entry['name']}' on the retail book at {wi['period']} (Delta method): ECL "
                  f"{mn(wf['reported_ecl'])} → {mn(wf['scenario_ecl'])} (+{mn(wf['change'])}, "
                  f"+{pct(wf['change_pct'], 2)})."),
         "artifacts": [_table_artifact(f"Unemployment scenario by product, {wi['period']}", wi)]},
    ]
    store.import_investigation(
        con, REEM, source={"type": "early-warning-level", "id": "retail", "label": "Early Warning · Retail",
                           "href": "/early-warning?domain=retail"},
        title="Retail risk build-up", turns=rturns, summary=(
            f"Retail Stage 2 EAD {mn(_fig(s2b, 'stage2_ead'))} at {R0} → {mn(_fig(s2, 'stage2_ead'))} at {R1}; "
            "Early Warning bands and an unemployment scenario on the same book."),
        continue_href="/what-if?domain=retail", project_id=PRJ_RETAIL, period=R1, inv_id=INV_RETAIL,
        at="2026-09-04T07:22:00Z", demo=True, status="in_review")
    notes = [
        (OMAR, "2026-09-04T09:00:00Z",
         f"Checked against the Early Warning retail list for {R1}: the Stage 2 build and the high and critical bands "
         "point at the same products. Taking it to the Stage 2 review."),
        (REEM, "2026-09-05T10:30:00Z", "Sent to the Head of Risk with the unemployment scenario."),
    ]
    for i, (who, at, body) in enumerate(notes):
        con.execute("INSERT OR IGNORE INTO investigation_notes(id, investigation_id, author_id, body, kind, created_at, "
                    "demo) VALUES(?,?,?,?,?,?,1)", (100 + i, INV_RETAIL, who, body, "note", at))


# --------------------------------------------------------------- projects


def _docx(title: str, subtitle: str, sections: list[tuple[str, list[str], list[Any] | None]]) -> bytes:
    from backend.house_style import Meta
    from backend.house_style import docx as hd

    meta = Meta(title=title, book="corporate", period=P1, subject="Construction",
                generated_by="Khalid Al-Otaibi (Corporate Credit Manager)",
                generated_at=datetime(2026, 7, 8, 9, 0, tzinfo=timezone.utc))
    doc = hd.document(meta, kind="Sector review", subtitle=subtitle, cover="block")
    for heading, paras, tbl in sections:
        hd.heading(doc, heading, 1)
        for p in paras:
            hd.para(doc, p)
        if tbl:
            hd.table(doc, tbl[0], tbl[1], kinds=tbl[2])
    fixed = datetime(2026, 7, 8, 9, 0)
    doc.core_properties.created = fixed
    doc.core_properties.modified = fixed
    doc.core_properties.last_printed = fixed
    buf = io.BytesIO()
    doc.save(buf)
    # Same bytes on every seed: re-pack the zip with a fixed timestamp on every entry.
    import zipfile
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(buf.getvalue())) as zin, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            info = zipfile.ZipInfo(item.filename, date_time=(2026, 7, 8, 9, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            zout.writestr(info, zin.read(item.filename))
    return out.getvalue()


def _projects(con: sqlite3.Connection, a: dict[str, Any], facts: dict[str, Any]) -> None:
    from backend.workspace_v5 import docs

    s1, s0 = facts["s1"], facts["s0"]
    ins = con.execute
    ins("INSERT OR IGNORE INTO projects(id, name, description, owner_id, status, due_at, period, members, links, "
        "created_at, updated_at, demo) VALUES(?,?,?,?,?,?,?,?,?,?,?,1)",
        (PRJ_CONSTRUCTION, "Construction sector deep-dive Q2 2026",
         f"Why Construction ECL rose from {mn(s0['ecl'])} at {P0} to {mn(s1['ecl'])} at {P1}, which sub-sectors and "
         "borrowers carry it, and what the committee should do. Corporate book only.",
         KHALID, "active", "2026-07-20", P1, store._j([KHALID, SARA, ABDULLAH, NOURA]),
         store._j([{"label": "Early Warning · Corporate · Construction", "type": "early-warning",
                    "href": "/early-warning?domain=corporate&segment=Construction"}]),
         "2026-07-08T08:00:00Z", "2026-07-10T15:00:00Z"))
    store.set_project_scope(
        con, PRJ_CONSTRUCTION,
        f"Answer for the Construction sector of the corporate book at {P1} unless the question names another sector or "
        f"quarter, and compare with {P0}. Quote amounts in SAR million with the period. Cite the project documents "
        "where they apply. This project uses the corporate book only: no retail, Early Warning or What-If data.",
        ["corporate"], {"book": "corporate", "segment": "Construction", "period": P1})

    sub1, sub0 = a["sub1"], a["sub0"]
    r0 = _rows(sub0)
    sub_rows = [[r["sub_sector"], r0.get(r["sub_sector"], {}).get("ecl", 0.0), r["ecl"], r["ead"], r["coverage_pct"]]
                for r in sub1["table"]["rows"]]
    stages = facts["stages"]
    review = _docx(
        "Construction sector credit review, Q2 2026", "Corporate book · Construction · 2026Q2",
        [("Summary", [f"Construction is the largest sector of the corporate book: EAD {mn(s1['ead'])} at {P1} "
                      f"({s1['borrowers']:,} borrowers, {s1['facilities']:,} facilities). ECL rose from "
                      f"{mn(s0['ecl'])} at {P0} to {mn(s1['ecl'])} at {P1}; coverage "
                      f"{pct(s0['coverage_pct'], 2)} → {pct(s1['coverage_pct'], 2)}.",
                      "The rise is in credit quality, not volume: EAD grew by "
                      f"{pct(100 * (s1['ead'] / s0['ead'] - 1))} while ECL grew by "
                      f"{pct(100 * (s1['ecl'] / s0['ecl'] - 1))}."], None),
         ("ECL by sub-sector", ["Sub-sector ECL, SAR million, largest first."],
          [["Sub-sector", f"ECL {P0}", f"ECL {P1}", f"EAD {P1}", "Coverage %"], sub_rows,
           ["text", "sar_mn", "sar_mn", "sar_mn", "pct"]]),
         ("Stage mix", ["IFRS 9 stage, SAR million."],
          [["Stage", f"EAD {P0}", f"EAD {P1}", f"ECL {P0}", f"ECL {P1}"],
           [[f"Stage {r['stage']}", r["ead_before"], r["ead_after"], r["ecl_before"], r["ecl_after"]] for r in stages],
           ["text", "sar_mn", "sar_mn", "sar_mn", "sar_mn"]]),
         ("Committee questions", [
             "Contractor payment cycles on public projects lengthened through the first half: watch working-capital "
             "lines and guarantees in civil works and building contractors.",
             "Retention of the sector on monthly review; borrower-level reviews for the watchlist names before the "
             "limits review."], None)])
    memo = (
        "Construction sector outlook: notes for the deep-dive\n\n"
        "Contractor payment delays on public projects are the main pressure on working capital. Building and civil "
        "works contractors with a high share of government receivables carry the longest receivable days.\n\n"
        "Cement and steel input costs feed into fixed-price contracts. Contractors without escalation clauses absorb "
        "the cost and their margins thin first; specialised trade contractors are the most exposed.\n\n"
        "Giga-project pipelines keep order books full, so the risk is liquidity and execution rather than demand. "
        "Watch guarantee calls and performance bond claims as early signals.\n\n"
        "Recommended actions for the committee: keep Construction on monthly review, review the watchlist borrowers "
        "before the limits review, and tighten covenants on new working-capital lines to contractors with "
        "concentrated government receivables.")
    tor = (
        "Retail Stage 2 review: terms of reference\n\n"
        f"Purpose: explain the Stage 2 build in the retail book from {R0} to {R1} by product, and decide whether the "
        "SICR triggers, the Early Warning bands and the collections strategy need to change.\n\n"
        "Scope: the retail book (Credit Card, Personal Finance, Auto Finance, Mortgage and Buy Now Pay Later) and the "
        "retail Early Warning list. Corporate exposures are out of scope.\n\n"
        "Questions: which products carry the build; whether the build is migration from Stage 1 or new lending; "
        "whether the high and critical Early Warning bands lead Stage 2 by one or more months; what collections "
        "capacity the build needs.\n\n"
        "Deliverables: a Stage 2 build analysis by product refreshed monthly, a short paper to the Head of Risk, and "
        "an Add to report section for the risk committee report.")
    for fid, pid, who, name, data, at in [
        ("pd-construction-review", PRJ_CONSTRUCTION, KHALID, "Construction sector credit review Q2 2026.docx", review,
         "2026-07-08T09:05:00Z"),
        ("pd-construction-outlook", PRJ_CONSTRUCTION, SARA, "Construction sector outlook notes.txt",
         memo.encode("utf-8"), "2026-07-08T11:40:00Z"),
        ("pd-retail-tor", PRJ_RETAIL, REEM, "Retail Stage 2 review terms of reference.txt", tor.encode("utf-8"),
         "2026-09-03T08:00:00Z"),
    ]:
        if pid == PRJ_RETAIL and not con.execute("SELECT 1 FROM projects WHERE id=?", (pid,)).fetchone():
            _retail_project(con, a)
        ext = docs.kind_of(name)
        store.add_project_file(con, who, pid, name, data, docs.extract(name, data), docs.KINDS[ext], file_id=fid,
                               at=at, demo=True)

    # one thread per project, answered by the project responder at seed time (figures from the data)
    for tid, pid, who, title, questions, t0 in [
        ("pt-construction-why", PRJ_CONSTRUCTION, SARA, "Why did Construction ECL rise?",
         ["Why did the ECL rise this quarter, and what does the outlook say about contractors?",
          "Show EAD by sub-sector",
          "How does this compare with retail Stage 2?"], "2026-07-09T08:00:00Z"),
        ("pt-retail-build", PRJ_RETAIL, OMAR, "Stage 2 build by product",
         [f"What is the Stage 2 build by product in {R1}?", "What do the Early Warning bands show?",
          "What is Construction ECL in the corporate book?"], "2026-09-05T08:00:00Z"),
    ]:
        store.create_project_thread(con, who, pid, title, thread_id=tid, at=t0, demo=True)
        p = store.project(con, pid)
        files = store.project_file_texts(con, pid)
        base = int(datetime.fromisoformat(t0.replace("Z", "+00:00")).timestamp())
        for i, q in enumerate(questions):
            ask = datetime.fromtimestamp(base + 600 * i, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            ans = datetime.fromtimestamp(base + 600 * i + 20, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            mid = (1000 if pid == PRJ_CONSTRUCTION else 2000) + 2 * i
            store.add_project_message(con, tid, "user", who, q, at=ask, demo=True, msg_id=mid)
            reply = responder.respond(p, q, files)
            store.add_project_message(con, tid, "assistant", None, reply.pop("text"), payload=reply, at=ans, demo=True,
                                      msg_id=mid + 1)


def _retail_project(con: sqlite3.Connection, a: dict[str, Any]) -> None:
    s2, s2b = a["s2"], a["s2b"]
    con.execute("INSERT OR IGNORE INTO projects(id, name, description, owner_id, status, due_at, period, members, "
                "links, created_at, updated_at, demo) VALUES(?,?,?,?,?,?,?,?,?,?,?,1)",
                (PRJ_RETAIL, "Retail Stage 2 review",
                 f"Retail Stage 2 EAD grew from {mn(_fig(s2b, 'stage2_ead'))} at {R0} to {mn(_fig(s2, 'stage2_ead'))} "
                 f"at {R1}. Which products carry it, whether Early Warning saw it first, and what to change.",
                 REEM, "active", "2026-09-30", R1, store._j([REEM, OMAR, FAISAL, LAMA]),
                 store._j([{"label": "Early Warning · Retail", "type": "early-warning",
                            "href": "/early-warning?domain=retail"}]),
                 "2026-09-03T08:00:00Z", "2026-09-05T08:30:00Z"))
    store.set_project_scope(
        con, PRJ_RETAIL,
        f"Answer for the retail book at {R1} unless another month is named, and compare with the month before. "
        "Bring in the Early Warning bands and reasons where they explain the Stage 2 build. Quote amounts in SAR "
        "million. Corporate data is out of scope.",
        ["retail", "ews"], {"book": "retail", "period": R1})


def apply(con: sqlite3.Connection, facts: dict[str, Any]) -> None:
    old = con.row_factory
    con.row_factory = sqlite3.Row  # the store's readers take rows by name
    try:
        a = _analyses(con)
        _retail_project(con, a)
        _investigations(con, a, facts)
        _projects(con, a, facts)
    finally:
        con.row_factory = old


def refresh_seeded_answers() -> int:
    """Re-answer the seeded project-thread replies through the forked Cockpit conversation (PLAN_R4 A3), once.

    Seeded replies written by the r3 keyword responder have no `stages` in their payload; each is recomputed from
    the question before it, in its project's scope, and updated in place. Messages users wrote, and replies already
    answered by the conversation, are not touched. Returns the number refreshed.

    Deal Desk edition: nothing to do (its seed, backend.workspace_v5.seed_dealdesk, has no Cockpit project threads)."""
    from backend.v5common.edition import is_dealdesk
    if is_dealdesk():
        return 0
    import json as _json
    done = 0
    with store.db() as con:
        old = con.execute(
            "SELECT m.id, m.thread_id, t.project_id FROM project_messages m JOIN project_threads t ON t.id = m.thread_id "
            "WHERE m.demo = 1 AND m.role = 'assistant' AND m.payload NOT LIKE '%\"stages\"%' ORDER BY m.id").fetchall()
        work = []
        for r in old:
            q = con.execute("SELECT text FROM project_messages WHERE thread_id=? AND role='user' AND id < ? "
                            "ORDER BY id DESC LIMIT 1", (r["thread_id"], r["id"])).fetchone()
            if q:
                work.append((r["id"], r["project_id"], q["text"], store.project(con, r["project_id"]),
                             store.project_file_texts(con, r["project_id"])))
    import os
    was = os.environ.get("CONVO_ASSISTANT_MODEL")
    os.environ["CONVO_ASSISTANT_MODEL"] = "off"  # seeded content: the deterministic planner, no model cost at startup
    replies = []
    try:
        for mid, _pid, question, project, files in work:
            try:
                replies.append((mid, responder.respond(project, question, files)))
            except Exception:  # noqa: BLE001 - a reply that cannot be recomputed keeps its seeded text
                continue
    finally:
        if was is None:
            os.environ.pop("CONVO_ASSISTANT_MODEL", None)
        else:
            os.environ["CONVO_ASSISTANT_MODEL"] = was
    for mid, reply in replies:
        text = reply.pop("text")
        with store.db() as con:  # noqa: SIM117
            con.execute("UPDATE project_messages SET text=?, payload=? WHERE id=?",
                        (text, _json.dumps(reply, default=str), mid))
        done += 1
    return done
