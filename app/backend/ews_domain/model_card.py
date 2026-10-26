"""The Early Warning rule set as a standard MODEL CARD.

Written for a credit-committee member who is not a modeller: what the model
is for, what it reads (by source, then risk layer, then rule), how scores are
cut into bands, how it is performing on the book today and over the last six
periods, what it cannot do, and how it has changed.

Every count is computed live from the EWS release with SQL at the requested
period. The only fixed text is prose. Rules come from `ews_rules.RULES`
(whatever the live rule set holds, including rules added after this module
was written); their source and risk layer come from `ews_catalogue`, and a
rule the catalogue does not yet describe is still shown, under Bank Internal
and the layer "other".

Counting rules (the same as the drill, `drill.py`):
  * a customer's score is the highest `ews_score` among its exposures;
  * WARNED = score at or above the book's moderate floor; HIGH OR CRITICAL =
    at or above its high floor;
  * ALREADY BAD = any exposure 90+ DPD, Stage 3 or in default;
  * FORWARD RISK = warned and not already bad.
"""
from __future__ import annotations

import re
from typing import Any

from backend.ews_domain import ews_catalogue as cat
from backend.ews_domain import ews_rules as ews
from backend.ews_domain import reader as rd

STABILITY_POINTS = 6

#: Targets the rule set was calibrated to (ops/ews_calibration.py).
TARGETS = {"warned_min_pct": 10.0, "warned_max_pct": 20.0, "high_or_critical_max_pct": 7.0,
           "capture_pct": 100.0}

OTHER_LAYER = {"key": "other", "label": "Other",
               "means": "Rules the signal catalogue does not yet place in a risk layer.",
               "risk_layer": "", "risk_layer_label": ""}

_BAD = "(dpd_days >= 90 OR stage = 3 OR default_flag = 1)"


# ---------------------------------------------------------------- words

def _nouns(domain_id: str) -> dict[str, str]:
    if domain_id == "corporate":
        return {"book": "Corporate", "owner": "borrower", "owners": "borrowers",
                "exposure": "facility", "exposures": "facilities", "period": "quarter"}
    return {"book": "Retail", "owner": "customer", "owners": "customers",
            "exposure": "account", "exposures": "accounts", "period": "month"}


def _column_labels(domain_id: str) -> dict[str, dict[str, str]]:
    """Every catalogue input of this book, by column: label and unit."""
    out: dict[str, dict[str, str]] = {}
    for sig in cat.SIGNALS:
        if sig.domain != domain_id:
            continue
        for inp in sig.inputs:
            out.setdefault(inp.column, {"label": inp.label, "unit": inp.unit,
                                        "meaning": inp.meaning})
    return out


def _human(column: str, labels: dict[str, dict[str, str]]) -> tuple[str, str]:
    known = labels.get(column)
    if known:
        return known["label"], known["unit"]
    words = column.replace("_pct", "").replace("_sar_mn", "").replace("_", " ").strip()
    unit = "percent" if column.endswith("_pct") else "days" if column.endswith("_days") else ""
    return words[:1].upper() + words[1:], unit


_OPS = {">": "above", ">=": "at or above", "<": "below", "<=": "at or below", "=": "equals",
        "<>": "is not", "!=": "is not"}
_CMP = re.compile(r"^\(?\s*([a-z_][a-z0-9_]*)\s*(>=|<=|<>|!=|>|<|=)\s*(-?\d+(?:\.\d+)?|'[^']*')\s*\)?$", re.I)
_IN = re.compile(r"^\(?\s*([a-z_][a-z0-9_]*)\s+(NOT\s+)?IN\s*\(([^)]*)\)\s*\)?$", re.I)


def _split(sql: str, word: str) -> list[str]:
    """Split on a top-level AND / OR (not inside parentheses or quotes)."""
    parts, depth, buf, i, quote = [], 0, "", 0, False
    token = f" {word} "
    while i < len(sql):
        ch = sql[i]
        if ch == "'":
            quote = not quote
        if not quote:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            if depth == 0 and sql[i:i + len(token)].upper() == token:
                parts.append(buf.strip())
                buf, i = "", i + len(token)
                continue
        buf += ch
        i += 1
    parts.append(buf.strip())
    return [p for p in parts if p]


def _unit(num: str, unit: str) -> str:
    if unit in ("percent", "%"):
        return f"{num}%"
    if unit in ("days", "months"):
        return f"{num} {unit}"
    return num


