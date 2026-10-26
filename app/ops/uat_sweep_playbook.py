"""UAT sweep, Playbook and Policy Docs part (PLAN_R3 S1-1 and S1-2). Called from ops/uat_sweep.py (`--only playbook`).

Every figure on screen is checked against the Playbook service's API (the API is tested against the books in
tests/v5/playbook); every control is clicked; each step ends with no console error, no page error and no failed
request, and the label rule on the screen, in the data and in every downloaded file. The sweep creates its own
reports and its own circular, named for the run, and withdraws the circular again, so it can be re-run and the
seeded content stays as seeded.
"""
from __future__ import annotations

import io
import json
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable

import core_login
from uat_sweep_core import as_user, cookie_of, tid

PB = "http://127.0.0.1:8506"


def pb_get(path: str, cookie: str) -> Any:
    req = urllib.request.Request(PB + path, headers={"Cookie": f"cp_session={cookie}"})
    with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310 - fixed loopback origin
        return json.loads(r.read())


def _docx(paragraphs: list[tuple[str, str]]) -> bytes:
    from docx import Document

    d = Document()
    for style, text in paragraphs:
        d.add_paragraph(text, style=style)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def _download(pg, testid: str) -> Path:
    with pg.expect_download(timeout=180_000) as d:
        pg.click(tid(testid))
    out = Path(tempfile.mkdtemp(prefix="pb_", dir=str(Path(__file__).resolve().parents[1] / "var"))) / d.value.suggested_filename
    d.value.save_as(out)
    return out


