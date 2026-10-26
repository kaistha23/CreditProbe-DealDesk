"use client";

/**
 * "Save as analysis" and "Save as investigation" on a Cockpit answer (FX-12, docs/v5/FROZEN_EXCEPTIONS.md).
 *
 * The frozen answer row renders this component and nothing else changes there. What is saved is read back from the
 * Cockpit's own API as the Cockpit published it (the run's final response; the thread's every turn), so no figure is
 * re-typed: the analysis keeps the narrative, tables, charts and numeric claims, and the Workspace derives the
 * recompute recipe from the table (backend/workspace_v5/compute.infer_book_spec).
 */

import { readStatus, readThread, type RenderedChart, type RenderedTable } from "@/components/cockpit-v4/client";
import { SaveButton } from "@/components/v5/workspace/save";
import { ws3, type Artifact } from "@/lib/v5/workspace-r3";

function tableArtifact(t: RenderedTable): Artifact {
  const rows = (t.rows ?? []).map((r) => r.canonical as Record<string, string | number | null>);
  const unit = (c: string) => {
    const u = String(t.column_units?.[c] ?? "");
    if (/sar/i.test(u) || c.endsWith("_sar_mn")) return "sar_mn" as const;
    if (/pct|%/.test(u) || c.endsWith("_pct")) return "pct" as const;
    return rows.length && rows.every((r) => typeof r[c] === "number") ? ("num" as const) : ("text" as const);
  };
  return { kind: "table", title: t.title || "Result", columns: t.columns.map((c) => ({ key: c, label: c.replace(/_/g, " "), unit: unit(c) })), rows: rows.slice(0, 500) };
}

function chartArtifact(c: RenderedChart): Artifact | null {
  const y = c.y_columns?.[0];
  if (!y || !c.points?.length) return null;
  return { kind: "chart", title: c.title, unit: /sar/i.test(c.unit) ? "sar_mn" : /pct|%/.test(c.unit) ? "pct" : "int",
           points: c.points.map((p) => ({ label: String(p.label), value: Number(p.values?.[y] ?? 0) })) };
}

export function AnswerWorkspaceSave({ question, threadId, runId }: { question: string; threadId?: string; runId: string }) {
  if (!threadId) return null;
  const href = `/cockpit/thread/${encodeURIComponent(threadId)}`;
  const saveAnalysis = async (title: string) => {
    const [status, thread] = await Promise.all([readStatus(runId), readThread(threadId)]);
    const fr = status.final_response;
    if (!fr) throw new Error("This answer has not finished yet.");
    return ws3.createAnalysis({
      title, question, origin: "cockpit", book: thread.domain_id,
      answer: { narrative: fr.narrative, tables: fr.tables, charts: fr.charts, numeric_claims: fr.numeric_claims, run_id: runId },
      origin_link: { type: "cockpit-thread", id: threadId, label: `Cockpit · ${thread.domain_short_label || thread.domain_id}`, href },
    });
  };
  const saveInvestigation = async (title: string) => {
    const thread = await readThread(threadId);
    const turns = thread.turns.flatMap((t) => [
      { role: "user" as const, text: t.question, at: t.created_at },
      { role: "assistant" as const, text: t.answer?.narrative ?? "", at: t.created_at,
        artifacts: [...(t.answer?.tables ?? []).map(tableArtifact),
                    ...(t.answer?.charts ?? []).map(chartArtifact).filter((a): a is Artifact => a !== null)] },
    ]);
    return ws3.importInvestigation({
      source: { type: "cockpit-thread", id: threadId, label: `Cockpit · ${thread.title || question.slice(0, 80)}`, href },
      title, turns, continue_href: href,
    });
  };
  return (
    <>
      <SaveButton kind="analysis" defaultTitle={question} save={saveAnalysis} testId="v4-action-save-analysis" />
      <SaveButton kind="investigation" defaultTitle={question} save={saveInvestigation} testId="v4-action-save-investigation" />
    </>
  );
}
