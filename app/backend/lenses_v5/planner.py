"""From a request to a lens spec, and from an edit command to a changed spec (PLAN_R5 L1.2-L1.3).

The planner reads the request against the book's own values (sectors, sub-sectors, regions, branches, RMs,
products, sub-products, stages, bands), so "Makkah retail cards" scopes to region Makkah, product Credit
Card. The tile set is a rich default for the book with the request's focus first ("by RM" puts the
breakdown by relationship manager at the top). The model path proposes the same spec shape through the
`build_lens` / `edit_lens` tools; both paths go through `normalise`, so a tile the engine cannot run never
reaches a lens.
"""
from __future__ import annotations

import copy
import re
import uuid
from typing import Any

from backend.lenses_v5.catalogue import DIMS, DISTRIBUTIONS, METRICS
from backend.lenses_v5.engine import ENGINE, LensError
from backend.lenses_v5.tiles import CHARTS, TYPES

RETAIL_WORDS = ("retail", "card", "cards", "credit card", "personal finance", "mortgage", "auto finance", "auto loan", "bnpl",
                "buy now pay later", "customer", "customers", "consumer", "vintage", "roll rate", "roll rates")
CORP_WORDS = ("corporate", "borrower", "borrowers", "sector", "construction", "real estate", "rm ", "relationship manager", "dscr",
              "leverage", "covenant", "facility", "facilities")
ALIASES = {"cards": "Credit Card", "card": "Credit Card", "credit cards": "Credit Card", "bnpl": "Buy Now Pay Later",
           "auto": "Auto Finance", "auto loans": "Auto Finance", "mortgages": "Mortgage", "home finance": "Mortgage",
           "personal loans": "Personal Finance", "personal finance": "Personal Finance", "eastern": "Eastern Province",
           "makkah": "Makkah", "mecca": "Makkah", "riyadh": "Riyadh", "jeddah": "Makkah", "realestate": "Real Estate"}
BY_WORDS = {"rm": "rm_name", "rms": "rm_name", "relationship manager": "rm_name", "relationship managers": "rm_name", "region": "region",
            "regions": "region", "branch": "branch_name", "branches": "branch_name", "sector": "sector", "sectors": "sector",
            "sub-sector": "sub_sector", "sub sector": "sub_sector", "subsector": "sub_sector", "sub-sectors": "sub_sector", "rating": "rating_current",
            "ratings": "rating_current", "grade": "rating_current", "stage": "stage", "product": "product", "products": "product",
            "sub-product": "sub_product", "sub product": "sub_product", "segment": "customer_segment", "business unit": "business_unit",
            "band": "ews_band", "early warning band": "ews_band", "vintage": "vintage_year", "channel": "origination_channel",
            "tier": "relationship_tier", "facility type": "product_type", "employment": "employment_type", "bucket": "delinquency_bucket"}
SCOPE_DIMS = {"corporate": ("sector", "sub_sector", "region", "branch_name", "rm_name", "business_unit", "relationship_tier", "product_type"),
              "retail": ("product", "sub_product", "region", "branch_name", "customer_segment", "employment_type")}
#: R13 L (J8): a compact strip of eight (NPL ratio repeated Stage 3 share; warned sits next to high or critical in the tiles)
KPI_KEYS = {"corporate": ["ead", "ecl", "coverage", "stage2_share", "stage3_share", "cost_of_risk", "high_critical", "dscr"],
            "retail": ["ead", "ecl", "coverage", "stage2_share", "stage3_share", "dpd30_share", "cost_of_risk", "high_critical"]}
