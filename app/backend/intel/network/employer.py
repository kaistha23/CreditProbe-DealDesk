"""Employer exposure (R14 backlog #10): the bank's exposure to a project employer held through every contractor it pays.

Two sources, one answer:

  book       the employer is a corporate book borrower (a developer, a utility, a telecom operator). The contractors
             and suppliers it pays are the SUPPLIES edges into it (rel-saudi-v1), observed through payments routed via
             the bank, with the share of each contractor's revenue it pays. Exposure = the contractor's EAD (funded,
             and non-funded: guarantees and trade lines); attributable = EAD x the share of revenue the employer pays.
  deal desk  the employer is named on Deal Desk projects (dd_project.employer / employer_entity_id): projects, payment
             certificates (certified but unpaid, retention, delay, pending certificates), the LGs issued for each
             project (dd_facility_limit by project_id) and the employer's bureau report.

Concentration is tested against risk appetite: the employer's own plus attributable exposure against the single
obligor appetite (CP-1.1, it is one credit risk), and each contractor's dependence against the Deal Desk products
guide (top employers' share of a contractor's backlog, project.employer_concentration_max).
"""
from __future__ import annotations

import re
from typing import Any

from backend.b360.store import clean, rows
from backend.intel.network import common, links, writer


class EmployerError(ValueError):
    pass


def _contractor_exposure(period: str, ids: list[str]) -> dict[str, dict[str, Any]]:
    if not ids:
        return {}
    got = rows("""SELECT borrower_id, SUM(ead_sar_mn) AS ead,
                         SUM(CASE WHEN facility_class = 'funded' THEN ead_sar_mn ELSE 0 END) AS funded,
                         SUM(CASE WHEN facility_class = 'non_funded' THEN ead_sar_mn ELSE 0 END) AS non_funded,
                         SUM(CASE WHEN product_type = 'project_finance' THEN ead_sar_mn ELSE 0 END) AS project_finance,
                         SUM(ecl_sar_mn) AS ecl, MAX(stage) AS stage
                  FROM corp_facility WHERE reporting_quarter = ? AND list_contains(?, borrower_id) GROUP BY 1""",
               [period, sorted(set(ids))])
    return {r["borrower_id"]: r for r in got}


def _dd(relation: str, **filters: Any) -> list[dict[str, Any]]:
    try:
        from backend.dealdesk.data.store import dd_read
        return dd_read(relation, **filters)
    except Exception:  # noqa: BLE001 - Deal Desk relations are optional for a book employer
        return []


def _trace(relation: str, row: dict[str, Any]) -> dict[str, Any]:
    try:
        from backend.dealdesk.data.store import trace
        return trace(relation, row)
    except Exception:  # noqa: BLE001
        return common.src(relation)


def deal_desk_projects(name: str | None, entity_id: str | None) -> list[dict[str, Any]]:
    out = []
    for p in _dd("dd_project"):
        if (entity_id and p.get("employer_entity_id") == entity_id) or \
                (name and p.get("employer") and name.lower() in str(p["employer"]).lower()):
            out.append(p)
    return out


def _resolve(period: str, employer: str) -> dict[str, Any]:
    t = (employer or "").strip()
    if not t:
        raise EmployerError("Name the employer (a book borrower id or name, or a Deal Desk employer).")
    ents = [e for e in _dd("b360_entity") if e.get("role") == "employer"]
    ent = next((e for e in ents if e["entity_id"].upper() == t.upper() or t.lower() in str(e["entity_name"]).lower()), None)
    book = None
    if ent and ent.get("borrower_id"):
        hit = common.find_borrower(period, ent["borrower_id"])
        book = hit[0] if hit else None
    if not book and not ent:
        hit = common.find_borrower(period, t)
        book = hit[0] if hit else None
    projects = deal_desk_projects(ent["entity_name"] if ent else (book or {}).get("borrower_name") or t,
                                  ent["entity_id"] if ent else None)
    if not book and not ent and not projects:
        raise EmployerError(f"No book borrower or Deal Desk employer matches {employer!r}.")
    return {"book": book, "entity": ent, "projects": projects}


