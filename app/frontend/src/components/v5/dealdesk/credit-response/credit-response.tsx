"use client";

/**
 * R16 c: "Credit response" on Deal Desk. Credit uploads the RM's business request (Word, PDF or photos) with the
 * customer's documents; CreditProbe reads the request, runs the Deal Desk flow on it step by step, writes the feedback
 * brief to the RM and the credit division's response in the bank form (preview, Word, PDF).
 *
 * Reached by clicking: Deal Desk → Proposal pipeline → "Credit response". The case id stays in the URL (?case=…), so a
 * reload or Back returns to the same case. Test ids: credit-response-*.
 */

import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { CheckCircle2, CircleDashed, Download, FileText, Loader2, Upload, XCircle } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { PlainWords } from "@/components/v5/ui/plain-words";
import {
  type Block, type Brief, type CrCase, type CrOverview, type CrPaper, type CrStep, creditResponse, looksLikeRequest, nextStep, progress, runs,
  severityTone,
} from "@/lib/v5/dealdesk-credit-response";
import { cn } from "@/lib/utils";

import { Chip, PrimaryButton, SecondaryButton, Section, tableCls, tdCls, thCls } from "../kit";

type Tab = "response" | "brief" | "request" | "steps";

function Rich({ text }: { text: string }) {
  return <>{runs(text).map((r, i) => (
    <span key={i} className={cn(r.bold && "font-semibold", r.underline && "underline")}>{r.text}</span>))}</>;
}

function BlockView({ b }: { b: Block }) {
  if (b.t === "p") return <p className="text-[12.5px] leading-relaxed text-text-primary"><Rich text={b.text} /></p>;
  if (b.t === "h") return <p className="pt-1 text-[12px] font-semibold text-accent">{b.text}</p>;
  if (b.t === "bullets") return <ul className="list-disc space-y-1 pl-5 text-[12.5px] leading-relaxed">{b.items.map((x, i) => <li key={i}><Rich text={x} /></li>)}</ul>;
  if (b.t === "numbered") return <ol className="list-decimal space-y-1 pl-5 text-[12.5px] leading-relaxed">{b.items.map((x, i) => <li key={i}><Rich text={x} /></li>)}</ol>;
  if (b.t === "kv") return (
    <div className="grid grid-cols-1 gap-x-4 gap-y-1 text-[12px] sm:grid-cols-2">
      {b.pairs.map(([k, v], i) => <div key={i} className="flex gap-2"><span className="w-40 shrink-0 text-text-muted">{k}</span><span className="text-text-primary">{v}</span></div>)}
    </div>);
  if (b.t === "table") return (
    <div className="overflow-auto">
      <table className={tableCls}>
        <thead><tr>{b.header.map((h, i) => <th key={i} className={thCls}>{h}</th>)}</tr></thead>
        <tbody>{b.rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j} className={cn(tdCls, "whitespace-normal")}><Rich text={String(c)} /></td>)}</tr>)}</tbody>
      </table>
      {b.source ? <p className="mt-1 text-[11px] text-text-muted">Source: {b.source}</p> : null}
    </div>);
  if (b.t === "sign") return (
    <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">{b.rows.map(([role, name], i) => (
      <div key={i} className="rounded border border-border px-2 py-3 text-[11px]"><div className="text-text-muted">{role}</div><div className="mt-4 border-t border-border pt-1">{name || " "}</div></div>))}</div>);
  if (b.t === "box") return <div className="rounded border border-dashed border-border px-2 py-6 text-[11px] text-text-muted">{b.title}</div>;
  return null;
}

function StepIcon({ s }: { s: CrStep["status"] }) {
  if (s === "done") return <CheckCircle2 size={15} className="text-positive" aria-hidden />;
  if (s === "error") return <XCircle size={15} className="text-negative" aria-hidden />;
  if (s === "running") return <Loader2 size={15} className="animate-spin text-accent" aria-hidden />;
  return <CircleDashed size={15} className="text-text-muted" aria-hidden />;
}

