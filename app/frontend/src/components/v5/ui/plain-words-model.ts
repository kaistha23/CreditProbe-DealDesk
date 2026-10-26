/**
 * R14 U (K34): the rules of the shared "In plain words" block, free of React so they are unit-tested.
 *
 * Every panel opens with 3–4 short lines (≤ 60 words in all), written by the panel owner's deterministic writer from
 * the panel's own result: (1) what this is, (2) what it proposes here with the one or two numbers that matter,
 * (3) what to do / the caveat. Jargon is explained inline on first use ("RAROC (return on the capital the risk
 * uses)"), so a layman can read it. This file gives owners three helpers:
 *
 *   glossFirstUse(lines)   adds the inline explanation the first time a term appears in the block
 *   checkPlainWords(lines) the K34 acceptance rules (count, length, a number, no unexplained jargon)
 *   spokenText(lines)      the text the speaker reads (no brackets read aloud twice, units spelled)
 */

export const PLAIN_WORDS_LIMITS = { minLines: 1, maxLines: 4, maxWords: 60 } as const;

/** Credit jargon and its plain explanation (used in brackets on first use). Longest keys first when matching. */
export const GLOSSARY: Record<string, string> = {
  RAROC: "return on the capital the risk uses",
  SVA: "value added after the cost of capital",
  LGD: "share of the loan lost if the borrower defaults",
  PD: "chance the borrower defaults",
  EAD: "amount owed at default",
  ECL: "expected credit loss provision",
  EL: "expected loss",
  RWA: "risk-weighted assets, which drive capital",
  DSCR: "cash flow divided by debt payments",
  CET1: "core capital ratio",
  CRM: "credit risk mitigation",
  DoA: "delegation of authority",
  EWS: "early warning",
  NPL: "non-performing loan",
  DPD: "days past due",
  LTV: "loan to value",
  bps: "hundredths of a percent",
};

const TERMS = Object.keys(GLOSSARY).sort((a, b) => b.length - a.length);

function termRe(term: string): RegExp {
  // Whole word; case-sensitive for acronyms (so "pd" in "updated" never matches), "bps" lower-case only.
  return new RegExp(`(^|[^A-Za-z0-9])(${term})(?![A-Za-z0-9])`, "");
}

/** True when the term at `index` in `line` is already followed by its bracketed explanation. */
function explainedAt(line: string, index: number, term: string): boolean {
  const rest = line.slice(index + term.length);
  return /^\s*\(/.test(rest);
}

/**
 * Add the plain explanation in brackets the first time each jargon term appears in the block (later uses stay bare).
 * Already-explained uses ("RAROC (return …)") are left as they are. Numbers before "bps" are kept ("40 bps").
 */
export function glossFirstUse(lines: string[]): string[] {
  const seen = new Set<string>();
  return lines.map((line) => {
    let out = line;
    for (const term of TERMS) {
      if (seen.has(term)) continue;
      const m = termRe(term).exec(out);
      if (!m) continue;
      seen.add(term);
      const at = m.index + m[1].length;
      if (explainedAt(out, at, term)) continue;
      const end = at + term.length;
      out = `${out.slice(0, end)} (${GLOSSARY[term]})${out.slice(end)}`;
    }
    return out;
  });
}

export function wordCount(lines: string[]): number {
  return lines.join(" ").split(/\s+/).filter(Boolean).length;
}

/** Strip the bracketed glosses (for the word count: the limit is on what the owner wrote, not on our brackets). */
export function withoutGlosses(text: string): string {
  let out = text;
  for (const term of TERMS) out = out.split(` (${GLOSSARY[term]})`).join("");
  return out;
}

export interface PlainWordsCheck { ok: boolean; words: number; problems: string[] }

/**
 * The K34 acceptance rules for one block: 1–4 lines (3–4 recommended), ≤ 60 words (glosses excluded), at least one
 * number taken from the panel, and every jargon term explained on first use (after glossFirstUse this always holds).
 */
export function checkPlainWords(lines: string[], opts: { glossed?: boolean } = {}): PlainWordsCheck {
  const problems: string[] = [];
  const clean = lines.map((l) => l.trim()).filter(Boolean);
  if (clean.length < PLAIN_WORDS_LIMITS.minLines) problems.push("no lines");
  if (clean.length > PLAIN_WORDS_LIMITS.maxLines) problems.push(`${clean.length} lines (at most ${PLAIN_WORDS_LIMITS.maxLines})`);
  const words = wordCount(clean.map(withoutGlosses));
  if (words > PLAIN_WORDS_LIMITS.maxWords) problems.push(`${words} words (at most ${PLAIN_WORDS_LIMITS.maxWords})`);
  if (!clean.some((l) => /\d/.test(l))) problems.push("names no number from the panel");
  const text = opts.glossed === false ? clean : glossFirstUse(clean);
  const seen = new Set<string>();
  for (const line of text) {
    for (const term of TERMS) {
      const m = termRe(term).exec(line);
      if (!m || seen.has(term)) continue;
      seen.add(term);
      if (!explainedAt(line, m.index + m[1].length, term)) problems.push(`"${term}" not explained on first use`);
    }
  }
  if (clean.some((l) => /[{}[\]]|undefined|NaN|null/.test(l))) problems.push("debug text in a line");
  return { ok: problems.length === 0, words, problems };
}

/** What the speaker reads: the lines as sentences, units spoken ("SAR 1.2m" → "SAR 1.2 million"). */
export function spokenText(lines: string[]): string {
  return lines
    .map((l) => l.trim()).filter(Boolean)
    .map((l) => (/[.!?]$/.test(l) ? l : `${l}.`))
    .join(" ")
    .replace(/(\d)\s?bn\b/g, "$1 billion")
    .replace(/(\d)\s?m\b/g, "$1 million")
    .replace(/(\d)\s?k\b/g, "$1 thousand")
    .replace(/(\d)\s?pp\b/g, "$1 percentage points")
    .replace(/(\d)\s?bps\b/g, "$1 basis points")
    .replace(/(\d)x\b/g, "$1 times")
    .replace(/\s+/g, " ")
    .trim();
}
