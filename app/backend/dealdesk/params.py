"""Versioned parameter tables: seeded defaults (data/dealdesk/params/v1), Admin edits (var/dealdesk/params).

Every table carries its owner, version, effective date and approver. An edit never changes a
file in place: it validates the new rows and writes the next version, recording who and why.
`current()` is the set in force; `versions()` is what every trace records.
"""
from __future__ import annotations

import copy
import json
import threading
from datetime import datetime, timezone
from typing import Any

from backend.dealdesk import paths
from backend.dealdesk.seed import GRADES

_LOCK = threading.Lock()
_CACHE: dict[str, Any] = {}
REQUIRED = ("pd_master_scale", "pd_migration", "lgd", "ccf", "sa_risk_weights", "capital", "ftp", "opex", "returns",
            "risk_appetite", "market_bounds", "doa", "covenant_packages", "structures", "stress",
            "pricing_behaviour", "credit_protection", "covenant_items", "relationship")
OWNERS = {"Treasury", "Finance", "Risk Models", "CFO", "Risk", "Shariah and Risk"}


class ParamError(ValueError):
    def __init__(self, table: str, errors: list[str]):
        super().__init__(f"{table}: " + "; ".join(errors))
        self.table = table
        self.errors = errors


def _seed_dir():
    return paths.params_dir() / "v1"


def _edit_dir():
    return paths.VAR / "params"


def _load_all() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for name in REQUIRED:
        p = _seed_dir() / f"{name}.json"
        if not p.exists():
            raise ParamError(name, [f"seed file missing ({p}); run ops/dealdesk_build.py"])
        out[name] = json.loads(p.read_text())
        d = _edit_dir() / name
        if d.exists():
            vs = sorted(d.glob("v*.json"), key=lambda q: int(q.stem[1:]))
            if vs:
                out[name] = json.loads(vs[-1].read_text())
    return out


def current() -> dict[str, dict[str, Any]]:
    with _LOCK:
        if not _CACHE:
            tabs = _load_all()
            for name, tab in tabs.items():
                errs = validate(name, tab)
                if errs:
                    raise ParamError(name, errs)
            _CACHE.update(tabs)
        return _CACHE


def reload() -> None:
    with _LOCK:
        _CACHE.clear()


def table(name: str) -> dict[str, Any]:
    tabs = current()
    if name not in tabs:
        raise KeyError(name)
    return tabs[name]


def rows(name: str) -> Any:
    return table(name)["rows"]


def versions() -> dict[str, str]:
    return {k: v["version"] for k, v in current().items()}


def version_tag() -> str:
    vs = versions()
    return "v1" if all(v == "v1" for v in vs.values()) else "+".join(f"{k}:{v}" for k, v in sorted(vs.items()) if v != "v1")


# ------------------------------------------------------------------ validation

def _prob(x: Any) -> bool:
    return isinstance(x, (int, float)) and 0.0 <= float(x) <= 1.0


