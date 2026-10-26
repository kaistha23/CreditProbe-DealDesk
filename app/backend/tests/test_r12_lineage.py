"""R12 lineage and no-side-door harness (PLAN_R12 §0 "Tests"; Session E owns it, every session adds cases).

    python3 -m pytest -q backend/tests/test_r12_lineage.py

How to add your session's cases:
  * LINEAGE_CASES: a (name, callable) whose result is an API response or paper model; every figure in it
    ({"value": <number>, "source": {domain, relation, key, period, column}}) must resolve to a registered row.
    Build figures with backend.dealdesk.data.lineage.figure(relation, row, column).
  * SCOPED_SOURCES: your R12 modules; a data-file literal in them that is not a registered relation fails.
  * RUNTIME_CASES: a (name, callable) run under watch_opens(); any data/ file it opens that is not a registered
    relation (or allowed configuration) fails.
Tests that publish use the `r12_root` fixture, so the committed data is never written.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import shutil

import pandas as pd
import pytest

from backend.dealdesk.data import lineage, schema as S, store

V5 = pathlib.Path(__file__).resolve().parents[2]


# ------------------------------------------------------------------ cases other sessions extend

def _twin_a_bureau_figures():
    rows = store.dd_read("other_bank_facility", proposal_id="R12-TWA")
    return {"matrix": [lineage.figure("other_bank_facility", r, "bureau_outstanding_mn", "SAR million") for r in rows]}


def _twin_b_project_figures():
    rows = store.dd_read("dd_project", proposal_id="R12-TWB")
    return {"projects": [{"name": r["project_name"], "wd": lineage.figure("dd_project", r, "work_done_pct", "%")} for r in rows]}


def _b_review_figures():
    """B: the source figures behind the review of both twins (financials detail, bureau, other banks, prior conditions, insider links)."""
    from backend.dealdesk.review2 import workspace
    return {pid: workspace.review(pid, publish=False)["figures"] for pid in ("R12-TWA", "R12-TWB")}


def _group_response(pid):  # R12-C: the whole /group/all response for a deal (every figure in it must trace)
    from fastapi.testclient import TestClient
    from backend.dealdesk.api import PREFIX, app
    from backend.dealdesk.group import service
    service.clear()
    return TestClient(app).get(f"{PREFIX}/proposals/{pid}/group/all").json()


import contextlib  # noqa: E402


@contextlib.contextmanager
def _d_scratch():
    """D's cases seed the R12 ladder into dd_stress_scenario on first use: run them on a scratch copy of the R12
    folders so the committed data (and the build --check) never change."""
    import tempfile
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="r12-d-"))
    for folder in S.MANIFEST:
        dst = tmp / folder
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(V5 / folder, dst)
    old = {k: os.environ.get(k) for k in ("DEALDESK_R12_ROOT", "DEALDESK_R12_HISTORY")}
    os.environ["DEALDESK_R12_ROOT"] = str(tmp)
    os.environ["DEALDESK_R12_HISTORY"] = str(tmp / "_history")
    store._CACHE.clear()
    try:
        yield tmp
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        store._CACHE.clear()


def _d_ladder_figures():
    """D: every sensitivity and deal fact the Stress Lab ladder used on twin B, traced to its Data Domains row."""
    from backend.dealdesk.data import deals
    from backend.dealdesk.stress2 import chain, ladder
    with _d_scratch():
        out = ladder.run(deals.get("R12-TWB"), None, reverse=False, publish=False)
        figs = {"rows": [{"id": r["id"], "figures": chain.traced_figures(r)} for r in out["rows"] if r["applicable"]]}
        # resolve while the scratch root (with the seeded ladder) is in force
        bad = lineage.untraced(figs)
    assert not bad, bad
    # outside the scratch root the rows D seeds at first use (ladder-only sensitivities) do not exist yet: keep the
    # figures whose rows are in the committed data (oil, GDP, fixed-cost, customer and project shares from E's seed)
    for r in figs["rows"]:
        r["figures"] = [f for f in r["figures"] if lineage.resolves(f["source"])[0]]
    assert any(r["figures"] for r in figs["rows"])
    return figs


def _d_monitoring_plan_figures():
    """D: the monitoring plans' review dates and trigger thresholds come from dd_monitoring_plan / dd_condition rows."""
    rows = store.dd_read("dd_condition", source="stress") or store.dd_read("dd_condition")
    return {"conditions": [lineage.figure("dd_condition", r, "trigger_threshold") for r in rows if r.get("trigger_threshold") is not None][:20]}