def exposure(employer: str, period: str | None = None, publish: bool = True) -> dict[str, Any]:
    period = common.resolve_quarter(period)
    who = _resolve(period, employer)
    book, ent, projects = who["book"], who["entity"], who["projects"]
    app = common.appetite()
    name = (ent or {}).get("entity_name") or (book or {}).get("borrower_name")
    contractors: list[dict[str, Any]] = []
    own = 0.0
    own_attrs: dict[str, Any] = {}
    if book:
        bid = book["borrower_id"]
        own_attrs = common.borrowers(period, [bid]).get(bid, {})
        own = float(own_attrs.get("ead") or 0.0)
        edges = links.supplies_into(period, [bid])
        ex = _contractor_exposure(period, [e["supplier_id"] for e in edges])
        attrs = common.borrowers(period, [e["supplier_id"] for e in edges])
        for e in edges:
            s = e["supplier_id"]
            x, a = ex.get(s, {}), attrs.get(s, {})
            ead = float(x.get("ead") or 0.0)
            share = float(e["revenue_share_pct"] or 0.0)
            contractors.append({"borrower_id": s, "name": a.get("borrower_name"), "sector": e["supplier_sector"],
                                "is_contractor": e["supplier_sector"] == links.CONTRACTOR_SECTOR,
                                "ead": ead, "funded": float(x.get("funded") or 0.0), "non_funded": float(x.get("non_funded") or 0.0),
                                "project_finance": float(x.get("project_finance") or 0.0), "ecl": float(x.get("ecl") or 0.0),
                                "stage": x.get("stage"), "revenue_share_pct": share,
                                "annual_paid_sar_mn": float(e["annual_value_sar_mn"] or 0.0),
                                "attributable": ead * share / 100, "rating": a.get("rating_current"),
                                "ews_band": a.get("ews_band"),
                                "dependence": "high" if share >= 30 else "material" if share >= 10 else "low",
                                "source": common.src("rel_edge", period, ["revenue_share_pct", "annual_value_sar_mn"],
                                                     edge_id=e["edge_id"]),
                                "href": f"/borrower-360?domain=corporate&customer_id={s}"})
        contractors.sort(key=lambda c: (-c["attributable"], -c["ead"], c["borrower_id"]))
    # Deal Desk: projects, payment certificates and LGs
    dd_rows = []
    lg_out = due = ret = dd_funded = dd_proposed = 0.0
    for p in projects:
        lgs = [l for l in _dd("dd_facility_limit", proposal_id=p["proposal_id"]) if l.get("project_id") == p["project_id"]]
        lg_children = [l for l in lgs if l.get("product_code")] or lgs
        lg_o = sum(float(l.get("outstanding_mn") or 0.0) for l in lg_children if not l.get("funded_flag"))
        funded_o = sum(float(l.get("outstanding_mn") or 0.0) for l in lg_children if l.get("funded_flag"))
        lg_out += lg_o
        dd_funded += funded_o
        dd_proposed += sum(float(l.get("proposed_mn") or 0.0) for l in lg_children)
        due += float(p.get("due_mn") or 0.0)
        ret += float(p.get("retention_mn") or 0.0)
        deal = (_dd("dd_deal", proposal_id=p["proposal_id"]) or [{}])[0]
        dd_rows.append({"project_id": p["project_id"], "project": p["project_name"], "proposal_id": p["proposal_id"],
                        "contractor_id": p["obligor_id"], "contractor": deal.get("obligor_name"), "status": p["status"],
                        "contract_value": float(p.get("contract_value_revised_mn") or p.get("contract_value_original_mn") or 0.0),
                        "backlog": float(p.get("backlog_mn") or 0.0), "due": float(p.get("due_mn") or 0.0),
                        "retention": float(p.get("retention_mn") or 0.0),
                        "payment_delay_days": p.get("payment_delay_days"), "pending_certs": p.get("pending_certs_n"),
                        "last_cert_no": p.get("last_cert_no"), "lg_outstanding": lg_o, "funded_outstanding": funded_o,
                        "lg_products": sorted({str(l.get("product_code")) for l in lg_children if l.get("product_code")}),
                        "source": _trace("dd_project", p)})
    # contractor dependence on this employer in Deal Desk (share of the contractor's backlog)
    dd_dep = []
    for cid in sorted({r["contractor_id"] for r in dd_rows}):
        allp = [p for p in _dd("dd_project") if p.get("obligor_id") == cid]
        tot = sum(float(p.get("backlog_mn") or 0.0) for p in allp)
        mine = sum(r["backlog"] for r in dd_rows if r["contractor_id"] == cid)
        dd_dep.append({"contractor_id": cid, "backlog_share": mine / tot if tot else None, "backlog": mine,
                       "guide": app["employer_backlog"]["limit"],
                       "flag": bool(tot and mine / tot > app["employer_backlog"]["limit"])})
    bureau = None
    if ent:
        br = [b for b in _dd("bureau_entity_report") if b.get("entity_id") == ent["entity_id"]]
        if br:
            b = br[0]
            bureau = {k: b.get(k) for k in ("bureau", "report_date", "score", "overdue_mn", "returned_cheques_n",
                                             "court_cases_n", "worst_status")}
    ews = [c for c in contractors if c["ews_band"] in ("moderate", "high", "critical")]
    totals = {"contractors": len(contractors) + len({r["contractor_id"] for r in dd_rows}),
              "book_contractors": len(contractors),
              "exposure": sum(c["ead"] for c in contractors) + lg_out + dd_funded,
              "non_funded": sum(c["non_funded"] for c in contractors) + lg_out,
              "attributable": sum(c["attributable"] for c in contractors) + lg_out + dd_funded,
              "deal_desk_outstanding": lg_out + dd_funded, "deal_desk_proposed": dd_proposed,
              "own_exposure": own, "lg_outstanding": lg_out, "due": due, "retention": ret,
              "in_early_warning": len(ews), "ews_exposure": sum(c["ead"] for c in ews),
              "high_dependence": sum(1 for c in contractors if c["dependence"] == "high")}
    sn = app["single_name"]
    combined = totals["attributable"] + own
    appetite = {"label": sn["label"], "basis": sn["basis"], "metric": "own exposure + attributable through contractors",
                "value": combined, "appetite": sn["appetite"], "trigger": sn["trigger"], "limit": sn["limit"],
                "utilisation_pct": 100 * combined / float(sn["limit"]), "status": common.status_against(combined, sn),
                "employer_backlog_guide": app["employer_backlog"], "deal_desk_dependence": dd_dep}
    cov = links.coverage(period)
    limits = [
        "Contractors and suppliers are those whose payments from the employer the bank sees (SUPPLIES edges, "
        f"rel-saudi-v1; {cov['supply_link_pct']:.1f}% of borrowers carry one); a contractor paid through another bank is missing.",
        "Attributable exposure assumes a contractor's risk to the employer is proportional to the share of its revenue "
        "the employer pays; project-level splits exist only for Deal Desk projects.",
        "Book exposure is per contractor, not per project: the corporate book release has no project or payment-"
        "certificate fields; payment certificates and LGs by project come from Deal Desk (dd_project, dd_facility_limit).",
    ]
    if not book:
        limits.append(f"{name} is not a corporate book borrower: no own exposure and no book contractors are read.")
    if not projects:
        limits.append("No Deal Desk project names this employer.")
    out = {"period": period, "employer": {"name": name, "borrower_id": (book or {}).get("borrower_id"),
                                          "entity_id": (ent or {}).get("entity_id"), "sector": (book or {}).get("sector"),
                                          "rating": own_attrs.get("rating_current"), "ews_band": own_attrs.get("ews_band"),
                                          "credit_status": (ent or {}).get("credit_status"), "bureau": bureau},
           "totals": totals, "appetite": appetite, "contractors": contractors[:60], "projects": dd_rows,
           "by_sector": _by_sector(contractors), "limits": limits, "coverage": cov,
           "lineage": [common.src("rel_edge", period, ["SUPPLIES"]), common.src("corp_facility", period),
                       common.src("corp_borrower", period), common.src("ews_corp", period), common.src("dd_project"),
                       common.src("dd_facility_limit"), common.src("bureau_entity_report"), common.src("b360_entity"),
                       common.src("risk_appetite")],
           "sources": {"attributable": common.derived("sum(contractor EAD x revenue share paid by the employer) + "
                                                      "project LGs outstanding", common.src("rel_edge", period),
                                                      common.src("corp_facility", period), common.src("dd_facility_limit"))},
           "money_unit": common.MONEY}
    out["text"] = writer.employer_text(out)
    if publish:
        out["view"] = common.publish_view("employer", re.sub(r"\W+", "_", str(name))[:40], out,
                                          {"employer": employer, "period": period})
    if book:  # R14 G: the registered row (net_employer_view), when the employer is in the published set
        from backend.intel.network import views
        reg = views.registered("net_employer_view", employer_id=book["borrower_id"])
        out["data_domains"] = ({"source": reg["source"], "published_at": reg["row"].get("published_at"),
                                "note": "Registered in Data Domains as Network intelligence · net_employer_view"} if reg else None)
    return clean(out)


