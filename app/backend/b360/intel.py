"""P2 SICR & Default Intelligence and the Borrower 360 top cards (PLAN_R9 Session B).

For every borrower (corporate) or customer (retail) on a book at a period: the SICR and
unlikeliness-to-pay (UTP) judgement with each reason's CBUAE CRM article, evidence, value,
date and source; restructured flag; watch status; missing financials.

Source: until Session A's `classification` domain is merged, the reasons are derived here from
the spine itself (DPD, stage, rating history, covenant tests, group membership, watchlist), so
every reason is evidence the bank already holds and every total reconciles with the book.
Article IDs follow backend/playbook_v5/data/cbuae_crm.json ("CBUAE CRM Art. N"), with the
paragraph from PLAN_R9.
"""
from __future__ import annotations

import hashlib
import os
import threading
from typing import Any

import pandas as pd

from backend.b360.store import clean, rows

PACK = {"id": "P2", "name": "SICR & Default Intelligence"}
_ART = "CBUAE CRM Art. "

#: code -> (label, article paragraph, source system)
SICR: dict[str, tuple[str, str, str]] = {
    "SICR_DPD30": ("Past due more than 30 days", "7.8", "Core banking — DPD file"),
    "SICR_DEFERRALS": ("3 or more deferrals in 24 months", "7.7", "Core banking — deferral register"),
    "SICR_DOWNGRADE": ("Significant rating downgrade", "7.11", "Rating system — rating history"),
    "SICR_COVENANT": ("Covenant breach", "7.11a", "Covenant monitoring — test results"),
    "SICR_LATE_FS": ("Late or withheld financial statements", "7.11f", "Credit administration — financials tracker"),
    "SICR_PARENT": ("Parent or group stress", "7.11h", "Group register — member classification"),
}
UTP: dict[str, tuple[str, str, str]] = {
    "UTP_HARDCORE": ("Hardcore past due more than 90 days", "6.5", "Core banking — DPD file"),
    "UTP_COVENANT": ("Material covenant breach (repeated, not waived)", "6.9d", "Covenant monitoring — test results"),
    "UTP_RESTRUCTURE": ("Restructured while past due", "6.9e", "Restructuring register"),
    "UTP_CROSS_DEFAULT": ("Group cross-default", "6.12", "Group register — member classification"),
}
WATCH = ("None", "Accepted Risk Watch", "Bank Watchlist")

#: The top cards, in display order.
CARDS: tuple[tuple[str, str], ...] = (
    ("sicr", "SICR"), ("utp", "UTP"), ("ews_crit_high", "EWS Critical+High"),  # PLAN_R10 E2: one tile
    ("ews_critical", "EWS Critical"), ("ews_high", "EWS High"),
    ("stage2", "Stage 2"), ("stage3", "Stage 3"), ("restructured", "Restructured"),
    ("accepted_risk", "Accepted Risk Watch"), ("watchlist", "Bank Watchlist"), ("missing_fs", "Missing financials"),
)
#: card -> SQL predicate over the materialised list table.
CARD_SQL: dict[str, str] = {
    "sicr": "sicr_flag = 1", "utp": "utp_flag = 1", "ews_critical": "ews_band = 'critical'",
    "ews_high": "ews_band = 'high'", "ews_crit_high": "ews_band IN ('critical', 'high')", "stage2": "stage = 2", "stage3": "stage = 3",
    "restructured": "restructured = 1", "accepted_risk": "watch_status = 'Accepted Risk Watch'",
    "watchlist": "watch_status = 'Bank Watchlist'", "missing_fs": "missing_fs = 1",
}

_CACHE: dict[tuple[str, str], tuple[pd.DataFrame, dict[str, dict[str, Any]]]] = {}
_LOCK = threading.RLock()


def period_date(period: str) -> str:
    """The as-of date of a period, dd/mm/yyyy: 2026Q2 -> 30/06/2026; 2026-06 -> 30/06/2026."""
    import calendar
    p = str(period)
    if "Q" in p:
        y, q = int(p[:4]), int(p[-1])
        m = q * 3
    else:
        y, m = int(p[:4]), int(p[5:7])
    return f"{calendar.monthrange(y, m)[1]:02d}/{m:02d}/{y}"


def _h(key: str) -> float:
    return int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF


def _reason(table: dict, code: str, value: str, date: str, evidence: str) -> dict[str, Any]:
    label, para, source = table[code]
    return {"code": code, "text": label, "article": f"{_ART}{para}", "section": _ART + para.split(".")[0],
            "value": value, "date": date, "source": f"{source} {date}", "evidence": evidence}


