"use client";

/**
 * PLAN_R11 R7: the Review step. `ReviewWorkspace({ proposalId })` for a Deal Desk proposal (DD-nn) or a prepared case
 * (PRP-A-GMC, PRP-B-ASB).
 *
 *   Answer first: the decision line, then ≤ 4 tiles (decision, approval level, counter-proposal, precedent).
 *   Left:  the memo, section by section, each line marked supported / contradicted / exception / unverifiable,
 *          with the evidence on hover.
 *   Right: findings by severity, the counter-proposals (priced by the optimiser), the conditions, the precedent.
 *   Committee decision sheet in Word; RM drafting ("Draft proposal": Session P's house-style drafter behind R's "Draft from data",
 *   reconciled by Session M so the deal has one drafting button).
 */

import * as React from "react";
import { Download, FileUp, RefreshCw } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { KpiRow } from "@/components/v5/core/kpi-row";
import { PoweredBy } from "@/components/v5/core/powered-by";
import { cn } from "@/lib/utils";
import { useLoad } from "@/lib/v5/dealdesk";
import {
  CATEGORY_LABEL, type Category, type Check, type MemoLine, SEVERITY_TONE, VERDICT_LABEL, VERDICT_TONE, type Verdict, type Workspace,
  bySeverity, countsLine, markCounts, money, nOfN, pct, pp, reviewApi,
} from "@/lib/v5/dealdesk-review";

import { CURE_TONE, SEVERITY_LABEL as ENGINE_SEV_LABEL, SEVERITY_TONE as ENGINE_SEV_TONE, type EngineFinding, groupFindings } from "@/lib/v5/dealdesk-engines";

import { ConditionsTracker } from "./review-conditions";
import { PrepareProposalButton } from "./proposal/credit-proposal";
import { ProposalDocFromCheck } from "./proposal/rm-brief";
import { Chip, ChartTitle, Empty, PrimaryButton, Section, SecondaryButton, tableCls, tdCls, thCls } from "./kit";

const wrap = "whitespace-normal";
const MARK_BORDER: Record<Verdict, string> = {
  supported: "border-l-positive", contradicted: "border-l-negative", exception: "border-l-warning", unverifiable: "border-l-border",
};
const ANSWER_TONE = { negative: "border-negative/40 bg-negative-muted text-negative", warning: "border-warning/40 bg-warning-muted text-warning",
  positive: "border-positive/40 bg-positive-muted text-positive" } as const;

// ---------------------------------------------------------------- the memo, line by line

function LineRow({ l, active, onPick }: { l: MemoLine; active: boolean; onPick: (l: MemoLine) => void }) {
  const [hover, setHover] = React.useState(false);
  const cells = l.kind === "row" ? l.text.split(" | ") : null;
  return (
    <li id={`memo-${l.line_id}`} data-testid="memo-line" data-mark={l.mark ?? "none"}
        className={cn("relative border-l-2 py-1 pl-2.5 pr-1 text-[12px] leading-5", l.mark ? MARK_BORDER[l.mark] : "border-l-transparent",
                      active && "bg-accent-muted", l.check_ids.length && "cursor-pointer hover:bg-surface-hover")}
        onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)} onFocus={() => setHover(true)} onBlur={() => setHover(false)}
        onClick={() => l.check_ids.length && onPick(l)} tabIndex={l.evidence.length ? 0 : -1}>
      <div className="flex items-start gap-2">
        {cells ? (
          <span className="grid min-w-0 flex-1 gap-x-3" style={{ gridTemplateColumns: `minmax(0,2fr) repeat(${Math.max(cells.length - 1, 1)}, minmax(0,1fr))` }}>
            {cells.map((c, i) => <span key={i} className={cn("min-w-0 truncate", i ? "text-right tabular-nums text-text-primary" : "text-text-secondary")} title={c}>{c}</span>)}
          </span>) : <span className="min-w-0 flex-1 text-text-primary">{l.text}</span>}
        {l.mark === "contradicted" || l.mark === "exception" ? <Chip tone={VERDICT_TONE[l.mark]}>{VERDICT_LABEL[l.mark]}</Chip> : null}
      </div>
      {hover && l.evidence.length ? (
        <div role="tooltip" className="absolute left-4 top-full z-30 mt-0.5 w-[min(420px,90%)] rounded-md border border-border bg-surface-raised p-2.5 shadow-lg" data-testid="memo-evidence">
          {l.evidence.map((e, i) => (
            <div key={i} className={cn(i && "mt-2 border-t border-border pt-2")}>
              <div className="flex items-center gap-1.5"><Chip tone={VERDICT_TONE[e.verdict]}>{VERDICT_LABEL[e.verdict]}</Chip>
                <span className="text-[11px] font-medium text-text-primary">{e.title}</span></div>
              <p className="mt-1 text-[11px] leading-4 text-text-secondary">{e.finding}</p>
              <p className="mt-0.5 text-[10px] text-text-muted">Source: {e.source}</p>
            </div>))}
        </div>) : null}
    </li>
  );
}

