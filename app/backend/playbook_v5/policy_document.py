"""The credit policy pack and the seeded circular as professional Word and PDF documents (PLAN_R3 S1-2).

The pack (`backend/cockpit_v4/credit_policy.json`, or an amended copy of it) is written up one book at a time as a
board-approved credit policy: cover page, document control, contents, purpose and scope, governance, definitions,
one chapter per pack section with each clause as a numbered subsection, compliance and breach handling, and a
clause index. A circular (`circulars.C_2026_03`) is written up in supervisory-circular form.

Both formats are rendered from one block list so the Word and PDF versions say exactly the same thing. Word styling
comes only from `house` (the house-style rule); the PDF uses reportlab with the same palette.

The pack's `institution` and `note` fields are never printed: the documents speak of "the Bank".
"""
from __future__ import annotations

import io
import re
from datetime import UTC, date, datetime
from html import escape
from typing import Any

from backend.playbook_v5 import circulars, house

# --------------------------------------------------------------------------------------------------------------
# Formatting helpers
# --------------------------------------------------------------------------------------------------------------

_ACRONYMS = {"ead", "ecl", "dscr", "ltv", "dpd", "dbr", "utp", "sicr", "fpd", "sar", "ews", "id", "ifrs", "ebitda"}
_WORDS = {"min": "minimum", "max": "maximum", "mn": "million"}
_UNITS = (("_sar_mn", "SAR m"), ("_pct", "%"), ("_x", "x"), ("_days", "days"), ("_months", "months"),
          ("_quarters", "quarters"), ("_points", "points"))
_BOOK_META = {
    "corporate": {"ref": "CCP", "owner": "Credit Risk Policy, Chief Credit Officer"},
    "retail": {"ref": "RCP", "owner": "Retail Credit Policy, Chief Credit Officer"},
}
_APPROVERS = {"noura.alharbi": "Noura Al-Harbi, Head of Credit"}


def humanise(key: str) -> str:
    """`single_obligor_ead_sar_mn` -> "Single obligor EAD (SAR m)"; labels already in prose are kept."""
    if "_" not in key and not key.islower():
        return key
    unit = ""
    for suffix, label in _UNITS:
        if key.endswith(suffix) and key != suffix.lstrip("_"):
            key, unit = key[: -len(suffix)], label
            break
    words = [w.upper() if w in _ACRONYMS else _WORDS.get(w, w) for w in key.split("_") if w]
    text = " ".join(words)
    text = text.replace("re rating", "re-rating").replace("sub sector", "sub-sector")
    text = text[:1].upper() + text[1:] if text else key
    return f"{text} ({unit})" if unit else text


def _fmt_date(value: Any) -> str:
    if not value:
        return "—"
    try:
        d = date.fromisoformat(str(value)[:10])
    except ValueError:
        return str(value)
    return f"{d.day} {d.strftime('%B %Y')}"


def _num(v: float) -> str:
    return f"{v:,.2f}".rstrip("0").rstrip(".") if isinstance(v, float) and v != int(v) else f"{v:,.0f}"


def _fmt_threshold(key: str, value: Any, rule: str) -> tuple[str, bool]:
    """A threshold value as text, and whether it is numeric (right-aligned)."""
    if isinstance(value, bool):
        return ("Yes" if value else "No"), False
    if isinstance(value, int | float):
        if key.endswith("_x"):
            return f"{value:.2f}", True
        text = _num(value)
        if key == humanise(key) and f"{text}%" in rule:  # prose label whose rule quotes it as a percentage
            text = f"{text}%"
        return text, True
    if isinstance(value, list | tuple):
        return ", ".join(str(v) for v in value), False
    return str(value), False


def _threshold_table(clause: dict[str, Any]) -> tuple[list[str], list[list[str]], list[bool]] | None:
    th = clause.get("thresholds") or {}
    if not th:
        return None
    rows, flags = [], []
    for k, v in th.items():
        text, numeric = _fmt_threshold(k, v, clause.get("rule", ""))
        rows.append([humanise(k), text])
        flags.append(numeric)
    return ["Parameter", "Value"], rows, [False, all(flags)]


