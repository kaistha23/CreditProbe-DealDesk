"use client";

/**
 * R10 Q1: auditor and regulator queries answered in the Cockpit (the /queries screen is gone).
 *
 * Not frozen. The frozen Cockpit home (`cockpit-v4-home.tsx`) calls `useCockpitQueries()` and renders
 * `<CockpitQueries />` under its Ask box through the registered exception FX-R10-Q1; nothing else on the home changes.
 *
 * - A question typed in the Ask box that reads as an auditor or regulator query is answered here by the Queries
 *   service (P7, port 8516): the answer to the question first (its key figure bold), then the evidence (chart, table,
 *   Powered by and Trace), then the letter's other questions behind one click, and the response pack.
 * - Every other question goes to the Cockpit's agent exactly as before (the hook returns false).
 * - "Attach a letter" beside the box reads an uploaded letter (.docx, .pdf) or Excel template; "Letters" asks one of
 *   the five letters on file.
 */

import { AnswerHeadline, AnswerProse } from "@/components/answer";
import * as React from "react";
import { ChevronDown, FileDown, FileSpreadsheet, Loader2, Paperclip, X } from "lucide-react";

import { InfoPopover } from "@/components/ui/info-popover";
import { Plot } from "@/components/v5/ews/plot";
import { DataTable, Pill, PoweredTrace, STATUS_TONE } from "@/components/v5/queries/parts";
import {
  answerOrder, askQuery, headline, isQueryQuestion, NotAQuery, PREPARED_QUESTIONS, type QueryAsk,
} from "@/lib/v5/cockpit-queries";
import { queries, STATUSES, type Answer, type QueryItem } from "@/lib/v5/queries";
import { cn } from "@/lib/utils";

const BTN = "inline-flex h-7 items-center gap-1.5 rounded-md border border-border px-2.5 text-[12px] text-text-secondary hover:bg-surface-hover disabled:opacity-50";

export interface Turn { id: number; question: string; ask: QueryAsk }

export interface CockpitQueriesState {
  turns: Turn[];
  busy: string;
  error: string;
  /** Is this question one the Queries service should answer (cue check only, no network)? */
  claims: (question: string) => boolean;
  /** Answer a query in the Cockpit. False when the service says it is not a query: the caller asks the agent. */
  ask: (question: string) => Promise<boolean>;
  attach: (file: File) => Promise<void>;
  replace: (turnId: number, item: QueryItem) => void;
  dismiss: (turnId: number) => void;
}

export function useCockpitQueries(): CockpitQueriesState {
  const [turns, setTurns] = React.useState<Turn[]>([]);
  const [busy, setBusy] = React.useState("");
  const [error, setError] = React.useState("");
  const seq = React.useRef(0);
  const lastItem = React.useRef<Record<string, string>>({});

  const push = React.useCallback((question: string, ask: QueryAsk) => {
    lastItem.current[ask.case] = ask.item.id;
    seq.current += 1;
    const turn = { id: seq.current, question, ask };
    setTurns((t) => [turn, ...t]);
  }, []);

  const ask = React.useCallback(async (question: string) => {
    const q = question.trim();
    if (!q) return false;
    setBusy(q);
    setError("");
    try {
      // The letter already answered in this conversation, when the question is about the same case.
      const items = Object.values(lastItem.current);
      const out = await askQuery(q, items.length ? items[items.length - 1] : undefined);
      push(q, out);
      return true;
    } catch (e) {
      if (e instanceof NotAQuery) return false;
      setError(e instanceof Error ? e.message : String(e));
      return true;
    } finally {
      setBusy("");
    }
  }, [push]);

  const attach = React.useCallback(async (file: File) => {
    setBusy(`Reading ${file.name}…`);
    setError("");
    try {
      const item = await queries.upload(file);
      push(`Attached ${file.name}: answer this letter`, { question: file.name, case: item.case, focus: item.answers[0]?.n ?? 1, item });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy("");
    }
  }, [push]);

  const replace = React.useCallback((turnId: number, item: QueryItem) => {
    setTurns((t) => t.map((x) => (x.id === turnId ? { ...x, ask: { ...x.ask, item } } : x)));
  }, []);
  const dismiss = React.useCallback((turnId: number) => setTurns((t) => t.filter((x) => x.id !== turnId)), []);

  return { turns, busy, error, claims: isQueryQuestion, ask, attach, replace, dismiss };
}

/** The attach row and the query answers, under the Cockpit's Ask box.
 *  R14 G (FX-R14-01): `attach={false}` leaves out the "Attach a letter / Letters on file" row; a typed auditor or regulator
 *  question is still answered here (the hand-off in askFromHome is unchanged), and evidence packs live in Governance →
 *  Inspection responder. */
