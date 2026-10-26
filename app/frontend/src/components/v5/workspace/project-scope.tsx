"use client";

/**
 * A project like a Claude project (PLAN_R3 S3-2): its access rules (which data domains it may use), its context or
 * instructions, its uploaded documents and its threads. Each thread answers only from the project's domains,
 * documents and instructions (backend/workspace_v5/responder.py) and refuses anything outside them.
 */

import { useRouter } from "next/navigation";
import { BackButton } from "@/components/v5/core/back-button";
import Link from "next/link";
import * as React from "react";
import { FileText, Loader2, MessageSquare, Upload } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { createThread, startRun } from "@/components/cockpit-v4/client";
import { useCoreAuth } from "@/components/v5/core/auth";
import { ShareButton } from "@/components/v5/mail/share";
import { AddToReportButton, type BuiltSection } from "@/components/v5/playbook/add-to-report";
import { cn } from "@/lib/utils";
import { LiveTrace, ProcessTrace, ThreadShell, UserTurn } from "@/components/v5/thread";
import { newTraceId } from "@/lib/v5/thread";
import { day, formatValue, useWs, when, type Person, type Unit } from "@/lib/v5/workspace";
import { DOMAIN_LABEL, DOMAINS, ws3, type Message, type ProjectFile, type ResultTable, type ThreadRow } from "@/lib/v5/workspace-r3";
import { MessageText } from "@/components/v5/playbook/ai-thread";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

import { ErrorBox, Loading, PageTop, SectionTitle, Who, inputClass } from "./parts";
import { friendlyMessage } from "@/lib/v5/errors";
import { edition } from "@/lib/navigation";

export interface ProjectScope {
  id: string; name: string; description: string; owner: Person | null; instructions: string; domains: string[];
  files: ProjectFile[]; threads: ThreadRow[];
}

