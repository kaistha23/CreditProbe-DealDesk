"use client";

/**
 * R13 IE item 18: inspection responder — compact panel (tools menu).
 *
 * R14 G (K14, K15): the screen says what it is for and what to do (empty state with three clickable sample requests and
 * a preview of the pack's sections), and the result is the answer itself: a one-line summary, then one row per borrower
 * (name → Borrower 360, EAD, stage path, approval reference / level / date, conditions met / overdue) expandable to the
 * evidence; Word and Excel at the top; the pack reference explained; the coverage check collapsed, each answer labelled
 * with its source (the governance register is a demo seed).
 */

import * as React from "react";
import Link from "next/link";
import { ChevronRight, FileSearch, Loader2 } from "lucide-react";

import { Chip, PrimaryButton, tableCls } from "@/components/v5/dealdesk/kit";
import { PanelWords } from "@/components/v5/panels-g/panel-words";
import { cn } from "@/lib/utils";
import {
  COVERAGE_LABEL, coverageGrid, coverageTone, gov, parseSample, type InspectionAnswer, type InspectionPack, type InspectionSample,
} from "@/lib/v5/intel-governance";
import { writeInspection, writeInspectionEmpty } from "@/lib/v5/plain-words-g/inspection";

import { DownloadButton, Failure, Fold, MethodNote, Td, Th, useGovOrigin } from "./shared";

/** Shown when the samples endpoint is not reachable (same three requests as backend/intel/governance/inspection.SAMPLES). */
const FALLBACK_SAMPLES: InspectionSample[] = [
  { key: "auditor_stage3", who: "External auditor", label: "Auditor: Stage 3 sample in Construction",
    request: "The auditor asks for the approvals, conditions and stage history of the 5 largest Stage 3 borrowers in Construction" },
  { key: "sama_concentration", who: "Regulator", label: "SAMA: largest exposures and their approvals",
    request: "SAMA asks for the exposure, limits, rating, approvals and authority of the 10 largest borrowers" },
  { key: "ia_exceptions", who: "Internal audit", label: "Internal audit: policy exceptions on watch-list names",
    request: "Internal audit asks for the policy exceptions, approvals and conditions of the 5 largest watch list borrowers" },
];
const FALLBACK_SECTIONS = [
  "Cover: the request, the pack reference and the as-of quarter",
  "Summary and the answer per item: EAD, stage path, approval with level and date, conditions and their status",
  "Coverage check: each item and topic asked against what the data holds",
  "Evidence per item: facilities, approval steps, conditions and exceptions",
  "Policy clauses cited, quoted from the policy library",
  "Method and data note; the Excel holds every figure with its relation, row and period",
];
const DOT: Record<string, string> = { answered: "bg-positive", partial: "bg-warning", not_available: "bg-negative" };

