"""Export to Excel: one sheet per Borrower 360 tab (or the one asked for), plus About, in the house style.

Each sheet holds the tab's summary figures and every table on the tab, in the
order the screen shows them. Rows come from the same tab builders the screen
reads (`service.tab`), so the workbook and the screen cannot disagree. Ratings
tables keep the order the service gives them: period order for histories, the
global rating order (backend/v5common/ratings.py) for any table by rating.
Styling (header block, brand header rows, banding, filters, number formats) is
backend.house_style; nothing here styles a cell.
"""
from __future__ import annotations

from typing import Any

from backend.b360 import service
from backend.ews_domain import ews_rules as ews
from backend.house_style import Meta
from backend.house_style import xlsx as hx
from backend.house_style.xlsx import Block, Col
from backend.v5common import ratings

#: Borrower 360 units to house-style kinds.
KINDS = {"sar_mn": "sar_mn", "sar_k": "sar_k", "pct": "pct1", "prob": "prob", "x": "x", "num": "num",
         "months": "months", "int": "int", "days": "days"}


def _kind(unit: str, key: str = "") -> str:
    if unit in KINDS:
        return KINDS[unit]
    return "rating" if ("rating" in key or "grade" in key or key in ("band", "ews_band")) else ""


def _tab_blocks(tab: dict[str, Any]) -> list[Block]:
    blocks: list[Block] = []
    if tab.get("note"):
        blocks.append(Block(note=tab["note"]))
    if tab.get("summary"):
        blocks.append(Block(title="Summary", pairs=[(f["label"], f["value"], _kind(f.get("unit", ""))) for f in tab["summary"]]))
    for t in tab.get("tables", []):
        cols = t["columns"]
        per_row_unit = any(c["unit"] == "@unit" for c in cols)
        hcols = [Col(c["key"], c["label"] or c["key"], "" if c["unit"] == "@unit" else _kind(c["unit"], c["key"])) for c in cols]
        rows = [[r.get(c["key"]) for c in cols] + ([r.get("unit", "")] if per_row_unit else []) for r in t["rows"]]
        row_kinds = ([[_kind(r.get("unit", "")) if c["unit"] == "@unit" else "" for c in cols] for r in t["rows"]]
                     if per_row_unit else None)
        if per_row_unit:
            hcols.append(Col("unit", "Unit"))
        blocks.append(Block(title=t["title"], note=t.get("note") or "", columns=hcols, rows=rows, row_kinds=row_kinds))
    return blocks


def _meta(domain_id: str, owner_id: str, name: str, period: str, title: str, by: str) -> Meta:
    who = f"{owner_id} {name}".strip()
    return Meta(f"{title} · {who}", book=domain_id, period=period,
                subject=("Customer " if domain_id == "retail" else "Borrower ") + who, generated_by=by)


def workbook(domain_id: str, owner_id: str, period: str = "", tab_key: str = "", generated_by: str = "") -> tuple[bytes, str]:
    ctx = service.Ctx(domain_id, owner_id, period)
    keys = [tab_key] if tab_key else service.tab_keys(domain_id)
    tabs = [service.tab(domain_id, owner_id, ctx.period, k, ctx) for k in keys]
    p = ctx.profile
    meta = _meta(domain_id, owner_id, p.get("name") or "", ctx.period, "Borrower 360", generated_by)
    wb = hx.workbook(meta)
    lines: list[tuple[str, Any]] = [
        ("Borrower 360", ""),
        ("Book", domain_id),
        ("Customer" if domain_id == "retail" else "Borrower", owner_id),
        ("Name", p.get("name") or "—"),
        ("Period", ctx.period),
        ("As of", p.get("as_of")),
        ("Tabs", ", ".join(t["label"] for t in tabs)),
        ("Book release", p["releases"]["book"]),
        ("Early Warning release", p["releases"]["ews"]),
        ("Early Warning rule set", ews.RULESET_VERSION),
        ("Band floors (moderate, high, critical)", ", ".join(str(x) for x in ews.BAND_FLOORS[domain_id])),
        ("Bureau release", p["releases"]["bureau"]),
        ("Open Banking release", p["releases"]["open_banking"]),
        ("Rating order", " > ".join(ratings.RATING_ORDER) + " (best to worst; backend/v5common/ratings.py)"),
        ("Amounts", "SAR million unless a column says SAR thousand"),
    ]
    hx.about_sheet(wb, meta, lines)
    for t in tabs:
        hx.blocks_sheet(wb, t["label"], meta, _tab_blocks(t),
                        title=f"{t['label']} · {owner_id}" + (f" · {p['name']}" if p.get("name") else "") + f" · {t['period']}")
    name = f"borrower360_{domain_id}_{owner_id}_{ctx.period}" + (f"_{tab_key}" if tab_key else "") + ".xlsx"
    return hx.to_bytes(wb), name