function Steps({ c, running }: { c: CrCase; running: string | null }) {
  const [open, setOpen] = React.useState<string | null>(null);
  return (
    <ol className="divide-y divide-border rounded-lg border border-border bg-surface" data-testid="credit-response-steps">
      {c.steps.map((s) => {
        const st = running === s.key ? "running" : s.status;
        return (
          <li key={s.key} data-testid={`credit-response-step-${s.key}`} data-status={st}>
            <button type="button" className="flex w-full items-start gap-2 px-3 py-2 text-left hover:bg-surface-hover" onClick={() => setOpen(open === s.key ? null : s.key)}
                    aria-expanded={open === s.key}>
              <span className="mt-0.5"><StepIcon s={st} /></span>
              <span className="min-w-0 flex-1">
                <span className="block text-[13px] font-medium text-text-primary">{s.label}</span>
                {s.headline ? <span className="block truncate text-[12px] text-text-secondary">{s.headline}</span> : null}
              </span>
              {s.seconds !== undefined ? <span className="shrink-0 text-[11px] tabular-nums text-text-muted">{s.seconds.toFixed(1)} s</span> : null}
            </button>
            {open === s.key && s.plain_words?.length ? (
              <div className="px-9 pb-3"><PlainWords lines={s.plain_words} testId={`credit-response-step-${s.key}-plain`} /></div>) : null}
          </li>);
      })}
    </ol>);
}

function UploadCard({ ov, busy, onFiles, onDemo }: {
  ov: CrOverview | undefined; busy: boolean; onFiles: (f: File[]) => void; onDemo: (k: "docx" | "pdf" | "jpg") => void;
}) {
  const input = React.useRef<HTMLInputElement>(null);
  const [files, setFiles] = React.useState<File[]>([]);
  const [drag, setDrag] = React.useState(false);
  const add = (list: FileList | null) => setFiles((prev) => [...prev, ...Array.from(list ?? [])].filter((f, i, a) => a.findIndex((g) => g.name === f.name) === i));
  const req = files.filter((f) => looksLikeRequest(f.name));
  return (
    <Section title="Upload the business request and the documents" testId="credit-response-upload">
      <div onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
           onDrop={(e) => { e.preventDefault(); setDrag(false); add(e.dataTransfer.files); }}
           className={cn("flex flex-col items-center gap-2 rounded-lg border-2 border-dashed px-4 py-6 text-center", drag ? "border-accent bg-accent-muted" : "border-border")}>
        <Upload size={20} className="text-accent" aria-hidden />
        <p className="text-[13px] text-text-primary">Drop the RM&apos;s business request (Word, PDF or photos of its pages) and the customer&apos;s documents here</p>
        <p className="text-[12px] text-text-muted">Several files at once; Word, PDF, JPG or PNG. Photos are read with OCR{ov?.ocr?.available ? ` (${ov.ocr.engine})` : ""}.</p>
        <input ref={input} type="file" multiple accept={(ov?.accepted ?? [".docx", ".pdf", ".jpg", ".png"]).join(",")} className="hidden"
               onChange={(e) => add(e.target.files)} data-testid="credit-response-file" />
        <SecondaryButton onClick={() => input.current?.click()} data-testid="credit-response-choose">Choose files</SecondaryButton>
      </div>
      {files.length ? (
        <div className="mt-3 space-y-2" data-testid="credit-response-files">
          <p className="text-[12px] text-text-secondary">{files.length} file{files.length !== 1 ? "s" : ""} chosen; {req.length ? `the request: ${req.map((f) => f.name).join(", ")}` : "the request is found from its content (its first page says 'Action requested')"}.</p>
          <div className="flex flex-wrap gap-1">{files.slice(0, 40).map((f) => <Chip key={f.name} tone={looksLikeRequest(f.name) ? "accent" : "neutral"}>{f.name}</Chip>)}</div>
          <div className="flex gap-2">
            <PrimaryButton disabled={busy} onClick={() => onFiles(files)} data-testid="credit-response-start"><FileText size={14} aria-hidden /> Read and respond</PrimaryButton>
            <SecondaryButton disabled={busy} onClick={() => setFiles([])}>Clear</SecondaryButton>
          </div>
        </div>) : null}
      {ov?.demo ? (
        <div className="mt-4 rounded-md border border-border bg-surface-sunken px-3 py-2" data-testid="credit-response-demo">
          <p className="text-[12px] text-text-secondary">Demo pack on this laptop: {ov.demo.customer}. The request with the customer&apos;s {ov.demo.documents.pdf ?? 0} documents (PDF):</p>
          <div className="mt-2 flex flex-wrap gap-2">
            <SecondaryButton disabled={busy} onClick={() => onDemo("pdf")} data-testid="credit-response-demo-pdf">Request as PDF</SecondaryButton>
            <SecondaryButton disabled={busy} onClick={() => onDemo("docx")} data-testid="credit-response-demo-docx">Request as Word</SecondaryButton>
            <SecondaryButton disabled={busy} onClick={() => onDemo("jpg")} data-testid="credit-response-demo-jpg">Request as photos</SecondaryButton>
          </div>
        </div>) : null}
    </Section>);
}

