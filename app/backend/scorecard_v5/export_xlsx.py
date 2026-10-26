"""The validation's tables as an Excel workbook in the house style (backend/house_style)."""
from __future__ import annotations

from typing import Any

from backend.house_style import Meta, xlsx as hx
from backend.house_style.xlsx import Col

KIND = {"pct": "share", "pct2": "share", "num": "num", "num4": "num4", "int": "int", "text": "text", "rag": "text"}


def build(v: dict[str, Any], generated_by: str = "") -> bytes:
    res = v["result"]
    sc = res["scorecard"]
    meta = Meta(title=f"{sc['name']} v{sc['version']}: validation results", book=sc["book"], period=v["as_of"], subject=f"{sc['segment']} · {sc['type']}",
                generated_by=generated_by, reference=v["validation_id"])
    wb = hx.workbook(meta)
    s = res["summary"]
    hx.about_sheet(wb, meta, [("Scorecard", f"{sc['scorecard_id']} · {sc['name']} v{sc['version']}"), ("Monitoring window", f"{res['plan']['monitoring'][0]} to {res['plan']['monitoring'][1]}"),
                              ("Overall verdict", s["overall"].upper()), ("Tests", s["tests"]), ("Outcome", "Default within 12 months")])
    rows = []
    for sec in res["sections"]:
        for x in sec["tests"]:
            rows.append({"group": sec["title"], "test": x["label"], "value": x["value"] if isinstance(x["value"], (int, float)) else str(x["value"] or ""),
                         "threshold": x["threshold"], "verdict": x["status"].upper() if x["status"] != "na" else "N/A", "reading": x["comment"]})
    hx.table_sheet(wb, "Verdicts", meta, [Col("group", "Group", "text"), Col("test", "Test", "text"), Col("value", "Value", "num4"), Col("threshold", "Threshold", "text"),
                                          Col("verdict", "Verdict", "text"), Col("reading", "Reading", "text")], rows)
    for sec in res["sections"]:
        for t in sec["tables"]:
            cols = [Col(c["key"], c["label"], KIND.get(c["format"], "text")) for c in t["columns"]]
            data = [{c["key"]: (str(r.get(c["key"], "")).upper() if c["format"] == "rag" else r.get(c["key"])) for c in t["columns"]} for r in t["rows"]]
            hx.table_sheet(wb, t["id"][:28], meta, cols, data)
    return hx.to_bytes(wb)