METRIC_WORDS = {"dscr": "dscr", "debt service": "dscr", "leverage": "leverage", "ltv": "ltv", "loan to value": "ltv", "ecl": "ecl",
                "ead": "ead", "exposure": "ead", "coverage": "coverage", "stage 2": "stage2_share", "stage 3": "stage3_share", "npl": "npl_ratio",
                "cost of risk": "cost_of_risk", "warned": "warned", "warning": "warned", "high or critical": "high_critical", "critical": "high_critical",
                "pd": "pd", "probability of default": "pd", "lgd": "lgd", "utilisation": "utilisation", "utilization": "utilisation", "limit": "limit",
                "write-off": "write_offs", "write off": "write_offs", "30+": "dpd30_share", "dpd": "dpd30_share", "90+": "dpd90_share",
                "behaviour score": "behaviour_score", "watchlist": "watchlist", "covenant": "covenant_breaches", "downgrade": "downgraded",
                "raroc": "dd_raroc", "deal desk": "dd_pipeline", "scorecard": "sc_score", "bad rate": "sc_bad_rate", "what-if": "ecl_pd20",
                "pd +20": "ecl_pd20", "obligors": "obligors", "borrowers": "obligors", "customers": "obligors"}
DIST_WORDS = {"dscr": "dscr_x", "leverage": "leverage_x", "ltv": "collateral_ltv_pct", "loan to value": "collateral_ltv_pct", "utilisation": "utilisation_pct",
              "utilization": "utilisation_pct", "pd": "pd_pit_12m", "dpd": "dpd_days", "days past due": "dpd_days", "behaviour score": "behaviour_score",
              "lgd": "lgd_pct"}


def _new_id(prefix: str = "t") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:6]}"


def _has(text: str, word: str) -> bool:
    return re.search(rf"(?<![a-z]){re.escape(word)}(?![a-z])", text) is not None


def detect_book(text: str, default: str = "corporate") -> str:
    t = text.lower()
    r = sum(_has(t, w) for w in RETAIL_WORDS)
    c = sum(_has(t, w) for w in CORP_WORDS)
    if r > c:
        return "retail"
    if c > r:
        return "corporate"
    # a value only one book has (a sector, a product)
    for book in ("retail", "corporate"):
        other = "corporate" if book == "retail" else "retail"
        for d in ("product", "sub_product") if book == "retail" else ("sector", "sub_sector", "rm_name"):
            if any(_has(t, v.lower()) for v in ENGINE.values(book, d)):
                return book
        del other
    return default


def detect_filters(text: str, book: str) -> list[dict[str, Any]]:
    t = " " + text.lower() + " "
    for a, v in ALIASES.items():
        # whole-word test: "credit cards" contains "credit card" as text but not as a word, and lost its filter (R13 L)
        if _has(t, a) and not _has(t, v.lower()):
            t += " " + v.lower() + " "
    out: dict[str, list[str]] = {}
    for dim in SCOPE_DIMS[book]:
        for v in ENGINE.values(book, dim):
            if len(v) > 2 and _has(t, v.lower()):
                out.setdefault(dim, []).append(v)
    # a sub-sector that only matched because it repeats its sector's name is dropped ("Real Estate" vs "Real Estate Development")
    if "sector" in out and "sub_sector" in out:
        out["sub_sector"] = [s for s in out["sub_sector"] if not any(s.lower() == x.lower() for x in out["sector"])]
        if not out["sub_sector"]:
            out.pop("sub_sector")
    m = re.search(r"stage\s*([123])\b", t)
    if m and not re.search(r"stage\s*[123]\s*(migration|watch|share|mix)", t):
        out["stage"] = [f"Stage {m.group(1)}"]
    return [{"dim": k, "values": v} for k, v in out.items()]


def detect_by(text: str, book: str) -> str:
    t = text.lower()
    m = re.search(r"\bby\s+([a-z\- ]{2,30}?)(?:\s+instead|\s+and|\s+for|\s+in|[,.]|$)", t)
    if m:
        w = m.group(1).strip()
        for k in sorted(BY_WORDS, key=len, reverse=True):
            if w.startswith(k) and book in DIMS[BY_WORDS[k]].books:
                return BY_WORDS[k]
    return ""


def scope_label(book: str, filters: list[dict[str, Any]]) -> str:
    parts = [", ".join(f["values"]) for f in filters]
    return " · ".join(parts) or ("Corporate book" if book == "corporate" else "Retail book")


