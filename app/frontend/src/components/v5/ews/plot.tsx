"use client";

/**
 * The one Plotly surface the v5 Early Warning screens draw through.
 *
 * Plotly is imported dynamically, on the client, the first time a chart
 * mounts: the server render and pages without charts never pay for it.
 * Hover, zoom/pan, double-click reset, legend toggle and PNG download (mode
 * bar) are Plotly's own; this wrapper only themes the figure and manages the
 * draw / purge lifecycle.
 *
 * The look (fonts, palette, gridlines, hover, light and dark) is the house theme in `lib/plotly-theme.ts`.
 * Plotly cannot read CSS variables, so a figure may name colours as
 * `var(--ipm-accent)` and they are resolved against the live theme before the
 * draw -- and redrawn when the theme on <html> changes.
 */

import * as React from "react";

import { plotlyConfig, resolveVars, safeHover, themedLayout } from "@/lib/plotly-theme";

interface PlotlyApi {
  react: (el: HTMLElement, data: unknown[], layout: unknown, config?: unknown) => Promise<unknown>;
  purge: (el: HTMLElement) => void;
}

type Figure = Record<string, unknown>;

let plotly: Promise<PlotlyApi> | null = null;

function loadPlotly(): Promise<PlotlyApi> {
  if (!plotly) {
    plotly = import("plotly.js-dist-min").then((m) => {
      const mod = m as unknown as { default?: PlotlyApi } & PlotlyApi;
      return mod.default ?? mod;
    });
    // A failed load (network) may be retried by the next chart.
    plotly.catch(() => { plotly = null; });
  }
  return plotly;
}

/** The house theme (PLAN_R12 N2): fonts, palette, gridlines, hover, light and dark live in lib/plotly-theme.ts. */
export { safeHover };

function liveLookup(): (name: string) => string {
  const style = getComputedStyle(document.documentElement);
  return (name: string) => style.getPropertyValue(name);
}

function pageFont(): string {
  return typeof document !== "undefined" ? getComputedStyle(document.body).fontFamily : "";
}

/** Re-render when the theme on <html> changes (data-theme / class). */
function useThemeVersion(): number {
  const [version, setVersion] = React.useState(0);
  React.useEffect(() => {
    const observer = new MutationObserver(() => setVersion((v) => v + 1));
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class", "data-theme", "style"] });
    return () => observer.disconnect();
  }, []);
  return version;
}

export function Plot({ data, layout, height = 280, testId, ariaLabel, filename = "early-warning-chart",
                       className, onPointClick, scrollZoom = false, staticPlot = false }: {
  data: Figure[]; layout?: Figure; height?: number; testId?: string; ariaLabel: string;
  filename?: string; className?: string;
  /** A picture with no hover or mode bar (sparklines on cards and rows). */
  staticPlot?: boolean;
  /** Zoom with the mouse wheel (a network, a map); charts leave the page scrolling. */
  scrollZoom?: boolean;
  /** Called with the clicked point's customdata (first point under the cursor). */
  onPointClick?: (customdata: unknown) => void;
}) {
  const host = React.useRef<HTMLDivElement | null>(null);
  const chain = React.useRef<Promise<unknown>>(Promise.resolve());
  const clickRef = React.useRef(onPointClick);
  const [error, setError] = React.useState("");
  const theme = useThemeVersion();
  React.useEffect(() => { clickRef.current = onPointClick; });

  // Figures are compared by value: a parent that rebuilds an identical figure does not redraw.
  const figure = JSON.stringify({ data: safeHover(data), layout: layout ?? {}, height, theme, scrollZoom, staticPlot });

  React.useEffect(() => {
    const el = host.current;
    if (!el) return;
    let live = true;
    el.setAttribute("data-rendered", "false");
    chain.current = chain.current
      .catch(() => undefined)
      .then(() => loadPlotly())
      .then(async (Plotly) => {
        if (!live || !el.isConnected) return;
        const { data: d, layout: l, height: h, scrollZoom: zoom, staticPlot: still } = JSON.parse(figure) as {
          data: Figure[]; layout: Figure; height: number; scrollZoom: boolean; staticPlot: boolean };
        const lookup = liveLookup();
        await Plotly.react(el, resolveVars(d, lookup), resolveVars(themedLayout(l, h, pageFont()), lookup),
                           plotlyConfig({ filename, scrollZoom: zoom, staticPlot: still }));
        if (!live) return;
        const node = el as HTMLDivElement & {
          on?: (event: string, fn: (e: { points?: { customdata?: unknown }[] }) => void) => void;
          removeAllListeners?: (event: string) => void;
        };
        node.removeAllListeners?.("plotly_click");
        node.on?.("plotly_click", (e) => {
          const point = e?.points?.[0];
          if (point && clickRef.current) clickRef.current(point.customdata);
        });
        el.setAttribute("data-rendered", "true");
        setError("");
      })
      .catch((failed: unknown) => {
        if (live) setError(failed instanceof Error ? failed.message : String(failed));
      });
    return () => { live = false; };
  }, [figure, filename]);

  // Purge once, on unmount, after any draw in flight has settled.
  React.useEffect(() => {
    const el = host.current;
    return () => {
      if (!el) return;
      chain.current = chain.current
        .catch(() => undefined)
        .then(() => loadPlotly())
        .then((Plotly) => Plotly.purge(el))
        .catch(() => undefined);
    };
  }, []);

  return (
    <>
      <div ref={host} role="img" aria-label={ariaLabel} data-testid={testId} data-rendered="false"
           className={className} style={{ width: "100%", minHeight: height, cursor: onPointClick ? "pointer" : undefined }} />
      {error ? <p role="alert" className="text-[11px] text-negative">The chart could not be drawn ({error}).</p> : null}
    </>
  );
}
