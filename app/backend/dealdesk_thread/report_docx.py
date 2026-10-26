"""The 5-page Deal Desk Word report (DEAL_DESK_PROMPT section 4), in house style.

  1. Deal summary and recommendation
  2. Obligor and financials
  3. Ask vs recommended structure, with RAROC and capital
  4. Risk appetite and constraint analysis
  5. Stress results and the draft risk opinion

Every figure comes from engine calls made for the report (`engine.py`); the
draft opinion is the conversation's Draft answer (validated against those
calls). The trace IDs of the calls are listed on page 5. Styling is
backend.house_style.docx: a cover block on page 1, the running header and
classification, the footer with the reference and "Page X of Y".

`section()` builds the same content as a Playbook section (PLAYBOOK_API.md 3).
"""
from __future__ import annotations

import io
import re
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from backend.house_style import ACCENT as BRAND  # noqa: E402
from backend.house_style import Meta  # noqa: E402
from backend.house_style import docx as hd  # noqa: E402

from backend.dealdesk_thread import engine  # noqa: E402

UP, DOWN, TOTAL = "#12704B", "#A92A25", "#" + BRAND
hd.chart_style()

FACILITY = {"term_loan": "Term finance", "revolver": "Revolving working capital", "performance_lg": "Performance LG",
            "financial_lg": "Financial LG", "trade_lc": "Trade LC"}


from backend.dealdesk import fmt as F  # noqa: E402
from backend.dealdesk_thread import method_appendix, proposal_full  # noqa: E402

GUARANTEE_LABEL = {"REQ-PARENT": "Parent guarantee (requested)", "REQ-BANK": "Bank guarantee (requested)",
                   "REQ-SOVEREIGN": "Sovereign guarantee (requested)", "REQ-ECA": "ECA cover (requested)"}


def pct(x: float | None, d: int | None = None) -> str:
    return F.pct(x, d)


def sar(x: float | None) -> str:
    return F.sar(x)


def amt(x: float, ccy: str) -> str:
    return F.amount(x, ccy)


def cval(c: dict, v: Any = None) -> str:
    v = c["value"] if v is None else v
    return F.by_unit(v, c.get("unit", ""))


def _repay(t: dict) -> str:
    a = t.get("amortisation")
    if a == "balloon":
        return f"Balloon {F.num(t.get('balloon_pct', 0))}%"
    return str(a or "").capitalize()


TERM_ROWS = [
    ("Facility", lambda t: FACILITY.get(t["facility_type"], t["facility_type"])),
    ("Structure", lambda t: str(t["structure"]).capitalize()),
    ("Amount", lambda t: amt(t["amount"], t["currency"])),
    ("Hold level", lambda t: f"{round(float(t.get('hold_pct', 100)), 1):g}%"),
    ("Tenor", lambda t: f"{t['tenor_years']} years"),
    ("Grace", lambda t: f"{t.get('grace_years', 0)} years"),
    ("Repayment", _repay),
    ("Rate", lambda t: str(t.get("rate_type", "floating")).capitalize()),
    ("Margin", lambda t: f"{'SOFR' if t['currency'] == 'USD' else 'SAIBOR'} + {F.bps(t['margin_bps'])}"),
    ("Upfront fee", lambda t: F.bps(t["upfront_fee_bps"])),
    ("Commitment fee", lambda t: F.bps(t.get("commitment_fee_bps", 0))),
    ("Commission", lambda t: F.bps(t.get("commission_bps", 0))),
    ("Prepayment fee", lambda t: F.bps(t.get("prepayment_fee_bps", 0))),
    ("Cash margin", lambda t: f"{round(float(t.get('cash_margin_pct', 0)), 1):g}%"),
    ("Collateral pledged", lambda t: ", ".join(t.get("collateral_ids") or []) or "None"),
    ("Guarantee", lambda t: f"{GUARANTEE_LABEL.get(t['guarantee_id'], t['guarantee_id'])} · {round(float(t.get('guarantee_coverage_pct', 0)), 1):g}%"
     if t.get("guarantee_id") else "None"),
    ("Credit insurance", lambda t: f"{round(float(t.get('insurance_cover_pct', 0)), 1):g}%"),
    ("Assigned receivables", lambda t: f"{round(float(t.get('receivables_assignment_pct', 0)), 1):g}%"),
    ("Covenant package", lambda t: str(t.get("covenant_package", "standard")).capitalize()),
    ("Covenants and conditions", lambda t: ", ".join(x.replace("_", " ") for x in t.get("covenant_items") or []) or "Package only"),
    ("Review cycle", lambda t: f"{t.get('review_cycle_months', 12)} months"),
    ("Cross-sell committed", lambda t: ", ".join(x.replace("_", " ") for x in t.get("cross_sell") or []) or "None"),
]