def default_tiles(book: str, filters: list[dict[str, Any]], focus_by: str = "", text: str = "") -> list[dict[str, Any]]:
    t = text.lower()
    dims = {f["dim"] for f in filters}
    if book == "corporate":
        seg = "sub_sector" if "sector" in dims else "sector"
        geo = "branch_name" if "region" in dims else "region"
    else:
        seg = "sub_product" if "product" in dims else "product"
        geo = "branch_name" if "region" in dims else "region"
    tiles: list[dict[str, Any]] = []

    def add(**k: Any) -> None:
        tiles.append({"id": _new_id(), **k})
    if "concentration" in t:
        add(type="concentration")
        add(type="top_names", metric="ead", top=20)
    if any(w in t for w in ("critical", "early warning", "ews", "warned")):
        add(type="top_names", metric="high_critical_ead", top=20, title="Top 20 high or critical names")
        add(type="reasons")
    if "migration" in t and book == "corporate":
        add(type="migration")
    if focus_by:
        add(type="breakdown", metric="stage2_ead" if "stage 2" in t else "ecl", dim=focus_by, chart="hbar")
        add(type="breakdown", metric="warned" if "stage 2" not in t else "stage2_share", dim=focus_by, chart="hbar")
    add(type="trend", metrics=["ecl", "coverage"], chart="line")
    add(type="trend", metrics=["stage2_share", "stage3_share"], chart="line")
    add(type="mix_trend", metric="ead", dim="stage", chart="stacked100")
    if book == "corporate":
        add(type="breakdown", metric="ead", dim="rating_current", chart="bar", title="EAD by rating (global order)")
    else:
        add(type="breakdown", metric="ead", dim="score_band", chart="bar", title="EAD by behaviour score band")
    add(type="breakdown", metric="ecl", dim=seg, chart="hbar")
    add(type="breakdown", metric="ead", dim=geo, chart="hbar")
    add(type="mix_trend", metric="ead", dim="ews_band", chart="stacked100", title="Early Warning bands (share of EAD)")
    add(type="reasons")
    if book == "corporate":
        add(type="migration")
        add(type="distribution", column="dscr_x")
        add(type="concentration")
        add(type="breakdown", metric="utilisation", dim="product_type", chart="bar", title="Limit utilisation by facility type")
    else:
        add(type="roll_rate")
        add(type="vintage")
        add(type="distribution", column="utilisation_pct")
    add(type="top_names", metric="ead", top=20)
    seen, out = set(), []
    for x in tiles:
        sig = (x["type"], x.get("metric"), x.get("dim"), x.get("column"), tuple(x.get("metrics") or []))
        if x["type"] in ("reasons", "migration", "concentration", "roll_rate", "vintage"):
            sig = (x["type"],)
        if x["type"] == "top_names":
            sig = ("top_names",)
        if sig not in seen:
            seen.add(sig)
            out.append(x)
    return out


def build_spec(text: str, book: str = "", title: str = "") -> dict[str, Any]:
    """A complete lens spec from a request."""
    # the words decide when they name a book or its values ("Makkah retail cards" on the Corporate toggle is retail);
    # otherwise the toggle does
    b = detect_book(text, default=book if book in ("corporate", "retail") else "corporate")
    filters = detect_filters(text, b)
    by = detect_by(text, b)
    label = scope_label(b, filters)
    spec = {"book": b, "filters": filters, "period": ENGINE.as_of(b), "scope_label": label,
            "title": title or _title(text, b, label, by), "kpis": KPI_KEYS[b][:], "tiles": default_tiles(b, filters, by, text),
            "compare": None, "custom_metrics": [], "request": text}
    return normalise(spec)


def _title(text: str, book: str, label: str, by: str) -> str:
    t = text.strip().rstrip(".")
    if 3 <= len(t) <= 60 and not t.lower().startswith(("show", "build", "make", "create", "give", "i want", "can you")):
        return t[0].upper() + t[1:]
    head = label if label not in ("Corporate book", "Retail book") else ("Corporate portfolio" if book == "corporate" else "Retail portfolio")
    return f"{head} dashboard" + (f" by {DIMS[by].label.lower()}" if by else "")


