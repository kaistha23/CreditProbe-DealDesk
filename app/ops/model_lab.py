#!/usr/bin/env python3
"""The model lab: run Deal Desk on one model, then compare two runs (Opus against an open-weight model).

    .venv/bin/python ops/model_lab.py run --experiment opus-baseline
    .venv/bin/python ops/model_lab.py run --experiment qwen38-27b-fp8 --stages thread,desk,draft,bankform
    .venv/bin/python ops/model_lab.py compare --baseline opus-baseline --candidate qwen38-27b-fp8 [--judge]
    .venv/bin/python ops/model_lab.py list
    .venv/bin/python ops/model_lab.py dry [--efficiency both|off|on]   # Round E: before/after token estimate, no model

`run` drives the RUNNING Deal Desk service (port 8508, `--api` to change) over HTTP, exactly as the UI does, with
whatever model the service was started on (ops/v5.sh with CONVO_PROVIDER / CONVO_OPENAI_BASE_URL / CONVO_EXPERIMENT in
its environment: the experiment name the service reports must match `--experiment`, or pass --no-check). It writes
var/model_lab/<experiment>/:

  manifest.json              the gateway the service reported (provider, model, quant, base URL), commit, time, stages
  thread/<pid>__<n>.json     one Deal Desk question (the 21 of tests/v5/dealdesk_ui/test_convo.py plus --questions):
                             the answer blocks, source (model / deterministic), validation (figures checked, untraced),
                             the engine tools called, elapsed ms
  desk/<n>.json              the portfolio questions on the desk thread
  draft/<pid>.json           the house-style proposal draft: per section the method (model, or template with the reason
                             the model's text was rejected), the house-style score, the text
  bankform/<pid>.json        the bank-form proposal with polish=true: the lines the model changed
  telemetry.json             every model call and every turn the service recorded for this experiment (tokens, ms)

`compare` scores a candidate against a baseline run, without any model unless --judge:
  thread   per question: same source? figures in the answer (numbers) and their overlap with the baseline, figures the
           validator removed, tools called (set overlap), words; per experiment: model-answer rate, validation pass
           rate, mean figure overlap
  draft    per section: method (model acceptance rate), rejection reasons, score, text similarity to the baseline
  bankform lines changed by polish
  tokens   per stage and per deal: calls, input/output/reasoning tokens, model time; candidate / baseline ratios
  --judge  Opus (MODEL_LAB_JUDGE_MODEL, key CONVO_ANTHROPIC_API_KEY or ANTHROPIC_API_KEY) scores each candidate
           answer and draft section 1-5 on faithfulness, completeness and clarity against the baseline and the facts
and writes var/model_lab/compare_<baseline>_vs_<candidate>.{json,md,csv}.

Standard library only for `run` and `compare` (the judge needs the anthropic package, in the venv). No key printed.
"""
from __future__ import annotations

import argparse
import csv
import difflib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

V5 = Path(__file__).resolve().parents[1]
LAB = V5 / "var" / "model_lab"
API = os.environ.get("DEALDESK_API_ORIGIN") or f"http://127.0.0.1:{os.environ.get('DEALDESK_API_PORT', '8508')}"
DESK = "/api/v1/dealdesk/desk"
ENGINE = "/api/v1/dealdesk"

# The golden question set (tests/v5/dealdesk_ui/test_convo.py): intent, proposal, question. None = the desk thread.
QUESTIONS: list[tuple[str, str | None, str]] = [
    ("explain", "DD-01", "Why does the ask fail?"),
    ("explain", "DD-02", "Why does the ask fail?"),
    ("explain", "DD-09", "Explain the sector constraint"),
    ("optimise", "DD-01", "Optimise"),
    ("optimise", "DD-01", "Client won't accept above SAIBOR + 250"),
    ("optimise", "DD-01", "Keep the amount at 300m, what do we need?"),
    ("optimise", "DD-01", "No real-estate collateral available, find a structure"),
    ("optimise", "DD-14", "Optimise"),
    ("optimise", "DD-04", "Restructure this"),
    ("whatif", "DD-01", "What if we take 30% cash margin?"),
    ("whatif", "DD-01", "What if the margin is 320 bps?"),
    ("whatif", "DD-03", "What if the tenor is 5 years?"),
    ("compare", "DD-01", "Compare the counter-offers"),
    ("stress", "DD-01", "How does this hold if they're downgraded two notches?"),
    ("stress", "DD-04", "Stress the structure"),
    ("draft", "DD-01", "Draft the credit risk opinion, conditions precedent and covenants"),
    ("breakeven", "DD-01", "What is the breakeven margin?"),
    ("portfolio", None, "How much real-estate headroom is left this quarter?"),
    ("portfolio", None, "Which proposals breach a hard limit?"),
    ("portfolio", None, "How much sector headroom is left?"),
    ("ingest", "DD-01", "I want to upload a memo"),
]
DRAFT_DEALS = ["DD-01", "DD-02", "DD-04", "R12-TWA"]
BANKFORM_DEALS = ["R12-TWA", "R14-RWQ"]
NUM = re.compile(r"(?<![\w.])-?\d{1,3}(?:,\d{3})+(?:\.\d+)?|(?<![\w.])-?\d+(?:\.\d+)?")