def _clause(sql: str, labels: dict[str, dict[str, str]]) -> str | None:
    m = _CMP.match(sql.strip())
    if m:
        col, op, val = m.groups()
        label, unit = _human(col, labels)
        if val.startswith("'"):
            return f"{label} {'is' if op == '=' else 'is not'} {val.strip(chr(39))}"
        if (unit == "flag" or col.endswith("_flag")) and op == "=" and val in ("1", "0"):
            name = label if "flag" in label.lower() else f"{label} flag"
            return f"{name} {'is set' if val == '1' else 'is not set'}"
        if col == "stage" and op == "=":
            return f"Stage {val}"
        return f"{label} {_OPS.get(op, op)} {_unit(val, unit)}"
    m = _IN.match(sql.strip())
    if m:
        col, neg, vals = m.groups()
        label, _ = _human(col, labels)
        items = [v.strip().strip("'") for v in vals.split(",")]
        joined = items[0] if len(items) == 1 else f"{', '.join(items[:-1])} or {items[-1]}"
        return f"{label} {'is not' if neg else 'is'} {joined}"
    return None


def threshold(sql: str, labels: dict[str, dict[str, str]]) -> dict[str, str]:
    """The rule's trigger point in words, parsed from its SQL where it is simple."""
    for word in ("OR", "AND"):
        parts = _split(sql, word)
        if len(parts) > 1:
            said = [_clause(p, labels) for p in parts]
            if all(said) and len(parts) <= 3:
                return {"text": f" {word.lower()} ".join(s for s in said if s), "kind": "composite"}
            return {"text": "A combination of conditions: see \"What it checks\".",
                    "kind": "composite"}
    one = _clause(sql, labels)
    if one is None:
        return {"text": "See the technical detail.", "kind": "other"}
    kind = "flag" if " flag is " in one else "category" if " is " in one else "numeric"
    return {"text": one, "kind": kind}


# ---------------------------------------------------------------- reads

def _period_window(domain_id: str, period: str) -> tuple[str, str, list[str], list[str]]:
    chosen, prior, all_periods = rd.resolve_period(domain_id, period)
    i = all_periods.index(chosen)
    return chosen, prior, all_periods, all_periods[max(0, i - STABILITY_POINTS + 1): i + 1]


def _fires(domain_id: str, chosen: str, rules: list[dict[str, Any]],
           available: set[str]) -> dict[str, dict[str, Any]]:
    """Per live rule: distinct owners and exposures on which its SQL is true at `chosen`."""
    spec = rd.domain_spec(domain_id)
    exp, P, O = rd.exposure(domain_id), spec["period"], spec["owner_key"]
    live = [r for r in rules if ews._columns(r["sql"]) <= available]
    out: dict[str, dict[str, Any]] = {}

    def one_query(batch: list[dict[str, Any]]) -> None:
        cols = ", ".join(
            f'COUNT(DISTINCT CASE WHEN ({r["sql"]}) THEN "{O}" END) AS "o{i}", '
            f'SUM(CASE WHEN ({r["sql"]}) THEN 1 ELSE 0 END) AS "e{i}", '
            f'SUM(CASE WHEN ({r["sql"]}) THEN ead_sar_mn ELSE 0 END) AS "x{i}"'
            for i, r in enumerate(batch))
        row = rd.q(f'SELECT {cols} FROM {exp} WHERE "{P}" = ?', [chosen])[0]
        for i, r in enumerate(batch):
            out[r["id"]] = {"customers": int(row[f"o{i}"] or 0), "exposures": int(row[f"e{i}"] or 0),
                            "exposure_sar_mn": float(row[f"x{i}"] or 0), "error": ""}

    if not live:
        return out
    try:
        one_query(live)
    except Exception:  # noqa: BLE001 - isolate the rule that cannot be evaluated
        for r in live:
            try:
                one_query([r])
            except Exception as exc:  # noqa: BLE001
                out[r["id"]] = {"customers": None, "exposures": None, "exposure_sar_mn": None,
                                "error": str(exc).splitlines()[0][:200]}
    return out


