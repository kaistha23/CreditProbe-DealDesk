import assert from "node:assert/strict";
import { test } from "node:test";

import {
  DARK_TOKENS, LIGHT_TOKENS, PALETTE, isDarkTheme, plotlyConfig, resolveVars, safeHover, seriesColor, sparkFigure, themedLayout, tokenLookup,
} from "./plotly-theme.ts";

test("the palette is the eight theme chart tokens, and series colours wrap", () => {
  assert.equal(PALETTE.length, 8);
  assert.equal(seriesColor(0), "var(--ipm-chart-1)");
  assert.equal(seriesColor(9), "var(--ipm-chart-2)");
  assert.equal(seriesColor(-1), "var(--ipm-chart-8)");
});

test("light and dark token maps cover the same tokens, and every palette token", () => {
  assert.deepEqual(Object.keys(LIGHT_TOKENS).sort(), Object.keys(DARK_TOKENS).sort());
  for (const v of PALETTE) assert.ok(LIGHT_TOKENS[v.slice(4, -1)], v);
  assert.ok(isDarkTheme("midnight") && !isDarkTheme("executive-light") && !isDarkTheme(undefined));
});

test("a chart's own layout wins, axes keep the house gridlines, an axis title string becomes {text}", () => {
  const l = themedLayout({ hovermode: "closest", xaxis: { title: "Tenor, years", dtick: 1 }, hoverlabel: { bgcolor: "red" } }, 300, "Inter");
  assert.equal(l.height, 300);
  assert.equal(l.hovermode, "closest");
  const x = l.xaxis as Record<string, unknown>;
  assert.equal(x.dtick, 1);
  assert.equal(x.gridcolor, "var(--ipm-border)");
  assert.equal((x.title as Record<string, unknown>).text, "Tenor, years");
  const hover = l.hoverlabel as Record<string, unknown>;
  assert.equal(hover.bgcolor, "red");
  assert.equal(hover.bordercolor, "var(--ipm-border)");
  assert.equal((l.font as Record<string, unknown>).family, "Inter");
  assert.ok(l.yaxis, "a y axis is themed even when the chart names none");
});

test("var() colours resolve against the light and the dark theme", () => {
  const fig = { marker: { color: ["var(--ipm-chart-1)", "var(--ipm-accent)"] }, line: { color: "var(--nope)" } };
  const light = resolveVars(fig, tokenLookup(false));
  const dark = resolveVars(fig, tokenLookup(true));
  assert.deepEqual(light.marker.color, ["#2563A8", "#10527a"]);
  assert.deepEqual(dark.marker.color, ["#3B82C4", "#4d9fd4"]);
  assert.equal(light.line.color, "#888");
});

test("the config downloads a 2x PNG with no logo; a static plot has no mode bar", () => {
  const c = plotlyConfig({ filename: "x" });
  assert.equal(c.displaylogo, false);
  assert.deepEqual(c.toImageButtonOptions, { format: "png", filename: "x", scale: 2 });
  assert.equal(plotlyConfig({ staticPlot: true }).displayModeBar, false);
});

test("safe hover: a long float hovers at two decimals, a formatted trace is left alone", () => {
  const [a, b] = safeHover([{ y: [1.23456789] }, { y: [1.23456789], hovertemplate: "%{y}" }]);
  assert.equal(a.yhoverformat, ",.2f");
  assert.equal(b.yhoverformat, undefined);
});

test("a sparkline has no axes, no hover and keeps gaps as gaps", () => {
  const f = sparkFigure([1, null, 3], { bands: [2] });
  assert.equal((f.data[0] as Record<string, unknown>).connectgaps, false);
  assert.equal((f.layout.xaxis as Record<string, unknown>).visible, false);
  assert.equal((f.layout.shapes as unknown[]).length, 1);
});
