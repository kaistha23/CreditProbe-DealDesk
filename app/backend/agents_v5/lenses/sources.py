"""The five sources the monitoring agent plans from (PLAN_R11_AGENTS K2), each a read-only tool over existing engines.

  composition   the scope's concentrations, large exposures and growth segments (lens engine)
  appetite      the risk-appetite limits and triggers (data/dealdesk/params/v1/risk_appetite.json, read-only)
  regulation    the CBUAE CRM metric library (backend.lenses_v5.crm_intel) and breach checks (backend.regulatory.crm_checks)
  movement      which catalogue metrics moved most last quarter and which are volatile (lens engine)
  materiality   the EAD and ECL each candidate speaks for (lens engine)

Each returns plain data plus the evidence it used (the SQL or the file and row), never a typed figure.
"""
from __future__ import annotations

import json
import pathlib
import statistics
from typing import Any

from backend.agents_v5.lenses import metrics as M
from backend.lenses_v5.catalogue import DIMS, METRICS
from backend.lenses_v5.engine import ENGINE, TABLE, _q

V5 = pathlib.Path(__file__).resolve().parents[3]
RISK_APPETITE = V5 / "data" / "dealdesk" / "params" / "v1" / "risk_appetite.json"
DEFAULT_TRIGGER = 0.9          # trigger = 90% of the limit when the row carries none (Session L adds triggers)
RATING_BUCKETS = {"IG": ("AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB", "BBB-"), "BB": ("BB+", "BB", "BB-"),
                  "B": ("B+", "B", "B-"), "CCC-C": ("CCC+", "CCC", "CCC-", "CC", "C")}


def segment_dim(book: str, filters: list[dict[str, Any]]) -> str:
    dims = {f["dim"] for f in filters}
    if book == "corporate":
        return "sub_sector" if "sector" in dims else "sector"
    return "sub_product" if "product" in dims else "product"


# ------------------------------------------------------------------ composition
def composition(book: str, filters: list[dict[str, Any]], period: str = "") -> dict[str, Any]:
    p = period or ENGINE.as_of(book)
    T = TABLE[book]
    w = ENGINE.where(book, filters)
    seg = segment_dim(book, filters)
    g = M.grid(book, p, n=5)
    p4 = g[0]
    sql = (f"SELECT {DIMS[seg].sql} AS k, SUM(CASE WHEN period = {_q(p)} THEN ead_sar_mn END) AS e1, "
           f"SUM(CASE WHEN period = {_q(p4)} THEN ead_sar_mn END) AS e0 FROM {T} WHERE period IN ({_q(p)}, {_q(p4)}) AND {w} GROUP BY 1")
    rows = ENGINE.q(sql)
    tot1 = sum(r["e1"] or 0 for r in rows) or 1
    tot0 = sum(r["e0"] or 0 for r in rows) or 1
    segs = []
    for r in rows:
        if r["k"] is None:
            continue
        sh = (r["e1"] or 0) / tot1 * 100
        gr = ((r["e1"] or 0) / r["e0"] - 1) * 100 if r["e0"] else None
        segs.append({"segment": str(r["k"]), "ead": round(r["e1"] or 0, 2), "share": round(sh, 2), "growth_4q": None if gr is None else round(gr, 2)})
    segs.sort(key=lambda s: -s["share"])
    book_growth = (tot1 / tot0 - 1) * 100
    growth = sorted([s for s in segs if s["growth_4q"] is not None and s["share"] >= 2 and s["growth_4q"] > book_growth],
                    key=lambda s: -(s["growth_4q"] or 0))[:3]
    top = [s for s in segs if s["share"] >= 7][:6] or segs[:3]
    big = ENGINE.q(f"SELECT owner_id, ANY_VALUE(owner_name) AS name, SUM(ead_sar_mn) AS e FROM {T} WHERE period = {_q(p)} AND {w} "
                   f"GROUP BY 1 ORDER BY 3 DESC LIMIT 5")
    return {"period": p, "since": p4, "segment_dim": seg, "segments": segs, "top_segments": top, "growth_segments": growth,
            "book_growth_4q": round(book_growth, 2), "ead": round(tot1, 2),
            "largest_names": [{"owner_id": r["owner_id"], "name": r["name"], "ead": round(r["e"], 2)} for r in big],
            "evidence": [{"tool": "lens.composition", "sql": sql}]}


# ------------------------------------------------------------------ risk appetite
def _levels(row: dict[str, Any], key: str | None, scale: float) -> tuple[float, float, float | None, str]:
    """(limit, trigger, appetite) in the metric's own units, and where the trigger came from."""
    if key is None:
        lim, trig, app = row.get("limit"), row.get("trigger"), row.get("appetite")
    else:
        lim = (row.get("limits") or {}).get(key)
        trig = (row.get("triggers") or {}).get(key, row.get("trigger") if not isinstance(row.get("trigger"), dict) else None)
        app = (row.get("appetites") or {}).get(key)
    t = trig * scale if isinstance(trig, (int, float)) else lim * scale * DEFAULT_TRIGGER
    return lim * scale, t, (app * scale if isinstance(app, (int, float)) else None), ("row" if isinstance(trig, (int, float)) else "default 90% of limit")


