"""Proposed recalibration of gw-ews-1.0.0 -- ANALYSIS ONLY, nothing is applied.

Searches thresholds, weights and band cut-offs (every rule keeps its meaning:
same column, same direction) for each book, against the targets the user set:
about 10-20% of customers warned (moderate or worse) and under 7% high or
critical, at the as-of period. Counting is the drill's: a customer's score is
the worst score among its exposures.

One constraint is added and stated: every customer that is already bad (90+
DPD, Stage 3 or default) must still be warned -- a recalibration that stops
warning on defaulted names would hit any target and mean nothing.

Writes evidence/v5/ews/calibration/{proposal.json, PROPOSAL.md}. Never edits
ews_rules.py.
"""
from __future__ import annotations

import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

from backend.ews_domain import ews_rules as ews
from backend.ews_domain import paths, reader as rd

OUT = paths.V5 / "evidence" / "v5" / "ews" / "calibration"
TARGET_WARNED = (10.0, 20.0)
TARGET_SEVERE = 7.0

# Each rule: the column it reads, its current threshold, and the thresholds the
# search may move it to -- same column, same direction, so the meaning holds.
CURRENT = {
    "corporate": {
        "rules": {"C-WATCH": (None, 3), "C-DOWNGRADE": (0, 2), "C-COVENANT": (0, 2),
                  "C-DPD": (0, 3), "C-SICR": (None, 2), "C-UTIL": (90, 1)},
        "bands": (2, 4, 6),
    },
    "retail": {
        "rules": {"R-DPD": (0, 3), "R-SCORE-LOW": ("DE", 1), "R-SCORE-DOWN": ("Deteriorated", 2),
                  "R-UTIL": (85, 2), "R-MINPAY": (35, 1), "R-SALARY": (None, 2)},
        "bands": (2, 4, 6),
    },
}

GRID = {
    "corporate": {
        "C-WATCH": [(None, w) for w in (1, 2, 3)],
        "C-DOWNGRADE": [(0, w) for w in (1, 2)],
        "C-COVENANT": [(0, w) for w in (1, 2)],
        "C-DPD": [(t, w) for t in (0, 59) for w in (2, 3, 4)],
        "C-SICR": [(None, w) for w in (1, 2)],
        "C-UTIL": [(t, w) for t in (90, 95, 98) for w in (0, 1)],
        "bands": [(2, 4, 6), (3, 5, 7), (3, 6, 8), (4, 6, 8), (4, 7, 9)],
    },
    "retail": {
        "R-DPD": [(t, w) for t in (0, 9, 29) for w in (2, 3, 4)],
        "R-SCORE-LOW": [(s, w) for s in ("DE", "E") for w in (1, 2)],
        "R-UTIL": [(t, w) for t in (85, 95, 100) for w in (1, 2)],
        "R-MINPAY": [(t, w) for t in (35, 30, 25) for w in (0, 1)],
        "bands": [(2, 4, 6), (3, 5, 7), (3, 6, 8), (4, 6, 8)],
    },
}


def load(domain_id: str) -> tuple[pd.DataFrame, dict]:
    spec = rd.domain_spec(domain_id)
    f = pd.read_parquet(paths.DATASETS / spec["release_id"] / spec["exposure"])
    f = f[f[spec["period"]] == f[spec["period"]].max()].copy()
    f = _with_previous_band(f, spec, domain_id)
    f["bad"] = (f.dpd_days >= 90) | (f.stage == 3) | (f.default_flag == 1)
    return f, spec


def fires(f: pd.DataFrame, domain_id: str, rule: str, threshold) -> np.ndarray:
    if domain_id == "corporate":
        return {"C-WATCH": lambda: f.watchlist_flag == 1,
                "C-DOWNGRADE": lambda: f.rating_notches_moved > threshold,
                "C-COVENANT": lambda: f.covenant_breaches > threshold,
                "C-DPD": lambda: f.dpd_days > threshold,
                "C-SICR": lambda: f.sicr_flag == 1,
                "C-UTIL": lambda: f.utilisation_pct >= threshold,
                # gw-ews-1.1.0 (INBOX Item 1.2): Stage 3 or the default flag.
                "C-DEFAULT": lambda: (f.stage == 3) | (f.default_flag == 1)}[rule]().fillna(False).to_numpy()
    return {"R-DPD": lambda: f.dpd_days > threshold,
            "R-SCORE-LOW": lambda: f.score_band.isin(list(threshold)),
            # As published: compares to 'Deteriorated'; the book writes
            # 'DETERIORATED', so this never fires. Reported, not changed.
            "R-SCORE-DOWN": lambda: (f.score_migration == threshold if threshold != "2BANDS"
                                     else _band_fall(f) >= 2),
            "R-UTIL": lambda: f.utilisation_pct >= threshold,
            "R-MINPAY": lambda: f.payment_ratio_pct < threshold,
            # Needs employer_sector_group, which the book does not publish.
            "R-SALARY": lambda: pd.Series(False, index=f.index)}[rule]().fillna(False).to_numpy()


