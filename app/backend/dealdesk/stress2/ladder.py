"""The R12 Stress Lab run: the ladder by family, not-applicable rows, the LTV column, the checked stressed RAROC,
reverse stress, the transmission chain, the verdict, the monitoring tier and the commentary (PLAN_R12 §1.5).

Every scenario goes through the R11 Stress Lab (`stress_lab.Lab.scenario`, which runs `engine.analyse`), never a
copy of it. What R12 adds around it:

  resolve     a ladder spec -> the concrete shocks for this deal, step by step, each step with its number and its
              source: the sensitivity row (`dd_stress_sensitivity`, current version) or the deal's own fact
              (`facts.deal_facts`), so the chain can be shown and asked about.
  applicable  a row that cannot move this deal (no own-sector downturn, no projects, no collateral, no guarantee,
              no real estate) is kept and says "not applicable to this deal" and why (O6).
  LTV         exposure / all pledged collateral after the shock, wherever collateral is pledged (O6); the R11
              LTV (real estate only, against the LTV limit) stays the pass/breach test.
  RAROC       the checked stressed RAROC (O4, `raroc_check`) replaces the engine figure in the RAROC test.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from typing import Any

from backend.dealdesk import engine, paths
from backend.dealdesk import stress_lab as sl
from backend.dealdesk.stress2 import catalogue as cat
from backend.dealdesk.stress2 import facts as fx
from backend.dealdesk.stress2 import raroc_check
from backend.dealdesk.stress2 import store

SEV_RANK = {"none": -1, "mild": 0, "moderate": 1, "severe": 2, "custom": 3}
PROJECT_SECTOR_SHARE = 0.25


class NA(Exception):
    """This scenario cannot move this deal."""


def _pct(v: float, dp: int = 1) -> str:
    return sl._m(f"{v * 100:+.{dp}f}%")


# ------------------------------------------------------------------ resolving one spec, step by step

class Resolver:
    def __init__(self, p: dict[str, Any], t: dict[str, Any], sens: cat.Sensitivities, facts: dict[str, Any]):
        self.p, self.t, self.sens, self.facts = p, t, sens, facts
        self.sector = p["obligor"]["sector"]
        items = {c["collateral_id"]: c for c in p["security"]["collateral"]}
        self.pledged = [items[c] for c in t.get("collateral_ids", []) if c in items]
        self.has_guarantee = bool(t.get("guarantee_id")) or float(t.get("insurance_cover_pct") or 0) > 0

    def _sens(self, sid: str) -> dict[str, Any]:
        return self.sens.get(sid, self.sector)

    def _src(self, s: dict[str, Any]) -> str:
        where = self.sector if s.get("matched_sector") == self.sector else "all sectors (default)"
        return f"{s.get('label', s['sensitivity_id'])}, {where}: {s.get('source', '')} (dd_stress_sensitivity v{s.get('version')})"

    def step(self, steps: list, name: str, value: Any, display: str, source: str, *, relation: str, row: str,
             deal_fact: bool = False, band: tuple | None = None, trace: dict[str, Any] | None = None) -> None:
        steps.append({"step": name, "value": value, "display": sl._m(display), "source": source, "relation": relation,
                      "row": row, "deal_fact": deal_fact, "band": band, "trace": trace})

    def resolve(self, shocks: dict[str, Any], lookup, depth: int = 0) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """(resolved shocks in stress_lab's form, steps). Raises NA when nothing in the spec moves this deal."""
        if shocks.get("compose"):
            out = copy.deepcopy(sl.EMPTY)
            steps: list[dict[str, Any]] = []
            na: list[str] = []
            for part in shocks["compose"]:
                alts = str(part).split("|")
                done = False
                for sid in alts:
                    sc = lookup(sid)
                    if sc is None:
                        continue
                    try:
                        r, st = self.resolve(sc["shocks"], lookup, depth + 1)
                    except NA as e:
                        na.append(f"{sc['label']}: {e}")
                        continue
                    out = sl.combine(out, r)
                    steps += [{**s, "part": sc["label"]} for s in st]
                    done = True
                    break
                if not done and len(alts) > 1:
                    na.append(f"{part}: none of the alternatives applies")
            if not steps:
                raise NA("; ".join(na) or "no part of this combination moves this deal")
            if na:
                steps.append({"step": "Parts that do not apply", "value": None, "display": "; ".join(na), "source": "",
                              "relation": "", "row": "", "deal_fact": False, "band": None})
            return out, steps
        r = copy.deepcopy(sl.EMPTY)
        steps = []
        sec = self.sector
        reasons = []
        for key in ("oil_pct", "gdp_pct"):
            if shocks.get(key):
                sid = "oil_revenue_beta" if key == "oil_pct" else "gdp_revenue_beta"
                s = self._sens(sid)
                move = float(shocks[key])
                rev = s["value"] * (-move)
                if abs(rev) < 1e-12:
                    reasons.append(f"{s['label']} is zero for {sec}")
                    continue
                r = sl.combine(r, {**sl.EMPTY, "revenue_pct": rev, "collateral": {}})
                nm = "Oil" if key == "oil_pct" else "Non-oil GDP"
                self.step(steps, f"{nm} {move:+g}% -> revenue", rev,
                          f"{nm} {move:+g}% x beta {s['value'] * 100:+.2f}% per 1% fall = revenue {_pct(rev)}",
                          self._src(s), relation="dd_stress_sensitivity", row=f"{sid} / {s.get('matched_sector')}",
                          band=(s.get("lower"), s.get("upper")), trace=store.sens_source(s))
        if shocks.get("sector_downturn"):
            k = float(shocks["sector_downturn"])
            sr, sd, sm = (self._sens(x) for x in ("sector_downturn_revenue", "sector_downturn_receivable_days", "sector_downturn_margin_bps"))
            if abs(sr["value"]) < 1e-12 and abs(sd["value"]) < 1e-12 and abs(sm["value"]) < 1e-12:
                reasons.append(f"no own-sector downturn is defined for {sec}")
            else:
                r = sl.combine(r, {**sl.EMPTY, "revenue_pct": k * sr["value"], "receivable_days": k * sd["value"],
                                   "ebitda_margin_bps": k * sm["value"], "collateral": {}})
                self.step(steps, f"{sec} downturn x {k:g}", k * sr["value"],
                          f"revenue {_pct(k * sr['value'])}, receivable days {k * sd['value']:+.0f}, margin {k * sm['value']:+.0f} bps",
                          self._src(sr), relation="dd_stress_sensitivity", row=f"sector_downturn_* / {sr.get('matched_sector')}",
                          trace=store.sens_source(sr))
        if shocks.get("revenue_pct"):
            v = float(shocks["revenue_pct"])
            r = sl.combine(r, {**sl.EMPTY, "revenue_pct": v, "collateral": {}})
            self.step(steps, "Revenue shock", v, f"revenue {_pct(v)} on the latest audited year", "scenario definition (dd_stress_scenario)",
                      relation="dd_stress_scenario", row="revenue_pct")
        if shocks.get("ebitda_margin_bps"):
            v = float(shocks["ebitda_margin_bps"])
            r["ebitda_margin_bps"] += v
            self.step(steps, "Margin shock", v, f"EBITDA margin {v:+.0f} bps", "scenario definition (dd_stress_scenario)",
                      relation="dd_stress_scenario", row="ebitda_margin_bps")
        if shocks.get("customer_loss_share"):
            k = float(shocks["customer_loss_share"])
            f = self.facts.get("largest_customer_share")
            if f:
                share, src, rel, row, deal, tr = f["value"], f["source"], f["relation"], f["row"], True, f.get("trace")
            else:
                s = self._sens("largest_customer_share")
                share, src, rel, row, deal, tr = (s["value"], self._src(s), "dd_stress_sensitivity",
                                                  f"largest_customer_share / {s.get('matched_sector')}", False, store.sens_source(s))
            rev = -k * share
            r = sl.combine(r, {**sl.EMPTY, "revenue_pct": rev, "collateral": {}})
            self.step(steps, "Largest customer -> revenue", rev,
                      f"{k * 100:.0f}% of the largest customer's {share * 100:.0f}% share = revenue {_pct(rev)}", src,
                      relation=rel, row=row, deal_fact=deal, trace=tr)
        if shocks.get("receivable_days"):
            v = float(shocks["receivable_days"])
            r["receivable_days"] += v
            self.step(steps, "Payment delay", v, f"receivable days {v:+.0f}, funded with short-term debt",
                      "scenario definition (dd_stress_scenario)", relation="dd_stress_scenario", row="receivable_days")
        if shocks.get("delay_months"):
            m = float(shocks["delay_months"])
            f = self.facts.get("project_revenue_share")
            s = self._sens("project_revenue_share")
            tr = None
            if f:
                share, src, rel, row, deal, tr = f["value"], f["source"], f["relation"], f["row"], True, f.get("trace")
            elif s.get("matched_sector") == sec and s["value"] >= PROJECT_SECTOR_SHARE:
                share, src, rel, row, deal, tr = s["value"], self._src(s), "dd_stress_sensitivity", f"project_revenue_share / {sec}", False, store.sens_source(s)
            else:
                share = None
                reasons.append(f"no financed projects in the deal file and {sec} revenue is not milestone-based")
            if share:
                rev = -share * min(m, 12.0) / 12.0
                days = share * m * 365.0 / 12.0
                r = sl.combine(r, {**sl.EMPTY, "revenue_pct": rev, "receivable_days": days, "collateral": {}})
                self.step(steps, f"Project delay {m:g} months", rev,
                          f"project share {share * 100:.0f}% x {min(m, 12):g}/12 = revenue {_pct(rev)}; work done carried as {days:.0f} receivable days",
                          src, relation=rel, row=row, deal_fact=deal, trace=tr)
        if shocks.get("rate_bps"):
            v = float(shocks["rate_bps"])
            r["rate_bps"] += v
            fixed = self.t.get("rate_type") == "fixed"
            self.step(steps, "Benchmark rate", v, f"SAIBOR / EIBOR {v:+.0f} bps" + (" (this deal is fixed rate: only the obligor's existing debt reprices)" if fixed else ""),
                      "scenario definition (dd_stress_scenario)", relation="dd_stress_scenario", row="rate_bps")
        if shocks.get("collateral_pct") is not None and shocks.get("collateral_pct") != 0:
            if not self.pledged:
                reasons.append("no collateral is pledged in this structure")
            else:
                v = float(shocks["collateral_pct"])
                r = sl.combine(r, {**sl.EMPTY, "collateral": {"*": v}})
                self.step(steps, "Collateral value", v, f"every pledged item {_pct(v, 0)} ({', '.join(sorted({c['type'].replace('_', ' ') for c in self.pledged}))})",
                          "scenario definition (dd_stress_scenario)", relation="dd_collateral_guarantee", row=",".join(c["collateral_id"] for c in self.pledged))
        if shocks.get("real_estate_pct"):
            v = float(shocks["real_estate_pct"])
            has_re = any(c["type"] == "real_estate" for c in self.pledged)
            s = self._sens("real_estate_revenue_beta")
            rev = s["value"] * (-v) if s.get("matched_sector") == sec else 0.0
            if not has_re and abs(rev) < 1e-12:
                reasons.append("no real estate is pledged and the obligor's revenue does not follow real-estate prices")
            else:
                if has_re:
                    r = sl.combine(r, {**sl.EMPTY, "collateral": {"real_estate": v / 100.0}})
                    self.step(steps, "Real-estate collateral", v / 100.0, f"pledged real estate {v:+g}%", "scenario definition (dd_stress_scenario)",
                              relation="dd_collateral_guarantee", row=",".join(c["collateral_id"] for c in self.pledged if c["type"] == "real_estate"))
                if abs(rev) > 1e-12:
                    r = sl.combine(r, {**sl.EMPTY, "revenue_pct": rev, "collateral": {}})
                    self.step(steps, "Real-estate prices -> revenue", rev, f"prices {v:+g}% x beta {s['value'] * 100:+.2f}% = revenue {_pct(rev)}",
                              self._src(s), relation="dd_stress_sensitivity", row=f"real_estate_revenue_beta / {sec}", trace=store.sens_source(s))
        if shocks.get("notches"):
            n = int(shocks["notches"])
            r["notches"] += n
            self.step(steps, "Rating shock", n, f"rating −{n} notch{'es' if n > 1 else ''}, applied directly", "scenario definition (dd_stress_scenario)",
                      relation="dd_stress_scenario", row="notches")
        if shocks.get("guarantee_unenforceable"):
            if not self.has_guarantee:
                reasons.append("no guarantee or credit insurance is in this structure")
            else:
                r["guarantee_unenforceable"] = True
                self.step(steps, "Guarantee", True, "the guarantee and credit insurance give no protection", "scenario definition (dd_stress_scenario)",
                          relation="dd_collateral_guarantee", row=str(self.t.get("guarantee_id") or "insurance"))
        if not steps:
            raise NA("; ".join(reasons) if reasons else "the scenario carries no shock")
        if reasons and depth == 0:
            steps.append({"step": "Parts that do not apply", "value": None, "display": "; ".join(reasons), "source": "", "relation": "",
                          "row": "", "deal_fact": False, "band": None})
        return r, steps

    def finish(self, r: dict[str, Any]) -> dict[str, Any]:
        """Attach the fixed-cost share and funding spread the stressed financials use."""
        fc = self._sens("fixed_cost_share")
        sp = self._sens("short_term_funding_spread_bps")
        return {**r, "_fixed_cost_share": fc["value"], "_st_spread_bps": sp["value"]}


# ------------------------------------------------------------------ one row

def ltv_cover(lab: sl.Lab, r: dict[str, Any], resolver: Resolver) -> float | None:
    """Exposure (funded; the facility amount when unfunded) / pledged collateral value after the shock, any type (O6)."""
    if not resolver.pledged:
        return None
    v = 0.0
    for c in resolver.pledged:
        x = float(c.get("value") or 0.0) * engine.fx(c.get("currency", "SAR"))
        x *= (1 + r["collateral"].get(c["type"], 0.0)) * (1 + r["collateral"].get("*", 0.0))
        v += x
    # the funded exposure; for an unfunded facility (guarantees, LCs) the facility amount the collateral secures
    expo = lab.mirror.f_full if lab.mirror.f_full > 0 else float(lab.base["metrics"]["amount_sar_mn"])
    if v <= 0:
        return float("inf") if expo > 0 else None
    return expo / v


def _verdict_cells(row: dict[str, Any], base_fails: set[str]) -> list[str]:
    """The tests a row breaks for the verdict: new breaches only; for the rating family, Stage 2 at the SICR notch
    count is the shock's own definition and does not count (DSCR, covenants, RAROC, limits and minimum rating do)."""
    out = [c for c in row["fails_on"] if c not in base_fails]
    if row.get("family") == "rating":
        out = [c for c in out if c != "stage"]
    return out


def run_row(lab: sl.Lab, resolver: Resolver, sc: dict[str, Any], lookup) -> dict[str, Any]:
    spec = {"group": sc["family"], "label": sc["label"], "severity": sc["severity"], "basis": sc["basis"]}
    try:
        r, steps = resolver.resolve(sc["shocks"], lookup)
    except NA as e:
        return {"id": sc["scenario_id"], "family": sc["family"], "group": sc["family"], "label": sc["label"], "severity": sc["severity"],
                "basis": sc["basis"], "scope": sc.get("scope", "bank"), "version": sc.get("version", 1), "applicable": False,
                "na_reason": f"Not applicable to this deal: {e}.", "steps": [], "shocks": [], "cells": {}, "fails_on": [],
                "breaks": [], "survives": True, "source": sc.get("source")}
    r = resolver.finish(r)
    row = lab.scenario(sc["scenario_id"], spec, r)
    m = row["metrics"]
    q, tt, sh = sl.stressed_case(lab.p, lab.t, r)
    a = lab.run_engine(r, m["notches"]["total"]) if not sl.is_null(r) else lab.base
    chk = raroc_check.check(lab, r, m["notches"]["total"], m["stage"], a, m["ecl"])
    m["lifetime_raroc_r11"] = m["lifetime_raroc"]
    m["lifetime_raroc"] = chk["raroc"]
    m["sva_r11"] = m["sva"]
    m["sva"] = chk["sva"]
    m["clears_hurdle"] = chk["clears_hurdle"]
    m["ltv_cover"] = ltv_cover(lab, r, resolver)
    h = m["hurdle"]
    amber = float(sl._tr_bands()["raroc_amber_pts"])
    rr = m["lifetime_raroc"]
    row["cells"]["raroc"] = "breach" if (rr is None or not chk["clears_hurdle"]) else "amber" if rr < h + amber else "pass"
    row["fails_on"] = [k for k, v in row["cells"].items() if v == "breach"]
    row["survives"] = not row["fails_on"]
    row.update({"family": sc["family"], "scope": sc.get("scope", "bank"), "version": sc.get("version", 1), "steps": steps,
                "raroc_check": chk, "na_reason": None, "source": sc.get("source"), "fixed_cost_share": r.get("_fixed_cost_share")})
    row.pop("resolved", None)
    row["resolved"] = {k: v for k, v in r.items() if not k.startswith("_")}
    return row


# ------------------------------------------------------------------ reverse stress

COV_LABEL = "a covenant break"


class Reverse:
    """How far until DSCR < 1, a covenant breaks, Stage 2, or the checked RAROC < hurdle, per driver; and how many
    notches the deal survives."""

    def __init__(self, lab: sl.Lab, resolver: Resolver):
        self.lab, self.res = lab, resolver
        self._chk: dict[tuple[int, int], dict[str, Any]] = {}

    def _r(self, drv: str, x: float) -> dict[str, Any]:
        r = copy.deepcopy(sl.EMPTY)
        if drv == "collateral_pct":
            r["collateral"] = {"*": x}
        elif drv == "notches":
            r["notches"] = int(x)
        else:
            r[drv] = x
        return self.res.finish(r)

    def _checked(self, r: dict[str, Any], n: int, stage: int, financial: bool) -> dict[str, Any]:
        key = (n, stage) if financial else None
        if key and key in self._chk:
            return self._chk[key]
        a = self.lab.run_engine(r if not financial else self.res.finish(copy.deepcopy(sl.EMPTY)), n)
        ecl, _ = self.lab._ecl(a["metrics"], stage)
        c = raroc_check.check(self.lab, r if not financial else self.res.finish(copy.deepcopy(sl.EMPTY)), n, stage, a, ecl)
        if key:
            self._chk[key] = c
        return c

    def fails(self, drv: str, crit: str, x: float) -> bool | None:
        r = self._r(drv, x)
        st = self.lab.mirror.ratios(r)
        n = int(r["notches"]) + sl.implied_notches(self.lab.base_r, st)
        if crit == "dscr":
            return st["dscr"] < 1.0
        if crit == "covenant":
            cv = self.lab._covenants({"dscr": st["dscr"], "debt_ebitda": st["debt_ebitda"], "interest_cover": st["interest_cover"]})
            mod = [c for c in cv if c["status"] != "not_modelled"]
            if not mod:
                return None
            return any(c["status"] == "breach" for c in mod)
        stage = sl.stage_for(self.lab.rating0, n, st["dscr"])[0]
        if crit == "stage2":
            return stage >= 2
        if crit == "raroc":
            fin = drv in ("revenue_pct", "ebitda_margin_bps", "notches")
            return not self._checked(r, n, stage, fin)["clears_hurdle"]
        if crit == "ltv":
            lim = self.lab._ltv_limit()
            if st["ltv"] is None or lim is None:
                return None
            return st["ltv"] > lim + 1e-12
        raise KeyError(crit)

    def solve(self, drv: str, crit: str, lo: float, hi: float, tol: float) -> dict[str, Any]:
        f0 = self.fails(drv, crit, lo)
        if f0 is None:
            return {"criterion": crit, "status": "na", "value": None}
        if f0:
            return {"criterion": crit, "status": "already", "value": lo}
        if not self.fails(drv, crit, hi):
            return {"criterion": crit, "status": "beyond", "value": None, "limit_of_search": hi}
        a, b = lo, hi
        while abs(b - a) > tol:
            mid = (a + b) / 2
            if self.fails(drv, crit, mid):
                b = mid
            else:
                a = mid
        return {"criterion": crit, "status": "found", "value": b, "passes_at": a}

    def notches(self, up_to: int = 8) -> dict[str, Any]:
        out = {}
        for crit in ("raroc", "stage2", "dscr", "covenant"):
            first = None
            for n in range(0, up_to + 1):
                f = self.fails("notches", crit, n)
                if f is None:
                    break
                if f:
                    first = n
                    break
            out[crit] = first
        surv = (out["raroc"] - 1) if out["raroc"] is not None else up_to
        return {"breaks_at": out, "survives_up_to": max(0, surv) if out["raroc"] != 0 else 0, "searched_to": up_to}

    def run(self) -> dict[str, Any]:
        rng = cat.r11_table()["transmission"]["breakeven_ranges"]
        labels = {"dscr": "DSCR below 1.0", "covenant": COV_LABEL, "stage2": "Stage 2", "raroc": "RAROC below the hurdle",
                  "ltv": "LTV above the limit"}
        drivers = {"revenue_pct": ("Revenue", ("dscr", "covenant", "stage2", "raroc")),
                   "ebitda_margin_bps": ("EBITDA margin", ("dscr", "covenant", "stage2", "raroc")),
                   "rate_bps": ("Benchmark rate", ("dscr", "covenant", "stage2")),
                   "collateral_pct": ("Collateral value", ("ltv",))}
        rows = []
        for drv, (lab_, crits) in drivers.items():
            lo, hi = (float(v) for v in rng[drv])
            res = []
            for c in crits:
                if drv == "collateral_pct" and not self.res.pledged:
                    res.append({"criterion": c, "label": labels[c], "status": "na", "value": None, "note": "No collateral is pledged."})
                    continue
                s = self.solve(drv, c, lo, hi, sl.TOL[drv])
                res.append({**s, "label": labels[c]})
            rows.append({"driver": drv, "label": lab_, "criteria": res, "range": [lo, hi]})
        nt = self.notches()
        return {"drivers": rows, "notches": nt, "headline": headline(rows, nt)}


def _drv_text(drv: str, v: float) -> str:
    if drv in ("revenue_pct", "collateral_pct"):
        return sl._m(f"{v * 100:+.1f}%" if abs(v) < 0.095 else f"{v * 100:+.0f}%")
    return sl._m(f"{v:+.0f} bps")


def headline(rows: list[dict[str, Any]], nt: dict[str, Any]) -> str:
    """'Survives up to 2 notches; breaks a covenant at −18% revenue.'"""
    parts = []
    br = nt["breaks_at"]
    if br.get("raroc") == 0:
        parts.append("RAROC is below the hurdle before any downgrade")
    elif br.get("raroc") is None:
        parts.append(f"RAROC stays above the hurdle through {nt['searched_to']} notches")
    else:
        parts.append(f"survives up to {nt['survives_up_to']} notch{'es' if nt['survives_up_to'] != 1 else ''} before RAROC falls below the hurdle")
    rev = next((x for x in rows if x["driver"] == "revenue_pct"), None)
    if rev:
        found = [c for c in rev["criteria"] if c["status"] == "found"]
        already = [c for c in rev["criteria"] if c["status"] == "already"]
        if found:
            f = min(found, key=lambda c: abs(c["value"]))
            parts.append(f"{'breaks a covenant' if f['criterion'] == 'covenant' else 'hits ' + f['label']} at {_drv_text('revenue_pct', f['value'])} revenue")
        already = [c for c in already if not (c["criterion"] == "raroc" and br.get("raroc") == 0)]
        if already:
            parts.append(", ".join(c["label"] for c in already) + " before any revenue fall")
    s = "; ".join(parts) + "."
    return s[0].upper() + s[1:]


# ------------------------------------------------------------------ the whole run

def _hash(o: Any) -> str:
    return hashlib.sha1(json.dumps(o, sort_keys=True, default=str).encode()).hexdigest()[:16]


def run(p: dict[str, Any], terms: dict[str, Any] | None = None, *, scenario_ids: list[str] | None = None,
        el_view: str = "economic", capital_basis: str | None = None, structure_label: str | None = None,
        reverse: bool = True, sensitivity_version: str | None = None, publish: bool = True, extra: list[dict[str, Any]] | None = None,
        include_chain: bool = True) -> dict[str, Any]:
    """POST /proposals/{id}/stress2."""
    from backend.dealdesk.stress2 import chain as ch, commentary, verdict as vd
    cat.ensure_seeded()
    asked = engine.merge_terms(p, None)
    t = engine.merge_terms(p, terms)
    lab = sl.Lab(p, t, el_view, capital_basis, structure_label or ("Asked" if t == asked else "Selected"))
    sens = cat.Sensitivities(sensitivity_version)
    facts = fx.deal_facts(p)
    res = Resolver(p, lab.t, sens, facts)
    scs = cat.scenarios(p["proposal_id"]) + list(extra or [])
    if scenario_ids:
        scs = [s for s in scs if s["scenario_id"] in scenario_ids]
    allmap = {s["scenario_id"]: s for s in cat.scenarios(p["proposal_id"]) + list(extra or [])}
    base = lab.base_row()
    chk0 = raroc_check.check(lab, copy.deepcopy(sl.EMPTY), 0, 1, lab.base, base["metrics"]["ecl"])
    base["raroc_check"] = chk0
    base["metrics"]["ltv_cover"] = ltv_cover(lab, sl.EMPTY, res)
    base["family"] = "base"
    base_fails = set(base["fails_on"])
    rows = [run_row(lab, res, s, allmap.get) for s in scs]
    for r in rows:
        r["breaks"] = _verdict_cells(r, base_fails) if r["applicable"] else []
    fams = []
    for fid, flab in cat.FAMILIES:
        fr = [r for r in rows if r["family"] == fid]
        if fr:
            fams.append({"id": fid, "label": flab, "row_ids": [r["id"] for r in fr]})
    rv = Reverse(lab, res).run() if reverse else None
    v = vd.verdict(rows, base, base_fails)
    tier = vd.tier_for(v, rows, rv, lab, facts)
    for r in rows:
        if r["applicable"] and include_chain:
            r["chain"] = ch.chain(lab, r, base)
    out: dict[str, Any] = {
        "proposal_id": p["proposal_id"], "obligor": p["obligor"]["name"], "obligor_id": p["obligor"].get("obligor_id"),
        "sector": p["obligor"]["sector"], "structure": {"label": lab.label, "terms": lab.t},
        "base": base, "families": fams, "rows": rows,
        "columns": [{"key": k, "label": sl.CELL_LABELS[k]} for k in sl.METRIC_CELLS] + [{"key": "ltv_cover", "label": "LTV (all collateral)"}],
        "show_ltv": bool(res.pledged), "reverse": rv, "verdict": v, "tier": tier,
        "deal_facts": facts, "sensitivity_version": sens.version, "scenario_set": sorted({str(s.get("set_id") or s.get("scope")) for s in scs}),
        "backend": store.backend("dd_stress_result"),
        "counts": {"applicable": sum(1 for r in rows if r["applicable"]), "not_applicable": sum(1 for r in rows if not r["applicable"]),
                   "breaking": sum(1 for r in rows if r["breaks"])},
        "evaluations": lab.evals,
    }
    out["commentary"] = commentary.write(out)
    try:   # R14 m (K12): the current-regime block, read first in every scenario answer (backend/scenarios/regime.py)
        from backend.scenarios import regime as _rg, revenue as _rv
        out["regime"] = {**_rg.block(), "revenue": _rv.deal_line(p["proposal_id"], p["obligor"].get("sector"))}
    except Exception:  # noqa: BLE001 - the ladder never fails on the regime block
        out["regime"] = None
    out["run_id"] = "SR-" + _hash([p["proposal_id"], lab.t, [(s["scenario_id"], s.get("version")) for s in scs], sens.version,
                                   el_view, capital_basis])
    if publish:
        out["published"] = publish_result(out)
    return out


def publish_result(out: dict[str, Any], *, context: str = "stress_run", by: str = "") -> dict[str, Any]:
    """dd_stress_result: one row per scenario of a run (deduplicated by run id and context)."""
    if store.read("dd_stress_result", run_id=out["run_id"], context=context):
        return {"relation": "dd_stress_result", "rows": 0, "backend": store.backend("dd_stress_result"), "duplicate": True}
    at = store.now()
    rows = []
    for r in [out["base"]] + out["rows"]:
        m = r.get("metrics") or {}
        rows.append({
            "run_id": out["run_id"], "context": context, "proposal_id": out["proposal_id"], "obligor_id": out.get("obligor_id"),
            "structure_label": out["structure"]["label"], "scenario_id": r["id"], "scenario_version": r.get("version", 1),
            "family": r.get("family"), "severity": r.get("severity"), "applicable": bool(r.get("applicable", True)),
            "revenue_change": ((r.get("financials") or {}).get("revenue", 0) / (r.get("financials") or {}).get("base_revenue", 1) - 1)
            if (r.get("financials") or {}).get("base_revenue") else None, "ebitda": (r.get("financials") or {}).get("ebitda"),
            "na_reason": r.get("na_reason"), "dscr": m.get("dscr"), "debt_ebitda": m.get("debt_ebitda"), "ltv": m.get("ltv"),
            "ltv_cover": m.get("ltv_cover"), "rating": m.get("rating"), "notches_total": (m.get("notches") or {}).get("total"),
            "pd_12m": m.get("pd_12m"), "stage": m.get("stage"), "ecl_sar_mn": m.get("ecl"), "raroc": m.get("lifetime_raroc"),
            "raroc_r11": m.get("lifetime_raroc_r11"), "sva_sar_mn": m.get("sva"), "hurdle": m.get("hurdle"),
            "fails_on": r.get("fails_on", []), "breaks": r.get("breaks", []), "verdict": out["verdict"]["verdict"],
            "tier": out["tier"]["tier"], "sensitivity_version": out["sensitivity_version"], "run_at": at, "run_by": by or "deal desk",
            "reporting_quarter": paths.AS_OF,
        })
    return store.publish("dd_stress_result", rows)


def finite(v: Any) -> Any:
    return None if isinstance(v, float) and not math.isfinite(v) else v
