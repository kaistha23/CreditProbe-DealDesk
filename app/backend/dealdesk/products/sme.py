"""PLAN_R12 Session P (I28): the SME fast-track lane.

One screen per application: the SME scorecard decision (SME-ANN v1.4, the Scorecard domain's model), the
programme's policy rules, the delegation of authority by amount, the conditions and a short paper.
Applications that fail a programme rule are exceptions: they leave the lane and go to the full Deal Desk flow.

  score(app)      points per characteristic from the scorecard's own bins, total score, grade and grade PD
  rules(app, sc)  the programme rules, each pass / fail with its value, threshold and whether a failure
                  declines (hard) or routes to the full flow (exception)
  decide(app)     Approve | Approve with conditions | Refer to full flow | Decline, the DoA level, conditions,
                  the short paper; `publish_decision` writes it back to `dd_sme_application` through E's publisher
  counts()        the landing card: applications in the lane by decision
"""
from __future__ import annotations

import datetime as dt
import json
from functools import lru_cache
from typing import Any

import pandas as pd

from backend.dealdesk.products import policy, source
from backend.dealdesk.products.project import _bool, _f

PRODUCT = "sme"
REL = "dd_sme_application"
SCORECARD = "SME-ANN"
SCORECARD_NAME, SCORECARD_VERSION = "SME Scorecard", "1.4"
#: SME-ANN's numeric characteristics (backend/scorecard_v5/domain/build.py): a row carrying them is rescored
NUMERIC_CHARACTERISTICS = ("interest_cover_x", "qualitative_score", "ebitda_margin_pct", "cash_conversion_pct",
                           "balance_buffer_months", "returned_payments_q")
DECISIONS = ("Approve", "Approve with conditions", "Refer to full flow", "Decline")


@lru_cache(maxsize=1)
def scorecard_spec() -> dict[str, Any]:
    """The SME scorecard's spec (bins, points, grades) through the Scorecard module's own domain loader (the model behind
    the registered relation SME-ANN); Deal Desk opens no scorecard file itself."""
    from backend.scorecard_v5 import engine as sc_engine
    return sc_engine.domain(SCORECARD).spec


def _grade_rank(g: str) -> int:
    try:
        return int(str(g).strip().upper().lstrip("G"))
    except ValueError:
        return 99


def norm(row: dict[str, Any]) -> dict[str, Any]:
    """A `dd_sme_application` row in the lane's terms (contract names kept; aliases added)."""
    a = dict(row)
    a.setdefault("application_id", row.get("proposal_id"))
    a.setdefault("applicant_name", row.get("applicant"))
    if a.get("amount_sar_mn") is None and row.get("amount_mn") is not None:
        a["amount_sar_mn"] = row["amount_mn"]
    if a.get("tenor_years") is None and row.get("tenor_months") is not None:
        a["tenor_years"] = _f(row["tenor_months"]) / 12.0
    a.setdefault("received_date", row.get("submitted_date"))
    return a


def score(app: dict[str, Any]) -> dict[str, Any]:
    """Rescore from the characteristics when the row carries them; else the score and grade recorded in the relation
    (the SME-ANN result E stored), with the grade PD from the scorecard's grade table."""
    if not any(app.get(v) is not None for v in NUMERIC_CHARACTERISTICS) and app.get("score") is not None:
        # the result recorded with the application: no scorecard file is opened (no side door)
        g = app.get("grade")
        grade = f"G{int(g)}" if isinstance(g, (int, float)) else str(g)
        pd_ = _f(app.get("pd")) if app.get("pd") is not None else None
        return {"scorecard": {"id": app.get("scorecard_id") or SCORECARD, "name": SCORECARD_NAME, "version": SCORECARD_VERSION},
                "score": float(app["score"]), "grade": grade, "pd": pd_, "lines": [], "recorded": True,
                "src": source.src(REL, app, "score")}
    from backend.scorecard_v5.domain import binning
    sp = scorecard_spec()
    lines, total = [], 0.0
    for v in sp["variables"]:
        x = app.get(v["name"])
        k = int(binning.assign(v, pd.Series([x], dtype=object if v["type"] == "categorical" else float))[0])
        b = v["bins"][k]
        total += float(b["points"])
        lines.append({"variable": v["name"], "label": v["label"], "value": x, "bin": b["label"], "points": float(b["points"]),
                      "src": source.src(REL, app, v["name"])})
    grade = next((g for g in sp["grades"] if (g["low"] is None or total >= g["low"]) and (g["high"] is None or total < g["high"])),
                 sp["grades"][-1])
    return {"scorecard": {"id": SCORECARD, "name": sp["name"], "version": sp["version"]}, "score": round(total, 1),
            "grade": grade["grade"], "pd": float(grade["pd"]), "lines": lines,
            "src": {"domain": "Scorecard", "relation": SCORECARD, "derived": f"{sp['name']} v{sp['version']}: sum of bin points"}}


