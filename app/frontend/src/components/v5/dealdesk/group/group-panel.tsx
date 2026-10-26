"use client";

/**
 * PLAN_R12 §1.4 (I24), Session C: the group and governance panel for the Review and Structure steps. Answer first (group
 * exposure against the cap, the rating overlay), then the group (parent, subsidiaries, sisters), shareholders and UBOs,
 * board and key persons with their links to other borrowers, insider links, ownership changes, connected parties with
 * their status, the increase-cap ask with its approval authority, and the red flags with the conditions they raise.
 * Every block's (i) names its Data Domains relations.
 */

import * as React from "react";

import { cn } from "@/lib/utils";

import { Chip, Kpi, Section, tableCls, tdCls, thCls } from "../kit";
import { useGroupAll } from "./api";
import { type CapTest, type Flag, type GroupAll, type Node, capLine, ownershipText, pts, sarm, severityTone, structureLine } from "./model";
import { Answer, Loading, SourceInfo, StatusChip, SubTitle } from "./parts";
import { PanelWords } from "@/components/v5/panels-g/panel-words"; // R14 G (K34)
import { writeGroup } from "@/lib/v5/plain-words-g/deal";

function NameCell({ name, href, sub }: { name: string; href?: string | null; sub?: string | null }) {
  return (
    <td className={cn(tdCls, "whitespace-normal")}>
      {href ? <a href={href} className="text-accent hover:underline">{name}</a> : name}
      {sub ? <span className="block text-[11px] text-text-muted">{sub}</span> : null}
    </td>
  );
}

function GroupTable({ rows }: { rows: Node[] }) {
  if (!rows.length) return null;
  return (
    <div className="overflow-x-auto">
      <table className={tableCls}>
        <thead><tr>{["Company", "Link", "Held", "Exposure", "Rating", "Status"].map((h) => <th key={h} className={thCls}>{h}</th>)}</tr></thead>
        <tbody>{rows.map((n) => (
          <tr key={n.borrower_id}>
            <NameCell name={n.name} href={n.href} sub={n.activity ?? undefined} />
            <td className={tdCls}>{n.link}</td>
            <td className={cn(tdCls, "text-right")}>{n.ownership_pct != null ? pts(n.ownership_pct) : "–"}</td>
            <td className={cn(tdCls, "text-right")}>{sarm(n.ead)}</td>
            <td className={tdCls}>{n.rating ?? "–"}</td>
            <td className={tdCls}><StatusChip status={n.status} /></td>
          </tr>))}</tbody>
      </table>
    </div>
  );
}

