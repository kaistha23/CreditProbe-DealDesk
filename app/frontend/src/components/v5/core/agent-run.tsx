"use client";

/**
 * R11 agents, shared UI (PLAN_R11_AGENTS, Session G).
 *
 *   <AgentRunButton agent="dealdesk.committee" goal="Prepare DD-05 for committee" context={{ proposal_id: "DD-05" }} />
 *   <AgentRunDrawer runId={id} onClose={...} renderOutput={(run) => <MyPack run={run} />} />
 *   <AgentInbox agent="ews.triage" scope="corporate" />
 *
 * The drawer shows the goal; the plan as numbered steps that tick off live; findings with evidence chips
 * (each opens the step that produced it); the narrative with its citations; proposals with Approve and
 * Reject for the roles that may decide; and a link to the full Trace. Built on the Deal Desk kit, the
 * shared KpiRow and the theme tokens. Every figure on it comes from a tool step (A1).
 */

import * as React from "react";
import Link from "next/link";
import { Bot, Check, ChevronDown, ChevronRight, CircleDashed, ExternalLink, Loader2, MinusCircle, X, XCircle } from "lucide-react";

import { ANSWER_STYLE, answerInline, prepareAnswerText, splitHeadline } from "@/components/answer";
import { KpiRow, type KpiTile } from "@/components/v5/core/kpi-row";
import { useCoreAuth } from "@/components/v5/core/auth";
import { Chip, PrimaryButton, SecondaryButton } from "@/components/v5/dealdesk/kit";
import {
  type AgentApproval, type AgentFinding, type AgentRun, type AgentRunSummary, type AgentSchedule, type AgentStep,
  bySeverity, citationParts, decide, duration, evidenceStep, getRun, isFinished, listRuns, mayDecide,
  progress, severityCounts, severityTone, startRun, toolLabel, tracePath,
} from "@/lib/v5/agents";
import { cn } from "@/lib/utils";
import { PlainWords } from "@/components/v5/ui/plain-words";
import { PanelActions } from "@/components/v5/thread/panel-actions";
import type { ModuleKey } from "@/lib/v5/thread-actions";

/** R16 t (M7): the module an agent's answer belongs to (its Share, Trace, Word and Add to report). */
function agentModule(agent: string): ModuleKey {
  const a = agent.toLowerCase();
  return a.includes("ews") || a.includes("triage") || a.includes("warning") ? "ews" : a.includes("whatif") || a.includes("scenario") ? "whatif"
    : a.includes("deal") ? "dealdesk" : a.includes("lens") ? "lenses" : "agents";
}

import {
  type Subject, b360LinkFor, backWithRun, ewsDetailHref, findingSubject, originFor, planningState, sourceLegend, splitIds,
} from "./agent-finding-model";
import { edition } from "@/lib/navigation";

// ---------------------------------------------------------------- polling

export function useAgentRun(runId: string | null): { run: AgentRun | null; error: string; reload: () => void } {
  const [run, setRun] = React.useState<AgentRun | null>(null);
  const [error, setError] = React.useState("");
  const [nonce, setNonce] = React.useState(0);
  React.useEffect(() => {
    if (!runId) return;
    let live = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const tick = async () => {
      try {
        const r = await getRun(runId);
        if (!live) return;
        setRun(r);
        setError("");
        if (!isFinished(r.status)) timer = setTimeout(tick, 900);
      } catch (e) {
        if (!live) return;
        setError(e instanceof Error ? e.message : "The run could not be loaded.");
        timer = setTimeout(tick, 2500);
      }
    };
    void tick();
    return () => { live = false; if (timer) clearTimeout(timer); };
  }, [runId, nonce]);
  return { run, error, reload: () => setNonce((n) => n + 1) };
}

// ---------------------------------------------------------------- button

export function AgentRunButton({ agent, goal, context, label, planner, renderOutput, onRun, primary = true, testId, initialRunId, plainWords }: {
  agent: string; goal: string; context?: Record<string, unknown>; label?: string; planner?: "auto" | "model" | "deterministic";
  renderOutput?: (run: AgentRun) => React.ReactNode; onRun?: (runId: string) => void; primary?: boolean; testId?: string;
  /** R15 L6: a run to open at once (Back from Borrower 360 / Early Warning detail carries agent_run=<id>). */
  initialRunId?: string | null;
  /** R15 L4: the "In plain words" lines shown while the run plans (the run's own lines replace them when it ends). */
  plainWords?: string[];
}) {
  const [runId, setRunId] = React.useState<string | null>(initialRunId ?? null);
  React.useEffect(() => { if (initialRunId) setRunId(initialRunId); }, [initialRunId]);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const go = async () => {
    setBusy(true);
    setError("");
    try {
      const r = await startRun(agent, goal, context ?? {}, planner ?? "auto");
      setRunId(r.run_id);
      onRun?.(r.run_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "The agent could not start.");
    } finally {
      setBusy(false);
    }
  };
  const Btn = primary ? PrimaryButton : SecondaryButton;
  return (
    <>
      <Btn onClick={go} disabled={busy} data-testid={testId ?? "agent-run-button"} title={error || goal}>
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Bot className="h-4 w-4" />}
        {label ?? "Run agent"}
      </Btn>
      {error ? <span className="text-[12px] text-negative" role="alert">{error}</span> : null}
      {runId ? <AgentRunDrawer runId={runId} onClose={() => setRunId(null)} renderOutput={renderOutput} plainWords={plainWords} /> : null}
    </>
  );
}

