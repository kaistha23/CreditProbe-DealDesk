"""P2: section-by-section drafting in the house style.

For each section of the house structure (the profile's section order for this bank and memo type) the drafter takes:
  - the profile (openers, standard phrases, number format, voice, sentence length, what the RM edited before);
  - the 2-3 nearest exemplar sections (`retrieve`), for wording only;
  - the section's facts (`facts`): the only source of any figure or name.

Model path: the app's model key (`backend.convo.provider`: CONVO_/COCKPIT_/WHATIF_ANTHROPIC_API_KEY, never printed), one
forced tool call per section; the output is accepted only if every figure in it is one of the section's facts and every
sentence with a figure cites a fact ([F3]). Otherwise, or with no key (the cloud), the deterministic template path:
candidate phrasings filled from the facts, the one closest to the house profile and the exemplars chosen.

Judgement sections (risks and mitigants, recommendation) are drafted as clearly marked suggestions for the RM.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from backend.dealdesk.house_style import facts as factsmod
from backend.dealdesk.house_style import profile as prof
from backend.dealdesk.house_style import stylo

JUDGEMENT = {"risks", "recommendation"}
DEFAULT_ORDER = ["request", "obligor", "facilities", "financials", "business", "conduct", "security", "risks", "recommendation"]
NUM = re.compile(r"(?<![A-Za-z\[])-?\d[\d,]*(?:\.\d+)?")
CITE = re.compile(r"\[(F\d+)\]")


# ---------------------------------------------------------------------------------------------- figure validation

YEAR_TOKEN = re.compile(r"^(19|20)\d\d$")


def _nums(text: str) -> list[float]:
    """The figures in a text, years (1900-2099 written as a plain year) excepted."""
    out = []
    for m in NUM.finditer(CITE.sub("", text or "")):
        tok = m.group(0)
        if YEAR_TOKEN.match(tok):
            continue
        try:
            out.append(round(float(tok.replace(",", "")), 4))
        except ValueError:
            continue
    return out


def _forms(f: dict[str, Any]) -> set[float]:
    """The ways one fact's figure may be written: as displayed, and its value at 0-2 decimals (x100 for a ratio)."""
    ok: set[float] = set(_nums(str(f.get("display", ""))))
    if f["kind"] == "text":
        ok.update(_nums(str(f.get("value", ""))))
    else:
        v = float(f["value"])
        for x in ((v * 100,) if f.get("unit") == "ratio" else (v,)):
            for d in (0, 1, 2):
                ok.add(round(round(x, d), 4))
    return ok


def allowed_numbers(fs: list[dict[str, Any]]) -> set[float]:
    ok: set[float] = set()
    for f in fs:
        ok |= _forms(f)
    return ok


CLAUSE = re.compile(r"(?<=[.;!?])\s+")


def check(text_parts: list[str], fs: list[dict[str, Any]]) -> list[str]:
    """Problems with drafted text: in each clause (split at '.', ';', '!' or '?'), every figure must be a figure of a fact
    cited in that clause, and every citation must be a fact of the section."""
    by = {f["id"]: f for f in fs}
    problems = []
    for part in text_parts:
        for cid in CITE.findall(part):
            if cid not in by:
                problems.append(f"citation {cid} is not a fact of this section")
        masked = part
        for f in fs:  # a text fact quoted whole (it may hold its own ';') counts as that fact
            v = str(f.get("value", "")).rstrip(".") if f["kind"] == "text" else ""
            if v and len(v) > 3 and v in masked and f"[{f['id']}]" in masked:
                masked = masked.replace(v, f"[{f['id']}]")
        for clause in CLAUSE.split(masked):
            nums = _nums(clause)
            if not nums:
                continue
            cited = [by[c] for c in CITE.findall(clause) if c in by]
            if not cited:
                problems.append(f"uncited figure in: {clause[:80]}")
                continue
            ok: set[float] = set()
            for f in cited:
                ok |= _forms(f)
            for n in nums:
                if n not in ok:
                    problems.append(f"figure {n:g} is not a figure of the fact cited with it ({', '.join(f['id'] for f in cited)})")
    return problems


# ---------------------------------------------------------------------------------------------- phrasing choice

class Chooser:
    """Picks, among candidate phrasings, the one closest to the house: profile phrases and openers, the nearest exemplar
    sections, phrases the RM preferred; minus phrases the RM removed."""

    def __init__(self, view: dict[str, Any], exemplars: list[dict[str, Any]], section: str):
        self.phr = {p["text"]: p["weight"] for p in view.get("phrases", [])}
        self.pref = {p["text"]: p["weight"] for p in view["learned"]["preferred"]}
        self.avoid = {p["text"]: p["weight"] for p in view["learned"]["avoid"]}
        sec = next((s for s in view["sections"] + view.get("credit_sections", []) if s["key"] == section), None)
        self.openers = {o["text"]: o["weight"] for o in (sec or {}).get("openers", [])}
        self.ex: dict[str, float] = {}
        for e in exemplars:
            for g in prof.phrases_of(e["text"]):
                self.ex[g] = self.ex.get(g, 0.0) + (2.0 if e.get("primary") else 1.0) * max(0.1, e.get("score", 0.5))
        self.target = (view.get("style") or {}).get("sentence_words") or 14.0

    def score(self, s: str) -> float:
        grams = prof.phrases_of(s)
        sc = sum(min(3.0, self.phr.get(g, 0.0)) for g in grams) * 0.3 + sum(self.ex.get(g, 0.0) for g in grams) * 0.5
        sc += sum(self.pref.get(g, 0.0) for g in grams) * 2.0 - sum(self.avoid.get(g, 0.0) for g in grams) * 3.0
        sc += min(4.0, self.openers.get(prof.opener_of(s), 0.0)) * 1.0
        n = len(stylo.words(s))
        sc -= abs(n - self.target) * 0.02
        return sc

    variant = 0

    def pick(self, cands: list[str]) -> str:
        """The phrasing closest to the house; a regenerate (variant n) takes the next one down, cycling."""
        cands = list(dict.fromkeys(c for c in cands if c))
        if not cands:
            return ""
        order = sorted(range(len(cands)), key=lambda i: (-round(self.score(cands[i]), 6), i))
        return cands[order[self.variant % len(order)]]


