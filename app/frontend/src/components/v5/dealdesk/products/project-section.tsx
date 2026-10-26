"use client";

/**
 * PLAN_R12 Session P (I28): the contracting / project section, mounted by Session U on the deal page when the
 * product template is "contracting". Answer first, four tiles, then the financed-projects status table, the
 * project cash-flow deficit with the payment-delay stress (30/60/90 days), the LGs with their CCFs and the employer
 * credit. Every figure from GET /products/{id}/project. Renders nothing when the deal has no project data.
 */

import * as React from "react";

import { Plot } from "@/components/v5/ews/plot";
import { cn } from "@/lib/utils";

import { C } from "../charts";
import { Chip, Section, tableCls, tdCls, thCls } from "../kit";
import { productsApi, useProduct } from "./api";
import { type ProjectResult, amt, coverTone, days, deficitSeries, month, pct, projectTiles, slipTone, srcLine, times } from "./format";
import { Answer, Failed, Flags, Loading, Sub, Tiles, scrollCls } from "./parts";

const TITLE = "Financed projects and project cash flow";
const DELAY_COLOURS = [C.rec, C.hurdle, "var(--ipm-chart-4)", C.down];

export function ProjectSection({ proposalId, showEmpty = false }: { proposalId: string; showEmpty?: boolean }) {
  const { data, error, loading, reload } = useProduct(`project:${proposalId}`, (s) => productsApi.project(proposalId, s));
  if (loading && !data) return <Loading title={TITLE} testId="products-project-loading" />;
  if (error) return <Failed title={TITLE} message={error} onRetry={reload} testId="products-project-error" />;
  if (!data || (!data.has_data && !showEmpty)) return null;
  return <ProjectView r={data} />;
}

export function ProjectView({ r }: { r: ProjectResult }) {
  return (
    <Section title={TITLE} testId="products-project"
             info={<>Contract status, cash flow and payment-delay stress from the deal&apos;s financed projects (Deal Desk products
               domain: dd_project, dd_project_cashflow, dd_facility_limit). The cover ratio compares remaining contract proceeds
               with funded outstanding.</>}>
      <Answer text={r.answer} testId="products-project-answer" />
      {r.has_data ? <>
        <Tiles tiles={projectTiles(r)} testId="products-project-tiles" />
        <StatusTable r={r} />
        <DeficitChart r={r} />
        <DelayTable r={r} />
        <LgTable r={r} />
        <EmployerTable r={r} />
      </> : null}
    </Section>
  );
}

