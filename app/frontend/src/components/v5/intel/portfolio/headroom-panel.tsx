"use client";

/** PLAN_R13 §I ID, backlog #14: growth headroom map — where the bank can still lend next quarter, and the hurdle each slice clears. */

import * as React from "react";

import { Chip, tableCls, tdCls, thCls } from "@/components/v5/dealdesk/kit";
import { cn } from "@/lib/utils";
import { type Headroom, pctOf, sarM, toolPath } from "@/lib/v5/intel-portfolio";

import { PanelWords } from "@/components/v5/panels-g/panel-words";
import { writeHeadroom } from "@/lib/v5/plain-words-g/book";

import { Footnotes, Interpretation, Loading, PanelError, Strip, useIntel } from "./shell";

const LEVELS = [["appetite", "Appetite"], ["trigger", "Trigger"], ["limit", "Limit"]] as const;

export function HeadroomPanel({ initialLevel = "appetite" }: { initialLevel?: "appetite" | "trigger" | "limit" }) {
  const [level, setLevel] = React.useState<string>(initialLevel);
  const [all, setAll] = React.useState(false);
  const { data, error, loading } = useIntel<Headroom>(toolPath("headroom", { level }));
  const open = data ? data.rows.filter((r) => r.headroom_sar_mn > 1) : [];
  const shown = data ? (all ? data.rows : open.slice(0, 10)) : [];
  return (
    <div className="space-y-3" data-testid="intel-headroom">
      <PanelWords panel="headroom" lines={data ? () => writeHeadroom(data) : error ? [] : null} />
      <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Measured against">
        {LEVELS.map(([k, l]) => (
          <button key={k} type="button" onClick={() => setLevel(k)} aria-pressed={level === k} data-testid={`intel-headroom-level-${k}`}
                  className={cn("h-7 rounded-full border px-3 text-[12px]", level === k ? "border-accent bg-accent-muted text-accent" : "border-border text-text-secondary")}>{l}</button>
        ))}
      </div>
      {error ? <PanelError error={error} /> : null}
      {loading ? <Loading what="Measuring headroom against the risk-appetite statement…" /> : null}
      {data ? (<>
        <Interpretation lines={data.summary} testId="intel-headroom-summary" />
        <Strip kpis={data.kpis} pick={["open_slices", "rwa_budget", "cost_of_risk", "sub_ig"]} testId="intel-headroom-kpis" />
        <div className="overflow-x-auto">
          <table className={tableCls} data-testid="intel-headroom-table">
            <thead><tr>
              <th className={thCls}>Sector · rating</th><th className={cn(thCls, "text-right")}>Headroom</th><th className={thCls}>Bound by</th>
              <th className={cn(thCls, "text-right")}>RAROC now</th><th className={thCls}>Hurdle</th><th className={cn(thCls, "text-right")}>EL</th>
            </tr></thead>
            <tbody>
              {shown.map((r) => (
                <tr key={r.slice}>
                  <td className={tdCls}>{r.slice}</td>
                  <td className={cn(tdCls, "text-right font-medium")}>{sarM(r.headroom_sar_mn, 0)}</td>
                  <td className={tdCls}>{r.binding_label}{r.binding_already_beyond ? <span className="ml-1 text-negative">(beyond)</span> : null}</td>
                  <td className={cn(tdCls, "text-right")}>{pctOf(r.raroc_median)}</td>
                  <td className={tdCls}>
                    {r.clears_hurdle === null ? <Chip>{pctOf(r.hurdle, 0)}</Chip>
                      : r.clears_hurdle ? <Chip tone="positive">clears {pctOf(r.hurdle, 0)}</Chip>
                      : <Chip tone="warning" title="Margin uplift the median facility needs">{pctOf(r.hurdle, 0)} +{Math.round(r.margin_uplift_bps ?? 0)} bps</Chip>}
                  </td>
                  <td className={cn(tdCls, "text-right")}>{r.el_rate_bps.toFixed(0)} bps</td>
                </tr>))}
            </tbody>
          </table>
          <button type="button" onClick={() => setAll((x) => !x)} className="mt-1 text-[12px] text-accent hover:underline" data-testid="intel-headroom-all">
            {all ? "Show slices with headroom" : `Show all ${data.rows.length} slices`}</button>
        </div>
        {data.groups.length ? (
          <div className="overflow-x-auto">
            <h3 className="mb-1 text-[12px] font-medium text-text-secondary">Connected groups closest to their cap</h3>
            <table className={tableCls} data-testid="intel-headroom-groups">
              <thead><tr><th className={thCls}>Group</th><th className={cn(thCls, "text-right")}>EAD</th><th className={cn(thCls, "text-right")}>Cap</th><th className={cn(thCls, "text-right")}>Room</th></tr></thead>
              <tbody>{data.groups.slice(0, 6).map((g) => (
                <tr key={g.group_id}>
                  <td className={tdCls}>{g.group_name}</td><td className={cn(tdCls, "text-right")}>{sarM(g.ead_sar_mn, 0)}</td>
                  <td className={cn(tdCls, "text-right")}>{sarM(g.cap_sar_mn, 0)}</td>
                  <td className={cn(tdCls, "text-right", g.over_cap_sar_mn > 0 && "text-negative")}>
                    {g.over_cap_sar_mn > 0 ? `over by ${sarM(g.over_cap_sar_mn, 0)}` : sarM(g.headroom_sar_mn, 0)}</td>
                </tr>))}</tbody>
            </table>
          </div>) : null}
        <Footnotes env={data} testId="intel-headroom-notes" />
      </>) : null}
    </div>
  );
}
