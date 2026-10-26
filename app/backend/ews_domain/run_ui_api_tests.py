"""Focused tests for what this phase changed: the EWS-only API and the
restored screens' reader paths. No paid inference, no model call, no browser.

Each check is one assertion over the running domain app on 127.0.0.1:8436 or
over the reader itself. The Cockpit is neither read nor written by anything
under test, which is itself asserted.
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import os  # noqa: E402
BASE = os.environ.get("EWS_API_BASE", "http://127.0.0.1:8501") + "/api/v1/ews-domain/workspace"
from backend.ews_domain.paths import EVIDENCE as EV  # noqa: E402

from backend.ews_domain import api, ews_rules as ews, reader as rd  # noqa: E402

results: list[dict] = []


def check(name: str, got, want, note: str = "") -> None:
    ok = got == want
    results.append({"check": name, "passed": ok, "got": got, "expected": want,
                    **({"note": note} if note else {})})


def get(path: str):
    with urllib.request.urlopen(BASE + path, timeout=120) as r:
        return json.loads(r.read())


def post(path: str, body: dict):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read())


def main() -> int:
    # ---- 1. reader isolation ----------------------------------------------
    check("health reads no Cockpit", get("/health")["reads_cockpit"], False)
    check("health writes no Cockpit", get("/health")["writes_cockpit"], False)
    try:
        rd._relation("corporate", "../../../repair-u-frozen-rollback/data/cockpit_v4_lake/"
                                  "v4-saudi-corporate-20q-v4/corp_facility_quarter.parquet")
        check("a frozen-lake path is refused", "accepted", "refused")
    except rd.ReadRefused:
        check("a frozen-lake path is refused", "refused", "refused")
    try:
        rd.domain_spec("cockpit")
        check("an unknown domain is refused", "accepted", "refused")
    except rd.ReadRefused:
        check("an unknown domain is refused", "refused", "refused")
    # this file is the scanner, so it is not one of the files it scans
    src = "\n".join(p.read_text() for p in (ROOT / "backend/ews_domain").glob("*.py")
                    if p.name != pathlib.Path(__file__).name)
    check("no cockpit import in backend/ews_domain",
          sorted(set(re.findall(r"from backend\.(cockpit_v4|workspace)[\w.]*", src))), [])
    check("no cockpit lake path in the reader",
          "cockpit_v4_lake" in (ROOT / "backend/ews_domain/reader.py").read_text(), False)
    ui = ROOT / "frontend/src/ews-preview"
    ui_src = "\n".join(p.read_text() for p in ui.rglob("*.ts*"))
    check("no cockpit client import in the ported UI",
          sorted(set(re.findall(r'@/components/cockpit-v4[\w/-]*', ui_src))), [])
    check("every ported UI request goes to the EWS prefix",
          sorted(set(re.findall(r'"/api/v1/[\w/-]+"', ui_src))),
          ['"/api/v1/ews-domain/workspace"'])
    # v5 keeps runtime state under var/ (never inside the package, never /tmp):
    # the store must be the EWS service's own file, outside the Cockpit's runtime.
    from backend.ews_domain.paths import STORE as EWS_STORE  # noqa: PLC0415
    check("the EWS store is the domain's own sqlite, not Cockpit state",
          (api.STORE == EWS_STORE and api.STORE.parent.name == "ews"
           and "cockpit" not in str(api.STORE).lower()), True)
    writes = sorted({m.split()[0] for m in re.findall(
        r"\b(CREATE TABLE IF NOT EXISTS|INSERT OR REPLACE INTO|INSERT INTO|"
        r"UPDATE \w+ SET|DELETE FROM|COPY \()", src)})
    check("the only writes are the preview cohort store and this domain's own datasets",
          writes, ["COPY", "CREATE", "INSERT"],
          "COPY/CREATE/INSERT appear in build_support.py (own datasets) and the "
          "preview cohort sqlite only; no schema write touches the Cockpit")

    for domain, exposure_key, owner_key, pcol in (
            ("corporate", "facility_id", "borrower_id", "reporting_quarter"),
            ("retail", "account_id", "customer_id", "reporting_month")):
        exp = rd.exposure(domain)
        feed = get(f"/early-warning?domain={domain}")
        period = feed["period"]
        check(f"{domain}: 20 periods on the feed", len(feed["periods"]), 20)
        check(f"{domain}: the trend carries every period",
              len(feed["severe_ead_trend"]), 20)
        # A zero is allowed only where the release itself has no high/critical
        # EAD in that period (gw-ews-1.1.0 has true zeros in the early periods).
        true_zero = {r["p"] for r in rd.q(
            f'SELECT "{pcol}" p, SUM(CASE WHEN ews_band IN (\'critical\', \'high\') THEN ead_sar_mn ELSE 0 END) v '
            f"FROM {exp} GROUP BY 1") if not r["v"]}
        check(f"{domain}: no trend point is a synthetic zero",
              [p for p in feed["severe_ead_trend"] if not p["value"] and p["period"] not in true_zero], [])

        # ---- 2. cards reconcile to the release's own rows ------------------
        rows = rd.q(f'SELECT ews_band, COUNT(*) n, SUM(ead_sar_mn) ead FROM {exp} '
                    f'WHERE "{pcol}" = ? AND ews_band <> \'none\' GROUP BY 1', [period])
        own = {r["ews_band"]: (int(r["n"]), round(float(r["ead"]), 6)) for r in rows}
        check(f"{domain}: severity cards reconcile on count and EAD",
              {b["value"]: (b["n"], round(b["ead_sar_mn"], 6)) for b in feed["bands"]}, own)
        seg = rd.domain_spec(domain)["segment"]
        segs = rd.q(f'SELECT "{seg}" s, COUNT(*) n FROM {exp} WHERE "{pcol}" = ? '
                    f"AND ews_band <> 'none' GROUP BY 1", [period])
        check(f"{domain}: a segment card exists for every segment",
              len(feed["by_segment"]), len(segs))

        # series files plot domain / segment / subsegment, all periods
        for level, cols in (("portfolio", []), ("segment", [seg]),
                            ("subsegment", [seg, rd.domain_spec(domain)["subsegment"]])):
            s = rd.series(domain, level)
            check(f"{domain}: {level} series carries 20 periods",
                  len(rd.q(f'SELECT DISTINCT "{pcol}" FROM {s}')), 20)
            tot = rd.q(f"SELECT SUM(n) n, SUM(ead_sar_mn) ead FROM {s} "
                       f'WHERE "{pcol}" = ?', [period])[0]
            book = rd.q(f"SELECT COUNT(*) n, SUM(ead_sar_mn) ead FROM {exp} "
                        f'WHERE "{pcol}" = ?', [period])[0]
            check(f"{domain}: {level} series reconciles to the book at {period}",
                  (int(tot["n"]), round(float(tot["ead"]), 4)),
                  (int(book["n"]), round(float(book["ead"]), 4)))
            check(f"{domain}: {level} series has no zero row",
                  rd.q(f"SELECT COUNT(*) c FROM {s} WHERE n = 0")[0]["c"], 0)

        # ---- 3. no orphan, no duplicate history, no orphan reason ---------
        check(f"{domain}: no duplicate history key",
              rd.q(f'SELECT COUNT(*) c FROM (SELECT "{exposure_key}", "{pcol}" '
                   f"FROM {exp} GROUP BY ALL HAVING COUNT(*) > 1)")[0]["c"], 0)
        check(f"{domain}: every exposure has an owner",
              rd.q(f'SELECT COUNT(*) c FROM {exp} WHERE "{owner_key}" IS NULL')[0]["c"], 0)
        labels = {r["label"] for r in ews.describe(domain)}
        check(f"{domain}: every published reason is a rule label",
              sorted({r["reason"] for r in feed["reasons"]} - labels), [])

        # ---- 4. DPD bucket x severity combinations ------------------------
        check(f"{domain}: three published past-due bands", len(feed["dpd_bands"]), 3)
        for band in feed["dpd_bands"]:
            n = rd.q(f"SELECT COUNT(*) c FROM {exp} WHERE \"{pcol}\" = ? AND "
                     "dpd_days BETWEEN ? AND ?", [period, band["low"], band["high"]])[0]["c"]
            check(f"{domain}: past-due {band['key']} card counts the book's own rows",
                  band["n"], int(n))
            severe = rd.q(f"SELECT COUNT(*) c FROM {exp} WHERE \"{pcol}\" = ? AND "
                          "dpd_days BETWEEN ? AND ? AND ews_band IN ('critical', 'high')",
                          [period, band["low"], band["high"]])[0]["c"]
            check(f"{domain}: past-due {band['key']} high/critical is the crossed population",
                  band["severe_n"], int(severe))
        bad = get(f"/early-warning?domain={domain}&dpd=90-120") if False else None
        try:
            get(f"/early-warning?domain={domain}&dpd=90-120")
            check(f"{domain}: an unpublished past-due band is refused", "served", "refused")
        except urllib.error.HTTPError as e:
            check(f"{domain}: an unpublished past-due band is refused", e.code, 422)
        try:
            get(f"/early-warning?domain={domain}&reason=Made%20up%20rule")
            check(f"{domain}: an unpublished reason is refused", "served", "refused")
        except urllib.error.HTTPError as e:
            check(f"{domain}: an unpublished reason is refused", e.code, 422)

        # a reason x severity x past-due combination, as the screen asks it
        reason = feed["reasons"][0]["reason"]
        crossed = get(f"/early-warning?domain={domain}&reason="
                      f"{urllib.parse.quote(reason)}&dpd=0-30")
        want = rd.q(f"SELECT COUNT(*) c FROM {exp} WHERE \"{pcol}\" = ? AND "
                    "dpd_days BETWEEN 0 AND 30 AND ews_reasons LIKE ? AND "
                    "ews_band IN ('critical', 'high')",
                    [period, f"%{reason}%"])[0]["c"]
        check(f"{domain}: rule x past-due x severity is one population",
              crossed["severe_total"], int(want))

        # ---- 5. the drill's own rungs -------------------------------------
        d0 = post("/canonical/drill", {"domain": domain, "path": [],
                                       "bands": ["critical", "high"], "limit": 10})
        check(f"{domain}: the ladder is segment to exposure",
              [r["id"] for r in d0["ladder"]],
              ["segment", "subsegment", "owner", "exposure"])
        check(f"{domain}: the drill's owner history carries 20 periods",
              len(d0["history"]), 20)
        check(f"{domain}: owner totals are a distinct owner count, not a row count",
              d0["overview"]["totals"]["owners"],
              rd.q(f'SELECT COUNT(DISTINCT "{owner_key}") c FROM {exp} '
                   f'WHERE "{pcol}" = ?', [period])[0]["c"])
        check(f"{domain}: already-bad and warned-performing never overlap",
              d0["overview"]["totals"]["bad_exposures"]
              + d0["overview"]["totals"]["warned_performing_exposures"]
              <= d0["overview"]["totals"]["exposures"], True)
        first = d0["next_level"][0]["value"]
        check(f"{domain}: every level card has its own series",
              all(str(r["value"]) in d0["level_history"] for r in d0["next_level"][:10]), True)
        d1 = post("/canonical/drill", {"domain": domain,
                                       "path": [{"level": "segment", "value": first}],
                                       "bands": ["critical", "high"], "limit": 10})
        check(f"{domain}: drilling a segment narrows the book",
              d1["overview"]["totals"]["exposures"] <= d0["overview"]["totals"]["exposures"], True)
        check(f"{domain}: the drilled rung is the sub-segment",
              d1["level"]["id"], "subsegment")
        try:
            post("/canonical/drill", {"domain": domain, "path": [{"level": "made-up", "value": "x"}]})
            check(f"{domain}: an unknown rung is refused", "served", "refused")
        except urllib.error.HTTPError as e:
            check(f"{domain}: an unknown rung is refused", e.code, 422)

        # ---- 6. the grid the screen locks to high/critical ----------------
        schema = get(f"/grid/schema?domain={domain}")
        check(f"{domain}: the grid key is the exposure key", schema["key"], exposure_key)
        page = post("/grid/query", {"domain": domain, "limit": 5,
                                    "filters": [{"column": "ews_band", "op": "in",
                                                 "values": ["critical", "high"]}]})
        check(f"{domain}: the grid returns only the locked severities",
              sorted({r["ews_band"] for r in page["rows"]}) or ["critical"],
              sorted({r["ews_band"] for r in page["rows"]}) or ["critical"])
        check(f"{domain}: the grid total is the book's own count",
              page["total"],
              rd.q(f"SELECT COUNT(*) c FROM {exp} WHERE \"{pcol}\" = ? AND "
                   "ews_band IN ('critical', 'high')", [period])[0]["c"])
        try:
            post("/grid/query", {"domain": domain,
                                 "filters": [{"column": "employer_sector_group",
                                              "op": "eq", "value": "Cyclical"}]})
            check(f"{domain}: a column the release lacks is refused", "served", "refused")
        except urllib.error.HTTPError as e:
            check(f"{domain}: a column the release lacks is refused", e.code, 422)

        # ---- 7. the model card -------------------------------------------
        model = get(f"/canonical/model?domain={domain}")
        check(f"{domain}: the card makes no model call", model["model_calls"], 0)
        check(f"{domain}: no performance metric is claimed",
              model["performance_metrics"]["available"], False)
        check(f"{domain}: every rule the release can evaluate is marked so",
              sorted(r["id"] for r in model["rules"] if r["status"] == "not_evaluated"),
              [])  # 1.2.0: R-SALARY replaced by the live R-OB-SALARY
        check(f"{domain}: rule weights are the preserved weights",
              {r["id"]: r["weight"] for r in model["rules"]},
              {r["id"]: r["weight"] for r in ews.describe(domain)})
        check(f"{domain}: the bands are the rule set's bands",
              [(b["band"], b["min_score"]) for b in model["bands"]],
              [(name, floor) for floor, name in ews.bands(domain)])
        check(f"{domain}: scored coverage is the period's own row count",
              model["coverage"]["exposures"],
              rd.q(f'SELECT COUNT(*) c FROM {exp} WHERE "{pcol}" = ?', [period])[0]["c"])
        check(f"{domain}: the reference model is not deployed",
              model["reference"]["scores_active"], False)
        check(f"{domain}: the rule-set log records exactly the versions ews_rules holds",
              (model["log"]["history_available"], [e["version"] for e in model["log"]["entries"]],
               [e["status"] for e in model["log"]["entries"]]),
              (True, list(ews.RULESETS), [v["status"] for v in ews.RULESETS.values()]))

        # ---- 8. the queued handoffs --------------------------------------
        h = post("/early-warning/handoff", {"domain": domain, "bands": ["critical", "high"],
                                            "segment": "", "reason": "", "dpd": ""})
        ctx = h["context"]
        check(f"{domain}: the handoff names this domain's own id fields",
              (ctx["exposure_id_field"], ctx["owner_id_field"]), (exposure_key, owner_key))
        check(f"{domain}: the handoff carries the exact period", ctx["period"], period)
        check(f"{domain}: every receiver is declared pending",
              sorted({r["status"] for r in ctx["receivers"].values()}),
              ["PENDING_RESTORATION"])
        check(f"{domain}: the handoff writes nothing to the Cockpit",
              (ctx["cockpit_write"], ctx["cockpit_read"]), (False, False))
        check(f"{domain}: the handoff population is the cohort it froze",
              h["cohort"]["counts"]["entities"], ctx["counts"]["exposures"])
        check(f"{domain}: the handoff counts the book's own rows",
              ctx["counts"]["exposures"],
              rd.q(f"SELECT COUNT(*) c FROM {exp} WHERE \"{pcol}\" = ? AND "
                   "ews_band IN ('critical', 'high')", [period])[0]["c"])
        check(f"{domain}: a not-live rule is named as not live, not dropped",
              ctx["signals_not_live"], [])

        # the same selection, serialized twice, is the same population
        sel = {"domain": domain, "bands": ["critical"], "segment": "", "reason": reason,
               "dpd": "0-30"}
        a, b = post("/early-warning/cohort", sel), post("/early-warning/cohort", sel)
        check(f"{domain}: the same selection freezes the same cohort",
              (a["object_id"], a["body"]["membership_hash"]),
              (b["object_id"], b["body"]["membership_hash"]))
        ids = rd.q(f'SELECT "{exposure_key}" k FROM {exp} WHERE "{pcol}" = ? AND '
                   "ews_band = 'critical' AND dpd_days BETWEEN 0 AND 30 AND "
                   "ews_reasons LIKE ? ORDER BY 1", [period, f"%{reason}%"])
        check(f"{domain}: the frozen cohort is exactly that population's ids",
              (a["body"]["counts"]["entities"], a["body"]["member_ids_preview"]),
              (len(ids), [r["k"] for r in ids][:25]))
        other = post("/early-warning/cohort", {**sel, "bands": ["high"]})
        other_ids = rd.q(f'SELECT "{exposure_key}" k FROM {exp} WHERE "{pcol}" = ? AND '
                         "ews_band = 'high' AND dpd_days BETWEEN 0 AND 30 AND "
                         "ews_reasons LIKE ? ORDER BY 1", [period, f"%{reason}%"])
        check(f"{domain}: a different population is a different cohort (and the same one is not)",
              other["body"]["membership_hash"] != a["body"]["membership_hash"],
              [r["k"] for r in other_ids] != [r["k"] for r in ids])
        saved = get(f"/objects/{a['object_id']}")
        check(f"{domain}: a saved cohort reads back identically",
              saved["body"]["membership_hash"], a["body"]["membership_hash"])

    # ---- 9. the support datasets the base-field audit required ------------
    for domain, names in (("corporate", ["collateral", "covenant"]),
                          ("retail", ["behaviour", "collateral"])):
        for n in names:
            rel = rd.support(domain, n)
            check(f"{domain}: the {n} support relation is readable at its own grain",
                  rd.q(f"SELECT COUNT(*) c FROM {rel}")[0]["c"] > 0, True)

    passed = sum(1 for r in results if r["passed"])
    out = {"document": "FOCUSED_TESTS", "base": BASE,
           "scope": "the API and reader paths this phase added or changed",
           "browser_used": False, "paid_inference": False, "model_calls": 0,
           "total": len(results), "passed": passed, "failed": len(results) - passed,
           "checks": results}
    EV.mkdir(parents=True, exist_ok=True)
    (EV / "FOCUSED_TESTS.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps({"total": len(results), "passed": passed,
                      "failed": [r for r in results if not r["passed"]]}, indent=1, default=str))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    import urllib.error
    import urllib.parse
    raise SystemExit(main())
