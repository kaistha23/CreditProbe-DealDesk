"""One engine per fact (PLAN_R14 N2). Session E owns approval authority, the SVA basis and capacity; Session M owns the
current macro regime. Until their branches are merged, each adapter calls the engine when it is importable and
otherwise computes the same fact with the R13 engines, in the same output shape, and says which source answered
(`source`). Everything in Session F reads these four functions and nothing else for these facts.
"""
from __future__ import annotations

import functools
import importlib
import math
from typing import Any

from backend.dealdesk import engine

E_PENDING = "R13 engine (fallback: Session E's engine did not answer)"


def _try(mod: str, names: tuple[str, ...]):
    try:
        m = importlib.import_module(mod)
    except Exception:  # noqa: BLE001 - the engine is not on this branch yet
        return None
    for n in names:
        fn = getattr(m, n, None)
        if callable(fn):
            return fn
    return None


def _num(v: Any) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


# ------------------------------------------------------------------ approval authority (E: K18 K19 K25)

def approval(p: dict[str, Any], a: dict[str, Any], review: dict[str, Any] | None = None) -> dict[str, Any]:
    """{level, rank, rule, reasons, source}: the one approval authority for a deal on a structure.

    Session E's `approval_authority(deal, structure)` when present. Otherwise: the engine's DoA on the structure
    (exposure after the deal, rating, soft breaches), raised to the Review DoA when the Review's binding rule (a policy
    exception or a failed rule) needs a higher level; the rule that drove the level is named."""
    fn = _try("backend.dealdesk.approval", ("approval_authority",))
    if fn is not None:
        try:
            r = fn(p["proposal_id"], dict(a["terms"]))
        except Exception:  # noqa: BLE001 - fall back rather than fail the whole flow
            r = None
        if isinstance(r, dict) and r.get("level"):
            reasons = [x.get("detail") if isinstance(x, dict) else str(x) for x in (r.get("reasons") or [])]
            return {"level": r["level"], "rank": r.get("rank"), "rule": r.get("rule") or "", "reasons": [x for x in reasons if x],
                    "approvable": r.get("approvable", True), "expected_days": r.get("expected_days"),
                    "source": "Session E approval authority engine (backend.dealdesk.approval)"}
    ap = a["approval"]
    level, rank = ap["level"], int(ap.get("rank") or 0)
    rule = (ap.get("reasons") or [""])[0]
    reasons = list(ap.get("reasons") or [])
    if review and review.get("doa"):
        doa = review["doa"]
        b = doa.get("binding") or {}
        if b.get("basis") in ("exceptions", "rule") and int(doa.get("rank") or 0) > rank:
            level, rank = doa["level"], int(doa["rank"])
            rule = f"{b.get('detail', '')} ({b.get('basis')}) escalates to {level}"
            reasons.append(rule)
    if ap.get("hard_breaches"):
        reasons.append("Hard limit breached: " + ", ".join(x.replace("_", " ") for x in ap["hard_breaches"]))
    return {"level": level, "rank": rank, "rule": rule, "reasons": reasons, "source": E_PENDING}


# ------------------------------------------------------------------ SVA basis (E: one choice per tile type)

SVA_BASIS_LABEL = {"lifetime": "SVA over the life of the deal (PV at the hurdle)", "one_year": "SVA in year one"}


def sva(a: dict[str, Any], pid: str | None = None) -> dict[str, Any]:
    """{value, basis, label, lifetime, one_year, source}: both bases computed; `value` is the basis the Deal Desk tiles show."""
    fn = _try("backend.dealdesk.economics.core", ("economics",))
    if fn is not None and pid:
        try:
            r = fn(pid, dict(a["terms"]))
            basis = (r.get("basis") or {}).get("sva", "lifetime")
            sv = r.get("sva") or {}
            val = sv.get(basis)
            if val is not None:
                return {"value": float(val), "basis": basis, "label": "SVA " + str((r.get("basis") or {}).get("label") or SVA_BASIS_LABEL.get(basis, "")),
                        "lifetime": _num(sv.get("lifetime")), "one_year": _num(sv.get("one_year")),
                        "source": "Session E economics engine (backend.dealdesk.economics)"}
        except Exception:  # noqa: BLE001
            pass
    m = a["metrics"]
    h = float(m["hurdle"])
    y1 = a["pnl"][0] if a.get("pnl") else None
    one = None if y1 is None else float(y1["rap"]) - h * float(y1["capital"])
    return {"value": float(m["sva"]), "basis": "lifetime", "label": SVA_BASIS_LABEL["lifetime"], "lifetime": float(m["sva"]),
            "one_year": one, "source": E_PENDING}


