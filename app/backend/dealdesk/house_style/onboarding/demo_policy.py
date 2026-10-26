"""PLAN_R11 P6 demo data: a fictional bank credit policy (about 10 pages), written to
`demo_inputs/policy/Fictional_Bank_Credit_Policy.docx`.

The bank ("Sandstone Harbour Bank PJSC") and every name in it are fictional. No real bank, client, staff or project is
named. The text is the source of truth for the document; `python -m backend.dealdesk.house_style.onboarding.demo_policy`
rewrites the .docx (deterministic: fixed core properties, no timestamps).

Some clauses are deliberately weaker than the CBUAE Credit Risk Management Standards (review every 18 months, Stage 2 at
60 days past due, Stage 3 valuations every 18 months, Board re-approval every five years, a 9-month moratorium, write-off
after 7 years) so the onboarding finds them; a few have no data in the books (customer concentration, submission of
covenant certificates) so it reports them as manual; the required memo sections include two the demo memos never write.
"""
from __future__ import annotations

import datetime as dt
import io
import pathlib
from typing import Any

from backend.dealdesk import paths

BANK = "Sandstone Harbour Bank PJSC"
TITLE = "Corporate Credit Policy"
VERSION = "Version 4.2, approved by the Board Credit Committee, effective 1 July 2026"
OUT = paths.V5 / "demo_inputs" / "policy" / "Fictional_Bank_Credit_Policy.docx"

