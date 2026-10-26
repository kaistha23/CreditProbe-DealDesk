import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

/**
 * Deal Desk (DEAL_DESK_PROMPT section 4, PLAN_R4 G3), checked against its source. The sweep
 * (ops/uat_sweep_dealdesk.py) checks the behaviour in a browser; these keep the design rules encoded.
 */

const root = fileURLToPath(new URL("../../", import.meta.url));
const read = (path: string) => readFileSync(root + path, "utf8");
const dir = "components/v5/dealdesk/";

test("the module is in the v5 sidebar under Intelligence and talks to port 8508 with the session cookie", () => {
  const nav = read("lib/navigation.ts");
  assert.ok(nav.includes('href: "/deal-desk"') && nav.slice(nav.indexOf("export const V5_LIVE_HREFS")).split("];")[0].includes('"/deal-desk"'));
  const lib = read("lib/v5/dealdesk.ts");
  assert.ok(lib.includes('credentials: "include"') && lib.includes("NEXT_PUBLIC_DEALDESK_API") && lib.includes("8508"));
});

test("the home is the What-If pattern: the chat box on top, the pipeline below, New proposal beside it", () => {
  const home = read(dir + "home.tsx");
  // R13 X: the chat box is the shared ModuleLanding (ids="dealdesk" gives data-testid="dealdesk-chat")
  assert.ok(home.indexOf('<ModuleLanding ids="dealdesk"') > -1 && home.indexOf('testId="dealdesk-pipeline"') > home.indexOf('<ModuleLanding ids="dealdesk"'));
  for (const f of ["dealdesk-filter-sector", "dealdesk-filter-rating", "dealdesk-filter-size", "dealdesk-filter-rm", "dealdesk-new"]) assert.ok(home.includes(f), f);
  // PLAN_R5 D3: Recent analyses (saved and optimised, with the Word report of a saved one) below the pipeline, and the continue row
  assert.ok(home.indexOf("<RecentAnalyses") > home.indexOf('testId="dealdesk-pipeline"'), "recent analyses below the pipeline");
  assert.ok(home.includes('data-testid="dealdesk-continue"') && home.includes("x.report"), "continue row; saved analyses keep their Word report");
  // PLAN_R5 G4 + R14 n (K16): asking on the home opens a NEW thread (its own id) in the one thread frame
  const desk = read(dir + "desk-thread.tsx");
  assert.ok(home.includes("openDeskThread(") && !home.includes("?thread=desk"));
  assert.ok(desk.includes("<ThreadShell") && desk.includes("LiveTrace") && desk.includes("newDeskThread"));
});

test("a deal has the four-step stepper, and the chat box at the bottom of the thread", () => {
  const kit = read(dir + "kit.tsx");
  // PLAN_R14 (R14 F): the first step is labelled Upload, followed by Proposal check
  for (const s of ["Upload", "Proposal check", "Analysis", "Structure", "Recommendation"]) assert.ok(kit.includes(`label: "${s}"`), s);
  const thread = read(dir + "thread.tsx");
  // PLAN_R5 G4, superseded by PLAN_R10 D6: the shared Composer in its own bar below the scrolling panel (nothing under it),
  // the trace on every turn. R13 X (J10): Optimise and the deal actions are back on the composer bar (R11), via DealBarActions.
  assert.ok(thread.includes("<Composer") && thread.includes('inputTestId="dealdesk-composer"'));
  assert.ok(thread.includes("actions={<DealBarActions") && read(dir + "action-bar.tsx").includes('data-testid="dealdesk-optimise"'));
  assert.ok(thread.indexOf('data-testid="dealdesk-conversation"') < thread.indexOf('data-testid="thread-composer"'), "composer after the panel");
  assert.ok(thread.includes("<AssistantTurn trace=") && thread.includes("<LiveTrace"));
});

test("at most one primary action per step; Optimise lives with the chat box (G4)", () => {
  const steps = read(dir + "steps.tsx");
  const chunks = steps.split("// ------------------------------------------------------------------ ").slice(2);
  for (const c of chunks) {
    const n = (c.match(/<PrimaryButton/g) ?? []).length;
    assert.ok(n <= 1, `${c.slice(0, 20)}: ${n}`);
  }
  assert.ok(!steps.includes('data-testid="dealdesk-optimise"'), "no Optimise button at the top of a step");
});

test("every chart goes through the shared Plotly surface with a download file name", () => {
  const charts = read(dir + "charts.tsx");
  const plots = charts.match(/<Plot /g) ?? [];
  assert.ok(plots.length >= 7);
  assert.equal((charts.match(/filename="deal-desk-/g) ?? []).length, plots.length);
  assert.ok(charts.includes('categoryorder: "array"'), "the rating axis keeps the global order");
});

test("the term panel recomputes through the engine, never the assistant, newest request wins", () => {
  const panel = read(dir + "term-panel.tsx");
  assert.ok(panel.includes("dealdesk.compute(") && !panel.includes("dealdesk.ask(") && panel.includes("seq.current"));
});

test("no loose provenance or warning paragraphs: explanations sit behind the (i)", () => {
  for (const f of ["home.tsx", "steps.tsx", "thread.tsx"]) {
    const src = read(dir + f);
    for (const phrase of [/synthetic/i, /\bdemo\b/i, /not available/i, /written by the assistant/i, /every figure checked/i]) {
      assert.ok(!phrase.test(src), `${f}: ${phrase}`);
    }
  }
});
