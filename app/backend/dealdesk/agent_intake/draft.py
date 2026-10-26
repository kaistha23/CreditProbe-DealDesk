"""Round A, step 3: draft the business request (the RM's credit application to Credit), SIB format, at most 650 words.

    prompt(ctx)              the drafting prompt (the Credit Request Agent's draftPromptText, with R16's bank-form sections)
    deterministic(ctx)       the same request written by rules from the read documents (no model key; the tests)
    check_figures(md, ev)    every figure in the draft must be in the evidence it cites ([D3] a document, [RM] the RM notes,
                             [Ask] the ask); a figure that is not is removed from the paper and listed (R16's figure rule:
                             the model writes, never computes)
    evidence(ctx)            the numbers each source holds

`ctx`: {customer, cr, market, currency, bureau, request_type, existing, rm, as_of, ask, notes, docs: [{id, name, pages, result}],
        check (checklist.run)}.
"""
from __future__ import annotations

import re
from typing import Any

from backend.dealdesk.agent_intake import checklist as CK
from backend.dealdesk.agent_intake.read import numbers

MAX_WORDS = 650
SECTIONS = ["Action requested", "Facilities", "Security and terms", "Group exposure, relationship and conduct", "Background",
            "Financials", "Risks and mitigants (RM's justification)", "Documents, exceptions and pending items", "Recommendation"]
CITE = re.compile(r"\[((?:D\d+|RM|Ask)(?:\s*,\s*(?:D\d+|RM|Ask))*)\]")


# ================================================================================================ the prompt
def evidence_block(ctx: dict[str, Any]) -> str:
    out = []
    for d in ctx["docs"]:
        r = d["result"]
        figs = "\n".join(f"- {f['label']}: {f['value']}" + (f" (p. {f['page']})" if f.get("page") else "") for f in r.get("key_figures") or [])
        obs = "\n".join(f"- {o}" for o in r.get("observations") or [])
        out.append(f"### {d['id']} — {r.get('doc_type')} (file: {d['name']})\nEntity: {r.get('entity') or 'n/a'} | Period/date: "
                   f"{r.get('period_or_date') or 'n/a'} | Expiry: {r.get('expiry_date') or 'n/a'}\nSummary: {r.get('summary') or ''}\n"
                   f"Figures:\n{figs}\nObservations:\n{obs}")
    return "\n\n".join(out)


