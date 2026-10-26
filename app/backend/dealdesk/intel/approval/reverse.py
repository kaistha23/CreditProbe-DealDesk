"""Reverse solver for declines (R14 backlog #4, R13 Session IA).

For a deal that fails (the RAROC hurdle, a hard limit, a policy (soft) limit, or the stress tier rule), the smallest
change in amount, tenor, collateral, pricing or covenants that makes it approvable, as an RM-ready counter-offer.

Method
  1. The ask is run through the engine (engine.analyse) and the stress ladder (stress2.ladder.run, not published).
     Failures: SVA < 0 (RAROC below the hurdle), each hard breach, each soft (policy) breach, and a stress verdict
     of "Restructure" (something breaks already at mild severity, R12 tier rule).
  2. One lever family at a time is freed, every other lever held at the ask, and the Optimise engine
     (optimizer.Problem.closest) returns the closest-to-ask structure that clears the hurdle and every limit.
     Families: amount (down to 5% of the ask), tenor and profile, security (collateral, cash margin, guarantee),
     pricing (margin and fees inside the market bounds), covenants (package). A sixth run frees every lever
     ("Optimise, all levers").
  3. Candidates are ranked by the optimiser's own distance from the ask (the weighted change it minimises), and
     the best ones are re-run through the stress ladder; the first one whose verdict is not "Restructure" is the
     counter-offer. If none passes the ladder, the amount is stepped down (90%, 80%, 70% of the candidate) and
     re-priced, and the result says what the stress still breaks.
Every figure is an engine run on the deal's Data Domains row (lineage: dd_deal.proposal_json + parameter versions).
"""
from __future__ import annotations

import time
from typing import Any

from backend.dealdesk import engine, optimizer
from backend.dealdesk.intel.approval import common as C

FAMILIES = {
    "amount": ("Lower amount", ["amount"]),
    "tenor": ("Shorter tenor or faster repayment", ["tenor_years", "grace_years", "amortisation", "balloon_pct"]),
    "security": ("More security", ["collateral_ids", "cash_margin_pct", "guarantee_id", "guarantee_coverage_pct"]),
    "pricing": ("Higher price", ["margin_bps", "upfront_fee_bps", "commitment_fee_bps", "commission_bps"]),
    "covenants": ("Tighter covenants", ["covenant_package"]),
    "amount_price": ("Lower amount and higher price", ["amount", "margin_bps", "upfront_fee_bps", "commitment_fee_bps", "commission_bps"]),
}
ALL_VARS = sorted({k for _, ks in FAMILIES.values() for k in ks} | {"structure", "funded_share_pct"})
LABELS = {"amount": "Amount", "tenor_years": "Tenor", "grace_years": "Grace", "amortisation": "Repayment profile",
          "balloon_pct": "Balloon", "margin_bps": "Margin", "upfront_fee_bps": "Upfront fee", "commitment_fee_bps": "Commitment fee",
          "commission_bps": "Commission", "cash_margin_pct": "Cash margin", "collateral_ids": "Collateral",
          "guarantee_id": "Guarantee", "guarantee_coverage_pct": "Guarantee cover", "covenant_package": "Covenant package",
          "structure": "Structure", "funded_share_pct": "Funded share"}
STRESS_BUDGET = 5
TEST_WORDS = {"dscr": "DSCR", "debt_ebitda": "Debt/EBITDA", "covenants": "covenants", "limits": "limits", "raroc": "RAROC", "rating": "rating",
              "stage": "Stage 2", "ltv": "LTV"}


def _tests(bs: list[str]) -> str:
    return ", ".join(TEST_WORDS.get(b, b.replace("_", " ")) for b in bs)
TERMLESS = {"min_rating": "The minimum rating for new money is a rating test: no change in amount, tenor, security, price or covenants cures it. "
                          "It needs an exception at the escalation level or a decline."}


def _stress(p: dict[str, Any], terms: dict[str, Any] | None) -> dict[str, Any]:
    from backend.dealdesk.stress2 import ladder
    try:
        r = ladder.run(p, terms, publish=False, reverse=False, include_chain=False)
    except Exception as e:  # noqa: BLE001 - the ladder is optional evidence; say so rather than fail the solve
        return {"verdict": None, "tier": None, "worst_breaking_severity": None, "error": str(e)[:200], "breaking": []}
    v = r["verdict"]
    return {"verdict": v["verdict"], "worst_breaking_severity": v.get("worst_breaking_severity"), "tier": (r.get("tier") or {}).get("tier"),
            "why": v.get("why"), "breaking": [{"scenario": x.get("label") or x.get("id"), "severity": x.get("severity"), "breaks": x["breaks"]}
                                             for x in r["rows"] if x.get("breaks")][:6]}