function ResponseView({ cid, paper }: { cid: string; paper: CrPaper | undefined }) {
  if (!paper) return <Skeleton className="h-96 w-full" />;
  const s = paper.summary;
  return (
    <div className="space-y-3" data-testid="credit-response-paper">
      <div className="rounded-lg border border-border bg-surface p-3">
        <div className="flex flex-wrap items-center gap-2">
          <Chip tone={s.head.startsWith("Not") ? "negative" : s.head.includes("conditions") || s.head.startsWith("Counter") ? "warning" : "positive"} testId="credit-response-decision">{s.head}</Chip>
          <span className="text-[12px] text-text-muted">{paper.form_title ?? "CREDIT DIVISION RESPONSE"} · {paper.customer} · {paper.proposal_id}</span>
          <span className="ml-auto flex gap-2">
            <a href={creditResponse.fileUrl(cid, "response.docx")} data-testid="credit-response-docx"
               className="inline-flex h-8 items-center gap-1.5 rounded-md bg-accent px-3 text-[12px] font-medium text-accent-contrast hover:bg-accent-hover"><Download size={13} aria-hidden /> Word</a>
            <a href={creditResponse.fileUrl(cid, "response.pdf")} data-testid="credit-response-pdf"
               className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-surface px-3 text-[12px] text-text-secondary hover:bg-surface-hover"><Download size={13} aria-hidden /> PDF</a>
          </span>
        </div>
        <p className="mt-2 text-[12.5px] text-text-primary"><Rich text={s.decision} /></p>
        {s.conditions.length ? (<>
          <p className="mt-2 text-[12px] font-semibold text-accent">Conditions precedent (prior to limit loading)</p>
          <ol className="list-decimal space-y-1 pl-5 text-[12px]">{s.conditions.slice(0, 10).map((x, i) => <li key={i}>{x}</li>)}</ol></>) : null}
      </div>
      {paper.parts.map((p) => (
        <div key={p.key} className="rounded-lg border border-border bg-surface" data-testid={`credit-response-part-${p.key}`}>
          <div className="rounded-t-lg bg-accent px-3 py-1.5 text-[12px] font-semibold text-accent-contrast">{p.title} <span className="font-normal opacity-80">· {p.subtitle}</span></div>
          <div className="space-y-4 p-3">
            {p.sections.map((sec, i) => (
              <div key={sec.key} className="space-y-1.5" data-testid={`credit-response-section-${sec.key}`}>
                <p className="text-[13px] font-semibold text-text-primary">{sec.n ? `${sec.n}. ` : `CP${i + 1}. `}{sec.heading}</p>
                {sec.blocks.map((b, j) => <BlockView key={j} b={b} />)}
              </div>))}
          </div>
        </div>))}
    </div>);
}

