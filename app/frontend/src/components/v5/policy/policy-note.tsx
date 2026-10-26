"use client";

/**
 * PolicyNote: the one line that names the policy clause behind a movement (PLAN_R3 S1-2, PLAYBOOK_API.md 9).
 *
 *   <PolicyNote book="corporate" measure="stage2" driver="downgrade" segment="Construction" period="2026Q2"
 *               prefix="Stage 2 rose because" />
 *
 * It reads the active versioned policy pack through `GET /api/v1/policy/explain`. It renders nothing while it
 * asks, when no clause applies (`sentence` null: never invent a clause), or when the service cannot be reached.
 * It never throws.
 */

import Link from "next/link";
import * as React from "react";
import { Scale } from "lucide-react";

import { cn } from "@/lib/utils";
import { type Explain, type ExplainClause, policy } from "@/lib/v5/policy";

export interface PolicyNoteProps {
  book: string;
  measure: string;
  driver?: string;
  segment?: string;
  period?: string;
  prefix?: string;
  testId?: string;
  className?: string;
}

export function PolicyNote({ book, measure, driver, segment, period, prefix, testId = "policy-note", className }: PolicyNoteProps) {
  const key = [book, measure, driver ?? "", segment ?? "", period ?? ""].join("|");
  const [state, setState] = React.useState<{ key: string; data: Explain | null } | null>(null);

  React.useEffect(() => {
    let live = true;
    try {
      policy.explain({ book, measure, driver, segment, period }).then(
        (data) => { if (live) setState({ key, data }); },
        () => { if (live) setState({ key, data: null }); },
      );
    } catch {
      // Never surface: a note that cannot be read is simply not shown.
    }
    return () => { live = false; };
  }, [key, book, measure, driver, segment, period]);

  const data = state?.key === key ? state.data : null;
  if (!data || typeof data.sentence !== "string" || !data.sentence.trim()) return null;
  const sentence = data.sentence.trim();
  const clauses = Array.isArray(data.clauses) ? data.clauses : [];

  return (
    <p className={cn("flex items-start gap-1.5 text-xs leading-relaxed text-text-secondary", className)}
       data-testid={testId} data-pack={data.pack_version}>
      <Scale className="mt-0.5 size-3.5 shrink-0 text-accent" aria-hidden />
      <span>
        <span className="font-medium text-text-primary">{prefix ?? "Policy:"}</span>{" "}
        <LinkedSentence sentence={sentence} clauses={clauses} />
      </span>
    </p>
  );
}

function escapeRe(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** The sentence with every clause id it names turned into a link to that clause in Policy Docs. */
function LinkedSentence({ sentence, clauses }: { sentence: string; clauses: ExplainClause[] }) {
  const linkable = clauses.filter((c) => c && typeof c.clause_id === "string" && c.clause_id && typeof c.href === "string" && c.href.startsWith("/"));
  if (!linkable.length) return <>{sentence}</>;
  const byId = new Map(linkable.map((c) => [c.clause_id, c]));
  const ids = [...byId.keys()].sort((a, b) => b.length - a.length).map(escapeRe);
  const parts = sentence.split(new RegExp(`(${ids.join("|")})`, "g"));
  const mentioned = parts.some((p) => byId.has(p));
  return (
    <>
      {parts.map((part, i) => {
        const c = byId.get(part);
        if (!c) return <React.Fragment key={i}>{part}</React.Fragment>;
        return (
          <Link key={i} href={c.href} title={c.title} data-testid="policy-note-clause" data-clause={c.clause_id}
                className="font-mono font-medium text-accent hover:underline">
            {part}
          </Link>
        );
      })}
      {mentioned ? null : (
        <>
          {" "}
          {linkable.map((c, i) => (
            <React.Fragment key={c.clause_id}>
              {i ? ", " : "("}
              <Link href={c.href} title={c.title} data-testid="policy-note-clause" data-clause={c.clause_id}
                    className="font-mono font-medium text-accent hover:underline">{c.clause_id}</Link>
              {i === linkable.length - 1 ? ")" : null}
            </React.Fragment>
          ))}
        </>
      )}
    </>
  );
}