def _with_previous_band(f: pd.DataFrame, spec: dict, domain_id: str) -> pd.DataFrame:
    """Releases built before gw-ews-1.1.0 lack the customer's previous band; take it from the owner file."""
    if domain_id != "retail" or "customer_score_band_previous" in f:
        return f
    o = pd.read_parquet(paths.DATASETS / spec["release_id"] / spec["owner"],
                        columns=[spec["period"], spec["owner_key"], "score_band_previous"])
    o = o.rename(columns={"score_band_previous": "customer_score_band_previous"})
    return f.merge(o, on=[spec["period"], spec["owner_key"]], how="left")


BAND_ORDER = {b: i for i, b in enumerate("ABCDE")}


def _band_fall(f: pd.DataFrame) -> pd.Series:
    """Behaviour bands fallen since last month (A best .. E worst), customer grain."""
    return (f.customer_score_band.map(BAND_ORDER) - f.customer_score_band_previous.map(BAND_ORDER)).fillna(0)


def evaluate(f, spec, domain_id, rules: dict, bands: tuple) -> dict:
    score = np.zeros(len(f), dtype=int)
    fired = {}
    for rule, (threshold, weight) in rules.items():
        hit = fires(f, domain_id, rule, threshold)
        fired[rule] = hit
        score = score + hit * weight
    o = spec["owner_key"]
    frame = pd.DataFrame({"owner": f[o].to_numpy(), "score": score, "bad": f.bad.to_numpy()})
    owners = frame.groupby("owner").agg(score=("score", "max"), bad=("bad", "any"))
    mod, high, crit = bands
    band = np.select([owners.score >= crit, owners.score >= high, owners.score >= mod, owners.score >= 1],
                     ["critical", "high", "moderate", "low"], "none")
    n = len(owners)
    counts = pd.Series(band).value_counts().reindex(["critical", "high", "moderate", "low", "none"], fill_value=0)
    warned = int((owners.score >= mod).sum())
    severe = int((owners.score >= high).sum())
    rule_owners = {r: int(frame.loc[h, "owner"].nunique()) for r, h in fired.items()}
    return {"customers": n, "warned": warned, "warned_pct": 100 * warned / n,
            "high_or_critical": severe, "high_or_critical_pct": 100 * severe / n,
            "bad": int(owners.bad.sum()), "bad_warned_pct": 100 * float((owners.score[owners.bad] >= mod).mean()),
            "bad_high_or_critical_pct": 100 * float((owners.score[owners.bad] >= high).mean()),
            "forward_risk": int(((owners.score >= mod) & ~owners.bad).sum()),
            "bands": {k: int(v) for k, v in counts.items()},
            "rule_customers": rule_owners}


