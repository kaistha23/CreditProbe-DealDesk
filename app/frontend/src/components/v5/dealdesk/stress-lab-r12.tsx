"use client";

/**
 * PLAN_R12 Session D: the Stress Lab as a ladder (I19, I20, I22, O3–O6). Exported for Session U to mount on the Stress
 * step (in place of the R11 `StressLab`, which stays exported unchanged):
 *
 *   StressLabR12        commentary and verdict first, then the ladder by family, reverse stress and the chain drawer
 *   StressCommentary    the 100–200-word reading above the grid (verdict, what breaks first, driver, what to do)
 *   StressVerdictCard   verdict, monitoring tier, review frequency and named triggers (Recommendation / committee paper)
 *   ChainDrawer         one scenario's transmission chain with each step's number and source
 *
 * Every figure is the engine's (POST /proposals/{id}/stress2); the (i) popovers carry the explanations.
 */

import { scenarioMemoHref } from "@/lib/v5/whatif";
import * as React from "react";
import { RegimeStrip } from "@/components/v5/scenarios/regime-strip";   // R14 m (K12)
import { Loader2, MessageSquareText, Plus, X } from "lucide-react";

import { KpiRow } from "@/components/v5/core/kpi-row";
import { cn } from "@/lib/utils";
import type { Terms } from "@/lib/v5/dealdesk";
import {
  COL_LABEL, SEV_LABEL, TIER_TONE, TONE_WORD, VERDICT_TONE, cellTone, cellValue, dataDomainsHref, ladderGroups, reverseLines, runStress2Cached,
  stress2Api, visibleCols, type ChainStep, type LadderRow, type Stress2Result, type StressBody2,
} from "@/lib/v5/dealdesk-stress2";

import { Explainer } from "./explain";
import { ChartTitle, Chip, Empty, SecondaryButton, Section, tableCls, thCls } from "./kit";
import { ScenarioEditor } from "./stress-lab-editor";
import { InfoPopover } from "@/components/ui/info-popover"; // R13 X: notes behind the (i)

// ---------------------------------------------------------------- data

export function useStress2(proposalId: string, body: StressBody2) {
  const [st, setSt] = React.useState<{ key: string; res: Stress2Result | null; error: string }>({ key: "", res: null, error: "" });
  const [nonce, setNonce] = React.useState(0);
  const bodyKey = JSON.stringify(body);
  const key = `${proposalId}#${bodyKey}#${nonce}`;
  React.useEffect(() => {
    let live = true;
    runStress2Cached(proposalId, JSON.parse(bodyKey) as StressBody2, nonce > 0)
      .then((r) => { if (live) setSt({ key, res: r, error: "" }); })
      .catch((e: Error) => { if (live) setSt((o) => ({ key, res: o.res, error: e.message })); });
    return () => { live = false; };
  }, [proposalId, bodyKey, nonce, key]);
  return { res: st.res, error: st.key === key ? st.error : "", busy: st.key !== key, reload: () => setNonce((n) => n + 1) };
}

const TONE_CELL = {
  pass: "bg-positive-muted text-positive",
  amber: "bg-warning-muted text-warning",
  breach: "bg-negative-muted text-negative font-semibold",
  na: "text-text-secondary",
} as const;
const SEV_TONE = { mild: "neutral", moderate: "warning", severe: "negative", none: "neutral", custom: "accent" } as const;

// ---------------------------------------------------------------- commentary and verdict

export function StressCommentary({ r }: { r: Stress2Result }) {
  return (
    <div className="rounded-lg border border-border bg-surface-muted/40 p-3" data-testid="stress2-commentary">
      <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
        <Chip tone={VERDICT_TONE[r.verdict.verdict]} testId="stress2-verdict">{r.verdict.verdict}</Chip>
        <Chip tone={TIER_TONE[r.tier.tier]} testId="stress2-tier">Monitoring tier {r.tier.tier}</Chip>
        <span className="text-[11px] text-text-muted">{r.commentary.words} words · {r.commentary.polished ? "polished" : "written from the run"}</span>
      </div>
      <p className="break-words text-[13px] leading-5 text-text-primary" data-testid="stress2-commentary-text">{r.commentary.text}</p>
    </div>
  );
}

