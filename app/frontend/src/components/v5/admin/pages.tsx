"use client";

/**
 * The Admin console pages (PLAN_R5 Session A): Workflow (A1), Users & Teams (A2), Agent Operations (A3),
 * AI Studio (A4), Settings (A5) and the Audit log (A6). Each page has one purpose, the Admin assistant on the right,
 * and an (i) pointing to its Cockpit help page (docs/product_knowledge/admin_*.md).
 */

import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { Download, KeyRound, Play, Power, Search, UserMinus, Users } from "lucide-react";

import { hbarFigure } from "@/components/answer/bar-figure";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Plot } from "@/components/v5/ews/plot";
import { cn } from "@/lib/utils";
import { MODULE_LABEL, ROLE_LABEL, admin, count, pct, secs, usd, useLoad, when, type AdminUser, type AiRun, type StudioConfig } from "@/lib/v5/admin";
import { MODEL_NAMES, modelDisplayName } from "@/lib/v5/model-names";

import { AccessTab } from "./access";
import { AdminFrame, ChangeQueue, Chip, Empty, Stat, StatusPill, useMe } from "./frame";
import { ItemsTab, WorkflowsTab } from "./workflows";
import { EwsPdCard } from "./ews-pd";
import { friendlyMessage } from "@/lib/v5/errors";
import { edition } from "@/lib/navigation";
import { IntelligenceStudioLink } from "@/components/v5/dealdesk/intelligence-studio"; // Round S

function useTab(def: string) {
  const router = useRouter();
  const params = useSearchParams();
  const tab = params.get("tab") ?? def;
  // The tab is in the address (replaced): Back from a page opened here returns to this tab.
  return [tab, (t: string) => router.replace(`?tab=${t}`, { scroll: false })] as const;
}
function useTick() {
  const [tick, setTick] = React.useState(0);
  return [tick, () => setTick((t) => t + 1)] as const;
}
const HELP = (page: string) => <p className="mt-2 text-[12px]">In the Cockpit, ask “What is {page}?” for the flow, links and a worked example.</p>;

// ================================================================ A1 Workflow
export function WorkflowPage() {
  const [tab, setTab] = useTab("access");
  const [tick, reload] = useTick();
  const me = useMe();
  const ov = useLoad(() => admin.overview(), `ov:${tick}`);
  const pendingPol = ov.data?.pending.filter((c) => c.kind === "policy").length ?? 0;
  const pendingWf = ov.data?.pending.filter((c) => c.kind === "workflow").length ?? 0;
  return (
    <AdminFrame title="Workflow" testId="admin-workflow" tab={tab} onTab={setTab}
                tabs={[{ key: "access", label: "Data access", badge: pendingPol }, { key: "workflows", label: "Approval workflows", badge: pendingWf },
                       { key: "items", label: "Live items", badge: ov.data?.items.length }]}
                info={<><p>Who sees what, and who approves what. Data access policies restrict each user to books, sectors, regions, branches, RM portfolios and segments, to modules and actions, and can mask obligor names. Every v5 service and every AI answer applies them.</p><p className="mt-2">{edition() === "dealdesk" ? "Approval workflows route Deal Desk proposals by DOA, Playbook sign-off and parameter changes, with SLAs, escalation and delegation." : "Approval workflows route Deal Desk proposals by DOA, Playbook sign-off, official What-If scenarios, Early Warning actions and parameter changes, with SLAs, escalation and delegation."}</p>{HELP("Workflow")}</>}
                seeds={[edition() === "dealdesk"
                          ? { label: "Large proposals: CRO approval in 5 days", send: "Create a workflow so proposals above SAR 100 m need the CRO's approval within 5 days, escalate to the Executive Credit Committee after 10" }
                          : { label: "Critical EWS names: RM action plan in 5 days", send: "Create a workflow so Critical Early Warning names need an RM action plan within 5 days, escalate to the Head of Credit after 10" },
                        { label: "Makkah desk: Makkah region only", send: "The Makkah desk should only see Makkah region borrowers and customers in both books" },
                        { label: "What can Nawaf see?", send: "What can nawaf.alotaibi see?" },
                        { label: "How does maker-checker work?", send: "How does maker-checker work in Admin?" }]}>
      {!me ? <Skeleton className="h-64 w-full" /> : tab === "workflows" ? <WorkflowsTab me={me.username} tick={tick} reload={reload} />
        : tab === "items" ? <ItemsTab tick={tick} /> : <AccessTab me={me.username} tick={tick} reload={reload} />}
    </AdminFrame>
  );
}

