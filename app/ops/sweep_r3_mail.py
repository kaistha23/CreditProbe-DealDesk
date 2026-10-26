"""UAT sweep, PLAN_R3 S3-3: CreditProbe Mail, fully carved out.

`mail_steps(s, page, UI, wait_url)` is registered in ops/uat_sweep.py like `core_steps` (ops/uat_sweep_core.py), whose
helpers it reuses. Every figure on screen is checked against the Core service's API, every control is clicked, and
each step ends with no console error, no page error and no failed request. It sends real mail between the seeded
users and reads the expected counts from the API first, so it can be re-run; what it changes on seeded threads
(stars, labels, archive) it puts back.

Covers: the three panes; the list's fields (sender and avatar, subject, preview, attachment icon, time, unread dot,
star, label chips); star from the list; select, select all and the bulk actions (archive, move to Inbox, mark read,
mark unread, star, label, move to label); a new label with its colour; search with each filter (from, to, has
attachment, label, date range) and the filter chips; compose with To/Cc/Bcc from the directory, rich text (bold,
italic, list, link), a file and CreditProbe objects; the auto-saved draft in Drafts, reopened and sent; Discard;
Bcc privacy; reply, reply all and forward landing in the right mailboxes; the quoted-text toggle; an object card
opening in place, Close, Escape, Open full page and browser Back; the notifications bell, the new-mail toast and the
unread counts; the Administrator's mailboxes and audit log in the new layout; view-as read only; every Back path.
"""
from __future__ import annotations

import json
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import core_login
from uat_sweep_core import as_user, cookie_of, tid, urllib_status

