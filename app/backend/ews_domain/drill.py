"""The Early Warning drill: portfolio -> segment -> (classification) ->
sub-segment -> customers -> customer, for both books.

Corporate: sector -> sub-sector -> borrower (quarterly).
Retail:    product -> Salaried / Non-Salaried -> sub-product -> customer
           (monthly).

Everything here is an aggregate of the EWS release's own scored rows
(the live rule set, `ews_score` / `ews_band` / `ews_reasons` as the package
wrote them). Nothing is re-weighted, re-banded or invented; definitions travel
with every response so a screen can state them.

Counting rules (stated once, used everywhere):
  * a CUSTOMER's score in a scope is the worst (max) score of its exposures in
    that scope; its band is that score's band;
  * WARNED = score at or above the book's moderate floor; HIGH OR CRITICAL =
    at or above its high floor (ews_rules.BAND_FLOORS);
  * CURRENT BAD = any exposure 90+ DPD, Stage 3 or in default;
  * FORWARD RISK = warned and not current bad;
  * DEFAULT ENTRIES = customers bad now that were in scope and not bad in the
    prior period, over those eligible (the default-entry rate);
  * amounts are exposure EAD in SAR million; "exposure warned" is the EAD of
    exposures that are themselves warned.
A customer with exposures in two products is counted in each product.
"""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from backend.ews_domain import ews_catalogue as cat
from backend.ews_domain import ews_rules as ews
from backend.ews_domain import reader as rd

TREND_POINTS = 6


def warned_min(domain_id: str) -> int:
    return ews.floor(domain_id, "moderate")


def severe_min(domain_id: str) -> int:
    return ews.floor(domain_id, "high")

CLASSIFICATIONS = {
    "SALARIED": {"label": "Salaried", "types": ("Salaried-Private", "Salaried-Government"),
                 "meaning": "Customers paid a salary by an employer (private or government)."},
    "NON_SALARIED": {"label": "Non-Salaried", "types": ("Self-employed", "Non-salaried"),
                     "meaning": "Self-employed customers and customers without a salary."},
}

DPD_BUCKETS = (  # key, label, low, high (inclusive)
    ("current", "Current", 0, 0), ("1-9", "1-9 DPD", 1, 9), ("10-19", "10-19 DPD", 10, 19),
    ("20-29", "20-29 DPD", 20, 29), ("30-59", "30-59 DPD", 30, 59),
    ("60-89", "60-89 DPD", 60, 89), ("90+", "90+ DPD", 90, 100000),
)

# Conditions name the floors; `cohort_sql` fills them in for a book.
COHORTS = {
    "all": ("All customers in scope", "TRUE"),
    "warned": ("Warned", "score >= {w}"),
    "high_or_critical": ("High or critical", "score >= {s}"),
    "current_bad": ("Current bad", "bad"),
    "forward_risk": ("Forward risk (warned, still performing)", "score >= {w} AND NOT bad"),
}


def cohort_sql(domain_id: str, key: str) -> str:
    return COHORTS[key][1].format(w=warned_min(domain_id), s=severe_min(domain_id))


def definitions(domain_id: str) -> dict[str, str]:
    (crit, _), (high, _), (mod, _), _ = ews.bands(domain_id)
    return {**DEFINITIONS,
            "warned": f"Warned: score of {mod} or more (moderate, high or critical).",
            "high_or_critical": f"High or critical: score of {high} or more.",
            "bands": (f"Score bands: {crit}+ critical, {high}-{crit - 1} high, {mod}-{high - 1} moderate, "
                      + (f"1-{mod - 1} low" if mod > 2 else "1 low")
                      + f", 0 none (rule set {ews.RULESET_VERSION}).")}


DEFINITIONS = {
    "customer_score": "A customer's score is the highest rule-weight score among its exposures in this view.",
    "current_bad": "Current bad: any exposure 90+ days past due, in Stage 3 or in default.",
    "forward_risk": "Forward risk: warned but not yet current bad - the population the warning exists to find.",
    "default_entry_rate": ("Default-entry rate: customers that became current bad this period, over customers "
                           "in the same view last period that were not bad."),
    "exposure_warned": "Exposure warned: EAD of exposures that are themselves warned.",
    "overlap": "A customer with exposures in two products or sectors is counted in each.",
}


# ---------------------------------------------------------------- scope

class Scope:
    """Which slice of the book a request is about, compiled to SQL.

    `dims` is the level drill filter (PLAN_R4 B4): {dimension key: value}, e.g. {"region": "Riyadh",
    "branch": "Riyadh Olaya"}. Dimensions are defined in `DIMS`; a scope with dims reads the enriched
    relation (exposure + branch domain + current rating), one row per exposure row.
    """

    def __init__(self, domain_id: str, segment: str = "", classification: str = "",
                 subsegment: str = "", dims: dict[str, str] | None = None, enriched: bool = False):
        self.domain_id = domain_id
        self.spec = rd.domain_spec(domain_id)
        self.segment = segment or ""
        self.classification = (classification or "").upper()
        self.subsegment = subsegment or ""
        self.dims = {k: str(v) for k, v in (dims or {}).items() if v not in (None, "")}
        self.enriched = enriched or bool(self.dims)
        if self.classification and domain_id != "retail":
            raise rd.ReadRefused("Salaried / Non-Salaried applies to the retail book only.")
        if self.classification and self.classification not in CLASSIFICATIONS:
            raise rd.ReadRefused(f"{classification!r} is not a classification; they are "
                                 f"{sorted(CLASSIFICATIONS)}.")
        if self.segment:
            self._known(self.spec["segment"], self.segment)
        if self.subsegment:
            self._known(self.spec["subsegment"], self.subsegment)
        for k, v in self.dims.items():
            expr = dim_expr(domain_id, k)
            hit = rd.q(f"SELECT 1 AS x FROM {self.rel} WHERE {expr} = ? LIMIT 1", [v])
            if not hit:
                raise rd.ReadRefused(f"{v!r} is not a {DIMS[domain_id][k]['label'].lower()} of this book.")

    @property
    def rel(self) -> str:
        return rd.enriched(self.domain_id) if self.enriched else rd.exposure(self.domain_id)

    def _known(self, column: str, value: str) -> None:
        hit = rd.q(f'SELECT 1 AS x FROM {rd.exposure(self.domain_id)} WHERE "{column}" = ? LIMIT 1',
                   [value])
        if not hit:
            raise rd.ReadRefused(f"{value!r} is not a {column.replace('_', ' ')} of this book.")

    def where(self) -> tuple[str, list[Any]]:
        clauses, params = ["TRUE"], []
        if self.segment:
            clauses.append(f'"{self.spec["segment"]}" = ?')
            params.append(self.segment)
        if self.classification:
            types = CLASSIFICATIONS[self.classification]["types"]
            clauses.append(f"employment_type IN ({', '.join('?' for _ in types)})")
            params.extend(types)
        if self.subsegment:
            clauses.append(f'"{self.spec["subsegment"]}" = ?')
            params.append(self.subsegment)
        for k, v in self.dims.items():
            clauses.append(f"{dim_expr(self.domain_id, k)} = ?")
            params.append(v)
        # PLAN_R5 A1: only the customers the caller's data access policy allows (cards, counts, lists, exports).
        from backend.access import sql_predicate
        pred = sql_predicate(f'"{self.spec["owner_key"]}"', "retail" if self.domain_id == "retail" else "corporate")
        if pred != "TRUE":
            clauses.append(pred)
        return " AND ".join(clauses), params

    @property
    def level(self) -> str:
        if self.subsegment:
            return "subsegment"
        if self.classification:
            return "classification"
        if self.segment:
            return "segment"
        return "portfolio"

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"segment": self.segment, "classification": self.classification,
                               "subsegment": self.subsegment, "level": self.level}
        if self.dims:
            out["dims"] = dict(self.dims)
        return out


