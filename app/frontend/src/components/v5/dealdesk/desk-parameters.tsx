"use client";

/**
 * The Deal Desk Parameters page (PLAN_R9 Session E, E1; PLAN_R12 Session G, R11_FEEDBACK I2–I6).
 *
 * R9: every parameter prefilled, editable, versioned with an effective date and applied immediately; the (i) on each row
 * says why it is required and where it comes from in the bank; saving shows the proposal verdicts before and after.
 *
 * R12 G: the page is the Parameters & policy tab (`ParametersTab`, exported for Session U's landing page):
 *  - Upload policy: Session O's P6 learner reads the policy; the review shows what it found, what it did not and what is
 *    new; keep or define each value; Approve writes a new parameter version with provenance, Reject changes nothing (I2).
 *  - Policies: the library with version, date, uploader and status, a viewer, Word downloads and the originals (I3).
 *  - Every (i) opens with the value's source: "Set by <Policy> v<n>, clause <x>: '<quote>'" or "Set manually by <owner>
 *    on <date>", then why and where (I4). Download Excel: four sheets in house style (I5). The (i) stays in bounds (I6).
 */

import * as React from "react";
import { Download, FileUp } from "lucide-react";

import { useRouter } from "next/navigation";

import { Skeleton } from "@/components/ui/skeleton";
import { BackButton } from "@/components/v5/core/back-button";
import { cn } from "@/lib/utils";
import { useLoad } from "@/lib/v5/dealdesk";
import {
  type ParamRow, type PolicyRecord, ACCEPT, acceptable, download, groupRows, parseValue, policiesApi, provenanceLine, shortDate,
  sourceChip, valueText,
} from "@/lib/v5/dealdesk-params";
import { type CaseRow, pc, review } from "@/lib/v5/proposal-review";

import { InfoPopover } from "./explain"; // R12 G (I6): the bounded Deal Desk (i)
import { Chip, Kpi, PrimaryButton, SecondaryButton, Section, tableCls, tdCls, thCls } from "./kit";
import { PoliciesTab } from "./parameters/policies-tab";
import { PolicyReview } from "./parameters/policy-review";

type Tab = "parameters" | "policies" | "changes";
const TABS: { key: Tab; label: string }[] = [{ key: "parameters", label: "Parameters" }, { key: "policies", label: "Policies" }, { key: "changes", label: "Change log" }];

function ParamInfo({ row }: { row: ParamRow }) {
  const p = row.provenance;
  return (
    <InfoPopover title={row.label} testId="param-info">
      <p data-testid="param-provenance"><b className="text-text-primary">{p.kind === "policy" ? "Source." : "Set manually."}</b> {provenanceLine(p)}</p>
      {p.kind === "policy" && p.approved_by ? <p>Approved by {p.approved_by} on {shortDate(p.approved_on ?? "")}.</p> : null}
      <p><b className="text-text-primary">Why it is required.</b> {row.why}</p>
      {/* the basis of a value a policy set is that clause, already quoted above */}
      {p.quote && row.where.includes(p.quote.slice(0, 40)) ? null : <p><b className="text-text-primary">Where it comes from in the bank.</b> {row.where}</p>}
      <p className="text-text-muted">Version {row.version}, effective {shortDate(row.effective_from)}, owner {row.owner}.</p>
    </InfoPopover>
  );
}

function Editor({ row, onSaved, onCancel }: { row: ParamRow; onSaved: (m: string) => void; onCancel: () => void }) {
  const unit = row.unit === "ccf" ? "rate" : row.unit;
  const start = row.unit === "ccf" ? valueText((row.value as { regulatory: number }).regulatory, "rate") : valueText(row.value, unit);
  const [text, setText] = React.useState(start);
  const [reason, setReason] = React.useState("");
  const [err, setErr] = React.useState("");
  const save = () => {
    const p = parseValue(text, unit, row.value);
    if (p.error) { setErr(p.error); return; }
    const value = row.unit === "ccf" ? { regulatory: p.value, economic: p.value } : p.value;
    review.setParam(row.table, row.key, value, reason || "Change on the Parameters page").then(
      (x) => onSaved(`${row.label}: version ${x.version}, effective ${shortDate(x.effective_from)}. Applied now.`),
      (e: unknown) => setErr(e instanceof Error ? e.message : String(e)));
  };
  return (
    <tr><td colSpan={6} className="border-b border-border/60 p-3">
      <div className="grid gap-2 md:grid-cols-[1fr_1fr_auto]">
        <textarea rows={Math.min(8, text.split("\n").length + 1)} value={text} onChange={(e) => setText(e.target.value)} aria-label={`New value for ${row.label}`}
                  data-testid="param-edit-value" className="rounded-md border border-border bg-surface p-2 font-mono text-[12px]" />
        <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Reason for the change" aria-label="Reason for the change"
               className="h-8 rounded-md border border-border bg-surface px-2 text-[12px]" />
        <div className="flex gap-2"><SecondaryButton onClick={onCancel}>Cancel</SecondaryButton><PrimaryButton onClick={save} data-testid="param-edit-save">Save and apply</PrimaryButton></div>
      </div>
      {err ? <p role="alert" className="mt-1 text-[12px] text-negative">{err}</p> : null}
    </td></tr>
  );
}