export function CockpitQueries({ state, attach = true }: { state: CockpitQueriesState; attach?: boolean }) {
  const file = React.useRef<HTMLInputElement>(null);
  const [menu, setMenu] = React.useState(false);
  const top = React.useRef<HTMLDivElement>(null);
  const count = state.turns.length;
  React.useEffect(() => {
    if (count) top.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [count]);

  return (
    <div className={attach || count || state.busy || state.error ? "mt-3 space-y-3" : "hidden"} data-testid="cockpit-queries" data-attach={attach ? "1" : "0"}>
      {!attach && state.busy ? (
        <span className="inline-flex items-center gap-1.5 text-[12px] text-text-muted" data-testid="cockpit-queries-busy">
          <Loader2 size={13} className="animate-spin" aria-hidden /> Answering on the books…
        </span>) : null}
      {attach ? <div className="relative flex flex-wrap items-center gap-2 text-[12px]">
        <input ref={file} type="file" accept=".docx,.pdf,.xlsx" className="hidden" data-testid="cockpit-queries-file"
               onChange={(e) => { const f = e.target.files?.[0]; if (f) void state.attach(f); e.target.value = ""; }} />
        <button type="button" className={BTN} disabled={!!state.busy} onClick={() => file.current?.click()}
                data-testid="cockpit-queries-attach" title="Attach an auditor or regulator letter (.docx, .pdf) or an Excel template">
          <Paperclip size={13} aria-hidden /> Attach a letter
        </button>
        <button type="button" className={BTN} disabled={!!state.busy} onClick={() => setMenu((m) => !m)}
                aria-expanded={menu} data-testid="cockpit-queries-letters">
          Letters on file <ChevronDown size={13} aria-hidden />
        </button>
        <InfoPopover title="Auditor and regulator queries">
          <p>Ask an auditor, CBUAE or internal audit question in the box, attach the letter, or pick one on file. CreditProbe
            answers each numbered question on the books, with the data used, a schedule and the Trace, and drafts the
            response pack. Powered by P7 Regulatory Response Intelligence.</p>
        </InfoPopover>
        {state.busy ? (
          <span className="inline-flex items-center gap-1.5 text-text-muted" data-testid="cockpit-queries-busy">
            <Loader2 size={13} className="animate-spin" aria-hidden /> Answering on the books…
          </span>
        ) : null}
        {menu ? (
          <ul className="absolute left-0 top-8 z-20 w-[22rem] max-w-[90vw] rounded-md border border-border bg-surface p-1 shadow-lg"
              data-testid="cockpit-queries-menu">
            {PREPARED_QUESTIONS.map((p) => (
              <li key={p.case}>
                <button type="button" className="w-full rounded px-2 py-1.5 text-left text-[12px] text-text-primary hover:bg-surface-hover"
                        data-testid={`cockpit-queries-letter-${p.case}`}
                        onClick={() => { setMenu(false); void state.ask(p.question); }}>
                  {p.label}
                </button>
              </li>
            ))}
          </ul>
        ) : null}
      </div> : null}
      {state.error ? <p className="text-sm text-negative" data-testid="cockpit-queries-error">{state.error}</p> : null}
      <div ref={top} />
      {state.turns.map((t) => <QueryTurn key={t.id} turn={t} state={state} />)}
    </div>
  );
}

function QueryTurn({ turn, state }: { turn: Turn; state: CockpitQueriesState }) {
  const { item, focus } = turn.ask;
  const [lead, ...rest] = answerOrder(item.answers, focus);
  const [more, setMore] = React.useState(false);
  const update = async (fn: () => Promise<QueryItem>) => state.replace(turn.id, await fn());
  const tid = `cockpit-query-${turn.id}`;
  return (
    <article className="rounded-xl border border-border bg-surface p-4 shadow-sm" data-testid={tid} data-case={item.case} data-focus={focus}>
      <div className="flex items-start gap-2">
        <p className="min-w-0 flex-1 text-[13px] italic text-text-secondary" data-testid={`${tid}-question`}>“{turn.question}”</p>
        <button type="button" aria-label="Close this answer" className="text-text-muted hover:text-text-primary" onClick={() => state.dismiss(turn.id)}>
          <X size={14} aria-hidden />
        </button>
      </div>
      <p className="mt-1 text-[11px] text-text-muted" data-testid={`${tid}-letter`}>
        {item.from} · {item.title} · {item.article}{item.reference ? ` · ${item.reference.replace(/^REF:\s*/i, "")}` : ""} · book {item.period}
      </p>
      {lead ? <LeadAnswer a={lead} tid={`${tid}-lead`} onSave={(draft) => update(() => queries.edit(item.id, lead.n, { draft }))} /> : null}
      {rest.length ? (
        <div className="mt-3 border-t border-border pt-2">
          <button type="button" className="text-[12px] text-accent hover:underline" onClick={() => setMore((m) => !m)} data-testid={`${tid}-more`}>
            {more ? "Hide" : "Show"} the letter&rsquo;s other {rest.length} question{rest.length > 1 ? "s" : ""}
          </button>
          {more ? (
            <ol className="mt-2 space-y-3">
              {rest.map((a) => <OtherAnswer key={a.n} a={a} tid={`${tid}-q${a.n}`} />)}
            </ol>
          ) : null}
        </div>
      ) : null}
      <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-border pt-3 text-[12px]" data-testid={`${tid}-actions`}>
        <a className={BTN} href={queries.exportUrl(item.id, "docx")} data-testid={`${tid}-docx`}><FileDown size={13} aria-hidden /> Response pack (Word)</a>
        <a className={BTN} href={queries.exportUrl(item.id, "xlsx")} data-testid={`${tid}-xlsx`}><FileSpreadsheet size={13} aria-hidden /> Fill template (Excel)</a>
        <label className="ml-auto flex items-center gap-1.5 text-text-secondary">Status
          <select value={item.status} onChange={(e) => void update(() => queries.status(item.id, { status: e.target.value }))}
                  className="rounded border border-border bg-surface px-1.5 py-0.5" data-testid={`${tid}-status`}>
            {STATUSES.map((s) => <option key={s}>{s}</option>)}
          </select>
        </label>
        <Pill tone={STATUS_TONE[item.status]}>{item.owner} · due {item.due}</Pill>
      </div>
    </article>
  );
}

/** The answer to the question asked: headline with its key figure, the rest of the draft, then the evidence. */
function LeadAnswer({ a, tid, onSave }: { a: Answer; tid: string; onSave: (draft: string) => Promise<void> }) {
  const [editing, setEditing] = React.useState(false);
  const [text, setText] = React.useState(a.draft);
  const head = headline(a.draft);
  const tail = a.draft.trim().slice(head.length).trim();
  return (
    <section className="mt-3 space-y-3" data-testid={tid}>
      <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-text-muted">Question {a.n} · {a.question}</p>
      {editing ? (
        <div className="space-y-2">
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={5} className="w-full rounded-md border border-border bg-surface p-2 text-[13px]" data-testid={`${tid}-text`} />
          <div className="flex gap-2">
            <button type="button" className={BTN} onClick={() => void onSave(text).then(() => setEditing(false))} data-testid={`${tid}-save`}>Save</button>
            <button type="button" className={BTN} onClick={() => { setText(a.draft); setEditing(false); }}>Cancel</button>
          </div>
        </div>
      ) : (
        <>
          {/* PLAN_R12 N2: the shared answer style, headline sentence first. */}
          <AnswerHeadline text={head} />
          {tail ? <AnswerProse text={tail} /> : null}
          <button type="button" className="text-[12px] text-accent hover:underline" onClick={() => { setText(a.draft); setEditing(true); }} data-testid={`${tid}-edit`}>Edit answer</button>
        </>
      )}
      <Evidence a={a} tid={tid} />
    </section>
  );
}

function OtherAnswer({ a, tid }: { a: Answer; tid: string }) {
  const [open, setOpen] = React.useState(false);
  return (
    <li className="rounded-md border border-border p-3" data-testid={tid}>
      <p className="text-[12px] font-medium text-text-primary">{a.n}. {a.question}</p>
      <AnswerHeadline text={headline(a.draft)} compact className="mt-1" />
      <button type="button" className="mt-1 text-[12px] text-accent hover:underline" onClick={() => setOpen((o) => !o)} data-testid={`${tid}-open`}>
        {open ? "Hide the evidence" : "Full answer and evidence"}
      </button>
      {open ? <div className="mt-2 space-y-2"><AnswerProse text={a.draft} compact fold={false} /><Evidence a={a} tid={tid} /></div> : null}
    </li>
  );
}

function Evidence({ a, tid }: { a: Answer; tid: string }) {
  return (
    <div className={cn("space-y-3")} data-testid={`${tid}-evidence`}>
      {a.chart ? (
        <div className="rounded-md border border-border p-2">
          <div className="flex justify-end"><InfoPopover title="About this chart" align="right"><p>{a.analysis}</p></InfoPopover></div>
          <Plot data={a.chart.data} layout={a.chart.layout} height={240} ariaLabel={a.question} testId={`${tid}-chart`} filename={`query-${a.n}`} />
        </div>
      ) : null}
      {a.table && a.table.rows.length ? <DataTable table={a.table} testId={`${tid}-table`} max={10} /> : null}
      {a.data_used.length ? (
        <p className="text-[11px] text-text-muted" data-testid={`${tid}-data`}>
          Data used: {a.data_used.map((d) => `${d.domain} · ${d.relation}${d.filter ? ` (${d.filter})` : ""}`).join("; ")}
        </p>
      ) : null}
      <PoweredTrace powered={a.powered_by} trace={a.trace} testId={tid} />
    </div>
  );
}
