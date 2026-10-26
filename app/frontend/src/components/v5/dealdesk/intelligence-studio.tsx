"use client";

/**
 * Round S: Deal Desk → Intelligence Studio. "Shows how much it has learnt from the RMs, the bank." Every count comes
 * from the store that holds it (customers and their sources, documents read, proposals learned per bank and per
 * analyst, rules by author, policies in force, reader accuracy over time, corrections absorbed, model governance);
 * a store that is not there shows why, never a zero. Built from Deal Desk's own kit (Section, Kpi, Chip, tables).
 */

import * as React from "react";
import Link from "next/link";
import { Brain } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { Plot } from "@/components/v5/ews/plot";
import { BackLink } from "@/components/v5/ui/back-link";
import { PlainWords } from "@/components/v5/ui/plain-words";
import { cn } from "@/lib/utils";
import {
  type Absent, type Overview, count, coverageBars, pct, readerSeries, secs, stageLabel, studioApi, tokens,
} from "@/lib/v5/intelligence-studio";

import { C } from "./charts";
import { InfoPopover } from "./explain";
import { Chip, Empty, Kpi, Section, tableCls, tdCls, thCls } from "./kit";

const SHORT: Record<string, string> = { deal_register: "Deals", core_banking: "Core", bureau: "Bureau", group: "Group",
  credit_history: "Decisions", uploads: "Uploads", past_proposals: "Proposals" };

function Missing({ part, what }: { part: Absent; what: string }) {
  return <Empty><span data-testid="studio-empty">{part.reason || `${what} is not available in this build.`}</span></Empty>;
}

/** The link to the Studio from Deal Desk's home and from Agent Operations (one line, Deal Desk's link style). */
export function IntelligenceStudioLink({ testId = "intelligence-studio-link", className }: { testId?: string; className?: string }) {
  return (
    <Link href="/deal-desk/intelligence" data-testid={testId}
          className={cn("inline-flex items-center gap-1 text-[12px] text-accent hover:underline", className)}>
      <Brain size={12} aria-hidden />Intelligence Studio: what CreditProbe has learnt from the RMs and the bank →
    </Link>
  );
}

export function IntelligenceStudioPage() {
  const [o, setO] = React.useState<Overview | null>(null);
  const [err, setErr] = React.useState("");
  const [module, setModule] = React.useState("deal_desk");
  React.useEffect(() => {
    let live = true;
    studioApi.overview(module).then((x) => { if (live) setO(x); }).catch((e: Error) => setErr(e.message));
    return () => { live = false; };
  }, [module]);
  const h = o?.headline;

  return (
    <div className="space-y-4" data-testid="intelligence-studio">
      <div className="flex flex-wrap items-center gap-2">
        <BackLink fallback={{ label: "Deal Desk", href: "/deal-desk" }} />
        <h1 className="text-2xl font-semibold text-text-primary">Intelligence Studio</h1>
        <InfoPopover title="Intelligence Studio">
          What CreditProbe has learnt from the bank&apos;s data, its RMs and analysts: the customers it knows and from which
          sources, the documents it has read, the proposals whose house style it writes in, the analysts&apos; rules, the policy
          in force, how often the analysts had to correct the reader, the corrections it absorbed, and every model call it made.
          Each count is read from the store that holds it when the page opens.
        </InfoPopover>
      </div>
      {err ? <p className="text-[12px] text-negative" role="alert">{err}</p> : null}
      <PlainWords lines={o?.plain_words ?? []} loading={!o} testId="studio-words" />
      {!o || !h ? <Skeleton className="h-28 w-full" /> : (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4" data-testid="studio-kpis">
            <Kpi label="Customers known" value={count(h.customers)} testId="studio-kpi-customers" />
            <Kpi label="Documents read" value={count(h.documents_read)} testId="studio-kpi-documents" />
            <Kpi label="Proposals learned" value={count(h.proposals_learned)} testId="studio-kpi-proposals" />
            <Kpi label="Analysts' rules" value={count(h.rules_active)} testId="studio-kpi-rules" />
            <Kpi label="Policy clauses" value={count(h.policy_clauses)} testId="studio-kpi-policy" />
            <Kpi label="Corrections" value={count(h.corrections_absorbed)} testId="studio-kpi-corrections" />
            <Kpi label="Reader kept as read" value={pct(h.reader_accuracy_pct)} sub="types not corrected" testId="studio-kpi-reader" />
            <Kpi label="Model calls" value={count(h.model_calls)} testId="studio-kpi-calls" />
          </div>

          <CustomersSection o={o} />
          <div className="grid gap-4 2xl:grid-cols-2">
            <DocumentsSection o={o} />
            <ProposalsSection o={o} />
          </div>
          <div className="grid gap-4 2xl:grid-cols-2">
            <RulesSection o={o} />
            <PoliciesSection o={o} />
          </div>
          <ReaderSection o={o} />
          <CorrectionsSection o={o} />
          <GovernanceSection o={o} module={module} onModule={(m) => { setO(null); setModule(m); }} />
        </>)}
    </div>
  );
}