def appetite(book: str) -> dict[str, Any]:
    """Portfolio-level rows of the risk appetite that the books can measure (each as a monitored metric with its limit,
    trigger and appetite in the metric's units), and the rows they cannot, with why."""
    raw = json.loads(RISK_APPETITE.read_text())
    meas, skipped = [], []

    def add(row: dict[str, Any], rid: str, label: str, mkind: str, unit: str, key: str | None, scale: float, segment: dict[str, Any] | None = None,
            metric: str = "ead") -> None:
        lim, trig, app, src = _levels(row, key, scale)
        meas.append({"row": rid, "label": label, "mkind": mkind, "metric": metric, "unit": unit, "segment": segment, "limit": lim, "trigger": trig,
                     "appetite": app, "basis": row.get("basis", ""), "kind": row["kind"], "trigger_source": src})
    for row in raw.get("rows", []):
        name = row["name"]
        if book != "corporate":
            skipped.append({"row": name, "why": "The risk-appetite statement covers the corporate book."})
            continue
        if row.get("scope") == "new_business" or row.get("direction") == "min":
            skipped.append({"row": name, "why": "A new-business limit: the Deal Desk pipeline tests it on pending deals."})
        elif name == "sector_appetite":
            for sec in (row.get("limits") or {}):
                add(row, f"{name}:{sec}", f"{sec} share of the corporate book", "share", "pct", sec, 100, {"dim": "sector", "values": [sec]})
        elif name == "sector_policy":
            add(row, name, "Largest sector share", "max_share", "pct", None, 100, {"dim": "sector", "values": []})
        elif name == "rating_bucket":
            for bkt, lim in (row.get("limits") or {}).items():
                if lim >= 1.0:
                    skipped.append({"row": f"{name}:{bkt}", "why": "No limit on investment grade (100%)."})
                    continue
                add(row, f"{name}:{bkt}", f"Rating bucket {bkt} share", "share", "pct", bkt, 100, {"dim": "rating_current", "values": list(RATING_BUCKETS[bkt])})
        elif name == "single_name":
            add(row, name, "Largest single obligor", "single_name", "sar_mn", None, 1)
        elif name == "top20_obligor_share":
            add(row, name, "Top 20 obligors' share of EAD", "top20", "pct", None, 100)
        elif name == "sector_hhi":
            add(row, name, "Sector concentration (HHI)", "hhi", "count", None, 10000, {"dim": "sector", "values": []})
        elif name == "sub_ig_share":
            add(row, name, "Sub-investment-grade share", "share", "pct", None, 100,
                {"dim": "rating_current", "values": [*RATING_BUCKETS["BB"], *RATING_BUCKETS["B"], *RATING_BUCKETS["CCC-C"]]})
        elif name == "re_construction_share":
            add(row, name, "Real estate and construction share", "share", "pct", None, 100, {"dim": "sector", "values": list(row.get("sectors") or [])})
        elif name == "region_share":
            add(row, name, "Largest region share", "max_share", "pct", None, 100, {"dim": "region", "values": []})
        elif name == "stage2_share":
            add(row, name, "Stage 2 share", "catalogue", "pct", None, 100, metric="stage2_share")
        elif name in ("group_connected", "group_large_exposure", "connected_lending_share"):
            skipped.append({"row": name, "why": "The lens books carry a group name that clusters hundreds of obligors, not the "
                                                "connected-group register; Deal Desk tests this limit per proposal."})
        elif name in ("collateral_type", "unsecured_share"):
            skipped.append({"row": name, "why": "Collateral type and security are not columns of the lens relations (data gap)."})
        elif name == "cost_of_risk_bps":
            skipped.append({"row": name, "why": "Expected cost of risk is a Deal Desk pipeline measure; the books carry the realised cost of "
                                                "risk, which the regulation source monitors (CBUAE CRM Art. 9.2)."})
        else:
            skipped.append({"row": name, "why": "A deal-level limit: Deal Desk checks it on each proposal."})
    return {"file": "data/dealdesk/params/v1/risk_appetite.json", "version": raw.get("version"), "effective_from": raw.get("effective_from"),
            "measurable": meas, "skipped": skipped, "evidence": [{"tool": "lenses_risk_appetite", "file": "data/dealdesk/params/v1/risk_appetite.json"}]}


def largest_sector(book: str, period: str) -> str:
    r = ENGINE.q(f"SELECT sector AS k FROM {TABLE[book]} WHERE period = {_q(period)} GROUP BY 1 ORDER BY SUM(ead_sar_mn) DESC LIMIT 1")
    return str(r[0]["k"]) if r else ""


