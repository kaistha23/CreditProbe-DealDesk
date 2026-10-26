"""gw-ews-1.3.0: the Early Warning story calibration (PLAN_R5 Session E).

Same targets and constraints as gw-ews-1.1.0 / 1.2.0 (EWS_UAT.md section 7, INBOX Item 1):
about 10-20% of owners warned and under 7% high or critical at the as-of date, every already-bad
owner warned, no rule switched off, critical band not empty.

New in 1.3.0: the search also scores the STORY (docs/v5/EWS_STORY.md): on the last period's change,
per level (corporate: sector, region, Construction's sub-sectors; retail: product, region), a segment
IMPROVES when its warned owners fall and its high/critical EAD does not rise, and DETERIORATES when
its warned owners rise and its high/critical EAD does not fall.
The search keeps only sets with at least 2 improving and 2 deteriorating segments per level, then
prefers the set whose named segments move as the story says, then the most forward risk.

Reads the EWS releases as built (backend/ews_domain/build_packages.py), which carry every input
column. Writes evidence/v5/ews/calibration/ruleset_1_3_0.json.

    python ops/ews_story_calibration.py            # search, report
    python ops/ews_story_calibration.py --check    # evaluate the built release (its ews_score), exit 1 on a miss
"""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

V5 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V5))
from backend.ews_domain import paths  # noqa: E402
from backend.ews_domain import reader as rd  # noqa: E402

OUT = V5 / "evidence" / "v5" / "ews" / "calibration"
TARGET_WARNED = (10.0, 20.0)
TARGET_SEVERE = 7.0

#: Rule -> function(frame, threshold) -> bool array. Columns as the EWS release carries them.
FIRES = {
    # corporate
    "C-WATCH": lambda f, t: f.watchlist_flag == 1,
    "C-DOWNGRADE": lambda f, t: f.rating_notches_moved < 0,
    "C-COVENANT": lambda f, t: f.covenant_breaches > 0,
    "C-DPD": lambda f, t: f.dpd_days > t,
    "C-SICR": lambda f, t: f.sicr_flag == 1,
    "C-UTIL": lambda f, t: f.utilisation_pct >= t,
    "C-DEFAULT": lambda f, t: (f.stage == 3) | (f.default_flag == 1),
    "C-BUR-EXTDPD": lambda f, t: f.external_dpd_days > t,
    "C-BUR-ENQ": lambda f, t: f.enquiries_q >= t,
    "C-OB-INFLOW": lambda f, t: f.inflow_trend_pct <= t,
    "C-OB-BUFFER": lambda f, t: f.balance_buffer_months < t,
    "C-OB-RETURNED": lambda f, t: f.returned_payments_q >= t,
    # retail
    "R-DPD": lambda f, t: f.dpd_days > t,
    "R-SCORE-LOW": lambda f, t: f.score_band == "E",
    "R-SCORE-DOWN": lambda f, t: (
        ((f.customer_score_band_previous == "A") & f.customer_score_band.isin(["C", "D", "E"]))
        | ((f.customer_score_band_previous == "B") & f.customer_score_band.isin(["D", "E"]))
        | ((f.customer_score_band_previous == "C") & (f.customer_score_band == "E"))),
    "R-UTIL": lambda f, t: f.utilisation_pct >= t,
    "R-MINPAY": lambda f, t: (f.payment_ratio_pct < 30) & (f.payment_ratio_change_3m <= t),
    "R-BUR-SCORE": lambda f, t: f.bureau_score < t,
    "R-BUR-EXTDPD": lambda f, t: f.external_dpd_days > t,
    "R-BUR-ENQ": lambda f, t: f.enquiries_3m >= t,
    "R-OB-SALARY": lambda f, t: f.salary_interruption_flag == 1,
    "R-OB-BUFFER": lambda f, t: f.balance_buffer_months < t,
    "R-OB-INFLOW": lambda f, t: f.inflow_trend_pct <= t,
}

