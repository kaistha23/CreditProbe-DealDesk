"""Policy Docs: the library, the versioned policy pack, the interpretation of an upload, and the policy lookup.

The pack
  Version 1 is the Cockpit's default pack (backend/cockpit_v4/credit_policy.json), stored as two policy documents
  (the Corporate and the Retail Credit Policy). A policy or circular added to the Cockpit writes a new version:
  the previous pack with the document's clauses applied (a clause with an existing id replaces it, a new id joins
  its section), each carrying its effective date and its source. Withdrawing a document writes another version
  without it. Older versions stay on record. The active version is written to `paths.active_pack_path()`, which
  the Cockpit's pack loader reads (FX-7), so retrieval, receipts and the refusal rules are unchanged and only the
  clauses differ.

Interpretation
  Without a model key the interpretation is deterministic: clause ids and their sentences, the limits and
  thresholds in them (percentages, multiples, days, notches, points, SAR amounts), the book they belong to, the
  change against the clause in force, and the books, segments and Early Warning rules they touch.
"""
from __future__ import annotations

import copy
import json
import os
import re
import sqlite3
from datetime import date
from typing import Any

from backend.playbook_v5 import circulars, paths, store

CLAUSE_RE = re.compile(r"\b([RC]P)[-\s‐-―]?(\d+)\.(\d+)\b", re.I)
THRESH_RE = re.compile(r"(\d+(?:\.\d+)?\s?(?:%|per cent|x\b|days?\b|notch(?:es)?\b|points?\b|bps\b|months?\b|quarters?\b)"
                       r"|SAR\s?\d[\d,.]*\s?(?:bn|m|million|billion)?)", re.I)
MEASURE_CLAUSES: dict[tuple[str, str], list[str]] = {
    ("retail", "stage2"): ["RP-5.1"], ("retail", "ecl"): ["RP-5.1", "RP-5.2"], ("retail", "stage3"): ["RP-5.2"],
    ("retail", "pd"): ["RP-2.2", "RP-5.1"], ("retail", "dpd"): ["RP-4.1"], ("retail", "ews"): ["RP-5.1"],
    ("retail", "rating"): ["RP-5.1"], ("retail", "lgd"): ["RP-2.4"], ("retail", "concentration"): ["RP-2.1"],
    ("corporate", "stage2"): ["CP-3.3"], ("corporate", "ecl"): ["CP-3.3", "CP-3.4"], ("corporate", "stage3"): ["CP-3.3"],
    ("corporate", "pd"): ["CP-3.2", "CP-3.3"], ("corporate", "rating"): ["CP-3.2", "CP-3.3"],
    ("corporate", "dpd"): ["CP-3.3"], ("corporate", "ews"): ["CP-3.1", "CP-3.4"], ("corporate", "lgd"): ["CP-4.1"],
    ("corporate", "concentration"): ["CP-1.3", "CP-1.1", "CP-1.2"],
}
DRIVER_CLAUSES: dict[tuple[str, str], list[str]] = {
    ("retail", "downgrade"): ["RP-5.1"], ("retail", "dpd"): ["RP-5.1", "RP-4.1"], ("retail", "restructuring"): ["RP-4.2"],
    ("retail", "limit"): ["RP-2.1"], ("retail", "collateral"): ["RP-2.4"], ("retail", "macro"): ["RP-5.1"],
    ("corporate", "downgrade"): ["CP-3.3"], ("corporate", "watchlist"): ["CP-3.3", "CP-3.1"],
    ("corporate", "dpd"): ["CP-3.3"], ("corporate", "restructuring"): ["CP-2.3"],
    ("corporate", "collateral"): ["CP-4.1", "CP-4.2"], ("corporate", "concentration"): ["CP-1.3", "CP-1.2"],
    ("corporate", "limit"): ["CP-1.1"], ("corporate", "macro"): ["CP-3.3"],
}
MEASURES = ("stage2", "stage3", "ecl", "pd", "lgd", "rating", "concentration", "dpd", "ews")


def default_pack() -> dict[str, Any]:
    return json.loads(paths.DEFAULT_PACK.read_text(encoding="utf-8"))


def _flat(pack: dict[str, Any], book: str) -> list[dict[str, Any]]:
    out = []
    for s in pack["books"][book]["sections"]:
        for c in s["clauses"]:
            out.append({**c, "book": book, "section": s["section"], "section_title": s["title"]})
    return out


def _clause_out(c: dict[str, Any], book: str, status: str = "active") -> dict[str, Any]:
    return {"clause_id": c["clause"], "book": book, "section": c.get("section", c["clause"].split(".")[0]),
            "section_title": c.get("section_title", ""), "title": c.get("title", ""), "rule": c.get("rule", ""),
            "thresholds": c.get("thresholds") or {}, "applies_to": c.get("applies_to") or [],
            "owner": c.get("owner", ""), "last_reviewed": c.get("last_reviewed", ""), "levers": c.get("levers") or [],
            "effective_from": c.get("effective_from"), "source": c.get("source"), "status": status,
            **({"summary": c["summary"]} if c.get("summary") else {}),
            **({"previous": c["previous"]} if c.get("previous") else {}),
            **({"regulatory_basis": c["regulatory_basis"]} if c.get("regulatory_basis") else {})}


# -------------------------------------------------------------------- pack