def validate(name: str, tab: dict[str, Any]) -> list[str]:
    errs: list[str] = []
    for k in ("name", "owner", "version", "effective_from", "rows"):
        if k not in tab:
            errs.append(f"missing '{k}'")
    if errs:
        return errs
    if tab["owner"] not in OWNERS:
        errs.append(f"owner '{tab['owner']}' is not one of {sorted(OWNERS)}")
    r = tab["rows"]
    if name == "pd_master_scale":
        got = [x.get("rating") for x in r]
        if got != GRADES:
            errs.append("ratings must be the global order AAA..C")
        pds = [x.get("pd_ttc") for x in r]
        if not all(_prob(p) and p > 0 for p in pds):
            errs.append("every pd_ttc must be in (0, 1]")
        elif any(b < a for a, b in zip(pds, pds[1:])):
            errs.append("pd_ttc must not fall from a better to a worse grade")
    elif name == "pd_migration":
        if [x.get("from") for x in r] != GRADES:
            errs.append("rows must be the grades AAA..C in order")
        for x in r:
            to = x.get("to", {})
            if set(to) != set(GRADES + ["D"]):
                errs.append(f"{x.get('from')}: columns must be every grade and D")
                continue
            if any(not _prob(v) for v in to.values()):
                errs.append(f"{x.get('from')}: probabilities must be in [0, 1]")
            if abs(sum(to.values()) - 1.0) > 1e-6:
                errs.append(f"{x.get('from')}: row sums to {sum(to.values()):.6f}, not 1")
    elif name == "lgd":
        if not (_prob(r.get("floor")) and all(_prob(v) for v in r.get("unsecured", {}).values())):
            errs.append("floor and unsecured LGDs must be in [0, 1]")
        for k, c in r.get("collateral", {}).items():
            if not _prob(c.get("haircut")) or float(c.get("recovery_years", -1)) < 0:
                errs.append(f"collateral {k}: haircut in [0, 1], recovery_years >= 0")
        if any(not (0.5 <= float(v) <= 1.5) for v in r.get("structure", {}).values()):
            errs.append("structure multipliers must be in [0.5, 1.5]")
    elif name == "ccf":
        for k, v in r.items():
            if not (_prob(v.get("regulatory")) and _prob(v.get("economic"))):
                errs.append(f"{k}: CCFs must be in [0, 1]")
    elif name == "capital":
        if r.get("basis") not in ("regulatory", "economic", "max"):
            errs.append("basis must be regulatory, economic or max")
        if not (0.08 <= float(r.get("capital_ratio_target", 0)) <= 0.30):
            errs.append("capital_ratio_target must be in [8%, 30%]")
        if float(r.get("tier1_sar_mn", 0)) <= 0:
            errs.append("tier1_sar_mn must be positive")
        ec = r.get("economic", {})
        if not (0.9 <= float(ec.get("confidence", 0.999)) < 1.0):
            errs.append("economic.confidence must be in [0.9, 1)")
        if not (0.0 < float(ec.get("correlation_min", 0.12)) <= float(ec.get("correlation_max", 0.24)) < 1.0):
            errs.append("economic correlation bounds must satisfy 0 < min <= max < 1")
    elif name == "ftp":
        n = len(r.get("tenors", []))
        for cur in ("SAR", "USD"):
            if len(r.get("base", {}).get(cur, [])) != n or len(r.get("liquidity_premium_bps", {}).get(cur, [])) != n:
                errs.append(f"{cur}: one base rate and one liquidity premium per tenor")
    elif name == "returns":
        if any(not (0.0 < float(v) < 0.5) for v in r.get("hurdle", {}).values()):
            errs.append("hurdle rates must be in (0, 50%)")
        if not _prob(r.get("zakat_rate")) or not _prob(r.get("ancillary_realisation")):
            errs.append("zakat_rate and ancillary_realisation must be in [0, 1]")
    elif name == "risk_appetite":
        for x in r:
            if x.get("kind") not in ("hard", "soft"):
                errs.append(f"{x.get('name')}: kind must be hard or soft")
    elif name == "market_bounds":
        for b, v in r.get("by_bucket", {}).items():
            for k, (lo, hi) in v.items():
                if lo > hi or lo < 0:
                    errs.append(f"{b}.{k}: range [{lo}, {hi}] is not valid")
    elif name == "doa":
        if [x.get("rank") for x in r] != sorted(x.get("rank") for x in r):
            errs.append("levels must be in ascending rank")
    return errs


def edit(name: str, new_rows: Any, user: str, reason: str) -> dict[str, Any]:
    """Validate and write the next version of a table. Returns the new table."""
    tab = copy.deepcopy(table(name))
    if not reason or not reason.strip():
        raise ParamError(name, ["a reason is required"])
    prev = tab["version"]
    num = int(prev[1:]) + 1 if prev.startswith("v") and prev[1:].isdigit() else 2
    tab.update({"rows": new_rows, "version": f"v{num}",
                "effective_from": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "approved_by": user, "edited": {"by": user, "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                                 "reason": reason.strip(), "previous": prev}})
    errs = validate(name, tab)
    if errs:
        raise ParamError(name, errs)
    d = _edit_dir() / name
    d.mkdir(parents=True, exist_ok=True)
    (d / f"v{num}.json").write_text(json.dumps(tab, indent=1))
    reload()
    return tab