function StatusTable({ r }: { r: ProjectResult }) {
  const st = r.status;
  if (!st || !st.rows.length) return null;
  return (
    <Sub title={`Status of financed projects (as of ${st.as_of})`}>
      <div className={scrollCls}>
        <table className={tableCls} data-testid="products-project-status">
          <thead><tr>
            {["Project", "Employer", "Contract (revised)", "Work done vs plan", "Extension of time", "Received · due", "Last certificate"].map((h) =>
              <th key={h} className={thCls}>{h}</th>)}
          </tr></thead>
          <tbody>
            {st.rows.map((p) => (
              <React.Fragment key={p.project_id}>
                <tr>
                  <td className={cn(tdCls, "max-w-[180px] truncate")} title={p.project_name}>{p.project_name}</td>
                  <td className={cn(tdCls, "max-w-[140px] truncate")} title={p.consultant ? `Consultant: ${p.consultant}` : undefined}>{p.employer ?? "–"}</td>
                  <td className={tdCls} title={`Original ${amt(p.contract_value_original, p.currency)}. ${srcLine(p.src.contract_value_revised)}`}>
                    {amt(p.contract_value_revised, p.currency)}{p.variation_pct ? <span className="block text-[11px] text-text-muted">{p.variation_pct > 0 ? "+" : ""}{pct(p.variation_pct)} on original</span> : null}
                  </td>
                  <td className={tdCls} title={`Work done ${pct(p.wd_pct)} against ${p.planned_pct !== null && p.planned_pct !== undefined ? `${pct(p.planned_pct)} planned` : `${pct(p.time_elapsed_pct)} of the time elapsed`}. ${srcLine(p.src.wd_pct)}`}>
                    {pct(p.wd_pct)} <span className="text-text-muted">/ {pct(p.planned_pct ?? p.time_elapsed_pct)}</span>
                    {p.slip_pts !== null && p.slip_pts > 0 ? <span className="ml-1"><Chip tone={slipTone(p) === "negative" ? "negative" : "warning"}>−{p.slip_pts.toFixed(0)} pts</Chip></span> : null}
                  </td>
                  <td className={tdCls} title={p.eot_days ? p.eot_label : undefined}>
                    {p.eot_days ? <>
                      <Chip tone={p.eot_formalised === false ? "negative" : "neutral"}>{days(p.eot_days)}</Chip>
                      <span className={cn("block text-[11px]", p.eot_formalised === false ? "text-negative" : "text-text-muted")}>
                        {p.eot_formalised === false ? "not formalised" : p.eot_formalised ? "formalised" : "status not provided"}</span>
                    </> : "None"}
                  </td>
                  <td className={tdCls} title={`${srcLine(p.src.amount_received)}\n${srcLine(p.src.amount_due)}`}>
                    {amt(p.amount_received, p.currency)}
                    <span className={cn("block text-[11px]", p.days_due > 90 ? "text-negative" : "text-text-muted")}>
                      due {amt(p.amount_due, p.currency)}{p.days_due > 90 ? ` · ${days(p.days_due)}` : ""}</span>
                  </td>
                  <td className={tdCls}>{p.last_certificate.no ?? "–"}{p.last_certificate.date ? <span className="block text-[11px] text-text-muted">{p.last_certificate.date}</span> : null}</td>
                </tr>
                {p.flags.length || p.narrative ? <tr><td colSpan={7} className="border-b border-border/60 px-2 pb-2">
                  <Flags items={p.flags} />
                  {p.narrative ? <p className="mt-1 whitespace-normal text-[12px] text-text-muted">{p.narrative}</p> : null}
                </td></tr> : null}
              </React.Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </Sub>
  );
}

function DeficitChart({ r }: { r: ProjectResult }) {
  const series = deficitSeries(r);
  if (!series.length) return null;
  const data = series.map((s, i) => ({
    type: "scatter", mode: "lines+markers", name: s.name, x: s.x, y: s.y,
    line: { color: DELAY_COLOURS[i % DELAY_COLOURS.length], width: i === 0 ? 2.5 : 1.5, dash: i === 0 ? "solid" : "dot" },
    marker: { size: i === 0 ? 6 : 4 }, hovertemplate: `${s.name}<br>%{x}: deficit SAR %{y:,.1f}m<extra></extra>`,
  }));
  const lim = r.delay_stress?.funded_limit;
  const layout: Record<string, unknown> = {
    hovermode: "x unified", margin: { l: 56, r: 12, t: 30, b: 36 },
    legend: { orientation: "h", x: 0, y: 1.02, yanchor: "bottom", font: { size: 10 } },
    yaxis: { rangemode: "tozero", tickformat: ",.0f", title: { text: "Cumulative deficit, SAR m" } },
    // at most ~12 month labels, horizontal
    xaxis: { tickmode: "array", tickangle: 0, tickvals: series[0].x.filter((_, i) => i % Math.max(1, Math.ceil(series[0].x.length / 12)) === 0) },
    shapes: lim ? [{ type: "line", xref: "paper", x0: 0, x1: 1, y0: lim, y1: lim, line: { color: C.hurdle, width: 1.5, dash: "dash" } }] : [],
    annotations: lim ? [{ xref: "paper", x: 1, y: lim, xanchor: "right", yanchor: "bottom", showarrow: false, text: `Funded limit ${amt(lim)}`, font: { size: 10 } }] : [],
  };
  return (
    <Sub title={`Project cash-flow deficit${r.cash_flow?.peak_month ? `: peak ${amt(r.cash_flow.peak_deficit)} in ${month(r.cash_flow.peak_month)}` : ""}`}
         info="Cumulative receipts and advance less costs, by month; the deficit is the shortfall. Dotted lines delay every receipt by 30, 60 and 90 days.">
      <Plot data={data} layout={layout} height={240} testId="products-project-deficit" filename="deal-desk-project-deficit"
            ariaLabel="Monthly cumulative project cash-flow deficit, base and with payments 30, 60 and 90 days late" />
    </Sub>
  );
}

function DelayTable({ r }: { r: ProjectResult }) {
  const ds = r.delay_stress;
  if (!ds) return null;
  return (
    <Sub title="Payment-delay stress">
      <div className={scrollCls}>
        <table className={tableCls} data-testid="products-project-delay">
          <thead><tr>{["Case", "Peak deficit", "Peak month", "Extra funding", "Funded outstanding", "Cover ratio", "Within funded limit"].map((h) =>
            <th key={h} className={thCls}>{h}</th>)}</tr></thead>
          <tbody>
            {ds.rows.map((d) => (
              <tr key={d.delay_days}>
                <td className={tdCls}>{d.label}</td>
                <td className={tdCls}>{amt(d.peak_deficit)}</td>
                <td className={tdCls}>{month(d.peak_month)}</td>
                <td className={tdCls}>{d.delay_days ? amt(d.extra_funding) : "–"}</td>
                <td className={tdCls}>{amt(d.funded_outstanding)}</td>
                <td className={cn(tdCls, coverTone(d.cover_ratio, ds.cover_ratio_min) === "negative" && "text-negative")}>{times(d.cover_ratio)}</td>
                <td className={tdCls}>{d.within_limit === null ? "–" : d.within_limit ? <Chip tone="positive">Yes · headroom {amt(d.headroom)}</Chip> : <Chip tone="negative">No</Chip>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-1 text-[12px] text-text-secondary">
        {ds.first_break ? `First break at ${ds.first_break.delay_days} days: ${ds.first_break.what}.` : `No break up to ${ds.rows[ds.rows.length - 1].delay_days} days' delay.`}
        {" "}Cover ratio minimum {times(ds.cover_ratio_min)}.
      </p>
    </Sub>
  );
}

function LgTable({ r }: { r: ProjectResult }) {
  const lg = r.lgs;
  if (!lg || !lg.rows.length) return null;
  return (
    <Sub title={`Guarantees and LCs: ${amt(lg.total_proposed)} proposed, EAD ${amt(lg.total_ead_regulatory)}`}
         info="Bid bond, advance payment guarantee, performance bond and retention bond use the transaction-related CCF; EAD is on the amount net of cash margin.">
      <div className={scrollCls}>
        <table className={tableCls} data-testid="products-project-lgs">
          <thead><tr>{["Type", "Limit", "Outstanding", "Proposed", "Cash margin", "CCF (regulatory)", "EAD (regulatory)"].map((h) =>
            <th key={h} className={thCls}>{h}</th>)}</tr></thead>
          <tbody>
            {lg.rows.map((x) => (
              <tr key={x.limit_id}>
                <td className={tdCls}>{x.label}</td>
                <td className={tdCls}>{x.limit_id}</td>
                <td className={tdCls}>{amt(x.outstanding)}</td>
                <td className={tdCls}>{amt(x.proposed)}</td>
                <td className={tdCls}>{pct(x.cash_margin_pct)}</td>
                <td className={tdCls}>{pct(x.ccf_regulatory)}</td>
                <td className={tdCls}>{amt(x.ead_regulatory)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Sub>
  );
}

function EmployerTable({ r }: { r: ProjectResult }) {
  const e = r.employer_credit;
  if (!e || !e.rows.length) return null;
  return (
    <Sub title="Employer credit">
      <p className="mb-1.5 text-[12px] text-text-secondary">{e.text}.</p>
      <div className={scrollCls}>
        <table className={tableCls} data-testid="products-project-employers">
          <thead><tr>{["Employer", "Projects", "Remaining backlog", "Share", "Certified unpaid", "Oldest unpaid", "Rating", "Bureau"].map((h) =>
            <th key={h} className={thCls}>{h}</th>)}</tr></thead>
          <tbody>
            {e.rows.map((x) => (
              <tr key={x.employer}>
                <td className={cn(tdCls, "max-w-[200px] truncate")} title={x.employer}>{x.employer}</td>
                <td className={tdCls}>{x.projects}</td>
                <td className={tdCls}>{amt(x.backlog)}</td>
                <td className={tdCls}>{pct(x.backlog_share)}</td>
                <td className={tdCls}>{amt(x.amount_due)}</td>
                <td className={tdCls}>{x.max_days_due ? days(x.max_days_due) : "–"}</td>
                <td className={tdCls}>{x.rating ?? "Not provided"}</td>
                <td className={tdCls}>{x.bureau ? `${amt(x.bureau.overdue)} overdue · ${x.bureau.court_cases} court case${x.bureau.court_cases === 1 ? "" : "s"}` : "Not provided"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Sub>
  );
}
