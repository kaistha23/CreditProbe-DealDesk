"use client";

/**
 * R13 M (PLAN_R13 §I): one place that turns a routed question (lib/v5/intel-intents.ts `routeIntel`) into the engine's
 * own compact panel. Used by Noor's Ask tab (the answer under the box) and by `IntelHost` (the drawer any page opens
 * with `?intel=<key>`, which is where the Noor panel sends a question). The panels are the sessions' exports, unchanged.
 */

import * as React from "react";
import Link from "next/link";
import { ArrowUpRight, X } from "lucide-react";

import { FinQualityPanel } from "@/components/v5/dealdesk/fin-quality";
import { DecisionConsistencyPanel, ReverseSolverPanel, SecurityOptimiserPanel } from "@/components/v5/dealdesk/intel";
import {
  CommitteeRehearsalPanel, DefaultPremortemPanel, GroupContagionPanel, NegotiationFrontierPanel, PrecedentExplorerPanel, PricingBenchmarkPanel,
  RenewalDiffPanel, RevenueTruthPanel,
} from "@/components/v5/dealdesk/intel2"; // R14 i (D13 replaces the R13 challenger panel, K29)
import { DoaPanel, ExceptionPanel, InspectionPanel, RmTrackPanel } from "@/components/v5/intel/governance";
import { CovenantDesignerPanel, RenewalAutopilotPanel, WhoToCallPanel } from "@/components/v5/intel/ib";
import { ContagionPanel, EmployerPanel, EventTranslatorPanel } from "@/components/v5/intel/network";
import { EclBridgePanel, ExitsPanel, HeadroomPanel, RwaPanel, WorkoutPanel } from "@/components/v5/intel/portfolio";
import { type IntelMatch, type IntelPanelKey, intelHref, routeByKey } from "@/lib/v5/intel-intents";
import { PanelActions } from "@/components/v5/thread/panel-actions";
import { intelSources } from "@/lib/v5/thread-actions";

/** Demo deals offered when a deal-level question names none (the twins of the UAT). */
const DEMO_DEALS = ["R12-TWA", "R12-TWB", "DD-06"];

export function IntelPanel({ m, onDeal }: { m: IntelMatch; onDeal?: (deal: string) => void }) {
  const k: IntelPanelKey = m.route.key;
  if (m.missing === "deal") {
    return (
      <div className="flex flex-wrap items-center gap-2 text-[13px] text-text-secondary" data-testid="intel-needs-deal">
        <span>{m.route.label} works on one deal. Which one?</span>
        {DEMO_DEALS.map((d) => (
          <button key={d} type="button" onClick={() => onDeal?.(d)} data-testid={`intel-pick-${d}`}
                  className="rounded-full border border-border px-2.5 py-0.5 text-[12px] hover:border-accent hover:text-text-primary">{d}</button>))}
      </div>
    );
  }
  const deal = m.deal ?? "";
  switch (k) {
    case "fin-quality": return <FinQualityPanel proposalId={deal} />;
    case "challenger": return <CommitteeRehearsalPanel proposalId={deal} />;
    case "reverse": return <ReverseSolverPanel proposalId={deal} />;
    case "security": return <SecurityOptimiserPanel proposalId={deal} />;
    case "consistency": return <DecisionConsistencyPanel proposalId={deal || "book"} />;
    case "renewals": return <RenewalAutopilotPanel />;
    case "covenants": return <CovenantDesignerPanel proposalId={deal} />;
    case "calls": return <WhoToCallPanel />;
    case "event": return <EventTranslatorPanel initialText={m.question} autoRun />;
    case "contagion": return <ContagionPanel borrowerId={m.borrower ?? ""} />;
    case "employer": return <EmployerPanel employer={m.employer ?? ""} />;
    case "headroom": return <HeadroomPanel />;
    case "exits": return <ExitsPanel />;
    case "rwa": return <RwaPanel />;
    case "ecl-bridge": return <EclBridgePanel />;
    case "workout": return <WorkoutPanel borrowerId={m.borrower ?? ""} />;
    case "inspection": return <InspectionPanel initial={m.question} />;
    case "exceptions": return <ExceptionPanel />;
    case "rm-track": return <RmTrackPanel />;
    case "doa": return <DoaPanel />;
    case "frontier": return <NegotiationFrontierPanel proposalId={deal} />;
    case "premortem": return <DefaultPremortemPanel proposalId={deal} />;
    case "precedents": return <PrecedentExplorerPanel proposalId={deal} />;
    case "pricing": return <PricingBenchmarkPanel proposalId={deal} />;
    case "revenue-check": return <RevenueTruthPanel proposalId={deal} />;
    case "renewal-diff": return <RenewalDiffPanel proposalId={deal} />;
    case "group-contagion": return <GroupContagionPanel proposalId={deal} />;
  }
}

/** The answer card under Noor's Ask box: which engine answered, where it lives, and the panel itself. */
export function IntelAnswer({ m, onClose, onDeal }: { m: IntelMatch; onClose?: () => void; onDeal?: (deal: string) => void }) {
  return (
    <section className="rounded-xl border border-border bg-surface p-4 text-left" data-testid="intel-answer" data-intel={m.route.key}>
      <header className="mb-3 flex items-start gap-3">
        <div className="min-w-0">
          <p className="text-[10.5px] font-semibold uppercase tracking-[0.12em] text-text-muted">Answered by</p>
          <h3 className="text-[15px] font-semibold text-text-primary" data-testid="intel-answer-title">
            {m.route.label}{m.deal ? <span className="font-normal text-text-secondary"> · {m.deal}</span> : null}</h3>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <Link href={intelHref(m)} className="inline-flex items-center gap-1 text-[12px] text-accent hover:underline" data-testid="intel-answer-open"
                title={m.route.home}>Open in module <ArrowUpRight size={12} /></Link>
          {onClose ? (
            <button type="button" onClick={onClose} aria-label="Close" data-testid="intel-answer-close"
                    className="inline-flex size-7 items-center justify-center rounded-md text-text-muted hover:bg-surface-hover"><X size={14} /></button>) : null}
        </div>
      </header>
      <IntelPanel m={m} onDeal={onDeal} />
      {/* R16 t (M7): Share, Trace, Word and Add to report on the panel's answer */}
      <div className="mt-3 border-t border-border/60 pt-1.5">
        <PanelActions module="intel" id={`${m.route.key}${m.deal ? `:${m.deal}` : ""}${m.borrower ? `:${m.borrower}` : ""}`} title={`${m.route.label}${m.deal ? ` · ${m.deal}` : ""}`}
                      question={m.question || m.route.label} container='[data-testid="intel-answer"]' href={intelHref(m)} testId="intel-actions"
                      sources={intelSources({ route: { key: m.route.key, label: m.route.label, home: m.route.home }, deal: m.deal, borrower: m.borrower, employer: m.employer })} />
      </div>
    </section>
  );
}

/** A match for a panel key opened from a URL (`?intel=<key>&deal=…&borrower=…&q=…`). */
export function matchFromParams(sp: URLSearchParams, page: { dealId?: string | null } = {}): IntelMatch | null {
  const raw = sp.get("intel");
  if (!raw) return null;
  let route;
  try { route = routeByKey(raw as IntelPanelKey); } catch { return null; }
  if (!route) return null;
  const deal = sp.get("deal") ?? page.dealId ?? undefined;
  const m: IntelMatch = { route, question: sp.get("q") ?? "", deal: deal || undefined,
                          borrower: sp.get("borrower") ?? undefined, employer: sp.get("employer") ?? undefined };
  if (route.needs === "deal" && !m.deal) m.missing = "deal";
  return m;
}
