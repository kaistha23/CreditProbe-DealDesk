"""The RM's ask and notes, read by rules (N4: no model, same result every run).

    a = parse_ask("Renew the SAR 45m overdraft and increase the LC line from SAR 20m to SAR 30m, SAIBOR + 2.25%, 12 months")
    a["items"]   -> [{"action": "renew", "facility": "Overdraft", "amount": 45.0, ...}, {"action": "increase", "facility": "Letters of credit",
                     "from_amount": 20.0, "amount": 30.0, ...}]
    n = parse_notes("Owner is hands-on. Business routed via us is SAR 180m a year.")
    n["lines"]   -> [{"text": ..., "topic": "background"}, {"text": ..., "topic": "relationship"}]

Amounts are in millions of the currency named (SAR when none is named). A figure the RM typed is attributed "as per RM" wherever
it is printed; a figure the ask does not give is never invented: the writer says "not stated in the ask".
"""
from __future__ import annotations

import re
from typing import Any

CCY = r"(?:SAR|SR|USD|AED|EUR|US\$|\$)"
UNIT = r"(?:bn|billion|b|mn|m|million|mio|k|thousand)"
AMOUNT = re.compile(rf"(?P<c1>{CCY})?\s*(?P<n>\d[\d,]*(?:\.\d+)?)\s*(?P<u>{UNIT})?\b\.?\s*(?P<c2>{CCY})?", re.I)

#: facility vocabulary -> (canonical label, kind); first match wins, longest phrases first
FACILITIES: list[tuple[str, str, str]] = [
    (r"advance payment (?:guarantee|lg)s?|\bapgs?\b", "Advance payment guarantees", "lg"),
    (r"performance (?:bond|guarantee|lg)s?|\bpbs?\b", "Performance guarantees", "lg"),
    (r"bid bonds?|tender (?:bond|guarantee)s?|\bbbs?\b", "Bid bonds", "lg"),
    (r"retention (?:bond|guarantee)s?", "Retention guarantees", "lg"),
    (r"letters? of guarantee|\blgs?\b|guarantee line|bank guarantees?", "Letters of guarantee", "lg"),
    (r"usance (?:lcs?|letters? of credit)", "Usance letters of credit", "lc"),
    (r"sight (?:lcs?|letters? of credit)", "Sight letters of credit", "lc"),
    (r"letters? of credit|\blcs?\b|documentary credits?", "Letters of credit", "lc"),
    (r"trust receipts?|\btrs?\b|lc refinanc\w*", "Trust receipts / LC refinance", "funded"),
    (r"invoice discount\w*|receivables? (?:finance|discount\w*)|factoring", "Receivables finance", "funded"),
    (r"overdrafts?|\bod\b|current account limit", "Overdraft", "funded"),
    (r"short[- ]term (?:loan|murabaha|finance)s?|\bstls?\b|\bstl\b", "Short-term murabaha", "funded"),
    (r"tawarruq", "Tawarruq", "funded"),
    (r"murabaha", "Murabaha", "funded"),
    (r"medium[- ]term loan|\bmtl\b|term loans?|term finance|ijara\w*|capex (?:loan|finance|line)", "Term finance", "funded"),
    (r"project (?:limit|finance|line|facility)", "Project limit", "combined"),
    (r"working capital (?:limit|line|facility|finance)?|revolving (?:limit|line|facility|credit)", "Working capital limit", "funded"),
    (r"general (?:limit|line|facility)|combined limit|overall limit|umbrella limit", "General limit", "combined"),
    (r"trade (?:finance )?(?:limit|line|facilit\w+)", "Trade finance limit", "combined"),
    (r"(?:fx|foreign exchange|treasury) (?:line|limit)", "FX / treasury line", "treasury"),
    (r"corporate (?:credit )?cards?|credit cards?", "Corporate cards", "funded"),
    (r"takeover (?:limit|facility|loan)", "Takeover facility", "funded"),
]
FAC = [(re.compile(p, re.I), lab, kind) for p, lab, kind in FACILITIES]

ACTIONS = [("takeover", r"take ?over|takeover|refinance (?:the )?other bank|buy ?out"),
           ("increase", r"increase|enhance|raise|top[- ]?up|uplift|step up"),
           ("reduce", r"reduce|decrease|cut|lower"),
           ("cancel", r"cancel|close|withdraw|terminate"),
           ("renew", r"renew|roll ?over|extend|continue|maintain|retain"),
           ("new", r"\bnew\b|\badd\b|introduce|grant|approve|set up|establish|open|sanction|one[- ]off")]
