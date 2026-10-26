"use client";

/**
 * The interactive history charts of Borrower 360, drawn through the v5 Plotly
 * surface (`components/v5/ews/plot.tsx`). Every figure is built from what the
 * Borrower 360 service returned for the tab; nothing is recomputed.
 *
 * Ratings are drawn on the global rating scale (lib/v5/ratings.ts): the axis
 * is the scale position, labelled with the grade, AAA at the top.
 */

import * as React from "react";

import { ChartInfo } from "@/components/v5/core/chart-explain";
import { Plot } from "@/components/v5/ews/plot";
import type { DomainId, Row, Tab } from "@/lib/v5/b360";
import { shortPeriod } from "@/lib/v5/ews";
import { RATING_ORDER, ratingRank, sortByRating } from "@/lib/v5/ratings";

import { tabChartExplain } from "./explain";

type Figure = Record<string, unknown>;

const C1 = "var(--ipm-chart-1)";
const C2 = "var(--ipm-chart-2)";
const C3 = "var(--ipm-chart-3)";
const C4 = "var(--ipm-chart-4)";
const WARNING = "var(--ipm-warning)";
const NEGATIVE = "var(--ipm-negative)";
const ACCENT = "var(--ipm-accent)";
const MUTED = "var(--ipm-text-muted)";
const PALETTE = [C1, C2, C3, C4, "var(--ipm-chart-5)", "var(--ipm-chart-6)", "var(--ipm-chart-7)", "var(--ipm-chart-8)"];

const n = (v: unknown): number | null => (v === null || v === undefined || v === "" ? null : Number(v));

function line(name: string, x: string[], y: (number | null)[], color: string, extra: Figure = {}): Figure {
  return { type: "scatter", mode: "lines+markers", name, x, y, connectgaps: false,
           line: { color, width: 2 }, marker: { color, size: 6 },
           hovertemplate: "%{y:,.2f}<extra>%{fullData.name}</extra>", ...extra };
}

function bar(name: string, x: string[], y: (number | null)[], color: string, extra: Figure = {}): Figure {
  return { type: "bar", name, x, y, marker: { color }, hovertemplate: "%{y:,.2f}<extra>%{fullData.name}</extra>",
           ...extra };
}

const sarm = (name: string) => ({ hovertemplate: `SAR %{y:,.3f}m<extra>${name}</extra>` });
const y2 = (title: string, extra: Figure = {}): Figure => ({ overlaying: "y", side: "right", showgrid: false,
                                                             title: { text: title, font: { size: 11 } }, ...extra });
const yTitle = (title: string, extra: Figure = {}): Figure => ({ title: { text: title, font: { size: 11 } }, ...extra });

function tableRows(tab: Tab, id: string): Row[] {
  return tab.tables.find((t) => t.id === id)?.rows ?? [];
}