// ---------------------------------------------------------------- drawer

function StepIcon({ s }: { s: AgentStep["status"] }) {
  const cls = "h-4 w-4 shrink-0";
  if (s === "done") return <Check className={cn(cls, "text-positive")} aria-label="done" />;
  if (s === "running") return <Loader2 className={cn(cls, "animate-spin text-accent")} aria-label="running" />;
  if (s === "skipped") return <MinusCircle className={cn(cls, "text-warning")} aria-label="skipped" />;
  if (s === "failed") return <XCircle className={cn(cls, "text-negative")} aria-label="failed" />;
  return <CircleDashed className={cn(cls, "text-text-muted")} aria-label="pending" />;
}

function Figures({ figures }: { figures: Record<string, number> }) {
  const keys = Object.keys(figures);
  if (!keys.length) return null;
  return (
    <dl className="mt-1 grid grid-cols-2 gap-x-3 gap-y-0.5 text-[11px]">
      {keys.slice(0, 12).map((k) => (
        <div key={k} className="flex min-w-0 justify-between gap-2">
          <dt className="truncate text-text-muted">{k.replace(/_/g, " ")}</dt>
          <dd className="tabular-nums text-text-secondary">{fmtFigure(k, figures[k])}</dd>
        </div>
      ))}
    </dl>
  );
}

/** A step figure for display: ratios as %, multiples as x, money in m, counts and years as integers. */
export function fmtFigure(key: string, v: number): string {
  if (typeof v !== "number" || !Number.isFinite(v)) return "–";
  const k = key.toLowerCase();
  if (k === "year" || k.endsWith("_year")) return String(Math.round(v));
  if (/(dscr|debt_ebitda|_cover|multiple|ratio$)/.test(k)) return `${v.toFixed(2)}x`;
  if (/(raroc|hurdle|rate|^p_|_p_|margin$|share|cagr|^p$|change_vs)/.test(k) && Math.abs(v) <= 5) return `${(v * 100).toFixed(1)}%`;
  if (/(bps)/.test(k)) return `${Math.round(v)} bps`;
  if (/(sva|ecl|rwa|amount|ead|revenue|ebitda|limits|exposure|el_)/.test(k)) return `${v.toLocaleString("en-GB", { maximumFractionDigits: 2 })}m`;
  if (Number.isInteger(v)) return v.toLocaleString("en-GB");
  return v.toLocaleString("en-GB", { maximumFractionDigits: 2 });
}

function StepRow({ step, index, open, onToggle }: { step: AgentStep; index: number; open: boolean; onToggle: () => void }) {
  return (
    <li id={`agent-step-${step.id}`} className={cn("rounded-md border border-transparent", open && "border-border bg-surface-hover/40")}
        data-testid={`agent-step-${step.id}`} data-status={step.status}>
      <button type="button" onClick={onToggle} className="flex w-full items-start gap-2 px-2 py-1.5 text-left">
        <span className="mt-0.5 w-6 shrink-0 text-[11px] tabular-nums text-text-muted">{index + 1}.</span>
        <StepIcon s={step.status} />
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-2">
            <span className="text-[12px] font-medium text-text-primary">{toolLabel(step.tool)}</span>
            {step.added_by ? <Chip tone="accent" title={step.added_by}>added</Chip> : null}
            <span className="ml-auto shrink-0 text-[11px] tabular-nums text-text-muted">{step.status === "done" || step.status === "failed" ? duration(step.duration_ms) : ""}</span>
          </span>
          <span className={cn("block truncate text-[12px]", step.status === "skipped" ? "text-warning" : "text-text-secondary")}>
            {step.summary || step.why}
          </span>
        </span>
        {open ? <ChevronDown className="mt-0.5 h-3.5 w-3.5 text-text-muted" /> : <ChevronRight className="mt-0.5 h-3.5 w-3.5 text-text-muted" />}
      </button>
      {open ? (
        <div className="px-10 pb-2 text-[12px] text-text-secondary">
          {step.why ? <p><span className="text-text-muted">Why: </span>{step.why}</p> : null}
          {step.added_by ? <p><span className="text-text-muted">Added by: </span>{step.added_by}</p> : null}
          {step.summary ? <p className="whitespace-normal">{step.summary}</p> : null}
          {step.error ? <p className="text-negative">{step.error}</p> : null}
          <Figures figures={step.figures ?? {}} />
          {step.trace_id ? <p className="mt-1 text-[11px] text-text-muted">Engine trace {step.trace_id}</p> : null}
        </div>
      ) : null}
    </li>
  );
}

