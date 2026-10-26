"""P6 demo data: four short past credit memos of the fictional Sandstone Harbour Bank, two approved with conditions and
two declined, each with the committee's decision, conditions and comments (what the onboarding learns committee
questions from). Every name is invented. `python -m backend.dealdesk.house_style.onboarding.demo_memos` rewrites them
under `data/dealdesk/house_style/onboarding/demo_memos/` (deterministic).
"""
from __future__ import annotations

import datetime as dt
import io
import pathlib
from typing import Any

from backend.dealdesk import paths

OUT = paths.DATA / "house_style" / "onboarding" / "demo_memos"

MEMOS: list[dict[str, Any]] = [
    {"file": "SHB-M01_Qasr_Lumen_Contracting.docx", "title": "Credit proposal: Qasr Lumen Contracting LLC (increase)",
     "decision": "Approved with conditions by the Executive Credit Committee",
     "sections": {
         "Executive summary": ["The business unit requests an increase of the guarantee lines from AED 140m to AED 185m to "
                               "support two new hospital projects. The obligor is an existing client rated BB."],
         "Obligor and group": ["Qasr Lumen Contracting LLC is a mid-sized building contractor owned by its founding family."],
         "Facilities and request": ["Performance guarantees AED 120m, advance payment guarantees AED 45m, overdraft AED 20m."],
         "Financial analysis": ["Revenue AED 610m in FY2025, EBITDA AED 48m; net debt to EBITDA 2.1x."],
         "Risks and mitigants": ["Project execution risk on two hospital projects, mitigated by the contractor's track record."],
         "Recommendation": ["The business unit recommends approval of the increase as requested."],
         "Committee decision and conditions": [
             "Facility letters for the new facilities at other banks to be obtained and reconciled with the AECB report before drawdown.",
             "Cash margin of 10% on all new performance guarantees.",
             "Amounts due from related parties to be subordinated to the Bank's facilities."],
         "Committee comments": [
             "The committee asked how much of the backlog is with a single employer and whether it is verified by the quantity surveyor.",
             "The committee questioned whether repayment survives the stress case with a six-month delay on the larger project."]}},
    {"file": "SHB-M02_Marjan_Vale_Trading.docx", "title": "Credit proposal: Marjan Vale Trading LLC (renewal)",
     "decision": "Approved with conditions by the Chief Risk Officer",
     "sections": {
         "Executive summary": ["Renewal of trade lines of AED 75m for a building materials trader rated BB-."],
         "Obligor and group": ["A trading company with two sister companies under common ownership."],
         "Facilities and request": ["Letters of credit AED 50m, trust receipts AED 25m."],
         "Financial analysis": ["Revenue AED 420m; current ratio 1.15x; leverage 3.2x."],
         "Account conduct and bureau report": ["Turnover routed through the Bank is 55% of revenue against a 70% undertaking."],
         "Recommendation": ["Renew for twelve months."],
         "Committee decision and conditions": [
             "Turnover routing undertaking of 70% to be met within six months, monitored quarterly.",
             "Audited standalone financial statements of the borrower to be submitted, the auditor to be on the approved list.",
             "Due from related parties to be reduced below AED 10m by the next review."],
         "Committee comments": [
             "The committee asked whether the facilities at other banks match the bureau report.",
             "Pricing does not clear the hurdle; the committee asked for a pricing review at renewal."]}},
    {"file": "SHB-M03_Tilal_Orbit_Logistics.docx", "title": "Credit proposal: Tilal Orbit Logistics LLC (new)",
     "decision": "Declined by the Executive Credit Committee",
     "sections": {
         "Executive summary": ["New-to-bank term finance of AED 90m for a warehouse, secured by a mortgage over the property."],
         "Obligor and group": ["A logistics company in its third year of operation."],
         "Facilities and request": ["Term loan AED 90m over 8 years with a 30% balloon."],
         "Financial analysis": ["DSCR 1.05x in the base case; leverage 5.1x."],
         "Security and collateral": ["First-degree mortgage over the warehouse, valued at AED 130m in 2023."],
         "Recommendation": ["The business unit recommends approval."],
         "Committee decision and conditions": [
             "Declined: debt service cover below the policy minimum and the valuation is out of date."],
         "Committee comments": [
             "The committee noted the valuation is older than 24 months and not by an approved valuer.",
             "The committee asked what the DSCR is after the deal under the stress case.",
             "The committee asked for facility letters for the borrowings at other banks."]}},
    {"file": "SHB-M04_Sadaf_Prism_Foods.docx", "title": "Credit proposal: Sadaf Prism Foods LLC (increase)",
     "decision": "Declined by the Chief Risk Officer",
     "sections": {
         "Executive summary": ["Increase of working capital lines from AED 40m to AED 70m for a food processor rated B+."],
         "Obligor and group": ["Owned by a holding company that changed ownership in 2026."],
         "Facilities and request": ["Revolving working capital AED 70m."],
         "Financial analysis": ["Revenue AED 300m; EBITDA margin 6%; the FY2025 audit opinion is qualified."],
         "Recommendation": ["The business unit recommends approval of the increase."],
         "Committee decision and conditions": [
             "Declined pending a re-assessment of the change of ownership (KYC) and an unqualified audit opinion."],
         "Committee comments": [
             "The committee asked how much is due from related parties after the change of ownership.",
             "The committee asked whether the security is perfected and the legal opinion current.",
             "Pricing at 275 bps is below the hurdle for a B+ obligor."]}},
]


def _bytes(m: dict[str, Any]) -> bytes:
    from docx import Document
    d = Document()
    cp = d.core_properties
    cp.author = cp.last_modified_by = "Corporate Banking (fictional)"
    cp.created = cp.modified = dt.datetime(2026, 6, 1)
    cp.revision = 1
    d.add_heading(m["title"], level=0)
    d.add_paragraph(f"Sandstone Harbour Bank PJSC (fictional). Decision: {m['decision']}.")
    for head, paras in m["sections"].items():
        d.add_heading(head, level=1)
        bullets = head.startswith("Committee decision")
        for p in paras:
            d.add_paragraph(p, style="List Bullet" if bullets else None)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def files() -> list[pathlib.Path]:
    return sorted(OUT.glob("SHB-M*.docx"))


def write(out: pathlib.Path = OUT) -> list[pathlib.Path]:
    out.mkdir(parents=True, exist_ok=True)
    res = []
    for m in MEMOS:
        f = out / m["file"]
        f.write_bytes(_bytes(m))
        res.append(f)
    return res


if __name__ == "__main__":  # pragma: no cover
    for f in write():
        print(f"wrote {f.relative_to(paths.V5)}")
