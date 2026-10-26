"""Round A: the agentic intake. One run = the Credit Request Agent's three steps on the customer's pack:

    1. Read and classify each document   R16's reader (and OCR) and the model read every new document into the intake
                                         schema, in parallel; the two readings are reconciled (read.reconcile)
    2. Check the file against the checklist   rules (checklist.run): received / missing / expired, the completeness score,
                                         what cannot be assessed, and against the previous run the delta and "now covered"
    3. Draft the business request        the model writes it, streamed (draft.prompt); figures not in the evidence are removed
                                         (draft.check_figures); the completeness line and the could-not-assess block go under
                                         the header. No model key: the deterministic draft (draft.deterministic)

    start(files, ask, notes, ...)        a new run (or `parent_run_id`: the RM adds documents and runs again on the same file)
    revise(run_id, instruction)          the model revises the draft (a new version, same checks)
    attach(run_id, proposal_id)          the deal the RM opened or created from the file (R16's attach is called by the UI)

The pack is R16's customer file too (backend/dealdesk/intake/service.py): the run opens it (or adds to it), so the deal is
opened and the file attached exactly as R16 does; the run keeps the intake id.
"""
from __future__ import annotations

import hashlib
import io
import re
import threading
import time
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from backend.dealdesk.agent_intake import checklist as CK
from backend.dealdesk.agent_intake import draft as DR
from backend.dealdesk.agent_intake import model as M
from backend.dealdesk.agent_intake import read as RD
from backend.dealdesk.agent_intake import store as ST

STEPS = [("read", "Read and classify each document", "Extracts dates, figures and credit observations from every file, including photos and scanned PDFs."),
         ("check", "Check the file against the checklist", "Marks each required document as received, missing or expired."),
         ("draft", "Draft the business request", "Writes the RM's request to Credit, citing the source document for every figure.")]
WORKERS = 3
MAX_FILES = 80


class AgentError(ValueError):
    pass


# ------------------------------------------------------------------------------------------------ files
def unpack(files: list[tuple[str, bytes]]) -> tuple[list[tuple[str, bytes]], list[str]]:
    """ZIPs opened (folders flattened, __MACOSX and hidden files skipped); unsupported files listed."""
    out: list[tuple[str, bytes]] = []
    skipped: list[str] = []
    for name, data in files:
        if name.lower().endswith(".zip"):
            try:
                z = zipfile.ZipFile(io.BytesIO(data))
            except zipfile.BadZipFile:
                skipped.append(f"{name}: not a readable ZIP")
                continue
            for e in sorted(z.infolist(), key=lambda x: x.filename):
                base = Path(e.filename).name
                if e.is_dir() or "__MACOSX" in e.filename or base.startswith(".") or not base:
                    continue
                if not base.lower().endswith(RD.ACCEPTED):
                    skipped.append(f"{base}: not a supported file")
                    continue
                out.append((base, z.read(e)))
            continue
        if not name.lower().endswith(RD.ACCEPTED):
            skipped.append(f"{Path(name).name}: not a supported file")
            continue
        out.append((Path(name).name, data))
    if len(out) > MAX_FILES:
        raise AgentError(f"Upload at most {MAX_FILES} documents at once.")
    return out, skipped


def _groups(files: list[tuple[str, bytes]]) -> list[list[tuple[str, bytes]]]:
    """Photographed pages of one document (name_p1.jpg, name_p2.jpg) are one document, as R16 reads them."""
    from backend.dealdesk.intake.service import page_stem
    groups: dict[str, list[tuple[int, str, bytes]]] = {}
    order: list[str] = []
    for name, data in files:
        stem, n = page_stem(name)
        key = stem if n else f"{name}\0{len(order)}"
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append((n, name, data))
    return [[(nm, d) for _, nm, d in sorted(groups[k], key=lambda x: x[0])] for k in order]


