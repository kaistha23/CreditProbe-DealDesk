"""The monitoring front page, the deep dive and the alerts (R16 M8). Deterministic writers only (N4).

Reads the published relations (data/scorecard_v5/monitoring-saudi-v1, built by build.py) and the service store
(findings register at run time, maker-checker conclusions). Every line names its relation and rows (`trace`).

  health(today)               per scorecard: RAG per MMSG criterion, overall RAG, one line
  breaches(today)             the 5-10 breaches that matter across scorecards, ranked
  deep_dive(sid, today)       tests over time, segment drill, characteristics, root cause, recommended actions, findings
  register(today)             the findings register (seed + run time), with overdue flags
  brief_items(today)          alerts for Noor's brief
"""
from __future__ import annotations

import datetime as dt
import functools
import math
import os
from typing import Any

import pandas as pd

from backend.scorecard_v5 import engine, paths
from backend.scorecard_v5.monitoring import compute

RELEASE = "monitoring-saudi-v1"
DIR = paths.DOMAIN.parent / RELEASE
DOMAIN = "scorecard_monitoring"
RANK = {"red": 3, "amber": 2, "green": 1, "na": 0}
CRITERIA = ["discrimination", "calibration", "stability", "overrides", "migration", "data_quality", "usage", "cycle", "findings"]
TITLES = {k: v["title"] for k, v in compute.POLICY["criteria"].items()}
#: headline metrics per criterion, lead first; series metrics have a value per period, window metrics one value
HEAD = {
    "discrimination": ["gini", "gini_drop_rel", "gini_window"],
    "calibration": ["oe_ratio", "binomial_red", "hl_p"],
    "stability": ["psi", "csi_max"],
    "overrides": ["override_rate", "override_upgrade_oe"],
    "migration": ["grade_share_shift", "grade_max_share", "migration_2notch"],
    "data_quality": ["missing_inputs", "unseen_bins", "missing_outcome"],
    "usage": ["out_of_scope"],
}
SERIES = {"gini", "ks", "gini_drop_rel", "oe_ratio", "psi", "csi_max", "override_rate", "grade_share_shift", "grade_max_share", "migration_2notch",
          "missing_inputs", "unseen_bins", "missing_outcome", "out_of_scope"}
CRIT_WEIGHT = {"calibration": 1.3, "discrimination": 1.3, "usage": 1.2, "cycle": 1.15, "stability": 1.1, "findings": 1.05, "overrides": 1.0,
               "migration": 0.9, "data_quality": 0.9}
LABEL = {
    "gini": "Gini (matured period)", "ks": "KS", "gini_drop_rel": "Fall in Gini since development", "gini_window": "Gini on the latest matured window",
    "gini_segment": "Gini by segment", "oe_ratio": "Observed / expected default rate", "binomial_red": "Grades red on the binomial test",
    "hl_p": "Hosmer-Lemeshow p-value", "psi": "Score PSI", "csi_max": "Largest characteristic CSI", "override_rate": "Override rate",
    "override_upgrade_oe": "Upgrade overrides: observed / expected", "grade_share_shift": "Largest grade-share change vs development",
    "grade_max_share": "Largest single-grade share", "migration_2notch": "Moved two or more grades in a year",
    "missing_inputs": "Largest missing rate of a model input", "unseen_bins": "Rows outside the development ranges",
    "missing_outcome": "Matured rows without an outcome", "out_of_scope": "Scored outside the approved scope",
    "cycle_used": "Time since the last full independent validation", "findings_overdue": "Open findings past due",
}
FMT = {"gini": "pct", "ks": "pct", "gini_drop_rel": "pct", "gini_window": "pct", "gini_segment": "pct", "oe_ratio": "x", "binomial_red": "int",
       "hl_p": "p", "psi": "num3", "csi_max": "num3", "override_rate": "pct", "override_upgrade_oe": "x", "grade_share_shift": "pts",
       "grade_max_share": "pct", "migration_2notch": "pct", "missing_inputs": "pct", "unseen_bins": "pct", "missing_outcome": "pct",
       "out_of_scope": "pct", "cycle_used": "months", "findings_overdue": "int", "oe_grade": "x", "oe_segment": "x", "psi_segment": "num3"}
DECISIONS = {"unchanged": "Leave the model unchanged", "overlay": "Temporary adjustment (overlay) with a remediation plan", "recalibrate": "Recalibrate",
             "redevelop": "Redevelop", "restrict": "Restrict use to the approved scope", "withdraw": "Withdraw",
             "monitor": "Investigate the shift and monitor monthly (redevelopment review if it persists)"}


def today() -> dt.date:
    v = os.environ.get("CP_TODAY")
    try:
        return dt.date.fromisoformat(v) if v else dt.date.today()
    except ValueError:
        return dt.date.today()


def fmt(v: Any, kind: str) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    v = float(v)
    return {"pct": f"{v:.1%}", "x": f"{v:.2f}×", "int": f"{v:,.0f}", "p": ("< 0.001" if v < 0.001 else f"{v:.3f}"), "num3": f"{v:.3f}",
            "pts": f"{v * 100:.1f} pts", "months": f"{v:.0f} months"}.get(kind, f"{v:,.2f}")