def _owner_stats(domain_id: str, periods: list[str]) -> dict[str, dict[str, Any]]:
    """Per period: customers, band counts and the four performance counts."""
    spec = rd.domain_spec(domain_id)
    exp, P, O = rd.exposure(domain_id), spec["period"], spec["owner_key"]
    (crit, _), (high, _), (mod, _), _ = ews.bands(domain_id)
    marks = ", ".join("?" for _ in periods)
    rows = rd.q(f"""
        WITH o AS (SELECT "{P}" AS period, "{O}" AS owner, MAX(ews_score) AS score,
                          BOOL_OR({_BAD}) AS bad
                   FROM {exp} WHERE "{P}" IN ({marks}) GROUP BY ALL)
        SELECT period, COUNT(*) AS customers,
               SUM(CASE WHEN score >= {crit} THEN 1 ELSE 0 END) AS critical,
               SUM(CASE WHEN score >= {high} AND score < {crit} THEN 1 ELSE 0 END) AS high,
               SUM(CASE WHEN score >= {mod} AND score < {high} THEN 1 ELSE 0 END) AS moderate,
               SUM(CASE WHEN score >= 1 AND score < {mod} THEN 1 ELSE 0 END) AS low,
               SUM(CASE WHEN COALESCE(score, 0) < 1 THEN 1 ELSE 0 END) AS none,
               SUM(CASE WHEN score >= {mod} THEN 1 ELSE 0 END) AS warned,
               SUM(CASE WHEN score >= {high} THEN 1 ELSE 0 END) AS high_or_critical,
               SUM(CASE WHEN bad THEN 1 ELSE 0 END) AS already_bad,
               SUM(CASE WHEN bad AND score >= {mod} THEN 1 ELSE 0 END) AS already_bad_warned,
               SUM(CASE WHEN score >= {mod} AND NOT bad THEN 1 ELSE 0 END) AS forward_risk
        FROM o GROUP BY 1 ORDER BY 1""", periods)
    out = {}
    for r in rows:
        row = {k: int(v or 0) for k, v in r.items() if k != "period"}
        n = row["customers"]
        row["warned_pct"] = 100 * row["warned"] / n if n else 0.0
        row["high_or_critical_pct"] = 100 * row["high_or_critical"] / n if n else 0.0
        row["capture_pct"] = (100 * row["already_bad_warned"] / row["already_bad"]
                              if row["already_bad"] else None)
        row["forward_risk_pct"] = 100 * row["forward_risk"] / n if n else 0.0
        out[r["period"]] = row
    return out


def _band_exposures(domain_id: str, chosen: str) -> dict[str, dict[str, Any]]:
    spec = rd.domain_spec(domain_id)
    rows = rd.q(f"""SELECT COALESCE(ews_band, 'none') AS band, COUNT(*) AS exposures,
                           SUM(ead_sar_mn) AS ead FROM {rd.exposure(domain_id)}
                    WHERE "{spec['period']}" = ? GROUP BY 1""", [chosen])
    return {r["band"]: {"exposures": int(r["exposures"]), "exposure_sar_mn": float(r["ead"] or 0)}
            for r in rows}


# ---------------------------------------------------------------- sections

