"""Assemble the detector's answer for a deal or a Book renewal, and the sentences the papers print.

    assess(pid)        {subject, grade, signals, families, headline, lines, coverage, sources, as_of, mode}
    assess_book(fid)   the same for a back-book facility (corporate book and deposits only: audit and related-party
                       signals are "not assessable" and the grade says "limited")
    paragraph(pid)     [sentences] in the credit voice for the synopsis and the committee paper
"""
from __future__ import annotations

import functools
from typing import Any

from backend.dealdesk.fin_quality import grade as G
from backend.dealdesk.fin_quality import inputs as I
from backend.dealdesk.fin_quality import signals as SG

SEV_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4, "none": 5, "not_assessable": 6}
FAM_RANK = {k: i for i, k in enumerate(SG.FAMILIES)}


def rank(s: dict[str, Any]) -> tuple[int, int, str]:
    """Most severe first; within a severity, in family order (related parties first), then by code."""
    return (SEV_RANK.get(s["severity"], 9), FAM_RANK.get(s["family"], 99), s["code"])


def _version() -> str:
    try:
        from backend.dealdesk.data import store as DS
        return "|".join(str(DS.version_of(r)) for r in ("dd_financials_detail", "dd_project", "dd_account_conduct", "dd_document", "dd_tnc", "dd_business_profile"))
    except Exception:  # noqa: BLE001
        return ""


