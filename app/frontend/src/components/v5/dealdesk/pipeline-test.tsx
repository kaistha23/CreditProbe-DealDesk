"use client";

/**
 * R11 Session L (PLAN_R11 L5, contract): `PipelineTestButton({ proposalId, terms, ready })`.
 *
 * Disabled until Optimise has a result (`ready`), then live by itself; a click re-solves the pending pipeline
 * with this deal, on the structure picked in Optimise (`terms`, default the recommended one), forced in and optional.
 * The answer renders compactly with the same components as Pipeline mode: one line, at most 4 tiles, the deals it
 * displaces and its marginal effect on each risk-appetite limit (before = the pipeline without it, after = with it).
 */

import * as React from "react";
import { GitCompareArrows } from "lucide-react";

import { KpiRow } from "@/components/v5/core/kpi-row";
import { Skeleton } from "@/components/ui/skeleton";
import { InfoPopover } from "./explain"; // R12 G (I6): the bounded Deal Desk (i)
import type { Terms } from "@/lib/v5/dealdesk";
import { type PipelineTest, canTest, pipelineApi, testLine } from "@/lib/v5/dealdesk-pipeline";
import { pct, sar } from "@/lib/v5/format";
import { friendlyMessage } from "@/lib/v5/errors";
import { PlainWords } from "@/components/v5/ui/plain-words"; // R14 U (K34)
import { type PipelineLines, flowApi } from "@/lib/v5/dealdesk-flow"; // R14 F (K21)

import { APPETITE_INFO, AppetitePanel } from "./appetite-panel";
import { ChartTitle, Chip, PrimaryButton } from "./kit";

export const PIPELINE_TEST_INFO = (
  <>
    Tests this deal, on the structure picked in Optimise, against every pending deal and every limit. The whole pending pipeline is re-solved
    exactly twice: with this deal optional (does it make the cut on its own merits?) and with it forced in (what it displaces and what it costs).
    Rank is by SVA per unit of RWA among the deals the optimiser approves. The limit that binds first is the one whose remaining headroom holds the
    fewest multiples of this deal.
  </>
);

export function PipelineTestResult({ t }: { t: PipelineTest }) {
  const tiles = [
    { label: "Makes the cut", value: t.makes_cut ? "Yes" : t.fits ? "No" : "Cannot fit", tone: (t.makes_cut ? "positive" : "negative") as "positive" | "negative",
      sub: t.value_change === null ? "forced in, it breaks a hard limit" : `${t.value_change >= 0 ? "+" : ""}${sar(t.value_change)} pipeline value`,
      info: "Whether the exact optimum of the pending pipeline approves this deal when it is optional, and how the pipeline's value changes with it forced in." },
    { label: "Rank", value: `${t.rank} of ${t.ranked}`, sub: `${sar(t.sva_per_100m_rwa)} SVA per 100m RWA`,
      info: "Rank by SVA per unit of RWA among the approved deals, with this one in." },
    { label: "Displaces", value: String(t.displaced.length), sub: t.displaced.length ? t.displaced.map((d) => d.proposal_id).join(", ") : "No deal drops out",
      info: "Deals approved without this one that drop out of the optimum once it is forced in." },
    { label: "Binds first", value: t.binds_first ? t.binds_first.label : "–", sub: t.binds_first ? `${t.binds_first.scope} · ${t.binds_first.times >= 0 ? `${t.binds_first.times.toFixed(1)}x headroom` : "past limit"}` : "",
      tone: (t.binds_first && t.binds_first.times < 1 ? "negative" : "neutral") as "negative" | "neutral",
      info: "The limit whose remaining headroom, after the rest of the selection, holds the fewest multiples of this deal." },
  ];
  return (
    <div className="space-y-3" data-testid="dealdesk-pipeline-test-result">
      <p className="text-[13px] font-semibold text-text-primary" data-testid="dealdesk-pipeline-test-line">{testLine(t)}</p>
      <KpiRow tiles={tiles} testId="dealdesk-pipeline-test-tiles" />
      {t.displaced.length || t.resized.length ? (
        <div className="flex flex-wrap items-center gap-1.5 text-[12px] text-text-secondary" data-testid="dealdesk-pipeline-test-displaced">
          {t.displaced.map((d) => <Chip key={d.proposal_id} tone="negative" title={`SVA ${sar(d.sva)}, RWA ${sar(d.rwa)}`}>{d.proposal_id} out</Chip>)}
          {t.resized.map((d) => <Chip key={d.proposal_id} tone="warning" title={`${d.from} to ${d.to}`}>{d.proposal_id} resized</Chip>)}
        </div>) : null}
      <div>
        <ChartTitle title="Marginal effect on the risk appetite" info={APPETITE_INFO} />
        <AppetitePanel rows={t.limits} compact testId="dealdesk-pipeline-test-appetite" />
      </div>
      <p className="text-[11px] text-text-muted">
        {t.structure.label}: {sar(t.structure.amount_sar_mn)}, RAROC {pct(t.structure.lifetime_raroc)}, SVA {sar(t.structure.sva)} · pipeline of {t.pipeline.deals} pending deals,
        RWA budget {sar(t.pipeline.rwa_budget)}.
      </p>
    </div>
  );
}