# ------------------------------------------------------------------ the relations


def _mtime() -> float:
    try:
        return max(p.stat().st_mtime for p in DIR.glob("*.parquet"))
    except ValueError:
        return 0.0


@functools.lru_cache(maxsize=2)
def _load(stamp: float) -> dict[str, pd.DataFrame]:
    return {p.stem: pd.read_parquet(p) for p in DIR.glob("*.parquet")}


def rel(name: str) -> pd.DataFrame:
    return _load(_mtime())[name]


def inventory() -> dict[str, dict[str, Any]]:
    return {r["scorecard_id"]: r for r in rel("sc_model_inventory").to_dict("records")}


def schedule() -> dict[str, dict[str, Any]]:
    return {r["scorecard_id"]: r for r in rel("sc_monitor_schedule").to_dict("records")}


def _trace(relation: str, keys: dict[str, Any], period: str = "", column: str = "value") -> dict[str, Any]:
    return {"domain": DOMAIN, "relation": relation, "keys": keys, "period": period, "column": column}


def _series(sid: str, metric: str, segment: str | None = None) -> pd.DataFrame:
    m = rel("sc_monitor_metric")
    x = m[(m.scorecard_id == sid) & (m.metric == metric)]
    if segment is not None:
        x = x[x.segment == segment]
    return x.sort_values("period")


def _since(x: pd.DataFrame) -> str:
    """The first period of the streak of non-green values that runs to the latest period."""
    since = ""
    for r in x.sort_values("period", ascending=False).itertuples():
        if r.status in ("red", "amber"):
            since = r.period
        else:
            break
    return since


# ------------------------------------------------------------------ store-backed facts


def _store():
    from backend.scorecard_v5 import api
    return api.store()


def register(on: dt.date | None = None, store=None) -> list[dict[str, Any]]:
    """The findings register: the published seed overlaid by the run-time store (new findings, status / owner / due changes)."""
    on = on or today()
    rows = {r["finding_id"]: dict(r) for r in rel("sc_findings_register").to_dict("records")}
    for r in rows.values():
        r["origin"] = "register"
    st = store if store is not None else _store()
    for r in st.findings():
        rows[r["finding_id"]] = {**rows.get(r["finding_id"], {}), **r}
    out = []
    for r in rows.values():
        due = dt.date.fromisoformat(str(r["due_on"])[:10])
        r["overdue"] = r["status"] != "closed" and due < on
        r["days_overdue"] = (on - due).days if r["overdue"] else 0
        r["trace"] = _trace("sc_findings_register", {"finding_id": r["finding_id"]}, column="due_on") if r.get("origin") == "register" else \
            {"domain": "scorecard", "relation": "scorecard service store: findings", "keys": {"finding_id": r["finding_id"]}, "status": "service_store"}
        out.append(r)
    sev = {"High": 0, "Medium": 1, "Low": 2}
    out.sort(key=lambda r: (r["status"] == "closed", not r["overdue"], sev.get(r["severity"], 3), r["due_on"]))
    return out


def last_full_validation(sid: str, store=None) -> dict[str, Any]:
    """The latest full independent validation: the inventory's, or a later CreditProbe validation approved by a checker."""
    inv = inventory()[sid]
    best = {"date": str(inv["last_full_validation"]), "ref": inv["last_validation_ref"], "conclusion": inv["last_validation_conclusion"],
            "source": "inventory", "trace": _trace("sc_model_inventory", {"scorecard_id": sid}, column="last_full_validation")}
    st = store if store is not None else _store()
    for vid, c in st.conclusions().items():
        if c.get("state") == "approved" and c.get("scorecard_id") == sid and c.get("full") and str(c.get("checker_at", ""))[:10] > best["date"]:
            best = {"date": str(c["checker_at"])[:10], "ref": vid, "conclusion": c["conclusion"], "source": "creditprobe",
                    "trace": {"domain": "scorecard", "relation": "scorecard service store: conclusions", "keys": {"validation_id": vid}, "status": "service_store"}}
    return best


def pending_reviews(sid: str, store=None) -> list[dict[str, Any]]:
    """CreditProbe validations of this scorecard whose conclusion is not yet approved by a checker."""
    st = store if store is not None else _store()
    cons = st.conclusions()
    out = []
    for v in st.validations():
        if v["scorecard_id"] != sid:
            continue
        c = cons.get(v["validation_id"]) or {}
        if c.get("state") != "approved":
            out.append({"validation_id": v["validation_id"], "created_at": v["created_at"], "review": v["review"], "state": c.get("state") or "not proposed",
                        "conclusion": c.get("conclusion") or v["review"].get("conclusion") or ""})
    return out


# ------------------------------------------------------------------ criterion lines


