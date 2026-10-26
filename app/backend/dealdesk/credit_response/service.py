"""A credit-response case: the uploaded business request and documents, the steps run on them, the outputs.

    c = start([("business_request.pdf", b"..."), ("12_audited_fs__fy2025.pdf", b"...")], by="anne")
    for key in STEP_KEYS: c = step(c["case_id"], key)        # or run(case_id) for all of them
    response_docx(case_id) / response_pdf(case_id) / brief_docx(case_id)

Everything a case keeps is under var/dealdesk/credit_response/<case_id>/ (uploads, case.json); the deal and its rows are
published to Data Domains (dd_deal, dd_facility_limit, dd_security, dd_tnc, dd_project, dd_credit_response) under the
customer's proposal id.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.dealdesk import paths
from backend.dealdesk.credit_response import case as CS
from backend.dealdesk.credit_response import evidence as EV
from backend.dealdesk.credit_response import flow as FL
from backend.dealdesk.credit_response import reading as RD
from backend.dealdesk.credit_response import request as RQ

STEPS = [("read", "Read the business request and the documents"), ("deal", "Identify the customer and set up the deal"),
         *FL.STEPS, ("brief", "Feedback brief to the RM"), ("response", "Credit division's response (bank form)")]
STEP_KEYS = [k for k, _ in STEPS]
_LOCK = threading.RLock()


class CaseError(ValueError):
    pass


def root() -> Path:
    return paths.VAR / "credit_response"


def _dir(cid: str) -> Path:
    if not re.fullmatch(r"CRS-[0-9A-Za-z-]{6,40}", cid or ""):
        raise CaseError("No such case.")
    return root() / cid


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _save(c: dict[str, Any]) -> None:
    d = _dir(c["case_id"])
    d.mkdir(parents=True, exist_ok=True)
    (d / "case.json").write_text(json.dumps(c, default=str, indent=1))


def get(cid: str) -> dict[str, Any]:
    f = _dir(cid) / "case.json"
    if not f.exists():
        raise CaseError("No such case.")
    return json.loads(f.read_text())


def cases() -> list[dict[str, Any]]:
    out = []
    for f in sorted(root().glob("CRS-*/case.json"), reverse=True):
        try:
            c = json.loads(f.read_text())
        except ValueError:
            continue
        out.append({k: c.get(k) for k in ("case_id", "created", "by", "customer", "proposal_id", "status", "decision")})
    return out


def _is_request(name: str, text: str) -> bool:
    n = name.lower()
    return "business_request" in n or "business-request" in n or n.startswith("request") or EV.is_request(text)


def start(files: list[tuple[str, bytes]], by: str = "", request_name: str | None = None) -> dict[str, Any]:
    """Keep the uploads; work out which file(s) are the business request (several photos of its pages are one request)."""
    if not files:
        raise CaseError("Upload the business request (Word, PDF or photos of its pages) and any documents you have.")
    files = [(Path(n).name, b) for n, b in files if b]
    h = hashlib.sha256(b"".join(hashlib.sha256(b).digest() for _n, b in sorted(files))).hexdigest()
    cid = f"CRS-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{h[:8]}"
    d = _dir(cid)
    (d / "uploads").mkdir(parents=True, exist_ok=True)
    for n, b in files:
        (d / "uploads" / n).write_bytes(b)
    c = {"case_id": cid, "created": _now(), "by": by, "status": "uploaded", "files": [{"name": n, "bytes": len(b)} for n, b in files],
         "request_name": request_name, "steps": {}, "sha": h[:16]}
    _save(c)
    return view(c)


def _uploads(c: dict[str, Any]) -> list[tuple[str, bytes]]:
    d = _dir(c["case_id"]) / "uploads"
    return [(f["name"], (d / f["name"]).read_bytes()) for f in c["files"]]


def _page_key(name: str) -> tuple[str, int]:
    m = re.search(r"_p(\d+)\.\w+$", name)
    return (re.sub(r"_p\d+\.\w+$", "", name), int(m.group(1)) if m else 0)


def _read(c: dict[str, Any]) -> dict[str, Any]:
    reads: list[dict[str, Any]] = []
    ups = _uploads(c)
    named = any(_is_request(n, "") for n, _b in ups) or bool(c.get("request_name"))

    def rd(n: str, b: bytes) -> dict[str, Any]:
        try:
            return RD.read(n, b)
        except RD.ReadError as e:
            return {"name": n, "error": str(e), "text": "", "method": "", "sha": hashlib.sha256(b).hexdigest()[:16]}
    # photos are read (OCR) here only when they may be the request; the customer file reads the others
    for n, b in ups:
        if n.lower().endswith(EV.reading.IMAGE) and not (_is_request(n, "") or c.get("request_name") == n):
            reads.append({"name": n, "text": "", "method": "image (read by the customer file)", "sha": hashlib.sha256(b).hexdigest()[:16], "deferred": True})
        else:
            reads.append(rd(n, b))
    if not named and not any(r.get("text") and _is_request(r["name"], r["text"]) for r in reads):
        reads = [rd(n, b) if r.get("deferred") else r for r, (n, b) in zip(reads, ups)]
    req = [r for r in reads if r.get("text") and ((c.get("request_name") and r["name"] == c["request_name"]) or (not c.get("request_name") and _is_request(r["name"], r["text"])))]
    if not req:
        raise CaseError("No business request found among the uploads: upload the request (its first page says 'Action requested').")
    # one request: prefer Word, then PDF, then the photos of its pages in page order
    def rank(r: dict[str, Any]) -> tuple[int, str, int]:
        n = r["name"].lower()
        return (0 if n.endswith(".docx") else 1 if n.endswith(".pdf") else 2, *_page_key(n))
    req.sort(key=rank)
    first = req[0]
    used = [first] if not first["name"].lower().endswith(EV.reading.IMAGE) else [r for r in req if r["name"].lower().endswith(EV.reading.IMAGE)]
    text = "\n".join(r["text"] for r in used)
    method = first["method"] + (f" ({len(used)} pages)" if len(used) > 1 else "")
    name = first["name"] if len(used) == 1 else f"{_page_key(first['name'])[0]} (photos, {len(used)} pages)"
    request = RQ.parse(text, name, method)
    request["sha"] = hashlib.sha256(text.encode()).hexdigest()[:16]
    request["also_uploaded_as"] = [r["name"] for r in req if r not in used]
    req_names = {r["name"] for r in req}
    docs, intake_id, intake_pw = _documents(c, [(n, b) for n, b in _uploads(c) if n not in req_names],
                                            {r["name"]: r for r in reads if r["name"] not in req_names})
    pw = [f"The business request was read from {name} ({method}): {request['counts']['facilities']} limit lines, "
          f"{request['counts']['security']} security items and {request['counts']['terms']} terms.",
          f"{sum(1 for d in docs if d.get('doc_type') and not d['duplicate'])} supporting documents recognised"
          + (f", {sum(1 for d in docs if not d.get('doc_type'))} not recognised" if any(not d.get('doc_type') for d in docs) else "") + "."]
    if request["read_gaps"]:
        pw.append("Not read: " + "; ".join(request["read_gaps"][:3]) + ".")
    pw += intake_pw[1:3]
    return {"request": request, "documents": docs, "intake_id": intake_id, "texts": sorted(p.name for p in (_dir(c["case_id"]) / "texts").glob("*.txt")), "plain_words": pw,
            "headline": f"{request['fields'].get('name', 'Customer')}: SAR {request['totals'].get('proposed') or 0:,.1f}m proposed"}


def _documents(c: dict[str, Any], files: list[tuple[str, bytes]], reads: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], str, list[str]]:
    """The supporting documents: session i's customer file (classifier, fields, checklist, reconciliation, bank pull) when it
    is merged; the case's own reader of the demo contract's document types otherwise. Word and PDF texts are kept for
    credit's own reading (extension of time, contract clauses)."""
    tdir = _dir(c["case_id"]) / "texts"
    tdir.mkdir(parents=True, exist_ok=True)
    for n, r in reads.items():
        if r.get("text") and not n.lower().endswith(EV.reading.IMAGE):
            (tdir / (Path(n).stem + ".txt")).write_text(r["text"])
    own = []
    for n, r in reads.items():
        if r.get("error"):
            own.append({"name": n, "doc_type": None, "label": "Not readable", "fields": {}, "read_error": r["error"], "method": ""})
            continue
        if n.lower().endswith(EV.reading.IMAGE):
            own.append({"name": n, "doc_type": None, "label": "", "fields": {}, "method": r.get("method") or "image (OCR)", "sha": r.get("sha", ""), "read_error": ""})
            continue
        dt, _score = EV.classify(r["text"], n)
        f = EV.extract(r["text"], dt) if dt is not None else {}
        own.append({"name": n, "doc_type": dt.code if dt else None, "label": dt.label if dt else "Not recognised", "fields": f, "method": r["method"],
                    "sha": r["sha"], "read_error": ""})
    intake_id, pw = "", []
    try:
        from backend.dealdesk.intake import service as IS
    except Exception:  # noqa: BLE001 - session i not merged
        IS = None
    if IS is not None and files:
        try:
            v = IS.open_file(files, by=c.get("by") or "credit response")
            intake_id, pw = v["intake_id"], list(v.get("plain_words") or [])
            st = IS._load(intake_id)  # noqa: SLF001 - the file's documents with their typed fields
            by_name = {d["name"]: d for d in own}
            for x in st["documents"]:
                mine = by_name.get(x.get("file_name"))
                fields = {k: (v2.get("value") if isinstance(v2, dict) else v2) for k, v2 in (x.get("fields") or {}).items()}
                if mine is None:
                    continue
                if x.get("doc_type") not in (None, "unknown", "unreadable"):
                    own_f = mine.get("fields") or {}
                    merged = {**own_f, **{k: v2 for k, v2 in fields.items() if v2 not in (None, "", [])}}
                    for k, v2 in own_f.items():  # a table: the longer reading wins (a PDF's wrapped cells read differently)
                        if isinstance(v2, list) and isinstance(merged.get(k), list) and len(v2) > len(merged[k]):
                            merged[k] = v2
                    mine.update({"doc_type": x["doc_type"], "label": x.get("doc_label") or mine.get("label"), "fields": merged,
                                 "subject": x.get("subject") or "", "method": x.get("read_method") or mine.get("method"), "classified_by": "session i intake"})
        except Exception as e:  # noqa: BLE001 - the case reads the documents itself
            pw = [f"The customer file could not be opened ({type(e).__name__}); the documents were read by the case itself."]
    for d in own:
        d.setdefault("subject", str((d.get("fields") or {}).get("full_name") or (d.get("fields") or {}).get("project_id") or ""))
    seen: dict[tuple[str, str], dict[str, Any]] = {}
    for d in own:
        if not d.get("doc_type"):
            continue
        k = (d["doc_type"], str(d.get("subject") or ""), str((d.get("fields") or {}).get("certificate_number") or ""),
             str((d.get("fields") or {}).get("fiscal_year") or (d.get("fields") or {}).get("period_to") or ""))
        if k not in seen or len(d["fields"]) > len(seen[k]["fields"]):
            seen[k] = d
    keep = {id(v) for v in seen.values()}
    for d in own:
        d["duplicate"] = bool(d.get("doc_type")) and id(d) not in keep
    return own, intake_id, pw