# Each section: number, title, lead paragraphs, clauses (number, text), tables (caption, header, rows).
SECTIONS: list[dict[str, Any]] = [
    {"n": "1", "title": "Purpose, scope and authority", "lead": [
        f"This Corporate Credit Policy (the Policy) sets out the principles, limits and minimum standards under which "
        f"{BANK} (the Bank) originates, approves, documents, monitors and recovers credit to corporate and commercial "
        "obligors. It is the Bank's primary credit risk document and is read together with the Risk Appetite Statement, "
        "the Delegation of Authority matrix in Appendix A and the product programmes approved under it.",
        "The Policy applies to every funded and unfunded facility booked by the Corporate and Commercial Banking divisions, "
        "including trade finance, guarantees, project and contract finance, real-estate finance and treasury lines "
        "extended to corporate obligors. Retail, credit card and small business programmes are governed by their own "
        "programme documents and are outside the scope of this Policy.",
        "Departures from the Policy are exceptions. An exception is approved only by the authority one level above the "
        "authority that would otherwise approve the facility, is recorded in the credit application with its rationale "
        "and mitigants, and is reported to the Board Risk Committee each quarter."],
     "clauses": [
        ("1.1", "The Policy is owned by the Chief Risk Officer and is reviewed by the Board Credit Committee at least "
                "once a year, or earlier when the regulatory framework or the Bank's strategy changes."),
        ("1.2", "Where this Policy and an applicable regulation differ, the stricter of the two applies. Business units "
                "may adopt stricter internal standards but may not relax any requirement of this Policy."),
        ("1.3", "Every credit decision is documented in a credit application prepared by the business unit and "
                "independently reviewed by the Credit Risk division before it is presented to the approving authority."),
     ]},
    {"n": "2", "title": "Credit governance and delegation of authority", "lead": [
        "The Board of Directors sets the Bank's credit risk appetite and approves this Policy. The Board delegates credit "
        "approval authority to the Board Credit Committee, the Executive Credit Committee and named individuals through "
        "the Delegation of Authority matrix in Appendix A. Authority is personal to the role, is exercised jointly by a "
        "business and a risk signatory (the four-eyes principle), and may not be sub-delegated.",
        "The approving authority is determined by the obligor's aggregate exposure after the proposed facilities, "
        "including the exposure of connected parties, and by its internal rating. A proposal that carries a policy "
        "exception is approved one level higher."],
     "clauses": [
        ("2.1", "Facilities to a single obligor or group exceeding 10% of the Bank's Tier 1 capital are material "
                "facilities and require the approval of the Board of Directors."),
        ("2.2", "Material facilities shall be re-approved by the Board of Directors at least every five years."),
        ("2.3", "No member of an approving authority may approve a facility to an obligor in which that member, or a "
                "member of their family, holds an interest; the conflict is declared and recorded in the minutes."),
        ("2.4", "Credit applications are submitted to the approving authority not less than 10 business days before "
                "the expiry of the existing facilities."),
     ]},
    {"n": "3", "title": "The credit application", "lead": [
        "A credit application presents the obligor, the request, the analysis and the recommendation in the Bank's "
        "standard format. The business unit writes the proposal; the Credit Risk division adds its independent opinion, "
        "its checks and the conditions it recommends. The approving authority records its decision, its conditions and "
        "its comments on the application."],
     "clauses": [
        ("3.1", "Every credit application shall contain the following sections: Executive summary; Obligor and group; "
                "Facilities and request; Financial analysis; Account conduct and bureau report; Business and projects; "
                "Security and collateral; Risks and mitigants; Pricing and RAROC; Environmental and social risk; "
                "Recommendation; Conditions and covenants."),
        ("3.2", "The application states the obligor's internal rating and its date, the aggregate exposure of the group "
                "after the request and the approving authority required under Appendix A."),
        ("3.3", "Audited financial statements for the last three financial years shall be analysed; management accounts "
                "older than six months are not accepted in place of audited statements."),
        ("3.4", "The financial statements of the obligor shall be audited by an auditor on the Bank's approved list."),
        ("3.5", "A credit bureau report dated within the last 30 days shall be obtained for the obligor and each "
                "guarantor before the application is submitted."),
     ]},
    {"n": "4", "title": "Risk acceptance criteria", "lead": [
        "The Bank lends to obligors with a demonstrable capacity to repay from operating cash flow. Collateral mitigates "
        "loss but does not replace repayment capacity. The criteria below apply to every new facility and to every "
        "increase; a renewal that fails a criterion is an exception."],
     "clauses": [
        ("4.1", "The Bank shall not extend new money to an obligor rated below B- on the Bank's internal master scale. "
                "Existing obligors rated CCC may be renewed only with the approval of the Executive Credit Committee."),
        ("4.2", "The debt service coverage ratio after the proposed facilities shall be not less than 1.25x."),
        ("4.3", "Total debt to EBITDA after the proposed facilities shall not exceed 3.5x."),
        ("4.4", "Trading and contracting obligors shall maintain a current ratio of at least 1.10x."),
        ("4.5", "A balloon or bullet repayment shall not exceed 40% of the original facility amount."),
        ("4.6", "No single customer shall account for more than 40% of the obligor's annual revenue."),
        ("4.7", "For contractors, the order backlog shall not exceed 3.0 times annual revenue."),
     ]},
    {"n": "5", "title": "Concentration limits", "lead": [
        "Concentration limits protect the Bank's capital from the failure of a single name, a group or a sector. Limits "
        "are measured on aggregate funded and unfunded exposure, unfunded exposure converted at the regulatory credit "
        "conversion factors. The Risk Management division reports utilisation to the Board Risk Committee monthly."],
     "clauses": [
        ("5.1", "Aggregate exposure to a single obligor shall not exceed AED 300 million."),
        ("5.2", "Aggregate exposure to a group of connected obligors shall not exceed AED 600 million."),
        ("5.3", "Exposure to a group of connected counterparties shall not exceed 25% of the Bank's Tier 1 capital."),
        ("5.4", "No single economic sector shall exceed 15% of the corporate loan book."),
        ("5.5", "Real estate and construction together shall not exceed 20% of the corporate loan book."),
     ]},
    {"n": "6", "title": "Tenor and repayment", "lead": [
        "Tenors match the purpose of the facility and the useful life of the asset financed. Term facilities amortise; "
        "the maximum tenor depends on the obligor's rating bucket and is set out below."],
     "clauses": [
        ("6.1", "The maximum tenor of a term facility by rating bucket is set out in Table 6.1."),
        ("6.2", "Working capital facilities shall not exceed a tenor of 12 months and are renewed on review."),
     ],
     "tables": [{"caption": "Table 6.1 Maximum tenor by rating bucket", "header": ["Rating bucket", "Maximum tenor (years)"],
                 "rows": [["IG", "10"], ["BB", "7"], ["B", "4"], ["CCC-C", "2"]]}]},
    {"n": "7", "title": "Security and collateral", "lead": [
        "Security is taken to improve recovery, not to justify a weak credit. Every item of security is valued, perfected "
        "and monitored. The Legal division approves the form of every security document; standard forms are not amended "
        "without its consent."],
     "clauses": [
        ("7.1", "The loan-to-value ratio on income-producing real estate shall not exceed 65%."),
        ("7.2", "Performance and advance payment guarantees issued for contractors shall carry a cash margin of not "
                "less than 10%."),
        ("7.3", "Real estate collateral shall be revalued by a Bank-approved valuer at least every 24 months, and at "
                "least every 18 months for obligors in Stage 3."),
        ("7.4", "Legal opinions on security shall be no older than 24 months at the date of drawdown."),
        ("7.5", "All security shall be perfected before the first drawdown; a deferral of perfection of up to 60 days "
                "requires the approval of the authority one level above the approving authority."),
        ("7.6", "Secured facilities shall have a collateral cover, after haircuts, of at least 125%."),
        ("7.7", "Guarantees issued by the Bank shall carry an expiry date and follow the Bank's standard format."),
     ]},
    {"n": "8", "title": "Monitoring, review and classification", "lead": [
        "Every obligor is monitored continuously and reviewed formally. The review updates the rating, tests covenants, "
        "confirms security and records the account conduct. Early warning signals are acted on when they arise, not at "
        "the next review."],
     "clauses": [
        ("8.1", "Every corporate obligor shall be reviewed at least every 18 months; obligors rated B+ or worse at least "
                "every 12 months."),
        ("8.2", "Covenant compliance certificates shall be submitted within 120 days of the obligor's financial year end."),
        ("8.3", "A facility more than 60 days past due shall be classified in Stage 2 and placed on the watchlist."),
        ("8.4", "A facility more than 90 days past due on a material obligation shall be classified in Stage 3."),
        ("8.5", "A facility restructured three or more times in a context of financial difficulty shall be classified "
                "in Stage 3."),
        ("8.6", "A non-distressed restructuring with a repayment moratorium exceeding 9 months shall be classified in "
                "Stage 2."),
        ("8.7", "Stage 3 exposures shall be written off no later than 7 years after classification in Stage 3."),
     ]},
    {"n": "9", "title": "Pricing and returns", "lead": [
        "Every facility is priced to return at least the Bank's cost of capital over its life. Pricing outside the "
        "market bounds below is an exception; pricing below the RAROC floor needs the approval of the Chief Risk Officer."],
     "clauses": [
        ("9.1", "The lifetime RAROC of a new facility shall not be below 12%."),
        ("9.2", "Facility margins shall be within the bounds of Table 9.2 for the obligor's rating bucket."),
     ],
     "tables": [{"caption": "Table 9.2 Margin bounds by rating bucket (basis points over the base rate)",
                 "header": ["Rating bucket", "Minimum margin (bps)", "Maximum margin (bps)"],
                 "rows": [["IG", "100", "250"], ["BB", "175", "375"], ["B", "300", "500"], ["CCC-C", "450", "650"]]}]},
    {"n": "10", "title": "Credit committee practice", "lead": [
        "Committees record their decision, the conditions precedent and covenants attached to it, and the questions they "
        "raised. Recurring questions are fed back to the business units so that applications answer them before they "
        "are asked. The Credit Risk division tracks every condition to its due date."],
     "clauses": [
        ("10.1", "Conditions precedent are satisfied and evidenced before the first drawdown; conditions subsequent "
                 "carry a due date and an owner."),
        ("10.2", "A facility approved subject to conditions is not booked until the Credit Administration unit confirms "
                 "the conditions precedent in writing."),
     ]},
]

