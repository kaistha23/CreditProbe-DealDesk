/**
 * R16 n: Listen on every answer in every module (a source scan: the components are .tsx, which node --test does not
 * render; the production-build walk `ops/r16_n_walk.py` clicks it in each module).
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const src = (p: string) => readFileSync(new URL(`../../../${p}`, import.meta.url), "utf8");

test("the shared bar draws Listen first, on the answer it sits under", () => {
  const s = src("components/v5/thread/action-bar.tsx");
  assert.match(s, /<ListenButton module=\{module\} question=\{question \?\? ""\} getEl=\{answerEl\}/);
  assert.match(s, /getEl=\{\(\) => bodyRef\.current\}/, "a chat turn narrates its own body");
  assert.match(src("components/v5/thread/panel-actions.tsx"), /question=\{question \|\| title\} getEl=\{panelEl\} nearby/, "a panel narrates the panel");
  assert.match(src("components/v5/thread/cockpit-actions.tsx"), /getEl=\{\(\) => anchor\.current\?\.closest\('\[data-testid="v4-turn-assistant"\]'\)/, "a Cockpit answer narrates the turn");
});

const MODULES: [string, string, RegExp][] = [
  ["Cockpit Ask", "components/v5/attention/answer-share.tsx", /<CockpitAnswerActions /],
  ["Noor panel", "components/noor/noor-panel.tsx", /<TurnActions /],
  ["Deal Desk landing", "components/v5/dealdesk/desk-thread.tsx", /actions=\{\{ index: /],
  ["Deal Desk proposal", "components/v5/dealdesk/thread.tsx", /actions=\{\{ index: /],
  ["What-If", "components/v5/whatif/thread.tsx", /actions=\{\{ index: /],
  ["Lenses", "components/v5/lenses/assistant.tsx", /actions=\{\{ index: /],
  ["Scorecard", "components/v5/scorecard/thread.tsx", /actions=\{\{ index: /],
  ["Playbook", "components/v5/playbook/start-thread.tsx", /actions=\{\{ index: /],
  ["Early Warning", "components/v5/ews/workspace.tsx", /<PanelActions module="ews"/],
  ["Early Warning customer", "components/v5/ews/customer-detail.tsx", /<PanelActions module="ews"/],
  ["Borrower 360", "components/v5/b360/workspace.tsx", /<PanelActions module="b360"/],
  ["Intelligence panels", "components/v5/intel/intel-panel.tsx", /<PanelActions module="intel"/],
  ["Agent result pages", "components/v5/core/agent-run.tsx", /<PanelActions module=\{agentModule\(run\.agent\)\}/],
];
for (const [name, file, rx] of MODULES) {
  test(`${name}: every answer carries the shared bar, so Listen`, () => assert.match(src(file), rx));
}

test("nothing plays unless clicked (M1); a second click stops; no voice chosen, no sound", () => {
  const s = src("components/v5/thread/listen.tsx");
  const calls = s.split("speakText(").length - 1;
  assert.equal(calls, 1, "one call to speakText");
  const at = s.indexOf("speakText(seg.text");
  assert.ok(at > s.indexOf("const click = async () =>"), "inside the click handler");
  assert.ok(!/useEffect\([^)]*speak/.test(s) && !/setInterval|\.autoplay|autoPlay/.test(s), "no effect, timer or autoplay speaks");
  assert.match(s, /if \(state === "playing" && current\?\.id === mine\.current\) \{ current\.stop\(\); return; \}/);
  assert.match(s, /if \(!choice\) \{ setNote\(CHOOSE_VOICE_NOTE\); return; \}/);
  assert.match(s, /chosenVoiceFor\(lang\)/, "the reader's chosen voice for the answer's language");
});

test("the pulse is styled", () => {
  const css = src("app/globals.css");
  assert.match(css, /@keyframes cp-narrate-pulse/);
  assert.match(css, /tr\.cp-narrate-pulse/);
});
