"use client";

/**
 * The population charts at the head of every What-If thread (PLAN_R3 S3-5):
 * stage mix, EAD by rating (global order) or behaviour score band, the sector
 * or product split, the top warning reasons and the Early Warning bands.
 *
 * Drawn through the shared Plotly surface (hover with formatted values, legend
 * toggles, zoom, PNG download from the mode bar; `data-rendered="true"` once
 * drawn). The figures themselves are pure functions in lib/v5/whatif-summary.
 */

import * as React from "react";

import { Plot } from "@/components/v5/ews/plot";
import type { PopulationSummary } from "@/lib/v5/whatif";
import { type Figure, bandsFigure, gradeFigure, reasonsFigure, splitFigure, stageFigure } from "@/lib/v5/whatif-summary";

export { BAND_COLOUR, STAGE_COLOUR } from "@/lib/v5/whatif-summary";

type Props = { summary: PopulationSummary; testId: string; filename: string };

function Draw({ figure, testId, filename, ariaLabel }: { figure: Figure; testId: string; filename: string; ariaLabel: string }) {
  return <Plot data={figure.data} layout={figure.layout} height={figure.height} testId={testId} filename={filename} ariaLabel={ariaLabel} />;
}

export function StageDonut({ summary, testId, filename }: Props) {
  return <Draw figure={stageFigure(summary)} testId={testId} filename={filename} ariaLabel={`EAD by IFRS 9 stage for ${summary.scope_label}`} />;
}

export function GradeBars({ summary, testId, filename }: Props) {
  return <Draw figure={gradeFigure(summary)} testId={testId} filename={filename}
               ariaLabel={`EAD by ${summary.grades.label.toLowerCase()}, ${summary.grades.order.join(", ")}`} />;
}

export function SplitBars({ summary, testId, filename }: Props) {
  return <Draw figure={splitFigure(summary)} testId={testId} filename={filename} ariaLabel={`EAD by ${summary.split.label.toLowerCase()}`} />;
}

export function ReasonBars({ summary, testId, filename }: Props) {
  return <Draw figure={reasonsFigure(summary)} testId={testId} filename={filename}
               ariaLabel={`Top Early Warning reasons by ${summary.labels.owners.toLowerCase()} and by EAD`} />;
}

export function BandBars({ summary, testId, filename }: Props) {
  return <Draw figure={bandsFigure(summary)} testId={testId} filename={filename}
               ariaLabel={`${summary.labels.owners} by Early Warning band, worst first`} />;
}

export { React };
