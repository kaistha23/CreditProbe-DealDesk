"use client";

/** R13 IE item 19: exception intelligence — compact panel (tools menu). */

import * as React from "react";

import { Chip, tableCls } from "@/components/v5/dealdesk/kit";
import { Plot } from "@/components/v5/ews/plot";
import { TONE } from "@/lib/plotly-theme";
import { gov, pctText, rateText, ratioText, verdictTone } from "@/lib/v5/intel-governance";

import { PanelWords } from "@/components/v5/panels-g/panel-words"; // R14 G (K34)
import { writeExceptions } from "@/lib/v5/plain-words-g/governance";
import { DownloadButton, Failure, Fold, Lines, Loading, MethodNote, Stat, Td, Th, useGov, useGovOrigin } from "./shared";

export function ExceptionPanel() {
  const where = useGovOrigin();
  const { data, error, busy } = useGov(() => gov.exceptions(where), [where]);
  if (busy) return <Loading label="Reading every approved exception and what happened after…" />;
  if (error) return <Failure message={error} />;
  if (!data || !data.available) return <Lines lines={data?.lines ?? []} testId="gov-exc-lines" />;
  const judged = data.types.filter((t) => t.n > 0 && t.oe_default != null);
  const order = [...judged].sort((a, b) => (a.oe_default ?? 0) - (b.oe_default ?? 0));
  const e = data.peers.exception, p = data.peers.no_exception;
  return (
    <div className="space-y-4" data-testid="gov-exceptions">
      <PanelWords panel="exceptions" lines={() => writeExceptions(data)} className="" />
      <div className="flex items-start justify-between gap-3">
        <Lines lines={data.lines} testId="gov-exc-lines" />
        <MethodNote title="Exception intelligence" method={data.method} data={data.data_note} />
      </div>
      <div className="grid grid-cols-3 gap-2">
        <Stat label="Default 12m · with exception" value={pctText(e.default.pct)} sub={`n ${e.n.toLocaleString()} · CI ${e.default.ci_low_pct.toFixed(1)}–${e.default.ci_high_pct.toFixed(1)}%`} tone="negative" testId="gov-exc-kpi-with" />
        <Stat label="Default 12m · no exception" value={pctText(p.default.pct)} sub={`n ${p.n.toLocaleString()} · CI ${p.default.ci_low_pct.toFixed(1)}–${p.default.ci_high_pct.toFixed(1)}%`} testId="gov-exc-kpi-without" />
        <Stat label="Types to tighten" value={data.tighten.length} sub={`of ${data.types.length} exception types`} tone={data.tighten.length ? "negative" : "positive"} testId="gov-exc-kpi-tighten" />
      </div>
      <div className="overflow-x-auto">
        <table className={tableCls} data-testid="gov-exc-table">
          <thead><tr><Th>Exception type</Th><Th right>n</Th><Th right>Default 12m (95% CI)</Th><Th right>Peers</Th><Th right>Observed / expected</Th><Th>Verdict</Th></tr></thead>
          <tbody>
            {data.types.map((t) => (
              <tr key={t.type}>
                <Td title={t.judged_on ? `Judged on ${t.judged_on}; measured on ${t.measured_on}` : t.note}>{t.label}</Td>
                <Td right>{t.n.toLocaleString()}</Td>
                <Td right>{rateText(t.default)}</Td>
                <Td right>{pctText(t.expected_default_pct)}</Td>
                <Td right>{ratioText(t.oe_default, t.oe_default_ci)}</Td>
                <Td><Chip tone={verdictTone(t.verdict)}>{t.verdict}</Chip></Td>
              </tr>))}
          </tbody>
        </table>
      </div>
      <Plot testId="gov-exc-chart" ariaLabel="Defaults against risk-matched peers by exception type, with 95% intervals" height={220}
            filename="exception-intelligence"
            data={[{
              type: "scatter", mode: "markers", orientation: "h",
              y: order.map((t) => t.label), x: order.map((t) => t.oe_default),
              error_x: { type: "data", symmetric: false, array: order.map((t) => (t.oe_default_ci?.[1] ?? 0) - (t.oe_default ?? 0)),
                         arrayminus: order.map((t) => (t.oe_default ?? 0) - (t.oe_default_ci?.[0] ?? 0)), color: TONE.muted },
              marker: { size: 9, color: order.map((t) => (t.verdict === "tighten" ? TONE.negative : t.verdict === "keep" ? TONE.positive : TONE.warning)) },
              hovertemplate: "%{y}: %{x:.2f}× peers<extra></extra>",
            }]}
            layout={{ xaxis: { type: "log", title: { text: "Defaults vs risk-matched peers (×, log scale)" } }, yaxis: { automargin: true },
                      shapes: [{ type: "line", x0: 1, x1: 1, yref: "paper", y0: 0, y1: 1, line: { color: TONE.textMuted, dash: "dot", width: 1 } }],
                      margin: { l: 10, r: 10, t: 6, b: 40 } }} />
      <Fold title="Latest approved exceptions and what happened after" testId="gov-exc-ledger"
            meta={`${Math.min(25, data.ledger.length)} of ${data.ledger_total.toLocaleString()}`}>
        <div className="max-h-[260px] overflow-auto">
          <table className={tableCls}>
            <thead><tr><Th>Borrower</Th><Th>Quarter</Th><Th>Exception</Th><Th>Approved by</Th><Th right>Worst stage</Th><Th right>Max DPD</Th><Th>Default</Th></tr></thead>
            <tbody>
              {data.ledger.slice(0, 25).map((r) => (
                <tr key={r.exception_id}>
                  <Td className="max-w-[180px] truncate" title={`${r.borrower_name} · RM ${r.rm}`}>{r.borrower_name}</Td>
                  <Td>{r.quarter}</Td>
                  <Td title={`Clause ${r.clause}`}>{r.label}</Td>
                  <Td>{r.approved_by}</Td>
                  <Td right>{r.after.worst_stage}</Td>
                  <Td right>{r.after.max_dpd}</Td>
                  <Td>{r.after.default ? <Chip tone="negative">default</Chip> : <span className="text-text-muted">no</span>}</Td>
                </tr>))}
            </tbody>
          </table>
        </div>
      </Fold>
      <div className="flex justify-end">
        <DownloadButton label="Excel" testId="gov-exc-xlsx" run={() => gov.download(where, "exceptions")} />
      </div>
    </div>
  );
}
