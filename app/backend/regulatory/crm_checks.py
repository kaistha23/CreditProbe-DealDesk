"""CBUAE Credit Risk Management Standards: a deterministic engine of breach checks on the books (PLAN_R7 C3).

Each check is tied to the paragraph of the Standards it tests ("CBUAE CRM Art. 7.8"), states the rule in one line,
and returns one breach per entity (facility, account, or the book) with the measured value, the required value, the
materiality (EAD and ECL, SAR million) and a severity. Read-only on the books; no model call; the same books always
give the same breaches.

Checks (the Standards' rules that the books' fields can test; the others are listed in NOT_CHECKED with the reason):

  corporate (quarterly, latest quarter against the one before)
    CRM-6.4   90+ days past due not in Stage 3                                  Art. 6.4, 9.5(a)
    CRM-7.8   30+ days past due still in Stage 1                                Art. 7.8, 9.5(b)
    CRM-6.12  a borrower in default on a material facility (>5% of its funded
              exposure) with other facilities not in Stage 3                    Art. 6.12, 6.4
    CRM-9.11  upgraded from Stage 3 straight to Stage 1                         Art. 9.11
    CRM-9.7   left Stage 3 with arrears outstanding                             Art. 9.7, 9.35
    CRM-9.8   back to Stage 1 inside the probation period (2 quarterly
              instalments after the last overdue one)                           Art. 9.8, 9.34
    CRM-9.30  restructured (distressed) borrower's facility in Stage 1          Art. 9.30, 9.28
    CRM-9.23  Stage 3 provision below the wholesale floor (25% of the unsecured
              portion up to 4 years in Stage 3, then 100%; 25% of the secured
              portion after 4 years), collateral after the Table 4 haircuts     Art. 9.23, 10.8
    CRM-10.8  Stage 3 collateral haircut below the Table 4 minimum for the
              months since becoming Stage 3                                     Art. 10.8, 10.9
    CRM-10.11 Stage 3 real estate valuation older than 12 months                Art. 10.11(c)(iii)
    CRM-12.5  Stage 3 held more than 5 years without a full write-off           Art. 12.5(b)
    CRM-12.3  Stage 3 above 5% of the book's credit exposure (Board report)     Art. 12.3
  retail (monthly, latest month against the one before)
    CRM-6.4, CRM-7.8 as above on accounts (cross-default does not apply to retail, Art. 6.11)
    CRM-9.24  Stage 3 provision below the retail floor by days past due (25% /
              25% / 50% / 100% of the exposure net of collateral)               Art. 9.24
    CRM-10.11 Stage 3 collateral valuation older than 12 months (residential
              property) or 6 months (motor vehicle)                             Art. 10.11(c)(iv), (d)
    CRM-12.3  as above
"""
from __future__ import annotations

import functools
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from backend.spine.books import book

DOC = "CBUAE Credit Risk Management Standards"
PREFIX = "CBUAE CRM"
HREF = "/policy-docs?doc=pd_cbuae_crm"

SEVERITIES = ("high", "medium", "low")
#: Table 4 (Art. 10.8): minimum haircut (%) by months since becoming Stage 3, for the collateral types the books
#: hold that the table lists. Receivables and plant and equipment are not in the table (Art. 10.8: evaluated case by
#: case), cash in SAR is N/A, so none of these is tested.
HAIRCUT_BANDS = (24, 36, 48, 60)  # up to 24, 25-36, 37-48, 49-60, after 60
HAIRCUT_TABLE: dict[str, tuple[float, ...]] = {
    "Real Estate": (20, 40, 60, 80, 100),
    "Corporate Guarantee": (20, 40, 60, 80, 100),  # "Bonds or guarantees from corporations rated [BBB-] or above"
    "Residential Property": (20, 40, 60, 80, 100),
    "Motor Vehicle": (20, 40, 60, 80, 100),  # "Aircraft, motor vehicles and boats/vessels"
}
#: Art. 10.11: the oldest valuation (months) a Stage 3 facility's collateral may carry.
VALUATION_MAX_MONTHS = {"Real Estate": 12, "Residential Property": 12, "Motor Vehicle": 6}
STAGE3_SHARE_MAX = 0.05  # Art. 12.3
WRITE_OFF_YEARS = 5  # Art. 12.5(b)
MATERIAL_SHARE = 0.05  # Art. 6.4: a facility is material above 5% of the obligor's funded exposure


