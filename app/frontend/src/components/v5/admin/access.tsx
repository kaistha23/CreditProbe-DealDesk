"use client";

/**
 * Admin -> Workflow -> Data access (PLAN_R5 A1): the data access policies, a policy editor with a live preview,
 * and "View as user", which shows exactly what a user would see and can open CreditProbe as them.
 */

import * as React from "react";
import { Eye, Pencil, Plus, ShieldCheck } from "lucide-react";

import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { core } from "@/lib/v5/core";
import { FIELD_LABEL, MODULE_LABEL, ROLE_LABEL, admin, count, pct, sar, useLoad, type AdminUser, type LiveObject, type Policy } from "@/lib/v5/admin";

import { ChangeQueue, Chip, StatusPill } from "./frame";
import { friendlyMessage } from "@/lib/v5/errors";

type Options = Awaited<ReturnType<typeof admin.options>>;

export function AccessTab({ me, tick, reload }: { me: string; tick: number; reload: () => void }) {
  const pols = useLoad(() => admin.objects<Policy>("policy"), `pol:${tick}`);
  const users = useLoad(() => admin.users(), `users:${tick}`);
  const opts = useLoad(() => admin.options(), "opts");
  const [edit, setEdit] = React.useState<{ policy: Policy; op: "create" | "update" } | null>(null);
  const [viewAs, setViewAs] = React.useState("nawaf.alotaibi");
  if (pols.error) return <p role="alert" className="text-sm text-negative">{pols.error}</p>;
  if (!pols.data || !users.data || !opts.data) return <Skeleton className="h-64 w-full" />;
  const teamName = Object.fromEntries(users.data.teams.map((t) => [t.id, t.name]));
  const userName = Object.fromEntries(users.data.users.map((u) => [u.username, u.name]));
  return (
    <div className="space-y-5" data-testid="access-tab">
      <ChangeQueue changes={pols.data.changes} me={me} onDone={reload} testId="policy-changes" />
      {edit ? (
        <PolicyEditor initial={edit.policy} op={edit.op} opts={opts.data} users={users.data.users} teamName={teamName}
                      onClose={() => setEdit(null)} onSaved={() => { setEdit(null); reload(); }} />
      ) : null}
      <section className="space-y-2">
        <div className="flex items-center justify-between">
          <h2 className="text-[14px] font-semibold text-text-primary">Data access policies</h2>
          <button type="button" onClick={() => setEdit({ op: "create", policy: blankPolicy() })} data-testid="policy-new"
                  className="inline-flex items-center gap-1 rounded-md bg-accent px-3 py-1.5 text-[12px] font-medium text-accent-contrast"><Plus size={13} /> New policy</button>
        </div>
        <div className="grid gap-3 lg:grid-cols-2">
          {pols.data.objects.map((o) => <PolicyCard key={o.id} o={o} teamName={teamName} userName={userName}
                                                    onEdit={() => setEdit({ op: "update", policy: o.body })} onViewAs={(u) => setViewAs(u)} users={users.data!.users} />)}
        </div>
      </section>
      <ViewAs users={users.data.users} username={viewAs} onChange={setViewAs} />
    </div>
  );
}

function blankPolicy(): Policy {
  return { id: "", name: "", status: "active", description: "", books: ["corporate"], scope: {}, modules: ["*"],
           actions: { export: true, send: true, approve: true, run_model: true }, mask: { obligor_name: false, obligor_id: false },
           assignees: { users: [], roles: [], teams: [] } };
}

function scopeText(p: Policy): string[] {
  const out: string[] = [];
  for (const b of p.books) {
    const sc = p.scope[b] ?? {};
    const parts = Object.entries(sc).filter(([, v]) => v?.length).map(([f, v]) =>
      `${FIELD_LABEL[f] ?? f}: ${v.map((x) => (x === "own" ? "their own" : x)).slice(0, 4).join(", ")}${v.length > 4 ? ` +${v.length - 4}` : ""}`);
    out.push(`${b === "corporate" ? "Corporate" : "Retail"}: ${parts.length ? parts.join("; ") : "whole book"}`);
  }
  return out;
}

