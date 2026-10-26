/**
 * R16 m (M3): every chat-box placeholder is short — at most 60 characters and at most one example.
 * Long examples live in starter chips. Scans the component sources (Cockpit's frozen files excepted)
 * for placeholder literals and placeholder constants, and checks the What-If per-book placeholder.
 */

import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import { PLACEHOLDER_MAX, placeholderOk, whatIfPlaceholder, whatIfStarterChips } from "./placeholders.ts";
import { ASK_PLACEHOLDER } from "../../components/home/starters.ts";

const SRC = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");

/** The chat / ask boxes named in R15 M3; each must exist and hold at least one placeholder. */
const CHAT_BOXES = [
  "components/v5/whatif/home.tsx", "components/v5/whatif/thread.tsx",
  "components/v5/dealdesk/home.tsx", "components/v5/dealdesk/thread.tsx", "components/v5/dealdesk/desk-thread.tsx",
  "components/v5/lenses/home.tsx", "components/v5/lenses/assistant.tsx",
  "components/home/home-ask.tsx", "components/noor/noor-panel.tsx",
  "components/v5/ews/workspace.tsx", "components/v5/b360/workspace.tsx",
  "components/v5/scorecard/home.tsx", "components/v5/scorecard/thread.tsx",
  "components/v5/playbook/home.tsx", "components/v5/playbook/start-thread.tsx", "components/v5/playbook/report.tsx",
  "components/v5/policy/add-flow.tsx", "components/v5/brf/studio.tsx",
  "components/v5/workspace/project-scope.tsx", "components/v5/workspace/investigations.tsx",
  "components/v5/intel/network/event-panel.tsx", "components/v5/intel/governance/inspection-panel.tsx",
  "components/v5/admin/frame.tsx", "components/trace/modify-panel.tsx",
];

function walk(dir: string, out: string[] = []): string[] {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) { if (e.name !== "cockpit-v4" && e.name !== "node_modules") walk(p, out); }
    else if (/\.tsx?$/.test(e.name) && !/\.test\.tsx?$/.test(e.name)) out.push(p);
  }
  return out;
}

function skipString(src: string, j: number): number {
  const q = src[j]; let depth = 0;
  for (j++; j < src.length; j++) {
    const c = src[j];
    if (c === "\\") { j++; continue; }
    if (q === "`") {
      if (c === "$" && src[j + 1] === "{") { depth++; j++; continue; }
      if (c === "}" && depth > 0) { depth--; continue; }
    }
    if (c === q && depth === 0) return j + 1;
  }
  return j;
}

/** The expression after `placeholder=`, `placeholder={`, `placeholder: ` or `PLACEHOLDER = `. */
function expressionAfter(src: string, i: number, op: string): string {
  while (src[i] === " ") i++;
  if (op === "=" && (src[i] === '"' || src[i] === "'")) return src.slice(i, skipString(src, i));
  let depth = 0, j = i;
  for (; j < src.length; j++) {
    const c = src[j];
    if (c === '"' || c === "'" || c === "`") { j = skipString(src, j) - 1; continue; }
    if ("({[".includes(c)) depth++;
    else if (")}]".includes(c)) { if (depth === 0) break; depth--; }
    else if (depth === 0 && op !== "={") {
      if (c === "," || c === ";") break;
      if (c === "\n" && op !== ":") { const next = src.slice(j).match(/^\s*(.)/); if (!next || !"?:+|&".includes(next[1])) break; }
    }
  }
  return src.slice(i, j);
}

/** String literals in an expression; a template's `${…}` counts as ten characters. */
function literals(expr: string): string[] {
  const out: string[] = [];
  for (let j = 0; j < expr.length;) {
    const c = expr[j];
    if (c === '"' || c === "'" || c === "`") {
      const end = skipString(expr, j); let s = expr.slice(j + 1, end - 1);
      if (c === "`") s = s.replace(/\$\{[^}]*\}/g, "x".repeat(10));
      out.push(s); j = end;
    } else j++;
  }
  return out;
}

