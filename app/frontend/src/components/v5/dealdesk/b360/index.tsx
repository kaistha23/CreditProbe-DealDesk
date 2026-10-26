"use client";

/**
 * Rounds B and G: Borrower 360 inside the deal and the customer file (not a separate screen), with the counterparty exposure
 * the graph reads across deals. Every fact shows where it was read and when (the Bank's data relation, or the document and
 * page). Built from Deal Desk's own kit (Section, Chip, table classes); no new styling.
 *
 *   <DealBorrower360 proposalId="R16-C2" onClose={…} />     the panel on the deal (?b360=1)
 *   <CustomerBorrower360 cif="CB09001" />                     the customer file (/deal-desk/customer-packs?cif=…)
 *   <CounterpartyLine proposalId="R16-C2" onOpen={…} />       one line on the deal when the graph has a signal
 */

import * as React from "react";
import Link from "next/link";
import { AlertTriangle, Network, RefreshCw, Trash2, X } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { PlainWords } from "@/components/v5/ui/plain-words";
import { cn } from "@/lib/utils";
import {
  type B360Section, type Borrower360, type Signal, type SignalSummary, type Table, RULE_LABEL, SEVERITY_TONE, b360Api, cellUnit, evidenceLine,
  fmtValue, signalLine, sourceLine, tabs,
} from "@/lib/v5/dealdesk-b360";

import { Chip, Empty, SecondaryButton, Section, tableCls, tdCls, thCls } from "../kit";

function SourceNote({ text, testId }: { text: string; testId?: string }) {
  return <p className="mt-1 text-[11px] text-text-muted" data-testid={testId}>Source: {text}</p>;
}

function Facts({ s }: { s: B360Section }) {
  if (!s.facts.length) return null;
  return (
    <div className="grid grid-cols-2 gap-2 md:grid-cols-4" data-testid={`b360-facts-${s.key}`}>
      {s.facts.map((f, i) => (
        <div key={`${f.label}-${i}`} className="min-w-0 rounded-md border border-border px-3 py-2" title={f.note || sourceLine(f.source)} data-testid="b360-fact">
          <p className="truncate text-[11px] text-text-muted">{f.label}</p>
          <p className="truncate text-[15px] font-semibold tabular-nums text-text-primary">{fmtValue(f.value, f.unit)}</p>
          <p className="truncate text-[10px] text-text-muted" data-testid="b360-fact-source">{sourceLine(f.source)}</p>
        </div>))}
    </div>
  );
}

function DataTable({ t }: { t: Table }) {
  return (
    <div className="min-w-0" data-testid={`b360-table-${t.id}`}>
      <h3 className="mb-1 text-[12px] font-medium text-text-secondary">{t.title}</h3>
      <div className="overflow-auto">
        <table className={tableCls}>
          <thead><tr>{t.columns.map((c) => <th key={c.key} className={cn(thCls, /sar|pct|number|count|days/.test(c.unit) && "text-right")}>{c.label}</th>)}</tr></thead>
          <tbody>{t.rows.map((r, i) => (
            <tr key={i} data-synthetic={r.synthetic ? "true" : undefined}>
              {t.columns.map((c) => {
                const u = cellUnit(c, r);
                return <td key={c.key} className={cn(tdCls, /sar|pct|number|count|days/.test(u) ? "text-right" : "whitespace-normal")}>{fmtValue(r[c.key], u)}</td>;
              })}
            </tr>))}
          </tbody>
        </table>
      </div>
      <SourceNote text={sourceLine(t.source)} />
    </div>
  );
}

function SectionView({ s }: { s: B360Section }) {
  return (
    <div className="space-y-3" data-testid={`b360-section-${s.key}`}>
      {s.plain_words.length ? <PlainWords lines={s.plain_words} testId={`b360-words-${s.key}`} gloss={false} /> : null}
      {s.empty ? <Empty>{s.empty}</Empty> : null}
      <Facts s={s} />
      {s.tables.map((t) => <DataTable key={t.id} t={t} />)}
    </div>
  );
}

