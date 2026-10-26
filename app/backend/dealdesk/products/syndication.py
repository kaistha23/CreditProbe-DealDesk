"""PLAN_R12 Session P (I28): syndicated facilities, analysed on our share.

  share        facility total, our commitment, our final hold after the sell-down, as amounts and shares
  role         agent / lead (mandated lead arranger) / participant, with what the role means for documents,
               fees and information
  sell_down    the plan, step by step, with our hold and the RAROC / SVA at each step (the engine run on our
               commitment with `hold_pct` = hold / commitment, so arranger skim applies only when we sell down)
  analytics    RAROC, SVA, EAD, RWA, capital and EL of our share (never of the whole facility)
  lenders      pari passu, our voting share against the majority-lenders threshold (blocking minority or not),
               information from the agent and how old it is, covenants as reported by the agent

`dd_syndication`: one row per syndicated deal (contract columns *_mn in SAR million). The engine runs through `deals.get`.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from backend.dealdesk.products import policy, source
from backend.dealdesk.products.project import _bool, _f, _m, _pct

PRODUCT = "syndicated"
REL = "dd_syndication"

ROLES = {
    "agent": {"label": "Facility agent", "documents": "full", "fees": "arrangement and agency fees",
              "information": "we hold the borrower's information and pass it to the lenders"},
    "lead": {"label": "Mandated lead arranger", "documents": "full", "fees": "arrangement fee and skim on the sold share",
             "information": "direct, as arranger"},
    "participant": {"label": "Participant", "documents": "lighter: the information memorandum, the agent's reports and the facility agreement",
                    "fees": "participation fee", "information": "from the agent only"},
}


def role_key(x: Any) -> str:
    s = str(x or "participant").strip().lower()
    if "agent" in s:
        return "agent"
    if "lead" in s or "arranger" in s or "mla" in s or "bookrunner" in s:
        return "lead"
    return "participant"


def _engine(pid: str, commitment: float, hold_amt: float) -> dict[str, Any] | None:
    try:
        from backend.dealdesk import engine
        try:
            from backend.dealdesk.data import deals
            p = deals.get(pid)
        except ImportError:
            from backend.dealdesk import proposals
            p = proposals.get(pid)
    except Exception:  # noqa: BLE001 - the deal is not in the deal registry yet
        return None
    hold_pct = 100.0 if commitment <= 0 else max(1.0, min(100.0, 100.0 * hold_amt / commitment))
    fx = engine.fx(p["ask"].get("currency") or "SAR")
    terms = {"amount": round(commitment / fx, 6), "hold_pct": round(hold_pct, 4)}
    try:
        a = engine.analyse(p, terms)
    except engine.TermsError:
        a = engine.analyse(p, terms, validate=False)
    except Exception:  # noqa: BLE001
        return None
    m = a["metrics"]
    return {"hold_pct_of_commitment": hold_pct, "held_sar_mn": m["held_sar_mn"], "raroc": m["lifetime_raroc"], "hurdle": m["hurdle"],
            "sva": m["sva"], "clears_hurdle": m["clears_hurdle"], "ead_y1": m["ead_y1"], "rwa_y1": m["rwa_y1"],
            "capital_y1": m["capital_y1"], "el_y1": m["el_y1"], "arranger_skim_sar_mn": a["levers"]["arranger_skim_sar_mn"],
            "src": source.derived(source.src("dd_deal", {"proposal_id": pid}), source.src(REL, {"proposal_id": pid}),
                                  method=f"Deal Desk engine on our commitment SAR {commitment:,.1f}m at hold {hold_pct:.1f}% (deal from dd_deal)")}


def analyse(proposal_id: str, as_of: dt.date | None = None) -> dict[str, Any]:
    facs = source.read(REL, proposal_id=proposal_id)
    if not facs:
        return {"proposal_id": proposal_id, "product": PRODUCT, "has_data": False,
                "answer": "No syndicated facility is recorded for this deal."}
    f = facs[0]
    total, commit = _f(f.get("total_facility_mn")), _f(f.get("our_commitment_mn"))
    final = _f(f.get("final_hold_mn"), commit) if f.get("final_hold_mn") is not None else max(0.0, commit - _f(f.get("sell_down_mn")))
    rk = role_key(f.get("role"))
    ccy = "SAR"
    s = lambda c: source.src(REL, f, c)  # noqa: E731
    plan = [{"step": 0, "date": f.get("signing_date"), "hold": commit, "buyer_type": "At signing", "src": s("our_commitment_mn")}]
    if final != commit:
        plan.append({"step": 1, "date": f.get("sell_down_by"), "hold": final, "buyer_type": f"After selling down {_m(commit - final)}",
                     "src": s("final_hold_mn")})
    for st in plan:
        st["share_of_facility"] = st["hold"] / total if total else None
        st["analytics"] = _engine(proposal_id, commit, st["hold"])
    final_a = plan[-1]["analytics"]
    maj = _pct(f.get("majority_lenders_pct")) or 0.6667
    vote = final / total if total else 0.0
    cap = float(policy.v("syndication.max_hold_pct", PRODUCT))
    pari = _bool(f.get("pari_passu_flag"))
    flags = []
    if vote * 100 > cap:
        flags.append(f"Final hold {vote:.0%} of the facility above the {cap:.0f}% guide")
    if pari is False:
        flags.append("Not pari passu with the other lenders")
    if rk != "participant" and final >= commit:
        flags.append("No sell-down planned on an arranged facility")
    if rk == "participant" and not f.get("info_from_agent"):
        flags.append("No information from the agent on file")
    if final_a and not final_a["clears_hurdle"]:
        flags.append(f"RAROC on our hold {final_a['raroc']:.1%} below the {final_a['hurdle']:.1%} hurdle")
    ans = (f"{ROLES[rk]['label']} in a {_m(total)} facility: we commit {_m(commit)} ({commit / total:.0%})"
           + (f" and hold {_m(final)} ({vote:.1%}) after the sell-down" if final != commit else "")) if total \
        else "Our share of the facility is not recorded"
    if final_a:
        ans += (f"; on our {'final ' if final != commit else ''}hold RAROC {final_a['raroc']:.1%} against a {final_a['hurdle']:.1%} hurdle "
                f"(SVA {_m(final_a['sva'])})")
    ans += f"; {'blocking minority' if vote > 1 - maj else 'no blocking minority'} at a {maj:.0%} majority."
    return {"proposal_id": proposal_id, "product": PRODUCT, "has_data": True, "answer": ans,
            "facility": {"name": f.get("facility_name"), "borrower": f.get("borrower"), "currency": ccy, "facility_total": total,
                         "our_commitment": commit, "final_hold": final, "our_share": commit / total if total else None,
                         "final_share": vote, "lenders": int(_f(f.get("lenders_n"))) or None, "agent": f.get("agent_bank"),
                         "mla_banks": f.get("mla_banks"), "pari_passu": pari, "tenor_years": f.get("tenor_years"),
                         "margin_bps": f.get("margin_bps"), "participation_fee_bps": f.get("upfront_fee_bps"),
                         "sell_down_by": f.get("sell_down_by"), "security": f.get("security_text"),
                         "src": {"facility_total": s("total_facility_mn"), "our_commitment": s("our_commitment_mn"),
                                 "final_hold": s("final_hold_mn")}},
            "role": {"key": rk, **ROLES[rk]},
            "sell_down": plan, "analytics": final_a,
            "lenders": {"src": s("majority_lenders_pct"), "majority_pct": maj, "our_vote": vote, "blocking_minority": vote > 1 - maj,
                        "info_from_agent": f.get("info_from_agent"), "agent_info_date": None, "agent_info_age_days": None},
            "covenants_text": f.get("covenants_text"), "covenants": [], "flags": flags}
