"use client";

/**
 * PLAN_R12 Session T (I18): the live run of "Try it on your documents".
 *
 * Answer first (the time from upload to drafted memo and what the review found), then the six visible steps, each with
 * its status, time and result: what the policy sets and what is left to CreditProbe defaults, the deal the proposal
 * became (every field with its source, every default labelled), the review against the participant's own clauses, the
 * counter-proposal and committee paper, and the draft in the memo's language. Exit wipes the demo session.
 */

import * as React from "react";
import { Download, LogOut, Play, ShieldCheck } from "lucide-react";

import { InfoPopover } from "@/components/ui/info-popover";
import { KpiRow } from "@/components/v5/core/kpi-row";
import { cn } from "@/lib/utils";

import { Chip, PrimaryButton, SecondaryButton, Section, tableCls, tdCls, thCls } from "../kit";
import {
  ACCEPT, type CounterResult, type DraftResult, type ExtractResult, type Mode, type Overview, type PolicyResult, type ReviewResult,
  type Step, type TrySession, type Wiped, acceptedFile, answerLine, dealLine, facilityLabel, fmtValue, langLabel, remaining, secs,
  sevTone, stepStatusLabel, stepTone, tryDocs, verdictLabel, verdictTone,
} from "./try-docs-api";
import { PanelWords } from "@/components/v5/panels-g/panel-words"; // R14 G (K34)
import { writeTryDocs } from "@/lib/v5/plain-words-g/deal";

const wrapCls = "whitespace-normal break-words border-b border-border/60 px-2 py-2 align-top";

