"""R16 m (M2): the segment analysis behind an Early Warning card.

A card on the Early Warning screen (a sector, a product, a sub-sector, a
Salaried / Non-Salaried split or a level-drill value such as a region) opens
the analysis of its population as the default action. Every number here is an
aggregate of the Early Warning release the reader already serves
(`reader.exposure` / `reader.enriched`, the package's own `ews_score`,
`ews_band`, `ews_reasons`, `ead_sar_mn`, `ecl_sar_mn`, `stage`, `dpd_days`),
counted with the drill's rules (`drill.py`: a customer's score is its worst
exposure's score; warned = moderate floor or above). Deterministic, no model
call, the same answer every run.

Sections:
  plain_words   3-4 lines, at most 60 words, written from the figures below;
  headline      warned owners, their EAD, high/critical share, movement on the prior period;
  drivers       the warning indicator families behind the warned exposures, with the change on the prior period;
  rules         every EWS rule fired on the warned exposures (id, name, weight, counts);
  top_names     the largest warned owners by EAD in the scope, with band, stage, DPD and main reasons;
  ecl           stage mix and ECL now, and ECL if the warnings come true -- the P3 ECL impact engine
                (`backend/risk_intel/ecl_impact.py`, the engine behind the EclImpactPanel), not a new formula;
  actions       rule-based next steps, each with its owner role and the rule that raised it;
  stress        the body of the existing What-If export ("Stress this cohort").
"""
from __future__ import annotations

from typing import Any

from backend.ews_domain import drill
from backend.ews_domain import ews_catalogue as cat
from backend.ews_domain import ews_rules as ews
from backend.ews_domain import reader as rd

TOP_NAMES = 10
#: Action thresholds (one place; every action prints the rule that raised it).
SEVERE_SHARE_TIGHTEN_PCT = 10.0     # high/critical exposure at or above 10% of the scope's EAD
UPLIFT_SICR_PCT = 10.0              # ECL if the warnings come true at least 10% above the current ECL


def _pct(a: float, b: float) -> float:
    return 100.0 * a / b if b else 0.0


def _relations(scope: drill.Scope) -> list[str]:
    spec = scope.spec
    rel = [f"{spec['exposure'].removesuffix('.parquet')} ({spec['release_id']})"]
    if scope.enriched:
        rel.append(f"{spec['owner'].removesuffix('.parquet')} + branch ({spec['release_id']})")
    return rel


# ---------------------------------------------------------------- drivers and rules

def _rule_meta(domain_id: str) -> dict[str, dict[str, Any]]:
    out = {}
    for r in ews.RULES[domain_id]:
        m = cat.signal_dict(domain_id, r["id"])
        out[r["label"]] = {"id": r["id"], "label": r["label"], "weight": int(r["weight"]),
                           "family": m.get("family") or "other", "family_label": m.get("family_label") or "Other",
                           "layer": m.get("layer", ""), "layer_label": m.get("layer_label", ""),
                           "source": m.get("source", ""), "source_label": m.get("source_label", "")}
    return out


