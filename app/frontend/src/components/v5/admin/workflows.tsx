"use client";

/**
 * Admin -> Workflow -> Approval workflows (PLAN_R5 A1): workflows as step cards (assignee, SLA, escalation,
 * delegation, conditions), an editor, a simulation on a real sample object, and the live items they produced.
 */

import * as React from "react";
import { ArrowRight, Clock, GitBranch, Pencil, Play, Plus, Trash2, UserCheck } from "lucide-react";

import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { OBJECT_LABEL, ROLE_LABEL, admin, assigneeText, useLoad, type AdminUser, type Item, type LiveObject, type Sample, type Simulation,
         type Step, type Workflow } from "@/lib/v5/admin";

import { ChangeQueue, Chip, Empty, StatusPill } from "./frame";
import { friendlyMessage } from "@/lib/v5/errors";

const KIND_STYLE: Record<string, string> = { action: "border-l-accent", review: "border-l-warning", approve: "border-l-positive", notify: "border-l-border" };
const days = (n: number) => `${n} ${n === 1 ? "day" : "days"}`;
const KIND_WORD: Record<string, string> = { action: "Action", review: "Review", approve: "Approval", notify: "Notify" };

export function WorkflowsTab({ me, tick, reload }: { me: string; tick: number; reload: () => void }) {
  const wfs = useLoad(() => admin.objects<Workflow>("workflow"), `wf:${tick}`);
  const users = useLoad(() => admin.users(), "wf-users");
  const samples = useLoad(() => admin.samples(), "wf-samples");
  const [edit, setEdit] = React.useState<{ wf: Workflow; op: "create" | "update" } | null>(null);
  const [sim, setSim] = React.useState<string>("");
  if (wfs.error) return <p role="alert" className="text-sm text-negative">{wfs.error}</p>;
  if (!wfs.data || !users.data || !samples.data) return <Skeleton className="h-64 w-full" />;
  const names = Object.fromEntries(users.data.users.map((u) => [u.username, u.name]));
  return (
    <div className="space-y-5" data-testid="workflows-tab">
      <ChangeQueue changes={wfs.data.changes} me={me} onDone={reload} testId="workflow-changes" />
      {edit ? <WorkflowEditor initial={edit.wf} op={edit.op} users={users.data.users} samples={samples.data.samples}
                              onClose={() => setEdit(null)} onSaved={() => { setEdit(null); reload(); }} /> : null}
      <div className="flex items-center justify-between">
        <h2 className="text-[14px] font-semibold text-text-primary">Approval workflows</h2>
        <button type="button" onClick={() => setEdit({ op: "create", wf: blankWorkflow() })} data-testid="workflow-new"
                className="inline-flex items-center gap-1 rounded-md bg-accent px-3 py-1.5 text-[12px] font-medium text-accent-contrast"><Plus size={13} /> New workflow</button>
      </div>
      <div className="space-y-3">
        {wfs.data.objects.map((o) => (
          <WorkflowCard key={o.id} o={o} names={names} onEdit={() => setEdit({ op: "update", wf: o.body })}
                        simOpen={sim === o.id} onSim={() => setSim(sim === o.id ? "" : o.id)} samples={samples.data!.samples[o.body.object_type] ?? []} />))}
      </div>
    </div>
  );
}

function blankWorkflow(): Workflow {
  return { id: "", name: "", status: "active", object_type: "ews_name", description: "", trigger: { event: "ews_band_changed", conditions: [] },
           steps: [{ id: "s1", name: "", kind: "action", assignee: { type: "rm_of_object" }, sla_days: 5, escalate_after_days: null,
                     escalate_to: null, condition: [], delegation: true, note: "" }] };
}

