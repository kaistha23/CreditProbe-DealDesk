"use client";

/**
 * PLAN_R12 Session B (I16): the Review step body. `<ReviewStepBody dealId="PRP-B-ASB" />`.
 *
 *   Answer first: the decision line, then 4 tiles (decision and approval, quality score, documents missing, open queries).
 *   The 12 review points (status, summary, counts); click one to filter the findings.
 *   Findings by severity with their evidence, policy clause and source relation; "Query RM" on any finding.
 *   The R12 analyses: adjusted ratios (every adjustment shown), receivables, auditor, bureau and other banks with the reconciliation,
 *   status of earlier conditions, insider and staff links.
 *   The reviewer opinion in the credit voice (credit view only), second-line sign-off, documents and queries.
 *
 * view="prepare" (RM) hides the opinion and the sign-off; the server enforces the same for RM logins.
 */

import * as React from "react";
import { RefreshCw, Send } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { KpiRow } from "@/components/v5/core/kpi-row";
import { useLoad } from "@/lib/v5/dealdesk";
import { cn } from "@/lib/utils";

import { DocumentsPanel } from "../documents-panel";
import { Chip, Empty, SecondaryButton, Section, tableCls, tdCls, thCls } from "../kit";
import { review2Api } from "./api";
import {
  type Analytics, type Finding, POINT_LABEL, POINT_TONE, type Point, type Review2, SEV_LABEL, SEV_TONE, groupBySeverity, lineageText, money, pct,
  queryForFinding, ratioValue, severityLine, underlineParts,
} from "./helpers";
import { QueriesPanel } from "./queries-panel";

const wrap = "whitespace-normal";
const SHORT_DECISION: Record<string, string> = { "Do not approve as proposed": "Do not approve", "Approve with conditions": "With conditions",
  "Approve as proposed": "Approve" };
const ANSWER_TONE = { negative: "border-negative/40 bg-negative-muted text-negative", warning: "border-warning/40 bg-warning-muted text-warning",
  positive: "border-positive/40 bg-positive-muted text-positive" } as const;

// ---------------------------------------------------------------- the 12 points

function Points({ points, picked, onPick }: { points: Point[]; picked: number | null; onPick: (n: number | null) => void }) {
  return (
    <Section title="The 12 review points" testId="review2-points"
             info={<>The credit review in twelve points, from completeness to outputs. Each point is <b>Fail</b> when it has a critical finding,
               <b> Attention</b> with major or minor findings, <b>Pass</b> when checked with nothing found, and <b>Not assessed</b> when the data it needs
               is not available. Click a point to see only its findings.</>}
             action={picked ? <SecondaryButton onClick={() => onPick(null)}>All points</SecondaryButton> : null}>
      <ol className="grid grid-cols-1 gap-1.5 xl:grid-cols-2">
        {points.map((p) => (
          <li key={p.point}>
            <button type="button" onClick={() => onPick(picked === p.point ? null : p.point)} data-testid="review2-point" data-status={p.status}
                    className={cn("flex w-full min-w-0 items-start gap-2 rounded-md border border-border px-2.5 py-2 text-left hover:border-accent",
                                  picked === p.point && "border-accent bg-accent-muted")}>
              <span className="mt-0.5 w-5 shrink-0 text-right text-[12px] font-semibold tabular-nums text-text-muted">{p.point}</span>
              <span className="min-w-0 flex-1">
                <span className="flex flex-wrap items-center gap-1.5">
                  <span className="text-[12px] font-medium text-text-primary">{p.name}</span>
                  <Chip tone={POINT_TONE[p.status]}>{POINT_LABEL[p.status]}</Chip>
                  {p.finding_ids.length ? <span className="text-[11px] text-text-muted">{severityLine(p.counts)}</span> : null}
                </span>
                <span className="mt-0.5 line-clamp-2 block text-[11px] leading-4 text-text-secondary" title={p.summary}>{p.summary}</span>
              </span>
            </button>
          </li>))}
      </ol>
    </Section>
  );
}

// ---------------------------------------------------------------- findings