def gather(pid: str, terms: dict | None, state: dict, appendix: bool = True) -> dict[str, Any]:
    rec = engine.Recorder()
    p = rec.get(f"/proposals/{pid}")["proposal"]
    ask = rec.post("/compute", {"proposal_id": pid})
    cur = rec.post("/compute", {"proposal_id": pid, "terms": terms}) if terms else ask
    stress = rec.post("/stress", {"proposal_id": pid, "terms": terms, "scenario": "all"})
    out = {"p": p, "ask": ask, "cur": cur, "stress": stress, "opt": None, "alts": None, "recommended": bool(terms)}
    if appendix:
        if state.get("optimisation"):
            try:
                out["opt"] = rec.post("/optimize", {"proposal_id": pid, "objective": "both", **(state.get("optimise_request") or {})})
            except engine.EngineError:
                out["opt"] = None
        if out["opt"] and "alternatives" in out["opt"]:
            out["alts"] = {"alternatives": out["opt"]["alternatives"], "single_lever": out["opt"]["single_lever"]}
        else:
            try:
                out["alts"] = rec.post("/alternatives", {"proposal_id": pid, **{k: v for k, v in (state.get("optimise_request") or {}).items()
                                                                                 if k in ("fixed", "bounds", "allow_soft") and v}})
            except engine.EngineError:
                out["alts"] = None
        out["param_tables"] = rec.get("/params").get("tables", [])
        out["meta"] = engine.get("/meta")
        out["tornado"] = rec.post("/tornado", {"proposal_id": pid, "terms": terms})
        # R7 U2: the same axis as the screen, so the ask and the hurdle contour are on the grid (commission for an LG/LC).
        from backend.dealdesk_thread.api import heat_axis
        hx, hxs, hys = heat_axis({**p["ask"], **(terms or {})})
        out["heatmap"] = rec.post("/grid", {"proposal_id": pid, "terms": terms, "x": hx, "x_values": hxs,
                                            "y": "tenor_years", "y_values": hys, "metric": "lifetime_raroc"})
        a0 = p["ask"]["amount"]
        out["amount_curve"] = rec.post("/grid", {"proposal_id": pid, "terms": terms, "x": "amount",
                                                 "x_values": [round(a0 * s, 3) for s in (0.6, 0.8, 1.0, 1.2)], "metric": "lifetime_raroc"})
    out["traces"] = rec.trace_ids
    return out


def _draft(pid: str, p: dict, state: dict) -> str:
    from backend.dealdesk_thread import convo

    class _S:
        def state(self, _pid: str) -> dict:
            return dict(state)

        def set_state(self, *_a: Any) -> None:
            pass
    a = convo.answer(_S(), p, "Draft the credit risk opinion, conditions precedent and covenants", {})
    return "\n".join(b.get("markdown") or "" for b in a["blocks"])


def _waterfall_png(bars: list[dict]) -> io.BytesIO:
    fig, ax = plt.subplots(figsize=(7.2, 2.3))
    running = 0.0
    for i, b in enumerate(bars):
        if b.get("total"):
            bottom, height, colour = 0.0, b["value"], TOTAL
        else:
            v = b["value"]
            bottom = running if v >= 0 else running + v
            height, colour = abs(v), (UP if v >= 0 else DOWN)
            running += v
        ax.bar(i, height, bottom=bottom, color=colour, width=0.62)
        ax.text(i, bottom + height, F.sar(b["value"]), ha="center", va="bottom", fontsize=6)
    ax.set_xticks(range(len(bars)))
    ax.set_xticklabels([b["step"] for b in bars], rotation=25, ha="right", fontsize=7)
    ax.set_ylabel("PV, SAR million", fontsize=8)
    ax.tick_params(axis="y", labelsize=7)
    ax.spines[["top", "right"]].set_visible(False)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=160, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


