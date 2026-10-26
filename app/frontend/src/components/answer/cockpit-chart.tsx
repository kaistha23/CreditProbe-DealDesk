"use client";

/**
 * A frozen Cockpit answer chart drawn through the shared Plotly surface (presentation-only exception: Plotly
 * rendering). The figure is `cockpitFigure`'s: positions from the canonical numbers, every visible string the
 * server's. When there is no figure (nothing plottable) the caller's `fallback` renders instead, so which charts
 * appear is decided exactly as before.
 */

import * as React from "react";

import type { RenderedChart } from "@/components/cockpit-v4/client";
import { Plot } from "@/components/v5/ews/plot";

import { cockpitFigure } from "./cockpit-figure";

/** A download name built from the chart's title (letters, digits and dashes only). */
function fileNameOf(chart: RenderedChart): string {
  const slug = (chart.title || chart.kind || "chart").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 60);
  return `cockpit-${slug || "chart"}`;
}

export function CockpitPlotlyChart({ chart, fallback }: { chart: RenderedChart; fallback: React.ReactNode }) {
  const figure = React.useMemo(() => cockpitFigure(chart), [chart]);
  if (!figure) return <>{fallback}</>;
  return (
    <div data-testid="v4-chart-plotly" data-kind={chart.kind} className="min-w-0">
      <Plot
        data={figure.data}
        layout={figure.layout}
        height={figure.height}
        ariaLabel={chart.title}
        filename={fileNameOf(chart)}
        testId="v4-plotly-chart"
      />
    </div>
  );
}
