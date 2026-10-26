"""Alternative structures and single-lever minimum changes over the full lever set (PLAN_R5 D4).

For a proposal (or any base term set) this module answers two questions the risk manager asks of a
deal that does not clear:

* **single_lever**: for every lever the proposal allows, the smallest change of that lever alone
  that clears the hurdle (SVA >= 0) without breaching a hard limit (or a soft one, unless escalation
  is allowed), inside the lever's market and policy bounds and the user's own bounds. A lever that
  cannot do it alone reports how far it gets at its bound.
* **alternatives**: 2-4 distinct structures that clear, each built from a recipe that mixes lever
  groups (pricing, risk mitigation, structure, protection, sell-down) and closed by the cheapest
  amount of one lever; each comes with its changed terms, RAROC, SVA, approval level and *why it
  works*: the lever contributions to the RAROC gain (Shapley values over the changed levers, so the
  bars add up exactly to the total gain).

Every returned figure is a full engine evaluation (`engine.analyse`); nothing is extrapolated.
"""
from __future__ import annotations

import itertools
import math
import time
from typing import Any, Callable

from backend.dealdesk import engine, levers, params

LABEL = {row["key"]: row["label"] for row in levers.catalogue()}
GROUP = {row["key"]: row["group"] for row in levers.catalogue()}
UNIT = {"margin_bps": "bps", "upfront_fee_bps": "bps", "commitment_fee_bps": "bps", "commission_bps": "bps", "prepayment_fee_bps": "bps",
        "cash_margin_pct": "%", "guarantee_coverage_pct": "%", "insurance_cover_pct": "%", "receivables_assignment_pct": "%",
        "hold_pct": "%", "tenor_years": "years", "grace_years": "years", "balloon_pct": "%", "funded_share_pct": "%",
        "deposit_pct": "% of limit"}  # Round D
#: distance weights by lever group, most costly to the client first (amount 5, tenor 4, margin 3, collateral 2, fees 1)
WEIGHT = {"amount": 5.0, "hold_pct": 1.5, "tenor_years": 4.0, "grace_years": 1.0, "amortisation": 1.5, "balloon_pct": 1.0,
          "margin_bps": 3.0, "upfront_fee_bps": 1.0, "commitment_fee_bps": 1.0, "commission_bps": 1.0, "prepayment_fee_bps": 0.7,
          "cash_margin_pct": 2.0, "collateral_ids": 2.0, "guarantee_id": 2.0, "guarantee_coverage_pct": 2.0, "insurance_cover_pct": 1.5,
          "receivables_assignment_pct": 1.2, "covenant_package": 1.0, "covenant_items": 0.8, "review_cycle_months": 0.6,
          "rate_type": 1.0, "facility_type": 3.0, "funded_share_pct": 2.0, "structure": 1.0, "cross_sell": 0.3,
          "deposit_pct": 2.0}  # Round D: a required deposit weighs as a cash margin
SCALE = {"margin_bps": 100.0, "upfront_fee_bps": 100.0, "commitment_fee_bps": 100.0, "commission_bps": 100.0, "prepayment_fee_bps": 100.0,
         "cash_margin_pct": 100.0, "guarantee_coverage_pct": 100.0, "insurance_cover_pct": 100.0, "receivables_assignment_pct": 100.0,
         "hold_pct": 100.0, "balloon_pct": 100.0, "funded_share_pct": 100.0, "grace_years": 5.0, "deposit_pct": 100.0}


