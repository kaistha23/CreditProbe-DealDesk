"use client";

/**
 * R16 b: the RM business request studio (PLAN_R16 Part A). The RM picks the customer (or the chat box named it), sees the
 * customer file in brief (documents, the Bank's limits and conduct), types the ask in the chat box and the RM notes, and
 * CreditProbe writes the business request in the bank form: preview by page, Word, Share inside CreditProbe and Trace
 * (every figure with its document or Data Domains row). Deterministic writer (backend/dealdesk/rm_request), no model.
 */

import * as React from "react";
import { RulesApplied } from "@/components/v5/rules/rules-applied";  // Round K
import type { RuleApplied } from "@/lib/v5/dealdesk-rules";
import { ArrowUp, FileDown, FileText, ListTree, RefreshCw, Share2, X } from "lucide-react";

import { PlainWords } from "@/components/v5/ui/plain-words";
import { cn } from "@/lib/utils";

import { Chip, PrimaryButton, SecondaryButton, tableCls, tdCls, thCls } from "../kit";
import { errorText, fileHref, getJson } from "../papers/paper-view";
import { BlockView } from "../proposal/blocks";
import {
  type BrCustomer, type BusinessRequest, type CustomerFile, STATUS_TONE, brUrls, money, pagesOf, traceGroups,
} from "./model";
import { ShareRequestDialog } from "./share-dialog";
import { OpenPaperButton } from "../paperws/open";

const PLACEHOLDER = "Type the ask, e.g. renew all and add a SAR 20m LC line";

function useCustomers() {
  const [rows, setRows] = React.useState<BrCustomer[] | null>(null);
  React.useEffect(() => {
    let live = true;
    getJson<{ customers: BrCustomer[] }>(brUrls.customers()).then((r) => { if (live) setRows(r.customers); }).catch(() => { if (live) setRows([]); });
    return () => { live = false; };
  }, []);
  return rows;
}

function fileLines(f: CustomerFile): string[] {
  const c = f.customer;
  const lim = f.facilities.reduce((a, x) => a + (x.existing_mn ?? 0), 0);
  const l1 = !f.existing
    ? `${c.short ?? c.name} is new to the bank: 0 limits with us today.`
    : f.facilities.length
      ? `${c.short ?? c.name} banks with us: ${f.facilities.length} limits of ${money(lim)}, ${f.accounts_n} accounts.`
      : `${c.short ?? c.name} is a customer (CIF ${c.cif}); 0 limits found in the Bank's data yet.`;
  const l2 = f.conduct_12m.credit_turnover_mn !== null
    ? `Last 12 months: credits ${money(f.conduct_12m.credit_turnover_mn)}, ${f.conduct_12m.returned_cheques_n ?? 0} returned cheque${f.conduct_12m.returned_cheques_n === 1 ? "" : "s"}.`
    : `${f.documents_n} documents uploaded for this customer.`;
  return [l1, l2, `Documents: ${f.counts.received} received, ${f.counts.expired} expired, ${f.counts.missing} missing.`,
          "Type the ask below; add RM notes; then Write."];
}

function CustomerBrief({ f, onOpen }: { f: CustomerFile; onOpen: (rid: string) => void }) {
  const [all, setAll] = React.useState(false);
  const issues = f.checklist.filter((x) => x.status !== "received");
  const shown = all ? f.checklist : issues;
  return (
    <div className="space-y-3" data-testid="br-customer-file">
      <PlainWords lines={fileLines(f)} testId="br-customer-plain-words" />
      {f.facilities.length ? (
        <div>
          <p className="mb-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">Limits with the Bank (SAR m)</p>
          <table className={cn(tableCls, "text-[11px]")} data-testid="br-customer-limits">
            <thead><tr><th className={thCls}>Facility</th><th className={cn(thCls, "text-right")}>Limit</th><th className={cn(thCls, "text-right")}>Outstanding</th></tr></thead>
            <tbody>{f.facilities.map((x) => (
              <tr key={x.facility} title={x.source}><td className={cn(tdCls, "whitespace-normal")}>{x.facility}</td>
                <td className={cn(tdCls, "text-right")}>{x.existing_mn?.toFixed(1) ?? "–"}</td><td className={cn(tdCls, "text-right")}>{x.outstanding_mn?.toFixed(1) ?? "–"}</td></tr>))}
            </tbody>
          </table>
        </div>) : null}
      <div>
        <div className="mb-1 flex items-center justify-between">
          <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">Document checklist</p>
          <button type="button" className="text-[11px] text-accent underline" onClick={() => setAll((x) => !x)} data-testid="br-checklist-toggle">
            {all ? "Only gaps" : `All ${f.checklist.length}`}</button>
        </div>
        <ul className="max-h-64 space-y-1 overflow-auto pr-1" data-testid="br-checklist">
          {shown.map((x, i) => (
            <li key={`${x.doc_type}-${x.subject}-${i}`} className="flex items-start justify-between gap-2 text-[11px]">
              <span className="text-text-secondary">{x.label}{x.subject ? <span className="text-text-muted"> · {x.subject.replace(/_/g, " ")}</span> : null}</span>
              <Chip tone={STATUS_TONE[x.status]}>{x.status}</Chip></li>))}
          {!shown.length ? <li className="text-[11px] text-text-muted">Every required document is on file.</li> : null}
        </ul>
      </div>
      {f.requests.length ? (
        <div>
          <p className="mb-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">Requests written</p>
          <ul className="space-y-1" data-testid="br-previous">
            {f.requests.slice(0, 5).map((r) => (
              <li key={r.request_id} className="text-[11px] text-text-secondary">
                <button type="button" onClick={() => onOpen(r.request_id)} className="text-left hover:underline" data-testid={`br-previous-${r.request_id}`}>
                  <span className="font-medium text-accent">{r.request_id}</span> · {money(r.total_proposed)}{r.status === "shared" ? " · shared" : ""}</button></li>))}
          </ul>
        </div>) : null}
    </div>
  );
}