def search(domain_id: str):
    """Every combination in the grid, evaluated; returns the ranked choice and the frontier."""
    f, spec = load(domain_id)
    base = CURRENT[domain_id]
    names = [k for k in GRID[domain_id] if k != "bands"]
    fixed = {k: v for k, v in base["rules"].items() if k not in names}
    lo, hi = TARGET_WARNED
    rows = []
    for combo in itertools.product(*(GRID[domain_id][k] for k in names), GRID[domain_id]["bands"]):
        rules = {**fixed, **dict(zip(names, combo[:-1]))}
        bands = combo[-1]
        r = evaluate(f, spec, domain_id, rules, bands)
        r["changes"] = sum(rules[k] != base["rules"][k] for k in rules) + (bands != base["bands"])
        r["meets"] = lo <= r["warned_pct"] <= hi and r["high_or_critical_pct"] < TARGET_SEVERE
        rows.append((rules, bands, r))

    def rank(item):
        r = item[2]
        miss = (max(0.0, r["high_or_critical_pct"] - TARGET_SEVERE) + max(0.0, r["warned_pct"] - hi)
                + max(0.0, lo - r["warned_pct"]))
        # Meet the targets; keep every already-bad customer warned; put as many
        # of them as possible in high/critical; keep a non-empty critical band;
        # land the warned rate near the middle; change as little as possible.
        rules, _, _ = item
        dpd = rules["C-DPD" if domain_id == "corporate" else "R-DPD"]
        # An early-warning set keeps its earliest signal (the first missed
        # payment, DPD > 0) and switches no rule off (weight 0).
        early = 0 if dpd[0] == 0 else 1
        silenced = sum(1 for k, (_, w) in rules.items() if w == 0 and k in GRID[domain_id])
        return (0 if r["meets"] else 1, round(miss, 1), -round(r["bad_warned_pct"], 1), early, silenced,
                -round(r["bad_high_or_critical_pct"], 0), 0 if r["bands"]["critical"] else 1,
                round(abs(r["warned_pct"] - 15.0), 0), r["changes"])

    keep_bad = [x for x in rows if x[2]["bad_warned_pct"] >= 100.0]
    best = min(keep_bad or rows, key=rank)
    frontier = {
        "lowest_warned_pct_keeping_every_bad_customer_warned":
            round(min(x[2]["warned_pct"] for x in keep_bad), 1) if keep_bad else None,
        "combinations_meeting_targets": sum(x[2]["meets"] for x in rows),
        "combinations_meeting_targets_and_keeping_bad_warned": sum(x[2]["meets"] for x in keep_bad),
    }
    meeting = [x for x in rows if x[2]["meets"]]
    if meeting:
        alt = max(meeting, key=lambda x: (x[2]["bad_warned_pct"], -x[2]["changes"]))
        frontier["best_if_targets_are_forced"] = {
            "rules": {k: list(v) for k, v in alt[0].items()}, "bands": alt[1],
            "warned_pct": round(alt[2]["warned_pct"], 1),
            "high_or_critical_pct": round(alt[2]["high_or_critical_pct"], 1),
            "already_bad_still_warned_pct": round(alt[2]["bad_warned_pct"], 1)}
    before = evaluate(f, spec, domain_id, base["rules"], base["bands"])
    return f, spec, before, best, frontier


def stability(domain_id: str, rules: dict, bands: tuple) -> list[dict]:
    spec = rd.domain_spec(domain_id)
    all_f = pd.read_parquet(paths.DATASETS / spec["release_id"] / spec["exposure"])
    all_f = _with_previous_band(all_f, spec, domain_id)
    all_f["bad"] = (all_f.dpd_days >= 90) | (all_f.stage == 3) | (all_f.default_flag == 1)
    out = []
    for period in sorted(all_f[spec["period"]].unique())[-4:]:
        f = all_f[all_f[spec["period"]] == period]
        r = evaluate(f, spec, domain_id, rules, bands)
        out.append({"period": period, "warned_pct": round(r["warned_pct"], 1),
                    "high_or_critical_pct": round(r["high_or_critical_pct"], 1)})
    return out


# ------------------------------------------------------- gw-ews-1.1.0
# INBOX Item 1 (Anne, 2026-10-10). Retail: the section 7 proposal as it stands,
# plus R-SCORE-DOWN limited to a fall of 2 or more behaviour bands (Item 1.3).
# Corporate: one new rule, C-DEFAULT (Stage 3 or default flag), and the same
# search, targets and constraints as before.
RETAIL_110 = {"rules": {"R-DPD": (0, 4), "R-SCORE-LOW": ("E", 1), "R-SCORE-DOWN": ("2BANDS", 2),
                        "R-UTIL": (85, 2), "R-MINPAY": (30, 1), "R-SALARY": (None, 2)},
              "bands": (3, 5, 7)}
GRID_CORP_110 = {**{k: v for k, v in GRID["corporate"].items() if k != "bands"},
                 "C-DEFAULT": [(None, w) for w in (2, 3, 4, 5, 6, 7)],
                 "bands": GRID["corporate"]["bands"]}


