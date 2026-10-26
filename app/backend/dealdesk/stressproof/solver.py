"""Stress-proofing (K23 (4)-(6)): the reverse solver for the smallest change set that survives a target severity.

The user picks the target (default moderate; severe is monitored, not designed for, else the deal is over-structured).
Starting from a structure of the set, the solver applies levers in the order of what they ask of the client, cheapest
first, and keeps only the ones the failing tests need:

  1  amount to capacity          the funded amount cut to the capacity engine's figure when the ask is above it
  2  covenant reset               a covenant that breaks under the target is reset to the worst stressed value with 10%
                                  headroom, never past the policy limit, stepping back to today's level over the tenor
  3  amount (to survive)          when leverage, DSCR, Stage or a hard limit still breaks, the largest amount that
                                  survives (bisection on the Stress Lab ladder itself)
  4  cash margin                  when LTV breaks: cash margin raised until it does not
  5  receivables assignment       on a working-capital line with receivables pledged: assignment of the receivables
                                  (lowers LGD, so less price is needed)
  6  pricing and margin ratchet   if the result is below the hurdle: the upfront fee to breakeven (up to 100 bps), else
                                  margin / commission; plus a rating-linked margin ratchet (25 bps a notch) for downgrades
  7  guarantee                    only a guarantor rated better than the obligor (Session E's substitution rule)
  8  cash sweep                   a term loan with a bullet or balloon that breaks DSCR gets a 50% excess-cash sweep as a
                                  condition; its effect is not modelled in the DSCR (stated)

Every evaluation is the R12 Stress Lab ladder on the candidate (never a copy); the final structure is run in full
(all severities), added to the set as "Stress-proofed (<target>)" and the matrix re-runs on it and the starting one.
"""
from __future__ import annotations

import copy
import hashlib
import math
import json
from typing import Any

from backend.dealdesk import engine, params
from backend.dealdesk.seed import GRADES
from backend.dealdesk.stress2 import catalogue as cat
from backend.dealdesk.stressproof import adapters as AD
from backend.dealdesk.stressproof import interpret
from backend.dealdesk.stressproof import matrix as MX
from backend.dealdesk.stressproof import structures as ST

TARGETS = ("mild", "moderate", "severe")
HEADROOM = 0.10
MIN_AMOUNT_SHARE = 0.10
RATCHET_BPS = 25.0
UPFRONT_MAX = 100.0


class ProofError(ValueError):
    pass


def _ids(pid: str, target: str) -> list[str]:
    cut = TARGETS.index(target)
    return [s["scenario_id"] for s in cat.scenarios(pid)
            if (s.get("severity") in TARGETS and TARGETS.index(s["severity"]) <= cut) or (s.get("severity") not in TARGETS and cut == 2)]


def _cand(label: str, t: dict[str, Any], cov: list[dict[str, Any]] | None) -> dict[str, Any]:
    return {"key": "candidate", "label": label, "role": "stress_proofed", "terms": t, "covenants": cov}


def _fails(p: dict[str, Any], t: dict[str, Any], cov: list[dict[str, Any]] | None, ids: list[str]) -> tuple[set[str], dict[str, Any]]:
    out = MX.ladder_for(p, _cand("candidate", t, cov), scenario_ids=ids, publish=False)
    tests: set[str] = set()
    for r in out["rows"]:
        if r["applicable"]:
            tests |= set(MX.survival_breaks(r))
    return tests, out


def _covenant_kind(typ: str) -> str:
    t = typ.lower()
    if t.startswith("dscr"):
        return "dscr"
    if "ebitda" in t and "debt" in t:
        return "leverage"
    if "interest" in t:
        return "interest"
    return ""


