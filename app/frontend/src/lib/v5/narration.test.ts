/** R16 n: the spoken narration of an answer, one case per module and per answer type. */
import { test } from "node:test";
import assert from "node:assert/strict";

import { type ChartFacts, type NarrationInput, answerLang, answerType, narrate, numberWords, speakNumbers } from "./narration.ts";
import type { ModuleKey } from "./thread-actions.ts";

const SAYS_NUMBER = /\b(zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|million|billion|percent)\b|\d/i;

const BAR: ChartFacts = { kind: "bar", title: "Exposure by sector", place: "right", unit: "SAR",
  series: [{ name: "EAD", labels: ["Construction", "Retail", "Energy"], values: [1.48e9, 0.61e9, 0.42e9] }] };

const CASES: [ModuleKey, Partial<NarrationInput>][] = [
  ["cockpit", { blocks: [{ kind: "text", text: "Twelve renewals fall due in the next 90 days, worth SAR 2.3 bn. Three of them are on the watch list." }],
                tables: [{ title: "", columns: ["Borrower", "Limit", "Due"], rows: [["Al Noor Trading", "SAR 120 mn", "12 Nov"], ["Tuwaiq Construction", "SAR 410 mn", "3 Dec"]], place: "below" }] }],
  ["noor", { blocks: [{ kind: "text", text: "Construction drove most of this quarter's rise in Stage 2." }, { kind: "figures", items: [{ label: "Stage 2 exposure", value: "SAR 3.1 bn" }, { label: "Change", value: "+12.5%" }] }] }],
  ["dealdesk", { blocks: [{ kind: "text", text: "Two proposals breach a hard limit. Both are in construction." }], charts: [BAR] }],
  ["whatif", { blocks: [{ kind: "text", text: "Under the severe scenario ECL rises to SAR 1.9 bn, up 38%." }],
               charts: [{ kind: "waterfall", title: "ECL decomposition", place: "below", unit: "SAR", series: [{ name: "", labels: ["Baseline", "PD shift", "LGD", "Scenario"], values: [1.4e9, 0.35e9, 0.12e9, 1.9e9] }] }] }],
  ["lenses", { blocks: [{ kind: "text", text: "The lens shows 41 borrowers with falling cash cover." }],
               charts: [{ kind: "pie", title: "By sector", place: "right", series: [{ name: "", labels: ["Construction", "Retail", "Other"], values: [22, 11, 8] }] }] }],
  ["ews", { blocks: [{ kind: "text", text: "The watch list grew by 7 customers this month." }],
            charts: [{ kind: "line", title: "Watch list", place: "below", series: [{ name: "Customers on watch", labels: ["Jul", "Aug", "Sep", "Oct"], values: [31, 33, 35, 42] }] }] }],
  ["b360", { blocks: [{ kind: "figures", items: [{ label: "Total exposure", value: "SAR 640 mn" }, { label: "Linked parties", value: "9" }] }] }],
  ["scorecard", { blocks: [{ kind: "text", text: "The SME scorecard still ranks well: the Gini is 0.58." }, { kind: "bullets", items: ["Stability index 0.12 on two factors", "Calibration within tolerance"] }] }],
  ["playbook", { blocks: [{ kind: "text", text: "Your report has 4 sections and 2 open questions." }] }],
  ["intel", { blocks: [{ kind: "text", text: "Renewals due in 90 days: 12, worth SAR 2.3 bn." }],
              charts: [{ kind: "hbar", title: "By RM", place: "right", series: [{ name: "", labels: ["Sara", "Omar", "Huda"], values: [5, 4, 3] }] }] }],
  ["agents", { blocks: [{ kind: "text", text: "The triage agent flagged 6 customers. We recommend opening Tuwaiq Construction first." }] }],
];

for (const [module, inp] of CASES) {
  test(`${module}: headline, a number said naturally, the visual, the next step`, () => {
    const n = narrate({ module, question: "q", lang: "en", blocks: [], ...inp });
    assert.equal(n.segments[0].part, "headline");
    assert.match(n.text, SAYS_NUMBER, "names a number");
    assert.ok(!/\d/.test(n.text), `numbers are said in words: ${n.text}`);
    assert.equal(n.segments.at(-1)?.part, "next");
    if (inp.charts?.length) {
      const v = n.segments.find((s) => s.part === "visual");
      assert.ok(v, "points at the chart");
      assert.match(v.text, /\b(chart|waterfall)\b/);
      assert.equal(v.target?.kind, "chart");
    }
    if (inp.tables?.length) assert.match(n.text, /row of the table/);
  });
}