class Ctx:
    def __init__(self, p: dict[str, Any], base: dict[str, Any] | None = None, fixed: dict[str, Any] | None = None,
                 bounds: dict[str, Any] | None = None, allow_soft: bool = False, el_view: str = "economic",
                 capital_basis: str | None = None):
        self.p = p
        self.base = engine.merge_terms(p, base)
        self.fixed = dict(fixed or {})
        self.bounds = {k: v for k, v in (bounds or {}).items() if k != "exclude_collateral_types"}
        self.exclude = set((bounds or {}).get("exclude_collateral_types", []))
        if self.exclude:
            self.base["collateral_ids"] = [c for c in self.base["collateral_ids"] if self._ctype(c) not in self.exclude]
        self.allow_soft = allow_soft
        self.kw = {"el_view": el_view, "capital_basis": capital_basis}
        self.evals = 0
        self._cache: dict[str, dict[str, Any]] = {}

    def _ctype(self, cid: str) -> str:
        return next((c["type"] for c in self.p["security"]["collateral"] if c["collateral_id"] == cid), "")

    def run(self, t: dict[str, Any]) -> dict[str, Any]:
        key = repr(sorted((k, repr(v)) for k, v in t.items()))
        if key not in self._cache:
            self.evals += 1
            a = engine.analyse(self.p, t, validate=False, **self.kw)
            hard = [c for c in a["constraints"] if c["status"] == "breach" and c["kind"] == "hard"]
            soft = [c for c in a["constraints"] if c["status"] == "breach" and c["kind"] == "soft"]
            ok = bool(a["metrics"]["clears_hurdle"]) and not hard and (self.allow_soft or not soft)
            self._cache[key] = {"a": a, "ok": ok, "hard": hard, "soft": soft}
        return self._cache[key]

    def rng(self, key: str) -> tuple[float, float] | None:
        b = levers.bounds(self.p, key)
        if not b:
            return None
        lo, hi = float(b["min"]), float(b["max"])
        if key in self.bounds:
            ulo, uhi = (float(x) for x in self.bounds[key])
            lo, hi = max(lo, ulo), min(hi, uhi)
        return (lo, hi) if lo <= hi + 1e-9 else None

    def free(self, key: str) -> bool:
        return key not in self.fixed

    def distance(self, t: dict[str, Any]) -> float:
        d = 0.0
        for k, w in WEIGHT.items():
            a, v = self.base.get(k), t.get(k)
            if a == v:
                continue
            if k == "amount":
                d += w * max(0.0, float(a) - float(v)) / float(a)
            elif k == "tenor_years":
                d += w * abs(float(a) - float(v)) / float(a)
            elif k in SCALE:
                d += w * abs(float(v) - float(a)) / SCALE[k]
            elif k == "guarantee_id":
                d += w * (0.5 if v else 0.0)
            elif isinstance(v, list):
                d += w * 0.25 * len(set(v) ^ set(a or []))
            else:
                d += w * 0.5
        return d


def _min_value(ctx: Ctx, t: dict[str, Any], key: str, lo: float, hi: float, increasing: bool, integer: bool = False,
               it: int = 30) -> float | None:
    """Smallest move from the base value toward the bound that makes the term set feasible.

    `increasing`: the lever helps as it rises (fees, cover, cash); otherwise as it falls (amount, hold,
    tenor). Bisection on the feasibility predicate, which is monotone along a helpful lever."""
    far = hi if increasing else lo
    near = float(t[key])

    def ok(x: float) -> bool:
        v = int(round(x)) if integer else x
        tt = {**t, key: v}
        if key == "tenor_years" and tt["grace_years"] >= v:
            tt["grace_years"] = max(0, int(v) - 1)
        return ctx.run(tt)["ok"]

    if ok(near):
        return near
    if not ok(far):
        return None
    if integer:
        rng = range(int(near) + 1, int(far) + 1) if increasing else range(int(near) - 1, int(far) - 1, -1)
        for v in rng:
            if ok(v):
                return float(v)
        return far
    a, b = near, far
    for _ in range(it):
        m = (a + b) / 2
        if ok(m):
            b = m
        else:
            a = m
    # round up to a sensible step (bps and % to 1 decimal)
    step = 0.1 if key not in ("amount",) else 0.01
    v = math.ceil(b / step) * step if increasing else math.floor(b / step) * step
    return v if ok(v) else b


def _with(t: dict[str, Any], **kv: Any) -> dict[str, Any]:
    tt = dict(t)
    tt.update(kv)
    if tt["grace_years"] >= tt["tenor_years"]:
        tt["grace_years"] = max(0, int(tt["tenor_years"]) - 1)
    return tt


def _best_guarantee(ctx: Ctx, t: dict[str, Any]) -> str | None:
    """The protection option that helps most at full cover (own guarantees first, then requested ones)."""
    best, best_s = None, -1e18
    for g in levers.guarantee_options(ctx.p):
        tt = _with(t, guarantee_id=g["id"], guarantee_coverage_pct=100)
        s = ctx.run(tt)["a"]["metrics"]["sva"]
        if s > best_s + 1e-12:
            best, best_s = g["id"], s
    return best


