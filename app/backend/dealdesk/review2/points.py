"""The 12 review points (I16): each point's status, summary line, findings and the analysis behind it.

Status per point: "fail" (a critical finding), "attention" (major or minor findings), "pass" (checked, nothing found),
"not assessed" (no input available).
"""
from __future__ import annotations

import re
from typing import Any

from backend.dealdesk.review2 import analytics as A
from backend.dealdesk.review2.findings import POINTS, SEV_RANK

#: Words that need a number or source behind them (the anatomy's voice rule: no adjective without a number).
UNEVIDENCED = ("strong", "excellent", "robust", "healthy", "comfortable", "well established", "well-established", "reputed", "reputable",
               "leading", "significant", "solid", "sound", "prestigious", "renowned", "ample", "sufficient", "confident", "expected to",
               "is likely", "will continue", "proven")
BALANCE = ("risk", "weakness", "concern", "however", "mitigant", "mitigate", "breach", "exception", "delay", "overdue", "decline")
_NUM = re.compile(r"\d")


def language_check(ledger: dict[str, Any]) -> dict[str, Any]:
    lines = [ln for ln in ledger.get("lines") or [] if ln.get("kind") == "text"]
    hits = []
    for ln in lines:
        t = ln["text"]
        low = t.lower()
        words = [w for w in UNEVIDENCED if re.search(r"\b" + re.escape(w) + r"\b", low)]
        if words and not _NUM.search(t):
            hits.append({"line_id": ln["line_id"], "section": ln.get("section"), "text": t[:240], "words": words})
    full = " ".join(ln["text"].lower() for ln in lines)
    balance = [w for w in BALANCE if re.search(r"\b" + w, full)]
    one_sided = bool(lines) and len(balance) < 2
    out: dict[str, Any] = {"lines_checked": len(lines), "unevidenced": hits, "balance_words": balance, "one_sided": one_sided,
                           "source": {"relation": "dd_proposal", "key": {"memo": "ledger"}, "period": None}, "findings": []}
    out["headline"] = ((f"{len(hits)} of {len(lines)} memo sentences make a claim with no number or source" if hits else
                        f"All {len(lines)} memo sentences carry a number or a source") +
                       ("; the memo names no risk or weakness" if one_sided else "") + ".") if lines else "No memo text to check."
    if hits:
        out["findings"].append({**A.finding("LNG-01", 10, "minor", "Unevidenced claims in the memo",
                                            f"{len(hits)} sentence{'s' if len(hits) != 1 else ''} use " +
                                            ", ".join(sorted({w for h in hits for w in h['words']}))[:120] +
                                            " without a number or source (e.g. \"" + hits[0]["text"][:120] + "\").",
                                            [{"source": "Memo", "text": h["text"], "ref": out["source"]} for h in hits[:5]],
                                            len(hits), 0, "House style: every sentence a fact, number and date"),
                                "line_ids": [h["line_id"] for h in hits]})
    if one_sided:
        out["findings"].append(A.finding("LNG-02", 10, "minor", "One-sided memo", "The memo names no risk, weakness or mitigant; "
                                         "the credit comments must state the concerns and what mitigates them.",
                                         [{"source": "Memo", "text": f"{len(lines)} sentences, balance words found: {', '.join(balance) or 'none'}",
                                           "ref": out["source"]}], len(balance), 2, "House style: measured scepticism"))
    return out


def versions(sid: str, ledger: dict[str, Any], queries: dict[str, Any]) -> dict[str, Any]:
    from backend.dealdesk import review_facts as RF
    vs = [{"version": "submitted", "file": "stored memo", "lines": ledger.get("counts", {}).get("lines")}]
    up = RF.uploaded_memo_path(sid)
    if up.exists():
        import datetime as dt
        vs.append({"version": "uploaded", "file": up.name, "at": dt.datetime.fromtimestamp(up.stat().st_mtime, dt.timezone.utc).isoformat(timespec="seconds")})
    c = queries.get("counts") or {}
    open_n = queries.get("open", 0)
    out: dict[str, Any] = {"versions": vs, "queries": {"open": open_n, "answered": c.get("answered", 0), "closed": c.get("closed", 0)},
                           "source": {"relation": "dd_query", "key": {"deal_id": sid}, "period": None}, "findings": []}
    out["headline"] = (f"Reviewing the {vs[-1]['version']} memo ({len(vs)} version{'s' if len(vs) != 1 else ''}); "
                       f"{open_n} queries open, {c.get('answered', 0)} answered, {c.get('closed', 0)} closed.")
    if open_n:
        out["findings"].append(A.finding("VER-01", 11, "info", "Queries open with the RM", f"{open_n} quer{'y' if open_n == 1 else 'ies'} raised to the RM not yet answered.",
                                         [{"source": "Queries", "text": q["question"][:200], "ref": q["source"]} for q in queries.get("items", []) if q["status"] in ("queued", "sent")][:5],
                                         open_n, 0, "Credit Policy 3.4 Queries answered before recommendation"))
    if c.get("answered"):
        out["findings"].append(A.finding("VER-02", 11, "info", "Answers awaiting review", f"{c['answered']} RM answer{'s' if c['answered'] != 1 else ''} to review and close.",
                                         [], c["answered"], 0, ""))
    return out