def _md_paras(doc, md: str) -> None:
    items: list[str] = []
    for line in md.splitlines():
        line = line.strip()
        if line.startswith("- "):
            items.append(line[2:])
            continue
        if items:
            hd.bullets(doc, items)
            items = []
        if line.startswith("#"):
            hd.heading(doc, line.lstrip("#").strip(), 3)
        elif line:
            hd.para(doc, line)
    if items:
        hd.bullets(doc, items)


PAIR_WIDTHS = (2.5, 6.0, 2.5, 6.0)


def _fix_widths(t, widths) -> None:
    """Fixed column widths that Word and LibreOffice both honour (autofit off, grid and cells set)."""
    from docx.shared import Cm
    t.autofit = False
    for i, w in enumerate(widths):
        t.columns[i].width = Cm(w)
        for c in t.columns[i].cells:
            c.width = Cm(w)


def _pairs(rows: list[tuple[str, str]]) -> list[list[str]]:
    """Label/value rows laid out two pairs per table row, so the proposal stays on one page."""
    half = (len(rows) + 1) // 2
    left, right = rows[:half], rows[half:]
    return [[a, b] + (list(right[i]) if i < len(right) else ["", ""]) for i, (a, b) in enumerate(left)]


def proposal_pages(doc, p: dict) -> None:
    """D5: the complete proposal as the business submitted it, before any analysis (page 1)."""
    full = proposal_full.full(p)
    hd.heading(doc, "1. The proposal as submitted")
    tb = hd.table(doc, ["Obligor, group and deal", "", "", ""],
             _pairs([(r["label"], r["value"]) for r in full["obligor"]] + [(r["label"], r["value"]) for r in full["deal"]]), gap=False, size=7,
             widths=PAIR_WIDTHS)
    _fix_widths(tb, PAIR_WIDTHS)
    lines = full["facility_lines"]
    hd.table(doc, ["Facility line", "Facility", "Amount", "Tenor", "Pricing", "Fees", "Repayment"],
             [[ln["line_id"], f"{ln['facility']} · {ln['structure']}", ln["amount"], ln["tenor"], ln["pricing"], ln["fees"], ln["repayment"]]
              for ln in lines], gap=False, size=7)
    shared = [("Security", lines[0]["security"]), ("Guarantees", lines[0]["guarantees"]), ("Covenants", lines[0]["covenants"])]
    tb = hd.table(doc, ["Security and covenants (all lines)", "", "", ""], _pairs(shared + [("Memo reference", next(
        (r["value"] for r in full["deal"] if r["label"] == "Credit memo"), ""))]), gap=False, size=7)
    _fix_widths(tb, PAIR_WIDTHS)


def exposure_and_financials(doc, p: dict) -> None:
    full = proposal_full.full(p)
    if full["existing_facilities"]:
        hd.table(doc, ["Existing facility", "Product", "Limit", "Drawn", "EAD", "Stage"],
                 [[f["facility_id"], f["product"], f["limit"], f["drawn"], f["ead"], f["stage"]] for f in full["existing_facilities"]],
                 right_from=2, gap=False, size=7)
    years = p["financials"]["years"]
    hd.table(doc, [f"Financials, {p['financials'].get('currency', 'SAR')} m"] + [f"{y['year']}{' P' if y.get('kind') == 'projection' else ''}" for y in years],
             [[lab] + [f"{y[k]:,.1f}" if k != "current_ratio" else F.times(y[k]) for y in years]
              for lab, k in (("Revenue", "revenue"), ("EBITDA", "ebitda"), ("Total debt", "total_debt"), ("Debt service", "debt_service"),
                             ("Net worth", "net_worth"), ("Current ratio", "current_ratio"))], right_from=1, gap=False, size=7)