def _lever_specs(ctx: Ctx) -> list[tuple[str, bool, bool]]:
    """(key, increasing, integer) for the continuous / ordered levers this proposal allows."""
    t = ctx.base
    unfunded = t["facility_type"] in engine.UNFUNDED or float(t["funded_share_pct"]) == 0
    specs: list[tuple[str, bool, bool]] = []
    if not unfunded:
        specs.append(("margin_bps", True, False))
    specs.append(("upfront_fee_bps", True, False))
    if t["facility_type"] == "revolver" or (not unfunded and float(t["utilisation_pct"]) < 100):
        specs.append(("commitment_fee_bps", True, False))
    if unfunded or float(t["funded_share_pct"]) < 100:
        specs.append(("commission_bps", True, False))
    if t["facility_type"] == "term_loan":
        specs.append(("prepayment_fee_bps", True, False))
    specs += [("tenor_years", False, True), ("amount", False, False), ("hold_pct", False, False), ("cash_margin_pct", True, False),
              ("insurance_cover_pct", True, False), ("receivables_assignment_pct", True, False)]
    return [s for s in specs if ctx.free(s[0])]


def _row(ctx: Ctx, key: str, frm: Any, to: Any, tt: dict[str, Any] | None, note: str = "") -> dict[str, Any]:
    r = ctx.run(tt)["a"] if tt is not None else None
    out = {"lever": key, "label": LABEL.get(key, key), "group": GROUP.get(key, ""), "from": frm, "to": to,
           "unit": UNIT.get(key, ""), "clears_alone": tt is not None, "note": note}
    if key == "amount":
        out["unit"] = f"{ctx.base['currency']} m"
    if r is not None:
        m = r["metrics"]
        out.update({"lifetime_raroc": m["lifetime_raroc"], "sva": m["sva"], "approval": r["approval"]["level"],
                    "delta": (to - frm) if isinstance(to, (int, float)) and isinstance(frm, (int, float)) and not isinstance(to, bool) else None})
    return out


def single_lever(ctx: Ctx) -> list[dict[str, Any]]:
    t = ctx.base
    rows = []
    for key, inc, integer in _lever_specs(ctx):
        r = ctx.rng(key)
        if r is None:
            continue
        lo, hi = r
        if key == "tenor_years":
            lo = max(lo, 1)
        v = _min_value(ctx, t, key, lo, hi, inc, integer)
        if v is None:
            bound = hi if inc else lo
            rows.append(_row(ctx, key, t[key], None, None, note=f"Does not clear alone within its bound ({bound:g} {UNIT.get(key, '')})".strip()))
        else:
            vv = int(v) if integer else round(v, 2)
            tt = _with(t, **{key: vv})
            if not ctx.run(tt)["ok"]:
                tt = _with(t, **{key: v})
                vv = v
            rows.append(_row(ctx, key, t[key], vv, tt))
    # discrete levers: the cheapest option that clears alone
    if ctx.free("guarantee_id") or ctx.free("guarantee_coverage_pct"):
        best = None
        for g in levers.guarantee_options(ctx.p):
            tg = _with(t, guarantee_id=g["id"], guarantee_coverage_pct=0)
            v = _min_value(ctx, tg, "guarantee_coverage_pct", 0, 100, True)
            if v is not None and (best is None or v < best[1]):
                best = (g, v)
        if best:
            g, v = best
            tt = _with(t, guarantee_id=g["id"], guarantee_coverage_pct=round(v, 1))
            if not ctx.run(tt)["ok"]:
                tt = _with(t, guarantee_id=g["id"], guarantee_coverage_pct=v)
            row = _row(ctx, "guarantee_coverage_pct", float(t["guarantee_coverage_pct"]), tt["guarantee_coverage_pct"], tt,
                       note=g["label"])
            row["guarantee_id"] = g["id"]
            rows.append(row)
        else:
            rows.append(_row(ctx, "guarantee_coverage_pct", float(t["guarantee_coverage_pct"]), None, None,
                             note="No available or requestable guarantee clears alone"))
    for key, opts in (("amortisation", ["equal", "sculpted", "balloon", "bullet"]), ("review_cycle_months", [6, 3]),
                      ("rate_type", ["floating"])):
        if not ctx.free(key) or (key == "amortisation" and t["facility_type"] != "term_loan"):
            continue
        if all(o == t.get(key) for o in opts):
            continue
        hit = None
        for o in opts:
            if o == t.get(key):
                continue
            tt = _with(t, **{key: o})
            if key == "amortisation" and o == "balloon":
                tt["balloon_pct"] = levers.bounds(ctx.p, "balloon_pct")["max"]
            if ctx.run(tt)["ok"]:
                hit = (o, tt)
                break
        rows.append(_row(ctx, key, t.get(key), hit[0] if hit else None, hit[1] if hit else None,
                         note="" if hit else "No option clears alone"))
    rows += _deposit_row(ctx, t)  # Round D: "require a deposit" alone
    if ctx.free("covenant_items"):
        allc = list(params.rows("covenant_items")["items"])
        tt = _with(t, covenant_items=allc, covenant_package="enhanced")
        rows.append(_row(ctx, "covenant_items", t.get("covenant_items") or [], allc if ctx.run(tt)["ok"] else None,
                         tt if ctx.run(tt)["ok"] else None, note="" if ctx.run(tt)["ok"] else "The full covenant set does not clear alone"))
    return rows