def _deal(c: dict[str, Any]) -> dict[str, Any]:
    from backend.dealdesk.credit_response import projects as PJ
    rd = c["steps"]["read"]["data"]
    request, docs = rd["request"], [d for d in rd["documents"] if not d.get("duplicate")]
    m = CS.match(request, docs, "\n".join(request["sections"].get("header", []) + request.get("preamble", [])))
    pid = m["proposal_id"] or CS.new_id(request["sha"])
    p = CS.proposal(request, docs, m, pid)
    CS.save_store(p)
    extra = PJ.rows(pid, p["obligor"]["obligor_id"], docs, request)
    pub = CS.publish(p, request, m, c["case_id"], extra)
    if rd.get("intake_id"):
        try:
            from backend.dealdesk.intake import service as IS
            IS.attach(rd["intake_id"], pid)
        except Exception:  # noqa: BLE001 - the file stays unattached; the response reads it by its id
            pass
    _clear_caches(pid)
    a = p["ask"]
    pw = [f"{p['obligor']['name']} is {'an existing customer' if m['existing'] else 'new to the bank'} ({m['how']}); the deal is {pid}.",
          f"The engines read the ask as SAR {a['amount']:,.1f}m ({p['request']['amount_basis']}), {a['facility_type'].replace('_', ' ')}, "
          f"{a['tenor_years']} year{'s' if a['tenor_years'] != 1 else ''}, on top of SAR {p['obligor']['existing_exposure_sar_mn']:,.1f}m outstanding."]
    return {"proposal_id": pid, "match": m, "ask": {k: a.get(k) for k in ("amount", "facility_type", "tenor_years", "margin_bps", "commission_bps", "funded_share_pct", "cash_margin_pct")},
            "amount_basis": p["request"]["amount_basis"], "published": pub, "plain_words": pw, "headline": pw[0]}