// ================================================================ A2 Users & Teams
export function UsersPage() {
  const [tab, setTab] = useTab("users");
  const [tick, reload] = useTick();
  const me = useMe();
  const data = useLoad(() => admin.users(), `users:${tick}`);
  const opts = useLoad(() => admin.options(), "u-opts");
  const [msg, setMsg] = React.useState("");
  const [err, setErr] = React.useState("");
  const [edit, setEdit] = React.useState<AdminUser | null>(null);
  const act = async (fn: () => Promise<{ message?: string } | unknown>, ok: string) => {
    setErr(""); setMsg("");
    try { const r = await fn() as { message?: string }; setMsg(r?.message ?? ok); reload(); } catch (e) { setErr(friendlyMessage(e)); }
  };
  const teamName = Object.fromEntries((data.data?.teams ?? []).map((t) => [t.id, t.name]));
  return (
    <AdminFrame title="Users and Teams" testId="admin-users" tab={tab} onTab={setTab}
                tabs={[{ key: "users", label: "Users" }, { key: "teams", label: "Teams" }, { key: "roles", label: "Roles" }, { key: "rms", label: "RM hierarchy" }]}
                info={<><p>The people who use CreditProbe: their role, team, RM portfolio, the access policies that apply to them and their last activity. Changes to a user (role, team, deactivation, a new user) go through approval; a password reset is local and immediate.</p>{HELP("Users and Teams")}</>}
                seeds={[{ label: "What can the auditor see?", send: "What can hind.alsubaie see?" }, { label: "Explain the roles", send: "What are the roles in Users and Teams?" }]}>
      {msg ? <p className="text-[12px] text-positive" data-testid="users-msg">{msg}</p> : null}
      {err ? <p role="alert" className="text-[12px] text-negative" data-testid="users-error">{err}</p> : null}
      {!data.data || !me ? <Skeleton className="h-64 w-full" /> : <>
        <ChangeQueue changes={data.data.changes} me={me.username} onDone={reload} testId="user-changes" />
        {edit ? (
          <Card className="space-y-3 border-accent/50 p-4" data-testid="user-editor">
            <p className="text-[14px] font-semibold text-text-primary">{edit.username ? `Change ${edit.name}` : "Invite a user"}</p>
            <div className="grid gap-2 md:grid-cols-3">
              {!data.data.users.some((u) => u.username === edit.username) || !edit.username ? <>
                <input placeholder="username (first.last)" value={edit.username} onChange={(e) => setEdit({ ...edit, username: e.target.value.toLowerCase() })} data-testid="user-new-username" className="rounded-md border border-border bg-surface px-2 py-1 text-[13px]" />
                <input placeholder="Full name" value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} data-testid="user-new-name" className="rounded-md border border-border bg-surface px-2 py-1 text-[13px]" /></> : null}
              <select value={edit.role} onChange={(e) => setEdit({ ...edit, role: e.target.value })} data-testid="user-role" className="rounded-md border border-border bg-surface px-2 py-1 text-[13px]">
                {data.data.roles.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}</select>
              <select value={edit.team} onChange={(e) => setEdit({ ...edit, team: e.target.value })} data-testid="user-team" className="rounded-md border border-border bg-surface px-2 py-1 text-[13px]">
                {data.data.teams.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</select>
              {edit.role === "rm" ? <select value={edit.rm_id} onChange={(e) => setEdit({ ...edit, rm_id: e.target.value })} className="rounded-md border border-border bg-surface px-2 py-1 text-[13px]">
                <option value="">RM ID…</option>{(opts.data?.rms ?? []).map((r) => <option key={r.rm_id} value={r.rm_id}>{r.rm_id} {r.rm_name}</option>)}</select> : null}
            </div>
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setEdit(null)} className="rounded-md border border-border px-3 py-1 text-[12px]">Cancel</button>
              <button type="button" data-testid="user-save" onClick={() => {
                const exists = data.data!.users.some((u) => u.username === edit.username);
                const body = { ...edit, status: exists ? edit.status : "invited" } as Record<string, unknown>;
                delete body.policies; delete body.version; delete body.in_core;
                void act(() => admin.draft("user", exists ? "update" : "create", body, `${exists ? "Change user" : "Invite"}: ${edit.name}`, edit.username, true), "Submitted for approval.");
                setEdit(null);
              }} className="rounded-md bg-accent px-3 py-1 text-[12px] font-medium text-accent-contrast">Submit for approval</button>
            </div>
          </Card>) : null}
        {tab === "users" ? (
          <section className="space-y-2">
            <div className="flex justify-end"><button type="button" data-testid="user-invite" onClick={() => setEdit({ username: "", name: "", title: "", department: "", core_team: "", books: ["corporate"], role: "analyst", team: "T-CORP",
              rm_id: "", branch_id: "", status: "invited", last_activity: "", delegate: "", version: 0, policies: [], in_core: false })}
                    className="inline-flex items-center gap-1 rounded-md bg-accent px-3 py-1.5 text-[12px] font-medium text-accent-contrast"><Users size={13} /> Invite a user</button></div>
            <div className="overflow-x-auto rounded-md border border-border bg-surface">
              <table className="w-full text-[13px]" data-testid="users-table">
                <thead className="bg-surface-sunken text-left text-[10px] uppercase tracking-wide text-text-muted">
                  <tr><th className="px-3 py-2">User</th><th className="px-3 py-2">Role</th><th className="px-3 py-2">Team</th><th className="px-3 py-2">Access policies</th><th className="px-3 py-2">Last activity</th><th className="px-3 py-2">Status</th><th className="px-3 py-2" /></tr>
                </thead>
                <tbody>{data.data.users.map((u) => (
                  <tr key={u.username} className="border-t border-border" data-testid="user-row" data-user={u.username}>
                    <td className="px-3 py-2"><p className="font-medium text-text-primary">{u.name}</p><p className="text-[11px] text-text-muted">{u.username} · {u.title}{u.rm_id ? ` · ${u.rm_id}` : ""}</p></td>
                    <td className="px-3 py-2">{ROLE_LABEL[u.role] ?? u.role}</td><td className="px-3 py-2 text-text-secondary">{teamName[u.team] ?? u.team}</td>
                    <td className="px-3 py-2">{u.policies.length ? u.policies.map((p) => <Chip key={p.id} tone="accent">{p.name}</Chip>) : <span className="text-[12px] text-text-muted">{u.role === "admin" ? "Unrestricted" : "Profile books"}</span>}</td>
                    <td className="px-3 py-2 text-[12px] tabular-nums text-text-secondary">{when(u.last_activity)}</td>
                    <td className="px-3 py-2"><StatusPill status={u.status === "active" ? "live" : u.status} /></td>
                    <td className="px-3 py-2"><div className="flex justify-end gap-1">
                      <button type="button" title="Change role or team" onClick={() => setEdit(u)} data-testid="user-edit" className="rounded border border-border px-2 py-0.5 text-[11px] hover:border-accent">Change</button>
                      <button type="button" title="Reset password" aria-label={`Reset ${u.name}'s password`} onClick={() => void act(() => admin.resetPassword(u.username), "Password reset.")} data-testid="user-reset" className="rounded border border-border p-1 hover:border-accent"><KeyRound size={12} /></button>
                      {u.status === "active" && u.role !== "admin" ? <button type="button" title="Deactivate" aria-label={`Deactivate ${u.name}`} data-testid="user-deactivate"
                        onClick={() => { const b = { ...u, status: "deactivated" } as Record<string, unknown>; delete b.policies; delete b.version; delete b.in_core;
                          void act(() => admin.draft("user", "update", b, `Deactivate ${u.name}`, u.username, true), "Deactivation submitted for approval."); }}
                        className="rounded border border-border p-1 hover:border-negative"><UserMinus size={12} /></button> : null}
                    </div></td>
                  </tr>))}</tbody>
              </table>
            </div>
          </section>) : null}
        {tab === "teams" ? (
          <div className="grid gap-3 md:grid-cols-2" data-testid="teams-grid">
            {data.data.teams.map((t) => {
              const members = data.data!.users.filter((u) => u.team === t.id);
              return (
                <Card key={t.id} className="space-y-1.5 p-4" data-testid="team-card">
                  <p className="text-[14px] font-semibold text-text-primary">{t.name}</p>
                  <p className="text-[12px] text-text-secondary">{t.description}</p>
                  <p className="text-[12px] text-text-muted">Lead: {data.data!.users.find((u) => u.username === t.lead)?.name ?? t.lead} · {members.length} members</p>
                  <div className="flex flex-wrap gap-1">{members.map((m) => <Chip key={m.username}>{m.name}</Chip>)}</div>
                </Card>);
            })}
          </div>) : null}
        {tab === "roles" ? (
          <div className="grid gap-3 md:grid-cols-3" data-testid="roles-grid">
            {data.data.roles.map((r) => (
              <Card key={r.id} className="space-y-1.5 p-4" data-testid="role-card">
                <p className="text-[14px] font-semibold text-text-primary">{r.name}</p>
                <p className="text-[12px] text-text-secondary">{r.description}</p>
                <p className="text-[11px] text-text-muted">{r.modules.includes("*") ? "All modules" : r.modules.map((m) => MODULE_LABEL[m] ?? m).join(", ")}</p>
                <p className="text-[11px] text-text-muted">{data.data!.users.filter((u) => u.role === r.id).length} users</p>
              </Card>))}
          </div>) : null}
        {tab === "rms" ? <RmTree rms={opts.data?.rms ?? []} users={data.data.users} /> : null}
      </>}
    </AdminFrame>
  );
}