# Level dimensions (PLAN_R4 B4). `expr` is SQL over the enriched relation; `owner` marks an attribute of the
# customer (one value per customer and period, so customer counts add up across cards); `order` sorts the cards.
PRODUCT_TYPES = {"asset_finance": "Asset finance", "overdraft": "Overdraft", "project_finance": "Project finance",
                 "revolving_credit": "Revolving credit", "supply_chain_finance": "Supply chain finance",
                 "term_loan": "Term loan", "trade_finance": "Trade finance", "working_capital": "Working capital"}

DIMS: dict[str, dict[str, dict[str, Any]]] = {
    "corporate": {
        "sector": {"label": "Sector", "plural": "Sectors", "expr": '"sector"', "owner": True},
        "region": {"label": "Region", "plural": "Regions", "expr": '"region"', "owner": True},
        "branch": {"label": "Branch", "plural": "Branches", "expr": '"branch_name"', "owner": True},
        "rating": {"label": "Rating grade", "plural": "Rating grades", "expr": '"rating_current"', "owner": True,
                   "order": "rating"},
        "bu": {"label": "Business unit", "plural": "Business units", "expr": '"business_unit"', "owner": True},
        "rm": {"label": "Relationship manager", "plural": "Relationship managers", "expr": '"rm_name"',
               "owner": True},
        "product": {"label": "Product", "plural": "Products", "expr": '"product_type"', "owner": False,
                    "names": PRODUCT_TYPES},
    },
    "retail": {
        "product": {"label": "Product", "plural": "Products", "expr": '"product"', "owner": False},
        "region": {"label": "Region", "plural": "Regions", "expr": '"region"', "owner": True},
        "branch": {"label": "Branch", "plural": "Branches", "expr": '"branch_name"', "owner": True},
        "band": {"label": "Score band", "plural": "Score bands", "expr": '"customer_score_band"', "owner": True,
                 "order": "key", "prefix": "Band "},
        "salaried": {"label": "Salaried / Non-Salaried", "plural": "Salaried and Non-Salaried",
                     "expr": None, "owner": True, "order": "key",
                     "names": {k: v["label"] for k, v in CLASSIFICATIONS.items()}},
        "vintage": {"label": "Vintage", "plural": "Vintages", "expr": 'CAST("vintage_year" AS VARCHAR)',
                    "owner": False, "order": "key"},
    },
}


def dim_expr(domain_id: str, key: str) -> str:
    dims = DIMS.get(domain_id, {})
    if key not in dims:
        raise rd.ReadRefused(f"{key!r} is not a level of the {domain_id} book; they are {sorted(dims)}.")
    return dims[key]["expr"] or classification_expr()


def dim_value_label(domain_id: str, key: str, value: str) -> str:
    d = DIMS[domain_id][key]
    return d.get("names", {}).get(value) or f"{d.get('prefix', '')}{value}"


def classification_expr() -> str:
    whens = " ".join(
        f"WHEN employment_type IN ({', '.join(repr(t) for t in c['types'])}) THEN '{k}'"
        for k, c in CLASSIFICATIONS.items())
    return f"CASE {whens} ELSE 'UNCLASSIFIED' END"


def band_of(score: float | int | None, domain_id: str) -> str:
    return ews.band_of(domain_id, score)


# ---------------------------------------------------------------- KPIs

def _periods_window(domain_id: str, period: str, points: int) -> tuple[list[str], dict[str, str]]:
    chosen, _, all_periods = rd.resolve_period(domain_id, period)
    i = all_periods.index(chosen)
    window = all_periods[max(0, i - points + 1): i + 1]
    prior = {p: (all_periods[all_periods.index(p) - 1] if all_periods.index(p) else "")
             for p in window}
    return window, prior