function FindingRow({ f, ccy, onQuery, canQuery }: { f: Finding; ccy: string; onQuery: (f: Finding) => void; canQuery: boolean }) {
  const [open, setOpen] = React.useState(false);
  void ccy;
  return (
    <li className="rounded-md border border-border px-3 py-2" data-testid="review2-finding" data-code={f.code} data-severity={f.severity}>
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-[12px] font-medium text-text-primary">{f.title}</span>
        {f.status !== "open" ? <Chip tone={f.status === "addressed" ? "positive" : "accent"}>{f.status === "query_sent" ? "Query sent" : f.status[0].toUpperCase() + f.status.slice(1)}</Chip> : null}
        {f.author && f.author !== "B" ? <Chip>Group review</Chip> : null}
        <span className="ml-auto text-[10px] text-text-muted">{f.point}. {f.point_name} · {f.code}{f.rule_ids.length ? ` (${f.rule_ids.join(", ")})` : ""}</span>
      </div>
      <p className="mt-1 whitespace-normal text-[12px] leading-5 text-text-secondary">{f.finding}</p>
      <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-text-muted">
        <span className="min-w-0 truncate">{[f.policy_ref, f.crm_article, f.doa_level ? `Approval: ${f.doa_level}` : null].filter(Boolean).join(" · ")}</span>
        {f.evidence.length ? <button type="button" className="text-accent hover:underline" onClick={() => setOpen((o) => !o)}>{open ? "Hide evidence" : `Evidence (${f.evidence.length})`}</button> : null}
        {canQuery && f.status === "open" && f.severity !== "info" ? (
          <button type="button" className="ml-auto inline-flex items-center gap-1 text-accent hover:underline" onClick={() => onQuery(f)} data-testid="finding-query">
            <Send size={11} aria-hidden />Query RM</button>) : null}
      </div>
      {open ? (
        <ul className="mt-1.5 space-y-1 border-t border-border pt-1.5" data-testid="review2-evidence">
          {f.evidence.map((e, i) => (
            <li key={i} className="text-[11px] leading-4">
              <span className="font-medium text-text-primary">{e.source}: </span><span className="text-text-secondary">{e.text}</span>
              {e.ref ? <span className="block text-[10px] text-text-muted">Source: {lineageText(e.ref)}</span> : null}
            </li>))}
        </ul>) : null}
    </li>
  );
}

function Findings({ r, point, onQuery, canQuery }: { r: Review2; point: number | null; onQuery: (f: Finding) => void; canQuery: boolean }) {
  const list = r.findings.filter((f) => !point || f.point === point);
  const groups = groupBySeverity(list);
  return (
    <Section title={point ? `Findings: ${point}. ${r.points[point - 1]?.name ?? ""}` : "Findings"} testId="review2-findings"
             info={<>Every finding by severity with its evidence, the policy clause and the Data Domains relation each figure comes from. Findings from
               the rule book and the deal analyses are folded together, so one issue appears once (the rule ids are shown in brackets).</>}
             action={<span className="text-[11px] text-text-muted">{severityLine(r.counts)}</span>}>
      {!groups.length ? <Empty>No findings{point ? " on this point" : ""}.</Empty> : (
        <div className="max-h-[560px] space-y-3 overflow-y-auto pr-1">
          {groups.map((g) => (
            <div key={g.severity}>
              <div className="mb-1 flex items-center gap-2"><Chip tone={SEV_TONE[g.severity]}>{SEV_LABEL[g.severity]}</Chip>
                <span className="text-[11px] text-text-muted">{g.items.length}</span></div>
              <ul className="space-y-1.5">{g.items.map((f) => <FindingRow key={f.finding_id} f={f} ccy={r.currency} onQuery={onQuery} canQuery={canQuery} />)}</ul>
            </div>))}
        </div>)}
    </Section>
  );
}

// ---------------------------------------------------------------- the R12 analyses