function RmTree({ rms, users }: { rms: { rm_id: string; rm_name: string; branch_id: string; branch_name: string }[]; users: AdminUser[] }) {
  const byBranch: Record<string, typeof rms> = {};
  for (const r of rms) (byBranch[`${r.branch_id} ${r.branch_name}`] ??= []).push(r);
  const signin = Object.fromEntries(users.filter((u) => u.rm_id).map((u) => [u.rm_id, u]));
  return (
    <div className="space-y-2" data-testid="rm-tree">
      <p className="text-[12px] text-text-muted">{count(rms.length)} relationship managers across {count(Object.keys(byBranch).length)} branches (Branches and RMs domain). RMs with a CreditProbe sign-in are highlighted.</p>
      <div className="grid gap-3 md:grid-cols-3">
        {Object.entries(byBranch).sort().map(([b, list]) => (
          <Card key={b} className="p-3" data-testid="rm-branch">
            <p className="text-[13px] font-semibold text-text-primary">{b}</p>
            <ul className="mt-1 space-y-0.5 text-[12px]">{list.map((r) => <li key={r.rm_id} className={cn(signin[r.rm_id] ? "font-medium text-accent" : "text-text-secondary")}>{r.rm_id} {r.rm_name}{signin[r.rm_id] ? " · signs in" : ""}</li>)}</ul>
          </Card>))}
      </div>
    </div>
  );
}

// ================================================================ A3 Agent Operations
export function AgentOpsPage() {
  const [tab, setTab] = useTab("runs");
  const [tick, reload] = useTick();
  const [f, setF] = React.useState<{ module: string; outcome: string; user: string; q: string }>({ module: "", outcome: "", user: "", q: "" });
  const runs = useLoad(() => admin.runs(f), `runs:${JSON.stringify(f)}:${tick}`);
  const daily = useLoad(() => admin.daily(f.module), `daily:${f.module}:${tick}`);
  const [open, setOpen] = React.useState<AiRun | null>(null);
  const all = runs.data?.runs ?? [];
  const lat = all.map((r) => r.latency_ms).sort((a, b) => a - b);
  const q = (p: number) => (lat.length ? lat[Math.min(lat.length - 1, Math.round(p * (lat.length - 1)))] : 0);
  return (
    <AdminFrame title="Agent Operations" testId="admin-agentops" tab={tab} onTab={setTab}
                tabs={[{ key: "runs", label: "Live log" }, { key: "queue", label: "Failures and refusals" }, { key: "charts", label: "Daily" },
                       { key: "evals", label: "Evaluations" }, { key: "switches", label: "Kill switches" }]}
                info={<><p>Every AI run in every module: who asked what, the process steps with their timings, the tools called, tokens, cost, latency, the outcome and the figures the validator checked or removed. Drill into a run for its full trace, run each module&apos;s evaluation suite on demand, and switch a module&apos;s assistant to planner mode with its kill switch.</p>{HELP("Agent Operations")}</>}
                seeds={[{ label: "What is Agent Operations?", send: "What is Agent Operations?" }, { label: "How does the kill switch work?", send: "How does the kill switch work in Agent Operations?" }]}>
      <div className="grid gap-3 md:grid-cols-5" data-testid="agentops-kpis">
        <Stat label="Runs" value={count(runs.data?.total)} sub={f.module ? MODULE_LABEL[f.module] : "All modules"} testId="kpi-runs" />
        <Stat label="Latency p50" value={secs(q(0.5))} /><Stat label="Latency p95" value={secs(q(0.95))} />
        <Stat label="Cost" value={usd(all.reduce((s, r) => s + (r.cost_usd || 0), 0))} />
        <Stat label="Refusal rate" value={pct(all.length ? all.filter((r) => r.outcome === "refused").length / all.length : 0)} />
      </div>
      <IntelligenceStudioLink testId="agentops-intelligence-studio-link" /> {/* Round S */}
      {(tab === "runs" || tab === "queue") ? (
        <section className="space-y-2">
          <div className="flex flex-wrap items-center gap-2" data-testid="agentops-filters">
            <select value={f.module} onChange={(e) => setF({ ...f, module: e.target.value })} data-testid="agentops-module" className="rounded-md border border-border bg-surface px-2 py-1 text-[12px]">
              <option value="">All modules</option>{(runs.data?.modules ?? []).map((m) => <option key={m} value={m}>{MODULE_LABEL[m] ?? m}</option>)}</select>
            <select value={f.user} onChange={(e) => setF({ ...f, user: e.target.value })} data-testid="agentops-user" className="rounded-md border border-border bg-surface px-2 py-1 text-[12px]">
              <option value="">All users</option>{(runs.data?.users ?? []).map((u) => <option key={u} value={u}>{u}</option>)}</select>
            {tab === "runs" ? <select value={f.outcome} onChange={(e) => setF({ ...f, outcome: e.target.value })} data-testid="agentops-outcome" className="rounded-md border border-border bg-surface px-2 py-1 text-[12px]">
              <option value="">Every outcome</option><option value="completed">Completed</option><option value="refused">Refused</option><option value="failed">Failed</option></select> : null}
            <label className="flex items-center gap-1 rounded-md border border-border bg-surface px-2 py-1 text-[12px]"><Search size={12} />
              <input value={f.q} onChange={(e) => setF({ ...f, q: e.target.value })} placeholder="Search questions" data-testid="agentops-search" className="w-48 bg-transparent outline-none" /></label>
          </div>
          {!runs.data ? <Skeleton className="h-64 w-full" /> : (
            <div className="overflow-x-auto rounded-md border border-border bg-surface">
              <table className="w-full text-[12px]" data-testid="agentops-runs">
                <thead className="bg-surface-sunken text-left text-[10px] uppercase tracking-wide text-text-muted">
                  <tr><th className="px-3 py-2">When</th><th className="px-3 py-2">Module</th><th className="px-3 py-2">User</th><th className="px-3 py-2">Question</th>
                    <th className="px-3 py-2 text-right">Latency</th><th className="px-3 py-2 text-right">Tokens</th><th className="px-3 py-2 text-right">Cost</th><th className="px-3 py-2">Outcome</th></tr>
                </thead>
                <tbody>{all.filter((r) => tab === "runs" || r.outcome !== "completed").map((r) => (
                  <tr key={r.run_id} onClick={() => setOpen(r)} className="cursor-pointer border-t border-border hover:bg-surface-hover" data-testid="agentops-run" data-id={r.run_id}>
                    <td className="px-3 py-2 tabular-nums text-text-secondary">{when(r.at)}</td><td className="px-3 py-2">{MODULE_LABEL[r.module] ?? r.module}</td>
                    <td className="px-3 py-2">{r.user}</td><td className="max-w-[360px] truncate px-3 py-2 text-text-primary">{r.question}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{secs(r.latency_ms)}</td><td className="px-3 py-2 text-right tabular-nums">{count((r.tokens_in || 0) + (r.tokens_out || 0))}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{usd(r.cost_usd)}</td>
                    <td className="px-3 py-2"><Chip tone={r.outcome === "completed" ? "good" : r.outcome === "refused" ? "warn" : "bad"}>{r.outcome}</Chip></td></tr>))}</tbody>
              </table>
              {tab === "queue" && !all.some((r) => r.outcome !== "completed") ? <Empty>No failure or refusal.</Empty> : null}
            </div>)}
          {open ? <RunTrace run={open} onClose={() => setOpen(null)} /> : null}
        </section>) : null}
      {tab === "charts" ? <DailyCharts daily={daily.data} /> : null}
      {tab === "evals" ? <Evals tick={tick} reload={reload} /> : null}
      {tab === "switches" ? <Switches tick={tick} reload={reload} /> : null}
    </AdminFrame>
  );
}