function CapBlock({ cap }: { cap: CapTest }) {
  const ask = cap.increase_ask;
  return (
    <div data-testid="dealdesk-group-cap">
      <SubTitle info={<SourceInfo title="Group exposure and cap" sources={[]}>
        <p>Group exposure after the deal = the group&apos;s exposure today ({cap.basis}) + the deal&apos;s year-1 exposure. It is held to the tighter of the
          connected group limit ({sarm(cap.connected_group_limit.limit_sar_mn)}, {cap.connected_group_limit.basis}) and the group&apos;s approved exposure cap.
          The optimiser treats it as a binding constraint: when it binds, the recommended structure holds the amount to the headroom.</p>
      </SourceInfo>}>Group exposure against the cap</SubTitle>
      <div className="overflow-x-auto">
        <table className={tableCls}>
          <thead><tr>{["Company", "Exposure today", "Limits", "Funded", "Proposed"].map((h) => <th key={h} className={thCls}>{h}</th>)}</tr></thead>
          <tbody>
            {cap.members.map((m) => (
              <tr key={m.borrower_id} className={m.is_self ? "font-medium" : undefined}>
                <td className={cn(tdCls, "whitespace-normal")}>{m.name}{m.is_self ? " (this obligor)" : ""}</td>
                <td className={cn(tdCls, "text-right")}>{sarm(m.ead)}</td>
                <td className={cn(tdCls, "text-right")}>{sarm(m.limit)}</td>
                <td className={cn(tdCls, "text-right")}>{sarm(m.funded_limit)}</td>
                <td className={cn(tdCls, "text-right")}>{m.proposed_limit != null ? sarm(m.proposed_limit) : "–"}</td>
              </tr>))}
            <tr className="font-semibold">
              <td className={tdCls}>Group after the deal</td>
              <td className={cn(tdCls, "text-right")} colSpan={4}>{sarm(cap.after_ead)} against {sarm(cap.binding_limit)} ({cap.binding})</td>
            </tr>
          </tbody>
        </table>
      </div>
      {cap.approved_cap ? (
        <p className="mt-2 text-[12px] text-text-secondary">Approved group cap {sarm(cap.approved_cap.limit_sar_mn)}
          {cap.approved_cap.approved_by ? `, ${cap.approved_cap.approved_by}` : ""}{cap.approved_cap.committee_ref ? ` (${cap.approved_cap.committee_ref}` : ""}
          {cap.approved_cap.approved_on ? `, ${cap.approved_cap.approved_on})` : cap.approved_cap.committee_ref ? ")" : ""}.</p>) : null}
      {ask ? (
        <div className={cn("mt-3 rounded-md border p-3", ask.kind === "increase_cap_requested" ? "border-warning/40 bg-warning-muted" : "border-negative/40 bg-negative-muted")}
             data-testid="dealdesk-group-cap-ask">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-[13px] font-semibold text-text-primary">
              {ask.kind === "policy_exception" ? (cap.approved_cap ? "Ask: increase the group exposure cap, above the connected group limit (policy exception)"
                : "Ask: policy exception on the connected group limit") : "Ask: increase the group exposure cap"}</p>
            <Chip tone="accent">Approval: {ask.doa.level}</Chip>
            <Chip tone="neutral">+{sarm(ask.increase_sar_mn)}{ask.increase_pct != null ? ` (+${pts(ask.increase_pct)})` : ""}</Chip>
          </div>
          <p className="mt-1 text-[12px] text-text-primary">{ask.text}</p>
          <p className="mt-1 text-[12px] text-text-secondary">{ask.alternative}</p>
        </div>) : null}
    </div>
  );
}

export function FlagList({ flags, testId }: { flags: Flag[]; testId?: string }) {
  if (!flags.length) return <p className="text-[12px] text-text-muted">No red flag on governance or conduct.</p>;
  return (
    <ol className="space-y-2" data-testid={testId}>
      {flags.map((f) => (
        <li key={f.code} className="rounded-md border border-border p-2.5" data-testid={`dealdesk-flag-${f.code}`}>
          <div className="flex flex-wrap items-center gap-2">
            <Chip tone={severityTone(f.severity)}>{f.severity}</Chip>
            <span className="text-[13px] font-medium text-text-primary">{f.title}</span>
            <span className="text-[11px] text-text-muted">{f.review_point_label}</span>
            {f.notch ? <Chip tone="warning">−{f.notch} notch</Chip> : null}
            <span className="ml-auto"><SourceInfo title={f.title} sources={f.evidence}><p>Finding {f.finding_id}.</p></SourceInfo></span>
          </div>
          <p className="mt-1 text-[12px] leading-5 text-text-primary">{f.detail}</p>
          <p className="mt-1 text-[12px] leading-5 text-text-secondary"><span className="font-medium">Condition ({f.condition.kind}, {f.condition.owner}, {f.condition.due}):</span> {f.condition.text}</p>
        </li>))}
    </ol>
  );
}