function Memo({ w, activeLines, onPick, proposalId }: { w: Workspace; activeLines: Set<string>; onPick: (l: MemoLine) => void; proposalId?: string }) {
  // R14 E (K19 #2): one count source: the legend reads the findings engine's check counts, the same numbers as the Findings header
  const m = w.engine ? w.engine.counts.checks : markCounts(w.memo.sections);
  return (
    <Section title="The memo" testId="review-memo"
             info={<>The proposal as written, read into {w.memo.counts.lines} lines with {w.memo.counts.figures} figures and {w.memo.counts.assertions} assertions.
               Each line is marked by the checks that test it: <b>supported</b> (green), <b>contradicted</b> by the data (red), a policy <b>exception</b>
               (amber), or <b>unverifiable</b> (grey: a claim no data source can test). Hover a line for the evidence; click it to see its findings.</>}
             action={<span className="flex items-center gap-2"><span className="text-[11px] text-text-muted">{w.memo.file}</span>
               {/* R15 b (L11 (2)): the RM's document itself, with the proposal check's comments beside each section */}
               {proposalId ? <ProposalDocFromCheck proposalId={proposalId} testId="review-memo-view-proposal" /> : null}</span>}>
      <div className="mb-2 flex flex-wrap gap-1.5" data-testid="memo-legend">
        {(["contradicted", "exception", "supported", "unverifiable"] as Verdict[]).map((v) =>
          <Chip key={v} tone={VERDICT_TONE[v]}>{VERDICT_LABEL[v]} {m[v]}</Chip>)}
      </div>
      <div className="max-h-[calc(100vh-260px)] min-h-[420px] overflow-y-auto pr-1">
        {w.memo.sections.map((s) => (
          <div key={s.line_id} className="mb-3">
            <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-[0.06em] text-text-muted">{s.title}</h3>
            <ul>{s.lines.map((l) => <LineRow key={l.line_id} l={l} active={activeLines.has(l.line_id)} onPick={onPick} />)}</ul>
          </div>))}
      </div>
    </Section>
  );
}

// ---------------------------------------------------------------- findings

function Finding({ c, active, onPick }: { c: Check; active: boolean; onPick: (c: Check) => void }) {
  return (
    <li data-testid="review-finding" data-rule={c.rule_id} data-severity={c.severity}
        className={cn("cursor-pointer rounded-md border border-border px-3 py-2 hover:border-accent", active && "border-accent bg-accent-muted")}
        onClick={() => onPick(c)}>
      <div className="flex flex-wrap items-center gap-1.5">
        <Chip tone={VERDICT_TONE[c.verdict]}>{VERDICT_LABEL[c.verdict]}</Chip>
        <span className="text-[12px] font-medium text-text-primary">{c.title}</span>
        <span className="ml-auto text-[10px] text-text-muted">{c.rule_id}</span>
      </div>
      <p className="mt-1 text-[12px] leading-5 text-text-secondary">{c.finding}</p>
      <p className="mt-1 text-[11px] text-text-muted">
        {[c.crm_article, c.policy_ref, c.doa ? `Approval: ${c.doa.level}` : null].filter(Boolean).join(" · ")}
      </p>
    </li>
  );
}