def _g_policy_library_figures():
    """R12 G: the policy library's figures come from dd_policy (clauses per policy version)."""
    return {"policies": [lineage.figure("dd_policy", r, "clauses_n", "count") for r in store.dd_read("dd_policy")]}


def _book_facility_figures():
    """I: a book facility's drift waterfall and twin A's (every step traced to the row it moves)."""
    from backend.dealdesk.book import core
    fid = core.listing("going_bad", limit=1)["rows"][0]["facility_id"]
    return {"book": core.facility(fid)["waterfall"], "twin_a": core.facility("R12-TWA:L0")["waterfall"]}


def _papers_figures(pid: str):
    from backend.dealdesk import committee_paper
    return committee_paper.lineage_figures(pid)


def _noor_construction_line():
    """N1: the demo path's Construction line, its Why? and its three options (every figure traced)."""
    from datetime import date
    from backend.agents_v5.brief import answers, sources
    items, _ = sources.collect({"persona": "cro", "today": date(2026, 10, 19)}, only=("sector_appetite",))
    line = next(i.to_dict() for i in items if i.id == "appetite:Construction")
    return {"line": line["numbers"], "why": answers.why(line)["numbers"],
            "options": [o["numbers"] for o in answers.options(line)["options"]]}


LINEAGE_CASES: list[tuple[str, object]] = [
    ("F: twin A paper figures", lambda: _papers_figures("R12-TWA")),
    ("F: twin B paper figures", lambda: _papers_figures("R12-TWB")),
    ("E: twin A other-bank matrix", _twin_a_bureau_figures),
    ("E: twin B financed projects", _twin_b_project_figures),
    ("B: review figures, both twins", _b_review_figures),
    ("C: twin A group, cap, owners, conduct, bureau", lambda: _group_response("R12-TWA")),  # R12-C
    ("C: twin B group cap increase", lambda: _group_response("R12-TWB")),  # R12-C
    ("C: book deal DD-02 group and conduct", lambda: _group_response("DD-02")),  # R12-C
    ("D: stress ladder sensitivities and deal facts (twin B)", _d_ladder_figures),
    ("D: monitoring trigger thresholds", _d_monitoring_plan_figures),
    ("G: policy library", _g_policy_library_figures),
    ("I: Book RAROC drift waterfall", _book_facility_figures),
    ("N1: Noor construction line, Why and options", _noor_construction_line),
    ("R14 i: DD-06 group contagion on the deal (D12)", lambda: __import__("backend.dealdesk.intel2.contagion", fromlist=["x"]).contagion("DD-06")),
    ("R14 i: twin A revenue truth check (D10)", lambda: __import__("backend.dealdesk.intel2.revenue", fromlist=["x"]).revenue("R12-TWA")),
]