def _deposit_row(ctx: Ctx, t: dict[str, Any]) -> list[dict[str, Any]]:
    """Round D: the smallest lien-marked cash deposit (% of the limit) that clears alone, on a funded facility."""
    funded = t["facility_type"] not in engine.UNFUNDED and float(t["funded_share_pct"]) > 0
    if not funded or not ctx.free("deposit_pct") or not ctx.free("deposit_type") or not ctx.free("cash_margin_pct"):
        return []
    hi = float(levers.bounds(ctx.p, "deposit_pct")["by_type"]["lien_cash"][1])
    if "deposit_pct" in ctx.bounds:
        hi = min(hi, float(ctx.bounds["deposit_pct"][1]))
    lien = t.get("deposit_type") == "lien_cash" and not float(t.get("deposit_amount") or 0)
    base = t if lien else _with(t, deposit_type="lien_cash", deposit_pct=0, deposit_amount=0, deposit_tenor_months=0, deposit_facility="")
    frm = float(base["deposit_pct"])
    if hi <= frm:
        return []
    v = _min_value(ctx, base, "deposit_pct", frm, hi, True)
    if v is None:
        return [_row(ctx, "deposit_pct", frm, None, None, note=f"A lien-marked cash deposit does not clear alone within its bound ({hi:g}% of the limit)")]
    vv = round(v, 2)
    tt = _with(base, deposit_pct=vv)
    if not ctx.run(tt)["ok"]:
        tt, vv = _with(base, deposit_pct=v), v
    row = _row(ctx, "deposit_pct", frm, vv, tt, note="Lien-marked cash deposit, maintained for the life of the facility")
    row["deposit_type"] = "lien_cash"
    return [row]


def contributions(ctx: Ctx, t_alt: dict[str, Any]) -> list[dict[str, Any]]:
    """Shapley contribution of each changed lever to the RAROC and SVA gain from the base to `t_alt`."""
    base = ctx.base
    keys = [k for k in engine.TERM_KEYS if base.get(k) != t_alt.get(k)]
    # tie dependent fields to their lever
    groups: dict[str, list[str]] = {}
    for k in keys:
        g = {"guarantee_coverage_pct": "guarantee_id", "balloon_pct": "amortisation", "grace_years": "tenor_years",
             # Round D: the deposit's fields move together
             "deposit_type": "deposit_pct", "deposit_amount": "deposit_pct", "deposit_tenor_months": "deposit_pct",
             "deposit_facility": "deposit_pct"}.get(k, k)
        if g == "tenor_years" and "tenor_years" not in keys:
            g = "grace_years"
        groups.setdefault(g, []).append(k)
    names = list(groups)
    if not names:
        return []

    def val(sub: tuple[str, ...]) -> tuple[float, float]:
        tt = dict(base)
        for n in sub:
            for k in groups[n]:
                tt[k] = t_alt[k]
        if tt["grace_years"] >= tt["tenor_years"]:
            tt["grace_years"] = max(0, int(tt["tenor_years"]) - 1)
        m = ctx.run(tt)["a"]["metrics"]
        return float(m["lifetime_raroc"]), float(m["sva"])

    n = len(names)
    contrib = {k: [0.0, 0.0] for k in names}
    if n <= 5:
        perms = list(itertools.permutations(names))
    else:
        perms = [tuple(names), tuple(reversed(names))]
    for perm in perms:
        prev = val(())
        cur: tuple[str, ...] = ()
        for k in perm:
            cur = cur + (k,)
            v = val(tuple(sorted(cur)))
            contrib[k][0] += v[0] - prev[0]
            contrib[k][1] += v[1] - prev[1]
            prev = v
    out = []
    for k in names:
        out.append({"lever": k, "label": LABEL.get(k, k), "group": GROUP.get(k, ""), "raroc_pts": contrib[k][0] / len(perms),
                    "sva": contrib[k][1] / len(perms), "from": base.get(k), "to": t_alt.get(k)})
    out.sort(key=lambda r: -r["raroc_pts"])
    return out