function ParameterTables({ rows, groups, onSaved }: { rows: ParamRow[]; groups: string[]; onSaved: (m: string) => void }) {
  const [edit, setEdit] = React.useState<string | null>(null);
  return (
    <div className="space-y-4">
      {groupRows(rows, groups).map((g) => (
        <Section key={g.group} title={g.group} testId={`params-group-${g.group.toLowerCase().replace(/\W+/g, "-")}`}
                 info="The (i) on each row says what set the value (a policy clause, or a person), why the parameter is required and where it comes from in the bank.">
          <div className="overflow-x-auto">
            <table className={tableCls}>
              <thead><tr>{["Parameter", "Value in force", "Source", "Version", "Effective", ""].map((h) => <th key={h} className={thCls}>{h}</th>)}</tr></thead>
              <tbody>{g.rows.map((row) => {
                const chip = sourceChip(row.provenance);
                const canEdit = row.editable && row.group === groups[0];
                return (
                  <React.Fragment key={row.id}>
                    <tr data-testid="param-row" data-id={row.id} data-source={row.provenance.kind}>
                      <td className={cn(tdCls, "whitespace-normal font-medium")}><span className="inline-flex items-center gap-1">{row.label}<ParamInfo row={row} /></span></td>
                      <td className={cn(tdCls, "max-w-[460px] whitespace-normal text-text-secondary")} data-testid="param-value">{row.display}</td>
                      <td className={tdCls}><Chip tone={chip.tone} title={provenanceLine(row.provenance)} testId="param-source">{chip.label}</Chip></td>
                      <td className={tdCls}>{row.version}</td>
                      <td className={tdCls}>{shortDate(row.effective_from)}</td>
                      <td className={cn(tdCls, "text-right")}>{canEdit ? <SecondaryButton onClick={() => setEdit(edit === row.id ? null : row.id)} data-testid="param-edit">Change</SecondaryButton>
                        : <span className="text-[11px] text-text-muted">{row.owner}</span>}</td>
                    </tr>
                    {edit === row.id ? <Editor row={row} onCancel={() => setEdit(null)} onSaved={(m) => { setEdit(null); onSaved(m); }} /> : null}
                  </React.Fragment>);
              })}</tbody>
            </table>
          </div>
        </Section>))}
    </div>
  );
}

function ChangeLog({ tick }: { tick: number }) {
  const r = useLoad(() => policiesApi.changes(), `changes:${tick}`);
  if (r.error) return <p role="alert" className="text-[12px] text-negative">{r.error}</p>;
  if (!r.data) return <Skeleton className="h-40 w-full" />;
  return (
    <Section title="Change log" testId="params-changes" info="Every value that changed between two versions of a parameter table: when, from and to, who, why, and the policy clause when a policy set it.">
      {!r.data.changes.length ? <p className="text-[12px] text-text-muted">No change since version 1.</p> : (
        <div className="overflow-x-auto"><table className={tableCls}>
          <thead><tr>{["When", "Parameter", "From", "To", "Version", "By", "Source"].map((h) => <th key={h} className={thCls}>{h}</th>)}</tr></thead>
          <tbody>{r.data.changes.map((c, i) => (
            <tr key={`${c.table}-${c.key}-${c.version}-${i}`} data-testid="params-change">
              <td className={tdCls}>{shortDate(c.at)}</td><td className={cn(tdCls, "whitespace-normal font-medium")}>{c.parameter}</td>
              <td className={cn(tdCls, "max-w-[260px] whitespace-normal text-text-secondary")}>{c.from}</td>
              <td className={cn(tdCls, "max-w-[260px] whitespace-normal")}>{c.to}</td>
              <td className={tdCls}>{c.previous} → {c.version}</td><td className={tdCls}>{c.by}</td>
              <td className={cn(tdCls, "whitespace-normal text-text-secondary")}>{c.source}</td></tr>))}</tbody>
        </table></div>)}
    </Section>
  );
}

