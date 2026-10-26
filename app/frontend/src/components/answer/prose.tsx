"use client";

/**
 * An answer's prose (PLAN_R12 N2): headline sentence first, then the body in the refined type scale, key figures
 * emphasised, pipe tables as compact house-kit tables, and anything past a screenful behind "Show more" (no walls
 * of text). Internal tool names are read out in banker words. Words and numbers are the writer's own; long
 * decimals are tidied by the shared formatter and a rating table reads AAA to D.
 *
 * Supersedes components/v5/thread/markdown.tsx (which now re-exports this) and the per-module markdown renderers.
 */

import Link from "next/link";
import * as React from "react";
import { ChevronDown, ChevronUp } from "lucide-react";

import { cn } from "@/lib/utils";
import { emphasise } from "@/lib/v5/emphasis";
import { tidyText } from "@/lib/v5/format";
import { orderRatingTable } from "@/lib/v5/ratings";

import { bankerText } from "./banker";
import { foldProse, splitHeadline } from "./headline";
import { A } from "./styles";
import { AnswerTable, looksNumeric } from "./table";

const LINK = /\[([^\]]+)\]\((\/[^)\s]*)\)/;

/** Bold (key figures), inline code, italics and links to CreditProbe screens (relative paths only). */
export function inline(s: string): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  const re = /\*\*(.+?)\*\*|`(.+?)`|\[([^\]]+)\]\((\/[^)\s]*)\)|(?<![\w*])\*(?!\s)(.+?)\*(?![\w*])/g;
  let last = 0;
  let k = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(s))) {
    if (m.index > last) out.push(s.slice(last, m.index));
    if (m[1]) out.push(<strong key={k++} className={A.figure}>{m[1]}</strong>);
    else if (m[2]) out.push(<code key={k++} className={A.code}>{m[2]}</code>);
    else if (m[3]) out.push(<Link key={k++} href={m[4]} className={A.link} data-testid="answer-link">{m[3]}</Link>);
    else out.push(<em key={k++}>{m[5]}</em>);
    last = m.index + m[0].length;
  }
  if (last < s.length) out.push(s.slice(last));
  return out;
}

const ITEM = /^\s*([-*•]|\d+[.)])\s/;

