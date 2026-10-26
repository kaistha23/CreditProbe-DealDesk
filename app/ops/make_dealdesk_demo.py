"""PLAN_R6 D3: the Deal Desk demo pack, written to demo_inputs/deal_desk/.

Nine synthetic Saudi credit applications, each as a long-form Word credit memo
(CP_Demo_DD-2NN_<Obligor>_LongForm.docx) and a short-form Excel sheet
(CP_Demo_DD-2NN_<Obligor>_ShortForm.xlsx). Group members use real connected
group IDs and names from the corporate book (2026Q2), so the demo shows
connected exposure and group-limit effects. All names are synthetic.

    .venv/bin/python ops/make_dealdesk_demo.py          write the pack
    .venv/bin/python ops/make_dealdesk_demo.py --check  write, read back every file and run the engine
"""
from __future__ import annotations

import json
import pathlib
import sys

V5 = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V5))
OUT = V5 / "demo_inputs" / "deal_desk"

FAC = {"term_loan": "Term finance", "revolver": "Revolving working capital", "performance_lg": "Performance letter of guarantee",
       "trade_lc": "Trade letter of credit"}

CASES: list[dict] = [
    dict(id="DD-201", slug="AlKhobarModernLogistics", name="Al Khobar Modern Logistics Company", cr="2051048817",
         group="Al Khobar Modern Logistics Group (CG9317-006)", sector="Transport and Logistics", region="Eastern Province",
         rating="A-", ext="A- (Fitch)", simah="clear", rm="Khalid Al-Otaibi", facility="term_loan", structure="murabaha", ccy="SAR",
         amount=60, tenor=5, grace=1, repay="equal", margin=260, fee=75, commit=25,
         fin=[(410, 82, 31, 150, 38, 260, 70, 25, 9), (455, 93, 36, 140, 44, 290, 78, 30, 8.5), (502, 104, 41, 135, 52, 325, 88, 32, 8)],
         coll=("real estate", 55, "2026-06-30"), guar=("corporate", "Al Khobar Modern Logistics Group holding company", 100),
         dscr=1.5, lev=3.0, cash_margin=0, purpose="Fleet expansion: 120 refrigerated trucks for the Dammam-Riyadh corridor",
         case="Group member that clears easily: strong rating, secured, parent guarantee."),
    dict(id="DD-202", slug="RawabiIndustrialWorks", name="Rawabi Industrial Works Fabrication Company", cr="2050771230",
         group="Rawabi Industrial Works Group CG1277 (CG1277)", sector="Manufacturing", region="Eastern Province",
         rating="BBB", ext="", simah="clear", rm="Sara Al-Dosari", facility="term_loan", structure="tawarruq", ccy="SAR",
         amount=150, tenor=6, grace=1, repay="equal", margin=240, fee=60, commit=25,
         fin=[(980, 150, 52, 520, 95, 610, 160, 70, 34), (1040, 162, 58, 540, 104, 650, 172, 75, 36), (1110, 176, 63, 560, 110, 700, 185, 80, 38)],
         coll=("plant and equipment", 90, "2026-05-15"), guar=None, dscr=1.3, lev=3.5, cash_margin=0,
         purpose="New steel fabrication line at Jubail",
         case="Group member that breaches the SAR 500m connected-group limit: the group already holds SAR 662m."),
    dict(id="DD-203", slug="NajdCentralEngineering", name="Najd Central Engineering Contracting Company", cr="1010458812",
         group="Najd Central Engineering Group (CG6292-119)", sector="Construction", region="Riyadh",
         rating="BB", ext="", simah="clear", rm="Abdullah Al-Zahrani", facility="term_loan", structure="murabaha", ccy="SAR",
         amount=45, tenor=5, grace=0, repay="equal", margin=270, fee=40, commit=20,
         fin=[(320, 41, 12, 120, 22, 140, 30, 18, 9), (345, 44, 13, 125, 20, 150, 33, 20, 9.5), (372, 48, 15, 128, 24, 162, 36, 22, 10)],
         coll=None, guar=None, dscr=None, lev=None, cash_margin=0, purpose="Working capital and equipment for a Ministry of Housing contract",
         case="Below the hurdle as asked (unsecured, thin margin); fixable with collateral or a guarantee. No security or covenants stated: the thread asks for them."),
    dict(id="DD-204", slug="TabukDatesProcessing", name="Tabuk Dates Processing Company", cr="3550120944",
         group="", sector="Agriculture and Agri-processing", region="Tabuk",
         rating="BBB+", ext="BBB+ (S&P)", simah="clear", rm="Khalid Al-Otaibi", facility="term_loan", structure="murabaha", ccy="SAR",
         amount=35, tenor=4, grace=0, repay="equal", margin=230, fee=60, commit=20,
         fin=[(190, 38, 18, 55, 21, 160, 34, 9, 3), (212, 43, 21, 52, 26, 178, 39, 11, 2.8), (236, 48, 24, 50, 30, 198, 44, 12, 2.6)],
         coll=("receivables", 20, "2026-06-30"), guar=None, dscr=1.4, lev=2.5, cash_margin=0,
         purpose="Packing plant upgrade and cold storage", case="New to bank, clears comfortably."),
    dict(id="DD-205", slug="JazanColdChainLeasing", name="Jazan Cold Chain Services Company", cr="5900033712",
         group="", sector="Transport and Logistics", region="Jazan",
         rating="BBB-", ext="", simah="clear", rm="Sara Al-Dosari", facility="term_loan", structure="ijara", ccy="SAR",
         amount=70, tenor=6, grace=1, repay="equal", margin=240, fee=50, commit=20,
         fin=[(150, 33, 11, 95, 14, 110, 27, 30, 6), (171, 38, 13, 105, 17, 121, 31, 34, 6.5), (190, 42, 15, 112, 19, 134, 35, 36, 7)],
         coll=None, guar=None, dscr=1.25, lev=3.5, cash_margin=0,
         purpose="Ijara over a new cold-chain warehouse at Jazan port (asset to be identified)",
         case="Islamic structure (ijara) with no underlying asset pledged: fails the structure rule until an asset is identified."),
    dict(id="DD-206", slug="TuwaiqModernProperties", name="Tuwaiq Modern Properties Development Company", cr="1010699301",
         group="Tuwaiq Modern Properties Group (CG3425-011)", sector="Real Estate", region="Riyadh",
         rating="BB+", ext="", simah="clear", rm="Abdullah Al-Zahrani", facility="term_loan", structure="musharaka", ccy="SAR",
         amount=180, tenor=7, grace=2, repay="balloon", margin=280, fee=80, commit=25,
         fin=[(260, 70, 30, 310, 25, 520, 40, 120, 18), (290, 78, 34, 340, 28, 560, 46, 140, 20), (318, 86, 37, 365, 31, 600, 52, 150, 22)],
         coll=("real estate", 240, "2026-04-30"), guar=None, dscr=1.2, lev=4.0, cash_margin=0,
         purpose="Mixed-use development, north Riyadh",
         case="Breaches a sector limit (real estate is already over its 10% risk-appetite cap) and, with the group's SAR 322m, the SAR 500m connected-group limit."),
    dict(id="DD-207", slug="TaifFirstLogistics", name="Taif First Logistics Company", cr="4032217765",
         group="Taif First Logistics Group (CG9317-018)", sector="Transport and Logistics", region="Makkah",
         rating="BBB", ext="", simah="clear", rm="Khalid Al-Otaibi", facility="revolver", structure="murabaha", ccy="SAR",
         amount=40, tenor=3, grace=0, repay="bullet", margin=200, fee=30, commit=30,
         fin=[(280, 46, 17, 110, 19, 190, 40, 14, 7), (301, 50, 19, 115, 22, 205, 44, 15, 7.5), (325, 54, 21, 118, 25, 220, 47, 16, 8)],
         coll=("receivables", 25, "2026-06-30"), guar=None, dscr=1.3, lev=3.0, cash_margin=0,
         purpose="Seasonal working capital for Hajj logistics", case="Group member: connected exposure shown; revolving facility."),
    dict(id="DD-208", slug="QassimSpecialistHealthcare", name="Qassim Specialist Healthcare Company", cr="1131055420",
         group="", sector="Healthcare", region="Qassim",
         rating="BB-", ext="", simah="clear", rm="Sara Al-Dosari", facility="term_loan", structure="murabaha", ccy="SAR",
         amount=50, tenor=5, grace=1, repay="equal", margin=250, fee=50, commit=20,
         fin=[(140, 26, 8, 70, 12, 90, 22, 18, 4), (158, 30, 10, 74, 14, 99, 25, 20, 4.2), (176, 34, 12, 78, 16, 110, 29, 22, 4.4)],
         coll=None, guar=("kafalah", "Kafalah SME guarantee programme", 80), dscr=1.25, lev=3.5, cash_margin=0,
         purpose="New 80-bed specialist wing", case="New to bank, sub-investment grade; a Kafalah guarantee carries it over the hurdle."),
    dict(id="DD-209", slug="WadiHanifahTechnologies", name="Wadi Hanifah Technologies Company", cr="1010812276",
         group="Wadi Hanifah Technologies Group (CG1191-011)", sector="Information Technology", region="Riyadh",
         rating="BBB-", ext="", simah="clear", rm="Abdullah Al-Zahrani", facility="performance_lg", structure="conventional", ccy="SAR",
         amount=30, tenor=2, grace=0, repay="bullet", margin=0, fee=25, commit=0, commission=120,
         fin=[(230, 35, 14, 60, 30, 120, 30, 8, 3), (262, 40, 17, 62, 34, 135, 34, 9, 3.1), (295, 46, 20, 64, 39, 152, 39, 10, 3.2)],
         coll=("cash", 6, "2026-06-30"), guar=None, dscr=1.3, lev=2.5, cash_margin=20,
         purpose="Performance guarantees for a government digital-services contract",
         case="Unfunded facility (performance LG) for a group member, with a 20% cash margin."),
]
# Calibration for the intended case mix: EBITDA up and debt down where only the limit or structure test should bind.
_TUNE = {"DD-202": (1.5, 0.85), "DD-203": (1.6, 0.75), "DD-205": (1.7, 0.7), "DD-206": (1.8, 0.8), "DD-208": (1.6, 0.75)}
for _c in CASES:
    e, dbt = _TUNE.get(_c["id"], (1.0, 1.0))
    _c["fin"] = [(r[0], round(r[1] * e), r[2], round(r[3] * dbt), *r[4:]) for r in _c["fin"]]
