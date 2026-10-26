"""Planning what is worth monitoring (PLAN_R11_AGENTS K2): candidates from five sources, back-tested, ranked by value,
de-duplicated with reasons, each with its definition, scope, frequency, threshold and one line on why it matters.

Value (0-1) = 0.25 materiality + 0.20 risk-appetite proximity + 0.20 regulation + 0.15 recent movement + 0.10 signal
quality + 0.10 breach (a risk-appetite limit or regulatory level breached now). Each part is computed and shown on the metric, so the ranking can be read and argued with:
  materiality   the larger of the EAD and ECL share the metric speaks for, saturating at 30%
  appetite      1 past the trigger; rising from 0 at 60% of the limit to 1 at the trigger
  regulation    1 for a CBUAE CRM breach check or a Board trigger, 0.6 for a CRM library metric
  movement      the last quarter's move as a z-score against the previous 8 moves, saturating at 3
  signal        how useful the back-tested alert rate is (1-3 alerts in 8 quarters is best; never or always is poor)
"""
from __future__ import annotations

import hashlib
import json
import statistics
from typing import Any

from backend.agents_v5.lenses import metrics as M
from backend.agents_v5.lenses import sources as S
from backend.agents_v5.lenses import thresholds as TH
from backend.lenses_v5 import fmt
from backend.lenses_v5.catalogue import DIMS, METRICS
from backend.lenses_v5.engine import ENGINE

MAX_SET = 12
WEIGHTS = {"materiality": 0.25, "appetite": 0.20, "regulation": 0.20, "movement": 0.15, "signal": 0.10, "breach": 0.10}
SIGNAL = {"useful": 1.0, "noisy": 0.4, "never": 0.2, "constant": 0.1, "untested": 0.3}
CORR_DROP = 0.95


def frequency(book: str) -> str:
    return "Quarterly (each corporate quarter-end release)" if book == "corporate" else "Monthly (each retail month-end; moves measured over 3 months)"


# ------------------------------------------------------------------ candidates
def _cand(d: M.MDef, sources: list[str], why: str, threshold: dict[str, Any] | None = None, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"def": d.public(), "sources": sources, "why_seed": why, "fixed_threshold": threshold, **(extra or {})}