function kb(n: number): string {
  return n >= 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`;
}

export function ProjectActions({ p }: { p: ProjectScope }) {
  const object = { type: "project" as const, id: p.id, label: `Project: ${p.name}`, href: `/projects/${p.id}`, summary: p.description.slice(0, 300) };
  const build = async () => ({
    title: p.name,
    blocks: [
      { kind: "paragraph", text: p.description },
      { kind: "bullets", items: [`Data domains: ${p.domains.map((d) => DOMAIN_LABEL[d] ?? d).join(", ") || "documents only"}`,
                                  `Documents: ${p.files.map((f) => f.name).join(", ") || "none"}`,
                                  `Threads: ${p.threads.map((t) => t.title).join("; ") || "none"}`] },
      ...(p.instructions ? [{ kind: "callout", tone: "info", text: `Instructions: ${p.instructions}` }] : []),
    ],
  });
  return (
    <>
      <ShareButton object={object} testId="ws-project-share" />
      <AddToReportButton source={object} build={async () => (await build()) as unknown as BuiltSection} testId="ws-project-add-report" defaultTitle={p.name} />
    </>
  );
}

export function ProjectScopePanel({ p, onChanged }: { p: ProjectScope; onChanged: () => void }) {
  const { effective, viewingAs } = useCoreAuth();
  const me = effective?.username ?? "";
  const canEdit = !viewingAs && (me === p.owner?.id || me === "anne");
  const [domains, setDomains] = React.useState<string[]>(p.domains);
  const [instructions, setInstructions] = React.useState(p.instructions);
  const [busy, setBusy] = React.useState(false);
  const [msg, setMsg] = React.useState<string | null>(null);
  async function save() {
    setBusy(true);
    setMsg(null);
    try {
      await ws3.settings(p.id, { domains, instructions });
      setMsg("Saved.");
      onChanged();
    } catch (e) {
      setMsg(friendlyMessage(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Card className="space-y-3 p-4" data-testid="ws-project-access">
      <SectionTitle>Access: the data this project may use</SectionTitle>
      <div className="flex flex-wrap gap-2">
        {DOMAINS.map((d) => {
          const on = domains.includes(d);
          return (
            <label key={d} data-testid={`ws-project-domain-${d}`} data-on={on ? "1" : "0"}
                   className={cn("inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs",
                                 on ? "border-accent bg-accent-muted text-accent" : "border-border text-text-muted")}>
              <input type="checkbox" checked={on} disabled={!canEdit}
                     onChange={(e) => setDomains((c) => (e.target.checked ? [...c, d] : c.filter((x) => x !== d)))} />
              {DOMAIN_LABEL[d]}
            </label>
          );
        })}
      </div>
      <div>
        <p className="mb-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-text-muted">Context and instructions</p>
        {canEdit ? (
          <textarea value={instructions} onChange={(e) => setInstructions(e.target.value)} rows={3} data-testid="ws-project-instructions"
                    aria-label="Project instructions" className={cn(inputClass, "resize-y")} />
        ) : <p className="text-sm text-text-secondary" data-testid="ws-project-instructions">{p.instructions || "None."}</p>}
      </div>
      {canEdit ? (
        <div className="flex items-center justify-end gap-2">
          {msg ? <span className="text-xs text-text-secondary" data-testid="ws-project-settings-msg">{msg}</span> : null}
          <Button size="sm" variant="outline" onClick={() => void save()} disabled={busy} data-testid="ws-project-settings-save">Save access and instructions</Button>
        </div>
      ) : <p className="text-[11px] text-text-muted">Only the project owner changes its access rules.</p>}
    </Card>
  );
}

export function ProjectDocuments({ p, onChanged }: { p: ProjectScope; onChanged: () => void }) {
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  async function upload(file: File | undefined) {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      await ws3.upload(p.id, file);
      onChanged();
    } catch (e) {
      setError(friendlyMessage(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section data-testid="ws-project-docs">
      <SectionTitle right={
        <label className="inline-flex cursor-pointer items-center gap-1 text-xs text-accent">
          {busy ? <Loader2 className="size-3.5 animate-spin" /> : <Upload className="size-3.5" />} Upload
          <input type="file" accept=".docx,.pdf,.txt,.md" className="sr-only" data-testid="ws-project-upload"
                 onChange={(e) => { void upload(e.target.files?.[0]); e.target.value = ""; }} />
        </label>}>Documents</SectionTitle>
      {error ? <p className="mb-2 text-xs text-negative" role="alert" data-testid="ws-project-upload-error">{error}</p> : null}
      {p.files.length === 0 ? <p className="text-xs text-text-muted">No documents yet. Upload a .docx, .pdf or .txt; its text is used by the project&apos;s threads.</p> : (
        <ul className="space-y-2">
          {p.files.map((f) => (
            <li key={f.id}>
              <Card className="space-y-1 p-3" data-testid={`ws-project-doc-${f.id}`}>
                <div className="flex items-center gap-2">
                  <FileText className="size-4 shrink-0 text-text-muted" aria-hidden />
                  <a href={ws3.documentHref(p.id, f.id)} className="min-w-0 flex-1 truncate text-sm font-medium text-accent hover:underline"
                     data-testid={`ws-project-doc-download-${f.id}`}>{f.name}</a>
                  <span className="text-[11px] text-text-muted">{f.kind} · {kb(f.size)} · {f.words.toLocaleString("en-US")} words</span>
                </div>
                <p className="line-clamp-2 text-xs text-text-secondary">{f.excerpt}</p>
                <p className="text-[11px] text-text-muted">{f.uploaded_by?.name} · {day(f.created_at)}</p>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function ProjectThreads({ p }: { p: ProjectScope }) {
  const router = useRouter();
  const [q, setQ] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  async function start() {
    setBusy(true);
    setError(null);
    try {
      const t = await ws3.newThread(p.id, { question: q.trim() });
      router.push(`/projects/${encodeURIComponent(p.id)}/threads/${encodeURIComponent(t.id)}`);
    } catch (e) {
      setError(friendlyMessage(e));
      setBusy(false);
    }
  }
  return (
    <section data-testid="ws-project-threads">
      <SectionTitle>Threads</SectionTitle>
      <Card className="mb-3 space-y-2 p-3">
        <textarea value={q} onChange={(e) => setQ(e.target.value)} rows={2} data-testid="ws-project-new-thread" aria-label="Ask in this project"
                  placeholder="Ask about this project's data or documents…"
                  className={cn(inputClass, "resize-y")} />
        {error ? <p className="text-xs text-negative" role="alert">{error}</p> : null}
        <div className="flex justify-end">
          <Button size="sm" onClick={() => void start()} disabled={busy || !q.trim()} data-testid="ws-project-new-thread-start">
            {busy ? <Loader2 className="animate-spin" aria-hidden /> : <MessageSquare aria-hidden />} Start a thread
          </Button>
        </div>
      </Card>
      <ul className="space-y-2">
        {p.threads.map((t) => (
          <li key={t.id}>
            <Card className="p-0" data-testid={`ws-project-thread-${t.id}`}>
              <Link href={`/projects/${encodeURIComponent(p.id)}/threads/${encodeURIComponent(t.id)}`} className="block p-3 hover:bg-surface-hover">
                <p className="text-sm font-medium text-text-primary">{t.title}</p>
                <p className="text-xs text-text-muted">{t.owner?.name} · {t.messages} messages · {when(t.updated_at)}</p>
              </Link>
            </Card>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Reply({ m, index }: { m: Message; index: number }) {
  if (m.role === "user") {
    return (
      <div className="flex justify-end" data-testid="ws-thread-msg-user" data-index={index}>
        <p className="max-w-3xl rounded-lg bg-accent px-3 py-2 text-[13px] text-accent-contrast">{m.text}</p>
      </div>
    );
  }
  return (
    <div className="space-y-2">
    {m.trace ? <ProcessTrace snapshot={m.trace} /> : null}
    <div data-testid="ws-thread-msg-assistant" data-index={index} data-refused={m.refused ? "1" : "0"}
         className={cn("space-y-2 rounded-lg border p-3.5", m.refused ? "border-warning/40 bg-warning-muted" : "border-border bg-surface")}>
      {m.refused ? <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-warning" data-testid="ws-thread-refusal">Outside this project&apos;s scope</p> : null}
      <div className="space-y-2 text-sm leading-[1.65] text-text-primary"><MessageText text={m.text} /></div>
      {m.figures?.length ? (
        <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
          {m.figures.slice(0, 8).map((f, i) => (
            <Card key={`${f.key}-${i}`} className="p-2" data-testid={`ws-thread-figure-${f.key}`} data-value={f.value}>
              <p className="text-[10px] uppercase tracking-[0.08em] text-text-muted">{f.label}</p>
              <p className="text-sm font-semibold tabular-nums">{formatValue(f.value, f.unit)}</p>
            </Card>
          ))}
        </div>) : null}
      {(m.tables?.length ? m.tables : m.table ? [m.table] : []).slice(0, 3).map((t, i) => <AnswerTable key={i} table={t} />)}
      {m.citations?.length ? (
        <div className="flex flex-wrap gap-1.5" data-testid="ws-thread-citations">
          {m.citations.map((c, i) => c.href ? (
            <Link key={i} href={c.href} className="rounded-md border border-border px-2 py-0.5 text-[11px] text-accent hover:bg-surface-hover">{c.label}</Link>
          ) : (
            <span key={i} className="rounded-md border border-border px-2 py-0.5 text-[11px] text-text-secondary">{c.kind === "document" ? "Document · " : ""}{c.label}</span>
          ))}
        </div>) : null}
    </div>
    </div>
  );
}

function AnswerTable({ table }: { table: ResultTable }) {
  const cols = table.columns ?? [];
  const rows = table.rows ?? [];
  if (!rows.length) return null;
  return (
    <div className="overflow-x-auto rounded-lg border border-border" data-testid="ws-thread-table">
      {table.title ? <p className="border-b border-border bg-surface-sunken px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.06em] text-text-muted">{table.title}</p> : null}
      <Table>
        <TableHeader>
          <TableRow>{cols.map((c) => <TableHead key={c.key} className={cn("text-[11px]", c.unit !== "text" && "text-right")}>{c.label}</TableHead>)}</TableRow>
        </TableHeader>
        <TableBody>
          {rows.slice(0, 50).map((r, i) => (
            <TableRow key={i} data-testid="ws-thread-table-row">
              {cols.map((c) => (
                <TableCell key={c.key} className={cn("py-1.5 text-[12px]", c.unit !== "text" && "text-right tabular-nums",
                                                     c.key === "reasons" && "min-w-[260px] whitespace-normal text-text-secondary")}>
                  {c.unit === "num" ? (typeof r[c.key] === "number" ? Number(r[c.key]).toLocaleString("en-US", { maximumFractionDigits: 2 }) : r[c.key] ?? "—")
                    : formatValue(r[c.key], c.unit as Unit)}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

export function ProjectThreadView({ projectId, threadId }: { projectId: string; threadId: string }) {
  const router = useRouter();
  const [reload, setReload] = React.useState(0);
  const t = useWs(() => ws3.thread(projectId, threadId), `pthread|${projectId}|${threadId}|${reload}`, `pthread|${projectId}|${threadId}`);
  const ctx = useWs(() => ws3.cockpitContext(projectId), `pctx|${projectId}`);
  const [text, setText] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [pending, setPending] = React.useState<{ q: string; trace: string } | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const back = { href: `/projects/${encodeURIComponent(projectId)}`, label: "Project" };
  async function send(raw = text) {
    const q = raw.trim();
    if (!q || busy) return;
    const trace = newTraceId();
    setBusy(true);
    setError(null);
    setPending({ q, trace });
    setText("");
    try {
      await ws3.send(projectId, threadId, q, trace);
      setReload((n) => n + 1);
    } catch (e) {
      setError(friendlyMessage(e));
      setText(q);
    } finally {
      setBusy(false);
      setPending(null);
    }
  }
  async function askCockpit() {
    const c = ctx.data;
    const q = text.trim();
    if (!c?.available || !c.domain || !q) return;
    setBusy(true);
    setError(null);
    try {
      const th = await createThread(c.domain);
      await startRun({ question: q, threadId: th.thread_id, domain: c.domain, filters: c.ui_filters });
      router.push(`/cockpit/thread/${encodeURIComponent(th.thread_id)}`);
    } catch (e) {
      setError(friendlyMessage(e));
      setBusy(false);
    }
  }
  if (t.error) return <div className="space-y-4"><PageTop title="Thread" back={back} /><ErrorBox error={t.error} /></div>;
  if (!t.data) return <div className="space-y-4"><PageTop title="Thread" back={back} /><Loading /></div>;
  const d = t.data;
  const header = (
    <header className="space-y-2">
      <BackButton fallback={{ href: back.href, label: d.project.name }} testId="ws-back" />
      <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-text-muted">Project thread</p>
      <h1 className="text-2xl font-semibold text-text-primary">{d.title}</h1>
      <div className="flex flex-wrap items-center gap-1.5 text-xs" data-testid="ws-thread-scope">
        <span className="text-text-muted">Answers only from:</span>
        {d.project.domains.map((x) => <span key={x} className="rounded-full border border-accent/40 bg-accent-muted px-2 py-0.5 text-accent">{DOMAIN_LABEL[x] ?? x}</span>)}
        {d.project.files.length ? <span className="rounded-full border border-border px-2 py-0.5 text-text-secondary">{d.project.files.length} documents</span> : null}
        {d.project.instructions ? <span className="rounded-full border border-border px-2 py-0.5 text-text-secondary" title={d.project.instructions}>project instructions</span> : null}
        <span className="text-text-muted">· started by <Who person={d.owner} /> · {when(d.created_at)}</span>
      </div>
    </header>
  );
  return (
    <div data-testid={`ws-project-thread-view-${d.id}`}>
      <ThreadShell
        header={header}
        testId="ws-thread-shell"
        scrollKey={`${d.messages.length}|${pending?.q ?? ""}`}
        notice={error ? <p className="text-xs text-negative" role="alert" data-testid="ws-thread-error">{error}</p> : null}
        composer={{
          value: text, onChange: setText, onSubmit: (v) => void send(v), busy, testId: "ws-thread", primarySend: true,
          inputTestId: "ws-thread-input", sendTestId: "ws-thread-send", placeholder: "Ask about the project's data or documents…",
          actions: ctx.data?.available && edition() !== "dealdesk" ? (
            <Button size="sm" variant="outline" className="h-9" onClick={() => void askCockpit()} disabled={busy || !text.trim()} data-testid="ws-thread-ask-cockpit"
                    title="Opens a Cockpit conversation in the project's book, with the project's context and domain scope in the request context">
              Ask the Cockpit with this project&apos;s context
            </Button>) : undefined,
        }}
      >
        <div className="space-y-3" data-testid="ws-thread-messages">
          {d.messages.map((m, i) => <Reply key={m.id} m={m} index={i} />)}
          {pending ? (
            <div className="space-y-3" data-testid="ws-thread-working">
              <UserTurn text={pending.q} />
              <LiveTrace base={ws3.traceBase()} traceId={pending.trace} />
            </div>) : null}
        </div>
      </ThreadShell>
    </div>
  );
}
