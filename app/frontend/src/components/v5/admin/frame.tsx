"use client";

/**
 * The Admin console frame (PLAN_R5 Session A): the page header (eyebrow, title, an (i) with the page's purpose and a
 * link to its Cockpit help), tabs, the content, the maker-checker queue for the page's kinds, and the Admin
 * assistant (a conversation thread on the shared layer) in a collapsible panel on the right.
 */

import * as React from "react";
import { Bot, ChevronRight, Send, X } from "lucide-react";

import { InfoPopover } from "@/components/ui/info-popover";
import { GovernanceTools } from "@/components/v5/intel/governance";
import { AnswerBlocks, AssistantTurn, ProcessTrace, ThreadShell, UserTurn } from "@/components/v5/thread";
import { cn } from "@/lib/utils";
import { type ConvoBlock, type ConvoEvent, type ConvoThreadView as ThreadView, convoClient } from "@/lib/v5/convo";
import { traceFromEvents } from "@/lib/v5/thread";
import { admin, convoBase, count, sar, type Change, type Kind, type Policy, type Preview, type Simulation, type Workflow } from "@/lib/v5/admin";
import { friendlyMessage } from "@/lib/v5/errors";

export interface Tab { key: string; label: string; badge?: number }

export function AdminFrame({ eyebrow = "Admin", title, info, tabs, tab, onTab, children, testId, seeds, actions }: {
  eyebrow?: string; title: string; info: React.ReactNode; tabs?: Tab[]; tab?: string; onTab?: (k: string) => void;
  children: React.ReactNode; testId: string; seeds: { label: string; send: string }[]; actions?: React.ReactNode;
}) {
  const [open, setOpen] = React.useState(false);
  return (
    <div className="flex gap-5" data-testid={testId}>
      <div className="min-w-0 flex-1 space-y-5">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-text-muted">{eyebrow}</p>
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-semibold text-text-primary">{title}</h1>
              <InfoPopover title={`About ${title}`}>{info}</InfoPopover>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {actions}
            <GovernanceTools origin="admin" menu="admin-tools" />
            {!open ? (
              <button type="button" onClick={() => setOpen(true)} data-testid="admin-assistant-open"
                      className="inline-flex items-center gap-1.5 rounded-md border border-border bg-surface px-3 py-1.5 text-[13px] text-text-primary hover:border-accent">
                <Bot size={14} /> Ask the Admin assistant
              </button>) : null}
          </div>
        </div>
        {tabs?.length ? (
          <div className="flex gap-1 border-b border-border" role="tablist">
            {tabs.map((t) => (
              <button key={t.key} type="button" role="tab" aria-selected={tab === t.key} onClick={() => onTab?.(t.key)} data-testid={`admin-tab-${t.key}`}
                      className={cn("-mb-px border-b-2 px-3 py-2 text-[13px] font-medium",
                        tab === t.key ? "border-accent text-text-primary" : "border-transparent text-text-muted hover:text-text-primary")}>
                {t.label}{t.badge ? <span className="ml-1.5 rounded-full bg-accent/15 px-1.5 text-[11px] text-accent">{t.badge}</span> : null}
              </button>))}
          </div>) : null}
        {children}
      </div>
      {open ? <AdminAssistant seeds={seeds} onClose={() => setOpen(false)} /> : null}
    </div>
  );
}

