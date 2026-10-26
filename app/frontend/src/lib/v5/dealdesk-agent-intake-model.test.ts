import { test } from "node:test";
import assert from "node:assert/strict";

import {
  type AgentCheck, type AgentDoc, citeTitle, gapLine, inline, isAccepted, isLive, mergeFiles, meter, parseMd, readCounts, secs, wordCount,
} from "./dealdesk-agent-intake-model.ts";

const check = (over: Partial<AgentCheck> = {}): AgentCheck => ({
  received: [], missing: [], expired: [], total: 24, lines: [], comp: { pct: 35, gaps: [], crit: 2 },
  prev_pct: null, delta_pts: null, prev_crit: null, now_covered: [], ...over,
});

test("meter: the first run shows the score; a re-run shows 20% → 35% (+15) and the critical count before and after", () => {
  assert.equal(meter(check()).title, "Completeness 35%");
  const m = meter(check({ prev_pct: 20, delta_pts: 15, prev_crit: 4 }));
  assert.equal(m.title, "Completeness 20% → 35% (+15)");
  assert.equal(m.crit, "4 → 2 critical gaps");
  assert.equal(m.band, "lo");
  assert.equal(meter(check({ comp: { pct: 85, gaps: [], crit: 1 } })).band, "hi");
  assert.equal(meter(check({ comp: { pct: 60, gaps: [], crit: 1 } })).crit, "1 critical gap");
  assert.equal(meter(check({ prev_pct: 35, delta_pts: 0 })).title, "Completeness 35%");
});

test("gap lines name the analysis, the blocking document and the section; critical first word", () => {
  const g = { sec: "4", item: "x", cannot: "Show exposure with other banks", w: 3, crit: true, because: "SIMAH report, company missing", blocking: ["SIMAH report, company"], partial: false };
  assert.equal(gapLine(g), "Critical: Show exposure with other banks — SIMAH report, company missing. [Section 4]");
  assert.equal(gapLine({ ...g, partial: true }), "Show exposure with other banks (only in part) — SIMAH report, company missing. [Section 4]");
});

test("the paper: headings, the completeness line, the gaps block, tables and bullets", () => {
  const md = [
    "# Business Request — Saqr Al Wadi Contracting Co.", "", "| Item | Detail |", "|---|---|", "| Customer and CR | Saqr [D2] |", "",
    "**Completeness: 82%** of the evidence a full request rests on; 0 critical gaps.", "",
    "## What this request could not assess", "The documents on file did not allow me to do the following.", "", "- Value the collateral — missing. [Section 3]", "",
    "## 1. Action requested", "Credit is asked to approve [Ask].", "", "## 6. Financials", "| SAR m | FY2025 [D3] |", "|---|---|", "| Revenue | 214.9 |",
    "- EBITDA margin [figure removed] [D3].",
  ].join("\n");
  const b = parseMd(md);
  assert.deepEqual(b.map((x) => x.t), ["h1", "table", "p", "h2", "p", "ul", "h2", "p", "h2", "table", "ul"]);
  assert.equal(b[2].t === "p" && b[2].completeness, true);
  assert.equal(b[3].t === "h2" && b[3].gaps, true);
  assert.equal(b[5].t === "ul" && b[5].inGaps, true);
  assert.equal(b[7].t === "p" && b[7].inGaps, false);
  const t = b[9];
  assert.ok(t.t === "table" && t.header[1] === "FY2025 [D3]" && t.rows[0][1] === "214.9");
});

test("inline: bold, citations and removed figures are separate segments", () => {
  assert.deepEqual(inline("**Completeness: 82%** of it [D3, RM] and [figure removed] [Ask]").map((s) => s.t),
                   ["bold", "text", "cite", "text", "removed", "text", "cite"]);
  assert.deepEqual(inline("plain [Section 4]"), [{ t: "text", text: "plain [Section 4]" }]);
});

test("words exclude citations; files and runs", () => {
  assert.equal(wordCount("## 1. Action\nRevenue SAR 214.9m [D3] rose."), 6);
  assert.ok(isAccepted("pack.ZIP") && isAccepted("a.xlsx") && isAccepted("scan.jpeg") && !isAccepted("x.exe"));
  assert.ok(isLive({ status: "running" }) && isLive({ status: "revising" }) && !isLive({ status: "done" }) && !isLive(null));
  assert.equal(secs(12345), "12.3s");
  assert.equal(secs(null), "");
  const m = mergeFiles([{ name: "a.pdf", size: 1 }], [{ name: "a.pdf", size: 1 }, { name: "b.pdf", size: 2 }]);
  assert.equal(m.files.length, 2);
  assert.equal(m.dup, 1);
});

test("read counts and citation titles", () => {
  const docs = [
    { id: "D1", name: "01 Letter.docx", status: "read", recon: { status: "confirmed" } },
    { id: "D2", name: "02 CR.jpg", status: "read", recon: { status: "flagged" } },
    { id: "D3", name: "x", status: "failed", recon: null },
  ] as unknown as AgentDoc[];
  assert.deepEqual(readCounts(docs), { confirmed: 1, offered: 0, flagged: 1, rule: 0, failed: 1 });
  assert.equal(citeTitle("[D2, RM]", docs), "D2 · 02 CR.jpg; RM notes");
});
