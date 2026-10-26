"use client";

/**
 * R13 X (J9): the work queues as one line of small counters (was R12's six cards); definitions behind the (i).
 * R12 Session U (PLAN_R12 §1.1, I30): the work-queue cards under the Ask Deal Desk box. Six small cards; each opens a
 * filtered list whose rows open the existing deal page. Counts come from the engine (`GET /landing/cards`): the
 * workflow events for the three origination cards, the Book (Session I) for "going bad" and "renewals", and the
 * conditions for "conditions due". A card whose source is not connected yet shows 0 and still links to its place.
 */

import { useRouter } from "next/navigation";
import * as React from "react";
import { ArrowRight, X } from "lucide-react";

import { InfoPopover } from "./explain";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { type LandingCard, type LandingCards as Cards, r12Api, stateTone } from "@/lib/v5/dealdesk-r12";
import { sar } from "@/lib/v5/format";
import { friendlyMessage } from "@/lib/v5/errors";

import { Chip, Section, tableCls, tdCls, thCls } from "./kit";

const SHORT: Record<string, string> = {
  to_review: "To review", in_review: "In review", committee: "Committee", going_bad: "Going bad", renewals: "Renewals", conditions: "Conditions", sme: "SME fast track",
};

/** R13 X (J9): one small counter; the title, the source line and the definition sit in its tooltip, not on the screen. */
function Counter({ c, active, onOpen }: { c: LandingCard; active: boolean; onOpen: () => void }) {
  const tone = c.key === "going_bad" && c.count ? "text-negative" : c.key === "conditions" && c.count ? "text-warning" : "text-text-primary";
  return (
    <button type="button" onClick={onOpen} aria-pressed={active} title={`${c.title}: ${c.sub}`}
            data-testid={`dealdesk-card-${c.key}`} data-count={c.count} data-available={c.available ? "true" : "false"}
            className={cn("inline-flex h-7 items-center gap-1.5 rounded-full border px-2.5 text-[12px] transition-colors",
                          active ? "border-accent bg-accent-muted text-accent" : "border-border bg-surface text-text-secondary hover:border-accent")}>
      <span data-testid={`dealdesk-card-${c.key}-open`}>{SHORT[c.key] ?? c.title}</span>
      <b className={cn("tabular-nums", tone)} data-testid={`dealdesk-card-${c.key}-count`}>{c.count.toLocaleString("en-GB")}</b>
    </button>
  );
}

function CardList({ c, onClose, onOpen }: { c: LandingCard; onClose: () => void; onOpen: (href: string) => void }) {
  return (
    <Section title={c.title} testId="dealdesk-card-list" info={c.info}
             action={<button type="button" onClick={onClose} aria-label="Close the list" data-testid="dealdesk-card-list-close"
                             className="inline-flex size-7 items-center justify-center rounded-md text-text-muted hover:bg-surface-hover"><X size={14} /></button>}>
      {!c.rows.length ? <p className="text-[12px] text-text-muted" data-testid="dealdesk-card-list-empty">No deal in this queue.</p> : (
        <div className="max-h-[360px] overflow-auto">
          <table className={tableCls} data-testid={`dealdesk-card-list-${c.key}`}>
            <thead className="sticky top-0 bg-surface"><tr>
              <th className={thCls}>Deal</th><th className={thCls}>Obligor</th><th className={thCls}>Sector</th>
              <th className={cn(thCls, "text-center")}>Rating</th><th className={cn(thCls, "text-right")}>Amount</th>
              <th className={thCls}>RM</th><th className={thCls}>State</th>
              {c.key === "in_review" ? <th className={cn(thCls, "text-right")}>Open queries</th> : null}
              {c.key === "committee" ? <th className={thCls}>Committee</th> : null}
              <th className={cn(thCls, "text-right")}>{c.key === "in_review" ? "Days in review" : "Days"}</th><th className={thCls} /></tr></thead>
            <tbody>{c.rows.map((r) => (
              <tr key={r.proposal_id} onClick={() => onOpen(r.href)} className="cursor-pointer hover:bg-surface-hover"
                  data-testid={`dealdesk-card-row-${r.proposal_id}`}>
                <td className={cn(tdCls, "font-medium text-accent")}>{r.proposal_id}</td>
                <td className={cn(tdCls, "max-w-[16rem] truncate")} title={r.obligor_name}>{r.obligor_name}</td>
                <td className={cn(tdCls, "max-w-[12rem] truncate")} title={r.sector}>{r.sector}</td>
                <td className={cn(tdCls, "text-center font-medium")}>{r.rating}</td>
                <td className={cn(tdCls, "text-right")}>{r.amount_sar_mn === null ? "–" : sar(r.amount_sar_mn)}</td>
                <td className={cn(tdCls, "max-w-[10rem] truncate")} title={r.rm}>{r.rm}</td>
                <td className={tdCls}><Chip tone={stateTone(r.state)}>{r.state_label}</Chip></td>
                {c.key === "in_review" ? <td className={cn(tdCls, "text-right")}>{r.queries_open ?? 0}</td> : null}
                {c.key === "committee" ? <td className={tdCls}>{r.committee_date ? r.committee_date.slice(0, 10) : "Not scheduled"}</td> : null}
                <td className={cn(tdCls, "text-right")}>{r.days ?? "–"}</td>
                <td className={tdCls}><ArrowRight size={13} className="text-text-muted" aria-hidden /></td>
              </tr>))}</tbody>
          </table>
        </div>)}
    </Section>
  );
}

export function LandingCards({ open, onOpenCard }: { open: string; onOpenCard: (key: string) => void }) {
  const router = useRouter();
  const [data, setData] = React.useState<Cards | null>(null);
  const [error, setError] = React.useState("");
  React.useEffect(() => {
    let live = true;
    r12Api.cards().then((d) => { if (live) setData(d); }).catch((e) => { if (live) setError(friendlyMessage(e, "Deal Desk")); });
    return () => { live = false; };
  }, []);
  const go = (c: LandingCard) => {
    // The three origination cards open their list here; the Book and conditions cards open where their data lives.
    if (c.source === "workflow" || c.key === "sme") onOpenCard(open === c.key ? "" : c.key);
    else router.push(c.href);
  };
  const shown = data?.cards.find((c) => c.key === open && c.source === "workflow") ?? null;
  return (
    <div className="space-y-3" data-testid="dealdesk-cards">
      {error ? <p className="text-[12px] text-negative" role="alert">{error}</p> : null}
      {!data && !error ? <Skeleton className="h-7 w-full max-w-3xl" /> : null}
      {data ? (
        <div className="flex flex-wrap items-center gap-1.5" data-testid="dealdesk-cards-row">
          <span className="mr-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-text-muted">Work queues</span>
          {data.cards.map((c) => <Counter key={c.key} c={c} active={open === c.key} onOpen={() => go(c)} />)}
          <span className="relative z-10"><InfoPopover title="Work queues">
            {data.cards.map((c) => <span key={c.key} className="block"><b className="font-medium">{c.title}.</b> {c.info}</span>)}
          </InfoPopover></span>
        </div>) : null}
      {shown ? <CardList c={shown} onClose={() => onOpenCard("")} onOpen={(href) => router.push(href)} /> : null}
    </div>
  );
}
