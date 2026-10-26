"""R16 i: the customer file. Upload the customer's documents (several at once, any mix of Word, PDF and photos),
read and classify each one, extract its fields, judge the checklist, reconcile across documents and the Bank's data, and
publish everything to Data Domains.

    open_file(files, by, as_of)        new customer file from a first batch of files → the file view
    add_files(iid, files)              more documents into the same file
    get(iid)                           the file view (documents, checklist, reconciliation, bank pull, plain words)
    attach(iid, proposal_id)           the deal created from the file; rows re-published with its proposal_id
    by_deal(proposal_id)               the latest file attached to a deal (or None)
    facts(iid | proposal_id)           the normalised customer file for the business-request and credit-response writers
    remove_document(iid, doc_id), delete(iid)

State lives under var/dealdesk/intake/<iid>/ (the files and state.jsonl, one JSON line); the Data Domains rows are the published view.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import shutil
import threading
import uuid
from pathlib import Path
from typing import Any

from backend.dealdesk.intake import bank as BANK
from backend.dealdesk.intake import checklist as CL
from backend.dealdesk.intake import reconcile as RC
from backend.dealdesk.intake import reader as RD
from backend.dealdesk.intake.doctypes import BY_CODE
from backend.dealdesk.intake.extract import classify, extract, norm, title_of

V5 = Path(__file__).resolve().parents[3]
_LOCK = threading.RLock()
ACTOR = "R16-i:intake"
RELS = ("dd_intake_file", "dd_intake_document", "dd_intake_field", "dd_intake_check", "dd_intake_reconciliation")


class IntakeError(ValueError):
    pass


def root() -> Path:
    p = Path(os.environ.get("DEALDESK_INTAKE_ROOT") or (V5 / "var" / "dealdesk" / "intake"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def as_of_default() -> dt.date:
    v = os.environ.get("CP_INTAKE_AS_OF", "").strip()
    if v:
        return dt.date.fromisoformat(v)
    return dt.date.today()


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _dir(iid: str) -> Path:
    if not re.fullmatch(r"IN-[A-Z0-9\-]{4,40}", iid or ""):
        raise IntakeError(f"No such customer file: {iid}")
    return root() / iid


def _load(iid: str) -> dict[str, Any]:
    p = _dir(iid) / "state.jsonl"
    if not p.exists():
        raise IntakeError(f"No such customer file: {iid}")
    return json.loads(p.read_text())


def _save(st: dict[str, Any]) -> None:
    d = _dir(st["intake_id"])
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / "state.jsonl.tmp"
    tmp.write_text(json.dumps(st, default=str))
    tmp.replace(d / "state.jsonl")


# ------------------------------------------------------------------------------------------------ reading one file
def subject_of(doc: dict[str, Any]) -> str:
    code = doc.get("doc_type") or ""
    d = BY_CODE.get(code)
    f = doc.get("fields") or {}

    def v(k: str) -> str:
        x = f.get(k)
        return str(x["value"]) if isinstance(x, dict) and x.get("value") not in (None, "") else ""
    if d is None:
        return ""
    if d.per in ("owner", "guarantor"):
        return v("full_name")
    if d.per == "bank":
        return v("bank_name")
    if d.per == "account":
        acct = re.sub(r"\D", "", v("account_number"))
        return f"{v('bank_name')} …{acct[-4:]}" if acct else v("bank_name")
    if d.per == "project":
        return v("project_id")
    if d.per == "certificate":
        return " ".join(x for x in (v("project_id"), "IPC " + v("certificate_number") if v("certificate_number") else "") if x)
    if d.per == "period":
        if code == "audited_fs":
            return "FY" + v("fiscal_year")[:4] if v("fiscal_year") else ""
        return f"{v('period_from')} to {v('period_to')}".strip(" to")
    if d.per == "collateral":
        return v("deed_number") or v("property") or v("policy_number")
    return "company"


_PAGE = re.compile(r"^(?P<stem>.+?)[_\- ]p(?:age)?[_\- ]?(?P<n>\d{1,2})$", re.I)


def page_stem(name: str) -> tuple[str, int]:
    """'13_audited_fs__fy2025_p2.jpg' → ('13_audited_fs__fy2025', 2); a single file → (name, 0)."""
    stem = Path(name).stem
    m = _PAGE.match(stem)
    if m and RD.kind_of(name) == "image":
        return m.group("stem"), int(m.group("n"))
    return Path(name).name, 0


def _year_fallback(doc: dict[str, Any], names: list[str]) -> None:
    """A photographed statements page without the header: the year from the page itself, else from the file name."""
    if doc.get("doc_type") != "audited_fs" or (doc.get("fields") or {}).get("fiscal_year"):
        return
    text = " ".join(doc.get("lines") or [])
    m = re.search(r"31\s*/\s*12\s*/\s*(20\d\d)", text) or re.search(r"(?i)\bFY\s?(20\d\d)\b", text) or \
        re.search(r"(?i)fy(20\d\d)", " ".join(names)) or re.search(r"\b(20\d\d)\b\s*\|?\s*\b20\d\d\b", text)
    if m:
        doc["fields"]["fiscal_year"] = {"value": f"{m.group(1)}-12-31", "label": "Financial year ended", "type": "date", "line": 0,
                                        "raw": "inferred from the page or the file name"}


def _analyse(doc: dict[str, Any], names: list[str]) -> dict[str, Any]:
    lines = doc.get("lines") or []
    c = classify(" ".join(names), lines)
    doc.update(doc_type=c["doc_type"], doc_label=c["label"], confidence=c["confidence"], why=c["why"], title=title_of(lines))
    doc["fields"] = extract(c["doc_type"], lines, doc.get("spans")) if c["doc_type"] != "unknown" else {}
    _year_fallback(doc, names)
    doc["subject"] = subject_of(doc)
    return doc


def read_pages(pages: list[tuple[str, bytes]], doc_id: str) -> dict[str, Any]:
    """One document from one file, or from several photographed pages of it (read in page order, text joined)."""
    name0 = Path(pages[0][0]).name
    shas = [hashlib.sha256(d).hexdigest() for _, d in pages]
    stem = page_stem(name0)[0]
    label = name0 if len(pages) == 1 else f"{stem} (pages {', '.join(str(page_stem(n)[1]) for n, _ in pages)})"
    base = {"doc_id": doc_id, "file_name": label, "sha256": shas[0], "page_shas": shas, "page_files": [Path(n).name for n, _ in pages],
            "page_stem": stem if len(pages) > 1 or page_stem(name0)[1] else "", "size": sum(len(d) for _, d in pages), "read_at": _now()}
    lines: list[str] = []
    spans: list[Any] | None = []
    meta: dict[str, Any] = {}
    errors: list[str] = []
    for name, data in pages:
        try:
            r = RD.read(name, data)
        except RD.ReadError as e:
            errors.append(str(e))
            continue
        lines.extend(r["lines"])
        if spans is not None and r.get("spans") is not None:
            spans.extend(r["spans"])
        else:
            spans = None
        meta = meta or {"file_kind": r["kind"], "read_method": r["method"], "ocr_engine": r["ocr_engine"]}
        meta["pages"] = meta.get("pages", 0) + r["pages"]
    if not lines:
        return {**base, "error": errors[0] if errors else "no text could be read", "doc_type": "unreadable", "doc_label": "Could not be read",
                "confidence": 0.0, "fields": {}, "lines": [], "file_kind": RD.kind_of(name0), "read_method": "", "ocr_engine": "", "pages": 0}
    doc = {**base, **meta, "characters": sum(len(x) for x in lines), "lines": lines, "spans": spans if spans else None}
    return _analyse(doc, [n for n, _ in pages])


def read_one(name: str, data: bytes, doc_id: str) -> dict[str, Any]:
    return read_pages([(name, data)], doc_id)


# ------------------------------------------------------------------------------------------------ the file view
def _profile(docs: list[dict[str, Any]]) -> dict[str, Any]:
    names: dict[str, list[str]] = {}
    crs: dict[str, int] = {}
    for d in docs:
        n = CL.fv(d, "customer_name")
        if n:
            names.setdefault(norm(n), []).append(str(n))
        c = re.sub(r"\D", "", str(CL.fv(d, "cr_number") or ""))
        if len(c) >= 8:
            crs[c] = crs.get(c, 0) + 1
    name = ""
    if names:
        key = max(names, key=lambda k: len(names[k]))
        # the spelling with the most spaces wins (OCR may have dropped some)
        name = max(names[key], key=lambda s: (s.count(" "), len(s)))
    cr = max(crs, key=crs.get) if crs else ""
    city = activity = legal = sector = ""
    for d in docs:
        if d.get("doc_type") == "commercial_registration":
            city, activity, legal = (str(CL.fv(d, k) or "") for k in ("city", "activity", "legal_form"))
    contractor = any(d.get("doc_type") in ("project_list", "project_contract", "payment_certificate") for d in docs) or bool(
        re.search(r"(?i)contract|construct|building works|civil", activity))
    low = activity.lower()
    sector = ("Construction" if contractor else "Manufacturing" if re.search(r"manufactur|industr|polymer|plastic|factory", low)
              else "Wholesale Trade" if re.search(r"trad|wholesale|distribut|import", low) else "Services" if low else "")
    return {"customer_name": name, "cr_number": cr, "city": city, "activity": activity, "legal_form": legal, "sector": sector,
            "contractor": contractor}


def _plain(view: dict[str, Any]) -> list[str]:
    c = view["counts"]
    p = view["profile"]
    b = view["bank"]
    flags = [t for t in view["reconciliation"] if t["severity"] >= 2]
    lines = [f"We read {view['documents_n']} files for {p.get('customer_name') or 'the customer'}"
             + (f" (CR {p['cr_number']})" if p.get("cr_number") else "") + f": {view['by_method_text']}.",
             f"Checklist: {c['received']} of {c['required']} required documents received, {c['missing']} missing, {c['expired']} expired.",
             (f"Already a customer of the Bank ({b.get('how')}): accounts, conduct, facilities and group are pulled below."
              if b.get("existing") else "New to the Bank: no account or deal carries this CR number."),
             (f"{len(flags)} things to ask about when the documents are read together, the first: {flags[0]['title'].rstrip('.')}."
              if flags else "The key figures agree across the documents.")]
    return lines


def view(st: dict[str, Any]) -> dict[str, Any]:
    as_of = dt.date.fromisoformat(st["as_of"])
    docs = [d for d in st["documents"] if d.get("doc_type") not in ("unreadable",)]
    prof = _profile(docs)
    m = BANK.match(prof["cr_number"], prof["customer_name"]) if (prof["cr_number"] or prof["customer_name"]) else None
    bank = BANK.pull(m, as_of) if m else BANK.not_found(prof["cr_number"], prof["customer_name"])
    lines = CL.build(docs, as_of, contractor=prof["contractor"], existing=bool(bank.get("existing")))
    for d in docs:
        s, why, until = CL.doc_status(d, as_of)
        d["status"], d["status_reason"], d["valid_until"] = s, why, until
    recon = RC.run(docs, prof, bank, as_of)
    by_method: dict[str, int] = {}
    for d in st["documents"]:
        by_method[d.get("read_method") or "not read"] = by_method.get(d.get("read_method") or "not read", 0) + 1
    out = {
        "intake_id": st["intake_id"], "proposal_id": st.get("proposal_id") or "", "as_of": st["as_of"], "created_at": st["created_at"],
        "created_by": st.get("created_by") or "", "profile": prof, "bank": bank, "documents_n": len(st["documents"]),
        "by_method": by_method, "by_method_text": ", ".join(f"{n} {k}" for k, n in sorted(by_method.items(), key=lambda kv: -kv[1])),
        "documents": [{k: d.get(k) for k in ("doc_id", "file_name", "page_files", "file_kind", "read_method", "ocr_engine", "pages", "title", "doc_type",
                                              "doc_label", "confidence", "why", "subject", "status", "status_reason", "valid_until", "error")}
                      | {"fields_n": len(d.get("fields") or {}),
                         "customer_name": CL.fv(d, "customer_name"), "cr_number": CL.fv(d, "cr_number")} for d in st["documents"]],
        "checklist": lines, "counts": CL.counts(lines),
        "groups": [{"key": g, "label": CL.GROUP_LABEL[g]} for g in CL.GROUP_ORDER],
        "reconciliation": recon,
    }
    out["plain_words"] = _plain(out)
    return out


# ------------------------------------------------------------------------------------------------ publish
def _rows(st: dict[str, Any], v: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    iid, pid = st["intake_id"], st.get("proposal_id") or ""
    c = v["counts"]
    b = v["bank"]
    rows: dict[str, list[dict[str, Any]]] = {r: [] for r in RELS}
    rows["dd_intake_file"].append({
        "intake_id": iid, "proposal_id": pid, "customer_name": v["profile"]["customer_name"], "cr_number": v["profile"]["cr_number"],
        "existing_customer": 1 if b.get("existing") else 0, "matched_cif": b.get("cif") or "", "matched_proposal_id": b.get("proposal_id") or "",
        "case_kind": ("existing" if b.get("existing") else "new_to_bank") + ("+contractor" if v["profile"]["contractor"] else ""),
        "as_of": v["as_of"], "documents_n": v["documents_n"], "received_n": c["received"], "missing_n": c["missing"], "expired_n": c["expired"],
        "flags_n": sum(1 for t in v["reconciliation"] if t["severity"] >= 2), "created_by": st.get("created_by") or "", "created_at": st["created_at"]})
    vdocs = {d["doc_id"]: d for d in v["documents"]}
    for d in st["documents"]:
        dv = vdocs.get(d["doc_id"], {})
        f = d.get("fields") or {}

        def g(k: str) -> str:
            x = f.get(k)
            return str(x["value"]) if isinstance(x, dict) and x.get("value") not in (None, "") and not isinstance(x.get("value"), list) else ""
        rows["dd_intake_document"].append({
            "doc_id": d["doc_id"], "intake_id": iid, "proposal_id": pid, "file_name": d["file_name"], "file_kind": d.get("file_kind") or "",
            "read_method": d.get("read_method") or "", "ocr_engine": d.get("ocr_engine") or "", "pages": int(d.get("pages") or 0),
            "doc_type": d.get("doc_type") or "", "doc_label": d.get("doc_label") or "", "confidence": float(d.get("confidence") or 0),
            "subject": d.get("subject") or "", "customer_name": g("customer_name") or g("full_name"), "cr_number": g("cr_number"),
            "issue_date": CL.ref_date(d) or "", "expiry_date": g("expiry_date") if re.fullmatch(r"\d{4}-\d\d-\d\d", g("expiry_date")) else "",
            "period_from": g("period_from") if re.fullmatch(r"\d{4}-\d\d-\d\d", g("period_from")) else "",
            "period_to": g("period_to") if re.fullmatch(r"\d{4}-\d\d-\d\d", g("period_to")) else "",
            "status": dv.get("status") or ("unreadable" if d.get("error") else "received"), "fields_n": len(f), "sha256": d.get("sha256") or ""})
        for k, x in f.items():
            val = x.get("value")
            is_list = isinstance(val, list)
            num = float(val) if isinstance(val, (int, float)) and not isinstance(val, bool) else float("nan")
            rows["dd_intake_field"].append({
                "field_row_id": f"{d['doc_id']}:{k}", "intake_id": iid, "proposal_id": pid, "doc_id": d["doc_id"], "doc_type": d.get("doc_type") or "",
                "field": k, "label": x.get("label") or "", "value_text": "" if is_list else str(val), "value_num": num,
                "value_mn": round(num / 1e6, 4) if x.get("type") == "sar" and num == num else float("nan"),
                "value_json": json.dumps(val, default=str) if is_list else "", "line_no": int(x.get("line") or 0), "raw_text": str(x.get("raw") or "")[:200]})
    for ln in v["checklist"]:
        cid = f"{iid}:{ln['doc_type']}:{norm(ln['subject'])[:30]}"
        n = 2
        while any(r["check_id"] == cid for r in rows["dd_intake_check"]):
            cid = f"{iid}:{ln['doc_type']}:{norm(ln['subject'])[:30]}:{n}"
            n += 1
        rows["dd_intake_check"].append({"check_id": cid, "intake_id": iid, "proposal_id": pid, "req_group": ln["req_group"], "doc_type": ln["doc_type"],
                                        "requirement": ln["requirement"], "subject": ln["subject"], "status": ln["status"], "doc_ids": ln["doc_ids"],
                                        "reason": ln.get("reason") or "", "valid_until": ln.get("valid_until") or "", "rule_ref": ln.get("rule_ref") or ""})
    for t in v["reconciliation"]:
        rid = f"{iid}:{t['test']}"
        if any(r["recon_id"] == rid for r in rows["dd_intake_reconciliation"]):
            rid = f"{rid}:{len(rows['dd_intake_reconciliation'])}"

        def fl(x: Any) -> float:
            return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else float("nan")
        rows["dd_intake_reconciliation"].append({
            "recon_id": rid, "intake_id": iid, "proposal_id": pid, "topic": t["topic"], "title": t["title"], "status": t["status"],
            "severity": int(t["severity"]), "value_a": fl(t.get("a")), "value_b": fl(t.get("b")), "value_c": fl(t.get("c")),
            "gap_pct": fl(t.get("gap_pct")), "unit_note": t.get("unit_note") or "", "sentence": t["sentence"],
            "evidence_json": json.dumps(t.get("evidence") or [], default=str)})
    return rows


def publish(st: dict[str, Any], v: dict[str, Any] | None = None) -> dict[str, int]:
    """Replace this file's rows in every intake relation (Data Domains). Best effort: a failed publish never loses the file."""
    v = v or view(st)
    if os.environ.get("CP_INTAKE_NO_PUBLISH") == "1":
        return {}
    from backend.dealdesk.data import store
    out: dict[str, int] = {}
    for rel, rows in _rows(st, v).items():
        try:
            store.publish(rel, rows, mode="replace_where", where={"intake_id": st["intake_id"]}, actor=ACTOR)
            out[rel] = len(rows)
        except Exception as e:  # noqa: BLE001
            out[rel] = -1
            st.setdefault("publish_errors", []).append(f"{rel}: {type(e).__name__}: {e}"[:200])
    from backend.dealdesk.graph.hook import feed_intake_state  # Round G: every published customer file feeds the graph
    feed_intake_state(st)
    return out


