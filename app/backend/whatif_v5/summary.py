"""The population summary at the head of every What-If thread (PLAN_R3 S3-5).

Every figure is computed here from the What-If domain at the thread's period
(EAD, ECL, stage, rating or behaviour score band, sector or product) and from
the Early Warning release, read-only, at the same period (each exposure's
Early Warning score, band and reasons). Nothing is typed in or estimated.

    profile(frame, domain, period)   key figures, stage mix, rating mix in the global order,
                                     sector/product split, warning bands and reasons, top 20 owners
    cohort(cohort_id)                an Early Warning cohort, with its reconciliation to the
                                     frozen Early Warning list (count and EAD)
    thread(thread)                   the thread's own population: its cohort, the scope of its
                                     current scenario (segment, borrower...) or the whole book

Amounts are SAR million, as in the books.
"""
from __future__ import annotations

import functools
from typing import Any
from urllib.parse import urlencode

import duckdb
import numpy as np
import pandas as pd

from backend.v5common import ratings
from backend.whatif_v5 import cohorts, paths
from backend.whatif_v5.domain import store
from backend.whatif_v5.models import runner
from backend.whatif_v5.models.engine import scope_mask
from backend.whatif_v5.models.scenario import Scope

EWS_DIR = paths.V5 / "data" / "ews"
EWS_FILES = {"corporate": ("ews-saudi-corporate-20q-v4e2", "ews_corp_exposure.parquet", "facility_id", "reporting_quarter"),
             "retail": ("ews-saudi-retail-20m-v5e1", "ews_retail_exposure.parquet", "account_id", "reporting_month")}
#: Early Warning bands, worst first (backend/ews_domain/ews_rules.bands, plus "none" below the lowest floor).
BAND_ORDER = ("critical", "high", "moderate", "low", "none")
BAND_LABELS = {"critical": "Critical", "high": "High", "moderate": "Moderate", "low": "Low", "none": "No warning"}
#: Owners at or above this band are "warned" in Early Warning's own list (its default cohort).
WARNED = ("critical", "high", "moderate")
TOP_N = 20
TOLERANCE = 1e-6


class SummaryError(LookupError):
    pass


# ------------------------------------------------------------------ Early Warning (read-only)

@functools.lru_cache(maxsize=8)
def _ews_period(domain: str, period: str) -> pd.DataFrame:
    rel, name, key, pcol = EWS_FILES[domain]
    path = EWS_DIR / rel / name
    if not path.exists():
        return pd.DataFrame(columns=["exposure_id", "ews_score", "ews_band", "ews_reasons"])
    con = duckdb.connect()
    try:
        return con.execute(f"""SELECT "{key}" AS exposure_id, ews_score, ews_band, ews_reasons
                               FROM read_parquet(?) WHERE "{pcol}" = ?""", [str(path), period]).df()
    finally:
        con.close()


def _split_reasons(v: Any) -> list[str]:
    """Early Warning joins the rules that fired with '; ' (backend/ews_domain)."""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return []
    return [x.strip() for x in str(v).split(";") if x.strip()]


# ------------------------------------------------------------------ the profile

def grade_order(domain: str, grades: list[str], frame: pd.DataFrame | None = None) -> list[str]:
    """Corporate: the global rating order (AAA ... D). Retail: the book's own band order (grade_rank, A best)."""
    if domain == "corporate":
        return list(ratings.ordered(grades))
    if frame is not None and "grade_rank" in frame and len(frame):
        rank = frame.groupby("grade")["grade_rank"].min().to_dict()
        return sorted(grades, key=lambda g: (rank.get(g, 99), str(g)))
    return sorted(grades)


def _b360(domain: str, owner_id: str, period: str) -> str:
    return "/borrower-360?" + urlencode({"domain": domain, "customer_id": owner_id, "period": period, "tab": "profile"})