def candidates(book: str, filters: list[dict[str, Any]], comp: dict[str, Any], app: dict[str, Any], reg: dict[str, Any],
               mov: dict[str, Any], lens_kpis: list[str] | None = None) -> list[dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}

    def add(c: dict[str, Any]) -> None:
        k = c["def"]["key"]
        if k in out:
            out[k]["sources"] = sorted(set(out[k]["sources"]) | set(c["sources"]))
            if c.get("fixed_threshold") and not out[k].get("fixed_threshold"):
                out[k]["fixed_threshold"] = c["fixed_threshold"]
            for x in ("appetite", "regulation"):
                if c.get(x) and not out[k].get(x):
                    out[k][x] = c[x]
            return
        out[k] = c
    p = comp["period"]
    # regulation: the CRM library metrics and the breach checks
    for r in reg["metrics"]:
        m = METRICS[r["metric"]]
        d = M.mdef(label=m.label, unit=m.unit, book=book, kind="catalogue", metric=r["metric"], filters=filters, better=m.better,
                   article=r["article"], source="CBUAE CRM")
        add(_cand(d, ["regulation"], r["article"] + (f" ({r['name']})" if r["name"] != m.label else ""), r["threshold"],
                  {"regulation": {"library_id": r["library_id"], "article": r["article"], "weight": 1.0 if r["threshold"] else 0.6}}))
    for c in reg["checks"]:
        d = M.mdef(label=f"{c['title']} (count)", unit="count", book=book, kind="crm_check", metric=c["check_id"], filters=filters,
                   article=c["article"], source="CBUAE CRM checks")
        add(_cand(d, ["regulation"], f"CBUAE CRM breach check {c['check_id']}", {"logic": "change", "k": 25.0, "direction": "up"},
                  {"regulation": {"check_id": c["check_id"], "article": c["article"], "weight": 1.0, "breaches_now": c["breaches"]}}))
    # risk appetite
    for a in app["measurable"]:
        mk = a["mkind"]
        if mk == "catalogue":
            m = METRICS[a["metric"]]
            d = M.mdef(label=m.label, unit=m.unit, book=book, kind="catalogue", metric=a["metric"], filters=[], better=m.better, source="Risk appetite")
        else:
            d = M.mdef(label=a["label"], unit=a["unit"], book=book, kind=mk, metric="ead", filters=[], segment=a["segment"], source="Risk appetite")
        add(_cand(d, ["appetite"], f"Risk appetite, {a['kind']} limit ({a['basis']})",
                  {"logic": "appetite", "trigger": round(a["trigger"], 4), "limit": round(a["limit"], 4), "direction": "up"},
                  {"appetite": {"row": a["row"], "basis": a["basis"], "limit": a["limit"], "trigger": a["trigger"], "appetite": a.get("appetite"),
                                "trigger_source": a["trigger_source"]}}))
    # composition: top segments, growth segments, concentration
    seg_dim = comp["segment_dim"]
    for s in comp["top_segments"]:
        d = M.mdef(label=f"{s['segment']} share of {_scope_word(book, filters)}", unit="pct", book=book, kind="share", metric="ead", filters=filters,
                   segment={"dim": seg_dim, "values": [s["segment"]]}, source="Composition")
        add(_cand(d, ["composition"], f"{s['segment']} is {fmt.pct(s['share'])} of {_scope_word(book, filters)}",
                  extra={"seed_figures": {"share": s["share"]}}))
    for s in comp["growth_segments"]:
        f2 = [*filters, {"dim": seg_dim, "values": [s["segment"]]}]
        for key in ("stage2_share", "warned_share"):
            m = METRICS[key]
            d = M.mdef(label=f"{m.label}: {s['segment']}", unit=m.unit, book=book, kind="catalogue", metric=key, filters=f2, better=m.better,
                       source="Composition (growth)")
            add(_cand(d, ["composition"], f"{s['segment']} grew {fmt.pct(s['growth_4q'])} in 4 quarters against {fmt.pct(comp['book_growth_4q'])} "
                                         f"for the scope; new lending is where quality slips first",
                      extra={"seed_figures": {"growth": s["growth_4q"], "book_growth": comp["book_growth_4q"]}}))
    d = M.mdef(label="Top 20 obligors' share of EAD", unit="pct", book=book, kind="top20", metric="ead", filters=filters, article="CBUAE CRM Art. 11.4",
               source="Composition")
    add(_cand(d, ["composition", "regulation"], "Single-name concentration (CBUAE CRM Art. 11.4, CRM-M29)",
              extra={"regulation": {"library_id": "CRM-M29", "article": "CBUAE CRM Art. 11.4", "weight": 0.6}}))
    d = M.mdef(label=f"{DIMS[seg_dim].label} concentration (HHI)", unit="count", book=book, kind="hhi", metric="ead", filters=filters,
               segment={"dim": seg_dim, "values": []}, article="CBUAE CRM Art. 11.4", source="Composition")
    add(_cand(d, ["composition", "regulation"], "Sector concentration (CBUAE CRM Art. 11.4, CRM-M30)",
              extra={"regulation": {"library_id": "CRM-M30", "article": "CBUAE CRM Art. 11.4", "weight": 0.6}}))
    # recent movement: the largest unusual moves among the catalogue metrics
    for r in mov["top_movers"]:
        if abs(r["z"]) < 1.5:
            continue
        m = METRICS[r["metric"]]
        d = M.mdef(label=m.label, unit=m.unit, book=book, kind="catalogue", metric=r["metric"], filters=filters, better=m.better, source="Movement")
        add(_cand(d, ["movement"], f"Moved {r['z']:+.1f} standard deviations last quarter", extra={"seed_figures": {"z": r["z"]}}))
    # the lens's own KPIs (when the goal names a lens)
    for k in lens_kpis or []:
        if k in METRICS and book in METRICS[k].books and METRICS[k].kind in S.MOVABLE:
            m = METRICS[k]
            d = M.mdef(label=m.label, unit=m.unit, book=book, kind="catalogue", metric=k, filters=filters, better=m.better, source="Lens")
            add(_cand(d, ["lens"], "On this lens's KPI row"))
    del p
    return list(out.values())