export function StressVerdictCard({ r, compact = false }: { r: Stress2Result; compact?: boolean }) {
  const t = r.tier;
  return (
    <div className="space-y-2" data-testid="stress2-verdict-card">
      <div className="flex flex-wrap items-center gap-1.5">
        <Chip tone={VERDICT_TONE[r.verdict.verdict]}>{r.verdict.verdict}</Chip>
        <Chip tone={TIER_TONE[t.tier]}>Tier {t.tier}</Chip>
        <Chip>Review every {t.review_frequency_months} months</Chip>
        {t.provisional ? <Chip tone="warning">provisional until restructured</Chip> : null}
      </div>
      <p className="text-[12px] leading-5 text-text-secondary">{r.verdict.action}</p>
      {!compact && t.triggers.length ? (
        <ul className="space-y-1 text-[12px]" data-testid="stress2-triggers">
          {t.triggers.map((x) => (
            <li key={x.trigger_id} className="flex items-start gap-2" title={`${x.basis} · ${x.source}`}>
              <Chip tone={x.action === "alert" ? "negative" : "warning"}>{x.action === "alert" ? "EWS alert" : "watch"}</Chip>
              <span className="min-w-0 flex-1 text-text-primary">{x.label}</span>
            </li>))}
        </ul>) : null}
      {!compact && t.ews_thresholds.override ? (
        <div className="flex items-center gap-1 text-[11px] text-text-muted">Tighter Early Warning bands for this name<InfoPopover title="Early Warning bands">Moderate {t.ews_thresholds.band_floors.moderate}, high {t.ews_thresholds.band_floors.high}, critical {t.ews_thresholds.band_floors.critical} (book {t.ews_thresholds.book_floors.moderate}/{t.ews_thresholds.book_floors.high}/{t.ews_thresholds.book_floors.critical}).</InfoPopover></div>
      ) : null}
    </div>
  );
}

function VerdictInfo({ r }: { r: Stress2Result }) {
  return <Explainer testId="stress2-info-verdict"
    shows={<p>The verdict follows from the mildest severity that still breaks a test, and sets the monitoring tier.</p>}
    formulas={[
      <>Breaks first at mild (or fails before any stress): Restructure, tier High until fixed.</>,
      <>Breaks first at moderate: Approve with enhanced monitoring, tier High, quarterly review, the stressed driver as a named Early Warning trigger.</>,
      <>Breaks only at severe: Approve, standard monitoring, tier Medium, semi-annual review. Nothing breaks: Approve, tier Standard, annual review.</>,
      <>Only new breaks count. For the rating family, Stage 2 at the policy&apos;s SICR notch count is the scenario itself, not a break.</>,
    ]}
    read={<p>{r.verdict.why}.</p>}
    act={<p>{r.verdict.action}</p>} />;
}

// ---------------------------------------------------------------- the ladder

function LadderInfo({ r }: { r: Stress2Result }) {
  return <Explainer testId="stress2-info-ladder"
    shows={<p>Every family runs mild → moderate → severe on the {r.structure.label.toLowerCase()} structure; rows that cannot move this deal say why.</p>}
    formulas={[
      <>Shock → revenue by the sector sensitivity (dd_stress_sensitivity v{r.sensitivity_version}) or the deal&apos;s own fact; EBITDA with operating leverage; DSCR and leverage after the deal.</>,
      <>Rating: scenario notches plus the notches the stressed ratios imply; PD from the model at that grade; Stage 2 at three notches or DSCR below 1.0.</>,
      <>RAROC is checked at the stressed rating: PD, capital (the risk weight moves with the rating), ECL at the stressed stage and any margin ratchet.</>,
      <>LTV: the funded exposure over all pledged collateral after the shock.</>,
      ...(r.scenario_set?.includes("R13-S1") ? [
        <>Severities calibrated on history (set R13-S1): mild P75, moderate P92, severe the worse of P96 and the worst observed episode; drivers the bank data cannot size keep a labelled expert value. In a high-oil regime the oil rows are a reversal from today&apos;s level and the combined rows a trade disruption (R14). <a className="text-accent underline" href={scenarioMemoHref()} data-testid="stress2-memo">Methodology memo</a></>,
      ] : []),
    ]}
    read={<p>Read across a row for what one scenario breaks; down a family for the severity at which it starts to break. Click a row for its chain.</p>}
    act={<p>The first row to break decides the verdict and names the driver to watch.</p>} />;
}