function AdjustedRatios({ a, ccy }: { a: Analytics["adjusted"]; ccy: string }) {
  return (
    <Section title="Adjusted ratios" testId="review2-adjusted"
             info={<>Net worth, leverage, working capital and the current ratio after netting intangibles, balances due from related parties,
               shareholder accounts and non-core investments. Every adjustment is listed with its amount and what it is netted from. Source: {lineageText(a.source)}.</>}>
      <p className={cn("mb-2 text-[12px] leading-5 text-text-primary", wrap)}>{a.headline}</p>
      {a.rows.length ? (
        <div className="overflow-x-auto">
        <table className={tableCls}>
          <thead><tr><th className={thCls}>FY{a.year ?? ""}</th><th className={cn(thCls, "text-right")}>Reported</th><th className={cn(thCls, "text-right")}>Adjusted</th>
            <th className={cn(thCls, "text-right")}>Change</th><th className={cn(thCls, "text-right")}>Prior year</th></tr></thead>
          <tbody>{a.rows.map((r) => (
            <tr key={r.ratio} data-testid="adj-row">
              <td className={cn(tdCls, "text-text-primary")}>{r.ratio}</td>
              <td className={cn(tdCls, "text-right")}>{ratioValue(r.reported, r.unit, ccy)}</td>
              <td className={cn(tdCls, "text-right font-semibold")}>{ratioValue(r.adjusted, r.unit, ccy)}</td>
              <td className={cn(tdCls, "text-right text-text-secondary")}>{r.change === null ? "—" : ratioValue(r.change, r.unit, ccy)}</td>
              <td className={cn(tdCls, "text-right text-text-muted")}>{ratioValue(r.prior, r.unit, ccy)}</td>
            </tr>))}</tbody>
        </table></div>) : null}
      {a.adjustments.length ? (
        <div className="mt-3">
          <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-[0.06em] text-text-muted">Adjustments</h3>
          <ul className="space-y-0.5" data-testid="adj-items">
            {a.adjustments.map((x) => (
              <li key={x.field} className="flex items-baseline gap-2 text-[12px]">
                <span className="min-w-0 flex-1 text-text-secondary">{x.item} <span className="text-[11px] text-text-muted">(netted from {x.applies_to.join(" and ").replace(/_/g, " ")})</span></span>
                <span className="tabular-nums text-text-primary">{money(-x.amount, ccy)}</span>
              </li>))}
          </ul>
        </div>) : null}
      {a.missing.length ? <p className="mt-2 text-[11px] text-text-muted">Not provided: {a.missing.join(", ")}.</p> : null}
    </Section>
  );
}

function Receivables({ a, ccy }: { a: Analytics["receivables"]; ccy: string }) {
  const c = a.concentration;
  return (
    <Section title="Receivables quality" testId="review2-receivables"
             info={<>Ageing by bucket, concentration in the largest counterparties, retention receivables and balances due from related parties,
               from the notes to the audited accounts. Source: {lineageText(a.source)}.</>}>
      <p className={cn("mb-2 text-[12px] leading-5 text-text-primary", wrap)}>{a.headline}</p>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="min-w-0">
          <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-[0.06em] text-text-muted">Ageing</h3>
          {a.ageing.length ? (
            <table className={tableCls}><tbody>{a.ageing.map((b) => (
              <tr key={b.bucket}><td className={tdCls}>{b.bucket}</td><td className={cn(tdCls, "text-right")}>{money(b.amount, ccy)}</td>
                <td className={cn(tdCls, "text-right text-text-muted")}>{pct(b.share)}</td></tr>))}</tbody></table>
          ) : <p className="text-[12px] text-text-secondary">{a.over_365_share !== null ? `${pct(a.over_365_share)} over 365 days; buckets not provided.` : "Not provided."}</p>}
        </div>
        <div className="min-w-0">
          <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-[0.06em] text-text-muted">Concentration ({c.basis})</h3>
          {c.top2_share !== null ? (
            <ul className="space-y-0.5 text-[12px]">
              {c.names.slice(0, 4).map((n) => <li key={n.name} className="flex gap-2"><span className="min-w-0 flex-1 truncate text-text-secondary">{n.name}</span><span className="tabular-nums">{pct(n.share)}</span></li>)}
              <li className="flex gap-2 border-t border-border pt-0.5 font-medium"><span className="flex-1">Top 2</span><span className="tabular-nums">{pct(c.top2_share)}</span></li>
            </ul>) : <p className="text-[12px] text-text-secondary">Not provided.</p>}
        </div>
        <div className="min-w-0">
          <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-[0.06em] text-text-muted">Retention and related parties</h3>
          <ul className="space-y-0.5 text-[12px] text-text-secondary">
            <li>Retentions: {money(a.retention.receivable, ccy)}{a.retention.overdue ? `, ${money(a.retention.overdue, ccy)} past release` : ""}</li>
            <li>Due from related parties: {money(a.related_party.amount, ccy)}{a.related_party.share_of_current_assets !== null ? ` (${pct(a.related_party.share_of_current_assets)} of current assets)` : ""}</li>
            <li>Cash cycle: {a.cash_cycle_days ? `${a.cash_cycle_days.toFixed(0)} days` : "—"}</li>
          </ul>
        </div>
      </div>
    </Section>
  );
}