def _by_sector(contractors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    agg: dict[str, dict[str, Any]] = {}
    for c in contractors:
        a = agg.setdefault(c["sector"], {"sector": c["sector"], "names": 0, "ead": 0.0, "attributable": 0.0})
        a["names"] += 1
        a["ead"] += c["ead"]
        a["attributable"] += c["attributable"]
    return sorted(agg.values(), key=lambda x: -x["attributable"])


def ranking(period: str | None = None, limit: int = 15, sector: str | None = None) -> dict[str, Any]:
    """Book-wide: the employers the bank is most exposed to through the contractors they pay."""
    period = common.resolve_quarter(period)
    sec = "AND b.sector = ?" if sector else ""
    got = rows(f"""
        WITH f AS (SELECT borrower_id, SUM(ead_sar_mn) AS ead FROM corp_facility WHERE reporting_quarter = ? GROUP BY 1),
             e AS (SELECT e.target_borrower_id AS employer_id, e.source_borrower_id AS contractor_id, e.revenue_share_pct
                   FROM rel_edge e JOIN corp_borrower s ON s.borrower_id = e.source_borrower_id
                        AND s.reporting_quarter = e.reporting_quarter
                   WHERE e.reporting_quarter = ? AND e.rel_type = 'SUPPLIES' AND s.sector = 'Construction')
        SELECT e.employer_id, b.borrower_name AS name, b.sector, COUNT(*) AS contractors,
               SUM(f.ead) AS contractor_ead, SUM(f.ead * e.revenue_share_pct / 100) AS attributable,
               MAX(e.revenue_share_pct) AS max_share, (SELECT ead FROM f WHERE f.borrower_id = e.employer_id) AS own_ead
        FROM e JOIN f ON f.borrower_id = e.contractor_id
             JOIN corp_borrower b ON b.borrower_id = e.employer_id AND b.reporting_quarter = ?
        WHERE b.sector <> 'Construction' {sec}
        GROUP BY 1, 2, 3 ORDER BY attributable DESC, e.employer_id LIMIT ?""",
               [period, period, period] + ([sector] if sector else []) + [int(limit)])
    sn = common.appetite()["single_name"]
    for r in got:
        tot = float(r["attributable"] or 0.0) + float(r["own_ead"] or 0.0)
        r["combined"] = tot
        r["status"] = common.status_against(tot, sn)
        r["utilisation_pct"] = 100 * tot / float(sn["limit"])
    return clean({"period": period, "rows": got, "appetite": {k: sn[k] for k in ("label", "appetite", "trigger", "limit", "basis")},
                  "deal_desk_employers": [{"entity_id": e["entity_id"], "name": e["entity_name"],
                                           "credit_status": e.get("credit_status")}
                                          for e in _dd("b360_entity") if e.get("role") == "employer"],
                  "method": "contractors = Construction-sector suppliers paid by the employer (SUPPLIES edges); "
                            "attributable = contractor EAD x revenue share paid",
                  "lineage": [common.src("rel_edge", period), common.src("corp_facility", period),
                              common.src("corp_borrower", period)], "money_unit": common.MONEY})