function TraceView({ p }: { p: BusinessRequest }) {
  const groups = traceGroups(p.figures);
  return (
    <div className="space-y-3 rounded-md border border-border bg-surface p-3" data-testid="br-trace">
      <PlainWords lines={[`Every one of the ${p.figures.length} figures printed comes from ${groups.length} sources: a document (with its id) or a Data Domains row.`,
                          `${p.untraced.length} figures have no source.`, `${p.notes_used.length} RM notes were placed by topic, each marked "as per RM".`]} testId="br-trace-plain-words" />
      {groups.map((g) => (
        <details key={g.source} className="rounded border border-border/70 px-2 py-1">
          <summary className="cursor-pointer text-[11.5px] text-text-primary">{g.source} <span className="text-text-muted">· {g.figures.length}</span></summary>
          <table className={cn(tableCls, "mt-1 text-[11px]")}>
            <thead><tr><th className={thCls}>Section</th><th className={thCls}>Figure</th><th className={cn(thCls, "text-right")}>Printed</th></tr></thead>
            <tbody>{g.figures.map((f, i) => (
              <tr key={i}><td className={tdCls}>{p.sections.find((s) => s.key === f.section)?.heading ?? f.section}</td>
                <td className={cn(tdCls, "whitespace-normal")}>{f.label}</td><td className={cn(tdCls, "text-right")}>{f.text}</td></tr>))}</tbody>
          </table>
        </details>))}
      {p.notes_used.length ? (
        <table className={cn(tableCls, "text-[11px]")} data-testid="br-trace-notes">
          <thead><tr><th className={thCls}>RM note</th><th className={thCls}>Placed in</th></tr></thead>
          <tbody>{p.notes_used.map((n, i) => <tr key={i}><td className={cn(tdCls, "whitespace-normal")}>{n.text}</td><td className={tdCls}>{n.section}</td></tr>)}</tbody>
        </table>) : null}
    </div>
  );
}

export function RequestPreview({ p }: { p: BusinessRequest }) {
  const pages = pagesOf(p);
  let n = 0;
  return (
    <div className="mx-auto max-w-[940px] space-y-4" data-testid="br-preview">
      {pages.map((pg, pi) => (
        <article key={pg.key} className="rounded-md border border-border bg-surface shadow-sm" data-testid={`br-page-${pg.key}`}>
          <div className="grid grid-cols-2 gap-x-3 border-b border-border bg-surface-sunken px-4 py-1.5 text-[10px] text-text-muted sm:grid-cols-4">
            {p.header_line.slice(0, 4).map(([k, v]) => <span key={k} className="truncate"><b className="text-text-secondary">{k}</b> {v}</span>)}
          </div>
          <div className="space-y-3 px-5 py-4">
            {pi === 0 ? <p className="text-[15px] font-semibold text-accent">BUSINESS REQUEST <span className="text-[11px] font-normal text-text-muted">{p.customer} · {p.request_id} · {p.as_of_label}</span></p> : null}
            <div className="rounded-sm bg-accent px-3 py-1 text-[11px] font-semibold text-accent-contrast">{pg.title} <span className="font-normal opacity-80">· {pg.subtitle}</span></div>
            {pg.sections.map((s) => {
              n += 1;
              return (
                <section key={s.key} className="space-y-1.5" data-testid={`br-section-${s.key}`} id={`br-${s.key}`}>
                  <h4 className="text-[13px] font-semibold text-text-primary">{n}. {s.heading}</h4>
                  <div className={cn("space-y-1.5", s.key === "action" && "rounded-sm border-2 border-text-primary/70 p-3")}>
                    {s.blocks.map((b, i) => <BlockView key={i} b={b} />)}
                  </div>
                </section>);
            })}
          </div>
          <div className="border-t border-border px-4 py-1 text-right text-[10px] text-text-muted">Page {pi + 1} of {pages.length}</div>
        </article>))}
    </div>
  );
}

