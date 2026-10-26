"""Deterministic writers (N3): every sentence is composed from the computed numbers; a model may only polish them.

Each writer returns {"headline": str, "lines": [str, ...]}: the headline is one sentence with the number that
matters, the lines are 3-5 short findings (mantra: less detail is more vibrant), no free notes.
"""
from __future__ import annotations

from typing import Any

CH = {"direct": "directly", "contractor": "as contractors", "supplier": "as suppliers", "customer": "as buyers",
      "macro": "through their sector", "guarantee": "through guarantees", "group": "through the group",
      "collateral": "through shared collateral", "employer": "through the same project employer"}


def n(k: int, one: str, many: str | None = None) -> str:
    """'1 borrower', '3 borrowers', '2 facilities': a count with its noun, no '(s)'."""
    return f"{k:,} {one if k == 1 else (many or one + 's')}"


def m(x: float | None, dp: int = 1) -> str:
    """SAR million with sign-aware formatting."""
    if x is None:
        return "n/a"
    return f"SAR {x:,.{dp}f}m"


def dm(x: float | None, dp: int = 1) -> str:
    if x is None:
        return "n/a"
    return f"{'+' if x >= 0 else '−'}SAR {abs(x):,.{dp}f}m"


def pct(x: float | None, dp: int = 1, signed: bool = False) -> str:
    if x is None:
        return "n/a"
    return f"{x:+.{dp}f}%" if signed else f"{x:.{dp}f}%"


def event_text(o: dict[str, Any]) -> dict[str, Any]:
    ev, imp = o["event"], o["impact"]
    name = ev["label"]
    p = ev.get("params") or {}
    if ev["family"] == "oil" and o["drivers"]:
        name = f"Oil {o['drivers'][0]['value']:+g}%".replace("-", "−")
    elif ev["family"] == "developer_delay" and p.get("name"):
        name = f"{p['name']} delaying payments {p.get('days')} days"
    elif ev["family"] == "sector_downgrade" and p.get("sector"):
        name = f"{p['sector']} downgrade"
    s2 = imp["stage2_after_n"] - imp["stage2_before_n"]
    head = (f"{name} ({ev['severity']}): ECL {dm(imp['ecl_change'])} ({pct(imp['ecl_change_pct'], 2, True)}) to "
            f"{m(imp['ecl_after'], 0)}; Stage 2 {s2:+,d} facilities ({dm(imp['stage2_ead_after'] - imp['stage2_ead_before'], 0)} EAD).")
    if o.get("deal_desk") and not o["channels"]:
        dd = o["deal_desk"]
        k = len({x["contractor_id"] for x in dd})
        head = (f"{name} ({ev['severity']}): {m(sum(x['due'] for x in dd))} certified but unpaid and "
                f"{m(sum(x['lg_outstanding'] for x in dd))} of LGs outstanding at its {'contractors' if k > 1 else 'contractor'} "
                f"in Deal Desk; no corporate book borrower is hit.")
    lines = []
    if o.get("deal_desk"):
        dd = o["deal_desk"]
        lines.append(f"{n(len(dd), 'Deal Desk project')} with this employer: certified but unpaid "
                     f"{m(sum(x['due'] for x in dd))}, retention {m(sum(x['retention'] for x in dd))}, LGs outstanding "
                     f"{m(sum(x['lg_outstanding'] for x in dd))}.")
    for c in sorted(o["channels"], key=lambda c: -c["d_ecl"])[:3]:
        lines.append(f"{n(c['borrowers'], 'borrower')} hit {CH.get(c['channel'], c['channel'])}: EAD {m(c['ead'], 0)}, "
                     f"ECL {dm(c['d_ecl'])}, {c['to_stage2']:,} to Stage 2, {c['to_stage3']:,} to default.")
    if o["call_list"]:
        c0 = o["call_list"][0]
        rm = f", RM {c0['rm']}" if c0.get("rm") else ""
        lines.append(f"Call {n(len(o['call_list']), 'name')} today, first {c0['name']} ({c0['borrower_id']}{rm}): {c0['reason']}")
    else:
        lines.append("No borrower moves enough to call today.")
    if o["by_sector"]:
        top = o["by_sector"][0]
        lines.append(f"Largest sector hit: {top['sector']} (ECL {dm(top['d_ecl'])}).")
    lines.append(f"Severity from the {o['calibration']['label']}.")
    wf = o["employers"]["retail_workforce"]
    if wf["customers"]:
        lines.append(f"{n(wf['customers'], 'retail customer')} salaried by the hit corporates "
                     f"(retail EAD {m(wf['exposure'])}, not stressed here).")
    return {"headline": head, "lines": lines[:6]}


