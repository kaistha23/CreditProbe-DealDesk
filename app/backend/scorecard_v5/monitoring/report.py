"""The MMSG validation report (R16 M8): a full validation of one scorecard in the CBUAE Model Management Standards and
Guidance structure, as a house-style Word document. Deterministic (N4): every sentence is written from the validation
result, the monitoring relations, the inventory, the findings register and the maker-checker record.

Sections: 1 Executive summary and conclusion; 2 Scope; 3 Data; 4 Conceptual soundness; 5 Discrimination; 6 Calibration;
7 Stability; 8 Benchmarking; 9 Overrides; 10 Use test; 11 Findings with severity and remediation; 12 Conclusion and
maker-checker; 13 Monitoring plan; Appendix A thresholds; Appendix B MMSG references.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

import numpy as np

from backend.house_style import Meta, docx as hd
from backend.scorecard_v5 import engine
from backend.scorecard_v5.monitoring import compute, front
from backend.scorecard_v5.report_docx import VERDICT_WORD, fmtv, figure_png

CONCLUSIONS = {"fit": "Fit for use", "conditions": "Fit for use with conditions", "not_fit": "Not fit for use"}
SEVERITY = {"red": "High", "amber": "Medium"}
GROUP_CRITERION = {"discrimination": "discrimination", "calibration": "calibration", "stability": "stability", "variables": "conceptual",
                   "overrides": "overrides"}


def _tests(res: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {x["id"]: x for s in res["sections"] for x in s["tests"]}


def proposed_conclusion(res: dict[str, Any], dive: dict[str, Any]) -> dict[str, Any]:
    """The rule-based conclusion the maker starts from (MMS 3.7.8: a fully articulated judgement)."""
    t = _tests(res)
    st = lambda k: t.get(k, {}).get("status", "na")  # noqa: E731
    oe = t.get("oe_ratio", {}).get("value")
    crit = {c["criterion"]: c["status"] for c in dive["criteria"]}
    reasons = []
    if st("gini") == "red":
        reasons.append("ranking power (Gini) is below its red limit")
        concl = "not_fit"
    elif st("oe_ratio") == "red" and (st("psi") == "red" or (oe is not None and not 0.5 <= float(oe) <= 2.0)):
        reasons.append(f"the PDs miss the observed default rate ({float(oe):.2f}×)" + (" and the population has moved (PSI red)" if st("psi") == "red" else ""))
        concl = "not_fit"
    else:
        reds = [x["label"] for x in t.values() if x["status"] == "red"]
        if crit.get("usage") == "red":
            reds.append("use outside the approved scope")
        if reds:
            reasons.append("red: " + "; ".join(reds[:4]))
            concl = "conditions"
        else:
            concl = "fit"
            reasons.append("no test is red")
    return {"conclusion": concl, "label": CONCLUSIONS[concl], "reasons": reasons}


def findings_from(validation_id: str, sid: str, res: dict[str, Any], on: dt.date) -> list[dict[str, Any]]:
    """New register findings from a validation's red and amber tests (owner from the inventory, due date by severity)."""
    inv = front.inventory()[sid]
    days = compute.POLICY["finding_due_days"]
    out = []
    for k, f in enumerate(engine.findings(res), 1):
        sev = SEVERITY[f["status"]]
        crit = GROUP_CRITERION.get(f["group"], f["group"])
        owner = inv["override_owner"] if crit == "overrides" else inv["model_owner"]
        out.append({"finding_id": f"F-{validation_id.split('-')[-1].upper()}-{k:02d}", "scorecard_id": sid, "source_ref": validation_id, "criterion": crit,
                    "severity": sev, "title": f["label"], "text": f["text"], "remediation": f["action"], "owner": owner,
                    "raised_on": on.isoformat(), "due_on": (on + dt.timedelta(days=days[sev])).isoformat(), "status": "open", "origin": "validation"})
    return out


