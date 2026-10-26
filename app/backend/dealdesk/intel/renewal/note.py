"""The one-page renewal note for a CLEAN renewal (deterministic writer, PLAN_R13 N3) and the full paper for an EXCEPTION.

The note is built from the prepared review (`pack.review`): every figure printed is one of the review's sourced numbers, and
the note lists the relations it read. It renders to Word through the house-style bank-form renderer (same look as the papers).
Exceptions get the full R12 papers engine (bankform.paper.write) on the deal's file, opening the renewal file from the Book
first when the facility has none (book.actions.start_renewal, which publishes the dd_workflow_event).
"""
from __future__ import annotations

from typing import Any

from backend.dealdesk.house_style.bankform import blocks as bk


def _v(x: Any) -> Any:
    return x.get("value") if isinstance(x, dict) else x


def _f(x: Any, fmt: str = "{:,.1f}", none: str = "n/a") -> str:
    v = _v(x)
    if v is None:
        return none
    try:
        return fmt.format(float(v))
    except (TypeError, ValueError):
        return str(v)


OPS = {">": "above", ">=": "at or above", "<": "below", "<=": "at or below", "=": "equal to"}


def _num(v: Any) -> str:
    if v is None:
        return "n/a"
    try:
        x = float(v)
    except (TypeError, ValueError):
        return str(v)
    return f"{x:,.0f}" if x == int(x) else f"{x:,.2f}"


def _commercial_lines(rv: dict[str, Any], repricing: dict[str, Any] | None) -> list[str]:
    out = []
    if "raroc" in rv.get("commercial", []):
        r = rv["risk"]
        line = (f"RAROC is {_f(r['raroc_now_pct'])}% against a {_f(r['hurdle_pct'], '{:,.0f}')}% hurdle "
                f"({_f(r['raroc_orig_pct'])}% at origination)")
        if repricing and repricing.get("text"):
            line += f": {repricing['text']}"
        out.append(line + ".")
    if "promise" in rv.get("commercial", []):
        out.append("A routing or cross-sell promise is unmet: the RM re-commits the undertaking with a date in the renewal.")
    return out