APPENDIX_A = {"caption": "Appendix A. Delegation of Authority matrix",
              "lead": "Approval authority by aggregate group exposure after the proposed facilities and internal rating. "
                      "An application with one soft-limit breach is approved one level higher; two or more go to the "
                      "Executive Credit Committee.",
              "header": ["Authority", "Maximum exposure (AED million)", "Minimum rating"],
              "rows": [["Corporate Credit Manager", "25", "BBB-"], ["Head of Credit", "100", "BB-"],
                       ["Chief Risk Officer", "200", "B-"], ["Executive Credit Committee", "300", "CCC"],
                       ["Board Credit Committee", "above 300", "C"]]}

GLOSSARY = [
    ("Aggregate exposure", "Funded outstanding plus unfunded commitments converted at the regulatory conversion factors."),
    ("Connected obligors", "Obligors under common ownership or control, or whose repayment depends on one another."),
    ("Material facility", "A facility above the materiality threshold of clause 2.1."),
    ("RAROC", "Risk-adjusted return on capital over the life of the facility, after expected loss and the cost of funds."),
    ("Stage 2, Stage 3", "The IFRS 9 stages: significant increase in credit risk, and credit-impaired."),
]


def _doc_bytes() -> bytes:
    from docx import Document
    from docx.shared import Pt

    d = Document()
    cp = d.core_properties
    cp.author, cp.title, cp.comments = "Credit Risk Policy (fictional)", f"{BANK}: {TITLE}", "Fictional demo document"
    cp.created = cp.modified = dt.datetime(2026, 7, 1)
    cp.last_modified_by, cp.revision = "Credit Risk Policy (fictional)", 1
    st = d.styles["Normal"]
    st.font.name, st.font.size = "Calibri", Pt(11)
    d.add_heading(f"{BANK}", level=0)
    d.add_paragraph(TITLE).runs[0].bold = True
    d.add_paragraph(VERSION)
    d.add_paragraph("Fictional document prepared for the CreditProbe demonstration. The Bank, its committees and its "
                    "figures are invented; no real institution is described.")
    d.add_heading("Contents", level=1)
    for s in SECTIONS:
        d.add_paragraph(f"{s['n']}. {s['title']}")
    d.add_paragraph("Appendix A. Delegation of Authority matrix")
    d.add_paragraph("Appendix B. Glossary")
    d.add_page_break()
    for s in SECTIONS:
        d.add_heading(f"{s['n']}. {s['title']}", level=1)
        for p in s.get("lead", []):
            d.add_paragraph(p)
        for num, text in s.get("clauses", []):
            d.add_paragraph(f"{num} {text}")
        for t in s.get("tables", []):
            d.add_paragraph(t["caption"]).runs[0].italic = True
            tb = d.add_table(rows=1, cols=len(t["header"]))
            tb.style = "Table Grid"
            for i, h in enumerate(t["header"]):
                tb.rows[0].cells[i].text = h
            for r in t["rows"]:
                cells = tb.add_row().cells
                for i, v in enumerate(r):
                    cells[i].text = v
        d.add_paragraph(_commentary(s["n"]))
        if PRACTICE.get(s["n"]):
            d.add_paragraph(PRACTICE[s["n"]])
    d.add_page_break()
    d.add_heading(APPENDIX_A["caption"], level=1)
    d.add_paragraph(APPENDIX_A["lead"])
    tb = d.add_table(rows=1, cols=3)
    tb.style = "Table Grid"
    for i, h in enumerate(APPENDIX_A["header"]):
        tb.rows[0].cells[i].text = h
    for r in APPENDIX_A["rows"]:
        cells = tb.add_row().cells
        for i, v in enumerate(r):
            cells[i].text = v
    d.add_heading("Appendix B. Glossary", level=1)
    for k, v in GLOSSARY:
        p = d.add_paragraph()
        p.add_run(f"{k}. ").bold = True
        p.add_run(v)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


