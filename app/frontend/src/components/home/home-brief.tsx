"use client";

/**
 * The Brief tab (PLAN_R13 Session H, R12_FEEDBACK J2, J3): Noor's complete brief, the landing page after sign-in.
 *
 * The same brief component as Noor's panel (`NoorBrief`): a headline sentence, at most five lines, "n more" collapsed.
 * The Cockpit's deterministic attention cards are read through the Cockpit's own `readAttention` (unchanged) and sent
 * with the brief as its evidence: they are not shown as a panel here, and a line's Why opens the card behind it.
 * The book's ECL movement and what colleagues sent sit behind one quiet disclosure, so nothing computed is lost (N1).
 *
 * Deal Desk edition: the brief is Deal Desk's ("What matters in Deal Desk": the queue, queries, sector appetite,
 * conditions due, renewals, high tiers, approvals), read without the Cockpit's attention cards; the book's ECL
 * disclosure is not offered, since the Cockpit's ECL run is not part of the edition.
 */

import * as React from "react";
import { ChevronDown } from "lucide-react";

import { readAttention, type DomainId } from "@/components/cockpit-v4/client";
import { NoorBrief } from "@/components/noor/noor-brief";
import { noor } from "@/components/noor/noor-client";
import type { Brief, BriefItem } from "@/components/noor/noor-model";
import { adoptBrief, loadBrief } from "@/components/noor/noor-store";
import { SpeakerButton, VoiceNotice } from "@/components/noor/speaker-button";
import { useViewingAs } from "@/components/noor/viewing-as";
import { edition } from "@/lib/navigation";
import { cn } from "@/lib/utils";

/** The brief module the home shows: Deal Desk's in the Deal Desk edition, the whole persona brief in the full product. */
export function homeBriefModule(): string | undefined {
  return edition() === "dealdesk" ? "dealdesk" : undefined;
}

export function HomeBrief({ domain, onEvidence, onAsk, more }: {
  domain: DomainId;
  /** Opens the Cockpit attention card (the evidence) in the Cockpit's own drawer. */
  onEvidence: (itemId: string) => void;
  onAsk: () => void;
  /** The book's ECL movement and Sent to you, behind the disclosure. */
  more?: React.ReactNode;
}) {
  const { persona } = useViewingAs();
  const [brief, setBrief] = React.useState<Brief | null>(null);
  const [failed, setFailed] = React.useState(false);
  const [version, setVersion] = React.useState(0);
  const [showMore, setShowMore] = React.useState(false);
  const module = homeBriefModule();
  if (module) more = undefined;

  React.useEffect(() => {
    let live = true;
    void (async () => {
      let attention: unknown[] = [];
      if (!module) {
        try {
          const feed = await Promise.race([readAttention(domain), new Promise<null>((ok) => setTimeout(() => ok(null), 2500))]);
          attention = (feed?.segments_requiring_attention ?? []) as unknown[];
        } catch { attention = []; }
      }
      try {
        const b = await noor.brief(module ? { persona, module, top: 5 } : { persona, attention, top: 5 });
        if (!live) return;
        setBrief(b);
        setFailed(false);
        adoptBrief(b);
      } catch {
        if (live) setFailed(true);
      }
    })();
    return () => { live = false; };
  }, [persona, domain, version, module]);

  const evidence = React.useCallback((item: BriefItem) => {
    const id = item.evidence?.[0]?.item_id;
    if (!id) return false;
    onEvidence(id);
    return true;
  }, [onEvidence]);

  return (
    <div className="w-full pt-8" data-testid="home-brief">
      <div className="mx-auto w-full max-w-[46rem]">
      {brief ? (
        <NoorBrief brief={brief} variant="page" onEvidence={evidence} testId="noor-home-brief"
                   controls={<SpeakerButton brief={brief} />} />
      ) : failed ? (
        <div className="space-y-2" role="status">
          <p className="font-prose text-[20px] text-text-primary">Noor&apos;s brief could not be read just now.</p>
          <p className="text-[13px] text-text-muted">
            <button type="button" onClick={() => setVersion((v) => v + 1)} className="font-medium text-accent hover:underline">Try again</button>
            {" "}or{" "}
            <button type="button" onClick={onAsk} className="font-medium text-accent hover:underline">ask Noor a question</button>.
          </p>
        </div>
      ) : (
        <BriefSkeleton />
      )}

      {brief ? (
        <div className="mt-8 flex flex-wrap items-center gap-x-5 gap-y-2 text-[12.5px]">
          <button type="button" onClick={onAsk} data-testid="home-brief-ask" className="font-medium text-accent underline-offset-4 hover:underline">
            Ask Noor anything</button>
          <button type="button" onClick={() => void loadBrief(module ? { module } : {})} className="text-text-muted hover:text-text-primary">
            Open in the panel</button>
          {more ? (
            <button type="button" onClick={() => setShowMore((v) => !v)} aria-expanded={showMore} data-testid="home-brief-more"
                    className="inline-flex items-center gap-1 text-text-muted hover:text-text-primary">
              <ChevronDown className={cn("size-3.5 transition-transform", showMore && "rotate-180")} aria-hidden />
              The book&apos;s ECL and items sent to you
            </button>
          ) : null}
        </div>
      ) : null}
      {brief ? <VoiceNotice className="mt-3" /> : null}
      </div>
      {more && showMore ? <div className="mt-10 space-y-12 border-t border-border pt-10" data-testid="home-brief-more-body">{more}</div> : null}
    </div>
  );
}

function BriefSkeleton() {
  return (
    <div className="space-y-5" aria-busy="true" aria-label="Reading every source for your brief">
      <div className="h-3 w-64 animate-pulse rounded bg-surface-sunken" />
      <div className="h-6 w-[28rem] max-w-full animate-pulse rounded bg-surface-sunken" />
      <div className="space-y-4 border-t border-border pt-4">
        {[0, 1, 2, 3].map((i) => <div key={i} className="h-10 animate-pulse rounded bg-surface-sunken/70" />)}
      </div>
    </div>
  );
}