#: R12 modules scanned for data-file literals (add yours; paths that do not exist yet are skipped)
SCOPED_SOURCES = [
    "backend/dealdesk/data", "backend/dealdesk/products", "backend/dealdesk/review2", "backend/dealdesk/group",
    "backend/dealdesk/stress2", "backend/dealdesk/monitoring", "backend/dealdesk/book", "backend/ews_link",
    "backend/dealdesk/workflow.py", "backend/dealdesk/registry_lookup.py", "backend/dealdesk/documents.py",
    "backend/dealdesk/committee_paper.py", "backend/dealdesk/policy_library.py", "backend/dealdesk/calibration",
    "backend/dealdesk/house_style/bankform", "backend/dealdesk/house_style/papers_api.py",
    "backend/agents_v5/brief",
    "backend/dealdesk/fin_quality",  # R13 Q
    "backend/dealdesk/stressproof",  # R14 F
    "backend/dealdesk/intel2",  # R14 i
    "backend/regulatory/issues",  # R14 r: regulatory issue views
    "backend/dealdesk/rm_request",  # R16 b: business request
    "backend/dealdesk/intake",  # R16 i: customer file (document intake)
]
#: files inside SCOPED_SOURCES that legitimately read a non-relation (the one-time migration of pipeline.json)
STATIC_EXEMPT = {("backend/dealdesk/data/build.py", "pipeline.json"), ("backend/dealdesk/data/build.py", "proposals.json"),
                 ("backend/dealdesk/data/build.py", "stress_scenarios.json"),
                 # R12 T: the calibration's own exported coefficients (N3), and the two public macro series it regresses on
                 # (not yet a registered relation: docs/STATUS_R12_TRY.md gap 2)
                 ("backend/dealdesk/calibration/sensitivity.py", "calibrated_v1.json"),
                 ("backend/dealdesk/calibration/sensitivity.py", "brent_monthly_eia.csv"),
                 ("backend/dealdesk/calibration/sensitivity.py", "mev_annual.csv"),
                 # N1: the assistant's name and voice are bank configuration, not data (PLAN_R12 §0 exception), kept
                 # under var/noor; the demo walk writes its timing record next to its screenshots.
                 ("backend/agents_v5/brief/service.py", "settings.json"),
                 # R13 H (J1): the user's own voice preference (on/off, language) sits beside the bank's voice settings.
                 ("backend/agents_v5/brief/service.py", "user_voice.json"),
                 # R14 n (K9): the reader's last brief visit (per source, the data period seen), so "New" marks only a
                 # source refreshed since then: the user's own state beside user_voice.json, not bank data.
                 ("backend/agents_v5/brief/service.py", "brief_visits.json"),
                 ("backend/agents_v5/brief/demo_walk.py", "demo_timings.json"),
                 # R16 b: the customer's uploaded documents (the demo packs' printed fields, until intake's extraction is read) are
                 # documents, not bank data; the bank's own data is read through registered relations only
                 ("backend/dealdesk/rm_request/inputs.py", "manifest.json"), ("backend/dealdesk/rm_request/inputs.py", "customers.json")}


def _pipeline_set():
    from backend.dealdesk import pipeline
    pipeline.seeded_set.cache_clear()
    return pipeline.seeded_set()


def _deals_get():
    from backend.dealdesk.data import deals
    return [deals.get(p) for p in ("R12-TWA", "R12-TWB", "R12-SYN", "R12-ESC", "R12-SME1", "PL-01")]


def _b_document_checklists():
    """B: the document checklist of every R12 demo deal and a PL deal reads only registered relations and the rule book."""
    from backend.dealdesk import documents
    return [documents.checklist(p) for p in ("R12-TWA", "R12-TWB", "R12-SYN", "R12-ESC", "R12-SME1", "PL-01")]


def _d_ews_panel():
    """D: the EWS link reads dd_monitoring_plan, the EWS book and borrower ratios only through registered relations.
    (A ladder run is not a runtime case here: the engine it calls opens the PD model's scorecard specs, which are
    outside D; D's own code is covered by the static scan and tests/v5/dealdesk/test_r12_stress.py::test_no_side_door.)"""
    from backend.ews_link import adapter
    with _d_scratch():
        adapter.panel("XE-TWA-01")
        adapter.tier_high_movers()


def _g_parameters_and_library():
    from backend.dealdesk import policy_library as PL
    return PL.parameter_rows(), PL.listing(), PL.provenance_relation_rows()


def _book_all():
    """I: the Book read end to end from cold (frame, counts, every filter, a facility, the drift and feedback views)."""
    from backend.dealdesk.book import core, drift, feedback, promises, sources
    sources.clear_cache(); drift.universe.cache_clear(); drift.frame.cache_clear(); core.refresh()
    promises._deposits_12m.cache_clear(); promises._conduct_12m.cache_clear(); promises._conduct_raw.cache_clear(); core.covenants.cache_clear()
    out = [core.listing(f, limit=2) for f in core.FILTERS]
    return out + [core.counts(), core.facility("R12-TWA:L0"), drift.summary(), feedback.hurdle_overrides(), feedback.realisation()]


