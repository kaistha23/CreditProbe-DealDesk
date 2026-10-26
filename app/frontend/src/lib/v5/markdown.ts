/**
 * PLAN_R5 P2: the light markdown an assistant writes, as parts a screen can render properly.
 *
 * Paragraphs, headings (`#`), quotes (`>`, shown without their markers), bullet and numbered lists, and pipe
 * tables, which become real house-style tables: never raw pipes. Pure, so the node tests can run it.
 */

import { orderRatingTable } from "./ratings.ts";

export type MdPart =
  | { type: "paragraph"; text: string }
  | { type: "heading"; level: number; text: string }
  | { type: "quote"; paragraphs: string[] }
  | { type: "list"; ordered: boolean; items: string[] }
  | { type: "table"; header: string[]; rows: string[][] };

const TABLE_ROW = /^\s*\|.*\|\s*$/;
const TABLE_RULE = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/;
const HEADING = /^\s*(#{1,6})\s+(.+?)\s*#*\s*$/;
const QUOTE = /^\s*>\s?(.*)$/;
const LIST = /^\s*([-*•]|\d+[.)])\s+(.+)$/;

function cells(line: string): string[] {
  let s = line.trim();
  if (s.startsWith("|")) s = s.slice(1);
  if (s.endsWith("|")) s = s.slice(0, -1);
  return s.split("|").map((c) => c.trim());
}

function isLabel(line: string): boolean {
  const t = line.trim();
  return t.endsWith(":") || (t.startsWith("**") && t.replace(/:$/, "").endsWith("**"));
}

export function parseMarkdown(text: string): MdPart[] {
  const lines = String(text ?? "").replace(/\r\n/g, "\n").split("\n");
  const out: MdPart[] = [];
  let para: string[] = [];
  const flush = () => {
    if (para.length) out.push({ type: "paragraph", text: para.join("\n").trim() });
    para = [];
  };
  let i = 0;
  while (i < lines.length) {
    const ln = lines[i];
    if (!ln.trim()) { flush(); i += 1; continue; }
    if (TABLE_ROW.test(ln) && i + 1 < lines.length && TABLE_RULE.test(lines[i + 1])) {
      flush();
      const header = cells(ln);
      const rows: string[][] = [];
      i += 2;
      while (i < lines.length && TABLE_ROW.test(lines[i])) {
        if (!TABLE_RULE.test(lines[i])) rows.push(cells(lines[i]));
        i += 1;
      }
      // PLAN_R6 E3: a table by rating grade reads AAA to D
      out.push({ type: "table", header, rows: orderRatingTable(rows) });
      continue;
    }
    const h = HEADING.exec(ln);
    if (h) { flush(); out.push({ type: "heading", level: h[1].length, text: h[2] }); i += 1; continue; }
    if (QUOTE.test(ln)) {
      flush();
      const q: string[] = [];
      while (i < lines.length && QUOTE.test(lines[i])) { q.push((QUOTE.exec(lines[i]) as RegExpExecArray)[1]); i += 1; }
      out.push({ type: "quote", paragraphs: q.join("\n").split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean) });
      continue;
    }
    if (LIST.test(ln) && para.length === 1 && isLabel(para[0])) flush();
    if (LIST.test(ln) && !para.length) {
      const items: string[] = [];
      const ordered = /^\s*\d/.test(ln);
      while (i < lines.length && (LIST.test(lines[i]) || (items.length && /^\s{2,}\S/.test(lines[i])))) {
        const m = LIST.exec(lines[i]);
        if (m) items.push(m[2].trim());
        else items[items.length - 1] += ` ${lines[i].trim()}`;
        i += 1;
      }
      out.push({ type: "list", ordered, items });
      continue;
    }
    para.push(ln.replace(/\s+$/, ""));
    i += 1;
  }
  flush();
  return out;
}

/** Whether a text needs the markdown renderer at all (a table, a heading or a quote in it). */
export function hasRichMarkdown(text: string): boolean {
  const s = String(text ?? "");
  return /^\s*\|.*\|\s*$/m.test(s) || /^\s*#{1,6}\s/m.test(s) || /^\s*>/m.test(s);
}

const NUMERIC_CELL = /^[+\-−]?\s*(SAR\s*)?[+\-−]?\d[\d,]*(\.\d+)?\s*(%|bps|bn|m|mn|x|pp)?$/i;

/** A column reads as numbers (right-aligned, tabular figures) when every filled cell is a figure. */
export function numericColumn(values: unknown[]): boolean {
  const filled = values.map((v) => String(v ?? "").trim()).filter((v) => v && v !== "—" && v !== "-");
  return filled.length > 0 && filled.every((v) => NUMERIC_CELL.test(v.replace(/\*\*/g, "")));
}