def prompt(ctx: dict[str, Any]) -> str:
    ck = ctx["check"]
    cur, bureau = ctx["currency"], ctx["bureau"]
    return f"""You are an experienced corporate Relationship Manager at a {ctx['market']} bank. Write the BUSINESS REQUEST (the RM's credit application) that goes to the Credit Risk division for independent review. Think like an RM: present the deal clearly and make the case, while disclosing every weakness Credit will find anyway, with its mitigant.

INPUTS
Customer: {ctx.get('customer') or '(take the legal name from the documents)'}
Request type: {ctx['request_type']}
Relationship: {'Existing customer of the Bank' if ctx['existing'] else 'New to bank'}
RM: {ctx.get('rm') or '[RM name]'}
Date: {ctx['as_of']}
THE ASK (from the RM): {ctx['ask']}
RM NOTES (facts the documents do not show; label them "per RM" when used): {ctx.get('notes') or 'none'}

CHECKLIST RESULT
Received: {'; '.join(ck['received']) or 'none'}
Missing: {'; '.join(ck['missing']) or 'none'}
Expired: {'; '.join(ck['expired']) or 'none'}

EVIDENCE EXTRACTED FROM THE DOCUMENTS
{evidence_block(ctx)}

WRITE THE REQUEST IN MARKDOWN, in the bank's form (the business request sections). It must fit on 1-2 printed pages: at most {MAX_WORDS} words in total, tables included. Use exactly this structure:
# Business Request — <customer legal name>
A two-column table (Item | Detail), one short line per row: Customer and CR, Group, Request type, Segment, RM, Date, Customer since, Internal rating and PD (proposed vs previous, or "To be assigned by Credit"), Total proposed limits ({cur}).
## 1. Action requested
Two sentences at most: what Credit is asked to approve, and why.
## 2. Facilities
Table: Facility | Existing | Proposed | Tenor | Purpose | Pricing. Amounts in {cur} m. Add a total row.
## 3. Security and terms
At most 5 bullets: security and guarantees (with guarantor net worth if provided), conditions precedent, covenants proposed.
## 4. Group exposure, relationship and conduct
At most 6 bullets: exposure with the Bank and other lenders from {bureau} (limits vs outstanding), group exposure, deposits and share of wallet, utilisation and conduct incidents, RAROC vs hurdle, covenant breaches under the current approval with the proposed fix.
## 5. Background
At most 3 bullets: ownership and management, business and backlog, key concentrations.
## 6. Financials
Table only, {cur} m, one column per available year or period: revenue, gross margin %, EBITDA margin %, net profit, total debt, equity, debt/equity, current ratio, receivables (DSO), CFO — only figures printed in the evidence. Then at most 2 one-line bullets.
## 7. Risks and mitigants (RM's justification)
Table: Risk | Mitigant. At most 5 rows, the most material only.
## 8. Documents, exceptions and pending items
Bullets, one line each: policy exceptions, then missing or expired documents with "prior to limit loading" where they are conditions precedent.
## 9. Recommendation
Two to three sentences, ending "Recommended for approval as proposed." or the stated variation.

RULES
- Use only the evidence, the ask and the RM notes. Never invent a number, name or date, and never compute one: a figure must be printed in the evidence (a ratio or margin only where the evidence states it). Where a statement is limited by a missing or expired document, write "Not provided — <document> missing" in place of the figure, and list the document in section 8.
- Do not write an "Information gaps" section; the system adds it.
- Cite the source after each figure or fact as [D3]; use [RM] for RM notes and [Ask] for the ask.
- Crisp bank-memo language: every line one fact, no filler, no repetition across sections, active voice, no adjectives without figures. Bullets at most 20 words. Currency {cur}, millions to one decimal.
- Do not exceed {MAX_WORDS} words. Cut detail before you exceed it; Credit can read the source documents.
- Output the markdown only, with no preamble and no code fences."""


REVISE = ("Revise the business request: {ins}\nKeep the same structure, rules and citations, keep every figure as printed in the "
          "evidence (never add or compute one), and stay within 650 words. Do not write the Completeness line or the section "
          "\"What this request could not assess\": the system adds them. Output the full revised markdown only.")


def clean_md(s: str) -> str:
    s = re.sub(r"^```(?:markdown|md)?\s*", "", (s or "").strip(), flags=re.I)
    return re.sub(r"```\s*$", "", s).strip()


def words(md: str) -> int:
    t = re.sub(r"[#*|`\-]+", " ", CITE.sub("", md))
    return len(re.findall(r"\w[\w.,%/'’]*", t))


# ================================================================================================ the figure check
def _forms(n: float) -> set[float]:
    out = {round(n, 6)}
    for div in (1e3, 1e6, 1e9):
        if n >= div / 20:
            for d in (0, 1, 2):
                out.add(round(n / div, d))
    for d in (0, 1, 2):
        out.add(round(n, d))
    return out


def evidence(ctx: dict[str, Any]) -> dict[str, set[float]]:
    ev: dict[str, set[float]] = {}
    for d in ctx["docs"]:
        nums = numbers("\n".join(d.get("pages") or []))
        for f in (d["result"].get("key_figures") or []):
            nums |= numbers(f["value"])
        ev[d["id"]] = {x for n in nums for x in _forms(n)}
    ev["RM"] = {x for n in numbers(ctx.get("notes") or "") for x in _forms(n)}
    ev["Ask"] = {x for n in numbers(ctx.get("ask") or "") for x in _forms(n)}
    return ev


