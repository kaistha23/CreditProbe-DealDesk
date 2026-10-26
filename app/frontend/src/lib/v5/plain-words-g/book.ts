/**
 * R14 G (K34): "In plain words" writers for the Book / Lenses portfolio tools, the renewal autopilot and who to call.
 * Deterministic (N4): every number comes from the panel's own response; same result, same words.
 * (1) what this is; (2) what it says here, with the numbers that matter; (3) what to do / the caveat.
 */
import { lines, n, sar } from "./fmt.ts";

interface Kpi { key: string; value: unknown; unit?: string; text?: string | null }
function kpi(kpis: Kpi[] | undefined, key: string): number | null {
  const k = (kpis ?? []).find((x) => x.key === key);
  return k && typeof k.value === "number" && Number.isFinite(k.value) ? k.value : null;
}
function kpiText(kpis: Kpi[] | undefined, key: string): string | null {
  const k = (kpis ?? []).find((x) => x.key === key);
  return k ? (typeof k.value === "string" ? k.value : k.text ?? null) : null;
}

// ------------------------------------------------------------------ growth headroom

export interface HeadroomLike {
  kpis?: Kpi[]; rows: { slice: string; headroom_sar_mn: number; clears_hurdle: boolean | null; margin_uplift_bps?: number | null }[];
  book?: { sub_ig_share?: number; cost_of_risk_bps?: number } | null;
}
export function writeHeadroom(d: HeadroomLike): string[] {
  const open = d.rows.filter((r) => r.headroom_sar_mn > 1).sort((a, b) => b.headroom_sar_mn - a.headroom_sar_mn);
  const top = open[0];
  const clearing = open.filter((r) => r.clears_hurdle);
  const count = kpi(d.kpis, "open_slices") ?? open.length;
  const of = /of (\d[\d,]*)/.exec(kpiText(d.kpis, "open_slices") ?? "")?.[1] ?? n(d.rows.length);
  return lines(
    "Where the bank can still lend next quarter within its risk appetite",
    top ? `${n(count)} of ${of} sector and rating slices have room; the widest is ${top.slice} with ${sar(top.headroom_sar_mn)}`
      : `None of the ${of} slices has room left at this level`,
    clearing.length ? `${n(clearing.length)} of the widest clear the return hurdle at today's pricing`
      : top ? `None clears the return hurdle at today's pricing${top.margin_uplift_bps ? `: about ${Math.round(top.margin_uplift_bps)} bps more margin needed` : ""}`
      : null,
    "Grow where the price pays; reprice before growing elsewhere",
  );
}

// ------------------------------------------------------------------ exit and sell-down

export interface ExitsLike { kpis?: Kpi[]; rows: { borrower_name: string; action: string; how?: string }[] }
export function writeExits(d: ExitsLike): string[] {
  const cand = kpi(d.kpis, "candidates");
  const cap = kpi(d.kpis, "capital_freed");
  const ecl = kpi(d.kpis, "ecl_freed");
  const lost = kpi(d.kpis, "value_lost");
  const first = d.rows[0];
  return lines(
    "Performing names the bank could shrink or not renew, and what that frees",
    `${cand != null ? `${n(cand)} names qualify; ` : ""}the top ${n(d.rows.length >= 6 ? 25 : d.rows.length)} free ${sar(cap)} of capital and release ${sar(ecl)} of provisions`,
    lost != null ? `The cost is about ${sar(lost)} a year of relationship income` : null,
    first ? `Start with ${first.borrower_name}; the RM confirms before any exit is agreed` : "The RM confirms before any exit is agreed",
  );
}

// ------------------------------------------------------------------ RWA finder

export interface RwaLike { kpis?: Kpi[]; rwa_total_sar_mn?: number }
export function writeRwa(d: RwaLike): string[] {
  const save = kpi(d.kpis, "rwa_saving");
  const capital = kpi(d.kpis, "capital_saving");
  const now = kpi(d.kpis, "recognisable");
  const after = kpi(d.kpis, "after_action");
  const risk = kpi(d.kpis, "at_risk");
  return lines(
    "Capital the book may not need: risk weights that could be lower",
    `It finds ${sar(save)} of RWA to save, about ${sar(capital)} of capital; ${sar(now)} can be claimed now`,
    after != null ? `${sar(after)} needs an action first, such as perfecting guarantees` : null,
    risk != null ? `Watch the other way: ${sar(risk)} of relief rests on collateral not yet registered` : null,
  );
}