def relationships_workbook(domain_id: str, owner_id: str, period: str = "", depth: int = 1,
                           generated_by: str = "") -> tuple[bytes, str]:
    """The borrower's relationships as a workbook: the nodes and edges drawn, and every analytic beside the graph."""
    from backend.b360 import graph as rel

    g = rel.build(domain_id, owner_id, period, depth)
    a = g["analytics"]
    ctx_period = g["period"]
    focal = g["focal"]
    meta = _meta(domain_id, owner_id, focal.get("name") or "", ctx_period, "Relationships", generated_by)
    wb = hx.workbook(meta)
    manifest = service.manifest("relationships") if "relationships" in service.paths.MANIFESTS else {}
    lines: list[tuple[str, Any]] = [
        ("Relationships", f"{owner_id} " + (focal.get("name") or "")),
        ("Book", domain_id), ("Period", ctx_period), ("Depth", f"{g['depth']} step" + ("s" if g["depth"] > 1 else "")),
        ("Nodes drawn", len(g["nodes"])), ("Links drawn", len(g["edges"])),
        ("Relationship release", manifest.get("release_id", "")), ("Early Warning rule set", ews.RULESET_VERSION),
        ("Amounts", "SAR million"),
        ("How to read it", "A link reads from the borrower outward: toward the borrower a supply link is a supplier, away from it a customer."),
    ]
    if domain_id == "corporate" and a["group"].get("policy"):
        p = a["group"]["policy"]
        lines.append((f"{p['clause']} {p['title']}", f"SAR {p['limit_sar_mn']:,.0f}m"))
    hx.about_sheet(wb, meta, lines)

    def sheet(title: str, columns: list[tuple[str, str, str]], data: list[dict[str, Any]], tail: list[tuple[str, Any, str]] = ()) -> None:
        cols = [Col(k, label, _kind(unit, k)) for k, label, unit in columns]
        if tail:
            hx.blocks_sheet(wb, title, meta, [Block(columns=cols, rows=data, empty="(none)"), Block(pairs=tail)],
                            title=f"{title} · {owner_id} · {ctx_period}")
        else:
            hx.table_sheet(wb, title, meta, cols, data, title=f"{title} · {owner_id} · {ctx_period}", empty="(none)")

    sheet("Nodes", [("id", "Id", ""), ("type", "Type", ""), ("name", "Name", ""), ("sector", "Sector", ""), ("region", "Region", ""),
                    ("rating", "Rating", ""), ("ews_band", "EWS band", ""), ("ews_score", "EWS score", "int"),
                    ("exposure", "EAD", "sar_mn"), ("ecl", "ECL", "sar_mn"), ("hop", "Steps from borrower", "int"),
                    ("is_focal", "Borrower", "")], g["nodes"])
    sheet("Links", [("id", "Id", ""), ("source", "From", ""), ("target", "To", ""), ("kind", "Kind", ""), ("type", "Type", ""),
                    ("label", "Detail", ""), ("ownership_pct", "Ownership %", "pct"), ("purchase_share_pct", "Share of purchases %", "pct"),
                    ("revenue_share_pct", "Share of revenue %", "pct"), ("annual_value_sar_mn", "Annual value", "sar_mn"),
                    ("facility_id", "Facility", ""), ("guarantee_amount_sar_mn", "Guarantee value", "sar_mn"),
                    ("collateral_id", "Shared asset", "")], g["edges"])
    if domain_id == "corporate":
        grp = a["group"]
        tail = ([("Group", f"{grp['group_id']} {grp['group_name']}", ""), ("Group EAD (SAR million)", grp["exposure"], "sar_mn"),
                 (f"{grp['policy']['clause']} limit (SAR million)", grp["policy"]["limit_sar_mn"], "sar_mn"),
                 ("Limit used %", round(grp["utilisation_pct"], 2), "pct"), ("Status", grp["status"], "")]
                if grp.get("rows") else [])
        sheet("Group vs limit", [("borrower_id", "Borrower", ""), ("name", "Name", ""), ("role", "Role", ""), ("ownership_pct", "Held by parent %", "pct"),
                                 ("exposure", "EAD", "sar_mn"), ("share_pct", "Share of group %", "pct"), ("rating", "Rating", ""),
                                 ("ews_band", "EWS band", "")], grp.get("rows", []), tail)
        scols = [("borrower_id", "Borrower", ""), ("name", "Name", ""), ("sector", "Sector", ""), ("purchase_share_pct", "Share of purchases %", "pct"),
                 ("revenue_share_pct", "Share of their revenue %", "pct"), ("annual_value_sar_mn", "Annual value", "sar_mn"),
                 ("exposure", "EAD with the bank", "sar_mn"), ("rating", "Rating", ""), ("ews_band", "EWS band", "")]
        sheet("Suppliers", scols, a["suppliers"]["rows"])
        sheet("Customers", scols, a["customers"]["rows"])
        sheet("Contagion", [("borrower_id", "Borrower", ""), ("name", "Name", ""), ("kinds", "Linked as", ""), ("ews_band", "EWS band", ""),
                            ("ews_score", "EWS score", "int"), ("exposure", "EAD", "sar_mn"), ("rating", "Rating", ""),
                            ("watchlist", "Watchlist", "")], [{**r, "kinds": ", ".join(r["kinds"])} for r in a["contagion"]["rows"]])
        flat = [{"collateral_id": x["collateral_id"], "type": x["type"], "market_value": x["market_value"], "total_pct": x["total_pct"],
                 "over_pledged": x["over_pledged"], **c} for x in a["collateral"]["assets"] for c in x["claims"]]
        sheet("Shared collateral", [("collateral_id", "Asset", ""), ("type", "Type", ""), ("market_value", "Market value", "sar_mn"),
                                    ("borrower_id", "Claimant", ""), ("name", "Name", ""), ("facility_id", "Facility", ""),
                                    ("claim", "Claim", "sar_mn"), ("allocation_pct", "Claim of value %", "pct"),
                                    ("total_pct", "All claims of value %", "pct"), ("over_pledged", "Over-pledged", "")], flat)
        sheet("Guarantees", [("direction", "Direction", ""), ("guarantor_id", "Guarantor", ""), ("guarantor", "Guarantor name", ""),
                             ("guaranteed_id", "Guaranteed", ""), ("guaranteed", "Guaranteed name", ""), ("facility_id", "Facility", ""),
                             ("amount", "Guarantee value", "sar_mn"), ("basis", "Guarantor is", ""), ("guarantor_band", "Guarantor EWS band", "")],
              a["guarantees"]["rows"])
        sheet("People", [("person_id", "Person", ""), ("name", "Name", ""), ("roles", "Roles", "")], a["people"]["rows"])
    else:
        sheet("Household", [("customer_id", "Customer", ""), ("role", "Role", ""), ("exposure", "EAD", "sar_mn"), ("ecl", "ECL", "sar_mn"),
                            ("rating", "Behaviour band", ""), ("ews_band", "EWS band", "")], a["household"]["rows"])
        e = a["employer"]
        sheet("Employer", [("borrower_id", "Borrower", ""), ("name", "Name", ""), ("sector", "Sector", ""), ("exposure", "EAD", "sar_mn"),
                           ("rating", "Rating", ""), ("ews_band", "EWS band", "")], [e["employer"]] if e.get("employer") else [])
    return hx.to_bytes(wb), f"relationships_{domain_id}_{owner_id}_{ctx_period}.xlsx"


