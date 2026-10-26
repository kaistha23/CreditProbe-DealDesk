/** R16 t (M7): the thread actions, one test per module, and the memo intent (shared case list with the backend). */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import {
  type ActionDoc, type ActionTurn, type DomLike, type ModuleKey, MODULE_LABEL,
  answerDoc, b360Sources, cockpitSources, composeDoc, convoSources, dealdeskSources, domBlocks, ewsSources, intelSources,
  cockpitBlocks, keyedTable, relationsInText, traceSources, memoIntent, memoPlainWords, memoReply, noorSources, planMemo, playbookSources, scorecardSources, shareObject,
  sharePlainWords, textBlocks, toPlaybookBlocks, whatifSources, withoutOfferEnding,
} from "./thread-actions.ts";

const CASES = JSON.parse(readFileSync(new URL("../../../../tests/v5/thread_actions/intent_cases.json", import.meta.url), "utf8")).cases as
  { text: string; expect: null | Record<string, unknown> }[];

test("memo intent: the shared case list (same rule as backend/thread_actions/intent.py)", () => {
  for (const c of CASES) {
    const got = memoIntent(c.text);
    if (c.expect === null) { assert.equal(got, null, c.text); continue; }
    assert.ok(got, c.text);
    for (const [k, v] of Object.entries(c.expect)) assert.deepEqual((got as unknown as Record<string, unknown>)[k], v, `${c.text}: ${k}`);
  }
});

test("planMemo: write now, ask first, or say there is nothing yet; never prose", () => {
  assert.deepEqual(planMemo("which proposals breach a hard limit", 2), { action: "none" });
  assert.equal(planMemo("prepare a memo", 1).action, "write");
  const e = planMemo("prepare a memo", 0);
  assert.equal(e.action, "empty");
  assert.ok(e.action === "empty" && !/say the word/i.test(e.message));
  const a = planMemo("prepare a memo on which proposals breach a hard limit", 0);
  assert.equal(a.action, "ask-then-write");
  assert.ok(a.action === "ask-then-write" && a.question === "Which proposals breach a hard limit?");
});

test("no 'say the word and I'll…' endings", () => {
  assert.equal(withoutOfferEnding("Three proposals breach a hard limit. Say the word and I'll prepare a memo."), "Three proposals breach a hard limit.");
  assert.equal(withoutOfferEnding("ECL is up 4%. Want me to draft a note for the CRO?"), "ECL is up 4%.");
  assert.equal(withoutOfferEnding("ECL is up 4%.\nLet me know if you'd like a Word version."), "ECL is up 4%.");
  assert.equal(withoutOfferEnding("Nothing to remove here."), "Nothing to remove here.");
});

// ------------------------------------------------------------------ a fake DOM

function el(tagName: string, kids: (DomLike | string)[] = [], attrs: Record<string, string> = {}): DomLike {
  const children = kids.map((k) => (typeof k === "string" ? el("#text", [], { __text: k }) : k));
  const own = attrs.__text;
  return {
    tagName, children: own !== undefined ? [] : children,
    get textContent() { return own !== undefined ? own : children.map((c) => c.textContent ?? "").join(" "); },
    getAttribute: (n: string) => (n in attrs && n !== "__text" ? attrs[n] : null),
  };
}
const answerDom = () => el("DIV", [
  el("BUTTON", ["Listen"], { "data-testid": "answer-speaker" }),
  el("H3", ["Hard limits"]),
  el("P", ["Three proposals breach a hard limit."]),
  el("UL", [el("LI", ["Fictional Trading Co: single obligor"]), el("LI", ["Sahra Contracting: sector"])]),
  el("TABLE", [el("THEAD", [el("TR", [el("TH", ["Deal"]), el("TH", ["Exposure SAR m"])])]),
               el("TBODY", [el("TR", [el("TD", ["DD-01"]), el("TD", ["120.5"])]), el("TR", [el("TD", ["DD-07"]), el("TD", ["88.0"])])])]),
  el("DIV", [el("BUTTON", ["Share"])], { "data-thread-actions": "" }),
  el("P", ["Say the word and I'll prepare a memo."]),
]);

test("domBlocks reads the answer as shown: headings, text, lists, tables; skips buttons, the bar and the offer", () => {
  const b = domBlocks(answerDom());
  assert.deepEqual(b.map((x) => x.kind), ["text", "bullets", "table"]);
  assert.ok(b[0].kind === "text" && b[0].text.includes("### Hard limits") && b[0].text.includes("Three proposals"));
  assert.ok(b[2].kind === "table" && b[2].columns.join("|") === "Deal|Exposure SAR m" && b[2].rows.length === 2 && b[2].title === "Hard limits");
  assert.ok(!JSON.stringify(b).includes("Listen") && !JSON.stringify(b).includes("Share") && !/say the word/i.test(JSON.stringify(b)));
});