CASES[6]["case"] = "Group member with connected exposure; just below the hurdle as asked, fixable with a few bps of margin; revolving facility."
YEARS = ["2023", "2024", "2025"]
FIN_ROWS = ["Revenue", "EBITDA", "Net income", "Total debt", "Cash and equivalents", "Net worth (equity)", "Operating cash flow",
            "Capital expenditure", "Interest expense"]


def _margin(c: dict) -> str:
    return f"{'SOFR' if c['ccy'] == 'USD' else 'SAIBOR'} + {c['margin']} bps"


def _debt_service(c: dict, y: int) -> float:
    f = c["fin"][y]
    return round(f[8] + f[3] / 6, 1)


def short_rows(c: dict) -> list[tuple[str, object]]:
    f = c["fin"][-1]
    rows: list[tuple[str, object]] = [
        ("Obligor", c["name"]), ("CR number", c["cr"]), ("Group", c["group"] or "None (new to bank)"), ("Sector", c["sector"]),
        ("Region", c["region"]), ("Internal rating", c["rating"]), ("External rating", c["ext"] or "Unrated"), ("SIMAH", c["simah"]),
        ("Relationship manager", c["rm"]), ("Purpose", c["purpose"]),
        ("Facility", FAC[c["facility"]]), ("Structure", c["structure"].capitalize()), ("Currency", c["ccy"]),
        ("Amount (million)", c["amount"]), ("Tenor (years)", c["tenor"]), ("Grace (years)", c["grace"]), ("Repayment", c["repay"]),
        ("Margin (bps)", c["margin"]), ("Upfront fee (bps)", c["fee"]), ("Commitment fee (bps)", c["commit"]),
        ("Commission (bps)", c.get("commission", 0)), ("Cash margin (%)", c["cash_margin"]),
        ("Revenue (million)", f[0]), ("EBITDA (million)", f[1]), ("Total debt (million)", f[3]),
        ("Debt service (million)", _debt_service(c, 2)), ("Net worth (million)", f[5]), ("Current ratio", 1.3),
        ("Collateral type", c["coll"][0] if c["coll"] else "None offered"),
        ("Collateral value (million)", c["coll"][1] if c["coll"] else "None"),
        ("Guarantee type", c["guar"][0] if c["guar"] else "None offered"), ("Guarantor", c["guar"][1] if c["guar"] else "None"),
        ("Guarantee cover (%)", c["guar"][2] if c["guar"] else "None"),
        ("DSCR minimum (x)", c["dscr"] if c["dscr"] else "None proposed"),
        ("Debt/EBITDA maximum (x)", c["lev"] if c["lev"] else "None proposed"),
    ]
    return rows