def search_110_corporate():
    """Every combination with C-DEFAULT; hard constraints, then the same ranking as `search`."""
    d = "corporate"
    f, spec = load(d)
    names = [k for k in GRID_CORP_110 if k != "bands"]
    lo, hi = TARGET_WARNED
    base = {**CURRENT[d]["rules"], "C-DEFAULT": (None, 0)}
    rows = []
    for combo in itertools.product(*(GRID_CORP_110[k] for k in names), GRID_CORP_110["bands"]):
        rules, bands = dict(zip(names, combo[:-1])), combo[-1]
        r = evaluate(f, spec, d, rules, bands)
        r["changes"] = sum(rules[k] != base[k] for k in rules) + (bands != CURRENT[d]["bands"])
        r["meets"] = lo <= r["warned_pct"] <= hi and r["high_or_critical_pct"] < TARGET_SEVERE
        r["silenced"] = sum(1 for _, w in rules.values() if w == 0)
        r["valid"] = r["bad_warned_pct"] >= 100.0 and r["silenced"] == 0 and r["bands"]["critical"] > 0
        rows.append((rules, bands, r))

    def miss(r):
        return (max(0.0, r["high_or_critical_pct"] - TARGET_SEVERE) + max(0.0, r["warned_pct"] - hi)
                + max(0.0, lo - r["warned_pct"]))

    def rank(item):
        rules, _, r = item
        early = 0 if rules["C-DPD"][0] == 0 else 1
        return (0 if r["meets"] else 1, round(miss(r), 1), early, -round(r["bad_high_or_critical_pct"], 0),
                round(abs(r["warned_pct"] - 15.0), 0), r["changes"])

    valid = [x for x in rows if x[2]["valid"]]
    best = min(valid or rows, key=rank)
    frontier = {"combinations": len(rows),
                "combinations_meeting_targets": sum(x[2]["meets"] for x in rows),
                "combinations_meeting_targets_and_all_constraints": sum(x[2]["meets"] for x in valid),
                "lowest_warned_pct_with_all_constraints":
                    round(min(x[2]["warned_pct"] for x in valid), 1) if valid else None}
    return f, spec, best, frontier


def main_110() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    report = {"ruleset": "gw-ews-1.1.0", "previous": "gw-ews-1.0.0", "targets": {
        "warned_pct": TARGET_WARNED, "high_or_critical_pct_below": TARGET_SEVERE,
        "constraints": ["every already-bad customer stays warned", "no rule switched off (weight 0)",
                        "critical band not empty"]}, "books": {}}
    f, spec, (rules, bands, after), frontier = search_110_corporate()
    before = evaluate(f, spec, "corporate", CURRENT["corporate"]["rules"], CURRENT["corporate"]["bands"])
    report["books"]["corporate"] = {
        "as_of": str(f[spec["period"]].max()), "frontier": frontier, "meets_targets": bool(after["meets"]),
        "before": {"rules": {k: list(v) for k, v in CURRENT["corporate"]["rules"].items()},
                   "band_floors": CURRENT["corporate"]["bands"], **before},
        "after": {"rules": {k: list(v) for k, v in rules.items()}, "band_floors": bands, **after},
        "stability_before": stability("corporate", CURRENT["corporate"]["rules"], CURRENT["corporate"]["bands"]),
        "stability_after": stability("corporate", rules, bands)}
    f, spec = load("retail")
    before = evaluate(f, spec, "retail", CURRENT["retail"]["rules"], CURRENT["retail"]["bands"])
    after = evaluate(f, spec, "retail", RETAIL_110["rules"], RETAIL_110["bands"])
    after["meets"] = (TARGET_WARNED[0] <= after["warned_pct"] <= TARGET_WARNED[1]
                      and after["high_or_critical_pct"] < TARGET_SEVERE)
    report["books"]["retail"] = {
        "as_of": str(f[spec["period"]].max()), "meets_targets": bool(after["meets"]),
        "before": {"rules": {k: list(v) for k, v in CURRENT["retail"]["rules"].items()},
                   "band_floors": CURRENT["retail"]["bands"], **before},
        "after": {"rules": {k: list(v) for k, v in RETAIL_110["rules"].items()},
                  "band_floors": RETAIL_110["bands"], **after},
        "stability_before": stability("retail", CURRENT["retail"]["rules"], CURRENT["retail"]["bands"]),
        "stability_after": stability("retail", RETAIL_110["rules"], RETAIL_110["bands"])}
    for d, b in report["books"].items():
        a = b["after"]
        print(d, "meets" if b["meets_targets"] else "DOES NOT MEET", f"warned {a['warned_pct']:.1f}%",
              f"high/crit {a['high_or_critical_pct']:.1f}%", f"bad warned {a['bad_warned_pct']:.1f}%",
              "floors", a["band_floors"], a["rules"], a["bands"], b.get("frontier", ""))
    (OUT / "ruleset_1_1_0.json").write_text(json.dumps(report, indent=1, default=str))
    return 0


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    report = {"ruleset": ews.RULESET_VERSION, "applied": False, "targets": {
        "warned_pct": TARGET_WARNED, "high_or_critical_pct_below": TARGET_SEVERE,
        "constraint": "every already-bad customer stays warned"}, "books": {}}
    for d in ("corporate", "retail"):
        f, spec, before, best, frontier = search(d)
        rules, bands, after = best
        report["books"][d] = {
            "as_of": str(f[spec["period"]].max()), "frontier": frontier,
            "meets_targets": bool(after["meets"]),
            "before": {"rules": {k: list(v) for k, v in CURRENT[d]["rules"].items()},
                       "bands": CURRENT[d]["bands"], **before},
            "after": {"rules": {k: list(v) for k, v in rules.items()}, "bands": bands, **after},
            "stability_after": stability(d, rules, bands),
            "stability_before": stability(d, CURRENT[d]["rules"], CURRENT[d]["bands"]),
        }
        print(d, "meets" if after["meets"] else "DOES NOT MEET", f"warned {before['warned_pct']:.1f}% -> {after['warned_pct']:.1f}%",
              f"high/crit {before['high_or_critical_pct']:.1f}% -> {after['high_or_critical_pct']:.1f}%",
              "bands", bands, {k: v for k, v in rules.items() if v != CURRENT[d]['rules'][k]}, frontier)
    (OUT / "proposal.json").write_text(json.dumps(report, indent=1, default=str))
    return 0