def rules(app: dict[str, Any], sc: dict[str, Any]) -> list[dict[str, Any]]:
    P = lambda k: policy.v(k, PRODUCT)  # noqa: E731
    amt, tenor = _f(app.get("amount_sar_mn") or app.get("amount")), _f(app.get("tenor_years"), 1)
    bureau = str(app.get("bureau_flag") or app.get("simah_flag") or "").lower() or None
    rp, ic, dpd = app.get("returned_payments_q"), app.get("interest_cover_x"), app.get("external_dpd_days")
    g = _grade_rank(sc["grade"])
    na = object()
    max_amt = max([float(x["max_sar_mn"]) for x in doa_levels()[0]] or [float(P("sme.max_amount_sar_mn"))])
    out = [
        ("amount", "Amount within the programme", amt, f"≤ SAR {max_amt:g} million", amt <= max_amt, "exception"),
        ("tenor", "Tenor within the programme", tenor, f"≤ {P('sme.max_tenor_years')} years", tenor <= float(P("sme.max_tenor_years")), "exception"),
        ("grade_floor", "Scorecard grade above the decline cut-off", sc["grade"], "G1 to G7", g < 8, "hard"),
        ("grade", "Scorecard grade within the lane", sc["grade"], f"G1 to {P('sme.max_grade_eligible')}", g <= _grade_rank(P("sme.max_grade_eligible")), "exception"),
        ("bureau", "No adverse bureau record", bureau or na, "clear or watch", bureau != "adverse", "hard"),
        ("bureau_watch", "Bureau clear", bureau or na, "clear", bureau == "clear", "exception"),
        ("returned", "Returned payments in the quarter", na if rp is None else _f(rp), f"≤ {P('sme.max_returned_payments_q')}",
         _f(rp) <= float(P("sme.max_returned_payments_q")), "exception"),
        ("dpd", "No external arrears over 30 days", na if dpd is None else _f(dpd), "≤ 30 days", _f(dpd) <= 30, "exception"),
        ("cover", "Interest cover", na if ic is None else _f(ic), f"≥ {P('sme.min_interest_cover_x'):g}x",
         _f(ic) >= float(P("sme.min_interest_cover_x")), "exception"),
        ("sector", "Sector in the programme", app.get("sector"), "not " + ", ".join(P("sme.excluded_sectors")),
         app.get("sector") not in list(P("sme.excluded_sectors")), "exception"),
    ]
    unit = {"amount": lambda v: f"SAR {v:,.2f} million", "tenor": _yrs, "returned": lambda v: f"{v:g}",
            "dpd": lambda v: f"{v:g} days", "cover": lambda v: f"{v:.2f}x"}
    rows = [{"id": i, "rule": r, "value": v, "value_text": unit[i](v) if i in unit else str(v), "threshold": t, "pass": bool(ok),
             "on_fail": kind, "src": source.src(REL, app)} for i, r, v, t, ok, kind in out if v is not na]
    # the bank's own rule results recorded with the application (rules_json: {rule, value, limit, pass})
    rj = app.get("rules_json") or []
    if isinstance(rj, str):
        import json as _json
        try:
            rj = _json.loads(rj)
        except ValueError:
            rj = []
    for k, x in enumerate(rj if isinstance(rj, list) else []):
        if not isinstance(x, dict):
            continue
        v, lim, ok = x.get("value"), x.get("limit"), bool(x.get("pass"))
        num = isinstance(v, (int, float)) and not isinstance(v, bool) and isinstance(lim, (int, float))
        op = ("≥" if (v >= lim) == ok else "≤") if num else ""
        rows.append({"id": f"policy_{k + 1}", "rule": rule_label(str(x.get("rule") or f"policy rule {k + 1}")), "value": v,
                     "value_text": f"{v:g}" if isinstance(v, (int, float)) and not isinstance(v, bool) else str(v),
                     "threshold": (f"{op} {lim:g}" if num else str(lim if lim is not None else "")), "pass": ok,
                     "on_fail": "hard" if str(x.get("severity") or "").lower() in ("hard", "decline") else "exception",
                     "src": source.src(REL, app, "rules_json")})
    # the watch rule only matters when the adverse rule passed
    return [r for r in rows if not (r["id"] == "bureau_watch" and bureau == "adverse")]