export function GroupPanelView({ g }: { g: GroupAll }) {
  const f = g.facts;
  const ov = g.governance.overlay;
  const cap = g.cap_test;
  const cp = f.connected_parties;
  const groupRows = [...(f.structure.parent ? [f.structure.parent] : []), ...f.structure.subsidiaries, ...f.structure.sisters];
  return (<>
    <Answer testId="dealdesk-group-answer">{capLine(cap)} {ov.text}</Answer>
    <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <Kpi label="Group after the deal" value={cap ? sarm(cap.after_ead) : "–"} sub={cap ? `${pts(cap.utilisation_pct)} of ${sarm(cap.binding_limit)}` : undefined}
           tone={cap?.status === "breach" ? "negative" : "neutral"} testId="dealdesk-group-kpi-exposure" />
      <Kpi label="Rating overlay" value={ov.notches ? `${ov.base_rating} → ${ov.overlaid_rating}` : ov.base_rating}
           sub={`${ov.reasons.length} red flag${ov.reasons.length === 1 ? "" : "s"}${ov.capped ? `, capped at ${ov.cap}` : ""}`}
           tone={ov.notches ? "negative" : "positive"} testId="dealdesk-group-kpi-overlay" />
      <Kpi label="Connected parties" value={String(cp.count)} sub={`${cp.adverse.length} adverse · ${sarm(cp.adverse_ead)}`}
           tone={cp.adverse.length ? "negative" : "neutral"} />
      <Kpi label="Owners identified" value={f.shareholders.rows.length ? pts(f.shareholders.identified_pct, 0) : "Not provided"}
           sub={f.shareholders.ubo_identified ? `${f.shareholders.ubo_count} UBO${f.shareholders.ubo_count === 1 ? "" : "s"}`
             : f.shareholders.rows.length ? "no UBO named" : "shareholder register not on file"}
           tone={f.shareholders.ubo_identified ? "positive" : f.shareholders.rows.length ? "negative" : "neutral"} />
    </div>

    <SubTitle info={<SourceInfo title="Group" sources={f.structure.source} />}>Group</SubTitle>
    <p className="mb-2 text-[12px] text-text-secondary">{structureLine(f)}</p>
    <GroupTable rows={groupRows} />

    {cap ? <CapBlock cap={cap} /> : null}

    <div className="grid gap-4 xl:grid-cols-2">
      <div>
        <SubTitle info={<SourceInfo title="Shareholders and UBOs" sources={f.shareholders.source} />}>Shareholders and UBOs</SubTitle>
        {f.shareholders.rows.length ? (
          <table className={tableCls}><thead><tr>{["Holder", "Share", "UBO", "Nationality"].map((h) => <th key={h} className={thCls}>{h}</th>)}</tr></thead>
            <tbody>{f.shareholders.rows.map((r, i) => (
              <tr key={`${r.name}-${i}`}><td className={cn(tdCls, "whitespace-normal")}>{r.name}{r.kind === "company" ? " (company)" : ""}{r.nominee ? " (nominee)" : ""}</td>
                <td className={cn(tdCls, "text-right")}>{ownershipText(r)}</td><td className={tdCls}>{r.ubo ? <Chip tone="accent">UBO</Chip> : "–"}</td>
                <td className={tdCls}>{r.nationality ?? "–"}</td></tr>))}</tbody></table>
        ) : <p className="text-[12px] text-text-muted">Shareholders not provided.</p>}
      </div>
      <div>
        <SubTitle info={<SourceInfo title="Board and key persons" sources={f.board.source} />}>Board and key persons</SubTitle>
        {f.board.rows.length ? (
          <table className={tableCls}><thead><tr>{["Person", "Role", "Also linked to"].map((h) => <th key={h} className={thCls}>{h}</th>)}</tr></thead>
            <tbody>{f.board.rows.map((b, i) => (
              <tr key={`${b.person_id ?? b.name}-${i}`}><td className={cn(tdCls, "whitespace-normal")}>{b.name}{b.key_person ? " ★" : ""}</td>
                <td className={tdCls}>{b.roles.join(", ")}</td>
                <td className={cn(tdCls, "whitespace-normal")}>{b.other_borrowers.length ? b.other_borrowers.map((o) => (
                  <span key={o.borrower_id} className="mr-2 inline-flex items-center gap-1">
                    {o.href ? <a href={o.href} className="text-accent hover:underline">{o.name}</a> : o.name}<StatusChip status={o.status} /></span>))
                  : b.other_directorships ?? "–"}</td></tr>))}</tbody></table>
        ) : <p className="text-[12px] text-text-muted">Board not provided.</p>}
      </div>
    </div>

    {(f.insiders.count || f.ownership_changes.count) ? (
      <div className="grid gap-4 xl:grid-cols-2">
        <div>
          <SubTitle>Insider and staff links</SubTitle>
          {f.insiders.rows.length ? <ul className="space-y-1 text-[12px]">{f.insiders.rows.map((r, i) => (
            <li key={i}><span className="font-medium">{r.party}</span>: {r.link}{r.role ? ` (${r.role})` : ""}{r.entity ? ` in ${r.entity}` : ""}
              {r.pct != null ? `, ${pts(r.pct)}` : ""}{r.disclosed === false ? "; not disclosed in the proposal" : ""}{r.detected_by ? `; found by ${r.detected_by}` : ""}.</li>))}</ul>
            : <p className="text-[12px] text-text-muted">{f.insiders.note ?? "None found."}</p>}
        </div>
        <div>
          <SubTitle>Ownership changes ({f.ownership_changes.lookback})</SubTitle>
          {f.ownership_changes.rows.length ? <ul className="space-y-1 text-[12px]">{f.ownership_changes.rows.map((r, i) => (
            <li key={i}>{r.date}{r.entity ? `, ${r.entity}` : ""}: {r.holder ? `${r.holder} ` : ""}{r.from ?? "–"} → {r.to ?? "–"}{r.disclosed === false ? " (not disclosed)" : ""}.</li>))}</ul>
            : <p className="text-[12px] text-text-muted">None in the period.</p>}
        </div>
      </div>) : null}

    <SubTitle info={<SourceInfo title="Connected parties" sources={[]}><p>Every company linked to the obligor by group, guarantee, shared collateral,
      common director or the related-party register, with its status from the book, the classification domain and the bureau.</p></SourceInfo>}>
      Connected parties</SubTitle>
    {cp.rows.length ? (
      <div className="max-h-72 overflow-auto">
        <table className={tableCls}><thead><tr>{["Company", "Linked by", "Exposure", "Max DPD (4q)", "Status"].map((h) => <th key={h} className={thCls}>{h}</th>)}</tr></thead>
          <tbody>{cp.rows.map((r) => (
            <tr key={r.borrower_id}><NameCell name={r.name} href={r.href} sub={r.note ?? (r.classified_basis?.length ? r.classified_basis.join(", ") : undefined)} />
              <td className={cn(tdCls, "whitespace-normal")}>{r.links.join(", ")}</td><td className={cn(tdCls, "text-right")}>{sarm(r.ead)}</td>
              <td className={cn(tdCls, "text-right")}>{r.max_dpd_4q || "–"}</td><td className={tdCls}><StatusChip status={r.status} /></td></tr>))}</tbody></table>
      </div>) : <p className="text-[12px] text-text-muted">No connected party in the bank&apos;s records.</p>}

    <SubTitle info={<SourceInfo title="Rating overlay" sources={[]}><p>{ov.basis}</p></SourceInfo>}>Red flags, rating overlay and conditions</SubTitle>
    <FlagList flags={g.governance.flags} testId="dealdesk-group-flags" />
  </>);
}

/** Group and governance for one deal (Review and Structure steps). */
export function GroupPanel({ proposalId }: { proposalId: string }) {
  const r = useGroupAll(proposalId);
  return (
    <Section title="Group and governance" testId="dealdesk-group-panel"
             info={<><p>The group from Borrower 360: parent, subsidiaries and sisters, shareholders and UBOs, board and key persons with their links to other
               borrowers, insider links, ownership changes, shared collateral and connected parties classified, in arrears or in litigation.</p>
               <p className="mt-2">Group exposure is tested against the group cap in the optimiser; each governance or conduct red flag is a review finding, takes one
                 notch off the rating (capped) and raises a condition.</p></>}>
      <PanelWords panel="group" lines={r.data ? () => writeGroup(r.data!) : r.error ? [] : null} />
      {r.data ? <GroupPanelView g={r.data} /> : <Loading error={r.error} />}
    </Section>
  );
}
