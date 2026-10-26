"""Data-level proof that the corporate rescale changed scale and nothing else.

Compares data/reference/original/<release> (the Round H bytes) with the
rescaled lake book. Writes evidence/v5/foundation/rescale_data_reconciliation.json
and prints a summary. Exit 1 on any failed check.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

V5 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V5))
from backend.cockpit_v4 import domains as dom  # noqa: E402
from backend.cockpit_v4 import schema as schema_mod  # noqa: E402

RELEASE = "v4-saudi-corporate-20q-v4"
ORIG = V5 / "data" / "reference" / "original" / RELEASE
NEW = V5 / "data" / "cockpit_v4_lake" / RELEASE
OUT = V5 / "evidence" / "v5" / "foundation" / "rescale_data_reconciliation.json"
FACTOR = json.loads((NEW / "manifest.json").read_text())["notes"]["v5_rescale"]["factor"]
RATIO_TOL = 1e-12
DIMENSIONS = ("sector", "sub_sector", "region", "product_type", "stage", "relationship_tier")

checks: list[dict] = []


def check(name: str, ok: bool, **detail) -> None:
    checks.append({"check": name, "pass": bool(ok), **detail})


def money(relation: str) -> list[str]:
    return [f.name for f in schema_mod.relation(dom.CORPORATE, relation).fields if f.unit == "rcy"]


#: The registered Early Warning story (ops/ews_story_book.py, PLAN_R5 Session E) is applied to the
#: original BEFORE the rescale, so the reconciliation source is story(original) when the lake
#: records it. Every check below then proves the rescale changed scale and nothing else; the
#: story's own changes are listed in evidence/v5/ews/story/book_story_record.json.
STORY = "v5_ews_story" in json.loads((NEW / "manifest.json").read_text())["notes"]


def source_frames() -> dict[str, pd.DataFrame]:
    frames = {r: pd.read_parquet(ORIG / f"{r}.parquet") for r in schema_mod.relation_names(dom.CORPORATE)}
    if STORY:
        from ops.ews_story_book import story
        frames, _ = story(frames)
    return frames


def relation_checks() -> dict[str, pd.DataFrame]:
    frames = {}
    source = source_frames()
    for relation in schema_mod.relation_names(dom.CORPORATE):
        a = source[relation]
        b = pd.read_parquet(NEW / f"{relation}.parquet")
        frames[relation] = (a, b)
        cols = money(relation)
        other = [c for c in a.columns if c not in cols]
        check(f"{relation}: same rows, columns and order",
              len(a) == len(b) and list(a.columns) == list(b.columns),
              rows=len(a), columns=len(a.columns))
        check(f"{relation}: same dtypes", (a.dtypes == b.dtypes).all())
        check(f"{relation}: {len(other)} non-money columns byte-identical (IDs, periods, "
              f"ratings, PDs, LGD, %, multiples, flags, stages)",
              a[other].equals(b[other]), columns=other)
        rel = []
        for c in cols:
            x, y = a[c].to_numpy("float64"), b[c].to_numpy("float64")
            same_nan = np.array_equal(np.isnan(x), np.isnan(y))
            mask = ~np.isnan(x) & (x != 0)
            dev = float(np.max(np.abs(y[mask] / x[mask] / FACTOR - 1))) if mask.any() else 0.0
            zeros = bool(np.array_equal(x == 0, y == 0))
            rel.append(dev)
            check(f"{relation}.{c}: every value = original x {FACTOR}",
                  same_nan and zeros and dev < RATIO_TOL, max_relative_deviation=dev)
    return frames


def aggregate_checks(frames) -> dict:
    a, b = frames["corp_facility_quarter"]
    report = {}
    for frame, tag in ((a, "before"), (b, "after")):
        q = frame.groupby("reporting_quarter").agg(ead=("ead_sar_mn", "sum"), ecl=("ecl_sar_mn", "sum"),
                                                   limit=("limit_sar_mn", "sum"),
                                                   facilities=("facility_id", "nunique"),
                                                   borrowers=("borrower_id", "nunique"))
        report[tag] = q
    qa, qb = report["before"], report["after"]
    check("per-quarter EAD, ECL and limit totals scale by exactly the factor (20 quarters)",
          float(np.max(np.abs((qb[["ead", "ecl", "limit"]] / qa[["ead", "ecl", "limit"]]).to_numpy() / FACTOR - 1))) < RATIO_TOL)
    check("per-quarter facility and borrower counts identical",
          qa[["facilities", "borrowers"]].equals(qb[["facilities", "borrowers"]]))

    ratio_dev = 0.0
    rank_breaks = []
    for dim in DIMENSIONS:
        ga = a.groupby(["reporting_quarter", dim]).agg(ead=("ead_sar_mn", "sum"), ecl=("ecl_sar_mn", "sum"),
                                                       drawn=("drawn_sar_mn", "sum"), limit=("limit_sar_mn", "sum"))
        gb = b.groupby(["reporting_quarter", dim]).agg(ead=("ead_sar_mn", "sum"), ecl=("ecl_sar_mn", "sum"),
                                                       drawn=("drawn_sar_mn", "sum"), limit=("limit_sar_mn", "sum"))
        for name, fa, fb in (
            ("coverage", ga.ecl / ga.ead, gb.ecl / gb.ead),
            ("utilisation", ga.drawn / ga.limit, gb.drawn / gb.limit),
            ("share_of_ead", ga.ead / ga.groupby(level=0).ead.transform("sum"),
             gb.ead / gb.groupby(level=0).ead.transform("sum")),
        ):
            m = fa.abs() > 0
            ratio_dev = max(ratio_dev, float(((fb[m] - fa[m]).abs() / fa[m].abs()).max()))
        for quarter in ga.index.get_level_values(0).unique():
            for measure in ("ead", "ecl"):
                ra = ga.loc[quarter][measure].sort_values(ascending=False, kind="stable").index.tolist()
                rb = gb.loc[quarter][measure].sort_values(ascending=False, kind="stable").index.tolist()
                if ra != rb:
                    rank_breaks.append((dim, quarter, measure))
    check(f"coverage, utilisation and EAD share by quarter x {', '.join(DIMENSIONS)} unchanged",
          ratio_dev < 1e-12, max_relative_deviation=ratio_dev)
    check("rankings by EAD and by ECL within every quarter and dimension unchanged",
          not rank_breaks, breaks=rank_breaks[:20])

    # Borrower EAD is a sum of facility amounts stored to the cent. Rank at
    # that precision, ties broken by id: in the ORIGINAL book eight pairs of
    # borrowers have identical EAD and their raw-float order is last-bit
    # noise (2641.6000000000004 vs 2641.6), which any multiplication reshuffles.
    def ranking(frame, scale):
        s = frame[frame.reporting_quarter == "2026Q2"].groupby("borrower_id").ead_sar_mn.sum()
        cents = (s / scale).round(2)
        order = cents.reset_index().sort_values(["ead_sar_mn", "borrower_id"], ascending=[False, True])
        return order.borrower_id.tolist(), cents
    rank_a, cents_a = ranking(a, 1.0)
    rank_b, cents_b = ranking(b, FACTOR)
    ties = cents_a[cents_a.duplicated(keep=False)].sort_values()
    check("borrower ranking by EAD at 2026Q2 identical at stored (cent) precision, all 5,412",
          rank_a == rank_b and cents_a.equals(cents_b),
          exact_tie_borrowers=ties.index.tolist())

    ca, cb = frames["corp_collateral_quarter"]
    ltv_a = ca.groupby("reporting_quarter").allocated_value_sar_mn.sum() / ca.groupby("reporting_quarter").market_value_sar_mn.sum()
    ltv_b = cb.groupby("reporting_quarter").allocated_value_sar_mn.sum() / cb.groupby("reporting_quarter").market_value_sar_mn.sum()
    check("collateral allocated/market value ratio by quarter unchanged",
          float(((ltv_b - ltv_a).abs() / ltv_a).max()) < 1e-12)

    def profile(frame):
        f = frame[frame.reporting_quarter == "2026Q2"]
        borrower = f.groupby("borrower_id").ead_sar_mn.sum()
        return {"total_ead_sar_mn": round(float(f.ead_sar_mn.sum()), 1),
                "total_ecl_sar_mn": round(float(f.ecl_sar_mn.sum()), 1),
                "total_limit_sar_mn": round(float(f.limit_sar_mn.sum()), 1),
                "coverage_pct": round(float(f.ecl_sar_mn.sum() / f.ead_sar_mn.sum() * 100), 4),
                "median_facility_ead_sar_mn": round(float(f.ead_sar_mn.median()), 3),
                "median_borrower_ead_sar_mn": round(float(borrower.median()), 3),
                "largest_borrower_ead_sar_mn": round(float(borrower.max()), 1),
                "stage_counts": {int(k): int(v) for k, v in f.stage.value_counts().sort_index().items()},
                "facilities": int(f.facility_id.nunique()), "borrowers": int(f.borrower_id.nunique())}
    return {"2026Q2_before": profile(a), "2026Q2_after": profile(b), "ews_story_applied": STORY}


def main() -> int:
    frames = relation_checks()
    profiles = aggregate_checks(frames)
    failed = [c for c in checks if not c["pass"]]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"release": RELEASE, "factor": FACTOR, "checks": checks,
                               "profiles": profiles, "failed": len(failed)}, indent=1, default=str))
    for c in checks:
        print(("PASS " if c["pass"] else "FAIL ") + c["check"])
    print(json.dumps(profiles, indent=1))
    print(f"{len(checks) - len(failed)}/{len(checks)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