function RunTrace({ run, onClose }: { run: AiRun; onClose: () => void }) {
  const total = Math.max(1, run.steps.reduce((s, x) => Math.max(s, x.at_ms + x.ms), 0));
  // A gantt of the stages: each bar starts where the stage started and is as long as it took.
  const gantt = hbarFigure({ labels: run.steps.map((s) => s.stage.charAt(0).toUpperCase() + s.stage.slice(1)),
                             values: run.steps.map((s) => s.ms / 1000), base: run.steps.map((s) => s.at_ms / 1000),
                             text: run.steps.map((s) => secs(s.ms)), color: "var(--ipm-accent)", xTitle: "Seconds from the start of the run" });
  return (
    <Card className="space-y-3 border-accent/50 p-4" data-testid="agentops-trace" data-id={run.run_id}>
      <div className="flex items-start justify-between gap-2">
        <div><p className="text-[11px] text-text-muted">{run.run_id} · {when(run.at)} · {MODULE_LABEL[run.module] ?? run.module} · {run.user} · {modelDisplayName(run.model)}</p>
          <p className="text-[14px] font-semibold text-text-primary">{run.question}</p></div>
        <button type="button" onClick={onClose} data-testid="agentops-trace-close" className="text-[12px] text-text-muted hover:text-text-primary">Close</button>
      </div>
      <Plot data={gantt.data} layout={{ ...gantt.layout, xaxis: { ...(gantt.layout.xaxis as object), range: [0, (total / 1000) * 1.08], ticksuffix: "s" } }}
            height={gantt.height} ariaLabel="Time spent in each stage of the run" filename={`agentops-${run.run_id}-stages`} testId="agentops-gantt" />
      {/* The same timings as text, one row per stage (screen readers, and the sweep's step count). */}
      <ul className="sr-only">
        {run.steps.map((s) => <li key={s.stage} data-testid="agentops-step">{s.stage}: {secs(s.ms)}, from {secs(s.at_ms)}</li>)}
      </ul>
      <div className="flex flex-wrap gap-1">{run.tools.map((t, i) => <Chip key={i} tone="accent">{t}</Chip>)}</div>
      <p className="text-[12px] text-text-secondary">Outcome: {run.outcome}{run.refusal_reason ? `: ${run.refusal_reason}` : ""} · tokens {count(run.tokens_in)} in, {count(run.tokens_out)} out · {usd(run.cost_usd)} · figures validated {count(run.figures_validated)}, removed {count(run.figures_removed)}</p>
    </Card>
  );
}