export function SignalList({ signals, onRemoved }: { signals: Signal[]; onRemoved?: () => void }) {
  const [busy, setBusy] = React.useState("");
  if (!signals.length) {
    return <Empty>No counterparty of this customer is in difficulty or in another deal, as far as the documents and the Bank&apos;s data show.</Empty>;
  }
  const remove = async (edgeId: string) => {
    if (!window.confirm("Remove this link from the graph? It stays removed, with your name and today's date.")) return;
    setBusy(edgeId);
    try { await b360Api.removeLink(edgeId); onRemoved?.(); } catch { /* the link stays */ } finally { setBusy(""); }
  };
  return (
    <ul className="space-y-2" data-testid="b360-signals">
      {signals.map((s) => (
        <li key={s.signal_id} className="rounded-md border border-border px-3 py-2" data-testid="b360-signal" data-severity={s.severity} data-rule={s.rule}>
          <div className="flex flex-wrap items-center gap-2">
            <Chip tone={SEVERITY_TONE[s.severity]}>{s.severity === "high" ? "High" : s.severity === "medium" ? "Medium" : "Joined"}</Chip>
            <Chip>{RULE_LABEL[s.rule] ?? s.rule}</Chip>
            {s.other_deals.map((o) => (
              <Link key={o.proposal_id} href={`/deal-desk/${encodeURIComponent(o.proposal_id)}?b360=1`} className="text-[11px] text-accent hover:underline"
                    data-testid="b360-signal-deal">{o.proposal_id}{o.status ? ` · ${o.status.replace(/_/g, " ")}` : ""}</Link>))}
            {s.counterparty.cif ? <Link href={`/deal-desk/customer-packs?cif=${encodeURIComponent(s.counterparty.cif)}`} className="text-[11px] text-accent hover:underline">
              {s.counterparty.name}&apos;s file</Link> : null}
            {s.synthetic ? <Chip tone="warning" title="A link seeded for the trial (fictional), marked in the graph">Seeded link</Chip> : null}
          </div>
          <p className="mt-1 text-[13px] text-text-primary" data-testid="b360-signal-text">{s.title}.</p>
          <div className="mt-1 space-y-0.5 text-[11px] text-text-muted">
            {s.standing[0] ? <p>Standing: {s.standing[0].note || s.standing[0].label} — {sourceLine({ label: s.standing[0].source_label, doc_label: s.standing[0].doc_label ?? undefined,
                                                                                                     page: s.standing[0].page, date: s.standing[0].date ?? null })}</p> : null}
            {s.evidence.slice(0, 3).map((e) => (
              <p key={e.edge_id} className="flex items-center gap-2" data-testid="b360-signal-evidence">
                <span>Link: {evidenceLine(e)}</span>
                <button type="button" onClick={() => void remove(e.edge_id)} disabled={busy === e.edge_id} aria-label="Remove this link"
                        className="inline-flex items-center text-text-muted hover:text-negative" title="Remove this link"><Trash2 size={11} /></button>
              </p>))}
          </div>
        </li>))}
    </ul>
  );
}

export function Borrower360Panel({ data, onRefresh, onClose, testId = "b360-panel" }: {
  data: Borrower360; onRefresh?: () => void; onClose?: () => void; testId?: string;
}) {
  const [tab, setTab] = React.useState<string>(data.signals_summary.high ? "counterparty" : "overview");
  const list = tabs(data.sections, data.signals_summary);
  const sec = data.sections.find((s) => s.key === tab);
  const sj = data.subject;
  return (
    <Section title={`Borrower 360 — ${sj.name}`} testId={testId}
             info="What the Bank holds on this customer (LOS, core banking, bureau, limits and utilisation, conduct, group, past deals and proposals) and what the uploads have taught the system, each fact with its source and date. Counterparty exposure reads the graph of every upload and the Bank's data across deals."
             action={<>
               {onRefresh ? <SecondaryButton onClick={onRefresh} data-testid="b360-refresh" title="Read again past the ten-minute cache"><RefreshCw size={12} /> Refresh</SecondaryButton> : null}
               {onClose ? <SecondaryButton onClick={onClose} data-testid="b360-close" aria-label="Close Borrower 360"><X size={12} /> Close</SecondaryButton> : null}
             </>}>
      <div className="mb-3 flex flex-wrap gap-1.5">
        {sj.cif ? <Chip tone="accent">{sj.existing ? `Existing · ${sj.cif}` : `New to bank · ${sj.cif}`}</Chip> : <Chip>New to bank</Chip>}
        {sj.cr_number ? <Chip>CR {sj.cr_number}</Chip> : null}{sj.sector ? <Chip>{sj.sector}</Chip> : null}
        {sj.rating ? <Chip>{sj.rating}</Chip> : null}{sj.group_name ? <Chip>{sj.group_name}</Chip> : null}
        <Chip title="The Bank's data as at">Bank data as at {data.as_of_label}</Chip>
      </div>
      <div className="mb-3 flex flex-wrap gap-1 border-b border-border pb-2" role="tablist" aria-label="Borrower 360" data-testid="b360-tabs">
        {list.map((t) => (
          <button key={t.key} type="button" role="tab" aria-selected={tab === t.key} onClick={() => setTab(t.key)} data-testid={`b360-tab-${t.key}`}
                  className={cn("h-7 rounded px-2.5 text-[12px]", tab === t.key ? "bg-accent font-medium text-accent-contrast" : "text-text-secondary hover:bg-surface-hover")}>
            {t.label}{t.count ? <span className="ml-1 tabular-nums opacity-80">{t.count}</span> : null}</button>))}
      </div>
      {tab === "overview" ? (
        <div className="space-y-3" data-testid="b360-overview">
          <PlainWords lines={data.plain_words} testId="b360-words" gloss={false} />
          <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-4">
            {data.sections.map((s) => (
              <button key={s.key} type="button" onClick={() => setTab(s.key)} data-testid={`b360-card-${s.key}`}
                      className="rounded-md border border-border px-3 py-2 text-left hover:bg-surface-hover">
                <p className="text-[12px] font-medium text-text-primary">{s.title}</p>
                <p className="mt-0.5 text-[11px] text-text-muted">{s.empty || `${s.n} facts · ${s.facts[0] ? `${s.facts[0].label}: ${fmtValue(s.facts[0].value, s.facts[0].unit)}` : ""}`}</p>
              </button>))}
          </div>
        </div>) : null}
      {tab === "counterparty" ? (
        <div className="space-y-2" data-testid="b360-counterparty">
          <p className="text-[12px] text-text-secondary">
            {data.signals_summary.total
              ? `${data.signals_summary.total} signal${data.signals_summary.total === 1 ? "" : "s"}: ${data.signals_summary.high} high, ${data.signals_summary.medium} medium, ${data.signals_summary.low} joined to other deals.`
              : "The graph links this customer to its buyers, suppliers, guarantors, owners and group from every document read and the Bank's data."}
          </p>
          <SignalList signals={data.signals} onRemoved={onRefresh} />
        </div>) : null}
      {sec ? <SectionView s={sec} /> : null}
    </Section>
  );
}

