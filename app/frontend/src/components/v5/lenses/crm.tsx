"use client";

/**
 * P1 CBUAE CRM Intelligence in Lenses (PLAN_R9 Session D).
 *
 *  CrmUploadThread  the circular dropped into the Lenses chat: live steps (reading articles -> mapping obligations ->
 *                   checking data), then the obligations by article, each mapped to library metrics and marked
 *                   available / partial / data gap; "Create the dashboard" builds and opens the CBUAE CRM lens.
 *  CrmLibrary       Lenses -> Library: the CBUAE CRM metric library (definition, formula, fields, article, frequency,
 *                   threshold, data status).
 *  CrmFindings      the findings at the top of a CRM lens, "Powered by P1".
 */

import { useRouter } from "next/navigation";
import * as React from "react";
import { Check, FileText, LayoutDashboard, Loader2 } from "lucide-react";

import { Card } from "@/components/ui/card";
import { PoweredBy } from "@/components/v5/core/powered-by";
import { InfoPopover } from "@/components/ui/info-popover";
import { cn } from "@/lib/utils";
import { type Book, LensesError, crm, type CrmFinding, type CrmLibrary as Lib, type CrmUpload } from "@/lib/v5/lenses";
import { friendlyMessage } from "@/lib/v5/errors";

/** "Powered by P1" through the shared component (Session G): the pack, the article, the confidence and the trace. */
export function PoweredByP1({ rule, confidence = "high", className }: { rule?: string; confidence?: string; className?: string }) {
  const c = (confidence === "medium" || confidence === "low" ? confidence : "high") as "high" | "medium" | "low";
  return <PoweredBy pack="P1" article={rule || "CBUAE Credit Risk Management Standards"} confidence={c}
                    trace={{ href: "/lenses?tab=library" }} className={className} />;
}

const COVER_TONE: Record<string, string> = {
  available: "border-positive/40 text-positive", partial: "border-warning/50 text-warning",
  "data gap": "border-negative/40 text-negative", gap: "border-negative/40 text-negative", qualitative: "border-border text-text-muted",
};
const COVER_WORD: Record<string, string> = { available: "Available", partial: "Partial", "data gap": "Data gap", gap: "Data gap", qualitative: "Policy only" };

export function Coverage({ value }: { value: string }) {
  return <span className={cn("whitespace-nowrap rounded-full border px-2 py-0.5 text-[10px] font-medium", COVER_TONE[value] ?? COVER_TONE.qualitative)}
               data-testid="crm-coverage">{COVER_WORD[value] ?? value}</span>;
}

export const CREATE_WORDS = /\b(create|build|make|generate)\b.*\bdashboard\b|^\s*dashboard\s*$/i;

interface Step { label: string; detail: string; done: boolean }
const PLAN_STEPS = ["Reading the articles", "Mapping obligations", "Checking data"];

