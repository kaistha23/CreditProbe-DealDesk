"""R14 U (K17): the Deal Desk proposal list over every deal the desk knows, read from Data Domains first.

Before R14 the Proposal pipeline listed the R11 proposal store only (15 seeded DD deals + uploads: 18 on the Mac),
so the R12/R13 test deals (twins R12-TWA Al Sahel and R12-TWB Gulf Meridian, R12-ESC, R12-SYN, the SME deals) and
the 27 pipeline applications (PL-xx) were reachable only by a typed URL. Now:

* the list is every row of `deal_desk.dd_deal` (49: 15 DD, 7 R12 demo, 27 PL) plus any upload made since the build,
  with the live status of DD deals and uploads from the Deal Desk store (a status change made today wins);
* the Pending filter counts exactly the deals the Pipeline tab counts (`pipeline.pending()`, which reads the same
  registry), so the two screens agree;
* search is fuzzy on the obligor / deal name and the id ("al sahal" → Al Sahel Building Materials Trading LLC,
  "twa" → R12-TWA, "dd 6" → DD-06);
* `find_named(question)` finds the deal a free-text question names, so a deal named in the Ask box opens the deal.

Deterministic: same rows, same order, same scores every run (N4).
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

PENDING = ("new", "in_review", "counter_offered")

SOURCE_LABEL = {"r16_customer": "Customer file", "dealdesk": "Deal Desk", "deal_desk": "Deal Desk", "uploaded": "Uploaded", "r12_demo": "Reference deal",
                "pipeline": "Pipeline set"}

# Words that never identify an obligor on their own (a question naming "the company" names no deal).
STOP = frozenset("""al el the and of for company co llc ltd limited est establishment trading group holding holdings
contracting industries industrial services national saudi arabian arabia modern united international commercial
general corporation corp inc limit limits renewal new project facility facilities proposal deal finance
working capital term loan line increase""".split())


# Places: a question about "Riyadh" is about the region, not about the one obligor whose name starts with it, so a
# place never names a deal on its own (two words do: "Yanbu Glass").
PLACES = frozenset("""riyadh jeddah dammam khobar makkah mecca madinah medina taif tabuk qassim hail jouf najran jazan jizan
yanbu jubail dhahran abha kharj unayzah buraidah qatif hofuf ahsa eastern northern southern western central najd red sea
gulf tihama asir baha qurayyat dawadmi rabigh khafji""".split())


# ------------------------------------------------------------------ normalising

def norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", (s or "").lower())).strip()


def _tokens(s: str) -> list[str]:
    return [t for t in norm(s).split(" ") if t]


def id_key(pid: str) -> str:
    """"R12-TWA" → "r12twa", "DD-06" → "dd06" (also matches "dd 6", "dd6")."""
    k = re.sub(r"[^a-z0-9]", "", (pid or "").lower())
    return re.sub(r"(?<=[a-z])0+(?=\d)", "", k)


def _tok_sim(q: str, t: str) -> float:
    if q == t:
        return 1.0
    if len(q) >= 3 and t.startswith(q):
        return 0.95
    if len(q) < 3:
        return 0.0
    return SequenceMatcher(None, q, t).ratio()


# ------------------------------------------------------------------ fuzzy match

def score(query: str, name: str, pid: str, alt: str = "") -> float:
    """0..1: how well `query` names this deal. Id matches score 1.0 (exact) / 0.9 (contained); a name matches when every
    query word is close to some word of the name (or the alternative deal name), averaged. 0 when any word misses."""
    q = norm(query)
    if not q:
        return 0.0
    qk, ik = id_key(q), id_key(pid)
    if qk and qk == ik:
        return 1.0
    if len(qk) >= 3 and (qk in ik or ik.endswith(qk)):
        return 0.9
    words = _tokens(name) + _tokens(alt)
    if not words:
        return 0.0
    sims = []
    for w in q.split(" "):
        best = max((_tok_sim(w, t) for t in words), default=0.0)
        if w in STOP and best < 1.0:
            best = 0.0 if best < 0.75 else best
        sims.append(best)
    if min(sims) < 0.75:
        return 0.0
    # Stop words alone do not name a deal ("al company" is not a search).
    if all(w in STOP for w in q.split(" ")):
        return 0.0
    return round(sum(sims) / len(sims) * 0.85, 4)


THRESHOLD = 0.66


def find_named(question: str, rows: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    """The deal a free-text question names, or None. An id anywhere in the question wins; else the best run of 1–4
    consecutive words that fuzzily matches an obligor's distinctive name (at least one non-stop word)."""
    rows = rows if rows is not None else all_rows()
    text = question or ""
    by_key = {id_key(r["proposal_id"]): r for r in rows}
    for m in re.finditer(r"\b(?:DD|PL|R12)\s*-?\s*[A-Z0-9]{1,6}\b", text, flags=re.I):
        r = by_key.get(id_key(m.group(0)))
        if r:
            return r
    words = _tokens(text)
    best, best_s = None, 0.0
    for n in (4, 3, 2, 1):
        for i in range(0, max(0, len(words) - n + 1)):
            span = words[i:i + n]
            if all(w in STOP or w in PLACES for w in span) or any(len(w) < 3 and w not in STOP for w in span):
                continue
            phrase = " ".join(span)
            for r in rows:
                s = score(phrase, r["obligor_name"], "")  # the obligor name only: deal titles are full of generic words
                # A single distinctive word must be a near-exact match to count (questions are full of words).
                if n == 1 and s < 0.8:
                    continue
                s += 0.02 * n  # longer phrases win ties
                if s > best_s:
                    best, best_s = r, s
        if best is not None and best_s >= THRESHOLD + 0.02 * n:
            return best
    return best if best_s >= THRESHOLD else None