/** R15 L6: what the drawer needs to open a customer from a finding or a name in the answer. */
interface LinkCtx { origin: string; back: string; domain?: unknown; period?: unknown; onLeave: () => void }

function IdLink({ id, lc }: { id: string; lc: LinkCtx }) {
  const s: Subject = { id, name: id, domain: /^RC/i.test(id) ? "retail" : "corporate", period: String(lc.period ?? "") };
  const href = b360LinkFor(s, lc.origin, lc.back) ?? ewsDetailHref(s, lc.origin, lc.back);
  return <Link href={href} onClick={lc.onLeave} className="font-medium text-accent hover:underline" data-testid="agent-answer-id"
               title={href.startsWith("/deal-desk") ? "Open the customer in Deal Desk" : href.startsWith("/borrower-360") ? "Open Borrower 360" : "Open the Early Warning detail"}>{id}</Link>;
}

/** One run of narrative text with its citation chips (each opens the step behind it). */
function Cited({ text, onCite, legend, lc }: { text: string; onCite: (sid: string) => void; legend?: (sid: string) => string; lc?: LinkCtx }) {
  return (
    <>
      {citationParts(text).map((p, i) => p.cite ? (
        <span key={i} className="mx-0.5 inline-flex gap-0.5 align-[1px]">
          {p.cite.map((c) => (
            <button key={c} type="button" onClick={() => onCite(c)} title={legend ? legend(c) : c}
                    className="rounded border border-accent/30 bg-accent-muted px-1 py-px text-[10px] font-medium leading-none text-accent">{c}</button>
          ))}
        </span>
      ) : lc ? (
        <React.Fragment key={i}>
          {splitIds(p.text ?? "").map((q, j) => q.id ? <IdLink key={j} id={q.id} lc={lc} />
            : <React.Fragment key={j}>{answerInline(prepareAnswerText(q.text ?? ""))}</React.Fragment>)}
        </React.Fragment>
      ) : <React.Fragment key={i}>{answerInline(prepareAnswerText(p.text ?? ""))}</React.Fragment>)}
    </>
  );
}

/** PLAN_R12 N2: the agent's answer in the shared answer style: the headline sentence first, then the rest in the body type
 *  (key figures, banker words); citations stay on every sentence. */
function Narrative({ text, onCite, legend, lc }: { text: string; onCite: (sid: string) => void; legend?: (sid: string) => string; lc?: LinkCtx }) {
  const { headline, rest } = splitHeadline(text);
  return (
    <div className={ANSWER_STYLE.body} data-testid="agent-narrative">
      {headline ? <p className={ANSWER_STYLE.headline} data-testid="answer-headline"><Cited text={headline} onCite={onCite} legend={legend} lc={lc} /></p> : null}
      {/* R15 L5: one sentence per line, not one long paragraph */}
      {(headline ? rest : text).trim() ? (headline ? rest : text).split(/(?<=\])\.\s+(?=[A-Z0-9])/).map((line, i, all) => (
        <p key={i} className="mb-1"><Cited text={i < all.length - 1 ? `${line}.` : line} onCite={onCite} legend={legend} lc={lc} /></p>
      )) : null}
      {legend ? <p className="mt-1 text-[11px] text-text-muted">S1, S2 … are the steps of the plan below: hover a chip to see which source it read, click it to open that step.</p> : null}
    </div>
  );
}

function Chips({ refs, onCite, legend }: { refs: string[]; onCite: (sid: string) => void; legend?: (sid: string) => string }) {
  const ids = Array.from(new Set(refs.map(evidenceStep)));
  return (
    <div className="flex shrink-0 flex-wrap gap-1">
      {ids.map((sid) => (
        <button key={sid} type="button" onClick={(e) => { e.stopPropagation(); onCite(sid); }} title={legend ? legend(sid) : `Open ${sid}`}
                className="rounded border border-border px-1.5 text-[10px] text-text-secondary hover:bg-surface-hover">{sid}</button>
      ))}
    </div>
  );
}

const fmtNum = (v: unknown, d = 1) => (typeof v === "number" && Number.isFinite(v) ? v.toLocaleString("en-GB", { maximumFractionDigits: d }) : "–");

/** R15 L6: the customer's early-warning indicators behind a finding (rules with weights, score trend, DPD, stage,
 *  rating, conduct and bureau), each part with the S-chip of the step that read it. */
