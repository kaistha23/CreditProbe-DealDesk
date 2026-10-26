"use client";

/** PLAN_R13 §I ID, backlog #15: exit and sell-down list — ranked by capital and ECL freed per unit of relationship value lost. */

import * as React from "react";

import { Chip, tableCls, tdCls, thCls } from "@/components/v5/dealdesk/kit";
import { cn } from "@/lib/utils";
import { ACTION_LABEL, type Exits, bandTone, sarM, toolPath } from "@/lib/v5/intel-portfolio";

import { PanelWords } from "@/components/v5/panels-g/panel-words";
import { writeExits } from "@/lib/v5/plain-words-g/book";

import { Footnotes, Interpretation, Loading, PanelError, Strip, useIntel } from "./shell";

export function ExitsPanel({ limit = 25 }: { limit?: number }) {
  const { data, error, loading } = useIntel<Exits>(toolPath("exits", { limit }));
  const [open, setOpen] = React.useState("");
  return (
    <div className="space-y-3" data-testid="intel-exits">
      <PanelWords panel="exits" lines={data ? () => writeExits(data) : error ? [] : null} />
      {error ? <PanelError error={error} /> : null}
      {loading ? <Loading what="Ranking names by capital and ECL freed…" /> : null}
      {data ? (<>
        <Interpretation lines={data.summary} testId="intel-exits-summary" />
        <Strip kpis={data.kpis} pick={["capital_freed", "ecl_freed", "value_lost", "ratio"]} testId="intel-exits-kpis" />
        <div className="overflow-x-auto">
          <table className={tableCls} data-testid="intel-exits-table">
            <thead><tr>
              <th className={thCls}>Name</th><th className={thCls}>Action</th><th className={cn(thCls, "text-right")}>Capital + ECL freed</th>
              <th className={cn(thCls, "text-right")}>Value lost / yr</th><th className={cn(thCls, "text-right")}>Ratio</th>
            </tr></thead>
            <tbody>
              {data.rows.map((r) => (
                <React.Fragment key={r.borrower_id}>
                  <tr className="cursor-pointer hover:bg-surface-hover" onClick={() => setOpen(open === r.borrower_id ? "" : r.borrower_id)}
                      data-testid={`intel-exit-${r.borrower_id}`}>
                    <td className={tdCls}>
                      <span className="font-medium text-text-primary">{r.borrower_name}</span>
                      <span className="ml-1 text-text-muted">{r.rating} · {r.sector}</span>
                      {r.ews_band && bandTone(r.ews_band) !== "neutral" ? <span className="ml-1"><Chip tone={bandTone(r.ews_band)}>{r.ews_band}</Chip></span> : null}
                    </td>
                    <td className={tdCls}><Chip tone={r.action === "not_renew" ? "warning" : r.action === "sell_down" ? "accent" : "neutral"}>{ACTION_LABEL[r.action]}</Chip></td>
                    <td className={cn(tdCls, "text-right font-medium")}>{sarM(r.net_freed_sar_mn, 2)}</td>
                    <td className={cn(tdCls, "text-right")}>{sarM(r.relationship_value_lost_sar_mn, 2)}</td>
                    <td className={cn(tdCls, "text-right")}>{r.score.toFixed(1)}x</td>
                  </tr>
                  {open === r.borrower_id ? (
                    <tr><td colSpan={5} className="border-b border-border/60 px-2 py-2 text-[12px] text-text-secondary">
                      <p><span className="text-text-primary">How:</span> {r.how}.</p>
                      <p><span className="text-text-primary">Why:</span> {r.reasons.join("; ")}.</p>
                      <p>Capital {sarM(r.capital_freed_sar_mn, 2)} · ECL {sarM(r.ecl_freed_sar_mn, 2)}{r.sale_loss_sar_mn ? ` · sale loss ${sarM(r.sale_loss_sar_mn, 2)}` : ""} ·
                        EAD {sarM(r.ead_sar_mn)} ({r.facilities} facilities) · {r.relationship_tier} · group {r.group_name}</p>
                    </td></tr>) : null}
                </React.Fragment>))}
            </tbody>
          </table>
        </div>
        <Footnotes env={data} testId="intel-exits-notes" />
      </>) : null}
    </div>
  );
}
