"use client";

/** R13 IE item 22: DoA calibration — compact panel (tools menu). */

import * as React from "react";

import { Chip, tableCls } from "@/components/v5/dealdesk/kit";
import { Plot } from "@/components/v5/ews/plot";
import { TONE } from "@/lib/plotly-theme";
import { gov, pctText, rateText } from "@/lib/v5/intel-governance";

import { PanelWords } from "@/components/v5/panels-g/panel-words"; // R14 G (K34)
import { writeDoa } from "@/lib/v5/plain-words-g/governance";
import { DownloadButton, Failure, Lines, Loading, MethodNote, Td, Th, useGov, useGovOrigin } from "./shared";

export function DoaPanel() {
  const where = useGovOrigin();
  const { data, error, busy } = useGov(() => gov.doa(where), [where]);
  if (busy) return <Loading label="Timing every approval level…" />;
  if (error) return <Failure message={error} />;
  if (!data || !data.available) return <Lines lines={data?.lines ?? []} testId="gov-doa-lines" />;
  const lv = data.levels;
  return (
    <div className="space-y-4" data-testid="gov-doa">
      <PanelWords panel="doa" lines={() => writeDoa(data)} className="" />
      <div className="flex items-start justify-between gap-3">
        <Lines lines={data.lines.slice(0, 2)} testId="gov-doa-lines" />
        <MethodNote title="DoA calibration" method={data.method} data={data.data_note} />
      </div>
      <div className="grid gap-2" data-testid="gov-doa-proposals">
        {data.proposals.map((p, i) => (
          <div key={i} className="rounded-md border border-accent/30 bg-accent-muted/40 px-3 py-2">
            <div className="flex items-center gap-2">
              <Chip tone="accent">{p.rule === "pass_through" ? "Stop pass-through sign-off" : "Lift delegation"}</Chip>
              <span className="ml-auto text-[12px] tabular-nums text-text-secondary">≈ {p.days_saved_per_year.toLocaleString()} file-days a year · {p.control_given_up} past changes forgone</span>
            </div>
            <p className="mt-1 text-[13px] font-medium text-text-primary">{p.change}</p>
            <p className="text-[12px] text-text-secondary">{p.why}</p>
          </div>))}
      </div>
      <div className="grid grid-cols-[1fr_minmax(0,300px)] gap-3 max-[1360px]:grid-cols-1">
        <div className="overflow-x-auto">
          <table className={tableCls} data-testid="gov-doa-table">
            <thead><tr><Th>Level</Th><Th right>Files</Th><Th right>Median days</Th><Th right>Share of time</Th><Th right>Changed passing up</Th><Th right>Changed deciding</Th><Th right>Declined</Th></tr></thead>
            <tbody>
              {lv.map((l) => (
                <tr key={l.rank}>
                  <Td>{l.level}</Td>
                  <Td right>{l.files.toLocaleString()}</Td>
                  <Td right>{l.median_days.toFixed(1)}</Td>
                  <Td right>{pctText(l.share_of_turnaround_pct, 0)}</Td>
                  <Td right>{rateText(l.pass_through.changed)}</Td>
                  <Td right>{rateText(l.deciding.changed)}</Td>
                  <Td right>{pctText(l.deciding.declined?.pct ?? null)}</Td>
                </tr>))}
            </tbody>
          </table>
        </div>
        <Plot testId="gov-doa-chart" ariaLabel="Median days at each approval level" height={200} filename="doa-calibration"
              data={[{ type: "bar", orientation: "h", y: lv.map((l) => l.level), x: lv.map((l) => l.median_days),
                       marker: { color: lv.map((l) => (data.proposals.some((p) => p.level === l.level && p.rule === "pass_through") ? TONE.warning : TONE.accent)) },
                       hovertemplate: "%{y}: %{x:.1f} days (median)<extra></extra>" }]}
              layout={{ xaxis: { title: { text: "Median days at the level" } }, yaxis: { automargin: true, autorange: "reversed" }, margin: { l: 10, r: 10, t: 6, b: 40 } }} />
      </div>
      <div className="flex justify-end">
        <DownloadButton label="Excel" testId="gov-doa-xlsx" run={() => gov.download(where, "doa")} />
      </div>
    </div>
  );
}