/** One figure per history tab; null where a tab has no chart. */
export function figureFor(domain: DomainId, tab: Tab): { data: Figure[]; layout: Figure; label: string } | null {
  const s = tab.series ?? [];
  const x = s.map((r) => shortPeriod(String(r.period)));
  const corporate = domain === "corporate";
  const xaxis = { type: "category" };
  switch (tab.key) {
    case "exposure": {
      const long = tableRows(tab, "by_exposure");
      const ids = [...new Set(long.map((r) => String(r.exposure_id)))];
      const periods = s.map((r) => String(r.period));
      const data = ids.map((id, i) => bar(`EAD ${id}`, x, periods.map((p) => {
        const hit = long.find((r) => r.period === p && r.exposure_id === id);
        return hit ? n(hit.ead_sar_mn) : null;
      }), PALETTE[i % PALETTE.length], sarm(`EAD ${id}`)));
      data.push(line("ECL (total)", x, s.map((r) => n(r.ecl)), NEGATIVE, { yaxis: "y2", ...sarm("ECL") }));
      return { data, label: "EAD by exposure (stacked) and total ECL, every period",
               layout: { barmode: "stack", xaxis, yaxis: yTitle("EAD (SAR m)", { rangemode: "tozero" }),
                         yaxis2: y2("ECL (SAR m)", { rangemode: "tozero" }), margin: { l: 64, r: 64, t: 12, b: 40 } } };
    }
    case "ratings": {
      if (corporate) {
        const ranks = s.map((r) => ratingRank(String(r.rating_current ?? "")));
        const orig = s.map((r) => ratingRank(String(r.rating_at_origination ?? "")));
        const seen = [...ranks, ...orig].filter((v) => v < RATING_ORDER.length);
        const lo = Math.max(0, Math.min(...seen) - 1);
        const hi = Math.min(RATING_ORDER.length - 1, Math.max(...seen) + 1);
        const ticks = RATING_ORDER.map((_, i) => i).filter((i) => i >= lo && i <= hi);
        return {
          label: "Rating every quarter on the global scale (AAA at the top), with PD",
          data: [
            line("Rating", x, ranks, C1, { line: { color: C1, width: 2, shape: "hv" },
                                          customdata: s.map((r) => r.rating_current),
                                          hovertemplate: "%{customdata}<extra>Rating</extra>" }),
            line("At origination", x, orig, MUTED, { mode: "lines", line: { color: MUTED, width: 1, dash: "dot" },
                                                    customdata: s.map((r) => r.rating_at_origination),
                                                    hovertemplate: "%{customdata}<extra>At origination</extra>" }),
            line("PD (TTC 12m, %)", x, s.map((r) => (n(r.pd_ttc_12m) ?? 0) * 100), WARNING,
                 { yaxis: "y2", hovertemplate: "%{y:.2f}%<extra>PD (TTC 12m)</extra>" }),
          ],
          layout: { xaxis, margin: { l: 56, r: 64, t: 12, b: 40 },
                    yaxis: yTitle("Rating", { tickvals: ticks, ticktext: ticks.map((i) => RATING_ORDER[i]),
                                              range: [hi + 0.5, lo - 0.5], zeroline: false }),
                    yaxis2: y2("PD (%)", { rangemode: "tozero", ticksuffix: "%" }) },
        };
      }
      const order = (tab.meta.band_order as string[] | undefined) ?? ["A", "B", "C", "D", "E"];
      return {
        label: "Behaviour score and band, every month (band A best .. E worst)",
        data: [
          line("Behaviour score", x, s.map((r) => n(r.behaviour_score)), C1,
               { customdata: s.map((r) => r.score_band), hovertemplate: "%{y:.0f} (band %{customdata})<extra>Behaviour score</extra>" }),
          line("Band", x, s.map((r) => n(r.band_rank)), WARNING,
               { yaxis: "y2", line: { color: WARNING, width: 1.5, shape: "hv" }, customdata: s.map((r) => r.score_band),
                 hovertemplate: "%{customdata}<extra>Band</extra>" }),
        ],
        layout: { xaxis, yaxis: yTitle("Score"), margin: { l: 56, r: 56, t: 12, b: 40 },
                  yaxis2: y2("Band", { tickvals: order.map((_, i) => i), ticktext: order, range: [order.length - 0.5, -0.5] }) },
      };
    }
    case "stage-dpd": {
      const per = (tab.meta.dpd_by_exposure as { exposure_id: string; periods: string[]; dpd: (number | null)[] }[] | undefined) ?? [];
      const data: Figure[] = per.map((e, i) => line(`DPD ${e.exposure_id}`, e.periods.map(shortPeriod), e.dpd,
                                                    PALETTE[i % PALETTE.length],
                                                    { hovertemplate: "%{y} days<extra>%{fullData.name}</extra>" }));
      data.push(line("Worst stage", x, s.map((r) => n(r.worst_stage)), NEGATIVE,
                     { yaxis: "y2", line: { color: NEGATIVE, width: 2, shape: "hv", dash: "dash" },
                       hovertemplate: "stage %{y}<extra>Worst stage</extra>" }));
      return { data, label: "Days past due by exposure, and the worst IFRS 9 stage, every period",
               layout: { xaxis: { type: "category", categoryorder: "array", categoryarray: x },
                         yaxis: yTitle("DPD (days)", { rangemode: "tozero" }), margin: { l: 56, r: 56, t: 12, b: 40 },
                         yaxis2: y2("Stage", { tickvals: [1, 2, 3], range: [0.5, 3.5] }) } };
    }
    case "collateral":
      if (!s.length) return null;
      return { label: "Collateral value and cover of EAD, every period",
               data: [bar("Collateral value", x, s.map((r) => n(r.value)), C3, sarm("Collateral value")),
                      line("Collateral over EAD (%)", x, s.map((r) => n(r.cover_pct)), C1,
                           { yaxis: "y2", hovertemplate: "%{y:.1f}%<extra>Collateral over EAD</extra>" })],
               layout: { xaxis, yaxis: yTitle("SAR m", { rangemode: "tozero" }), yaxis2: y2("%", { rangemode: "tozero" }),
                         margin: { l: 56, r: 56, t: 12, b: 40 } } };
    case "covenants":
      if (!s.length) return null;
      return { label: "Covenant breaches and the lowest headroom, every quarter",
               data: [bar("Breaches", x, s.map((r) => n(r.breaches)), NEGATIVE, { hovertemplate: "%{y}<extra>Breaches</extra>" }),
                      bar("On watch", x, s.map((r) => n(r.watch)), WARNING, { hovertemplate: "%{y}<extra>On watch</extra>" }),
                      line("Lowest headroom (%)", x, s.map((r) => n(r.min_headroom_pct)), C1,
                           { yaxis: "y2", hovertemplate: "%{y:.1f}%<extra>Lowest headroom</extra>" })],
               layout: { barmode: "stack", xaxis, yaxis: yTitle("Covenants", { rangemode: "tozero", dtick: 1 }),
                         yaxis2: y2("Headroom (%)"), margin: { l: 56, r: 56, t: 12, b: 40 } } };
    case "financials":
      if (corporate) {
        return { label: "Revenue and EBITDA (SAR m), leverage and DSCR (x), every quarter",
                 data: [bar("Revenue", x, s.map((r) => n(r.revenue_sar_mn)), C1, sarm("Revenue")),
                        bar("EBITDA", x, s.map((r) => n(r.ebitda_sar_mn)), C3, sarm("EBITDA")),
                        line("Leverage (x)", x, s.map((r) => n(r.leverage_x)), NEGATIVE,
                             { yaxis: "y2", hovertemplate: "%{y:.2f}x<extra>Leverage</extra>" }),
                        line("DSCR (x)", x, s.map((r) => n(r.dscr_x)), WARNING,
                             { yaxis: "y2", hovertemplate: "%{y:.2f}x<extra>DSCR</extra>" })],
                 layout: { barmode: "group", xaxis, yaxis: yTitle("SAR m", { rangemode: "tozero" }),
                           yaxis2: y2("Times (x)", { rangemode: "tozero" }), margin: { l: 56, r: 56, t: 12, b: 40 } } };
      }
      if (!s.length) return null;
      return { label: "Account inflows (SAR thousand) and the balance buffer, every month",
               data: [bar("Inflows", x, s.map((r) => n(r.total_inflows_sar_k)), C1,
                          { hovertemplate: "SAR %{y:,.1f}k<extra>Inflows</extra>" }),
                      line("3-month average", x, s.map((r) => n(r.inflows_3m_avg_sar_k)), C3,
                           { hovertemplate: "SAR %{y:,.1f}k<extra>3-month average</extra>" }),
                      line("Balance buffer (months)", x, s.map((r) => n(r.balance_buffer_months)), WARNING,
                           { yaxis: "y2", hovertemplate: "%{y:.1f} months<extra>Balance buffer</extra>" })],
               layout: { xaxis, yaxis: yTitle("SAR thousand", { rangemode: "tozero" }),
                         yaxis2: y2("Months", { rangemode: "tozero" }), margin: { l: 56, r: 56, t: 12, b: 40 } } };
    case "group": {
      if (!corporate) return null;
      const mix = sortByRating(tableRows(tab, "rating_mix") as { rating: string; borrowers: number; warned: number }[], "rating");
      const xs = mix.map((m) => m.rating);
      return { label: "Group members by rating, in the global rating order (best to worst)",
               data: [bar("Borrowers", xs, mix.map((m) => m.borrowers), C1, { hovertemplate: "%{y}<extra>Borrowers</extra>" }),
                      bar("Warned (EWS moderate or worse)", xs, mix.map((m) => m.warned), WARNING,
                          { hovertemplate: "%{y}<extra>Warned</extra>" })],
               layout: { barmode: "group", xaxis: { type: "category", categoryorder: "array", categoryarray: xs },
                         yaxis: yTitle("Borrowers", { rangemode: "tozero" }) } };
    }
    case "ews": {
      const floors = (tab.meta.band_floors as Record<string, number> | undefined) ?? {};
      const shapes = Object.entries(floors).map(([band, f]) => ({
        type: "line", xref: "paper", x0: 0, x1: 1, yref: "y", y0: f - 0.5, y1: f - 0.5,
        line: { color: band === "critical" ? NEGATIVE : band === "high" ? WARNING : ACCENT, width: 1, dash: "dot" },
      }));
      const annotations = Object.entries(floors).map(([band, f]) => ({
        xref: "paper", x: 1, xanchor: "right", yref: "y", y: f - 0.5, yanchor: "bottom", showarrow: false,
        text: `${band} ≥ ${f}`, font: { size: 10, color: MUTED },
      }));
      return { label: "Early Warning score every period, and the rules fired by source",
               data: [line("Score", x, s.map((r) => n(r.score)), NEGATIVE,
                           { customdata: s.map((r) => r.band), hovertemplate: "%{y} (%{customdata})<extra>Score</extra>" }),
                      bar("Bank internal", x, s.map((r) => n(r.bank_internal)), C1, { yaxis: "y2", hovertemplate: "%{y}<extra>Bank internal rules</extra>" }),
                      bar("Bureau", x, s.map((r) => n(r.bureau)), C2, { yaxis: "y2", hovertemplate: "%{y}<extra>Bureau rules</extra>" }),
                      bar("Open Banking", x, s.map((r) => n(r.open_banking)), C3, { yaxis: "y2", hovertemplate: "%{y}<extra>Open Banking rules</extra>" })],
               layout: { barmode: "stack", xaxis: { type: "category", anchor: "y2" }, shapes, annotations,
                         margin: { l: 56, r: 16, t: 12, b: 40 },
                         yaxis: { domain: [0.42, 1], rangemode: "tozero", title: { text: "Score", font: { size: 11 } } },
                         yaxis2: { domain: [0, 0.32], anchor: "x", rangemode: "tozero", dtick: 1,
                                   title: { text: "Rules fired", font: { size: 11 } } } } };
    }
    case "bureau":
      if (!s.length) return null;
      if (corporate) {
        return { label: "Exposure at other lenders and external DPD, every quarter",
                 data: [bar("External exposure", x, s.map((r) => n(r.external_exposure_sar_mn)), C2, sarm("External exposure")),
                        line("External DPD", x, s.map((r) => n(r.external_dpd_days)), NEGATIVE,
                             { yaxis: "y2", hovertemplate: "%{y} days<extra>External DPD</extra>" })],
                 layout: { xaxis, yaxis: yTitle("SAR m", { rangemode: "tozero" }),
                           yaxis2: y2("Days", { rangemode: "tozero" }), margin: { l: 56, r: 56, t: 12, b: 40 } } };
      }
      return { label: "Bureau score and external DPD, every month",
               data: [line("Bureau score", x, s.map((r) => n(r.bureau_score)), C1, { hovertemplate: "%{y}<extra>Bureau score</extra>" }),
                      bar("External DPD", x, s.map((r) => n(r.external_dpd_days)), NEGATIVE,
                          { yaxis: "y2", opacity: 0.6, hovertemplate: "%{y} days<extra>External DPD</extra>" })],
               layout: { xaxis, yaxis: yTitle("Score (300-900)"), yaxis2: y2("Days", { rangemode: "tozero" }),
                         shapes: [{ type: "line", xref: "paper", x0: 0, x1: 1, yref: "y", y0: 560, y1: 560,
                                    line: { color: WARNING, width: 1, dash: "dot" } }],
                         margin: { l: 56, r: 56, t: 12, b: 40 } } };
    case "open-banking":
      if (!s.length) return null;
      if (corporate) {
        return { label: "Operating inflows and their trend, every quarter",
                 data: [bar("Operating inflows", x, s.map((r) => n(r.operating_inflows_sar_mn)), C3, sarm("Operating inflows")),
                        line("Inflow trend (%)", x, s.map((r) => n(r.inflow_trend_pct)), WARNING,
                             { yaxis: "y2", hovertemplate: "%{y:.1f}%<extra>Inflow trend</extra>" })],
                 layout: { xaxis, yaxis: yTitle("SAR m", { rangemode: "tozero" }), yaxis2: y2("%"),
                           margin: { l: 56, r: 56, t: 12, b: 40 } } };
      }
      return { label: "Inflows, salary credits and balance buffer, every month",
               data: [bar("Inflows", x, s.map((r) => n(r.total_inflows_sar_k)), C3,
                          { hovertemplate: "SAR %{y:,.1f}k<extra>Inflows</extra>" }),
                      line("Balance buffer (months)", x, s.map((r) => n(r.balance_buffer_months)), WARNING,
                           { yaxis: "y2", hovertemplate: "%{y:.1f}<extra>Balance buffer</extra>" }),
                      line("Salary missing", x, s.map((r) => n(r.salary_interruption_flag)), NEGATIVE,
                           { yaxis: "y2", mode: "markers", marker: { color: NEGATIVE, size: 9, symbol: "x" },
                             hovertemplate: "%{y}<extra>Salary missing (1 = yes)</extra>" })],
               layout: { xaxis, yaxis: yTitle("SAR thousand", { rangemode: "tozero" }),
                         yaxis2: y2("Months / flag", { rangemode: "tozero" }), margin: { l: 56, r: 56, t: 12, b: 40 } } };
    default:
      return null;
  }
}

export function TabChart({ domain, tab }: { domain: DomainId; tab: Tab }) {
  const f = figureFor(domain, tab);
  if (!f) return null;
  return (
    <div className="space-y-1" data-testid={`b360-chart-${tab.key}`}>
      <div className="flex items-center gap-2">
        <p className="text-[12px] font-semibold text-text-primary">{f.label}</p>
        <ChartInfo title={f.label} explain={tabChartExplain(tab.key, f.label, f.data)}
                   hint="Hover for values; drag to zoom, double-click to reset; click the legend to hide a series." />
      </div>
      <Plot data={f.data} layout={f.layout} height={tab.key === "ews" ? 360 : 300}
            testId={`b360-plot-${tab.key}`} ariaLabel={f.label} filename={`borrower-360-${tab.key}`} />
    </div>
  );
}
