"use client";

/**
 * PLAN_R11 Session S (S3): the Stress Lab. `StressLab` is the deal view's Stress step (placed by U after Structure);
 * `StressSummary` is one line and four tiles inside Optimise with a link to the step. Answer first, then evidence:
 *
 *   1. the answer line and ≤ 4 tiles (scenarios survived, severe case, revenue to DSCR 1.0, worst ECL)
 *   2. a custom shock typed in words ("revenue −20% and rates +150 bps")
 *   3. the scenario × metric heatmap (pass, close, breach); a row opens the scenario drawer
 *   4. distance to failure (reverse stress) and the asked against recommended resilience
 *
 * Every figure is the engine's (POST /proposals/{id}/stress); the R5 Analysis stress table stays where it is (N1).
 */

import * as React from "react";
import { ArrowRight, Loader2, Play, X } from "lucide-react";

import { KpiRow } from "@/components/v5/core/kpi-row";
import { Plot } from "@/components/v5/ews/plot";
import { cn } from "@/lib/utils";
import type { Terms } from "@/lib/v5/dealdesk";
import {
  BEYOND_RATIO, CELL_LABEL, GROUP_LABEL, TONE_WORD, answerLine, cellText, distanceBars, firstToBreak, fmtDriver,
  heatmapGroups, resilienceCounts, resilienceRows, runStressCached, summaryTiles, visibleCells,
  type CellTone, type ScenarioRow, type StressBody, type StressLabResult,
} from "@/lib/v5/dealdesk-stress";
import { pct, ratio, sar } from "@/lib/v5/format";

import { C } from "./charts";
import { Explainer } from "./explain";
import { ChartTitle, Chip, Empty, PrimaryButton, SecondaryButton, Section, tableCls, tdCls, thCls } from "./kit";

// ---------------------------------------------------------------- data

function useStress(proposalId: string, body: StressBody) {
  // the last result stays on screen while a new one (another structure, a custom shock) is computed
  const [st, setSt] = React.useState<{ key: string; res: StressLabResult | null; error: string }>({ key: "", res: null, error: "" });
  const [nonce, setNonce] = React.useState(0);
  const key = `${proposalId}#${JSON.stringify(body)}#${nonce}`;
  React.useEffect(() => {
    let live = true;
    runStressCached(proposalId, JSON.parse(key.split("#").slice(1, -1).join("#")) as StressBody)
      .then((r) => { if (live) setSt({ key, res: r, error: "" }); })
      .catch((e: Error) => { if (live) setSt((o) => ({ key, res: o.res, error: e.message })); });
    return () => { live = false; };
  }, [proposalId, key]);
  return { res: st.res, error: st.key === key ? st.error : "", busy: st.key !== key, retry: () => setNonce((n) => n + 1) };
}

const bodyFor = (terms?: Terms | null, rec?: Terms | null, label?: string, custom?: string): StressBody => ({
  terms: terms ?? null, recommended_terms: rec ?? null, structure_label: label, ...(custom ? { custom } : {}),
});

// ---------------------------------------------------------------- pieces

const TONE_CELL: Record<CellTone, string> = {
  pass: "bg-positive-muted text-positive",
  amber: "bg-warning-muted text-warning",
  breach: "bg-negative-muted text-negative font-semibold",
  na: "text-text-muted",
};
const x2 = (v: number | null | undefined) => (v === null || v === undefined || !Number.isFinite(v) ? "–" : `${ratio(v)}x`);
const pc = (v: number | null | undefined) => pct(v, { dp: 1 });

function Tiles({ r, testId }: { r: StressLabResult; testId: string }) {
  return <KpiRow testId={testId} tiles={summaryTiles(r).map((t, i) => ({ ...t, testId: `${testId}-${i + 1}` }))} />;
}

function Loading({ text }: { text: string }) {
  return <Empty><span className="inline-flex items-center gap-2"><Loader2 size={14} className="animate-spin" /> {text}</span></Empty>;
}