def _sources(domain_id: str, chosen: str, available: set[str]) -> tuple[list[dict[str, Any]],
                                                                         list[dict[str, Any]]]:
    labels = _column_labels(domain_id)
    rules = list(ews.RULES.get(domain_id, []))
    fires = _fires(domain_id, chosen, rules, available)
    nouns = _nouns(domain_id)

    flat: list[dict[str, Any]] = []
    for rule in rules:
        meta = cat.signal(domain_id, rule["id"])
        src = meta.source if meta and meta.source in cat.SOURCE_BY_KEY else "bank_internal"
        fam = meta.family if meta and meta.family in cat.FAMILY_BY_KEY else "other"
        needed = sorted(ews._columns(rule["sql"]))
        missing = [c for c in needed if c not in available]
        fired = fires.get(rule["id"], {})
        live = not missing and not fired.get("error")
        source_obj = cat.SOURCE_BY_KEY.get(src)
        why = ""
        if missing:
            why = (f"The release does not publish {', '.join(missing)}, so the rule cannot be "
                   "evaluated and contributes nothing to any score.")
        elif fired.get("error"):
            why = f"The rule's expression could not be evaluated on this release ({fired['error']})."
        limitation = (rule.get("limitation") or getattr(meta, "limitation", "") or "")
        if not live and not limitation and source_obj is not None and not source_obj.connected:
            limitation = source_obj.absent_because
        flat.append({
            "id": rule["id"],
            "name": rule["label"],
            "condition": (meta.condition if meta else "")
            or "Not yet described in the signal catalogue; see the technical detail.",
            "review": meta.review if meta else "",
            "threshold": threshold(rule["sql"], labels)["text"],
            "threshold_kind": threshold(rule["sql"], labels)["kind"],
            "weight": rule["weight"],
            "live": live,
            "not_live_reason": why,
            "limitation": limitation,
            "proxy": bool(meta and meta.proxy),
            "customers": fired.get("customers") if live else None,
            "exposures": fired.get("exposures") if live else None,
            "exposure_sar_mn": fired.get("exposure_sar_mn") if live else None,
            "source": src,
            "family": fam,
            "catalogued": meta is not None,
            "technical": {
                "expression": rule["sql"],
                "inputs": [{"column": c, "label": _human(c, labels)[0], "unit": _human(c, labels)[1],
                            "meaning": labels.get(c, {}).get("meaning", ""), "present": c in available}
                           for c in needed],
                "missing_columns": missing,
                "evaluated_on": f"each {nouns['exposure']} row at the period; a {nouns['owner']} "
                                "fires if any of its exposures does",
            },
        })

    sources = []
    for s in cat.SOURCES:
        mine = [r for r in flat if r["source"] == s.key]
        families = [f.key for f in cat.FAMILIES] + ["other"]
        layers = []
        for fk in families:
            rows = [r for r in mine if r["family"] == fk]
            if not rows:
                continue
            f = cat.FAMILY_BY_KEY.get(fk)
            layer = ({"key": f.key, "label": f.label, "means": f.means, "risk_layer": f.layer,
                      "risk_layer_label": cat.layer_label(f.layer)} if f else dict(OTHER_LAYER))
            layers.append({**layer, "rules": rows,
                           "rules_total": len(rows), "rules_live": sum(r["live"] for r in rows)})
        live_n = sum(r["live"] for r in mine)
        sources.append({
            "key": s.key, "label": s.label, "description": s.means,
            "status": "connected" if live_n else "declared, no live rule",
            "connected": bool(live_n),
            "catalogue_connected": s.connected,
            "absent_because": "" if live_n else (s.absent_because or
                                                "No rule reading this source is live on this release."),
            "requires": [] if live_n else list(s.requires),
            "rules_total": len(mine), "rules_live": live_n, "layers": layers,
        })
    return sources, flat


def _bands(domain_id: str, chosen: str, stats: dict[str, Any]) -> dict[str, Any]:
    nouns = _nouns(domain_id)
    (crit, _), (high, _), (mod, _), _ = ews.bands(domain_id)
    by_band = _band_exposures(domain_id, chosen)
    rows = [("critical", crit, None, "Act now: the strongest combination of warning signs."),
            ("high", high, crit - 1, "Review this cycle with the relationship or collections team."),
            ("moderate", mod, high - 1, "Watch: on the warning list, lowest priority."),
            ("low", 1, mod - 1, "A sign is present but below the warning floor; not warned."),
            ("none", 0, 0, "No warning rule fires.")]
    total = stats.get("customers", 0)
    out = []
    for name, lo, hi, means in rows:
        if name == "none":
            score = "0"
        elif hi is None:
            score = f"{lo} or more"
        elif hi <= lo:
            score = f"{lo}"
        else:
            score = f"{lo} to {hi}"
        n = stats.get(name, 0)
        out.append({"band": name, "floor": lo, "ceiling": hi, "score_range": score,
                    "warned": name in ("critical", "high", "moderate"), "means": means,
                    "customers": n, "customers_pct": 100 * n / total if total else 0.0,
                    "exposures": by_band.get(name, {}).get("exposures", 0),
                    "exposure_sar_mn": by_band.get(name, {}).get("exposure_sar_mn", 0.0)})
    return {"floors": {"critical": crit, "high": high, "moderate": mod, "low": 1, "none": 0},
            "rows": out, "customers": total,
            "how": (f"A {nouns['owner']}'s score is the highest score among its {nouns['exposures']}; "
                    f"the score is the sum of the weights of the rules that fire. Moderate, high and "
                    f"critical {nouns['owners']} are 'warned'.")}


def _target(key: str, label: str, value: float | None, met: bool | None, said: str) -> dict[str, Any]:
    return {"key": key, "label": label, "value": value, "met": met, "statement": said}