# ------------------------------------------------------------------ http

def call(path: str, body: dict | None = None, method: str | None = None, timeout: float = 1800.0, cookie: str = "") -> Any:
    url = API + path
    data = None if body is None else json.dumps(body).encode()
    headers = {"Content-Type": "application/json"} if data is not None else {}
    if cookie:
        headers["Cookie"] = f"cp_session={cookie}"
    req = urllib.request.Request(url, data=data, method=method or ("POST" if data is not None else "GET"), headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - loopback
        out = r.read()
    return json.loads(out or b"null")


def timed(path: str, body: dict | None = None, method: str | None = None, cookie: str = "") -> tuple[Any, int, str]:
    t0 = time.monotonic()
    try:
        out = call(path, body, method, cookie=cookie)
        return out, int((time.monotonic() - t0) * 1000), ""
    except urllib.error.HTTPError as e:
        return None, int((time.monotonic() - t0) * 1000), f"HTTP {e.code}: {e.read()[:200]!r}"
    except Exception as e:  # noqa: BLE001
        return None, int((time.monotonic() - t0) * 1000), f"{type(e).__name__}: {str(e)[:200]}"


def session_cookie() -> str:
    """A signed-in session when the Core service runs (so turns are stored under a user); empty otherwise."""
    try:
        sys.path.insert(0, str(V5 / "ops"))
        from core_login import login
        return login()["cookie"]
    except Exception:  # noqa: BLE001
        return ""


# ------------------------------------------------------------------ run

def answer_text(answer: dict[str, Any]) -> str:
    return "\n".join(b.get("markdown", "") for b in (answer or {}).get("blocks", []) if b.get("type") in ("text", "draft"))


def figures(text: str) -> list[str]:
    return [m.group(0).replace(",", "") for m in NUM.finditer(text or "")]


def _paper_lines(paper: Any) -> list[str]:
    """Every string in a paper, in document order, skipping volatile keys (created, ids, trace ids)."""
    out: list[str] = []

    def walk(x: Any, key: str = "") -> None:
        if isinstance(x, dict):
            for k, v in x.items():
                if k in ("created", "created_at", "generated", "as_of_label", "trace_id", "trace_ids", "id", "paper_id", "run_id"):
                    continue
                walk(v, k)
        elif isinstance(x, list):
            for v in x:
                walk(v, key)
        elif isinstance(x, str) and len(x) > 2:
            out.append(x)
    walk(paper)
    return out


def run(a: argparse.Namespace) -> int:
    out = LAB / a.experiment
    out.mkdir(parents=True, exist_ok=True)
    health, _, err = timed(DESK + "/health")
    if err:
        print(f"STOP: the Deal Desk service is not reachable at {API} ({err}).")
        return 1
    gw = (health or {}).get("assistant") or {}
    if not a.no_check and (gw.get("experiment") or "") != a.experiment:
        print(f"STOP: the service reports experiment {gw.get('experiment')!r}, not {a.experiment!r}. Start it with "
              f"CONVO_EXPERIMENT={a.experiment} (or pass --no-check).")
        return 1
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=V5, capture_output=True, text=True).stdout.strip()
    stages = [s.strip() for s in a.stages.split(",") if s.strip()]
    manifest = {"experiment": a.experiment, "gateway": gw, "engine": (health or {}).get("engine"), "commit": sha,
                "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "stages": stages, "api": API}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(f"experiment {a.experiment}: provider={gw.get('provider')} model={gw.get('model')} quant={gw.get('quant') or '-'} "
          f"planner={gw.get('planner')} commit={sha}")
    cookie = session_cookie()
    questions = list(QUESTIONS)
    for q in a.questions or []:
        pid, _, text = q.partition(":")
        questions.append(("custom", pid or None, text))
    if a.deals:
        questions = [q for q in questions if q[1] in a.deals or q[1] is None]
    failures = 0

    if "thread" in stages or "desk" in stages:
        (out / "thread").mkdir(exist_ok=True)
        (out / "desk").mkdir(exist_ok=True)
        n = {}
        for intent, pid, text in questions:
            if pid is None and "desk" not in stages:
                continue
            if pid is not None and "thread" not in stages:
                continue
            key = pid or "desk"
            n[key] = n.get(key, 0) + 1
            if pid:
                res, ms, err = timed(f"{DESK}/proposals/{pid}/thread", {"question": text}, cookie=cookie)
                ans = (res or {}).get("answer") or {}
            else:
                res, ms, err = timed(f"{DESK}/ask", {"question": text}, cookie=cookie)
                ans = res or {}   # the desk answer is the body itself (plus turn_id, thread_id)
            row = {"intent": intent, "proposal_id": pid, "question": text, "ms": ms, "error": err,
                   "source": ans.get("source"), "answer_intent": ans.get("intent"), "tools": ans.get("tools"),
                   "validation": ans.get("validation"), "text": answer_text(ans), "figures": figures(answer_text(ans)),
                   "blocks": ans.get("blocks"), "suggestions": ans.get("suggestions"), "trace_ids": ans.get("trace_ids")}
            folder = "thread" if pid else "desk"
            (out / folder / f"{key}__{n[key]:02d}.json").write_text(json.dumps(row, indent=1, ensure_ascii=False))
            failures += bool(err)
            print(f"  {folder:6} {key:8} {ms:7d} ms  {str(row['source'] or '-'):13} {'ERROR ' + err if err else text[:60]}")

    if "draft" in stages:
        (out / "draft").mkdir(exist_ok=True)
        for pid in (a.deals or DRAFT_DEALS):
            res, ms, err = timed(f"{ENGINE}/proposals/{pid}/draft", {"use_model": True}, cookie=cookie)
            d = res or {}
            secs = [{"key": s.get("key"), "heading": s.get("heading"), "method": s.get("method"), "score": s.get("score"),
                     "text": "\n".join(s.get("paragraphs") or []) + ("\n" if s.get("bullets") else "") + "\n".join(f"- {b}" for b in s.get("bullets") or []),
                     "citations": [c.get("id") for c in s.get("citations") or []]} for s in d.get("sections") or []]
            row = {"proposal_id": pid, "ms": ms, "error": err, "draft_id": d.get("draft_id"), "score": d.get("score"),
                   "lint": d.get("lint"), "sections": secs,
                   "facts": [{"id": f.get("id"), "label": f.get("label"), "value": f.get("display") or f.get("value")} for f in d.get("facts") or []]}
            (out / "draft" / f"{pid}.json").write_text(json.dumps(row, indent=1, ensure_ascii=False))
            failures += bool(err)
            by_model = sum(1 for s in secs if s["method"] == "model")
            print(f"  draft  {pid:8} {ms:7d} ms  sections {len(secs)}, by the model {by_model}  {'ERROR ' + err if err else ''}")

    if "bankform" in stages:
        (out / "bankform").mkdir(exist_ok=True)
        for pid in (a.deals or BANKFORM_DEALS):
            plain, ms0, err0 = timed(f"{ENGINE}/proposals/{pid}/bank-form?polish=false", cookie=cookie)
            polished, ms, err = timed(f"{ENGINE}/proposals/{pid}/bank-form?polish=true", cookie=cookie)
            # the paper's text lines only (timestamps and ids differ between two renders)
            t0 = _paper_lines(plain)
            t1 = _paper_lines(polished)
            changed = sum(1 for d in difflib.ndiff(t0, t1) if d[:1] in "+-") if plain and polished else None
            row = {"proposal_id": pid, "ms_plain": ms0, "ms_polished": ms, "error": err or err0, "changed_lines": changed,
                   "plain": plain, "polished": polished}
            (out / "bankform" / f"{pid}.json").write_text(json.dumps(row, indent=1, ensure_ascii=False))
            failures += bool(err or err0)
            print(f"  bankform {pid:6} {ms:7d} ms  polish changed {changed} lines  {'ERROR ' + (err or err0) if (err or err0) else ''}")

    # the service's own telemetry for this experiment
    tel = {"calls": (call(f"{DESK}/telemetry/calls?experiment={a.experiment}&limit=5000") or {}).get("rows"),
           "runs": (call(f"{DESK}/telemetry/runs?experiment={a.experiment}") or {}).get("runs"),
           "summary": (call(f"{DESK}/telemetry/summary?by=purpose,model&experiment={a.experiment}") or {}).get("rows")}
    (out / "telemetry.json").write_text(json.dumps(tel, indent=1))
    manifest["finished"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    manifest["failures"] = failures
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    tot = {k: sum((r.get(k) or 0) for r in (tel["summary"] or [])) for k in ("calls", "input_tokens", "output_tokens", "reasoning_tokens", "ms")}
    print(f"done: {tot['calls']} model calls, {tot['input_tokens']:,} in / {tot['output_tokens']:,} out tokens, "
          f"{tot['ms'] / 1000:.0f} s model time, {failures} failures -> {out}")
    return 1 if failures else 0


# ------------------------------------------------------------------ compare

def _load(exp: str, folder: str) -> dict[str, dict]:
    p = LAB / exp / folder
    if not p.is_dir():
        return {}
    return {f.stem: json.loads(f.read_text()) for f in sorted(p.glob("*.json"))}


def _overlap(a: list[str], b: list[str]) -> float | None:
    sa, sb = set(a or []), set(b or [])
    if not sa and not sb:
        return None
    return round(len(sa & sb) / len(sa | sb), 3)


def _sim(a: str, b: str) -> float:
    return round(difflib.SequenceMatcher(None, a or "", b or "").ratio(), 3)


def compare(a: argparse.Namespace) -> int:
    b, c = a.baseline, a.candidate
    for e in (b, c):
        if not (LAB / e / "manifest.json").exists():
            print(f"STOP: no run {e} under {LAB}")
            return 1
    mb, mc = json.loads((LAB / b / "manifest.json").read_text()), json.loads((LAB / c / "manifest.json").read_text())
    rep: dict[str, Any] = {"baseline": mb, "candidate": mc, "thread": [], "draft": [], "bankform": [], "tokens": {}}
    judge = Judge() if a.judge else None

    # thread + desk
    for folder in ("thread", "desk"):
        lb, lc = _load(b, folder), _load(c, folder)
        for key in sorted(set(lb) | set(lc)):
            rb, rc = lb.get(key), lc.get(key)
            if not rb or not rc:
                rep["thread"].append({"key": key, "missing_in": b if not rb else c})
                continue
            row = {"key": key, "proposal_id": rc.get("proposal_id"), "question": rc.get("question"),
                   "source": {"baseline": rb.get("source"), "candidate": rc.get("source")},
                   "error": {"baseline": rb.get("error"), "candidate": rc.get("error")},
                   "ms": {"baseline": rb.get("ms"), "candidate": rc.get("ms")},
                   "figures": {"baseline": len(rb.get("figures") or []), "candidate": len(rc.get("figures") or []),
                               "overlap": _overlap(rb.get("figures"), rc.get("figures"))},
                   "untraced": {"baseline": len((rb.get("validation") or {}).get("untraced") or []),
                                "candidate": len((rc.get("validation") or {}).get("untraced") or [])},
                   "validation_passed": {"baseline": (rb.get("validation") or {}).get("passed"), "candidate": (rc.get("validation") or {}).get("passed")},
                   "tools": {"baseline": rb.get("tools"), "candidate": rc.get("tools"), "overlap": _overlap(rb.get("tools") or [], rc.get("tools") or [])},
                   "words": {"baseline": len((rb.get("text") or "").split()), "candidate": len((rc.get("text") or "").split())},
                   "text_similarity": _sim(rb.get("text", ""), rc.get("text", ""))}
            if judge:
                row["judge"] = judge.answer(rc.get("question", ""), rb.get("blocks") or [], rb.get("text", ""), rc.get("text", ""))
            rep["thread"].append(row)

    # draft
    db, dc = _load(b, "draft"), _load(c, "draft")
    for pid in sorted(set(db) | set(dc)):
        rb, rc = db.get(pid), dc.get(pid)
        if not rb or not rc:
            rep["draft"].append({"proposal_id": pid, "missing_in": b if not rb else c})
            continue
        sb = {s["key"]: s for s in rb.get("sections") or []}
        secs = []
        for s in rc.get("sections") or []:
            base = sb.get(s["key"], {})
            row = {"key": s["key"], "method": {"baseline": base.get("method"), "candidate": s.get("method")},
                   "score": {"baseline": base.get("score"), "candidate": s.get("score")},
                   "text_similarity": _sim(base.get("text", ""), s.get("text", "")),
                   "figures_overlap": _overlap(figures(base.get("text", "")), figures(s.get("text", "")))}
            if judge:
                row["judge"] = judge.section(s.get("heading", s["key"]), rc.get("facts") or [], base.get("text", ""), s.get("text", ""))
            secs.append(row)
        rep["draft"].append({"proposal_id": pid, "ms": {"baseline": rb.get("ms"), "candidate": rc.get("ms")},
                             "score": {"baseline": (rb.get("score") or {}).get("total") if isinstance(rb.get("score"), dict) else rb.get("score"),
                                       "candidate": (rc.get("score") or {}).get("total") if isinstance(rc.get("score"), dict) else rc.get("score")},
                             "model_sections": {"baseline": sum(1 for s in rb.get("sections") or [] if s.get("method") == "model"),
                                                "candidate": sum(1 for s in rc.get("sections") or [] if s.get("method") == "model"),
                                                "of": len(rc.get("sections") or [])},
                             "rejections": {"candidate": [s.get("method") for s in rc.get("sections") or [] if s.get("method") and s.get("method") != "model"]},
                             "sections": secs})

    # bankform
    bb, bc = _load(b, "bankform"), _load(c, "bankform")
    for pid in sorted(set(bb) | set(bc)):
        rb, rc = bb.get(pid), bc.get(pid)
        if rb and rc:
            rep["bankform"].append({"proposal_id": pid, "changed_lines": {"baseline": rb.get("changed_lines"), "candidate": rc.get("changed_lines")},
                                    "ms": {"baseline": rb.get("ms_polished"), "candidate": rc.get("ms_polished")}})

    # tokens and time, by stage
    def by_stage(exp: str) -> dict[str, dict]:
        t = json.loads((LAB / exp / "telemetry.json").read_text()) if (LAB / exp / "telemetry.json").exists() else {}
        out: dict[str, dict] = {}
        for r in t.get("summary") or []:
            k = r.get("purpose") or "?"
            o = out.setdefault(k, {"calls": 0, "input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0, "ms": 0})
            for f in o:
                o[f] += r.get(f) or 0
        return out

    tb, tc = by_stage(b), by_stage(c)
    tokens = {}
    for k in sorted(set(tb) | set(tc)):
        xb, xc = tb.get(k, {}), tc.get(k, {})
        tokens[k] = {"baseline": xb, "candidate": xc,
                     "ratio": {f: (round(xc[f] / xb[f], 2) if xb.get(f) else None) for f in ("calls", "input_tokens", "output_tokens", "ms") if xc}}
    totb = {f: sum(x.get(f, 0) for x in tb.values()) for f in ("calls", "input_tokens", "output_tokens", "reasoning_tokens", "ms")}
    totc = {f: sum(x.get(f, 0) for x in tc.values()) for f in ("calls", "input_tokens", "output_tokens", "reasoning_tokens", "ms")}
    tokens["TOTAL"] = {"baseline": totb, "candidate": totc,
                       "ratio": {f: (round(totc[f] / totb[f], 2) if totb.get(f) else None) for f in ("calls", "input_tokens", "output_tokens", "ms")}}
    rep["tokens"] = tokens

    # headline
    th = [r for r in rep["thread"] if "missing_in" not in r]
    def rate(rows, f):
        vals = [f(r) for r in rows]
        vals = [v for v in vals if v is not None]
        return round(sum(vals) / len(vals), 3) if vals else None
    rep["headline"] = {
        "questions": len(th),
        "model_answers": {"baseline": sum(1 for r in th if r["source"]["baseline"] == "model"), "candidate": sum(1 for r in th if r["source"]["candidate"] == "model")},
        "validation_pass_rate": {"baseline": rate(th, lambda r: 1.0 if r["validation_passed"]["baseline"] else 0.0),
                                 "candidate": rate(th, lambda r: 1.0 if r["validation_passed"]["candidate"] else 0.0)},
        "mean_figure_overlap": rate(th, lambda r: r["figures"]["overlap"]),
        "mean_tool_overlap": rate(th, lambda r: r["tools"]["overlap"]),
        "mean_ms": {"baseline": rate(th, lambda r: r["ms"]["baseline"]), "candidate": rate(th, lambda r: r["ms"]["candidate"])},
        "draft_model_sections": {"baseline": sum(d["model_sections"]["baseline"] for d in rep["draft"] if "model_sections" in d),
                                 "candidate": sum(d["model_sections"]["candidate"] for d in rep["draft"] if "model_sections" in d),
                                 "of": sum(d["model_sections"]["of"] for d in rep["draft"] if "model_sections" in d)},
        "tokens": tokens.get("TOTAL"),
    }
    if judge:
        js = [r["judge"] for r in th if r.get("judge")] + [s["judge"] for d in rep["draft"] for s in d.get("sections", []) if s.get("judge")]
        for f in ("faithfulness", "completeness", "clarity"):
            rep["headline"][f"judge_{f}"] = rate(js, lambda j, f=f: j.get(f))
        rep["headline"]["judge_prefers_candidate"] = rate(js, lambda j: {"candidate": 1.0, "tie": 0.5, "baseline": 0.0}.get(j.get("preference")))

    stem = LAB / f"compare_{b}_vs_{c}"
    stem.with_suffix(".json").write_text(json.dumps(rep, indent=1, ensure_ascii=False))
    stem.with_suffix(".md").write_text(markdown(rep))
    with stem.with_suffix(".csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["kind", "key", "proposal", "question_or_section", "baseline", "candidate", "figure_overlap", "text_similarity", "ms_baseline", "ms_candidate", "judge"])
        for r in th:
            w.writerow(["thread", r["key"], r.get("proposal_id"), r.get("question"), r["source"]["baseline"], r["source"]["candidate"],
                        r["figures"]["overlap"], r["text_similarity"], r["ms"]["baseline"], r["ms"]["candidate"], json.dumps(r.get("judge")) if r.get("judge") else ""])
        for d in rep["draft"]:
            for s in d.get("sections", []):
                w.writerow(["draft", d["proposal_id"], d["proposal_id"], s["key"], s["method"]["baseline"], s["method"]["candidate"],
                            s["figures_overlap"], s["text_similarity"], d["ms"]["baseline"], d["ms"]["candidate"], json.dumps(s.get("judge")) if s.get("judge") else ""])
    print(markdown(rep))
    print(f"-> {stem}.json / .md / .csv")
    return 0


def markdown(rep: dict[str, Any]) -> str:
    h = rep["headline"]
    mb, mc = rep["baseline"], rep["candidate"]
    g = lambda m: f"{(m.get('gateway') or {}).get('provider')} / {(m.get('gateway') or {}).get('model')} {(m.get('gateway') or {}).get('quant') or ''}".strip()  # noqa: E731
    lines = [f"# Model lab: {mb['experiment']} vs {mc['experiment']}", "",
             f"Baseline: {g(mb)} (commit {mb.get('commit')}, {mb.get('started')})",
             f"Candidate: {g(mc)} (commit {mc.get('commit')}, {mc.get('started')})", "",
             "## Headline", "", "| Measure | Baseline | Candidate |", "|---|---|---|",
             f"| Questions | {h['questions']} | {h['questions']} |",
             f"| Answered by the model (not the planner) | {h['model_answers']['baseline']} | {h['model_answers']['candidate']} |",
             f"| Validation pass rate (every figure traced) | {h['validation_pass_rate']['baseline']} | {h['validation_pass_rate']['candidate']} |",
             f"| Mean figure overlap with the baseline | - | {h['mean_figure_overlap']} |",
             f"| Mean engine-tool overlap with the baseline | - | {h['mean_tool_overlap']} |",
             f"| Mean answer time (ms) | {h['mean_ms']['baseline']} | {h['mean_ms']['candidate']} |",
             f"| Draft sections written by the model | {h['draft_model_sections']['baseline']} / {h['draft_model_sections']['of']} | {h['draft_model_sections']['candidate']} / {h['draft_model_sections']['of']} |"]
    t = h.get("tokens") or {}
    if t:
        for f in ("calls", "input_tokens", "output_tokens", "reasoning_tokens", "ms"):
            ratio = (t.get("ratio") or {}).get(f)
            lines.append(f"| Model {f.replace('_', ' ')} | {t['baseline'].get(f, 0):,} | {t['candidate'].get(f, 0):,}"
                         f"{f' ({ratio}x)' if ratio is not None else ''} |")
    for f in ("judge_faithfulness", "judge_completeness", "judge_clarity", "judge_prefers_candidate"):
        if f in h:
            lines.append(f"| {f.replace('_', ' ').capitalize()} | - | {h[f]} |")
    lines += ["", "## Tokens and time by stage", "", "| Stage | Calls b/c | Input b/c | Output b/c | Model ms b/c |", "|---|---|---|---|---|"]
    for k, v in rep["tokens"].items():
        if k == "TOTAL":
            continue
        xb, xc = v["baseline"], v["candidate"]
        lines.append(f"| {k} | {xb.get('calls', 0)} / {xc.get('calls', 0)} | {xb.get('input_tokens', 0):,} / {xc.get('input_tokens', 0):,} | "
                     f"{xb.get('output_tokens', 0):,} / {xc.get('output_tokens', 0):,} | {xb.get('ms', 0):,} / {xc.get('ms', 0):,} |")
    lines += ["", "## Questions", "", "| Deal | Question | Source b/c | Figures b/c (overlap) | Untraced b/c | Tools overlap | ms b/c |", "|---|---|---|---|---|---|---|"]
    for r in rep["thread"]:
        if "missing_in" in r:
            lines.append(f"| | {r['key']} | missing in {r['missing_in']} | | | | |")
            continue
        lines.append(f"| {r.get('proposal_id') or 'desk'} | {(r.get('question') or '')[:50]} | {r['source']['baseline']} / {r['source']['candidate']} | "
                     f"{r['figures']['baseline']} / {r['figures']['candidate']} ({r['figures']['overlap']}) | {r['untraced']['baseline']} / {r['untraced']['candidate']} | "
                     f"{r['tools']['overlap']} | {r['ms']['baseline']} / {r['ms']['candidate']} |")
    if rep["draft"]:
        lines += ["", "## House-style drafts", "", "| Deal | Model sections b/c | Score b/c | Candidate rejections |", "|---|---|---|---|"]
        for d in rep["draft"]:
            if "missing_in" in d:
                lines.append(f"| {d['proposal_id']} | missing in {d['missing_in']} | | |")
                continue
            lines.append(f"| {d['proposal_id']} | {d['model_sections']['baseline']} / {d['model_sections']['candidate']} of {d['model_sections']['of']} | "
                         f"{d['score']['baseline']} / {d['score']['candidate']} | {'; '.join(d['rejections']['candidate'])[:120]} |")
    if rep["bankform"]:
        lines += ["", "## Bank-form polish", "", "| Deal | Lines changed b/c | ms b/c |", "|---|---|---|"]
        for r in rep["bankform"]:
            lines.append(f"| {r['proposal_id']} | {r['changed_lines']['baseline']} / {r['changed_lines']['candidate']} | {r['ms']['baseline']} / {r['ms']['candidate']} |")
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------ judge

class Judge:
    """Opus as the reference reader: scores a candidate text against the baseline and the facts (1-5), via one tool."""

    TOOL = {"name": "score", "description": "Score the candidate.", "input_schema": {
        "type": "object", "required": ["faithfulness", "completeness", "clarity", "preference", "reason"], "properties": {
            "faithfulness": {"type": "integer", "minimum": 1, "maximum": 5, "description": "Every figure and claim is supported by the facts or the baseline's figures; 5 = nothing wrong, 1 = invented or wrong figures."},
            "completeness": {"type": "integer", "minimum": 1, "maximum": 5, "description": "Covers what the baseline covers and what the question asked."},
            "clarity": {"type": "integer", "minimum": 1, "maximum": 5, "description": "Reads as a credit professional writes: direct, precise, no filler."},
            "preference": {"type": "string", "enum": ["baseline", "candidate", "tie"]},
            "reason": {"type": "string"}}}}

    def __init__(self) -> None:
        import anthropic
        key = next((os.environ.get(v) for v in ("CONVO_ANTHROPIC_API_KEY", "COCKPIT_ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY") if os.environ.get(v)), "")
        if not key:
            raise SystemExit("STOP: --judge needs CONVO_ANTHROPIC_API_KEY (or ANTHROPIC_API_KEY) in the environment.")
        self.client = anthropic.Anthropic(api_key=key, timeout=120.0, max_retries=2)
        self.model = os.environ.get("MODEL_LAB_JUDGE_MODEL", "claude-opus-5")

    def _score(self, system: str, user: str) -> dict[str, Any]:
        try:
            msg = self.client.messages.create(model=self.model, max_tokens=600, system=system,
                                              messages=[{"role": "user", "content": user}], tools=[self.TOOL],
                                              tool_choice={"type": "tool", "name": "score"})
            for b in msg.content:
                if getattr(b, "type", "") == "tool_use":
                    return dict(b.input)
        except Exception as e:  # noqa: BLE001
            return {"error": f"{type(e).__name__}: {str(e)[:120]}"}
        return {"error": "no score"}

    def answer(self, question: str, baseline_blocks: list[dict], baseline: str, candidate: str) -> dict[str, Any]:
        tables = [b for b in baseline_blocks if b.get("type") == "table"]
        return self._score(
            "You are the senior credit officer of a GCC bank reviewing two answers to the same Deal Desk question. The tables are "
            "the engine's results (the facts). Score the CANDIDATE against the facts and the BASELINE with the score tool.",
            json.dumps({"question": question, "facts_tables": tables[:6], "baseline": baseline[:6000], "candidate": candidate[:6000]}, ensure_ascii=False))

    def section(self, heading: str, facts: list[dict], baseline: str, candidate: str) -> dict[str, Any]:
        return self._score(
            "You are the head of credit of a GCC bank reviewing one section of a credit proposal written in the bank's house style. "
            "The facts list is the only source of figures. Score the CANDIDATE against the facts and the BASELINE with the score tool.",
            json.dumps({"section": heading, "facts": facts[:80], "baseline": baseline[:6000], "candidate": candidate[:6000]}, ensure_ascii=False))


# ------------------------------------------------------------------ main

def main(argv: list[str]) -> int:
    global API
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--experiment", required=True, help="a label, e.g. opus-baseline, qwen38-27b-fp8")
    r.add_argument("--stages", default="thread,desk,draft,bankform")
    r.add_argument("--deals", default="", help="comma-separated proposal ids to restrict to (default: the question set's)")
    r.add_argument("--questions", action="append", help="extra question as PID:text (PID empty for the desk)")
    r.add_argument("--api", default=API)
    r.add_argument("--no-check", action="store_true", help="do not require the service to report this experiment name")
    c = sub.add_parser("compare")
    c.add_argument("--baseline", required=True)
    c.add_argument("--candidate", required=True)
    c.add_argument("--judge", action="store_true", help="score with Opus as the reference reader (needs a key)")
    sub.add_parser("list")
    d = sub.add_parser("dry", help="Round E: calls and estimated tokens per question, before/after, no service, no model")
    d.add_argument("--efficiency", default="both", choices=["both", "off", "on"])
    a = ap.parse_args(argv)
    if a.cmd == "run":
        API = a.api.rstrip("/")
        a.deals = [d.strip() for d in a.deals.split(",") if d.strip()]
        return run(a)
    if a.cmd == "compare":
        return compare(a)
    if a.cmd == "dry":   # Round E (ops/model_lab_dry.py)
        sys.path.insert(0, str(V5 / "ops"))
        import model_lab_dry
        return model_lab_dry.main(a.efficiency)
    for p in sorted(LAB.glob("*/manifest.json")):
        m = json.loads(p.read_text())
        gw = m.get("gateway") or {}
        print(f"{m['experiment']:28} {gw.get('provider') or '-':10} {gw.get('model') or '-':32} {m.get('started')}  stages={','.join(m.get('stages', []))}  failures={m.get('failures')}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