function ConductAndProjections({ c, p }: { c: Analytics["conduct"]; p: Analytics["projections"] }) {
  if (!c && !p) return null;
  return (
    <Section title="Conduct and projections" testId="review2-conduct"
             info={<>Turnover through the bank&rsquo;s accounts against the revenue the financials report, and the projections tested against the audited
               track record (growth and margins never reached).</>}>
      {c ? <p className={cn("text-[12px] leading-5 text-text-primary", wrap)} data-testid="conduct-line">{c.headline}</p> : null}
      {p ? <p className={cn("mt-1.5 text-[12px] leading-5 text-text-secondary", wrap)} data-testid="projections-line">{p.headline}</p> : null}
    </Section>
  );
}

function Auditor({ a }: { a: Analytics["auditor"] }) {
  return (
    <Section title="Auditor quality" testId="review2-auditor"
             info={<>The auditor against the bank&rsquo;s approved panel, the audit opinion and, when qualified, the basis of qualification and its amount,
               and whether the statements are standalone, combined or consolidated. Grade A: panel auditor, clean opinion, standalone accounts.</>}>
      <div className="flex flex-wrap items-center gap-1.5">
        {a.grade ? <Chip tone={a.grade === "A" ? "positive" : a.grade === "B" ? "warning" : "negative"}>Grade {a.grade}</Chip> : null}
        {a.opinion ? <Chip tone={a.opinion === "qualified" ? "warning" : a.opinion === "unqualified" ? "positive" : "negative"}>Opinion {a.opinion}</Chip> : null}
        {a.approved_panel === false ? <Chip tone="warning">Not on the approved panel</Chip> : a.approved_panel ? <Chip tone="positive">Approved panel</Chip> : null}
      </div>
      <p className={cn("mt-2 text-[12px] leading-5 text-text-primary", wrap)}>{a.headline}</p>
    </Section>
  );
}

