"""The brief's words. Deterministic first (N6): this writer produces the whole brief and is what the tests check.
With a model key in this process's environment (the Mac Keychain via ops/v5.sh) and `polish=True`, the model may
only rephrase the opening sentence; every line, number and order stays the deterministic one, and the polished
sentence is dropped if it loses a figure.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any


MODULE_LABEL = {"cockpit": "the Cockpit", "ews": "Early Warning", "lenses": "Lenses", "dealdesk": "Deal Desk",
                "whatif": "What-If", "regulatory": "regulatory checks", "queries": "auditor and regulator letters",
                "ecl": "the ECL run", "watch": "accepted-risk watch", "agents": "approvals"}

#: Which sources each module brief reads (I13 point 6: the module brief from its agent).
MODULE_SOURCES: dict[str, tuple[str, ...]] = {
    "dealdesk": ("dd_queue", "dd_query", "sector_appetite", "condition_due", "renewal", "tier_high", "approval",
                 "counterparty_exposure"),  # Round G
    "ews": ("ews_triage", "tier_high", "condition_due"),
    "lenses": ("lenses_alert", "cockpit_attention", "sector_appetite"),
    "whatif": ("sector_appetite", "cockpit_attention", "regulatory_breach", "ews_triage"),
    "cockpit": tuple(),  # the whole brief
}


def part_of_day(hour: int) -> str:
    return "Good morning" if hour < 12 else ("Good afternoon" if hour < 17 else "Good evening")


def opening(persona: str, first_name: str, n_shown: int, n_total: int, rows: list[dict[str, Any]], hour: int,
            assistant: str = "Noor") -> str:
    hello = f"{part_of_day(hour)}{', ' + first_name if first_name else ''}."
    if not rows:
        return f"{hello} Nothing needs you right now: every source {assistant} reads is quiet."
    crit = sum(1 for r in rows if r["severity"] == "critical")
    lead = rows[0]
    count = {1: "One thing", 2: "Two things", 3: "Three things", 4: "Four things", 5: "Five things"}.get(n_shown, f"{n_shown} things")
    # R14 n (K9): most data arrives monthly or quarterly, so never "since yesterday"; the data dates sit in the eyebrow.
    s = f"{hello} {count} to pay attention to"
    if crit:
        s += f", {crit} of them critical"
    s += f". First: {lead['title']}."
    if n_total > n_shown:
        s += f" {n_total - n_shown} more below."
    return s


def headline(persona: str, rows: list[dict[str, Any]], n_total: int, module: str = "") -> str:
    """The brief's headline sentence (J3, R14 K9): "Five things to pay attention to, 1 critical." Never "since
    yesterday" (the sources are monthly and quarterly; their dates are in the eyebrow, `data_dates`). Deterministic."""
    if module:
        label = MODULE_LABEL.get(module, module)
        return f"Nothing in {label} needs you today." if not rows else \
            f"{_count_word(len(rows))} to pay attention to in {label}" + _crit(rows) + "."
    if not rows:
        return "Nothing needs you right now: every source is quiet."
    return f"{_count_word(len(rows))} to pay attention to" + _crit(rows) + "."


def headline_ar(rows: list[dict[str, Any]], module: str = "") -> str:
    """The headline in Arabic, written natively (K9, K10)."""
    if not rows:
        return "لا شيء يحتاج إلى انتباهك الآن."
    n = len(rows)
    crit = sum(1 for r in rows if r["severity"] == "critical")
    s = f"{_AR_COUNT.get(n, str(n) + ' أمور')} تستحق انتباهك"
    if crit:
        s += f"، منها {crit} {'حرج' if crit == 1 else 'حرجة'}"
    return s + "."


_MON = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
#: Relations that are live stores (read now), not periodic data: their date is "today".
LIVE_DOMAINS = {"deal_desk": "Deal Desk", "agents": "Approvals", "watch": None}
LIVE_RELATIONS = {"dd_deal", "dd_condition", "dd_raroc_drift", "dd_query", "approvals", "approvals (ews.triage)"}


def period_label(p: str) -> str:
    """2026Q2 stays; 2026-09 -> Sep 2026; an ISO date -> 4 Oct 2026."""
    p = str(p or "")
    if re.fullmatch(r"\d{4}Q[1-4]", p):
        return p
    m = re.fullmatch(r"(\d{4})-(\d{2})", p)
    if m:
        return f"{_MON[int(m.group(2)) - 1]} {m.group(1)}"
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2}).*", p)
    if m:
        return f"{int(m.group(3))} {_MON[int(m.group(2)) - 1]} {m.group(1)}"
    return p


def _period_key(p: str) -> str:
    m = re.fullmatch(r"(\d{4})Q([1-4])", p)
    if m:
        return f"{m.group(1)}-{int(m.group(2)) * 3:02d}"
    return p