# ------------------------------------------------------- gw-ews-1.2.0
# INBOX Item 3, phase A5: Bureau and Open Banking go live. The 1.1.0 internal
# rules keep their thresholds and weights; the search sets the new external
# rules' thresholds and weights and the band floors, under the same targets and
# constraints, and prefers the set that warns the most still-performing names
# (forward risk), since that is what external signals add.
EXT_FIRES = {
    "R-BUR-SCORE": lambda f, t: f.bureau_score < t,
    "R-BUR-EXTDPD": lambda f, t: f.external_dpd_days > t,
    "R-BUR-ENQ": lambda f, t: f.enquiries_3m >= t,
    "R-OB-SALARY": lambda f, t: f.salary_interruption_flag == 1,
    "R-OB-BUFFER": lambda f, t: f.balance_buffer_months < t,
    "R-OB-INFLOW": lambda f, t: f.inflow_trend_pct <= t,
    "C-BUR-EXTDPD": lambda f, t: f.external_dpd_days > t,
    "C-OB-INFLOW": lambda f, t: f.inflow_trend_pct <= t,
}
FIXED_110 = {
    "retail": {"R-DPD": (0, 4), "R-SCORE-LOW": ("E", 1), "R-SCORE-DOWN": ("2BANDS", 2),
               "R-UTIL": (85, 2), "R-MINPAY": (30, 1)},
    "corporate": {"C-WATCH": (None, 1), "C-DOWNGRADE": (0, 2), "C-COVENANT": (0, 1), "C-DPD": (59, 2),
                  "C-SICR": (None, 1), "C-UTIL": (95, 1), "C-DEFAULT": (None, 2)},
}
GRID_120 = {
    "retail": {"R-BUR-SCORE": [(t, w) for t in (560, 580, 600) for w in (1, 2, 3)],
               "R-BUR-EXTDPD": [(t, w) for t in (29, 59) for w in (1, 2, 3)],
               "R-BUR-ENQ": [(t, w) for t in (4, 5) for w in (1, 2)],
               "R-OB-SALARY": [(None, w) for w in (1, 2, 3)],
               "R-OB-BUFFER": [(t, w) for t in (0.75, 1.0) for w in (1, 2)],
               "R-OB-INFLOW": [(t, w) for t in (-30, -40) for w in (1, 2)],
               "bands": [(3, 5, 7), (4, 6, 8), (4, 7, 9), (5, 7, 9), (5, 8, 10)]},
    # Corporate: the 1.1.0 internal rules re-enter the search (weights > 0 only;
    # with them fixed, none of 180 combinations met every constraint).
    "corporate": {"C-WATCH": [(None, w) for w in (1, 2, 3)],
                  "C-DOWNGRADE": [(0, w) for w in (1, 2)],
                  "C-COVENANT": [(0, w) for w in (1, 2)],
                  "C-DPD": [(t, w) for t in (0, 59) for w in (2, 3, 4)],
                  "C-SICR": [(None, w) for w in (1, 2)],
                  "C-UTIL": [(t, 1) for t in (90, 95, 98)],
                  "C-DEFAULT": [(None, w) for w in (2, 3, 4, 5, 6, 7)],
                  "C-BUR-EXTDPD": [(t, w) for t in (29, 59) for w in (1, 2, 3)],
                  "C-OB-INFLOW": [(t, w) for t in (-20, -25) for w in (1, 2, 3)],
                  "bands": [(4, 7, 9), (4, 6, 8), (5, 7, 9), (5, 8, 10), (3, 6, 8), (5, 9, 11), (6, 9, 11), (4, 8, 10), (5, 8, 11)]},
}


