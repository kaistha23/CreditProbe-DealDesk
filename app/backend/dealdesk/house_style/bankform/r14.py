"""R14 session p: the bank-form writers fed by the selected structure and the one engine per fact (K26, K27; SIB_GAP_AUDIT.md A5,
A6, A7, A10, B2, B16, B19). Each wraps the R12 writer of the same section and adds what the gap audit asks for; with no feed
(the R12 call path) the R12 text is returned unchanged.

    __text__  in a block's text = bold and underlined (a key concern), rendered by render.py in Word and PDF.
"""
from __future__ import annotations

import re
from typing import Any

from backend.dealdesk.house_style.bankform import cp_writers as C
from backend.dealdesk.house_style.bankform import writers as W
from backend.dealdesk.house_style.bankform.blocks import BL, H, KV, NL, P, T
from backend.dealdesk.house_style.bankform.ctx import Deal, d, num

Out = tuple[list[dict[str, Any]], list[str]]
FIELD = {"amount": ("Amount", "m"), "margin_bps": ("Margin", "bps"), "tenor_years": ("Tenor", "years"), "upfront_fee_bps": ("Upfront fee", "bps"),
         "cash_margin_pct": ("Cash margin", "%"), "guarantee_coverage_pct": ("Guarantee cover", "%"), "commission_bps": ("Commission", "bps"),
         "amortisation": ("Amortisation", ""), "balloon_pct": ("Balloon", "%"), "receivables_assignment_pct": ("Receivables assigned", "%"),
         "utilisation_pct": ("Utilisation", "%"), "funded_share_pct": ("Funded share", "%"), "grace_years": ("Grace", "years"),
         "deposit": ("Deposit requirement", "")}  # Round D


def _F(D: Deal):
    return getattr(D, "feed", None)


def _v(x: Any, unit: str, D: Deal) -> str:
    if isinstance(x, (int, float)):
        if unit == "m":
            return D.money(x)
        return f"{x:,.1f}".rstrip("0").rstrip(".") + (f" {unit}" if unit and unit != "%" else unit)
    return str(x)


def change_lines(D: Deal, changes: list[dict[str, Any]]) -> list[str]:
    out = []
    for c in changes or []:
        f = str(c.get("field") or c.get("lever") or "")
        lab, unit = FIELD.get(f, (f.replace("_", " ").capitalize(), ""))
        a, v = c.get("ask", c.get("from")), c.get("value", c.get("to"))
        if a is None and v is None:
            continue
        out.append(f"{lab} {_v(a, unit, D)} → {_v(v, unit, D)}")
    return out


def _pct(x: Any) -> str:
    v = num(x)
    return "–" if v is None else f"{v * 100:,.1f}%"


# ------------------------------------------------------------------------------------------------ 2 action requested

def w_action(D: Deal) -> Out:
    blocks, gaps = W.w_action(D)
    F = _F(D)
    if F is None:
        return blocks, gaps
    st = F.structure
    ch = change_lines(D, st.get("changes"))
    if st["key"] != "ask" and ch:
        blocks.append(P(f"Credit has structured the request as **{st['label']}** ({_asof(D)}): " + "; ".join(ch) + "; the business's ask is kept in section 3 for reference."))
    elif st["key"] == "ask":
        blocks.append(P(f"The proposal is written on the structure as per business ({_asof(D)}); no credit change of amount, tenor or pricing."))
    if st.get("default_note"):
        blocks.append(P(f"{st['default_note'].rstrip('.')} ({_asof(D)})."))
    return blocks, gaps


def _asof(D: Deal) -> str:
    return W._asof(D)  # noqa: SLF001


# ------------------------------------------------------------------------------------------------ 16 geopolitical / market

_DICT = re.compile(r"\{[^{}]*\}")


def _narrative(r: dict[str, Any]) -> str:
    t = str(r.get("narrative") or "")
    if "{" in t or "_" in t.replace("non_oil", "non-oil"):
        t = _DICT.sub("", t)
        t = re.sub(r"\b\w+_\w+\b", lambda m: m.group(0).replace("_", " "), t)
        t = re.sub(r"\s*(revenue|receivable days|gdp)\s*%?,?", "", t, flags=re.I).strip(" ,:;")
    return t


