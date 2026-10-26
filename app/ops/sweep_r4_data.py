"""UAT sweep, PLAN_R4 18:58 (part "r4-data"): every module's data appears in Data Builder.

The overview lists every live domain -- Cockpit, Early Warning, Bureau, Open Banking, Scorecard Validation, What-If,
Branches and RMs, and Deal Desk once its session's branch is merged -- with its relations and row counts equal to the
API; the sidebar lists the same domains. Each domain's rows, dictionary, search, filter and exports are swept by the
Data Builder steps of part "modules" (step C), which walk every live domain.
Imported by ops/uat_sweep.py, which puts ops/ on the path and passes the Sweep.
"""
from __future__ import annotations

import json
import urllib.request
from typing import Any, Callable

from uat_sweep_core import tid

DATA = "http://127.0.0.1:8504/api/v1/data"
#: PLAN_R4 18:58: these must be live (Deal Desk is required once v5/r4-dealdesk is merged).
REQUIRED = {"cockpit", "ews", "bureau", "open_banking", "scorecard", "what_if", "branches"}


def data_steps(s, page, UI: str, wait_for: Callable[..., Any]) -> None:
    with urllib.request.urlopen(f"{DATA}/domains", timeout=120) as r:  # noqa: S310 - loopback
        doms = [d for d in json.loads(r.read())["domains"] if d["status"] == "live"]
    live = {d["domain"] for d in doms}
    from pathlib import Path
    required = REQUIRED | ({"deal_desk"} if (Path(__file__).resolve().parents[1] / "backend" / "dealdesk").exists() else set())

    s.start("both", "R4-DB1", "Data Builder lists every module's data: overview cards and sidebar, row counts equal the API")
    s.check("every required domain is live", required <= live, sorted(required), sorted(live))
    page.goto(UI + "/data-builder", wait_until="domcontentloaded")
    page.wait_for_selector(tid("db-overview"), timeout=90_000)
    page.wait_for_selector(tid(f"db-domain-{doms[0]['domain']}"), timeout=90_000)
    s.check("overview: domain count", str(len(doms)) in page.inner_text(tid("db-sum-domains")), len(doms), page.inner_text(tid("db-sum-domains")))
    for d in doms:
        card = tid(f"db-domain-card-{d['domain']}")
        shown = page.inner_text(card) if page.locator(card).count() else ""
        s.check(f"{d['label']}: card shows its relations and rows",
                f"{len(d['relations'])} relations · {d['rows']:,} rows" in shown, f"{len(d['relations'])} relations · {d['rows']:,} rows", shown[:120])
        s.check(f"{d['label']}: in the sidebar", page.locator(tid(f"db-domain-{d['domain']}")).count() >= 1)
    s.check("no placeholder domain shown", page.locator(tid("db-coming")).count() == 0 and "coming" not in page.inner_text(tid("db-domains")).lower())

    s.start("both", "R4-DB2", "Each new domain opens a relation: grid rows, dictionary and Back")
    for dom in ("scorecard", "what_if", "branches"):
        d = next((x for x in doms if x["domain"] == dom), None)
        if not d:
            s.check(f"{dom} listed", False)
            continue
        rel = d["relations"][0]["relation"]
        page.goto(UI + f"/data-builder?domain={dom}&relation={rel}", wait_until="domcontentloaded")
        page.wait_for_selector(tid("db-grid"), timeout=90_000)
        s.check(f"{dom}/{rel}: grid has rows", page.locator(f'{tid("db-grid")} tbody tr').count() > 0)
        with urllib.request.urlopen(f"{DATA}/relations/{dom}/{rel}/schema", timeout=120) as r:  # noqa: S310
            schema = json.loads(r.read())
        page.click(tid("db-dictionary"))
        page.wait_for_selector(tid(f"db-dict-row-{schema['columns'][0]['name']}"), timeout=30_000)
        s.check(f"{dom}/{rel}: dictionary has one row per field", page.locator('[data-testid^="db-dict-row-"]').count() == len(schema["columns"]),
                len(schema["columns"]), page.locator('[data-testid^="db-dict-row-"]').count())
        s.check(f"{dom}/{rel}: every field has a written definition", all(c["source"] != "derived" for c in schema["columns"]))
        page.go_back()
        page.wait_for_selector(tid("db-grid"), timeout=30_000)
    s.finish()