function PolicyCard({ o, teamName, userName, onEdit, onViewAs, users }: { o: LiveObject<Policy>; teamName: Record<string, string>;
  userName: Record<string, string>; onEdit: () => void; onViewAs: (u: string) => void; users: AdminUser[] }) {
  const p = o.body;
  const who = [...p.assignees.teams.map((t) => teamName[t] ?? t), ...p.assignees.roles.map((r) => `${ROLE_LABEL[r] ?? r} role`),
               ...p.assignees.users.map((u) => userName[u] ?? u)];
  const members = users.filter((u) => u.policies.some((x) => x.id === p.id));
  const blocked = Object.entries(p.actions).filter(([, v]) => !v).map(([k]) => k.replace("_", " "));
  return (
    <Card className="space-y-2.5 p-4" data-testid="policy-card" data-id={p.id}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-start gap-2">
          <ShieldCheck size={16} className="mt-0.5 shrink-0 text-accent" />
          <div>
            <p className="text-[14px] font-semibold text-text-primary">{p.name}</p>
            <p className="text-[12px] text-text-secondary">{p.description}</p>
          </div>
        </div>
        <StatusPill status={p.status} />
      </div>
      <div className="space-y-1 text-[12px]">
        {scopeText(p).map((s) => <p key={s} className="text-text-primary">{s}</p>)}
        <div className="flex flex-wrap gap-1">
          <Chip tone="accent">{p.modules.includes("*") ? "All modules" : `${p.modules.length} modules`}</Chip>
          {blocked.length ? <Chip tone="warn">No {blocked.join(", ")}</Chip> : <Chip tone="good">All actions</Chip>}
          {p.mask.obligor_name ? <Chip tone="bad">Names masked</Chip> : null}
          {p.mask.obligor_id ? <Chip tone="bad">IDs masked</Chip> : null}
        </div>
        <p className="text-text-muted">Assigned to {who.join(", ") || "nobody yet"} · v{o.version} · {members.length} {members.length === 1 ? "user" : "users"}</p>
      </div>
      <div className="flex flex-wrap gap-2">
        <button type="button" onClick={onEdit} data-testid="policy-edit" className="inline-flex items-center gap-1 rounded-md border border-border px-2.5 py-1 text-[12px] hover:border-accent"><Pencil size={12} /> Edit</button>
        {members[0] ? <button type="button" onClick={() => onViewAs(members[0].username)} data-testid="policy-view-as"
                              className="inline-flex items-center gap-1 rounded-md border border-border px-2.5 py-1 text-[12px] hover:border-accent"><Eye size={12} /> View as {members[0].name}</button> : null}
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------- editor
function Toggle({ on, onClick, children, testId }: { on: boolean; onClick: () => void; children: React.ReactNode; testId?: string }) {
  return <button type="button" onClick={onClick} data-testid={testId} aria-pressed={on}
                 className={cn("rounded-full border px-2.5 py-0.5 text-[12px]", on ? "border-accent bg-accent/10 text-accent" : "border-border text-text-secondary hover:border-accent")}>{children}</button>;
}

function PolicyEditor({ initial, op, opts, users, teamName, onClose, onSaved }: { initial: Policy; op: "create" | "update"; opts: Options;
  users: AdminUser[]; teamName: Record<string, string>; onClose: () => void; onSaved: () => void }) {
  const [p, setP] = React.useState<Policy>(() => JSON.parse(JSON.stringify(initial)) as Policy);
  const [who, setWho] = React.useState(users.find((u) => u.role === "rm")?.username ?? users[1]?.username ?? "");
  const [pv, setPv] = React.useState<Awaited<ReturnType<typeof admin.previewDraft>> | null>(null);
  const [error, setError] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const set = (f: (x: Policy) => void) => setP((x) => { const y = JSON.parse(JSON.stringify(x)) as Policy; f(y); return y; });
  const flip = <T,>(arr: T[], v: T) => (arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v]);
  const key = JSON.stringify(p) + who;
  React.useEffect(() => {
    const t = setTimeout(() => { void admin.previewDraft(p, who).then(setPv).catch(() => setPv(null)); }, 300);
    return () => clearTimeout(t);
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps
  const save = async (submit: boolean) => {
    setBusy(true); setError("");
    try {
      await admin.draft("policy", op, p, `${op === "create" ? "New policy" : "Change policy"}: ${p.name}`, op === "update" ? p.id : "", submit);
      onSaved();
    } catch (e) { setError(friendlyMessage(e)); } finally { setBusy(false); }
  };
  const field = (b: "corporate" | "retail", f: string) => p.scope[b]?.[f] ?? [];
  const setField = (b: "corporate" | "retail", f: string, v: string[]) => set((x) => {
    x.scope[b] = { ...(x.scope[b] ?? {}), [f]: v };
    if (!v.length) delete x.scope[b]![f];
  });
  return (
    <Card className="space-y-4 border-accent/50 p-5" data-testid="policy-editor">
      <div className="flex items-center justify-between">
        <h2 className="text-[14px] font-semibold text-text-primary">{op === "create" ? "New data access policy" : `Change ${initial.name}`}</h2>
        <button type="button" onClick={onClose} data-testid="policy-cancel" className="text-[12px] text-text-muted hover:text-text-primary">Cancel</button>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <label className="space-y-1 text-[12px] text-text-secondary">Name
          <input value={p.name} onChange={(e) => set((x) => { x.name = e.target.value; })} data-testid="policy-name"
                 className="w-full rounded-md border border-border bg-surface px-2.5 py-1.5 text-[13px] text-text-primary" /></label>
        <label className="space-y-1 text-[12px] text-text-secondary">Purpose
          <input value={p.description} onChange={(e) => set((x) => { x.description = e.target.value; })} data-testid="policy-description"
                 className="w-full rounded-md border border-border bg-surface px-2.5 py-1.5 text-[13px] text-text-primary" /></label>
      </div>
      <div className="space-y-2">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">Books and rows</p>
        <div className="flex gap-2">
          {(["corporate", "retail"] as const).map((b) => <Toggle key={b} on={p.books.includes(b)} testId={`policy-book-${b}`}
            onClick={() => set((x) => { x.books = flip(x.books, b); })}>{b === "corporate" ? "Corporate book" : "Retail book"}</Toggle>)}
        </div>
        {p.books.map((b) => (
          <div key={b} className="grid gap-2 rounded-md bg-surface-sunken p-3 md:grid-cols-2" data-testid={`policy-scope-${b}`}>
            <p className="md:col-span-2 text-[12px] font-medium text-text-primary">{b === "corporate" ? "Corporate" : "Retail"}: leave a field empty for every value</p>
            {Object.entries(opts.fields[b]).filter(([f]) => f !== "rm_ids" && f !== "branches" && f !== "sub_sectors").map(([f, vals]) => (
              <div key={f} className="space-y-1">
                <p className="text-[11px] text-text-muted">{FIELD_LABEL[f] ?? f}</p>
                <div className="flex flex-wrap gap-1">
                  {vals.map((v) => <Toggle key={v} on={field(b, f).includes(v)} testId={`policy-${b}-${f}`} onClick={() => setField(b, f, flip(field(b, f), v))}>{v}</Toggle>)}
                </div>
              </div>))}
            <label className="space-y-1 text-[11px] text-text-muted">Branches
              <select multiple value={field(b, "branches")} onChange={(e) => setField(b, "branches", [...e.target.selectedOptions].map((o) => o.value))}
                      data-testid={`policy-${b}-branches`} className="h-28 w-full rounded-md border border-border bg-surface text-[12px] text-text-primary">
                <option value="own">The user's own branch</option>
                {opts.branches[b].map((x) => <option key={x.branch_id} value={x.branch_id}>{x.branch_id} {x.branch_name}</option>)}
              </select></label>
            {b === "corporate" ? (
              <label className="space-y-1 text-[11px] text-text-muted">RM portfolios
                <select multiple value={field(b, "rm_ids")} onChange={(e) => setField(b, "rm_ids", [...e.target.selectedOptions].map((o) => o.value))}
                        data-testid="policy-corporate-rms" className="h-28 w-full rounded-md border border-border bg-surface text-[12px] text-text-primary">
                  <option value="own">The user's own portfolio (an RM sees their borrowers)</option>
                  {opts.rms.map((r) => <option key={r.rm_id} value={r.rm_id}>{r.rm_id} {r.rm_name} · {r.branch_name}</option>)}
                </select></label>) : null}
          </div>))}
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-1.5">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">Modules</p>
          <div className="flex flex-wrap gap-1">
            <Toggle on={p.modules.includes("*")} testId="policy-module-all" onClick={() => set((x) => { x.modules = x.modules.includes("*") ? [] : ["*"]; })}>All modules</Toggle>
            {!p.modules.includes("*") ? opts.modules.map((m) => <Toggle key={m.key} on={p.modules.includes(m.key)} testId={`policy-module-${m.key}`}
              onClick={() => set((x) => { x.modules = flip(x.modules, m.key); })}>{m.label}</Toggle>) : null}
          </div>
        </div>
        <div className="space-y-1.5">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">Actions and masking</p>
          <div className="flex flex-wrap gap-1">
            {opts.actions.map((a) => <Toggle key={a.key} on={p.actions[a.key] !== false} testId={`policy-action-${a.key}`}
              onClick={() => set((x) => { x.actions[a.key] = x.actions[a.key] === false; })}>{a.label}</Toggle>)}
            <Toggle on={p.mask.obligor_name} testId="policy-mask-name" onClick={() => set((x) => { x.mask.obligor_name = !x.mask.obligor_name; })}>Mask obligor names</Toggle>
            <Toggle on={p.mask.obligor_id} testId="policy-mask-id" onClick={() => set((x) => { x.mask.obligor_id = !x.mask.obligor_id; })}>Mask obligor IDs</Toggle>
          </div>
        </div>
      </div>
      <div className="space-y-1.5">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">Assigned to</p>
        <div className="flex flex-wrap gap-1">
          {opts.teams.map((t) => <Toggle key={t.id} on={p.assignees.teams.includes(t.id)} testId={`policy-team-${t.id}`}
            onClick={() => set((x) => { x.assignees.teams = flip(x.assignees.teams, t.id); })}>{teamName[t.id] ?? t.name}</Toggle>)}
          {opts.roles.map((r) => <Toggle key={r.id} on={p.assignees.roles.includes(r.id)} testId={`policy-role-${r.id}`}
            onClick={() => set((x) => { x.assignees.roles = flip(x.assignees.roles, r.id); })}>{r.name} role</Toggle>)}
        </div>
        <select value="" onChange={(e) => { const v = e.target.value; if (v) set((x) => { x.assignees.users = flip(x.assignees.users, v); }); }}
                data-testid="policy-user-add" className="rounded-md border border-border bg-surface px-2 py-1 text-[12px]">
          <option value="">Add or remove a user…</option>
          {users.map((u) => <option key={u.username} value={u.username}>{p.assignees.users.includes(u.username) ? "✓ " : ""}{u.name}</option>)}
        </select>
      </div>
      <div className="rounded-md border border-border p-3" data-testid="policy-preview">
        <div className="flex flex-wrap items-center gap-2 text-[12px]">
          <span className="font-medium text-text-primary">Preview for</span>
          <select value={who} onChange={(e) => setWho(e.target.value)} data-testid="policy-preview-user" className="rounded-md border border-border bg-surface px-2 py-1 text-[12px]">
            {users.map((u) => <option key={u.username} value={u.username}>{u.name}</option>)}
          </select>
        </div>
        <div className="mt-2 grid gap-2 md:grid-cols-2">
          {pv ? Object.entries(pv.books).map(([b, v]) => (
            <p key={b} className="text-[12px] text-text-secondary" data-testid="policy-preview-book" data-book={b} data-customers={v.customers}>
              <span className="font-medium text-text-primary">{b === "corporate" ? "Corporate" : "Retail"}:</span> {count(v.customers)} of {count(v.of)} customers ({pct(v.of ? v.customers / v.of : 0)}), {sar(v.ead_sar_mn)} of {sar(v.of_ead_sar_mn)} EAD</p>))
            : <Skeleton className="h-8 w-full" />}
        </div>
      </div>
      {error ? <p role="alert" className="text-[12px] text-negative" data-testid="policy-error">{error}</p> : null}
      <div className="flex justify-end gap-2">
        <button type="button" disabled={busy || !p.name.trim()} onClick={() => void save(false)} data-testid="policy-save" className="rounded-md border border-border px-3 py-1.5 text-[13px] hover:border-accent disabled:opacity-40">Save as draft</button>
        <button type="button" disabled={busy || !p.name.trim()} onClick={() => void save(true)} data-testid="policy-submit" className="rounded-md bg-accent px-3 py-1.5 text-[13px] font-medium text-accent-contrast disabled:opacity-40">Save and submit for approval</button>
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------- view as
function ViewAs({ users, username, onChange }: { users: AdminUser[]; username: string; onChange: (u: string) => void }) {
  const pv = useLoad(() => admin.preview(username), `pv:${username}`);
  const [error, setError] = React.useState("");
  const open = async () => {
    try { await core.viewAs(username); window.location.assign("/"); } catch (e) { setError(friendlyMessage(e)); }
  };
  return (
    <section className="space-y-3" data-testid="view-as-panel">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-1.5 text-[14px] font-semibold text-text-primary"><Eye size={15} /> View as user</h2>
        <div className="flex items-center gap-2">
          <select value={username} onChange={(e) => onChange(e.target.value)} data-testid="view-as-user" className="rounded-md border border-border bg-surface px-2 py-1 text-[13px]">
            {users.map((u) => <option key={u.username} value={u.username}>{u.name} · {ROLE_LABEL[u.role] ?? u.role}</option>)}
          </select>
          <button type="button" onClick={() => void open()} data-testid="view-as-open" className="rounded-md bg-accent px-3 py-1.5 text-[12px] font-medium text-accent-contrast">Open CreditProbe as this user</button>
        </div>
      </div>
      {error ? <p role="alert" className="text-[12px] text-negative">{error}</p> : null}
      {!pv.data ? <Skeleton className="h-40 w-full" /> : (
        <Card className="space-y-4 p-4" data-testid="view-as-preview" data-user={username}>
          <p className="text-[13px] text-text-secondary">
            <span className="font-semibold text-text-primary">{pv.data.user.name}</span> · {pv.data.policy.unrestricted ? "Administrator: unrestricted" :
              pv.data.policy.policies.length ? `under ${pv.data.policy.policies.map((x) => x.name).join(", ")}` : "no policy: the books on their profile"}
          </p>
          <div className="grid gap-3 md:grid-cols-2">
            {pv.data.books.map((b) => (
              <div key={b.book} className="rounded-md bg-surface-sunken p-3" data-testid="view-as-book" data-book={b.book} data-visible={b.visible} data-customers={b.seen.customers}>
                <p className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">{b.book === "corporate" ? "Corporate book" : "Retail book"}</p>
                {b.visible ? (<>
                  <p className="mt-1 text-lg font-semibold tabular-nums text-text-primary">{count(b.seen.customers)} <span className="text-[12px] font-normal text-text-muted">of {count(b.total.customers)} {b.book === "corporate" ? "borrowers" : "customers"}</span></p>
                  <p className="text-[12px] text-text-secondary">EAD {sar(b.seen.ead_sar_mn)} of {sar(b.total.ead_sar_mn)} ({pct(b.total.ead_sar_mn ? b.seen.ead_sar_mn / b.total.ead_sar_mn : 0)}) · ECL {sar(b.seen.ecl_sar_mn)}</p>
                </>) : <p className="mt-1 text-[13px] text-text-muted">Not visible</p>}
              </div>))}
          </div>
          <div className="flex flex-wrap gap-1" data-testid="view-as-modules">
            {pv.data.modules.map((m) => <Chip key={m.key} tone={m.allowed ? "good" : "neutral"}>{m.allowed ? "" : "No "}{MODULE_LABEL[m.key] ?? m.label}</Chip>)}
            {pv.data.actions.map((a) => <Chip key={a.key} tone={a.allowed ? "accent" : "warn"}>{a.allowed ? "" : "No "}{a.label.split(" (")[0]}</Chip>)}
          </div>
          {pv.data.books.filter((b) => b.visible && b.sample.length).map((b) => (
            <div key={b.book} className="overflow-x-auto">
              <p className="mb-1 text-[12px] font-medium text-text-primary">Largest {b.book === "corporate" ? "borrowers" : "customers"} as they would see them</p>
              <table className="w-full text-[12px]" data-testid="view-as-sample">
                <thead className="bg-surface-sunken text-left text-[10px] uppercase tracking-wide text-text-muted">
                  <tr><th className="px-2 py-1.5">ID</th><th className="px-2 py-1.5">Name</th><th className="px-2 py-1.5">{b.book === "corporate" ? "Sector" : "Segment"}</th>
                    <th className="px-2 py-1.5">Region</th><th className="px-2 py-1.5">Branch</th>{b.book === "corporate" ? <th className="px-2 py-1.5">RM</th> : null}
                    <th className="px-2 py-1.5 text-right">EAD (SAR m)</th><th className="px-2 py-1.5 text-right">Stage</th></tr>
                </thead>
                <tbody>{b.sample.map((r) => (
                  <tr key={String(r.id)} className="border-t border-border">
                    <td className="px-2 py-1.5 font-mono">{String(r.id)}</td><td className="px-2 py-1.5">{String(r.name ?? "")}</td>
                    <td className="px-2 py-1.5">{String(r.sector ?? r.segment ?? "")}</td><td className="px-2 py-1.5">{String(r.region ?? "")}</td>
                    <td className="px-2 py-1.5">{String(r.branch ?? "")}</td>{b.book === "corporate" ? <td className="px-2 py-1.5">{String(r.rm ?? "")}</td> : null}
                    <td className="px-2 py-1.5 text-right tabular-nums">{Number(r.ead_sar_mn).toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}</td>
                    <td className="px-2 py-1.5 text-right">{String(r.stage)}</td></tr>))}</tbody>
              </table>
            </div>))}
          <p className="text-[11px] text-text-muted">Cockpit: {pv.data.cockpit.books.length ? pv.data.cockpit.books.map((b) => (b === "corporate" ? "Corporate" : "Retail")).join(" and ") : "no book"} (book level).</p>
        </Card>)}
    </section>
  );
}