# ------------------------------------------------------------------------------------------------ API-facing
def _ingest(st: dict[str, Any], files: list[tuple[str, bytes]]) -> list[str]:
    d = _dir(st["intake_id"]) / "files"
    d.mkdir(parents=True, exist_ok=True)
    known = {sh for x in st["documents"] for sh in (x.get("page_shas") or [x.get("sha256")])}
    skipped: list[str] = []
    groups: dict[str, list[tuple[int, str, bytes]]] = {}
    for name, data in files:
        sha = hashlib.sha256(data).hexdigest()
        if sha in known:
            skipped.append(Path(name).name)
            continue
        known.add(sha)
        stem, n = page_stem(name)
        groups.setdefault(stem if n else f"{stem}\0{len(groups)}", []).append((n, name, data))
    for key, items in groups.items():
        items.sort(key=lambda x: x[0])
        stem = key.split("\0")[0]
        prev = next((x for x in st["documents"] if stem and x.get("page_stem") == stem), None) if "\0" not in key else None
        if prev is not None:  # more pages of a photographed document already in the file
            for _, name, data in items:
                safe = re.sub(r"[^A-Za-z0-9._\-]+", "_", Path(name).name)[-120:]
                (d / f"{prev['doc_id']}__{safe}").write_bytes(data)
            names = (prev.get("page_files") or []) + [Path(n).name for _, n, _ in items]
            pages = [(nm, (next(d.glob(f"{prev['doc_id']}__{re.sub(r'[^A-Za-z0-9._-]+', '_', nm)[-120:]}"))).read_bytes()) for nm in names]
            pages.sort(key=lambda x: page_stem(x[0])[1])
            new = read_pages(pages, prev["doc_id"])
            st["documents"][st["documents"].index(prev)] = new
            continue
        n = len(st["documents"]) + 1
        doc_id = f"{st['intake_id']}-D{n:02d}"
        for _, name, data in items:
            safe = re.sub(r"[^A-Za-z0-9._\-]+", "_", Path(name).name)[-120:]
            (d / f"{doc_id}__{safe}").write_bytes(data)
        st["documents"].append(read_pages([(nm, dt_) for _, nm, dt_ in items], doc_id))
    return skipped