def kpis(scope: Scope, periods: list[str], group: str | None = None,
         prior: dict[str, str] | None = None) -> dict[tuple[str, str], dict[str, Any]]:
    """KPIs per (period, group value). `group` is a SQL expression or None."""
    spec = scope.spec
    P, K, O = spec["period"], spec["key"], spec["owner_key"]
    where, params = scope.where()
    grp = group or "'__all__'"
    need = sorted(set(periods) | {v for v in (prior or {}).values() if v})
    marks = ", ".join("?" for _ in need)
    base = f"""
        e AS (SELECT "{P}" AS period, {grp} AS grp, "{O}" AS owner, "{K}" AS exp_id,
                     ews_score, ead_sar_mn AS ead, ecl_sar_mn AS ecl, dpd_days,
                     (dpd_days >= 90 OR stage = 3 OR default_flag = 1) AS bad,
                     CASE WHEN ews_reasons = '' THEN 0
                          ELSE len(string_split(ews_reasons, '; ')) END AS triggers
              FROM {scope.rel}
              WHERE "{P}" IN ({marks}) AND ({where})),
        o AS (SELECT period, grp, owner, MAX(ews_score) AS score, BOOL_OR(bad) AS bad, SUM(ead) AS ead
              FROM e GROUP BY ALL)"""
    p_all = [*need, *params]
    (crit, _), (high, _), (mod, _), _ = ews.bands(scope.domain_id)
    owners = rd.q(f"""WITH {base}
        SELECT period, grp, COUNT(*) AS customers,
               SUM(CASE WHEN score >= {mod} THEN 1 ELSE 0 END) AS customers_warned,
               SUM(CASE WHEN score >= {high} THEN 1 ELSE 0 END) AS high_or_critical,
               SUM(CASE WHEN score >= {crit} THEN 1 ELSE 0 END) AS critical,
               SUM(CASE WHEN score >= {high} AND score < {crit} THEN 1 ELSE 0 END) AS high,
               SUM(CASE WHEN score >= {mod} AND score < {high} THEN 1 ELSE 0 END) AS moderate,
               SUM(CASE WHEN score >= 1 AND score < {mod} THEN 1 ELSE 0 END) AS low,
               SUM(CASE WHEN bad THEN 1 ELSE 0 END) AS current_bad,
               SUM(CASE WHEN score >= {mod} AND NOT bad THEN 1 ELSE 0 END) AS forward_risk,
               SUM(CASE WHEN bad THEN ead ELSE 0 END) AS exposure_bad
        FROM o GROUP BY ALL""", p_all)
    expos = rd.q(f"""WITH {base}
        SELECT period, grp, COUNT(*) AS facilities, SUM(ead) AS exposure, SUM(ecl) AS ecl,
               SUM(CASE WHEN ews_score >= {mod} THEN ead ELSE 0 END) AS exposure_warned,
               SUM(CASE WHEN ews_score >= {high} THEN ead ELSE 0 END) AS exposure_severe,
               SUM(CASE WHEN dpd_days >= 30 THEN ead ELSE 0 END) AS exposure_dpd30,
               SUM(triggers) AS triggers_fired
        FROM e GROUP BY ALL""", p_all)
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for r in owners:
        out[(r["period"], str(r["grp"]))] = {k: int(r[k] or 0) for k in r if k not in ("period", "grp", "exposure_bad")}
        # PLAN_R10 E1: all EAD of the owners that are already bad (owner basis, like the "Already bad" count).
        out[(r["period"], str(r["grp"]))]["exposure_bad"] = float(r["exposure_bad"] or 0)
    for r in expos:
        row = out.setdefault((r["period"], str(r["grp"])), {})
        row.update({"facilities": int(r["facilities"] or 0),
                    "exposure": float(r["exposure"] or 0), "ecl": float(r["ecl"] or 0),
                    "exposure_warned": float(r["exposure_warned"] or 0),
                    "exposure_severe": float(r["exposure_severe"] or 0),
                    "exposure_dpd30": float(r["exposure_dpd30"] or 0),
                    "triggers_fired": int(r["triggers_fired"] or 0)})
    if prior:
        pairs = [(p, q) for p, q in prior.items() if q]
        if pairs:
            values = ", ".join("(?, ?)" for _ in pairs)
            flat = [x for pair in pairs for x in pair]
            odr = rd.q(f"""WITH {base}, pm(period, prior) AS (VALUES {values})
                SELECT o.period, o.grp, COUNT(*) AS eligible,
                       SUM(CASE WHEN o.bad THEN 1 ELSE 0 END) AS entries
                FROM o JOIN pm ON pm.period = o.period
                JOIN o AS op ON op.owner = o.owner AND op.grp = o.grp AND op.period = pm.prior
                WHERE NOT op.bad GROUP BY ALL""", [*p_all, *flat])
            for r in odr:
                row = out.setdefault((r["period"], str(r["grp"])), {})
                row["default_eligible"] = int(r["eligible"] or 0)
                row["default_entries"] = int(r["entries"] or 0)
    for row in out.values():
        _derive(row)
    return out


def _derive(row: dict[str, Any]) -> None:
    exposure = row.get("exposure") or 0.0
    row.setdefault("default_eligible", 0)
    row.setdefault("default_entries", 0)
    row["exposure_warned_pct"] = 100 * row.get("exposure_warned", 0) / exposure if exposure else 0.0
    row["exposure_severe_pct"] = 100 * row.get("exposure_severe", 0) / exposure if exposure else 0.0
    # PLAN_R10 E1: the "already bad" tile shows its share of exposure (all EAD of the already-bad owners).
    row["exposure_bad_pct"] = 100 * row.get("exposure_bad", 0) / exposure if exposure else 0.0
    row["dpd_30_plus_pct"] = 100 * row.get("exposure_dpd30", 0) / exposure if exposure else 0.0
    row["odr_pct"] = (100 * row["default_entries"] / row["default_eligible"]
                      if row["default_eligible"] else None)
    customers = row.get("customers") or 0
    row["warned_pct"] = 100 * row.get("customers_warned", 0) / customers if customers else 0.0
    row["severity"] = {b: row.get(b, 0) for b in ("critical", "high", "moderate", "low")}


MOVEMENT_KEYS = ("customers", "customers_warned", "high_or_critical", "current_bad", "forward_risk",
                 "exposure", "exposure_warned", "exposure_severe", "exposure_warned_pct",
                 "exposure_severe_pct", "odr_pct", "warned_pct")


def _movement(now: dict[str, Any], before: dict[str, Any] | None) -> dict[str, Any]:
    if not before:
        return {k: None for k in MOVEMENT_KEYS}
    out = {}
    for k in MOVEMENT_KEYS:
        a, b = now.get(k), before.get(k)
        out[k] = None if a is None or b is None else a - b
    return out


TREND_KEYS = ("customers_warned", "high_or_critical", "current_bad", "forward_risk",
              "exposure_severe", "exposure_warned_pct", "odr_pct", "warned_pct")


def _trend(table, window: list[str], grp: str) -> list[dict[str, Any]]:
    return [{"period": p, **{k: (table.get((p, grp)) or {}).get(k) for k in TREND_KEYS}}
            for p in window]


# ---------------------------------------------------------------- reasons

def reasons(scope: Scope, period: str, prior: str, limit: int = 5,
            group: str | None = None) -> dict[str, list[dict[str, Any]]]:
    """Top warning reasons per group value, with the change on the prior period."""
    spec = scope.spec
    P, O, K = spec["period"], spec["owner_key"], spec["key"]
    where, params = scope.where()
    grp = group or "'__all__'"
    rows = rd.q(f"""
        WITH x AS (SELECT "{P}" AS period, {grp} AS grp, "{O}" AS owner, "{K}" AS exp_id, ead_sar_mn,
                          trim(unnest(string_split(ews_reasons, '; '))) AS reason
                   FROM {scope.rel}
                   WHERE "{P}" IN (?, ?) AND ews_reasons <> '' AND ({where}))
        SELECT grp, reason,
               COUNT(DISTINCT CASE WHEN period = ? THEN owner END) AS customers,
               COUNT(CASE WHEN period = ? THEN 1 END) AS facilities,
               SUM(CASE WHEN period = ? THEN ead_sar_mn ELSE 0 END) AS exposure,
               COUNT(DISTINCT CASE WHEN period = ? THEN owner END) AS previous_customers
        FROM x WHERE reason <> '' GROUP BY ALL""",
                [period, prior or period, *params, period, period, period, prior or "__none__"])
    by_label = {r["label"]: r for r in ews.RULES[scope.domain_id]}
    out: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        rule = by_label.get(r["reason"], {})
        meta = cat.signal_dict(scope.domain_id, rule.get("id", "")) if rule else {}
        item = {"key": rule.get("id", r["reason"]), "reason": r["reason"], "name": r["reason"],
                "weight": rule.get("weight"), "family": meta.get("family", ""),
                "family_label": meta.get("family_label", ""), "layer": meta.get("layer", ""),
                "layer_name": cat.layer_label(meta.get("layer", "")),
                "customers": int(r["customers"] or 0), "facilities": int(r["facilities"] or 0),
                "exposure": float(r["exposure"] or 0),
                "previous_customers": int(r["previous_customers"] or 0) if prior else None}
        item["change"] = (item["customers"] - item["previous_customers"]) if prior else None
        out.setdefault(str(r["grp"]), []).append(item)
    for k in out:
        out[k] = sorted([i for i in out[k] if i["customers"]],
                        key=lambda i: (-i["customers"], -i["exposure"]))[:limit]
    return out