def appendix_pages(doc, g: dict) -> None:
    """D6: the method appendix: formula, inputs with this deal's values, parameter tables, a worked line."""
    hd.page_break(doc)
    hd.heading(doc, "Appendix A. Method")
    hd.para(doc, "Every metric and chart of this report and of the Deal Desk screens, with its formula, this deal's inputs, the parameter "
                 "tables used (owner and version) and a worked line. Money in SAR million; year 1 unless stated; present values at the hurdle. "
                 "Reference: Deal Desk engine methodology.", size=8)
    for i, e in enumerate(method_appendix.entries(g), start=1):
        hd.heading(doc, f"A.{i} {e['title']}", 2)
        hd.para(doc, f"**Formula.** {e['formula']}", size=8)
        if e["inputs"]:
            hd.table(doc, ["Input", "Value for this deal"], [[x["name"], x["value"]] for x in e["inputs"]], gap=False, size=7.5)
        if e["parameters"]:
            hd.para(doc, "**Parameter tables.** " + "; ".join(f"{x['table']} (owner {x['owner']}, version {x['version']})" for x in e["parameters"]) + ".",
                    size=7.5)
        hd.para(doc, f"**Worked line.** {e['worked']}", size=8)
        if e.get("note"):
            hd.para(doc, e["note"], size=7.5, italic=True)
    hd.heading(doc, "Appendix B. Engine calls", 2)
    hd.para(doc, "Engine calls behind this report: " + ", ".join(dict.fromkeys(g["traces"])) + ".", size=7)


