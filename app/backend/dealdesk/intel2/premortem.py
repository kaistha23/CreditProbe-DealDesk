"""D7 Default pre-mortem: the three most likely ways this deal goes bad, how likely and how fast, and the covenant or
Early Warning trigger that would warn first on each.

Method (deterministic)
  * Paths: the deal's own Stress Lab ladder (latest dd_stress_result run), one path per driver family: revenue
    (borrower revenue), sector downturn, oil-led demand, loss of key customers, margin squeeze, payment delays,
    project delays (contractors) and collateral value; plus group contagion when a connected party is already
    classified, in litigation or in arrears (D12).
  * "Goes bad" = DSCR below 1.0x, Stage 2 or a rating downgrade in the scenario (the default-relevant breaks). The
    path's breaking severity is the mildest severity at which that happens.
  * Probability (a year): the calibrated frequency of the driver moving at least that much in one year
    (dd_scenario_calibration.freq_share at that severity, R13 §S, data window stated); for drivers with no history
    (customer loss, payment and project delays) the severity percentile convention (mild 25%, moderate 8%, severe 4%)
    and the label say so. A path that does not go bad even at severe gets a quarter of the severe frequency and is
    labelled "beyond severe". Contagion: the party has already failed, so the probability is the chance it pulls the
    obligor down within a year, an expert transmission by status (classified 25%, litigation 15%, arrears 10%),
    doubled for a group (cross-default) link.
  * Speed (labelled expert view by channel): payment delays, key customer loss and contagion are fast (within
    2 quarters); revenue, sector, oil and margin are medium (2-4 quarters); collateral is slow (over 4 quarters).
  * First warning: the trigger on the path's metric that fires at a milder severity than the default (the 'covenant'
    or 'leverage' break comes before the DSCR break): the deal's covenant on that metric (proposal covenants) or the
    monitoring plan's named trigger, else the Early Warning rule for the channel; lead = severity steps between them.
"""
from __future__ import annotations

import functools
import json
from typing import Any

from backend.dealdesk.intel2 import common as C

SEVS = ("mild", "moderate", "severe")
PATHS = {
    "rev": ("revenue", "Revenue falls", "revenue", "medium"),
    "sector": ("sector", "Sector downturn", "sector_cycle", "medium"),
    "oil": ("oil", "Oil-led demand fall", "brent", "medium"),
    "cust": ("customer", "Loss of key customers", "customer", "fast"),
    "margin": ("margin", "Margin squeeze (input costs)", "margin", "medium"),
    "paydelay": ("payment_delay", "Customers pay late (working capital)", "payment_delay", "fast"),
    "delay": ("project_delay", "Project delays (contractor)", "project_delay", "fast"),
    "coll": ("collateral", "Collateral value falls", "collateral", "slow"),
    "re": ("collateral", "Real-estate values fall", "re_price", "slow"),
}
CONVENTION = {"mild": 0.25, "moderate": 0.08, "severe": 0.04}  # P75 / P92 / P96: the §S severity definition
TRANSMISSION = {"classified": 0.25, "in litigation": 0.15, "in arrears": 0.10}  # expert: chance a year the obligor is pulled down
GROUP_LINK = 2.0  # a group (cross-default) link doubles the transmission
SPEED = {"fast": "fast: within 2 quarters", "medium": "medium: 2 to 4 quarters", "slow": "slow: more than 4 quarters"}
BAD = ("stage2", "rating")
EWS = {"revenue": "Early Warning: credit turnover through our account down more than 15% on last year",
       "sector": "Early Warning: sector watch (sector stress index) plus turnover down more than 15%",
       "oil": "Early Warning: Brent below the budget price for two months and turnover down",
       "customer": "Early Warning: top customer's payments into our account stop for 60 days",
       "margin": "Early Warning: gross margin in the interim accounts below last year by 3 points",
       "payment_delay": "Early Warning: limit utilisation above 95% for 3 months and receivable days up 30",
       "project_delay": "Early Warning: work done behind the project plan by more than 15%",
       "collateral": "Early Warning: revaluation overdue or LTV above the covenant",
       "contagion": "Early Warning: connected party DPD above 30 or a new court case"}


def _family(sid: str) -> str | None:
    for k in sorted(PATHS, key=len, reverse=True):
        if sid.startswith(k + "_") or sid == k:
            return k
    if sid.startswith("sector_"):
        return "sector"
    return None


