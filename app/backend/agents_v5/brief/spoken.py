"""Noor's spoken scripts (R14 n, K10). Deterministic writers (N4): the voice explains the issue, it does not read the
screen.

    issue_script(item)   40–70 seconds per brief line: what is breached, bank vs requirement, the 2–3 reasons with
                         their shares, the impact and the one action. English and Arabic; the Arabic is written from
                         the same numbers in Arabic sentence order, not translated from the English.
    brief_script(brief)  the headline, then one sentence per line.
    answer_summary(kind, answer)   what the speaker on an answer reads (its spoken summary, never the tables).

Every figure comes from the line itself or from the rows of the relation behind it (`regulatory.crm_breach` for the
regulatory lines), so the script names the same numbers as the screen. Seconds are estimated at the calm voice rate
(0.92 × ~140 words a minute ≈ 129 words a minute in English, ≈ 105 in Arabic).
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from backend.agents_v5.brief import readers as R

WPM_EN = 129.0
WPM_AR = 105.0


# ------------------------------------------------------------------ number words

def sar(v: float | None) -> str:
    """SAR millions as a voice reads them: '878.5 million riyals', '1.73 billion riyals'."""
    if v is None:
        return "an unknown amount"
    a = abs(float(v))
    if a >= 1000:
        return f"{a / 1000:,.2f} billion riyals"
    if a >= 10:
        return f"{a:,.1f} million riyals"
    return f"{a:,.2f} million riyals"


def sar_ar(v: float | None) -> str:
    if v is None:
        return "مبلغ غير معروف"
    a = abs(float(v))
    if a >= 1000:
        return f"{a / 1000:,.2f} مليار ريال"
    if a >= 10:
        return f"{a:,.1f} مليون ريال"
    return f"{a:,.2f} مليون ريال"


def pct(v: float | None, nd: int = 0) -> str:
    return "an unknown share" if v is None else f"{v:.{nd}f} percent"


def pct_ar(v: float | None, nd: int = 0) -> str:
    return "نسبة غير معروفة" if v is None else f"{v:.{nd}f} بالمئة"


def seconds(text: str, lang: str = "en") -> int:
    words = len(text.split())
    return int(round(words / (WPM_AR if lang.startswith("ar") else WPM_EN) * 60))


def speakable(text: str) -> str:
    """Screen text made sayable: SAR 1.73bn -> 1.73 billion riyals, 0.5pp -> 0.5 percentage points."""
    t = re.sub(r"−", "minus ", str(text or ""))
    t = re.sub(r"SAR ([\d,.]+)bn", r"\1 billion riyals", t)
    t = re.sub(r"SAR ([\d,.]+)m\b", r"\1 million riyals", t)
    t = re.sub(r"(\d)pp\b", r"\1 percentage points", t)
    t = re.sub(r"(\d)%", r"\1 percent", t)
    t = re.sub(r"(\d)x\b", r"\1 times", t)
    return re.sub(r"\s+", " ", t).strip()


def _f(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _num(item: dict[str, Any], label: str) -> float | None:
    for n in item.get("numbers") or []:
        if str(n.get("label", "")).lower() == label.lower():
            try:
                return float(n.get("value"))
            except (TypeError, ValueError):
                return None
    return None


def _period(item: dict[str, Any]) -> str:
    s = str(item.get("since") or "")
    if re.fullmatch(r"\d{4}Q[1-4]", s):
        return s
    for t in item.get("trace") or []:
        p = str((t or {}).get("period") or "")
        if p:
            return p
    return s[:10]


def _period_ar(p: str) -> str:
    m = re.fullmatch(r"(\d{4})Q([1-4])", p or "")
    return f"الربع {['الأول', 'الثاني', 'الثالث', 'الرابع'][int(m.group(2)) - 1]} من {m.group(1)}" if m else (p or "")


# ------------------------------------------------------------------ the regulatory lines: rows behind the check

_MONTHS = re.compile(r"(\d+) months in Stage 3")
_SECURED = re.compile(r"25% of the secured \(([\d.]+)\)")
_UNSECURED = re.compile(r"unsecured portion \(([\d.]+)\)")

VINTAGES = (("under one year", "أقل من سنة", 0, 12), ("one to two years", "من سنة إلى سنتين", 12, 24),
            ("two to four years", "من سنتين إلى أربع سنوات", 24, 48), ("four years or more", "أربع سنوات أو أكثر", 48, 10_000))


def breach_facts(check_id: str) -> dict[str, Any] | None:
    """Bank vs requirement and a decomposition for one regulatory check, from `regulatory.crm_breach` rows."""
    r = R.read("regulatory", "crm_breach", where="check_id = ? AND book = 'corporate'", args=[check_id])
    if r.status != "ok" or not r.rows:
        return None
    rows = r.rows
    ead = sum(_f(x.get("ead_sar_mn")) for x in rows)
    ecl = sum(_f(x.get("ecl_sar_mn")) for x in rows)
    sf = sum(_f(x.get("shortfall_sar_mn")) for x in rows)
    unit = str(rows[0].get("unit") or "")
    out: dict[str, Any] = {"check_id": check_id, "n": len(rows), "ead": ead, "ecl": ecl, "shortfall": sf, "unit": unit,
                           "title": rows[0].get("title"), "article": rows[0].get("article"),
                           "period": max(str(x.get("period") or "") for x in rows),
                           "source": {"domain": "regulatory", "relation": "crm_breach", "key": {"check_id": check_id}}}
    if unit == "SAR million":  # provision floors: measured = ECL held, required = floor amount
        req = sum(_f(x.get("required")) for x in rows)
        out["bank_rate"] = 100 * ecl / ead if ead else None
        out["floor_rate"] = 100 * req / ead if ead else None
        out["required"] = req
        by: dict[str, dict[str, float]] = defaultdict(lambda: {"n": 0, "sf": 0.0, "ead": 0.0})
        unsec_sf = old_sf = 0.0
        old_n = 0
        for x in rows:
            d = str(x.get("detail") or "")
            m = _MONTHS.search(d)
            months = int(m.group(1)) if m else None
            s = _f(x.get("shortfall_sar_mn"))
            if months is not None:
                for en, ar, lo, hi in VINTAGES:
                    if lo <= months < hi:
                        by[en]["n"] += 1
                        by[en]["sf"] += s
                        by[en]["ead"] += _f(x.get("ead_sar_mn"))
                if months >= 60:
                    old_sf += s
                    old_n += 1
            sec = _SECURED.search(d)
            if sec is not None and _f(sec.group(1)) == 0.0:
                unsec_sf += s
        out["vintages"] = [{"label": en, "label_ar": ar, "n": int(by[en]["n"]), "shortfall": by[en]["sf"],
                            "share": 100 * by[en]["sf"] / sf if sf else 0.0} for en, ar, _, _ in VINTAGES if by[en]["n"]]
        out["unsecured_share"] = 100 * unsec_sf / sf if sf else None
        out["over_five_years"] = {"n": old_n, "shortfall": old_sf, "share": 100 * old_sf / sf if sf else 0.0}
    elif unit == "stage":  # stage should be `required`; the bank holds `measured`
        by_stage: dict[int, dict[str, float]] = defaultdict(lambda: {"n": 0, "ead": 0.0, "ecl": 0.0})
        for x in rows:
            st = int(_f(x.get("measured")))
            by_stage[st]["n"] += 1
            by_stage[st]["ead"] += _f(x.get("ead_sar_mn"))
            by_stage[st]["ecl"] += _f(x.get("ecl_sar_mn"))
        out["required_stage"] = int(_f(rows[0].get("required")))
        out["stages"] = [{"stage": k, "n": int(v["n"]), "ead": v["ead"], "ecl": v["ecl"],
                          "share": 100 * v["ead"] / ead if ead else 0.0} for k, v in sorted(by_stage.items())]
        out["bank_rate"] = 100 * ecl / ead if ead else None
    else:
        meas = [_f(x.get("measured")) for x in rows]
        req = [_f(x.get("required")) for x in rows]
        out["measured_avg"] = sum(meas) / len(meas)
        out["required_avg"] = sum(req) / len(req)
    return out


# ------------------------------------------------------------------ reasons behind the other lines (read from the rows)

_REASON_AR = {"SICR-DOWNGRADE": "خفض التصنيف منذ آخر مراجعة", "UTP-DPD90": "تأخر السداد أكثر من 90 يوماً",
              "SICR-DPD30": "تأخر السداد أكثر من 30 يوماً", "SICR-COVENANT": "مخالفة تعهد مالي",
              "SICR-SECTOR": "ضغط اقتصادي على القطاع", "UTP-RESTRUCTURE": "إعادة هيكلة متكررة",
              "SICR-DEFER3": "ثلاثة تأجيلات أو أكثر خلال 24 شهراً", "SICR-LATEFIN": "تأخر القوائم المالية أو حجبها",
              "UTP-COVENANT": "مخالفة تعهد جوهري", "SICR-QUALAUDIT": "تقرير متحفظ من المدقق الخارجي",
              "UTP-OTHERBANK": "تصنيفه متعثراً لدى بنك آخر", "UTP-CROSSDEFAULT": "تعثر عضو آخر في المجموعة"}
_ANOMALY_AR = {"PD changed with no rating change": "تغير احتمال التعثر دون تغير التصنيف",
               "LGD changed with no collateral change": "تغير الخسارة عند التعثر دون تغير الضمانات",
               "EAD greater than limit": "قيمة التعرض أعلى من الحد", "Stage inconsistent with DPD": "مرحلة لا تتسق مع أيام التأخر",
               "Missing collateral value": "قيمة ضمان مفقودة", "Stage 3 with zero ECL": "مرحلة ثالثة بخسارة متوقعة صفرية"}


def line_reasons(item: dict[str, Any]) -> dict[str, Any] | None:
    """The 2–3 reasons with their shares behind a non-regulatory line, read from the rows of its relation:
    stage migrations by SICR / unlikely-to-pay reason (an exposure can carry several), ECL data issues by kind,
    accepted-risk triggers by metric. None when the line has no such rows."""
    import json as _json
    from collections import Counter
    kind = str(item.get("kind") or "")
    if kind == "migrations":
        period = str((item.get("entity") or {}).get("id") or item.get("since") or "")
        r = R.read("classification", "cls_exposure", columns="sicr_reasons, utp_reasons",
                   where="book = 'corporate' AND stage > previous_stage AND period = ?", args=[period])
        if r.status != "ok" or not r.rows:
            return None
        c: Counter = Counter()
        text: dict[str, str] = {}
        for x in r.rows:
            codes = set()
            for f in ("sicr_reasons", "utp_reasons"):
                try:
                    for it in _json.loads(x.get(f) or "[]"):
                        codes.add(it["code"])
                        text[it["code"]] = it["text"]
                except (ValueError, TypeError, KeyError):
                    continue
            c.update(codes)
        n = len(r.rows)
        top = [{"label": text[k], "label_ar": _REASON_AR.get(k, text[k]), "n": v, "share": 100 * v / n}
               for k, v in c.most_common(3)]
        return {"n": n, "reasons": top, "overlap": True, "noun": "exposures", "noun_ar": "تعرضاً",
                "source": {"domain": "classification", "relation": "cls_exposure", "period": period}}
    if kind == "ecl_anomaly":
        run = str((item.get("entity") or {}).get("id") or item.get("since") or "")
        r = R.read("ecl_runs", "ecl_anomaly", columns="kind, count(*) AS n", where="run_id = ?", args=[run], group="1",
                   order="n DESC")
        if r.status != "ok" or not r.rows:
            r = R.read("ecl_runs", "ecl_anomaly", columns="kind, count(*) AS n", group="1", order="n DESC")
        if r.status != "ok" or not r.rows:
            return None
        n = sum(int(x["n"]) for x in r.rows)
        top = [{"label": str(x["kind"]), "label_ar": _ANOMALY_AR.get(str(x["kind"]), str(x["kind"])),
                "n": int(x["n"]), "share": 100 * int(x["n"]) / n} for x in r.rows[:3]]
        return {"n": n, "reasons": top, "overlap": False, "noun": "issues", "noun_ar": "مسألة",
                "source": {"domain": "ecl_runs", "relation": "ecl_anomaly"}}
    return None


def _lc(label: str) -> str:
    """Lower-case the first letter of a label unless it starts an abbreviation (PD, LGD, EAD, FY2026)."""
    return label if label[1:2].isupper() or label[1:2].isdigit() else label[:1].lower() + label[1:]


def _reasons_sentence(rs: dict[str, Any]) -> tuple[str, str]:
    parts = [f"{x['n']:,} ({pct(x['share'])}) {('carries' if x['n'] == 1 else 'carry') if rs['overlap'] else ('is' if x['n'] == 1 else 'are')} {_lc(x['label'])}" for x in rs["reasons"]]
    en = f"Why: of the {rs['n']:,} {rs['noun']}, " + ", ".join(parts[:-1]) + (" and " if len(parts) > 1 else "") + parts[-1] + "."
    if rs["overlap"]:
        en += " One exposure can carry several reasons."
    ar = "الأسباب: " + "، و".join(f"{pct_ar(x['share'])} {x['label_ar']}" for x in rs["reasons"]) + \
         f"، من أصل {rs['n']:,} {rs['noun_ar']}."
    return en, ar


# ------------------------------------------------------------------ per issue

def issue_script(item: dict[str, Any], why: dict[str, Any] | None = None, options: dict[str, Any] | None = None) -> dict[str, Any]:
    """{en, ar, seconds_en, seconds_ar, words_en, kind, numbers}. `why` and `options` are the line's answers when the
    caller has them (they are computed here otherwise)."""
    ent = item.get("entity") or {}
    facts = None
    if item.get("kind") == "breach" and ent.get("kind") == "check":
        facts = breach_facts(str(ent.get("id") or ""))
    if facts and facts["unit"] == "SAR million":
        en, ar = _floor_script(item, facts)
    elif facts and facts["unit"] == "stage":
        en, ar = _stage_script(item, facts)
    else:
        if why is None or options is None:
            from backend.agents_v5.brief import answers
            why = why if why is not None else _safe(answers.why, item)
            options = options if options is not None else _safe(answers.options, item)
        en, ar = _generic_script(item, why or {}, options or {}, facts)
    return {"item_id": item.get("id"), "en": en, "ar": ar, "seconds_en": seconds(en), "seconds_ar": seconds(ar, "ar"),
            "words_en": len(en.split()), "kind": "regulatory" if facts else "generic",
            "plain_words": plain_words(item, facts, en, options),
            "facts": _public(facts) if facts else None, "voice_rate": 0.92}


def _safe(fn, item):
    try:
        return fn(item)
    except Exception:  # noqa: BLE001 - the script stands on the line alone
        return {}


def _public(f: dict[str, Any]) -> dict[str, Any]:
    keep = ("check_id", "n", "ead", "ecl", "shortfall", "bank_rate", "floor_rate", "required", "vintages",
            "unsecured_share", "over_five_years", "stages", "required_stage", "period", "source", "article")
    return {k: f[k] for k in keep if k in f}


def _floor_script(item: dict[str, Any], f: dict[str, Any]) -> tuple[str, str]:
    n, ead, sf = f["n"], f["ead"], f["shortfall"]
    bank, floor = f.get("bank_rate"), f.get("floor_rate")
    vint = sorted(f.get("vintages") or [], key=lambda v: -v["share"])[:3]
    old = f.get("over_five_years") or {}
    p = f["period"]
    reasons = "; ".join(f"{pct(v['share'])} of it sits in the {v['n']} exposures {v['label']} in Stage 3" for v in vint)
    en = (f"{f['title']}. On {n} Stage 3 exposures with {sar(ead)} of exposure at default, the bank holds a loss "
          f"rate of {pct(bank, 1)}: its provision divided by the exposure. The regulatory minimum for the same "
          f"exposures is {pct(floor, 1)} under {f['article']}, which steps up after four years in Stage 3 to all of the "
          f"unsecured part. The gap is a provision shortfall of {sar(sf)}. Why: {reasons}. ")
    if f.get("unsecured_share") is not None:
        en += f"{pct(f['unsecured_share'])} is on exposures with no recognised security. "
    if old.get("n"):
        en += (f"And {old['n']} exposures, {pct(old['share'])} of the shortfall, have been in Stage 3 five years "
               f"or more without being written off. ")
    en += (f"Impact: {sar(sf)} of provision through profit and loss in {p}. "
           f"Action: top up by vintage, oldest first, and send the five-year cases to write-off review.")
    vint_ar = "، و".join(f"{pct_ar(v['share'])} في تعرضات أمضت {v['label_ar']} في المرحلة الثالثة وعددها {v['n']}"
                         for v in vint)
    ar = (f"المخصص على تعرضات المرحلة الثالثة أقل من الحد الأدنى التنظيمي. لدى البنك {n} تعرضاً في المرحلة الثالثة "
          f"بقيمة {sar_ar(ead)}، ويحتفظ عليها بمعدل خسارة قدره {pct_ar(bank, 1)} من قيمة التعرض، بينما يشترط "
          f"المنظم حداً أدنى قدره {pct_ar(floor, 1)} وفق {f['article']}. الفرق نقص في المخصصات قدره {sar_ar(sf)}. "
          f"مصدر هذا النقص: {vint_ar}. ")
    if f.get("unsecured_share") is not None:
        ar += f"و{pct_ar(f['unsecured_share'])} من النقص على تعرضات بلا ضمانات معترف بها. "
    if old.get("n"):
        ar += f"وهناك {old['n']} تعرضاً بقيت في المرحلة الثالثة خمس سنوات أو أكثر ولم تُشطب بعد. "
    ar += (f"الأثر: سد الفجوة يكلف {sar_ar(sf)} من المخصصات على الأرباح في {_period_ar(p)}. "
           f"المطلوب: رفع المخصصات حسب مدة البقاء في المرحلة الثالثة بدءاً بما تجاوز أربع سنوات، "
           f"وإحالة حالات الخمس سنوات إلى مراجعة الشطب.")
    return en, ar


def _stage_script(item: dict[str, Any], f: dict[str, Any]) -> tuple[str, str]:
    n, ead, ecl = f["n"], f["ead"], f["ecl"]
    req = f.get("required_stage", 3)
    stages = sorted(f.get("stages") or [], key=lambda s: -s["share"])[:3]
    reasons = "; ".join(f"{s['n']} are held in Stage {s['stage']}, {pct(s['share'])} of the exposure" for s in stages)
    en = (f"{f['title']}. {n} corporate exposures with {sar(ead)} of exposure at default belong to borrowers who are "
          f"already in default on another material facility. Under {f['article']} every facility of a defaulted "
          f"wholesale borrower moves to Stage {req}. The bank still holds them lower: {reasons}. "
          f"Today they carry {sar(ecl)} of expected credit loss, {pct(f.get('bank_rate'), 2)} of the exposure, "
          f"far below what a defaulted exposure carries. The impact: moving them to Stage {req} raises the "
          f"provision and the Stage 3 ratio in {f['period']}; the size depends on each facility's loss given "
          f"default and its security. What to do: apply cross-default in the staging run this quarter, starting with "
          f"the largest names, and ask the relationship managers to confirm the defaulted facility for each borrower.")
    reasons_ar = "، و".join(f"{s['n']} تعرضاً في المرحلة {s['stage']} بنسبة {pct_ar(s['share'])} من القيمة" for s in stages)
    ar = (f"لم يُطبَّق مبدأ التعثر المتبادل على محفظة الشركات. هناك {n} تعرضاً بقيمة {sar_ar(ead)} لعملاء متعثرين "
          f"أصلاً في تسهيل جوهري آخر، والقاعدة في {f['article']} تقضي بنقل جميع تسهيلات المقترض المتعثر إلى "
          f"المرحلة {req}. لكن البنك يحتفظ بها في مراحل أدنى: {reasons_ar}. وتحمل اليوم خسارة ائتمانية متوقعة قدرها "
          f"{sar_ar(ecl)} فقط، أي {pct_ar(f.get('bank_rate'), 2)} من القيمة. الأثر: نقلها إلى المرحلة {req} يرفع "
          f"المخصصات ونسبة المرحلة الثالثة في {_period_ar(f['period'])}. المطلوب: تطبيق التعثر المتبادل في احتساب "
          f"المراحل هذا الربع بدءاً بأكبر العملاء، والتأكد من التسهيل المتعثر لكل مقترض مع مديري العلاقات.")
    return en, ar


def _generic_script(item: dict[str, Any], why: dict[str, Any], options: dict[str, Any],
                    facts: dict[str, Any] | None) -> tuple[str, str]:
    title = speakable(item.get("title") or "")
    en = f"{title}. "
    ar_parts = [f"{_ar_title(item)}."]
    if _AR_WHY.get(str(item.get("kind") or "")):
        ar_parts.append(_AR_WHY[str(item.get("kind"))])
    reasons = None
    try:
        reasons = line_reasons(item)
    except Exception:  # noqa: BLE001 - the script stands on the line alone
        reasons = None
    if reasons and reasons.get("reasons"):
        r_en, r_ar = _reasons_sentence(reasons)
        en += r_en + " "
        ar_parts.append(r_ar)
    if facts and facts.get("measured_avg") is not None:
        en += (f"Across the {facts['n']} cases the bank's value averages {facts['measured_avg']:,.1f} {facts['unit']} "
               f"against a required {facts['required_avg']:,.1f}. ")
        ar_parts.append(f"متوسط قيمة البنك {facts['measured_avg']:,.1f} مقابل {facts['required_avg']:,.1f} مطلوبة "
                        f"في {facts['n']} حالة.")
    ans = speakable(str(why.get("answer") or ""))
    if ans and (ans.startswith(title[:40].rstrip(".")) or title.startswith(ans[:40].rstrip("."))):
        # The answer restates the line with more detail: say it once, the fuller way.
        fuller = (ans if len(ans) > len(title) else title).rstrip(".") + ". "
        en = en.replace(f"{title}. ", fuller, 1)
        ans = ""
    if ans:
        en += "Why it matters: " + ans[0].lower() + ans[1:].rstrip(".") + ". " if not ans[:2].isupper() else ans.rstrip(".") + ". "
    steps = [s for s in (why.get("steps") or []) if s.get("count") is not None][:3]
    how_found = ""
    if steps:
        how_found = "How it was found: " + "; ".join(
            f"{s['label'][0].lower()}{s['label'][1:]}, {int(s['count']):,}{(' (' + s['note'] + ')') if s.get('note') else ''}"
            for s in steps) + ". "
        en += how_found
    nums = [n for n in item.get("numbers") or [] if n.get("value") is not None][:3]
    if nums:
        en += "The figures: " + ", ".join(f"{str(n['label']).lower()} {speakable(n.get('display') or '')}" for n in nums) + ". "
    rec = next((o for o in options.get("options") or [] if o.get("recommended")), None)
    if rec:
        eff = speakable(str(rec.get("effect") or ""))
        how = speakable(str(rec.get("how") or ""))
        en += f"What to do: {speakable(rec['title']).rstrip('.')}" + (f". {how.rstrip('.')}. " if how else ". ")
        if eff and not eff.startswith(title[:40].rstrip(".")) and not eff.startswith("No change"):
            en += f"The effect: {eff.rstrip('.')}. "
    else:
        en += "What to do: open the line and assign an owner with a due date. "
    when = _period(item)
    src_label = str(item.get("source_label") or "the source")
    en += f"This comes from {src_label}" + (f", data as of {when}." if when else ".")
    # 40–70 seconds: drop the method, then the figures repeated from the line, until it fits.
    for cut in (how_found, "The figures: "):
        if seconds(en) <= 70 or not cut:
            continue
        if cut == how_found:
            en = en.replace(how_found, "")
        else:
            en = re.sub(r"The figures: [^.]*(\.\d[^.]*)*\. ", "", en)
    if nums:
        ar_parts.append("الأرقام: " + "، ".join(f"{_ar_label(n['label'])} {_ar_display(n)}" for n in nums) + ".")
    if rec:
        ar_parts.append("المطلوب: " + _AR_ACTION.get(str(rec.get("key") or ""), "اعتماد الخيار الموصى به في قائمة الإجراءات") + ".")
    else:
        ar_parts.append("المطلوب: فتح البند وتعيين مسؤول بتاريخ استحقاق.")
    if when:
        ar_parts.append(f"المصدر: {_AR_SOURCE.get(src_label, src_label)}، بيانات {_period_ar(when) if 'Q' in when else when}.")
    return re.sub(r"\s+", " ", en).strip(), " ".join(ar_parts)


_AR_ACTION = {"act": "التصرف الآن وتكليف الجهة المعنية بالحل هذا الأسبوع",
              "assign": "تكليف مسؤول بموعد استحقاق خلال أربعة عشر يوماً",
              "monitor": "المتابعة في الموجز حتى المراجعة القادمة"}

_AR_SOURCE = {"ECL run data checks": "فحوص بيانات احتساب الخسائر المتوقعة", "Regulatory checks": "الفحوص التنظيمية",
              "Deal Desk": "مكتب الصفقات", "Risk appetite": "شهية المخاطر", "Early Warning": "الإنذار المبكر",
              "Accepted-risk watch": "متابعة المخاطر المقبولة", "Book: renewals and repricing": "المحفظة: التجديد وإعادة التسعير",
              "Deal Desk committee calendar": "جدول لجان مكتب الصفقات", "Auditor and regulator letters": "خطابات المدقق والجهة الرقابية",
              "Conditions and covenants": "الشروط والتعهدات", "Lenses": "العدسات", "Approvals": "الموافقات"}

_AR_LABEL = {"exposures": "عدد التعرضات", "ead": "قيمة التعرض", "shortfall": "النقص", "share of book": "الحصة من المحفظة",
             "limit": "الحد", "appetite limit": "حد شهية المخاطر", "headroom": "المساحة المتبقية",
             "warned exposure": "التعرض تحت الإنذار", "warned, a year ago": "التعرض تحت الإنذار قبل عام",
             "facilities read": "التسهيلات المقروءة", "facilities": "التسهيلات", "names": "العملاء",
             "into stage 3": "إلى المرحلة الثالثة", "issues needing a re-run": "مسائل تحتاج إعادة احتساب",
             "deals": "عدد الصفقات", "asked": "المبلغ المطلوب", "pipeline asked": "المطلوب في خط الصفقات",
             "limits asked": "الحدود المطلوبة", "due in 30 days": "مستحقة خلال ثلاثين يوماً", "overdue": "متأخرة",
             "off track": "خارج المسار", "triggers due": "محفزات مستحقة", "oldest, days": "أقدمها بالأيام",
             "with open queries": "باستفسارات مفتوحة", "average gap to hurdle": "متوسط الفجوة عن العائد المطلوب",
             "letters": "الخطابات", "questions": "الأسئلة"}

#: Sector names as an Arabic reader says them (the brief's sectors are the book's own list).
_AR_SECTOR = {"Construction": "المقاولات", "Real Estate": "العقار", "Wholesale Trade": "تجارة الجملة",
              "Retail Trade": "تجارة التجزئة", "Manufacturing": "الصناعة", "Hospitality": "الضيافة",
              "Transport": "النقل", "Transport & Logistics": "النقل والخدمات اللوجستية", "Energy": "الطاقة",
              "Oil & Gas": "النفط والغاز", "Healthcare": "الرعاية الصحية", "Education": "التعليم",
              "Agriculture": "الزراعة", "Utilities": "المرافق", "Telecom": "الاتصالات", "Mining": "التعدين",
              "Financial Services": "الخدمات المالية", "Services": "الخدمات", "Government": "الجهات الحكومية"}


def _ar_label(label: str) -> str:
    return _AR_LABEL.get(str(label).lower(), str(label))


def _ar_display(n: dict[str, Any]) -> str:
    v = n.get("value")
    if n.get("unit") == "SAR mn":
        return sar_ar(_f(v))
    if n.get("unit") == "%":
        return pct_ar(_f(v), 1)
    try:
        return f"{int(float(v)):,}"
    except (TypeError, ValueError):
        return str(n.get("display") or "")


_AR_KIND = {"sector_appetite": "تركز قطاعي قريب من حد شهية المخاطر أو فوقه",
            "deal_queue": "صفقات تنتظر قرار الائتمان", "ews_proposals": "مقترحات الإنذار المبكر بانتظار القرار",
            "migrations": "تعرضات انتقلت إلى مرحلة أسوأ", "breach": "مخالفة تنظيمية",
            "ecl_anomaly": "مسائل في بيانات احتساب الخسائر الائتمانية المتوقعة",
            "letters": "خطابات المدقق والجهة الرقابية المفتوحة", "queries": "استفسارات مفتوحة على الصفقات",
            "large_exposure": "تعرض كبير مقابل الضمانات", "lens_alert": "تنبيه من العدسات",
            "conditions": "شروط موافقة مفتوحة أو مستحقة", "watch_due": "محفزات مخاطر مقبولة تستحق قريباً",
            "repricing": "تسهيلات للتجديد دون العائد المطلوب", "approvals": "موافقات بانتظار القرار",
            "tier_high": "صفقات في فئة المراقبة العالية"}

#: Why the kind matters, said natively in Arabic (one sentence per kind).
_AR_WHY = {"sector_appetite": "تجاوز الحد أو الاقتراب منه يقيّد الإقراض الجديد في القطاع ويرفع تركز المخاطر.",
           "deal_queue": "كل يوم انتظار يؤخر العميل ويضغط على مواعيد اللجان.",
           "migrations": "الانتقال إلى مرحلة أسوأ يرفع المخصصات ويستدعي مراجعة العملاء المعنيين.",
           "ews_proposals": "المقترحات المعلقة تعني إشارات إنذار لم يُتخذ فيها قرار بعد.",
           "breach": "المخالفة التنظيمية تظهر في تقارير التفتيش وتتطلب معالجة موثقة.",
           "ecl_anomaly": "إن لم تُصحح البيانات قبل الاحتساب فستكون أرقام المخصصات خاطئة.",
           "letters": "تأخر الرد على المدقق أو الجهة الرقابية يضر بالعلاقة الرقابية.",
           "queries": "الاستفسارات المفتوحة تؤخر قرارات الائتمان.",
           "conditions": "الشروط غير المستوفاة تعني أن التسهيل يعمل خارج ما وافقت عليه اللجنة.",
           "watch_due": "المخاطر المقبولة مشروطة بمحفزات، وتجاوزها يعيد القرار إلى اللجنة.",
           "repricing": "التجديد بسعر دون العائد المطلوب يستهلك رأس المال دون عائد كافٍ.",
           "approvals": "القرارات المعلقة تؤخر العمل في الوحدات الأخرى.",
           "tier_high": "الصفقات في الفئة العالية تحتاج متابعة أقرب ومحفزات واضحة.",
           "large_exposure": "التعرض الكبير يركز الخسارة المحتملة في عميل واحد.",
           "lens_alert": "التنبيه يعني أن مؤشراً في المحفظة تجاوز حده."}


def _ar_title(item: dict[str, Any]) -> str:
    base = _AR_KIND.get(str(item.get("kind") or ""), "بند يحتاج انتباهك")
    name = (item.get("entity") or {}).get("name")
    name = _AR_SECTOR.get(str(name), name)
    return f"{base}: {name}" if name and str(item.get("kind")) in ("sector_appetite", "large_exposure") else base


# ------------------------------------------------------------------ "In plain words" (K34 block, content by n)

def _clip(sentence: str, words: int) -> str:
    w = sentence.split()
    return sentence if len(w) <= words else " ".join(w[:words]).rstrip(",;:") + "…"


def plain_words(item: dict[str, Any], facts: dict[str, Any] | None, script: str,
                options: dict[str, Any] | None = None) -> list[str]:
    """3 lines, at most ~60 words: what this is, what it means here (with the number that matters), what to do.
    Deterministic, from the same facts as the spoken script."""
    if facts and facts.get("unit") == "SAR million":
        return [f"The regulator sets a minimum provision for loans in default (Stage 3); the bank holds less on {facts['n']} of them.",
                f"The bank holds {facts['bank_rate']:.1f}% of the exposure as provision; the minimum is {facts['floor_rate']:.1f}%: "
                f"SAR {facts['shortfall']:,.1f}m short.",
                "Top up the oldest cases first and send loans in default for five years or more to write-off review."]
    if facts and facts.get("unit") == "stage":
        top = max(facts.get("stages") or [{"stage": 2, "share": 0}], key=lambda x: x["share"])
        return [f"When a company defaults on one loan, all its loans must be treated as in default (Stage {facts.get('required_stage', 3)}).",
                f"{facts['n']} loans of such companies are still held as performing, {top['share']:.0f}% of the exposure in Stage {top['stage']}.",
                "Apply cross-default in this quarter's staging run, largest names first."]
    sentences = [x for x in re.split(r"(?<!Art\.)(?<!No\.)(?<=[.!?])\s+", script) if x]
    out = [_clip(str(item.get("title") or "").rstrip(".") + ".", 24)]
    why = next((x for x in sentences if x.startswith("Why it matters:")), "")
    if why:
        w = why.replace("Why it matters: ", "")
        out.append(_clip(w[:1].upper() + w[1:], 18))
    rec = next((o for o in (options or {}).get("options") or [] if o.get("recommended")), None)
    if rec:
        generic = rec.get("key") in ("act", "assign", "monitor")
        out.append(_clip(str(rec.get("how") if generic else rec.get("title") or ""), 18))
    return [x for x in out if x][:4]


# ------------------------------------------------------------------ the brief, and answers

def spoken_line(item: dict[str, Any]) -> str:
    """One sentence for a line in the brief-level script."""
    return speakable(str(item.get("title") or "")).rstrip(".") + "."


def spoken_line_ar(item: dict[str, Any]) -> str:
    nums = [n for n in item.get("numbers") or [] if n.get("value") is not None][:2]
    tail = ("، " + "، ".join(f"{_ar_label(n['label'])} {_ar_display(n)}" for n in nums)) if nums else ""
    return f"{_ar_title(item)}{tail}."


def brief_script(headline: str, headline_ar: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    order = ["First", "Second", "Third", "Fourth", "Fifth"]
    order_ar = ["أولاً", "ثانياً", "ثالثاً", "رابعاً", "خامساً"]
    en = " ".join([speakable(headline)] + [f"{order[i]}: {spoken_line(r)}" for i, r in enumerate(rows[:5])])
    ar = " ".join([headline_ar] + [f"{order_ar[i]}: {spoken_line_ar(r)}" for i, r in enumerate(rows[:5])])
    return {"en": en, "ar": ar, "seconds_en": seconds(en), "seconds_ar": seconds(ar, "ar")}


def answer_summary(kind: str, answer: dict[str, Any], item: dict[str, Any] | None = None) -> str:
    """What the speaker on an answer reads: the answer's own sentence and, for options, the recommended one."""
    text = speakable(str(answer.get("answer") or ""))
    if kind == "options":
        rec = next((o for o in answer.get("options") or [] if o.get("recommended")), None)
        if rec:
            text = (text + " " if text else "") + f"Recommended: {rec['title'].rstrip('.')}. {speakable(rec.get('effect') or '')}"
    return re.sub(r"\s+", " ", text).strip()


def options_plain_words(answer: dict[str, Any]) -> list[str]:
    """"In plain words" for What should we do?: the choice in one line, the recommended option and what it changes."""
    opts = answer.get("options") or []
    rec = next((o for o in opts if o.get("recommended")), None)
    if not opts:
        return ["No option could be priced for this line."]
    short = [_clip(str(o.get("title") or "").split(";")[0].rstrip("."), 7) for o in opts]
    out = [f"{len(opts)} options: " + "; ".join(short) + "."]
    if rec:
        out.append(_clip(f"Recommended: {str(rec.get('title') or '').rstrip('.')}.", 18))
        generic = rec.get("key") in ("act", "assign", "monitor")
        detail = str(rec.get("how") if generic else rec.get("effect") or "")
        if detail:
            out.append(_clip(detail.rstrip(".") + ".", 22))
    return out[:4]
