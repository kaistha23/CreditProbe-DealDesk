"use client";

/**
 * PLAN_R12 Session G (I2): the review of an uploaded policy. One row per parameter: found in the policy (the policy's
 * value, the clause and its quote, the change against the value in force), not in the policy (keep the value in force,
 * or define one now), or new in the policy (leave out, add as a parameter or as a review rule). Nothing changes until
 * Approve, which writes one new version per changed table with provenance; Reject changes nothing.
 */

import * as React from "react";

import { cn } from "@/lib/utils";
import {
  type Action, type Choice, type PolicyRecord, type ReviewRow, type ReviewStatus, ACTION_LABEL, STATUS_LABEL, approvePreview, changeTone,
  changeWord, countBy, decisionBody, isPercentUnit, needsValue, policiesApi, shortDate, valueShape, valueText, valueUnit,
} from "@/lib/v5/dealdesk-params";

import { InfoPopover } from "../explain";
import { Chip, PrimaryButton, Section, SecondaryButton, tableCls, tdCls, thCls } from "../kit";

const FILTERS: ReviewStatus[] = ["found", "new", "not_found"];

function unitHint(unit: string): string {
  if (isPercentUnit(unit)) return "in %";
  if (unit === "x") return "times";
  if (unit === "sar m") return "SAR m";
  if (unit.endsWith("_map")) return "one “name: value” per line";
  return "";
}

function DecisionCell({ row, choice, onChange, error }: { row: ReviewRow; choice: Choice | undefined; onChange: (c: Choice) => void; error?: string }) {
  const action = choice?.action ?? row.decision;
  const unit = valueUnit(row);
  const shape = valueShape(row);
  const isMap = shape !== null && typeof shape === "object" && !Array.isArray(shape);
  const start = row.status === "found" ? valueText(row.proposals[0]?.proposed, unit) : valueText(row.value, unit);
  return (
    <div className="min-w-[200px] space-y-1">
      <select value={action} onChange={(e) => onChange({ action: e.target.value as Action, text: choice?.text ?? start })}
              aria-label={`Decision for ${row.label}`} data-testid="policy-review-decision"
              className="h-8 w-full rounded-md border border-border bg-surface px-2 text-[12px] text-text-primary">
        {row.options.map((o) => <option key={o} value={o}>{ACTION_LABEL[o]}</option>)}
      </select>
      {needsValue(action) ? (
        <div>
          {isMap ? (
            <textarea rows={3} value={choice?.text ?? ""} onChange={(e) => onChange({ action, text: e.target.value })} aria-label={`Value for ${row.label}`}
                      data-testid="policy-review-value" className="w-full rounded-md border border-border bg-surface p-1.5 font-mono text-[12px]" />
          ) : (
            <input value={choice?.text ?? ""} onChange={(e) => onChange({ action, text: e.target.value })} aria-label={`Value for ${row.label}`}
                   data-testid="policy-review-value" className="h-8 w-full rounded-md border border-border bg-surface px-2 text-[12px] tabular-nums" />)}
          {unitHint(isMap ? `${unit}_map` : unit) ? <p className="text-[11px] text-text-muted">{unitHint(isMap ? `${unit}_map` : unit)}</p> : null}
        </div>) : null}
      {error ? <p role="alert" className="text-[11px] text-negative">{error}</p> : null}
    </div>
  );
}

function PolicyCell({ row }: { row: ReviewRow }) {
  if (row.status === "not_found") return <span className="text-text-muted">Not in the policy</span>;
  if (row.status === "new") {
    return (
      <span className="inline-flex items-center gap-1 whitespace-normal">
        <b className="font-semibold text-text-primary">{row.display}</b>
        <span className="text-text-muted">clause {row.clause}</span>
        <InfoPopover title={`Clause ${row.clause}`}><p>&lsquo;{row.quote}&rsquo;</p>
          <p>{row.has_rule ? "The review can check this as a rule." : "No Deal Desk parameter holds it yet."}</p></InfoPopover>
      </span>);
  }
  return (
    <div className="space-y-0.5 whitespace-normal">
      {row.proposals.map((p) => (
        <span key={p.item_id} className="flex flex-wrap items-center gap-1">
          <b className="font-semibold text-text-primary">{p.subfield ? `${p.subfield}: ` : ""}{p.display}</b>
          <span className="text-text-muted">clause {p.clause}</span>
          <InfoPopover title={`Clause ${p.clause}`}>
            <p>&lsquo;{p.quote}&rsquo;</p>
            {p.conversion ? <p>{p.conversion}</p> : null}
            {p.conflict ? <p className="text-negative">{p.conflict.message}</p> : null}
          </InfoPopover>
        </span>))}
    </div>
  );
}