DATE_LIKE = re.compile(
    r"\b\d{1,2}[ \-/](?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[ \-/,]*(?:20)?\d{2}\b|"
    r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[ \-]?(?:20)?\d{2,4}\b|\b20\d\d-\d\d-\d\d\b|\b\d{1,2}/\d{1,2}/20\d\d\b|"
    r"\b(?:FY|H[12]|Q[1-4]|9M|YTD)\s?(?:20)?\d{2,4}\b|\b(?:19|20)\d\d\b|(?i:section|sections|§)\s?\d+(?:[,–-]\s?\d+)*|^\s*\d+\.\s|^#+\s*\d+\.?|"
    r"\b(?:CR|CIF|VAT|TRN|ID)\s*(?:no\.?|number)?\s*:?\s*\d{5,}\b|\bD\d+\b", re.M)
FIG = re.compile(r"(?<![\w.])\(?-?\d[\d,]*(?:\.\d+)?\)?\s?(?:%|x\b|m\b|bn\b|k\b|mn\b|million\b|billion\b)?")


def _value(tok: str) -> tuple[float, int] | None:
    s = re.sub(r"[%xmbnkilo\s]+$", "", tok.strip().strip("()").replace(",", "")).strip()
    try:
        v = abs(float(s))
    except ValueError:
        return None
    dec = len(s.split(".")[1]) if "." in s else 0
    return v, dec


def _ok(v: float, dec: int, pool: set[float]) -> bool:
    if round(v, dec) in pool or v in pool:
        return True
    return any(abs(round(p, dec) - v) < 1e-9 for p in pool if abs(p - v) < 1)


def check_figures(md: str, ev: dict[str, set[float]], small_ints: int = 10) -> tuple[str, list[dict[str, Any]]]:
    """Remove every figure the evidence it cites does not hold. Uncited figures must be in some evidence. Dates, years,
    section numbers, references and counts up to `small_ints` are not figures. The system's completeness block is exempt."""
    allpool: set[float] = set().union(*ev.values()) if ev else set()
    out_lines: list[str] = []
    rejected: list[dict[str, Any]] = []
    exempt = False
    in_table, table_cites = False, set()
    for i, line in enumerate(md.splitlines()):
        if line.startswith("**Completeness:") or re.match(r"^##\s*What this request could not assess", line):
            exempt = True
        elif exempt and re.match(r"^##\s*\d", line):
            exempt = False
        if exempt or line.startswith("# "):
            out_lines.append(line)
            continue
        cited = {c.strip() for grp in CITE.findall(line) for c in grp.split(",")}
        if line.lstrip().startswith("|"):  # a table row also answers to the sources its header cites
            if not table_cites and not in_table:
                table_cites = set(cited)
            in_table = True
            cited |= table_cites
        else:
            in_table, table_cites = False, set()
        pool = set().union(*(ev.get(c, set()) for c in cited)) if cited else allpool
        masked = DATE_LIKE.sub(lambda m: " " * len(m.group(0)), CITE.sub(lambda m: " " * len(m.group(0)), line))
        spans = []
        for m in FIG.finditer(masked):
            got = _value(m.group(0))
            if got is None:
                continue
            v, dec = got
            if (dec == 0 and v <= small_ints) or _ok(v, dec, pool):
                continue
            a, b = m.span()
            while b > a and line[b - 1] == " ":
                b -= 1
            spans.append((a, b))
            rejected.append({"line": i + 1, "figure": line[a:b].strip(), "cited": sorted(cited), "text": line.strip()[:160]})
        for a, b in reversed(spans):
            line = line[:a] + "[figure removed]" + line[b:]
        out_lines.append(line)
    return "\n".join(out_lines), rejected


# ================================================================================================ the deterministic writer
class Ev:
    """Find printed facts in the read documents (each answer names its document)."""

    def __init__(self, ctx: dict[str, Any]):
        self.ctx = ctx
        self.docs = ctx["docs"]

    def of(self, *ids: str) -> list[dict[str, Any]]:
        return [d for d in self.docs if not ids or set(d["result"].get("checklist_ids") or []) & set(ids)]

    def lines(self, d: dict[str, Any]) -> list[str]:
        return [x for p in d.get("pages") or [] for x in p.splitlines()]

    def grab(self, rx: str, *ids: str, flags: int = re.I) -> tuple[re.Match[str] | None, str]:
        for d in self.of(*ids):
            for ln in self.lines(d):
                m = re.search(rx, ln, flags)
                if m:
                    return m, d["id"]
        return None, ""

    def grab_all(self, rx: str, *ids: str, flags: int = re.I) -> list[tuple[re.Match[str], str]]:
        out = []
        for d in self.of(*ids):
            for ln in self.lines(d):
                m = re.search(rx, ln, flags)
                if m:
                    out.append((m, d["id"]))
        return out