def normalise(spec: dict[str, Any]) -> dict[str, Any]:
    """Drop or repair anything the engine cannot run: unknown metrics, dimensions of the other book, bad chart types."""
    s = copy.deepcopy(spec)
    b = s["book"]
    custom = {c["key"] for c in s.get("custom_metrics") or []}
    s["kpis"] = [k for k in s.get("kpis") or [] if k in custom or (k in METRICS and b in METRICS[k].books)]
    good = []
    for t in s.get("tiles") or []:
        if t.get("type") not in TYPES:
            continue
        if t.get("dim") and (t["dim"] not in DIMS or b not in DIMS[t["dim"]].books):
            continue
        ms = t.get("metrics") or ([t["metric"]] if t.get("metric") else [])
        if any(m not in custom and (m not in METRICS or b not in METRICS[m].books) for m in ms):
            continue
        if t["type"] == "distribution" and (t.get("column") not in DISTRIBUTIONS or b not in DISTRIBUTIONS[t["column"]]["books"]):
            continue
        if t["type"] in ("roll_rate", "vintage") and b != "retail":
            continue
        if t["type"] == "migration" and False:
            continue
        if t["type"] == "compare" and not s.get("compare"):
            continue
        if t.get("chart") and t["chart"] not in CHARTS[t["type"]]:
            t["chart"] = CHARTS[t["type"]][0]
        t.setdefault("id", _new_id())
        good.append(t)
    s["tiles"] = good
    return s


# ------------------------------------------------------------------ edit commands
def _find_tiles(spec: dict[str, Any], words: str) -> list[dict[str, Any]]:
    w = words.lower()
    hits = []
    kind_words = {"map": ("region", "branch_name"), "region": ("region",), "rating": ("rating_current",), "migration": ("migration",),
                  "top names": ("top_names",), "top 20": ("top_names",), "names": ("top_names",), "table": ("top_names",), "reasons": ("reasons",),
                  "regulatory": ("regulatory",), "breaches": ("regulatory",), "cbuae": ("regulatory",),
                  "concentration": ("concentration",), "roll rate": ("roll_rate",), "vintage": ("vintage",), "stage mix": ("stage",),
                  "early warning band": ("ews_band",), "ews band": ("ews_band",), "trend": ("trend",)}
    for t in spec["tiles"]:
        title = (t.get("title") or "").lower()
        keys = {t.get("type"), t.get("dim"), t.get("column"), *(t.get("metrics") or []), t.get("metric")}
        if t.get("id") and t["id"] in words:
            hits.append(t)
            continue
        for k, v in kind_words.items():
            if _has(w, k) and keys & set(v):
                hits.append(t)
                break
        else:
            if t.get("column") and any(_has(w, x) for x, c in DIST_WORDS.items() if c == t["column"]):
                hits.append(t)
            elif title and len(w) > 3 and w in title:
                hits.append(t)
    return hits