export function CrmUploadThread({ file, book, onReset, createSignal }: { file: File; book: Book; onReset: () => void; createSignal: number }) {
  const router = useRouter();
  const [steps, setSteps] = React.useState<Step[]>(PLAN_STEPS.map((l) => ({ label: l, detail: "", done: false })));
  const [result, setResult] = React.useState<CrmUpload | null>(null);
  const [error, setError] = React.useState("");
  const [building, setBuilding] = React.useState(false);
  const [open, setOpen] = React.useState<string>("");
  const started = React.useRef(0);

  React.useEffect(() => {
    let live = true;
    const t0 = Date.now();
    started.current = t0;
    // the parent remounts this thread (key) for every new file, so the state starts empty
    crm.upload(file).then(async (r) => {
      // the server's steps, shown one by one so the reader can follow them (about a second in all)
      for (let i = 0; i < r.steps.length; i++) {
        const wait = Math.max(0, 450 * (i + 1) - (Date.now() - t0));
        await new Promise((ok) => setTimeout(ok, wait));
        if (!live) return;
        setSteps((s) => s.map((x, k) => (k === i ? { label: r.steps[i].label, detail: r.steps[i].detail, done: true } : x)));
      }
      if (live) setResult(r);
    }).catch((e) => { if (live) setError(friendlyMessage(e)); });
    return () => { live = false; };
  }, [file]);

  const busy = React.useRef(false);
  const create = async () => {
    if (busy.current) return;
    busy.current = true;
    setBuilding(true); setError("");
    try {
      const out = await crm.dashboard({ book, upload_id: result?.upload_id });
      router.push(out.href);
    } catch (e) {
      setError(e instanceof LensesError ? e.message : friendlyMessage(e));
      setBuilding(false);
      busy.current = false;
    }
  };
  const createRef = React.useRef(create);
  React.useEffect(() => { createRef.current = create; });

  React.useEffect(() => {
    if (createSignal && result) void Promise.resolve().then(() => createRef.current());
  }, [createSignal]); // eslint-disable-line react-hooks/exhaustive-deps

  const running = !result && !error;
  return (
    <div className="space-y-3" data-testid="crm-thread" data-state={result ? "answered" : error ? "error" : "running"}>
      <div className="flex justify-end">
        <p className="inline-flex items-center gap-1.5 rounded-lg bg-surface-hover px-3 py-1.5 text-[13px] text-text-primary" data-testid="crm-user-turn">
          <FileText size={14} className="text-accent" /> {file.name}</p>
      </div>
      <ol className="space-y-1" data-testid="crm-steps">
        {steps.map((s, i) => (
          <li key={i} className="flex items-center gap-2 text-[12px]" data-testid="crm-step" data-done={s.done ? "1" : "0"}>
            {s.done ? <Check size={13} className="text-positive" /> : running ? <Loader2 size={13} className="animate-spin text-text-muted" /> : <span className="w-[13px]" />}
            <span className={s.done ? "text-text-primary" : "text-text-muted"}>{s.label}</span>
            {s.detail ? <span className="text-text-muted">· {s.detail}</span> : null}
          </li>))}
      </ol>
      {error ? (
        <p className="text-[12px] text-negative" role="alert" data-testid="crm-error">{error}
          <button type="button" onClick={onReset} className="ml-2 underline">Start again</button></p>) : null}
      {result ? (
        <div className="space-y-3" data-testid="crm-answer">
          <p className="text-[13px] leading-relaxed text-text-primary">
            <b>{result.document}</b>: <b>{result.obligations}</b> obligations across <b>{result.articles.length}</b> articles, measured by{" "}
            <b>{result.metrics}</b> library metrics. On your data today <b>{result.coverage.available}</b> are available,{" "}
            <b>{result.coverage.partial}</b> partial and <b>{result.coverage.gap}</b> are data gaps.
          </p>
          <p className="text-[11px] text-text-muted">{result.method}</p>
          <div className="overflow-hidden rounded-md border border-border" data-testid="crm-articles">
            <table className="w-full text-[12px]">
              <thead className="bg-surface-hover text-left text-[10px] uppercase tracking-wide text-text-muted">
                <tr><th className="px-2 py-1.5">Article</th><th className="px-2 py-1.5 text-right">Obligations</th><th className="px-2 py-1.5">Library metrics</th><th className="px-2 py-1.5">Data</th></tr>
              </thead>
              <tbody>
                {result.articles.map((a) => (
                  <React.Fragment key={a.article}>
                    <tr className="cursor-pointer border-t border-border hover:bg-surface-hover" onClick={() => setOpen(open === a.article ? "" : a.article)}
                        data-testid="crm-article-row">
                      <td className="px-2 py-1.5"><b>{a.article}</b> <span className="text-text-secondary">{a.title}</span></td>
                      <td className="px-2 py-1.5 text-right tabular-nums">{a.obligations}</td>
                      <td className="px-2 py-1.5">
                        <div className="flex flex-wrap gap-1">
                          {a.metrics.length ? a.metrics.map((m) => (
                            <span key={m.id} title={m.closes_with ? `Closes with the ${m.closes_with} domain` : m.status}
                                  className={cn("rounded border px-1.5 py-0.5 text-[10px]", COVER_TONE[m.status])}>{m.name}</span>))
                            : <span className="text-[11px] text-text-muted">Governance and policy text</span>}
                        </div>
                      </td>
                      <td className="px-2 py-1.5"><Coverage value={a.coverage} /></td>
                    </tr>
                    {open === a.article ? (
                      <tr className="border-t border-border bg-surface" data-testid="crm-article-items">
                        <td colSpan={4} className="px-3 py-2">
                          <ul className="space-y-1">
                            {a.items.map((it, i) => (
                              <li key={i} className="flex items-start gap-2 text-[11px]">
                                <span className="shrink-0 font-semibold text-text-secondary">{it.clause}</span>
                                <span className="flex-1 text-text-primary">{it.text}</span>
                                <Coverage value={it.coverage} />
                              </li>))}
                            {!a.items.length ? <li className="text-[11px] text-text-muted">Definitions only: no obligation to measure.</li> : null}
                          </ul>
                        </td>
                      </tr>) : null}
                  </React.Fragment>))}
              </tbody>
            </table>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" onClick={() => void create()} disabled={building} data-testid="crm-create-dashboard"
                    className="inline-flex items-center gap-1.5 rounded-md bg-accent px-4 py-2 text-[13px] font-medium text-accent-contrast disabled:opacity-50">
              {building ? <Loader2 size={14} className="animate-spin" /> : <LayoutDashboard size={14} />} Create the dashboard</button>
            <span className="text-[11px] text-text-muted">or type &ldquo;create the dashboard&rdquo;</span>
            <PoweredByP1 rule={result.powered_by.rule || "general mapper"} confidence={result.powered_by.confidence} className="ml-auto" />
          </div>
          {building ? <p className="text-[12px] text-text-muted" data-testid="crm-building">Building the CBUAE CRM dashboard…</p> : null}
        </div>) : null}
    </div>
  );
}