ACT = [(a, re.compile(p, re.I)) for a, p in ACTIONS]
VERB = r"renew|increase|enhance|raise|add|new|reduce|decrease|cancel|take ?over|takeover|grant|approve|introduce|set up|establish|extend|sanction|maintain|retain"

PRICING = [re.compile(r"(?:SAIBOR|SIBOR|EIBOR|SOFR|benchmark)\s*\+\s*(\d+(?:\.\d+)?)\s*%", re.I),
           re.compile(r"(?:SAIBOR|SIBOR|EIBOR|SOFR|benchmark)\s*\+\s*(\d+)\s*(?:bps|bp|basis points)", re.I),
           re.compile(r"(?:margin|spread|profit rate)\s*(?:of|at)?\s*(\d+(?:\.\d+)?)\s*%", re.I),
           re.compile(r"(?:margin|spread)\s*(?:of|at)?\s*(\d+)\s*(?:bps|bp)", re.I)]
COMMISSION = re.compile(r"(?:commission|fee)\s*(?:of|at)?\s*(\d+(?:\.\d+)?)\s*%\s*(p\.?a\.?|per annum|flat|per quarter|p\.?q\.?)?", re.I)
TENOR = re.compile(r"(\d+(?:\.\d+)?)\s*[- ]?(months?|mths?|years?|yrs?)\b", re.I)
SECURITY = re.compile(r"(?:secured|against|backed|supported|guaranteed|assignment|mortgage|pledge|hypothecation|cash margin|personal guarantee|"
                      r"corporate guarantee|promissory|security cheque|undated cheque)", re.I)
BENCH = re.compile(r"\b(SAIBOR|SIBOR|EIBOR|SOFR)\b", re.I)


def to_millions(n: str, unit: str | None) -> float:
    x = float(n.replace(",", ""))
    u = (unit or "").lower()
    if u in ("bn", "billion", "b"):
        return x * 1000
    if u in ("k", "thousand"):
        return x / 1000
    if u in ("m", "mn", "million", "mio"):
        return x
    return x / 1e6 if x >= 100_000 else x  # "SAR 45,000,000" or "SAR 45"


def amounts(text: str) -> list[dict[str, Any]]:
    """Money amounts in a clause: [{"value": millions, "ccy", "at": index}], ignoring percentages, tenors and years."""
    out = []
    for m in AMOUNT.finditer(text):
        n, u = m.group("n"), m.group("u")
        ccy = m.group("c1") or m.group("c2")
        tail = text[m.end("n"):m.end("n") + 12].lower()
        if re.match(r"\s*(%|bps|bp|basis|months?|mths?|years?|yrs?|days?|x\b|times)", tail):
            continue
        if not ccy and not u:
            continue  # a bare number is not an amount ("2026", "12")
        if re.fullmatch(r"(19|20)\d\d", n) and not u:
            continue
        cc = (ccy or "SAR").upper().replace("SR", "SAR").replace("US$", "USD").replace("$", "USD")
        out.append({"value": round(to_millions(n, u), 3), "ccy": cc, "at": m.start(), "text": m.group(0).strip()})
    return out


FAC_WORDS = "|".join(f"(?:{p})" for p, _, _ in FACILITIES)


def clauses(text: str) -> list[str]:
    t = re.sub(r"\s+", " ", text or "").strip()
    # "take over X with a term loan of SAR 60m and an LG line of SAR 25m": one clause per facility named with its own amount
    t = re.sub(rf"\s+(?:with|and|plus)\s+(?=(?:a |an |the )?(?:new )?(?:(?:{CCY})\s*[\d.,]+\s*(?:{UNIT})?\s+)?(?:{FAC_WORDS}))", "; ", t, flags=re.I)
    parts = re.split(rf";|\n|(?<=[a-z\)])\.\s+|,\s*(?=(?:and\s+)?(?:{VERB})\b)|\s+and\s+(?=(?:also\s+)?(?:{VERB})\b)|\s+plus\s+(?=(?:a\s+)?(?:{VERB}|\w+ (?:line|limit)))",
                     t, flags=re.I)
    return [p.strip(" ,.") for p in parts if p and p.strip(" ,.")]


def facility_of(text: str) -> tuple[str, str] | None:
    for rx, lab, kind in FAC:
        if rx.search(text):
            return lab, kind
    return None


def action_of(text: str, default: str = "") -> str:
    hits = [(m.start(), a) for a, rx in ACT for m in [rx.search(text)] if m]
    return min(hits)[1] if hits else default