# ------------------------------------------------------------------------------------------------ the run
def _new_run(ask: str, notes: str, rm: str, by: str, parent: dict[str, Any] | None, market: str) -> dict[str, Any]:
    from backend.dealdesk.intake import service as IS
    rid = "AR-" + uuid.uuid4().hex[:10].upper()
    info = M.available()
    return {"run_id": rid, "parent_run_id": parent["run_id"] if parent else "", "intake_id": parent["intake_id"] if parent else "",
            "proposal_id": (parent or {}).get("proposal_id") or "", "created_at": ST.now(), "created_by": by, "status": "queued", "error": "",
            "as_of": (parent or {}).get("as_of") or IS.as_of_default().isoformat(), "market": market or (parent or {}).get("market") or "",
            "market_set": bool(market), "ask": ask, "notes": notes, "rm": rm or by or "", "customer": (parent or {}).get("customer") or "",
            "cr": (parent or {}).get("cr") or "", "existing": False, "request_type": DR.request_type(ask), "model": info,
            "steps": [{"key": k, "title": t, "status": "pending", "detail": d, "ms": None, "started_at": None} for k, t, d in STEPS],
            "documents": [dict(d, new=False) for d in (parent or {}).get("documents") or []], "skipped": [], "check": None,
            "draft": {"text": "", "md": "", "source": "", "status": "pending", "words": 0, "rejected": [], "versions": []},
            "model_calls": [], "bank": (parent or {}).get("bank") or {}, "elapsed_ms": None}


def _step(run: dict[str, Any], key: str, **kw: Any) -> dict[str, Any]:
    s = next(x for x in run["steps"] if x["key"] == key)
    s.update(kw)
    return s


def start(files: list[tuple[str, bytes]], ask: str, notes: str = "", rm: str = "", by: str = "", market: str = "",
          parent_run_id: str = "", sync: bool = False) -> dict[str, Any]:
    if not ask.strip():
        raise AgentError("State the ask first: what the business wants approved (facilities, amounts, tenor, purpose, pricing).")
    parent = ST.get(parent_run_id) if parent_run_id else None
    if parent is not None and parent.get("status") in ("queued", "running"):
        raise AgentError("The last run is still working; wait for it to finish.")
    got, skipped = unpack(files)
    if not got and not (parent and parent.get("documents")):
        raise AgentError("Add at least one document (PDF, Word, Excel, CSV, photos, or the whole pack as one ZIP).")
    run = _new_run(ask.strip(), notes.strip(), rm, by, parent, market if market in CK.CHECK else "")
    run["skipped"] = skipped
    ST.LIVE[run["run_id"]] = run
    ST.save(run)
    if sync:
        execute(run, got)
    else:
        threading.Thread(target=execute, args=(run, got), daemon=True, name=f"agent-intake-{run['run_id']}").start()
    return run


def execute(run: dict[str, Any], files: list[tuple[str, bytes]]) -> dict[str, Any]:
    from backend.convo import telemetry
    t0 = time.monotonic()
    run["status"] = "running"
    try:
        with telemetry.use(module=M.MODULE, run_id=run["run_id"], domain="dealdesk"):
            _read(run, files)
            _check(run)
            _draft(run)
        run["status"] = "done"
    except Exception as e:  # noqa: BLE001 - a failed run says why and keeps what it did
        run["status"] = "failed"
        run["error"] = f"{type(e).__name__}: {str(e)[:300]}"
        for s in run["steps"]:
            if s["status"] == "running":
                s["status"] = "failed"
    finally:
        run["elapsed_ms"] = int((time.monotonic() - t0) * 1000)
        ST.save(run)
        ST.LIVE.pop(run["run_id"], None)
    return run