// ------------------------------------------------------------------ ECL bridge forecast

export interface EclBridgeLike {
  kpis?: Kpi[]; next_run?: string;
  macro?: { scenarios?: { severity: string; closing_sar_mn: number; delta_sar_mn: number }[]; window?: string; fingerprint?: string } | null;
}
export function writeEclBridge(d: EclBridgeLike): string[] {
  const open = kpi(d.kpis, "opening");
  const fc = kpi(d.kpis, "forecast");
  const ov = kpi(d.kpis, "overlay");
  const mod = (d.macro?.scenarios ?? []).find((s) => s.severity === "moderate");
  return lines(
    "A forecast of next quarter's provisions before the run, and what drives the change",
    `Base path: ${sar(fc)} for ${d.next_run ?? "next quarter"}, from ${sar(open)} now, mostly from loans moving stage`,
    mod ? `In the moderate stress scenario it reaches ${sar(mod.closing_sar_mn)}, ${sar(mod.delta_sar_mn)} more` : "Stress scenarios are not available on this data",
    ov != null ? `A ${sar(ov)} overlay is drafted for review, not booked` : null,
  );
}

// ------------------------------------------------------------------ workout optimiser

export interface WorkoutLike {
  kpis?: Kpi[]; profile?: { borrower_name?: string; ead_sar_mn?: number; stage?: number; third_restructuring_next?: boolean } | null;
}
export function writeWorkout(d: WorkoutLike): string[] {
  const best = kpiText(d.kpis, "best");
  const npv = kpi(d.kpis, "npv");
  const up = kpi(d.kpis, "uplift");
  const p = d.profile ?? {};
  return lines(
    "The best way to recover a problem loan, from hold to sale or legal action",
    `For ${p.borrower_name ?? "this borrower"} (owes ${sar(p.ead_sar_mn)}), the best route is ${best ?? "not found"}, recovering ${sar(npv)} today`,
    up != null ? `That is ${sar(up)} more than holding, after the cost of capital` : null,
    p.third_restructuring_next ? "A reschedule would be its third in 24 months" : "Agree the route with workout and legal",
  );
}

// ------------------------------------------------------------------ renewal autopilot

export interface RenewalsLike {
  window_days: number; counts: { clean: number; exception: number }; ead_sar_mn?: { clean: number; exception: number };
  scope?: "material" | "all"; materiality_floor_sar_mn?: number; names?: number; whole_book_total?: number;
}
export function writeRenewals(d: RenewalsLike): string[] {
  const total = d.counts.clean + d.counts.exception;
  const floor = d.materiality_floor_sar_mn ?? 50;
  const material = d.scope !== "all";
  const rest = (d.whole_book_total ?? total) - total;
  return lines(
    `Renewals due in the next ${n(d.window_days)} days, prepared and sorted into clean and exceptions`,
    material
      ? `${n(total)} material renewals (names owing at least SAR ${n(floor)}m): ${n(d.counts.clean)} clean on a one-page note, ${n(d.counts.exception)} need a full paper`
      : `${n(total)} renewals in the whole book: ${n(d.counts.clean)} clean, ${n(d.counts.exception)} exceptions`,
    d.ead_sar_mn ? `The exceptions carry ${sar(d.ead_sar_mn.exception)}: look at those first` : null,
    material && rest > 0 ? `${n(rest)} smaller renewals stay in the full list` : null,
  );
}

// ------------------------------------------------------------------ who to call today

export interface CallsLike {
  total: number; today: number; this_week: number; rows: { borrower_name: string; signals: { label: string }[] }[];
  scope?: "material" | "all"; materiality_floor_sar_mn?: number; below_floor?: number; material_ead_sar_mn?: number;
}
export function writeCalls(d: CallsLike): string[] {
  const floor = d.materiality_floor_sar_mn ?? 50;
  const material = d.scope !== "all";
  const first = d.rows[0];
  return lines(
    "Clients to call this week because a warning sign fired, largest exposure first",
    material
      ? `${n(d.total)} material names (owing at least SAR ${n(floor)}m): ${n(d.today)} today, ${n(d.this_week)} this week`
      : `${n(d.total)} names in the whole book: ${n(d.today)} today, ${n(d.this_week)} this week`,
    first ? `Start with ${first.borrower_name}: ${(first.signals[0]?.label ?? "a signal fired").toLowerCase()}` : null,
    material && d.below_floor ? `${n(d.below_floor)} smaller names with a signal stay with their relationship managers` : null,
  );
}