export function StepCards({ wf, names }: { wf: Workflow; names: Record<string, string> }) {
  return (
    <div className="flex flex-wrap items-stretch gap-2" data-testid="workflow-steps">
      {wf.steps.map((s, i) => (
        <React.Fragment key={s.id}>
          {i ? <ArrowRight size={16} className="self-center text-text-muted" /> : null}
          <div className={cn("w-52 rounded-md border border-border border-l-4 bg-surface px-3 py-2", KIND_STYLE[s.kind])} data-testid="workflow-step">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-text-muted">{i + 1} · {KIND_WORD[s.kind] ?? s.kind}</p>
            <p className="text-[13px] font-medium leading-snug text-text-primary">{s.name}</p>
            <p className="mt-1 flex items-center gap-1 text-[11px] text-text-secondary"><UserCheck size={11} className="shrink-0" /> {assigneeText(s.assignee, names)}</p>
            {s.kind !== "notify" ? <p className="flex items-center gap-1 text-[11px] text-text-secondary"><Clock size={11} className="shrink-0" /> {days(s.sla_days)}{s.escalate_after_days ? ` · escalates after ${days(s.escalate_after_days)} to ${assigneeText(s.escalate_to, names)}` : ""}</p> : null}
            {s.condition?.length ? <p className="flex items-center gap-1 text-[11px] text-warning"><GitBranch size={11} /> if {s.condition.map((c) => `${c.field} ${c.op} ${Array.isArray(c.value) ? c.value.join("/") : String(c.value)}`).join(", ")}</p> : null}
          </div>
        </React.Fragment>))}
    </div>
  );
}

function WorkflowCard({ o, names, onEdit, simOpen, onSim, samples }: { o: LiveObject<Workflow>; names: Record<string, string>; onEdit: () => void;
  simOpen: boolean; onSim: () => void; samples: Sample[] }) {
  const w = o.body;
  return (
    <Card className="space-y-3 p-4" data-testid="workflow-card" data-id={w.id}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="text-[14px] font-semibold text-text-primary">{w.name}</p>
          <p className="text-[12px] text-text-secondary">{w.description}</p>
          <div className="mt-1 flex flex-wrap gap-1">
            <Chip tone="accent">{OBJECT_LABEL[w.object_type] ?? w.object_type}</Chip>
            {w.trigger.conditions.map((c) => <Chip key={c.field}>when {c.field} {c.op} {String(c.value)}</Chip>)}
            <Chip>v{o.version}</Chip>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <StatusPill status={w.status} />
          <button type="button" onClick={onSim} data-testid="workflow-simulate" className="inline-flex items-center gap-1 rounded-md border border-border px-2.5 py-1 text-[12px] hover:border-accent"><Play size={12} /> Simulate</button>
          <button type="button" onClick={onEdit} data-testid="workflow-edit" className="inline-flex items-center gap-1 rounded-md border border-border px-2.5 py-1 text-[12px] hover:border-accent"><Pencil size={12} /> Edit</button>
        </div>
      </div>
      <StepCards wf={w} names={names} />
      {simOpen ? <SimulatePanel wf={w} samples={samples} /> : null}
    </Card>
  );
}