// ---------------------------------------------------------------- assistant
export function AdminAssistant({ seeds, onClose }: { seeds: { label: string; send: string }[]; onClose: () => void }) {
  const client = React.useMemo(() => convoClient(convoBase()), []);
  const [thread, setThread] = React.useState<string>("");
  const [draft, setDraft] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const start = async (q: string) => {
    const text = q.trim();
    if (!text) return;
    setBusy(true); setError("");
    try { const r = await client.create("admin", {}, text, text.slice(0, 80)); setThread(r.thread.thread_id); setDraft(""); }
    catch (e) { setError(friendlyMessage(e)); }
    finally { setBusy(false); }
  };
  return (
    <aside className="sticky top-4 flex h-[calc(100vh-7rem)] w-[420px] shrink-0 flex-col rounded-lg border border-border bg-surface" data-testid="admin-assistant">
      <div className="flex items-center justify-between border-b border-border px-4 py-2.5">
        <p className="flex items-center gap-1.5 text-[13px] font-semibold text-text-primary"><Bot size={14} /> Admin assistant</p>
        <div className="flex items-center gap-1">
          {thread ? <button type="button" onClick={() => setThread("")} data-testid="admin-assistant-new" className="rounded px-2 py-0.5 text-[12px] text-text-muted hover:text-text-primary">New</button> : null}
          <button type="button" onClick={onClose} aria-label="Close the assistant" data-testid="admin-assistant-close" className="rounded p-1 text-text-muted hover:text-text-primary"><X size={14} /></button>
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-3 py-3">
        {thread ? <AdminThread threadId={thread} /> : (
          <div className="flex h-full flex-col justify-end gap-3">
            <p className="text-[13px] text-text-secondary">Explains any Admin page and drafts configuration from your words. Drafts go through approval like any change.</p>
            <div className="flex flex-col gap-1.5">
              {seeds.map((s) => (
                <button key={s.label} type="button" disabled={busy} onClick={() => void start(s.send)} data-testid="admin-assistant-seed"
                        className="flex items-center justify-between rounded-md border border-border px-3 py-2 text-left text-[12px] text-text-primary hover:border-accent disabled:opacity-40">
                  {s.label}<ChevronRight size={13} className="text-text-muted" /></button>))}
            </div>
            <form className="flex items-end gap-2" onSubmit={(e) => { e.preventDefault(); void start(draft); }}>
              <textarea value={draft} onChange={(e) => setDraft(e.target.value)} rows={2} data-testid="admin-assistant-input"
                        placeholder="e.g. “Auditors read-only, names masked”"
                        onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void start(draft); } }}
                        className="min-h-[48px] flex-1 resize-none rounded-md border border-border bg-surface px-3 py-2 text-[13px] focus:border-accent focus:outline-none" />
              <button type="submit" disabled={busy || !draft.trim()} data-testid="admin-assistant-send"
                      className="inline-flex items-center gap-1 rounded-md bg-accent px-3 py-2 text-[13px] font-medium text-accent-contrast disabled:opacity-40"><Send size={13} /> Ask</button>
            </form>
            {error ? <p role="alert" className="text-[12px] text-negative">{error}</p> : null}
          </div>)}
      </div>
    </aside>
  );
}

/** The Admin assistant's thread on the shared shell (PLAN_R5 G4): turns in the middle, the process trace with its
 * timer on every answer, the composer pinned at the bottom with the follow-up chips. */
function AdminThread({ threadId }: { threadId: string }) {
  const client = React.useMemo(() => convoClient(convoBase()), []);
  const [view, setView] = React.useState<ThreadView | null>(null);
  const [live, setLive] = React.useState<{ runId: string; question: string; events: ConvoEvent[] } | null>(null);
  const [draft, setDraft] = React.useState("");
  const [error, setError] = React.useState("");
  const stop = React.useRef<(() => void) | null>(null);
  const load = React.useCallback(async () => {
    try { const v = await client.thread(threadId); setView(v); setError(""); return v; }
    catch (e) { setError(friendlyMessage(e)); return null; }
  }, [client, threadId]);
  const follow = React.useCallback((runId: string, question: string) => {
    stop.current?.();
    setLive({ runId, question, events: [] });
    stop.current = client.watch(runId, {
      onEvent: (e) => setLive((l) => (l && l.runId === runId ? { ...l, events: [...l.events, e] } : l)),
      onSettled: () => { void load().then(() => setLive(null)); },
    });
  }, [client, load]);
  React.useEffect(() => {
    void load().then((v) => { if (v?.active_run) follow(v.active_run, ""); });
    return () => stop.current?.();
  }, [load, follow]);
  const ask = async (q: string) => {
    const text = q.trim();
    if (!text || live) return;
    setDraft("");
    try { const r = await client.ask(threadId, text); follow(r.run_id, text); } catch (e) { setError(friendlyMessage(e)); }
  };
  if (!view) return error ? <p role="alert" className="text-[12px] text-negative">{error}</p> : <p className="text-[12px] text-text-muted">Opening…</p>;
  const lastTurn = view.turns[view.turns.length - 1];
  const chips = live ? [] : (lastTurn?.answer.suggestions ?? []).map((c) => ({ label: c.label, send: c.send }));
  return (
    <ThreadShell compact testId="admin-thread" scrollKey={`${view.turns.length}|${live?.events.length ?? 0}`}
                 notice={error ? <p role="alert" className="text-[12px] text-negative">{error}</p> : null}
                 composer={{ value: draft, onChange: setDraft, onSubmit: (v) => void ask(v), busy: !!live, chips, onChip: (c) => void ask(c.send),
                             placeholder: "Ask, or describe a policy or workflow", testId: "admin-thread", rows: 2 }}>
      {view.turns.map((t) => (
        <div key={t.run_id} className="space-y-2" data-testid="admin-turn">
          <UserTurn compact text={t.answer.question_display || t.question} />
          <AssistantTurn compact trace={t.answer.trace}>
            <AnswerBlocks compact blocks={t.answer.blocks} evidence={t.answer.evidence} onAsk={(q) => void ask(q)} renderBlock={(b, i) => <AdminBlock block={b} key={i} />} />
          </AssistantTurn>
        </div>))}
      {live ? (
        <div className="space-y-2" data-testid="admin-live-turn">
          {live.question ? <UserTurn compact text={live.question} /> : null}
          <ProcessTrace compact snapshot={traceFromEvents(live.events)} />
        </div>) : null}
    </ThreadShell>
  );
}