def w_geopolitical(D: Deal) -> Out:
    F = _F(D)
    out: list[dict[str, Any]] = []
    gaps: list[str] = []
    if F is not None and F.regime:
        out.append(H("Current regime"))
        out.append(BL([_attributed(str(x)) for x in F.regime["lines"]]))  # R14 x: m's lines in p's voice rule V1
        out.append(P(f"Source: {F.regime['source']}, read on {_asof(D)}.", exempt=True))
    else:
        gaps.append("current regime")
        out.append(P(f"Current macro regime not available as at {_asof(D)} (session m's regime block not merged; MEV files not readable)."))
    sec = str(D.get("sector", default="")).lower()
    sens = []
    for r in D.rows("dd_stress_sensitivity") or []:
        if str(r.get("sector") or "").lower() == sec:
            sens.append(r)
    sc = [r for r in D.rows("dd_stress_scenario") if str(r.get("scope") or "bank") == "bank" and r.get("family") in ("macro", None)]
    rel = []
    for r in sc:
        name = str(r.get("name") or r.get("label") or "")
        if not name:
            continue
        shocks = r.get("shocks") if isinstance(r.get("shocks"), dict) else {}
        rv = (shocks.get("revenue_pct") or {}) if isinstance(shocks.get("revenue_pct"), dict) else {}
        bysec = {k.lower(): v for k, v in (rv.get("by_sector") or {}).items()} if isinstance(rv, dict) else {}
        if sec and sec in bysec:
            rel.append((abs(float(bysec[sec])), name, r.get("severity"), float(bysec[sec])))
    rel.sort(key=lambda x: (-x[0], x[1]))
    if rel:
        out.append(H(f"Bank scenarios that move {D.get('sector', default='this sector')} most"))
        out.append(BL([f"{n} ({sev}): {D.get('sector', default='sector')} revenue {v * 100:+.1f}% per dd_stress_scenario as at {_asof(D)}." for _, n, sev, v in rel[:3]]))
    else:
        mac = [r for r in sc if r.get("severity") in ("moderate", "severe")][:2]
        if mac:
            out.append(H("Bank scenarios"))
            out.append(BL([f"{r.get('name') or r.get('label')} ({r.get('severity')}) per dd_stress_scenario as at {_asof(D)}." for r in mac]))
    macro = [r for r in D.rows("dd_stress_result") if r.get("family") == "macro"]
    if macro:
        br = [r for r in macro if str(r.get("breaks")) in ("1", "True", "true")]
        out.append(P(f"On the Deal Desk stress of {_asof(D)}, {len(br)} of {len(macro)} macro cases break a limit"
                     + (f"; the first is {br[0].get('what_breaks')} under '{br[0].get('scenario')}' ({br[0].get('severity')})." if br else ".")))
    geo = [r for r in D.rows("dd_business_profile") if r.get("item_kind") in ("geopolitical", "market")]
    out.append(H("As per business"))
    if geo:
        out.append(BL([f"{r.get('label')}: {W._profile_text(r)}" for r in geo]))  # noqa: SLF001
    else:
        out.append(P(f"Effect on routes, ports, input costs and labour as per business: information not provided in the request of {d(D.get('received_date')) or _asof(D)}."))
    return out, gaps


# ------------------------------------------------------------------------------------------------ 19 recommendation