function Bureau({ a, ccy }: { a: Analytics["bureau"]; ccy: string }) {
  return (
    <Section title="Bureau and other banks" testId="review2-bureau"
             info={<>The credit bureau for every group entity and UBO, the central bank risk bureau (CBRBR) and the other-bank matrix (bank × entity),
               with the client&rsquo;s declared limits reconciled against the bureau. A gap of more than 5% is not reconciled.</>}>
      <p className={cn("mb-2 text-[12px] leading-5 text-text-primary", wrap)}>{a.headline}</p>
      <div className="overflow-x-auto">
        <table className={tableCls} data-testid="bureau-entities">
          <thead><tr><th className={thCls}>Entity</th><th className={thCls}>Role</th><th className={cn(thCls, "text-right")}>Outstanding</th>
            <th className={cn(thCls, "text-right")}>Overdue</th><th className={cn(thCls, "text-right")}>Returned cheques</th><th className={thCls}>Classification</th><th className={thCls}>Report</th></tr></thead>
          <tbody>{a.entities.map((e) => (
            <tr key={e.entity + e.role}>
              <td className={cn(tdCls, wrap, "max-w-[220px] text-text-primary")}>{e.entity}</td><td className={tdCls}>{e.role}</td>
              <td className={cn(tdCls, "text-right")}>{money(e.outstanding, ccy)}</td><td className={cn(tdCls, "text-right")}>{money(e.overdue, ccy)}</td>
              <td className={cn(tdCls, "text-right", (e.returned_cheques ?? 0) > 0 && "text-negative")}>{e.returned_cheques ?? "—"}</td>
              <td className={cn(tdCls, ["Loss", "Doubtful", "Substandard"].includes(String(e.classification)) && "font-medium text-negative")}>{e.classification ?? "—"}</td>
              <td className={tdCls}>{e.provided ? "Provided" : <span className="text-warning">Not provided</span>}</td>
            </tr>))}</tbody>
        </table>
      </div>
      {a.reconciliation.length ? (
        <div className="mt-3 overflow-x-auto">
          <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-[0.06em] text-text-muted">Declared against bureau</h3>
          <table className={tableCls} data-testid="bureau-reconciliation">
            <thead><tr><th className={thCls}>Bank</th><th className={thCls}>Entity</th><th className={cn(thCls, "text-right")}>Declared</th>
              <th className={cn(thCls, "text-right")}>Bureau</th><th className={cn(thCls, "text-right")}>Gap</th><th className={thCls}>Status</th><th className={thCls}>Letter</th></tr></thead>
            <tbody>{a.reconciliation.map((r, i) => (
              <tr key={i}>
                <td className={cn(tdCls, wrap)}>{r.bank}</td><td className={cn(tdCls, wrap)}>{r.entity}</td>
                <td className={cn(tdCls, "text-right")}>{money(r.declared, ccy)}</td><td className={cn(tdCls, "text-right")}>{money(r.bureau, ccy)}</td>
                <td className={cn(tdCls, "text-right font-medium", r.status !== "reconciles" && "text-negative")}>{money(r.gap, ccy)}{r.gap_share !== null ? ` (${pct(r.gap_share)})` : ""}</td>
                <td className={tdCls}><Chip tone={r.status === "reconciles" ? "positive" : "negative"}>{r.status}</Chip></td>
                <td className={tdCls}>{r.letter === null ? "—" : r.letter ? "Provided" : "Not provided"}</td>
              </tr>))}</tbody>
          </table>
        </div>) : null}
      {a.matrix.banks.length > 1 ? (
        <div className="mt-3 overflow-x-auto">
          <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-[0.06em] text-text-muted">Other banks × group entity</h3>
          <table className={tableCls} data-testid="bureau-matrix">
            <thead><tr><th className={thCls}>Bank</th>{a.matrix.entities.map((e) => <th key={e} className={cn(thCls, "text-right")}>{e}</th>)}</tr></thead>
            <tbody>{a.matrix.rows.map((r) => (
              <tr key={String(r.bank)}><td className={tdCls}>{String(r.bank)}</td>
                {a.matrix.entities.map((e) => <td key={e} className={cn(tdCls, "text-right")}>{money(r[e] as number | null, ccy)}</td>)}</tr>))}</tbody>
          </table>
        </div>) : null}
    </Section>
  );
}

function TrackAndInsiders({ e, i }: { e: Analytics["earlier"]; i: Analytics["insider"] }) {
  return (
    <Section title="Earlier conditions and insider links" testId="review2-track"
             info={<>The conditions of the previous approval with how far each was met (for example a routing undertaking measured against account
               flows), and every staff, insider or nominee link to a party in the deal.</>}>
      <p className={cn("mb-1.5 text-[12px] leading-5 text-text-primary", wrap)}>{e.headline}</p>
      {e.rows.length ? (
        <ul className="mb-3 space-y-1" data-testid="earlier-conditions">
          {e.rows.map((r) => (
            <li key={r.condition_id} className="flex flex-wrap items-baseline gap-2 text-[12px]">
              <Chip tone={r.status === "complied" ? "positive" : r.status === "complied late" ? "warning" : "negative"}>{r.status}</Chip>
              <span className="min-w-0 flex-1 text-text-secondary">{r.text}</span><span className="tabular-nums text-text-primary">{r.measure}</span>
            </li>))}
        </ul>) : null}
      {e.promises?.length ? (
        <ul className="mb-3 space-y-1" data-testid="promises">
          {e.promises.map((p) => (
            <li key={p.promise_id} className="flex flex-wrap items-baseline gap-2 text-[12px]">
              <Chip tone={p.delivered_share !== null && p.delivered_share < 0.8 ? "negative" : "positive"}>promise {pct(p.delivered_share)}</Chip>
              <span className="min-w-0 flex-1 text-text-secondary">{p.text}</span>
              <span className="tabular-nums text-text-primary">{money(p.delivered, "")} of {money(p.promised, "")}</span>
            </li>))}
        </ul>) : null}
      <p className={cn("text-[12px] leading-5", i.rows.some((r) => r.kind === "staff") ? "font-medium text-negative" : "text-text-secondary", wrap)}
         data-testid="insider-links">{i.headline}</p>
    </Section>
  );
}