function CustomersSection({ o }: { o: Overview }) {
  const c = o.customers;
  return (
    <Section title="Customers known and source coverage" testId="studio-customers"
             info="Every customer in the deal register and in an uploaded customer file, and which of the bank's sources hold data on each: the deal register, core banking (accounts and conduct), bureau, group, past credit decisions, uploaded documents and past proposals.">
      {!c.available ? <Missing part={c} what="The customer register" /> : (
        <div className="grid gap-4 2xl:grid-cols-5">
          <div className="min-w-0 2xl:col-span-2"><Plot testId="studio-chart-coverage" filename="intelligence-studio-coverage" height={Math.max(220, c.coverage.length * 32 + 60)}
                ariaLabel="Share of known customers each source holds data on"
                data={[{ type: "bar", orientation: "h", y: coverageBars(c).map((b) => b.label), x: coverageBars(c).map((b) => b.pct / 100),
                         marker: { color: C.rec }, customdata: coverageBars(c).map((b) => b.customers),
                         hovertemplate: "%{y}: %{customdata} customers (%{x:.1%})<extra></extra>" }]}
                layout={{ showlegend: false, margin: { l: 200, r: 16, t: 8, b: 40 }, yaxis: { autorange: "reversed" },
                          xaxis: { tickformat: ".0%", range: [0, 1], title: { text: "Share of known customers" } } }} /></div>
          <div className="max-h-[320px] min-w-0 overflow-auto 2xl:col-span-3">
            <table className={tableCls} data-testid="studio-customers-table">
              <thead><tr><th className={thCls}>Customer</th>{c.sources.map((s) => <th key={s.key} className={cn(thCls, "text-center")} title={s.label}>{SHORT[s.key] ?? s.key}</th>)}</tr></thead>
              <tbody>{c.rows.map((r) => (
                <tr key={`${r.customer_id}-${r.name}`}>
                  <td className={cn(tdCls, "whitespace-normal")}>{r.name}{!r.existing ? <span className="ml-2 inline-block"><Chip>New to bank</Chip></span> : null}</td>
                  {c.sources.map((s) => <td key={s.key} className={cn(tdCls, "text-center")}>{r.sources[s.key] ? <span className="text-positive" aria-label="held">●</span> : <span className="text-text-muted" aria-label="not held">·</span>}</td>)}
                </tr>))}</tbody>
            </table>
          </div>
        </div>)}
    </Section>
  );
}

