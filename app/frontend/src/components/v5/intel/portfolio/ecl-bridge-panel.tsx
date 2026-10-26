"use client";

/** PLAN_R13 §I ID, backlog #17: ECL bridge forecast — next quarter's ECL before the run, stage movers, drivers and the drafted overlay. */

import * as React from "react";

import { Chip, tableCls, tdCls, thCls } from "@/components/v5/dealdesk/kit";
import { cn } from "@/lib/utils";
import { type EclBridge, barGeometry, bandTone, pctOf, sarM, signedSar, toolPath, waterfall } from "@/lib/v5/intel-portfolio";

import { PanelWords } from "@/components/v5/panels-g/panel-words";
import { writeEclBridge } from "@/lib/v5/plain-words-g/book";

import { Footnotes, Interpretation, Loading, PanelError, Strip, useIntel } from "./shell";

export function EclBridgePanel() {
  const { data, error, loading } = useIntel<EclBridge>(toolPath("ecl_bridge"));
  const [showOverlay, setShowOverlay] = React.useState(false);
  const bars = data ? waterfall(data.bridge) : [];
  const geo = barGeometry(bars);
  return (
    <div className="space-y-3" data-testid="intel-ecl-bridge">
      <PanelWords panel="ecl-bridge" lines={data ? () => writeEclBridge(data) : error ? [] : null} />
      {error ? <PanelError error={error} /> : null}
      {loading ? <Loading what="Forecasting next quarter's ECL…" /> : null}
      {data ? (<>
        <Interpretation lines={data.summary} testId="intel-ecl-summary" />
        <Strip kpis={data.kpis} pick={["opening", "forecast", "stage2_ead", "overlay"]} testId="intel-ecl-kpis" />
        <div className="space-y-1" role="img" aria-label="ECL bridge" data-testid="intel-ecl-waterfall">
          {bars.map((b, i) => (
            <div key={b.key} className="grid grid-cols-[180px_1fr_88px] items-center gap-2 text-[12px]">
              <span className="truncate text-text-secondary" title={b.label}>{b.label}</span>
              <div className="relative h-4 rounded bg-surface">
                <div className={cn("absolute top-0 h-4 rounded", b.kind === "total" ? "bg-accent" : b.kind === "up" ? "bg-negative" : "bg-positive")}
                     style={{ left: `${geo[i].left}%`, width: `${geo[i].width}%` }} />
              </div>
              <span className="text-right tabular-nums text-text-primary">{b.kind === "total" ? sarM(b.value) : signedSar(b.value)}</span>
            </div>))}
        </div>
        {data.macro?.scenarios?.length ? (
          <div className="overflow-x-auto" data-testid="intel-ecl-macro">
            <h3 className="mb-1 text-[12px] font-medium text-text-secondary">Under the §S stress scenarios</h3>
            <table className={tableCls}>
              <thead><tr><th className={thCls}>Scenario</th><th className={cn(thCls, "text-right")}>Forecast {data.next_run}</th>
                <th className={cn(thCls, "text-right")}>Change on the base path</th><th className={cn(thCls, "text-right")}>Stage 2 share (one year)</th></tr></thead>
              <tbody>{data.macro.scenarios.map((x) => (
                <tr key={x.severity} data-testid={`intel-ecl-macro-${x.severity}`} title={x.label}>
                  <td className={tdCls}><span className="capitalize">{x.severity}</span></td>
                  <td className={cn(tdCls, "text-right font-medium")}>{sarM(x.closing_sar_mn)}</td>
                  <td className={cn(tdCls, "text-right")}>{signedSar(x.delta_sar_mn)}</td>
                  <td className={cn(tdCls, "text-right")}>{x.stage2_share_start != null && x.stage2_share_stressed != null
                    ? `${pctOf(x.stage2_share_start)} → ${pctOf(x.stage2_share_stressed)}` : "–"}</td>
                </tr>))}</tbody>
            </table>
            <p className="mt-1 text-[11px] text-text-muted">§S window {data.macro.window || "n/a"} · calibration {data.macro.fingerprint || "n/a"} · engine {data.macro.engine_version}
              {" "}· a quarter carries a quarter of §S&apos;s one-year change by sector</p>
          </div>) : data.macro?.note ? <p className="text-[11px] text-text-muted">{data.macro.note}</p> : null}
        <div className="overflow-x-auto">
          <h3 className="mb-1 text-[12px] font-medium text-text-secondary">Stage movers</h3>
          <table className={tableCls} data-testid="intel-ecl-movers">
            <thead><tr><th className={thCls}>Name</th><th className={thCls}>Now</th><th className={cn(thCls, "text-right")}>P(worse)</th>
              <th className={cn(thCls, "text-right")}>Expected ECL rise</th></tr></thead>
            <tbody>{data.rows.slice(0, 10).map((m) => (
              <tr key={m.facility_id} title={m.ews_reasons ?? undefined}>
                <td className={tdCls}><span className="font-medium text-text-primary">{m.borrower_name}</span><span className="ml-1 text-text-muted">{m.rating} · {m.facilities > 1 ? `${m.facilities} facilities` : m.facility_id}</span></td>
                <td className={tdCls}><Chip tone={m.stage === 2 ? "warning" : "neutral"}>Stage {m.stage}</Chip> <Chip tone={bandTone(m.ews_band)}>{m.ews_band}</Chip></td>
                <td className={cn(tdCls, "text-right")}>{pctOf(m.p_worse)}</td>
                <td className={cn(tdCls, "text-right font-medium")}>{sarM(m.expected_increase_sar_mn, 2)}</td>
              </tr>))}</tbody>
          </table>
        </div>
        <div>
          <button type="button" onClick={() => setShowOverlay((x) => !x)} className="text-[12px] text-accent hover:underline" data-testid="intel-ecl-overlay-toggle">
            {showOverlay ? "Hide" : "Show"} the drafted overlay justification ({sarM(data.overlay.amount_sar_mn)})</button>
          {showOverlay ? (
            <div className="mt-2 rounded-md border border-border bg-surface px-3 py-2 text-[12px] leading-5 text-text-secondary" data-testid="intel-ecl-overlay">
              {data.overlay.text.split("\n").map((l) => <p key={l}>{l}</p>)}
              <p className="mt-1 text-text-muted">Back-test {data.backtest.pooled.quarters.join(", ")}: inflow error Stage 2 {pctOf(data.backtest.pooled.inflow_error["2"])},
                Stage 3 {pctOf(data.backtest.pooled.inflow_error["3"])} (negative = under-predicted) · {data.overlay.status}</p>
            </div>) : null}
        </div>
        <Footnotes env={data} testId="intel-ecl-notes" />
      </>) : null}
    </div>
  );
}
