"""P1 CBUAE CRM Intelligence in Lenses (PLAN_R9 Session D).

  LIBRARY      the CBUAE CRM metric library: every obligation the Standards set that a dashboard can measure, with its
               definition, formula, data fields, article, frequency, threshold and whether the bank's data carries it
               (available / partial / data gap).
  read_upload  an uploaded circular -> obligations by article, each mapped to library metrics. The CBUAE Credit Risk
               Management Standards are recognised by their SHA-256 and mapped from the curated pack (instant,
               reviewed); any other file goes through the general mapper (articles and "must/shall" sentences matched to
               the library by keywords), stated as such.
  dashboard    the lens spec of the CRM dashboard and its findings (5-7, each with a number and an article), computed
               from the books and the CRM breach checks (backend.regulatory.crm_checks) at the moment it is built.

Everything is deterministic: the same books and the same file give the same answer.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import re
import time
from typing import Any

PACK = {"id": "P1", "name": "CBUAE CRM Intelligence", "version": "1.0",
        "source": "CBUAE Credit Risk Management Standards", "href": "/policy-docs?doc=pd_cbuae_crm"}

V5 = pathlib.Path(__file__).resolve().parents[2]
CRM_JSON = V5 / "backend" / "playbook_v5" / "data" / "cbuae_crm.json"
#: The circular Anne drops into the chat (demo_inputs/policy/CBUAE_Credit_Risk_Management_Standards_EN_5996.pdf).
KNOWN = {"3c52398208e39a4215e919feb46cec6b2e819f683b5ee4e5de0f527d861f28a2": "cbuae-crm-5996"}

A = "Art. "
# status: available = computed from the books today; partial = computed with a proxy or on one book;
# gap = needs a field the books do not carry yet (the R9 data domains add most of them).
_L: list[tuple[str, str, str, str, str, str, str, str, str, str, str]] = [
    # id, group, name, definition, formula, fields, article, frequency, threshold, status, lens metric
    ("CRM-M01", "Classification", "Stage mix (share of EAD)", "Share of exposure in Stage 1, 2 and 3", "EAD(stage s) / EAD",
     "stage, ead", A + "9.2", "Monthly", "Board report on movement", "available", "stage2_share"),
    ("CRM-M02", "Classification", "Stage migration matrix", "Exposure moving between stages quarter on quarter", "EAD(s0 -> s1) / EAD(s0)",
     "stage, previous stage, ead", A + "9.5", "Quarterly", "Report every transfer", "available", ""),
    ("CRM-M03", "Classification", "DPD buckets", "Exposure by days past due: 0, 1-29, 30-59, 60-89, 90+", "EAD by DPD bucket",
     "dpd_days, ead", A + "9.5", "Monthly", "30+ SICR, 90+ default", "available", "dpd30_share"),
    ("CRM-M04", "Classification", "Stage 3 sub-buckets", "Stage 3 by time in default: <1y, 1-2y, 2-4y, 4y+", "EAD(stage 3) by years in Stage 3",
     "stage, stage-3 date, ead", A + "9.23", "Quarterly", "Floor steps at 4 years", "available", "stage3_share"),
    ("CRM-M05", "Classification", "NPL ratio", "Non-performing (Stage 3) exposure over total exposure", "EAD(stage 3) / EAD",
     "stage, ead", A + "12.3", "Monthly", "> 5% reported to the Board", "available", "npl_ratio"),
    ("CRM-M06", "Classification", "90+ DPD not in Stage 3", "Facilities 90+ days past due outside Stage 3", "count(dpd >= 90 and stage < 3)",
     "dpd_days, stage", A + "6.4", "Monthly", "Zero", "available", "dpd90_share"),
    ("CRM-M07", "Classification", "Upgrades from Stage 3 to Stage 1", "Facilities moved straight from Stage 3 to Stage 1", "count(s0 = 3 and s1 = 1)",
     "stage, previous stage", A + "9.11", "Quarterly", "Zero", "available", ""),
    ("CRM-M08", "SICR", "30+ DPD not in Stage 2", "Facilities 30+ days past due still in Stage 1", "count(dpd >= 30 and stage = 1)",
     "dpd_days, stage", A + "7.8", "Monthly", "Zero unless rebutted", "available", "dpd30_ead"),
    ("CRM-M09", "SICR", "3+ deferrals in 24 months", "Obligors with three or more payment deferrals in 24 months", "count(deferrals_24m >= 3)",
     "deferrals in 24 months", A + "7.7", "Monthly", "Stage 2", "gap", ""),
    ("CRM-M10", "SICR", "SICR rebuttals approved by CCO and CRO", "Rebutted 30+ DPD SICR cases and their sign-offs", "count(rebutted) by sign-off",
     "sicr_flag, rebuttal, approvers", A + "7.10", "Quarterly", "Both signatures", "gap", ""),
    ("CRM-M11", "SICR", "Stage 2 share", "Exposure in Stage 2 over total exposure", "EAD(stage 2) / EAD",
     "stage, ead", A + "7.2", "Monthly", "Trend reviewed by the Board", "available", "stage2_share"),
    ("CRM-M12", "SICR", "Rating downgrades", "Obligors downgraded in the quarter", "count(notches moved > 0)",
     "rating, previous rating", A + "7.11", "Quarterly", "Bank trigger CP-3.3", "available", "downgraded"),
    ("CRM-M13", "SICR", "Covenant breaches", "Covenant breaches recorded on the book", "sum(covenant breaches)",
     "covenant breaches", A + "7.11", "Quarterly", "Assess SICR", "available", "covenant_breaches"),
    ("CRM-M14", "Provisioning", "Stage 1 + 2 provisions against 1.5% of CRWA", "Collective provisions over credit RWA", "ECL(stage 1, 2) / CRWA",
     "ecl, stage, crwa", A + "9.21", "Quarterly", ">= 1.50%", "gap", ""),
    ("CRM-M15", "Provisioning", "Stage 3 wholesale floor shortfall", "Stage 3 provision below the wholesale floor after haircuts", "sum(max(0, floor - ECL))",
     "stage, ecl, collateral, haircut, stage-3 date", A + "9.23", "Quarterly", "Zero shortfall", "available", ""),
    ("CRM-M16", "Provisioning", "Stage 3 retail floor shortfall", "Retail Stage 3 provision below the floor by DPD", "sum(max(0, floor(dpd) - ECL))",
     "dpd_days, ecl, collateral", A + "9.24", "Monthly", "Zero shortfall", "available", ""),
    ("CRM-M17", "Provisioning", "ECL coverage", "Expected credit loss over exposure", "ECL / EAD",
     "ecl, ead", A + "9.2", "Monthly", "By stage, trended", "available", "coverage"),
    ("CRM-M18", "Provisioning", "Interest in suspense", "Interest and fees 90+ days past due held in suspense", "sum(interest 90+ DPD)",
     "interest, fees, dpd", A + "9.19", "Monthly", "100% provided", "gap", ""),
    ("CRM-M19", "Provisioning", "Cost of risk", "Change in ECL plus write-offs over exposure", "(dECL + write-offs) / EAD",
     "ecl, write-offs, ead", A + "9.2", "Quarterly", "Within appetite", "available", "cost_of_risk"),
    ("CRM-M20", "Restructuring", "Restructured exposure (distressed / non-distressed)", "Restructured facilities by type", "EAD(restructured) by type",
     "restructured flag, type", A + "8.3", "Monthly", "Distressed: Stage 3", "partial", ""),
    ("CRM-M21", "Restructuring", "Distressed restructured in Stage 1", "Distressed restructurings classified Stage 1", "count(restructured and stage = 1)",
     "restructured flag, stage", A + "9.30", "Quarterly", "Zero", "available", ""),
    ("CRM-M22", "Restructuring", "Standstill longer than 90 days", "Standstill arrangements open more than 90 days", "count(standstill_days > 90)",
     "standstill start", A + "8.7", "Monthly", "Zero without approval", "gap", ""),
    ("CRM-M23", "Restructuring", "3+ restructurings", "Obligors restructured three or more times", "count(restructurings >= 3)",
     "restructuring count", A + "9.29", "Quarterly", "Stage 3", "gap", ""),
    ("CRM-M24", "Restructuring", "Probation breaches", "Back to Stage 1 inside the probation period", "count(cure before probation end)",
     "stage history, instalments", A + "9.34", "Quarterly", "Zero", "available", ""),
    ("CRM-M25", "Default", "Hardcore overdraft > 90 days", "Overdrafts with no credit turnover for 90 days", "count(hardcore days > 90)",
     "overdraft, turnover", A + "6.5", "Monthly", "Default", "gap", ""),
    ("CRM-M26", "Default", "Unlikeliness to pay (UTP) indicators", "Obligors with a UTP indicator and no default", "count(utp_flag and stage < 3)",
     "utp_flag, utp reasons", A + "6.8", "Monthly", "Assess default", "gap", ""),
    ("CRM-M27", "Default", "Cross-default groups", "Borrowers in default on a material facility with others performing", "count(borrower)",
     "borrower, facility, stage, ead", A + "6.12", "Quarterly", "Zero", "available", ""),
    ("CRM-M28", "Default", "Stage 3 older than 5 years", "Stage 3 held more than 5 years without a write-off", "count(years in stage 3 > 5)",
     "stage-3 date, write-off", A + "12.5", "Annual", "Write off", "available", ""),
    ("CRM-M29", "Concentration", "Top 20 share", "Exposure of the 20 largest obligors over total", "EAD(top 20) / EAD",
     "obligor, ead", A + "11.4", "Monthly", "Within appetite", "available", ""),
    ("CRM-M30", "Concentration", "Sector concentration (HHI)", "Herfindahl index of exposure by sector", "sum(share^2)",
     "sector, ead", A + "11.4", "Monthly", "Within appetite", "available", ""),
    ("CRM-M31", "Concentration", "Related-party exposure", "Exposure to related parties and staff-linked obligors", "EAD(related)",
     "related-party register", A + "2.9", "Quarterly", "Board approved", "gap", ""),
    ("CRM-M32", "Concentration", "Exposures > 10% / 5% of Tier 1", "Large exposures needing Board or BCC approval", "count(EAD / Tier 1 > 10%)",
     "group, ead, tier 1", A + "2.6", "Quarterly", "Board / BCC approval", "gap", ""),
    ("CRM-M33", "Governance", "Credit exceptions and their performance", "Approved exceptions and how those facilities perform", "count(exceptions), DPD of them",
     "exceptions register", A + "3.20", "Quarterly", "Reported to the Board", "gap", ""),
    ("CRM-M34", "Governance", "Annual reviews overdue", "Wholesale obligors past their annual review date", "count(today - review date > 12m)",
     "review date", A + "4.3", "Monthly", "Zero", "gap", ""),
    ("CRM-M35", "Governance", "Ratings older than 12 months", "Obligors whose rating was not refreshed in 12 months", "count(rating age > 12m)",
     "rating date", A + "11.3", "Monthly", "Zero", "gap", ""),
    ("CRM-M36", "Governance", "Collateral valuations overdue", "Stage 3 collateral valued more than 12 (6) months ago", "count(valuation age > limit)",
     "valuation date, collateral type", A + "10.11", "Monthly", "Zero", "available", ""),
    ("CRM-M37", "Governance", "Haircuts below the Table 4 minimum", "Stage 3 collateral haircut below the minimum", "count(haircut < min)",
     "collateral, haircut, stage-3 date", A + "10.8", "Quarterly", "Zero", "available", ""),
    ("CRM-M38", "Governance", "CRO independent reviews", "Material proposals reviewed by the CRO before approval", "count(reviewed) / count(material)",
     "proposal, CRO review", A + "4.9", "Quarterly", "100%", "gap", ""),
    ("CRM-M39", "EWS", "Early Warning bucket mix", "Exposure by Early Warning band", "EAD by band",
     "ews band, ead", A + "11.6", "Weekly", "Critical and High reviewed", "available", "severe_ead_share"),
    ("CRM-M40", "EWS", "Watchlist names", "Obligors on the Bank Watchlist", "count(watchlist)",
     "watchlist flag", A + "11.6", "Monthly", "Reviewed monthly", "available", "watchlist"),
    ("CRM-M41", "EWS", "Accepted Risk Watch missed items", "Watch items past their due date", "count(status = missed)",
     "watch items", A + "11.6", "Monthly", "Escalate at 2+", "gap", ""),
    ("CRM-M42", "EWS", "High or critical warned obligors", "Obligors in the High or Critical Early Warning band", "count(band in high, critical)",
     "ews band", A + "11.6", "Weekly", "Action plan each", "available", "high_critical"),
    ("CRM-M43", "Models", "PD and LGD parameters", "EAD-weighted 12-month PD and LGD", "wavg(PD), wavg(LGD)",
     "pd, lgd, ead", A + "13.2", "Quarterly", "Validated annually", "available", "pd"),
    ("CRM-M44", "Classification", "Stage 3 share above 5% (Board report)", "Stage 3 share of the book against the Board trigger", "EAD(stage 3) / EAD vs 5%",
     "stage, ead", A + "12.3", "Quarterly", "<= 5% or Board report", "available", "stage3_share"),
]

#: Which data domain (PLAN_R9 Session A) closes each gap once v5/r9-data is merged.
CLOSES = {"CRM-M09": "classification", "CRM-M10": "classification", "CRM-M14": "collateral", "CRM-M18": "deposits",
          "CRM-M20": "classification", "CRM-M22": "collateral", "CRM-M23": "collateral", "CRM-M25": "deposits",
          "CRM-M26": "classification", "CRM-M31": "relationships", "CRM-M32": "collateral", "CRM-M33": "origination",
          "CRM-M34": "classification", "CRM-M35": "classification", "CRM-M38": "proposals", "CRM-M41": "watch"}

LIBRARY: list[dict[str, Any]] = [
    {"id": i, "group": g, "name": n, "definition": d, "formula": f, "fields": fl, "article": "CBUAE CRM " + a,
     "frequency": fr, "threshold": th, "status": st, "lens_metric": lm, "closes_with": CLOSES.get(i, "")}
    for (i, g, n, d, f, fl, a, fr, th, st, lm) in _L]
BY_ID = {m["id"]: m for m in LIBRARY}

#: The R9 data domains (Session A, backend.r9_data) that are loaded close these gaps; watch (C) and proposals (E)
#: live in their own services and stay gaps here.
R9_DOMAINS = {"classification", "collateral", "relationships", "deposits", "origination"}


def _apply_domains() -> None:
    try:
        from backend.r9_data import read as r9

        r9.manifest()
    except Exception:  # noqa: BLE001 - without the domains the gaps stay gaps
        return
    for m in LIBRARY:
        if m["status"] == "gap" and m["closes_with"] in R9_DOMAINS:
            m["status"] = "available"
            m["source"] = f"R9 data domain: {m['closes_with']}"


_apply_domains()
GROUPS = list(dict.fromkeys(m["group"] for m in LIBRARY))


def _art_major(article: str) -> int:
    m = re.search(r"(\d+)", article.replace("CBUAE CRM", ""))
    return int(m.group(1)) if m else 0


def library() -> dict[str, Any]:
    counts = {s: sum(1 for m in LIBRARY if m["status"] == s) for s in ("available", "partial", "gap")}
    return {"pack": PACK, "metrics": LIBRARY, "groups": GROUPS, "counts": counts, "total": len(LIBRARY)}


# ------------------------------------------------------------------ mapping a circular to the library
#: Article -> library metrics (the curated P1 mapping of the CBUAE CRM Standards).
ARTICLE_METRICS: dict[int, list[str]] = {
    1: [], 2: ["CRM-M31", "CRM-M32"], 3: ["CRM-M33"], 4: ["CRM-M34", "CRM-M38"], 5: ["CRM-M38"],
    6: ["CRM-M06", "CRM-M25", "CRM-M26", "CRM-M27"], 7: ["CRM-M08", "CRM-M09", "CRM-M10", "CRM-M11", "CRM-M12", "CRM-M13"],
    8: ["CRM-M20", "CRM-M22", "CRM-M23"], 9: ["CRM-M01", "CRM-M02", "CRM-M03", "CRM-M04", "CRM-M07", "CRM-M14", "CRM-M15",
                                              "CRM-M16", "CRM-M17", "CRM-M18", "CRM-M21", "CRM-M24"],
    10: ["CRM-M36", "CRM-M37"], 11: ["CRM-M29", "CRM-M30", "CRM-M35", "CRM-M39", "CRM-M40", "CRM-M41", "CRM-M42"],
    12: ["CRM-M05", "CRM-M28", "CRM-M44"], 13: ["CRM-M43"],
}
KEYWORDS: dict[str, list[str]] = {
    "CRM-M01": ["stage 1", "stage 2", "stage 3", "staging"], "CRM-M02": ["migration", "transfer"], "CRM-M03": ["days past due", "dpd"],
    "CRM-M05": ["non-performing", "npl"], "CRM-M06": ["90 days"], "CRM-M08": ["30 days"], "CRM-M09": ["deferral"],
    "CRM-M10": ["rebut"], "CRM-M12": ["downgrade"], "CRM-M13": ["covenant"], "CRM-M14": ["risk-weighted", "1.5%", "1.50%"],
    "CRM-M15": ["provision", "floor"], "CRM-M18": ["suspense", "interest"], "CRM-M20": ["restructur"], "CRM-M22": ["standstill"],
    "CRM-M25": ["overdraft"], "CRM-M26": ["unlikel"], "CRM-M27": ["cross-default", "cross default"], "CRM-M28": ["write-off", "write off"],
    "CRM-M29": ["concentration", "large exposure"], "CRM-M31": ["related part"], "CRM-M32": ["tier 1", "board approval"],
    "CRM-M33": ["exception"], "CRM-M34": ["annual review"], "CRM-M35": ["rating"], "CRM-M36": ["valuation"], "CRM-M37": ["haircut"],
    "CRM-M38": ["chief risk officer", "cro"], "CRM-M39": ["early warning"], "CRM-M40": ["watchlist", "watch list"], "CRM-M43": ["model"],
}
OBLIGES = re.compile(r"\b(must|shall|should|required to|are expected to)\b", re.I)


def _coverage(ids: list[str]) -> str:
    st = [BY_ID[i]["status"] for i in ids if i in BY_ID]
    if not st:
        return "qualitative"
    if all(s == "available" for s in st):
        return "available"
    if any(s in ("available", "partial") for s in st):
        return "partial"
    return "data gap"


def _crm_pack() -> dict[str, Any]:
    return json.loads(CRM_JSON.read_text())


def _short(text: str, n: int = 220) -> str:
    t = re.sub(r"\s+", " ", text).strip()
    return t if len(t) <= n else t[: n - 1].rsplit(" ", 1)[0] + "…"


def _known_mapping() -> dict[str, Any]:
    """The reviewed P1 mapping of the CBUAE CRM Standards: every article, its obligations (the clauses that oblige),
    and the library metrics that measure them."""
    pack = _crm_pack()
    arts: list[dict[str, Any]] = []
    for sec in pack["sections"]:
        m = re.search(r"Art\. (\d+)", sec["section"])
        if not m:
            continue
        n = int(m.group(1))
        clauses = [c for c in pack["clauses"] if c.get("section") == sec["section"]]
        obliging = [c for c in clauses if OBLIGES.search(c.get("rule", ""))]
        metric_ids = ARTICLE_METRICS.get(n, [])
        obligations = []
        for c in obliging:
            low = c["rule"].lower()
            ids = [i for i in metric_ids if any(k in low for k in KEYWORDS.get(i, []))]
            obligations.append({"clause": c["clause"].replace("CBUAE CRM ", ""), "text": _short(c["rule"]), "metrics": ids,
                                "coverage": _coverage(ids) if ids else "qualitative"})
        arts.append({"article": f"Art. {n}", "number": n, "title": sec["title"].split(": ", 1)[-1], "clauses": len(clauses),
                     "obligations": len(obliging), "metrics": [{"id": i, "name": BY_ID[i]["name"], "status": BY_ID[i]["status"],
                                                              "closes_with": BY_ID[i]["closes_with"]} for i in metric_ids],
                     "coverage": _coverage(metric_ids) if metric_ids else "qualitative", "items": obligations[:8]})
    return {"document": pack["title"], "reference": "CBUAE CRM", "articles": arts}


def _general_mapping(text: str, name: str) -> dict[str, Any]:
    """Any other circular: split by 'Article N' headings, keep the sentences that oblige, match them to the library."""
    chunks = re.split(r"\n\s*(?=Article\s+\d+\b)", text)
    arts: list[dict[str, Any]] = []
    for ch in chunks:
        m = re.match(r"Article\s+(\d+)\s*[:.\-–]?\s*([^\n]{0,80})", ch.strip())
        n = int(m.group(1)) if m else 0
        title = (m.group(2).strip() if m else "") or (f"Article {n}" if n else "General")
        sents = [s for s in re.split(r"(?<=[.;])\s+", ch) if OBLIGES.search(s)]
        items, ids_all = [], []
        for s in sents:
            low = s.lower()
            ids = [i for i, kws in KEYWORDS.items() if any(k in low for k in kws)]
            ids_all.extend(ids)
            items.append({"clause": f"{n}" if n else "-", "text": _short(s), "metrics": ids, "coverage": _coverage(ids) if ids else "qualitative"})
        if not items:
            continue
        uniq = list(dict.fromkeys(ids_all))
        arts.append({"article": f"Art. {n}" if n else "General", "number": n, "title": _short(title, 70), "clauses": len(sents),
                     "obligations": len(items), "metrics": [{"id": i, "name": BY_ID[i]["name"], "status": BY_ID[i]["status"],
                                                           "closes_with": BY_ID[i]["closes_with"]} for i in uniq],
                     "coverage": _coverage(uniq) if uniq else "qualitative", "items": items[:8]})
    merged: dict[str, dict[str, Any]] = {}
    for a in arts:  # the same article split by page breaks
        if a["article"] in merged:
            b = merged[a["article"]]
            b["obligations"] += a["obligations"]
            b["clauses"] += a["clauses"]
            b["items"] = (b["items"] + a["items"])[:8]
            ids = list(dict.fromkeys([x["id"] for x in b["metrics"]] + [x["id"] for x in a["metrics"]]))
            b["metrics"] = [{"id": i, "name": BY_ID[i]["name"], "status": BY_ID[i]["status"], "closes_with": BY_ID[i]["closes_with"]} for i in ids]
            b["coverage"] = _coverage(ids) if ids else "qualitative"
        else:
            merged[a["article"]] = a
    return {"document": pathlib.Path(name).stem.replace("_", " "), "reference": "", "articles": list(merged.values())[:40]}


def _quick_text(name: str, data: bytes, pages: int | None = None) -> tuple[str, int]:
    """The file's text (all pages, or the first `pages`) and its page count."""
    ext = pathlib.Path(name).suffix.lower()
    if ext == ".pdf":
        import io

        from pypdf import PdfReader

        r = PdfReader(io.BytesIO(data))
        n = len(r.pages)
        take = r.pages if pages is None else r.pages[: min(pages, n)]
        return "\n".join((p.extract_text() or "") for p in take), n
    if ext == ".docx":
        import io

        from docx import Document

        d = Document(io.BytesIO(data))
        return "\n".join(p.text for p in d.paragraphs), 0
    return data.decode("utf-8", errors="replace"), 0