function BriefView({ cid, brief }: { cid: string; brief: Brief | undefined }) {
  if (!brief) return <Skeleton className="h-64 w-full" />;
  return (
    <div className="space-y-3" data-testid="credit-response-brief">
      <div className="flex flex-wrap items-center gap-2 rounded-lg border border-border bg-surface p-3">
        <span className="text-[13px] font-medium text-text-primary">To {brief.to}: {brief.subject}</span>
        <Chip tone="negative">{brief.critical} critical</Chip><Chip tone="warning">{brief.major} major</Chip>
        <a href={creditResponse.fileUrl(cid, "brief.docx")} data-testid="credit-response-brief-docx"
           className="ml-auto inline-flex h-8 items-center gap-1.5 rounded-md bg-accent px-3 text-[12px] font-medium text-accent-contrast hover:bg-accent-hover"><Download size={13} aria-hidden /> Word</a>
      </div>
      {brief.groups.map((g) => (
        <Section key={g.severity} title={g.label} testId={`credit-response-brief-${g.severity}`}>
          <div className="overflow-auto">
          <table className={cn(tableCls, "min-w-[640px] table-fixed")}>
            <colgroup><col className="w-8" /><col className="w-28" /><col /><col /></colgroup>
            <thead><tr><th className={thCls}>#</th><th className={thCls}>Section</th><th className={thCls}>Query</th><th className={thCls}>What credit sees</th></tr></thead>
            <tbody>{g.items.map((it) => (
              <tr key={it.n}><td className={tdCls}>{it.n}</td><td className={cn(tdCls, "whitespace-normal")}>{it.section}</td>
                <td className={cn(tdCls, "whitespace-normal")}><span className="font-medium">{it.title}</span><br />{it.query}</td>
                <td className={cn(tdCls, "whitespace-normal text-text-secondary")}><Rich text={it.evidence} />{it.source ? <span className="block break-words text-[11px] text-text-muted">{it.source}</span> : null}</td></tr>))}
            </tbody>
          </table>
          </div>
        </Section>))}
    </div>);
}

type Req = { header: Record<string, string>; totals: Record<string, number | null>; document: string; method: string;
             facilities: { seq: number; level: number; limit_name: string; existing_mn: number | null; outstanding_mn: number | null; proposed_mn: number | null; cash_margin_pct?: number; particulars?: string; total: boolean }[];
             security: { seq: number; kind: string; text: string; perfection_status: string }[]; terms: { seq: number; category: string; text: string; existing_status: string }[];
             read_gaps: string[] };

function RequestView({ c }: { c: CrCase }) {
  const rd = c.steps.find((s) => s.key === "read")?.data as { request?: Req; documents?: { name: string; label: string; method: string; duplicate?: boolean }[] } | undefined;
  const r = rd?.request;
  if (!r) return <Skeleton className="h-64 w-full" />;
  const f = (x: number | null | undefined) => (x === null || x === undefined ? "–" : x.toFixed(1));
  return (
    <div className="space-y-3" data-testid="credit-response-request">
      <Section title={`Facilities as requested (SAR m) · ${r.document} · read as ${r.method}`}>
        <table className={tableCls}>
          <thead><tr><th className={thCls}>Limit / sub-limit</th><th className={cn(thCls, "text-right")}>Existing</th><th className={cn(thCls, "text-right")}>Outstanding</th>
            <th className={cn(thCls, "text-right")}>Proposed</th><th className={cn(thCls, "text-right")}>Cash margin</th><th className={thCls}>Particulars</th></tr></thead>
          <tbody>{r.facilities.map((x) => (
            <tr key={x.seq} className={cn(x.total && "font-semibold")}>
              <td className={cn(tdCls, "whitespace-normal", x.level === 2 && "pl-6")}>{x.limit_name}</td><td className={cn(tdCls, "text-right")}>{f(x.existing_mn)}</td>
              <td className={cn(tdCls, "text-right")}>{f(x.outstanding_mn)}</td><td className={cn(tdCls, "text-right")}>{f(x.proposed_mn)}</td>
              <td className={cn(tdCls, "text-right")}>{x.cash_margin_pct ? `${x.cash_margin_pct}%` : "–"}</td><td className={cn(tdCls, "whitespace-normal text-text-secondary")}>{x.particulars}</td></tr>))}
          </tbody>
        </table>
      </Section>
      <Section title="Security and support as requested">
        <ul className="list-disc space-y-1 pl-5 text-[12.5px]">{r.security.map((s) => <li key={s.seq}>{s.text} <Chip tone={s.perfection_status === "pending" ? "warning" : "neutral"}>{s.perfection_status.replace("_", " ")}</Chip></li>)}</ul>
      </Section>
      <Section title="Terms and conditions as requested">
        <ol className="list-decimal space-y-1 pl-5 text-[12.5px]">{r.terms.map((t) => <li key={t.seq}>{t.text} {t.existing_status === "not_complied" ? <Chip tone="negative">not complied</Chip> : null}</li>)}</ol>
      </Section>
      {rd?.documents?.length ? (
        <Section title={`Documents uploaded (${rd.documents.length})`}>
          <div className="flex flex-wrap gap-1">{rd.documents.filter((d) => !d.duplicate).map((d) => <Chip key={d.name} title={d.method}>{d.label || d.name}</Chip>)}</div>
        </Section>) : null}
    </div>);
}