# ---------------------------------------------------------------- words

def money(v: float | None) -> str:
    """SAR million in; the screens' compact form out: SAR 14.9bn, SAR 523m, SAR 845k."""
    if v is None:
        return "-"
    if v == 0:
        return "SAR 0"
    a = abs(v)
    scaled, suffix = ((v / 1000, "bn") if a >= 1000 else (v, "m") if a >= 1
                      else (v * 1000, "k") if a >= 0.001 else (v * 1e6, ""))
    s = abs(scaled)
    decimals = 0 if s >= 100 else 1 if s >= 10 else 2
    return f"SAR {scaled:,.{decimals}f}{suffix}"


def commentary(name: str, row: dict[str, Any], move: dict[str, Any], top: list[dict[str, Any]],
               period_noun: str, owner_noun: str) -> str:
    if not row.get("customers"):
        return f"{name} has no {owner_noun}s in this {period_noun}."
    parts = [f"{name}: {row['customers_warned']:,} of {row['customers']:,} {owner_noun}s are warned "
             f"({row['warned_pct']:.1f}%)"]
    d = move.get("customers_warned")
    if d is not None:
        parts[-1] += (f", {abs(d):,} {'more' if d > 0 else 'fewer'} than last {period_noun}"
                      if d else ", unchanged on last " + period_noun)
    parts.append(f"{money(row['exposure_severe'])} of exposure is high or critical "
                 f"({row['exposure_severe_pct']:.1f}% of {money(row['exposure'])})")
    if row.get("odr_pct") is not None:
        parts.append(f"default-entry rate {row['odr_pct']:.2f}% ({row['default_entries']:,} of "
                     f"{row['default_eligible']:,})")
    if top:
        parts.append(f"leading reason: {top[0]['name']} ({top[0]['customers']:,} {owner_noun}s)")
    return "; ".join(parts) + "."


# ---------------------------------------------------------------- levels

def _labels(domain_id: str) -> dict[str, str]:
    if domain_id == "corporate":
        return {"segment": "Sector", "segments": "Sectors", "subsegment": "Sub-sector",
                "subsegments": "Sub-sectors", "owner": "borrower", "owners": "borrowers",
                "exposure": "facility", "exposures": "facilities", "period": "quarter",
                "portfolio": "Total corporate"}
    return {"segment": "Product", "segments": "Products", "subsegment": "Sub-product",
            "subsegments": "Sub-products", "owner": "customer", "owners": "customers",
            "exposure": "account", "exposures": "accounts", "period": "month",
            "portfolio": "Total retail", "classification": "Classification"}


def _card(name: str, key: str, now: dict, before: dict | None, trend: list, top: list,
          parent: dict | None, labels: dict) -> dict[str, Any]:
    move = _movement(now, before)
    card = {"key": key, "label": name, **now, "movement": move, "trend": trend, "top_reasons": top,
            "commentary": commentary(name, now, move, top, labels["period"], labels["owner"])}
    if parent:
        card["materiality"] = {
            "customers_pct": 100 * now.get("customers", 0) / parent["customers"] if parent.get("customers") else 0,
            "facilities_pct": 100 * now.get("facilities", 0) / parent["facilities"] if parent.get("facilities") else 0,
            "exposure_pct": 100 * now.get("exposure", 0) / parent["exposure"] if parent.get("exposure") else 0}
    return card


SOURCE_LABELS = {"bank_internal": "Bank internal", "bureau": "Bureau", "open_banking": "Open Banking"}


def rule_source(domain_id: str, rule_id: str) -> str:
    meta = cat.signal(domain_id, rule_id)
    return meta.source if meta else "bank_internal"


def by_source(scope: Scope, period: str, group: str | None = None) -> dict[str, list[dict[str, Any]]]:
    """Per group: of the warned customers, how many carry a fired rule from each source."""
    spec = scope.spec
    P, O = spec["period"], spec["owner_key"]
    where, params = scope.where()
    grp = group or "'__all__'"
    mod = warned_min(scope.domain_id)
    flags, fparams = [], []
    for src in SOURCE_LABELS:
        labels = [r["label"] for r in ews.RULES[scope.domain_id] if rule_source(scope.domain_id, r["id"]) == src]
        if labels:
            flags.append("(" + " OR ".join("contains(ews_reasons, ?)" for _ in labels) + f") AS f_{src}")
            fparams.extend(labels)
        else:
            flags.append(f"FALSE AS f_{src}")
    rows = rd.q(f"""
        WITH e AS (SELECT {grp} AS grp, "{O}" AS owner, ews_score, {', '.join(flags)}
                   FROM {scope.rel} WHERE "{P}" = ? AND ({where})),
             o AS (SELECT grp, owner, MAX(ews_score) AS score,
                          {', '.join(f'BOOL_OR(f_{s}) AS f_{s}' for s in SOURCE_LABELS)}
                   FROM e GROUP BY ALL)
        SELECT grp, COUNT(*) FILTER (WHERE score >= {mod}) AS warned,
               {', '.join(f'COUNT(*) FILTER (WHERE score >= {mod} AND f_{s}) AS n_{s}' for s in SOURCE_LABELS)}
        FROM o GROUP BY 1""", [*fparams, period, *params])
    out = {}
    for r in rows:
        w = int(r["warned"] or 0)
        out[str(r["grp"])] = [{"key": s, "label": lbl, "customers": int(r[f"n_{s}"] or 0),
                               "share_pct": 100.0 * int(r[f"n_{s}"] or 0) / w if w else 0.0}
                              for s, lbl in SOURCE_LABELS.items()]
    return out


def rating_mix(scope: Scope, period: str) -> list[dict[str, Any]]:
    """Corporate: borrowers in the view by their current rating, in the global rating order."""
    if scope.domain_id != "corporate":
        return []
    from backend.v5common import ratings
    spec = scope.spec
    P, O = spec["period"], spec["owner_key"]
    where, params = scope.where()
    mod, high = warned_min("corporate"), severe_min("corporate")
    rows = rd.q(f"""
        WITH o AS (SELECT "{O}" AS owner, MAX(ews_score) AS score, SUM(ead_sar_mn) AS ead
                   FROM {scope.rel} WHERE "{P}" = ? AND ({where}) GROUP BY 1)
        SELECT b.rating_current AS rating, COUNT(*) AS borrowers,
               COUNT(*) FILTER (WHERE o.score >= {mod}) AS warned,
               COUNT(*) FILTER (WHERE o.score >= {high}) AS high_or_critical, SUM(o.ead) AS exposure
        FROM o JOIN {rd.owner("corporate")} b ON b."{O}" = o.owner AND b."{P}" = ?
        GROUP BY 1""", [period, *params, period])
    return [{"rating": r["rating"], "borrowers": int(r["borrowers"]), "warned": int(r["warned"]),
             "high_or_critical": int(r["high_or_critical"]), "exposure": float(r["exposure"] or 0)}
            for r in sorted(rows, key=lambda r: ratings.sort_key(r["rating"]))]


