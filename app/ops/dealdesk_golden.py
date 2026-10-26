"""Write the Deal Desk golden workbook: tests/dealdesk/golden_deals.xlsx.

    python3 ops/dealdesk_golden.py

Five deals (funded revolver, unfunded LG, Ijara, guaranteed SME, amortising with balloon), one sheet
each. The inputs block holds the deal terms and the parameter values (as values, each labelled with
its parameter table); every result line is an Excel formula on those inputs, written independently
of backend/dealdesk/engine.py. The PD term structure is an input: it comes from the XGBoost model,
which Excel cannot evaluate (its reproduction is a separate test). LibreOffice recalculates the file
so it carries computed values; tests/dealdesk/test_golden.py checks the engine against them.
"""
from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import tempfile

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

V5 = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V5))

from backend.dealdesk import engine, params, pd_model, proposals  # noqa: E402

OUT = V5 / "tests" / "dealdesk" / "golden_deals.xlsx"
DEALS = [("DD-06", "Funded revolver"), ("DD-09", "Unfunded performance LG"), ("DD-08", "Ijara"),
         ("DD-10", "Guaranteed (Kafalah) SME"), ("DD-04", "Amortising with balloon")]
#: R5 D4: cases that move non-margin levers (sheet, proposal, title, terms over the ask)
LEVER_CASES = [
    ("L1 DD-02 fees", "DD-02", "Upfront fee 125 bps and prepayment fee 100 bps", {"upfront_fee_bps": 125, "prepayment_fee_bps": 100}),
    ("L2 DD-02 guarantee", "DD-02", "Export credit agency cover 50% (requested protection)", {"guarantee_id": "REQ-ECA", "guarantee_coverage_pct": 50}),
    ("L3 DD-02 cash margin", "DD-02", "Cash margin 20%", {"cash_margin_pct": 20}),
    ("L4 DD-02 sculpted", "DD-02", "Sculpted amortisation after one grace year", {"amortisation": "sculpted"}),
    ("L5 DD-03 sell-down", "DD-03", "Hold 70%: 30% sold down, arranger skim on the sold share", {"hold_pct": 70}),
]
HEAD = PatternFill("solid", fgColor="10527A")
INPUT = PatternFill("solid", fgColor="FBF0DC")


