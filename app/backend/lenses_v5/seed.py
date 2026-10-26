"""Seeded lenses (PLAN_R5 L2): the seven templates and two saved lenses, built by the same planner as any request.

Templates are re-seeded when SEED_VERSION changes (their specs follow the planner); saved lenses are kept.
"""
from __future__ import annotations

import time
from typing import Any

from backend.lenses_v5 import fmt, planner
from backend.lenses_v5.engine import ENGINE

SEED_VERSION = "lenses-seed-2"   # R13 L: "credit cards" keeps its product filter

#: key, name, book, request, description, tags
TEMPLATES: list[tuple[str, str, str, str, str, list[str]]] = [
    ("cro-portfolio", "CRO portfolio", "corporate", "CRO portfolio dashboard",
     "The whole corporate book for the CRO: loss, staging, Early Warning, migration, concentration and the largest names.", ["cro", "portfolio"]),
    ("construction-sector", "Construction sector", "corporate", "Construction sector dashboard by sub-sector",
     "Construction by sub-sector: ECL, staging, Early Warning reasons, DSCR and the names that drive it.", ["sector", "construction"]),
    ("real-estate-concentration", "Real Estate concentration", "corporate", "Real Estate concentration",
     "Real Estate concentration: top-10 share and HHI, LTV, staging and the largest exposures.", ["sector", "concentration"]),
    ("makkah-region", "Makkah region", "corporate", "Makkah region by branch",
     "Makkah: branches, sectors, Early Warning and migration for the region's corporate book.", ["region", "makkah"]),
    ("retail-cards", "Retail cards", "retail", "Retail credit cards by region",
     "Credit cards: delinquency, roll rates, vintages, behaviour score bands and Early Warning.", ["retail", "cards"]),
    ("stage2-watch", "Stage 2 watch", "corporate", "Stage 2 migration by RM",
     "Stage 2 by relationship manager: where the SICR book sits and how it moves.", ["stage 2", "watch"]),
    ("ews-critical", "Early Warning critical names", "corporate", "Early Warning critical names",
     "The high and critical Early Warning names, their reasons and their exposure.", ["early warning", "critical"]),
]
TEMPLATE_KEYS = [t[0] for t in TEMPLATES]

#: The Featured row on the Lenses home (PLAN_R6 L1): three templates and one featured lens of its own, opened as a copy
#: like a template. Kind "featured" keeps it out of the seven templates.
FEATURED_EXTRA: list[tuple[str, str, str, str, str, list[str]]] = [
    ("concentration-risk", "Concentration risk", "corporate", "Concentration risk by sector and rating",
     "Where the corporate book is concentrated: top-10 share and HHI, sectors, ratings and the largest names.", ["concentration", "featured"]),
]
FEATURED_KEYS = ["cro-portfolio", "stage2-watch", "ews-critical", "concentration-risk", "retail-cards"]

#: Saved lenses that show "mine" and "shared with me" from the first sign-in.
SAVED: list[tuple[str, str, str, str, str, list[str], list[tuple[str, str]]]] = [
    ("anne", "admin", "Construction watch", "Construction sector dashboard by RM", "Construction by relationship manager for the weekly risk call.",
     ["construction", "weekly"], []),
    ("faisal.alqahtani", "risk", "Q2 portfolio review", "CRO portfolio dashboard", "Corporate portfolio for the Q2 risk committee.",
     ["committee"], [("user", "anne"), ("team", "risk")]),
    # PLAN_R6 L1: a fuller home for Anne (four or more of her own, three or more shared with her, in both books)
    ("anne", "admin", "Real Estate concentration", "Real Estate concentration", "Real Estate: top-10 share, HHI, LTV and the largest exposures.",
     ["real estate", "concentration"], []),
    ("anne", "admin", "Makkah region", "Makkah region by branch", "Makkah branches, sectors and Early Warning for the regional review.",
     ["region", "makkah"], []),
    ("anne", "admin", "Stage 2 by RM", "Stage 2 migration by RM", "Stage 2 by relationship manager for the monthly SICR review.",
     ["stage 2"], []),
    ("anne", "admin", "Retail cards", "Retail credit cards by region", "Credit cards: delinquency, roll rates and vintages by region.",
     ["retail", "cards"], []),
    ("anne", "admin", "Personal finance by region", "Retail personal finance by region", "Personal finance by region for the retail risk call.",
     ["retail", "personal finance"], []),
    ("noura.alharbi", "risk", "Early Warning weekly", "Early Warning critical names", "The high and critical names for the Sunday watchlist call.",
     ["early warning", "weekly"], [("user", "anne")]),
    ("khalid.alotaibi", "corporate", "Concentration review", "Concentration risk by sector and rating", "Single-name and sector concentration for ALCO.",
     ["concentration", "alco"], [("user", "anne")]),
    ("sara.aldosari", "corporate", "Cards delinquency review", "Retail credit cards by region", "Cards roll rates and vintages for the retail committee.",
     ["retail", "cards"], [("user", "anne")]),
    ("sara.aldosari", "corporate", "Retail Makkah", "Makkah retail cards", "Makkah retail cards for the regional retail review.",
     ["retail", "makkah"], [("user", "anne")]),
]


