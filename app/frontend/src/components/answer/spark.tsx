"use client";

/**
 * A static Plotly sparkline for cards and rows (R12: every chart in the app draws through the one Plotly surface).
 *
 * Long lists carry several of these per row, so the Plotly figure is mounted only once the box comes within
 * ~200px of the viewport; until then an empty box of the same height holds the space. The figure is static (no
 * hover, no mode bar). A null value is a GAP, never a zero; reference `bands` are dotted lines; the last measured
 * point carries a small dot.
 */

import * as React from "react";

import { Plot } from "@/components/v5/ews/plot";
import { TONE, sparkFigure } from "@/lib/plotly-theme";

/** True once the element has come within `rootMargin` of the viewport (stays true). */
export function useNearViewport<T extends Element>(rootMargin = "200px"): [React.RefObject<T | null>, boolean] {
  const ref = React.useRef<T | null>(null);
  const [near, setNear] = React.useState(false);
  React.useEffect(() => {
    if (near) return;
    const el = ref.current;
    if (!el) return;
    if (typeof IntersectionObserver === "undefined") {
      const timer = setTimeout(() => setNear(true), 0);
      return () => clearTimeout(timer);
    }
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) { setNear(true); observer.disconnect(); }
    }, { rootMargin });
    observer.observe(el);
    return () => observer.disconnect();
  }, [near, rootMargin]);
  return [ref, near];
}

export function PlotlySpark({ values, color = TONE.accent, bands = [], height = 28, ariaLabel, testId, className }: {
  values: (number | null)[];
  color?: string;
  /** Horizontal reference lines, in the series' own units (dotted). */
  bands?: number[];
  height?: number;
  ariaLabel: string;
  testId?: string;
  className?: string;
}) {
  const [ref, near] = useNearViewport<HTMLDivElement>();
  const clean = values.map((v) => (typeof v === "number" && Number.isFinite(v) ? v : null));
  const figure = sparkFigure(clean, { color, bands });
  let last = -1;
  clean.forEach((v, i) => { if (v !== null) last = i; });
  const data = last >= 0
    ? [...figure.data, { type: "scatter", mode: "markers", x: [last], y: [clean[last]], marker: { color, size: 4 }, hoverinfo: "skip" }]
    : figure.data;
  // Keep the reference lines inside the picture (as the hand-drawn spark did) and a lone point centred.
  const measured = [...clean.filter((v): v is number => v !== null), ...bands];
  const layout: Record<string, unknown> = { ...figure.layout,
    xaxis: { ...(figure.layout.xaxis as object), range: clean.length > 1 ? [0, clean.length - 1] : [-1, 1] } };
  if (measured.length) {
    const lo = Math.min(...measured), hi = Math.max(...measured);
    const pad = (hi - lo || Math.abs(hi) || 1) * 0.12;
    layout.yaxis = { ...(figure.layout.yaxis as object), range: [lo - pad, hi + pad] };
  }
  return (
    <div ref={ref} className={className} style={{ minHeight: height }} data-testid={testId ? `${testId}-box` : undefined}>
      {near ? <Plot data={data} layout={layout} height={height} staticPlot ariaLabel={ariaLabel} testId={testId} filename="sparkline" /> : null}
    </div>
  );
}