def _reset_covenants(p: dict[str, Any], cov: list[dict[str, Any]], out: dict[str, Any], a: dict[str, Any], tenor: int,
                     notes: list[str]) -> list[dict[str, Any]]:
    """New covenant thresholds with 10% headroom over the worst stressed value, inside the policy limits."""
    de_lim = next((float(c["limit"]) for c in a["constraints"] if c["name"] == "debt_ebitda"), None)
    dscr_lim = next((float(c["limit"]) for c in a["constraints"] if c["name"] == "dscr"), 1.0)
    changes = []
    for c in cov:
        kind = _covenant_kind(c["type"])
        vals = [x.get("value") for r in out["rows"] if r["applicable"] for x in r.get("covenants") or []
                if x["type"] == c["type"] and isinstance(x.get("value"), (int, float))]
        vals = [float(v) for v in vals if v == v and abs(v) != float("inf")]
        if not vals or not kind:
            continue
        old = float(c["threshold"])
        if kind == "leverage":
            worst = max(vals)
            if worst <= old:
                continue
            new = round(min(worst * (1 + HEADROOM), de_lim if de_lim else worst * (1 + HEADROOM)) * 4) / 4
            if new <= old:
                notes.append(f"{c['type']} covenant is already at the {de_lim:.2f}x policy limit: a reset above it needs a policy exception "
                             f"(worst stressed {worst:.2f}x)" if de_lim else f"{c['type']} covenant cannot be reset")
                continue
        else:
            worst = min(vals)
            if worst >= old:
                continue
            floor = dscr_lim if kind == "dscr" else 1.5
            new = max(floor, round(worst / (1 + HEADROOM) * 20) / 20)
            if new >= old:
                continue
        step = (f"; steps back to {old:.2f}x by year {tenor}" if tenor > 1 else "; back to today's level at renewal")
        changes.append({"lever": "covenant_reset", "field": c["type"], "from": old, "to": new,
                        "text": f"{c['type']} covenant {old:.2f}x → {new:.2f}x (worst stressed {worst:.2f}x, {int(HEADROOM * 100)}% headroom{step})",
                        "client": "", "cost": "covenant protection loosened"})
        c["threshold"] = new
        c["step_down_to"] = old
    return changes


def _amount_bisect(p: dict[str, Any], t: dict[str, Any], cov, ids: list[str], hard: set[str]) -> tuple[float | None, set[str]]:
    """The largest amount at which none of `hard` breaks (None when even the floor breaks)."""
    hi = float(t["amount"])
    lo = hi * MIN_AMOUNT_SHARE
    tests, _ = _fails(p, {**t, "amount": lo}, cov, ids)
    left = tests & hard
    hard = hard - left          # what the amount cannot cure (the obligor's own position) is reported, the rest is solved
    if not hard:
        return None, left
    for _ in range(7):
        mid = (lo + hi) / 2
        tests, _ = _fails(p, {**t, "amount": mid}, cov, ids)
        if tests & hard:
            hi = mid
        else:
            lo = mid
    return lo, left


