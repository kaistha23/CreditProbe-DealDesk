/**
 * PLAN_R6 E1 (screen 06): the policy text excerpt with its clause IDs and clause titles picked out, and its
 * headings styled. Each line becomes a part the page renders: a heading, a clause (id, title, rest) or plain text.
 */
export type ExcerptLine =
  | { kind: "heading"; text: string }
  | { kind: "clause"; id: string; title: string; rest: string }
  | { kind: "text"; text: string };

const CLAUSE = /^\s*(CBUAE CRM (?:Art\. \d+(?:\.\d+)*|Intro \d)|[A-Z]{1,5}-\d+ (?:§\d+(?:\.\d+)*|Intro \([a-z]\))|(?:[A-Z]{1,5}-)?\d+(?:\.\d+)+[a-z]?|[A-Z]{1,5}-\d+(?:\.\d+)*)\s+([^.:\n]{2,80}[.:])\s*(.*)$/;

export function parseExcerpt(text: string): ExcerptLine[] {
  return String(text ?? "").split("\n").filter((l) => l.trim()).map((raw): ExcerptLine => {
    const l = raw.trim();
    const m = CLAUSE.exec(l);
    if (m) return { kind: "clause", id: m[1], title: m[2].replace(/[.:]$/, ""), rest: m[3] };
    const words = l.split(/\s+/).length;
    if (/^#{1,4}\s/.test(l) || /^(section|part|chapter|annex|appendix)\b/i.test(l) && words <= 10
        || (words <= 8 && !/[.;,]$/.test(l) && l === l.toUpperCase() && /[A-Z]/.test(l))) {
      return { kind: "heading", text: l.replace(/^#+\s*/, "") };
    }
    return { kind: "text", text: l };
  });
}
