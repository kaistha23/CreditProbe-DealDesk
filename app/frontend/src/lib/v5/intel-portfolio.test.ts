import assert from "node:assert/strict";
import { test } from "node:test";

import { type BridgeStep, barGeometry, bridgeAddsUp, kpiValue, lineageHref, pctOf, sarM, signedSar, toolPath, waterfall } from "./intel-portfolio.ts";

const steps: BridgeStep[] = [
  { key: "opening", label: "ECL run 2026Q3", value_sar_mn: 6993.7 },
  { key: "stage", label: "Stage moves", value_sar_mn: 764.6 },
  { key: "pd", label: "PD", value_sar_mn: 37.2 },
  { key: "lgd", label: "LGD", value_sar_mn: -10.0 },
  { key: "closing", label: "Forecast", value_sar_mn: 7785.5 },
];

test("waterfall floats steps on the running level and totals from zero", () => {
  const w = waterfall(steps);
  assert.equal(w[0].kind, "total");
  assert.equal(w[1].start, 6993.7);
  assert.ok(Math.abs(w[1].end - 7758.3) < 1e-9);
  assert.equal(w[3].kind, "down");
  assert.equal(w[4].kind, "total");
  assert.ok(bridgeAddsUp(steps));
  assert.ok(!bridgeAddsUp([...steps.slice(0, 4), { key: "closing", label: "x", value_sar_mn: 1 }]));
  for (const g of barGeometry(w)) assert.ok(g.left >= 0 && g.left + g.width <= 100.7, g.key);
});

test("words", () => {
  assert.equal(sarM(6993.7), "SAR 7.0bn");
  assert.equal(sarM(12.34), "SAR 12.3m");
  assert.equal(sarM(0.25), "SAR 250k");
  assert.equal(sarM(null), "—");
  assert.equal(signedSar(-3), "-SAR 3.0m");
  assert.equal(pctOf(0.1234), "12.3%");
  assert.equal(kpiValue({ key: "a", label: "A", value: 0.586, unit: "share", text: null }), "58.6%");
  assert.equal(kpiValue({ key: "a", label: "A", value: 2000, unit: "SAR m", text: null }), "SAR 2.0bn");
  assert.equal(kpiValue({ key: "a", label: "A", value: "Hold", unit: "text", text: null }), "Hold");
});

test("tool paths and lineage links", () => {
  assert.equal(toolPath("headroom", { level: "limit" }), "/api/v1/intel/portfolio/headroom?level=limit");
  assert.equal(toolPath("workout", { borrowerId: "CB00002" }), "/api/v1/intel/portfolio/workout/CB00002");
  assert.equal(toolPath("workout", { limit: 30 }), "/api/v1/intel/portfolio/workout?limit=30");
  assert.equal(toolPath("ecl_bridge"), "/api/v1/intel/portfolio/ecl-bridge");
  assert.equal(lineageHref({ domain: "collateral", relation: "col_crwa", path: null, period: "2026-06-30", rows: 1, columns: [] }),
    "/data-builder?domain=collateral&relation=col_crwa&period=2026-06-30");
  assert.equal(lineageHref({ domain: "expert_assumptions", relation: "x", path: null, period: null, rows: null, columns: [] }), null);
});