def write(rv: dict[str, Any], repricing: dict[str, Any] | None = None) -> dict[str, Any]:
    """{title, recommendation, sections[{key, heading, blocks}], markdown, sources} for one clean renewal."""
    fin, con, bur, cov, risk = rv["financials"], rv["conduct"], rv["bureau"], rv["covenants_conditions"], rv["risk"]
    name, fid = rv["borrower_name"], rv["facility_id"]
    limit = _f(rv["limit_sar_mn"])
    rec = (f"Renew {fid} ({str(rv.get('product') or '').replace('_', ' ')}) for {name} for 12 months on its existing limit of "
           f"SAR {limit}m: none of the {len(rv['criteria']) - len([c for c in rv['criteria'] if c.get('kind') == 'commercial'])} "
           f"credit criteria fired at the {rv['as_of_quarter']} data.")
    passed = [c for c in rv["criteria"] if c.get("kind") != "commercial" and c["known"] and not c["fired"]]
    untested = [c for c in rv["criteria"] if not c["known"]]
    key_rows = [
        ["Exposure (EAD)", f"SAR {_f(rv['ead_sar_mn'])}m", "ews.corp_exposure"],
        ["Stage / rating", f"{_f(risk['stage'], '{:.0f}')} / {_v(risk['rating_now']) or 'n/a'} (origination {_v(risk['rating_at_origination']) or 'n/a'})", "ews.corp_exposure, ecl_runs.ecl_facility"],
        ["Early Warning", f"{_v(risk['ews_band']) or 'n/a'} (score {_f(risk['ews_score'], '{:.0f}')})", "ews.corp_exposure"],
        ["EBITDA, year on year", f"SAR {_f(fin['ebitda_sar_mn'])}m ({_f(fin['ebitda_yoy_pct'], '{:+.1f}')}%)", "cockpit.corp_borrower_quarter"],
        ["Leverage / DSCR", f"{_f(fin['leverage_x'], '{:.2f}')}x / {_f(fin['dscr_x'], '{:.2f}')}x", "cockpit.corp_borrower_quarter"],
        ["Covenants", f"{_f(cov['covenants'], '{:.0f}')} tested, {_f(cov['covenants_breached'], '{:.0f}')} in breach, min headroom {_f(cov['min_headroom_pct'])}%", "ews.corp_covenant"],
        ["Account inflows", f"SAR {_f(con['inflow_3m_avg_sar_mn'], '{:,.2f}')}m a month ({_f(con['inflow_change_pct'], '{:+.0f}')}% vs prior 6 months)", "deposits.dep_month"],
        ["Bureau", f"other-bank debt SAR {_f(bur['external_exposure_sar_mn'])}m, {_f(bur['external_dpd_days'], '{:.0f}')} days past due", "bureau.bureau_corp_quarter"],
        ["RAROC / hurdle", f"{_f(risk['raroc_now_pct'])}% / {_f(risk['hurdle_pct'], '{:.0f}')}%", "Book drift"],
    ]
    secs = [
        {"key": "recommendation", "heading": "Recommendation", "blocks": [bk.P(rec)]},
        {"key": "key_figures", "heading": "Refreshed figures", "blocks": [bk.T(["Item", "Value", "Source"], key_rows, source=f"Data Domains, {rv['as_of_quarter']}", widths=[4.5, 7.4, 5.5])]},
        {"key": "clean", "heading": "Why it is clean", "blocks": [bk.BL([f"{c['label']}: {_num(c['value'])} (exception if {OPS[c['op']]} {_num(c['threshold'])})" for c in passed])]},
    ]
    com = _commercial_lines(rv, repricing)
    if com:
        secs.append({"key": "conditions", "heading": "Renewal conditions", "blocks": [bk.NL(com)]})
    lim = list(rv.get("data_limits", [])) + [f"Not tested ({c['label']}): no data for this obligor." for c in untested]
    if lim:
        secs.append({"key": "limits", "heading": "What this note could not check", "blocks": [bk.BL(lim)]})
    secs.append({"key": "sign", "heading": "Approval", "blocks": [{"t": "sign", "rows": [("Relationship manager", ""), ("Credit reviewer", "")]}]})
    md = [f"# Renewal note · {name}", "", f"**{fid}** · {rv.get('sector') or ''} · renewal {rv.get('renewal_date')} · data {rv['as_of_quarter']}", ""]
    for s in secs:
        md.append(f"## {s['heading']}")
        for b in s["blocks"]:
            if b["t"] == "p":
                md.append(b["text"])
            elif b["t"] in ("bullets", "numbered"):
                md += [f"{'1.' if b['t'] == 'numbered' else '-'} {i}" for i in b["items"]]
            elif b["t"] == "table":
                md += ["| " + " | ".join(b["header"]) + " |", "|" + "---|" * len(b["header"])] + ["| " + " | ".join(map(str, r)) + " |" for r in b["rows"]]
        md.append("")
    return {"kind": "renewal_note", "facility_id": fid, "borrower_name": name, "title": f"Renewal note · {name}", "recommendation": rec,
            "sections": secs, "markdown": "\n".join(md), "pages": 1, "writer": "deterministic (R13 IB renewal note)"}


def docx(rv: dict[str, Any], note: dict[str, Any]) -> tuple[bytes, str]:
    """The note in Word through the bank-form renderer."""
    from backend.dealdesk.house_style.bankform import render
    lim = _v(rv["limit_sar_mn"]) or 0.0
    paper = {"proposal_id": rv["facility_id"], "customer": rv["borrower_name"], "currency": "SAR", "as_of": rv["as_of_quarter"],
             "request_kind": "renewal", "sector": rv.get("sector") or "", "rating": _v(rv["risk"]["rating_now"]) or "", "group": "",
             "totals": {"existing": lim, "outstanding": _v(rv["ead_sar_mn"]) or 0.0, "proposed": lim}, "sections": note["sections"]}
    return render.docx(paper, kind="Renewal note")


def full_paper(fid: str, by: str) -> dict[str, Any]:
    """The full R12 paper for an exception: the deal's own file, or the renewal file opened from the Book."""
    from backend.dealdesk.book import actions
    from backend.dealdesk.house_style.bankform import paper
    pack = actions.renewal_pack(fid)
    pid = pack.get("proposal_id")
    opened = None
    if not pid:
        opened = actions.start_renewal(fid, by, note="Renewal autopilot: exception, full paper prepared for the CCO")
        pid = opened.get("proposal_id")
    if not pid:
        return {"facility_id": fid, "proposal_id": None, "paper": None,
                "why": (opened or {}).get("text") or "The renewal file could not be opened."}
    p = paper.write(pid)
    return {"facility_id": fid, "proposal_id": pid, "opened_file": bool(opened), "paper": paper.summary(p),
            "links": {"bank_form": f"/api/v1/dealdesk/proposals/{pid}/bank-form", "docx": f"/api/v1/dealdesk/proposals/{pid}/bank-form.docx",
                      "pdf": f"/api/v1/dealdesk/proposals/{pid}/bank-form.pdf", "committee_paper": f"/api/v1/dealdesk/proposals/{pid}/committee-paper",
                      "deal": f"/deal-desk/{pid}"}}