_LABELS = {"dscr": "Debt service cover", "pct": "(%)", "12m": "(12 months)", "x": "(x)", "mn": "(SAR million)"}


def rule_label(name: str) -> str:
    """'returned_cheques_12m' -> 'Returned cheques (12 months)'; a sentence passes through."""
    if " " in name:
        return name[:1].upper() + name[1:]
    words = [_LABELS.get(w, w) for w in name.split("_")]
    s = " ".join(words)
    return s[:1].upper() + s[1:]


def doa_levels() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """The lane's authority by amount: Session E's SME template (`doa_by_amount_mn`), else the policy default."""
    try:
        from backend.dealdesk.products import templates
        rows = templates.TEMPLATES["sme"]["doa_by_amount_mn"]
        levels = [{"level": lvl, "max_sar_mn": float(cap)} for cap, lvl in rows if cap is not None]
        if levels:
            return levels, {"domain": "Deal Desk", "relation": "product_template", "key": {"product": "sme", "field": "doa_by_amount_mn"}}
    except Exception:  # noqa: BLE001
        pass
    lv, psrc = policy.value("sme.doa", PRODUCT)
    return list(lv), psrc


def doa(exposure: float, grade: str) -> dict[str, Any]:
    levels, psrc = doa_levels()
    i = next((k for k, lv_ in enumerate(levels) if exposure <= float(lv_["max_sar_mn"]) + 1e-9), None)
    if i is None:
        return {"level": "Credit DoA (full flow)", "in_lane": False, "exposure_sar_mn": exposure, "src": psrc,
                "reason": f"Exposure SAR {exposure:,.2f} million above the lane's highest authority"}
    step = _grade_rank(grade) > _grade_rank(policy.v("sme.max_grade_auto", PRODUCT))
    j = min(len(levels) - 1, i + 1) if step else i
    return {"level": levels[j]["level"], "in_lane": True, "exposure_sar_mn": exposure, "src": psrc,
            "reason": f"Exposure SAR {exposure:,.2f} million up to SAR {float(levels[i]['max_sar_mn']):g} million"
                      + (f"; one level up for grade {grade}" if step and j != i else ""),
            "levels": levels}