def _calibrated_sensitivity():
    from backend.dealdesk.calibration import publish
    return [publish.latest(s, d) for s in ("Construction", "Wholesale Trade", "No Such Sector") for d in ("oil", "gdp_nonoil")]


def _noor_briefs():
    from datetime import date
    from backend.agents_v5.brief import service
    return [service.brief(persona=p, today=date(2026, 10, 19), hour=8) for p in ("cro", "reviewer", "rm", "analyst")]


RUNTIME_CASES: list[tuple[str, object]] = [
    ("F: paper figures twin A", lambda: _papers_figures("R12-TWA")),
    ("F: paper figures twin B", lambda: _papers_figures("R12-TWB")),
    ("E: pipeline set via dd_pipeline", _pipeline_set),
    ("E: deal registry", _deals_get),
    ("B: document checklists", _b_document_checklists),
    ("C: group bundle, twin B", lambda: __import__("backend.dealdesk.group.service", fromlist=["x"]).bundle("R12-TWB", refresh=True)),  # R12-C
    ("C: group bundle, DD-02", lambda: __import__("backend.dealdesk.group.service", fromlist=["x"]).bundle("DD-02", refresh=True)),  # R12-C
    ("D: EWS link panel and tier-High movers", _d_ews_panel),
    ("G: parameters, provenance and the policy library", _g_parameters_and_library),
    ("I: the Book", _book_all),
    ("T: the engine's read of the calibrated sensitivities", _calibrated_sensitivity),
    ("N1: Noor briefs for every persona", _noor_briefs),
]


# Session P (products): every figure of the four product sections, and the reads behind them
def _p(fn_name: str, pid: str | None = None):
    def run():
        from backend.dealdesk.products import escrow, lineage as plin, project, sme, syndication
        mods = {"project": project.analyse, "escrow": escrow.analyse, "syndication": syndication.analyse}
        out = [sme.decide(a) for a in sme.applications()] if fn_name == "sme" else mods[fn_name](pid)
        return {"figures": plin.as_figures(out)}
    return run


LINEAGE_CASES += [("P: twin B project section", _p("project", "R12-TWB")), ("P: escrow section", _p("escrow", "R12-ESC")),
                  ("P: syndication on our share", _p("syndication", "R12-SYN")), ("P: SME fast-track lane", _p("sme"))]
RUNTIME_CASES += [("Q: financial quality, twin A", lambda: __import__("backend.dealdesk.fin_quality", fromlist=["x"]).assess("R12-TWA")),  # R13 Q
                  ("Q: financial quality, twin B", lambda: __import__("backend.dealdesk.fin_quality", fromlist=["x"]).assess("R12-TWB")),
                  ("Q: financial quality, a Book renewal", lambda: __import__("backend.dealdesk.fin_quality", fromlist=["x"]).assess_book("CF000011"))]
RUNTIME_CASES += [("P: twin B project section", _p("project", "R12-TWB")), ("P: escrow section", _p("escrow", "R12-ESC")),
                  ("P: syndication on our share", _p("syndication", "R12-SYN")), ("P: SME fast-track lane", _p("sme"))]


# ------------------------------------------------------------------ fixtures

@pytest.fixture()
def r12_root(tmp_path, monkeypatch):
    """A scratch copy of the R12 folders; publish() writes there, never to the committed data."""
    for folder in S.MANIFEST:
        src = V5 / folder
        dst = tmp_path / folder
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst)
    monkeypatch.setenv("DEALDESK_R12_ROOT", str(tmp_path))
    monkeypatch.setenv("DEALDESK_R12_HISTORY", str(tmp_path / "_history"))
    store._CACHE.clear()
    yield tmp_path
    store._CACHE.clear()


def _committed_hashes() -> dict[str, str]:
    import hashlib
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for f in S.MANIFEST for p in sorted((V5 / f).glob("*"))}


# ------------------------------------------------------------------ the contract and the registry

def test_every_contract_relation_is_registered_with_its_file_and_keys():
    from backend.data_builder.registry import DOMAINS
    for rid, spec in S.RELATIONS.items():
        reg = DOMAINS[spec["domain"]]["relations"].get(rid)
        assert reg, rid
        assert reg["path"] == f"{spec['folder']}/{rid}.parquet" and reg["key_columns"] == spec["keys"] and reg["period_column"] == S.PERIOD
        assert (V5 / reg["path"]).exists(), rid