def open_file(files: list[tuple[str, bytes]], by: str = "", as_of: str | None = None, proposal_id: str = "") -> dict[str, Any]:
    if not files:
        raise IntakeError("Upload at least one document.")
    iid = "IN-" + dt.datetime.now(dt.timezone.utc).strftime("%y%m%d%H%M") + "-" + uuid.uuid4().hex[:4].upper()
    st = {"intake_id": iid, "created_at": _now(), "created_by": by, "as_of": (as_of or as_of_default().isoformat()),
          "proposal_id": proposal_id, "documents": []}
    with _LOCK:
        _dir(iid).mkdir(parents=True, exist_ok=True)
        skipped = _ingest(st, files)
        v = view(st)
        st["published"] = publish(st, v)
        _save(st)
    v["skipped"] = skipped
    return v


def add_files(iid: str, files: list[tuple[str, bytes]]) -> dict[str, Any]:
    with _LOCK:
        st = _load(iid)
        skipped = _ingest(st, files)
        v = view(st)
        st["published"] = publish(st, v)
        _save(st)
    v["skipped"] = skipped
    return v


def get(iid: str) -> dict[str, Any]:
    return view(_load(iid))


def document(iid: str, doc_id: str) -> dict[str, Any]:
    st = _load(iid)
    d = next((x for x in st["documents"] if x["doc_id"] == doc_id), None)
    if d is None:
        raise IntakeError(f"No such document: {doc_id}")
    return {k: d.get(k) for k in ("doc_id", "file_name", "read_method", "ocr_engine", "doc_type", "doc_label", "confidence", "why", "subject", "title",
                                   "fields", "error")} | {"text": "\n".join(d.get("lines") or [])[:20000]}