function useLoad(load: (refresh: boolean) => Promise<Borrower360>, key: string) {
  const [data, setData] = React.useState<Borrower360 | null>(null);
  const [err, setErr] = React.useState("");
  const run = React.useCallback((refresh: boolean) => {
    setErr("");
    if (refresh) setData(null);
    load(refresh).then(setData).catch((e: Error) => setErr(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  React.useEffect(() => { setData(null); run(false); }, [run]);
  return { data, err, refresh: () => run(true) };
}

export function DealBorrower360({ proposalId, onClose }: { proposalId: string; onClose?: () => void }) {
  const { data, err, refresh } = useLoad((r) => b360Api.deal(proposalId, r), proposalId);
  if (err) return <p className="text-[12px] text-negative" role="alert" data-testid="b360-error">{err}</p>;
  if (!data) return <Skeleton className="h-48 w-full" data-testid="b360-loading" />;
  return <Borrower360Panel data={data} onRefresh={refresh} onClose={onClose} testId="dealdesk-b360" />;
}

export function CustomerBorrower360({ cif }: { cif: string }) {
  const { data, err, refresh } = useLoad((r) => b360Api.customer(cif, r), cif);
  if (err) return <p className="text-[12px] text-negative" role="alert" data-testid="b360-error">{err}</p>;
  if (!data) return <Skeleton className="h-48 w-full" data-testid="b360-loading" />;
  return <Borrower360Panel data={data} onRefresh={refresh} testId="customer-b360" />;
}

/** One line on the deal when the graph holds a high or medium counterparty signal for its borrower. */
export function CounterpartyLine({ proposalId, onOpen }: { proposalId: string; onOpen: () => void }) {
  const [sig, setSig] = React.useState<{ signals: Signal[]; summary: SignalSummary } | null>(null);
  React.useEffect(() => {
    let live = true;
    b360Api.dealSignals(proposalId).then((s) => { if (live) setSig(s); }).catch(() => undefined);
    return () => { live = false; };
  }, [proposalId]);
  if (!sig || !(sig.summary.high + sig.summary.medium)) return null;
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-warning/40 bg-warning-muted px-3 py-2 text-[12px]" data-testid="dealdesk-counterparty-line">
      {sig.summary.high ? <AlertTriangle size={14} className="shrink-0 text-negative" aria-hidden /> : <Network size={14} className="shrink-0 text-warning" aria-hidden />}
      <span className="font-semibold text-text-primary">Counterparty exposure</span>
      <span className="min-w-0 flex-1 break-words text-text-secondary">{signalLine(sig.signals)}</span>
      <SecondaryButton onClick={onOpen} data-testid="dealdesk-counterparty-open">Open Borrower 360</SecondaryButton>
    </div>
  );
}
