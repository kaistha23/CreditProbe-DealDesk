"""The triage agent's tools, written to the contract's `Tool` fields (name, module, description, input schema,
read-only or proposal-only, the engine callable).

Read-only tools wrap the Early Warning release, Borrower 360, account conduct, the bureau, sector peers, the EWS
ECL-impact computation, the CBUAE indicator engine and the decision table. Proposal-only tools put a watchlist entry,
a SICR proposal or a UTP proposal into the approvals queue; none of them changes a stage or a flag (A4).
Every tool returns `summary` (one line for the trace) and `rows_scanned` (the A5 budget).
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from backend.agents_v5.ews import decide as dec
from backend.agents_v5.ews import followup as fu
from backend.agents_v5.ews import indicators as ind
from backend.agents_v5.ews import reads, store

MODULE = "early_warning"
SEVERITY = {"critical": 0, "high": 1, "moderate": 2, "low": 3, "none": 4}


def _today(today: str | None) -> dt.date:
    return dt.date.fromisoformat(today) if today else dt.datetime.now(dt.UTC).date()


def _money(v: float) -> str:
    return f"SAR {v:,.1f} m"


# ---------------------------------------------------------------- 1. the warned names in scope

def warned_names(domain: str = "corporate", period: str = "", sector: str = "", borrower: str = "",
                 include_followed: bool = True, max_names: int = 1500) -> dict[str, Any]:
    w = reads.warned(domain, period, sector=sector, borrower=borrower)
    rows = w["rows"]
    followed = set(store.followed(domain)) if include_followed else set()
    in_scope_ids = {r["borrower_id"] for r in rows}
    if borrower and not rows:
        return {"period": w["period"], "owners": [], "rows_scanned": w["rows_scanned"], "names": {},
                "summary": f"{borrower} is not on the {domain} book in {w['period']}.", "not_found": borrower}
    warned_rows = [r for r in rows if r["warned"] or borrower]
    stage3 = [r for r in warned_rows if int(r["stage"] or 0) >= 3 or r["defaulted"]]
    live = [r for r in warned_rows if not (int(r["stage"] or 0) >= 3 or r["defaulted"])]
    revisit = [r for r in rows if r["borrower_id"] in followed and r not in live and r not in stage3]
    live.sort(key=lambda r: (SEVERITY.get(r["band"], 9), -r["ead"], r["borrower_id"]))
    chosen = (revisit + live)[: max(0, int(max_names))]
    skipped = len(revisit) + len(live) - len(chosen)
    names = {r["borrower_id"]: {k: r[k] for k in ("borrower_name", "sector", "sub_sector", "score", "band", "stage",
                                                    "dpd", "ead", "ecl", "facilities", "warned")} | {"domain": domain}
             for r in chosen}
    for r in revisit:
        if r["borrower_id"] in names:
            names[r["borrower_id"]]["revisit"] = True
    return {"period": w["period"], "prior_period": w["prior_period"], "owners": list(names), "names": names,
            "sub_sectors": sorted({n["sub_sector"] for n in names.values()}),
            "warned_total": len(warned_rows) if not borrower else sum(1 for r in rows if r["warned"]),
            "warned_ead": sum(r["ead"] for r in warned_rows),
            "stage3": len(stage3), "stage3_ead": sum(r["ead"] for r in stage3),
            "stage3_ids": [r["borrower_id"] for r in stage3],
            "live": len(live), "revisit": len(revisit),
            "followed_not_in_book": sorted(followed - in_scope_ids) if not (sector or borrower) else [],
            "budget_skipped": skipped, "max_names": max_names, "rows_scanned": w["rows_scanned"],
            "goal_borrower": borrower or "", "domain": domain,
            "summary": (f"{len(warned_rows)} warned in {w['period']}: {len(stage3)} already Stage 3 (outside triage), "
                        f"{len(live)} to triage, {len(revisit)} followed up from earlier runs"
                        + (f"; {skipped} beyond the name budget" if skipped else "") + ".")}


# ---------------------------------------------------------------- 2–7. evidence reads

def rules_trend(domain: str, period: str, owners: list[str]) -> dict[str, Any]:
    r = reads.rules_and_trend(domain, period, owners)
    rising = sum(1 for v in r["by_owner"].values() if (v["change"] or 0) > 0)
    return {**r, "summary": f"Rules fired and 6-period score trend for {len(owners)} names; {rising} rose on the period."}


def b360_evidence(domain: str, period: str, owners: list[str], profile: bool = False) -> dict[str, Any]:
    r = reads.b360_evidence(domain, period, owners)
    if profile and len(owners) == 1:
        try:
            r["profile"] = reads.b360_profile(domain, period, owners[0])
        except Exception as exc:  # noqa: BLE001 -- the release facts above still stand
            r["profile_error"] = str(exc)
    cov = sum(1 for v in r["by_owner"].values() if any(c.get("breach_flag") for c in v.get("covenants") or []))
    return {**r, "summary": f"Borrower 360 facts for {len(owners)} names: exposure, group, rating, financials, "
                            f"collateral, covenants ({cov} with a covenant in breach); open conditions not on this build."}


def conduct(domain: str, period: str, owners: list[str]) -> dict[str, Any]:
    r = reads.conduct(domain, period, owners)
    ret = sum(1 for v in r["by_owner"].values() if v["returned_payments_q"] >= 2)
    return {**r, "summary": f"Account conduct for {len(owners)} names; {ret} with 2 or more returned payments."}


def bureau(domain: str, period: str, owners: list[str]) -> dict[str, Any]:
    r = reads.bureau(domain, period, owners)
    have = sum(1 for v in r["by_owner"].values() if v.get("available"))
    if not have:
        return {**r, "skipped": "No bureau record for these names on this build.",
                "summary": "Bureau: no record for these names on this build (step skipped)."}
    xd = sum(1 for v in r["by_owner"].values() if v.get("external_default"))
    return {**r, "summary": f"Bureau for {have} of {len(owners)} names; {xd} classified as defaulted elsewhere."}


def sector_peers(domain: str, period: str, sub_sectors: list[str]) -> dict[str, Any]:
    r = reads.sector_peers(domain, period, sub_sectors)
    stressed = sorted(k for k, v in r["by_sub_sector"].items() if v["sector_stress"])
    return {**r, "stressed": stressed,
            "summary": f"Peers in {len(sub_sectors)} sub-sectors; {len(stressed)} show sector stress."}


def changes(domain: str, period: str, owners: list[str]) -> dict[str, Any]:
    r = reads.changes(domain, period, owners)
    cured = sum(1 for v in r["by_owner"].values() if v.get("dpd_cured"))
    new = sum(1 for v in r["by_owner"].values() if v.get("new_reasons"))
    return {**r, "summary": f"Changes since {r.get('prior_period') or 'the first period'}: {new} names with new "
                            f"warning reasons, {cured} with arrears cured."}


def history(domain: str, owners: list[str], run_id: str = "") -> dict[str, Any]:
    prev = store.last_verdicts(owners, domain=domain, before_run=run_id)
    acts = store.open_actions(owners, domain=domain)
    props = pending_proposals(owners)
    return {"previous": prev, "actions": acts, "pending_proposals": props, "rows_scanned": len(prev) + len(acts),
            "summary": f"Earlier triage: {len(prev)} names seen before, {len(acts)} open actions, "
                       f"{len(props)} pending proposals."}


def pending_proposals(owners: list[str]) -> list[dict[str, Any]]:
    """Pending SICR, UTP and watch-list proposals of this agent in the approvals queue (expired ones drop out)."""
    from backend.agents_v5.runtime import approvals
    want = set(owners)
    out = []
    for r in approvals.listing(agent=AGENT_ID, status="pending"):
        ch = r.get("change") or {}
        if ch.get("borrower_id") in want:
            out.append({"borrower_id": ch["borrower_id"], "kind": KIND_OF.get(r["kind"], r["kind"]), "id": r["id"],
                        "expires_at": r.get("expires_at"), "approver_role": r.get("approver_role")})
    return out


# ---------------------------------------------------------------- 8. the CBUAE indicator engine

def assess(names: dict[str, Any], rules: dict[str, Any], b360: dict[str, Any], conduct: dict[str, Any],
           bureau: dict[str, Any] | None, peers: dict[str, Any], changes: dict[str, Any],
           domain: str = "corporate") -> dict[str, Any]:
    out = {}
    for o, n in names.items():
        b = b360.get(o) or {}
        e = {**b, "domain": domain, "conduct": conduct.get(o) or {}, "bureau": (bureau or {}).get(o) or {},
             "peers": peers.get(n.get("sub_sector")) or {}, "changes": changes.get(o) or {},
             "rules": (rules.get(o) or {}).get("rules") or []}
        out[o] = {"indicators": ind.assess(e), "evidence": e}
    fired = sum(1 for v in out.values() if v["indicators"])
    return {"by_owner": out, "rows_scanned": 0, "thresholds": ind.THRESHOLDS,
            "summary": f"CBUAE CRM Art. 6 and 7 indicators evaluated for {len(names)} names; {fired} with at least one."}


# ---------------------------------------------------------------- 9. the decision table and RM notes

def decide(names: dict[str, Any], assessed: dict[str, Any], rules: dict[str, Any], today: str = "") -> dict[str, Any]:
    day = _today(today)
    out, counts = {}, {v: 0 for v in dec.ORDER}
    for o, n in names.items():
        a = assessed.get(o) or {}
        e = a.get("evidence") or {}
        subj = {"borrower_id": o, "borrower_name": n.get("borrower_name"), "stage": n.get("stage"),
                "domain": e.get("domain") or "corporate",
                "band": n.get("band"), "score": n.get("score"), "indicators": a.get("indicators") or [],
                "rules": (rules.get(o) or {}).get("rules") or [], "changes": e.get("changes") or {},
                "rm": e.get("rm") or {}}
        v = dec.decide(subj)
        v["note"] = dec.action_note(subj, v, day)
        out[o] = v
        counts[v["verdict"]] += 1
    return {"by_owner": out, "counts": counts, "rows_scanned": 0, "today": day.isoformat(),
            "summary": "Verdicts: " + ", ".join(f"{counts[k]} {dec.LABEL[k].lower()}" for k in reversed(dec.ORDER)) + "."}


# ---------------------------------------------------------------- 10. ECL impact of the proposals

def ecl_impact(domain: str, period: str, verdicts: dict[str, Any]) -> dict[str, Any]:
    owners = [o for o, v in verdicts.items() if v["verdict"] in ("sicr", "utp", "watchlist")]
    if not owners:
        return {"by_owner": {}, "rows_scanned": 0, "skipped": "No proposal to size.", "summary": "No proposal to size."}
    r = reads.ecl_impact(domain, period, owners)
    tot = {k: {"names": 0, "ead": 0.0, "ecl_move": 0.0, "expected_uplift": 0.0} for k in ("sicr", "utp", "watchlist")}
    for o, x in r["by_owner"].items():
        k = verdicts[o]["verdict"]
        x["proposal_move"] = x["stage2_uplift"] if k == "sicr" else x["stage3_uplift"] if k == "utp" else 0.0
        t = tot[k]
        t["names"] += 1
        t["ead"] += x["ead"]
        t["ecl_move"] += x["proposal_move"]
        t["expected_uplift"] += x["expected_uplift"]
    return {**r, "totals": tot,
            "summary": (f"ECL impact: SICR {tot['sicr']['names']} names, EAD {_money(tot['sicr']['ead'])}, Stage 2 move "
                        f"+{_money(tot['sicr']['ecl_move'])}; UTP {tot['utp']['names']} names, EAD {_money(tot['utp']['ead'])}, "
                        f"Stage 3 move +{_money(tot['utp']['ecl_move'])}; expected uplift (EWS method) on all proposals "
                        f"+{_money(sum(t['expected_uplift'] for t in tot.values()))}.")}


# ---------------------------------------------------------------- 11. follow-up and escalation

def followup(names: dict[str, Any], verdicts: dict[str, Any], b360: dict[str, Any], history: dict[str, Any],
             today: str = "", defaulted: list[str] | None = None) -> dict[str, Any]:
    day = _today(today)
    now = {o: {"verdict": v["verdict"], "reason": v["reason"], "borrower_name": names[o].get("borrower_name"),
               "still_warned": bool(names[o].get("warned")), "rm": ((b360.get(o) or {}).get("rm") or {})}
           for o, v in verdicts.items()}
    outcomes = fu.review(now, history.get("previous") or {}, history.get("actions") or [], day, set(defaulted or []))
    counts: dict[str, int] = {}
    for x in outcomes:
        counts[x["outcome"]] = counts.get(x["outcome"], 0) + 1
    return {"outcomes": outcomes, "counts": counts, "rows_scanned": 0, "today": day.isoformat(),
            "summary": ("Follow-up on " + str(len(outcomes)) + " names: "
                        + (", ".join(f"{v} {k.replace('_', ' ')}" for k, v in sorted(counts.items())) or "none") + ".")}


# ---------------------------------------------------------------- 12. proposals (approvals queue only)

AGENT_ID = "ews.triage"
APPROVER = {"watchlist": "CREDIT_OFFICER", "sicr": "CCO", "utp": "CCO"}
EXPIRY_DAYS = {"watchlist": 20, "sicr": 10, "utp": 5}
TITLE = {"watchlist": "Add to watch list", "sicr": "Propose SICR (Stage 2)", "utp": "Propose unlikely-to-pay (Stage 3)"}
#: approvals-queue kinds
KIND = {"watchlist": "ews.watchlist_proposal", "sicr": "ews.sicr_proposal", "utp": "ews.utp_proposal"}
KIND_OF = {v: k for k, v in KIND.items()}


def _submit(change: dict[str, Any], kind: str, *, run_id: str, user: str, scope: str) -> str:
    """The runtime's `propose()`: a pending approval with maker-checker, the approver role and an expiry."""
    from backend.agents_v5.runtime import approvals
    row = approvals.propose(change, APPROVER[kind], kind=KIND[kind], title=change["title"], reason=change["reason"],
                            evidence=[f"{e['kind']}:{e['href']}" for e in change["evidence"] if e.get("href")],
                            agent=AGENT_ID, run_id=run_id, maker=user or f"agent:{AGENT_ID}", scope=scope,
                            expires_hours=24 * EXPIRY_DAYS[kind], risk="high" if kind == "utp" else "medium")
    return str(row["id"])