# ------------------------------------------------------------------------------------------------ step 1
def _model_read(run: dict[str, Any], doc: dict[str, Any], ft: dict[str, Any], market: str) -> dict[str, Any] | None:
    from backend.convo import telemetry
    if not run["model"]["model_available"] or ft is None:
        return None
    with telemetry.use(module=M.MODULE, run_id=run["run_id"], domain="dealdesk"):
        try:
            res = M.tool_call(run["model_calls"], "agent_intake_read", "You read bank customer documents into a schema. Copy figures exactly.",
                              RD.model_content(doc["id"], doc["name"], market, run["as_of"], ft), RD.TOOL, doc_id=doc["id"])
        except Exception as e:  # noqa: BLE001 - the rule reader stands
            doc["model_error"] = f"{type(e).__name__}: {str(e)[:120]}"
            return None
    return RD.clean_model(res, market)


def _read(run: dict[str, Any], files: list[tuple[str, bytes]]) -> None:
    from backend.dealdesk.intake import service as IS
    st = _step(run, "read", status="running", started_at=ST.now(), detail="Opening the pack…")
    t0 = time.monotonic()
    ST.save(run)
    known = {sh for d in run["documents"] for sh in d.get("sha256s") or []}
    n0 = len(run["documents"])
    new: list[dict[str, Any]] = []
    for grp in _groups(files):
        shas = [hashlib.sha256(b).hexdigest() for _, b in grp]
        if all(s in known for s in shas):
            run["skipped"].append(f"{grp[0][0]}: already in the file")
            continue
        known.update(shas)
        did = f"D{n0 + len(new) + 1}"
        names = [n for n, _ in grp]
        doc = {"id": did, "name": grp[0][0] if len(grp) == 1 else f"{Path(grp[0][0]).stem} ({len(grp)} pages)", "files": names,
               "kind": RD.kind_of(grp[0][0]), "sha256s": shas, "status": "reading", "new": True, "method": "", "result": None,
               "rule": None, "model": None, "recon": None, "r16_doc_id": "", "r16_type": "", "error": ""}
        new.append(doc)
        fd = ST.files_dir(run["intake_id"] or run["run_id"])
        for n, b in grp:
            (fd / f"{did}__{re.sub(r'[^A-Za-z0-9._ ()-]+', '_', n)[-120:]}").write_bytes(b)
    run["documents"] += new
    ST.save(run)
    if not new and not run["documents"]:
        raise AgentError("No document could be read.")
    # the texts (the model's input and the figure check's source) per new document
    fts: dict[str, dict[str, Any] | None] = {}
    by_name = {}
    for doc in new:
        grp = [(n, b) for n, b in files if n in doc["files"]]
        by_name[doc["id"]] = grp
        try:
            if len(grp) == 1:
                fts[doc["id"]] = RD.file_text(*grp[0])
            else:
                parts = [RD.file_text(n, b) for n, b in grp]
                fts[doc["id"]] = {"kind": "image", "pages": [], "images": [i for p in parts for i in p["images"]][:RD.MAX_IMAGES], "method": "photos (page images)"}
            doc["method"] = fts[doc["id"]]["method"]
        except Exception as e:  # noqa: BLE001
            fts[doc["id"]] = None
            doc["error"] = str(e)[:200]
    texts = [p for ft in fts.values() if ft for p in ft["pages"]]
    market = run["market"] or RD.market_of(texts + [run["ask"], run["notes"]])
    run["market"] = market

    # R16's reader (OCR for photos and scans) and the model, at the same time
    r16_out: dict[str, Any] = {}

    def r16() -> None:
        rend = [RD.r16_rendition(n, b) for doc in new for n, b in by_name[doc["id"]]]
        if not rend:
            r16_out["view"] = IS.get(run["intake_id"]) if run["intake_id"] else None
            return
        try:
            if run["intake_id"]:
                r16_out["view"] = IS.add_files(run["intake_id"], rend)
            else:
                r16_out["view"] = IS.open_file(rend, by=run["created_by"], as_of=run["as_of"])
        except Exception as e:  # noqa: BLE001
            r16_out["error"] = f"{type(e).__name__}: {e}"
    th = threading.Thread(target=r16, daemon=True)
    th.start()
    done = [0]

    def one(doc: dict[str, Any]) -> None:
        doc["model"] = _model_read(run, doc, fts.get(doc["id"]), market)
        done[0] += 1
        st["detail"] = f"Read {done[0]} of {len(new)} new documents" + (" with the model" if run["model"]["model_available"] else "")
        ST.save(run, force=False)
    if run["model"]["model_available"]:
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            list(ex.map(one, [d for d in new if fts.get(d["id"])]))
    st["detail"] = "Reading photos and scans (OCR)…" if any(d["kind"] in ("image",) or (fts.get(d["id"]) or {}).get("kind") == "image" for d in new) else "Reading…"
    ST.save(run)
    th.join()
    if "error" in r16_out and not run["intake_id"]:
        raise AgentError(f"The customer file could not be opened: {r16_out['error']}")
    v = r16_out.get("view")
    if v is not None:
        run["intake_id"] = v["intake_id"]
        run["bank"] = {k: v["bank"].get(k) for k in ("existing", "how", "proposal_id", "cif", "name")}
        run["customer"] = RD.company_name(v["profile"].get("customer_name")) or run["customer"]
        run["cr"] = v["profile"].get("cr_number") or run["cr"]
        # the originals under the intake id
        src = ST.root() / "files" / run["run_id"]
        if src.exists():
            dst = ST.files_dir(run["intake_id"])
            for p in src.iterdir():
                p.replace(dst / p.name)
            src.rmdir()
    st_docs = {}
    if run["intake_id"]:
        st_docs = {Path(n).name: d for d in IS._load(run["intake_id"])["documents"] for n in (d.get("page_files") or [d.get("file_name")])}  # noqa: SLF001
    for doc in new:
        rend_names = [RD.r16_name(n) for n in doc["files"]]
        r16doc = next((st_docs[n] for n in rend_names if n in st_docs), None) or {}
        doc["r16_doc_id"] = r16doc.get("doc_id") or ""
        doc["r16_type"] = r16doc.get("doc_type") or ""
        ft = fts.get(doc["id"])
        pages = ft["pages"] if ft and ft["kind"] == "text" else (["\n".join(r16doc.get("lines") or [])] if r16doc.get("lines") else [])
        if not pages and not doc["model"]:
            doc["status"] = "failed"
            doc["error"] = doc["error"] or r16doc.get("error") or "No text could be read."
            continue
        if not doc["method"] or doc["kind"] == "image" or (ft and ft["kind"] == "image"):
            doc["method"] = (r16doc.get("read_method") or doc["method"] or "") + (" + model vision" if doc["model"] else "")
        ST.save_pages(run["intake_id"] or run["run_id"], doc["id"], pages)
        doc["rule"] = RD.rule_read(r16doc, pages, doc["name"], run["customer"])
        doc["result"], doc["recon"] = RD.reconcile(doc["rule"], doc["model"], pages)
        doc["status"] = "read"
    ok = [d for d in new if d["status"] == "read"]
    if not any(d["status"] == "read" for d in run["documents"]):
        raise AgentError("No document could be read. Check the files and run again.")
    rc = {"confirmed": 0, "offered": 0, "flagged": 0, "rule": 0}
    for d in ok:
        rc[d["recon"]["status"]] = rc.get(d["recon"]["status"], 0) + 1
    if not run["customer"]:
        ents = [RD.company_name(d["result"].get("entity")) for d in run["documents"] if d.get("result")]
        ents = [e for e in ents if e]
        run["customer"] = max(set(ents), key=ents.count) if ents else RD.name_in_texts(texts + [run["ask"], run["notes"]])
    bad = [d for d in new if d["status"] == "failed"]
    carried = len(run["documents"]) - len(new)
    parts = [f"{len(ok)} new document{'s' if len(ok) != 1 else ''} read" + (f" ({carried} from the last run)" if carried else "")]
    if run["model"]["model_available"]:
        parts.append(f"{rc['confirmed']} confirmed, {rc['offered']} where the model found more, {rc['flagged']} flagged")
    else:
        parts.append("rule reader and OCR (no model key)")
    if bad:
        parts.append(f"{len(bad)} could not be read")
    st.update(status="warn" if bad or rc["flagged"] else "done", ms=int((time.monotonic() - t0) * 1000), detail="; ".join(parts) + ".")
    ST.save(run)