def _clear_caches(pid: str) -> None:
    for mod, attr in (("backend.dealdesk.review_workspace", "_CACHE"), ("backend.dealdesk.optimizer", "_CACHE"), ("backend.dealdesk.stressproof.matrix", "_RUNS")):
        try:
            m = __import__(mod, fromlist=[attr])
            cache = getattr(m, attr, None)
            if isinstance(cache, dict):
                for k in [k for k in cache if pid in str(k)]:
                    cache.pop(k, None)
        except Exception:  # noqa: BLE001
            pass
    try:
        from backend.dealdesk.house_style.bankform import cp_writers
        getattr(cp_writers, "_CACHE", {}).clear()
    except Exception:  # noqa: BLE001
        pass


def _flow_step(c: dict[str, Any], key: str) -> dict[str, Any]:
    pid = c["steps"]["deal"]["data"]["proposal_id"]
    doc = None
    if key == "check":
        req = c["steps"]["read"]["data"]["request"]
        doc = RQ.as_check_doc(req, req["sha"])
    return FL.run_step(key, pid, doc)


def _brief(c: dict[str, Any]) -> dict[str, Any]:
    from backend.dealdesk.credit_response import brief as BR
    b = BR.build(c)
    return {**b, "plain_words": b["plain_words"], "headline": b["subject"]}


