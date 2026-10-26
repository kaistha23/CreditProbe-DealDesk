"use client";

/**
 * Round A: the agentic intake (the Credit Request Agent, docs/v5/reference/credit-request-agent.html) as the first step of
 * New proposal → Customer documents. The RM drops the whole pack (ZIP or files: PDF, Word, Excel, CSV, photos, scans), states
 * the ask and the RM notes, presses once, and watches three steps with their timings:
 *   1. Read and classify each document (the model and R16's reader, reconciled)
 *   2. Check the file against the checklist (rules: received / missing / expired, completeness, what cannot be assessed,
 *      the delta and "Now covered since the last run" when documents are added and the agent runs again)
 *   3. Draft the business request (streamed; every figure cited; figures not in the evidence removed)
 * Beside the paper: Revise by instruction and Word. The deal is opened or created from the file by the parent, as R16 does.
 */

import * as React from "react";
import { AlertTriangle, Check, FileDown, FileText, FileUp, Loader2, Sparkles, X } from "lucide-react";

import { cn } from "@/lib/utils";
import {
  ACCEPT, type AgentCheck, type AgentDoc, type AgentRun, type AgentStep, agentIntake, citeTitle, gapLine, inline, isAccepted, isCritical,
  isLive, type MdBlock, mergeFiles, meter, parseMd, RECON, readCounts, secs,
} from "@/lib/v5/dealdesk-agent-intake";
import { friendlyMessage } from "@/lib/v5/errors";

import { Chip, PrimaryButton, SecondaryButton, Section } from "../kit";

const label = "text-[11px] font-medium uppercase tracking-[0.08em] text-text-muted";
const input = "w-full rounded-md border border-border bg-surface px-2.5 py-2 text-[13px] text-text-primary placeholder:text-text-muted focus:border-accent focus:outline-none";

// ------------------------------------------------------------------------------------------------ the paper
function Inline({ text, docs }: { text: string; docs: AgentDoc[] }) {
  return <>{inline(text).map((s, i) => s.t === "bold" ? <strong key={i}>{s.text}</strong>
    : s.t === "cite" ? <span key={i} className="whitespace-nowrap font-mono text-[10.5px] text-accent" title={citeTitle(s.text, docs)} data-testid="agent-cite">{s.text}</span>
      : s.t === "removed" ? <span key={i} className="rounded bg-negative-muted px-1 text-[11px] text-negative" title="This figure is not in the evidence it cites, so it was removed" data-testid="agent-removed">figure removed</span>
        : <React.Fragment key={i}>{s.text}</React.Fragment>)}</>;
}

function Paper({ md, docs, streaming }: { md: string; docs: AgentDoc[]; streaming: boolean }) {
  const blocks = React.useMemo(() => parseMd(md), [md]);
  const groups: { gaps: boolean; items: MdBlock[] }[] = [];
  for (const b of blocks) {
    const g = "inGaps" in b && b.inGaps;
    if (!groups.length || groups[groups.length - 1].gaps !== g) groups.push({ gaps: g, items: [] });
    groups[groups.length - 1].items.push(b);
  }
  const one = (b: MdBlock, i: number) => {
    switch (b.t) {
      case "h1": return <h1 key={i} className="mb-3 text-[18px] font-semibold text-text-primary">{b.text}</h1>;
      case "h2": return <h2 key={i} className={cn("mb-2 mt-5 border-b pb-1 text-[12px] font-semibold uppercase tracking-[0.06em]",
                                                 b.gaps ? "border-negative/40 text-negative" : "border-border text-accent")}>{b.text}</h2>;
      case "h3": return <h3 key={i} className="mb-1 mt-3 text-[13px] font-semibold text-text-primary">{b.text}</h3>;
      case "p": return <p key={i} className={cn("mb-2 max-w-[78ch]", b.completeness && "rounded-md bg-warning-muted px-3 py-2 text-[13px]")}
                          data-testid={b.completeness ? "agent-paper-completeness" : undefined}><Inline text={b.text} docs={docs} /></p>;
      case "ul": return <ul key={i} className="mb-2 list-disc space-y-0.5 pl-5">{b.items.map((x, j) => <li key={j}><Inline text={x} docs={docs} /></li>)}</ul>;
      case "table": return (
        <div key={i} className="mb-3 overflow-x-auto">
          <table className="w-full border-collapse font-sans text-[12px] tabular-nums">
            <thead><tr>{b.header.map((h, j) => <th key={j} className="border border-border bg-accent-muted px-2 py-1 text-left font-semibold"><Inline text={h} docs={docs} /></th>)}</tr></thead>
            <tbody>{b.rows.map((r, j) => <tr key={j}>{r.map((c, k) => <td key={k} className="border border-border px-2 py-1 align-top"><Inline text={c} docs={docs} /></td>)}</tr>)}</tbody>
          </table>
        </div>);
    }
  };
  return (
    <article className="rounded-lg border border-border bg-surface px-6 py-5 font-serif text-[14.5px] leading-6 text-text-primary" data-testid="agent-paper">
      {groups.map((g, gi) => g.gaps
        ? <div key={gi} className="mb-3 rounded-md bg-negative-muted/60 px-3 py-2 font-sans text-[13px]" data-testid="agent-paper-gaps">{g.items.map(one)}</div>
        : <React.Fragment key={gi}>{g.items.map(one)}</React.Fragment>)}
      {streaming ? <span className="ml-1 inline-block h-4 w-1.5 animate-pulse bg-accent align-middle" aria-hidden /> : null}
    </article>
  );
}