function DocumentsSection({ o }: { o: Overview }) {
  const d = o.documents;
  return (
    <Section title="Documents read" testId="studio-documents"
             info="Every document read into a customer file (Data Domains: dd_intake_document), by the type the reader gave it and by how it was read (Word, PDF text, photo or scan through OCR or the model's vision).">
      {!d.available ? <Missing part={d} what="The customer-file documents" /> : !d.total ? <Empty>No customer document has been read yet. Upload a pack in New proposal → Customer documents.</Empty> : (
        <>
          <p className="mb-2 text-[12px] text-text-secondary">{count(d.total)} documents in {count(d.files)} customer files, {count(d.pages)} pages.
            {" "}{d.by_method.map((m) => <span key={m.method} className="ml-1 inline-block"><Chip>{m.method}: {m.n}</Chip></span>)}</p>
          <table className={tableCls} data-testid="studio-documents-table">
            <thead><tr><th className={thCls}>Document type</th><th className={cn(thCls, "text-right")}>Read</th></tr></thead>
            <tbody>{d.by_type.map((t) => <tr key={t.doc_type}><td className={cn(tdCls, "whitespace-normal")}>{t.label}</td><td className={cn(tdCls, "text-right")}>{t.n}</td></tr>)}</tbody>
          </table>
        </>)}
    </Section>
  );
}

function ProposalsSection({ o }: { o: Overview }) {
  const p = o.proposals;
  return (
    <Section title="Proposals learned, per bank and per analyst" testId="studio-proposals"
             info="The proposals whose house style the drafting writes in, per bank (memos, cases, opinions, exemplars and the bank's uploads), and per person: deals as analyst or RM, sections they edited or accepted, rules they wrote and paper edits.">
      {!p.available ? <Missing part={p} what="The house-style corpus" /> : (
        <div className="space-y-3">
          <table className={tableCls} data-testid="studio-banks-table">
            <thead><tr><th className={thCls}>House style</th><th className={cn(thCls, "text-right")}>Proposals</th><th className={thCls}>Kinds</th></tr></thead>
            <tbody>{p.by_bank.map((b) => (
              <tr key={b.bank}><td className={cn(tdCls, "whitespace-normal")}>{b.label}</td><td className={cn(tdCls, "text-right")}>{b.proposals}</td>
                <td className={cn(tdCls, "whitespace-normal")}>{Object.entries(b.kinds).map(([k, n]) => `${k} ${n}`).join(" · ")}</td></tr>))}</tbody>
          </table>
          <div className="max-h-[260px] overflow-auto">
            <table className={tableCls} data-testid="studio-analysts-table">
              <thead><tr><th className={thCls}>Person</th><th className={cn(thCls, "text-right")}>Deals (RM)</th><th className={cn(thCls, "text-right")}>Deals (analyst)</th>
                <th className={cn(thCls, "text-right")}>Edited</th><th className={cn(thCls, "text-right")}>Accepted</th><th className={cn(thCls, "text-right")}>Rules</th><th className={cn(thCls, "text-right")}>Paper edits</th></tr></thead>
              <tbody>{p.by_analyst.map((a) => (
                <tr key={a.person}><td className={cn(tdCls, "whitespace-normal")}>{a.person}</td><td className={cn(tdCls, "text-right")}>{a.deals_as_rm}</td>
                  <td className={cn(tdCls, "text-right")}>{a.deals_as_analyst}</td><td className={cn(tdCls, "text-right")}>{a.sections_edited}</td>
                  <td className={cn(tdCls, "text-right")}>{a.sections_accepted}</td><td className={cn(tdCls, "text-right")}>{a.rules}</td><td className={cn(tdCls, "text-right")}>{a.paper_edits}</td></tr>))}</tbody>
            </table>
          </div>
        </div>)}
    </Section>
  );
}