export function ParametersTab({ standalone = false, onChanged }: { standalone?: boolean; onChanged?: () => void }) {
  const [tick, setTick] = React.useState(0);
  const [tab, setTab] = React.useState<Tab>("parameters");
  const [reviewing, setReviewing] = React.useState<PolicyRecord | null>(null);
  const [msg, setMsg] = React.useState("");
  const [err, setErr] = React.useState("");
  const [busy, setBusy] = React.useState("");
  const file = React.useRef<HTMLInputElement>(null);
  const view = useLoad(() => policiesApi.parameters(), `parameters:${tick}`);
  const lib = useLoad(() => policiesApi.list(), `policies:${tick}`);
  const policies = lib.data?.policies ?? null;
  const pending = (policies ?? []).filter((p) => p.status === "pending");
  const refresh = () => { setTick((t) => t + 1); onChanged?.(); };

  const openReview = (p: PolicyRecord) => {
    setErr("");
    policiesApi.get(p.policy_id, p.version).then((r) => { setReviewing(r); setTab("parameters"); }, (e: unknown) => setErr(e instanceof Error ? e.message : String(e)));
  };
  const learned = (r: PolicyRecord) => { setReviewing(r); setMsg(""); setBusy(""); refresh(); };
  const fail = (e: unknown) => { setErr(e instanceof Error ? e.message : String(e)); setBusy(""); };
  const upload = (f: File | undefined) => {
    if (!f) return;
    setErr(""); setMsg("");
    if (!acceptable(f.name)) { setErr(`${f.name}: upload the policy as .docx, .pdf, .md or .txt.`); return; }
    setBusy(`Reading ${f.name}…`);
    policiesApi.upload(f).then(learned, fail);
  };

  const v = view.data;
  const fromPolicy = v?.from_policy ?? 0;
  const active = v?.active_policies ?? [];
  const answer = v ? `${v.total} parameters in force: ${fromPolicy} set by ${active.length ? active.map((a) => `${a.title} v${a.version}`).join(", ") : "a policy"}, `
    + `${v.total - fromPolicy} set manually.${pending.length ? ` ${pending.length} uploaded polic${pending.length === 1 ? "y awaits" : "ies await"} approval.` : ""}` : "";

  return (
    <div className="space-y-4" data-testid="parameters-tab">
      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-0">
          {standalone ? <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-text-muted">Deal Desk</p> : null}
          <div className="flex items-center gap-2">
            <h2 className={cn("font-semibold text-text-primary", standalone ? "text-2xl" : "text-[16px]")}>Parameters &amp; policy</h2>
            <InfoPopover title="Parameters and policy">Every parameter the Deal Desk uses, with the source that set it. Upload the bank&apos;s credit policy to see which values it sets and which it does not mention; keep or define each one, then approve to create a new version, or reject to change nothing. The library keeps every policy with its Word download.</InfoPopover>
          </div>
        </div>
        <div className="ml-auto flex flex-wrap gap-2">
          <input ref={file} type="file" accept={ACCEPT} className="hidden" data-testid="params-upload-input" onChange={(e) => { upload(e.target.files?.[0]); e.target.value = ""; }} />
          <PrimaryButton onClick={() => file.current?.click()} disabled={Boolean(busy)} data-testid="params-upload"><FileUp size={14} /> Upload policy</PrimaryButton>
          <SecondaryButton onClick={() => { setBusy("Reading the sample policy…"); setErr(""); policiesApi.sample().then(learned, fail); }} disabled={Boolean(busy)}
                           data-testid="params-sample">Use the sample policy</SecondaryButton>
          <SecondaryButton onClick={() => download(policiesApi.excelUrl(), "Deal Desk parameters.xlsx").catch(fail)} data-testid="params-excel">
            <Download size={14} /> Download Excel</SecondaryButton>
        </div>
      </div>

      {view.error ? <p role="alert" className="text-[12px] text-negative">{view.error}</p> : null}
      {!v && !view.error ? <Skeleton className="h-24 w-full" /> : null}
      {v ? (
        <>
          <p className="text-[14px] font-medium text-text-primary" data-testid="params-answer">{answer}</p>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4" data-testid="params-tiles">
            <Kpi label="Parameters" value={String(v.total)} sub={`${v.groups.length} groups · ${v.version === "v1" ? "version 1" : "edited"}`} />
            <Kpi label="Set by a policy" value={String(fromPolicy)} tone={fromPolicy ? "positive" : "neutral"} sub={`${v.total - fromPolicy} set manually`} />
            <Kpi label="Active policy" value={active.length ? `v${active[0].version}` : "None"} sub={active[0]?.title ?? "Upload one to start"} />
            <Kpi label="Awaiting approval" value={String(pending.length)} tone={pending.length ? "negative" : "neutral"} sub={pending[0] ? `${pending[0].title} v${pending[0].version}` : "Nothing to review"} />
          </div>
        </>) : null}
      {busy ? <p className="text-[12px] text-text-secondary" role="status" data-testid="params-busy">{busy}</p> : null}
      {msg ? <p className="text-[12px] text-positive" role="status" data-testid="params-msg">{msg}</p> : null}
      {err ? <p role="alert" className="text-[12px] text-negative" data-testid="params-error">{err}</p> : null}
      {!reviewing && pending.length ? (
        <p className="text-[12px] text-text-secondary">{pending[0].title} v{pending[0].version} awaits approval.{" "}
          <button type="button" className="font-medium text-accent hover:underline" onClick={() => openReview(pending[0])} data-testid="params-open-pending">Review it</button></p>) : null}

      {reviewing ? (
        <div className="space-y-2">
          <PolicyReview key={`${reviewing.policy_id}-${reviewing.version}-${reviewing.status}`} rec={reviewing}
                        onDone={(r, m) => { setMsg(m); setReviewing({ ...reviewing, ...r }); refresh(); }} />
          <div className="flex justify-end"><SecondaryButton onClick={() => setReviewing(null)} data-testid="policy-review-close">Close the review</SecondaryButton></div>
        </div>) : null}

      <div className="flex gap-1 border-b border-border" role="tablist" aria-label="Parameters and policy">
        {TABS.map((t) => (
          <button key={t.key} type="button" role="tab" aria-selected={tab === t.key} onClick={() => setTab(t.key)} data-testid={`params-tab-${t.key}`}
                  className={cn("-mb-px border-b-2 px-3 py-2 text-[13px]", tab === t.key ? "border-accent font-semibold text-text-primary" : "border-transparent text-text-secondary hover:text-text-primary")}>
            {t.label}{t.key === "policies" && policies ? ` · ${policies.length}` : ""}</button>))}
      </div>
      {tab === "parameters" && v ? <ParameterTables rows={v.rows} groups={v.groups} onSaved={(m) => { setMsg(m); refresh(); }} /> : null}
      {tab === "policies" ? <PoliciesTab policies={policies} onReview={openReview} onError={(m) => setErr(m)} /> : null}
      {tab === "changes" ? <ChangeLog tick={tick} /> : null}
    </div>
  );
}


/** The page: back to Settings, the tab, and the proposals' verdicts with these parameters (before and after a change). */
export function DeskParametersPage() {
  const router = useRouter();
  const [tick, setTick] = React.useState(0);
  const cases = useLoad(() => review.cases(), `cases:${tick}`);
  const [before, setBefore] = React.useState<CaseRow[] | null>(null);
  const changed = () => { setBefore(cases.data?.cases ?? null); setTick((t) => t + 1); };
  return (
    <div className="space-y-4" data-testid="desk-params">
      <div className="flex flex-wrap items-center gap-2">
        <BackButton fallback={{ href: "/settings", label: "Settings" }} testId="desk-params-back" />
        <div className="ml-auto flex gap-2">
          <SecondaryButton onClick={() => router.push("/deal-desk/parameters/learn")} data-testid="desk-params-learn">Learn from documents</SecondaryButton>
          <SecondaryButton onClick={() => router.push("/deal-desk/review")} data-testid="desk-params-review">Proposal review</SecondaryButton>
        </div>
      </div>
      <ParametersTab standalone onChanged={changed} />
      <Section title="Deal Desk verdicts with these parameters" testId="desk-params-verdicts"
               info="The proposals under review, recomputed with the parameters in force. After a change, the previous RAROC and verdict are shown beside the new ones.">
        {!cases.data ? <Skeleton className="h-16 w-full" /> : (
          <table className={tableCls}><thead><tr>{["Borrower", "RAROC", "Hurdle", "Verdict", before ? "Before the change" : ""].map((h) => <th key={h} className={thCls}>{h}</th>)}</tr></thead>
            <tbody>{cases.data.cases.map((c) => { const b = before?.find((x) => x.case_id === c.case_id); return (
              <tr key={c.case_id} data-testid="desk-params-verdict" className="cursor-pointer hover:bg-surface-muted" onClick={() => router.push(`/deal-desk/review?case=${c.case_id}`)}>
                <td className={cn(tdCls, "font-medium")}>{c.borrower}</td><td className={cn(tdCls, "text-right")}><b>{pc(c.raroc)}</b></td>
                <td className={cn(tdCls, "text-right")}>{pc(c.hurdle)}</td>
                <td className={tdCls}><Chip tone={c.verdict.startsWith("Clears") ? "positive" : "negative"} testId="desk-params-verdict-chip">{c.verdict}</Chip></td>
                <td className={cn(tdCls, "text-text-secondary")}>{b ? `${pc(b.raroc)} vs ${pc(b.hurdle)}: ${b.verdict}` : ""}</td></tr>); })}</tbody></table>)}
      </Section>
    </div>
  );
}