def _criterion(sid: str, crit: str, on: dt.date, store=None) -> dict[str, Any]:
    """One criterion of one scorecard: status, lead metric, value, threshold, trend, since, sentence, trace."""
    inv = inventory()[sid]
    L = compute.limits(sid)
    if crit == "cycle":
        lv = last_full_validation(sid, store)
        last = dt.date.fromisoformat(lv["date"])
        months = (on - last).days / 30.4375
        cyc = int(inv["validation_cycle_months"])
        used = months / cyc
        status = engine.rate(used, L["cycle_used"])
        due = _add_months(last, cyc)
        pend = pending_reviews(sid, store)
        tail = ""
        if pend and status != "green":
            p0 = pend[0]
            tail = (f" A CreditProbe validation ({_d(p0['created_at'])}) is waiting for its conclusion to be approved by a checker; "
                    "until then it does not count as the independent validation.")
        sent = (f"Last full independent validation {lv['ref']} on {_dmy(last)}; {months:.0f} months against a {cyc}-month cycle for a {inv['tier']} model"
                + (f": overdue since {_dmy(due)}." if due < on else f": next due {_dmy(due)}.") + tail)
        return {"criterion": crit, "status": status, "metric": "cycle_used", "label": LABEL["cycle_used"], "value": round(months, 1),
                "display": f"{months:.0f} of {cyc} months", "threshold": f"{inv['tier']}: full validation every {cyc} months (bank policy, MMS 3.7.1)",
                "trend": [], "since": due.isoformat() if due < on else "", "sentence": sent, "period": on.isoformat(),
                "owner": inv["validator"], "trace": [lv["trace"], _trace("sc_model_inventory", {"scorecard_id": sid}, column="validation_cycle_months")],
                "also": []}
    if crit == "findings":
        reg = [r for r in register(on, store) if r["scorecard_id"] == sid and r["status"] != "closed"]
        od = [r for r in reg if r["overdue"]]
        status = "red" if any(r["severity"] == "High" for r in od) else "amber" if od else "green"
        worst = max(od, key=lambda r: (r["severity"] == "High", r["days_overdue"])) if od else None
        sent = (f"{len(od)} of {len(reg)} open findings are past due; the oldest, \"{worst['title']}\" ({worst['severity']}), was due {_dmy(dt.date.fromisoformat(worst['due_on']))}"
                f" ({worst['days_overdue']} days ago)." if od else f"{len(reg)} open findings, none past due.")
        return {"criterion": crit, "status": status, "metric": "findings_overdue", "label": LABEL["findings_overdue"], "value": float(len(od)),
                "display": f"{len(od)} of {len(reg)}", "threshold": "none past due (MMS 3.7.10: high-severity findings remedied promptly)",
                "trend": [], "since": worst["due_on"] if worst else "", "sentence": sent, "period": on.isoformat(),
                "owner": worst["owner"] if worst else inv["model_owner"], "trace": [r["trace"] for r in od[:5]], "also": [],
                "findings": [r["finding_id"] for r in od]}
    lines = []
    for metric in HEAD[crit]:
        x = _series(sid, metric, "" if metric not in ("csi_max", "grade_share_shift", "grade_max_share", "missing_inputs", "out_of_scope") else None)
        if x.empty:
            continue
        cur = x.iloc[-1]
        lines.append((metric, x, cur))
    if not lines:
        return {"criterion": crit, "status": "na", "metric": "", "label": TITLES[crit], "value": None, "display": "not applicable",
                "threshold": "", "trend": [], "since": "", "sentence": _na_sentence(sid, crit), "period": "", "owner": inv["model_owner"], "trace": [], "also": []}
    lead = max(lines, key=lambda t: (RANK[t[2]["status"]], -HEAD[crit].index(t[0])))
    metric, x, cur = lead
    series_x = x if metric in SERIES else (_series(sid, "oe_ratio", "") if crit == "calibration" else _series(sid, "gini", "") if crit == "discrimination" else x)
    since = _since(series_x) if cur["status"] in ("red", "amber") else ""
    owner = inv["data_owner"] if crit == "data_quality" else inv["override_owner"] if crit == "overrides" else inv["model_owner"]
    trend = [{"period": r.period, "value": None if pd.isna(r.value) else float(r.value), "status": r.status} for r in series_x.tail(8).itertuples()]
    also = [f"{LABEL[m]} {fmt(c['value'], FMT[m])} ({c['status']})" for m, _x, c in lines if m != metric and c["status"] in ("red", "amber")]
    thr = "no grade red, at most one amber" if metric == "binomial_red" else str(cur["threshold"] or L.get(metric, {}).get("text", ""))
    return {"criterion": crit, "status": cur["status"], "metric": metric, "label": LABEL[metric], "value": None if pd.isna(cur["value"]) else float(cur["value"]),
            "display": fmt(cur["value"], FMT[metric]), "threshold": thr, "trend": trend,
            "since": since, "sentence": _sentence(sid, metric, cur, since), "period": str(cur["period"]), "owner": owner,
            "trace": [_trace("sc_monitor_metric", {"scorecard_id": sid, "metric": metric, "period": str(cur["period"]), "segment": str(cur["segment"])},
                             str(cur["period"]))], "also": also}


def _na_sentence(sid: str, crit: str) -> str:
    if crit == "overrides":
        return "Not applicable: this scorecard grades the live book every month and records no overrides."
    return "Not applicable to this scorecard."