def _c(f: dict[str, Any] | None) -> str:
    return f"{f['display']} [{f['id']}]" if f else ""


def _t(f: dict[str, Any] | None) -> str:
    return f"{f['display']}" if f else ""


def _lc(s: str) -> str:
    return s[:1].lower() + s[1:] if s and not s[:2].isupper() else s


# ---------------------------------------------------------------------------------------------- section templates

Template = Callable[[factsmod.Facts, Chooser, dict[str, Any]], dict[str, Any]]


def _out(paragraphs: list[str] | None = None, bullets: list[str] | None = None, table: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"paragraphs": [p for p in (paragraphs or []) if p], "bullets": [b for b in (bullets or []) if b], "table": table}


def t_request(F: factsmod.Facts, ch: Chooser, meta: dict[str, Any]) -> dict[str, Any]:
    items = [f for f in F.section("request") if f["key"].startswith("req_")]
    if items:
        return _out(bullets=[f"{f['value']} [{f['id']}]" for f in items])
    g = F.get
    am, fa, te, bm, mg, pu = g("amount"), g("facility"), g("tenor"), g("benchmark"), g("margin") or g("commission"), g("purpose")
    price = (f"{bm['value']} + {_c(mg)}" if g("margin") else f"a commission of {_c(mg)}") if mg else ""
    s1 = ch.pick([f"{meta['name']} requests a {fa['value']} of {_c(am)} for {_c(te)}" + (f" at {price}" if price else "") + ".",
                  f"Request: {fa['value']} of {_c(am)} over {_c(te)}" + (f", priced at {price}" if price else "") + ".",
                  f"Approval is sought for a {_c(am)} {fa['value']} with a tenor of {_c(te)}" + (f" at {price}" if price else "") + "."])
    s2 = ch.pick([f"Purpose: {pu['value']} [{pu['id']}]." if pu else "", f"The facility is required for {_lc(pu['value'])} [{pu['id']}]." if pu else ""])
    rows = [[f["label"], f["display"]] for f in F.section("request") if f["key"] not in ("purpose",)]
    return _out([s1, s2], table={"header": ["Term", "Requested"], "rows": rows, "cites": [f["id"] for f in F.section("request")]})


def t_facilities(F: factsmod.Facts, ch: Chooser, meta: dict[str, Any]) -> dict[str, Any]:
    g = F.get
    paras = []
    if g("cap_existing"):
        paras.append(ch.pick([
            f"Group exposure cap: {_c(g('cap_existing'))}, proposed {_c(g('cap_proposed'))} (group exposure after this request {_c(g('group_after'))}).",
            f"The group exposure cap of {_c(g('cap_existing'))} is proposed at {_c(g('cap_proposed'))}; group exposure after this request is {_c(g('group_after'))}."]))
    if g("limits_existing_f") and g("amount_f"):
        paras.append(ch.pick([
            f"Existing limits of {_c(g('limits_existing_f'))}; the request adds {_c(g('amount_f'))}, taking total limits to {_c(g('limits_after_f'))}.",
            f"Total limits {_c(g('limits_existing_f'))} -> {_c(g('limits_after_f'))} with the new {_c(g('amount_f'))} facility."]))
    elif g("amount_f"):
        paras.append(f"New limit requested: {_c(g('amount_f'))}; no existing limits with the bank.")
    te, tp, tc = g("total_existing"), g("total_proposed"), g("total_change")
    if te and tp:
        paras.append(ch.pick([f"Total limits move from {_c(te)} to {_c(tp)}, an increase of {_c(tc)}.",
                              f"Total limits {_c(te)} -> {_c(tp)} (increase {_c(tc)})."]))
    if g("fees"):
        paras.append(f"Upfront fees: {_c(g('fees'))}.")
    from backend.dealdesk import proposal_cases as pc
    rows, cites = [], []
    c = pc.CASES.get(meta["pid"])
    if c:
        for i, f in enumerate(c["facilities"], start=1):
            fid = g(f"fac_{i}")
            cites.append(fid["id"] if fid else "")
            rows.append([f["name"], f"{f['existing']:,.1f}", f"{f['proposed']:,.1f}", str(f["bps"])])
    table = {"header": ["Facility", "Existing", "Proposed", "Pricing (bps)"], "rows": rows, "cites": [x for x in cites if x]} if rows else None
    return _out(paras, table=table)


