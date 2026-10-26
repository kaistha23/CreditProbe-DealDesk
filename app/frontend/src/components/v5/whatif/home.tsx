"use client";

/**
 * The What-If home (PLAN_R2 6.4-6.5): a chat box at the top that opens a
 * thread, and the scenario library below it -- the standard scenarios and the
 * repository of saved ones (owner, date, model, ECL impact, tags). Selecting a
 * scenario opens a thread that first describes it, then shows its impact.
 *
 * Opened with ?cohort=<id> (Early Warning's "Export to What-If") it opens a
 * new thread on that cohort; the address is replaced, so Back returns to
 * Early Warning, not to a page that would open another thread.
 */

import { landingQuestion, rememberPendingMemo } from "@/lib/v5/thread-actions-pending";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { useUrlState } from "@/lib/v5/back";
import { FileText, Trash2 } from "lucide-react";

import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import {
  type DomainId, type LibraryRow, type ReportItem, LEGACY_SCENARIOS, asOfLabel, pct, rememberRun, reportPackHref,
  sar, scenarioReportHref, useLoad, whatif,
} from "@/lib/v5/whatif";

import { AddToReport, ShareButton } from "./share";
import { friendlyMessage } from "@/lib/v5/errors";
import { startFresh } from "@/lib/v5/thread-rule";
import { EclDiagnostics } from "./ecl-diagnostics";
import { ModuleLanding } from "@/components/v5/landing/module-landing";
import { whatIfPlaceholder, whatIfStarterChips } from "@/lib/v5/placeholders";
import { NetworkToolsMenu } from "@/components/v5/intel/network";

function BookToggle({ domain, onChange }: { domain: DomainId; onChange: (d: DomainId) => void }) {
  return (
    <div className="inline-flex rounded-md border border-border bg-surface p-0.5" role="group" aria-label="Book">
      {(["corporate", "retail"] as const).map((d) => (
        <button key={d} type="button" onClick={() => onChange(d)} aria-pressed={domain === d} data-testid={`whatif-book-${d}`}
                className={cn("rounded px-3 py-1 text-[12px] font-medium capitalize",
                              domain === d ? "bg-accent text-accent-contrast" : "text-text-secondary hover:bg-surface-hover")}>{d}</button>))}
    </div>
  );
}

const when = (t: number) => (t ? new Date(t * 1000).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }) : "—");