// ------------------------------------------------------------------------------------------------ steps
function Dot({ s }: { s: AgentStep["status"] }) {
  if (s === "running") return <Loader2 size={15} className="mt-0.5 animate-spin text-accent" aria-label="running" />;
  if (s === "done") return <span className="mt-0.5 inline-flex size-[15px] items-center justify-center rounded-full bg-positive text-white"><Check size={10} strokeWidth={3} /></span>;
  if (s === "warn") return <span className="mt-0.5 inline-block size-[15px] rounded-full bg-warning" aria-label="done with warnings" />;
  if (s === "failed") return <span className="mt-0.5 inline-flex size-[15px] items-center justify-center rounded-full bg-negative text-white"><X size={10} strokeWidth={3} /></span>;
  return <span className="mt-0.5 inline-block size-[15px] rounded-full border-2 border-border" aria-label="pending" />;
}

function ReadDetail({ run }: { run: AgentRun }) {
  const [open, setOpen] = React.useState<string | null>(null);
  return (
    <ul className="mt-2 space-y-1" data-testid="agent-read-docs">
      {run.documents.map((d) => (
        <li key={d.id} className="text-[12px]" data-testid="agent-read-doc" data-status={d.status} data-recon={d.recon?.status ?? ""}>
          <button type="button" className="flex w-full items-start gap-2 text-left hover:text-text-primary" onClick={() => setOpen(open === d.id ? null : d.id)}>
            <span className="w-8 shrink-0 font-mono text-accent">{d.id}</span>
            <span className="min-w-0 flex-1 text-text-secondary">
              {d.status === "reading" ? `reading ${d.name}…` : d.status === "failed" ? `${d.name} — could not be read (${d.error})`
                : <>{d.result?.doc_type}{d.result?.period_or_date ? ` · ${d.result.period_or_date}` : ""}{!d.new ? <span className="text-text-muted"> · last run</span> : null}</>}
            </span>
            {d.recon ? <Chip tone={RECON[d.recon.status].tone}>{RECON[d.recon.status].label}</Chip> : null}
          </button>
          {open === d.id && d.result ? (
            <div className="ml-10 mt-1 space-y-1 rounded-md bg-surface-sunken p-2 text-[11.5px] text-text-secondary" data-testid="agent-read-doc-detail">
              <p><span className="text-text-muted">File:</span> {d.name} · {d.method}{d.result.entity ? ` · ${d.result.entity}` : ""}{d.result.expiry_date ? ` · expires ${d.result.expiry_date}` : ""}</p>
              {d.result.summary ? <p>{d.result.summary}</p> : null}
              {d.recon?.notes.map((n, i) => <p key={i} className="text-warning">{n}</p>)}
              {d.result.key_figures.length ? (
                <p><span className="text-text-muted">Key figures:</span> {d.result.key_figures.slice(0, 12).map((f) => `${f.label}: ${f.value}${f.page ? ` (p. ${f.page})` : ""}`).join(" · ")}
                  {d.result.key_figures.length > 12 ? ` · +${d.result.key_figures.length - 12}` : ""}</p>) : null}
              {d.recon?.rejected.length ? <p className="text-negative">Rejected (not in the document): {d.recon.rejected.map((f) => `${f.label} ${f.value}`).join(" · ")}</p> : null}
              {d.result.observations.length ? <ul className="list-disc pl-4">{d.result.observations.map((o, i) => <li key={i}>{o}</li>)}</ul> : null}
            </div>) : null}
        </li>))}
      {run.skipped.length ? <li className="text-[11.5px] text-text-muted">Skipped: {run.skipped.join("; ")}</li> : null}
    </ul>
  );
}

