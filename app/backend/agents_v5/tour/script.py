"""Noor's introduction tour: the deterministic script writer (PLAN_R14 session t; R13_FEEDBACK K36, K36a).

The tour is a fixed sequence of steps over the live product. Each step names the screen (route), the element it
highlights (CSS selectors, `[data-tour=<key>]` first, then the existing test ids as fall-backs), the action the tour
takes there, and what Noor says, in English and in Arabic written natively from the same numbers (not a translation).

The words come from rule-based templates; the numbers come from `facts.collect()` at run time, each with its source
stamp. Templates hold no digits at all: every figure in a caption is a fact (claims discipline, K36 (4), N5). A clause
whose fact is absent on this build is dropped and listed under `dropped`, so the tour never states a figure it did not
read. Same data → same script, every run (N4); no model is called.

Story (K36a): CreditProbe is in the intelligence business. It sits above the loan system, core banking, rating,
collections and early-warning systems, reads them all and makes the credit and risk team more intelligent. Existing
systems are described by capability (they record, post, score, flag), never by vendor.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from backend.agents_v5.tour import facts as F
from backend.agents_v5.tour.facts import Fact

VERSION = "tour-r14-1.0.0"

# Speaking pace for the duration estimate (rate 0.92 of the browser's ~2.6 words/s; Arabic words are longer).
WPS = {"en": 2.7, "ar": 2.1}
PAUSE_MS = 700          # after each line, before the next step
MIN_MS = 4500


# ---------------------------------------------------------------- the templates

@dataclass(frozen=True)
class Clause:
    """One sentence (or part) of a line; dropped when any fact in `needs` is absent."""
    en: str
    ar: str
    needs: tuple[str, ...] = ()
    why_dropped: str = ""


@dataclass(frozen=True)
class StepSpec:
    key: str
    title_en: str
    title_ar: str
    route: str
    action: dict[str, Any]
    selectors: tuple[str, ...]
    clauses: tuple[Clause, ...]
    optional: bool = False          # skipped (not shown) when none of its selectors is on the page
    wait_for: tuple[str, ...] = ()  # the page is ready when one of these is present
    module: str = ""


def _t(key: str) -> str:
    return f'[data-tour="{key}"]'


def _id(tid: str) -> str:
    return f'[data-testid="{tid}"]'


def nav(href: str) -> dict[str, Any]:
    """Open a module by clicking its link in the primary navigation (N6: clicks, not URLs)."""
    return {"type": "open_module", "click": [f'nav[aria-label="Primary"] a[href="{href}"]'], "href": href}


DEAL = F.TOUR_DEAL

STEPS: tuple[StepSpec, ...] = (
    StepSpec(
        "intro", "Meet Noor", "تعرّفوا إلى نور", "/", {"type": "home"},
        (_t("tour-logo"), 'header a[aria-label^="CreditProbe"]'),
        (Clause("I'm Noor. Your bank already has a loan system, core banking, ratings, collections and early warning. "
                "Each one records something. None of them tells you what it means. That's my job.",
                "أنا نور. لدى مصرفكم نظام للقروض، ونظام مصرفي أساسي، وأداة للتصنيف، ونظام للتحصيل، وآخر للإنذار "
                "المبكر. كلٌّ منها يسجّل شيئاً، ولا يخبركم أيٌّ منها بما يعنيه. وهذه مهمتي."),),
        module="cockpit"),
    StepSpec(
        "layers", "The intelligence layer", "طبقة الذكاء", "/", {"type": "diagram"},
        (_t("tour-diagram"),),
        (Clause("CreditProbe sits above all of them", "يعمل كريدت بروب فوقها جميعاً"),
         Clause(", reads {domains} data domains every day", "، ويقرأ كل يوم {domains} مجالاً من البيانات",
                ("domains",)),
         Clause(", and turns them into decisions. Intelligence, not another system of record.",
                "، ويحوّلها إلى قرارات. نحن نقدّم الذكاء، لا نظام سجلات آخر."),),
        module="cockpit"),
    StepSpec(
        "brief", "The morning brief", "الموجز الصباحي", "/",
        {"type": "brief", "tab": "brief",
         # Noor reads two lines: the highlight moves to each line as its words come up in the caption
         "sequence": [{"selector": f'{_id("noor-home-brief-lines")} > li:nth-child(1)', "mark_en": "First:", "mark_ar": "أولها:"},
                      {"selector": f'{_id("noor-home-brief-lines")} > li:nth-child(2)', "mark_en": "Then:", "mark_ar": "ثم:"}]},
        (_t("brief-lines"), _id("noor-home-brief-lines"), _id("noor-home-brief")),
        (Clause("Every morning, a brief with the evidence.", "كل صباح، موجز ومعه الدليل."),
         Clause("Today, {brief_headline}", "اليوم {brief_headline_ar}", ("brief_headline",)),
         Clause("First: {brief_line1}.", "أولها: {brief_line1_ar}.", ("brief_line1",)),
         Clause("Then: {brief_line2}.", "ثم: {brief_line2_ar}.", ("brief_line2",)),),
        wait_for=(_id("noor-home-brief"),), module="cockpit"),
    StepSpec(
        "why", "Why, not just what", "لماذا، لا ماذا فقط", "/",
        {"type": "click", "click": [_t("brief-why"), f'{_id("noor-home-brief-lines")} li:first-child {_id("noor-why")}'],
         "close_after": True},
        (_t("brief-why-answer"), _id("noor-panel"), f'{_id("noor-home-brief-lines")} li:first-child'),
        (Clause("Ask why, and I show the cause: the rule, what the bank holds against it, and where the gap comes "
                "from.",
                "اسألوا لماذا، فأعرض السبب: القاعدة، وما يحتفظ به المصرف مقابلها، ومن أين تأتي الفجوة."),
         Clause("Here, {brief_rule}.", "والقاعدة هنا {brief_rule}.", ("brief_rule",)),),
        module="cockpit"),
    StepSpec(
        "ask", "Ask anything", "اسألوا ما تشاؤون", "/", {"type": "ask", "tab": "ask"},
        (_t("ask-box"), _id("home-ask")),
        (Clause("Or just ask: the ECL movement, who moved to Stage two, who to call today. Every answer traces back "
                "to the data.",
                "أو اسألوا مباشرة: حركة الخسائر الائتمانية المتوقعة، ومن انتقل إلى المرحلة الثانية، ومن يجب "
                "الاتصال به اليوم. وكل إجابة تعود إلى مصدر بياناتها."),),
        wait_for=(_id("home-ask"),), module="cockpit"),
    StepSpec(
        "ews", "Early Warning", "الإنذار المبكر", "/early-warning", nav("/early-warning"),
        (_t("ews-list"), _id("ews-askbar"), "main"),
        (Clause("Early Warning finds borrowers going bad quarters before they default",
                "يكتشف الإنذار المبكر المقترضين المتدهورين قبل التعثر بفصول"),
         Clause(": {ews_names} sit in the critical band in {book_period}, with {ews_ead} of exposure",
                "، وفي {book_period} هناك {ews_names} مقترضاً في الفئة الحرجة بتعرض قدره {ews_ead}",
                ("book_period", "ews_names", "ews_ead")),
         Clause(". A rating tool gives a score; I explain what changed.",
                ". أداة التصنيف تعطي درجة، وأنا أشرح ما الذي تغيّر."),),
        wait_for=(_id("ews-askbar"),), module="ews"),
    StepSpec(
        "b360", "Borrower 360", "المقترض 360", "/borrower-360", nav("/borrower-360"),
        (_t("b360-list"), _id("b360-askbar"), "main"),
        (Clause("Borrower 360 shows the whole relationship in one click: group, guarantors, accounts, bureau and "
                "conduct",
                "ويعرض المقترض 360 العلاقة كاملة بنقرة واحدة: المجموعة والكفلاء والحسابات وسجل الائتمان والسلوك"),
         Clause(", across {groups} groups", "، عبر {groups} مجموعة", ("groups",)),
         Clause(".", "."),),
        wait_for=(_id("b360-askbar"),), module="b360"),
    StepSpec(
        "whatif", "What-If", "ماذا لو", "/what-if", nav("/what-if"),
        (_t("whatif-chat"), _id("whatif-landing"), "main"),
        (Clause("What-If is something no bank system does: agents design a scenario, run it on the whole book and "
                "estimate ECL, Stage two and capital without the ECL engine",
                "ماذا لو قدرة لا يملكها أي نظام مصرفي اليوم: يصمّم الوكلاء السيناريو، ويطبّقونه على المحفظة كلها، "
                "ويقدّرون الخسائر المتوقعة والمرحلة الثانية ورأس المال من دون تشغيل محرك الخسائر"),
         Clause(", starting from your book's own ECL, reconciled in all {whatif_periods} quarters",
                "، انطلاقاً من خسائر محفظتكم نفسها، مطابِقةً في الفصول الـ{whatif_periods} كلها",
                ("whatif_periods",)),
         Clause(". Back-tested on {bt_quarters} quarter steps, its estimate came within {bt_mean} of the full engine on "
                "average, {bt_worst} at worst",
                ". وفي الاختبار الرجعي على {bt_quarters} خطوة فصلية جاء تقديره ضمن {bt_mean} من المحرك الكامل في "
                "المتوسط، و{bt_worst} في أسوأ الحالات",
                ("bt_quarters", "bt_mean", "bt_worst"),
                "the What-If back-test relation (whatif_backtest, session m) is not on this build"),
         Clause(".", "."),),
        wait_for=(_id("whatif-landing"),), module="whatif"),
    StepSpec(
        "lenses", "Lenses", "العدسات", "/lenses", nav("/lenses"),
        (_t("lenses-chat"), _id("lenses-landing"), "main"),
        (Clause("Lenses cut the book any way you like", "وتعرض العدسات المحفظة كما تريدون"),
         Clause(", across {lens_dims} dimensions", "، عبر {lens_dims} بُعداً", ("lens_dims",)),
         Clause(", and say in plain words what moved.", "، وتقول بكلمات بسيطة ما الذي تغيّر."),),
        wait_for=(_id("lenses-landing"),), module="lenses"),
    StepSpec(
        "deal_check", "Deal Desk: the proposal check", "مكتب الصفقات: فحص المقترح", "/deal-desk/{check_deal}",
        {"type": "open_deal", "click": ['nav[aria-label="Primary"] a[href="/deal-desk"]'], "deal": "{check_deal}",
         "open": ['a[href="/deal-desk/{check_deal}"]', f'{_id("dealdesk-table")} tr:has-text("{{check_deal}}")'],
         "then": [_t("dd-proposal-check"), _id("dealdesk-step-proposal-check"), _id("dealdesk-step-check")]},
        (_t("dd-proposal-check"), _id("dealdesk-step-proposal-check"), _id("dealdesk-step-check"),
         _id("dealdesk-step-proposal"), _id("dealdesk-stepper")),
        (Clause("Deal Desk is your second credit analyst.", "مكتب الصفقات هو محللكم الائتماني الثاني."),
         Clause("{deals_pending} proposals wait in the pipeline.", "في خط المعالجة {deals_pending} مقترحاً.",
                ("deals_pending",)),
         Clause("I check the relationship manager's paper first: what's missing, untrue or undisclosed.",
                "أفحص ورقة مدير العلاقة أولاً: ما الناقص، وما غير الصحيح، وما لم يُفصح عنه."),
         Clause("In {pq_deal_name}'s proposal I found {pq_defects} defects, {pq_critical} of them critical.",
                "وفي مقترح {pq_deal_name} وجدت {pq_defects} عيباً، منها {pq_critical} حرجة.",
                ("pq_deal_name", "pq_defects", "pq_critical"),
                "the proposal-check relation (dd_proposal_quality, session p) is not on this build"),),
        wait_for=(_id("dealdesk-stepper"),), module="dealdesk"),
    StepSpec(
        "deal_review", "Review", "المراجعة", f"/deal-desk/{DEAL}",
        {"type": "open_deal", "click": ['nav[aria-label="Primary"] a[href="/deal-desk"]'], "deal": DEAL,
         "open": [f'a[href="/deal-desk/{DEAL}"]', f'{_id("dealdesk-table")} tr:has-text("{DEAL}")'],
         "then": [_t("dd-review"), _id("dealdesk-step-review")]},
        (_t("dd-review"), _id("dealdesk-step-review-view"), _id("dealdesk-step-review")),
        (Clause("Then the deal itself", "ثم الصفقة نفسها"),
         Clause(": on {deal_name}, asking {deal_ask}, I raised {deal_findings} findings, {deal_critical} critical",
                ": في صفقة {deal_name} بطلب قدره {deal_ask} رصدت {deal_findings} ملاحظة، منها {deal_critical} حرجة",
                ("deal_name", "deal_ask", "deal_findings", "deal_critical")),
         Clause(", across capacity, conduct, policy and financial quality.",
                "، في القدرة على السداد والسلوك والسياسة وجودة القوائم المالية."),),
        wait_for=(_id("dealdesk-step-review-view"),), module="dealdesk"),
    StepSpec(
        "deal_structure", "Structure and stress", "الهيكلة والضغط", f"/deal-desk/{DEAL}",
        {"type": "click", "click": [_t("dd-structure"), _id("dealdesk-step-structure")]},
        (_t("dd-stress"), _id("dealdesk-stress-button"), _t("dd-structure-set"), _id("dealdesk-step-structure-view"),
         _id("dealdesk-step-structure")),
        (Clause("I find the structure that works, stress it", "أجد الهيكل الذي ينجح، وأختبره تحت الضغط"),
         Clause(" across {deal_scenarios} scenarios", " عبر {deal_scenarios} سيناريو", ("deal_scenarios",)),
         Clause(", stress-proof it and price it.", "، وأحصّنه، وأسعّره."),),
        wait_for=(_id("dealdesk-step-structure-view"),), module="dealdesk"),
    StepSpec(
        "deal_proposal", "The credit proposal", "المقترح الائتماني", f"/deal-desk/{DEAL}",
        {"type": "click", "click": [_t("dd-recommendation"), _id("dealdesk-step-recommendation")]},
        (_t("dd-prepare-proposal"), _t("prepare-proposal"), _id("dealdesk-prepare-proposal"),
         _id("dealdesk-step-recommendation-view"), _id("dealdesk-step-recommendation")),
        (Clause("And I write the credit proposal in your bank's own format, every figure traced.",
                "ثم أكتب المقترح الائتماني بنموذج مصرفكم، وكل رقم فيه يعود إلى مصدره."),),
        wait_for=(_id("dealdesk-step-recommendation-view"),), module="dealdesk"),
    StepSpec(
        "book", "Book and monitoring", "المحفظة والمتابعة", "/deal-desk",
        {"type": "click", "click": ['nav[aria-label="Primary"] a[href="/deal-desk"]'],
         "then": [_t("dd-monitoring"), _id("dealdesk-tab-monitoring"), _id("dealdesk-tab-book")]},
        (_t("dd-monitoring"), _id("monitoring-page"), _id("dealdesk-tab-monitoring-panel"), _id("dealdesk-tab-book-panel"),
         _id("dealdesk-tab-book")),
        (Clause("After approval I keep watching", "وبعد الموافقة أواصل المتابعة"),
         Clause(" {book_borrowers} borrowers and {book_ead} on the book", " لـ{book_borrowers} مقترضاً و{book_ead} في المحفظة",
                ("book_borrowers", "book_ead")),
         Clause(": tiers, covenants, promises, renewals.", ": المستويات والتعهدات والوعود والتجديدات."),
         Clause("{monitoring_proposals} proposed for monitoring today.",
                "وعدد الأسماء المقترحة للمتابعة اليوم: {monitoring_proposals}.", ("monitoring_proposals",),
                "the monitoring proposals relation (dd_monitoring_proposal, session f) is not on this build"),),
        wait_for=(_id("dealdesk-tab-book"),), module="dealdesk"),
    StepSpec(
        "scorecard", "Scorecard validation", "التحقق من بطاقات التقييم", "/scorecard-validation",
        nav("/scorecard-validation"), (_t("scorecard-home"), _id("sv-home"), "main"),
        (Clause("I validate your scorecards", "أتحقق من بطاقات التقييم"),
         Clause(", all {scorecards} of them", "، وعددها {scorecards}", ("scorecards",)),
         Clause(".", "."),),
        module="scorecard"),
    StepSpec(
        "brf", "Regulatory returns", "التقارير الرقابية", "/brf", nav("/brf"), (_t("brf-home"), _id("brf-studio"), "main"),
        (Clause("I build your regulatory returns from the same data", "وأُعدّ التقارير الرقابية من البيانات نفسها"),
         Clause(", {brf_returns} of them today", "، و{brf_returns} منها جاهزة اليوم", ("brf_returns",)),
         Clause(".", "."),),
        module="brf"),
    StepSpec(
        "policy", "Policy documents", "وثائق السياسات", "/policy-docs", nav("/policy-docs"),
        (_t("policy-home"), _id("policy-library"), "main"),
        (Clause("I know your credit policy clause by clause", "وأعرف سياستكم الائتمانية بنداً بنداً"),
         Clause(", all {policy_clauses} clauses", "، بنودها الـ{policy_clauses} كلها", ("policy_clauses",)),
         Clause(".", "."),),
        module="policy"),
    StepSpec(
        "playbook", "Playbook", "دليل العمل", "/playbook", nav("/playbook"), (_t("playbook-home"), _id("playbook-home"), "main"),
        (Clause("I know the regulator's rules", "وأعرف قواعد الجهة الرقابية"),
         Clause(", {rule_sections} sections", "، في {rule_sections} قسماً", ("rule_sections",)),
         Clause(", and I follow your playbooks.", "، وأتّبع أدلة عملكم."),),
        module="playbook"),
    StepSpec(
        "governance", "Governance", "الحوكمة", "/deal-desk",
        {"type": "panel", "click": ['nav[aria-label="Primary"] a[href="/deal-desk"]'],
         "then": [_id("gov-tools"), _id("gov-tool-inspection")], "close_after": True},
        (_t("gov-inspection"), _id("gov-drawer-inspection"), _id("gov-tools")),
        (Clause("When the regulator or the auditor asks, I build the evidence pack",
                "وعندما تسأل الجهة الرقابية أو المدقق، أُعدّ ملف الأدلة"),
         Clause(" from {decisions} decisions on file", " من {decisions} قراراً في السجل", ("decisions",)),
         Clause(".", "."),),
        optional=True, wait_for=(_id("gov-drawer-inspection"),), module="governance"),
    StepSpec(
        "data", "Data Domains", "مجالات البيانات", "/data-builder", nav("/data-builder"), (_t("data-home"), _id("db-overview"), _id("db-workspace"), "main"),
        (Clause("Every number I give traces to your data, down to the row",
                "وكل رقم أقدّمه يعود إلى بياناتكم، حتى السطر"),
         Clause(": {domains} domains, {relations} tables", ": {domains} مجالاً و{relations} جدولاً",
                ("domains", "relations")),
         Clause(".", "."),),
        module="data"),
    StepSpec(
        "workspace", "Workspace", "مساحة العمل", "/workspace", nav("/workspace"), (_t("workspace-home"), _id("ws-home"), "main"),
        (Clause("Your projects, analyses and messages live in Workspace, next to the evidence.",
                "ومشاريعكم وتحليلاتكم ورسائلكم في مساحة العمل، بجانب الأدلة."),),
        module="workspace"),
    StepSpec(
        "close", "Over to you", "الكلمة لكم", "/", {"type": "home", "tab": "brief"},
        (_t("brief-lines"), _id("noor-home-brief"), _id("home-tabs")),
        (Clause("Your team stays in charge. I make it sharper, every morning. Ask me anything.",
                "يبقى فريقكم صاحب القرار، وأنا أجعله أذكى كل صباح. اسألوني ما تشاؤون."),),
        module="cockpit"),
)


# ---------------------------------------------------------------- the brief's own lines, said in both languages

_AR_LABEL = {
    "Exposures": "تعرضاً", "Names": "اسماً", "Deals": "صفقة", "Letters": "خطاباً", "Questions": "سؤالاً",
}


def _num(item: dict[str, Any], label: str) -> dict[str, Any] | None:
    return next((n for n in item.get("numbers") or [] if n.get("label") == label and n.get("value") is not None), None)


def _say_ar(n: dict[str, Any]) -> str:
    if n.get("unit") == "SAR mn":
        return F.sar_ar(float(n["value"]))
    if n.get("unit") == "%":
        return F.pct(float(n["value"]))
    return F.count(n["value"]) if float(n["value"]).is_integer() else str(n["display"])


_AR_SHORT = {
    "breach": "مخالفة تنظيمية ثانية في الفحوص الرقابية", "ecl_anomaly": "مشكلات في بيانات الخسائر الائتمانية المتوقعة",
    "deal_queue": "صفقات بانتظار المراجعة الائتمانية", "conditions": "شروط موافقة مستحقة",
    "watch_due": "محفزات للمخاطر المقبولة تستحق قريباً", "migrations": "تعرضات انتقلت إلى مرحلة أسوأ",
    "sector_appetite": "حصة قطاع مقابل حد الرغبة في المخاطر", "letters": "خطابات مفتوحة من المدقق والجهات الرقابية",
}


def line_ar(item: dict[str, Any], short: bool = False) -> str:
    """One brief line in Arabic, written from its numbers per kind of line (the English title is not translated).
    `short`: the subject only (the second line of the tour is said short, as in English)."""
    kind = item.get("kind") or ""
    if short:
        return _AR_SHORT.get(kind, "بند آخر يحتاج إلى انتباهكم")
    g = lambda lab: _num(item, lab)  # noqa: E731
    if kind == "breach" and g("Exposures") and g("EAD"):
        s = f"مخالفة تنظيمية على {_say_ar(g('Exposures'))} تعرضاً بقيمة {_say_ar(g('EAD'))}"
        sh = g("Shortfall")
        if sh and float(sh["value"]) > 0.05:
            s += f"، وعجز في المخصصات قدره {_say_ar(sh)}"
        return s
    if kind == "ecl_anomaly" and g("Issues needing a re-run"):
        return f"{_say_ar(g('Issues needing a re-run'))} مشكلات في البيانات يجب حلّها قبل احتساب الخسائر الائتمانية المتوقعة"
    if kind == "deal_queue" and g("Deals"):
        s = f"{_say_ar(g('Deals'))} صفقة بانتظار المراجعة الائتمانية"
        a = g("Asked") or g("Pipeline asked")
        return s + (f" بقيمة {_say_ar(a)}" if a else "")
    if kind == "conditions" and g("Due in 30 days"):
        return f"{_say_ar(g('Due in 30 days'))} شروط موافقة مفتوحة أو مستحقة قريباً"
    if kind == "watch_due" and g("Triggers due"):
        return f"{_say_ar(g('Triggers due'))} محفزاً للمخاطر المقبولة تستحق قريباً"
    if kind == "migrations" and g("Exposures"):
        return f"{_say_ar(g('Exposures'))} تعرضاً للشركات انتقلت إلى مرحلة أسوأ"
    if kind == "sector_appetite" and g("Share of book") and g("Appetite limit"):
        return (f"قطاع يشكّل {_say_ar(g('Share of book'))} من محفظة الشركات مقابل حد للرغبة في المخاطر قدره "
                f"{_say_ar(g('Appetite limit'))}")
    if kind == "letters" and g("Letters"):
        return f"{_say_ar(g('Letters'))} خطابات مفتوحة من المدقق والجهات الرقابية"
    first = next((n for n in item.get("numbers") or [] if n.get("label") in _AR_LABEL), None)
    if first:
        return f"بند يحتاج إلى انتباهكم يخص {_say_ar(first)} {_AR_LABEL[first['label']]}"
    return "بند يحتاج إلى انتباهكم"


_AR_COUNT = {1: "أمر واحد", 2: "أمران", 3: "ثلاثة أمور", 4: "أربعة أمور", 5: "خمسة أمور"}


def brief_facts(brief: dict[str, Any] | None) -> dict[str, Fact]:
    """The brief's headline and first two lines as facts (each line keeps the brief's own trace)."""
    if not brief or not brief.get("items"):
        return {}
    items = brief["items"]
    out: dict[str, Fact] = {}
    crit = sum(1 for r in items if r.get("severity") == "critical")
    head = str(brief.get("headline") or "").rstrip(".")
    head = head[:1].lower() + head[1:] if head else head
    if head:
        ar = (_AR_COUNT.get(len(items), f"{len(items)} أمور") + " تستحق انتباهكم"
              + ("، منها أمر حرج واحد" if crit == 1 else f"، منها {crit} حرجة" if crit else "") + ".")
        out["brief_headline"] = Fact("brief_headline", len(items), head + ".", ar, "noor", "brief",
                                     "the brief's headline: lines shown and critical lines (backend/agents_v5/brief)",
                                     {"persona": brief.get("persona")}, str(brief.get("date") or ""))
        out["brief_headline_ar"] = out["brief_headline"]
    for i, it in enumerate(items[:2], start=1):
        tr = (it.get("trace") or [{}])[0]
        title = str(it.get("title") or "").rstrip(".")
        if i == 2 and ":" in title:   # the second line is said short: its subject, not every number
            title = title.split(":")[0]
        out[f"brief_line{i}"] = Fact(f"brief_line{i}", it.get("id"), title, line_ar(it, short=(i == 2 and ":" in str(it.get("title") or ""))), str(tr.get("domain") or ""),
                                     str(tr.get("relation") or ""), f"brief line {i}: {it.get('source_label')}",
                                     dict(tr.get("keys") or {}), str(tr.get("period") or it.get("since") or ""))
        out[f"brief_line{i}_ar"] = out[f"brief_line{i}"]
    art = ((items[0].get("entity") or {}).get("article") or "").strip()
    if art:
        tr = (items[0].get("trace") or [{}])[0]
        m = re.match(r"^(.*?)\s*Art\.\s*([\d.]+)$", art)
        art_ar = f"المادة {m.group(2)} من {m.group(1)}" if m and m.group(1) else art
        out["brief_rule"] = Fact("brief_rule", art, art, art_ar,str(tr.get("domain") or ""), str(tr.get("relation") or ""),
                                 "the article the first brief line checks", dict(tr.get("keys") or {}))
    return out


# ---------------------------------------------------------------- writing

_SLOT = re.compile(r"\{(\w+)\}")
NUM = re.compile(r"\d+(?:[.,]\d+)*")


def _fill(tpl: str, facts: dict[str, Fact], lang: str) -> str:
    def sub(m: re.Match[str]) -> str:
        f = facts[m.group(1)]
        return f.ar if lang == "ar" else f.en
    return _SLOT.sub(sub, tpl)


def _join(parts: list[str]) -> str:
    s = ""
    for p in parts:
        if not p:
            continue
        if not s or p[0] in ",.;:،" or p[0] == " ":
            s += p
        else:
            s += " " + p
    s = re.sub(r"\s+([,.;:،])", r"\1", s)
    s = re.sub(r"([,،])\s*\.", ".", s)
    s = re.sub(r"\.\.+", ".", s)
    return re.sub(r"\s{2,}", " ", s).strip()


def numbers_in(text: str) -> list[str]:
    return NUM.findall(text)


# Product names that carry a digit (not figures).
NAMES = ("Borrower 360", "المقترض 360")


def claims_audit(text: str, used: list[Fact]) -> list[str]:
    """Numbers in `text` that no fact used by the step says (must be empty: K36 (4))."""
    for name in NAMES:
        text = text.replace(name, "")
    backed: set[str] = set()
    for f in used:
        for s in (f.en, f.ar):
            backed.update(numbers_in(str(s)))
    return [n for n in numbers_in(text) if n not in backed]


_ORD_EN = {"1": "first", "2": "second", "3": "third", "4": "fourth"}
_ORD_AR = {"1": "الأول", "2": "الثاني", "3": "الثالث", "4": "الرابع"}


def spoken_en(text: str) -> str:
    """The caption as it is said: amounts, quarters and abbreviations in words a voice reads well (same numbers)."""
    t = re.sub(r"−?SAR (\d[\d,.]*)bn", lambda m: f"{m.group(1)} billion riyals", text)
    t = re.sub(r"−?SAR (\d[\d,.]*)m\b", lambda m: f"{m.group(1)} million riyals", t)
    t = re.sub(r"\b(\d{4})Q([1-4])\b", lambda m: f"the {_ORD_EN[m.group(2)]} quarter of {m.group(1)}", t)
    t = re.sub(r"\bEAD\b", "exposure at default", t)
    t = re.sub(r"\bArt\. ", "Article ", t)
    t = re.sub(r"\bECL\b", "E C L", t)
    return t


def spoken_ar(text: str) -> str:
    t = re.sub(r"\b(\d{4})Q([1-4])\b", lambda m: f"الربع {_ORD_AR[m.group(2)]} من {m.group(1)}", text)
    t = re.sub(r"\bArt\. ", "المادة ", t)
    return t


@dataclass
class Step:
    n: int
    key: str
    title: str
    route: str
    action: dict[str, Any]
    selectors: list[str]
    optional: bool
    wait_for: list[str]
    module: str
    caption: str
    voice: str
    caption_en: str
    caption_ar: str
    voice_en: str
    voice_ar: str
    title_en: str
    title_ar: str
    duration_ms: int
    facts: list[str] = field(default_factory=list)
    dropped: list[dict[str, str]] = field(default_factory=list)
    unbacked: list[str] = field(default_factory=list)


def _deal(x: Any, deal: str) -> Any:
    """The deal the proposal-check step opens: session p's checked demo deal when it is on the build, else twin A."""
    if isinstance(x, str):
        return x.replace("{check_deal}", deal)
    if isinstance(x, list):
        return [_deal(v, deal) for v in x]
    if isinstance(x, dict):
        return {k: _deal(v, deal) for k, v in x.items()}
    return x