def inputs_for(pid: str, terms: dict | None = None) -> tuple[list[tuple[str, str, object, str]], dict]:
    """(key, label, value, source) for every input, and the engine analysis for the same terms."""
    p = proposals.get(pid)
    a = engine.analyse(p, terms)
    t = a["terms"]
    P = params.current()
    lg, ccf, rw, cap, ftp, opx, ret = (P[k]["rows"] for k in ("lgd", "ccf", "sa_risk_weights", "capital", "ftp", "opex", "returns"))
    cov = P["covenant_packages"]["rows"]["packages"][t["covenant_package"]]
    ftype = t["facility_type"]
    unf = ftype in engine.UNFUNDED
    utype = ftype if unf else t["unfunded_type"]
    T = int(t["tenor_years"])
    bal = 1.0 if t["amortisation"] == "bullet" else t["balloon_pct"] / 100 if t["amortisation"] == "balloon" else 0.0
    seg = "gre" if p["obligor"].get("gre") else "sme" if p["obligor"].get("sme") else "corporate"
    g = a["lgd"]["guarantee"]
    pb = P["pricing_behaviour"]["rows"]
    rows = [
        ("A", "Amount held (SAR m)", t["amount"] * a["fx_to_sar"] * t["hold_pct"] / 100, "terms.amount x fx x hold_pct"),
        ("AFULL", "Facility amount (SAR m)", t["amount"] * a["fx_to_sar"], "terms.amount x fx"),
        ("SKIM", "Arranger skim on the sold-down share", pb["arranger_skim_bps"] / 1e4, "pricing_behaviour.arranger_skim_bps"),
        ("PFEE", "Prepayment fee", t["prepayment_fee_bps"] / 1e4, "terms.prepayment_fee_bps"),
        ("CPR", "Expected prepayment rate p.a. (term loans)", a["rates"]["prepayment_cpr"], "pricing_behaviour.prepayment_cpr"),
        ("SCULPT", "Sculpted amortisation (1) or not (0)", 1 if t["amortisation"] == "sculpted" else 0, "terms.amortisation"),
        ("SG", "Sculpting growth", pb["sculpt_growth"], "pricing_behaviour.sculpt_growth"),
        ("T", "Tenor (years)", T, "terms.tenor_years"), ("G", "Grace (years)", t["grace_years"], "terms.grace_years"),
        ("TERM", "Term loan (1) or revolver/unfunded (0)", 1 if ftype == "term_loan" else 0, "terms.facility_type"),
        ("BAL", "Balloon share", bal if ftype == "term_loan" else 0.0, "terms.amortisation / balloon_pct"),
        ("FS", "Funded share", 0.0 if unf else t["funded_share_pct"] / 100, "terms.funded_share_pct"),
        ("U", "Utilisation / usage", t["utilisation_pct"] / 100, "terms.utilisation_pct"),
        ("MRG", "Margin", t["margin_bps"] / 1e4, "terms.margin_bps"), ("UPF", "Upfront fee", t["upfront_fee_bps"] / 1e4, "terms.upfront_fee_bps"),
        ("CMF", "Commitment fee", t["commitment_fee_bps"] / 1e4, "terms.commitment_fee_bps"),
        ("COM", "LG/LC commission", t["commission_bps"] / 1e4, "terms.commission_bps"),
        ("CASH", "Cash margin share", t["cash_margin_pct"] / 100, "terms.cash_margin_pct"),
        ("CCFUE", "CCF undrawn (economic)", ccf["undrawn_committed"]["economic"], "ccf"),
        ("CCFOE", "CCF unfunded (economic)", ccf[utype]["economic"], f"ccf.{utype}"),
        ("CCFUR", "CCF undrawn (regulatory)", ccf["undrawn_committed"]["regulatory"], "ccf"),
        ("CCFOR", "CCF unfunded (regulatory)", ccf[utype]["regulatory"], f"ccf.{utype}"),
        ("FLOOR", "LGD floor", lg["floor"], "lgd.floor"), ("LGDU", "Unsecured LGD", lg["unsecured"]["senior"], "lgd.unsecured.senior"),
        ("STR", "Structure multiplier", lg["structure"][t["structure"]], f"lgd.structure.{t['structure']}"),
        ("COVL", "Covenant LGD multiplier", cov["lgd_multiplier"], "covenant_packages"),
        ("COVP", "Covenant PD multiplier", cov["pd_multiplier"], "covenant_packages"),
        ("RR", "Recovery discount rate", lg["recovery_discount_rate"], "lgd.recovery_discount_rate"),
    ]
    for i, c in enumerate(a["lgd"]["collateral"], start=1):
        rows += [(f"CV{i}", f"Collateral {c['collateral_id']} value (SAR m)", c["value_sar_mn"], "security.collateral"),
                 (f"CH{i}", f"Collateral {c['collateral_id']} haircut", c["haircut"], f"lgd.collateral.{c['type']}"),
                 (f"CY{i}", f"Collateral {c['collateral_id']} recovery years", c["recovery_years"], f"lgd.collateral.{c['type']}")]
    rows += [
        ("TTC", "TTC PD (master scale)", a["pd"]["ttc_pd"], "pd_master_scale"),
        ("C", "Guarantee coverage", g["coverage"] if g else 0.0, "terms.guarantee_coverage_pct"),
        ("GLGD", "Guarantor LGD", g["lgd"] if g else 0.0, "lgd.guarantor_lgd"),
        ("GTTC", "Guarantor TTC PD", pd_model.master_pd(g["rating"]) if g else 0.0, "pd_master_scale"),
        ("RW", "Obligor risk weight", a["capital"]["rw_obligor"], "sa_risk_weights"),
        ("RWG", "Guarantor risk weight (blank = not eligible)", (g["sa_rw"] if g and g["sa_rw"] is not None else ""), "sa_risk_weights.guarantor"),
        ("FXH", "FX mismatch haircut on cash (cash margin is in the deal currency)", 0.0, "sa_risk_weights"),
        ("CR", "Capital ratio target", cap["capital_ratio_target"], "capital"), ("ALPHA", "Operational risk alpha", cap["operational"]["alpha"], "capital"),
        ("RMIN", "IRB correlation at high PD", cap["economic"]["correlation_min"], "capital.economic"),
        ("RMAX", "IRB correlation at low PD", cap["economic"]["correlation_max"], "capital.economic"),
        ("RK", "IRB correlation decay k", cap["economic"]["correlation_k"], "capital.economic"),
        ("PDF", "IRB PD floor", cap["economic"]["pd_floor"], "capital.economic"),
        ("CONF", "Economic capital confidence", cap["economic"]["confidence"], "capital.economic"),
        ("BASE", "Base rate (3M)", a["rates"]["base"], "ftp.base"), ("LP", "Liquidity premium at tenor", a["rates"]["liquidity_premium"], "ftp.liquidity_premium_bps"),
        ("CBU", "Contingent charge on undrawn", ftp["contingent_bps"]["undrawn_committed"] / 1e4, "ftp.contingent_bps"),
        ("CBO", "Contingent charge on unfunded", ftp["contingent_bps"][utype] / 1e4, "ftp.contingent_bps"),
        ("OFIX", "Origination cost fixed (SAR m)", opx[seg]["origination_fixed"], f"opex.{seg}"),
        ("OBPS", "Origination cost on amount", opx[seg]["origination_bps"] / 1e4, f"opex.{seg}"),
        ("SFIX", "Servicing cost fixed p.a. (SAR m)", opx[seg]["servicing_fixed"], f"opex.{seg}"),
        ("SBPS", "Servicing cost on exposure p.a.", opx[seg]["servicing_bps"] / 1e4, f"opex.{seg}"),
        ("CMON", "Covenant monitoring p.a. (SAR m)", opx["covenant_monitoring"][t["covenant_package"]], "opex.covenant_monitoring"),
        ("CBR", "Return credited on capital", ret["capital_benefit_rate"], "returns"),
        ("Z", "Zakat rate", ret["zakat_rate"], "returns"), ("H", "Hurdle rate", a["hurdle"], "returns"),
    ]
    marg = [r["model_marginal"] for r in a["pd"]["term_structure"]]
    gpd = list(engine.guarantor_pd(g["rating"], T)) if g else [0.0] * T
    q = list(pd_model.stage2_probability(a["pd"]["rating_used"], T))
    return rows, {"analysis": a, "marg": marg, "gpd": gpd, "T": T, "ncoll": len(a["lgd"]["collateral"]), "stage2": q,
                  "guaranteed": bool(g)}