M = "/api/v1/mail"
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _call(method: str, path: str, cookie: str, body: dict | None = None) -> Any:
    req = urllib.request.Request(core_login.CORE + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Cookie": f"cp_session={cookie}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310 - fixed loopback origin
            return json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return {"status": e.code}


def get(path: str, cookie: str) -> Any:
    return core_login.api_get(path, cookie)


def list_when(iso: str, now: datetime | None = None) -> str:
    """The list's time, as frontend/src/lib/v5/core.ts listWhen: HH:MM today (UTC), '7 Jul', '31 Dec 2025'."""
    now = now or datetime.now(timezone.utc)
    d = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(timezone.utc)
    if d.date() == now.date():
        return d.strftime("%H:%M")
    day = f"{d.day} {MONTHS[d.month - 1]}"
    return day if d.year == now.year else f"{day} {d.year}"


def api_for_url(url: str) -> str:
    """The threads API call that the Mail page at `url` makes (its address holds folder, search and filters)."""
    p = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
    q = {"folder": p.get("folder", "inbox"), "q": p.get("q", ""), "label": p.get("label", ""), "from": p.get("from", ""),
         "to": p.get("rcpt", ""), "has_attachment": "true" if p.get("att") == "1" else "", "date_from": p.get("after", ""),
         "date_to": p.get("before", ""), "limit": "50"}
    return f"{M}/threads?" + urllib.parse.urlencode({k: v for k, v in q.items() if v})


def rows(page) -> int:
    return page.locator(tid("mail-row")).count()


def row(tid_: str) -> str:
    return f'{tid("mail-row")}[data-thread-id="{tid_}"]'


def wait_rows(page, n: int, timeout: int = 30_000) -> None:
    page.wait_for_function("(n) => document.querySelectorAll('[data-testid=\"mail-row\"]').length === n", arg=n, timeout=timeout)


def settle(page) -> None:
    page.wait_for_load_state("networkidle")
    page.wait_for_selector(f'{tid("mail-total")}, {tid("mail-empty")}', timeout=60_000)


def mail_steps(s, page, UI: str, wait_url: Callable[..., Any]) -> None:
    browser = page.context.browser
    run_id = datetime.now(timezone.utc).strftime("%d%H%M%S")  # subjects of this run, so a re-run finds its own mail
    kck, sck, ock, rck, nck, lck, ack = (cookie_of(u) for u in (
        "khalid.alotaibi", "sara.aldosari", "omar.alghamdi", "reem.alshehri", "noura.alharbi", "lama.almutairi", "anne"))
    # a clean start on the seeded threads this sweep touches (an earlier run may have left them changed)
    for t in ("t_seed_pack", "t_seed_policy", "t_seed_minutes"):
        _call("POST", f"{M}/threads/{t}/star", kck, {"value": False})
        _call("POST", f"{M}/threads/{t}/archive", kck, {"value": False})
        _call("POST", f"{M}/threads/{t}/labels", kck, {"add": [], "remove": ["Models", "Sweep R3", "Policy"]})
    _call("DELETE", f"{M}/labels/Sweep%20R3", kck)
    _call("POST", f"{M}/threads/t_seed_minutes/read", kck, {"read": False})  # at least one unread row (the R2 sweep reads them all)

    # ------------------------------------------------------------ 1. three panes, list fields
    s.start("both", "R3-3", "Mail (Khalid): three panes; folders, coloured labels and unread counts; list fields equal the API")
    ctx_k, kp, _ = as_user(browser, s, "khalid.alotaibi")
    s.page = kp
    kp.goto(UI + "/messages", wait_until="domcontentloaded")
    kp.wait_for_selector(tid("mail-row"), timeout=90_000)
    settle(kp)
    s.check("three panes: folders, conversations, reading pane", all(kp.locator(tid(t)).is_visible() for t in
            ("mail-folders", "mail-list-pane", "mail-reading-pane")))
    s.check("folders: Inbox, Starred, Sent, Drafts, Archive, All mail",
            all(kp.locator(tid(f"folder-{f}")).count() == 1 for f in ("inbox", "starred", "sent", "drafts", "archive", "all")))
    counts = get(f"{M}/counts", kck)
    shown = kp.inner_text(tid("folder-inbox-count")).strip() if kp.locator(tid("folder-inbox-count")).count() else "0"
    s.check("Inbox count = unread conversations", shown == str(counts["unread"]), counts["unread"], shown)
    for f in ("starred", "archive", "all"):
        n = counts["unread_by_folder"][f]
        el = kp.locator(tid(f"folder-{f}-count"))
        s.check(f"{f}: unread count", (el.inner_text().strip() if el.count() else "0") == str(n), n, el.inner_text() if el.count() else "0")
    labels = get(f"{M}/labels", kck)["labels"]
    s.check("every label is listed", all(kp.locator(tid(f"label-{lab['name']}")).count() == 1 for lab in labels), [lab["name"] for lab in labels])
    for lab in labels:
        el = kp.locator(tid(f"label-{lab['name']}"))
        colour = el.locator("span").first.evaluate("e => getComputedStyle(e).backgroundColor")
        want = "rgb({}, {}, {})".format(*(int(lab["color"][i:i + 2], 16) for i in (1, 3, 5)))
        shown = kp.inner_text(tid(f"label-count-{lab['name']}")).strip()
        s.check(f"label {lab['name']}: colour and count", colour == want and shown == str(lab["unread"] or lab["count"] or ""),
                (want, lab["unread"] or lab["count"]), (colour, shown))
    api = get(f"{M}/threads?folder=inbox", kck)
    s.check("one row per conversation", rows(kp) == api["total"], api["total"], rows(kp))
    for t in api["threads"]:
        r = kp.locator(row(t["thread_id"]))
        others = [p for p in (t.get("senders") or t["participants"]) if p["username"] != "khalid.alotaibi"]
        sender = ", ".join(p["name"].split(" ")[0] for p in others[:3]) or "Me"
        got = {"sender": r.locator(tid("row-sender")).inner_text().split("(")[0].strip(), "subject": r.locator(tid("row-subject")).inner_text(),
               "snippet": r.locator(tid("row-snippet")).inner_text(), "time": r.locator(tid("row-time")).inner_text(),
               "unread": r.get_attribute("data-unread") == "true" and r.locator(tid("row-unread-dot")).count() == 1,
               "attachment": r.locator(tid("row-attachment")).count() == 1,
               "star": r.locator(tid("row-star")).get_attribute("aria-pressed") == "true",
               "labels": [x.get_attribute("data-label") for x in r.locator(tid("row-label")).all()],
               "avatar": others[0]["initials"] in r.inner_text() if others else True}
        want = {"sender": sender, "subject": t["subject"], "snippet": t["snippet"], "time": list_when(t["last_at"]),
                "unread": t["unread"], "attachment": t["has_attachments"], "star": t["starred"], "labels": t["labels"], "avatar": True}
        s.check(f"{t['thread_id']}: sender, avatar, subject, preview, attachment icon, time, unread, star, labels", got == want, want, got)
    s.check("unread rows are bold", kp.locator(f'{tid("mail-row")}[data-unread="true"] {tid("row-subject")}').first.evaluate(
        "e => +getComputedStyle(e).fontWeight >= 600"))

    # ------------------------------------------------------------ 2. star, select, bulk
    s.start("both", "R3-3", "Mail (Khalid): star from the list; select, select all; bulk archive, move to Inbox, read, unread, star, label, move to label")
    kp.locator(f'{row("t_seed_pack")} {tid("row-star")}').click()
    kp.wait_for_selector(f'{row("t_seed_pack")}[data-starred="true"]', timeout=30_000)
    s.check("star from the list: Starred in the API", get(f"{M}/threads/t_seed_pack", kck)["starred"] is True)
    kp.locator(f'{row("t_seed_pack")} {tid("row-star")}').click()
    kp.wait_for_selector(f'{row("t_seed_pack")}[data-starred="false"]', timeout=30_000)
    pick = ["t_seed_pack", "t_seed_policy"]

    def select(ids: list[str]) -> None:
        for t in ids:
            kp.locator(f'{row(t)} {tid("row-select")}').check()
        kp.wait_for_selector(tid("mail-bulk-bar"))

    select(pick)
    s.check("bulk bar: 2 selected", kp.inner_text(tid("mail-selected-count")).startswith("2 selected"), "2 selected", kp.inner_text(tid("mail-selected-count")))
    kp.click(tid("bulk-read"))
    kp.wait_for_selector(tid("mail-toast"))
    kp.wait_for_selector(f'{row("t_seed_pack")}[data-unread="false"]', timeout=30_000)
    s.check("Mark read: both read", all(get(f"{M}/threads/{t}", kck)["unread"] is False for t in pick))
    before = get(f"{M}/counts", kck)
    select(pick)
    kp.click(tid("bulk-unread"))
    kp.wait_for_selector(f'{row("t_seed_pack")}[data-unread="true"]', timeout=30_000)
    after = get(f"{M}/counts", kck)
    s.check("Mark unread: both unread, the Inbox count rises by 2", after["unread"] == before["unread"] + 2, before["unread"] + 2, after["unread"])
    kp.wait_for_function("(n) => document.querySelector('[data-testid=\"folder-inbox-count\"]').innerText.trim() === String(n)", arg=after["unread"], timeout=30_000)
    select(pick)
    kp.click(tid("bulk-star"))
    kp.wait_for_selector(f'{row("t_seed_policy")}[data-starred="true"]', timeout=30_000)
    s.check("Star: both starred", all(get(f"{M}/threads/{t}", kck)["starred"] for t in pick))
    for t in pick:
        _call("POST", f"{M}/threads/{t}/star", kck, {"value": False})
    n0 = rows(kp)
    select(pick)
    kp.click(tid("bulk-archive"))
    wait_rows(kp, n0 - 2)
    s.check("Archive: both leave the Inbox and are in Archive", set(pick) <= {t["thread_id"] for t in get(f"{M}/threads?folder=archive", kck)["threads"]})
    kp.click(tid("folder-archive"))
    kp.wait_for_selector(row("t_seed_pack"))
    select(pick)
    kp.click(tid("bulk-unarchive"))
    kp.wait_for_selector(row("t_seed_pack"), state="detached", timeout=30_000)
    s.check("Move to Inbox: both back", not set(pick) & {t["thread_id"] for t in get(f"{M}/threads?folder=archive", kck)["threads"]})
    kp.click(tid("folder-inbox"))
    kp.wait_for_selector(row("t_seed_pack"))
    settle(kp)
    kp.check(tid("mail-select-all"))
    s.check("Select all selects every row", kp.inner_text(tid("mail-selected-count")).startswith(f"{rows(kp)} selected"), rows(kp), kp.inner_text(tid("mail-selected-count")))
    kp.click(tid("bulk-clear"))
    s.check("clearing the selection hides the bar", kp.locator(tid("mail-bulk-bar")).count() == 0)
    select(pick)
    kp.click(tid("bulk-label"))
    kp.click(tid("bulk-label-option-Models"))
    kp.wait_for_selector(f'{row("t_seed_pack")} {tid("row-label")}[data-label="Models"]', timeout=30_000)
    s.check("Label as Models: both labelled, still in the Inbox", all("Models" in get(f"{M}/threads/{t}", kck)["labels"] for t in pick)
            and kp.locator(row("t_seed_policy")).count() == 1)
    n1 = rows(kp)
    select(["t_seed_policy"])
    kp.click(tid("bulk-move"))
    kp.click(tid("bulk-move-option-Policy"))
    wait_rows(kp, n1 - 1)
    pol = get(f"{M}/threads/t_seed_policy", kck)
    s.check("Move to Policy: labelled and out of the Inbox", "Policy" in pol["labels"] and pol["archived"] is True)
    kp.click(tid("label-Policy"))
    kp.wait_for_selector(row("t_seed_policy"))
    settle(kp)
    s.check("the Policy label lists it (All mail, label filter)", rows(kp) == get(f"{M}/threads?folder=all&label=Policy", kck)["total"])
    for t in pick:
        _call("POST", f"{M}/bulk", kck, {"thread_ids": [t], "action": "unlabel", "label": "Models"})
    _call("POST", f"{M}/threads/t_seed_policy/archive", kck, {"value": False})
    _call("POST", f"{M}/threads/t_seed_policy/labels", kck, {"add": [], "remove": ["Policy"]})
    ev = get(f"{M}/audit?actor=khalid.alotaibi&action=bulk", ack)["events"]
    s.check("bulk actions are in the audit log", len(ev) >= 6, ">= 6", len(ev))

    # ------------------------------------------------------------ 3. a new label
    s.start("both", "R3-3", "Mail (Khalid): a new label with its colour; applied from the conversation; listed and counted")
    kp.click(tid("folder-inbox"))
    kp.wait_for_selector(row("t_seed_pack"))
    kp.click(tid("label-create"))
    kp.fill(tid("label-create-name"), "Sweep R3")
    kp.click(tid("label-create-color-db2777"))
    kp.click(tid("label-create-submit"))
    kp.wait_for_selector(tid("label-Sweep R3"), timeout=30_000)
    made = {lab["name"]: lab for lab in get(f"{M}/labels", kck)["labels"]}.get("Sweep R3", {})
    s.check("label created with its colour", made.get("color") == "#db2777", "#db2777", made)
    kp.click(row("t_seed_pack"))
    kp.wait_for_selector(f'{tid("thread-view")}[data-thread-id="t_seed_pack"]')
    kp.click(tid("thread-labels"))
    kp.click(tid("label-toggle-Sweep R3"))
    kp.wait_for_selector(f'{tid("thread-label")}[data-label="Sweep R3"]', timeout=30_000)
    kp.click(tid("thread-labels"))
    kp.wait_for_function("() => document.querySelector('[data-testid=\"label-count-Sweep R3\"]').innerText.trim() !== ''", timeout=30_000)
    s.check("label count on the folders pane", kp.inner_text(tid("label-count-Sweep R3")).strip() == "1", "1", kp.inner_text(tid("label-count-Sweep R3")))
    kp.click(tid("label-Sweep R3"))
    kp.wait_for_function("() => /label=Sweep/.test(location.search)")
    wait_rows(kp, 1)
    s.check("the label lists the conversation", kp.locator(row("t_seed_pack")).count() == 1)
    _call("DELETE", f"{M}/labels/Sweep%20R3", kck)
    _call("POST", f"{M}/threads/t_seed_pack/read", kck, {"read": False})

    # ------------------------------------------------------------ 4. search and filters
    s.start("both", "R3-3", "Mail (Khalid): search with each filter (from, to, has attachment, label, date range) equals the server's search")
    kp.goto(UI + "/messages", wait_until="domcontentloaded")
    kp.wait_for_selector(tid("mail-row"), timeout=90_000)

    def same_as_api(what: str) -> None:
        settle(kp)
        want = get(api_for_url(kp.url), kck)
        got = [r.get_attribute("data-thread-id") for r in kp.locator(tid("mail-row")).all()]
        s.check(f"{what}: the rows equal the API", got == [t["thread_id"] or t.get("draft_id") for t in want["threads"]],
                [t["thread_id"] for t in want["threads"]], got)

    kp.fill(tid("mail-search"), "Construction")
    kp.wait_for_function("() => /q=Construction/.test(location.search)")
    same_as_api("free text 'Construction'")
    kp.click(tid("mail-search-clear"))
    kp.wait_for_function("() => !/q=/.test(location.search)")
    for what, fill, url_part in (
            ("From: Sara", lambda: kp.select_option(tid("filter-from"), "sara.aldosari"), "from=sara.aldosari"),
            ("To: Anne", lambda: kp.select_option(tid("filter-to"), "anne"), "rcpt=anne"),
            ("Has attachment", lambda: kp.check(tid("filter-has-attachment")), "att=1"),
            ("Label: Committee", lambda: kp.select_option(tid("filter-label"), "Committee"), "label=Committee"),
            ("Date range 16 to 20 Jul 2026", lambda: (kp.fill(tid("filter-date-from"), "2026-07-16"), kp.fill(tid("filter-date-to"), "2026-07-20")),
             "after=2026-07-16")):
        kp.click(tid("mail-filters-toggle"))
        kp.wait_for_selector(tid("mail-filters"))
        kp.click(tid("filter-clear"))
        kp.wait_for_function("() => !/(from|rcpt|att|after|before|label)=/.test(location.search)", timeout=30_000)
        kp.click(tid("mail-filters-toggle"))
        kp.wait_for_selector(tid("mail-filters"))
        fill()
        kp.click(tid("filter-apply"))
        kp.wait_for_function("(p) => location.search.includes(p)", arg=url_part, timeout=30_000)
        same_as_api(what)
        s.check(f"{what}: a filter chip shows it", kp.locator(tid("filter-chip")).count() >= 1, ">= 1", kp.locator(tid("filter-chip")).count())
    # filters combine with free text, and a chip clears its filter
    kp.fill(tid("mail-search"), "pack")
    kp.wait_for_function("() => /q=pack/.test(location.search)")
    same_as_api("date range and free text 'pack'")
    kp.click(tid("filter-chip-clear-after"))
    kp.wait_for_function("() => !/after=/.test(location.search)")
    same_as_api("after clearing the From-date chip")
    kp.fill(tid("mail-search"), "zzzz-nothing")
    kp.wait_for_selector(tid("mail-empty"), timeout=30_000)
    s.check("no match says so", "No messages match" in kp.inner_text(tid("mail-empty")))
    kp.goto(UI + "/messages", wait_until="domcontentloaded")
    kp.wait_for_selector(tid("mail-row"), timeout=90_000)

    # ------------------------------------------------------------ 5. compose
    s.start("both", "R3-3", "Mail (Sara): To/Cc/Bcc from the directory, rich text, a file and objects; the draft saves itself and is in Drafts")
    tmp = Path(tempfile.mkdtemp()) / "sweep-r3-notes.txt"
    tmp.write_text("Sweep R3 attachment: retail cohort notes\n")
    ctx_s, sp, _ = as_user(browser, s, "sara.aldosari")
    s.page = sp
    drafts0 = get(f"{M}/counts", sck)["drafts"]
    sp.goto(UI + "/messages", wait_until="domcontentloaded")
    sp.wait_for_selector(tid("mail-compose"), timeout=90_000)
    sp.click(tid("mail-compose"))
    sp.wait_for_selector(tid("compose-dialog"))
    for field, text, user in (("to", "Om", "omar.alghamdi"), ("cc", "Reem", "reem.alshehri"), ("bcc", "nou", "noura.alharbi")):
        if field != "to":
            sp.click(tid(f"compose-add-{field}"))
        sp.fill(tid(f"compose-{field}-input"), text)
        sp.wait_for_selector(f'{tid(f"compose-{field}-options")} [data-username="{user}"]')
        s.check(f"{field.capitalize()}: the directory suggests {user} for '{text}'", True)
        sp.click(f'{tid(f"compose-{field}-options")} [data-username="{user}"]')
        sp.keyboard.press("Escape")
        s.check(f"{field.capitalize()}: chip for {user}", sp.locator(f'{tid(f"compose-{field}-chip")}[data-username="{user}"]').count() == 1)
    sp.fill(tid("compose-bcc-input"), "Om")
    s.check("someone already in To is not offered in Bcc", sp.locator(f'{tid("compose-bcc-options")} [data-username="omar.alghamdi"]').count() == 0)
    sp.fill(tid("compose-bcc-input"), "")
    sp.keyboard.press("Escape")
    subj = f"Sweep R3: retail cohort {run_id}"
    sp.fill(tid("compose-subject"), subj)
    sp.click(tid("compose-body"))
    sp.keyboard.type("Omar, the cohort is ")
    sp.click(tid("rte-bold"))
    sp.keyboard.type("ready")
    sp.click(tid("rte-bold"))
    sp.keyboard.type(" and ")
    sp.click(tid("rte-italic"))
    sp.keyboard.type("checked")
    sp.click(tid("rte-italic"))
    sp.keyboard.press("Enter")
    sp.click(tid("rte-bulleted-list"))
    sp.keyboard.type("Stage 2 split")
    sp.keyboard.press("Enter")
    sp.keyboard.type("Early Warning list ")
    sp.click(tid("rte-link"))
    sp.fill(tid("rte-link-input"), "/early-warning?domain=retail")
    sp.click(tid("rte-link-apply"))
    sp.set_input_files(tid("compose-file-input"), str(tmp))
    sp.wait_for_selector(tid("mail-file"), timeout=30_000)
    sp.click(tid("compose-attach-object"))
    sp.wait_for_selector(tid("object-picker"))
    sp.click(tid("pick-borrower"))
    sp.fill(tid("pick-borrower-id"), "CB01312")
    sp.click(tid("pick-confirm"))
    sp.click(tid("compose-attach-object"))
    sp.click(tid("pick-page"))
    sp.select_option(tid("pick-page-type"), "scorecard-validation")
    sp.fill(tid("pick-page-path"), "/scorecard-validation")
    sp.fill(tid("pick-page-label"), "Scorecard validation: retail application")
    sp.click(tid("pick-confirm"))
    sp.wait_for_function("() => document.querySelectorAll('[data-testid=\"compose-attachments\"] [data-testid=\"mail-object\"]').length === 2")
    s.check("file and two objects attached", sp.locator(f'{tid("compose-attachments")} {tid("mail-file")}').count() == 1)
    sp.wait_for_selector(f'{tid("compose-autosave")}[data-state="saved"]', timeout=30_000)
    s.check("auto-save: 'Saved' with the time", sp.inner_text(tid("compose-autosave")).startswith("Saved"), "Saved hh:mm UTC", sp.inner_text(tid("compose-autosave")))
    drafts = get(f"{M}/threads?folder=drafts", sck)["threads"]
    mine = [d for d in drafts if d["subject"] == subj]
    s.check("auto-saved draft is stored once", len(mine) == 1 and get(f"{M}/counts", sck)["drafts"] == drafts0 + 1, 1, len(mine))
    if mine:
        d = get(f"{M}/drafts/{mine[0]['draft_id']}", sck)
        s.check("the stored draft has To, Cc, Bcc, rich text and attachments",
                (d["to"], d["cc"], d["bcc"]) == (["omar.alghamdi"], ["reem.alshehri"], ["noura.alharbi"])
                and "<strong>ready</strong>" in d["body_html"] and len(d["attachments"]) == 3, "to/cc/bcc, <strong>, 3 attachments", d)
    sp.click(tid("compose-close"))
    sp.wait_for_selector(tid("compose-dialog"), state="detached")
    sp.click(tid("folder-drafts"))
    sp.wait_for_function("() => document.querySelector('[data-testid=\"folder-drafts\"]').getAttribute('aria-current') === 'page'")
    draft_row = sp.locator(f'{tid("mail-row")}[data-thread-id^="d_"]', has_text=subj)
    draft_row.first.wait_for(timeout=30_000)
    s.check("the auto-saved draft is in Drafts", draft_row.count() == 1, 1, draft_row.count())
    draft_row.first.click()
    sp.wait_for_selector(tid("compose-dialog"))
    sp.wait_for_selector(f'{tid("compose-bcc-chip")}[data-username="noura.alharbi"]', timeout=30_000)
    s.check("reopened: subject, body, Bcc and attachments restored",
            sp.input_value(tid("compose-subject")) == subj and "ready" in sp.inner_text(tid("compose-body"))
            and sp.locator(f'{tid("compose-attachments")} {tid("mail-object")}').count() == 2)

    s.start("both", "R3-3", "Mail (Sara): send the draft; Bcc stays private; it lands in Sent and the recipients' Inboxes")
    before = {u: get(f"{M}/counts", c)["unread"] for u, c in (("omar", ock), ("reem", rck), ("noura", nck))}
    sp.click(tid("compose-send"))
    sp.wait_for_selector(tid("mail-toast"))
    sp.wait_for_selector(tid("thread-view"), timeout=60_000)
    sent = urllib.parse.parse_qs(urllib.parse.urlparse(sp.url).query)["thread"][0]
    s.check("lands on the conversation in Sent", "folder=sent" in sp.url, "folder=sent", sp.url)
    s.check("the draft is gone", get(f"{M}/counts", sck)["drafts"] == drafts0, drafts0, get(f"{M}/counts", sck)["drafts"])
    m0 = get(f"{M}/threads/{sent}", sck)["messages"][0]
    s.check("stored: bold, italic, list, link", all(x in m0["body_html"] for x in ("<strong>ready</strong>", "<em>checked</em>", "<li>", 'href="/early-warning?domain=retail"')),
            "strong, em, li, a", m0["body_html"][:200])
    s.check("stored: file + borrower + scorecard validation", sorted((a["kind"], a.get("object", {}).get("type", "")) for a in m0["attachments"])
            == [("file", ""), ("object", "borrower"), ("object", "scorecard-validation")])
    s.check("Sara sees her Bcc", sp.locator(tid("message-bcc")).count() >= 1 and "Noura" in sp.inner_text(tid("message-bcc")))
    after = {u: get(f"{M}/counts", c)["unread"] for u, c in (("omar", ock), ("reem", rck), ("noura", nck))}
    s.check("Omar, Reem and Noura each have one more unread", all(after[u] == before[u] + 1 for u in before), before, after)
    for who, c in (("Omar", ock), ("Reem", rck)):
        m = get(f"{M}/threads/{sent}", c)["messages"][0]
        s.check(f"{who} does not see the Bcc", m["bcc"] == [] and "noura" not in json.dumps(m["to"] + m["cc"]))
    s.check("Noura sees only herself in Bcc", [u["username"] for u in get(f"{M}/threads/{sent}", nck)["messages"][0]["bcc"]] == ["noura.alharbi"])

    s.start("both", "R3-3", "Mail (Sara): Discard deletes an auto-saved draft")
    d0 = get(f"{M}/counts", sck)["drafts"]
    sp.click(tid("mail-compose"))
    sp.wait_for_selector(tid("compose-dialog"))
    sp.fill(tid("compose-subject"), "Sweep R3: to be discarded")
    sp.wait_for_selector(f'{tid("compose-autosave")}[data-state="saved"]', timeout=30_000)
    s.check("it auto-saved", get(f"{M}/counts", sck)["drafts"] == d0 + 1)
    sp.click(tid("compose-discard"))
    sp.wait_for_selector(tid("compose-dialog"), state="detached")
    sp.wait_for_load_state("networkidle")
    s.check("Discard deleted it", get(f"{M}/counts", sck)["drafts"] == d0, d0, get(f"{M}/counts", sck)["drafts"])

    # ------------------------------------------------------------ 6. reply, reply all, forward, quoted text
    s.start("both", "R3-3", "Mail: Omar replies all (never to the Bcc), Reem replies, Sara forwards; each lands in the right mailboxes; quoted text folds")
    ctx_o, op, _ = as_user(browser, s, "omar.alghamdi")
    s.page = op
    op.goto(UI + f"/messages?thread={sent}", wait_until="domcontentloaded")
    op.wait_for_selector(tid("thread-view"), timeout=90_000)
    s.check("Omar: To and Cc shown, no Bcc", "Reem" in op.inner_text(tid("message-recipients")) and op.locator(tid("message-bcc")).count() == 0
            and "Noura" not in op.inner_text(tid("thread-view")))
    s.check("Omar: the file and both objects are cards", op.locator(tid("mail-file")).count() == 1 and op.locator(tid("mail-object")).count() == 2)
    op.click(tid("mail-reply-all"))
    op.wait_for_selector(f'{tid("compose")}[data-mode="reply_all"]')
    chips = sorted(e.get_attribute("data-username") for e in op.locator(f'{tid("compose-to-chip")}, {tid("compose-cc-chip")}, {tid("compose-bcc-chip")}').all())
    s.check("Reply all: Sara and Reem, not Noura (Bcc), not me", chips == ["reem.alshehri", "sara.aldosari"], ["reem.alshehri", "sara.aldosari"], chips)
    op.click(tid("compose-body"))
    op.keyboard.type("Thanks. Split is done.")
    op.click(tid("compose-send"))
    op.wait_for_selector(tid("mail-toast"))
    op.wait_for_function("() => document.querySelectorAll('[data-testid=\"mail-message\"]').length === 2", timeout=30_000)
    s.check("reply all: Sara and Reem have 2 messages, Noura still 1",
            [len(get(f"{M}/threads/{sent}", c)["messages"]) for c in (sck, rck, nck)] == [2, 2, 1],
            [2, 2, 1], [len(get(f"{M}/threads/{sent}", c)["messages"]) for c in (sck, rck, nck)])
    s.check("Omar's reply quotes the message: folded behind 'Show quoted text'",
            op.locator(f'{tid("mail-message")} >> nth=1').locator(tid("quoted-toggle")).count() == 1
            and op.locator(f'{tid("mail-message")} >> nth=1').locator(tid("message-quoted")).count() == 0)
    last = op.locator(f'{tid("mail-message")} >> nth=1')
    last.locator(tid("quoted-toggle")).click()
    last.locator(tid("message-quoted")).wait_for()
    s.check("Show quoted text: the original is shown", "Omar, the cohort is" in last.locator(tid("message-quoted")).inner_text())
    last.locator(tid("quoted-toggle")).click()
    s.check("Hide quoted text: folded again", last.locator(tid("message-quoted")).count() == 0)

    ctx_r, rp, _ = as_user(browser, s, "reem.alshehri")
    s.page = rp
    rp.goto(UI + f"/messages?thread={sent}", wait_until="domcontentloaded")
    rp.wait_for_selector(tid("mail-reply"), timeout=90_000)
    rp.click(tid("mail-reply"))
    rp.wait_for_selector(f'{tid("compose")}[data-mode="reply"]')
    to = [e.get_attribute("data-username") for e in rp.locator(tid("compose-to-chip")).all()]
    s.check("Reply: to the last sender only (Omar)", to == ["omar.alghamdi"], ["omar.alghamdi"], to)
    rp.click(tid("compose-body"))
    rp.keyboard.type("Noted, thank you.")
    rp.click(tid("compose-send"))
    rp.wait_for_selector(tid("mail-toast"))
    s.check("Reply: Omar has 3 messages, Sara still 2", (len(get(f"{M}/threads/{sent}", ock)["messages"]), len(get(f"{M}/threads/{sent}", sck)["messages"])) == (3, 2))

    s.page = sp
    sp.goto(UI + f"/messages?thread={sent}&folder=sent", wait_until="domcontentloaded")
    sp.wait_for_selector(tid("thread-view"), timeout=90_000)
    sp.locator(f'{tid("mail-message")} button[aria-expanded]').first.click()
    sp.wait_for_selector(tid("mail-forward"))
    sp.locator(tid("mail-forward")).first.click()
    sp.wait_for_selector(f'{tid("compose")}[data-mode="forward"]')
    s.check("Forward: Fwd: subject, the original's attachments carried",
            sp.input_value(tid("compose-subject")) == f"Fwd: {subj}" and sp.locator(f'{tid("compose-attachments")} {tid("mail-object")}').count() == 2)
    sp.fill(tid("compose-to-input"), "lama")
    sp.click(f'{tid("compose-to-options")} [data-username="lama.almutairi"]')
    sp.click(tid("compose-send"))
    sp.wait_for_selector(tid("mail-toast"))
    lama = get(f"{M}/threads?" + urllib.parse.urlencode({"folder": "inbox", "q": f"Fwd: {subj}"}), lck)["threads"]
    s.check("Forward: a new conversation in Lama's Inbox", len(lama) >= 1 and lama[0]["thread_id"] != sent)
    s.check("Forward: Lama cannot open the original", urllib_status(f"{M}/threads/{sent}", lck) == 403)

    # ------------------------------------------------------------ 7. objects in place, Back paths
    s.start("both", "R3-3", "Mail (Khalid): an object card opens in place; Close, Escape, Open full page and Back return; seeded quoted text")
    s.page = kp
    kp.goto(UI + "/messages?thread=t_seed_overlay", wait_until="domcontentloaded")
    kp.wait_for_selector(f'{tid("thread-view")}[data-thread-id="t_seed_overlay"]', timeout=90_000)
    reply = kp.locator(f'{tid("mail-message")} >> nth=1')
    s.check("seeded reply: the quote is folded", reply.locator(tid("quoted-toggle")).count() == 1 and reply.locator(tid("message-quoted")).count() == 0)
    reply.locator(tid("quoted-toggle")).click()
    s.check("Show quoted text: 'Khalid Al-Otaibi wrote:'", "Khalid Al-Otaibi wrote:" in reply.locator(tid("message-quoted")).inner_text())
    with kp.expect_download() as dl:
        kp.locator(tid("mail-file-link")).first.click()
    s.check("the seeded CSV downloads", Path(dl.value.path()).read_text().startswith("sub_sector,"))
    kp.goto(UI + "/messages?thread=t_seed_cb01312", wait_until="domcontentloaded")
    kp.wait_for_selector(tid("mail-object-open"), timeout=90_000)
    kp.locator(tid("mail-object-open")).first.click()
    kp.wait_for_selector(tid("object-panel"))
    s.check("opens in place: the panel names CB01312", "CB01312" in kp.inner_text(tid("object-panel-title")))
    kp.click(tid("object-panel-close"))
    s.check("Close returns to the conversation", kp.locator(tid("object-panel")).count() == 0 and kp.locator(tid("thread-view")).count() == 1)
    kp.locator(tid("mail-object-open")).first.click()
    kp.wait_for_selector(tid("object-panel"))
    kp.keyboard.press("Escape")
    kp.wait_for_selector(tid("object-panel"), state="detached")
    s.check("Escape returns to the conversation", kp.locator(tid("thread-view")).count() == 1)
    kp.locator(tid("mail-object-full")).first.click()
    wait_url(kp, r".*/borrower-360.*CB01312.*")
    s.check("the card's Open full page goes to Borrower 360", "customer_id=CB01312" in kp.url, "/borrower-360?…CB01312", kp.url)
    kp.go_back()
    kp.wait_for_selector(tid("thread-view"), timeout=60_000)
    s.check("browser Back returns to the conversation", "thread=t_seed_cb01312" in kp.url, "thread=t_seed_cb01312", kp.url)
    # R7: Back is the exact previous screen: here the conversation opened before this one (t_seed_overlay).
    kp.click(tid("mail-back"))
    kp.wait_for_function("() => /thread=t_seed_overlay/.test(location.search)")
    s.check("Back returns to the previous screen (the conversation read before)", "thread=t_seed_overlay" in kp.url,
            "thread=t_seed_overlay", kp.url)
    kp.goto(UI + "/messages", wait_until="domcontentloaded")
    kp.wait_for_selector(row("t_seed_cb01312"), timeout=60_000)
    kp.click(row("t_seed_cb01312"))
    kp.wait_for_selector(tid("mail-back"))
    kp.click(tid("mail-back"))
    kp.wait_for_function("() => !/thread=/.test(location.search)")
    s.check("opened from the list, Back returns to the list", kp.locator(tid("mail-select")).count() == 1)
    kp.click(row("t_seed_cb01312"))
    kp.wait_for_selector(tid("thread-close"))
    kp.click(tid("thread-close"))
    kp.wait_for_function("() => !/thread=/.test(location.search)")
    s.check("the conversation's Close (X) returns to the list", kp.locator(tid("mail-select")).count() == 1)
    kp.goto(UI + "/messages/t_seed_cb01312", wait_until="domcontentloaded")
    kp.wait_for_selector(tid("thread-view"), timeout=90_000)
    s.check("an old /messages/<id> link opens the conversation", "thread=t_seed_cb01312" in kp.url, "thread=t_seed_cb01312", kp.url)

    # ------------------------------------------------------------ 8. notifications and unread count
    s.start("both", "R3-3", "Notifications: new mail raises the bell, the Mail badge and the Inbox count, and shows a toast that opens it")
    kp.goto(UI + "/messages", wait_until="domcontentloaded")
    kp.wait_for_selector(tid("mail-row"), timeout=90_000)
    kp.wait_for_load_state("networkidle")
    c0 = get(f"{M}/counts", kck)
    badge0 = kp.inner_text(tid("header-mail-unread")).strip() if kp.locator(tid("header-mail-unread")).count() else "0"
    s.check("Mail badge = unread conversations", badge0 == str(c0["unread"]), c0["unread"], badge0)
    bell0 = kp.inner_text(tid("header-notifications-count")).strip() if kp.locator(tid("header-notifications-count")).count() else "0"
    s.check("bell count = unread notifications", bell0 == str(min(c0["notifications"], 99)) or (bell0 == "99+" and c0["notifications"] > 99), c0["notifications"], bell0)
    new = _call("POST", f"{M}/send", sck, {"to": ["khalid.alotaibi"], "cc": [], "subject": f"Sweep R3: new mail toast {run_id}",
                                         "body_html": "<p>Khalid, a quick one.</p>", "attachments": [], "mode": "new"})
    kp.wait_for_selector(tid("mail-new-toast"), timeout=45_000)
    s.check("toast: names the sender and subject", f"Sweep R3: new mail toast {run_id}" in kp.inner_text(tid("mail-new-toast-title"))
            and "Sara Al-Dosari" in kp.inner_text(tid("mail-new-toast-title")))
    kp.wait_for_function("(n) => document.querySelector('[data-testid=\"header-mail-unread\"]')?.innerText.trim() === String(n)", arg=c0["unread"] + 1, timeout=30_000)
    s.check("Mail badge rose by one", True)
    kp.wait_for_function("(n) => document.querySelector('[data-testid=\"folder-inbox-count\"]')?.innerText.trim() === String(n)", arg=c0["unread"] + 1, timeout=45_000)
    s.check("Inbox count rose by one (the list re-reads)", kp.locator(row(new["thread_id"])).count() == 1)
    kp.click(tid("header-notifications"))
    kp.wait_for_selector(tid("notifications-panel"))
    first = kp.locator(tid("notification-item")).first
    s.check("the bell lists it first, unread", first.get_attribute("data-href") == f"/messages?thread={new['thread_id']}" and first.get_attribute("data-read") == "false")
    kp.keyboard.press("Escape")
    kp.click("body", position={"x": 5, "y": 500})
    if kp.locator(tid("mail-new-toast-open")).count():
        kp.click(tid("mail-new-toast-open"))
    else:
        kp.click(row(new["thread_id"]))
    kp.wait_for_selector(f'{tid("thread-view")}[data-thread-id="{new["thread_id"]}"]', timeout=60_000)
    kp.wait_for_load_state("networkidle")
    c1 = get(f"{M}/counts", kck)
    s.check("opening it marks it read: back to the earlier unread count", c1["unread"] == c0["unread"], c0["unread"], c1["unread"])
    s.finish()

    # ------------------------------------------------------------ 9. admin
    s.start("both", "R3-3", "Administrator: all mailboxes and the audit log inside the three-pane layout; Back paths")
    ctx_a, ap, _ = as_user(browser, s, "anne")
    s.page = ap
    ap.goto(UI + "/messages", wait_until="domcontentloaded")
    ap.wait_for_selector(tid("admin-nav-mailboxes"), timeout=90_000)
    ap.click(tid("admin-nav-mailboxes"))
    ap.wait_for_selector(tid("mail-admin"))
    s.check("admin view keeps the folders pane", ap.locator(tid("mail-folders")).is_visible())
    boxes = get(f"{M}/admin/mailboxes", ack)["mailboxes"]
    for b in boxes:
        txt = ap.inner_text(tid(f"mailbox-{b['user']['username']}"))
        c = b["counts"]
        s.check(f"{b['user']['username']}: inbox, unread, sent, drafts, archive equal the API",
                all(str(c[k]) in txt for k in ("inbox", "unread", "sent", "drafts", "archive")), c, txt)
    ap.click(tid("open-mailbox-sara.aldosari"))
    ap.wait_for_selector(tid("mailbox-banner"), timeout=60_000)
    settle(ap)
    s.check("Sara's mailbox, read only: rows equal her Inbox, no select or compose",
            rows(ap) == get(f"{M}/threads?folder=inbox", sck)["total"] and ap.locator(tid("row-select")).count() == 0
            and ap.locator(tid("mail-compose")).is_disabled())
    ap.click(tid("mailbox-back"))
    ap.wait_for_selector(tid("mail-admin"))
    ap.click(tid("admin-nav-audit"))
    ap.select_option(tid("audit-action"), "bulk")
    ap.wait_for_function("() => document.querySelectorAll('[data-testid=\"audit-rows\"] tr').length >= 1", timeout=30_000)
    total = get(f"{M}/audit?action=bulk", ack)["total"]
    s.check("audit log: bulk actions listed, total equals the API", str(total) in ap.inner_text(tid("audit-total")), total, ap.inner_text(tid("audit-total")))
    ap.click(tid("folder-inbox"))
    ap.wait_for_selector(tid("mail-list"), timeout=60_000)
    s.check("a folder leaves the admin view (Back to Mail)", ap.locator(tid("mail-admin")).count() == 0 and "admin=1" not in ap.url)
    ctx_u, up, _ = as_user(browser, s, "omar.alghamdi")
    up.goto(UI + "/messages", wait_until="domcontentloaded")
    up.wait_for_selector(tid("mail-list"), timeout=90_000)
    s.check("a user has no Administration in the folders pane", up.locator(tid("admin-nav-mailboxes")).count() == 0)

    # ------------------------------------------------------------ 10. view as: read only
    s.start("both", "R3-3", "View as Khalid: his mail, filters work, and nothing can be changed")
    s.page = ap
    ap.goto(UI + "/messages", wait_until="domcontentloaded")
    ap.wait_for_selector(tid("user-menu"), timeout=90_000)
    ap.click(tid("user-menu"))
    ap.select_option(tid("view-as"), "khalid.alotaibi")
    ap.wait_for_selector(tid("viewing-banner"), timeout=60_000)
    ap.wait_for_selector(tid("mail-row"), timeout=60_000)
    settle(ap)
    s.check("Khalid's Inbox", rows(ap) == get(f"{M}/threads?folder=inbox", kck)["total"])
    s.check("no select boxes, stars disabled, no New label, compose disabled",
            ap.locator(tid("row-select")).count() == 0 and ap.locator(tid("row-star")).first.is_disabled()
            and ap.locator(tid("label-create")).count() == 0 and ap.locator(tid("mail-compose")).is_disabled())
    ap.click(tid("mail-filters-toggle"))
    ap.select_option(tid("filter-from"), "sara.aldosari")
    ap.click(tid("filter-apply"))
    ap.wait_for_function("() => /from=sara/.test(location.search)")
    settle(ap)
    s.check("filters work while viewing as", rows(ap) == get(f"{M}/threads?folder=inbox&from=sara.aldosari", kck)["total"])
    ap.click(tid("user-menu"))
    ap.select_option(tid("view-as"), "")
    ap.wait_for_function("() => !document.querySelector('[data-testid=\"viewing-as-chip\"]')", timeout=60_000)
    s.finish()
    s.page = page
    for c in (ctx_k, ctx_s, ctx_o, ctx_r, ctx_a, ctx_u):
        c.close()