def t_financials(F: factsmod.Facts, ch: Chooser, meta: dict[str, Any]) -> dict[str, Any]:
    g = F.get
    paras = []
    rev, eb, mar, ds, dscr = g("revenue"), g("ebitda"), g("ebitda_margin"), g("debt_service"), g("dscr")
    yr = g("fin_year")
    when = f"In {yr['value']} [{yr['id']}], " if yr else ""
    if rev and eb:
        gr = g("revenue_growth")
        paras.append(ch.pick([
            f"{when}revenue was {_c(rev)}" + (f" ({_c(gr)} on the year before)" if gr else "") + f" and EBITDA {_c(eb)}, a margin of {_c(mar)}.",
            f"Revenue {_c(rev)}, EBITDA {_c(eb)} (margin {_c(mar)})" + (f"; revenue growth {_c(gr)}" if gr else "") + ".",
            f"{when}the company generated revenue of {_c(rev)} and EBITDA of {_c(eb)} ({_c(mar)} margin)."]))
    lev, td, nd = g("leverage"), g("total_debt"), g("net_debt")
    debt = td or nd
    if debt and lev:
        paras.append(ch.pick([
            f"{debt['label']} of {_c(debt)} is {_c(lev)} EBITDA" + (f"; DSCR {_c(dscr)} on debt service of {_c(ds)}" if dscr and ds else (f"; DSCR {_c(dscr)}" if dscr else "")) + ".",
            f"{debt['label']} {_c(debt)} ({lev['label']} {_c(lev)})" + (f", debt service {_c(ds)}, DSCR {_c(dscr)}" if dscr and ds else "") + "."]))
    if g("backlog"):
        b, bp, bg, bc = g("backlog"), g("backlog_prior"), g("backlog_growth"), g("backlog_cover")
        paras.append(ch.pick([f"Backlog {_c(b)} (prior year {_c(bp)}, up {_c(bg)}), {_c(bc)} revenue.",
                              f"The backlog stands at {_c(b)} against {_c(bp)} a year earlier (up {_c(bg)}), {_c(bc)} revenue."]))
    wc, wcp = g("working_capital"), g("working_capital_prior")
    if wc and wcp:
        move = "fell" if wc["value"] < wcp["value"] else "rose"
        paras.append(ch.pick([f"Working capital {move} to {_c(wc)} from {_c(wcp)}.", f"Working capital {_c(wc)} (prior year {_c(wcp)})."]))
    extra = [f for f in F.section("financials") if f["key"] in ("noncore_property", "retentions_not_due", "parent_related_party_share",
                                                                 "current_assets", "related_party_receivable", "related_party_share_ca",
                                                                 "goodwill_internal", "receivables_over_1y", "cash_cycle", "shareholder_withdrawals")]
    if extra:
        paras.append("; ".join(f"{f['label']} {_c(f)}" for f in extra) + ".")
    nw, cr = g("net_worth"), g("current_ratio")
    if nw or cr:
        paras.append(ch.pick([", ".join(x for x in (f"Net worth {_c(nw)}" if nw else "", f"current ratio {_c(cr)}" if cr else "") if x) + ".",
                              " and ".join(x for x in (f"Net worth stands at {_c(nw)}" if nw else "", f"the current ratio at {_c(cr)}" if cr else "") if x) + "."]))
    table = None
    if meta["source"] == "case":
        rows = [[f["label"], f["display"]] for f in F.section("financials") if f["kind"] == "number"]
        table = {"header": ["Item", "Value"], "rows": rows, "cites": [f["id"] for f in F.section("financials")]}
    if meta["source"] == "proposal":
        p = factsmod.get_proposal(meta["pid"])
        years = sorted(p["financials"]["years"], key=lambda y: y["year"])
        cites = [f["id"] for f in F.section("financials")]
        table = {"header": ["Item"] + [f"{y['year']}{' P' if y.get('kind') == 'projection' else ''}" for y in years],
                 "rows": [[lab] + [f"{float(y[k]):,.1f}" if isinstance(y.get(k), (int, float)) else "–" for y in years] for lab, k in
                          (("Revenue", "revenue"), ("EBITDA", "ebitda"), ("Total debt", "total_debt"), ("Debt service", "debt_service"),
                           ("Net worth", "net_worth"))], "cites": cites, "source": "; ".join(sorted({str(y.get('source', '')) for y in years}))}
    return _out(paras, table=table)


def t_business(F: factsmod.Facts, ch: Chooser, meta: dict[str, Any]) -> dict[str, Any]:
    g = F.get
    projects = [f for f in F.section("business") if f["key"].startswith("project_")]
    bullets = [f"{f['value'].rstrip('.')} [{f['id']}]." for f in projects]
    paras = []
    shares = [f for f in F.section("business") if f["key"].startswith("backlog_share_")]
    if shares:
        paras.append("Backlog concentration: " + "; ".join(f"{f['label'].split(': ', 1)[1]} {_c(f)}" for f in shares) + ".")
    if g("other_banks"):
        fl = g("facility_letters")
        letters = (f"facility letters not obtained [{fl['id']}]" if fl and not fl["value"] else (f"facility letters obtained for {_c(fl)}" if fl else ""))
        paras.append(ch.pick([f"The group obtained {_c(g('other_banks'))} of new facilities at {_c(g('other_banks_n'))} other banks" + (f"; {letters}" if letters else "") + ".",
                              f"New facilities at other banks: {_c(g('other_banks'))} from {_c(g('other_banks_n'))} banks" + (f"; {letters}" if letters else "") + "."]))
    pu = g("purpose_b")
    if pu:
        paras.append(ch.pick([f"Purpose: {pu['value']} [{pu['id']}].", f"The facility supports {_lc(pu['value'])} [{pu['id']}]."]))
    an = g("ancillary")
    table = None
    if an:
        paras.append(ch.pick([f"Ancillary income of {_c(an)} a year ({an['derived'].replace('sum of ', '')}).",
                              f"The relationship is expected to bring ancillary income of {_c(an)} a year."]))
        anc = (factsmod.get_proposal(meta["pid"]).get("business_case") or {}).get("ancillary_income_sar_mn_pa") or {}
        table = {"header": [f"Ancillary income ({meta['currency']} m p.a.)", "Amount"],
                 "rows": [[k.replace("_", " ").capitalize(), f"{float(v):,.2f}"] for k, v in anc.items()], "cites": [an["id"]]}
    return _out(paras, bullets, table)