def write_sheet(wb: Workbook, pid: str, title: str, sheet: str | None = None, terms: dict | None = None) -> None:
    ws = wb.create_sheet(sheet or pid)
    rows, ctx = inputs_for(pid, terms)
    T = ctx["T"]
    ws["A1"] = f"{sheet or pid}: {title}" + (f" (terms over the ask: {terms})" if terms else "")
    ws["A1"].font = Font(bold=True, size=13, color="10527A")
    ws["A2"] = "Inputs (shaded) are values; every other cell is a formula on them. SAR million."
    ref: dict[str, str] = {}
    r0 = 4
    for i, (k, label, v, src) in enumerate(rows):
        r = r0 + i
        ws.cell(r, 1, label)
        c = ws.cell(r, 2, v)
        c.fill = INPUT
        ws.cell(r, 3, src).font = Font(color="5B6673", size=9)
        ref[k] = f"$B${r}"
    # year table
    y0 = r0 + len(rows) + 2
    lines = ["Year", "Model marginal PD", "Guarantor marginal PD", "Drawn (start of year)", "Principal", "Undrawn",
             "Unfunded outstanding", "EAD", "Collateral recognised", "LGD", "PD (after covenant)", "Expected loss",
             "SA exposure", "SA exposure net of cash", "RWA", "Regulatory capital", "Maturity", "K obligor", "K guarantor",
             "Economic capital", "Profit income", "Fee income", "Commitment fee", "Commission", "FTP", "Opex",
             "Gross income", "Operational capital", "Capital", "Capital benefit", "Pre-zakat profit", "Zakat", "RAP",
             "Discount factor"]
    R = {name: y0 + i for i, name in enumerate(lines)}
    for name, r in R.items():
        ws.cell(r, 1, name).font = Font(bold=name in ("EAD", "LGD", "Expected loss", "RWA", "Capital", "RAP"))
    cols = [get_column_letter(4 + j) for j in range(T)]
    first, last = cols[0], cols[-1]
    rec_terms = "+".join(f"{ref[f'CV{i}']}*(1-{ref[f'CH{i}']})*(1+{ref['RR']})^(-{ref[f'CY{i}']})" for i in range(1, ctx["ncoll"] + 1)) or "0"
    F = f"({ref['A']}*{ref['FS']})"
    Uf = f"({ref['A']}*(1-{ref['FS']}))"
    for j, col in enumerate(cols):
        prev = get_column_letter(3 + j)
        c = lambda name: f"{col}{R[name]}"  # noqa: E731
        ws[c("Year")] = j + 1
        ws[c("Year")].fill = HEAD
        ws[c("Year")].font = Font(bold=True, color="FFFFFF")
        ws[c("Model marginal PD")] = ctx["marg"][j]
        ws[c("Model marginal PD")].fill = INPUT
        ws[c("Guarantor marginal PD")] = float(ctx["gpd"][j])
        ws[c("Guarantor marginal PD")].fill = INPUT
        yr = c("Year")
        if j == 0:
            ws[c("Drawn (start of year)")] = f"=IF({ref['TERM']}=1,{F},{F}*{ref['U']})"
        else:
            ws[c("Drawn (start of year)")] = (f"=IF({ref['TERM']}=1,{prev}{R['Drawn (start of year)']}-{prev}{R['Principal']},{F}*{ref['U']})")
        sculpt = (f"{F}*(1+{ref['SG']})^({yr}-{ref['G']}-1)*{ref['SG']}/((1+{ref['SG']})^({ref['T']}-{ref['G']})-1)")
        ws[c("Principal")] = (f"=IF({ref['TERM']}=1,MIN({c('Drawn (start of year)')},IF({yr}>{ref['G']},IF({ref['SCULPT']}=1,{sculpt},"
                              f"{F}*(1-{ref['BAL']})/({ref['T']}-{ref['G']})),0)"
                              f"+IF({yr}={ref['T']},{F}*{ref['BAL']},0)),IF({yr}={ref['T']},{F}*{ref['U']},0))")
        ws[c("Undrawn")] = f"=IF({ref['TERM']}=1,0,{F}*(1-{ref['U']}))"
        ws[c("Unfunded outstanding")] = f"={Uf}*{ref['U']}"
        ws[c("EAD")] = f"={c('Drawn (start of year)')}+{ref['CCFUE']}*{c('Undrawn')}+{ref['CCFOE']}*{c('Unfunded outstanding')}"
        ws[c("Collateral recognised")] = f"={rec_terms}+{ref['A']}*{ref['CASH']}"
        ws[c("LGD")] = (f"=MAX({ref['FLOOR']},IF({c('EAD')}>0,MAX(0,{c('EAD')}-{c('Collateral recognised')})/{c('EAD')},0)"
                        f"*{ref['LGDU']}*{ref['STR']}*{ref['COVL']})")
        ws[c("PD (after covenant)")] = f"={c('Model marginal PD')}*{ref['COVP']}"
        ws[c("Expected loss")] = (f"={c('EAD')}*((1-{ref['C']})*{c('PD (after covenant)')}*{c('LGD')}"
                                  f"+{ref['C']}*MIN({c('PD (after covenant)')}*{c('LGD')},{c('Guarantor marginal PD')}*{ref['GLGD']}))")
        ws[c("SA exposure")] = f"={c('Drawn (start of year)')}+{ref['CCFUR']}*{c('Undrawn')}+{ref['CCFOR']}*{c('Unfunded outstanding')}"
        ws[c("SA exposure net of cash")] = f"=MAX(0,{c('SA exposure')}-{ref['A']}*{ref['CASH']}*(1-{ref['FXH']}))"
        ws[c("RWA")] = (f"={c('SA exposure net of cash')}*IF(AND({ref['RWG']}<>\"\",{ref['C']}>0),(1-{ref['C']})*{ref['RW']}+{ref['C']}*MIN({ref['RW']},{ref['RWG']}),{ref['RW']})")
        ws[c("Regulatory capital")] = f"={c('RWA')}*{ref['CR']}"
        ws[c("Maturity")] = f"=MIN(5,MAX(1,{ref['T']}-{yr}+1))"

        def k(pdref: str, lgdref: str) -> str:
            p_ = f"MAX({ref['PDF']},{pdref})"
            e = f"((1-EXP(-{ref['RK']}*{p_}))/(1-EXP(-{ref['RK']})))"
            rr = f"({ref['RMIN']}*{e}+{ref['RMAX']}*(1-{e}))"
            b = f"((0.11852-0.05478*LN({p_}))^2)"
            return (f"MAX(0,({lgdref}*NORMSDIST((NORMSINV({p_})+SQRT({rr})*NORMSINV({ref['CONF']}))/SQRT(1-{rr}))-{p_}*{lgdref})"
                    f"*(1+({c('Maturity')}-2.5)*{b})/(1-1.5*{b}))")
        ws[c("K obligor")] = "=" + k(ref["TTC"], c("LGD"))
        ws[c("K guarantor")] = f"=IF({ref['C']}>0,{k(ref['GTTC'], ref['GLGD'])},0)"
        ws[c("Economic capital")] = f"={c('EAD')}*((1-{ref['C']})*{c('K obligor')}+{ref['C']}*MIN({c('K obligor')},{c('K guarantor')}))"
        ws[c("Profit income")] = f"={c('Drawn (start of year)')}*({ref['BASE']}+{ref['MRG']})"
        ws[c("Fee income")] = (f"=({ref['UPF']}*{ref['A']}+{ref['SKIM']}*({ref['AFULL']}-{ref['A']}))"
                               f"*({c('Drawn (start of year)')}+{c('Unfunded outstanding')})"
                               f"/(SUM(${first}${R['Drawn (start of year)']}:${last}${R['Drawn (start of year)']})"
                               f"+SUM(${first}${R['Unfunded outstanding']}:${last}${R['Unfunded outstanding']}))"
                               f"+IF({ref['TERM']}=1,{c('Drawn (start of year)')}*{ref['CPR']}*{ref['PFEE']},0)")
        ws[c("Commitment fee")] = f"={c('Undrawn')}*{ref['CMF']}"
        ws[c("Commission")] = f"={c('Unfunded outstanding')}*{ref['COM']}"
        ws[c("FTP")] = (f"={c('Drawn (start of year)')}*({ref['BASE']}+{ref['LP']})+{c('Undrawn')}*{ref['CBU']}"
                        f"+{c('Unfunded outstanding')}*{ref['CBO']}")
        ws[c("Opex")] = (f"={ref['SFIX']}+{ref['SBPS']}*({c('Drawn (start of year)')}+{c('Unfunded outstanding')})+{ref['CMON']}"
                         f"+IF({yr}=1,{ref['OFIX']}+{ref['OBPS']}*{ref['A']},0)")
        ws[c("Gross income")] = f"={c('Profit income')}-{c('FTP')}+{c('Fee income')}+{c('Commitment fee')}+{c('Commission')}"
        ws[c("Operational capital")] = f"={ref['ALPHA']}*MAX(0,{c('Gross income')})"
        ws[c("Capital")] = f"=MAX({c('Regulatory capital')},{c('Economic capital')})+{c('Operational capital')}"
        ws[c("Capital benefit")] = f"={c('Capital')}*{ref['CBR']}"
        ws[c("Pre-zakat profit")] = (f"={c('Profit income')}+{c('Fee income')}+{c('Commitment fee')}+{c('Commission')}-{c('FTP')}"
                                     f"-{c('Opex')}-{c('Expected loss')}+{c('Capital benefit')}")
        ws[c("Zakat")] = f"={ref['Z']}*{c('Pre-zakat profit')}"
        ws[c("RAP")] = f"={c('Pre-zakat profit')}-{c('Zakat')}"
        ws[c("Discount factor")] = f"=(1+{ref['H']})^(-{yr})"
    s0 = R["Discount factor"] + 2
    rng = lambda name: f"${first}${R[name]}:${last}${R[name]}"  # noqa: E731
    results = [("PV risk-adjusted profit", f"=SUMPRODUCT({rng('Discount factor')},{rng('RAP')})"),
               ("PV capital", f"=SUMPRODUCT({rng('Discount factor')},{rng('Capital')})"),
               ("Lifetime RAROC", f"=B{s0}/B{s0 + 1}"),
               ("SVA", f"=SUMPRODUCT({rng('Discount factor')},{rng('RAP')})-{ref['H']}*SUMPRODUCT({rng('Discount factor')},{rng('Capital')})"),
               ("RWA year 1", f"={first}{R['RWA']}"), ("EL year 1", f"={first}{R['Expected loss']}"),
               ("EL lifetime (undiscounted)", f"=SUM({rng('Expected loss')})"), ("LGD year 1", f"={first}{R['LGD']}"),
               ("EAD year 1", f"={first}{R['EAD']}"), ("Capital year 1", f"={first}{R['Capital']}")]
    ws.cell(s0 - 1, 1, "Results").font = Font(bold=True, color="10527A", size=12)
    for i, (label, f) in enumerate(results):
        ws.cell(s0 + i, 1, label).font = Font(bold=True)
        ws.cell(s0 + i, 2, f)
    if not ctx["guaranteed"]:
        _accounting(ws, ctx, ref, R, cols, s0 + len(results) + 2)
    ws.column_dimensions["A"].width = 44
    ws.column_dimensions["B"].width = 16
    ws.column_dimensions["C"].width = 30
    for col in cols:
        ws.column_dimensions[col].width = 13
    ws.freeze_panes = "B4"
    for row in ws.iter_rows():
        for cell in row:
            cell.alignment = Alignment(vertical="center")


