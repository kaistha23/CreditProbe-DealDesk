"use client";

/**
 * PLAN_R11 R4: conditions as tracked triggers.
 *
 *   <ConditionsTracker dealId="DD-02" />      the deal view's tracker (all deals when dealId is omitted)
 *   <ConditionsDueLine href="/deal-desk/review?view=conditions" />
 *                                             the one-line "Conditions due" count for the Deal Desk landing (Single deal mode)
 *
 * Status comes from data where the trigger has a check (met when it holds); otherwise the trigger is manual and keeps
 * the status set here. Owner, due date, status and note are edited in place and persist in the Deal Desk store.
 */

import * as React from "react";
import Link from "next/link";
import { CalendarClock, Check, ChevronDown, ChevronRight, Database, Hand } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { useLoad } from "@/lib/v5/dealdesk";
import { type CondStatus, type Condition, STATUS_LABEL, STATUS_TONE, reviewApi, sortConditions } from "@/lib/v5/dealdesk-review";

import { Chip, Empty, Section, tableCls, tdCls, thCls } from "./kit";

const wrap = "whitespace-normal";
const KIND_LABEL: Record<Condition["kind"], string> = { CP: "Condition precedent", covenant: "Covenant", watch: "Watch item" };
const EDITABLE: (CondStatus | "auto")[] = ["auto", "met", "waived", "breached"];

function StatusCell({ c, onSaved }: { c: Condition; onSaved: (c: Condition) => void }) {
  const [busy, setBusy] = React.useState(false);
  const set = (v: string) => {
    setBusy(true);
    reviewApi.patch(c.id, { status: v as CondStatus | "auto" }).then((x) => { setBusy(false); onSaved(x); }, () => setBusy(false));
  };
  // The chip is the control: a transparent select over it opens the choices (From data, Met, Waived, Breached).
  return (
    <span className="relative inline-flex" title="Set the status">
      <Chip tone={STATUS_TONE[c.status]} testId="condition-status">{STATUS_LABEL[c.status]}<ChevronDown size={11} aria-hidden /></Chip>
      <select aria-label="Set status" disabled={busy} value="" onChange={(e) => set(e.target.value)} data-testid="condition-set-status"
              className="absolute inset-0 cursor-pointer opacity-0">
        <option value="" disabled>Set status</option>
        {EDITABLE.map((s) => <option key={s} value={s}>{s === "auto" ? "From data" : STATUS_LABEL[s as CondStatus]}</option>)}
      </select>
    </span>
  );
}

function OwnerCell({ c, onSaved }: { c: Condition; onSaved: (c: Condition) => void }) {
  const [v, setV] = React.useState(c.owner);
  const save = () => { if (v !== c.owner) reviewApi.patch(c.id, { owner: v }).then(onSaved, () => setV(c.owner)); };
  return <input aria-label="Owner" value={v} onChange={(e) => setV(e.target.value)} onBlur={save} data-testid="condition-owner"
                className="h-6 w-32 rounded border border-transparent bg-transparent px-1 text-[12px] hover:border-border focus:border-accent" />;
}

const dueShort = (c: Condition) => {
  if (!c.due_date) return c.due_text || "–";
  const d = new Date(`${c.due_date}T00:00:00Z`);
  const txt = d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
  return c.due_text.startsWith("monthly") ? `Monthly · ${txt}` : c.due_text.startsWith("annual") ? `Annual · ${txt}` : txt;
};

function DueCell({ c, onSaved, compact }: { c: Condition; onSaved: (c: Condition) => void; compact: boolean }) {
  if (compact) return <span className="block truncate" title={c.due_text}>{dueShort(c)}</span>;
  const save = (d: string) => { if (d && d !== c.due_date) reviewApi.patch(c.id, { due_date: d }).then(onSaved, () => undefined); };
  return (
    <div className="flex flex-col">
      <input type="date" aria-label="Due date" defaultValue={c.due_date ?? ""} onChange={(e) => save(e.target.value)} data-testid="condition-due"
             className="h-6 w-[128px] rounded border border-transparent bg-transparent px-1 text-[12px] hover:border-border focus:border-accent" />
      {!c.due_date || /^(monthly|annual)/.test(c.due_text) ? <span className="truncate px-1 text-[11px] text-text-muted" title={c.due_text}>{c.due_text}</span> : null}
    </div>
  );
}