export function PolicyReview({ rec, onDone }: { rec: PolicyRecord; onDone: (r: PolicyRecord, message: string) => void }) {
  const rows = React.useMemo(() => rec.review ?? [], [rec.review]);
  const counts = countBy(rows);
  const [filter, setFilter] = React.useState<ReviewStatus>("found");
  const [choices, setChoices] = React.useState<Record<string, Choice>>({});
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const [busy, setBusy] = React.useState(false);
  const [err, setErr] = React.useState("");
  const [note, setNote] = React.useState("");
  const pending = rec.status === "pending";
  const shown = rows.filter((r) => r.status === filter);

  const approve = () => {
    const { decisions, errors: e } = decisionBody(rows, choices);
    setErrors(e);
    if (Object.keys(e).length) { setErr("Some values need a correction before approving."); return; }
    setBusy(true); setErr("");
    policiesApi.approve(rec.policy_id, rec.version, decisions).then((x) => {
      const made = x.policy.param_versions.map((v) => `${v.table.replace(/_/g, " ")} ${v.version}`).join(", ");
      onDone(x.policy, `${rec.title} v${rec.version} approved. ${made ? `New versions: ${made}, effective ${shortDate(x.policy.decided_at)}.` : "No value changed."}`);
    }, (e2: unknown) => setErr(e2 instanceof Error ? e2.message : String(e2))).finally(() => setBusy(false));
  };
  const reject = () => {
    setBusy(true); setErr("");
    policiesApi.reject(rec.policy_id, rec.version, note).then((x) => onDone(x.policy, `${rec.title} v${rec.version} rejected. No parameter changed.`),
      (e2: unknown) => setErr(e2 instanceof Error ? e2.message : String(e2))).finally(() => setBusy(false));
  };

  return (
    <Section title={`Review: ${rec.title} v${rec.version}`} testId="policy-review"
             info="What the policy sets, what it does not mention and what it adds. Choose for each row; nothing changes until you approve. Approving writes one new version of each changed parameter table, with the policy, version and clause as the source of every value it sets.">
      <p className="text-[14px] font-medium text-text-primary" data-testid="policy-review-answer">{rec.summary.text}</p>
      <p className="mt-1 text-[12px] text-text-secondary">
        {rec.issuer ? `${rec.issuer} · ` : ""}{rec.document_version ? `document version ${rec.document_version} · ` : ""}effective {shortDate(rec.effective_date)}
        {" · "}{rec.clauses} clauses read{rec.conflicts ? ` · ${rec.conflicts} clauses weaker than the CBUAE CRM Standards (see Learn from documents)` : ""}
        {" · "}uploaded by {rec.uploaded_by || "–"} on {shortDate(rec.uploaded_at)}</p>

      <div className="mt-3 flex flex-wrap items-center gap-2" role="tablist" aria-label="Rows">
        {FILTERS.map((f) => (
          <button key={f} type="button" role="tab" aria-selected={filter === f} onClick={() => setFilter(f)} data-testid={`policy-review-filter-${f}`}
                  className={cn("h-7 rounded-full border px-3 text-[12px]", filter === f ? "border-accent bg-accent-muted text-accent" : "border-border text-text-secondary hover:border-accent")}>
            {STATUS_LABEL[f]} · {counts[f]}</button>))}
      </div>

      <div className="mt-3 overflow-x-auto">
        <table className={tableCls} data-testid="policy-review-table">
          <thead><tr>{["Parameter", "In force", "In the policy", "Change", pending ? "Decision" : "Decided"].map((h) => <th key={h} className={thCls}>{h}</th>)}</tr></thead>
          <tbody>
            {shown.map((r) => (
              <tr key={r.id} data-testid="policy-review-row" data-status={r.status} data-id={r.id} className="align-top">
                <td className={cn(tdCls, "whitespace-normal font-medium")}><span className="block min-w-[160px]">{r.label}</span>
                  <span className="text-[11px] font-normal text-text-muted">{r.group}</span></td>
                <td className={cn(tdCls, "max-w-[280px] whitespace-normal text-text-secondary")}>{r.status === "new" ? "–" : r.display}
                  {r.version ? <span className="block text-[11px] text-text-muted">{r.version} · {shortDate(r.effective_from)}</span> : null}</td>
                <td className={cn(tdCls, "max-w-[320px]")}><PolicyCell row={r} /></td>
                <td className={tdCls}>{r.change ? <Chip tone={changeTone(r.change)}>{changeWord(r.change)}</Chip> : null}</td>
                <td className={tdCls}>{pending
                  ? <DecisionCell row={r} choice={choices[r.id]} error={errors[r.id]}
                                  onChange={(c) => { setChoices((x) => ({ ...x, [r.id]: c })); setErrors((x) => { const y = { ...x }; delete y[r.id]; return y; }); }} />
                  : <span className="text-text-secondary">{ACTION_LABEL[r.decision]}</span>}</td>
              </tr>))}
            {!shown.length ? <tr><td colSpan={5} className={cn(tdCls, "text-text-muted")}>None.</td></tr> : null}
          </tbody>
        </table>
      </div>

      {pending ? (
        <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-border pt-3">
          <p className="min-w-0 flex-1 text-[12px] text-text-secondary" data-testid="policy-review-preview">{approvePreview(rows, choices)}</p>
          <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Reason, if rejecting" aria-label="Reason for rejecting"
                 className="h-8 w-56 rounded-md border border-border bg-surface px-2 text-[12px]" />
          <SecondaryButton onClick={reject} disabled={busy} data-testid="policy-review-reject">Reject</SecondaryButton>
          <PrimaryButton onClick={approve} disabled={busy} data-testid="policy-review-approve">Approve</PrimaryButton>
        </div>) : (
        <p className="mt-3 text-[12px] text-text-secondary" data-testid="policy-review-decided">
          {rec.status === "rejected" ? "Rejected" : "Approved"} by {rec.decided_by} on {shortDate(rec.decided_at)}
          {rec.param_versions.length ? `: ${rec.param_versions.map((v) => `${v.table.replace(/_/g, " ")} ${v.version}`).join(", ")}` : ""}.
          {rec.note ? ` ${rec.note}` : ""}</p>)}
      {err ? <p role="alert" className="mt-2 text-[12px] text-negative" data-testid="policy-review-error">{err}</p> : null}
    </Section>
  );
}