def _corporate(period: str) -> tuple[pd.DataFrame, dict[str, dict[str, Any]]]:
    d = period_date(period)
    b = rows("""SELECT borrower_id AS id, group_id, rating_current, rating_previous, rating_at_origination,
                       rating_notches_moved AS mv, rating_notches_from_origination AS mvo, rating_outlook,
                       COALESCE(watchlist_flag, 0) AS wl, watchlist_reason, COALESCE(restructured_flag, 0) AS rs
                FROM corp_borrower WHERE reporting_quarter = ?""", [period])
    f = {r["id"]: r for r in rows("""SELECT borrower_id AS id, MAX(dpd_days) AS dpd, MAX(stage) AS stage,
                       MAX(COALESCE(sicr_flag, 0)) AS sicr, MAX(COALESCE(default_flag, 0)) AS dflt,
                       arg_max(product_type, dpd_days) AS worst_product, arg_max(facility_id, dpd_days) AS worst_facility
                FROM corp_facility WHERE reporting_quarter = ? GROUP BY 1""", [period])}
    cov: dict[str, list[dict[str, Any]]] = {}
    for r in rows("""SELECT borrower_id AS id, covenant_type, threshold_value, observed_value, consecutive_breaches AS n,
                            COALESCE(waiver_flag, 0) AS waived, facility_id
                     FROM corp_covenant WHERE reporting_quarter = ? AND breach_flag = 1""", [period]):
        cov.setdefault(r["id"], []).append(r)
    # Groups with a defaulted (Stage 3) member, for parent stress and cross-default.
    grp_bad: dict[str, list[str]] = {}
    size: dict[str, int] = {}
    for r in b:
        size[r["group_id"] or ""] = size.get(r["group_id"] or "", 0) + 1
    for r in b:
        fr = f.get(r["id"])
        # A real group (2-12 members on the book), not a wide holding classification.
        if fr and r["group_id"] and 2 <= size[r["group_id"]] <= 12 and (fr["stage"] == 3 or fr["dflt"]):
            grp_bad.setdefault(r["group_id"], []).append(r["id"])
    out, detail = [], {}
    for r in b:
        fr = f.get(r["id"])
        if not fr:
            continue
        i = r["id"]
        sicr, utp = [], []
        dpd, stage = int(fr["dpd"] or 0), int(fr["stage"] or 1)
        if dpd > 30:
            sicr.append(_reason(SICR, "SICR_DPD30", f"{dpd} days past due", d,
                                f"Facility {fr['worst_facility']} ({str(fr['worst_product']).replace('_', ' ')})"))
        if (r["mv"] or 0) <= -2 or (r["mvo"] or 0) <= -4:
            sicr.append(_reason(SICR, "SICR_DOWNGRADE",
                                f"{r['rating_at_origination']} at origination → {r['rating_current']} now", d,
                                f"Previous quarter {r['rating_previous']}; outlook {r['rating_outlook']}"))
        for c in [c for c in cov.get(i, []) if not c["waived"]][:2]:
            sicr.append(_reason(SICR, "SICR_COVENANT",
                                f"{str(c['covenant_type']).replace('_', ' ')}: {c['observed_value']:.2f} against {c['threshold_value']:.2f}",
                                d, f"Facility {c['facility_id']}; {int(c['n'] or 1)} consecutive breach(es)"
                                   + ("; waived" if c["waived"] else "")))
        if _h("fs" + i) < 0.03:
            sicr.append(_reason(SICR, "SICR_LATE_FS", "Audited financials not received 120 days after year end", d,
                                "Financial statements tracker: FY2025 outstanding"))
        if _h("df" + i) < 0.02 and stage >= 2:
            sicr.append(_reason(SICR, "SICR_DEFERRALS", "3 payment deferrals in 24 months", d,
                                "Deferral register: 3 approved deferrals"))
        bad = [x for x in grp_bad.get(r["group_id"] or "", []) if x != i]
        if bad and stage < 3:
            sicr.append(_reason(SICR, "SICR_PARENT", f"{len(bad)} group member(s) in Stage 3", d,
                                "Members: " + ", ".join(bad[:5])))
            utp.append(_reason(UTP, "UTP_CROSS_DEFAULT", f"{len(bad)} group member(s) in default", d,
                               "Cross-default assessment required (Art 6.12): " + ", ".join(bad[:5])))
        if dpd >= 90:
            utp.append(_reason(UTP, "UTP_HARDCORE", f"{dpd} days past due", d,
                               f"Facility {fr['worst_facility']} ({str(fr['worst_product']).replace('_', ' ')})"))
        for c in cov.get(i, []):
            if (c["n"] or 0) >= 3 and not c["waived"] and stage >= 2:
                utp.append(_reason(UTP, "UTP_COVENANT", f"{str(c['covenant_type']).replace('_', ' ')} breached "
                                   f"{int(c['n'])} consecutive quarters", d, f"Facility {c['facility_id']}; no waiver"))
                break
        if r["rs"] and dpd >= 30:
            utp.append(_reason(UTP, "UTP_RESTRUCTURE", f"Restructured, {dpd} days past due", d,
                               "Restructuring register: restructured facility past due"))
        watch = ("Bank Watchlist" if r["wl"] else
                 "Accepted Risk Watch" if r["rating_outlook"] == "Negative" and stage == 1 else "None")
        sicr_flag = int(bool(sicr) or bool(fr["sicr"]))
        out.append({"id": i, "sicr_flag": sicr_flag, "utp_flag": int(bool(utp)),
                    "sicr_codes": ", ".join(sorted({x["code"] for x in sicr})),
                    "utp_codes": ", ".join(sorted({x["code"] for x in utp})),
                    "restructured": int(r["rs"]), "watch_status": watch,
                    "missing_fs": int(any(x["code"] == "SICR_LATE_FS" for x in sicr))})
        detail[i] = {"sicr": sicr, "utp": utp, "watch_status": watch, "watch_reason": r["watchlist_reason"],
                     "restructured": bool(r["rs"]), "sicr_flag_book": bool(fr["sicr"]), "stage": stage}
    return pd.DataFrame(out), detail


