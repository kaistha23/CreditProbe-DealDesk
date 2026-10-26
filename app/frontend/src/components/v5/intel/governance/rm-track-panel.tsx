"use client";

/** R13 IE item 21: RM track record — compact panel (tools menu). */

import * as React from "react";

import { Chip, tableCls } from "@/components/v5/dealdesk/kit";
import { cn } from "@/lib/utils";
import { flagTone, gov, pctText, ratioText } from "@/lib/v5/intel-governance";

import { PanelWords } from "@/components/v5/panels-g/panel-words"; // R14 G (K34)
import { writeRmTrack } from "@/lib/v5/plain-words-g/governance";
import { DownloadButton, Failure, Lines, Loading, MethodNote, Td, Th, useGov, useGovOrigin } from "./shared";

export function RmTrackPanel() {
  const where = useGovOrigin();
  const [group, setGroup] = React.useState<"rm" | "branch">("rm");
  const { data, error, busy } = useGov(() => gov.rmTrack(where, group), [where, group]);
  return (
    <div className="space-y-4" data-testid="gov-rm">
      <PanelWords panel="rm-track" lines={data?.available ? () => writeRmTrack(data) : busy ? null : []} className="" />
      <div className="flex items-center gap-1" role="tablist" aria-label="Group by">
        {(["rm", "branch"] as const).map((g) => (
          <button key={g} type="button" role="tab" aria-selected={group === g} onClick={() => setGroup(g)} data-testid={`gov-rm-group-${g}`}
                  className={cn("rounded-md px-3 py-1 text-[12px] font-medium",
                    group === g ? "bg-accent-muted text-accent" : "text-text-muted hover:bg-surface-hover")}>
            {g === "rm" ? "By RM" : "By branch"}
          </button>))}
      </div>
      {busy ? <Loading label="Scoring track records against the risk taken…" /> : error ? <Failure message={error} /> : !data || !data.available ? (
        <Lines lines={data?.lines ?? []} testId="gov-rm-lines" />) : (
        <>
          <div className="flex items-start justify-between gap-3">
            <Lines lines={data.lines} testId="gov-rm-lines" />
            <MethodNote title="RM track record" method={data.method} data={data.data_note} />
          </div>
          <div className="max-h-[420px] overflow-auto" data-testid="gov-rm-table">
            <table className={tableCls}>
              <thead className="sticky top-0 bg-surface">
                <tr><Th>{group === "rm" ? "RM" : "Branch"}</Th><Th right>Approvals</Th><Th right>Quality</Th><Th right>Queries</Th>
                  <Th right>Conditions met</Th><Th right>Promises kept</Th><Th right>Defaults O/E</Th><Th right>Score</Th><Th>Flag</Th></tr>
              </thead>
              <tbody>
                {data.rows.map((r) => (
                  <tr key={r.id}>
                    <Td className="max-w-[170px] truncate" title={`${r.name} · ${r.branch ?? r.region} · ${r.id}`}>
                      <span className="block truncate">{r.name}</span>
                      <span className="block truncate text-[11px] text-text-muted">{r.branch ?? r.region}</span>
                    </Td>
                    <Td right>{r.approved}</Td>
                    <Td right>{typeof r.quality.value === "number" ? r.quality.value.toFixed(0) : "—"}</Td>
                    <Td right>{r.queries_per_file.toFixed(1)}</Td>
                    <Td right>{pctText(r.conditions?.pct ?? null, 0)}</Td>
                    <Td right>{pctText(r.promises?.pct ?? null, 0)}</Td>
                    <Td right title={`95% interval ${ratioText(r.oe, r.oe_ci)}; ${r.defaults} defaults vs ${r.expected_defaults.toFixed(1)} expected`}>{ratioText(r.oe)}</Td>
                    <Td right className="font-semibold">{r.score == null ? "—" : r.score.toFixed(0)}</Td>
                    <Td title={r.flag}>{r.flag ? <Chip tone={flagTone(r.flag)}>{r.flag.replace(" than risk taken", "")}</Chip> : null}</Td>
                  </tr>))}
              </tbody>
            </table>
          </div>
          <div className="flex items-center justify-between">
            <p className="text-[12px] text-text-muted">{data.total} {group === "rm" ? "RMs" : "branches"} · at least {data.min_n} approvals to be ranked</p>
            <DownloadButton label="Excel" testId="gov-rm-xlsx" run={() => gov.download(where, "rm-track", undefined, group)} />
          </div>
        </>)}
    </div>
  );
}
