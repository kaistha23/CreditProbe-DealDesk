"""Scheduled monitoring (PLAN_R11_AGENTS K3): compute the set, detect material moves, investigate each one, explain it in
two lines with evidence, notify; then review the set and propose retiring or re-thresholding metrics that never fire
or fire constantly.

Investigation reads only engines: the change is decomposed by sector, rating and borrower on the lens engine
(exactly additive for shares, ratios and sums), split into numerator and denominator (the driver), the Early Warning
read (bands and reasons of the names behind the move, from the EWS release the lens engine carries) and the What-If
read (the Delta-method ECL uplift at PD +20% of the segment behind the move).
"""
from __future__ import annotations

import os
import time
from typing import Any

from backend.agents_v5.lenses import metrics as M
from backend.agents_v5.lenses import thresholds as TH
from backend.lenses_v5 import fmt
from backend.lenses_v5.engine import ENGINE, TABLE, _q

SEG_DIM = {"corporate": "sector", "retail": "product"}


def period_label(p: str) -> str:
    """'2026Q2' stays; a retail month '2026-08' reads 'Aug 2026' (a date, not a figure)."""
    import re
    m = re.fullmatch(r"(\d{4})-(\d{2})", p or "")
    if not m:
        return p or ""
    months = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
    return f"{months[int(m.group(2)) - 1]} {m.group(1)}"
RATING_DIM = {"corporate": "rating_current", "retail": "score_band"}


# ------------------------------------------------------------------ compute and detect
def compute(metrics: list[dict[str, Any]], period: str = "") -> list[dict[str, Any]]:
    out = []
    for m in metrics:
        d = M.from_dict(m["def"])
        p = period or ENGINE.as_of(d.book)
        g = M.grid(d.book, p, n=17)
        s, sql = M.series(d, g)
        ev = TH.evaluate([s.get(x) for x in g], m["threshold"], d.unit)
        out.append({"key": m["key"], "label": m["label"], "unit": d.unit, "period": g[-1], "prev_period": g[-2] if len(g) > 1 else None,
                    "value": s.get(g[-1]), "prev": s.get(g[-2]) if len(g) > 1 else None, "display": fmt.fmt_value(s.get(g[-1]), d.unit),
                    "evaluation": ev, "threshold": m["threshold"], "threshold_text": m.get("threshold_text") or TH.describe(m["threshold"], d.unit),
                    "sql": sql, "def": m["def"]})
    return out


def severity(c: dict[str, Any]) -> str:
    ev = c["evaluation"]
    if not ev.get("fired"):
        return ""
    if ev.get("severity") in ("red", "high"):
        return "high"
    return "alert"


def detect(computed: list[dict[str, Any]], history: dict[str, list[dict[str, Any]]] | None = None) -> list[dict[str, Any]]:
    """Material moves: every metric whose threshold fires. A metric that fired last run at the same severity and has not
    worsened is marked `continuing` (shown, not re-notified)."""
    alerts = []
    for c in computed:
        sev = severity(c)
        if not sev:
            continue
        prev = (history or {}).get(c["key"]) or []
        last = prev[-1] if prev else None
        status = "new"
        if last and last["period"] != c["period"] and last["severity"] == sev and last["value"] is not None and c["value"] is not None:
            worse = (c["value"] > last["value"]) if c["threshold"].get("direction", "up") != "down" else (c["value"] < last["value"])
            status = "worsened" if worse else "continuing"
        elif last and last["period"] == c["period"]:
            status = "repeat"
        alerts.append({**c, "severity": sev, "status": status})
    alerts.sort(key=lambda a: (0 if a["severity"] == "high" else 1, a["label"]))
    return alerts


# ------------------------------------------------------------------ investigate
def decompose(alert: dict[str, Any], by: str) -> dict[str, Any]:
    d = M.from_dict(alert["def"])
    if by == "segment":
        by = SEG_DIM[d.book]
    elif by == "rating":
        by = RATING_DIM[d.book]
    if not alert.get("prev_period"):
        return {"by": by, "rows": [], "note": "no previous period"}
    return M.decompose(d, alert["prev_period"], alert["period"], by)