export function PipelineTestButton({ proposalId, terms, ready }: {
  proposalId: string; terms?: Terms | Partial<Terms> | null; ready: boolean;
}) {
  const [busy, setBusy] = React.useState(false);
  // The answer belongs to the deal, structure and optimisation it was run on: a new one hides it.
  const key = `${proposalId}|${JSON.stringify(terms ?? null)}|${ready}`;
  const [out, setOut] = React.useState<{ key: string; res: PipelineTest | null; error: string } | null>(null);
  const res = out?.key === key ? out.res : null;
  const error = out?.key === key ? out.error : "";
  const run = async () => {
    if (!canTest(ready, busy)) return;
    setBusy(true);
    setOut(null);
    try {
      setOut({ key, res: await pipelineApi.test(proposalId, terms ?? null), error: "" });
    } catch (e) {
      setOut({ key, res: null, error: friendlyMessage(e, "Deal Desk") });
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="space-y-3" data-testid="dealdesk-pipeline-test">
      <div className="flex flex-wrap items-center gap-2">
        <PrimaryButton onClick={() => void run()} disabled={!canTest(ready, busy)} data-testid="dealdesk-pipeline-test-button"
                       data-ready={ready ? "true" : "false"} title={ready ? undefined : "Available once Optimise has a result"}>
          <GitCompareArrows size={14} /> {busy ? "Testing against the pipeline…" : "Test against pipeline"}
        </PrimaryButton>
        <InfoPopover title="Test against pipeline">{PIPELINE_TEST_INFO}</InfoPopover>
      </div>
      {error ? <p className="text-[12px] text-negative" role="alert">{error}</p> : null}
      {busy && !res ? <Skeleton className="h-28 w-full" /> : null}
      {res ? <PipelineTestResult t={res} /> : null}
    </div>
  );
}

// ------------------------------------------------------------------ R14 F (K21): the test on the selected structure, explained

const RAG_TONE: Record<string, "positive" | "warning" | "negative"> = { green: "positive", amber: "warning", red: "negative" };

function lineValue(v: number | string | null, unit: string): string {
  if (v == null) return "–";
  if (typeof v === "string") return v;
  if (unit === "share") return pct(v);
  if (unit.startsWith("SAR")) return v === 0 ? "SAR 0.0m" : sar(v);
  const u = unit === "years" && v === 1 ? "year" : unit;
  return `${v.toLocaleString("en-US", { maximumFractionDigits: 2 })}${u ? ` ${u}` : ""}`;
}

/** R14 F (K21): "Would this deal get a slot in this quarter's pipeline…?" on the selected structure, with the deal's own lines. */
export function PipelineLinesPanel({ proposalId, structureKey, structureLabel }: { proposalId: string; structureKey: string | null; structureLabel: string }) {
  const [busy, setBusy] = React.useState(false);
  const key = `${proposalId}|${structureKey}`;
  const [out, setOut] = React.useState<{ key: string; res: PipelineLines | null; error: string } | null>(null);
  const res = out?.key === key ? out.res : null;
  const error = out?.key === key ? out.error : "";
  const run = async () => {
    setBusy(true);
    setOut(null);
    try { setOut({ key, res: await flowApi.pipelineLines(proposalId, structureKey ?? undefined), error: "" }); }
    catch (e) { setOut({ key, res: null, error: friendlyMessage(e, "Deal Desk") }); }
    finally { setBusy(false); }
  };
  return (
    <div className="space-y-3" data-testid="dealdesk-pipeline-test" data-structure={structureKey ?? ""}>
      <p className="text-[12px] text-text-secondary" data-testid="dealdesk-pipeline-purpose">
        Would this deal get a slot in this quarter&apos;s pipeline under the RWA and EL budget, and what does it push out? Tested on: <b>{structureLabel}</b>.</p>
      <div className="flex flex-wrap items-center gap-2">
        <PrimaryButton onClick={() => void run()} disabled={busy} data-testid="dealdesk-pipeline-test-button" data-ready="true">
          <GitCompareArrows size={14} /> {busy ? "Testing against the pipeline…" : `Test ${structureLabel.toLowerCase()} against the pipeline`}</PrimaryButton>
        <InfoPopover title="Test against pipeline">{PIPELINE_TEST_INFO}</InfoPopover>
      </div>
      {error ? <p className="text-[12px] text-negative" role="alert">{error}</p> : null}
      {busy && !res ? <Skeleton className="h-28 w-full" /> : null}
      {res ? (
        <div className="space-y-3" data-testid="dealdesk-pipeline-test-result">
          <PlainWords lines={res.plain_words} speak testId="dealdesk-pipeline-plain-words" />
          <p className="text-[13px] font-semibold text-text-primary" data-testid="dealdesk-pipeline-test-line">{res.verdict}</p>
          <p className="text-[11px] text-text-muted" data-testid="dealdesk-pipeline-label">{res.label_line}</p>
          <KpiRow testId="dealdesk-pipeline-test-tiles" tiles={[
            { label: "Makes the cut", value: res.makes_cut ? "Yes" : res.fits ? "No" : "Cannot fit", tone: res.makes_cut ? "positive" : "negative",
              sub: `Rank ${res.rank} of ${res.ranked} by SVA per RWA`, info: "Whether the exact optimum of the pending pipeline approves this structure when it is optional." },
            { label: "This deal's SVA", value: sar(res.sva.value), sub: res.sva.label, info: res.value_text ?? undefined },
            { label: "Other deals changed", value: String(res.displaces_count), sub: res.displaces_text,
              info: "Deals that drop out of the optimum, or are resized to a smaller option, once this one is in. Resized deals are counted." },
            { label: "Closest limit", value: res.closest_short?.label ?? "–", sub: res.closest_short ? `${res.closest_short.room} · ${res.closest_short.scope}` : "",
              info: res.closest_limit ?? "The limit whose remaining room holds the fewest multiples of this deal." },
          ]} />
          {res.resized.length ? <ul className="space-y-0.5 text-[12px] text-text-secondary" data-testid="dealdesk-pipeline-resized">
            {res.resized.map((d) => <li key={d.proposal_id}>{d.text}.</li>)}</ul> : null}
          {res.value_text ? <p className="text-[12px] text-text-secondary" data-testid="dealdesk-pipeline-value-text">{res.value_text}</p> : null}
          <div>
            <ChartTitle title="This deal's own lines: before → after" info={<>The deal&apos;s own obligor, group, sector, rating bucket and product limits, measured on the book before and after this structure. RAG: {Object.entries(res.rag_legend).map(([k, v]) => `${k} = ${v}`).join("; ")}.</>} />
            <div className="overflow-x-auto"><table className="w-full border-collapse text-[12px]" data-testid="dealdesk-pipeline-lines">
              <thead><tr>{["Line", "Scope", "Before", "After", "Limit", "Room after this deal", ""].map((h) => (
                <th key={h} className="border-b border-border px-2 py-2 text-left text-[11px] font-medium uppercase tracking-[0.06em] text-text-muted">{h}</th>))}</tr></thead>
              <tbody>{res.lines.map((l) => (
                <tr key={`${l.name}-${l.scope}`} data-testid="dealdesk-pipeline-line" data-rag={l.rag}>
                  <td className="border-b border-border/60 px-2 py-1.5">{l.line}</td>
                  <td className="border-b border-border/60 px-2 py-1.5">{l.scope}</td>
                  <td className="border-b border-border/60 px-2 py-1.5 tabular-nums">{lineValue(l.before, l.unit)}</td>
                  <td className="border-b border-border/60 px-2 py-1.5 tabular-nums">{lineValue(l.after, l.unit)}</td>
                  <td className="border-b border-border/60 px-2 py-1.5 tabular-nums">{lineValue(l.limit, l.unit)}</td>
                  <td className="border-b border-border/60 px-2 py-1.5 tabular-nums">{l.room_times_deal != null ? `${l.room_times_deal.toFixed(1)}× this deal` : l.headroom != null ? `${lineValue(l.headroom, l.unit)} left` : "–"}</td>
                  <td className="border-b border-border/60 px-2 py-1.5"><Chip tone={RAG_TONE[l.rag]}>{l.rag === "green" ? "Green" : l.rag === "amber" ? "Amber" : "Red"}</Chip></td>
                </tr>))}</tbody>
            </table></div>
          </div>
        </div>) : null}
    </div>
  );
}
