"""The corporate book's Early Warning story: a recorded regeneration step (PLAN_R5 Session E).

WHY (docs/v5/EWS_STORY.md section 1). The corporate generator applies one portfolio-wide stress
path: in 2026Q2 the current-bad population doubles in EVERY sector and region (default-entry
1.99% -> 8.16%), so every Early Warning card rises and a client cannot see where the problem is.
The default-entry rate and the already-bad population are the book's own, so the story cannot be
made inside Early Warning alone.

WHAT. One deterministic overlay on the 2026Q2 rows of the ORIGINAL (unscaled) book, applied
before the rescale, so the lake stays exactly `story(original) x 0.01`:

  * DETERIORATING, untouched: Construction everywhere, Real Estate outside Makkah (Riyadh and the
    Eastern Province), and Hospitality in Makkah (so Makkah deteriorates through Construction and
    Hospitality after the season). Their 2026Q2
    rows keep the book's wave byte for byte.
  * IMPROVING: Healthcare, Power and Utilities, Telecommunications: every 2026Q2
    worsening is reverted to the facility's 2026Q1 risk state, and a share of the borrowers bad or
    in Stage 2 at 2026Q1 cure (Stage 2 probation, or Stage 1).
  * STABLE: every other sector: 30% of the newly defaulted borrowers stay in default, the rest are
    reverted, and as many borrowers bad at 2026Q1 cure, so the sector's current-bad count holds at its
    2026Q1 level with defaults and cures both flowing.
  * PROTECTED everywhere: the collateral and covenant relations, every amount that is not a risk
    amount (limit, drawn, undrawn, EAD) and financials; ratings only where stage and rating must stay consistent. Construction's rows are
    untouched, so the Cockpit's first attention item keeps its figure; Receivables LTV and Current
    Ratio covenant breaches read only protected relations. Supply Chain Finance and Makkah keep
    their direction but rise by less (the wave is largely Supply Chain Finance defaults spread
    across every sector); docs/v5/EWS_STORY.md lists every changed Cockpit figure.

"Revert" copies the facility's 2026Q1 risk fields (stage, SICR, default, DPD, past-due, PDs, LGD,
cure flag) and its 2026Q1 risk-amount RATIOS (ECL 12m / lifetime / booked, coverage, write-off,
recovery, each over EAD) onto its 2026Q2 EAD; quarters_in_stage counts on. On the borrower row the
2026Q1 watchlist state is carried forward and the 2026Q1 rating is restored; for reverted and cured borrowers
the rating is then lifted, where needed, to the best grade the borrower's lowest stage allows under the bank's
staging policy (CC or worse is Stage 3; CCC is Stage 2), so stage and rating stay consistent. "Cure" sets Stage 2 (from 3) or Stage 1 (from 2), clears
default, DPD and past-due, sets the cure flag, takes the sector's median 2026Q2 PDs for that stage
and the book's own ECL arithmetic on the facility's LGD and EAD. Nothing else changes; every other quarter is byte-identical.

Usage:
    python ops/ews_story_book.py            # rebuild the lake from data/reference/original
    python ops/ews_story_book.py --dry-run  # print the effect, write nothing
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

V5 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V5))

RELEASE = "v4-saudi-corporate-20q-v4"
REFERENCE = V5 / "data" / "reference" / "original" / RELEASE
LAKE = V5 / "data" / "cockpit_v4_lake" / RELEASE
EVIDENCE = V5 / "evidence" / "v5" / "ews" / "story"
AS_OF, PRIOR = "2026Q2", "2026Q1"
STORY_VERSION = "ews-story-1"
SALT = "gw-ews-1.3.0/story"

DETERIORATING_SECTORS = ("Construction", "Real Estate")
#: Construction keeps its wave in every region; Real Estate outside Makkah (its stress is
#: Riyadh and the Eastern Province), so Makkah is Construction and Hospitality.
DETERIORATING_EVERYWHERE = ("Construction", "Real Estate", "Hospitality")
DETERIORATING_REGIONS = ("Makkah",)
#: In the deteriorating region, these sectors keep the wave too (the season's end in Makkah).
DETERIORATING_REGION_SECTORS = ("Construction", "Hospitality")
IMPROVING_SECTORS = ("Healthcare", "Power and Utilities", "Telecommunications")
PROTECTED_PRODUCTS: tuple[str, ...] = ()
#: Cures never touch Supply Chain Finance lines: the programme's stress is the Cockpit's second
#: attention item and stays visible.
CURE_SKIP_PRODUCTS = ("supply_chain_finance",)
#: Improving sectors: share of borrowers bad / in Stage 2 at 2026Q1 that cure in 2026Q2.
CURE_SHARE = {"bad": 0.60, "stage2": 0.40}
#: Stable sectors: current-bad target at 2026Q2 as a multiple of 2026Q1 (outside Makkah).
STABLE_BAD_RATIO = 1.0
#: Stable sectors: share of the 2026Q2 new defaults that stay (offset by as many cures).
STABLE_KEEP_NEW = 0.3

#: Borrowers named anywhere in v5 (Deal Desk proposals, seeded memos, mail, tests, UAT scripts): their
#: rows are never changed, so every seeded figure about them stays true. Found with
#: grep -E "CB[0-9]{5}" over backend, tests, ops, data/dealdesk, frontend and docs.
PROTECTED_BORROWERS = frozenset((
    "CB00001", "CB00063", "CB00412", "CB00732", "CB00773", "CB00797", "CB00800", "CB00808",
    "CB00938", "CB01025", "CB01045", "CB01080", "CB01127", "CB01143", "CB01159", "CB01284",
    "CB01312", "CB01333", "CB01338", "CB01399", "CB02729", "CB03886", "CB04043", "CB04673",
    "CB04714", "CB04716", "CB04735", "CB04799", "CB04811", "CB04876", "CB04895", "CB04907",
    "CB04932", "CB04936", "CB04976", "CB05080", "CB99999",
))

RISK_FIELDS = ("stage", "sicr_flag", "default_flag", "dpd_days", "past_due_flag", "pd_pit_12m",
               "pd_lifetime", "lgd_pct", "cure_flag", "ecl_coverage_pct")
RISK_AMOUNTS = ("ecl_12m_sar_mn", "ecl_lifetime_sar_mn", "ecl_sar_mn", "write_off_sar_mn",
                "recovery_sar_mn")
WATCH_FIELDS = ("watchlist_flag", "watchlist_reason", "quarters_on_watchlist", "rating_notches_from_origination",
                "rating_notches_moved", "pd_ttc_12m")


def _rank(key: str) -> str:
    return hashlib.sha256(f"{SALT}/{key}".encode()).hexdigest()


def _bad(f: pd.DataFrame) -> pd.Series:
    return (f.dpd_days >= 90) | (f.stage == 3) | (f.default_flag == 1)


RATING_ORDER = ('AAA', 'AA+', 'AA', 'AA-', 'A+', 'A', 'A-', 'BBB+', 'BBB', 'BBB-', 'BB+', 'BB', 'BB-', 'B+', 'B', 'B-',
                'CCC', 'CC', 'C', 'D')


def implied_stage(rating: str, notches_from_origination: float) -> int:
    """The least stage the bank's staging policy allows for a borrower's 2026Q2 rating (the rule the What-If
    engine applies: CC or worse is Stage 3; CCC, or 2+ notches down since origination, is Stage 2). A revert
    or a cure never goes below it, so the book stays consistent with its own staging."""
    r = RATING_ORDER.index(rating) if rating in RATING_ORDER else -1
    if r >= RATING_ORDER.index("CC"):
        return 3
    if r >= RATING_ORDER.index("CCC") or (notches_from_origination or 0) >= 2:
        return 2
    return 1


def _worse(now: pd.DataFrame, before: pd.DataFrame) -> pd.Series:
    """Facility rows (indexed like `now`) that worsened against `before` (same facility index)."""
    b = before.reindex(now.index)
    return ((now.stage > b.stage) | (now.default_flag > b.default_flag) | (now.sicr_flag > b.sicr_flag)
            | ((now.dpd_days >= 90) & (b.dpd_days < 90))).fillna(False)


def story(frames: dict[str, pd.DataFrame]) -> tuple[dict[str, pd.DataFrame], dict]:
    """Apply the overlay to the ORIGINAL frames. Returns (new frames, change record)."""
    fac = frames["corp_facility_quarter"].copy()
    bor = frames["corp_borrower_quarter"].copy()
    now_mask = fac.reporting_quarter == AS_OF
    now = fac[now_mask].set_index("facility_id")
    before = fac[fac.reporting_quarter == PRIOR].set_index("facility_id")
    now_index = pd.Series(fac.index[now_mask], index=now.index)   # facility_id -> row label

    kept = ((now.sector.isin(DETERIORATING_SECTORS) & ~now.region.isin(DETERIORATING_REGIONS))
            | now.sector.isin(DETERIORATING_EVERYWHERE)
            | (now.region.isin(DETERIORATING_REGIONS) & now.sector.isin(DETERIORATING_REGION_SECTORS)))
    open_ = ~kept
    by_borrower = now.groupby("borrower_id")
    # A borrower is in play only if all its facilities are outside the protected story parts.
    eligible_b = by_borrower.apply(lambda g: bool(open_.loc[g.index].all()) and g.name not in PROTECTED_BORROWERS)
    eligible_b = eligible_b[eligible_b]
    sector_of = by_borrower.sector.first()
    # Protected rows never change, so they never count as a worsening the overlay can undo.
    worse = _worse(now, before) & ~now.product_type.isin(PROTECTED_PRODUCTS)
    bad_now_b = _bad(now).groupby(now.borrower_id).any()
    bad_before_b = _bad(before).groupby(before.borrower_id).any()
    s2_before_b = (before.stage == 2).groupby(before.borrower_id).any()
    worse_b = worse.groupby(now.borrower_id).any()

    # A cure never touches a CURE_SKIP_PRODUCTS line, so a borrower bad on one cannot cure.
    skip_bad = now.product_type.isin(CURE_SKIP_PRODUCTS) & _bad(now)
    cure_blocked = set(now.borrower_id[skip_bad])
    bq = bor[bor.reporting_quarter == AS_OF].set_index("borrower_id")
    floor_b = {b: implied_stage(r, n) for b, r, n in zip(bq.index, bq.rating_current, bq.rating_notches_from_origination)}
    # A reverted borrower takes its 2026Q1 rating too, so its policy floor is the 2026Q1 one; a borrower is
    # revertible only if each facility's 2026Q1 stage is at or above that floor.
    bp = bor[bor.reporting_quarter == PRIOR].set_index("borrower_id")
    floor_q1 = {b: implied_stage(r, n) for b, r, n in zip(bp.index, bp.rating_current, bp.rating_notches_from_origination)}
    q1_stage = before.stage
    revertible = {b for b in by_borrower.groups if all(fid in before.index for fid in by_borrower.get_group(b).index)}
    revert: set[str] = set()
    cure: set[str] = set()
    for sector in sorted(sector_of.unique()):
        ids = sorted((b for b in eligible_b.index if sector_of[b] == sector), key=_rank)
        worsened = [b for b in ids if worse_b.get(b, False) and b in revertible]
        if sector in IMPROVING_SECTORS:
            revert.update(worsened)
            bad1 = [b for b in ids if bad_before_b.get(b, False)]
            s21 = [b for b in ids if not bad_before_b.get(b, False) and s2_before_b.get(b, False)]
            cure.update(bad1[: int(round(CURE_SHARE["bad"] * len(bad1)))])
            cure.update(s21[: int(round(CURE_SHARE["stage2"] * len(s21)))])
            continue
        # Stable: revert newly-bad borrowers until the sector's bad count is back
        # to STABLE_BAD_RATIO x its 2026Q1 count; revert the same share of the other worsenings.
        if not ids:
            continue
        target = int(round(STABLE_BAD_RATIO * bad_before_b.reindex(ids).fillna(False).sum()))
        current = int(bad_now_b.reindex(ids).fillna(False).sum())
        new_bad = [b for b in worsened if bad_now_b.get(b, False) and not bad_before_b.get(b, False)]
        # Keep a share of the new defaults and cure as many old ones, so the count holds near its
        # 2026Q1 level with a realistic flow both ways (not a default-entry rate of zero).
        keep = int(round(STABLE_KEEP_NEW * len(new_bad)))
        k = max(0, len(new_bad) - keep)
        revert.update(new_bad[:k])
        old_bad = [b for b in ids if bad_before_b.get(b, False) and bad_now_b.get(b, False)
                   and b not in cure_blocked]
        cure.update(old_bad[: max(0, current - k - target)])
        share = k / len(new_bad) if new_bad else 0.0
        other = [b for b in worsened if b not in set(new_bad)]
        revert.update(other[: int(round(share * len(other)))])
    cure -= revert

    # ---- revert: the 2026Q1 risk state on the 2026Q2 EAD
    rows_reverted = []
    for b in sorted(revert):
        for fid in by_borrower.get_group(b).index:
            if fid not in before.index or not worse.get(fid, False):
                continue
            i, p = now_index[fid], before.loc[fid]
            ead = float(fac.at[i, "ead_sar_mn"])
            for c in RISK_FIELDS:
                fac.at[i, c] = p[c]
            for c in RISK_AMOUNTS:
                fac.at[i, c] = (float(p[c]) / float(p.ead_sar_mn) * ead) if p.ead_sar_mn else 0.0
            fac.at[i, "quarters_in_stage"] = int(p.quarters_in_stage) + 1
            rows_reverted.append(fid)

    # ---- cure: one stage better, default cleared; the sector's median PDs for that stage, the facility's
    # own LGD, and the book's own ECL arithmetic (ECL 12m = PD 12m x LGD x EAD, lifetime = PD lifetime x
    # LGD x EAD; Stage 1 books the 12-month figure, Stage 2 the lifetime one).
    med = {}
    for (sector, stage), g in now.groupby(["sector", "stage"]):
        med[(sector, int(stage))] = {"pd_pit_12m": float(g.pd_pit_12m.median()),
                                     "pd_lifetime": float(g.pd_lifetime.median())}
    rows_cured = []
    for b in sorted(cure):
        for fid in by_borrower.get_group(b).index:
            i = now_index[fid]
            stage = int(fac.at[i, "stage"])
            if stage == 1 or now.at[fid, "product_type"] in PROTECTED_PRODUCTS + CURE_SKIP_PRODUCTS:
                continue
            new = 2 if stage == 3 else 1
            m = med[(sector_of[b], new)]
            ead = float(fac.at[i, "ead_sar_mn"])
            lgd = float(fac.at[i, "lgd_pct"]) / 100.0
            fac.at[i, "stage"] = new
            fac.at[i, "sicr_flag"] = 1 if new == 2 else 0
            fac.at[i, "default_flag"] = 0
            fac.at[i, "dpd_days"] = 0
            fac.at[i, "past_due_flag"] = 0
            fac.at[i, "cure_flag"] = 1
            fac.at[i, "quarters_in_stage"] = 1
            fac.at[i, "pd_pit_12m"] = m["pd_pit_12m"]
            fac.at[i, "pd_lifetime"] = m["pd_lifetime"]
            e12, elt = m["pd_pit_12m"] * lgd * ead, m["pd_lifetime"] * lgd * ead
            fac.at[i, "ecl_12m_sar_mn"] = e12
            fac.at[i, "ecl_lifetime_sar_mn"] = elt
            fac.at[i, "ecl_sar_mn"] = e12 if new == 1 else elt
            fac.at[i, "ecl_coverage_pct"] = 100.0 * (e12 if new == 1 else elt) / ead if ead else 0.0
            fac.at[i, "write_off_sar_mn"] = 0.0
            fac.at[i, "recovery_sar_mn"] = 0.0
            rows_cured.append(fid)

    # ---- tenure: the Cockpit publishes the average quarters in stage by stage at the as-of date (its L08
    # journey: 16.62 / 6.10 / 5.70, ROUND(AVG(quarters_in_stage), 2)) and its suite holds that evidence. A
    # changed facility's natural tenure (2026Q1 + 1 for a revert, 1 for a cure) moves those averages, so the
    # changed rows' tenures are shifted evenly, per stage, until each stage's average equals the original book's
    # to full precision as closely as whole quarters allow. Unchanged rows are not touched.
    changed = set(rows_reverted) | set(rows_cured)
    orig_now = frames["corp_facility_quarter"]
    orig_now = orig_now[orig_now.reporting_quarter == AS_OF]
    target_avg = orig_now.groupby("stage").quarters_in_stage.mean().to_dict()
    q2 = fac[fac.reporting_quarter == AS_OF]
    for stage, g in q2.groupby("stage"):
        ids = g.index[g.facility_id.isin(changed)]
        if not len(ids):
            continue
        need = target_avg[int(stage)] * len(g) - float(g.loc[~g.index.isin(ids), "quarters_in_stage"].sum())
        base = fac.loc[ids, "quarters_in_stage"].astype(int).to_numpy()
        total = int(np.floor(need))
        if round(total / len(g), 2) == total / len(g):
            total -= 1   # never an exact two-decimal average: the evidence holds a rounded figure, not an exact one
        d = total - int(base.sum())
        k, r = divmod(d, len(ids))
        add = np.full(len(ids), k)
        add[:r] += 1
        fac.loc[ids, "quarters_in_stage"] = np.maximum(1, base + add)

    # ---- borrower rows: the 2026Q1 watchlist state carried forward for reverted borrowers;
    # cured borrowers come off the watchlist only if they reach Stage 1 everywhere.
    bnow = bor.reporting_quarter == AS_OF
    bprev = bor[bor.reporting_quarter == PRIOR].set_index("borrower_id")
    pd_ttc_of = bor[bnow].groupby("rating_current").pd_ttc_12m.median().to_dict()
    borrowers_changed = []
    for i in bor.index[bnow]:
        b = bor.at[i, "borrower_id"]
        if b in revert or b in cure:
            # The rating follows the stage: a reverted borrower takes its 2026Q1 rating; then, reverted or
            # cured, the rating is lifted to the best grade its lowest facility stage allows if the policy
            # floor would put it higher (CC or worse is Stage 3; CCC or 2+ notches since origination is
            # Stage 2), so the book stays consistent with its own staging policy.
            p = bprev.loc[b]
            rating = p.rating_current if b in revert else bor.at[i, "rating_current"]
            nfo = float(p.rating_notches_from_origination if b in revert else bor.at[i, "rating_notches_from_origination"])
            low = int(fac.loc[fac.reporting_quarter.eq(AS_OF) & fac.borrower_id.eq(b), "stage"].min())
            if implied_stage(rating, nfo) > low:
                rating = "CCC" if low == 2 else "B-"
                if low == 1:
                    nfo = min(nfo, 1.0)
            if rating != bor.at[i, "rating_current"] or nfo != float(bor.at[i, "rating_notches_from_origination"]):
                prev = p.rating_current
                moved = RATING_ORDER.index(prev) - RATING_ORDER.index(rating)   # positive = upgrade (book sign)
                bor.at[i, "rating_current"] = rating
                bor.at[i, "rating_previous"] = prev
                bor.at[i, "rating_notches_moved"] = moved
                bor.at[i, "rating_migration"] = "UPGRADE" if moved > 0 else "DOWNGRADE" if moved < 0 else "STABLE"
                bor.at[i, "rating_driver"] = p.rating_driver if moved < 0 else "None"
                bor.at[i, "rating_notches_from_origination"] = nfo
                bor.at[i, "rating_outlook"] = p.rating_outlook if rating == prev else "Stable"
                bor.at[i, "pd_ttc_12m"] = (p.pd_ttc_12m if rating == prev else pd_ttc_of.get(rating, p.pd_ttc_12m))
                borrowers_changed.append(b)
        if b in revert:
            p = bprev.loc[b]
            if int(bor.at[i, "watchlist_flag"]) != int(p.watchlist_flag):
                bor.at[i, "watchlist_flag"] = p.watchlist_flag
                bor.at[i, "watchlist_reason"] = p.watchlist_reason
                bor.at[i, "quarters_on_watchlist"] = (int(p.quarters_on_watchlist) + 1
                                                      if int(p.watchlist_flag) else 0)
                borrowers_changed.append(b)

    for c in RISK_FIELDS + ("quarters_in_stage",):
        fac[c] = fac[c].astype(frames["corp_facility_quarter"][c].dtype)
    for c in WATCH_FIELDS:
        bor[c] = bor[c].astype(frames["corp_borrower_quarter"][c].dtype)
    out = dict(frames)
    out["corp_facility_quarter"] = fac
    out["corp_borrower_quarter"] = bor
    record = {"story_version": STORY_VERSION, "as_of": AS_OF, "prior": PRIOR,
              "deteriorating_sectors": list(DETERIORATING_SECTORS),
              "deteriorating_regions": list(DETERIORATING_REGIONS),
              "improving_sectors": list(IMPROVING_SECTORS), "protected_products": list(PROTECTED_PRODUCTS),
              "cure_share": CURE_SHARE, "stable_bad_ratio": STABLE_BAD_RATIO, "stable_keep_new": STABLE_KEEP_NEW,
              "borrowers_reverted": len(revert), "borrowers_cured": len(cure),
              "facility_rows_reverted": len(rows_reverted), "facility_rows_cured": len(rows_cured),
              "borrower_rows_watchlist_changed": len(borrowers_changed),
              "facility_ids_changed": sorted(rows_reverted + rows_cured),
              "borrower_ids_changed": sorted(set(borrowers_changed))}
    return out, record


def load_original() -> dict[str, pd.DataFrame]:
    return {p.stem: pd.read_parquet(p) for p in sorted(REFERENCE.glob("*.parquet"))}


def summary(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    f = frames["corp_facility_quarter"]
    f = f[f.reporting_quarter.isin([PRIOR, AS_OF])].assign(bad=lambda x: _bad(x))
    g = f.groupby(["sector", "reporting_quarter", "borrower_id"]).bad.any().reset_index()
    return g.pivot_table(index="sector", columns="reporting_quarter", values="bad", aggfunc="sum")


def main(argv: list[str]) -> int:
    from backend.cockpit_v4 import domains as dom  # noqa: E402
    from backend.cockpit_v4 import lake  # noqa: E402
    from backend.cockpit_v4 import schema as schema_mod  # noqa: E402
    from ops.rescale_corporate import FACTOR, money_columns  # noqa: E402

    original = load_original()
    frames, record = story(original)
    before, after = summary(original), summary(frames)
    print(pd.concat({"original": before, "story": after}, axis=1).to_string())
    print(json.dumps({k: v for k, v in record.items() if not k.endswith("_changed")}, indent=1))
    if "--dry-run" in argv:
        return 0

    manifest_path = LAKE / lake.MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "v5_rescale" in (manifest.get("notes") or {}), "rescale record missing"
    written = []
    for relation in schema_mod.relation_names(dom.CORPORATE):
        spec = schema_mod.relation(dom.CORPORATE, relation)
        frame = frames[relation].copy()
        for column in money_columns(relation):
            frame[column] = frame[column].astype("float64") * FACTOR
        frame = frame[list(spec.columns)]
        path = LAKE / f"{relation}.parquet"
        frame.to_parquet(path, index=False)
        written.append(path)

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "book_story_record.json").write_text(json.dumps(record, indent=1))
    notes = dict(manifest["notes"])
    notes["v5_ews_story"] = {
        "story_version": STORY_VERSION,
        "applied_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "builder": "ops/ews_story_book.py",
        "record": "evidence/v5/ews/story/book_story_record.json",
        "facility_rows_changed": record["facility_rows_reverted"] + record["facility_rows_cured"],
        "borrower_rows_changed": record["borrower_rows_watchlist_changed"],
        "quarters_changed": [AS_OF],
        "reason": ("Registered data change (PLAN_R5 Session E): the 2026Q2 default wave is kept in "
                   "Construction, Real Estate and Makkah, reverted in the other sectors, with cures in "
                   "Healthcare, Power and Utilities and Telecommunications. Applied to the original "
                   "before the x0.01 rescale; see docs/v5/EWS_STORY.md."),
    }
    manifest["notes"] = notes
    manifest["release_fingerprint"] = lake._digest(written)  # noqa: SLF001
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print("story applied ->", manifest["release_fingerprint"][:16])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
