"""Issue views for every other CBUAE CRM check (K4 "same pattern for every regulatory line"): rule, bank vs
requirement, decomposition (a bridge that sums), concentration, impact, actions with owner and date, source, and
what the data cannot tell us.

Families (by what the check measures):
  stage       CRM-6.4, 7.8, 6.12 (cross-default), 9.11, 9.7, 9.8, 9.30: stage held vs stage required. The bank-vs-
              requirement figure is ECL coverage held vs the coverage the required stage needs: Stage 3 = EAD × the
              facility's own LGD (PD = 1); Stage 2 = the lifetime ECL the book already computes. The bridge is the
              ECL uplift by stage held and product.
  haircut     CRM-10.8: haircut applied vs the Table 4 minimum; the bridge is the collateral value the bank counts
              above the rule, by collateral type and time in Stage 3.
  valuation   CRM-10.11: valuation age vs the maximum.
  write_off   CRM-12.5: months in Stage 3 vs 60; the bridge is the net charge of writing off (EAD − ECL held).
  book        CRM-12.3: Stage 3 share of EAD vs 5%.
  floor       CRM-9.24 (retail floor): ECL vs the floor; bridge by the floor band.
CRM-9.23 has its own deep dive (floor.py).
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from backend.agents_v5.brief import readers as R
from backend.agents_v5.brief.items import fmt
from backend.regulatory import crm_checks as C
from backend.regulatory.issues import common as K

FAMILY = {"CRM-6.4": "stage", "CRM-7.8": "stage", "CRM-6.12": "stage", "CRM-9.11": "stage", "CRM-9.7": "stage",
          "CRM-9.8": "stage", "CRM-9.30": "stage", "CRM-10.8": "haircut", "CRM-10.11": "valuation",
          "CRM-12.5": "write_off", "CRM-12.3": "book", "CRM-9.24": "floor", "CRM-9.23": "floor"}
STAGE_REQUIRED = {"CRM-6.4": 3, "CRM-6.12": 3, "CRM-7.8": 2, "CRM-9.11": 2, "CRM-9.7": 3, "CRM-9.8": 2, "CRM-9.30": 2}
PLAIN_WHAT = {
    "CRM-6.4": "This checks that loans more than 90 days late are treated as defaulted (Stage 3).",
    "CRM-7.8": "This checks that loans more than 30 days late are at least on watch (Stage 2).",
    "CRM-6.12": "This checks that when a company defaults on one material loan, all its loans are treated as defaulted.",
    "CRM-9.11": "This checks that defaulted loans pass through Stage 2 before returning to Stage 1.",
    "CRM-9.7": "This checks that loans leave default only once all arrears are paid.",
    "CRM-9.8": "This checks that loans return to Stage 1 only after the 6-month probation.",
    "CRM-9.30": "This checks that restructured loans of distressed borrowers are not in Stage 1.",
    "CRM-10.8": "This checks that collateral on defaulted loans is discounted at least as much as the regulator's table.",
    "CRM-10.11": "This checks that collateral on defaulted loans has a recent valuation.",
    "CRM-12.5": "This checks that loans in default for more than 5 years are written off.",
    "CRM-12.3": "This checks whether defaulted loans exceed 5% of the book, which the Board must explain.",
    "CRM-9.24": "This checks that provisions on defaulted retail loans meet the regulator's minimum.",
}
NEXT_STAGE_LABEL = {2: "Stage 2 (lifetime ECL)", 3: "Stage 3 (EAD × LGD, PD = 1)"}


def _breaches(check_id: str, book: str) -> tuple[list[dict[str, Any]], R.Read]:
    r = R.read("regulatory", "crm_breach", where="check_id = ? AND book = ?", args=[check_id, book],
               order="shortfall_sar_mn DESC, ead_sar_mn DESC, entity_id")
    return r.rows, r


def _facilities(ids: list[str], period: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for part in K._chunks(sorted(set(ids))):
        ph = ", ".join("?" for _ in part)
        r = R.read("cockpit", "corp_facility_quarter",
                   columns="facility_id, borrower_id, product_type, sector, stage, dpd_days, ead_sar_mn, ecl_sar_mn, "
                           "ecl_lifetime_sar_mn, lgd_pct, quarters_in_stage",
                   where=f"facility_id IN ({ph}) AND reporting_quarter = ?", args=[*part, period])
        out.update({str(x["facility_id"]): x for x in r.rows})
    return out


def _lgd(v: Any) -> float:
    x = float(v or 0.0)
    return x / 100.0 if x > 1.0 else x


def _base(ck: C.Check, book: str, period: str, rows: list[dict[str, Any]], kind: str) -> dict[str, Any]:
    ead = sum(float(r["ead_sar_mn"]) for r in rows if r["entity_type"] != "book")
    return {"id": f"crm:{ck.id}" + ("" if book == "corporate" else f":{book}"), "kind": kind, "check_id": ck.id,
            "book": book, "module": "Regulatory intelligence", "title": ck.title, "period": period,
            "severity": ck.severity,
            "rule": {"article": ck.article, "text": ck.rule, "href": f"{K.POLICY_HREF}&clause={ck.article}", "detail": ""},
            "source": {"label": "Source: regulatory.crm_breach", "domain": "regulatory", "relation": "crm_breach",
                       "href": f"/data-builder?domain=regulatory&relation=crm_breach&check_id={ck.id}"},
            "_ead": ead}


def _empty(ck: C.Check, book: str, period: str) -> dict[str, Any]:
    v = _base(ck, book, period, [], "compliant")
    v.pop("_ead")
    v.update({"headline": f"{ck.id} ({ck.article.replace(C.PREFIX + ' ', '')}): no {book} exposure breaches this "
                          f"rule at {period}.",
              "plain_words": [PLAIN_WHAT.get(ck.id, ck.rule), f"Nothing breaches it at {period}.",
                              "Nothing to do; the check runs again with the next book."],
              "comparison": None, "tables": [], "bridge": None, "concentration": None, "impact": [], "actions": [],
              "exposures": None, "cannot_tell": [], "trace": []})
    return v


def view(check_id: str, book: str = "corporate", today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    ck = C.BY_ID[check_id]
    rows, rd = _breaches(check_id, book)
    period = str(rows[0]["period"]) if rows else C.context(book).period
    if not rows:
        return _empty(ck, book, period)
    fam = FAMILY.get(check_id, "stage")
    fn = {"stage": _stage, "haircut": _haircut, "valuation": _valuation, "write_off": _write_off, "book": _book_share,
          "floor": _retail_floor}[fam]
    v = fn(ck, book, period, rows, today)
    v.pop("_ead", None)
    v.setdefault("trace", [])
    v["trace"].insert(0, rd.stamp({"check_id": check_id, "book": book}, period))
    return v


def _exposures(rows: list[dict[str, Any]], period: str, cols: list[tuple[str, str, str]], extra) -> dict[str, Any]:
    names = K.borrower_names([r["owner_id"] for r in rows[:25]], period) if rows and rows[0]["book"] == "corporate" else {}
    out = []
    for r in rows[:25]:
        b = str(r["owner_id"])
        out.append({"facility_id": r["entity_id"], "borrower_id": b, "name": names.get(b, b),
                    "href": f"/borrower-360?id={b}" if b.startswith("CB") else "", "ead": K.r2(r["ead_sar_mn"]),
                    "ecl": K.r2(r["ecl_sar_mn"]), "measured": r["measured"], "required": r["required"],
                    "detail": r["detail"], **extra(r)})
    return K.table("exposures", f"The {min(25, len(rows))} largest of {len(rows):,}",
                   [("name", "Borrower", "text"), ("facility_id", "Facility", "text"), *cols], out)


# ------------------------------------------------------------------ stage held vs stage required

def _stage(ck, book, period, rows, today) -> dict[str, Any]:
    v = _base(ck, book, period, rows, "stage")
    need = STAGE_REQUIRED.get(ck.id, 3)
    fac = _facilities([r["entity_id"] for r in rows], period) if book == "corporate" else {}
    s_crm = K.src("regulatory", "crm_breach", {"check_id": ck.id, "book": book}, "ead_sar_mn", period)
    s_fac = K.src("cockpit", "corp_facility_quarter", {"reporting_quarter": period}, "ecl_lifetime_sar_mn, lgd_pct",
                  period)
    enriched = []
    for r in rows:
        f = fac.get(str(r["entity_id"]), {})
        ead, ecl = float(r["ead_sar_mn"]), float(r["ecl_sar_mn"])
        req = ead * _lgd(f.get("lgd_pct")) if need == 3 else float(f.get("ecl_lifetime_sar_mn") or ecl)
        held = f.get("stage")
        enriched.append({**r, "borrower_id": r["owner_id"],
                         "held": str(int(held)) if held is not None else str(r["measured"])[:1],
                         "product": str(f.get("product_type") or "Not recorded"), "required_ecl": max(req, ecl),
                         "uplift": max(req - ecl, 0.0)})
    ead = sum(float(x["ead_sar_mn"]) for x in enriched)
    ecl = sum(float(x["ecl_sar_mn"]) for x in enriched)
    req = sum(x["required_ecl"] for x in enriched)
    up = sum(x["uplift"] for x in enriched)
    bank_pct, req_pct = K.pct(ecl, ead) or 0.0, K.pct(req, ead) or 0.0
    borrowers = len({x["borrower_id"] for x in enriched})
    sentence = (f"Bank holds {K.words(len(rows), 'facility', 'facilities')} ({K.words(borrowers, 'borrower')}) in a lower stage than the rule needs, "
                f"with ECL coverage of {bank_pct:.1f}% against {req_pct:.1f}% in {NEXT_STAGE_LABEL[need]}: "
                f"{fmt(up, 'SAR mn')} short.")

    def groups(key: str) -> list[dict[str, Any]]:
        acc: dict[str, list[float]] = {}
        for x in enriched:
            a = acc.setdefault(x[key], [0, 0.0, 0.0, 0.0])
            a[0] += 1
            a[1] += float(x["ead_sar_mn"])
            a[2] += float(x["ecl_sar_mn"])
            a[3] += x["uplift"]
        return [{"name": (f"Held in Stage {k}" if key == "held" else k), "n": int(a[0]), "ead": K.r2(a[1]),
                 "bank_pct": K.pct(a[2], a[1]), "req_pct": K.pct(a[2] + a[3], a[1]), "uplift": K.r2(a[3])}
                for k, a in sorted(acc.items(), key=lambda kv: (-kv[1][3], kv[0]))]

    cols = [("name", "", "text"), ("n", "Facilities", "n"), ("ead", "EAD", "SAR mn"),
            ("bank_pct", "Coverage held", "%"), ("req_pct", f"In Stage {need}", "%"),
            ("uplift", "ECL short", "SAR mn")]
    by_stage, by_prod = groups("held"), groups("product")
    tot = {"name": "All", "n": len(enriched), "ead": K.r2(ead), "bank_pct": bank_pct, "req_pct": req_pct,
           "uplift": K.r2(up)}
    tables = [K.table("by_stage", "Bank vs requirement by stage held", cols, by_stage, tot),
              K.table("by_product", "Bank vs requirement by product", cols, by_prod, tot)]
    steps = [{"key": f"held{g['name'][-1]}", "label": f"{g['name']} → Stage {need}", "value": g["uplift"],
              "facilities": g["n"], "ead": g["ead"],
              "explain": f"Moving these to Stage {need} raises coverage from {g['bank_pct'] or 0:.1f}% to "
                         f"{g['req_pct'] or 0:.1f}%.",
              "rows": [x["entity_id"] for x in sorted((y for y in enriched if f"Held in Stage {y['held']}" == g["name"]),
                                                      key=lambda y: -y["uplift"])[:10]],
              "link": None, "source": {**s_fac, "method": "EAD × LGD (Stage 3) or lifetime ECL (Stage 2) − ECL held"}}
             for g in by_stage]
    bridge = K.bridge(f"Where the {fmt(up, 'SAR mn')} of ECL comes from", up, steps,
                      "Per facility: the ECL it needs in the required stage (Stage 3: EAD × its own LGD, PD = 1; "
                      "Stage 2: the lifetime ECL the book computes) less the ECL held; summed by the stage held.")
    conc = K.concentration(enriched, "uplift", period, label="ECL short") if book == "corporate" else None
    actions = [K.action(1, f"Move {K.words(len(rows), 'facility', 'facilities')} to Stage {need} in the staging system and re-run their ECL",
                        "classification", today, 14, ck.rule, K.fig("Facilities", len(rows), "", s_crm)),
               K.action(2, f"Book the ECL uplift of {fmt(up, 'SAR mn')} in the quarter's ECL run", "provisioning", today,
                        21, "Coverage follows the stage.", K.fig("ECL uplift", K.r2(up), "SAR mn", s_fac))]
    if ck.id == "CRM-6.12":
        actions.append(K.action(3, "Add the cross-default rule to the staging engine: a default on a facility above 5% of "
                                   "the borrower's funded exposure moves all its facilities to Stage 3", "data", today, 60,
                                "Art. 6.12 is a borrower-level rule; the book stages facility by facility."))
        actions.append(K.action(4, f"Review the {borrowers:,} borrowers with their relationship managers: restructure, "
                                   "call in or accept with a documented rebuttal", "credit", today, 30,
                                "Default on one material facility usually precedes the rest."))
    else:
        actions.append(K.action(3, "Fix the staging rule that let these through and document any rebuttal",
                                "classification", today, 45, ck.rule))
    v.pop("_ead")
    v.update({
        "headline": f"{ck.id} ({ck.article.replace(C.PREFIX + ' ', '')}): {K.words(len(rows), book + ' facility', book + ' facilities')} with "
                    f"{fmt(ead, 'SAR mn')} EAD {'is' if len(rows) == 1 else 'are'} held below Stage {need} at {period}; moving {'it' if len(rows) == 1 else 'them'} needs "
                    f"{fmt(up, 'SAR mn')} more ECL.",
        "plain_words": [PLAIN_WHAT.get(ck.id, ck.rule),
                        f"{K.words(len(rows), 'loan')} of {K.words(borrowers, 'borrower')} held too low: provisions "
                        f"cover {K.pct_words(bank_pct)} against {K.pct_words(req_pct)} needed.",
                        f"Restaging them costs about {fmt(up, 'SAR mn')} of provisions.",
                        "Restage them now and fix the staging rule so it cannot recur."],
        "comparison": {"sentence": sentence,
                       "bank": K.fig("ECL coverage held (ECL ÷ EAD)", bank_pct, "%", {**s_crm, "column": "ecl ÷ ead"}),
                       "required": K.fig(f"Coverage in Stage {need}", req_pct, "%", s_fac), "model": None,
                       "figures": [K.fig("Facilities", len(rows), "", s_crm), K.fig("Borrowers", borrowers, "", s_crm),
                                   K.fig("EAD", K.r2(ead), "SAR mn", s_crm), K.fig("ECL held", K.r2(ecl), "SAR mn", s_crm),
                                   K.fig("ECL short", K.r2(up), "SAR mn", s_fac)]},
        "tables": tables, "bridge": bridge, "concentration": conc,
        "impact": K.impact_rows(up, what="uplift if restaged"), "actions": actions,
        "exposures": _exposures(sorted(enriched, key=lambda x: (-x["uplift"], x["entity_id"])), period,
                                [("measured", "Stage held", "text"), ("ead", "EAD", "SAR mn"), ("ecl", "ECL held", "SAR mn"),
                                 ("uplift", "ECL short", "SAR mn"), ("detail", "Why", "text")],
                                lambda r: {"uplift": K.r2(r["uplift"])}),
        "cannot_tell": ["Documented rebuttals of the presumption (Art. 7.8) are not in the book: a facility with a "
                        "valid rebuttal is compliant.",
                        "Stage 3 coverage uses the facility's own LGD with PD = 1, before the Art. 9.23 floor; the floor "
                        "can add more.",
                        "The CET1 effect is pre-tax and pre-zakat, on credit RWA only."],
        "trace": [s_crm, s_fac, *((conc or {}).get("source") or [])],
    })
    return v


# ------------------------------------------------------------------ collateral haircut below Table 4

def _months(detail: str) -> int:
    m = re.search(r"(\d+) months", detail or "")
    return int(m.group(1)) if m else 0


def _haircut(ck, book, period, rows, today) -> dict[str, Any]:
    v = _base(ck, book, period, rows, "haircut")
    ctx = C.context(book, period)
    col = ctx.collateral.set_index("collateral_id") if ctx.collateral is not None else None
    enriched = []
    for r in rows:
        cid = str(r["detail"]).split(":")[0].split()[-1]
        ctype = str(r["detail"]).split(" CC")[0] if " CC" in str(r["detail"]) else str(r["detail"]).split(":")[0]
        mv = float(col.loc[cid]["market_value_sar_mn"]) if col is not None and cid in col.index else 0.0
        own, need = float(r["measured"]), float(r["required"])
        enriched.append({**r, "borrower_id": r["owner_id"], "collateral_id": cid, "ctype": ctype, "mv": mv,
                         "own": own, "need": need, "months": _months(str(r["detail"])),
                         "over": mv * (need - own) / 100.0})
    over = sum(x["over"] for x in enriched)
    mv = sum(x["mv"] for x in enriched)
    own_w = (sum(x["own"] * x["mv"] for x in enriched) / mv) if mv else 0.0
    need_w = (sum(x["need"] * x["mv"] for x in enriched) / mv) if mv else 0.0
    s_crm = K.src("regulatory", "crm_breach", {"check_id": ck.id, "book": book}, "measured, required", period)
    s_col = K.src("cockpit", "corp_collateral_quarter", {"reporting_quarter": period}, "market_value_sar_mn", period)
    band = lambda m: "Up to 2 years" if m <= 24 else ("2–4 years" if m <= 48 else ("4–5 years" if m <= 60 else "Over 5 years"))  # noqa: E731

    def groups(fn) -> list[dict[str, Any]]:
        acc: dict[str, list[float]] = {}
        for x in enriched:
            a = acc.setdefault(fn(x), [0, 0.0, 0.0, 0.0, 0.0])
            a[0] += 1
            a[1] += x["mv"]
            a[2] += x["own"] * x["mv"]
            a[3] += x["need"] * x["mv"]
            a[4] += x["over"]
        return [{"name": k, "n": int(a[0]), "mv": K.r2(a[1]), "own": round(a[2] / a[1], 1) if a[1] else None,
                 "need": round(a[3] / a[1], 1) if a[1] else None, "over": K.r2(a[4])}
                for k, a in sorted(acc.items(), key=lambda kv: (-kv[1][4], kv[0]))]

    cols = [("name", "", "text"), ("n", "Items", "n"), ("mv", "Market value", "SAR mn"), ("own", "Applied", "%"),
            ("need", "Table 4", "%"), ("over", "Above the rule", "SAR mn")]
    tot = {"name": "All", "n": len(enriched), "mv": K.r2(mv), "own": round(own_w, 1), "need": round(need_w, 1),
           "over": K.r2(over)}
    by_type, by_band = groups(lambda x: x["ctype"]), groups(lambda x: band(x["months"]))
    try:
        from backend.regulatory.issues import floor
        fv = floor.view(today, period)
        in_floor = next((s["value"] for s in fv["bridge"]["steps"] if s["key"] == "haircut"), 0.0)
    except Exception:  # noqa: BLE001
        in_floor = None
    steps = [{"key": f"t{i}", "label": g["name"], "value": g["over"], "facilities": g["n"], "ead": g["mv"],
              "explain": f"Haircut {g['own'] or 0:.0f}% applied against a {g['need'] or 0:.0f}% minimum.",
              "rows": [x["entity_id"] for x in enriched if x["ctype"] == g["name"]][:10], "link": None,
              "source": {**s_col, "method": "market value × (minimum − applied haircut)"}} for i, g in enumerate(by_type)]
    bridge = K.bridge(f"Where the {fmt(over, 'SAR mn')} of collateral value above the rule sits", over, steps,
                      "Per collateral item: market value × (Table 4 minimum − the haircut applied), by collateral type.")
    impact = [K.fig("Collateral value counted above Table 4", K.r2(over), "SAR mn", s_col)]
    if in_floor is not None:
        impact.append(K.fig("Of which shows up as Stage 3 floor shortfall (in CRM-9.23)", K.r2(in_floor), "SAR mn",
                            K.src("regulatory", "crm_breach", {"check_id": "CRM-9.23"}, "shortfall_sar_mn", period,
                                  "haircut driver of the CRM-9.23 bridge")))
    v.pop("_ead")
    v.update({
        "headline": f"{ck.id} ({ck.article.replace(C.PREFIX + ' ', '')}): {len(rows):,} collateral items on Stage 3 "
                    f"facilities carry haircuts below Table 4 at {period}; the bank counts {fmt(over, 'SAR mn')} more "
                    "collateral than the rule allows.",
        "plain_words": [PLAIN_WHAT[ck.id],
                        f"On {len(rows):,} items the bank discounts {own_w:.0f}% where the rule needs {need_w:.0f}%.",
                        f"That counts {fmt(over, 'SAR mn')} of collateral the rule does not allow"
                        + (f"; {fmt(in_floor, 'SAR mn')} of the provision gap comes from it." if in_floor else "."),
                        "Re-haircut these items to Table 4 and revalue them."],
        "comparison": {"sentence": f"Bank applies an average haircut of {own_w:.1f}% against a Table 4 minimum of "
                                   f"{need_w:.1f}% on {len(rows):,} Stage 3 collateral items: {fmt(over, 'SAR mn')} "
                                   "counted above the rule.",
                       "bank": K.fig("Haircut applied (value-weighted)", round(own_w, 1), "%", s_crm),
                       "required": K.fig("Table 4 minimum (value-weighted)", round(need_w, 1), "%", s_crm), "model": None,
                       "figures": [K.fig("Items", len(rows), "", s_crm), K.fig("Market value", K.r2(mv), "SAR mn", s_col),
                                   K.fig("Counted above the rule", K.r2(over), "SAR mn", s_col)]},
        "tables": [K.table("by_type", "Applied vs minimum by collateral type", cols, by_type, tot),
                   K.table("by_band", "Applied vs minimum by time in Stage 3", cols, by_band, tot)],
        "bridge": bridge, "concentration": K.concentration(enriched, "over", period, label="Value above the rule"),
        "impact": impact,
        "actions": [K.action(1, f"Re-haircut {len(rows):,} items to Table 4 in the collateral system", "collateral",
                             today, 30, ck.rule, K.fig("Items", len(rows), "", s_crm)),
                    K.action(2, "Commission new valuations on the real estate among them", "collateral", today, 60,
                             "A new valuation is the only way to support a value above the table."),
                    K.action(3, "Re-run the Stage 3 floor once the haircuts are fixed", "provisioning", today, 35,
                             "The floor counts collateral after the Table 4 haircut.",
                             link={"label": "CRM-9.23 issue", "href": K.issue_href("crm:CRM-9.23")})],
        "exposures": _exposures(sorted(enriched, key=lambda x: (-x["over"], x["entity_id"])), period,
                                [("measured", "Haircut applied %", "text"), ("required", "Minimum %", "text"),
                                 ("over", "Value above the rule", "SAR mn"), ("detail", "Item", "text")],
                                lambda r: {"over": K.r2(r["over"])}),
        "cannot_tell": ["Valuations the bank holds outside the book (recent appraisals, sale offers) are not here; "
                        "Art. 10.8 allows them to be considered case by case.",
                        "Receivables and plant and equipment are not in Table 4 and are not tested."],
        "trace": [s_crm, s_col],
    })
    return v


# ------------------------------------------------------------------ valuation out of date, write-off, book share, retail floor

def _simple(ck, book, period, rows, today, *, kind, sentence, bank, req, plain, actions, cannot, bridge=None,
            tables=None, impact=None, extra_cols=None) -> dict[str, Any]:
    v = _base(ck, book, period, rows, kind)
    s_crm = K.src("regulatory", "crm_breach", {"check_id": ck.id, "book": book}, "measured, required", period)
    v.pop("_ead")
    ead = sum(float(r["ead_sar_mn"]) for r in rows)
    sf_total = sum(float(r["shortfall_sar_mn"] or 0.0) for r in rows)
    v.update({
        "headline": f"{ck.id} ({ck.article.replace(C.PREFIX + ' ', '')}): "
                    f"{K.words(len(rows), book + (' account' if book == 'retail' else ' facility'), book + (' accounts' if book == 'retail' else ' facilities'))} "
                    f"with {fmt(ead, 'SAR mn')} EAD at {period}"
                    + (f", {fmt(sf_total, 'SAR mn')} of provision below the floor." if sf_total > 0 else "."),
        "plain_words": plain,
        "comparison": {"sentence": sentence, "bank": bank, "required": req, "model": None,
                       "figures": [K.fig("Breaches", len(rows), "", s_crm), K.fig("EAD", K.r2(ead), "SAR mn", s_crm)]},
        "tables": tables or [], "bridge": bridge,
        "concentration": K.concentration([{**r, "borrower_id": r["owner_id"]} for r in rows], "ead_sar_mn", period,
                                         label="EAD") if book == "corporate" else None,
        "impact": impact or [], "actions": actions,
        "exposures": _exposures(rows, period, extra_cols or [("measured", "Measured", "text"),
                                                             ("required", "Required", "text"), ("ead", "EAD", "SAR mn"),
                                                             ("detail", "Detail", "text")], lambda r: {}),
        "cannot_tell": cannot, "trace": [s_crm],
    })
    return v


def _valuation(ck, book, period, rows, today):
    ages = [float(r["measured"]) for r in rows]
    s = K.src("regulatory", "crm_breach", {"check_id": ck.id, "book": book}, "measured", period)
    mean_age = sum(ages) / len(ages) if ages else 0.0
    maxm = max(float(r["required"]) for r in rows)
    return _simple(ck, book, period, rows, today, kind="valuation",
                   sentence=f"Collateral on {len(rows):,} Stage 3 {'accounts' if book == 'retail' else 'facilities'} was "
                            f"valued {mean_age:.1f} months ago on average against a maximum of {maxm:.0f} months.",
                   bank=K.fig("Average valuation age", round(mean_age, 1), "months", s),
                   req=K.fig("Maximum allowed", maxm, "months", s),
                   plain=[PLAIN_WHAT[ck.id], f"{len(rows):,} loans carry valuations older than allowed "
                                             f"({mean_age:.0f} months on average).",
                          "Old valuations may overstate what the bank can recover.", "Order new valuations now."],
                   actions=[K.action(1, f"Order new valuations on {len(rows):,} items", "collateral", today, 45, ck.rule)],
                   cannot=["The book holds valuation age, not the valuation report; a valuation outside the book "
                           "may already exist."])


def _write_off(ck, book, period, rows, today):
    ead = sum(float(r["ead_sar_mn"]) for r in rows)
    ecl = sum(float(r["ecl_sar_mn"]) for r in rows)
    s = K.src("regulatory", "crm_breach", {"check_id": ck.id, "book": book}, "ead_sar_mn, ecl_sar_mn", period)
    months = [float(r["measured"]) for r in rows]
    steps = [{"key": "held", "label": "ECL already held (absorbs the write-off)", "value": ecl, "facilities": len(rows),
              "ead": K.r2(ead), "explain": "Provision already on the balance sheet.", "rows": [], "link": None,
              "source": s},
             {"key": "net", "label": "New charge on write-off (EAD − ECL held)", "value": ead - ecl,
              "facilities": len(rows), "ead": K.r2(ead), "explain": "Hits P&L when written off.",
              "rows": [r["entity_id"] for r in rows[:10]], "link": None, "source": s}]
    return _simple(ck, book, period, rows, today, kind="write_off",
                   sentence=f"Bank holds {K.words(len(rows), 'facility', 'facilities')} in Stage 3 for {sum(months) / len(months) / 12:.1f} "
                            f"years on average against a 5-year maximum; ECL covers {K.pct(ecl, ead) or 0:.1f}% of "
                            f"{fmt(ead, 'SAR mn')}.",
                   bank=K.fig("Average time in Stage 3", round(sum(months) / len(months), 0), "months", s),
                   req=K.fig("Maximum before write-off", 60, "months", s),
                   plain=[PLAIN_WHAT[ck.id], f"{len(rows):,} loans have been in default over 5 years and are still "
                                             "on the books.",
                          f"Writing them off costs {fmt(ead - ecl, 'SAR mn')} more than is provided.",
                          "Write them off or get Board sign-off for an exception."],
                   bridge=K.bridge(f"What writing off {fmt(ead, 'SAR mn')} costs", ead, steps,
                                   "EAD split into the ECL already held and the new charge."),
                   impact=K.impact_rows(ead - ecl, what="net charge on write-off"),
                   actions=[K.action(1, f"Put {K.words(len(rows), 'facility', 'facilities')} to the Board: write off or sign an exception",
                                     "board", today, 30, ck.rule),
                            K.action(2, "Keep recovery action going after write-off and record recoveries", "remedial",
                                     today, 60, "A write-off is an accounting step, not a waiver.")],
                   cannot=["Board exceptions already signed are not in the book."])


def _book_share(ck, book, period, rows, today):
    r = rows[0]
    s = K.src("regulatory", "crm_breach", {"check_id": ck.id, "book": book}, "measured", period)
    v = _simple(ck, book, period, rows, today, kind="book",
                   sentence=f"Stage 3 is {r['measured']}% of the {book} book's EAD against the {r['required']}% level "
                            "that needs a Board explanation and reduction plan.",
                   bank=K.fig("Stage 3 share of EAD", float(r["measured"]), "%", s),
                   req=K.fig("Level that needs a Board plan", float(r["required"]), "%", s),
                   plain=[PLAIN_WHAT[ck.id], f"Defaulted loans are {r['measured']}% of the {book} book.",
                          "The Board must explain why to the regulator and approve a plan to reduce it.",
                          "Prepare the Board paper with the reduction plan."],
                   actions=[K.action(1, "Prepare the Board paper: causes and a reduction plan, reported every six months",
                                     "board", today, 30, ck.rule)],
                   cannot=["Whether a Board plan is already in place is not in the book."])
    v["headline"] = (f"{ck.id} ({ck.article.replace(C.PREFIX + ' ', '')}): Stage 3 is {r['measured']}% of the {book} "
                     f"book's EAD ({fmt(float(r['ead_sar_mn']), 'SAR mn')}) at {period}, above {r['required']}%.")
    v["comparison"]["figures"] = [K.fig("Stage 3 EAD", K.r2(r["ead_sar_mn"]), "SAR mn", s),
                                  K.fig("Stage 3 ECL", K.r2(r["ecl_sar_mn"]), "SAR mn", s)]
    v["concentration"] = None
    v["exposures"] = None
    return v


def _retail_floor(ck, book, period, rows, today):
    ead = sum(float(r["ead_sar_mn"]) for r in rows)
    ecl = sum(float(r["ecl_sar_mn"]) for r in rows)
    sf = sum(float(r["shortfall_sar_mn"]) for r in rows)
    s = K.src("regulatory", "crm_breach", {"check_id": ck.id, "book": book}, "shortfall_sar_mn", period)
    acc: dict[str, list[float]] = {}
    for r in rows:
        m = re.search(r"floor: (\d+)%", str(r["detail"]))
        k = f"{m.group(1)}% floor" if m else "Floor"
        a = acc.setdefault(k, [0, 0.0])
        a[0] += 1
        a[1] += float(r["shortfall_sar_mn"])
    steps = [{"key": k, "label": k, "value": a[1], "facilities": int(a[0]), "ead": None, "explain": "By days past due "
              "(Table 3).", "rows": [], "link": None, "source": s} for k, a in sorted(acc.items())]
    return _simple(ck, book, period, rows, today, kind="floor",
                   sentence=f"Bank holds Stage 3 coverage of {K.pct(ecl, ead) or 0:.1f}% (ECL ÷ EAD) against a "
                            f"regulatory minimum of {K.pct(ecl + sf, ead) or 0:.1f}% (floor ÷ EAD) on {len(rows):,} "
                            f"accounts: {fmt(sf, 'SAR mn')} short.",
                   bank=K.fig("Coverage held", K.pct(ecl, ead), "%", s), req=K.fig("Floor", K.pct(ecl + sf, ead), "%", s),
                   plain=[PLAIN_WHAT[ck.id], f"On {len(rows):,} accounts provisions are {fmt(sf, 'SAR mn')} below "
                                             "the minimum.", "The gap grows with days past due.",
                          "Top up the provisions in the next run."],
                   bridge=K.bridge(f"Where the {fmt(sf, 'SAR mn')} comes from", sf, steps,
                                   "Shortfall by the floor band the account falls in (Art. 9.24, Table 3)."),
                   impact=K.impact_rows(sf),
                   extra_cols=[("measured", "ECL held, SAR mn", "text"), ("required", "Floor, SAR mn", "text"),
                               ("ead", "EAD", "SAR mn"), ("detail", "Detail", "text")],
                   actions=[K.action(1, f"Top up retail Stage 3 provisions by {fmt(sf, 'SAR mn')}", "provisioning",
                                     today, 21, ck.rule)],
                   cannot=["Collateral recoveries in progress are not in the book."])