def t_conduct(F: factsmod.Facts, ch: Chooser, meta: dict[str, Any]) -> dict[str, Any]:
    g = F.get
    paras = []
    if g("avg_balance"):
        paras.append(ch.pick([f"Average deposit balances {_c(g('avg_balance'))}; flow fees {_c(g('flow_fees'))} a year; account turnover {_c(g('turnover'))} of revenue.",
                              f"The account holds average balances of {_c(g('avg_balance'))}, with flow fees of {_c(g('flow_fees'))} a year and turnover of {_c(g('turnover'))} of revenue."]))
    if g("routing_required"):
        paras.append(f"Routing undertaking {_c(g('routing_required'))} the limit; achieved {_c(g('routing_achieved'))}.")
    if g("returned_cheques"):
        f = g("returned_cheques")
        paras.append(f"Bureau: {f['value']} [{f['id']}].")
    if g("facilities_n"):
        ut = g("utilisation")
        u1 = f" ({_c(ut)} utilisation)" if ut else ""
        u2 = f" (utilisation {_c(ut)})" if ut else ""
        paras.append(ch.pick([f"The obligor has {_c(g('facilities_n'))} existing facilities with limits of {_c(g('facilities_limit'))}, drawn {_c(g('facilities_drawn'))}"
                              f"{u1}; {g('stage')['value']} [{g('stage')['id']}].",
                              f"Existing facilities: {_c(g('facilities_n'))}, limits {_c(g('facilities_limit'))}, drawn {_c(g('facilities_drawn'))}{u2}; "
                              f"{g('stage')['value']} [{g('stage')['id']}]."]))
    if g("bureau"):
        paras.append(f"SIMAH: {g('bureau')['value']} [{g('bureau')['id']}].")
    return _out(paras)


def t_obligor(F: factsmod.Facts, ch: Chooser, meta: dict[str, Any]) -> dict[str, Any]:
    g = F.get
    paras = []
    if g("profile"):
        bits = [f"Sector {g('sector')['value']}" if g("sector") else "", f"internal rating {g('rating')['value']}" if g("rating") else "",
                g("tier")["value"] if g("tier") else ""]
        paras.append(f"{g('name')['value']} [{g('name')['id']}]: {_lc(g('profile')['value'])} [{g('profile')['id']}]. "
                     + "; ".join(b for b in bits if b) + (f" [{g('rating')['id']}]." if g("rating") else "."))
    else:
        nm, se, rg, ra, gr, ex = (g(k) for k in ("name", "sector", "region", "rating", "group", "existing"))
        where = ", ".join(x["value"] for x in (se, rg) if x)
        rated = f", rated {ra['value']} internally" if ra else ""
        paras.append(ch.pick([
            f"{nm['value']}" + (f" ({where})" if where else "") + f" is {ex['value']}{rated}" + (f" and part of {gr['value']}" if gr else "") + f" [{nm['id']}].",
            f"Obligor: {nm['value']}" + (f"; sector {se['value']}" if se else "") + (f"; internal rating {ra['value']}" if ra else "")
            + (f"; group {gr['value']}" if gr else "") + f" [{nm['id']}]."]))
        if g("cr"):
            paras.append(f"CR number {g('cr')['value']} [{g('cr')['id']}]." + (f" Existing exposure {_c(g('existing_exposure'))}." if g("existing_exposure") else ""))
    rows = [[f["label"], f["display"]] for f in F.section("obligor")]
    return _out(paras, table={"header": ["Field", "Value"], "rows": rows, "cites": [f["id"] for f in F.section("obligor")]} if meta["source"] == "proposal" else None)


def t_security(F: factsmod.Facts, ch: Chooser, meta: dict[str, Any]) -> dict[str, Any]:
    g = F.get
    paras = []
    ct, cv, ltv = g("collateral_type"), g("collateral_value"), g("ltv")
    if ct and cv and ltv:
        paras.append(ch.pick([f"Collateral: {ct['value']} [{ct['id']}], valued at {_c(cv)} (LTV {_c(ltv)}).",
                              f"The facility is secured by {ct['value']} [{ct['id']}] with a value of {_c(cv)}, an LTV of {_c(ltv)}."]))
    elif ct and cv:
        paras.append(f"Collateral: {ct['value']} [{ct['id']}], valued at {_c(cv)}.")
    elif ct:
        paras.append(f"Collateral: {ct['value']} [{ct['id']}].")
    for sfx in ("", "_2", "_3"):
        gu, gc = g(f"guarantee{sfx}"), g(f"guarantee_cover{sfx}")
        if gu:
            paras.append(f"Guarantee: {gu['value']} [{gu['id']}]" + (f", cover {_c(gc)}" if gc else "") + ".")
    if g("covenant_package"):
        cov = [f for f in F.section("security") if f["key"].startswith("cov_")]
        paras.append(f"Covenant package: {g('covenant_package')['value']} [{g('covenant_package')['id']}].")
        if cov:
            paras.append("Covenants: " + "; ".join(f"{f['label']} {_c(f)}" for f in cov) + ".")
    table = None
    if meta["source"] == "proposal":
        sec = factsmod.get_proposal(meta["pid"]).get("security", {})
        rows = [[c.get("collateral_id", ""), str(c.get("type", "")).replace("_", " "), f"{float(c.get('value') or 0):,.1f}", c.get("currency") or "SAR",
                 c.get("valuation_date", ""), "Yes" if c.get("pledged_in_ask", True) else "No"] for c in sec.get("collateral", [])]
        if rows:
            table = {"header": ["ID", "Type", "Value", "Currency", "Valuation date", "Offered"], "rows": rows,
                     "cites": [f["id"] for f in F.section("security") if f["key"] in ("collateral_type", "collateral_value")]}
    return _out(paras, table=table)


