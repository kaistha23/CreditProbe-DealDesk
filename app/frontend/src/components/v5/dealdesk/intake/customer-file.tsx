"use client";

/**
 * R16 i: the customer file. Drop the customer's documents (Word, PDF, photos; many at once) and see, in this order:
 * who the customer is and whether the Bank already knows them, the document checklist (received / missing / expired),
 * what the documents say when read together (reconciliation), the Bank's own data (accounts, conduct, facilities, group),
 * and every document with how it was read and what it was classified as.
 *
 *   <IntakeDrop onFiles={…} busy />                      the drop zone (multi-file)
 *   <CustomerFileView file={v} onChange={setV} />        the file view (sections, each with its plain-words block)
 *   <CustomerFilePanel proposalId="R16-C1" />            the deal's customer file (More → Customer file); upload when none
 */

import * as React from "react";
import { AlertTriangle, CheckCircle2, FileImage, FileText, FileUp, Landmark, Plus, Trash2, X } from "lucide-react";

import { PlainWords } from "@/components/v5/ui/plain-words";
import { cn } from "@/lib/utils";
import {
  ACCEPT, type BankPull, uploadInBatches, type CheckLine, type CustomerFile, type IntakeDoc, RECON_LABEL, STATUS_LABEL, fmtMn, groupChecklist, intake, plainWords,
  reconTone, statusTone,
} from "@/lib/v5/dealdesk-intake";
import { friendlyMessage } from "@/lib/v5/errors";

import { Chip, Kpi, SecondaryButton, Section, tableCls, tdCls, thCls } from "../kit";

const wrap = "whitespace-normal";

// ------------------------------------------------------------------------------------------------ drop zone
export function IntakeDrop({ onFiles, busy, compact = false, label, progress, testId = "intake-drop" }: {
  onFiles: (files: File[]) => void; busy?: boolean; compact?: boolean; label?: string; /** "Read 12 of 38 files…" while busy */ progress?: string; testId?: string;
}) {
  const [over, setOver] = React.useState(false);
  const pick = (list: FileList | null) => { if (list && list.length) onFiles(Array.from(list)); };
  return (
    <label data-testid={testId}
           onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
           onDrop={(e) => { e.preventDefault(); setOver(false); pick(e.dataTransfer.files); }}
           className={cn("flex cursor-pointer flex-col items-center justify-center gap-1.5 rounded-lg border border-dashed text-center text-[13px] text-text-secondary hover:border-accent",
                         over ? "border-accent bg-accent-muted" : "border-border", compact ? "h-16 flex-row gap-2" : "h-40")}>
      {compact ? <Plus size={16} /> : <FileUp size={22} />}
      <span className="font-medium text-text-primary">{busy ? (progress || "Reading the documents…") : label ?? "Drop the customer's documents here, or choose files"}</span>
      {!compact ? <span className="text-[12px] text-text-muted">Word, PDF or photos of the pages (JPG, PNG); many at once. Photos are read by OCR.</span> : null}
      <input type="file" multiple accept={ACCEPT} className="sr-only" disabled={busy} data-testid={`${testId}-input`}
             onChange={(e) => { pick(e.target.files); e.currentTarget.value = ""; }} />
    </label>
  );
}

// ------------------------------------------------------------------------------------------------ header
function Header({ v }: { v: CustomerFile }) {
  const c = v.counts;
  const flags = v.reconciliation.filter((t) => t.severity >= 2).length;
  return (
    <div className="space-y-3" data-testid="intake-header">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-[16px] font-semibold text-text-primary" data-testid="intake-customer">{v.profile.customer_name || "Customer not identified"}</h2>
        {v.profile.cr_number ? <Chip>CR {v.profile.cr_number}</Chip> : null}
        {v.bank.existing
          ? <Chip tone="accent" testId="intake-existing"><Landmark size={12} /> Existing customer{v.bank.cif ? ` · CIF ${v.bank.cif}` : ""}</Chip>
          : <Chip testId="intake-new">New to bank</Chip>}
        {v.profile.contractor ? <Chip>Contractor</Chip> : null}
        {v.profile.city ? <span className="text-[12px] text-text-muted">{v.profile.city}{v.profile.activity ? ` · ${v.profile.activity}` : ""}</span> : null}
      </div>
      <div className="grid grid-cols-2 gap-2 md:grid-cols-5">
        <Kpi label="Files read" value={v.documents_n} sub={v.by_method_text} testId="intake-kpi-files" />
        <Kpi label="Received" value={`${c.received} / ${c.required}`} sub="required documents" tone="positive" testId="intake-kpi-received" />
        <Kpi label="Missing" value={c.missing} sub="to ask the customer for" tone={c.missing ? "negative" : "neutral"} testId="intake-kpi-missing" />
        <Kpi label="Expired" value={c.expired} sub="to be renewed" tone={c.expired ? "negative" : "neutral"} testId="intake-kpi-expired" />
        <Kpi label="To ask about" value={flags} sub="when read together" tone={flags ? "negative" : "positive"} testId="intake-kpi-flags" />
      </div>
    </div>
  );
}