export function InspectionPanel({ initial = "" }: { initial?: string }) {
  const where = useGovOrigin();
  const [request, setRequest] = React.useState(initial);
  const [sample, setSample] = React.useState("");
  const [pack, setPack] = React.useState<InspectionPack | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const [meta, setMeta] = React.useState<{ samples: InspectionSample[]; sections: string[] }>({ samples: FALLBACK_SAMPLES, sections: FALLBACK_SECTIONS });
  React.useEffect(() => {
    let live = true;
    gov.inspectionSamples(where).then((m) => { if (live && m.samples?.length) setMeta(m); }).catch(() => null);
    return () => { live = false; };
  }, [where]);
  const run = React.useCallback(async (req: string, smp: string) => {
    if (!req.trim() && !parseSample(smp).length) return;
    setBusy(true); setError("");
    try { setPack(await gov.inspection(where, req, parseSample(smp))); }
    catch (e) { setError(e instanceof Error ? e.message : "Something went wrong."); }
    finally { setBusy(false); }
  }, [where]);
  React.useEffect(() => {
    if (!initial.trim()) return;
    const t = window.setTimeout(() => void run(initial, ""), 0);
    return () => window.clearTimeout(t);
  }, [initial, run]);
  const body = { request, sample: parseSample(sample) };
  return (
    <div className="space-y-4" data-testid="gov-inspection">
      {!pack ? <PanelWords panel="inspection" lines={busy ? null : writeInspectionEmpty(meta.samples.length)} className="" /> : null}
      <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); void run(request, sample); }}>
        <textarea value={request} onChange={(e) => setRequest(e.target.value)} rows={3} data-testid="gov-insp-request"
                  placeholder="Paste the request, or pick a sample below" aria-label="Regulator or auditor request"
                  className="w-full resize-none rounded-md border border-border bg-surface px-3 py-2 text-[13px] text-text-primary focus:border-accent focus:outline-none" />
        <div className="flex items-center gap-2">
          <input value={sample} onChange={(e) => setSample(e.target.value)} data-testid="gov-insp-sample" aria-label="Sample list"
                 placeholder="Sample ids (optional), e.g. CB00039, CF000011"
                 className="h-9 min-w-0 flex-1 rounded-md border border-border bg-surface px-3 text-[13px] text-text-primary focus:border-accent focus:outline-none" />
          <PrimaryButton type="submit" disabled={busy || (!request.trim() && !sample.trim())} data-testid="gov-insp-run">
            {busy ? <Loader2 size={14} className="animate-spin" /> : <FileSearch size={14} />} Build pack
          </PrimaryButton>
        </div>
        {!pack && !busy ? (
          <div className="space-y-1.5" data-testid="gov-insp-samples">
            <p className="text-[11px] font-medium uppercase tracking-[0.08em] text-text-muted">Sample requests</p>
            <div className="grid gap-1.5 sm:grid-cols-3">
              {meta.samples.map((s, i) => (
                <button key={s.key} type="button" data-testid={i === 0 ? "gov-insp-example" : `gov-insp-sample-${s.key}`}
                        onClick={() => { setRequest(s.request); setSample(""); void run(s.request, ""); }}
                        className="rounded-md border border-border bg-surface px-3 py-2 text-left hover:border-accent hover:bg-surface-hover">
                  <span className="block text-[11px] text-text-muted">{s.who}</span>
                  <span className="block text-[12px] font-medium text-text-primary">{s.label}</span>
                </button>))}
            </div>
            <Sections sections={meta.sections} />
          </div>) : null}
      </form>
      {error ? <Failure message={error} /> : null}
      {pack ? <Pack pack={pack} sections={meta.sections} onEditSample={(ids) => setSample(ids.join(", "))} downloads={
        <>
          <DownloadButton label="Word" testId="gov-insp-docx" run={() => gov.download(where, "inspection-docx", body)} />
          <DownloadButton label="Excel" testId="gov-insp-xlsx" run={() => gov.download(where, "inspection-xlsx", body)} />
        </>} /> : null}
    </div>
  );
}

function Sections({ sections }: { sections: string[] }) {
  return (
    <details className="text-[12px]" data-testid="gov-insp-sections">
      <summary className="cursor-pointer select-none text-text-secondary hover:text-text-primary">What the pack holds ({sections.length} sections)</summary>
      <ol className="mt-1 list-decimal space-y-0.5 pl-5 text-text-secondary">{sections.map((s) => <li key={s}>{s}</li>)}</ol>
    </details>
  );
}

function sar(v: number | undefined): string {
  return v == null ? "–" : `SAR ${v.toLocaleString("en-US", { maximumFractionDigits: 1, minimumFractionDigits: 1 })}m`;
}

function AnswerRow({ a, pack }: { a: InspectionAnswer; pack: InspectionPack }) {
  const [open, setOpen] = React.useState(false);
  const cov = pack.coverage.filter((c) => c.item === a.item);
  const seed = (a.approval?.evidence ?? "").includes("demo seed");
  return (
    <>
      <tr data-testid={`gov-insp-answer-${a.item}`}>
        <Td>
          <button type="button" onClick={() => setOpen((x) => !x)} aria-expanded={open} aria-label={open ? "Hide evidence" : "Show evidence"}
                  className="mr-1 inline-flex size-5 items-center justify-center rounded text-text-muted hover:bg-surface-hover">
            <ChevronRight size={13} className={cn("transition-transform", open && "rotate-90")} /></button>
          {a.href ? <Link href={a.href} className="font-medium text-accent hover:underline" data-testid={`gov-insp-open-${a.item}`}>{a.name}</Link>
            : <span className="font-medium text-text-primary">{a.name}</span>}
          <span className="ml-1 text-[11px] text-text-muted">{a.item}</span>
        </Td>
        <Td right>{a.ead ? sar(a.ead.value) : "–"}</Td>
        <Td className="whitespace-normal">{a.stage_path ?? "–"}</Td>
        <Td className="whitespace-normal">{a.approval?.text ?? "–"}</Td>
        <Td className="whitespace-normal">{a.conditions?.text ?? "–"}</Td>
        <Td>{seed ? <Chip tone="warning" title="The approvals history is a fictional seed (gov_* relations); book figures are real">demo seed</Chip>
          : a.found ? <Chip tone="positive">book</Chip> : <Chip tone="negative">not found</Chip>}</Td>
      </tr>
      {open ? (
        <tr><td colSpan={6} className="bg-surface-sunken px-3 py-2">
          <ul className="space-y-0.5 text-[12px] text-text-secondary">
            {a.line ? <li className="text-text-primary">{a.line}</li> : null}
            {cov.map((c) => (
              <li key={c.topic}><span className="font-medium text-text-primary">{c.topic_label}:</span> {COVERAGE_LABEL[c.status].toLowerCase()} — {c.reason}
                {c.evidence ? <span className="text-text-muted"> (source: {c.evidence})</span> : null}</li>))}
          </ul>
        </td></tr>) : null}
    </>
  );
}

