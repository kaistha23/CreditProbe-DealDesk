/**
 * R14 G (K34) acceptance: every More / Tools / Governance / Network / Portfolio panel and Who to call renders the
 * "In plain words" block, written by its deterministic writer from the panel's own result, naming at least one number.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { checkPlainWords } from "../../../components/v5/ui/plain-words-model.ts";
import { writeCalls, writeEclBridge, writeExits, writeHeadroom, writeRenewals, writeRwa, writeWorkout } from "./book.ts";
import { writeCovenants } from "./covenants.ts";
import {
  writeChallenger, writeCommitteePaper, writeConsistency, writeDocuments, writeFinQuality, writeGroup, writeReverse, writeSwot,
  writeTryDocs, writeWriteProposal,
} from "./deal.ts";
import { writeDoa, writeExceptions, writeRmTrack } from "./governance.ts";
import { writeInspection, writeInspectionEmpty } from "./inspection.ts";
import { writeContagion, writeEmployer, writeEmployerRanking, writeEvent } from "./network.ts";
import { writeSecurity } from "./security.ts";

const fx = (n: string) => JSON.parse(readFileSync(new URL(`./fixtures/${n}.json`, import.meta.url), "utf8"));
const src = (p: string) => readFileSync(new URL(`../../../components/${p}`, import.meta.url), "utf8");

type W = (d: never) => string[];
/** menu → panel (block key) → component file → writer → fixture */
const PANELS: { menu: string; label: string; key: string; file: string; write: W; fixture: string }[] = [
  { menu: "Deal · More", label: "Documents", key: "documents", file: "v5/dealdesk/documents-panel.tsx", write: writeDocuments as W, fixture: "docs-DD-06" },
  { menu: "Deal · More", label: "Group", key: "group", file: "v5/dealdesk/group/group-panel.tsx", write: writeGroup as W, fixture: "group-DD-06" },
  { menu: "Deal · More", label: "SWOT", key: "swot", file: "v5/dealdesk/group/swot-panel.tsx", write: ((d: { swot: never }) => writeSwot(d.swot)) as W, fixture: "group-DD-06" },
  { menu: "Deal · More", label: "Write proposal", key: "write", file: "v5/dealdesk/papers/write-proposal-dialog.tsx", write: writeWriteProposal as W, fixture: "paper-DD-06" },
  { menu: "Deal · More", label: "Committee paper", key: "committee", file: "v5/dealdesk/papers/committee-paper-dialog.tsx", write: writeCommitteePaper as W, fixture: "committee-DD-06" },
  { menu: "Deal · More", label: "Try it on your documents", key: "try", file: "v5/dealdesk/try-docs/try-docs-run.tsx", write: ((o: never) => writeTryDocs({ overview: o })) as W, fixture: "trydocs-overview" },
  { menu: "Deal · More", label: "Financial quality", key: "fin-quality", file: "v5/dealdesk/fin-quality/panel.tsx", write: writeFinQuality as W, fixture: "finq-DD-06" },
  { menu: "Deal · More", label: "Committee questions", key: "challenger", file: "v5/dealdesk/intel/approval/challenger-panel.tsx", write: writeChallenger as W, fixture: "challenger-DD-06" },
  { menu: "Deal · More", label: "Make it approvable", key: "reverse", file: "v5/dealdesk/intel/approval/reverse-panel.tsx", write: writeReverse as W, fixture: "reverse-DD-06" },
  { menu: "Deal · More", label: "Security value", key: "security", file: "v5/dealdesk/intel/approval/security-panel.tsx", write: writeSecurity as W, fixture: "security" },
  { menu: "Deal · More", label: "Decision consistency", key: "consistency", file: "v5/dealdesk/intel/approval/consistency-panel.tsx", write: writeConsistency as W, fixture: "consistency-DD-06" },
  { menu: "Deal · More", label: "Covenant designer", key: "covenants", file: "v5/intel/ib/covenant-designer-panel.tsx", write: writeCovenants as W, fixture: "covenants" },
  { menu: "Book · Tools", label: "Renewal autopilot", key: "renewals", file: "v5/intel/ib/renewal-autopilot-panel.tsx", write: writeRenewals as W, fixture: "renewals" },
  { menu: "Portfolio tools", label: "Growth headroom", key: "headroom", file: "v5/intel/portfolio/headroom-panel.tsx", write: writeHeadroom as W, fixture: "headroom" },
  { menu: "Portfolio tools", label: "Exit and sell-down", key: "exits", file: "v5/intel/portfolio/exits-panel.tsx", write: writeExits as W, fixture: "exits" },
  { menu: "Portfolio tools", label: "RWA finder", key: "rwa", file: "v5/intel/portfolio/rwa-panel.tsx", write: writeRwa as W, fixture: "rwa" },
  { menu: "Portfolio tools", label: "ECL bridge forecast", key: "ecl-bridge", file: "v5/intel/portfolio/ecl-bridge-panel.tsx", write: writeEclBridge as W, fixture: "ecl-bridge" },
  { menu: "Portfolio tools", label: "Workout optimiser", key: "workout", file: "v5/intel/portfolio/workout-panel.tsx", write: writeWorkout as W, fixture: "workout" },
  { menu: "Early Warning · Tools", label: "Who to call", key: "who-to-call", file: "v5/intel/ib/who-to-call-panel.tsx", write: writeCalls as W, fixture: "calls" },
  { menu: "Governance", label: "Inspection responder", key: "inspection", file: "v5/intel/governance/inspection-panel.tsx", write: writeInspection as W, fixture: "inspection" },
  { menu: "Governance", label: "Exception intelligence", key: "exceptions", file: "v5/intel/governance/exception-panel.tsx", write: writeExceptions as W, fixture: "gov-exceptions" },
  { menu: "Governance", label: "RM track record", key: "rm-track", file: "v5/intel/governance/rm-track-panel.tsx", write: writeRmTrack as W, fixture: "gov-rm-track" },
  { menu: "Governance", label: "DoA calibration", key: "doa", file: "v5/intel/governance/doa-panel.tsx", write: writeDoa as W, fixture: "gov-doa" },
  { menu: "Network tools", label: "Contagion map", key: "contagion", file: "v5/intel/network/contagion-panel.tsx", write: writeContagion as W, fixture: "net-contagion" },
  { menu: "Network tools", label: "Employer exposure", key: "employer", file: "v5/intel/network/employer-panel.tsx", write: writeEmployer as W, fixture: "net-employer" },
  { menu: "Network tools", label: "Employer ranking", key: "employers", file: "v5/intel/network/employer-panel.tsx", write: writeEmployerRanking as W, fixture: "net-employers" },
  { menu: "Network tools", label: "Event translator", key: "event", file: "v5/intel/network/event-panel.tsx", write: writeEvent as W, fixture: "net-event" },
];