def _item(p: dict[str, Any], cid: str) -> dict[str, Any] | None:
    return next((c for c in p["security"]["collateral"] if c["collateral_id"] == cid), None)


def _guarantor(p: dict[str, Any], gid: str | None) -> str:
    if not gid:
        return "none"
    g = next((g for g in p["security"]["guarantees"] if g["guarantee_id"] == gid), None)
    if g:
        return f"{g['guarantor']} ({g['type']}, {g['guarantor_rating']})"
    from backend.dealdesk import params
    c = params.rows("credit_protection")["guarantee_catalogue"].get(gid)
    return c["label"] if c else gid


def describe(p: dict[str, Any], field: str, ask: Any, value: Any, ccy: str) -> str:
    """One RM-ready line per change."""
    lab = LABELS.get(field, field)
    if field == "amount":
        return f"{lab} {ccy} {float(ask):,.1f}m → {ccy} {float(value):,.1f}m ({float(value) / float(ask) - 1:+.0%})"
    if field.endswith("_bps"):
        return f"{lab} {float(ask):,.0f} bps → {float(value):,.0f} bps ({float(value) - float(ask):+,.0f} bps)"
    if field.endswith("_pct"):
        return f"{lab} {float(ask or 0):,.0f}% → {float(value or 0):,.0f}%"
    if field in ("tenor_years", "grace_years"):
        return f"{lab} {ask} → {value} years"
    if field == "collateral_ids":
        add = [c for c in value if c not in (ask or [])]
        drop = [c for c in (ask or []) if c not in value]
        parts = []
        for c in add:
            it = _item(p, c) or {}
            parts.append(f"pledge {c} ({str(it.get('type', '')).replace('_', ' ')}, {it.get('currency', 'SAR')} {float(it.get('value') or 0):,.1f}m)")
        for c in drop:
            parts.append(f"release {c}")
        return f"{lab}: " + "; ".join(parts)
    if field == "guarantee_id":
        return f"{lab}: {_guarantor(p, ask)} → {_guarantor(p, value)}"
    return f"{lab} {ask} → {value}"


def _failures(pid: str, a: dict[str, Any], st: dict[str, Any]) -> list[dict[str, Any]]:
    m = a["metrics"]
    out = []
    if not m["clears_hurdle"]:
        out.append({"kind": "hurdle", "label": "RAROC below the hurdle",
                    "text": f"Lifetime RAROC {C.pct(m['lifetime_raroc'])} against a hurdle of {C.pct(m['hurdle'])} (SVA {_z(m['sva']):,.2f}m).",
                    "value": C.efig(pid, m["lifetime_raroc"], "share", "Lifetime RAROC"), "limit": C.efig(pid, m["hurdle"], "share", "Hurdle")})
    for c in C.hard_breaches(a):
        out.append({"kind": "limit", "name": c["name"], "label": c["label"], "text": f"{c['label']}: {_v(c['value'])} against {_v(c['limit'])} {c['unit']} ({c['basis']}).",
                    "value": C.efig(pid, c["value"], c["unit"], c["label"]), "limit": C.efig(pid, c["limit"], c["unit"], "Limit")})
    for c in C.soft_breaches(a):
        out.append({"kind": "policy", "name": c["name"], "label": c["label"], "text": f"{c['label']} (policy): {c['value']} against {c['limit']} {c['unit']}.",
                    "value": C.efig(pid, c["value"], c["unit"], c["label"]) if isinstance(c["value"], (int, float)) else None})
    if st.get("verdict") == "Restructure":
        out.append({"kind": "stress", "label": "Stress tier: Restructure",
                    "text": f"Stress ladder verdict Restructure: {st.get('why') or 'something breaks at mild severity'}.",
                    "value": None})
    return out


def _fixed_for(ask: dict[str, Any], free: list[str]) -> dict[str, Any]:
    return {k: ask[k] for k in ALL_VARS if k not in free and k in ask}


def _candidate(p: dict[str, Any], label: str, family: str, fixed: dict[str, Any], bounds: dict[str, Any] | None,
               ask: dict[str, Any], fx: float, seconds: float) -> dict[str, Any] | None:
    try:
        prob = optimizer.Problem(p, fixed=fixed, bounds=bounds)
        r = prob.closest(max_seconds=seconds)
    except engine.TermsError:
        return None
    if r is None:
        return None
    s = optimizer._summary(r, ask, label, fx)
    s["family"] = family
    return s


