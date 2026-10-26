/** PLAN_R11 Session U: six horizontal steps, the panels under the Optimise structures, the thread's R11 actions. */
import { readFileSync, existsSync } from "node:fs";
import test from "node:test";
import assert from "node:assert/strict";

const root = new URL("../../", import.meta.url).pathname;
const read = (p: string) => readFileSync(root + p, "utf8");
const dir = "components/v5/dealdesk/";

// PLAN_R12 N1: the step order changed (I15); PLAN_R14 (K23, K31, R14 F): Upload → Proposal check → Review → Analysis → Structure →
// Recommendation, with Stress a header button over the chosen structures (?step=stress keeps its key).
test("U1: six steps in order, the four existing keys and labels unchanged, ?step=stress and ?step=review", () => {
  const k = read(dir + "kit.tsx");
  const steps = k.slice(k.indexOf("export const STEPS"), k.indexOf("] as const;"));
  const keys = [...steps.matchAll(/key: "([\w-]+)", label: "([\w ]+)"/g)].map((m) => `${m[1]}:${m[2]}`);
  assert.deepEqual(keys, ["proposal:Upload", "proposal-check:Proposal check", "review:Review", "analysis:Analysis", "structure:Structure", "recommendation:Recommendation"]);
  const t = read(dir + "thread.tsx");
  // R13 X: the R11 review workspace is the Review step's first view (the 12-point review one click away)
  assert.ok(t.includes('step === "stress" ? (') && t.includes("<StressOverStructures") && t.includes("<StressStep") && t.includes('reviewModeNow === "workspace" ? <ReviewStep'));
  assert.ok(t.includes('if (s === LANDING_STEP) q.delete("step"); else q.set("step", s);'), "the ?step= URL scheme is the R7 one, Proposal when absent (R12 I1)");
  assert.ok(!t.includes('["proposal", "analysis", "structure", "recommendation"]'), "no hard-coded four-step list left");
});

test("U2: the Optimise structures stay first; forward risk, the stress summary and Test against pipeline follow in order", () => {
  const s = read(dir + "steps.tsx");
  const structure = s.slice(s.indexOf("export function StructureStep"), s.indexOf("// ------------------------------------------------------------------ 3a"));
  const iView = structure.indexOf("<OptimiseView"), iPanels = structure.indexOf("<R11OptimisePanels"), iSheet = structure.indexOf("<TermSheet");
  assert.ok(iView > -1 && iView < iPanels && iPanels < iSheet, "structures, then the R11 panels, then the term sheet");
  const panels = s.slice(s.indexOf("export function R11OptimisePanels"), s.indexOf("// ------------------------------------------------------------------ 4 Stress"));
  const a = panels.indexOf("<ForwardRiskPanel"), b = panels.indexOf("<StressSummary"), c = panels.indexOf("<PipelineTestButton");
  assert.ok(a > -1 && a < b && b < c, "forward risk, stress summary, pipeline test");
  assert.equal((panels.match(/<Collapsible /g) ?? []).length, 3, "each is collapsible");
  assert.ok(panels.includes("ready={ready}") && panels.includes("const ready = Boolean(opt && terms)"), "the pipeline test activates with the optimisation result");
  // the Optimise view itself is untouched by R11
  assert.ok(!read(dir + "optimise-view.tsx").includes("R11"));
});

test("U2: a collapsible panel remembers its state, guarded for blocked storage", () => {
  const k = read(dir + "kit.tsx");
  const c = k.slice(k.indexOf("function readOpen"));
  assert.ok(c.includes("localStorage.getItem(`dealdesk.panel.${key}`)") && c.includes("localStorage.setItem(`dealdesk.panel.${id}`"));
  assert.equal((c.match(/try \{/g) ?? []).length, 2, "every storage call in try/catch");
  assert.ok(k.includes("aria-expanded={open}") && k.includes("FoldContext.Provider value={null}"), "the outermost Section folds, nested ones do not");
  const sec = k.slice(k.indexOf("export function Section("), k.indexOf("/** A chart's own title"));
  assert.ok(sec.includes('<h2 className="text-[14px] font-semibold text-text-primary">{title}</h2>'), "the Section title unchanged for every existing card");
});

test("U2: the real component exports are mounted and the stand-ins file is gone", () => {
  assert.ok(!existsSync(root + dir + "__r11_slots__.tsx"), "the slots file is deleted once the component branches merged");
  const s = read(dir + "steps.tsx");
  for (const [name, file] of [["ForwardRiskPanel", "forward-risk"], ["PipelineTestButton", "pipeline-test"], ["ReviewWorkspace", "review-workspace"]]) {
    // R14 F (K21): pipeline-test also exports PipelineLinesPanel (the test on the selected structure), imported on the same line
    assert.ok(s.includes(`import { ${name} } from "./${file}"`) || new RegExp(`import \\{[^}]*\\b${name}\\b[^}]*\\} from "\\./${file}"`).test(s), name);
  }
  // PLAN_R12 integration (U): Session D's StressLabStep replaces the R11 StressLab on the Stress step; StressSummary stays.
  assert.ok(s.includes('import { StressSummary } from "./stress-lab"') && s.includes('import { StressLabStep } from "./stress-lab-r12"'));
  assert.ok(read(dir + "thread.tsx").includes('import { ConditionsTracker } from "./review-conditions"'));
  const home = read(dir + "home.tsx");
  assert.ok(home.includes('mode === "single" ? <ConditionsDueLine /> : null'), "conditions due on the landing, Single deal mode");
});

test("U3: a stress or review answer opens its step", () => {
  const t = read(dir + "thread.tsx");
  assert.ok(t.includes('stress_lab: "stress"') && t.includes('review: "review"') && t.includes('committee_sheet: "review"'));
});

test("U4: the new steps use the kit (Section, (i)), one primary action at most, no rough text", () => {
  const s = read(dir + "steps.tsx");
  const stress = s.slice(s.indexOf("export function StressStep"), s.indexOf("// ------------------------------------------------------------------ 5 Review"));
  assert.ok(stress.indexOf("<AskLine") > -1 && stress.indexOf("<AskLine") < stress.indexOf("<StressLab"), "the ask line, then the Stress Lab (its own Section)");
  const review = s.slice(s.indexOf("export function ReviewStep"), s.indexOf("export function relaxRead"));
  assert.ok(review.includes("<ReviewWorkspace proposalId="), "the Review step is R's workspace");
  for (const chunk of ["// ------------------------------------------------------------------ 3a"]) {
    const body = s.slice(s.indexOf(chunk), s.indexOf("// ------------------------------------------------------------------ ", s.indexOf(chunk) + 10));
    assert.ok(body.includes("<Section") && body.includes("<Collapsible"), chunk);
    assert.ok((body.match(/<PrimaryButton/g) ?? []).length <= 1, chunk);
    assert.ok(!/TODO|FIXME|lorem|JSON\.stringify/.test(body), chunk);
  }
});
