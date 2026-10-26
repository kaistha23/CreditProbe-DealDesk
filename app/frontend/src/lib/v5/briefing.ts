/**
 * PLAN_R9 G4: the Workspace Intelligence Briefing — the pure part.
 *
 * The component fetches the book from the Early Warning service (the same
 * service and the same SAR-million figures the Cockpit's books and Early
 * Warning read, so totals reconcile); everything here turns that snapshot into
 * the KPI band, "what our intelligence found this morning" and the four
 * Plotly figures. No React, so node --test covers it.
 */

import type { PackId } from "./intelligence-packs.ts";

export type Book = "corporate" | "retail";

export interface StageSlice { ead: number; ecl: number; n: number }
export interface PeriodPoint {
  period: string;
  stage: Record<1 | 2 | 3, StageSlice>;
  critical: number; high: number; moderate: number; low: number;
  ecl: number; exposure: number;
}
export interface Segment { label: string; exposure: number; ecl: number; eclChange: number | null; severe: number }
export interface CrmSummary { breaches: number; high: number; checksInBreach: number; topArticle: string | null; topTitle: string | null; shortfall: number }

export interface BookSnapshot {
  book: Book;
  period: string;
  priorPeriod: string | null;
  moneyUnit: string;
  exposure: number;
  ecl: number;
  prevEcl: number | null;
  critical: number;
  high: number;
  warnedExposure: number;
  topReason: { name: string; customers: number; change: number | null } | null;
  stage: Record<1 | 2 | 3, StageSlice>;
  segments: Segment[];
  trend: PeriodPoint[];
  crm: CrmSummary | null;
  /** P4 Accepted Risk Watch (Session C's `watch` domain, GET /api/v1/ews/intel/watch); null until it is served. */
  watch?: WatchSummary | null;
}
export interface WatchSummary { names: number; escalations: number; missed: number; due: number;
                                top: { id: string; name: string; why: string }[] }

export interface Kpi { key: string; label: string; value: string; sub?: string; href: string; tone?: "neutral" | "warn" | "bad" }
export interface Finding { id: string; pack: PackId; rule: string; article?: string; headline: string; figure: string; action: string; href: string }

const DASH = "—";
const ok = (v: number | null | undefined): v is number => typeof v === "number" && Number.isFinite(v);

/** SAR millions in the house format: >= 1,000m in bn (2 dp), else m (1 dp). */
export function money(m: number | null | undefined): string {
  if (!ok(m)) return DASH;
  const abs = Math.abs(m);
  const f = (v: number, dp: number) => v.toLocaleString("en-US", { minimumFractionDigits: dp, maximumFractionDigits: dp });
  if (abs >= 1000) return `SAR ${f(m / 1000, 2)}bn`;
  return `SAR ${f(m, abs < 10 ? 2 : 1)}m`;
}
export function share(part: number | null | undefined, whole: number | null | undefined, dp = 1): string {
  if (!ok(part) || !ok(whole) || whole === 0) return DASH;
  return `${((part / whole) * 100).toFixed(dp)}%`;
}
export function int(v: number | null | undefined): string {
  return ok(v) ? Math.round(v).toLocaleString("en-US") : DASH;
}

export function emptyStage(): Record<1 | 2 | 3, StageSlice> {
  return { 1: { ead: 0, ecl: 0, n: 0 }, 2: { ead: 0, ecl: 0, n: 0 }, 3: { ead: 0, ecl: 0, n: 0 } };
}

/** The service's stage_mix rows ({value|stage, n, ead|ead_sar_mn, ecl|ecl_sar_mn}) as stage 1/2/3. */
export function stageFromRows(rows: Record<string, unknown>[] | null | undefined): Record<1 | 2 | 3, StageSlice> {
  const out = emptyStage();
  for (const r of rows ?? []) {
    const s = Number(r.value ?? r.stage);
    if (s !== 1 && s !== 2 && s !== 3) continue;
    out[s].ead += Number(r.ead_sar_mn ?? r.ead ?? 0) || 0;
    out[s].ecl += Number(r.ecl_sar_mn ?? r.ecl ?? 0) || 0;
    out[s].n += Number(r.n ?? 0) || 0;
  }
  return out;
}

export function coverage(s: BookSnapshot): number | null {
  return s.exposure ? s.ecl / s.exposure : null;
}

