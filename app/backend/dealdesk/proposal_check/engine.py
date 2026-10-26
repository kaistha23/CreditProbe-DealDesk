"""The proposal check (PLAN_R14 p, K31 / D1): the quality of the RM's paper, separate from the quality of the deal.

    res = check_docx(data, name, pid=None)    # Word upload; pid detected from the header block (CIF / customer) when not given
    res = check_record(pid)                    # no Word on file: the RM's memo (data/dealdesk/memos) or the submission record
    res["score"], res["sections"], res["defects"], res["observations"], res["queries"], res["rows"]  (dd_proposal_quality rows)

Deterministic (N4): the same document and the same Data Domains rows give the same result; no model is called. Every defect
carries the claim it is about, the bank's evidence (relation, key) and the query to the RM.
"""
from __future__ import annotations

import pathlib
import re
import time
from datetime import date
from typing import Any

from backend.dealdesk.house_style.bankform import ctx as bctx, registry, source as S
from backend.dealdesk.proposal_check import parse, rules

V5 = pathlib.Path(__file__).resolve().parents[3]
AS_OF = "2026-10-18"   # the demo's today (backend/dealdesk/data/schema.py AS_OF_DATE)
PENALTY = {"critical": 50, "major": 25, "minor": 5, "info": 0}
CATEGORIES = ("completeness", "accuracy", "consistency", "disclosure", "voice", "policy")
STAMP = "2026-10-18T21:00:00Z"


def _as_of() -> date:
    try:
        from backend.dealdesk.data import schema
        return date.fromisoformat(schema.AS_OF_DATE)
    except Exception:  # noqa: BLE001
        return date.fromisoformat(AS_OF)


def detect_pid(doc: dict[str, Any]) -> str | None:
    deals = S.read("dd_deal")
    hdr = {k.lower(): v for k, v in doc.get("header", {}).items()}
    cif = next((v for k, v in hdr.items() if "cif" in k), "")
    for d in deals:
        if cif and str(d.get("cif") or "") == cif.strip():
            return str(d["proposal_id"])
    text = (doc.get("title", "") + " " + " ".join(hdr.values()) + " " + doc.get("full_text", "")[:3000]).lower()
    for d in sorted(deals, key=lambda d: -len(str(d.get("obligor_name") or ""))):
        n = str(d.get("obligor_name") or "").lower()
        if n and n in text:
            return str(d["proposal_id"])
    m = re.search(r"\b((?:DD|PL)-\d{2}|R1[2-4]-[A-Z0-9]+)\b", doc.get("title", "") + " " + doc.get("full_text", "")[:2000])
    return m.group(1) if m else None


def _deal_row(pid: str) -> dict[str, Any]:
    r = S.read("dd_deal", proposal_id=pid)
    return r[-1] if r else {}