def test_borrower_360_is_live_with_the_existing_relationship_tables():
    from backend.data_builder.registry import DOMAINS
    b = DOMAINS["borrower_360"]
    assert b["status"] == "live"
    for k in ("rel_edge_quarter", "rel_group_quarter", "rel_person_role", "rel_shared_collateral", "b360_shareholder", "b360_board",
              "b360_insider_link", "b360_ownership_change", "b360_entity", "b360_edge"):
        assert k in b["relations"] and (V5 / b["relations"][k]["path"]).exists(), k


@pytest.mark.parametrize("rid", sorted(S.RELATIONS))
def test_files_match_the_contract(rid):
    df = pd.read_parquet(store.relation_path(rid))
    assert list(df.columns) == S.column_names(rid)
    assert len(df) > 0, f"{rid} has no demo rows"
    assert not df.duplicated(subset=S.RELATIONS[rid]["keys"]).any(), rid
    assert set(df[S.PERIOD]) == {S.AS_OF}
    for n, t, _, _ in S.columns(rid):
        if t in ("int", "flag"):
            assert pd.api.types.is_integer_dtype(df[n]), (rid, n)
        elif t == "float":
            assert pd.api.types.is_float_dtype(df[n]), (rid, n)
        else:
            assert all(isinstance(v, str) for v in df[n].dropna()), (rid, n)
        if t == "flag":
            assert set(df[n].dropna().unique()) <= {0, 1}, (rid, n)
        if t == "json":
            for v in df[n].dropna():
                json.loads(v)
        if t == "date":
            assert all(v == "" or re.fullmatch(r"\d{4}-\d{2}-\d{2}", v) for v in df[n].dropna()), (rid, n)
    m = store.read_manifest(S.RELATIONS[rid]["folder"])["relations"][rid]
    assert m["rows"] == len(df) and m["version"] >= 1 and m["content_sha256"] == store._content_hash(df)


def test_contract_document_is_current():
    from backend.dealdesk.data import contract
    assert (V5 / "docs" / "v5" / "R12_DATA_CONTRACT.md").read_text() == contract.build()


# ------------------------------------------------------------------ readers and publisher

def test_dd_read_filters_and_parses_json():
    rows = store.dd_read("dd_document", proposal_id="R12-TWA", status=["pending", "expired"])
    assert rows and all(r["status"] in ("pending", "expired") for r in rows)
    plan = store.dd_read("dd_monitoring_plan", proposal_id="R12-TWA")[0]
    assert isinstance(plan["named_triggers"], list) and plan["named_triggers"][0]["metric"] == "routing_multiple"
    assert store.dd_read("rel_group_quarter", columns=["group_id"], reporting_quarter="2026Q2")  # registered existing relation
    with pytest.raises(KeyError):
        store.dd_read("not_a_relation")


def test_publish_versions_and_upserts_without_touching_committed_data(r12_root):
    before = _committed_hashes()
    v0 = store.version_of("dd_review_finding")
    r = store.publish("dd_review_finding", [{"finding_id": "T-1", "proposal_id": "R12-TWA", "review_point": 4, "severity": "high",
                                             "title": "Adjusted net worth", "evidence_value": 63.0}], actor="test")
    assert r["version"] == v0 + 1
    store.publish("dd_review_finding", [{"finding_id": "T-1", "proposal_id": "R12-TWA", "review_point": 4, "severity": "medium"}], actor="test")
    rows = store.dd_read("dd_review_finding", finding_id="T-1")
    assert len(rows) == 1 and rows[0]["severity"] == "medium" and rows[0]["rel_version"] == v0 + 2
    assert store.dd_read("dd_review_finding", finding_id="E-TWA-F2"), "upsert keeps the other rows"
    m = store.read_manifest(S.DD_DIR)["relations"]["dd_review_finding"]
    assert m["version"] == v0 + 2 and m["history"][-1]["by"] == "test"
    assert (r12_root / "_history" / "dd_review_finding").exists()
    with pytest.raises(store.SchemaError):
        store.publish("dd_review_finding", [{"finding_id": "T-2", "nope": 1}])
    with pytest.raises(store.SchemaError):
        store.publish("dd_review_finding", [{"finding_id": "T-1"}], mode="append")
    with pytest.raises(KeyError):
        store.publish("dd_proposal", [{}])  # R11 relations are built by their own builder
    assert _committed_hashes() == before