# ------------------------------------------------------------------ capacity (E: K22)

WC_PRODUCTS = {"revolver", "working_capital", "trade", "overdraft", "lc", "performance_lg", "advance_payment_lg", "bid_bond", "murabaha_wc"}


def _detail(pid: str) -> dict[str, Any] | None:
    try:
        from backend.dealdesk.data import store
        rows = store.dd_read("dd_financials_detail", proposal_id=pid)
    except Exception:  # noqa: BLE001
        return None
    rows = [r for r in rows if r.get("entity_scope") == "standalone" and r.get("period_kind") == "audited"]
    return max(rows, key=lambda r: r.get("year") or 0) if rows else None


def capacity(p: dict[str, Any], a: dict[str, Any]) -> dict[str, Any]:
    """{method, capacity_sar_mn, ask_sar_mn, passes, formula, source}: what the obligor can carry for this product."""
    fn = _try("backend.dealdesk.capacity", ("capacity",))
    if fn is not None:
        try:
            r = fn(p["proposal_id"], dict(a["terms"]))
        except Exception:  # noqa: BLE001
            r = None
        if isinstance(r, dict) and r.get("capacity_sar_mn") is not None:
            label = {"borrowing_base": "Borrowing base (working-capital cycle)", "dscr_leverage": "DSCR and leverage"}.get(r.get("method"), r.get("method_label") or r.get("method") or "")
            return {"method": r.get("method_label") or label, "capacity_sar_mn": float(r["capacity_sar_mn"]), "ask_sar_mn": float(r.get("ask_sar_mn") or 0.0),
                    "passes": bool(r.get("within")), "formula": r.get("formula", ""), "severity": r.get("severity"),
                    "recommended_amount_sar_mn": _num(r.get("recommended_amount_sar_mn")),
                    "source": "Session E capacity engine (backend.dealdesk.capacity)"}
    t = a["terms"]
    fin = engine.latest_actual(p)
    ebitda, debt = float(fin["ebitda"]), float(fin["total_debt"])
    lim = next((float(c["limit"]) for c in a["constraints"] if c["name"] == "debt_ebitda"), 4.0)
    funded = float(a["metrics"]["amount_sar_mn"]) * (0.0 if t["facility_type"] in engine.UNFUNDED else float(t["funded_share_pct"]) / 100.0)
    lev_cap = max(0.0, lim * ebitda - debt)
    d = _detail(p["proposal_id"]) if t["facility_type"] in WC_PRODUCTS else None
    if d and d.get("ageing_0_90_mn") is not None:
        rec = 0.85 * float(d.get("ageing_0_90_mn") or 0) + 0.50 * float(d.get("ageing_91_180_mn") or 0)
        top1 = float(d.get("top1_receivable_pct") or 0) / 100.0
        conc = max(0.0, top1 - 0.10) * float(d.get("receivables_mn") or 0)
        inv = 0.60 * float(d.get("inventory_mn") or 0)
        other = float(d.get("bank_debt_st_mn") or 0)
        bb = rec - conc + inv
        cap = max(0.0, bb - other)
        return {"method": "Borrowing base (working-capital line)", "capacity_sar_mn": cap, "ask_sar_mn": funded,
                "passes": funded <= cap + 1e-9,
                "formula": (f"Eligible receivables {rec - conc:,.1f} (0–90 days at 85%, 91–180 at 50%, older nil, related parties nil, "
                            f"top customer above 10% nil) + inventory {inv:,.1f} (60%) − short-term bank debt already drawn {other:,.1f} "
                            f"= SAR {bb - other:,.1f}m ({d.get('period_label')}, dd_financials_detail). Trade payables are not deducted "
                            "in this interim method; Session E's capacity engine replaces it."),
                "source": E_PENDING}
    return {"method": "Leverage capacity (policy Debt/EBITDA)", "capacity_sar_mn": lev_cap, "ask_sar_mn": funded,
            "passes": funded <= lev_cap + 1e-9,
            "formula": f"{lim:.2f}x EBITDA {ebitda:,.1f} − debt {debt:,.1f} = SAR {lim * ebitda - debt:,.1f}m (latest audited year)",
            "source": E_PENDING}


# ------------------------------------------------------------------ counter-offer and findings (E: K19, K24)