def _scope_word(book: str, filters: list[dict[str, Any]]) -> str:
    return " · ".join(", ".join(f["values"]) for f in filters) or f"the {book} book"


# ------------------------------------------------------------------ back-test, score, rank, de-duplicate
def assess(c: dict[str, Any], period: str, mov_by_metric: dict[str, dict[str, Any]]) -> dict[str, Any]:
    d = M.from_dict(c["def"])
    g = M.grid(d.book, period, n=17)
    series, sql = M.series(d, g)
    direction = TH.adverse(d.better)
    if c.get("fixed_threshold"):
        th = {**c["fixed_threshold"]}
        th.setdefault("direction", direction)
        bt = TH.backtest(g, series, th, d.unit)
        searched: list[dict[str, Any]] = []
        how = "fixed by the source"
        if th["logic"] == "change" and TH.noise(bt) in ("noisy", "constant", "never"):
            cal = TH.calibrate(g, series, d.unit, direction)
            if cal["chosen"] and TH.noise(cal["chosen"]["backtest"]) == "useful":
                th, bt, searched, how = cal["chosen"]["threshold"], cal["chosen"]["backtest"], cal["searched"], "calibrated on 8 quarters"
    else:
        cal = TH.calibrate(g, series, d.unit, direction)
        if cal["chosen"] is None:
            th = {"logic": "change", "k": 1.0, "direction": direction}
            bt = TH.backtest(g, series, th, d.unit)
        else:
            th, bt = cal["chosen"]["threshold"], cal["chosen"]["backtest"]
        searched, how = cal["searched"], "calibrated on 8 quarters"
    stake = M.at_stake(d, period)
    now = series.get(period)
    prev = series.get(g[-2]) if len(g) > 1 else None
    # value parts
    mat = min(1.0, max(stake["ead"], stake["ecl"]) / 0.30)
    if d.kind == "hhi":
        mat = 0.5
    appv = 0.0
    if th["logic"] == "appetite" and now is not None:
        trig, lim = th["trigger"], th["limit"]
        appv = 1.0 if now >= trig else max(0.0, (now / lim - 0.6) / ((trig / lim) - 0.6)) if lim else 0.0
    regv = float((c.get("regulation") or {}).get("weight", 0.0))
    del mov_by_metric
    z = _z_last(g, series, d.unit)
    movv = min(1.0, abs(z) / 3.0) if z is not None else 0.0
    nz = TH.noise(bt)
    sig = SIGNAL.get(nz, 0.3)
    if th["logic"] in ("absolute", "appetite"):
        firing = bool(bt["fired_periods"]) and bt["fired_periods"][-1] == g[-1]
        if firing:
            sig = 1.0      # a limit or trigger breached now is the first thing to watch, however long it has been breached
        elif nz == "never" and regv + appv > 0:
            sig = 0.5      # a control that has not been breached is still worth keeping
    breach = 0.0
    if th["logic"] in ("absolute", "appetite") and now is not None:
        lvl = th.get("limit", th.get("level"))
        breach = 1.0 if (now >= lvl if th.get("direction", "up") != "down" else now <= lvl) else 0.0
    parts = {"materiality": round(mat, 3), "appetite": round(appv, 3), "regulation": round(regv, 3), "movement": round(movv, 3), "signal": round(sig, 3),
             "breach": breach}
    value = round(sum(WEIGHTS[k] * v for k, v in parts.items()), 4)
    return {**c, "threshold": th, "threshold_text": TH.describe(th, d.unit), "threshold_how": how, "threshold_searched": searched,
            "backtest": bt, "noise": nz, "series": {p: series.get(p) for p in g}, "grid": g, "sql": sql,
            "now": now, "prev": prev, "now_display": fmt.fmt_value(now, d.unit), "z_last": z,
            "at_stake": {k: round(v, 4) for k, v in stake.items()}, "value_parts": parts, "value": value}