#: List units to house-style kinds (the list's own units; see booklist.COLUMNS).
LIST_KINDS = {"id": "", "text": "", "rating": "rating", "ews_band": "rating", "int": "int", "days": "days",
              "sar_mn": "sar_mn", "num": "num", "flag": ""}


def list_workbook(view: Any, keys: list[str] | None = None, generated_by: str = "") -> tuple[bytes, str]:
    """The Borrower 360 list as the screen holds it: every row of the filtered view, in its order, the chosen columns."""
    from backend.b360 import booklist
    from backend.house_style import stream

    data, sort, direction = booklist.all_rows(view)
    cols = booklist.columns(view.domain_id)
    known = {c.key: c for c in cols}
    chosen = [known[k] for k in (keys or []) if k in known] or [c for c in cols if c.default]
    if "id" not in [c.key for c in chosen]:
        chosen = [known["id"], *chosen]
    lab = booklist.labels(view.domain_id)
    corporate = view.domain_id == "corporate"
    filters = [(lab.get(k, k), v) for k, v in (view.filters or {}).items() if v not in (None, "")]
    if view.ead_min is not None:
        filters.append(("EAD from (SAR m)", view.ead_min))
    if view.ead_max is not None:
        filters.append(("EAD to (SAR m)", view.ead_max))
    if view.q:
        filters.append(("Search", view.q))
    scope = "; ".join(f"{k} {v}" for k, v in filters) or "Whole book"
    title = f"Borrower 360 · {'Corporate borrowers' if corporate else 'Retail customers'}"
    meta = Meta(title, book=view.domain_id, period=view.period, subject=scope, generated_by=generated_by)

    def value(r: dict[str, Any], c: Any) -> Any:
        v = r.get(c.key)
        if c.unit == "flag":
            return None if v is None else ("Yes" if v else "No")
        return v

    sheet = stream.Sheet("Borrowers" if corporate else "Customers", meta,
                         [Col(c.key, c.label, LIST_KINDS.get(c.unit, "")) for c in chosen],
                         ([value(r, c) for c in chosen] for r in data), title=f"{title} · {view.period}")
    sort_label = next((c.label for c in cols if c.key == sort), sort)
    about = [
        ("Book", view.domain_id), ("Period", view.period),
        ("Book release", service.SPEC[view.domain_id]["book"]),
        ("Early Warning release", service.SPEC[view.domain_id]["ews_release"]),
        ("Early Warning rule set", ews.RULESET_VERSION),
        *[(f"Filter: {k}", v) for k, v in filters],
        ("Sorted by", f"{sort_label} ({'descending' if direction == 'desc' else 'ascending'})"),
        (f"Rows: {lab['owners']}", len(data)),
        ("EAD total (SAR m)", round(sum(float(r.get("ead") or 0) for r in data), 2)),
        ("ECL total (SAR m)", round(sum(float(r.get("ecl") or 0) for r in data), 2)),
        ("Amounts", "SAR million; EAD, ECL and limit are sums over the owner's exposures at the period"),
    ]
    body = stream.write([sheet, stream.about(meta, about)], meta)
    return body, f"borrower360_{view.domain_id}_list_{view.period}.xlsx"