def apply(pack: dict[str, Any], doc: dict[str, Any]) -> dict[str, Any]:
    """The pack with one document's clauses applied (replace by id, or join the section)."""
    if doc.get("kind") == "regulation":
        return apply_regulation(pack, doc)
    out = copy.deepcopy(pack)
    for c in doc["clauses"]:
        book = c.get("book") or ("retail" if c["clause"].upper().startswith("RP") else "corporate")
        if book not in out["books"]:
            continue
        clause = {k: v for k, v in c.items() if k not in ("book", "section", "section_title", "previous")}
        clause["effective_from"] = doc.get("effective_from")
        clause["source"] = {"doc_id": doc["id"], "kind": doc["kind"], "reference": doc.get("reference", "")}
        sec_id = c.get("section") or c["clause"].split(".")[0]
        sections = out["books"][book]["sections"]
        sec = next((s for s in sections if s["section"] == sec_id), None)
        if sec is None:
            sec = {"section": sec_id, "title": c.get("section_title") or sec_id, "clauses": []}
            sections.append(sec)
            sections.sort(key=lambda s: int(re.sub(r"\D", "", s["section"]) or 0))
        idx = next((i for i, x in enumerate(sec["clauses"]) if x["clause"] == clause["clause"]), None)
        if idx is None:
            sec["clauses"].append(clause)
            sec["clauses"].sort(key=lambda x: int(x["clause"].split(".")[1]))
        else:
            sec["clauses"][idx] = clause
    return out


#: A regulator's paragraphs behind the bank's own clauses (R6 policy, CBO BM-1230). The Cockpit retrieves the bank's
#: clause by its frozen keyword map (FX-7 path: only the pack changes), so the regulatory paragraphs travel ON the
#: bank clause a question reaches, as `regulatory_basis`, with their own ids ("BM-1230 §4.2") and full text.
REGULATORY_BASIS: dict[str, dict[str, list[str]]] = {
    "BM-1230": {
        "RP-4.2": ["4.1", "4.2", "4.4", "4.5.1", "4.6.1", "4.8"],
        "CP-2.3": ["4.1", "4.2", "4.4", "4.5.1", "4.6.1", "4.8", "1.3"],
        "RP-5.1": ["2.1", "2.5", "5.5.2"],
        "CP-3.3": ["2.1", "2.5", "2.6", "5.5.2"],
        "RP-5.2": ["1.2", "1.3", "5.5.1", "5.6.1"],
        "RP-4.1": ["1.2", "2.5"],
        "RP-4.4": ["6.1", "6.2", "6.3"],
        "CP-3.1": ["3.3", "2.6"],
        "CP-3.2": ["3.4.2", "3.4.3", "3.4.4", "3.3"],
        "CP-1.1": ["3.4.2"],
        "CP-1.2": ["3.4.2"],
        "CP-1.3": ["3.4.2"],
        "CP-4.1": ["1.4", "5.7.5"],
        "CP-4.2": ["5.7.5"],
    },
    # R7 (Session C): the CBUAE Credit Risk Management Standards, which replace BM-1230 in the active pack.
    "CBUAE CRM": {
        "RP-4.2": ["8.3", "8.4", "8.7", "8.10", "9.28", "9.29", "9.31", "9.35", "11.11"],
        "CP-2.3": ["8.3", "8.10", "8.12", "9.28", "9.29", "9.35", "6.9"],
        "RP-5.1": ["7.1", "7.7", "7.8", "9.5", "9.8"],
        "CP-3.3": ["7.1", "7.7", "7.8", "7.11", "9.5", "9.8", "9.10", "9.21", "9.23"],
        "RP-5.2": ["6.3", "6.4", "6.10", "6.11", "9.5", "9.24", "9.19"],
        "RP-4.1": ["3.13", "6.4", "7.8"],
        "RP-4.4": ["12.4", "12.5", "12.6"],
        "CP-3.1": ["7.6", "7.11"],
        "CP-3.2": ["4.3", "9.4", "11.3"],
        "CP-1.1": ["2.6", "2.7"],
        "CP-1.2": ["2.6", "2.7"],
        "CP-1.3": ["3.5", "11.6"],
        "CP-4.1": ["10.7", "10.8", "10.11"],
        "CP-4.2": ["10.11", "10.9"],
    },
}
#: What a regulation does NOT say, carried on the bank clause a question reaches, so an answer never invents it.
REGULATORY_SCOPE: dict[str, dict[str, str]] = {
    "BM-1230": {cid: ("CBO BM-1230 (Credit Management – Prudential Framework) sets no large exposure, single-obligor, "
                      "group or sector limit; it brings large exposures, sector concentrations and connected "
                      "counterparties into the scope of the loan review (BM-1230 §3.4.2). The limit in force is the "
                      "Bank's own clause.") for cid in ("CP-1.1", "CP-1.2", "CP-1.3")},
    "CBUAE CRM": {cid: ("The CBUAE Credit Risk Management Standards set no single-obligor, group or sector limit. They "
                        "require Board approval of any facility above 10% of Tier 1 capital (CBUAE CRM Art. 2.6) and Board "
                        "Credit Committee approval above 5% of Tier 1 capital or AED 1 billion (CBUAE CRM Art. 2.7), and "
                        "thresholds for acceptable concentrations (CBUAE CRM Art. 3.5). The limit in force is the Bank's "
                        "own clause.") for cid in ("CP-1.1", "CP-1.2", "CP-1.3")},
}
BASIS_CHARS = 1500


def _num(cid: str) -> str:
    return cid.split("§", 1)[1] if "§" in cid else cid.rsplit(" ", 1)[-1]


