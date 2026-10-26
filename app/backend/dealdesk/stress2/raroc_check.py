"""O4: the stressed RAROC, checked. Under a downgrade the stressed RAROC must re-price PD, capital, ECL and the
pricing ratchet at the stressed grade, not keep the origination values.

What the R11 engine run already does (verified here, every row): PD is the model re-scored at the stressed grade
(`pd_model.obligor_pd(p, notches)`), the economic capital uses the stressed grade's TTC PD, and the yearly EL uses
the stressed PD. What it did not do, and why RAROC barely moved (DD-01: 28.2% -> 27.7% at four notches):

  capital   the standardised risk weight is read from the obligor's *external* rating, which the notch shock left
            at origination; with capital basis "max" the regulatory charge binds, so capital did not move. Here the
            external rating moves by the same notches (an unrated obligor stays unrated: SA 100%, and the table
            says so).
  ECL       the engine charges the yearly EL at the stressed PD (its PV is the lifetime ECL). In Stage 2 the lifetime
            ECL is provisioned up front: the same losses earlier (the year-1 provision build is reported); in Stage 3
            the loss is EAD x LGD now and replaces the EL stream (after zakat), so no loss is counted twice.
  ratchet   a rating-linked margin ratchet in the terms (`margin_ratchet_bps_per_notch`, capped by
            `margin_ratchet_cap_bps`) steps the margin up with the downgrade; with no ratchet the margin stays and
            the market margin for the stressed bucket is shown for the renewal.

Each step is a full engine run (or the closed-form provision charge), so the attribution adds up exactly:
R11 value + capital + ECL + ratchet = checked value.
"""
from __future__ import annotations

import copy
from typing import Any

from backend.dealdesk import engine, params, pd_model
from backend.dealdesk.seed import GRADES, bucket
from backend.dealdesk import stress_lab as sl


def _ext_after(ext: str | None, n: int) -> str | None:
    if not ext or ext not in GRADES or n <= 0:
        return ext
    return GRADES[min(len(GRADES) - 1, GRADES.index(ext) + n)]


def _ratchet(t: dict[str, Any], raw: dict[str, Any] | None = None) -> tuple[float, float | None]:
    src = {**t, **{k: v for k, v in (raw or {}).items() if k.startswith("margin_ratchet")}}
    step = float(src.get("margin_ratchet_bps_per_notch") or 0.0)
    cap = src.get("margin_ratchet_cap_bps")
    return step, (None if cap is None else float(cap))


def _market_margin(rating: str) -> list[float] | None:
    mb = params.rows("market_bounds")["by_bucket"]
    b = bucket(rating)
    return mb.get(b, {}).get("margin_bps")