def solve(pid: str, max_seconds: float = 25.0) -> dict[str, Any]:
    t0 = time.time()
    pid = C.resolve_id(pid)
    p = C.proposal(pid)
    a = C.analysis(pid)
    ask = a["terms"]
    ccy = ask["currency"]
    fx = engine.fx(ccy)
    st0 = _stress(p, None)
    fails = _failures(pid, a, st0)
    rec = C.latest_stress(pid)
    base = {"proposal_id": pid, "obligor": p["obligor"]["name"], "currency": ccy,
            "ask": {"terms": ask, "lifetime_raroc": C.efig(pid, a["metrics"]["lifetime_raroc"], "share", "Lifetime RAROC"),
                    "hurdle": C.efig(pid, a["metrics"]["hurdle"], "share", "Hurdle"),
                    "sva": C.efig(pid, a["metrics"]["sva"], f"{ccy} m", "SVA"),
                    "approval": a["approval"], "stress": st0},
            "recorded_stress": {"run_id": rec["run_id"], "verdict": rec["verdict"], "worst_breaking_severity": rec["worst_breaking_severity"],
                                "source": {"domain": "deal_desk", "relation": "dd_stress_result", "key": {"proposal_id": pid, "run_id": rec["run_id"]}}
                                if rec["run_id"] else None},
            "failures": fails, "method": __doc__.split("Method", 1)[1].split("Every figure")[0].strip()}
    if not fails:
        base.update({"approvable_as_asked": True, "candidates": [], "counter_offer": None,
                     "headline": f"{p['obligor']['name']} is approvable as asked: lifetime RAROC {C.pct(a['metrics']['lifetime_raroc'])} "
                                 f"against {C.pct(a['metrics']['hurdle'])}, no limit breached, stress verdict {st0.get('verdict') or 'not run'}.",
                     "seconds": round(time.time() - t0, 2)})
        return base

    cands: list[dict[str, Any]] = []
    per = max(1.5, min(4.0, max_seconds / 8))
    for fam, (label, free) in FAMILIES.items():
        bounds = {"amount": [0.05 * float(ask["amount"]), float(ask["amount"])]} if "amount" in free else None
        c = _candidate(p, label, fam, _fixed_for(ask, free), bounds, ask, fx, per)
        if c is not None and c["changes"]:
            cands.append(c)
    allc = _candidate(p, "Optimise, all levers", "all", {}, {"amount": [0.05 * float(ask["amount"]), float(ask["amount"])]},
                      ask, fx, per * 1.5)
    if allc is not None and allc["changes"]:
        cands.append(allc)
    cands.sort(key=lambda c: c["distance"])
    uniq: dict[str, dict[str, Any]] = {}
    for c in cands:  # the same structure reached by several families: keep it once, name every family
        sig = repr(sorted((k, str(v)) for k, v in c["terms"].items()))
        if sig in uniq:
            uniq[sig].setdefault("also", []).append(c["label"])
        else:
            uniq[sig] = c
    cands = list(uniq.values())
    # stress verification, in distance order
    chosen = None
    checked = 0
    for c in cands:
        if checked >= STRESS_BUDGET or time.time() - t0 > max_seconds:
            break
        c["stress"] = _stress(p, c["terms"])
        checked += 1
        if c["stress"].get("verdict") not in ("Restructure",):
            chosen = c
            break
    note = None
    if chosen is None and cands:
        # step the amount down on the closest candidate and re-price, until the ladder stops saying Restructure
        best = cands[0]
        last = None
        for f in (0.85, 0.7, 0.5, 0.3):
            if time.time() - t0 > max_seconds + 15:
                break
            amt = float(best["terms"]["amount"]) * f
            fixed = _fixed_for(best["terms"], FAMILIES["pricing"][1])
            fixed["amount"] = amt
            c = _candidate(p, f"Lower amount ({f:.0%} of the closest fix), re-priced", "amount+pricing", fixed,
                           {"amount": [amt, amt]}, ask, fx, per)
            if c is None:
                continue
            c["stress"] = _stress(p, c["terms"])
            last = (f, c)
            if c["stress"].get("verdict") != "Restructure":
                chosen = c
                cands.append(c)
                break
        if chosen is None:
            chosen = best
            brk = (last[1] if last else best).get("stress") or {}
            note = ("No structure found clears the stress tier rule: the closest fix still breaks at mild severity "
                    f"({'; '.join(b['scenario'] + ': ' + _tests(b['breaks']) for b in (best.get('stress') or {}).get('breaking', [])[:3])})"
                    + (f", and so does {last[0]:.0%} of that amount re-priced ({'; '.join(b['scenario'] for b in brk.get('breaking', [])[:3])})" if last else "")
                    + ". The offer clears the hurdle and every limit; committee would still see the stress verdict Restructure, "
                      "so the paper must carry the mitigation for the breaking tests above.")
    out_c = []
    for c in cands:
        out_c.append(_public(pid, p, c, ccy))
    blockers = [TERMLESS[f["name"]] for f in fails if f.get("name") in TERMLESS]
    base.update({"approvable_as_asked": False, "candidates": out_c, "termless_blockers": blockers,
                 "counter_offer": _offer(pid, p, chosen, ccy, a, note) if chosen else None,
                 "unsolved": None if cands else _unsolved(p),
                 "seconds": round(time.time() - t0, 2)})
    base["headline"] = (base["counter_offer"]["headline"] if base["counter_offer"] else
                        f"No single-lever or combined change inside the market bounds makes {p['obligor']['name']} approvable."
                        + (" " + " ".join(blockers) if blockers else ""))
    return base


