/**
 * R16 m (M2): the Early Warning card's primary action is the segment analysis; the What-If cohort thread is the
 * optional "Stress this cohort" inside it, and the cohort thread opens on the same analysis (compact).
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { analysisKey, change } from "../segment-analysis-model.ts";

const SRC = join(import.meta.dirname, "..", "..", "..", "..");
const read = (p: string) => readFileSync(join(SRC, p), "utf8");

test("the analysis key is the card's key (segment, sub-segment, classification, level-drill value)", () => {
  assert.equal(analysisKey({ segment: "Construction" }), "Construction");
  assert.equal(analysisKey({ segment: "Construction", sub: "Residential" }), "Residential");
  assert.equal(analysisKey({ segment: "Credit Card", cls: "SALARIED" }), "SALARIED");
  assert.equal(analysisKey({ dims: { region: "Riyadh", branch: "Riyadh Olaya" } }), "Riyadh Olaya");
  assert.equal(analysisKey({}), "portfolio");
  assert.equal(change(3), "+3");
  assert.equal(change(-2), "−2");
  assert.equal(change(null), "—");
});

test("regression: the card's primary action is Analyse, which opens the segment analysis (not What-If)", () => {
  const ws = read("components/v5/ews/workspace.tsx");
  const card = ws.slice(ws.indexOf("export function ChildCard"));
  assert.ok(card.includes("data-testid={`ews-analyse-${card.key}`}"), "the card renders the Analyse button");
  assert.ok(card.includes("onClick={onAnalyse}"));
  assert.ok(/> Analyse\s*</.test(card), "labelled Analyse");
  assert.ok(!card.includes('label="What-If"'), "the old What-If button is gone from the card");
  // the level view and the level drill both wire the action into the address (Back returns to the cards)
  assert.ok(ws.includes('"analysis"') && ws.includes('analysis: "1"'));
  assert.ok(ws.includes("onAnalyse={() => open({ ...nextScope, analysis: \"1\" })}"));
  assert.ok(ws.includes("onAnalyse={(d) => openDims(d, { analysis: \"1\" })}"));
  assert.ok(ws.includes("state.analysis ? (") && ws.includes("<SegmentAnalysisView"));
  const lv = read("components/v5/ews/levels.tsx");
  assert.ok(lv.includes("onAnalyse={onAnalyse ? () => onAnalyse(step(c.key)) : undefined}"));
});

test("the analysis has every section, plain words first, and Stress this cohort is the existing export", () => {
  const a = read("components/v5/ews/segment-analysis.tsx");
  const card = a.slice(a.indexOf("export function SegmentAnalysisCard"), a.indexOf("function Section("));
  assert.ok(card.indexOf("<PlainWords") < card.indexOf("ews-analysis-headline"), "plain words open the panel");
  for (const id of ["ews-analysis-headline", "ews-analysis-drivers", "ews-analysis-rules", "ews-analysis-top",
                    "ews-analysis-ecl", "ews-analysis-actions"]) assert.ok(card.includes(`"${id}"`), id);
  assert.ok(card.includes('<ExportToWhatIf testId={`ews-export-${cardKey}`} label="Stress this cohort" body={a.stress} />'));
  assert.ok(card.includes("onOpenCustomer(n.customer_id)") && card.includes("n.links.borrower_360"), "names open the customer");
  assert.ok(card.includes("a.sources."), "every section states its source");
  const lib = read("lib/v5/ews.ts");
  assert.ok(lib.includes("segmentAnalysis:") && lib.includes("/segment-analysis"));
});

test("the What-If cohort thread opens on the compact analysis; its header wraps instead of squeezing", () => {
  const b = read("components/v5/whatif/blocks.tsx");
  const cohort = b.slice(b.indexOf("function CohortCard"));
  assert.ok(cohort.includes("{block.analysis ? <SegmentAnalysisCompact a={block.analysis} /> : null}"));
  assert.ok(cohort.indexOf("SegmentAnalysisCompact") < cohort.indexOf('testId="whatif-customers"'), "analysis before the tiles");
  const a = read("components/v5/ews/segment-analysis.tsx");
  assert.ok(a.includes('data-testid="whatif-cohort-analysis"') && a.includes('testId="whatif-cohort-plain-words"'));
  const h = read("components/v5/whatif/header.tsx");
  assert.ok(h.includes("flex w-full min-w-0 flex-wrap items-center"), "the glance line wraps");
  assert.ok(h.includes("min-w-[min(100%,18rem)] flex-[1_1_18rem]"), "the figures keep a usable width");
});