export function CrmLibraryPanel({ onClose }: { onClose: () => void }) {
  const [lib, setLib] = React.useState<Lib | null>(null);
  const [error, setError] = React.useState("");
  const [group, setGroup] = React.useState("");
  React.useEffect(() => { crm.library().then(setLib).catch((e) => setError(friendlyMessage(e))); }, []);
  const rows = (lib?.metrics ?? []).filter((m) => !group || m.group === group);
  return (
    <Card className="space-y-3 p-4" data-testid="crm-library">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <button type="button" onClick={onClose} className="rounded border border-border px-2 py-0.5 text-[12px] text-text-secondary hover:bg-surface-hover"
                  data-testid="crm-library-back">Back</button>
          <h2 className="text-[15px] font-semibold text-text-primary">CBUAE CRM metric library</h2>
          <InfoPopover title="About the library">
            <p>Every obligation of the CBUAE Credit Risk Management Standards that a dashboard can measure, with its definition, formula,
              the data fields it needs, its article, frequency and threshold. &ldquo;Data gap&rdquo; names the data domain that closes it.</p>
          </InfoPopover>
        </div>
        {lib ? <p className="text-[12px] text-text-secondary"><b>{lib.total}</b> metrics · <b>{lib.counts.available}</b> available · <b>{lib.counts.partial}</b> partial · <b>{lib.counts.gap}</b> data gaps</p> : null}
      </div>
      {lib ? <PoweredByP1 rule={`version ${lib.pack.version}`} /> : null}
      <div className="flex flex-wrap gap-1.5">
        {["", ...(lib?.groups ?? [])].map((g) => (
          <button key={g || "all"} type="button" onClick={() => setGroup(g)} data-testid={`crm-library-group-${g || "all"}`}
                  className={cn("rounded-full border px-2.5 py-0.5 text-[12px]", group === g ? "border-accent bg-accent text-accent-contrast" : "border-border text-text-secondary hover:border-accent")}>
            {g || "All"}</button>))}
      </div>
      {error ? <p className="text-[12px] text-negative" role="alert">{error}</p> : null}
      <div className="overflow-x-auto rounded-md border border-border">
        <table className="w-full text-[12px]" data-testid="crm-library-table">
          <thead className="bg-surface-hover text-left text-[10px] uppercase tracking-wide text-text-muted">
            <tr>{["Metric", "Definition", "Formula", "Data fields", "Article", "Frequency", "Threshold", "Data"].map((h) => <th key={h} className="px-2 py-1.5">{h}</th>)}</tr>
          </thead>
          <tbody>
            {rows.map((m) => (
              <tr key={m.id} className="border-t border-border align-top" data-testid="crm-library-row">
                <td className="px-2 py-1.5"><b>{m.name}</b><div className="text-[10px] text-text-muted">{m.id} · {m.group}</div></td>
                <td className="px-2 py-1.5 text-text-secondary">{m.definition}</td>
                <td className="px-2 py-1.5 font-mono text-[11px]">{m.formula}</td>
                <td className="px-2 py-1.5 text-text-secondary">{m.fields}</td>
                <td className="whitespace-nowrap px-2 py-1.5">{m.article.replace("CBUAE CRM ", "")}</td>
                <td className="px-2 py-1.5">{m.frequency}</td>
                <td className="px-2 py-1.5">{m.threshold}</td>
                <td className="px-2 py-1.5"><Coverage value={m.status} />{m.closes_with ? <div className="mt-0.5 text-[10px] text-text-muted">{m.closes_with} domain</div> : null}</td>
              </tr>))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

export function CrmFindings({ findings }: { findings: CrmFinding[] }) {
  if (!findings?.length) return null;
  return (
    <Card className="space-y-2 border-accent/40 p-4" data-testid="crm-findings">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-[13px] font-semibold text-text-primary">What CBUAE CRM Intelligence found</h2>
        <PoweredByP1 rule="CBUAE CRM Art. 6-12" />
      </div>
      <ol className="space-y-1.5">
        {findings.map((f, i) => (
          <li key={i} className="flex items-start gap-2 text-[13px]" data-testid="crm-finding">
            <span className="mt-0.5 inline-flex h-5 min-w-[3.5rem] shrink-0 items-center justify-center rounded bg-accent/10 px-1.5 text-[11px] font-semibold tabular-nums text-accent">{f.figure}</span>
            <span className="flex-1 text-text-primary">{f.text}</span>
            {f.href ? <a href={f.href} className="shrink-0 whitespace-nowrap text-[11px] text-accent underline">{f.article.replace("CBUAE CRM ", "")}</a>
              : <span className="shrink-0 whitespace-nowrap text-[11px] text-text-muted">{f.article.replace("CBUAE CRM ", "")}</span>}
          </li>))}
      </ol>
    </Card>
  );
}
