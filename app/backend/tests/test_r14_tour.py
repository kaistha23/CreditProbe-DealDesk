"""PLAN_R14 session t (R13_FEEDBACK K36, K36a): Noor's introduction tour — the deterministic script writer.

  .venv/bin/python -m pytest backend/tests/test_r14_tour.py -q
"""
from __future__ import annotations

import re

import pytest

from backend.agents_v5.tour import facts as F
from backend.agents_v5.tour import script as S
from backend.agents_v5.tour.facts import Fact

MODULES = {"cockpit", "ews", "b360", "whatif", "lenses", "dealdesk", "scorecard", "brf", "policy", "playbook",
           "governance", "data", "workspace"}
ACTIONS = {"home", "diagram", "brief", "click", "ask", "open_module", "open_deal", "panel"}
VENDORS = re.compile(r"temenos|finastra|finacle|infosys|oracle|flexcube|misys|murex|ncino|moody|fitch|s&p|fico|"
                     r"experian|equifax|sas\b|simah|nice actimize|t24|sap\b", re.I)
REAL_NAMES = re.compile(r"\bSIB\b|aldar|kharafi", re.I)


@pytest.fixture(scope="module")
def live() -> dict[str, Fact]:
    return F.collect()


@pytest.fixture(scope="module")
def tours(live) -> dict[str, dict]:
    return {lang: S.script(lang=lang, persona="cro", facts=live) for lang in ("en", "ar")}


def test_templates_hold_no_digits():
    """Claims discipline (K36 (4)): a figure can only enter a caption through a fact."""
    for spec in S.STEPS:
        for c in spec.clauses:
            for text in (c.en, c.ar):
                assert not re.search(r"\d", S._SLOT.sub("", text).replace("360", "")), (spec.key, text)


def test_every_step_is_complete(tours):
    for lang, t in tours.items():
        assert t["n_steps"] == len(S.STEPS) >= 16
        for s in t["steps"]:
            assert s["route"].startswith("/") and s["selectors"] and s["action"]["type"] in ACTIONS, s["key"]
            assert s["caption_en"] and s["caption_ar"] and s["voice_en"] and s["voice_ar"], s["key"]
            assert s["title_en"] and s["title_ar"] and s["duration_ms"] >= S.MIN_MS
            assert re.search(r"[؀-ۿ]", s["caption_ar"]), s["key"]
        assert t["dir"] == ("rtl" if lang == "ar" else "ltr")


def test_covers_every_module_and_the_story(tours):
    """K36a: every function, and the sales story (intelligence layer above LOS, CBS, rating, collections, EWS)."""
    keys = [s["key"] for s in tours["en"]["steps"]]
    assert {s["module"] for s in tours["en"]["steps"]} == MODULES
    for k in ("intro", "layers", "brief", "why", "ask", "ews", "b360", "whatif", "lenses", "deal_check",
              "deal_review", "deal_structure", "deal_proposal", "book", "scorecard", "brf", "policy", "playbook",
              "governance", "data", "workspace", "close"):
        assert k in keys
    assert keys[0] == "intro" and keys[1] == "layers" and keys[-1] == "close"
    en = " ".join(s["caption_en"] for s in tours["en"]["steps"])
    for w in ("loan system", "core banking", "rating", "collections", "early warning", "intelligence"):
        assert w in en.lower(), w
    assert "not another system of record" in en


def test_claims_backed_by_facts(tours, live):
    """Every number in every caption appears in a fact the step used; every fact names its source."""
    for t in tours.values():
        assert t["claims"]["unbacked"] == []
        for s in t["steps"]:
            assert s["unbacked"] == [], (s["key"], s["unbacked"])
        for k, f in t["facts"].items():
            assert f["domain"] and f["relation"] and f["method"], k


def test_data_facts_are_registered_relations(live):
    from backend.data_builder.registry import DOMAINS
    non_relation = {("data_domains", "registry"), ("lenses", "catalogue"), ("playbook", "regulations"),
                    ("scorecard", "registry"), ("what_if", "whatif_corporate")}
    for k, f in live.items():
        if (f.domain, f.relation) in non_relation:
            continue
        assert f.relation in (DOMAINS.get(f.domain) or {}).get("relations", {}), (k, f.domain, f.relation)


def test_live_numbers_are_read(live):
    for k in ("domains", "relations", "book_borrowers", "book_ead", "ews_names", "deal_findings", "deals_pending"):
        assert k in live, k
    assert live["deal_findings"].value > 0 and live["book_borrowers"].value > 0


def test_deterministic(live):
    a = S.script(lang="en", facts=live, brief=None)
    b = S.script(lang="en", facts=live, brief=None)
    assert a == b