function errText(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

function FilePick({ label, info, file, onFile, testId, optional }: {
  label: string; info: string; file: File | null; onFile: (f: File | null) => void; testId: string; optional?: boolean;
}) {
  return (
    <label className="flex min-w-0 flex-1 flex-col gap-1 text-[12px] text-text-secondary">
      <span className="inline-flex items-center gap-1 font-medium text-text-primary">
        {label}{optional ? <span className="font-normal text-text-muted">(optional)</span> : null}
        <InfoPopover title={label}>{info}</InfoPopover>
      </span>
      <input type="file" accept={ACCEPT} data-testid={testId}
             onChange={(e) => { const f = e.target.files?.[0] ?? null; onFile(f && acceptedFile(f.name) ? f : null); }}
             className="min-w-0 text-[12px] file:mr-2 file:h-7 file:rounded-md file:border file:border-border file:bg-surface file:px-2 file:text-[12px]" />
      {file ? <span className="truncate text-[11px] text-text-muted" title={file.name}>{file.name}</span> : null}
    </label>
  );
}

function Notice({ text, model }: { text: string; model?: string | null }) {
  return (
    <div className="flex items-start gap-2 rounded-lg border border-warning/30 bg-warning-muted px-3 py-2 text-[12px] text-text-primary" data-testid="try-notice">
      <ShieldCheck size={16} className="mt-0.5 shrink-0 text-warning" aria-hidden />
      <div className="min-w-0 space-y-1"><p>{text}</p>{model ? <p className="font-medium">{model}</p> : null}</div>
    </div>
  );
}

// ---------------------------------------------------------------- step results

function PolicyView({ r, sid, onApprove }: { r: PolicyResult; sid: string; onApprove: (msg: string) => void }) {
  const [all, setAll] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const thr = r.found.filter((f) => f.type === "threshold");
  const rows = all ? thr : thr.slice(0, 8);
  const defs = r.missing.filter((m) => m.value != null);
  return (
    <div className="space-y-3">
      {thr.length ? (
        <div className="overflow-x-auto">
          <table className={tableCls} data-testid="try-policy-found">
            <thead><tr><th className={thCls}>Clause</th><th className={thCls}>What it sets</th><th className={thCls}>Your policy</th>
              <th className={thCls}>CreditProbe today</th><th className={thCls}>Change</th></tr></thead>
            <tbody>{rows.map((f) => (
              <tr key={f.id}>
                <td className={tdCls}>{f.clause ?? "–"}</td>
                <td className={wrapCls} title={f.quote}>{f.label}{f.conflict ? <> <Chip tone="negative" title={f.conflict.message}>Weaker than {f.conflict.regulation}</Chip></> : null}</td>
                <td className={tdCls}>{fmtValue(f.value, f.unit)}</td>
                <td className={tdCls}>{f.param ? fmtValue(f.param.in_force) : "–"}</td>
                <td className={tdCls}>{f.param?.change ? <Chip tone={f.param.change === "tighter" ? "accent" : f.param.change === "looser" ? "warning" : "neutral"}>{f.param.change}</Chip> : "–"}</td>
              </tr>))}</tbody>
          </table>
          {thr.length > 8 ? <SecondaryButton className="mt-2" onClick={() => setAll(!all)}>{all ? "Show fewer" : `Show all ${thr.length}`}</SecondaryButton> : null}
        </div>) : null}
      {defs.length ? (
        <div data-testid="try-policy-defaults">
          <p className="mb-1 text-[12px] font-medium text-text-primary">Not in your policy: CreditProbe defaults used ({defs.length})</p>
          <div className="flex flex-wrap gap-1.5">{defs.map((m) => (
            <Chip key={m.metric} tone="neutral" title={m.source}>{m.label}: {fmtValue(m.value, m.unit)} · default</Chip>))}</div>
        </div>) : null}
      {r.version ? (
        <div className="flex flex-wrap items-center gap-2">
          <Chip tone="warning">Demo-only version</Chip>
          <span className="text-[12px] text-text-secondary">{r.version.applies_to}</span>
          <SecondaryButton disabled={busy} data-testid="try-approve-policy" onClick={() => {
            setBusy(true);
            tryDocs.approvePolicy(sid).then((a) => onApprove(`Proposed to the bank's checker: ${a.items} items in ${a.where}.`),
              (e: unknown) => onApprove(errText(e))).finally(() => setBusy(false));
          }}>Approve as a policy proposal</SecondaryButton>
        </div>) : null}
    </div>
  );
}

function ExtractView({ r }: { r: ExtractResult }) {
  return (
    <div className="space-y-3">
      <p className="text-[13px] font-medium text-text-primary" data-testid="try-deal-line">{dealLine(r.deal)}</p>
      <div className="grid gap-3 lg:grid-cols-2">
        <div className="overflow-x-auto">
          <table className={tableCls} data-testid="try-deal-fields">
            <thead><tr><th className={thCls}>Field</th><th className={thCls}>Read</th><th className={thCls}>Where</th></tr></thead>
            <tbody>{r.fields.map((f) => (
              <tr key={f.field}><td className={tdCls}>{f.label}</td>
                <td className={wrapCls}>{f.field === "facility_type" ? facilityLabel(String(f.value)) : fmtValue(f.value)}</td>
                <td className={wrapCls}>{f.source}</td></tr>))}</tbody>
          </table>
        </div>
        <div className="space-y-2">
          {r.defaults.length ? (
            <div data-testid="try-deal-defaults">
              <p className="mb-1 text-[12px] font-medium text-text-primary">Defaults used ({r.defaults.length})</p>
              <ul className="space-y-1 text-[12px] text-text-secondary">{r.defaults.map((d) => (
                <li key={d.field} className="flex items-start gap-2"><Chip tone="warning">Default</Chip><span className="min-w-0">{d.why}</span></li>))}</ul>
            </div>) : <p className="text-[12px] text-text-secondary">Every field the engine needs was read from the proposal.</p>}
          {r.lines.length ? (
            <div className="overflow-x-auto">
              <table className={tableCls} data-testid="try-deal-lines">
                <thead><tr><th className={thCls}>Facility ({r.currency_in_proposal} m)</th><th className={thCls}>Existing</th><th className={thCls}>Proposed</th><th className={thCls}>bps</th></tr></thead>
                <tbody>{r.lines.map((l, i) => (
                  <tr key={i}><td className={wrapCls} title={l.facility_type ? facilityLabel(l.facility_type) : undefined}>{l.facility}</td>
                    <td className={tdCls}>{fmtValue(l.existing)}</td><td className={tdCls}>{fmtValue(l.proposed)}</td><td className={tdCls}>{fmtValue(l.pricing_bps)}</td></tr>))}</tbody>
              </table>
            </div>) : null}
          <p className="flex items-center gap-1 text-[11px] text-text-muted">Data lineage<InfoPopover title="Data Domains">{r.published.published ? `Published under ${r.published.scope}` : "Kept in this session only"} · {r.deal_id}</InfoPopover></p>
        </div>
      </div>
    </div>
  );
}

function ReviewView({ r }: { r: ReviewResult }) {
  const [all, setAll] = React.useState(false);
  const rows = all ? r.findings : r.findings.slice(0, 8);
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1.5">
        <Chip tone="positive">{r.policy_counts.supported} met</Chip>
        <Chip tone="negative">{r.policy_counts.contradicted + r.policy_counts.exception} breached</Chip>
        <Chip tone="warning">{r.policy_counts.unverifiable} need data</Chip>
        {r.decision ? <Chip tone="accent">{r.decision}</Chip> : null}
      </div>
      <div className="overflow-x-auto">
        <table className={tableCls} data-testid="try-review-findings">
          <thead><tr><th className={thCls}>Severity</th><th className={thCls}>Finding</th><th className={thCls}>Against</th></tr></thead>
          <tbody>{rows.map((f, i) => (
            <tr key={`${f.rule_id}-${i}`}><td className={tdCls}><Chip tone={sevTone(f.severity)}>{f.severity}</Chip></td>
              <td className={wrapCls}><span className="font-medium text-text-primary">{f.title}</span>{f.title ? ": " : ""}{f.finding}</td>
              <td className={wrapCls}>{f.source}</td></tr>))}</tbody>
        </table>
        {r.findings.length > 8 ? <SecondaryButton className="mt-2" onClick={() => setAll(!all)}>{all ? "Show fewer" : `Show all ${r.findings.length}`}</SecondaryButton> : null}
      </div>
      {r.policy_checks.length ? (
        <details className="text-[12px]"><summary className="cursor-pointer text-text-secondary">Every check of your clauses ({r.policy_checks.length})</summary>
          <ul className="mt-1 space-y-1">{r.policy_checks.map((c, i) => (
            <li key={i} className="flex items-start gap-2"><Chip tone={verdictTone(c.verdict)}>{verdictLabel(c.verdict)}</Chip>
              <span className="min-w-0">{c.source}: {c.finding}</span></li>))}</ul>
        </details>) : null}
    </div>
  );
}