def _performance(domain_id: str, chosen: str, window: list[str],
                 stats: dict[str, dict[str, Any]]) -> dict[str, Any]:
    nouns = _nouns(domain_id)
    now = stats.get(chosen, {})

    def four(p: str) -> dict[str, Any]:
        s = stats.get(p, {})
        return {"period": p, "customers": s.get("customers", 0),
                "warned": s.get("warned", 0), "warned_pct": s.get("warned_pct", 0.0),
                "high_or_critical": s.get("high_or_critical", 0),
                "high_or_critical_pct": s.get("high_or_critical_pct", 0.0),
                "already_bad": s.get("already_bad", 0),
                "already_bad_warned": s.get("already_bad_warned", 0),
                "capture_pct": s.get("capture_pct"), "forward_risk": s.get("forward_risk", 0)}

    cur = four(chosen)
    w, h, c = cur["warned_pct"], cur["high_or_critical_pct"], cur["capture_pct"]
    t = TARGETS
    targets = [
        _target("warned_rate", f"Warned {t['warned_min_pct']:.0f}–{t['warned_max_pct']:.0f}% of {nouns['owners']}",
                w, t["warned_min_pct"] <= w <= t["warned_max_pct"],
                f"{w:.1f}% of {nouns['owners']} are warned."),
        _target("high_or_critical_rate", f"High or critical below {t['high_or_critical_max_pct']:.0f}%",
                h, h < t["high_or_critical_max_pct"], f"{h:.1f}% are high or critical."),
        _target("already_bad_capture", f"Every already-bad {nouns['owner']} warned", c,
                None if c is None else cur["already_bad_warned"] == cur["already_bad"],
                (f"{cur['already_bad_warned']:,} of {cur['already_bad']:,} already-bad "
                 f"{nouns['owners']} are warned." if cur["already_bad"]
                 else f"No {nouns['owner']} is already bad at this period.")),
    ]
    stability = [four(p) for p in window]
    for row in stability:
        row["targets_met"] = (t["warned_min_pct"] <= row["warned_pct"] <= t["warned_max_pct"]
                              and row["high_or_critical_pct"] < t["high_or_critical_max_pct"]
                              and (row["already_bad"] == 0
                                   or row["already_bad_warned"] == row["already_bad"]))
    rates = [r["warned_pct"] for r in stability]
    return {
        **cur,
        "targets": targets,
        "targets_met": sum(1 for x in targets if x["met"]),
        "targets_total": len(targets),
        "stability": stability,
        "stability_range": {"warned_pct_min": min(rates) if rates else None,
                            "warned_pct_max": max(rates) if rates else None,
                            "periods": len(stability)},
        "definitions": {
            "warned_rate": f"Share of {nouns['owners']} whose score is moderate, high or critical.",
            "high_or_critical_rate": f"Share of {nouns['owners']} whose score is high or critical.",
            "already_bad_capture": (f"Of the {nouns['owners']} already bad (any {nouns['exposure']} 90+ "
                                    "days past due, Stage 3 or in default), the share that are warned."),
            "forward_risk": (f"Warned {nouns['owners']} that are not yet bad: the population the "
                             "warning exists to find."),
        },
        "backtest": {"available": False,
                     "statement": ("No backtest, AUC, Gini, KS or default-prediction result exists for "
                                   "this rule set, so none is shown. The figures above describe how the "
                                   "rules sort today's book, not how well they predict default.")},
    }


def _parity(domain_id: str, chosen: str, rules: list[dict[str, Any]]) -> dict[str, Any]:
    """Does the score the release carries equal the live rules applied now?"""
    spec = rd.domain_spec(domain_id)
    score = " + ".join(f"(CASE WHEN {r['technical']['expression']} THEN {r['weight']} ELSE 0 END)"
                       for r in rules if r["live"]) or "0"
    try:
        r = rd.q(f"""SELECT COUNT(*) AS n,
                            SUM(CASE WHEN COALESCE(ews_score, 0) <> ({score}) THEN 1 ELSE 0 END) AS diff,
                            string_agg(DISTINCT ews_ruleset_version, ', ') AS scored_with
                     FROM {rd.exposure(domain_id)} WHERE "{spec['period']}" = ?""", [chosen])[0]
        return {"exposures": int(r["n"]), "differ": int(r["diff"] or 0),
                "scored_with": r["scored_with"] or "", "checked": True}
    except Exception as exc:  # noqa: BLE001
        return {"exposures": None, "differ": None, "scored_with": "", "checked": False,
                "error": str(exc).splitlines()[0][:200]}


