"use client";

/**
 * Round K: the rules, shown and edited where Anne asked: the analyst's own page (My rules: theirs, their team's, the bank's)
 * and Policy Docs → Global rules (the bank's). Every rule shows its author, date and source; an edit, pause or removal is
 * kept in its history.
 */

import * as React from "react";
import { History, Loader2, Pause, Pencil, Play, Plus, Trash2 } from "lucide-react";

import { cn } from "@/lib/utils";
import { type DocType, type Rule, type RuleEvent, type Scope, rules } from "@/lib/v5/dealdesk-rules";
import { friendlyMessage } from "@/lib/v5/errors";

const sel = "h-8 rounded-md border border-border bg-surface px-2 text-[12.5px] text-text-primary";
const btn = "inline-flex items-center gap-1 rounded-md border border-border px-2 py-0.5 text-[11.5px] hover:bg-surface-hover disabled:opacity-50";
const SCOPES: { id: Scope; label: string }[] = [{ id: "me", label: "Me" }, { id: "team", label: "My team" }, { id: "bank", label: "The bank" }];
const DOCS: { id: DocType; label: string }[] = [{ id: "both", label: "Both documents" }, { id: "request", label: "Credit request" }, { id: "proposal", label: "Credit proposal" }];

export function RulesList({ scope, mine = false, addScope = "me", title, testId = "rules-list" }: {
  scope?: Scope; mine?: boolean; addScope?: Scope; title?: string; testId?: string;
}) {
  const [rows, setRows] = React.useState<Rule[] | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [tick, setTick] = React.useState(0);
  const [adding, setAdding] = React.useState(false);
  React.useEffect(() => {
    let live = true;
    rules.list({ scope, mine, status: "" }).then((r) => live && setRows(r.rules), (e) => live && setError(friendlyMessage(e)));
    return () => { live = false; };
  }, [scope, mine, tick]);
  const reload = () => setTick((n) => n + 1);
  return (
    <section className="space-y-3" data-testid={testId}>
      <div className="flex flex-wrap items-center gap-2">
        {title ? <h2 className="text-[15px] font-semibold text-text-primary">{title}</h2> : null}
        {rows ? <span className="text-[12px] text-text-muted" data-testid={`${testId}-count`}>{rows.length} rule{rows.length === 1 ? "" : "s"}</span> : null}
        <button type="button" onClick={() => setAdding((a) => !a)} className={cn(btn, "ml-auto")} data-testid={`${testId}-add`}><Plus className="size-3.5" /> Add a rule</button>
      </div>
      {adding ? <AddRule scope={addScope} onDone={() => { setAdding(false); reload(); }} testId={`${testId}-new`} /> : null}
      {error ? <p role="alert" className="text-[12.5px] text-negative">{error}</p> : !rows ? <p className="text-[12.5px] text-text-muted">Loading the rules…</p> : rows.length === 0 ? (
        <p className="rounded-lg border border-dashed border-border px-4 py-6 text-center text-[12.5px] text-text-muted" data-testid={`${testId}-empty`}>
          No rules yet. When you give CreditProbe an instruction in a document, it asks whether to keep it as a rule.
        </p>
      ) : (
        <ul className="divide-y divide-border rounded-lg border border-border bg-surface">
          {rows.map((r) => <RuleRow key={r.id} r={r} onChanged={reload} testId={`${testId}-row`} />)}
        </ul>
      )}
    </section>
  );
}

function AddRule({ scope, onDone, testId }: { scope: Scope; onDone: () => void; testId: string }) {
  const [text, setText] = React.useState("");
  const [sc, setSc] = React.useState<Scope>(scope);
  const [doc, setDoc] = React.useState<DocType>("both");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  async function save() {
    setBusy(true); setError(null);
    try { await rules.create({ instruction: text.trim(), scope: sc, document: doc, source: { via: "typed" } }); onDone(); }
    catch (e) { setError(friendlyMessage(e)); } finally { setBusy(false); }
  }
  return (
    <div className="space-y-2 rounded-lg border border-border bg-surface-sunken p-3" data-testid={testId}>
      <textarea value={text} onChange={(e) => setText(e.target.value)} rows={2} maxLength={600} placeholder="For example: say obligor, not client"
                className="w-full rounded-md border border-border bg-surface p-2 text-[12.5px]" data-testid={`${testId}-text`} aria-label="The rule" />
      <div className="flex flex-wrap items-center gap-2 text-[12px]">
        <select value={sc} onChange={(e) => setSc(e.target.value as Scope)} className={sel} data-testid={`${testId}-scope`} aria-label="Who it is for">
          {SCOPES.map((x) => <option key={x.id} value={x.id}>{x.label}</option>)}
        </select>
        <select value={doc} onChange={(e) => setDoc(e.target.value as DocType)} className={sel} data-testid={`${testId}-document`} aria-label="Document">
          {DOCS.map((x) => <option key={x.id} value={x.id}>{x.label}</option>)}
        </select>
        <button type="button" onClick={() => void save()} disabled={busy || !text.trim()} data-testid={`${testId}-save`}
                className="ml-auto inline-flex items-center gap-1 rounded-md bg-accent px-3 py-1 font-medium text-accent-contrast disabled:opacity-60">
          {busy ? <Loader2 className="size-3.5 animate-spin" /> : null} Save the rule
        </button>
      </div>
      {error ? <p role="alert" className="text-[12px] text-negative">{error}</p> : null}
    </div>
  );
}

