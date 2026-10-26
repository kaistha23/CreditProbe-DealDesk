"""The deterministic checks of the proposal check (PLAN_R14 p, K31 point 1). No model: regular expressions over the RM's text,
figures recomputed from the RM's own tables, and the bank's data read through the bankform `source` door (Data Domains).

Each rule is `fn(C) -> list[Finding]`, C = Ctx(doc, D, as_of). A Finding is a dict:
    {check, category, severity, result, defect_type, section_key, title, claim, para, evidence, evidence_relation, evidence_key, query}
result "defect" (critical / major), "observation" (minor / info) or "pass". Categories: completeness, accuracy, consistency,
disclosure, voice, policy.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Callable

from backend.dealdesk.house_style.bankform import ctx as bctx, registry
from backend.dealdesk.house_style.bankform.ctx import num

NUMWORDS = {"no": 0, "nil": 0, "none": 0, "zero": 0, "one": 1, "a single": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
            "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12}
MONEY = re.compile(r"(?:SAR|AED|USD)\s*([\d,]+(?:\.\d+)?)\s*(bn|billion|m|mn|million)?", re.I)
SENT = re.compile(r"(?<=[.;!?])\s+(?=[A-Z(])")
VAGUE = ("satisfactory", "strong", "good", "healthy", "comfortable", "adequate", "sound", "reputed", "excellent", "well established")
MONTHS = {m: i + 1 for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"))}


def _d(x: Any) -> date | None:
    try:
        return date.fromisoformat(str(x)[:10])
    except (TypeError, ValueError):
        return None


def money(text: str) -> list[float]:
    out = []
    for m in MONEY.finditer(text):
        v = float(m.group(1).replace(",", ""))
        if (m.group(2) or "").lower() in ("bn", "billion"):
            v *= 1000
        out.append(v)
    return out


@dataclass
class Ctx:
    doc: dict[str, Any]
    D: bctx.Deal
    as_of: date
    deal: dict[str, Any] = field(default_factory=dict)

    def sec(self, key: str) -> dict[str, Any] | None:
        return next((s for s in self.doc["sections"] if s["key"] == key), None)

    def sentences(self, keys: tuple[str, ...] | None = None) -> list[tuple[str, str, int | None]]:
        """(section_key, sentence, paragraph index) over the given sections (all when None), tables included as one line per row."""
        out = []
        for s in self.doc["sections"]:
            if keys and s["key"] not in keys:
                continue
            for p in s["paras"]:
                for t in SENT.split(p["text"]):
                    if t.strip():
                        out.append((s["key"], t.strip(), p["i"]))
            for tb in s["tables"]:
                for r in tb:
                    out.append((s["key"], " | ".join(r), s.get("heading_i")))
        return out

    def find(self, pattern: str, keys: tuple[str, ...] | None = None) -> list[tuple[str, str, int | None]]:
        rx = re.compile(pattern, re.I)
        return [x for x in self.sentences(keys) if rx.search(x[1])]

    def anchor(self, key: str) -> int | None:
        s = self.sec(key)
        if s is None:
            return None
        return s.get("heading_i") if s.get("heading_i") is not None else (s["paras"][0]["i"] if s["paras"] else None)

    def money(self, x: Any) -> str:
        return self.D.money(x)


def F(check: str, category: str, severity: str, result: str, defect_type: str, section_key: str, title: str, *, claim: str = "",
      para: int | None = None, evidence: str = "", rel: str = "", key: str = "", query: str = "") -> dict[str, Any]:
    return {"check": check, "category": category, "severity": severity, "result": result, "defect_type": defect_type if result != "pass" else "",
            "section_key": section_key, "title": title, "claim": claim, "para": para, "evidence": evidence, "evidence_relation": rel,
            "evidence_key": key, "query": query if result != "pass" else ""}


def _count_in(sentence: str) -> int | None:
    s = sentence.lower()
    m = re.search(r"(\d+)\s+(?:\w+\s+){0,2}(?:returned|bounced|dishonou?red)", s)
    if m:
        return int(m.group(1))
    for w, n in sorted(NUMWORDS.items(), key=lambda x: -len(x[0])):
        if re.search(rf"\b{w}\b\s+(?:\w+\s+){{0,2}}(?:returned|bounced|dishonou?red)", s):
            return n
    if re.search(r"(?:returned|bounced|dishonou?red)[^.]*\b(?:nil|none)\b", s):
        return 0
    return None


# ------------------------------------------------------------------------------------------------------------- completeness

def r_sections(C: Ctx) -> list[dict[str, Any]]:
    out = []
    have = {s["key"]: s for s in C.doc["sections"]}
    missing = []
    for k in registry.ANATOMY:
        spec = registry.BY_KEY[k]
        if k == "projects":
            continue  # its own rule (financed projects of a contractor)
        if k == "new_project" and not any(str(r.get("status")) == "new" for r in C.D.rows("dd_project")):
            continue  # not applicable without a new project
        s = have.get(k)
        if s is None:
            missing.append(spec)
        elif s["words"] < 12 and not s["tables"] and k not in ("signatures", "header"):
            out.append(F("COMP-THIN", "completeness", "minor", "observation", "thin_section", k,
                         f"Section {spec.n} {spec.heading} is thin ({s['words']} words)", para=C.anchor(k),
                         query=f"Please complete section {spec.n} ({spec.heading}) with figures and dates."))
        else:
            out.append(F("COMP-SECTION", "completeness", "info", "pass", "", k, f"Section {spec.n} {spec.heading} present ({s['words']} words)"))
    if missing:
        names = ", ".join(f"{s.n} {s.heading}" for s in missing)
        out.append(F("COMP-SECTION", "completeness", "major", "defect", "missing_section", missing[0].key,
                     f"{len(missing)} of 20 bank-form sections missing: {names}",
                     evidence="The bank-form anatomy requires all 20 sections (PROPOSAL_ANATOMY §2); a missing section scores 0.",
                     query=f"Please add the missing sections ({names}), or state 'information not provided' with the reason in each."))
    return out


def r_projects(C: Ctx) -> list[dict[str, Any]]:
    fin = [r for r in C.D.rows("dd_project") if int(num(r.get("financed_flag")) or 0) == 1]
    if not fin:
        return []
    s = C.sec("projects")
    names = [str(r.get("project_name") or "") for r in fin]
    covered = s is not None and all(n.lower() in " ".join(p["text"] for p in s["paras"]).lower() + " ".join(" ".join(c for r in t for c in r) for t in s["tables"]).lower()
                                    for n in names if n)
    late = [r for r in fin if str(r.get("status")) == "delayed"]
    ev = "; ".join(f"{r.get('project_name')}: {r.get('work_done_pct')}% done vs {r.get('planned_pct')}% planned, "
                   f"completion revised to {bctx.d(r.get('completion_revised'))}, {int(num(r.get('pending_certs_n')) or 0)} certificates pending" for r in fin)
    if covered:
        return [F("COMP-PROJECTS", "completeness", "info", "pass", "", "projects", f"Status of the {len(fin)} financed projects given")]
    return [F("COMP-PROJECTS", "completeness", "major", "defect", "missing_project_status", "projects",
              f"Status of financed projects missing: {len(fin)} financed projects, {len(late)} delayed",
              para=C.anchor("projects"), evidence=ev + " (dd_project).", rel="dd_project", key=f"proposal_id={C.D.pid}",
              query=f"Please add the status of the {len(fin)} financed projects ({', '.join(names)}): work done vs plan, extensions of time, "
                    "certificates pending and payments received.")]


# ------------------------------------------------------------------------------------------------------------- accuracy / disclosure

def r_returned_cheques(C: Ctx) -> list[dict[str, Any]]:
    since = C.as_of - timedelta(days=365)
    rc = [r for r in C.D.rows("dd_returned_cheque") if (_d(r.get("return_date")) or date.min) > since]
    obs = {str(r.get("obligor_id")) for r in C.D.rows("dd_account_conduct") + C.D.rows("dd_returned_cheque") if r.get("obligor_id")}
    me = {str(x) for x in (C.D.get("obligor_id"), C.D.get("cif"), C.D.get("book_obligor_id")) if x}
    if len(obs) > 1 and me & obs:
        # R16 x: the deal's rows hold the borrower and its connected parties: a connected party's cheques are not the borrower's
        rc = [r for r in rc if str(r.get("obligor_id") or "") in me]
    if not C.D.rows("dd_returned_cheque") and not C.D.rows("dd_account_conduct"):
        return []
    n, amt = len(rc), sum(num(r.get("amount_mn")) or 0 for r in rc)
    dates = ", ".join(bctx.d(r.get("return_date")) for r in sorted(rc, key=lambda r: str(r.get("return_date"))))
    ev = f"{n} returned cheques in the 12 months to {bctx.d(C.as_of.isoformat())} ({C.money(amt)}" + (f": {dates}" if dates else "") + ")."
    claims = [(k, s, i, _count_in(s)) for k, s, i in C.find(r"returned|bounced|dishonou?red")]
    claims = [c for c in claims if c[3] is not None]
    if n == 0:
        return [F("ACC-RETURNED-CHEQUES", "accuracy", "info", "pass", "", "relationship", "No returned cheques in 12 months; nothing to disclose")]
    if claims and min(c[3] for c in claims) >= n:
        return [F("ACC-RETURNED-CHEQUES", "accuracy", "info", "pass", "", claims[0][0], f"Returned cheques disclosed ({n})")]
    if claims:
        k, s, i, c = min(claims, key=lambda x: x[3])
        title = f"RM claim contradicted: {n} returned cheques in 12 months; proposal says {'none' if c == 0 else c}"
        return [F("ACC-RETURNED-CHEQUES", "accuracy", "critical", "defect", "undisclosed_returned_cheques", k, title, claim=s, para=i,
                  evidence=ev, rel="dd_returned_cheque", key=f"proposal_id={C.D.pid}",
                  query=f"The account shows {n} returned cheques in the last 12 months ({dates}). Please correct the relationship section and explain each.")]
    return [F("ACC-RETURNED-CHEQUES", "disclosure", "critical", "defect", "undisclosed_returned_cheques", "relationship",
              f"Not disclosed: {n} returned cheques in 12 months", para=C.anchor("relationship"), evidence=ev, rel="dd_returned_cheque",
              key=f"proposal_id={C.D.pid}", query=f"Please disclose the {n} returned cheques of the last 12 months ({dates}) and explain each.")]


def _turnover_12m(C: Ctx) -> tuple[float, str, str] | None:
    rows = sorted(C.D.rows("dd_account_conduct"), key=lambda r: str(r.get("month")))
    rows = [r for r in rows if str(r.get("month") or "")[:7] <= C.as_of.isoformat()[:7]]
    if not rows:
        return None
    last = rows[-12:]
    tot = sum(num(r.get("credit_turnover_mn")) or 0 for r in last)
    return tot, str(last[0].get("month")), str(last[-1].get("month"))


def r_turnover(C: Ctx) -> list[dict[str, Any]]:
    t = _turnover_12m(C)
    if t is None:
        return []
    tot, m0, m1 = t
    hits = [(k, s, i, money(s)) for k, s, i in C.find(r"turnover|routed through|routing through|flows? through our")]
    hits = [h for h in hits if h[3]]
    if not hits:
        return [F("ACC-TURNOVER", "accuracy", "info", "observation", "", "relationship",
                  f"No turnover claim to test; account credit turnover {C.money(tot)} over {bctx.d(m0)}–{bctx.d(m1)}")]
    k, s, i, vals = hits[0]
    claim = max(vals)
    gap = claim / tot - 1 if tot else 0.0
    if gap > 0.15:
        return [F("ACC-TURNOVER", "accuracy", "major", "defect", "turnover_overstated", k,
                  f"RM claim contradicted: turnover {C.money(claim)} claimed, account shows {C.money(tot)} ({gap * 100:.0f}% above)", claim=s, para=i,
                  evidence=f"Credit turnover in the account {C.money(tot)} over the 12 months {bctx.d(m0)}–{bctx.d(m1)} (dd_account_conduct).",
                  rel="dd_account_conduct", key=f"proposal_id={C.D.pid};month={m0}..{m1}",
                  query=f"The proposal states turnover of {C.money(claim)}; our account shows {C.money(tot)} in the last 12 months. "
                        "Please correct it or provide the other banks' statements that support the figure.")]
    return [F("ACC-TURNOVER", "accuracy", "info", "pass", "", k, f"Turnover claim {C.money(claim)} within 15% of the account ({C.money(tot)})")]


def _latest_fin(C: Ctx) -> dict[str, Any] | None:
    rows = [r for r in C.D.rows("dd_financials_detail") if str(r.get("period_kind") or r.get("kind") or "") in ("audited", "actual", "")]
    rows = [r for r in rows if str(r.get("entity_scope") or "subject") in ("subject", "")] or rows
    return max(rows, key=lambda r: (num(r.get("year")) or 0)) if rows else None


def r_related_receivables(C: Ctx) -> list[dict[str, Any]]:
    f = _latest_fin(C)
    if not f:
        return []
    rp = num(f.get("due_from_related_mn") if f.get("due_from_related_mn") is not None else f.get("due_from_related"))
    tr = num(f.get("receivables_mn") if f.get("receivables_mn") is not None else f.get("receivables"))
    if not rp or not tr:
        return []
    yr = f.get("period_label") or f.get("year")
    ev = f"{yr}: trade receivables {C.money(tr)} and due from related parties {C.money(rp)} reported separately (dd_financials_detail)."
    for k, s, i in C.find(r"no (?:related[- ]party|intra-?group) (?:balances|receivables|exposure)"):
        return [F("ACC-RELATED-RECEIVABLES", "accuracy", "critical", "defect", "related_party_receivables_as_trade", k,
                  f"RM claim contradicted: {C.money(rp)} due from related parties; proposal says none", claim=s, para=i, evidence=ev,
                  rel="dd_financials_detail", key=f"proposal_id={C.D.pid};year={f.get('year')}",
                  query=f"The {yr} accounts show {C.money(rp)} due from related parties. Please show it separately from trade receivables.")]
    for k, s, i in C.find(r"receivable"):
        if re.search(r"related|intra-?group|sister|group compan", s, re.I):
            continue
        for v in money(s):
            if abs(v - (tr + rp)) <= 0.015 * (tr + rp):
                return [F("ACC-RELATED-RECEIVABLES", "accuracy", "critical", "defect", "related_party_receivables_as_trade", k,
                          f"Related-party receivables counted as trade: {C.money(v)} stated = {C.money(tr)} trade + {C.money(rp)} related", claim=s, para=i,
                          evidence=ev + f" Adjusted current ratio and working capital exclude the {C.money(rp)}.", rel="dd_financials_detail",
                          key=f"proposal_id={C.D.pid};year={f.get('year')}",
                          query=f"Receivables of {C.money(v)} include {C.money(rp)} due from related parties. Please split them, give the ageing of the related "
                                "balance and restate the working capital without it.")]
    return [F("ACC-RELATED-RECEIVABLES", "accuracy", "info", "pass", "", "synopsis", "Related-party receivables not mixed with trade receivables")]


def r_ubo_bureau(C: Ctx) -> list[dict[str, Any]]:
    miss = [r for r in C.D.rows("bureau_entity_report") if str(r.get("entity_kind")) == "ubo" and not int(num(r.get("provided_flag")) or 0)]
    pend = [r for r in C.D.rows("dd_document") if str(r.get("doc_type")) == "bureau_ubo" and str(r.get("status")) in ("pending", "expired")]
    if not miss and not pend:
        return []
    who = [str(r.get("entity_name")) for r in miss] or [str(r.get("entity_name")) for r in pend]
    ev = "; ".join(f"{r.get('entity_name')}: bureau report not provided ({r.get('not_provided_reason') or 'no report on file'})" for r in miss) or \
        "; ".join(f"{r.get('entity_name')}: {r.get('doc_label')} {r.get('status')}" for r in pend)
    disclosed = C.find(r"(?:UBO|" + "|".join(re.escape(w.split()[0]) for w in who) + r")[^.]*(?:not (?:yet )?(?:provided|available|obtained|received)|pending|requested|awaited)",
                       ("bureau", "exceptions", "cbrbr"))
    if disclosed:
        return [F("DISC-UBO-BUREAU", "disclosure", "info", "pass", "", disclosed[0][0], "Missing UBO bureau report disclosed")]
    claim = C.find(r"(?:UBO|shareholder|owner|" + "|".join(re.escape(w.split()[0]) for w in who) + r")[^.]*(?:clear|clean|satisfactory|no adverse|obtained)",
                   ("bureau", "cbrbr", "background"))
    k, s, i = claim[0] if claim else ("bureau", "", C.anchor("bureau"))
    return [F("DISC-UBO-BUREAU", "disclosure", "major", "defect", "ubo_bureau_missing", k or "bureau",
              f"UBO bureau report missing: {', '.join(who)}" + ("; proposal reports it as clear" if s else "; not disclosed"), claim=s, para=i,
              evidence=ev + " (bureau_entity_report, dd_document; Credit Policy 3.5: a bureau report within 30 days for the obligor and each guarantor).",
              rel="bureau_entity_report", key=f"proposal_id={C.D.pid};entity_kind=ubo",
              query=f"Please obtain the bureau report of {', '.join(who)} (dated within 30 days) or state in section 11 that it is not provided and why.")]


def _unperfected(C: Ctx) -> list[dict[str, Any]]:
    return [r for r in C.D.rows("dd_security") if "guarantee" in str(r.get("kind")) and str(r.get("perfection_status") or "").lower() in ("pending", "not_perfected", "not perfected")]


def r_unperfected_guarantee(C: Ctx) -> list[dict[str, Any]]:
    un = _unperfected(C)
    if not un:
        return []
    names = [str(r.get("provider") or "") for r in un]
    ev = "; ".join(f"{r.get('kind', '').replace('_', ' ')} of {r.get('provider')} for {C.money(r.get('amount_mn') or r.get('amount'))}: "
                   f"{str(r.get('perfection_status')).replace('_', ' ')}" + (f", deadline {bctx.d(r.get('perfection_deadline'))}" if r.get("perfection_deadline") else "")
                   for r in un) + " (dd_security; Credit Policy 7.5: all security perfected before the first drawdown)."
    allp = C.find(r"all (?:the )?(?:security|securities|guarantees|collateral)[^.]*(?:perfected|in place|executed|registered|obtained)")
    if allp:
        k, s, i = allp[0]
        return [F("DISC-GUARANTEE", "disclosure", "critical", "defect", "unperfected_guarantee", k,
                  f"RM claim contradicted: {len(un)} guarantee(s) not perfected ({', '.join(names)}); proposal says all security is perfected", claim=s, para=i,
                  evidence=ev, rel="dd_security", key=f"proposal_id={C.D.pid};security_id={','.join(str(r.get('security_id')) for r in un)}",
                  query=f"The guarantee of {', '.join(names)} is not perfected. Please state its status and the date it will be perfected (prior to limit loading).")]
    told = [x for x in C.find(r"(?:pending|not (?:yet )?perfected|to be perfected|awaited|outstanding)", ("security", "exceptions", "terms"))
            if any(n.split()[0].lower() in x[1].lower() for n in names)]
    if told:
        return [F("DISC-GUARANTEE", "disclosure", "info", "pass", "", told[0][0], "Unperfected guarantee disclosed")]
    return [F("DISC-GUARANTEE", "disclosure", "critical", "defect", "unperfected_guarantee", "security",
              f"Not disclosed: guarantee of {', '.join(names)} not perfected", para=C.anchor("security"), evidence=ev, rel="dd_security",
              key=f"proposal_id={C.D.pid}", query=f"Please disclose that the guarantee of {', '.join(names)} is not perfected and when it will be.")]


def _date_mentions(text: str, d0: date) -> bool:
    t = text.lower()
    return d0.isoformat() in t or (f"{MONTHS_ABBR[d0.month - 1]}" in t and str(d0.year) in t)


MONTHS_ABBR = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")


def r_valuation(C: Ctx) -> list[dict[str, Any]]:
    old = []
    for r in C.D.rows("dd_security"):
        vd = _d(r.get("valuation_date"))
        if vd and (C.as_of - vd).days > 365:
            old.append((r, vd))
    if not old:
        return []
    r, vd = old[0]
    months = (C.as_of.year - vd.year) * 12 + C.as_of.month - vd.month
    ev = (f"{str(r.get('kind')).replace('_', ' ')} of {r.get('provider')} valued {C.money(r.get('value_mn'))} on {bctx.d(vd.isoformat())}, "
          f"{months} months before {bctx.d(C.as_of.isoformat())} (dd_security; demo rule DR-16 asks for a land valuation not older than 12 months).")
    sents = C.find(r"valu", ("security", "exceptions", "action"))
    for k, s, i in sents:
        if re.search(r"recent|latest|updated|current|fresh|new valuation", s, re.I) and not _date_mentions(s, vd):
            return [F("DISC-VALUATION", "disclosure", "major", "defect", "stale_valuation", k,
                      f"Stale valuation not disclosed: valuation {months} months old ({bctx.d(vd.isoformat())}); proposal calls it recent", claim=s, para=i,
                      evidence=ev, rel="dd_security", key=f"proposal_id={C.D.pid};security_id={r.get('security_id')}",
                      query=f"The valuation is dated {bctx.d(vd.isoformat())} ({months} months old). Please state the date and obtain a fresh valuation before limit loading.")]
        if _date_mentions(s, vd):
            return [F("DISC-VALUATION", "disclosure", "info", "pass", "", k, f"Valuation date ({bctx.d(vd.isoformat())}) disclosed")]
    k, s, i = sents[0] if sents else ("security", "", C.anchor("security"))
    return [F("DISC-VALUATION", "disclosure", "major", "defect", "stale_valuation", k,
              f"Stale valuation not disclosed: valuation {months} months old ({bctx.d(vd.isoformat())}); no date given", claim=s, para=i, evidence=ev,
              rel="dd_security", key=f"proposal_id={C.D.pid};security_id={r.get('security_id')}",
              query=f"Please give the valuation date ({bctx.d(vd.isoformat())}) and obtain a fresh valuation before limit loading.")]


def _num_cells(row: list[str]) -> list[float | None]:
    out = []
    for c in row:
        c2 = c.replace(",", "").replace("SAR", "").replace("m", "").strip()
        try:
            out.append(float(c2))
        except ValueError:
            out.append(None)
    return out


def r_group_exposure(C: Ctx) -> list[dict[str, Any]]:
    s = C.sec("group_exposure")
    data_tot = sum(num(r.get("total_proposed_mn")) or 0 for r in C.D.rows("dd_group_exposure"))
    if s is None:
        return []
    for tb in s["tables"]:
        if len(tb) < 3 or not re.search(r"total", tb[-1][0], re.I):
            continue
        body = [_num_cells(r) for r in tb[1:-1]]
        tot = _num_cells(tb[-1])
        for j in range(1, len(tb[-1])):
            col = [r[j] for r in body if j < len(r) and r[j] is not None]
            if tot[j] is None or not col:
                continue
            ssum = sum(col)
            if abs(ssum - tot[j]) > 0.5:
                head = tb[0][j] if j < len(tb[0]) else f"column {j + 1}"
                return [F("CONS-GROUP-EXPOSURE", "consistency", "major", "defect", "group_exposure_total_wrong", "group_exposure",
                          f"Group exposure total wrong: {head} total {C.money(tot[j])}, the rows add up to {C.money(ssum)}", claim=" | ".join(tb[-1]),
                          para=C.anchor("group_exposure"),
                          evidence=f"Rows recomputed: {C.money(ssum)}; group exposure after the deal in Data Domains {C.money(data_tot)} (dd_group_exposure).",
                          rel="dd_group_exposure", key=f"proposal_id={C.D.pid}",
                          query=f"The group exposure table totals {C.money(tot[j])} but its rows add up to {C.money(ssum)} ({C.money(data_tot)} per our records). Please correct it.")]
            if data_tot and abs(tot[j] - data_tot) > 0.5 and re.search(r"propos|after", tb[0][j] if j < len(tb[0]) else "", re.I):
                return [F("CONS-GROUP-EXPOSURE", "accuracy", "major", "defect", "group_exposure_total_wrong", "group_exposure",
                          f"Group exposure total {C.money(tot[j])} differs from the bank's records ({C.money(data_tot)})", claim=" | ".join(tb[-1]),
                          para=C.anchor("group_exposure"), evidence=f"Group exposure after the deal {C.money(data_tot)} (dd_group_exposure).",
                          rel="dd_group_exposure", key=f"proposal_id={C.D.pid}",
                          query=f"Please reconcile the group exposure total ({C.money(tot[j])}) with our records ({C.money(data_tot)}).")]
        return [F("CONS-GROUP-EXPOSURE", "consistency", "info", "pass", "", "group_exposure", "Group exposure table adds up")]
    return []


def r_facilities_total(C: Ctx) -> list[dict[str, Any]]:
    s = C.sec("facilities")
    if s is None:
        return []
    for tb in s["tables"]:
        if len(tb) < 3 or not re.search(r"total", tb[-1][0], re.I):
            continue
        body = [r for r in tb[1:-1] if not r[0].startswith((" ", " ", "–", "-")) and not re.search(r"sub-?limit|^\s", r[0], re.I)]
        top = [_num_cells(r) for r in body if not re.match(r"^\s*(?:\(|·|•|of which)", r[0])]
        tot = _num_cells(tb[-1])
        for j in range(1, len(tb[-1])):
            col = [r[j] for r in top if j < len(r) and r[j] is not None]
            if tot[j] is None or not col:
                continue
            if abs(sum(col) - tot[j]) > 0.5:
                return [F("CONS-FACILITIES", "consistency", "major", "defect", "facilities_total_wrong", "facilities",
                          f"Facilities total wrong: {tb[0][j]} total {C.money(tot[j])}, the limits add up to {C.money(sum(col))}", claim=" | ".join(tb[-1]),
                          para=C.anchor("facilities"), evidence="Recomputed from the proposal's own table.",
                          query="Please correct the facilities table totals.")]
        return [F("CONS-FACILITIES", "consistency", "info", "pass", "", "facilities", "Facilities table adds up")]
    return []


def r_covenants(C: Ctx) -> list[dict[str, Any]]:
    hits = [x for x in C.find(r"covenant") if re.search(r"\b(standard|usual|normal|customary|as per (?:policy|practice)|market)\b", x[1], re.I)
            and not re.search(r"\d", x[1])]
    if not hits:
        return [F("POL-COVENANTS", "policy", "info", "pass", "", "terms", "Covenants stated with numbers")] if C.find(r"covenant") else []
    k, s, i = hits[0]
    pol = "DSCR not below 1.25x (Credit Policy 4.2), total debt / EBITDA not above 3.5x (4.3), current ratio at least 1.10x for contractors (4.4)"
    return [F("POL-COVENANTS", "policy", "major", "defect", "covenant_without_numbers", k, "Covenants 'standard' with no thresholds, test dates or cure",
              claim=s, para=i, evidence=f"The policy sets {pol}; the package must name each threshold, the test date and the statements it is tested on.",
              rel="dd_policy_clause", key="policy_id=POL-CR-01;clause=4.2,4.3,4.4",
              query="Please list each covenant with its threshold, test frequency and the statements it is tested on (e.g. DSCR ≥ 1.25x on audited accounts).")]


def r_sales_terms(C: Ctx) -> list[dict[str, Any]]:
    hits = [x for x in C.find(r"\bsales\b[^.]*\b(?:terms|basis|credit|payment)\b|\bsold\b[^.]*\bterms\b") if not re.search(r"\d", x[1])]
    if not hits:
        return [F("VOICE-SALES-TERMS", "voice", "info", "pass", "", "background", "Sales terms stated with figures")] if C.find(r"sales terms|payment terms") else []
    k, s, i = hits[0]
    bp = [r for r in C.D.rows("dd_business_profile") if str(r.get("item_kind")) == "sales_terms"]
    ev = (str(bp[0].get("text")) + " (dd_business_profile).") if bp else "Anatomy §2.7: sales terms with the share of PDC / LC / open account and the days."
    return [F("VOICE-SALES-TERMS", "voice", "major", "defect", "vague_sales_terms", k, "Sales terms vague: no days, shares or retention given", claim=s, para=i,
              evidence=ev, rel="dd_business_profile" if bp else "", key=f"proposal_id={C.D.pid};item_kind=sales_terms" if bp else "",
              query="Please state the sales terms with numbers: certificate frequency, days to payment, retention and advance, and the share of each.")]


def r_prior_conditions(C: Ctx) -> list[dict[str, Any]]:
    def _nc(v: Any) -> bool:
        return str(v or "").replace("_", " ").lower() in ("not complied", "breached")
    nc = [r for r in C.D.rows("dd_condition") if _nc(r.get("status"))]
    nc += [r for r in C.D.rows("dd_tnc") if _nc(r.get("existing_status")) and not any(
        str(r.get("text") or "")[:40].lower() == str(x.get("text") or "")[:40].lower() for x in nc)]
    if not nc:
        return []
    refs = sorted({str(r.get("prior_committee_ref") or r.get("committee_ref") or "") for r in nc if r.get("prior_committee_ref") or r.get("committee_ref")})
    ev = "; ".join(f"{r.get('text')} — not complied" + (f" (measured {bctx.d(r.get('measured_at'))})" if r.get("measured_at") else "") for r in nc) + \
        f" (dd_condition{', ' + ', '.join(refs) if refs else ''})."
    claims = [x for x in C.find(r"condition") if re.search(r"complied|fulfilled|satisfied|\bmet\b|adhered", x[1], re.I)
              and not re.search(r"not (?:been )?(?:complied|fulfilled|satisfied|met)|non-?complian|outstanding|pending|partly", x[1], re.I)]
    told = C.find(r"not (?:been )?(?:complied|fulfilled|met)|non-?complian")
    if claims:
        k, s, i = claims[0]
        return [F("ACC-PRIOR-CONDITIONS", "accuracy", "critical", "defect", "prior_condition_misstated", k,
                  f"RM claim contradicted: {len(nc)} condition(s) of {', '.join(refs) or 'the last approval'} not complied; proposal says complied",
                  claim=s, para=i, evidence=ev, rel="dd_condition", key=f"proposal_id={C.D.pid};status=not_complied",
                  query=f"{len(nc)} condition(s) of {', '.join(refs) or 'the last approval'} are not complied: " +
                        "; ".join(str(r.get("text")) for r in nc) + ". Please correct the status and give the reason and a date.")]
    if told:
        return [F("ACC-PRIOR-CONDITIONS", "accuracy", "info", "pass", "", told[0][0], "Status of existing conditions disclosed")]
    return [F("ACC-PRIOR-CONDITIONS", "disclosure", "critical", "defect", "prior_condition_misstated", "terms",
              f"Not disclosed: {len(nc)} condition(s) of {', '.join(refs) or 'the last approval'} not complied", para=C.anchor("terms"), evidence=ev,
              rel="dd_condition", key=f"proposal_id={C.D.pid};status=not_complied",
              query="Please add the status of the existing conditions (anatomy §2.5), with the reason and a date for each one not complied.")]


def _pricing(C: Ctx) -> dict[str, Any] | None:
    """Lifetime RAROC of the deal as proposed vs the hurdle: session e's economics engine when present, else the Deal Desk engine
    on the proposal record (deterministic)."""
    import json
    pj = C.deal.get("proposal_json")
    if isinstance(pj, str) and pj:
        try:
            pj = json.loads(pj)
        except ValueError:
            pj = None
    if not isinstance(pj, dict) or not pj.get("ask"):
        return None
    try:
        from backend.dealdesk import engine
        a = engine.analyse(pj)
        m = a["metrics"]
        return {"raroc": m["lifetime_raroc"] * 100, "hurdle": m["hurdle"] * 100, "margin_bps": pj["ask"].get("margin_bps"),
                "source": "Deal Desk engine (engine.analyse on dd_deal.proposal_json)"}
    except Exception:  # noqa: BLE001 - not priceable: no pricing check
        return None


def r_pricing(C: Ctx) -> list[dict[str, Any]]:
    p = _pricing(C)
    if p is None or p["raroc"] >= p["hurdle"]:
        return [] if p is None else [F("DISC-PRICING", "policy", "info", "pass", "", "exceptions",
                                       f"Pricing clears the hurdle: RAROC {p['raroc']:.1f}% vs {p['hurdle']:.1f}%")]
    told = C.find(r"(?:pricing|raroc|hurdle|margin|spread)[^.]*(?:exception|below|deviation|waiver)|(?:exception|deviation)[^.]*(?:pricing|raroc|hurdle|margin)",
                  ("exceptions", "recommendation", "action", "facilities"))
    if told:
        return [F("DISC-PRICING", "disclosure", "info", "pass", "", told[0][0], "Pricing exception disclosed")]
    exc = C.find(r"no (?:policy )?(?:exceptions?|deviations?)", ("exceptions",))
    k, s, i = exc[0] if exc else ("exceptions", "", C.anchor("exceptions"))
    return [F("DISC-PRICING", "disclosure", "major", "defect", "pricing_exception_undisclosed", "exceptions",
              f"Pricing exception not disclosed: RAROC {p['raroc']:.1f}% vs {p['hurdle']:.1f}% hurdle at {p['margin_bps']:g} bps", claim=s, para=i,
              evidence=f"Lifetime RAROC {p['raroc']:.1f}% against a {p['hurdle']:.1f}% hurdle on the terms proposed ({p['source']}; Credit Policy 9.1–9.2).",
              rel="dd_deal", key=f"proposal_id={C.D.pid}",
              query=f"At {p['margin_bps']:g} bps the deal returns {p['raroc']:.1f}% against the {p['hurdle']:.1f}% hurdle. Please list it as a pricing exception "
                    "with business's reason, or reprice.")]


def r_vague(C: Ctx) -> list[dict[str, Any]]:
    out = []
    for k, s, i in C.sentences():
        if k in ("header", "signatures", "facilities") or re.search(r"\d", s) or "|" in s:
            continue
        w = next((v for v in VAGUE if re.search(rf"\b{v}\b", s, re.I)), None)
        if w and not re.search(r"covenant|sales", s, re.I):
            out.append(F("VOICE-VAGUE", "voice", "minor", "observation", "vague_claim", k, f"Vague claim with no figure or date ('{w}')", claim=s, para=i,
                         query=f"Please replace '{w}' with the figure, date and source behind it."))
    return out[:8]


RULES: list[Callable[[Ctx], list[dict[str, Any]]]] = [
    r_sections, r_projects, r_returned_cheques, r_turnover, r_related_receivables, r_ubo_bureau, r_unperfected_guarantee, r_valuation,
    r_group_exposure, r_facilities_total, r_covenants, r_sales_terms, r_prior_conditions, r_pricing, r_vague]

# Deal Desk edition, Round P: thresholds an approved regulation or policy put in force (Policy Docs), the clause cited.
RULES.append(__import__("backend.dealdesk.rulebook.hook", fromlist=["r_rulebook"]).r_rulebook)