def t_risks(F: factsmod.Facts, ch: Chooser, meta: dict[str, Any]) -> dict[str, Any]:
    g = F.get
    paras = []
    if g("peak_deficit"):
        paras.append(ch.pick([f"Stressed cash flow: peak deficit {_c(g('peak_deficit'))} in month {_c(g('peak_month'))}; funded lines {_c(g('funded_lines'))}.",
                              f"Under stress the cash flow shows a peak deficit of {_c(g('peak_deficit'))} in month {_c(g('peak_month'))} against funded lines of {_c(g('funded_lines'))}."]))
    sig = [f for f in F.section("risks") if f["key"].endswith("_r") and f["kind"] == "number"]
    if sig:
        paras.append("Points for the RM to assess: " + "; ".join(f"{f['label']} {_c(f)}" for f in sig) + ".")
    paras.append(ch.pick(["Mitigants to be set out by the RM against each risk.", "The RM to state the mitigant for each risk and the conditions that address it."]))
    return _out(paras)


def t_recommendation(F: factsmod.Facts, ch: Chooser, meta: dict[str, Any]) -> dict[str, Any]:
    g = F.get
    paras = []
    if g("rec"):
        paras.append(ch.pick([f"Relationship recommendation: {g('rec')['value']} [{g('rec')['id']}].",
                              f"The relationship recommends: {_lc(g('rec')['value'])} [{g('rec')['id']}]."]))
        paras.append(f"Approval is sought for total limits of {_c(g('total_proposed_r'))}; obligor rated {g('rating_r')['value']} [{g('rating_r')['id']}].")
    else:
        rm, pu, am = g("rm"), g("purpose_r"), g("amount_r")
        who = rm["value"] if rm and rm["value"] else "The relationship manager"
        paras.append(ch.pick([f"{who} recommends the facility as requested: {_lc(pu['value'])} [{pu['id']}]." if pu else "",
                              f"{who} recommends approval of {_c(am)} for {_lc(pu['value'])} [{pu['id']}]." if pu else ""]))
        if g("raroc") and g("hurdle"):
            ok = g("raroc")["value"] >= g("hurdle")["value"]
            paras.append(f"Lifetime RAROC {_c(g('raroc'))} {'clears' if ok else 'is below'} the {_c(g('hurdle'))} hurdle"
                         + (f"; approval at {g('approval')['value']} [{g('approval')['id']}]" if g("approval") else "") + ".")
    return _out(paras)


def t_summary(F: factsmod.Facts, ch: Chooser, meta: dict[str, Any]) -> dict[str, Any]:
    g = F.get
    paras = []
    nm, ra = g("name"), g("rating")
    if not nm:
        return _out([])
    rated = f", rated {ra['value']} [{ra['id']}]," if ra else ""
    te, tp = g("total_existing"), g("total_proposed")
    if te and tp:
        paras.append(ch.pick([
            f"{nm['value']} [{nm['id']}]{rated} requests total limits of {_c(tp)} against {_c(te)} today.",
            f"The proposal takes total limits for {nm['value']} [{nm['id']}] from {_c(te)} to {_c(tp)}."]))
    elif g("amount"):
        fa, am, te2 = g("facility"), g("amount"), g("tenor")
        paras.append(ch.pick([
            f"{nm['value']} [{nm['id']}]{rated} requests a {fa['value']} of {_c(am)} for {_c(te2)}.",
            f"The proposal is for a {_c(am)} {fa['value']} over {_c(te2)} to {nm['value']} [{nm['id']}]."]))
    if g("rec"):
        paras.append(f"Relationship recommendation: {g('rec')['value']} [{g('rec')['id']}].")
    return _out(paras)


def t_conditions(F: factsmod.Facts, ch: Chooser, meta: dict[str, Any]) -> dict[str, Any]:
    g = F.get
    cov = [f for f in F.items if f["key"].startswith("cov_")]
    bullets = [f"{f['label']} {_c(f)}" for f in cov]
    if g("routing_required"):
        bullets.append(f"Routing undertaking of {_c(g('routing_required'))} the limit")
    if g("covenant_package"):
        bullets.insert(0, f"Covenant package: {g('covenant_package')['value']} [{g('covenant_package')['id']}]")
    paras = [] if bullets else ["Conditions precedent and covenants to be set by the RM."]
    return _out(paras, bullets)


TEMPLATES: dict[str, Template] = {"summary": t_summary, "conditions": t_conditions, "request": t_request, "facilities": t_facilities, "financials": t_financials, "business": t_business,
                                  "conduct": t_conduct, "obligor": t_obligor, "security": t_security, "risks": t_risks,
                                  "recommendation": t_recommendation}


# ---------------------------------------------------------------------------------------------- model path

TOOL = {"name": "write_section", "description": "Write one section of the credit proposal in the house style.",
        "input_schema": {"type": "object", "properties": {
            "paragraphs": {"type": "array", "items": {"type": "string"}, "description": "Prose paragraphs; cite every figure as [F<n>]."},
            "bullets": {"type": "array", "items": {"type": "string"}, "description": "Bullet points, if the house writes this section as bullets."}},
            "required": ["paragraphs"]}}


def _system(view: dict[str, Any]) -> str:
    st = view.get("style") or {}
    n = view["numbers"]
    return ("You draft one section of a bank credit proposal in the bank's house style. Match the house's language, tone and "
            "intention: its openers, standard phrases, sentence length (about "
            f"{st.get('sentence_words') or 14} words), certainty (plain statements, few hedges), voice (business unit, no first person) "
            f"and number format (currency first, unit '{n['unit']}', e.g. AED 212.4m; percentages with '{n['percent']}'; multiples with 'x'). "
            "FACTS: use only the facts given, never a figure or name from the exemplars; cite every figure with its fact id in square "
            "brackets, e.g. 'Revenue AED 2,050m [F12]'. Exemplars show wording only. Do not invent mitigants or conclusions in a "
            "factual section; in a judgement section, write a suggestion the RM can accept or change. Follow every analyst_rules "
            "line (the writer's, their team's and the bank's saved rules) unless it would change a figure.")