function EngineFindingRow({ f }: { f: EngineFinding }) {
  const [open, setOpen] = React.useState(false);
  return (
    <li data-testid="review-finding" data-rule={f.code} data-severity={f.severity} data-category={f.category}
        className={cn("cursor-pointer rounded-md border border-border px-3 py-2 hover:border-accent", open && "border-accent bg-accent-muted")}
        onClick={() => setOpen((o) => !o)}>
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="min-w-0 flex-1 text-[12px] font-medium text-text-primary" data-testid="finding-title">{f.title}</span>
        <Chip tone={CURE_TONE[f.cure.kind] ?? "neutral"}>{f.cure.kind_label}</Chip>
      </div>
      {open ? (
        <div className="mt-1 space-y-1">
          <p className="text-[12px] leading-5 text-text-secondary">{f.text}</p>
          <p className="text-[12px] leading-5 text-text-primary"><b>Cure:</b> {f.cure.text} <span className="text-text-muted">({f.cure.owner}, {f.cure.when})</span></p>
          <p className="text-[11px] text-text-muted">{f.category_label} · {f.source} · {f.source_relation}{f.policy_ref ? ` · ${f.policy_ref}` : ""}</p>
        </div>) : <p className="mt-0.5 text-[11px] text-text-muted">{f.category_label} · {f.source}</p>}
    </li>
  );
}

function EngineFindings({ w }: { w: Workspace }) {
  const e = w.engine!;
  const [cat, setCat] = React.useState<string>("all");
  const groups = groupFindings(e.findings, cat);
  return (
    <Section title="Findings" testId="review-findings"
             info={<>Every finding on this deal, from one engine: the rule book&rsquo;s checks ({w.rules.count} rules, version {w.rules.version}), every
               published review finding (review, group and conduct, financial quality, track record, documents), the capacity check and covenant
               headroom. Titles state the result; each finding carries its cure (structure, condition precedent, covenant, explanation) or
               &ldquo;not curable by structure&rdquo;. The same counts feed the memo legend and the decision. Click a finding for its evidence.</>}
             action={<span className="text-[11px] text-text-muted" data-testid="findings-counts">{e.counts.line}</span>}>
      <div className="mb-2 flex flex-wrap gap-1.5" data-testid="findings-filter">
        {e.chips.map((c) => (
          <button key={c.key} type="button" onClick={() => setCat(c.key)} data-testid={`findings-chip-${c.key}`}
                  className={cn("h-6 rounded-full border px-2 text-[11px]",
                                cat === c.key ? "border-accent bg-accent-muted text-accent" : "border-border text-text-secondary hover:border-accent")}>
            {c.label} {c.count}</button>))}
      </div>
      {!groups.length ? <Empty>No open findings.</Empty> : (
        <div className="max-h-[520px] space-y-3 overflow-y-auto pr-1">
          {groups.map((g) => (
            <div key={g.severity}>
              <div className="mb-1 flex items-center gap-2"><Chip tone={ENGINE_SEV_TONE[g.severity]}>{ENGINE_SEV_LABEL[g.severity]}</Chip>
                <span className="text-[11px] text-text-muted">{g.items.length}</span></div>
              <ul className="space-y-1.5">{g.items.map((f) => <EngineFindingRow key={f.id} f={f} />)}</ul>
            </div>))}
        </div>)}
      <p className="mt-2 text-[11px] text-text-muted" data-testid="findings-checks-line">Rule checks: {e.counts.checks_line}.</p>
    </Section>
  );
}