// ------------------------------------------------------------------------------------------------ checklist
function Checklist({ v }: { v: CustomerFile }) {
  const groups = groupChecklist(v.checklist, v.groups);
  const docName = (ids: string) => ids.split(",").filter(Boolean).map((id) => v.documents.find((d) => d.doc_id === id)?.file_name ?? id).join(", ");
  const missing = v.checklist.filter((l) => l.status === "missing" || l.status === "expired");
  return (
    <Section title="Document checklist" testId="intake-checklist"
             info="Each required document against the bank's list (KYC, company legal, credit bureau, financials, bank statements and the other documents credit asks for). Expired means the printed expiry passed or the document is older than its validity rule.">
      <PlainWords testId="intake-checklist-plain" speak lines={[
        `${v.counts.received} of ${v.counts.required} required documents are in the file.`,
        missing.length ? `Still needed: ${missing.slice(0, 3).map((l) => `${l.requirement.toLowerCase()}${l.subject && l.subject !== "company" ? ` (${l.subject})` : ""}`).join("; ")}${missing.length > 3 ? ` and ${missing.length - 3} more` : ""}.` : "Nothing is missing.",
        "Grey lines do not apply to this customer.",
      ]} />
      <div className="mt-3 space-y-3">
        {groups.map((g) => (
          <div key={g.key} data-testid={`intake-group-${g.key}`}>
            <div className="mb-1 flex items-center gap-2">
              <h3 className="text-[12px] font-semibold uppercase tracking-[0.06em] text-text-secondary">{g.label}</h3>
              <span className="text-[12px] tabular-nums text-text-muted">{g.received} of {g.required}</span>
            </div>
            <table className={tableCls}>
              <tbody>{g.lines.map((l: CheckLine, i) => (
                <tr key={`${l.doc_type}-${l.subject}-${i}`} data-testid="intake-check-line" data-status={l.status} className={cn(l.status === "not_applicable" && "opacity-55")}>
                  <td className={cn(tdCls, "w-[34%]", wrap)}>{l.requirement}</td>
                  <td className={cn(tdCls, "w-[18%]", wrap, "text-text-secondary")}>{l.subject === "company" ? "" : l.subject}</td>
                  <td className={cn(tdCls, "w-[10%]")}><Chip tone={statusTone(l.status)}>{STATUS_LABEL[l.status] ?? l.status}</Chip></td>
                  <td className={cn(tdCls, wrap, "text-text-secondary")}>{l.reason}{l.doc_ids ? <span className="text-text-muted"> · {docName(l.doc_ids)}</span> : null}</td>
                </tr>))}</tbody>
            </table>
          </div>))}
      </div>
    </Section>
  );
}