def profile(f: pd.DataFrame, domain: str, period: str, top_n: int = TOP_N) -> dict[str, Any]:
    """Every figure of the header, from the exposures in `f` (What-If domain rows at `period`)."""
    lab = runner.LABELS[domain]
    e = _ews_period(domain, period)
    f = f.merge(e, on="exposure_id", how="left")
    f["ews_score"] = pd.to_numeric(f["ews_score"], errors="coerce").fillna(0.0)
    f["ews_band"] = f["ews_band"].fillna("none").astype(str).str.lower()
    ead_total = float(f["ead"].sum())
    ecl_total = float(f["ecl_final"].sum())

    stages = []
    for s in (1, 2, 3):
        m = f["stage"] == s
        ead = float(f.loc[m, "ead"].sum())
        stages.append({"stage": s, "label": f"Stage {s}", "n": int(m.sum()), "owners": int(f.loc[m, "owner_id"].nunique()),
                       "ead": ead, "ecl": float(f.loc[m, "ecl_final"].sum()),
                       "ead_pct": ead / ead_total * 100 if ead_total else 0.0})

    g = f.groupby("grade").agg(n=("exposure_id", "size"), owners=("owner_id", "nunique"), ead=("ead", "sum"),
                               ecl=("ecl_final", "sum"))
    order = grade_order(domain, [str(x) for x in g.index], f)
    grades = [{"grade": k, "n": int(g.loc[k, "n"]), "owners": int(g.loc[k, "owners"]), "ead": float(g.loc[k, "ead"]),
               "ecl": float(g.loc[k, "ecl"]), "ead_pct": float(g.loc[k, "ead"]) / ead_total * 100 if ead_total else 0.0}
              for k in order]

    # One sector or product (a cohort exported from a segment): split by its sub-sectors or sub-products instead.
    by, split_label, split_plural = "segment", lab["segment"], lab["segments"]
    if f["segment"].nunique() == 1 and f["subsegment"].nunique() > 1:
        by, split_label, split_plural = "subsegment", lab["subsegment"], lab["subsegment"] + "s"
    sg = f.groupby(by).agg(n=("exposure_id", "size"), owners=("owner_id", "nunique"), ead=("ead", "sum"),
                                  ecl=("ecl_final", "sum")).sort_values(["ead"], ascending=False, kind="mergesort")
    split = [{"name": str(k), "n": int(r.n), "owners": int(r.owners), "ead": float(r.ead), "ecl": float(r.ecl),
              "ead_pct": float(r.ead) / ead_total * 100 if ead_total else 0.0,
              "coverage_pct": float(r.ecl) / float(r.ead) * 100 if r.ead else 0.0} for k, r in sg.iterrows()]

    # Owner view: an owner's Early Warning score is the highest of its exposures' (as Early Warning lists it),
    # so its band is its worst exposure band.
    band_rank = {b: i for i, b in enumerate(BAND_ORDER)}
    f["band_rank"] = f["ews_band"].map(band_rank).fillna(len(BAND_ORDER) - 1).astype(int)
    first = f.sort_values(["owner_id", "ead"], ascending=[True, False], kind="mergesort")
    o = f.groupby("owner_id").agg(n=("exposure_id", "size"), ead=("ead", "sum"), ecl=("ecl_final", "sum"),
                                  score=("ews_score", "max"), band_rank=("band_rank", "min"), stage=("stage", "max"),
                                  grade_rank=("grade_rank", "max"))
    main = first.groupby("owner_id").first()
    o["segment"] = main["segment"]
    o["name"] = main["owner_name"] if "owner_name" in main else None
    worst_grade = f.sort_values(["owner_id", "grade_rank"], ascending=[True, False], kind="mergesort").groupby("owner_id")["grade"].first()
    o["grade"] = worst_grade
    o["band"] = o["band_rank"].map(lambda i: BAND_ORDER[int(i)])

    bands = []
    for b in BAND_ORDER:
        ob = o[o["band"] == b]
        if len(ob) or b in WARNED:
            bands.append({"band": b, "label": BAND_LABELS[b], "owners": int(len(ob)), "exposures": int(ob["n"].sum()),
                          "ead": float(ob["ead"].sum()), "ecl": float(ob["ecl"].sum())})

    fired: dict[str, dict[str, Any]] = {}
    for oid, eid, ead, raw in zip(f["owner_id"], f["exposure_id"], f["ead"], f["ews_reasons"]):
        for r in _split_reasons(raw):
            x = fired.setdefault(r, {"reason": r, "owners": set(), "exposures": 0, "ead": 0.0})
            x["owners"].add(oid)
            x["exposures"] += 1
            x["ead"] += float(ead)
    reasons = sorted(({"reason": x["reason"], "owners": len(x["owners"]), "exposures": x["exposures"], "ead": x["ead"]}
                      for x in fired.values()), key=lambda r: (-r["owners"], -r["ead"], r["reason"]))[:10]

    top = o.sort_values(["ead", "score"], ascending=[False, False], kind="mergesort").head(top_n)
    top_rows = [{"rank": i + 1, "owner_id": str(oid), "owner_name": r["name"] if isinstance(r["name"], str) and r["name"] else None,
                 "segment": str(r["segment"]), "grade": str(r["grade"]), "stage": int(r["stage"]), "exposures": int(r["n"]),
                 "ead": float(r["ead"]), "ecl": float(r["ecl"]),
                 "coverage_pct": float(r["ecl"]) / float(r["ead"]) * 100 if r["ead"] else 0.0,
                 "ews_score": int(r["score"]), "ews_band": str(r["band"]), "ews_band_label": BAND_LABELS[str(r["band"])],
                 "share_pct": float(r["ead"]) / ead_total * 100 if ead_total else 0.0,
                 "href": _b360(domain, str(oid), period)}
                for i, (oid, r) in enumerate(top.iterrows())]

    s2 = next(x for x in stages if x["stage"] == 2)
    s3 = next(x for x in stages if x["stage"] == 3)
    warned = o[o["band"].isin(WARNED)]
    cards = {
        "owners": int(len(o)), "exposures": int(len(f)), "ead": ead_total, "ecl": ecl_total,
        "coverage_pct": ecl_total / ead_total * 100 if ead_total else 0.0,
        "stage2_ead_pct": s2["ead_pct"], "stage3_ead_pct": s3["ead_pct"], "stage2_n": s2["n"], "stage3_n": s3["n"],
        "ews_avg_score": float(o["score"].mean()) if len(o) else 0.0,
        "ews_warned_owners": int(len(warned)), "ews_warned_ead": float(warned["ead"].sum()),
        "ews_warned_pct": len(warned) / len(o) * 100 if len(o) else 0.0,
    }
    return {"domain": domain, "period": period, "labels": lab, "cards": cards, "stages": stages,
            "grades": {"label": lab["grade"], "order": order, "rows": grades},
            "split": {"label": split_label, "plural": split_plural, "by": by,
                      "within": str(f["segment"].iloc[0]) if by == "subsegment" else "", "rows": split},
            "bands": bands, "reasons": reasons, "top": {"n": top_n, "rows": top_rows}}