def run(pid: str, doc: dict[str, Any]) -> dict[str, Any]:
    t0 = time.perf_counter()
    D = bctx.load(pid, price=False)
    deal = _deal_row(pid)
    C = rules.Ctx(doc=doc, D=D, as_of=_as_of(), deal=deal)
    found: list[dict[str, Any]] = []
    for fn in rules.RULES:
        try:
            found += fn(C)
        except Exception as e:  # noqa: BLE001 - one rule's data problem never takes the check down
            found.append(rules.F(f"ERR-{fn.__name__}", "completeness", "info", "observation", "", "header",
                                 f"Check {fn.__name__} could not run ({type(e).__name__})"))
    for i, f in enumerate(found):
        f["n"] = i + 1
    rank = {"critical": 0, "major": 1, "minor": 2, "info": 3}
    defects = sorted([f for f in found if f["result"] == "defect"], key=lambda f: (rank.get(f["severity"], 4), f["n"]))  # critical first
    obs = [f for f in found if f["result"] == "observation"]
    have = {s["key"] for s in doc["sections"]}
    secs = []
    for k in registry.ANATOMY:
        spec = registry.BY_KEY[k]
        mine = [f for f in found if f["section_key"] == k]
        present = k in have
        pen = sum(PENALTY.get(f["severity"], 0) for f in mine if f["result"] != "pass")
        na = k == "new_project" and not present and not any(str(r.get("status")) == "new" for r in D.rows("dd_project"))
        na = na or (k == "projects" and not present and not any(int(bctx.num(r.get("financed_flag")) or 0) for r in D.rows("dd_project")))
        score = 100.0 if na else (max(0.0, 100.0 - pen) if present else 0.0)
        secs.append({"key": k, "n": spec.n, "heading": spec.heading, "present": present, "applicable": not na, "score": score,
                     "defects": sum(1 for f in mine if f["result"] == "defect"), "observations": sum(1 for f in mine if f["result"] == "observation"),
                     "critical": sum(1 for f in mine if f["severity"] == "critical" and f["result"] == "defect"),
                     "words": next((s["words"] for s in doc["sections"] if s["key"] == k), 0)})
    score = round(sum(s["score"] for s in secs) / len(secs), 1)
    by_cat = {c: sum(1 for f in defects if f["category"] == c) for c in CATEGORIES}
    run_id = f"PQ-{pid}-{doc['sha'][:8]}"
    queries = [{"n": i + 1, "section": registry.BY_KEY[f["section_key"]].n if f["section_key"] in registry.BY_KEY else 0,
                "heading": registry.BY_KEY[f["section_key"]].heading if f["section_key"] in registry.BY_KEY else "", "severity": f["severity"],
                "title": f["title"], "query": f["query"], "check": f["check"], "defect_type": f["defect_type"]}
               for i, f in enumerate(sorted([f for f in found if f["query"]], key=lambda f: (-PENALTY[f["severity"]], f["n"])))]
    res = {"proposal_id": pid, "run_id": run_id, "document": doc["name"], "document_kind": doc["kind"], "document_sha": doc["sha"],
           "customer": D.name, "rm": deal.get("rm", ""), "branch": deal.get("branch") or deal.get("business_unit") or "", "sector": D.get("sector", default=""),
           "status": deal.get("status", ""), "score": score, "grade": grade(score), "sections": secs,
           "sections_present": sum(1 for s in secs if s["present"]), "defects": defects, "observations": obs,
           "passes": [f for f in found if f["result"] == "pass"], "critical": sum(1 for f in defects if f["severity"] == "critical"),
           "by_category": by_cat, "queries": queries, "as_of": C.as_of.isoformat(), "method": "deterministic rules over the document and Data Domains (no model)",
           "elapsed_s": round(time.perf_counter() - t0, 3),
           "headline": headline(D.name, score, defects, secs)}
    res["rows"] = rows(res, found)
    from backend.dealdesk.proposal_check.section_detail import details, document_view, rm_brief  # R15 b (L10, L11)
    res["section_detail"] = details(res, doc)
    res["brief"] = rm_brief(res)
    res["document_view"] = document_view(res, doc)
    return res


def grade(score: float) -> str:
    return "A" if score >= 95 else "B" if score >= 85 else "C" if score >= 70 else "D" if score >= 50 else "E"


def headline(name: str, score: float, defects: list[dict[str, Any]], secs: list[dict[str, Any]]) -> str:
    crit = sum(1 for f in defects if f["severity"] == "critical")
    miss = sum(1 for s in secs if not s["present"] and s["applicable"])
    return (f"{name}: proposal quality {score:.0f}/100 (grade {grade(score)}); {len(defects)} defects, {crit} critical; "
            f"{20 - miss} of 20 sections present." if defects else f"{name}: proposal quality {score:.0f}/100 (grade {grade(score)}); no defects found.")