def challenger(sid: str, plan: dict[str, Any]) -> dict[str, Any] | None:
    """Benchmark: the strongest single characteristic (highest development IV) ranked on its own, on the monitoring sample."""
    d = engine.domain(sid)
    sp = d.spec
    v = max(sp["variables"], key=lambda x: x["iv"])
    f = d.frame
    mon = f[(f.period >= plan["monitoring"][0]) & (f.period <= plan["monitoring"][1]) & f.matured]
    woe = np.asarray([b["woe"] for b in v["bins"]], dtype=float)[mon[f"bin_{v['name']}"].to_numpy()]
    auc = engine._auc(mon.y12.to_numpy(dtype=float), woe)
    if np.isnan(auc):
        return None
    if auc < 0.5:
        auc = 1 - auc
    return {"variable": v["label"], "gini": 2 * auc - 1, "n": int(len(mon))}


def build(v: dict[str, Any], *, generated_by: str = "", conclusion: dict[str, Any] | None = None, prior: dict[str, Any] | None = None,
          on: dt.date | None = None, store=None) -> bytes:
    on = on or front.today()
    res = v["result"]
    sc = res["scorecard"]
    sid = sc["scorecard_id"]
    plan = res["plan"]
    smp = res["sample"]
    s = res["summary"]
    t = _tests(res)
    dive = front.deep_dive(sid, on, store)
    inv = dive["inventory"]
    prop = proposed_conclusion(res, dive)
    con = conclusion or {}
    state = con.get("state") or "not proposed"
    final = CONCLUSIONS.get(con.get("conclusion", ""), "") if state == "approved" else ""
    meta = Meta(title=f"{sc['name']} v{sc['version']}: MMSG validation", book=sc["book"], period=plan["as_of"],
                subject=f"{inv['tier']} · {sc['segment']} {sc['type']} scorecard", generated_by=generated_by, reference=v["validation_id"])
    doc = hd.document(meta, kind="Model validation report (CBUAE MMSG)", subtitle=f"{sc['name']} v{sc['version']} · as of {plan['as_of']}",
                      details=[("Model", f"{sid} · {sc['name']} v{sc['version']}"), ("Model risk tier", f"{inv['tier']}: {inv['tier_reason']}"),
                               ("Model owner", inv["model_owner"]), ("Validator", inv["validator"]),
                               ("Validation type", "Full independent validation" if all(plan["tests"].values()) or sum(plan["tests"].values()) >= 4 else "Targeted validation"),
                               ("Conclusion", final or f"{prop['label']} (proposed; {state})")])

    # 1 ------------------------------------------------------------------
    hd.heading(doc, "1. Executive summary and conclusion")
    hd.key_figures(doc, [("Conclusion", final or f"{prop['label']} (proposed)"), ("Monitoring health", dive["overall"].upper()),
                         ("Tests green / amber / red", f"{s['counts']['green']} / {s['counts']['amber']} / {s['counts']['red']}"),
                         ("Gini", fmtv(t.get("gini", {}).get("value"), "pct")), ("Observed / expected", fmtv(t.get("oe_ratio", {}).get("value"), "num")),
                         ("Score PSI", fmtv(t.get("psi", {}).get("value"), "num4"))], per_row=3)
    hd.para(doc, f"The {sc['name']} (version {sc['version']}, {inv['tier']}) was validated as of {plan['as_of']} on {smp['monitoring']['n']:,} monitoring observations "
                 f"with {smp['monitoring']['defaults']:,} defaults ({smp['monitoring']['from']} to {smp['monitoring']['to']}), against its development sample "
                 f"({smp['development']['from']} to {smp['development']['to']}: {smp['development']['n']:,} observations, {smp['development']['defaults']:,} defaults).")
    for key in ("gini", "oe_ratio", "psi"):
        if key in t:
            hd.para(doc, f"**{t[key]['label']}** ({VERDICT_WORD[t[key]['status']]}): {t[key]['comment']}")
    hd.para(doc, f"**Proposed conclusion: {prop['label']}**, because " + "; ".join(prop["reasons"]) + ".")
    hd.para(doc, "**Root cause.** " + " ".join(dive["root_cause"][:2]))
    hd.para(doc, "**Recommended decisions (MMS 4.3.3).**", size=10)
    hd.bullets(doc, [f"**{a['title']}** ({a['severity']}; owner {a['owner']}; by {a['due']}). {a['why']}" for a in dive["actions"]], numbered=True)

    # 2 ------------------------------------------------------------------
    hd.heading(doc, "2. Scope")
    hd.table(doc, ["Item", "Detail"], [
        ["Model", f"{sc['name']} v{sc['version']} ({sid}), {sc['type']} scorecard, {sc['segment']} segment"],
        ["Purpose and intended use", inv["intended_use"]], ["Approved scope", f"{inv['segment_col'].replace('_', ' ')}: {inv['approved_segments'].replace(' | ', ', ')}"],
        ["Model risk tier", f"{inv['tier']}: {inv['tier_reason']} (MMS 3.1.5, 4.4.5)"],
        ["Approval", f"{inv['approved_by']} on {inv['approved_on']}"],
        ["Last full independent validation", f"{inv['last_validation_ref']} on {inv['last_full_validation']} ({CONCLUSIONS.get(inv['last_validation_conclusion'], inv['last_validation_conclusion'])})"],
        ["Validation cycle", f"every {inv['validation_cycle_months']} months for {inv['tier']} (bank policy under MMS 3.7.1)"],
        ["Owners", f"model: {inv['model_owner']}; data: {inv['data_owner']}; overrides: {inv['override_owner']}"],
        ["Validator", f"{inv['validator']}, independent of development and use"],
        ["Tests in scope", ", ".join(engine.GROUP_TITLES[g] for g, on_ in plan["tests"].items() if on_)],
    ], right_from=99)

    # 3 ------------------------------------------------------------------
    hd.heading(doc, "3. Data")
    hd.table(doc, ["Sample", "Window", "Observations", "Defaults"], [
        ["Development", f"{smp['development']['from']} to {smp['development']['to']}", f"{smp['development']['n']:,}", f"{smp['development']['defaults']:,}"],
        ["Monitoring (outcome matured)", f"{smp['monitoring']['from']} to {smp['monitoring']['to']}", f"{smp['monitoring']['n']:,}", f"{smp['monitoring']['defaults']:,}"],
        ["As-of (population only)", plan["as_of"], f"{smp['as_of']['n']:,}", "—"]], right_from=2)
    dq = {c["criterion"]: c for c in dive["criteria"]}["data_quality"]
    hd.para(doc, f"Data quality is {dq['status'].upper()}: {dq['sentence']} Outcomes are final up to {smp['last_matured']}; later periods enter the stability tests only.")
    chars = [c for c in dive["characteristics"]]
    hd.table(doc, ["Characteristic", "In model", "Missing", "Outside development ranges", "CSI"],
             [[c["label"], "yes" if c["in_model"] else "candidate", f"{c['missing_pct']:.1%}", "—" if c["unseen_pct"] is None else f"{c['unseen_pct']:.1%}",
               "—" if c["csi"] is None else f"{c['csi']:.3f}"] for c in chars[:16]], right_from=2, size=8)
    hd.note(doc, f"Characteristics at {dive['characteristics_period']} against development; source scorecard_monitoring.sc_monitor_characteristic.")

    # 4 ------------------------------------------------------------------
    hd.heading(doc, "4. Conceptual soundness")
    hd.para(doc, f"The scorecard is a points scorecard on weight-of-evidence bins with {len(sc['variables'])} characteristics: "
                 + ", ".join(f"{x['label']} (IV {x['iv']:.2f})" for x in sc["variables"]) + ". Each characteristic's bin order is tested for monotonicity, "
                 "its information value is re-measured on the monitoring sample, and the set is tested for correlation and variance inflation.")
    var = next((sec for sec in res["sections"] if sec["id"] == "variables"), None)
    if var:
        _tests_table(doc, var)
    else:
        hd.para(doc, "The variables tests were not in the plan of this validation.")

    # 5-7, 9 ---------------------------------------------------------------
    no = 5
    for gid, title in (("discrimination", "Discrimination"), ("calibration", "Calibration"), ("stability", "Stability")):
        hd.heading(doc, f"{no}. {title}")
        sec = next((x for x in res["sections"] if x["id"] == gid), None)
        if sec:
            _tests_table(doc, sec)
            for ch in sec["charts"][:2]:
                hd.figure(doc, figure_png(ch["figure"]), width_cm=14.5, caption=ch["title"])
        else:
            hd.para(doc, "Not in the plan of this validation.")
        c = {x["criterion"]: x for x in dive["criteria"]}[gid]
        hd.para(doc, f"**Monitoring since the last validation:** {c['sentence']}" + (f" Also: {'; '.join(c['also'])}." if c["also"] else ""))
        if gid == "discrimination" and dive["segments"]["rows"]:
            hd.table(doc, [dive["segments"]["by"].replace("_", " ").title(), "Observations", "Defaults", "Gini", "O / E", "In scope"],
                     [[r["segment"], f"{r.get('n') or 0:,}", f"{r.get('defaults') or 0:,}", fmtv(r.get("gini"), "pct"), fmtv(r.get("oe"), "num"),
                       "yes" if r["in_scope"] else "NO"] for r in dive["segments"]["rows"]], right_from=1, size=8)
        no += 1
    # 8 ------------------------------------------------------------------
    hd.heading(doc, "8. Benchmarking")
    rows = [["Development sample", fmtv(dive["inventory"]["dev_gini"], "pct"), "the scorecard on the sample it was built on"]]
    if "gini" in t:
        rows.append(["This validation (monitoring sample)", fmtv(t["gini"]["value"], "pct"), t["gini"]["comment"]])
    if prior:
        pg = _tests(prior["result"]).get("gini")
        if pg:
            rows.append([f"Previous CreditProbe validation ({prior['as_of']})", fmtv(pg["value"], "pct"), pg["comment"]])
    ch = challenger(sid, plan)
    if ch:
        rows.append([f"Challenger: {ch['variable']} alone", fmtv(ch["gini"], "pct"), f"the strongest single characteristic ranked on its own ({ch['n']:,} observations)"])
    hd.table(doc, ["Benchmark", "Gini", "Basis"], rows, right_from=99)
    if ch and "gini" in t:
        lift = float(t["gini"]["value"]) - ch["gini"]
        hd.para(doc, f"The scorecard adds {lift * 100:.1f} Gini points over its strongest single characteristic" +
                (": the multivariate design earns its complexity." if lift > 0.05 else ": the lift is small; the redevelopment should test a simpler design."))
    # 9 ------------------------------------------------------------------
    hd.heading(doc, "9. Overrides")
    sec = next((x for x in res["sections"] if x["id"] == "overrides"), None)
    if sec:
        _tests_table(doc, sec)
    oc = {x["criterion"]: x for x in dive["criteria"]}["overrides"]
    hd.para(doc, oc["sentence"])
    if dive["override_reasons"]:
        hd.table(doc, ["Reason (latest period)", "Share of overrides", "Observed default rate", "Expected"],
                 [[r["reason"], f"{r['share']:.1%}", fmtv(r["observed"], "pct2"), fmtv(r["expected"], "pct2")] for r in dive["override_reasons"]], right_from=1)
    # 10 -----------------------------------------------------------------
    hd.heading(doc, "10. Use test")
    u = {x["criterion"]: x for x in dive["criteria"]}["usage"]
    hd.para(doc, f"Intended use: {inv['intended_use']} {u['sentence']} (MMS 3.5.1-3.5.2, 3.6.2.)")
    hd.para(doc, f"The grade is used in decisions: {('overrides are recorded and tested (section 9)' if sc['has_overrides'] else 'the book is re-graded every month and the grade drives collections and limits')}.")
    # 11 -----------------------------------------------------------------
    hd.heading(doc, "11. Findings with severity and remediation")
    new = findings_from(v["validation_id"], sid, res, on)
    if new:
        hd.para(doc, "**From this validation**", size=10)
        hd.table(doc, ["Ref", "Severity", "Finding", "Remediation", "Owner", "Due"],
                 [[f["finding_id"], f["severity"], f["title"], f["remediation"], f["owner"].split(" (")[0], f["due_on"]] for f in new],
                 widths=[2.4, 1.5, 4.2, 5.4, 2.6, 2.0], right_from=99, size=7.5)
    old = [f for f in dive["findings"] if f["status"] != "closed" and f.get("source_ref") != v["validation_id"]]
    if old:
        hd.para(doc, "**Open from earlier validations and monitoring**", size=10)
        hd.table(doc, ["Ref", "Severity", "Finding", "Owner", "Due", "Status"],
                 [[f["finding_id"], f["severity"], f["title"], f["owner"].split(" (")[0], f["due_on"], ("OVERDUE " if f["overdue"] else "") + f["status"].replace("_", " ")]
                  for f in old], right_from=99, size=8)
    # 12 -----------------------------------------------------------------
    hd.heading(doc, "12. Conclusion and maker-checker")
    hd.para(doc, f"**Proposed by the rules:** {prop['label']} (" + "; ".join(prop["reasons"]) + ").")
    hd.table(doc, ["Step", "Record"], [
        ["State", {"approved": "Approved by the checker", "proposed": "Proposed, waiting for the checker", "returned": "Returned by the checker"}.get(state, "Not yet proposed")],
        ["Conclusion", CONCLUSIONS.get(con.get("conclusion", ""), "—")], ["Maker", f"{con.get('maker') or '—'} {('on ' + con['maker_at'][:10]) if con.get('maker_at') else ''}".strip()],
        ["Maker's note", con.get("note") or "—"], ["Checker", f"{con.get('checker') or '—'} {('on ' + con['checker_at'][:10]) if con.get('checker_at') else ''}".strip()],
        ["Checker's note", con.get("checker_note") or "—"]], right_from=99)
    hd.para(doc, "Validator: ______________________   Head of Model Validation (checker): ______________________   Date: ____________")
    hd.para(doc, "Model Oversight Committee decision: ________________________________________________   Reference: ____________")
    # 13 -----------------------------------------------------------------
    hd.heading(doc, "13. Monitoring plan")
    sch = dive["schedule"] or {}
    hd.para(doc, f"Monitoring runs {sch.get('frequency', inv['monitoring_frequency'])} (last {sch.get('last_run', '—')}, next {sch.get('next_run', '—')}); results go to "
                 f"{sch.get('report_to', 'the Model Oversight Committee')} and red breaches on {inv['tier']} models go to Noor's brief the same day (MMS 3.6.4, 3.6.6).")
    hd.table(doc, ["Criterion", "Today", "Lead metric", "Value", "Since", "Owner"],
             [[front.TITLES[c["criterion"]], VERDICT_WORD.get(c["status"], c["status"]), c["label"], c["display"], c["since"] or "—", c["owner"].split(" (")[0]]
              for c in dive["criteria"]], right_from=99, size=8)
    hd.heading(doc, "Appendix A. Thresholds applied")
    hd.table(doc, ["Test", "Verdict rule"], [[x["label"], x["text"]] for x in res["thresholds"].values()] +
             [[x["label"], engine.threshold_text(x) if x["kind"] in ("low", "high") else ""] for x in compute.POLICY["limits"].values()], right_from=99, size=8)
    hd.heading(doc, "Appendix B. MMSG references")
    hd.table(doc, ["Area", "Reference"], [[k.replace("_", " ").title(), v_] for k, v_ in compute.POLICY["references"].items()], right_from=99, size=8)
    hd.note(doc, compute.POLICY["note"])
    return hd.to_bytes(doc)


def _tests_table(doc, sec: dict[str, Any]) -> None:
    rows = [[x["label"], fmtv(x["value"], x["format"]) if x["format"] != "text" else x["value"], x["threshold"], VERDICT_WORD[x["status"]], x["comment"]] for x in sec["tests"]]
    hd.table(doc, ["Test", "Value", "Threshold", "Verdict", "Reading"], rows, widths=[3.6, 2.0, 3.6, 1.6, 6.2], right_from=99, size=8)
