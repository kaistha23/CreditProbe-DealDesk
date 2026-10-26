import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

/** PLAN_R7 Session U, checked against the source. The sweep (`r7-ui`, `dealdesk`) checks the behaviour in a browser. */

const root = fileURLToPath(new URL("../../", import.meta.url));
const read = (path: string) => readFileSync(root + path, "utf8");

// PLAN_R10 L1 supersedes R9 G5: the illustration is removed; a small mark under Sign in, "AI powered" beneath.
test("R10 L1: no login illustration; the AI-powered mark sits under the Sign in button, with a fallback", () => {
  const login = read("components/v5/core/login.tsx");
  assert.ok(!login.includes("IntelligenceVisual") && !login.includes("AiBrain"));
  assert.ok(!require_exists("components/v5/core/intelligence-visual.tsx"), "the R9 illustration is gone");
  assert.ok(!require_exists("components/v5/core/ai-brain.tsx"), "the brain diagram is gone");
  assert.ok(login.indexOf("<AiPoweredMark") > login.indexOf('data-testid="login-submit"'), "mark under Sign in");
  const mark = read("components/v5/core/ai-powered-mark.tsx");
  assert.ok(mark.includes('"/brand/ai-powered-mark.png"') && mark.includes("onError") && mark.includes("login-ai-mark-fallback"));
  assert.ok(/figcaption[^>]*>AI powered</.test(mark));
  assert.ok(/AI_MARK_SIZE = (5[6-9]|6[0-4]);/.test(mark), "about 56-64 px");
});

function require_exists(path: string): boolean {
  try { read(path); return true; } catch { return false; }
}

// PLAN_R12 N1 (I1): one new expectation: a deal opens on Proposal (R7 opened on Analysis).
test("U2: a deal opens on Proposal, never jumping past it, and does not scroll to the composer on load", () => {
  const thread = read("components/v5/dealdesk/thread.tsx");
  assert.ok(thread.includes("const step: StepKey = parseStep(urlStep);"), "Proposal unless ?step= names another");
  assert.ok(read("lib/v5/dealdesk-r12.ts").includes('export const LANDING_STEP: R12StepKey = "proposal";'));
  assert.ok(!thread.includes('go("structure");\n      if (x.state.optimisation)') && !/if \(x\.state\.recommended\) go\(/.test(thread));
  // R10 D6: the panel scrolls only after a new question (nothing is scrolled on load).
  assert.ok(thread.includes("if (!added && !pending) return;"));
  const steps = read("components/v5/dealdesk/steps.tsx");
  const proposal = steps.slice(steps.indexOf("export function ProposalStep"), steps.indexOf("export function AnalysisStep"));
  assert.ok(proposal.indexOf('data-testid="dealdesk-analyse"') < proposal.indexOf("<ProposalInFull"), "Analyse the ask above the proposal in full");
  const analysis = steps.slice(steps.indexOf("export function AnalysisStep"));
  for (const c of ["<WaterfallChart", "<IsoRarocHeatmap", "<RarocAmountCurve", "<TornadoChart"]) assert.ok(analysis.includes(c), c);
  for (const i of ["<WaterfallInfo", "<HeatmapInfo", "<AmountInfo", "<TornadoInfo"]) assert.ok(analysis.includes(i), i);
});

test("R7 (screen 01): Settings and Optimise on the analysis chart card; a saved recommendation one click away", () => {
  const steps = read("components/v5/dealdesk/steps.tsx");
  const analysis = steps.slice(steps.indexOf("export function AnalysisStep"), steps.indexOf("// ------------------------------------------------------------------ 3"));
  assert.ok(analysis.includes('data-testid="dealdesk-analysis-optimise"') && analysis.includes("{settings}"));
  assert.ok(analysis.includes('data-testid="dealdesk-open-recommendation"'));
  const thread = read("components/v5/dealdesk/thread.tsx");
  assert.ok(thread.includes('testId="dealdesk-card-optimiser"'), "the card's settings have their own test ids");
  assert.ok(thread.includes('onRecommendation={rec ? () => go("recommendation") : undefined}'));
});

test("R7 Back: every v5 Back goes to the exact previous screen (history), else returnTo, else the parent", () => {
  const files: Record<string, string> = {
    "components/v5/dealdesk/thread.tsx": 'testId="dealdesk-back"',
    "components/v5/whatif/thread.tsx": 'testId="whatif-back"',
    "components/v5/whatif/model-card.tsx": 'testId="whatif-card-back"',
    "components/v5/scorecard/thread.tsx": 'testId="sv-back"',
    "components/v5/playbook/report.tsx": 'testId="playbook-back"',
    "components/v5/policy/document.tsx": 'testId="policy-back"',
    "components/v5/lenses/lens-view.tsx": 'testId="lens-back"',
    "components/v5/workspace/parts.tsx": 'testId="ws-back"',
    "components/v5/b360/workspace.tsx": 'testId="b360-back"',
    "app/early-warning/model/page.tsx": 'testId="ews-model-back"',
  };
  for (const [f, id] of Object.entries(files)) {
    const s = read(f);
    assert.ok(s.includes("<BackButton") && s.includes(id), f);
  }
  for (const f of ["components/v5/dealdesk/home.tsx", "components/v5/playbook/home.tsx", "components/v5/mail/mail-app.tsx", "components/v5/ews/workspace.tsx"]) {
    assert.ok(read(f).includes("backOr(router"), f);
  }
  const thread = read("components/v5/dealdesk/thread.tsx");
  assert.ok(thread.includes("window.history.pushState"), "each Deal Desk step is a history entry");
  assert.ok(read("components/layout/app-shell.tsx").includes("recordVisit("), "the trail is recorded for browsers without the Navigation API");
});