def _accounting(ws, ctx: dict, ref: dict, R: dict, cols: list[str], top: int) -> None:
    """The accounting EL view (no guarantee): allowance at the end of year t =
    (1 - q_t) x EL_{t+1} + q_t x sum of EL after t (12-month ECL for Stage 1, lifetime for the expected
    Stage 2 share q_t from the migration matrix); year-t charge = EL_t + allowance_t - allowance_{t-1},
    with the day-one Stage 1 ECL (= EL_1) as the opening allowance charged in year 1."""
    ws.cell(top, 1, "Accounting view").font = Font(bold=True, color="10527A", size=12)
    names = ["Stage 2 probability (end of year)", "Allowance (end of year)", "Allowance change", "Day-one ECL",
             "Credit cost (accounting)", "Pre-zakat profit (accounting)", "Zakat (accounting)", "RAP (accounting)"]
    A = {n: top + 1 + i for i, n in enumerate(names)}
    for n, r in A.items():
        ws.cell(r, 1, n)
    first, last = cols[0], cols[-1]
    el = R["Expected loss"]
    for j, col in enumerate(cols):
        c = lambda n: f"{col}{A[n]}"  # noqa: E731
        nxt = cols[j + 1] if j + 1 < len(cols) else None
        prev = cols[j - 1] if j else None
        ws[c("Stage 2 probability (end of year)")] = float(ctx["stage2"][j])
        ws[c("Stage 2 probability (end of year)")].fill = INPUT
        if nxt is None:
            ws[c("Allowance (end of year)")] = 0
        else:
            q = c("Stage 2 probability (end of year)")
            ws[c("Allowance (end of year)")] = f"=(1-{q})*{nxt}{el}+{q}*SUM({nxt}{el}:${last}${el})"
        ws[c("Day-one ECL")] = f"={first}{el}" if j == 0 else 0
        opening = f"{first}{A['Day-one ECL']}" if j == 0 else f"{prev}{A['Allowance (end of year)']}"
        ws[c("Allowance change")] = f"={c('Allowance (end of year)')}-{opening}"
        ws[c("Credit cost (accounting)")] = f"={col}{el}+{c('Allowance change')}+{c('Day-one ECL')}"
        ws[c("Pre-zakat profit (accounting)")] = f"={col}{R['Pre-zakat profit']}+{col}{el}-{c('Credit cost (accounting)')}"
        ws[c("Zakat (accounting)")] = f"={ref['Z']}*{c('Pre-zakat profit (accounting)')}"
        ws[c("RAP (accounting)")] = f"={c('Pre-zakat profit (accounting)')}-{c('Zakat (accounting)')}"
    rng = lambda r: f"${first}${r}:${last}${r}"  # noqa: E731
    df, capr = rng(R["Discount factor"]), rng(R["Capital"])
    res = top + len(names) + 2
    for i, (label, f) in enumerate([
            ("Lifetime RAROC (accounting)", f"=SUMPRODUCT({df},{rng(A['RAP (accounting)'])})/SUMPRODUCT({df},{capr})"),
            ("SVA (accounting)", f"=SUMPRODUCT({df},{rng(A['RAP (accounting)'])})-{ref['H']}*SUMPRODUCT({df},{capr})"),
            ("Lifetime credit cost (accounting)", f"=SUM({rng(A['Credit cost (accounting)'])})")]):
        ws.cell(res + i, 1, label).font = Font(bold=True)
        ws.cell(res + i, 2, f)