def _limitations(domain_id: str, rules: list[dict[str, Any]], sources: list[dict[str, Any]],
                 parity: dict[str, Any]) -> list[dict[str, str]]:
    nouns = _nouns(domain_id)
    out = [
        {"key": "weights", "title": "Weights are severity weights, not fitted coefficients",
         "text": ("Each rule's weight was set by judgement and calibrated against simple targets "
                  "(how many are warned, how many are high or critical, whether every already-bad "
                  f"{nouns['owner']} is warned). It is not a statistical coefficient, it is not a "
                  "probability, and the score is not a probability of default.")},
        {"key": "no_backtest", "title": "No backtest or discrimination statistics",
         "text": ("No backtest, AUC, Gini or KS result exists for this rule set. The performance "
                  "section shows how the rules sort the book, not how well they predict future "
                  "default.")},
        {"key": "already_bad_in_scope", "title": "Already-bad names are on the warning list",
         "text": (f"Rules such as days past due and Stage 3 / default also fire on {nouns['owners']} "
                  "that are already bad, so the warning list mixes names to watch with names "
                  "already in workout. 'Forward risk' isolates the ones still performing; the "
                  "already-bad capture shows coverage, not foresight.")},
        {"key": "snapshot", "title": "A period-end snapshot, not a live feed",
         "text": (f"Rules are evaluated once per {nouns['period']} on the published release. "
                  f"Anything that happens between {nouns['period']}-ends is not seen until the "
                  "next release.")},
    ]
    for r in rules:
        if not r["live"]:
            why = r["not_live_reason"]
            if r["limitation"]:
                why = f"{why} {r['limitation']}".strip()
            out.append({"key": f"not_live:{r['id']}", "title": f"{r['id']} ({r['name']}) is not live",
                        "text": why or "The rule cannot be evaluated on this release."})
        elif r["proxy"] or r["limitation"]:
            out.append({"key": f"proxy:{r['id']}", "title": f"{r['id']} is a stand-in (proxy)",
                        "text": r["limitation"] or "This rule is a governed stand-in for a signal "
                                                   "the release does not publish directly."})
        if not r["catalogued"]:
            out.append({"key": f"uncatalogued:{r['id']}",
                        "title": f"{r['id']} is not yet described in the signal catalogue",
                        "text": ("It is scored, but its source and risk layer are not yet recorded; "
                                 "it is shown under Bank Internal, layer 'Other'.")})
    for s in sources:
        if not s["connected"]:
            out.append({"key": f"source:{s['key']}", "title": f"{s['label']}: no live rule",
                        "text": s["absent_because"]})
    if parity.get("checked") and parity.get("differ"):
        out.append({"key": "score_parity", "title": "Release scores lag the live rule set",
                    "text": (f"On {parity['differ']:,} of {parity['exposures']:,} {nouns['exposures']} the "
                             f"score the release carries (scored with {parity['scored_with']}) differs "
                             "from the live rules applied now. Bands and performance use the release "
                             "score; per-rule counts use the live rules. The release needs rebuilding.")})
    return out


def _version_log(domain_id: str) -> list[dict[str, Any]]:
    versions = list(ews.RULESETS.items())
    out = []
    for i, (v, rs) in enumerate(versions):
        rules = rs["rules"].get(domain_id, [])
        mod, high, crit = rs["band_floors"][domain_id]
        prev = versions[i + 1][1]["rules"].get(domain_id, []) if i + 1 < len(versions) else None
        changes: dict[str, list[str]] = {"added": [], "removed": [], "reweighted": [], "redefined": []}
        if prev is not None:
            before = {r["id"]: r for r in prev}
            after = {r["id"]: r for r in rules}
            changes["added"] = [k for k in after if k not in before]
            changes["removed"] = [k for k in before if k not in after]
            for k in after:
                if k in before:
                    if after[k]["weight"] != before[k]["weight"]:
                        changes["reweighted"].append(f"{k} {before[k]['weight']}→{after[k]['weight']}")
                    if after[k]["sql"] != before[k]["sql"]:
                        changes["redefined"].append(k)
        out.append({"version": v, "status": rs["status"], "effective": rs["effective"],
                    "change": rs["change"],
                    "band_floors": {"critical": crit, "high": high, "moderate": mod},
                    "rules_total": len(rules),
                    "rules": [{"id": r["id"], "label": r["label"], "weight": r["weight"], "sql": r["sql"]}
                              for r in rules],
                    "changes": changes if prev is not None else None,
                    "current": v == ews.RULESET_VERSION})
    return out