// ---------------------------------------------------------------- opinion and sign-off

function OpinionCard({ r }: { r: Review2 }) {
  const op = r.opinion;
  if (!op) return null;
  return (
    <Section title="Reviewer opinion" testId="review2-opinion"
             info={<>The credit division&rsquo;s opinion, written from the findings and analyses: every sentence a fact with its number and source,
               attribution explicit, adjusted figures stated, key concerns underlined. Hidden from the RM&rsquo;s Prepare view.</>}
             action={<span className="text-[11px] text-text-muted">{op.author} · {op.words} words</span>}>
      <ol className="space-y-2">
        {op.paragraphs.map((p, i) => (
          <li key={i} className="text-[12px] leading-5 text-text-primary">
            <span className="font-semibold">{i + 1}. {p.title}. </span>
            {underlineParts(p.text, p.underline).map((s, j) => s.underline ? <u key={j} className="decoration-negative underline-offset-2">{s.text}</u> : <span key={j}>{s.text}</span>)}
          </li>))}
      </ol>
    </Section>
  );
}

const ROLE_LABEL: Record<string, string> = { analyst: "Credit analyst", senior_manager: "Senior manager", vp_credit: "VP Credit", cco: "CCO", cro: "CRO" };

function SignOff({ r, onSigned }: { r: Review2; onSigned: () => void }) {
  const so = r.signoff;
  const [role, setRole] = React.useState("analyst");
  const [decision, setDecision] = React.useState("agree");
  const [note, setNote] = React.useState("");
  const [msg, setMsg] = React.useState<string | null>(null);
  const sign = async () => {
    try { await review2Api.signoff(r.deal_id, role, decision, note); setMsg(`Signed as ${ROLE_LABEL[role]}.`); setNote(""); onSigned(); }
    catch (e) { setMsg(e instanceof Error ? e.message : String(e)); }
  };
  if (!so) return null;
  return (
    <Section title="Sign-off" testId="review2-signoff"
             info={<>Second-line sign-off on the review: analyst, senior manager, VP Credit, CCO and CRO, each with a decision and a note. Every sign-off
               is kept in the audit trail.</>}>
      <ul className="mb-2 flex flex-wrap gap-1.5">
        {so.roles.map((k) => {
          const s = so.latest[k];
          return <Chip key={k} tone={!s ? "neutral" : s.decision === "disagree" ? "negative" : "positive"} title={s ? `${s.by}, ${s.at}${s.note ? `: ${s.note}` : ""}` : undefined}>
            {ROLE_LABEL[k] ?? k}: {s ? s.decision : "pending"}</Chip>;
        })}
      </ul>
      <div className="flex flex-wrap items-center gap-1.5">
        <select aria-label="Role" value={role} onChange={(e) => setRole(e.target.value)} className="h-8 rounded-md border border-border bg-surface px-1.5 text-[12px]">
          {so.roles.map((k) => <option key={k} value={k}>{ROLE_LABEL[k] ?? k}</option>)}</select>
        <select aria-label="Decision" value={decision} onChange={(e) => setDecision(e.target.value)} className="h-8 rounded-md border border-border bg-surface px-1.5 text-[12px]">
          {["agree", "agree with conditions", "disagree"].map((d) => <option key={d} value={d}>{d}</option>)}</select>
        <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Note" aria-label="Note" className="h-8 min-w-0 flex-1 rounded-md border border-border bg-surface px-2 text-[12px]" />
        <SecondaryButton onClick={() => void sign()} data-testid="signoff-submit">Sign</SecondaryButton>
      </div>
      {msg ? <p className="mt-1.5 text-[12px] text-text-secondary" role="status">{msg}</p> : null}
      {so.trail.length ? <p className="mt-1.5 text-[11px] text-text-muted">{so.trail.length} sign-off{so.trail.length === 1 ? "" : "s"} in the trail.</p> : null}
    </Section>
  );
}

// ---------------------------------------------------------------- the step body

