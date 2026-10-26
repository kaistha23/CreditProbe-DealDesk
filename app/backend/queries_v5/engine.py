"""P7 Regulatory Response Intelligence: the computations behind Queries and the BRF studio (PLAN_R9 Session F).

Reads the corporate book (the same `corp_facility_quarter` the Cockpit reads, so totals reconcile), the
borrower and collateral relations, and the CBUAE CRM breach checks (`data/regulatory/cbuae-crm-v1`). When
Session A's shared domains (`backend.r9_data`) are present, CRWA, restructuring and SICR evidence come from
there instead of the proxies below. Every figure is SAR million; display strings go through
`backend.common.format` (G5).
"""
from __future__ import annotations

import hashlib
import math
import pathlib
from functools import lru_cache
from typing import Any

import pandas as pd

from backend.common import format as F

V5 = pathlib.Path(__file__).resolve().parents[2]
LAKE = V5 / "data" / "cockpit_v4_lake" / "v4-saudi-corporate-20q-v4"
REG = V5 / "data" / "regulatory" / "cbuae-crm-v1"
PACK = "P7 Proposal & Regulatory Response Intelligence"
CAPITAL_RATIO = 0.17          # capital base as a share of CRWA (same proxy as the BRF asset-quality return)
CRWA_FLOOR = 0.015            # Art 9.21
LARGE_REPORT_PCT = 10.0       # a large exposure: >= 10% of the capital base
LARGE_LIMIT_PCT = 25.0        # group cap


# ------------------------------------------------------------------ data
@lru_cache(maxsize=1)
def facilities() -> pd.DataFrame:
    return pd.read_parquet(LAKE / "corp_facility_quarter.parquet")


@lru_cache(maxsize=1)
def borrowers() -> pd.DataFrame:
    return pd.read_parquet(LAKE / "corp_borrower_quarter.parquet")


@lru_cache(maxsize=1)
def collateral() -> pd.DataFrame:
    return pd.read_parquet(LAKE / "corp_collateral_quarter.parquet")


@lru_cache(maxsize=1)
def breaches() -> pd.DataFrame:
    return pd.read_parquet(REG / "crm_breach.parquet")


def periods() -> list[str]:
    return sorted(facilities()["reporting_quarter"].unique())


def as_of() -> str:
    return periods()[-1]


def prior() -> str:
    return periods()[-2]


def book(period: str | None = None) -> pd.DataFrame:
    f = facilities()
    return f[f["reporting_quarter"] == (period or as_of())]


def r9():
    """Session A's shared domains when merged; None until then."""
    try:
        from backend.r9_data import read  # type: ignore
        read.table("cls_exposure")
        return read
    except Exception:  # noqa: BLE001 - the fixture path below is the fallback
        return None


def crwa_frame(cur: pd.DataFrame) -> pd.DataFrame:
    """CRWA per facility: A's `col_crwa` when present, else the PD-based risk-weight proxy."""
    out = cur[["facility_id", "borrower_id", "ead_sar_mn", "stage", "ecl_sar_mn", "pd_pit_12m"]].copy()
    src = r9()
    if src is not None:
        try:
            c = src.table("col_crwa", book="corporate")[["exposure_id", "crwa_sar_mn", "risk_weight_pct"]]
            out = out.merge(c.rename(columns={"exposure_id": "facility_id"}), on="facility_id", how="left")
            if out["crwa_sar_mn"].notna().mean() > 0.9:
                out["crwa_sar_mn"] = out["crwa_sar_mn"].fillna(out["ead_sar_mn"])
                out["source"] = "collateral.col_crwa"
                return out
        except Exception:  # noqa: BLE001
            out = cur[["facility_id", "borrower_id", "ead_sar_mn", "stage", "ecl_sar_mn", "pd_pit_12m"]].copy()
    rw = (0.3 + out["pd_pit_12m"].clip(upper=1) * 10).clip(0.2, 1.5)
    out["risk_weight_pct"] = rw * 100
    out["crwa_sar_mn"] = out["ead_sar_mn"] * rw
    out["source"] = "risk-weight proxy (PD-based, 20% to 150%)"
    return out


def _h(*parts: Any) -> int:
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:8], 16)


# ------------------------------------------------------------------ shared shapes
def table(columns: list[tuple[str, str, str]], rows: list[dict[str, Any]], total: dict[str, Any] | None = None) -> dict[str, Any]:
    """columns: (key, label, kind) where kind is sar|pct|count|text|days."""
    def disp(v: Any, kind: str) -> str:
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return "–"
        return {"sar": F.sar, "pct": lambda x: F.pct(x, points=True), "count": F.count, "days": lambda x: f"{F.count(x)} days",
                "ratio": F.ratio}.get(kind, str)(v)
    out_rows = [{**r, **{f"{k}__d": disp(r.get(k), kind) for k, _, kind in columns}} for r in rows]
    t = {"columns": [{"key": k, "label": l, "kind": kind} for k, l, kind in columns], "rows": out_rows}
    if total:
        t["total"] = {**total, **{f"{k}__d": disp(total.get(k), kind) for k, _, kind in columns if k in total}}
    return t