function CounterView({ r, sid }: { r: CounterResult; sid: string }) {
  const cps = r.counter_proposals;
  return (
    <div className="space-y-2">
      {cps.length ? (
        <ul className="space-y-1 text-[12px]" data-testid="try-counter">{cps.map((c, i) => (
          <li key={i} className="rounded-md border border-border bg-surface px-3 py-2">
            <span className="font-medium text-text-primary">{String(c.label ?? c.title ?? c.name ?? `Counter-proposal ${i + 1}`)}</span>
            {c.summary ? <span className="text-text-secondary">: {String(c.summary)}</span> : null}
          </li>))}</ul>) : <p className="text-[12px] text-text-secondary">No counter-proposal: the optimiser found no better structure within your limits.</p>}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[12px] text-text-secondary">{r.engine}{r.paper?.answer?.decision ? `: ${r.paper.answer.decision}` : ""}</span>
        <a href={tryDocs.paperHref(sid)} className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-surface px-3 text-[12px] text-text-secondary hover:bg-surface-hover"
           data-testid="try-paper-docx"><Download size={14} aria-hidden /> Committee paper (Word)</a>
      </div>
    </div>
  );
}

function DraftView({ r, sid }: { r: DraftResult; sid: string }) {
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <Chip tone="accent">{langLabel(r.language)}</Chip>
        <span className="text-[12px] text-text-secondary">{r.engine} · {r.words} words{r.style_score != null ? ` · style score ${r.style_score}` : ""}</span>
        <a href={tryDocs.draftHref(sid)} className="ml-auto inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-surface px-3 text-[12px] text-text-secondary hover:bg-surface-hover"
           data-testid="try-draft-docx"><Download size={14} aria-hidden /> Draft (Word)</a>
      </div>
      <div dir={r.direction} lang={r.language} className={cn("max-h-[420px] space-y-3 overflow-y-auto rounded-md border border-border bg-surface p-3 text-[13px] leading-6",
        r.direction === "rtl" && "text-right")} data-testid="try-draft">
        {r.sections.map((s) => (
          <section key={s.key}>
            <h4 className="text-[13px] font-semibold text-text-primary">{s.heading}</h4>
            {s.paragraphs.map((p, i) => <p key={i} className="text-text-secondary">{p}</p>)}
            {s.bullets?.length ? <ul className="list-disc ps-5 text-text-secondary">{s.bullets.map((b, i) => <li key={i}>{b}</li>)}</ul> : null}
            {s.table?.rows?.length ? (
              <table className={cn(tableCls, "mt-1")}><tbody>{s.table.rows.slice(0, 12).map((row, i) => (
                <tr key={i}>{(row as unknown[]).map((c, j) => <td key={j} className={wrapCls}>{String(c ?? "")}</td>)}</tr>))}</tbody></table>) : null}
          </section>))}
      </div>
    </div>
  );
}

