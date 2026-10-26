"use client";

/**
 * R14 Session F (K23 (2), K25 (1)): the structure set on the Structure step. Rows Ask · Recommended · Alternatives ·
 * Your structures, each with base RAROC against the hurdle, SVA (one basis), DSCR, covenant headroom, capacity check and
 * approval authority; one Select per row; a sticky bar "Selected: <name> → Recommend", disabled with the reason. The
 * selection is the input to Stress (header button) and Recommendation.
 */

import * as React from "react";
import { ArrowRight, Check } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { PlainWords } from "@/components/v5/ui/plain-words";
import { cn } from "@/lib/utils";
import { type StructureRow, type StructureSet, flowApi, grouped, pct, sarm, x } from "@/lib/v5/dealdesk-flow";
import { friendlyMessage } from "@/lib/v5/errors";

import { Chip, PrimaryButton, Section, tableCls, tdCls, thCls } from "./kit";

export function useStructureSet(proposalId: string, nonce = 0): { set: StructureSet | null; error: string; setSet: (s: StructureSet) => void } {
  const [set, setSet] = React.useState<StructureSet | null>(null);
  const [error, setError] = React.useState("");
  React.useEffect(() => {
    let live = true;
    void flowApi.structureSet(proposalId).then((s) => { if (live) { setSet(s); setError(""); } })
      .catch((e) => { if (live) setError(friendlyMessage(e, "Deal Desk")); });
    return () => { live = false; };
  }, [proposalId, nonce]);
  return { set, error, setSet };
}

function Head({ r }: { r: StructureRow }) {
  return (
    <div className="min-w-0">
      <p className="truncate font-medium text-text-primary" title={r.origin}>{r.label}</p>
      <p className="truncate text-[11px] text-text-muted" title={r.origin}>{r.origin}</p>
    </div>
  );
}

export function StructureSetTable({ set, onSelect, busy, compact }: {
  set: StructureSet; onSelect?: (key: string) => void; busy?: boolean; compact?: boolean;
}) {
  return (
    <div className="overflow-x-auto">
      <table className={cn(tableCls, "table-fixed min-w-[920px]")} data-testid="flow-structure-table">
        <colgroup><col className="w-[22%]" /><col className="w-[12%]" /><col className="w-[10%]" /><col className="w-[8%]" /><col className="w-[12%]" />
          <col className="w-[14%]" /><col className="w-[13%]" /><col className="w-[9%]" /></colgroup>
        <thead><tr>
          {["Structure", "RAROC vs hurdle", "SVA", "DSCR", "Covenant headroom", "Capacity", "Approval", ""].map((h) => <th key={h} className={cn(thCls, "whitespace-normal")}>{h}</th>)}
        </tr></thead>
        {grouped(set).map((g) => (
          <tbody key={g.group} data-testid={`flow-structure-group-${g.group.toLowerCase().replace(/\W+/g, "-")}`}>
            <tr><td colSpan={8} className="bg-canvas px-2 py-1 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-text-muted">{g.group}</td></tr>
            {g.rows.length ? g.rows.map((r) => (
              <tr key={r.key} data-testid={`flow-structure-row-${r.key}`} data-selected={r.selected ? "true" : "false"}
                  className={cn(r.selected && "bg-accent-muted")}>
                <td className={cn(tdCls, "whitespace-normal")}><Head r={r} /></td>
                <td className={tdCls}><span className={cn("font-semibold", r.clears_hurdle ? "text-positive" : "text-negative")}>{pct(r.raroc, 2)}</span>
                  <span className="block text-[11px] text-text-muted">hurdle {pct(r.hurdle)}</span></td>
                <td className={cn(tdCls, r.sva < -1e-6 ? "text-negative" : "")} title={r.sva_label}>{sarm(r.sva)}</td>
                <td className={tdCls}>{x(r.dscr)}</td>
                <td className={cn(tdCls, "whitespace-normal")} title={r.covenant_tightest ?? undefined}>
                  {r.covenant_headroom == null ? "–" : <span className={cn(r.covenant_headroom < 0 ? "text-negative" : r.covenant_headroom < 0.1 ? "text-warning" : "")}>{pct(r.covenant_headroom, 0)}</span>}
                  {r.covenant_tightest && !compact ? <span className="block truncate text-[11px] text-text-muted">{r.covenant_tightest}</span> : null}</td>
                <td className={cn(tdCls, "whitespace-normal")} title={r.capacity.formula}>
                  <Chip tone={r.capacity.passes ? "positive" : "negative"}>{r.capacity.passes ? "Within" : "Above"}</Chip>
                  <span className="block text-[11px] text-text-muted">{sarm(r.capacity.ask_sar_mn)} vs {sarm(r.capacity.capacity_sar_mn)}</span></td>
                <td className={cn(tdCls, "whitespace-normal")} title={[r.approval.rule, ...r.approval.reasons].filter(Boolean).join(" · ")}>
                  <span className="line-clamp-2 text-[12px]">{r.approval.level}</span></td>
                <td className={tdCls}>
                  {onSelect ? (r.selected
                    ? <Chip tone="accent" testId={`flow-structure-selected-${r.key}`}><Check size={12} /> Selected</Chip>
                    : <button type="button" disabled={busy} onClick={() => onSelect(r.key)} data-testid={`flow-structure-select-${r.key}`}
                              className="h-7 rounded-md border border-border px-2.5 text-[12px] text-text-secondary hover:border-accent hover:text-accent disabled:opacity-40">Select</button>)
                    : null}
                </td>
              </tr>)) : (
              <tr><td colSpan={8} className={cn(tdCls, "text-[12px] text-text-muted")}>
                {g.group === "Your structures" ? "None yet: build one in Structure it yourself and save it, or stress-proof a structure." : "None."}</td></tr>)}
          </tbody>))}
      </table>
    </div>
  );
}