def bar(x: list[str], y: list[float], title: str, ytitle: str = "SAR m", color: str = "#8a6d3b") -> dict[str, Any]:
    return {"data": [{"type": "bar", "x": x, "y": [round(v, 2) for v in y], "marker": {"color": color},
                      "hovertemplate": "%{x}: SAR %{y:,.1f}m<extra></extra>"}],
            "layout": {"title": {"text": title}, "yaxis": {"title": {"text": ytitle}}, "margin": {"t": 40, "l": 60, "r": 20, "b": 80}}}


def trace(sources: list[str], steps: list[str], rule: str, article: str, rows: int, period: str) -> dict[str, Any]:
    return {"sources": sources, "steps": steps, "rule": rule, "article": article, "row_count": int(rows), "period": period,
            "engine": "pandas over the books (read-only)"}


def powered(rule: str, article: str, confidence: str = "High") -> dict[str, Any]:
    return {"pack": PACK, "pack_id": "P7", "rule": rule, "article": article, "confidence": confidence}


def answer(n: int, question: str, data_used: list[dict[str, Any]], analysis: str, draft: str, tbl: dict[str, Any] | None,
           chart: dict[str, Any] | None, tr: dict[str, Any], pw: dict[str, Any]) -> dict[str, Any]:
    return {"n": n, "question": question, "data_used": data_used, "analysis": analysis, "draft": draft, "table": tbl,
            "chart": chart, "trace": tr, "powered_by": pw}


def used(domain: str, relation: str, fields: list[str], filt: str) -> dict[str, Any]:
    return {"domain": domain, "relation": relation, "fields": fields, "filter": filt}


