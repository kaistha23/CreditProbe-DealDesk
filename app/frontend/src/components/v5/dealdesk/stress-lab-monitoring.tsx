"use client";

/**
 * PLAN_R12 Session D (I22-5, §1.5 "the tier travels"): the monitoring plan of one deal. Exported for Session U (the
 * Recommendation step, the approval) and Session I (the Book row):
 *
 *   MonitoringPlanPanel   the plan in force (tier, drivers, triggers, review), "Set at approval", and a tier change
 *                         that needs a reason (logged as a new version in dd_monitoring_plan)
 */

import * as React from "react";
import { Loader2 } from "lucide-react";

import { cn } from "@/lib/utils";
import type { Terms } from "@/lib/v5/dealdesk";
import { TIER_TONE, stress2Api, tierSentence, type Plan, type Tier } from "@/lib/v5/dealdesk-stress2";

import { Chip, Empty, PrimaryButton, SecondaryButton, Section } from "./kit";
import { InfoPopover } from "@/components/ui/info-popover"; // R13 X: notes behind the (i)

const TIERS: Tier[] = ["High", "Medium", "Standard"];

export function MonitoringPlanPanel({ proposalId, terms, canApprove = false, onChange }: {
  proposalId: string; terms?: Terms | null; canApprove?: boolean; onChange?: (p: Plan) => void;
}) {
  const [plan, setPlan] = React.useState<Plan | null | undefined>(undefined);
  const [history, setHistory] = React.useState<Plan[]>([]);
  const [error, setError] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [tier, setTier] = React.useState<Tier>("High");
  const [reason, setReason] = React.useState("");
  const load = React.useCallback(() => {
    stress2Api.plan(proposalId).then((r) => { setPlan(r.plan); setHistory(r.history); if (r.plan) setTier(r.plan.tier); })
      .catch((e: Error) => { setError(e.message); setPlan(null); });
  }, [proposalId]);
  React.useEffect(() => { load(); }, [load]);
  const approve = async () => {
    setBusy(true);
    setError("");
    try {
      const r = await stress2Api.publishPlan(proposalId, { terms: terms ?? null });
      onChange?.(r.plan);
      load();
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  const change = async () => {
    setBusy(true);
    setError("");
    try {
      const r = await stress2Api.changeTier(proposalId, tier, reason);
      onChange?.(r.plan);
      setReason("");
      load();
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <Section title="Monitoring plan" testId="stress2-plan">
      {plan === undefined ? <Empty><span className="inline-flex items-center gap-2"><Loader2 size={14} className="animate-spin" /> Reading the plan</span></Empty> : null}
      {plan === null ? (
        <div className="flex flex-wrap items-center gap-3" data-testid="stress2-plan-none">
          <p className="flex items-center gap-1 text-[12px] text-text-secondary">Tier not set yet<InfoPopover title="Monitoring tier">The tier is set at approval from the stress verdict, as a condition.</InfoPopover></p>
          {canApprove ? <PrimaryButton onClick={approve} disabled={busy} data-testid="stress2-plan-approve">Set at approval</PrimaryButton> : null}
        </div>) : null}
      {plan ? (
        <div className="space-y-2" data-testid="stress2-plan-current">
          <div className="flex flex-wrap items-center gap-1.5">
            <Chip tone={TIER_TONE[plan.tier]}>Tier {plan.tier}</Chip>
            <Chip>Review every {plan.review_frequency_months} months · next {plan.next_review_date}</Chip>
            <Chip>v{plan.version}</Chip>
          </div>
          <p className="text-[12px] text-text-primary" data-testid="stress2-plan-sentence">{tierSentence(plan)}.</p>
          <p className="text-[12px] text-text-secondary">{plan.reason}</p>
          {plan.triggers?.length ? (
            <ul className="space-y-1 text-[12px]">
              {plan.triggers.map((t) => <li key={t.trigger_id} className="flex items-center gap-2"><Chip tone={t.action === "alert" ? "negative" : "warning"}>{t.action === "alert" ? "EWS alert" : "watch"}</Chip><span className="min-w-0 flex-1 truncate" title={t.basis}>{t.label}</span></li>)}
            </ul>) : null}
          <div className="flex flex-wrap items-end gap-2 border-t border-border pt-2">
            <label className="flex flex-col gap-1 text-[11px] text-text-secondary">Change tier
              <select className="h-8 rounded-md border border-border bg-surface px-2 text-[12px]" value={tier} onChange={(e) => setTier(e.target.value as Tier)}>
                {TIERS.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </label>
            <label className="flex min-w-[220px] flex-1 flex-col gap-1 text-[11px] text-text-secondary">Reason (required)
              <input className="h-8 rounded-md border border-border bg-surface px-2 text-[12px]" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Cash collateral of 30% received" />
            </label>
            <SecondaryButton onClick={change} disabled={busy || tier === plan.tier || reason.trim().length < 5} data-testid="stress2-plan-change">Change tier</SecondaryButton>
          </div>
          {history.length > 1 ? (
            <details className="text-[11px] text-text-muted">
              <summary className="cursor-pointer">History ({history.length} versions)</summary>
              <ul className="mt-1 space-y-0.5">
                {history.slice().reverse().map((h) => <li key={h.plan_id} className={cn(h.plan_id === plan.plan_id && "text-text-primary")}>v{h.version} · {h.set_on} · {h.previous_tier ? `${h.previous_tier} → ` : ""}{h.tier} · {h.set_by}: {h.reason}</li>)}
              </ul>
            </details>) : null}
        </div>) : null}
      {error ? <p className="mt-2 text-[12px] text-negative" data-testid="stress2-plan-error">{error}</p> : null}
    </Section>
  );
}
