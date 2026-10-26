"use client";

/**
 * The interactive charts of the v5 Early Warning screen, all drawn through
 * `plot.tsx` (Plotly): the level's trend, the comparison of its children,
 * borrowers by rating, a card's full trend (in a dialog) and a customer's
 * history. Every figure here is built from what the service returned; nothing
 * is recomputed.
 */

import * as React from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  type Card as LevelCard, type CustomerDetail, type RatingMix, type TrendPoint, shortPeriod,
} from "@/lib/v5/ews";
import { RATING_ORDER, sortByRating } from "@/lib/v5/ratings";

import { Plot } from "./plot";

type Figure = Record<string, unknown>;

const WARNING = "var(--ipm-warning)";
const NEGATIVE = "var(--ipm-negative)";
const ACCENT = "var(--ipm-accent)";
const MUTED = "var(--ipm-text-muted)";

function line(name: string, x: string[], y: (number | null)[], color: string, extra: Figure = {}): Figure {
  return {
    type: "scatter", mode: "lines+markers", name, x, y, connectgaps: false,
    line: { color, width: 2 }, marker: { color, size: 6 },
    hovertemplate: "%{y:,}<extra>%{fullData.name}</extra>",
    ...extra,
  };
}

const Cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

/** Warned, high or critical and forward risk over the trend periods. */
export function LevelTrendPlot({ trend, owners, testId, height = 260 }: {
  trend: TrendPoint[]; owners: string; testId?: string; height?: number;
}) {
  const x = trend.map((p) => shortPeriod(p.period));
  const data = [
    line(`Warned ${owners}`, x, trend.map((p) => p.customers_warned), WARNING),
    line("High or critical", x, trend.map((p) => p.high_or_critical), NEGATIVE),
    line("Forward risk", x, trend.map((p) => p.forward_risk), ACCENT),
  ];
  const layout = {
    xaxis: { type: "category" },
    yaxis: { rangemode: "tozero", tickformat: ",d", title: { text: Cap(owners), font: { size: 11 } } },
  };
  return <Plot data={data} layout={layout} height={height} testId={testId} filename="early-warning-trend"
               ariaLabel={`Trend of warned ${owners}, high or critical and forward risk over ${trend.length} periods`} />;
}

/**
 * A card's full trend: counts, default-entry rate and high/critical exposure,
 * three panels on one shared period axis.
 */
export function CardTrendPlot({ trend, owners, testId, filename }: {
  trend: TrendPoint[]; owners: string; testId?: string; filename?: string;
}) {
  const x = trend.map((p) => shortPeriod(p.period));
  const data = [
    line(`Warned ${owners}`, x, trend.map((p) => p.customers_warned), WARNING),
    line("High or critical", x, trend.map((p) => p.high_or_critical), NEGATIVE),
    line("Forward risk", x, trend.map((p) => p.forward_risk), ACCENT, { line: { color: ACCENT, width: 2, dash: "dot" } }),
    line("Default-entry rate (%)", x, trend.map((p) => p.odr_pct), NEGATIVE,
         { yaxis: "y2", hovertemplate: "%{y:.2f}%<extra>%{fullData.name}</extra>" }),
    line("High/critical EAD (SAR m)", x, trend.map((p) => p.exposure_severe), ACCENT,
         { yaxis: "y3", hovertemplate: "SAR %{y:,.1f}m<extra>%{fullData.name}</extra>" }),
  ];
  const layout = {
    margin: { l: 64, r: 16, t: 12, b: 40 },
    xaxis: { type: "category", anchor: "y3" },
    yaxis: { domain: [0.68, 1], rangemode: "tozero", tickformat: ",d", title: { text: Cap(owners), font: { size: 11 } } },
    yaxis2: { domain: [0.36, 0.6], anchor: "x", rangemode: "tozero", ticksuffix: "%", title: { text: "Default-entry", font: { size: 11 } } },
    yaxis3: { domain: [0, 0.28], anchor: "x", rangemode: "tozero", tickformat: ",.0f", title: { text: "SAR m", font: { size: 11 } } },
  };
  return <Plot data={data} layout={layout} height={520} testId={testId} filename={filename ?? "early-warning-card-trend"}
               ariaLabel={`Trend of warned ${owners}, default-entry rate and high or critical exposure over ${trend.length} periods`} />;
}