def _propose(kind: str, names: dict[str, Any], verdicts: dict[str, Any], assessed: dict[str, Any],
             impact: dict[str, Any] | None, history: dict[str, Any], b360: dict[str, Any], run_id: str = "",
             today: str = "", user: str = "", scope: str = "") -> dict[str, Any]:
    day = _today(today)
    pending = {(p["borrower_id"], p["kind"]) for p in history.get("pending_proposals") or []}
    made, dup, already, retail = [], [], [], []
    for o, v in verdicts.items():
        if v["verdict"] != kind:
            continue
        if (o, kind) in pending:
            dup.append(o)
            continue
        if kind == "watchlist" and ((b360.get(o) or {}).get("owner") or {}).get("watchlist_flag"):
            already.append(o)  # already on the bank's watch list: keep, nothing to propose
            continue
        if kind == "watchlist" and names.get(o, {}).get("domain") == "retail":
            retail.append(o)  # retail: enhanced monitoring is the collections action note, not a watch-list entry
            continue
        n = names[o]
        inds = [i for i in (assessed.get(o) or {}).get("indicators") or [] if i["code"] in v["basis"]]
        links = (b360.get(o) or {}).get("links") or {}
        change = {
            "type": KIND[kind], "module": MODULE, "borrower_id": o, "borrower_name": n.get("borrower_name"),
            "title": f"{TITLE[kind]}: {n.get('borrower_name') or o}",
            "current_stage": n.get("stage"), "proposed": {"watchlist": "Watch list entry", "sicr": "Stage 2 (SICR)",
                                                          "utp": "Stage 3 (unlikely to pay)"}[kind],
            "reason": v["reason"], "indicators": [{"code": i["code"], "label": i["label"], "article": i["article"]["ref"],
                                                   "fields": i["fields"]} for i in inds],
            "articles": v["articles"], "ecl_impact": (impact or {}).get(o),
            "ead_sar_mn": n.get("ead"), "maker": user or f"agent:{AGENT_ID}", "checker_role": APPROVER[kind],
            "expires": (day + dt.timedelta(days=EXPIRY_DAYS[kind])).isoformat(),
            "action_note": v.get("note"),
            "reversibility": ("Reversible until approved. Approval records the decision for the staging process; "
                              "the agent never writes the stage."),
            "evidence": [{"kind": "borrower_360", "href": links.get("borrower_360")},
                         {"kind": "early_warning", "href": links.get("early_warning")}],
        }
        ref = _submit(change, kind, run_id=run_id, user=user, scope=scope)
        store.add_proposal(run_id or "adhoc", o, kind, ref, day.isoformat(), change)
        made.append({"borrower_id": o, "approval_id": ref, "approver_role": APPROVER[kind],
                     "expires": change["expires"], "title": change["title"]})
    if not made and not dup and not already and not retail:
        return {"proposals": [], "rows_scanned": 0, "skipped": f"No {kind} verdict in this run.",
                "summary": f"No {dec.LABEL[kind].lower()} proposals."}
    return {"proposals": made, "duplicates": dup, "already_on_watchlist": already, "retail_monitoring": retail,
            "rows_scanned": 0,
            "summary": (f"{len(made)} {TITLE[kind].lower()} proposals to the approvals queue ({APPROVER[kind]})"
                        + (f"; {len(dup)} already pending" if dup else "")
                        + (f"; {len(already)} already on the watch list (kept)" if already else "")
                        + (f"; {len(retail)} retail customers to enhanced collections monitoring (action notes, the "
                           "retail book has no watch-list entry to approve)" if retail else "") + ".")}


