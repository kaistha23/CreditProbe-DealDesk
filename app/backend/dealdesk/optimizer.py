"""The Deal Desk optimiser (spec 3.6): closest-to-ask, maximum SVA, frontier, counter-offers,
minimum relaxation, binding constraints with shadow prices, stress and robustness.

Method
  1. Enumerate the discrete levers (tenor, grace, amortisation profile, structure, guarantee,
     collateral package, covenant package, cash margin, funded share), ordered by their own
     distance from the ask; a combination whose discrete distance already exceeds the best
     solution found is skipped (it cannot be closer).
  2. Solve the continuous part of each combination exactly:
       amount   every amount-dependent limit is linear in the amount at fixed other terms
                (EAD, RWA, debt service and funded debt all scale with it), so the largest
                feasible amount is read off one evaluation and verified;
       pricing  SVA is affine in the margin and in each fee (where gross income is positive),
                so the cheapest weighted price increase that brings SVA to zero is a one-
                constraint LP: fill the levers in order of SVA gained per unit of distance.
     Amount and pricing are iterated (DSCR depends on the margin) and the result is verified by
     the full engine; only verified points are kept (no solver-only numbers).
  3. Keep the feasible points; return the closest, the maximum SVA, the non-dominated frontier
     and named counter-offers. If nothing is feasible, relax one lever or limit at a time and
     report the minimum change that makes a structure feasible.
"""
from __future__ import annotations

import copy
import itertools
import math
import time
from typing import Any

import numpy as np

from backend.dealdesk import constraints as cons
from backend.dealdesk import engine, params
from backend.dealdesk.seed import bucket

DEFAULT_WEIGHTS = {"amount": 5.0, "tenor": 4.0, "margin": 3.0, "collateral": 2.0, "fees": 1.0}
A_DEPENDENT = ("single_name", "group_connected", "group_large_exposure", "sector_policy", "sector_appetite", "rating_bucket",
               "collateral_type", "ltv", "dscr", "debt_ebitda", "bu_rwa_budget", "bu_el_budget")
CASH_STEPS = (0, 10, 20, 30)
EPS = 1e-9


RANGE_KEYS = ("amount", "tenor_years", "margin_bps", "upfront_fee_bps", "commitment_fee_bps", "commission_bps", "cash_margin_pct",
              "deposit_pct")  # Round D: the "require a deposit" lever


def deposit_lever(ask: dict[str, Any], fixed: dict[str, Any] | None, bounds: dict[str, Any] | None) -> bool:
    """Round D: on a fully funded facility the optimiser's cash cover is a required lien-marked deposit (the Deposit requirement
    term) rather than a cash margin, which stays the LG/LC lever. Off when the user holds or bounds the cash margin or the deposit."""
    fixed, bounds = fixed or {}, bounds or {}
    if ask["facility_type"] in engine.UNFUNDED or float(ask["funded_share_pct"]) < 100:
        return False
    if "cash_margin_pct" in fixed or "cash_margin_pct" in bounds:
        return False
    return not any(k in fixed for k in ("deposit_type", "deposit_pct", "deposit_amount"))


def lien_pct(t: dict[str, Any]) -> float:
    """The lien-marked deposit as a % of the limit (0 when the deposit is operating balances or absent)."""
    if t.get("deposit_type") != "lien_cash":
        return 0.0
    amt = float(t.get("deposit_amount") or 0.0)
    return amt / float(t["amount"]) * 100.0 if amt > 0 and float(t["amount"]) > 0 else float(t.get("deposit_pct") or 0.0)


def split_bounds(bounds: dict[str, Any] | None) -> tuple[dict[str, list[float]], set[str]]:
    """User bounds: numeric [lo, hi] ranges for the RANGE_KEYS, and `exclude_collateral_types` (a list of
    collateral types that are not available, e.g. ["real_estate"]). Anything else is refused."""
    ranges: dict[str, list[float]] = {}
    exclude: set[str] = set()
    for k, v in (bounds or {}).items():
        if k == "exclude_collateral_types":
            if not isinstance(v, (list, tuple)) or not all(isinstance(x, str) for x in v):
                raise engine.TermsError([{"field": "bounds.exclude_collateral_types", "message": "a list of collateral types"}])
            exclude |= set(v)
        elif k in RANGE_KEYS:
            try:
                lo, hi = (float(x) for x in v)
            except (TypeError, ValueError):
                raise engine.TermsError([{"field": f"bounds.{k}", "message": "[low, high] as two numbers"}]) from None
            ranges[k] = [lo, hi]
        else:
            raise engine.TermsError([{"field": f"bounds.{k}", "message": f"one of {', '.join(RANGE_KEYS)}, exclude_collateral_types"}])
    return ranges, exclude