def _model(section: dict[str, Any], fs: list[dict[str, Any]], view: dict[str, Any], exemplars: list[dict[str, Any]],
           judgement: bool) -> tuple[dict[str, Any] | None, str]:
    try:
        from backend.convo import provider as prov
    except Exception:  # noqa: BLE001
        return None, "no provider"
    p = prov.default()
    if p is None:
        return None, "no model key"
    sec = next((s for s in view["sections"] if s["key"] == section["key"]), {})
    user = json.dumps({
        "section": {"key": section["key"], "heading": section["heading"], "judgement": judgement,
                    "house_openers": [o["text"] for o in sec.get("openers", [])[:5]], "bullets": sec.get("bullet_share", 0) > 0.5},
        "house_phrases": [x["text"] for x in view.get("phrases", [])[:20]],
        "avoid": [x["text"] for x in view["learned"]["avoid"][:10]],
        "analyst_rules": __import__("backend.dealdesk.rules.hook", fromlist=["x"]).model_rules(section["key"]),  # Round K
        "facts": [{"id": f["id"], "label": f["label"], "value": f["display"], "source": f["source"]} for f in fs],
        "exemplars_wording_only": [{"heading": e["heading"], "text": e["text"][:700]} for e in exemplars],
        "house_sentences_with_these_facts": [t for t, _ in induced([x for e in exemplars for line in e["text"].splitlines()
                                                                     for x in (stylo.sentences(line) or [line])], fs)][:6]},
        ensure_ascii=False)
    try:
        reply = p.step("dealdesk_house_style_draft", _system(view), [{"role": "user", "content": user}], [TOOL])
    except Exception as e:  # noqa: BLE001 - provider failure: the template path drafts the section
        return None, f"model unavailable ({type(e).__name__})"
    use = next((u for u in reply.tool_uses() if u.get("name") == "write_section"), None)
    if not use:
        return None, "model gave no section"
    out = _out([str(x) for x in use["input"].get("paragraphs") or []], [str(x) for x in use["input"].get("bullets") or []])
    problems = check(out["paragraphs"] + out["bullets"], fs)
    if problems:
        return None, "model output rejected: " + problems[0]
    return out, "model"


# ---------------------------------------------------------------------------------------------- drafting

def plan(view: dict[str, Any]) -> list[dict[str, Any]]:
    """The sections to draft: the house's business-unit structure, in its order, that a template can fill."""
    out = [{"key": s["key"], "heading": s["heading"], "voice": s["voice"]} for s in view["sections"] if s["key"] in TEMPLATES]
    keys = {s["key"] for s in out}
    if "recommendation" not in keys:
        out.append({"key": "recommendation", "heading": "Recommendation", "voice": "business"})
    return out


def section_query(sec: dict[str, Any], fs: list[dict[str, Any]], meta: dict[str, Any]) -> str:
    return " ".join([sec["heading"], meta.get("sector", ""), meta["segment"]] + [f"{f['label']} {f['display']}" for f in fs])


# ---------------------------------------------------------------------------------------------- house sentences, re-filled

SYN = {"turnover": "revenue", "sales": "revenue", "topline": "revenue", "borrowings": "debt", "leverage": "debt", "order": "backlog",
       "orderbook": "backlog", "cover": "dscr", "coverage": "dscr", "limits": "limit", "deposits": "deposit", "balances": "balance"}
_YEAR = re.compile(r"^(?:FY\s?)?(?:19|20)\d\d$")
#: words that judge or give a direction: a house sentence carrying one would assert it about this memo's figures
NUMBER_WORDS = re.compile(r"\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twice|half|double|triple|single|"
                          r"first|second|third|several|few|many|dozen|hundred|thousand)\b", re.I)
EVALUATIVE = re.compile(r"\b(comfortabl\w*|satisfactor\w*|strong\w*|healthy|robust|adequate\w*|sound|weak\w*|good|poor|adverse|"
                        r"improv\w*|deteriorat\w*|increas\w*|decreas\w*|declin\w*|ros[e]|risen|fell|fallen|grew|grown|growth|drop\w*|"
                        r"high\w*|low\w*|significant\w*|substantial\w*|modest\w*|limited|excellent|concern\w*|stable|stabl\w*|"
                        r"despite|although|however|only|over|under|exceed\w*|below|above|up|down)\b", re.I)
_SPAN = re.compile(r"(?:FY\s?)?\b(?:19|20)\d\d\b|\b(?:AED|SAR|USD)\s?-?[\d,]+(?:\.\d+)?\s?(?:bn|billion|mn|million|m)?\b|-?\d[\d,]*(?:\.\d+)?\s?(?:%|per cent|x\b|times\b|bps\b)?")


def _unit_of(span: str) -> str:
    if re.match(r"(AED|SAR|USD)", span):
        return "ccy m"
    if span.rstrip().endswith(("%", "per cent")):
        return "pct"
    if span.rstrip().endswith(("x", "times")):
        return "x"
    if span.rstrip().endswith("bps"):
        return "bps"
    return "plain"


def _unit_ok(span_unit: str, fact_unit: str) -> bool:
    return {"ccy m": ("ccy m",), "pct": ("ratio", "%"), "x": ("x",), "bps": ("bps",), "plain": ("count", "years")}[span_unit].__contains__(fact_unit)


#: words that name a financial measure: every one around a figure must be in the label of the fact that replaces it
FIN_TERMS = {"total", "net", "gross", "debt", "revenue", "ebitda", "margin", "service", "dscr", "backlog", "working", "capital", "cash",
             "equity", "worth", "assets", "liabilities", "current", "ratio", "profit", "income", "interest", "deposit", "balance", "limit",
             "existing", "proposed", "cap", "exposure", "fees", "fee", "commission", "retention", "retentions", "receivable", "receivables",
             "payable", "inventory", "operating", "tangible", "advance", "payment", "guarantee", "collateral", "value", "ltv", "tenor",
             "amount", "pricing", "flow", "routing", "deficit", "funded", "property", "goodwill", "withdrawals", "cycle", "utilisation"}