def _families(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for key, label in SG.FAMILIES.items():
        ss = [s for s in signals if s["family"] == key]
        fl = [s for s in ss if s["flag"] is True]
        worst = min((s["severity"] for s in fl), key=lambda v: SEV_RANK.get(v, 9), default=None)
        out.append({"family": key, "label": label, "signals": len(ss), "flagged": len(fl), "assessable": sum(1 for s in ss if s["flag"] is not None),
                    "worst": worst})
    return out


def _domain(relation: str) -> str | None:
    try:
        from backend.dealdesk.data import store as DS
        return DS.domain_of(relation)
    except Exception:  # noqa: BLE001
        return None


def _with_domains(signals: list[dict[str, Any]]) -> None:
    """Every source names its Data Domains domain too, so the panel opens it in Data Domains."""
    for s in signals:
        for src in [s.get("source")] + list(s.get("sources") or []):
            if src and src.get("relation") and "domain" not in src:
                src["domain"] = _domain(src["relation"])


def _result(x: dict[str, Any]) -> dict[str, Any]:
    signals = SG.run(x)
    _with_domains(signals)
    g = G.grade(signals)
    flagged = sorted([s for s in signals if s["flag"] is True], key=rank)
    ys = x.get("years") or []
    subject = {"kind": x["kind"], "id": x["id"], "proposal_id": x.get("proposal_id"), "facility_id": x.get("facility_id"), "obligor_id": x.get("obligor_id"),
               "name": x["name"], "group": x.get("group"), "sector": x.get("sector"), "currency": x["currency"],
               "periods": [y["label"] for y in ys], "entity": ys[-1].get("entity_name") if ys else None, "scope": ys[-1].get("scope") if ys else None}
    res = {"subject": subject, "as_of": x["as_of_date"], "period": x.get("period"), "mode": x["mode"], "grade": g, "signals": signals,
           "flagged": [s["code"] for s in flagged], "families": _families(signals),
           "sources": sorted({s["source"]["relation"] for s in signals if s.get("source")} | {r["relation"] for s in signals for r in s.get("sources") or []})}
    res["headline"] = headline(res)
    res["lines"] = [s["text"] for s in flagged[:5]]
    return res


@functools.lru_cache(maxsize=128)
def _assess(pid: str, tag: str) -> dict[str, Any]:
    return _result(I.load(pid))


@functools.lru_cache(maxsize=256)
def _assess_book(fid: str, tag: str) -> dict[str, Any]:
    return _result(I.load_book(fid))


def assess(pid: str) -> dict[str, Any]:
    return _assess(pid, _version())


def assess_book(fid: str) -> dict[str, Any]:
    return _assess_book(fid, _version())


def clear() -> None:
    _assess.cache_clear()
    _assess_book.cache_clear()


def _asof_label(res: dict[str, Any]) -> str:
    return SG._asof({"as_of_date": res["as_of"]})  # noqa: SLF001


def headline(res: dict[str, Any]) -> str:
    g = res["grade"]
    asof = _asof_label(res)
    if res["mode"] == "none":
        return f"Financial quality not assessable as at {asof}: statements not provided in Data Domains."
    bs = g["by_severity"]
    sev = ", ".join(f"{n} {k}" for k, n in bs.items() if n)
    return (f"Financial quality grade {g['grade']} as at {asof}: {g['flagged']} of {g['signals']} signals flagged" + (f" ({sev})" if sev else "")
            + f", {g['assessable']} assessable from Data Domains" + ("; coverage limited, so the grade reflects only the data on file" if g["limited"] else "") + ".")


def summary(res: dict[str, Any]) -> dict[str, Any]:
    """The compact view the Book row and lists use."""
    return {"id": res["subject"]["id"], "grade": res["grade"]["grade"], "flagged": res["grade"]["flagged"], "assessable": res["grade"]["assessable"],
            "signals": res["grade"]["signals"], "limited": res["grade"]["limited"], "headline": res["headline"],
            "top": [{"code": s["code"], "label": s["label"], "display": s["display"], "severity": s["severity"]}
                    for s in sorted([s for s in res["signals"] if s["flag"] is True], key=rank)[:3]]}


def paragraph(pid: str | dict[str, Any], max_lines: int = 6) -> list[str]:
    """The "Financial quality" sentences of the synopsis and the committee paper, in the credit voice (voice.py rules):
    the grade with its counts, the flagged signals by severity, the statistical screens with their reliability, and
    what could not be assessed."""
    res = pid if isinstance(pid, dict) else assess(pid)
    asof = _asof_label(res)
    g = res["grade"]
    if res["mode"] == "none":
        return [f"Financial quality screen not available: statements not provided in Data Domains as at {asof}."]
    bs = g["by_severity"]
    out = [f"Financial quality grade **{g['grade']}** as per CreditProbe's financial-quality screen as at {asof}: {g['flagged']} of {g['signals']} signals flagged"
           + (" (" + ", ".join(f"{n} {k}" for k, n in bs.items() if n) + ")" if g["flagged"] else "")
           + f" on {', '.join(res['subject']['periods'][-3:]) or 'the statements on file'}; {g['meaning']}"
           + (f"; only {g['assessable']} of {g['signals']} signals could be assessed from the data on file" if g["limited"] else "") + "."]
    flagged = sorted([s for s in res["signals"] if s["flag"] is True and s["family"] != "statistical"], key=rank)
    for s in flagged[:max_lines]:
        out.append(f"{s['text'].rstrip('.')} ({s['severity']}; {s['code']}, per {s['source']['relation'] if s.get('source') else 'Data Domains'}).")
    if len(flagged) > max_lines:
        out.append(f"{len(flagged) - max_lines} further signal(s) flagged as at {asof}: " + "; ".join(f"{s['label']} {s['display']}" for s in flagged[max_lines:]) + ".")
    st = {s["code"]: s for s in res["signals"] if s["family"] == "statistical"}
    bits = []
    b = st.get("ST-01")
    if b and b["value"] is not None:
        bits.append(f"Beneish M-score {b['value']:.2f} for {b['period']} against {b['threshold']:.2f}" + (" (flagged)" if b["flag"] else ""))
    f = st.get("ST-02")
    if f and f["value"] is not None:
        bits.append(f"Benford MAD {f['value']:.4f} on {f['inputs'].get('n')} reported amounts ({f['inputs'].get('band')})" + (" (flagged)" if f["flag"] else ""))
    if bits:
        out.append("Statistical screens, indicative only as at " + asof + ": " + "; ".join(bits) + ".")
    na = [s["label"] for s in res["signals"] if s["flag"] is None]
    if na:
        out.append(f"Not assessable as at {asof} (inputs not provided): " + ", ".join(na[:6]) + (f" and {len(na) - 6} more" if len(na) > 6 else "") + ".")
    return out
