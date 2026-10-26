"""Contractor evidence from the uploaded documents: the project schedule, contracts and payment certificates, joined with
the bank statements, as dd_project rows (anatomy §9 Status of financed projects, §13 New project).

    rows(pid, obligor_id, docs, request)  -> {"dd_project": [...]} ({} when the customer is not a contractor)
    certificates(docs)                     -> [{project_id, certificate_number, certified_on, due_date, net_payable_mn,
                                               paid_on, paid_amount_mn, days_late, status, source}]

A certificate is paid when a statement credit of the same amount, or of the amount plus 15% VAT (within 1%), lands on or
after its certification date;
it is late by the days between its due date and that credit (or the as-of date when unpaid). Deterministic.
"""
from __future__ import annotations

import json
import re
from datetime import date, timedelta
from typing import Any


def as_of() -> date:
    try:
        from ops.r16_customers import ids
        return date.fromisoformat(ids.AS_OF)
    except Exception:  # noqa: BLE001
        return date.today()


def _d(s: Any) -> date | None:
    try:
        return date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return None


def _mn(x: Any) -> float | None:
    try:
        return None if x in (None, "") else round(float(x) / 1e6, 4)
    except (TypeError, ValueError):
        return None


def _credits(docs: list[dict[str, Any]]) -> list[tuple[date, float, str, str]]:
    out = []
    for d in docs:
        if d.get("doc_type") != "bank_statement":
            continue
        for t in d["fields"].get("transactions") or []:
            dt, cr = _d(t.get("date")), t.get("credit")
            if dt and isinstance(cr, (int, float)) and cr > 0:
                out.append((dt, float(cr), str(t.get("description") or ""), d["name"]))
    out.sort()
    return sorted(out)