def _ids(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _sentence(text: str) -> str:
    text = text.strip()
    return text if text.endswith((".", "!", "?")) else text + "."


# --------------------------------------------------------------------------------------------------------------
# The block list: one description of the document, rendered to Word and to PDF
# --------------------------------------------------------------------------------------------------------------


class _Blocks:
    def __init__(self) -> None:
        self.items: list[tuple] = []

    def h1(self, text: str) -> None:
        self.items.append(("h1", text))

    def h2(self, text: str) -> None:
        self.items.append(("h2", text))

    def p(self, text: str) -> None:
        self.items.append(("p", text))

    def label(self, label: str, value: str) -> None:
        self.items.append(("p", f"**{label}:** {value}"))

    def bullets(self, items: list[str]) -> None:
        if items:
            self.items.append(("bullets", list(items)))

    def numbered(self, items: list[str]) -> None:
        if items:
            self.items.append(("numbered", list(items)))

    def table(self, header: list[str], rows: list[list[str]], numeric: list[bool] | None = None,
              widths: list[float] | None = None) -> None:
        self.items.append(("table", header, rows, numeric or [False] * len(header), widths))

    def callout(self, text: str, tone: str = "info") -> None:
        self.items.append(("callout", text, tone))

    def caption(self, text: str) -> None:
        self.items.append(("caption", text))

    def contents(self) -> None:
        self.items.append(("contents",))

    def pagebreak(self) -> None:
        self.items.append(("pagebreak",))


# --------------------------------------------------------------------------------------------------------------
# Policy content
# --------------------------------------------------------------------------------------------------------------


def _book(pack: dict[str, Any], book: str) -> dict[str, Any]:
    books = pack.get("books") or {}
    if book not in books:
        raise KeyError(f"unknown policy book: {book!r} (expected one of {sorted(books)})")
    return books[book]


def _clauses(bk: dict[str, Any]) -> list[dict[str, Any]]:
    return [c for s in bk.get("sections", []) for c in s.get("clauses", [])]


def _policy_ref(bk: dict[str, Any], book: str) -> str:
    year = str(bk.get("approved_on") or "")[:4] or str(datetime.now(UTC).year)
    return f"{_BOOK_META.get(book, {'ref': book[:3].upper()})['ref']}-{year}"


def _policy_meta(pack: dict[str, Any], book: str) -> tuple[str, str, list[tuple[str, str]]]:
    bk = _book(pack, book)
    title = bk.get("title") or f"{book.title()} Credit Policy"
    subtitle = f"Approved by the {bk.get('approved_by', 'approving committee')}"
    meta = [
        ("Policy reference", _policy_ref(bk, book)),
        ("Version", str(pack.get("pack_version") or "—")),
        ("Approved by", f"{bk.get('approved_by', '—')}, {_fmt_date(bk.get('approved_on'))}"),
        ("Next review", _fmt_date(bk.get("next_review"))),
        ("Owner function", _BOOK_META.get(book, {}).get("owner", "Credit Risk Policy")),
        ("Classification", "Internal"),
    ]
    return title, subtitle, meta


def _scope_sentence(scope: str) -> str:
    scope = scope.strip().rstrip(".")
    return (scope[:1].lower() + scope[1:]) if scope[:3].lower() == "all" else scope


def _definitions(book: str) -> list[list[str]]:
    common = [
        ["DPD", "Days past due: the number of days a contractual payment has been overdue, measured on the "
                "oldest unpaid amount."],
        ["EAD", "Exposure at default: the expected outstanding exposure at the time of default, including the "
                "expected drawing of undrawn commitments."],
        ["ECL", "Expected credit loss: the probability-weighted estimate of credit losses recognised under "
                "IFRS 9, over 12 months for Stage 1 and over the lifetime of the exposure for Stages 2 and 3."],
        ["SICR", "Significant increase in credit risk since initial recognition, assessed under the staging "
                 "clauses of this policy."],
        ["Stage 1", "Performing exposures with no significant increase in credit risk since origination; "
                    "12-month ECL is recognised."],
        ["Stage 2", "Exposures that meet a SICR trigger but are not credit-impaired; lifetime ECL is recognised."],
        ["Stage 3", "Credit-impaired (defaulted) exposures; lifetime ECL is recognised and interest is "
                    "recognised on the net carrying amount."],
        ["LTV", "Loan to value: outstanding exposure divided by the recognised value of the security, "
                "expressed as a percentage."],
    ]
    if book == "retail":
        extra = [
            ["DBR", "Debt burden ratio: total monthly credit obligations, including the proposed facility, as a "
                    "share of verified net monthly income."],
            ["Behavioural score", "The Bank's internal score of an account's performance on book, used for "
                                  "limit management and staging."],
            ["FPD", "First payment default: an account that misses its first scheduled instalment."],
            ["Restructure", "A change to contractual terms granted because the customer is in or near financial "
                            "difficulty."],
            ["Vintage", "The cohort of accounts originated in the same month or quarter, tracked by months on "
                        "book."],
        ]
    else:
        extra = [
            ["DSCR", "Debt service coverage ratio: cash available for debt service divided by scheduled "
                     "principal and profit or interest payments, expressed as a multiple (x)."],
            ["Leverage", "Net debt divided by EBITDA, expressed as a multiple (x)."],
            ["Notch", "One step on the Bank's internal rating scale."],
            ["Connected group", "Obligors connected by ownership or control, treated as a single risk."],
            ["UTP", "Unlikeliness to pay: an assessment that the obligor is unlikely to meet its obligations in "
                    "full without recourse to security, regardless of days past due."],
            ["Watchlist", "The list of obligors under enhanced monitoring because of early signs of "
                          "deterioration; watchlist names are reviewed at least monthly."],
        ]
    return sorted(common + extra, key=lambda r: (r[0].startswith("Stage"), r[0].lower()))


def _document_control(pack: dict[str, Any], bk: dict[str, Any]) -> list[list[str]]:
    clauses = _clauses(bk)
    base_version = str(bk.get("approved_on") or "")[:7].replace("-", ".") or "—"
    rows = [[base_version, _fmt_date(bk.get("approved_on")), bk.get("approved_by", "—"),
             "Annual review; policy re-approved in full."]]
    amended: dict[str, list[dict[str, Any]]] = {}
    for c in clauses:
        if c.get("effective_from") or c.get("source"):
            amended.setdefault(str(c.get("source") or "policy amendment"), []).append(c)
    version = str(pack.get("pack_version") or "")
    if amended:
        for source, cs in amended.items():
            when = max((str(c.get("effective_from") or c.get("last_reviewed") or "") for c in cs), default="")
            rows.append([version or "—", _fmt_date(when), "Head of Credit",
                         f"{_ids([c['clause'] for c in cs])} amended or added under {source}."])
    elif version and version != base_version:
        when = max((str(c.get("last_reviewed") or "") for c in clauses), default="")
        rows.append([version, _fmt_date(when or bk.get("approved_on")), bk.get("approved_by", "—"),
                     "Current consolidated version of the policy."])
    return rows


def _policy_blocks(pack: dict[str, Any], book: str) -> _Blocks:
    bk = _book(pack, book)
    clauses = _clauses(bk)
    committee = bk.get("approved_by") or "the approving committee"
    title = bk.get("title") or f"{book.title()} Credit Policy"
    owner_fn = _BOOK_META.get(book, {}).get("owner", "Credit Risk Policy")
    b = _Blocks()

    b.h1("Document control")
    b.table(["Version", "Date", "Approver", "Change summary"], _document_control(pack, bk),
            widths=[2.6, 3.0, 3.8, 7.2])
    b.label("Policy reference", _policy_ref(bk, book))
    b.label("Next scheduled review", _fmt_date(bk.get("next_review")))
    b.caption("This document is controlled. Printed copies are uncontrolled; the current version is the one held "
              "by Credit Risk Policy.")
    b.contents()

    # 1. Purpose and scope
    b.h1("1. Purpose and scope")
    lending = "corporate and commercial" if book == "corporate" else "consumer"
    b.p(f"This policy sets out the rules under which the Bank originates, manages, monitors and provisions credit "
        f"exposure in its {lending} book. It applies to {_scope_sentence(bk.get('scope', 'all lending in the book'))}, "
        f"whether booked at origination, renewal, increase or restructure.")
    b.p("The policy defines the limits, standards and triggers that every credit decision must satisfy, the "
        "staging and provisioning rules that follow from them, and the authority required to depart from them. "
        "It is read together with the Bank's risk appetite statement, its IFRS 9 impairment methodology and the "
        "delegated credit authority matrix; where they differ, the stricter requirement applies.")
    b.p("Business units may adopt procedures that are more conservative than this policy. No requirement may be "
        "relaxed except through the exceptions route in section 2 or an amendment approved by the "
        f"{committee}.")

    # 2. Governance and roles
    b.h1("2. Governance and roles")
    b.h2("2.1 Policy ownership and approval")
    b.p(f"The policy is owned by {owner_fn} and approved by the {committee}. The owner maintains the policy, "
        "proposes amendments, and issues circulars that amend individual clauses between annual reviews; each "
        f"circular is reported to the {committee} at its next meeting.")
    b.h2("2.2 Review cycle")
    b.p(f"The policy is reviewed in full at least annually. The current version was approved on "
        f"{_fmt_date(bk.get('approved_on'))} and the next review falls due on {_fmt_date(bk.get('next_review'))}. "
        "An out-of-cycle review is triggered by a material change in regulation, risk appetite or portfolio "
        "performance.")
    b.h2("2.3 Exceptions and overrides")
    override = next((c for c in clauses if "override" in str(c.get("title", "")).lower()), None)
    if override:
        b.p(f"A departure from this policy is an override and follows {override['clause']} "
            f"({override.get('title')}): it requires approval one authority level above the normal approver and a "
            "documented compensating factor. Exceptions outside that clause are approved by the Head of Credit and "
            f"reported to the {committee}.")
    else:
        b.p("A departure from this policy is an exception. It requires the approval of the Head of Credit, must "
            "state the compensating factor and the date by which the exposure returns within policy, and is "
            f"reported to the {committee} at its next meeting. Exceptions to a limit set by the {committee} are "
            "approved by that committee.")
    b.h2("2.4 Clause owners")
    b.p("Each clause has a named owner, accountable for its application, monitoring and annual review.")
    owners: dict[str, list[str]] = {}
    for c in clauses:
        owners.setdefault(c.get("owner") or "Unassigned", []).append(c["clause"])
    b.table(["Owner", "Clauses"], [[o, ", ".join(ids)] for o, ids in owners.items()], widths=[6.0, 10.6])

    # 3. Definitions
    b.h1("3. Definitions")
    b.p("Terms used in this policy have the following meanings.")
    b.table(["Term", "Definition"], _definitions(book), widths=[3.4, 13.2])

    # 4.. One chapter per section
    n = 4
    for sec in bk.get("sections", []):
        b.h1(f"{n}. {sec.get('title', '')} ({sec.get('section', '')})")
        for i, c in enumerate(sec.get("clauses", []), start=1):
            b.h2(f"{n}.{i} {c['clause']} {c.get('title', '')}")
            if c.get("effective_from") or c.get("source"):
                bits = []
                if c.get("effective_from"):
                    bits.append(f"effective {_fmt_date(c['effective_from'])}")
                if c.get("source"):
                    bits.append(f"under {c['source']}")
                note = f"**Amended clause:** {' '.join(bits)}."
                if c.get("summary"):
                    note += f" {_sentence(str(c['summary']))}"
                b.callout(note)
            b.label("Policy statement", _sentence(c.get("rule", "")))
            tt = _threshold_table(c)
            if tt:
                header, rows, numeric = tt
                b.table(header, rows, numeric, widths=[8.0, 8.6])
            b.label("Applies to", ", ".join(humanise(a) for a in c.get("applies_to", [])) or "—")
            b.label("Owner", c.get("owner") or "—")
            b.label("Last reviewed", _fmt_date(c.get("last_reviewed")))
            if c.get("levers"):
                b.p("**Permitted changes (levers):**")
                b.bullets([_sentence(lv[:1].upper() + lv[1:]) for lv in c["levers"]])
        n += 1

    # Compliance and breach handling
    b.h1(f"{n}. Compliance and breach handling")
    b.p("Compliance with this policy is a first-line responsibility of the business and credit units that "
        "originate and manage exposure. Credit Risk Policy monitors compliance as the second line, and Internal "
        "Audit tests it as part of its annual plan.")
    b.bullets([
        "A breach of a limit, cap or trigger is reported to the clause owner within five business days of "
        "identification, with the exposure, the cause and a proposed remediation.",
        f"Breaches of a limit set by the {committee} are escalated to that committee at its next meeting, and "
        "immediately where the breach exceeds the limit by more than 10%.",
        "No new exposure that would deepen a breach may be approved until the remediation plan is agreed.",
        "Overrides and exceptions are recorded with their approver and compensating factor, and reported "
        "quarterly by product and approver.",
        "Repeated or wilful non-compliance is referred to the Head of Credit and may result in withdrawal of "
        "delegated credit authority.",
    ])
    b.p("Records supporting each credit decision, override and breach are retained in line with the Bank's "
        "record retention standard.")

    # Appendix
    b.h1("Appendix A. Clause index")
    b.table(["Clause", "Title", "Owner", "Last reviewed"],
            [[c["clause"], c.get("title", ""), c.get("owner", "—"), _fmt_date(c.get("last_reviewed"))]
             for c in clauses], widths=[2.2, 6.4, 5.0, 3.0])
    b.caption(f"{title}, version {pack.get('pack_version', '—')}: {len(clauses)} clauses in "
              f"{len(bk.get('sections', []))} chapters.")
    return b


# --------------------------------------------------------------------------------------------------------------
# Circular content
# --------------------------------------------------------------------------------------------------------------


def _approver(circ: dict[str, Any]) -> str:
    who = str(circ.get("approved_by") or "")
    return _APPROVERS.get(who, who.replace(".", " ").title() if who else "Head of Credit")


def _quarter(value: Any) -> str:
    try:
        d = date.fromisoformat(str(value)[:10])
    except ValueError:
        return "next"
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


def _circular_meta(circ: dict[str, Any]) -> tuple[str, str, list[tuple[str, str]]]:
    title = circ.get("title") or circ.get("reference") or "Circular"
    meta = [
        ("Reference", str(circ.get("reference") or "—")),
        ("Date issued", _fmt_date(circ.get("issued"))),
        ("Effective date", _fmt_date(circ.get("effective_from"))),
        ("Issued by", str(circ.get("issuer") or "Credit Risk Policy")),
        ("Approved by", _approver(circ)),
        ("Classification", "Internal"),
    ]
    return title, "Credit Risk Policy — Circular", meta


def _subject(circ: dict[str, Any]) -> str:
    title = str(circ.get("title") or "")
    ref = str(circ.get("reference") or "")
    return re.sub(rf"^Circular\s+{re.escape(ref)}\s*:\s*", "", title) if ref else title


def _actions(circ: dict[str, Any]) -> list[str]:
    clauses = circ.get("clauses") or []
    staging = [c["clause"] for c in clauses
               if "stage" in c.get("applies_to", []) or "stage 2" in str(c.get("rule", "")).lower()]
    quarter = _quarter(circ.get("effective_from"))
    out = []
    if staging:
        out.append(f"**IFRS 9:** update the staging engine to apply the amended triggers in {_ids(staging)} from "
                   f"the first reporting date in {quarter}, and confirm the change through the staging release "
                   "controls.")
    text = " ".join(str(c.get("rule", "")).lower() for c in clauses)
    wanted = ("C-DOWNGRADE", "C-WATCH", "R-SCORE-DOWN")
    ews = [rid for rid in wanted
           if any(rid == r[1] and any(k in text for k in r[0]) for r in circulars.EWS_RULES)] or list(wanted)
    out.append(f"**Early Warning rule owners:** review {_ids(ews)} so that the early-warning signals align with the "
               "new staging triggers, and report any change in alert volumes to the Head of Credit.")
    by = re.search(r"by\s+(\d{1,2}\s+[A-Z][a-z]+\s+\d{4})", str(circ.get("transitional") or ""))
    out.append("**Model Validation:** back-test the staging model against the amended triggers and report the "
               f"effect on stage migration{' by ' + by.group(1) if by else ''}.")
    out.append(f"**Finance:** reflect the amended staging in the {quarter} ECL and explain the movement attributable "
               f"to {circ.get('reference', 'this circular')} in the provisioning commentary.")
    return out


def _circular_blocks(circ: dict[str, Any]) -> _Blocks:
    b = _Blocks()
    b.p("**Credit Risk Policy — Circular**")
    b.table(["", ""], [
        ["Reference", str(circ.get("reference") or "—")],
        ["Date", _fmt_date(circ.get("issued"))],
        ["To", str(circ.get("addressees") or "—")],
        ["From", str(circ.get("issuer") or "Credit Risk Policy")],
        ["Subject", _subject(circ)],
        ["Effective date", _fmt_date(circ.get("effective_from"))],
    ], widths=[3.4, 13.2])

    b.h1("1. Purpose")
    b.p(str(circ.get("purpose") or ""))
    b.h1("2. Summary of changes")
    b.p(str(circ.get("summary") or ""))
    clauses = circ.get("clauses") or []
    if clauses:
        b.table(["Clause", "Title", "Change"],
                [[c["clause"], c.get("title", ""), "Amended" if c.get("previous") else "New clause"]
                 for c in clauses], widths=[2.6, 9.6, 4.4])

    b.h1("3. Amended and new clauses")
    for i, c in enumerate(clauses, start=1):
        b.h2(f"3.{i} {c['clause']} {c.get('title', '')}")
        where = " ".join(x for x in (str(c.get("section") or ""), str(c.get("section_title") or "")) if x)
        if where or c.get("book"):
            book = str(c.get("book") or "").title()
            b.caption(f"{book + ' Credit Policy' if book else ''}{', ' if book and where else ''}"
                      f"{'section ' + where if where else ''}")
        b.label("New text", _sentence(str(c.get("rule", ""))))
        prev = c.get("previous")
        b.label("Previous text", f"*{_sentence(str(prev))}*" if prev else "New clause.")
        tt = _threshold_table(c)
        if tt:
            header, rows, numeric = tt
            b.table(header, rows, numeric, widths=[8.0, 8.6])

    b.h1("4. Effective date and transition")
    b.p(f"This circular takes effect on {_fmt_date(circ.get('effective_from'))}. "
        f"{circ.get('transitional') or ''}".strip())
    b.h1("5. Actions required")
    b.bullets(_actions(circ))
    b.p("Addressees confirm implementation to Credit Risk Policy within 30 days of the effective date.")

    b.h1("Issued and approved")
    b.table(["", ""], [
        ["Issued by", str(circ.get("issuer") or "Credit Risk Policy")],
        ["Approved by", _approver(circ)],
        ["Date", _fmt_date(circ.get("issued"))],
    ], widths=[3.4, 13.2])
    b.caption("Queries on this circular are addressed to Credit Risk Policy.")
    return b


# --------------------------------------------------------------------------------------------------------------
# Word renderer (house style only)
# --------------------------------------------------------------------------------------------------------------


def _render_docx(title: str, subtitle: str, meta: list[tuple[str, str]], blocks: _Blocks, kind: str) -> bytes:
    doc = house.new_document(title, subtitle, meta, kind=kind, generated_by="Credit Risk Policy")
    for item in blocks.items:
        k = item[0]
        if k == "h1":
            doc.add_heading(item[1], level=1)
        elif k == "h2":
            doc.add_heading(item[1], level=2)
        elif k == "p":
            house.rich(doc.add_paragraph(), item[1])
        elif k in ("bullets", "numbered"):
            style = "List Bullet" if k == "bullets" else "List Number"
            for text in item[1]:
                house.rich(doc.add_paragraph(style=style), text)
        elif k == "table":
            _, header, rows, numeric, widths = item
            if header and not any(header):  # key/value block: no header row, so give the labels in bold
                house.table(doc, ["Item", "Detail"], rows, numeric=numeric, widths=widths)
            else:
                house.table(doc, header, rows, numeric=numeric, widths=widths)
        elif k == "callout":
            house.callout(doc, item[1], item[2])
        elif k == "caption":
            house.caption(doc, item[1])
        elif k == "contents":
            house.contents(doc)
        elif k == "pagebreak":
            doc.add_page_break()
    return house.save(doc)


# --------------------------------------------------------------------------------------------------------------
# PDF renderer (reportlab, house palette)
# --------------------------------------------------------------------------------------------------------------


def _inline(text: str) -> str:
    """Escape for reportlab and turn **bold** / *italic* into markup."""
    out = escape(text, quote=False)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", out)
    return re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", out)


def _render_pdf(title: str, subtitle: str, meta: list[tuple[str, str]], blocks: _Blocks, kind: str) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from reportlab.platypus.tableofcontents import TableOfContents

    def c(hex_: str):
        return colors.HexColor("#" + hex_)

    ink, muted, accent, accent2, band, rule = (c(house.INK), c(house.MUTED), c(house.ACCENT), c(house.ACCENT_2),
                                               c(house.BAND), c(house.RULE))
    base = ParagraphStyle("Body", fontName="Helvetica", fontSize=9.5, leading=13.5, textColor=ink, spaceAfter=5)
    st = {
        "body": base,
        "h1": ParagraphStyle("H1", parent=base, fontName="Helvetica-Bold", fontSize=15, leading=19,
                             textColor=accent, spaceBefore=14, spaceAfter=7, keepWithNext=1),
        "h2": ParagraphStyle("H2", parent=base, fontName="Helvetica-Bold", fontSize=11.5, leading=15,
                             textColor=accent, spaceBefore=10, spaceAfter=4, keepWithNext=1),
        "caption": ParagraphStyle("Caption", parent=base, fontName="Helvetica-Oblique", fontSize=8, leading=11,
                                  textColor=muted),
        "bullet": ParagraphStyle("Bullet", parent=base, leftIndent=14, bulletIndent=4, spaceAfter=3),
        "cell": ParagraphStyle("Cell", parent=base, fontSize=8.5, leading=11, spaceAfter=0),
        "cell_r": ParagraphStyle("CellR", parent=base, fontSize=8.5, leading=11, spaceAfter=0, alignment=TA_RIGHT),
        "head": ParagraphStyle("Head", parent=base, fontName="Helvetica-Bold", fontSize=8.5, leading=11,
                               spaceAfter=0, textColor=colors.white),
        "head_r": ParagraphStyle("HeadR", parent=base, fontName="Helvetica-Bold", fontSize=8.5, leading=11,
                                 spaceAfter=0, textColor=colors.white, alignment=TA_RIGHT),
        "label": ParagraphStyle("Label", parent=base, fontName="Helvetica-Bold", fontSize=8.5, leading=11,
                                spaceAfter=0, textColor=muted),
    }
    margin = 2.2 * cm
    width = A4[0] - 2 * margin

    def make_table(header: list[str], rows: list[list[str]], numeric: list[bool],
                   widths: list[float] | None) -> Table:
        ncol = len(header) if header else (len(rows[0]) if rows else 1)
        if widths and len(widths) == ncol:
            total = sum(widths)
            col_w = [width * w / total for w in widths]
        else:
            col_w = [width / ncol] * ncol
        keyval = not any(header)
        data: list[list[Any]] = []
        if not keyval:
            data.append([Paragraph(_inline(h), st["head_r" if numeric[i] else "head"]) for i, h in enumerate(header)])
        for row in rows:
            cells = []
            for i, v in enumerate(row):
                sty = st["label"] if keyval and i == 0 else st["cell_r" if numeric[i] else "cell"]
                cells.append(Paragraph(_inline(str(v)), sty))
            data.append(cells)
        t = Table(data, colWidths=col_w, repeatRows=0 if keyval else 1, hAlign="LEFT")
        cmds: list[tuple] = [
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
            ("LINEBELOW", (0, 0), (-1, -1), 0.5, rule), ("BOX", (0, 0), (-1, -1), 0.5, rule),
        ]
        if keyval:
            cmds += [("BACKGROUND", (0, 0), (0, -1), band)]
        else:
            cmds += [("BACKGROUND", (0, 0), (-1, 0), accent),
                     ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, band])]
        t.setStyle(TableStyle(cmds))
        return t

    class _Doc(SimpleDocTemplate):
        def afterFlowable(self, flowable):  # noqa: N802 - reportlab hook name
            if isinstance(flowable, Paragraph) and flowable.style.name == "H1":
                text = flowable.getPlainText()
                key = "h1-" + re.sub(r"\W", "", text)
                self.canv.bookmarkPage(key)
                self.canv.addOutlineEntry(text, key, level=0)
                if text != "Document control":
                    self.notify("TOCEntry", (0, text, self.page, key))

    def first_page(canv, _doc) -> None:
        canv.saveState()
        canv.setFillColor(accent)
        canv.rect(0, A4[1] - 1.1 * cm, A4[0], 1.1 * cm, stroke=0, fill=1)
        canv.setFillColor(accent2)
        canv.rect(0, A4[1] - 1.3 * cm, A4[0], 0.2 * cm, stroke=0, fill=1)
        canv.setStrokeColor(rule)
        canv.line(margin, 2.0 * cm, A4[0] - margin, 2.0 * cm)
        canv.setFont("Helvetica", 7.5)
        canv.setFillColor(muted)
        canv.drawString(margin, 1.5 * cm, "Internal. Controlled document; printed copies are uncontrolled.")
        canv.restoreState()

    def later_pages(canv, doc_) -> None:
        canv.saveState()
        canv.setFont("Helvetica", 7.5)
        canv.setFillColor(muted)
        canv.drawString(margin, A4[1] - 1.25 * cm, f"CreditProbe  |  {title}")
        canv.setStrokeColor(rule)
        canv.setLineWidth(0.5)
        canv.line(margin, A4[1] - 1.4 * cm, A4[0] - margin, A4[1] - 1.4 * cm)
        canv.line(margin, 1.5 * cm, A4[0] - margin, 1.5 * cm)
        canv.drawRightString(A4[0] - margin, 1.05 * cm, f"Page {doc_.page}")
        canv.drawString(margin, 1.05 * cm, "Internal")
        canv.restoreState()

    story: list[Any] = [Spacer(1, 3.2 * cm)]
    story.append(Paragraph(f'<font color="#{house.ACCENT_2}"><b>CREDITPROBE</b></font>'
                           f'<font color="#{house.MUTED}">   ·   {escape(kind.upper())}</font>',
                           ParagraphStyle("Kicker", parent=base, fontSize=10, spaceAfter=14)))
    story.append(Paragraph(escape(title), ParagraphStyle("Title", parent=base, fontName="Helvetica-Bold",
                                                         fontSize=24, leading=29, textColor=accent, spaceAfter=10)))
    if subtitle:
        story.append(Paragraph(escape(subtitle), ParagraphStyle("Sub", parent=base, fontSize=12.5, leading=16,
                                                                textColor=muted, spaceAfter=22)))
    stamp = datetime.now(UTC).strftime("%d %b %Y %H:%M UTC")
    cover_rows = [[Paragraph(escape(k), st["label"]), Paragraph(escape(v or "—"), st["cell"])]
                  for k, v in [*meta, ("Generated", f"{stamp} by Credit Risk Policy")]]
    ct = Table(cover_rows, colWidths=[4.5 * cm, width - 4.5 * cm], hAlign="LEFT")
    ct.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.5, rule), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                            ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story += [ct, PageBreak()]

    toc = None
    for item in blocks.items:
        k = item[0]
        if k == "h1":
            story.append(Paragraph(_inline(item[1]), st["h1"]))
        elif k == "h2":
            story.append(Paragraph(_inline(item[1]), st["h2"]))
        elif k == "p":
            story.append(Paragraph(_inline(item[1]), st["body"]))
        elif k in ("bullets", "numbered"):
            for j, text in enumerate(item[1], start=1):
                story.append(Paragraph(_inline(text), st["bullet"], bulletText="•" if k == "bullets" else f"{j}."))
            story.append(Spacer(1, 3))
        elif k == "table":
            _, header, rows, numeric, widths = item
            story += [make_table(header, rows, numeric, widths), Spacer(1, 7)]
        elif k == "callout":
            fill = {"info": "E8F1F6", "warning": "FDF2DC", "critical": "FBE6E6"}.get(item[2], "E8F1F6")
            box = Table([[Paragraph(_inline(item[1]), st["cell"])]], colWidths=[width])
            box.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), c(fill)),
                                     ("LINEBEFORE", (0, 0), (0, -1), 2.5, accent2),
                                     ("LEFTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 5),
                                     ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
            story += [KeepTogether([box]), Spacer(1, 6)]
        elif k == "caption":
            story.append(Paragraph(_inline(item[1]), st["caption"]))
        elif k == "contents":
            toc = TableOfContents()
            toc.levelStyles = [ParagraphStyle("TOC1", parent=base, fontSize=10, leading=15, leftIndent=0,
                                              firstLineIndent=0)]
            toc.dotsMinLevel = 0
            story += [PageBreak(), Paragraph("Contents", ParagraphStyle("Contents", parent=st["h2"], fontSize=15,
                                                                        leading=19)), toc, PageBreak()]
        elif k == "pagebreak":
            story.append(PageBreak())

    buf = io.BytesIO()
    doc = _Doc(buf, pagesize=A4, leftMargin=margin, rightMargin=margin, topMargin=2.0 * cm,
               bottomMargin=2.0 * cm, title=title, author="Credit Risk Policy", subject=subtitle)
    if toc is not None:
        doc.multiBuild(story, onFirstPage=first_page, onLaterPages=later_pages)
    else:
        doc.build(story, onFirstPage=first_page, onLaterPages=later_pages)
    return buf.getvalue()


# --------------------------------------------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------------------------------------------


def policy_docx(pack: dict[str, Any], book: str) -> bytes:
    """The book's credit policy ("Corporate Credit Policy" / "Retail Credit Policy") as a Word document."""
    title, subtitle, meta = _policy_meta(pack, book)
    return _render_docx(title, subtitle, meta, _policy_blocks(pack, book), "Credit Policy")


def policy_pdf(pack: dict[str, Any], book: str) -> bytes:
    """The book's credit policy as an A4 PDF."""
    title, subtitle, meta = _policy_meta(pack, book)
    return _render_pdf(title, subtitle, meta, _policy_blocks(pack, book), "Credit Policy")


def circular_docx(circ: dict[str, Any]) -> bytes:
    """A policy circular (e.g. `circulars.C_2026_03`) as a Word document."""
    title, subtitle, meta = _circular_meta(circ)
    return _render_docx(title, subtitle, meta, _circular_blocks(circ), "Circular")


def circular_pdf(circ: dict[str, Any]) -> bytes:
    """A policy circular as an A4 PDF."""
    title, subtitle, meta = _circular_meta(circ)
    return _render_pdf(title, subtitle, meta, _circular_blocks(circ), "Circular")


__all__ = ["circular_docx", "circular_pdf", "humanise", "policy_docx", "policy_pdf"]