@dataclass(frozen=True)
class Check:
    id: str
    article: str            # "CBUAE CRM Art. 7.8"
    articles: tuple[str, ...]
    title: str
    rule: str
    books: tuple[str, ...]
    level: str              # facility | account | borrower | book
    severity: str
    measure: str            # what "measured" and "required" are
    fn: Callable[["Ctx", "Check"], list["Breach"]] = field(compare=False, repr=False)

    def meta(self) -> dict[str, Any]:
        return {"check_id": self.id, "article": self.article, "articles": list(self.articles), "title": self.title,
                "rule": self.rule, "books": list(self.books), "level": self.level, "severity": self.severity,
                "measure": self.measure, "href": f"{HREF}&clause={self.article}"}


@dataclass
class Breach:
    check_id: str
    article: str
    title: str
    rule: str
    book: str
    period: str
    entity_type: str        # facility | account | book
    entity_id: str
    borrower_id: str        # the borrower (corporate) or customer (retail) behind it; the book id for a book check
    measured: float | str
    required: float | str
    unit: str
    ead_sar_mn: float
    ecl_sar_mn: float
    shortfall_sar_mn: float
    severity: str
    detail: str

    def row(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Ctx:
    """The frames a check reads. `prev`/`prev2` are the period before and the one before that."""
    book: str
    period: str
    fac: pd.DataFrame
    prev: pd.DataFrame | None = None
    prev2: pd.DataFrame | None = None
    borrowers: pd.DataFrame | None = None
    collateral: pd.DataFrame | None = None
    months_per_period: int = 3


# ------------------------------------------------------------------ loading

CORP_FAC = ["facility_id", "borrower_id", "reporting_quarter", "stage", "dpd_days", "ead_sar_mn", "ecl_sar_mn",
            "quarters_in_stage", "default_flag", "write_off_sar_mn"]
RET_ACC = ["account_id", "customer_id", "reporting_month", "stage", "dpd_days", "ead_sar_mn", "ecl_sar_mn",
           "product", "secured_flag", "write_off_sar_mn"]


def _id(b: str) -> str:
    return "facility_id" if b == "corporate" else "account_id"


def _owner(b: str) -> str:
    return "borrower_id" if b == "corporate" else "customer_id"


def _pcol(b: str) -> str:
    return "reporting_quarter" if b == "corporate" else "reporting_month"


@functools.lru_cache(maxsize=8)
def _frames(b: str) -> tuple[pd.DataFrame, pd.DataFrame | None, pd.DataFrame]:
    bk = book(b)
    if b == "corporate":
        fac = pd.read_parquet(bk.path("corp_facility_quarter"), columns=CORP_FAC)
        bor = pd.read_parquet(bk.path("corp_borrower_quarter"),
                              columns=["borrower_id", "reporting_quarter", "restructured_flag", "watchlist_flag"])
        col = pd.read_parquet(bk.path("corp_collateral_quarter"),
                              columns=["collateral_id", "facility_id", "reporting_quarter", "collateral_type",
                                       "market_value_sar_mn", "haircut_pct", "valuation_age_quarters"])
        col = col.rename(columns={"collateral_value_sar_mn": "market_value_sar_mn"})
        col["valuation_age_months"] = col.pop("valuation_age_quarters") * 3
        return fac, bor, col
    fac = pd.read_parquet(bk.path("retail_account_month"), columns=RET_ACC)
    col = pd.read_parquet(bk.path("retail_collateral_month"),
                          columns=["account_id", "reporting_month", "collateral_type", "collateral_value_sar_mn",
                                   "valuation_age_months"])
    col = col.rename(columns={"collateral_value_sar_mn": "market_value_sar_mn"})
    return fac, None, col


def context(b: str, period: str | None = None) -> Ctx:
    fac, bor, col = _frames(b)
    bk = book(b)
    period = period or bk.as_of
    periods = list(bk.periods)
    if period not in periods:
        raise ValueError(f"The {b} book has no period {period!r}.")
    i = periods.index(period)
    pc = _pcol(b)

    def at(df: pd.DataFrame | None, k: int) -> pd.DataFrame | None:
        if df is None or i - k < 0:
            return None
        return df[df[pc] == periods[i - k]].reset_index(drop=True)

    return Ctx(book=b, period=period, fac=at(fac, 0), prev=at(fac, 1), prev2=at(fac, 2), borrowers=at(bor, 0),
               collateral=at(col, 0), months_per_period=3 if b == "corporate" else 1)


# ------------------------------------------------------------------ helpers


def _r(x: float) -> float:
    return round(float(x), 4)


def _mk(ck: Check, ctx: Ctx, row: Any, measured: Any, required: Any, unit: str, detail: str,
        shortfall: float = 0.0) -> Breach:
    b = ctx.book
    return Breach(check_id=ck.id, article=ck.article, title=ck.title, rule=ck.rule, book=b, period=ctx.period,
                  entity_type="facility" if b == "corporate" else "account", entity_id=str(row[_id(b)]),
                  borrower_id=str(row[_owner(b)]), measured=measured, required=required, unit=unit,
                  ead_sar_mn=_r(row["ead_sar_mn"]), ecl_sar_mn=_r(row["ecl_sar_mn"]), shortfall_sar_mn=_r(shortfall),
                  severity=ck.severity, detail=detail)


def _with_prev(ctx: Ctx, cols: list[str], frame: pd.DataFrame | None = None, suffix: str = "_prev") -> pd.DataFrame:
    frame = ctx.prev if frame is None else frame
    if frame is None:
        return ctx.fac.assign(**{c + suffix: pd.NA for c in cols})
    p = frame.set_index(_id(ctx.book))[cols].rename(columns=lambda c: c + suffix)
    return ctx.fac.join(p, on=_id(ctx.book))


def _months_in_stage3(ctx: Ctx, row: Any) -> int:
    """Months since the facility became Stage 3 (corporate: quarters in stage x 3)."""
    q = row.get("quarters_in_stage") if hasattr(row, "get") else None
    return int(q) * 3 if q is not None and not pd.isna(q) else 0


def _haircut_min(ctype: str, months: int) -> float | None:
    band = HAIRCUT_TABLE.get(ctype)
    if band is None:
        return None
    for k, edge in enumerate(HAIRCUT_BANDS):
        if months <= edge:
            return float(band[k])
    return float(band[-1])


# ------------------------------------------------------------------ checks


def c_90dpd(ctx: Ctx, ck: Check) -> list[Breach]:
    f = ctx.fac
    hit = f[(f["dpd_days"] > 90) & (f["stage"] != 3)]
    return [_mk(ck, ctx, r, int(r["stage"]), 3, "stage", f"{int(r['dpd_days'])} days past due in Stage {int(r['stage'])}")
            for _, r in hit.iterrows()]


def c_30dpd(ctx: Ctx, ck: Check) -> list[Breach]:
    f = ctx.fac
    hit = f[(f["dpd_days"] > 30) & (f["stage"] == 1)]
    return [_mk(ck, ctx, r, 1, 2, "stage", f"{int(r['dpd_days'])} days past due in Stage 1") for _, r in hit.iterrows()]


def c_cross_default(ctx: Ctx, ck: Check) -> list[Breach]:
    f = ctx.fac.copy()
    total = f.groupby("borrower_id")["ead_sar_mn"].transform("sum")
    f["material"] = f["ead_sar_mn"] > MATERIAL_SHARE * total
    defaulted = f[(f["stage"] == 3) & f["material"]].groupby("borrower_id")["facility_id"].first()
    hit = f[f["borrower_id"].isin(defaulted.index) & (f["stage"] != 3)]
    return [_mk(ck, ctx, r, int(r["stage"]), 3, "stage",
                f"borrower {r['borrower_id']} is in default on material facility {defaulted[r['borrower_id']]}")
            for _, r in hit.iterrows()]


def c_3_to_1(ctx: Ctx, ck: Check) -> list[Breach]:
    f = _with_prev(ctx, ["stage"])
    hit = f[(f["stage_prev"] == 3) & (f["stage"] == 1)]
    return [_mk(ck, ctx, r, "Stage 3 to Stage 1", "Stage 3 to Stage 2 first", "migration",
                "upgraded from Stage 3 straight to Stage 1") for _, r in hit.iterrows()]


def c_3_exit_arrears(ctx: Ctx, ck: Check) -> list[Breach]:
    f = _with_prev(ctx, ["stage"])
    hit = f[(f["stage_prev"] == 3) & (f["stage"] < 3) & (f["dpd_days"] > 0)]
    return [_mk(ck, ctx, r, int(r["dpd_days"]), 0, "days past due",
                f"left Stage 3 for Stage {int(r['stage'])} with {int(r['dpd_days'])} days past due outstanding")
            for _, r in hit.iterrows()]


def c_probation(ctx: Ctx, ck: Check) -> list[Breach]:
    """Stage 2 to Stage 1 needs 2 quarterly instalments after the last overdue one (Art. 9.8(b)): a facility back in
    Stage 1 this quarter that was past due in either of the two quarters before is inside its probation period."""
    f = _with_prev(ctx, ["stage", "dpd_days"])
    f = f.join(ctx.prev2.set_index("facility_id")[["dpd_days"]].rename(columns={"dpd_days": "dpd_days_prev2"}),
               on="facility_id") if ctx.prev2 is not None else f.assign(dpd_days_prev2=0)
    last_overdue = f[["dpd_days_prev", "dpd_days_prev2"]].fillna(0)
    hit = f[(f["stage_prev"] == 2) & (f["stage"] == 1) & ((last_overdue > 0).any(axis=1))]
    out = []
    for _, r in hit.iterrows():
        q = 1 if (r["dpd_days_prev"] or 0) > 0 else 2
        out.append(_mk(ck, ctx, r, f"{q - 1} quarters", "2 quarterly instalments (6 months)", "probation",
                       f"back in Stage 1 {q - 1} quarter(s) after its last overdue instalment"))
    return out


def c_restructured_stage1(ctx: Ctx, ck: Check) -> list[Breach]:
    if ctx.borrowers is None:
        return []
    rs = set(ctx.borrowers.loc[ctx.borrowers["restructured_flag"] == 1, "borrower_id"])
    hit = ctx.fac[ctx.fac["borrower_id"].isin(rs) & (ctx.fac["stage"] == 1)]
    return [_mk(ck, ctx, r, 1, "2 or 3", "stage", f"borrower {r['borrower_id']} is restructured; facility in Stage 1")
            for _, r in hit.iterrows()]


def _secured_after_haircut(ctx: Ctx, fid_col: str) -> pd.DataFrame:
    """Per facility: collateral value after the Table 4 haircut for its months in Stage 3 (types the table lists;
    other types are not counted as secured), plus the facility's own haircut for comparison."""
    if ctx.collateral is None or ctx.collateral.empty:
        return pd.DataFrame(columns=[fid_col, "secured"])
    s3 = ctx.fac[ctx.fac["stage"] == 3]
    months = {r[fid_col]: _months_in_stage3(ctx, r) for _, r in s3.iterrows()} if ctx.book == "corporate" else {}
    c = ctx.collateral[ctx.collateral[fid_col].isin(s3[fid_col])]
    vals: dict[str, float] = {}
    for _, r in c.iterrows():
        hc = _haircut_min(r["collateral_type"], months.get(r[fid_col], 0))
        if hc is None:
            continue
        own = float(r["haircut_pct"]) if "haircut_pct" in r and not pd.isna(r.get("haircut_pct")) else 0.0
        vals[r[fid_col]] = vals.get(r[fid_col], 0.0) + float(r["market_value_sar_mn"]) * (1 - max(hc, own) / 100)
    return pd.DataFrame({fid_col: list(vals), "secured": list(vals.values())})


def c_stage3_floor_wholesale(ctx: Ctx, ck: Check) -> list[Breach]:
    s3 = ctx.fac[ctx.fac["stage"] == 3]
    sec = _secured_after_haircut(ctx, "facility_id").set_index("facility_id")["secured"]
    out = []
    for _, r in s3.iterrows():
        ead = float(r["ead_sar_mn"])
        secured = min(ead, float(sec.get(r["facility_id"], 0.0)))
        unsecured = ead - secured
        months = _months_in_stage3(ctx, r)
        if months <= 48:
            floor = 0.25 * unsecured
            how = f"25% of the unsecured portion ({unsecured:.4f}), {months} months in Stage 3"
        else:
            floor = unsecured + 0.25 * secured
            how = f"100% of the unsecured portion ({unsecured:.4f}) + 25% of the secured ({secured:.4f}), {months} months in Stage 3"
        ecl = float(r["ecl_sar_mn"])
        if ecl + 1e-9 < floor:
            out.append(_mk(ck, ctx, r, _r(ecl), _r(floor), "SAR million", f"floor: {how}", floor - ecl))
    return out


RETAIL_FLOOR = ((120, 0.25), (180, 0.50))  # Table 3: 91-120 25%, 121-180 50%, 180+ 100%; UTP not past due 25%


def _retail_floor_pct(dpd: float) -> float:
    if dpd <= 90:
        return 0.25
    for edge, pct in RETAIL_FLOOR:
        if dpd <= edge:
            return pct
    return 1.0


def c_stage3_floor_retail(ctx: Ctx, ck: Check) -> list[Breach]:
    s3 = ctx.fac[ctx.fac["stage"] == 3]
    sec = _secured_after_haircut(ctx, "account_id").set_index("account_id")["secured"]
    out = []
    for _, r in s3.iterrows():
        ead = float(r["ead_sar_mn"])
        net = max(ead - float(sec.get(r["account_id"], 0.0)), 0.0)
        pct = _retail_floor_pct(float(r["dpd_days"]))
        floor = pct * net
        ecl = float(r["ecl_sar_mn"])
        if ecl + 1e-9 < floor:
            out.append(_mk(ck, ctx, r, _r(ecl), _r(floor), "SAR million",
                           f"floor: {pct:.0%} of the exposure net of collateral ({net:.4f}) at {int(r['dpd_days'])} days "
                           "past due", floor - ecl))
    return out


def c_haircut(ctx: Ctx, ck: Check) -> list[Breach]:
    if ctx.collateral is None or "haircut_pct" not in ctx.collateral:
        return []
    s3 = ctx.fac[ctx.fac["stage"] == 3].set_index("facility_id")
    c = ctx.collateral[ctx.collateral["facility_id"].isin(s3.index)]
    out = []
    for _, cr in c.iterrows():
        r = s3.loc[cr["facility_id"]]
        months = _months_in_stage3(ctx, r)
        need = _haircut_min(cr["collateral_type"], months)
        if need is None or float(cr["haircut_pct"]) + 1e-9 >= need:
            continue
        row = {**r.to_dict(), "facility_id": cr["facility_id"]}
        out.append(_mk(ck, ctx, row, float(cr["haircut_pct"]), need, "% haircut",
                       f"{cr['collateral_type']} {cr['collateral_id']}: {months} months in Stage 3"))
    return out


def c_valuation_age(ctx: Ctx, ck: Check) -> list[Breach]:
    if ctx.collateral is None:
        return []
    idc = _id(ctx.book)
    s3 = ctx.fac[ctx.fac["stage"] == 3].set_index(idc)
    c = ctx.collateral[ctx.collateral[idc].isin(s3.index)]
    out = []
    for _, cr in c.iterrows():
        need = VALUATION_MAX_MONTHS.get(cr["collateral_type"])
        if need is None or float(cr["valuation_age_months"]) <= need:
            continue
        row = {**s3.loc[cr[idc]].to_dict(), idc: cr[idc]}
        out.append(_mk(ck, ctx, row, int(cr["valuation_age_months"]), need, "months",
                       f"{cr['collateral_type']} valued {int(cr['valuation_age_months'])} months before {ctx.period}"))
    return out


def c_write_off(ctx: Ctx, ck: Check) -> list[Breach]:
    s3 = ctx.fac[ctx.fac["stage"] == 3]
    limit = WRITE_OFF_YEARS * 12
    out = []
    for _, r in s3.iterrows():
        m = _months_in_stage3(ctx, r)
        if m > limit and float(r["ead_sar_mn"]) > 0:
            out.append(_mk(ck, ctx, r, m, limit, "months in Stage 3",
                           f"{m // 12} years {m % 12} months in Stage 3, still on balance sheet"))
    return out


def c_stage3_share(ctx: Ctx, ck: Check) -> list[Breach]:
    f = ctx.fac
    total = float(f["ead_sar_mn"].sum())
    s3 = f[f["stage"] == 3]
    share = float(s3["ead_sar_mn"].sum()) / total if total else 0.0
    if share <= STAGE3_SHARE_MAX:
        return []
    return [Breach(check_id=ck.id, article=ck.article, title=ck.title, rule=ck.rule, book=ctx.book, period=ctx.period,
                   entity_type="book", entity_id=ctx.book, borrower_id=ctx.book, measured=round(share * 100, 2),
                   required=STAGE3_SHARE_MAX * 100, unit="% of credit exposure in Stage 3",
                   ead_sar_mn=_r(s3["ead_sar_mn"].sum()), ecl_sar_mn=_r(s3["ecl_sar_mn"].sum()), shortfall_sar_mn=0.0,
                   severity=ck.severity,
                   detail=(f"Stage 3 is {share:.2%} of the {ctx.book} book's EAD: the Board must explain the causes to "
                           "the CBUAE and approve a reduction plan, reported semi-annually"))]


A = PREFIX + " Art. "
CHECKS: tuple[Check, ...] = (
    Check("CRM-6.4", A + "6.4", (A + "6.4", A + "9.5"), "90+ days past due not in Stage 3",
          "An obligor more than 90 days past due on a material obligation is in default, and a defaulted facility is "
          "Stage 3.", ("corporate", "retail"), "facility", "high", "stage held vs Stage 3", c_90dpd),
    Check("CRM-7.8", A + "7.8", (A + "7.8", A + "9.5"), "30+ days past due still in Stage 1",
          "Repayments more than 30 days past due are a SICR: the facility is at least Stage 2 (unless the presumption is "
          "rebutted and documented).", ("corporate", "retail"), "facility", "high", "stage held vs Stage 2", c_30dpd),
    Check("CRM-6.12", A + "6.12", (A + "6.12", A + "6.4"), "Wholesale cross-default not applied",
          "For a wholesale obligor, default on a material facility (over 5% of its funded exposure) triggers the default "
          "of the obligor, so its other facilities are Stage 3.", ("corporate",), "facility", "high",
          "stage held vs Stage 3", c_cross_default),
    Check("CRM-9.11", A + "9.11", (A + "9.11",), "Upgraded from Stage 3 straight to Stage 1",
          "A wholesale facility in Stage 3 is not upgraded to Stage 1 directly: it goes to Stage 2 first and is "
          "monitored for the Article 9.8 period.", ("corporate",), "facility", "high", "migration", c_3_to_1),
    Check("CRM-9.7", A + "9.7", (A + "9.7", A + "9.35"), "Left Stage 3 with arrears outstanding",
          "A facility remains in Stage 3 until all arrears are settled.", ("corporate",), "facility", "high",
          "days past due on leaving Stage 3 vs 0", c_3_exit_arrears),
    Check("CRM-9.8", A + "9.8", (A + "9.8", A + "9.34"), "Back to Stage 1 inside the probation period",
          "A wholesale facility returns from Stage 2 to Stage 1 only after the probation period: 2 quarterly "
          "instalments (6 months) from the last overdue instalment.", ("corporate",), "facility", "medium",
          "quarters since the last overdue instalment vs 2", c_probation),
    Check("CRM-9.30", A + "9.30", (A + "9.30", A + "9.28"), "Restructured exposure in Stage 1",
          "A distressed restructured facility is allocated to Stage 2 or Stage 3, not Stage 1.", ("corporate",),
          "facility", "medium", "stage held vs Stage 2 or 3", c_restructured_stage1),
    Check("CRM-9.23", A + "9.23", (A + "9.23", A + "10.8"), "Stage 3 provision below the wholesale floor",
          "Stage 3 wholesale provisions are at least 25% of the unsecured portion for 4 years in Stage 3, then 100% of "
          "it plus 25% of the secured portion (collateral after the Table 4 haircuts).", ("corporate",), "facility",
          "high", "ECL vs the floor (SAR million)", c_stage3_floor_wholesale),
    Check("CRM-9.24", A + "9.24", (A + "9.24",), "Stage 3 provision below the retail floor",
          "Stage 3 retail provisions are at least 25% (unlikely to pay, 91-120 days), 50% (121-180 days) or 100% (180+ "
          "days) of the exposure net of collateral.", ("retail",), "account", "high", "ECL vs the floor (SAR million)",
          c_stage3_floor_retail),
    Check("CRM-10.8", A + "10.8", (A + "10.8", A + "10.9"), "Stage 3 collateral haircut below the Table 4 minimum",
          "For Stage 3, collateral haircuts are at least the Table 4 minimum for the months since becoming Stage 3 "
          "(real estate and corporate guarantees: 20% up to 24 months, 40%, 60%, 80%, then 100% after 60 months).",
          ("corporate",), "facility", "medium", "haircut applied vs the minimum (%)", c_haircut),
    Check("CRM-10.11", A + "10.11", (A + "10.11",), "Stage 3 collateral valuation out of date",
          "For a Stage 3 facility, real estate is valued within the last 12 months and motor vehicles within the last 6 "
          "months of the reporting date.", ("corporate", "retail"), "facility", "medium",
          "valuation age vs the maximum (months)", c_valuation_age),
    Check("CRM-12.5", A + "12.5", (A + "12.5", A + "12.4"), "Stage 3 held more than 5 years",
          "A Stage 3 exposure is not held on the balance sheet for more than 5 years since migrating to Stage 3: it is "
          "fully written off (exceptions need Board sign-off).", ("corporate",), "facility", "medium",
          "months in Stage 3 vs 60", c_write_off),
    Check("CRM-12.3", A + "12.3", (A + "12.3",), "Stage 3 above 5% of credit exposure",
          "When Stage 3 exceeds 5% of total credit exposure, the Board explains the causes to the CBUAE and approves a "
          "plan to reduce it, communicated semi-annually.", ("corporate", "retail"), "book", "low",
          "Stage 3 share of EAD vs 5%", c_stage3_share),
)
BY_ID = {c.id: c for c in CHECKS}

#: Rules of the Standards these books cannot test, and why (shown with the results so nothing is implied).
NOT_CHECKED = [
    {"article": A + "7.7", "rule": "3 or more deferrals in 24 months is a SICR", "why": "the books hold no deferral history"},
    {"article": A + "9.29", "rule": "restructured 3 or more times: Stage 3", "why": "the books flag a restructuring, not how many"},
    {"article": A + "9.21", "rule": "Stage 1 and 2 provisions of at least 1.50% of credit RWA",
     "why": "the books hold no risk-weighted assets"},
    {"article": A + "9.19", "rule": "100% provision on interest and fees more than 90 days past due",
     "why": "the books do not split interest and fees from principal"},
    {"article": A + "4.3", "rule": "annual review and rating update of every wholesale obligor (Art. 9.4(c), 11.3)",
     "why": "the books hold no review date"},
    {"article": A + "2.6", "rule": "Board approval of facilities above 10% of Tier 1 capital",
     "why": "the books hold no Tier 1 capital or approval record"},
    {"article": A + "7.11", "rule": "rating downgrade as a SICR indicator",
     "why": "the Standards state no number of notches; the Bank's own trigger is CP-3.3"},
]


# ------------------------------------------------------------------ running


def run_book(b: str, period: str | None = None, checks: tuple[Check, ...] = CHECKS, ctx: Ctx | None = None) -> list[Breach]:
    ctx = ctx or context(b, period)
    out: list[Breach] = []
    for ck in checks:
        if b in ck.books:
            out.extend(ck.fn(ctx, ck))
    return out


def _summary(rows: list[dict[str, Any]], ctxs: dict[str, Ctx]) -> list[dict[str, Any]]:
    out = []
    for ck in CHECKS:
        for b in ck.books:
            mine = [r for r in rows if r["check_id"] == ck.id and r["book"] == b]
            tested = int(len(ctxs[b].fac)) if ck.level != "book" else 1
            out.append({**ck.meta(), "book": b, "period": ctxs[b].period, "tested": tested,
                        "breaches": len(mine), "status": "breach" if mine else "compliant",
                        "borrowers": len({r["borrower_id"] for r in mine}),
                        "ead_sar_mn": _r(sum(r["ead_sar_mn"] for r in mine if r["entity_type"] != "book") or
                                         sum(r["ead_sar_mn"] for r in mine)),
                        "ecl_sar_mn": _r(sum(r["ecl_sar_mn"] for r in mine if r["entity_type"] != "book") or
                                         sum(r["ecl_sar_mn"] for r in mine)),
                        "shortfall_sar_mn": _r(sum(r["shortfall_sar_mn"] for r in mine))})
    return out


@functools.lru_cache(maxsize=4)
def _run_all(corp_period: str, retail_period: str) -> str:
    ctxs = {"corporate": context("corporate", corp_period), "retail": context("retail", retail_period)}
    rows = [x.row() for b, c in ctxs.items() for x in run_book(b, ctx=c)]
    sev = {s: i for i, s in enumerate(SEVERITIES)}
    rows.sort(key=lambda r: (sev[r["severity"]], r["book"], r["check_id"], -r["ead_sar_mn"], r["entity_id"]))
    checks = _summary(rows, ctxs)
    by_article: dict[str, dict[str, Any]] = {}
    for c in checks:
        a = by_article.setdefault(c["article"], {"article": c["article"], "title": c["title"], "breaches": 0,
                                                  "ead_sar_mn": 0.0, "ecl_sar_mn": 0.0, "shortfall_sar_mn": 0.0,
                                                  "checks": []})
        a["breaches"] += c["breaches"]
        a["ead_sar_mn"] = _r(a["ead_sar_mn"] + c["ead_sar_mn"])
        a["ecl_sar_mn"] = _r(a["ecl_sar_mn"] + c["ecl_sar_mn"])
        a["shortfall_sar_mn"] = _r(a["shortfall_sar_mn"] + c["shortfall_sar_mn"])
        if c["check_id"] not in a["checks"]:
            a["checks"].append(c["check_id"])
    arts = sorted(by_article.values(), key=lambda a: [int(x) for x in a["article"].split("Art. ")[1].split(".")])
    out = {
        "document": DOC, "reference": PREFIX, "href": HREF,
        "periods": {b: c.period for b, c in ctxs.items()},
        "as_of": {b: book(b).as_of_label() if hasattr(book(b), "as_of_label") else c.period for b, c in ctxs.items()},
        "totals": {"breaches": len(rows), "checks": len(checks),
                   "checks_in_breach": sum(1 for c in checks if c["breaches"]),
                   "high": sum(1 for r in rows if r["severity"] == "high"),
                   "ead_sar_mn": _r(sum(r["ead_sar_mn"] for r in rows if r["entity_type"] != "book")),
                   "ecl_sar_mn": _r(sum(r["ecl_sar_mn"] for r in rows if r["entity_type"] != "book")),
                   "shortfall_sar_mn": _r(sum(r["shortfall_sar_mn"] for r in rows))},
        "by_book": {b: {"breaches": sum(1 for r in rows if r["book"] == b),
                        "tested": int(len(c.fac)),
                        "ead_sar_mn": _r(sum(r["ead_sar_mn"] for r in rows if r["book"] == b and r["entity_type"] != "book"))}
                    for b, c in ctxs.items()},
        "checks": checks, "by_article": arts, "breaches": rows, "not_checked": NOT_CHECKED,
        "method": ("Deterministic checks of the books against the CBUAE Credit Risk Management Standards; each breach "
                   "names its article, the entity, the measured and required values, and its EAD and ECL (SAR million)."),
    }
    return json.dumps(out, default=float)


def run(corporate_period: str | None = None, retail_period: str | None = None) -> dict[str, Any]:
    """Every check on both books (latest periods by default). Cached per period pair."""
    return json.loads(_run_all(corporate_period or book("corporate").as_of, retail_period or book("retail").as_of))


def breaches(article: str = "", book_id: str = "", severity: str = "", entity: str = "", check_id: str = "",
             limit: int = 50, **periods: str) -> dict[str, Any]:
    """Filtered breaches: by article ("9", "9.23", "CBUAE CRM Art. 9.23"), book, severity, entity id or check."""
    res = run(periods.get("corporate_period"), periods.get("retail_period"))
    art = article.replace(PREFIX, "").replace("Art.", "").replace("Article", "").strip()
    rows = res["breaches"]
    checks = res["checks"]
    if art:
        def ok(a: str) -> bool:
            n = a.split("Art. ")[1]
            return n == art or n.startswith(art + ".") or n.split(".")[0] == art and "." not in art
        rows = [r for r in rows if ok(r["article"])]  # the check's own article (its cross-references are listed)
        checks = [c for c in checks if ok(c["article"])]
    if book_id:
        rows = [r for r in rows if r["book"] == book_id]
        checks = [c for c in checks if c["book"] == book_id]
    if severity:
        rows = [r for r in rows if r["severity"] == severity]
    if check_id:
        rows = [r for r in rows if r["check_id"] == check_id]
        checks = [c for c in checks if c["check_id"] == check_id]
    if entity:
        e = entity.strip().upper()
        rows = [r for r in rows if r["entity_id"].upper() == e or r["borrower_id"].upper() == e]
    return {**{k: res[k] for k in ("document", "reference", "href", "periods", "not_checked")},
            "filter": {"article": article, "book": book_id, "severity": severity, "entity": entity, "check": check_id},
            "count": len(rows), "ead_sar_mn": _r(sum(r["ead_sar_mn"] for r in rows if r["entity_type"] != "book")),
            "ecl_sar_mn": _r(sum(r["ecl_sar_mn"] for r in rows if r["entity_type"] != "book")),
            "shortfall_sar_mn": _r(sum(r["shortfall_sar_mn"] for r in rows)),
            "checks": checks, "breaches": rows[:limit], "truncated": len(rows) > limit}


def frame(res: dict[str, Any] | None = None) -> pd.DataFrame:
    """The breaches as a table (the `regulatory` data domain relation)."""
    res = res or run()
    df = pd.DataFrame(res["breaches"])
    for c in ("measured", "required"):
        df[c] = df[c].astype(str)
    return df


def write(out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / "crm_breach.parquet"
    frame().to_parquet(p, index=False)
    return p