function RulesSection({ o }: { o: Overview }) {
  const r = o.rules;
  return (
    <Section title="Rules by author" testId="studio-rules"
             info="The analysts' rules in force (saved after an instruction with 'Save this as a rule?', or typed in My rules and Global rules), by author and scope: me, my team, the bank.">
      {!r.available ? <Missing part={r} what="Analysts' rules" /> : !r.total ? <Empty>No rule saved yet.</Empty> : (
        <>
          <table className={tableCls} data-testid="studio-rules-table">
            <thead><tr><th className={thCls}>Author</th><th className={cn(thCls, "text-right")}>Rules</th><th className={cn(thCls, "text-right")}>Me</th>
              <th className={cn(thCls, "text-right")}>Team</th><th className={cn(thCls, "text-right")}>Bank</th><th className={cn(thCls, "text-right")}>From an instruction</th></tr></thead>
            <tbody>{r.by_author.map((a) => (
              <tr key={a.author}><td className={tdCls}>{a.name}</td><td className={cn(tdCls, "text-right")}>{a.rules}</td><td className={cn(tdCls, "text-right")}>{a.me}</td>
                <td className={cn(tdCls, "text-right")}>{a.team}</td><td className={cn(tdCls, "text-right")}>{a.bank}</td><td className={cn(tdCls, "text-right")}>{a.from_instruction}</td></tr>))}</tbody>
          </table>
          <ul className="mt-3 space-y-1 text-[12px] text-text-secondary" data-testid="studio-rules-recent">
            {r.recent.map((x) => <li key={x.id}><span className="text-text-primary">{x.text}</span> · {x.author} · {x.scope}</li>)}
          </ul>
        </>)}
    </Section>
  );
}

function PoliciesSection({ o }: { o: Overview }) {
  const p = o.policies;
  return (
    <Section title="Policies in force" testId="studio-policies"
             info="The policy pack Policy Docs has in force (the bank's credit policy books and the regulations), the policy library, and the regulations, internal policies and gold standards approved in Policy Docs.">
      {!p.available ? <Missing part={p} what="The policy pack" /> : (
        <div className="space-y-3">
          {p.pack_version ? <p className="text-[12px] text-text-secondary">Pack <span className="font-medium text-text-primary">{p.pack_version}</span>: {count(p.clauses)} clauses.</p> : null}
          <table className={tableCls} data-testid="studio-policies-table">
            <thead><tr><th className={thCls}>Policy or regulation</th><th className={thCls}>In force from</th><th className={cn(thCls, "text-right")}>Clauses</th></tr></thead>
            <tbody>
              {(p.books ?? []).map((b) => <tr key={b.book}><td className={cn(tdCls, "whitespace-normal")}>{b.title}<span className="block text-[11px] text-text-muted">{b.approved_by} · next review {b.next_review}</span></td><td className={tdCls}>{b.approved_on}</td><td className={cn(tdCls, "text-right")}>{b.clauses}</td></tr>)}
              {(p.regulatory ?? []).map((r) => <tr key={r.key}><td className={cn(tdCls, "whitespace-normal")}>{r.title}<span className="block text-[11px] text-text-muted">{r.issuer}</span></td><td className={tdCls}>{r.effective_from}</td><td className={cn(tdCls, "text-right")}>{r.clauses}</td></tr>)}
              {p.library.map((l) => <tr key={`${l.policy_id}-${l.version}`}><td className={cn(tdCls, "whitespace-normal")}>{l.title}<span className="block text-[11px] text-text-muted">policy library v{l.version} · {l.status}</span></td><td className={tdCls}>{l.effective_date}</td><td className={cn(tdCls, "text-right")}>{l.clauses}</td></tr>)}
            </tbody>
          </table>
          {p.rulebook && p.rulebook.available === false ? <p className="text-[11px] text-text-muted" data-testid="studio-rulebook-empty">{p.rulebook.reason}</p>
            : <p className="text-[12px] text-text-secondary" data-testid="studio-rulebook">Policy Docs: {count(p.rulebook.assessments)} documents assessed, {count(p.rulebook.approved)} approved, {count(p.rulebook.thresholds)} thresholds applied, {count(p.rulebook.gold)} gold standards, {count(p.rulebook.open_flags)} pending deals flagged.</p>}
        </div>)}
    </Section>
  );
}