def test_absent_fact_drops_its_clause(live):
    fs = {k: v for k, v in live.items() if not k.startswith("bt_")}
    t = S.script(lang="en", facts=fs, brief={})
    wi = next(s for s in t["steps"] if s["key"] == "whatif")
    assert "back-test" not in wi["caption"]
    assert any(d["step"] == "whatif" and "bt_mean" in d["missing"] for d in t["claims"]["dropped"])
    # without the brief, the brief step still speaks (no line, no figure)
    br = next(s for s in t["steps"] if s["key"] == "brief")
    assert br["caption"] and not re.search(r"\d", br["caption"])


def test_measured_backtest_is_quoted_when_present(live):
    fs = dict(live)
    fs["bt_quarters"] = Fact("bt_quarters", 20, "20", "20", "what_if", "whatif_backtest", "quarters")
    fs["bt_mean"] = Fact("bt_mean", 1.23, "1.23%", "1.23%", "what_if", "whatif_backtest", "mean abs error")
    fs["bt_worst"] = Fact("bt_worst", 4.5, "4.5%", "4.5%", "what_if", "whatif_backtest", "worst abs error")
    for lang in ("en", "ar"):
        wi = next(s for s in S.script(lang=lang, facts=fs, brief={})["steps"] if s["key"] == "whatif")
        assert "1.23%" in wi["caption"] and "4.5%" in wi["caption"] and wi["unbacked"] == []
    assert "99.9" not in str(S.script(lang="en", facts=fs, brief={}))


def test_brief_lines_in_both_languages():
    brief = {"persona": "cro", "date": "2026-10-19", "headline": "Five things across the bank since yesterday, 1 critical.",
             "items": [
                 {"id": "crm:X", "kind": "breach", "severity": "critical", "source_label": "Regulatory checks",
                  "title": "Stage 3 provision below the floor: 219 exposures, SAR 1.73bn EAD, SAR 878.5m provision shortfall",
                  "numbers": [{"label": "Exposures", "value": 219, "unit": "", "display": "219"},
                              {"label": "EAD", "value": 1728.55, "unit": "SAR mn", "display": "SAR 1.73bn"},
                              {"label": "Shortfall", "value": 878.5, "unit": "SAR mn", "display": "SAR 878.5m"}],
                  "trace": [{"domain": "regulatory", "relation": "crm_breach", "keys": {"check_id": "X"}, "period": "2026Q2"}],
                  "entity": {"article": "Rule 9.23"}},
                 {"id": "dd:q", "kind": "deal_queue", "severity": "high", "source_label": "Deal Desk",
                  "title": "32 deals waiting for credit review, SAR 3.53bn asked",
                  "numbers": [{"label": "Deals", "value": 32, "unit": "", "display": "32"}],
                  "trace": [{"domain": "deal_desk", "relation": "dd_deal", "keys": {}, "period": "2026Q2"}]}]}
    fs = S.brief_facts(brief)
    assert fs["brief_line1"].relation == "crm_breach" and "219" in fs["brief_line1"].ar
    assert "878.5 مليون ريال" in fs["brief_line1"].ar and "1.73 مليار ريال" in fs["brief_line1"].ar
    assert fs["brief_rule"].en == "Rule 9.23"
    t = S.script(lang="ar", facts=fs, brief={})
    br = next(s for s in t["steps"] if s["key"] == "brief")
    assert "219" in br["caption_ar"] and br["unbacked"] == []
    assert "Stage 3 provision below the floor" in br["caption_en"]


@pytest.mark.parametrize("kind,label,unit", [("ecl_anomaly", "Issues needing a re-run", ""), ("migrations", "Exposures", ""),
                                             ("letters", "Letters", ""), ("watch_due", "Triggers due", "")])
def test_line_ar_kinds(kind, label, unit):
    s = S.line_ar({"kind": kind, "numbers": [{"label": label, "value": 7, "unit": unit, "display": "7"}]})
    assert "7" in s and re.search(r"[؀-ۿ]", s)


def test_no_vendor_or_real_names(tours):
    for t in tours.values():
        text = " ".join(s["caption_en"] + " " + s["caption_ar"] + " " + s["title_en"] for s in t["steps"])
        assert not VENDORS.search(text), VENDORS.search(text)
        assert not REAL_NAMES.search(text)


def test_length_is_a_short_tour(tours):
    """About two and a half minutes (K36: 1–2 minutes, plan ~2.5): the estimate stays under four."""
    for t in tours.values():
        assert 90_000 <= t["duration_ms"] <= 240_000, t["duration_ms"]


def test_voice_is_male_and_calm(tours):
    v = tours["en"]["voice"]
    assert v["gender"] == "male" and v["en"][:2] == ["Evan", "Nathan"] and v["ar"] == ["Maged"]
    assert v["rate"] == 0.92 and v["pitch"] == 0.9