function AdminBlock({ block }: { block: ConvoBlock }) {
  if (block.type === "admin_draft") return <DraftCard block={block as unknown as { kind: "policy" | "workflow"; title: string; body: Policy | Workflow; simulation?: Simulation }} />;
  if (block.type === "admin_preview") {
    const p = (block as unknown as { preview: Preview }).preview;
    return (
      <div className="mt-2 rounded-md border border-border bg-surface-sunken p-3 text-[12px]" data-testid="admin-preview-block">
        <p className="font-medium text-text-primary">{p.user.name}</p>
        {p.books.map((b) => (
          <p key={b.book} className="text-text-secondary">{b.book === "corporate" ? "Corporate" : "Retail"}: {b.visible ? `${count(b.seen.customers)} of ${count(b.total.customers)} customers, ${sar(b.seen.ead_sar_mn)} of ${sar(b.total.ead_sar_mn)} EAD` : "not visible"}</p>))}
      </div>);
  }
  return null;
}

function DraftCard({ block }: { block: { kind: "policy" | "workflow"; title: string; body: Policy | Workflow; simulation?: Simulation } }) {
  const [state, setState] = React.useState<"" | "saving" | "saved" | "error">("");
  const [msg, setMsg] = React.useState("");
  const save = async (submit: boolean) => {
    setState("saving");
    try {
      const body = { ...block.body } as Record<string, unknown>;
      delete body.drafted_from;
      const ch = await admin.draft(block.kind as Kind, "create", body, `${block.kind === "policy" ? "New policy" : "New workflow"}: ${block.title}`, "", submit, "assistant");
      setState("saved"); setMsg(submit ? `Submitted for approval as ${ch.change_id}.` : `Saved as draft ${ch.change_id}. Submit it from the page when ready.`);
    } catch (e) { setState("error"); setMsg(friendlyMessage(e)); }
  };
  const wf = block.kind === "workflow" ? (block.body as Workflow) : null;
  return (
    <div className="mt-2 space-y-2 rounded-md border border-accent/40 bg-surface p-3" data-testid="admin-draft-card" data-kind={block.kind}>
      <p className="text-[10px] font-semibold uppercase tracking-wide text-accent">Draft {block.kind === "policy" ? "data access policy" : "workflow"}</p>
      <p className="text-[13px] font-semibold text-text-primary">{block.title}</p>
      {wf ? (
        <ol className="space-y-1 text-[12px] text-text-secondary">
          {wf.steps.map((s, i) => <li key={s.id}>{i + 1}. {s.name} · {s.sla_days} days{s.escalate_after_days ? ` · escalates after ${s.escalate_after_days}` : ""}</li>)}
        </ol>) : null}
      {state === "saved" || state === "error" ? <p className={cn("text-[12px]", state === "error" ? "text-negative" : "text-positive")} data-testid="admin-draft-msg">{msg}</p> : (
        <div className="flex gap-2">
          <button type="button" disabled={state === "saving"} onClick={() => void save(false)} data-testid="admin-draft-save"
                  className="rounded-md border border-border px-3 py-1 text-[12px] hover:border-accent disabled:opacity-40">Save as draft</button>
          <button type="button" disabled={state === "saving"} onClick={() => void save(true)} data-testid="admin-draft-submit"
                  className="rounded-md bg-accent px-3 py-1 text-[12px] font-medium text-accent-contrast disabled:opacity-40">Save and submit</button>
        </div>)}
    </div>
  );
}

// ---------------------------------------------------------------- maker-checker queue
const STATUS_STYLE: Record<string, string> = {
  draft: "bg-surface-sunken text-text-secondary", submitted: "bg-warning/15 text-warning", live: "bg-positive/15 text-positive",
  rejected: "bg-negative/15 text-negative", withdrawn: "bg-surface-sunken text-text-muted",
};
export function StatusPill({ status }: { status: string }) {
  const word = { draft: "Draft", submitted: "Waiting for approval", live: "Live", rejected: "Rejected", withdrawn: "Withdrawn", active: "Live", retired: "Retired" }[status] ?? status;
  return <span className={cn("rounded-full px-2 py-0.5 text-[11px] font-medium", STATUS_STYLE[status] ?? STATUS_STYLE.live)} data-testid="status-pill" data-status={status}>{word}</span>;
}