/** PLAN_R10 G-TILES: four tiles, one row. Coverage rides on the ECL tile; watch and CRM breaches are cards below. */
export function kpis(s: BookSnapshot): Kpi[] {
  const s2 = s.stage[2].ead, s3 = s.stage[3].ead;
  const eclMove = ok(s.prevEcl) ? s.ecl - s.prevEcl : null;
  const move = eclMove === null ? "" : ` · ${eclMove >= 0 ? "+" : "−"}${money(Math.abs(eclMove))}`;
  return [
    { key: "exposure", label: "Exposure", value: money(s.exposure), sub: `as of ${s.period}`, href: "/" },
    { key: "ecl", label: "ECL", value: money(s.ecl), sub: `coverage ${share(s.ecl, s.exposure, 2)}${move}`,
      href: "/what-if", tone: eclMove !== null && eclMove > 0 ? "warn" : "neutral" },
    { key: "stage23", label: "Stage 2 + 3 share", value: share(s2 + s3, s.exposure),
      sub: `S2 ${share(s2, s.exposure)} · S3 ${share(s3, s.exposure)}`, href: "/borrower-360", tone: "warn" },
    { key: "ews", label: "EWS Critical / High", value: `${int(s.critical)} / ${int(s.high)}`,
      sub: s.exposure && ok(s.warnedExposure) ? `${share(s.warnedExposure, s.exposure)} of exposure` : "customers",
      href: "/early-warning", tone: s.critical > 0 ? "bad" : "neutral" },
  ];
}

/** "What our intelligence found this morning": 5–7 findings, each with a number, its pack and an action. */
export function findings(s: BookSnapshot): Finding[] {
  const out: Finding[] = [];
  const s2 = s.stage[2].ead, s3 = s.stage[3].ead;
  if (s.critical + s.high > 0) {
    out.push({ id: "ews", pack: "P3", rule: "P3-EWS-01",
      headline: `${int(s.critical)} customers are Critical and ${int(s.high)} High on early warning`,
      figure: money(s.warnedExposure), action: "Review the Critical names", href: "/early-warning" });
  }
  if (s.stage[2].ead > 0) {
    out.push({ id: "sicr", pack: "P2", rule: "P2-SICR-02",
      headline: `Stage 2 holds ${share(s2, s.exposure)} of exposure; SICR evidence is ready per client`,
      figure: money(s2), action: "Open SICR in Borrower 360", href: "/borrower-360" });
  }
  if (ok(s.prevEcl)) {
    const d = s.ecl - s.prevEcl;
    const top = [...s.segments].filter((x) => ok(x.eclChange)).sort((a, b) => Math.abs(b.eclChange!) - Math.abs(a.eclChange!))[0];
    out.push({ id: "ecl", pack: "P6", rule: "P6-MOV-01",
      headline: `ECL ${d >= 0 ? "rose" : "fell"} ${money(Math.abs(d))} since ${s.priorPeriod ?? "the prior period"}${top ? `; ${top.label} moved most` : ""}`,
      figure: money(s.ecl), action: "See what moved ECL", href: "/what-if" });
  }
  if (s.crm && s.crm.breaches > 0) {
    // The breach's own article, not a fixed rule: the most-breached check names it.
    out.push({ id: "crm", pack: "P1", rule: "", article: s.crm.topArticle || "CBUAE CRM Standards",
      headline: `${int(s.crm.breaches)} CBUAE CRM breaches across ${int(s.crm.checksInBreach)} checks${s.crm.topTitle ? `, most on “${s.crm.topTitle}”` : ""}${s.crm.shortfall > 0 ? `; provision shortfall ${money(s.crm.shortfall)}` : ""}`,
      figure: int(s.crm.breaches),
      action: "Open the breach checks", href: "/early-warning" });
  }
  if (s3 > 0) {
    out.push({ id: "s3", pack: "P6", rule: "P6-FLR-03",
      headline: `Stage 3 coverage is ${share(s.stage[3].ecl, s3)} against the CBUAE floors`,
      figure: money(s3), action: "Check coverage against floors", href: "/" });
  }
  const conc = [...s.segments].sort((a, b) => b.exposure - a.exposure)[0];
  if (conc && s.exposure) {
    out.push({ id: "conc", pack: "P5", rule: "P5-GRP-01",
      headline: `${conc.label} is the largest concentration at ${share(conc.exposure, s.exposure)} of the book`,
      figure: money(conc.exposure), action: "See the network in Borrower 360", href: "/borrower-360" });
  }
  if (s.watch && s.watch.escalations > 0) {
    out.push({ id: "watch", pack: "P4", rule: "P4-ESC-02",
      headline: `${int(s.watch.escalations)} accepted risks worsened past their approval conditions and should escalate`,
      figure: int(s.watch.escalations), action: "Review in Early Warning", href: "/early-warning" });
  }
  if (s.topReason) {
    out.push({ id: "reason", pack: "P4", rule: "P4-ESC-02",
      headline: `Top warning reason: ${s.topReason.name} on ${int(s.topReason.customers)} customers${ok(s.topReason.change) && s.topReason.change !== 0 ? ` (${s.topReason.change > 0 ? "+" : ""}${int(s.topReason.change)})` : ""}`,
      figure: int(s.topReason.customers), action: "Check accepted risks that worsened", href: "/early-warning" });
  }
  return out.slice(0, 7);
}