// ------------------------------------------------------------------------------------------------ reconciliation
function Reconciliation({ v }: { v: CustomerFile }) {
  const [all, setAll] = React.useState(false);
  const flags = v.reconciliation.filter((t) => t.severity >= 2);
  const shown = all ? v.reconciliation : v.reconciliation.filter((t) => t.severity >= 1 || t.status !== "agrees").slice(0, 12);
  const agrees = v.reconciliation.filter((t) => t.status === "agrees").length;
  return (
    <Section title="Read together: do the documents agree?" testId="intake-recon"
             info="Key figures joined across documents and the Bank's data: revenue in the audited accounts vs VAT filings vs bank-statement credits, owners in the AoA vs CR vs bureau, identity, arithmetic, concentration, bureau, projects, guarantor support. Most serious first."
             action={<SecondaryButton onClick={() => setAll(!all)} data-testid="intake-recon-all">{all ? "Show the points to ask" : `Show all ${v.reconciliation.length} tests`}</SecondaryButton>}>
      <PlainWords testId="intake-recon-plain" speak lines={[
        `${v.reconciliation.length} cross-checks ran; ${agrees} agree.`,
        flags.length ? `${flags.length} need a question to the RM or the customer; the most serious is first.` : "Nothing needs a question.",
        "Each line says what each document shows, with the numbers.",
      ]} />
      <ul className="mt-3 divide-y divide-border/60">
        {shown.map((t) => (
          <li key={t.test} className="flex items-start gap-3 py-2.5" data-testid="intake-recon-line" data-severity={t.severity} data-test={t.test}>
            <span className="mt-0.5 shrink-0">{t.status === "agrees" ? <CheckCircle2 size={15} className="text-positive" /> : <AlertTriangle size={15} className={t.severity >= 3 ? "text-negative" : t.severity >= 2 ? "text-warning" : "text-text-muted"} />}</span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[13px] font-medium text-text-primary">{t.title}</span>
                <Chip tone={reconTone(t)}>{t.severity >= 3 ? "Key concern" : RECON_LABEL[t.status] ?? t.status}</Chip>
              </div>
              <p className="mt-0.5 text-[12.5px] leading-5 text-text-secondary">{t.sentence}</p>
              {(() => {
                const src = [...new Set((t.evidence ?? []).map((e) => e.file || (e.relation ? `Bank data: ${e.relation}` : "")).filter(Boolean))];
                return src.length ? <p className="mt-0.5 text-[11px] text-text-muted" data-testid="intake-recon-source">Source: {src.slice(0, 4).join(" · ")}{src.length > 4 ? ` +${src.length - 4}` : ""}</p> : null;
              })()}
            </div>
          </li>))}
      </ul>
    </Section>
  );
}

// ------------------------------------------------------------------------------------------------ bank pull
function Spark({ values, testId }: { values: number[]; testId?: string }) {
  if (!values.length) return null;
  const w = 240, h = 44, max = Math.max(...values, 1e-9);
  const bw = w / values.length;
  return (
    <svg width={w} height={h} role="img" aria-label="Monthly credits" data-testid={testId} className="text-accent">
      {values.map((x, i) => <rect key={i} x={i * bw + 1} y={h - (x / max) * (h - 4)} width={Math.max(1, bw - 2)} height={(x / max) * (h - 4)} rx={1} className="fill-current opacity-70" />)}
    </svg>
  );
}

function GroupGraph({ g, cif }: { g: NonNullable<BankPull["group"]>; cif?: string }) {
  const ents = g.entities;
  if (!ents.length) return null;
  const parent = ents.find((e) => !e.parent_entity_id || !ents.some((x) => x.entity_id === e.parent_entity_id)) ?? ents[0];
  const kids = ents.filter((e) => e.entity_id !== parent.entity_id);
  const W = 760, H = 150, y0 = 28, y1 = 112;
  const xs = kids.map((_, i) => (W / (kids.length + 1)) * (i + 1));
  const weak = (e: (typeof ents)[number]) => /classif|substandard|doubtful|loss|default|litig|stage ?3|watch/i.test(`${e.credit_status} ${e.credit_status_note}`);
  const label = (s: string) => (s.length > 26 ? `${s.slice(0, 25)}…` : s);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Group structure" data-testid="intake-group-graph">
      {kids.map((k, i) => <line key={k.entity_id} x1={W / 2} y1={y0 + 14} x2={xs[i]} y2={y1 - 14} className="stroke-border" strokeWidth={1.2} />)}
      {[{ e: parent, x: W / 2, y: y0 }, ...kids.map((e, i) => ({ e, x: xs[i], y: y1 }))].map(({ e, x, y }) => (
        <g key={e.entity_id} data-weak={weak(e) ? "1" : undefined}>
          <rect x={x - 82} y={y - 14} width={164} height={28} rx={6}
                className={cn("stroke-[1.2]", weak(e) ? "fill-negative-muted stroke-negative" : e.borrower_id === cif ? "fill-accent-muted stroke-accent" : "fill-surface stroke-border")} />
          <text x={x} y={y - 1} textAnchor="middle" className="fill-text-primary text-[10.5px] font-medium">{label(e.entity_name)}</text>
          <text x={x} y={y + 10} textAnchor="middle" className={cn("text-[9px]", weak(e) ? "fill-negative" : "fill-text-muted")}>{label(weak(e) ? (e.credit_status_note || e.credit_status) : e.role)}</text>
        </g>))}
    </svg>
  );
}