function ReaderSection({ o }: { o: Overview }) {
  const r = o.reader;
  return (
    <Section title="Reader accuracy against the analysts' confirmations" testId="studio-reader"
             info="Per week of upload: the documents read, how many document types the analysts had to correct (reader kept as read = not corrected), the cross-document checks (agree, differ, a question for the RM) and, where the model reader reconciles fields with the rule-based reader, the fields confirmed, offered and flagged.">
      {!r.available ? <Missing part={r} what="The customer files" /> : !r.periods.length ? <Empty>No customer document has been read yet.</Empty> : (
        <div className="grid items-start gap-4 lg:grid-cols-5">
          <div className="min-w-0 lg:col-span-2"><Plot testId="studio-chart-reader" filename="intelligence-studio-reader" height={260}
                ariaLabel="Share of document types kept as the reader read them, by week of upload"
                data={[{ type: "scatter", mode: "lines+markers", x: readerSeries(r).x, y: readerSeries(r).accuracy.map((v) => (v == null ? null : v / 100)),
                         line: { color: C.rec, width: 2 }, marker: { size: 8 }, customdata: readerSeries(r).documents,
                         hovertemplate: "%{x}: %{y:.1%} kept as read, %{customdata} documents<extra></extra>" }]}
                layout={{ showlegend: false, margin: { l: 56, r: 16, t: 8, b: 40 }, xaxis: { type: "category" },
                          yaxis: { tickformat: ".0%", range: [0, 1.05], title: { text: "Kept as read" } } }} /></div>
          <div className="min-w-0 overflow-x-auto lg:col-span-3"><table className={tableCls} data-testid="studio-reader-table">
            <thead><tr><th className={thCls}>Week</th><th className={cn(thCls, "text-right")}>Read</th><th className={cn(thCls, "text-right")}>Corrected</th>
              <th className={cn(thCls, "text-right")}>Agree</th><th className={cn(thCls, "text-right")}>Differ</th><th className={cn(thCls, "text-right")}>Ask RM</th>
              {r.field_states ? <><th className={cn(thCls, "text-right")}>Fields confirmed</th><th className={cn(thCls, "text-right")}>Offered</th><th className={cn(thCls, "text-right")}>Flagged</th></> : null}</tr></thead>
            <tbody>{r.periods.map((p) => (
              <tr key={p.period}><td className={tdCls}>{p.period}</td><td className={cn(tdCls, "text-right")}>{p.documents}</td><td className={cn(tdCls, "text-right")}>{p.corrected}</td>
                <td className={cn(tdCls, "text-right")}>{p.recon_agrees}</td><td className={cn(tdCls, "text-right")}>{p.recon_differs}</td><td className={cn(tdCls, "text-right")}>{p.recon_flags}</td>
                {r.field_states ? <><td className={cn(tdCls, "text-right")}>{p.fields_confirmed}</td><td className={cn(tdCls, "text-right")}>{p.fields_offered}</td><td className={cn(tdCls, "text-right")}>{p.fields_flagged}</td></> : null}</tr>))}</tbody>
          </table></div>
        </div>)}
    </Section>
  );
}

function CorrectionsSection({ o }: { o: Overview }) {
  const c = o.corrections;
  return (
    <Section title="Corrections absorbed" testId="studio-corrections"
             info="What people taught the system: house-style sections edited or accepted as written, document types corrected, instructions saved as rules, and paper edits made by instruction.">
      {!c.available ? <Missing part={c} what="Corrections" /> : (
        <div className="grid gap-4 lg:grid-cols-2">
          <table className={tableCls} data-testid="studio-corrections-table">
            <thead><tr><th className={thCls}>Kind</th><th className={cn(thCls, "text-right")}>Absorbed</th></tr></thead>
            <tbody>{c.by_kind.map((k) => <tr key={k.kind}><td className={tdCls}>{k.label}</td><td className={cn(tdCls, "text-right")}>{k.n}</td></tr>)}</tbody>
          </table>
          {c.recent.length ? (
            <ul className="space-y-1 text-[12px] text-text-secondary" data-testid="studio-corrections-recent">
              {c.recent.map((x, i) => <li key={`${x.at}-${i}`}><span className="text-text-primary">{x.what}</span>{x.by ? ` · ${x.by}` : ""}{x.at ? ` · ${x.at.slice(0, 10)}` : ""}</li>)}
            </ul>) : <Empty>No correction yet: edits, accepts, corrected document types and saved rules appear here.</Empty>}
        </div>)}
    </Section>
  );
}