def _duration(text: str, lang: str) -> int:
    words = len(text.split())
    return max(MIN_MS, int(words / WPS[lang] * 1000) + PAUSE_MS)


def write(facts: dict[str, Fact], lang: str = "en") -> list[Step]:
    lang = "ar" if lang == "ar" else "en"
    out: list[Step] = []
    check = str(facts["pq_deal"].value) if "pq_deal" in facts else DEAL
    for i, spec in enumerate(STEPS, start=1):
        route, action = _deal(spec.route, check), _deal(spec.action, check)
        en_parts: list[str] = []
        ar_parts: list[str] = []
        used: list[str] = []
        dropped: list[dict[str, str]] = []
        for c in spec.clauses:
            missing = [k for k in c.needs if k not in facts]
            if missing:
                dropped.append({"clause": c.en, "missing": ", ".join(missing),
                                "why": c.why_dropped or "not readable on this build"})
                continue
            en_parts.append(_fill(c.en, facts, "en"))
            ar_parts.append(_fill(c.ar, facts, "ar"))
            used += [k for k in _SLOT.findall(c.en + c.ar) if k not in used]
        en, ar = _join(en_parts), _join(ar_parts)
        fs = [facts[k] for k in used]
        ven, var = spoken_en(en), spoken_ar(ar)
        unbacked = sorted(set(claims_audit(en, fs) + claims_audit(ar, fs) + claims_audit(ven, fs)
                              + claims_audit(var, fs)))
        text = ar if lang == "ar" else en
        said = var if lang == "ar" else ven
        out.append(Step(
            n=i, key=spec.key, title=spec.title_ar if lang == "ar" else spec.title_en, route=route,
            action=action, selectors=list(spec.selectors), optional=spec.optional,
            wait_for=list(spec.wait_for), module=spec.module, caption=text, voice=said,
            caption_en=en, caption_ar=ar, voice_en=ven, voice_ar=var, title_en=spec.title_en, title_ar=spec.title_ar,
            duration_ms=_duration(said, lang), facts=used, dropped=dropped, unbacked=unbacked))
    return out