def _mn(s: str) -> str:
    """'214,912,430' → '214.9'; '(383,130)' → '-0.4' (formatting, not computing)."""
    neg = s.strip().startswith("(") or s.strip().startswith("-")
    v = float(re.sub(r"[^\d.]", "", s) or 0) / 1e6
    return f"{'-' if neg else ''}{v:,.1f}"


def _amounts(line: str) -> list[str]:
    return re.findall(r"\(?-?\d{1,3}(?:,\d{3})+\)?", line)


def request_type(ask: str) -> str:
    a = (ask or "").lower()
    renew = "renew" in a
    more = bool(re.search(r"\b(add|new|increase|enhance)", a))
    return "Renewal with increase" if renew and more else "Renewal" if renew else "Increase" if "increase" in a else "New facility"


def _facilities(E: Ev, ctx: dict[str, Any]) -> list[list[str]]:
    rows = []
    ask = ctx["ask"]
    for m, did in E.grab_all(r"^\s*(?P<name>[A-Za-z][A-Za-z ()&/\-–]{5,}?)\s{2,}(?P<ex>[\d,]{5,}|[–-])\s{2,}(?P<req>[\d,]{5,})\s{2,}(?P<tenor>\d+ months)\s{2,}(?P<purpose>.+)$",
                             "request_letter"):
        name = re.sub(r"\s+", " ", m.group("name")).strip()
        ex = _mn(m.group("ex")) if re.search(r"\d", m.group("ex")) else "–"
        price = "To be agreed"
        if re.search(r"(?i)murabaha|stf|working capital", name):
            pm = re.search(r"(?i)(?:murabaha|stf)[^;)]*?\bat ([^;)]+)", ask)
            price = f"{pm.group(1).strip()} [Ask]" if pm else price
        elif re.search(r"(?i)guarantee|\bLG\b", name) and ex != "–":
            pm = re.search(r"(?i)\bLG\b[^;)]*?\bat ([^;)]+)", ask)
            price = f"{pm.group(1).strip()} [Ask]" if pm else price
        purpose = re.sub(r"\s{2,}", " ", m.group("purpose")).strip()[:70]
        rows.append([f"{name} [{did}]", ex, _mn(m.group("req")), m.group("tenor"), purpose, price])
    return rows


def _fin_rows(E: Ev) -> tuple[list[str], list[list[str]]]:
    audited = sorted(E.of("audited_fs"), key=lambda d: str(d["result"].get("period_or_date") or ""))
    mgmt = E.of("mgmt_accounts")[:1]
    cols: list[tuple[str, dict[str, Any], int]] = []
    for d in audited[-2:]:
        p = str(d["result"].get("period_or_date") or "")
        cols.append((p if p.startswith("FY") else d["name"][:12], d, 0))
    if len(audited) == 1:  # the prior year from the same statements' comparative column
        y = re.search(r"20\d\d", cols[0][0])
        if y:
            cols.insert(0, (f"FY{int(y.group(0)) - 1}", audited[0], 1))
    for d in mgmt:
        p = str(d["result"].get("period_or_date") or "")
        cols.append(("H1 2026" if re.search(r"(?i)30 june 2026|six months", p + " ".join(E.lines(d)[:6])) else (p or "Interim")[:14], d, 0))
    items = [("Revenue", r"^\s*Revenue(?: from contracts with customers)?\b"), ("Gross profit", r"^\s*Gross profit\b"),
             ("Net profit", r"^\s*Net profit for the (?:year|period)\b"), ("Total equity", r"^\s*Total equity\b"),
             ("Trade receivables", r"^\s*Trade receivables\b"), ("Total current assets", r"^\s*Total current assets\b"),
             ("Total current liabilities", r"^\s*Total current liabilities\b"),
             ("Cash from operations", r"^\s*Net cash (?:from|generated)[^\n]*operating activities")]
    rows = []
    for label, rx in items:
        row = [label]
        for _, d, k in cols:
            v = "–"
            for ln in E.lines(d):
                if re.search(rx, ln, re.I):
                    am = _amounts(ln)
                    if len(am) > k:
                        v = _mn(am[k])
                    break
            row.append(v)
        if any(x != "–" for x in row[1:]):
            rows.append(row)
    # stated borrowings (notes) and ratios (management KPIs), never computed here
    bor = ["Total borrowings"]
    for _, d, k in cols:
        v = "–"
        for ln in E.lines(d):
            m = re.search(r"(?i)total borrowings(?: at [^:]+)?:?\s*SAR\s*([\d,]{5,})(?:\s*\((?:\d+ \w+ )?(?:20\d\d: )?SAR\s*([\d,]{5,}))?", ln)
            if m:
                v = _mn(m.group(1) if k == 0 or not m.group(2) else m.group(2))
                break
        bor.append(v)
    if any(x != "–" for x in bor[1:]):
        rows.append(bor)
    head = ["SAR m"] + [f"{c[0]} [{c[1]['id']}]" for c in cols]
    return head, rows


