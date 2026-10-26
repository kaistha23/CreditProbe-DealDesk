"use client";

/** R16 M8: the findings register (owner, due date, overdue flag) with status changes recorded in the service store. */

import * as React from "react";

import { cn } from "@/lib/utils";
import { friendlyMessage } from "@/lib/v5/errors";
import { type Finding, monitor } from "@/lib/v5/scorecard-monitor";

import { day, person } from "./monitor-model";

const TH = "px-3 py-1.5 text-left text-[10px] font-semibold uppercase tracking-wide text-text-muted";
const NEXT: Record<string, { to: "open" | "in_progress" | "closed"; label: string }[]> = {
  open: [{ to: "in_progress", label: "Start" }, { to: "closed", label: "Close" }],
  in_progress: [{ to: "closed", label: "Close" }],
  closed: [{ to: "open", label: "Reopen" }],
};

export function FindingsTable({ rows, onChanged, compact, showScorecard }: { rows: Finding[]; onChanged?: () => void; compact?: boolean; showScorecard?: boolean }) {
  const [busy, setBusy] = React.useState("");
  const [error, setError] = React.useState("");
  const change = async (f: Finding, to: string) => {
    setBusy(f.finding_id);
    setError("");
    try { await monitor.updateFinding(f.finding_id, { status: to }); onChanged?.(); }
    catch (e) { setError(friendlyMessage(e)); }
    finally { setBusy(""); }
  };
  if (!rows.length) return <p className="text-[12px] text-text-muted">No findings on the register.</p>;
  return (
    <div className="space-y-1" data-testid="sm-register">
      {error ? <p className="text-[12px] text-negative" role="alert">{error}</p> : null}
      <div className={cn("overflow-auto rounded-md border border-border", compact && "max-h-[320px]")}>
        <table className="w-full text-[12px]">
          <thead className="sticky top-0 bg-surface-sunken"><tr>
            <th className={TH}>Ref</th>{showScorecard ? <th className={TH}>Scorecard</th> : null}<th className={TH}>Severity</th><th className={TH}>Finding</th>
            <th className={TH}>Owner</th><th className={TH}>Due</th><th className={TH}>Status</th><th className={TH} /></tr></thead>
          <tbody>
            {rows.map((f) => (
              <tr key={f.finding_id} className="border-t border-border align-top" data-testid="sm-finding" data-id={f.finding_id} data-overdue={f.overdue} data-status={f.status}>
                <td className="whitespace-nowrap px-3 py-1.5 text-text-muted">{f.finding_id}</td>
                {showScorecard ? <td className="px-3 py-1.5">{f.scorecard_id}</td> : null}
                <td className={cn("px-3 py-1.5 font-medium", f.severity === "High" ? "text-negative" : f.severity === "Medium" ? "text-warning" : "text-text-secondary")}>{f.severity}</td>
                <td className="px-3 py-1.5"><p className="font-medium text-text-primary">{f.title}</p>
                  {compact ? null : <p className="text-text-secondary">{f.remediation}</p>}</td>
                <td className="px-3 py-1.5">{person(f.owner)}</td>
                <td className={cn("whitespace-nowrap px-3 py-1.5", f.overdue && "font-semibold text-negative")}>{day(f.due_on)}{f.overdue ? ` · ${f.days_overdue}d late` : ""}</td>
                <td className="whitespace-nowrap px-3 py-1.5 capitalize">{f.status.replace("_", " ")}</td>
                <td className="whitespace-nowrap px-3 py-1.5">
                  {NEXT[f.status].map((n) => (
                    <button key={n.to} type="button" disabled={busy === f.finding_id} onClick={() => void change(f, n.to)} data-testid={`sm-finding-${n.to}`}
                            className="mr-1 rounded border border-border px-1.5 py-0.5 text-[11px] hover:border-accent disabled:opacity-40">{n.label}</button>))}
                </td>
              </tr>))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
