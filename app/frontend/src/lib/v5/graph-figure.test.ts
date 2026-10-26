import assert from "node:assert/strict";
import { test } from "node:test";

import { graphFigure, kindsIn, nodeSize, visible, type GEdge, type GNode, type GraphPayload } from "./graph-figure.ts";

const node = (id: string, over: Partial<GNode> = {}): GNode => ({
  id, type: "borrower", name: `Name ${id}`, ews_band: "low", exposure: 10, hop: 1, is_focal: false, x: 0, y: 0, ...over,
});
const edge = (id: string, s: string, t: string, kind: GEdge["kind"], over: Partial<GEdge> = {}): GEdge => ({
  id, source: s, target: t, type: kind.toUpperCase(), kind, label: id, directed: true, ...over,
});

const g: GraphPayload = {
  domain_id: "corporate", customer_id: "A", period: "2026Q2", depth: 1,
  focal: node("A", { is_focal: true, hop: 0, exposure: 40, ews_band: "high" }),
  nodes: [node("A", { is_focal: true, hop: 0, exposure: 40, ews_band: "high", x: 0, y: 0 }), node("B", { x: 0.5, y: 0.2, exposure: 10 }),
          node("C", { x: -0.5, y: 0.4, ews_band: "critical", exposure: 25 }), node("D", { x: 0.1, y: -0.8, ews_band: "none", exposure: 5 }),
          node("P:1", { type: "person", name: "A Person", x: 0.7, y: -0.6, exposure: 0, ews_band: "none", roles: [{ borrower_id: "A", role: "Owner", ownership_pct: 60 }] })],
  edges: [edge("e1", "A", "B", "group"), edge("e2", "C", "A", "supplier"), edge("e3", "A", "D", "customer"), edge("e4", "P:1", "A", "person", { directed: false })],
  legend: { group: { label: "Group", count: 1 }, supplier: { label: "Supplier", count: 1 }, customer: { label: "Customer", count: 1 },
            guarantor: { label: "Guarantor", count: 0 }, collateral: { label: "Shared collateral", count: 0 }, person: { label: "Owner or director", count: 1 } },
  truncated: {}, bands: [], analytics: {},
};

test("every kind on: every node and edge is drawn", () => {
  const f = graphFigure(g, new Set(["group", "supplier", "customer", "person"]));
  assert.deepEqual(f.shown, { nodes: 5, edges: 4 });
});

test("a kind switched off removes its edges and the names only it connected", () => {
  const v = visible(g, new Set(["group", "customer", "person"]));
  assert.deepEqual(v.nodes.map((n) => n.id).sort(), ["A", "B", "D", "P:1"]);  // C was a supplier only
  const none = visible(g, new Set());
  assert.deepEqual(none.nodes.map((n) => n.id), ["A"]);  // the borrower in the middle always stays
});

test("node colour is the band, the focal node is ringed, size follows exposure", () => {
  const f = graphFigure(g, new Set(["group", "supplier", "customer"]));
  const critical = f.data.find((d) => d.name === "Critical") as { marker: { color: string; size: number[] } };
  assert.equal(critical.marker.color, "#dc2626");
  const high = f.data.find((d) => d.name === "High") as { marker: { line: { width: number[] } }; customdata: { focal: boolean }[] };
  assert.equal(high.marker.line.width[0], 4);
  assert.equal(high.customdata[0].focal, true);
  assert.ok(nodeSize(40, 40) > nodeSize(10, 40) && nodeSize(0, 40) === 16);
  assert.ok(nodeSize(40, 40, true) < nodeSize(40, 40) && nodeSize(0, 40, true) === 11);  // a crowded graph draws smaller markers
});

test("edge traces: one per kind, an arrow only where the edge is directed, hover carries the detail", () => {
  const f = graphFigure(g, new Set(["group", "supplier", "person"]));
  const lines = f.data.filter((d) => d.mode === "lines+markers") as { legendgroup: string; marker: { size: number[] } }[];
  assert.deepEqual(lines.map((l) => l.legendgroup), ["group", "supplier", "person"]);
  assert.deepEqual(lines[0].marker.size, [0, 11, 0, 0]);
  assert.deepEqual(lines[2].marker.size, [0, 0, 0, 0]);  // a person link has no arrow
  const hover = f.data.find((d) => d.name === "Group (links)") as { text: string[] };
  assert.ok(hover.text[0].includes("A → B"));
});

test("kindsIn lists the kinds present, in legend order", () => {
  assert.deepEqual(kindsIn(g), ["group", "supplier", "customer", "person"]);
});