def counter_offer(pid: str) -> dict[str, Any] | None:
    """Session E's counter-offer (Review counter-proposal with every critical/major finding cured or flagged, amount cut to
    capacity): {terms, headline, cures, not_curable}, or None when the engine is absent."""
    fn = _try("backend.dealdesk.findings", ("counter_offer",))
    if fn is None:
        return None
    try:
        r = fn(pid)
    except Exception:  # noqa: BLE001
        return None
    st = (r or {}).get("structure") or {}
    if not st.get("terms"):
        return None
    return {"terms": st["terms"], "headline": r.get("headline", ""), "cures": r.get("cures") or [], "not_curable": r.get("not_curable") or [],
            "changes": st.get("changes") or [], "amount_note": st.get("amount_note", "")}


def deal_findings(pid: str) -> dict[str, Any] | None:
    fn = _try("backend.dealdesk.findings", ("deal_findings",))
    if fn is None:
        return None
    try:
        return fn(pid)
    except Exception:  # noqa: BLE001
        return None


# ------------------------------------------------------------------ the current regime (M: K12)

@functools.lru_cache(maxsize=1)
def regime() -> dict[str, Any]:
    """{label, key, brent, month, chg_3m, chg_12m, percentile, vintage, source}: read first in every scenario answer."""
    # R14 x (N2, one engine per fact): session m's regime block (backend.scenarios.regime.current) is the one source; its
    # dated Brent level (daily spot, e.g. USD 108 on 19 Oct 2026) replaces the EIA monthly fallback below.
    try:
        from backend.scenarios import regime as RG
        r = RG.current()
        b = r.get("brent") or {}
        lat = b.get("latest") or {}
        if r.get("label") and lat.get("value") is not None:
            key = "high_oil_supply_shock" if r.get("regime") == "supply_shock_high_oil" else str(r.get("regime") or "normal")
            pct = b.get("percentile_35y")
            return {"label": str(r["label"])[:1].upper() + str(r["label"])[1:], "key": key, "brent": float(lat["value"]),
                    "month": str(lat.get("date") or ""), "chg_3m": None if b.get("change_3m_pct") is None else b["change_3m_pct"] / 100.0,
                    "chg_12m": None if b.get("change_12m_pct") is None else b["change_12m_pct"] / 100.0,
                    "percentile": None if pct is None else pct / 100.0, "vintage": r.get("vintage_line") or "",
                    "source": "Session m current regime (backend/scenarios/regime.py; dd_macro_regime)"}
    except Exception:  # noqa: BLE001 - fall back to the readers below
        pass
    for mod, names in (("backend.scenarios.regime", ("current_regime",)), ("backend.whatif_v5.domain.mev", ("current_regime",))):
        fn = _try(mod, names)
        if fn is not None:
            try:
                r = fn()
                if isinstance(r, dict) and r.get("label"):
                    return {**r, "source": r.get("source") or f"Session M ({mod})"}
            except Exception:  # noqa: BLE001
                pass
    try:
        from backend.whatif_v5.domain import mev
        s = mev.brent_monthly()
    except Exception:  # noqa: BLE001
        return {"label": "Regime not available", "key": "unknown", "brent": None, "month": None, "chg_3m": None, "chg_12m": None,
                "percentile": None, "vintage": "", "source": "What-If MEV relation not readable"}
    last_m = str(s.index[-1])
    last = float(s.iloc[-1])
    c3 = last / float(s.iloc[-4]) - 1 if len(s) > 3 else None
    c12 = last / float(s.iloc[-13]) - 1 if len(s) > 12 else None
    hist = s[s.index >= str(int(last_m[:4]) - 35)]
    pct = float((hist <= last).mean())
    if last >= 90 and (c12 or 0) >= 0.3:
        key, label = "high_oil_supply_shock", "Supply-shock high-oil regime"
    elif (c12 or 0) <= -0.3:
        key, label = "oil_slump", "Oil-slump regime"
    else:
        key, label = "normal", "Normal oil regime"
    return {"label": label, "key": key, "brent": last, "month": last_m, "chg_3m": c3, "chg_12m": c12, "percentile": pct,
            "vintage": f"Brent monthly (EIA) to {last_m}", "source": "whatif_v5 MEV relation (brent_monthly_eia)"}


def regime_line(r: dict[str, Any] | None = None) -> str:
    r = r or regime()
    if r.get("brent") is None:
        return r["label"] + "."
    bits = [f"Brent USD {r['brent']:,.0f} ({r['month']})"]
    if r.get("chg_12m") is not None:
        bits.append(f"{r['chg_12m'] * 100:+.0f}% in 12 months")
    if r.get("percentile") is not None:
        bits.append(f"{r['percentile'] * 100:.0f}th percentile of 35 years")
    return f"{r['label']}: " + ", ".join(bits) + "."