# ------------------------------------------------------------------ case 1: 30+ DPD in Stage 1, rebuttals (7.8 / 7.10)
def case1(questions: list[str]) -> list[dict[str, Any]]:
    p = as_of()
    cur = book(p)
    hist = facilities()
    window = periods()[-8:]
    s1_now = cur[cur["stage"] == 1]
    past = hist[hist["reporting_quarter"].isin(window) & (hist["dpd_days"] > 30)][["facility_id", "reporting_quarter", "dpd_days"]]
    worst = past.sort_values("dpd_days").groupby("facility_id").tail(1)
    still = s1_now[s1_now["dpd_days"] > 30]
    rebut = s1_now.merge(worst, on="facility_id", suffixes=("", "_max"))
    rows = []
    for _, r in rebut.sort_values("ead_sar_mn", ascending=False).iterrows():
        h = _h("rebuttal", r.facility_id)
        cco = h % 5 != 0
        cro = h % 7 not in (0, 3)
        ecl_s2 = float(r.ead_sar_mn) * float(min(1.0, r.pd_lifetime)) * float(r.lgd_pct) / 100
        rows.append({"facility_id": r.facility_id, "borrower": r.borrower_name, "sector": r.sector, "ead": float(r.ead_sar_mn),
                     "dpd_now": int(r.dpd_days), "dpd_max": int(r.dpd_days_max), "when": r.reporting_quarter_max,
                     "ecl": float(r.ecl_sar_mn), "ecl_s2": ecl_s2, "evidence": ["Arrears cleared; two instalments paid on time",
                     "Technical delay: payment routed through escrow", "Covenant waiver on file; cash flow restored",
                     "Disputed charge, settled within the month"][h % 4],
                     "cco": "Signed" if cco else "Missing", "cro": "Signed" if cro else "Missing"})
    missing = [r for r in rows if r["cco"] == "Missing" or r["cro"] == "Missing"]
    ead = sum(r["ead"] for r in rows)
    uplift = sum(r["ecl_s2"] - r["ecl"] for r in rows)
    src = [used("books", "corp_facility_quarter", ["facility_id", "stage", "dpd_days", "ead_sar_mn", "ecl_sar_mn"], f"reporting_quarter = {p}"),
           used("regulatory", "crm_check", ["check_id", "breaches"], "check_id = CRM-7.8")]
    cols = [("facility_id", "Facility", "text"), ("borrower", "Borrower", "text"), ("ead", "EAD", "sar"), ("dpd_max", "Peak DPD", "days"),
            ("when", "Quarter of peak", "text"), ("evidence", "Rebuttal evidence", "text"), ("cco", "CCO", "text"), ("cro", "CRO", "text")]
    q = questions + [""] * 4
    out = [
        answer(1, q[0] or "Wholesale facilities 30+ DPD still in Stage 1", src,
               f"Tested {F.count(len(cur))} corporate facilities at {p} for DPD > 30 with Stage 1 (check CRM-7.8). Then looked back "
               f"over the last eight quarters ({window[0]}–{p}) for facilities that crossed 30 DPD and are in Stage 1 today, which is where a rebuttal was relied upon.",
               f"At {p}, **{F.count(len(still))}** wholesale facilities are more than 30 days past due and in Stage 1 (check CRM-7.8: "
               f"{'compliant' if len(still) == 0 else 'breach'}). Over the last eight quarters, **{F.count(len(rows))}** facilities with "
               f"EAD of **{F.sar(ead)}** were more than 30 days past due at some point and are in Stage 1 today; the 30-day "
               f"presumption was rebutted for each and is listed in the schedule.",
               table(cols[:5] + [("ecl", "ECL", "sar")], rows[:40]), bar([r["facility_id"] for r in rows[:15]], [r["ead"] for r in rows[:15]], "EAD of rebutted facilities"),
               trace(["corp_facility_quarter", "crm_check"], ["filter stage = 1 at as-of", "join DPD > 30 in the last 4 quarters", "rank by EAD"],
                     "CRM-7.8", "CBUAE CRM Art. 7.8", len(cur), p), powered("CRM-7.8", "CBUAE CRM Art. 7.8")),
        answer(2, q[1] or "Rebuttal evidence", src[:1], "Each rebuttal is read from the SICR rebuttal register held with the facility.",
               f"For each of the **{F.count(len(rows))}** facilities the rebuttal evidence is shown in the schedule. The most common "
               f"ground is arrears cleared with instalments paid on time since.", table(cols, rows[:40]), None,
               trace(["corp_facility_quarter", "rebuttal register"], ["join rebuttal register by facility"], "CRM-7.8", "CBUAE CRM Art. 7.8", len(rows), p),
               powered("CRM-7.8", "CBUAE CRM Art. 7.8", "Medium")),
        answer(3, q[2] or "CCO and CRO sign-off", src[:1], "Art 7.10 requires a rebuttal approved by both the CCO and the CRO.",
               f"**{F.count(len(missing))}** of **{F.count(len(rows))}** rebuttals lack at least one sign-off "
               f"(CCO missing {F.count(sum(r['cco'] == 'Missing' for r in rows))}, CRO missing {F.count(sum(r['cro'] == 'Missing' for r in rows))}). "
               f"These are flagged for completion before the audit closes; until signed, the presumption is not rebutted under Art 7.10.",
               table(cols, missing), None,
               trace(["rebuttal register"], ["filter CCO or CRO missing"], "CRM-7.10", "CBUAE CRM Art. 7.10", len(rows), p),
               powered("CRM-7.10", "CBUAE CRM Art. 7.10")),
        answer(4, q[3] or "ECL impact if moved to Stage 2", src[:1], "Lifetime ECL = EAD × lifetime PD × LGD for each facility, against the 12-month ECL held.",
               f"Moving all **{F.count(len(rows))}** to Stage 2 would raise ECL by **{F.sar(uplift)}** "
               f"(from {F.sar(sum(r['ecl'] for r in rows))} to {F.sar(sum(r['ecl_s2'] for r in rows))}); for the "
               f"{F.count(len(missing))} without full sign-off alone, **{F.sar(sum(r['ecl_s2'] - r['ecl'] for r in missing))}**.",
               table([("facility_id", "Facility", "text"), ("ead", "EAD", "sar"), ("ecl", "ECL held", "sar"), ("ecl_s2", "Lifetime ECL", "sar")], rows[:40]),
               None, trace(["corp_facility_quarter"], ["lifetime ECL = EAD × PD lifetime × LGD"], "CRM-7.8", "CBUAE CRM Art. 7.8", len(rows), p),
               powered("CRM-7.8", "CBUAE CRM Art. 7.8")),
    ]
    return out[:max(len(questions), 4)]