def data_dates(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    """The eyebrow's data dates (K9): one entry per family of sources in the brief, e.g. Corporate 2026Q2 · Retail
    Sep 2026 · Deal Desk today · ECL run 2026Q3. Read from each line's trace (relation and period), never invented."""
    fam: dict[str, str] = {}
    order: list[str] = []
    for r in rows:
        for t in r.get("trace") or []:
            if not isinstance(t, dict):
                continue
            dom, rel, per = str(t.get("domain") or ""), str(t.get("relation") or ""), str(t.get("period") or "")
            book = str((t.get("keys") or t.get("key") or {}).get("book") or "")
            if rel in LIVE_RELATIONS or (dom == "deal_desk" and not per):
                label, when = "Deal Desk", "today"
            elif dom == "ecl_runs":
                label, when = "ECL run", per
            elif not per:
                continue
            else:
                label, when = ("Retail" if book == "retail" else "Corporate"), per
            if label not in fam:
                order.append(label)
                fam[label] = when
            elif when != "today" and _period_key(when) > _period_key(fam[label]):
                fam[label] = when
    rank = {"Corporate": 0, "Retail": 1, "Deal Desk": 2, "ECL run": 3}
    return [{"label": k, "date": "today" if fam[k] == "today" else period_label(fam[k]),
             "text": f"{k} {'today' if fam[k] == 'today' else period_label(fam[k])}"}
            for k in sorted(order, key=lambda k: rank.get(k, 9))]


def _count_word(n: int) -> str:
    return {1: "One thing", 2: "Two things", 3: "Three things", 4: "Four things", 5: "Five things"}.get(n, f"{n} things")


def _crit(rows: list[dict[str, Any]]) -> str:
    crit = sum(1 for r in rows if r["severity"] == "critical")
    high = sum(1 for r in rows if r["severity"] == "high")
    if crit:
        return f", {crit} critical" if crit > 1 or len(rows) > 1 else ", critical"
    if high:
        return f", {high} high priority"
    return ""


_AR_COUNT = {1: "أمر واحد", 2: "أمران", 3: "ثلاثة أمور", 4: "أربعة أمور", 5: "خمسة أمور"}
_AR_SCOPE = {"cro": "في البنك", "reviewer": "على مكتب المراجعة اليوم", "rm": "لعملائك اليوم",
             "analyst": "في عملك اليوم"}


def opening_ar(persona: str, first_name: str, n_shown: int, n_total: int, rows: list[dict[str, Any]], hour: int) -> str:
    """The opening in Arabic for the Gulf Arabic voice (I13.1). The lines themselves stay in English (gap)."""
    hello = ("صباح الخير" if hour < 12 else "مساء الخير") + (f" يا {first_name}" if first_name else "") + "."
    if not rows:
        return f"{hello} لا شيء يحتاج إليك الآن."
    crit = sum(1 for r in rows if r["severity"] == "critical")
    s = f"{hello} {_AR_COUNT.get(n_shown, str(n_shown) + ' أمور')} تستحق انتباهك"
    if crit:
        s += f"، {crit} منها حرجة"
    s += "."
    if n_total > n_shown:
        s += f" و{n_total - n_shown} أخرى في القائمة."
    return s


def module_opening(module: str, rows: list[dict[str, Any]], n_total: int) -> str:
    label = MODULE_LABEL.get(module, module)
    if not rows:
        return f"Nothing in {label} needs you today."
    s = f"{_count_word(len(rows))} to pay attention to in {label}. First: {rows[0]['title']}."
    if n_total > len(rows):
        s += f" {n_total - len(rows)} more below."
    return s


def polish(sentence: str, *, enabled: bool) -> tuple[str, str]:
    """(sentence, how). Model polish only with a key in this process's environment (the shared convo provider reads
    CONVO_ / COCKPIT_ / WHATIF_ANTHROPIC_API_KEY, or ANTHROPIC_API_KEY passed through) and only if every figure
    survives; otherwise the deterministic sentence stands."""
    if not enabled:
        return sentence, "deterministic"
    try:
        from backend.convo import provider as prov
        p = prov.default()
    except Exception:  # noqa: BLE001
        p = None
    if p is None:
        return sentence, "deterministic"
    try:
        reply = p.step("noor.brief.polish",
                       "Rephrase this morning-brief sentence for a senior banker. Keep every number, name and date "
                       "exactly as written. One or two sentences. No tool or system names.",
                       [{"role": "user", "content": sentence}], [])
        text = reply.text().strip()
    except Exception:  # noqa: BLE001
        return sentence, "deterministic"
    figures = re.findall(r"\d[\d,.]*", sentence)
    if text and all(f in text for f in figures):
        return text, "model polish"
    return sentence, "deterministic"


def when(today: date) -> str:
    return today.strftime("%A %d %B %Y").replace(" 0", " ")
