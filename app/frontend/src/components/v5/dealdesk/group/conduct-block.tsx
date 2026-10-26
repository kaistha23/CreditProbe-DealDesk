"use client";

/**
 * PLAN_R12 §1.4 (I24), Session C: the conduct block (proposal section "Relationship with the bank"): turnover against
 * limits and the routing undertaking, returned cheques, utilisation, past dues and the bureau trend. Answer first (one
 * sentence in the proposal voice), then the KPIs, the 24-month chart and the detail tables.
 */

import * as React from "react";

import { Plot } from "@/components/v5/ews/plot";
import { cn } from "@/lib/utils";

import { Kpi, Section, tableCls, tdCls, thCls } from "../kit";
import { useGroupAll } from "./api";
import { type Conduct, conductKpis, sarm } from "./model";
import { Answer, Loading, SourceInfo, SubTitle } from "./parts";

export function ConductBlockView({ c }: { c: Conduct }) {
  const k = conductKpis(c);
  const m = c.turnover.months;
  return (<>
    <Answer testId="dealdesk-conduct-answer">{c.headline}</Answer>
    <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {k.map((x) => <Kpi key={x.label} label={x.label} value={x.value} sub={x.sub}
                         tone={x.tone === "negative" ? "negative" : x.tone === "positive" ? "positive" : "neutral"} />)}
    </div>
    {m.length ? (
      <div className="mt-3">
        <Plot ariaLabel="Credit turnover and returned cheques by month" filename="conduct" height={230}
              data={[{ type: "bar", name: "Credit turnover (SAR m)", x: m.map((x) => x.month), y: m.map((x) => x.credit_turnover_sar_mn), marker: { color: "#C9BC9C" } },
                     { type: "scatter", mode: "lines", name: "Average balance (SAR m)", x: m.map((x) => x.month), y: m.map((x) => x.avg_balance_sar_mn),
                       line: { color: "#1F4E79", width: 2 } },
                     { type: "scatter", mode: "markers", name: "Returned cheques", x: m.filter((x) => x.cheques_returned_count > 0).map((x) => x.month),
                       y: m.filter((x) => x.cheques_returned_count > 0).map((x) => x.cheques_returned_count), yaxis: "y2",
                       marker: { color: "#B42318", size: 9, symbol: "x" } }] as never[]}
              layout={{ margin: { l: 48, r: 40, t: 10, b: 40 }, legend: { orientation: "h", y: -0.3 }, yaxis: { title: { text: "SAR m" } },
                        yaxis2: { overlaying: "y", side: "right", title: { text: "cheques" }, rangemode: "tozero", dtick: 1 } } as never} />
      </div>) : null}
    <div className="grid gap-4 xl:grid-cols-3">
      <div>
        <SubTitle>Returned cheques (12 months)</SubTitle>
        {c.returned_cheques.dates.length ? (
          <table className={tableCls}><thead><tr>{["Date", "Count", "Amount", "Reason"].map((h) => <th key={h} className={thCls}>{h}</th>)}</tr></thead>
            <tbody>{c.returned_cheques.dates.map((d, i) => <tr key={i}><td className={tdCls}>{d.month}</td><td className={cn(tdCls, "text-right")}>{d.count}</td>
              <td className={cn(tdCls, "text-right")}>{sarm(d.amount)}</td><td className={tdCls}>{d.reason ?? "–"}</td></tr>)}</tbody></table>
        ) : <p className="text-[12px] text-text-muted">None returned.</p>}
      </div>
      <div>
        <SubTitle>Past dues by quarter</SubTitle>
        {c.past_dues.quarters.length ? (
          <table className={tableCls}><thead><tr>{["Quarter", "Max DPD", "Lines past due"].map((h) => <th key={h} className={thCls}>{h}</th>)}</tr></thead>
            <tbody>{c.past_dues.quarters.map((q) => <tr key={q.quarter}><td className={tdCls}>{q.quarter}</td>
              <td className={cn(tdCls, "text-right", q.max_dpd >= 30 && "text-negative")}>{q.max_dpd}</td><td className={cn(tdCls, "text-right")}>{q.past_due_facilities}</td></tr>)}</tbody></table>
        ) : <p className="text-[12px] text-text-muted">No facilities with the bank.</p>}
      </div>
      <div>
        <SubTitle>Bureau</SubTitle>
        {c.bureau.entity_reports.length ? (
          <table className={tableCls}><thead><tr>{["Entity", "Outstanding", "Overdue", "Court"].map((h) => <th key={h} className={thCls}>{h}</th>)}</tr></thead>
            <tbody>{c.bureau.entity_reports.map((e, i) => <tr key={i}><td className={cn(tdCls, "whitespace-normal")}>{e.entity}{e.role ? ` (${e.role})` : ""}</td>
              {e.provided ? (<><td className={cn(tdCls, "text-right")}>{sarm(e.outstanding_sar_mn ?? null)}</td><td className={cn(tdCls, "text-right")}>{sarm(e.overdue_sar_mn ?? null)}</td>
                <td className={cn(tdCls, "text-right", (e.court_cases ?? 0) > 0 && "text-negative")}>{e.court_cases ?? 0}</td></>)
                : <td className={cn(tdCls, "whitespace-normal text-text-muted")} colSpan={3}>not provided{e.not_provided_reason ? `: ${e.not_provided_reason}` : ""}</td>}</tr>)}</tbody></table>
        ) : c.bureau.quarters.length ? (
          <table className={tableCls}><thead><tr>{["Quarter", "External", "DPD", "Enquiries"].map((h) => <th key={h} className={thCls}>{h}</th>)}</tr></thead>
            <tbody>{c.bureau.quarters.slice(-4).map((q) => <tr key={q.quarter}><td className={tdCls}>{q.quarter}</td>
              <td className={cn(tdCls, "text-right")}>{sarm(q.external_exposure_sar_mn)}</td><td className={cn(tdCls, "text-right")}>{q.external_dpd_days ?? "–"}</td>
              <td className={cn(tdCls, "text-right")}>{q.enquiries ?? "–"}</td></tr>)}</tbody></table>
        ) : <p className="text-[12px] text-text-muted">No bureau record.</p>}
      </div>
    </div>
  </>);
}

/** Relationship conduct for one deal (Review and Structure steps). */
export function ConductBlock({ proposalId }: { proposalId: string }) {
  const r = useGroupAll(proposalId);
  return (
    <Section title="Relationship conduct" testId="dealdesk-conduct-block"
             info={r.data ? <SourceInfo title="Relationship conduct" sources={r.data.conduct.source}>
               <p>Account turnover against limits and the routing undertaking, returned cheques, utilisation, past dues on the bank&apos;s facilities and the bureau trend.</p>
             </SourceInfo> : undefined}>
      {r.data ? <ConductBlockView c={r.data.conduct} /> : <Loading error={r.error} />}
    </Section>
  );
}