test("the chart line names the outlier bar and pulses it", () => {
  const n = narrate({ module: "dealdesk", question: "", lang: "en", blocks: [{ kind: "text", text: "Construction leads." }], charts: [BAR] });
  const v = n.segments.find((s) => s.part === "visual")!;
  assert.equal(v.text, "In the chart on the right, the Construction bar stands well above the rest, at one point four eight billion riyals.");
  assert.deepEqual(v.target, { kind: "chart", chart: 0, series: 0, point: 0 });
});

test("the table line names the row with the largest figure", () => {
  const n = narrate(Object.assign({ module: "cockpit" as ModuleKey, question: "", lang: "en" as const, blocks: [] }, CASES[0][1]));
  const v = n.segments.find((s) => s.part === "visual")!;
  assert.match(v.text, /^Look at the second row of the table: Tuwaiq Construction, with limit of four hundred and ten million riyals\.$/);
  assert.deepEqual(v.target, { kind: "row", table: 0, row: 1 });
});

test("line, pie, waterfall wording", () => {
  const t = (k: number) => narrate({ module: CASES[k][0], question: "", lang: "en", blocks: [], ...CASES[k][1] }).segments.find((s) => s.part === "visual")!.text;
  assert.match(t(5), /^In the line chart below, Customers on watch rises from thirty-one in Jul to forty-two in Oct\.$/);
  assert.match(t(4), /largest slice is Construction, fifty-four percent of the total/);
  assert.match(t(3), /^In the waterfall below, the biggest step is Scenario/);
});

test("the answer's own next step wins over the module's", () => {
  const n = narrate({ module: "agents", question: "", lang: "en", ...CASES[10][1] } as NarrationInput);
  assert.match(n.segments.at(-1)!.text, /recommend opening Tuwaiq Construction first/);
  assert.ok(!n.segments.slice(0, -1).some((s) => /recommend/.test(s.text)), "said once");
});

test("no text: the headline comes from the question", () => {
  const n = narrate({ module: "b360", question: "How exposed is Najd Foods?", lang: "en", ...CASES[6][1] } as NarrationInput);
  assert.match(n.segments[0].text, /How exposed is Najd Foods/);
  assert.match(n.text, /Total exposure is six hundred and forty million riyals/);
});

test("Arabic answers are narrated in Arabic", () => {
  const blocks = [{ kind: "text" as const, text: "يتركز أعلى تعرض في قطاع البناء بقيمة 1.48 مليار ريال." }];
  assert.equal(answerLang(blocks[0].text), "ar");
  const n = narrate({ module: "dealdesk", question: "", lang: "ar", blocks, charts: [{ ...BAR, series: [{ name: "", labels: ["البناء", "التجزئة"], values: [1.48e9, 0.5e9] }] }] });
  assert.match(n.text, /في الرسم البياني على اليمين، يبرز عمود البناء/);
  assert.match(n.text, /الخطوة التالية/);
  assert.match(n.text, /\d/, "Arabic digits are left to the voice's own pacing");
});

test("numbers said naturally", () => {
  assert.equal(speakNumbers("SAR 1.48 bn"), "one point four eight billion riyals");
  assert.equal(speakNumbers("12.5% vs 40 bps"), "twelve point five percent versus forty basis points");
  assert.equal(speakNumbers("3.2x in 2026Q3"), "three point two times in Q three twenty twenty-six");
  assert.equal(speakNumbers("2,450 deals"), "two thousand four hundred and fifty deals");
  assert.equal(speakNumbers("SAR 1,480,000,000"), "one point four eight billion riyals");
  assert.equal(numberWords("-3"), "minus three");
  assert.equal(speakNumbers("in 2008"), "in two thousand and eight");
});