function GovernanceSection({ o, module, onModule }: { o: Overview; module: string; onModule: (m: string) => void }) {
  const g = o.governance;
  return (
    <Section title="Model governance" testId="studio-governance"
             info="Every model call, measured: the stage it served, the model, input, output and cached tokens, and the time it took; per stage and per day. Deal Desk's known questions are answered engine first with one writing call; prompts are cached."
             action={<select value={module} onChange={(e) => onModule(e.target.value)} data-testid="studio-governance-module"
                             className="rounded-md border border-border bg-surface px-2 py-1 text-[12px]">
               <option value="deal_desk">Deal Desk</option><option value="">Every module</option></select>}>
      {!g.available ? <Missing part={g} what="Model telemetry" /> : (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-6" data-testid="studio-governance-kpis">
            <Kpi label="Calls" value={count(g.totals.calls)} sub={`${count(g.totals.turns)} turns`} />
            <Kpi label="Calls per turn" value={g.totals.calls_per_turn ?? "–"} />
            <Kpi label="Input per turn" value={tokens(g.totals.input_per_turn)} sub="tokens, cached included" />
            <Kpi label="Cached tokens" value={tokens(g.totals.cached_tokens)} />
            <Kpi label="Latency p50" value={secs(g.totals.p50_ms)} sub={`p95 ${secs(g.totals.p95_ms)}`} />
            <Kpi label="Models" value={g.totals.models.length} sub={g.totals.models.join(", ") || "–"} />
          </div>
          <div className="flex flex-wrap gap-2"><Chip tone={g.efficiency ? "positive" : "warning"}>{g.efficiency ? "Prompt caching and engine first: on" : "Prompt caching and engine first: off"}</Chip></div>
          <div className="grid gap-4 lg:grid-cols-2">
            <table className={tableCls} data-testid="studio-governance-stages">
              <thead><tr><th className={thCls}>Stage</th><th className={thCls}>Model</th><th className={cn(thCls, "text-right")}>Calls</th>
                <th className={cn(thCls, "text-right")}>Input</th><th className={cn(thCls, "text-right")}>Output</th><th className={cn(thCls, "text-right")}>Cached</th><th className={cn(thCls, "text-right")}>Avg time</th></tr></thead>
              <tbody>{g.by_stage.map((s) => (
                <tr key={`${s.purpose}-${s.model}`}><td className={cn(tdCls, "whitespace-normal")}>{stageLabel(s.purpose || "")}</td><td className={tdCls}>{s.model}</td>
                  <td className={cn(tdCls, "text-right")}>{s.calls}</td><td className={cn(tdCls, "text-right")}>{tokens(s.input_tokens)}</td><td className={cn(tdCls, "text-right")}>{tokens(s.output_tokens)}</td>
                  <td className={cn(tdCls, "text-right")}>{tokens(s.cached_tokens)}</td><td className={cn(tdCls, "text-right")}>{secs(s.avg_ms)}</td></tr>))}</tbody>
            </table>
            {g.by_day.length ? (
              <Plot testId="studio-chart-calls" filename="intelligence-studio-model-calls" height={240} ariaLabel="Model calls per day"
                    data={[{ type: "bar", x: g.by_day.map((d) => d.day), y: g.by_day.map((d) => d.calls), marker: { color: C.rec },
                             customdata: g.by_day.map((d) => [d.input_tokens + d.cached_tokens, d.output_tokens]),
                             hovertemplate: "%{x}: %{y} calls, %{customdata[0]:,} input and %{customdata[1]:,} output tokens<extra></extra>" }]}
                    layout={{ showlegend: false, margin: { l: 48, r: 16, t: 8, b: 40 }, xaxis: { type: "category" }, yaxis: { title: { text: "Calls" } } }} />) : null}
          </div>
        </div>)}
    </Section>
  );
}