def apply_command(spec: dict[str, Any], text: str) -> tuple[dict[str, Any], list[str]]:
    """Apply one conversational edit. Returns the new spec and what changed (one line per change)."""
    s = copy.deepcopy(spec)
    b = s["book"]
    t = text.lower().strip()
    done: list[str] = []
    # switch scope / book: "switch to retail personal finance", "change to Makkah"
    m = re.match(r"(?:switch|change|move)\s+(?:the lens\s+)?to\s+(.+)", t)
    if m:
        target = m.group(1)
        nb = detect_book(target, b)
        filters = detect_filters(target, nb)
        if nb != b or filters:
            new = build_spec(target, nb, title="")
            new["title"] = s["title"] if nb == b and not filters else new["title"]
            return new, [f"Switched to {new['scope_label']} ({'corporate' if nb == 'corporate' else 'retail'} book)"]
    # compare with a segment
    m = re.search(r"compare (?:it |this )?(?:with|to|against)\s+(.+)", t)
    if m:
        target = m.group(1)
        if target.strip(" .") in ("the book", "the whole book", "the portfolio", "all", "the bank"):
            filters, label = [], ("Corporate book" if b == "corporate" else "Retail book")
        else:
            filters = detect_filters(target, b)
            if not filters:
                raise LensError(f"I could not find '{target.strip()}' in the {b} book.")
            label = scope_label(b, filters)
        s["compare"] = {"label": label, "filters": filters}
        # the two comparison trends take the place of the lens's own coverage and staging trends (and of an earlier comparison)
        s["tiles"] = [x for x in s["tiles"] if x["type"] != "compare" and not (x["type"] == "trend" and set(x.get("metrics") or [])
                                                                               & {"coverage", "stage2_share"})]
        s["tiles"].insert(0, {"id": _new_id(), "type": "compare", "metric": "coverage"})
        s["tiles"].insert(1, {"id": _new_id(), "type": "compare", "metric": "stage2_share"})
        done.append(f"Compared with {label}: coverage and Stage 2 trends now show both, and the breakdowns show both side by side")
        return normalise(s), done
    # remove
    m = re.match(r"(?:remove|delete|drop|hide)\s+(?:the\s+)?(.+)", t)
    if m:
        hits = _find_tiles(s, m.group(1))
        if not hits:
            raise LensError(f"No tile on this lens matches '{m.group(1).strip()}'.")
        ids = {h["id"] for h in hits}
        s["tiles"] = [x for x in s["tiles"] if x["id"] not in ids]
        done.append(f"Removed {len(hits)} tile{'s' if len(hits) > 1 else ''}: " + ", ".join(h.get("title") or describe(h) for h in hits))
        return normalise(s), done
    # show by X instead
    m = re.search(r"(?:show|break (?:it )?down|split)\s+(?:it\s+|this\s+)?by\s+(.+?)(?:\s+instead)?$", t)
    if m and not t.startswith("add"):
        dim = detect_by("by " + m.group(1), b)
        if not dim:
            raise LensError(f"'{m.group(1)}' is not a dimension of the {b} book.")
        n = 0
        for x in s["tiles"]:
            if x["type"] == "breakdown" and x.get("dim") not in ("rating_current", "score_band", "stage", "product_type"):
                x["dim"] = dim
                x.pop("title", None)
                n += 1
        if not n:
            s["tiles"].insert(0, {"id": _new_id(), "type": "breakdown", "metric": "ecl", "dim": dim})
            n = 1
        done.append(f"Breakdowns now by {DIMS[dim].label.lower()} ({n} tile{'s' if n > 1 else ''})")
        return normalise(s), done
    # add
    m = re.match(r"(?:add|include|show|put)\s+(?:a\s+|an\s+|the\s+)?(.+)", t)
    if m:
        what = m.group(1)
        tile = tile_from_words(what, b)
        if tile is None:
            raise LensError(f"I could not turn '{what.strip()}' into a tile. Try a metric from the catalogue (Add ratio).")
        s["tiles"].insert(0, tile)
        done.append(f"Added: {tile.get('title') or describe(tile)}")
        return normalise(s), done
    raise LensError("That is not an edit I can make.")


def tile_from_words(what: str, book: str) -> dict[str, Any] | None:
    w = what.lower()
    if "distribution" in w or "histogram" in w:
        for k in sorted(DIST_WORDS, key=len, reverse=True):
            if _has(w, k) and book in DISTRIBUTIONS[DIST_WORDS[k]]["books"]:
                return {"id": _new_id(), "type": "distribution", "column": DIST_WORDS[k]}
    for word, typ in (("regulatory", "regulatory"), ("breach", "regulatory"), ("cbuae", "regulatory"),
                      ("compliance", "regulatory"), ("migration", "migration"), ("roll rate", "roll_rate"), ("vintage", "vintage"), ("concentration", "concentration"),
                      ("hhi", "concentration"), ("reason", "reasons"), ("top", "top_names")):
        if word in w:
            if typ in ("roll_rate", "vintage") and book != "retail":
                return None
            return {"id": _new_id(), "type": typ}
    metric = ""
    for k in sorted(METRIC_WORDS, key=len, reverse=True):
        if _has(w, k) and book in METRICS[METRIC_WORDS[k]].books:
            metric = METRIC_WORDS[k]
            break
    if not metric:
        return None
    dim = detect_by(w, book)
    if "map" in w:
        dim = "region"
    if dim:
        return {"id": _new_id(), "type": "breakdown", "metric": metric, "dim": dim}
    if "mix" in w and metric == "ead":
        return {"id": _new_id(), "type": "mix_trend", "metric": "ead", "dim": "stage"}
    return {"id": _new_id(), "type": "trend", "metrics": [metric]}