# ------------------------------------------------------------------ cohorts, scopes, threads

def cohort(cohort_id: str) -> dict[str, Any]:
    """The cohort Early Warning froze, profiled, and reconciled to Early Warning's own counts and EAD."""
    frozen = cohorts.open_cohort(cohort_id)
    domain, period = frozen["domain_id"], frozen["period"]
    if domain not in store.BOOKS:
        raise SummaryError(f"Cohort {cohort_id} is on '{domain}', which is not a What-If book.")
    ids = set(frozen["exposure_ids"])
    f = store.frame(domain, period)
    f = f[f["exposure_id"].isin(ids)]
    out = profile(f, domain, period)
    c = out["cards"]
    counts = frozen.get("counts") or {}
    ews = {"customers": counts.get("customers"), "exposures": counts.get("exposures"),
           "ead": frozen.get("exposure"), "ecl": frozen.get("ecl")}
    checks = [
        {"label": runner.LABELS[domain]["owners"], "ews": ews["customers"], "whatif": c["owners"]},
        {"label": runner.LABELS[domain]["exposures"], "ews": ews["exposures"], "whatif": c["exposures"]},
        {"label": "EAD", "ews": ews["ead"], "whatif": c["ead"]},
        {"label": "ECL", "ews": ews["ecl"], "whatif": c["ecl"]},
        {"label": "Frozen ids found in the What-If domain", "ews": len(ids), "whatif": c["exposures"]},
    ]
    for x in checks:
        x["matches"] = x["ews"] is not None and abs(float(x["ews"]) - float(x["whatif"])) <= TOLERANCE * max(1.0, abs(float(x["whatif"])))
    out.update({"kind": "cohort", "cohort_id": cohort_id, "title": frozen.get("title", ""),
                "scope_label": f"Early Warning cohort {frozen.get('title') or cohort_id}",
                "ruleset": frozen.get("ruleset", ""), "membership_hash": frozen.get("membership_hash", ""),
                "membership_verified": bool(frozen.get("membership_verified")),
                "reconciliation": {"source": "Early Warning list frozen at export", "checks": checks,
                                   "matches": all(x["matches"] for x in checks)}})
    return out


def scope_of(state: dict[str, Any] | None) -> list[Scope] | None:
    """The population of the thread's current scenario: the union of its steps' scopes; None = the whole book."""
    st_ = state or {}
    steps = (st_.get("pending") or st_.get("scenario") or {}).get("steps") or []
    scopes = [Scope.from_dict(s.get("scope")) for s in steps]
    if not scopes or any(s.is_book() for s in scopes):
        return None
    return scopes


def population(domain: str, period: str, scopes: list[Scope] | None = None) -> dict[str, Any]:
    lab = runner.LABELS[domain]
    f = store.frame(domain, period)
    if scopes:
        m = np.zeros(len(f), dtype=bool)
        for s in scopes:
            m |= scope_mask(f, s)
        f = f[m]
        described = []
        for s in scopes:
            d = s.describe(lab)
            if d not in described:
                described.append(d)
        label, kind = " and ".join(described), "scope"
    else:
        label, kind = f"the {lab['book'].lower()} book", "book"
    out = profile(f, domain, period)
    out.update({"kind": kind, "scope_label": label, "title": label[:1].upper() + label[1:]})
    return out


def thread(t: dict[str, Any]) -> dict[str, Any]:
    domain = t["domain"]
    if t.get("cohort_id"):
        out = cohort(t["cohort_id"])
    else:
        period = store.resolve_period(domain, t.get("period") or "")
        out = population(domain, period, scope_of(t.get("state")))
    out["thread_id"] = t["thread_id"]
    return out


__all__ = ["BAND_ORDER", "SummaryError", "cohort", "grade_order", "population", "profile", "scope_of", "thread"]