function BankBlock({ b }: { b: BankPull }) {
  if (!b.existing) {
    return (
      <Section title="The Bank's own data" testId="intake-bank">
        <PlainWords testId="intake-bank-plain" lines={["This customer does not bank with us yet: no account or deal carries this CR number.",
          "Everything here comes from the uploaded documents."]} />
      </Section>);
  }
  const l = b.last12;
  const credits = (b.conduct ?? []).map((r) => Number(r.credit_turnover_mn) || 0);
  const ft = b.facilities_total;
  return (
    <Section title="The Bank's own data (existing customer)" testId="intake-bank"
             info={`Pulled from Data Domains: ${b.sources.join(", ") || "none"}. Matched by ${b.how}.`}>
      <PlainWords testId="intake-bank-plain" speak lines={[
        `Banks with us${b.since ? ` since ${b.since.slice(0, 4)}` : ""}${b.rating ? `, rated ${b.rating}` : ""}; matched by ${b.how.split(" on ")[0]}.`,
        l ? `Last 12 months: SAR ${fmtMn(l.credits_mn)}m credited, average balance SAR ${fmtMn(l.avg_balance_mn)}m, ${l.returned_cheques_n} returned cheques.` : "No account conduct on file.",
        ft ? `Limits SAR ${fmtMn(ft.existing_mn)}m, used SAR ${fmtMn(ft.outstanding_mn)}m (${fmtMn(ft.utilisation_pct, 0)}%).` : "No facility on file.",
        b.connected_weak?.length ? `Watch: ${b.connected_weak[0].name} in the group is ${b.connected_weak[0].status.toLowerCase()}.` : "",
      ].filter(Boolean)} />
      <div className="mt-3 grid grid-cols-2 gap-2 md:grid-cols-4">
        <Kpi label="Credits, 12 months" value={l ? `SAR ${fmtMn(l.credits_mn)}m` : "–"} sub={l ? `${l.from} to ${l.to}` : undefined} testId="intake-bank-credits" />
        <Kpi label="Average balance" value={l ? `SAR ${fmtMn(l.avg_balance_mn)}m` : "–"} sub="12 months" />
        <Kpi label="Utilisation" value={l ? `${fmtMn(l.utilisation_avg_pct, 0)}%` : "–"} sub={l ? `peak ${fmtMn(l.utilisation_peak_pct, 0)}%` : undefined} />
        <Kpi label="Past dues · returned cheques" value={l ? `${l.past_due_months} · ${l.returned_cheques_n}` : "–"}
             sub={l ? `max ${l.past_due_days_max} days · SAR ${fmtMn(l.returned_cheques_mn, 2)}m` : undefined} tone={l && (l.past_due_months || l.returned_cheques_n) ? "negative" : "neutral"} />
      </div>
      {credits.length ? <div className="mt-3 flex items-center gap-3 text-[12px] text-text-muted"><Spark values={credits} testId="intake-bank-spark" />
        <span>Monthly credits, {b.conduct?.[0]?.month} to {b.conduct?.[b.conduct.length - 1]?.month} (dd_account_conduct)</span></div> : null}
      {b.accounts?.length ? (
        <div className="mt-4 overflow-x-auto" data-testid="intake-bank-accounts">
          <h3 className="mb-1 text-[12px] font-semibold uppercase tracking-[0.06em] text-text-secondary">Accounts</h3>
          <table className={tableCls}>
            <thead><tr>{["Account", "Type", "Holder", "Opened", "Balance (SAR m)", "Avg balance", "Credits 12m"].map((h) => <th key={h} className={thCls}>{h}</th>)}</tr></thead>
            <tbody>{b.accounts.map((a, i) => {
              const g = (k: string) => a[k] as never;
              const num = (...ks: string[]) => { for (const k of ks) if (typeof a[k] === "number") return fmtMn(a[k] as number, 2); return "–"; };
              return (
                <tr key={i}>
                  <td className={tdCls}>{g("account_no") ?? g("account_number") ?? g("iban")}</td>
                  <td className={cn(tdCls, wrap)}>{g("label") ?? g("account_type") ?? g("type")}</td>
                  <td className={cn(tdCls, wrap, "text-text-secondary")}>{String(g("holder") ?? "Customer")}</td>
                  <td className={tdCls}>{g("opened") ?? g("open_date")}</td>
                  <td className={tdCls}>{num("balance_mn", "eom_balance_mn")}</td>
                  <td className={tdCls}>{num("avg_balance_12m_mn", "avg_balance_mn")}</td>
                  <td className={tdCls}>{num("credits_12m_mn", "credit_turnover_12m_mn", "credits_mn")}</td>
                </tr>);
            })}</tbody>
          </table>
        </div>) : null}
      {b.facilities?.length ? (
        <div className="mt-4 overflow-x-auto" data-testid="intake-bank-facilities">
          <h3 className="mb-1 text-[12px] font-semibold uppercase tracking-[0.06em] text-text-secondary">Facilities with the Bank</h3>
          <table className={tableCls}>
            <thead><tr>{["Limit", "Existing (SAR m)", "Outstanding (SAR m)", "Used", "Cash margin", "Tenor"].map((h) => <th key={h} className={thCls}>{h}</th>)}</tr></thead>
            <tbody>{b.facilities.map((f) => (
              <tr key={f.limit_id}>
                <td className={cn(tdCls, wrap, Number(f.level) > 1 && "pl-6 text-text-secondary")}>{f.limit_name}</td>
                <td className={tdCls}>{fmtMn(f.existing_mn)}</td><td className={tdCls}>{fmtMn(f.outstanding_mn)}</td>
                <td className={tdCls}>{f.existing_mn ? `${fmtMn((f.outstanding_mn / f.existing_mn) * 100, 0)}%` : "–"}</td>
                <td className={tdCls}>{f.cash_margin_pct ? `${f.cash_margin_pct}%` : ""}</td>
                <td className={cn(tdCls, wrap)}>{f.tenor_text}</td>
              </tr>))}</tbody>
          </table>
        </div>) : null}
      {b.group?.entities?.length ? (
        <div className="mt-4" data-testid="intake-bank-group">
          <h3 className="mb-1 text-[12px] font-semibold uppercase tracking-[0.06em] text-text-secondary">Group and connected parties{b.group_name ? ` · ${b.group_name}` : ""}</h3>
          <GroupGraph g={b.group} cif={b.cif} />
        </div>) : null}
      {b.limit_history?.length ? (
        <div className="mt-3 text-[12px] text-text-secondary" data-testid="intake-bank-history">
          <h3 className="mb-1 text-[12px] font-semibold uppercase tracking-[0.06em] text-text-secondary">Limit history</h3>
          <ul className="space-y-0.5">{b.limit_history.slice(-5).map((r, i) => <li key={i}>{r.ref_date} · {r.authority} {r.ref_no}: {r.text}</li>)}</ul>
        </div>) : null}
      {(() => {
        const rh = (b.b360?.rating_history ?? []).map((r) => String(r.rating ?? "")).filter(Boolean);
        const seq = rh.filter((r, i) => i === 0 || r !== rh[i - 1]);
        const band = b.b360?.ews?.band ? String(b.b360.ews.band) : "";
        if (!seq.length && !band) return null;
        return (
          <p className="mt-3 text-[12px] text-text-secondary" data-testid="intake-bank-b360">
            Borrower 360: {seq.length ? `rating ${seq.join(" → ")} over the last ${rh.length} quarters` : ""}{band ? ` · early-warning band ${band}` : ""}
            {b.b360?.ews?.reasons ? ` (${String(b.b360.ews.reasons)})` : ""}</p>);
      })()}
    </Section>
  );
}