def script(*, lang: str = "en", persona: str = "cro", brief: dict[str, Any] | None = None,
           facts: dict[str, Fact] | None = None) -> dict[str, Any]:
    """The whole tour, ready to play: steps, the facts each figure came from, and the claims audit."""
    fs = dict(facts if facts is not None else F.collect())
    if brief is None:
        try:
            from backend.agents_v5.brief import service
            brief = service.brief(persona=persona, top=5)
        except Exception:  # noqa: BLE001 - the brief clause is dropped, the tour still plays
            brief = None
    fs.update(brief_facts(brief))
    steps = write(fs, lang)
    total = sum(s.duration_ms for s in steps)
    used = sorted({k for s in steps for k in s.facts})
    return {
        "version": VERSION, "lang": "ar" if lang == "ar" else "en", "dir": "rtl" if lang == "ar" else "ltr",
        "steps": [asdict(s) for s in steps], "n_steps": len(steps), "duration_ms": total,
        "facts": {k: fs[k].public() for k in used},
        "claims": {"unbacked": sorted({n for s in steps for n in s.unbacked}),
                   "dropped": [{"step": s.key, **d} for s in steps for d in s.dropped],
                   "rule": "every figure in a caption is a fact read at run time with its source; templates hold no "
                           "digits; a clause whose fact is absent is dropped"},
        "voice": {"en": ["Evan", "Nathan", "Daniel"], "ar": ["Maged"], "rate": 0.92, "pitch": 0.9, "gender": "male"},
        "story": "CreditProbe is in the intelligence business: it sits above the loan system, core banking, rating, "
                 "collections and early-warning systems and makes credit and risk teams more intelligent.",
    }