def contagion_text(o: dict[str, Any]) -> dict[str, Any]:
    f, t = o["focal"], o["totals"]
    head = (f"If {f['name']} ({f['borrower_id']}) fails: {n(t['names'], 'other borrower')} carr{'ies' if t['names'] == 1 else 'y'} {m(t['exposure'], 0)} "
            f"of exposure linked to it, {m(t['at_risk'])} at risk; second-order ECL {dm(t['d_ecl_second'])} on top of "
            f"its own {dm(t['d_ecl_focal'])}.")
    lines = []
    for c in o["channels"]:
        if c["names"]:
            lines.append(f"{CH.get(c['channel'], c['channel']).capitalize()}: {n(c['names'], 'name')}, exposure "
                         f"{m(c['exposure'], 0)}, at risk {m(c['at_risk'])}, ECL {dm(c['d_ecl'])}.")
    if t["to_stage2"] or t["to_stage3"]:
        lines.append(f"Other names: {n(t['to_stage2'], 'facility', 'facilities')} move to Stage 2 and {t['to_stage3']:,} default.")
    top = o["names"][:1]
    if top:
        lines.append(f"Most exposed: {top[0]['name']} ({top[0]['borrower_id']}), {top[0]['why']}.")
    return {"headline": head, "lines": lines[:6]}


def employer_text(o: dict[str, Any]) -> dict[str, Any]:
    e, t = o["employer"], o["totals"]
    head = (f"{e['name']}: bank exposure {m(t['exposure'], 0)} through {n(t['contractors'], 'contractor or supplier', 'contractors and suppliers')} "
            f"it pays, of which {m(t['attributable'])} attributable to its payments "
            f"({o['appetite']['status']}).")
    lines = []
    if t.get("own_exposure"):
        lines.append(f"Direct exposure to {e['name']} itself: {m(t['own_exposure'])}; total with contractors "
                     f"{m(t['exposure'] + t['own_exposure'], 0)}.")
    if o.get("projects"):
        lines.append(f"{n(len(o['projects']), 'Deal Desk project')}: LGs outstanding {m(t['lg_outstanding'])}, proposed "
                     f"limits {m(t.get('deal_desk_proposed', 0.0))}; certified but unpaid {m(t.get('due', 0.0))}, "
                     f"retention {m(t.get('retention', 0.0))}.")
        slow = [p for p in o["projects"] if (p.get("payment_delay_days") or 0) >= 90]
        if slow:
            lines.append(f"Payments late on {n(len(slow), 'project')}, worst {max(p['payment_delay_days'] for p in slow)} "
                         f"days with {n(sum(int(p.get('pending_certs') or 0) for p in slow), 'certificate')} pending.")
    dep = [c for c in o["contractors"] if (c.get("revenue_share_pct") or 0) >= 30]
    if dep:
        lines.append(f"{n(len(dep), 'contractor')} take{'s' if len(dep) == 1 else ''} 30% or more of revenue from it; largest exposure "
                     f"{dep[0]['name']} ({m(dep[0]['ead'])}).")
    if t.get("in_early_warning"):
        lines.append(f"{t['in_early_warning']} of its contractors {'is' if t['in_early_warning'] == 1 else 'are'} already in Early Warning "
                     f"({m(t['ews_exposure'])}).")
    a = o["appetite"]
    lines.append(f"Against appetite: own plus attributable exposure ({m(a['value'])}) is {pct(a['utilisation_pct'], 0)} of the "
                 f"{m(a['limit'], 0)} {a['label'].lower()} limit ({a['status']}).")
    return {"headline": head, "lines": lines[:6]}