#: Explanatory paragraphs that carry no threshold (a real policy reads this way; they fill the pages).
COMMENTARY = {
    "1": "The Policy is written for the people who apply it: relationship managers, credit analysts, approvers and the "
         "control functions. Where it states a limit, the limit is a ceiling and not a target; where it states a "
         "process, the process is the minimum and an approver may ask for more. Internal Audit tests compliance with "
         "the Policy as part of its annual plan and reports its findings to the Board Audit Committee.",
    "2": "The four-eyes principle means that no facility is approved by the business alone. The risk signatory is "
         "independent of the business line and of the relationship. Committees meet with a quorum of a majority of "
         "voting members, including the chair or the alternate chair, and record dissent in the minutes. Decisions "
         "taken by circulation are ratified at the next meeting.",
    "3": "The business unit is responsible for the accuracy of the application. Figures are taken from the audited "
         "accounts, the loan origination system and the core banking system and are reconciled before submission. "
         "The Credit Risk division does not correct the application; it records its observations in its opinion and "
         "the business unit answers them.",
    "4": "The criteria are tested on the obligor's audited figures and on the projections in the application. Where "
         "the obligor is part of a group, the criteria are also tested on the group's consolidated accounts. A "
         "projection that relies on a single contract, a single customer or a single asset sale is treated with "
         "caution and is stressed in the application.",
    "5": "When a limit is approached, the Risk Management division notifies the business unit and the Chief Risk "
         "Officer. New exposure that would breach a limit is not approved under delegated authority; it is presented "
         "to the Board Credit Committee with a plan to return within the limit.",
    "6": "Amortisation profiles are set so that the facility is repaid from the cash flow it finances. Grace periods "
         "are justified by the construction or ramp-up period of the project and are documented in the application.",
    "7": "Valuations are performed by valuers on the Bank's approved panel, rotated at least every third valuation. "
         "Insurance over the security is assigned to the Bank and renewed before expiry. Security documents are held "
         "by the Credit Administration unit, which confirms perfection in writing before the first drawdown.",
    "8": "The review is a full credit assessment and not a renewal formality. It covers the obligor's performance "
         "against the projections approved, the covenants, the conduct of the accounts, the security and any change "
         "in ownership, management or auditor. Early warning signals include delays in submitting financial "
         "statements, returned cheques, excesses over limits and adverse news.",
    "9": "Pricing includes the margin, the fees and the commissions on unfunded lines. Relationship returns may be "
         "considered when the ancillary business is documented and has been earned in the last twelve months; "
         "promised business is not counted.",
    "10": "The committee secretary records the questions the committee raised and the answers given. A question left "
          "open is recorded as a condition with an owner and a due date. The Credit Risk division analyses the "
          "questions raised each quarter and shares the recurring ones with the business units.",
}


