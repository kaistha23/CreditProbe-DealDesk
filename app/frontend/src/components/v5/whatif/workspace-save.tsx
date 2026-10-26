"use client";

/**
 * What-If thread header: Save as analysis (the current scenario; the Workspace re-runs it through the What-If engine,
 * so the saved figures are the engine's) and Save as investigation (every turn of the thread, with its results as
 * tables and key figures). PLAN_R3 S3-2.
 */

import { SaveButton } from "@/components/v5/workspace/save";
import type { Answer, Result, ThreadView } from "@/lib/v5/whatif";
import { ws3, type Artifact, type TurnIn } from "@/lib/v5/workspace-r3";

function resultArtifacts(r: Result): Artifact[] {
  const c = r.cards;
  return [
    { kind: "figures", title: `${r.method_name}, ${r.period}`, period: r.period, figures: [
      { key: "reported_ecl", label: "Reported ECL", value: c.reported_ecl, unit: "sar_mn" },
      { key: "scenario_ecl", label: "Scenario ECL", value: c.scenario_ecl, unit: "sar_mn" },
      { key: "change", label: "ECL change", value: c.change, unit: "sar_mn" },
      { key: "change_pct", label: "ECL change %", value: c.change_pct, unit: "pct" },
    ] },
    { kind: "table", title: `ECL by ${r.labels.segment.toLowerCase()}, ${r.period}`, period: r.period,
      columns: [{ key: "segment", label: r.labels.segment, unit: "text" }, { key: "ecl_before", label: "ECL before", unit: "sar_mn" },
                { key: "ecl_after", label: "ECL after", unit: "sar_mn" }, { key: "change", label: "Change", unit: "sar_mn" }],
      rows: r.by_segment.map((s) => ({ segment: s.segment, ecl_before: s.ecl_before, ecl_after: s.ecl_after, change: s.change })) },
  ];
}

function answerTurn(a: Answer): TurnIn {
  const text: string[] = [];
  const artifacts: Artifact[] = [];
  for (const b of a.blocks) {
    if (b.type === "text") text.push(b.markdown);
    else if (b.type === "commentary" || b.type === "refusal" || b.type === "error" || b.type === "report") text.push(b.text);
    else if (b.type === "understood") text.push(`Understood: ${b.steps.map((s) => s.restatement).join("; ")} on ${b.population}.`);
    else if (b.type === "question") text.push(b.text);
    else if (b.type === "proposal") text.push(`Proposed: ${b.steps.map((s) => s.restatement).join("; ")} on ${b.population}.`);
    else if (b.type === "answer") text.push(b.markdown);
    else if (b.type === "likelihood") text.push(`${b.label}. ${b.note}`);
    else if (b.type === "result") artifacts.push(...resultArtifacts(b.result));
  }
  return { role: "assistant", text: text.join("\n\n").slice(0, 20000), artifacts };
}

/** The header's own button size (Save, Share, Word report, Excel). */
const SMALL = "h-[26px] gap-1 px-2 text-[12px] font-normal";

export function WhatIfWorkspaceSave({ thread, busy }: { thread: ThreadView; busy: boolean }) {
  const href = `/what-if/thread/${encodeURIComponent(thread.thread_id)}`;
  const source = { type: "whatif-thread", id: thread.thread_id, label: `What-If · ${thread.title}`, href };
  const lastQ = thread.turns[thread.turns.length - 1];
  const question = lastQ ? (lastQ.answer.question_display || lastQ.question) : thread.title;
  return (
    <>
      <SaveButton kind="analysis" testId="whatif-save-analysis" className={SMALL} defaultTitle={`What-If: ${thread.title}`}
                  disabled={!thread.state.has_scenario || !thread.state.scenario || busy}
                  save={(title) => ws3.createAnalysis({
                    title, question, origin: "whatif", book: thread.domain, period: thread.period,
                    whatif: { scenario: thread.state.scenario ?? {}, method: thread.state.method ?? "delta" }, origin_link: source,
                  })} />
      <SaveButton kind="investigation" testId="whatif-save-investigation" className={SMALL} defaultTitle={thread.title}
                  disabled={!thread.turns.length || busy}
                  save={(title) => ws3.importInvestigation({
                    source, title, continue_href: href, period: thread.period,
                    turns: thread.turns.flatMap((t) => [{ role: "user" as const, text: t.answer.question_display || t.question }, answerTurn(t.answer)]),
                  })} />
    </>
  );
}
