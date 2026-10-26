"""Step 1, learn the participant's policy: Session O's P6 learner, kept as a demo-only version.

Found: every threshold and condition the policy sets, with its clause and quote, and how it compares with the value
CreditProbe uses today. Missing: every parameter the review and the engine use that the policy does not set; those
keep the CreditProbe default, labelled as such. Nothing is written to the bank's rule book or parameter tables; a
checker can approve the policy, which turns it into a normal P6 proposal (Parameters > Learn from documents) where
every item is still accepted one by one (maker-checker).
"""
from __future__ import annotations

import copy
from typing import Any

from backend.dealdesk.house_style.onboarding import learn as L
from backend.dealdesk.house_style.onboarding import metrics as M
from backend.dealdesk.house_style.onboarding import service as O

DEMO_STATUS = "demo-only"


def _bytes_for_learner(name: str, data: bytes, doc: dict[str, Any]) -> tuple[str, bytes]:
    """The learner reads .docx/.pdf/.md/.txt; a scan arrives as its OCR text."""
    low = name.lower()
    from backend.dealdesk.try_docs import arabic
    if doc.get("language") == "ar" or arabic.is_arabic(doc.get("text", "")):
        # an Arabic policy: the banking terms in the English wording the clause reader knows (quotes keep the numbers)
        return name.rsplit(".", 1)[0] + ".txt", arabic.policy_text(doc["text"]).encode("utf-8")
    if doc.get("method", "").endswith("(OCR)") or not low.endswith((".docx", ".pdf", ".md", ".txt")):
        return name.rsplit(".", 1)[0] + ".txt", doc["text"].encode("utf-8")
    return name, data


def _found_row(it: dict[str, Any]) -> dict[str, Any]:
    p = it.get("param") or {}
    return {"id": it["id"], "metric": it.get("metric"), "label": it.get("label"), "type": it["type"], "clause": it.get("clause"),
            "quote": it.get("quote"), "value": it.get("value"), "unit": it.get("unit"), "checkability": it.get("checkability"),
            "why_manual": it.get("why"), "rule_id": (it.get("rule") or {}).get("id"),
            "param": {k: p.get(k) for k in ("table", "row", "field", "proposed", "in_force", "change", "conversion")} if p else None,
            "conflict": it.get("conflict"), "status": DEMO_STATUS}


def _defaults(found_metrics: set[str]) -> list[dict[str, Any]]:
    """Every parameter-backed metric the policy does not set, with the value CreditProbe uses (labelled default)."""
    out = []
    for met in M.METRICS:
        if met["key"] in found_metrics:
            continue
        if met.get("param"):
            probe = [{"param": copy.deepcopy(met["param"]) | {"proposed": None}, "stricter": met["stricter"]}]
            L.in_force(probe)
            pp = probe[0]["param"]
            out.append({"metric": met["key"], "label": met["label"], "value": pp.get("in_force"), "unit": met["unit"],
                        "source": f"CreditProbe default ({pp['table']} {pp.get('version_in_force') or ''})".replace(" )", ")"),
                        "default": True, "checked": bool(met.get("rule"))})
        else:
            out.append({"metric": met["key"], "label": met["label"], "value": None, "unit": met["unit"],
                        "source": "not in your policy: not checked", "default": True, "checked": False})
    return out


def defaults_only() -> dict[str, Any]:
    d = _defaults(set())
    return {"found": [], "missing": d, "rules": [], "conflicts": [], "gaps": {"data": [], "sections": []}, "version": None,
            "summary": f"No policy: {sum(1 for x in d if x['value'] is not None)} parameters use the CreditProbe default."}


def learn(name: str, data: bytes, doc: dict[str, Any]) -> dict[str, Any]:
    nm, b = _bytes_for_learner(name, data, doc)
    s = O.learn((nm, b), [], save=False)
    items = s["items"]
    found = [_found_row(it) for it in items]
    lang = doc.get("language", "en")
    if lang == "ar":  # keep the participant's own Arabic wording as the quote
        import re as _re
        orig = {m.group(1): m.group(2).strip() for m in (_re.match(r"^\s*(\d{1,2}\.\d{1,2})\s+(.+)$", ln) for ln in
                                                         doc["text"].splitlines()) if m}
        for f in found:
            if f.get("clause") in orig:
                f["quote_en"], f["quote"] = f.get("quote"), orig[f["clause"]]
    found_metrics = {it.get("metric") for it in items if it.get("metric")}
    missing = _defaults(found_metrics)
    rules = []
    for it in items:
        r = it.get("rule")
        if r:
            rules.append({**copy.deepcopy(r), "enabled": True, "status": DEMO_STATUS, "clause": it.get("clause"), "quote": it.get("quote")})
    n_thr = sum(1 for it in items if it["type"] == "threshold")
    n_def = sum(1 for x in missing if x["value"] is not None)
    summary = (f"Found {n_thr} thresholds and {len(items) - n_thr} conditions in {name} ({len(rules)} become review rules); "
               f"{len(s['conflicts'])} clauses weaker than the CBUAE CRM Standards; {len(missing)} items not in the policy, "
               f"{n_def} of them on the CreditProbe default. Demo-only version: nothing changes in the bank's parameters.")
    if not items and lang == "ar":
        summary = (f"{name} is in Arabic and no clause could be matched to a known parameter; every parameter uses the CreditProbe "
                   "default, labelled.")
    return {"found": found, "missing": missing, "rules": rules, "conflicts": s["conflicts"], "consistent": s.get("consistent", []),
            "gaps": s["gaps"], "documents": s["documents"], "learner_seconds": s["timings"]["learn_s"],
            "version": {"id": "demo-" + (doc.get("sha256") or "")[:8], "status": DEMO_STATUS,
                        "applies_to": "this demo session only; approve to propose it to the bank's checker"},
            "summary": summary}


def approve(name: str, data: bytes, doc: dict[str, Any], by: str) -> dict[str, Any]:
    """Approve the demo policy: it becomes a normal P6 session (every item PROPOSED; a checker accepts each one)."""
    nm, b = _bytes_for_learner(name, data, doc)
    s = O.learn((nm, b), [], by=by, save=True)
    return {"onboarding_session": s["session_id"], "items": len(s["items"]), "status": "proposed",
            "where": "Deal Desk > Parameters > Learn from documents", "summary": s["summary"]["text"]}