function Paragraphs({ text, compact, inlineRun }: { text: string; compact: boolean; inlineRun: (s: string) => React.ReactNode }) {
  const paras = text.trim() ? text.trim().split(/\n{2,}/) : [];
  return (
    <>
      {paras.map((p, i) => {
        const lines = p.split("\n").filter((l) => l.trim());
        if (!lines.length) return null;
        if (/^#{1,4}\s/.test(lines[0]) && lines.length === 1) return <h4 key={i} className={A.heading}>{inlineRun(lines[0].replace(/^#+\s*/, ""))}</h4>;
        if (lines.every((l) => /^\s*>/.test(l))) {
          return <blockquote key={i} className="border-l-2 border-accent/40 pl-3">{inlineRun(lines.map((l) => l.replace(/^\s*>\s?/, "")).join(" "))}</blockquote>;
        }
        if (lines.every((l) => /^\s*\|/.test(l)) && lines.length >= 2) {
          const cells = (l: string) => l.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
          const body = lines.filter((l) => !/^\s*\|?\s*:?-{2,}/.test(l));
          const [head, ...unordered] = body.map(cells);
          // PLAN_R6 E3: a table by rating grade reads AAA to D (bold markers ignored when reading the grade)
          const ordered = orderRatingTable(unordered.map((r, j) => [(r[0] ?? "").replace(/\*\*/g, ""), String(j)])).map((x) => unordered[Number(x[1])]);
          const right = head.map((_, j) => j > 0 && ordered.length > 0 && ordered.every((r) => !r[j] || looksNumeric((r[j] ?? "").replace(/\*\*/g, ""))));
          return (
            <AnswerTable key={i} bare testId="answer-prose-table" max={compact ? 5 : 8}
                         columns={head.map((h, j) => ({ key: String(j), label: inlineRun(h), align: right[j] ? "right" : "left" }))}
                         rows={ordered.map((r) => Object.fromEntries(head.map((_, j) => [String(j), inlineRun(r[j] ?? "")])))} />);
        }
        const bullets = lines.filter((l) => ITEM.test(l));
        if (bullets.length === lines.length) {
          const ordered = /^\s*\d/.test(lines[0]);
          const items = lines.map((l, j) => <li key={j} className="pl-0.5">{inlineRun(l.replace(ITEM, ""))}</li>);
          return ordered
            ? <ol key={i} className="ml-5 list-decimal space-y-1 marker:text-text-muted">{items}</ol>
            : <ul key={i} className="ml-5 list-disc space-y-1 marker:text-accent">{items}</ul>;
        }
        if (bullets.length && ITEM.test(lines[1] ?? "") && !ITEM.test(lines[0])) {
          return (
            <div key={i} className="space-y-1">
              <p>{inlineRun(lines[0])}</p>
              <ul className="ml-5 list-disc space-y-1 marker:text-accent">{lines.slice(1).map((l, j) => <li key={j}>{inlineRun(l.replace(ITEM, ""))}</li>)}</ul>
            </div>);
        }
        return <p key={i}>{inlineRun(lines.join(" ").replace(/^#+\s*/, ""))}</p>;
      })}
    </>
  );
}

/** The one headline line of an answer. */
export function AnswerHeadline({ text, compact = false, className, inlineRun = inline }: {
  text: string; compact?: boolean; className?: string; inlineRun?: (s: string) => React.ReactNode;
}) {
  if (!String(text ?? "").trim()) return null;
  return <p className={cn(compact ? A.headlineCompact : A.headline, "[&_strong]:text-text-primary", className)} data-testid="answer-headline">{inlineRun(text)}</p>;
}

/**
 * Text prepared for display: banker words, tidy decimals, and key figures in bold, consistently: each paragraph the
 * writer left without emphasis gets its figures bolded (a writer who bolded only the headline still gets figures
 * emphasised in the body); a paragraph the writer emphasised is shown as written.
 */
export function prepare(text: string): string {
  return tidyText(bankerText(String(text ?? ""))).split(/(\n{2,})/).map((part) => (/^\n+$/.test(part) ? part : emphasise(part))).join("");
}

export function AnswerProse({ text, className, headline = false, fold = true, compact = false, testId = "convo-markdown", inlineRun = inline, inherit = false }: {
  text: string;
  className?: string;
  /** Show the first sentence as the answer's headline (the first prose block of an answer). */
  headline?: boolean;
  /** Put the body past a screenful behind "Show more". */
  fold?: boolean;
  compact?: boolean;
  testId?: string;
  /** A module's own inline renderer (for example links that open its items). */
  inlineRun?: (s: string) => React.ReactNode;
  /** Keep the surrounding text colour (prose inside a coloured bubble). */
  inherit?: boolean;
}) {
  const [open, setOpen] = React.useState(false);
  const prepared = React.useMemo(() => prepare(text), [text]);
  const { headline: head, rest } = React.useMemo(() => (headline ? splitHeadline(prepared) : { headline: "", rest: prepared }), [prepared, headline]);
  const { open: shown, more } = React.useMemo(() => (fold ? foldProse(rest, compact ? 7 : 9) : { open: rest, more: "" }), [rest, fold, compact]);
  if (!head && !shown.trim()) return null;
  return (
    <div className={cn(compact ? A.bodyCompact : A.body, inherit && "text-inherit [&_strong]:text-inherit", className)} data-testid={testId} data-answer-style="r12">
      {head ? <AnswerHeadline text={head} compact={compact} inlineRun={inlineRun} /> : null}
      <Paragraphs text={shown} compact={compact} inlineRun={inlineRun} />
      {more ? (
        <>
          {open ? <Paragraphs text={more} compact={compact} inlineRun={inlineRun} /> : null}
          <button type="button" className={A.more} onClick={() => setOpen((x) => !x)} aria-expanded={open} data-testid="answer-prose-more">
            {open ? <><ChevronUp size={13} aria-hidden /> Show less</> : <><ChevronDown size={13} aria-hidden /> Show more</>}</button>
        </>) : null}
    </div>
  );
}

export { LINK as ANSWER_LINK };