def apply_regulation(pack: dict[str, Any], doc: dict[str, Any]) -> dict[str, Any]:
    """A regulation in the pack: its paragraphs under `regulatory`, and on the bank clauses they stand behind."""
    out = copy.deepcopy(pack)
    ref = doc.get("reference") or doc["id"]
    meta = doc.get("interpretation") or {}
    source = {"doc_id": doc["id"], "kind": "regulation", "reference": ref,
              "issuer": meta.get("issuer", ""), "jurisdiction": meta.get("jurisdiction", "")}
    paras = [{"clause": c["clause"], "title": c.get("title", ""), "rule": c.get("rule", ""),
              "section": c.get("section", ""), "section_title": c.get("section_title", ""),
              "effective_from": doc.get("effective_from"), "source": source} for c in doc["clauses"]]
    out.setdefault("regulatory", {})[ref] = {
        "title": doc["title"], "issuer": meta.get("issuer", ""), "jurisdiction": meta.get("jurisdiction", ""),
        "category": "Regulatory", "effective_from": doc.get("effective_from"), "source": source,
        "source_file": meta.get("source_file", ""), "clauses": paras}
    by_num = {_num(p["clause"]): p for p in paras}
    for book in out["books"].values():
        for sec in book["sections"]:
            for c in sec["clauses"]:
                nums = REGULATORY_BASIS.get(ref, {}).get(c["clause"], [])
                basis = [{"clause_id": by_num[n]["clause"], "title": by_num[n]["title"],
                          "text": by_num[n]["rule"][:BASIS_CHARS], "issuer": source["issuer"],
                          "effective_from": doc.get("effective_from")} for n in nums if n in by_num]
                if basis:
                    c.setdefault("regulatory_basis", []).extend(basis)
                note = REGULATORY_SCOPE.get(ref, {}).get(c["clause"])
                if note:
                    c.setdefault("regulatory_scope", []).append(note)
    if ref == "CBUAE CRM":
        _attach_compliance(out, ref)
    return out


#: R7 (C3.2): the CBUAE CRM breach checks travel to the Cockpit through the pack (FX-7 path, no frozen edit): a
#: summary under `regulatory["CBUAE CRM"]["compliance"]`, and on each bank clause a question reaches, the results of
#: the checks behind it as `regulatory_compliance` (article, check, book, period, breaches, EAD/ECL, shortfall).
COMPLIANCE_CLAUSES: dict[str, list[str]] = {
    "CRM-6.4": ["RP-5.2", "CP-3.3"], "CRM-7.8": ["RP-5.1", "RP-4.1", "CP-3.3"], "CRM-6.12": ["CP-3.3"],
    "CRM-9.11": ["CP-3.3"], "CRM-9.7": ["CP-3.3", "CP-2.3"], "CRM-9.8": ["CP-3.3"], "CRM-9.30": ["CP-2.3", "RP-4.2"],
    "CRM-9.23": ["CP-3.3"], "CRM-9.24": ["RP-5.2"], "CRM-10.8": ["CP-4.1"], "CRM-10.11": ["CP-4.2", "RP-2.4"],
    "CRM-12.5": ["RP-4.4", "CP-3.3"], "CRM-12.3": ["RP-5.2", "CP-3.3"],
}


def _attach_compliance(pack: dict[str, Any], ref: str) -> None:
    try:
        from backend.regulatory import crm_checks

        res = crm_checks.run()
    except Exception:  # noqa: BLE001 - the pack never fails for want of the checks
        return
    pack["regulatory"][ref]["compliance"] = {
        "periods": res["periods"], "totals": res["totals"], "by_book": res["by_book"],
        "by_article": [{k: a[k] for k in ("article", "title", "breaches", "ead_sar_mn", "ecl_sar_mn",
                                          "shortfall_sar_mn")} for a in res["by_article"]],
        "note": ("Results of the CBUAE CRM breach checks on the books (deterministic). Each line names the article, the "
                 "check, the book and period, the number of breaching facilities/accounts and their EAD/ECL in SAR "
                 "million."),
        "href": "/early-warning?crm=1"}
    lines: dict[str, list[dict[str, Any]]] = {}
    for c in res["checks"]:
        for cid in COMPLIANCE_CLAUSES.get(c["check_id"], []):
            if _book_of(cid) != c["book"]:
                continue
            lines.setdefault(cid, []).append({k: c[k] for k in ("article", "title", "book", "period", "status",
                                                                "breaches", "tested", "ead_sar_mn", "ecl_sar_mn",
                                                                "shortfall_sar_mn")})
    for b in pack["books"].values():
        for sec in b["sections"]:
            for c in sec["clauses"]:
                if c["clause"] in lines:
                    c["regulatory_compliance"] = lines[c["clause"]]


def regulatory_clauses(pack: dict[str, Any]) -> list[dict[str, Any]]:
    return [c for r in (pack.get("regulatory") or {}).values() for c in r["clauses"]]


_STOP = set("a an the of in on for to and or is are what does do say says about under with by from at as be any "
            "which how there their this that it cbo central bank oman circular framework annexure bm 1230 "
            "cbuae uae crm standards standard article art paragraph we our compliant compliance breach breaches "
            "requirements requirement rules rule policy prudential me tell".split())
#: A reader's words for a regulatory topic, mapped to the words the regulation uses.
_SYNONYMS = {"restructured": "restructuring rescheduling restructured rescheduled", "restructure": "restructuring rescheduling",
             "rescheduled": "restructuring rescheduling", "forbearance": "restructuring concession",
             "review": "review lrm loan", "credit review": "loan review lrm", "large": "large exposures concentrations",
             "exposure": "exposures concentrations tier capital material", "limits": "limit concentrations exposures",
             "default": "default non performing 90 days", "npl": "non performing stage 3", "sicr": "significant increase",
             "staging": "stage classification", "writeoff": "write off", "provision": "provisioning ecl",
             "provisions": "provisioning ecl", "collateral": "collateral haircut security",
             "governance": "board senior management", "oversight": "cro cco credit review",
             "underwriting": "underwriting credit committee", "models": "model models rating",
             "npa": "non performing assets stage 3", "valuation": "valuation collateral",
             "dpd": "days past due", "watchlist": "watch list", "reporting": "reporting board information",
             "ratings": "rating review annually", "reviewed": "review annually yearly", "often": "frequency annually",
             "exposures": "concentrations tier capital material", "recent": "within last months",
             "probation": "probation instalments arrears settled"}


