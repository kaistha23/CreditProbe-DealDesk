"""The issue views by id, and the list of every open issue (the "Issues on the books" tab).

Ids are the brief line ids, so a brief line and its issue view are the same object:
    crm:<check_id>[:retail]   a CBUAE CRM check (crm:CRM-9.23 has the deep dive of K4)
    le:near                   large exposures
    ecl:anomalies:<run>       ECL input data issues
    ews:migrations:<period>   exposures moved to a worse stage
"""
from __future__ import annotations

import copy
import functools
import json
from datetime import date
from typing import Any

from backend.agents_v5.brief import readers as R
from backend.agents_v5.brief.items import fmt
from backend.regulatory import crm_checks as C
from backend.regulatory.issues import checks, common as K, floor, others


class UnknownIssue(KeyError):
    pass


def _today(today: date | str | None) -> date:
    if isinstance(today, date):
        return today
    try:
        return date.fromisoformat(str(today))
    except (TypeError, ValueError):
        return date.today()


@functools.lru_cache(maxsize=32)
def _get(issue_id: str, today: str) -> str:
    t = date.fromisoformat(today)
    if issue_id.startswith("crm:"):
        parts = issue_id.split(":")
        check_id = parts[1]
        book = parts[2] if len(parts) > 2 else "corporate"
        if check_id not in C.BY_ID or book not in C.BY_ID[check_id].books:
            raise UnknownIssue(issue_id)
        v = floor.view(t) if (check_id == floor.CHECK_ID and book == "corporate") else checks.view(check_id, book, t)
    elif issue_id == "le:near" or issue_id.startswith("le:"):
        v = others.large_exposure(t)
    elif issue_id.startswith("ecl:anomalies"):
        v = others.ecl_anomalies(issue_id.split(":", 2)[2] if issue_id.count(":") >= 2 else "", t)
    elif issue_id.startswith("ews:migrations"):
        v = others.migrations(issue_id.split(":", 2)[2] if issue_id.count(":") >= 2 else "", t)
    else:
        raise UnknownIssue(issue_id)
    v["id"] = issue_id
    v["href"] = K.issue_href(issue_id)
    return json.dumps(v, default=float)


def get(issue_id: str, today: date | str | None = None) -> dict[str, Any]:
    return json.loads(_get(str(issue_id), _today(today).isoformat()))


def list_issues(today: date | str | None = None) -> dict[str, Any]:
    """Every check in breach (both books) plus the other issue kinds, largest money first."""
    r = R.read("regulatory", "crm_check", where="breaches > 0", order="shortfall_sar_mn DESC, ead_sar_mn DESC")
    out = []
    for c in r.rows:
        iid = f"crm:{c['check_id']}" + ("" if c["book"] == "corporate" else f":{c['book']}")
        sf, ead = float(c.get("shortfall_sar_mn") or 0.0), float(c.get("ead_sar_mn") or 0.0)
        n = int(c["breaches"])
        unit = "account" if c["book"] == "retail" else "facility"
        line = (f"{K.words(n, unit, unit[:-1] + 'ies' if unit == 'facility' else unit + 's')}, {fmt(ead, 'SAR mn')} EAD"
                + (f", {fmt(sf, 'SAR mn')} short" if sf else ""))
        if c.get("level") == "book" or str(c["check_id"]) == "CRM-12.3":
            line = f"Stage 3 ({fmt(ead, 'SAR mn')} EAD) is above 5% of the {c['book']} book"
        sev = "critical" if sf > 100 else str(c["severity"])
        out.append({"id": iid, "kind": checks.FAMILY.get(str(c["check_id"]), "check"), "title": c["title"],
                    "article": c["article"], "book": c["book"], "period": c["period"], "n": n,
                    "ead": ead, "shortfall": sf, "severity": sev, "line": line, "href": K.issue_href(iid)})
    extra = []
    a = R.read("ecl_runs", "ecl_anomaly", columns="run_id, count(*) AS n, sum(rerun_required) AS r", group="run_id",
               order="run_id DESC", limit=1)
    if a.rows:
        x = a.rows[0]
        extra.append({"id": f"ecl:anomalies:{x['run_id']}", "kind": "ecl_anomaly", "title": "ECL input data issues",
                      "article": "ECL run controls", "book": "corporate", "period": x["run_id"], "n": int(x["n"]),
                      "ead": None, "shortfall": 0.0, "severity": "high" if int(x["r"] or 0) else "medium",
                      "line": f"{int(x['n'])} issues, {int(x['r'] or 0)} need a re-run",
                      "href": K.issue_href(f"ecl:anomalies:{x['run_id']}")})
    le = R.read("collateral", "col_large_exposure", columns="max(pct_of_capital) AS p, max(limit_pct) AS l, "
                "max(as_of_date) AS d")
    if le.rows and le.rows[0].get("p") is not None:
        x = le.rows[0]
        extra.append({"id": "le:near", "kind": "large_exposure", "title": "Large exposures",
                      "article": "Large exposures (25% of Tier 1)", "book": "corporate", "period": str(x["d"]),
                      "n": None, "ead": None, "shortfall": 0.0,
                      "severity": "high" if float(x["p"]) >= 0.8 * float(x["l"]) else "low",
                      "line": f"largest group {float(x['p']):.1f}% of Tier 1 against {float(x['l']):.0f}%",
                      "href": K.issue_href("le:near")})
    rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    allx = sorted(out + extra, key=lambda i: (rank.get(i["severity"], 4), -(i["shortfall"] or 0.0), -(i["ead"] or 0.0),
                                              i["id"]))
    return {"issues": allx, "count": len(allx),
            "trace": [r.stamp({"breaches": "> 0"}, "")]}


def brief_line(check_id: str) -> str | None:
    """The brief line for a check, naming both rates (K4 (1)); None when the check has no bank-vs-requirement figure."""
    try:
        if check_id == floor.CHECK_ID:
            return floor.line()
        v = get(f"crm:{check_id}")
        cmp_ = v.get("comparison") or {}
        return cmp_.get("sentence") or None
    except Exception:  # noqa: BLE001 - the brief never fails on a view
        return None


def why(issue_id: str) -> dict[str, Any]:
    """What the brief's Why needs from the view: the comparison, the bridge and where to open the full view."""
    v = copy.deepcopy(get(issue_id))
    return {"headline": v.get("headline"), "comparison": v.get("comparison"), "bridge": v.get("bridge"),
            "rule": v.get("rule"), "href": v.get("href"), "plain_words": v.get("plain_words")}
