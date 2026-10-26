/**
 * R14 G (K34): "In plain words" writers for the Network tools — contagion map, employer exposure and event translator.
 * Deterministic (N4); every number is the engine's own (totals, impact, appetite).
 */
import type { ContagionResult, EmployerRanking, EmployerResult, EventResult } from "../../../components/v5/intel/network/format.ts";
import { dsar, lines, n, pctv, plural, sar } from "./fmt.ts";

export function writeContagion(d: ContagionResult): string[] {
  const t = d.totals;
  const top = [...d.names].sort((a, b) => (b.at_risk ?? 0) - (a.at_risk ?? 0))[0];
  const what = `Who else the bank is exposed to if ${d.focal.name} fails, and through which links`;
  const says = t.names
    ? `${plural(t.names, "other borrower")} carry ${sar(t.exposure)} linked to it; ${sar(t.at_risk)} is at risk`
    : "No other borrower in the book is linked to it";
  const ecl = `Provisions change ${dsar(t.d_ecl_focal)} on it and ${dsar(t.d_ecl_second)} on the others`;
  const act = top && t.names ? `Review ${top.name} first: it ${top.why}` : null;
  return lines(what, says, ecl, act);
}

export function writeEmployer(d: EmployerResult): string[] {
  const t = d.totals, a = d.appetite;
  return lines(
    `What the bank lends to the contractors ${d.employer.name} pays, beside its own loans`,
    `${plural(t.contractors, "contractor")} carry ${sar(t.exposure)}, ${sar(t.attributable)} of it hanging on its payments; its own exposure is ${sar(t.own_exposure)}`,
    `Together that is ${pctv(a.utilisation_pct, 0)} of the ${sar(a.limit)} single-name limit (${a.status})`,
    t.in_early_warning ? `${plural(t.in_early_warning, "contractor")} already in Early Warning: if it pays late, start with them`
      : "None of its contractors is in Early Warning today",
  );
}

export function writeEvent(d: EventResult): string[] {
  const i = d.impact;
  const top = [...d.by_sector].sort((a, b) => b.d_ecl - a.d_ecl)[0];
  return lines(
    `This translates "${d.event.text || d.event.label}" into what it does to the bank's corporate loans`,
    `Provisions change ${dsar(i.ecl_change)} (${pctv(i.ecl_change_pct, 1)}) to ${sar(i.ecl_after)}; ${n(i.to_stage2_n)} facilities move to Stage 2`,
    top ? `${top.sector} is hit hardest (${dsar(top.d_ecl)}): call the names on the list below first` : null,
    /§S|calibrat/i.test(d.calibration?.label ?? "") ? "The shock sizes come from the bank's calibrated stress scenarios"
      : "The shock sizes are the What-If engine's current settings",
  );
}

export function writeEmployerRanking(d: EmployerRanking): string[] {
  const top = d.rows[0];
  const near = d.rows.filter((r) => r.status !== "within appetite").length;
  return lines(
    "Project employers ranked by what the bank lends to the contractors they pay",
    top ? `${top.name} leads: ${sar(top.attributable)} of contractor loans hang on its payments, ${sar(top.combined)} with its own` : "No employer pays contractors that borrow from the bank",
    near ? `${plural(near, "employer")} near or over the ${sar(d.appetite.limit)} single-name limit: review them first`
      : `All ${n(d.rows.length)} listed are within the ${sar(d.appetite.limit)} single-name limit; open one to see its contractors`,
  );
}

/** R14 G (K34): the event translator before a run — what it is, how to start, what you get. */
export function writeEventEmpty(examples: number): string[] {
  return lines(
    "Type a shock from this morning's news and see which borrowers it hits",
    "You get the ECL and Stage 2 hit from the What-If engine and who to call today",
    `Start from one of the ${examples} example events below, then pick mild, moderate or severe`,
  );
}
