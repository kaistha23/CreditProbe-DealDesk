"""R13 IE exports in house style (docs/v5/HOUSE_STYLE.md): the inspection pack as Word and Excel, and each of the
other three engines as Excel. Every figure row carries its source (relation, key, period) so the file stands alone."""
from __future__ import annotations

import json
from typing import Any

from backend.house_style import Meta
from backend.house_style import docx as hd
from backend.house_style import xlsx as hx


def _src(fig: dict[str, Any] | None) -> str:
    if not fig:
        return ""
    s = fig.get("source") if "source" in fig else fig
    if not s:
        return ""
    key = ", ".join(f"{k}={v}" for k, v in (s.get("key") or s.get("filter") or {}).items())
    return f"{s.get('relation', '')} [{key}] {s.get('period', '')}".strip()


def _v(fig: dict[str, Any] | None) -> Any:
    return None if not fig else fig.get("value")


def _figure_rows(pack: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for it in pack["items"]:
        ev = it.get("evidence") or {}
        for f in ev.get("facilities") or []:
            for label, k, unit in (("Limit", "limit", "SAR m"), ("EAD", "ead", "SAR m"), ("Stage", "stage", ""),
                                   ("Days past due", "dpd", "days"), ("ECL", "ecl", "SAR m")):
                rows.append({"item": it["id"], "object": f["facility_id"], "figure": label, "value": _v(f[k]), "unit": unit,
                             "source": _src(f[k])})
        if ev.get("rating"):
            rows.append({"item": it["id"], "object": it["id"], "figure": "Rating", "value": _v(ev["rating"]), "unit": "",
                         "source": _src(ev["rating"])})
        if it["kind"] == "deal":
            rows.append({"item": it["id"], "object": it["id"], "figure": "Proposed limits", "value": _v(ev.get("proposed_limits")),
                         "unit": "SAR m", "source": _src(ev.get("proposed_limits"))})
    return rows


def _approval_rows(pack: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for it in pack["items"]:
        ev = it.get("evidence") or {}
        for d in ev.get("decisions") or []:
            for s in d["steps"]:
                rows.append({"item": it["id"], "decision": d["decision_id"], "quarter": d["quarter"], "case": d["case_type"],
                             "outcome": d["decision"], "level": s["level"], "received": s["received_on"], "decided": s["decided_on"],
                             "days": s["days"], "action": s["output"], "source": _src(s["source"])})
        deals = [x for x in (ev.get("deals") or []) if x] + ([ev] if it["kind"] == "deal" else [])
        for dl in deals:
            for w in dl.get("workflow") or []:
                rows.append({"item": it["id"], "decision": dl["proposal_id"], "quarter": "", "case": "", "outcome": dl.get("status"),
                             "level": w["role"], "received": "", "decided": str(w["at"])[:10], "days": None, "action": w["to_state"],
                             "source": _src(w["source"])})
    return rows


def _condition_rows(pack: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for it in pack["items"]:
        ev = it.get("evidence") or {}
        for d in ev.get("decisions") or []:
            c = d["conditions"]
            rows.append({"item": it["id"], "ref": d["decision_id"], "what": f"{c['set']} set, {c['met']} met, {c['breached']} breached",
                         "status": "breached" if c["breached"] else ("met" if c["set"] else "none set"), "source": _src(c["source"])})
            for x in d["exceptions"]:
                rows.append({"item": it["id"], "ref": x["exception_id"], "what": f"Policy exception {x['type']} (clause {x['clause']}); "
                             f"mitigant: {x['mitigant']}", "status": f"approved by {x['approved_by']}", "source": _src(x["measured"])})
        deals = [x for x in (ev.get("deals") or []) if x] + ([ev] if it["kind"] == "deal" else [])
        for dl in deals:
            for c in dl.get("conditions") or []:
                rows.append({"item": it["id"], "ref": c["condition_id"], "what": c["text"], "status": c["status"], "source": _src(c["source"])})
    return rows


def _meta(title: str, subject: str, user: str, ref: str = "") -> Meta:
    return Meta(title=title, book="corporate", period="2026Q2", subject=subject, generated_by=user, reference=ref,
                classification="CONFIDENTIAL")


def inspection_xlsx(pack: dict[str, Any], user: str = "") -> bytes:
    meta = _meta("Inspection evidence pack", pack.get("request") or "Sample request", user, pack["pack_id"])
    wb = hx.workbook(meta)
    hx.table_sheet(wb, "Coverage", meta, [hx.Col("item", "Item"), hx.Col("kind", "Kind"), hx.Col("topic_label", "Topic"),
                                          hx.Col("status", "Status"), hx.Col("reason", "What the pack holds")], pack["coverage"],
                   title="What was asked and what is answered")
    hx.table_sheet(wb, "Figures", meta, [hx.Col("item", "Item"), hx.Col("object", "Facility / object"), hx.Col("figure", "Figure"),
                                         hx.Col("value", "Value", "num"), hx.Col("unit", "Unit"), hx.Col("source", "Source (relation [key] period)")],
                   _figure_rows(pack), title="Figures with lineage")
    hx.table_sheet(wb, "Approvals", meta, [hx.Col("item", "Item"), hx.Col("decision", "Decision / deal"), hx.Col("quarter", "Quarter"),
                                           hx.Col("case", "Case"), hx.Col("outcome", "Outcome"), hx.Col("level", "Level / role"),
                                           hx.Col("received", "Received"), hx.Col("decided", "Decided"), hx.Col("days", "Days", "num"),
                                           hx.Col("action", "Action"), hx.Col("source", "Source")], _approval_rows(pack),
                   title="Approvals history")
    hx.table_sheet(wb, "Conditions", meta, [hx.Col("item", "Item"), hx.Col("ref", "Reference"), hx.Col("what", "Condition / exception"),
                                            hx.Col("status", "Status"), hx.Col("source", "Source")], _condition_rows(pack),
                   title="Conditions and exceptions")
    hx.table_sheet(wb, "Policy", meta, [hx.Col("clause", "Clause"), hx.Col("heading", "Section"), hx.Col("quote", "Text"),
                                        hx.Col("policy_id", "Policy")], pack["clauses"], title="Policy clauses that apply")
    hx.about_sheet(wb, meta, [("Request", pack.get("request") or ""), ("Sample", ", ".join(pack.get("sample") or [])),
                              ("Sample rule", pack.get("sample_rule") or "As requested"), ("Summary", " ".join(pack["lines"])),
                              ("Method", pack["method"]), ("Data", pack["data_note"])], index=0)
    return hx.to_bytes(wb)


def inspection_docx(pack: dict[str, Any], user: str = "") -> bytes:
    meta = _meta("Inspection evidence pack", pack.get("request") or "Sample request", user, pack["pack_id"])
    s = pack["coverage_summary"]
    doc = hd.document(meta, kind="Evidence pack", subtitle=pack.get("request") or "Sample request", cover=True,
                      details=[("Pack", pack["pack_id"]), ("As of", pack["as_of"]), ("Items", str(len(pack["items"])))])
    hd.heading(doc, "Summary", 1)
    hd.key_figures(doc, [("Answered", str(s["answered"])), ("Partly answered", str(s["partial"])), ("Not available", str(s["not_available"]))])
    hd.bullets(doc, pack["lines"])
    if pack.get("answers"):  # R14 G (K15): the answer itself, one row per item
        hd.heading(doc, "Answer per item", 1)
        hd.para(doc, (pack.get("summary") or "").replace("(demo seed)", "(fictional seed, see Method and data)"))
        hd.table(doc, ["Item", "Name", "EAD", "Stage path", "Approval", "Conditions"],
                 [[a["item"], a["name"], f"SAR {a['ead']['value']:,.1f}m" if a.get("ead") else "–", a.get("stage_path") or "–",
                   (a.get("approval") or {}).get("text") or "–", (a.get("conditions") or {}).get("text") or "–"] for a in pack["answers"]],
                 widths=[2.0, 3.6, 2.0, 4.0, 3.4, 2.0])
    hd.heading(doc, "Coverage: what was asked and what is answered", 1)
    hd.table(doc, ["Item", "Topic", "Status", "What the pack holds"],
             [[c["item"], c["topic_label"], c["status"].replace("_", " "), c["reason"]] for c in pack["coverage"]], widths=[2.6, 3.8, 2.6, 8])
    for it in pack["items"]:
        ev = it.get("evidence")
        hd.heading(doc, f"{it['id']} · {it['kind']}" + (f" · {ev.get('name') or ev.get('deal_name') or ''}" if ev else ""), 1)
        if not ev:
            hd.para(doc, "Not found in Data Domains.")
            continue
        facs = ev.get("facilities") or []
        if facs:
            hd.heading(doc, "Facilities", 2)
            hd.table(doc, ["Facility", "Limit", "EAD", "Stage", "DPD", "ECL", "Source"],
                     [[f["facility_id"], _v(f["limit"]), _v(f["ead"]), _v(f["stage"]), _v(f["dpd"]), _v(f["ecl"]), _src(f["ead"])]
                      for f in facs], kinds=["", "sar_mn", "sar_mn", "int", "int", "sar_mn", ""], right_from=1)
        decs = ev.get("decisions") or []
        if decs:
            hd.heading(doc, "Approvals, conditions and exceptions", 2)
            hd.table(doc, ["Decision", "Quarter", "Outcome", "Level", "Steps", "Conditions", "Exceptions"],
                     [[d["decision_id"], d["quarter"], d["decision"].replace("_", " "), d["required_level"],
                       " → ".join(f"{s['level']} {s['output']} ({s['days']}d)" for s in d["steps"]),
                       f"{d['conditions']['met']}/{d['conditions']['set']} met",
                       ", ".join(f"{x['type']} ({x['clause']})" for x in d["exceptions"]) or "none"] for d in decs])
        deals = [x for x in (ev.get("deals") or []) if x] + ([ev] if it["kind"] == "deal" else [])
        for dl in deals:
            hd.heading(doc, f"Deal {dl['proposal_id']} ({dl.get('status')})", 2)
            if dl.get("workflow"):
                hd.bullets(doc, [f"{w['seq']}. {w['to_state']} — {w['actor']} ({w['role']}), {str(w['at'])[:10]}" for w in dl["workflow"]])
            if dl.get("conditions"):
                hd.table(doc, ["Condition", "Kind", "Status", "Text"],
                         [[c["condition_id"], c["kind"], c["status"], c["text"]] for c in dl["conditions"]], widths=[2.6, 2.4, 2.4, 9.6])
    hd.heading(doc, "Policy clauses that apply", 1)
    hd.table(doc, ["Clause", "Text"], [[c["clause"], c["quote"]] for c in pack["clauses"]], widths=[1.6, 15.4])
    hd.heading(doc, "Method and data", 1)
    hd.para(doc, pack["method"])
    hd.para(doc, pack["data_note"])
    return hd.to_bytes(doc)


def engine_xlsx(kind: str, out: dict[str, Any], user: str = "") -> bytes:
    """Excel for exception intelligence, RM track record and DoA calibration."""
    titles = {"exceptions": "Exception intelligence", "rm": "RM track record", "doa": "DoA calibration"}
    meta = _meta(titles[kind], "Governance history 2021Q4–2025Q2, outcomes to 2026Q2", user)
    wb = hx.workbook(meta)
    if kind == "exceptions":
        rows = [{"label": t["label"], "n": t["n"], "judged_on": t.get("judged_on"), "default": (t.get("default") or {}).get("pct"),
                 "lo": (t.get("default") or {}).get("ci_low_pct"), "hi": (t.get("default") or {}).get("ci_high_pct"),
                 "exp": t.get("expected_default_pct"), "oe": t.get("oe_default"), "mig": (t.get("migration") or {}).get("pct"),
                 "verdict": t["verdict"]} for t in out["types"]]
        hx.table_sheet(wb, "By type", meta, [hx.Col("label", "Exception type"), hx.Col("n", "n", "int"), hx.Col("judged_on", "Judged on"),
                                             hx.Col("default", "Default 12m", "pct"), hx.Col("lo", "CI low", "pct"), hx.Col("hi", "CI high", "pct"),
                                             hx.Col("exp", "Expected (peers)", "pct"), hx.Col("oe", "Observed / expected", "num"),
                                             hx.Col("mig", "Migration 12m", "pct"), hx.Col("verdict", "Verdict")], rows)
        led = [{**{k: r[k] for k in ("exception_id", "borrower_name", "quarter", "label", "clause", "approved_by", "rm")},
                "worst": r["after"]["worst_stage"], "dpd": r["after"]["max_dpd"], "default": r["after"]["default"],
                "notches": r["after"]["notches"]} for r in out["ledger"]]
        hx.table_sheet(wb, "Ledger", meta, [hx.Col("exception_id", "Exception"), hx.Col("borrower_name", "Borrower"), hx.Col("quarter", "Quarter"),
                                            hx.Col("label", "Type"), hx.Col("clause", "Clause"), hx.Col("approved_by", "Approved by"),
                                            hx.Col("rm", "RM"), hx.Col("worst", "Worst stage", "int"), hx.Col("dpd", "Max DPD", "int"),
                                            hx.Col("default", "Defaulted", "int"), hx.Col("notches", "Notches", "int")], led)
    elif kind == "rm":
        rows = [{"name": r["name"], "unit": r.get("branch") or r.get("region"), "approved": r["approved"], "quality": _v(r["quality"]),
                 "queries": r["queries_per_file"], "cond": (r["conditions"] or {}).get("pct"), "prom": (r["promises"] or {}).get("pct"),
                 "oe": r["oe"], "score": r["score"], "flag": r["flag"]} for r in out["rows"]]
        hx.table_sheet(wb, "Track record", meta, [hx.Col("name", "Name"), hx.Col("unit", "Branch / region"), hx.Col("approved", "Approvals", "int"),
                                                  hx.Col("quality", "Quality", "num"), hx.Col("queries", "Queries per file", "num"),
                                                  hx.Col("cond", "Conditions met", "pct"), hx.Col("prom", "Promises delivered", "pct"),
                                                  hx.Col("oe", "Defaults O/E", "num"), hx.Col("score", "Score", "num"), hx.Col("flag", "Flag")], rows)
    else:
        rows = [{"level": l["level"], "files": l["files"], "med": l["median_days"], "p75": l["p75_days"], "share": l["share_of_turnaround_pct"],
                 "pt": (l["pass_through"]["changed"] or {}).get("pct"), "dc": (l["deciding"]["changed"] or {}).get("pct"),
                 "decl": (l["deciding"]["declined"] or {}).get("pct"), "ovr": (l["deciding"]["overturned"] or {}).get("pct")}
                for l in out["levels"]]
        hx.table_sheet(wb, "Levels", meta, [hx.Col("level", "Level"), hx.Col("files", "Files", "int"), hx.Col("med", "Median days", "num"),
                                            hx.Col("p75", "P75 days", "num"), hx.Col("share", "Share of time", "pct"),
                                            hx.Col("pt", "Changed when passing up", "pct"), hx.Col("dc", "Changed when deciding", "pct"),
                                            hx.Col("decl", "Declined", "pct"), hx.Col("ovr", "Overturned", "pct")], rows)
        hx.table_sheet(wb, "Proposals", meta, [hx.Col("change", "Proposed change"), hx.Col("why", "Evidence"),
                                               hx.Col("days_saved_per_year", "File-days saved a year", "int"),
                                               hx.Col("control_given_up", "Past changes forgone", "int")], out["proposals"])
    hx.about_sheet(wb, meta, [("Summary", " ".join(out["lines"])), ("Method", out["method"]), ("Data", out["data_note"])], index=0)
    return hx.to_bytes(wb)


def dumps(o: Any) -> str:
    return json.dumps(o, default=str)
