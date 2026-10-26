"use client";

/**
 * PLAN_R12 Session B (I26): the document checklist of a deal, built from the bank's document rules (product × segment × policy).
 *
 *   <DocumentsPanel dealId="PRP-A-GMC" editable />   the checklist: every required item with status (received / pending / expired / waived),
 *                                                     date, expiry and the clause that requires it; "Send query to RM" per missing item and
 *                                                     for all missing at once (through Mail); credit can mark an item received or waive it
 *   <DocumentsBadge dealId="PRP-A-GMC" onClick={…} />  the action-bar button "Documents (n missing)"
 *
 * U mounts both; neither renders an error into the shell (a failed load shows nothing for the badge, a short line for the panel).
 */

import { ProposalDocFromCheck } from "./proposal/rm-brief";
import * as React from "react";
import { FileText, Send } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { useLoad } from "@/lib/v5/dealdesk";
import { PanelWords } from "@/components/v5/panels-g/panel-words"; // R14 G (K34)
import { writeDocuments } from "@/lib/v5/plain-words-g/deal";
import { cn } from "@/lib/utils";

import { Chip, Empty, SecondaryButton, Section, tableCls, tdCls, thCls } from "./kit";
import { review2Api } from "./review2/api";
import { DOC_LABEL, DOC_TONE, type DocItem, type DocStatus, type Documents, docsBadge, groupDocs, pct, queryForDoc } from "./review2/helpers";

const wrap = "whitespace-normal";

export function DocumentsBadge({ dealId, onClick, className }: { dealId: string; onClick?: () => void; className?: string }) {
  const { data } = useLoad(() => review2Api.documents(dealId), `docs-badge:${dealId}`);
  return (
    <SecondaryButton onClick={onClick} className={className} data-testid="documents-badge" title={data?.headline}>
      <FileText size={14} aria-hidden />{docsBadge(data)}
    </SecondaryButton>
  );
}

function StatusEdit({ item, onSave }: { item: DocItem; onSave: (s: DocStatus, note?: string) => Promise<void> }) {
  const [busy, setBusy] = React.useState(false);
  const pick = async (s: DocStatus) => {
    let note: string | undefined;
    if (s === "waived") {
      note = window.prompt("Reason for the waiver (kept in the audit trail)") ?? "";
      if (!note.trim()) return;
    }
    setBusy(true);
    try { await onSave(s, note); } finally { setBusy(false); }
  };
  return (
    <select aria-label={`Status of ${item.name}`} value={item.status} disabled={busy} data-testid="doc-status-edit"
            onChange={(e) => void pick(e.target.value as DocStatus)}
            className="h-7 rounded-md border border-border bg-surface px-1.5 text-[11px] text-text-secondary">
      {(["received", "pending", "expired", "waived"] as DocStatus[]).map((s) => <option key={s} value={s}>{DOC_LABEL[s]}</option>)}
    </select>
  );
}