def write_xlsx(c: dict, path: pathlib.Path) -> None:
    import openpyxl
    from openpyxl.styles import Font, PatternFill
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Short form"
    ws["A1"] = f"CreditProbe demo · Short-form credit application · {c['id']}"
    ws["A1"].font = Font(bold=True, size=13)
    ws["A2"] = "Synthetic demo data, not client data. SAR million unless stated."
    ws["A2"].font = Font(italic=True, color="666666")
    r = 4
    for label, value in short_rows(c):
        ws.cell(r, 1, label).font = Font(bold=True)
        ws.cell(r, 1).fill = PatternFill("solid", fgColor="F4EFE6")
        ws.cell(r, 2, value)
        r += 1
    ws.column_dimensions["A"].width = 30
    ws.column_dimensions["B"].width = 62
    wb.save(path)


def write_docx(c: dict, path: pathlib.Path) -> None:
    from docx import Document
    from docx.shared import Pt
    d = Document()
    d.styles["Normal"].font.name = "Calibri"
    d.styles["Normal"].font.size = Pt(10.5)

    def table(header: list[str], rows: list[list[object]]) -> None:
        t = d.add_table(rows=1, cols=len(header))
        t.style = "Light Grid Accent 1"
        for i, h in enumerate(header):
            t.rows[0].cells[i].text = h
        for row in rows:
            cells = t.add_row().cells
            for i, v in enumerate(row):
                cells[i].text = f"{v:,.1f}" if isinstance(v, float) else str(v)
        d.add_paragraph()

    def prose(*paras: str) -> None:
        for p in paras:
            d.add_paragraph(p)

    f = c["fin"]
    d.add_heading(f"Credit application · {c['name']}", 0)
    prose(f"Reference {c['id']} · Corporate Banking · prepared by {c['rm']} · October 2026",
          "Synthetic demo data for CreditProbe. Not client data. Amounts in SAR million unless stated.")

    d.add_heading("1. Executive summary", 1)
    sec = (f"secured by {c['coll'][0]} valued at SAR {c['coll'][1]} million" if c["coll"] else "offered on an unsecured basis")
    if c["guar"]:
        sec += f", with a {c['guar'][0]} guarantee from {c['guar'][1]} covering {c['guar'][2]}%"
    prose(f"The relationship team requests a {FAC[c['facility']].lower()} of {c['ccy']} {c['amount']} million over {c['tenor']} years "
          f"for {c['name']}, priced at {_margin(c)} with a {c['fee']} bps upfront fee, {sec}. The purpose is {c['purpose'].lower()}.",
          f"The obligor is rated {c['rating']} on the internal scale. Revenue grew from SAR {f[0][0]} million in {YEARS[0]} to "
          f"SAR {f[2][0]} million in {YEARS[2]}, and EBITDA from SAR {f[0][1]} million to SAR {f[2][1]} million. "
          "The team recommends approval subject to the conditions in section 10.")
    table(["Item", "Detail"], [["Obligor", c["name"]], ["CR number", c["cr"]], ["Group", c["group"] or "None (new to bank)"],
                               ["Sector", c["sector"]], ["Region", c["region"]], ["Internal rating", c["rating"]],
                               ["External rating", c["ext"] or "Unrated"], ["SIMAH", c["simah"]], ["Relationship manager", c["rm"]]])

    d.add_heading("2. Background", 1)
    prose(f"{c['name']} was incorporated under commercial registration {c['cr']} and operates from {c['region']}. "
          f"It is active in {c['sector'].lower()}, serving government-linked and private customers across the Kingdom.",
          "The company has grown steadily under Vision 2030 programmes, with a stable customer base, contracted revenue for the next "
          "two years and a clean SIMAH record. The bank first met the company through its trade finance needs; this request would "
          "make the bank one of its two main lenders.",
          "Operations are organised in three divisions, each with its own budget and monthly reporting to the board. Audited "
          "statements for the last three years carry clean opinions from a top-ten audit firm.")

    d.add_heading("3. Group structure", 1)
    if c["group"]:
        prose(f"The obligor is a member of {c['group']}, an existing connected group in the bank's corporate book. "
              "Exposure to the group is aggregated for the connected-group limit (CP-1.2) and the large-exposure limit.",
              "The holding company owns 100% of the obligor; sister companies bank with us on working-capital and trade lines. "
              "Connected parties are identified under the bank's related-party policy.")
        table(["Ownership", "Share"], [["Holding company", "100%"], ["Ultimate beneficial owners (family)", "100% of the holding"]])
    else:
        prose("The obligor is new to the bank and is not part of a group in the corporate book. Ownership is held by the founding "
              "family (70%) and a regional private-equity fund (30%). No connected parties hold facilities with the bank.")

    d.add_heading("4. Management", 1)
    prose("The chief executive has led the company for twelve years and previously held senior roles in a listed peer. The chief "
          "financial officer joined four years ago from a Big Four firm and introduced monthly management accounts and a treasury policy.",
          "The board has five members, two of them independent, and an audit committee that meets quarterly. Succession planning "
          "is documented for the top three roles.")

    d.add_heading("5. Industry", 1)
    prose(f"The {c['sector'].lower()} sector in Saudi Arabia benefits from public investment under Vision 2030 and from the growth "
          "of non-oil GDP. Competition is fragmented; larger players with scale and certification have pricing power.",
          "Key risks are payment delays from public-sector customers, input-cost inflation and concentration in a few large contracts. "
          "The bank's book holds the sector within its risk-appetite caps; the analysis tests the deal's effect on those caps.")

    d.add_heading("6. Financials", 1)
    prose("Audited figures, SAR million. The latest actual year is used for the covenant tests.")
    table(["SAR million"] + YEARS, [[lab] + [float(f[y][i]) for y in range(3)] for i, lab in enumerate(FIN_ROWS)]
          + [["Debt service"] + [_debt_service(c, y) for y in range(3)], ["Current ratio", 1.2, 1.25, 1.3]])
    prose(f"Debt/EBITDA stands at {f[2][3] / f[2][1]:.2f}x in {YEARS[2]}. Operating cash flow covers capital expenditure in every year.")

    d.add_heading("7. Facility requested", 1)
    table(["Term", "Requested"], [
        ["Facility", FAC[c["facility"]]], ["Structure", c["structure"].capitalize()], ["Currency", c["ccy"]],
        ["Amount", f"{c['ccy']} {c['amount']} million"], ["Tenor", f"{c['tenor']} years"], ["Grace", f"{c['grace']} years"],
        ["Repayment", c["repay"]], ["Margin", _margin(c)], ["Upfront fee", f"{c['fee']} bps"],
        ["Commitment fee", f"{c['commit']} bps"], ["Commission", f"{c.get('commission', 0)} bps"],
        ["Cash margin", f"{c['cash_margin']}%"]])
    prose(f"Purpose: {c['purpose']}.")

    d.add_heading("8. Security", 1)
    rows: list[list[object]] = []
    if c["coll"]:
        rows += [["Collateral type", c["coll"][0]], ["Collateral value", f"SAR {c['coll'][1]} million"],
                 ["Valuation date", c["coll"][2]], ["LTV", f"{c['amount'] / c['coll'][1] * 100:.0f}%"]]
    else:
        rows += [["Collateral type", "None offered"]]
    if c["guar"]:
        rows += [["Guarantee type", c["guar"][0]], ["Guarantor", c["guar"][1]], ["Guarantee cover", f"{c['guar'][2]}%"]]
    else:
        rows += [["Guarantee type", "None offered"]]
    table(["Item", "Detail"], rows)

    d.add_heading("9. Covenants and conditions", 1)
    cov = [["DSCR minimum", f"{c['dscr']}x" if c["dscr"] else "None proposed"],
           ["Debt/EBITDA maximum", f"{c['lev']}x" if c["lev"] else "None proposed"]]
    table(["Covenant", "Threshold"], cov)
    prose("Conditions precedent: board resolution, audited statements, Shariah sign-off on the documentation where Islamic, "
          "perfection of any security before first drawdown. Reporting: quarterly management accounts, annual audited statements.")

    d.add_heading("10. Risk assessment and recommendation", 1)
    prose("Strengths: contracted revenue, experienced management, conservative leverage for the sector.",
          "Weaknesses: customer concentration, working-capital intensity, exposure to public-sector payment cycles.",
          "Mitigants: the security and covenants above, quarterly monitoring, and a cash sweep on any contract award above plan.",
          f"Recommendation: approve the {FAC[c['facility']].lower()} of {c['ccy']} {c['amount']} million on the terms above, subject to "
          "the risk-adjusted return clearing the hurdle and every hard limit after the deal.")
    for _ in range(2):  # supporting appendix pages (6-10 page memo)
        d.add_page_break()
        d.add_heading("Appendix: site visit and account conduct", 1)
        prose("The relationship manager visited the main operating site in September 2026. Facilities were well maintained, "
              "safety certifications were current and the order book was evidenced by signed contracts.",
              "Account conduct with existing banks is satisfactory, with no excesses or returned cheques in the last 24 months. "
              "Trade lines are used at 60-70% on average with seasonal peaks in the fourth quarter.",
              "The finance team provided a 24-month cash-flow forecast; the base case shows comfortable coverage, and a downside case "
              "with a 15% revenue fall keeps coverage above the proposed covenant.")
    d.save(path)