# ------------------------------------------------------------------------------------------------ step 2
def _check(run: dict[str, Any]) -> None:
    st = _step(run, "check", status="running", started_at=ST.now(), detail="Checking…")
    t0 = time.monotonic()
    read = [{"id": d["id"], "name": d["name"], "result": d["result"]} for d in run["documents"] if d.get("result")]
    ids = {k for d in read for k in d["result"].get("checklist_ids") or []}
    run["existing"] = RD.existing_of(bool((run.get("bank") or {}).get("existing")), ids, run["ask"])
    prev = None
    if run["parent_run_id"]:
        try:
            prev = (ST.get(run["parent_run_id"]).get("check") or {}).get("comp")
        except ST.NotFound:
            prev = None
    ck = CK.run(read, run["market"], run["existing"], run["as_of"], prev=prev)
    run["check"] = ck
    st.update(status="warn" if ck["missing"] or ck["expired"] else "done", ms=int((time.monotonic() - t0) * 1000),
              detail=f"{len(ck['received'])} of {ck['total']} received · {len(ck['missing'])} missing · {len(ck['expired'])} expired · "
                     f"{CK.meter_text(ck)}, {ck['comp']['crit']} critical gap{'' if ck['comp']['crit'] == 1 else 's'}")
    ST.save(run)