for (const p of PANELS) {
  test(`${p.menu} → ${p.label}: renders the plain-words block with a number`, () => {
    assert.ok(src(p.file).includes(`<PanelWords panel="${p.key}"`), `${p.file} does not render the block`);
    const l = p.write(fx(p.fixture) as never);
    const c = checkPlainWords(l);
    assert.ok(c.ok, `${c.problems.join("; ")} :: ${l.join(" | ")}`);
    assert.ok(l.length >= 3 && l.length <= 4, `${l.length} lines`);
    assert.ok(/\d/.test(l.join(" ")));
    assert.ok(!/\bn\/a\b/.test(l.join(" ")), "a figure is missing");
    assert.deepEqual(p.write(fx(p.fixture) as never), l);
  });
}

test("the inspection responder's empty state explains itself", () => {
  assert.ok(checkPlainWords(writeInspectionEmpty(3)).ok);
});

test("every panel the writers know is in the list", () => {
  assert.equal(new Set(PANELS.map((p) => p.key)).size, PANELS.length);
  assert.ok(PANELS.length >= 27);
});

test("the event translator's empty state explains itself", async () => {
  const { writeEventEmpty } = await import("./network.ts");
  assert.ok(checkPlainWords(writeEventEmpty(4)).ok);
  assert.ok(src("v5/intel/network/event-panel.tsx").includes('<PanelWords panel="event-empty"'));
});