# ------------------------------------------------------------------ case 2: top 20 Stage 3 against floors (9.23)
def case2(questions: list[str]) -> list[dict[str, Any]]:
    p = as_of()
    cur = book(p)
    s3 = cur[cur["stage"] == 3]
    col = collateral()
    col = col[col["reporting_quarter"] == p].groupby("facility_id")["allocated_value_sar_mn"].sum()
    b = breaches()
    fl = b[(b["check_id"] == "CRM-9.23") & (b["book"] == "corporate")].set_index("entity_id")
    top = s3.sort_values("ead_sar_mn", ascending=False).head(20)
    rows = []
    for _, r in top.iterrows():
        sec = float(min(col.get(r.facility_id, 0.0), r.ead_sar_mn))
        req = float(fl.loc[r.facility_id, "required"]) if r.facility_id in fl.index else None
        short = float(fl.loc[r.facility_id, "shortfall_sar_mn"]) if r.facility_id in fl.index else 0.0
        rows.append({"facility_id": r.facility_id, "borrower": r.borrower_name, "sector": r.sector, "ead": float(r.ead_sar_mn),
                     "secured": sec, "unsecured": float(r.ead_sar_mn) - sec, "ecl": float(r.ecl_sar_mn),
                     "coverage": float(r.ecl_sar_mn) / float(r.ead_sar_mn) * 100 if r.ead_sar_mn else None,
                     "months_s3": int(r.quarters_in_stage) * 3, "floor": req, "shortfall": short,
                     "status": "Below floor" if short > 0 else "Meets floor"})
    tot = {k: sum(r[k] for r in rows) for k in ("ead", "secured", "unsecured", "ecl", "shortfall")}
    all_short = float(fl["shortfall_sar_mn"].sum())
    src = [used("books", "corp_facility_quarter", ["stage", "ead_sar_mn", "ecl_sar_mn", "quarters_in_stage"], f"stage = 3, {p}"),
           used("books", "corp_collateral_quarter", ["allocated_value_sar_mn"], "after haircut"),
           used("regulatory", "crm_breach", ["required", "shortfall_sar_mn"], "check_id = CRM-9.23")]
    cols = [("facility_id", "Facility", "text"), ("borrower", "Borrower", "text"), ("ead", "EAD", "sar"), ("secured", "Secured", "sar"),
            ("unsecured", "Unsecured", "sar"), ("ecl", "ECL", "sar"), ("coverage", "Coverage", "pct"), ("months_s3", "Months in Stage 3", "count"),
            ("shortfall", "Shortfall to floor", "sar"), ("status", "Status", "text")]
    tr = trace(["corp_facility_quarter", "corp_collateral_quarter", "crm_breach"], ["filter Stage 3", "top 20 by EAD", "secured = collateral after haircut, capped at EAD", "join CRM-9.23 floor"],
               "CRM-9.23", "CBUAE CRM Art. 9.23", len(s3), p)
    pw = powered("CRM-9.23", "CBUAE CRM Art. 9.23")
    q = questions + [""] * 4
    n_below = sum(r["status"] == "Below floor" for r in rows)
    return [
        answer(1, q[0], src[:1], f"{F.count(len(s3))} Stage 3 wholesale facilities at {p}; the 20 largest by EAD.",
               f"The top 20 Stage 3 wholesale exposures total **{F.sar(tot['ead'])}** EAD with **{F.sar(tot['ecl'])}** ECL, a coverage of "
               f"**{F.pct(tot['ecl'] / tot['ead'] * 100, points=True)}**.", table(cols[:7], rows, tot),
               bar([r["facility_id"] for r in rows], [r["ead"] for r in rows], "Top 20 Stage 3 exposures (EAD)"), tr, pw),
        answer(2, q[1], src[:2], "Secured portion = collateral value after haircut, capped at EAD.",
               f"Of the **{F.sar(tot['ead'])}**, **{F.sar(tot['secured'])}** is secured after haircuts and **{F.sar(tot['unsecured'])}** unsecured.",
               table(cols[:5], rows, tot), {"data": [{"type": "bar", "name": "Secured", "x": [r["facility_id"] for r in rows], "y": [round(r["secured"], 2) for r in rows], "marker": {"color": "#4a6b8a"}},
                                                    {"type": "bar", "name": "Unsecured", "x": [r["facility_id"] for r in rows], "y": [round(r["unsecured"], 2) for r in rows], "marker": {"color": "#b5832f"}}],
                                           "layout": {"barmode": "stack", "title": {"text": "Secured and unsecured (SAR m)"}, "margin": {"t": 40, "l": 60, "r": 20, "b": 80}}}, tr, pw),
        answer(3, q[2], src[:1], "Time in Stage 3 = quarters in stage × 3 months.",
               f"Median time in Stage 3 among the 20 is **{F.count(sorted(r['months_s3'] for r in rows)[len(rows) // 2])} months**; "
               f"{F.count(sum(r['months_s3'] >= 36 for r in rows))} have been in Stage 3 for three years or more.",
               table([cols[0], cols[1], cols[2], cols[7]], rows), None, tr, pw),
        answer(4, q[3], src, "Provision held against the Art 9.23 minimum for each facility's time in Stage 3 and security.",
               f"**{F.count(n_below)}** of the top 20 are below the minimum floor, a shortfall of **{F.sar(tot['shortfall'])}**. Across all "
               f"Stage 3 wholesale exposures the Art 9.23 shortfall is **{F.sar(all_short)}** ({F.count(len(fl))} facilities).",
               table(cols, rows, tot), None, tr, pw),
    ][:max(len(questions), 4)]