// ------------------------------------------------------------------------------------------------ documents
function DocDetail({ iid, d, onClose }: { iid: string; d: IntakeDoc; onClose: () => void }) {
  const [data, setData] = React.useState<Awaited<ReturnType<typeof intake.document>> | null>(null);
  const [err, setErr] = React.useState("");
  React.useEffect(() => { void intake.document(iid, d.doc_id).then(setData).catch((e) => setErr(friendlyMessage(e))); }, [iid, d.doc_id]);
  return (
    <div className="mt-2 rounded-lg border border-border bg-surface p-3" data-testid="intake-doc-detail">
      <div className="mb-2 flex items-center gap-2">
        <span className="text-[13px] font-medium text-text-primary">{d.file_name}</span>
        <a href={intake.rawUrl(iid, d.doc_id)} target="_blank" rel="noreferrer" className="text-[12px] text-accent underline">Open the file</a>
        <button type="button" onClick={onClose} aria-label="Close" className="ml-auto rounded p-1 text-text-muted hover:bg-surface-hover"><X size={14} /></button>
      </div>
      {err ? <p className="text-[12px] text-negative">{err}</p> : !data ? <p className="text-[12px] text-text-muted">Loading…</p> : (
        <div className="grid gap-3 md:grid-cols-2">
          <table className={tableCls}>
            <thead><tr><th className={thCls}>Field</th><th className={thCls}>Read as</th><th className={thCls}>Line</th></tr></thead>
            <tbody>{Object.entries(data.fields).map(([k, f]) => (
              <tr key={k}>
                <td className={cn(tdCls, wrap)}>{f.label}</td>
                <td className={cn(tdCls, wrap)}>{Array.isArray(f.value) ? `${f.value.length} rows` : typeof f.value === "number" ? f.value.toLocaleString("en-US") : String(f.value)}</td>
                <td className={cn(tdCls, "text-text-muted")}>{f.line}</td>
              </tr>))}</tbody>
          </table>
          <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded bg-surface-sunken p-2 text-[11px] leading-4 text-text-secondary" data-testid="intake-doc-text">{data.text}</pre>
        </div>)}
    </div>
  );
}