/** The tracker: what, type, data source, due, owner, status (from data or manual). */
export function ConditionsTracker({ dealId: dealIdProp, proposalId, compact = false, title = "Conditions" }: {
  /** The deal (DD-nn or a prepared case id); all deals when omitted. `proposalId` is accepted as an alias. */
  dealId?: string; proposalId?: string; compact?: boolean; title?: string;
}) {
  const dealId = dealIdProp ?? proposalId;
  const [rev, setRev] = React.useState(0);
  const r = useLoad(() => reviewApi.conditions(dealId ?? ""), `conditions:${dealId ?? "*"}:${rev}`);
  const [local, setLocal] = React.useState<Record<string, Condition>>({});
  const onSaved = (c: Condition) => { setLocal((m) => ({ ...m, [c.id]: c })); setRev((n) => n + 1); };
  const items = r.data ? sortConditions(r.data.items.map((c) => local[c.id] ?? c)) : [];
  const s = r.data?.summary;
  return (
    <Section title={title} testId="conditions-tracker"
             info={<>Every condition precedent, covenant and watch item from the review becomes a tracked trigger. <b>From data</b>: the trigger has a check
               against the bank&rsquo;s data and shows <i>Met</i> when it holds. <b>Manual</b>: no data source; set the status here. Due within 30 days, or
               before committee or drawdown, reads as <i>Due</i>. Edits persist in the Deal Desk store.</>}
             action={s ? <span className="text-[12px] text-text-secondary" data-testid="conditions-summary">{s.line} · {s.data_evaluated} of {s.total} from data</span> : null}>
      {r.error ? <p role="alert" className="text-[12px] text-negative">{r.error}</p> : null}
      {!r.data && !r.error ? <Skeleton className="h-24 w-full" /> : null}
      {r.data && !items.length ? <Empty>No conditions recorded.</Empty> : null}
      {items.length ? (
        <div className={cn("overflow-auto", compact ? "max-h-[420px]" : "max-h-[calc(100vh-300px)] min-h-[420px]")}>
          <table className={tableCls} data-testid="conditions-table">
            <thead className="sticky top-0 bg-surface"><tr>
              {[...(dealId ? [] : ["Deal"]), "Condition", ...(compact ? [] : ["Type", "Source"]), "Due", ...(compact ? [] : ["Owner"]), "Status"].map((h) => <th key={h} className={thCls}>{h}</th>)}
            </tr></thead>
            <tbody>{items.map((c) => (
              <tr key={c.id} data-testid="condition-row" data-status={c.status}>
                {dealId ? null : <td className={cn(tdCls, "max-w-[160px] truncate")} title={c.deal_name}>{c.deal_name}</td>}
                <td className={cn(tdCls, wrap, compact ? "min-w-[160px]" : "min-w-[220px]")}>
                  <span className="text-text-primary">{c.what}</span>
                  <span className="ml-1.5 inline-flex align-middle text-text-muted" title={c.evaluation === "data" ? "Status from data" : "Manual status"}>
                    {c.evaluation === "data" ? <Database size={12} aria-label="From data" /> : <Hand size={12} aria-label="Manual" />}</span>
                  {compact ? <span className="block text-[11px] text-text-muted">{c.owner}{c.note ? ` · ${c.note}` : ""}</span>
                    : c.note ? <span className="block text-[11px] text-text-muted">{c.note}</span> : null}
                </td>
                {compact ? null : <td className={tdCls}>{KIND_LABEL[c.kind]}</td>}
                {compact ? null : <td className={cn(tdCls, wrap, "max-w-[200px] text-text-secondary")}>{c.source}</td>}
                <td className={cn(tdCls, compact ? "max-w-[130px]" : "max-w-[180px]")}><DueCell c={c} onSaved={onSaved} compact={compact} /></td>
                {compact ? null : <td className={tdCls}><OwnerCell c={c} onSaved={onSaved} /></td>}
                <td className={tdCls}><StatusCell c={c} onSaved={onSaved} /></td>
              </tr>))}</tbody>
          </table>
        </div>) : null}
    </Section>
  );
}

/** One line for the Deal Desk landing: "Conditions due: 11 across 3 deals · 1 overdue  >". Owned by R; mounted by L/U/M in home.tsx. */
export function ConditionsDueLine({ href = "/deal-desk/review?view=conditions" }: { href?: string }) {
  const r = useLoad(() => reviewApi.summary(), "conditions:summary");
  if (r.error || !r.data) return null;
  const s = r.data;
  const tone = s.by_status.overdue || s.by_status.breached ? "text-negative" : s.due ? "text-warning" : "text-text-secondary";
  return (
    <Link href={href} data-testid="conditions-due-line"
          className="inline-flex h-7 items-center gap-1.5 rounded-md px-2 text-[12px] text-text-secondary hover:bg-surface-hover">
      {s.due ? <CalendarClock size={14} className={tone} aria-hidden /> : <Check size={14} className="text-positive" aria-hidden />}
      <span className={cn("font-medium", tone)}>{s.line}</span>
      <ChevronRight size={12} aria-hidden className="text-text-muted" />
    </Link>
  );
}

export function ConditionsPage() {
  return <ConditionsTracker title="Conditions across deals" />;
}
