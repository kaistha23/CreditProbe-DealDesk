"""R14 E (K18, K21, K22 #2, K24): the one economics engine.

* RAROC and SVA are computed once per structure by `engine.analyse` (lifetime: PV over the tenor at the hurdle) and
  read here with their BASIS LABEL. Tiles of every type show the lifetime basis (`SVA_BASIS`), with the one-year figure
  (year-one risk-adjusted profit less the hurdle charge on year-one capital) in the (i). The pipeline test and every
  other reader take `basis` from here, so no screen mixes a lifetime and a one-year SVA without saying so.
* One reporting period (`reporting_period`): the book quarter every deal figure, memo cover and paper states.
* EL and RWA (i): PD, LGD, EAD, the regulatory exposure after CCFs, the risk weight and every credit-risk mitigant
  applied, with a band test (EL rate and RWA density in the band for the rating unless a stated CRM explains it).
* PD and LGD: the model PD beside the master-scale PD for the grade; the guarantor rule (substitution only when the
  guarantor is rated better than the obligor; engine.analyse applies it) stated in the LGD (i).
* RAROC bridge: deal RAROC → relationship RAROC (ancillary income) → with deposits (deposit value), each step in SAR.
"""
from __future__ import annotations

from typing import Any

from backend.dealdesk import paths, pd_model
from backend.dealdesk.economics import deal as D
from backend.v5common.ratings import rank

SVA_BASIS = "lifetime"
BASIS_LABEL = {"lifetime": "lifetime (PV over the tenor at the hurdle)", "one_year": "year one"}
QUARTER_END = {"Q1": "03-31", "Q2": "06-30", "Q3": "09-30", "Q4": "12-31"}


def reporting_period() -> dict[str, Any]:
    """The one reporting period: the book quarter of the Deal Desk data (paths.AS_OF)."""
    q = paths.AS_OF
    y, qq = q[:4], q[4:]
    return {"quarter": q, "as_of": f"{y}-{QUARTER_END.get(qq, '12-31')}", "label": f"{qq} {y} (book as at {y}-{QUARTER_END.get(qq, '12-31')})",
            "source": "backend.dealdesk.paths.AS_OF (Deal Desk book quarter; deal, memo, book and papers)"}


def _pct(x: Any, dp: int = 1) -> str:
    return "n/a" if not isinstance(x, (int, float)) else f"{x * 100:.{dp}f}%"


def _mn(x: Any, dp: int = 1) -> str:
    return "n/a" if not isinstance(x, (int, float)) else f"SAR {x:,.{dp}f}m"


def _rw_label(p: dict[str, Any], rw_obl: float) -> str:
    ob = p["obligor"]
    if ob.get("sovereign"):
        return "sovereign"
    if ob.get("gre"):
        return "government-related entity"
    if ob.get("real_estate_finance"):
        return "income-producing real estate by LTV"
    if ob.get("sme"):
        return "SME corporate"
    if ob.get("external_rating"):
        return f"corporate rated {ob['external_rating']}"
    return "unrated corporate"


def _bands(rating: str) -> dict[str, Any]:
    """The band for the grade: EL rate between PD x LGD floor and PD x unsecured LGD (master-scale PD); RWA density on
    the regulatory exposure equal to the obligor's SA risk weight."""
    from backend.dealdesk import params
    lg = params.rows("lgd")
    ms = pd_model.master_pd(rating)
    return {"pd_master_scale": ms, "el_rate_min": ms * float(lg["floor"]), "el_rate_max": ms * float(lg["unsecured"]["senior"]),
            "lgd_floor": float(lg["floor"]), "lgd_unsecured": float(lg["unsecured"]["senior"])}