def _bad(r: dict[str, Any]) -> bool:
    br = str(r.get("breaks") or "").split(";")
    d = C.finite(r.get("dscr_x"))
    return any(b in br for b in BAD) or (d is not None and d < 1.0)


def _cal() -> dict[tuple[str, str], dict[str, Any]]:
    out = {}
    for c in C.rows("dd_scenario_calibration"):
        k = (c["driver"], c["severity"])
        if k not in out or int(c["version"]) > int(out[k]["version"]):
            out[k] = c
    return out


def _covenant(p: dict[str, Any], key: str) -> str | None:
    cov = {str(c.get("type", "")).lower(): c.get("threshold") for c in (p.get("security") or {}).get("covenants") or []}
    want = {"revenue": "dscr", "sector": "dscr", "oil": "dscr", "customer": "dscr", "margin": "interest cover",
            "payment_delay": "current ratio", "project_delay": "dscr", "collateral": "ltv"}.get(key)
    for k, v in cov.items():
        if want and want in k:
            return f"{k.upper() if len(k) <= 4 else k.capitalize()} covenant {v}"
    if want == "dscr" and any("ebitda" in k for k in cov):
        k = next(k for k in cov if "ebitda" in k)
        return f"{k.capitalize()} covenant {cov[k]}"
    return None


def _lc(x: dict[str, Any]) -> str:
    return x.get("driver_lc") or (x["driver"][:1].lower() + x["driver"][1:])