class Problem:
    """One optimisation request: the proposal, the ask, fixed variables, bounds, weights, options."""

    def __init__(self, p: dict[str, Any], fixed: dict[str, Any] | None = None, bounds: dict[str, Any] | None = None,
                 weights: dict[str, float] | None = None, allow_soft: bool = False, el_view: str = "economic",
                 capital_basis: str | None = None, relax: dict[str, Any] | None = None):
        self.p = p
        self.ask = engine.merge_terms(p, None)
        self.fixed = {k: v for k, v in (fixed or {}).items() if k in engine.TERM_KEYS}
        self.bounds, self.exclude_types = split_bounds(bounds)
        self.w = {**DEFAULT_WEIGHTS, **{k: float(v) for k, v in (weights or {}).items() if k in DEFAULT_WEIGHTS}}
        self.allow_soft = allow_soft
        self.kw = {"el_view": el_view, "capital_basis": capital_basis}
        self.relax = relax or {}
        self.evals = 0
        self.points: list[dict[str, Any]] = []
        self._cache: dict[str, dict[str, Any]] = {}
        mb = params.rows("market_bounds")
        bk = bucket(p["obligor"]["internal_rating"])
        b = mb["by_bucket"][bk]
        add = mb.get("sector_margin_addon_bps", {}).get(p["obligor"]["sector"], 0)
        self.market = {"margin_bps": [b["margin_bps"][0] + add, b["margin_bps"][1] + add],
                       "upfront_fee_bps": list(b["upfront_fee_bps"]), "commitment_fee_bps": list(b["commitment_fee_bps"]),
                       "commission_bps": list(b["commission_bps"])}
        if "margin_cap_bps" in self.relax:
            self.market["margin_bps"][1] = self.relax["margin_cap_bps"]
        self.min_share = float(self.relax.get("min_amount_share", mb.get("min_amount_share", 0.6)))
        self.fx = engine.fx(self.ask["currency"])
        self.dep = deposit_lever(self.ask, self.fixed, self.bounds)  # Round D

    # ------------------------------------------------------------ helpers
    def lim(self, key: str) -> tuple[float, float]:
        """Continuous range: market bounds widened to include the ask, narrowed by user bounds, pinned by fixed."""
        if key == "amount":
            lo, hi = self.min_share * self.ask["amount"], self.ask["amount"]
        elif key == "cash_margin_pct":
            lo, hi = 0.0, max(30.0, self.ask["cash_margin_pct"])
        elif key == "deposit_pct":  # Round D: lgd.collateral.lien_deposit.max_pct
            lien = params.rows("lgd")["collateral"].get("lien_deposit") or {}
            lo, hi = 0.0, max(float(lien.get("max_pct", 30.0)), lien_pct(self.ask))
        else:
            m = self.market[key]
            lo, hi = min(m[0], self.ask[key]), max(m[1], self.ask[key])
        if key in self.bounds:
            blo, bhi = (float(x) for x in self.bounds[key])
            if key == "amount":
                lo, hi = blo, bhi  # the user's amount range replaces the default (60%-100% of the ask)
            else:
                lo, hi = max(lo, blo), min(hi, bhi)
        if key in self.fixed:
            lo = hi = float(self.fixed[key])
        if lo > hi + EPS:
            raise engine.TermsError([{"field": f"bounds.{key}", "message": f"empty range [{lo:g}, {hi:g}]"}])
        return lo, hi

    def evaluate(self, t: dict[str, Any]) -> dict[str, Any]:
        key = repr(sorted((k, tuple(v) if isinstance(v, list) else v) for k, v in t.items()))
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        self.evals += 1
        a = engine.analyse(self.p, t, **self.kw)
        cs = a["constraints"]
        ignore = set(self.relax.get("ignore", ()))
        hard = [c for c in cs if c["status"] == "breach" and c["name"] not in ignore and (c["kind"] == "hard" or not self.allow_soft)]
        soft = [c for c in cs if c["status"] == "breach" and c["kind"] == "soft" and c["name"] not in ignore]
        hurdle_ok = a["metrics"]["sva"] >= -1e-7 or self.relax.get("hurdle_off")
        res = {"terms": a["terms"], "analysis": a, "metrics": a["metrics"], "blocking": hard, "soft": soft,
               "clears": bool(hurdle_ok and not hard),
               "feasible": bool(hurdle_ok and not hard and self.admissible(a["terms"])), "distance": self.distance(a["terms"])}
        self._cache[key] = res
        if res["feasible"]:
            self.points.append(res)
        return res

    def admissible(self, t: dict[str, Any]) -> bool:
        """Inside the user's request: fixed values held, no excluded collateral type."""
        for k, v in self.fixed.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                if abs(float(t[k]) - float(v)) > 1e-6:
                    return False
            elif k == "collateral_ids":
                if sorted(t[k]) != sorted(v):
                    return False
            elif t.get(k) != v:
                return False
        for k, (lo, hi) in self.bounds.items():
            if not (lo - 1e-6 <= float(t[k]) <= hi + 1e-6):
                return False
        return not any(self._ctype(c) in self.exclude_types for c in t["collateral_ids"])

    def distance(self, t: dict[str, Any]) -> float:
        a, w = self.ask, self.w
        d = w["amount"] * max(0.0, a["amount"] - t["amount"]) / a["amount"]
        d += w["tenor"] * max(0, a["tenor_years"] - t["tenor_years"]) / a["tenor_years"]
        d += w["tenor"] * 0.05 * ((t["grace_years"] != a["grace_years"]) + (t["amortisation"] != a["amortisation"] or t["balloon_pct"] != a["balloon_pct"]))
        rng = max(1.0, self.market["margin_bps"][1] - self.market["margin_bps"][0])
        d += w["margin"] * max(0.0, t["margin_bps"] - a["margin_bps"]) / rng
        items = {c["collateral_id"]: c for c in self.p["security"]["collateral"]}
        added = sum(items[c]["value"] * engine.fx(items[c].get("currency", "SAR")) for c in t["collateral_ids"] if c not in a["collateral_ids"])
        coll = added / (a["amount"] * self.fx) + max(0.0, t["cash_margin_pct"] - a["cash_margin_pct"]) / 100.0
        coll += max(0.0, lien_pct(t) - lien_pct(a)) / 100.0  # Round D: a required deposit costs the client as a cash margin
        g_add = (t["guarantee_coverage_pct"] if t.get("guarantee_id") else 0) - (a["guarantee_coverage_pct"] if a.get("guarantee_id") else 0)
        coll += max(0.0, g_add) / 100.0
        steps = {"none": 0, "standard": 1, "enhanced": 2}
        coll += 0.1 * max(0, steps[t["covenant_package"]] - steps[a["covenant_package"]])
        d += w["collateral"] * coll
        fees = sum(max(0.0, t[k] - a[k]) for k in ("upfront_fee_bps", "commitment_fee_bps", "commission_bps"))
        d += w["fees"] * (fees / 100.0 + 0.1 * (t["structure"] != a["structure"]) + 0.05 * (t.get("funded_share_pct") != a.get("funded_share_pct")))
        return float(d)

    # ------------------------------------------------------------ discrete combinations
    def options(self, key: str) -> list[Any]:
        a = self.ask
        if key in self.fixed:
            return [self.fixed[key]]
        ft = a["facility_type"]
        if key == "tenor_years":
            lo = max(1, math.ceil(a["tenor_years"] / 2))
            if "tenor_years" in self.bounds:
                b0, b1 = self.bounds["tenor_years"]
                out = [n for n in range(max(1, int(math.ceil(b0))), min(10, int(b1)) + 1)]
                if not out:
                    raise engine.TermsError([{"field": "bounds.tenor_years", "message": "no whole tenor in 1-10 inside the range"}])
                return out[::-1]
            return list(range(a["tenor_years"], lo - 1, -1))
        if key == "grace_years":
            return sorted({a["grace_years"], 0})[::-1] if ft == "term_loan" else [a["grace_years"]]
        if key == "profile":
            if ft != "term_loan":
                return [(a["amortisation"], a["balloon_pct"])]
            opts = [(a["amortisation"], a["balloon_pct"]), ("equal", 0), ("balloon", 25), ("balloon", 50)]
            return list(dict.fromkeys(opts))
        if key == "structure":
            allowed = params.rows("structures")[ft]
            mult = params.rows("lgd")["structure"]
            out = [a["structure"]]
            for s in sorted(allowed, key=lambda s: mult[s]):
                if mult[s] < mult[a["structure"]] and s not in out:
                    out.append(s)
            return out
        if key == "guarantee":
            out = [(a.get("guarantee_id"), a["guarantee_coverage_pct"] if a.get("guarantee_id") else 0)]
            for g in self.p["security"]["guarantees"]:
                if (g["guarantee_id"], g["coverage_pct"]) not in out:
                    out.append((g["guarantee_id"], g["coverage_pct"]))
            if a.get("guarantee_id") and (None, 0) not in out:
                out.append((None, 0))
            return out
        if key == "collateral":
            ok = {c["collateral_id"] for c in self.p["security"]["collateral"] if c["type"] not in self.exclude_types}
            base = [c for c in a["collateral_ids"] if c in ok]
            avail = sorted(ok - set(base))
            out = []
            for r in range(len(avail) + 1):
                for sub in itertools.combinations(avail, r):
                    out.append(sorted(base + list(sub)))
            return out
        if key == "covenant_package":
            order = ["none", "standard", "enhanced"]
            return order[order.index(a["covenant_package"]):]
        if key == "deposit":  # Round D: (type, % of limit): the ask's deposit, then lien-marked cash at the parameter's steps
            cur = (a.get("deposit_type") or "none", float(a.get("deposit_pct") or 0.0))
            if not self.dep:
                return [cur]
            lo, hi = self.lim("deposit_pct")
            lien = params.rows("lgd")["collateral"].get("lien_deposit") or {}
            have = lien_pct(a)
            steps = [float(x) for x in lien.get("steps_pct", (10, 20, 30)) if have < float(x) <= hi and float(x) >= lo]
            return [cur] + [("lien_cash", x) for x in steps]
        if key == "cash_margin_pct":
            if self.dep:  # Round D: the cash cover is the deposit on a funded facility
                return [a["cash_margin_pct"]]
            lo, hi = self.lim("cash_margin_pct")
            return sorted({min(max(a["cash_margin_pct"], lo), hi), *[c for c in CASH_STEPS if a["cash_margin_pct"] < c <= hi]})
        if key == "funded_share_pct":
            f = a["funded_share_pct"]
            if ft in engine.UNFUNDED or f in (0, 100):
                return [f]
            return [f] + [x for x in (f - 25, f + 25) if 0 < x < 100]
        raise KeyError(key)

    def combos(self) -> list[dict[str, Any]]:
        keys = ["tenor_years", "grace_years", "profile", "structure", "guarantee", "collateral", "covenant_package",
                "cash_margin_pct", "funded_share_pct", "deposit"]
        opts = {k: self.options(k) for k in keys}
        if "collateral_ids" in self.fixed:
            opts["collateral"] = [sorted(self.fixed["collateral_ids"])]
        if "guarantee_id" in self.fixed:
            gid = self.fixed["guarantee_id"]
            cov = float(self.fixed.get("guarantee_coverage_pct", next((g["coverage_pct"] for g in self.p["security"]["guarantees"]
                                                                       if g["guarantee_id"] == gid), 0)))
            opts["guarantee"] = [(gid, cov if gid else 0)]
        if "amortisation" in self.fixed:
            opts["profile"] = [(self.fixed["amortisation"], self.fixed.get("balloon_pct", self.ask["balloon_pct"]))]
        out = []
        for vals in itertools.product(*[opts[k] for k in keys]):
            c = dict(zip(keys, vals))
            t = copy.deepcopy(self.ask)
            t["tenor_years"] = int(c["tenor_years"])
            t["grace_years"] = min(int(c["grace_years"]), t["tenor_years"] - 1)
            t["amortisation"], t["balloon_pct"] = c["profile"]
            t["structure"] = c["structure"]
            t["guarantee_id"], t["guarantee_coverage_pct"] = c["guarantee"]
            t["collateral_ids"] = c["collateral"]
            t["covenant_package"] = c["covenant_package"]
            t["cash_margin_pct"] = c["cash_margin_pct"]
            t["funded_share_pct"] = c["funded_share_pct"]
            if c["deposit"] != (t.get("deposit_type") or "none", float(t.get("deposit_pct") or 0.0)):  # Round D
                t.update({"deposit_type": c["deposit"][0], "deposit_pct": c["deposit"][1], "deposit_amount": 0,
                          "deposit_tenor_months": 0, "deposit_facility": ""})
            for k, v in self.fixed.items():
                if k not in ("amount", "margin_bps", "upfront_fee_bps", "commitment_fee_bps", "commission_bps"):
                    t[k] = v
            if t["structure"] == "ijara" and not {self._ctype(x) for x in t["collateral_ids"]} & set(params.rows("structures")["ijara_requires"]):
                continue
            if t["grace_years"] >= t["tenor_years"]:
                continue
            out.append(t)
        uniq = {repr(sorted((k, tuple(v) if isinstance(v, list) else v) for k, v in t.items())): t for t in out}
        return sorted(uniq.values(), key=self.distance)

    def price_levers(self, t: dict[str, Any]) -> list[str]:
        """The prices that earn anything on this structure (margin on drawn, commitment fee on undrawn, commission on LG/LC)."""
        ft = t["facility_type"]
        funded = ft not in engine.UNFUNDED and float(t["funded_share_pct"]) > 0
        out = ["upfront_fee_bps"]
        if funded:
            out.append("margin_bps")
            if ft == "revolver" and float(t["utilisation_pct"]) < 100:
                out.append("commitment_fee_bps")
        if ft in engine.UNFUNDED or float(t["funded_share_pct"]) < 100:
            out.append("commission_bps")
        return out

    def best_value(self, name: str, max_seconds: float = 6.0) -> dict[str, Any] | None:
        """With `name` ignored and the amount at its minimum, the structure whose `name` value is best."""
        lo, _ = self.lim("amount")
        best, t0 = None, time.time()
        sign = -1.0 if name == "dscr" else 1.0  # dscr: higher is better
        for t in self.combos():
            if time.time() - t0 > max_seconds:
                break
            tt = {**t, "amount": lo}
            priced = self.price(tt)
            if priced is None:
                continue
            r = self.evaluate(priced)
            if not r["feasible"]:
                continue
            c = next(c for c in r["analysis"]["constraints"] if c["name"] == name)
            if best is None or sign * c["value"] < sign * best[1]["value"]:
                best = (r, c)
        return None if best is None else {"result": best[0], "constraint": best[1]}

    def _ctype(self, cid: str) -> str:
        return next(c["type"] for c in self.p["security"]["collateral"] if c["collateral_id"] == cid)

    # ------------------------------------------------------------ continuous solve for one combination
    def amount_max(self, t: dict[str, Any]) -> float | None:
        """Largest amount in range with every amount-dependent blocking limit passing (linear in the amount)."""
        lo, hi = self.lim("amount")
        r = self.evaluate({**t, "amount": hi})
        if not r["blocking"]:
            return hi
        A = hi
        for c in r["blocking"]:
            if c["name"] not in A_DEPENDENT:
                return None
            A = min(A, self._a_limit(c, hi))
        for _ in range(4):
            if A < lo - EPS:
                return None
            r = self.evaluate({**t, "amount": A})
            if not r["blocking"]:
                return A
            if any(c["name"] not in A_DEPENDENT for c in r["blocking"]):
                return None
            A2 = min(self._a_limit(c, A) for c in r["blocking"])
            A = min(A2, A * 0.999)
        return None

    def _a_limit(self, c: dict[str, Any], A: float) -> float:
        n, v, L = c["name"], c["value"], c["limit"]
        if n in ("single_name", "group_connected", "group_large_exposure"):
            per = c["deal"] / A
            return (L - c["before"]) / per if per > 0 else A
        if n in ("sector_policy", "sector_appetite", "rating_bucket", "collateral_type"):
            per = c["deal"] / A
            from backend.dealdesk import portfolio
            tot = portfolio.snapshot()["total_ead"]
            S = c["before"] * tot
            return max(0.0, (L * tot - S) / (per * (1 - L))) if per > 0 else A
        if n == "dscr":
            # dscr = E / (DS_existing + k A): k is read off this evaluation, the limit solved for A
            fin = engine.latest_actual(self.p)
            E, ds0 = float(fin["ebitda"]), float(fin["debt_service"])
            k = (E / v - ds0) / A if v > 0 else 0.0
            return max(0.0, (E / L - ds0) / k) if k > 0 else A
        if n == "debt_ebitda":
            fin = engine.latest_actual(self.p)
            per = (v * fin["ebitda"] - fin["total_debt"]) / A
            return max(0.0, (L * fin["ebitda"] - fin["total_debt"]) / per) if per > 0 else A
        if n in ("ltv", "bu_rwa_budget", "bu_el_budget"):
            return A * L / v if v > 0 else A
        return A

    def price(self, t: dict[str, Any]) -> dict[str, Any] | None:
        """Cheapest weighted price increase that makes SVA >= 0 (SVA is affine in each price)."""
        r = self.evaluate(t)
        if r["metrics"]["sva"] >= -1e-7:
            return t
        levers = []
        has_drawn = sum(row["drawn_avg"] for row in r["analysis"]["schedule"]) > 0
        has_undrawn = sum(row["undrawn_avg"] for row in r["analysis"]["schedule"]) > 0
        has_unf = sum(row["unfunded_avg"] for row in r["analysis"]["schedule"]) > 0
        rng = max(1.0, self.market["margin_bps"][1] - self.market["margin_bps"][0])
        for k, cost, use in (("margin_bps", self.w["margin"] / rng, has_drawn), ("upfront_fee_bps", self.w["fees"] / 100.0, True),
                             ("commitment_fee_bps", self.w["fees"] / 100.0, has_undrawn), ("commission_bps", self.w["fees"] / 100.0, has_unf)):
            if not use:
                continue
            lo, hi = self.lim(k)
            cur = float(t[k])
            if hi <= cur + EPS:
                continue
            step = min(50.0, hi - cur)
            r2 = self.evaluate({**t, k: cur + step})
            slope = (r2["metrics"]["sva"] - r["metrics"]["sva"]) / step
            if slope <= 0:
                continue
            levers.append((slope / cost, k, slope, cur, hi))
        levers.sort(reverse=True)
        gap = -r["metrics"]["sva"]
        tt = dict(t)
        for _, k, slope, cur, hi in levers:
            need = gap / slope
            take = min(need, hi - cur)
            tt[k] = cur + take
            gap -= take * slope
            if gap <= 1e-12:
                break
        if gap > 1e-9:
            return None
        # verify and correct the last lever (affine up to the operational-risk kink)
        for _ in range(4):
            rv = self.evaluate(tt)
            s = rv["metrics"]["sva"]
            if s >= -1e-7:
                return tt
            k = next((k for _, k, *_ in reversed(levers) if tt[k] > float(t[k])), None)
            if k is None:
                return None
            lo, hi = self.lim(k)
            slope = next(sl for _, kk, sl, *_ in levers if kk == k)
            tt[k] = min(hi, tt[k] + (-s) / slope * 1.000001 + 1e-6)
            if tt[k] >= hi - EPS and self.evaluate(tt)["metrics"]["sva"] < -1e-7:
                return None
        return tt if self.evaluate(tt)["metrics"]["sva"] >= -1e-7 else None

    def amount_candidates(self, t: dict[str, Any], a_max: float) -> list[float]:
        """Amounts below the largest feasible one worth trying: a grid down to the floor, and the edges of
        the real-estate LTV risk-weight bands (where the risk weight steps)."""
        lo, _ = self.lim("amount")
        if a_max <= lo + EPS:
            return []
        out = list(np.linspace(a_max, lo, 6)[1:])
        if self.p["obligor"].get("real_estate_finance"):
            re_v = sum(float(c.get("value") or 0) * engine.fx(c.get("currency", "SAR")) for c in self.p["security"]["collateral"]
                       if c["collateral_id"] in t["collateral_ids"] and c["type"] == "real_estate")
            f_share = float(t["funded_share_pct"]) / 100.0
            if re_v > 0 and f_share > 0:
                for b in params.rows("sa_risk_weights")["ipre_ltv"]:
                    a = b["max_ltv"] * re_v / f_share / self.fx * (1 - 1e-9)
                    if lo - EPS <= a < a_max:
                        out.append(a)
        return sorted(set(out), reverse=True)

    def _solve_at(self, tt: dict[str, Any], A: float) -> dict[str, Any] | None:
        tt = {**tt, "amount": A}
        for _ in range(4):
            priced = self.price(tt)
            if priced is None:
                return None
            r = self.evaluate(priced)
            if r["feasible"]:
                return r
            A2 = self.amount_max(priced)
            if A2 is None or A2 >= priced["amount"] - EPS:
                return None
            tt = {**priced, "amount": A2}
        return None

    def solve_combo(self, t: dict[str, Any]) -> dict[str, Any] | None:
        tt = dict(t)
        for k in ("margin_bps", "upfront_fee_bps", "commitment_fee_bps", "commission_bps"):
            lo, hi = self.lim(k)
            tt[k] = min(max(float(tt[k]), lo), hi)
        A = self.amount_max(tt)
        if A is None:
            return None
        r = self._solve_at(tt, A)
        if r is not None:
            return r
        # Pricing cannot close the gap at the largest amount: a smaller amount can (fixed costs aside, a
        # risk-weight band or a limit may step). Keep the closest verified point.
        best = None
        for a in self.amount_candidates(tt, A):
            r = self._solve_at(tt, a)
            if r is not None and (best is None or r["distance"] < best["distance"] - 1e-12):
                best = r
        return best

    # ------------------------------------------------------------ searches
    def closest(self, max_seconds: float = 20.0) -> dict[str, Any] | None:
        best = None
        t0 = time.time()
        for t in self.combos():
            if best is not None and self.distance(t) >= best["distance"] - 1e-12:
                break
            if time.time() - t0 > max_seconds:
                break
            r = self.solve_combo(t)
            if r is not None and (best is None or r["distance"] < best["distance"] - 1e-12):
                best = r
        return best

    def max_sva(self, max_seconds: float = 20.0) -> dict[str, Any] | None:
        best = None
        t0 = time.time()
        seen = set()
        for t in self.combos():
            if time.time() - t0 > max_seconds:
                break
            tt = dict(t)
            for k in self.price_levers(t):
                tt[k] = self.lim(k)[1]
            sig = repr(sorted((k, tuple(v) if isinstance(v, list) else v) for k, v in tt.items() if k != "amount"))
            if sig in seen:
                continue
            seen.add(sig)
            A = self.amount_max(tt)
            if A is None:
                continue
            for a in [A] + self.amount_candidates(tt, A):
                r = self.evaluate({**tt, "amount": a})
                if r["feasible"] and (best is None or r["metrics"]["sva"] > best["metrics"]["sva"] + 1e-12):
                    best = r
        return best

    def frontier(self) -> list[dict[str, Any]]:
        pts = sorted({(round(r["distance"], 10), round(r["metrics"]["sva"], 10)): r for r in self.points}.values(),
                     key=lambda r: (r["distance"], -r["metrics"]["sva"]))
        out, best_sva = [], -math.inf
        for r in pts:
            if r["metrics"]["sva"] > best_sva + 1e-12:
                out.append(r)
                best_sva = r["metrics"]["sva"]
        return out

    def sweep_frontier(self, base: dict[str, Any] | None, top: dict[str, Any] | None, n: int = 6) -> None:
        """Fill the frontier between closest and maximum SVA: raise each price toward its market maximum."""
        if base is None:
            return
        t = dict(base["terms"])
        for k in ("margin_bps", "upfront_fee_bps"):
            lo, hi = self.lim(k)
            for x in np.linspace(float(t[k]), hi, n)[1:]:
                self.evaluate({**t, k: float(x)})
        if top is not None:
            tt = dict(top["terms"])
            for x in np.linspace(float(tt["amount"]), float(base["terms"]["amount"]), 4)[1:-1]:
                self.evaluate({**tt, "amount": float(x)})