def el_rwa(pid: str, a: dict[str, Any]) -> dict[str, Any]:
    p = D.proposal(pid)
    t, m, lgd, cap = a["terms"], a["metrics"], a["lgd"], a["capital"]
    rating = (a.get("pd") or {}).get("rating_used") or p["obligor"]["internal_rating"]
    sch = a["schedule"][0]
    from backend.dealdesk import params
    ccf = params.rows("ccf")
    utype = t["facility_type"] if t["facility_type"] in ("performance_lg", "financial_lg", "trade_lc") else t["unfunded_type"]
    expo_reg = float(cap["by_year"][0]["exposure_sa"])
    rwa = float(m["rwa_y1"])
    rw_obl = float(cap["rw_obligor"])
    ead, pd12, lgd1, el = float(m["ead_y1"]), float(m["pd_12m"]), float(m["lgd_y1"]), float(m["el_y1"])
    g = lgd.get("guarantee") or None
    ins = lgd.get("insurance") or None
    crm: list[dict[str, Any]] = []
    for c in lgd.get("collateral") or []:
        crm.append({"kind": "collateral", "label": f"{c['type'].replace('_', ' ')} {c['collateral_id']}",
                    "effect": f"{_mn(c['value_sar_mn'])} less {c['haircut']:.0%} haircut, discounted {c['recovery_years']:g}y: "
                              f"{_mn(c['recognised_sar_mn'])} recognised in LGD (not eligible for SA risk-weight relief)",
                    "in_lgd": True, "in_rwa": False})
    if lgd.get("cash_margin_sar_mn"):
        crm.append({"kind": "cash_margin", "label": "Cash margin", "effect": f"{_mn(lgd['cash_margin_sar_mn'])} netted from LGD and from the SA exposure",
                    "in_lgd": True, "in_rwa": True})
    if g:
        if g.get("substitution"):
            crm.append({"kind": "guarantee", "label": f"Guarantee {g['guarantee_id']} ({g['guarantor']}, {g['rating']})",
                        "effect": f"{g['coverage']:.0%} covered: PD/LGD substitution applied (guarantor better rated than the obligor)"
                                  + (f"; SA risk weight {g['sa_rw']:.0%}" if g.get("sa_rw") is not None else "; not an eligible SA protection provider"),
                        "in_lgd": True, "in_rwa": g.get("sa_rw") is not None})
        else:
            crm.append({"kind": "guarantee", "label": f"Guarantee {g['guarantee_id']} ({g['guarantor']}, {g['rating']})",
                        "effect": g.get("substitution_rule") or "no PD/LGD substitution", "in_lgd": False, "in_rwa": False})
    if ins:
        crm.append({"kind": "insurance", "label": f"Credit insurance ({ins['insurer_rating']})",
                    "effect": f"{ins['cover']:.0%} covered at the insurer's PD and LGD; SA risk weight {ins['sa_rw']:.0%}", "in_lgd": True, "in_rwa": True})
    crm_rwa = [c for c in crm if c["in_rwa"]]
    crm_lgd = [c for c in crm if c["in_lgd"]]
    b = _bands(rating)
    el_rate = el / ead if ead else None
    dens_expo = rwa / expo_reg if expo_reg else None
    dens_limit = rwa / float(m["amount_sar_mn"]) if m.get("amount_sar_mn") else None
    el_in = el_rate is not None and b["el_rate_min"] * 0.5 <= el_rate <= b["el_rate_max"] * 1.5
    rwa_in = dens_expo is not None and abs(dens_expo - rw_obl) <= 0.02
    el_expl = None if el_in else ("explained by " + "; ".join(c["label"] for c in crm_lgd) if crm_lgd else None)
    rwa_expl = None if rwa_in else ("explained by " + "; ".join(c["label"] for c in crm_rwa) if crm_rwa else None)
    ccf_text = (f"drawn {_mn(sch['drawn_avg'])} + {ccf['undrawn_committed']['regulatory']:.0%} × undrawn {_mn(sch['undrawn_avg'])}"
                + (f" + {ccf[utype]['regulatory']:.0%} × {utype.replace('_', ' ')} {_mn(sch['unfunded_avg'])}" if sch["unfunded_avg"] else ""))
    rwa_text = (f"RWA {_mn(rwa)} = SA exposure {_mn(expo_reg)} ({ccf_text}"
                + (f", less cash {_mn(lgd['cash_margin_sar_mn'])}" if lgd.get("cash_margin_sar_mn") else "") + f") × risk weight {rw_obl:.0%} "
                f"({_rw_label(p, rw_obl)})" + ("; CRM in RWA: " + "; ".join(c["label"] for c in crm_rwa) if crm_rwa else "; no CRM in RWA")
                + f". RWA is {_pct(dens_limit, 0)} of the {_mn(float(m['amount_sar_mn']))} limit because of the credit-conversion factors, "
                  f"not because of a lower risk weight.")
    el_text = (f"EL year one {_mn(el, 2)} = EAD {_mn(ead)} × PD {_pct(pd12, 2)} × LGD {_pct(lgd1)}"
               + (" (uncovered share; covered share at the protection provider)" if (g and g.get("substitution")) or ins else "")
               + f" = {_pct(el_rate, 2)} of EAD. Band for {rating}: {_pct(b['el_rate_min'], 2)}–{_pct(b['el_rate_max'], 2)} "
                 f"(master-scale PD {_pct(b['pd_master_scale'], 2)} × LGD {b['lgd_floor']:.0%}–{b['lgd_unsecured']:.0%}).")
    lgd_text = (f"LGD {_pct(lgd1)} = max({b['lgd_floor']:.0%} floor, (EAD {_mn(ead)} − recognised security "
                f"{_mn(lgd['collateral_recognised_sar_mn'])}) / EAD × unsecured {lgd['unsecured']:.0%} × covenant {lgd['covenant_multiplier']:.2f})"
                + ("; " + "; ".join(f"{c['label']}: {c['effect']}" for c in crm) if crm else ""))
    pdi = a.get("pd") or {}
    pd_text = (f"PD 12m {_pct(pd12, 2)} (model {_pct(pdi.get('model_pd_12m'), 2)}, version {pdi.get('model_version', 'n/a')}) against the "
               f"bank's master scale for {rating}: {_pct(b['pd_master_scale'], 2)}"
               + (f"; covenant overlay ×{pdi['covenant_overlay']['pd_multiplier']:.2f}" if pdi.get("covenant_overlay") else ""))
    return {"el": {"y1": el, "lifetime_pv": float(m["el_lifetime_pv"]), "rate_y1": el_rate, "info": el_text},
            "rwa": {"y1": rwa, "exposure_reg_y1": expo_reg, "risk_weight": rw_obl, "density_exposure": dens_expo, "density_limit": dens_limit,
                    "info": rwa_text},
            "pd": {"pd_12m": pd12, "model_12m": pdi.get("model_pd_12m"), "master_scale_12m": b["pd_master_scale"], "rating": rating, "info": pd_text},
            "lgd": {"y1": lgd1, "unsecured": float(lgd["unsecured"]), "collateral_recognised_sar_mn": float(lgd["collateral_recognised_sar_mn"]),
                    "guarantee_applied": bool(g and g.get("substitution")), "guarantee": g, "info": lgd_text},
            "ead_y1": ead, "crm": crm,
            "bands": {"el_rate": [b["el_rate_min"], b["el_rate_max"]], "rwa_density_exposure": rw_obl,
                      "el_in_band": el_in, "rwa_in_band": rwa_in, "el_explained_by": el_expl, "rwa_explained_by": rwa_expl,
                      "ok": (el_in or bool(el_expl)) and (rwa_in or bool(rwa_expl)),
                      "rule": "EL rate within ½× PD×LGD floor and 1.5× PD×unsecured LGD for the grade; RWA / SA exposure equal to "
                              "the obligor's SA risk weight; outside the band only with a stated CRM"}}