def level(domain_id: str, period: str = "", segment: str = "", classification: str = "",
          subsegment: str = "") -> dict[str, Any]:
    scope = Scope(domain_id, segment, classification, subsegment)
    spec, labels = scope.spec, _labels(domain_id)
    window, prior_of = _periods_window(domain_id, period, TREND_POINTS)
    chosen = window[-1]
    prior = prior_of.get(chosen, "")
    all_periods = rd.periods(domain_id)

    head = kpis(scope, window, None, prior_of)
    head_prev = kpis(scope, [prior], None, {prior: all_periods[all_periods.index(prior) - 1]
                                            if prior and all_periods.index(prior) else ""}) if prior else {}
    now = head.get((chosen, "__all__"), {})
    before = head_prev.get((prior, "__all__")) if prior else None
    top = reasons(scope, chosen, prior).get("__all__", [])

    # Children: the next level down, each as a card with its own trend.
    if scope.level == "portfolio":
        child_col, child_kind = f'"{spec["segment"]}"', "segment"
    elif scope.level == "segment":
        child_col, child_kind = f'"{spec["subsegment"]}"', "subsegment"
    elif scope.level == "classification":
        child_col, child_kind = f'"{spec["subsegment"]}"', "subsegment"
    else:
        child_col, child_kind = None, None

    children: list[dict[str, Any]] = []
    if child_col:
        table = kpis(scope, window, child_col, prior_of)
        prev_table = kpis(scope, [prior], child_col) if prior else {}
        tops = reasons(scope, chosen, prior, limit=3, group=child_col)
        keys = sorted({g for (p, g) in table if p == chosen},
                      key=lambda g: -table[(chosen, g)].get("exposure_severe", 0))
        for g in keys:
            children.append(_card(g, g, table[(chosen, g)], prev_table.get((prior, g)),
                                  _trend(table, window, g), tops.get(g, []), now, labels))

    classifications: list[dict[str, Any]] = []
    if domain_id == "retail" and scope.level == "segment":
        expr = classification_expr()
        table = kpis(scope, window, expr, prior_of)
        prev_table = kpis(scope, [prior], expr) if prior else {}
        tops = reasons(scope, chosen, prior, limit=3, group=expr)
        for key, meta in CLASSIFICATIONS.items():
            if (chosen, key) in table:
                card = _card(meta["label"], key, table[(chosen, key)], prev_table.get((prior, key)),
                             _trend(table, window, key), tops.get(key, []), now, labels)
                card.update({"meaning": meta["meaning"],
                             "derivation": "employment_type in (" + ", ".join(meta["types"]) + ")"})
                classifications.append(card)

    breadcrumbs = [{"label": labels["portfolio"], "scope": {}}]
    if segment:
        breadcrumbs.append({"label": segment, "scope": {"segment": segment}})
    if scope.classification:
        breadcrumbs.append({"label": CLASSIFICATIONS[scope.classification]["label"],
                            "scope": {"segment": segment, "classification": scope.classification}})
    if subsegment:
        breadcrumbs.append({"label": subsegment, "scope": {**scope.as_dict(), "level": None}})

    name = subsegment or (CLASSIFICATIONS[scope.classification]["label"] if scope.classification
                          else segment) or labels["portfolio"]
    move = _movement(now, before)
    payload = {
        "domain_id": domain_id, "release_id": spec["release_id"], "ruleset": ews.RULESET_VERSION,
        "period": chosen, "prior_period": prior, "periods": all_periods, "trend_periods": window,
        "frequency": "quarterly" if domain_id == "corporate" else "monthly",
        "money_unit": "SAR million", "scope": scope.as_dict(), "labels": labels,
        "name": name, "breadcrumbs": breadcrumbs,
        "headline": now, "previous": before, "movement": move,
        "trend": _trend(head, window, "__all__"), "top_reasons": top,
        "commentary": commentary(name, now, move, top, labels["period"], labels["owner"]),
        "children": children, "children_kind": child_kind, "classifications": classifications,
        "definitions": definitions(domain_id),
    }
    sources = by_source(scope, chosen)
    now["by_source"] = sources.get("__all__", [])
    if children:
        per = by_source(scope, chosen, child_col)
        for c in children:
            c["by_source"] = per.get(str(c["key"]), [])
    if classifications:
        per = by_source(scope, chosen, classification_expr())
        for c in classifications:
            c["by_source"] = per.get(str(c["key"]), [])
    payload["rating_mix"] = rating_mix(scope, chosen)
    if scope.level == "portfolio":
        payload["interpretation"] = interpretation(children, now, labels)
    return payload


def interpretation(children: list[dict[str, Any]], total: dict[str, Any],
                   labels: dict[str, str]) -> dict[str, Any]:
    """Which segment matters most, by stated arithmetic (no model call).

    Ranked by the segment's high-or-critical exposure as a share of the
    WHOLE book: a small segment's large move does not outrank a large
    segment's material one. The other criteria are shown, not weighted.
    """
    book = total.get("exposure") or 0.0
    ranked = []
    for c in children:
        share = 100 * c.get("exposure_severe", 0) / book if book else 0.0
        ranked.append({"key": c["key"], "label": c["label"], "severe_share_of_book_pct": share,
                       "exposure_severe": c.get("exposure_severe", 0),
                       "warned_pct": c.get("warned_pct", 0),
                       "warned_change": c["movement"].get("customers_warned"),
                       "odr_pct": c.get("odr_pct"), "odr_change": c["movement"].get("odr_pct"),
                       "materiality_pct": c.get("materiality", {}).get("exposure_pct", 0)})
    ranked.sort(key=lambda r: -r["severe_share_of_book_pct"])
    for i, r in enumerate(ranked, 1):
        r["rank"] = i
    if not ranked:
        return {"headline": "", "interpretation": "", "ranking": []}
    lead = ranked[0]
    text = (f"{lead['label']} carries the largest high-or-critical exposure: {money(lead['exposure_severe'])}, "
            f"{lead['severe_share_of_book_pct']:.1f}% of the whole book, with {lead['warned_pct']:.1f}% of its "
            f"{labels['owners']} warned.")
    if len(ranked) > 1:
        second = ranked[1]
        text += (f" {second['label']} follows at {money(second['exposure_severe'])} "
                 f"({second['severe_share_of_book_pct']:.1f}% of the book).")
    ext = {s["key"]: s for s in total.get("by_source", [])}
    if ext.get("bureau", {}).get("customers") or ext.get("open_banking", {}).get("customers"):
        text += (f" Of the {total.get('customers_warned', 0):,} warned {labels['owners']}, "
                 f"{ext['bureau']['customers']:,} carry a Bureau signal and "
                 f"{ext['open_banking']['customers']:,} an Open Banking signal.")
    movers = [r for r in ranked if (r["warned_change"] or 0) > 0]
    if movers:
        m = max(movers, key=lambda r: r["warned_change"])
        text += f" The largest rise in warned {labels['owners']} is in {m['label']} (+{m['warned_change']:,})."
    return {"headline": f"{lead['label']} is the most concerning {labels['segment'].lower()} this {labels['period']}",
            "interpretation": text, "ranking": ranked,
            "ranking_basis": ("High-or-critical exposure as a share of the whole book. Warned share, the change "
                              "in warned customers and the default-entry rate are shown alongside, not weighted."),
            "model_calls": 0}