/** The level's children side by side: warned customers and high/critical exposure. */
export function ComparePlot({ cards, owners, kind, onOpen, testId }: {
  cards: LevelCard[]; owners: string; kind: string; onOpen?: (key: string) => void; testId?: string;
}) {
  const x = cards.map((c) => c.label);
  const keys = cards.map((c) => c.key);
  const data = [
    { type: "bar", name: `Warned ${owners}`, x, y: cards.map((c) => c.customers_warned), customdata: keys,
      offsetgroup: "warned", marker: { color: WARNING }, hovertemplate: "%{y:,}<extra>%{fullData.name}</extra>" },
    { type: "bar", name: "High/critical exposure (SAR m)", x, y: cards.map((c) => c.exposure_severe), customdata: keys,
      yaxis: "y2", offsetgroup: "severe", marker: { color: NEGATIVE },
      hovertemplate: "SAR %{y:,.1f}m<extra>%{fullData.name}</extra>" },
  ];
  const layout = {
    barmode: "group",
    bargap: 0.25,
    margin: { l: 56, r: 64, t: 12, b: 40 },
    xaxis: { type: "category", tickangle: cards.length > 6 ? -30 : 0 },
    yaxis: { rangemode: "tozero", tickformat: ",d", title: { text: `Warned ${owners}`, font: { size: 11, color: WARNING } } },
    yaxis2: { overlaying: "y", side: "right", rangemode: "tozero", tickformat: ",.0f", showgrid: false,
              title: { text: "High/critical EAD (SAR m)", font: { size: 11, color: NEGATIVE } } },
  };
  return <Plot data={data} layout={layout} height={cards.length > 6 ? 340 : 300} testId={testId}
               filename={`early-warning-${kind}-comparison`}
               ariaLabel={`Warned ${owners} and high or critical exposure for each of ${cards.length} ${kind}`}
               onPointClick={onOpen ? (key) => { if (typeof key === "string") onOpen(key); } : undefined} />;
}

/** Borrowers and warned borrowers per rating grade, AAA to D. */
export function RatingPlot({ mix, owners, testId }: { mix: RatingMix[]; owners: string; testId?: string }) {
  const rows = sortByRating(mix, "rating");
  const x = rows.map((r) => r.rating);
  const order = [...RATING_ORDER, ...x.filter((r) => !RATING_ORDER.includes(r))];
  const data = [
    { type: "bar", name: Cap(owners), x, y: rows.map((r) => r.borrowers), marker: { color: ACCENT },
      hovertemplate: "%{y:,}<extra>%{fullData.name}</extra>" },
    { type: "bar", name: "Warned", x, y: rows.map((r) => r.warned), marker: { color: WARNING },
      customdata: rows.map((r) => [r.high_or_critical, r.exposure]),
      hovertemplate: "%{y:,} (high/critical %{customdata[0]:,} · exposure SAR %{customdata[1]:,.1f}m)<extra>%{fullData.name}</extra>" },
  ];
  const layout = {
    barmode: "group",
    bargap: 0.2,
    xaxis: { type: "category", categoryorder: "array", categoryarray: order, title: { text: "Rating", font: { size: 11 } } },
    yaxis: { rangemode: "tozero", tickformat: ",d", title: { text: Cap(owners), font: { size: 11 } } },
  };
  return <Plot data={data} layout={layout} height={280} testId={testId} filename="early-warning-ratings"
               ariaLabel={`${Cap(owners)} and warned ${owners} by rating`} />;
}