def _deposit_value(pid: str) -> tuple[float, str]:
    try:
        from backend.dealdesk import deposits
        b = deposits.behaviour(pid)
        return float(b.get("deposit_value_sar_mn") or 0.0), str(b.get("source") or "deposits")
    except Exception:  # noqa: BLE001
        return 0.0, "no account data"


def raroc_bridge(pid: str, structure: Any = None, a: dict[str, Any] | None = None) -> dict[str, Any]:
    """Deal RAROC → relationship RAROC (+ ancillary income) → with deposits (+ deposit value), on one capital base
    (PV of the structure's capital at the hurdle), each step with its PV in SAR."""
    pid = D.resolve_id(pid)
    if a is None:
        st = D.structure_terms(pid, structure)
        a = D.analysis(pid, st["terms"])
    m = a["metrics"]
    from backend.dealdesk import params
    zakat = float(params.rows("returns")["zakat_rate"])
    h = float(m["hurdle"])
    T = int(a["terms"]["tenor_years"])
    disc = [(1 + h) ** -(i + 1) for i in range(T)]
    pv_cap = float(m["pv_capital"])
    pv_rap = float(m["pv_rap"])
    pv_anc = sum(d * float(r.get("ancillary") or 0.0) for d, r in zip(disc, a["pnl"]))
    dep, dep_src = _deposit_value(pid)
    pv_dep = dep * (1 - zakat) * sum(disc)
    r1 = pv_rap / pv_cap if pv_cap else None
    r2 = (pv_rap + pv_anc) / pv_cap if pv_cap else None
    r3 = (pv_rap + pv_anc + pv_dep) / pv_cap if pv_cap else None
    steps = [{"step": "Deal", "raroc": r1, "delta_pp": None, "pv_sar_mn": pv_rap,
              "what": "risk-adjusted profit of this structure / its capital (lifetime)"},
             {"step": "+ ancillary income (relationship)", "raroc": r2, "delta_pp": (r2 - r1) * 100 if r1 is not None else None,
              "pv_sar_mn": pv_anc, "what": "cross-sell income in the business case, after realisation and zakat"},
             {"step": "+ deposits", "raroc": r3, "delta_pp": (r3 - r2) * 100 if r2 is not None else None, "pv_sar_mn": pv_dep,
              "what": f"deposit value {_mn(dep, 2)} a year (balances × (FTP credit − profit paid) + flow fees), after zakat ({dep_src})"}]
    return {"steps": steps, "pv_capital_sar_mn": pv_cap, "hurdle": h, "basis": SVA_BASIS,
            "headline": f"Deal {_pct(r1)} → relationship {_pct(r2)} → with deposits {_pct(r3)} (hurdle {_pct(h)})",
            "source": "engine.analyse (pnl, PV at the hurdle) + backend.dealdesk.deposits (deposit value)"}


