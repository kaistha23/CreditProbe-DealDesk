/** R13 Session X (J4, J7, J9, J10): declutter, one module landing, the R11 layouts back. */
import { readFileSync } from "node:fs";
import test from "node:test";
import assert from "node:assert/strict";

const root = new URL("../../", import.meta.url).pathname;
const read = (p: string) => readFileSync(root + p, "utf8");

test("J7: no module-top Noor strip on any module page", () => {
  for (const r of ["deal-desk", "what-if", "lenses", "early-warning", "borrower-360"]) {
    const page = read(`app/${r}/page.tsx`);
    assert.ok(!page.includes("NoorModuleBrief") && !page.includes("noor/module-brief"), r);
  }
});

test("J7: Deal Desk, What-If and Lenses land on the shared ModuleLanding; Early Warning and Borrower 360 keep their tables with one ask line", () => {
  for (const [f, ids] of [["components/v5/dealdesk/home.tsx", "dealdesk"], ["components/v5/whatif/home.tsx", "whatif"], ["components/v5/lenses/home.tsx", "lenses"]]) {
    const h = read(f);
    assert.ok(h.includes(`<ModuleLanding ids="${ids}"`), f);
    assert.ok(h.includes("recent="), `${f}: recent-work cards`);
  }
  const ews = read("components/v5/ews/workspace.tsx");
  assert.ok(ews.includes('<CockpitAskBar ids="ews"') && ews.includes("<LevelView"));
  const b360 = read("components/v5/b360/workspace.tsx");
  assert.ok(b360.indexOf('<CockpitAskBar ids="b360"') > -1 && b360.indexOf('<CockpitAskBar ids="b360"') < b360.indexOf("<BookList"));
  const ml = read("components/v5/landing/module-landing.tsx");
  assert.ok(ml.includes("export function ModuleLanding") && ml.includes("export function AskBar") && ml.includes("export function CockpitAskBar"));
  assert.ok(ml.includes("mx-auto w-full max-w-3xl") && ml.includes("text-center"), "the box is centred");
});

test("J4: the What-If thread opens on the question; the book figures are one collapsed 'Book at a glance' line", () => {
  const h = read("components/v5/whatif/header.tsx");
  const th = h.slice(h.indexOf("export function ThreadHeader"));
  assert.ok(th.includes('"Book at a glance"') && th.includes("React.useState(false)") && th.includes('data-testid="whatif-glance"'));
  assert.ok(th.indexOf("{expanded ? (") < th.indexOf("<SummaryCards"), "the tiles only when the line is opened");
});

test("J9: the landing counters read the material lists", () => {
  const api = read("components/v5/dealdesk/book/api.ts");
  assert.ok(api.includes('"material_going_bad"') && api.includes('"material_renewals"'));
  const cards = read("components/v5/dealdesk/landing-cards.tsx");
  assert.ok(cards.includes("function Counter(") && cards.includes("title={`${c.title}: ${c.sub}`}"), "definitions in the tooltip, not on screen");
});