class UploadError(ValueError):
    pass


def read_upload(name: str, data: bytes) -> dict[str, Any]:
    """An uploaded circular -> the obligations by article mapped to the library, with the steps it took (timed)."""
    if not data:
        raise UploadError("The file is empty.")
    if pathlib.Path(name).suffix.lower() not in (".pdf", ".docx", ".txt", ".md"):
        raise UploadError("Upload the circular as a .pdf, .docx, .txt or .md file.")
    t0 = time.perf_counter()
    digest = hashlib.sha256(data).hexdigest()
    known = KNOWN.get(digest)
    steps: list[dict[str, Any]] = []

    def step(label: str, detail: str) -> None:
        steps.append({"label": label, "detail": detail, "ms": int((time.perf_counter() - t0) * 1000)})

    try:
        text, pages = _quick_text(name, data, pages=3 if known else None)
    except Exception as exc:  # noqa: BLE001
        raise UploadError("That file could not be read. Upload a text-based .pdf or a .docx.") from exc
    if known:
        mapping = _known_mapping()
        if "credit risk" not in text.lower():
            # the hash matched but the text did not: never trust the precomputed answer blindly
            mapping = _general_mapping(_quick_text(name, data)[0], name)
            known = None
    else:
        mapping = _general_mapping(text, name)
    arts = mapping["articles"]
    n_obl = sum(a["obligations"] for a in arts)
    step(f"Reading {len(arts)} articles", f"{pages} pages" if pages else "text extracted")
    step("Mapping obligations", f"{n_obl} obligations matched to the CBUAE CRM metric library")
    ids = list(dict.fromkeys(m["id"] for a in arts for m in a["metrics"]))
    cov = {s: sum(1 for i in ids if BY_ID[i]["status"] == s) for s in ("available", "partial", "gap")}
    step("Checking data", f"{cov['available']} metrics available, {cov['partial']} partial, {cov['gap']} data gaps")
    return {"upload_id": digest[:16], "sha256": digest, "file": name, "recognised": bool(known),
            "method": ("Recognised as the CBUAE Credit Risk Management Standards: the reviewed P1 mapping was applied."
                       if known else "General mapper: articles and the sentences that oblige, matched to the library by keywords."),
            "document": mapping["document"], "articles": arts, "obligations": n_obl, "metrics": len(ids), "coverage": cov,
            "steps": steps, "ms": int((time.perf_counter() - t0) * 1000), "powered_by": {**PACK, "confidence": "high" if known else "medium",
                                                                                         "rule": "CBUAE CRM Art. 1-13" if known else ""}}