def economics(pid: str, structure: Any = None) -> dict[str, Any]:
    pid = D.resolve_id(pid)
    st = D.structure_terms(pid, structure)
    a = D.analysis(pid, st["terms"])
    m = a["metrics"]
    h = float(m["hurdle"])
    y1 = a["pnl"][0]
    rap1, cap1 = float(y1["rap"]), float(y1["capital"])
    one_raroc = rap1 / cap1 if cap1 else None
    one_sva = rap1 - h * cap1
    er = el_rwa(pid, a)
    return {"proposal_id": pid, "structure": {"key": st["key"], "label": st["label"]}, "terms": st["terms"],
            "raroc": {"lifetime": m["lifetime_raroc"], "one_year": one_raroc, "hurdle": h, "clears": bool(m["clears_hurdle"]),
                      "relationship": m["relationship_raroc"]},
            "sva": {"lifetime": m["sva"], "one_year": one_sva, "relationship_lifetime": m["relationship_sva"]},
            "basis": {"raroc": SVA_BASIS, "sva": SVA_BASIS, "label": BASIS_LABEL[SVA_BASIS],
                      "note": "Every RAROC and SVA tile shows the lifetime basis; the year-one figure is in the (i)."},
            "amount_sar_mn": m["amount_sar_mn"], "dscr_post": m["dscr_post"], "debt_ebitda_post": m["debt_ebitda_post"],
            "el": er["el"], "rwa": er["rwa"], "pd": er["pd"], "lgd": er["lgd"], "ead_y1": er["ead_y1"], "crm": er["crm"], "bands": er["bands"],
            "bridge": raroc_bridge(pid, a=a), "period": reporting_period(),
            "source": "engine.analyse (Deal Desk engine; parameters " + D.version() + ")"}


def covenant_headroom(pid: str, a: dict[str, Any]) -> list[dict[str, Any]]:
    """Each financial covenant against the structure's post-deal ratio, with headroom (positive = room left)."""
    p = D.proposal(pid)
    m = a["metrics"]
    out = []
    for c in p["security"].get("covenants") or []:
        typ, thr = str(c["type"]), float(c["threshold"])
        low = typ.lower()
        if "dscr" in low:
            v, hr = m.get("dscr_post"), (m.get("dscr_post") / thr - 1) if m.get("dscr_post") else None
            sense = "min"
        elif "ebitda" in low and ("debt" in low or "leverage" in low):
            v, hr = m.get("debt_ebitda_post"), (1 - m.get("debt_ebitda_post") / thr) if m.get("debt_ebitda_post") else None
            sense = "max"
        else:
            continue
        out.append({"covenant": typ, "threshold": thr, "value": v, "sense": sense, "headroom_pct": hr * 100 if hr is not None else None,
                    "breached": hr is not None and hr < 0,
                    "text": (f"{typ} {v:.2f}x against {'minimum' if sense == 'min' else 'maximum'} {thr:.2f}x: "
                             f"{'breached' if hr is not None and hr < 0 else 'headroom'} {abs(hr) * 100:.1f}%") if v is not None and hr is not None else typ})
    return out


def rating_rank(r: str) -> int:
    return rank(r)
