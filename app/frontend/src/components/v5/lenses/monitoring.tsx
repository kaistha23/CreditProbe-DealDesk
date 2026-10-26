"use client";

/**
 * R11 Session K (PLAN_R11_AGENTS K4): the Monitoring agent panel in Lenses.
 *
 *   <MonitoringAgentButton scope={{ lensId }} />   or   scope={{ book, filters }}
 *
 * One entry in the lens header opens a right-side panel with three tabs:
 *   Proposed  the agent's ranked monitoring set: definition, threshold, why, back-tested alert rate (8 quarters);
 *             accept, edit (re-back-tested at once) or reject each metric; approve or reject the set (risk approvers)
 *   Active    the approved set, its schedule and the monitoring lens; run now; review the set
 *   Alerts    the latest alerts, each explained in two lines with the steps that produced every figure
 * Runs open in the shared AgentRunDrawer; the AgentInbox lists this scope's runs. Every figure comes from the
 * agent's tools (backend/agents_v5/lenses) through the agents service (8517); nothing here computes a number.
 */

import Link from "next/link";
import * as React from "react";
import { Check, ExternalLink, Loader2, Pencil, Play, Radar, RefreshCw, X } from "lucide-react";

import { AgentInbox, AgentRunDrawer } from "@/components/v5/core/agent-run";
import { KpiRow, type KpiTile } from "@/components/v5/core/kpi-row";
import { Chip, PrimaryButton, SecondaryButton, tableCls, tdCls, thCls } from "@/components/v5/dealdesk/kit";
import { agentsOrigin } from "@/lib/v5/agents";
import { friendlyError } from "@/lib/v5/errors";
import { cn } from "@/lib/utils";

import { type MonitorScope, type MonitorTab, scopeQuery } from "./monitoring-scope";
import { InfoPopover } from "@/components/ui/info-popover"; // R13 X: notes behind the (i)

export { monitorScopeOf, monitorTabOf, type MonitorScope } from "./monitoring-scope";

const AGENT = "lenses.monitoring";
const BASE = "/api/v1/agents/lenses";

type Tab = MonitorTab;