# ------------------------------------------------------------------ rows

def _register() -> dict[str, dict[str, Any]]:
    try:
        from backend.dealdesk.data import deals
        return {r["proposal_id"]: r for r in deals.register()}
    except Exception:  # noqa: BLE001 - before the R12 build: the store alone
        return {}


def all_rows() -> list[dict[str, Any]]:
    """One summary row per deal: dd_deal (Data Domains) joined to the engine-ready proposal; live status for the
    Deal Desk store's deals and uploads."""
    from backend.dealdesk import proposals, registry_lookup
    reg = _register()
    store_ids = set(proposals.all_proposals())
    out: list[dict[str, Any]] = []
    for p in registry_lookup.all_deals():
        pid = p.get("proposal_id", "")
        r = reg.get(pid, {})
        if pid not in store_ids and r.get("status"):
            p = dict(p, status=r["status"])  # Data Domains first for the demo and pipeline deals
        p.setdefault("status", "new")
        p.setdefault("received", r.get("received_date", ""))
        try:
            s = proposals.summary(p)
        except Exception:  # noqa: BLE001 - a malformed upload never hides the rest of the list
            continue
        if pid in store_ids:
            src = "dealdesk" if re.fullmatch(r"DD-\d{2}", pid) else "uploaded"
        else:
            src = p.get("source") or r.get("source") or "pipeline"
        s["source"] = src
        s["source_label"] = SOURCE_LABEL.get(src, src)
        s["deal_name"] = r.get("deal_name", "") or ""
        s["product"] = r.get("product", "") or "corporate"
        s["branch"] = r.get("branch", "") or ""
        s["group_name"] = r.get("group_name", "") or p.get("obligor", {}).get("group_name", "")
        s["in_dd_deal"] = bool(r)
        s["pending"] = s["status"] in PENDING
        out.append(s)
    order = {"dealdesk": 0, "uploaded": 1, "r16_customer": 2, "r12_demo": 2, "pipeline": 3}
    return sorted(out, key=lambda x: (order.get(x["source"], 9), x["proposal_id"]))


def listing(status: str = "", sector: str = "", rating: str = "", rm: str = "", min_amount: float | None = None,
            max_amount: float | None = None, q: str = "", source: str = "") -> dict[str, Any]:
    rows = all_rows()
    total = len(rows)
    if status == "pending":
        rows = [r for r in rows if r["pending"]]
    elif status:
        rows = [r for r in rows if r["status"] == status]
    if sector:
        rows = [r for r in rows if r["sector"].lower() == sector.lower()]
    if rating:
        rows = [r for r in rows if r["rating"] == rating]
    if rm:
        rows = [r for r in rows if r["rm"].lower() == rm.lower()]
    if source:
        rows = [r for r in rows if r["source"] == source or r["source_label"].lower() == source.lower()]
    if min_amount is not None:
        rows = [r for r in rows if r["amount_sar_mn"] >= min_amount]
    if max_amount is not None:
        rows = [r for r in rows if r["amount_sar_mn"] <= max_amount]
    if q.strip():
        scored = [(score(q, r["obligor_name"], r["proposal_id"], r.get("deal_name", "")), r) for r in rows]
        rows = [dict(r, match=s) for s, r in sorted(scored, key=lambda x: (-x[0], x[1]["proposal_id"])) if s >= THRESHOLD]
    allr = all_rows() if (status or sector or rating or rm or source or q) else None
    base = allr if allr is not None else rows
    counts = {s: sum(1 for r in base if r["status"] == s) for s in ("new", "in_review", "counter_offered", "approved", "declined")}
    counts["pending"] = sum(1 for r in base if r["pending"])
    by_source = {}
    for r in base:
        by_source[r["source_label"]] = by_source.get(r["source_label"], 0) + 1
    return {"proposals": rows, "total": total, "counts": counts, "by_source": by_source,
            "source": "deal_desk.dd_deal (Data Domains) + Deal Desk store (live status, uploads)"}