def file_bytes(iid: str, doc_id: str) -> tuple[str, bytes]:
    d = _dir(iid) / "files"
    for p in sorted(d.glob(f"{doc_id}__*")):
        return p.name.split("__", 1)[1], p.read_bytes()
    raise IntakeError(f"No such document: {doc_id}")


def reclassify(iid: str, doc_id: str, doc_type: str) -> dict[str, Any]:
    """The user corrects a document's type: fields are re-read for that type."""
    if doc_type not in BY_CODE:
        raise IntakeError(f"Unknown document type: {doc_type}")
    with _LOCK:
        st = _load(iid)
        d = next((x for x in st["documents"] if x["doc_id"] == doc_id), None)
        if d is None:
            raise IntakeError(f"No such document: {doc_id}")
        d["doc_type"], d["doc_label"], d["confidence"], d["why"] = doc_type, BY_CODE[doc_type].label, 1.0, ["set by the user"]
        d["fields"] = extract(doc_type, d.get("lines") or [], d.get("spans"))
        _year_fallback(d, d.get("page_files") or [d["file_name"]])
        d["subject"] = subject_of(d)
        v = view(st)
        st["published"] = publish(st, v)
        _save(st)
    return v


def remove_document(iid: str, doc_id: str) -> dict[str, Any]:
    with _LOCK:
        st = _load(iid)
        st["documents"] = [x for x in st["documents"] if x["doc_id"] != doc_id]
        for p in (_dir(iid) / "files").glob(f"{doc_id}__*"):
            p.unlink()
        v = view(st)
        st["published"] = publish(st, v)
        _save(st)
    return v