function Findings({ w, picked, onPick }: { w: Workspace; picked: string | null; onPick: (c: Check) => void }) {
  const [cat, setCat] = React.useState<Category | "all">("all");
  const list = w.findings.filter((f) => cat === "all" || f.category === cat);
  const groups = bySeverity(list);
  return (
    <Section title="Findings" testId="review-findings"
             info={<>Every check is a rule in the bank&rsquo;s rule book ({w.rules.count} rules, version {w.rules.version}): what it tests, the inputs, the
               threshold, the policy clause, the CBUAE CRM article and the Delegation of Authority level it needs. Findings are the checks the data
               contradicts or that need a policy exception, by severity. Click one to see its lines in the memo.</>}
             action={<span className="text-[11px] text-text-muted">{w.verdicts.supported} supported · {w.verdicts.unverifiable} unverifiable</span>}>
      <div className="mb-2 flex flex-wrap gap-1.5" data-testid="findings-filter">
        {(["all", "data", "consistency", "policy", "connected"] as const).map((k) => {
          const n = k === "all" ? w.findings.length : w.findings.filter((f) => f.category === k).length;
          return <button key={k} type="button" onClick={() => setCat(k)} disabled={!n && k !== "all"}
                         className={cn("h-6 rounded-full border px-2 text-[11px] disabled:opacity-40",
                                       cat === k ? "border-accent bg-accent-muted text-accent" : "border-border text-text-secondary hover:border-accent")}>
            {k === "all" ? "All" : CATEGORY_LABEL[k]} {n}</button>;
        })}
      </div>
      {!groups.length ? <Empty>No findings: every check is supported by the data.</Empty> : (
        <div className="max-h-[440px] space-y-3 overflow-y-auto pr-1">
          {groups.map((g) => (
            <div key={g.severity}>
              <div className="mb-1 flex items-center gap-2"><Chip tone={SEVERITY_TONE[g.severity]}>{g.severity[0].toUpperCase() + g.severity.slice(1)}</Chip>
                <span className="text-[11px] text-text-muted">{g.items.length}</span></div>
              <ul className="space-y-1.5">{g.items.map((c) => <Finding key={c.check_id} c={c} active={picked === c.check_id} onPick={onPick} />)}</ul>
            </div>))}
        </div>)}
    </Section>
  );
}

// ---------------------------------------------------------------- counter-proposals, precedent