export function CreditResponseView() {
  const router = useRouter();
  const params = useSearchParams();
  const cid = params.get("case") ?? "";
  const [ov, setOv] = React.useState<CrOverview>();
  const [c, setC] = React.useState<CrCase>();
  const [paper, setPaper] = React.useState<CrPaper>();
  const [running, setRunning] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string>("");
  const [tab, setTab] = React.useState<Tab>("response");
  const busy = running !== null;
  const stop = React.useRef(false);

  React.useEffect(() => { creditResponse.overview().then(setOv).catch((e) => setError(String(e?.message ?? e))); }, []);
  React.useEffect(() => {
    stop.current = false;
    setPaper(undefined);
    if (!cid) { setC(undefined); return; }
    creditResponse.get(cid).then(setC).catch((e) => setError(String(e?.message ?? e)));
    return () => { stop.current = true; };
  }, [cid]);

  // run the remaining steps one by one, so each shows as it finishes
  React.useEffect(() => {
    if (!c || busy || error) return;
    const k = nextStep(c);
    if (!k) return;
    setRunning(k);
    creditResponse.step(c.case_id, k).then((n) => { if (!stop.current) setC(n); })
      .catch((e) => setError(String(e?.message ?? e))).finally(() => setRunning(null));
  }, [c, busy, error]);

  React.useEffect(() => {
    if (c?.status === "done" && !paper) creditResponse.paper(c.case_id).then(setPaper).catch((e) => setError(String(e?.message ?? e)));
  }, [c, paper]);

  const open = (n: CrCase) => { setError(""); setC(n); router.push(`/deal-desk/credit-response?case=${encodeURIComponent(n.case_id)}&from=deal-desk`); };
  const startFiles = (files: File[]) => { setError(""); setRunning("upload"); creditResponse.start(files).then(open).catch((e) => setError(String(e?.message ?? e))).finally(() => setRunning(null)); };
  const startDemo = (k: "docx" | "pdf" | "jpg") => { setError(""); setRunning("upload"); creditResponse.startDemo(k).then(open).catch((e) => setError(String(e?.message ?? e))).finally(() => setRunning(null)); };

  const pr = c ? progress(c) : null;
  const brief = c?.steps.find((s) => s.key === "brief")?.data as Brief | undefined;
  const plain = c?.status === "done" && paper ? paper.summary.plain_words
    : c ? [`Credit is reading the business request of ${c.customer ?? "the customer"} and running the Deal Desk flow on it: ${pr?.done} of ${pr?.total} steps done.`,
           "Each step says what it found in plain words; the response is written when the last step finishes."]
    : ov?.plain_words ?? [];

  return (
    <div className="mx-auto max-w-[1180px] space-y-4 p-4" data-testid="credit-response">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-[18px] font-semibold text-text-primary">Credit response</h1>
        {c ? <Chip tone="accent">{c.customer ?? c.case_id}{c.proposal_id ? ` · ${c.proposal_id}` : ""}</Chip> : null}
        {c?.proposal_id && c.status === "done" ? (
          <SecondaryButton className="ml-auto" onClick={() => router.push(`/deal-desk/${encodeURIComponent(c.proposal_id!)}?from=deal-desk`)} data-testid="credit-response-open-deal">Open the deal</SecondaryButton>) : null}
        {c ? <SecondaryButton className={cn(!(c.proposal_id && c.status === "done") && "ml-auto")} onClick={() => router.push("/deal-desk/credit-response?from=deal-desk")} data-testid="credit-response-new">New response</SecondaryButton> : null}
      </div>
      <PlainWords lines={plain} loading={!ov && !c} testId="credit-response-plain" />
      {error ? <p role="alert" className="rounded-md border border-negative/30 bg-negative-muted px-3 py-2 text-[12px] text-negative" data-testid="credit-response-error">{error}
        {c ? <button type="button" className="ml-2 underline" onClick={() => setError("")}>Try again</button> : null}</p> : null}

      {!cid ? (<>
        <UploadCard ov={ov} busy={busy} onFiles={startFiles} onDemo={startDemo} />
        {running === "upload" ? <p className="flex items-center gap-2 text-[12px] text-text-secondary"><Loader2 size={14} className="animate-spin" aria-hidden /> Uploading…</p> : null}
        {ov?.cases?.length ? (
          <Section title="Recent credit responses" testId="credit-response-recent">
            <table className={tableCls}><tbody>{ov.cases.map((x) => (
              <tr key={x.case_id} className="cursor-pointer hover:bg-surface-hover" onClick={() => router.push(`/deal-desk/credit-response?case=${encodeURIComponent(x.case_id)}&from=deal-desk`)}>
                <td className={cn(tdCls, "text-accent")}>{x.customer ?? x.case_id}</td><td className={tdCls}>{x.proposal_id ?? ""}</td>
                <td className={cn(tdCls, "whitespace-normal text-text-secondary")}>{x.decision ?? x.status}</td><td className={cn(tdCls, "text-text-muted")}>{x.created?.slice(0, 16).replace("T", " ")}</td></tr>))}
            </tbody></table>
          </Section>) : null}
      </>) : !c ? <Skeleton className="h-96 w-full" /> : (
        <div className={cn("grid grid-cols-1 gap-4", c.status !== "done" && "xl:grid-cols-[300px_1fr]")}>
          {c.status === "done" ? (
            <details className="rounded-lg border border-border bg-surface px-3 py-2" data-testid="credit-response-steps-done">
              <summary className="cursor-pointer text-[12.5px] text-text-secondary">
                {pr?.total} steps run in {c.steps.reduce((a, s) => a + (s.seconds ?? 0), 0).toFixed(0)} s: read, deal, proposal check, review, analysis, structure, stress,
                stress-proof, recommendation, RM brief, response. Show each step and its plain words</summary>
              <div className="mt-2"><Steps c={c} running={running} /></div>
            </details>) : (
          <div className="space-y-2">
            <div className="h-1.5 w-full overflow-hidden rounded bg-surface-sunken" aria-label="Progress"><div className="h-full bg-accent transition-all" style={{ width: `${pr?.pct ?? 0}%` }} /></div>
            <Steps c={c} running={running} />
          </div>)}
          <div className="min-w-0 space-y-3">
            <div className="inline-flex rounded-md border border-border p-0.5" role="tablist" aria-label="Credit response view">
              {([["response", "Credit response"], ["brief", "Feedback to the RM"], ["request", "Request as read"]] as const).map(([k, label]) => (
                <button key={k} type="button" role="tab" aria-selected={tab === k} onClick={() => setTab(k)} data-testid={`credit-response-tab-${k}`}
                        className={cn("h-8 whitespace-nowrap rounded px-3 text-[12px]", tab === k ? "bg-accent font-medium text-accent-contrast" : "text-text-secondary hover:bg-surface-hover")}>{label}</button>))}
            </div>
            {tab === "response" ? (c.status === "done" ? <ResponseView cid={c.case_id} paper={paper} />
              : <p className="flex items-center gap-2 rounded-lg border border-border bg-surface px-3 py-6 text-[12.5px] text-text-secondary"><Loader2 size={14} className="animate-spin" aria-hidden /> The response is written when the steps on the left finish ({pr?.done} of {pr?.total}).</p>)
              : tab === "brief" ? (brief ? (<>
                  <PlainWords lines={c.steps.find((x) => x.key === "brief")?.plain_words ?? []} testId="credit-response-brief-plain" />
                  <BriefView cid={c.case_id} brief={brief} /></>) : <p className="rounded-lg border border-border bg-surface px-3 py-6 text-[12.5px] text-text-secondary">The feedback brief is written after the recommendation step.</p>)
              : (<>
                  <PlainWords lines={c.steps.find((x) => x.key === "read")?.plain_words ?? []} testId="credit-response-request-plain" />
                  <RequestView c={c} /></>)}
          </div>
        </div>)}
    </div>);
}
