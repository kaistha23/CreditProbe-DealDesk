"use client";

/**
 * R13 IB (R14 backlog #5): the renewal autopilot — a compact panel for the Book's Tools menu.
 *
 * Every renewal due in the next 90 days is prepared automatically and classified: clean ones carry a one-page note (Word),
 * exceptions carry the criteria that fired and the full paper on request. Exceptions first, by EAD. Method, criteria and
 * data limits sit behind the (i), not on the screen.
 */

import * as React from "react";
import { Download, FileText } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { useLoad } from "@/lib/v5/dealdesk";
import { fmt } from "@/lib/v5/format";
import { type RenewalClass, type RenewalPaper, type RenewalRow, criterionLine, topCriteria } from "@/lib/v5/intel-ib";
import { cn } from "@/lib/utils";

import { PanelWords } from "@/components/v5/panels-g/panel-words";
import { writeRenewals } from "@/lib/v5/plain-words-g/book";

import { Chip, Empty, PrimaryButton, Section, SecondaryButton, tableCls, tdCls, thCls } from "../../dealdesk/kit";
import { ibApi } from "./api";
import { type Scope, ScopeToggle } from "./scope-toggle";

const PAGE = 15;
const LINK = "inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-surface px-3 text-[12px] text-text-secondary hover:bg-surface-hover";

function Detail({ row }: { row: RenewalRow }) {
  const it = useLoad(() => ibApi.renewal(row.facility_id), `renewal-${row.facility_id}`);
  const [paper, setPaper] = React.useState<RenewalPaper | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [err, setErr] = React.useState("");
  if (it.error) return <p role="alert" className="text-[12px] text-negative">{it.error}</p>;
  if (!it.data) return <Skeleton className="h-24 w-full" />;
  const d = it.data;
  if (d.note) {
    return (
      <div className="space-y-2" data-testid="renewal-note">
        <div className="flex items-center gap-2">
          <p className="text-[12px] font-medium text-text-primary">{d.note.recommendation}</p>
          <a href={ibApi.noteDocxHref(row.facility_id)} className={cn(LINK, "ml-auto")} data-testid="renewal-note-docx"><Download size={13} /> Note (Word)</a>
        </div>
        {d.note.sections.filter((s) => s.key === "key_figures" || s.key === "conditions").map((s) => (
          <div key={s.key}>
            <p className="text-[11px] font-medium uppercase tracking-[0.06em] text-text-muted">{s.heading}</p>
            {s.blocks.map((b, i) => b.t === "table" ? (
              <table key={i} className={tableCls}><tbody>{(b.rows ?? []).map((r, j) => (
                <tr key={j}><td className={cn(tdCls, "text-text-secondary")}>{r[0]}</td><td className={tdCls} title={String(r[2] ?? "")}>{r[1]}</td></tr>))}</tbody></table>
            ) : <ol key={i} className="list-decimal pl-5 text-[12px] text-text-secondary">{(b.items ?? []).map((x) => <li key={x}>{x}</li>)}</ol>)}
          </div>))}
      </div>
    );
  }
  const fired = d.review.criteria.filter((c) => c.fired && c.kind === "credit");
  return (
    <div className="space-y-2" data-testid="renewal-exception">
      <ul className="space-y-0.5 text-[12px] text-text-secondary">{fired.map((c) => <li key={c.id} title={c.reads}>{criterionLine(c)}</li>)}</ul>
      {paper?.links ? (
        <div className="flex flex-wrap items-center gap-2 text-[12px]" data-testid="renewal-paper-ready">
          <Chip tone="positive">Paper ready · {paper.proposal_id}</Chip>
          <a href={ibApi.href(paper.links.docx)} className={LINK}><FileText size={13} /> Proposal (Word)</a>
          <a href={ibApi.href(paper.links.pdf)} className={LINK}>PDF</a>
          <a href={paper.links.deal} className={LINK}>Open deal</a>
        </div>
      ) : (
        <PrimaryButton disabled={busy} data-testid="renewal-paper" onClick={() => {
          setBusy(true); setErr("");
          ibApi.renewalPaper(row.facility_id).then(setPaper, (e: unknown) => setErr(e instanceof Error ? e.message : String(e))).finally(() => setBusy(false));
        }}>{busy ? "Preparing the paper…" : "Prepare the full paper"}</PrimaryButton>
      )}
      {paper && !paper.links ? <p className="text-[12px] text-negative">{paper.why}</p> : null}
      {err ? <p role="alert" className="text-[12px] text-negative">{err}</p> : null}
    </div>
  );
}