function LabInfo({ r }: { r: StressLabResult }) {
  return <Explainer testId="stress-info-lab"
    shows={<p>The {r.structure.label.toLowerCase()} structure run through the Deal Desk engine under {r.summary.applicable} scenarios: macro, sector, obligor, collateral, rating and combined, plus any shock you type.</p>}
    formulas={[
      <>Financial shocks move the latest audited year: revenue with operating leverage, EBITDA margin, and receivable days funded with short-term debt; DSCR and Debt/EBITDA are the engine&apos;s after the deal.</>,
      <>Rating: the scenario&apos;s notches plus one notch for each DSCR or Debt/EBITDA band the obligor falls through; PD is the model re-scored at the stressed grade ({r.pd_source === "engine" ? "engine PD" : "with the forward-risk Stage 2 probability"}).</>,
      <>Stage 2 at three notches below origination or DSCR below 1.0; ECL is 12-month in Stage 1, lifetime in Stage 2.</>,
      <>RAROC, SVA, RWA and every limit come from the same engine run, against the same hurdle and risk appetite.</>,
    ]}
    read={<p>A scenario survives when nothing breaches: DSCR 1.0 and its limit, Debt/EBITDA, LTV, covenants, minimum rating, Stage 1, the hurdle and the hard limits.</p>}
    act={<p>Start with what breaks first. A short distance on revenue or margin calls for covenants and cash sweeps; on collateral, for more security or a lower LTV; on RAROC, for pricing.</p>} />;
}

function Heatmap({ r, onOpen }: { r: StressLabResult; onOpen: (s: ScenarioRow) => void }) {
  const cols = visibleCells(r);
  const groups = heatmapGroups(r);
  return (
    <div className="max-h-[480px] overflow-auto" data-testid="stress-heatmap">
      <table className={cn(tableCls, "table-fixed")}>
        <colgroup><col className="w-[190px]" />{cols.map((c) => <col key={c} />)}</colgroup>
        <thead className="sticky top-0 z-10 bg-surface"><tr><th className={thCls}>Scenario</th>{cols.map((c) => <th key={c} className={cn(thCls, "text-center")}>{CELL_LABEL[c]}</th>)}</tr></thead>
        <tbody>
          {groups.map((g) => (
            <React.Fragment key={g.group}>
              {g.group !== "base" ? (
                <tr><td colSpan={cols.length + 1} className="px-2 pb-1 pt-2.5 text-[11px] font-semibold uppercase tracking-[0.06em] text-text-muted">{g.label}</td></tr>) : null}
              {g.rows.map((s) => (
                <tr key={s.id} onClick={() => onOpen(s)} data-testid={`stress-row-${s.id}`}
                    className={cn("cursor-pointer hover:bg-surface-hover", !s.applicable && s.id !== "base" && "opacity-60")}>
                  <td className="truncate border-b border-border/60 px-2 py-1.5 text-text-primary" title={`${s.label}${s.applicable || s.id === "base" ? "" : " (no effect on this obligor)"}`}>
                    <span className={cn(s.id === "base" && "font-semibold")}>{s.label}</span>
                  </td>
                  {cols.map((c) => (
                    <td key={c} className="border-b border-border/60 p-0.5" title={`${CELL_LABEL[c]}: ${TONE_WORD[s.cells[c]]}`}>
                      <span className={cn("block truncate rounded px-1.5 py-1 text-center text-[11px] tabular-nums", TONE_CELL[s.cells[c]])}>{cellText(c, s)}</span>
                    </td>))}
                </tr>))}
            </React.Fragment>))}
        </tbody>
      </table>
    </div>
  );
}

function HeatmapInfo({ r }: { r: StressLabResult }) {
  return <Explainer testId="stress-info-heatmap"
    shows={<p>Each scenario (row) against each test (column), coloured pass, close or breach. The base row is the structure before any stress.</p>}
    formulas={[
      <>DSCR: breach below 1.0 or below the DSCR limit; close within 10% above the limit.</>,
      <>Debt/EBITDA and LTV: breach above the limit; close within 10% of it. Covenants: the memo&apos;s DSCR, net debt/EBITDA and interest cover.</>,
      <>Rating / PD: close on any downgrade, breach below the minimum rating. Stage: breach in Stage 2 or 3.</>,
      <>RAROC: breach below the {pc(r.base.metrics.hurdle)} hurdle, close within 2 points. Limits: breach on a new hard limit, close on a new soft one or a higher approval level.</>,
    ]}
    read={<p>Read across a row for what one scenario breaks; down a column for how fragile one test is. Faded rows do not move this obligor.</p>}
    act={<p>Click a row for the scenario&apos;s shocks, basis and every figure before and after.</p>} />;
}

