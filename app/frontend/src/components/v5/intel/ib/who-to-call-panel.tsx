"use client";

/**
 * R13 IB (R14 backlog #7): who to call today — a compact panel for the Early Warning Tools menu.
 *
 * The names needing a call this week, ranked by materiality (EAD weighted by the strength of the evidence), each with the
 * reason and the action; the signals behind a name, with their sources, open on click. Method and data limits behind the (i).
 */

import * as React from "react";

import { Borrower360Button, BorrowerNameLink } from "@/components/v5/ui/borrower-360-link"; // R14 U (K11)
import { FromLink } from "@/components/v5/ui/back-link"; // R14 U (K1)

import { Skeleton } from "@/components/ui/skeleton";
import { useLoad } from "@/lib/v5/dealdesk";
import { fmt } from "@/lib/v5/format";
import { signalChips, sourceLine, urgencyTone } from "@/lib/v5/intel-ib";
import { cn } from "@/lib/utils";

import { PanelWords } from "@/components/v5/panels-g/panel-words";
import { writeCalls } from "@/lib/v5/plain-words-g/book";

import { Chip, Empty, Section, SecondaryButton, tableCls, tdCls, thCls } from "../../dealdesk/kit";
import { ibApi } from "./api";
import { type Scope, ScopeToggle } from "./scope-toggle";

const PAGE = 15;

export function WhoToCallPanel({ onClose }: { onClose?: () => void }) {
  const [signal, setSignal] = React.useState("");
  const [offset, setOffset] = React.useState(0);
  const [open, setOpen] = React.useState("");
  const [scope, setScope] = React.useState<Scope>("material");
  const q = useLoad(() => ibApi.calls({ limit: PAGE, offset, signal, scope }), `calls-${scope}-${signal}-${offset}`);
  const d = q.data;
  const info = d ? (
    <div className="space-y-2 text-[12px]">
      <p>{d.method}</p>
      <p>Data: book {d.as_of.book} · conduct {d.as_of.conduct} · bureau {d.as_of.bureau}</p>
      <p className="font-medium">Data limits</p>
      <ul className="list-disc pl-4">{d.data_limits.map((x) => <li key={x}>{x}</li>)}</ul>
    </div>
  ) : undefined;
  return (
    <Section title="Who to call today" info={info} testId="who-to-call-panel"
             action={onClose ? <SecondaryButton onClick={onClose} data-testid="who-to-call-close">Close</SecondaryButton> : undefined}>
      <PanelWords panel="who-to-call" lines={d ? () => writeCalls(d) : q.error ? [] : null} />
      {q.error ? <p role="alert" className="text-[12px] text-negative">{q.error}</p> : null}
      {!d ? <Skeleton className="h-40 w-full" /> : (
        <div className="space-y-3">
          <div className="flex flex-wrap items-start gap-3">
            <p className="min-w-0 flex-1 text-[13px] text-text-primary" data-testid="calls-summary">{d.summary}</p>
            <ScopeToggle scope={scope} floor={d.materiality_floor_sar_mn} testId="calls-scope"
                         onChange={(s) => { setScope(s); setOffset(0); setOpen(""); }} />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" aria-pressed={!signal} onClick={() => { setSignal(""); setOffset(0); }} data-testid="calls-signal-all"
                    className={cn("h-7 rounded-full border px-3 text-[12px]", !signal ? "border-accent bg-accent-muted text-accent" : "border-border text-text-secondary hover:bg-surface-hover")}>All</button>
            {signalChips(d).map((c) => (
              <button key={c.id} type="button" aria-pressed={signal === c.id} onClick={() => { setSignal(c.id); setOffset(0); }} data-testid={`calls-signal-${c.id}`}
                      className={cn("h-7 rounded-full border px-3 text-[12px]", signal === c.id ? "border-accent bg-accent-muted text-accent" : "border-border text-text-secondary hover:bg-surface-hover")}>
                {c.label} <b className="tabular-nums">{fmt.count(c.count)}</b></button>))}
          </div>
          {d.rows.length === 0 ? <Empty>Nobody to call on this signal.</Empty> : (
            <div className="overflow-x-auto"><table className={tableCls} data-testid="calls-table">
              <thead><tr><th className={thCls}>#</th><th className={thCls}>Name</th><th className={cn(thCls, "text-right")}>EAD</th><th className={thCls}>When</th>
                <th className={thCls}>Reason</th><th className={thCls}>Action</th></tr></thead>
              <tbody>{d.rows.map((r) => (
                <React.Fragment key={r.borrower_id}>
                  <tr className="cursor-pointer align-top hover:bg-surface-hover" onClick={() => setOpen(open === r.borrower_id ? "" : r.borrower_id)} data-testid={`calls-row-${r.borrower_id}`}>
                    <td className={cn(tdCls, "text-text-muted")}>{r.rank}</td>
                    <td className={tdCls}><span className="flex items-start gap-2"><span className="min-w-0"><BorrowerNameLink customerId={r.borrower_id} name={r.borrower_name} from="who-to-call" className="font-medium" /><br /><span className="text-text-muted">{r.sector}</span></span>
                      <Borrower360Button customerId={r.borrower_id} from="who-to-call" className="ml-auto" />{/* R14 U (K11) */}</span></td>
                    <td className={cn(tdCls, "text-right")} title={sourceLine(r.ead_sar_mn.source)}>{fmt.sar(r.ead_sar_mn.value)}</td>
                    <td className={tdCls}><Chip tone={urgencyTone(r.urgency)}>{r.urgency}</Chip></td>
                    <td className={cn(tdCls, "max-w-[300px] whitespace-normal text-text-secondary")}>{r.reason}</td>
                    <td className={cn(tdCls, "max-w-[300px] whitespace-normal text-text-secondary")}>{r.action}</td>
                  </tr>
                  {open === r.borrower_id ? (
                    <tr><td colSpan={6} className="border-b border-border/60 bg-surface-sunken p-3">
                      <ul className="space-y-0.5 text-[12px]" data-testid="calls-signals">{r.signals.map((s) => (
                        <li key={s.id}><b className="text-text-primary">{s.label}</b> · {s.text} <span className="text-text-muted">· {sourceLine(s.value.source)}</span></li>))}</ul>
                      <FromLink href={r.open} from="who-to-call" className="mt-2 inline-block text-[12px] text-accent underline">Open {r.proposal_id ?? r.borrower_id}</FromLink>
                    </td></tr>) : null}
                </React.Fragment>))}</tbody>
            </table></div>)}
          <div className="flex items-center gap-2 text-[12px] text-text-muted">
            <span>{fmt.count(offset + 1)}–{fmt.count(Math.min(offset + PAGE, d.total))} of {fmt.count(d.total)}</span>
            <SecondaryButton className="ml-auto" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Previous</SecondaryButton>
            <SecondaryButton disabled={offset + PAGE >= d.total} onClick={() => setOffset(offset + PAGE)}>Next</SecondaryButton>
          </div>
        </div>)}
    </Section>
  );
}