def _public(pid: str, p: dict[str, Any], c: dict[str, Any], ccy: str) -> dict[str, Any]:
    m = c["metrics"]
    src = {"terms": c["terms"]}
    return {"label": c["label"], "family": c["family"], "also_reached_by": c.get("also", []), "distance": round(float(c["distance"]), 4),
            "changes": [{**ch, "text": describe(p, ch["field"], ch["ask"], ch["value"], ccy),
                         "source": C.deal_source(pid, "optimizer.Problem.closest", src["terms"])} for ch in c["changes"]],
            "lifetime_raroc": C.efig(pid, m["lifetime_raroc"], "share", "Lifetime RAROC", "optimizer.Problem.closest", src["terms"]),
            "sva": C.efig(pid, m["sva"], f"{ccy} m", "SVA", "optimizer.Problem.closest", src["terms"]),
            "rwa_y1": C.efig(pid, m["rwa_y1"], "SAR m", "RWA year 1", "optimizer.Problem.closest", src["terms"]),
            "el_y1": C.efig(pid, m["el_y1"], "SAR m", "EL year 1", "optimizer.Problem.closest", src["terms"]),
            "approval": c["approval"], "stress": c.get("stress"), "terms": c["terms"]}


def _offer(pid: str, p: dict[str, Any], c: dict[str, Any], ccy: str, a: dict[str, Any], note: str | None) -> dict[str, Any]:
    pub = _public(pid, p, c, ccy)
    m = c["metrics"]
    lines = [ch["text"] for ch in pub["changes"]]
    st = c.get("stress") or {}
    name = p["obligor"]["name"]
    text = (f"Counter-offer to {name}: " + "; ".join(lines) + ". Everything else as asked. "
            f"At these terms the lifetime RAROC is {C.pct(m['lifetime_raroc'])} against a hurdle of {C.pct(m['hurdle'])} "
            f"(SVA {ccy} {_z(m['sva']):,.2f}m), no limit is breached, the approval sits with {c['approval']['level']}"
            + (f", and the stress verdict is {st['verdict']}" if st.get("verdict") else "") + ".")
    head = (f"Smallest change that makes {name} approvable: " + "; ".join(lines) +
            f" (RAROC {C.pct(a['metrics']['lifetime_raroc'])} → {C.pct(m['lifetime_raroc'])}).")
    return {**pub, "headline": head, "rm_text": text, "note": note,
            "client_asks": lines, "why_this_one": "Closest to the ask by the optimiser's weighted distance among the structures that "
                                                  "clear the hurdle, every limit and (where checked) the stress tier rule."}


def _v(x: Any) -> str:
    return f"{x:,.2f}" if isinstance(x, (int, float)) and not isinstance(x, bool) else str(x)


def _z(x: float) -> float:
    return 0.0 if abs(x) < 0.005 else x


def _unsolved(p: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        return optimizer._relaxation(p, {"fixed": None, "bounds": None, "weights": None, "allow_soft": False,
                                         "el_view": "economic", "capital_basis": None})
    except Exception:  # noqa: BLE001
        return []