def _words(text: str) -> list[str]:
    low = re.sub(r"\b(write[-\s]?offs?|written[-\s]off)\b", "writeoff", (text or "").lower())
    return [w for w in re.findall(r"[a-z0-9]+", low) if w not in _STOP]


def search(pack: dict[str, Any], question: str, k: int = 5) -> list[dict[str, Any]]:
    """The regulatory paragraphs of the pack a question reaches, best first (title words count three times)."""
    q = _words(question)
    low = (question or "").lower()
    if "credit review" in low or "loan review" in low:
        q += _words(_SYNONYMS["credit review"])
    for w in list(q):
        q += _words(_SYNONYMS.get(w, ""))
    named = re.findall(r"(?:§|\bart(?:icle)?\.?)\s?(\d+(?:\.\d+)*)", question or "", re.I)
    articles = {n for n in named if "." not in n}
    terms = {t for t in q if not (t.isdigit() and len(t) == 1)}  # "Stage 3": the stage word carries it
    scored = []
    for c in regulatory_clauses(pack):
        if named and _num(c["clause"]) in named and "." in _num(c["clause"]):
            scored.append((100.0, c))
            continue
        tw = _words(c["title"] + " " + c.get("section_title", ""))
        bw = _words(c["rule"])
        score = sum(3 for t in terms if t in tw) + sum(min(bw.count(t), 3) for t in terms) / 2
        if articles and _num(c["clause"]).split(".")[0] in articles and "Art." in c["clause"]:
            score = score + 6 if score else 2
        if score:
            scored.append((score, c))
    scored.sort(key=lambda x: -x[0])
    return [c for _, c in scored[:k]]


def lookup(con: sqlite3.Connection, question: str, k: int = 5) -> dict[str, Any]:
    """Policy for the v5 assistants: the regulatory paragraphs and the bank clauses a question reaches, from the
    active pack, with the pack version every citation quotes."""
    return lookup_pack(active(con)["pack"], question, k)


def active_pack_file() -> dict[str, Any]:
    """The active pack as Policy Docs last wrote it (FX-7 file), for a service that holds no Playbook store. Without
    the file: the default pack with the seeded regulation applied, labelled as the seed labels it."""
    p = paths.active_pack_path()
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = json.loads((paths.V5 / "backend" / "playbook_v5" / "data" / "cbuae_crm.json").read_text(encoding="utf-8"))
        doc = {"id": data["id"], "kind": "regulation", "reference": data["reference"], "title": data["title"],
               "effective_from": data["effective_from"], "clauses": data["clauses"],
               "interpretation": {k: data[k] for k in ("issuer", "jurisdiction", "source_file")}}
        pack = apply_regulation(default_pack(), doc)
        pack["pack_version"] = FALLBACK_PACK_VERSION
        return pack


#: The pack version the seed gives the CBUAE CRM Standards (pp-2026.4: BM-1230 withdrawn, CBUAE CRM added).
FALLBACK_PACK_VERSION = "pp-2026.4"


POLICY_WORDS = re.compile(r"\b(polic(y|ies)|circular|regulat\w*|cbo|central bank|bm[-\s]?1230|clause|prudential|"
                          r"restructur\w*|reschedul\w*|write[-\s]?offs?|sicr|large exposures?|loan review|"
                          r"credit review|cbuae|crm standards?|credit risk management standards?|"
                          r"definition of default|default definition|provisioning|minimum provisions?|"
                          r"collateral haircuts?|collateral valuation|probation period|"
                          r"non[-\s]?performing assets?|article \d+)\b", re.I)


def lookup_pack(pack: dict[str, Any], question: str, k: int = 5) -> dict[str, Any]:
    regs = search(pack, question, k)
    ql = (question or "").lower()
    hit = {x["clause"] for x in regs}
    ranked = sorted(((sum(r["clause_id"] in hit for r in c.get("regulatory_basis") or []), b, c)
                     for b in ("corporate", "retail") for c in _flat(pack, b)), key=lambda x: -x[0])
    bank = [_clause_out(c, b) for n, b, c in ranked if n][:4]
    notes = sorted({n for b in ("corporate", "retail") for c in _flat(pack, b) for n in c.get("regulatory_scope") or []
                    if any(w in ql for w in ("large exposure", "single obligor", "concentration", "exposure limit",
                                             "sector limit", "group limit"))})
    return {"pack_version": pack.get("pack_version"),
            "regulatory": [{"clause_id": c["clause"], "title": c["title"], "text": c["rule"],
                            "issuer": c["source"].get("issuer"), "reference": c["source"].get("reference"),
                            "effective_from": c.get("effective_from"),
                            "href": f"/policy-docs?doc={c['source']['doc_id']}&clause={c['clause']}"} for c in regs],
            "bank_clauses": [{"clause_id": c["clause_id"], "title": c["title"], "rule": c["rule"], "book": c["book"]}
                             for c in bank],
            "notes": notes,
            "citation_rule": ("Quote each paragraph by its id and title in bold (e.g. **CBUAE CRM Art. 7.8 DPD "
                              "indicator**), with the pack version. A topic the paragraphs here do not cover is not in "
                              "the regulation. To find which exposures breach the standards, call crm_breaches.")}