export function RenewalAutopilotPanel({ onClose }: { onClose?: () => void }) {
  const [cls, setCls] = React.useState<"all" | RenewalClass>("exception");
  const [offset, setOffset] = React.useState(0);
  const [open, setOpen] = React.useState("");
  const [scope, setScope] = React.useState<Scope>("material");
  const q = useLoad(() => ibApi.renewals({ cls, limit: PAGE, offset, scope }), `renewals-${scope}-${cls}-${offset}`);
  const d = q.data;
  const info = d ? (
    <div className="space-y-2 text-[12px]">
      <p>Clean when no credit criterion fires; RAROC below hurdle and unmet promises become renewal conditions on the note.</p>
      <ul className="list-disc pl-4">{d.criteria.map((c) => <li key={c.id}>{c.label} ({c.kind}) · {c.source}</li>)}</ul>
      <p className="font-medium">Data limits</p>
      <ul className="list-disc pl-4">{d.data_limits.map((x) => <li key={x}>{x}</li>)}</ul>
    </div>
  ) : undefined;
  return (
    <Section title="Renewal autopilot" info={info} testId="renewal-autopilot-panel"
             action={onClose ? <SecondaryButton onClick={onClose} data-testid="renewal-autopilot-close">Close</SecondaryButton> : undefined}>
      <PanelWords panel="renewals" lines={d ? () => writeRenewals(d) : q.error ? [] : null} />
      {q.error ? <p role="alert" className="text-[12px] text-negative">{q.error}</p> : null}
      {!d ? <Skeleton className="h-40 w-full" /> : (
        <div className="space-y-3">
          <div className="flex flex-wrap items-start gap-3">
            <p className="min-w-0 flex-1 text-[13px] text-text-primary" data-testid="renewal-summary">{d.summary}</p>
            <ScopeToggle scope={scope} floor={d.materiality_floor_sar_mn} testId="renewal-scope"
                         onChange={(s) => { setScope(s); setOffset(0); setOpen(""); }} />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {(["exception", "clean", "all"] as const).map((k) => (
              <button key={k} type="button" aria-pressed={cls === k} data-testid={`renewal-cls-${k}`} onClick={() => { setCls(k); setOffset(0); setOpen(""); }}
                      className={cn("h-7 rounded-full border px-3 text-[12px]", cls === k ? "border-accent bg-accent-muted text-accent" : "border-border text-text-secondary hover:bg-surface-hover")}>
                {k === "all" ? "All" : k === "clean" ? "Clean" : "Exceptions"} <b className="tabular-nums">{fmt.count(k === "all" ? d.counts.clean + d.counts.exception : d.counts[k])}</b>
              </button>))}
            {cls !== "clean" ? topCriteria(d).map((c) => <Chip key={c.id} tone="warning">{c.label} · {fmt.count(c.count)}</Chip>) : null}
          </div>
          {d.rows.length === 0 ? <Empty>No renewals in this view.</Empty> : (
            <div className="overflow-x-auto"><table className={tableCls} data-testid="renewal-table">
              <thead><tr><th className={thCls}>Borrower</th><th className={thCls}>Renewal</th><th className={cn(thCls, "text-right")}>EAD</th>
                <th className={thCls}>Result</th><th className={thCls}>Why</th></tr></thead>
              <tbody>{d.rows.map((r) => (
                <React.Fragment key={r.facility_id}>
                  <tr className="cursor-pointer hover:bg-surface-hover" onClick={() => setOpen(open === r.facility_id ? "" : r.facility_id)} data-testid={`renewal-row-${r.facility_id}`}>
                    <td className={cn(tdCls, "whitespace-normal")}><span className="font-medium text-text-primary">{r.borrower_name}</span><br /><span className="text-text-muted">{r.facility_id}</span></td>
                    <td className={tdCls}>{r.renewal_date} <span className="text-text-muted">({r.days_to_renewal}d)</span></td>
                    <td className={cn(tdCls, "text-right")}>{fmt.sar(r.ead_sar_mn)}</td>
                    <td className={tdCls}><Chip tone={r.classification === "clean" ? "positive" : "negative"}>{r.classification === "clean" ? "Clean · note" : "Exception · paper"}</Chip></td>
                    <td className={cn(tdCls, "min-w-[220px] whitespace-normal text-text-secondary")}>{r.line}</td>
                  </tr>
                  {open === r.facility_id ? <tr><td colSpan={5} className="border-b border-border/60 bg-surface-sunken p-3"><Detail row={r} /></td></tr> : null}
                </React.Fragment>))}</tbody>
            </table></div>)}
          <div className="flex items-center gap-2 text-[12px] text-text-muted">
            <span>{fmt.count(offset + 1)}–{fmt.count(Math.min(offset + PAGE, d.total))} of {fmt.count(d.total)} · data {d.as_of}</span>
            <SecondaryButton className="ml-auto" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Previous</SecondaryButton>
            <SecondaryButton disabled={offset + PAGE >= d.total} onClick={() => setOffset(offset + PAGE)}>Next</SecondaryButton>
          </div>
        </div>)}
    </Section>
  );
}
