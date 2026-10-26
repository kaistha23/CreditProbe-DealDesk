import assert from "node:assert/strict";
import { test } from "node:test";

import {
  type Draft, type DraftSection, answerLine, citedFacts, lintBySection, methodLabel, parseSectionText, profileLabel, scoreTone,
  sectionText, sectionTone, splitCitations, withSection,
} from "./dealdesk-draft.ts";

const fact = (id: string, display: string) => ({ id, key: id, label: id, value: display, unit: "ccy m", display, source: "Proposal PRP-A-GMC",
  derived: null, kind: "number" as const, section: "financials" });

const sec = (over: Partial<DraftSection> = {}): DraftSection => ({
  key: "financials", heading: "Financial highlights (AED million)", voice: "business", judgement: false,
  paragraphs: ["Revenue AED 2,050m [F27] and EBITDA AED 96m [F28]."], bullets: [], table: null,
  citations: [fact("F27", "AED 2,050m"), fact("F28", "AED 96m")], exemplars: [], method: "template (no model key)", status: "draft",
  edited: false, version: 1, score: 80, ...over,
});

const draft = (over: Partial<Draft> = {}): Draft => ({
  draft_id: "DR-1", proposal_id: "PRP-A-GMC", title: "Credit Proposal: Gulf Meridian Contracting LLC", created: "",
  meta: { pid: "PRP-A-GMC", source: "case", bank: "house-uae", kind: "increase", segment: "contractor", currency: "AED",
    name: "Gulf Meridian Contracting LLC", sector: "Construction", rating: "BB-" },
  profile: { group: "house-uae|increase|contractor", bank_label: "UAE house (anonymised)", documents: 2, primary_exemplars: [], edits_learned: 0 },
  sections: [sec(), sec({ key: "recommendation", heading: "Recommendation", judgement: true })], facts: [],
  score: { total: 87.3, structure: 100, phrase: 71.4, stylometrics: 92.3, stylometric_parts: {}, band: { low: 70.5, high: 77.7, mean: 74.1, n: 2 }, within_band: true },
  lint: [], methods: ["template"], ...over,
});

test("citations split into text and chips", () => {
  assert.deepEqual(splitCitations("Revenue AED 2,050m [F27] and EBITDA AED 96m [F28]."), [
    { kind: "text", text: "Revenue AED 2,050m" }, { kind: "cite", id: "F27" }, { kind: "text", text: " and EBITDA AED 96m" },
    { kind: "cite", id: "F28" }, { kind: "text", text: "." }]);
  assert.deepEqual(splitCitations("No figures here."), [{ kind: "text", text: "No figures here." }]);
});

test("section text round-trips through the PATCH format", () => {
  const s = sec({ bullets: ["Renew the AED 50m bid bond line [F8]"] });
  const t = sectionText(s);
  assert.equal(t, "Revenue AED 2,050m [F27] and EBITDA AED 96m [F28].\n- Renew the AED 50m bid bond line [F8]");
  assert.deepEqual(parseSectionText(t), { paragraphs: s.paragraphs, bullets: s.bullets });
  assert.deepEqual(parseSectionText("\n  \n• one\n* two\nthree"), { paragraphs: ["three"], bullets: ["one", "two"] });
});

test("score tone follows the house band", () => {
  const band = { low: 70, high: 80, mean: 75, n: 5 };
  assert.equal(scoreTone(76, band), "positive");
  assert.equal(scoreTone(72, band), "warning");
  assert.equal(scoreTone(69.9, band), "negative");
  assert.equal(scoreTone(10, { low: 0, high: 100, mean: null, n: 0 }), "positive");
  assert.equal(sectionTone(undefined), "warning");
  assert.equal(sectionTone(90), "positive");
  assert.equal(sectionTone(40), "negative");
});

test("answer line states the result first", () => {
  const d = draft({ lint: [{ id: "L1", rule: "hedging", severity: "minor", section: "financials", message: "", excerpt: "", suggestion: "" }] });
  assert.equal(answerLine(d), "2 sections drafted from data, reads like the house: style score 87.3 (house band 70.5–77.7); 1 point differs from house style; "
    + "1 judgement section for the RM. 0 of 2 accepted.");
  const d2 = draft({ score: { ...d.score, within_band: false, total: 60 }, sections: d.sections.map((s) => ({ ...s, status: "accepted" as const })) });
  assert.match(answerLine(d2), /below the house band: style score 60 .* 2 of 2 accepted\.$/);
});

test("profile label, method labels, lint grouping", () => {
  assert.equal(profileLabel(draft()), "UAE house (anonymised) · increase · contractor");
  assert.equal(profileLabel(draft({ profile: { ...draft().profile, group: "house-ksa|*|*", bank_label: "KSA reference house" } })), "KSA reference house · all types · all");
  assert.equal(methodLabel("template (no model key)"), "House template");
  assert.equal(methodLabel("model"), "Model, figures checked");
  const g = lintBySection([
    { id: "L1", rule: "spelling", severity: "minor", section: "business", message: "", excerpt: "", suggestion: "" },
    { id: "L2", rule: "missing_section", severity: "major", section: "business", message: "", excerpt: "", suggestion: "" },
  ]);
  assert.deepEqual(g.business.map((l) => l.id), ["L2", "L1"]);
});

test("cited facts in citation order, and immutable section replace", () => {
  const s = sec({ paragraphs: ["EBITDA AED 96m [F28]; revenue AED 2,050m [F27]."] });
  assert.deepEqual(citedFacts(s).map((f) => f.id), ["F28", "F27"]);
  const d = draft();
  const d2 = withSection(d, { ...d.sections[0], status: "accepted" });
  assert.equal(d.sections[0].status, "draft");
  assert.equal(d2.sections[0].status, "accepted");
});

test("house number format and voice lines", async () => {
  const { numberFormatLine, voiceLine } = await import("./dealdesk-draft.ts");
  assert.equal(numberFormatLine({ unit: "m", decimals: 1, percent: "%", multiple: "x", trim_integers: true }, "AED", "British"),
    "AED 212.4m (AED 50m) · 12.5% · 1.25x · British spelling");
  assert.equal(voiceLine({ sentence_words: 10.9, sentence_sd: 6, hedges_per_100w: 0, first_person_per_100w: 0, passive_share: 0.1 }),
    "11 words a sentence · plain, unhedged · third person");
  assert.equal(voiceLine(undefined), "Not enough prose to measure");
});