def pricing_of(text: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    b = BENCH.search(text)
    for i, rx in enumerate(PRICING):
        m = rx.search(text)
        if m:
            v = float(m.group(1))
            out["margin_pct"] = v / 100 if i in (1, 3) else v
            out["benchmark"] = (b.group(1).upper() if b else ("SAIBOR" if i < 2 else ""))
            break
    m = COMMISSION.search(text)
    if m:
        out["commission_pct"] = float(m.group(1))
        out["commission_basis"] = (m.group(2) or "p.a.").replace("per annum", "p.a.")
    return out


def tenor_of(text: str) -> int | None:
    m = TENOR.search(text)
    if not m:
        return None
    v = float(m.group(1))
    return int(round(v * 12)) if m.group(2).lower().startswith("y") else int(round(v))


BARE = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s*(?:m|mn|million)?(?![\w.%])(?!\s*(?:%|months?|mths?|years?|yrs?|days?|bps|bp))", re.I)
TAKEOVER_BANK = re.compile(r"take ?over (?:the facilities (?:of|with|from) |facilities (?:of|with|from) )?((?:[A-Z][\w&'-]*\s){0,4}Bank)\b")


FAMILY = {"Short-term murabaha": "murabaha", "Murabaha": "murabaha", "Tawarruq": "murabaha", "Letters of credit": "lc",
          "Sight letters of credit": "lc", "Usance letters of credit": "lc", "Letters of guarantee": "lg", "Performance guarantees": "lg",
          "Advance payment guarantees": "lg", "Bid bonds": "lg", "Retention guarantees": "lg", "General limit": "general",
          "Working capital limit": "general", "Trade finance limit": "general"}


def family(label: str) -> str:
    """The facility family a label belongs to (so "Murabaha" in an ask names the "Short-term Murabaha" on the books)."""
    canon = (facility_of(label) or (label,))[0]
    return FAMILY.get(canon, canon.lower())


def same_facility(a: str, b: str) -> bool:
    return a.strip().lower() == b.strip().lower() or family(a) == family(b)


def _match_existing(fac: str, existing: list[dict[str, Any]]) -> dict[str, Any] | None:
    exact = [e for e in existing if (facility_of(str(e.get("facility", ""))) or ("",))[0] == fac or str(e.get("facility", "")).lower() == fac.lower()]
    if exact:
        return exact[0]
    fam = [e for e in existing if same_facility(str(e.get("facility", "")), fac)]
    return fam[0] if len(fam) == 1 else None


def _list_parse(text: str, existing: list[dict[str, Any]]) -> dict[str, Any] | None:
    """An ask that lists its facilities after a colon or in brackets ("increase them to SAR 140m: Murabaha 40 to 65, LCs 30 to 40,
    LGs 10 unchanged"; "takeover: SAR 157m (term loan 72m over 48 months, Murabaha 45m, LCs 40m) at SAIBOR + 1.25%"). Amounts in the
    list are in millions of the sentence's currency; the head's amounts are totals; pricing after the list applies to every item."""
    t = re.sub(r"\s+", " ", text or "").strip()
    m = re.search(r"\(([^()]*)\)", t)
    if m and len([x for x in re.split(r",|;|\band\b", m.group(1)) if facility_of(x)]) >= 2:
        head, body, tail = t[:m.start()], m.group(1), t[m.end():]
    elif ":" in t and len([x for x in re.split(r",|;|\band\b", t.split(":", 1)[1]) if facility_of(x)]) >= 2:
        head, rest = t.split(":", 1)
        parts = re.split(r"(?<=[a-z0-9%])\.\s+", rest, maxsplit=1)
        body, tail = parts[0], (parts[1] if len(parts) > 1 else "")
    else:
        return None
    ccy = next((a["ccy"] for a in amounts(t)), "SAR")
    head_act = action_of(head, default="new")
    tb = TAKEOVER_BANK.search(t)
    takeover = bool(re.search(r"take ?over|takeover", t, re.I))
    pr_tail, ten_tail = pricing_of(tail), tenor_of(tail)
    items = []
    for seg in [x.strip(" .") for x in re.split(r",|;|\band\b(?![^()]*\))", body) if x.strip(" .")]:
        fac = facility_of(seg)
        if not fac:
            continue
        nums = [a["value"] for a in amounts(seg)] or [float(x) for x in BARE.findall(re.sub(TENOR, " ", seg))]
        cur = _match_existing(fac[0], existing)
        it: dict[str, Any] = {"facility": fac[0], "kind": fac[1], "clause": seg, "ccy": ccy}
        if re.search(r"unchanged|same|as is|no change|maintain", seg, re.I):
            it["action"] = "renew"
            it["amount"] = nums[0] if nums else (cur or {}).get("limit")
        elif len(nums) >= 2 and re.search(r"\bto\b|->|→", seg):
            it["from_amount"], it["amount"] = nums[0], nums[1]
            it["action"] = "increase" if nums[1] > nums[0] else ("reduce" if nums[1] < nums[0] else "renew")
        elif nums:
            it["amount"] = nums[0]
            if cur is not None and cur.get("limit") is not None:
                lim = float(cur["limit"])
                it["action"] = "renew" if abs(lim - nums[0]) < 1e-6 else ("increase" if nums[0] > lim else "reduce")
                if it["action"] != "renew":
                    it["from_amount"] = lim
            else:
                it["action"] = "new"
        else:
            it["action"] = "renew" if cur else head_act
            it["amount"] = (cur or {}).get("limit")
        if cur is not None:
            it["existing_limit"], it["existing_outstanding"] = cur.get("limit"), cur.get("outstanding")
        if takeover and it["action"] == "new":
            it["purpose"] = f"takeover of {tb.group(1).strip()}" if tb else "takeover of the other bank's facilities"
        ten = tenor_of(seg)
        if ten:
            it["tenor_months"] = ten
        it.update(pricing_of(seg) or ({k: v for k, v in pr_tail.items()} if fac[1] not in ("lc", "lg") else
                                      {k: v for k, v in pr_tail.items() if k.startswith("commission")}))
        if ten_tail and not it.get("tenor_months"):
            it["tenor_months"] = ten_tail
        items.append(it)
    if len(items) < 2:
        return None
    heads = [a["value"] for a in amounts(head)]
    sec = [c for c in clauses(tail) if SECURITY.search(c)]
    return {"items": items, "head_totals": heads, "takeover_bank": tb.group(1).strip() if tb else "", "security": sec,
            "renew_existing_total": heads[0] if heads and re.search(r"renew", head, re.I) else None,
            "target_total": heads[-1] if heads and (len(heads) > 1 or not re.search(r"renew", head, re.I)) else None}


def parse_ask(text: str, existing: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """The ask as items. `existing`: the customer's current facilities [{"facility", "limit", ...}] so "renew all" and "increase the
    overdraft to SAR 60m" name the current limit."""
    existing = existing or []
    lp = _list_parse(text, existing)
    if lp:
        items = lp["items"]
        return {"text": (text or "").strip(), "items": items, "security": lp["security"], "list": True,
                "head_totals": lp["head_totals"], "target_total": lp["target_total"], "renew_existing_total": lp["renew_existing_total"],
                "takeover_bank": lp["takeover_bank"],
                "pricing": next(({k: v for k, v in i.items() if k in ("margin_pct", "benchmark", "commission_pct", "commission_basis")} for i in items if "margin_pct" in i), {}),
                "tenor_months": next((i["tenor_months"] for i in items if i.get("tenor_months")), None),
                "total_proposed": round(sum(float(i.get("amount") or 0) for i in items if i["action"] != "cancel"), 3)}
    items: list[dict[str, Any]] = []
    security: list[str] = []
    last: dict[str, Any] | None = None
    renew_all = bool(re.search(r"renew (?:all|the existing|existing|current)(?: (?:facilities|limits|lines))?", text or "", re.I))
    for c in clauses(text):
        if SECURITY.search(c) and not facility_of(c) and not amounts(c):
            security.append(c)
            continue
        fac = facility_of(c)
        act = action_of(c, default="")
        if renew_all and not fac and not amounts(c) and re.search(r"renew", c, re.I):
            continue
        am = amounts(c)
        pr, ten = pricing_of(c), tenor_of(c)
        if not fac and not am and last is not None and (pr or ten):
            last.update({k: v for k, v in pr.items() if k not in last})
            if ten and not last.get("tenor_months"):
                last["tenor_months"] = ten
            continue
        if not fac and not am and not act:
            if SECURITY.search(c):
                security.append(c)
            continue
        if not fac and am and act in ("new", "increase", "renew", "takeover", "") and re.search(r"limit|line|facilit|exposure|finance|loan", c, re.I) is None and last is not None:
            fac = (last["facility"], last["kind"])
        if not fac:
            fac = ("Takeover facility", "funded") if act == "takeover" else ("Facility (type not stated)", "funded")
        cur = _match_existing(fac[0], existing)
        it: dict[str, Any] = {"action": act or ("renew" if cur else "new"), "facility": fac[0], "kind": fac[1], "clause": c,
                              "ccy": am[0]["ccy"] if am else "SAR"}
        if re.search(r"\bfrom\b", c, re.I) and len(am) >= 2:
            it["from_amount"], it["amount"] = am[0]["value"], am[1]["value"]
        elif re.search(r"\bby\b", c, re.I) and am and it["action"] in ("increase", "reduce") and cur and cur.get("limit") is not None:
            it["from_amount"] = float(cur["limit"])
            it["amount"] = round(float(cur["limit"]) + (am[0]["value"] if it["action"] == "increase" else -am[0]["value"]), 3)
        elif am:
            it["amount"] = am[0]["value"]
        if cur is not None:
            it["existing_limit"] = cur.get("limit")
            it["existing_outstanding"] = cur.get("outstanding")
            if "from_amount" not in it and it["action"] in ("increase", "reduce"):
                it["from_amount"] = cur.get("limit")
            if it["action"] == "renew" and "amount" not in it:
                it["amount"] = cur.get("limit")
        if re.search(r"one[- ]off", c, re.I):
            it["one_off"] = True
        it.update(pr)
        if ten:
            it["tenor_months"] = ten
        m = re.search(r"\bfor\s+(?!\d)(.{4,80}?)(?:$|,|;| at | with )", c, re.I)
        if m and not TENOR.match(m.group(1)):
            it["purpose"] = m.group(1).strip()
        if SECURITY.search(c):
            security.append(c)
        items.append(it)
        last = it
    if renew_all:
        have = {i["facility"].lower() for i in items}
        for e in existing:
            lab = (facility_of(str(e.get("facility", ""))) or (str(e.get("facility")), "funded"))[0]
            if lab.lower() not in have and str(e.get("facility", "")).lower() not in have and float(e.get("limit") or 0) > 0:
                items.append({"action": "renew", "facility": str(e.get("facility")), "kind": "funded", "clause": "renew existing facilities",
                              "ccy": e.get("ccy") or "SAR", "amount": e.get("limit"), "existing_limit": e.get("limit"),
                              "existing_outstanding": e.get("outstanding")})
    return {"text": (text or "").strip(), "items": items, "security": list(dict.fromkeys(security)),
            "pricing": next(({k: v for k, v in i.items() if k in ("margin_pct", "benchmark", "commission_pct", "commission_basis")} for i in items if "margin_pct" in i), {}),
            "tenor_months": next((i["tenor_months"] for i in items if i.get("tenor_months")), None),
            "total_proposed": round(sum(float(i.get("amount") or 0) for i in items if i["action"] != "cancel"), 3)}


TOPICS = [("security", r"guarant|collateral|mortgag|assign|pledge|security|cheque|cash margin|title deed|net ?worth"),
          ("relationship", r"relationship|banking with|banks with|since \d{4}|deposit|turnover|payroll|account|wallet|cross[- ]sell|routed|conduct|utili[sz]"),
          ("terms", r"covenant|undertak|condition|route|routing|within \d|subordinat|dividend|reporting|pric(?:e|ing)|saibor|margin of|spread"),
          ("market", r"contract|order|tender|project|supplier|market|demand|backlog|pipeline|award|distribut"),
          ("background", r"founded|establish|owner|family|shareholder|sister|subsidiar|group|staff|employee|branch|management|generation|ceo|md\b"),
          ("financials", r"revenue|sales|profit|margin|ebitda|audited|growth|grew|leverage|debt|cash ?flow|receivable|inventory|vat|customer")]
TOP = [(t, re.compile(p, re.I)) for t, p in TOPICS]


def sentences(text: str) -> list[str]:
    t = re.sub(r"[ \t]+", " ", text or "").strip()
    raw = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])|\n+|^\s*[-•*]\s*|\s+[-•]\s+(?=[A-Z])", t, flags=re.M)
    return [s.strip(" -•*").strip() for s in raw if s and len(s.strip(" -•*").strip()) > 2]


def parse_notes(text: str) -> dict[str, Any]:
    lines = []
    for s in sentences(text):
        topic = next((t for t, rx in TOP if rx.search(s)), "justification")
        s2 = s if s.endswith((".", "!", "?")) else s + "."
        lines.append({"text": s2[0].upper() + s2[1:], "topic": topic, "figures": [a["text"] for a in amounts(s)]
                      + re.findall(r"\d+(?:\.\d+)?\s*%", s)})
    return {"text": (text or "").strip(), "lines": lines, "topics": sorted({l["topic"] for l in lines})}