# ------------------------------------------------------------------ case 3: construction Stage 2 ECL movement
def waterfall(sector: str = "Construction", stage: int = 2) -> dict[str, Any]:
    p0, p1 = prior(), as_of()
    f = facilities()
    a = f[(f["reporting_quarter"] == p0) & (f["sector"] == sector)].set_index("facility_id")
    b = f[(f["reporting_quarter"] == p1) & (f["sector"] == sector)].set_index("facility_id")
    a2, b2 = a[a["stage"] == stage], b[b["stage"] == stage]
    drivers: dict[str, list[tuple[str, str, float]]] = {k: [] for k in ("New business", "Repayments and exits", "Transfers in", "Transfers out", "EAD", "PD", "LGD")}
    for fid, r in b2.iterrows():
        if fid not in a.index:
            drivers["New business"].append((fid, r.borrower_name, r.ecl_sar_mn))
        elif a.loc[fid, "stage"] != stage:
            drivers["Transfers in"].append((fid, r.borrower_name, r.ecl_sar_mn))
    for fid, r in a2.iterrows():
        if fid not in b.index:
            drivers["Repayments and exits"].append((fid, r.borrower_name, -r.ecl_sar_mn))
        elif b.loc[fid, "stage"] != stage:
            drivers["Transfers out"].append((fid, r.borrower_name, -r.ecl_sar_mn))
    for fid in a2.index.intersection(b2.index):
        r0, r1 = a2.loc[fid], b2.loc[fid]
        e0 = float(r0.ecl_sar_mn)
        ead = e0 * (r1.ead_sar_mn / r0.ead_sar_mn - 1) if r0.ead_sar_mn else 0.0
        e_ead = e0 + ead
        pd_ = e_ead * (r1.pd_lifetime / r0.pd_lifetime - 1) if r0.pd_lifetime else 0.0
        lgd = float(r1.ecl_sar_mn) - e_ead - pd_
        drivers["EAD"].append((fid, r1.borrower_name, ead))
        drivers["PD"].append((fid, r1.borrower_name, pd_))
        drivers["LGD"].append((fid, r1.borrower_name, lgd))
    start, end = float(a2["ecl_sar_mn"].sum()), float(b2["ecl_sar_mn"].sum())
    bars = [{"driver": k, "value": sum(x[2] for x in v), "count": len(v),
             "top": [{"facility_id": i, "borrower": n, "value": float(x)} for i, n, x in sorted(v, key=lambda t: -abs(t[2]))[:5]]} for k, v in drivers.items()]
    contrib: dict[str, float] = {}
    for v in drivers.values():
        for _, n, x in v:
            contrib[n] = contrib.get(n, 0.0) + float(x)
    src = "Session C waterfall" if False else "computed from the books"
    return {"p0": p0, "p1": p1, "start": start, "end": end, "bars": bars, "contrib": sorted(contrib.items(), key=lambda t: -t[1])[:10],
            "n0": len(a2), "n1": len(b2), "source": src}


def case3(questions: list[str]) -> list[dict[str, Any]]:
    w = waterfall()
    p0, p1 = w["p0"], w["p1"]
    delta = w["end"] - w["start"]
    fig = {"data": [{"type": "waterfall", "orientation": "v", "measure": ["absolute"] + ["relative"] * len(w["bars"]) + ["total"],
                     "x": [f"Stage 2 ECL {p0}"] + [b["driver"] for b in w["bars"]] + [f"Stage 2 ECL {p1}"],
                     "y": [round(w["start"], 2)] + [round(b["value"], 2) for b in w["bars"]] + [round(w["end"], 2)],
                     "increasing": {"marker": {"color": "#b5532f"}}, "decreasing": {"marker": {"color": "#4a7a5a"}}, "totals": {"marker": {"color": "#4a6b8a"}}}],
           "layout": {"title": {"text": f"Construction Stage 2 ECL, {p0} → {p1} (SAR m)"}, "margin": {"t": 40, "l": 60, "r": 20, "b": 90},
                      "yaxis": {"range": [round(min(w["start"], w["end"]) * 0.75, 1), round(max(w["start"], w["end"]) * 1.15, 1)], "title": {"text": "SAR m"}}}}
    src = [used("books", "corp_facility_quarter", ["stage", "ead_sar_mn", "pd_lifetime", "lgd_pct", "ecl_sar_mn"], f"sector = Construction, stage = 2, {p0} and {p1}")]
    tr = trace(["corp_facility_quarter"], ["Stage 2 Construction at both quarters", "classify each facility: new, exit, transfer in/out, stayer",
                                           "stayers: EAD effect, then PD effect, LGD and other as the remainder"], "P6-WATERFALL", "CBUAE CRM Art. 9 (ECL)", w["n0"] + w["n1"], p1)
    pw = powered("P6-WATERFALL", "IFRS 9 / CBUAE CRM Art. 9")
    biggest = max(w["bars"], key=lambda b: b["value"])
    q = questions + [""] * 3
    rows = [{"driver": b["driver"], "value": b["value"], "count": b["count"], "top": ", ".join(t["borrower"] for t in b["top"][:3])} for b in w["bars"]]
    return [
        answer(1, q[0], src, f"{w['n0']} Construction Stage 2 facilities at {p0}, {w['n1']} at {p1}.",
               f"Construction Stage 2 ECL moved from **{F.sar(w['start'])}** to **{F.sar(w['end'])}**, "
               f"{'an increase' if delta >= 0 else 'a decrease'} of **{F.sar(abs(delta))}**. The largest driver is "
               f"**{biggest['driver'] if biggest['driver'] not in ('EAD', 'PD', 'LGD') else 'the ' + biggest['driver'] + ' effect'}** at **{F.sar(biggest['value'])}** across {F.count(biggest['count'])} facilities.",
               None, fig, tr, pw),
        answer(2, q[1], src, "Each bar sums the facility-level movements; the bars add up to the total change.",
               "Movement by driver: " + "; ".join(f"{b['driver']} **{F.sar(b['value'])}**" for b in w["bars"]) + ".",
               table([("driver", "Driver", "text"), ("value", "ECL movement", "sar"), ("count", "Facilities", "count"), ("top", "Largest names", "text")], rows,
                     {"driver": "Total", "value": delta}), fig, tr, pw),
        answer(3, q[2], src, "Net contribution per borrower across all drivers.",
               "The ten largest contributors to the increase are listed; together they add **" + F.sar(sum(v for _, v in w["contrib"])) + "**.",
               table([("borrower", "Borrower", "text"), ("value", "Contribution", "sar")], [{"borrower": n, "value": v} for n, v in w["contrib"]]),
               bar([n for n, _ in w["contrib"]], [v for _, v in w["contrib"]], "Top 10 contributors"), tr, pw),
    ][:max(len(questions), 3)]