def _response(c: dict[str, Any]) -> dict[str, Any]:
    from backend.dealdesk.credit_response import response as RS
    paper = RS.build(c)
    f = _dir(c["case_id"]) / "response_paper.json"
    f.write_text(json.dumps(paper, default=str))
    s = paper["summary"]
    return {"sections": [{k: x[k] for k in ("key", "n", "heading", "part")} | {"blocks": len(x["blocks"])} for x in paper["sections"]],
            "summary": s, "plain_words": s["plain_words"], "headline": s["decision"]}


def step(cid: str, key: str) -> dict[str, Any]:
    if key not in STEP_KEYS:
        raise CaseError(f"Unknown step {key}.")
    with _LOCK:
        c = get(cid)
        i = STEP_KEYS.index(key)
        missing = [k for k in STEP_KEYS[:i] if k not in c["steps"] and k in ("read", "deal")]
        for k in missing:
            c = step(cid, k)
        import time
        t0 = time.perf_counter()
        if key in dict(FL.STEPS):
            res = _flow_step(c, key)
        else:
            try:
                data = {"read": _read, "deal": _deal, "brief": _brief, "response": _response}[key](c)
                res = {"key": key, "label": dict(STEPS)[key], "status": "done", "plain_words": data.pop("plain_words", []), "headline": data.pop("headline", ""),
                       "data": data}
            except CaseError:
                raise
            except Exception as e:  # noqa: BLE001
                if key in ("read", "deal"):
                    raise CaseError(f"{dict(STEPS)[key]} failed: {type(e).__name__}: {e}") from e
                res = {"key": key, "label": dict(STEPS)[key], "status": "error", "plain_words": [f"{dict(STEPS)[key]} could not be written ({type(e).__name__})."],
                       "headline": "", "data": {"error": f"{type(e).__name__}: {e}"[:400]}}
            res["seconds"] = round(time.perf_counter() - t0, 2)
        res["at"] = _now()
        c["steps"][key] = res
        if key == "read":
            c["customer"] = res["data"]["request"]["fields"].get("name")
        if key == "deal":
            c["proposal_id"] = res["data"]["proposal_id"]
            for k in STEP_KEYS[i + 1:]:  # a new deal: the later steps run again
                c["steps"].pop(k, None)
        if key == "response":
            c["decision"] = res.get("headline")
            c["status"] = "done"
            _publish_case(c)
        else:
            c["status"] = "running"
        _save(c)
        return view(c)


def run(cid: str) -> dict[str, Any]:
    c = get(cid)
    for k in STEP_KEYS:
        c = step(cid, k)
    return c


def view(c: dict[str, Any]) -> dict[str, Any]:
    """The case as the screen shows it (the request text and document texts left out)."""
    out = {k: v for k, v in c.items() if k != "steps"}
    out["steps"] = [{"key": k, "label": lb, **({kk: vv for kk, vv in c["steps"][k].items() if kk != "key"} if k in c["steps"] else {"status": "pending"})}
                    for k, lb in STEPS]
    out["next"] = next((k for k in STEP_KEYS if k not in c["steps"]), None)
    return out


def paper(cid: str) -> dict[str, Any]:
    f = _dir(cid) / "response_paper.json"
    if not f.exists():
        step(cid, "response")
    return json.loads(f.read_text())


def response_docx(cid: str) -> tuple[bytes, str]:
    from backend.dealdesk.credit_response import response as RS
    return RS.docx(paper(cid))


def response_pdf(cid: str) -> tuple[bytes, str]:
    from backend.dealdesk.credit_response import response as RS
    return RS.pdf(paper(cid))


def brief_docx(cid: str) -> tuple[bytes, str]:
    from backend.dealdesk.credit_response import brief as BR
    c = get(cid)
    if "brief" not in c["steps"]:
        c = get(step(cid, "brief")["case_id"])
    return BR.docx(c)


def _publish_case(c: dict[str, Any]) -> None:
    try:
        from backend.dealdesk.credit_response import relation as RL
        RL.publish_case(c)
    except Exception:  # noqa: BLE001 - the case stays on disk; Data Domains catches up on the next run
        pass
