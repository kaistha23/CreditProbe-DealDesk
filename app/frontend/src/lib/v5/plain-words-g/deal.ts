/**
 * R14 G (K34): the "In plain words" writers for the deal page's More menu panels. Deterministic (N4): same data, same
 * words. Each block: (1) what the panel is; (2) what it says for this deal, with the one or two numbers that matter, all
 * read from the panel's own result (N5); (3) what to do or the caveat. Rules: lib/v5/../components/v5/ui/plain-words-model.
 *
 * Types are structural (only the fields each writer reads), so the panels' own models stay the source of truth.
 */
import { lines, n, pct, plural, sar } from "./fmt.ts";

type Fig = { value: number | null } | null | undefined;
/** Drop bracketed asides from quoted engine text (the block keeps brackets for its glossary only). */
const nob = (t: string): string => t.replace(/\s*\([^)]*\)/g, "").replace(/\s+/g, " ").trim();
const fv = (f: Fig): number | null => (f && typeof f.value === "number" && Number.isFinite(f.value) ? f.value : null);

// ------------------------------------------------------------------ Documents (review2 documents checklist)

export interface DocumentsLike {
  counts: Record<string, number>; missing_count: number; completeness: number; items?: unknown[];
}

export function writeDocuments(d: DocumentsLike): string[] {
  const total = Object.values(d.counts).reduce((a, b) => a + (b || 0), 0);
  const expired = d.counts.expired ?? 0;
  const what = "The documents the bank's rules require for this deal, and which ones are on file";
  const says = d.missing_count
    ? `${n(d.missing_count)} of ${n(total)} required documents are missing or expired${expired ? `, ${n(expired)} of them expired` : ""}; the file is ${pct(d.completeness)} complete`
    : `All ${n(total)} required documents are on file; the file is ${pct(d.completeness)} complete`;
  const todo = d.missing_count
    ? "Send the missing items to the RM as queries before the deal goes to committee"
    : "Nothing to chase: the review can rely on the file";
  return lines(what, says, todo);
}

// ------------------------------------------------------------------ Group & SWOT

export interface GroupLike {
  cap_test: null | { group_name?: string | null; after_ead?: number | null; binding_limit?: number | null; headroom_after?: number | null;
              status?: string | null; utilisation_pct?: number | null };
  governance: { counts: { governance?: number; conduct?: number; high?: number };
                overlay?: { base_rating?: string; overlaid_rating?: string; notches?: number } | null };
  facts?: { structure?: { members?: number; standalone?: boolean } | null } | null;
}

export function writeGroup(g: GroupLike): string[] {
  const c = g.cap_test ?? {};
  const flags = (g.governance.counts.governance ?? 0) + (g.governance.counts.conduct ?? 0);
  const ov = g.governance.overlay;
  const what = "Who the borrower belongs to, the group's total borrowing with us and any warning signs in ownership or conduct";
  const exp = c.after_ead != null && c.binding_limit != null
    ? `After this deal the group owes ${sar(c.after_ead)} against a limit of ${sar(c.binding_limit)}, ${c.utilisation_pct != null ? `${c.utilisation_pct.toFixed(0)}% used` : (c.status ?? "")}`
    : null;
  const fl = flags
    ? `${plural(flags, "red flag")} found${ov && ov.notches ? `: the rating drops ${plural(ov.notches, "notch", "notches")} to ${ov.overlaid_rating}` : ""}`
    : "No governance or conduct red flag found";
  const todo = flags ? "Each red flag is a review finding with a condition: clear them before approval" : "Nothing to clear on the group side";
  return lines(what, exp, fl, todo);
}

export interface SwotLike {
  counts: Record<string, number>; summary?: string;
}

export function writeSwot(s: SwotLike): string[] {
  const k = (q: string) => s.counts[q] ?? 0;
  const what = "The deal's strengths, weaknesses, opportunities and threats, each with its figure and source";
  const says = `${plural(k("strength"), "strength")} against ${plural(k("weakness"), "weakness", "weaknesses")}, with ${plural(k("opportunity"), "opportunity", "opportunities")} and ${plural(k("threat"), "threat")}`;
  const main = s.summary && /Main weakness: (.+?)\.?$/.exec(s.summary)?.[1];
  const todo = main ? `Start with the main weakness, ${nob(main)}, and check the structure mitigates it` : "Check every weakness has a mitigant in the structure";
  return lines(what, says, todo);
}