GRID = {
    "corporate": {
        "C-WATCH": [(None, w) for w in (1, 2)],
        "C-DOWNGRADE": [(0, w) for w in (1, 2)],
        "C-COVENANT": [(0, w) for w in (1, 2)],
        "C-DPD": [(59, w) for w in (2, 3)],
        "C-SICR": [(None, 1)],
        "C-UTIL": [(98, 1)],
        "C-DEFAULT": [(None, w) for w in (2, 3, 4, 5)],
        "C-BUR-EXTDPD": [(59, w) for w in (1, 2, 3)],
        "C-BUR-ENQ": [(t, 1) for t in (2, 3)],
        "C-OB-INFLOW": [(t, w) for t in (-20, -30) for w in (1, 2, 3)],
        "C-OB-BUFFER": [(t, w) for t in (0.75, 1.0) for w in (1, 2)],
        "C-OB-RETURNED": [(t, w) for t in (2, 3) for w in (1, 2)],
        "bands": [(5, 9, 11), (4, 7, 9), (5, 8, 10), (5, 7, 9), (6, 9, 11), (4, 8, 10)],
    },
    "retail": {
        "R-DPD": [(0, w) for w in (3, 4)],
        "R-SCORE-LOW": [("E", w) for w in (1, 2)],
        "R-SCORE-DOWN": [("2BANDS", 2)],
        "R-UTIL": [(t, w) for t in (85, 95) for w in (1, 2)],
        "R-MINPAY": [(t, w) for t in (-10, -15) for w in (1, 2)],
        "R-BUR-SCORE": [(t, w) for t in (560, 580) for w in (1, 2, 3)],
        "R-BUR-EXTDPD": [(59, w) for w in (1, 2)],
        "R-BUR-ENQ": [(5, w) for w in (1, 2)],
        "R-OB-SALARY": [(None, w) for w in (1, 2)],
        "R-OB-BUFFER": [(t, w) for t in (0.75, 1.0) for w in (1, 2)],
        "R-OB-INFLOW": [(t, w) for t in (-30, -40) for w in (1, 2)],
        "bands": [(4, 7, 9), (3, 5, 7), (4, 6, 8), (5, 7, 9), (5, 8, 10), (4, 8, 10)],
    },
}

#: The story, per level: segment -> +1 deteriorates, -1 improves.
STORY = {
    "corporate": {
        "sector": {"Construction": 1, "Real Estate": 1, "Healthcare": -1, "Power and Utilities": -1,
                   "Telecommunications": -1},
        "region": {"Makkah": 1},
        "sub_sector@Construction": {"Building Contracting": 1, "Civil Infrastructure": -1},
    },
    "retail": {
        "product": {"Credit Card": 1, "Buy Now Pay Later": 1, "Mortgage": -1, "Auto Finance": -1},
        "region": {"Qassim": 1},
    },
}


def load(domain_id: str, periods: int = 2) -> tuple[pd.DataFrame, dict]:
    spec = rd.domain_spec(domain_id)
    f = pd.read_parquet(paths.DATASETS / spec["release_id"] / spec["exposure"])
    keep = sorted(f[spec["period"]].unique())[-periods:]
    f = f[f[spec["period"]].isin(keep)].reset_index(drop=True)
    f["bad"] = ((f.dpd_days >= 90) | (f.stage == 3) | (f.default_flag == 1)).to_numpy()
    return f, spec