/** A customer's history: score, days past due and exposure on one shared period axis. */
export function CustomerHistoryPlot({ history, warnedMin, testId }: {
  history: CustomerDetail["history"]; warnedMin: number; testId?: string;
}) {
  const x = history.map((h) => shortPeriod(h.period));
  const data = [
    line("Score", x, history.map((h) => h.score), WARNING,
         { customdata: history.map((h) => h.band), hovertemplate: "%{y} (%{customdata})<extra>Score</extra>" }),
    line("Days past due", x, history.map((h) => h.dpd), NEGATIVE, { yaxis: "y2" }),
    line("Exposure (SAR m)", x, history.map((h) => h.exposure), ACCENT,
         { yaxis: "y3", hovertemplate: "SAR %{y:,.2f}m<extra>Exposure</extra>" }),
  ];
  const ref = (yref: string, y: number) => ({
    type: "line", xref: "paper", x0: 0, x1: 1, yref, y0: y, y1: y, layer: "below",
    line: { color: MUTED, width: 1, dash: "dot" },
  });
  const layout = {
    margin: { l: 64, r: 16, t: 12, b: 40 },
    xaxis: { type: "category", anchor: "y3" },
    yaxis: { domain: [0.68, 1], rangemode: "tozero", title: { text: "Score", font: { size: 11 } } },
    yaxis2: { domain: [0.36, 0.6], anchor: "x", rangemode: "tozero", title: { text: "DPD", font: { size: 11 } } },
    yaxis3: { domain: [0, 0.28], anchor: "x", rangemode: "tozero", title: { text: "SAR m", font: { size: 11 } } },
    shapes: [ref("y", warnedMin), ref("y2", 30)],
    annotations: [
      { xref: "paper", x: 1, xanchor: "right", yref: "y", y: warnedMin, yanchor: "bottom", showarrow: false,
        text: "warning threshold", font: { size: 10, color: MUTED } },
      { xref: "paper", x: 1, xanchor: "right", yref: "y2", y: 30, yanchor: "bottom", showarrow: false,
        text: "30 DPD", font: { size: 10, color: MUTED } },
    ],
  };
  return <Plot data={data} layout={layout} height={440} testId={testId} filename="early-warning-customer-history"
               ariaLabel={`Score, days past due and exposure over ${history.length} periods`} />;
}

/** A modal over the page: Escape, the close button or the backdrop closes it. */
export function ChartDialog({ title, subtitle, onClose, children, testId = "ews-trend-dialog" }: {
  title: string; subtitle?: string; onClose: () => void; children: React.ReactNode; testId?: string;
}) {
  const closeRef = React.useRef<HTMLButtonElement | null>(null);
  const onCloseRef = React.useRef(onClose);
  React.useEffect(() => { onCloseRef.current = onClose; });
  React.useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    const keydown = (e: KeyboardEvent) => { if (e.key === "Escape") { e.preventDefault(); onCloseRef.current(); } };
    window.addEventListener("keydown", keydown);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeRef.current?.focus();
    return () => {
      window.removeEventListener("keydown", keydown);
      document.body.style.overflow = overflow;
      opener?.focus?.();
    };
  }, []);
  const titleId = React.useId();
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
         onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <Card role="dialog" aria-modal="true" aria-labelledby={titleId} data-testid={testId}
            className="max-h-[92vh] w-full max-w-4xl overflow-y-auto p-4 shadow-xl">
        <div className="flex items-start gap-3">
          <div className="min-w-0">
            <p id={titleId} className="text-sm font-semibold text-text-primary">{title}</p>
            {subtitle ? <p className="text-[11px] text-text-muted">{subtitle}</p> : null}
          </div>
          <Button ref={closeRef} variant="outline" size="sm" className="ml-auto" onClick={onClose}
                  data-testid="ews-trend-close" aria-label="Close chart">
            <X className="size-3.5" aria-hidden /> Close
          </Button>
        </div>
        <div className="mt-2">{children}</div>
      </Card>
    </div>,
    document.body,
  );
}

export const CHART_HINT = "Hover for values · click a legend entry to hide it · drag to zoom, double-click to reset · camera icon saves a PNG.";
