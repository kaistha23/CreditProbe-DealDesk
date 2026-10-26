/**
 * Answer first (PLAN_R12 N2, I10 a): the shape of an answer before it is drawn.
 *
 * - `splitHeadline` takes the first sentence of the first prose paragraph as the headline: the one line a banker
 *   reads before deciding whether to read on. A lead-in label ("**Answer:**", "Summary:") is dropped; an answer that
 *   opens with a table, a list or a heading has no headline and is shown as written.
 * - `foldProse` keeps the body short: the first paragraphs stay open and the rest sits behind "Show more", so no
 *   answer is a wall of text. Lists, tables and headings count by their size, not as one paragraph.
 *
 * Pure TypeScript: tested with the node runner. Nothing here changes a word or a number; it only decides where the
 * text is shown.
 */

const LEAD = /^\s*(?:\*\*)?(?:answer|summary|in short|short answer|headline|bottom line|tl;dr|verdict)\s*[:.\-–—]\s*(?:\*\*)?\s*/i;
const BLOCKY = /^\s*(?:[|#>]|[-*•]\s|\d+[.)]\s|```)/;

/** Sentence end: a full stop, ! or ? followed by a space and a capital / digit / quote, outside a number ("1.5") or an abbreviation. */
function firstSentenceEnd(p: string): number {
  const re = /([.!?])(\*\*)?(\s+)(?=[A-Z0-9“"(*])/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(p))) {
    const before = p.slice(Math.max(0, m.index - 5), m.index);
    if (/\b(?:e\.g|i\.e|vs|approx|incl|no|c|cf|etc|Mr|Ms|Dr|St|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)$/i.test(before)) continue;
    if (/\b[A-Z]$/.test(before)) continue; // an initial, "U.S."
    return m.index + 1 + (m[2]?.length ?? 0);
  }
  return -1;
}

export interface Headline { headline: string; rest: string }

/** The headline sentence and the rest of the text (both markdown, words unchanged). */
export function splitHeadline(markdown: string, maxWords = 45): Headline {
  const text = String(markdown ?? "").replace(/\r\n/g, "\n").trim();
  if (!text) return { headline: "", rest: "" };
  const paras = text.split(/\n{2,}/);
  const first = paras[0];
  if (BLOCKY.test(first) || first.split("\n").length > 1 && first.split("\n").every((l) => BLOCKY.test(l))) return { headline: "", rest: text };
  // A first paragraph spread over several lines (one statement per line) reads as its first line.
  const lines = first.split("\n");
  const lead = lines[0].replace(LEAD, "");
  if (!lead.trim() || BLOCKY.test(lead)) return { headline: "", rest: text };
  let headline = lead;
  let tail = "";
  const end = firstSentenceEnd(lead);
  if (end > 0 && end < lead.length) { headline = lead.slice(0, end); tail = lead.slice(end).trim(); }
  // A bold run split across the cut keeps its markers balanced on both sides.
  if ((headline.match(/\*\*/g) ?? []).length % 2 === 1) { headline = `${headline}**`; tail = `**${tail}`; }
  if (headline.split(/\s+/).length > maxWords) return { headline: "", rest: text };
  const restFirst = [tail, ...lines.slice(1)].filter((l) => l.trim()).join("\n");
  const rest = [restFirst, ...paras.slice(1)].filter((p) => p.trim()).join("\n\n");
  return { headline: headline.trim(), rest };
}

/** The headline without markdown emphasis, for an aria-label or a plain-text copy. */
export function plainHeadline(markdown: string): string {
  return splitHeadline(markdown).headline.replace(/\*\*|`|\*/g, "").trim();
}

/** How much space a paragraph takes, in lines a reader sees (a table row or list item is a line). */
function weight(p: string): number {
  const lines = p.split("\n").filter((l) => l.trim());
  if (lines.every((l) => /^\s*\|/.test(l))) return Math.max(1, lines.length - 1);
  if (lines.every((l) => /^\s*(?:[-*•]|\d+[.)])\s/.test(l))) return lines.length;
  const words = p.split(/\s+/).length;
  return Math.max(1, Math.ceil(words / 22));
}

export interface Fold { open: string; more: string; hidden: number }

/**
 * The body split into what is shown and what sits behind "Show more". The open part keeps whole paragraphs up to
 * `budget` lines (never fewer than one paragraph); the fold happens only when it hides at least `minHidden` lines,
 * so a short answer is never folded for the sake of one line.
 */
export function foldProse(markdown: string, budget = 9, minHidden = 3): Fold {
  const text = String(markdown ?? "").trim();
  const paras = text ? text.split(/\n{2,}/) : [];
  let used = 0;
  let cut = paras.length;
  for (let i = 0; i < paras.length; i++) {
    const w = weight(paras[i]);
    if (i > 0 && used + w > budget) { cut = i; break; }
    used += w;
  }
  const hiddenWeight = paras.slice(cut).reduce((s, p) => s + weight(p), 0);
  if (cut >= paras.length || hiddenWeight < minHidden) return { open: text, more: "", hidden: 0 };
  return { open: paras.slice(0, cut).join("\n\n"), more: paras.slice(cut).join("\n\n"), hidden: paras.length - cut };
}

/** Key figures in a sentence (money, percentages, bps, multiples, counts with a unit): what the renderer emphasises. */
export const FIGURE =
  /(?<![\w*`])((?:SAR|USD|AED|OMR|US\$)\s?-?\d[\d,]*(?:\.\d+)?\s?(?:bn|billion|m|mn|million|k|thousand)?|[-+−]?\d[\d,]*(?:\.\d+)?\s?(?:%|pp|bps|x)(?![\w%])|[-+−]?\d[\d,]*(?:\.\d+)?\s(?:basis points|percentage points|notches?|borrowers|names|accounts|facilities|deals|days|years))(?![\w*])/g;

/** The figures a text mentions, in order (deduplicated). */
export function figuresIn(text: string): string[] {
  const out: string[] = [];
  for (const m of String(text ?? "").replace(/\*\*/g, "").matchAll(FIGURE)) if (!out.includes(m[1])) out.push(m[1]);
  return out;
}