# ---------------------------------------------------------------- the card

def model_card(domain_id: str, period: str = "") -> dict[str, Any]:
    spec = rd.domain_spec(domain_id)
    nouns = _nouns(domain_id)
    chosen, prior, all_periods, window = _period_window(domain_id, period)
    available = set(rd.columns(domain_id))
    exp = rd.exposure(domain_id)

    stats = _owner_stats(domain_id, window)
    now = stats.get(chosen, {})
    size = rd.q(f'SELECT COUNT(*) AS exposures, COUNT(DISTINCT "{spec["owner_key"]}") AS owners, '
                f'SUM(ead_sar_mn) AS ead FROM {exp} WHERE "{spec["period"]}" = ?', [chosen])[0]
    sources, rules = _sources(domain_id, chosen, available)
    parity = _parity(domain_id, chosen, rules)
    (crit, _), (high, _), (mod, _), _ = ews.bands(domain_id)

    summary = {
        "name": f"Early Warning rule set — {nouns['book']}",
        "model_id": cat.ACTIVE_MODEL["id"],
        "kind": "Deterministic rule set (scorecard of yes/no rules)",
        "purpose": (f"Flags {nouns['owners']} who show early signs of financial stress, so the "
                    "relationship, credit and collections teams can review them before they "
                    "default. It ranks who to look at first; it does not decide credit, price "
                    "risk or set provisions."),
        "intended_users": "Credit risk, relationship managers, collections and the credit committee.",
        "not_for": ("Credit approval or pricing, IFRS 9 staging or ECL, regulatory capital, or any "
                    "decision about an individual without a person reviewing the evidence."),
        "how_it_works": (f"Every {nouns['period']} each {nouns['exposure']} is checked against "
                         f"{len(rules)} yes/no rules (for example, payments overdue, limit almost fully "
                         "used, or the bank's own rating falling). Each rule that is true adds its "
                         f"weight to a score. A {nouns['owner']}'s score is the highest score among "
                         f"its {nouns['exposures']}. The score is then cut into bands: {crit} or more "
                         f"is critical, {high} to {crit - 1} high, {mod} to {high - 1} moderate and "
                         f"anything from 1 to {mod - 1} low. Moderate, high and critical {nouns['owners']} "
                         "are 'warned'. There is no statistical model, no machine learning and no "
                         "manual override: the same data always gives the same answer."),
        "scope": {"book": nouns["book"], "domain_id": domain_id,
                  "grain": spec["exposure_grain"], "owner_grain": spec["owner_grain"],
                  "owners_label": nouns["owners"], "exposures_label": nouns["exposures"],
                  "customers": int(size["owners"] or 0), "exposures": int(size["exposures"] or 0),
                  "exposure_sar_mn": float(size["ead"] or 0),
                  "frequency": "quarterly" if spec["period"] == "reporting_quarter" else "monthly",
                  "period_label": nouns["period"]},
        "release_id": spec["release_id"],
        "source_release_id": spec["source_release_id"],
        "ruleset_version": ews.RULESET_VERSION,
        "catalogue_version": cat.CATALOGUE_VERSION,
        "as_of": chosen,
        "prior_period": prior,
        "status": "active",
        "rules_total": len(rules),
        "rules_live": sum(r["live"] for r in rules),
        "sources_connected": sum(s["connected"] for s in sources),
        "sources_total": len(sources),
        "warned": now.get("warned", 0),
        "warned_pct": now.get("warned_pct", 0.0),
        "model_calls": 0,
    }

    return {
        "domain_id": domain_id,
        "period": chosen,
        "periods": all_periods,
        "stability_periods": window,
        "summary": summary,
        "sources": sources,
        "bands": _bands(domain_id, chosen, now),
        "performance": _performance(domain_id, chosen, window, stats),
        "limitations": _limitations(domain_id, rules, sources, parity),
        "version_log": _version_log(domain_id),
        "score_parity": parity,
        "model_calls": 0,
    }


__all__ = ["STABILITY_POINTS", "TARGETS", "model_card", "threshold"]
