/**
 * One customer's early-warning issues, assembled once.
 *
 * Two screens used to draw the same tripped rules twice: the profile's own
 * `early_warning.tripped` table and the governed signal catalogue read for
 * the same owner. They are not two findings, they are one finding with two
 * halves of its evidence -- the profile carries the rule's population and
 * EAD, the catalogue carries the dated observation behind it. This module
 * joins them on the rule id, which both sides take from the same active
 * rule, and says plainly when it must NOT join: a catalogue read that
 * answered for another owner, release or period is not this customer's
 * evidence and is never merged into it.
 */

import type { EntitySignals, Profile, ReasonRow } from "@/ews-preview/lib/workspace/canonical";

/** The profile's half of one tripped rule. Served, not recomputed here. */
export interface RuleSummary {
  id: string;
  reason: string;
  weight: number;
  exposures: number;
  ead_sar_mn: number;
  limitation: string;
}

/**
 * Each rule's EAD is the EAD of the exposures that tripped THAT rule. One
 * exposure can trip several, so the column is per rule and never a total.
 */
export const EAD_NOT_ADDITIVE =
  "Exposures and EAD are counted per rule. One exposure can trip several rules, " +
  "so these rows overlap and must not be added into a customer total.";

/** Why the catalogue's half of the evidence is not on screen. */
export type SummaryOnlyReason = "loading" | "error" | "identity";

export type CustomerIssues =
  | {
      kind: "merged";
      signals: EntitySignals;
      /** Keyed by rule id, for the signals the catalogue returned. */
      summary: Record<string, RuleSummary>;
      /** Tripped rules the catalogue read carries no fired signal for. */
      unmatched: RuleSummary[];
    }
  | {
      kind: "summary-only";
      reason: SummaryOnlyReason;
      summaries: RuleSummary[];
      note: string;
    };

/**
 * The tripped rules of this profile, one row per rule id.
 *
 * A repeated id is the same rule, not a second finding, so the first row
 * stands and the order the server sorted them in is kept.
 */
export function ruleSummaries(profile: Profile): RuleSummary[] {
  const seen = new Set<string>();
  const out: RuleSummary[] = [];
  for (const r of profile.early_warning.tripped as ReasonRow[]) {
    if (!r.id || seen.has(r.id)) continue;
    seen.add(r.id);
    out.push({
      id: r.id,
      reason: r.reason,
      weight: r.weight,
      exposures: r.exposures,
      ead_sar_mn: r.ead_sar_mn,
      limitation: r.limitation ?? "",
    });
  }
  return out;
}

/**
 * Is this catalogue read about the row the reader has open?
 *
 * Owner, book, period and release all have to agree. A stale response from
 * a previous selection answers every one of those questions differently and
 * would caption another customer's observations with this customer's name.
 */
export function answersFor(profile: Profile, signals: EntitySignals): boolean {
  return (
    signals.entity_id === profile.owner_id &&
    signals.domain_id === profile.domain_id &&
    signals.period === profile.period &&
    signals.release_id === profile.release_id
  );
}

/** The profile half, keyed by rule id, for the rules the catalogue fired. */
export function summaryByRule(
  summaries: RuleSummary[],
  signals: EntitySignals,
): Record<string, RuleSummary> {
  const fired = new Set(signals.fired_signals.map((one) => one.id));
  const out: Record<string, RuleSummary> = {};
  for (const s of summaries) if (fired.has(s.id)) out[s.id] = s;
  return out;
}

/**
 * Assemble the one panel.
 *
 * The profile summary is never dropped: when the catalogue read fails, is
 * still running or answered for someone else, the rules the profile already
 * proved are shown on their own and the panel says which half is missing.
 */
export function customerIssues({
  profile,
  signals,
  error,
}: {
  profile: Profile;
  signals: EntitySignals | null;
  error?: string;
}): CustomerIssues {
  const summaries = ruleSummaries(profile);
  if (error) {
    return {
      kind: "summary-only",
      reason: "error",
      summaries,
      note: `The signal catalogue could not be read for ${profile.owner_id} (${error}). The rules below are the profile's own, without the dated observation behind each one.`,
    };
  }
  if (!signals) {
    return {
      kind: "summary-only",
      reason: "loading",
      summaries,
      note: `Reading the signal catalogue for ${profile.owner_id}. The rules below are the profile's own until it answers.`,
    };
  }
  if (!answersFor(profile, signals)) {
    return {
      kind: "summary-only",
      reason: "identity",
      summaries,
      note: `The signal catalogue answered for ${signals.entity_id} at ${signals.period} on ${signals.release_id}, not for ${profile.owner_id} at ${profile.period} on ${profile.release_id}, so its observations are not shown here.`,
    };
  }
  const summary = summaryByRule(summaries, signals);
  return {
    kind: "merged",
    signals,
    summary,
    unmatched: summaries.filter((s) => !(s.id in summary)),
  };
}