def check(lab: "sl.Lab", r: dict[str, Any], total: int, stage: int, a: dict[str, Any], ecl: float) -> dict[str, Any]:
    """The checked stressed RAROC for one scenario row (r: resolved shocks; total: scenario + implied notches;
    a: the R11 engine run of the row; ecl: the row's stage ECL)."""
    p, t, kw = lab.p, lab.t, lab.kw
    m = a["metrics"]
    rating0 = p["obligor"]["internal_rating"]
    g = sl.grade_after(rating0, total)
    pd_direct = pd_model.obligor_pd(p, total) if total else None
    verified = {
        "rating": a["pd"]["rating_used"] == g if a.get("pd") else None,
        "pd_12m_model": None if pd_direct is None else abs(pd_direct["pd_12m"] - (a["pd"]["model_pd_12m"] if a.get("pd") else 0)) < 1e-12,
        "ttc_pd": None if not a.get("pd") else abs(float(a["pd"]["ttc_pd"]) - pd_model.master_pd(g)) < 1e-12,
    }
    r11 = m["lifetime_raroc"]
    h = float(m["hurdle"])
    steps: list[dict[str, Any]] = [{"step": "PD, economic capital and EL at the stressed grade (engine)", "raroc": r11,
                                    "delta": None, "basis": f"rating {g}; PD 12m {m['pd_12m'] * 100:.2f}%; TTC PD "
                                    f"{(a['pd']['ttc_pd'] if a.get('pd') else 0) * 100:.2f}%"}]
    cur = a
    # 1. capital: the external rating moves with the downgrade (SA risk weight)
    ext0 = p["obligor"].get("external_rating")
    ext1 = _ext_after(ext0, total)
    cap_note = "No downgrade: capital unchanged."
    if total and ext0 and ext1 != ext0:
        q, tt, sh = sl.stressed_case(p, t, r)
        q["obligor"] = {**q["obligor"], "external_rating": ext1}
        sh["notches"] = total
        try:
            cur = engine.analyse(q, tt, shocks=sh, validate=False, **kw)
        except StopIteration:
            cur = a
        rw0 = params.rows("sa_risk_weights")["corporate_by_external"].get(ext0)
        rw1 = params.rows("sa_risk_weights")["corporate_by_external"].get(ext1)
        cap_note = (f"External rating {ext0} -> {ext1}: SA risk weight {rw0 * 100:.0f}% -> {rw1 * 100:.0f}%; "
                    f"capital year 1 {m['capital_y1']:.2f} -> {cur['metrics']['capital_y1']:.2f} m")
    elif total:
        cap_note = ("Unrated for the standardised approach: the SA risk weight stays at the unrated corporate weight; "
                    "economic capital moves with the TTC PD (in the engine run)") if not ext0 else "External rating unchanged."
    r_cap = cur["metrics"]["lifetime_raroc"]
    steps.append({"step": "Capital at the stressed rating (SA risk weight)", "raroc": r_cap, "delta": _d(r_cap, r11), "basis": cap_note})
    # 2. pricing ratchet
    step_bps, cap_bps = _ratchet(t, getattr(lab, "raw_terms", None))
    m_now = float(t["margin_bps"])
    rat_note = "No rating-linked ratchet in this structure: the margin stays."
    mk = _market_margin(g)
    if total and step_bps > 0:
        add = step_bps * total if cap_bps is None else min(cap_bps, step_bps * total)
        q, tt, sh = sl.stressed_case(p, {**t, "margin_bps": m_now + add}, r)
        if ext1 != ext0:
            q["obligor"] = {**q["obligor"], "external_rating": ext1}
        sh["notches"] = total
        cur = engine.analyse(q, tt, shocks=sh, validate=False, **kw)
        rat_note = f"Ratchet {step_bps:.0f} bps a notch x {total}: margin {m_now:.0f} -> {m_now + add:.0f} bps"
    elif total and mk:
        rat_note += f" At renewal the market margin for {bucket(g)} names is {mk[0]:.0f}-{mk[1]:.0f} bps (today {m_now:.0f})."
    r_rat = cur["metrics"]["lifetime_raroc"]
    steps.append({"step": "Pricing ratchet", "raroc": r_rat, "delta": _d(r_rat, r_cap), "basis": rat_note})
    # 3. ECL at the stressed stage. The engine's credit cost is the yearly EL at the stressed PD; its PV is the lifetime
    # ECL. In Stage 2 the lifetime ECL is provisioned up front: the same losses, earlier (the year-1 provision build is
    # reported); in Stage 3 the loss is EAD x LGD now. The stage ECL replaces the EL stream (after zakat), so no loss
    # is counted twice.
    cm = cur["metrics"]
    zakat = float(params.rows("returns")["zakat_rate"])
    el_pv = float(cm["el_lifetime_pv"])
    build = max(0.0, float(ecl) - float(cm["el_y1"])) if stage >= 2 else 0.0
    adj = (el_pv - float(ecl)) * (1 - zakat) if stage >= 2 else 0.0
    pv_rap, pv_cap = float(cm["pv_rap"]), float(cm["pv_capital"])
    r_ecl = (pv_rap + adj) / pv_cap if pv_cap > 0 else None
    sva = float(cm["sva"]) + adj
    steps.append({"step": "ECL at the stressed stage", "raroc": r_ecl, "delta": _d(r_ecl, r_rat),
                  "basis": ("Stage 1: the 12-month EL at the stressed PD is the credit cost (engine)." if stage < 2 else
                            f"Stage 2: lifetime ECL {float(ecl):.3f} m provisioned up front (year-1 provision build {build:.3f} m over the "
                            f"12-month EL); it is the PV of the yearly EL the engine charges, so RAROC moves by timing only"
                            if stage == 2 else
                            f"Stage 3: loss EAD x LGD {float(ecl):.3f} m now, replacing the yearly EL (PV {el_pv:.3f} m), after zakat")})
    return {"r11_raroc": r11, "raroc": r_ecl, "sva": sva, "hurdle": h, "clears_hurdle": bool(sva >= -1e-9), "rating": g,
            "external_rating": ext1, "capital_y1": float(cm["capital_y1"]), "rwa_y1": float(cm["rwa_y1"]),
            "margin_bps": float(cur["terms"]["margin_bps"]), "provision_build_y1": build, "steps": steps,
            "verified": verified, "market_margin_bps": mk,
            "attribution_ok": r_ecl is None or r11 is None or abs(sum(s["delta"] or 0.0 for s in steps[1:]) - (r_ecl - r11)) < 1e-9}


def _d(a: Any, b: Any) -> float | None:
    if a is None or b is None:
        return None
    return float(a) - float(b)


def notch_ladder(lab: "sl.Lab", up_to: int = 4) -> list[dict[str, Any]]:
    """The rating family applied directly, checked: 0..up_to notches (the test and the O4 table)."""
    out = []
    for n in range(up_to + 1):
        r = copy.deepcopy(sl.EMPTY)
        r["notches"] = n
        a = lab.run_engine(r, n) if n else lab.base
        st = lab.mirror.ratios(r)
        stage, _why = sl.stage_for(lab.rating0, n, a["metrics"]["dscr_post"])
        ecl, _ = lab._ecl(a["metrics"], stage)
        c = check(lab, r, n, stage, a, ecl)
        out.append({"notches": n, "rating": c["rating"], "pd_12m": a["metrics"]["pd_12m"], "stage": stage, "ecl": ecl,
                    "r11_raroc": c["r11_raroc"], "raroc": c["raroc"], "capital_y1": c["capital_y1"], "dscr": st["dscr"]})
    return out