function Counters({ w }: { w: Workspace }) {
  const cps = w.counter.counter_proposals;
  const ask = w.counter.ask;
  const ccy = w.subject.currency;
  const [open, setOpen] = React.useState<string | null>(cps[0]?.id ?? null);
  return (
    <Section title="Counter-proposals" testId="review-counters"
             info={<>The levers the findings imply (tranching, a cap, cash margin, dropping a line, routing, conditions precedent) combined into packages
               and priced by the Deal Desk optimiser with the package&rsquo;s terms held: the closest structure that clears every hard limit and the
               hurdle. RAROC is lifetime RAROC; SVA and Day-1 ECL in {ccy} m.{w.subject.kind === "case" ? " For a prepared case the optimiser is tried first; where the book's single-obligor limit blocks every structure, the package is priced by the engine at its terms with pricing at the hurdle breakeven." : ""}</>}>
      {!cps.length ? <Empty>No counter-proposal needed: approve as proposed.</Empty> : (
        <div className="overflow-x-auto"><table className={tableCls} data-testid="counter-table">
          <thead><tr>{["", "Amount", "RAROC", "SVA", "Day-1 ECL", "Approval"].map((h) => <th key={h} className={cn(thCls, h && h !== "Approval" && "text-right")}>{h}</th>)}</tr></thead>
          <tbody>
            {ask ? <tr className="text-text-muted"><td className={tdCls}>As proposed</td><td className={cn(tdCls, "text-right")}>{money(ask.amount, ccy)}</td>
              <td className={cn(tdCls, "text-right")}>{pct(ask.raroc)}</td><td className={cn(tdCls, "text-right")}>{money(ask.sva, ccy)}</td>
              <td className={cn(tdCls, "text-right")}>{money(ask.ecl_day1, ccy)}</td><td className={cn(tdCls, "max-w-[110px] truncate")} title={w.doa.level}>{w.doa.level}</td></tr> : null}
            {cps.map((c) => (
              <React.Fragment key={c.id}>
                <tr className="cursor-pointer hover:bg-surface-hover" onClick={() => setOpen(open === c.id ? null : c.id)} data-testid="counter-row">
                  <td className={cn(tdCls, wrap, "min-w-[150px] font-medium text-text-primary")}>{c.title}</td>
                  <td className={cn(tdCls, "text-right")}>{money(c.amount, ccy)}</td>
                  <td className={cn(tdCls, "text-right font-semibold", c.clears_hurdle ? "text-positive" : "text-negative")} title={`Hurdle ${pct(c.hurdle)}`}>
                    {pct(c.raroc)} <span className="font-normal text-text-muted">({pp(c.vs_ask.raroc)})</span></td>
                  <td className={cn(tdCls, "text-right")}>{money(c.sva, ccy)}</td>
                  <td className={cn(tdCls, "text-right")}>{money(c.ecl_day1, ccy)}</td>
                  <td className={cn(tdCls, "max-w-[110px] truncate")} title={c.approval ?? ""}>{c.approval ?? "–"}</td>
                </tr>
                {open === c.id ? (
                  <tr><td colSpan={6} className="border-b border-border/60 px-2 pb-3 pt-1">
                    <div className="grid gap-3 md:grid-cols-2">
                      <div><ChartTitle title="Terms" info="What changes against the proposal, and the pricing the engine needs to clear the hurdle." />
                        <ul className="list-disc pl-4 text-[12px] text-text-secondary">{c.terms.map((t) => <li key={t}>{t}</li>)}</ul></div>
                      <div><ChartTitle title="Conditions precedent" info="From the findings: to be met before the limits are made available." />
                        <ul className="list-disc pl-4 text-[12px] text-text-secondary">{c.conditions_precedent.map((t) => <li key={t}>{t}</li>)}</ul></div>
                    </div>
                    {c.note ? <p className="mt-2 text-[11px] text-warning" data-testid="counter-note">{c.note}</p> : null}
                    {c.hard_breaches.length ? <p className="mt-2 text-[11px] text-text-muted">Limit exceptions still needing approval: {c.hard_breaches.map((b) => b.replace(/_/g, " ")).join(", ")}.</p> : null}
                    {c.forward_risk ? <p className="mt-1 text-[11px] text-text-muted" data-testid="counter-forward">Forward risk: P(Stage 2) next quarter{" "}
                      <b>{pct(c.forward_risk.p_stage2_next_q)}</b> · P(30+ DPD) <b>{pct(c.forward_risk.p_dpd30_next_q)}</b> · expected ECL in 4 quarters{" "}
                      <b>{money(c.forward_risk.ecl_q4, "SAR")}</b></p> : null}
                  </td></tr>) : null}
              </React.Fragment>))}
          </tbody>
        </table></div>)}
      {(() => {  // R14 E: the open counter-proposal's cures, below the table so they wrap at every width
        const c = cps.find((x) => x.id === open);
        return c?.cures?.length ? (
          <div className="mt-3" data-testid="counter-cures">
            <ChartTitle title={`${c.id}: each critical and major finding, and how it is cured`}
                        info="From the findings engine: the cure for every open critical and major finding, or 'not curable by structure' where only the committee can accept or decline the risk." />
            <ul className="space-y-1.5">{c.cures.map((x) => (
              <li key={x.finding_id} data-testid="counter-cure" data-curable={x.curable ? "1" : "0"}
                  className="rounded-md border border-border px-2.5 py-1.5">
                <div className="flex flex-wrap items-start gap-2">
                  <span className="min-w-0 flex-1 text-[12px] font-medium text-text-primary">{x.title}</span>
                  <Chip tone={CURE_TONE[x.cure_kind] ?? "neutral"}>{x.cure_kind_label}</Chip>
                </div>
                <p className="mt-0.5 text-[12px] leading-5 text-text-secondary">{x.cure} <span className="text-text-muted">({x.owner}, {x.when})</span></p>
              </li>))}</ul>
          </div>) : null;
      })()}
    </Section>
  );
}

