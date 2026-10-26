"""A deal's data for the papers: every relation the 20 anatomy sections and the CreditProbe sections read, through `source`.

    D = load("DD-31")
    D.p                      the dd_proposal row (dict with _src)
    D.rows("dd_project")     the deal's rows of a relation ([] when the relation is empty or missing)
    D.status["dd_project"]   live | empty | missing
    D.money(12.5)            "AED 12.5m" in the deal's currency

Scopes: a deal relation is filtered by proposal_id; a group relation by proposal_id, then group_id, then obligor_id (the first
that returns rows); deposits by obligor_id. Formatting helpers live here so every writer writes figures the same way.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from backend.dealdesk.house_style.bankform import source as S

#: the relations the papers read (docs/v5/R12_DATA_CONTRACT.md); all reached through `source`
DEAL = ("dd_facility_limit", "dd_proposal_facility", "dd_security", "dd_collateral_guarantee", "dd_tnc", "dd_condition", "dd_group_exposure",
        "dd_reference", "dd_account_conduct", "dd_returned_cheque", "dd_financials_detail", "dd_obligor_financials", "dd_result", "dd_review_finding",
        "dd_swot", "dd_stress_result", "dd_monitoring_plan", "dd_document", "dd_workflow_event", "dd_project", "dd_project_cashflow", "dd_promise",
        "dd_query", "dd_raroc_drift", "dd_syndication", "dd_escrow_account", "dd_sme_application", "bureau_entity_report", "bureau_cbrbr",
        "other_bank_facility", "dd_precedent", "dd_forward_risk", "dd_business_profile")
PRODUCT = ("dd_syndication", "dd_escrow_account", "dd_sme_application")
GROUP = ("b360_entity", "b360_shareholder", "b360_board", "b360_insider_link", "b360_ownership_change", "rel_shared_collateral")
BANK = ("dd_stress_scenario", "dd_document_rule")

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def d(x: Any) -> str:
    """'30 Jun 2026' from an ISO date; '2026Q2' and 'FY2025' pass through; '' for nothing."""
    if x in (None, ""):
        return ""
    if isinstance(x, (date, datetime)):
        return f"{x.day} {MONTHS[x.month - 1]} {x.year}"
    s = str(x)
    try:
        if len(s) >= 10 and s[4] == "-" and s[7] == "-":
            y, m, dd = int(s[:4]), int(s[5:7]), int(s[8:10])
            return f"{dd} {MONTHS[m - 1]} {y}"
        if len(s) == 7 and s[4] == "-":
            return f"{MONTHS[int(s[5:7]) - 1]} {s[:4]}"
    except (ValueError, IndexError):
        return s
    return s


def num(x: Any) -> float | None:
    try:
        if x in (None, ""):
            return None
        return float(x)
    except (TypeError, ValueError):
        return None


def share(x: Any) -> float | None:
    """A share as a fraction: 0.44 stays, 44 (a percent) becomes 0.44."""
    v = num(x)
    if v is None:
        return None
    return v / 100.0 if abs(v) > 1.5 else v


def pct(x: Any, dp: int = 1) -> str:
    v = share(x)
    return "" if v is None else f"{v * 100:,.{dp}f}%"


def pct_raw(x: Any, dp: int = 1) -> str:
    """A value already in percent (14.2 -> '14.2%')."""
    v = num(x)
    return "" if v is None else f"{v:,.{dp}f}%"


def xx(x: Any, dp: int = 2) -> str:
    v = num(x)
    return "" if v is None else f"{v:,.{dp}f}x"


@dataclass
class Deal:
    pid: str
    p: dict[str, Any]
    data: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    status: dict[str, str] = field(default_factory=dict)
    ccy: str = "AED"
    as_of: str = ""

    def rows(self, relation: str) -> list[dict[str, Any]]:
        return self.data.get(relation, [])

    def one(self, relation: str) -> dict[str, Any] | None:
        r = self.rows(relation)
        return r[0] if r else None

    def money(self, x: Any, dp: int = 1) -> str:
        v = num(x)
        if v is None:
            return ""
        if round(v, dp) == 0:
            v = 0.0
        if abs(v) >= 1000 and dp <= 1:
            return f"{self.ccy} {v / 1000:,.2f}bn"
        return f"{self.ccy} {v:,.{dp}f}m"

    def m(self, x: Any, dp: int = 1) -> str:
        """A table cell in millions, no unit."""
        v = num(x)
        return "–" if v is None else f"{v:,.{dp}f}"

    @property
    def name(self) -> str:
        return str(S.first(self.p, "obligor_name", "customer_name", default=self.pid))

    @property
    def group(self) -> str:
        return str(S.first(self.p, "group_name", default=""))

    def get(self, *cols: str, default: Any = None) -> Any:
        return S.first(self.p, *cols, default=default)

    def src(self, relation: str) -> str:
        rows = self.rows(relation)
        if not rows:
            return f"{S.domain_of(relation)} · {relation} · {self.status.get(relation, 'missing')}"
        s = rows[0]["_src"]
        n = len(rows)
        return f"{s['domain']} · {s.get('relation') or relation} · {n} row{'s' if n != 1 else ''}" + (f" · {s['period']}" if s.get("period") else "")


class NotFound(KeyError):
    pass


def _rows(relation: str, **flt: Any) -> tuple[list[dict[str, Any]], str]:
    return S._read(relation, flt)  # noqa: SLF001 - same package


def _user_proposal(pid: str) -> dict[str, Any] | None:
    """The desk's own proposal (proposals.get, R11 user store) in the dd_proposal row shape, or None."""
    try:
        from backend.dealdesk import proposals
        pr = proposals.get(pid)
    except Exception:  # noqa: BLE001 - not in the desk store either
        return None
    if not isinstance(pr, dict) or not pr.get("obligor"):
        return None
    import json
    ob, ask = pr.get("obligor") or {}, pr.get("ask") or {}
    return {"proposal_id": pid, "obligor_id": ob.get("obligor_id"), "obligor_name": ob.get("name"), "group_id": ob.get("group_id"),
            "group_name": ob.get("group_name"), "sector": ob.get("sector"), "segment": ob.get("segment"),
            "internal_rating": ob.get("internal_rating"), "simah_flag": ob.get("simah_flag"), "rm": pr.get("rm"),
            "currency": ask.get("currency", "SAR"), "amount": ask.get("amount"), "tenor_years": ask.get("tenor_years"),
            "facility_type": ask.get("facility_type"), "received": pr.get("received"), "case": pr.get("case", ""),
            "book_obligor_id": ob.get("book_id") or ob.get("obligor_id"),
            "proposal_json": json.dumps(pr, default=str), "_src": {"domain": "deal_desk", "relation": "desk proposal store"}}