# ---------------------------------------------------------------- customers

def _owner_rows_sql(scope: Scope, period: str) -> tuple[str, list[Any]]:
    spec = scope.spec
    P, O, K = spec["period"], spec["owner_key"], spec["key"]
    where, params = scope.where()
    name = f'ANY_VALUE("{spec["owner_name"]}")' if spec.get("owner_name") else "NULL"
    sql = f"""
        SELECT "{O}" AS owner, {name} AS owner_name,
               MAX(ews_score) AS score, BOOL_OR(dpd_days >= 90 OR stage = 3 OR default_flag = 1) AS bad,
               COUNT(*) AS facilities, SUM(ead_sar_mn) AS exposure, SUM(ecl_sar_mn) AS ecl,
               MAX(dpd_days) AS dpd, MAX(stage) AS stage,
               string_agg(DISTINCT "{spec['segment']}", ', ') AS segments,
               string_agg(DISTINCT "{spec['subsegment']}", ', ') AS subsegments,
               string_agg(ews_reasons, '; ') AS reasons_raw,
               arg_max("{K}", ews_score) AS worst_exposure
        FROM {scope.rel}
        WHERE "{P}" = ? AND ({where}) GROUP BY 1"""
    return sql, [period, *params]


def list_filter(domain_id: str, cohort: str = "warned", reason: str = "", layer: str = "", dpd: str = "",
                stage: int | None = None, band_min: str = "", search: str = "") -> tuple[str, list[Any]]:
    """The list's WHERE clause over `_owner_rows_sql` rows: the cohort and every filter."""
    if cohort not in COHORTS:
        raise rd.ReadRefused(f"{cohort!r} is not a cohort; they are {sorted(COHORTS)}.")
    conds, cparams = [cohort_sql(domain_id, cohort)], []
    if reason:
        conds.append("reasons_raw LIKE ?")
        cparams.append(f"%{reason}%")
    if layer:
        labels_in_layer = [r["label"] for r in ews.RULES[domain_id]
                           if cat.signal_dict(domain_id, r["id"]).get("layer") == layer]
        if not labels_in_layer:
            raise rd.ReadRefused(f"{layer!r} is not a layer of the {domain_id} rule set.")
        conds.append("(" + " OR ".join("reasons_raw LIKE ?" for _ in labels_in_layer) + ")")
        cparams.extend(f"%{lbl}%" for lbl in labels_in_layer)
    if dpd:
        bucket = next((b for b in DPD_BUCKETS if b[0] == dpd), None)
        if bucket is None:
            raise rd.ReadRefused(f"{dpd!r} is not a DPD bucket; they are {[b[0] for b in DPD_BUCKETS]}.")
        conds.append("dpd BETWEEN ? AND ?")
        cparams.extend([bucket[2], bucket[3]])
    if stage:
        conds.append("stage = ?")
        cparams.append(int(stage))
    if band_min:
        floor = next((f for f, n in ews.bands(domain_id) if n == band_min), None)
        if floor is None:
            raise rd.ReadRefused(f"{band_min!r} is not a band.")
        conds.append("score >= ?")
        cparams.append(floor)
    if search:
        conds.append("(owner ILIKE ? OR COALESCE(owner_name, '') ILIKE ?)")
        cparams.extend([f"%{search}%", f"%{search}%"])
    return " AND ".join(conds), cparams


def customers(domain_id: str, period: str = "", segment: str = "", classification: str = "",
              subsegment: str = "", cohort: str = "warned", reason: str = "", layer: str = "",
              dpd: str = "", stage: int | None = None, band_min: str = "", search: str = "",
              limit: int = 25, offset: int = 0, dims: dict[str, str] | None = None) -> dict[str, Any]:
    scope = Scope(domain_id, segment, classification, subsegment, dims=dims)
    spec, labels = scope.spec, _labels(domain_id)
    window, _ = _periods_window(domain_id, period, TREND_POINTS)
    chosen = window[-1]
    if cohort not in COHORTS:
        raise rd.ReadRefused(f"{cohort!r} is not a cohort; they are {sorted(COHORTS)}.")
    base, params = _owner_rows_sql(scope, chosen)
    filt, cparams = list_filter(domain_id, cohort, reason, layer, dpd, stage, band_min, search)
    total = rd.q(f"SELECT COUNT(*) AS n, SUM(exposure) AS ead FROM ({base}) WHERE {filt}",
                 [*params, *cparams])[0]
    page = rd.q(f"SELECT * FROM ({base}) WHERE {filt} ORDER BY score DESC, exposure DESC, owner "
                f"LIMIT ? OFFSET ?", [*params, *cparams, int(limit), int(offset)])
    cohorts = []
    for key, (label, _) in COHORTS.items():
        n = rd.q(f"SELECT COUNT(*) AS n FROM ({base}) WHERE {cohort_sql(domain_id, key)}", params)[0]["n"]
        cohorts.append({"key": key, "label": label.replace("customers", labels["owners"]), "customers": int(n)})
    scope_total = rd.q(f"SELECT SUM(exposure) AS ead FROM ({base})", params)[0]["ead"] or 0.0

    owners = [r["owner"] for r in page]
    series = _series(scope, owners, window)
    facts = _owner_facts(domain_id, owners, chosen)
    rows = []
    for r in page:
        reasons_list = sorted({x.strip() for x in (r["reasons_raw"] or "").split(";") if x.strip()})
        rows.append({
            "customer_id": r["owner"], "customer_name": r["owner_name"],
            "score": int(r["score"] or 0), "band": band_of(r["score"], domain_id),
            "current_bad": bool(r["bad"]),
            "forward_risk": bool((r["score"] or 0) >= warned_min(domain_id) and not r["bad"]),
            "facilities": int(r["facilities"]), "exposure": float(r["exposure"] or 0),
            "ecl": float(r["ecl"] or 0), "dpd": int(r["dpd"] or 0), "stage": int(r["stage"] or 0),
            "segments": r["segments"], "subsegments": r["subsegments"],
            "worst_exposure": r["worst_exposure"],
            "share_of_scope_pct": 100 * float(r["exposure"] or 0) / scope_total if scope_total else 0,
            "reasons": [_reason_meta(domain_id, x) for x in reasons_list],
            "layers": sorted({_reason_meta(domain_id, x)["layer"] for x in reasons_list} - {""}),
            "series": series.get(r["owner"], []), **facts.get(r["owner"], {}),
        })
    return {"domain_id": domain_id, "period": chosen, "scope": scope.as_dict(), "labels": labels,
            "cohort": cohort, "cohorts": cohorts,
            "filters": {"reason": reason, "layer": layer, "dpd": dpd, "stage": stage,
                        "band_min": band_min, "search": search},
            "dpd_buckets": [{"key": k, "label": lbl} for k, lbl, *_ in DPD_BUCKETS],
            "layers": sorted({cat.signal_dict(domain_id, r["id"]).get("layer", "")
                              for r in ews.RULES[domain_id]} - {""}),
            "layer_labels": {k: cat.layer_label(k) for k in cat.LAYERS},
            "reasons": [r["label"] for r in ews.RULES[domain_id]],
            "total": int(total["n"] or 0), "total_exposure": float(total["ead"] or 0),
            "limit": int(limit), "offset": int(offset), "customers": rows,
            "definitions": definitions(domain_id), "warned_min": warned_min(domain_id)}


