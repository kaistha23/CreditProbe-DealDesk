"""The interpreter (K23 (5), N4): deterministic text per structure, from the run's own numbers. Same text every run;
a model may only polish it. Plain words: RAROC, SVA, DSCR explained on first use in the plain-words lines."""
from __future__ import annotations

import math
from typing import Any

TEST_LABEL = {"dscr": "DSCR", "debt_ebitda": "Debt/EBITDA against policy", "ltv": "LTV", "covenants": "a covenant", "rating": "the minimum rating",
              "stage": "Stage 1 (it moves to Stage 2)", "limits": "a hard limit", "raroc": "the hurdle"}


def _x(v: Any) -> str:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "–"
    return "n/a" if not math.isfinite(f) else f"{f:.2f}x"


def _pct(v: Any, dp: int = 1) -> str:
    try:
        return f"{float(v) * 100:.{dp}f}%"
    except (TypeError, ValueError):
        return "–"


def _sar(v: Any) -> str:
    try:
        f = float(v)
        f = 0.0 if abs(f) < 0.005 else f
        return f"SAR {f:,.2f}m" if abs(f) < 10 else f"SAR {f:,.1f}m"
    except (TypeError, ValueError):
        return "–"


def not_stressed(row: dict[str, Any]) -> str:
    return (f"{row['label']} is not stressed: it fails before any stress ({row['not_recommendable_reason']}). "
            "Fix the base case first, or run it on request to show the committee how far it falls.")


def short_limit(label: str, obligor: str = "") -> str:
    """'DSCR after the deal (Al Sahel ...)' -> 'DSCR after the deal' when the scope is the obligor itself."""
    if obligor and label.endswith(f"({obligor})"):
        return label[: -len(obligor) - 2].rstrip()
    return label


def _detail(sr: dict[str, Any], tests: list[str], obligor: str = "") -> str:
    m = sr.get("metrics") or {}
    th = sr.get("thresholds") or {}
    bits = []
    shown = set(tests)
    for t in tests:
        if t == "dscr":
            bits.append(f"DSCR {_x(m.get('dscr'))} against {_x(th.get('dscr_limit') or 1.0)}")
        elif t == "debt_ebitda":
            bits.append(f"Debt/EBITDA {_x(m.get('debt_ebitda'))} against the {_x(th.get('debt_ebitda_limit'))} policy limit")
        elif t == "covenants":
            br = [c for c in sr.get("covenants") or [] if c.get("status") == "breach"]
            for c in br[:2]:
                typ = c["type"].lower()
                same = ("dscr" in shown and typ.startswith("dscr")) or ("debt_ebitda" in shown and "ebitda" in typ and "debt" in typ)
                if same and abs(float(c["threshold"]) - float((th.get("dscr_limit") if typ.startswith("dscr") else th.get("debt_ebitda_limit")) or 0)) < 1e-9:
                    continue
                bits.append(f"{c['type']} covenant {_x(c.get('value'))} against {_x(c['threshold'])}")
        elif t == "stage":
            bits.append(f"Stage {m.get('stage')} ({m.get('stage_reason') or 'downgrade'})")
        elif t == "limits":
            ls = [short_limit(x, obligor) for x in (sr.get("limits") or {}).get("new_labels", [])]
            ls = [x for x in ls if not ((x.startswith("DSCR") and "dscr" in shown) or (x.startswith("Debt/EBITDA") and "debt_ebitda" in shown))]
            if ls:
                bits.append("hard limit " + ", ".join(ls[:2]))
        elif t == "ltv":
            bits.append(f"LTV {_pct(m.get('ltv'))} against {_pct(th.get('ltv_limit'))}")
        elif t == "rating":
            bits.append(f"rating {m.get('rating')} below the minimum")
    return "; ".join(bits)


def _why(sr: dict[str, Any]) -> str:
    st = [s for s in sr.get("steps") or [] if s.get("display") and s.get("step") != "Parts that do not apply"]
    f = sr.get("financials") or {}
    chain = st[0]["display"] if st else ""
    e0, e1 = f.get("base_ebitda"), f.get("ebitda")
    if e0 and e1 is not None:
        chain += ("; " if chain else "") + f"EBITDA {_sar(e0)} → {_sar(e1)}"
    if f.get("working_capital_funded"):
        chain += f", {_sar(f['working_capital_funded'])} of extra working capital funded with debt"
    return chain


