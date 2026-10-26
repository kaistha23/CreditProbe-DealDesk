"""UAT sweep, PLAN_R5 Session E (part "r5-ews-story"): the Early Warning story (docs/v5/EWS_STORY.md).

Imported by ops/uat_sweep.py, which puts ops/ on the path and passes the Sweep. On both books, for every top level
of the story (corporate: Sector, Region; retail: Product, Region):

  * the API: at least 2 segments IMPROVE (fewer warned, no more high/critical EAD) and at least 2 DETERIORATE
    (more warned, no less high/critical EAD) on the prior period, and every segment the story names moves the way
    the story says (ops/ews_story_calibration.py STORY);
  * the screen: every card's "+N / −N warned" badge carries the direction of its warned movement, green when fewer
    and red when more; its warned and high/critical EAD sparklines carry the direction of their last move; at
    least 2 badges are green and at least 2 red;
  * Construction's sub-sectors: Building Contracting deteriorates, Civil Infrastructure improves.

Console errors, failed requests and banned labels are checked by the Sweep at every step.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ops.ews_story_calibration import STORY  # noqa: E402

LEVELS = {"corporate": [("sector", "Sector"), ("region", "Region")],
          "retail": [("product", "Product"), ("region", "Region")]}
DEFAULT = {"corporate": "sector", "retail": "product"}


def tid(t: str) -> str:
    return f'[data-testid="{t}"]'


def _u():
    main = sys.modules.get("__main__")
    if main is not None and hasattr(main, "KPI_TILES"):
        return main
    import uat_sweep  # noqa: PLC0415
    return uat_sweep


def direction(dw: float | None, de: float | None) -> str:
    dw, de = dw or 0, de or 0
    if dw < 0 and de <= 0:
        return "improving"
    if dw > 0 and de >= 0:
        return "deteriorating"
    return "mixed"


def sign(v: float | None) -> str:
    return "flat" if not v else ("up" if v > 0 else "down")


def last_move(trend: list[dict], key: str) -> str:
    vals = [p.get(key) for p in trend if p.get(key) is not None]
    if len(vals) < 2:
        return "flat"
    d = vals[-1] - vals[-2]
    return "flat" if abs(d) < 0.05 else ("up" if d > 0 else "down")


def check_level(s, page, U, book: str, level: str, cards: list[dict], named: dict[str, int]) -> None:
    by = {c["label"]: direction(c["movement"]["customers_warned"], c["movement"]["exposure_severe"]) for c in cards}
    imp = sorted(k for k, v in by.items() if v == "improving")
    det = sorted(k for k, v in by.items() if v == "deteriorating")
    s.check(f"{level}: at least 2 segments improve", len(imp) >= 2, ">= 2", imp)
    s.check(f"{level}: at least 2 segments deteriorate", len(det) >= 2, ">= 2", det)
    for seg, want in named.items():
        s.check(f"{level}: {seg} {'deteriorates' if want > 0 else 'improves'} (the story)",
                by.get(seg) == ("deteriorating" if want > 0 else "improving"),
                "deteriorating" if want > 0 else "improving", by.get(seg))
    wrong, greens, reds = [], 0, 0
    for c in cards:
        badge = page.locator(tid(f"ews-warned-move-{c['key']}")).first
        d = badge.get_attribute("data-direction")
        want = sign(c["movement"]["customers_warned"])
        cls = badge.get_attribute("class") or ""
        if d != want or (want == "down" and "text-positive" not in cls) or (want == "up" and "text-negative" not in cls):
            wrong.append(f"{c['key']}: badge {d} want {want}")
        greens += want == "down"
        reds += want == "up"
        for k, series in (("warned", "customers_warned"), ("severe", "exposure_severe")):
            sp = page.locator(tid(f"ews-trends-{c['key']}-{k}"))
            if sp.count() == 0:
                continue
            got, exp = sp.first.get_attribute("data-direction"), last_move(c["trend"], series)
            if got != exp:
                wrong.append(f"{c['key']}:{k} spark {got} want {exp}")
    s.check(f"{level}: every badge and sparkline carries its direction (green improving, red worsening)",
            not wrong, "all", wrong[:6])
    s.check(f"{level}: badges show both directions", greens >= 2 and reds >= 2, ">= 2 green and >= 2 red",
            f"{greens} green, {reds} red")


def ews_story_steps(s, page, U_unused, UI: str, wait_url) -> None:  # noqa: ARG001
    U = _u()
    for book in ("corporate", "retail"):
        page.goto(f"{UI}/early-warning?domain={book}", timeout=180_000)
        page.wait_for_selector(tid("ews-level-toggle"), timeout=180_000)
        for key, label in LEVELS[book]:
            s.start(book, "E-story", f"The story by {label}: improving and deteriorating segments, badges, sparklines")
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(600)
            page.click(tid(f"ews-lv-{key}"))
            if key == DEFAULT[book]:
                page.wait_for_selector(tid("ews-level-portfolio"), timeout=120_000)
            else:
                page.wait_for_selector(tid("ews-dim-level-0"), timeout=120_000)
            page.wait_for_selector(tid("ews-kpis"), timeout=60_000)
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(500)
            v = U.api("/levels/view", domain=book, level=key)
            check_level(s, page, U, book, key, v["children"], STORY[book][key])
        if book == "corporate":
            s.start(book, "E-story", "Construction's sub-sectors: Building Contracting worst, Civil Infrastructure improves")
            page.click(tid("ews-lv-sector"))
            page.wait_for_selector(tid("ews-level-portfolio"), timeout=120_000)
            page.wait_for_load_state("networkidle")
            page.click(tid("ews-open-Construction"))
            page.wait_for_selector(tid("ews-card-Building Contracting"), timeout=120_000)
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(500)
            lv = U.api("/level", domain=book, segment="Construction")
            cards = lv["children"]
            by = {c["label"]: direction(c["movement"]["customers_warned"], c["movement"]["exposure_severe"]) for c in cards}
            s.check("Building Contracting deteriorates", by.get("Building Contracting") == "deteriorating",
                    "deteriorating", by.get("Building Contracting"))
            s.check("Civil Infrastructure improves", by.get("Civil Infrastructure") == "improving",
                    "improving", by.get("Civil Infrastructure"))
            worst = max(cards, key=lambda c: c["exposure_severe"])
            s.check("Building Contracting carries the most high/critical EAD", worst["label"] == "Building Contracting",
                    "Building Contracting", worst["label"])
            bc = page.locator(tid("ews-warned-move-Building Contracting")).first
            ci = page.locator(tid("ews-warned-move-Civil Infrastructure")).first
            s.check("badges: Building Contracting red, Civil Infrastructure green",
                    bc.get_attribute("data-direction") == "up" and ci.get_attribute("data-direction") == "down",
                    "up / down", f"{bc.get_attribute('data-direction')} / {ci.get_attribute('data-direction')}")