# ------------------------------------------------------------------ regulation
#: CBUAE CRM library metrics the lens catalogue measures, with the threshold the Standards (or the Board) set.
REG_METRICS: list[tuple[str, str, str, dict[str, Any] | None]] = [
    # library id, catalogue metric, article, a fixed regulatory threshold if the Standards give one
    ("CRM-M11", "stage2_share", "CBUAE CRM Art. 7.2", None),
    ("CRM-M44", "stage3_share", "CBUAE CRM Art. 12.3", {"logic": "absolute", "level": 5.0, "direction": "up"}),
    ("CRM-M05", "npl_ratio", "CBUAE CRM Art. 12.3", {"logic": "absolute", "level": 5.0, "direction": "up"}),
    ("CRM-M03", "dpd30_share", "CBUAE CRM Art. 9.5", None),
    ("CRM-M06", "dpd90_share", "CBUAE CRM Art. 6.4", None),
    ("CRM-M17", "coverage", "CBUAE CRM Art. 9.2", None),
    ("CRM-M19", "cost_of_risk", "CBUAE CRM Art. 9.2", None),
    ("CRM-M12", "downgraded", "CBUAE CRM Art. 7.11", None),
    ("CRM-M13", "covenant_breaches", "CBUAE CRM Art. 7.11", None),
    ("CRM-M39", "severe_ead_share", "CBUAE CRM Art. 11.6", None),
    ("CRM-M42", "high_critical", "CBUAE CRM Art. 11.6", None),
    ("CRM-M40", "watchlist", "CBUAE CRM Art. 11.6", None),
    ("CRM-M43", "pd", "CBUAE CRM Art. 13.2", None),
]


def regulation(book: str, period: str = "") -> dict[str, Any]:
    from backend.lenses_v5 import crm_intel
    p = period or ENGINE.as_of(book)
    lib = {m["id"]: m for m in crm_intel.LIBRARY}
    out = []
    for lid, key, art, th in REG_METRICS:
        if book not in METRICS[key].books:
            continue
        out.append({"library_id": lid, "metric": key, "article": art, "name": lib.get(lid, {}).get("name", METRICS[key].label),
                    "threshold": th, "standard": lib.get(lid, {}).get("threshold", "")})
    checks = []
    now = M.crm(book, p)
    for cid in M.CRM_IDS[book]:
        c = now.get(cid)
        if c is None:
            continue
        checks.append({"check_id": cid, "title": c["title"], "article": "CBUAE CRM " + c["article"], "breaches": c["breaches"],
                       "ead": round(c["ead"], 2), "shortfall": round(c["shortfall"], 2)})
    return {"period": p, "metrics": out, "checks": checks, "library_size": len(crm_intel.LIBRARY),
            "gaps": [m["id"] for m in crm_intel.LIBRARY if m["status"] == "gap"],
            "evidence": [{"tool": "lens.regulation", "ref": "backend.lenses_v5.crm_intel.LIBRARY"},
                         {"tool": "lens.regulation", "ref": f"backend.regulatory.crm_checks.run_book('{book}', '{p}')"}]}


# ------------------------------------------------------------------ recent movement
MOVABLE = ("sum", "ratio", "wavg", "distinct", "cor")


def movement(book: str, filters: list[dict[str, Any]], period: str = "") -> dict[str, Any]:
    """Every catalogue metric of the book: last move, its z-score against the previous 8 moves, and volatility."""
    p = period or ENGINE.as_of(book)
    g = M.grid(book, p, n=12)
    keys = [k for k, m in METRICS.items() if book in m.books and m.kind in MOVABLE and m.source in ("Books", "Early Warning")
            and k not in ("limit", "drawn", "exposures", "obligors")]
    rows = []
    for k in keys:
        d = M.mdef(label=METRICS[k].label, unit=METRICS[k].unit, book=book, kind="catalogue", metric=k, filters=filters, better=METRICS[k].better)
        s, _ = M.series(d, g)
        vals = [s.get(x) for x in g]
        moves = [b - a for a, b in zip(vals[:-1], vals[1:], strict=False) if a is not None and b is not None]
        if len(moves) < 5:
            continue
        if METRICS[k].unit in ("sar_mn", "count"):
            moves = [(b - a) / abs(a) * 100 for a, b in zip(vals[:-1], vals[1:], strict=False) if a and b is not None]
        last, hist = moves[-1], moves[-9:-1]
        sd = statistics.pstdev(hist) or 1e-9
        z = (last - statistics.fmean(hist)) / sd
        rows.append({"metric": k, "label": METRICS[k].label, "unit": METRICS[k].unit, "last_move": round(last, 4), "z": round(z, 2),
                     "volatility": round(statistics.pstdev(moves), 4), "value": vals[-1]})
    rows.sort(key=lambda r: -abs(r["z"]))
    return {"period": p, "grid": g, "metrics": rows, "top_movers": rows[:6],
            "evidence": [{"tool": "lens.movement", "ref": f"lens engine series over {g[0]}..{g[-1]}"}]}