def _fire_120(f: pd.DataFrame, domain_id: str, rule: str, t, as_run_110: bool = False) -> np.ndarray:
    # C-DOWNGRADE: the book writes rating_notches_moved POSITIVE for an upgrade
    # and NEGATIVE for a downgrade (rating_migration agrees on every row). Up to
    # 1.1.0 the rule tested "> 0" and so fired on upgrades. 1.2.0 tests "< 0".
    if rule == "C-DOWNGRADE" and not as_run_110:
        return (f.rating_notches_moved < -t).fillna(False).to_numpy()
    if rule in EXT_FIRES:
        return EXT_FIRES[rule](f, t).fillna(False).to_numpy()
    return fires(f, domain_id, rule, t)


def _fast(f: pd.DataFrame, spec: dict):
    """Owner boundaries for a frame sorted by owner, and per-owner already-bad."""
    o = f[spec["owner_key"]].to_numpy()
    starts = np.flatnonzero(np.r_[True, o[1:] != o[:-1]])
    bad = np.maximum.reduceat(f.bad.to_numpy().astype(int), starts).astype(bool)
    return o, starts, bad


def _eval_fast(score: np.ndarray, starts: np.ndarray, bad: np.ndarray, bands: tuple) -> dict:
    s = np.maximum.reduceat(score, starts)
    mod, high, crit = bands
    n = len(s)
    warned, severe = s >= mod, s >= high
    return {"customers": n, "warned": int(warned.sum()), "warned_pct": 100 * warned.mean(),
            "high_or_critical": int(severe.sum()), "high_or_critical_pct": 100 * severe.mean(),
            "critical": int((s >= crit).sum()), "bad": int(bad.sum()),
            "bad_warned_pct": 100 * float(warned[bad].mean()), "forward_risk": int((warned & ~bad).sum())}


def search_120(domain_id: str):
    f, spec = load(domain_id)
    f = f.sort_values(spec["owner_key"], kind="stable").reset_index(drop=True)
    _, starts, bad = _fast(f, spec)
    grid = GRID_120[domain_id]
    fixed = {k: v for k, v in FIXED_110[domain_id].items() if k not in grid}
    base = sum((_fire_120(f, domain_id, r, t).astype(int) * w for r, (t, w) in fixed.items()),
               np.zeros(len(f), dtype=int))
    names = [k for k in grid if k != "bands"]
    cache = {(r, t): _fire_120(f, domain_id, r, t).astype(int) for r in names for t, _ in grid[r]}
    lo, hi = TARGET_WARNED
    rows = []
    for combo in itertools.product(*(grid[k] for k in names), grid["bands"]):
        rules, bands = dict(zip(names, combo[:-1])), combo[-1]
        score = base + sum(cache[(r, t)] * w for r, (t, w) in rules.items())
        r = _eval_fast(score, starts, bad, bands)
        r["meets"] = lo <= r["warned_pct"] <= hi and r["high_or_critical_pct"] < TARGET_SEVERE
        r["valid"] = r["bad_warned_pct"] >= 100.0 and r["critical"] > 0
        rows.append((rules, bands, r))
    valid = [x for x in rows if x[2]["valid"]]

    def rank(item):
        rules, bands, r = item
        miss = (max(0.0, r["high_or_critical_pct"] - TARGET_SEVERE) + max(0.0, r["warned_pct"] - hi)
                + max(0.0, lo - r["warned_pct"]))
        changes = sum(1 for k, v in rules.items() if FIXED_110[domain_id].get(k) != v)
        return (0 if r["meets"] else 1, round(miss, 1), -r["forward_risk"], changes)

    best = min(valid or rows, key=rank)
    frontier = {"combinations": len(rows), "meeting_targets": sum(x[2]["meets"] for x in rows),
                "meeting_targets_and_constraints": sum(x[2]["meets"] for x in valid)}
    return f, spec, {**fixed, **best[0]}, best[1], frontier