export function WhatIfHome() {
  const router = useRouter();
  const params = useSearchParams();
  const domain = (params.get("domain") === "retail" ? "retail" : "corporate") as DomainId;
  const cohort = params.get("cohort") ?? "";
  const legacy = params.get("scenario") ?? "";
  const openId = params.get("open") ?? "";
  const [draft, setDraft] = React.useState("");
  const [method, setMethod] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const [notice, setNotice] = React.useState("");
  const [tab, setTab] = useUrlState<"standard" | "saved">("lib", "standard", "replace");
  const [version, setVersion] = React.useState(0);
  const opening = React.useRef(false);

  const meta = useLoad(() => whatif.meta(domain), `meta-${domain}`);
  const lib = useLoad(() => whatif.library(domain), `lib-${domain}-${version}`);
  const threads = useLoad(() => whatif.threads(domain), `threads-${domain}-${version}`);
  const pack = useLoad(() => whatif.reportPack(), `pack-${version}`);

  const open = React.useCallback(async (body: Parameters<typeof whatif.createThread>[0], replace = false) => {
    setBusy(true);
    setError("");
    try {
      // R16 m (M6): the landing box, its starter buttons and every library card open a NEW thread (never the last one).
      // R16 t (M7): "write a note on X" asks X; the thread writes the Word note once it is answered
      const lq = body && typeof (body as { question?: unknown }).question === "string" ? landingQuestion((body as { question: string }).question) : null;
      if (lq?.memo) body = { ...body, question: lq.ask };
      const t = await whatif.createThread(startFresh("whatif", body));
      if (t.run) rememberRun(t.thread_id, t.run.run_id);
      if (lq?.memo) rememberPendingMemo("whatif", t.thread_id, lq.memo);
      const url = `/what-if/thread/${t.thread_id}`;
      if (replace) router.replace(url); else router.push(url);
    } catch (e) {
      setError(friendlyMessage(e));
      setBusy(false);
    }
  }, [router]);

  // Early Warning "Export to What-If" and the older deep links open a thread at once.
  React.useEffect(() => {
    if (opening.current) return;
    const body = cohort ? { cohort_id: cohort } : openId ? { domain, library_id: openId }
      : legacy ? { domain, library_id: `std-${domain}-${LEGACY_SCENARIOS[domain]?.[legacy] ?? legacy}` } : null;
    if (!body) return;
    opening.current = true;
    void Promise.resolve().then(() => open(body, true));
  }, [cohort, legacy, openId, domain, open]);

  const setDomain = (d: DomainId) => router.push(`/what-if?domain=${d}`);
  const ask = (text: string) => {
    const q = text.trim();
    if (!q) return;
    const withMethod = method && !/\b(delta|xgboost|xgb)\b/i.test(q) ? `${q} using ${method === "xgboost" ? "XGBoost" : "the delta method"}` : q;
    void open({ domain, question: withMethod });
  };

  if (cohort || legacy || openId) {
    return (
      <div className="space-y-3" data-testid="whatif-opening">
        {error ? <p className="text-sm text-negative" role="alert">{error}</p> : <p className="text-[13px] text-text-muted">Opening a What-If thread…</p>}
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  const m = meta.data;
  const lab = m?.labels;
  const rows: LibraryRow[] = (tab === "standard" ? lib.data?.standard : lib.data?.saved) ?? [];
  return (
    <div className="space-y-5" data-testid="whatif-home">
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-text-muted">Intelligence</p>
          <h1 className="text-2xl font-semibold text-text-primary">What-If</h1>
        </div>
        <BookToggle domain={domain} onChange={setDomain} />
        {m ? <p className="text-[11px] text-text-muted" data-testid="whatif-asof">As of {asOfLabel(m.as_of)} · {lab?.book} · {lab?.frequency} · SAR</p> : null}
        <div className="ml-auto flex items-center gap-2 text-[12px]">
          <Link className="text-accent hover:underline" href={`/what-if/models/${domain}/delta`} data-testid="whatif-card-delta">Delta model card</Link>
          <Link className="text-accent hover:underline" href={`/what-if/models/${domain}/xgboost`} data-testid="whatif-card-xgboost">XGBoost model card</Link>
          {domain === "corporate" ? <NetworkToolsMenu module="whatif" /> : null}
        </div>
      </div>

      {/* R13 X (J7): the centred chat box and small cards of recent threads (ModuleLanding); the scenario library below. */}
      <ModuleLanding ids="whatif" title="Ask What-If" value={draft} onChange={setDraft} onAsk={ask} busy={busy} error={error}
                     placeholder={whatIfPlaceholder(m ? lab?.book : undefined)}
                     examples={m ? whatIfStarterChips(m.examples) : []}
                     extraChips={<>
                        <button type="button" onClick={() => ask("Stress the corporate book: mild, moderate and severe")} disabled={busy}
                                data-testid="whatif-calibrated" title="Severities calibrated on history, with the evidence and a methodology memo"
                                className="rounded-full border border-accent/50 px-3 py-1 text-[12px] text-accent hover:border-accent">Mild, moderate, severe</button>
                        <button type="button" onClick={() => ask("what scenario should I run?")} disabled={busy} data-testid="whatif-brainstorm"
                                         className="rounded-full border border-dashed border-border px-3 py-1 text-[12px] text-text-muted hover:border-accent">Help me shape a scenario</button></>}
                     trailing={<select value={method} onChange={(e) => setMethod(e.target.value)} aria-label="Model" data-testid="whatif-model-pick"
                                       className="h-8 rounded-md border border-border bg-surface px-2 text-[12px] text-text-secondary">
                       <option value="">Model: ask me</option><option value="delta">Delta method</option><option value="xgboost">XGBoost</option></select>}
                     recentTitle="Recent threads" recentLoading={!threads.data && !threads.error} recentEmpty="No threads yet."
                     recent={(threads.data?.threads ?? []).slice(0, 6).map((t) => ({
                       key: t.thread_id, title: t.title, testId: "whatif-recent-thread",
                       sub: `${t.period}${t.cohort_id ? (t.cohort_id.startsWith("b360-cohort-") ? " · Borrower 360 selection" : " · Early Warning cohort") : ""}`,
                       meta: when(t.updated_at), onOpen: () => router.push(`/what-if/thread/${t.thread_id}`) }))} />
      {notice ? <p className="rounded-md border border-border bg-surface px-3 py-2 text-[12px]" data-testid="whatif-notice">{notice}</p> : null}

      <Card className="space-y-3 p-4" data-testid="whatif-library">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-[14px] font-semibold text-text-primary">Scenario library</h2>
          <div className="inline-flex rounded-md border border-border p-0.5 text-[12px]" role="tablist">
            <button type="button" role="tab" aria-selected={tab === "standard"} onClick={() => setTab("standard")} data-testid="whatif-lib-standard"
                    className={cn("rounded px-2 py-0.5", tab === "standard" ? "bg-accent text-accent-contrast" : "")}>Standard ({lib.data?.standard.length ?? 0})</button>
            <button type="button" role="tab" aria-selected={tab === "saved"} onClick={() => setTab("saved")} data-testid="whatif-lib-saved"
                    className={cn("rounded px-2 py-0.5", tab === "saved" ? "bg-accent text-accent-contrast" : "")}>Saved repository ({lib.data?.saved.length ?? 0})</button>
          </div>
        </div>
        {lib.error ? <p className="text-sm text-negative" role="alert">{lib.error}</p> : null}
        {!lib.data ? <Skeleton className="h-32 w-full" /> : rows.length === 0 ? (
          <p className="text-[12px] text-text-muted">No saved scenarios yet. Save one from a thread.</p>) : tab === "standard" ? (
          <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-4">
            {rows.map((r) => (
              <button key={r.scenario_id} type="button" onClick={() => void open({ domain, library_id: r.scenario_id })} disabled={busy}
                      data-testid={`whatif-lib-${r.scenario_id}`}
                      className="rounded-md border border-border bg-surface p-3 text-left hover:border-accent disabled:opacity-50">
                <p className="text-[13px] font-semibold text-text-primary">{r.name}</p>
                <p className="mt-0.5 text-[11px] text-text-muted">{r.description}</p>
                <p className="mt-1 flex flex-wrap gap-1">{r.tags.map((t) => <span key={t} className="rounded bg-surface-hover px-1.5 text-[10px] text-text-muted">{t}</span>)}</p>
              </button>))}
          </div>) : (
          <div className="overflow-auto">
            <table className="w-full border-collapse text-[12px]" data-testid="whatif-repository">
              <thead><tr className="border-b border-border text-left text-[11px] text-text-muted">
                <th className="px-2 py-1">Scenario</th><th className="px-2 py-1">Owner</th><th className="px-2 py-1">Date</th><th className="px-2 py-1">Model</th>
                <th className="px-2 py-1 text-right">ECL before</th><th className="px-2 py-1 text-right">ECL after</th><th className="px-2 py-1 text-right">Impact</th>
                <th className="px-2 py-1">Tags</th><th className="px-2 py-1"></th></tr></thead>
              <tbody>{rows.map((r) => (
                <tr key={r.scenario_id} className="border-b border-border/50" data-testid={`whatif-saved-${r.scenario_id}`}>
                  <td className="px-2 py-1"><button type="button" className="text-left text-accent hover:underline" onClick={() => void open({ domain, library_id: r.scenario_id })}>{r.name}</button>
                    <span className="block text-[11px] text-text-muted">{r.steps.join("; ")}</span></td>
                  <td className="px-2 py-1">{r.owner || "—"}</td><td className="px-2 py-1">{when(r.created_at)}</td>
                  <td className="px-2 py-1">{r.method === "xgboost" ? "XGBoost" : "Delta"}</td>
                  <td className="px-2 py-1 text-right tabular-nums">{sar(r.ecl_before)}</td><td className="px-2 py-1 text-right tabular-nums">{sar(r.ecl_after)}</td>
                  <td className="px-2 py-1 text-right tabular-nums">{r.change === null ? "—" : `${sar(r.change)} (${pct(r.change_pct, 1)})`}</td>
                  <td className="px-2 py-1">{r.tags.join(", ")}</td>
                  <td className="px-2 py-1"><div className="flex gap-1">
                    <ShareButton kind="whatif-scenario" id={r.scenario_id} label={r.name} compact
                                 href={`/what-if?domain=${r.domain}&open=${r.scenario_id}`}
                                 summary={`${r.domain === "corporate" ? "Corporate" : "Retail"}. ECL ${sar(r.ecl_before)} to ${sar(r.ecl_after)} (${pct(r.change_pct, 1)}).`}
                                 meta={{ book: r.domain, period: r.period, model: r.method }} reportUrl={scenarioReportHref(r.scenario_id)} />
                    <a href={scenarioReportHref(r.scenario_id)} title="Word report" className="rounded-md border border-border p-1 hover:bg-surface-hover"><FileText size={13} /></a>
                    <AddToReport scenarioId={r.scenario_id} onDone={(msg) => { setNotice(msg); setVersion((v) => v + 1); }} />
                    <button type="button" title="Delete" className="rounded-md border border-border p-1 hover:bg-surface-hover"
                            onClick={async () => { if (window.confirm(`Delete “${r.name}”?`)) { await whatif.removeScenario(r.scenario_id).catch(() => null); setVersion((v) => v + 1); } }}>
                      <Trash2 size={13} /></button></div></td>
                </tr>))}</tbody>
            </table>
          </div>)}
      </Card>

      {/* PLAN_R9 C3 (P6): ECL diagnostics, and the ECL of current warnings (P3), on the book in view. */}
      <EclDiagnostics domain={domain} />

      <div className="grid gap-4">
        <Card className="space-y-2 p-4" data-testid="whatif-pack">
          <div className="flex items-baseline justify-between"><h2 className="text-[14px] font-semibold text-text-primary">Report pack</h2>
            {(pack.data?.items.length ?? 0) > 0 ? <a href={reportPackHref()} className="text-[12px] text-accent underline" data-testid="whatif-pack-download">Download the pack (Word)</a> : null}</div>
          {(pack.data?.items ?? []).map((i: ReportItem) => (
            <div key={i.item_id} className="flex items-center justify-between rounded px-2 py-1 text-[12px] hover:bg-surface-hover">
              <span>{i.name} <span className="text-text-muted">· {i.domain} · {i.method === "xgboost" ? "XGBoost" : "Delta"}{i.change !== null ? ` · ${sar(i.change)}` : ""}</span></span>
              <button type="button" onClick={async () => { await whatif.removeFromReport(i.item_id).catch(() => null); setVersion((v) => v + 1); }} title="Remove"><Trash2 size={12} /></button>
            </div>))}
          {pack.data && !pack.data.items.length ? <p className="text-[12px] text-text-muted">No scenarios in the pack yet.</p> : null}
        </Card>
      </div>
    </div>
  );
}
