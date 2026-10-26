/**
 * PLAN_R6 E1: every thread answer and commentary shows its key figures in bold.
 *
 * Writers are told to bold the key figures and the conclusion. When an answer arrives with no emphasis at all
 * (a deterministic writer, a stored answer from before R6, or a model that did not follow the instruction), the
 * renderer bolds the figures in its prose so the reader's eye still lands on them. Tables, headings and code are
 * left alone, and an answer that already carries `**` is shown exactly as written.
 */

const FIGURE =
  /(?<![\w*`])((?:SAR|USD|US\$)\s?-?\d[\d,]*(?:\.\d+)?\s?(?:bn|billion|m|mn|million|k|thousand)?|[-+−]?\d[\d,]*(?:\.\d+)?\s?(?:%|pp|bps|x)(?![\w%])|[-+−]?\d[\d,]*(?:\.\d+)?\s(?:basis points|percentage points|notches?|borrowers|names|accounts|facilities))(?![\w*])/g;

function emphasiseLine(line: string): string {
  if (/^\s*\|/.test(line) || /^\s*#/.test(line) || /^\s*```/.test(line)) return line;
  // keep inline code untouched
  return line.split(/(`[^`]*`)/).map((part) => (part.startsWith("`") ? part : part.replace(FIGURE, "**$1**"))).join("");
}

/** The text with its figures in bold when it carries no emphasis of its own. */
export function emphasise(text: string): string {
  const s = String(text ?? "");
  if (!s.trim() || s.includes("**")) return s;
  let inFence = false;
  return s.split("\n").map((l) => {
    if (/^\s*```/.test(l)) { inFence = !inFence; return l; }
    return inFence ? l : emphasiseLine(l);
  }).join("\n");
}

/** True when the text will render at least one <strong>. */
export function hasEmphasis(text: string): boolean {
  return /\*\*[^*]+\*\*/.test(emphasise(text));
}