def documents_findings(dl: dict[str, Any]) -> list[dict[str, Any]]:
    by_rule: dict[str, list[dict[str, Any]]] = {}
    for i in dl["items"]:
        if i["mandatory"] and i["status"] in ("pending", "expired"):
            by_rule.setdefault(i["rule_id"], []).append(i)
    out = []
    for rid, items in by_rule.items():
        i0 = items[0]
        parties = "; ".join(f"{i['for']}: " + ((i["note"][0].lower() + i["note"][1:] if i["note"][1:2].islower() else i["note"]) if i.get("note") else
                                                ("expired on " + str(i["expires"]) if i["status"] == "expired" else
                                                 "not provided" if i["status_source"] != "rule" else "not yet on file")) for i in items[:4])
        # a gap the evidence shows (or a user or Data Domains row records) keeps the rule's severity; an item simply not yet on
        # file for a new proposal is a minor completeness point until the RM is asked for it
        sev = i0["severity"] if any(i["status_source"] != "rule" for i in items) else "minor"
        f = A.finding(rid, 7 if i0["group"] in ("Legal", "Security") else 1, sev,
                      f"{i0['name']}: {'expired' if all(i['status'] == 'expired' for i in items) else 'not provided'}",
                      f"{i0['name']}. {parties}{'; and ' + str(len(items) - 4) + ' more' if len(items) > 4 else ''}. Required by {i0['clause']}.",
                      [{"source": "Document checklist", "text": f"{i['for']}: {i['status']}" + (f", expired {i['expires']}" if i['status'] == 'expired' else ""),
                        "ref": i["source"]} for i in items[:5]], len(items), 0, i0["clause"])
        f["document_items"] = [i["item_id"] for i in items]
        out.append(f)
    return out


def precedent_findings(prec: dict[str, Any]) -> list[dict[str, Any]]:
    hz = (prec.get("horizons") or [None])[0]
    if not hz or not hz.get("N") or hz.get("stage2_rate") is None or hz.get("book_stage2_rate") is None:
        return []
    r, b = hz["stage2_rate"], hz["book_stage2_rate"]
    if r > 0.2 and r > 1.5 * b:
        return [A.finding("PRC-01", 9, "major", "Similar deals deteriorated more than the book",
                          f"{hz['stage2']} of {hz['N']} similar borrowers ({A.pc(r)}) reached Stage 2 within {hz['quarters']} quarters ({hz['window']}), "
                          f"against {A.pc(b)} for the book.", [{"source": "Corporate book", "text": prec.get("line") or "",
                                                                "ref": {"relation": "corp_facility_quarter", "key": {"match": hz.get("match")}, "period": hz.get("window")}}],
                          round(r, 4), round(1.5 * b, 4), "Credit Policy 3.6 Precedent and peers")]
    return []


def _status(fs: list[dict[str, Any]], assessed: bool) -> str:
    if not assessed:
        return "not assessed"
    if any(f["severity"] == "critical" for f in fs):
        return "fail"
    if any(f["severity"] in ("major", "minor") for f in fs):
        return "attention"
    return "pass"


def assemble(findings: list[dict[str, Any]], blocks: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for n, name, scope in POINTS:
        fs = sorted([f for f in findings if f["point"] == n], key=lambda f: (SEV_RANK.get(f["severity"], 3), f["code"]))
        b = blocks.get(n) or {}
        assessed = b.get("assessed", True)
        st = _status(fs, assessed)
        if b.get("floor") == "attention" and st == "pass":
            st = "attention"
        out.append({"point": n, "name": name, "scope": scope, "status": st, "summary": b.get("summary") or "",
                    "lines": b.get("lines") or [], "counts": {s: sum(1 for f in fs if f["severity"] == s) for s in SEV_RANK},
                    "finding_ids": [f["finding_id"] for f in fs], "checks": b.get("checks") or {}, "analysis": b.get("analysis") or []})
    return out