def _docs_in_pack(con: sqlite3.Connection, doc_ids: list[str]) -> list[dict[str, Any]]:
    docs = [doc_dict(con, d) for d in doc_ids]
    return sorted(docs, key=lambda d: (d.get("effective_from") or "", d["id"]))


def build_pack(con: sqlite3.Connection, doc_ids: list[str], label: str) -> dict[str, Any]:
    pack = default_pack()
    for d in _docs_in_pack(con, doc_ids):
        pack = apply(pack, d)
    pack["pack_version"] = label
    pack["base_pack_version"] = default_pack().get("pack_version")
    pack["documents"] = doc_ids
    return pack


def active_version(con: sqlite3.Connection) -> sqlite3.Row:
    r = con.execute("SELECT * FROM policy_pack_versions WHERE active=1 ORDER BY version DESC LIMIT 1").fetchone()
    if r is None:
        raise store.NotFound("There is no active policy pack.")
    return r


def _version_row(r: sqlite3.Row) -> dict[str, Any]:
    pack = store._l(r["pack"], {})
    n = sum(len(s["clauses"]) for b in pack.get("books", {}).values() for s in b["sections"])
    return {"version": r["version"], "label": r["label"], "created_at": r["created_at"],
            "created_by": store.person(r["created_by"]), "effective_from": r["effective_from"],
            "approved_by": store.person(r["approved_by"]), "change": r["change"],
            "documents": store._l(r["documents"], []), "active": bool(r["active"]), "clause_count": n}


#: Provenance kept in the pack file (and read by the Cockpit's tests) but never shown: the label rule.
_PROVENANCE = ("note", "institution", "not_client_data")


def shown(pack: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in pack.items() if k not in _PROVENANCE}


def versions(con: sqlite3.Connection) -> list[dict[str, Any]]:
    return [_version_row(r) for r in con.execute("SELECT * FROM policy_pack_versions ORDER BY version DESC")]


def version(con: sqlite3.Connection, v: int) -> dict[str, Any]:
    r = con.execute("SELECT * FROM policy_pack_versions WHERE version=?", (v,)).fetchone()
    if r is None:
        raise store.NotFound(f"There is no pack version {v}.")
    return {**_version_row(r), "pack": shown(store._l(r["pack"], {}))}


def active(con: sqlite3.Connection) -> dict[str, Any]:
    r = active_version(con)
    return {**_version_row(r), "pack": store._l(r["pack"], {})}


def _next_label(con: sqlite3.Connection) -> tuple[int, str]:
    n = int(con.execute("SELECT COALESCE(MAX(version), 0) FROM policy_pack_versions").fetchone()[0]) + 1
    return n, f"pp-2026.{n}"


def new_version(con: sqlite3.Connection, who: str, doc_ids: list[str], change: str, effective_from: str | None,
                approved_by: str | None, at: str | None = None) -> dict[str, Any]:
    n, label = _next_label(con)
    pack = build_pack(con, doc_ids, label)
    con.execute("UPDATE policy_pack_versions SET active=0")
    con.execute("INSERT INTO policy_pack_versions(version, label, created_at, created_by, effective_from, approved_by, "
                "change, documents, pack, active) VALUES(?,?,?,?,?,?,?,?,?,1)",
                (n, label, at or store.now(), who, effective_from, approved_by, change, store._j(doc_ids),
                 store._j(pack)))
    write_active_pack(con)
    out = active(con)
    return {**out, "pack": shown(out["pack"])}


def write_active_pack(con: sqlite3.Connection) -> None:
    """Write the active pack where the Cockpit reads it (FX-7). Atomic: a reader never sees half a file."""
    try:
        pack = active(con)["pack"]
    except store.NotFound:
        return
    p = paths.active_pack_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(pack, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)


# --------------------------------------------------------------- documents


def doc_dict(con: sqlite3.Connection, doc_id: str) -> dict[str, Any]:
    r = con.execute("SELECT * FROM policy_documents WHERE id=?", (doc_id,)).fetchone()
    if r is None:
        raise store.NotFound(f"There is no policy document {doc_id!r}.")
    return {**dict(r), "clauses": store._l(r["clauses"], []), "interpretation": store._l(r["interpretation"])}