# ------------------------------------------------------------------ the dashboard
KPIS = ["ead", "ecl", "coverage", "stage2_share", "stage3_share", "dpd90_share", "high_critical"]


def dashboard_spec(book: str = "corporate") -> dict[str, Any]:
    """The CBUAE CRM dashboard as a lens spec (the engine renders every figure)."""
    from backend.lenses_v5 import planner
    from backend.lenses_v5.engine import ENGINE

    corp = book == "corporate"

    def t(**k: Any) -> dict[str, Any]:
        return {"id": planner._new_id(), **k}
    tiles = [
        t(type="regulatory", chart="hbar", title="CBUAE CRM breaches by article"),
        t(type="mix_trend", metric="ead", dim="stage", chart="stacked100", title="Stage mix (share of EAD) · Art. 9.2"),
        t(type="trend", metrics=["stage2_share", "stage3_share"], chart="line", title="Stage 2 and Stage 3 share · Art. 7, 12.3"),
        t(type="distribution", column="dpd_days", title="DPD buckets · Art. 7.8, 6.4"),
        t(type="trend", metrics=["dpd30_share", "dpd90_share"], chart="line", title="30+ and 90+ DPD share · Art. 7.8, 6.4"),
        t(type="trend", metrics=["ecl", "coverage"], chart="line", title="ECL and coverage · Art. 9.21-9.24"),
        t(type="breakdown", metric="coverage", dim="stage", chart="bar", title="Coverage by stage against the floors · Art. 9.23"),
    ]
    if corp:
        tiles += [t(type="migration", title="Stage migration · Art. 9.5"),
                  t(type="concentration", title="Concentration: top 20 and HHI · Art. 11.4"),
                  t(type="breakdown", metric="ead", dim="sector", chart="hbar", title="Sector concentration · Art. 11.4"),
                  t(type="breakdown", metric="ead", dim="rating_current", chart="bar", title="EAD by rating (global order)")]
    else:
        tiles += [t(type="roll_rate", title="Roll rates · Art. 9.5"),
                  t(type="breakdown", metric="ead", dim="product", chart="hbar", title="Exposure by product · Art. 11.4")]
    tiles += [t(type="mix_trend", metric="ead", dim="ews_band", chart="stacked100", title="Early Warning bands · Art. 11.6"),
              t(type="top_names", metric="ead", top=20, title="Top 20 exposures · Art. 11.4")]
    spec = {"book": book, "filters": [], "period": ENGINE.as_of(book), "scope_label": "Corporate book" if corp else "Retail book",
            "title": "CBUAE CRM compliance dashboard", "kpis": KPIS[:], "tiles": tiles, "compare": None, "custom_metrics": [],
            "request": "Create the CBUAE CRM dashboard"}
    spec = planner.normalise(spec)
    spec["intel"] = {"pack": PACK, "findings": findings(book), "built_at": int(time.time())}
    return spec