def _z_last(g: list[str], series: dict[str, float | None], unit: str) -> float | None:
    vals = [series.get(p) for p in g]
    moves = [TH._delta(b, a, unit) for a, b in zip(vals[:-1], vals[1:], strict=False) if a is not None and b is not None]  # noqa: SLF001
    moves = [x for x in moves if x is not None]
    if len(moves) < 5:
        return None
    hist = moves[-9:-1]
    sd = statistics.pstdev(hist)
    if sd <= 1e-9:
        return 0.0 if abs(moves[-1] - statistics.fmean(hist)) < 1e-9 else 3.0
    return round((moves[-1] - statistics.fmean(hist)) / sd, 2)


def signal_family(c: dict[str, Any]) -> str:
    """Two metrics with the same numerator condition over the same scope carry the same signal
    (Stage 2 EAD and Stage 2 share; NPL ratio and Stage 3 share; warned obligors and warned EAD)."""
    d = c["def"]
    if d["kind"] != "catalogue":
        return json.dumps([d["kind"], d["metric"], d["filters"], d["segment"]], sort_keys=True)
    m = METRICS[d["metric"]]
    base = METRICS[m.num] if m.kind == "ratio" else m
    cond = base.cond if base.kind in ("sum", "distinct") and base.cond else f"{m.kind}:{m.expr or d['metric']}"
    return json.dumps(["cond", cond, d["filters"]], sort_keys=True)


def _moves(c: dict[str, Any]) -> list[float]:
    vals = [c["series"].get(p) for p in c["grid"]]
    return [b - a for a, b in zip(vals[:-1], vals[1:], strict=False) if a is not None and b is not None]


def _corr(a: list[float], b: list[float]) -> float | None:
    n = min(len(a), len(b))
    if n < 6:
        return None
    a, b = a[-n:], b[-n:]
    try:
        return statistics.correlation(a, b)
    except statistics.StatisticsError:
        return None