#: A second paragraph per section: how the clauses are applied in practice (no thresholds).
PRACTICE = {
    "1": "Questions of interpretation are referred to the Credit Risk Policy unit, which answers in writing and keeps a register "
         "of its interpretations. An interpretation that changes how a clause is applied is brought to the next review of the "
         "Policy, so that the text and the practice do not drift apart. Business units do not issue their own guidance on the "
         "Policy; where a product programme needs more detail, the programme is approved under the Policy and refers to it.",
    "2": "The secretary of each committee keeps the attendance, the papers presented, the decision, the conditions and the "
         "dissent of each member. Minutes are circulated for confirmation within a week and are signed by the chair. A "
         "decision is effective when the minutes record it; a facility letter is not issued on the strength of a verbal "
         "approval. The Credit Administration unit checks every facility letter against the approval before it is released.",
    "3": "The application is written for the approver, who may not know the obligor. It states the request plainly, explains "
         "why the Bank should lend, sets out what could go wrong and how the Bank is protected, and ends with a clear "
         "recommendation. It avoids promotional language, states figures with their source and date, and distinguishes the "
         "obligor's own figures from the business unit's projections and from the Credit Risk division's adjustments.",
    "4": "Where an obligor narrowly fails a criterion, the application explains the reason, the trend and the mitigation, "
         "and proposes a covenant or a condition that addresses it. A failure that is structural rather than temporary is "
         "not mitigated by pricing. The Credit Risk division may ask for additional analysis, including sensitivities to the "
         "obligor's main revenue drivers, and records in its opinion whether the mitigation is adequate.",
    "5": "Concentration is assessed at the level of the group, including entities that are not borrowers of the Bank but "
         "whose failure would affect the obligor. Exposure to entities owned or controlled by the same shareholders is "
         "aggregated. Where ownership is unclear, the Bank aggregates until the ownership is evidenced. Sector classification "
         "follows the obligor's main source of revenue and is reviewed at each annual review.",
    "6": "Repayment schedules are agreed with the obligor before approval and are attached to the application. A schedule "
         "that defers most of the repayment to the final instalment is a balloon structure and is assessed as such. Bullet "
         "repayments are acceptable for short-dated trade facilities that are self-liquidating; for term facilities they are "
         "an exception and the application shows how the final repayment will be refinanced or met from cash.",
    "7": "Security that cannot be enforced is not security. Before relying on any item, the Bank confirms that it is legally "
         "enforceable in the jurisdiction where it sits, that the Bank's interest is registered where registration is "
         "possible, and that the asset is insured and maintained. Personal guarantees are supported by a statement of net "
         "worth that is updated at each review. Corporate guarantees are approved by the guarantor's board.",
    "8": "Monitoring is the shared responsibility of the relationship manager and the Credit Risk division. The relationship "
         "manager visits the obligor, reads its accounts and explains its performance; the Credit Risk division tests the "
         "explanation against the data. Disagreement between the two is escalated to the Head of Credit, who records the "
         "outcome. Watchlist obligors are discussed monthly at the Watchlist Committee until they are upgraded or exited.",
    "9": "The pricing model used for every application is the one maintained by the Finance division, with the parameters "
         "approved for the quarter. Manual adjustments to the model's output are not allowed; a different price is proposed "
         "as an exception with its rationale. The Finance division reports the realised return of approved facilities against "
         "the return at approval each half-year.",
    "10": "Committee members prepare by reading the application and the Credit Risk division's opinion before the meeting. "
          "Questions that can be answered before the meeting are sent to the business unit in advance, so that the meeting "
          "is spent on judgement rather than on facts. Where a committee repeatedly asks the same question, the Credit Risk "
          "Policy unit considers whether the application template should answer it by default.",
}


def _commentary(n: str) -> str:
    return COMMENTARY.get(n, "")


def write(out: pathlib.Path = OUT) -> pathlib.Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(_doc_bytes())
    return out


if __name__ == "__main__":  # pragma: no cover
    p = write()
    print(f"wrote {p.relative_to(paths.V5)} ({p.stat().st_size:,} bytes)")