def _reason_meta(domain_id: str, label: str) -> dict[str, Any]:
    rule = next((r for r in ews.RULES[domain_id] if r["label"] == label), None)
    meta = cat.signal_dict(domain_id, rule["id"]) if rule else {}
    return {"key": rule["id"] if rule else label, "name": label, "weight": rule["weight"] if rule else None,
            "layer": meta.get("layer", ""), "layer_name": cat.layer_label(meta.get("layer", "")),
            "family": meta.get("family", "")}


def _series(scope: Scope, owners: list[str], window: list[str]) -> dict[str, list[dict[str, Any]]]:
    """Each customer's six periods IN THE SAME VIEW as the list, so the last point is the row's score."""
    if not owners:
        return {}
    domain_id = scope.domain_id
    spec = rd.domain_spec(domain_id)
    P, O = spec["period"], spec["owner_key"]
    where, params = scope.where()
    rows = rd.q(f"""SELECT "{O}" AS owner, "{P}" AS period, MAX(ews_score) AS score,
                           MAX(dpd_days) AS dpd, SUM(ead_sar_mn) AS exposure
                    FROM {scope.rel}
                    WHERE "{O}" IN ({', '.join('?' for _ in owners)})
                      AND "{P}" IN ({', '.join('?' for _ in window)}) AND ({where})
                    GROUP BY 1, 2""", [*owners, *window, *params])
    by: dict[str, dict[str, dict]] = {}
    for r in rows:
        by.setdefault(r["owner"], {})[r["period"]] = r
    return {o: [{"period": p, "score": (by.get(o, {}).get(p) or {}).get("score"),
                 "dpd": (by.get(o, {}).get(p) or {}).get("dpd"),
                 "exposure": (by.get(o, {}).get(p) or {}).get("exposure")} for p in window]
            for o in owners}


def _owner_facts(domain_id: str, owners: list[str], period: str) -> dict[str, dict[str, Any]]:
    if not owners:
        return {}
    spec = rd.domain_spec(domain_id)
    if domain_id == "corporate":
        cols = ("group_id", "group_name", "rating_current", "rating_previous", "rating_outlook",
                "watchlist_flag", "watchlist_reason", "relationship_tier", "region")
    else:
        cols = ("customer_segment", "employment_type", "region", "tenure_months", "behaviour_score",
                "behaviour_score_previous", "score_band", "score_migration", "accounts_held")
    rows = rd.q(f"""SELECT "{spec['owner_key']}" AS owner, {', '.join(f'"{c}"' for c in cols)}
                    FROM {rd.owner(domain_id)} WHERE "{spec['period']}" = ?
                      AND "{spec['owner_key']}" IN ({', '.join('?' for _ in owners)})""",
                [period, *owners])
    out = {r.pop("owner"): r for r in rows}
    extra = ("branch_name", "business_unit", "rm_name") if domain_id == "corporate" else ("branch_name",)
    for r in rd.q(f"""SELECT "{spec['owner_key']}" AS owner, {', '.join(extra)} FROM {rd.branch(domain_id)}
                      WHERE "{spec['period']}" = ? AND "{spec['owner_key']}" IN ({', '.join('?' for _ in owners)})""",
                  [period, *owners]):
        out.setdefault(r.pop("owner"), {}).update(r)
    return out


# ---------------------------------------------------------------- one customer

def customer(domain_id: str, owner_id: str, period: str = "") -> dict[str, Any]:
    spec = rd.domain_spec(domain_id)
    chosen, prior, all_periods = rd.resolve_period(domain_id, period)
    P, O, K = spec["period"], spec["owner_key"], spec["key"]
    rows = rd.q(f'SELECT * FROM {rd.exposure(domain_id)} WHERE "{O}" = ? AND "{P}" = ? ORDER BY ews_score DESC, ead_sar_mn DESC',
                [owner_id, chosen])
    if not rows:
        raise LookupError(f"{owner_id} has no exposures in {chosen}.")
    labels = _labels(domain_id)
    rules = ews.RULES[domain_id]
    exposures = []
    for r in rows:
        evaluated = []
        for rule in rules:
            fired = rule["label"] in [x.strip() for x in (r.get("ews_reasons") or "").split(";")]
            needed = sorted(ews._columns(rule["sql"]))
            meta = cat.signal_dict(domain_id, rule["id"])
            evaluated.append({"id": rule["id"], "name": rule["label"], "weight": rule["weight"],
                              "fired": fired, "condition": rule["sql"],
                              "values": {c: r.get(c) for c in needed},
                              "available": all(c in r for c in needed),
                              "layer": meta.get("layer", ""), "layer_name": cat.layer_label(meta.get("layer", "")),
                              "family": meta.get("family", ""), "limitation": rule.get("limitation", "")})
        exposures.append({
            "exposure_id": r[K], "segment": r.get(spec["segment"]), "subsegment": r.get(spec["subsegment"]),
            "product_type": r.get("product_type"), "exposure": r.get("ead_sar_mn"), "limit": r.get("limit_sar_mn"),
            "ecl": r.get("ecl_sar_mn"), "utilisation_pct": r.get("utilisation_pct"), "dpd": r.get("dpd_days"),
            "stage": r.get("stage"), "score": r.get("ews_score"), "band": r.get("ews_band"),
            "reasons": [x.strip() for x in (r.get("ews_reasons") or "").split(";") if x.strip()],
            "rules": evaluated})
    history = rd.q(f"""SELECT "{P}" AS period, MAX(ews_score) AS score, MAX(dpd_days) AS dpd, MAX(stage) AS stage,
                              SUM(ead_sar_mn) AS exposure, SUM(ecl_sar_mn) AS ecl, COUNT(*) AS facilities,
                              BOOL_OR(dpd_days >= 90 OR stage = 3 OR default_flag = 1) AS bad,
                              string_agg(ews_reasons, '; ') AS reasons_raw
                       FROM {rd.exposure(domain_id)} WHERE "{O}" = ? GROUP BY 1 ORDER BY 1""", [owner_id])
    for h in history:
        h["band"] = band_of(h["score"], domain_id)
        h["reasons"] = sorted({x.strip() for x in (h.pop("reasons_raw") or "").split(";") if x.strip()})
    score = max(int(r.get("ews_score") or 0) for r in rows)
    bad = any((r.get("dpd_days") or 0) >= 90 or r.get("stage") == 3 or r.get("default_flag") == 1 for r in rows)
    facts = _owner_facts(domain_id, [owner_id], chosen).get(owner_id, {})
    fired = sorted({x for e in exposures for x in e["reasons"]})
    return {"domain_id": domain_id, "release_id": spec["release_id"], "period": chosen, "prior_period": prior,
            "labels": labels, "customer_id": owner_id,
            "customer_name": rows[0].get(spec["owner_name"]) if spec.get("owner_name") else None,
            "score": score, "band": band_of(score, domain_id), "current_bad": bad,
            "forward_risk": score >= warned_min(domain_id) and not bad,
            "exposure": sum(float(r.get("ead_sar_mn") or 0) for r in rows),
            "ecl": sum(float(r.get("ecl_sar_mn") or 0) for r in rows),
            "facilities": len(rows), "facts": facts, "exposures": exposures,
            "reasons": [_reason_meta(domain_id, x) for x in fired],
            "history": history, "definitions": definitions(domain_id), "warned_min": warned_min(domain_id),
            "links": links(domain_id, owner_id, chosen)}