def w_recommendation(D: Deal) -> Out:
    blocks, gaps = W.w_recommendation(D)
    F = _F(D)
    if F is None:
        return blocks, gaps
    st, e, a = F.structure, F.economics or {}, F.approval or {}
    head = []
    ra, hu = (e.get("raroc") or {}).get("lifetime"), (e.get("raroc") or {}).get("hurdle")
    if st["key"] != "ask":
        head.append(f"Approve on the **{st['label']}** structure: " + ("; ".join(change_lines(D, st.get("changes"))) or "terms as in section 3") + f" ({_asof(D)}).")
    if ra is not None:
        head.append(f"Lifetime RAROC {_pct(ra)} against a {_pct(hu)} hurdle and SVA {D.money((e.get('sva') or {}).get('lifetime'), 2)} on the "
                    f"{(e.get('basis') or {}).get('raroc', 'lifetime')} basis, per {e.get('source', 'the economics engine')} ({_asof(D)}).")
    if a.get("level"):
        head.append(f"Approval authority: **{a['level']}**; rule: {a.get('rule') or 'not provided'} (per the engine's delegation of authority, {_asof(D)}).")
    cap = F.capacity or {}
    if cap.get("capacity_sar_mn") is not None:
        within = cap.get("within")
        head.append(f"Capacity ({cap.get('method_label') or cap.get('method')}): {D.money(cap.get('capacity_sar_mn'))} against {D.money(cap.get('ask_sar_mn'))} requested"
                    + ("" if within else " — __the structure is sized to capacity__") + f" ({_asof(D)}).")
    sp = F.stress_proof
    if sp:
        head.append(f"Stress-proofed to **{sp.get('target') or sp.get('target_severity') or 'moderate'}** severity on {d(str(sp.get('created_at') or '')[:10]) or _asof(D)} "
                    f"(per dd_stress_proof {sp.get('proof_id') or sp.get('run_id') or ''}).")
    cures = (F.counter or {}).get("cures") or []
    crit = [c for c in cures if str(c.get("severity")) in ("critical", "major")]
    for b in blocks:  # the selected structure replaces the R12 optimiser line (one structure in the paper)
        if b.get("t") == "numbered":
            b["items"] = [x for x in b["items"] if not str(x).startswith("Structure as per CreditProbe's recommended alternative")]
    nl = [b for b in blocks if b.get("t") == "numbered"]
    if nl and blocks[0].get("t") == "p":
        dec, cond = len(nl[0]["items"]), (len(nl[1]["items"]) if len(nl) > 1 else 0)
        blocks[0] = dict(blocks[0], text=re.sub(r"the \d+ decisions and \d+ additional conditions",
                                                f"the {dec + len(head)} decisions and {cond} additional conditions", blocks[0]["text"]))
    out = [blocks[0]]
    if head:
        out += [H("Decision on the selected structure"), NL(head)]
    out += blocks[1:]
    if crit:
        out.append(H("Findings and their cures"))
        out.append(T(["Finding", "Severity", "Cure", "Owner", "When"],
                     [[("__" + str(c.get("title")) + "__") if c.get("severity") == "critical" else c.get("title"), c.get("severity"), c.get("cure") if c.get("curable", True) else "Not curable by structure: " + str(c.get("cure") or ""),
                       c.get("owner") or "–", c.get("when") or "–"] for c in crit[:14]],
                     source="session e findings engine (dd_review_finding + live rules), counter_offer", widths=[6.0, 1.6, 6.4, 1.6, 1.8], size=7.0))
        if len(crit) > 14:
            out.append(P(f"{len(crit) - 14} further critical or major findings are in the findings register as at {_asof(D)}."))
        nc = (F.counter or {}).get("not_curable") or []
        if nc:
            out.append(P(f"__{len(nc)} finding(s) not curable by structure__ as at {_asof(D)}: " + "; ".join(str(x.get("title") if isinstance(x, dict) else x) for x in nc[:5]) + "."))
    return out, gaps


# ------------------------------------------------------------------------------------------------ 20 signatures

def w_signatures(D: Deal) -> Out:
    from backend.dealdesk.house_style.bankform.blocks import BOX, SIGN
    F = _F(D)
    a = (F.approval if F else None) or {}
    level = a.get("level") or W.approval_authority(D)
    rule = a.get("rule") or "per the bank's delegation of authority"
    analyst = str(D.get("credit_analyst", default="") or "")
    return [SIGN([("Analyst / Senior Manager, Credit", analyst), ("VP Credit", ""), ("Chief Credit Officer", "")]),
            BOX("CRO review / comments", 4),
            BOX(f"Credit committee approval / instructions · approval authority: {level} · rule: {rule}", 5)], []


# ------------------------------------------------------------------------------------------------ CreditProbe: RAROC / SVA and the selected structure