# ------------------------------------------------------------------ public functions

def _summary(r: dict[str, Any] | None, ask: dict[str, Any], label: str, fx: float) -> dict[str, Any] | None:
    if r is None:
        return None
    t = r["terms"]
    changes = []
    units = {"amount": f"{t['currency']} m", "tenor_years": "years", "grace_years": "years", "margin_bps": "bps",
             "upfront_fee_bps": "bps", "commitment_fee_bps": "bps", "commission_bps": "bps", "cash_margin_pct": "%",
             "guarantee_coverage_pct": "%", "balloon_pct": "%", "funded_share_pct": "%", "deposit_pct": "% of limit",
             "deposit_amount": f"{t['currency']} m", "deposit_tenor_months": "months"}
    for k in engine.TERM_KEYS:
        a, v = ask.get(k), t.get(k)
        if isinstance(a, float) or isinstance(v, float):
            if a is None or v is None or abs(float(a) - float(v)) > 1e-6:
                changes.append({"field": k, "ask": a, "value": v, "unit": units.get(k, "")})
        elif a != v:
            changes.append({"field": k, "ask": a, "value": v, "unit": units.get(k, "")})
    an = r["analysis"]
    return {"label": label, "terms": t, "metrics": an["metrics"], "distance": r["distance"], "changes": changes,
            "approval": an["approval"], "soft_breaches": [c["name"] for c in r["soft"]],
            "constraints": an["constraints"]}