// ------------------------------------------------------------------ one test per module

const turn = (q: string, sources: ActionTurn["sources"], i = 1): ActionTurn => ({ question: q, answer_id: `a${i}`, blocks: domBlocks(answerDom()), sources });

function checkModule(module: ModuleKey, doc: ActionDoc, expectSource: (d: ActionDoc) => boolean) {
  assert.equal(doc.module, module);
  assert.ok(doc.turns.length >= 1 && doc.turns[0].blocks.length >= 1, `${module}: blocks`);
  assert.ok(expectSource(doc), `${module}: sources`);
  const one = answerDoc(doc, doc.turns.length - 1);
  assert.equal(one.turns.length, 1);
  const pb = toPlaybookBlocks(doc);
  assert.ok(pb.length >= 3 && pb.length <= 60 && pb.some((x) => x.kind === "table"), `${module}: report blocks`);
  for (const x of pb) if (x.kind === "table") assert.ok(x.columns.every((c) => c.key && c.label) && x.rows.every((r) => typeof r === "object"));
  const so = shareObject(doc, "answer", one.turns[0].answer_id);
  assert.equal(so.type, "thread-answer");
  assert.ok(so.href.startsWith("/") && so.id.startsWith(`${module}:`) && so.label.startsWith(MODULE_LABEL[module]));
  assert.equal(sharePlainWords(doc, "thread").length, 3);
}

test("Deal Desk: deal row, figure check and engine runs", () => {
  const s = dealdeskSources({ trace_ids: ["T1", "T2"], validation: { checked: 12, untraced: [], passed: true }, intent: "screen" }, "DD-01");
  checkModule("dealdesk", composeDoc("dealdesk", "desk-1", "Which proposals breach a hard limit", "/deal-desk/thread/desk-1", [turn("Which proposals breach a hard limit", s)]),
              (d) => d.turns[0].sources.some((x) => x.relation === "dd_deal" && x.keys?.proposal_id === "DD-01") && d.turns[0].sources.filter((x) => x.kind === "run").length === 2);
});

test("What-If: evidence SQL, scenario relations and the book", () => {
  const s = whatifSources({ evidence: [{ sql: "select * from corp_borrower_quarter", purpose: "Book", row_count: 10 }],
                            blocks: [{ type: "scenario_set", relations: ["dd_scenario_result", "whatif_mev_annual"], as_of: "2026Q2", engine_version: "s1", fingerprint: "f" },
                                     { type: "result", result: { domain: "corporate", period: "2026-08" } }] as unknown as { type: string }[] });
  checkModule("whatif", composeDoc("whatif", "wi-1", "Construction stress", "/what-if/thread/wi-1", [turn("Construction stress", s)]),
              (d) => d.turns[0].sources.some((x) => x.sql) && d.turns[0].sources.some((x) => x.relation === "dd_scenario_result"));
});

test("Lenses: convo evidence", () => {
  const s = convoSources({ evidence: [{ sql: "select quarter, ecl from ecl_runs", purpose: "ECL trend", row_count: 8 }] });
  checkModule("lenses", composeDoc("lenses", "ln-1", "CRO dashboard", "/lenses/L1", [turn("CRO dashboard", s)]), (d) => d.turns[0].sources[0].kind === "query");
});

test("Scorecard: evidence, validation and scorecard", () => {
  const s = scorecardSources({ evidence: [], blocks: [{ type: "validation", validation_id: "V-9" }] as unknown as { type: string }[] }, "SME-1");
  checkModule("scorecard", composeDoc("scorecard", "sc-1", "Validate the SME scorecard", "/scorecard/thread/sc-1", [turn("Validate", s)]),
              (d) => d.turns[0].sources.some((x) => x.keys?.validation_id === "V-9"));
});

test("Playbook: citations as documents", () => {
  const s = playbookSources([{ citations: [{ kind: "policy", label: "Credit policy §4.2", doc_id: "P-42", href: "/policy/P-42" }], source: "deterministic" }]);
  checkModule("playbook", composeDoc("playbook", "pb-1", "Draft", "/playbook", [turn("Draft", s)]), (d) => d.turns[0].sources.some((x) => x.kind === "document" && x.keys?.doc_id === "P-42"));
});