const PLACEHOLDER_RE = /\b([A-Za-z_]*[Pp]laceholder[A-Za-z_]*|PLACEHOLDER[A-Z_]*)\s*(=\{|=(?!=)|:(?=\s))/g;

function placeholdersIn(file: string): { line: number; text: string }[] {
  const src = fs.readFileSync(file, "utf8"); const found: { line: number; text: string }[] = [];
  for (const m of src.matchAll(PLACEHOLDER_RE)) {
    const line = src.slice(0, m.index).split("\n").length;
    for (const text of literals(expressionAfter(src, m.index! + m[0].length, m[2]))) found.push({ line, text });
  }
  return found;
}

test("every listed chat box exists and declares a placeholder", () => {
  for (const rel of CHAT_BOXES) {
    const file = path.join(SRC, rel);
    assert.ok(fs.existsSync(file), `${rel} is missing`);
    const src = fs.readFileSync(file, "utf8");
    assert.ok(/placeholder/i.test(src), `${rel} has no placeholder`);
  }
});

test("chat-box placeholders are at most 60 characters with one example", () => {
  const bad: string[] = [];
  for (const rel of CHAT_BOXES) {
    for (const { line, text } of placeholdersIn(path.join(SRC, rel))) {
      if (!placeholderOk(text)) bad.push(`${rel}:${line} [${text.length}] ${text}`);
    }
  }
  assert.deepEqual(bad, []);
});

test("no placeholder literal anywhere in the components and pages is longer than 60 characters", () => {
  const bad: string[] = [];
  const files = [...walk(path.join(SRC, "components")), ...walk(path.join(SRC, "app"))];
  assert.ok(files.length > 50);
  for (const file of files) {
    for (const { line, text } of placeholdersIn(file)) {
      if (!placeholderOk(text)) bad.push(`${path.relative(SRC, file)}:${line} [${text.length}] ${text}`);
    }
  }
  assert.deepEqual(bad, []);
});

test("the scanner catches a long placeholder in each form it reads", () => {
  const long = "Ask about the book, or describe a scenario: “reduce collateral by 20%”, “LGD +5pp”";
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "m3-"));
  try {
    const f = path.join(tmp, "x.tsx");
    fs.writeFileSync(f, [
      `<input placeholder="${long}" className="placeholder:text-text-muted h-8 w-full rounded-md border border-border" />`,
      `<Composer placeholder={busy ? "Short one" : \`${long}\`} />`,
      `const box = { placeholder: ok ? "fine"\n  : "${long}", rows: 2 };`,
      `const PLACEHOLDER = "${long}";`,
    ].join("\n"));
    const got = placeholdersIn(f).filter((p) => !placeholderOk(p.text)).map((p) => p.line);
    assert.deepEqual(got, [1, 2, 3, 5]);
  } finally { fs.rmSync(tmp, { recursive: true, force: true }); }
});

test("What-If placeholder is short for both books and before the book loads", () => {
  for (const book of ["Corporate", "Retail", undefined]) {
    const p = whatIfPlaceholder(book);
    assert.ok(p.length <= PLACEHOLDER_MAX, `${book}: ${p}`);
    assert.ok(placeholderOk(p), p);
    if (book) assert.match(p, new RegExp(book.toLowerCase()));
  }
});

test("the old long What-If example moves to a starter chip, once", () => {
  const corporate = ["oil price -40%", "increase PD by 30% for Construction", "downgrade by 2 notches", "LGD +5pp", "extra"];
  const chips = whatIfStarterChips(corporate);
  assert.deepEqual(chips, [...corporate.slice(0, 4), "reduce collateral by 20%"]);
  assert.deepEqual(whatIfStarterChips(["Reduce collateral by 20%"]), ["Reduce collateral by 20%"]);
  assert.deepEqual(whatIfStarterChips(undefined), ["reduce collateral by 20%"]);
});

test("Cockpit Ask placeholder (home starters) is short", () => {
  assert.ok(placeholderOk(ASK_PLACEHOLDER), ASK_PLACEHOLDER);
});