def _round_amount(x: float) -> float:
    step = 5.0 if x >= 50 else 1.0 if x >= 5 else 0.5
    return max(step, (x // step) * step)


def _better_guarantee(p: dict[str, Any], t: dict[str, Any]) -> dict[str, Any] | None:
    r0 = p["obligor"]["internal_rating"]
    if r0 not in GRADES or t.get("guarantee_id"):
        return None
    best = None
    for g in p["security"].get("guarantees") or []:
        gr = g.get("guarantor_rating")
        if gr in GRADES and GRADES.index(gr) < GRADES.index(r0) and (best is None or GRADES.index(gr) < GRADES.index(best["guarantor_rating"])):
            best = g
    return best


def _price(p: dict[str, Any], t: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Reprice to the hurdle: upfront fee first (up to 100 bps), then margin (funded) or commission (unfunded)."""
    q = dict(t)
    ch = []
    a = engine.analyse(p, q)
    if a["metrics"]["clears_hurdle"]:
        return q, ch
    be = engine.breakeven(p, q, "upfront_fee_bps")
    if be.get("value") is not None and be["value"] <= UPFRONT_MAX:
        v = round(float(be["value"]) + 0.5)
        ch.append({"lever": "pricing", "field": "upfront_fee_bps", "from": q["upfront_fee_bps"], "to": v,
                   "text": f"Upfront fee {q['upfront_fee_bps']:.0f} → {v:.0f} bps (breakeven to the hurdle)", "client": f"upfront fee {v:.0f} bps",
                   "cost": "paid by the client"})
        q["upfront_fee_bps"] = v
        return q, ch
    funded = q["facility_type"] not in engine.UNFUNDED and float(q["funded_share_pct"]) > 0
    lever = "margin_bps" if funded else "commission_bps"
    be = engine.breakeven(p, q, lever)
    if be.get("value") is not None:
        v = round(float(be["value"]) + 0.5)
        ch.append({"lever": "pricing", "field": lever, "from": q[lever], "to": v,
                   "text": f"{'Margin' if funded else 'Commission'} {q[lever]:.0f} → {v:.0f} bps (breakeven to the hurdle)",
                   "client": f"{'margin' if funded else 'commission'} {v:.0f} bps", "cost": "paid by the client"})
        q[lever] = v
    return q, ch


def _ratchet(t: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rmax = float(params.rows("pricing_behaviour").get("margin_ratchet_max_bps_per_notch", 0) or 0)
    if rmax <= 0 or float(t.get("margin_ratchet_bps_per_notch") or 0) > 0:
        return t, []
    v = min(RATCHET_BPS, rmax)
    return {**t, "margin_ratchet_bps_per_notch": v}, [{"lever": "margin_ratchet", "field": "margin_ratchet_bps_per_notch", "from": 0, "to": v,
        "text": f"Margin ratchet +{v:.0f} bps per notch of downgrade", "client": f"pays +{v:.0f} bps a notch only if downgraded",
        "cost": "none unless downgraded"}]


def solve(pid: str, from_key: str | None = None, target: str = "moderate") -> dict[str, Any]:
    if target not in TARGETS:
        raise ProofError("target severity must be mild, moderate or severe")
    s = ST.structure_set(pid)
    by = {r["key"]: r for r in s["rows"]}
    key = from_key or s["selected"]
    if key not in by:
        raise KeyError(key)
    start = by[key]
    p = ST.deal(pid)
    t = engine.merge_terms(p, start["terms"])
    cov = copy.deepcopy(start["covenants"] or p["security"].get("covenants") or [])
    ids = _ids(pid, target)
    changes: list[dict[str, Any]] = []
    uncured: list[str] = []
    a0 = engine.analyse(ST.with_covenants(p, cov), t)

    # 1 amount to capacity
    capy = AD.capacity(p, a0)
    share = 0.0 if t["facility_type"] in engine.UNFUNDED else float(t["funded_share_pct"]) / 100.0
    if not capy["passes"] and (share > 0 or capy.get("recommended_amount_sar_mn")):
        rec_amt = capy.get("recommended_amount_sar_mn")
        new = (float(rec_amt) if rec_amt is not None else capy["capacity_sar_mn"] / share) / engine.fx(t["currency"])
        if new < float(t["amount"]) * MIN_AMOUNT_SHARE:
            uncured.append(f"capacity {capy['method'].lower()} SAR {capy['capacity_sar_mn']:,.1f}m is below {int(MIN_AMOUNT_SHARE * 100)}% of the ask")
        else:
            new = math.floor(new * 10) / 10
            changes.append({"lever": "amount_to_capacity", "field": "amount", "from": t["amount"], "to": new,
                            "text": f"Amount {t['amount']:,.1f} → {new:,.1f} (to capacity: {capy['method'].lower()} SAR {capy['capacity_sar_mn']:,.1f}m)",
                            "client": f"limit {new:,.0f} instead of {t['amount']:,.0f}", "cost": "smaller deal"})
            t["amount"] = new

    # 2-4 survive the target
    tests, out = _fails(p, t, cov, ids)
    first_before = MX.first_break({"cells": [MX.cell(out["rows"], sv) for sv in MX.SEVERITIES]})
    cov_done = False
    for _ in range(4):
        if not tests:
            break
        if "covenants" in tests and not cov_done:
            cov_done = True
            ch = _reset_covenants(p, cov, out, engine.analyse(ST.with_covenants(p, cov), t), int(t["tenor_years"]), uncured)
            if ch:
                changes += ch
                tests, out = _fails(p, t, cov, ids)
                continue
        hard = tests & {"debt_ebitda", "limits", "dscr", "stage", "covenants"}
        if hard:
            amt, left = _amount_bisect(p, t, cov, ids, hard)
            if left:
                uncured.append("even at " + f"{int(MIN_AMOUNT_SHARE * 100)}% of the amount " + ", ".join(sorted(MX.TEST_LABEL[x] for x in left))
                               + " still break: the obligor's own position breaks under the target, not this deal")
            if amt is None:
                break
            new = _round_amount(amt)
            if new < float(t["amount"]) - 1e-9:
                changes.append({"lever": "amount", "field": "amount", "from": t["amount"], "to": new,
                                "text": f"Amount {t['amount']:,.0f} → {new:,.0f} (largest amount that survives {target})",
                                "client": f"limit {new:,.0f} instead of {t['amount']:,.0f}", "cost": "smaller deal"})
                t["amount"] = new
                if t["facility_type"] == "term_loan" and t["amortisation"] in ("bullet", "balloon") and "dscr" in hard:
                    changes.append({"lever": "cash_sweep", "field": "condition", "from": None, "to": "50% excess cash sweep",
                                    "text": "Cash sweep: 50% of excess cash flow prepays the balloon (condition; effect not modelled in the DSCR)",
                                    "client": "50% excess cash sweep", "cost": "none"})
            tests, out = _fails(p, t, cov, ids)
            if left:
                tests -= left
                if not tests:
                    break
            continue
        if "ltv" in tests:
            cm = min(100.0, float(t["cash_margin_pct"]) + 10.0)
            changes.append({"lever": "cash_margin", "field": "cash_margin_pct", "from": t["cash_margin_pct"], "to": cm,
                            "text": f"Cash margin {t['cash_margin_pct']:.0f}% → {cm:.0f}% (LTV under {target})", "client": f"cash margin {cm:.0f}%",
                            "cost": "client cash blocked"})
            t["cash_margin_pct"] = cm
            tests, out = _fails(p, t, cov, ids)
            continue
        break
    final_tests, _ = _fails(p, t, cov, ids)
    for x in sorted(final_tests):
        if not any(MX.TEST_LABEL[x] in u for u in uncured):
            uncured.append(f"{MX.TEST_LABEL[x]} still breaks under {target}")

    # 5 receivables assignment on a working-capital line with receivables pledged
    items = {c["collateral_id"]: c for c in p["security"]["collateral"]}
    if (t["facility_type"] in AD.WC_PRODUCTS and float(t.get("receivables_assignment_pct") or 0) == 0
            and any(items.get(c, {}).get("type") == "receivables" for c in t.get("collateral_ids") or [])):
        before = engine.analyse(p, t)["metrics"]["sva"]
        tt = {**t, "receivables_assignment_pct": 100}
        try:
            after = engine.analyse(p, tt)["metrics"]["sva"]
        except engine.TermsError:
            after = before
        if after > before + 1e-6:
            changes.append({"lever": "receivables_assignment", "field": "receivables_assignment_pct", "from": 0, "to": 100,
                            "text": "Assignment of the pledged receivables (100%, notified to the debtors)", "client": "assign receivables",
                            "cost": "operational: notices to debtors"})
            t = tt

    # 6 guarantee, only from a better-rated guarantor; 7 pricing and ratchet
    g = _better_guarantee(p, t)
    if g is not None and not engine.analyse(p, t)["metrics"]["clears_hurdle"]:
        tt = {**t, "guarantee_id": g["guarantee_id"], "guarantee_coverage_pct": float(g.get("coverage_pct") or 100)}
        try:
            if engine.analyse(p, tt)["metrics"]["sva"] > engine.analyse(p, t)["metrics"]["sva"]:
                changes.append({"lever": "guarantee", "field": "guarantee_id", "from": t.get("guarantee_id"), "to": g["guarantee_id"],
                                "text": f"Guarantee of {g['guarantor']} ({g['guarantor_rating']}, better than the obligor's {p['obligor']['internal_rating']})",
                                "client": f"guarantee from {g['guarantor']}", "cost": "none to the bank"})
                t = tt
        except engine.TermsError:
            pass
    t, ch = _price(p, t)
    changes += ch
    if ch:
        t, ch2 = _ratchet(t)
        changes += ch2
    return {"pid": pid, "start": start, "terms": t, "covenants": cov if any("step_down_to" in c for c in cov) else None,
            "changes": changes, "uncured": uncured, "target": target, "first_before": first_before}


def proof(pid: str, from_key: str | None = None, target: str = "moderate", by: str = "", publish: bool = True) -> dict[str, Any]:
    """POST /proposals/{pid}/stress-proof: solve, add the structure to the set, re-run the matrix on it and the start."""
    sol = solve(pid, from_key, target)
    start = sol["start"]
    n = 1 + sum(1 for r in ST.saved(pid) if r["role"] == "stress_proofed" and r["label"].startswith(f"Stress-proofed ({target})"))
    label = f"Stress-proofed ({target})" + (f" {n}" if n > 1 else "")
    cov = [{k: v for k, v in c.items() if k in ("type", "threshold")} for c in sol["covenants"]] if sol["covenants"] else None
    if sol["changes"]:
        added = ST.add(pid, label, "stress_proofed", sol["terms"], cov, origin=f"Stress-proofed from {start['label']} to {target}", by=by)
        new_key = added["added"]
        m = MX.run(pid, keys=[start["key"], new_key], force=[start["key"]])
        a_row = next(r for r in added["rows"] if r["key"] == new_key)
    else:
        # nothing to change: no copy of the start is added to the set; the result says why
        added = ST.structure_set(pid)
        new_key = start["key"]
        label = start["label"]
        m = MX.run(pid, keys=[start["key"]], force=[start["key"]])
        a_row = start
    after = next(c for c in m["structures"] if c["key"] == new_key)
    before = next(c for c in m["structures"] if c["key"] == start["key"])
    survives = after["stressed"] and TARGETS.index(target) <= MX.SEV_RANK.get(after["survives_up_to"], -1)
    text = interpret.proofed(before, after, sol["changes"], target, start, a_row, survives, sol["uncured"] or
                             ([] if survives else [MX.first_break(after)]))
    pr = {"proof_id": "SP-" + hashlib.sha1(json.dumps([pid, start["key"], sol["terms"], cov, target], sort_keys=True, default=str).encode()).hexdigest()[:12],
          "proposal_id": pid, "from_structure_key": start["key"], "new_structure_key": new_key, "target_severity": target,
          "changes_json": sol["changes"], "survives_flag": int(bool(survives)), "first_break_before": sol["first_before"],
          "raroc_before_pct": start["raroc"] * 100, "raroc_after_pct": a_row["raroc"] * 100, "sva_before_mn": start["sva"], "sva_after_mn": a_row["sva"],
          "cost_text": text["cost"], "interpretation": " ".join(text["lines"]), "regime_label": AD.regime()["label"],
          "sensitivity_version": str(m.get("sensitivity_version") or ""), "run_by": by or "deal desk", "run_at": ST.now()}
    if publish:
        from backend.dealdesk.data import store
        store.publish("dd_stress_proof", [pr], mode="upsert", actor=by or "deal desk")
    return {"proposal_id": pid, "proof": pr, "new_key": new_key, "label": label, "survives": bool(survives), "changes": sol["changes"],
            "uncured": sol["uncured"], "interpretation": text, "matrix": m, "structure_set": ST.structure_set(pid),
            "added": bool(sol["changes"]),
            "plain_words": [
                f"This finds the smallest change that lets the deal survive a {target} shock.",
                (f"It changes: {text['changes']}." if sol["changes"] else
                 ("No change was needed." if survives else f"No change to the structure helps: the borrower's own finances break under a {target} shock.")),
                f"Cost: {text['cost']}.",
                ("The new structure survives; severe shocks are watched through monitoring, not designed for." if survives
                 else "It still breaks: this cannot be fixed by structure alone, so accept and monitor, or decline."),
            ]}