def driver(alert: dict[str, Any]) -> dict[str, Any]:
    d = M.from_dict(alert["def"])
    if not alert.get("prev_period"):
        return {"available": False}
    return M.driver(d, alert["prev_period"], alert["period"])


def ews_read(alert: dict[str, Any], borrowers: list[str]) -> dict[str, Any]:
    """The Early Warning band and reasons of the names behind the move (the EWS release in the lens engine)."""
    d = M.from_dict(alert["def"])
    ids = [b for b in borrowers if b][:8]
    if not ids:
        return {"names": [], "warned": 0}
    T = TABLE[d.book]
    sql = (f"SELECT owner_id, ANY_VALUE(owner_name) AS name, MAX(ews_score) AS score, "
           f"ARG_MAX(ews_band, ews_score) AS band, ARG_MAX(ews_reasons, ews_score) AS reasons FROM {T} "
           f"WHERE period = {_q(alert['period'])} AND owner_id IN ({', '.join(_q(i) for i in ids)}) GROUP BY 1")
    rows = ENGINE.q(sql)
    names = [{"owner_id": r["owner_id"], "name": r["name"], "band": r["band"], "score": r["score"],
              "reasons": [x.strip() for x in str(r["reasons"] or "").split(";") if x.strip()][:3]} for r in rows]
    warned = [n for n in names if n["band"] in ("moderate", "high", "critical")]
    reasons: dict[str, int] = {}
    for n in warned:
        for x in n["reasons"]:
            reasons[x] = reasons.get(x, 0) + 1
    return {"names": names, "warned": len(warned), "of": len(names), "top_reasons": sorted(reasons.items(), key=lambda kv: -kv[1])[:3], "sql": sql}


def whatif_read(alert: dict[str, Any], segment: str) -> dict[str, Any]:
    """What-If (Delta method, the catalogue's ecl_pd20_uplift): the ECL uplift at PD +20% of the segment behind the move."""
    d = M.from_dict(alert["def"])
    if not segment:
        return {"available": False}
    dim = SEG_DIM[d.book]
    filters = [*d.filters, {"dim": dim, "values": [segment]}] if not any(f["dim"] == dim for f in d.filters) else d.filters
    try:
        rows, sql = ENGINE.series(d.book, filters, [alert["period"]], ["ecl", "ecl_pd20_uplift"])
    except Exception as e:  # noqa: BLE001
        return {"available": False, "error": str(e)}
    r = rows[0] if rows else {}
    return {"available": True, "segment": segment, "ecl": r.get("ecl"), "uplift": r.get("ecl_pd20_uplift"), "sql": sql,
            "method": "What-If Delta method: ECL scales with PD (catalogue metric ecl_pd20_uplift)"}


# ------------------------------------------------------------------ explain
def _c(v: float | None, unit: str) -> str:
    if v is None:
        return "–"
    if unit == "pct":
        return f"{v:+.2f}pp"
    if unit == "bps":
        return f"{v:+.0f} bps"
    if unit == "sar_mn":
        return ("+" if v >= 0 else "−") + fmt.amount(abs(v))
    if unit == "count":
        return f"{v:+,.0f}"
    return f"{v:+.2f}"