function DistanceChart({ r }: { r: StressLabResult }) {
  const bars = distanceBars(r);
  if (!bars.length) return <Empty>No reverse stress applies to this structure.</Empty>;
  const tone = { breach: C.down, amber: C.hurdle, pass: C.up };
  const data = [{
    type: "bar", orientation: "h", y: bars.map((b) => b.label), x: bars.map((b) => b.ratio), text: bars.map((b) => b.display),
    textposition: "auto", insidetextanchor: "end", marker: { color: bars.map((b) => tone[b.tone]) },
    customdata: bars.map((b) => fmtDriver(b.driver, b.driver === "revenue_pct" || b.driver === "collateral_pct" ? -b.harshest : b.driver === "rate_bps" ? b.harshest : -b.harshest)),
    hovertemplate: "%{y}<br>Fails at %{text}<br>Harshest tested move %{customdata}<extra></extra>",
  }];
  return <Plot data={data} height={Math.max(200, 28 * bars.length + 70)} testId="stress-distance-chart" filename="deal-desk-distance-to-failure"
               ariaLabel="Distance to failure for each driver and test, as a multiple of the harshest tested move"
               layout={{ margin: { l: 210, r: 16, t: 22, b: 44 }, showlegend: false, bargap: 0.35,
                         yaxis: { autorange: "reversed", automargin: true },
                         xaxis: { title: { text: "Multiple of the harshest tested move" }, range: [0, BEYOND_RATIO], dtick: 0.5 },
                         shapes: [{ type: "line", x0: 1, x1: 1, yref: "paper", y0: 0, y1: 1, line: { color: C.hurdle, dash: "dash", width: 2 } }],
                         annotations: [{ x: 1, y: 1, xref: "x", yref: "paper", yanchor: "bottom", text: "harshest scenario", showarrow: false,
                                         font: { size: 10, color: C.hurdle } }] }} />;
}

function DistanceInfo({ r }: { r: StressLabResult }) {
  const f = firstToBreak(r);
  return <Explainer testId="stress-info-distance"
    shows={<p>Reverse stress: how far revenue, EBITDA margin, collateral value or the benchmark rate can move before DSCR falls below 1.0, LTV breaches its limit, RAROC falls below the hurdle or the deal moves to Stage 2.</p>}
    formulas={[
      <>Each breakeven is the smallest move that fails the test, found by bisection on the engine&apos;s own formulas (DSCR, LTV, rating bands) or on full engine runs (RAROC).</>,
      <>Bar length: the breakeven ÷ the harshest move on that driver among the scenarios (the dashed line at 1). Bars at 3 are beyond the search range.</>,
      ...(f ? [<>First to break: {f.label}, at {f.display}.</>] : []),
    ]}
    read={<p>Red bars fail inside the scenario set; amber within one and a half times it; green further out.</p>}
    act={<p>Protect the shortest bar first: covenants and a cash sweep for revenue and margin, security or a lower amount for collateral, a fixed rate or a hedge for rates.</p>} />;
}

