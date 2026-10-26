"use client";

/** A saved conversation (an investigation's turns) and its artifacts: tables, key figures, charts, linked objects. */

import Link from "next/link";
import * as React from "react";
import { ArrowUpRight } from "lucide-react";

import { hbarFigure } from "@/components/answer/bar-figure";
import { Card } from "@/components/ui/card";
import { Plot } from "@/components/v5/ews/plot";
import { cn } from "@/lib/utils";
import { formatValue, when, type Unit } from "@/lib/v5/workspace";
import type { Artifact, Col, Turn } from "@/lib/v5/workspace-r3";

import { Prose } from "./parts";

function fmt(v: unknown, unit: Col["unit"]): string {
  return formatValue(v, (unit === "num" ? "int" : unit) as Unit);
}

export function ArtifactView({ a, testId }: { a: Artifact; testId: string }) {
  if (a.kind === "table") {
    return (
      <Card className="overflow-x-auto p-0" data-testid={testId} data-kind="table">
        <p className="border-b border-border px-3 py-2 text-xs font-semibold text-text-primary">{a.title}</p>
        <table className="w-full text-xs">
          <thead>
            <tr>{a.columns.map((c) => <th key={c.key} className={cn("px-3 py-1.5 font-medium text-text-muted", c.unit !== "text" ? "text-right" : "text-left")}>{c.label}</th>)}</tr>
          </thead>
          <tbody>
            {a.rows.slice(0, 25).map((r, i) => (
              <tr key={i} className="border-t border-border">
                {a.columns.map((c) => <td key={c.key} className={cn("px-3 py-1 tabular-nums", c.unit !== "text" && "text-right")}>{fmt(r[c.key], c.unit)}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
        {a.rows.length > 25 ? <p className="px-3 py-1.5 text-[11px] text-text-muted">{a.rows.length - 25} more rows</p> : null}
      </Card>
    );
  }
  if (a.kind === "figures") {
    return (
      <div className="grid grid-cols-2 gap-2 md:grid-cols-4" data-testid={testId} data-kind="figures">
        {a.figures.map((f) => (
          <Card key={f.key} className="p-2.5" data-value={f.value}>
            <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-text-muted">{f.label}</p>
            <p className="text-[15px] font-semibold tabular-nums">{formatValue(f.value, f.unit)}</p>
          </Card>
        ))}
      </div>
    );
  }
  if (a.kind === "chart") {
    const shown = a.points.slice(0, 15);
    const fig = hbarFigure({ labels: shown.map((p) => p.label), values: shown.map((p) => p.value),
                             text: shown.map((p) => formatValue(p.value, a.unit)) });
    return (
      <Card className="space-y-1.5 p-3" data-testid={testId} data-kind="chart">
        <p className="text-xs font-semibold text-text-primary">{a.title}</p>
        <Plot data={fig.data} layout={fig.layout} height={fig.height} ariaLabel={a.title} filename="workspace-chart" testId={`plot-${testId}`} />
      </Card>
    );
  }
  if (a.kind === "object") {
    return (
      <Link href={a.href} data-testid={testId} data-kind="object"
            className="inline-flex items-center gap-1 rounded-md border border-border bg-surface px-2 py-1 text-xs text-accent hover:bg-surface-hover">
        {a.label} <ArrowUpRight className="size-3" aria-hidden />
      </Link>
    );
  }
  if (a.kind === "text") return <Card className="p-3 text-xs" data-testid={testId}><p className="font-semibold">{a.title}</p><Prose text={a.text} /></Card>;
  return null;
}

export function Conversation({ turns }: { turns: Turn[] }) {
  return (
    <ol className="space-y-3" data-testid="ws-conversation">
      {turns.map((t, i) => (
        <li key={i} data-testid={`ws-turn-${t.role}`} data-index={i}>
          {t.role === "user" ? (
            <div className="flex justify-end">
              <p className="max-w-3xl rounded-lg bg-accent px-3 py-2 text-[13px] text-accent-contrast">{t.text}</p>
            </div>
          ) : (
            <div className={cn("space-y-2 rounded-lg border p-3.5", t.role === "note" ? "border-dashed border-border bg-surface-sunken" : "border-border bg-surface")}>
              <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-text-muted">
                {t.role === "note" ? `Note${t.author ? ` · ${t.author}` : ""}` : "Answer"} · {when(t.at)}
              </p>
              {t.text ? <Prose text={t.text} /> : null}
              {t.artifacts?.length ? (
                <div className="space-y-2">
                  {t.artifacts.map((a, j) => <ArtifactView key={j} a={a} testId={`ws-artifact-${i}-${j}`} />)}
                </div>) : null}
            </div>
          )}
        </li>
      ))}
    </ol>
  );
}