function EwsDetail({ d, onCite, legend }: { d: Record<string, unknown>; onCite: (sid: string) => void; legend?: (sid: string) => string }) {
  const e = (d.ews ?? null) as null | {
    period?: string; rules?: { label: string; weight?: number | null }[]; score?: number; band?: string; change?: number | null;
    series?: { period: string; score: number | null }[]; dpd?: number | null; stage?: number | null; rating?: string | null;
    rating_previous?: string | null; covenant_breaches?: number | null; conduct?: Record<string, number>; bureau?: Record<string, unknown>;
    rules_step?: string; b360_step?: string; conduct_step?: string; bureau_step?: string;
  };
  const inds = (d.indicators ?? []) as { code: string; label: string; article: string; in_basis?: boolean }[];
  const S = (sid?: string) => sid ? <Chips refs={[sid]} onCite={onCite} legend={legend} /> : null;
  const fact = "flex flex-wrap items-baseline gap-x-2 gap-y-0.5";
  if (!e && !inds.length) {
    const keys = Object.entries(d).filter(([, v]) => typeof v === "number" || (typeof v === "string" && v.length < 60)).slice(0, 10);
    return keys.length ? (
      <dl className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[11px]">
        {keys.map(([k, v]) => <div key={k} className="flex justify-between gap-2"><dt className="text-text-muted">{k.replace(/_/g, " ")}</dt><dd className="tabular-nums text-text-secondary">{typeof v === "number" ? fmtFigure(k, v) : String(v)}</dd></div>)}
      </dl>
    ) : null;
  }
  return (
    <div className="space-y-1.5 text-[12px]" data-testid="agent-finding-ews">
      {e ? (
        <>
          <div className={fact}>
            <span className="text-text-muted">Early-warning score {e.period ? `(${e.period})` : ""}</span>
            <span className="font-medium tabular-nums text-text-primary">{fmtNum(e.score, 0)}{e.band ? ` · ${e.band}` : ""}</span>
            {typeof e.change === "number" ? <span className={cn("tabular-nums", e.change > 0 ? "text-negative" : "text-text-secondary")}>{e.change > 0 ? "+" : ""}{e.change} on the period</span> : null}
            {S(e.rules_step)}
          </div>
          {e.series?.length ? (
            <p className="text-[11px] tabular-nums text-text-secondary" data-testid="agent-finding-trend">
              Trend: {e.series.map((x) => `${x.period} ${x.score ?? "–"}`).join(" → ")}
            </p>
          ) : null}
          {e.rules?.length ? (
            <ul className="ml-4 list-disc text-[12px] text-text-secondary" data-testid="agent-finding-rules">
              {e.rules.map((r) => <li key={r.label}>{r.label}{r.weight != null ? <span className="text-text-muted"> · weight {r.weight}</span> : null}</li>)}
            </ul>
          ) : null}
          <div className={fact}>
            <span className="text-text-muted">Days past due</span><span className="tabular-nums text-text-primary">{fmtNum(e.dpd, 0)}</span>
            <span className="text-text-muted">Stage</span><span className="tabular-nums text-text-primary">{fmtNum(e.stage, 0)}</span>
            <span className="text-text-muted">Rating</span><span className="text-text-primary">{e.rating ?? "–"}{e.rating_previous && e.rating_previous !== e.rating ? ` (was ${e.rating_previous})` : ""}</span>
            {e.covenant_breaches ? <><span className="text-text-muted">Covenant breaches</span><span className="tabular-nums text-negative">{e.covenant_breaches}</span></> : null}
            {S(e.b360_step)}
          </div>
          {e.conduct && Object.keys(e.conduct).length ? (
            <div className={fact}>
              <span className="text-text-muted">Account conduct</span>
              {"returned_payments_q" in e.conduct ? <span>{e.conduct.returned_payments_q} returned payments</span> : null}
              {"inflow_trend_pct" in e.conduct ? <span>inflows {fmtNum(e.conduct.inflow_trend_pct)}%</span> : null}
              {"overdraft_utilisation_pct" in e.conduct ? <span>overdraft use {fmtNum(e.conduct.overdraft_utilisation_pct, 0)}%</span> : null}
              {S(e.conduct_step)}
            </div>
          ) : null}
          {e.bureau ? (
            <div className={fact}>
              <span className="text-text-muted">Bureau</span>
              <span>{e.bureau.external_default ? "defaulted at another lender" : "no default elsewhere"}</span>
              <span>external DPD {fmtNum(e.bureau.external_dpd_days, 0)}</span>
              <span>{fmtNum(e.bureau.enquiries_q, 0)} enquiries</span>
              {S(e.bureau_step)}
            </div>
          ) : null}
        </>
      ) : null}
      {inds.filter((i) => i.in_basis).length ? (
        <div>
          <p className="text-text-muted">CBUAE indicators behind the verdict</p>
          <ul className="ml-4 list-disc text-text-secondary">
            {inds.filter((i) => i.in_basis).map((i) => <li key={i.code}><span className="font-mono text-[10px] text-text-primary">{i.article}</span> {i.label}</li>)}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function FindingRow({ f, onCite, legend, lc }: { f: AgentFinding; onCite: (sid: string) => void; legend?: (sid: string) => string; lc?: LinkCtx }) {
  const subject = findingSubject(f, { domain: lc?.domain, period: lc?.period });
  const [open, setOpen] = React.useState(false);
  const ewsHref = subject && lc ? ewsDetailHref(subject, lc.origin, lc.back) : null;
  const b360 = subject && lc ? b360LinkFor(subject, lc.origin, lc.back) : null;
  return (
    <li className={cn("py-1.5", open && "bg-surface-hover/40")} data-testid="agent-finding" data-subject={subject?.id ?? ""}>
      <div className={cn("flex items-start gap-2", subject && "cursor-pointer")}
           onClick={subject ? () => setOpen(!open) : undefined} role={subject ? "button" : undefined} tabIndex={subject ? 0 : undefined}
           onKeyDown={subject ? (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setOpen(!open); } } : undefined}
           aria-expanded={subject ? open : undefined} data-testid={subject ? "agent-finding-toggle" : undefined}>
        {subject ? (open ? <ChevronDown className="mt-0.5 h-3.5 w-3.5 shrink-0 text-text-muted" /> : <ChevronRight className="mt-0.5 h-3.5 w-3.5 shrink-0 text-text-muted" />) : null}
        <Chip tone={severityTone(f.severity)}>{f.severity}</Chip>
        <div className="min-w-0 flex-1">
          <p className="text-[12px] font-medium text-text-primary">{f.title}</p>
          {f.detail ? <p className="text-[12px] text-text-secondary">{f.detail}</p> : null}
        </div>
        <Chips refs={f.evidence} onCite={onCite} legend={legend} />
      </div>
      {open && subject ? (
        <div className="ml-6 mt-2 space-y-2 rounded-md border border-border bg-surface p-2.5" data-testid="agent-finding-detail">
          <EwsDetail d={f.data} onCite={onCite} legend={legend} />
          <div className="flex flex-wrap gap-2">
            {ewsHref && edition() !== "dealdesk" ? <Link href={ewsHref} onClick={lc?.onLeave} data-testid="agent-finding-ews-link"
                             className="inline-flex h-8 items-center rounded-md border border-border px-3 text-[12px] font-medium text-text-primary hover:bg-surface-hover">Early Warning detail</Link> : null}
            {b360 ? <Link href={b360} onClick={lc?.onLeave} data-testid="agent-finding-b360-link"
                          className="inline-flex h-8 items-center rounded-md bg-accent px-3 text-[12px] font-medium text-white hover:opacity-90">{edition() === "dealdesk" ? "Customer in Deal Desk" : "Borrower 360"}</Link> : null}
          </div>
        </div>
      ) : null}
    </li>
  );
}

export function ProposalRow({ a, onDecided, compact = false }: { a: AgentApproval; onDecided: () => void; compact?: boolean }) {
  const { effective } = useCoreAuth();
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const can = mayDecide(effective?.role, a, effective?.username);
  const act = async (d: "approve" | "reject") => {
    setBusy(true);
    setError("");
    try { await decide(a.id, d); onDecided(); } catch (e) { setError(e instanceof Error ? e.message : "Not decided."); } finally { setBusy(false); }
  };
  if (compact) {
    const why = !can && a.status === "pending"
      ? (effective?.username && effective.username === a.maker ? "You started this run: another person decides (four eyes)."
        : `A ${a.approver_role.replace(/_/g, " ").toLowerCase()} decides.`) : "";
    return (
      <li className="list-none" data-testid="agent-proposal">
        {a.status === "pending" ? (
          <div className="flex flex-wrap items-center gap-1.5" title={why || undefined}>
            <PrimaryButton className="h-7 px-2.5 text-[11px]" disabled={busy || !can} onClick={() => act("approve")} data-testid="agent-approve">Approve</PrimaryButton>
            <SecondaryButton className="h-7 px-2.5 text-[11px]" disabled={busy || !can} onClick={() => act("reject")} data-testid="agent-reject">Reject</SecondaryButton>
          </div>
        ) : <Chip tone={a.status === "approved" ? "positive" : a.status === "rejected" ? "negative" : "neutral"}>{a.status}</Chip>}
        <p className="mt-0.5 text-[10px] text-text-muted">{why || `${a.approver_role.replace(/_/g, " ").toLowerCase()} · expires ${a.expires_at.slice(0, 10)}`}</p>
        {error ? <p className="mt-0.5 text-[10px] text-negative" role="alert">{error}</p> : null}
      </li>
    );
  }
  return (
    <li className="rounded-md border border-border p-2" data-testid="agent-proposal">
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <p className="text-[12px] font-medium text-text-primary">{a.title}</p>
          <p className="text-[11px] text-text-muted">Needs {a.approver_role.replace(/_/g, " ").toLowerCase()} approval · expires {a.expires_at.slice(0, 10)}</p>
        </div>
        <Chip tone={a.status === "approved" ? "positive" : a.status === "rejected" ? "negative" : a.status === "expired" ? "neutral" : "warning"}>{a.status}</Chip>
      </div>
      {a.status === "pending" ? (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <PrimaryButton className="h-8 px-3 text-[12px]" disabled={busy || !can} onClick={() => act("approve")} data-testid="agent-approve"
                         title={can ? "Approve this proposal" : undefined}>Approve</PrimaryButton>
          <SecondaryButton disabled={busy || !can} onClick={() => act("reject")} data-testid="agent-reject">Reject</SecondaryButton>
          {!can ? (
            <span className="text-[11px] text-text-muted" data-testid="agent-decide-why">
              {effective?.username && effective.username === a.maker ? "You started this run: another person decides (four eyes)."
                : `A ${a.approver_role.replace(/_/g, " ").toLowerCase()} decides.`}
            </span>
          ) : null}
        </div>
      ) : null}
      {a.applied?.note || a.applied?.error ? <p className="mt-1 text-[11px] text-text-muted">{a.applied.error ?? a.applied.note}</p> : null}
      {error ? <p className="mt-1 text-[11px] text-negative" role="alert">{error}</p> : null}
    </li>
  );
}

function Block({ title, children, testId }: { title: string; children: React.ReactNode; testId?: string }) {
  return (
    <section className="border-t border-border px-4 py-3" data-testid={testId}>
      <h3 className="mb-2 text-[11px] font-medium uppercase tracking-[0.08em] text-text-muted">{title}</h3>
      {children}
    </section>
  );
}

/** R15 L4: while the run plans: what it is doing and for how long; after 60 s without a step, why, and a way out. */
function Planning({ run, startedAt, onWritten, onClose }: { run: AgentRun | null; startedAt: number; onWritten: () => void; onClose: () => void }) {
  const [now, setNow] = React.useState(() => Date.now());
  React.useEffect(() => { const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t); }, []);
  const st = planningState(startedAt, now, Boolean(run?.plan?.steps?.length), isFinished(run?.status));
  return (
    <div className="space-y-2" data-testid="agent-planning">
      <p className="flex items-center gap-2 text-[12px] text-text-secondary">
        <Loader2 className="h-4 w-4 animate-spin" />
        {run?.status === "queued" || !run ? "Starting the agent" : "Choosing the steps"} · <span className="tabular-nums">{st.seconds} s</span>
      </p>
      <p className="text-[11px] text-text-muted">The written plan reads the warnings, the evidence for each borrower and the CBUAE indicators, then decides. If a language model is set up it may choose the steps first; a model that has not answered in 40 seconds is dropped.</p>
      {st.stalled ? (
        <div className="rounded-md border border-warning/40 bg-warning-muted/40 p-2.5 text-[12px]" role="status" data-testid="agent-planning-stalled">
          <p className="font-medium text-text-primary">Still planning after {st.seconds} seconds.</p>
          <p className="text-text-secondary">The model may not be available on this machine, or the agents service is busy. Run the written plan now (same rules, no model), or close this and work from the warned list.</p>
          <div className="mt-2 flex flex-wrap gap-2">
            <PrimaryButton className="h-8 px-3 text-[12px]" onClick={onWritten} data-testid="agent-run-written">Run the written plan now</PrimaryButton>
            <SecondaryButton onClick={onClose} data-testid="agent-planning-close">Show the warned list</SecondaryButton>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export function AgentRunDrawer({ runId: firstRunId, onClose, renderOutput, plainWords }: {
  runId: string; onClose: () => void; renderOutput?: (run: AgentRun) => React.ReactNode; plainWords?: string[];
}) {
  const [runId, setRunId] = React.useState(firstRunId);
  React.useEffect(() => setRunId(firstRunId), [firstRunId]);
  const [startedAt, setStartedAt] = React.useState(() => Date.now());
  const { run, error, reload } = useAgentRun(runId);
  const [open, setOpen] = React.useState<string | null>(null);
  const runWritten = async () => {
    if (!run) return;
    try {
      const r = await startRun(run.agent, run.goal, run.context ?? {}, "deterministic");
      setStartedAt(Date.now());
      setRunId(r.run_id);
    } catch { /* the stalled note stays; the list is behind the drawer */ }
  };
  const sources = (run?.output?.sources ?? null) as Record<string, string> | null;
  const legend = (sid: string) => sourceLegend(sid, sources, run?.plan?.steps.find((s) => s.id === sid)?.tool);
  const [here, setHere] = React.useState("");
  React.useEffect(() => { setHere(`${window.location.pathname}${window.location.search}`); }, [runId]);
  const lc: LinkCtx | undefined = run ? {
    origin: originFor(run.agent), back: backWithRun(here || "/", runId),
    domain: run.context?.domain, period: (run.output?.period as string | undefined) ?? run.context?.period, onLeave: onClose,
  } : undefined;
  const pw = ((run?.output?.plain_words as string[] | undefined) ?? plainWords ?? []).filter(Boolean);
  const cite = (sid: string) => {
    setOpen(sid);
    requestAnimationFrame(() => document.getElementById(`agent-step-${sid}`)?.scrollIntoView({ block: "center", behavior: "smooth" }));
  };
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  const pr = progress(run?.plan);
  const counts = severityCounts(run?.findings ?? []);
  const done = isFinished(run?.status);
  const tiles: KpiTile[] = run ? [
    { label: "Steps", value: `${pr.settled}/${pr.total}`, sub: !run.plan ? "choosing the steps" : run.plan.planner === "model" ? "Model plan" : "Written plan" },
    { label: "Findings", value: String(run.findings.length), sub: `${counts.critical} critical · ${counts.major} major`, tone: counts.critical ? "negative" : counts.major ? "warning" : "neutral" },
    { label: "Proposals", value: String(run.proposals.length), sub: "for a person to approve" },
    { label: "Time", value: done ? duration(run.duration_ms) : "running", sub: run.status },
  ] : [];
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/20" onClick={onClose} data-testid="agent-run-drawer">
      <aside role="dialog" aria-modal="true" aria-label="Agent run"
             className="flex h-full w-full max-w-[880px] flex-col overflow-hidden border-l border-border bg-surface shadow-2xl"
             onClick={(e) => e.stopPropagation()}>
        <header className="flex items-start gap-3 border-b border-border px-4 py-3">
          <Bot className="mt-0.5 h-5 w-5 shrink-0 text-accent" />
          <div className="min-w-0 flex-1">
            <p className="text-[11px] font-medium uppercase tracking-[0.08em] text-text-muted">Agent goal</p>
            <h2 className="text-[15px] font-semibold text-text-primary" data-testid="agent-goal">{run?.goal ?? "Starting…"}</h2>
            {run?.output?.headline ? <p className="mt-0.5 text-[13px] font-medium text-text-primary" data-testid="agent-headline">{String(run.output.headline)}</p> : null}
            {/* R16 t (M7): Share, Trace, Word and Add to report on the agent's answer */}
            {run && done ? (
              <div className="mt-1">
                <PanelActions module={agentModule(run.agent)} id={runId} title={run.goal} container='[data-testid="agent-run-drawer"] aside' testId="agent-actions"
                              sources={[{ kind: "run", label: `Agent run ${runId}`, method: run.agent },
                                        ...(run.plan?.steps ?? []).slice(0, 20).map((st) => ({ kind: "engine" as const, label: `${st.tool}: ${st.summary || st.why || st.id}`.slice(0, 200), method: st.tool }))]} />
              </div>) : null}
          </div>
          <button type="button" onClick={onClose} aria-label="Close" className="rounded p-1 text-text-muted hover:bg-surface-hover"><X className="h-4 w-4" /></button>
        </header>
        <div className="h-1 w-full bg-border/50"><div className="h-1 bg-accent transition-all" style={{ width: `${Math.round(pr.share * 100)}%` }} /></div>
        <div className="min-h-0 flex-1 overflow-y-auto">
          {error && !run ? <p className="px-4 py-3 text-[13px] text-negative" role="alert">{error}</p> : null}
          {pw.length ? <div className="px-4 pt-3"><PlainWords lines={pw.slice(0, 4)} testId="agent-plain-words" /></div> : null}
          {run ? <div className="px-4 py-3"><KpiRow tiles={tiles} /></div> : null}
          {run && !run.plan?.steps?.length && !done ? <div className="px-4 pb-3"><Planning run={run} startedAt={startedAt} onWritten={runWritten} onClose={onClose} /></div> : null}
          {run?.narrative ? <Block title="Answer" testId="agent-answer"><Narrative text={run.narrative} onCite={cite} legend={legend} lc={lc} /></Block> : null}
          {run && done && renderOutput ? renderOutput(run) : null}
          {run?.findings?.length ? (
            <Block title="Findings" testId="agent-findings">
              <p className="mb-1 text-[11px] text-text-muted">{edition() === "dealdesk" ? "Click a borrower to see its indicators, then open the customer in Deal Desk." : "Click a borrower to see its early-warning indicators, then open the Early Warning detail or Borrower 360."}</p>
              <ul className="divide-y divide-border">{bySeverity(run.findings).slice(0, 40).map((f, i) => <FindingRow key={`${runId}-${i}`} f={f} onCite={cite} legend={legend} lc={lc} />)}</ul>
            </Block>
          ) : null}
          {run?.approvals?.length ? (
            <Block title="Proposals" testId="agent-proposals">
              <ul className="space-y-2">{run.approvals.slice(0, 12).map((a) => <ProposalRow key={a.id} a={a} onDecided={reload} />)}</ul>
              {run.approvals.length > 12 ? <p className="mt-2 text-[11px] text-text-muted">{run.approvals.length - 12} more wait in the approvals queue (the table above has Approve and Reject on each row).</p> : null}
            </Block>
          ) : null}
          <Block title="Plan" testId="agent-plan">
            {run?.plan ? (
              <>
                <ol className="space-y-0.5">
                  {run.plan.steps.map((s, i) => <StepRow key={s.id} step={s} index={i} open={open === s.id} onToggle={() => setOpen(open === s.id ? null : s.id)} />)}
                </ol>
                {run.plan.notes.filter((n) => !n.startsWith("model:")).length ? (
                  <ul className="mt-2 space-y-0.5 text-[11px] text-text-muted">
                    {run.plan.notes.filter((n) => !n.startsWith("model:")).map((n, i) => <li key={i}>{n}</li>)}
                  </ul>
                ) : null}
              </>
            ) : done ? null : <p className="text-[12px] text-text-muted">The steps appear here as soon as the plan is chosen.</p>}
            {run?.stopped ? <p className="mt-2 text-[12px] text-warning" role="status">{run.stopped}</p> : null}
          </Block>
        </div>
        <footer className="flex items-center gap-2 border-t border-border px-4 py-2 text-[12px]">
          <span className="text-text-muted">{run ? `${run.run_id}` : ""}</span>
          <Link href={tracePath(runId)} className="ml-auto inline-flex items-center gap-1 text-accent hover:underline" data-testid="agent-trace-link">
            Full trace <ExternalLink className="h-3.5 w-3.5" />
          </Link>
        </footer>
      </aside>
    </div>
  );
}

// ---------------------------------------------------------------- inbox

export function AgentInbox({ agent, scope, title = "Agent runs", limit = 6, renderOutput, defaultOpen = false }: {
  agent: string; scope?: string; title?: string; limit?: number; renderOutput?: (run: AgentRun) => React.ReactNode; defaultOpen?: boolean;
}) {
  const [rows, setRows] = React.useState<AgentRunSummary[]>([]);
  const [schedules, setSchedules] = React.useState<AgentSchedule[]>([]);
  const [openRun, setOpenRun] = React.useState<string | null>(null);
  const [expanded, setExpanded] = React.useState(defaultOpen);
  const [error, setError] = React.useState("");
  React.useEffect(() => {
    let live = true;
    listRuns({ agent, scope, limit }).then((r) => { if (live) { setRows(r.runs); setSchedules(r.schedules); } })
      .catch((e) => { if (live) setError(e instanceof Error ? e.message : ""); });
    return () => { live = false; };
  }, [agent, scope, limit, openRun]);
  const latest = rows[0];
  return (
    <div className="rounded-lg border border-border bg-surface" data-testid="agent-inbox">
      <button type="button" onClick={() => setExpanded(!expanded)} className="flex w-full items-center gap-2 px-3 py-2 text-left">
        <Bot className="h-4 w-4 text-accent" />
        <span className="text-[12px] font-medium text-text-primary">{title}</span>
        <span className="truncate text-[12px] text-text-secondary">
          {error ? error : latest ? `Latest: ${latest.headline || latest.status} · ${latest.created_at.slice(0, 16).replace("T", " ")}` : "No runs yet"}
          {schedules.length ? ` · ${schedules.filter((s) => s.enabled).length} scheduled` : ""}
        </span>
        {expanded ? <ChevronDown className="ml-auto h-4 w-4 text-text-muted" /> : <ChevronRight className="ml-auto h-4 w-4 text-text-muted" />}
      </button>
      {expanded ? (
        <ul className="divide-y divide-border border-t border-border">
          {rows.map((r) => (
            <li key={r.run_id}>
              <button type="button" onClick={() => setOpenRun(r.run_id)} className="flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-surface-hover" data-testid="agent-inbox-row">
                <Chip tone={r.status === "completed" ? "positive" : r.status === "failed" ? "negative" : r.status === "partial" ? "warning" : "accent"}>{r.status}</Chip>
                <span className="min-w-0 flex-1 truncate text-[12px] text-text-primary">{r.headline || r.goal}</span>
                <span className="shrink-0 text-[11px] text-text-muted">{r.trigger === "scheduled" ? "scheduled · " : ""}{r.created_at.slice(5, 16).replace("T", " ")}</span>
              </button>
            </li>
          ))}
          {schedules.map((s) => (
            <li key={s.id} className="flex items-center gap-2 px-3 py-1.5 text-[12px] text-text-secondary">
              <Chip>{s.enabled ? "scheduled" : "paused"}</Chip>
              <span className="min-w-0 flex-1 truncate">{s.goal}</span>
              <span className="shrink-0 text-[11px] text-text-muted">{s.cron}</span>
            </li>
          ))}
          {!rows.length && !schedules.length ? <li className="px-3 py-2 text-[12px] text-text-muted">No runs yet</li> : null}
        </ul>
      ) : null}
      {openRun ? <AgentRunDrawer runId={openRun} onClose={() => setOpenRun(null)} renderOutput={renderOutput} /> : null}
    </div>
  );
}