def _recipes(ctx: Ctx) -> list[tuple[str, str, dict[str, Any], str, bool, bool]]:
    """(label, why, preset changes, closing lever, increasing, integer)."""
    t = ctx.base
    p = ctx.p
    unfunded = t["facility_type"] in engine.UNFUNDED or float(t["funded_share_pct"]) == 0
    price = "commission_bps" if unfunded else "margin_bps"
    mb = {k: levers.bounds(p, k) for k in ("upfront_fee_bps", "margin_bps", "commission_bps")}
    out: list[tuple[str, str, dict[str, Any], str, bool, bool]] = []
    fee_hi = mb["upfront_fee_bps"]["max"]
    pre = {"upfront_fee_bps": max(float(t["upfront_fee_bps"]), round((float(t["upfront_fee_bps"]) + fee_hi) / 2))}
    if t["facility_type"] == "term_loan":
        pre["prepayment_fee_bps"] = 100
    out.append(("Fees first, then price", "Income: a higher arrangement fee and a prepayment fee, closed by the smallest price rise",
                pre, price, True, False))
    out.append(("Cash margin and price", "Exposure net of cash: lower RWA and LGD, closed by the smallest price rise",
                {"cash_margin_pct": 10}, price, True, False))
    g = _best_guarantee(ctx, t) if (ctx.free("guarantee_id")) else None
    if g:
        out.append(("Guarantee cover", "PD substitution on the covered part (and SA risk-weight relief where eligible)",
                    {"guarantee_id": g, "guarantee_coverage_pct": 0}, "guarantee_coverage_pct", True, False))
    out.append(("Credit insurance and assignment", "LGD and capital relief from an A-rated insurer plus assigned contract proceeds",
                {"receivables_assignment_pct": 50}, "insurance_cover_pct", True, False))
    if t["facility_type"] == "term_loan" and int(t["tenor_years"]) > 1:
        out.append(("Shorter tenor, sculpted repayment", "Lower average exposure, FTP and PD horizon",
                    {"amortisation": "sculpted", "covenant_items": ["dscr", "cash_sweep"]}, "tenor_years", False, True))
    out.append(("Sell-down and price", "Lower hold reduces concentration and capital; the arranger skim on the sold share adds fees",
                {"hold_pct": 70}, price, True, False))
    out.append(("Smaller amount", "Less exposure against the same fixed costs and limits", {}, "amount", False, False))
    return [r for r in out if ctx.free(r[3]) and all(ctx.free(k) for k in r[2])]


def _limits_ok(ctx: Ctx, t: dict[str, Any]) -> bool:
    r = ctx.run(t)
    return not r["hard"] and (ctx.allow_soft or not r["soft"])


def _limit_bases(ctx: Ctx) -> list[tuple[str, dict[str, Any]]]:
    """Where the ask breaches an amount-dependent limit: the largest amount, and the smallest hold (the
    client keeps the full amount, the bank sells the rest down), that pass every limit."""
    t = ctx.base
    if _limits_ok(ctx, t):
        return [("", t)]
    out = []
    for key in ("hold_pct", "amount"):
        if not ctx.free(key):
            continue
        r = ctx.rng(key)
        if r is None:
            continue
        lo = r[0]
        far = _with(t, **{key: lo})
        if not _limits_ok(ctx, far):
            continue
        a, b = float(t[key]), lo
        for _ in range(30):
            m = (a + b) / 2
            if _limits_ok(ctx, _with(t, **{key: m})):
                b = m
            else:
                a = m
        v = math.floor(b * 10) / 10 if key == "hold_pct" else math.floor(b * 100) / 100
        tv = _with(t, **{key: v})
        if not _limits_ok(ctx, tv):
            tv = _with(t, **{key: b})
        out.append(("Sell-down to the limit" if key == "hold_pct" else "Amount at the limit", tv))
    return out