def _f(text: str, article: str, figure: str, rule: str, href: str = "", confidence: str = "high") -> dict[str, Any]:
    return {"text": text, "article": article, "figure": figure, "rule": rule, "confidence": confidence,
            "href": href, "pack": "P1"}


def findings(book: str = "corporate") -> list[dict[str, Any]]:
    """5-7 findings with numbers and articles, from the breach checks and the books (both deterministic)."""
    from backend.lenses_v5 import fmt
    from backend.lenses_v5.engine import ENGINE
    from backend.regulatory import crm_checks

    out: list[dict[str, Any]] = []
    try:
        res = crm_checks.run()
    except Exception:  # noqa: BLE001 - the dashboard still renders without the checks
        res = None
    if res:
        tot = res["totals"]
        out.append(_f(f"{fmt.count(tot['breaches'])} CBUAE CRM breaches across {tot['checks_in_breach']} of {tot['checks']} checks, "
                      f"{fmt.count(tot['high'])} high severity, on {fmt.amount(tot['ead_sar_mn'])} of exposure.",
                      "CBUAE CRM Art. 6-12", fmt.count(tot["breaches"]), "CRM checks", PACK["href"]))
        mine = sorted([c for c in res["checks"] if c["book"] == book and c["breaches"] and c["check_id"] != "CRM-12.3"],
                      key=lambda c: (-(c.get("shortfall_sar_mn") or 0), -c["ead_sar_mn"], -c["breaches"]))
        for c in mine[:3]:
            extra = (f", provision shortfall {fmt.amount(c['shortfall_sar_mn'])}" if c.get("shortfall_sar_mn") else "")
            out.append(_f(f"{c['title']}: {fmt.count(c['breaches'])} {'facilities' if book == 'corporate' else 'accounts'} "
                          f"({fmt.count(c['borrowers'])} {'obligors' if book == 'corporate' else 'customers'}), EAD {fmt.amount(c['ead_sar_mn'])}{extra}.",
                          c["article"], fmt.count(c["breaches"]), c["check_id"], "/borrower-360"))
    try:
        b = book
        p = ENGINE.as_of(b)
        rows, _ = ENGINE.series(b, [], ENGINE.window(b, p), ["ead", "stage3_share", "stage2_share", "coverage"])
        now = rows[-1] if rows else {}
        prev = rows[-2] if len(rows) > 1 else {}
        s3 = now.get("stage3_share")
        if s3 is not None:
            over = s3 > 5
            out.append(_f(f"Stage 3 is {fmt.pct(s3)} of the book ({'above' if over else 'within'} the 5% Board-report trigger).",
                          "CBUAE CRM Art. 12.3", fmt.pct(s3), "CRM-12.3"))
        s2, s2p = now.get("stage2_share"), prev.get("stage2_share")
        if s2 is not None:
            mv = f", {'up' if (s2p or 0) < s2 else 'down'} from {fmt.pct(s2p)} a period before" if s2p is not None else ""
            out.append(_f(f"Stage 2 is {fmt.pct(s2)} of exposure{mv}.", "CBUAE CRM Art. 7", fmt.pct(s2), "CRM-M11"))
    except Exception:  # noqa: BLE001
        pass
    dom = _domain_findings(book)
    gaps = [m for m in LIBRARY if m["status"] == "gap"]
    gap = _f(f"{len(gaps)} of {len(LIBRARY)} CRM metrics still need data that is not loaded"
             + (f" (among them {', '.join(m['name'] for m in gaps[:2])})." if gaps else "."),
             "CBUAE CRM Art. 11", f"{len(gaps)}", "P1 library", "/lenses?tab=library", "medium")
    # totals, the two largest check findings, the domain findings (CRWA floor, deferrals), Stage 3 vs 5%, the gaps
    head = out[:3] if dom else out[:4]
    rest = [f for f in out[len(head):] if f["rule"] in ("CRM-12.3", "CRM-M11")]
    return (head + dom + rest + [gap])[:7] if len(head + dom + rest) < 7 else (head + dom + rest)[:6] + [gap]


