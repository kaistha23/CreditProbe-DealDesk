"use client";

/**
 * The PD model card for a proposal (DEAL_DESK_PROMPT 3.2a): the corporate XGBoost model the What-If domain owns,
 * read-only here; what it scores, its target, training data, calibration, monotone constraints, the
 * out-of-range check for this obligor and the model's limitations. Opened from the PD chip; never inline.
 */

import * as React from "react";
import { X } from "lucide-react";

import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { dealdesk, rate } from "@/lib/v5/dealdesk";

import { Chip, tableCls, tdCls, thCls } from "./kit";
import { friendlyMessage } from "@/lib/v5/errors";

interface Feature { feature: string; value: number; p01: number; p99: number; min: number; max: number; status: string; kind?: string }
interface CardT {
  trace_id: string; model?: { version?: string; trained?: string }; role?: string; target?: string; scores?: string;
  training?: { domain?: string; periods?: string; rows?: number; split?: string };
  calibration?: Record<string, { rows?: number; r2?: number; mean_actual?: number; mean_predicted?: number }>;
  monotone_constraints?: string | Record<string, number>; deal_terms_in_model?: string[]; limitations?: string[];
  proposal?: { out_of_range?: { status?: string; features?: Feature[] } };
  out_of_range?: { status?: string; features?: Feature[] };
}

/** G5: a feature value. Probabilities and shares (below 1) read as %, with 2 decimals; the rest with at most 2 decimals. */
const fmt = (v: number) => (Math.abs(v) < 1 && v !== 0 && !Number.isInteger(v)
  ? `${(v * 100).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`
  : v.toLocaleString("en-US", { maximumFractionDigits: 2 }));

export function ModelCardDialog({ proposalId, onClose }: { proposalId: string; onClose: () => void }) {
  const [card, setCard] = React.useState<CardT | null>(null);
  const [error, setError] = React.useState("");
  React.useEffect(() => {
    let live = true;
    dealdesk.modelCard(proposalId).then((c) => { if (live) setCard(c as unknown as CardT); }, (e: unknown) => { if (live) setError(friendlyMessage(e)); });
    return () => { live = false; };
  }, [proposalId]);
  const oor = card?.proposal?.out_of_range ?? card?.out_of_range;
  const rows: [string, React.ReactNode][] = card ? [
    ["Model", `${card.model?.version ?? ""}${card.model?.trained ? ` · trained ${card.model.trained.slice(0, 10)}` : ""}`],
    ["Role in Deal Desk", card.role ?? ""], ["Target", card.target ?? ""], ["Scores", card.scores ?? ""],
    ["Training data", card.training ? `${card.training.domain ?? ""}, ${card.training.periods ?? ""}, ${(card.training.rows ?? 0).toLocaleString("en-US")} rows` : ""],
    ["Deal terms in the model", card.deal_terms_in_model?.length ? card.deal_terms_in_model.join(", ") : "None"],
    ["Monotone constraints", typeof card.monotone_constraints === "string" ? card.monotone_constraints : JSON.stringify(card.monotone_constraints ?? "")],
  ] : [];
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-auto bg-black/30 p-8" role="dialog" aria-modal="true"
         aria-label="PD model card" data-testid="dealdesk-model-card">
      <Card className="w-full max-w-3xl space-y-4 p-6">
        <div className="flex items-center gap-2">
          <h2 className="text-[16px] font-semibold text-text-primary">PD model card</h2>
          {oor?.status ? <Chip tone={oor.status === "in_range" ? "positive" : "warning"}>{oor.status === "in_range" ? "In training range" : "Outside training range"}</Chip> : null}
          <button type="button" onClick={onClose} aria-label="Close" data-testid="dealdesk-model-card-close"
                  className="ml-auto rounded-md p-1 text-text-muted hover:bg-surface-hover"><X size={16} /></button>
        </div>
        {error ? <p className="text-[12px] text-negative" role="alert">{error}</p> : null}
        {!card && !error ? <Skeleton className="h-64 w-full" /> : null}
        {card ? (
          <>
            <dl className="grid grid-cols-[180px_1fr] gap-x-4 gap-y-2 text-[12px]">
              {rows.map(([k, v]) => (<React.Fragment key={k}><dt className="text-text-muted">{k}</dt><dd className="text-text-primary">{v}</dd></React.Fragment>))}
            </dl>
            {card.calibration ? (
              <table className={tableCls}>
                <thead><tr><th className={thCls}>Calibration</th><th className={cn(thCls, "text-right")}>Rows</th><th className={cn(thCls, "text-right")}>R²</th>
                  <th className={cn(thCls, "text-right")}>Mean actual</th><th className={cn(thCls, "text-right")}>Mean predicted</th></tr></thead>
                <tbody>{Object.entries(card.calibration).filter(([, c]) => c && typeof c === "object" && c.rows).map(([k, c]) => (
                  <tr key={k}><td className={tdCls}>{k.replace(/_/g, " ")}</td><td className={cn(tdCls, "text-right")}>{(c.rows ?? 0).toLocaleString("en-US")}</td>
                    <td className={cn(tdCls, "text-right")}>{c.r2 === undefined ? "–" : c.r2.toFixed(2)}</td>
                    <td className={cn(tdCls, "text-right")}>{c.mean_actual === undefined ? "—" : rate(c.mean_actual, 2)}</td>
                    <td className={cn(tdCls, "text-right")}>{c.mean_predicted === undefined ? "—" : rate(c.mean_predicted, 2)}</td></tr>))}</tbody>
              </table>) : null}
            {oor?.features?.length ? (
              <table className={tableCls} data-testid="dealdesk-model-card-range">
                <thead><tr><th className={thCls}>Feature</th><th className={cn(thCls, "text-right")}>This obligor</th>
                  <th className={cn(thCls, "text-right")}>1st–99th percentile</th><th className={thCls}>Range</th></tr></thead>
                <tbody>{[...oor.features].sort((a, b) => Number(a.status === "in_range") - Number(b.status === "in_range")).map((f) => (
                  <tr key={f.feature}><td className={tdCls}>{f.feature.replace(/_/g, " ")}</td><td className={cn(tdCls, "text-right")}>{fmt(f.value)}</td>
                    <td className={cn(tdCls, "text-right")}>{fmt(f.p01)} – {fmt(f.p99)}</td>
                    <td className={tdCls}>{f.status === "in_range" ? <Chip tone="positive">In range</Chip> : <Chip tone="warning">Outside</Chip>}</td></tr>))}</tbody>
              </table>) : null}
            {card.limitations?.length ? (
              <ul className="ml-4 list-disc space-y-1 text-[12px] text-text-secondary">{card.limitations.map((l) => <li key={l}>{l}</li>)}</ul>) : null}
          </>) : null}
      </Card>
    </div>
  );
}