def describe(tile: dict[str, Any]) -> str:
    t = tile["type"]
    if t == "pinned":
        return tile.get("title") or "From the assistant"
    if t == "breakdown":
        return f"{METRICS[tile['metric']].label if tile['metric'] in METRICS else tile['metric']} by {DIMS[tile['dim']].label.lower()}"
    if t == "trend":
        return " and ".join(METRICS[m].label if m in METRICS else m for m in tile.get("metrics", [])) + " trend"
    if t == "distribution":
        return f"{DISTRIBUTIONS[tile['column']]['label']} distribution"
    return {"top_names": f"Top {tile.get('top') or 20} names by {METRICS.get(tile.get('metric', 'ead'), METRICS['ead']).label}",
            "mix_trend": f"{METRICS.get(tile.get('metric', 'ead'), METRICS['ead']).label} mix by {DIMS.get(tile.get('dim', 'stage'), DIMS['stage']).label.lower()}",
            "migration": "Stage migration", "roll_rate": "Roll rates", "vintage": "Vintage curves", "concentration": "Concentration: top 10 obligors",
            "reasons": "Early Warning reasons", "regulatory": "Regulatory breaches by article", "compare": f"{METRICS.get(tile.get('metric', 'coverage'), METRICS['coverage']).label} comparison"}.get(t, t.replace("_", " "))