def links(domain_id: str, owner_id: str, period: str) -> dict[str, str]:
    from urllib.parse import urlencode
    return {"borrower_360": "/borrower-360?" + urlencode({"domain": domain_id, "customer_id": owner_id, "period": period}),
            "early_warning": "/early-warning?" + urlencode({"domain": domain_id, "customer": owner_id,
                                                            "period": period})}


# ---------------------------------------------------------------- export to What-If

def export(body: dict[str, Any], store) -> dict[str, Any]:
    """Freeze a population for What-If: the exposures of the matching customers.

    The population is computed now and stored with a membership hash, so a
    later What-If runs on exactly these exposures even if the view changes.
    """
    domain_id = str(body.get("domain") or "")
    spec = rd.domain_spec(domain_id)
    scope = Scope(domain_id, body.get("segment", ""), body.get("classification", ""),
                  body.get("subsegment", ""), dims=body.get("dims") or None)
    chosen, _, _ = rd.resolve_period(domain_id, str(body.get("period") or ""))
    if body.get("customer_id"):
        owners = [str(body["customer_id"])]
        cohort_key = "customer"
    else:
        result = customers(domain_id, chosen, scope.segment, scope.classification, scope.subsegment,
                           cohort=str(body.get("cohort") or "warned"), reason=body.get("reason", ""),
                           layer=body.get("layer", ""), dpd=body.get("dpd", ""), stage=body.get("stage"),
                           band_min=body.get("band_min", ""), search=body.get("search", ""),
                           limit=1_000_000, offset=0, dims=scope.dims)
        owners = [c["customer_id"] for c in result["customers"]]
        cohort_key = result["cohort"]
    where, params = scope.where()
    P, O, K = spec["period"], spec["owner_key"], spec["key"]
    members = rd.q(f"""SELECT "{K}" AS k, "{O}" AS o, ead_sar_mn AS ead, ecl_sar_mn AS ecl, stage, ews_band
                       FROM {scope.rel} WHERE "{P}" = ? AND ({where})
                         AND "{O}" IN (SELECT unnest(?::VARCHAR[])) ORDER BY 1""",
                   [chosen, *params, owners]) if owners else []
    membership = hashlib.sha256("\n".join(m["k"] for m in members).encode()).hexdigest()
    request = {"domain": domain_id, "period": chosen, "scope": scope.as_dict(), "cohort": cohort_key,
               "filters": {k: body.get(k) for k in ("reason", "layer", "dpd", "stage", "band_min", "search")
                           if body.get(k)}, "customer_id": body.get("customer_id") or ""}
    object_id = "ews-cohort-" + hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()[:12]
    stage_mix: dict[str, dict[str, float]] = {}
    for m in members:
        s = stage_mix.setdefault(str(m["stage"]), {"n": 0, "ead": 0.0, "ecl": 0.0})
        s["n"] += 1
        s["ead"] += float(m["ead"] or 0)
        s["ecl"] += float(m["ecl"] or 0)
    labels = _labels(domain_id)
    name_bits = [scope.segment, CLASSIFICATIONS.get(scope.classification, {}).get("label", ""),
                 scope.subsegment, *(dim_value_label(domain_id, k, v) for k, v in scope.dims.items()),
                 str(body.get("customer_id") or "")]
    obj = {
        "object_id": object_id, "kind": "cohort", "status": "frozen", "domain_id": domain_id,
        "release_id": spec["release_id"], "ruleset": ews.RULESET_VERSION, "period": chosen,
        "title": " · ".join([b for b in name_bits if b] or [labels["portfolio"]]) + f" · {COHORTS.get(cohort_key, ('customer',))[0]}",
        "request": request, "membership_hash": membership,
        "counts": {"customers": len({m["o"] for m in members}), "exposures": len(members)},
        "exposure": sum(float(m["ead"] or 0) for m in members),
        "ecl": sum(float(m["ecl"] or 0) for m in members),
        "stage_mix": stage_mix, "exposure_ids": [m["k"] for m in members],
        "customer_ids": sorted({m["o"] for m in members}),
        "receiver": {"module": "What-If", "status": "LIVE",
                     "note": "What-If (module 3) opens this cohort by id and runs scenarios on exactly these exposures."},
        "created_at": time.time(), "cockpit_read": False, "cockpit_write": False,
    }
    with store() as c:
        c.execute("INSERT OR REPLACE INTO cohort VALUES (?, ?, ?)",
                  (object_id, obj["created_at"], json.dumps(obj, default=str)))
    return {k: v for k, v in obj.items() if k not in ("exposure_ids",)}


def meta(domain_id: str) -> dict[str, Any]:
    spec = rd.domain_spec(domain_id)
    periods = rd.periods(domain_id)
    segs = [r["s"] for r in rd.q(f'SELECT DISTINCT "{spec["segment"]}" AS s FROM {rd.exposure(domain_id)} ORDER BY 1')]
    return {"domain_id": domain_id, "release_id": spec["release_id"], "ruleset": ews.RULESET_VERSION,
            "periods": periods, "as_of": periods[-1], "labels": _labels(domain_id),
            "frequency": "quarterly" if domain_id == "corporate" else "monthly",
            "segments": segs, "classifications": ([{"key": k, "label": v["label"]} for k, v in CLASSIFICATIONS.items()]
                                                  if domain_id == "retail" else []),
            "cohorts": [{"key": k, "label": v[0].replace("customers", _labels(domain_id)["owners"])}
                        for k, v in COHORTS.items()],
            "dpd_buckets": [{"key": k, "label": lbl} for k, lbl, *_ in DPD_BUCKETS],
            "bands": [n for _, n in ews.bands(domain_id)], "band_floors": list(ews.BAND_FLOORS[domain_id]),
            "money_unit": "SAR million",
            "common_quarter_end": {"corporate": "2026Q2", "retail": "2026-06"},
            "definitions": definitions(domain_id)}