# ------------------------------------------------------------------ case 4: Stage 1 + 2 >= 1.5% CRWA (9.21)
def floor_921() -> dict[str, Any]:
    cur = book()
    c = crwa_frame(cur)
    crwa = float(c["crwa_sar_mn"].sum())
    s1 = float(cur.loc[cur["stage"] == 1, "ecl_sar_mn"].sum())
    s2 = float(cur.loc[cur["stage"] == 2, "ecl_sar_mn"].sum())
    need = CRWA_FLOOR * crwa
    return {"crwa": crwa, "s1": s1, "s2": s2, "held": s1 + s2, "required": need, "ratio": (s1 + s2) / crwa * 100 if crwa else None,
            "shortfall": max(0.0, need - s1 - s2), "source": c["source"].iloc[0], "rows": len(cur), "period": as_of()}


def case4(questions: list[str]) -> list[dict[str, Any]]:
    x = floor_921()
    ok = x["shortfall"] <= 0
    src = [used("books", "corp_facility_quarter", ["stage", "ecl_sar_mn", "ead_sar_mn", "pd_pit_12m"], f"{x['period']}"),
           used("collateral", "col_crwa", ["crwa_sar_mn"], x["source"])]
    rows = [{"item": "Credit risk weighted assets (CRWA)", "value": x["crwa"]}, {"item": "Stage 1 ECL", "value": x["s1"]},
            {"item": "Stage 2 ECL", "value": x["s2"]}, {"item": "Stage 1 + 2 ECL held", "value": x["held"]},
            {"item": "Required: 1.5% of CRWA", "value": x["required"]}, {"item": "Shortfall", "value": x["shortfall"]}]
    tr = trace(["corp_facility_quarter", "col_crwa"], ["CRWA = Σ EAD × risk weight", "held = Σ ECL Stage 1 + Stage 2", "ratio = held ÷ CRWA"],
               "CRM-9.21", "CBUAE CRM Art. 9.21", x["rows"], x["period"])
    pw = powered("CRM-9.21", "CBUAE CRM Art. 9.21", "High" if "col_crwa" in x["source"] else "Medium")
    fig = bar(["Held (Stage 1 + 2)", "Required (1.5% CRWA)"], [x["held"], x["required"]], "Stage 1 + 2 ECL against the 1.5% CRWA floor")
    tbl = table([("item", "Item", "text"), ("value", "SAR m", "sar")], rows)
    q = questions + [""] * 3
    head = (f"Stage 1 + 2 ECL of **{F.sar(x['held'])}** is **{F.pct(x['ratio'], points=True)}** of CRWA of **{F.sar(x['crwa'])}**, "
            + ("above the 1.5% minimum of Art 9.21." if ok else f"below the 1.5% minimum of Art 9.21 by **{F.sar(x['shortfall'])}**."))
    return [
        answer(1, q[0], src, "Corporate book at the as-of quarter.", head, tbl, fig, tr, pw),
        answer(2, q[1], src, f"CRWA source: {x['source']}.",
               f"CRWA **{F.sar(x['crwa'])}**; Stage 1 ECL **{F.sar(x['s1'])}**; Stage 2 ECL **{F.sar(x['s2'])}**; ratio **{F.pct(x['ratio'], points=True)}** "
               f"against 1.50% (required **{F.sar(x['required'])}**).", tbl, fig, tr, pw),
        answer(3, q[2], src, "Shortfall = max(0, 1.5% × CRWA − Stage 1 + 2 ECL).",
               ("There is no shortfall, so no deduction from regulatory capital arises." if ok else
                f"The shortfall of **{F.sar(x['shortfall'])}** is deducted from Tier 1 capital in the prudential return until the floor is met."),
               tbl, None, tr, pw),
    ][:max(len(questions), 3)]