class Evaluator:
    """Fast owner-level evaluation of one score vector, per period and per level (numpy only)."""

    def __init__(self, f: pd.DataFrame, spec: dict, domain_id: str):
        self.f, self.spec, self.domain_id = f, spec, domain_id
        P, O = spec["period"], spec["owner_key"]
        self.periods = sorted(f[P].unique())
        self.ead = f.ead_sar_mn.fillna(0).to_numpy()
        levels = {"__book__": pd.Series("book", index=f.index)}
        for level in STORY[domain_id]:
            if "@" in level:
                col, parent = level.split("@")
                levels[level] = f[col].where(f[spec["segment"]] == parent)
            else:
                levels[level] = f[level]
        self.groups = {}
        bad_rows = f.bad.to_numpy().astype(int)
        for level, seg in levels.items():
            valid = np.flatnonzero(seg.notna().to_numpy())
            ps = (f[P].astype(str) + "|" + seg.astype(str)).to_numpy()[valid]
            ps_codes, ps_uniques = pd.factorize(ps, sort=True)
            key = pd.Series(ps).str.cat(f[O].astype(str).to_numpy()[valid], sep="|").to_numpy()
            order_local = np.argsort(key, kind="stable")
            order = valid[order_local]
            k = key[order_local]
            starts = np.flatnonzero(np.r_[True, k[1:] != k[:-1]])
            owner_ps = ps_codes[order_local][starts]
            bad = np.maximum.reduceat(bad_rows[order], starts).astype(bool)
            self.groups[level] = {"order": order, "starts": starts, "owner_ps": owner_ps, "bad": bad,
                                  "row_ps": ps_codes[order_local], "n": len(ps_uniques),
                                  "index": pd.MultiIndex.from_tuples([tuple(x.split("|", 1)) for x in ps_uniques],
                                                                     names=["period", "segment"])}

    def run(self, score: np.ndarray, bands: tuple) -> dict:
        mod, high, crit = bands
        out: dict = {}
        for level, g in self.groups.items():
            sc = score[g["order"]]
            s = np.maximum.reduceat(sc, g["starts"])
            n, c = g["n"], g["owner_ps"]
            warned, severe = s >= mod, s >= high

            def cnt(mask):
                return np.bincount(c, weights=mask.astype(float), minlength=n)
            agg = pd.DataFrame({
                "owners": np.bincount(c, minlength=n), "warned": cnt(warned), "severe": cnt(severe),
                "critical": cnt(s >= crit), "bad": cnt(g["bad"]), "bad_warned": cnt(g["bad"] & warned),
                "fwd": cnt(warned & ~g["bad"]),
                "severe_ead": np.bincount(g["row_ps"], weights=np.where(sc >= high, self.ead[g["order"]], 0.0),
                                          minlength=n)}, index=g["index"])
            out[level] = agg
        return out


def story_check(levels: dict, periods: list, domain_id: str) -> dict:
    now, prev = periods[-1], periods[-2]
    res = {}
    for level, agg in levels.items():
        if level == "__book__":
            continue
        a, b = agg.xs(now), agg.xs(prev)
        d_w = (a.warned - b.warned.reindex(a.index).fillna(0))
        d_e = (a.severe_ead - b.severe_ead.reindex(a.index).fillna(0))
        # Improving: fewer warned and no more high/critical EAD (a segment with none has none to lose).
        improving = sorted(a.index[(d_w < 0) & (d_e <= 0)])
        deteriorating = sorted(a.index[(d_w > 0) & (d_e >= 0)])
        named = STORY[domain_id][level]
        hits = sum(1 for s, v in named.items()
                   if (v > 0 and s in deteriorating) or (v < 0 and s in improving))
        res[level] = {"improving": improving, "deteriorating": deteriorating, "story_hits": hits,
                      "story_named": len(named),
                      # Sub-segment levels inside one segment carry the named story only.
                      "ok": (hits == len(named)) if "@" in level else (len(improving) >= 2 and len(deteriorating) >= 2),
                      "delta_warned": {k: int(v) for k, v in d_w.items()},
                      "delta_severe_ead_sar_mn": {k: round(float(v), 1) for k, v in d_e.items()}}
    return res


def headline(levels: dict, period: str) -> dict:
    r = levels["__book__"].xs(period).iloc[0]
    return {"owners": int(r.owners), "warned": int(r.warned), "warned_pct": 100 * r.warned / r.owners,
            "high_or_critical": int(r.severe), "high_or_critical_pct": 100 * r.severe / r.owners,
            "critical": int(r.critical), "bad": int(r.bad),
            "bad_warned_pct": 100 * r.bad_warned / r.bad if r.bad else 100.0, "forward_risk": int(r.fwd)}