interface Threshold { logic: "absolute" | "change" | "zscore" | "appetite"; k?: number; level?: number; trigger?: number; limit?: number; direction?: string }
interface Backtest { quarters: number; fired: number; rate: number | null; fired_periods: string[]; evaluated_periods: string[]; label: string }
interface MonMetric {
  key: string; rank?: number; label: string; unit: string; scope: string; frequency: string; threshold: Threshold; threshold_text: string;
  why: string; sources: string[]; backtest: Backtest; noise: string; value: number; now_display: string; status: string;
  definition?: { tile?: { type: string }; catalogue_metric?: string; custom_metric?: { label: string } }; retired?: boolean;
  now_period?: string; firing?: boolean;
}
interface Proposal {
  proposal_id: string; kind: "monitoring_set" | "monitoring_changes"; approval_id: string | null; status: string; approver_role: string;
  expires_at: string | number; requested_by: string; run_id: string; maker: string; decided_by: string;
  payload: { label?: string; metrics?: MonMetric[]; dropped?: { key: string; label: string; reason: string; why: string }[];
             changes?: { key: string; label: string; action: string; why: string; to_text?: string }[] };
}
interface Alert {
  alert_id: string; metric_key: string; label: string; period: string; severity: "high" | "alert"; status: string; display: string; headline: string;
  explanation: string[]; detail: { run_id?: string; evidence?: string[]; threshold_text?: string }; created_at: number;
}
interface Panel {
  scope: { scope_key: string; label: string; book: string; lens_id: string; lens_name: string; period: string };
  pending: Proposal[]; decided: Proposal[];
  active: null | { set_id: string; label: string; lens_id: string; version: number; approved_by: string; created_by: string;
                   schedule: { cron: string; text: string } | null; metrics: MonMetric[]; retired: MonMetric[] };
  alerts: Alert[]; runs: { run_id: string; status: string; headline: string; created_at: string; trigger: string }[];
  can_decide: boolean; me: string;
}
interface RunResult { run_id: string; status: string; output: { headline?: string; proposal_id?: string } }

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let r: Response;
  try {
    r = await fetch(`${agentsOrigin()}${BASE}${path}`, {
      ...init, credentials: "include", cache: "no-store", headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new Error("The Monitoring agent is temporarily unavailable. Please try again in a moment.");
  }
  const body = await r.json().catch(() => null);
  if (!r.ok) throw new Error(friendlyError("The Monitoring agent", r.status, body));
  return body as T;
}

const post = <T,>(path: string, body: unknown) => call<T>(path, { method: "POST", body: JSON.stringify(body) });

const scopeBody = (s: MonitorScope) => (s.lensId ? { lens_id: s.lensId } : { book: s.book ?? "corporate", filters: s.filters ?? [] });

const SOURCE_WORD: Record<string, string> = { composition: "Composition", appetite: "Risk appetite", regulation: "Regulation", movement: "Movement", lens: "This lens" };
const STATUS_TONE: Record<string, "neutral" | "positive" | "negative" | "warning" | "accent"> = {
  proposed: "neutral", accepted: "positive", edited: "accent", rejected: "negative", active: "positive",
};

function when(v: string | number | null | undefined): string {
  if (v === null || v === undefined || v === "") return "";
  const d = typeof v === "number" ? new Date(v * 1000) : new Date(v);
  return Number.isNaN(d.getTime()) ? "" : d.toISOString().slice(0, 10);
}

/** The back-test as 8 marks (filled = the threshold would have fired that quarter) and "n of 8". */
function BacktestMarks({ bt }: { bt: Backtest }) {
  const fired = new Set(bt.fired_periods);
  return (
    <span className="inline-flex items-center gap-1.5" title={`Back-test: fired in ${bt.fired_periods.join(", ") || "no quarter"} of ${bt.evaluated_periods.join(", ")}`}>
      <span className="inline-flex gap-0.5" aria-hidden>
        {bt.evaluated_periods.map((p) => <span key={p} className={cn("h-2.5 w-1.5 rounded-sm", fired.has(p) ? "bg-warning" : "bg-border")} />)}
      </span>
      <span className="tabular-nums text-text-secondary">{bt.fired} of {bt.quarters}</span>
    </span>
  );
}

function thresholdFields(t: Threshold): (keyof Threshold)[] {
  return t.logic === "appetite" ? ["trigger", "limit"] : t.logic === "absolute" ? ["level"] : ["k"];
}
const FIELD_WORD: Record<string, string> = { k: "Threshold", level: "Level", trigger: "Trigger", limit: "Limit" };

function EditRow({ m, onSave, onCancel, busy }: { m: MonMetric; onSave: (t: Partial<Threshold>) => void; onCancel: () => void; busy: boolean }) {
  const fields = thresholdFields(m.threshold);
  const [vals, setVals] = React.useState<Record<string, string>>(Object.fromEntries(fields.map((f) => [f, String(m.threshold[f] ?? "")])));
  return (
    <div className="flex flex-wrap items-end gap-2 py-1" data-testid={`monitor-edit-${m.key}`}>
      {fields.map((f) => (
        <label key={f} className="flex flex-col text-[11px] text-text-muted">{FIELD_WORD[f]}
          <input type="number" step="any" value={vals[f]} onChange={(e) => setVals({ ...vals, [f]: e.target.value })}
                 className="h-8 w-24 rounded-md border border-border bg-surface px-2 text-[12px] tabular-nums text-text-primary" />
        </label>))}
      <SecondaryButton disabled={busy} onClick={() => onSave(Object.fromEntries(fields.map((f) => [f, Number(vals[f])])))} data-testid={`monitor-edit-save-${m.key}`}>
        {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />} Back-test and keep</SecondaryButton>
      <SecondaryButton onClick={onCancel}>Cancel</SecondaryButton>
    </div>
  );
}

function MetricsTable({ metrics, editable, onAct, busyKey, testId }: {
  metrics: MonMetric[]; editable: boolean; busyKey: string; testId: string;
  onAct?: (m: MonMetric, action: "accept" | "reject" | "edit", t?: Partial<Threshold>) => void;
}) {
  const [editing, setEditing] = React.useState("");
  return (
    <div className="overflow-x-auto">
      <table className={tableCls} data-testid={testId}>
        <thead><tr>
          <th className={cn(thCls, "w-8")}>#</th><th className={thCls}>Metric and why</th><th className={thCls}>Threshold</th>
          <th className={thCls}>Back-test</th><th className={cn(thCls, "text-right")}>Now</th>{editable ? <th className={thCls} /> : null}
        </tr></thead>
        <tbody>
          {metrics.map((m, i) => (
            <tr key={m.key} data-testid={`monitor-metric-${m.key}`} data-status={m.status} className={cn(m.status === "rejected" && "opacity-50")}>
              <td className={cn(tdCls, "align-top text-text-muted")}>{m.rank ?? i + 1}</td>
              <td className="max-w-[260px] border-b border-border/60 px-2 py-2 align-top">
                <p className="text-[12px] font-medium text-text-primary">{m.label}</p>
                <p className="mt-0.5 whitespace-normal text-[11px] leading-4 text-text-secondary">{m.why}</p>
                <span className="mt-1 flex flex-wrap gap-1">{m.sources.map((s) => <Chip key={s}>{SOURCE_WORD[s] ?? s}</Chip>)}
                  {m.status && m.status !== "proposed" ? <Chip tone={STATUS_TONE[m.status] ?? "neutral"}>{m.status}</Chip> : null}</span>
                {editing === m.key && onAct ? (
                  <EditRow m={m} busy={busyKey === m.key} onCancel={() => setEditing("")}
                           onSave={(t) => { onAct(m, "edit", t); setEditing(""); }} />) : null}
              </td>
              <td className="max-w-[200px] whitespace-normal border-b border-border/60 px-2 py-2 align-top text-[11px] text-text-secondary">{m.threshold_text}</td>
              <td className={cn(tdCls, "align-top")}><BacktestMarks bt={m.backtest} /></td>
              <td className={cn(tdCls, "text-right align-top font-medium", m.firing ? "text-negative" : "text-text-primary")}
                  title={m.now_period ? `As of ${m.now_period}${m.firing ? ": past its threshold" : ""}` : undefined}>{m.now_display}</td>
              {editable && onAct ? (
                <td className={cn(tdCls, "align-top")}>
                  <span className="inline-flex gap-1">
                    <button type="button" title="Accept" aria-label={`Accept ${m.label}`} onClick={() => onAct(m, "accept")} disabled={busyKey === m.key}
                            className="rounded p-1 text-positive hover:bg-surface-hover" data-testid={`monitor-accept-${m.key}`}><Check className="h-3.5 w-3.5" /></button>
                    <button type="button" title="Edit the threshold" aria-label={`Edit ${m.label}`} onClick={() => setEditing(editing === m.key ? "" : m.key)}
                            className="rounded p-1 text-accent hover:bg-surface-hover" data-testid={`monitor-editbtn-${m.key}`}><Pencil className="h-3.5 w-3.5" /></button>
                    <button type="button" title="Reject" aria-label={`Reject ${m.label}`} onClick={() => onAct(m, "reject")} disabled={busyKey === m.key}
                            className="rounded p-1 text-negative hover:bg-surface-hover" data-testid={`monitor-reject-${m.key}`}><X className="h-3.5 w-3.5" /></button>
                  </span>
                </td>) : null}
            </tr>))}
        </tbody>
      </table>
    </div>
  );
}

function Proposed({ panel, busy, onPlan, onAct, onDecide, busyKey }: {
  panel: Panel; busy: string; busyKey: string; onPlan: () => void;
  onAct: (p: Proposal, m: MonMetric, action: "accept" | "reject" | "edit", t?: Partial<Threshold>) => void;
  onDecide: (p: Proposal, d: "approve" | "reject") => void;
}) {
  const p = panel.pending[0];
  const [showDropped, setShowDropped] = React.useState(false);
  if (!p) {
    return (
      <div className="space-y-3 px-4 py-4" data-testid="monitor-proposed-empty">
        <p className="flex items-center gap-1 text-[13px] text-text-secondary">
          No monitors proposed yet.
          <InfoPopover title="Monitoring agent">The agent reads the scope&apos;s composition, the risk appetite, the CBUAE CRM checks, recent movement and materiality, back-tests a
          threshold for each candidate over 8 quarters and proposes a ranked set for a risk approver.</InfoPopover>
        </p>
        <PrimaryButton onClick={onPlan} disabled={!!busy} data-testid="monitor-plan">
          {busy === "plan" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Radar className="h-4 w-4" />}
          {panel.active ? "Plan again" : "Plan what to monitor"}</PrimaryButton>
        {panel.decided[0] ? <p className="text-[12px] text-text-muted">Last proposal {panel.decided[0].status}{panel.decided[0].decided_by ? ` by ${panel.decided[0].decided_by}` : ""}.</p> : null}
      </div>);
  }
  const ms = p.payload.metrics ?? [];
  const changes = p.payload.changes ?? [];
  const mine = p.maker === panel.me;
  return (
    <div className="space-y-3 px-4 py-3" data-testid="monitor-proposed">
      <div className="flex flex-wrap items-center gap-2">
        <Chip tone="warning">Pending approval</Chip>
        <span className="text-[12px] text-text-secondary">
          {p.kind === "monitoring_set" ? `${ms.length} metrics` : `${changes.length} changes`} · asked by {p.requested_by || "the scheduler"} ·
          needs a risk approver · expires {when(p.expires_at)}</span>
        <span className="ml-auto inline-flex gap-2">
          {panel.can_decide && !mine ? (
            <>
              <PrimaryButton onClick={() => onDecide(p, "approve")} disabled={!!busy} data-testid="monitor-approve">
                {busy === "approve" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />} Approve</PrimaryButton>
              <SecondaryButton onClick={() => onDecide(p, "reject")} disabled={!!busy} data-testid="monitor-reject">Reject</SecondaryButton>
            </>) : (
            <span className="text-[11px] text-text-muted" data-testid="monitor-approver-note">
              {mine ? "You asked for this plan: another risk approver decides it." : "A Head of Risk, Head of Credit or Risk Manager approves it."}</span>)}
        </span>
      </div>
      {p.kind === "monitoring_set" ? (
        <MetricsTable metrics={ms} editable onAct={(m, a, t) => onAct(p, m, a, t)} busyKey={busyKey} testId="monitor-proposed-table" />
      ) : (
        <ul className="space-y-1.5" data-testid="monitor-changes">
          {changes.map((c) => (
            <li key={c.key} className="text-[12px]"><Chip tone={c.action === "retire" ? "negative" : "accent"}>{c.action === "retire" ? "Retire" : "Re-threshold"}</Chip>{" "}
              <span className="font-medium text-text-primary">{c.label}</span>: <span className="text-text-secondary">{c.why}</span></li>))}
        </ul>)}
      {p.payload.dropped?.length ? (
        <div>
          <button type="button" onClick={() => setShowDropped(!showDropped)} className="text-[12px] text-accent hover:underline" data-testid="monitor-dropped-toggle">
            {showDropped ? "Hide" : "Show"} the {p.payload.dropped.length} candidates left out, and why</button>
          {showDropped ? (
            <ul className="mt-1 space-y-1" data-testid="monitor-dropped">
              {p.payload.dropped.map((d) => (
                <li key={d.key} className="text-[11px] text-text-secondary"><span className="font-medium text-text-primary">{d.label}</span>: {d.why}</li>))}
            </ul>) : null}
        </div>) : null}
      <SecondaryButton onClick={onPlan} disabled={!!busy} data-testid="monitor-replan"><RefreshCw className="h-3.5 w-3.5" /> Plan again</SecondaryButton>
    </div>
  );
}

function Active({ panel, busy, onRun, onReview, currentLens }: { panel: Panel; busy: string; onRun: () => void; onReview: () => void; currentLens?: string }) {
  const a = panel.active;
  if (!a) return <p className="px-4 py-4 text-[13px] text-text-secondary" data-testid="monitor-active-empty">No approved monitoring set yet. Plan one under Proposed.</p>;
  const latest = panel.alerts.length ? panel.alerts[0].period : "";
  const tiles: KpiTile[] = [
    { label: "Metrics", value: String(a.metrics.length), sub: `version ${a.version}${a.retired.length ? ` · ${a.retired.length} retired` : ""}` },
    { label: "Alerts", value: String(panel.alerts.filter((x) => x.period === latest).length), sub: latest ? `latest release ${latest}` : "none yet",
      tone: panel.alerts.some((x) => x.period === latest && x.severity === "high") ? "negative" : "neutral" },
    { label: "Schedule", value: a.schedule ? (a.schedule.text.split(",")[0] || "set") : "–", sub: a.schedule?.text.split(",").slice(1).join(",").trim() || "" },
    { label: "Approved by", value: a.approved_by || "–", sub: `asked by ${a.created_by}` },
  ];
  return (
    <div className="space-y-3 px-4 py-3" data-testid="monitor-active">
      <KpiRow tiles={tiles} />
      <div className="flex flex-wrap items-center gap-2">
        <PrimaryButton onClick={onRun} disabled={!!busy} data-testid="monitor-run">
          {busy === "run" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />} Run now</PrimaryButton>
        <SecondaryButton onClick={onReview} disabled={!!busy} data-testid="monitor-review">
          {busy === "review" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />} Review the set</SecondaryButton>
        {a.lens_id && a.lens_id !== currentLens ? (
          <Link href={`/lenses/${a.lens_id}`} className="ml-auto inline-flex items-center gap-1 text-[12px] text-accent hover:underline" data-testid="monitor-open-lens">
            Open the monitoring lens <ExternalLink className="h-3.5 w-3.5" /></Link>) : null}
      </div>
      <MetricsTable metrics={a.metrics} editable={false} busyKey="" testId="monitor-active-table" />
    </div>
  );
}

function Alerts({ panel, onOpenRun }: { panel: Panel; onOpenRun: (id: string) => void }) {
  if (!panel.alerts.length) return <p className="px-4 py-4 text-[13px] text-text-secondary" data-testid="monitor-alerts-empty">No alerts yet. Alerts appear after each run of the approved set.</p>;
  return (
    <ul className="divide-y divide-border" data-testid="monitor-alerts">
      {[...panel.alerts].sort((x, y) => y.period.localeCompare(x.period) || (x.severity === y.severity ? 0 : x.severity === "high" ? -1 : 1)).map((a) => (
        <li key={a.alert_id} className="px-4 py-3" data-testid={`monitor-alert-${a.metric_key}`}>
          <div className="flex flex-wrap items-center gap-2">
            <Chip tone={a.severity === "high" ? "negative" : "warning"}>{a.severity === "high" ? "High" : "Alert"}</Chip>
            {a.status !== "new" ? <Chip>{a.status}</Chip> : null}
            <span className="text-[13px] font-medium text-text-primary">{a.headline}</span>
            <span className="ml-auto text-[11px] text-text-muted">{a.period}</span>
          </div>
          {a.explanation.map((line, i) => <p key={i} className="mt-1 text-[12px] leading-5 text-text-secondary">{line}</p>)}
          {a.detail?.run_id ? (
            <button type="button" onClick={() => onOpenRun(String(a.detail.run_id))} className="mt-1 inline-flex items-center gap-1 text-[11px] text-accent hover:underline">
              Evidence: {(a.detail.evidence ?? []).join(", ") || "the run"} <ExternalLink className="h-3 w-3" /></button>) : null}
        </li>))}
    </ul>
  );
}

export function MonitoringPanel({ scope, onClose, initialTab, currentLens }: { scope: MonitorScope; onClose: () => void; initialTab?: Tab; currentLens?: string }) {
  const [panel, setPanel] = React.useState<Panel | null>(null);
  const [tab, setTab] = React.useState<Tab>(initialTab ?? "proposed");
  const [error, setError] = React.useState("");
  const [notice, setNotice] = React.useState("");
  const [busy, setBusy] = React.useState("");
  const [busyKey, setBusyKey] = React.useState("");
  const [runId, setRunId] = React.useState<string | null>(null);
  const picked = React.useRef(false);       // a tab the user chose is never overridden by the first load
  const q = scopeQuery(scope);

  const load = React.useCallback(async (pick = false) => {
    try {
      const p = await call<Panel>(`/monitoring?${q}`);
      setPanel(p);
      setError("");
      if (pick && !initialTab && !picked.current) setTab(p.pending.length ? "proposed" : p.alerts.length ? "alerts" : p.active ? "active" : "proposed");
    } catch (e) { setError(e instanceof Error ? e.message : "The panel could not load."); }
  }, [q, initialTab]);
  React.useEffect(() => { void Promise.resolve().then(() => load(true)); }, [load]);
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape" && !runId) onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, runId]);

  const go = async (what: "plan" | "run" | "review") => {
    setBusy(what);
    setNotice("");
    try {
      const r = await post<RunResult>(`/monitoring/${what}`, scopeBody(scope));
      setNotice(r.output?.headline ? `${r.output.headline}.` : `Run ${r.status}.`);
      await load();
      setTab(what === "run" ? "alerts" : "proposed");
      setRunId(r.run_id);
    } catch (e) { setNotice(e instanceof Error ? e.message : "The agent could not run."); }
    finally { setBusy(""); }
  };
  const act = async (p: Proposal, m: MonMetric, action: "accept" | "reject" | "edit", t?: Partial<Threshold>) => {
    setBusyKey(m.key);
    try { await post(`/proposals/${p.proposal_id}/metrics/${encodeURIComponent(m.key)}`, { action, threshold: t }); await load(); }
    catch (e) { setNotice(e instanceof Error ? e.message : "That change could not be saved."); }
    finally { setBusyKey(""); }
  };
  const decide = async (p: Proposal, d: "approve" | "reject") => {
    setBusy(d);
    try {
      await post(`/proposals/${p.proposal_id}/decision`, { decision: d });
      setNotice(d === "approve" ? "Approved: the monitoring lens and its schedule are in place." : "Rejected: nothing changed.");
      await load();
      if (d === "approve") setTab("active");
    } catch (e) { setNotice(e instanceof Error ? e.message : "The decision could not be recorded."); }
    finally { setBusy(""); }
  };

  const tabs: { key: Tab; label: string; n?: number }[] = [
    { key: "proposed", label: "Proposed", n: panel?.pending.length ? (panel.pending[0].payload.metrics?.length ?? panel.pending[0].payload.changes?.length) : undefined },
    { key: "active", label: "Active", n: panel?.active?.metrics.length },
    { key: "alerts", label: "Alerts", n: panel?.alerts.length || undefined },
  ];
  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/20" onClick={onClose} data-testid="monitor-panel">
      <aside role="dialog" aria-modal="true" aria-label="Monitoring agent" onClick={(e) => e.stopPropagation()}
             className="flex h-full w-full max-w-[760px] flex-col overflow-hidden border-l border-border bg-surface shadow-2xl">
        <header className="flex items-start gap-3 border-b border-border px-4 py-3">
          <Radar className="mt-0.5 h-5 w-5 shrink-0 text-accent" />
          <div className="min-w-0 flex-1">
            <p className="text-[11px] font-medium uppercase tracking-[0.08em] text-text-muted">Monitoring agent</p>
            <h2 className="truncate text-[15px] font-semibold text-text-primary" data-testid="monitor-scope">
              {panel ? (panel.scope.lens_name || panel.scope.label) : "Loading…"}</h2>
            {panel ? <p className="text-[12px] text-text-secondary">As of {panel.scope.period}</p> : null}
          </div>
          <button type="button" onClick={onClose} aria-label="Close" className="rounded p-1 text-text-muted hover:bg-surface-hover"><X className="h-4 w-4" /></button>
        </header>
        <nav className="flex gap-1 border-b border-border px-3" role="tablist">
          {tabs.map((t) => (
            <button key={t.key} type="button" role="tab" aria-selected={tab === t.key} onClick={() => { picked.current = true; setTab(t.key); }} data-testid={`monitor-tab-${t.key}`}
                    className={cn("-mb-px border-b-2 px-3 py-2 text-[12px] font-medium", tab === t.key ? "border-accent text-text-primary" : "border-transparent text-text-muted hover:text-text-primary")}>
              {t.label}{t.n ? <span className="ml-1 tabular-nums text-text-muted">{t.n}</span> : null}</button>))}
        </nav>
        {notice ? <p className="border-b border-border px-4 py-2 text-[12px] text-text-secondary" role="status" data-testid="monitor-notice">{notice}</p> : null}
        <div className="min-h-0 flex-1 overflow-y-auto">
          {error ? <p className="px-4 py-3 text-[13px] text-negative" role="alert">{error}</p> : null}
          {!panel && !error ? <p className="flex items-center gap-2 px-4 py-4 text-[12px] text-text-secondary"><Loader2 className="h-4 w-4 animate-spin" />Loading…</p> : null}
          {panel && tab === "proposed" ? <Proposed panel={panel} busy={busy} busyKey={busyKey} onPlan={() => void go("plan")} onAct={act} onDecide={decide} /> : null}
          {panel && tab === "active" ? <Active panel={panel} busy={busy} onRun={() => void go("run")} onReview={() => void go("review")} currentLens={currentLens} /> : null}
          {panel && tab === "alerts" ? <Alerts panel={panel} onOpenRun={setRunId} /> : null}
          {panel ? <div className="px-4 py-3"><AgentInbox agent={AGENT} scope={panel.scope.scope_key} title="Monitoring runs" limit={6} /></div> : null}
        </div>
      </aside>
      {runId ? <div onClick={(e) => e.stopPropagation()}><AgentRunDrawer runId={runId} onClose={() => setRunId(null)} /></div> : null}
    </div>
  );
}

/** The one entry in the lens header. A lens the agent built opens its set's own scope (the book or segment). */
export function MonitoringAgentButton({ scope, className, initialTab, currentLens }: { scope: MonitorScope; className?: string; initialTab?: Tab; currentLens?: string }) {
  const [open, setOpen] = React.useState(!!initialTab);
  return (
    <>
      <button type="button" className={className} onClick={() => setOpen(true)} data-testid="lens-monitoring-agent">
        <Radar size={13} /> Monitoring agent</button>
      {open ? <MonitoringPanel scope={scope} onClose={() => setOpen(false)} initialTab={initialTab} currentLens={currentLens} /> : null}
    </>
  );
}