def alternatives(ctx: Ctx, max_n: int = 4) -> list[dict[str, Any]]:
    found = []
    for prefix, t in _limit_bases(ctx):
        found += _alternatives_from(ctx, t, prefix)
    return _pick(found, max_n)


def _alternatives_from(ctx: Ctx, t: dict[str, Any], prefix: str) -> list[dict[str, Any]]:
    found = []
    tb = ctx.base
    if ctx.run(t)["ok"] and t is not tb:
        found.append(_alt(ctx, prefix, "The limit was the only obstacle", t))
    for label, why, pre, close, inc, integer in _recipes(ctx):
        if prefix and close in ("amount", "hold_pct"):
            continue
        tt = _with(t, **pre)
        r = ctx.rng(close) if close != "guarantee_coverage_pct" else (0.0, 100.0)
        if r is None:
            continue
        lo, hi = r
        v = _min_value(ctx, tt, close, lo, hi, inc, integer)
        if v is None:
            continue
        ta = _with(tt, **{close: (int(v) if integer else round(v, 1))})
        if not ctx.run(ta)["ok"]:
            ta = _with(tt, **{close: v})
        # drop secondary preset changes that turn out not to be needed (keep the structure lean); the
        # recipe's defining lever (its first preset) stays, or the recipe is not this structure
        keys = list(pre)
        for k in keys[1:]:
            trial = _with(ta, **{k: t[k]})
            if ctx.run(trial)["ok"]:
                ta = trial
        if keys and keys[0] != "guarantee_id" and ctx.run(_with(ta, **{keys[0]: t[keys[0]]}))["ok"]:
            continue
        if not ctx.run(ta)["ok"]:
            continue
        found.append(_alt(ctx, (prefix + ", " + label.lower()) if prefix else label, why, ta))
    return found


def _alt(ctx: Ctx, label: str, why: str, ta: dict[str, Any]) -> dict[str, Any]:
    t = ctx.base
    res = ctx.run(ta)
    a = res["a"]
    changes = [{"field": k, "label": LABEL.get(k, k), "group": GROUP.get(k, ""), "ask": t.get(k), "value": ta.get(k),
                "unit": UNIT.get(k, "") if k != "amount" else f"{t['currency']} m"}
               for k in engine.TERM_KEYS if t.get(k) != ta.get(k)]
    return {"label": label, "why": why, "terms": ta, "changes": changes, "distance": ctx.distance(ta),
            "metrics": a["metrics"], "approval": a["approval"], "soft_breaches": [c["name"] for c in res["soft"]],
            "contributions": contributions(ctx, ta)}


def _pick(found: list[dict[str, Any]], max_n: int) -> list[dict[str, Any]]:
    found = [f for f in found if f["changes"]]
    # distinct structures, closest first
    found.sort(key=lambda r: r["distance"])
    out, seen = [], set()
    for r in found:
        sig = tuple(sorted(c["field"] for c in r["changes"]))
        if sig in seen:
            continue
        seen.add(sig)
        out.append(r)
        if len(out) >= max_n:
            break
    return out


def analyse_alternatives(p: dict[str, Any], terms: dict[str, Any] | None = None, fixed: dict[str, Any] | None = None,
                         bounds: dict[str, Any] | None = None, allow_soft: bool = False, el_view: str = "economic",
                         capital_basis: str | None = None) -> dict[str, Any]:
    t0 = time.time()
    ctx = Ctx(p, terms, fixed, bounds, allow_soft, el_view, capital_basis)
    base = ctx.run(ctx.base)
    out = {"base_clears": base["ok"], "base_metrics": base["a"]["metrics"], "single_lever": [] if base["ok"] else single_lever(ctx),
           "alternatives": [] if base["ok"] else alternatives(ctx)}
    out["searched"] = {"evaluations": ctx.evals, "seconds": round(time.time() - t0, 2)}
    return out


__all__ = ["analyse_alternatives", "single_lever", "alternatives", "contributions", "Ctx"]