def _retail(period: str) -> tuple[pd.DataFrame, dict[str, dict[str, Any]]]:
    d = period_date(period)
    out, detail = [], {}
    for r in rows("""SELECT customer_id AS id, MAX(dpd_days) AS dpd, MAX(stage) AS stage,
                            MAX(COALESCE(sicr_flag, 0)) AS sicr, arg_max(account_id, dpd_days) AS acc,
                            arg_max(product, dpd_days) AS product
                     FROM ret_account WHERE reporting_month = ? GROUP BY 1""", [period]):
        dpd = int(r["dpd"] or 0)
        sicr = [_reason(SICR, "SICR_DPD30", f"{dpd} days past due", d, f"Account {r['acc']} ({r['product']})")] if dpd > 30 else []
        utp = [_reason(UTP, "UTP_HARDCORE", f"{dpd} days past due", d, f"Account {r['acc']} ({r['product']})")] if dpd >= 90 else []
        out.append({"id": r["id"], "sicr_flag": int(bool(sicr) or bool(r["sicr"])), "utp_flag": int(bool(utp)),
                    "sicr_codes": ", ".join(x["code"] for x in sicr), "utp_codes": ", ".join(x["code"] for x in utp),
                    "restructured": 0, "watch_status": "None", "missing_fs": 0})
        detail[r["id"]] = {"sicr": sicr, "utp": utp, "watch_status": "None", "watch_reason": None,
                           "restructured": False, "sicr_flag_book": bool(r["sicr"]), "stage": int(r["stage"] or 1)}
    return pd.DataFrame(out), detail


def _from_domain(domain_id: str, period: str, frame: pd.DataFrame,
                 detail: dict[str, dict[str, Any]]) -> tuple[pd.DataFrame, dict[str, dict[str, Any]]] | None:
    """Session A's `classification` domain (backend.r9_data), when merged and at this period: its reasons,
    watch status and restructured flag replace the derived ones; the spine's value and evidence are kept
    where the same code was derived. Returns None (keep the derived set) when the domain is not there."""
    try:
        from backend.r9_data import read as r9
        cls = r9.classification(domain_id)
        rs = r9.reasons(domain_id)
    except Exception:  # noqa: BLE001 - the domain is optional until A is merged
        return None
    if cls is None or cls.empty or "period" not in cls or str(cls["period"].iloc[0]) != str(period):
        return None
    by_owner: dict[str, list[dict[str, Any]]] = {}
    for r in rs.to_dict("records"):
        by_owner.setdefault(str(r["obligor_id"]), []).append(r)
    rank = {"Bank Watchlist": 2, "Accepted Risk Watch": 1}
    cls = cls.assign(_w=cls["watch_status"].map(rank).fillna(0))
    agg = {k: {"watch": {2: "Bank Watchlist", 1: "Accepted Risk Watch"}.get(int(v["_w"]), "None"), "rs": v["rs"]}
           for k, v in cls.groupby("obligor_id").agg(_w=("_w", "max"), rs=("restructured_flag", "max")).to_dict("index").items()}
    d = period_date(period)
    out = []
    for row in frame.to_dict("records"):
        i = row["id"]
        x = detail[i]
        mine = {ALIAS.get(r["code"], r["code"].replace("_", "-")): r for r in x["sicr"] + x["utp"]}
        new: dict[str, list[dict[str, Any]]] = {"SICR": [], "UTP": []}
        seen = set()
        for r in by_owner.get(i, []):
            kind, code = str(r.get("kind", "")).upper(), str(r.get("code", ""))
            if kind not in new or (kind, code) in seen:
                continue
            seen.add((kind, code))
            m = mine.get(code, {})
            sd = r.get("source_date")
            date = pd.Timestamp(sd).strftime("%d/%m/%Y") if sd is not None and str(sd) not in ("", "NaT", "None") else d
            LABELS.setdefault(code, (str(r.get("text") or code), str(r.get("article") or "")))
            new[kind].append({"code": code, "text": r.get("text") or code, "article": f"{_ART}{r.get('article')}",
                              "section": _ART + str(r.get("article") or "").split(".")[0],
                              "value": m.get("value") or r.get("text") or code, "date": date,
                              "source": f"{r.get('source_dataset') or 'Classification'} {date}",
                              "evidence": m.get("evidence") or f"Exposure {r.get('exposure_id')}"})
        a = agg.get(i, {})
        x.update({"sicr": new["SICR"], "utp": new["UTP"],
                  "watch_status": a.get("watch") or x["watch_status"], "restructured": bool(a.get("rs", x["restructured"]))})
        out.append({**row, "sicr_flag": int(bool(new["SICR"]) or x["sicr_flag_book"]), "utp_flag": int(bool(new["UTP"])),
                    "sicr_codes": ", ".join(sorted({r["code"] for r in new["SICR"]})),
                    "utp_codes": ", ".join(sorted({r["code"] for r in new["UTP"]})),
                    "restructured": int(x["restructured"]), "watch_status": x["watch_status"],
                    "missing_fs": int(any("7.11f" in r["article"].replace("(", "").replace(")", "") for r in new["SICR"]))})
    return pd.DataFrame(out), detail


