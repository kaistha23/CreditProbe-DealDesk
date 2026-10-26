/**
 * PLAN_R10 C3: the charts a validation shows in its thread, above the test tables, so a run reads as
 * pictures first: ROC and CAP; Gini and KS by period and by segment; observed against expected by grade;
 * PSI by period, CSI by variable; override outcomes. The service names them (result.key_charts, and the
 * thread's validation block); an older stored result without that list falls back to KEY_CHARTS.
 */

import type { ChartData, Result } from "@/lib/v5/scorecard";

/** The key charts in reading order (the same list as backend/scorecard_v5/engine.py KEY_CHARTS). */
export const KEY_CHARTS = ["roc", "cap", "gini_trend", "ks_trend", "gini_segment", "ks_segment", "oe_grade", "psi_trend", "csi_bar", "ovr_outcome"] as const;

/** The key charts of a result that have data, in the order named (the service's list, else KEY_CHARTS). */
export function keyCharts(result: Pick<Result, "sections"> & { key_charts?: string[] }, ids?: readonly string[]): ChartData[] {
  const order = ids?.length ? ids : result.key_charts?.length ? result.key_charts : KEY_CHARTS;
  const byId = new Map<string, ChartData>();
  for (const s of result.sections ?? []) for (const c of s.charts ?? []) byId.set(c.id, c);
  return order.map((id) => byId.get(id)).filter((c): c is ChartData => Boolean(c && c.figure?.data?.length));
}