def propose_utp(**kw: Any) -> dict[str, Any]:
    return _propose("utp", **kw)


def propose_sicr(**kw: Any) -> dict[str, Any]:
    return _propose("sicr", **kw)


def propose_watchlist(**kw: Any) -> dict[str, Any]:
    return _propose("watchlist", **kw)


# ---------------------------------------------------------------- 13. the portfolio summary

def summary(scope: dict[str, Any], verdicts: dict[str, Any], impact: dict[str, Any] | None,
            follow: dict[str, Any] | None) -> dict[str, Any]:
    c = verdicts.get("counts") or {}
    tot = (impact or {}).get("totals") or {}
    reviewed = sum(c.values())
    s = tot.get("sicr") or {}
    u = tot.get("utp") or {}
    fig = {"warned": scope.get("warned_total", 0), "reviewed": reviewed, "stage3_outside": scope.get("stage3", 0),
           "budget_skipped": scope.get("budget_skipped", 0), **{k: c.get(k, 0) for k in dec.ORDER},
           "sicr_ead": s.get("ead", 0.0), "sicr_ecl": s.get("ecl_move", 0.0),
           "utp_ead": u.get("ead", 0.0), "utp_ecl": u.get("ecl_move", 0.0),
           "proposal_ecl": round(float(s.get("ecl_move", 0.0)) + float(u.get("ecl_move", 0.0)), 6),
           "expected_uplift": sum((t or {}).get("expected_uplift", 0.0) for t in tot.values()),
           "followup": (follow or {}).get("counts") or {}}
    # where the proposals concentrate (sector, or product for retail), by proposal EAD
    names = scope.get("names") or {}
    imp = (impact or {}).get("by_owner") or {}
    conc: dict[str, dict[str, float]] = {}
    for o, v in (verdicts.get("by_owner") or {}).items():
        if v["verdict"] in ("sicr", "utp") and o in imp:
            k = str(names.get(o, {}).get("sector") or "other")
            c2 = conc.setdefault(k, {"names": 0, "ead": 0.0, "ecl_move": 0.0})
            c2["names"] += 1
            c2["ead"] += imp[o]["ead"]
            c2["ecl_move"] += imp[o]["proposal_move"]
    top = sorted(conc.items(), key=lambda kv: -kv[1]["ead"])[:3]
    fig["concentration"] = [{"segment": k, **v} for k, v in top]
    line = (f"{reviewed} of {fig['warned']} warnings reviewed ({fig['stage3_outside']} already Stage 3): "
            f"{fig['noise']} noise, {fig['watch']} watch, {fig['watchlist']} watchlist, {fig['sicr']} SICR proposals "
            f"(EAD {_money(fig['sicr_ead'])}, ECL +{_money(fig['sicr_ecl'])}), {fig['utp']} UTP "
            f"(EAD {_money(fig['utp_ead'])}, ECL +{_money(fig['utp_ecl'])}).")
    by = verdicts.get("by_owner") or {}
    if scope.get("goal_borrower") and len(by) == 1:  # one borrower: its verdict, not a portfolio line
        o, v = next(iter(by.items()))
        n = (scope.get("names") or {}).get(o, {})
        x = ((impact or {}).get("by_owner") or {}).get(o)
        line = ((f"{n['borrower_name']} ({o})" if n.get("borrower_name") else o) + f": {v['label']}"
                + (f"; EAD {_money(x['ead'])}, ECL move if approved +{_money(x['proposal_move'])}" if x and
                   v["verdict"] in ("sicr", "utp") else "") + ".")
    return {"figures": fig, "line": line, "rows_scanned": 0, "summary": line}


__all__ = ["AGENT_ID", "APPROVER", "KIND", "assess", "b360_evidence", "bureau", "changes", "conduct", "decide",
           "ecl_impact", "followup", "history", "pending_proposals", "propose_sicr", "propose_utp", "propose_watchlist",
           "rules_trend", "sector_peers", "summary", "warned_names"]