/** The sticky bar: "Selected: <name> → Recommend", disabled with the reason. */
export function SelectedBar({ set, onRecommend, busy }: { set: StructureSet; onRecommend: (r: StructureRow) => void; busy?: boolean }) {
  const cur = set.rows.find((r) => r.key === set.selected) ?? set.rows[0];
  return (
    <div className="sticky bottom-0 z-10 flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-accent/40 bg-surface px-3 py-2 shadow-sm"
         data-testid="flow-selected-bar" data-enabled={set.bar.enabled ? "true" : "false"}>
      <span className="text-[13px] font-semibold text-text-primary" data-testid="flow-selected-label">{set.bar.label}</span>
      <span className="text-[12px] text-text-secondary">RAROC {pct(cur.raroc, 2)} · SVA {sarm(cur.sva)} · {cur.approval.level}</span>
      {!set.bar.enabled ? <span className="min-w-0 flex-1 text-[12px] text-negative" data-testid="flow-recommend-reason">Cannot recommend: {set.bar.reason}</span>
        : <span className="flex-1" />}
      <PrimaryButton onClick={() => onRecommend(cur)} disabled={busy || !set.bar.enabled} data-testid="flow-recommend"
                     title={set.bar.enabled ? undefined : set.bar.reason}>Recommend <ArrowRight size={14} /></PrimaryButton>
    </div>
  );
}

export function StructureSetPanel({ proposalId, nonce = 0, onChange, onRecommend, busy }: {
  proposalId: string; nonce?: number; onChange?: (s: StructureSet) => void; onRecommend: (r: StructureRow) => void; busy?: boolean;
}) {
  const { set, error, setSet } = useStructureSet(proposalId, nonce);
  const [working, setWorking] = React.useState(false);
  const [err, setErr] = React.useState("");
  React.useEffect(() => { if (set) onChange?.(set); }, [set, onChange]);
  const select = async (key: string) => {
    setWorking(true);
    setErr("");
    try { setSet(await flowApi.select(proposalId, key)); } catch (e) { setErr(friendlyMessage(e, "Deal Desk")); } finally { setWorking(false); }
  };
  return (
    <Section title="The structures this deal is judged on" testId="flow-structure-set"
             info="Every structure measured the same way: base RAROC against the hurdle, SVA on one basis, DSCR after the deal, the tightest covenant's headroom, the capacity check by product and the approval authority from one Delegation of Authority engine.">
      {error ? <p role="alert" className="text-[12px] text-negative">{error}</p> : null}
      {!set && !error ? <><PlainWords lines={[]} loading /><Skeleton className="mt-3 h-48 w-full" /></> : null}
      {set ? (
        <div className="space-y-3">
          <PlainWords lines={set.plain_words} speak testId="flow-structure-plain-words" />
          {set.default_note ? <p className="text-[12px] text-text-secondary" data-testid="flow-default-note">{set.default_note}</p> : null}
          <StructureSetTable set={set} onSelect={(k) => void select(k)} busy={working || busy} />
          {err ? <p role="alert" className="text-[12px] text-negative">{err}</p> : null}
          <p className="text-[11px] text-text-muted">{set.sva_basis}. Capacity, approval and SVA from the Deal Desk engines; hover a cell for its formula or rule.</p>
          <SelectedBar set={set} onRecommend={onRecommend} busy={working || busy} />
        </div>) : null}
    </Section>
  );
}