def build(pid: str, terms: dict | None, state: dict, turns: list[dict] | None = None, generated_by: str = "",
          reference: str = "") -> tuple[bytes, str]:
    g = gather(pid, terms, state)
    p, ask, cur, st = g["p"], g["ask"], g["cur"], g["stress"]
    ob, m, m0 = p["obligor"], cur["metrics"], ask["metrics"]
    rec_name = "Recommended" if g["recommended"] else "Ask"
    from backend.dealdesk.economics import reporting_period  # R14 E (K18 #2): one reporting period
    meta = Meta(f"Deal Desk · {ob['name']}", book="corporate", period=reporting_period()["quarter"], subject=f"{pid} · {ob['sector']} · {ob['internal_rating']}",
                generated_by=generated_by, reference=f"{reference or pid}")
    doc = hd.document(meta, kind="Pre-deal analysis", subtitle=f"{ob['name']} · {pid}", cover="block")

    # 1. The proposal as submitted (D5)
    proposal_pages(doc, p)
    hd.page_break(doc)

    # 2. Deal summary and recommendation (the obligor's existing exposure and financials first)
    hd.heading(doc, "2. Exposure, financials and recommendation")
    exposure_and_financials(doc, p)
    t = cur["terms"]
    verdict = "clears" if m["clears_hurdle"] else "does not clear"
    hard = [c for c in cur["constraints"] if c["status"] == "breach" and c["kind"] == "hard"]
    soft = [c for c in cur["constraints"] if c["status"] == "breach" and c["kind"] == "soft"]
    hd.para(doc, f"{ob['name']} ({ob['internal_rating']}, {ob['sector']}) asks for **{amt(p['ask']['amount'], p['ask']['currency'])}** over "
                 f"{p['ask']['tenor_years']} years at {'SOFR' if p['ask']['currency'] == 'USD' else 'SAIBOR'} + {F.bps(p['ask']['margin_bps'])}. "
                 f"On the ask, lifetime RAROC is {pct(m0['lifetime_raroc'])} against the {pct(m0['hurdle'])} hurdle.")
    hd.para(doc, (f"**{'Recommended structure' if g['recommended'] else 'The ask as it stands'}:** {amt(t['amount'], t['currency'])} over "
                  f"{t['tenor_years']} years at {F.bps(t['margin_bps'])}. Lifetime RAROC {pct(m['lifetime_raroc'])} {verdict} the hurdle; "
                  f"SVA {sar(m['sva'])}. " + (f"Hard limits breached: {', '.join(c['label'] for c in hard)}. " if hard else "Every hard limit passes. ")
                  + (f"Soft breaches for escalation: {', '.join(c['label'] for c in soft)}. " if soft else "")
                  + f"Approval: **{cur['approval']['level']}**."))
    hd.key_figures(doc, [("Amount", amt(t["amount"], t["currency"])), ("Lifetime RAROC", pct(m["lifetime_raroc"])), ("SVA", sar(m["sva"])),
                         ("Breakeven margin", "–" if m0.get("breakeven_margin_bps") is None else F.bps(m0["breakeven_margin_bps"])),
                         ("RWA (year one)", sar(m["rwa_y1"])), ("Approval", cur["approval"]["level"])])
    rows2 = [["Lifetime RAROC", pct(m0["lifetime_raroc"]), pct(m["lifetime_raroc"])],
             ["Relationship RAROC", pct(m0["relationship_raroc"]), pct(m["relationship_raroc"])],
             ["SVA", sar(m0["sva"]), sar(m["sva"])], ["EL (PV)", sar(m0["el_lifetime_pv"]), sar(m["el_lifetime_pv"])],
             ["Day-one ECL", sar(m0["day_one_ecl"]), sar(m["day_one_ecl"])],
             ["Model PD (12 months)", pct(ask["pd"]["model_pd_12m"]), pct(cur["pd"]["model_pd_12m"])]]
    if g["recommended"]:
        hd.table(doc, ["Measure", "Ask", rec_name], rows2, right_from=1, gap=False)
    else:
        hd.table(doc, ["Measure", "Ask"], [r[:2] for r in rows2], right_from=1, gap=False)
    oor = cur["pd"].get("out_of_range") or {}
    if oor.get("status") and oor["status"] != "in_range":
        flagged = [f for f in oor.get("features", []) if f.get("status") != "in_range"]
        hd.para(doc, "**PD model range check:** " + "; ".join(f"{f['feature']} {F.num(f['value'])} outside {F.num(f.get('p01'))}–{F.num(f.get('p99'))}"
                                                            for f in flagged)
                + f". Master-scale PD {pct(cur['pd']['master_scale_pd_12m'])} shown for comparison.", size=8)
    hd.page_break(doc)

    # 3. Ask vs recommended structure, alternatives, RAROC and capital
    hd.heading(doc, "3. Structure, RAROC and capital")
    cols = [("Ask", ask)] + ([(rec_name, cur)] if g["recommended"] else [])
    o = g["opt"]
    if o and o.get("max_sva"):
        cols.append(("Maximum SVA", {"terms": o["max_sva"]["terms"], "metrics": o["max_sva"]["metrics"], "approval": o["max_sva"]["approval"]}))
    alts = ((g.get("alts") or {}).get("alternatives") or [])[:2]
    for a in alts:
        cols.append((a["label"], {"terms": a["terms"], "metrics": a["metrics"], "approval": a["approval"]}))
    base_terms = ask["terms"]
    rows = [[lab] + [f(c["terms"]) for _, c in cols] for lab, f in TERM_ROWS]
    neutral = {"0 bps", "0%", "None", "Package only", "12 months", "Floating", "100%", "0 years"}
    essential = ("Facility", "Structure", "Amount", "Tenor", "Repayment", "Margin", "Upfront fee", "Collateral pledged", "Guarantee",
                 "Covenant package")
    rows = [r for r in rows if r[0] in essential or any(x != r[1] for x in r[2:]) or r[1] not in neutral]
    hd.table(doc, ["Term"] + [n for n, _ in cols], rows, right_from=1, gap=False, size=7)
    hd.heading(doc, "RAROC and capital", 2)
    hd.table(doc, ["Measure"] + [n for n, _ in cols], [
        ["Lifetime RAROC"] + [pct(c["metrics"]["lifetime_raroc"]) for _, c in cols],
        ["SVA"] + [sar(c["metrics"]["sva"]) for _, c in cols],
        ["RWA (year one)"] + [sar(c["metrics"]["rwa_y1"]) for _, c in cols],
        ["Capital (year one)"] + [sar(c["metrics"]["capital_y1"]) for _, c in cols],
        ["EL (PV)"] + [sar(c["metrics"]["el_lifetime_pv"]) for _, c in cols],
        ["Approval"] + [c["approval"]["level"] for _, c in cols]], right_from=1, gap=False, size=7)
    hd.figure(doc, _waterfall_png(cur["waterfall"]), width_cm=11,
              caption=f"Figure 1. RAROC waterfall, {rec_name.lower()} structure: present values over the life, SAR million (method in Appendix A).")
    del base_terms
    hd.page_break(doc)

    # 4. Risk appetite and constraint analysis
    hd.heading(doc, "4. Risk appetite and constraints")
    hd.table(doc, ["Limit", "Scope", "After the deal", "Limit", "Type", "Result"],
             [[c["label"], c.get("scope", ""), cval(c), cval(c, c["limit"]), str(c["kind"]).capitalize(),
               "PASS" if c["status"] == "pass" else "FAIL"] for c in cur["constraints"]], right_from=2, gap=False, size=7.5)
    hd.para(doc, f"**Required approval:** {cur['approval']['level']}. " + "; ".join(cur["approval"].get("reasons") or []) + ".")
    if o and o.get("binding"):
        hd.heading(doc, "Binding constraints", 2)
        hd.table(doc, ["Constraint", "SVA gained per unit of relaxation", "Unit"],
                 [[b.get("label") or b["constraint"].replace("_", " ").capitalize(),
                   "–" if b.get("shadow_price") is None else f"SAR {b['shadow_price'] * 1e6:,.0f}", b.get("unit", "")] for b in o["binding"]],
                 right_from=1, gap=False, size=7.5)
    sl = [x for x in ((g.get("alts") or {}).get("single_lever") or []) if x.get("clears_alone")]
    if sl:
        hd.heading(doc, "Minimum change on a single lever", 2)
        hd.table(doc, ["Lever", "Now", "Clears at", "Lifetime RAROC", "Approval"],
                 [[x["label"] + (f" ({x['note']})" if x.get("note") else ""), _lv(x["from"], x["unit"]), _lv(x["to"], x["unit"]),
                   pct(x.get("lifetime_raroc")), x.get("approval", "")] for x in sl], right_from=1, gap=False, size=7.5)
    if o and not o.get("feasible") and o.get("relaxation"):
        hd.heading(doc, "Minimum relaxation", 2)
        hd.table(doc, ["Lever", "Now", "Needed"], [[x.get("label") or x["lever"].replace("_", " ").capitalize(), _lv(x["from"], x.get("unit", "")),
                                                    "not reachable" if x["to"] is None else _lv(x["to"], x.get("unit", ""))]
                                                   for x in o["relaxation"]], right_from=1, gap=False, size=7.5)
    hd.page_break(doc)

    # 5. Stress results and the draft risk opinion
    hd.heading(doc, "5. Stress and the risk opinion")
    hd.table(doc, ["Scenario", "Lifetime RAROC", "SVA", "EL (PV)", "Client DSCR", "Hurdle"],
             [["Base", pct(st["base"]["lifetime_raroc"]), sar(st["base"]["sva"]), "", "", ""]] +
             [[x["label"], pct(x["lifetime_raroc"]), sar(x["sva"]), sar(x["el_lifetime_pv"]),
               F.times(x.get("dscr_post")), "PASS" if x["clears_hurdle"] else "FAIL"] for x in st["rows"]],
             right_from=1, gap=False, size=7.5)
    hd.para(doc, f"**Robustness:** {st['robustness_notches']} notches of downgrade before lifetime RAROC falls below the hurdle.")
    _md_paras(doc, F.tidy(_draft(pid, p, state)))

    # Appendix (D6)
    appendix_pages(doc, g)
    safe = re.sub(r"[^\w-]+", "-", f"Deal-Desk-{pid}-{ob['name']}")[:80].strip("-")
    return hd.to_bytes(doc), f"{safe}.docx"