def test_new_deal_desk_steps_have_tour_selectors_first():
    """Other sessions build the new Deal Desk steps: their data-tour hooks come first, existing ids after."""
    by = {s.key: s for s in S.STEPS}
    assert by["deal_check"].selectors[0] == '[data-tour="dd-proposal-check"]'
    assert by["deal_structure"].selectors[0] == '[data-tour="dd-stress"]'
    assert by["deal_proposal"].selectors[0] == '[data-tour="dd-prepare-proposal"]'
    assert by["book"].selectors[0] == '[data-tour="dd-monitoring"]'


def test_api():
    from fastapi.testclient import TestClient
    from backend.dealdesk_thread.api import app
    c = TestClient(app)
    r = c.get("/api/v1/tour/script", params={"lang": "ar"})
    assert r.status_code == 200 and r.json()["lang"] == "ar" and r.json()["claims"]["unbacked"] == []
    f = c.get("/api/v1/tour/facts").json()
    assert f["n"] >= 10 and all(v["relation"] for v in f["facts"].values())
    assert c.get("/api/v1/tour/health").json()["status"] == "ok"


def test_spoken_form_says_the_same_numbers(tours):
    """The voice line is the caption in words a voice reads well (riyals, quarters, abbreviations), same figures."""
    assert S.spoken_en("SAR 1.73bn EAD in 2026Q2, SAR 878.5m short; Art. 9.23") == \
        "1.73 billion riyals exposure at default in the second quarter of 2026, 878.5 million riyals short; Article 9.23"
    assert S.spoken_ar("في 2026Q2") == "في الربع الثاني من 2026"
    for t in tours.values():
        for s in t["steps"]:
            assert sorted(S.numbers_in(s["voice_en"])) == sorted(S.numbers_in(S.spoken_en(s["caption_en"])))
            assert "SAR " not in s["voice_en"] and not re.search(r"\d{4}Q\d", s["voice_en"] + s["voice_ar"])


def test_backtest_reads_session_m_relation(monkeypatch):
    """m's `whatif_backtest` (abs_error_pct per quarter step, version): mean and worst of the latest version."""
    from backend.agents_v5.brief import readers
    from backend.agents_v5.brief.readers import Read
    rows = [{"from_quarter": f"Q{i}", "version": 1, "abs_error_pct": e} for i, e in enumerate([10.0, 5.0, 19.21, 6.0])]
    rows += [{"from_quarter": "Q0", "version": 0, "abs_error_pct": 99.0}]
    monkeypatch.setattr(readers, "domain_of", lambda rel: "deal_desk" if rel == "whatif_backtest" else None)
    monkeypatch.setattr(F, "read", lambda d, r, **k: Read(d, r, [dict(x) for x in rows]))
    bt = F.backtest()
    assert bt["bt_quarters"].value == 4 and bt["bt_worst"].en == "19.21%" and bt["bt_mean"].en == "10.05%"
    fs = {**F.collect(), **bt}
    wi = next(s for s in S.script(lang="en", facts=fs, brief={})["steps"] if s["key"] == "whatif")
    assert "Back-tested on 4 quarter steps" in wi["caption"] and "10.05%" in wi["caption"] and wi["unbacked"] == []


def test_proposal_check_opens_the_checked_deal(monkeypatch, live):
    """p's `dd_proposal_quality`: the step opens p's demo deal and says its defects; absent → twin A, clause dropped."""
    from backend.agents_v5.brief.readers import Read

    def fake(d, r, **k):
        if r == "dd_proposal_quality":
            return Read(d, r, [{"proposal_id": "R14-DEMO", "run_id": "PQ-R14-DEMO-aa", "n": 12, "crit": 4},
                               {"proposal_id": "R14-DEMO", "run_id": "PQ-R14-DEMO-bb", "n": 1, "crit": 0}])
        if r == "dd_deal":
            return Read(d, r, [{"obligor_name": "Fictional Demo Trading"}])
        return Read(d, r, [], status="not_registered")
    monkeypatch.setattr(F, "read", fake)
    pq = F.proposal_check()
    assert pq["pq_deal"].value == "R14-DEMO" and pq["pq_defects"].value == 12 and pq["pq_critical"].value == 4
    st = next(s for s in S.script(lang="en", facts={**live, **pq}, brief={})["steps"] if s["key"] == "deal_check")
    assert st["route"] == "/deal-desk/R14-DEMO" and st["action"]["open"][0] == 'a[href="/deal-desk/R14-DEMO"]'
    assert "12 defects, 4 of them critical" in st["caption"] and st["unbacked"] == []
    # R14 x: on the merged branch the live facts carry p's dd_proposal_quality; "absent" means without the pq_* facts.
    no_pq = {k: v for k, v in live.items() if not k.startswith("pq_")}
    st0 = next(s for s in S.script(lang="en", facts=no_pq, brief={})["steps"] if s["key"] == "deal_check")
    assert st0["route"] == f"/deal-desk/{F.TOUR_DEAL}" and "{check_deal}" not in str(st0["action"])
