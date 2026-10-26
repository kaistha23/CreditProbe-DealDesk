"use client";

/**
 * R13 IB (R14 backlog #2): the covenant designer — a compact panel for the deal page's More menu.
 *
 * For the deal, each covenant's proposed threshold, calibrated so that in the bank's history a breach came 2–3 quarters
 * before Stage 2 or default: early hit rate, median lead, false-alarm rate, against the template threshold and the bank's
 * as-set covenants, with the borrower's value today. Method and data limits behind the (i).
 *
 * R14 G (K32): opens with "In plain words" and a purpose line; a minimum-headroom choice (default 15% from today's value)
 * re-runs the designer; proposed levels stay inside sensible bounds; one verdict per row ("Beats template" only against a
 * template that itself warns); the headroom column and the trade-off line per covenant; the bank-template findings; and
 * the column help in plain words.
 */

import * as React from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { PanelWords } from "@/components/v5/panels-g/panel-words";
import { useLoad } from "@/lib/v5/dealdesk";
import { rate, sourceLine, threshold } from "@/lib/v5/intel-ib";
import { writeCovenants } from "@/lib/v5/plain-words-g/covenants";
import { cn } from "@/lib/utils";

import { Chip, Section, SecondaryButton, tableCls, tdCls, thCls } from "../../dealdesk/kit";
import { ibApi } from "./api";

const HEADROOMS = [10, 15, 20, 25] as const;
export const COVENANT_PURPOSE = "Covenant levels that would have warned at least 2 quarters before Stage 2 or default on similar borrowers, "
  + "and how often they would have raised false alarms on good ones.";
export const COVENANT_HELP: [string, string][] = [
  ["Today", "the client's value now"],
  ["Proposed", "the level to write into the facility"],
  ["Headroom", "how far today's value is from the proposed level"],
  ["Early hits", "share of past bad cases the level caught 2 or more quarters early"],
  ["Lead", "median quarters of warning"],
  ["False alarms", "share of good borrowers that would have breached"],
  ["Template", "the bank's standard level, with its own hits and false alarms"],
];

function headroom(v: number | null | undefined): string {
  return v == null || !Number.isFinite(v) ? "–" : `${v.toFixed(0)}%`;
}