def _domain_findings(book: str) -> list[dict[str, Any]]:
    """Findings that need the R9 data domains: Stage 1 + 2 provisions against 1.5% of CRWA (Art. 9.21) and 3+
    deferrals in 24 months still in Stage 1 (Art. 7.7). Empty when the domains are not loaded."""
    from backend.lenses_v5 import fmt

    try:
        from backend.r9_data import read as r9
        from backend.regulatory import crm_checks

        fac = crm_checks.context(book).fac
        ecl12 = float(fac[fac["stage"] < 3]["ecl_sar_mn"].sum())
        crwa = float(r9.crwa(book)["crwa_sar_mn"].sum())
        cls = r9.classification(book, parse=False)
    except Exception:  # noqa: BLE001
        return []
    out: list[dict[str, Any]] = []
    if crwa > 0:
        ratio = ecl12 / crwa * 100
        short = max(0.0, 0.015 * crwa - ecl12)
        out.append(_f(f"Stage 1 + 2 provisions are {fmt.pct(ratio, 2)} of credit RWA ({fmt.amount(ecl12)} on {fmt.amount(crwa)}), "
                      + (f"below the 1.50% floor by {fmt.amount(short)}." if short > 0 else "above the 1.50% floor."),
                      "CBUAE CRM Art. 9.21", fmt.pct(ratio, 2), "CRM-M14", "/what-if", "high"))
    d = cls[(cls["deferrals_24m"] >= 3) & (cls["stage"] == 1)]
    if len(d):
        out.append(_f(f"{fmt.count(len(d))} exposures with 3 or more deferrals in 24 months are still in Stage 1 "
                      f"({fmt.count(d['obligor_id'].nunique())} obligors).", "CBUAE CRM Art. 7.7", fmt.count(len(d)), "CRM-M09",
                      "/borrower-360", "high"))
    return out


def warm() -> None:
    """Run the CRM checks and one dashboard render at start-up, so the key moment is instant the first time too."""
    try:
        from backend.lenses_v5.render import render

        for b in ("corporate", "retail"):
            render(dashboard_spec(b))
    except Exception:  # noqa: BLE001 - warming never blocks the service
        pass