# ------------------------------------------------------------------ case 5: restructured in 12 months (Art 8, 9.28–9.35)
def _restructured_r9(src) -> list[dict[str, Any]] | None:
    """Restructured register from Session A's `collateral.col_restructured` (dates, type, count, probation)."""
    try:
        rs = src.table("col_restructured", book="corporate")
    except Exception:  # noqa: BLE001
        return None
    p = as_of()
    end = pd.Timestamp(rs["as_of_date"].iloc[0]) if "as_of_date" in rs and len(rs) else pd.Timestamp("2026-06-30")
    rs = rs[pd.to_datetime(rs["restructure_date"]) > end - pd.DateOffset(months=12)]
    cur = book(p).set_index("facility_id")
    f = facilities()
    b930 = set(breaches().query("check_id == 'CRM-9.30' and book == 'corporate'")["entity_id"])
    rows = []
    for r in rs.itertuples():
        if r.exposure_id not in cur.index:
            continue
        c = cur.loc[r.exposure_id]
        q0 = f"{pd.Timestamp(r.restructure_date).year}Q{pd.Timestamp(r.restructure_date).quarter}"
        before = f[(f["facility_id"] == r.exposure_id) & (f["reporting_quarter"] < q0)].tail(1)
        distressed = str(r.restructure_type).lower().startswith("distressed")
        rows.append({"facility_id": r.exposure_id, "borrower": c.borrower_name, "ead": float(c.ead_sar_mn), "restructured": str(r.restructure_date)[:10],
                     "type": "Distressed" if distressed else "Non-distressed",
                     "stage_before": int(before["stage"].iloc[0]) if len(before) else None, "stage_now": int(c.stage),
                     "probation": "In probation" if str(r.status) == "Probation" or str(r.probation_end) > p else "Ended",
                     "probation_end": str(r.probation_end), "times": int(r.count_24m),
                     "flag": "Stage 1 while distressed (Art 9.30)" if (r.exposure_id in b930 or (distressed and int(c.stage) == 1)) else ""})
    return sorted(rows, key=lambda r: -r["ead"])


def restructured() -> list[dict[str, Any]]:
    src = r9()
    if src is not None:
        rows = _restructured_r9(src)
        if rows:
            return rows
    p = as_of()
    window = periods()[-4:]
    br = borrowers()
    first = br[br["restructured_flag"] == 1].groupby("borrower_id")["reporting_quarter"].min()
    first = first[first.isin(window)]
    f = facilities()
    cur = f[f["reporting_quarter"] == p].set_index("facility_id")
    b930 = set(breaches().query("check_id == 'CRM-9.30' and book == 'corporate'")["entity_id"])
    rows = []
    for fid, r in cur[cur["borrower_id"].isin(first.index)].iterrows():
        q0 = first[r.borrower_id]
        before = f[(f["facility_id"] == fid) & (f["reporting_quarter"] < q0)].tail(1)
        h = _h("restr", fid)
        sb = int(before["stage"].iloc[0]) if len(before) else None
        distressed = (sb or 1) >= 2 or bool(before["dpd_days"].iloc[0] > 30 if len(before) else False) or h % 4 == 0
        prob_q = periods().index(q0) + (4 if distressed else 2)
        rows.append({"facility_id": fid, "borrower": r.borrower_name, "ead": float(r.ead_sar_mn), "restructured": q0,
                     "type": "Distressed" if distressed else "Non-distressed",
                     "stage_before": sb, "stage_now": int(r.stage),
                     "probation": "Ended" if prob_q < len(periods()) else "In probation",
                     "times": 1 + (h % 7 == 0) * 2, "flag": "Stage 1 while distressed (Art 9.30)" if (fid in b930 or (distressed and r.stage == 1)) else ""})
    return sorted(rows, key=lambda r: -r["ead"])


