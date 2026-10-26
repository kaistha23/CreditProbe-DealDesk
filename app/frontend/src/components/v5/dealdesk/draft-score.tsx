"use client";

/**
 * PLAN_R11 Session P (P3): the draft's house-style score against the band of the bank's own memos, and the
 * "differs from house style" lint. At most 4 tiles (G-TILES); explanations in (i).
 */

import * as React from "react";

import { KpiRow } from "@/components/v5/core/kpi-row";
import { type Draft, type Lint, fmt1, lintBySection, scoreTone } from "@/lib/v5/dealdesk-draft";

import { Chip, Section } from "./kit";

const RULE: Record<string, string> = {
  missing_section: "Missing section", section_order: "Section order", sentence_length: "Sentence length", hedging: "Hedging",
  voice: "Voice", number_format: "Number format", abbreviation: "Abbreviation", spelling: "Spelling", rm_avoids: "RM removed before",
  uncited_figure: "Uncited figure",
};

export function DraftScoreTiles({ draft }: { draft: Draft }) {
  const sc = draft.score;
  const accepted = draft.sections.filter((s) => s.status === "accepted").length;
  const n = draft.sections.length;
  return (
    <KpiRow testId="draft-score-tiles" tiles={[
      { label: "House-style score", value: fmt1(sc.total), tone: scoreTone(sc.total, sc.band),
        sub: sc.band.n ? `band ${fmt1(sc.band.low)}–${fmt1(sc.band.high)}` : "no band yet",
        info: <>30% structure + 35% phrase use + 35% stylometrics, against the house profile. The band is the bank&apos;s own memos scored
          leave-one-out ({sc.band.basis || `${sc.band.n} memos`}); a draft reads like the house at or above its low end.</> },
      { label: "Structure", value: fmt1(sc.structure), sub: "sections and order",
        info: "Share of the house sections present (60%) and agreement with the house order (40%), less any section the house does not write." },
      { label: "Phrase and tone", value: fmt1((sc.phrase + sc.stylometrics) / 2), sub: `phrases ${fmt1(sc.phrase)} · style ${fmt1(sc.stylometrics)}`,
        info: "Phrases: sentences that open like the house or use its standard phrases. Style: sentence length, hedging, voice, number format, abbreviations and spelling against the house." },
      { label: "Accepted", value: `${accepted} of ${n}`, sub: draft.lint.length ? `${draft.lint.length} lint point${draft.lint.length === 1 ? "" : "s"}` : "no lint points",
        tone: accepted === n ? "positive" : "neutral", info: "Sections the RM has accepted. Judgement sections stay suggestions until accepted." },
    ]} />
  );
}

function LintRow({ l, heading, onFocus }: { l: Lint; heading: string; onFocus?: () => void }) {
  return (
    <li data-testid="draft-lint-item">
     <button type="button" onClick={onFocus} className="w-full rounded-md border border-border px-2.5 py-2 text-left hover:border-accent">
      <div className="flex flex-wrap items-center gap-1.5">
        <Chip tone={l.severity === "major" ? "negative" : "warning"}>{RULE[l.rule] ?? l.rule}</Chip>
        <span className="truncate text-[11px] text-text-muted">{heading}</span>
      </div>
      <p className="mt-1 text-[12px] leading-snug text-text-secondary">{l.message}</p>
      {l.suggestion ? <p className="mt-0.5 text-[11px] text-text-muted">House: {l.suggestion}</p> : null}
     </button>
    </li>
  );
}

export function DraftLint({ draft, onFocus }: { draft: Draft; onFocus?: (key: string) => void }) {
  const by = lintBySection(draft.lint);
  const heading = (k: string) => draft.sections.find((s) => s.key === k)?.heading ?? k;
  return (
    <Section title="Differs from house style" testId="draft-lint"
             info="Each place the draft differs from the house profile: structure, sentence length, hedging, voice, number format, abbreviations, spelling and phrases an RM removed before.">
      {draft.lint.length === 0 ? (
        <p className="text-[12px] text-text-secondary" data-testid="draft-lint-empty">No differences from the house style.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {Object.entries(by).flatMap(([k, ls]) => ls.map((l) => <LintRow key={l.id} l={l} heading={heading(k)} onFocus={() => onFocus?.(k)} />))}
        </ul>
      )}
    </Section>
  );
}