def thumb(spec: dict[str, Any]) -> dict[str, Any]:
    """A card thumbnail: three headline figures and the ECL trend, from the engine."""
    b = spec["book"]
    try:
        rows, _ = ENGINE.series(b, spec.get("filters") or [], ENGINE.window(b, spec.get("period") or ENGINE.as_of(b)), ["ead", "ecl", "coverage", "warned"])
    except Exception:  # noqa: BLE001 - a thumbnail never blocks a card
        return {"figures": [], "spark": []}
    now = rows[-1] if rows else {}
    return {"figures": [{"label": "EAD", "display": fmt.amount(now.get("ead"))}, {"label": "ECL", "display": fmt.amount(now.get("ecl"))},
                        {"label": "Coverage", "display": fmt.pct(now.get("coverage"))}, {"label": "Warned", "display": fmt.count(now.get("warned"))}],
            "spark": [r.get("ecl") for r in rows], "period": now.get("period")}


def ensure(store: Any) -> None:
    now = time.time()
    for i, (key, name, book, request, desc, tags) in enumerate(TEMPLATES):
        cur = store.template(key)
        if cur is not None and (cur["description"] == desc and (cur["tags"] or [])[-1:] == [SEED_VERSION]):
            continue
        if cur is not None:
            store.archive(cur["lens_id"])
        spec = planner.build_spec(request, book, title=name)
        lens = store.create(owner="", team="", spec=spec, kind="template", name=name, description=desc, tags=[*tags, SEED_VERSION],
                            saved=True, template_key=key, change="Template", at=now - i)
        store.update(lens["lens_id"], thumb=thumb(spec))
    for i, (key, name, book, request, desc, tags) in enumerate(FEATURED_EXTRA):
        cur = store.keyed("featured", key)
        if cur is not None and cur["description"] == desc and (cur["tags"] or [])[-1:] == [SEED_VERSION]:
            continue
        if cur is not None:
            store.archive(cur["lens_id"])
        spec = planner.build_spec(request, book, title=name)
        lens = store.create(owner="", team="", spec=spec, kind="featured", name=name, description=desc, tags=[*tags, SEED_VERSION],
                            saved=True, template_key=key, change="Featured", at=now - 10 - i)
        store.update(lens["lens_id"], thumb=thumb(spec))
    have = {(x["owner"], x["name"]): x for x in store.lenses("lens")}
    for owner, team, name, request, desc, tags, shares in SAVED:
        if (owner, name) in have:
            _repair_scope(store, have[(owner, name)], request)
            continue
        spec = planner.build_spec(request, "", title=name)
        lens = store.create(owner=owner, team=team, spec=spec, name=name, description=desc, tags=tags, saved=True, change="Saved")
        store.update(lens["lens_id"], thumb=thumb(spec))
        for kind, target in shares:
            store.share(lens["lens_id"], kind, target, owner)


def _repair_scope(store: Any, lens: dict[str, Any], request: str) -> None:
    """R13 L: a seeded lens planned before the whole-word alias fix lost its scope ("Retail credit cards" showed the whole
    retail book). Restore the planner's filters on a seeded lens still at its seeded request with no filters; a lens the
    user has re-scoped is left alone."""
    try:
        spec = store.spec(lens["lens_id"])
    except KeyError:
        return
    if spec.get("request") != request or spec.get("filters"):
        return
    fresh = planner.build_spec(request, spec.get("book") or "")
    if not fresh.get("filters") or fresh["book"] != spec.get("book"):
        return
    spec = {**spec, "filters": fresh["filters"], "scope_label": fresh["scope_label"]}
    store.commit(lens["lens_id"], spec, "Scope restored: " + fresh["scope_label"], "system")
    store.update(lens["lens_id"], thumb=thumb(spec))
