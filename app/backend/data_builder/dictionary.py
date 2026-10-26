"""The data dictionary: type, unit and description for every column.

Order of precedence for a column's description:
  1. the relation's own `fields` override in the registry      (source "registry")
  2. the relation's own manifest (fields / dictionary)          (source "manifest")
  3. the same column in another domain's manifest               (source "manifest")
  4. `registry.CURATED`                                         (source "registry")
  5. a plain-English sentence generated from the column name    (source "derived")
Units come from the same sources, normalised, and otherwise from the column
name's suffix (_sar_mn -> SAR million, _pct -> %, _days -> days, _x -> x ...).
"""
from __future__ import annotations

import functools
import json
import re
from typing import Any

from backend.data_builder.paths import DATA, V5
from backend.data_builder.registry import CURATED, DOMAINS

# ---------------------------------------------------------------- units

_UNIT_ALIASES = {
    "rcy": "SAR million",  # reporting currency, manifests publish amount_scale "million"
    "percent": "%",
    "times": "x",
    "probability_0_1": "probability (0-1)",
    "percentage points": "percentage points",
    "index": "index",
    "count": "count",
    "days": "days",
    "months": "months",
    "notches": "notches",
}

_SUFFIX_UNITS: list[tuple[str, str]] = [
    ("_sar_mn", "SAR million"), ("_sar_k", "SAR thousand"), ("_sar", "SAR"),
    ("_pct", "%"), ("_pp", "percentage points"), ("_days", "days"), ("_months", "months"),
    ("_quarters", "quarters"), ("_x", "x"), ("_flag", "flag (0/1)"),
]


def unit_for(name: str, given: str | None, logical_type: str) -> str:
    if logical_type == "flag":
        return "flag (0/1)"
    if given:
        return _UNIT_ALIASES.get(given.strip().lower(), given.strip())
    for suffix, unit in _SUFFIX_UNITS:
        if name.endswith(suffix):
            return unit
    if name.startswith("pd_"):
        return "probability (0-1)"
    return ""


def logical_type(name: str, storage: str) -> str:
    s = storage.upper()
    if name.endswith("_flag") and ("INT" in s or s == "BOOLEAN"):
        return "flag"
    if s == "BOOLEAN":
        return "flag"
    if "INT" in s:
        return "integer"
    if any(t in s for t in ("DOUBLE", "FLOAT", "DECIMAL", "REAL", "NUMERIC")):
        return "number"
    if "DATE" in s or "TIME" in s:
        return "date"
    return "text"


# ---------------------------------------------------------------- manifests

def _load(rel_path: str) -> dict[str, Any]:
    path = (V5 / rel_path).resolve()
    if DATA not in path.parents or not path.is_file():
        return {}
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


@functools.cache
def manifest_entries(rel_path: str, kind: str, relation_file: str) -> dict[str, dict[str, str]]:
    """{column: {description, unit, label}} from one manifest, for one relation file."""
    m = _load(rel_path)
    out: dict[str, dict[str, str]] = {}
    if kind == "cockpit":
        stem = relation_file.rsplit("/", 1)[-1].removesuffix(".parquet")
        for rel in m.get("relations", []):
            if rel.get("relation") != stem:
                continue
            for f in rel.get("fields", []):
                out[f["name"]] = {"description": f.get("description", ""), "unit": f.get("unit", ""),
                                  "label": f.get("label", "")}
    elif kind == "external":
        for name, f in (m.get("dictionary") or {}).items():
            out[name] = {"description": f.get("description", ""), "unit": f.get("unit", ""), "label": ""}
    return out


@functools.lru_cache(maxsize=1)
def global_entries() -> dict[str, dict[str, str]]:
    """Every column documented by any manifest in the registry (first one wins)."""
    out: dict[str, dict[str, str]] = {}
    for dom in DOMAINS.values():
        for spec in dom["relations"].values():
            if spec.get("manifest") and spec.get("manifest_kind") in ("cockpit", "external"):
                for name, entry in manifest_entries(spec["manifest"], spec["manifest_kind"], spec["path"]).items():
                    if entry.get("description") and name not in out:
                        out[name] = entry
    return out


# ---------------------------------------------------------------- derived words

_WORDS = {
    "id": "identifier", "dpd": "days past due", "ead": "exposure at default", "ecl": "expected credit loss",
    "pd": "probability of default", "lgd": "loss given default", "ltv": "loan-to-value", "pit": "point-in-time",
    "ttc": "through-the-cycle", "sar": "", "mn": "", "k": "", "pct": "", "pp": "", "x": "", "flag": "",
    "q": "this quarter", "3m": "last 3 months", "6m": "last 6 months", "12m": "12 months", "ews": "Early Warning",
    "ebitda": "EBITDA", "ebit": "EBIT", "dscr": "debt service cover", "sicr": "significant increase in credit risk",
    "bnpl": "BNPL", "num": "number of", "n": "count",
}


def derived_description(name: str, ltype: str, unit: str) -> str:
    tokens = [t for t in re.split(r"_+", name) if t]
    words = [_WORDS.get(t, t) for t in tokens]
    phrase = " ".join(w for w in words if w).strip() or name
    phrase = phrase[0].upper() + phrase[1:]
    if ltype == "flag":
        return f"1 when {phrase.lower()} applies to this row, otherwise 0."
    if tokens and tokens[-1] == "id":
        return f"{phrase}: the {' '.join(words[:-1]) or 'row'} this row refers to."
    if unit and unit not in ("count", "flag (0/1)"):
        return f"{phrase}, in {unit}."
    return f"{phrase}."


def describe(spec: dict[str, Any], name: str, storage: str) -> dict[str, Any]:
    ltype = logical_type(name, storage)
    own = spec.get("fields", {}).get(name)
    entry: dict[str, str] | None = None
    source = "derived"
    if own:
        entry, source = own, "registry"
    elif spec.get("manifest") and spec.get("manifest_kind") in ("cockpit", "external"):
        e = manifest_entries(spec["manifest"], spec["manifest_kind"], spec["path"]).get(name)
        if e and e.get("description"):
            entry, source = e, "manifest"
    if entry is None and name in global_entries():
        entry, source = global_entries()[name], "manifest"
    if entry is None and name in CURATED:
        entry, source = CURATED[name], "registry"
    unit = unit_for(name, (entry or {}).get("unit"), ltype)
    description = (entry or {}).get("description") or derived_description(name, ltype, unit)
    label = (entry or {}).get("label") or name.replace("_", " ").capitalize()
    return {"name": name, "label": label, "type": ltype, "storage_type": storage, "unit": unit,
            "description": description, "source": source,
            "key": name in spec["key_columns"], "period": name == spec.get("period_column")}