def _binding(prob: Problem, r: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Constraints at (or within 1% of) their limit, with SVA gained per unit of relaxation."""
    if r is None:
        return []
    out = []
    t = r["terms"]
    base_sva = r["metrics"]["sva"]
    for c in r["analysis"]["constraints"]:
        if c["headroom"] is None or c["unit"] == "rating" or not isinstance(c["limit"], (int, float)):
            continue
        scale = abs(c["limit"]) if c["limit"] else 1.0
        if abs(c["headroom"]) <= 0.01 * scale + 1e-9 and c["name"] in A_DEPENDENT:
            # relax by 1% of the limit: the amount can grow by what the linear limit allows
            A0 = float(t["amount"])
            c2 = dict(c, limit=c["limit"] * (1.01 if c["name"] != "dscr" else 0.99))
            A1 = min(prob.lim("amount")[1] * 1.5, prob._a_limit(c2, A0))
            if A1 <= A0 + 1e-9:
                continue
            a1 = engine.analyse(prob.p, {**t, "amount": A1}, **prob.kw)
            dl = abs(c2["limit"] - c["limit"])
            out.append({"constraint": c["name"], "label": c["label"], "headroom": c["headroom"], "unit": c["unit"],
                        "shadow_price": (a1["metrics"]["sva"] - base_sva) / dl, "per": f"SVA SAR m per {c['unit']} of limit"})
    m_hi = prob.lim("margin_bps")[1]
    if abs(float(t["margin_bps"]) - m_hi) < 1e-6 and r["analysis"]["schedule"][0]["drawn_avg"] > 0:
        a1 = engine.analyse(prob.p, {**t, "margin_bps": m_hi + 10}, **prob.kw)
        out.append({"constraint": "market_margin_cap", "label": "Market margin cap", "headroom": 0.0, "unit": "bps",
                    "shadow_price": (a1["metrics"]["sva"] - base_sva) / 10.0, "per": "SVA SAR m per bp of margin"})
    if abs(r["metrics"]["sva"]) < 1e-6:
        out.append({"constraint": "hurdle", "label": "RAROC hurdle", "headroom": 0.0, "unit": "share",
                    "shadow_price": None, "per": "binding: SVA = 0"})
    return out


def _counter_offers(p: dict[str, Any], base_kw: dict[str, Any], ask: dict[str, Any], closest: dict[str, Any] | None,
                    fx: float) -> list[dict[str, Any]]:
    """Named alternatives: each is the closest-to-ask structure with some levers held at the ask."""
    a_ref = closest["terms"]["amount"] if closest is not None else ask["amount"]
    price = {"margin_bps": ask["margin_bps"], "upfront_fee_bps": ask["upfront_fee_bps"],
             "commitment_fee_bps": ask["commitment_fee_bps"], "commission_bps": ask["commission_bps"]}
    variants = [
        ("Same amount, shorter tenor", {"amount": a_ref}, {"tenor_years": [1, max(1, ask["tenor_years"] - 1)]}),
        ("Same tenor, deposit required" if deposit_lever(ask, base_kw.get("fixed"), base_kw.get("bounds")) else "Same tenor, cash margin",
         {"tenor_years": ask["tenor_years"], **price, "collateral_ids": ask["collateral_ids"],
                                     "covenant_package": ask["covenant_package"]}, None),
        ("Lower amount, current pricing", {**price, "tenor_years": ask["tenor_years"]}, None),
        ("Same structure, higher price", {"tenor_years": ask["tenor_years"], "collateral_ids": ask["collateral_ids"],
                                          "cash_margin_pct": ask["cash_margin_pct"], "covenant_package": ask["covenant_package"],
                                          "structure": ask["structure"], "amortisation": ask["amortisation"],
                                          "balloon_pct": ask["balloon_pct"], "grace_years": ask["grace_years"]}, None),
        ("More security, current pricing", {"margin_bps": ask["margin_bps"], "upfront_fee_bps": ask["upfront_fee_bps"]}, None),
        ("Tighter covenants", {"covenant_package": "enhanced"}, None),
    ]
    out, seen = [], set()
    if closest is not None:
        seen.add(repr(sorted((k, str(v)) for k, v in closest["terms"].items())))
    user_fixed = base_kw.get("fixed") or {}
    for label, fixed, bounds in variants:
        if any(k in user_fixed and user_fixed[k] != v for k, v in fixed.items()):
            continue
        if bounds and "tenor_years" in bounds and bounds["tenor_years"][1] >= ask["tenor_years"]:
            continue
        ub, excl = split_bounds(base_kw.get("bounds"))
        outside = [k for k, v in fixed.items() if k in ub and isinstance(v, (int, float)) and not (float(ub[k][0]) - EPS <= v <= float(ub[k][1]) + EPS)]
        if outside:
            continue
        b = {k: [float(v[0]), float(v[1])] for k, v in ub.items()}
        for k, (lo_, hi_) in (bounds or {}).items():  # intersect the variant's bounds with the user's
            b[k] = [max(lo_, b[k][0]), min(hi_, b[k][1])] if k in b else [lo_, hi_]
        if any(v[0] > v[1] for v in b.values()):
            continue
        if excl:
            if "collateral_ids" in fixed and any(_ctype_of(p, c) in excl for c in fixed["collateral_ids"]):
                fixed = {k: v for k, v in fixed.items() if k != "collateral_ids"}
            b["exclude_collateral_types"] = sorted(excl)
        prob = Problem(p, fixed={**fixed, **user_fixed}, bounds=b, weights=base_kw.get("weights"),
                       allow_soft=base_kw.get("allow_soft", False), el_view=base_kw.get("el_view", "economic"),
                       capital_basis=base_kw.get("capital_basis"))
        r = prob.closest(max_seconds=3.0)
        if r is None:
            continue
        sig = repr(sorted((k, str(v)) for k, v in r["terms"].items()))
        if sig in seen:
            continue
        seen.add(sig)
        out.append(_summary(r, ask, label, fx))
        if len(out) == 5:
            break
    return out


def _ctype_of(p: dict[str, Any], cid: str) -> str:
    return next(c["type"] for c in p["security"]["collateral"] if c["collateral_id"] == cid)


def _relaxation(p: dict[str, Any], kw: dict[str, Any]) -> list[dict[str, Any]]:
    """One lever or limit at a time: the minimum change that makes a structure feasible."""
    base = Problem(p, **kw)
    ask = base.ask
    out = []
    # amount below the minimum share of the ask
    pr = Problem(p, **{**kw, "relax": {"min_amount_share": 0.05}})
    r = pr.closest(max_seconds=6.0)
    if r is not None:
        out.append({"lever": "amount", "from": ask["amount"], "to": round(r["terms"]["amount"], 4), "unit": f"{ask['currency']} m",
                    "delta": round(r["terms"]["amount"] - ask["amount"], 4),
                    "note": f"{r['terms']['amount'] / ask['amount']:.0%} of the ask, below the {base.min_share:.0%} minimum"})
    # margin beyond the market cap
    pr = Problem(p, **{**kw, "relax": {"margin_cap_bps": 2000}})
    r = pr.closest(max_seconds=6.0)
    if r is not None and r["terms"]["margin_bps"] > base.market["margin_bps"][1]:
        out.append({"lever": "margin_bps", "from": ask["margin_bps"], "to": round(r["terms"]["margin_bps"], 1), "unit": "bps",
                    "delta": round(r["terms"]["margin_bps"] - ask["margin_bps"], 1), "beyond_market": True,
                    "note": f"market cap {base.market['margin_bps'][1]} bps"})
    # each blocking limit, relaxed alone
    a = base.evaluate({**ask, **base.fixed})
    names = {c["name"] for c in a["blocking"]}
    best_c = base.closest(max_seconds=4.0)
    for n in sorted(names | {c["name"] for c in (best_c["blocking"] if best_c else [])}):
        pr = Problem(p, **{**kw, "relax": {"ignore": [n]}})
        if n in A_DEPENDENT:
            hit = pr.best_value(n)
            if hit is None:
                continue
            c = hit["constraint"]
            note = "smallest relaxation: the best structure at the minimum amount"
        else:
            r = pr.closest(max_seconds=6.0)
            if r is None:
                continue
            c = next(c for c in r["analysis"]["constraints"] if c["name"] == n)
            note = "limit relaxed to the value the closest structure needs"
        out.append({"lever": n, "label": c["label"], "kind": c["kind"], "from": c["limit"], "to": c["value"], "unit": c["unit"],
                    "delta": (c["value"] - c["limit"]) if isinstance(c["value"], (int, float)) and isinstance(c["limit"], (int, float)) else None,
                    "note": note})
    # the hurdle
    pr = Problem(p, **{**kw, "relax": {"hurdle_off": True}})
    r = pr.max_sva(max_seconds=6.0)
    if r is not None and r["metrics"]["sva"] < 0:
        out.append({"lever": "hurdle", "from": r["metrics"]["hurdle"], "to": r["metrics"]["lifetime_raroc"], "unit": "share",
                    "delta": r["metrics"]["lifetime_raroc"] - r["metrics"]["hurdle"],
                    "note": "best lifetime RAROC inside market bounds and every hard limit"})
    return out


def optimize(p: dict[str, Any], fixed: dict[str, Any] | None = None, bounds: dict[str, Any] | None = None,
             weights: dict[str, float] | None = None, objective: str = "both", allow_soft: bool = False,
             el_view: str = "economic", capital_basis: str | None = None, counter_offers: bool = True) -> dict[str, Any]:
    t0 = time.time()
    kw = {"fixed": fixed, "bounds": bounds, "weights": weights, "allow_soft": allow_soft, "el_view": el_view, "capital_basis": capital_basis}
    prob = Problem(p, **kw)
    ask = prob.ask
    ask_r = prob.evaluate(dict(ask))
    closest = prob.closest() if objective in ("closest", "both") else None
    top = prob.max_sva() if objective in ("max_sva", "both") else None
    if closest is None and objective in ("max_sva",) and top is not None:
        closest = None
    feasible = (closest or top) is not None
    prob.sweep_frontier(closest, top)
    fr = prob.frontier()
    out = {
        "feasible": feasible, "objective": objective, "weights": prob.w, "market_bounds": prob.market,
        "ask": {"terms": ask, "metrics": ask_r["metrics"], "clears": ask_r["clears"],
                "breaches": [c["name"] for c in ask_r["blocking"]], "soft_breaches": [c["name"] for c in ask_r["soft"]],
                "approval": ask_r["analysis"]["approval"]},
        "closest": _summary(closest, ask, "Closest to ask", prob.fx),
        "max_sva": _summary(top, ask, "Maximum value", prob.fx),
        "frontier": [{"distance": r["distance"], "sva": r["metrics"]["sva"], "lifetime_raroc": r["metrics"]["lifetime_raroc"],
                      "amount": r["terms"]["amount"], "tenor_years": r["terms"]["tenor_years"], "margin_bps": r["terms"]["margin_bps"],
                      "terms": r["terms"]} for r in fr],
        "binding": _binding(prob, closest) + [dict(b, solution="max_sva") for b in _binding(prob, top)],
        "counter_offers": [],
        "relaxation": None,
    }
    if feasible and counter_offers:
        out["counter_offers"] = _counter_offers(p, kw, ask, closest, prob.fx)
    if not feasible:
        out["relaxation"] = _relaxation(p, kw)
    # R5 D4: alternative structures over the full lever set and the minimum change on each single lever
    from backend.dealdesk import alternatives as _alts
    try:
        alt = _alts.analyse_alternatives(p, None, fixed, bounds, allow_soft, el_view, capital_basis)
        out["alternatives"], out["single_lever"] = alt["alternatives"], alt["single_lever"]
    except engine.TermsError:
        out["alternatives"], out["single_lever"] = [], []
    out["searched"] = {"evaluations": prob.evals, "feasible_points": len(prob.points), "seconds": round(time.time() - t0, 2)}
    return out


def stress(p: dict[str, Any], terms: dict[str, Any] | None = None, scenario: str = "all", el_view: str = "economic",
           capital_basis: str | None = None) -> dict[str, Any]:
    sc = params.rows("stress")
    keys = list(sc) if scenario in ("all", "", None) else [scenario]
    for k in keys:
        if k not in sc:
            raise engine.TermsError([{"field": "scenario", "message": f"one of {', '.join(sc)}"}])
    base = engine.analyse(p, terms, el_view=el_view, capital_basis=capital_basis)
    rows = []
    for k in keys:
        s = sc[k]
        shocks = {"notches": s.get("notches", 0), "collateral_shock": s.get("collateral_shock", 0.0),
                  "rate_shock_bps": s.get("rate_shock_bps", 0.0), "ccf_add": s.get("ccf_add", 0.0)}
        if "utilisation_pct" in s:
            shocks["utilisation_pct"] = s["utilisation_pct"]
        a = engine.analyse(p, terms, el_view=el_view, capital_basis=capital_basis, shocks=shocks)
        m = a["metrics"]
        rows.append({"scenario": k, "label": s["label"], "lifetime_raroc": m["lifetime_raroc"], "sva": m["sva"],
                     "el_lifetime_pv": m["el_lifetime_pv"], "el_y1": m["el_y1"], "rwa_y1": m["rwa_y1"], "lgd_y1": m["lgd_y1"],
                     "pd_12m": m["pd_12m"], "dscr_post": m["dscr_post"], "clears_hurdle": m["clears_hurdle"],
                     "breaches": [c["name"] for c in cons.breaches(a["constraints"])],
                     "delta_raroc": m["lifetime_raroc"] - base["metrics"]["lifetime_raroc"], "delta_sva": m["sva"] - base["metrics"]["sva"]})
    return {"base": {"lifetime_raroc": base["metrics"]["lifetime_raroc"], "sva": base["metrics"]["sva"],
                     "el_lifetime_pv": base["metrics"]["el_lifetime_pv"], "rwa_y1": base["metrics"]["rwa_y1"]},
            "rows": rows, "robustness_notches": robustness(p, terms, el_view=el_view, capital_basis=capital_basis)}


def robustness(p: dict[str, Any], terms: dict[str, Any] | None = None, max_notches: int = 6, **kw: Any) -> int:
    """Notches of downgrade before lifetime RAROC falls below the hurdle (0 if it already does)."""
    for n in range(0, max_notches + 1):
        if engine.analyse(p, terms, shocks={"notches": n}, **kw)["metrics"]["sva"] < 0:
            return max(0, n - 1) if n else 0
    return max_notches


def tornado(p: dict[str, Any], terms: dict[str, Any] | None = None, **kw: Any) -> dict[str, Any]:
    """Lifetime RAROC with each lever moved down and up, the others at the given terms."""
    t = engine.merge_terms(p, terms)
    base = engine.analyse(p, t, **kw)["metrics"]["lifetime_raroc"]
    bars = []

    def r(tt: dict[str, Any], shocks: dict[str, Any] | None = None) -> float:
        return engine.analyse(p, tt, shocks=shocks, validate=False, **kw)["metrics"]["lifetime_raroc"]

    drawn = t["facility_type"] not in engine.UNFUNDED
    if drawn:
        bars.append({"lever": "Margin ±50 bps", "low": r({**t, "margin_bps": max(0, t["margin_bps"] - 50)}), "high": r({**t, "margin_bps": t["margin_bps"] + 50})})
    bars.append({"lever": "Upfront fee ±25 bps", "low": r({**t, "upfront_fee_bps": max(0, t["upfront_fee_bps"] - 25)}),
                 "high": r({**t, "upfront_fee_bps": t["upfront_fee_bps"] + 25})})
    lo_t, hi_t = max(1, t["tenor_years"] - 1), min(10, t["tenor_years"] + 1)
    bars.append({"lever": "Tenor ±1 year", "low": r({**t, "tenor_years": lo_t, "grace_years": min(t["grace_years"], lo_t - 1)}),
                 "high": r({**t, "tenor_years": hi_t})})
    bars.append({"lever": "Amount ±20%", "low": r({**t, "amount": t["amount"] * 0.8}), "high": r({**t, "amount": t["amount"] * 1.2})})
    bars.append({"lever": "Cash margin +10 pts", "low": base, "high": r({**t, "cash_margin_pct": min(100, t["cash_margin_pct"] + 10)})})
    bars.append({"lever": "Rating ±1 notch", "low": r(t, {"notches": 1}), "high": r(t, {"notches": -1})})
    bars.append({"lever": "Collateral value ±20%", "low": r(t, {"collateral_shock": -0.2}), "high": r(t, {"collateral_shock": 0.2})})
    if t["commission_bps"] or t["facility_type"] in engine.UNFUNDED:
        bars.append({"lever": "Commission ±25 bps", "low": r({**t, "commission_bps": max(0, t["commission_bps"] - 25)}),
                     "high": r({**t, "commission_bps": t["commission_bps"] + 25})})
    # R5 D4: the rest of the lever set (one-sided where the lever only moves one way from the terms)
    if t["facility_type"] == "term_loan":
        bars.append({"lever": "Prepayment fee +100 bps", "low": base, "high": r({**t, "prepayment_fee_bps": t.get("prepayment_fee_bps", 0) + 100})})
    bars.append({"lever": "Hold −20 pts (sell-down)", "low": r({**t, "hold_pct": max(20, t.get("hold_pct", 100) - 20)}), "high": base})
    bars.append({"lever": "Credit insurance +50 pts", "low": base,
                 "high": r({**t, "insurance_cover_pct": min(100 - (t["guarantee_coverage_pct"] if t.get("guarantee_id") else 0),
                                                           t.get("insurance_cover_pct", 0) + 50)})})
    bars.append({"lever": "Assigned receivables +50 pts", "low": base,
                 "high": r({**t, "receivables_assignment_pct": min(100, t.get("receivables_assignment_pct", 0) + 50)})})
    for b in bars:
        b["low_delta"], b["high_delta"] = b["low"] - base, b["high"] - base
        b["span"] = abs(b["high"] - b["low"])
    bars.sort(key=lambda b: -b["span"])
    return {"base_raroc": base, "bars": bars}


def grid(p: dict[str, Any], terms: dict[str, Any] | None, x: str, x_values: list[float], y: str | None = None,
         y_values: list[float] | None = None, metric: str = "lifetime_raroc", **kw: Any) -> dict[str, Any]:
    t = engine.merge_terms(p, terms)
    allowed = {"margin_bps", "tenor_years", "amount", "upfront_fee_bps", "cash_margin_pct", "commission_bps", "guarantee_coverage_pct",
               "utilisation_pct"}
    for k in (x, y):
        if k is not None and k not in allowed:
            raise engine.TermsError([{"field": "x/y", "message": f"one of {', '.join(sorted(allowed))}"}])
    ys = y_values if y else [None]
    vals = []
    for yv in ys:
        row = []
        for xv in x_values:
            tt = {**t, x: xv}
            if y:
                tt[y] = yv
            for k in ("tenor_years",):
                if k in (x, y):
                    tt[k] = int(tt[k])
                    tt["grace_years"] = min(tt["grace_years"], tt[k] - 1)
            row.append(engine.analyse(p, tt, **kw)["metrics"].get(metric))
        vals.append(row)
    return {"x": x, "x_values": x_values, "y": y, "y_values": y_values, "metric": metric, "values": vals if y else vals[0],
            "hurdle": engine.hurdle_for(p), "ask": {"x": t[x], "y": t[y] if y else None}}