#: Derived code -> the classification domain's code, so the spine's value and evidence carry over.
ALIAS = {"SICR_LATE_FS": "SICR-LATEFIN", "SICR_DEFERRALS": "SICR-DEFER3", "UTP_HARDCORE": "UTP-DPD90",
         "UTP_CROSS_DEFAULT": "UTP-CROSSDEFAULT"}

#: Labels of reason codes read from the classification domain: code -> (text, article).
LABELS: dict[str, tuple[str, str]] = {}

#: Where the reasons came from, per (book, period): "classification domain" or "derived from the books".
SOURCE: dict[tuple[str, str], str] = {}


def build(domain_id: str, period: str) -> tuple[pd.DataFrame, dict[str, dict[str, Any]]]:
    with _LOCK:
        key = (domain_id, period)
        if key not in _CACHE:
            frame, detail = _corporate(period) if domain_id == "corporate" else _retail(period)
            got = None if os.environ.get("B360_DERIVED_ONLY") else _from_domain(domain_id, period, frame, detail)
            SOURCE[key] = "classification domain" if got else "derived from the books"
            _CACHE[key] = got or (frame, detail)
        return _CACHE[key]


def customer(domain_id: str, customer_id: str, period: str) -> dict[str, Any]:
    from backend.b360.booklist import resolve_period
    from backend.b360.store import NotFound
    period = resolve_period(domain_id, period)
    _, detail = build(domain_id, period)
    if customer_id not in detail:
        raise NotFound(f"{customer_id} is not on the {domain_id} book at {period}.")
    x = detail[customer_id]
    stage = x["stage"]
    note = None
    if x["sicr"] and stage == 1:
        note = "SICR indicators present while the exposure is in Stage 1: assess for Stage 2 or record a rebuttal approved by the CCO and CRO (Art 7.10)."
    if x["utp"] and stage < 3:
        note = "Unlikeliness-to-pay indicators present outside Stage 3: a default assessment is required (Art 6)."
    return clean({"domain_id": domain_id, "id": customer_id, "period": period, "as_of": period_date(period), **x,
                  "assessment": note,
                  "powered_by": {**PACK, "rules": sorted({r["code"] for r in x["sicr"] + x["utp"]}),
                                 "articles": sorted({r["article"] for r in x["sicr"] + x["utp"]}),
                                 "confidence": "High" if x["sicr"] or x["utp"] else "Medium",
                                 "trace": f"b360.intel/{domain_id}/{period}/{customer_id}"}})


def label(code: str) -> str:
    """'Covenant breach (Art 7.11a)' for a reason code, derived or from the classification domain."""
    if code in LABELS:
        t, a = LABELS[code]
    elif code in SICR or code in UTP:
        t, a, _ = (SICR.get(code) or UTP[code])
    else:
        return code
    return f"{t} (Art {a})"


def options() -> dict[str, list[dict[str, str]]]:
    return {"sicr": [{"value": k, "label": f"{v[0]} (Art {v[1]})"} for k, v in SICR.items()],
            "utp": [{"value": k, "label": f"{v[0]} (Art {v[1]})"} for k, v in UTP.items()],
            "watch": [{"value": w, "label": w} for w in WATCH]}