def sync_deal_documents(proposal_id: str, v: dict[str, Any], by: str = "intake") -> int:
    """The deal's own document checklist (R12 B, backend/dealdesk/documents.py) learns what the customer file received:
    each pending item whose rule a received document answers becomes received, dated, with a note naming the file.
    Never downgrades an item and never touches one a user already set."""
    try:
        from backend.dealdesk import documents as DOCS
        items = DOCS.checklist(proposal_id)["items"]
    except Exception:  # noqa: BLE001 - a deal the R12 checklist cannot read: nothing to sync
        return 0
    got = [ln for ln in v["checklist"] if ln["status"] == "received" and ln.get("rule_ref")]
    names = {d["doc_id"]: d["file_name"] for d in v["documents"]}
    n = 0
    for it in items:
        if it.get("status") != "pending" or it.get("status_source") == "user":
            continue
        cands = [ln for ln in got if ln["rule_ref"] == it["rule_id"]]
        kind = it.get("for_kind")
        if kind in ("ubo", "guarantor", "person", "shareholder", "bank"):
            cands = [ln for ln in cands if CL.same_name(ln["subject"], it.get("for") or "")]
        elif kind == "entity" and not CL.same_name(v["profile"].get("customer_name") or "", it.get("for") or ""):
            cands = []  # another group entity's document is not the customer's
        elif kind == "collateral":
            cands = []
        if not cands:
            continue
        ln = cands[0]
        try:
            DOCS.set_status(proposal_id, it["item_id"], "received", v["as_of"],
                            f"In the customer file {v['intake_id']}: {', '.join(names.get(x, x) for x in ln['doc_ids'].split(',') if x)[:160]}", by)
            n += 1
        except Exception:  # noqa: BLE001
            continue
    return n