export function SimulatePanel({ wf, samples }: { wf: Workflow; samples: Sample[] }) {
  const [pick, setPick] = React.useState(samples[0]?.id ?? "");
  const [res, setRes] = React.useState<Simulation | null>(null);
  const [error, setError] = React.useState("");
  const run = React.useCallback(async (id: string) => {
    setError("");
    try { setRes(await admin.simulate(wf, samples.find((s) => s.id === id))); } catch (e) { setError(friendlyMessage(e)); }
  }, [wf, samples]);
  React.useEffect(() => { void run(pick); }, [pick, run]);
  return (
    <div className="space-y-2 rounded-md bg-surface-sunken p-3" data-testid="workflow-sim">
      <div className="flex flex-wrap items-center gap-2 text-[12px]">
        <span className="font-medium text-text-primary">Simulate on</span>
        <select value={pick} onChange={(e) => setPick(e.target.value)} data-testid="workflow-sim-object" className="max-w-[420px] rounded-md border border-border bg-surface px-2 py-1 text-[12px]">
          {samples.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
        </select>
        {res ? <span className="text-text-muted">{res.fires ? "The trigger fires" : "The trigger does not fire for this object"} · {res.total_days} days end to end{res.doa ? ` · DOA level ${res.doa.level}` : ""}</span> : null}
      </div>
      {error ? <p role="alert" className="text-[12px] text-negative">{error}</p> : null}
      {res ? (
        <table className="w-full text-[12px]" data-testid="workflow-sim-table">
          <thead className="text-left text-[10px] uppercase tracking-wide text-text-muted">
            <tr><th className="py-1">Step</th><th>Assignee</th><th>Starts</th><th>Due</th><th>Escalates</th><th>Notified in</th></tr>
          </thead>
          <tbody>
            {res.timeline.map((t, i) => (
              <tr key={i} className="border-t border-border" data-testid="workflow-sim-row">
                <td className="py-1.5 font-medium text-text-primary">{t.step}</td>
                {t.skipped ? <td colSpan={5} className="text-text-muted">Skipped: {t.why}</td> : <>
                  <td>{t.assignee}</td><td className="tabular-nums">{t.starts}</td><td className="tabular-nums">{t.due}</td>
                  <td className="tabular-nums">{t.escalates ? `${t.escalates} → ${t.escalate_to}` : "–"}</td><td>{(t.notify ?? []).join(", ")}</td></>}
              </tr>))}
          </tbody>
        </table>) : <Skeleton className="h-20 w-full" />}
    </div>
  );
}

const ASSIGNEE_TYPES = [
  { v: "rm_of_object", l: "The borrower's RM" }, { v: "owner_of_object", l: "The owner" }, { v: "role", l: "A role" },
  { v: "user", l: "A person" }, { v: "doa_level", l: "DOA approver" }, { v: "doa_next", l: "Next DOA level" },
];

function AssigneePick({ value, onChange, users, testId }: { value: { type: string; value?: string } | null; onChange: (v: { type: string; value?: string } | null) => void;
  users: AdminUser[]; testId: string }) {
  const t = value?.type ?? "";
  return (
    <div className="flex gap-1">
      <select value={t} onChange={(e) => onChange(e.target.value ? { type: e.target.value, value: e.target.value === "role" ? "analyst" : e.target.value === "user" ? users[0]?.username : undefined } : null)}
              data-testid={testId} className="rounded-md border border-border bg-surface px-1.5 py-1 text-[12px]">
        <option value="">None</option>
        {ASSIGNEE_TYPES.map((a) => <option key={a.v} value={a.v}>{a.l}</option>)}
      </select>
      {t === "role" ? <select value={value?.value} onChange={(e) => onChange({ type: "role", value: e.target.value })} className="rounded-md border border-border bg-surface px-1.5 py-1 text-[12px]">
        {Object.entries(ROLE_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select> : null}
      {t === "user" ? <select value={value?.value} onChange={(e) => onChange({ type: "user", value: e.target.value })} className="rounded-md border border-border bg-surface px-1.5 py-1 text-[12px]">
        {users.map((u) => <option key={u.username} value={u.username}>{u.name}</option>)}</select> : null}
    </div>
  );
}

function WorkflowEditor({ initial, op, users, samples, onClose, onSaved }: { initial: Workflow; op: "create" | "update"; users: AdminUser[];
  samples: Record<string, Sample[]>; onClose: () => void; onSaved: () => void }) {
  const [w, setW] = React.useState<Workflow>(() => JSON.parse(JSON.stringify(initial)) as Workflow);
  const [error, setError] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const names = Object.fromEntries(users.map((u) => [u.username, u.name]));
  const set = (f: (x: Workflow) => void) => setW((x) => { const y = JSON.parse(JSON.stringify(x)) as Workflow; f(y); return y; });
  const setStep = (i: number, f: (s: Step) => void) => set((x) => { f(x.steps[i]); });
  const save = async (submit: boolean) => {
    setBusy(true); setError("");
    try { await admin.draft("workflow", op, w, `${op === "create" ? "New workflow" : "Change workflow"}: ${w.name}`, op === "update" ? w.id : "", submit); onSaved(); }
    catch (e) { setError(friendlyMessage(e)); } finally { setBusy(false); }
  };
  const input = "rounded-md border border-border bg-surface px-2 py-1 text-[12px] text-text-primary";
  return (
    <Card className="space-y-4 border-accent/50 p-5" data-testid="workflow-editor">
      <div className="flex items-center justify-between">
        <h2 className="text-[14px] font-semibold text-text-primary">{op === "create" ? "New workflow" : `Change ${initial.name}`}</h2>
        <button type="button" onClick={onClose} data-testid="workflow-cancel" className="text-[12px] text-text-muted hover:text-text-primary">Cancel</button>
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        <label className="space-y-1 text-[12px] text-text-secondary md:col-span-2">Name
          <input value={w.name} onChange={(e) => set((x) => { x.name = e.target.value; })} data-testid="workflow-name" className={cn(input, "w-full text-[13px]")} /></label>
        <label className="space-y-1 text-[12px] text-text-secondary">Applies to
          <select value={w.object_type} onChange={(e) => set((x) => { x.object_type = e.target.value; })} data-testid="workflow-object" className={cn(input, "w-full")}>
            {Object.entries(OBJECT_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
        <label className="space-y-1 text-[12px] text-text-secondary md:col-span-3">Purpose
          <input value={w.description} onChange={(e) => set((x) => { x.description = e.target.value; })} data-testid="workflow-description" className={cn(input, "w-full text-[13px]")} /></label>
      </div>
      <div className="space-y-2">
        {w.steps.map((s, i) => (
          <div key={i} className={cn("grid items-end gap-2 rounded-md border border-border border-l-4 p-3 md:grid-cols-6", KIND_STYLE[s.kind])} data-testid="workflow-edit-step">
            <label className="space-y-1 text-[11px] text-text-muted md:col-span-2">Step {i + 1}
              <input value={s.name} onChange={(e) => setStep(i, (x) => { x.name = e.target.value; })} data-testid="workflow-step-name" className={cn(input, "w-full")} /></label>
            <label className="space-y-1 text-[11px] text-text-muted">Kind
              <select value={s.kind} onChange={(e) => setStep(i, (x) => { x.kind = e.target.value as Step["kind"]; })} className={cn(input, "w-full")}>
                {Object.entries(KIND_WORD).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
            <div className="space-y-1 text-[11px] text-text-muted md:col-span-3">Assignee
              <AssigneePick value={s.assignee} users={users} testId="workflow-step-assignee" onChange={(v) => setStep(i, (x) => { x.assignee = v ?? { type: "rm_of_object" }; })} /></div>
            <label className="space-y-1 text-[11px] text-text-muted">SLA (days)
              <input type="number" min={0} value={s.sla_days} onChange={(e) => setStep(i, (x) => { x.sla_days = Number(e.target.value); })} data-testid="workflow-step-sla" className={cn(input, "w-full")} /></label>
            <label className="space-y-1 text-[11px] text-text-muted">Escalate after (days)
              <input type="number" min={0} value={s.escalate_after_days ?? ""} onChange={(e) => setStep(i, (x) => { x.escalate_after_days = e.target.value === "" ? null : Number(e.target.value); })}
                     data-testid="workflow-step-escalate" className={cn(input, "w-full")} /></label>
            <div className="space-y-1 text-[11px] text-text-muted md:col-span-3">Escalate to
              <AssigneePick value={s.escalate_to} users={users} testId="workflow-step-escalate-to" onChange={(v) => setStep(i, (x) => { x.escalate_to = v; })} /></div>
            <div className="flex items-center justify-between gap-2">
              <label className="flex items-center gap-1 text-[11px] text-text-muted"><input type="checkbox" checked={s.delegation} onChange={(e) => setStep(i, (x) => { x.delegation = e.target.checked; })} /> Delegation</label>
              {w.steps.length > 1 ? <button type="button" aria-label="Remove the step" onClick={() => set((x) => { x.steps.splice(i, 1); })} data-testid="workflow-step-remove" className="text-text-muted hover:text-negative"><Trash2 size={14} /></button> : null}
            </div>
          </div>))}
        <button type="button" data-testid="workflow-step-add" onClick={() => set((x) => { x.steps.push({ id: `s${x.steps.length + 1}`, name: "", kind: "approve", assignee: { type: "role", value: "cro" }, sla_days: 3,
          escalate_after_days: null, escalate_to: null, condition: [], delegation: true, note: "" }); })}
                className="inline-flex items-center gap-1 rounded-md border border-dashed border-border px-3 py-1 text-[12px] text-text-secondary hover:border-accent"><Plus size={12} /> Add a step</button>
      </div>
      <div className="space-y-2">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">Preview</p>
        <StepCards wf={w} names={names} />
        {w.steps.every((s) => s.name) ? <SimulatePanel wf={w} samples={samples[w.object_type] ?? []} /> : <Empty>Name every step to simulate it.</Empty>}
      </div>
      {error ? <p role="alert" className="text-[12px] text-negative" data-testid="workflow-error">{error}</p> : null}
      <div className="flex justify-end gap-2">
        <button type="button" disabled={busy || !w.name.trim()} onClick={() => void save(false)} data-testid="workflow-save" className="rounded-md border border-border px-3 py-1.5 text-[13px] hover:border-accent disabled:opacity-40">Save as draft</button>
        <button type="button" disabled={busy || !w.name.trim()} onClick={() => void save(true)} data-testid="workflow-submit" className="rounded-md bg-accent px-3 py-1.5 text-[13px] font-medium text-accent-contrast disabled:opacity-40">Save and submit for approval</button>
      </div>
    </Card>
  );
}

export function ItemsTab({ tick }: { tick: number }) {
  const items = useLoad(() => admin.items(), `items:${tick}`);
  const users = useLoad(() => admin.users(), "items-users");
  if (!items.data || !users.data) return <Skeleton className="h-40 w-full" />;
  const names = Object.fromEntries(users.data.users.map((u) => [u.username, u.name]));
  const now = new Date("2026-10-11T18:00:00Z").getTime();
  return (
    <div className="space-y-2" data-testid="items-tab">
      <h2 className="text-[14px] font-semibold text-text-primary">Live items</h2>
      {!items.data.items.length ? <Empty>No workflow item is open.</Empty> : (
        <div className="overflow-x-auto rounded-md border border-border bg-surface">
          <table className="w-full text-[13px]">
            <thead className="bg-surface-sunken text-left text-[10px] uppercase tracking-wide text-text-muted">
              <tr><th className="px-3 py-2">Item</th><th className="px-3 py-2">Workflow</th><th className="px-3 py-2">With</th><th className="px-3 py-2">Opened</th><th className="px-3 py-2">Due</th><th className="px-3 py-2">State</th></tr>
            </thead>
            <tbody>
              {items.data.items.map((it: Item) => {
                const late = new Date(it.due_at).getTime() < now;
                return (
                  <tr key={it.item_id} className="border-t border-border" data-testid="item-row">
                    <td className="px-3 py-2 font-medium text-text-primary">{it.title}</td><td className="px-3 py-2 text-text-secondary">{it.workflow_id}</td>
                    <td className="px-3 py-2">{names[it.assignee] ?? it.assignee}{it.escalated_to ? <span className="text-warning"> · escalated to {names[it.escalated_to] ?? it.escalated_to}</span> : null}</td>
                    <td className="px-3 py-2 tabular-nums">{it.opened_at.slice(0, 10)}</td><td className="px-3 py-2 tabular-nums">{it.due_at.slice(0, 10)}</td>
                    <td className="px-3 py-2">{late ? <Chip tone="bad">Overdue</Chip> : <Chip tone="good">On time</Chip>}</td>
                  </tr>);
              })}
            </tbody>
          </table>
        </div>)}
    </div>
  );
}
