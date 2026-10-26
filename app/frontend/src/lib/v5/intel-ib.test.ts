import assert from "node:assert/strict";
import { test } from "node:test";

import { INTEL_INTENTS, findIntent, intentPath, matchIntent } from "./intel-intents-ib.ts";
import { type CovenantRow, callsQuery, criterionLine, rate, renewalQuery, signalChips, sourceLine, threshold, topCriteria, versusTemplate } from "./intel-ib.ts";

test("intents: the three IB engines are routed from plain questions", () => {
  assert.equal(matchIntent("Who should I call today?")?.id, "ib.who_to_call");
  assert.equal(matchIntent("which renewals are due next quarter")?.id, "ib.renewal_autopilot");
  assert.equal(matchIntent("Can you design covenants for this deal?")?.id, "ib.covenant_designer");
  assert.equal(matchIntent("what is the ECL of the book"), null);
});

test("intents: ids unique, every intent has an API, panel and menu", () => {
  const ids = INTEL_INTENTS.map((i) => i.id);
  assert.equal(new Set(ids).size, ids.length);
  for (const i of INTEL_INTENTS) {
    assert.ok(i.api.path.startsWith("/api/v1/"));
    assert.ok(i.panel && i.menu && i.phrases.length > 0);
  }
});

test("intents: path fills the deal id and refuses without one", () => {
  const cov = findIntent("ib.covenant_designer")!;
  assert.equal(intentPath(cov, "DD-02"), "/api/v1/dealdesk/intel/covenants/DD-02");
  assert.throws(() => intentPath(cov));
  assert.equal(intentPath(findIntent("ib.who_to_call")!), "/api/v1/intel/calls");
});

test("queries", () => {
  assert.equal(renewalQuery({ cls: "exception", q: "Najd" }), "?days=90&cls=exception&limit=25&offset=0&q=Najd");
  assert.equal(callsQuery({ signal: "cheques", minWeight: 3 }), "?limit=25&offset=0&signal=cheques&min_weight=3");
});

test("renewal helpers", () => {
  const top = topCriteria({
    by_criterion: { stage: 5, dpd: 9, raroc: 100 },
    criteria: [
      { id: "stage", label: "Stage", op: ">=", threshold: 2, source: "", kind: "credit" },
      { id: "dpd", label: "DPD", op: ">", threshold: 0, source: "", kind: "credit" },
      { id: "raroc", label: "RAROC", op: "<", threshold: 0, source: "", kind: "commercial" },
    ],
  });
  assert.deepEqual(top.map((x) => x.id), ["dpd", "stage"]);
  assert.equal(criterionLine({ id: "x", label: "Covenant headroom below 10%", op: "<", threshold: 10, value: 4.234, fired: true, known: true, reads: "", kind: "credit" }),
    "Covenant headroom below 10%: 4.23 (exception if below 10)");
});

test("covenant helpers", () => {
  assert.equal(threshold(1.5, "x"), "1.50x");
  assert.equal(threshold(94.2, "%"), "94%");
  assert.equal(rate(0.426), "43%");
  assert.equal(rate(null), "–");
  const base = { covenant: "dscr", label: "DSCR", direction: "min", unit: "x", current: null, template_source: "", as_set: null,
    recommended: true, already_breached: false, text: "" } as const;
  const st = (e: number, f: number) => ({ threshold: 1, events: 10, detected: 5, hit_rate: e, early_hit_rate: e, on_time_rate: e, median_lead_q: 3, false_alarm_rate: f, precision: 0.3 });
  assert.equal(versusTemplate({ ...base, proposed: st(0.4, 0.05), template: st(0.1, 0.0) } as CovenantRow), "better");
  assert.equal(versusTemplate({ ...base, proposed: st(0.4, 0.05), template: null } as CovenantRow), "no template");
});

test("calls helpers", () => {
  const chips = signalChips({ signals: [{ id: "a", label: "A", weight: 2, action: "" }, { id: "b", label: "B", weight: 5, action: "" }, { id: "c", label: "C", weight: 4, action: "" }],
    by_signal: { a: 10, b: 1, c: 0 } });
  assert.deepEqual(chips.map((c) => c.id), ["b", "a"]);
  assert.equal(sourceLine({ domain: "ews", relation: "corp_exposure", column: "ews_band", period: "2026Q2" }), "ews.corp_exposure · ews_band · 2026Q2");
  assert.equal(sourceLine({ domain: "computed", relation: "r13_ib", method: "EAD × w" }), "Computed: EAD × w");
});