export function ChangeQueue({ changes, me, onDone, testId = "change-queue", title = "Changes in progress" }: {
  changes: Change[]; me: string; onDone: () => void; testId?: string; title?: string;
}) {
  const [busy, setBusy] = React.useState("");
  const [error, setError] = React.useState("");
  if (!changes.length) return null;
  const act = async (id: string, fn: () => Promise<unknown>) => {
    setBusy(id); setError("");
    try { await fn(); onDone(); } catch (e) { setError(friendlyMessage(e)); } finally { setBusy(""); }
  };
  return (
    <section className="rounded-lg border border-warning/40 bg-surface" data-testid={testId}>
      <div className="flex items-center justify-between border-b border-border px-4 py-2">
        <h2 className="text-[13px] font-semibold text-text-primary">{title} <span className="ml-1 text-text-muted">{changes.length}</span></h2>
        <InfoPopover title="Maker-checker">
          <p>Every change is drafted, submitted, then approved by a second person (an Admin or a CRO) before it goes live. The maker cannot approve their own change. Approving writes the next version; earlier versions are kept, and every step is in the Audit log.</p>
        </InfoPopover>
      </div>
      <ul className="divide-y divide-border">
        {changes.map((c) => (
          <li key={c.change_id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-2.5" data-testid="change-row" data-id={c.change_id} data-status={c.status}>
            <div className="min-w-0">
              <p className="truncate text-[13px] font-medium text-text-primary">{c.title}</p>
              <p className="text-[11px] text-text-muted">{c.change_id} · {c.kind_label} · by {c.maker}{c.source === "assistant" ? " (drafted with the assistant)" : ""}</p>
            </div>
            <div className="flex items-center gap-2">
              <StatusPill status={c.status} />
              {c.status === "draft" && c.maker === me ? <>
                <button type="button" disabled={!!busy} onClick={() => void act(c.change_id, () => admin.submit(c.change_id))} data-testid="change-submit" className="rounded-md bg-accent px-2.5 py-1 text-[12px] text-accent-contrast disabled:opacity-40">Submit</button>
                <button type="button" disabled={!!busy} onClick={() => void act(c.change_id, () => admin.withdraw(c.change_id))} data-testid="change-withdraw" className="rounded-md border border-border px-2.5 py-1 text-[12px] disabled:opacity-40">Withdraw</button></> : null}
              {c.status === "submitted" && c.maker !== me ? <>
                <button type="button" disabled={!!busy} onClick={() => void act(c.change_id, () => admin.approve(c.change_id))} data-testid="change-approve" className="rounded-md bg-positive px-2.5 py-1 text-[12px] text-white disabled:opacity-40">Approve</button>
                <button type="button" disabled={!!busy} onClick={() => void act(c.change_id, () => admin.reject(c.change_id, "Returned for rework"))} data-testid="change-reject" className="rounded-md border border-border px-2.5 py-1 text-[12px] disabled:opacity-40">Reject</button></> : null}
              {c.status === "submitted" && c.maker === me ? <>
                <span className="text-[11px] text-text-muted">Another approver must decide</span>
                <button type="button" disabled={!!busy} onClick={() => void act(c.change_id, () => admin.withdraw(c.change_id))} data-testid="change-withdraw" className="rounded-md border border-border px-2.5 py-1 text-[12px] disabled:opacity-40">Withdraw</button></> : null}
            </div>
          </li>))}
      </ul>
      {error ? <p role="alert" className="px-4 pb-2 text-[12px] text-negative" data-testid="change-error">{error}</p> : null}
    </section>
  );
}

export function useMe() {
  const [me, setMe] = React.useState<{ username: string; can_approve: boolean } | null>(null);
  React.useEffect(() => { void admin.overview().then((o) => setMe(o.me)).catch(() => setMe({ username: "", can_approve: false })); }, []);
  return me;
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <p className="rounded-md border border-dashed border-border px-4 py-6 text-center text-[13px] text-text-muted">{children}</p>;
}

export function Stat({ label, value, sub, testId }: { label: string; value: string; sub?: string; testId?: string }) {
  return (
    <div className="rounded-lg border border-border bg-surface px-4 py-3" data-testid={testId}>
      <p className="text-[10px] font-semibold uppercase tracking-wide text-text-muted">{label}</p>
      <p className="mt-1 text-xl font-semibold tabular-nums text-text-primary">{value}</p>
      {sub ? <p className="text-[11px] text-text-muted">{sub}</p> : null}
    </div>
  );
}

export function Chip({ children, tone = "neutral" }: { children: React.ReactNode; tone?: "neutral" | "accent" | "warn" | "bad" | "good" }) {
  const t = { neutral: "bg-surface-sunken text-text-secondary", accent: "bg-accent/10 text-accent", warn: "bg-warning/15 text-warning",
              bad: "bg-negative/10 text-negative", good: "bg-positive/10 text-positive" }[tone];
  return <span className={cn("inline-flex items-center rounded-full px-2 py-0.5 text-[11px]", t)}>{children}</span>;
}
