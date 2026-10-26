/**
 * R14 G (carried J8 gap): the lens assistant does not repeat the dashboard's interpretation. Threads written before R14
 * stored the interpretation inside the build answer; `stripRepeated` removes from an answer's markdown every line that the
 * dashboard already shows (headline or interpretation line), and points to it once instead. Pure (node-testable).
 */

const norm = (s: string) => s.replace(/^\s*[-*•]\s+/, "").replace(/\*\*/g, "").replace(/\s+/g, " ").trim().toLowerCase();

export const POINTER = "The reading of this lens is at the top of the dashboard.";

export function stripRepeated(markdown: string, shown: string[]): string {
  const seen = new Set(shown.map(norm).filter(Boolean));
  if (!seen.size) return markdown;
  let removed = 0;
  const kept = markdown.split("\n").filter((l) => {
    if (seen.has(norm(l))) { removed += 1; return false; }
    return true;
  });
  if (!removed) return markdown;
  const out = kept.join("\n").replace(/\n{3,}/g, "\n\n").trim();
  return out.includes("top of the dashboard") ? out : out.replace(/^(.*?)(\n\n|$)/, (_m, first: string, sep: string) => `${first}\n\n${POINTER}${sep}`);
}

/** The lines the dashboard shows (headline + interpretation lines). */
export function dashboardLines(it: { headline?: string; lines?: { text: string }[] } | null | undefined): string[] {
  if (!it) return [];
  return [it.headline ?? "", ...(it.lines ?? []).map((l) => l.text)].filter(Boolean);
}