function Pack({ pack, downloads, sections, onEditSample }: {
  pack: InspectionPack; downloads: React.ReactNode; sections: string[]; onEditSample: (ids: string[]) => void;
}) {
  const g = coverageGrid(pack.coverage);
  const answers = pack.answers ?? [];
  return (
    <div className="space-y-3" data-testid="gov-insp-pack">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">{downloads}</div>
        <div className="flex items-center gap-2 text-[11px] text-text-muted">
          <span data-testid="gov-insp-packid" title={pack.pack_note}>Pack reference {pack.pack_id}</span>
          <MethodNote title="Inspection responder" method={pack.method} data={pack.data_note} />
        </div>
      </div>
      <PanelWords panel="inspection" lines={() => writeInspection(pack)} className="" />
      <p className="text-[13px] font-medium text-text-primary" data-testid="gov-insp-summary">{pack.summary ?? pack.lines[0]}</p>
      {pack.sample_rule ? (
        <p className="text-[12px] text-text-secondary" data-testid="gov-insp-rule">{pack.sample_rule}{" "}
          <button type="button" className="text-accent hover:underline" data-testid="gov-insp-edit-sample"
                  onClick={() => onEditSample(answers.map((a) => a.item))}>Edit this sample</button></p>) : null}
      {answers.length ? (
        <div className="overflow-x-auto" data-testid="gov-insp-answers">
          <table className={tableCls}>
            <thead><tr><Th>Borrower</Th><Th right>EAD</Th><Th>Stage path</Th><Th>Approval</Th><Th>Conditions</Th><Th>Source</Th></tr></thead>
            <tbody>{answers.map((a) => <AnswerRow key={a.item} a={a} pack={pack} />)}</tbody>
          </table>
        </div>) : null}
      {pack.pack_note ? <p className="text-[11px] text-text-muted" data-testid="gov-insp-packnote">{pack.pack_note}</p> : null}
      <Fold title="Coverage check: what was asked against what the data holds" testId="gov-insp-coverage-fold"
            meta={`${pack.coverage_summary.answered} of ${pack.coverage.length} answered`}>
        <div className="space-y-3 p-2">
          <div className="overflow-x-auto" data-testid="gov-insp-coverage">
            <table className={tableCls}>
              <thead><tr><Th>Item</Th>{g.topics.map((t) => <Th key={t.key} className="text-center">{t.label}</Th>)}</tr></thead>
              <tbody>
                {g.items.map((i) => (
                  <tr key={i}>
                    <Td className="font-medium">{answers.find((a) => a.item === i)?.name ?? i}</Td>
                    {g.topics.map((t) => {
                      const c = g.cell(i, t.key);
                      return (
                        <Td key={t.key} className="text-center" title={c ? `${COVERAGE_LABEL[c.status]}: ${c.reason}${c.evidence ? ` (source: ${c.evidence})` : ""}` : ""}>
                          {c ? <span className={cn("inline-block size-2.5 rounded-full", DOT[c.status])} aria-label={COVERAGE_LABEL[c.status]} /> : null}
                        </Td>);
                    })}
                  </tr>))}
              </tbody>
            </table>
            <div className="mt-1.5 flex gap-3 text-[11px] text-text-muted">
              {(["answered", "partial", "not_available"] as const).map((k) => (
                <span key={k} className="inline-flex items-center gap-1"><span className={cn("size-2 rounded-full", DOT[k])} />{COVERAGE_LABEL[k]}</span>))}
            </div>
          </div>
          <div className="max-h-[220px] overflow-auto" data-testid="gov-insp-gaps">
            <table className={tableCls}>
              <thead><tr><Th>Item</Th><Th>Topic</Th><Th>Status</Th><Th>Source</Th><Th>What the pack holds</Th></tr></thead>
              <tbody>
                {pack.coverage.map((c, k) => (
                  <tr key={k}>
                    <Td>{c.item}</Td><Td>{c.topic_label}</Td>
                    <Td><Chip tone={coverageTone(c.status)}>{COVERAGE_LABEL[c.status]}</Chip></Td>
                    <Td>{c.evidence ?? "–"}</Td>
                    <Td className="max-w-[300px] truncate" title={c.reason}>{c.reason}</Td>
                  </tr>))}
              </tbody>
            </table>
          </div>
        </div>
      </Fold>
      <Sections sections={pack.sections ?? sections} />
    </div>
  );
}