function CheckDetail({ c }: { c: AgentCheck }) {
  const m = meter(c);
  const band = m.band === "hi" ? "bg-positive" : m.band === "mid" ? "bg-warning" : "bg-negative";
  const lo = m.prev !== null ? Math.min(m.prev, m.pct) : 0;
  return (
    <div className="mt-2 space-y-2" data-testid="agent-check">
      <div className="max-w-md">
        <div className="flex justify-between text-[13px]">
          <b className="text-text-primary" data-testid="agent-meter">{m.title.replace(/\((\+?-?\d+)\)$/, "")}{m.delta !== null
            ? <em className={cn("not-italic", m.delta > 0 ? "text-positive" : "text-negative")}>({m.delta > 0 ? "+" : ""}{m.delta})</em> : null}</b>
          <span className="text-text-muted">{m.crit}</span>
        </div>
        <div className="mt-1 flex h-2 overflow-hidden rounded bg-border" role="img" aria-label={m.title}>
          {m.prev !== null ? <i className={cn("block h-full opacity-45", band)} style={{ width: `${lo}%` }} /> : null}
          <i className={cn("block h-full", band)} style={{ width: `${Math.max(0, m.pct - lo)}%` }} />
        </div>
      </div>
      {c.now_covered.length ? (
        <div className="text-[12.5px]" data-testid="agent-now-covered">
          <b className="text-text-primary">Now covered since the last run</b>
          <ul className="mt-0.5 list-disc pl-5 text-positive">{c.now_covered.map((x) => <li key={x.item}>{x.text}</li>)}</ul>
        </div>) : null}
      {c.comp.gaps.length ? (
        <div className="text-[12.5px]" data-testid="agent-cannot">
          <b className="text-text-primary">What I cannot assess with this file</b>
          <p className="text-[11.5px] text-text-muted"><span className="font-semibold text-negative">Red: critical</span>, Credit would normally return the request without it. Grey: important, it weakens the request.</p>
          <ul className="mt-0.5 list-disc space-y-0.5 pl-5">{c.comp.gaps.map((g) => (
            <li key={g.item + g.because} className={isCritical(g) ? "text-negative" : "text-text-secondary"} data-testid="agent-gap" data-critical={isCritical(g) ? "1" : "0"}>{gapLine(g)}</li>))}</ul>
        </div>) : null}
      <p className="text-[12px] text-text-secondary">{c.received.length} of {c.total} received · {c.missing.length} missing · {c.expired.length} expired</p>
      <div className="flex flex-wrap gap-1" data-testid="agent-check-chips">
        {c.lines.filter((l) => l.status === "expired").map((l) => <Chip key={l.id} tone="warning">Expired: {l.label} ({l.note})</Chip>)}
        {c.lines.filter((l) => l.status === "missing").map((l) => <Chip key={l.id} tone="negative">Missing: {l.label}</Chip>)}
        {c.lines.filter((l) => l.status === "received").map((l) => <Chip key={l.id} tone="positive">{l.label}</Chip>)}
      </div>
    </div>
  );
}