// ------------------------------------------------------------------ Write proposal / Committee paper

export interface PaperLike {
  customer: string; totals: { existing: number; outstanding: number; proposed: number }; request_kind?: string;
  sections: unknown[]; coverage: string[]; voice: string[]; gaps: unknown[];
}

function checks(p: PaperLike): string {
  if (p.coverage.length) return `${plural(p.coverage.length, "required section")} still missing`;
  const bits: string[] = [];
  if (p.voice.length) bits.push(`${plural(p.voice.length, "sentence")} off the house voice`);
  if (p.gaps.length) bits.push(`${plural(p.gaps.length, "section")} where the data is not yet available`);
  return bits.length ? bits.join(" and ") : "every required section is there, in the house voice";
}

export function writeWriteProposal(p: PaperLike): string[] {
  const what = "The full credit proposal in the bank's own form, drafted from the deal's data";
  const says = `It asks for total limits of ${sar(p.totals.proposed)}${p.totals.existing ? ` against ${sar(p.totals.existing)} today` : ""}, over ${plural(p.sections.length, "section")}`;
  const todo = `Checks: ${checks(p)}. Read it, then download Word or PDF`;
  return lines(what, says, todo);
}

export interface CommitteeLike { approval_authority: string; density: string[]; paper: PaperLike; summary: unknown[] }

export function writeCommitteePaper(c: CommitteeLike): string[] {
  const what = "A short decision summary for the committee, then the full paper in committee order";
  const says = `Limits of ${sar(c.paper.totals.proposed)} go to ${c.approval_authority}; the summary has ${plural(c.summary.length, "part")}`;
  const dens = c.density.length
    ? `${plural(c.density.length, "summary line")} without a figure or source: fix before sending`
    : "Every summary line carries a figure or a source; download Word or PDF for the pack";
  return lines(what, says, dens);
}

// ------------------------------------------------------------------ Try it on your documents

export interface TryDocsState {
  overview?: { ttl_hours?: number; steps?: unknown[]; accepted?: string[] } | null;
  session?: {
    total_seconds: number; complete: boolean;
    steps: { key: string; status: string; result?: unknown }[];
  } | null;
}

export function writeTryDocs(t: TryDocsState): string[] {
  const s = t.session;
  const what = "Try CreditProbe on your own credit proposal and policy: it reads them, reviews the deal and drafts the memo";
  if (!s) {
    const ttl = t.overview?.ttl_hours;
    const nSteps = t.overview?.steps?.length;
    return lines(what,
      nSteps ? `Each run takes ${plural(nSteps, "timed step")}, from reading the file to the drafted memo` : null,
      `Your files stay on this laptop and are wiped when you exit${ttl ? `, or after ${plural(ttl, "hour")}` : ""}`,
      "Drop a proposal, or use the sample one, to start");
  }
  const done = s.steps.filter((x) => x.status === "done").length;
  const rev = s.steps.find((x) => x.key === "review")?.result as { severity?: Record<string, number>; decision?: string | null } | undefined;
  const sev = rev?.severity;
  const findings = sev ? (sev.critical ?? 0) + (sev.major ?? 0) + (sev.minor ?? 0) : null;
  const says = s.complete
    ? `Done in ${s.total_seconds.toFixed(1)} seconds: ${findings != null ? `${plural(findings, "finding")}, ${n(sev?.critical ?? 0)} critical` : `${plural(done, "step")} done`}`
    : `${n(done)} of ${n(s.steps.length)} steps done in ${s.total_seconds.toFixed(1)} seconds`;
  const todo = rev?.decision ? `Review verdict: ${rev.decision}. Exit and wipe when you have finished` : "Run the next step, then exit and wipe";
  return lines(what, says, todo);
}