export function ReviewStepBody({ dealId, view = "review", showDocuments = true, showQueries = true }: {
  dealId: string; view?: "review" | "prepare"; showDocuments?: boolean; showQueries?: boolean;
}) {
  const [tick, setTick] = React.useState(0);
  const [refresh, setRefresh] = React.useState(false);
  const [point, setPoint] = React.useState<number | null>(null);
  const [prefill, setPrefill] = React.useState<{ question: string; refId?: string; kind?: "finding" | "document" } | null>(null);
  const { data: r, error, loading } = useLoad(() => review2Api.review(dealId, { refresh, view }), `review2:${dealId}:${view}:${tick}`);
  const reload = (full = false) => { setRefresh(full); setTick((t) => t + 1); };
  const queriesRef = React.useRef<HTMLDivElement | null>(null);
  const credit = view === "review";
  const onQuery = (f: Finding) => {
    setPrefill({ question: queryForFinding(f), refId: f.finding_id, kind: "finding" });
    queriesRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  if (loading) return <div className="space-y-3" data-testid="review2-loading"><Skeleton className="h-14 w-full" /><Skeleton className="h-20 w-full" /><Skeleton className="h-80 w-full" /></div>;
  if (error || !r) return <Empty>{error ?? "The review is not available right now."}</Empty>;
  const ccy = r.currency;
  return (
    <div className="space-y-3" data-testid="review2-step">
      <div className={cn("flex flex-wrap items-center gap-3 rounded-lg border px-4 py-3", ANSWER_TONE[r.answer.tone])} data-testid="review2-answer">
        <p className="min-w-0 flex-1 text-[14px] font-semibold leading-5">{r.answer.headline}</p>
        <SecondaryButton onClick={() => reload(true)} aria-label="Run the review again"><RefreshCw size={13} aria-hidden />Re-run</SecondaryButton>
      </div>
      <KpiRow tiles={[
        { label: "Decision", value: SHORT_DECISION[r.answer.decision] ?? r.answer.decision, sub: `Approval: ${r.answer.approval}`, tone: r.answer.tone === "positive" ? "positive" : r.answer.tone === "negative" ? "negative" : "warning",
          info: "The decision follows the findings: any critical finding means do not approve as proposed; major findings mean approve with conditions." },
        { label: "Proposal quality", value: `${r.quality.score}/100`, sub: `Grade ${r.quality.grade}`,
          info: r.quality.parts.map((p) => `${p.part} ${p.points}/${p.weight}: ${p.basis}`).join("; ") },
        { label: "Documents missing", value: String(r.documents.missing_count), sub: `Completeness ${pct(r.documents.completeness)}`,
          tone: r.documents.missing_count ? "warning" : "positive", info: r.documents.headline },
        { label: "Queries open", value: String(r.queries.open), sub: `${r.queries.counts.answered} answered · ${r.queries.counts.closed} closed`, info: r.queries.headline },
      ]} />
      <div className="grid grid-cols-1 gap-3 2xl:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
        <Points points={r.points} picked={point} onPick={setPoint} />
        <Findings r={r} point={point} onQuery={onQuery} canQuery={credit} />
      </div>
      <AdjustedRatios a={r.analytics.adjusted} ccy={ccy} />
      <Receivables a={r.analytics.receivables} ccy={ccy} />
      <Bureau a={r.analytics.bureau} ccy={ccy} />
      <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
        <div className="space-y-3"><Auditor a={r.analytics.auditor} /><ConductAndProjections c={r.analytics.conduct} p={r.analytics.projections} /></div>
        <TrackAndInsiders e={r.analytics.earlier} i={r.analytics.insider} />
      </div>
      {credit ? <OpinionCard r={r} /> : null}
      {showDocuments ? <DocumentsPanel dealId={dealId} editable={credit} canQuery={credit} /> : null}
      {showQueries ? <div ref={queriesRef}><QueriesPanel dealId={dealId} role={credit ? "credit" : "rm"} prefill={prefill} /></div> : null}
      {credit ? <SignOff r={r} onSigned={() => reload(false)} /> : null}
      <p className="text-[11px] text-text-muted" data-testid="review2-basis">{r.basis} Reviewed {r.reviewed_at.slice(0, 16).replace("T", " ")} UTC in {r.seconds.toFixed(1)} s.
        Amounts in {ccy} millions.</p>
    </div>
  );
}