test("answer types", () => {
  assert.equal(answerType({ module: "noor", question: "", lang: "en", blocks: [], charts: [BAR] }), "chart");
  assert.equal(answerType({ module: "noor", question: "", lang: "en", blocks: [{ kind: "table", title: "", columns: ["a", "b"], rows: [["x", 1]] }] }), "table");
  assert.equal(answerType({ module: "noor", question: "", lang: "en", ...CASES[1][1] } as NarrationInput), "figures");
  assert.equal(answerType({ module: "noor", question: "", lang: "en", blocks: [{ kind: "bullets", items: ["a"] }] }), "list");
  assert.equal(answerType({ module: "noor", question: "", lang: "en", blocks: [{ kind: "text", text: "a" }] }), "text");
});

test("trailing zeros are not said; a headline that starts with a number starts with a capital", () => {
  assert.equal(speakNumbers("SAR 18.70 bn and 240.0 mn"), "eighteen point seven billion riyals and two hundred and forty million");
  const n = narrate({ module: "dealdesk", question: "", lang: "en", blocks: [{ kind: "text", text: "2 proposals breach a hard limit at the ask:" }] });
  assert.equal(n.segments[0].text, "Two proposals breach a hard limit at the ask.");
});

test("labels are not headlines; ids and codes are not figures; the row is named by its words", () => {
  const n = narrate({ module: "agents", question: "", lang: "en", blocks: [{ kind: "text", text: "Agent goal." }, { kind: "text", text: "132 borrowers look unlikely to pay." }],
    tables: [{ title: "", columns: ["#", "Borrower", "Article", "ECL"], rows: [["1", "Tuwaiq Construction · CB00002", "Art. 7.8", "SAR 12 mn"], ["2", "Najd Foods", "Art. 7.2", "SAR 40 mn"]], place: "below" }] });
  assert.match(n.segments[0].text, /^One hundred and thirty-two borrowers/);
  assert.match(n.text, /Look at the second row of the table: Najd Foods, with ECL of forty million riyals\./);
  assert.equal(speakNumbers("Borrower 360 · Bureau 564"), "Borrower three sixty, Bureau five hundred and sixty-four");
});

test("dates, meta lines, sentence capitals", () => {
  assert.equal(speakNumbers("due 2027-01-15 (86d)"), "due the fifteenth of January twenty twenty-seven (in eighty-six days)");
  const n = narrate({ module: "noor", question: "", lang: "en", blocks: [{ kind: "text", text: "Noor · Corporate Q2 2026 · Deal Desk today · ECL run 2026Q3" }, { kind: "text", text: "Stage 2 rose by 4%. 12 names moved." }] });
  assert.equal(n.segments[0].text, "Stage two rose by four percent.");
  const m = narrate({ module: "noor", question: "", lang: "en", blocks: [{ kind: "text", text: "Construction leads the book this quarter. 12 names moved to Stage 2." }] });
  assert.equal(m.segments[1].text, "Twelve names moved to Stage two.");
});

test("the largest chart is the one pointed at; index axes and long decimals are said plainly", () => {
  const spark: ChartFacts = { kind: "line", title: "Default-entry rate: 6 periods, latest 23.1827111984", place: "right", area: 4000,
    series: [{ name: "", labels: ["0", "1", "2"], values: [1.23, 9.5, 23.1827111984] }] };
  const big: ChartFacts = { ...BAR, area: 90000 };
  const n = narrate({ module: "ews", question: "", lang: "en", blocks: [{ kind: "text", text: "The watch list grew this quarter." }], charts: [spark, big] });
  const v = n.segments.filter((s) => s.part === "visual");
  assert.equal(v.length, 1);
  assert.deepEqual(v[0].target, { kind: "chart", chart: 1, series: 0, point: 0 });
  const only = narrate({ module: "ews", question: "", lang: "en", blocks: [], charts: [spark] }).segments.find((s) => s.part === "visual")!;
  assert.equal(only.text, "In the line chart on the right, Default-entry rate rises from one point two three to twenty-three point one eight over the last three periods.");
});

test("a formula in brackets is not said; a cut never leaves a bracket open", () => {
  const n = narrate({ module: "noor", question: "", lang: "en", blocks: [{ kind: "text", text: "Stage 3 provision is below the wholesale floor: the bank holds a Stage 3 LGD of 44.1% (ECL ÷ EAD) against a floor of 45%." }] });
  assert.equal(n.segments[0].text, "Stage three provision is below the wholesale floor: the bank holds a Stage three LGD of forty-four point one percent against a floor of forty-five percent.");
});