def test_publish_replace_where_rewrites_one_deal(r12_root):
    store.publish("dd_swot", [{"swot_id": "C-SYN-1", "proposal_id": "R12-SYN", "quadrant": "S", "text": "x"}], mode="replace_where",
                  where={"proposal_id": "R12-SYN"}, actor="C")
    rows = store.dd_read("dd_swot", proposal_id="R12-SYN")
    assert [r["swot_id"] for r in rows] == ["C-SYN-1"]


# ------------------------------------------------------------------ referential integrity of the demo data

def test_every_deal_reference_resolves():
    deals = {r["proposal_id"] for r in store.dd_read("dd_deal", columns=["proposal_id"])}
    assert {"R12-TWA", "R12-TWB", "R12-SYN", "R12-ESC", "R12-SME1", "R12-SME2", "R12-SME3"} <= deals
    assert len([d for d in deals if d.startswith("PL-")]) == 27 and len([d for d in deals if re.fullmatch(r"DD-\d\d", d)]) == 15
    for rid in S.RELATIONS:
        df = store.dd_frame(rid)
        if "proposal_id" in df.columns and rid not in ("dd_stress_scenario",):
            ids = set(df["proposal_id"].dropna()) - {""}
            assert ids <= deals, (rid, ids - deals)


def test_entities_limits_projects_and_rules_resolve():
    ents = {r["entity_id"] for r in store.dd_read("b360_entity", columns=["entity_id"])}
    persons = {r["holder_id"] for r in store.dd_read("b360_shareholder", columns=["holder_id"])}
    for rid in ("bureau_entity_report", "bureau_cbrbr", "other_bank_facility", "dd_group_exposure"):
        bad = set(store.dd_frame(rid)["entity_id"]) - ents - persons
        assert not bad, (rid, bad)
    limits = {(r["proposal_id"], r["limit_id"]) for r in store.dd_read("dd_facility_limit", columns=["proposal_id", "limit_id"])}
    for rid in ("dd_security", "dd_tnc", "dd_condition"):
        for r in store.dd_read(rid, columns=["proposal_id", "limit_id"]):
            assert r["limit_id"] == "ALL" or (r["proposal_id"], r["limit_id"]) in limits, (rid, r)
    projects = {r["project_id"] for r in store.dd_read("dd_project", columns=["project_id"])}
    assert set(store.dd_frame("dd_project_cashflow")["project_id"]) <= projects
    rules = {r["rule_id"] for r in store.dd_read("dd_document_rule", columns=["rule_id"])}
    assert set(store.dd_frame("dd_document")["rule_id"]) <= rules


def test_twins_carry_every_anatomy_fact():
    """The facts PROPOSAL_ANATOMY §2 needs, for both twins."""
    for pid in ("R12-TWA", "R12-TWB"):
        for rel in ("dd_facility_limit", "dd_security", "dd_tnc", "dd_group_exposure", "dd_reference", "dd_business_profile",
                    "dd_account_conduct", "bureau_entity_report", "bureau_cbrbr", "other_bank_facility", "dd_financials_detail",
                    "dd_document", "dd_workflow_event", "dd_condition"):
            assert store.dd_read(rel, proposal_id=pid), (pid, rel)
    a = store.dd_frame("dd_financials_detail", proposal_id="R12-TWA")
    assert (a["opinion"] == "qualified").any() and (a["period_kind"] == "interim").any() and a["due_from_related_mn"].max() > 0
    assert store.dd_read("b360_insider_link", entity_id="XE-TWA-04")
    assert store.dd_read("dd_promise", proposal_id="R12-TWA")[0]["delivered_pct"] == pytest.approx(33.0, abs=0.5)
    assert store.dd_frame("dd_account_conduct", proposal_id="R12-TWA")["returned_cheques_n"].sum() > 0
    ob = store.dd_frame("other_bank_facility", proposal_id="R12-TWA")
    assert (ob["difference_mn"].abs() > 10).any() and (ob["clarified_flag"] == 0).any()
    pj = store.dd_frame("dd_project", proposal_id="R12-TWB")
    assert (pj["eot_days"] > 0).any() and (pj["payment_delay_days"] > 90).any() and pj["work_done_pct"].notna().all()
    cf = store.dd_frame("dd_project_cashflow", project_id="PJ-TWB-4")
    assert cf["cumulative_mn"].min() < 0
    d = store.dd_read("dd_deal", proposal_id="R12-TWB")[0]
    assert d["group_cap_proposed_mn"] > d["group_cap_existing_mn"]
    docs = store.dd_frame("dd_document", proposal_id="R12-TWA")
    assert (docs["status"] != "received").sum() >= 3