export function DocumentsPanel({ dealId, editable = true, canQuery = true, onChange, words = false }: {
  dealId: string; editable?: boolean; canQuery?: boolean; onChange?: (d: Documents) => void; /** R14 G: the plain-words block (More menu) */ words?: boolean;
}) {
  const [tick, setTick] = React.useState(0);
  const [msg, setMsg] = React.useState<string | null>(null);
  const [sent, setSent] = React.useState<Set<string>>(new Set());
  const { data, error, loading } = useLoad(() => review2Api.documents(dealId), `docs:${dealId}:${tick}`);
  React.useEffect(() => { if (data && onChange) onChange(data); }, [data, onChange]);
  const reload = () => setTick((t) => t + 1);
  const save = async (i: DocItem, s: DocStatus, note?: string) => {
    try { await review2Api.setDocument(dealId, i.item_id, s, note); setMsg(`${i.name} (${i.for}): ${DOC_LABEL[s].toLowerCase()}.`); reload(); }
    catch (e) { setMsg(e instanceof Error ? e.message : String(e)); }
  };
  const query = async (i: DocItem) => {
    try {
      const q = await review2Api.raiseQuery(dealId, queryForDoc(i), "document", i.item_id);
      setSent((x) => new Set(x).add(i.item_id));
      setMsg(q.status === "sent" ? `Query sent to ${q.to_user} through Mail.` : "Query kept; Mail is not reachable and it will be sent on the next refresh.");
    } catch (e) { setMsg(e instanceof Error ? e.message : String(e)); }
  };
  const queryAll = async () => {
    try { const r = await review2Api.queryMissing(dealId); setMsg(`${r.raised} queries sent to the RM through Mail.`); setSent(new Set(r.items.map((q) => q.ref_id ?? ""))); }
    catch (e) { setMsg(e instanceof Error ? e.message : String(e)); }
  };
  return (
    <Section title="Documents" testId="documents-panel"
             info={<>The documents this deal needs, generated from the bank&rsquo;s document rules for its product, segment and the credit policy
               {data ? ` (${data.policy.name} ${data.policy.version}, rules ${data.rules_version})` : ""}. Each item shows its status, the date of the copy on
               file, when it expires and the clause that requires it. Missing and expired items feed the completeness review; &ldquo;Send query&rdquo;
               asks the RM through Mail and the reply comes back to the review.</>}
             action={<span className="flex flex-wrap items-center gap-2">
               {/* R15 b (L11 (2)): the RM's proposal itself, with the check's comments beside each section */}
               <ProposalDocFromCheck proposalId={dealId} testId="documents-view-rm-proposal" />
               {data && canQuery && data.missing_count ? (
               <SecondaryButton onClick={() => void queryAll()} data-testid="documents-query-all"><Send size={13} aria-hidden />Query all missing</SecondaryButton>) : null}</span>}>
      {words ? <PanelWords panel="documents" lines={data ? () => writeDocuments(data) : error ? [] : null} /> : null}
      {loading ? <Skeleton className="h-40 w-full" /> : error || !data ? <Empty>The document checklist is not available right now.</Empty> : (
        <div>
          <div className="mb-2 flex flex-wrap items-center gap-1.5" data-testid="documents-summary">
            <span className="mr-1 text-[13px] font-medium text-text-primary">{data.headline}</span>
            {(["received", "pending", "expired", "waived"] as DocStatus[]).map((s) =>
              <Chip key={s} tone={DOC_TONE[s]}>{DOC_LABEL[s]} {data.counts[s]}</Chip>)}
            <span className="ml-auto text-[11px] text-text-muted">Completeness {pct(data.completeness)}</span>
          </div>
          {msg ? <p className="mb-2 text-[12px] text-text-secondary" role="status">{msg}</p> : null}
          <div className="overflow-x-auto">
            <table className={tableCls}>
              <thead><tr>
                <th className={thCls}>Document</th><th className={thCls}>For</th><th className={thCls}>Status</th>
                <th className={thCls}>Date</th><th className={thCls}>Expires</th><th className={thCls} />
              </tr></thead>
              <tbody>
                {groupDocs(data.items).map((g) => (
                  <React.Fragment key={g.group}>
                    <tr><td colSpan={6} className="pb-1 pt-3 text-[11px] font-semibold uppercase tracking-[0.06em] text-text-muted">{g.group}</td></tr>
                    {g.items.map((i) => (
                      <tr key={i.item_id} data-testid="doc-item" data-status={i.status} data-rule={i.rule_id}>
                        <td className={cn(tdCls, wrap, "min-w-[220px] text-text-primary")}>
                          {i.name}{i.mandatory ? null : <span className="ml-1 text-[10px] text-text-muted">(optional)</span>}
                          {i.note ? <p className="text-[11px] text-text-secondary">{i.note}</p> : null}
                          <p className="text-[10px] leading-4 text-text-muted" title={i.policy}>{i.clause}</p>
                        </td>
                        <td className={cn(tdCls, wrap, "max-w-[200px] text-text-secondary")}>{i.for}</td>
                        <td className={tdCls}>{editable ? <StatusEdit item={i} onSave={(s, n) => save(i, s, n)} /> : <Chip tone={DOC_TONE[i.status]}>{DOC_LABEL[i.status]}</Chip>}</td>
                        <td className={tdCls}>{i.date ?? "—"}</td>
                        <td className={cn(tdCls, i.status === "expired" && "text-negative")}>{i.expires ?? "—"}</td>
                        <td className={tdCls}>
                          {canQuery && i.mandatory && (i.status === "pending" || i.status === "expired") ? (
                            sent.has(i.item_id) ? <Chip tone="accent">Query sent</Chip> :
                              <button type="button" onClick={() => void query(i)} data-testid="doc-query"
                                      className="inline-flex h-7 items-center gap-1 rounded-md border border-border px-2 text-[11px] text-text-secondary hover:border-accent hover:text-accent">
                                <Send size={12} aria-hidden />Send query to RM</button>) : null}
                        </td>
                      </tr>))}
                  </React.Fragment>))}
              </tbody>
            </table>
          </div>
        </div>)}
    </Section>
  );
}