def search(domain_id: str, limit: int | None = None) -> dict:
    f, spec = load(domain_id)
    ev = Evaluator(f, spec, domain_id)
    grid = GRID[domain_id]
    names = [k for k in grid if k != "bands"]
    cache = {(r, t): FIRES[r](f, t).fillna(False).to_numpy().astype(np.int16)
             for r in names for t, _ in grid[r]}
    combos = list(itertools.product(*(grid[k] for k in names)))
    rng = np.random.default_rng(130)
    if limit and len(combos) > limit:
        combos = [combos[i] for i in sorted(rng.choice(len(combos), size=limit, replace=False))]
    best, best_key, tried, meeting = None, None, 0, 0
    lo, hi = TARGET_WARNED
    for combo in combos:
        score = sum(cache[(r, t)] * w for r, (t, w) in zip(names, combo))
        for bands in grid["bands"]:
            tried += 1
            levels = ev.run(score, bands)
            h = headline(levels, ev.periods[-1])
            if not (lo <= h["warned_pct"] <= hi and h["high_or_critical_pct"] < TARGET_SEVERE
                    and h["bad_warned_pct"] >= 100.0 and h["critical"] > 0):
                continue
            meeting += 1
            st = story_check(levels, ev.periods, domain_id)
            ok = all(v["ok"] for v in st.values())
            hits = sum(v["story_hits"] for v in st.values())
            key = (ok, hits, h["forward_risk"])
            if best_key is None or key > best_key:
                best_key = key
                best = {"rules": dict(zip(names, combo)), "bands": bands, "headline": h, "story": st}
    return {"domain_id": domain_id, "combinations": tried, "meeting_targets_and_constraints": meeting,
            "best": best, "periods": ev.periods}


def check() -> dict:
    """The live release as built: targets, constraints and the story, from its own ews_score."""
    from backend.ews_domain import ews_rules as ews
    out = {}
    for d in ("corporate", "retail"):
        f, spec = load(d)
        ev = Evaluator(f, spec, d)
        levels = ev.run(f.ews_score.fillna(0).to_numpy().astype(int), ews.BAND_FLOORS[d])
        h = headline(levels, ev.periods[-1])
        st = story_check(levels, ev.periods, d)
        lo, hi = TARGET_WARNED
        ok = (lo <= h["warned_pct"] <= hi and h["high_or_critical_pct"] < TARGET_SEVERE
              and h["bad_warned_pct"] >= 100.0 and h["critical"] > 0
              and all(v["ok"] for k, v in st.items() if "@" not in k)
              and all(v["story_hits"] == v["story_named"] for v in st.values()))
        out[d] = {"ok": ok, "headline": h, "story": st}
    return out


def main(argv: list[str]) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    if "--check" in argv:
        res = check()
        print(json.dumps({d: {"ok": r["ok"], "headline": r["headline"],
                              "story": {k: {x: v[x] for x in ("improving", "deteriorating", "story_hits",
                                                              "story_named")} for k, v in r["story"].items()}}
                          for d, r in res.items()}, indent=1, default=str))
        return 0 if all(r["ok"] for r in res.values()) else 1
    limit = int(argv[argv.index("--limit") + 1]) if "--limit" in argv else None
    report = {"ruleset": "gw-ews-1.3.0", "previous": "gw-ews-1.2.0",
              "targets": {"warned_pct": TARGET_WARNED, "high_or_critical_pct_below": TARGET_SEVERE},
              "constraints": ["every already-bad owner warned", "no rule switched off", "critical band not empty",
                              "at least 2 improving and 2 deteriorating segments per level"],
              "story": STORY, "books": {}}
    for d in ("corporate", "retail"):
        r = search(d, limit)
        report["books"][d] = r
        b = r["best"]
        print(d, r["combinations"], r["meeting_targets_and_constraints"],
              json.dumps(b and {"rules": b["rules"], "bands": b["bands"], "headline": b["headline"],
                                "story": {k: {x: v[x] for x in ("improving", "deteriorating", "story_hits", "ok")}
                                          for k, v in b["story"].items()}}, default=str))
    (OUT / "ruleset_1_3_0.json").write_text(json.dumps(report, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