def structure(row: dict[str, Any], res: dict[str, Any], out: dict[str, Any]) -> dict[str, Any]:
    """{first, why, survives, lines}: what breaks first, why, and how far it survives."""
    by = {r["id"]: r for r in out["rows"]}
    first = next((c["first_break"] for c in res["cells"] if c["first_break"]), None)
    sev = next((c["severity"] for c in res["cells"] if c["first_break"]), None)
    up = res["survives_up_to"]
    if first is None:
        s = f"{row['label']} survives every applicable scenario up to severe."
        return {"first": "Nothing breaks.", "why": "", "survives": s, "lines": [s]}
    sr = by.get(first["id"], {})
    f = f"{first['label']} ({sev}) breaks first: {_detail(sr, first['tests'], out.get('obligor', ''))}."
    w = _why(sr)
    s = ("It does not survive a mild scenario." if up == "none" else f"It survives up to {up}, not {sev}.")
    lines = [f, ("Why: " + w + ".") if w else "", s]
    return {"first": f, "why": w, "survives": s, "lines": [x for x in lines if x]}


def proofed(before: dict[str, Any], after: dict[str, Any], changes: list[dict[str, Any]], target: str,
            b_row: dict[str, Any], a_row: dict[str, Any], survives: bool, uncured: list[str]) -> dict[str, Any]:
    ch = "; ".join(c["text"] for c in changes) or ("no change needed" if survives else "no change to the structure helps")
    cost = (f"RAROC {_pct(b_row['raroc'], 2)} → {_pct(a_row['raroc'], 2)}, SVA {_sar(b_row['sva'])} → {_sar(a_row['sva'])}"
            f" ({a_row['sva_basis'].replace('_', '-')} basis)")
    asks = [c["client"] for c in changes if c.get("client")]
    lines = [f"Stress-proofed to {target}: {ch}.", f"What it costs: {cost}."]
    if asks:
        lines.append("What it asks of the client: " + "; ".join(asks) + ".")
    if survives:
        lines.append(f"The new structure survives every applicable {target} scenario (and milder); severe is monitored, not designed for.")
    else:
        lines.append(f"It still does not survive {target}: " + "; ".join(uncured) + ". Not curable by structure alone: accept and monitor, or decline.")
    return {"changes": ch, "cost": cost, "client": "; ".join(asks), "lines": lines}


def matrix_plain(cols: list[dict[str, Any]], reg: dict[str, Any]) -> list[str]:
    st = [c for c in cols if c["stressed"]]
    out = [f"This puts each chosen structure through mild, moderate and severe shocks to the drivers that matter for this deal, "
           f"in today's conditions ({reg['label'].lower()})."]
    for c in cols[:3]:
        if not c["stressed"]:
            out.append(f"{c['label']}: not stressed, it already fails before any shock.")
        else:
            up = c["survives_up_to"]
            out.append(f"{c['label']}: " + ("survives even severe shocks." if up == "severe" else
                                             "breaks at the mildest shock." if up == "none" else f"holds up to {up} shocks."))
    if st and any(c["survives_up_to"] in ("none", "mild") for c in st):
        out.append("Use Stress-proof to find the smallest change that survives a moderate shock.")
    return out[:4]


def matrix_read(cols: list[dict[str, Any]]) -> list[str]:
    """R15 b (L8 (b)): how to read the stress matrix, and what breaks first and why, in plain words."""
    out = ["How to read it: each row is a structure, each column a severity (mild, moderate, severe). A cell fails when a shock of "
           "that severity newly breaks a test the structure passes today: DSCR, leverage against policy, a covenant, the rating floor, "
           "Stage 1 or a hard limit. Stressed RAROC is shown, not tested."]
    for c in cols:
        if not c.get("stressed"):
            continue
        bad = next((x for x in c.get("cells") or [] if not x.get("passes") and x.get("first_break")), None)
        if bad:
            fb = bad["first_break"]
            out.append(f"{c['label']}: breaks first at {bad['severity']} on {fb['label']}, which breaks "
                       f"{', '.join(t if t[:2].isupper() else t[:1].lower() + t[1:] for t in fb.get('test_labels') or []) or 'a test'}.")
        else:
            out.append(f"{c['label']}: no severity breaks a test.")
        if len(out) >= 3:
            break
    return out