function Precedent({ w }: { w: Workspace }) {
  const p = w.precedent;
  return (
    <Section title="Precedent" testId="review-precedent"
             info={<>Similar borrowers in the corporate book: {p.sector}, rating within 2 notches of {p.rating}, similar size and the features the book
               holds{p.features_not_in_book.length ? ` (not testable in the book: ${p.features_not_in_book.map((f) => f.feature.toLowerCase()).join(", ")})` : ""}.
               Of those in Stage 1 and under 30 days past due at the anchor quarter, how many reached Stage 2, or 30+ days past due, in the following
               quarters, against the whole book.</>}>
      <p className="mb-2 text-[12px] text-text-primary" data-testid="precedent-line">{p.line}</p>
      <table className={tableCls} data-testid="precedent-table">
        <thead><tr>{["Horizon", "Match", "Stage 2", "30+ DPD", "Book"].map((h) => <th key={h} className={thCls}>{h}</th>)}</tr></thead>
        <tbody>{p.horizons.map((h) => (
          <tr key={h.quarters}><td className={tdCls} title={h.window}>{h.quarters} quarters</td>
            <td className={cn(tdCls, "max-w-[160px] truncate text-text-secondary")} title={h.match}>{h.match}</td>
            <td className={tdCls}><b>{nOfN(h.stage2, h.N)}</b></td><td className={tdCls}>{nOfN(h.dpd30, h.N)}</td>
            <td className={tdCls}>{pct(h.book_stage2_rate, 0)}</td></tr>))}</tbody>
      </table>
    </Section>
  );
}

// ---------------------------------------------------------------- the workspace