def w_raroc(D: Deal) -> Out:
    F = _F(D)
    if F is None or not F.economics:
        return C.w_raroc(D)
    rows = []
    for lab, e in (("As asked", F.economics_ask), (F.structure["label"] if F.structure["key"] != "ask" else None, F.economics if F.structure["key"] != "ask" else None)):
        if not lab or not e:
            continue
        r, s = e.get("raroc") or {}, e.get("sva") or {}
        el, pdv, lg = e.get("el") or {}, e.get("pd") or {}, e.get("lgd") or {}
        rows.append([lab, D.m(e.get("ead_y1")), _pct(pdv.get("model_12m") or pdv.get("master_scale_12m")), _pct(lg.get("y1")), D.m(el.get("y1"), 2),
                     D.m((e.get("rwa") or {}).get("y1")), _pct(r.get("lifetime")), _pct(r.get("one_year")), _pct(r.get("hurdle")), D.m(s.get("lifetime"), 2),
                     "Yes" if r.get("clears") else "**No**"])
    basis = (F.economics.get("basis") or {}).get("label") or "lifetime"
    blocks = [T(["Structure", "EAD y1", "PD 12m", "LGD", "EL y1", "RWA y1", "RAROC (lifetime)", "RAROC (1-year)", "Hurdle", "SVA (lifetime)", "Clears"], rows,
                source=f"{F.economics.get('source')} · basis {basis}", widths=[3.6, 1.3, 1.2, 1.1, 1.2, 1.3, 1.6, 1.5, 1.2, 1.5, 1.0], size=6.8)]
    e = F.economics
    r = e.get("raroc") or {}
    blocks.append(P(f"On the {F.structure['label']} structure, lifetime RAROC is {_pct(r.get('lifetime'))} against a {_pct(r.get('hurdle'))} hurdle "
                    f"({'clears' if r.get('clears') else '__below the hurdle__'}) with SVA of {D.money((e.get('sva') or {}).get('lifetime'), 2)} ({basis}), "
                    f"per {e.get('source')} for {(e.get('period') or {}).get('label') or _asof(D)}."))
    rel = (e.get("raroc") or {}).get("relationship")
    if rel is not None:
        blocks.append(P(f"With the relationship's ancillary income and deposits, RAROC is {_pct(rel)} (relationship view, {_asof(D)})."))
    ss = (F.structure.get("row") or {})
    if ss:
        cap = ss.get("capacity") if not isinstance(ss.get("capacity"), dict) else (ss["capacity"].get("capacity_sar_mn") or ss["capacity"].get("capacity"))
        ap = ss.get("approval") if not isinstance(ss.get("approval"), dict) else ss["approval"].get("level")
        ch = ss.get("covenant_headroom")
        ch = min((x.get("headroom_pct") for x in ch if isinstance(x, dict) and x.get("headroom_pct") is not None), default=None) if isinstance(ch, list) else ch
        blocks.append(P(f"Structure set row ({ss.get('label')}): DSCR {num(ss.get('dscr')) or 0:,.2f}x; capacity {D.money(cap) if isinstance(cap, (int, float)) else '–'}; "
                        f"tightest covenant headroom {('%.1f%%' % ch) if isinstance(ch, (int, float)) else '–'}; approval {ap or '–'} (per dd_structure_set, {_asof(D)})."))
    return blocks, []


def w_selected(D: Deal) -> Out:
    """CreditProbe section: the selected structure, its approval path and capacity (one engine per fact)."""
    F = _F(D)
    if F is None:
        return [P(f"Selected structure not available: the writer was called without the deal file feed ({_asof(D)}).")], ["feed"]
    st, a, cap = F.structure, F.approval or {}, F.capacity or {}
    blocks = [KV([("Structure", st["label"]), ("Source", st["source"]), ("Changes from the ask", "; ".join(change_lines(D, st.get("changes"))) or "none"),
                  ("Approval authority", a.get("level") or "not available"), ("Binding rule", a.get("rule") or "not available"),
                  ("Capacity", (D.money(cap.get("capacity_sar_mn")) + f" ({cap.get('method_label') or cap.get('method')})") if cap.get("capacity_sar_mn") is not None else "not available")], cols=2)]
    if st.get("default_note"):
        blocks.append(P(f"{st['default_note'].rstrip('.')} ({_asof(D)})."))
    rs = a.get("reasons") or []
    if rs:
        blocks.append(T(["Basis", "Level", "Detail"], [[x.get("label") or x.get("basis"), x.get("level"), x.get("detail")] for x in rs[:8]],
                        source=a.get("source", ""), widths=[3.2, 4.0, 10.2], size=7.2))
    if cap.get("formula"):
        blocks.append(P(f"Capacity: {cap['formula']} ({_asof(D)})."))
    sp = F.stress_proof
    if sp:
        blocks.append(P(f"Stress-proofing: the structure was proofed to {sp.get('target') or sp.get('target_severity')} severity "
                        f"({str(sp.get('summary') or sp.get('interpretation') or 'see the stress section').rstrip('.')}; per dd_stress_proof, {_asof(D)})."))
    else:
        blocks.append(P(f"Stress-proofing: a stress-proofed structure is not available for this deal as at {_asof(D)} (dd_stress_proof)."))
    pl = F.pipeline
    blocks.append(H("Pipeline fit"))
    if pl:
        blocks.append(BL([f"{str(x).rstrip('.')}, per the Deal Desk pipeline test ({_asof(D)})." for x in (pl.get("verdict"), pl.get("value_text"), pl.get("displaces_text"),
                                                                                                    pl.get("closest_limit")) if x]))
    else:
        blocks.append(P(f"Pipeline fit not available: the pipeline test could not run on this structure as at {_asof(D)}."))
    return blocks, []