def attach(iid: str, proposal_id: str) -> dict[str, Any]:
    if not proposal_id:
        raise IntakeError("proposal_id is required")
    with _LOCK:
        st = _load(iid)
        st["proposal_id"] = proposal_id
        v = view(st)
        st["published"] = publish(st, v)
        st["synced_documents"] = sync_deal_documents(proposal_id, v)
        _save(st)
    v["synced_documents"] = st["synced_documents"]
    return v


def _states() -> list[dict[str, Any]]:
    out = []
    for p in root().glob("IN-*/state.jsonl"):
        try:
            out.append(json.loads(p.read_text()))
        except Exception:  # noqa: BLE001
            continue
    return out


def by_deal(proposal_id: str) -> dict[str, Any] | None:
    sts = [s for s in _states() if s.get("proposal_id") == proposal_id]
    if not sts:
        return None
    st = max(sts, key=lambda s: s.get("created_at") or "")
    return view(st)


def recent(limit: int = 12) -> list[dict[str, Any]]:
    sts = sorted(_states(), key=lambda s: s.get("created_at") or "", reverse=True)[:limit]
    out = []
    for s in sts:
        names = [CL.fv(d, "customer_name") for d in s.get("documents") or [] if CL.fv(d, "customer_name")]
        out.append({"intake_id": s["intake_id"], "proposal_id": s.get("proposal_id") or "", "created_at": s.get("created_at"),
                    "documents_n": len(s.get("documents") or []), "customer_name": names[0] if names else ""})
    return out