def test_demo_deals_price_through_the_engine():
    from backend.dealdesk import engine
    from backend.dealdesk.data import deals
    for pid in deals.demo_ids():
        m = engine.analyse(deals.get(pid))["metrics"]
        assert m["lifetime_raroc"] == m["lifetime_raroc"], pid


# fictional names only (N7): none of these real institutions may appear in any demo row
REAL_NAMES = ("Emirates NBD", "Mashreq", "ADCB", "Abu Dhabi Commercial", "First Abu Dhabi", "Dubai Islamic", "Al Rajhi", "Riyad Bank",
              "Saudi National Bank", "SABB", "Banque Saudi Fransi", "Arab National Bank", "Alinma", "Bank Albilad", "Bank AlJazira",
              "Emaar", "Aldar", "Nakheel", "Damac", "Arabtec", "Saudi Binladin", "SABIC", "Aramco", "Arwa", "Kuwait Finance House",
              "National Bank of Kuwait", "Commercial Bank of Dubai", "RAKBANK", "Sharjah Islamic", "Ajman Bank")


def test_demo_rows_use_fictional_names_only():
    """Every row Session E writes for the R12 demo deals (the R11 DD and PL sets are checked by their own suites)."""
    for rid, spec in S.RELATIONS.items():
        df = store.dd_frame(rid)
        if "proposal_id" in df.columns:
            df = df[df["proposal_id"].fillna("").str.startswith("R12-") | (df["proposal_id"].fillna("") == "")]
        text = " ".join(df[c].dropna().astype(str).str.cat(sep=" ") for c in df.columns if df[c].dtype == "string" or df[c].dtype == object)
        for n in REAL_NAMES:
            assert not re.search(rf"\b{re.escape(n)}\b", text, flags=re.I), (rid, n)


# ------------------------------------------------------------------ lineage

@pytest.mark.parametrize("name,fn", LINEAGE_CASES, ids=[c[0] for c in LINEAGE_CASES])
def test_lineage(name, fn):
    out = fn()
    figs = list(lineage.figures(out))
    assert figs, f"{name}: no figures found"
    assert lineage.untraced(out) == []


def test_lineage_catches_an_untraced_figure():
    assert lineage.untraced({"a": {"value": 1.0}}) == [("$.a", "no source")]
    bad = {"a": {"value": 1.0, "source": {"domain": "deal_desk_products", "relation": "dd_project", "key": {"project_id": "NOPE"}}}}
    assert lineage.untraced(bad)[0][1].startswith("no row")
    wrong = {"a": {"value": 1.0, "source": {"domain": "deal_desk", "relation": "dd_project", "key": {}}}}
    assert "not registered" in lineage.untraced(wrong)[0][1]


@pytest.mark.parametrize("rid", sorted(S.RELATIONS))
def test_every_row_traces_back(rid):
    rows = store.dd_read(rid)[:5]
    for r in rows:
        ok, why = lineage.resolves(store.trace(rid, r))
        assert ok, (rid, why)


# ------------------------------------------------------------------ no side door

def test_no_side_door_static():
    paths = [V5 / p for p in SCOPED_SOURCES if (V5 / p).exists()]
    bad = [(f, lit) for f, lit in lineage.static_side_doors(paths) if (f, pathlib.Path(lit).name) not in STATIC_EXEMPT]
    assert bad == []


