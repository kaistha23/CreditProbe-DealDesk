"use client";

/**
 * Projects: a body of work over weeks -- its tasks (each linked to the module
 * view or workspace item it is about), its people, and the investigations,
 * analyses and documents kept for it.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { type ProjectDetail as Detail, type TaskStatus, day, useWs, when, ws } from "@/lib/v5/workspace";

import { Empty, ErrorBox, LinkChips, Loading, PageTop, SectionTitle, StatusPill, Who, inputClass, useViewer } from "./parts";
import { ProjectActions, ProjectDocuments, ProjectScopePanel, ProjectThreads, type ProjectScope } from "./project-scope";
import { DOMAIN_LABEL, DOMAINS } from "@/lib/v5/workspace-r3";

const TASK_STATUSES: TaskStatus[] = ["todo", "in_progress", "done"];

export function ProjectList() {
  const [reload, setReload] = React.useState(0);
  const [creating, setCreating] = React.useState(false);
  const list = useWs(() => ws.projects(), `projects|${reload}`);
  const router = useRouter();
  return (
    <div className="space-y-5" data-testid="ws-projects">
      <PageTop title="Projects"
               about="A project holds a piece of work over weeks: its tasks, its people, and the investigations, analyses and documents kept for it."
               actions={<Button size="sm" onClick={() => setCreating((c) => !c)} data-testid="ws-new-project"><Plus aria-hidden /> New project</Button>} />
      {creating ? <NewProject onCreated={(id) => { setReload((n) => n + 1); router.push(`/projects/${id}`); }} onCancel={() => setCreating(false)} /> : null}
      {list.error ? <ErrorBox error={list.error} /> : !list.data ? <Loading /> : list.data.projects.length === 0 ? <Empty>No projects yet.</Empty> : (
        <div className="grid gap-3 md:grid-cols-2">
          {list.data.projects.map((p) => (
            <Card key={p.id} className="p-0" data-testid={`ws-project-${p.id}`}>
              <Link href={`/projects/${p.id}`} className="block space-y-2 p-4 transition-colors hover:bg-surface-hover">
                <div className="flex items-start gap-2">
                  <h3 className="min-w-0 flex-1 text-[15px] font-semibold text-text-primary">{p.name}</h3>
                  <StatusPill status={p.status} />
                </div>
                <p className="line-clamp-3 text-sm text-text-secondary">{p.description}</p>
                <Progress done={p.items_done} total={p.items} />
                <p className="text-xs text-text-muted">
                  {p.owner ? `Owner ${p.owner.name}` : null}{p.period ? ` · ${p.period}` : ""}{p.due_at ? ` · due ${day(p.due_at)}` : ""} · {p.members.length} members
                </p>
              </Link>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

function Progress({ done, total }: { done: number; total: number }) {
  const pct = total ? Math.round((100 * done) / total) : 0;
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-sunken">
        <div className="h-full rounded-full bg-accent" style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs tabular-nums text-text-muted">{done}/{total} tasks</span>
    </div>
  );
}

function NewProject({ onCreated, onCancel }: { onCreated: (id: string) => void; onCancel: () => void }) {
  const viewer = useViewer();
  const users = useWs(() => ws.users(), "users");
  const [name, setName] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [period, setPeriod] = React.useState("2026Q2");
  const [members, setMembers] = React.useState<string[]>([]);
  const [domains, setDomains] = React.useState<string[]>(["corporate", "retail", "ews", "whatif"]);
  const [instructions, setInstructions] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  async function create() {
    setBusy(true);
    setError(null);
    try {
      const p = await ws.createProject({ name, description, period, members, domains, instructions });
      onCreated(p.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create the project.");
      setBusy(false);
    }
  }
  return (
    <Card className="space-y-3 p-4" data-testid="ws-new-project-form">
      <div className="grid gap-3 sm:grid-cols-[2fr_1fr]">
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Project name" aria-label="Project name"
               className={inputClass} data-testid="ws-new-project-name" />
        <input value={period} onChange={(e) => setPeriod(e.target.value)} placeholder="Period" aria-label="Period" className={inputClass} />
      </div>
      <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={2} placeholder="What is it for?"
                aria-label="Description" className={cn(inputClass, "resize-y")} />
      <div className="flex flex-wrap gap-2 text-xs">
        <span className="text-text-muted">Data it may use:</span>
        {DOMAINS.map((d) => (
          <label key={d} className="flex items-center gap-1.5 text-text-secondary" data-testid={`ws-new-project-domain-${d}`}>
            <input type="checkbox" checked={domains.includes(d)}
                   onChange={(e) => setDomains((c) => (e.target.checked ? [...c, d] : c.filter((x) => x !== d)))} />
            {DOMAIN_LABEL[d]}
          </label>
        ))}
      </div>
      <textarea value={instructions} onChange={(e) => setInstructions(e.target.value)} rows={2} data-testid="ws-new-project-instructions"
                placeholder="Context or instructions for the project's threads (optional)" aria-label="Instructions"
                className={cn(inputClass, "resize-y")} />
      <div className="flex flex-wrap gap-2 text-xs">
        <span className="text-text-muted">Members:</span>
        {(users.data?.users ?? []).filter((u) => u.id !== viewer).map((u) => (
          <label key={u.id} className="flex items-center gap-1.5 text-text-secondary">
            <input type="checkbox" checked={members.includes(u.id)}
                   onChange={(e) => setMembers((c) => (e.target.checked ? [...c, u.id] : c.filter((x) => x !== u.id)))} />
            {u.name}
          </label>
        ))}
      </div>
      {error ? <p className="text-xs text-negative" role="alert">{error}</p> : null}
      <div className="flex justify-end gap-2">
        <Button variant="ghost" size="sm" onClick={onCancel}>Cancel</Button>
        <Button size="sm" onClick={create} disabled={busy || !name.trim()} data-testid="ws-new-project-create">Create project</Button>
      </div>
    </Card>
  );
}

export function ProjectDetail({ id }: { id: string }) {
  const viewer = useViewer();
  const [fresh, setFresh] = React.useState<Detail | null>(null);
  const [reload, setReload] = React.useState(0);
  const loaded = useWs(() => ws.project(id), `project|${id}|${reload}`, `project|${id}`);
  const p = fresh && fresh.id === id ? fresh : loaded.data;
  const changed = () => { setFresh(null); setReload((n) => n + 1); };
  const back = { href: "/projects", label: "Projects" };
  if (loaded.error) return <div className="space-y-4"><PageTop title="Project" back={back} /><ErrorBox error={loaded.error} /></div>;
  if (!p) return <div className="space-y-4"><PageTop title="Project" back={back} /><Loading /></div>;

  async function setStatus(taskId: number, status: TaskStatus) {
    setFresh(await ws.taskStatus(id, taskId, status));
  }

  return (
    <div className="space-y-5" data-testid={`ws-project-detail-${p.id}`}>
      <PageTop eyebrow="Project" title={p.name} back={back} subtitle={p.description}
               actions={<ProjectActions p={p as unknown as ProjectScope} />} />
      <div className="flex flex-wrap items-center gap-3 text-xs text-text-secondary">
        <StatusPill status={p.status} />
        {p.owner ? <span>Owner <Who person={p.owner} /></span> : null}
        {p.period ? <span>Period {p.period}</span> : null}
        {p.due_at ? <span>Due {day(p.due_at)}</span> : null}
        <span>Updated {when(p.updated_at)}</span>
      </div>
      <ProjectScopePanel key={`${p.id}|${p.updated_at}`} p={p as unknown as ProjectScope} onChanged={changed} />
      <div className="grid gap-5 lg:grid-cols-[2fr_1fr]">
        <ProjectThreads p={p as unknown as ProjectScope} />
        <ProjectDocuments p={p as unknown as ProjectScope} onChanged={changed} />
      </div>
      <div className="grid gap-5 lg:grid-cols-[2fr_1fr]">
        <section>
          <SectionTitle right={<Progress done={p.items_done} total={p.items} />}>Tasks</SectionTitle>
          <ul className="space-y-2">
            {p.tasks.map((t) => (
              <li key={t.id}>
                <Card className="p-3.5" data-testid={`ws-task-${t.id}`}>
                  <div className="flex flex-wrap items-start gap-2">
                    <div className="min-w-0 flex-1">
                      <p className={cn("text-sm font-medium", t.status === "done" ? "text-text-muted line-through" : "text-text-primary")}>{t.title}</p>
                      {t.detail ? <p className="mt-0.5 text-xs text-text-secondary">{t.detail}</p> : null}
                      <p className="mt-1 text-xs text-text-muted">{t.assignee ? `Assigned to ${t.assignee.name}` : "Unassigned"}</p>
                    </div>
                    <select value={t.status} aria-label={`Status of ${t.title}`} data-testid={`ws-task-status-${t.id}`}
                            onChange={(e) => void setStatus(t.id, e.target.value as TaskStatus)}
                            className="rounded-md border border-border bg-surface px-2 py-1 text-xs">
                      {TASK_STATUSES.map((s) => <option key={s} value={s}>{s === "todo" ? "To do" : s === "in_progress" ? "In progress" : "Done"}</option>)}
                    </select>
                  </div>
                  {t.href ? <LinkChips className="mt-2" links={[{ label: t.link_label || t.href, href: t.href, type: "task" }]} /> : null}
                </Card>
              </li>
            ))}
          </ul>
          <AddTask id={id} viewer={viewer} onAdded={(d) => setFresh(d)} />
        </section>
        <aside className="space-y-5">
          <section>
            <SectionTitle>People</SectionTitle>
            <ul className="space-y-1.5 text-xs">{p.members.map((m) => <li key={m.id}><Who person={m} /></li>)}</ul>
          </section>
          <Related title="Investigations" items={p.investigations.map((i) => ({ href: `/investigations/${i.id}`, label: i.title }))} />
          <Related title="Saved analyses" items={p.analyses.map((a) => ({ href: `/analyses/${a.id}`, label: a.title }))} />
          <Related title="Documents" items={p.documents.map((d) => ({ href: `/documents/${d.id}`, label: d.title }))} />
          <section>
            <SectionTitle>Open in the modules</SectionTitle>
            <LinkChips links={p.links} />
          </section>
        </aside>
      </div>
    </div>
  );
}

export function Related({ title, items }: { title: string; items: { href: string; label: string }[] }) {
  if (!items.length) return null;
  return (
    <section>
      <SectionTitle>{title}</SectionTitle>
      <ul className="divide-y divide-border rounded-lg border border-border bg-surface text-sm">
        {items.map((i) => (
          <li key={i.href}><Link href={i.href} className="block px-3 py-2 text-accent hover:bg-surface-hover">{i.label}</Link></li>
        ))}
      </ul>
    </section>
  );
}

function AddTask({ id, viewer, onAdded }: { id: string; viewer: string; onAdded: (d: Detail) => void }) {
  const users = useWs(() => ws.users(), "users");
  const [title, setTitle] = React.useState("");
  const [assignee, setAssignee] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  async function add() {
    setBusy(true);
    setError(null);
    try {
      onAdded(await ws.addTask(id, { title, detail: "", assignee_id: assignee || null }));
      setTitle("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not add the task.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="mt-3 flex flex-wrap items-center gap-2">
      <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Add a task" aria-label="New task"
             className={cn(inputClass, "w-auto flex-1 py-1.5")} data-testid="ws-new-task" />
      <select value={assignee} onChange={(e) => setAssignee(e.target.value)} aria-label="Assign to"
              className="rounded-md border border-border bg-surface px-2 py-1.5 text-xs">
        <option value="">Unassigned</option>
        {(users.data?.users ?? []).map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
      </select>
      <Button size="sm" variant="outline" onClick={add} disabled={busy || !title.trim()} data-testid="ws-new-task-add">Add</Button>
      {error ? <p className="w-full text-xs text-negative">{error}</p> : null}
    </div>
  );
}