function StepRow({ i, st, sid, onApprove }: { i: number; st: Step; sid: string; onApprove: (m: string) => void }) {
  const [open, setOpen] = React.useState(true);
  const body = st.status === "done" && st.result ? (
    st.key === "policy" ? <PolicyView r={st.result as PolicyResult} sid={sid} onApprove={onApprove} />
      : st.key === "extract" ? <ExtractView r={st.result as ExtractResult} />
        : st.key === "review" ? <ReviewView r={st.result as ReviewResult} />
          : st.key === "counter" ? <CounterView r={st.result as CounterResult} sid={sid} />
            : st.key === "draft" ? <DraftView r={st.result as DraftResult} sid={sid} /> : null) : null;
  return (
    <li className="rounded-lg border border-border bg-surface" data-testid={`try-step-${st.key}`} data-status={st.status}>
      <button type="button" className="flex w-full items-start gap-3 px-3 py-2 text-left" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span className={cn("mt-0.5 inline-flex size-6 shrink-0 items-center justify-center rounded-full text-[12px] font-semibold",
          st.status === "done" ? "bg-positive-muted text-positive" : st.status === "error" ? "bg-negative-muted text-negative"
            : st.status === "running" ? "animate-pulse bg-accent-muted text-accent" : "bg-surface-sunken text-text-muted")}>{i + 1}</span>
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-2">
            <span className="text-[13px] font-semibold text-text-primary">{st.label}</span>
            <Chip tone={stepTone(st.status)}>{stepStatusLabel(st.status)}</Chip>
            {st.seconds != null ? <span className="text-[12px] tabular-nums text-text-muted">{secs(st.seconds)}</span> : null}
          </span>
          {st.summary ? <span className="mt-0.5 block text-[12px] text-text-secondary">{st.summary}</span> : null}
        </span>
      </button>
      {open && body ? <div className="border-t border-border/60 px-3 py-3">{body}</div> : null}
    </li>
  );
}

// ---------------------------------------------------------------- the run

