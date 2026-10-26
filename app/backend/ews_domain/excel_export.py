"""Export to Excel: the rows on an Early Warning screen, as a real workbook.

INBOX Item 3, A1. Every level (portfolio, segment, classification,
sub-segment), every customer list after any filters, and every customer page
exports the rows it shows, with full detail:

  Customers    one row per customer or borrower in the view: every field shown
               on the cards (score, band, already bad, forward risk, exposure,
               ECL, worst DPD and stage, segments, the owner facts) and the
               rules that fired;
  Exposures    one row per facility or account of those customers in the view;
  Rules fired  one row per rule that fired on an exposure, with the value read
               and the weight;
  About        book, period, scope, filters, rule set, band floors and row counts.

The rows are the list's own query (drill.list_filter), so the workbook and the
screen cannot disagree. Ratings sort in the global order (backend/v5common/ratings).
"""
from __future__ import annotations

import re
from typing import Any

from backend.ews_domain import drill
from backend.ews_domain import ews_rules as ews
from backend.ews_domain import reader as rd
from backend.house_style import Meta, stream
from backend.house_style.xlsx import Col
from backend.v5common import ratings


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-")[:60] or "all"


def workbook(domain_id: str, period: str = "", segment: str = "", classification: str = "",
             subsegment: str = "", cohort: str = "all", reason: str = "", layer: str = "", dpd: str = "",
             stage: int | None = None, band_min: str = "", search: str = "",
             customer_id: str = "", generated_by: str = "", dims: dict[str, str] | None = None) -> tuple[bytes, str]:
    scope = drill.Scope(domain_id, segment, classification, subsegment, dims=dims)
    spec = scope.spec
    chosen, _, _ = rd.resolve_period(domain_id, period)
    P, O, K = spec["period"], spec["owner_key"], spec["key"]
    base, params = drill._owner_rows_sql(scope, chosen)
    if customer_id:
        filt, cparams = "owner = ?", [customer_id]
        cohort = "all"
    else:
        filt, cparams = drill.list_filter(domain_id, cohort or "all", reason, layer, dpd, stage, band_min, search)
    owners = rd.q(f"SELECT * FROM ({base}) WHERE {filt} ORDER BY score DESC, exposure DESC, owner",
                  [*params, *cparams])
    if customer_id and not owners:
        raise rd.ReadRefused(f"{customer_id} has no exposures in {chosen} in this view.")
    ids = [r["owner"] for r in owners]
    facts = _facts(domain_id, chosen)
    where, wparams = scope.where()
    exposures = rd.q(
        f'SELECT * FROM {scope.rel} WHERE "{P}" = ? AND ({where}) AND "{O}" IN '
        f"(SELECT owner FROM ({base}) WHERE {filt}) ORDER BY \"{O}\", ews_score DESC, \"{K}\"",
        [chosen, *wparams, *params, *cparams])
    floors = dict(zip(("moderate", "high", "critical"), ews.BAND_FLOORS[domain_id]))
    corporate = domain_id == "corporate"
    fact_cols = (["group_id", "group_name", "rating_current", "rating_previous", "rating_outlook", "watchlist_flag",
                  "watchlist_reason", "relationship_tier", "region"] if corporate else
                 ["customer_segment", "employment_type", "region", "tenure_months", "behaviour_score",
                  "behaviour_score_previous", "score_band", "score_migration", "accounts_held"])

    owner_label = "Borrower" if corporate else "Customer"
    scope_label = " › ".join(x for x in (segment, drill.CLASSIFICATIONS.get(scope.classification, {}).get("label", ""),
                                         subsegment) if x) or ("Total corporate" if corporate else "Total retail")
    meta = Meta(f"Early Warning · {customer_id or scope_label}", book=domain_id, period=chosen,
                subject=f"{scope_label} · cohort {cohort or 'all'}" + (f" · {customer_id}" if customer_id else ""),
                generated_by=generated_by)
    cust_cols = [Col("id", f"{owner_label} ID"), Col("name", f"{owner_label} name"), Col("score", "Score", "int"),
                 Col("band", "Band", "rating"), Col("bad", "Already bad"), Col("fwd", "Forward risk"),
                 Col("exposure", "Exposure (SAR m)", "sar_mn"), Col("ecl", "ECL (SAR m)", "sar_mn"),
                 Col("n", "Facilities" if corporate else "Accounts", "int"), Col("dpd", "Worst DPD", "days"),
                 Col("stage", "Worst stage", "int"), Col("segments", "Segments"), Col("subs", "Sub-segments"),
                 Col("rules", "Rules fired"),
                 *[Col(c, c.replace("_", " ").capitalize(), "rating" if c.startswith("rating") or c == "score_band"
                       else "int" if c in ("tenure_months", "behaviour_score", "behaviour_score_previous", "accounts_held") else "")
                   for c in fact_cols]]
    rows = []
    for r in owners:
        score = int(r["score"] or 0)
        fired = sorted({x.strip() for x in (r["reasons_raw"] or "").split(";") if x.strip()})
        f = facts.get(r["owner"], {})
        rows.append([r["owner"], r["owner_name"], score, ews.band_of(domain_id, score), bool(r["bad"]),
                     bool(score >= floors["moderate"] and not r["bad"]), r["exposure"], r["ecl"], r["facilities"],
                     r["dpd"], r["stage"], r["segments"], r["subsegments"], "; ".join(fired),
                     *[f.get(c) for c in fact_cols]])
    owners_sheet = stream.Sheet("Customers" if not corporate else "Borrowers", meta, cust_cols, rows,
                                title=f"Early Warning · {'Borrowers' if corporate else 'Customers'} · {scope_label}")
    n_cust = len(rows)

    exp_cols = [O, K, spec["segment"], spec["subsegment"], "product_type" if corporate else "product",
                "ead_sar_mn", "limit_sar_mn", "utilisation_pct", "ecl_sar_mn", "dpd_days", "stage",
                "default_flag", "ews_score", "ews_band", "ews_reasons"]
    exp_cols = [c for c in exp_cols if not exposures or c in exposures[0]]
    exp_kinds = {"ead_sar_mn": "sar_mn", "limit_sar_mn": "sar_mn", "ecl_sar_mn": "sar_mn", "utilisation_pct": "pct",
                 "dpd_days": "days", "stage": "int", "default_flag": "int", "ews_score": "int", "ews_band": "rating"}
    exp_sheet = stream.Sheet("Exposures", meta, [Col(c, c.replace("_", " "), exp_kinds.get(c, "")) for c in exp_cols],
                             ([e.get(c) for c in exp_cols] for e in exposures), title=f"Early Warning · Exposures · {scope_label}")
    n_exp = len(exposures)

    rules = ews.RULES[domain_id]
    rule_rows = []
    for e in exposures:
        names = {x.strip() for x in (e.get("ews_reasons") or "").split(";") if x.strip()}
        for rule in rules:
            if rule["label"] in names:
                cols = sorted(ews._columns(rule["sql"]))
                rule_rows.append([e[O], e[K], rule["id"], rule["label"], rule["sql"],
                                  "; ".join(f"{c}={e.get(c)}" for c in cols), rule["weight"], e.get("ews_score")])
    rules_sheet = stream.Sheet("Rules fired", meta, [Col("o", f"{owner_label} ID"), Col("e", "Exposure ID"), Col("r", "Rule"),
                                                     Col("n", "Rule name"), Col("c", "Condition"), Col("v", "Value read"),
                                                     Col("w", "Weight", "int"), Col("s", "Exposure score", "int")],
                               rule_rows, title=f"Early Warning · Rules fired · {scope_label}")
    n_rules = len(rule_rows)

    filters = {"cohort": cohort, "reason": reason, "layer": layer, "dpd": dpd, "stage": stage or "",
               "band_min": band_min, "search": search, "customer": customer_id}
    about = [
        ("Book", domain_id), ("Period", chosen), ("Release", spec["release_id"]),
        ("Rule set", ews.RULESET_VERSION),
        ("Band floors", ", ".join(f"{k} {v}+" for k, v in floors.items())),
        ("Scope", scope_label),
        *[(f"Filter: {k}", v) for k, v in filters.items() if v],
        ("Rows: customers", n_cust), ("Rows: exposures", n_exp), ("Rows: rules fired", n_rules),
        ("Rating order", " > ".join(ratings.RATING_ORDER)),
    ]
    body = stream.write([owners_sheet, exp_sheet, rules_sheet, stream.about(meta, about)], meta)
    bits = [f"ews_{domain_id}_{chosen}"]
    for part in (segment, scope.classification, subsegment):
        if part:
            bits.append(_slug(part))
    if customer_id:
        bits.append(customer_id)
    else:
        bits.append(cohort or "all")
        bits += [_slug(f"{k}-{v}") for k, v in filters.items() if v and k not in ("cohort", "customer")]
    return body, "_".join(bits) + ".xlsx"


def _facts(domain_id: str, period: str) -> dict[str, dict[str, Any]]:
    spec = rd.domain_spec(domain_id)
    rows = rd.q(f'SELECT * FROM {rd.owner(domain_id)} WHERE "{spec["period"]}" = ?', [period])
    return {r[spec["owner_key"]]: r for r in rows}


__all__ = ["workbook"]