def _add_months(d: dt.date, n: int) -> dt.date:
    import calendar
    y, m = divmod(d.month - 1 + n, 12)
    return dt.date(d.year + y, m + 1, min(d.day, calendar.monthrange(d.year + y, m + 1)[1]))


def _dmy(d: dt.date) -> str:
    return d.strftime("%d %b %Y").lstrip("0")


def _d(ts: float) -> str:
    return _dmy(dt.datetime.fromtimestamp(float(ts), dt.timezone.utc).date())


def _sentence(sid: str, metric: str, r: Any, since: str) -> str:
    """The plain sentence of a metric line: fact, number, comparison, since when."""
    p, v, seg = str(r["period"]), r["value"], str(r["segment"] or "")
    obs, exp = r.get("observed"), r.get("expected")
    sn = f"; outside the green band since {since}" if since and since != p else ""
    if metric == "oe_ratio":
        return f"Defaults ran at {obs:.2%} against {exp:.2%} predicted by the grade PDs in {p} ({v:.2f}×){sn}."
    if metric == "binomial_red":
        return f"{int(v)} grade(s) fail the binomial test (grade PD too low at the 1% level) on {r['note']}."
    if metric == "hl_p":
        return f"Hosmer-Lemeshow p {fmt(v, 'p')} ({r['note']}): the grade PDs do not fit the observed defaults."
    if metric == "gini":
        return f"Gini {v:.1%} in {p} (the latest period with a closed 12-month outcome){sn}."
    if metric == "gini_drop_rel":
        return f"Gini fell from {exp:.1%} at development to {obs:.1%} in {p}, a {v:.0%} relative fall{sn}."
    if metric == "gini_window":
        return f"Gini {v:.1%} on {r['note']} against {exp:.1%} at development."
    if metric == "psi":
        return f"The score distribution in {p} has moved from development: PSI {v:.3f}{sn}."
    if metric == "csi_max":
        return f"{_var_label(sid, seg)} has moved most: CSI {v:.3f} in {p}{sn}."
    if metric == "override_rate":
        return f"Officers overrode {v:.1%} of decisions in {p}{sn}."
    if metric == "override_upgrade_oe":
        return f"Approvals against the grade defaulted at {obs:.2%} against {exp:.2%} expected for their grades ({v:.2f}×), {r['note']}."
    if metric == "grade_share_shift":
        return f"Grade {seg} holds {obs:.1%} of the scored population in {p} against {exp:.1%} at development ({v * 100:+.1f} points){sn}."
    if metric == "grade_max_share":
        return f"Grade {seg} holds {v:.1%} of the scored population in {p}{sn}."
    if metric == "migration_2notch":
        return f"{v:.1%} of re-graded {('borrowers' if sid == 'SME-ANN' else 'accounts')} moved two or more grades in a year to {p} ({obs:.1%} down){sn}."
    if metric == "missing_inputs":
        return f"The largest missing rate of a model input in {p} is {v:.1%} ({_var_label(sid, seg)})."
    if metric == "unseen_bins":
        return f"{v:.1%} of rows in {p} have an input outside the ranges seen at development."
    if metric == "missing_outcome":
        return f"{v:.1%} of matured rows in {p} have no recorded outcome."
    if metric == "out_of_scope":
        return (f"{v:.1%} of the population scored in {p} is {seg or 'outside the approved scope'}, a segment absent from development and outside the approved use{sn}."
                if v > 0 else f"The whole population scored in {p} is inside the approved scope.")
    return f"{LABEL.get(metric, metric)} {fmt(v, FMT.get(metric, ''))} in {p}."


@functools.lru_cache(maxsize=8)
def _var_labels(sid: str) -> dict[str, str]:
    sp = engine.domain(sid).spec
    return {v["name"]: v["label"] for v in sp["variables"] + sp.get("candidates", [])}


def _var_label(sid: str, name: str) -> str:
    return _var_labels(sid).get(name, name.replace("_", " "))


# ------------------------------------------------------------------ health and breaches


def health(on: dt.date | None = None, store=None) -> list[dict[str, Any]]:
    on = on or today()
    inv = inventory()
    out = []
    for sid in inv:
        crits = [_criterion(sid, c, on, store) for c in CRITERIA]
        reds = [c for c in crits if c["status"] == "red"]
        ambers = [c for c in crits if c["status"] == "amber"]
        overall = "red" if reds else "amber" if ambers else "green"
        i = inv[sid]
        line = (f"{len(reds)} red, {len(ambers)} amber of {len([c for c in crits if c['status'] != 'na'])} criteria"
                + (f": {', '.join(TITLES[c['criterion']].lower() for c in reds)} red." if reds else "."))
        out.append({"scorecard_id": sid, "name": i["name"], "version": i["version"], "tier": i["tier"], "book": i["book"], "overall": overall,
                    "line": line, "criteria": crits, "model_owner": i["model_owner"], "frequency": i["monitoring_frequency"]})
    return out


