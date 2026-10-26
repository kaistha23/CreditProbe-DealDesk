/**
 * Goal detection for the What-If chat (PLAN_R11_AGENTS W3): the UI mirror of
 * `backend/agents_v5/whatif/goals.py`, tested on the same corpus
 * (`tests/v5/agents_whatif/goal_corpus.json`).
 *
 * A goal ("what would a regional slowdown do to us and what should we do?") offers
 * "Run as agent"; a single scenario ("oil −40%") never does, and the chat treats it
 * exactly as before.
 */

const STRONG: RegExp[] = [
  /\bwhat should (we|i|the bank)\b/i,
  /\bhow should (we|the bank) (respond|react|prepare|mitigate|act)\b/i,
  /\bwhat (management )?actions?\b/i,
  /\bwhat can we do\b/i,
  /\b(management|post[- ]model|judg(e)?mental)\s+overlays?\b/i,
  /\boverlays?\b.{0,40}\b(defensible|justif\w*|appropriate|warranted|size|how (much|big))\b/i,
  /\b(provision\w*|reserv\w*|cover\w*)\s+(enough|adequate\w*|sufficient\w*)\b/i,
  /\b(enough|adequate|sufficient)\s+(provision\w*|reserves?|ecl|coverage)\b/i,
  /\b(adequacy|sufficiency) of (our |the )?(provision\w*|ecl|coverage|reserves?)\b/i,
  /\bsensitivity (set|analysis|pack)\b/i,
];

const WEAK: RegExp[] = [
  /\bwhat (would|will|could|might|does|do)\b.{0,80}\b(do to|mean for|cost)\s+(us|the bank|our\b|the book|the portfolio)/i,
  /\bhow (badly )?(would|will|could) .{0,60}\b(hit|affect|impact|hurt)\s+(us|the bank|our\b|the book|the portfolio)/i,
  /\bstress[- ]test (the|our) (book|portfolio|bank)\b/i,
  /\bhow resilient\b/i,
  /\b(range|set) of scenarios\b/i,
];

const SIZE = /[-+−–]?\s?\d+(?:\.\d+)?\s*(%|pp\b|bps\b|bp\b|notch\w*|sd\b|percent|basis points|x\b)|\b[x×]\s?\d/i;

/** True when the text is a goal the What-If agent should run (not a single scenario or a question about the data). */
export function isGoal(text: string): boolean {
  const t = (text ?? "").trim();
  if (!t || t.startsWith("::")) return false;
  if (STRONG.some((p) => p.test(t))) return true;
  if (SIZE.test(t)) return false;
  return WEAK.some((p) => p.test(t));
}

/** The question a settled turn was asked with, when it is a goal not yet run as an agent. */
export function goalOfTurn(question: string, alreadyRun: Set<string>): string {
  const q = (question ?? "").replace(/^Run as agent:\s*/i, "").trim();
  return isGoal(q) && !alreadyRun.has(q) && !/^Run as agent:/i.test(question ?? "") ? q : "";
}