def rows(res: dict[str, Any], found: list[dict[str, Any]], at: str | None = None) -> list[dict[str, Any]]:
    at = at or STAMP
    base = {"run_id": res["run_id"], "proposal_id": res["proposal_id"], "document": res["document"], "document_sha": res["document_sha"],
            "rm": res["rm"], "branch": res["branch"], "sector": res["sector"], "checked_at": at}
    out = []
    for f in found:
        spec = registry.BY_KEY.get(f["section_key"])
        out.append({**base, "quality_id": f"{res['run_id']}:{f['n']:03d}", "section_key": f["section_key"], "section_n": spec.n if spec else 0,
                    "section_heading": spec.heading if spec else "", "check": f["check"], "category": f["category"], "severity": f["severity"],
                    "result": f["result"], "defect_type": f["defect_type"], "title": f["title"], "claim": f["claim"], "evidence": f["evidence"],
                    "evidence_relation": f["evidence_relation"], "evidence_key": f["evidence_key"], "query": f["query"], "score": None, "defects_n": None,
                    "status": "open" if f["result"] == "defect" else "closed"})
    for s in res["sections"]:
        out.append({**base, "quality_id": f"{res['run_id']}:S{s['n']:02d}", "section_key": s["key"], "section_n": s["n"], "section_heading": s["heading"],
                    "check": "section_score", "category": "score", "severity": "info", "result": "score", "defect_type": "",
                    "title": f"Section {s['n']} {s['heading']}: {s['score']:.0f}/100" + ("" if s["present"] else " (missing)"), "claim": "", "evidence": "",
                    "evidence_relation": "", "evidence_key": "", "query": "", "score": s["score"], "defects_n": s["defects"], "status": "closed"})
    out.append({**base, "quality_id": f"{res['run_id']}:P", "section_key": "", "section_n": 0, "section_heading": "", "check": "proposal_score",
                "category": "score", "severity": "info", "result": "score", "defect_type": "", "title": res["headline"], "claim": "", "evidence": "",
                "evidence_relation": "", "evidence_key": "", "query": "", "score": res["score"], "defects_n": len(res["defects"]), "status": "closed"})
    return out


def check_docx(data: bytes, name: str = "proposal.docx", pid: str | None = None) -> dict[str, Any]:
    doc = parse.read_docx(data, name)
    pid = pid or detect_pid(doc)
    if not pid:
        raise LookupError("The proposal could not be matched to a deal in dd_deal (no CIF or customer name found). Choose the deal first.")
    return run(pid, doc)


def memo_path(pid: str) -> pathlib.Path | None:
    p = V5 / "data" / "dealdesk" / "memos" / f"{pid}.docx"
    return p if p.exists() else None


class NoProposal(KeyError):
    """R15 b (L7): nothing the RM wrote is on file for this deal (no Word, no memo, no published submission record)."""


def check_record(pid: str, use_record: bool = False) -> dict[str, Any]:
    """What the RM submitted for a deal with no Word upload: the memo on file, else the submission record in dd_deal.

    R15 b (L7): a desk proposal (a renewal opened from the Book) has no RM paper and no published record: NoProposal,
    unless the reviewer chose "Use the submission record" (use_record), which checks the desk's pre-filled record."""
    from backend.dealdesk.proposal_check import store
    up = store.latest_upload(pid)
    if up is not None:
        return check_docx(up[0], up[1], pid)
    from backend.dealdesk.proposal_check import demo_pack
    dp = demo_pack.OUT / f"{pid}_RM_proposal_half_baked.docx"
    if dp.exists():  # the demo deal: the RM's half-baked paper is the one on file
        return check_docx(dp.read_bytes(), dp.name, pid)
    mp = memo_path(pid)
    if mp is not None:
        return check_docx(mp.read_bytes(), mp.name, pid)
    try:
        return run(pid, parse.from_record(pid))
    except KeyError:
        from backend.dealdesk.house_style.bankform import ctx as _ctx
        user = _ctx._user_proposal(pid)  # noqa: SLF001
        if user is None:
            raise
        if not use_record:
            raise NoProposal(pid) from None
        return run(pid, parse.from_record(pid, deal=user))