def doc_row(r: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    clauses = store._l(r["clauses"], []) if isinstance(r["clauses"], str) else r["clauses"]
    return {"id": r["id"], "title": r["title"], "kind": r["kind"], "reference": r["reference"], "book": r["book"],
            "status": r["status"], "effective_from": r["effective_from"], "approved_by": store.person(r["approved_by"]),
            "uploaded_by": store.person(r["uploaded_by"]), "uploaded_at": r["uploaded_at"],
            "clause_count": len(clauses), "summary": r["summary"], "href": f"/policy-docs?doc={r['id']}",
            "decided_at": r["decided_at"], "decided_by": store.person(r["decided_by"]),
            "decision_note": r["decision_note"], **_regulatory_meta(r)}


def _regulatory_meta(r: Any) -> dict[str, Any]:
    if r["kind"] != "regulation":
        return {}
    meta = r["interpretation"]
    meta = store._l(meta, {}) if isinstance(meta, str) or meta is None else meta
    return {"category": "Regulatory", "issuer": meta.get("issuer", ""), "jurisdiction": meta.get("jurisdiction", ""),
            "source_file": meta.get("source_file", "")}


def documents(con: sqlite3.Connection, kind: str = "", q: str = "") -> list[dict[str, Any]]:
    rows = [doc_row(r) for r in con.execute(
        "SELECT * FROM policy_documents ORDER BY CASE kind WHEN 'policy' THEN 0 WHEN 'regulation' THEN 1 ELSE 2 END, "
        "uploaded_at DESC, id")]
    if kind:
        rows = [r for r in rows if r["kind"] == kind]
    if q:
        ql = q.lower()
        rows = [r for r in rows if ql in (r["title"] + " " + r["reference"] + " " + r["summary"]).lower()]
    return rows


def document(con: sqlite3.Connection, doc_id: str) -> dict[str, Any]:
    d = doc_dict(con, doc_id)
    out = doc_row(d)
    status = {"active": "active", "pending": "proposed", "reference": "active"}.get(d["status"], "superseded")
    out["clauses"] = [_clause_out(c, c.get("book") or ("regulatory" if d["kind"] == "regulation" else "retail"
                                                       if c["clause"].startswith("RP") else "corporate"),
                                  status) for c in d["clauses"]]
    for c in out["clauses"]:
        c.setdefault("effective_from", d["effective_from"])
        if c["effective_from"] is None:
            c["effective_from"] = d["effective_from"]
        c["source"] = c["source"] or {"doc_id": d["id"], "kind": d["kind"], "reference": d["reference"]}
    out["interpretation"] = d["interpretation"]
    out["files"] = [store.file_row(f) for f in con.execute(
        "SELECT * FROM files WHERE owner_kind='policy' AND owner_id=? ORDER BY name", (doc_id,))]
    out["text_excerpt"] = (d["text"] or "")[:4000]
    out["versions"] = [v for v in versions(con) if doc_id in v["documents"] or v["version"] == 1]
    return out


def insert_document(con: sqlite3.Connection, doc: dict[str, Any], who: str, status: str,
                    interpretation: dict[str, Any] | None = None, at: str | None = None) -> None:
    con.execute("INSERT INTO policy_documents(id, title, kind, reference, book, status, effective_from, approved_by, "
                "uploaded_by, uploaded_at, summary, text, clauses, interpretation, decided_at, decided_by) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (doc["id"], doc["title"], doc["kind"], doc.get("reference", ""), doc.get("book", ""), status,
                 doc.get("effective_from"), doc.get("approved_by"), who, at or store.now(), doc.get("summary", ""),
                 doc.get("text", ""), store._j(doc.get("clauses", [])),
                 store._j(interpretation) if interpretation else None,
                 at if status == "active" and doc.get("approved_by") else None,
                 doc.get("approved_by") if status == "active" else None))


# ---------------------------------------------------------- interpretation