def delete(iid: str) -> dict[str, Any]:
    with _LOCK:
        d = _dir(iid)
        if d.exists():
            shutil.rmtree(d)
        try:
            from backend.dealdesk.data import store
            for rel in RELS:
                store.publish(rel, [], mode="replace_where", where={"intake_id": iid}, actor=ACTOR)
        except Exception:  # noqa: BLE001
            pass
    return {"deleted": iid}


# ------------------------------------------------------------------------------------------------ for the writers (b, c)
def _fields(d: dict[str, Any]) -> dict[str, Any]:
    return {k: x.get("value") for k, x in (d.get("fields") or {}).items()}


def facts(iid: str = "", proposal_id: str = "") -> dict[str, Any] | None:
    """The normalised customer file for the business-request (b) and credit-response (c) writers.

    {intake_id, proposal_id, as_of, profile, bank (the pull), documents: {doc_type: [{doc_id, file_name, subject, status, fields}]},
     latest: {doc_type: fields of the most recent}, financials: {FY2024: {...}, FY2025: {...}, 'YTD 2026-09': {...}},
     owners, checklist, counts, missing: [requirement lines], reconciliation, flags: [severity ≥ 2], plain_words,
     source: {relation, intake_id}}
    Every figure keeps its document id (documents[*].doc_id) so a writer can cite it ("as per the audited FY2025 accounts").
    """
    if iid:
        st = _load(iid)
    elif proposal_id:
        sts = [s for s in _states() if s.get("proposal_id") == proposal_id]
        if not sts:
            return None
        st = max(sts, key=lambda s: s.get("created_at") or "")
    else:
        raise IntakeError("intake_id or proposal_id is required")
    v = view(st)
    vd = {d["doc_id"]: d for d in v["documents"]}
    docs: dict[str, list[dict[str, Any]]] = {}
    for d in st["documents"]:
        if d.get("doc_type") in (None, "unknown", "unreadable"):
            continue
        docs.setdefault(d["doc_type"], []).append({"doc_id": d["doc_id"], "file_name": d["file_name"], "subject": d.get("subject") or "",
                                                    "status": vd.get(d["doc_id"], {}).get("status") or "received", "read_method": d.get("read_method"),
                                                    "fields": _fields(d)})
    latest = {}
    for code, xs in docs.items():
        latest[code] = sorted(xs, key=lambda x: str(CL.ref_date({"fields": {k: {"value": val} for k, val in x["fields"].items()}}) or ""))[-1]["fields"]
    fin: dict[str, Any] = {}
    for x in docs.get("audited_fs", []):
        y = str(x["fields"].get("fiscal_year") or "")[:4]
        if y:
            fin[f"FY{y}"] = {"kind": "audited", "doc_id": x["doc_id"], **x["fields"]}
    for x in docs.get("inhouse_fs", []):
        pt = str(x["fields"].get("period_to") or "")
        fin[f"YTD {pt[:7]}"] = {"kind": "in-house", "doc_id": x["doc_id"], **x["fields"]}
    allx = [d for d in st["documents"] if d.get("doc_type") not in ("unknown", "unreadable")]
    return {"intake_id": st["intake_id"], "proposal_id": st.get("proposal_id") or "", "as_of": st["as_of"], "profile": v["profile"],
            "bank": v["bank"], "documents": docs, "latest": latest, "financials": dict(sorted(fin.items())), "owners": CL.owners(allx),
            "guarantors": CL.guarantors(allx, CL.owners(allx)), "other_banks": CL.other_banks(allx),
            "checklist": v["checklist"], "counts": v["counts"], "missing": [ln for ln in v["checklist"] if ln["status"] in ("missing", "expired")],
            "reconciliation": v["reconciliation"], "flags": [t for t in v["reconciliation"] if t["severity"] >= 2], "plain_words": v["plain_words"],
            "source": {"relations": list(RELS), "intake_id": st["intake_id"]}}