function DailyCharts({ daily }: { daily: Awaited<ReturnType<typeof admin.daily>> | null }) {
  if (!daily) return <Skeleton className="h-64 w-full" />;
  const d = daily.days;
  const axis = { automargin: true, gridcolor: "var(--ipm-border)" };
  const base = { margin: { t: 30, r: 10, b: 40, l: 50 }, xaxis: axis, showlegend: true, legend: { orientation: "h", y: 1.15 } };
  return (
    <div className="grid gap-3 lg:grid-cols-2" data-testid="agentops-charts">
      <Card className="p-3"><Plot ariaLabel="Runs per day" testId="chart-runs" data={[{ type: "bar", x: d.map((x) => x.day), y: d.map((x) => x.runs), name: "Runs", marker: { color: "var(--ipm-accent)" } }]}
        layout={{ ...base, title: { text: "Runs per day", font: { size: 13 } }, yaxis: { ...axis, title: { text: "Runs" } } }} /></Card>
      <Card className="p-3"><Plot ariaLabel="Latency" testId="chart-latency" data={[
        { type: "scatter", mode: "lines+markers", x: d.map((x) => x.day), y: d.map((x) => x.p50_ms / 1000), name: "p50" },
        { type: "scatter", mode: "lines+markers", x: d.map((x) => x.day), y: d.map((x) => x.p95_ms / 1000), name: "p95" }]}
        layout={{ ...base, title: { text: "Latency (seconds)", font: { size: 13 } }, yaxis: { ...axis, title: { text: "Seconds" }, tickformat: ",.1f" } }} /></Card>
      <Card className="p-3"><Plot ariaLabel="Cost" testId="chart-cost" data={[{ type: "bar", x: d.map((x) => x.day), y: d.map((x) => x.cost_usd), name: "Cost (USD)" }]}
        layout={{ ...base, title: { text: "Cost per day (USD)", font: { size: 13 } }, yaxis: { ...axis, title: { text: "USD" }, tickformat: ",.2f" } }} /></Card>
      <Card className="p-3"><Plot ariaLabel="Refusal rate by module" testId="chart-refusal" data={[{ type: "bar", orientation: "h", y: daily.modules.map((m) => MODULE_LABEL[m.module] ?? m.module),
        x: daily.modules.map((m) => m.refusal_rate * 100), name: "Refusal rate (%)" }]}
        layout={{ ...base, title: { text: "Refusal rate by module (%)", font: { size: 13 } }, xaxis: { ...axis, title: { text: "%" }, tickformat: ",.1f" }, yaxis: { automargin: true } }} /></Card>
    </div>
  );
}

function Evals({ tick, reload }: { tick: number; reload: () => void }) {
  const ev = useLoad(() => admin.evals(), `evals:${tick}`);
  const [busy, setBusy] = React.useState("");
  const [err, setErr] = React.useState("");
  if (!ev.data) return <Skeleton className="h-40 w-full" />;
  return (
    <div className="grid gap-3 md:grid-cols-2" data-testid="agentops-evals">
      {Object.entries(ev.data.suites).map(([m, qs]) => {
        const last = ev.data!.runs.find((r) => r.module === m);
        return (
          <Card key={m} className="space-y-2 p-4" data-testid="eval-suite" data-module={m}>
            <div className="flex items-center justify-between">
              <p className="text-[14px] font-semibold text-text-primary">{MODULE_LABEL[m] ?? m}</p>
              <button type="button" disabled={!!busy} data-testid="eval-run" onClick={() => { setBusy(m); setErr(""); void admin.runEval(m).then(reload).catch((e: unknown) => setErr(friendlyMessage(e))).finally(() => setBusy("")); }}
                      className="inline-flex items-center gap-1 rounded-md bg-accent px-2.5 py-1 text-[12px] text-accent-contrast disabled:opacity-40"><Play size={12} /> {busy === m ? "Running…" : "Run"}</button>
            </div>
            {last ? <p className="text-[12px]" data-testid="eval-last" data-passed={last.passed} data-total={last.total}>Last run {when(last.at)} by {last.by}: <span className={last.passed === last.total ? "text-positive" : "text-warning"}>{count(last.passed)} of {count(last.total)} pass ({pct(last.passed / Math.max(1, last.total), 0)})</span></p>
              : <p className="text-[12px] text-text-muted">Not run yet.</p>}
            <ul className="space-y-1 text-[12px]">{qs.map((q, i) => {
              const r = last?.results[i];
              return <li key={i} className="flex gap-2"><span className={cn("mt-0.5 h-2 w-2 shrink-0 rounded-full", !r ? "bg-border" : r.pass ? "bg-positive" : "bg-negative")} />
                <span className="text-text-secondary">{q.q} <span className="text-text-muted">(expects {q.expect_tools.join(", ")})</span></span></li>;
            })}</ul>
          </Card>);
      })}
      {err ? <p role="alert" className="text-[12px] text-negative">{err}</p> : null}
    </div>
  );
}

function Switches({ tick, reload }: { tick: number; reload: () => void }) {
  const st = useLoad(() => admin.studio(), `sw:${tick}`);
  const [err, setErr] = React.useState("");
  if (!st.data) return <Skeleton className="h-40 w-full" />;
  return (
    <div className="space-y-2" data-testid="agentops-switches">
      {err ? <p role="alert" className="text-[12px] text-negative">{err}</p> : null}
      <div className="grid gap-3 md:grid-cols-3">
        {st.data.configs.map((c) => (
          <Card key={c.id} className="flex items-center justify-between p-4" data-testid="kill-switch" data-module={c.id} data-on={c.body.kill_switch}>
            <div><p className="text-[14px] font-semibold text-text-primary">{c.body.title}</p>
              <p className="text-[12px] text-text-muted">{c.body.read_only ? "Frozen: not switched here" : c.body.kill_switch ? "Planner mode (assistant model off)" : `Assistant on · ${modelDisplayName(c.body.model)}`}</p></div>
            {!c.body.read_only ? <button type="button" data-testid="kill-switch-toggle" onClick={() => void admin.kill(c.id, !c.body.kill_switch, "From Agent Operations").then(reload).catch((e: unknown) => setErr(friendlyMessage(e)))}
              className={cn("inline-flex items-center gap-1 rounded-md px-2.5 py-1 text-[12px]", c.body.kill_switch ? "bg-positive text-white" : "border border-negative text-negative")}>
              <Power size={12} /> {c.body.kill_switch ? "Turn the assistant back on" : "Kill switch"}</button> : <Chip>Read only</Chip>}
          </Card>))}
      </div>
    </div>
  );
}