def _label_words(text: str) -> set[str]:
    return {SYN.get(w, w) for w in re.findall(r"[a-z]{3,}", text.lower())} - {"the", "and", "for", "with", "from", "was", "were", "per", "aed",
                                                                                "sar", "usd", "year", "prior"}


def induced(sentences: list[str], fs: list[dict[str, Any]]) -> list[tuple[str, set[str]]]:
    """House sentences re-filled with this memo's facts. A sentence of an exemplar section qualifies when it names no one,
    carries no judging or direction word, and every figure in it is labelled by words that name exactly one of this
    section's facts of the same kind (every metric word around the figure must be in the fact's label: 'net debt' never
    takes a total-debt figure). Each figure is replaced by that fact, cited. Sentences without a figure are never used."""
    out: list[tuple[str, set[str]]] = []
    nums = [f for f in fs if f["kind"] == "number"]
    year = next((f for f in fs if f["key"] == "fin_year"), None)
    labels = {f["id"]: _label_words(f["label"] + " " + f["key"].replace("_", " ")) for f in nums}
    metric = (set().union(*labels.values()) if labels else set()) | FIN_TERMS
    for sent in sentences:
        if "@" in prof._tok(re.sub(r"\bFY\s?\d{4}", "FY", sent)) or len(stylo.words(sent)) < 4 or EVALUATIVE.search(sent) \
                or NUMBER_WORDS.search(re.sub(r"\bFY\s?\d{4}", "", sent)):
            continue
        spans = list(_SPAN.finditer(sent))
        if not spans or sum(1 for m in spans if _YEAR.match(m.group(0).strip())) > 1:
            continue
        built, last, label_from, used, ok = [], 0, 0, set(), True
        for k, m in enumerate(spans):
            before = sent[last:m.start()]
            if _YEAR.match(m.group(0).strip()):
                if not year:
                    ok = False
                    break
                used.add(year["id"])
                built.append(re.sub(r"FY\s?$", "", before) + f"{year['value']} [{year['id']}]")
                last = m.start() + len(m.group(0).rstrip())
                continue
            nxt = sent[m.start() + len(m.group(0).rstrip()): spans[k + 1].start() if k + 1 < len(spans) else len(sent)]
            w = _label_words(" ".join(re.findall(r"[A-Za-z]+", sent[label_from:m.start()])[-6:])) & metric
            if not w:  # "1.67x EBITDA": the label follows the figure
                w = _label_words(" ".join(re.findall(r"[A-Za-z]+", nxt)[:2])) & metric
            best, best_key = None, None
            if w:
                for f in nums:
                    if f["id"] in used or not _unit_ok(_unit_of(m.group(0)), f["unit"]) or not w <= labels[f["id"]]:
                        continue
                    key = (len(w & labels[f["id"]]), -len(labels[f["id"]]))
                    if best_key is None or key > best_key:
                        best, best_key = f, key
            if not best:
                ok = False
                break
            used.add(best["id"])
            built.append(before + _c(best))
            last = label_from = m.start() + len(m.group(0).rstrip())
        if ok:
            out.append(("".join(built) + sent[last:]).strip() and (("".join(built) + sent[last:]).strip(), used))
    return [x for x in out if x]


def _house_sentences(body: dict[str, Any], exemplars: list[dict[str, Any]], fs: list[dict[str, Any]], ch: "Chooser") -> dict[str, Any]:
    """Swap a drafted paragraph for a house sentence re-filled with this memo's facts, when the house sentence reads closer to
    the house and covers the paragraph's facts. A fact the house sentence leaves out must be a computed ratio, or sit in the
    section's table; a fact it adds is this memo's own and cited."""
    sents = [x for e in exemplars for line in e["text"].splitlines() for x in (stylo.sentences(line) or [line])]
    cands = induced(sents, fs)
    if not cands:
        return body
    by = {f["id"]: f for f in fs}
    in_table = set((body.get("table") or {}).get("cites") or []) if (body.get("table") or {}).get("rows") else set()
    paras = list(body["paragraphs"])
    taken: set[str] = set()
    for i, p in enumerate(paras):
        ids = set(CITE.findall(p))
        if not ids:
            continue
        best, best_sc = None, ch.score(p)
        for text, used in cands:
            if text in taken or not (used & ids):
                continue
            if any(not by.get(x, {}).get("derived") and x not in in_table for x in ids - used):
                continue
            sc = ch.score(text) + 0.5
            if sc > best_sc and not check([text], fs):
                best, best_sc = text, sc
        if best:
            paras[i] = best[:1].upper() + best[1:]
            taken.add(best)
    return {**body, "paragraphs": paras}


def _abbreviate(body: dict[str, Any], view: dict[str, Any]) -> dict[str, Any]:
    """The house's abbreviations: a spelled-out form the house abbreviates is written as the house writes it (CRO, AECB, EOT ...)."""
    used = {a["text"] for a in view.get("abbreviations", [])}
    house = " ".join(p["text"] for p in view.get("phrases", []))
    subs = [(full, abbr) for abbr, full in stylo.GLOSSARY.items() if abbr in used and full.lower() not in house]
    if not subs:
        return body

    def fix(t: str) -> str:
        for full, abbr in subs:
            t = re.sub(re.escape(full), abbr, t, flags=re.I)
        return t
    return {**body, "paragraphs": [fix(p) for p in body["paragraphs"]], "bullets": [fix(b) for b in body["bullets"]]}


