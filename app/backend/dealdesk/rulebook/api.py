"""/api/v1/dealdesk/rulebook: Policy Docs as the rulebook (Round P).

    GET   /rulebook/kinds                          the four kinds of Policy Docs with their counts
    POST  /rulebook/assess                         multipart: file (or text), kind (regulation | policy), title?, reference?, policy_doc_id?
                                                   -> summary, thresholds set, checks and parameters moved, pipeline impact (if
                                                   applied / if not applied), stored as a pending assessment
    GET   /rulebook/assessments                    ?kind= ?policy_doc_id= ?status=
    GET   /rulebook/assessments/{id}
    POST  /rulebook/assessments/{id}/refresh       the pipeline impact again (the pipeline moves)
    POST  /rulebook/assessments/{id}/decision      {approve: bool, note?} -> approve: thresholds in force (provenance), affected
                                                   pending deals flagged with the clause; reject: nothing changes
    GET   /rulebook/thresholds                     every policy-check threshold: the value in force, where it comes from, history
    GET   /rulebook/flags                          ?proposal_id= ?assessment_id= ?status=open|cleared|""
    POST  /rulebook/flags/{n}/clear
    GET   /rulebook/deals/{pid}                    a deal's open policy flags and its policy-check results
    GET   /rulebook/pipeline                       the pending deals the checks read (?refresh=1 recomputes)
    POST  /rulebook/gold                           multipart: file, title? -> differences from how CreditProbe writes today
    GET   /rulebook/gold, /rulebook/gold/{id}
    POST  /rulebook/gold/{id}/apply                {ids: [...]} -> bank rules (origin gold:<id>) + the house-style corpus
    POST  /rulebook/gold/{id}/dismiss
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any

from fastapi import APIRouter, Body, File, Form, HTTPException, Query, Request, UploadFile

from backend.dealdesk.rulebook import checks as CK
from backend.dealdesk.rulebook import facts as FA
from backend.dealdesk.rulebook import gold as GD
from backend.dealdesk.rulebook import impact as IM
from backend.dealdesk.rulebook import interpret as IN
from backend.dealdesk.rulebook import store
from backend.dealdesk.rules import hook as rules_hook

PREFIX = "/api/v1/dealdesk"
router = APIRouter(prefix=f"{PREFIX}/rulebook", tags=["dealdesk-rulebook"])
KINDS = [{"id": "regulation", "label": "Regulation", "about": "Regulators' circulars and rules (SAMA, CBUAE): read, impact on the pipeline, approve."},
         {"id": "policy", "label": "Internal credit policy", "about": "The bank's own credit policy and its amendments: read, impact, approve."},
         {"id": "gold", "label": "Gold-standard documents", "about": "Proposals the bank considers ideal: compared with how CreditProbe writes today."},
         {"id": "rules", "label": "Global rules", "about": "The bank's writing rules, applied to every credit request and proposal."}]
MAX_BYTES = 15 * 1024 * 1024


def _who(request: Request) -> str:
    return rules_hook.username(request)


def _need(request: Request) -> str:
    u = _who(request)
    if not u:
        raise HTTPException(401, "Sign in: every decision is stored with who made it.")
    return u


def _nf(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except store.NotFound as e:
        raise HTTPException(404, str(e.args[0]) if e.args else "Not found.") from None
    except (store.Invalid, ValueError) as e:
        raise HTTPException(422, str(e)) from None


async def _read(file: UploadFile | None, text: str) -> tuple[str, str, list[tuple[str, str]], bytes]:
    if file is not None and file.filename:
        data = await file.read()
        if len(data) > MAX_BYTES:
            raise HTTPException(413, "The file is over 15 MB.")
        from backend.playbook_v5 import ingest
        from backend.playbook_v5 import store as pstore
        try:
            t, sections = ingest.text_of(file.filename, data)
        except pstore.Invalid as e:
            raise HTTPException(422, str(e)) from None
        return file.filename, ingest.clean(t), sections, data
    if text.strip():
        lines = [ln.strip() for ln in text.splitlines()]
        sections = [(ln, "") for ln in lines if ln and len(ln) < 80 and (ln.isupper() or re.match(r"^\d+(?:\.\d+)*[.)]?\s+[A-Z]", ln))]
        return "pasted.txt", text, sections, text.encode()
    raise HTTPException(422, "file: upload the document (Word, PDF or text), or send its text.")


@router.get("/kinds")
def kinds() -> dict[str, Any]:
    a = Counter(x["kind"] for x in store.assessments())
    from backend.dealdesk.rules import store as rstore
    return {"kinds": [{**k, "count": len(store.golds()) if k["id"] == "gold" else len(rstore.listing(scope="bank")) if k["id"] == "rules"
                       else a.get(k["id"], 0)} for k in KINDS]}


@router.post("/assess")
async def assess(request: Request, file: UploadFile | None = File(None), text: str = Form(""), kind: str = Form("regulation"),
                 title: str = Form(""), reference: str = Form(""), policy_doc_id: str = Form(""), use_model: bool = Form(True)) -> dict[str, Any]:
    if kind not in ("regulation", "policy"):
        kind = "policy" if kind in ("guideline",) else "regulation"
    name, body, sections, _ = await _read(file, text)
    if not body.strip():
        raise HTTPException(422, "No text was found in that file.")
    if not title:  # the document's own subject line: the first line that is not a shouted letterhead
        title = next((ln.strip() for ln in body.splitlines() if 8 < len(ln.strip()) < 140 and not ln.strip().isupper()
                      and not IN.CLAUSE.match(ln)), "") or (sections[0][0] if sections else name)
    title = title.strip()[:200]
    if not reference:
        m = re.search(r"\b(?:Circular|Ref(?:erence)?)\s*(?:No\.?)?\s*([A-Z0-9][\w/-]{2,20})", body, re.I)
        reference = f"Circular {m.group(1)}" if m else ""
    from backend.convo import telemetry
    with telemetry.use(module="dealdesk", request_path=str(request.url.path)):
        reading = IN.read(body, title, use_model=use_model)
    aid = store.new_id("PA")
    imp = IM.assess(reading["changes"], store.overlay(), aid, reference or title)
    a = store.add_assessment({"id": aid, "kind": kind, "title": title, "reference": reference, "policy_doc_id": policy_doc_id, "file_name": name,
                              "text": body[:200_000], "summary": reading["summary"], "reading": reading, "impact": imp, "uploaded_by": _who(request)})
    return {"assessment": a, "question": "Apply this to Deal Desk?" if reading["changes"] else "Keep this on record?"}


@router.get("/assessments")
def list_assessments(kind: str = Query(""), policy_doc_id: str = Query(""), status: str = Query("")) -> dict[str, Any]:
    return {"assessments": store.assessments(kind, policy_doc_id, status)}


@router.get("/assessments/{aid}")
def get_assessment(aid: str) -> dict[str, Any]:
    return {"assessment": _nf(store.get_assessment, aid)}


@router.post("/assessments/{aid}/refresh")
def refresh(aid: str) -> dict[str, Any]:
    a = _nf(store.get_assessment, aid)
    if a["status"] != "pending":
        return {"assessment": a}
    imp = IM.assess(a["reading"].get("changes") or [], store.overlay(), aid, a["reference"] or a["title"])
    return {"assessment": store.update_assessment(aid, impact=imp)}


def _write_through(changes: list[dict[str, Any]], by: str, cite: str) -> list[dict[str, Any]]:
    """A threshold for every deal that a Deal Desk table owns is written to that table too (its owner's writer, a new version)."""
    out = []
    for c in changes:
        if c["segment"] != "all" or c["param"] != "max_leverage":
            continue
        try:
            from backend.dealdesk import desk_params
            t = desk_params.set_value("uae_desk", "max_leverage", float(c["value"]), by or "policy", f"{cite} {c.get('clause', '')}".strip())
            out.append({"table": "uae_desk", "key": "max_leverage", "version": t.get("version"), "value": c["value"]})
        except Exception as e:  # noqa: BLE001 - the threshold is in force in the checks either way
            out.append({"table": "uae_desk", "key": "max_leverage", "error": f"{type(e).__name__}: {str(e)[:120]}"})
    return out


@router.post("/assessments/{aid}/decision")
def decision(aid: str, request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    by = _need(request)
    a = _nf(store.get_assessment, aid)
    if a["status"] != "pending":
        raise HTTPException(409, f"This document is already {a['status']}.")
    note = str(body.get("note") or "")[:2000]
    if body.get("policy_doc_id"):
        store.update_assessment(aid, policy_doc_id=str(body["policy_doc_id"]))
    if not body.get("approve"):
        a = store.update_assessment(aid, status="rejected", decided_by=by, decided_at=store.now(), note=note)
        return {"assessment": a, "flagged": 0, "message": "Kept on record. Deal Desk's checks and the pipeline are unchanged."}
    changes = a["reading"].get("changes") or []
    cite = a["reference"] or a["title"]
    imp = IM.assess(changes, store.overlay(), aid, cite)  # the pipeline as it is at the moment of approval
    store.add_thresholds(aid, cite, changes, by)
    flags = [{"proposal_id": d["proposal_id"], "assessment_id": aid, "check": f["check"], "label": f["label"], "why": f["why"],
              "clause": f["clause"], "quote": f["quote"], "reference": cite} for d in imp["deals"] for f in d["new_failures"]]
    n = store.add_flags(flags, by)
    written = _write_through(changes, by, cite)
    a = store.update_assessment(aid, status="approved", decided_by=by, decided_at=store.now(), note=note, impact={**imp, "written": written},
                                flagged=len({f["proposal_id"] for f in flags}))
    deals = len({f["proposal_id"] for f in flags})
    return {"assessment": a, "flagged": deals, "flags": n, "written": written,
            "message": (f"Applied. {deals} pending deal{'s' if deals != 1 else ''} flagged with the clause cited; every later deal is checked "
                        f"against the new threshold{'s' if len(changes) != 1 else ''}." if changes else "Applied: kept as a reference; no threshold to check.")}


@router.get("/thresholds")
def thresholds() -> dict[str, Any]:
    desk = CK._desk()  # noqa: SLF001
    ov = store.overlay()
    rows = []
    for p, d in CK.PARAMS.items():
        sample = {"sector": "", "facility_type": "term_loan", "hurdle": None}
        v, src = CK.base(p, sample, desk)
        rows.append({"param": p, "check": d["check"], "label": d["label"], "unit": d["unit"], "where": d["where"],
                     "base": v, "base_display": CK.fmt(v, d["unit"]) if v is not None else ("the deal's hurdle" if p == "min_raroc" else "no requirement"),
                     "base_source": src,
                     "policy": [{"segment": e["segment"], "value": e["value"], "display": e.get("display") or CK.fmt(e["value"], d["unit"]),
                                 "clause": e["clause"], "reference": e["reference"], "approved_by": e["approved_by"], "approved_at": e["approved_at"],
                                 "assessment_id": e["assessment_id"]} for e in ov.get(p, [])]})
    return {"thresholds": rows}


@router.get("/flags")
def flags(proposal_id: str = Query(""), assessment_id: str = Query(""), status: str = Query("open")) -> dict[str, Any]:
    return {"flags": store.flags(proposal_id, assessment_id, status)}


@router.post("/flags/{n}/clear")
def clear(n: int, request: Request) -> dict[str, Any]:
    return {"flag": _nf(store.clear_flag, n, _need(request))}


@router.get("/deals/{pid}")
def deal(pid: str) -> dict[str, Any]:
    from backend.dealdesk.rulebook import hook
    return {"proposal_id": pid, "flags": store.flags(pid), "checks": hook.findings(pid) if store.thresholds() else []}


@router.get("/pipeline")
def pipeline(refresh: bool = Query(False)) -> dict[str, Any]:
    rows = FA.pending(refresh=refresh)
    by = Counter(r.get("sector") or "Unknown" for r in rows)
    return {"pending": len(rows), "by_sector": [{"sector": s, "pending": n} for s, n in by.most_common()],
            "deals": [{k: r.get(k) for k in ("proposal_id", "customer", "rm", "status", "sector", "facility_type", "amount", "currency", "tenor_years",
                                              "dscr_post", "debt_ebitda_post", "ltv", "collateral_cover", "valuation_age_days", "lifetime_raroc", "hurdle", "rating")}
                      for r in rows]}


# ------------------------------------------------------------------ gold standards

@router.post("/gold")
async def gold_upload(request: Request, file: UploadFile | None = File(None), text: str = Form(""), title: str = Form("")) -> dict[str, Any]:
    name, body, sections, data = await _read(file, text)
    if not body.strip():
        raise HTTPException(422, "No text was found in that file.")
    cmp = GD.compare(body, sections)
    gid = store.new_id("GS")
    g = store.add_gold({"id": gid, "title": (title or (sections[0][0] if sections else name)).strip()[:200], "file_name": name, "text": body[:200_000],
                        "comparison": cmp, "uploaded_by": _who(request)})
    _RAW[gid] = (name, data)
    return {"gold": g, "question": "Apply these?" if cmp["differences"] else ""}


_RAW: dict[str, tuple[str, bytes]] = {}


def _warm() -> None:
    """The pending deals' facts computed once in the background after the service starts (about 30 s on the demo pipeline), so
    the first upload's impact is instant. Not under the tests; DEALDESK_RULEBOOK_WARM=0 turns it off."""
    import os
    import sys
    import threading
    import time
    if "pytest" in sys.modules or os.environ.get("DEALDESK_RULEBOOK_WARM", "1") == "0":
        return

    def run() -> None:
        time.sleep(20)
        for fn in (FA.pending, GD.today):
            try:
                fn()
            except Exception:  # noqa: BLE001 - the first upload computes them instead
                pass
    threading.Thread(target=run, name="rulebook-warm", daemon=True).start()


_warm()


@router.get("/gold")
def gold_list() -> dict[str, Any]:
    return {"gold": store.golds()}


@router.get("/gold/{gid}")
def gold_get(gid: str) -> dict[str, Any]:
    return {"gold": _nf(store.get_gold, gid)}


@router.post("/gold/{gid}/apply")
def gold_apply(gid: str, request: Request, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    by = _need(request)
    g = _nf(store.get_gold, gid)
    if g["status"] != "pending":
        raise HTTPException(409, f"This comparison is already {g['status']}.")
    want = set(body.get("ids") or [d["id"] for d in g["comparison"].get("differences", [])])
    from backend.dealdesk.rules import store as rstore
    made = []
    for d in g["comparison"].get("differences", []):
        if d["id"] not in want:
            continue
        r = d["rule"]
        made.append(rstore.create(text=r["text"], kind=r["kind"], params=r["params"], scope="bank", document=r.get("document") or "proposal",
                                  section=r.get("section") or "", section_label=r.get("section_label") or "", author=by,
                                  source_instruction=f"From the gold-standard document {g['title']} ({gid}): {d['finding']}",
                                  source={"via": "gold", "gold_id": gid, "difference": d["id"]}, origin=f"gold:{gid}"))
    house = None
    try:  # the gold standard joins the house-style corpus, so the profile (phrases, sentence length, openers) learns from it
        from backend.dealdesk.house_style import service as hs
        name, data = _RAW.get(gid) or (f"{gid}.txt", g["text"].encode())
        if not name.lower().endswith((".docx", ".txt", ".md")):
            name, data = f"{gid}.txt", g["text"].encode()
        house = hs.ingest(name, data, bank="house-ksa")
    except Exception as e:  # noqa: BLE001 - the rules stand on their own
        house = {"error": f"{type(e).__name__}: {str(e)[:160]}"}
    g = store.update_gold(gid, status="applied", applied_by=by, applied_at=store.now(), applied=[r["id"] for r in made])
    return {"gold": g, "rules": made, "house_style": house,
            "message": f"Applied: {len(made)} rule{'s' if len(made) != 1 else ''} for the bank, and the document joins the house-style corpus."}


@router.post("/gold/{gid}/dismiss")
def gold_dismiss(gid: str, request: Request) -> dict[str, Any]:
    by = _need(request)
    _nf(store.get_gold, gid)
    return {"gold": store.update_gold(gid, status="dismissed", applied_by=by, applied_at=store.now())}