def explain(alert: dict[str, Any], seg: dict[str, Any], rat: dict[str, Any], bor: dict[str, Any], drv: dict[str, Any],
            ews: dict[str, Any], wi: dict[str, Any], steps: dict[str, str]) -> dict[str, Any]:
    """Two lines. Line 1: what moved and which threshold it crossed. Line 2: where it came from and why.
    Each figure carries the step that produced it ([s..] in `cites`)."""
    u = alert["unit"]
    ev = alert["evaluation"]
    mv = None if alert["value"] is None or alert["prev"] is None else alert["value"] - alert["prev"]
    if u in ("sar_mn", "count") and alert["prev"]:
        mvs = f"{(alert['value'] - alert['prev']) / abs(alert['prev']) * 100:+.1f}%"
    else:
        mvs = _c(mv, u)
    tl = alert["threshold"]["logic"]
    if tl == "appetite":
        crossed = f"past the risk-appetite {'limit' if ev.get('severity') == 'red' else 'trigger'} ({fmt.fmt_value(alert['threshold']['limit' if ev.get('severity') == 'red' else 'trigger'], u)})"
    elif tl == "absolute":
        crossed = f"above the {fmt.fmt_value(alert['threshold']['level'], u)} level"
    elif tl == "zscore":
        crossed = f"a {ev.get('measure', 0):+.1f} standard-deviation move against its last 8 quarters"
    else:
        crossed = f"beyond the {alert['threshold']['k']:g}{'pp' if u == 'pct' else ' bps' if u == 'bps' else '%'} change threshold"
    line1 = (f"{alert['label']} is {alert['display']} in {period_label(alert['period'])} ({mvs} on {period_label(alert['prev_period'])}), "
             f"{crossed} [{steps['compute']}].")
    bits = []
    unit_c = seg.get("unit_of_contribution", u)
    srows = [r for r in seg.get("rows", []) if r.get("contribution")]
    if srows:
        top = srows[:2]
        bits.append("mostly " + " and ".join(f"{r['name']} ({_c(r['contribution'], unit_c)})" for r in top) + f" [{steps['segment']}]")
    rrows = [r for r in rat.get("rows", []) if r.get("contribution")]
    if rrows:
        bits.append(f"by rating {rrows[0]['name']} ({_c(rrows[0]['contribution'], rat.get('unit_of_contribution', u))}) [{steps['rating']}]")
    brows = [r for r in bor.get("rows", []) if r.get("contribution")]
    if brows:
        bits.append("largest names " + ", ".join(f"{r['name']} ({_c(r['contribution'], bor.get('unit_of_contribution', u))})" for r in brows[:2])
                    + f" [{steps['borrower']}]")
    if drv.get("available"):
        bits.append(("driven by more exposure in the measure" if drv["main"] == "numerator" and (drv["numerator_part"] or 0) > 0 else
                     "driven by less exposure in the measure" if drv["main"] == "numerator" else
                     "driven by the book around it shrinking" if (drv["denominator_part"] or 0) > 0 else "driven by the book around it growing")
                    + f" ({_c(drv['numerator_part'], u)} from the numerator, {_c(drv['denominator_part'], u)} from the denominator) [{steps['driver']}]")
    line2 = (bits[0][:1].upper() + "; ".join(bits)[1:] + ".") if bits else "No single segment, rating or name explains it; the move is broad-based."
    if ews.get("names"):
        rs = ", ".join(r for r, _ in ews.get("top_reasons", [])[:2])
        line2 += f" Early Warning: {ews['warned']} of the {ews['of']} largest names are warned" + (f" ({rs})" if rs else "") + f" [{steps['ews']}]."
    if wi.get("available") and wi.get("uplift") is not None:
        line2 += f" What-If: PD +20% on {wi['segment']} adds {fmt.amount(wi['uplift'])} of ECL [{steps['whatif']}]."
    evidence = [{"step": steps[k], "kind": k} for k in ("compute", "segment", "rating", "borrower", "driver", "ews", "whatif") if k in steps]
    return {"headline": f"{alert['label']}: {alert['display']} ({mvs})", "lines": [line1, line2], "evidence": evidence,
            "severity": alert["severity"], "status": alert["status"]}