test("Noor: Data Domains trace stamps as rows", () => {
  const s = noorSources([{ domain: "deal_desk", relation: "dd_deal", keys: { proposal_id: "DD-01" }, period: "2026Q2", status: "ok" }]);
  checkModule("noor", composeDoc("noor", "noor-1", "Why is ECL up", "/", [turn("Why is ECL up", s)]), (d) => d.turns[0].sources[0].relation === "dd_deal" && d.turns[0].sources[0].keys?.proposal_id === "DD-01");
});

test("Cockpit: SQL from the run trace and the numeric claims' rows", () => {
  const s = cockpitSources([{ type: "query", payload: { sql: "SELECT sector FROM corp_borrower_quarter", purpose: "Stage 2", row_count: 12 } }],
                           [{ evidence: { artifact_id: "A1", row_key: "r1", column_id: "ead" } }, { evidence: { artifact_id: "A1", row_key: "r1", column_id: "ead" } }]);
  assert.equal(s.length, 2);
  checkModule("cockpit", composeDoc("cockpit", "th-c1", "Stage 2 by sector", "/cockpit/thread/th-c1", [turn("Stage 2 by sector", s)]), (d) => d.turns[0].sources.some((x) => x.sql));
});

test("Early Warning: the list's relations", () => {
  checkModule("ews", composeDoc("ews", "construction-warned", "Construction · Warned", "/early-warning", [turn("Construction · Warned", ewsSources({ id: "construction-warned" }))]),
              (d) => d.turns[0].sources[0].relation === "corp_exposure");
  assert.equal(ewsSources({ domain: "retail" })[0].relation, "retail_exposure");
});

test("Borrower 360: the borrower's rows", () => {
  checkModule("b360", composeDoc("b360", "CB0001", "Borrower 360", "/borrower-360/CB0001", [turn("Borrower 360", b360Sources("CB0001"))]),
              (d) => d.turns[0].sources[0].keys?.borrower_id === "CB0001");
});

test("Intel panels: the engine and the named deal", () => {
  const s = intelSources({ route: { key: "renewals", label: "Renewals", home: "/intel/renewals" }, deal: "DD-03" });
  checkModule("intel", composeDoc("intel", "renewals", "Renewals due", "/?intel=renewals", [turn("Renewals due", s)]), (d) => d.turns[0].sources.some((x) => x.keys?.proposal_id === "DD-03"));
});

test("Agents (Early Warning triage): a run document", () => {
  checkModule("agents", composeDoc("agents", "run-1", "Triage", "/early-warning", [turn("Triage", [{ kind: "run", label: "Agent run run-1" }])]), (d) => d.turns[0].sources[0].kind === "run");
});

test("whole thread vs one answer; text and keyed tables", () => {
  const d = composeDoc("whatif", "wi-2", "", "/w", [turn("Q1", [], 1), { question: "Q2", answer_id: "a2", blocks: textBlocks("Second answer."), sources: [] }]);
  assert.equal(d.title, "Q1");
  assert.equal(answerDoc(d, 1).turns[0].question, "Q2");
  const t = keyedTable("T", [{ key: "a", label: "A" }, { key: "b", label: "B" }], [{ a: 1, b: true }, { a: null, b: "x" }]);
  assert.ok(t.kind === "table" && t.rows[0][1] === "Yes" && t.rows[1][0] === "");
  const pb = toPlaybookBlocks(d);
  assert.ok(pb.some((x) => x.kind === "heading" && x.text === "Q2"));
});

test("memo card words and reply never offer: the document is written", () => {
  const r = { memo_id: "TM-20261021-abcdef", kind: "memo" as const, scope: "thread" as const, title: "Hard limits", addressee: "CRO", file_name: "Memo - Hard limits.docx",
              href: "/api/v1/thread-actions/memos/TM-20261021-abcdef.docx", bytes: 40960, answers: 2, tables: 1, sources: 3, recorded: true, plain_words: [], module_label: "Deal Desk" };
  const w = memoPlainWords(r);
  assert.equal(w.length, 3);
  assert.ok(w[0].includes("to the CRO") && w[1].includes("2 answers"));
  assert.equal(memoReply(r), "Memo written: Memo - Hard limits.docx (40 KB).");
});