def _fit(body: dict[str, Any], view: dict[str, Any], key: str, ch: Chooser, judgement: bool) -> list[str]:
    """As much prose as the house writes in this section: the house's paragraphs per memo (none beside a table when the
    house writes the section as a table), keeping the paragraphs closest to the house, in their order."""
    hs = next((s for s in view["sections"] if s["key"] == key), None)
    paras = body["paragraphs"]
    if not hs or judgement:
        return paras
    n = int(round(hs.get("paragraphs_per_memo", len(paras)) + 0.01))
    if n == 0 and not body.get("table") and not body.get("bullets"):
        n = 1
    if len(paras) <= n:
        return paras
    keep = sorted(sorted(range(len(paras)), key=lambda i: -ch.score(paras[i]))[:n])
    return [paras[i] for i in keep]


#: sections that draw on other sections' facts (a summary restates them; conditions come from security and conduct)
FACT_SOURCES = {"summary": None, "conditions": ("conditions", "security", "conduct")}


def facts_for(items: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    src = FACT_SOURCES.get(key, (key,))
    return [f for f in items if src is None or f["section"] in src]


def section_facts(F: factsmod.Facts, key: str) -> list[dict[str, Any]]:
    return facts_for(F.items, key)


def draft_section(sec: dict[str, Any], F: factsmod.Facts, view: dict[str, Any], index: Any, meta: dict[str, Any],
                  use_model: bool = True, exclude: set[str] | None = None, variant: int = 0) -> dict[str, Any]:
    fs = section_facts(F, sec["key"])
    ex = index.nearest(sec["key"], section_query(sec, fs, meta), meta["bank"], meta["kind"], meta["segment"], 3, exclude) if index else []
    judgement = sec["key"] in JUDGEMENT
    body, method = (None, "template")
    if use_model:
        body, why = _model(sec, fs, view, ex, judgement)
        method = "model" if body else f"template ({why})"
    if body is None:
        ch = Chooser(view, ex, sec["key"])
        ch.variant = variant  # a regenerate takes the next-best phrasing
        body = TEMPLATES[sec["key"]](F, ch, meta)
        body["paragraphs"] = [p[:1].upper() + p[1:] for p in body["paragraphs"]]
        body = _house_sentences(body, ex, fs, ch)
        body = _abbreviate(body, view)
        body["paragraphs"] = _fit(body, view, sec["key"], ch, judgement)
        problems = check(body["paragraphs"] + body["bullets"], fs)
        if problems:  # never ship an unsupported figure: drop the offending sentences
            body["paragraphs"] = [p for p in body["paragraphs"] if not check([p], fs)]
            body["bullets"] = [b for b in body["bullets"] if not check([b], fs)]
    cited = set(CITE.findall(" ".join(body["paragraphs"] + body["bullets"]))) | set((body.get("table") or {}).get("cites", []))
    return {"key": sec["key"], "heading": sec["heading"], "voice": sec.get("voice", "business"), "judgement": judgement,
            "paragraphs": body["paragraphs"], "bullets": body["bullets"], "table": body.get("table"),
            "citations": [f for f in F.items if f["id"] in cited], "exemplars": [{k: e[k] for k in ("doc_id", "heading", "similarity", "primary")} for e in ex],
            "method": method, "status": "draft", "edited": False, "version": 1}


def draft(pid: str, state: dict[str, Any], index: Any, use_model: bool = True, exclude: set[str] | None = None,
          sections: list[str] | None = None, with_engine: bool = True, bank: str | None = None) -> dict[str, Any]:
    meta = factsmod.memo_meta(pid)
    meta["bank"] = bank or prof.house_for(state, meta["bank"], meta["segment"])
    view = prof.view(state, meta["bank"], meta["kind"], meta["segment"])
    F = factsmod.gather(pid, prof.money_style(view), with_engine=with_engine)
    exclude = set(exclude or set()) | {pid, f"{pid}-OPINION"}  # a memo is never its own exemplar
    planned = plan(view)
    if sections and not any(s["key"] in sections for s in planned):
        raise ValueError(f"None of {', '.join(sections)} is a section of this house's proposals ({', '.join(s['key'] for s in planned)}).")
    secs = [draft_section(s, F, view, index, meta, use_model, exclude) for s in planned if not sections or s["key"] in sections]
    from backend.dealdesk.house_style import fidelity
    d = {"draft_id": f"DR-{uuid.uuid4().hex[:10]}", "proposal_id": pid, "title": meta["title"], "meta": meta,
         "created": datetime.now(timezone.utc).isoformat(timespec="seconds"), "profile_group": view["group"],
         "profile": {"group": view["group"], "bank_label": view["bank_label"], "documents": view["documents"],
                     "primary_exemplars": view["primary_exemplars"], "edits_learned": view["edits_learned"]},
         "sections": secs, "facts": F.items, "style": prof.money_style(view)}
    d["methods"] = sorted({s["method"].split(" (")[0] for s in secs})
    d.update(fidelity.assess(d, view, state))
    return d


def section_text(s: dict[str, Any]) -> str:
    return "\n".join(s.get("paragraphs", []) + [f"- {b}" for b in s.get("bullets", [])])


def as_doc(d: dict[str, Any]) -> dict[str, Any]:
    """A draft in the corpus document shape (for scoring and for learning)."""
    m = d["meta"]
    return {"doc_id": d["draft_id"], "title": d["title"], "source": "draft", "bank": m["bank"], "kind": m["kind"], "segment": m["segment"],
            "weight": 1.0, "primary": False,
            "sections": [{"key": s["key"], "heading": s["heading"], "voice": s.get("voice", "business"), "numbered": True,
                          "paragraphs": [CITE.sub("", p).replace("  ", " ").strip() for p in s["paragraphs"]],
                          "bullets": [CITE.sub("", b).strip() for b in s["bullets"]],
                          "tables": [{"header": s["table"]["header"], "rows": len(s["table"]["rows"])}] if s.get("table") else []}
                         for s in d["sections"]]}