def _book_of(cid: str) -> str:
    return "retail" if cid.upper().startswith("RP") else "corporate"


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.;])\s+(?=[A-Z(])|\n+", text) if s.strip()]


def extract_clauses(text: str, sections: list[tuple[str, str]]) -> list[dict[str, Any]]:
    """Clauses in the text: each clause id with the rule that follows it, up to the next clause id."""
    found: dict[str, dict[str, Any]] = {}
    every = list(CLAUSE_RE.finditer(text))
    # A clause starts a line ("RP-5.1 Significant increase ..."); an id inside a sentence is a cross-reference.
    matches = [m for m in every if not text[text.rfind("\n", 0, m.start()) + 1:m.start()].strip(" \t•-–*#0123456789.()")]
    matches = matches or every
    for i, m in enumerate(matches):
        cid = f"{m.group(1).upper()}-{m.group(2)}.{m.group(3)}"
        end = matches[i + 1].start() if i + 1 < len(matches) else min(len(text), m.end() + 1200)
        chunk = text[m.end():end].strip(" :.-–—\n\t")
        if len(chunk) < 25:  # a cross-reference ("under RP-4.2"), not the clause itself
            continue
        lines = [ln.strip() for ln in chunk.splitlines() if ln.strip()]
        title = lines[0] if lines and len(lines[0]) < 80 and not lines[0].endswith(".") else ""
        rule = " ".join(lines[1:] if title else lines)
        rule = re.split(r"\n\s*\n", rule)[0][:1200].strip()
        if cid in found and len(found[cid]["rule"]) >= len(rule):
            continue
        found[cid] = {"clause": cid, "title": title, "rule": rule}
    if not found:  # no ids: each section with a threshold becomes a proposed clause
        n = 1
        for head, body in sections:
            if THRESH_RE.search(body):
                book = "retail" if re.search(r"retail|consumer|card|mortgage|salar", body, re.I) else "corporate"
                cid = f"{'RP' if book == 'retail' else 'CP'}-9.{n}"
                found[cid] = {"clause": cid, "title": head[:80], "rule": body[:1200], "section": cid.split(".")[0],
                              "section_title": "Circular provisions"}
                n += 1
    return list(found.values())


def interpret(con: sqlite3.Connection, text: str, sections: list[tuple[str, str]], title: str) -> tuple[
        dict[str, Any], list[dict[str, Any]]]:
    return interpret_against(active(con)["pack"], text, sections, title)


def interpret_against(current: dict[str, Any], text: str, sections: list[tuple[str, str]], title: str) -> tuple[
        dict[str, Any], list[dict[str, Any]]]:
    held = {c["clause"]: c for b in ("retail", "corporate") for c in _flat(current, b)}
    found = extract_clauses(text, sections)
    clauses_out, changes, stored = [], [], []
    for c in found:
        cid = c["clause"]
        book = _book_of(cid)
        cur = held.get(cid)
        rule = c["rule"]
        th = [t.strip() for t in THRESH_RE.findall(rule)]
        limit = next((t for t in th if "%" in t or "SAR" in t.upper() or "per cent" in t), None)
        threshold = ", ".join(t for t in th if t != limit) or None
        scope_words = [seg for seg, words in circulars.SEGMENT_WORDS.items() if any(w in rule.lower() for w in words)]
        same = cur is not None and re.sub(r"\W+", " ", cur["rule"]).strip().lower() == re.sub(r"\W+", " ", rule).strip().lower()
        change = "unchanged" if same else ("amends" if cur else "new")
        title_ = c.get("title") or (cur or {}).get("title") or "Clause"
        clauses_out.append({"clause_id": cid, "title": title_, "rule": rule, "limit": limit, "threshold": threshold,
                            "scope": ", ".join(scope_words) or ("Retail book" if book == "retail" else "Corporate book"),
                            "book": book, "change": change, "current_rule": cur["rule"] if cur else None})
        if change != "unchanged":
            changes.append({"clause_id": cid, "before": cur["rule"] if cur else None, "after": rule,
                            "effect": (f"Replaces {cid} ({cur['title']}) in the {book} policy." if cur else
                                       f"Adds {cid} to the {book} policy.")})
        entry = {"clause": cid, "book": book, "section": c.get("section") or cid.split(".")[0],
                 "section_title": c.get("section_title") or next(
                     (s["title"] for s in current["books"][book]["sections"] if s["section"] == cid.split(".")[0]), ""),
                 "title": title_, "rule": rule, "thresholds": {}, "applies_to": (cur or {}).get("applies_to", []),
                 "owner": (cur or {}).get("owner", "Chief Credit Officer"), "last_reviewed": date.today().isoformat(),
                 "levers": (cur or {}).get("levers", []),
                 "summary": f"{cid} now reads: {_sentences(rule)[0][:160]}" if cur else f"{cid} adds: {_sentences(rule)[0][:160]}",
                 **({"previous": cur["rule"]} if cur else {})}
        stored.append(entry)
    low = text.lower()
    books = sorted({c["book"] for c in clauses_out}) or sorted(
        {b for b, w in (("retail", ("retail", "consumer", "card")), ("corporate", ("corporate", "contractor", "sector")))
         if any(x in low for x in w)})
    segs = sorted({seg for seg, words in circulars.SEGMENT_WORDS.items() if any(w in low for w in words)})
    rules = []
    for words, rid, name, book in circulars.EWS_RULES:
        if book in books and any(w in low for w in words) and rid not in {r["rule_id"] for r in rules}:
            hit = next(w for w in words if w in low)
            rules.append({"rule_id": rid, "name": name, "why": f"The document changes a trigger on “{hit}”, which this "
                                                                   f"rule reads in the {book} book."})
    n_new = sum(1 for c in clauses_out if c["change"] == "new")
    n_am = sum(1 for c in clauses_out if c["change"] == "amends")
    first = next((s for s in _sentences(text) if len(s) > 60), "")[:400]
    summary = (f"{title}: {len(clauses_out)} clause{'s' if len(clauses_out) != 1 else ''} found "
               f"({n_am} amending the policy in force, {n_new} new"
               f"{', ' + str(len(clauses_out) - n_am - n_new) + ' unchanged' if len(clauses_out) - n_am - n_new else ''}). "
               + (first if first else ""))
    interp = {"summary": store.clean_text(store.BANNED.sub("[label removed]", summary), "Summary", 2000),
              "clauses": clauses_out, "changes": changes,
              "affects": {"books": books, "segments": segs, "ews_rules": rules},
              "question": "Add this to the Cockpit?", "method": "rules"}
    return interp, stored


def upload(con: sqlite3.Connection, who: str, name: str, data: bytes, title: str = "", kind: str = "",
           reference: str = "") -> dict[str, Any]:
    from backend.playbook_v5 import ingest

    text, sections = ingest.text_of(name, data)
    text = ingest.clean(text)
    if not text.strip():
        raise store.Invalid("No text was found in that file.")
    title = store.clean_text(ingest.clean(title or (sections[0][0] if sections else name)), "Title", 200) or name
    m = re.search(r"\b(C-\d{4}-\d{2})\b", text)
    reference = reference or (m.group(1) if m else "")
    kind = kind if kind in ("policy", "circular", "guideline") else ("circular" if "circular" in text.lower()[:2000] else "policy")
    interp, clauses = interpret(con, text, sections, title)
    doc_id = store.new_id("pd")
    books = interp["affects"]["books"]
    insert_document(con, {"id": doc_id, "title": title, "kind": kind, "reference": reference,
                          "book": "both" if len(books) > 1 else (books[0] if books else ""), "summary": interp["summary"],
                          "text": text[:200_000], "clauses": clauses}, who, "pending", interp)
    store.save_file(con, who, "policy", doc_id, name, _ctype(name), data)
    return {"document": document(con, doc_id), "interpretation": interp}


def _ctype(name: str) -> str:
    n = name.lower()
    return ("application/vnd.openxmlformats-officedocument.wordprocessingml.document" if n.endswith(".docx")
            else "application/pdf" if n.endswith(".pdf") else "text/plain")


def decide(con: sqlite3.Connection, who: str, doc_id: str, add: bool, effective_from: str | None = None,
           approver: str | None = None, note: str = "") -> dict[str, Any]:
    d = doc_dict(con, doc_id)
    if d["status"] != "pending":
        raise store.Invalid(f"This document is {d['status']}; only a pending document can be decided.")
    note = store.clean_text(note, "Note", 2000)
    if not add:
        con.execute("UPDATE policy_documents SET status='rejected', decided_at=?, decided_by=?, decision_note=? WHERE id=?",
                    (store.now(), who, note, doc_id))
        return {"document": document(con, doc_id), "pack": {**active(con), "pack": shown(active(con)["pack"])}}
    if not d["clauses"]:
        raise store.Invalid("No clauses were found in this document, so there is nothing to add to the Cockpit.")
    eff = effective_from or date.today().isoformat()
    store._check_date(eff, "effective_from")
    approver = store.check_users([approver or who], "approver")[0]
    con.execute("UPDATE policy_documents SET status='active', effective_from=?, approved_by=?, decided_at=?, "
                "decided_by=?, decision_note=? WHERE id=?", (eff, approver, store.now(), who, note, doc_id))
    current = store._l(active_version(con)["documents"], [])
    pack = new_version(con, who, [*current, doc_id], f"Added {d['reference'] or d['title']}", eff, approver)
    return {"document": document(con, doc_id), "pack": pack}


def withdraw(con: sqlite3.Connection, who: str, doc_id: str, note: str = "") -> dict[str, Any]:
    d = doc_dict(con, doc_id)
    current = store._l(active_version(con)["documents"], [])
    if d["status"] != "active" or doc_id not in current:
        raise store.Invalid("Only a document that is in the active pack can be withdrawn.")
    note = store.clean_text(note, "Note", 2000)
    con.execute("UPDATE policy_documents SET status='withdrawn', decided_at=?, decided_by=?, decision_note=? WHERE id=?",
                (store.now(), who, note, doc_id))
    pack = new_version(con, who, [x for x in current if x != doc_id], f"Withdrew {d['reference'] or d['title']}",
                       date.today().isoformat(), who)
    return {"document": document(con, doc_id), "pack": pack}


# ------------------------------------------------------------------ lookup


def clauses(con: sqlite3.Connection, book: str = "", q: str = "") -> list[dict[str, Any]]:
    pack = active(con)["pack"]
    out = []
    for b in ("corporate", "retail"):
        if book and b != book:
            continue
        out.extend(_clause_out(c, b) for c in _flat(pack, b))
    if book in ("", "regulatory"):
        out.extend(_clause_out(c, "regulatory") for c in regulatory_clauses(pack))
    if q:
        ql = q.lower()
        out = [c for c in out if ql in (c["clause_id"] + " " + c["title"] + " " + c["rule"]).lower()]
    return out


def _date_words(iso: str | None) -> str:
    if not iso:
        return ""
    d = date.fromisoformat(iso)
    return f"{d.day} {d.strftime('%b %Y')}"


def explain(con: sqlite3.Connection, book: str, measure: str, driver: str = "", segment: str = "",
            period: str = "") -> dict[str, Any]:
    if book not in ("corporate", "retail"):
        raise store.Invalid("book is corporate or retail.")
    if measure not in MEASURES:
        raise store.Invalid(f"measure is one of {', '.join(MEASURES)}.")
    act = active(con)
    pack = act["pack"]
    held = {c["clause"]: c for c in _flat(pack, book)}
    ids = list(DRIVER_CLAUSES.get((book, driver), [])) + [c for c in MEASURE_CLAUSES.get((book, measure), [])]
    seen: list[str] = []
    for cid in ids:
        if cid in held and cid not in seen:
            seen.append(cid)
    picked = []
    for cid in seen:
        c = held[cid]
        # A sector watch applies only to its sector.
        if cid == "CP-3.4" and segment and "construction" not in segment.lower():
            continue
        if cid == "CP-3.4" and not segment and measure not in ("ews", "ecl"):
            continue
        # A clause takes effect from its effective date; a period before it is explained by the clause then in force.
        eff = c.get("effective_from")
        if eff and period and _period_end(period) and _period_end(period) < eff:
            base = {x["clause"]: x for x in _flat(default_pack(), book)}.get(cid)
            if base is None:
                continue
            c = base
        picked.append(c)
    # A clause a circular brought in is the more specific explanation: it leads.
    picked = sorted(picked, key=lambda c: 0 if c.get("source") else 1)[:3]
    out_clauses = []
    for c in picked:
        src = c.get("source") or {"doc_id": _base_doc(book), "kind": "policy", "reference": pack["books"][book]["title"]}
        out_clauses.append({"clause_id": c["clause"], "title": c.get("title", ""), "text": c.get("rule", ""),
                            "effective_from": c.get("effective_from") or pack["books"][book].get("approved_on"),
                            "source": src, "approved_by": act["approved_by"]["username"] if act.get("approved_by") and src.get("kind") != "policy" else None,
                            "href": f"/policy-docs?doc={src['doc_id']}&clause={c['clause']}"})
    sentence = None
    if picked:
        c = picked[0]
        if c.get("source") and c.get("summary"):
            ref = c["source"].get("reference") or c["source"]["doc_id"]
            sentence = f"{c['summary']} ({c['source']['kind']} {ref}, effective {_date_words(c.get('effective_from'))})."
        else:
            first = _sentences(c.get("rule", ""))[0] if c.get("rule") else ""
            sentence = f"{c['clause']} ({c.get('title', '')}) applies: {first.rstrip('.')}."
    return {"pack_version": pack.get("pack_version"), "clauses": out_clauses, "sentence": sentence,
            "book": book, "measure": measure, "driver": driver or None}


def _period_end(period: str) -> str | None:
    m = re.fullmatch(r"(\d{4})Q([1-4])", period or "")
    if m:
        return f"{m.group(1)}-{['03-31', '06-30', '09-30', '12-31'][int(m.group(2)) - 1]}"
    m = re.fullmatch(r"(\d{4})-(\d{2})", period or "")
    if m:
        return f"{period}-28"
    return None


def _base_doc(book: str) -> str:
    return "pd_policy_corporate" if book == "corporate" else "pd_policy_retail"