# ------------------------------------------------------------------------------------------------ step 3
def context(run: dict[str, Any]) -> dict[str, Any]:
    key = run["intake_id"] or run["run_id"]
    docs = [{"id": d["id"], "name": d["name"], "pages": ST.pages(key, d["id"]), "result": d["result"]} for d in run["documents"] if d.get("result")]
    ksa = run["market"] != "UAE"
    return {"customer": run["customer"], "cr": run["cr"], "market": run["market"], "currency": "SAR" if ksa else "AED",
            "bureau": "SIMAH" if ksa else "AECB", "request_type": run["request_type"], "existing": run["existing"], "rm": run["rm"],
            "as_of": run["as_of"], "ask": run["ask"], "notes": run["notes"], "docs": docs, "check": run["check"]}


def _finish(run: dict[str, Any], text: str, source: str, ctx: dict[str, Any], instruction: str = "") -> None:
    body = CK.strip_gaps(DR.clean_md(text))
    body, rejected = DR.check_figures(body, DR.evidence(ctx))
    md = CK.with_gaps(body, run["check"])
    d = run["draft"]
    d.update(md=md, text=md, source=source, status="done", words=DR.words(body), rejected=rejected)
    d["versions"].append({"n": len(d["versions"]) + 1, "at": ST.now(), "instruction": instruction, "source": source, "md": md,
                          "words": d["words"], "rejected": rejected})


def _draft(run: dict[str, Any]) -> None:
    st = _step(run, "draft", status="running", started_at=ST.now(), detail="Writing…")
    t0 = time.monotonic()
    ctx = context(run)
    run["draft"]["status"] = "streaming"
    ST.save(run)
    source = "deterministic"
    text = ""
    if run["model"]["model_available"]:
        def on_text(t: str) -> None:
            run["draft"]["text"] = t
            st["detail"] = f"Writing… {len(t):,} characters"
            ST.save(run, force=False)
        try:
            text = M.stream_text(run["model_calls"], "agent_intake_draft", DR.prompt(ctx), on_text)
            source = "model"
        except Exception as e:  # noqa: BLE001 - the deterministic draft stands
            run["draft"]["model_error"] = f"{type(e).__name__}: {str(e)[:160]}"
            text = ""
    if not text:
        text = DR.deterministic(ctx)
    _finish(run, text, source, ctx)
    c = run["check"]["comp"]
    rej = run["draft"]["rejected"]
    st.update(status="done", ms=int((time.monotonic() - t0) * 1000),
              detail=(f"Draft ready ({'written by the model' if source == 'model' else 'written by rules: no model key'}, {run['draft']['words']} words). "
                      f"Completeness {c['pct']}%" + (f": {len(c['gaps'])} item(s) not fully supported, {c['crit']} critical. What it could not assess is listed under the header."
                                                     if c["gaps"] else ".")
                      + (f" {len(rej)} figure{'s' if len(rej) != 1 else ''} not in the evidence removed." if rej else "")))
    ST.save(run)


