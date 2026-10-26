"use client";

/**
 * The Cockpit's answers in the shared answer style (PLAN_R12 N2, registered frozen exception FX-R12-02).
 *
 * The Cockpit is frozen, so these wrappers are presentation only: the narrative's words are the server's own,
 * rendered by the Cockpit's own `Markdown` (passed in as `render`), only split so the first sentence shows as the
 * headline and a long body sits behind "Show more". No word, number, claim, chart, table, order or flow changes.
 */

import * as React from "react";
import { ChevronDown, ChevronUp } from "lucide-react";

import { cn } from "@/lib/utils";

import { bankerText } from "./banker";
import { foldProse, splitHeadline } from "./headline";
import { A } from "./styles";

export { CockpitPlotlyChart } from "./cockpit-chart";

export function CockpitNarrative({ source, render, children }: {
  source: string;
  render: (markdown: string) => React.ReactNode;
  /** The Cockpit's own element for the whole narrative, drawn unchanged when there is no headline sentence to lead with. */
  children?: React.ReactNode;
}) {
  const [open, setOpen] = React.useState(false);
  const { headline, rest } = React.useMemo(() => splitHeadline(String(source ?? "")), [source]);
  const { open: shown, more } = React.useMemo(() => foldProse(rest, 10), [rest]);
  // A narrative with no headline sentence (it opens with a table or a list) is drawn exactly as before.
  if (!headline) return <>{children ?? render(String(source ?? ""))}</>;
  return (
    <div className={A.stackCompact} data-testid="v4-answer-style" data-answer-style="r12">
      <div data-testid="v4-answer-headline"
           className={cn("[&_[data-testid=v4-markdown]]:max-w-[72ch] [&_p]:m-0 [&_p]:text-[15px] [&_p]:font-semibold [&_p]:leading-[1.45] [&_p]:text-text-primary")}>
        {render(headline)}
      </div>
      {shown.trim() ? <div className="[&_strong]:text-text-primary">{render(shown)}</div> : null}
      {more ? (
        <>
          {open ? <div className="[&_strong]:text-text-primary">{render(more)}</div> : null}
          <button type="button" className={A.more} onClick={() => setOpen((x) => !x)} aria-expanded={open} data-testid="v4-answer-more">
            {open ? <><ChevronUp size={13} aria-hidden /> Show less</> : <><ChevronDown size={13} aria-hidden /> Show more</>}</button>
        </>) : null}
    </div>
  );
}

/** A follow-up question as a chip label: banker words for any internal name (the question sent is unchanged). */
export const cockpitChipLabel = (question: string): string => bankerText(question);
