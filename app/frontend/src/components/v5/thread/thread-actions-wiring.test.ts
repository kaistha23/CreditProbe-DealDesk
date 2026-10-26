/**
 * R16 t (M7): every module mounts the shared thread actions on its answers, and every chat routes "write a memo"
 * to the Word writer (a source scan: the components are .tsx, which node --test does not render).
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const src = (p: string) => readFileSync(new URL(`../../../${p}`, import.meta.url), "utf8");

const THREADS: [string, string, RegExp][] = [
  ["Deal Desk landing thread", "components/v5/dealdesk/desk-thread.tsx", /dealdeskSources\(/],
  ["Deal Desk proposal thread", "components/v5/dealdesk/thread.tsx", /dealdeskSources\(/],
  ["What-If", "components/v5/whatif/thread.tsx", /whatifSources\(/],
  ["Lenses", "components/v5/lenses/assistant.tsx", /convoSources\(/],
  ["Scorecard", "components/v5/scorecard/thread.tsx", /scorecardSources\(/],
  ["Playbook", "components/v5/playbook/start-thread.tsx", /playbookSources\(/],
];

for (const [name, file, sources] of THREADS) {
  test(`${name}: Share, Trace, Word, Add to report on every answer and the memo intent`, () => {
    const s = src(file);
    assert.match(s, /useThreadActions\(\{ module: "/, "creates the thread registry");
    assert.match(s, /<ThreadActionsProvider value=\{ta\}>/, "provides it to the answers");
    assert.match(s, /actions=\{\{ index: /, "each answer registers with its question");
    assert.match(s, sources, "with its module's sources");
    assert.match(s, /ta\.intercept\(q/, "a memo request is intercepted before it is asked");
    assert.match(s, /<MemoCards api=\{ta\}/, "and answered with the Word document");
  });
}

test("Noor: the bar on every answer turn and the memo intent", () => {
  const s = src("components/noor/noor-panel.tsx");
  assert.match(s, /<TurnActions /);
  assert.match(s, /noorSources\(/);
  assert.match(s, /ta\.intercept\(text/);
  assert.match(s, /<MemoCards api=\{ta\}/);
});

test("Cockpit: the bar through AnswerMailShare and the memo intent through FX-R16-T1", () => {
  assert.match(src("components/v5/attention/answer-share.tsx"), /<CockpitAnswerActions /);
  const tv = src("components/cockpit-v4/thread-view.tsx");
  assert.match(tv, /const memo = cockpitMemo\(question, threadId\);/);
  assert.match(tv, /<CockpitMemo threadId=\{threadId\} \/>/);
});

test("Panels: Early Warning, Borrower 360, intel panels, agent runs", () => {
  assert.match(src("components/v5/ews/workspace.tsx"), /<PanelActions module="ews"/);
  assert.match(src("components/v5/ews/customer-detail.tsx"), /<PanelActions module="ews"/);
  assert.match(src("components/v5/b360/workspace.tsx"), /<PanelActions module="b360"/);
  assert.match(src("components/v5/intel/intel-panel.tsx"), /<PanelActions module="intel"/);
  assert.match(src("components/v5/core/agent-run.tsx"), /<PanelActions module=\{agentModule\(run\.agent\)\}/);
  assert.match(src("components/v5/playbook/report.tsx"), /<PanelActions module="playbook"/);
  const sec = src("components/v5/playbook/ai-thread.tsx");
  assert.match(sec, /useThreadActions\(\{ module: "playbook"/);
  assert.match(sec, /ta\.intercept\(q, undefined, \{ writeOnly: true \}\)/);
});

test("AssistantTurn draws the bar when given actions; the bar has the four actions and plain words on its panels", () => {
  assert.match(src("components/v5/thread/thread-shell.tsx"), /\{children && actions \? <TurnActions /);
  const bar = src("components/v5/thread/action-bar.tsx");
  for (const id of ["-share`", "-trace`", "-word`", "-report`"]) assert.ok(bar.includes(id), id);
  for (const pw of ["thread-share-plain-words", "thread-trace-plain-words", "thread-memo-plain-words"]) assert.ok(bar.includes(pw), pw);
});

test("landings and Noor hand a memo request with its question to the new thread", () => {
  for (const f of ["components/noor/noor-dispatch.ts", "components/v5/whatif/home.tsx", "components/v5/lenses/home.tsx"]) {
    assert.match(src(f), /landingQuestion\(/, f);
    assert.match(src(f), /rememberPendingMemo\(/, f);
  }
  assert.match(src("components/home/home-ask.tsx"), /memoIntent\(q\)/);
  assert.match(src("components/v5/thread/action-bar.tsx"), /takePendingMemo\(module, threadId\)/);
  assert.match(src("components/v5/thread/cockpit-actions.tsx"), /takePendingMemo\("cockpit", threadId\)/);
});