# ------------------------------------------------------------------------------------------------ revise, attach
def revise(run_id: str, instruction: str, by: str = "", sync: bool = False) -> dict[str, Any]:
    run = ST.get(run_id)
    ins = (instruction or "").strip()
    if not ins:
        raise AgentError("Type the change you want, e.g. tighten section 7, add a covenant on DSO.")
    if run.get("status") != "done" or not run["draft"].get("md"):
        raise AgentError("The draft is not ready yet.")
    if not M.available()["model_available"]:
        raise AgentError("Revise needs the model, and no model key is set on this installation. The draft stays as written; "
                         "download it in Word to edit it.")
    run["status"] = "revising"
    run["draft"]["status"] = "streaming"
    ST.LIVE[run_id] = run

    def go() -> None:
        from backend.convo import telemetry
        t0 = time.monotonic()
        st = _step(run, "draft", status="running", detail=f"Revising: {ins}")
        try:
            with telemetry.use(module=M.MODULE, run_id=run_id, domain="dealdesk"):
                ctx = context(run)
                cur = CK.strip_gaps(run["draft"]["md"])

                def on_text(t: str) -> None:
                    run["draft"]["text"] = t
                    ST.save(run, force=False)
                text = M.stream_text(run["model_calls"], "agent_intake_revise", DR.REVISE.format(ins=ins), on_text,
                                     history=[{"role": "user", "content": DR.prompt(ctx)}, {"role": "assistant", "content": cur}])
                _finish(run, text, "model", ctx, instruction=ins)
                run["draft"]["versions"][-1]["by"] = by
                st.update(status="done", ms=int((time.monotonic() - t0) * 1000), detail=f"Revised: {ins}")
        except Exception as e:  # noqa: BLE001
            run["draft"].update(text=run["draft"]["md"], status="done", revise_error=f"{type(e).__name__}: {str(e)[:160]}")
            st.update(status="done", detail=f"Could not revise ({type(e).__name__}); the draft is unchanged.")
        finally:
            run["status"] = "done"
            ST.save(run)
            ST.LIVE.pop(run_id, None)
    if sync:
        go()
    else:
        threading.Thread(target=go, daemon=True).start()
    return run


def attach(run_id: str, proposal_id: str) -> dict[str, Any]:
    if not proposal_id:
        raise AgentError("proposal_id is required")
    run = ST.get(run_id)
    run["proposal_id"] = proposal_id
    ST.save(run)
    return run


def public(run: dict[str, Any]) -> dict[str, Any]:
    """The run as the screen reads it (no raw texts; the model's and the rule reader's readings kept for the document view)."""
    out = {k: v for k, v in run.items() if k not in ("documents",)}
    out["documents"] = [{k: d.get(k) for k in ("id", "name", "files", "kind", "method", "status", "new", "error", "result", "recon",
                                                "r16_doc_id", "r16_type", "model_error")} for d in run.get("documents") or []]
    out["model_summary"] = {"calls": len(run.get("model_calls") or []),
                            "input_tokens": sum(int(c.get("input_tokens") or 0) for c in run.get("model_calls") or []),
                            "output_tokens": sum(int(c.get("output_tokens") or 0) for c in run.get("model_calls") or []),
                            "ms": sum(int(c.get("ms") or 0) for c in run.get("model_calls") or [])}
    return out