@pytest.mark.parametrize("name,fn", RUNTIME_CASES, ids=[c[0] for c in RUNTIME_CASES])
def test_no_side_door_runtime(name, fn):
    with lineage.watch_opens() as opened:
        fn()
    assert lineage.side_doors(opened) == [], name


def test_side_door_detector_works():
    with lineage.watch_opens() as opened:
        (V5 / "data" / "dealdesk" / "pipeline" / "pipeline.json").read_text()
    assert lineage.side_doors(opened) == ["data/dealdesk/pipeline/pipeline.json"]


# ------------------------------------------------------------------ product templates (E)

def test_product_templates_cover_every_demo_deal():
    from backend.dealdesk.products import templates as T
    from backend.dealdesk.data import deals
    rules = {r["rule_id"] for r in store.dd_read("dd_document_rule", columns=["rule_id"])}
    for prod, t in T.TEMPLATES.items():
        assert set(t["document_rules"]) <= rules, prod
        assert set(t["sections"]) <= set(T.SECTION_LABEL), prod
        assert set(t["relations"]) <= set(S.RELATIONS) | {"dd_obligor_financials"}, prod
    want = {"R12-TWA": "corporate", "R12-TWB": "contracting", "R12-SYN": "syndicated", "R12-ESC": "escrow", "R12-SME1": "sme"}
    for pid, prod in want.items():
        assert T.for_deal(pid)["product"] == prod
    assert T.applies("R12-TWB", "section", "financed_projects") and not T.applies("R12-TWA", "section", "financed_projects")
    assert T.for_deal("R12-SME2")["lane"] == "fast_track" and T.doa_for_sme(4.5) == "SME Credit Manager"
    assert [s for s, _ in T.ANATOMY] == T.for_deal("R12-TWB")["sections"][:20]   # contracting paper = full anatomy in order
    assert T.for_deal("DD-01")["product"] in T.TEMPLATES and deals.product_of("PL-01") in T.TEMPLATES


def test_the_r12_data_build_is_deterministic():
    import subprocess
    import sys
    r = subprocess.run([sys.executable, "-m", "backend.dealdesk.data.build", "--check"], cwd=V5, capture_output=True, text=True,
                       env={k: v for k, v in os.environ.items() if not k.startswith("DEALDESK_R12")})
    assert r.returncode == 0 and "PASS" in r.stdout, r.stdout + r.stderr


def test_bridge_monitoring_plan_supersedes_and_workflow_appends(r12_root):
    from backend.dealdesk.data import bridge
    bridge.publish_monitoring_plan({"proposal_id": "R12-TWA", "obligor_id": "XE-TWA-01", "tier": "High", "stress_verdict": "approve_enhanced",
                                    "drivers": ["largest_customer_share"], "reason": "fails under moderate", "set_by": "test"})
    plans = store.dd_read("dd_monitoring_plan", proposal_id="R12-TWA")
    act = [p for p in plans if p["status"] == "active"]
    assert len(act) == 1 and act[0]["tier"] == "High" and act[0]["previous_tier"] == "Medium"
    assert any(p["status"] == "superseded" for p in plans)
    with pytest.raises(ValueError):
        bridge.publish_monitoring_plan({"proposal_id": "R12-TWA", "tier": "Standard"})
    n = len(store.dd_read("dd_workflow_event", proposal_id="R12-TWA"))
    bridge.publish_workflow("R12-TWA", "queries", "in_review", "Dana Al-Khatib", "credit_reviewer", "Replies received")
    assert len(store.dd_read("dd_workflow_event", proposal_id="R12-TWA")) == n + 1
    rows = bridge.r11_condition_rows([{"id": "DD-01:COVENANT:dscr", "deal_id": "DD-01", "kind": "covenant", "what": "DSCR at least 1.20x",
                                       "due_date": "2026-12-31", "due_text": "annual (FY accounts)", "status": "open", "inputs": {"v": "metrics.dscr_post"}}])
    store.publish("dd_condition", rows, mode="replace_where", where={"source": "r11"})
    assert store.dd_read("dd_condition", condition_id="DD-01:COVENANT:dscr")[0]["kind"] == "covenant"