# ------------------------------------------------------------------ edits by hand (the tile menu)
def apply_op(spec: dict[str, Any], op: dict[str, Any]) -> tuple[dict[str, Any], str]:
    s = copy.deepcopy(spec)
    kind = op.get("op")
    tid = op.get("tile_id", "")
    idx = next((i for i, x in enumerate(s["tiles"]) if x["id"] == tid), None)
    if kind in ("delete", "move", "chart", "metric", "dim", "filter", "rename") and idx is None:
        raise LensError(f"{tid} is not a tile of this lens.")
    if kind == "add_block":   # PLAN_R6 L2: a chart or table from an assistant answer, placed as a tile
        from backend.lenses_v5 import pinned
        new, change = pinned.add(s, op)
        return normalise(new), change
    if kind == "delete":
        x = s["tiles"].pop(idx)
        return normalise(s), f"Deleted {x.get('title') or describe(x)}"
    if kind == "move":
        x = s["tiles"].pop(idx)
        to = max(0, min(len(s["tiles"]), idx + (-1 if op.get("direction") == "up" else 1) if "to" not in op else int(op["to"])))
        s["tiles"].insert(to, x)
        return normalise(s), "Moved a tile"
    if kind == "chart":
        x = s["tiles"][idx]
        if op.get("chart") not in CHARTS[x["type"]]:
            raise LensError(f"A {x['type'].replace('_', ' ')} tile can be {', '.join(CHARTS[x['type']])}.")
        x["chart"] = op["chart"]
        return normalise(s), f"Chart type set to {op['chart']}"
    if kind == "metric":
        x = s["tiles"][idx]
        key = op.get("metric", "")
        custom = {c["key"] for c in s.get("custom_metrics") or []}
        if key not in custom and (key not in METRICS or s["book"] not in METRICS[key].books):
            raise LensError(f"'{key}' is not a metric of the {s['book']} book.")
        if x["type"] == "trend":
            x["metrics"] = [key]
        else:
            x["metric"] = key
        x.pop("title", None)
        return normalise(s), f"Metric set to {METRICS[key].label if key in METRICS else key}"
    if kind == "dim":
        x = s["tiles"][idx]
        if op.get("dim") not in DIMS or s["book"] not in DIMS[op["dim"]].books:
            raise LensError(f"'{op.get('dim')}' is not a dimension of the {s['book']} book.")
        x["dim"] = op["dim"]
        x.pop("title", None)
        return normalise(s), f"Now by {DIMS[op['dim']].label.lower()}"
    if kind == "rename":
        s["tiles"][idx]["title"] = str(op.get("title") or "")[:120]
        return normalise(s), "Renamed a tile"
    if kind == "filter":   # PLAN_R6 L5: per-tile filters ({dim, values}; empty values clear that dimension, no dim clears all)
        x = s["tiles"][idx]
        dim = str(op.get("dim") or "")
        if not dim:
            x.pop("filters", None)
            return normalise(s), "Tile filter cleared"
        if dim not in DIMS or s["book"] not in DIMS[dim].books:
            raise LensError(f"'{dim}' is not a dimension of the {s['book']} book.")
        vals = [str(v) for v in (op.get("values") or []) if str(v).strip()][:20]
        rest = [f for f in x.get("filters") or [] if f.get("dim") != dim]
        x["filters"] = [*rest, {"dim": dim, "values": vals}] if vals else rest
        if not x["filters"]:
            x.pop("filters")
        return normalise(s), (f"Tile filtered to {DIMS[dim].label.lower()} {', '.join(vals)}" if vals else f"Tile filter on {DIMS[dim].label.lower()} cleared")
    if kind == "add":
        tile = {k: v for k, v in (op.get("tile") or {}).items() if k in ("type", "metric", "metrics", "dim", "chart", "column", "top", "title")}
        tile["id"] = _new_id()
        new = normalise({**s, "tiles": [tile, *s["tiles"]]})
        if not new["tiles"] or new["tiles"][0]["id"] != tile["id"]:
            raise LensError("That tile cannot be built on this book.")
        return new, f"Added {tile.get('title') or describe(tile)}"
    if kind == "persona_plan":   # R16 M5: an approved persona metric plan rebuilds the lens (same book and scope)
        from backend.lenses_v5 import personas
        inc = op.get("include")
        return personas.apply_to(s, str(op.get("persona") or ""), [str(x) for x in inc] if isinstance(inc, list) else None)
    if kind == "kpis":
        s["kpis"] = list(op.get("kpis") or [])
        return normalise(s), "KPI row updated"
    if kind == "scope":
        s["filters"] = [f for f in op.get("filters") or [] if f.get("dim") in DIMS and f.get("values")]
        ENGINE.where(s["book"], s["filters"])
        s["scope_label"] = scope_label(s["book"], s["filters"])
        return normalise(s), f"Scope set to {s['scope_label']}"
    if kind == "period":
        if op.get("period") not in ENGINE.periods(s["book"]):
            raise LensError(f"{op.get('period')} is not a period of the {s['book']} book.")
        s["period"] = op["period"]
        return normalise(s), f"As of {op['period']}"
    if kind == "custom_ratio":
        c = {"key": "custom-" + uuid.uuid4().hex[:5], "label": str(op.get("label") or "Custom ratio")[:80], "num": op.get("num"), "den": op.get("den"),
             "filters": op.get("filters") or [], "scale": float(op.get("scale", 100)), "unit": "pct" if float(op.get("scale", 100)) == 100 else "ratio",
             "source": "Custom ratio", "better": op.get("better", "lower")}
        validate_custom(s["book"], c)
        s.setdefault("custom_metrics", []).append(c)
        s["tiles"].insert(0, {"id": _new_id(), "type": "trend", "metrics": [c["key"]], "title": f"{c['label']} trend"})
        s["kpis"].append(c["key"])
        return normalise(s), f"Added custom ratio {c['label']}"
    raise LensError(f"'{kind}' is not a lens edit.")


def validate_custom(book: str, c: dict[str, Any]) -> float | None:
    """The engine validates a custom ratio by running it on the as-of period of the whole book."""
    for k in ("num", "den"):
        if c.get(k) not in METRICS:
            raise LensError(f"Pick a {'numerator' if k == 'num' else 'denominator'} from the catalogue.")
    ENGINE.where(book, c.get("filters"))
    rows, _ = ENGINE.series(book, [], [ENGINE.as_of(book)], [c["key"]], custom={c["key"]: c})
    v = rows[0].get(c["key"]) if rows else None
    if v is None:
        raise LensError("The ratio has no value on this book (the denominator is zero or the filter matches nothing).")
    return v
