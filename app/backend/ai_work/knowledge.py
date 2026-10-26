"""The product knowledge base (docs/product_knowledge) with worked examples computed on the real books.

Each module file there carries a header (id, name, screen, keywords, example), "What it is", "Flow" (steps with
links that open each screen) and "Good to know". `pack_v5()` reads them and computes each module's worked example
from the current books through the same tools the conversations use, so every figure in a walkthrough is the
books' figure at the as-of date. `walkthrough(module)` writes the complete answer to "How does X work?": what it
is, the full flow step by step with links, and the worked example.

The pack is written to var/product_knowledge/pack_v5.json by ops/build_product_knowledge.py; the Cockpit's
product-help path reads it (registered exception FX-A4) and the Playbook, Project and help conversations call
`walkthrough` as a tool.
"""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from backend.convo import identity
from backend.workspace_v5.book import mn

V5 = Path(__file__).resolve().parents[2]
DOCS = V5 / "docs" / "product_knowledge"
PACK = Path(os.environ.get("COCKPIT_PRODUCT_KNOWLEDGE_V5") or V5 / "var" / "product_knowledge" / "pack_v5.json")
LINK = re.compile(r"\[([^\]]+)\]\((/[^)\s]*)\)")


def _parse(path: Path) -> dict[str, Any] | None:
    text = path.read_text(encoding="utf-8")
    head, _, body = text.partition("\n## ")
    meta = dict(re.findall(r"^(\w+):\s*(.+)$", head, re.M))
    if "id" not in meta:
        return None
    parts: dict[str, str] = {}
    for chunk in ("## " + body).split("\n## ")[0:]:
        chunk = chunk.lstrip("# ").strip()
        if not chunk:
            continue
        title, _, rest = chunk.partition("\n")
        parts[title.strip().lower()] = rest.strip()
    flow = []
    for ln in parts.get("flow", "").splitlines():
        m = re.match(r"^\s*\d+\.\s+(.*)$", ln)
        if m:
            flow.append({"text": m.group(1), "links": [{"label": a, "href": h} for a, h in LINK.findall(m.group(1))]})
    return {"id": meta["id"], "name": meta.get("name", meta["id"]), "screen": meta.get("screen", "/"),
            "keywords": [k.strip() for k in meta.get("keywords", "").split(",") if k.strip()],
            "example": meta.get("example", "none"), "what": parts.get("what it is", ""), "flow": flow,
            "good_to_know": [re.sub(r"^\s*-\s+", "", x) for x in parts.get("good to know", "").splitlines() if x.strip()]}


@lru_cache(maxsize=1)
def modules() -> list[dict[str, Any]]:
    out = []
    for p in sorted(DOCS.glob("*.md")):
        m = _parse(p)
        if m:
            out.append(m)
    return out


def find(question: str) -> dict[str, Any] | None:
    """The module a help question is about (the longest keyword that matches wins)."""
    q = question.lower()
    best, score = None, 0
    for m in modules():
        for k in [m["name"].lower(), *m["keywords"]]:
            if re.search(rf"\b{re.escape(k)}", q) and len(k) > score:
                best, score = m, len(k)
    return best


OVERVIEW = DOCS / "functionalities.md"


def overview() -> dict[str, Any] | None:
    """R6: the current functionalities, grouped (docs/product_knowledge/functionalities.md), for the Cockpit synopsis."""
    if not OVERVIEW.exists():
        return None
    text = OVERVIEW.read_text(encoding="utf-8")
    head, _, body = text.partition("\n## ")
    meta = dict(re.findall(r"^(\w+):\s*(.+)$", head, re.M))
    groups = []
    for chunk in ("## " + body).split("\n## "):
        title, _, rest = chunk.lstrip("# ").partition("\n")
        rows = [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in rest.splitlines()
                if ln.strip().startswith("|") and not re.match(r"^\|[\s|:-]+\|$", ln.strip())]
        items = [{"name": r[0], "screen": r[1], "arc": [] if r[2] in ("—", "-", "") else [a.strip() for a in r[2].split(",")],
                  "does": r[3], "owns": r[4]} for r in rows[1:] if len(r) >= 5]
        if items:
            groups.append({"group": title.strip(), "items": items})
    return {"note": meta.get("Note", ""), "absorbs": [a.strip() for a in meta.get("Absorbs", "").split(",") if a.strip()],
            "groups": groups, "count": sum(len(g["items"]) for g in groups)}


