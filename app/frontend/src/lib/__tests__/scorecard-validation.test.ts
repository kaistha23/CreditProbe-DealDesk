import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

/**
 * Scorecard Validation (PLAN_R3 S2), checked against its source.
 *
 * Structural claims about what the screens refuse to do: a verdict that is only a colour, a test with no stated
 * threshold, or a review that is not recorded would each look fine on screen and be wrong. The sweep
 * (ops/uat_sweep_scorecard.py) checks the behaviour in a browser; these keep the encoding of the rules in place.
 */

const root = fileURLToPath(new URL("../../", import.meta.url));
const read = (path: string) => readFileSync(root + path, "utf8");
const view = () => read("components/v5/scorecard/validation-view.tsx");

test("the home is a chat box on top and the past validations below it", () => {
  const home = read("components/v5/scorecard/home.tsx");
  assert.ok(home.indexOf('data-testid="sv-chat"') > -1 && home.indexOf('data-testid="sv-past"') > home.indexOf('data-testid="sv-chat"'));
  assert.ok(home.includes("createThread") && home.includes("/scorecard-validation/thread/"));
  assert.ok(home.includes('params.get("validation")'), "a ?validation= link opens the thread");
});

test("a verdict is a word as well as a colour, and the four states are styled apart", () => {
  const v = view();
  for (const state of ["green", "amber", "red", "na"]) assert.ok(v.includes(`${state}:`), `state ${state} is styled`);
  assert.ok(v.includes("STATUS_WORD[status]"), "the chip prints the word");
  const words = read("lib/v5/scorecard-words.ts");
  assert.ok(words.includes('na: "Not applicable"'));
});

test("every test row states its threshold and its reading", () => {
  const v = view();
  assert.ok(v.includes("Stated threshold") && v.includes("t.threshold") && v.includes("t.comment"));
  assert.ok(v.includes("data-status={t.status}"));
});

test("the charts are drawn through the shared Plotly surface, one per figure", () => {
  const v = view();
  assert.ok(v.includes('from "@/components/v5/ews/plot"') && v.includes("<Plot"));
  assert.ok(v.includes("chart.figure.data") && v.includes("chart.figure.layout"));
});

test("the review offers the three conclusions and records a note", () => {
  const v = view();
  assert.ok(v.includes("scorecard.review(") && v.includes("sv-review-note") && v.includes("Mark reviewed"));
  const words = read("lib/v5/scorecard-words.ts");
  for (const c of ["Fit for use", "Fit for use with conditions", "Not fit for use"]) assert.ok(words.includes(`"${c}"`), c);
});

test("Add to report uses the Playbook dialog's test ids and asks for a report or a new one", () => {
  const add = read("components/v5/scorecard/add-report.tsx");
  for (const id of ["add-report-dialog", "add-report-existing", "add-report-new", "add-report-title", "add-report-confirm", "add-report-done", "add-report-open", "add-report-error"]) {
    assert.ok(add.includes(`"${id}"`), id);
  }
  assert.ok(add.includes('template: "validation-report"'));
});

test("the module is reachable from the navigation and sends the session cookie to its own service", () => {
  const nav = read("lib/navigation.ts");
  assert.ok(/V5_LIVE_HREFS[^;]*"\/scorecard-validation"/.test(nav));
  const api = read("lib/v5/scorecard.ts");
  assert.ok(api.includes('credentials: "include"') && api.includes("NEXT_PUBLIC_SCORECARD_API") && api.includes("8507"));
});

test("a turn is answered in one request: no stream, a visible working state", () => {
  const thread = read("components/v5/scorecard/thread.tsx");
  assert.ok(thread.includes("sv-working") && thread.includes("scorecard.say("));
  assert.ok(!read("lib/v5/scorecard.ts").includes("EventSource"));
});