def load(pid: str, price: bool = True) -> Deal:
    """price=False skips the engine/optimiser fallback for an unpriced deal (the proposal check does not need dd_result)."""
    from backend.dealdesk.house_style.bankform import norm as N
    deal_rows, st_deal = _rows("dd_deal", proposal_id=pid)
    leg_rows, st_leg = _rows("dd_proposal", proposal_id=pid)
    if not leg_rows:  # a pipeline application (PL-nn) carries the same columns in dd_pipeline
        leg_rows, st_pl = _rows("dd_pipeline", proposal_id=pid)
        st_leg = f"{st_leg}; dd_pipeline {st_pl}"
    if not deal_rows and not leg_rows:
        # R15 b (L7): a proposal opened on the desk (a renewal started from the Book, or a new proposal) lives in the desk's
        # proposal store until it is published: read it there, labelled, so the renewal can be drafted and checked from data.
        user = _user_proposal(pid)
        if user is None:
            raise NotFound(f"No proposal {pid} in Data Domains (dd_deal {st_deal}, dd_proposal {st_leg}).")
        leg_rows, st_leg = [user], "desk proposal store (not yet published to Data Domains)"
    deal, legacy = (deal_rows[-1] if deal_rows else None), (leg_rows[-1] if leg_rows else None)
    pj = (deal or {}).get("proposal_json") or (legacy or {}).get("proposal_json")
    if isinstance(pj, str):
        import json
        try:
            pj = json.loads(pj)
        except ValueError:
            pj = None
    gid = S.first(deal, "group_id", default=S.first(legacy, "group_id"))
    ents, st_ent = _rows("b360_entity", group_id=gid) if gid else ([], "missing")
    subject = next((e for e in ents if e.get("role") == "subject"), None)
    p = N.header(deal, legacy, pj if isinstance(pj, dict) else None, subject)
    D = Deal(pid=pid, p=p, ccy=str(p.get("currency") or "SAR"),
             as_of=str(S.first(p, "as_of", default=_quarter_end(S.first(p, "reporting_quarter", default="")))))
    p.setdefault("as_of", D.as_of)
    D.data["dd_proposal"], D.status["dd_proposal"] = [p], "live"
    for rel in DEAL:
        D.data[rel], D.status[rel] = _rows(rel, proposal_id=pid)
    for rel in PRODUCT:
        D.data[rel], D.status[rel] = _rows(rel, proposal_id=pid)
    for rel in BANK:
        D.data[rel], D.status[rel] = _rows(rel)
    # Borrower 360: the group's entities, then everything keyed by entity
    ids = [e.get("entity_id") for e in ents if e.get("entity_id")]
    names = {str(e.get("entity_id")): e.get("entity_name") for e in ents}
    for rel in GROUP[1:]:
        if rel == "rel_shared_collateral":
            D.data[rel], D.status[rel] = (_rows(rel, group_id=gid) if gid and str(gid).startswith(("CG", "G")) else ([], "empty"))
        elif ids:
            D.data[rel], D.status[rel] = _rows(rel, entity_id=ids)
        else:
            D.data[rel], D.status[rel] = _rows(rel, group_id=gid) if gid else ([], "missing")
    exp = {str(r.get("entity_id")): r for r in D.rows("dd_group_exposure")}
    D.data["b360_entity"], D.status["b360_entity"] = [N.entity(e, exp) for e in ents], st_ent if not ents else "live"
    D.data["b360_shareholder"] = [N.shareholder(r, names) for r in D.rows("b360_shareholder")]
    D.data["b360_board"] = [N.board(r, names) for r in D.rows("b360_board")]
    D.data["b360_insider_link"] = [N.insider(r, names) for r in D.rows("b360_insider_link")]
    D.data["b360_ownership_change"] = [N.ownership_change(r, names) for r in D.rows("b360_ownership_change")]
    # Deal Desk relations in the writers' shape
    D.data["dd_facility_limit"] = sorted([N.facility_limit(r) for r in D.rows("dd_facility_limit")], key=lambda r: (r.get("seq") is None, r.get("seq") or 0))
    lnames = {str(r.get("limit_id")): r.get("name") for r in D.rows("dd_facility_limit")}
    if not D.rows("dd_security") and D.rows("dd_collateral_guarantee"):
        D.data["dd_security"], D.status["dd_security"] = D.rows("dd_collateral_guarantee"), "live"
    D.data["dd_security"] = [N.security(r, lnames) for r in D.rows("dd_security")]
    D.data["dd_tnc"] = sorted([N.tnc(r, lnames) for r in D.rows("dd_tnc")], key=lambda r: (str(r.get("limit_group")), r.get("seq") or 0))
    D.data["dd_condition"] = [N.condition(r, lnames) for r in D.rows("dd_condition")]
    D.data["dd_reference"] = sorted([N.reference(r) for r in D.rows("dd_reference")], key=lambda r: str(r.get("date") or ""))
    if not D.rows("dd_account_conduct"):
        oid = p.get("book_obligor_id")
        if oid:
            D.data["dd_account_conduct"], D.status["dd_account_conduct"] = _rows("dep_month", obligor_id=oid)
    D.data["dd_account_conduct"] = [N.conduct(r) for r in D.rows("dd_account_conduct")]
    if not D.rows("dd_financials_detail") and D.rows("dd_obligor_financials"):
        D.data["dd_financials_detail"], D.status["dd_financials_detail"] = D.rows("dd_obligor_financials"), "live"
    D.data["dd_financials_detail"] = [N.financials(r) for r in D.rows("dd_financials_detail")]
    emp = {str(e.get("entity_id")): e for e in ents}
    if D.rows("dd_project"):
        more = [r.get("employer_entity_id") for r in D.rows("dd_project") if r.get("employer_entity_id") and str(r.get("employer_entity_id")) not in emp]
        if more:
            emp.update({str(e.get("entity_id")): e for e in _rows("b360_entity", entity_id=more)[0]})
    D.data["dd_project"] = [N.project(r, emp.get(str(r.get("employer_entity_id")))) for r in D.rows("dd_project")]
    cf = D.rows("dd_project_cashflow")
    base = [r for r in cf if r.get("scenario") in (None, "", "base")]
    stressed = {(r.get("project_id"), r.get("month_no")): r for r in cf if "60" in str(r.get("scenario") or "")}
    out = []
    for r in base:
        x = N.cashflow(r)
        s60 = stressed.get((r.get("project_id"), r.get("month_no")))
        if s60 is not None and x.get("cumulative_delay_60d") is None:
            x["cumulative_delay_60d"] = S.first(s60, "cumulative_mn", "cumulative")
        out.append(x)
    D.data["dd_project_cashflow"] = sorted(out, key=lambda r: (str(r.get("project_id")), num(r.get("month")) or 0))
    D.data["bureau_entity_report"] = [N.bureau(r) for r in D.rows("bureau_entity_report")]
    D.data["bureau_cbrbr"] = [N.cbrbr(r) for r in D.rows("bureau_cbrbr")]
    D.data["other_bank_facility"] = [N.other_bank(r) for r in D.rows("other_bank_facility")]
    D.data["dd_review_finding"] = [N.finding(r) for r in D.rows("dd_review_finding") if str(r.get("status") or "open") != "superseded"]
    D.data["dd_swot"] = [N.swot(r) for r in D.rows("dd_swot")]
    plans = [N.plan(r) for r in D.rows("dd_monitoring_plan")]
    D.data["dd_monitoring_plan"] = [r for r in plans if str(r.get("status") or "active") == "active"] or plans
    labels = {str(r.get("scenario_id")): r.get("label") or r.get("name") for r in D.rows("dd_stress_scenario")}
    runs = D.rows("dd_stress_result")
    if runs and any(r.get("run_at") for r in runs):  # the latest run only
        last = max(str(r.get("run_at") or "") for r in runs)
        runs = [r for r in runs if str(r.get("run_at") or "") == last] or runs
    D.data["dd_stress_result"] = [N.stress(r, labels) for r in runs]
    D.data["dd_stress_scenario"] = [N.scenario(r) for r in D.rows("dd_stress_scenario") if str(r.get("status") or "approved") != "retired"
                                    and str(r.get("scope") or "bank") == "bank" or r.get("proposal_id") == pid]
    clauses = {str(r.get("rule_id")): r.get("clause") for r in D.rows("dd_document_rule")}
    D.data["dd_document"] = [N.document(r, clauses) for r in D.rows("dd_document")]
    D.data["dd_promise"] = [N.promise(r) for r in D.rows("dd_promise")]
    if price and not D.rows("dd_result"):  # not yet priced into dd_result (R12 deals): the engine prices it the same way, labelled as engine lineage
        from backend.dealdesk.house_style.bankform import cp_writers
        D.data["dd_result"] = cp_writers._cached("result", D, cp_writers._engine_result_raw)  # noqa: SLF001
        if D.data["dd_result"]:
            D.status["dd_result"] = "engine"
    if not p.get("previous_committee_ref"):
        cds = [r for r in D.rows("dd_reference") if str(r.get("kind")) in ("committee_decision", "limit_history") and r.get("committee_ref")]
        if cds:
            p["previous_committee_ref"], p["previous_committee_date"] = cds[-1]["committee_ref"], cds[-1].get("date")
    if p.get("group_exposure_funded") is None and D.rows("dd_group_exposure"):
        p["group_exposure_funded"] = sum(num(r.get("funded_proposed_mn")) or 0 for r in D.rows("dd_group_exposure"))
    return D


def _quarter_end(q: str) -> str:
    try:
        y, n = int(str(q)[:4]), int(str(q)[-1])
        return f"{y}-{n * 3:02d}-{[31, 30, 30, 31][n - 1]}"
    except (ValueError, IndexError):
        return str(q)
