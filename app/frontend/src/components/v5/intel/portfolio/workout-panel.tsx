"use client";

/**
 * PLAN_R13 §I ID, backlog #11: workout optimiser — for a stressed name, reschedule, extra collateral, partial exit,
 * sale and legal action compared on recovery NPV, ECL, capital and stage, counting the CBUAE three-restructuring rule.
 */

import * as React from "react";

import { Chip, tableCls, tdCls, thCls } from "@/components/v5/dealdesk/kit";
import { cn } from "@/lib/utils";
import { type Workout, type WorkoutCandidates, pctOf, sarM, signedSar, stageTone, toolPath } from "@/lib/v5/intel-portfolio";

import { PanelWords } from "@/components/v5/panels-g/panel-words";
import { writeWorkout } from "@/lib/v5/plain-words-g/book";

import { Footnotes, Interpretation, Loading, PanelError, Strip, useIntel } from "./shell";

export function WorkoutPanel({ borrowerId: given = "" }: { borrowerId?: string }) {
  const list = useIntel<WorkoutCandidates>(toolPath("workout", { limit: 30 }));
  const [picked, setPicked] = React.useState(given);
  const bid = picked || list.data?.rows[0]?.borrower_id || "";
  const { data, error, loading } = useIntel<Workout>(bid ? toolPath("workout", { borrowerId: bid }) : null);
  return (
    <div className="space-y-3" data-testid="intel-workout">
      <PanelWords panel="workout" lines={data ? () => writeWorkout(data) : error || list.error || (list.data && !bid) ? [] : null} />
      {list.error ? <PanelError error={list.error} /> : null}
      {list.loading ? <Loading what="Finding the stressed names…" /> : null}
      {list.data ? (
        <div className="flex flex-wrap items-center gap-2">
          <label htmlFor="intel-workout-name" className="text-[12px] text-text-secondary">Stressed name</label>
          <select id="intel-workout-name" value={bid} onChange={(e) => setPicked(e.target.value)} data-testid="intel-workout-pick"
                  className="h-8 min-w-[280px] rounded-md border border-border bg-surface px-2 text-[12px]">
            {given && !list.data.rows.some((r) => r.borrower_id === given) ? <option value={given}>{given}</option> : null}
            {list.data.rows.map((r) => (
              <option key={r.borrower_id} value={r.borrower_id}>
                {r.borrower_name} · Stage {r.stage} · {sarM(r.ead_sar_mn, 0)}{r.third_restructuring_next ? " · 2 restructurings" : ""}</option>))}
          </select>
          <span className="text-[11px] text-text-muted">{list.data.total.toLocaleString("en-US")} stressed names</span>
        </div>) : null}
      {error ? <PanelError error={error} /> : null}
      {loading ? <Loading what="Comparing workout routes…" /> : null}
      {data ? (<>
        <Interpretation lines={data.summary} testId="intel-workout-summary" />
        <Strip kpis={data.kpis} pick={["npv", "uplift", "restructurings", "ecl_now"]} testId="intel-workout-kpis" />
        <div className="overflow-x-auto">
          <table className={tableCls} data-testid="intel-workout-options">
            <thead><tr><th className={thCls}>Route</th><th className={cn(thCls, "text-right")}>Recovery NPV</th><th className={cn(thCls, "text-right")}>ECL after</th>
              <th className={cn(thCls, "text-right")}>Capital after</th><th className={thCls}>Stage</th></tr></thead>
            <tbody>{data.rows.map((o) => (
              <tr key={o.key} className={cn(o.key === data.recommended && "bg-accent-muted")} title={o.notes.join("; ")} data-testid={`intel-workout-${o.key}`}>
                <td className={tdCls}>
                  <span className="font-medium text-text-primary">{o.label}</span>
                  {o.key === data.recommended ? <span className="ml-1"><Chip tone="accent">best</Chip></span> : null}
                  {o.restructuring_number !== null && o.restructuring_number >= 3 ? <span className="ml-1"><Chip tone="negative">CBUAE 9.29</Chip></span> : null}
                </td>
                <td className={cn(tdCls, "text-right font-medium")}>{sarM(o.recovery_npv_sar_mn)} <span className="text-text-muted">{pctOf(o.recovery_rate, 0)}</span></td>
                <td className={cn(tdCls, "text-right")}>{sarM(o.ecl_after_sar_mn)} <span className="text-text-muted">{Math.abs(o.ecl_change_sar_mn) < 0.05 ? "unchanged" : signedSar(o.ecl_change_sar_mn)}</span></td>
                <td className={cn(tdCls, "text-right")}>{sarM(o.capital_after_sar_mn)}</td>
                <td className={tdCls}>{o.stage_after === null ? <Chip>derecognised</Chip> : <Chip tone={stageTone(o.stage_after)}>Stage {o.stage_after}</Chip>}</td>
              </tr>))}</tbody>
          </table>
        </div>
        <ul className="space-y-1 text-[12px] text-text-secondary" data-testid="intel-workout-notes-list">
          {data.rows.filter((o) => o.key === data.recommended || o.key === "reschedule").map((o) => (
            <li key={o.key}><span className="text-text-primary">{o.label}:</span> {o.notes.join("; ")}.</li>))}
        </ul>
        <Footnotes env={data} testId="intel-workout-notes" />
      </>) : null}
    </div>
  );
}