def playbook_steps(s, page, UI: str, wait_for: Callable[..., Any]) -> None:
    browser = page.context.browser
    run = time.strftime("%H%M%S")
    anne = cookie_of("anne")

    # ------------------------------------------------------------ home
    s.start("corporate", "R3-S1-1", "Playbook home: Work menu (Playbook, Policy Docs; no Documents), chat box, templates, reports with status counts")
    page.goto(UI + "/playbook", wait_until="domcontentloaded")
    page.wait_for_selector(tid("playbook-home"), timeout=120_000)
    page.wait_for_selector(tid("playbook-report-row"), timeout=60_000)
    nav = page.locator("nav").first.inner_text() if page.locator("nav").count() else page.inner_text("body")
    s.check("Work menu lists Playbook and Policy Docs", "Playbook" in nav and "Policy Docs" in nav)
    s.check("the old Documents item is gone from the menu", "\nDocuments\n" not in f"\n{nav}\n")
    api = pb_get("/api/v1/playbook/reports", anne)["reports"]
    rows = page.locator(tid("playbook-report-row"))
    s.check("every report the API lists is on the screen", rows.count() == len(api), len(api), rows.count())
    ids = {rows.nth(i).get_attribute("data-id") for i in range(rows.count())}
    s.check("the three seeded reports are there", {"rp_ccp_q2_2026", "rp_construction_review_q2_2026", "rp_memo_cb01312"} <= ids)
    s.check("chat box and the five templates", page.locator(tid("playbook-chat-input")).count() == 1 and all(
        page.locator(tid(f"playbook-template-{t}")).count() == 1 for t in (
            "credit-committee-pack", "risk-committee-report", "portfolio-review", "borrower-credit-memo", "scenario-report")))
    s.check("upload a .docx or .pdf is offered", page.locator(tid("playbook-upload-input")).count() == 1)
    in_review = sum(1 for r in api if r["status"] == "in_review")
    page.click(tid("playbook-filter-in_review"))
    page.wait_for_timeout(400)
    s.check("the In review tab shows the API's in-review reports", rows.count() == in_review, in_review, rows.count())
    page.click(tid("playbook-filter-all"))
    s.finish()

    # ----------------------------------------------------------- report
    s.start("corporate", "R3-S1-1", "A report: sections with charts and tables, status, owner, reviewers, due date, comments, versions; Word export; Back")
    rep = pb_get("/api/v1/playbook/reports/rp_ccp_q2_2026", anne)
    page.click(f'{tid("playbook-report-row")}[data-id="rp_ccp_q2_2026"] a, {tid("playbook-report-row")}[data-id="rp_ccp_q2_2026"]')
    wait_for(page, r"/playbook\?report=rp_ccp_q2_2026")
    page.wait_for_selector(tid("playbook-report"), timeout=60_000)
    page.wait_for_selector(tid("playbook-section"), timeout=60_000)
    s.check("every section is shown, in order", page.locator(tid("playbook-section")).count() == len(rep["sections"]),
            len(rep["sections"]), page.locator(tid("playbook-section")).count())
    s.check("title and status match the API", rep["title"] in page.inner_text(tid("playbook-report"))
            and "In review" in page.inner_text(tid("playbook-workflow")))
    page.wait_for_selector(f'{tid("playbook-chart")} .js-plotly-plot, {tid("playbook-chart")} svg', timeout=60_000)
    s.check("charts are drawn (Plotly)", page.locator(f'{tid("playbook-chart")}').count() >= 3)
    s.check("tables and key figures are drawn", page.locator(tid("playbook-kpi")).count() >= 1 and page.locator("table").count() >= 1)
    s.check("owner, reviewers and due date", "Abdullah Al-Zahrani" in page.inner_text(tid("playbook-people"))
            and "Noura Al-Harbi" in page.inner_text(tid("playbook-people")))
    s.check("imported sections show where they came from", page.locator(tid("playbook-provenance")).count() >= 3)
    page.click(tid("playbook-tab-comments"))
    page.wait_for_selector(tid("playbook-comment"), timeout=30_000)
    s.check("comments match the API", page.locator(tid("playbook-comment")).count() == len(rep["comments"]),
            len(rep["comments"]), page.locator(tid("playbook-comment")).count())
    page.click(tid("playbook-tab-versions"))
    page.wait_for_selector(tid("playbook-version-row"), timeout=30_000)
    vers = pb_get("/api/v1/playbook/reports/rp_ccp_q2_2026/versions", anne)["versions"]
    s.check("version history matches the API", page.locator(tid("playbook-version-row")).count() == len(vers),
            len(vers), page.locator(tid("playbook-version-row")).count())
    path = _download(page, "playbook-export")
    from docx import Document

    doc = Document(str(path))
    text = "\n".join(p.text for p in doc.paragraphs)
    s.check("Word export: cover, contents and the sections", rep["title"] in text and "Contents" in text
            and all(sec["title"] in text for sec in rep["sections"]))
    s.check("Word export: charts and page numbers", len(doc.inline_shapes) >= 3 and "NUMPAGES" in doc.sections[0].footer._element.xml)
    page.click(tid("playbook-back"))
    page.wait_for_selector(tid("playbook-home"), timeout=60_000)
    s.check("Back returns to the Playbook home", page.url.rstrip("/").endswith("/playbook"))
    s.finish()

    # --------------------------------------------- chat box and thread
    s.start("corporate", "R3-S1-1", "Chat box starts a credit memo; the thread revises a section, imports Early Warning and moves the status; Share in Mail")
    ctx, pg, _ = as_user(browser, s, "sara.aldosari")
    s.page = pg
    sara = cookie_of("sara.aldosari")
    pg.goto(UI + "/playbook", wait_until="domcontentloaded")
    pg.wait_for_selector(tid("playbook-chat-input"), timeout=120_000)
    pg.fill(tid("playbook-chat-input"), "Draft a credit memo for CB01143")
    pg.click(tid("playbook-chat-send"))
    wait_for(pg, r"/playbook\?report=rp_", 120_000)
    pg.wait_for_selector(tid("playbook-section"), timeout=60_000)
    rid = pg.url.split("report=")[1].split("&")[0]
    r1 = pb_get(f"/api/v1/playbook/reports/{rid}", sara)
    s.check("a borrower credit memo for CB01143 was started and drafted", r1["template"] == "borrower-credit-memo"
            and "CB01143" in r1["title"] and all(sec["blocks"] for sec in r1["sections"]))
    s.check("its sections are on the screen", pg.locator(tid("playbook-section")).count() == len(r1["sections"]))

    def say(text: str) -> dict:
        before = pg.locator(tid("playbook-message")).count()
        pg.fill(tid("playbook-thread-input"), text)
        pg.click(tid("playbook-thread-send"))
        pg.wait_for_function("(n) => document.querySelectorAll('[data-testid=\"playbook-message\"]').length >= n + 2",
                             arg=before, timeout=120_000)
        return pb_get(f"/api/v1/playbook/reports/{rid}", sara)

    r2 = say("Make the request and recommendation shorter")
    s.check("the assistant revised the section", len(r2["sections"][0]["blocks"][0]["text"]) < len(r1["sections"][0]["blocks"][0]["text"]))
    r3 = say("Import the Early Warning list for Construction")
    s.check("the Early Warning list was imported with its table", any(
        (sec.get("source") or {}).get("type") == "early-warning-list" and any(b["kind"] == "table" for b in sec["blocks"])
        for sec in r3["sections"]))
    pg.wait_for_timeout(500)
    s.check("the imported section is on the screen", pg.locator(tid("playbook-section")).count() == len(r3["sections"]))
    r4 = say("Send for review to Khalid")
    s.check("sent for review, Khalid reviewing", r4["status"] == "in_review"
            and [p["username"] for p in r4["reviewers"]] == ["khalid.alotaibi"])
    pg.wait_for_function("() => document.querySelector('[data-testid=\"playbook-workflow\"]').innerText.includes('In review')",
                         timeout=30_000)
    kck = cookie_of("khalid.alotaibi")
    before = core_login.api_get("/api/v1/mail/counts", kck)["unread"]
    pg.click(tid("playbook-share"))
    pg.wait_for_selector(tid("share-dialog"))
    pg.fill(tid("share-to-input"), "khalid")
    pg.click(f'{tid("share-to-options")} [data-username="khalid.alotaibi"]')
    pg.fill(tid("share-note"), f"Sweep {run}: please review.")
    pg.click(tid("share-send"))
    pg.wait_for_selector(tid("share-done"), timeout=30_000)
    pg.click(tid("share-finish"))
    s.check("Khalid's unread count rose by one", core_login.api_get("/api/v1/mail/counts", kck)["unread"] == before + 1)
    th = core_login.api_get("/api/v1/mail/threads?folder=inbox", kck)["threads"][0]
    o = core_login.api_get(f"/api/v1/mail/threads/{th['thread_id']}", kck)["messages"][0]["attachments"][0]["object"]
    s.check("the mail carries the report, linking back to it", o["type"] == "report" and o["href"] == f"/playbook?report={rid}",
            f"/playbook?report={rid}", o.get("href"))
    s.finish()

    # ------------------------------------------------- import picker
    s.start("corporate", "R3-S1-1", "Import picker: sources by type; importing a Data Builder extract and a Borrower 360 page")
    pg.goto(UI + f"/playbook?report={rid}", wait_until="domcontentloaded")
    pg.wait_for_selector(tid("playbook-import"), timeout=60_000)
    # The report is In review: it can still be edited by its owner.
    pg.click(tid("playbook-import"))
    pg.wait_for_selector(tid("playbook-import-dialog"))
    pg.wait_for_selector(tid("playbook-source-row"), timeout=60_000)
    types = {pg.locator(tid("playbook-source-row")).nth(i).get_attribute("data-type")
             for i in range(pg.locator(tid("playbook-source-row")).count())}
    s.check("the picker lists every kind of work", {"early-warning-list", "borrower", "data-extract", "attention-item",
                                                     "whatif-scenario", "analysis", "investigation"} <= types, "", sorted(types))
    n0 = len(pb_get(f"/api/v1/playbook/reports/{rid}", sara)["sections"])
    pg.locator(f'{tid("playbook-source-row")}[data-type="data-extract"]').first.click()
    pg.wait_for_selector(tid("playbook-import-dialog"), state="detached", timeout=60_000)
    r5 = pb_get(f"/api/v1/playbook/reports/{rid}", sara)
    s.check("the extract was imported as a section", len(r5["sections"]) == n0 + 1
            and (r5["sections"][-1].get("source") or {}).get("type") == "data-extract")
    s.finish()
    s.page = page
    ctx.close()

    # ------------------------------------------- template and upload
    s.start("corporate", "R3-S1-1", "Start from a template (portfolio review) and from an uploaded Word document")
    page.goto(UI + "/playbook", wait_until="domcontentloaded")
    page.wait_for_selector(tid("playbook-template-portfolio-review"), timeout=60_000)
    page.click(tid("playbook-template-portfolio-review"))
    page.wait_for_selector(tid("playbook-new-dialog"))
    page.fill(tid("playbook-new-title"), f"Sweep {run} Real Estate portfolio review")
    page.click(tid("playbook-new-confirm"))
    wait_for(page, r"/playbook\?report=rp_", 60_000)
    page.wait_for_selector(tid("playbook-section"), timeout=60_000)
    s.check("the template's five sections, empty", page.locator(tid("playbook-section")).count() == 5)
    page.click(tid("playbook-back"))
    page.wait_for_selector(tid("playbook-upload-input"), timeout=60_000)
    data = _docx([("Heading 1", "Purpose"), ("Normal", f"Sweep {run}: review of the trade finance book."),
                  ("Heading 1", "Findings"), ("Normal", "Utilisation rose in the quarter.")])
    up = Path(tempfile.mkdtemp(dir=str(Path(__file__).resolve().parents[1] / "var"))) / f"sweep_{run}_trade_review.docx"
    up.write_bytes(data)
    page.set_input_files(tid("playbook-upload-input"), str(up))
    wait_for(page, r"/playbook\?report=rp_", 60_000)
    page.wait_for_selector(tid("playbook-section"), timeout=60_000)
    titles = page.locator(tid("playbook-section-title")).all_inner_texts()
    s.check("the upload became a report with its headings as sections", any("Purpose" in t for t in titles)
            and any("Findings" in t for t in titles), "Purpose, Findings", titles)
    page.click(tid("playbook-back"))
    page.wait_for_selector(tid("playbook-home"), timeout=60_000)
    s.finish()

    # --------------------------------------- Add to report from modules
    s.start("corporate", "R3-S1-1", "Add to report from Early Warning lands in Playbook, with its charts and tables; the section links back")
    page.goto(UI + "/early-warning?domain=corporate", wait_until="domcontentloaded")
    page.wait_for_selector(tid("ews-add-report-level"), timeout=120_000)
    here = page.url.replace(UI, "")
    page.click(tid("ews-add-report-level"))
    page.wait_for_selector(tid("add-report-dialog"))
    page.click(tid("add-report-new"))
    page.fill(tid("add-report-title"), f"Sweep {run} Early Warning pack")
    page.click(tid("add-report-confirm"))
    page.wait_for_selector(tid("add-report-done"), timeout=60_000)
    page.click(tid("add-report-open"))
    wait_for(page, r"/playbook\?report=rp_", 60_000)
    page.wait_for_selector(tid("playbook-provenance"), timeout=60_000)
    rid2 = page.url.split("report=")[1].split("&")[0]
    r6 = pb_get(f"/api/v1/playbook/reports/{rid2}", anne)
    sec = next(x for x in r6["sections"] if x.get("source"))
    s.check("the Early Warning section has its chart and table", {"chart", "table"} <= {b["kind"] for b in sec["blocks"]})
    s.check("it links back to the same Early Warning view", sec["source"]["href"] == here, here, sec["source"]["href"])
    s.finish()

    # -------------------------------------------------- Policy Docs
    s.start("both", "R3-S1-2", "Policy Docs: the library (policies and the circular), the active pack, a document with its clauses and files; Back")
    page.goto(UI + "/policy-docs", wait_until="domcontentloaded")
    page.wait_for_selector(tid("policy-doc-row"), timeout=120_000)
    docs = pb_get("/api/v1/policy/documents", anne)["documents"]
    s.check("every document the API lists is on the screen", page.locator(tid("policy-doc-row")).count() == len(docs),
            len(docs), page.locator(tid("policy-doc-row")).count())
    pack = pb_get("/api/v1/policy/pack", anne)
    s.check("the active pack and its clause count", pack["label"] in page.inner_text(tid("policy-active-pack"))
            and str(pack["clause_count"]) in page.inner_text(tid("policy-summary")))
    page.click(tid("policy-filter-circular"))
    page.wait_for_timeout(600)
    s.check("the Circulars tab shows the circulars", page.locator(tid("policy-doc-row")).count() == sum(
        1 for d in docs if d["kind"] == "circular"))
    page.click(tid("policy-filter-all"))
    page.goto(UI + "/policy-docs?doc=pd_policy_corporate", wait_until="domcontentloaded")
    page.wait_for_selector(tid("policy-clause"), timeout=60_000)
    full = pb_get("/api/v1/policy/documents/pd_policy_corporate", anne)
    s.check("the policy's clauses are all shown", page.locator(tid("policy-clause")).count() == len(full["clauses"]),
            len(full["clauses"]), page.locator(tid("policy-clause")).count())
    s.check("Word and PDF are attached", page.locator(tid("policy-file")).count() == 2)
    with page.expect_download(timeout=120_000) as d:
        page.locator(tid("policy-file")).filter(has_text=".pdf").first.click()
    pdf = Path(tempfile.mkdtemp(dir=str(Path(__file__).resolve().parents[1] / "var"))) / d.value.suggested_filename
    d.value.save_as(pdf)
    from pypdf import PdfReader

    ptxt = "\n".join(p.extract_text() or "" for p in PdfReader(str(pdf)).pages)
    s.check("the PDF reads as the Corporate Credit Policy with every clause", "Corporate Credit Policy" in ptxt
            and all(c["clause_id"] in ptxt for c in full["clauses"]))
    page.click(tid("policy-back"))
    page.wait_for_selector(tid("policy-library"), timeout=60_000)
    s.check("Back returns to the library", "/policy-docs" in page.url and "doc=" not in page.url)
    page.goto(UI + "/policy-docs?doc=pd_circ_c_2026_03&clause=RP-5.1", wait_until="domcontentloaded")
    page.wait_for_selector(f'{tid("policy-clause")}[data-id="RP-5.1"]', timeout=60_000)
    s.check("the circular's three clauses, RP-5.1 highlighted", page.locator(tid("policy-clause")).count() == 3
            and page.locator(f'{tid("policy-clause")}[data-id="RP-5.1"]').get_attribute("data-highlighted") == "true")
    s.finish()

    s.start("both", "R3-S1-2", "Add a circular: upload, AI interpretation, 'Add this to the Cockpit?' Yes, new pack version; then withdrawn (older versions stay on record)")
    v0 = pb_get("/api/v1/policy/pack/versions", anne)["versions"]
    ref = f"C-2026-{run[-2:]}"
    text = (f"Circular {ref}: Sector concentration\n\nCP-1.3 Sector concentration\nExposure to any one sector may not "
            "exceed 16% of the corporate book, and to any one sub-sector 6%. A sector above its limit is closed to new "
            "names until it is within it.\n").encode()
    f = Path(tempfile.mkdtemp(dir=str(Path(__file__).resolve().parents[1] / "var"))) / f"{ref}.txt"
    f.write_bytes(text)
    page.goto(UI + "/policy-docs", wait_until="domcontentloaded")
    page.wait_for_selector(tid("policy-add"), timeout=60_000)
    page.click(tid("policy-add"))
    page.wait_for_selector(tid("policy-add-dialog"))
    page.set_input_files(tid("policy-upload-input"), str(f))
    if page.locator(tid("policy-upload-submit")).count():
        page.click(tid("policy-upload-submit"))
    page.wait_for_selector(tid("policy-interpretation"), timeout=120_000)
    itxt = page.inner_text(tid("policy-interpretation"))
    s.check("the interpretation shows the clause, its limit and the change", "CP-1.3" in itxt and "16%" in itxt)
    s.check("it asks “Add this to the Cockpit?”", "Add this to the Cockpit?" in page.inner_text(tid("policy-add-dialog")))
    page.click(tid("policy-add-yes"))
    page.wait_for_selector(tid("policy-add-confirm"), timeout=30_000)
    page.click(tid("policy-add-confirm"))
    page.wait_for_selector(tid("policy-decision-result"), timeout=60_000)
    v1 = pb_get("/api/v1/policy/pack/versions", anne)["versions"]
    s.check("a new pack version is active", len(v1) == len(v0) + 1 and v1[0]["active"] and v1[0]["label"] in page.inner_text(tid("policy-add-dialog")))
    clause = next(c for c in pb_get("/api/v1/policy/clauses?book=corporate", anne)["clauses"] if c["clause_id"] == "CP-1.3")
    s.check("the clause in the active pack is the new one", "16%" in clause["rule"])
    doc_id = next(d["id"] for d in pb_get("/api/v1/policy/documents", anne)["documents"] if d["reference"] == ref)
    if page.locator(tid("policy-add-finish")).count():
        page.click(tid("policy-add-finish"))
    page.goto(UI + f"/policy-docs?doc={doc_id}", wait_until="domcontentloaded")
    page.wait_for_selector(tid("policy-withdraw"), timeout=60_000)
    page.click(tid("policy-withdraw"))
    page.wait_for_selector(tid("policy-withdraw-confirm"))
    page.click(tid("policy-withdraw-confirm"))
    page.wait_for_selector(tid("policy-withdraw-done"), timeout=60_000)
    clause = next(c for c in pb_get("/api/v1/policy/clauses?book=corporate", anne)["clauses"] if c["clause_id"] == "CP-1.3")
    s.check("withdrawn: the clause in force is the one before", "18%" in clause["rule"])
    s.check("older versions stay on record", len(pb_get("/api/v1/policy/pack/versions", anne)["versions"]) == len(v0) + 2)
    s.finish()

    s.start("both", "R3-S1-2", "Old document links: /documents opens Policy Docs, a moved document opens in Playbook")
    page.goto(UI + "/documents", wait_until="domcontentloaded")
    wait_for(page, r"/policy-docs", 60_000)
    page.wait_for_selector(tid("policy-library"), timeout=60_000)
    s.check("/documents → Policy Docs", "/policy-docs" in page.url)
    page.goto(UI + "/documents/credit-memo-cb01045", wait_until="domcontentloaded")
    wait_for(page, r"/playbook\?report=rp_memo_cb01045", 60_000)
    page.wait_for_selector(tid("playbook-section"), timeout=60_000)
    s.check("the moved credit memo opens in Playbook", "Rabigh Continental Contracting" in page.inner_text(tid("playbook-report")))
    s.finish()
