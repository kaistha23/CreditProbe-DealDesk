"""Deterministic writers of the business request (N4): the "Action requested" voice of the bank-form proposal
(docs/v5/house_style/PROPOSAL_ANATOMY.md §2 items 1-8 and 14, plus the RM's justification), from the customer file, the RM's
ask and the RM's notes.

Voice: every sentence carries a fact, a number and a date or an attribution; prior year in brackets; shares, not only amounts;
the RM's notes in his own voice ("as per RM" only where a record contradicts a note); "not provided" when a document is missing. Every figure printed goes through W.m / W.pc /
W.n, which record it with its source (document and id, or Data Domains relation and row): paper["figures"] is the trace.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from backend.dealdesk.house_style.bankform import source as S
from backend.dealdesk.house_style.bankform.blocks import BL, BOX, H, KV, NL, P, SIGN, T
from backend.dealdesk.rm_request import inputs as I

LOWER_OK = {"the", "a", "an", "business", "our", "we", "they", "this", "these", "customer", "company", "group", "owner", "owners", "management",
            "pipeline", "expansion", "sales", "revenue", "collections", "deposits", "there", "it", "its", "new", "strong", "good", "both", "all", "no",
            "orders", "demand", "relationship", "family", "second", "plans", "plan"}
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
PRICING_NOTE = re.compile(r"SAIBOR|SIBOR|\bmargin\b|pricing|\bprice\b|commission|\bfee\b|bps|basis points", re.I)
ACTION_WORD = {"renew": "renew", "increase": "increase", "reduce": "reduce", "new": "approve a new", "takeover": "take over",
               "cancel": "cancel"}


def dt(x: Any) -> str:
    d = I._d(x)  # noqa: SLF001
    return f"{d.day:02d} {MONTHS[d.month - 1]} {d.year}" if d else (str(x) if x else "")


def mon(x: Any) -> str:
    """'Oct 2025' from '2025-10' or a date."""
    s = str(x or "")
    try:
        return f"{MONTHS[int(s[5:7]) - 1]} {s[:4]}"
    except (ValueError, IndexError):
        return s


def num(x: Any) -> float | None:
    try:
        return None if x in (None, "") else float(str(x).replace(",", ""))
    except (TypeError, ValueError):
        return None


def mn(x: Any) -> float | None:
    """SAR units (documents) -> millions."""
    v = num(x)
    return None if v is None else v / 1e6


def cut(t: Any, n: int = 160) -> str:
    """Text for a table cell: whole, or cut at the last ';' or '.' before n characters (never mid-word)."""
    t = str(t or "").strip()
    if len(t) <= n:
        return t
    k = max(t.rfind("; ", 0, n), t.rfind(". ", 0, n))
    if k > 20:
        return t[:k].rstrip(";. ") + "."
    k = t.rfind(" ", 0, n)
    return t[:k if k > 20 else n].rstrip(",;. ") + "…"


def subj(w: "W", x: Any) -> str:
    """A checklist subject slug printed as in the documents: 'fy2024' -> 'FY2024', 'fahad_saleh_al_mutlaq' -> the document's full name."""
    t = str(x or "").strip()
    if not t:
        return ""
    if re.fullmatch(r"(fy|\d{1,2}m)\d{4}", t, re.I):
        return t.upper()
    slug = lambda v: re.sub(r"[^a-z0-9]+", "_", str(v or "").lower()).strip("_")  # noqa: E731
    for d in w.cf.get("documents", []):
        f = d.get("fields") or {}
        nm = f.get("full_name") or f.get("bank_name")
        if nm and (d.get("subject") == t or slug(nm) == slug(t)):
            return str(nm)
    for d in w.docs("articles_of_association"):
        for sh in ((d.get("fields") or {}).get("shareholders") or []):
            if isinstance(sh, dict) and slug(sh.get("name")) == slug(t):
                return str(sh.get("name"))
    return t.replace("_", " ").title() if "_" in t or t.islower() else t


def sar(v_mn: float) -> str:
    return f"SAR {v_mn * 1e6:,.0f}"


def src_row(r: dict[str, Any] | None) -> str:
    return S.label((r or {}).get("_src")) if r else ""


class W:
    """The writing context: customer file, ask, notes, and the figure register (the trace)."""

    def __init__(self, cf: dict[str, Any], ask: dict[str, Any], notes: dict[str, Any], rm: str = "", written: str = I.AS_OF):
        self.cf, self.ask, self.notes, self.rm, self.written = cf, ask, notes, rm or "Relationship manager", written
        self.c = cf["customer"]
        self.bank = cf.get("bank") or {}
        self.figures: list[dict[str, Any]] = []
        self.section = ""
        self.used_notes: set[int] = set()
        self.ccy = "SAR"

    # ---- figures with their source
    def _rec(self, label: str, text: str, value: Any, src: str) -> str:
        self.figures.append({"section": self.section, "label": label, "value": value, "text": text, "source": src or "not traced"})
        return text

    def m(self, v_mn: Any, src: str, label: str = "", dp: int = 1, sign: bool = False) -> str:
        v = num(v_mn)
        if v is None:
            return "not provided"
        t = f"{'+' if sign and v > 0 else ''}{self.ccy} {v:,.{dp}f}m" if abs(v) < 1000 else f"{self.ccy} {v / 1000:,.2f}bn"
        return self._rec(label, t, round(v, 4), src)

    def cell(self, v_mn: Any, src: str, label: str = "", dp: int = 1) -> str:
        v = num(v_mn)
        if v is None:
            return "–"
        return self._rec(label, f"{v:,.{dp}f}", round(v, 4), src)

    def pc(self, v: Any, src: str, label: str = "", dp: int = 1, sign: bool = False) -> str:
        x = num(v)
        if x is None:
            return "n/a"
        return self._rec(label, f"{'+' if sign and x > 0 else ''}{x:,.{dp}f}%", round(x, 4), src)

    def x(self, v: Any, src: str, label: str = "", dp: int = 2) -> str:
        x = num(v)
        if x is None:
            return "n/a"
        return self._rec(label, f"{x:,.{dp}f}x", round(x, 4), src)

    def n(self, v: Any, src: str, label: str = "") -> str:
        x = num(v)
        if x is None:
            return "n/a"
        return self._rec(label, f"{x:,.0f}", x, src)

    # ---- document access
    def doc(self, t: str) -> dict[str, Any] | None:
        return I.doc(self.cf, t)

    def docs(self, t: str) -> list[dict[str, Any]]:
        return I.docs(self.cf, t)

    def f(self, t: str, name: str, default: Any = None) -> tuple[Any, str]:
        return I.field(self.cf, t, name, default)

    def rows(self, rel: str) -> list[dict[str, Any]]:
        return self.bank.get(rel) or []

    @property
    def contradicted(self) -> set[int]:
        """The notes that a record contradicts (note_checks, run on a scratch context so the trace is not doubled): they are disclosed,
        never printed as a business point."""
        if getattr(self, "_contra", None) is None:
            tmp = W(self.cf, self.ask, self.notes, rm=self.rm, written=self.written)
            nc = note_checks(tmp)
            self._contra = {i for i, ln in enumerate(self.notes.get("lines", [])) if any(f'"{ln["text"]}"' in x and re.search(r"contradicted|to be corrected", x) for x in nc)}
        return self._contra

    # ---- RM notes by topic (each note is printed once, in the first section that takes its topic)
    def notes_for(self, *topics: str) -> list[str]:
        out = []
        for i, ln in enumerate(self.notes.get("lines", [])):
            if i in self.used_notes or ln["topic"] not in topics:
                continue
            if i in self.contradicted:
                self.used_notes.add(i)
                continue
            if topics and topics[0] == "justification" and re.match(r"(met|spoke|called|visited|meeting)\b", ln["text"].strip(), re.I) \
                    and not re.search(r"\b(agreed|confirmed|committed|accepted|approved|signed|will)\b", ln["text"], re.I):
                self.used_notes.add(i)  # a meeting with no figure and no decision is not a business point
                continue
            self.used_notes.add(i)
            for fg in ln.get("figures") or []:
                self._rec("RM note figure", fg, fg, "RM notes (typed in the chat box), as per RM")
            t = ln["text"].strip()
            # the business request is the RM's own voice: the note is a plain statement ("as per RM" is credit's attribution and is
            # kept only where a record contradicts the note, note_checks)
            t = (t[0].upper() + t[1:]) if t else t
            out.append(t if t.endswith((".", "!", "?")) else t + ".")
        return out

    def pricing_notes(self) -> list[str]:
        """The RM's notes on pricing (SAIBOR, margin, commission, fee): they belong with the facility particulars, not the T&Cs."""
        out = []
        for i, ln in enumerate(self.notes.get("lines", [])):
            if i in self.used_notes or ln["topic"] not in ("terms", "justification", "financials") or not PRICING_NOTE.search(ln["text"]):
                continue
            self.used_notes.add(i)
            for fg in ln.get("figures") or []:
                self._rec("RM note figure", fg, fg, "RM notes (typed in the chat box), as per RM")
            t = ln["text"].strip()
            out.append((t[0].upper() + t[1:]).rstrip("."))
        return out

    @property
    def ask_src(self) -> str:
        return f"RM's ask typed in the chat box ({dt(self.written)})"


# ================================================================== financial periods

def periods(w: W) -> list[dict[str, Any]]:
    """[{label, kind, months, f: fields (SAR units), src}] audited (oldest first) then in-house."""
    out = []
    for d in w.docs("audited_fs"):
        f = d.get("fields") or {}
        y = str(f.get("fiscal_year") or d.get("period_to") or d.get("subject") or "")
        yy = (I._d(y).year if I._d(y) else re.sub(r"\D", "", y)[:4])  # noqa: SLF001
        out.append({"label": f"FY{yy}", "kind": "audited", "months": 12, "f": f, "src": d["source"], "end": d.get("period_to") or y})
    for d in w.docs("inhouse_fs"):
        f = d.get("fields") or {}
        a, b = I._d(d.get("period_from") or f.get("period_from")), I._d(d.get("period_to") or f.get("period_to"))  # noqa: SLF001
        months = ((b.year - a.year) * 12 + b.month - a.month + 1) if a and b else 12
        out.append({"label": f"{months}M{b.year}" if b else "Interim", "kind": "in-house", "months": months, "f": f, "src": d["source"],
                    "end": str(b or "")})
    if not out:  # an existing customer whose statements the Bank already holds
        for r in sorted(w.rows("dd_financials_detail"), key=lambda r: str(r.get("period_end") or "")):
            if str(r.get("entity_scope") or "subject") not in ("subject", "", "None"):
                continue
            f = {k[:-3]: (num(v) * 1e6 if num(v) is not None else None) for k, v in r.items() if k.endswith("_mn")}
            f["trade_receivables"] = f.get("receivables")
            f["total_equity"] = f.get("net_worth")
            f["auditor"], f["opinion"] = r.get("auditor"), r.get("opinion")
            out.append({"label": str(r.get("period_label")), "kind": str(r.get("period_kind") or ""), "months": int(num(r.get("months")) or 12),
                        "f": f, "src": src_row(r), "end": r.get("period_end")})
    return out


def ratios(f: dict[str, Any], months: int = 12) -> dict[str, float | None]:
    """Ratios of one period. EBITDA only when the statement shows D&A (never operating profit standing in for it); Debt / EBITDA on
    an annualised EBITDA for an interim period; bank debt = short-term + current portion of long-term + long-term borrowings."""
    g = lambda k: num(f.get(k))  # noqa: E731
    rev, gp, op, npf = g("revenue"), g("gross_profit"), g("operating_profit"), g("net_profit")
    dep = g("depreciation")
    st_, cp, lt = g("short_term_borrowings"), g("current_portion_ltd"), g("long_term_borrowings")
    debt = sum(x for x in (st_, cp, lt) if x) or None
    eq, tl, ca, cl = g("total_equity"), g("total_liabilities"), g("current_assets"), g("current_liabilities")
    ebitda = (op + dep) if op is not None and dep is not None else None
    ann = ebitda * 12 / months if ebitda and months else ebitda
    return {"gpm": gp / rev * 100 if rev and gp is not None else None, "npm": npf / rev * 100 if rev and npf is not None else None,
            "opm": op / rev * 100 if rev and op is not None else None, "ebitda": ebitda, "debt": debt,
            "debt_st": (sum(x for x in (st_, cp) if x) or None) if st_ is not None or cp is not None else None, "debt_lt": lt,
            "cr": ca / cl if ca and cl else None, "lev": tl / eq if tl and eq else None, "gear": debt / eq if debt and eq else None,
            "debt_ebitda": debt / ann if debt and ann else None, "roe": npf / eq * 100 if npf is not None and eq else None,
            "wc": (ca - cl) if ca is not None and cl is not None else None,
            "dso": (g("trade_receivables") or 0) / rev * 365 if rev and g("trade_receivables") is not None else None}


# ================================================================== facilities: existing + ask

def facility_rows(w: W) -> list[dict[str, Any]]:
    """One row per facility: existing (the Bank's dd_facility_limit), outstanding, proposed (the ask), change, particulars."""
    ex = top_limits(w.rows("dd_facility_limit"))
    ids = {r.get("limit_id") for r in ex}
    subs = [r for r in w.rows("dd_facility_limit") if r.get("parent_limit_id") in ids and r not in ex]
    from backend.dealdesk.rm_request.ask import facility_of
    rows: list[dict[str, Any]] = []
    for r in sorted(ex, key=lambda r: num(r.get("seq")) or 0):
        lab = str(r.get("limit_name") or r.get("product_code") or "Facility")
        rows.append({"facility": lab, "canon": (facility_of(lab) or (lab,))[0], "existing": num(r.get("existing_mn")), "outstanding": num(r.get("outstanding_mn")),
                     "proposed": num(r.get("existing_mn")), "cash_margin": num(r.get("cash_margin_pct")), "row": r, "src": src_row(r), "ask": None,
                     "funded": str(r.get("funded_flag", "")).lower() in ("1", "true", "y", "yes", "funded"),
                     "subs": [s for s in subs if s.get("parent_limit_id") == r.get("limit_id")]})
    for it in w.ask.get("items", []):
        from backend.dealdesk.rm_request.ask import same_facility
        hit = next((x for x in rows if x["ask"] is None and (x["canon"] == it["facility"] or x["facility"].lower() == it["facility"].lower())), None) \
            or next((x for x in rows if x["ask"] is None and it.get("existing_limit") is not None and same_facility(x["facility"], it["facility"])), None)
        if hit is None and it["action"] in ("renew", "increase", "reduce", "cancel") and len(rows) == 1 and it["facility"].startswith("Facility"):
            hit = rows[0]
        if hit is not None:
            hit["ask"] = it
            hit["proposed"] = 0.0 if it["action"] == "cancel" else (it.get("amount") if it.get("amount") is not None else hit["existing"])
        else:
            rows.append({"facility": it["facility"], "canon": it["facility"], "existing": None, "outstanding": None, "proposed": it.get("amount"),
                         "cash_margin": None, "row": None, "src": "", "ask": it, "funded": it.get("kind") in ("funded", "combined"), "subs": []})
    return rows