# ------------------------------------------------------------------ notify
def notify(recipients: list[str], title: str, href: str, actor: str = "agent:lenses-monitor") -> dict[str, Any]:
    """Into the notifications bell: the Mail notifications table (the path backend/admin/notify.py uses). Best effort;
    a test never writes into the machine's real store unless it points IDENTITY_STORE at a temporary one."""
    if os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get("AGENTS_LENSES_NOTIFY"):
        return {"delivered": 0, "recipients": recipients, "skipped": "test run"}
    sent = 0
    try:
        from backend.identity_v5 import store as ids
        with ids.db() as con:
            for u in sorted(set(r for r in recipients if r)):
                con.execute("INSERT INTO mail_notifications(username, kind, title, href, from_user, thread_id, created_at) VALUES(?,?,?,?,?,?,?)",
                            (u, "agent", title[:240], href, actor.split(":")[-1][:60], None, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))
                sent += 1
    except Exception as e:  # noqa: BLE001 - the alerts stay on the Monitoring agent panel
        return {"delivered": sent, "recipients": recipients, "error": str(e)[:200]}
    return {"delivered": sent, "recipients": recipients}


# ------------------------------------------------------------------ the set learns
def review(metrics: list[dict[str, Any]], history: dict[str, list[dict[str, Any]]], period: str = "") -> list[dict[str, Any]]:
    """Retire or re-threshold: metrics that never fire, or fire (almost) every quarter, over the back-test window plus the
    live runs since approval. Each proposal carries the evidence (alert counts, the new back-test)."""
    out = []
    for m in metrics:
        if m.get("status") == "rejected":
            continue
        d = M.from_dict(m["def"])
        p = period or ENGINE.as_of(d.book)
        g = M.grid(d.book, p, n=17)
        s, _ = M.series(d, g)
        bt = TH.backtest(g, s, m["threshold"], d.unit)
        live = [h for h in history.get(m["key"], []) if h["status"] != "repeat"]
        nz = TH.noise(bt)
        logic = m["threshold"]["logic"]
        ev = {"backtest": bt, "live_alerts": len(live), "noise": nz}
        if nz == "never":
            if logic in ("change", "zscore"):
                cal = TH.calibrate(g, s, d.unit, m["threshold"].get("direction", "up"))
                ch = cal["chosen"]
                if ch and TH.noise(ch["backtest"]) == "useful" and ch["threshold"] != m["threshold"]:
                    out.append({"action": "rethreshold", "key": m["key"], "label": m["label"], "from": m["threshold"], "to": ch["threshold"],
                                "to_text": TH.describe(ch["threshold"], d.unit), "evidence": {**ev, "new_backtest": ch["backtest"]},
                                "why": f"Never fired in {bt['label']}; {TH.describe(ch['threshold'], d.unit).lower()} would have fired in {ch['backtest']['label']}."})
                    continue
            now = s.get(g[-1])
            far = True
            if logic == "appetite" and now is not None:
                far = now < 0.7 * m["threshold"]["limit"]
            if logic == "absolute" and now is not None:
                far = now < 0.5 * m["threshold"]["level"]
            if far:
                out.append({"action": "retire", "key": m["key"], "label": m["label"], "evidence": ev,
                            "why": f"Never fired in {bt['label']} and no live alert since approval"
                                   + (f"; now {fmt.fmt_value(now, d.unit)}, far from its trigger" if logic in ("appetite", "absolute") else "") + "."})
        elif nz == "constant":
            if logic in ("change", "zscore"):
                cal = TH.calibrate(g, s, d.unit, m["threshold"].get("direction", "up"))
                ch = cal["chosen"]
                if ch and TH.noise(ch["backtest"]) == "useful":
                    out.append({"action": "rethreshold", "key": m["key"], "label": m["label"], "from": m["threshold"], "to": ch["threshold"],
                                "to_text": TH.describe(ch["threshold"], d.unit), "evidence": {**ev, "new_backtest": ch["backtest"]},
                                "why": f"Fired in {bt['label']}: noise. {TH.describe(ch['threshold'], d.unit)} would have fired in {ch['backtest']['label']}."})
                else:
                    out.append({"action": "retire", "key": m["key"], "label": m["label"], "evidence": ev,
                                "why": f"Fires in {bt['label']} and no threshold on the grid makes it selective."})
            # a limit breached every quarter is a standing breach: it stays (and is escalated), it is not noise
    return out
