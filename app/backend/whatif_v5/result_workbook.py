"""The Excel export of a What-If result: every table behind the screen, one sheet each, in the house style."""
from __future__ import annotations

from typing import Any

from backend.house_style import Meta
from backend.house_style import xlsx as hx
from backend.house_style.xlsx import Col


def build(result: dict[str, Any], title: str, generated_by: str = "") -> bytes:
    lab = result["labels"]
    c = result["cards"]
    meta = Meta(f"What-If · {title}", book=lab["book"].lower(), period=result["period"],
                subject=f"{result['population']['label']} · {result['method_name']} · run {result['run_id']}",
                generated_by=generated_by)
    wb = hx.workbook(meta)
    hx.about_sheet(wb, meta, [("Scenario", "; ".join(s["restatement"] for s in result["steps"])),
                              ("Population", result["population"]["label"]), ("Method", result["method_name"]),
                              ("Run", result["run_id"]), ("Amounts", "SAR million")])
    sar = "sar_mn"
    hx.table_sheet(wb, "Summary", meta, [Col("f", "Figure"), Col("v", "Value", "num")], [
        ["Reported ECL (SAR m)", c["reported_ecl"]], ["Baseline ECL, method start (SAR m)", c["start_ecl"]],
        ["Scenario ECL (SAR m)", c["scenario_ecl"]], ["Change (SAR m)", c["change"]], ["Change %", c["change_pct"]],
        ["EAD before (SAR m)", c["ead_before"]], ["EAD after (SAR m)", c["ead_after"]],
        ["Coverage before %", c["coverage_before"]], ["Coverage after %", c["coverage_after"]],
        ["Stage 1 to 2", c["moves"]["1->2"]], ["Stage 2 to 3", c["moves"]["2->3"]], ["Stage 1 to 3", c["moves"]["1->3"]],
        ["CET1 before % (illustrative)", c["capital_cet1_before_pct"]], ["CET1 after % (illustrative)", c["capital_cet1_after_pct"]],
    ] + [[f"Step {i + 1}", s["restatement"]] for i, s in enumerate(result["steps"])], title=f"Summary · {title}")
    hx.table_sheet(wb, "Waterfall", meta, [Col("l", "Step"), Col("k", "Kind"), Col("v", "ECL", sar)],
                   [[b["label"], b["kind"], b["value"]] for b in result["waterfall"]], title="ECL decomposition waterfall")
    hx.table_sheet(wb, f"By {lab['segment'].lower()}", meta,
                   [Col("s", lab["segment"]), Col("a", "EAD before", sar), Col("b", "EAD after", sar),
                    Col("c", "ECL before", sar), Col("d", "ECL after", sar), Col("e", "Change", sar)],
                   [[r["segment"], r["ead_before"], r["ead_after"], r["ecl_before"], r["ecl_after"], r["change"]]
                    for r in result["by_segment"]], title=f"ECL by {lab['segment'].lower()}")
    hx.table_sheet(wb, f"By {lab['grade'].lower()}", meta,
                   [Col("g", lab["grade"], "rating"), Col("p", "Masterscale PD %", "pct"), Col("a", "EAD before", sar),
                    Col("b", "EAD after", sar), Col("c", "ECL before", sar), Col("d", "ECL after", sar)],
                   [[r["grade"], r["pd_masterscale_pct"], r["ead_before"], r["ead_after"], r["ecl_before"], r["ecl_after"]]
                    for r in result["by_rating"]], title=f"EAD and ECL by {lab['grade'].lower()} (global order)")
    mig = result["migration"]
    hx.table_sheet(wb, "Stage migration", meta,
                   [Col("f", "From \\ to"), Col("c1", "Stage 1 (count)", "int"), Col("c2", "Stage 2 (count)", "int"),
                    Col("c3", "Stage 3 (count)", "int"), Col("e1", "Stage 1 (EAD)", sar), Col("e2", "Stage 2 (EAD)", sar),
                    Col("e3", "Stage 3 (EAD)", sar)],
                   [[f"Stage {s}", *mig["counts"][i], *mig["ead"][i]] for i, s in enumerate(mig["stages"])],
                   title="Stage migration (count and EAD)")
    hx.table_sheet(wb, "Top movers", meta,
                   [Col("x", lab["exposure"]), Col("o", lab["owner"]), Col("n", "Name"), Col("s", lab["segment"]),
                    Col("gb", "Grade before", "rating"), Col("ga", "Grade after", "rating"), Col("sb", "Stage before", "int"),
                    Col("sa", "Stage after", "int"), Col("e", "EAD", sar), Col("b", "ECL before", sar), Col("a", "ECL after", sar),
                    Col("c", "Change", sar)],
                   [[m["exposure_id"], m["owner_id"], m["owner_name"], m["segment"], m["grade_before"], m["grade_after"],
                     m["stage_before"], m["stage_after"], m["ead"], m["ecl_before"], m["ecl_after"], m["change"]]
                    for m in result["top_movers"]], title="Top movers by facility")
    hx.table_sheet(wb, "Macro scenarios", meta,
                   [Col("s", "Scenario"), Col("w", "Weight", "share"), Col("b", "ECL before", sar), Col("a", "ECL after", sar)],
                   [[k, v["weight"], v["before"], v["after"]] for k, v in result["by_scenario"].items()],
                   title="ECL by macroeconomic scenario")
    return hx.to_bytes(wb)