function Documents({ v, onChange, types }: { v: CustomerFile; onChange: (v: CustomerFile) => void; types: { code: string; label: string }[] }) {
  const [open, setOpen] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const photos = v.documents.filter((d) => d.file_kind === "image").length;
  const unknown = v.documents.filter((d) => d.doc_type === "unknown" || d.doc_type === "unreadable").length;
  const act = async (fn: () => Promise<CustomerFile>) => { setBusy(true); try { onChange(await fn()); } finally { setBusy(false); } };
  return (
    <Section title="Documents read" testId="intake-docs">
      <PlainWords testId="intake-docs-plain" lines={[
        `${v.documents_n} files: ${v.by_method_text}.`,
        photos ? `${photos} photos were read by OCR (text recognition); click a row to see what was read.` : "Click a row to see the fields and the text read.",
        unknown ? `${unknown} could not be recognised: set the type in the row.` : "Every file was recognised; correct a type if needed.",
      ]} />
      <div className="mt-3 overflow-x-auto">
        <table className={tableCls}>
          <thead><tr>{["File", "Read as", "Document", "About", "Status", ""].map((h, i) => <th key={i} className={thCls}>{h}</th>)}</tr></thead>
          <tbody>{v.documents.map((d) => (
            <React.Fragment key={d.doc_id}>
              <tr data-testid="intake-doc-row" data-type={d.doc_type} className="cursor-pointer hover:bg-surface-hover" onClick={() => setOpen(open === d.doc_id ? null : d.doc_id)}>
                <td className={cn(tdCls, wrap, "max-w-[260px] break-all")} data-testid="intake-doc-name">
                  <span className="inline-flex items-start gap-1.5">{d.file_kind === "image" ? <FileImage size={13} className="text-text-muted" /> : <FileText size={13} className="text-text-muted" />}{d.file_name}</span></td>
                <td className={cn(tdCls, "text-text-secondary")}>{d.read_method || "not read"}</td>
                <td className={tdCls} onClick={(e) => e.stopPropagation()}>
                  <select aria-label={`Type of ${d.file_name}`} value={types.some((t) => t.code === d.doc_type) ? d.doc_type : ""} disabled={busy}
                          data-testid="intake-doc-type" onChange={(e) => void act(() => intake.setType(v.intake_id, d.doc_id, e.target.value))}
                          className="h-7 max-w-[250px] rounded-md border border-border bg-surface px-1.5 text-[12px] text-text-primary">
                    {!types.some((t) => t.code === d.doc_type) ? <option value="">{d.error ? "Could not be read" : "Not recognised: choose"}</option> : null}
                    {types.map((t) => <option key={t.code} value={t.code}>{t.label}</option>)}
                  </select>
                  {d.confidence && d.confidence < 0.6 && types.some((t) => t.code === d.doc_type) ? <span className="ml-1 text-[11px] text-warning" title="Low confidence: check the type">check</span> : null}
                </td>
                <td className={cn(tdCls, wrap, "text-text-secondary")}>{d.subject === "company" ? "" : d.subject}</td>
                <td className={tdCls}>{d.error ? <Chip tone="negative" title={d.error}>Not read</Chip> : <Chip tone={statusTone(d.status)} title={d.status_reason}>{STATUS_LABEL[d.status] ?? d.status}</Chip>}</td>
                <td className={tdCls} onClick={(e) => e.stopPropagation()}>
                  <button type="button" aria-label={`Remove ${d.file_name}`} disabled={busy} data-testid="intake-doc-remove"
                          onClick={() => void act(() => intake.remove(v.intake_id, d.doc_id))} className="rounded p-1 text-text-muted hover:bg-surface-hover"><Trash2 size={13} /></button>
                </td>
              </tr>
              {open === d.doc_id ? <tr><td colSpan={6} className="p-0"><DocDetail iid={v.intake_id} d={d} onClose={() => setOpen(null)} /></td></tr> : null}
            </React.Fragment>))}</tbody>
        </table>
      </div>
    </Section>
  );
}