def _obs(E: Ev, ids: tuple[str, ...], rx: str = "") -> tuple[str, str]:
    for d in E.of(*ids):
        for o in d["result"].get("observations") or []:
            if not rx or re.search(rx, o, re.I):
                return o, d["id"]
    return "", ""


BREACH = r"^\s*([A-Za-z /()]+?)\s*\|\s*([≤≥<>]=?\s*[^|]+?)\s*\|[^|]*\|\s*([^|]+?)\s*\|\s*BREACH"


def _cell(t: str) -> str:
    return t.replace("|", "·")


def _short(t: str, n: int = 120) -> str:
    t = re.sub(r"\s*·\s*", " ", re.sub(r"\s{2,}", " ", t)).strip(" .")
    return t if len(t) <= n else t[: n - 1].rsplit(" ", 1)[0] + "…"


def deterministic(ctx: dict[str, Any]) -> str:
    """The business request written by rules from the read documents: same sections, every figure printed in a document
    (amounts shown in millions), each cited; a fact that is not in the file says so."""
    E = Ev(ctx)
    cur = ctx["currency"]
    ck = ctx["check"]
    name = ctx.get("customer") or "the customer"
    L: list[str] = [f"# Business Request — {name}", "", "| Item | Detail |", "|---|---|"]

    def cite(did: str) -> str:
        return f" [{did}]" if did else ""
    cr = ctx.get("cr") or ""
    crd = next((d["id"] for d in E.of("cr", "trade_licence")), "") or (E.grab(re.escape(cr))[1] if cr else "")
    L.append(f"| Customer and CR | {name}{', CR ' + cr if cr else ''}{cite(crd)} |")
    g, gd = E.grab(r"Group name:\s*([^|]+?)\s*(?:\||$)")
    L.append(f"| Group | {g.group(1).strip() + cite(gd) if g else '–'} |")
    L.append(f"| Request type | {ctx['request_type']} [Ask] |")
    s, sd = E.grab(r"Segment:?\s+([A-Z][A-Za-z\-]+(?:[ ,]+[A-Za-z&\-]+){0,3})")
    L.append(f"| Segment | {s.group(1).strip(' ,') + cite(sd) if s else '–'} |")
    L.append(f"| RM | {ctx.get('rm') or '–'} |")
    L.append(f"| Date | {ctx['as_of']} |")
    cs, csd = E.grab(r"Customer since:?\s*([A-Za-z]{3,9}[- ]\d{4})")
    L.append(f"| Customer since | {cs.group(1) + cite(csd) if cs else ('New to bank' if not ctx['existing'] else '–')} |")
    pr, prd = E.grab(r"Proposed rating \(grade\):?\s*(\d+)", "internal_rating")
    pp, _ = E.grab(r"Proposed PD \(1-year\):?\s*([\d.]+%)", "internal_rating")
    vr, _ = E.grab(r"Previous rating \(grade\):?\s*(\d+)", "internal_rating")
    vp, _ = E.grab(r"Previous PD \(1-year\):?\s*([\d.]+%)", "internal_rating")
    if pr:
        L.append(f"| Internal rating and PD | Grade {pr.group(1)}{', PD ' + pp.group(1) if pp else ''} proposed"
                 f"{' (previous ' + vr.group(1) + (', ' + vp.group(1) if vp else '') + ')' if vr else ''}{cite(prd)} |")
    else:
        L.append("| Internal rating and PD | To be assigned by Credit |")
    tl = re.search(r"(?i)total limits\s*(?:of\s*)?((?:SAR|AED)\s*[\d.,]+\s*m)", ctx["ask"])
    L.append(f"| Total proposed limits ({cur}) | {tl.group(1) + ' [Ask]' if tl else 'As per section 2 [Ask]'} |")

    # 1. Action requested
    L += ["", "## 1. Action requested", f"Credit is asked to approve: {ctx['ask'].rstrip('.')} [Ask]."]
    why, wd = E.grab(r"(The new line is required for[^.]*\.)", "request_letter")
    if why:
        L[-1] += f" {why.group(1)}{cite(wd)}"

    # 2. Facilities
    rows = _facilities(E, ctx)
    L += ["", "## 2. Facilities"]
    if rows:
        L += [f"| Facility | Existing ({cur} m) | Proposed ({cur} m) | Tenor | Purpose | Pricing |", "|---|---|---|---|---|---|"]
        L += ["| " + " | ".join(r) + " |" for r in rows]
        tot, td = E.grab(r"^\s*Total\s{2,}([\d,]{5,})\s{2,}([\d,]{5,})\s*$", "request_letter")
        if tot:
            L.append(f"| Total [{td}] | {_mn(tot.group(1))} | {_mn(tot.group(2))} | | | |")
    else:
        L.append(f"As stated in the ask [Ask]. Not provided — Facility request letter (signed) missing.")

    # 3. Security and terms
    L += ["", "## 3. Security and terms"]
    sec, sd = E.grab(r"(As security for the facilities[^.]*\.)", "request_letter")
    if sec:
        L.append(f"- {_short(sec.group(1), 160)}{cite(sd)}")
    nw, nwd = E.grab(r"Declared net worth\s*\|?\s*([\d.]+)", "guarantor_networth")
    nx, _ = E.grab(r"Net worth excluding the applicant\s*\|?\s*([\d.]+)", "guarantor_networth")
    if nw:
        L.append(f"- Guarantor declared net worth {cur} {nw.group(1)}m{f', {cur} {nx.group(1)}m excluding the applicant' if nx else ''}{cite(nwd)}.")
    elif "guarantor_networth" in ck["status"] and ck["status"]["guarantor_networth"]["st"] != "ok":
        L.append("- Guarantor net worth: Not provided — Guarantor net worth statement missing.")
    cov, cvd = E.grab(r"((?:Financial )?covenants tested annually[^\n]*)", "approval_history")
    if cov:
        L.append(f"- Current covenants: {_short(re.sub(r'^Financial covenants tested annually on audited accounts:?', '', cov.group(1)), 150)}{cite(cvd)}.")
    for ln in ck["lines"]:
        if ln["status"] == "expired":
            L.append(f"- Condition precedent: renewed {ln['label']} prior to limit loading ({ln['note']}).")

    # 4. Group exposure, relationship and conduct
    L += ["", "## 4. Group exposure, relationship and conduct"]
    b4 = []
    tlim, bd = E.grab(r"Total limits\s*[|:]?\s*([\d.]+)", "simah_company", "aecb_company")
    tout, _ = E.grab(r"Total outstanding\s*[|:]?\s*([\d.]+)", "simah_company", "aecb_company")
    nfac, _ = E.grab(r"Number of credit facilities\s*[|:]?\s*(\d+)", "simah_company", "aecb_company")
    if tlim and tout:
        b4.append(f"{ctx['bureau']}: total limits {cur} {tlim.group(1)}m, outstanding {cur} {tout.group(1)}m"
                  f"{' across ' + nfac.group(1) + ' facilities' if nfac else ''}{cite(bd)}.")
    else:
        b4.append(f"Exposure with other lenders: Not provided — {ctx['bureau']} report, company missing.")
    ws, wsd = E.grab(r"(Worst status\s*in\s*last 24 months:[^\n]*)", "simah_company", "aecb_company")
    if ws:
        b4.append(_short(ws.group(1), 130) + cite(wsd) + ".")
    ge, ged = E.grab(r"(Group exposure with the Bank [^.]*\.)", "group_structure")
    if ge:
        b4.append(_short(ge.group(1)) + cite(ged))
    dep, dd = E.grab(r"Total deposits:?\s*(SAR [\d.]+m)", "relationship_profile")
    sw, _ = E.grab(r"SHARE [O0]F WALLET\s*\(12M\)\s*:?\s*(\d+%)", "relationship_profile")
    ra, _ = E.grab(r"RAR[O0]C\s*\(12M\)\s*:?\s*([\d.]+%)\D+?hurdle\s*([\d.]+%)", "relationship_profile")
    if dep or sw or ra:
        parts = [f"deposits {dep.group(1)}" if dep else "", f"share of wallet {sw.group(1)}" if sw else "",
                 f"RAROC {ra.group(1)} vs hurdle {ra.group(2)}" if ra else ""]
        b4.append("Relationship: " + ", ".join(p for p in parts if p) + cite(dd) + ".")
    ut, ud = E.grab(r"Average STF utilisation\s+(\d+%)\s*\(peak (\d+%)", "bank_statements")
    ex, _ = E.grab(r"Excess over limit\s+(\d+ occurrence[^\n]*?)\s{2,}", "bank_statements")
    rc, _ = E.grab(r"Returned cheques\s+(\d+)\s*\(", "bank_statements")
    if ut or ex or rc:
        parts = [f"utilisation average {ut.group(1)}, peak {ut.group(2)}" if ut else "", f"excess {ex.group(1).strip()}" if ex else "",
                 f"{rc.group(1)} returned cheques" if rc else ""]
        b4.append("Conduct (12 months): " + "; ".join(p for p in parts if p) + cite(ud) + ".")
    elif ck["status"].get("bank_statements", {}).get("st") != "ok":
        b4.append("Account conduct: Not provided — Bank statements, 12 months missing.")
    for m, did in E.grab_all(BREACH, "approval_history")[:2]:
        b4.append(f"Covenant breach: {m.group(1).strip()} {m.group(3).strip()} vs {m.group(2).strip()}{cite(did)}; proposed fix per RM [RM]."
                  if re.search(r"(?i)waiver|reset|covenant", ctx.get("notes") or "") else
                  f"Covenant breach: {m.group(1).strip()} {m.group(3).strip()} vs {m.group(2).strip()}{cite(did)}; waiver or reset to be proposed.")
    L += [f"- {x}" for x in b4[:6]]

    # 5. Background
    L += ["", "## 5. Background"]
    b5 = []
    own, od = E.grab(r"held by ([^.]*\(\d+%\)[^.]*)\.", "audited_fs")
    if own:
        b5.append(f"Owned by {_short(own.group(1), 130)}{cite(od)}.")
    bl, bld = E.grab(r"^\s*Total\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*$", "project_list")
    if bl:
        b5.append(f"Contract value {cur} {bl.group(1)}m; certified {cur} {bl.group(2)}m; backlog {cur} {bl.group(3)}m{cite(bld)}.")
    elif ck["status"].get("project_list", {}).get("st") not in (None, "ok"):
        b5.append("Backlog: Not provided — Project list / backlog missing.")
    cc, ccd = E.grab(r"([A-Z][\w ]+ share of backlog:[^\n]+)", "project_list")
    if cc:
        b5.append(_short(cc.group(1)) + cite(ccd) + ".")
    else:
        t3, t3d = E.grab(r"(Top three customers[^\n]*)", "ageing")
        if t3:
            b5.append(_short(t3.group(1)) + cite(t3d) + ".")
    L += [f"- {x}" for x in b5[:3]] or ["- Not provided — background documents missing."]

    # 6. Financials
    L += ["", "## 6. Financials"]
    head, frows = _fin_rows(E)
    if frows and len(head) > 1:
        L += ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
        L += ["| " + " | ".join(r) + " |" for r in frows]
        o1, o1d = _obs(E, ("audited_fs",), r"emphasis|overdue|arbitration")
        o2, o2d = _obs(E, ("mgmt_accounts",), r"delay|borrowings|overdue")
        L += [f"- {_short(o, 140)}{cite(d)}." for o, d in ((o1, o1d), (o2, o2d)) if o]
    else:
        L.append("Not provided — Audited financials, 2 years missing.")

    # 7. Risks and mitigants
    L += ["", "## 7. Risks and mitigants (RM's justification)", "| Risk | Mitigant |", "|---|---|"]
    notes = [x.strip() for x in re.split(r"(?<=[.;])\s+", ctx.get("notes") or "") if x.strip()]
    risks: list[tuple[str, str]] = []
    for m, did in E.grab_all(BREACH, "approval_history")[:2]:
        risks.append((f"{m.group(1).strip()} covenant breached: {m.group(3).strip()} vs {m.group(2).strip()}", did))
    for ids, rx in ((("audited_fs",), r"emphasis|overdue|arbitration"), (("bank_statements",), r"excess|returned"),
                    (("project_list", "ageing"), r"concentration|share of backlog|top three|largest"),
                    (("site_visit",), r"red flag|watch|not yet supported|uncertain"), (("mgmt_accounts",), r"delay")):
        o, d = _obs(E, ids, rx)
        if o and all(o != r[0] for r in risks):
            risks.append((o, d))
    for o, d in risks[:5]:
        kw = set(re.findall(r"[a-z]{5,}", o.lower())) - {"which", "their", "under", "total", "about", "months", "there"}
        mit = next((n for n in notes if kw & set(re.findall(r"[a-z]{5,}", n.lower()))), "")
        L.append(f"| {_cell(_short(o, 110))}{cite(d)} | {(_cell(_short(mit, 110)) + ' [RM]') if mit else 'RM to address with Credit'} |")
    if not risks:
        L.append("| Not assessed: no observations read from the documents | – |")

    # 8. Documents, exceptions and pending items
    L += ["", "## 8. Documents, exceptions and pending items"]
    for m, did in E.grab_all(BREACH, "approval_history")[:3]:
        L.append(f"- Policy exception: {m.group(1).strip()} covenant {m.group(3).strip()} vs {m.group(2).strip()}{cite(did)}.")
    for ln in ck["lines"]:
        if ln["status"] == "expired":
            L.append(f"- {ln['label']} expired ({ln['note']}): renewed copy prior to limit loading.")
    crit = []
    for gp in ck["comp"]["gaps"]:
        if CK.critical(gp):
            crit += [b for b in gp["blocking"] if b not in crit]
    for b in crit:
        L.append(f"- {b}: not provided — prior to limit loading.")
    rest = [x for x in ck["missing"] if x not in crit]
    if rest:
        L.append(f"- Also missing: {', '.join(rest[:8])}{' and more' if len(rest) > 8 else ''}.")

    # 9. Recommendation
    L += ["", "## 9. Recommendation",
          f"Business recommends the {ctx['request_type'].lower()} as set out in section 2 [Ask], subject to the items in section 8. "
          "Recommended for approval as proposed."]
    md = "\n".join(L)
    return _fit(md)


def _fit(md: str) -> str:
    """Hold the paper to MAX_WORDS: drop the last bullet of the section with the most bullets (sections 3 to 6) until it fits."""
    lines = md.splitlines()
    while words("\n".join(lines)) > MAX_WORDS:
        sec, by = "", {}
        for i, x in enumerate(lines):
            if x.startswith("## "):
                sec = x
            elif x.startswith("- ") and re.match(r"## [3-6]\.", sec):
                by.setdefault(sec, []).append(i)
        if not by:
            break
        lines.pop(max(by.values(), key=len)[-1])
    return "\n".join(lines)