def main(check: bool) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = []
    for c in CASES:
        stem = f"CP_Demo_{c['id']}_{c['slug']}"
        write_docx(c, OUT / f"{stem}_LongForm.docx")
        write_xlsx(c, OUT / f"{stem}_ShortForm.xlsx")
        manifest.append({"id": c["id"], "obligor": c["name"], "group": c["group"] or None, "case": c["case"],
                         "files": [f"{stem}_LongForm.docx", f"{stem}_ShortForm.xlsx"]})
    (OUT / "manifest.json").write_text(json.dumps({"origin": "SYNTHETIC_DEMO", "not_client_data": True, "cases": manifest}, indent=1))
    if check:
        from backend.dealdesk_thread import engine, ingest
        for m in manifest:
            for fn in m["files"]:
                r = ingest.extract((OUT / fn).read_bytes(), fn)
                vals = {f["field"]: f["value"] for f in r["fields"] if f["value"] is not None}
                prop = engine.post("/proposals", ingest.proposal_from_fields(vals, {"filename": fn}))["proposal"]
                res = engine.post("/compute", {"proposal_id": prop["proposal_id"]})
                mt = res["metrics"]
                hard = [x["label"] for x in res["constraints"] if x["status"] == "breach" and x["kind"] == "hard"]
                soft = [x["label"] for x in res["constraints"] if x["status"] == "breach" and x["kind"] == "soft"]
                print(f"{fn}: {r['summary']}; RAROC {mt['lifetime_raroc']:.2%} vs {mt['hurdle']:.0%}; "
                      f"hard: {hard or 'none'}; soft: {soft or 'none'}; group {prop['obligor']['group_id'] or '-'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main("--check" in sys.argv))