// ------------------------------------------------------------- figures

type Fig = { data: Record<string, unknown>[]; layout: Record<string, unknown> };
const C = { s1: "var(--ipm-positive)", s2: "var(--ipm-warning)", s3: "var(--ipm-negative)", accent: "var(--ipm-accent)", muted: "var(--ipm-text-muted)" };

export function stageMixFigure(s: BookSnapshot): Fig {
  const x = s.trend.map((p) => p.period);
  const pc = (p: PeriodPoint, k: 1 | 2 | 3) => {
    const t = p.stage[1].ead + p.stage[2].ead + p.stage[3].ead;
    return t ? Math.round((p.stage[k].ead / t) * 1000) / 10 : 0;
  };
  return {
    data: ([1, 2, 3] as const).map((k) => ({
      type: "bar", name: `Stage ${k}`, x, y: s.trend.map((p) => pc(p, k)),
      marker: { color: k === 1 ? C.s1 : k === 2 ? C.s2 : C.s3 },
      hovertemplate: `Stage ${k}: %{y:.1f}% of exposure<extra>%{x}</extra>`,
    })),
    layout: { barmode: "stack", yaxis: { ticksuffix: "%", range: [0, 100] }, legend: { orientation: "h", y: -0.2 } },
  };
}

export function eclMovementFigure(s: BookSnapshot): Fig {
  const moves = s.segments.filter((g) => ok(g.eclChange) && g.eclChange !== 0)
    .sort((a, b) => Math.abs(b.eclChange!) - Math.abs(a.eclChange!)).slice(0, 4);
  const shown = moves.reduce((n, g) => n + g.eclChange!, 0);
  const total = ok(s.prevEcl) ? s.ecl - s.prevEcl : shown;
  const other = Math.round((total - shown) * 10) / 10;
  const labels = [s.priorPeriod ?? "Prior", ...moves.map((g) => g.label), ...(other ? ["Other"] : []), s.period];
  const values = [s.prevEcl ?? s.ecl - total, ...moves.map((g) => g.eclChange!), ...(other ? [other] : []), s.ecl];
  const measure = ["absolute", ...moves.map(() => "relative"), ...(other ? ["relative"] : []), "total"];
  return {
    data: [{
      type: "waterfall", x: labels, y: values, measure,
      increasing: { marker: { color: C.s3 } }, decreasing: { marker: { color: C.s1 } }, totals: { marker: { color: C.accent } },
      connector: { line: { color: "var(--ipm-border)" } },
      hovertemplate: "%{x}: SAR %{y:,.1f}m<extra></extra>",
    }],
    layout: { yaxis: { tickprefix: "SAR ", ticksuffix: "m", tickformat: ",.0f" }, showlegend: false },
  };
}

export function ewsTrendFigure(s: BookSnapshot): Fig {
  const x = s.trend.map((p) => p.period);
  const band = (k: "critical" | "high" | "moderate" | "low", name: string, color: string) => ({
    type: "scatter", mode: "lines+markers", name, x, y: s.trend.map((p) => p[k]), line: { color, width: 2 },
    hovertemplate: `${name}: %{y:,} customers<extra>%{x}</extra>`,
  });
  return {
    data: [band("critical", "Critical", C.s3), band("high", "High", C.s2), band("moderate", "Moderate", C.accent), band("low", "Low", C.muted)],
    layout: { legend: { orientation: "h", y: -0.2 }, yaxis: { title: { text: "Customers" } } },
  };
}

export function sectorFigure(s: BookSnapshot): Fig {
  const top = [...s.segments].sort((a, b) => b.exposure - a.exposure).slice(0, 8).reverse();
  return {
    data: [{
      type: "bar", orientation: "h", y: top.map((g) => g.label), x: top.map((g) => g.exposure),
      marker: { color: C.accent },
      customdata: top.map((g) => (s.exposure ? Math.round((g.exposure / s.exposure) * 1000) / 10 : 0)),
      hovertemplate: "%{y}: SAR %{x:,.1f}m (%{customdata:.1f}% of book)<extra></extra>",
    }],
    layout: { xaxis: { tickprefix: "SAR ", ticksuffix: "m", tickformat: ",.0f" }, showlegend: false },
  };
}

/** "Good morning" by the hour, in the reader's own clock. */
export function greeting(hour: number): string {
  return hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
}