def decide(app: dict[str, Any]) -> dict[str, Any]:
    app = norm(app)
    sc = score(app)
    rs = rules(app, sc)
    hard = [r for r in rs if not r["pass"] and r["on_fail"] == "hard"]
    exc = [r for r in rs if not r["pass"] and r["on_fail"] == "exception"]
    amt = _f(app.get("amount_sar_mn") or app.get("amount"))
    exposure = amt + _f(app.get("existing_exposure_sar_mn"))
    auth = doa(exposure, sc["grade"])
    conds = []
    above = float(policy.v("sme.collateral_above_sar_mn", PRODUCT))
    coll = _bool(app.get("collateral_offered"))
    if amt > above and not coll:
        conds.append(f"Security for amounts above SAR {above:g} million: cash or property collateral, prior to limit loading")
    if _grade_rank(sc["grade"]) > _grade_rank(policy.v("sme.max_grade_auto", PRODUCT)):
        conds.append(f"Grade {sc['grade']}: owner's personal guarantee and a 6-month review")
    if _f(app.get("returned_payments_q")) > 0:
        conds.append("Account conduct reviewed by the RM monthly for 6 months (returned payments in the quarter)")
    conds.append("Audited financials within 120 days of the year end; management accounts semi-annually")
    if hard:
        decision, lane = "Decline", "fast_track"
    elif exc or not auth["in_lane"]:
        decision, lane = "Refer to full flow", "full"
    elif len(conds) > 1:
        decision, lane = "Approve with conditions", "fast_track"
    else:
        decision, lane = "Approve", "fast_track"
    reasons = [f"{r['rule']}: {r['value_text']} against {r['threshold']}" for r in hard + exc]
    if not auth["in_lane"]:
        reasons.append(auth["reason"])
    out = {"src": source.src(REL, app), "application_id": app.get("application_id"), "applicant": app.get("applicant_name") or app.get("name"),
           "proposal_id": app.get("proposal_id"), "sector": app.get("sector"), "region": app.get("region"),
           "amount_sar_mn": amt, "tenor_years": _f(app.get("tenor_years"), 1), "product": app.get("product"),
           "existing_exposure_sar_mn": _f(app.get("existing_exposure_sar_mn")), "received_date": app.get("received_date"),
           "rm": app.get("rm"), "programme": app.get("programme"), "years_in_business": app.get("years_in_business"),
           "annual_sales_mn": app.get("annual_sales_mn"),
           "recorded": {"decision": app.get("decision"), "doa_level": app.get("doa_level"), "decided_date": app.get("decided_date")},
           "scorecard": sc, "rules": rs, "doa": auth, "decision": decision, "lane": lane, "conditions": conds if decision.startswith("Approve") else [],
           "exceptions": reasons, "route": None if lane != "full" else {"to": "full_flow", "reasons": reasons,
                                                                           "proposal_id": app.get("proposal_id")}}
    out["paper"] = paper(out)
    out["answer"] = out["paper"]["headline"]
    return out


def _yrs(y: float) -> str:
    return f"{y:g} year" + ("" if y == 1 else "s")


def paper(d: dict[str, Any]) -> dict[str, Any]:
    """The short paper: one page, every line a fact and a number (deterministic, N6)."""
    sc = d["scorecard"]
    passed = sum(1 for r in d["rules"] if r["pass"])
    head = (f"{d['decision']}: {d['applicant']}, SAR {d['amount_sar_mn']:,.2f} million over {_yrs(d['tenor_years'])}; "
            f"{sc['scorecard']['name']} score {sc['score']:.0f}, grade {sc['grade']}" + (f" (PD {sc['pd']:.2%})" if sc["pd"] is not None else "") + "; "
            f"{passed} of {len(d['rules'])} programme rules met; authority {d['doa']['level']}.")
    top = sorted(sc["lines"], key=lambda x: x["points"])
    who = ", ".join(str(x) for x in (d.get("sector"), d.get("region")) if x)
    biz = "; ".join(x for x in (f"{d['years_in_business']} years in business" if d.get("years_in_business") is not None else "",
                                f"annual sales SAR {_f(d['annual_sales_mn']):,.1f} million" if d.get("annual_sales_mn") is not None else "") if x)
    score_line = (f"Scorecard: {sc['score']:.0f} points, grade {sc['grade']}" + (f", grade PD {sc['pd']:.2%}" if sc["pd"] is not None else "") + ". "
                  + ("Weakest characteristics: " + "; ".join(f"{x['label']} {x['value']} ({x['points']:.0f} pts)" for x in top[:2])
                     + ". Strongest: " + "; ".join(f"{x['label']} {x['value']} ({x['points']:.0f} pts)" for x in top[-2:][::-1]) + "."
                     if top else f"As recorded with the application ({sc['scorecard']['id']} v{sc['scorecard']['version']})."))
    lines = [
        f"Applicant: {d['applicant']}" + (f" ({who})" if who else "") + f"; application {d['application_id']}"
        + (f" ({d['programme']})" if d.get("programme") else "")
        + (f" received {d['received_date']}" if d.get("received_date") else "") + (f"; RM {d['rm']}" if d.get("rm") else "")
        + (f"; {biz}" if biz else "") + ".",
        f"Request: {str(d.get('product') or 'facility').replace('_', ' ')} SAR {d['amount_sar_mn']:,.2f} million, tenor {_yrs(d['tenor_years'])}; "
        f"existing exposure SAR {d['existing_exposure_sar_mn']:,.2f} million; total SAR {d['doa']['exposure_sar_mn']:,.2f} million.",
        score_line,
        (f"Programme rules: all {len(d['rules'])} met." if passed == len(d["rules"]) else
         f"Programme rules: {passed} of {len(d['rules'])} met; not met: "
         + "; ".join(f"{r['rule']} ({r['value_text']} against {r['threshold']})" for r in d["rules"] if not r["pass"]) + "."),
        f"Authority: {d['doa']['level']} ({d['doa']['reason']}).",
    ]
    if d["exceptions"]:
        lines.append(("Declined: " if d["decision"] == "Decline" else "Exceptions, routed to the full Deal Desk flow: ")
                     + "; ".join(d["exceptions"]) + ".")
    if d["conditions"]:
        lines.append("Conditions: " + " ".join(f"({i}) {c}." for i, c in enumerate(d["conditions"], 1)))
    return {"headline": head, "lines": lines}