def _lv(v: Any, unit: str) -> str:
    if v is None:
        return "–"
    if isinstance(v, list):
        return ", ".join(str(x).replace("_", " ") for x in v) or "None"
    if isinstance(v, str):
        return v.replace("_", " ")
    if unit == "bps":
        return F.bps(v)
    if unit in ("%",):
        return f"{round(float(v), 1):g}%"
    if unit.endswith(" m") or unit == "SAR m":
        return F.amount(v, unit.split()[0]) if unit != "SAR m" else F.sar(v)
    if unit == "x":
        return F.times(v)
    if unit == "years":
        return f"{F.num(v)} years"
    if unit == "share":
        return F.pct(v)
    return F.num(v)


def section(pid: str, terms: dict | None, ref: str) -> dict[str, Any]:
    """The analysis as a Playbook section (PLAYBOOK_API.md 3): figures as raw numbers with formats."""
    g = gather(pid, terms, {}, appendix=False)
    p, ask, cur, st = g["p"], g["ask"], g["cur"], g["stress"]
    ob, m, m0 = p["obligor"], cur["metrics"], ask["metrics"]
    t = cur["terms"]
    kind = "dealdesk-analysis" if ref.startswith("DA-") else "dealdesk-proposal"
    full = proposal_full.full(p)
    txt = [{"key": "item", "label": "Item", "format": "text"}, {"key": "detail", "label": "Detail", "format": "text"}]
    lines = full["facility_lines"]
    blocks = [
        {"kind": "table", "title": "The proposal as submitted: obligor and group", "columns": txt,
         "rows": [{"item": r["label"], "detail": r["value"]} for r in full["obligor"]]},
        {"kind": "table", "title": "Facility lines",
         "columns": [{"key": "term", "label": "Term", "format": "text"}] + [{"key": ln["line_id"], "label": ln["line_id"], "format": "text"} for ln in lines],
         "rows": [{"term": lab, **{ln["line_id"]: ln[k] for ln in lines}} for k, lab in proposal_full.LINE_COLUMNS if k != "line_id"]},
        {"kind": "table", "title": "Purpose, RM, existing exposure and memo", "columns": txt,
         "rows": [{"item": r["label"], "detail": r["value"]} for r in full["deal"]]},
        {"kind": "paragraph", "text": f"**{ob['name']}** ({ob['internal_rating']}, {ob['sector']}). "
                                      f"{'Recommended' if g['recommended'] else 'Asked'}: {amt(t['amount'], t['currency'])} over {t['tenor_years']} years at "
                                      f"{F.bps(t['margin_bps'])}. Lifetime RAROC {pct(m['lifetime_raroc'])} against the {pct(m['hurdle'])} hurdle; "
                                      f"approval {cur['approval']['level']}."},
        {"kind": "kpis", "items": [
            {"label": "Lifetime RAROC", "value": m["lifetime_raroc"], "format": "pct", "delta": m["lifetime_raroc"] - m0["lifetime_raroc"],
             "status": "green" if m["clears_hurdle"] else "red"},
            {"label": "SVA", "value": m["sva"] * 1e6, "format": "sar", "status": "green" if m["sva"] >= 0 else "red"},
            {"label": "RWA (year one)", "value": m["rwa_y1"] * 1e6, "format": "sar"},
            {"label": "Day-one ECL", "value": m["day_one_ecl"] * 1e6, "format": "sar"}]},
        {"kind": "table", "title": "Ask and recommended structure",
         "columns": [{"key": "term", "label": "Term", "format": "text"}, {"key": "ask", "label": "Ask", "format": "text"},
                     {"key": "rec", "label": "Recommended", "format": "text"}],
         "rows": [{"term": lab, "ask": f(ask["terms"]), "rec": f(t)} for lab, f in TERM_ROWS]},
        {"kind": "rag", "title": "Risk appetite and limits after the deal",
         "items": [{"test": c["label"], "value": c["value"] if isinstance(c["value"], (int, float)) else None, "format": "num",
                    "threshold": f"{cval(c, c['limit'])} ({c['kind']})",
                    "status": "green" if c["status"] == "pass" else ("red" if c["kind"] == "hard" else "amber"), "comment": cval(c)}
                   for c in cur["constraints"]]},
        {"kind": "table", "title": "Stress",
         "columns": [{"key": "s", "label": "Scenario", "format": "text"}, {"key": "r", "label": "Lifetime RAROC", "format": "pct"},
                     {"key": "v", "label": "SVA", "format": "sar"}],
         "rows": [{"s": x["label"], "r": x["lifetime_raroc"], "v": x["sva"] * 1e6} for x in st["rows"]],
         "note": f"Robust to {st['robustness_notches']} notches of downgrade."},
    ]
    return {"source": {"type": kind, "id": ref, "label": f"Deal Desk: {ob['name']}", "href": f"/deal-desk/{pid}",
                       "summary": f"{ob['sector']} · {ob['internal_rating']} · RAROC {pct(m['lifetime_raroc'])}"},
            "section": {"title": f"Deal Desk: {ob['name']} ({pid})", "blocks": blocks}}