# ------------------------------------------------------------------------------------------------ 3 facilities (landscape, full columns)

def w_facilities(D: Deal) -> Out:
    lines = W._limits(D)  # noqa: SLF001
    if not lines:
        return W.w_facilities(D)
    kids: dict[str, list[dict[str, Any]]] = {}
    for r in lines:
        kids.setdefault(str(r.get("parent_limit_id") or ""), []).append(r)
    rows = []

    def pr(r: dict[str, Any]) -> str:
        bm, sp, fl = r.get("benchmark"), num(r.get("spread_pct")), num(r.get("floor_pct"))
        if bm:
            return f"{bm} + {sp:.2f}%" + (f", floor {fl:.2f}%" if fl else "") if sp is not None else str(bm)
        p = str(r.get("pricing") or "")
        return p if p and "commission" not in p else "–"

    def add(r: dict[str, Any], depth: int) -> None:
        cm, com = num(r.get("cash_margin_pct")), num(r.get("commission_pct_pa"))
        rows.append([("    " * depth) + str(r.get("name", "")), str(r.get("product_code") or "–"), D.m(r.get("existing")), D.m(r.get("outstanding")),
                     D.m(r.get("proposed")), (f"{cm:g}%" if cm else "–"), (f"{com:.2f}% p.a." if com else "–"), pr(r), str(r.get("tenor") or "–"),
                     str(r.get("repayment") or "–"), str(r.get("validity") or r.get("particulars") or "–")])
        for k in kids.get(str(r.get("limit_id")), []):
            add(k, depth + 1)
    for r in kids.get("", []):
        add(r, 0)
    te, to, tp = W.totals(D)
    rows.append(["**Total limits**", "", D.m(te), D.m(to), D.m(tp), "", "", "", "", "", ""])
    src = D.src("dd_facility_limit") if D.rows("dd_facility_limit") else D.src("dd_proposal_facility")
    blocks = [T(["Limit / sub-limit", "Product", f"Existing ({D.ccy} m)", "Outstanding", "Proposed", "Cash margin", "Commission", "Benchmark + spread, floor",
                 "Tenor / validity", "Repayment", "Particulars"], rows, source=src, widths=[5.2, 1.3, 1.5, 1.6, 1.5, 1.3, 1.6, 3.2, 2.6, 2.6, 3.4], size=6.9)]
    used = (to / te) if te else None
    blocks.append(P(f"Total limits of {D.money(tp)} proposed against {D.money(te)} existing as at {_asof(D)}; outstanding {D.money(to)}"
                    + (f" ({used * 100:,.1f}% of existing limits)." if used is not None else ".")))
    if not D.rows("dd_facility_limit"):
        blocks.append(P(f"The limit and sub-limit tree is not provided in Data Domains (dd_facility_limit {D.status.get('dd_facility_limit', 'missing')}) as at {_asof(D)}; "
                        f"the {len(lines)} line(s) above are read from the proposal's ask."))
    F = _F(D)
    if F is not None and F.structure["key"] != "ask" and change_lines(D, F.structure.get("changes")):
        blocks.append(P(f"Selected structure **{F.structure['label']}** changes the engine's priced line: " + "; ".join(change_lines(D, F.structure.get("changes")))
                        + f" (per the engine, {_asof(D)})."))
    fee = D.get("study_fee")
    blocks.append(P(f"Study and documentation fee: {D.money(fee, 2)} payable on approval, as at {_asof(D)}." if fee is not None
                    else f"Study and documentation fee: not provided in the request of {d(D.get('received_date')) or _asof(D)}."))
    return blocks, []