function Steps({ run, elapsed }: { run: AgentRun | null; elapsed: string }) {
  const steps: AgentStep[] = run?.steps ?? [
    { key: "read", title: "Read and classify each document", status: "pending", ms: null, started_at: null, detail: "Extracts dates, figures and credit observations from every file, including photos and scanned PDFs." },
    { key: "check", title: "Check the file against the checklist", status: "pending", ms: null, started_at: null, detail: "Marks each required document as received, missing or expired." },
    { key: "draft", title: "Draft the business request", status: "pending", ms: null, started_at: null, detail: "Writes the RM's request to Credit, citing the source document for every figure." },
  ];
  return (
    <Section title="Agent run" testId="agent-run"
             action={<span className="font-mono text-[11.5px] text-text-muted" data-testid="agent-elapsed">{elapsed}</span>}
             info="Step 1 reads every document twice: the model (text, or the page images for photos and scans) and CreditProbe's rule reader with OCR; the two are reconciled. Step 2 is rules only. Step 3 is the model writing, with every figure checked against the documents.">
      <ol>
        {steps.map((s, i) => (
          <li key={s.key} className={cn("grid grid-cols-[22px_minmax(0,1fr)_auto] gap-2 py-2.5", i && "border-t border-border")}
              data-testid={`agent-step-${s.key}`} data-status={s.status}>
            <Dot s={s.status} />
            <div className="min-w-0">
              <h4 className="text-[13.5px] font-semibold text-text-primary">{i + 1}. {s.title}</h4>
              <p className="mt-0.5 text-[12.5px] text-text-secondary" data-testid={`agent-step-${s.key}-detail`}>{s.detail}</p>
              {run && s.key === "read" && run.documents.length ? <ReadDetail run={run} /> : null}
              {run && s.key === "check" && run.check ? <CheckDetail c={run.check} /> : null}
            </div>
            <time className="font-mono text-[11.5px] text-text-muted" data-testid={`agent-step-${s.key}-time`}>{secs(s.ms)}</time>
          </li>))}
      </ol>
      {run?.model ? (
        <p className="mt-1 text-[11.5px] text-text-muted" data-testid="agent-model-line">
          {run.model.model_available
            ? `Model: ${run.model.model} · ${run.model_summary?.calls ?? 0} calls · ${(run.model_summary?.input_tokens ?? 0).toLocaleString()} tokens in, ${(run.model_summary?.output_tokens ?? 0).toLocaleString()} out · run ${run.run_id}`
            : `No model key on this installation: the rule reader (with OCR) read the documents and the request is written by rules · run ${run.run_id}`}</p>) : null}
    </Section>
  );
}

