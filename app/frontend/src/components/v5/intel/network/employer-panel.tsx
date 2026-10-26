"use client";

/**
 * PLAN_R13 §I Session IC (#10): employer exposure. The bank's exposure to a project employer held through every
 * contractor it pays (book links, Deal Desk projects, payment certificates and LGs), against appetite. With no
 * employer named it opens on the ranking: the employers the bank is most exposed to through their contractors.
 * Every figure from GET /api/v1/intel/network/employer/{employer} and /employers.
 */

import * as React from "react";

import { FromLink } from "@/components/v5/ui/back-link"; // R14 U (K1)

import { Chip, Section, tableCls, tdCls, thCls } from "@/components/v5/dealdesk/kit";
import { useProduct } from "@/components/v5/dealdesk/products/api";
import { Failed, Loading, Tiles, scrollCls } from "@/components/v5/dealdesk/products/parts";
import { cn } from "@/lib/utils";

import { PanelWords } from "@/components/v5/panels-g/panel-words"; // R14 G (K34)
import { writeEmployer, writeEmployerRanking } from "@/lib/v5/plain-words-g/network";
import { networkApi } from "./api";
import { type EmployerRanking, type EmployerResult, employerTiles, pct, sar } from "./format";
import { Findings, Limits } from "./parts";

const TITLE = "Employer exposure";

export function EmployerPanel({ employer = "", period, onOpenBorrower }: {
  employer?: string; period?: string; onOpenBorrower?: (id: string) => void;
}) {
  const [picked, setPicked] = React.useState(employer);
  return picked
    ? <EmployerOne employer={picked} period={period} onBack={() => setPicked("")} onOpenBorrower={onOpenBorrower} />
    : <EmployerList period={period} onPick={setPicked} />;
}

function EmployerList({ period, onPick }: { period?: string; onPick: (id: string) => void }) {
  const { data, error, loading, reload } = useProduct(`employers:${period ?? ""}`, (s) => networkApi.employers(10, period, s));
  if (loading && !data) return <Loading title={TITLE} testId="intel-employer-loading" />;
  if (error) return <Failed title={TITLE} message={error} onRetry={reload} testId="intel-employer-error" />;
  if (!data) return null;
  return (
    <Section title={TITLE} testId="intel-employers" info={<>{data.method}. Status against the single obligor appetite ({data.appetite.basis}).</>}>
      <RankingView r={data} onPick={onPick} />
    </Section>
  );
}