def evaluate_120(domain_id: str, rules: dict, bands: tuple, period: str | None = None,
                 as_run_110: bool = False) -> dict:
    spec = rd.domain_spec(domain_id)
    f = pd.read_parquet(paths.DATASETS / spec["release_id"] / spec["exposure"])
    p = period or f[spec["period"]].max()
    f = f[f[spec["period"]] == p].copy()
    f = _with_previous_band(f, spec, domain_id)
    f["bad"] = (f.dpd_days >= 90) | (f.stage == 3) | (f.default_flag == 1)
    f = f.sort_values(spec["owner_key"], kind="stable").reset_index(drop=True)
    o, starts, bad = _fast(f, spec)
    hits = {r: _fire_120(f, domain_id, r, t, as_run_110) for r, (t, _) in rules.items()}
    score = sum(hits[r].astype(int) * w for r, (_, w) in rules.items())
    out = _eval_fast(score, starts, bad, bands)
    s = np.maximum.reduceat(score, starts)
    mod, high, crit = bands
    out["bands"] = {"critical": int((s >= crit).sum()), "high": int(((s >= high) & (s < crit)).sum()),
                    "moderate": int(((s >= mod) & (s < high)).sum()), "low": int(((s >= 1) & (s < mod)).sum()),
                    "none": int((s == 0).sum())}
    out["bad_high_or_critical_pct"] = 100 * float((s >= high)[bad].mean())
    out["rule_customers"] = {r: int(pd.Series(o[h]).nunique()) for r, h in hits.items()}
    out["period"] = str(p)
    return out


def main_120() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    report = {"ruleset": "gw-ews-1.2.0", "previous": "gw-ews-1.1.0", "targets": {
        "warned_pct": TARGET_WARNED, "high_or_critical_pct_below": TARGET_SEVERE,
        "constraints": ["every already-bad customer stays warned", "no rule switched off (weight 0)",
                        "critical band not empty"],
        "preference": "the most still-performing names warned (forward risk)"}, "books": {}}
    for d in ("corporate", "retail"):
        f, spec, rules, bands, frontier = search_120(d)
        before_rules = {**FIXED_110[d], **({"R-SALARY": (None, 2)} if d == "retail" else {})}
        before_bands = (4, 7, 9) if d == "corporate" else (3, 5, 7)
        periods = sorted(pd.read_parquet(paths.DATASETS / spec["release_id"] / spec["exposure"],
                                         columns=[spec["period"]])[spec["period"]].unique())[-6:]
        report["books"][d] = {
            "as_of": periods[-1], "frontier": frontier,
            "before": {"rules": {k: list(v) for k, v in before_rules.items()}, "band_floors": before_bands,
                       **evaluate_120(d, {k: v for k, v in before_rules.items() if k != "R-SALARY"}, before_bands,
                                      as_run_110=True)},
            "after": {"rules": {k: list(v) for k, v in rules.items()}, "band_floors": bands,
                      **evaluate_120(d, rules, bands)},
            "stability_after": [{k: v for k, v in evaluate_120(d, rules, bands, p).items()
                                 if k in ("period", "warned_pct", "high_or_critical_pct", "bad_warned_pct",
                                          "forward_risk")} for p in periods],
        }
        a = report["books"][d]["after"]
        print(d, frontier, f"warned {a['warned_pct']:.1f}% hc {a['high_or_critical_pct']:.1f}% "
              f"bad {a['bad_warned_pct']:.1f}% fwd {a['forward_risk']} crit {a['critical']}", bands,
              {k: v for k, v in rules.items() if k not in FIXED_110[d]})
    (OUT / "ruleset_1_2_0.json").write_text(json.dumps(report, indent=1, default=str))
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main_120() if "--v120" in sys.argv else main_110() if "--v110" in sys.argv else main())