// ------------------------------------------------------------------------------------------------ the agent
export function AgentIntake({ onRun, footer }: {
  /** called when a run finishes (the parent shows R16's customer file and the open / create actions) */
  onRun?: (run: AgentRun) => void; footer?: React.ReactNode;
}) {
  const [files, setFiles] = React.useState<File[]>([]);
  const [ask, setAsk] = React.useState("");
  const [notes, setNotes] = React.useState("");
  const [run, setRun] = React.useState<AgentRun | null>(null);
  const [status, setStatus] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [over, setOver] = React.useState(false);
  const [revise, setRevise] = React.useState("");
  const [t0, setT0] = React.useState<number | null>(null);
  const [now, setNow] = React.useState(0);
  const live = isLive(run);
  const onRunRef = React.useRef(onRun);
  onRunRef.current = onRun;

  // poll the run while it works
  React.useEffect(() => {
    if (!run || !live) return;
    const t = setTimeout(() => {
      void agentIntake.get(run.run_id).then((r) => {
        setRun(r);
        if (!isLive(r)) {
          setStatus(r.status === "failed" ? `The run failed: ${r.error}` : `Done in ${secs(r.elapsed_ms)}.`);
          if (r.status === "done") onRunRef.current?.(r);
        }
      }).catch((e) => setStatus(friendlyMessage(e)));
    }, 600);
    return () => clearTimeout(t);
  }, [run, live]);
  React.useEffect(() => {
    if (!live) return;
    const i = setInterval(() => setNow(Date.now()), 200);
    return () => clearInterval(i);
  }, [live]);

  const add = (list: FileList | File[] | null) => {
    if (!list) return;
    const arr = Array.from(list);
    const ok = arr.filter((f) => isAccepted(f.name));
    const m = mergeFiles(files, ok);
    setFiles(m.files);
    const bad = arr.length - ok.length;
    setStatus(`${m.files.length} new document${m.files.length === 1 ? "" : "s"} ready${m.dup ? ` · ${m.dup} duplicate${m.dup === 1 ? "" : "s"} skipped` : ""}${bad ? ` · ${bad} not supported` : ""}.`);
  };
  const loadSample = async () => {
    setBusy(true); setStatus("Loading the sample deal…");
    try {
      const m = await agentIntake.sample();
      const fs = await agentIntake.sampleFiles(m);
      setRun(null); setFiles(fs); setAsk(m.ask); setNotes(m.notes);
      setStatus(`Sample: fictional deal loaded, ${fs.length} documents (${m.customer}). Press Run the agent.`);
    } catch (e) { setStatus(friendlyMessage(e)); } finally { setBusy(false); }
  };
  const start = async () => {
    if (!ask.trim()) { setStatus("State the ask first."); return; }
    if (!files.length && !run) { setStatus("Add at least one document."); return; }
    setBusy(true); setStatus("Uploading the pack…");
    try {
      const r = await agentIntake.start(files, { ask, notes, parentRunId: run?.status === "done" ? run.run_id : undefined });
      setRun(r); setFiles([]); setT0(Date.now()); setNow(Date.now()); setStatus("The agent is working…");
      if (!isLive(r) && r.status === "done") onRunRef.current?.(r);
    } catch (e) { setStatus(friendlyMessage(e)); } finally { setBusy(false); }
  };
  const doRevise = async () => {
    if (!run || !revise.trim()) return;
    setBusy(true);
    try { const r = await agentIntake.revise(run.run_id, revise.trim()); setRun(r); setRevise(""); setT0(Date.now()); setStatus(`Revising: ${revise.trim()}`); }
    catch (e) { setStatus(friendlyMessage(e)); } finally { setBusy(false); }
  };
  const elapsed = live && t0 ? secs(now - t0) : run?.elapsed_ms ? secs(run.elapsed_ms) : "";
  const draft = run?.draft;
  const md = draft ? (draft.status === "streaming" ? draft.text : draft.md || draft.text) : "";
  const rerun = run?.status === "done";

  return (
    <div className="space-y-4" data-testid="agent-intake">
      <div className="grid gap-4 lg:grid-cols-[minmax(0,320px)_minmax(0,1fr)]">
        {/* the deal file */}
        <div className="space-y-3" data-testid="agent-form">
          <div className="flex items-center gap-2">
            <span className={label}>Documents</span>
            <SecondaryButton className="ml-auto" onClick={() => void loadSample()} disabled={busy || live} data-testid="agent-load-sample">Load sample deal</SecondaryButton>
          </div>
          <label data-testid="agent-drop"
                 onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
                 onDrop={(e) => { e.preventDefault(); setOver(false); add(e.dataTransfer.files); }}
                 className={cn("flex cursor-pointer flex-col items-center justify-center gap-1.5 rounded-lg border border-dashed px-3 py-5 text-center text-[13px] text-text-secondary hover:border-accent",
                               over ? "border-accent bg-accent-muted" : "border-border")}>
            <FileUp size={20} />
            <span className="font-medium text-text-primary">{rerun ? "Add more documents" : "Drop the whole pack here, or choose files"}</span>
            <span className="text-[12px] text-text-muted">One ZIP, or PDF, Word, Excel, CSV, photos and scans. Many at once.</span>
            <input type="file" multiple accept={ACCEPT} className="sr-only" disabled={busy || live} data-testid="agent-drop-input"
                   onChange={(e) => { add(e.target.files); e.currentTarget.value = ""; }} />
          </label>
          {files.length || run?.documents.length ? (
            <ul className="max-h-64 space-y-1 overflow-auto" data-testid="agent-files">
              {run?.documents.map((d) => (
                <li key={d.id} className="flex items-center gap-2 rounded-md border border-border px-2 py-1 text-[12px]" data-testid="agent-file-uploaded">
                  <span className="w-8 shrink-0 font-mono text-accent">{d.id}</span>
                  <span className="min-w-0 flex-1"><span className="block truncate text-text-primary">{d.name}</span>
                    <span className="block truncate text-[11px] text-text-muted">{d.result?.doc_type ?? (d.status === "failed" ? "could not be read" : "reading…")}</span></span>
                </li>))}
              {files.map((f, i) => (
                <li key={`${f.name}-${i}`} className="flex items-center gap-2 rounded-md border border-dashed border-border px-2 py-1 text-[12px]" data-testid="agent-file-new">
                  <FileText size={13} className="shrink-0 text-text-muted" />
                  <span className="min-w-0 flex-1 truncate text-text-primary">{f.name}</span>
                  <span className="text-[11px] text-text-muted">{Math.max(1, Math.round(f.size / 1024))} KB</span>
                  <button type="button" aria-label={`Remove ${f.name}`} className="rounded p-0.5 text-text-muted hover:bg-surface-hover" disabled={busy || live}
                          onClick={() => setFiles(files.filter((_, j) => j !== i))}><X size={12} /></button>
                </li>))}
            </ul>) : null}
          <label className="block space-y-1"><span className={label}>The ask</span>
            <textarea className={cn(input, "min-h-[84px]")} value={ask} onChange={(e) => setAsk(e.target.value)} data-testid="agent-ask"
                      placeholder="Facilities, amounts, tenor, purpose, pricing" /></label>
          <label className="block space-y-1"><span className={label}>RM notes <span className="normal-case tracking-normal text-text-muted">optional</span></span>
            <textarea className={cn(input, "min-h-[72px]")} value={notes} onChange={(e) => setNotes(e.target.value)} data-testid="agent-notes"
                      placeholder="Not in the documents: collections, security, history" /></label>
          <PrimaryButton className="w-full justify-center" onClick={() => void start()} disabled={busy || live || (rerun && !files.length)} data-testid="agent-run-button">
            <Sparkles size={14} />{live ? "The agent is working…" : rerun ? "Run again with the new documents" : "Run the agent"}</PrimaryButton>
          <p className="min-h-[1.2em] text-[12px] text-text-secondary" role="status" data-testid="agent-status">{status}</p>
        </div>

        {/* the run and the request */}
        <div className="min-w-0 space-y-4">
          <Steps run={run} elapsed={elapsed} />
          <Section title="Business request" testId="agent-request"
                   action={draft?.md && !live ? (
                     <a href={agentIntake.docxUrl(run!.run_id)} className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-surface px-3 text-[12px] text-text-secondary hover:bg-surface-hover"
                        data-testid="agent-docx"><FileDown size={13} /> Download Word</a>) : null}
                   info="The RM's business request to Credit in the bank's form, at most 650 words. Every figure cites its document [D3], the RM notes [RM] or the ask [Ask]; a figure that is not in the evidence it cites is removed and marked. The completeness line and what could not be assessed sit under the header.">
            {md ? (
              <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_240px]">
                <Paper md={md} docs={run?.documents ?? []} streaming={draft?.status === "streaming"} />
                <aside className="space-y-2 text-[12px] text-text-secondary" data-testid="agent-revise">
                  <p className={label}>Revise</p>
                  <textarea className={cn(input, "min-h-[72px]")} value={revise} onChange={(e) => setRevise(e.target.value)} data-testid="agent-revise-input"
                            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void doRevise(); } }}
                            placeholder="e.g. tighten section 7, add a covenant on DSO" disabled={live} />
                  <SecondaryButton onClick={() => void doRevise()} disabled={busy || live || !revise.trim()} data-testid="agent-revise-button">Revise</SecondaryButton>
                  {draft?.revise_error ? <p className="text-negative">{draft.revise_error}</p> : null}
                  <p data-testid="agent-draft-meta">{draft?.source === "model" ? "Written by the model" : draft?.source === "deterministic" ? "Written by rules (no model)" : ""}
                    {draft?.words ? ` · ${draft.words} words` : ""}{draft?.versions.length ? ` · version ${draft.versions.length}` : ""}</p>
                  {draft?.rejected.length ? (
                    <p className="text-negative" data-testid="agent-rejected"><AlertTriangle size={12} className="mr-1 inline" />
                      {draft.rejected.length} figure{draft.rejected.length === 1 ? "" : "s"} not in the evidence removed: {draft.rejected.map((r) => r.figure).join(", ")}</p>) : null}
                  {draft && draft.versions.length > 1 ? <ul className="space-y-0.5">{draft.versions.slice(1).map((v) => <li key={v.n}>v{v.n}: {v.instruction}</li>)}</ul> : null}
                </aside>
              </div>
            ) : (
              <div className="text-[13px] text-text-secondary" data-testid="agent-request-empty">
                <p><b className="text-text-primary">No request drafted yet.</b> To see the agent work:</p>
                <ol className="ml-5 mt-1 list-decimal space-y-0.5"><li>Click <b>Load sample deal</b> for a fictional Saudi contractor, or drop your own pack.</li>
                  <li>State the ask and add any RM notes.</li><li>Click <b>Run the agent</b>.</li></ol>
              </div>)}
          </Section>
        </div>
      </div>
      {run?.status === "done" ? footer : null}
    </div>
  );
}