# ------------------------------------------------------------------------------------------------ CreditProbe: findings register

def w_findings(D: Deal) -> Out:
    F = _F(D)
    fd = (F.findings if F else None) or {}
    fs = fd.get("findings") or []
    if not fs:
        return [P(f"Findings register not available: the findings engine returned no findings for this deal as at {_asof(D)} (not available).")], ["findings"]
    c = fd.get("counts") or {}
    chips = " · ".join(f"{x['label']} {x['count']}" for x in fd.get("chips") or [] if x.get("key") != "all")
    blocks = [P(f"{c.get('line') or str(len(fs)) + ' findings'} as at {_asof(D)}, per the engine (one count source with the memo chips): {chips}."),
              P(f"Claims check of the RM's memo: {c.get('checks_line') or 'not available'} ({_asof(D)}, per the engine).")]
    sev = {"critical": 0, "major": 1, "minor": 2, "info": 3}
    rows = []
    for f in sorted(fs, key=lambda f: (sev.get(str(f.get("severity")), 4), str(f.get("category")), str(f.get("id")))):
        t = str(f.get("title") or "")
        cure = (f.get("cure") or {}).get("text") if isinstance(f.get("cure"), dict) else f.get("cure")
        rows.append([("__" + t + "__") if f.get("severity") == "critical" else t, f.get("category_label") or f.get("category"), f.get("severity"),
                     str(f.get("source_relation") or f.get("source") or "–"), str(cure or "–") if f.get("curable", True) else "Not curable by structure"])
    blocks.append(T(["Finding (result)", "Category", "Severity", "Evidence", "Cure"], rows, source="session e findings engine (dd_review_finding, live rules, capacity, covenants)",
                    widths=[6.4, 2.2, 1.5, 3.4, 4.5], size=6.9))
    br = F.bridge if F else None
    if br and br.get("steps"):
        blocks.append(H("RAROC bridge: deal → relationship → with deposits"))
        blocks.append(T(["Step", "RAROC", "Change (pp)", "PV (SAR m)", "What"], [[s_.get("step"), _pct(s_.get("raroc")), "–" if s_.get("delta_pp") is None else f"{s_['delta_pp']:+.1f}",
                                                                                  D.m(s_.get("pv_sar_mn"), 2), s_.get("what")] for s_ in br["steps"]],
                        source=str(br.get("source") or "economics engine"), widths=[4.0, 1.5, 1.6, 1.6, 9.3], size=7.0))
        blocks.append(P(f"{br.get('headline')} on the {br.get('basis', 'lifetime')} basis, per the engine ({_asof(D)})."))
    cap = (F.capacity if F else None) or {}
    if cap.get("inputs"):
        blocks.append(H(f"Capacity inputs ({cap.get('method_label') or cap.get('method')})"))
        blocks.append(T(["Input", "Value", "Unit", "Source"], [[i.get("name"), D.m(i.get("value")) if isinstance(i.get("value"), (int, float)) else i.get("value"), i.get("unit") or "",
                                                               (i.get("source") or {}).get("relation") if isinstance(i.get("source"), dict) else str(i.get("source") or "")]
                                                              for i in cap["inputs"][:12]], source="session e capacity engine", widths=[7.0, 2.0, 2.0, 6.0], size=7.0))
    return blocks, []


def _attributed(line: str) -> str:
    """R14 x (merge of m into p): session m's regime lines are written for screens; in the bank form every sentence needs
    a figure with a date or an attribution (voice rules V1, V2). A sentence without one gets "(as per CreditProbe's
    current-regime block)"; the markdown bold of the screen text is dropped."""
    from backend.dealdesk.house_style.bankform import voice as V
    out = []
    for sent in V.sentences(line.replace("**", "")):
        sent = sent.rstrip(".")
        if any(p.startswith(("V1", "V2")) for p in V.sentence_problems(sent + ".", "credit")):
            sent += " (as per CreditProbe's current-regime block)"
        out.append(sent + ".")
    return " ".join(out)