@functools.lru_cache(maxsize=64)
def _premortem(pid: str, which: str, tkey: str, pv: str) -> str:
    st = C.structure(pid, which, json.loads(tkey) or None)
    p = C.proposal(pid)
    a = C.analysis(pid, st["terms"])
    tsrc = {"structure": st["kind"]}
    sr = C.C.latest_stress(pid)
    cal = _cal()
    plans = C.rows("dd_monitoring_plan", proposal_id=pid)
    named = [t for pl in plans if pl.get("status") == "active" for t in (pl.get("named_triggers") or []) if isinstance(t, dict)]
    by: dict[str, list[dict[str, Any]]] = {}
    for r in sr["rows"]:
        if not int(r.get("applicable_flag") or 0):
            continue
        f = _family(r["scenario_id"])
        if f:
            by.setdefault(f, []).append(r)
    paths = []
    for f, rs in by.items():
        key, label, driver, speed = PATHS[f]
        rs = sorted(rs, key=lambda r: SEVS.index(r["severity"]) if r["severity"] in SEVS else 9)
        badr = next((r for r in rs if _bad(r)), None)
        warn = next((r for r in rs if r.get("breaks")), None)
        sev = badr["severity"] if badr else None
        c = cal.get((driver, sev or "severe")) or cal.get(("revenue", sev or "severe"))
        if c is None:
            continue
        fs = c.get("freq_share")
        conv = fs is None
        fs = CONVENTION[sev or "severe"] if conv else float(fs)
        prob = fs * (1.0 if badr else 0.25)
        ev = badr or rs[-1]
        lead_steps = (SEVS.index(sev) - SEVS.index(warn["severity"])) if (badr and warn and warn["severity"] in SEVS) else 0
        cov = _covenant(p, key)
        nt = next((t for t in named if key.split("_")[0] in str(t.get("metric", ""))), None)
        trig = (nt.get("label") if nt else None) or cov or EWS[key]
        if cov and warn and "covenant" in str(warn.get("breaks") or ""):
            trig = f"{cov} (breaks at {warn['severity']} stress)"
        paths.append({
            "key": f, "driver": label, "channel": key, "breaking_severity": sev or "beyond severe",
            "probability": C.fig(round(prob, 4), "share a year", C.row_source("dd_scenario_calibration", c, "freq_share" if not conv else "percentile"),
                                 f"Chance a year the driver moves at least {'that much' if badr else 'to severe'}"
                                 + (" (severity percentile convention: no history for this driver)" if conv else "")),
            "speed": SPEED[speed], "speed_class": speed,
            "dscr_at_break": C.rfig("dd_stress_result", ev, "dscr_x", "x", f"DSCR under {ev['scenario_id']}"),
            "revenue_change": C.rfig("dd_stress_result", ev, "revenue_change_pct", "%", "Revenue change in the scenario"),
            "what_breaks": [b for b in str(ev.get("breaks") or "").split(";") if b],
            "first_warning": trig, "ews_rule": EWS[key],
            "lead": (f"warns {lead_steps} severity step{'s' if lead_steps != 1 else ''} before default" if lead_steps > 0 else
                     "warns at the same severity as the default: tighten it" if badr else "no break up to severe"),
            "calibration": {"label": c["label"], "window": c.get("window"), "freq_labels": c.get("freq_labels"), "method": c.get("method"),
                            "move": c.get("value"), "unit": c.get("unit")}})
    # group contagion (D12): the party has already failed, so the path's probability is the PD it adds
    try:
        from backend.dealdesk.intel2 import contagion
        g = contagion.contagion(pid, which, json.loads(tkey) or None)
    except Exception:  # noqa: BLE001 - group facts optional
        g = None
    if g and g.get("adverse_count"):
        n = g["combined"]["notches"]
        adv = [x for x in g["parties"] if x["adverse"]]
        dp = 1.0
        for x in adv:
            tr = TRANSMISSION.get(x["status"], 0.1) * (GROUP_LINK if any(l in ("group", "parent", "subsidiary") for l in x["links"]) else 1.0)
            dp *= 1 - min(0.9, tr)
        dp = 1 - dp
        names = ", ".join(g["combined"]["parties"][:2])
        paths.append({"key": "contagion", "driver": f"Group contagion ({names})", "driver_lc": f"group contagion ({g['combined']['parties'][0]})", "channel": "contagion", "breaking_severity": "already failed",
                      "probability": C.efig(pid, round(dp, 4), "share a year",
                                            "Chance a year the connected party's failure pulls the obligor down (expert transmission by status and link)",
                                            "intel2.premortem", {**tsrc, "notches": n}),
                      "speed": SPEED["fast"], "speed_class": "fast",
                      "first_warning": (g["conditions"][0]["text"].split(";")[0].rstrip(".") if g.get("conditions") else EWS["contagion"]),
                      "ews_rule": EWS["contagion"], "lead": "the party is already in trouble: act now", "what_breaks": ["rating"],
                      "calibration": {"label": "Connected-party failure: rating notches by link (D12)", "move": n, "unit": "notches"}})
    paths.sort(key=lambda x: (-(x["probability"]["value"] or 0), x["key"]))
    top = paths[:3]
    for i, x in enumerate(top, 1):
        x["rank"] = i
    pd12 = a["metrics"]["pd_12m"]
    if top:
        head = (f"Most likely way {p['obligor']['name']} goes bad: {_lc(top[0])} "
                f"({C.pct(top[0]['probability']['value'])} a year, {top[0]['speed'].split(':')[0]}); first warning: {top[0]['first_warning']}. "
                f"Then: " + "; ".join(f"{_lc(x)} ({C.pct(x['probability']['value'])})" for x in top[1:]) + ".")
        plain = C.plain("This imagines the deal has failed and finds the three likeliest reasons, so we can watch for them.",
                        f"Top risk: {_lc(top[0])}, about {C.pct(top[0]['probability']['value'], 0)} a year; "
                        f"watch first: {top[0]['first_warning'].split(' (')[0][:1].lower() + top[0]['first_warning'].split(' (')[0][1:]}.",
                        "Put these triggers in the monitoring plan and the covenants before limits are loaded.")
    else:
        head = "No stress run is on file for this deal, so no default path can be sized. Run the Stress Lab first."
        plain = C.plain("This imagines the deal has failed and works out the most likely reasons.", "No stress run is on file for this deal.",
                        "Run the stress test, then open this again.")
    out = {"proposal_id": pid, "obligor": p["obligor"]["name"], "structure": {k: st[k] for k in ("kind", "label", "note")},
           "headline": head, "plain": plain, "paths": top, "considered": len(paths),
           "pd_12m": C.efig(pid, pd12, "share", "12-month PD today", "engine.analyse", tsrc),
           "stress_run": sr["run_id"], "stress_verdict": sr.get("verdict"),
           "note": ("Probabilities are the calibrated one-year frequencies of each driver's move (R13 §S); paths are not exclusive, "
                    "so they do not add up. Speeds are an expert view by channel."),
           "method": __doc__.split("Method", 1)[1].strip()}
    return json.dumps(out, default=str)


def premortem(pid: str, which: str = "selected", terms: dict[str, Any] | None = None) -> dict[str, Any]:
    from backend.dealdesk import params
    pid = C.resolve_id(pid)
    C.proposal(pid)
    return json.loads(_premortem(pid, which, json.dumps(terms or {}, sort_keys=True, default=str), C.cache_key()))