def _fired(scope: drill.Scope, periods: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Per (period, rule) and per (period, family): the WARNED exposures of the scope that carry it.

    A family is counted once per exposure even when two of its rules fired on it, so a family's exposures and
    EAD never exceed the warned exposures and EAD."""
    spec = scope.spec
    P, O, K = spec["period"], spec["owner_key"], spec["key"]
    where, params = scope.where()
    mod = drill.warned_min(scope.domain_id)
    meta = _rule_meta(scope.domain_id)
    values = ", ".join("(?, ?)" for _ in meta) or "('', 'other')"
    vparams = [x for label, m in meta.items() for x in (label, m["family"])]
    marks = ", ".join("?" for _ in periods)
    base = f"""
        m(reason, fam) AS (VALUES {values}),
        x AS (SELECT "{P}" AS period, "{O}" AS owner, "{K}" AS exp_id, ead_sar_mn AS ead,
                     trim(unnest(string_split(ews_reasons, '; '))) AS reason
              FROM {scope.rel}
              WHERE "{P}" IN ({marks}) AND ews_score >= {mod} AND ews_reasons <> '' AND ({where}))"""
    p = [*vparams, *periods, *params]
    rules = rd.q(f"""WITH {base}
        SELECT period, reason, COUNT(DISTINCT owner) AS owners, COUNT(*) AS exposures, SUM(ead) AS ead
        FROM x WHERE reason <> '' GROUP BY ALL""", p)
    fams = rd.q(f"""WITH {base},
        y AS (SELECT DISTINCT x.period, x.owner, x.exp_id, x.ead, COALESCE(m.fam, 'other') AS fam
              FROM x LEFT JOIN m USING (reason) WHERE x.reason <> '')
        SELECT period, fam, COUNT(DISTINCT owner) AS owners, COUNT(*) AS exposures, SUM(ead) AS ead
        FROM y GROUP BY ALL""", p)
    return rules, fams


def drivers_and_rules(scope: drill.Scope, period: str, prior: str, warned: dict[str, Any],
                      ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    meta = _rule_meta(scope.domain_id)
    rules_raw, fams_raw = _fired(scope, [period, prior] if prior else [period])
    w_owners, w_ead = warned["owners"], warned["ead"]

    rules: dict[str, dict[str, Any]] = {}
    for r in rules_raw:
        m = meta.get(r["reason"], {"id": "", "label": r["reason"], "weight": None, "family": "other",
                                   "family_label": "Other", "layer": "", "layer_label": "", "source": "",
                                   "source_label": ""})
        item = rules.setdefault(r["reason"], {**m, "owners": 0, "exposures": 0, "ead": 0.0,
                                              "prior_owners": 0 if prior else None, "prior_ead": 0.0 if prior else None})
        if r["period"] == period:
            item.update(owners=int(r["owners"]), exposures=int(r["exposures"]), ead=float(r["ead"] or 0))
        else:
            item.update(prior_owners=int(r["owners"]), prior_ead=float(r["ead"] or 0))
    rules_out = []
    for item in rules.values():
        if not item["owners"]:
            continue
        item["change"] = item["owners"] - item["prior_owners"] if prior else None
        item["share_of_warned_owners_pct"] = _pct(item["owners"], w_owners)
        item["share_of_warned_ead_pct"] = _pct(item["ead"], w_ead)
        rules_out.append(item)
    rules_out.sort(key=lambda i: (-i["owners"], -i["ead"], i["label"]))

    fam_labels = {m["family"]: m for m in meta.values()}
    fams: dict[str, dict[str, Any]] = {}
    for r in fams_raw:
        key = str(r["fam"])
        m = fam_labels.get(key, {"family_label": "Other", "layer": "", "layer_label": ""})
        item = fams.setdefault(key, {"key": key, "label": m["family_label"], "layer": m.get("layer", ""),
                                     "layer_label": m.get("layer_label", ""), "owners": 0, "exposures": 0,
                                     "ead": 0.0, "prior_owners": 0 if prior else None,
                                     "prior_ead": 0.0 if prior else None})
        if r["period"] == period:
            item.update(owners=int(r["owners"]), exposures=int(r["exposures"]), ead=float(r["ead"] or 0))
        else:
            item.update(prior_owners=int(r["owners"]), prior_ead=float(r["ead"] or 0))
    drivers = []
    for item in fams.values():
        if not item["owners"]:
            continue
        item["change"] = item["owners"] - item["prior_owners"] if prior else None
        item["ead_change"] = item["ead"] - item["prior_ead"] if prior else None
        item["share_of_warned_owners_pct"] = _pct(item["owners"], w_owners)
        item["share_of_warned_ead_pct"] = _pct(item["ead"], w_ead)
        item["rules"] = [r["id"] for r in rules_out if r["family"] == item["key"]]
        drivers.append(item)
    drivers.sort(key=lambda i: (-i["owners"], -i["ead"], i["label"]))
    return drivers, rules_out


def warned_totals(scope: drill.Scope, period: str) -> dict[str, Any]:
    """The warned EXPOSURES of the scope (score at the moderate floor or above): owners, exposures, EAD."""
    spec = scope.spec
    where, params = scope.where()
    r = rd.q(f"""SELECT COUNT(DISTINCT "{spec['owner_key']}") AS owners, COUNT(*) AS exposures,
                        SUM(ead_sar_mn) AS ead, SUM(ecl_sar_mn) AS ecl
                 FROM {scope.rel} WHERE "{spec['period']}" = ? AND ews_score >= {drill.warned_min(scope.domain_id)}
                   AND ({where})""", [period, *params])[0]
    return {"owners": int(r["owners"] or 0), "exposures": int(r["exposures"] or 0),
            "ead": float(r["ead"] or 0), "ecl": float(r["ecl"] or 0)}


# ---------------------------------------------------------------- top names

def top_names(scope: drill.Scope, period: str, limit: int = TOP_NAMES) -> list[dict[str, Any]]:
    domain_id = scope.domain_id
    base, params = drill._owner_rows_sql(scope, period)
    filt, fparams = drill.list_filter(domain_id, "warned")
    rows = rd.q(f"SELECT * FROM ({base}) WHERE {filt} ORDER BY exposure DESC, owner LIMIT ?",
                [*params, *fparams, int(limit)])
    weights = {r["label"]: int(r["weight"]) for r in ews.RULES[domain_id]}
    out = []
    for i, r in enumerate(rows, 1):
        fired = sorted({x.strip() for x in (r["reasons_raw"] or "").split(";") if x.strip()},
                       key=lambda x: (-weights.get(x, 0), x))
        out.append({"rank": i, "customer_id": r["owner"], "customer_name": r["owner_name"],
                    "score": int(r["score"] or 0), "band": drill.band_of(r["score"], domain_id),
                    "stage": int(r["stage"] or 0), "dpd": int(r["dpd"] or 0),
                    "exposure": float(r["exposure"] or 0), "ecl": float(r["ecl"] or 0),
                    "facilities": int(r["facilities"] or 0), "current_bad": bool(r["bad"]),
                    "main_reasons": fired[:3], "reasons_count": len(fired),
                    "links": drill.links(domain_id, r["owner"], period)})
    return out


# ---------------------------------------------------------------- ECL and stage

def _stage_mix(scope: drill.Scope, period: str, warned_only: bool) -> list[dict[str, Any]]:
    spec = scope.spec
    O, P = spec["owner_key"], spec["period"]
    where, params = scope.where()
    extra = ""
    if warned_only:
        extra = (f' AND "{O}" IN (SELECT "{O}" FROM {scope.rel} WHERE "{P}" = ? AND ({where}) '
                 f'GROUP BY 1 HAVING MAX(ews_score) >= {drill.warned_min(scope.domain_id)})')
    rows = rd.q(f"""SELECT stage, COUNT(*) AS n, SUM(ead_sar_mn) AS ead, SUM(ecl_sar_mn) AS ecl
                    FROM {scope.rel} WHERE "{P}" = ? AND ({where}){extra} GROUP BY 1 ORDER BY 1""",
                [period, *params, *([period, *params] if warned_only else [])])
    return [{"stage": int(r["stage"]), "n": int(r["n"]), "ead": float(r["ead"] or 0), "ecl": float(r["ecl"] or 0)}
            for r in rows]


def _scoped_impact(scope: drill.Scope, period: str) -> dict[str, Any]:
    """The P3 ECL impact engine on a scope finer than a sector / product.

    `ecl_impact.impact()` takes a segment only. For a sub-sector, a Salaried / Non-Salaried split or a level-drill
    value, the same engine is applied to the scope's exposures: the name's bucket comes from the engine's own frame
    (`ecl_impact._frame`, worst band over the whole book), the per-exposure ECL if defaulted is the engine's
    max(current ECL, EAD x LGD), the performing filter is the engine's, and the sums are the engine's `_agg` with the
    Admin PD by bucket. On a segment-only scope this path equals `impact()` exactly (tests/v5/ews)."""
    import pandas as pd

    from backend.risk_intel import ecl_impact as ei
    from backend.risk_intel import store

    spec = scope.spec
    P, O, K = spec["period"], spec["owner_key"], spec["key"]
    where, params = scope.where()
    cfg = store.pd_by_bucket()
    pds = {k: float(cfg["values"][k]) / 100.0 for k in ei.BUCKETS}
    book, _ = ei._frame(scope.domain_id, period)
    bucket_of = book.groupby("owner")["bucket"].first() if not book.empty else pd.Series(dtype=str)
    rows = rd.q(f"""SELECT "{K}" AS exp_id, "{O}" AS owner, ead_sar_mn AS ead, ecl_sar_mn AS ecl, lgd_pct,
                           stage, dpd_days FROM {scope.rel} WHERE "{P}" = ? AND ({where})""", [period, *params])
    f = pd.DataFrame(rows, columns=["exp_id", "owner", "ead", "ecl", "lgd_pct", "stage", "dpd_days"])
    f = f[(f["stage"] < 3) & (f["dpd_days"] < 90)].copy()
    f["lgd"] = f["lgd_pct"].astype(float) / 100.0
    f["ecl_def"] = (f["ead"] * f["lgd"]).where(lambda s: s > f["ecl"], f["ecl"])
    f["bucket"] = f["owner"].map(bucket_of).fillna("none")
    flagged = f[f["bucket"].isin(ei.BUCKETS)]
    total = ei._agg(flagged, pds)
    by_bucket = [{"bucket": b, "label": store.BUCKET_LABELS[b], "pd_pct": cfg["values"][b],
                  **ei._agg(flagged[flagged["bucket"] == b], pds)} for b in ei.BUCKETS]
    return {"period": period, "pd_by_bucket": cfg, "total": total, "by_bucket": by_bucket}


def ecl_effect(scope: drill.Scope, period: str, force_scoped: bool = False) -> dict[str, Any]:
    from backend.risk_intel import ecl_impact as ei

    segment_only = not (scope.classification or scope.subsegment or scope.dims)
    if segment_only and not force_scoped:
        d = ei.impact(scope.domain_id, period, scope.segment)
        engine = {"period": d["period"], "pd_by_bucket": d["pd_by_bucket"], "total": d["total"],
                  "by_bucket": d["by_bucket"]}
        call = f"ecl_impact.impact(domain={scope.domain_id!r}, segment={scope.segment!r})"
    else:
        engine = _scoped_impact(scope, period)
        call = "ecl_impact._agg on the scope's exposures (engine frame, buckets and PDs)"
    t = engine["total"]
    stage_scope = _stage_mix(scope, period, warned_only=False)
    stage_warned = _stage_mix(scope, period, warned_only=True)
    ecl_now = sum(s["ecl"] for s in stage_scope)
    ead_now = sum(s["ead"] for s in stage_scope)
    return {
        "stage_mix": stage_scope, "stage_mix_warned": stage_warned,
        "ecl_now": ecl_now, "ead_now": ead_now, "coverage_pct": _pct(ecl_now, ead_now),
        "flagged_names": t["names"], "flagged_ead": t["ead"],
        "current_ecl": t["current_ecl"], "ecl_if_defaulted": t["ecl_if_defaulted"],
        "expected_ecl": t["expected_ecl"], "uplift": t["uplift"],
        "uplift_pct": _pct(t["uplift"], t["current_ecl"]),
        "severe_ecl": t["severe_ecl"], "severe_uplift": t["severe_uplift"],
        "ecl_if_true_total": ecl_now + t["uplift"],
        "by_bucket": [{k: b[k] for k in ("bucket", "label", "pd_pct", "names", "ead", "current_ecl",
                                         "expected_ecl", "uplift")} for b in engine["by_bucket"]],
        "pd_version": engine["pd_by_bucket"].get("version"),
        "engine": "backend/risk_intel/ecl_impact.py (P3-ECL-01, the ECL impact panel's engine)",
        "engine_call": call,
        "method": ("ECL if the warnings come true = the P3 ECL impact engine: for the performing exposures of the "
                   "flagged names (Critical to Low), p x ECL if defaulted (max of current ECL and EAD x LGD) + "
                   "(1 - p) x current ECL, p the bucket's PD (management estimate, Admin). Stage 3 and 90+ DPD "
                   "exposures already carry lifetime ECL and are left out of the uplift."),
    }


# ---------------------------------------------------------------- actions

def actions(domain_id: str, name: str, labels: dict[str, str], head: dict[str, Any], move: dict[str, Any],
            drivers: list[dict[str, Any]], names: list[dict[str, Any]], ecl: dict[str, Any],
            warned: dict[str, Any]) -> list[dict[str, Any]]:
    owners = labels["owners"]
    out: list[dict[str, Any]] = []
    if names:
        ead = sum(n["exposure"] for n in names)
        out.append({"key": "review_top", "title": f"Review the top {len(names)} warned {owners}",
                    "why": (f"They hold {drill.money(ead)} of exposure in {name}; the largest is "
                            f"{names[0]['customer_name'] or names[0]['customer_id']} ({drill.money(names[0]['exposure'])})."),
                    "owner_role": "Relationship manager with the credit reviewer",
                    "rule": "Any warned name in scope: review the largest by EAD first."})
    perf_hc = [n for n in names if n["band"] in ("critical", "high") and not n["current_bad"]]
    if head.get("high_or_critical"):
        target = "the Bank Watchlist" if domain_id == "corporate" else "the early-collections contact list"
        out.append({"key": "monitor", "title": f"Propose the high or critical performing {owners} for monitoring",
                    "why": (f"{head['high_or_critical']:,} {owners} are high or critical"
                            + (f", {len(perf_hc)} of them among the top names and still performing" if perf_hc else "")
                            + f"; propose them for {target}."),
                    "owner_role": "Early Warning analyst (credit risk)" if domain_id == "corporate" else "Collections strategy lead",
                    "rule": "At least one high or critical name in scope."})
    rising = (move.get("customers_warned") or 0) > 0
    severe_share = head.get("exposure_severe_pct") or 0.0
    if rising or severe_share >= SEVERE_SHARE_TIGHTEN_PCT:
        what = ("Tighten limits and new-lending appetite for " if domain_id == "corporate"
                else "Tighten acceptance criteria and limit increases for ")
        bits = []
        if severe_share >= SEVERE_SHARE_TIGHTEN_PCT:
            bits.append(f"{severe_share:.1f}% of its exposure is high or critical")
        if rising:
            bits.append(f"warned {owners} rose by {move['customers_warned']:,} on last {labels['period']}")
        out.append({"key": "tighten", "title": what + name,
                    "why": "; ".join(bits).capitalize() + ".",
                    "owner_role": "Portfolio manager, approved by the CRO",
                    "rule": (f"High/critical share of exposure at or above {SEVERE_SHARE_TIGHTEN_PCT:.0f}%, "
                             "or more warned names than last period.")})
    if drivers and drivers[0]["key"] in ("delinquency", "payment_behaviour"):
        d = drivers[0]
        out.append({"key": "collections", "title": "Contact the names in arrears early",
                    "why": f"The leading driver is {d['label'].lower()} ({d['owners']:,} {owners}, {drill.money(d['ead'])}).",
                    "owner_role": "Collections / remedial management",
                    "rule": "The leading driver is delinquency or payment behaviour."})
    if ecl.get("uplift_pct", 0) >= UPLIFT_SICR_PCT and ecl.get("uplift", 0) > 0:
        out.append({"key": "sicr", "title": "Request a SICR assessment and ECL overlay review",
                    "why": (f"If the warnings come true, ECL on the flagged names rises by {drill.money(ecl['uplift'])} "
                            f"({ecl['uplift_pct']:.0f}% on {drill.money(ecl['current_ecl'])})."),
                    "owner_role": "IFRS 9 / impairment team",
                    "rule": f"ECL uplift at or above {UPLIFT_SICR_PCT:.0f}% of the flagged names' current ECL."})
    if warned["exposures"]:
        out.append({"key": "stress", "title": "Stress this cohort in What-If",
                    "why": (f"Freeze the {warned['owners']:,} warned {owners} and run a scenario on exactly "
                            "their exposures."),
                    "owner_role": "Risk analytics (stress testing)",
                    "rule": "Any warned population: optional."})
    return out


# ---------------------------------------------------------------- words

def plain_words(name: str, labels: dict[str, str], head: dict[str, Any], move: dict[str, Any],
                drivers: list[dict[str, Any]], ecl: dict[str, Any]) -> list[str]:
    owners, period = labels["owners"], labels["period"]
    d = move.get("customers_warned")
    moved = ("" if d is None else ", unchanged on last " + period if d == 0
             else f", {abs(d):,} {'more' if d > 0 else 'fewer'} than last {period}")
    lines = [f"{name}: {head.get('customers_warned', 0):,} of {head.get('customers', 0):,} {owners} are warned{moved}.",
             f"{drill.money(head.get('exposure_severe', 0))} of exposure is high or critical "
             f"({head.get('exposure_severe_pct', 0):.1f}%)."]
    if drivers:
        lines.append(f"Main driver: {drivers[0]['label'].lower()} ({drivers[0]['owners']:,} {owners}).")
    if ecl.get("uplift"):
        lines.append(f"If the warnings come true, ECL rises by {drill.money(ecl['uplift'])}.")
    return lines[:4]


# ---------------------------------------------------------------- the analysis

def analyse(domain_id: str, period: str = "", segment: str = "", classification: str = "", subsegment: str = "",
            dims: dict[str, str] | None = None, limit: int = TOP_NAMES) -> dict[str, Any]:
    scope = drill.Scope(domain_id, segment, classification, subsegment, dims=dims)
    spec, labels = scope.spec, drill._labels(domain_id)
    window, prior_of = drill._periods_window(domain_id, period, 2)
    chosen = window[-1]
    prior = prior_of.get(chosen, "")
    all_periods = rd.periods(domain_id)

    now = drill.kpis(scope, [chosen], None, {chosen: prior}).get((chosen, "__all__"), {})
    before = None
    if prior:
        i = all_periods.index(prior)
        before = drill.kpis(scope, [prior], None, {prior: all_periods[i - 1] if i else ""}).get((prior, "__all__"))
    move = drill._movement(now, before)

    warned = warned_totals(scope, chosen)
    warned_prior = warned_totals(scope, prior) if prior else None
    drivers, rules = drivers_and_rules(scope, chosen, prior, warned)
    names = top_names(scope, chosen, limit)
    ecl = ecl_effect(scope, chosen)

    dim_bits = [drill.dim_value_label(domain_id, k, v) for k, v in scope.dims.items()]
    name = (subsegment or (drill.CLASSIFICATIONS[scope.classification]["label"] if scope.classification else "")
            or segment)
    name = " · ".join([b for b in [segment if (subsegment or scope.classification) else "", name, *dim_bits] if b]) \
        or labels["portfolio"]
    key = (subsegment or scope.classification or segment
           or (list(scope.dims.values())[-1] if scope.dims else "") or "portfolio")

    headline = {
        "customers": now.get("customers", 0), "customers_warned": now.get("customers_warned", 0),
        "warned_pct": now.get("warned_pct", 0.0), "high_or_critical": now.get("high_or_critical", 0),
        "critical": now.get("critical", 0), "high": now.get("high", 0), "moderate": now.get("moderate", 0),
        "current_bad": now.get("current_bad", 0), "forward_risk": now.get("forward_risk", 0),
        "exposure": now.get("exposure", 0.0), "ecl": now.get("ecl", 0.0),
        "exposure_warned": now.get("exposure_warned", 0.0), "exposure_warned_pct": now.get("exposure_warned_pct", 0.0),
        "exposure_severe": now.get("exposure_severe", 0.0), "exposure_severe_pct": now.get("exposure_severe_pct", 0.0),
        "odr_pct": now.get("odr_pct"),
        "warned_exposures": warned["exposures"], "warned_ead": warned["ead"],
        "movement": {k: move.get(k) for k in ("customers_warned", "high_or_critical", "exposure_warned",
                                              "exposure_severe", "exposure_severe_pct", "warned_pct", "odr_pct")},
        "previous": ({k: before.get(k) for k in ("customers_warned", "high_or_critical", "exposure_warned",
                                                  "exposure_severe_pct")} if before else None),
        "prior_warned_ead": warned_prior["ead"] if warned_prior else None,
    }
    rel = _relations(scope)
    src = f"{', '.join(rel)} · {spec['period']} {chosen}" + (f" vs {prior}" if prior else "") + \
        f" · rule set {ews.RULESET_VERSION}"
    stress = {"domain": domain_id, "period": chosen, "segment": scope.segment,
              "classification": scope.classification, "subsegment": scope.subsegment, "cohort": "warned"}
    if scope.dims:
        stress["dims"] = dict(scope.dims)
    return {
        "domain_id": domain_id, "release_id": spec["release_id"], "ruleset": ews.RULESET_VERSION,
        "period": chosen, "prior_period": prior, "scope": scope.as_dict(), "labels": labels,
        "name": name, "key": key, "money_unit": "SAR million", "population": "warned",
        "plain_words": plain_words(name, labels, headline, move, drivers, ecl),
        "headline": headline,
        "drivers": drivers, "rules": rules, "top_names": names, "ecl": ecl,
        "actions": actions(domain_id, name, labels, headline, move, drivers, names, ecl, warned),
        "stress": stress,
        "sources": {
            "relations": rel,
            "headline": f"Counted from {src} (drill counting rules).",
            "drivers": f"Warned exposures' ews_reasons from {src}; a family counts an exposure once.",
            "rules": f"Rule ids from backend/ews_domain/ews_rules.py, matched on ews_reasons in {src}.",
            "top_names": f"Warned {labels['owners']} ordered by EAD in scope, from {src}.",
            "ecl": f"Stage and ECL from {src}; ECL if the warnings come true from {ecl['engine']}, PD by bucket "
                   f"v{ecl['pd_version']}.",
        },
        "definitions": drill.definitions(domain_id),
        "model_calls": 0,
    }


def compact(a: dict[str, Any], names: int = 5) -> dict[str, Any]:
    """The short form a What-If cohort thread opens with (R16 m, M2/M4): the same figures, fewer rows."""
    return {k: a[k] for k in ("domain_id", "period", "prior_period", "scope", "labels", "name", "key",
                              "plain_words", "headline", "sources", "stress")} | {
        "drivers": a["drivers"][:4], "rules": a["rules"][:5], "top_names": a["top_names"][:names],
        "ecl": {k: v for k, v in a["ecl"].items() if k not in ("by_bucket",)}, "actions": a["actions"][:4],
    }