// ================================================================ A4 AI Studio
export function StudioPage() {
  const [tick, reload] = useTick();
  const me = useMe();
  const st = useLoad(() => admin.studio(), `studio:${tick}`);
  const [mod, setMod] = React.useState("what_if");
  const [draft, setDraft] = React.useState<StudioConfig | null>(null);
  const [q, setQ] = React.useState("Increase PD by 15% with staging effect");
  const [bench, setBench] = React.useState<Awaited<ReturnType<typeof admin.bench>> | null>(null);
  const [err, setErr] = React.useState("");
  const cfg = st.data?.configs.find((c) => c.id === mod)?.body;
  React.useEffect(() => { setDraft(null); setBench(null); }, [mod]);
  const ed = draft ?? cfg;
  const set = (f: (c: StudioConfig) => void) => { if (!ed) return; const c = JSON.parse(JSON.stringify(ed)) as StudioConfig; f(c); setDraft(c); };
  const input = "w-full rounded-md border border-border bg-surface px-2 py-1 text-[12px] text-text-primary disabled:opacity-60";
  const ro = !!cfg?.read_only;
  return (
    <AdminFrame title="AI Studio" testId="admin-studio"
                info={<><p>How each module&apos;s assistant behaves: the model, its instructions and house tone, the glossary of bank terms, its knowledge sources, the tools it may call, its guardrails and answer style. Try a question against the live configuration and your draft side by side, then publish the draft through approval. The Cockpit&apos;s configuration is frozen and read-only here.</p>{HELP("AI Studio")}</>}
                seeds={[{ label: "What is AI Studio?", send: "What is AI Studio?" }]}>
      {!st.data || !me ? <Skeleton className="h-64 w-full" /> : <>
        <ChangeQueue changes={st.data.changes} me={me.username} onDone={reload} testId="studio-changes" />
        <div className="flex flex-wrap gap-1" data-testid="studio-modules">
          {st.data.configs.map((c) => <button key={c.id} type="button" onClick={() => setMod(c.id)} data-testid={`studio-module-${c.id}`}
            className={cn("rounded-full border px-3 py-1 text-[12px]", mod === c.id ? "border-accent bg-accent/10 text-accent" : "border-border text-text-secondary")}>{c.body.title}{c.body.read_only ? " (read only)" : ""}</button>)}
        </div>
        {ed ? (
          <div className="grid gap-4 lg:grid-cols-2">
            <Card className="space-y-3 p-4" data-testid="studio-config" data-module={mod}>
              <div className="flex items-center justify-between"><p className="text-[14px] font-semibold text-text-primary">{ed.title}</p>
                {ro ? <Chip>Frozen Cockpit: read only</Chip> : draft ? <Chip tone="warn">Draft (not saved)</Chip> : <Chip tone="good">Live</Chip>}</div>
              <label className="block space-y-1 text-[11px] text-text-muted">Model
                <select disabled={ro} value={ed.model} onChange={(e) => set((c) => { c.model = e.target.value; })} data-testid="studio-model" className={input}>
                  {MODEL_NAMES.map((m) => <option key={m.id} value={m.id}>{m.display}</option>)}
                  {ed.model && !MODEL_NAMES.some((m) => m.id === ed.model) ? <option value={ed.model}>{modelDisplayName(ed.model)}</option> : null}</select></label>
              <label className="block space-y-1 text-[11px] text-text-muted">System instructions
                <textarea disabled={ro} rows={4} value={ed.instructions} onChange={(e) => set((c) => { c.instructions = e.target.value; })} data-testid="studio-instructions" className={input} /></label>
              <label className="block space-y-1 text-[11px] text-text-muted">House tone
                <input disabled={ro} value={ed.tone} onChange={(e) => set((c) => { c.tone = e.target.value; })} className={input} /></label>
              <div className="space-y-1 text-[11px] text-text-muted">Glossary
                <ul className="space-y-0.5 text-[12px] text-text-secondary">{ed.glossary.map((g) => <li key={g.term}><span className="font-medium text-text-primary">{g.term}</span>: {g.meaning}</li>)}</ul></div>
              <div className="space-y-1 text-[11px] text-text-muted">Knowledge sources <div className="flex flex-wrap gap-1">{ed.knowledge.map((k) => <Chip key={k}>{k}</Chip>)}</div></div>
              <div className="space-y-1 text-[11px] text-text-muted">Allowed tools (click to switch one off or on)
                <div className="flex flex-wrap gap-1">{[...new Set([...(ed.known_tools ?? []), ...ed.tools])].map((t) => {
                  const on = ed.tools.includes(t);
                  return <button key={t} type="button" disabled={ro} data-testid="studio-tool" data-on={on} aria-pressed={on}
                    onClick={() => set((c) => { c.tools = on ? c.tools.filter((x) => x !== t) : [...c.tools, t]; })}
                    className={cn("rounded-full border px-2 py-0.5 text-[11px] disabled:opacity-70", on ? "border-accent bg-accent/10 text-accent" : "border-border text-text-muted line-through")}>{t}</button>;
                })}</div></div>
              <div className="flex flex-wrap gap-3 text-[12px]">
                {(["no_untraced_figure", "scope_refusal"] as const).map((g) => <label key={g} className="flex items-center gap-1"><input type="checkbox" disabled={ro} checked={!!ed.guardrails[g]}
                  onChange={(e) => set((c) => { c.guardrails[g] = e.target.checked; })} data-testid={`studio-guard-${g}`} /> {g === "no_untraced_figure" ? "No untraced figure" : "Refuse out-of-scope questions"}</label>)}
                <label className="flex items-center gap-1">Answers <select disabled={ro} value={ed.answer_style.length} onChange={(e) => set((c) => { c.answer_style.length = e.target.value; })} className="rounded border border-border bg-surface px-1 text-[12px]">
                  <option value="short">short</option><option value="medium">medium</option><option value="long">long</option></select></label>
              </div>
              {!ro ? <div className="flex justify-end gap-2">
                {draft ? <button type="button" onClick={() => setDraft(null)} className="rounded-md border border-border px-3 py-1 text-[12px]">Discard</button> : null}
                <button type="button" disabled={!draft} data-testid="studio-publish" onClick={() => { setErr(""); void admin.draft("studio", "update", draft, `AI Studio: ${draft!.title}`, mod, true).then(() => { setDraft(null); reload(); }).catch((e: unknown) => setErr(friendlyMessage(e))); }}
                        className="rounded-md bg-accent px-3 py-1 text-[12px] font-medium text-accent-contrast disabled:opacity-40">Submit the draft for approval</button></div> : null}
              {err ? <p role="alert" className="text-[12px] text-negative">{err}</p> : null}
            </Card>
            <Card className="space-y-3 p-4" data-testid="studio-bench">
              <p className="text-[14px] font-semibold text-text-primary">Try-out bench</p>
              <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); void admin.bench(mod, q, draft ?? undefined).then(setBench).catch((x: unknown) => setErr(String(x))); }}>
                <input value={q} onChange={(e) => setQ(e.target.value)} data-testid="studio-question" className={input} />
                <button type="submit" data-testid="studio-test" className="rounded-md bg-accent px-3 py-1 text-[12px] font-medium text-accent-contrast">Test</button>
              </form>
              {bench ? (
                <div className={cn("grid gap-3", bench.draft ? "md:grid-cols-2" : "")} data-testid="studio-bench-result">
                  {([["Live", bench.live], ...(bench.draft ? [["Draft", bench.draft]] : [])] as [string, NonNullable<typeof bench.live>][]).map(([label, b]) => (
                    <div key={label} className="space-y-1 rounded-md bg-surface-sunken p-3 text-[12px]" data-testid="studio-bench-side">
                      <p className="font-semibold text-text-primary">{label} · {modelDisplayName(b.model)}</p>
                      {b.refused ? <p className="text-warning">{b.refusal}</p> : <p className="text-text-secondary">Plans: {b.tools_planned.join(" → ")}</p>}
                      <details><summary className="cursor-pointer text-text-muted">Instructions the model receives ({count(b.prompt_chars)} characters)</summary>
                        <pre className="mt-1 whitespace-pre-wrap text-[11px] text-text-secondary">{b.system_prompt}</pre></details>
                    </div>))}
                  {bench.diff.length ? <p className="text-[11px] text-text-muted md:col-span-2">Changed in the draft: {bench.diff.join(", ")}</p> : null}
                </div>) : null}
            </Card>
          </div>) : null}
      </>}
    </AdminFrame>
  );
}