export function RankingView({ r, onPick }: { r: EmployerRanking; onPick: (id: string) => void }) {
  return (
    <div data-testid="intel-employers-result">
      <PanelWords panel="employers" lines={() => writeEmployerRanking(r)} />
      <p className="mb-2 text-[13px] text-text-primary">
        Employers the bank is most exposed to through the contractors they pay ({r.period}).
      </p>
      <div className={scrollCls}>
        <table className={tableCls} data-testid="intel-employers-table">
          <thead><tr>{["Employer", "Contractors", "Their EAD", "Attributable", "Own", "Appetite"].map((h) => <th key={h} className={thCls}>{h}</th>)}</tr></thead>
          <tbody>
            {r.rows.map((x) => (
              <tr key={x.employer_id}>
                <td className={cn(tdCls, "max-w-[190px] truncate")} title={`${x.name} (${x.employer_id}) · ${x.sector}`}>
                  <button type="button" className="text-accent hover:underline" onClick={() => onPick(x.employer_id)}>{x.name}</button>
                </td>
                <td className={tdCls}>{x.contractors}</td>
                <td className={tdCls}>{sar(x.contractor_ead)}</td>
                <td className={tdCls}>{sar(x.attributable)}</td>
                <td className={tdCls}>{sar(x.own_ead)}</td>
                <td className={tdCls}>{pct(x.utilisation_pct, 0)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {r.deal_desk_employers.length ? (
        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          <span className="text-[11px] text-text-muted">Deal Desk project employers:</span>
          {r.deal_desk_employers.map((e) => (
            <button key={e.entity_id} type="button" onClick={() => onPick(e.entity_id)} className="rounded-full"
                    data-testid={`intel-employer-dd-${e.entity_id}`}>
              <Chip tone={e.credit_status === "performing" ? "neutral" : "warning"}>{e.name}</Chip>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function EmployerOne({ employer, period, onBack, onOpenBorrower }: {
  employer: string; period?: string; onBack: () => void; onOpenBorrower?: (id: string) => void;
}) {
  const { data, error, loading, reload } = useProduct(`employer:${employer}:${period ?? ""}`, (s) => networkApi.employer(employer, period, s));
  if (loading && !data) return <Loading title={TITLE} testId="intel-employer-loading" />;
  if (error) return <Failed title={TITLE} message={error} onRetry={reload} testId="intel-employer-error" />;
  if (!data) return null;
  const back = <button type="button" className="text-[12px] text-accent hover:underline" onClick={onBack} data-testid="intel-employer-back">All employers</button>;
  return (
    <Section title={`${TITLE}: ${data.employer.name}`} testId="intel-employer" action={back}
             info={<>Exposure held through every contractor this employer pays, its own exposure and its project LGs, against the
               single obligor appetite.</>}>
      <EmployerView r={data} onOpenBorrower={onOpenBorrower} />
    </Section>
  );
}

export function EmployerView({ r, onOpenBorrower }: { r: EmployerResult; onOpenBorrower?: (id: string) => void }) {
  return (
    <div data-testid="intel-employer-result">
      <PanelWords panel="employer" lines={() => writeEmployer(r)} source={r.data_domains?.note} />
      <Findings text={r.text} testId="intel-employer-findings" />
      <Tiles tiles={employerTiles(r)} testId="intel-employer-tiles" />
      {r.contractors.length ? (
        <div className={cn(scrollCls, "mt-2")}>
          <table className={tableCls} data-testid="intel-employer-contractors">
            <thead><tr>{["Contractor", "Share it pays", "EAD", "Non-funded", "Attributable", "EWS"].map((h) => <th key={h} className={thCls}>{h}</th>)}</tr></thead>
            <tbody>
              {r.contractors.slice(0, 10).map((c) => (
                <tr key={c.borrower_id}>
                  <td className={cn(tdCls, "max-w-[180px] truncate")} title={`${c.name} (${c.borrower_id}) · ${c.sector}`}>
                    {onOpenBorrower
                      ? <button type="button" className="text-accent hover:underline" onClick={() => onOpenBorrower(c.borrower_id)}>{c.name}</button>
                      : <FromLink className="text-accent hover:underline" href={c.href} from="employer">{c.name}</FromLink>/* R14 U (K1) */}
                  </td>
                  <td className={tdCls}>{pct(c.revenue_share_pct)}{c.dependence === "high" ? <span className="ml-1"><Chip tone="warning">high</Chip></span> : null}</td>
                  <td className={tdCls}>{sar(c.ead)}</td>
                  <td className={tdCls}>{sar(c.non_funded)}</td>
                  <td className={tdCls}>{sar(c.attributable)}</td>
                  <td className={tdCls}>{c.ews_band ?? "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {r.projects.length ? (
        <div className={cn(scrollCls, "mt-3")}>
          <table className={tableCls} data-testid="intel-employer-projects">
            <thead><tr>{["Project", "Contractor", "Backlog", "Certified unpaid", "Delay", "LGs outstanding"].map((h) => <th key={h} className={thCls}>{h}</th>)}</tr></thead>
            <tbody>
              {r.projects.map((p) => (
                <tr key={p.project_id}>
                  <td className={cn(tdCls, "max-w-[180px] truncate")} title={`${p.project} (${p.project_id}) · ${p.status}`}>{p.project}</td>
                  <td className={cn(tdCls, "max-w-[150px] truncate")}>{p.contractor ?? p.contractor_id}</td>
                  <td className={tdCls}>{sar(p.backlog, 0)}</td>
                  <td className={tdCls}>{sar(p.due)}</td>
                  <td className={tdCls}>{p.payment_delay_days ? `${p.payment_delay_days} days · ${p.pending_certs ?? 0} cert.` : "on time"}</td>
                  <td className={tdCls} title={p.lg_products.join(", ")}>{sar(p.lg_outstanding)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      <Limits limits={r.limits} lineage={r.lineage} testId="intel-employer-limits" />
    </div>
  );
}
