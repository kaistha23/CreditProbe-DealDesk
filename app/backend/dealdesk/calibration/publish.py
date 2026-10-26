"""Publishing the calibration as a new `dd_stress_sensitivity` version through Session E's publisher (PLAN_R12 §0).

E's contract (docs/v5/R12_DATA_CONTRACT.md): one row per sector, driver and version, keyed sensitivity_id
("<sector>:<driver>"), version, reporting_quarter; E seeded version 1 from stress_scenarios.json (method "expert").
Calibrated v1 is **version 2** of the oil and non-oil GDP rows: `method = "regression"` with band, n and R² where the
data carries it, else the expert value again with `method = "expert"` and `source` saying "expert (fallback)" and why.
The other drivers (fixed-cost, largest-customer and project shares) stay at version 1. Re-publishing is idempotent
(`replace_where` on this version and owner), so M can re-run it after any merge:

    python -m backend.dealdesk.calibration.card --publish
"""
from __future__ import annotations

from datetime import date
from typing import Any

RELATION = "dd_stress_sensitivity"
VERSION = 2
OWNER = "Risk Models (calibrated v1, R12 Session T)"
CARD_REF = "docs/v5/R12_STRESS_CALIBRATION.md"
#: our driver keys -> the contract's
DRIVER = {"oil": "oil", "gdp_nonoil": "non_oil_gdp"}


def _store() -> Any | None:
    try:
        from backend.dealdesk.data import store  # Session E
    except Exception:  # noqa: BLE001 - E not merged
        return None
    return store if RELATION in __import__("backend.dealdesk.data.schema", fromlist=["RELATIONS"]).RELATIONS else None


def contract_rows(rows: list[dict[str, Any]], effective: str | None = None) -> list[dict[str, Any]]:
    """Our estimate rows in the contract's columns (nothing outside the contract)."""
    eff = effective or date.today().isoformat()
    out = []
    for r in rows:
        drv = DRIVER[r["driver"]]
        cal = not r["fallback"]
        if cal:
            src = (f"calibrated v1: {r['method']}; {r['data_relation']} {r['sample_from']}–{r['sample_to']}; "
                   f"partial R² {r['partial_r2']:.2f}; panel {r['panel_estimate']}"
                   + ("; extrapolated (shock beyond the sample's largest move)" if r["extrapolated"] else ""))
        else:
            src = (f"expert (fallback), calibrated v1: {r['reason']}; estimate {r['estimate']:+.4f} "
                   f"[{r['ci_low']:+.4f}, {r['ci_high']:+.4f}], R² {r['r2']:.2f}, n {r['n']}")
        out.append({
            "sensitivity_id": f"{r['sector']}:{drv}", "version": VERSION, "sector": r["sector"], "driver": drv,
            "beta": float(r["sensitivity"]),
            "band_low": float(r["ci_low"]) if cal else None, "band_high": float(r["ci_high"]) if cal else None,
            "method": "regression" if cal else "expert", "n_obs": int(r["n"]) if cal else None, "r2": float(r["r2"]) if cal else None,
            "source": src, "owner": OWNER, "effective_date": eff,
            "model_card_ref": f"{CARD_REF}#results-{'oil-brent-30' if drv == 'oil' else 'real-non-oil-gdp-3-points-below-plan'}",
        })
    return out


def publish_sensitivity(rows: list[dict[str, Any]], version: str, source: str, by: str) -> dict[str, Any]:
    st = _store()
    crow = contract_rows(rows)
    if st is None:
        import json

        from backend.dealdesk import paths
        d = paths.VAR / "calibration"
        d.mkdir(parents=True, exist_ok=True)
        f = d / f"{RELATION}.{version}.json"
        f.write_text(json.dumps({"relation": RELATION, "version": VERSION, "source": source, "rows": crow}, indent=1))
        return {"published": False, "relation": RELATION, "version": VERSION, "rows": len(crow),
                "via": "pending (Session E publisher not merged)", "file": str(f)}
    res = st.publish(RELATION, crow, mode="replace_where", actor=f"T:{by}", where={"version": VERSION, "owner": OWNER})
    return {"published": True, "relation": RELATION, "version": VERSION, "rows": len(crow), "via": "backend.dealdesk.data.publish",
            "calibration": version, "source": source, "result": res}


def latest(sector: str, driver: str) -> dict[str, Any] | None:
    """What the engine should read: the highest version of a sensitivity (falls back to the sector 'default')."""
    st = _store()
    if st is None:
        return None
    for sec in (sector, "default"):
        rows = st.dd_read(RELATION, sensitivity_id=f"{sec}:{DRIVER.get(driver, driver)}")
        if rows:
            return max(rows, key=lambda r: int(r["version"] or 0))
    return None