function Ladder({ r, onOpen }: { r: Stress2Result; onOpen: (s: LadderRow) => void }) {
  const cols = visibleCols(r);
  const groups = ladderGroups(r);
  const row = (s: LadderRow, base = false) => (
    <tr key={s.id} onClick={() => onOpen(s)} data-testid={`stress2-row-${s.id}`} data-applicable={s.applicable ? "yes" : "no"}
        className="cursor-pointer hover:bg-surface-hover">
      <td className="border-b border-border/60 px-2 py-1.5">
        <div className="flex min-w-0 items-center gap-1.5">
          {!base ? <Chip tone={SEV_TONE[s.severity] ?? "neutral"}>{SEV_LABEL[s.severity] ?? s.severity}</Chip> : null}
          <span className={cn("truncate text-text-primary", base && "font-semibold")} title={s.label}>{s.label}</span>
        </div>
      </td>
      {s.applicable || base ? cols.map((c) => {
        const tone = cellTone(c, s);
        return (
          <td key={c} className="border-b border-border/60 p-0.5" title={`${COL_LABEL[c]}: ${TONE_WORD[tone]}`}>
            <span className={cn("block truncate rounded px-1.5 py-1 text-center text-[11px] tabular-nums", TONE_CELL[tone])}>{cellValue(c, s)}</span>
          </td>);
      }) : (
        <td colSpan={cols.length} className="border-b border-border/60 px-2 py-1.5 text-[11px] italic text-text-muted" data-testid={`stress2-na-${s.id}`}>
          <span className="line-clamp-1" title={s.na_reason ?? ""}>{s.na_reason}</span>
        </td>)}
    </tr>);
  return (
    <div className="max-h-[560px] overflow-auto" data-testid="stress2-ladder">
      <table className={cn(tableCls, "table-fixed")}>
        <colgroup><col className="w-[250px]" />{cols.map((c) => <col key={c} />)}</colgroup>
        <thead className="sticky top-0 z-10 bg-surface">
          <tr><th className={thCls}>Scenario</th>{cols.map((c) => <th key={c} className={cn(thCls, "text-center")}>{COL_LABEL[c]}</th>)}</tr>
        </thead>
        <tbody>
          {row(r.base, true)}
          {groups.map((g) => (
            <React.Fragment key={g.id}>
              <tr data-testid={`stress2-family-${g.id}`}>
                <td colSpan={cols.length + 1} className="px-2 pb-1 pt-2.5 text-[11px] font-semibold uppercase tracking-[0.06em] text-text-muted">
                  {g.label}
                  <span className="ml-2 font-normal normal-case tracking-normal">
                    {g.breaking ? `${g.breaking} break` : "none break"}{g.notApplicable ? ` · ${g.notApplicable} not applicable` : ""}
                  </span>
                </td>
              </tr>
              {g.rows.map((s) => row(s))}
            </React.Fragment>))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------- reverse stress

function ReverseInfo() {
  return <Explainer testId="stress2-info-reverse"
    shows={<p>How far each driver can move before DSCR falls below 1.0, a covenant breaks, the deal moves to Stage 2 or the checked RAROC falls below the hurdle; and how many notches the deal survives.</p>}
    formulas={[<>Each distance is the smallest move that fails the test, found by bisection on the engine&apos;s own formulas; RAROC is the checked stressed RAROC.</>,
               <>A driver not reached inside its search range says so.</>]}
    read={<p>The shortest distance is what breaks first.</p>}
    act={<p>Protect the shortest distance: covenants and a cash sweep for revenue and margin, security for collateral, a hedge for rates, a ratchet for rating.</p>} />;
}

function ReverseStress({ r }: { r: Stress2Result }) {
  const lines = reverseLines(r);
  if (!lines.length) return <Empty>No reverse stress for this structure.</Empty>;
  const dot = { breach: "bg-negative", amber: "bg-warning", pass: "bg-positive" };
  return (
    <div data-testid="stress2-reverse">
      <p className="mb-2 text-[12px] font-medium text-text-primary" data-testid="stress2-reverse-headline">{r.reverse?.headline}</p>
      <ul className="space-y-1.5 text-[12px]">
        {lines.map((l) => (
          <li key={l.label} className="flex items-start gap-2">
            <span className={cn("mt-1.5 size-2 shrink-0 rounded-full", dot[l.tone])} aria-hidden />
            <span className="w-[120px] shrink-0 text-text-secondary">{l.label}</span>
            <span className="min-w-0 flex-1 break-words text-text-primary">{l.text}</span>
          </li>))}
      </ul>
    </div>
  );
}

// ---------------------------------------------------------------- the chain drawer

const STAGE_LABEL: Record<string, string> = {
  shock: "Shock", revenue: "Revenue", ebitda: "EBITDA", ratios: "Ratios", rating: "Rating", pd: "PD", stage: "Stage", ecl: "ECL",
  raroc: "RAROC", covenants: "Covenants",
};

export function ChainDrawer({ proposalId, row, terms, onClose }: {
  proposalId: string; row: LadderRow; terms?: Terms | null; onClose: () => void;
}) {
  const key = `${proposalId}|${row.id}|${JSON.stringify(terms ?? null)}`;
  const [st, setSt] = React.useState<{ key: string; data: { answer: string; chain: ChainStep[] } | null; error: string }>({ key: "", data: null, error: "" });
  const data = st.key === key ? st.data : null;
  const error = st.key === key ? st.error : "";
  React.useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  React.useEffect(() => {
    let live = true;
    stress2Api.chain(proposalId, row.id, terms ?? null)
      .then((d) => { if (live) setSt({ key, data: d, error: "" }); })
      .catch((e: Error) => { if (live) setSt({ key, data: null, error: e.message }); });
    return () => { live = false; };
  }, [proposalId, row.id, terms, key]);
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/30" role="presentation" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <aside role="dialog" aria-modal="true" aria-label={`How ${row.label} was built`} data-testid="stress2-drawer"
             className="flex h-full w-[560px] max-w-[96vw] flex-col overflow-y-auto border-l border-border bg-surface p-4 shadow-2xl">
        <div className="mb-2 flex items-start gap-2">
          <div className="min-w-0">
            <h3 className="truncate text-[14px] font-semibold text-text-primary" title={row.label}>{row.label}</h3>
            <div className="mt-1 flex flex-wrap gap-1.5">
              <Chip>{row.family}</Chip>
              <Chip tone={SEV_TONE[row.severity] ?? "neutral"}>{SEV_LABEL[row.severity] ?? row.severity}</Chip>
              {row.applicable ? <Chip tone={row.breaks.length ? "negative" : "positive"}>{row.breaks.length ? `Breaks ${row.breaks.map((c) => COL_LABEL[c as keyof typeof COL_LABEL] ?? c).join(", ")}` : "Holds"}</Chip>
                : <Chip>not applicable</Chip>}
            </div>
          </div>
          <button type="button" onClick={onClose} aria-label="Close" className="ml-auto rounded p-1 text-text-muted hover:bg-surface-hover" data-testid="stress2-drawer-close"><X size={16} /></button>
        </div>
        {row.basis ? <p className="text-[12px] leading-5 text-text-secondary">{row.basis}</p> : null}
        {!row.applicable ? <p className="mt-2 text-[12px] text-text-primary" data-testid="stress2-drawer-na">{row.na_reason}</p> : null}
        {error ? <p className="mt-2 text-[12px] text-negative">{error}</p> : null}
        {row.applicable && !data && !error ? <p className="mt-3 inline-flex items-center gap-2 text-[12px] text-text-muted"><Loader2 size={13} className="animate-spin" /> Building the chain</p> : null}
        {data ? (
          <>
            <h4 className="mt-3 text-[12px] font-medium text-text-secondary">How this scenario was built</h4>
            <p className="mt-1 break-words text-[12px] leading-5 text-text-primary" data-testid="stress2-drawer-answer">{data.answer}</p>
            {data.chain.length ? (
              <table className={cn(tableCls, "mt-3 table-fixed")} data-testid="stress2-chain">
                <colgroup><col className="w-[70px]" /><col className="w-[150px]" /><col /></colgroup>
                <thead><tr><th className={thCls}>Step</th><th className={thCls}>Figure</th><th className={thCls}>Number and source</th></tr></thead>
                <tbody>
                  {data.chain.map((c, i) => (
                    <tr key={`${c.stage}-${i}`} data-stage={c.stage}>
                      <td className="border-b border-border/60 px-2 py-1.5 align-top text-[11px] text-text-muted">{STAGE_LABEL[c.stage] ?? c.stage}</td>
                      <td className="border-b border-border/60 px-2 py-1.5 align-top text-text-secondary">
                        <span className="line-clamp-2">{c.label}</span>
                        {c.deal_fact ? <Chip tone="accent">deal file</Chip> : null}
                      </td>
                      <td className="border-b border-border/60 px-2 py-1.5 align-top">
                        <p className="break-words text-text-primary">{c.display}</p>
                        {c.source ? <p className="mt-0.5 break-words text-[11px] text-text-muted">{c.source}</p> : null}
                        {dataDomainsHref(c) ? <a href={dataDomainsHref(c) ?? undefined} target="_blank" rel="noreferrer" className="text-[11px] text-accent hover:underline"
                                                 title={`${c.relation}${c.row ? ` · ${c.row}` : ""}${c.period ? ` · ${c.period}` : ""}`}>Open in Data Domains: {c.relation}</a> : null}
                      </td>
                    </tr>))}
                </tbody>
              </table>) : null}
          </>) : null}
      </aside>
    </div>
  );
}

// ---------------------------------------------------------------- the step

export function StressLabR12({ proposalId, terms, label, onBuildScenario, onAsk, refresh = 0 }: {
  proposalId: string; terms?: Terms | null; label?: string;
  /** Bump to run the ladder again (after a scenario is saved). */
  refresh?: number;
  /** Opens the scenario editor (ScenarioEditor) for this deal. */
  onBuildScenario?: () => void;
  /** Sends a question to the Deal Desk thread / Noor (e.g. "How was the combined severe scenario built?"). */
  onAsk?: (question: string) => void;
}) {
  const body = React.useMemo<StressBody2>(() => ({ terms: terms ?? null, structure_label: label, ...(refresh ? { refresh } : {}) }), [terms, label, refresh]);
  const { res: r, error, busy, reload } = useStress2(proposalId, body);
  const [open, setOpen] = React.useState<LadderRow | null>(null);
  if (!r) {
    return (
      <Section title="Stress Lab" testId="stress2-lab">
        {error ? (
          <div className="flex items-center gap-3" data-testid="stress2-error">
            <p className="text-[12px] text-negative">{error}</p><SecondaryButton onClick={reload}>Try again</SecondaryButton>
          </div>) : <Empty><span className="inline-flex items-center gap-2"><Loader2 size={14} className="animate-spin" /> Running the ladder through the engine</span></Empty>}
      </Section>);
  }
  const first = r.verdict.first_break;
  const tiles = [
    { label: "Verdict", value: r.verdict.verdict.replace(" with enhanced monitoring", ", enhanced").replace(", standard monitoring", ", standard"),
      sub: first ? (first.id === "base" ? "fails before any stress" : `${first.label} breaks first`) : "nothing breaks", tone: VERDICT_TONE[r.verdict.verdict] === "neutral" ? undefined : VERDICT_TONE[r.verdict.verdict],
      info: "The verdict → action rule: the mildest severity that still breaks a test." },
    { label: "Monitoring tier", value: r.tier.tier, sub: `review every ${r.tier.review_frequency_months} months · ${r.tier.triggers.length} trigger${r.tier.triggers.length === 1 ? "" : "s"}`,
      tone: TIER_TONE[r.tier.tier], info: "Set at approval as a condition; travels to the Book and Early Warning." },
    { label: "Scenarios breaking", value: `${r.counts.breaking} of ${r.counts.applicable}`, sub: `${r.counts.not_applicable} not applicable to this deal`,
      tone: r.counts.breaking ? ("warning" as const) : ("positive" as const), info: "Applicable scenarios with a new breach of DSCR, a covenant, Stage 1, the checked RAROC hurdle or a limit." },
    { label: "Rating headroom", value: r.reverse ? (r.reverse.notches.breaks_at.raroc === 0 ? "0 notches" : `${r.reverse.notches.survives_up_to} notch${r.reverse.notches.survives_up_to === 1 ? "" : "es"}`) : "–",
      sub: "before RAROC falls below the hurdle", info: "Reverse stress on the rating family, with the checked stressed RAROC." },
  ];
  return (
    <Section title={`Stress Lab: ${r.structure.label.toLowerCase()} structure`} testId="stress2-lab" info={<VerdictInfo r={r} />}
             action={(
               <div className="flex items-center gap-2">
                 {busy ? <span className="inline-flex items-center gap-1.5 text-[12px] text-text-muted"><Loader2 size={12} className="animate-spin" /> Updating</span> : null}
                 {onAsk ? <SecondaryButton onClick={() => onAsk(`How was the ${(first?.label ?? "combined severe").toLowerCase()} scenario built?`)} data-testid="stress2-ask"><MessageSquareText size={12} /> Ask how it was built</SecondaryButton> : null}
                 {onBuildScenario ? <SecondaryButton onClick={onBuildScenario} data-testid="stress2-build"><Plus size={12} /> Build a scenario</SecondaryButton> : null}
               </div>)}>
      {r.regime ? <div className="mb-2"><RegimeStrip block={r.regime} compact testId="stress2-regime" /></div> : null}
      <StressCommentary r={r} />
      <KpiRow className="mt-3" testId="stress2-tiles" tiles={tiles.map((t, i) => ({ ...t, testId: `stress2-tile-${i + 1}` }))} />
      <div className="mt-4">
        <ChartTitle title="Scenario ladder" info={<LadderInfo r={r} />} />
        <Ladder r={r} onOpen={setOpen} />
      </div>
      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <div className="min-w-0">
          <ChartTitle title="Distance to failure" info={<ReverseInfo />} />
          <ReverseStress r={r} />
        </div>
        <div className="min-w-0">
          <ChartTitle title="Verdict and monitoring" info={<VerdictInfo r={r} />} />
          <StressVerdictCard r={r} />
        </div>
      </div>
      {open ? <ChainDrawer proposalId={proposalId} row={open} terms={terms} onClose={() => setOpen(null)} /> : null}
    </Section>
  );
}

/**
 * The Stress step as Session U mounts it: the same props as the R11 `StressLab` (swap the import), plus the scenario
 * editor under the ladder. `recommendedTerms` is accepted for the R11 signature; the ladder runs on `terms`.
 */
export function StressLabStep({ proposalId, terms, label, onAsk }: {
  proposalId: string; terms?: Terms | null; recommendedTerms?: Terms | null; label?: string; onAsk?: (question: string) => void;
}) {
  const [editing, setEditing] = React.useState(false);
  const [refresh, setRefresh] = React.useState(0);
  return (
    <div className="space-y-4" data-testid="stress2-step">
      <StressLabR12 proposalId={proposalId} terms={terms} label={label} onAsk={onAsk} refresh={refresh} onBuildScenario={() => setEditing((v) => !v)} />
      {editing ? <ScenarioEditor proposalId={proposalId} onClose={() => setEditing(false)} onSaved={(s) => { if (s.status === "approved") setRefresh((n) => n + 1); }} /> : null}
    </div>
  );
}