def _score(b: dict[str, Any], tier: str, on: dt.date) -> float:
    s = {"red": 10.0, "amber": 4.0}.get(b["status"], 0.0) * CRIT_WEIGHT.get(b["criterion"], 1.0) * (1.2 if tier == "Tier 1" else 1.0)
    if b.get("since"):
        try:
            s += min(_age_periods(b["since"], on), 12) * 0.15
        except ValueError:
            pass
    return round(s, 3)


def _age_periods(since: str, on: dt.date) -> int:
    if "Q" in since:
        y, q = since.split("Q")
        return max((on.year - int(y)) * 4 + ((on.month - 1) // 3 + 1) - int(q), 0)
    if len(since) == 7:
        y, m = since.split("-")
        return max((on.year - int(y)) * 12 + on.month - int(m), 0) // 3
    d = dt.date.fromisoformat(since[:10])
    return max((on - d).days // 91, 0)


def breaches(on: dt.date | None = None, store=None, hl: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """The breaches that matter: one per scorecard and criterion (the criterion's worst metric leads, the others are named
    in `also`), red first, ranked by severity, criterion weight, model tier and how long it has lasted; 5-10 lines."""
    on = on or today()
    hl = hl or health(on, store)
    pol = compute.POLICY["breaches"]
    cands = []
    for h in hl:
        for c in h["criteria"]:
            if c["status"] not in ("red", "amber"):
                continue
            b = {**c, "scorecard_id": h["scorecard_id"], "scorecard": h["name"], "tier": h["tier"], "criterion_title": TITLES[c["criterion"]],
                 "id": f"{h['scorecard_id']}:{c['criterion']}"}
            b["score"] = _score(b, h["tier"], on)
            b["headline"] = _headline(b)
            cands.append(b)
    cands.sort(key=lambda b: (-RANK[b["status"]], -b["score"], b["scorecard_id"], b["criterion"]))
    reds = [b for b in cands if b["status"] == "red"]
    n = min(max(len(reds), pol["min"]), pol["max"])
    out = cands[:n]
    for k, b in enumerate(out, 1):
        b["rank"] = k
    return out


def _headline(b: dict[str, Any]) -> str:
    sc = b["scorecard"].replace(" Scorecard", "")
    c = b["criterion"]
    word = {"discrimination": "ranking power", "calibration": "PDs", "stability": "population", "overrides": "overrides",
            "migration": "grades", "data_quality": "data", "usage": "use", "cycle": "validation", "findings": "findings"}[c]
    if c == "calibration":
        if b["metric"] == "oe_ratio":
            return f"{sc}: {word} {'under' if (b['value'] or 0) > 1 else 'over'}-predict defaults ({b['display']})"
        if b["metric"] == "binomial_red":
            return f"{sc}: {b['display']} grade PD(s) fail the binomial test"
        return f"{sc}: {word} do not fit defaults ({_lc(b['label'])} {b['display']})"
    if c == "usage":
        return f"{sc}: {b['display']} scored outside the approved scope"
    if c == "cycle":
        return f"{sc}: full validation {'overdue' if b['status'] == 'red' else 'nearly due'} ({b['display']})"
    if c == "findings":
        return f"{sc}: {b['display']} open findings past due"
    if c == "stability":
        return f"{sc}: {word} has moved ({_lc(b['label'])} {b['display']})"
    return f"{sc}: {_lc(b['label'])} {b['display']}"


def _lc(label: str) -> str:
    """Lower-case the first word unless it is an acronym (PSI, CSI, KS)."""
    w = label.split(" ", 1)
    return label if w[0].isupper() else label[0].lower() + label[1:]


# ------------------------------------------------------------------ plain words, root cause, actions


def plain_words(hl: list[dict[str, Any]], br: list[dict[str, Any]]) -> list[str]:
    """3 lines, under 60 words: what is checked, how many breaches, what to do first."""
    nred = len([b for b in br if b["status"] == "red"])
    lines = [f"{len(hl)} scorecards checked against the MMSG monitoring criteria: ranking, PDs, population, use and validation cycle."]
    lines.append(f"{len(br)} breaches matter today, {nred} red; act first on {br[0]['headline']}." if br else "Nothing is outside its limits today.")
    lines.append("Click a line for its deep dive; the Ask tab runs a full validation with its Word report.")
    return lines


def short_cause(crits: dict[str, dict[str, Any]]) -> str:
    st = {k: v["status"] for k, v in crits.items()}
    if st.get("calibration") == "red" and st.get("discrimination") != "red":
        return "Ranking holds but the PDs are wrong: recalibrate, not redevelop."
    if st.get("discrimination") == "red":
        return "Ranking power has gone: redevelop."
    if st.get("usage") == "red":
        return "It is used outside its approved scope."
    if st.get("stability") == "red":
        return "The scored population has moved from development."
    if st.get("cycle") == "red":
        return "Its full validation is overdue."
    return "Performance is inside its limits."


def root_cause(sid: str, crits: dict[str, dict[str, Any]]) -> list[str]:
    """Deterministic root-cause note: which facts explain which breach (rules, in order)."""
    out = []
    st = {k: v["status"] for k, v in crits.items()}
    cal, dis = crits.get("calibration", {}), crits.get("discrimination", {})
    if st.get("calibration") == "red" and st.get("discrimination") in ("green", "amber"):
        out.append(f"Ranking holds (Gini {dis.get('display', '—')}) while the PD level is wrong ({cal.get('label')} {cal.get('display')}): "
                   "the scorecard still orders customers, but the grade PDs no longer match the default rate. That points to recalibration, not redevelopment.")
    if st.get("calibration") == "red" and st.get("discrimination") == "red":
        out.append("Both ranking and level have failed: recalibration alone will not restore the scorecard.")
    if st.get("stability") in ("red", "amber"):
        ch = _top_csi(sid)
        if ch:
            out.append(f"The population shift is led by {ch['label']} (CSI {ch['csi']:.3f}" + (f", then {ch['next']} {ch['next_csi']:.3f}" if ch.get("next") else "") +
                       "): the people being scored differ from those the scorecard was built on.")
    if st.get("usage") in ("red", "amber"):
        u = crits["usage"]
        out.append(f"{u['sentence']} Part of the drift and the miscalibration sits in that segment, which had no development data.")
    if st.get("migration") in ("red", "amber"):
        out.append(crits["migration"]["sentence"])
    if st.get("overrides") in ("red", "amber"):
        up = _series(sid, "override_upgrade_oe", "")
        extra = ""
        if not up.empty and up.iloc[-1]["status"] in ("red", "amber"):
            u0 = up.iloc[-1]
            extra = (f" Approvals against the grade defaulted at {u0['observed']:.2%} against {u0['expected']:.2%} expected ({u0['value']:.2f}×): "
                     "officers' upgrades are not adding information the score lacks.")
        out.append(crits["overrides"]["sentence"] + extra)
    if st.get("cycle") == "red":
        out.append(crits["cycle"]["sentence"])
    if not out:
        out.append("Every MMSG monitoring criterion is inside its limits; no root cause to explain.")
    return out


def _top_csi(sid: str) -> dict[str, Any] | None:
    c = rel("sc_monitor_characteristic")
    x = c[(c.scorecard_id == sid) & c.in_model]
    if x.empty:
        return None
    last = x[x.period == x.period.max()].sort_values("csi", ascending=False)
    a = last.iloc[0]
    out = {"label": a["label"], "csi": float(a["csi"])}
    if len(last) > 1:
        out.update({"next": last.iloc[1]["label"], "next_csi": float(last.iloc[1]["csi"])})
    return out


def actions(sid: str, crits: dict[str, dict[str, Any]], on: dt.date) -> list[dict[str, Any]]:
    """Recommended actions in MMS 4.3.3 terms (recalibrate, redevelop, overlay, restrict use, leave unchanged)."""
    inv = inventory()[sid]
    due_days = compute.POLICY["finding_due_days"]
    st = {k: v["status"] for k, v in crits.items()}
    out = []

    def add(kind: str, why: str, severity: str, owner: str) -> None:
        out.append({"decision": kind, "title": DECISIONS[kind], "why": why, "severity": severity, "owner": owner,
                    "due": (on + dt.timedelta(days=due_days[severity])).isoformat(), "reference": "MMS 4.3.3"})
    if st.get("discrimination") == "red":
        add("redevelop", f"Ranking power is below its limit: {crits['discrimination']['sentence']}", "High", inv["model_owner"])
    if st.get("calibration") == "red":
        cal = crits["calibration"]
        oe = _series(sid, "oe_ratio", "").iloc[-1]
        scalar = float(oe["value"]) if not pd.isna(oe["value"]) else None
        if st.get("discrimination") != "red":
            add("recalibrate", f"{cal['sentence']} Ranking holds, so recalibrate the grade PDs on the latest matured cohorts.", "High", inv["model_owner"])
        if scalar and scalar > 1:
            add("overlay", f"Until the recalibrated PDs are approved, apply a PD scalar of {scalar:.2f}× (the latest observed / expected) to the grade PDs "
                            "used for pricing and ECL, documented and justified (MMS 3.3.5).", "High", inv["model_owner"])
    if st.get("usage") in ("red", "amber"):
        add("restrict", f"{crits['usage']['sentence']} Restrict use to {inv['approved_segments'].replace(' | ', ', ')}, or validate the new segment first "
                        "(MMS 3.5.1-3.5.2).", "High" if st["usage"] == "red" else "Medium", inv["model_owner"])
    if st.get("stability") == "red" and st.get("discrimination") != "red":
        add("monitor", f"{crits['stability']['sentence']} Investigate the characteristic shift; if it persists for two more periods, start a redevelopment review.",
            "Medium", inv["model_owner"])
    if st.get("cycle") == "red":
        out.append({"decision": "validate", "title": "Full independent validation now", "why": crits["cycle"]["sentence"], "severity": "High",
                    "owner": inv["validator"], "due": (on + dt.timedelta(days=60)).isoformat(), "reference": "MMS 3.7.1"})
    if not out:
        add("unchanged", "Every criterion is inside its limits.", "Low", inv["model_owner"])
    seen, uniq = set(), []
    for a in out:
        if (a["decision"], a["why"][:40]) not in seen:
            seen.add((a["decision"], a["why"][:40]))
            uniq.append(a)
    return uniq


# ------------------------------------------------------------------ deep dive


def _fig(data: list[dict[str, Any]], title: str, ytitle: str = "", ytick: str = "", **kw: Any) -> dict[str, Any]:
    return engine._fig(data, title, "", ytitle, yaxis={"tickformat": ytick, "title": {"text": ytitle}} if ytick else {"title": {"text": ytitle}},
                       xaxis={"tickangle": -45, "automargin": True, "type": "category"}, legend={"orientation": "h", "x": 0, "xanchor": "left", "y": 1.02, "yanchor": "bottom"}, **kw)


def _trend_chart(sid: str, metric: str, title: str, ytitle: str, ytick: str = "", lim: str | None = None) -> dict[str, Any] | None:
    x = _series(sid, metric, "" if metric not in ("csi_max", "grade_share_shift", "out_of_scope") else None)
    if x.empty:
        return None
    L = compute.limits(sid).get(lim or metric)
    cols = [engine.RAG_COLOUR.get(s, engine.PALETTE["grey"]) if smp != "development" else engine.PALETTE["grey"] for s, smp in zip(x.status, x["sample"])]
    data = [{"type": "bar", "name": LABEL.get(metric, metric), "x": x.period.tolist(), "y": [None if pd.isna(v) else round(float(v), 5) for v in x.value],
             "marker": {"color": cols}}]
    if L and L.get("kind") in ("high", "low"):
        p0, p1 = x.period.iloc[0], x.period.iloc[-1]
        data += [engine._hline(L["green"], engine.PALETTE["green"], "Green limit", p0, p1), engine._hline(L["amber"], engine.PALETTE["amber"], "Amber limit", p0, p1)]
    if L and L.get("kind") == "band":
        p0, p1 = x.period.iloc[0], x.period.iloc[-1]
        data += [engine._hline(L["green"][1], engine.PALETTE["green"], "Green upper", p0, p1), engine._hline(L["amber"][1], engine.PALETTE["amber"], "Amber upper", p0, p1)]
    return {"id": f"trend_{metric}", "title": title, "figure": _fig(data, title + " (grey: development)", ytitle, ytick), "note": (L or {}).get("text", "")}


def _oe_chart(sid: str) -> dict[str, Any] | None:
    x = _series(sid, "oe_ratio", "")
    if x.empty:
        return None
    data = [engine._line("Predicted (grade PD)", x.period.tolist(), [round(float(v), 5) for v in x.expected], engine.PALETTE["grey"], mode="lines+markers"),
            engine._line("Observed default rate", x.period.tolist(), [round(float(v), 5) for v in x.observed], engine.PALETTE["red"], mode="lines+markers",
                         marker={"color": [engine.RAG_COLOUR[s] for s in x.status], "size": 9})]
    return {"id": "trend_oe", "title": "Observed vs predicted default rate", "figure": _fig(data, "Observed vs predicted default rate by period", "Default rate", ".1%"),
            "note": "Periods whose 12-month outcome has closed."}


def deep_dive(sid: str, on: dt.date | None = None, store=None) -> dict[str, Any]:
    on = on or today()
    inv = inventory()
    if sid not in inv:
        raise KeyError(sid)
    i = inv[sid]
    hl = next(h for h in health(on, store) if h["scorecard_id"] == sid)
    crits = {c["criterion"]: c for c in hl["criteria"]}
    m = rel("sc_monitor_metric")
    mm = m[m.scorecard_id == sid]
    facts = compute.POLICY
    charts = [c for c in (
        _trend_chart(sid, "gini", "Gini by period", "Gini", ".0%"),
        _oe_chart(sid),
        _trend_chart(sid, "oe_ratio", "Observed / expected by period", "O / E"),
        _trend_chart(sid, "psi", "Score PSI by period", "PSI"),
        _trend_chart(sid, "csi_max", "Largest characteristic CSI by period", "CSI", lim="csi"),
        _trend_chart(sid, "override_rate", "Override rate by period", "Override rate", ".0%"),
        _trend_chart(sid, "migration_2notch", "Moved two or more grades in a year", "Share", ".0%"),
        _trend_chart(sid, "grade_share_shift", "Largest grade-share change vs development", "Points", ".0%"),
        _trend_chart(sid, "out_of_scope", "Scored outside the approved scope", "Share", ".0%"),
    ) if c]
    seg_col = str(i["segment_col"])
    segs = {}
    for metric in ("gini_segment", "oe_segment", "psi_segment"):
        for r in mm[mm.metric == metric].itertuples():
            d = segs.setdefault(r.segment, {"segment": r.segment})
            if metric == "gini_segment":
                d.update({"n": None if pd.isna(r.n) else int(r.n), "defaults": None if pd.isna(r.defaults) else int(r.defaults),
                          "gini": None if pd.isna(r.value) else float(r.value), "gini_status": r.status})
            elif metric == "oe_segment":
                d.update({"observed": r.observed, "expected": r.expected, "oe": None if pd.isna(r.value) else float(r.value), "oe_status": r.status})
            else:
                d.update({"psi": None if pd.isna(r.value) else float(r.value), "psi_status": r.status, "n_now": None if pd.isna(r.n) else int(r.n)})
    seg_rows = sorted(segs.values(), key=lambda d: -(d.get("n_now") or d.get("n") or 0))
    approved = set(str(i["approved_segments"]).split(" | "))
    for d in seg_rows:
        d["in_scope"] = d["segment"] in approved
    grades = [{"grade": r.segment, "n": int(r.n), "defaults": int(r.defaults), "observed": r.observed, "expected": r.expected,
               "oe": float(r.value), "status": r.status, "note": r.note} for r in mm[mm.metric == "oe_grade"].itertuples()]
    c = rel("sc_monitor_characteristic")
    cc = c[c.scorecard_id == sid]
    last = cc[cc.period == cc.period.max()]
    chars = [{"variable": r.variable, "label": r.label, "in_model": bool(r.in_model), "csi": None if pd.isna(r.csi) else float(r.csi),
              "missing_pct": float(r.missing_pct), "unseen_pct": None if pd.isna(r.unseen_pct) else float(r.unseen_pct),
              "iv_dev": None if pd.isna(r.iv_dev) else float(r.iv_dev), "iv_mon": None if pd.isna(r.iv_mon) else float(r.iv_mon), "status": r.status}
             for r in last.sort_values(["in_model", "csi"], ascending=[False, False]).itertuples()]
    reasons = [{"reason": r.segment, "share": float(r.value), "n": int(r.n), "observed": None if pd.isna(r.observed) else float(r.observed),
                "expected": None if pd.isna(r.expected) else float(r.expected)} for r in mm[mm.metric == "override_reason_share"].sort_values("value", ascending=False).itertuples()]
    reg = [r for r in register(on, store) if r["scorecard_id"] == sid]
    st = store if store is not None else _store()
    hist = []
    cons = st.conclusions()
    for v in st.validations():
        if v["scorecard_id"] == sid:
            hist.append({"validation_id": v["validation_id"], "thread_id": v["thread_id"], "title": v["title"], "as_of": v["as_of"], "overall": v["overall"],
                         "created_at": v["created_at"], "review": v["review"], "maker_checker": cons.get(v["validation_id"])})
    rc = root_cause(sid, crits)
    acts = actions(sid, crits, on)
    reds = [x for x in hl["criteria"] if x["status"] == "red"]
    pw = [f"{i['name']} v{i['version']}, {i['tier']}, owner {i['model_owner'].split(' (')[0]}: {hl['overall'].upper()} today.",
          (f"Red: {', '.join(TITLES[x['criterion']].lower() for x in reds)}." if reds else "No criterion is red."),
          short_cause(crits),
          f"First action: {acts[0]['title'].split(' (')[0].lower()}, owner {acts[0]['owner'].split(' (')[0]}, by {_dmy(dt.date.fromisoformat(acts[0]['due']))}."]
    return {"scorecard_id": sid, "name": i["name"], "version": i["version"], "tier": i["tier"], "tier_reason": i["tier_reason"], "overall": hl["overall"],
            "line": hl["line"], "inventory": {k: (v if not isinstance(v, float) or not math.isnan(v) else None) for k, v in i.items()},
            "schedule": schedule().get(sid), "plain_words": pw, "criteria": hl["criteria"], "charts": charts,
            "segments": {"by": seg_col, "rows": seg_rows, "window": str(mm[mm.metric == "gini_segment"].note.iloc[0]) if (mm.metric == "gini_segment").any() else ""},
            "grades": grades, "characteristics": chars, "characteristics_period": str(cc.period.max()), "override_reasons": reasons, "root_cause": rc, "actions": acts,
            "findings": reg, "validations": hist, "references": facts["references"],
            "sources": [f"{DOMAIN}.sc_monitor_metric", f"{DOMAIN}.sc_monitor_characteristic", f"{DOMAIN}.sc_model_inventory",
                        f"{DOMAIN}.sc_findings_register", f"{DOMAIN}.sc_monitor_schedule"]}


# ------------------------------------------------------------------ Noor's brief


def brief_items(on: dt.date | None = None, store=None, limit: int = 3) -> list[dict[str, Any]]:
    """Red breaches on Tier 1 scorecards, for Noor's brief (one line each, with Why, What to do, Open)."""
    on = on or today()
    out = []
    for b in breaches(on, store):
        if b["status"] != "red" or b["tier"] != "Tier 1":
            continue
        out.append({"id": f"scorecard:{b['id']}", "title": b["headline"], "detail": b["sentence"], "severity": "high" if b["criterion"] in
                    ("calibration", "discrimination", "usage", "cycle") else "medium", "since": b.get("since") or "", "owner": b["owner"].split(" (")[0],
                    "scorecard_id": b["scorecard_id"], "criterion": b["criterion"], "value": b["value"], "display": b["display"], "label": b["label"],
                    "trace": b["trace"], "href": f"/scorecard-validation?scorecard={b['scorecard_id']}&breach={b['criterion']}"})
        if len(out) >= limit:
            break
    return out
