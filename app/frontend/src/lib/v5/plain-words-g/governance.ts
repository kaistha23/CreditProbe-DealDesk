/**
 * R14 G (K34): "In plain words" writers for the Governance tools — exception intelligence, RM track record and DoA
 * calibration. Deterministic (N4). The decision history behind them (gov_* relations) is a fictional demo seed, and each
 * block says so; the outcomes (defaults, stage) are read from the corporate book.
 */
import type { DoaCalibration, ExceptionIntel, RmTrack } from "../intel-governance.ts";
import { lines, n, pctv } from "./fmt.ts";

const SEED = "Decision history is a demo seed; outcomes come from the real book";

export function writeExceptions(d: ExceptionIntel): string[] {
  const e = d.peers.exception, p = d.peers.no_exception;
  const worst = d.types.filter((t) => t.verdict === "tighten" && t.oe_default != null)
    .sort((a, b) => (b.oe_default ?? 0) - (a.oe_default ?? 0))[0];
  return lines(
    "This checks how approved policy exceptions performed afterwards against similar loans without one",
    `Loans with an exception defaulted at ${pctv(e.default.pct)} within a year, against ${pctv(p.default.pct)} without (${n(e.n)} and ${n(p.n)} decisions)`,
    worst ? `Tighten "${worst.label}" first: ${pctv(worst.default?.pct ?? null)} defaulted against ${pctv(worst.expected_default_pct ?? null)} expected`
      : "No exception type performed clearly worse than its peers",
    SEED,
  );
}

export function writeRmTrack(d: RmTrack): string[] {
  const ranked = d.rows.filter((r) => !r.thin && r.score != null).sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
  const who = d.group === "rm" ? "RMs" : "branches";
  const top = ranked[0], low = ranked[ranked.length - 1];
  return lines(
    `This scores ${who} on proposal quality, conditions met and how their approvals performed, adjusted for the risk taken`,
    `${n(d.total)} ${who} ranked with at least ${n(d.min_n)} approvals`
      + (top ? `; strongest ${top.name} (score ${n(top.score)})` : ""),
    low && low !== top && (low.score ?? 100) < 50
      ? `Coach ${low.name} first: score ${n(low.score)}, defaults ${(low.oe ?? 0).toFixed(1)} times what the risk taken implied`
      : "No one ranked stands out as weak; use the table to compare",
    SEED,
  );
}

export function writeDoa(d: DoaCalibration): string[] {
  const files = d.levels.reduce((m, l) => Math.max(m, l.files), 0);
  const slow = d.levels.filter((l) => l.rank > 0).sort((a, b) => (b.share_of_turnaround_pct ?? 0) - (a.share_of_turnaround_pct ?? 0))[0];
  const saved = d.proposals.reduce((s, p) => s + (p.days_saved_per_year ?? 0), 0);
  return lines(
    "This shows where approval levels add days without changing the decision",
    slow ? `Across ${n(files)} files, ${slow.level} takes the largest share of the time: ${pctv(slow.share_of_turnaround_pct, 0)}` : null,
    d.proposals.length ? `The ${n(d.proposals.length)} proposed changes would save about ${n(saved)} file-days a year; check the past changes given up before agreeing`
      : "No level qualifies for a change: each one alters enough files to keep",
    SEED,
  );
}