function Resilience({ r }: { r: StressLabResult }) {
  const rows = resilienceRows(r);
  const c = resilienceCounts(r);
  const rec = r.resilience?.recommended;
  if (!r.resilience?.asked) return <Empty>Resilience needs the asked structure.</Empty>;
  return (
    <div data-testid="stress-resilience-table">
      <p className="mb-2 text-[12px] text-text-primary" data-testid="stress-resilience-verdict">{r.resilience.verdict}</p>
      <div className="mb-2 flex flex-wrap gap-1.5">
        <Chip tone="neutral">Asked: {c.asked} of {c.of}</Chip>
        {rec ? <Chip tone="accent">{rec.label}: {c.rec} of {c.of}</Chip> : null}
      </div>
      <div className="max-h-[300px] overflow-y-auto">
        <table className={tableCls}>
          <thead className="sticky top-0 bg-surface"><tr><th className={thCls}>Scenario</th><th className={cn(thCls, "text-right")}>Asked</th>{rec ? <th className={cn(thCls, "text-right")}>Recommended</th> : null}</tr></thead>
          <tbody>
            {rows.map((x) => (
              <tr key={x.id} className={cn(x.differs && "bg-accent-muted/40")} data-differs={x.differs ? "yes" : "no"}>
                <td className="max-w-[180px] truncate border-b border-border/60 px-2 py-1.5" title={x.label}>{x.label}</td>
                <td className={cn(tdCls, "py-1.5 text-right")}><Verdict ok={x.asked} raroc={x.askedRaroc} /></td>
                {rec ? <td className={cn(tdCls, "py-1.5 text-right")}><Verdict ok={x.rec} raroc={x.recRaroc} /></td> : null}
              </tr>))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Verdict({ ok, raroc }: { ok: boolean | null; raroc: number | null }) {
  if (ok === null) return <span className="text-text-muted">–</span>;
  return <span className="inline-flex items-center gap-1.5"><span className="text-text-secondary">{pc(raroc)}</span>
    <Chip tone={ok ? "positive" : "negative"}>{ok ? "Survives" : "Fails"}</Chip></span>;
}

function ResilienceInfo({ r }: { r: StressLabResult }) {
  return <Explainer testId="stress-info-resilience"
    shows={<p>The same scenarios on the asked structure and on the Optimise recommended structure, side by side.</p>}
    formulas={[<>Each cell is a full engine run of that structure under that scenario; RAROC is lifetime RAROC.</>,
               <>A structure survives a scenario when no test breaches (see the heatmap&apos;s (i)).</>,
               <>Highlighted rows are where the two structures part ways.</>]}
    read={<p>{r.resilience?.verdict || "The structure that survives more scenarios, and the severe case, is the more resilient."}</p>}
    act={<p>Prefer the structure that survives the severe case; if neither does, add security or covenants before committee.</p>} />;
}

// ---------------------------------------------------------------- drawer

function Drawer({ s, r, onClose }: { s: ScenarioRow; r: StressLabResult; onClose: () => void }) {
  React.useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  const b = r.base.metrics;
  const m = s.metrics;
  const line = (label: string, before: string, after: string, tone?: CellTone) => (
    <tr key={label}>
      <td className="border-b border-border/60 px-2 py-1.5 text-text-secondary">{label}</td>
      <td className={cn(tdCls, "py-1.5 text-right text-text-secondary")}>{before}</td>
      <td className={cn(tdCls, "py-1.5 text-right font-medium", tone === "breach" ? "text-negative" : tone === "amber" ? "text-warning" : "text-text-primary")}>{after}</td>
    </tr>);
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/30" role="presentation" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <aside role="dialog" aria-modal="true" aria-label={`Scenario ${s.label}`} data-testid="stress-drawer"
             className="flex h-full w-[460px] max-w-[94vw] flex-col overflow-y-auto border-l border-border bg-surface p-4 shadow-2xl">
        <div className="mb-2 flex items-start gap-2">
          <div className="min-w-0">
            <h3 className="truncate text-[14px] font-semibold text-text-primary" title={s.label}>{s.label}</h3>
            <div className="mt-1 flex flex-wrap gap-1.5">
              <Chip>{GROUP_LABEL[s.group] ?? s.group}</Chip>
              {s.severity !== "none" ? <Chip tone={s.severity === "severe" ? "negative" : s.severity === "moderate" ? "warning" : "neutral"}>{s.severity}</Chip> : null}
              <Chip tone={s.survives ? "positive" : "negative"}>{s.survives ? "Survives" : `Fails: ${s.fails_on.map((c) => CELL_LABEL[c]).join(", ")}`}</Chip>
            </div>
          </div>
          <button type="button" onClick={onClose} aria-label="Close" className="ml-auto rounded p-1 text-text-muted hover:bg-surface-hover" data-testid="stress-drawer-close"><X size={16} /></button>
        </div>
        {s.basis ? <p className="text-[12px] leading-5 text-text-secondary">{s.basis}</p> : null}
        <div className="mt-2 flex flex-wrap gap-1.5" data-testid="stress-drawer-shocks">
          {s.shocks.length ? s.shocks.map((x) => <Chip key={x} tone="accent">{x}</Chip>) : <Chip>No shock for this obligor&apos;s sector</Chip>}
        </div>
        <table className={cn(tableCls, "mt-3")}>
          <thead><tr><th className={thCls}>Figure</th><th className={cn(thCls, "text-right")}>Base</th><th className={cn(thCls, "text-right")}>Stressed</th></tr></thead>
          <tbody>
            {line("Revenue", sar(s.financials.base_revenue), sar(s.financials.revenue))}
            {line("EBITDA", sar(s.financials.base_ebitda), sar(s.financials.ebitda))}
            {s.financials.working_capital_funded > 0 ? line("Working capital funded", "–", sar(s.financials.working_capital_funded)) : null}
            {line("DSCR after the deal", x2(b.dscr), x2(m.dscr), s.cells.dscr)}
            {line("Debt/EBITDA", x2(b.debt_ebitda), x2(m.debt_ebitda), s.cells.debt_ebitda)}
            {m.ltv !== null ? line("LTV", pc(b.ltv), pc(m.ltv), s.cells.ltv) : null}
            {line("Rating", b.rating, `${m.rating}${m.notches.total ? ` (${[m.notches.scenario ? `−${m.notches.scenario} scenario` : "", m.notches.implied ? `−${m.notches.implied} financials` : ""].filter(Boolean).join(", ")})` : ""}`, s.cells.rating)}
            {line("PD 12 months", pct(b.pd_12m, { dp: 2 }), pct(m.pd_12m, { dp: 2 }))}
            {s.forward ? line("P(Stage 2) next quarter", "–", pct(s.forward.p_stage2_next_q, { dp: 1 })) : null}
            {line("Stage", `Stage ${b.stage}`, `Stage ${m.stage}`, s.cells.stage)}
            {line("ECL", sar(r.base.metrics.ecl), sar(m.ecl))}
            {line("Lifetime RAROC", pc(b.lifetime_raroc), pc(m.lifetime_raroc), s.cells.raroc)}
            {line("SVA", sar(b.sva), sar(m.sva))}
            {line("RWA year 1", sar(b.rwa_y1), sar(m.rwa_y1))}
            {line("Approval level", r.base.limits.approval_level, s.limits.approval_level, s.limits.approval_change > 0 ? "amber" : undefined)}
          </tbody>
        </table>
        <p className="mt-2 text-[11px] leading-4 text-text-muted">{m.stage_reason}. {m.ecl_basis}.</p>
        {s.covenants.length ? (
          <>
            <h4 className="mt-3 text-[12px] font-medium text-text-secondary">Covenants</h4>
            <ul className="mt-1 space-y-1 text-[12px]" data-testid="stress-drawer-covenants">
              {s.covenants.map((c) => (
                <li key={c.type} className="flex items-center gap-2" title={c.basis}>
                  <span className="min-w-0 flex-1 truncate text-text-secondary">{c.type} {c.type.toLowerCase().includes("debt") ? "≤" : "≥"} {ratio(c.threshold)}x</span>
                  <span className="tabular-nums text-text-primary">{x2(c.value)}</span>
                  <Chip tone={c.status === "breach" ? "negative" : c.status === "amber" ? "warning" : c.status === "pass" ? "positive" : "neutral"}>
                    {c.status === "not_modelled" ? "not moved" : TONE_WORD[c.status]}</Chip>
                </li>))}
            </ul>
          </>) : null}
        <h4 className="mt-3 text-[12px] font-medium text-text-secondary">Limits and appetite</h4>
        <p className="mt-1 text-[12px] text-text-primary" data-testid="stress-drawer-limits">
          {s.limits.new_labels.length ? `New breaches: ${s.limits.new_labels.join("; ")}.` : "No new limit breach."}
          {s.limits.approval_change > 0 ? ` Approval moves up to ${s.limits.approval_level}.` : ""}
        </p>
      </aside>
    </div>
  );
}

// ---------------------------------------------------------------- custom shock

function CustomShock({ onRun, busy, last }: { onRun: (t: string) => void; busy: boolean; last: StressLabResult["custom"] }) {
  const [text, setText] = React.useState(last?.text ?? "");
  return (
    <form className="flex flex-wrap items-center gap-2" data-testid="stress-custom"
          onSubmit={(e) => { e.preventDefault(); if (text.trim()) onRun(text.trim()); }}>
      <label htmlFor="stress-custom-input" className="text-[12px] font-medium text-text-secondary">Your own shock</label>
      <input id="stress-custom-input" value={text} onChange={(e) => setText(e.target.value)} placeholder="revenue −20% and rates +150 bps"
             className="h-8 min-w-[220px] flex-1 rounded-md border border-border bg-surface px-2.5 text-[12px] text-text-primary placeholder:text-text-muted focus:border-accent focus:outline-none" />
      <SecondaryButton type="submit" disabled={busy || !text.trim()} data-testid="stress-custom-run"><Play size={12} /> Run</SecondaryButton>
      {last?.parsed?.length ? <span className="flex flex-wrap gap-1">{last.parsed.map((p) => <Chip key={p} tone="accent">{p}</Chip>)}</span> : null}
    </form>
  );
}

// ---------------------------------------------------------------- the step and the summary

export function StressLab({ proposalId, terms, recommendedTerms, label }: {
  proposalId: string; terms?: Terms | null; recommendedTerms?: Terms | null; label?: string;
}) {
  const [custom, setCustom] = React.useState<string>("");
  const { res, error, busy, retry } = useStress(proposalId, bodyFor(terms, recommendedTerms, label, custom));
  const [open, setOpen] = React.useState<ScenarioRow | null>(null);
  const r = res;
  if (!r) {
    return (
      <Section title="Stress Lab" testId="stress-lab">
        {error ? (
          <div className="flex items-center gap-3" data-testid="stress-error">
            <p className="text-[12px] text-negative">{error}</p><SecondaryButton onClick={retry}>Try again</SecondaryButton>
          </div>) : <Loading text="Running every scenario through the engine" />}
      </Section>);
  }
  const custRow = r.scenarios.find((s) => s.id === "custom");
  return (
    <Section title={`Stress Lab: ${r.structure.label.toLowerCase()} structure`} testId="stress-lab" info={<LabInfo r={r} />}
             action={busy ? <span className="inline-flex items-center gap-1.5 text-[12px] text-text-muted"><Loader2 size={12} className="animate-spin" /> Updating</span> : null}>
      <p className="mb-3 break-words text-[13px] font-semibold leading-5 text-text-primary" data-testid="stress-answer">{answerLine(r)}</p>
      <Tiles r={r} testId="stress-tiles" />
      <div className="mt-3 space-y-1.5">
        <CustomShock onRun={setCustom} busy={busy} last={r.custom} />
        {error ? <p className="text-[12px] text-negative" data-testid="stress-custom-error">{error}</p> : null}
        {custRow ? (
          <p className="text-[12px] text-text-secondary" data-testid="stress-custom-result">
            Your shock: <b className={custRow.survives ? "text-positive" : "text-negative"}>{custRow.survives ? "survives" : `fails ${custRow.fails_on.map((c) => CELL_LABEL[c]).join(", ")}`}</b>
            {" · "}DSCR {x2(custRow.metrics.dscr)} · RAROC {pc(custRow.metrics.lifetime_raroc)} · Stage {custRow.metrics.stage}
            {r.custom?.unparsed?.length ? <span className="text-text-muted"> · not understood: {r.custom.unparsed.join(", ")}</span> : null}
          </p>) : null}
      </div>
      <div className="mt-4">
        <ChartTitle title="Scenario heatmap" info={<HeatmapInfo r={r} />} />
        <Heatmap r={r} onOpen={setOpen} />
      </div>
      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <div className="min-w-0" data-testid="stress-distance">
          <ChartTitle title="Distance to failure" info={<DistanceInfo r={r} />} />
          <DistanceChart r={r} />
        </div>
        <div className="min-w-0" data-testid="stress-resilience">
          <ChartTitle title="Asked against recommended" info={<ResilienceInfo r={r} />} />
          <Resilience r={r} />
        </div>
      </div>
      {open ? <Drawer s={open} r={r} onClose={() => setOpen(null)} /> : null}
    </Section>
  );
}

/** Inside Optimise: one line and at most four tiles, with a link to the Stress step. */
export function StressSummary({ proposalId, terms, recommendedTerms, label, onOpen }: {
  proposalId: string; terms?: Terms | null; recommendedTerms?: Terms | null; label?: string; onOpen?: () => void;
}) {
  const { res, error, busy, retry } = useStress(proposalId, bodyFor(terms, recommendedTerms, label));
  const f = res ? firstToBreak(res) : null;
  return (
    <Section title="Stress summary" testId="stress-summary"
             info={res ? <LabInfo r={res} /> : undefined}
             action={onOpen ? <PrimaryButton onClick={onOpen} className="h-8 px-3 text-[12px]" data-testid="stress-summary-open">Open Stress Lab <ArrowRight size={13} /></PrimaryButton> : null}>
      {res ? (
        <>
          <p className="mb-3 break-words text-[13px] leading-5 text-text-primary" data-testid="stress-summary-answer">
            <b>{answerLine(res)}</b>
            {f ? <span className="text-text-secondary"> First to break: {f.label.replace(" → ", " to ")} at {f.display}.</span> : null}
          </p>
          <Tiles r={res} testId="stress-summary-tiles" />
        </>
      ) : error ? (
        <div className="flex items-center gap-3"><p className="text-[12px] text-negative">{error}</p><SecondaryButton onClick={retry}>Try again</SecondaryButton></div>
      ) : busy ? <Loading text="Stressing this structure" /> : null}
    </Section>
  );
}