def rank(assessed: list[dict[str, Any]], max_set: int = MAX_SET) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Ranked, de-duplicated set and the dropped metrics with their reason."""
    order = sorted(assessed, key=lambda c: (-c["value"], c["def"]["label"]))
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    fam: dict[str, dict[str, Any]] = {}
    for c in order:
        f = signal_family(c)
        if f in fam:
            k = fam[f]
            dropped.append({**_slim(c), "reason": "same_signal", "kept": k["def"]["key"],
                            "why": f"Same signal as {k['def']['label']} (both count the same exposures in the same scope); kept the higher-value one."})
            continue
        twin = None
        for k in kept:
            r = _corr(_moves(c), _moves(k))
            if r is not None and r >= CORR_DROP:
                twin = (k, r)
                break
        if twin:
            k, r = twin
            dropped.append({**_slim(c), "reason": "correlated", "kept": k["def"]["key"], "correlation": round(r, 3),
                            "why": f"Its quarterly moves track {k['def']['label']} (correlation {r:.2f} over {min(len(_moves(c)), len(_moves(k)))} quarters); "
                                   f"kept the higher-value one."})
            continue
        if len(kept) >= max_set:
            dropped.append({**_slim(c), "reason": "below_cut", "why": f"Value {c['value']:.2f} is below the {max_set} kept (the last kept scores "
                                                                      f"{kept[-1]['value']:.2f})."})
            continue
        fam[f] = c
        kept.append(c)
    for i, c in enumerate(kept, 1):
        c["rank"] = i
    return kept, dropped


def _slim(c: dict[str, Any]) -> dict[str, Any]:
    return {"key": c["def"]["key"], "label": c["def"]["label"], "value": c["value"], "sources": c["sources"], "backtest": c["backtest"],
            "threshold_text": c["threshold_text"]}


# ------------------------------------------------------------------ definitions and rationale
def definition(c: dict[str, Any]) -> dict[str, Any]:
    """The lens tile (and KPI) that shows the metric: an existing tile type or catalogue metric."""
    d = c["def"]
    if d["kind"] == "catalogue":
        return {"catalogue_metric": d["metric"], "kpi": d["metric"],
                "tile": {"type": "trend", "metrics": [d["metric"]], "chart": "line", "title": f"{d['label']} · monitored"}}
    if d["kind"] == "share":
        seg = d["segment"]
        ck = "custom-" + hashlib.sha1(json.dumps(seg, sort_keys=True).encode()).hexdigest()[:5]
        return {"custom_metric": {"key": ck, "label": d["label"][:80], "num": "ead", "den": "ead", "filters": [seg], "scale": 100.0, "unit": "pct",
                                  "source": "Monitoring agent", "better": "lower"},
                "kpi": ck, "tile": {"type": "trend", "metrics": [ck], "chart": "line", "title": f"{d['label']} · monitored"},
                "context_tile": {"type": "breakdown", "metric": "ead", "dim": seg["dim"], "chart": "hbar"}}
    if d["kind"] in ("top20", "hhi", "max_share", "single_name"):
        if d["kind"] == "max_share":
            return {"tile": {"type": "breakdown", "metric": "ead", "dim": "sector", "chart": "hbar", "title": "Sector shares against the 18% policy limit"}}
        if d["kind"] == "single_name":
            return {"tile": {"type": "top_names", "metric": "ead", "top": 20, "title": "Largest obligors against the single-name limit"}}
        return {"tile": {"type": "concentration", "title": "Concentration: top names and HHI · monitored"}}
    if d["kind"] == "crm_check":
        return {"tile": {"type": "regulatory", "chart": "hbar", "title": "CBUAE CRM breaches by article · monitored"}, "check": d["metric"]}
    return {}


def rationale(c: dict[str, Any]) -> str:
    """One line: why it matters, with the figures that make the case (each from this plan's tool outputs)."""
    d = c["def"]
    u = d["unit"]
    now = fmt.fmt_value(c["now"], u)
    bits = []
    if c.get("appetite"):
        a = c["appetite"]
        bits.append(f"{now} against a limit of {fmt.fmt_value(a['limit'], u)} (trigger {fmt.fmt_value(a['trigger'], u)})")
    elif c.get("regulation", {}).get("check_id"):
        bits.append(f"{fmt.count(c['now'])} breaches now under {c['regulation']['article']}")
    else:
        bits.append(f"{now} now")
    if c.get("prev") is not None and c.get("now") is not None:
        mv = c["now"] - c["prev"]
        if u in ("pct",):
            bits.append(f"{mv:+.2f}pp on the quarter")
        elif u == "bps":
            bits.append(f"{mv:+.0f} bps on the quarter")
        elif c["prev"]:
            bits.append(f"{mv / abs(c['prev']) * 100:+.1f}% on the quarter")
    stake = max(c["at_stake"]["ead"], c["at_stake"]["ecl"])
    if stake >= 0.02 and d["kind"] not in ("hhi",):
        bits.append(f"covers {fmt.pct(c['at_stake']['ead'] * 100)} of EAD and {fmt.pct(c['at_stake']['ecl'] * 100)} of ECL")
    reg = c.get("regulation") or {}
    head = c["why_seed"]
    if reg.get("article") and reg["article"] not in head:
        head += f" · {reg['article']}"
    return f"{head}: " + "; ".join(bits) + "."


def finalise(kept: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for c in kept:
        d = c["def"]
        out.append({"key": d["key"], "rank": c["rank"], "label": d["label"], "unit": d["unit"], "book": d["book"], "def": d,
                    "definition": definition(c), "scope": _scope_word(d["book"], d["filters"]) + (f" · {', '.join(d['segment']['values'])}" if d.get("segment") and d["segment"].get("values") and d["kind"] == "share" and d["filters"] else ""),
                    "frequency": frequency(d["book"]), "threshold": c["threshold"], "threshold_text": c["threshold_text"],
                    "threshold_how": c["threshold_how"], "threshold_searched": c["threshold_searched"],
                    "why": rationale(c), "sources": c["sources"], "backtest": c["backtest"], "noise": c["noise"],
                    "expected_alert_rate": c["backtest"]["rate"], "value": c["value"], "value_parts": c["value_parts"],
                    "now": c["now"], "now_display": c["now_display"], "series": c["series"], "at_stake": c["at_stake"],
                    "appetite": c.get("appetite"), "regulation": c.get("regulation"), "status": "proposed", "evidence_sql": c["sql"],
                    "prev": c["prev"], "z_last": c["z_last"], "seed_figures": c.get("seed_figures") or {}})
    return out


def as_of(book: str) -> str:
    return ENGINE.as_of(book)