def certificates(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cr = _credits(docs)
    # unpaid certificates are aged to the last statement date (the latest evidence of receipts), else the as-of date
    ends = [_d(d["fields"].get("period_to")) for d in docs if d.get("doc_type") == "bank_statement" and d["fields"].get("transactions")]
    today = max([e for e in ends if e], default=None) or as_of()
    out = []
    for d in docs:
        if d.get("doc_type") != "payment_certificate":
            continue
        f = d["fields"]
        net = f.get("net_payable")
        cert_on, due = _d(f.get("certified_on")), _d(f.get("due_date"))
        paid = None
        num = str(f.get("certificate_number") or "").strip()
        if num:  # the credit names the certificate ("SLDC payment IPC-11 incl. VAT")
            paid = next(((dt, amt, desc, src) for dt, amt, desc, src in cr if re.search(rf"(?<![\w-]){re.escape(num)}(?![\w])", desc)), None)
        if paid is None and isinstance(net, (int, float)) and net > 0 and cert_on:
            # the employer pays the net certified amount, or the net amount plus 15% VAT (the tax invoice)
            paid = next(((dt, amt, desc, src) for dt, amt, desc, src in cr if dt >= cert_on and not re.search(r"IPC[- ]?\d+", desc, re.I) and
                         (abs(amt - net) <= 0.01 * net or abs(amt - net * 1.15) <= 0.01 * net * 1.15)), None)
        late = None
        if due:
            end = paid[0] if paid else today
            late = (end - due).days
        out.append({"project_id": str(f.get("project_id") or ""), "certificate_number": str(f.get("certificate_number") or ""),
                    "period_to": f.get("period_to"), "certified_on": f.get("certified_on"), "due_date": f.get("due_date"),
                    "net_payable_mn": _mn(net), "gross_work_done_mn": _mn(f.get("gross_work_done")), "cumulative_retention_mn": _mn(f.get("cumulative_retention")),
                    "paid_on": paid[0].isoformat() if paid else None, "paid_amount_mn": _mn(paid[1]) if paid else None,
                    "paid_source": paid[3] if paid else None, "days_late": late, "aged_to": today.isoformat(),
                    "status": ("paid" if paid else ("overdue" if due and due < today else "not yet due")), "source": d["name"]})
    return sorted(out, key=lambda c: (c["project_id"], str(c["certified_on"])))


def _sane(r: dict[str, Any]) -> bool:
    """A project-list row read in line: amounts in order (received <= billed <= contract value), dates that parse."""
    try:
        cv, b, rc = float(r.get("contract_value") or 0), float(r.get("billed") or 0), float(r.get("received") or 0)
    except (TypeError, ValueError):
        return False
    ok_dates = all(_d(r.get(k)) is not None for k in ("planned_completion",) if r.get(k))
    return cv >= 1e6 and b <= cv * 1.02 and rc <= b * 1.02 + 1 and ok_dates


def _key(s: str) -> str:
    """'P1 Eastern Corridor Logistics Hub — Package B' and 'Eastern Corridor Logistics Hub — Package B' are one project."""
    return re.sub(r"[^a-z0-9]", "", re.sub(r"^\s*P\d+\s+", "", str(s or ""), flags=re.I).lower())


def _int(x: Any) -> int | None:
    m = re.search(r"\d+", str(x or ""))
    return int(m.group(0)) if m else None


def _same(a: str, b: str) -> bool:
    x, y = _key(a), _key(b)
    if re.fullmatch(r"\s*P\d+\s*", str(a or ""), re.I) or re.fullmatch(r"\s*P\d+\s*", str(b or ""), re.I):
        return str(a).strip().split()[0].upper() == str(b).strip().split()[0].upper() if a and b else False
    return bool(x and y and (x == y or (len(min(x, y, key=len)) > 8 and (x in y or y in x))))


def rows(pid: str, oid: str, docs: list[dict[str, Any]], request: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    plist = next((d for d in docs if d.get("doc_type") == "project_list"), None)
    contracts = [d for d in docs if d.get("doc_type") == "project_contract"]
    certs = certificates(docs)
    if not plist and not contracts and not certs:
        return {}
    projects: dict[str, dict[str, Any]] = {}
    lrows = (plist or {}).get("fields", {}).get("projects") or []
    if lrows and not all(_sane(r) for r in lrows):
        lrows = []  # a table read out of line (wrapped PDF cells): not used; the request's own table and the contracts stand
    if not lrows:
        lrows = [{"project_id": r["project"], "project": r["project"], "employer": r["employer"],
                  "contract_value": (r["value_mn"] or 0) * 1e6, "planned_completion": r["completion"], "work_done_pct": r["done_pct"],
                  "billed": (r["billed_mn"] or 0) * 1e6 if r["billed_mn"] is not None else None,
                  "received": (r["received_mn"] or 0) * 1e6 if r["received_mn"] is not None else None,
                  "retention_held": (r["retention_mn"] or 0) * 1e6 if r["retention_mn"] is not None else None, "status": "as per business"}
                 for r in request.get("projects") or []]
    for r in lrows:
        key = str(r.get("project") or r.get("project_id") or "").strip()
        if key:
            projects[key] = {"list": r}
    for d in contracts:
        f = d["fields"]
        key = str(f.get("project_id") or "").strip()
        hit = next((k for k in projects if _same(k, key) or _same(str(projects[k]["list"].get("project") or ""), key)), key)
        projects.setdefault(hit, {})["contract"] = {**f, "_source": d["name"]}
    for c in certs:
        hit = next((k for k in projects if _same(k, c["project_id"]) or _same(str((projects[k].get("list") or {}).get("project") or ""), c["project_id"])), c["project_id"])
        projects.setdefault(hit, {}).setdefault("certs", []).append(c)
    fac_names = [r["limit_name"] for r in request.get("facilities") or [] if r.get("level") == 1]
    today = as_of()
    out = []
    for i, (key, p) in enumerate(sorted(projects.items())):
        li, ct, cs = p.get("list") or {}, p.get("contract") or {}, p.get("certs") or []
        name = str(li.get("project") or ct.get("project_id") or key)
        value = li.get("contract_value") if isinstance(li.get("contract_value"), (int, float)) else ct.get("contract_value")
        comp_c, comp_l = _d(ct.get("completion_date")), _d(li.get("planned_completion"))
        eot = (comp_l - comp_c).days if comp_c and comp_l and comp_l > comp_c else 0
        status_txt = str(li.get("status") or "")
        formal = 1 if re.search(r"EOT\s+(approved|formalised|granted)|extension\s+(approved|granted|formalised)", status_txt, re.I) else 0
        wd = li.get("work_done_pct")
        overdue = [c for c in cs if c["status"] == "overdue"]
        paid_late = [c for c in cs if c["status"] == "paid" and (c["days_late"] or 0) > 0]
        last = cs[-1] if cs else {}
        delay = max([c["days_late"] or 0 for c in cs], default=0)
        billed, recv = _mn(li.get("billed")), _mn(li.get("received"))
        is_new = (wd in (None, 0, 0.0)) and not cs and bool(re.search(r"new|award|not started|mobili", status_txt, re.I) or not li)
        financed = any(_same(n, name) for n in fac_names) or any(_same(n, key) for n in fac_names)
        late_comp = bool(comp_l and comp_l < today and (wd or 0) < 100)
        parts = []
        if eot:
            parts.append(f"completion moved from {comp_c.isoformat()} (contract) to {comp_l.isoformat()} (project list), an extension of {eot} days"
                         + (" formalised" if formal else " not formalised by the employer"))
        if overdue:
            parts.append(f"{len(overdue)} certificate{'s' if len(overdue) != 1 else ''} unpaid past due date (oldest {max(c['days_late'] or 0 for c in overdue)} days)")
        if paid_late:
            parts.append(f"{len(paid_late)} paid late (up to {max(c['days_late'] for c in paid_late)} days)")
        out.append({"project_id": f"{pid}-P{i + 1:02d}", "proposal_id": pid, "obligor_id": oid, "project_name": f"{name} [{key}]" if key and key not in name else name,
                    "status": "new" if is_new else ("completed" if (wd or 0) >= 100 else "ongoing"), "financed_flag": 1 if financed else 0, "limit_id": "",
                    "employer": str(li.get("employer") or ct.get("employer") or ""), "employer_entity_id": "", "main_contractor": "",
                    "consultant": str(ct.get("consultant") or ""), "scope": "", "location": "",
                    "contract_value_original_mn": _mn(ct.get("contract_value")) or _mn(value), "contract_value_revised_mn": _mn(value),
                    "start_date": li.get("start") or ct.get("start_date"), "completion_original": ct.get("completion_date") or li.get("planned_completion"),
                    "completion_revised": li.get("planned_completion") if eot else None, "eot_days": eot or None, "eot_formalised_flag": formal if eot else None,
                    "work_done_pct": wd, "planned_pct": None, "billed_mn": billed, "received_mn": recv,
                    "due_mn": round((billed or 0) - (recv or 0) - (_mn(li.get("retention_held")) or 0), 4) if billed is not None and recv is not None else None,
                    "retention_mn": _mn(li.get("retention_held")) or (last.get("cumulative_retention_mn") if last else None),
                    "advance_mn": None, "last_cert_no": _int(last.get("certificate_number")), "last_cert_date": last.get("certified_on"),
                    "last_payment_date": max([c["paid_on"] for c in cs if c["paid_on"]], default=None), "payment_delay_days": delay or None,
                    "pending_certs_n": len(overdue) or None, "demand_letter_flag": 0, "lg_requirements": "",
                    "payment_terms": f"certified amounts paid within {ct.get('payment_terms_days')} days" if ct.get("payment_terms_days") else "",
                    "expected_margin_pct": None, "backlog_mn": round((_mn(value) or 0) * (1 - (wd or 0) / 100.0), 4) if value else None,
                    "narrative": ("; ".join(parts) + ("; past its planned completion" if late_comp else "")).strip("; ")
                    + f" [uploaded: {', '.join(sorted({x for x in [(plist or {}).get('name'), ct.get('_source')] + [c['source'] for c in cs] if x}))[:300]}]"})
    nw = new_award(request)
    if nw and not any(r["status"] == "new" and _same(r["project_name"], nw["name"]) for r in out):
        out.append({"project_id": f"{pid}-P{len(out) + 1:02d}", "proposal_id": pid, "obligor_id": oid, "project_name": nw["name"], "status": "new",
                    "financed_flag": 1, "limit_id": "", "employer": nw["employer"], "employer_entity_id": "", "main_contractor": "", "consultant": "",
                    "scope": "", "location": "", "contract_value_original_mn": nw["value_mn"], "contract_value_revised_mn": nw["value_mn"],
                    "start_date": nw["start"], "completion_original": nw["end"], "completion_revised": None, "eot_days": None, "eot_formalised_flag": None,
                    "work_done_pct": 0.0, "planned_pct": None, "billed_mn": None, "received_mn": None, "due_mn": None, "retention_mn": None,
                    "advance_mn": None, "last_cert_no": None, "last_cert_date": None, "last_payment_date": None, "payment_delay_days": None,
                    "pending_certs_n": None, "demand_letter_flag": 0, "lg_requirements": nw["lg"], "payment_terms": "",
                    "expected_margin_pct": None, "backlog_mn": nw["value_mn"],
                    "narrative": f"new award: letter of award {nw['loa'] or 'date not provided'}; contract not signed and cash-flow forecast not provided "
                                 f"(as per the business request, section 1) [business request]"})
    return {"dd_project": out}


class _Award:
    """The five groups new_award reads (limit, project name, employer, abbreviation, details), rebuilt from OCR text."""

    def __init__(self, *g: str) -> None:
        self._g = g

    def group(self, i: int) -> str:
        return self._g[i - 1]


def _ocr_award(request: dict[str, Any], act: str) -> _Award | None:
    """R16 x: the new project read from photos of the request. OCR joins words ("awardedby", "SAR 312.0m,24months") and can lose
    the line naming the project limit, so the limit comes from the facility tree (a new level-1 "Project limit" line), the employer
    and the award details from the bracketed text after "awarded by", and the project's name from the longest form of the limit's
    own name found anywhere in the request."""
    lim = next((f for f in request.get("facilities") or [] if not f.get("total") and f.get("level") == 1
                and re.search(r"project", f.get("limit_name") or "", re.I) and (f.get("existing_mn") or 0) == 0 and f.get("proposed_mn")), None)
    if not lim:
        return None
    a = re.search(r"awarded\s*by\s*(.+?)\s*\(([A-Z]{2,8})\)\s*\(([^)]*contract\s*value[^)]*)\)", act, re.I)
    if not a:
        return None
    stub = re.sub(r"^\s*project\s*limit\s*[-—–:]?\s*", "", lim["limit_name"], flags=re.I)
    stub = re.sub(r"\s*\((?:new|proposed)\)\s*$", "", stub, flags=re.I).strip(" -—–")
    blob = json.dumps(request, ensure_ascii=False, default=str)
    name = stub
    if stub:
        for x in re.findall(re.escape(stub) + r"(?:\s+(?:Logistics|Hub|Project|Phase|Centre|Center|Park|Tower|Towers|Complex|Terminal|Port|Road|City|Village|Campus|Hospital|Plant|Station|District|Development)\b){0,4}(?:\s*[—–-]\s*Package\s*[A-Z0-9]+)?", blob):
            if len(x) > len(name):
                name = x
    pk = re.search(r"Package\s*([A-Z0-9])(?![A-Z0-9])", act)
    if pk and "package" not in name.lower():
        name = f"{name} — Package {pk.group(1)}" if name else f"Package {pk.group(1)}"
    det = re.sub(r"(\d)\s*months", r"\1 months", a.group(3))
    det = re.sub(r",\s*(\d)", r", \1", det)
    det = re.sub(r"(?i)letterofaward", "letter of award", det)
    return _Award(f"{float(lim['proposed_mn']):.1f}", name or "the new project", a.group(1).strip(), a.group(2), det)


def new_award(request: dict[str, Any]) -> dict[str, Any] | None:
    """The new project the request asks a limit for, read from the action requested ("approve a new project limit of SAR 120.0m
    dedicated to <project> awarded by <employer> (letter of award dd/mm/yyyy, contract value SAR 312.0m, 24 months from dd/mm/yyyy)")."""
    act = str((request.get("action") or {}).get("text") or "")
    m = re.search(r"new\s+project\s+limit\s+of\s+SAR\s*([\d,.]+)\s*m\s+(?:dedicated\s+to|for)\s+(?:the\s+)?(.+?)\s+awarded\s+by\s+(.+?)\s*\(([^)]*)\)\s*\(([^)]*)\)", act, re.I)
    if not m:
        m = _ocr_award(request, act)  # R16 x: photos of the request (OCR drops spaces and, at times, a line of the action text)
    if not m:
        return None
    det = m.group(5)
    val = re.search(r"contract\s*value\s*(?:of\s*)?SAR\s*([\d,.]+)\s*m", det, re.I)
    ten = re.search(r"(\d+)\s*months?\s*from\s*(\d{1,2}/\d{1,2}/\d{4})", det, re.I)
    loa = re.search(r"letter\s+of\s+award\s*(\d{1,2}/\d{1,2}/\d{4})", det, re.I)
    if not val:
        return None
    start = end = None
    months = int(ten.group(1)) if ten else None
    if ten:
        dd, mm, yy = (int(x) for x in ten.group(2).split("/"))
        start = date(yy, mm, dd)
        ey, em = yy + (mm - 1 + months) // 12, (mm - 1 + months) % 12 + 1
        end = date(ey, em, min(dd, 28)) - timedelta(days=1)
    lim = next((f for f in request.get("facilities") or [] if not f.get("total") and f.get("level") == 1 and re.search(r"project", f["limit_name"], re.I)
                and (f.get("existing_mn") or 0) == 0), None)
    kids = [f for f in request.get("facilities") or [] if lim and f.get("parent") == lim["seq"]]
    return {"name": re.sub(r"\s+", " ", m.group(2)).strip(), "employer": f"{m.group(3).strip()} ({m.group(4).strip()})", "abbr": m.group(4).strip(),
            "limit_mn": float(m.group(1).replace(",", "")), "value_mn": float(val.group(1).replace(",", "")), "months": months,
            "start": start.isoformat() if start else None, "end": end.isoformat() if end else None,
            "loa": loa.group(1) if loa else "", "limit": lim, "kids": kids,
            "lg": "; ".join(f"{k['limit_name']} SAR {k['proposed_mn']:,.1f}m" for k in kids if re.search(r"guarantee|bond", k["limit_name"], re.I))}


def cash_gap(value_mn: float, months: int, gross_margin: float, advance: float = 0.10, retention: float = 0.10, lag: int = 2, delay: int = 0) -> tuple[float, int]:
    """Credit's re-performance of a new project's cash flow: work evenly over the months, costs at (1 - gross margin) paid the following
    month, the advance received at start, each certificate net of retention and advance recovery paid `lag` months after
    certification (+ `delay` months under stress). Returns (peak cumulative deficit in SAR m, month of the peak)."""
    w = value_mn / months
    flows: dict[int, float] = {}
    for t in range(1, months + 1):
        flows[t + 1] = flows.get(t + 1, 0.0) - w * (1 - gross_margin)
        flows[t + lag + delay] = flows.get(t + lag + delay, 0.0) + w * (1 - retention - advance)
    cash, low, when = value_mn * advance, 0.0, 0
    for t in range(1, months + lag + delay + 2):
        cash += flows.get(t, 0.0)
        if cash < low:
            low, when = cash, t
    return round(-low, 1), when
