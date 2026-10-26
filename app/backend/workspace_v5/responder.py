"""The project thread's responder: answers only from the project's data domains, documents and instructions.

Deterministic and grounded. No model is called (none is needed); every figure is read from the books, the Early
Warning release or the What-If engine, and every passage is quoted from a document uploaded to the project.

  1. Which domains does the question touch? (keywords, with the corporate sector names taken out first, so
     "Retail Trade" is a corporate sector and not the retail book)
  2. Any of them outside the project's access rules -> a clear refusal naming what the project uses.
  3. Otherwise: figures from the allowed book (period from the question, else the project's focus period, else the
     latest), the Early Warning headline, a What-If scenario from the library, bureau / Open Banking signals on the
     retail book, and the best-matching document passages.
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

import pandas as pd

from backend.workspace_v5 import compute, paths
from backend.workspace_v5.book import mn, pct

DOMAINS: dict[str, str] = {
    "corporate": "Cockpit corporate book",
    "retail": "Cockpit retail book",
    "ews": "Early Warning",
    "whatif": "What-If",
    "bureau": "Bureau",
    "open_banking": "Open Banking",
    "scorecard": "Scorecard",
    "dealdesk": "Deal Desk",
}
BOOK_DOMAINS = ("corporate", "retail")

_KEYWORDS: dict[str, tuple[str, ...]] = {
    "retail": (r"\bretail\b", r"\bmortgages?\b", r"\bcredit cards?\b", r"\bcards?\b", r"\bpersonal finance\b",
               r"\bauto finance\b", r"\bbnpl\b", r"\bbuy now pay later\b", r"\bconsumer\b"),
    "corporate": (r"\bcorporate\b", r"\bsectors?\b", r"\bsub-?sectors?\b", r"\bborrowers?\b", r"\bfacilit(y|ies)\b"),
    "ews": (r"\bearly warning\b", r"\bews\b", r"\bwatch-?list\b", r"\bwarning\b", r"\balerts?\b", r"\bbands?\b"),
    "whatif": (r"\bwhat-?if\b", r"\bscenarios?\b", r"\bstress\b", r"\bshocks?\b", r"\boil\b", r"\brecession\b",
               r"\brates? up\b", r"\bunemployment\b", r"\bhouse prices?\b"),
    "bureau": (r"\bbureau\b", r"\bsimah\b", r"\benquir(y|ies)\b", r"\binquir(y|ies)\b"),
    "open_banking": (r"\bopen banking\b", r"\binflows?\b", r"\bsalary\b", r"\bsalaries\b"),
    "scorecard": (r"\bscorecards?\b", r"\bgini\b", r"\bpsi\b", r"\bauc\b", r"\bvalidation\b"),
}
_STOP = set("the a an and or of in on for to by with what which how is are was were be this that these those from "
            "at as it its into than then there their our we you your me my show tell give about does did do much "
            "many per vs versus between over under q1 q2 q3 q4 sar".split())

_SCENARIOS = {  # keyword -> library key, per book
    "corporate": [("oil", "oil-shock"), ("rate", "rates-up"), ("recession", "recession"), ("downgrade", "downgrade-1"),
                  ("construction", "construction"), ("real estate", "real-estate")],
    "retail": [("unemployment", "unemployment"), ("rate", "rates-up"), ("house price", "house-prices"),
               ("card", "cards"), ("recession", "recession")],
}
BAND_ORDER = ["critical", "severe", "high", "moderate", "low", "none"]


def domain_list(keys: list[str]) -> str:
    names = [DOMAINS[k] for k in keys if k in DOMAINS]
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


@lru_cache(maxsize=2)
def segment_values(book: str) -> tuple[str, ...]:
    col = "sector" if book == "corporate" else "product"
    return tuple(sorted(str(v) for v in compute.frame(book)[col].unique()))


def mentioned_domains(question: str) -> list[str]:
    q = question.lower()
    for s in segment_values("corporate"):
        q = q.replace(s.lower(), " corporate ")
    for s in segment_values("retail"):
        q = q.replace(s.lower(), " retail ")
    out = [d for d, pats in _KEYWORDS.items() if any(re.search(p, q) for p in pats)]
    # R10 C4: "borrowers" / "facilities" alone are generic words, not the corporate book: "how many borrowers are
    # on the watchlist?" in a retail + Early Warning project asks Early Warning, it must not be refused.
    if "corporate" in out and len(out) > 1 and not re.search(r"\b(corporate|sub-?sectors?|sectors?)\b", q):
        out.remove("corporate")
    return out


def _tokens(text: str) -> list[str]:
    """Words of three letters or more, cut to a five-letter stem (so 'contractors' meets 'contractor')."""
    return [t[:5] for t in re.findall(r"[a-z0-9][a-z0-9\-]{2,}", text.lower()) if t not in _STOP]


def passages(question: str, documents: list[dict[str, Any]], limit: int = 2, context: str = "") -> list[dict[str, Any]]:
    """The document paragraphs that share the most words with the question (at least two; the project's focus words
    count as context)."""
    want = set(_tokens(question)) | set(_tokens(context))
    if not want:
        return []
    scored = []
    for d in documents:
        for i, para in enumerate(p.strip() for p in re.split(r"\n\s*\n|\n(?=[A-Z0-9•\-])", d.get("text") or "")):
            if len(para) < 80 or " | " in para:
                continue
            have = set(_tokens(para))
            score = len(want & have)
            if score >= 2:
                scored.append((score, -i, d, para))
    scored.sort(key=lambda x: (-x[0], -x[1], x[2]["id"]))
    out, seen = [], set()
    for score, _, d, para in scored:
        if (d["id"], para[:60]) in seen:
            continue
        seen.add((d["id"], para[:60]))
        out.append({"doc_id": d["id"], "name": d["name"], "text": para[:700], "score": score})
        if len(out) >= limit:
            break
    return out


def _measures_asked(q: str) -> list[str]:
    ms = []
    if re.search(r"\b(ead|exposure)", q):
        ms.append("ead")
    if re.search(r"\b(ecl|provision|impairment|loss allowance)", q):
        ms.append("ecl")
    if re.search(r"stage\s*2|sicr", q):
        ms += ["stage2_ead", "stage2_share_pct"]
    if re.search(r"stage\s*3|default", q):
        ms.append("stage3_ead")
    if "coverage" in q:
        ms.append("coverage_pct")
    return list(dict.fromkeys(ms)) or ["ead", "ecl", "coverage_pct", "stage2_share_pct"]


def _prev(book: str, period: str) -> str | None:
    ps = compute.periods(book)
    i = ps.index(period)
    return ps[i - 1] if i > 0 else None


def book_answer(book: str, q: str, period: str, focus: str | None) -> dict[str, Any]:
    col = "sector" if book == "corporate" else "product"
    named = [s for s in segment_values(book) if s.lower() in q]
    by = None
    if re.search(r"\bby (sector|sub-?sector|product|sub-?product|stage|region)", q):
        word = re.search(r"\bby (sector|sub-?sector|product|sub-?product|stage|region)", q).group(1).replace("-", "_")
        by = {"sector": "sector", "sub_sector": "sub_sector", "subsector": "sub_sector", "product": "product",
              "sub_product": "sub_product", "subproduct": "sub_product", "stage": "stage", "region": "region"}[word]
        if by not in compute.BOOKS[book]["dims"]:
            by = None
    segs = named or ([focus] if focus and focus in segment_values(book) and by not in ("sector", "product") else [])
    measures = _measures_asked(q)
    spec: dict[str, Any] = {"engine": "book", "book": book, "by": by, "measures": measures}
    if segs:
        spec["filters"] = {col: segs}
    now = compute.book_result(spec, period)
    prev_p = _prev(book, period)
    before = compute.book_result(spec, prev_p) if prev_p else None
    scope = (", ".join(segs) + " in the ") if segs else "the "
    unit = {"sar_mn": mn, "pct": lambda v: pct(v, 2), "int": lambda v: f"{int(v):,}"}
    parts = []
    bf = {f["key"]: f for f in (before or {}).get("figures", [])}
    for f in now["figures"]:
        s = f"{f['label']} {unit[f['unit']](f['value'])}"
        if f["key"] in bf and prev_p:
            old = bf[f["key"]]["value"]
            ch = f["value"] - old
            move = (f", {'+' if ch >= 0 else '-'}{mn(abs(ch))}" + (f" ({ch / old * 100:+.1f}%)" if old else "")
                    if f["unit"] == "sar_mn" else "")
            s += f" ({unit[f['unit']](old)} at {prev_p}{move})"
        parts.append(s)
    text = f"From {scope}{book} book at {period}: " + "; ".join(parts) + "."
    if by and now["table"]:
        m0 = measures[0]
        u0 = unit[compute.MEASURES[m0][1]]
        rows = now["table"]["rows"]
        text += (f" By {compute.BOOKS[book]['dims'][by].lower()}, {compute.MEASURES[m0][0]}: "
                 + "; ".join(f"{r[by]} {u0(r[m0])}" for r in rows[:6]) + ("; …" if len(rows) > 6 else "") + ".")
    return {"text": text, "result": now, "spec": spec, "previous_period": prev_p,
            "citation": {"kind": "data", "label": f"{DOMAINS[book]} · {now['source']}",
                         "href": "/cockpit/data"}}


@lru_cache(maxsize=4)
def _ews_table(book: str, name: str) -> pd.DataFrame:
    rel = paths.EWS_CORP if book == "corporate" else paths.EWS_RETAIL
    return pd.read_parquet(paths.EWS / rel / f"{name}.parquet")


def ews_answer(book: str, period: str, focus: str | None) -> dict[str, Any]:
    pcol = "reporting_quarter" if book == "corporate" else "reporting_month"
    seg_col = "sector" if book == "corporate" else "product"
    if focus:
        s = _ews_table(book, "ews_series_segment")
        s = s[(s[pcol] == period) & (s[seg_col] == focus)]
        where = f"{focus} at {period}"
    else:
        s = _ews_table(book, "ews_series_portfolio")
        s = s[s[pcol] == period]
        where = f"the {book} book at {period}"
    g = s.groupby("ews_band").agg(n=("n", "sum"), ead=("ead_sar_mn", "sum"))
    bands = [b for b in BAND_ORDER if b in g.index] + [b for b in g.index if b not in BAND_ORDER]
    words = [f"{b} {int(g.loc[b, 'n']):,} ({mn(float(g.loc[b, 'ead']))})" for b in bands]
    r = _ews_table(book, "ews_reason_period")
    r = r[r[pcol] == period].sort_values(["ead_sar_mn", "reason"], ascending=[False, True]).head(3)
    reasons = [f"{row.reason} ({int(row.n):,}, {mn(float(row.ead_sar_mn))})" for row in r.itertuples()]
    text = (f"Early Warning on {where}, by band: " + "; ".join(words) + "."
            + (f" Top warning reasons on the book: {'; '.join(reasons)}." if reasons else ""))
    return {"text": text, "citation": {"kind": "data", "label": f"Early Warning · {book}",
                                       "href": f"/early-warning?domain={book}" + (f"&segment={focus}" if focus else "")}}


def whatif_answer(book: str, q: str, period: str) -> dict[str, Any]:
    from backend.whatif_v5.chat import library
    entries = {e["key"]: e for e in library.STANDARD[book]}
    key = next((k for word, k in _SCENARIOS[book] if word in q and k in entries), None)
    if not key:
        names = ", ".join(e["name"] for e in library.STANDARD[book])
        return {"text": f"What-If scenarios for the {book} book: {names}. Name one (for example 'oil') and I will "
                        "run it.", "citation": {"kind": "data", "label": "What-If library",
                                                "href": f"/what-if?domain={book}"}}
    e = entries[key]
    sc = library.scenario_for(book, e, "")
    spec = {"engine": "whatif", "book": book, "method": "delta", "scenario": sc.to_dict()}
    try:
        res = compute.whatif_result(spec, period)
    except compute.ComputeError:
        res = compute.whatif_result(spec, None)
    f = {x["key"]: x["value"] for x in res["figures"]}
    top = res["table"]["rows"][:3]
    text = (f"What-If '{e['name']}' on the {book} book at {res['period']} (Delta method): ECL "
            f"{mn(f['reported_ecl'])} → {mn(f['scenario_ecl'])} ({'+' if f['change'] >= 0 else ''}{mn(f['change'])}, "
            f"{pct(f['change_pct'], 2)}). Largest moves: "
            + "; ".join(f"{r['segment']} {'+' if r['change'] >= 0 else ''}{mn(r['change'])}" for r in top) + ".")
    return {"text": text, "result": res, "spec": spec,
            "citation": {"kind": "data", "label": f"What-If · {res['source']}", "href": f"/what-if?domain={book}"}}


@lru_cache(maxsize=1)
def _retail_signals() -> pd.DataFrame:
    return pd.read_parquet(paths.EWS / paths.EWS_RETAIL / "ews_retail_exposure.parquet",
                           columns=["reporting_month", "account_id", "customer_id", "bureau_score", "enquiries_3m",
                                    "new_external_default", "salary_interruption_flag", "inflow_trend_pct",
                                    "returned_payments_3m"])


def bureau_answer(period: str) -> dict[str, Any]:
    d = _retail_signals()
    x = d[d.reporting_month == period].drop_duplicates("customer_id")
    text = (f"Bureau signals on the retail book at {period} ({len(x):,} customers): average bureau score "
            f"{x.bureau_score.mean():.0f}; {int((x.enquiries_3m >= 5).sum()):,} customers with 5 or more enquiries in "
            f"3 months; {int(x.new_external_default.sum()):,} new external defaults.")
    return {"text": text, "citation": {"kind": "data", "label": f"Bureau · {paths.EWS_RETAIL}",
                                       "href": "/early-warning?domain=retail"}}


def open_banking_answer(period: str) -> dict[str, Any]:
    d = _retail_signals()
    x = d[d.reporting_month == period].drop_duplicates("customer_id")
    text = (f"Open Banking signals on the retail book at {period} ({len(x):,} customers): "
            f"{int(x.salary_interruption_flag.sum()):,} salary interruptions; median inflow trend "
            f"{x.inflow_trend_pct.median():.1f}%; {int((x.returned_payments_3m > 0).sum()):,} customers with returned "
            "payments in 3 months.")
    return {"text": text, "citation": {"kind": "data", "label": f"Open Banking · {paths.EWS_RETAIL}",
                                       "href": "/early-warning?domain=retail"}}


def respond(project: dict[str, Any], question: str, documents: list[dict[str, Any]],
            history: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """One reply through the forked Cockpit conversation (backend/ai_work on backend/convo), scoped to the project's
    domains, documents and instructions: {text, refused, outside, domains_used, citations, figures, table, tables,
    passages, stages, source}."""
    from backend.ai_work import agent
    allowed = [d for d in project.get("domains") or [] if d in DOMAINS]
    focus = dict(project.get("focus") or {})
    scope = agent.Scope(
        domains=[*allowed, "product"], name=f"the project “{project.get('name', '')}”", noun="project",
        instructions=str(project.get("instructions") or ""), documents=documents, focus=focus,
        charter=("You answer inside a CreditProbe project: a workspace with its own data domains, documents and "
                 "instructions. Answer only from them; follow the project instructions; cite the documents you use."))
    out = agent.converse(question, scope, history or [], purpose="project")
    passages_found: list[dict[str, Any]] = []
    for c in out.get("citations") or []:
        if c.get("kind") == "document":
            passages_found.append({"doc_id": c.get("doc_id"), "name": c.get("label")})
    keep = ("refused", "outside", "domains_used", "citations", "figures", "table", "tables", "understood", "stages",
            "source", "suggestions")
    return {"text": out["text"], **{k: out.get(k) for k in keep}, "passages": passages_found,
            "removed": (out.get("validation") or {}).get("removed") or []}


def respond_r3(project: dict[str, Any], question: str, documents: list[dict[str, Any]]) -> dict[str, Any]:
    """The r3 keyword responder (kept for reference; project threads answer through `respond`)."""
    allowed = [d for d in project.get("domains") or [] if d in DOMAINS]
    q = question.lower().strip()
    asked = mentioned_domains(question)
    outside = [d for d in asked if d not in allowed]
    if outside:
        return {"text": (f"This project only uses {domain_list(allowed) or 'its documents'}. "
                         f"{domain_list(outside)} {'is' if len(outside) == 1 else 'are'} outside its scope, so I will "
                         "not answer from it here. Ask the project owner to add it under Access, or ask outside the "
                         "project."),
                "refused": True, "outside": outside, "domains_used": [], "citations": [], "figures": [],
                "table": None, "passages": []}
    focus = project.get("focus") or {}
    books = [d for d in asked if d in BOOK_DOMAINS] or [d for d in allowed if d in BOOK_DOMAINS][:1]
    parts: list[str] = []
    citations: list[dict[str, Any]] = []
    figures: list[dict[str, Any]] = []
    table = None
    used: list[str] = []
    for book in books:
        period = compute.period_in(book, question) or (focus.get("period") if focus.get("book") == book else None) \
            or compute.periods(book)[-1]
        fseg = focus.get("segment") if focus.get("book") == book else None
        only_other = any(d in asked for d in ("ews", "whatif", "bureau", "open_banking", "scorecard"))
        if not only_other or any(re.search(p, q) for p in (r"\bead\b", r"\becl\b", r"stage", r"exposure", "coverage")):
            a = book_answer(book, q, period, fseg)
            parts.append(a["text"])
            citations.append(a["citation"])
            figures += a["result"]["figures"]
            table = table or a["result"]["table"]
            used.append(book)
        if "ews" in allowed and ("ews" in asked or not only_other and "ews" in allowed and not asked):
            a = ews_answer(book, period, fseg)
            parts.append(a["text"])
            citations.append(a["citation"])
            used.append("ews")
        if "whatif" in asked:
            a = whatif_answer(book, q, period)
            parts.append(a["text"])
            citations.append(a["citation"])
            if a.get("result"):
                figures += a["result"]["figures"][:4]
                table = a["result"]["table"]
            used.append("whatif")
        if book == "retail" and "bureau" in asked:
            a = bureau_answer(period)
            parts.append(a["text"])
            citations.append(a["citation"])
            used.append("bureau")
        if book == "retail" and "open_banking" in asked:
            a = open_banking_answer(period)
            parts.append(a["text"])
            citations.append(a["citation"])
            used.append("open_banking")
    if "scorecard" in asked:
        parts.append("Scorecard validations are run and kept in Scorecard; open it for the Gini, PSI and calibration "
                     "results.")
        citations.append({"kind": "data", "label": "Scorecard", "href": "/scorecard-validation"})
        used.append("scorecard")
    found = passages(question, documents, context=str(focus.get("segment") or ""))
    if found:
        parts.append("From the project documents: " + " ".join(f"“{p['text']}” ({p['name']})" for p in found))
        citations += [{"kind": "document", "label": p["name"], "doc_id": p["doc_id"]} for p in found]
    if project.get("instructions"):
        citations.append({"kind": "instructions", "label": "Project instructions"})
    if not parts:
        parts.append(f"I answer from this project's sources only: {domain_list(allowed) or 'no data domains'}"
                     f"{' and ' + str(len(documents)) + ' documents' if documents else ''}. Ask about EAD, ECL, "
                     "Stage 2 or coverage, the Early Warning bands, a What-If scenario, or something in the documents.")
    return {"text": "\n\n".join(parts), "refused": False, "outside": [], "domains_used": list(dict.fromkeys(used)),
            "citations": citations, "figures": figures, "table": table, "passages": found}