def top_limits(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The limits a request names: level 1 under a level-0 total (R12 facility tree), else the rows that are not totals."""
    lv = lambda r: int(num(r.get("level")) if num(r.get("level")) is not None else 1)  # noqa: E731
    one = [r for r in rows if lv(r) == 1]
    if one:
        return one
    return [r for r in rows if not str(r.get("limit_name") or "").lower().startswith("total") and lv(r) <= 1]


def particulars(w: W, r: dict[str, Any]) -> str:
    it, row = r.get("ask") or {}, r.get("row") or {}
    bits = []
    if it.get("margin_pct") is not None:
        bits.append(f"{it.get('benchmark') or 'SAIBOR'} + {it['margin_pct']:.2f}% p.a. (as per RM)")
    elif row.get("spread_pct") not in (None, ""):
        bits.append(f"{row.get('benchmark') or 'SAIBOR'} + {num(row['spread_pct']):.2f}% p.a." + (f", floor {num(row['floor_pct']):.2f}%" if num(row.get("floor_pct")) else ""))
    if it.get("commission_pct") is not None:
        bits.append(f"commission {it['commission_pct']:.2f}% {it.get('commission_basis') or 'p.a.'} (as per RM)")
    elif num(row.get("commission_pct_pa")):
        c_ = num(row["commission_pct_pa"])
        basis = row.get("commission_basis") or ("p.q." if re.search(rf"{c_:.2f}%\s*(?:per quarter|p\.q\.)", str(row.get("particulars") or ""), re.I) else "p.a.")
        bits.append(f"commission {c_:.2f}% {basis}")
    if it.get("tenor_months"):
        tm = it["tenor_months"]
        bits.append(f"tenor {tm // 12} years" if tm >= 24 and tm % 12 == 0 else f"tenor {tm} months")
    elif row.get("tenor_text"):
        bits.append(str(row["tenor_text"]))
    if row.get("repayment_text"):
        bits.append(str(row["repayment_text"]))
    if it.get("purpose"):
        bits.append(f"purpose: {it['purpose']}")
    if it.get("one_off"):
        bits.append("one-off")
    if not it and r.get("row") is not None:
        bits.append("not addressed in the ask: shown at the existing limit")
    elif it and it.get("action") in ("new", "takeover") and it.get("margin_pct") is None and it.get("commission_pct") is None:
        d = default_pricing(w, r)
        bits.append(d or "pricing not stated in the ask")
    if row.get("particulars") and len(bits) < 4 and not re.search(r"\b(reduced|increased|new|cancel+ed|proposed)\b", str(row["particulars"]), re.I) \
            and not (num(row.get("commission_pct_pa")) and re.search(rf"^\s*{num(row['commission_pct_pa']):.2f}%", str(row["particulars"]))):
        bits.append(str(row["particulars"]))
    return "; ".join(bits) or "–"


SME_GRID = {"funded": ("3M SAIBOR + 3.00% p.a., floor 7.00%", "12 months"), "lg": ("commission 1.00% p.a.", "up to 24 months"),
            "lc": ("commission 0.30% p.q.", "usance up to 90 days")}


def _kind_of(r: dict[str, Any]) -> str:
    f = f"{r.get('facility')} {r.get('canon')}".lower()
    return "lg" if "guarantee" in f or "bond" in f else "lc" if "letter" in f and "credit" in f else "funded"


def default_pricing(w: W, r: dict[str, Any]) -> str:
    """Pricing when the ask is silent: for a takeover, the incumbent's terms for the same product (its offer letter); for a small
    new-to-bank customer, the SME price grid. Both marked as proposed by business."""
    tb = w.ask.get("takeover_bank")
    k = _kind_of(r)
    if tb:
        for d in w.docs("other_bank_offer_letter"):
            f = d.get("fields") or {}
            if tb.lower() not in str(f.get("bank_name") or "").lower():
                continue
            for x in f.get("facilities") or []:
                if isinstance(x, dict) and _kind_of({"facility": x.get("facility")}) == k and (k != "funded" or "murabaha" in str(x.get("facility")).lower() == "murabaha" in r["facility"].lower()):
                    pr = str(x.get("pricing") or "").replace("per quarter", "p.q.")
                    if pr:
                        w._rec(f"{r['facility']} incumbent pricing", pr, pr, d["source"])  # noqa: SLF001
                        return f"{'commission ' if k != 'funded' else ''}{pr} (proposed, as per {f.get('bank_name')} terms)"
    tp = _total(facility_rows_cache(w), "proposed") or 0
    if not w.c.get("existing") and tp <= 25:
        pr, tn = SME_GRID[k]
        w._rec(f"{r['facility']} SME grid pricing", pr, pr, "the Bank's SME price grid (proposed by business)")  # noqa: SLF001
        return f"{pr}; {tn} (proposed, SME price grid)"
    return ""


def facility_rows_cache(w: W) -> list[dict[str, Any]]:
    if getattr(w, "_rows", None) is None:
        w._rows = facility_rows(w)  # noqa: SLF001
    return w._rows  # noqa: SLF001


def fee_text(w: W, rows: list[dict[str, Any]]) -> str:
    """Study and documentation fee: the ask's, else 0.50% of new term loans, else 0.20% of the new money; SAR 20,000 minimum."""
    if w.ask.get("fee"):
        return str(w.ask["fee"])
    term = sum(r["proposed"] or 0 for r in rows if r.get("ask") and (r["ask"].get("action") in ("new", "takeover")) and "term" in r["facility"].lower())
    te, tp = _total(rows, "existing") or 0, _total(rows, "proposed") or 0
    if term:
        fee, base = term * 0.005, f"0.50% of the term finance of {w.m(term, w.ask_src, 'fee base term')}"
    elif tp > te:
        fee, base = (tp - te) * 0.002, f"0.20% of the {'increase' if te else 'new limits'} of {w.m(tp - te, w.ask_src, 'fee base new money')}"
    elif tp:
        fee, base = tp * 0.002, f"0.20% of the renewed limits of {w.m(tp, w.ask_src, 'fee base renewal')}"
    else:
        return "not applicable"
    floor = fee < 0.02
    fee = max(fee, 0.02)
    w._rec("study and documentation fee", sar(fee), round(fee, 4), "the Bank's fee tariff applied to the ask (proposed by business)")  # noqa: SLF001
    return f"{sar(fee)} ({base}{', minimum SAR 20,000' if floor else ''}), proposed by business"


# ================================================================== sections

def w_header(w: W) -> tuple[list[dict[str, Any]], list[str]]:
    c = w.c
    acts = {i["action"] for i in w.ask.get("items", [])}
    accts = w.rows("dd_customer_account")
    opened = min((str(a.get("opened") or a.get("opened_date") or "") for a in accts if a.get("opened") or a.get("opened_date")), default="")
    tick = lambda on, lab: f"{'☒' if on else '☐'} {lab}"  # noqa: E731
    kind = "  ".join([tick(not c.get("existing"), "New"), tick(bool(c.get("existing")), "Existing"), tick("renew" in acts, "Renewal"),
                      tick("increase" in acts or ("new" in acts and c.get("existing")), "Additional"), tick("takeover" in acts or bool(w.ask.get("takeover_bank")), "Takeover"),
                      tick("reduce" in acts or "cancel" in acts, "Amendment")])
    rv = I._d(w.written)  # noqa: SLF001
    review = dt(date(rv.year + 1, rv.month, min(rv.day, 28))) if rv else ""
    deal = (w.rows("dd_deal") or [{}])[0]
    rating = (f"{deal['rating_existing']} (existing)" if deal.get("rating_existing") else "") or str(((w.cf.get("intake") or {}).get("bank") or {}).get("rating") or "") \
        or next((str(r.get("text")) for r in w.rows("dd_reference") if "rating" in str(r.get("kind", "")).lower()), "")
    if deal.get("rating_existing"):
        w._rec("existing rating", str(deal["rating_existing"]), str(deal["rating_existing"]), src_row(deal))  # noqa: SLF001
    opened = opened or str(deal.get("account_opened_date") or "")
    dmy = lambda x: (lambda d: f"{d.day:02d}/{d.month:02d}/{d.year}" if d else "")(I._d(x))  # noqa: E731, SLF001
    conn = [e for e in w.rows("b360_entity") if str(e.get("role") or "").lower() in ("sister", "associate", "connected", "related")]
    if str(deal.get("related_party_flag") or "") in ("1", "True", "true") or deal.get("related_party_cif"):
        rp = f"Yes · CIF {deal.get('related_party_cif')}" if deal.get("related_party_cif") else "Yes"
        w._rec("related party flag", rp, rp, src_row(deal))  # noqa: SLF001
    elif conn:
        rp = "Yes · " + ", ".join(f"{e.get('entity_name')}{(' (CIF ' + str(e['borrower_id']) + ')') if e.get('borrower_id') else ''}" for e in conn[:3])
        w._rec("connected parties", rp, rp, src_row(conn[0]))  # noqa: SLF001
    else:
        rp = "No connected party in the Bank's data" if c.get("existing") else "None declared (new to bank)"
    coll = str(deal.get("collateral_code") or "") or ("RE — Real-estate mortgage" if w.rows("dd_security") and any("mortgage" in str(r.get("kind") or "").lower() for r in w.rows("dd_security"))
                                                       else "PG — Personal guarantee" if not w.rows("dd_security") and w.docs("articles_of_association") else "–")
    extra = [("Related / connected party", rp), ("AO / RO", " / ".join(x for x in (str(deal.get("ao") or ""), str(deal.get("ro") or "")) if x) or w.rm),
             ("Purpose code", str(deal.get("purpose_code") or "–")), ("Industry code", str(deal.get("industry_code") or "–")), ("Collateral code", coll),
             ("Proposed rating", str(deal.get("rating_proposed") or "to be assigned by Credit"))]
    for k_, v_ in extra[2:5]:
        if v_ not in ("–",) and deal.get(k_.lower().replace(" ", "_")):
            w._rec(k_, v_, v_, src_row(deal))  # noqa: SLF001
    pairs = [("Unit", f"Corporate Banking · {c.get('city') or '–'}"), ("Customer", c.get("name", "")), ("CIF", c.get("cif") or "New to bank"),
             ("CR number", c.get("cr_number") or "–"), ("Group", f"{c.get('group_name')} ({c.get('group_id')})" if c.get("group_name") else "–"),
             ("Account opened", dt(opened) or ("–" if c.get("existing") else "new to bank")),
             ("Industry", " · ".join(x for x in (c.get("sector"), c.get("sub_sector")) if x) or "–"), ("Request", kind),
             ("Rating", rating or ("as per the Bank's rating on file" if c.get("existing") else "to be rated (new to bank)")),
             ("RM", w.rm), ("Date", dmy(w.written)), ("Review date", dmy(date(rv.year + 1, rv.month, min(rv.day, 28))) if rv else review),
             ("Reference", f"{c.get('proposal_id') or c.get('key')}-BR")] + extra
    pairs = [(k_, (dmy(opened) if k_ == "Account opened" and opened else v_)) for k_, v_ in pairs]
    return [KV(pairs, cols=3)], []


def _total(rows: list[dict[str, Any]], k: str) -> float | None:
    v = [r[k] for r in rows if r.get(k) is not None]
    return sum(v) if v else None


def w_action(w: W) -> tuple[list[dict[str, Any]], list[str]]:
    rows = facility_rows(w)
    items = w.ask.get("items", [])
    gaps = []
    if not items:
        return [P("No ask has been typed yet: type the ask in the chat box (for example \"renew the facilities and increase the overdraft "
                  "to SAR 60m\") and CreditProbe writes this page.")], ["ask not typed"]
    parts = []
    for i, it in enumerate(items, start=1):
        a = it["action"]
        lab = it["facility"]
        amt = it.get("amount")
        if a == "increase" and it.get("from_amount") is not None and amt is not None:
            s = (f"increase the {lab} from {w.m(it['from_amount'], 'Data Domains · dd_facility_limit' if it.get('existing_limit') is not None else w.ask_src, f'{lab} existing')} to {w.m(amt, w.ask_src, f'{lab} proposed')} "
                 f"({w.m(amt - it['from_amount'], w.ask_src, f'{lab} change', sign=True)})")
        elif a == "reduce" and it.get("from_amount") is not None and amt is not None:
            s = f"reduce the {lab} from {w.m(it['from_amount'], w.ask_src, f'{lab} existing')} to {w.m(amt, w.ask_src, f'{lab} proposed')}"
        elif a == "renew":
            s = f"renew the {lab}" + (f" of {w.m(amt, w.ask_src, f'{lab} renewed')}" if amt is not None else "")
        elif a == "takeover":
            s = f"take over the customer's facilities with other banks" + (f" of {w.m(amt, w.ask_src, 'takeover amount')}" if amt is not None else "")
        elif a == "cancel":
            s = f"cancel the {lab}"
        else:
            s = f"approve a new {'one-off ' if it.get('one_off') else ''}{lab}" + (f" of {w.m(amt, w.ask_src, f'{lab} new')}" if amt is not None else " (amount not stated in the ask)")
        if it.get("tenor_months") and a in ("new", "takeover"):
            s += f" for {it['tenor_months']} months"
        parts.append(f"({_roman(i)}) {s}")
    te, tp = _total(rows, "existing"), _total(rows, "proposed")
    refs = sorted([r for r in w.rows("dd_reference") if r.get("ref_no") and re.search(r"committee|decision|approv|limit history|renewal",
                                                                                      str(r.get("kind") or ""), re.I)], key=lambda r: str(r.get("ref_date") or ""))
    prev = refs[-1] if refs else None
    ren = w.ask.get("renew_existing_total")
    tgt0 = w.ask.get("target_total")
    if prev is not None and ren is not None:
        lead = (f"Approval is requested to renew the facilities of {w.m(ren, w.ask_src, 'ask existing total')} approved under {prev['ref_no']} dated "
                f"{dt(prev.get('ref_date'))}" + (f" and increase them to {w.m(tgt0, w.ask_src, 'ask total')}" if tgt0 is not None and tgt0 > ren + 0.05 else "") + ": ")
        txt = lead + "; ".join(parts) + "."
    else:
        prev = None
        txt = "Approval is requested to " + "; ".join(parts) + "."
    if tp is not None:
        if te:
            txt += (f" Total limits move from {w.m(te, 'Data Domains · dd_facility_limit (existing limits)', 'total existing')} to "
                    f"{w.m(tp, w.ask_src, 'total proposed')} ({w.m(tp - te, w.ask_src, 'total change', sign=True)}, "
                    f"{w.pc((tp - te) / te * 100, w.ask_src, 'total change %', sign=True)}).")
        else:
            txt += f" Total proposed limits are {w.m(tp, w.ask_src, 'total proposed')}; the customer has no limits with the Bank today."
    tgt = w.ask.get("target_total")
    named = sum(float(i.get("amount") or 0) for i in items if i["action"] != "cancel")
    if tgt is not None and abs(tgt - named) > 0.05:
        txt += (f" The ask states total limits of {w.m(tgt, w.ask_src, 'ask total')} while the facilities it names sum to "
                f"{w.m(named, w.ask_src, 'named facilities')}: __to be aligned before submission__.")
        gaps.append("ask total differs from the facilities named")
    if w.ask.get("renew_existing_total") is not None and te is not None and abs(w.ask["renew_existing_total"] - te) > 0.05:
        txt += (f" The ask renews {w.m(w.ask['renew_existing_total'], w.ask_src, 'ask existing total')} of facilities; the Bank's records show "
                f"{w.m(te, 'Data Domains · dd_facility_limit', 'existing limits')} of existing limits.")
    cap, cap_src = group_cap(w)
    if cap is not None:
        gtot = _group_total_after(w, rows)
        if gtot is not None and gtot > cap + 0.05:
            import math
            newcap = math.ceil(gtot / 5 - 1e-9) * 5
            txt += (f" Group exposure after the request, {w.m(gtot, w.ask_src, 'group exposure after')}, exceeds the group cap of {w.m(cap, cap_src, 'group cap')}: "
                    f"approval is also requested to increase the group exposure cap from {w.m(cap, cap_src, 'group cap')} to {w.m(newcap, w.ask_src, 'group cap proposed')} "
                    "(the exposure after the request rounded up to the next SAR 5m).")
    if w.ask.get("takeover_bank"):
        tbk = w.ask["takeover_bank"]
        st = next((d for d in w.docs("other_bank_statement") if tbk.lower() in str((d.get("fields") or {}).get("bank_name") or d.get("subject") or "").lower().replace("_", " ")), None)
        osd = mn((st or {}).get("fields", {}).get("total_outstanding")) if st else None
        if osd is not None:
            txt += (f" The new facilities take over the customer's facilities with {tbk} (outstanding {w.m(osd, st['source'], 'incumbent outstanding')} at "
                    f"{dt(st['fields'].get('statement_date'))}, paid off at drawdown)")
            if tp is not None:
                d_ = tp - osd
                txt += (f"; the proposed limits of {w.m(tp, w.ask_src, 'total proposed')} exceed the payoff by {w.m(d_, w.ask_src, 'new money above payoff')} of new money." if d_ > 0.05
                        else f"; the proposed limits of {w.m(tp, w.ask_src, 'total proposed')} are below the payoff by {w.m(-d_, w.ask_src, 'payoff shortfall')}: __to be aligned__." if d_ < -0.05 else ".")
            else:
                txt += "."
        else:
            txt += f" The new facilities take over the customer's facilities with {tbk}; its statement of outstanding is __not provided__."
    untouched = [r for r in rows if r["ask"] is None and r["row"] is not None]
    if untouched and tgt is not None and abs(tgt - named) <= 0.05:
        txt += (f" The request covers {w.m(named, w.ask_src, 'named facilities')}; "
                + ", ".join(f"the {r['facility']} ({w.m(r['existing'], r['src'], r['facility'] + ' existing')})" for r in untouched)
                + " outside the ask " + ("runs" if len(untouched) == 1 else "run") + " as is and " + ("is" if len(untouched) == 1 else "are") + " included in the totals.")
    elif untouched:
        txt += (f" {len(untouched)} existing limit{'s are' if len(untouched) > 1 else ' is'} not addressed in the ask and "
                f"{'are' if len(untouched) > 1 else 'is'} shown for renewal at the existing amount: " + ", ".join(r["facility"] for r in untouched) + ".")
    out = [P(txt)]
    # previous approval
    if refs:
        r = refs[-1]
        out.append(P(f"Previous approval: {r.get('authority') or 'committee'} reference {r['ref_no']} dated {dt(r.get('ref_date'))}"
                     + (f" for {w.m(r.get('amount_mn'), src_row(r), 'previous approval')}" if num(r.get("amount_mn")) else "")
                     + (f", group cap {w.m(r.get('group_cap_mn'), src_row(r), 'group cap')}" if num(r.get("group_cap_mn")) else "") + "."))
    # the customer's own letter
    letter = w.doc("facility_request_letter")
    if letter:
        f = letter.get("fields") or {}
        req = mn(f.get("requested_total"))
        line = (f"The customer's facility request letter dated {dt(f.get('letter_date') or letter.get('issue_date'))}, signed by "
                f"{f.get('signatory') or 'the authorised signatory'}{(' (' + f['signatory_role'] + ')') if f.get('signatory_role') else ''}, "
                f"requests {w.m(req, letter['source'], 'letter requested total')}")
        if req is not None and tp is not None:
            new_items = sum(float(i.get("amount") or 0) - float(i.get("from_amount") or 0 if i["action"] == "increase" else 0)
                            for i in items if i["action"] in ("new", "increase", "takeover"))
            new_money = tp - (te or 0) if te else new_items
            diff = tp - req
            named_sum = sum(float(i.get("amount") or 0) for i in items if i["action"] != "cancel")
            if abs(diff) < 0.05 or abs(new_money - req) < 0.05 or abs(new_items - req) < 0.05 or abs(named_sum - req) < 0.05:
                line += ", consistent with this request."
            else:
                line += f"; this request differs by {w.m(diff, w.ask_src, 'request vs letter', sign=True)}: __to be reconciled before submission__."
                gaps.append("ask differs from the customer's request letter")
        else:
            line += "."
        out.append(P(line))
    else:
        out.append(P("The customer's signed facility request letter is __not provided__."))
        gaps.append("facility request letter not provided")
    res = w.doc("board_resolution")
    if res:
        f = res.get("fields") or {}
        au = mn(f.get("authorised_amount"))
        s = (f"Board resolution {f.get('resolution_number') or ''} dated {dt(f.get('resolution_date'))} authorises borrowing up to "
             f"{w.m(au, res['source'], 'borrowing authorised')}")
        if au is not None and tp is not None and au < tp - 0.05:
            s += f", __below the proposed limits of {w.m(tp, w.ask_src, 'total proposed')}__: a fresh resolution is required."
            gaps.append("board resolution below proposed limits")
        else:
            s += "."
        out.append(P(s))
    return out, gaps


def group_cap(w: W) -> tuple[float | None, str]:
    """The group exposure cap in force: dd_deal.group_cap_existing_mn, else the latest committee reference with a cap."""
    d = (w.rows("dd_deal") or [{}])[0]
    if num(d.get("group_cap_existing_mn")):
        return num(d["group_cap_existing_mn"]), src_row(d)
    refs = sorted([r for r in w.rows("dd_reference") if num(r.get("group_cap_mn"))], key=lambda r: str(r.get("ref_date") or ""))
    return (num(refs[-1]["group_cap_mn"]), src_row(refs[-1])) if refs else (None, "")


def _group_total_after(w: W, rows: list[dict[str, Any]]) -> float | None:
    g = w.rows("dd_group_exposure")
    tp = _total(rows, "proposed")
    if not g:
        return tp
    out = 0.0
    for r in g:
        subj = str(r.get("entity_name", "")).lower() == str(w.c.get("name", "")).lower() or r.get("entity_id") == w.c.get("cif")
        out += (tp or 0) if subj else (num(r.get("total_proposed_mn") or r.get("total_existing_mn")) or 0)
    return out


def _roman(i: int) -> str:
    return ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii"][i - 1] if i <= 12 else str(i)


def w_facilities(w: W) -> tuple[list[dict[str, Any]], list[str]]:
    rows = facility_rows(w)
    if not rows:
        return [P("No facility is named in the ask and the customer has no limits with the Bank.")], ["no facilities"]
    od = max((str((r["row"] or {}).get("_src", {}).get("period") or "") for r in rows if r["row"]), default="")
    tb = []
    for r in rows:
        ch = (r["proposed"] - (r["existing"] or 0)) if r["proposed"] is not None else None
        srcp = w.ask_src if r["ask"] else r["src"]
        tb.append([r["facility"], w.cell(r["existing"], r["src"], f"{r['facility']} existing") if r["existing"] is not None else "–",
                   w.cell(r["outstanding"], r["src"], f"{r['facility']} outstanding") if r["outstanding"] is not None else "–",
                   w.cell(r["proposed"], srcp, f"{r['facility']} proposed"),
                   ("+" if (ch or 0) > 0 else "") + (f"{ch:,.1f}" if ch is not None else "–"),
                   f"{r['cash_margin']:.0f}%" if r["cash_margin"] is not None else "–", particulars(w, r)])
        for s in r["subs"]:
            tb.append([f"    of which {s.get('limit_name')}", w.cell(s.get("existing_mn"), src_row(s), f"{s.get('limit_name')} existing"),
                       w.cell(s.get("outstanding_mn"), src_row(s)), w.cell(s.get("proposed_mn") or s.get("existing_mn"), src_row(s)), "", "", ""])
    te, to, tp = _total(rows, "existing"), _total(rows, "outstanding"), _total(rows, "proposed")
    tb.append(["**Total**", f"**{te:,.1f}**" if te is not None else "–", f"**{to:,.1f}**" if to is not None else "–",
               f"**{tp:,.1f}**" if tp is not None else "–", f"**{'+' if (tp or 0) - (te or 0) > 0 else ''}{(tp or 0) - (te or 0):,.1f}**", "", ""])
    pn = w.pricing_notes()
    for line in pn:  # a pricing note naming one facility goes into its particulars; otherwise under the table
        hit = next((i for i, r in enumerate(rows) if re.search(re.escape(r["facility"].split(" (")[0]), line, re.I)), None)
        if hit is not None:
            tb_i = sum(1 + len(rr["subs"]) for rr in rows[:hit])
            tb[tb_i][6] = f"{tb[tb_i][6]}; {line[0].lower() + line[1:]}" if tb[tb_i][6] != "–" else line
    out = [T(["Facility (SAR m)", "Existing", "Outstanding", "Proposed", "Change", "Cash margin", "Particulars"], tb,
             source="existing and outstanding: Data Domains · dd_facility_limit; proposed: the RM's ask (chat box)" if te is not None
             else "proposed: the RM's ask (chat box); the customer has no limits with the Bank", widths=[4.6, 1.8, 2.1, 1.8, 1.6, 1.5, 9.6], size=7.4)]
    rest = [x for x in pn if not any(re.search(re.escape(r["facility"].split(" (")[0]), x, re.I) for r in rows)]
    if rest:
        out.append(P("Pricing: " + "; ".join(rest) + "."))
    fund = sum(r["proposed"] or 0 for r in rows if r["funded"])
    known = all(r["row"] is not None or (r.get("ask") or {}).get("kind") in ("funded", "lc", "lg") for r in rows if (r["proposed"] or 0) > 0)
    if tp and not known:
        out.append(P("Funded and non-funded split as per the sub-limits; study and documentation fee: "
                     + fee_text(w, rows) + "."))
    elif tp:
        out.append(P(f"Funded {w.m(fund, w.ask_src, 'funded proposed')} ({w.pc(fund / tp * 100, w.ask_src, 'funded share')}) and non-funded "
                     f"{w.m(tp - fund, w.ask_src, 'non-funded proposed')} of the proposed total. Study and documentation fee: "
                     + fee_text(w, rows) + "."))
    # takeover: what is taken over
    if any((r.get("ask") or {}).get("action") == "takeover" for r in rows) or any(i["action"] == "takeover" for i in w.ask.get("items", [])):
        ob = w.docs("other_bank_statement") or w.docs("other_bank_offer_letter")
        if ob:
            lines = []
            for d in ob:
                f = d.get("fields") or {}
                lines.append(f"{f.get('bank_name') or 'Other bank'}: limits {w.m(mn(f.get('total_limits')), d['source'], 'other bank limits')}"
                             + (f", outstanding {w.m(mn(f.get('total_outstanding')), d['source'], 'other bank outstanding')} on {dt(f.get('statement_date'))}"
                                if f.get("total_outstanding") is not None else "") + f" ({d['source']})")
            out += [H("Facilities to be taken over"), BL(lines)]
    return out, []


def _nw_text(w: W, d: dict[str, Any]) -> str:
    f = d.get("fields") or {}
    nw, ta = mn(f.get("net_worth")), mn(f.get("total_assets"))
    s = (f"net worth {w.m(nw, d['source'], 'guarantor net worth')} (assets {w.m(ta, d['source'], 'guarantor assets')}) per statement dated "
         f"{dt(f.get('statement_date'))}")
    biggest = max((a for a in (f.get("assets") or []) if isinstance(a, dict)), key=lambda a: num(a.get("value")) or 0, default=None)
    if biggest and ta and num(biggest.get("value")):
        sh = num(biggest["value"]) / 1e6 / ta * 100
        s += f"; largest asset {biggest.get('asset') or biggest.get('description')} at {w.pc(sh, d['source'], 'largest asset share')} of assets"
    if d["status"] == "expired":
        s += "; __statement older than 12 months: an updated statement is required__"
    return s


def _movable(d: dict[str, Any]) -> bool:
    f = d.get("fields") or {}
    return bool(re.search(r"machinery|equipment|vehicle|lines|extruder", f"{f.get('property')} {d.get('subject')}", re.I)) \
        or "no title deed" in str(f.get("deed_number") or "").lower()


def _incumbent_charge(w: W, d: dict[str, Any]) -> str:
    """'currently charged to X, to be released on takeover' when the valuation or the incumbent's offer letter says so."""
    f = d.get("fields") or {}
    if f.get("encumbrance"):
        return f"; encumbrance: {f['encumbrance']}"
    tb = w.ask.get("takeover_bank")
    for o in w.docs("other_bank_offer_letter"):
        of = o.get("fields") or {}
        if tb and tb.lower() in str(of.get("bank_name") or "").lower() and re.search(r"charge over the machinery|machinery", str(of.get("security") or ""), re.I) and _movable(d):
            return f"; the first-ranking charge is registered to {of.get('bank_name')} ({o['source']}), to be released by {of.get('bank_name')} on takeover"
    return ""


def _val_text(w: W, d: dict[str, Any]) -> str:
    f = d.get("fields") or {}
    if _movable(d):
        return (f"{f.get('property') or 'the assets'} (owner {f.get('owner') or 'n/a'}): market value "
                f"{w.m(mn(f.get('market_value')), d['source'], 'market value')}, forced-sale {w.m(mn(f.get('forced_sale_value')), d['source'], 'forced-sale value')}, "
                f"valued by {f.get('valuer') or 'n/a'} on {dt(f.get('valuation_date'))}" + _incumbent_charge(w, d)
                + ("; __valuation older than 12 months__" if d["status"] == "expired" else ""))
    return (f"{f.get('property') or 'property'} (deed {f.get('deed_number') or 'n/a'}, owner {f.get('owner') or 'n/a'}): market value "
            f"{w.m(mn(f.get('market_value')), d['source'], 'market value')}, forced-sale {w.m(mn(f.get('forced_sale_value')), d['source'], 'forced-sale value')}, "
            f"valued by {f.get('valuer') or 'n/a'} on {dt(f.get('valuation_date'))}" + ("; __valuation older than 12 months__" if d["status"] == "expired" else ""))


def w_security(w: W) -> tuple[list[dict[str, Any]], list[str]]:
    """Security held (the Bank's register) joined with the documents that support it (net-worth statements, valuations): one line per
    security, the document's figures beside the register's, a difference said."""
    items, gaps = [], []
    nwd = list(w.docs("personal_net_worth"))
    vals = list(w.docs("valuation_report"))
    for r in w.rows("dd_security"):
        kind = str(r.get("kind") or "security").replace("_", " ")
        s = kind.capitalize()
        if r.get("provider"):
            s += f" of {r['provider']}"
        if num(r.get("amount_mn")) and "mortgage" not in kind.lower():
            s += f" for {w.m(r['amount_mn'], src_row(r), 'security amount')}"
        st = str(r.get("perfection_status") or "").replace("_", " ")
        s += f", {st}" if st else ""
        if r.get("perfection_deadline") and "perfect" not in st:
            s += f", to be perfected by {dt(r['perfection_deadline'])}"
        if str(r.get("existing_flag", "")).lower() in ("1", "true"):
            s, held_ = s.replace(", perfected", ""), True
        else:
            held_ = False
        doc = next((d for d in nwd if _same_name((d.get("fields") or {}).get("full_name") or d.get("subject"), r.get("provider"))), None) \
            if "guarantee" in kind.lower() and "personal" in kind.lower() else None
        if doc is not None:
            nwd.remove(doc)
            s += ": " + _nw_text(w, doc)
            bank_nw, doc_nw = num(r.get("net_worth_mn")), mn((doc.get("fields") or {}).get("net_worth"))
            if bank_nw and doc_nw and abs(bank_nw - doc_nw) > 0.02 * doc_nw:
                s += f" (the Bank's register: {w.m(bank_nw, src_row(r), 'guarantor net worth on register')} as at {dt(r.get('net_worth_statement_date'))})"
        elif num(r.get("net_worth_mn")):
            s += f": net worth {w.m(r['net_worth_mn'], src_row(r), 'guarantor net worth')} as at {dt(r.get('net_worth_statement_date'))} (the Bank's register)"
        if "mortgage" in kind.lower() and vals:
            v = vals.pop(0)
            s += " over " + _val_text(w, v)
        elif num(r.get("value_mn")):
            s += f", value {w.m(r['value_mn'], src_row(r), 'collateral value')}" + (f" (valued {dt(r.get('valuation_date'))})" if r.get("valuation_date") else "")
        items.append(s + (" — existing" if held_ else "") + ".")
    for c in w.ask.get("security", []):
        items.append(f"{c[0].upper() + c[1:]}" + ("" if c.endswith(".") else ".") + " (proposed)")
    from backend.dealdesk.deposit_requirement.docs import rm_security  # Round D: the Deposit requirement term
    items = rm_security(w, items)
    for d in nwd:
        f = d.get("fields") or {}
        items.append(f"Personal guarantee of {f.get('full_name') or d.get('subject')}: {_nw_text(w, d)}.")
    for d in vals:
        items.append(f"{'First-ranking charge over' if _movable(d) else 'Mortgage over'} {_val_text(w, d)}.")
    for d in w.docs("insurance_policy"):
        f = d.get("fields") or {}
        items.append(f"Insurance {f.get('policy_number') or ''} with {f.get('insurer') or 'n/a'}, sum insured {w.m(mn(f.get('sum_insured')), d['source'], 'sum insured')}, "
                     f"loss payee {f.get('loss_payee') or 'not stated'}, valid to {dt(f.get('expiry_date'))}" + ("; __expired__" if d["status"] == "expired" else "") + ".")
    items += standard_security(w, items)
    for m in w.cf.get("missing", []):
        if m.get("doc_type") in ("personal_net_worth", "valuation_report", "title_deed", "insurance_policy"):
            why = str(m.get("why") or "").strip()
            items.append(f"{I.LABELS.get(m['doc_type'], m['doc_type'])}{(' of ' + subj(w, m.get('subject'))) if m.get('subject') else ''}: "
                         f"__not provided__" + (f" ({why})" if why and why.lower().rstrip(".") not in ("not provided", "not provided by the customer") else "") + ".")
            gaps.append(f"{m['doc_type']} not provided")
    items += w.notes_for("security")
    if not items:
        items = ["Clean basis: no security is named in the ask and the Bank holds none for this customer; "
                 "the customer's standard undertakings and a promissory note for the funded limits apply."]
        gaps.append("no security named")
    return [BL(items)], gaps


def standard_security(w: W, held: list[str]) -> list[str]:
    """The standard items of every request: a promissory note for the proposed total, the cash margin of each LC / LG line, and for a
    new-to-bank customer the personal guarantee of each shareholder holding 25% or more (Articles of Association)."""
    rows = facility_rows_cache(w)
    tp = _total(rows, "proposed")
    out = []
    txt = " ".join(held).lower()
    if tp and "promissory" not in txt:
        out.append(f"Promissory note for {w.m(tp, w.ask_src, 'promissory note')} (the proposed total), signed by the customer (proposed).")
    for r in rows:
        if not r["proposed"] or r["funded"]:
            continue
        cm = r["cash_margin"]
        if cm is None and not w.c.get("existing") and _kind_of(r) == "lg":
            cm = 10.0
            w._rec(f"{r['facility']} cash margin", "10%", 10.0, "the Bank's standard cash margin for new-to-bank LGs (proposed by business)")  # noqa: SLF001
        if cm:
            out.append(f"Cash margin {w.pc(cm, r['src'] or w.ask_src, r['facility'] + ' cash margin', dp=0)} on the {r['facility']} "
                       f"({w.m(r['proposed'] * cm / 100, r['src'] or w.ask_src, r['facility'] + ' cash margin amount')} on the proposed {w.m(r['proposed'], w.ask_src, r['facility'] + ' proposed')}).")
    if not w.c.get("existing"):
        aoa = w.doc("articles_of_association")
        for sh in ((aoa or {}).get("fields") or {}).get("shareholders") or []:
            if not isinstance(sh, dict) or not sh.get("name"):
                continue
            pct = num(sh.get("pct"))
            pct = pct * 100 if pct is not None and pct <= 1 else pct
            if pct is None or pct < 25 or re.search(r"\b(co|company|llc|holding)\b", str(sh["name"]), re.I):
                continue
            if any(_same_name(sh["name"], re.sub(r"^.*guarantee of\s+|[:,].*$", "", h, flags=re.I)) for h in held if "guarantee" in h.lower()):
                continue
            out.append(f"Personal guarantee of {sh['name']} ({w.pc(pct, aoa['source'], sh['name'] + ' holding', dp=0)} shareholder) for the total facilities (proposed).")
    return out


LIB = {
    "Overdraft": "Overdraft for working capital only; no transfers to group or related parties; annual clean-up of 30 days or full renewal review.",
    "Letters of credit": "LCs for imports of goods and raw materials for the customer's own business only; usance up to 180 days; LC documents in the customer's name; shipping documents through the Bank.",
    "Sight letters of credit": "Sight LCs for imports of the customer's trading goods only; documents through the Bank.",
    "Usance letters of credit": "Usance LCs up to 180 days for trading goods only; acceptance settled from sale proceeds routed to the Bank.",
    "Trust receipts / LC refinance": "Trust receipts only against LCs opened by the Bank; maximum 120 days; settled from receivables of the goods financed.",
    "Letters of guarantee": "LGs in the Bank's standard wording only; no open-ended or on-demand-without-expiry LGs; single LG cap to be agreed with Credit.",
    "Performance guarantees": "Performance LGs up to 10% of contract value, against awarded contracts only; wording in the Bank's standard format.",
    "Advance payment guarantees": "Advance payment LGs only against advances received into the customer's account with the Bank; reducing with recovery.",
    "Bid bonds": "Bid bonds up to 2% of tender value; validity up to 120 days.",
    "Short-term murabaha": "Each drawdown against supplier invoices; tenor up to 180 days per drawdown; settled from the sale proceeds of the goods financed.",
    "Murabaha": "Each drawdown against supplier invoices; settled from the sale proceeds of the goods financed.",
    "Receivables finance": "Up to 80% of eligible invoices aged under 90 days; buyer concentration cap 25% per buyer; proceeds assigned to the Bank.",
    "Term finance": "Repayment in equal quarterly instalments over the tenor after any grace period; prepayment allowed without penalty from internal cash.",
    "Takeover facility": "Disbursed directly to the other bank against its liability letter; release of the other bank's security and its no-objection letter prior to disbursement.",
    "Project limit": "Disbursement against certified payment certificates only, up to 80% of certified amounts; project proceeds assigned and routed to the Bank.",
    "Working capital limit": "For working capital only; utilisation against invoices or LCs; no transfers to group or related parties.",
    "General limit": "Interchangeable between sub-limits within the general limit; sub-limit caps apply.",
}


def _tenor_days(w: W, r: dict[str, Any]) -> int | None:
    """The tenor per drawdown of a facility row, in days: the Bank's row (tenor_text), the facility's name ("usance 90 days"), the ask."""
    for t in (str((r.get("row") or {}).get("tenor_text") or ""), str(r.get("facility") or "")):
        m = re.search(r"(\d{2,3})\s*days", t, re.I)
        if m:
            return int(m.group(1))
    tm = (r.get("ask") or {}).get("tenor_months")
    return tm * 30 if tm and tm <= 12 else None


def lib_clause(w: W, k: str, r: dict[str, Any]) -> str:
    """The library clause of a facility, its tenor taken from the facility row (never a fixed 180 days that the table contradicts)."""
    t = LIB[k]
    rep = str((r.get("row") or {}).get("repayment_text") or "")
    if k == "Term finance" and rep:
        t = f"Repayment as in the facilities table ({rep}); prepayment allowed without penalty from internal cash."
    d = _tenor_days(w, r)
    if re.search(r"up to 180 days|maximum 120 days", t):
        if d:
            t = re.sub(r"(up to|maximum) (180|120) days", rf"\g<1> {d} days", t)
        else:
            t = re.sub(r";?\s*(?:tenor |usance )?(up to|maximum) (180|120) days( per drawdown)?", "; tenor as in the facilities table", t).replace(" ;", ";")
            t = re.sub(r"^(\w[^;]*?) as in the facilities table", r"\1 as in the facilities table", t)
    return t


def w_terms(w: W) -> tuple[list[dict[str, Any]], list[str]]:
    rows = facility_rows(w)
    out: list[str] = []
    seen = set()
    for r in rows:
        k = r["canon"] if r["canon"] in LIB else r["facility"]
        if k in LIB and k not in seen and (r["proposed"] or 0) > 0:
            seen.add(k)
            out.append(f"{r['facility']}: {lib_clause(w, k, r)}")
    # covenants for term finance (DSCR on the audited accounts)
    if any("term" in r["facility"].lower() and (r.get("ask") or {}).get("action") in ("new", "takeover") and (r["proposed"] or 0) > 0 for r in rows):
        out.append("Debt service coverage (EBITDA / (finance cost + current portion of long-term debt)) not below 1.20x, tested on each year's audited accounts.")
    # existing conditions: one line with each status (the trace view keeps the dd_tnc rows)
    ex = [t for t in w.rows("dd_tnc") if t.get("text") and str(t.get("existing_status") or "").strip()]
    routing_ex = next((t for t in ex if re.search(r"\broute|routing", str(t["text"]), re.I)), None)
    if ex:
        refs = sorted([r for r in w.rows("dd_reference") if r.get("ref_no") and re.search(r"committee|decision|approv", str(r.get("kind") or ""), re.I)],
                      key=lambda r: str(r.get("ref_date") or ""))
        bits = []
        for t in ex:
            st = str(t["existing_status"]).replace("_", " ")
            txt = re.sub(r"\s*\((?:CC|[A-Z]{2,})/[^)]*\)", "", str(t["text"])).strip().rstrip(".")
            txt = txt[0].lower() + txt[1:] if txt[:2] != txt[:2].upper() else txt
            w._rec("existing condition status", st, st, src_row(t))  # noqa: SLF001
            bits.append(f"{txt.replace(';', ',')} — {'__' + st + '__' if 'not' in st.lower() else st}")
        out.append(f"Existing conditions{(' (' + refs[-1]['ref_no'] + ')') if refs else ''}: " + "; ".join(bits) + ".")
    # business routing undertaking: the existing condition renewed, else sized on today's routing; new to bank: share of turnover
    cond = sorted(w.rows("dd_account_conduct"), key=lambda r: str(r.get("month") or ""))[-12:]
    fund = sum(r["proposed"] or 0 for r in rows if r["funded"])
    if routing_ex is not None:
        txt = re.sub(r"\s*\((?:CC|[A-Z]{2,})/[^)]*\)", "", str(routing_ex["text"])).strip().rstrip(".")
        out.append(f"Business routing: {txt[0].lower() + txt[1:]} (existing condition, renewed)"
                   + (f"; last 12 months credit turnover {w.m(sum(num(r.get('credit_turnover_mn')) or 0 for r in cond), src_row(cond[-1]), 'credit turnover 12m')}" if cond else "") + ".")
    elif not w.c.get("existing") and fund:
        out.append("Business routing: route not less than 70% of the customer's turnover through the Bank's accounts within 6 months of the first drawdown.")
    elif cond and fund:
        cr = sum(num(r.get("credit_turnover_mn")) or 0 for r in cond)
        times = int(cr / fund) if fund else 0
        out.append(f"Business routing: at least {max(1, min(times, 6))} times the funded limits ({w.m(fund, w.ask_src, 'funded proposed')}) to be routed "
                   f"through the Bank's accounts each year (last 12 months: {w.m(cr, src_row(cond[-1]), 'credit turnover 12m')}, "
                   f"{w.x(cr / fund, src_row(cond[-1]), 'routing multiple')} the proposed funded limits).")
    elif fund:
        out.append(f"Business routing: the customer to route its collections through the Bank, at least 3 times the funded limits "
                   f"(funded part of the {w.m(_total(rows, 'proposed'), w.ask_src, 'total proposed')} proposed) each year; to be confirmed with the customer.")
    if w.ask.get("takeover_bank"):
        tbk = w.ask["takeover_bank"]
        ins = [d for d in w.docs("insurance_policy") if tbk.lower() in str((d.get("fields") or {}).get("loss_payee") or "").lower()]
        out.append(f"Prior to disbursement: {tbk}'s liability letter and no-objection, disbursement direct to {tbk}, release of its charges and "
                   f"registration of the Bank's security" + (f"; insurance loss payee changed from {tbk} to the Bank ({ins[0]['source']})" if ins else "") + ".")
    from backend.dealdesk.deposit_requirement.docs import rm_terms  # Round D: the deposit's placement / maintenance condition
    out = rm_terms(w, out)
    out.append("Audited financial statements within 120 days of each year end and in-house statements within 60 days of each quarter end; "
               "a change of auditor only with the Bank's prior consent.")
    out.append("No change in ownership, management or legal form without the Bank's prior written consent"
               + ("; dividends as agreed in the ask" if re.search(r"dividend", str(w.ask.get("text") or ""), re.I) else "") + ".")
    dtr = None
    for p in periods(w)[::-1]:
        dtr = mn(p["f"].get("due_to_related"))
        if dtr is not None:
            if dtr > 0.5:
                out.append(f"Due to related parties of {w.m(dtr, p['src'], 'due to related parties')} ({p['label']}) to be subordinated to the Bank's facilities.")
            break
    exp = [d for d in w.cf["documents"] if d["status"] == "expired" and d.get("doc_type") in
           ("commercial_registration", "zakat_certificate", "nitaqat_certificate", "national_id", "insurance_policy")]
    for d in exp:
        out.append(f"Prior to limit loading: renewed {I.LABELS.get(d['doc_type'], d['doc_type']).lower()}"
                   f"{(' of ' + subj(w, d.get('subject'))) if d.get('subject') and d['doc_type'] == 'national_id' else ''} "
                   f"(the copy on file expired on {dt(d.get('expiry_date') or (d.get('fields') or {}).get('expiry_date'))}).")
    out += [n for n in w.notes_for("terms") if not PRICING_NOTE.search(n)]
    return [NL(out)], []


def w_group(w: W) -> tuple[list[dict[str, Any]], list[str]]:
    g = w.rows("dd_group_exposure")
    rows = facility_rows(w)
    tp, fp = _total(rows, "proposed"), sum(r["proposed"] or 0 for r in rows if r["funded"])
    out: list[dict[str, Any]] = []
    if g:
        tb, tot = [], [0.0] * 5
        for r in g:
            subj = str(r.get("entity_name", "")).lower() == str(w.c.get("name", "")).lower() or r.get("entity_id") == w.c.get("cif")
            vals = [num(r.get("funded_existing_mn")), num(r.get("total_existing_mn")), fp if subj else num(r.get("funded_proposed_mn") or r.get("funded_existing_mn")),
                    tp if subj else num(r.get("total_proposed_mn") or r.get("total_existing_mn")), num(r.get("outstanding_mn"))]
            tot = [a + (b or 0) for a, b in zip(tot, vals)]
            tb.append([str(r.get("entity_name")) + (" (subject)" if subj else "")] + [w.cell(v, w.ask_src if subj and i in (2, 3) else src_row(r), f"{r.get('entity_name')} {h}")
                                                                                      for i, (v, h) in enumerate(zip(vals, ("funded existing", "total existing", "funded proposed", "total proposed", "outstanding")))])
        tb.append(["**Group total**"] + [f"**{v:,.1f}**" for v in tot])
        out.append(T(["Entity (SAR m)", "Funded existing", "Total existing", "Funded proposed", "Total proposed", "Outstanding"], tb,
                     source="Data Domains · dd_group_exposure; the subject's proposed limits from the RM's ask", widths=[6, 2, 2, 2, 2, 2]))
        cap, cap_src = group_cap(w)
        out.append(P(f"Group exposure moves from {w.m(tot[1], 'Data Domains · dd_group_exposure', 'group total existing')} "
                     f"to {w.m(tot[3], w.ask_src, 'group total proposed')} with this request "
                     f"({w.m(tot[3] - tot[1], w.ask_src, 'group change', sign=True)})"
                     + (f" against a group cap of {w.m(cap, cap_src, 'group cap')}" + (": __the cap is to be increased__." if tot[3] > cap + 0.05 else ".")
                        if cap is not None else ".")))
    elif w.c.get("existing") and _total(rows, "existing") is not None:
        out.append(P(f"Group exposure with the Bank equals the customer's own limits of {w.m(_total(rows, 'existing'), 'Data Domains · dd_facility_limit', 'existing')}; "
                     "no other group entity holds limits with the Bank (Data Domains · dd_group_exposure has no row)."))
    elif w.c.get("existing"):
        out.append(P(f"The Bank's data holds no limits and no group exposure for CIF {w.c.get('cif')} as at {dt(w.written)} (Data Domains · dd_facility_limit, "
                     f"dd_group_exposure: no rows); group exposure after this request is {w.m(tp, w.ask_src, 'total proposed')}."))
    else:
        out.append(P("New to bank: neither the customer nor any related entity holds limits with the Bank; group exposure after this request equals "
                     f"the proposed limits of {w.m(tp, w.ask_src, 'total proposed')}."))
    refs = sorted(w.rows("dd_reference"), key=lambda r: str(r.get("ref_date") or ""))
    if refs:
        out.append(H("References"))
        out.append(T(["Date", "Kind", "Reference", "Authority", "Amount (SAR m)", "Note"],
                     [[dt(r.get("ref_date")), str(r.get("kind") or "").replace("_", " "), r.get("ref_no") or "", r.get("authority") or "",
                       w.cell(r.get("amount_mn"), src_row(r), "reference amount"), cut(r.get("text"))] for r in refs[-8:]],
                     source="Data Domains · dd_reference", widths=[2.2, 2.6, 2.6, 2.6, 2.0, 6.5]))
    return out, []


def w_background(w: W) -> tuple[list[dict[str, Any]], list[str]]:
    c, out, gaps = w.c, [], []
    cr = w.doc("commercial_registration")
    aoa = w.doc("articles_of_association")
    if cr or aoa:
        f = {**((aoa or {}).get("fields") or {}), **((cr or {}).get("fields") or {})}
        inc = ((aoa or {}).get("fields") or {}).get("date_of_incorporation")
        s = (f"{c.get('name')} is a {f.get('legal_form') or 'company'} registered in {f.get('city') or c.get('city') or 'the Kingdom'} under CR {f.get('cr_number') or c.get('cr_number')}"
             + (f", incorporated on {dt(inc)}" if inc else "") + (f"; activity: {f.get('activity')}" if f.get("activity") else "")
             + (f"; capital {w.m(mn(f.get('share_capital')), (cr or aoa)['source'], 'share capital')}" if f.get("share_capital") else "") + ".")
        if cr:
            s += f" The CR is valid to {dt(cr.get('expiry_date') or (cr.get('fields') or {}).get('expiry_date'))}" + (" (__expired__)." if cr["status"] == "expired" else ".")
        out.append(P(s))
    else:
        out.append(P("Commercial Registration and Articles of Association: __not provided__."))
        gaps.append("CR / AoA not provided")
    sh = (aoa or {}).get("fields", {}).get("shareholders") if aoa else None
    b3s = w.rows("b360_shareholder")
    ents = {e.get("entity_id"): e for e in w.rows("b360_entity")}

    def born(name: Any) -> str:
        for d in w.docs("national_id"):
            f = d.get("fields") or {}
            if _same_name(f.get("full_name"), name) and I._d(f.get("date_of_birth")):  # noqa: SLF001
                return w._rec(f"{name} born", str(I._d(f["date_of_birth"]).year), I._d(f["date_of_birth"]).year, d["source"])  # noqa: SLF001
        r = next((r for r in b3s if _same_name(r.get("holder_name"), name) and num(r.get("birth_year"))), None)
        return w._rec(f"{name} born", str(int(num(r["birth_year"]))), int(num(r["birth_year"])), src_row(r)) if r else ""  # noqa: SLF001

    def ubo(name: Any) -> str:
        r = next((r for r in b3s if _same_name(r.get("holder_name"), name) and num(r.get("ubo_effective_pct"))), None)
        return w.pc(r["ubo_effective_pct"], src_row(r), f"{name} UBO look-through") if r else ""
    if sh:
        out.append(T(["Shareholder", "Nationality", "Born", "Shares", "Holding", "UBO (look-through)"],
                     [[s.get("name"), s.get("nationality") or "", born(s.get("name")), w.n(s.get("shares"), aoa["source"], "shares") if s.get("shares") is not None else "",
                       w.pc(num(s.get("pct")) * (100 if (num(s.get("pct")) or 0) <= 1 else 1), aoa["source"], f"{s.get('name')} %"), ubo(s.get("name"))] for s in sh if isinstance(s, dict)],
                     source=aoa["source"] + ("; born and look-through: national IDs and Data Domains · b360_shareholder" if b3s else ""), widths=[6, 2.5, 1.6, 2.4, 2.2, 2.6]))
        # a corporate shareholder: its own shareholders from Borrower 360 (look-through to the ultimate owners)
        for s_ in sh:
            if not isinstance(s_, dict):
                continue
            pe = next((e for e in ents.values() if _same_name(e.get("entity_name"), s_.get("name"))), None)
            if pe is None:
                continue
            own = [r for r in b3s if r.get("entity_id") == pe.get("entity_id")]
            if own:
                out.append(P(f"{s_.get('name')} is owned by " + ", ".join(f"{r.get('holder_name')} {w.pc(r.get('share_pct'), src_row(r), 'parent holding', dp=0)}" for r in own)
                             + "; ultimate beneficial owners (look-through): "
                             + ", ".join(f"{r.get('holder_name')} {w.pc(r.get('ubo_effective_pct'), src_row(r), 'UBO look-through')}" for r in own if num(r.get("ubo_effective_pct")))
                             + " (Borrower 360)."))
    elif w.rows("b360_shareholder"):
        out.append(T(["Shareholder", "Nationality", "Holding", "UBO"],
                     [[r.get("holder_name"), r.get("nationality") or "", w.pc(r.get("share_pct"), src_row(r), "holding"), "yes" if r.get("ubo_flag") else ""]
                      for r in w.rows("b360_shareholder") if r.get("entity_id") in (c.get("cif"),) or len(w.rows("b360_shareholder")) <= 6],
                     source="Data Domains · b360_shareholder", widths=[7, 3, 3, 3]))
    mg = (aoa or {}).get("fields", {}).get("managers") if aoa else None
    if mg:
        out.append(P("Managers and signatories as per AoA: " + "; ".join(f"{m.get('name')} ({m.get('role')})" for m in mg if isinstance(m, dict)) + f" ({aoa['source']})."))
    ents = [e for e in w.rows("b360_entity") if e.get("entity_name") != c.get("name")]
    if ents:
        out.append(H(f"Group: {c.get('group_name') or ''}".strip()))
        out.append(T(["Entity", "Role", "Activity", "Status with the Bank"],
                     [[e.get("entity_name"), str(e.get("role") or "").replace("_", " "), e.get("activity") or "",
                       cut(str(e.get("credit_status") or "").replace("_", " ") + (f": {e['credit_status_note']}" if e.get("credit_status_note") else ""))] for e in ents],
                     source="Data Domains · b360_entity", widths=[5, 2.5, 5, 5]))
    ni = w.doc("nitaqat_certificate")
    if ni:
        f = ni.get("fields") or {}
        s = (f"Nitaqat band {f.get('nitaqat_band') or 'n/a'}: Saudisation {w.pc(_pct(f.get('saudisation_pct')), ni['source'], 'saudisation')} against "
             f"{w.pc(_pct(f.get('band_threshold_pct')), ni['source'], 'band minimum')} for the band, "
             f"{w.n(f.get('saudi_staff'), ni['source'], 'saudi staff')} Saudi of {w.n(f.get('total_staff'), ni['source'], 'total staff')} employees")
        hd = (_pct(f.get("saudisation_pct")) or 0) - (_pct(f.get("band_threshold_pct")) or 0)
        if f.get("band_threshold_pct") is not None and hd < 2:
            s += f"; __headroom of {hd:.1f} points to the band minimum__"
        out.append(P(s + (" (certificate expired)." if ni["status"] == "expired" else ".")))
    vat = w.doc("vat_certificate")
    if vat:
        f = vat.get("fields") or {}
        out.append(P(f"VAT registered under {f.get('vat_number') or c.get('vat_number')} since {dt(f.get('effective_date'))}, filing {str(f.get('filing_frequency') or 'n/a').lower()} ({vat['source']})."))
    tc = w.doc("top_customers_suppliers")
    if tc:
        f = tc.get("fields") or {}
        cu = [x for x in (f.get("customers") or []) if isinstance(x, dict)]
        if cu:
            top = sorted(cu, key=lambda x: -(num(x.get("share_pct")) or 0))
            s = ", ".join(f"{x.get('name')}{(' (' + str(x['relationship']).lower() + ')') if related(x.get('relationship')) else ''} "
                          f"{w.pc(_pct(x.get('share_pct')), tc['source'], 'customer share')}" for x in top[:3])
            t3 = sum(_pct(x.get("share_pct")) or 0 for x in top[:3])
            out.append(P(f"Top customers {f.get('year') or ''}: {s}; top 3 = {w.pc(t3, tc['source'], 'top 3 share')} of sales ({tc['source']})."))
        su = [x for x in (f.get("suppliers") or []) if isinstance(x, dict)]
        if su:
            top = sorted(su, key=lambda x: -(num(x.get("share_pct")) or 0))[:3]
            out.append(P("Top suppliers: " + ", ".join(f"{x.get('name')} ({x.get('country') or 'n/a'}) {w.pc(_pct(x.get('share_pct')), tc['source'], 'supplier share')}" for x in top)
                         + f" of purchases ({tc['source']})."))
    pl = w.doc("project_list")
    pr = [x for x in (((pl or {}).get("fields") or {}).get("projects") or []) if isinstance(x, dict)]
    if pr:
        out.append(H("Projects in hand"))
        out.append(T(["Project", "Employer", "Contract", "Work done", "Billed", "Received", "Retention", "Status"],
                     [[x.get("project"), x.get("employer"), w.cell(mn(x.get("contract_value")), pl["source"], "contract value"),
                       w.pc(_pct(x.get("work_done_pct")), pl["source"], "work done", dp=0), w.cell(mn(x.get("billed")), pl["source"], "billed"),
                       w.cell(mn(x.get("received")), pl["source"], "received"), w.cell(mn(x.get("retention_held")), pl["source"], "retention"),
                       cut(x.get("status"), 80)] for x in pr], source=pl["source"] + " (SAR m)", widths=[4.2, 3.6, 1.6, 1.4, 1.5, 1.6, 1.5, 3.2], size=7.0))
    sv = w.doc("site_visit_report")
    if sv:
        f = sv.get("fields") or {}
        out.append(P(f"Site visit on {dt(f.get('visit_date'))} by {f.get('visited_by') or 'the RM'} (met {f.get('met_with') or 'management'}): "
                     f"{str(f.get('premises') or '').rstrip('.')}{'; ' if f.get('premises') else ''}{w.n(f.get('staff_seen'), sv['source'], 'staff seen') if f.get('staff_seen') else ''}"
                     f"{' staff observed; ' if f.get('staff_seen') else ''}{str(f.get('observations') or '').rstrip('.')} ({sv['source']})."))
    aml = w.doc("aml_kyc_questionnaire")
    if aml:
        f = aml.get("fields") or {}
        out.append(P(f"AML/KYC questionnaire completed {dt(f.get('completed_on'))}: customer risk rating {f.get('risk_rating') or 'n/a'}, PEP {f.get('pep_flag') or 'n/a'}, "
                     f"cash-intensive {f.get('cash_intensive') or 'n/a'}, countries of trade {f.get('countries') or 'n/a'} ({aml['source']})."))
    out += [P(n) for n in w.notes_for("background", "market")]
    return out, gaps


def _pct(v: Any) -> float | None:
    x = num(v)
    if x is None:
        return None
    return x * 100 if abs(x) <= 1.0 else x


def w_relationship(w: W) -> tuple[list[dict[str, Any]], list[str]]:
    out: list[dict[str, Any]] = []
    c = w.c
    accts = w.rows("dd_customer_account")
    cond = sorted(w.rows("dd_account_conduct"), key=lambda r: str(r.get("month") or ""))
    if c.get("existing") and (accts or cond):
        opened = min((str(a.get("opened") or a.get("opened_date") or "") for a in accts if a.get("opened") or a.get("opened_date")), default="") \
            or str((w.rows("dd_deal") or [{}])[0].get("account_opened_date") or "")
        yrs = ""
        if opened and I._d(opened):  # noqa: SLF001
            od, wd = I._d(opened), I._d(w.written)  # noqa: SLF001
            yrs = f" ({(wd - od).days // 365} years)"
        out.append(P(f"The customer banks with us since {dt(opened) or 'n/a'}{yrs} with {len(accts)} account{'s' if len(accts) != 1 else ''}."))
        if accts:
            tb = []
            for a in accts:
                s = src_row(a)
                no = str(a.get("account_number") or a.get("account_no") or a.get("iban") or a.get("account_id") or "")
                tb.append([("…" + no[-4:]) if len(no) > 4 else no, (str(a.get("label") or "") or str(a.get("account_type") or "")).replace("_", " "), dt(a.get("opened") or a.get("opened_date")),
                           w.cell(_first(a, "balance_mn", "balance_30sep_mn", "closing_balance_mn"), s, f"balance {no[-4:]}"),
                           w.cell(_first(a, "avg_balance_12m_mn", "avg_balance_mn"), s, f"avg balance {no[-4:]}"),
                           w.cell(_first(a, "credits_12m_mn", "credit_turnover_12m_mn", "credits_mn"), s, f"credits {no[-4:]}")])
            out.append(T(["Account", "Type", "Opened", "Balance", "Avg balance 12m", "Credits 12m"], tb, source="Data Domains · dd_customer_account (SAR m)",
                         widths=[2.4, 3.2, 2.4, 2.2, 2.6, 2.4]))
        if cond:
            last, prev = cond[-12:], cond[-24:-12]
            s = src_row(last[-1])
            cr_l = sum(num(r.get("credit_turnover_mn")) or 0 for r in last)
            cr_p = sum(num(r.get("credit_turnover_mn")) or 0 for r in prev) if len(prev) == 12 else None
            ab = sum(num(r.get("avg_balance_mn")) or 0 for r in last) / len(last)
            ut = [num(r.get("utilisation_pct")) for r in last if num(r.get("utilisation_pct")) is not None]
            pdd = max((num(r.get("past_due_days_max")) or 0 for r in last), default=0)
            rc = sum(num(r.get("returned_cheques_n")) or 0 for r in last)
            rcm = sum(num(r.get("returned_cheques_mn")) or 0 for r in last)
            line = (f"Over {mon(last[0].get('month'))} – {mon(last[-1].get('month'))} credit turnover was "
                    f"{w.m(cr_l, s, 'credit turnover 12m')}" + (f" (PY {w.m(cr_p, src_row(prev[-1]), 'credit turnover prior 12m')}, "
                                                                 f"{w.pc((cr_l / cr_p - 1) * 100, s, 'credit turnover growth', sign=True)})" if cr_p else "")
                    + f" and the average balance {w.m(ab, s, 'average balance 12m')}.")
            if ut:
                line += (f" Utilisation averaged {w.pc(_pct(sum(ut) / len(ut)), s, 'average utilisation')} (peak {w.pc(_pct(max(ut)), s, 'peak utilisation')}).")
            line += (f" Past dues: {'none' if not pdd else 'maximum ' + w.n(pdd, s, 'past due days') + ' days'}; returned cheques: "
                     + ("none" if not rc else f"{w.n(rc, s, 'returned cheques')} for {w.m(rcm, s, 'returned cheques amount', dp=2)}") + " in the last 12 months.")
            out.append(P(line))
            cif = w.c.get("cif")
            own = [r for r in cond if not cif or not r.get("obligor_id") or r.get("obligor_id") == cif]
            qs: dict[str, list[dict[str, Any]]] = {}
            for r in own:
                m_ = str(r.get("month") or "")
                if len(m_) >= 7 and m_[5:7].isdigit():
                    qs.setdefault(f"Q{(int(m_[5:7]) - 1) // 3 + 1} {m_[:4]}", []).append(r)
            ql = [(k, v) for k, v in qs.items() if len(v) == 3][-4:]
            if len(ql) >= 2:
                tb = []
                for k, v in ql:
                    s_ = src_row(v[-1])
                    ut_ = [num(r.get("utilisation_pct")) for r in v if num(r.get("utilisation_pct")) is not None]
                    tb.append([k, w.cell(sum(num(r.get("credit_turnover_mn")) or 0 for r in v), s_, f"credit turnover {k}"),
                               w.cell(sum(num(r.get("avg_balance_mn")) or 0 for r in v) / 3, s_, f"average balance {k}"),
                               w.pc(sum(ut_) / len(ut_), s_, f"utilisation {k}", dp=0) if ut_ else "–",
                               w.n(max(num(r.get("past_due_days_max")) or 0 for r in v), s_, f"past due days {k}"),
                               w.n(sum(num(r.get("returned_cheques_n")) or 0 for r in v), s_, f"returned cheques {k}")])
                out.append(T(["Quarter", "Credit turnover", "Avg balance", "Utilisation", "Max past due (days)", "Returned cheques"], tb,
                             source="Data Domains · dd_account_conduct (SAR m)", widths=[2.4, 2.6, 2.4, 2.2, 2.8, 2.6]))
        b3 = (((w.cf.get("intake") or {}).get("bank") or {}).get("b360") or {})
        rh = [r for r in (b3.get("rating_history") or []) if isinstance(r, dict)]
        ews = b3.get("ews") or {}
        if rh or ews:
            bits = []
            if rh:
                seq = [f"{r.get('rating_current') or r.get('rating')} ({r.get('reporting_quarter')})" for r in rh[-4:]]
                bits.append("rating history " + " → ".join(seq))
                w._rec("rating history", seq[-1], seq[-1], "Borrower 360 · ratings (via CreditProbe intake)")  # noqa: SLF001
            if ews.get("band") or ews.get("ews_band"):
                band = ews.get("band") or ews.get("ews_band")
                bits.append(f"early-warning band {band}" + (f" (score {ews.get('score') or ews.get('ews_score')})" if ews.get("score") or ews.get("ews_score") else ""))
                w._rec("EWS band", str(band), band, "Borrower 360 · early warning (via CreditProbe intake)")  # noqa: SLF001
            out.append(P("Borrower 360: " + "; ".join(bits) + "."))
        rch = w.rows("dd_returned_cheque")
        if rch:
            out.append(T(["Date", "Amount (SAR m)", "Reason", "Regularised"],
                         [[dt(r.get("return_date")), w.cell(r.get("amount_mn"), src_row(r), "returned cheque", dp=2), r.get("reason") or "", "yes" if r.get("regularised_flag") else "no"]
                          for r in sorted(rch, key=lambda r: str(r.get("return_date") or ""))[-6:]], source="Data Domains · dd_returned_cheque", widths=[3, 3, 7, 2.5]))
    else:
        out.append(P(f"New to bank: {c.get('name')} has no account with the Bank; the relationship is proposed by {w.rm}."))
        bs = w.docs("bank_statement")
        if bs:
            tb = []
            for d in bs:
                f = d.get("fields") or {}
                tb.append([f.get("bank_name") or "", str(f.get("account_type") or "").title(), f"{dt(f.get('period_from'))[3:]} – {dt(f.get('period_to'))[3:]}",
                           w.cell(mn(f.get("total_credits")), d["source"], "statement credits"), w.cell(mn(f.get("closing_balance")), d["source"], "closing balance"),
                           w.n(f.get("returned_cheques") or 0, d["source"], "returned cheques")])
            out.append(T(["Bank", "Account", "Period", "Credits (SAR m)", "Closing balance", "Returned cheques"], tb, source="customer's bank statements", widths=[4, 2.6, 3.4, 2.4, 2.4, 2.2]))
    obl = w.docs("other_bank_offer_letter")
    obs = {((d.get("fields") or {}).get("bank_name") or ""): d for d in w.docs("other_bank_statement")}
    if obl or obs:
        tb = []
        for d in obl:
            f = d.get("fields") or {}
            st = obs.get(f.get("bank_name") or "")
            sf = (st or {}).get("fields") or {}
            tb.append([f.get("bank_name") or "", w.cell(mn(f.get("total_limits")), d["source"], "other bank limits"),
                       w.cell(mn(sf.get("total_outstanding")), st["source"], "other bank outstanding") if st else "not provided",
                       cut("; ".join(f"{x.get('facility')} {x.get('pricing') or ''}".strip() for x in (f.get("facilities") or []) if isinstance(x, dict))),
                       dt(f.get("expiry_date")), cut(f.get("security"))])
        for b, st in obs.items():
            if not any(((d.get("fields") or {}).get("bank_name") or "") == b for d in obl):
                sf = st.get("fields") or {}
                tb.append([b, w.cell(mn(sf.get("total_limits")), st["source"], "other bank limits"), w.cell(mn(sf.get("total_outstanding")), st["source"], "other bank outstanding"),
                           "offer letter not provided", "", ""])
        out.append(H("Facilities with other banks (as declared by the customer)"))
        out.append(T(["Bank", "Limits (SAR m)", "Outstanding", "Facilities and pricing", "Valid to", "Security"], tb,
                     source="other banks' offer letters and statements provided by the customer", widths=[3.2, 2, 2, 6, 2.2, 4]))
    out += [P(n) for n in w.notes_for("relationship")]
    return out, []


def _aggregate(name: Any) -> bool:
    """A line of a top-customers table that is a group of customers ("Other hospitals …", "Local customers (96)"), not one name."""
    n = str(name or "").lower()
    return n.startswith(("other", "others", "local customers", "export customers", "gcc export", "various", "remaining")) or bool(re.search(r"customers\s*\(\d+\)", n))


def _same_name(a: Any, b: Any) -> bool:
    n = lambda x: re.sub(r"\b(co|company|est|establishment|llc|trading|the)\b|[^a-z0-9 ]", " ", str(x or "").lower()).split()  # noqa: E731
    x, y = n(a), n(b)
    return bool(x) and x == y


def related(rel: Any) -> bool:
    r = str(rel or "").lower()
    return bool(r) and "third" not in r and "unrelated" not in r and any(k in r for k in ("related", "sister", "group", "affiliate", "associate", "owner", "common"))


def _first(r: dict[str, Any], *ks: str) -> Any:
    return next((r[k] for k in ks if r.get(k) not in (None, "")), None)


def w_financials(w: W) -> tuple[list[dict[str, Any]], list[str]]:
    ps = periods(w)
    if not ps:
        return [P("Audited and in-house financial statements: __not provided__.")], ["financials not provided"]
    lines = [("Revenue", "revenue"), ("Revenue growth %", "growth"), ("Gross profit", "gross_profit"), ("Gross margin %", "gpm"), ("Operating profit", "operating_profit"),
             ("Net profit", "net_profit"), ("Net margin %", "npm"), ("EBITDA", "ebitda"), ("Total assets", "total_assets"),
             ("Trade receivables", "trade_receivables"), ("Inventories", "inventory"), ("Due from related parties", "due_from_related"),
             ("Current ratio (x)", "cr"), ("Working capital", "wc"), ("Bank debt", "debt"), ("of which short-term (incl. CPLTD)", "debt_st"),
             ("of which long-term", "debt_lt"), ("Net worth", "total_equity"), ("Leverage TL/NW (x)", "lev"), ("Gearing bank debt/NW (x)", "gear"),
             ("Debt / EBITDA (x)", "debt_ebitda"), ("Operating cash flow", "operating_cash_flow")]
    rs = [ratios(p["f"], p["months"] or 12) for p in ps]
    prev_aud: dict[str, Any] | None = None
    for p, r in zip(ps, rs):  # revenue growth on the prior audited year (audited periods only: an interim is not comparable)
        rv = num(p["f"].get("revenue"))
        if p["kind"] == "audited":
            pv = num((prev_aud or {}).get("revenue"))
            r["growth"] = (rv / pv - 1) * 100 if rv and pv else None
            prev_aud = p["f"]
        else:
            r["growth"] = None
    tb = []
    for lab, k in lines:
        vals = []
        for p, r in zip(ps, rs):
            if k in r:
                v = r[k]
                v = (v / 1e6 if v is not None else None) if k in ("ebitda", "debt", "debt_st", "debt_lt", "wc") else v
                vals.append(w.cell(v, p["src"], f"{lab} {p['label']}", dp=1 if not k.endswith(("cr", "lev", "debt_ebitda", "gear")) else 2) if v is not None else "–")
            else:
                vals.append(w.cell(mn(p["f"].get(k)), p["src"], f"{lab} {p['label']}") if p["f"].get(k) not in (None, "") else "–")
        if any(v != "–" for v in vals):
            tb.append([lab] + vals)
    hdr = ["SAR m"] + [f"{p['label']} ({'audited' if p['kind'] == 'audited' else p['kind'] or 'in-house'})" for p in ps]
    out = [T(hdr, tb, source="; ".join(dict.fromkeys(p["src"] for p in ps)), widths=[5] + [3] * len(ps))]
    aud = [p for p in ps if p["kind"] == "audited"]
    if aud:
        la = aud[-1]["f"]
        out.append(P(f"Audited by {la.get('auditor') or 'n/a'}; opinion: {str(la.get('opinion') or 'not stated').lower()}"
                     + (f"; Qawaem reference {la.get('qawaem_reference')}" if la.get("qawaem_reference") else "") + f" ({aud[-1]['src']})."))
    # synopsis bullets with PY in brackets
    bl = []
    if len(aud) >= 2:
        a, b = aud[-2], aud[-1]
        fa, fb = a["f"], b["f"]
        ra, rb = ratios(fa), ratios(fb)
        rva, rvb = mn(fa.get("revenue")), mn(fb.get("revenue"))
        if rva and rvb:
            bl.append(f"Revenue {'rose' if rvb >= rva else 'fell'} to {w.m(rvb, b['src'], 'revenue ' + b['label'])} in {b['label']} (PY {w.m(rva, a['src'], 'revenue ' + a['label'])}), "
                      f"{w.pc((rvb / rva - 1) * 100, b['src'], 'revenue growth', sign=True)}; net profit {w.m(mn(fb.get('net_profit')), b['src'], 'net profit')} "
                      f"(PY {w.m(mn(fa.get('net_profit')), a['src'], 'net profit PY')}), net margin {w.pc(rb['npm'], b['src'], 'net margin')} (PY {w.pc(ra['npm'], a['src'], 'net margin PY')}).")
        if rb["lev"] is not None:
            bl.append(f"Net worth {w.m(mn(fb.get('total_equity')), b['src'], 'net worth')} (PY {w.m(mn(fa.get('total_equity')), a['src'], 'net worth PY')}); leverage "
                      f"{w.x(rb['lev'], b['src'], 'leverage')} (PY {w.x(ra['lev'], a['src'], 'leverage PY')}); current ratio {w.x(rb['cr'], b['src'], 'current ratio')} "
                      f"(PY {w.x(ra['cr'], a['src'], 'current ratio PY')}).")
        ca, tr = mn(fb.get("current_assets")), mn(fb.get("trade_receivables"))
        if ca and tr:
            bl.append(f"Trade receivables {w.m(tr, b['src'], 'receivables')} = {w.pc(tr / ca * 100, b['src'], 'receivables share of CA')} of current assets; "
                      f"receivable days {w.n(rb['dso'], b['src'], 'receivable days')} (PY {w.n(ra['dso'], a['src'], 'receivable days PY')}).")
        rps = mn(fb.get("related_party_sales"))
        if rps:
            bl.append(f"Sales to related parties {w.m(rps, b['src'], 'related-party sales')} = {w.pc(rps / rvb * 100, b['src'], 'related-party sales share')} of {b['label']} revenue (note to the accounts).")
        dfr = mn(fb.get("due_from_related"))
        eq = mn(fb.get("total_equity"))
        if dfr and eq:
            bl.append(f"If due from related parties ({w.m(dfr, b['src'], 'due from related')}) is netted off, adjusted net worth is "
                      f"{w.m(eq - dfr, b['src'], 'adjusted net worth')} and adjusted leverage {w.x((mn(fb.get('total_liabilities')) or 0) / (eq - dfr), b['src'], 'adjusted leverage') if eq - dfr > 0 else 'n/m'}.")
            ag_ = w.doc("receivables_ageing")
            tc_ = w.doc("top_customers_suppliers")
            relc = {str(x.get("name")) for x in (((tc_ or {}).get("fields") or {}).get("customers") or []) if isinstance(x, dict) and related(x.get("relationship"))} | \
                {str(e.get("entity_name")) for e in w.rows("b360_entity") if str(e.get("role") or "").lower() in ("associate", "sister", "connected", "related")}
            for x in ((ag_ or {}).get("fields") or {}).get("by_customer") or []:
                if isinstance(x, dict) and any(_same_name(x.get("customer"), n_) for n_ in relc):
                    o_ = mn((num(x.get("b181_365")) or 0) + (num(x.get("over_365")) or 0))
                    if o_ and o_ > 0.5:
                        bl.append(f"Receivables over 180 days from the related party {x.get('customer')}: {w.m(o_, ag_['source'], 'related receivables >180d')} at "
                                  f"{dt(ag_['fields'].get('as_of'))}; not netted above: __credit may net them off as well__.")
    if len(aud) == 1:  # one audited year (thin file): the year's own figures; a prior year compiled but not audited is said
        b = aud[-1]
        fb, rb = b["f"], ratios(b["f"])
        eq, dfr = mn(fb.get("total_equity")), mn(fb.get("due_from_related"))
        bl.append(f"{b['label']}: revenue {w.m(mn(fb.get('revenue')), b['src'], 'revenue')}, net profit {w.m(mn(fb.get('net_profit')), b['src'], 'net profit')} "
                  f"(net margin {w.pc(rb['npm'], b['src'], 'net margin')}); net worth {w.m(eq, b['src'], 'net worth')}, leverage {w.x(rb['lev'], b['src'], 'leverage')}"
                  + (f"; due from related parties {w.m(dfr, b['src'], 'due from related')} = {w.pc(dfr / eq * 100, b['src'], 'due from related share of NW')} of net worth" if dfr and eq else "") + ".")
        prior = next((m for m in w.cf.get("missing", []) if m.get("doc_type") == "audited_fs"), None)
        if prior:
            bl.append(f"Prior year {subj(w, prior.get('subject')) or ''}: {str(prior.get('why') or 'audited statements not provided').rstrip('.')}; growth is not verified on audited figures.")
    inh = [p for p in ps if p["kind"] != "audited"]
    if inh and aud:
        p, a = inh[-1], aud[-1]
        rv = mn(p["f"].get("revenue"))
        if rv and p["months"]:
            ann = rv * 12 / p["months"]
            ra = mn(a["f"].get("revenue"))
            bl.append(f"{p['label']} in-house revenue {w.m(rv, p['src'], 'interim revenue')}, annualised {w.m(ann, p['src'], 'annualised revenue')}"
                      + (f" ({w.pc((ann / ra - 1) * 100, p['src'], 'annualised vs audited', sign=True)} on {a['label']})" if ra else "")
                      + f"; net profit {w.m(mn(p['f'].get('net_profit')), p['src'], 'interim net profit')} (unaudited, prepared by {p['f'].get('prepared_by') or 'management'}).")
            ri = ratios(p["f"], p["months"])
            if ri["debt_ebitda"] is not None:
                bl.append(f"{p['label']} EBITDA {w.m(ri['ebitda'] / 1e6, p['src'], 'interim EBITDA')}; bank debt {w.m(ri['debt'] / 1e6, p['src'], 'interim bank debt')} = "
                          f"{w.x(ri['debt_ebitda'], p['src'], 'interim debt / annualised EBITDA')} annualised EBITDA.")
            else:
                miss = [lab for k, lab in (("depreciation", "depreciation and amortisation"), ("current_portion_ltd", "the current portion of long-term debt"))
                        if p["f"].get(k) in (None, "")]
                if miss:
                    bl.append(f"The {p['label']} in-house statements do not show {' or '.join(miss)}: {p['label']} EBITDA and Debt / EBITDA are not computed"
                              + (" and bank debt may exclude the current portion of long-term debt" if "the current portion of long-term debt" in miss else "")
                              + f"; the {a['label']} audited figures apply.")
    ag = w.doc("receivables_ageing")
    if ag:
        f = ag.get("fields") or {}
        tot = mn(f.get("total"))
        over = sum(mn(f.get(k)) or 0 for k in ("bucket_181_365", "bucket_over_365"))
        if tot:
            bc = [x for x in (f.get("by_customer") or []) if isinstance(x, dict)]
            top = max(bc, key=lambda x: num(x.get("total")) or 0, default=None)
            bl.append(f"Receivables ageing at {dt(f.get('as_of'))}: {w.m(tot, ag['source'], 'receivables ageing total')}, of which over 180 days "
                      f"{w.m(over, ag['source'], 'receivables >180d')} ({w.pc(over / tot * 100, ag['source'], 'share >180d')})"
                      + (f"; largest debtor {top.get('customer')} {w.pc((num(top.get('total')) or 0) / 1e6 / tot * 100, ag['source'], 'top debtor share')}" if top else "") + ".")
    if bl:
        out += [H("Financial synopsis"), BL(bl)]
    out += [P(n) for n in w.notes_for("financials")]
    return out, []


def reconciliation(w: W) -> list[dict[str, Any]]:
    """Revenue across sources over the same 12 months (VAT period): VAT standard-rated sales, statement credits / 1.15, and the
    audited / in-house revenue on a trailing-12-month basis where the periods allow."""
    out = []
    vr = w.doc("vat_returns")
    bs = w.docs("bank_statement")
    vat = None
    if vr:
        f = vr.get("fields") or {}
        rets = [x for x in (f.get("returns") or []) if isinstance(x, dict)]
        zero = sum(num(x.get("zero_rated_sales")) or 0 for x in rets)
        vat = mn((num(f.get("total_taxable_sales")) or 0) + zero) if f.get("total_taxable_sales") is not None else None
    cred = sum(mn((d.get("fields") or {}).get("total_credits")) or 0 for d in bs) if bs else None
    ps = periods(w)
    aud = [p for p in ps if p["kind"] == "audited"]
    inh = [p for p in ps if p["kind"] != "audited"]
    ttm = None
    if aud and inh and inh[-1]["months"] < 12:
        # trailing 12 months to the interim end: interim + (audited FY - same months of FY) ~ interim + FY x (12-m)/12
        a, i = aud[-1], inh[-1]
        if mn(a["f"].get("revenue")) and mn(i["f"].get("revenue")):
            ttm = mn(i["f"].get("revenue")) + mn(a["f"].get("revenue")) * (12 - i["months"]) / 12
    if vat is not None:
        out.append({"item": "VAT sales (standard and zero-rated), 12 months", "value": vat, "source": vr["source"]})
    if cred:
        out.append({"item": "Bank statement credits / 1.15, 12 months", "value": cred / 1.15, "source": "; ".join(d["source"] for d in bs)})
    if ttm is not None:
        out.append({"item": f"Revenue, trailing 12 months to {inh[-1]['label']} (in-house + pro-rated {aud[-1]['label']})", "value": ttm,
                    "source": f"{inh[-1]['src']}; {aud[-1]['src']}"})
    if aud:
        out.append({"item": f"Audited revenue {aud[-1]['label']}", "value": mn(aud[-1]["f"].get("revenue")), "source": aud[-1]["src"]})
    return out


def w_documents(w: W) -> tuple[list[dict[str, Any]], list[str]]:
    cl = I.checklist(w.cf)
    rec = sum(1 for x in cl if x["status"] == "received")
    exp = [x for x in cl if x["status"] == "expired"]
    mis = [x for x in cl if x["status"] == "missing"]
    out = [P(f"Documents on file as at {dt(w.written)}: {rec} received, {len(exp)} expired, {len(mis)} missing against the Bank's checklist of "
             f"{len(cl)} items ({'read by CreditProbe intake' if w.cf.get('origin') == 'intake' else 'as uploaded'}).")]
    rows = [[x["label"] + (f" · {subj(w, x['subject'])}" if x.get("subject") else ""), "__expired__" if x["status"] == "expired" else "__missing__",
             (f"expired {dt(x.get('expiry'))}" if x["status"] == "expired" and x.get("expiry") else (f"dated {dt(x.get('date'))}" if x["status"] == "expired" else x.get("why") or "not provided"))]
            for x in exp + mis]
    if rows:
        out.append(T(["Document", "Status", "Note"], rows, source="the document checklist (PLAN_R16 required list)", widths=[8, 2.5, 7]))
    ic = (w.cf.get("intake") or {}).get("reconciliation") or []
    if ic:
        agree = [t for t in ic if t.get("status") == "agrees"]
        rows2 = [[t.get("title") or "", "__flag__" if (t.get("severity") or 0) >= 2 else str(t.get("status") or ""), str(t.get("sentence") or "")[:260]]
                 for t in sorted(ic, key=lambda t: -(t.get("severity") or 0)) if t.get("status") != "agrees"]
        for t in ic:
            w._rec(t.get("title") or "intake check", str(t.get("status")), t.get("a"), _intake_src(t))  # noqa: SLF001
        out += [H(f"Cross-checks by CreditProbe intake ({len(agree)} agree, {len(ic) - len(agree)} to note)"),
                T(["Check", "Result", "Finding"], rows2 + [[t.get("title") or "", "agrees", str(t.get("sentence") or "")[:160]] for t in agree[:4]],
                  source=f"CreditProbe intake · dd_intake_reconciliation · {w.cf['intake'].get('intake_id')}", widths=[4.5, 1.6, 11.5], size=7.0)]
        return out, ([f"{len(mis)} documents missing"] if mis else []) + ([f"{len(exp)} documents expired"] if exp else [])
    rc = reconciliation(w)
    if len(rc) >= 2:
        base = rc[0]["value"]
        tb = [[r["item"], w.cell(r["value"], r["source"], r["item"]), (f"{(r['value'] / base - 1) * 100:+.1f}%" if base and r is not rc[0] and r["value"] else "base"), r["source"]] for r in rc]
        out += [H("Revenue cross-check"), T(["Measure", "SAR m", "vs VAT", "Source"], tb, source="documents as listed", widths=[6.5, 2, 1.8, 7.5])]
    return out, ([f"{len(mis)} documents missing"] if mis else []) + ([f"{len(exp)} documents expired"] if exp else [])


def intake_checks(w: W, min_sev: int = 2) -> list[dict[str, Any]]:
    return [t for t in ((w.cf.get("intake") or {}).get("reconciliation") or []) if (t.get("severity") or 0) >= min_sev and t.get("sentence")]


def _intake_src(t: dict[str, Any]) -> str:
    ids = sorted({str(e.get("doc_id")) for e in (t.get("evidence") or []) if isinstance(e, dict) and e.get("doc_id")})
    return f"CreditProbe intake check · dd_intake_reconciliation · {t.get('test')}" + (f" ({', '.join(ids[:4])})" if ids else "")


def disclosures(w: W) -> list[str]:
    """What credit will ask, said first by the RM: each from the documents or the Bank's data, with its source. With an intake
    file, intake's reconciliation flags (session i, one engine) come first and this writer skips the topics they cover."""
    out = []
    covered: set[str] = set()
    for t in intake_checks(w, 2):
        if t.get("topic") == "bureau" and re.search(r"overdue SAR 0\.00m", t["sentence"]) and re.search(r"\bCurrent\b", t["sentence"]):
            continue  # a clean bureau report is not a point to disclose
        w._rec(t.get("title") or "intake check", str(t.get("a") if t.get("a") is not None else ""), t.get("a"), _intake_src(t))  # noqa: SLF001
        out.append(f"{t['sentence'].rstrip('.')}." + (" __To be addressed__." if (t.get("severity") or 0) >= 3 else ""))
        covered.add(str(t.get("topic") or ""))
    covered |= {str(t.get("topic") or "") for t in intake_checks(w, 0)}
    # turnover vs revenue growth
    cond = sorted(w.rows("dd_account_conduct"), key=lambda r: str(r.get("month") or ""))
    aud = [p for p in periods(w) if p["kind"] == "audited"]
    tests = {str(t.get("test") or "") for t in intake_checks(w, 0)}
    if len(cond) >= 24 and len(aud) >= 2 and "revenue_growth_vs_credits" not in tests:
        cr_l = sum(num(r.get("credit_turnover_mn")) or 0 for r in cond[-12:])
        cr_p = sum(num(r.get("credit_turnover_mn")) or 0 for r in cond[-24:-12])
        ra, rb = mn(aud[-2]["f"].get("revenue")), mn(aud[-1]["f"].get("revenue"))
        if cr_p and ra and rb:
            g_t, g_r = (cr_l / cr_p - 1) * 100, (rb / ra - 1) * 100
            if g_r - g_t > 10:
                fy = re.sub(r"\D", "", aud[-1]["label"])[:4]
                cy = [r for r in cond if str(r.get("month") or "").startswith(fy)]
                py = [r for r in cond if fy.isdigit() and str(r.get("month") or "").startswith(str(int(fy) - 1))]
                cal = ""
                if len(cy) == 12 and len(py) == 12:
                    a_, b_ = sum(num(r.get("credit_turnover_mn")) or 0 for r in cy), sum(num(r.get("credit_turnover_mn")) or 0 for r in py)
                    cal = (f"; on the calendar year, credit turnover was {w.m(a_, src_row(cy[-1]), 'credit turnover CY')} in CY{fy} against "
                           f"{w.m(b_, src_row(py[-1]), 'credit turnover CY prior')} in CY{int(fy) - 1} ({w.pc((a_ / b_ - 1) * 100, src_row(cy[-1]), 'credit turnover CY growth', sign=True)})")
                out.append(f"Revenue grew {w.pc(g_r, aud[-1]['src'], 'revenue growth')} in {aud[-1]['label']} while credit turnover at the Bank grew "
                           f"{w.pc(g_t, src_row(cond[-1]), 'turnover growth')} over the last 12 months{cal}: __collections from the added sales are not seen in our accounts__; "
                           "business to explain where they are routed.")
    rc = reconciliation(w) if "revenue" not in covered else []
    if len(rc) >= 2 and rc[0]["value"]:
        far = [r for r in rc[1:3] if r["value"] and abs(r["value"] / rc[0]["value"] - 1) > 0.10]
        stm = next((r for r in far if r["item"].startswith("Bank statement credits")), None)
        if stm is not None:
            out.append(f"Bank statement credits of {w.m(stm['value'] * 1.15, stm['source'], 'statement credits 12m')} are "
                       f"{w.pc(stm['value'] / rc[0]['value'] * 100, stm['source'], 'credits share of VAT-inclusive sales', dp=0)} of VAT-inclusive sales "
                       f"({w.m(rc[0]['value'] * 1.15, rc[0]['source'], 'VAT-inclusive sales')} = VAT sales x 1.15): __to be explained__.")
            far = [r for r in far if r is not stm]
        if far:
            out.append("; ".join(f"{r['item']} {w.m(r['value'], r['source'], r['item'])} "
                                 f"({w.pc((r['value'] / rc[0]['value'] - 1) * 100, r['source'], 'gap vs VAT', sign=True)})" for r in far)
                       + f" against VAT sales of {w.m(rc[0]['value'], rc[0]['source'], 'VAT sales')}: __to be explained__.")
    tc = w.doc("top_customers_suppliers")
    if tc:
        cu = [x for x in ((tc.get("fields") or {}).get("customers") or []) if isinstance(x, dict) and not _aggregate(x.get("name"))]
        for x in cu:
            sh = _pct(x.get("share_pct")) or 0
            rp = related(x.get("relationship"))
            ent = next((e for e in w.rows("b360_entity") if _same_name(e.get("entity_name"), x.get("name"))), None)
            if "concentration" in covered and not ent:
                continue  # intake's concentration check says it (one engine per fact); the Borrower 360 join is said here
            if sh >= 30 or (rp and sh >= 10) or (ent and sh >= 10):
                line = (f"{x.get('name')} takes {w.pc(sh, tc['source'], 'customer concentration')} of sales" + (f" and is a {str(x['relationship']).lower()}" if rp else "")
                        + "; terms " + str(x.get("terms") or "not stated"))
                if ent:
                    line += (f"; Borrower 360 lists it in the customer's group as {str(ent.get('role') or 'a connected party').replace('_', ' ')}"
                             + (f" ({ent['credit_status_note']})" if ent.get("credit_status_note") else ""))
                    w._rec(f"{ent.get('entity_name')} group role", str(ent.get("role") or ""), str(ent.get("role") or ""), src_row(ent))  # noqa: SLF001
                out.append(line + (": __related-party concentration__." if (rp or ent) else ": __concentration__."))
    for e in ([] if any(x.startswith("connected_") for x in tests) else w.rows("b360_entity")):
        st = str(e.get("credit_status") or "").lower()
        if st and st not in ("regular", "standard", "performing", "none", "nan", "good"):
            w._rec(f"{e.get('entity_name')} credit status", str(e.get("credit_status")), str(e.get("credit_status")), src_row(e))  # noqa: SLF001
            out.append(f"Group entity {e.get('entity_name')} is {str(e.get('credit_status')).replace('_', ' ')}" + (f" ({e['credit_status_note']})" if e.get("credit_status_note") else "")
                       + ": __contagion to be addressed__.")
    for d in (w.docs("simah_consumer") + w.docs("simah_company")) if "bureau" not in covered else []:
        f = d.get("fields") or {}
        od = mn(f.get("total_overdue"))
        worst = str(f.get("worst_status_24m") or "")
        fac = [x for x in (f.get("facilities") or []) if isinstance(x, dict)]
        flags = [x for x in fac if num(x.get("overdue")) or any(k in str(x.get("status", "")).lower() + str(x.get("remark", "")).lower()
                                                                  for k in ("restructur", "rescheduled", "delinq", "default", "settled", "written"))]
        clean = (not worst) or worst.lower().startswith(("current", "0", "ok", "regular", "none", "no "))
        if (od and od > 0) or flags or not clean:
            who = f.get("full_name") or f.get("customer_name") or d.get("subject")
            bits = []
            if od:
                bits.append(f"overdue {w.m(od, d['source'], 'bureau overdue', dp=2)}")
            if not clean:
                bits.append(f"worst status in 24 months {worst}")
            for x in flags[:2]:
                bits.append(f"{x.get('lender')} {x.get('product')}: {x.get('status')}{(' – ' + str(x['remark'])) if x.get('remark') else ''}")
            out.append(f"SIMAH ({who}, report {dt(f.get('report_date'))}): " + "; ".join(bits) + ": __to be explained by business__.")
    ni = w.doc("nitaqat_certificate") if "saudisation" not in covered else None
    if ni:
        f = ni.get("fields") or {}
        if f.get("band_threshold_pct") is not None and (_pct(f.get("saudisation_pct")) or 0) - (_pct(f.get("band_threshold_pct")) or 0) < 2:
            out.append(f"Saudisation {w.pc(_pct(f.get('saudisation_pct')), ni['source'], 'saudisation')} is within 2 points of the {f.get('nitaqat_band')} band minimum "
                       f"{w.pc(_pct(f.get('band_threshold_pct')), ni['source'], 'band minimum')}: a fall in band restricts visas and government work.")
    pl = w.doc("project_list") if "projects" not in covered else None
    for x in ((pl or {}).get("fields") or {}).get("projects") or []:
        if not isinstance(x, dict):
            continue
        b, r = mn(x.get("billed")), mn(x.get("received"))
        if b and r is not None and b > 5 and r / b < 0.6:
            out.append(f"{x.get('project')}: received {w.m(r, pl['source'], 'project received')} of {w.m(b, pl['source'], 'project billed')} billed "
                       f"({w.pc(r / b * 100, pl['source'], 'collected share')}), retention held {w.m(mn(x.get('retention_held')), pl['source'], 'retention held')}; "
                       f"status: {x.get('status') or 'n/a'}: __collections behind billing__.")
    certs = [] if "projects" in covered else sorted(w.docs("payment_certificate"), key=lambda d: str((d.get("fields") or {}).get("due_date") or ""))
    wd = I._d(w.written)  # noqa: SLF001
    past = [d for d in certs if I._d((d.get("fields") or {}).get("due_date")) and wd and (wd - I._d(d["fields"]["due_date"])).days > 0]  # noqa: SLF001
    if past:
        f0 = past[0]["fields"]
        out.append(f"{len(past)} payment certificates on file are past their due date (oldest {f0.get('certificate_number')} for "
                   f"{w.m(mn(f0.get('net_payable')), past[0]['source'], 'oldest certificate net')}, due {dt(f0.get('due_date'))}): receipt dates to be shown against the account statement.")
    if aud and any("term" in str(i.get("facility") or "").lower() for i in w.ask.get("items", [])):
        fa = aud[-1]["f"]
        eb, fc, cp = ratios(fa)["ebitda"], num(fa.get("finance_cost")), num(fa.get("current_portion_ltd"))
        if eb and fc is not None and cp is not None and fc + cp > 0:
            dscr = eb / (fc + cp)
            note = next((str(x) for x in (fa.get("notes") or []) if re.search(r"covenant|DSCR", str(x), re.I)), "") if isinstance(fa.get("notes"), list) else \
                (str(fa.get("notes")) if re.search(r"covenant|DSCR", str(fa.get("notes") or ""), re.I) else "")
            if dscr < 1.25 or note:
                out.append(f"Debt service coverage on the {aud[-1]['label']} audited accounts is {w.x(dscr, aud[-1]['src'], 'DSCR audited')} (EBITDA "
                           f"{w.m(eb / 1e6, aud[-1]['src'], 'EBITDA for DSCR')} / finance cost {w.m(fc / 1e6, aud[-1]['src'], 'finance cost')} + current portion of "
                           f"long-term debt {w.m(cp / 1e6, aud[-1]['src'], 'CPLTD')})" + (f"; the accounts note: {cut(note)}" if note else "")
                           + (": __below 1.20x; compliance with the current lenders' DSCR covenants to be confirmed from the audited notes__." if dscr < 1.20 else "."))
    ask_m = [i.get("margin_pct") for i in w.ask.get("items", []) if i.get("margin_pct") is not None]
    if ask_m:
        for d in w.docs("other_bank_offer_letter"):
            f = d.get("fields") or {}
            ms = [float(x) for fx in (f.get("facilities") or []) if isinstance(fx, dict)
                  for x in re.findall(r"(?:SAIBOR|SIBOR)\s*\+\s*(\d+(?:\.\d+)?)\s*%", str(fx.get("pricing") or ""), re.I)]
            if ms and min(ask_m) < min(ms) - 0.25:
                out.append(f"Pricing asked, SAIBOR + {min(ask_m):.2f}% (as per RM), is {w.n((min(ms) - min(ask_m)) * 100, d['source'], 'pricing gap bps')} bps below "
                           f"{f.get('bank_name')}'s SAIBOR + {w.pc(min(ms), d['source'], 'other bank margin', dp=2)} ({d['source']}): __below the incumbent's price__.")
    miss = [m for m in w.cf.get("missing", []) if m.get("doc_type")]
    if miss:
        out.append("Not provided: " + "; ".join(f"{I.LABELS.get(m.get('doc_type'), m.get('doc_type'))}{(' (' + subj(w, m.get('subject')) + ')') if m.get('subject') else ''}"
                                                 for m in miss[:8]) + ".")
    return list(dict.fromkeys(out))


def note_checks(w: W) -> list[str]:
    """The RM's notes checked against the documents and the Bank's data (a note that a record contradicts is said plainly)."""
    out = []
    cond = sorted(w.rows("dd_account_conduct"), key=lambda r: str(r.get("month") or ""))[-12:]
    accts = w.rows("dd_customer_account")
    aud = [p for p in periods(w) if p["kind"] == "audited"]
    for ln in w.notes.get("lines", []):
        t = ln["text"]
        m = re.search(r"since\s+((?:19|20)\d\d)", t, re.I)
        opened = min((str(a.get("opened") or "") for a in accts if a.get("opened")), default="")
        if m and opened[:4].isdigit() and m.group(1) != opened[:4]:
            out.append(f"RM note \"{t}\" vs the Bank's records: first account opened {w._rec('account opened', dt(opened), opened, 'Data Domains · dd_customer_account')}: __to be corrected__.")  # noqa: SLF001
        if re.search(r"no (?:returned|bounced) cheques|clean conduct|no past dues?|never (?:late|overdue)", t, re.I) and cond:
            rc = sum(num(r.get("returned_cheques_n")) or 0 for r in cond)
            pdd = max((num(r.get("past_due_days_max")) or 0 for r in cond), default=0)
            if rc or pdd:
                s_ = src_row(cond[-1])
                out.append(f"RM note \"{t}\" vs the Bank's records: {w.n(rc, s_, 'returned cheques 12m')} returned cheques and past dues up to "
                           f"{w.n(pdd, s_, 'past due days 12m')} days in the last 12 months: __the note is contradicted__.")
        if re.search(r"track record|no delays?|never (?:late|delayed)|always (?:paid|on time)|clean (?:history|record)|no overdues?", t, re.I):
            for d in w.docs("simah_company") + w.docs("simah_consumer"):
                f = d.get("fields") or {}
                bad = [x for x in (f.get("facilities") or []) if isinstance(x, dict) and re.search(
                    r"restructur|reschedul|past due|delinq|default|written", f"{x.get('status')} {x.get('remark')}", re.I)]
                for x in bad[:2]:
                    out.append(f"RM note \"{t}\" vs SIMAH ({d['source']}): {x.get('lender')} {x.get('product')} shows \"{x.get('status')}"
                               f"{(' – ' + str(x['remark'])) if x.get('remark') else ''}\": __the note is contradicted; to be disclosed in full__.")
                    w._rec("SIMAH status", str(x.get("status")), str(x.get("status")), d["source"])  # noqa: SLF001
        g = re.search(r"(?:revenue|sales)[^.;]*?\b(?:up|grew|growth of|increase of|rose)\s*(?:by\s*)?(\d+(?:\.\d+)?)\s*%|(\d+(?:\.\d+)?)\s*%\s*(?:revenue|sales)?\s*growth", t, re.I)
        if g:
            claim = float(g.group(1) or g.group(2))
            if len(aud) >= 2 and mn(aud[-2]["f"].get("revenue")):
                act = (mn(aud[-1]["f"].get("revenue")) / mn(aud[-2]["f"].get("revenue")) - 1) * 100
                if abs(act - claim) > 2:
                    out.append(f"RM note \"{t}\" vs the audited accounts: revenue grew {w.pc(act, aud[-1]['src'], 'audited revenue growth')} in {aud[-1]['label']}: __to be corrected__.")
            else:
                out.append(f"RM note \"{t}\": the {claim:g}% growth cannot be verified, {'only ' + aud[-1]['label'] if aud else 'no'} audited statements "
                           "are on file: __prior-year audited statements required__.")
        am = [a_ for a_ in __import__("backend.dealdesk.rm_request.ask", fromlist=["amounts"]).amounts(t)]
        if am and re.search(r"revenue|sales|turnover", t, re.I) and aud and not re.search(r"route|routed|turnover with us|via us|through us", t, re.I):
            rv = mn(aud[-1]["f"].get("revenue"))
            if rv and abs(am[0]["value"] / rv - 1) > 0.10:
                out.append(f"RM note \"{t}\" vs the audited accounts: revenue {w.m(rv, aud[-1]['src'], 'audited revenue')} in {aud[-1]['label']}: __to be reconciled__.")
        if am and re.search(r"route|routed|via us|through us|turnover with us", t, re.I) and cond:
            cr = sum(num(r.get("credit_turnover_mn")) or 0 for r in cond)
            if cr and abs(am[0]["value"] / cr - 1) > 0.10:
                out.append(f"RM note \"{t}\" vs the Bank's records: credit turnover {w.m(cr, src_row(cond[-1]), 'credit turnover 12m')} in the last 12 months: __to be reconciled__.")
    return out


def w_justification(w: W) -> tuple[list[dict[str, Any]], list[str]]:
    out: list[dict[str, Any]] = []
    rn = w.notes_for("justification", "market", "financials", "relationship", "background", "terms", "security")
    pts = []
    aud = [p for p in periods(w) if p["kind"] == "audited"]
    if len(aud) >= 2:
        ra, rb = mn(aud[-2]["f"].get("revenue")), mn(aud[-1]["f"].get("revenue"))
        if ra and rb:
            pts.append(f"{'Growth' if rb >= ra else 'Revenue'}: revenue {'rose to' if rb >= ra else 'fell to'} {w.m(rb, aud[-1]['src'], 'revenue')} in {aud[-1]['label']} (PY {w.m(ra, aud[-2]['src'], 'revenue PY')}), "
                       f"{w.pc((rb / ra - 1) * 100, aud[-1]['src'], 'revenue growth', sign=True)}, net profit {w.m(mn(aud[-1]['f'].get('net_profit')), aud[-1]['src'], 'net profit')}.")
    cond = sorted(w.rows("dd_account_conduct"), key=lambda r: str(r.get("month") or ""))[-12:]
    if cond:
        pdd = max((num(r.get("past_due_days_max")) or 0 for r in cond), default=0)
        rc = sum(num(r.get("returned_cheques_n")) or 0 for r in cond)
        s = src_row(cond[-1])
        pts.append(f"Conduct: {'no past dues' if not pdd else 'past dues up to ' + w.n(pdd, s, 'past due days') + ' days'} and "
                   f"{'no returned cheques' if not rc else w.n(rc, s, 'returned cheques') + (' returned cheque' if rc == 1 else ' returned cheques')} in the last 12 months; "
                   f"credit turnover {w.m(sum(num(r.get('credit_turnover_mn')) or 0 for r in cond), s, 'credit turnover 12m')}.")
    accts = w.rows("dd_customer_account")
    if accts:
        bal = sum(num(_first(a, "balance_mn", "balance_30sep_mn", "closing_balance_mn")) or 0 for a in accts)
        pts.append(f"Deposits: balances of {w.m(bal, 'Data Domains · dd_customer_account', 'deposit balances')} across {len(accts)} accounts with the Bank.")
    vr = w.doc("vat_returns")
    if vr and len(aud) < 2:  # a thin file: the VAT filings are the verified trading record
        f = vr.get("fields") or {}
        rets = [x for x in (f.get("returns") or []) if isinstance(x, dict)]
        late = [x for x in rets if re.search(r"late|penalt|overdue", f"{x.get('status')} {x.get('remark')}", re.I)]
        if rets:
            pts.append(f"VAT: {w.n(len(rets), vr['source'], 'VAT returns filed')} returns on file for {mon(rets[0].get('period'))[:8] or 'the period'}"
                       f"{' – ' + mon(rets[-1].get('period'))[:8] if rets[-1].get('period') else ''}, "
                       + ("none filed late" if not late else f"{len(late)} filed late") + (f"; taxable sales {w.m(mn(f.get('total_taxable_sales')), vr['source'], 'VAT taxable sales')}" if f.get("total_taxable_sales") else "") + ".")
    rows = facility_rows(w)
    tp = _total(rows, "proposed")
    if tp and aud:
        rb = mn(aud[-1]["f"].get("revenue"))
        if rb:
            pts.append(f"Size: proposed limits of {w.m(tp, w.ask_src, 'total proposed')} = {w.pc(tp / rb * 100, aud[-1]['src'], 'limits to revenue')} of {aud[-1]['label']} revenue.")
    out.append(H("Business case"))
    out.append(BL(rn + pts if (rn or pts) else ["Justification not typed: the RM's notes box is empty."]))
    nc = note_checks(w)
    dsc = disclosures(w)
    # one bullet per matter: a SIMAH flag already quoted against a contradicted note is not repeated
    dsc = [x for x in dsc if not (x.startswith("SIMAH (") and any(re.search(re.escape(b.strip()[:40]), y) for y in nc
                                                                    for b in re.split(r";|: __", x.split("): ", 1)[-1]) if len(b.strip()) > 15))]
    ds = nc + dsc
    if ds:
        out += [H("Points disclosed for credit's review"), BL(ds)]
    out.append(P(f"Business recommends approval of the request as above. Prepared by {w.rm} on {dt(w.written)}."))
    return out, [] if (w.notes.get("lines") or []) else ["no RM notes"]


def w_signatures(w: W) -> tuple[list[dict[str, Any]], list[str]]:
    return [SIGN([("Relationship manager", w.rm), ("Unit head, Corporate Banking", ""), ("Regional head", "")]),
            BOX("Business head comments", 3)], []


#: sections written only when they have something to say (Round G: counterparty exposure)
OPTIONAL = ("counterparty",)

SECTIONS = [  # key, anatomy n, heading, voice, writer
    ("header", 1, "Header block", "form", w_header),
    ("action", 2, "Action requested", "business", w_action),
    ("facilities", 3, "Facilities", "business", w_facilities),
    ("security", 4, "Security and support", "business", w_security),
    ("terms", 5, "Terms and conditions", "business", w_terms),
    ("group_exposure", 6, "Group exposure and references", "business", w_group),
    ("counterparty", None, "Counterparty exposure", "business", lambda w: __import__("backend.dealdesk.graph.section", fromlist=["w"]).w_counterparty_request(w)),  # Round G
    ("background", 7, "Background", "business", w_background),
    ("relationship", 8, "Relationship with the bank", "business", w_relationship),
    ("financials", 14, "Financials", "business", w_financials),
    ("documents", None, "Documents and revenue cross-check", "business", w_documents),
    ("justification", None, "RM's justification", "business", w_justification),
    ("signatures", 20, "Signatures", "form", w_signatures),
]