export function BusinessRequestStudio({ initialCustomer, initialAsk, requestId, onClose }: {
  initialCustomer?: string; initialAsk?: string; requestId?: string; onClose: () => void;
}) {
  const customers = useCustomers();
  const [ref, setRef] = React.useState(initialCustomer ?? "");
  const [file, setFile] = React.useState<CustomerFile | null>(null);
  const [fileErr, setFileErr] = React.useState("");
  const [ask, setAsk] = React.useState(initialAsk ?? "");
  const [notes, setNotes] = React.useState("");
  const [paper, setPaper] = React.useState<BusinessRequest | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const [view, setView] = React.useState<"preview" | "trace">("preview");
  const [sharing, setSharing] = React.useState(false);

  React.useEffect(() => {
    if (!requestId) return;
    getJson<BusinessRequest>(brUrls.one(requestId)).then((p) => {
      setPaper(p); setAsk(p.ask_text); setNotes(p.notes_text); setRef(p.customer_key || p.proposal_id);
    }).catch((e: unknown) => setError(errorText(e)));
  }, [requestId]);

  React.useEffect(() => {
    if (!ref) { setFile(null); return; }
    let live = true;
    setFileErr("");
    getJson<CustomerFile>(brUrls.customer(ref)).then((f) => { if (live) setFile(f); }).catch((e: unknown) => { if (live) { setFile(null); setFileErr(errorText(e)); } });
    return () => { live = false; };
  }, [ref]);

  const write = async () => {
    if (!ref || !ask.trim()) return;
    setBusy(true);
    setError("");
    try {
      const p = await getJson<BusinessRequest>(brUrls.write(), { method: "POST", body: JSON.stringify({ customer: ref, ask, notes }) });
      setPaper(p);
      setView("preview");
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  React.useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === "Escape" && !sharing) onClose(); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose, sharing]);

  return (
    <div className="fixed inset-0 z-[65] flex items-stretch justify-center bg-black/40 p-3 sm:p-5" role="dialog" aria-modal="true" aria-label="Business request" data-testid="br-studio">
      <div className="flex w-full max-w-[1320px] flex-col overflow-hidden rounded-xl border border-border bg-surface-sunken shadow-xl">
        <div className="flex flex-wrap items-center gap-3 border-b border-border bg-surface px-4 py-3">
          <FileText size={16} className="text-accent" />
          <h2 className="text-[15px] font-semibold text-text-primary">Business request</h2>
          <select value={(customers ?? []).find((c) => c.key === ref || c.proposal_id === ref)?.key ?? ref} onChange={(e) => { setRef(e.target.value); setPaper(null); }} aria-label="Customer" data-testid="br-customer"
                  className="h-8 min-w-[260px] rounded-md border border-border bg-surface px-2 text-[12px] text-text-primary">
            <option value="">Choose the customer…</option>
            {(customers ?? []).map((c) => <option key={c.key} value={c.key}>{c.name} · {c.existing ? `CIF ${c.cif}` : "new to bank"}</option>)}
            {ref && customers && !customers.some((c) => c.key === ref || c.proposal_id === ref) ? (
              <option value={ref}>{file?.customer.name ?? ref} · {ref}</option>) : null}
          </select>
          {paper ? (
            <div className="ml-auto flex flex-wrap gap-2" data-testid="br-actions">
              <SecondaryButton onClick={() => setView(view === "trace" ? "preview" : "trace")} aria-pressed={view === "trace"} data-testid="br-trace-toggle"><ListTree size={13} /> Trace</SecondaryButton>
              <SecondaryButton onClick={() => setSharing(true)} data-testid="br-share"><Share2 size={13} /> Share</SecondaryButton>
              {/* Round W: revise the request with Noor beside it (versions, marked edits, Word/PDF, provenance) */}
              <OpenPaperButton kind="request" requestId={paper.request_id} label="Revise with Noor" testId="br-workspace" />
              <a href={fileHref(brUrls.docx(paper.request_id))} data-testid="br-word"
                 className="inline-flex h-8 items-center gap-1.5 rounded-md bg-accent px-3 text-[12px] font-medium text-accent-contrast hover:opacity-90"><FileDown size={13} /> Word</a>
            </div>) : <div className="ml-auto" />}
          <button type="button" onClick={onClose} aria-label="Close" data-testid="br-close" className="rounded-md p-1 text-text-muted hover:bg-surface-hover"><X size={16} /></button>
        </div>
        <div className="grid min-h-0 flex-1 grid-cols-1 overflow-hidden lg:grid-cols-[320px_1fr]">
          <aside className="min-h-0 overflow-auto border-b border-border bg-surface p-4 lg:border-b-0 lg:border-r" data-testid="br-side">
            {fileErr ? <p className="text-[12px] text-negative" role="alert">{fileErr}</p> : null}
            {file ? <CustomerBrief f={file} onOpen={(rid) => {
              void getJson<BusinessRequest>(brUrls.one(rid)).then((p) => { setPaper(p); setAsk(p.ask_text); setNotes(p.notes_text); setView("preview"); })
                .catch((e: unknown) => setError(errorText(e)));
            }} /> : !ref ? (
              <PlainWords lines={["Choose 1 customer: CreditProbe reads the uploaded documents and, for an existing customer, the Bank's own data.",
                                  "Type the ask in the chat box and add RM notes.", "CreditProbe writes the business request in the bank form, with Word and Share."]}
                          testId="br-empty-plain-words" />) : <div className="h-40 animate-pulse rounded-md bg-surface-hover" />}
          </aside>
          <div className="min-h-0 min-w-0 space-y-4 overflow-auto p-4" data-testid="br-main">
            <div className="space-y-2 rounded-lg border border-border bg-surface p-3" data-testid="br-composer">
              <div className="flex items-end gap-2">
                <textarea value={ask} onChange={(e) => setAsk(e.target.value)} rows={2} placeholder={PLACEHOLDER} aria-label="The ask" data-testid="br-ask"
                          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void write(); } }}
                          className="min-h-[44px] flex-1 resize-y rounded-md border border-border bg-surface px-3 py-2 text-[13px] text-text-primary outline-none focus:border-accent" />
                <PrimaryButton onClick={() => void write()} disabled={!ref || !ask.trim() || busy} data-testid="br-write" aria-label="Write the business request">
                  {busy ? <RefreshCw size={13} className="animate-spin" /> : <ArrowUp size={13} />} {paper ? "Write again" : "Write"}</PrimaryButton>
              </div>
              <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} placeholder="RM notes (optional): what you know that the file does not"
                        aria-label="RM notes" data-testid="br-notes"
                        className="w-full resize-y rounded-md border border-border bg-surface px-3 py-2 text-[12px] text-text-primary outline-none focus:border-accent" />
              {file?.ask_hint && !ask ? (
                <button type="button" className="text-[11px] text-accent underline" onClick={() => setAsk(file.ask_hint)} data-testid="br-ask-hint">
                  Example: {file.ask_hint}</button>) : null}
              {error ? <p className="text-[12px] text-negative" role="alert">{error}</p> : null}
            </div>
            {busy && !paper ? <div className="h-96 animate-pulse rounded-md bg-surface-hover" /> : null}
            {paper ? (
              <div className="space-y-3">
                <PlainWords lines={paper.plain_words} speak testId="br-plain-words" />
                <RulesApplied applied={(paper as { rules_applied?: RuleApplied[] }).rules_applied} testId="br-rules-applied" />
                {paper.ask.items.length ? (
                  <div className="flex flex-wrap gap-1.5" data-testid="br-ask-items">
                    {paper.ask.items.map((it, i) => <Chip key={i} tone="neutral">{it.action} · {it.facility}{it.amount !== undefined ? ` · ${money(it.amount)}` : ""}</Chip>)}
                    {paper.shared_with ? <Chip tone="positive">shared with {paper.shared_with.split(",").join(", ")}</Chip> : null}
                  </div>) : null}
                {view === "trace" ? <TraceView p={paper} /> : <RequestPreview p={paper} />}
              </div>) : null}
          </div>
        </div>
      </div>
      {sharing && paper ? <ShareRequestDialog p={paper} onClose={() => setSharing(false)}
                                              onShared={(to) => setPaper({ ...paper, shared_with: [...new Set([...(paper.shared_with ?? "").split(",").filter(Boolean), ...to])].join(",") })} /> : null}
    </div>
  );
}

/** The button that opens the studio (Deal Desk header; a customer file's view can pass its customer). */
export function BusinessRequestButton({ customer, label = "Business request", primary }: { customer?: string; label?: string; primary?: boolean }) {
  const [open, setOpen] = React.useState(false);
  const B = primary ? PrimaryButton : SecondaryButton;
  return (
    <>
      <B onClick={() => setOpen(true)} data-testid="dealdesk-business-request"><FileText size={13} /> {label}</B>
      {open ? <BusinessRequestStudio initialCustomer={customer} onClose={() => setOpen(false)} /> : null}
    </>
  );
}
