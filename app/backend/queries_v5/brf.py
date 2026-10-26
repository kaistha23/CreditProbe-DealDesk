"""BRF studio: four preconfigured credit returns, each a field map over existing domains, a process flow,
proposed checks, and a run that populates the grid (PLAN_R9 Session F, F2).

Returns (generic titles): R1 classification and provisions by stage; R2 large exposures; R3 sector
distribution; R4 past due, restructured and NPL. Every figure comes from the corporate book at the chosen
period, so the totals equal the Cockpit's.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from backend.common import format as F
from backend.queries_v5 import engine as E

RETURNS: dict[str, dict[str, Any]] = {
    "R1": {"title": "Classification and provisions by stage", "frequency": "Quarterly", "article": "CBUAE CRM Art. 9"},
    "R2": {"title": "Large exposures", "frequency": "Quarterly", "article": "CBUAE Large Exposures"},
    "R3": {"title": "Sector distribution of credit", "frequency": "Quarterly", "article": "CBUAE CRM Art. 4"},
    "R4": {"title": "Past due, restructured and non-performing", "frequency": "Quarterly", "article": "CBUAE CRM Art. 6, 8"},
}

SRC = "books.corp_facility_quarter"


def _field(fid: str, label: str, dataset: str, fields: list[str], filters: str, calc: str) -> dict[str, Any]:
    return {"id": fid, "label": label, "domain": dataset.split(".")[0], "dataset": dataset, "fields": fields, "filters": filters, "calc": calc}


def field_map(rid: str) -> list[dict[str, Any]]:
    if rid == "R1":
        out = []
        for s in (1, 2, 3):
            out += [_field(f"S{s}_EAD", f"Stage {s} gross exposure", SRC, ["ead_sar_mn"], f"stage = {s}", "Σ EAD"),
                    _field(f"S{s}_ECL", f"Stage {s} provisions (ECL)", SRC, ["ecl_sar_mn"], f"stage = {s}", "Σ ECL"),
                    _field(f"S{s}_COV", f"Stage {s} coverage", SRC, ["ecl_sar_mn", "ead_sar_mn"], f"stage = {s}", "Σ ECL ÷ Σ EAD")]
        return out + [_field("TOT_EAD", "Total gross exposure", SRC, ["ead_sar_mn"], "all", "Σ EAD"),
                      _field("TOT_ECL", "Total provisions", SRC, ["ecl_sar_mn"], "all", "Σ ECL")]
    if rid == "R2":
        return [_field("GRP", "Group", "books.corp_borrower_quarter", ["group_id", "group_name"], "group of the borrower", "group key"),
                _field("GRP_EAD", "Group exposure", SRC, ["ead_sar_mn"], "join borrower → group", "Σ EAD by group"),
                _field("CAP", "Capital base", "collateral.col_crwa", ["crwa_sar_mn"], "all", "CRWA × 17% capital ratio"),
                _field("PCT_CAP", "Exposure as % of capital", "derived", ["GRP_EAD", "CAP"], "", "GRP_EAD ÷ CAP"),
                _field("LE_FLAG", "Large exposure (≥ 10%)", "derived", ["PCT_CAP"], "", "PCT_CAP ≥ 10%"),
                _field("BREACH", "Above the 25% limit", "derived", ["PCT_CAP"], "", "PCT_CAP > 25%")]
    if rid == "R3":
        return [_field("SECTOR", "Economic sector", SRC, ["sector"], "all", "group by sector"),
                _field("SEC_EAD", "Gross exposure", SRC, ["ead_sar_mn"], "by sector", "Σ EAD"),
                _field("SEC_S3", "Stage 3 exposure", SRC, ["ead_sar_mn"], "stage = 3", "Σ EAD"),
                _field("SEC_ECL", "Provisions", SRC, ["ecl_sar_mn"], "by sector", "Σ ECL"),
                _field("SEC_SHARE", "Share of book", "derived", ["SEC_EAD"], "", "SEC_EAD ÷ Σ EAD")]
    return [_field("PD_1_30", "Past due 1–30 days", SRC, ["dpd_days", "ead_sar_mn"], "1 ≤ DPD ≤ 30", "Σ EAD"),
            _field("PD_31_90", "Past due 31–90 days", SRC, ["dpd_days", "ead_sar_mn"], "31 ≤ DPD ≤ 90", "Σ EAD"),
            _field("PD_90", "Past due over 90 days", SRC, ["dpd_days", "ead_sar_mn"], "DPD > 90", "Σ EAD"),
            _field("RESTR", "Restructured", "books.corp_borrower_quarter", ["restructured_flag"], "restructured_flag = 1", "Σ EAD of facilities"),
            _field("NPL", "Non-performing (Stage 3)", SRC, ["stage", "ead_sar_mn"], "stage = 3", "Σ EAD"),
            _field("NPL_RATIO", "NPL ratio", "derived", ["NPL", "TOT"], "", "NPL ÷ total EAD")]


def flow(rid: str) -> dict[str, Any]:
    """Process flow: sources (blue) → transformations (purple) → calculations (amber) → checks (red) → outputs (green)."""
    fm = field_map(rid)
    datasets = sorted({f["dataset"] for f in fm if f["dataset"] != "derived"})
    nodes = [{"id": f"src:{d}", "kind": "source", "label": d.split(".")[-1], "detail": f"Domain {d.split('.')[0]}"} for d in datasets]
    nodes.append({"id": "tx:period", "kind": "transform", "label": "Filter to period", "detail": "reporting_quarter = locked period"})
    nodes.append({"id": "tx:join", "kind": "transform", "label": "Join and group", "detail": "facility → borrower → group / sector"})
    for f in fm:
        nodes.append({"id": f"calc:{f['id']}", "kind": "calc", "label": f["label"], "detail": f"{f['calc']} where {f['filters'] or '—'}"})
    for c in checks(rid):
        nodes.append({"id": f"chk:{c['id']}", "kind": "check", "label": c["label"], "detail": c["rule"]})
    nodes.append({"id": "out:grid", "kind": "output", "label": f"{rid} return grid", "detail": RETURNS[rid]["title"]})
    edges = [{"from": n["id"], "to": "tx:period"} for n in nodes if n["kind"] == "source"]
    edges.append({"from": "tx:period", "to": "tx:join"})
    edges += [{"from": "tx:join", "to": n["id"]} for n in nodes if n["kind"] == "calc"]
    edges += [{"from": n["id"], "to": "out:grid"} for n in nodes if n["kind"] == "check"]
    edges += [{"from": f"calc:{fm[0]['id']}", "to": n["id"]} for n in nodes if n["kind"] == "check"]
    return {"nodes": nodes, "edges": edges}


def checks(rid: str) -> list[dict[str, Any]]:
    base = [{"id": "TOT_BOOK", "label": "Total equals the book", "rule": "Σ EAD of the return = Σ EAD of the book at the period"}]
    if rid == "R1":
        return base + [{"id": "STAGE_ECL", "label": "Stage totals equal ECL", "rule": "Σ stage provisions = Σ ECL of the book"},
                       {"id": "DPD_STAGE", "label": "DPD consistent with stage", "rule": "no DPD > 90 outside Stage 3; no DPD > 30 in Stage 1"}]
    if rid == "R2":
        return base + [{"id": "GRP_PRESENT", "label": "Every borrower has a group", "rule": "group_id present for each borrower"}]
    if rid == "R3":
        return base + [{"id": "SECTOR_CODES", "label": "Sector codes present", "rule": "no blank sector"}]
    return base + [{"id": "DPD_STAGE", "label": "DPD consistent with stage", "rule": "no DPD > 90 outside Stage 3"}]


def _check_results(rid: str, cur: pd.DataFrame, grid_total: float, ecl_total: float | None = None) -> list[dict[str, Any]]:
    book_ead = float(cur["ead_sar_mn"].sum())
    res = []
    for c in checks(rid):
        if c["id"] == "TOT_BOOK":
            ok = abs(grid_total - book_ead) < 0.01
            res.append({**c, "status": "PASS" if ok else "FAIL", "detail": f"Return {F.sar(grid_total)} · book {F.sar(book_ead)}"})
        elif c["id"] == "STAGE_ECL":
            b = float(cur["ecl_sar_mn"].sum())
            ok = abs((ecl_total or 0) - b) < 0.01
            res.append({**c, "status": "PASS" if ok else "FAIL", "detail": f"Return {F.sar(ecl_total)} · book {F.sar(b)}"})
        elif c["id"] == "DPD_STAGE":
            bad90 = int(((cur["dpd_days"] > 90) & (cur["stage"] < 3)).sum())
            bad30 = int(((cur["dpd_days"] > 30) & (cur["stage"] == 1)).sum())
            res.append({**c, "status": "PASS" if bad90 + bad30 == 0 else "FAIL", "detail": f"{F.count(bad90)} over 90 days outside Stage 3 · {F.count(bad30)} over 30 days in Stage 1"})
        elif c["id"] == "SECTOR_CODES":
            n = int(cur["sector"].isna().sum() + (cur["sector"].astype(str).str.strip() == "").sum())
            res.append({**c, "status": "PASS" if n == 0 else "FAIL", "detail": f"{F.count(n)} facilities without a sector"})
        elif c["id"] == "GRP_PRESENT":
            b = E.borrowers()
            b = b[b["reporting_quarter"] == cur["reporting_quarter"].iloc[0]]
            n = int(b["group_id"].isna().sum())
            res.append({**c, "status": "PASS" if n == 0 else "FAIL", "detail": f"{F.count(n)} borrowers without a group (reported standalone)"})
    return res


def run(rid: str, period: str | None = None) -> dict[str, Any]:
    period = period or E.as_of()
    cur = E.book(period)
    if cur.empty:
        raise ValueError(f"No book at {period}.")
    prev_p = E.periods()[E.periods().index(period) - 1] if E.periods().index(period) > 0 else None
    prev = E.book(prev_p) if prev_p else None
    if rid == "R1":
        rows = []
        for s in (1, 2, 3):
            x = cur[cur["stage"] == s]
            ead, ecl = float(x["ead_sar_mn"].sum()), float(x["ecl_sar_mn"].sum())
            rows.append({"line": f"Stage {s}", "count": len(x), "ead": ead, "ecl": ecl, "coverage": ecl / ead * 100 if ead else None})
        tot = {"line": "Total", "count": len(cur), "ead": float(cur["ead_sar_mn"].sum()), "ecl": float(cur["ecl_sar_mn"].sum())}
        tot["coverage"] = tot["ecl"] / tot["ead"] * 100
        cols = [("line", "Line", "text"), ("count", "Facilities", "count"), ("ead", "Gross exposure", "sar"), ("ecl", "Provisions", "sar"), ("coverage", "Coverage", "pct")]
        res = _check_results(rid, cur, tot["ead"], sum(r["ecl"] for r in rows))
        note_bits = []
        if prev is not None:
            for s in (2, 3):
                d = float(cur.loc[cur["stage"] == s, "ecl_sar_mn"].sum() - prev.loc[prev["stage"] == s, "ecl_sar_mn"].sum())
                note_bits.append(f"Stage {s} provisions {'rose' if d >= 0 else 'fell'} by **{F.sar(abs(d))}** against {prev_p}")
    elif rid == "R2":
        b = E.borrowers()
        b = b[b["reporting_quarter"] == period][["borrower_id", "group_id", "group_name", "borrower_name"]]
        x = cur.merge(b[["borrower_id", "group_id", "group_name"]], on="borrower_id", how="left")
        x["grp"] = x["group_id"].fillna(x["borrower_id"])
        x["grp_name"] = x["group_name"].fillna(x["borrower_name"])
        cap = float(E.crwa_frame(cur)["crwa_sar_mn"].sum()) * E.CAPITAL_RATIO
        g = x.groupby(["grp", "grp_name"]).agg(ead=("ead_sar_mn", "sum"), members=("borrower_id", "nunique"), ecl=("ecl_sar_mn", "sum")).reset_index()
        g["pct_cap"] = g["ead"] / cap * 100
        g = g.sort_values("ead", ascending=False)
        le = g[g["pct_cap"] >= E.LARGE_REPORT_PCT]
        top = le if len(le) >= 10 else g.head(max(10, len(le)))
        rows = [{"line": r.grp_name, "group": r.grp, "members": int(r.members), "ead": float(r.ead), "pct_cap": float(r.pct_cap),
                 "status": "Above limit" if r.pct_cap > E.LARGE_LIMIT_PCT else ("Large exposure" if r.pct_cap >= E.LARGE_REPORT_PCT else "Below threshold")} for r in top.itertuples()]
        tot = {"line": f"Capital base {F.sar(cap)} · {F.count(len(le))} large exposures", "ead": float(le["ead"].sum()) if len(le) else 0.0,
               "pct_cap": float(le["ead"].sum() / cap * 100) if len(le) else 0.0}
        cols = [("line", "Group", "text"), ("group", "Group ID", "text"), ("members", "Members", "count"), ("ead", "Exposure", "sar"), ("pct_cap", "% of capital", "pct"), ("status", "Status", "text")]
        res = _check_results(rid, cur, float(g["ead"].sum()))
        note_bits = [f"The largest group is **{rows[0]['line']}** at **{F.pct(rows[0]['pct_cap'], points=True)}** of capital",
                     f"**{F.count(sum(r['status'] == 'Above limit' for r in rows))}** groups are above the 25% limit"]
    elif rid == "R3":
        g = cur.groupby("sector").agg(ead=("ead_sar_mn", "sum"), ecl=("ecl_sar_mn", "sum"), count=("facility_id", "count")).reset_index()
        s3 = cur[cur["stage"] == 3].groupby("sector")["ead_sar_mn"].sum()
        tot_ead = float(cur["ead_sar_mn"].sum())
        rows = [{"line": r.sector, "count": int(r.count), "ead": float(r.ead), "s3": float(s3.get(r.sector, 0.0)), "ecl": float(r.ecl), "share": float(r.ead) / tot_ead * 100}
                for r in g.sort_values("ead", ascending=False).itertuples()]
        tot = {"line": "Total", "count": len(cur), "ead": tot_ead, "s3": float(s3.sum()), "ecl": float(cur["ecl_sar_mn"].sum()), "share": 100.0}
        cols = [("line", "Sector", "text"), ("count", "Facilities", "count"), ("ead", "Gross exposure", "sar"), ("s3", "Stage 3", "sar"), ("ecl", "Provisions", "sar"), ("share", "Share", "pct")]
        res = _check_results(rid, cur, sum(r["ead"] for r in rows))
        note_bits = [f"**{rows[0]['line']}** is the largest sector at **{F.pct(rows[0]['share'], points=True)}** of the book"]
    else:
        b = E.borrowers()
        rf = set(b[(b["reporting_quarter"] == period) & (b["restructured_flag"] == 1)]["borrower_id"])
        tot_ead = float(cur["ead_sar_mn"].sum())
        def s(mask) -> float:
            return float(cur.loc[mask, "ead_sar_mn"].sum())
        lines = [("Performing, not past due", (cur["dpd_days"] == 0) & (cur["stage"] < 3)),
                 ("Past due 1–30 days", cur["dpd_days"].between(1, 30)), ("Past due 31–90 days", cur["dpd_days"].between(31, 90)),
                 ("Past due over 90 days", cur["dpd_days"] > 90), ("Restructured", cur["borrower_id"].isin(rf)),
                 ("Non-performing (Stage 3)", cur["stage"] == 3)]
        rows = [{"line": n, "count": int(m.sum()), "ead": s(m), "share": s(m) / tot_ead * 100} for n, m in lines]
        tot = {"line": "Total book", "count": len(cur), "ead": tot_ead, "share": 100.0}
        cols = [("line", "Line", "text"), ("count", "Facilities", "count"), ("ead", "Exposure", "sar"), ("share", "% of book", "pct")]
        res = _check_results(rid, cur, tot_ead)
        note_bits = [f"NPL ratio **{F.pct(rows[-1]['share'], points=True)}**"]
        if prev is not None:
            p3 = float(prev.loc[prev["stage"] == 3, "ead_sar_mn"].sum()) / float(prev["ead_sar_mn"].sum()) * 100
            note_bits.append(f"against **{F.pct(p3, points=True)}** at {prev_p}")
    return {"return_id": rid, "title": RETURNS[rid]["title"], "period": period, "grid": E.table(cols, rows, tot), "checks": res,
            "note": "; ".join(note_bits) + ".", "powered_by": E.powered(f"BRF-{rid}", RETURNS[rid]["article"]),
            "trace": E.trace(["corp_facility_quarter", "corp_borrower_quarter"], [n["label"] for n in flow(rid)["nodes"] if n["kind"] == "transform"],
                             f"BRF-{rid}", RETURNS[rid]["article"], len(cur), period)}
