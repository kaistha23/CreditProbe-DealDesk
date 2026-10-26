"use client";

import * as React from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { FileDown, FileSpreadsheet, Upload } from "lucide-react";

import { InfoPopover } from "@/components/ui/info-popover";
import { Plot } from "@/components/v5/ews/plot";
import { DataTable, Pill, PoweredTrace, Rich, STATUS_TONE } from "@/components/v5/queries/parts";
import { ErrorBox, Loading, PageTop } from "@/components/v5/workspace/parts";
import { queries, STATUSES, type Answer, type CaseCard, type QueryCard, type QueryItem } from "@/lib/v5/queries";
import { cn } from "@/lib/utils";

const BTN = "inline-flex h-8 items-center gap-1.5 rounded-md border border-border px-3 text-[12px] text-text-secondary hover:bg-surface-hover disabled:opacity-50";
const PRIMARY = "inline-flex h-8 items-center gap-1.5 rounded-md bg-accent px-3 text-[12px] font-medium text-accent-contrast hover:opacity-90 disabled:opacity-50";

/** /queries: auditor and regulator queries answered on the books (P7). ?id= opens one query. */
export function QueriesHome() {
  const params = useSearchParams();
  const router = useRouter();
  const id = params.get("id");
  return id ? <QueryView id={id} onBack={() => router.push("/queries")} /> : <Tracker open={(q) => router.push(`/queries?id=${q}`)} />;
}

