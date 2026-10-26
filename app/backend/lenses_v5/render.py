"""Render a lens spec: the KPI row, every tile (figure, table, trace) and the commentary.

Every tile runs its own engine query; a tile that cannot run is shown with its reason, never with a made-up
figure. `untraced` counts figures without a trace (the L3 test asserts it is zero).
"""
from __future__ import annotations

import threading
import time
from typing import Any

from backend.lenses_v5 import fmt
from backend.lenses_v5.catalogue import DIMS
from backend.lenses_v5.engine import ENGINE, LensError
from backend.lenses_v5.interpret import interpret
from backend.lenses_v5.tiles import Ctx, kpis, run_tile

_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_LOCK = threading.Lock()


def render(spec: dict[str, Any], period: str = "", cache_key: str = "") -> dict[str, Any]:
    key = f"{cache_key}|{period}" if cache_key else ""
    if key:
        with _LOCK:
            hit = _CACHE.get(key)
        if hit:
            return hit[1]
    t0 = time.time()
    ctx = Ctx(spec, period)
    k = kpis(ctx, strip_keys(spec.get("kpis") or []))
    interp = interpret(spec, ctx, k)
    tiles = []
    for t in spec.get("tiles") or []:
        try:
            tiles.append(run_tile(t, ctx))
        except LensError as e:
            tiles.append({"id": t.get("id"), "type": t.get("type"), "title": t.get("title") or t.get("type", "").replace("_", " "),
                          "error": str(e), "figure": None, "table": None, "trace": None, "size": "half"})
    out = {"book": ctx.book, "period": ctx.period, "periods": ENGINE.periods(ctx.book), "window": ctx.window,
           "scope": [{"dim": f["dim"], "label": DIMS[f["dim"]].label, "values": f["values"]} for f in ctx.filters],
           "scope_label": spec.get("scope_label") or "", "compare": spec.get("compare"), "kpis": k, "tiles": tiles,
           "interpretation": interp, "commentary": {"markdown": interp["markdown"], "source": interp["source"]},
           "charts": sum(1 for t in tiles if t.get("figure")), "untraced": untraced(k, tiles), "ms": int((time.time() - t0) * 1000)}
    if key:
        with _LOCK:
            if len(_CACHE) > 200:
                _CACHE.clear()
            _CACHE[key] = (time.time(), out)
    return out


#: R13 L (J8): the KPI strip holds 6-8 small tiles. Lenses saved with the R12 row of ten drop, in this order, the
#: figures another tile already says (NPL ratio = Stage 3 share; warned obligors next to high or critical).
STRIP_MAX = 8
STRIP_DROP = (("npl_ratio", "stage3_share"), ("warned", "high_critical"), ("dscr", ""), ("dpd30_share", ""))


def strip_keys(keys: list[str]) -> list[str]:
    out = list(dict.fromkeys(keys))
    for key, if_has in STRIP_DROP:
        if len(out) <= STRIP_MAX:
            break
        if key in out and (not if_has or if_has in out):
            out.remove(key)
    return out


def untraced(k: list[dict[str, Any]], tiles: list[dict[str, Any]]) -> int:
    n = sum(1 for x in k if x.get("value") is not None and not (x.get("trace") or {}).get("sql"))
    n += sum(1 for t in tiles if not t.get("error") and not (t.get("trace") or {}).get("sql"))
    return n
