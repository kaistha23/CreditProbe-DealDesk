/**
 * Unit tests for the BRF studio graph helpers (PLAN_R10 Session B). No network.
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  type BrfGraph, NODE_W, addNode, columnOf, connect, counts, defaultNode, describe, keepPositions, layout, removeEdges, removeNodes,
  stripPositions, updateNode,
} from "./brf-studio.ts";

const G: BrfGraph = {
  nodes: [
    { id: "src:f", kind: "source", label: "corp_facility_quarter", spec: { dataset: "books.corp_facility_quarter" } },
    { id: "tx:p", kind: "transform", label: "Filter to period", spec: { op: "period" } },
    { id: "tx:s3", kind: "transform", label: "Filter Stage 3", spec: { op: "filter", where: "stage == 3" } },
    { id: "calc:ead", kind: "calc", label: "Stage 3 EAD", spec: { op: "sum", field: "ead_sar_mn" } },
    { id: "calc:ecl", kind: "calc", label: "Stage 3 ECL", spec: { op: "sum", field: "ecl_sar_mn" } },
    { id: "calc:cov", kind: "calc", label: "Stage 3 coverage", spec: { op: "pct", inputs: ["calc:ecl", "calc:ead"] } },
    { id: "chk:1", kind: "check", label: "Check", spec: { op: "zero" } },
    { id: "out:L01", kind: "output", label: "Stage 3 coverage", spec: { cell: "L01" } },
  ],
  edges: [
    { id: "e1", source: "src:f", target: "tx:p" }, { id: "e2", source: "tx:p", target: "tx:s3" },
    { id: "e3", source: "tx:s3", target: "calc:ead" }, { id: "e4", source: "tx:s3", target: "calc:ecl" },
    { id: "e5", source: "calc:ecl", target: "calc:cov" }, { id: "e6", source: "calc:ead", target: "calc:cov" },
    { id: "e7", source: "calc:cov", target: "out:L01" }, { id: "e8", source: "calc:ead", target: "chk:1" },
  ],
};

test("columns run left to right: source, period, filter, aggregate, derived, check, output", () => {
  const col = (id: string) => columnOf(G.nodes.find((n) => n.id === id)!, G);
  assert.deepEqual(["src:f", "tx:p", "tx:s3", "calc:ead", "calc:cov", "chk:1", "out:L01"].map(col), [0, 1, 2, 4, 5, 7, 8]);
});

test("layout places every node, without overlaps, and keeps user positions", () => {
  const l = layout(G);
  assert.ok(l.nodes.every((n) => n.position));
  const keys = l.nodes.map((n) => `${n.position!.x},${n.position!.y}`);
  assert.equal(new Set(keys).size, keys.length);
  assert.equal(l.nodes.find((n) => n.id === "tx:p")!.position!.x, NODE_W + 70);
  const moved = { ...G, nodes: G.nodes.map((n) => (n.id === "chk:1" ? { ...n, position: { x: 5, y: 7 } } : n)) };
  assert.deepEqual(layout(moved).nodes.find((n) => n.id === "chk:1")!.position, { x: 5, y: 7 });
});

test("keepPositions carries positions across a server round trip", () => {
  const before = layout(G);
  const server = stripPositions(before);
  assert.ok(server.nodes.every((n) => !n.position));
  const after = keepPositions(server, before);
  assert.deepEqual(after.nodes.map((n) => n.position), before.nodes.map((n) => n.position));
});

test("removing a node removes its edges", () => {
  const g = removeNodes(G, ["calc:cov"]);
  assert.equal(g.nodes.length, G.nodes.length - 1);
  assert.ok(!g.edges.some((e) => e.source === "calc:cov" || e.target === "calc:cov"));
  assert.equal(removeEdges(G, ["e8"]).edges.length, G.edges.length - 1);
});

test("adding nodes gives each kind a usable default", () => {
  let g = G;
  for (const k of ["source", "transform", "calc", "check", "output"] as const) g = addNode(g, defaultNode(k, g));
  assert.deepEqual(counts(g), { source: 2, transform: 3, calc: 4, check: 2, output: 2 });
  const out = g.nodes.filter((n) => n.kind === "output").at(-1)!;
  assert.equal(out.spec.cell, "L02");
  assert.equal(new Set(g.nodes.map((n) => n.id)).size, g.nodes.length);
});

test("connect: no self-loops or duplicates; an output reads one value; inputs keep order", () => {
  assert.equal(connect(G, "calc:ead", "calc:ead"), G);
  assert.equal(connect(G, "tx:p", "tx:s3"), G);
  const g = connect(G, "calc:ead", "out:L01");
  assert.deepEqual(g.edges.filter((e) => e.target === "out:L01").map((e) => e.source), ["calc:ead"]);
  const g2 = connect(G, "calc:ead", "calc:cov");
  assert.deepEqual(g2.nodes.find((n) => n.id === "calc:cov")!.spec.inputs, ["calc:ecl", "calc:ead"]);
});

test("updateNode and describe", () => {
  const g = updateNode(G, "calc:ead", { label: "EAD", spec: { where: "sector == 'Construction'" } });
  const n = g.nodes.find((x) => x.id === "calc:ead")!;
  assert.equal(n.label, "EAD");
  assert.equal(describe(n), "Σ ead_sar_mn where sector == 'Construction'");
  assert.equal(describe(G.nodes[1]), "reporting_quarter = locked period");
  assert.equal(describe(G.nodes.find((x) => x.id === "calc:cov")!), "A ÷ B × 100");
  assert.equal(describe(G.nodes.at(-1)!), "Line L01");
});