// ================================================================ A5 Settings
const words = (k: string) => { const t = k.replace(/_/g, " "); return t.charAt(0).toUpperCase() + t.slice(1); };
const val = (v: unknown) => (v === true ? "Yes" : v === false ? "No" : typeof v === "string" && /^[a-z]+(_[a-z]+)+$/.test(v) ? words(v) : String(v));
export function SettingsPage() {
  const router = useRouter();
  const [tick, reload] = useTick();
  const me = useMe();
  const st = useLoad(() => admin.settings(), `settings:${tick}`);
  const [edit, setEdit] = React.useState<{ id: string; text: string } | null>(null);
  const [err, setErr] = React.useState("");
  const [msg, setMsg] = React.useState("");
  return (
    <AdminFrame title="Settings" testId="admin-settings"
                info={<><p>The bank&apos;s profile and reporting calendar, the house style for every export, the register of owned parameter tables (each with its owner, version and change path through the Parameter-table workflow), notifications, data feed status and retention.</p>{HELP("Settings")}</>}
                seeds={[{ label: "How do I change a parameter table?", send: "How do I change a parameter table in Settings?" }]}>
      {!st.data || !me ? <Skeleton className="h-64 w-full" /> : <>
        <ChangeQueue changes={st.data.changes} me={me.username} onDone={reload} testId="setting-changes" />
        <Card className="flex items-center gap-3 p-4" data-testid="settings-dealdesk-params">
          <div className="min-w-0 flex-1"><p className="text-[14px] font-semibold text-text-primary">Deal Desk Parameters</p>
            <p className="text-[12px] text-text-secondary" title="FTP curves, deposit FTP credit, hurdles, cost of equity, capital ratio, risk weights, CCFs, LGD, opex, fees, tax, tenor caps, sector appetite and leverage: versioned, applied immediately.">Pricing, capital and appetite parameters, versioned</p></div>
          <button type="button" onClick={() => router.push("/deal-desk/parameters")} className="rounded-md border border-border px-3 py-1 text-[12px] hover:border-accent">Open</button>
        </Card>
        {/* R15 a (L2): Settings -> Voice, the voice buffet; the chosen voice per language becomes Noor's and the tour's. */}
        <Card className="flex items-center gap-3 p-4" data-testid="settings-voice">
          <div className="min-w-0 flex-1"><p className="text-[14px] font-semibold text-text-primary">Voice</p>
            <p className="text-[12px] text-text-secondary">Listen to every voice on this computer, English and Arabic, and choose the one Noor and the tour use</p></div>
          <button type="button" onClick={() => router.push("/settings/voice")} data-testid="settings-voice-open" className="rounded-md border border-border px-3 py-1 text-[12px] hover:border-accent">Open</button>
        </Card>
        {msg ? <p className="text-[12px] text-positive" data-testid="settings-msg">{msg}</p> : null}
        {err ? <p role="alert" className="text-[12px] text-negative">{err}</p> : null}
        {edition() === "dealdesk" ? null : <EwsPdCard />}
        <div className="grid gap-3 lg:grid-cols-2">
          {st.data.settings.map((s) => (
            <Card key={s.id} className="space-y-2 p-4" data-testid="setting-card" data-id={s.id}>
              <div className="flex items-center justify-between"><p className="text-[14px] font-semibold text-text-primary">{s.body.name}</p>
                <button type="button" onClick={() => setEdit({ id: s.id, text: JSON.stringify(s.body.body, null, 2) })} data-testid="setting-edit" className="rounded border border-border px-2 py-0.5 text-[11px] hover:border-accent">Change</button></div>
              {edit?.id === s.id ? (<>
                <textarea rows={8} value={edit.text} onChange={(e) => setEdit({ ...edit, text: e.target.value })} data-testid="setting-json" className="w-full rounded-md border border-border bg-surface p-2 font-mono text-[11px]" />
                <div className="flex justify-end gap-2"><button type="button" onClick={() => setEdit(null)} className="rounded-md border border-border px-3 py-1 text-[12px]">Cancel</button>
                  <button type="button" data-testid="setting-submit" onClick={() => { setErr(""); try { const body = JSON.parse(edit.text);
                    void admin.draft("setting", "update", { ...s.body, body }, `Settings: ${s.body.name}`, s.id, true).then(() => { setEdit(null); setMsg("Submitted for approval."); reload(); }).catch((e: unknown) => setErr(friendlyMessage(e))); }
                    catch { setErr("That is not valid JSON."); } }} className="rounded-md bg-accent px-3 py-1 text-[12px] text-accent-contrast">Submit for approval</button></div></>) : (
                <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-[12px]">{Object.entries(s.body.body).map(([k, v]) => (<React.Fragment key={k}>
                  <dt className="text-text-muted">{words(k)}</dt><dd className="text-text-primary">{typeof v === "object" ? Object.entries(v as Record<string, unknown>).map(([a, b]) => `${words(a).toLowerCase()}: ${val(b)}`).join("; ") : val(v)}</dd></React.Fragment>))}</dl>)}
              <p className="text-[11px] text-text-muted">v{s.version} · {when(s.updated_at)} by {s.updated_by}</p>
            </Card>))}
        </div>
        <section className="space-y-2">
          <h2 className="text-[14px] font-semibold text-text-primary">Parameter tables</h2>
          <div className="overflow-x-auto rounded-md border border-border bg-surface">
            <table className="w-full text-[12px]" data-testid="param-register">
              <thead className="bg-surface-sunken text-left text-[10px] uppercase tracking-wide text-text-muted">
                <tr><th className="px-3 py-2">Table</th><th className="px-3 py-2">Module</th><th className="px-3 py-2">Owner</th><th className="px-3 py-2">Version</th><th className="px-3 py-2">Effective</th><th className="px-3 py-2">Approved by</th><th className="px-3 py-2" /></tr>
              </thead>
              <tbody>{st.data.parameters.map((p) => (
                <tr key={p.id} className="border-t border-border" data-testid="param-row" data-id={p.id}>
                  <td className="px-3 py-2"><p className="font-medium text-text-primary">{p.name}</p><p className="text-[11px] text-text-muted">{p.description}</p></td>
                  <td className="px-3 py-2">{p.module}</td><td className="px-3 py-2">{p.owner}</td><td className="px-3 py-2 font-mono">{p.version}</td>
                  <td className="whitespace-nowrap px-3 py-2 tabular-nums">{p.effective_from}</td><td className="px-3 py-2 text-text-secondary">{p.approved_by}</td>
                  <td className="px-3 py-2"><button type="button" data-testid="param-propose" onClick={() => { setErr(""); void admin.draft("param", "create", { ...p, id: `${p.id}-next`, status: "proposed", workflow: "WF-PARAM" }, `Propose a new version of ${p.name}`, `${p.id}-next`).then(() => { setMsg(`Draft opened for ${p.name}; it follows the Parameter-table change workflow.`); reload(); }).catch((e: unknown) => setErr(friendlyMessage(e))); }}
                    className="whitespace-nowrap rounded border border-border px-2 py-0.5 text-[11px] hover:border-accent">Propose change</button></td></tr>))}</tbody>
            </table>
          </div>
        </section>
        <section className="space-y-2">
          <h2 className="text-[14px] font-semibold text-text-primary">Data feeds</h2>
          <div className="grid gap-2 md:grid-cols-4" data-testid="feeds">
            {st.data.feeds.map((f) => (
              <Card key={f.feed} className="p-3" data-testid="feed-card">
                <p className="text-[13px] font-medium text-text-primary">{f.feed}</p>
                <p className="text-[11px] text-text-muted">{f.release} · as of {f.as_of}</p>
                <p className="text-[11px]"><Chip tone={f.status === "loaded" ? "good" : "bad"}>{f.status === "loaded" ? "Loaded" : "Missing"}</Chip> <span className="text-text-muted">{f.loaded_at}</span></p>
              </Card>))}
          </div>
        </section>
      </>}
    </AdminFrame>
  );
}