export function TryDocsRun({ onExit, testId = "try-docs-run" }: { onExit?: () => void; testId?: string }) {
  const [ov, setOv] = React.useState<Overview | null>(null);
  const [s, setS] = React.useState<TrySession | null>(null);
  const [proposal, setProposal] = React.useState<File | null>(null);
  const [policy, setPolicy] = React.useState<File | null>(null);
  const [mode, setMode] = React.useState<Mode>("deterministic");
  const [busy, setBusy] = React.useState(false);
  const [err, setErr] = React.useState("");
  const [msg, setMsg] = React.useState("");
  const [wiped, setWiped] = React.useState<Wiped | null>(null);
  const sidRef = React.useRef<string | null>(null);

  React.useEffect(() => { tryDocs.overview().then(setOv, (e: unknown) => setErr(errText(e))); }, []);

  // a page closed without Exit still wipes the session (and the service wipes anything left after its time to live)
  React.useEffect(() => {
    const onHide = () => { if (sidRef.current) navigator.sendBeacon?.(tryDocs.wipeHref(sidRef.current)); };
    window.addEventListener("pagehide", onHide);
    return () => { window.removeEventListener("pagehide", onHide); onHide(); };
  }, []);

  const runFrom = React.useCallback(async (first: TrySession) => {
    let cur = first;
    for (const k of remaining(first)) {
      setS({ ...cur, steps: cur.steps.map((x) => (x.key === k ? { ...x, status: "running" } : x)) });
      try {
        cur = await tryDocs.step(cur.session_id, k);
      } catch (e) {
        setErr(errText(e));
        break;
      }
      setS(cur);
      if (cur.steps.find((x) => x.key === k)?.status !== "done") break;
    }
  }, []);

  const begin = (p: Promise<TrySession>) => {
    setBusy(true); setErr(""); setMsg(""); setWiped(null);
    p.then(async (x) => { sidRef.current = x.session_id; setS(x); await runFrom(x); }, (e: unknown) => setErr(errText(e)))
      .finally(() => setBusy(false));
  };

  const exit = () => {
    const sid = sidRef.current;
    if (!sid) { onExit?.(); return; }
    setBusy(true);
    tryDocs.wipe(sid).then((w) => { sidRef.current = null; setWiped(w); setS(null); setProposal(null); setPolicy(null); },
      (e: unknown) => setErr(errText(e))).finally(() => setBusy(false));
  };

  const steps = s?.steps ?? [];
  const review = steps.find((x) => x.key === "review" && x.status === "done")?.result as ReviewResult | undefined;
  const pol = steps.find((x) => x.key === "policy" && x.status === "done")?.result as PolicyResult | undefined;
  const draft = steps.find((x) => x.key === "draft" && x.status === "done")?.result as DraftResult | undefined;
  const ex = steps.find((x) => x.key === "extract" && x.status === "done")?.result as ExtractResult | undefined;

  return (
    <div className="space-y-3" data-testid={testId}>
      <Section title="Try it on your documents" testId="try-docs"
               info="Drop a credit proposal (Word, PDF or a scan; English or Arabic) and your credit policy. CreditProbe learns the policy, turns the proposal into a deal, reviews it against your clauses, prices a counter-proposal, writes the committee paper and drafts the memo in your memo's language. Each step is timed. Exit wipes the session."
               action={<>
                 {s ? <Chip tone="accent" testId="try-total">{secs(s.total_seconds)} total</Chip> : null}
                 {s ? <SecondaryButton onClick={exit} disabled={busy} data-testid="try-exit"><LogOut size={14} aria-hidden /> Exit and wipe</SecondaryButton>
                   : onExit ? <SecondaryButton onClick={onExit} data-testid="try-close">Close</SecondaryButton> : null}
               </>}>
        <div className="space-y-3">
          <PanelWords panel="try" className="" lines={ov || s ? () => writeTryDocs({ overview: ov, session: s }) : null} />
          <Notice text={s?.notice ?? ov?.notice ?? "Confidential demo session: your documents stay on this laptop and are wiped when you leave."}
                  model={s?.model_notice ?? (mode === "model" ? ov?.model_notice : null)} />
          {wiped ? <p className="text-[12px] text-positive" data-testid="try-wiped">Session wiped in {secs(wiped.seconds)}.<InfoPopover title="Wiped">The session deal, {wiped.rows_removed} stored rows and {Object.keys(wiped.files).length} working files removed.</InfoPopover></p> : null}
          {err ? <p className="text-[12px] text-negative" role="alert" data-testid="try-error">{err}</p> : null}
          {msg ? <p className="text-[12px] text-text-secondary">{msg}</p> : null}
          {!s ? (
            <div className="space-y-3" data-testid="try-upload">
              <div className="flex flex-col gap-3 md:flex-row">
                <FilePick label="Proposal" testId="try-proposal-file" file={proposal} onFile={setProposal}
                          info="The credit proposal or memo as the business wrote it: Word, PDF, or a scanned PDF or image (read by OCR). English or Arabic." />
                <FilePick label="Credit policy" optional testId="try-policy-file" file={policy} onFile={setPolicy}
                          info="Your credit policy (Word or PDF). What it does not set uses the CreditProbe default, shown as such. It stays a demo-only version unless approved." />
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <div role="radiogroup" aria-label="Mode" className="inline-flex overflow-hidden rounded-md border border-border text-[12px]">
                  {(["deterministic", "model"] as Mode[]).map((m) => (
                    <button key={m} type="button" role="radio" aria-checked={mode === m} data-testid={`try-mode-${m}`}
                            disabled={m === "model" && !ov?.model_available}
                            title={m === "model" && !ov?.model_available ? "No model key on this laptop: no-model mode only" : undefined}
                            onClick={() => setMode(m)}
                            className={cn("h-8 px-3 disabled:opacity-40", mode === m ? "bg-accent text-accent-contrast" : "bg-surface text-text-secondary hover:bg-surface-hover")}>
                      {m === "deterministic" ? "No model (deterministic)" : "Model polish"}</button>))}
                </div>
                <PrimaryButton disabled={!proposal || busy} data-testid="try-start" onClick={() => proposal && begin(tryDocs.start(proposal, policy, mode))}>
                  <Play size={14} aria-hidden /> Run on my documents</PrimaryButton>
                <SecondaryButton disabled={busy} data-testid="try-fallback" onClick={() => begin(tryDocs.fallback(mode))}
                                 title={ov ? `${ov.fallback.proposal} with ${ov.fallback.policy}` : undefined}>Use the prepared case</SecondaryButton>
                {ov && !ov.ocr.available ? <span className="text-[11px] text-text-muted">Scans need OCR, which is not installed on this laptop.</span> : null}
              </div>
            </div>
          ) : (
            <>
              <p className="text-[14px] font-semibold text-text-primary" data-testid="try-answer">{answerLine(s)}</p>
              <KpiRow tiles={[
                { label: "Time", value: secs(s.total_seconds), sub: `${steps.filter((x) => x.status === "done").length} of ${steps.length} steps`,
                  info: "System time of each step, upload to drafted memo; your reading time is not counted.", testId: "try-kpi-time" },
                { label: "Your policy", value: pol ? String(pol.found.filter((f) => f.type === "threshold").length) : "–",
                  sub: pol ? `thresholds · ${pol.missing.filter((m) => m.value != null).length} defaults` : "not read yet",
                  info: "Thresholds read from your policy, and the parameters it does not set (CreditProbe defaults)." },
                { label: "Findings", value: review ? String(review.findings.length) : "–",
                  sub: review ? `${review.severity.critical} critical · ${review.severity.major} major` : "not reviewed yet",
                  tone: review && review.severity.critical ? "negative" : "neutral",
                  info: "Breaches of your policy clauses plus the CreditProbe rule book findings." },
                { label: "Draft", value: draft ? langLabel(draft.language) : ex ? langLabel(s.documents.proposal?.language ?? "en") : "–",
                  sub: draft ? `${draft.sections.length} sections · ${draft.words} words` : "in your memo's language",
                  info: "The memo is drafted in the language of the proposal you uploaded." },
              ]} />
              <ol className="space-y-2" data-testid="try-steps">
                {steps.map((st, i) => <StepRow key={st.key} i={i} st={st} sid={s.session_id} onApprove={setMsg} />)}
              </ol>
              {!busy && !s.complete && remaining(s).length ? (
                <PrimaryButton data-testid="try-continue" onClick={() => { setErr(""); setBusy(true); runFrom(s).finally(() => setBusy(false)); }}>
                  <Play size={14} aria-hidden /> Run the remaining steps</PrimaryButton>) : null}
            </>
          )}
        </div>
      </Section>
    </div>
  );
}