# ------------------------------------------------------------ worked examples


def _example(key: str) -> dict[str, Any] | None:
    if key.startswith("admin_"):   # PLAN_R5 G6: the Admin pages' worked examples live with the Admin service
        from backend.admin import examples
        return examples.example(key)
    from backend.ai_work import tools
    if key == "dealdesk_levers":
        # R5 D4 / G6: the Deal Desk engine itself (deterministic), on DD-02, the deal below the hurdle (screen 15)
        from backend.dealdesk import alternatives as dd_alt
        from backend.dealdesk import fmt as dd_fmt
        from backend.dealdesk import proposals as dd_props
        p = dd_props.get("DD-02")
        r = dd_alt.analyse_alternatives(p)
        m = r["base_metrics"]
        alts = "; ".join(f"{a['label'].lower()} (RAROC {dd_fmt.pct(a['metrics']['lifetime_raroc'])}, {a['approval']['level']})"
                         for a in r["alternatives"][:3])
        from backend.dealdesk_thread.convo import lever_value
        single = "; ".join(f"{x['label'].lower()} alone at {lever_value(x['lever'], x['to'])}"
                           for x in r["single_lever"] if x["clears_alone"] and isinstance(x["to"], (int, float)))[:400]
        return {"title": f"{p['obligor']['name']} (DD-02), below the hurdle",
                "text": (f"Asked at SAIBOR + {p['ask']['margin_bps']} bps over {p['ask']['tenor_years']} years, lifetime RAROC is "
                         f"{dd_fmt.pct(m['lifetime_raroc'])} against a {dd_fmt.pct(m['hurdle'])} hurdle. Optimise shows "
                         f"{len(r['alternatives'])} structures that clear it: {alts}. The minimum change on one lever: {single}."),
                "links": [{"label": "Open DD-02 in Deal Desk", "href": "/deal-desk/DD-02"}]}
    if key == "cockpit_ecl":
        r = tools.book_figures("corporate", by="sector", measures=["ecl", "ead", "coverage_pct"])
        top = r.table["rows"][0]
        f = {x["key"]: x for x in r.figures}
        return {"title": "Asking the corporate book what drives ECL",
                "text": (f"You ask: “Which sectors carry the most ECL this quarter?”. The answer reads the corporate "
                         f"book at {r.extra['period']}: ECL {mn(f['ecl']['value'])} on EAD {mn(f['ead']['value'])}, "
                         f"coverage {f['coverage_pct']['value']:.2f}%; {top['sector']} carries the most ECL "
                         f"({mn(top['ecl'])}), with the full ranking as a table and chart you can save, share or add "
                         "to a report."),
                "links": [{"label": "Ask it in the Cockpit", "href": "/"}]}
    if key == "ews_construction":
        h = tools.ews_headline("corporate", segment="Construction")
        c = tools.ews_clients("corporate", ["critical"], segment="Construction", n=3)
        names = "; ".join(f"{x['id']} {x.get('name', '')} (score {x['score']:.1f}, EAD {mn(x['ead'])})"
                          for x in c.table["rows"])
        return {"title": "Construction on the corporate book",
                "text": (f"{h.text} Opening the Construction card lists the critical names first: {names}. Each opens "
                         "its customer page with the reasons and the facilities."),
                "links": [{"label": "Open Construction in Early Warning",
                           "href": "/early-warning?domain=corporate&segment=Construction"}]}
    if key == "b360_cb01312":
        r = tools.borrower_profile("CB01312")
        return {"title": "CB01312 in Borrower 360", "text": r.text,
                "links": [{"label": "Open CB01312", "href": "/borrower-360?borrower=CB01312"}]}
    if key == "whatif_oil":
        r = tools.whatif_scenario("corporate", "oil-shock")
        return {"title": "Oil price shock on the corporate book", "text": r.text,
                "links": [{"label": "Run it in What-If", "href": "/what-if?domain=corporate"}]}
    if key == "scorecard_verdicts":
        r = tools.scorecard_overview()
        return {"title": "The latest validations", "text": r.text.split(" Main findings:")[0],
                "links": [{"label": "Open Scorecard Validation", "href": "/scorecard-validation"}]}
    if key == "data_builder_construction":
        r = tools.book_figures("corporate", segment="Construction", measures=["count", "owners", "ead"])
        f = {x["key"]: x["value"] for x in r.figures}
        return {"title": "Construction facilities to Excel",
                "text": (f"Choose the corporate book at {r.extra['period']}, filter sector = Construction: the preview "
                         f"holds {int(f['count']):,} facilities of {int(f['owners']):,} borrowers with EAD "
                         f"{mn(f['ead'])}; Export writes the house-styled Excel with its About sheet."),
                "links": [{"label": "Open Data Domains", "href": "/data-builder"}]}
    if key == "playbook_ecl_report":
        from backend.playbook_v5 import ai
        p = ai.proposal_for("I want to draft a corporate ECL report")
        facts = ai._facts(p)
        return {"title": "A corporate IFRS 9 ECL report",
                "text": (f"You type “I want to draft a corporate ECL report”. The assistant answers with the scope "
                         f"({p['book']} book at {p['period']}) and the headline. {facts} It proposes "
                         f"{len(p['sections'])} sections: " + ", ".join(s["title"] for s in p["sections"])
                         + ". You add or drop sections, then say “Create it”: every section is drafted from the "
                         "books, and the Early Warning section's own assistant can list the critical names for you."),
                "links": [{"label": "Open Playbook", "href": "/playbook"}]}
    if key == "policy_pack":
        pol = json.loads((V5 / "backend" / "cockpit_v4" / "credit_policy.json").read_text())
        ids = sorted(set(re.findall(r"\b(?:CP|RP)-\d+\.\d+\b", json.dumps(pol))))
        return {"title": "The policy pack and a circular",
                "text": (f"The active pack holds the bank's credit policy ({len(ids)} clauses, {ids[0]} to {ids[-1]}) "
                         "and circular C-2026-03. Asking the Cockpit why Stage 2 rose cites the clause behind it, for "
                         "example RP-5.1 (a two-notch downgrade is a significant increase in credit risk).")
                if ids else "The active pack holds the bank's credit policy and circular C-2026-03.",
                "links": [{"label": "Open Policy Docs", "href": "/policy-docs"}]}
    if key == "projects_retail":
        r = tools.ews_clients("retail", ["high", "critical"], stage=1, n=5)
        rows = "; ".join(f"{x['id']} ({x['segment']}, {x['band'].lower()}, score {x['score']:.1f}, EAD {mn(x['ead'], 2)})"
                         for x in r.table["rows"])
        return {"title": "The Retail Stage 2 review project",
                "text": (f"In the project “Retail Stage 2 review” (retail book and Early Warning), the thread question "
                         f"“Give me a list of 5 high-alert Early Warning clients who are in Stage 1” returns: {rows}. "
                         f"{r.text.split(';')[0]}. Asking for corporate data there is refused: it is outside the "
                         "project's scope."),
                "links": [{"label": "Open the project", "href": "/projects/retail-stage2-review"}]}
    if key == "analyses_seed":
        r = tools.book_figures("corporate", by="sector", measures=["ead"])
        top = r.table["rows"][:3]
        return {"title": "EAD by sector, refreshed",
                "text": (f"The saved analysis “EAD by sector” refreshed at {r.extra['period']} ranks "
                         + ", ".join(f"{x['sector']} ({mn(x['ead'])})" for x in top)
                         + " first; Refresh against an earlier quarter shows the before and after side by side."),
                "links": [{"label": "Open Analyses", "href": "/analyses"}]}
    if key == "lenses_construction":
        from backend.lenses_v5 import planner as lp
        from backend.lenses_v5.render import render as lrender
        spec = lp.build_spec("Construction sector dashboard")
        r = lrender(spec)
        k = {x["key"]: x["display"] for x in r["kpis"]}
        return {"title": "A Construction lens",
                "text": (f"You type “construction sector dashboard” on the Lenses home. The lens opens on the corporate book at "
                         f"{r['period']}: EAD {k['ead']}, ECL {k['ecl']}, coverage {k['coverage']}, Stage 2 {k['stage2_share']}, "
                         f"{k['warned']} warned names, with {r['charts']} charts (ECL trend, stage mix, ratings, sub-sectors, regions, "
                         "Early Warning reasons, migration, DSCR, concentration) and the top 20 names. Saying “add DSCR distribution” "
                         "or “compare with Real Estate” in the assistant changes it; Save, Share or Add to report keep it."),
                "links": [{"label": "Open Lenses", "href": "/lenses"}]}
    return None


