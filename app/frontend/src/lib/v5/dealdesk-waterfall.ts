/**
 * PLAN_R12 Session G (R11_FEEDBACK O1): the RAROC waterfall's labels. The value labels used to sit above each bar
 * ("outside"), where the "Capital benefit" label collided with the next bar's hover box. Each bar's value now goes in its
 * own category label under the axis, on its own line, so nothing drawn inside the plot can overlap: not a label, not a
 * hover box. Pure and tested (dealdesk-waterfall.test.ts).
 */

/** "Risk-adjusted profit" + "1.91" -> "Risk-<br>adjusted<br>profit<br><b>1.91</b>": the name on up to three short lines
 *  (a hyphenated word longer than a line breaks after its hyphen), then the value in bold. */
export function waterfallTick(step: string, value: string, width = 9): string {
  const words = step.split(/\s+/).filter(Boolean).flatMap((w) => (w.length > width && w.includes("-") ? w.replace(/-/g, "-\u0000").split("\u0000") : [w]));
  const lines: string[] = [];
  let cur = "";
  for (const w of words) {
    const glue = cur.endsWith("-") ? "" : " ";
    if (cur && `${cur}${glue}${w}`.length > width) { lines.push(cur); cur = w; } else cur = cur ? `${cur}${glue}${w}` : w;
  }
  if (cur) lines.push(cur);
  const name = lines.length <= 3 ? lines : [lines[0], lines[1], lines.slice(2).join(" ")];
  return [...name, `<b>${value}</b>`].join("<br>");
}

/** Bottom margin (px) that fits the tallest tick: 16 px a line plus the axis padding. */
export function waterfallBottom(ticks: string[]): number {
  const lines = Math.max(1, ...ticks.map((t) => t.split("<br>").length));
  return 24 + lines * 16;
}

/** A bar's value under the axis, in the axis unit (SAR m): a step signed ("+0.36", "−5.26"), a level or total unsigned. */
export function waterfallValue(v: number, signed: boolean): string {
  if (!Number.isFinite(v)) return "–";
  const a = Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (!signed) return v < 0 ? `−${a}` : a;
  return v > 0 ? `+${a}` : v < 0 ? `−${a}` : a;
}