function RuleRow({ r, onChanged, testId }: { r: Rule; onChanged: () => void; testId: string }) {
  const [edit, setEdit] = React.useState(false);
  const [text, setText] = React.useState(r.text);
  const [sc, setSc] = React.useState<Scope>(r.scope);
  const [doc, setDoc] = React.useState<DocType>(r.document);
  const [hist, setHist] = React.useState<RuleEvent[] | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  async function run(fn: () => Promise<unknown>) {
    setBusy(true); setError(null);
    try { await fn(); setEdit(false); onChanged(); } catch (e) { setError(friendlyMessage(e)); } finally { setBusy(false); }
  }
  const off = r.status !== "active";
  return (
    <li className={cn("space-y-1.5 px-3 py-2.5 text-[12.5px]", off && "opacity-70")} data-testid={testId} data-id={r.id} data-scope={r.scope} data-status={r.status}>
      {edit ? (
        <div className="space-y-2">
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={2} className="w-full rounded-md border border-border bg-surface p-2" data-testid={`${testId}-edit-text`} aria-label="Rule" />
          <div className="flex flex-wrap gap-2">
            <select value={sc} onChange={(e) => setSc(e.target.value as Scope)} className={sel} aria-label="Who it is for">{SCOPES.map((x) => <option key={x.id} value={x.id}>{x.label}</option>)}</select>
            <select value={doc} onChange={(e) => setDoc(e.target.value as DocType)} className={sel} aria-label="Document">{DOCS.map((x) => <option key={x.id} value={x.id}>{x.label}</option>)}</select>
            <button type="button" className={btn} onClick={() => setEdit(false)}>Cancel</button>
            <button type="button" className={cn(btn, "border-accent text-accent")} disabled={busy} data-testid={`${testId}-edit-save`}
                    onClick={() => void run(() => rules.update(r.id, { ...(text !== r.text ? { text } : {}), scope: sc, document: doc }))}>Save</button>
          </div>
        </div>
      ) : (
        <div className="flex flex-wrap items-start gap-x-3 gap-y-1">
          <span className="min-w-0 flex-1 text-text-primary" data-testid={`${testId}-text`}>{r.text}</span>
          {r.can_edit ? (
            <span className="flex gap-1">
              <button type="button" className={btn} onClick={() => setEdit(true)} data-testid={`${testId}-edit`}><Pencil className="size-3" /> Edit</button>
              {r.status !== "removed" ? <button type="button" className={btn} disabled={busy} data-testid={`${testId}-pause`}
                      onClick={() => void run(() => rules.update(r.id, { status: off ? "active" : "paused" }))}>{off ? <><Play className="size-3" /> Resume</> : <><Pause className="size-3" /> Pause</>}</button> : null}
              {r.status !== "removed" ? <button type="button" className={btn} disabled={busy} data-testid={`${testId}-remove`}
                      onClick={() => void run(() => rules.remove(r.id))}><Trash2 className="size-3" /> Remove</button> : null}
            </span>
          ) : null}
        </div>
      )}
      <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-text-muted">
        <span className="rounded bg-surface-sunken px-1.5 py-0.5 text-text-secondary">{r.kind_label}</span>
        <span>{r.scope_label}</span><span>·</span><span>{r.document_label}</span>
        {r.section_label || r.section ? <><span>·</span><span>{r.section_label || r.section}</span></> : null}
        <span>·</span><span>{r.author_name}, {r.created_at.slice(0, 10)}</span>
        {r.status !== "active" ? <span className="font-semibold uppercase text-warning">{r.status}</span> : null}
        <span className="font-mono">{r.id}</span>
        <button type="button" className="inline-flex items-center gap-0.5 text-accent hover:underline" data-testid={`${testId}-history`}
                onClick={() => hist ? setHist(null) : void rules.history(r.id).then((h) => setHist(h.events), (e) => setError(friendlyMessage(e)))}>
          <History className="size-3" /> History
        </button>
      </div>
      {r.source_instruction ? <p className="text-[11px] text-text-muted">From: “{r.source_instruction}”</p> : null}
      {hist ? (
        <ul className="ml-3 list-disc text-[11px] text-text-secondary" data-testid={`${testId}-events`}>
          {hist.map((e) => <li key={e.n}>{e.at.slice(0, 16).replace("T", " ")} · {e.by_name} · {e.action}</li>)}
        </ul>
      ) : null}
      {error ? <p role="alert" className="text-[12px] text-negative">{error}</p> : null}
    </li>
  );
}