// ------------------------------------------------------------------ Financial quality

export interface FinQualityLike {
  subject: { name: string };
  grade: { grade: string; meaning: string; flagged: number; signals: number; assessable: number; limited: boolean;
           by_severity: Record<string, number> };
}

export function writeFinQuality(f: FinQualityLike): string[] {
  const g = f.grade;
  const what = "Checks whether the borrower's reported figures can be trusted: related parties, receivables, earnings, audit and account turnover";
  const says = g.limited && !g.flagged
    ? `Grade ${g.grade}: none of the ${n(g.assessable)} checks that could run flagged anything; ${g.meaning}`
    : `Grade ${g.grade}: ${n(g.flagged)} of ${n(g.signals)} checks flagged${g.flagged ? `, ${n(g.by_severity.critical ?? 0)} critical` : ""}; ${g.meaning}`;
  const todo = g.limited
    ? `Only ${n(g.assessable)} of ${n(g.signals)} checks could run on the data on file: ask for fuller statements before relying on the grade`
    : g.flagged ? "Ask the RM to explain each flagged item before committee" : "No action needed on the figures";
  return lines(what, says, todo);
}

// ------------------------------------------------------------------ Committee questions (challenger)

export interface ChallengerLike {
  obligor: string; questions: { question: string; avoided: boolean }[]; avoided: { question: string }[];
}

export function writeChallenger(c: ChallengerLike): string[] {
  const what = "The questions the credit committee is most likely to ask, each answered from the data";
  const k = c.questions.filter((q) => q.avoided).length;
  const says = k
    ? `${plural(c.questions.length, "question")} expected; the proposal does not answer ${n(k)} of them`
    : `${plural(c.questions.length, "question")} expected; the proposal answers all of them`;
  const todo = k ? "Prepare an answer for each one marked not answered, starting with the first" : "Keep the answers ready for the meeting";
  return lines(what, says, todo);
}

// ------------------------------------------------------------------ Make it approvable (reverse solver)

export interface ReverseLike {
  approvable_as_asked: boolean; failures: { label: string }[];
  ask: { lifetime_raroc: Fig; hurdle: Fig };
  counter_offer: { changes: { text: string }[]; lifetime_raroc: Fig; approval?: { level?: string } } | null;
}

export function writeReverse(r: ReverseLike): string[] {
  const what = "The smallest change that would make this deal approvable";
  const ra = fv(r.ask.lifetime_raroc), h = fv(r.ask.hurdle);
  const fails = r.approvable_as_asked
    ? "As asked the deal already clears every test"
    : `As asked it fails ${r.failures.length === 1 ? "one test" : `${n(r.failures.length)} tests`}: return ${pct(ra, 1)} against the ${pct(h, 1)} needed`;
  const co = r.counter_offer;
  const fix = co
    ? `Counter-offer: ${co.changes.slice(0, 2).map((c) => nob(c.text)).join("; ")}, lifting the return to ${pct(fv(co.lifetime_raroc), 1)}`
    : r.approvable_as_asked ? null : "No change in the deal's own terms clears it: price or amount must be renegotiated";
  const todo = co ? "Copy the counter-offer for the RM and agree it with the client" : null;
  return lines(what, fails, fix, todo);
}

// ------------------------------------------------------------------ Decision consistency

export interface ConsistencyLike {
  decision: { decision: string; by: string };
  similar: unknown[]; decided_differently: { status: string }[];
}

export function writeConsistency(c: ConsistencyLike): string[] {
  const what = "Similar past deals that were decided differently, and whether the differences explain it";
  const dd = c.decided_differently;
  const unexplained = dd.filter((p) => p.status !== "explained").length;
  const says = dd.length
    ? `${plural(c.similar.length, "similar deal")} found; ${n(dd.length)} decided differently, ${n(unexplained)} not fully explained`
    : `${plural(c.similar.length, "similar deal")} found, all decided the same way`;
  const todo = unexplained
    ? "Be ready to say why this deal is treated differently: committee will ask"
    : "The decision is in line with past practice";
  return lines(what, says, todo);
}