function Tracker({ open }: { open: (id: string) => void }) {
  const [items, setItems] = React.useState<QueryCard[] | null>(null);
  const [cases, setCases] = React.useState<CaseCard[]>([]);
  const [error, setError] = React.useState("");
  const [busy, setBusy] = React.useState("");
  const file = React.useRef<HTMLInputElement>(null);

  const load = React.useCallback(() => {
    Promise.all([queries.list(), queries.cases()]).then(([i, c]) => { setItems(i); setCases(c); setError(""); }).catch((e) => setError(String(e.message ?? e)));
  }, []);
  React.useEffect(load, [load]);

  const run = async (label: string, fn: () => Promise<QueryItem>) => {
    setBusy(label); setError("");
    try { const q = await fn(); open(q.id); } catch (e) { setError(e instanceof Error ? e.message : String(e)); } finally { setBusy(""); }
  };

  return (
    <div className="space-y-6" data-testid="queries-home">
      <PageTop eyebrow="Functionalities" title="Queries" back={{ href: "/workspace", label: "Workspace" }}
        about={<p>Upload an auditor or CBUAE letter (Word or PDF) or an Excel template. Each question is read, answered on the books with the data used, the analysis, a draft answer, a schedule and the Trace. Edit, then export the response pack in Word and Excel. Powered by P7 Regulatory Response Intelligence.</p>}
        actions={<>
          <input ref={file} type="file" accept=".docx,.pdf,.xlsx" className="hidden" data-testid="queries-file"
                 onChange={(e) => { const f = e.target.files?.[0]; if (f) void run("upload", () => queries.upload(f)); e.target.value = ""; }} />
          <button type="button" className={PRIMARY} disabled={!!busy} onClick={() => file.current?.click()} data-testid="queries-upload">
            <Upload size={14} aria-hidden /> {busy === "upload" ? "Reading the letter…" : "Upload a letter"}
          </button>
        </>} />
      {error ? <ErrorBox error={error} /> : null}

      <section className="space-y-2">
        <h2 className="text-[13px] font-semibold uppercase tracking-wide text-text-muted">Letters received</h2>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
          {cases.map((c) => (
            <button key={c.case} type="button" disabled={!!busy || !c.file} onClick={() => void run(c.case, () => queries.prepared(c.case))}
                    className="rounded-lg border border-border bg-surface p-3 text-left hover:border-accent disabled:opacity-60" data-testid={`queries-case-${c.case}`}>
              <div className="flex items-center justify-between gap-2"><Pill tone={c.from === "CBUAE" ? "bad" : c.from === "Auditor" ? "info" : "neutral"}>{c.from}</Pill><span className="text-[11px] text-text-muted">{c.article}</span></div>
              <div className="mt-2 text-[13px] font-medium text-text-primary">{c.title}</div>
              <div className="mt-1 truncate text-[11px] text-text-muted">{busy === c.case ? "Answering…" : c.file}</div>
            </button>
          ))}
        </div>
      </section>

      <section className="space-y-2">
        <div className="flex items-center gap-2">
          <h2 className="text-[13px] font-semibold uppercase tracking-wide text-text-muted">Tracker</h2>
          <InfoPopover title="Tracker"><p>Every query with its status (Open, Drafted, Reviewed, Sent), owner and due date. Click a row to open it.</p></InfoPopover>
        </div>
        {items === null ? <Loading what="Loading queries…" /> : items.length === 0 ? (
          <p className="rounded-lg border border-dashed border-border py-8 text-center text-sm text-text-secondary">No queries yet. Open a letter above or upload one.</p>
        ) : (
          <div className="overflow-x-auto rounded-md border border-border">
            <table className="w-full text-[13px]" data-testid="queries-tracker">
              <thead className="bg-surface-hover text-left text-[12px] text-text-secondary">
                <tr><th className="px-3 py-2">Query</th><th className="px-3 py-2">From</th><th className="px-3 py-2">Reference</th><th className="px-3 py-2 text-right">Questions</th><th className="px-3 py-2">Status</th><th className="px-3 py-2">Owner</th><th className="px-3 py-2">Due</th></tr>
              </thead>
              <tbody>
                {items.map((q) => (
                  <tr key={q.id} onClick={() => open(q.id)} className="cursor-pointer border-t border-border hover:bg-surface-hover" data-testid={`queries-row-${q.id}`}>
                    <td className="px-3 py-2 font-medium text-text-primary">{q.title}</td><td className="px-3 py-2">{q.from}</td>
                    <td className="px-3 py-2 text-text-secondary">{q.reference.replace(/^REF:\s*/i, "")}</td><td className="px-3 py-2 text-right">{q.questions}</td>
                    <td className="px-3 py-2"><Pill tone={STATUS_TONE[q.status]}>{q.status}</Pill></td><td className="px-3 py-2">{q.owner}</td><td className="px-3 py-2">{q.due}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

function QueryView({ id, onBack }: { id: string; onBack: () => void }) {
  const [q, setQ] = React.useState<QueryItem | null>(null);
  const [error, setError] = React.useState("");
  React.useEffect(() => { queries.get(id).then(setQ).catch((e) => setError(e instanceof Error ? e.message : String(e))); }, [id]);
  const update = async (fn: () => Promise<QueryItem>) => { try { setQ(await fn()); setError(""); } catch (e) { setError(e instanceof Error ? e.message : String(e)); } };

  if (error && !q) return <div className="space-y-4"><button className={BTN} onClick={onBack}>Back</button><ErrorBox error={error} /></div>;
  if (!q) return <Loading what="Opening the query…" />;
  return (
    <div className="space-y-5" data-testid="query-view">
      <PageTop eyebrow={`Queries · ${q.from}`} title={q.title} back={{ href: "/queries", label: "Queries" }}
        subtitle={<>{q.reference} · {q.sender} · book period <strong>{q.period}</strong></>}
        actions={<>
          <a className={BTN} href={queries.exportUrl(q.id, "xlsx")} data-testid="query-fill"><FileSpreadsheet size={14} aria-hidden /> Fill template</a>
          <a className={BTN} href={queries.exportUrl(q.id, "docx")} data-testid="query-export-docx"><FileDown size={14} aria-hidden /> Response pack (Word)</a>
          <a className={BTN} href={queries.exportUrl(q.id, "xlsx")} data-testid="query-export-xlsx"><FileDown size={14} aria-hidden /> Schedules (Excel)</a>
        </>} />
      {error ? <ErrorBox error={error} /> : null}
      <div className="flex flex-wrap items-center gap-3 rounded-lg border border-border bg-surface p-3 text-[13px]" data-testid="query-tracker-bar">
        <label className="flex items-center gap-1.5">Status
          <select value={q.status} onChange={(e) => void update(() => queries.status(q.id, { status: e.target.value }))} className="rounded border border-border bg-surface px-2 py-1" data-testid="query-status">
            {STATUSES.map((s) => <option key={s}>{s}</option>)}
          </select>
        </label>
        <label className="flex items-center gap-1.5">Owner
          <input defaultValue={q.owner} onBlur={(e) => e.target.value !== q.owner && void update(() => queries.status(q.id, { owner: e.target.value }))} className="w-32 rounded border border-border bg-surface px-2 py-1" data-testid="query-owner" />
        </label>
        <label className="flex items-center gap-1.5">Due
          <input type="date" defaultValue={q.due} onChange={(e) => void update(() => queries.status(q.id, { due: e.target.value }))} className="rounded border border-border bg-surface px-2 py-1" data-testid="query-due" />
        </label>
        <span className="ml-auto text-text-muted">{q.answers.length} questions · {q.article}</span>
      </div>
      <ol className="space-y-5">
        {q.answers.map((a) => <AnswerCard key={a.n} a={a} onSave={(draft) => update(() => queries.edit(q.id, a.n, { draft }))} />)}
      </ol>
      <section className="rounded-lg border border-border p-3 text-[12px] text-text-secondary" data-testid="query-log">
        <div className="mb-1 font-medium text-text-primary">Activity</div>
        {q.log.map((l, i) => <div key={i}>{l.at} · {l.text}</div>)}
      </section>
    </div>
  );
}

function AnswerCard({ a, onSave }: { a: Answer; onSave: (draft: string) => Promise<void> }) {
  const [editing, setEditing] = React.useState(false);
  const [text, setText] = React.useState(a.draft);
  const [tab, setTab] = React.useState<"answer" | "data" | "analysis">("answer");
  const tid = `answer-${a.n}`;
  return (
    <li className="rounded-xl border border-border bg-surface p-4 shadow-sm" data-testid={tid}>
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full bg-accent text-[12px] font-semibold text-accent-contrast">{a.n}</span>
        <div className="min-w-0 flex-1 space-y-3">
          <div className="text-[14px] font-medium text-text-primary">{a.question}</div>
          <div className="flex gap-1 text-[12px]">
            {(["answer", "data", "analysis"] as const).map((t) => (
              <button key={t} type="button" onClick={() => setTab(t)} data-testid={`${tid}-tab-${t}`}
                      className={cn("rounded px-2 py-0.5", tab === t ? "bg-accent text-accent-contrast" : "text-text-secondary hover:bg-surface-hover")}>
                {t === "answer" ? "Draft answer" : t === "data" ? "Data used" : "Analysis"}
              </button>
            ))}
            {a.edited ? <Pill tone="info">Edited</Pill> : null}
          </div>
          {tab === "answer" ? (editing ? (
            <div className="space-y-2">
              <textarea value={text} onChange={(e) => setText(e.target.value)} rows={5} className="w-full rounded-md border border-border bg-surface p-2 text-[13px]" data-testid={`${tid}-text`} />
              <div className="flex gap-2">
                <button type="button" className={PRIMARY} onClick={() => void onSave(text).then(() => setEditing(false))} data-testid={`${tid}-save`}>Save</button>
                <button type="button" className={BTN} onClick={() => { setText(a.draft); setEditing(false); }}>Cancel</button>
              </div>
            </div>
          ) : (
            <div className="space-y-1">
              <Rich text={a.draft} />
              <button type="button" className="text-[12px] text-accent hover:underline" onClick={() => { setText(a.draft); setEditing(true); }} data-testid={`${tid}-edit`}>Edit answer</button>
            </div>
          )) : tab === "data" ? (
            <ul className="space-y-1 text-[12px] text-text-secondary">
              {a.data_used.map((d, i) => <li key={i}><span className="font-medium text-text-primary">{d.domain} · {d.relation}</span> — {d.fields.join(", ")}{d.filter ? ` · ${d.filter}` : ""}</li>)}
            </ul>
          ) : <p className="text-[13px] text-text-secondary">{a.analysis}</p>}
          {a.chart ? (
            <div className="rounded-md border border-border p-2">
              <div className="flex justify-end"><InfoPopover title="About this chart" align="right"><p>{a.analysis}</p></InfoPopover></div>
              <Plot data={a.chart.data} layout={a.chart.layout} height={260} ariaLabel={a.question} testId={`${tid}-chart`} filename={`query-${a.n}`} />
            </div>
          ) : null}
          {a.table && a.table.rows.length ? <DataTable table={a.table} testId={`${tid}-table`} /> : null}
          <PoweredTrace powered={a.powered_by} trace={a.trace} testId={tid} />
        </div>
      </div>
    </li>
  );
}