export function ReviewWorkspace({ proposalId }: { proposalId: string }) {
  const [rev, setRev] = React.useState(0);
  const [uploaded, setUploaded] = React.useState<Workspace | null>(null);
  const [upErr, setUpErr] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const r = useLoad(() => reviewApi.workspace(proposalId, rev > 0), `review-ws:${proposalId}:${rev}`);
  const onMemo = (f: File | undefined) => {
    if (!f) return;
    setBusy(true); setUpErr("");
    reviewApi.uploadMemo(proposalId, f).then((w) => { setBusy(false); setUploaded(w); },
      (e: unknown) => { setBusy(false); setUpErr(e instanceof Error ? e.message : String(e)); });
  };
  const [picked, setPicked] = React.useState<string | null>(null);
  const [lines, setLines] = React.useState<Set<string>>(new Set());

  const data = uploaded ?? r.data;
  if (r.error && !uploaded) return <p role="alert" className="text-[12px] text-negative" data-testid="review-ws-error">{r.error}</p>;
  if (!data) return (
    <div className="space-y-3" data-testid="review-ws-loading"><Skeleton className="h-12 w-full" /><Skeleton className="h-20 w-full" />
      <div className="grid gap-3 lg:grid-cols-2"><Skeleton className="h-96 w-full" /><Skeleton className="h-96 w-full" /></div></div>);
  const w = data;
  const a = w.answer;
  const ccy = w.subject.currency;
  const cp = w.counter.counter_proposals[0];
  const h4 = w.precedent.horizons.find((h) => h.quarters === 4);
  const pickCheck = (c: Check) => {
    setPicked(c.check_id);
    setLines(new Set(c.line_ids));
    if (c.line_ids[0]) document.getElementById(`memo-${c.line_ids[0]}`)?.scrollIntoView({ block: "center", behavior: "smooth" });
  };
  const pickLine = (l: MemoLine) => {
    setLines(new Set([l.line_id]));
    setPicked(l.check_ids[0] ?? null);
    document.querySelector(`[data-rule="${(l.check_ids[0] ?? "").split(":")[0]}"]`)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  };

  return (
    <div className="space-y-3" data-testid="review-workspace">
      <div className={cn("flex flex-wrap items-center gap-3 rounded-lg border px-4 py-3", ANSWER_TONE[a.tone])} data-testid="review-answer">
        <div className="min-w-0 flex-1">
          <p className="text-[15px] font-semibold leading-6" data-testid="review-answer-headline">{a.headline.replace(/\.$/, "")}.</p>
          {/* R15 b (L13 (1)): the same one sentence as the deal page's tiles: price against the verdict */}
          {w.engine?.verdict.story ? <p className="mt-0.5 text-[12.5px] leading-5 opacity-90" data-testid="review-answer-story">{w.engine.verdict.story}</p> : null}
        </div>
        <div className="flex shrink-0 gap-2">
          <SecondaryButton onClick={() => { setUploaded(null); setRev((n) => n + 1); }} data-testid="review-rerun" title="Re-run the review on the latest data"><RefreshCw size={13} /> Re-run</SecondaryButton>
          <label className="inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-md border border-border bg-surface px-3 text-[12px] text-text-secondary hover:bg-surface-hover"
                 data-testid="review-upload-memo" title="Review a credit memo (.docx) against this proposal's data">
            <FileUp size={13} /> {busy ? "Reading…" : "Upload memo"}
            <input type="file" accept=".docx" className="hidden" onChange={(e) => onMemo(e.target.files?.[0])} /></label>
          {/* R15 b (L12): Draft proposal is the deterministic bank-form writer, the same as Recommendation → Prepare the credit proposal */}
          <PrepareProposalButton proposalId={proposalId} label="Draft proposal" primary={false} testId="review-draft-toggle" />
          <a href={reviewApi.sheetUrl(proposalId)} data-testid="review-sheet-docx"><PrimaryButton className="h-8 px-3 text-[12px]"><Download size={13} /> Committee sheet (Word)</PrimaryButton></a>
        </div>
      </div>

      {upErr ? <p role="alert" className="text-[12px] text-negative">{upErr}</p> : null}
      <KpiRow testId="review-tiles" tiles={[
        { label: "Recommended decision", value: <span className="text-[16px]" title={a.decision}>{a.decision}</span>,
          sub: w.engine ? w.engine.counts.line : countsLine(a.counts),
          tone: a.tone === "positive" ? "positive" : a.tone === "warning" ? "warning" : "negative", testId: "review-tile-decision",
          info: "Any critical finding: do not approve as proposed. Major findings only: approve with conditions. None: approve as proposed." },
        { label: "Approval level", value: <span className="text-[16px]" title={w.doa.level}>{w.doa.level}</span>, sub: w.doa.binding.detail,
          info: <>One approval-authority engine (Delegation of Authority): the highest level any of exposure after the deal (SAR {w.doa.exposure_sar_mn.toFixed(1)}m),
            rating, the number of exceptions, a policy exception, a hard limit or SIMAH needs.
            {w.doa.reasons?.length ? <span className="mt-1 block">{w.doa.reasons.map((r) => `${r.detail} → ${r.level ?? `rank ${r.rank}`}`).join(" · ")}</span> : null}</>,
          testId: "review-tile-doa" },
        cp ? { label: "Counter-proposal", value: pct(cp.raroc), sub: `${cp.title} · SVA ${money(cp.sva, ccy)}`, tone: cp.clears_hurdle ? "positive" : "negative",
               info: `Lifetime RAROC of the first counter-proposal against a ${pct(cp.hurdle)} hurdle, priced by the Deal Desk optimiser.`, testId: "review-tile-counter" }
           : { label: "Counter-proposal", value: "None needed", sub: "Approve as proposed", tone: "positive", testId: "review-tile-counter" },
        h4 ? { label: "Precedent, Stage 2 in 4 quarters", value: pct(h4.stage2_rate, 0), sub: `${h4.stage2} of ${h4.N} similar · book ${pct(h4.book_stage2_rate, 0)}`,
               tone: (h4.stage2_rate ?? 0) > (h4.book_stage2_rate ?? 0) ? "warning" : "neutral",
               info: "Similar borrowers in the book that reached Stage 2 within 4 quarters, against the whole book.", testId: "review-tile-precedent" }
           : { label: "Precedent", value: "–", sub: "No similar borrowers" },
      ]} />


      <div className="grid gap-3 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
        <div className="min-w-0 lg:sticky lg:top-2 lg:self-start"><Memo w={w} activeLines={lines} onPick={pickLine} proposalId={proposalId} /></div>
        <div className="min-w-0 space-y-3">
          {w.engine ? <EngineFindings w={w} /> : <Findings w={w} picked={picked} onPick={pickCheck} />}
          <Counters w={w} />
          <ConditionsTracker dealId={proposalId} compact />
          <Precedent w={w} />
        </div>
      </div>
      <PoweredBy pack="P7" rule="P7-PRO-01" article={w.powered_by.rules.join(", ") || "CBUAE CRM"} confidence="high" testId="review-ws-powered-by" />
    </div>
  );
}