# ------------------------------------------------------------------ the lane


def applications() -> list[dict[str, Any]]:
    return source.read(REL)


def lane(status: str = "") -> dict[str, Any]:
    out = [decide(a) for a in applications()]
    if status:
        out = [d for d in out if d["decision"] == status or d["lane"] == status]
    return {"applications": [{k: d[k] for k in ("application_id", "applicant", "sector", "amount_sar_mn", "decision", "lane", "answer")}
                             | {"grade": d["scorecard"]["grade"], "score": d["scorecard"]["score"], "doa_level": d["doa"]["level"],
                                "exceptions": len(d["exceptions"])} for d in out],
            "counts": _counts(out)}


def _counts(ds: list[dict[str, Any]]) -> dict[str, Any]:
    by = {k: sum(1 for d in ds if d["decision"] == k) for k in DECISIONS}
    return {"total": len(ds), "by_decision": by, "in_lane": sum(1 for d in ds if d["lane"] == "fast_track"),
            "to_full_flow": by["Refer to full flow"], "ready_to_approve": by["Approve"] + by["Approve with conditions"]}


def counts() -> dict[str, Any]:
    c = _counts([decide(a) for a in applications()])
    return {"card": "SME fast track", "count": c["total"], **c,
            "sub": f"{c['ready_to_approve']} ready to approve · {c['to_full_flow']} to the full flow · {c['by_decision']['Decline']} declined",
            "src": {"domain": "Deal Desk", "relation": REL, "derived": "SME fast-track decision per application"}}


def get(application_id: str) -> dict[str, Any] | None:
    a = next((x for x in applications() if str(x.get("application_id") or x.get("proposal_id")) == str(application_id)), None)
    return None if a is None else decide(a)


#: the lane's decision in the contract's vocabulary (dd_sme_application.decision)
CONTRACT_DECISION = {"Approve": "approve", "Approve with conditions": "approve", "Refer to full flow": "refer", "Decline": "decline"}


def publish_decision(d: dict[str, Any], by: str = "") -> dict[str, Any]:
    """Write the decision back to the application's row (upsert of the whole row, so E's facts are kept)."""
    pid = d.get("proposal_id") or d.get("application_id")
    row = next((dict(x) for x in source.read(REL, proposal_id=pid)), None)
    if row is None:
        return {"published": False, "relation": REL, "reason": "application not found"}
    for k in ("rel_version", "published_at", "application_id", "applicant_name", "amount_sar_mn", "tenor_years", "received_date"):
        row.pop(k, None)
    row.update({"decision": CONTRACT_DECISION[d["decision"]], "doa_level": d["doa"]["level"],
                "conditions_text": " | ".join(d["conditions"]) or None, "exception_flag": int(d["lane"] == "full"),
                "rules_failed": sum(1 for r in d["rules"] if not r["pass"]),
                "decided_date": dt.date.today().isoformat()})
    if isinstance(row.get("rules_json"), (list, dict)):
        row["rules_json"] = json.dumps(row["rules_json"])
    return source.publish(REL, [row], actor=f"P:{by}" if by else "P")