// ------------------------------------------------------------------------------------------------ the view
export function CustomerFileView({ file, onChange, footer }: { file: CustomerFile; onChange: (v: CustomerFile) => void; footer?: React.ReactNode }) {
  const [busy, setBusy] = React.useState(false);
  const [progress, setProgress] = React.useState("");
  const [error, setError] = React.useState("");
  const [types, setTypes] = React.useState<{ code: string; label: string }[]>([]);
  React.useEffect(() => { void intake.overview().then((o) => setTypes(o.doc_types)).catch(() => setTypes([])); }, []);
  const add = async (files: File[]) => {
    setBusy(true); setError("");
    try {
      onChange(await uploadInBatches(files, { intakeId: file.intake_id, onProgress: (d, t, v) => { setProgress(`Read ${d} of ${t} files…`); onChange(v); } }));
    } catch (e) { setError(friendlyMessage(e)); } finally { setBusy(false); setProgress(""); }
  };
  return (
    <div className="space-y-4" data-testid="intake-file" data-intake-id={file.intake_id}>
      <PlainWords testId="intake-plain" speak lines={plainWords(file)} />
      <Header v={file} />
      {footer}
      <Checklist v={file} />
      <Reconciliation v={file} />
      <BankBlock b={file.bank} />
      <Documents v={file} onChange={onChange} types={types} />
      <IntakeDrop compact busy={busy} progress={progress} onFiles={(f) => void add(f)} label="Add more documents" testId="intake-add" />
      {error ? <p className="text-[12px] text-negative" role="alert">{error}</p> : null}
    </div>
  );
}

/** The deal's customer file (More → Customer file). */
export function CustomerFilePanel({ proposalId }: { proposalId: string }) {
  const [file, setFile] = React.useState<CustomerFile | null>(null);
  const [state, setState] = React.useState<"loading" | "none" | "ready" | "error">("loading");
  const [busy, setBusy] = React.useState(false);
  const [progress, setProgress] = React.useState("");
  const [error, setError] = React.useState("");
  React.useEffect(() => {
    let live = true;
    void intake.byDeal(proposalId).then((v) => { if (live) { setFile(v); setState("ready"); } })
      .catch((e) => { if (live) setState((e as { status?: number }).status === 404 ? "none" : "error"); });
    return () => { live = false; };
  }, [proposalId]);
  const open = async (files: File[]) => {
    setBusy(true); setError("");
    try {
      const v = await uploadInBatches(files, { proposalId, onProgress: (d, t) => setProgress(`Read ${d} of ${t} files…`) });
      setFile(v); setState("ready");
    } catch (e) { setError(friendlyMessage(e)); } finally { setBusy(false); setProgress(""); }
  };
  return (
    <div className="space-y-3 pt-8" data-testid="intake-panel">
      {state === "loading" ? <PlainWords lines={[]} loading /> : null}
      {state === "none" || state === "error" ? (
        <>
          <PlainWords testId="intake-panel-plain" lines={["No customer documents are attached to this deal yet.",
            "Drop the customer's documents (Word, PDF or photos): CreditProbe reads them, checks the list and the numbers, and pulls the Bank's data."]} />
          <IntakeDrop busy={busy} progress={progress} onFiles={(f) => void open(f)} />
          {error ? <p className="text-[12px] text-negative" role="alert">{error}</p> : null}
        </>) : null}
      {state === "ready" && file ? <CustomerFileView file={file} onChange={setFile} /> : null}
    </div>
  );
}
