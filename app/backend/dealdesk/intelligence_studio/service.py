"""Round S: the Intelligence Studio. "Shows how much it has learnt from the RMs, the bank." (Anne, 23 Oct 2026)

Every count is read from the store that holds it, at request time; nothing here writes. A store that is absent (a
round not merged yet, a file never created) gives its section `available: false` and the reason, never a zero
pretending to be a measurement.

    customers     the Deal Desk deal register (dd_deal), the customer files (dd_intake_file) and the customer packs; per
                  customer, which sources the bank holds: deal register, core banking (dd_customer_account,
                  dd_account_conduct), bureau (bureau_entity_report, bureau_cbrbr), group (dd_group_exposure), credit
                  decisions (gov_decision), uploads (dd_intake_*), past proposals (the house-style corpus)
    documents     every document read into a customer file (dd_intake_document), by type and by how it was read
    proposals     the house-style corpus (proposals learned, per bank and kind) and, per analyst: deals, drafts edited,
                  sections accepted, rules written, paper-workspace edits
    rules         Round K's rules store (backend/dealdesk/rules), by author and scope (optional import)
    policies      the policy pack in force (Policy Docs), the policy library (dd_policy) and Round P's approved
                  assessments and thresholds (backend/dealdesk/rulebook, optional)
    reader        per week: documents read, document types the analyst corrected (reader accuracy), cross-document
                  reconciliation (agrees / differs / flag) and, when the model reader reconciles fields (Rounds A, R),
                  the field states (confirmed / offered / flagged)
    corrections   what the system absorbed from people: house-style edits and accepts, document types corrected,
                  rules saved from an instruction, paper-workspace edits by instruction
    governance    the model telemetry (backend/convo/telemetry): calls, tokens (input, output, cached), latency, model,
                  per stage and per day
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable

V5 = Path(__file__).resolve().parents[3]

SOURCES = [
    ("deal_register", "Deal register (LOS)"),
    ("core_banking", "Core banking: accounts and conduct"),
    ("bureau", "Bureau (SIMAH, CBRBR)"),
    ("group", "Group and connected parties"),
    ("credit_history", "Credit decisions (history)"),
    ("uploads", "Uploaded customer documents"),
    ("past_proposals", "Past proposals read"),
]
FIELD_STATES = {"confirmed": "confirmed", "agree": "confirmed", "agrees": "confirmed", "offered": "offered",
                "model_more": "offered", "flagged": "flagged", "disagree": "flagged", "differs": "flagged"}


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe(fn: Callable[[], Any], default: Any = None) -> tuple[Any, str]:
    try:
        return fn(), ""
    except Exception as e:  # noqa: BLE001 - an absent store is reported, never raised
        return default, f"{type(e).__name__}: {str(e)[:160]}"


def _rel(name: str, columns: list[str] | None = None) -> tuple[list[dict[str, Any]], bool]:
    from backend.dealdesk.data.store import dd_read
    rows, err = _safe(lambda: dd_read(name, columns=columns), None)
    return (rows or []), rows is not None and not err


def _week(ts: str) -> str:
    try:
        d = dt.date.fromisoformat(str(ts)[:10])
    except ValueError:
        return ""
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


# ------------------------------------------------------------------ customers and source coverage

def _corpus() -> tuple[list[dict[str, Any]], str]:
    from backend.dealdesk.house_style import store
    docs, err = _safe(store.corpus_docs, None)
    return (docs or []), err


def customers() -> dict[str, Any]:
    deals, ok_deals = _rel("dd_deal", ["proposal_id", "obligor_id", "obligor_name", "source", "rm", "credit_analyst"])
    files, ok_files = _rel("dd_intake_file")
    if not ok_deals and not ok_files:
        return {"available": False, "reason": "Neither the deal register nor the customer files can be read."}
    acc, _ = _rel("dd_customer_account", ["obligor_id"])
    cond, _ = _rel("dd_account_conduct", ["obligor_id"])
    bur1, _ = _rel("bureau_entity_report", ["proposal_id"])
    bur2, _ = _rel("bureau_cbrbr", ["proposal_id"])
    grp, _ = _rel("dd_group_exposure", ["proposal_id"])
    gov, _ = _rel("gov_decision", ["borrower_id"])
    idocs, _ = _rel("dd_intake_document", ["proposal_id", "intake_id"])
    corpus, _ = _corpus()

    core = {r["obligor_id"] for r in acc + cond if r.get("obligor_id")}
    bureau = {r["proposal_id"] for r in bur1 + bur2 if r.get("proposal_id")}
    group = {r["proposal_id"] for r in grp if r.get("proposal_id")}
    history = Counter(r["borrower_id"] for r in gov if r.get("borrower_id"))
    upl = {r["proposal_id"] for r in idocs if r.get("proposal_id")} | \
        {x for r in files for x in (r.get("proposal_id"), r.get("matched_proposal_id")) if x}
    past = {d["doc_id"] for d in corpus}

    by: dict[str, dict[str, Any]] = {}
    for r in deals:
        key = r.get("obligor_id") or r.get("obligor_name") or r["proposal_id"]
        c = by.setdefault(key, {"customer_id": r.get("obligor_id") or "", "name": r.get("obligor_name") or key, "proposals": [],
                                "existing": str(r.get("obligor_id") or "").startswith("CB")})
        c["proposals"].append(r["proposal_id"])
    names = {str(c["name"]).strip().lower(): k for k, c in by.items()}
    for f in files:   # a customer file of someone the register does not know is a customer learnt from the upload
        nm = str(f.get("customer_name") or "").strip()
        if not nm:
            continue
        k = names.get(nm.lower())
        if k is None:
            k = "file:" + f["intake_id"]
            by[k] = {"customer_id": f.get("matched_cif") or "", "name": nm, "proposals": [], "existing": bool(f.get("existing_customer"))}
            names[nm.lower()] = k
        by[k].setdefault("files", []).append(f["intake_id"])

    rows = []
    for k, c in by.items():
        ps = set(c["proposals"])
        src = {"deal_register": bool(ps),
               "core_banking": c["customer_id"] in core,
               "bureau": bool(ps & bureau),
               "group": bool(ps & group),
               "credit_history": history.get(c["customer_id"], 0) > 0,
               "uploads": bool(ps & upl) or bool(c.get("files")),
               "past_proposals": bool(ps & past)}
        rows.append({"customer_id": c["customer_id"], "name": c["name"], "existing": c["existing"],
                     "proposals": sorted(ps), "decisions": history.get(c["customer_id"], 0), "sources": src,
                     "sources_n": sum(src.values())})
    rows.sort(key=lambda r: (-r["sources_n"], r["name"]))
    n = len(rows)
    cov = [{"source": s, "label": lab, "customers": sum(1 for r in rows if r["sources"][s]),
            "pct": round(100.0 * sum(1 for r in rows if r["sources"][s]) / n, 1) if n else 0.0} for s, lab in SOURCES]
    return {"available": True, "total": n, "existing": sum(1 for r in rows if r["existing"]),
            "new_to_bank": sum(1 for r in rows if not r["existing"]), "coverage": cov, "rows": rows[:60],
            "sources": [{"key": s, "label": lab} for s, lab in SOURCES]}


# ------------------------------------------------------------------ documents read

def _intake_states() -> list[dict[str, Any]]:
    from backend.dealdesk.intake import service
    return service._states()  # noqa: SLF001 - read-only listing of the customer files


def documents() -> dict[str, Any]:
    docs, ok = _rel("dd_intake_document")
    if not ok:
        return {"available": False, "reason": "The customer-file documents (dd_intake_document) cannot be read."}
    by_type = Counter((d.get("doc_type") or "unknown", d.get("doc_label") or d.get("doc_type") or "Unknown") for d in docs)
    by_method = Counter(d.get("read_method") or "not read" for d in docs)
    by_kind = Counter(d.get("file_kind") or "other" for d in docs)
    return {"available": True, "total": len(docs), "files": len({d.get("intake_id") for d in docs}),
            "pages": sum(int(d.get("pages") or 0) for d in docs),
            "by_type": [{"doc_type": t, "label": lab, "n": n} for (t, lab), n in by_type.most_common()],
            "by_method": [{"method": m, "n": n} for m, n in by_method.most_common()],
            "by_kind": [{"kind": k, "n": n} for k, n in by_kind.most_common()]}


# ------------------------------------------------------------------ proposals learned, per bank and per analyst

def _house_events() -> list[dict[str, Any]]:
    from backend.dealdesk.house_style import store
    return store.events()


def _rules_store() -> Any:
    from backend.dealdesk.rules import store  # Round K (optional until merged)
    return store


def _paperws_rows(sql: str) -> list[sqlite3.Row] | None:
    try:
        from backend.dealdesk.paperws import store as pws  # Round W (optional until merged)
        p = pws.path()
    except Exception:  # noqa: BLE001
        p = V5 / "var" / "paperws" / "paperws.sqlite"
    if not Path(p).exists():
        return None
    con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        return list(con.execute(sql))
    except sqlite3.Error:
        return None
    finally:
        con.close()


def proposals() -> dict[str, Any]:
    corpus, err = _corpus()
    events, _ = _safe(_house_events, [])
    deals, ok_deals = _rel("dd_deal", ["proposal_id", "rm", "credit_analyst"])
    bank: dict[str, dict[str, Any]] = {}
    for d in corpus:
        b = bank.setdefault(d.get("bank") or "?", {"bank": d.get("bank") or "?", "label": d.get("bank_label") or d.get("bank") or "?",
                                                   "proposals": 0, "kinds": Counter(), "sources": Counter()})
        b["proposals"] += 1
        b["kinds"][d.get("kind") or "?"] += 1
        b["sources"][d.get("source") or "?"] += 1
    uploads = [e for e in events or [] if e.get("type") == "doc"]
    people: dict[str, dict[str, Any]] = defaultdict(lambda: {"deals_as_analyst": 0, "deals_as_rm": 0, "sections_edited": 0,
                                                             "sections_accepted": 0, "rules": 0, "paper_edits": 0})
    for r in deals:
        if r.get("credit_analyst"):
            people[r["credit_analyst"]]["deals_as_analyst"] += 1
        if r.get("rm"):
            people[r["rm"]]["deals_as_rm"] += 1
    for e in events or []:
        if e.get("type") == "edit" and e.get("by"):
            people[e["by"]]["sections_accepted" if e.get("accepted") else "sections_edited"] += 1
    rs, _ = _safe(lambda: _rules_store().listing(status="active"), None)
    for r in rs or []:
        people[r.get("author_name") or r.get("author") or "?"]["rules"] += 1
    for r in _paperws_rows("SELECT author, COUNT(*) AS n FROM versions WHERE action IN ('edit','structure') GROUP BY author") or []:
        if r["author"]:
            people[r["author"]]["paper_edits"] += r["n"]
    analysts = [{"person": k, **v, "total": sum(v.values())} for k, v in people.items()]
    analysts.sort(key=lambda x: (-x["total"], x["person"]))
    return {"available": bool(corpus) or ok_deals, "reason": err if not corpus else "",
            "learned": len(corpus), "uploaded": len(uploads),
            "by_bank": [{"bank": b["bank"], "label": b["label"], "proposals": b["proposals"], "kinds": dict(b["kinds"]),
                         "sources": dict(b["sources"])} for b in sorted(bank.values(), key=lambda x: -x["proposals"])],
            "by_analyst": analysts[:40]}


# ------------------------------------------------------------------ rules by author (Round K)

def rules() -> dict[str, Any]:
    st, err = _safe(_rules_store, None)
    if st is None:
        return {"available": False, "reason": "Analysts' rules arrive with Round K (backend/dealdesk/rules); not in this build yet."}
    rows, err = _safe(lambda: st.listing(status="active"), None)
    if rows is None:
        return {"available": False, "reason": f"The rules store could not be read ({err})."}
    by: dict[str, dict[str, Any]] = {}
    for r in rows:
        a = by.setdefault(r.get("author") or "?", {"author": r.get("author") or "?", "name": r.get("author_name") or r.get("author") or "?",
                                                  "rules": 0, "me": 0, "team": 0, "bank": 0, "from_instruction": 0, "last": ""})
        a["rules"] += 1
        a[r.get("scope") if r.get("scope") in ("me", "team", "bank") else "me"] += 1
        a["from_instruction"] += 1 if (r.get("source_instruction") or "").strip() else 0
        a["last"] = max(a["last"], str(r.get("updated_at") or r.get("created_at") or ""))
    recent = sorted(rows, key=lambda r: str(r.get("created_at") or ""), reverse=True)[:8]
    return {"available": True, "total": len(rows), "by_scope": dict(Counter(r.get("scope") for r in rows)),
            "by_author": sorted(by.values(), key=lambda a: (-a["rules"], a["name"])),
            "recent": [{"id": r.get("id"), "text": r.get("text"), "scope": r.get("scope"), "author": r.get("author_name") or r.get("author"),
                        "created_at": r.get("created_at"), "section": r.get("section_label") or r.get("section")} for r in recent]}


# ------------------------------------------------------------------ policies in force

def policies() -> dict[str, Any]:
    from backend.playbook_v5 import policy
    pack, err = _safe(policy.active_pack_file, None)
    out: dict[str, Any] = {"available": pack is not None, "reason": err}
    if pack:
        books = []
        for k, b in (pack.get("books") or {}).items():
            n = 0
            for s in b.get("sections") or []:
                n += len(s.get("clauses") or []) if isinstance(s, dict) else 0
            books.append({"book": k, "title": b.get("title") or k, "approved_by": b.get("approved_by"), "approved_on": b.get("approved_on"),
                          "next_review": b.get("next_review"), "clauses": n})
        regs = [{"key": k, "title": r.get("title") or k, "issuer": r.get("issuer"), "effective_from": r.get("effective_from"),
                 "clauses": len(r.get("clauses") or [])} for k, r in (pack.get("regulatory") or {}).items()]
        out.update({"pack_version": pack.get("pack_version"), "books": books, "regulatory": regs,
                    "clauses": sum(b["clauses"] for b in books) + sum(r["clauses"] for r in regs)})
    lib, ok = _rel("dd_policy")
    out["library"] = [{"policy_id": r.get("policy_id"), "version": r.get("version"), "title": r.get("title"), "status": r.get("status"),
                       "effective_date": r.get("effective_date"), "clauses": r.get("clauses_n")} for r in lib] if ok else []

    def rulebook() -> dict[str, Any]:
        from backend.dealdesk.rulebook import store as rb  # Round P (optional until merged)
        a = rb.assessments()
        return {"assessments": len(a), "approved": sum(1 for x in a if str(x.get("status")).lower() in ("approved", "applied", "active")),
                "by_kind": dict(Counter(x.get("kind") for x in a)), "thresholds": len(rb.thresholds()), "gold": len(rb.golds()),
                "open_flags": len(rb.flags())}
    rb, rerr = _safe(rulebook, None)
    out["rulebook"] = rb if rb is not None else {"available": False,
                                                 "reason": "Policy Docs' four kinds arrive with Round P (backend/dealdesk/rulebook)."}
    out["available"] = bool(out["available"] or out["library"] or rb)
    return out


# ------------------------------------------------------------------ reader accuracy vs analyst confirmations

def reader() -> dict[str, Any]:
    states, err = _safe(_intake_states, None)
    recon, ok_recon = _rel("dd_intake_reconciliation", ["intake_id", "status"])
    files, _ = _rel("dd_intake_file", ["intake_id", "created_at"])
    if states is None and not ok_recon:
        return {"available": False, "reason": "No customer-file store can be read."}
    created = {f["intake_id"]: f.get("created_at") or "" for f in files}
    weeks: dict[str, dict[str, Any]] = defaultdict(lambda: {"documents": 0, "readable": 0, "corrected": 0, "recon_agrees": 0,
                                                            "recon_differs": 0, "recon_flags": 0, "fields_confirmed": 0,
                                                            "fields_offered": 0, "fields_flagged": 0, "fields_read": 0})
    seen_docs = set()
    for st in states or []:
        wk = _week(st.get("created_at") or created.get(st.get("intake_id"), ""))
        for d in st.get("documents") or []:
            seen_docs.add(d.get("doc_id"))
            w = weeks[wk]
            w["documents"] += 1
            if d.get("doc_type") in ("unreadable",) or d.get("error"):
                continue
            w["readable"] += 1
            if "set by the user" in (d.get("why") or []) or d.get("corrected_by"):
                w["corrected"] += 1
            for f in (d.get("fields") or {}).values():
                if not isinstance(f, dict):
                    continue
                w["fields_read"] += 1
                s = FIELD_STATES.get(str(f.get("state") or f.get("reconciled") or "").lower())
                if s:
                    w[f"fields_{s}"] += 1
    if states is not None:   # the seeded rows of the relation (no state file) still count as documents read
        docs, _ = _rel("dd_intake_document", ["doc_id", "intake_id", "doc_type"])
        for d in docs:
            if d["doc_id"] not in seen_docs:
                w = weeks[_week(created.get(d["intake_id"], ""))]
                w["documents"] += 1
                if d.get("doc_type") != "unreadable":
                    w["readable"] += 1
    for r in recon:
        w = weeks[_week(created.get(r["intake_id"], ""))]
        k = {"agrees": "recon_agrees", "differs": "recon_differs", "flag": "recon_flags"}.get(str(r.get("status")))
        if k:
            w[k] += 1
    periods = []
    for wk in sorted(weeks):
        w = weeks[wk]
        acc = round(100.0 * (w["readable"] - w["corrected"]) / w["readable"], 1) if w["readable"] else None
        fx = w["fields_confirmed"] + w["fields_offered"] + w["fields_flagged"]
        periods.append({"period": wk or "undated", **w, "reader_accuracy_pct": acc,
                        "field_agreement_pct": round(100.0 * w["fields_confirmed"] / fx, 1) if fx else None})
    tot = {k: sum(p[k] for p in periods) for k in ("documents", "readable", "corrected", "recon_agrees", "recon_differs", "recon_flags",
                                                   "fields_read", "fields_confirmed", "fields_offered", "fields_flagged")}
    tot["reader_accuracy_pct"] = round(100.0 * (tot["readable"] - tot["corrected"]) / tot["readable"], 1) if tot["readable"] else None
    fx = tot["fields_confirmed"] + tot["fields_offered"] + tot["fields_flagged"]
    tot["field_agreement_pct"] = round(100.0 * tot["fields_confirmed"] / fx, 1) if fx else None
    return {"available": True, "periods": periods, "totals": tot, "field_states": fx > 0}


# ------------------------------------------------------------------ corrections absorbed

def corrections() -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    sources: dict[str, bool] = {}
    events, err = _safe(_house_events, None)
    sources["house_style"] = events is not None
    for e in events or []:
        if e.get("type") == "edit":
            items.append({"kind": "accept" if e.get("accepted") else "edit", "at": e.get("at") or "", "by": e.get("by") or "",
                          "what": f"{'Accepted' if e.get('accepted') else 'Edited'} the {str(e.get('section') or '').replace('_', ' ')} "
                                  f"section ({e.get('bank') or ''} house style)"})
    states, _ = _safe(_intake_states, None)
    sources["customer_files"] = states is not None
    for st in states or []:
        for d in st.get("documents") or []:
            if "set by the user" in (d.get("why") or []):
                items.append({"kind": "doc_type", "at": d.get("read_at") or st.get("created_at") or "", "by": st.get("created_by") or "",
                              "what": f"Document type corrected to {d.get('doc_label') or d.get('doc_type')} ({d.get('file_name')})"})
    rs, _ = _safe(lambda: _rules_store().listing(status="active"), None)
    sources["rules"] = rs is not None
    for r in rs or []:
        if (r.get("source_instruction") or "").strip():
            items.append({"kind": "rule", "at": r.get("created_at") or "", "by": r.get("author_name") or r.get("author") or "",
                          "what": f"Saved as a rule ({r.get('scope')}): {str(r.get('text') or '')[:120]}"})
    pw = _paperws_rows("SELECT author, at, instruction, section FROM versions WHERE action = 'edit' ORDER BY at DESC LIMIT 400")
    sources["paper_workspace"] = pw is not None
    for r in pw or []:
        at = dt.datetime.fromtimestamp(float(r["at"]), dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if r["at"] else ""
        items.append({"kind": "paper_edit", "at": at, "by": r["author"] or "",
                      "what": f"Changed {r['section'] or 'the paper'} by instruction: {str(r['instruction'] or '')[:120]}"})
    label = {"edit": "House-style edits", "accept": "Sections accepted as written", "doc_type": "Document types corrected",
             "rule": "Rules saved from an instruction", "paper_edit": "Paper edits by instruction"}
    by_kind = Counter(i["kind"] for i in items)
    items.sort(key=lambda i: str(i["at"]), reverse=True)
    return {"available": any(sources.values()), "sources": sources, "total": len(items),
            "by_kind": [{"kind": k, "label": label[k], "n": by_kind.get(k, 0)} for k in label],
            "by_week": [{"period": k, "n": v} for k, v in sorted(Counter(_week(i["at"]) or "undated" for i in items).items())],
            "recent": items[:12]}


# ------------------------------------------------------------------ model governance

def governance(module: str = "") -> dict[str, Any]:
    from backend.convo import efficiency, telemetry
    if not telemetry.db_path().exists():
        return {"available": False, "reason": "No model call has been recorded yet (backend/convo/telemetry).",
                "efficiency": efficiency.enabled()}
    where = {"module": module} if module else None
    by_stage = telemetry.summary(("purpose", "model"), where)
    by_model = telemetry.summary(("provider", "model"), where)
    rows = telemetry.rows(where, limit=20000)
    lat = sorted(int(r["ms"]) for r in rows if r.get("ms") is not None)
    q = (lambda p: lat[min(len(lat) - 1, round(p * (len(lat) - 1)))] if lat else None)  # noqa: E731
    days: dict[str, dict[str, int]] = defaultdict(lambda: {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cached_tokens": 0})
    for r in rows:
        d = days[str(r.get("at") or "")[:10]]
        d["calls"] += 1
        for k in ("input_tokens", "output_tokens", "cached_tokens"):
            d[k] += int(r.get(k) or 0)
    runs = telemetry.per_run(where)
    tot = {"calls": len(rows), "ok": sum(1 for r in rows if r.get("ok")), "input_tokens": sum(int(r.get("input_tokens") or 0) for r in rows),
           "output_tokens": sum(int(r.get("output_tokens") or 0) for r in rows),
           "cached_tokens": sum(int(r.get("cached_tokens") or 0) for r in rows),
           "p50_ms": q(0.5), "p95_ms": q(0.95), "turns": len(runs),
           "calls_per_turn": round(len(rows) / len(runs), 2) if runs else None,
           "input_per_turn": round(sum(int(r.get("input_tokens") or 0) + int(r.get("cached_tokens") or 0) for r in rows) / len(runs)) if runs else None,
           "models": sorted({r.get("model") for r in rows if r.get("model")})}
    return {"available": True, "module": module, "totals": tot, "by_stage": by_stage, "by_model": by_model,
            "by_day": [{"day": k, **v} for k, v in sorted(days.items())][-30:],
            "modules": sorted({r.get("module") for r in rows if r.get("module")}), "efficiency": efficiency.enabled()}


# ------------------------------------------------------------------ the page

def _n(n: int, one: str, many: str = "") -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


def overview(module: str = "") -> dict[str, Any]:
    parts: dict[str, Any] = {}
    for key, fn in (("customers", customers), ("documents", documents), ("proposals", proposals), ("rules", rules),
                    ("policies", policies), ("reader", reader), ("corrections", corrections)):
        val, err = _safe(fn, None)
        parts[key] = val if val is not None else {"available": False, "reason": err}
    gov, err = _safe(lambda: governance(module), None)
    parts["governance"] = gov if gov is not None else {"available": False, "reason": err}
    c, d, p, r, pol, rd, cor, g = (parts[k] for k in ("customers", "documents", "proposals", "rules", "policies", "reader", "corrections",
                                                       "governance"))
    head = {"customers": c.get("total") if c.get("available") else None,
            "documents_read": d.get("total") if d.get("available") else None,
            "proposals_learned": p.get("learned") if p.get("available") else None,
            "rules_active": r.get("total") if r.get("available") else None,
            "policy_clauses": pol.get("clauses") if pol.get("available") else None,
            "corrections_absorbed": cor.get("total") if cor.get("available") else None,
            "reader_accuracy_pct": (rd.get("totals") or {}).get("reader_accuracy_pct") if rd.get("available") else None,
            "model_calls": (g.get("totals") or {}).get("calls") if g.get("available") else None}
    words = []
    if c.get("available"):
        full = sum(1 for x in c["rows"] if x["sources_n"] >= 4)
        words.append(f"CreditProbe knows {_n(c['total'], 'customer')} ({c['existing']} existing, {c['new_to_bank']} new to the bank); "
                     f"{full} of them from four or more sources.")
    if d.get("available"):
        words.append(f"It has read {_n(d['total'], 'customer document')} in {_n(d['files'], 'customer file')}"
                     + (f", most often {d['by_type'][0]['label']}." if d["by_type"] else "."))
    if p.get("available"):
        words.append(f"It writes from {_n(p['learned'], 'proposal')} learned across {_n(len(p['by_bank']), 'house style')}"
                     + (f", {p['uploaded']} of them uploaded by the bank." if p["uploaded"] else "."))
    if r.get("available"):
        words.append(f"{_n(r['total'], 'analyst rule')} in force, from {_n(len(r['by_author']), 'author')}.")
    if pol.get("available") and pol.get("pack_version"):
        words.append(f"Policy pack {pol['pack_version']} is in force: {_n(pol.get('clauses', 0), 'clause')} across "
                     f"{_n(len(pol.get('books') or []), 'credit policy book')} and {_n(len(pol.get('regulatory') or []), 'regulation')}.")
    if cor.get("available"):
        words.append(f"{_n(cor['total'], 'correction')} from people absorbed" + (
            f"; the reader's document types were kept as read for {rd['totals']['reader_accuracy_pct']:g}% of documents."
            if rd.get("available") and (rd.get("totals") or {}).get("reader_accuracy_pct") is not None else "."))
    if g.get("available"):
        t = g["totals"]
        words.append(f"{_n(t['calls'], 'model call')} on record ({_n(t['turns'], 'turn')}), every one measured.")
    return {"as_of": _now(), "headline": head, "plain_words": words, **parts}


__all__ = ["overview", "customers", "documents", "proposals", "rules", "policies", "reader", "corrections", "governance", "SOURCES"]