def main() -> int:
    wb = Workbook()
    about = wb.active
    about.title = "About"
    about["A1"] = "CreditProbe Deal Desk: golden deals (hand calculation)"
    about["A1"].font = Font(bold=True, size=14, color="10527A")
    notes = ["Five deals; one sheet each. Inputs are values, every result is an Excel formula.",
             "Economic view: credit cost = PD x LGD x EAD by year. Capital basis: max(regulatory, economic) + operational.",
             "RAROC = PV(RAP) / PV(capital); SVA = PV(RAP - hurdle x capital); PV at the hurdle, end-of-year.",
             "The PD term structure is the XGBoost model's (an input here); the model itself is tested separately.",
             f"Parameter versions: {params.version_tag()}."]
    for i, n in enumerate(notes, start=3):
        about.cell(i, 1, n)
    about.cell(9, 1, "Sheet").font = Font(bold=True)
    about.cell(9, 2, "Case").font = Font(bold=True)
    for i, (pid, title) in enumerate(DEALS, start=10):
        about.cell(i, 1, pid)
        about.cell(i, 2, title)
        write_sheet(wb, pid, title)
    for i, (sheet, pid, title, terms) in enumerate(LEVER_CASES, start=10 + len(DEALS)):
        about.cell(i, 1, sheet)
        about.cell(i, 2, f"{title} (R5: non-margin levers)")
        write_sheet(wb, pid, title, sheet, terms)
    about.column_dimensions["A"].width = 100
    with tempfile.TemporaryDirectory() as d:
        raw = pathlib.Path(d) / "golden_deals.xlsx"
        wb.save(raw)
        outdir = pathlib.Path(d) / "calc"
        r = subprocess.run(["soffice", "--headless", "--calc", "--convert-to", "xlsx:Calc MS Excel 2007 XML", "--outdir", str(outdir), str(raw)],
                           capture_output=True, text=True, timeout=180)
        calc = outdir / "golden_deals.xlsx"
        if not calc.exists():
            print(r.stdout, r.stderr)
            return 1
        OUT.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(calc, OUT)
    print(f"golden workbook -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
