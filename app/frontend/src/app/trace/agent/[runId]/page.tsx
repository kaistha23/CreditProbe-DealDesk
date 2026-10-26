"use client";

/**
 * The full trace of one agent run (PLAN_R11_AGENTS A3), in the Trace page pattern: what was asked, how it was
 * planned (and by which planner), every step with its inputs, output summary, figures, duration and the
 * engine's own calculation trace id, the findings with their evidence, the narrative with its citation check,
 * the proposals and their decisions, and the budget spent.
 */

import * as React from "react";
import { Bot } from "lucide-react";

import { BackLink } from "@/components/layout/back-link";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { fmtFigure, useAgentRun } from "@/components/v5/core/agent-run";
import { Chip } from "@/components/v5/dealdesk/kit";
import { bySeverity, duration, plannerLabel, severityTone, toolLabel } from "@/lib/v5/agents";

export default function AgentTracePage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = React.use(params);
  const { run, error } = useAgentRun(runId);
  if (!run) {
    return error ? <p className="p-6 text-[13px] text-negative" role="alert">{error}</p> : <Skeleton className="h-[32rem] w-full" />;
  }
  const spent = run.budget?.spent ?? {};
  const limits = run.budget?.limits ?? {};
  return (
    <div className="mx-auto max-w-[1200px] space-y-4 p-4" data-testid="agent-trace">
      <BackLink href={run.agent.startsWith("dealdesk") && run.scope ? `/deal-desk/${encodeURIComponent(run.scope)}` : "/trace"} label={run.agent.startsWith("dealdesk") ? "Back to the deal" : "Back to Trace"} />
      <Card className="p-4">
        <div className="flex items-start gap-3">
          <Bot className="mt-1 h-5 w-5 text-accent" />
          <div className="min-w-0 flex-1">
            <p className="text-[11px] font-medium uppercase tracking-[0.08em] text-text-muted">Agent run · {run.agent}</p>
            <h1 className="text-[18px] font-semibold text-text-primary">{run.goal}</h1>
            {run.output?.headline ? <p className="text-[14px] text-text-primary">{String(run.output.headline)}</p> : null}
            <p className="mt-1 text-[12px] text-text-secondary">
              {plannerLabel(run)} · {run.status} · {run.trigger.replace("_", " ")} · started {run.created_at.replace("T", " ").slice(0, 19)}
              {run.finished_at ? ` · ${duration(run.duration_ms)}` : ""}{run.user ? ` · by ${run.user}` : ""}
            </p>
          </div>
          <Chip tone={run.status === "completed" ? "positive" : run.status === "failed" ? "negative" : "warning"}>{run.status}</Chip>
        </div>
        {run.narrative ? <p className="mt-3 whitespace-pre-line text-[13px] leading-6 text-text-primary">{run.narrative}</p> : null}
        {run.citation_check?.ok === false ? (
          <p className="mt-1 text-[12px] text-warning">{run.citation_check.removed ?? 0} sentence(s) with a figure not traced to a step were removed.</p>
        ) : null}
        {run.stopped ? <p className="mt-1 text-[12px] text-warning">{run.stopped}</p> : null}
      </Card>

      <Card className="p-4">
        <h2 className="mb-2 text-[14px] font-semibold text-text-primary">Plan and steps</h2>
        {run.plan?.notes?.filter((n) => !n.startsWith("model:")).length ? (
          <ul className="mb-2 text-[12px] text-text-secondary">{run.plan.notes.filter((n) => !n.startsWith("model:")).map((n, i) => <li key={i}>{n}</li>)}</ul>
        ) : null}
        <table className="w-full border-collapse text-[12px]">
          <thead>
            <tr className="text-left text-[11px] uppercase tracking-[0.06em] text-text-muted">
              <th className="border-b border-border px-2 py-2">Step</th><th className="border-b border-border px-2 py-2">Tool</th>
              <th className="border-b border-border px-2 py-2">Status</th><th className="border-b border-border px-2 py-2">Output</th>
              <th className="border-b border-border px-2 py-2">Figures</th><th className="border-b border-border px-2 py-2 text-right">Time</th>
            </tr>
          </thead>
          <tbody>
            {(run.plan?.steps ?? []).map((s) => (
              <tr key={s.id} className="align-top" data-testid={`trace-step-${s.id}`}>
                <td className="border-b border-border px-2 py-1.5 tabular-nums">{s.id}</td>
                <td className="border-b border-border px-2 py-1.5">
                  <span className="font-medium">{toolLabel(s.tool)}</span>
                  <span className="block text-[11px] text-text-muted">{s.why}{s.added_by ? ` · added by ${s.added_by}` : ""}</span>
                  <span className="block truncate text-[11px] text-text-muted" title={JSON.stringify(s.inputs)}>{Object.entries(s.inputs).map(([k, v]) => `${k}: ${typeof v === "object" ? "…" : String(v)}`).join(", ")}</span>
                </td>
                <td className="border-b border-border px-2 py-1.5"><Chip tone={s.status === "done" ? "positive" : s.status === "failed" ? "negative" : s.status === "skipped" ? "warning" : "neutral"}>{s.status}</Chip></td>
                <td className="border-b border-border px-2 py-1.5 text-text-secondary">{s.summary}{s.error ? <span className="block text-negative">{s.error}</span> : null}
                  {s.trace_id ? <span className="block text-[11px] text-text-muted">Engine trace {s.trace_id}</span> : null}</td>
                <td className="w-[240px] border-b border-border px-2 py-1.5 text-[11px] text-text-secondary">
                  {Object.entries(s.figures ?? {}).slice(0, 8).map(([k, v]) => <span key={k} className="flex justify-between gap-2 whitespace-nowrap"><span className="truncate">{k.replace(/_/g, " ")}</span><span className="tabular-nums">{fmtFigure(k, v)}</span></span>)}
                </td>
                <td className="border-b border-border px-2 py-1.5 text-right tabular-nums">{duration(s.duration_ms)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {run.findings.length ? (
        <Card className="p-4">
          <h2 className="mb-2 text-[14px] font-semibold text-text-primary">Findings</h2>
          <ul className="divide-y divide-border">
            {bySeverity(run.findings).map((f, i) => (
              <li key={i} className="flex items-start gap-2 py-1.5 text-[12px]">
                <Chip tone={severityTone(f.severity)}>{f.severity}</Chip>
                <span className="min-w-0 flex-1"><span className="font-medium">{f.title}</span>{f.detail ? <span className="block text-text-secondary">{f.detail}</span> : null}</span>
                <span className="text-[11px] text-text-muted">{f.evidence.join(", ")}</span>
              </li>
            ))}
          </ul>
        </Card>
      ) : null}

      <Card className="p-4">
        <h2 className="mb-2 text-[14px] font-semibold text-text-primary">Proposals and budget</h2>
        <ul className="mb-2 space-y-1 text-[12px]">
          {(run.approvals ?? []).map((a) => (
            <li key={a.id}>{a.title} · <span className="text-text-secondary">{a.status}{a.decided_by ? ` by ${a.decided_by}` : ""} · needs {a.approver_role}</span></li>
          ))}
          {!run.approvals?.length ? <li className="text-text-muted">No proposals</li> : null}
        </ul>
        <p className="text-[12px] text-text-secondary">
          {["tasks", "model_calls", "rows", "runtime_seconds"].map((m) => `${m.replace(/_/g, " ")} ${spent[m] ?? 0} of ${limits[m] ?? "–"}`).join(" · ")}
        </p>
      </Card>
    </div>
  );
}