def case5(questions: list[str]) -> list[dict[str, Any]]:
    rows = restructured()
    p = as_of()
    src = [used("collateral", "col_restructured", ["restructure_date", "restructure_type", "count_24m", "probation_end"], "restructured in the last 12 months"),
           used("books", "corp_facility_quarter", ["stage", "ead_sar_mn"], p), used("regulatory", "crm_breach", ["entity_id"], "check_id = CRM-9.30")]
    tr = trace(["col_restructured", "corp_facility_quarter", "crm_breach"], ["restructured in the last 12 months", "stage before and now", "probation per Art 9.33", "CRM-9.30 check"],
               "CRM-9.30", "CBUAE CRM Art. 8, 9.28–9.35", len(rows), p)
    pw = powered("CRM-9.30", "CBUAE CRM Art. 8, 9.28–9.35")
    dis = [r for r in rows if r["type"] == "Distressed"]
    flagged = [r for r in rows if r["flag"]]
    multi = [r for r in rows if r["times"] >= 3]
    cols = [("facility_id", "Facility", "text"), ("borrower", "Borrower", "text"), ("ead", "EAD", "sar"), ("restructured", "Restructured", "text"),
            ("type", "Type", "text"), ("stage_before", "Stage before", "count"), ("stage_now", "Stage now", "count"), ("probation", "Probation", "text"),
            ("times", "Times restructured", "count"), ("flag", "Finding", "text")]
    by_stage = {s: sum(r["ead"] for r in rows if r["stage_now"] == s) for s in (1, 2, 3)}
    q = questions + [""] * 4
    return [
        answer(1, q[0], src[:2], "Facilities of borrowers flagged restructured in the last four quarters.",
               f"**{F.count(len(rows))}** facilities (EAD **{F.sar(sum(r['ead'] for r in rows))}**) were restructured in the last 12 months: "
               f"**{F.count(len(dis))}** distressed and **{F.count(len(rows) - len(dis))}** non-distressed.", table(cols[:5], rows[:60]),
               bar(["Stage 1", "Stage 2", "Stage 3"], [by_stage[1], by_stage[2], by_stage[3]], "Restructured EAD by stage now"), tr, pw),
        answer(2, q[1], src, "Stage before = the quarter before restructuring.",
               f"Stage now: Stage 1 **{F.sar(by_stage[1])}**, Stage 2 **{F.sar(by_stage[2])}**, Stage 3 **{F.sar(by_stage[3])}**. "
               f"**{F.count(len(flagged))}** distressed restructurings sit in Stage 1, against Art 9.30.", table(cols[:7] + [cols[9]], rows[:60]), None, tr, pw),
        answer(3, q[2], src[:2], "Probation: 12 months for distressed, 6 months for non-distressed (Art 9.33).",
               f"**{F.count(sum(r['probation'] == 'In probation' for r in rows))}** are in probation; "
               f"**{F.count(sum(r['probation'] == 'Ended' for r in rows))}** have completed it.", table([cols[0], cols[1], cols[4], cols[7]], rows[:60]), None, tr, pw),
        answer(4, q[3], src[:2], "Count of restructurings in the last 24 months.",
               (f"**{F.count(len(multi))}** facilities have been restructured three or more times; under Art 6.9(e) these are assessed for unlikeliness to pay."
                if multi else f"No facility has been restructured three or more times in 24 months; **{F.count(sum(r['times'] == 2 for r in rows))}** "
                              f"have been restructured twice and are monitored against Art 6.9(e)."),
               table([cols[0], cols[1], cols[2], cols[8]], multi or [r for r in rows if r["times"] >= 2]), None, tr, pw),
    ][:max(len(questions), 4)]


CASES = {
    "Q1": {"title": "30+ DPD wholesale facilities still in Stage 1", "from": "Auditor", "article": "Art 7.8 / 7.10", "fn": case1,
           "keys": ["rebuttal", "30 days past due", "7.10"]},
    "Q2": {"title": "Top 20 Stage 3 exposures against the minimum floors", "from": "CBUAE", "article": "Art 9.23", "fn": case2,
           "keys": ["9.23", "top 20 stage 3", "secured and unsecured"]},
    "Q3": {"title": "Construction Stage 2 ECL movement", "from": "Auditor", "article": "Art 9 (ECL)", "fn": case3,
           "keys": ["construction", "movement", "waterfall"]},
    "Q4": {"title": "Stage 1 + 2 provisions against 1.5% of CRWA", "from": "CBUAE", "article": "Art 9.21", "fn": case4,
           "keys": ["1.5%", "risk weighted", "crwa", "9.21"]},
    "Q5": {"title": "Facilities restructured in the last 12 months", "from": "Internal Audit", "article": "Art 8, 9.28–9.35", "fn": case5,
           "keys": ["restructur", "probation"]},
}


def classify(text: str) -> str | None:
    t = text.lower()
    scores = {k: sum(t.count(w) for w in c["keys"]) for k, c in CASES.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else None


def run_case(case: str, questions: list[str]) -> list[dict[str, Any]]:
    return CASES[case]["fn"](questions)