def pack_v5() -> dict[str, Any]:
    from backend.ai_work import tools
    from backend.workspace_v5 import compute
    out = []
    for m in modules():
        ex = None
        if m["example"] != "none":
            try:
                ex = _example(m["example"])
            except Exception as e:  # noqa: BLE001 - a module without its example is still documented
                ex = {"title": "", "text": "", "links": [], "error": type(e).__name__}
        out.append({**m, "worked_example": ex})
    as_of = {b: compute.periods(b)[-1] for b in tools.BOOKS}
    return {"pack_version": f"v5-{as_of['corporate']}-{as_of['retail']}", "as_of": as_of,
            "source": "docs/product_knowledge", "modules": out, "overview": overview(),
            # PLAN_R9 G6: the intelligence framing (docs/product_knowledge/intelligence.md), read by FX-A4's synopsis.
            "intelligence": identity.parse()}


def write_pack(path: Path | None = None) -> Path:
    path = path or PACK
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(pack_v5(), indent=1, default=str), encoding="utf-8")
    return path


@lru_cache(maxsize=1)
def _cached() -> dict[str, Any]:
    if PACK.exists():
        try:
            return json.loads(PACK.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    return pack_v5()


def module_with_example(module_id: str) -> dict[str, Any] | None:
    return next((m for m in _cached()["modules"] if m["id"] == module_id), None)


def walkthrough(module_id: str) -> dict[str, Any]:
    """The complete answer to "How does <module> work?": markdown with links, and the figures it quotes."""
    m = module_with_example(module_id)
    if m is None:
        raise KeyError(module_id)
    ex = m.get("worked_example") or {}
    verb = "work" if m["name"].endswith("s") else "works"
    lines = [f"**How {m['name']} {verb}.** {m['what']}", "", "**The flow, step by step**"]
    lines += [f"{i}. {s['text']}" for i, s in enumerate(m["flow"], 1)]
    if ex.get("text"):
        lines += ["", f"**Worked example on the books: {ex['title']}.** {ex['text']}"]
        links = " · ".join(f"[{x['label']}]({x['href']})" for x in ex.get("links") or [])
        if links:
            lines.append(links)
    if m.get("good_to_know"):
        lines += ["", "**Good to know**", *[f"- {g}" for g in m["good_to_know"]]]
    links = [x for s in m["flow"] for x in s["links"]] + list(ex.get("links") or [])
    return {"module": m["id"], "name": m["name"], "markdown": "\n".join(lines), "links": links,
            "as_of": _cached().get("as_of", {})}