test("Cockpit transcript turns: narrative and published tables; run operations as engine steps", () => {
  const b = cockpitBlocks({ narrative: "Construction leads Stage 2. Shall I draft a note for the CRO?",
                            tables: [{ title: "Stage 2 by sector", columns: ["Sector", "EAD"], rows: [{ display: { Sector: "Construction", EAD: "1,204.5" } }], row_count: 9 }] });
  assert.ok(b[0].kind === "text" && b[0].text === "Construction leads Stage 2.");
  assert.ok(b[1].kind === "table" && b[1].rows[0][0] === "Construction" && b[1].row_count === 9);
  const s = cockpitSources([{ stage: "executing", operation: "run_query", status: "ok", public_message: "Read the corporate book" },
                            { stage: "executing", operation: "run_query", status: "ok", public_message: "again" }],
                           [], [{ title: "Stage 2 by sector", artifact_id: "ART-1", row_count: 9 }]);
  assert.deepEqual(s.map((x) => x.kind), ["engine", "run"]);
});

test("domBlocks reads a panel whose root is a dialog (agent drawer)", () => {
  const root = el("ASIDE", [el("P", ["Agent answer: 8 names move to SICR."])], { role: "dialog" });
  const b = domBlocks(root);
  assert.equal(b.length, 1);
});

test("Deal Desk tables name their deals; the process trace names its relations", () => {
  const s = dealdeskSources({ blocks: [{ type: "table", keys: ["proposal_id", "obligor"], rows: [["DD-03", "A"], ["DD-05", "B"], ["x", "C"]] }] as unknown as { type: string }[] });
  assert.deepEqual(s.filter((x) => x.relation === "dd_deal").map((x) => x.keys?.proposal_id), ["DD-03", "DD-05"]);
  assert.deepEqual(relationsInText("read dd_deal and corp_borrower_quarter, then dd_deal"), ["dd_deal", "corp_borrower_quarter"]);
  const t = traceSources({ steps: [{ label: "Query", detail: "dd_policy_clause: 12 rows", state: "done" }, { label: "Plan", detail: "" }] });
  assert.deepEqual(t.map((x) => x.kind), ["engine", "relation"]);
});

test("a placeholder thread title gives way to the first question", () => {
  assert.equal(composeDoc("whatif", "w", "New What-If thread", "/", [{ question: "ECL of construction?", answer_id: "a", blocks: textBlocks("x"), sources: [] }]).title, "ECL of construction?");
  assert.equal(composeDoc("whatif", "w", "Construction stress", "/", [{ question: "Q", answer_id: "a", blocks: textBlocks("x"), sources: [] }]).title, "Construction stress");
});

test("a line with buttons inside reads as its words (browser child nodes)", () => {
  const txtNode = (v: string) => ({ nodeType: 3, nodeValue: v });
  const btn = el("BUTTON", ["Why"]);
  const meta = { ...el("DIV", ["Regulatory checks · 2026Q2"]), nodeType: 1, childNodes: [txtNode("Regulatory checks · 2026Q2")] };
  const strong = { ...el("STRONG", ["878.5m"]), nodeType: 1, childNodes: [txtNode("878.5m")] };
  const li = { ...el("LI", []), nodeType: 1, childNodes: [txtNode("Stage 3 provision short by SAR "), strong, txtNode("."), meta, { ...btn, nodeType: 1 }] };
  const root = el("UL", [li as unknown as DomLike]);
  const b = domBlocks(el("DIV", [root]));
  assert.ok(b[0].kind === "bullets" && b[0].items[0] === "Stage 3 provision short by SAR 878.5m. Regulatory checks · 2026Q2", JSON.stringify(b));
});

test("landing question: a memo request with its question asks the question; the request waits for the thread", async () => {
  const { landingQuestion, rememberPendingMemo, takePendingMemo } = await import("./thread-actions-pending.ts");
  assert.deepEqual(landingQuestion("prepare a memo on which proposals breach a hard limit"),
                   { ask: "Which proposals breach a hard limit?", memo: "prepare a memo on which proposals breach a hard limit" });
  assert.deepEqual(landingQuestion("which proposals breach a hard limit"), { ask: "which proposals breach a hard limit", memo: null });
  const store = new Map<string, string>();
  (globalThis as unknown as { window: unknown }).window = { sessionStorage: {
    getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => { store.set(k, v); }, removeItem: (k: string) => { store.delete(k); } } };
  rememberPendingMemo("whatif", "T1", "write a note on X Y");
  assert.equal(takePendingMemo("whatif", "T1"), "write a note on X Y");
  assert.equal(takePendingMemo("whatif", "T1"), null);
  delete (globalThis as unknown as { window?: unknown }).window;
});

test("a thread titled by a memo request is titled by its subject", () => {
  assert.equal(composeDoc("dealdesk", "d", "prepare a memo on which proposals breach a hard limit", "/", [{ question: "Q", answer_id: "a", blocks: textBlocks("x"), sources: [] }]).title,
               "Which proposals breach a hard limit");
});
