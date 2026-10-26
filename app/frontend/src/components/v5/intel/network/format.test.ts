import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { type ContagionResult, type EmployerResult, type EventResult, contagionTiles, dsar, employerTiles, eventTiles,
         networkFigure, pct, sar, sourceLine } from "./format.ts";

const F = JSON.parse(readFileSync(new URL("./", import.meta.url).pathname + "network.fixture.json", "utf8")) as {
  event: EventResult; contagion: ContagionResult; employer: EmployerResult;
};

test("money and percent formats", () => {
  assert.equal(sar(1234.567), "SAR 1,234.6m");
  assert.equal(sar(null), "–");
  assert.equal(dsar(-2.5, 2), "−SAR 2.50m");
  assert.equal(dsar(0.3), "+SAR 0.3m");
  assert.equal(pct(1.234, 2, true), "+1.23%");
  assert.equal(pct(-4), "−4.0%");
});

test("event tiles carry the engine's numbers", () => {
  const t = eventTiles(F.event);
  assert.equal(t.length, 4);
  assert.equal(t[0].value, dsar(F.event.impact.ecl_change));
  assert.equal(t[2].value, F.event.affected.with_ecl_change.toLocaleString("en-US"));
  assert.equal(t[3].value, String(F.event.call_list.length));
});

test("contagion tiles and the network figure", () => {
  const t = contagionTiles(F.contagion);
  assert.equal(t[0].value, F.contagion.totals.names.toLocaleString("en-US"));
  const fig = networkFigure(F.contagion);
  const nodes = fig.data[fig.data.length - 1] as { x: number[]; customdata: string[] };
  assert.equal(nodes.x.length, F.contagion.network.nodes.length);
  assert.equal(nodes.customdata[0], F.contagion.focal.borrower_id);
  const kinds = new Set(F.contagion.network.edges.map((e) => e.kind));
  assert.equal(fig.data.length, kinds.size + 1);                     // one edge trace per channel, then the nodes
  for (const tr of fig.data.slice(0, -1) as { x: (number | null)[] }[]) assert.equal(tr.x.length % 3, 0);
});

test("employer tiles: appetite tone follows the status", () => {
  const t = employerTiles(F.employer);
  assert.equal(t[3].value, pct(F.employer.appetite.utilisation_pct, 0));
  assert.equal(t[3].tone, F.employer.appetite.status === "within appetite" ? "positive" : t[3].tone);
  assert.ok(sourceLine(F.employer.lineage).includes("Relationships · rel_edge_quarter"));
});

test("fixture: fictional names, deterministic writer text, limits present", () => {
  const blob = JSON.stringify(F);
  assert.doesNotMatch(blob, /emaar|aldar|nakheel|damac|aramco|sabic|al rajhi|neom|roshn/i);
  for (const r of [F.event, F.contagion, F.employer]) {
    assert.ok(r.text.headline.length > 20 && r.limits.length >= 2);
    assert.doesNotMatch(r.text.headline, /TODO|undefined|NaN/);
  }
});