// ================================================================ A6 Audit log
export function AuditPage() {
  const [f, setF] = React.useState<{ actor: string; category: string; q: string }>({ actor: "", category: "", q: "" });
  const data = useLoad(() => admin.audit(f), `audit:${JSON.stringify(f)}`);
  return (
    <AdminFrame title="Audit log" testId="admin-audit"
                info={<><p>Who did what and when: sign-ins, exports, approvals, configuration changes and AI runs, from the Admin service, the Core service and every module&apos;s assistant. Filter it and export it to Excel.</p>{HELP("the Audit log")}</>}
                seeds={[{ label: "What does the Audit log record?", send: "What does the Audit log record?" }]}
                actions={<a href={admin.auditExportUrl(f)} data-testid="audit-export" className="inline-flex items-center gap-1 rounded-md border border-border bg-surface px-3 py-1.5 text-[13px] hover:border-accent"><Download size={13} /> Export to Excel</a>}>
      <div className="flex flex-wrap items-center gap-2" data-testid="audit-filters">
        <select value={f.actor} onChange={(e) => setF({ ...f, actor: e.target.value })} data-testid="audit-actor" className="rounded-md border border-border bg-surface px-2 py-1 text-[12px]">
          <option value="">Everyone</option>{(data.data?.actors ?? []).map((a) => <option key={a} value={a}>{a}</option>)}</select>
        <select value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })} data-testid="audit-category" className="rounded-md border border-border bg-surface px-2 py-1 text-[12px]">
          <option value="">Every kind</option>{(data.data?.categories ?? []).map((c) => <option key={c} value={c}>{c}</option>)}</select>
        <label className="flex items-center gap-1 rounded-md border border-border bg-surface px-2 py-1 text-[12px]"><Search size={12} />
          <input value={f.q} onChange={(e) => setF({ ...f, q: e.target.value })} placeholder="Search" data-testid="audit-search" className="w-48 bg-transparent outline-none" /></label>
        <span className="text-[12px] text-text-muted" data-testid="audit-total">{count(data.data?.total)} events</span>
      </div>
      {!data.data ? <Skeleton className="h-64 w-full" /> : (
        <div className="overflow-x-auto rounded-md border border-border bg-surface">
          <table className="w-full text-[12px]" data-testid="audit-table">
            <thead className="bg-surface-sunken text-left text-[10px] uppercase tracking-wide text-text-muted">
              <tr><th className="px-3 py-2">When</th><th className="px-3 py-2">Who</th><th className="px-3 py-2">What</th><th className="px-3 py-2">Kind</th><th className="px-3 py-2">Object</th></tr>
            </thead>
            <tbody>{data.data.events.map((e, i) => (
              <tr key={i} className="border-t border-border" data-testid="audit-row" data-category={e.category}>
                <td className="px-3 py-1.5 tabular-nums text-text-secondary">{when(e.at)}</td>
                <td className="px-3 py-1.5">{e.actor}{e.on_behalf_of ? <span className="text-text-muted"> as {e.on_behalf_of}</span> : null}</td>
                <td className="px-3 py-1.5 font-medium text-text-primary">{e.label}</td><td className="px-3 py-1.5"><Chip>{e.category}</Chip></td>
                <td className="max-w-[420px] truncate px-3 py-1.5 text-text-secondary">{e.object}</td></tr>))}</tbody>
          </table>
        </div>)}
    </AdminFrame>
  );
}