export function CovenantDesignerPanel({ proposalId, onClose }: { proposalId: string; onClose?: () => void }) {
  const [mh, setMh] = React.useState<number>(15);
  const q = useLoad(() => ibApi.covenants(proposalId, mh), `covenants-${proposalId}-${mh}`);
  const d = q.data;
  const info = d ? (
    <div className="space-y-2 text-[12px]">
      <p>{d.method.objective}. Lead window {d.method.window_quarters} quarters; false alarms on quarters with no Stage 2 or default in the next {d.method.horizon_quarters};
        cap {rate(d.method.max_false_alarm)}.</p>
      <p>Calibrated on {d.population}: {d.events.toLocaleString("en-US")} Stage 2 or default events.</p>
      <p className="font-medium">Data limits</p>
      <ul className="list-disc pl-4">{d.data_limits.map((x) => <li key={x}>{x}</li>)}</ul>
    </div>
  ) : undefined;
  return (
    <Section title="Covenant designer" info={info} testId="covenant-designer-panel"
             action={onClose ? <SecondaryButton onClick={onClose} data-testid="covenant-designer-close">Close</SecondaryButton> : undefined}>
      <PanelWords panel="covenants" lines={d ? () => writeCovenants(d) : q.error ? [] : null} />
      <p className="mb-2 text-[12px] text-text-secondary" data-testid="covenant-purpose">{COVENANT_PURPOSE}</p>
      <div className="mb-3 flex flex-wrap items-center gap-1.5 text-[12px]" data-testid="covenant-headroom">
        <span className="text-text-secondary">Minimum headroom from today</span>
        {HEADROOMS.map((h) => (
          <button key={h} type="button" onClick={() => setMh(h)} aria-pressed={mh === h} data-testid={`covenant-headroom-${h}`}
                  className={cn("h-6 rounded-full border px-2.5 text-[11px] font-medium",
                                mh === h ? "border-accent bg-accent-muted text-accent" : "border-border text-text-secondary hover:bg-surface-hover")}>{h}%</button>))}
      </div>
      {q.error ? <p role="alert" className="text-[12px] text-negative">{q.error}</p> : null}
      {!d ? <Skeleton className="h-40 w-full" /> : (
        <div className="space-y-3">
          <p className="text-[13px] text-text-primary" data-testid="covenant-summary">{d.summary}</p>
          <div className="overflow-x-auto"><table className={tableCls} data-testid="covenant-table">
            <thead><tr>
              <th className={thCls}>Covenant</th>
              {COVENANT_HELP.slice(0, 2).map(([k, h]) => <th key={k} className={cn(thCls, "text-right")} title={h}>{k}</th>)}
              <th className={cn(thCls, "text-right")} title={COVENANT_HELP[2][1]}>Headroom</th>
              <th className={cn(thCls, "text-right")} title={COVENANT_HELP[3][1]}>Early hits</th>
              <th className={cn(thCls, "text-right")} title={COVENANT_HELP[4][1]}>Lead</th>
              <th className={cn(thCls, "text-right")} title={COVENANT_HELP[5][1]}>False alarms</th>
              <th className={cn(thCls, "text-right")} title={COVENANT_HELP[6][1]}>Template</th>
              <th className={cn(thCls, "text-right")} title="Template: early hits / false alarms">Template hits / alarms</th>
              <th className={thCls}>Verdict</th>
            </tr></thead>
            <tbody>{d.covenants.map((c) => (
              <tr key={c.covenant} data-testid={`covenant-row-${c.covenant}`} title={c.trade_off_line ?? c.text}>
                <td className={tdCls}><span className="font-medium text-text-primary">{c.label}</span></td>
                <td className={cn(tdCls, "text-right")} title={sourceLine(c.current?.source)}>{threshold(c.current?.value, c.unit)}</td>
                <td className={cn(tdCls, "text-right font-semibold")}>{threshold(c.proposed.threshold, c.unit)}</td>
                <td className={cn(tdCls, "text-right", c.proposed.deal_headroom_pct != null && c.proposed.deal_headroom_pct < (d.min_headroom_pct ?? 15) - 0.5 && "text-warning")}
                    data-testid={`covenant-headroom-cell-${c.covenant}`}>{headroom(c.proposed.deal_headroom_pct)}</td>
                <td className={cn(tdCls, "text-right")}>{rate(c.proposed.early_hit_rate)}</td>
                <td className={cn(tdCls, "text-right")}>{c.proposed.median_lead_q == null ? "–" : `${c.proposed.median_lead_q} q`}</td>
                <td className={cn(tdCls, "text-right")}>{rate(c.proposed.false_alarm_rate)}</td>
                <td className={cn(tdCls, "text-right")} title={c.template_source}>{threshold(c.template?.threshold, c.unit)}</td>
                <td className={cn(tdCls, "text-right")}>{c.template ? `${rate(c.template.early_hit_rate)} / ${rate(c.template.false_alarm_rate)}` : "–"}</td>
                <td className={tdCls} data-testid={`covenant-verdict-${c.covenant}`}>
                  {c.recommended ? <Chip tone="positive">Recommend</Chip> : <Chip title={c.why_not ?? undefined}>Not recommended</Chip>}
                  {c.beats_template ? <span className="ml-1"><Chip tone="accent">Beats template</Chip></span> : null}
                  {c.already_breached ? <span className="ml-1"><Chip tone="negative">Breached today</Chip></span> : null}
                </td>
              </tr>))}
            </tbody>
          </table></div>
          <p className="text-[11px] leading-4 text-text-muted" data-testid="covenant-column-help">
            {COVENANT_HELP.map(([k, h], i) => <span key={k}>{i ? " · " : ""}<span className="font-medium text-text-secondary">{k}</span> = {h}</span>)}.
          </p>
          <div className="space-y-1 text-[12px]" data-testid="covenant-tradeoffs">
            <p className="font-medium text-text-primary">Trade-off: early warning, false alarms and headroom</p>
            <ul className="space-y-0.5 text-text-secondary">
              {d.covenants.map((c) => (
                <li key={c.covenant}><span className="text-text-primary">{c.label.replace(/\s*\(.*\)$/, "")}:</span> {c.trade_off_line ?? c.text}
                  {!c.recommended && c.why_not ? <span className="text-text-muted"> Not recommended: {c.why_not}.</span> : null}</li>))}
            </ul>
          </div>
          {d.findings?.length ? (
            <div className="space-y-1 rounded-md border border-warning/30 bg-warning-muted px-3 py-2 text-[12px]" data-testid="covenant-findings">
              <p className="font-medium text-text-primary">The bank's template</p>
              {d.findings.map((f) => <p key={f.covenant + f.kind} className="text-text-secondary" title={f.text}>{f.title}.</p>)}
            </div>) : null}
          {d.coverage_note ? <p className="text-[12px] text-text-secondary" data-testid="covenant-coverage-note">{d.coverage_note}</p> : null}
        </div>)}
    </Section>
  );
}
