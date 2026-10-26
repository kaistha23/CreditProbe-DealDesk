"use client";

/**
 * PLAN_R10 D1/D6: opening a deal shows only the deal view (the step bar, four tiles, the step's analysis and
 * charts). The saved conversation does not open: it sits in "Recent threads" at the bottom, collapsed. A question
 * asked here starts a new thread under the view. The page is one panel: the view and the new thread scroll inside
 * it, and the input bar has its own space at the bottom, so nothing renders under it and long text wraps.
 *
 * Before R10: one deal at its own URL (/deal-desk/<proposal>), in the one thread frame (PLAN_R5 G4, docs/v5/THREAD_API.md):
 * the header, the stepper (1 Proposal, 2 Analysis, 3 Structure, 4 Recommendation), the KPI row and the step's
 * view, then the conversation scrolling in the middle; the composer is pinned at the bottom with the follow-up
 * chips and the primary actions (Optimise, Share, Add to report, Word report). Every answer shows the Cockpit's
 * process trace with its running timer while it works, and "Answered in …" once settled. Opened with
 * ?q=<question> from the home chat, it asks that question once.
 */

import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { Activity, ArrowLeft, FileText, GitBranch, Users } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { AssistantTurn, Composer, LiveTrace, MemoCards, ThreadActionsProvider, UserTurn, useThreadActions } from "@/components/v5/thread";
import { dealdeskSources } from "@/lib/v5/thread-actions";
import { newTraceId } from "@/lib/v5/thread";
import {
  type Analysis, type Bundle, type OptimizeResult, type Terms, type Turn, dealdesk, deskUrl,
} from "@/lib/v5/dealdesk";
import {
  type DealWorkflow, type View, LANDING_STEP, VIEW_LABEL, bannerLine, doneSet, parseStep, pathStates, r12Api, readVisited, stateTone,
  writeVisited,
} from "@/lib/v5/dealdesk-r12";

import { AnswerView } from "./answer";
import { Chip, PrimaryButton, SecondaryButton, Section, type StepKey, Stepper } from "./kit";
import { BackButton } from "@/components/v5/core/back-button";
import { DEFAULT_SETTINGS, type OptimiserSettings, OptimiserSettingsButton } from "./optimiser-settings";
import { DealBarActions, MoreMenu } from "./action-bar";
import { BusinessRequestStudio, isBusinessAsk } from "./business-request"; // R16 b: RM business request on the deal
import { StepIntel } from "./intel2"; // R14 i: the intelligence the plan places in this step
import { Slot, hasSlot } from "./r12-slots";
import { AccountBehaviour } from "./account-behaviour";
import { AnalysisStep, KpiRow, ProposalStep, RecommendationStep, ReviewStep, StressStep, StructureStep } from "./steps";
import { bestOffers } from "@/lib/v5/dealdesk-offer";
import { ConditionsTracker } from "./review-conditions";
import { MonitoringPlanPanel } from "./stress-lab-monitoring";
import { friendlyMessage } from "@/lib/v5/errors";
// R14 F (K20, K21, K23, K24, K25, K35): the structure set, Stress over structures, the Recommendation content, monitoring.
import { type StructureRow, type StructureSet, STRESS_DISABLED_REASON, flowApi, stressEnabled } from "@/lib/v5/dealdesk-flow";
import { PlainWords } from "@/components/v5/ui/plain-words";
import { StructureSetPanel } from "./flow-structure-set";
import { StressOverStructures } from "./stress-structures";
import { RecommendationPanel, SwotCard } from "./flow-recommendation";
import { ProposeMonitoringButton } from "./flow-monitoring";
import { PipelineLinesPanel } from "./pipeline-test";
import { CounterpartyLine, DealBorrower360 } from "./b360"; // Rounds B and G: Borrower 360 in the deal, counterparty exposure
import { isOpen as b360IsOpen } from "@/lib/v5/dealdesk-b360";

/** R13 X: the Review step's two views, R11's workspace first. */
function ReviewSwitch({ value, onChange }: { value: "workspace" | "points"; onChange: (v: "workspace" | "points") => void }) {
  return (
    <div className="inline-flex rounded-md border border-border p-0.5" role="tablist" aria-label="Review" data-testid="dealdesk-review-switch">
      {([["workspace", "Review workspace"], ["points", "12-point review"]] as const).map(([k, label]) => (
        <button key={k} type="button" role="tab" aria-selected={value === k} onClick={() => onChange(k)} data-testid={`dealdesk-review-${k}`}
                className={cn("h-7 rounded px-3 text-[12px]", value === k ? "bg-accent font-medium text-accent-contrast" : "text-text-secondary hover:bg-surface-hover")}>
          {label}</button>))}
    </div>
  );
}

/** PLAN_R11 U3: the thread answer's `action` that opens a step (stress and review intents). */
const R11_ACTION_STEP: Record<string, StepKey> = { stress_lab: "stress", review: "review", committee_sheet: "review" };

export function DealThread({ proposalId }: { proposalId: string }) {
  const router = useRouter();
  const params = useSearchParams();
  const [b, setB] = React.useState<Bundle | null>(null);
  const [opt, setOpt] = React.useState<OptimizeResult | null>(null);
  const [current, setCurrent] = React.useState<Analysis | null>(null);
  // R10 D1: `history` is the saved conversation (Recent threads, collapsed); `turns` is the new thread asked here.
  const [history, setHistory] = React.useState<Turn[]>([]);
  const [turns, setTurns] = React.useState<Turn[]>([]);
  const [historyOpen, setHistoryOpen] = React.useState(false);
  const scroller = React.useRef<HTMLDivElement | null>(null);
  // PLAN_R12 I1: every deal opens on Proposal (R7 opened on Analysis). The step is in the URL (?step=, Proposal when
  // absent) and each step change is a history entry, so the browser's Back and the Back button walk the steps exactly.
  const urlStep = params.get("step");
  const step: StepKey = parseStep(urlStep);
  // Round B: the deal's Borrower 360 panel (?b360=1), opened from the header or the counterparty line.
  const b360Open = b360IsOpen(params.get("b360"));
  const setB360 = React.useCallback((open: boolean) => {
    const q = new URLSearchParams(window.location.search);
    if (open) q.set("b360", "1"); else q.delete("b360");
    window.history.pushState(null, "", `${window.location.pathname}${q.size ? `?${q}` : ""}`);
  }, []);
  // PLAN_R12 O2: the steps visited on this deal (this browser); a tick is "visited and done", never "computed".
  const [visited, setVisited] = React.useState<Set<string>>(() => new Set([step]));
  // PLAN_R12 I17, I21: the workflow state, the role view and, for a pipeline deal, the optimiser's decision.
  const [wf, setWf] = React.useState<DealWorkflow | null>(null);
  const [wfBusy, setWfBusy] = React.useState(false);
  const fromPipeline = params.get("from") === "pipeline";
  const [added, setAdded] = React.useState(0);
  const [draft, setDraft] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [pending, setPending] = React.useState("");
  // R16 t (M7): Share, Trace, Word, Add to report on every answer; "write a memo" writes the Word document.
  const ta = useThreadActions({ module: "dealdesk", threadId: proposalId, title: b ? `${b.proposal.obligor.name} · ${proposalId}` : proposalId,
                                href: `/deal-desk/${encodeURIComponent(proposalId)}`, busy });
  const askRef = React.useRef<(q: string) => unknown>(() => undefined);
  const [traceId, setTraceId] = React.useState("");
  const [error, setError] = React.useState("");
  const [notice, setNotice] = React.useState("");
  const [settings, setSettings] = React.useState<OptimiserSettings>(DEFAULT_SETTINGS);
  // PLAN_R11 U2: the structure picked in Optimise (default the recommended one), for Stress and Test against pipeline.
  const [picked, setPicked] = React.useState<Terms | null>(null);
  // R13 X: the Review step opens on the R11 workspace (the Prepare view on B's pre-flight); the 12-point review is a click away.
  const [reviewMode, setReviewMode] = React.useState<"workspace" | "points" | null>(null);
  const asked = React.useRef(false);
  // R14 F: the structure set (selection = the input to Stress and Recommendation) and a nonce to reload what reads it.
  const [flowSet, setFlowSet] = React.useState<StructureSet | null>(null);
  const [flowNonce, setFlowNonce] = React.useState(0);
  // The R12 Stress Lab and the R11 term sheet sit in closed sections and render (and compute) only when opened.
  const [fullLab, setFullLab] = React.useState(false);
  const [recSheet, setRecSheet] = React.useState(false);

  const go = React.useCallback((s: StepKey) => {
    const q = new URLSearchParams(window.location.search);
    q.delete("q");
    if (s === LANDING_STEP) q.delete("step"); else q.set("step", s);
    const url = `${window.location.pathname}${q.size ? `?${q}` : ""}`;
    if (url !== window.location.pathname + window.location.search) window.history.pushState(null, "", url);
  }, []);

  const reload = React.useCallback(async () => {
    const x = await dealdesk.bundle(proposalId);
    setB(x);
    setCurrent(x.current);
    return x;
  }, [proposalId]);

  React.useEffect(() => {
    let live = true;
    void Promise.resolve().then(() => Promise.all([reload(), dealdesk.thread(proposalId)])).then(([x, th]) => {
      if (!live) return;
      setHistory(th.turns);
      if (x.state.optimisation) void dealdesk.optimize(proposalId, x.state.optimise_request ?? {}).then((o) => { if (live) setOpt(o); });
    }).catch((e) => { if (live) setError(friendlyMessage(e)); });
    return () => { live = false; };
  }, [proposalId, reload, go]);

  // R14 F: Stress and Recommendation read the structure set even when Structure was not opened in this visit.
  React.useEffect(() => {
    if (flowSet || (step !== "stress" && step !== "recommendation")) return;
    let live = true;
    void flowApi.structureSet(proposalId).then((x) => { if (live) setFlowSet(x); }).catch(() => null);
    return () => { live = false; };
  }, [proposalId, step, flowSet]);

  // R14 F: the four tiles follow the selected structure on Structure, Stress and Recommendation (one structure on screen).
  const [selAnalysis, setSelAnalysis] = React.useState<{ key: string; a: Analysis } | null>(null);
  const selKey = flowSet ? `${flowSet.selected}|${JSON.stringify(flowSet.rows.find((r) => r.key === flowSet.selected)?.terms ?? null)}` : "";
  React.useEffect(() => {
    if (!flowSet) return;
    const row = flowSet.rows.find((r) => r.key === flowSet.selected);
    if (!row) return;
    let live = true;
    void dealdesk.compute(proposalId, row.terms as unknown as Terms).then((a) => { if (live) setSelAnalysis({ key: selKey, a }); }).catch(() => null);
    return () => { live = false; };
  }, [proposalId, flowSet, selKey]);

  // O2: the visited steps are remembered per deal; the step on screen is visited.
  React.useEffect(() => {
    let live = true;
    void Promise.resolve().then(() => {
      if (!live) return;
      setVisited((v) => {
        const next = new Set([...readVisited(proposalId), ...v, step]);
        writeVisited(proposalId, next);
        return next;
      });
    });
    return () => { live = false; };
  }, [proposalId, step]);

  // The workflow first without the banner (fast), then with it (the pipeline decision may need a solve).
  React.useEffect(() => {
    let live = true;
    void r12Api.workflow(proposalId, false).then((w) => {
      if (!live) return;
      setWf(w);
      if (w.banner.in_pipeline) void r12Api.workflow(proposalId, true).then((x) => { if (live) setWf(x); }).catch(() => null);
    }).catch(() => null);
    return () => { live = false; };
  }, [proposalId]);

  const move = async (to: string) => {
    setWfBusy(true);
    try {
      const w = await r12Api.move(proposalId, to);
      setWf((old) => ({ ...w, banner: old?.banner ?? w.banner }));
      setNotice(`${w.label}. The handover is logged.`);
    } catch (e) {
      setNotice(friendlyMessage(e));
    } finally {
      setWfBusy(false);
    }
  };

  const optimise = React.useCallback(async () => {
    setBusy(true);
    setPending("Optimise");
    const tid = newTraceId();
    setTraceId(tid);
    try {
      const r = await dealdesk.optimiseTurn(proposalId, settings, tid);
      const o = r.optimisation;
      setOpt(o);
      // The Optimise view is the answer (D4); its turn is kept with the saved threads, not repeated under the view.
      setHistory((t) => [...t, r.turn]);
      if (o.closest) setCurrent(await dealdesk.compute(proposalId, o.closest.terms));
      go("structure");
      window.requestAnimationFrame(() => scroller.current?.scrollTo({ top: 0, behavior: "smooth" }));
    } catch (e) {
      setNotice(friendlyMessage(e));
    } finally {
      setBusy(false);
      setPending("");
    }
  }, [proposalId, go, settings]);

  const [brOpen, setBrOpen] = React.useState<{ ask: string } | null>(null); // R16 b
  const ask = React.useCallback(async (text: string) => {
    const q = text.trim();
    if (!q || busy) return;
    // R16 b: on a customer-file deal (R16-…) an RM's ask, and on any deal "write the business request", opens the business request
    if (/\bbusiness request\b/i.test(q) || (proposalId.startsWith("R16-") && isBusinessAsk(q))) {
      setDraft("");
      setBrOpen({ ask: /\bbusiness request\b/i.test(q) && !isBusinessAsk(q.replace(/business request/ig, "")) ? "" : q });
      return;
    }
    if (ta.intercept(q, (x) => askRef.current(x))) { setDraft(""); return; }
    setBusy(true);
    setPending(q);
    setDraft("");
    const tid = newTraceId();
    setTraceId(tid);
    try {
      const r = await dealdesk.ask(proposalId, q, tid);
      setTurns((t) => [...t, { turn_id: r.turn_id, question: q, owner: "", created: Date.now() / 1000, answer: r.answer }]);
      setAdded((n) => n + 1);
      if (r.answer.action === "optimise") {
        const o = await dealdesk.optimize(proposalId, (r.answer as unknown as { optimise_request?: object }).optimise_request ?? {});
        setOpt(o);
        go("structure");
      }
      // PLAN_R11 U3: a stress or review answer opens its step under the thread; the answer stays in the thread.
      const step = R11_ACTION_STEP[String(r.answer.action ?? "")];
      if (step) go(step);
    } catch (e) {
      setNotice(friendlyMessage(e));
    } finally {
      setBusy(false);
      setPending("");
    }
  }, [busy, proposalId, go, ta]);
  React.useEffect(() => { askRef.current = ask; }, [ask]);

  // Recent analyses link back here: ?turn=<id> scrolls to that turn; ?analysis=<id> loads the saved structure.
  const linked = React.useRef(false);
  React.useEffect(() => {
    if (!b || linked.current) return;
    const turn = params.get("turn");
    const aid = params.get("analysis");
    if (!turn && !aid) return;
    linked.current = true;
    if (turn) {
      setHistoryOpen(true);
      window.setTimeout(() => document.getElementById(`turn-${turn}`)?.scrollIntoView({ behavior: "smooth", block: "start" }), 400);
    }
    if (aid) {
      void dealdesk.analysis(aid).then(async (a) => {
        setCurrent(await dealdesk.compute(proposalId, a.terms));
        setNotice(`Saved analysis “${a.name}” loaded in the term panel.`);
        go(opt ? "structure" : "analysis");
      }).catch(() => null);
    }
  }, [b, params, proposalId, go, opt]);

  React.useEffect(() => {
    const q = params.get("q");
    if (q && b && !asked.current) {
      asked.current = true;
      // Drop only ?q= (the question is asked once); the step and the return context stay.
      const rest = new URLSearchParams(params.toString());
      rest.delete("q");
      router.replace(`/deal-desk/${encodeURIComponent(proposalId)}${rest.size ? `?${rest}` : ""}`);
      void Promise.resolve().then(() => ask(q));
    }
  }, [params, b, proposalId, router, ask]);

  // The panel follows a new question to its answer; Optimise instead shows its view from the top (D4). Nothing scrolls on load.
  React.useEffect(() => {
    if (!added && !pending) return;
    if (pending === "Optimise") return;
    const el = scroller.current?.querySelector('[data-testid="dealdesk-thread-end"]');
    el?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [added, pending]);

  const recommend = async (t: Terms) => {
    setBusy(true);
    try {
      await dealdesk.setState(proposalId, { terms: t, recommended: t });
      await dealdesk.setStatus(proposalId, "counter_offered").catch(() => null);
      await reload();
      go("recommendation");
    } finally {
      setBusy(false);
    }
  };

  /** R14 F (K25): Recommend from the sticky bar: the selected structure becomes the recommendation. */
  const recommendRow = async (r: StructureRow) => {
    await recommend(r.terms as unknown as Terms);
    setFlowNonce((n) => n + 1);
  };
  const saveStructure = async (t: Terms) => {
    const name = window.prompt("Name for your structure", "My structure");
    if (name === null) return;
    try {
      const s2 = await flowApi.save(proposalId, name || "My structure", t as unknown as Record<string, unknown>, true);
      setFlowSet(s2);
      setFlowNonce((n) => n + 1);
      setNotice(`Saved to Your structures as “${name || "My structure"}” and selected.`);
    } catch (e) { setNotice(friendlyMessage(e)); }
  };

  const save = async () => {
    if (!b) return;
    const name = window.prompt("Name for the saved analysis", `${b.proposal.obligor.name} · ${b.proposal.proposal_id}`);
    if (name === null) return;
    try {
      const s = await dealdesk.save(proposalId, name || b.proposal.obligor.name);
      setNotice(`Saved as “${s.name}”.`);
    } catch (e) { setNotice(friendlyMessage(e)); }
  };

  if (error) {
    return (
      <div className="space-y-3">
        <BackButton fallback={{ href: "/deal-desk", label: "Deal Desk" }} testId="dealdesk-back" />
        <p className="text-sm text-negative" role="alert">{error}</p>
      </div>);
  }
  if (!b || !current) return <Skeleton className="h-96 w-full" />;
  const p = b.proposal;
  const rec = b.state.recommended ? b.current : null;
  const done = doneSet(visited, { hasOpt: Boolean(opt), hasRec: Boolean(rec) });
  const reviewModeNow: "workspace" | "points" = reviewMode ?? (wf?.view === "prepare" ? "points" : "workspace");
  const view: View = wf?.view ?? "review";
  const banner = wf?.banner;
  const showBanner = Boolean(banner?.in_pipeline && (banner.source === "pipeline" || fromPipeline));
  const stressTerms = picked ?? (rec ? rec.terms : null) ?? bestOffers(opt)[0]?.solution.terms ?? p.ask;
  const recTerms = bestOffers(opt)[0]?.solution.terms ?? null;
  const stressLabel = picked && JSON.stringify(picked) !== JSON.stringify(rec?.terms ?? recTerms) ? "Picked"
    : rec || recTerms ? "Recommended" : "Asked";
  const settingsButton = <OptimiserSettingsButton terms={current.terms} value={settings} onChange={setSettings} />;
  const canStress = stressEnabled(step, visited);
  const selectedRow = flowSet?.rows.find((r) => r.key === flowSet.selected) ?? null;

  const last = turns[turns.length - 1];
  const chips = busy ? [] : (last?.answer.suggestions ?? [{ label: "Why does the ask fail?", send: "Why does the ask fail?" },
                                                        { label: "What are my options?", send: "What are my options? Which levers clear alone?" }]).slice(0, 3);
  const header = (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <BackButton fallback={{ href: "/deal-desk", label: "Deal Desk" }} testId="dealdesk-back" />
        <div className="min-w-0 flex-1">
          <h1 className="truncate text-[20px] font-semibold text-text-primary" data-testid="dealdesk-title">{p.obligor.name}</h1>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <Chip>{p.proposal_id}</Chip><Chip>{p.obligor.sector}</Chip><Chip>{p.obligor.internal_rating}</Chip>
            <Chip>{p.obligor.existing ? "Existing borrower" : "New to bank"}</Chip>
            {wf ? <Chip tone={stateTone(wf.state)} testId="dealdesk-workflow-state" title={`Workflow: ${wf.label}`}>{wf.label}</Chip> : null}
          </div>
        </div>
        {/* R13 X (J10): the workflow's handovers and the More menu in the header; the R11 page below. */}
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          {wf ? <span className="text-[11px] text-text-muted" data-testid="dealdesk-view">{VIEW_LABEL[view]} view</span> : null}
          {wf ? (
            <div className="flex flex-wrap items-center gap-2" data-testid="dealdesk-workflow" data-state={wf.state} data-view={view}
                 title={`Workflow: ${pathStates(wf.states, wf.state).map((s) => s.label).join(" › ")}`}>
              {wf.actions.map((a) => (
                <SecondaryButton key={a.to} onClick={() => void move(a.to)} disabled={wfBusy} data-testid={`dealdesk-move-${a.to}`}>{a.label}</SecondaryButton>))}
              {wf.history.length ? (
                <details className="relative" data-testid="dealdesk-handover-log">
                  <summary className="cursor-pointer list-none text-[12px] text-accent hover:underline">Handover log ({wf.history.length})</summary>
                  <ul className="absolute right-0 z-20 mt-1 w-[340px] space-y-1 rounded-lg border border-border bg-surface p-3 text-[12px] shadow-lg">
                    {wf.history.slice().reverse().map((e) => (
                      <li key={e.event_id} className="break-words"><span className="text-text-primary">{e.from_label} → {e.to_label}</span>
                        <span className="block text-[11px] text-text-muted">{e.actor || "–"}{e.role_label ? ` (${e.role_label})` : ""} · {e.at.slice(0, 16).replace("T", " ")}{e.note ? ` · ${e.note}` : ""}</span></li>))}
                  </ul>
                </details>) : null}
            </div>) : null}
          {/* R14 F (K23): Stress is a header button from Structure on, over the structures you choose. */}
          <SecondaryButton onClick={() => go("stress")} disabled={!canStress} data-testid="dealdesk-stress-button" data-tour="dd-stress" aria-pressed={step === "stress"}
                           title={canStress ? "Stress the structures you choose: mild, moderate, severe" : STRESS_DISABLED_REASON}
                           className={step === "stress" ? "border-accent bg-accent-muted text-accent" : undefined}>
            <Activity size={13} /> Stress</SecondaryButton>
          <ProposeMonitoringButton subject={{ proposalId: p.proposal_id, obligorId: p.obligor.obligor_id, obligorName: p.obligor.name, source: "deal" }}
                                   testId="dealdesk-propose-monitoring" />
          {/* R16 b: the RM business request in the bank form, from this deal's file and the Bank's data */}
          <SecondaryButton onClick={() => setBrOpen({ ask: "" })} data-testid="dealdesk-deal-business-request" title="Write the business request (bank form) from the ask and your notes">
            <FileText size={13} /> Business request</SecondaryButton>
          <SecondaryButton onClick={() => setB360(!b360Open)} data-testid="dealdesk-b360-button" aria-pressed={b360Open}
                           title="What the Bank holds on this borrower and what the uploads taught, with counterparty exposure"
                           className={b360Open ? "border-accent bg-accent-muted text-accent" : undefined}>
            <Users size={13} /> Borrower 360</SecondaryButton>
          <MoreMenu proposal={p} view={view} terms={rec?.terms ?? recTerms ?? null} />
        </div>
        {brOpen ? <BusinessRequestStudio initialCustomer={p.proposal_id} initialAsk={brOpen.ask || undefined} onClose={() => setBrOpen(null)} /> : null}
      </div>
      {/* PLAN_R12 I21: a pipeline deal opens here in full, with the optimiser's decision and the way back. */}
      {showBanner && banner ? (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-accent/40 bg-accent-muted px-3 py-2 text-[12px]" data-testid="dealdesk-pipeline-banner">
          <GitBranch size={14} className="shrink-0 text-accent" aria-hidden />
          <span className="font-semibold text-text-primary">Pipeline</span>
          {banner.decision ? (
            <>
              <Chip tone={banner.decision.decision === "approve" ? "positive" : "negative"} testId="dealdesk-pipeline-banner-decision">{bannerLine(banner)}</Chip>
              <span className="min-w-0 flex-1 break-words text-text-secondary" data-testid="dealdesk-pipeline-banner-reason">{banner.decision.reason}</span>
            </>
          ) : <span className="min-w-0 flex-1 text-text-muted">The optimiser&apos;s decision on this deal is being worked out.</span>}
          <SecondaryButton onClick={() => router.push(banner.back_href)} data-testid="dealdesk-back-to-pipeline"><ArrowLeft size={13} /> Back to pipeline</SecondaryButton>
        </div>) : null}
      <Stepper step={step} done={done} onStep={go} />
      {b360Open ? <DealBorrower360 proposalId={p.proposal_id} onClose={() => setB360(false)} />
        : <CounterpartyLine proposalId={p.proposal_id} onOpen={() => setB360(true)} />}
      <KpiRow ask={b.ask} rec={(selAnalysis?.key === selKey && (step === "structure" || step === "stress" || step === "recommendation") ? selAnalysis.a : null)
                               ?? rec ?? ((step === "structure" || step === "stress") && opt ? current : null)} />

      <StepIntel step={step} proposalId={p.proposal_id} />
      {step === "proposal" ? <ProposalStep p={p} full={b.proposal_full} onNext={() => go("proposal-check")} /> : null}
      {/* PLAN_R14 (K31): the Proposal check step; Session p's component fills the slot. */}
      {step === "proposal-check" ? (
        <div className="space-y-4" data-testid="dealdesk-step-proposal-check-view">
          {hasSlot("ProposalCheck") ? <Slot name="ProposalCheck" props={{ proposalId: p.proposal_id, onNext: () => go("review") }} /> : (<>
            <PlainWords testId="dealdesk-proposal-check-plain-words" lines={[
              "This step checks the quality of the RM's paper before the deal itself is judged: completeness, accuracy against the bank's data, consistency and disclosure.",
              "It scores each of the 20 sections of the proposal and lists the queries to send back to the RM.",
              "The checker for this deal is not installed on this build; go on to Review."]} />
            <PrimaryButton onClick={() => go("review")} data-testid="dealdesk-proposal-check-next">Review the deal</PrimaryButton></>)}
        </div>) : null}
      {step === "proposal" ? <Slot name="Product" props={{ proposalId: p.proposal_id }} /> : null}
      {step === "analysis" ? <AnalysisStep b={b} onOptimise={() => void optimise()} busy={busy} onAsk={() => go("proposal")}
                                           settings={<OptimiserSettingsButton terms={current.terms} value={settings} onChange={setSettings} testId="dealdesk-card-optimiser" />}
                                           onRecommendation={rec ? () => go("recommendation") : undefined} /> : null}
      {step === "analysis" ? <AccountBehaviour proposalId={p.proposal_id} /> : null}
      {step === "analysis" ? <SwotCard proposalId={p.proposal_id} /> : null}
      {/* R14 F (K23, K25): the structure set first: one Select per row and the sticky "Selected: … → Recommend" bar. */}
      {step === "structure" ? <StructureSetPanel proposalId={p.proposal_id} nonce={flowNonce} onChange={setFlowSet} onRecommend={(r) => void recommendRow(r)} busy={busy} /> : null}
      {/* R14 F (K21): Test against pipeline on the selected structure, also before any Optimise run (with one it sits under the structures). */}
      {step === "structure" && !opt && selectedRow ? (
        <Section title="Test against pipeline" testId="dealdesk-panel-pipeline">
          <PipelineLinesPanel proposalId={p.proposal_id} structureKey={selectedRow.key} structureLabel={selectedRow.label} />
        </Section>) : null}
      {step === "structure" ? <StructureStep key={opt?.trace_id ?? "none"} b={b} opt={opt} current={current} onCurrent={setCurrent} settings={settingsButton}
                                             onRecommend={(t) => void recommend(t)} onOptimise={() => void optimise()} busy={busy}
                                             onPick={setPicked} onStress={() => go("stress")}
                                             structureKey={selectedRow?.key ?? null} structureLabel={selectedRow?.label}
                                             onSave={(t) => void saveStructure(t)} /> : null}
      {/* R14 F (K20, K23): Stress over the chosen structures; the R12 Stress Lab on the selected structure stays one click below. */}
      {step === "stress" ? (
        <StressOverStructures proposalId={p.proposal_id} set={flowSet} onSetChange={(s2) => { setFlowSet(s2); setFlowNonce((n) => n + 1); }}
          below={(
            <details className="rounded-lg border border-border bg-surface" data-testid="flow-full-stress-lab" open={fullLab}
                     onToggle={(e) => setFullLab((e.target as HTMLDetailsElement).open)}>
              <summary className="cursor-pointer px-4 py-2.5 text-[13px] font-medium text-text-secondary">
                Full Stress Lab on {selectedRow?.label ?? stressLabel}: the ladder by family, the transmission chain, your own scenarios and the monitoring tier</summary>
              {fullLab ? <div className="p-4 pt-0">
                <StressStep b={b} terms={(selectedRow?.terms as unknown as Terms | undefined) ?? stressTerms} recommendedTerms={rec?.terms ?? recTerms}
                            label={selectedRow?.label ?? stressLabel} />
              </div> : null}
            </details>)} />) : null}
      {/* R13 X (J10): the R11 review workspace first; the 12-point review (B) one click away; Group & SWOT are in More. */}
      {step === "review" ? <ReviewSwitch value={reviewModeNow} onChange={setReviewMode} /> : null}
      {step === "review" && reviewModeNow === "points" ? <Slot name="Review" props={{ proposalId: p.proposal_id, view }} /> : null}
      {step === "review" && reviewModeNow === "workspace" ? <ReviewStep b={b} view={view} /> : null}
      {/* R14 F (K24): the Recommendation is never blank: built on the selected structure (default the Review counter-proposal). */}
      {step === "recommendation" ? <RecommendationPanel proposalId={p.proposal_id} nonce={flowNonce} onChoose={() => go("structure")} /> : null}
      {step === "recommendation" && rec ? (
        <details className="rounded-lg border border-border bg-surface" data-testid="flow-rec-term-sheet" open={recSheet}
                 onToggle={(e) => setRecSheet((e.target as HTMLDetailsElement).open)}>
          <summary className="cursor-pointer px-4 py-2.5 text-[13px] font-medium text-text-secondary">Term sheet against the ask, the risk opinion and the R11 stress table</summary>
          {recSheet ? <div className="p-4 pt-0"><RecommendationStep b={b} rec={rec} busy={busy} onSave={() => void save()}
                                                         onDraft={() => void ask("Draft the credit risk opinion, conditions precedent and covenants")} /></div> : null}
        </details>) : null}
      {/* PLAN_R11 R4: the deal's conditions precedent, covenants and watch items, tracked against data, under the recommendation. */}
      {step === "recommendation" && rec ? <ConditionsTracker dealId={p.proposal_id} title="Conditions and triggers" /> : null}
      {/* PLAN_R12 §1.5 (Session D, mounted by U): the monitoring tier set at approval, from the stress verdict; credit approves it. */}
      {step === "recommendation" && rec ? <MonitoringPlanPanel proposalId={p.proposal_id} terms={rec.terms}
                                                               canApprove={Boolean(wf && (wf.side === "credit" || wf.side === "admin"))} /> : null}
    </div>
  );

  const turnView = (t: Turn, i: number, base = 1000) => (
    <div key={t.turn_id} className="min-w-0 space-y-3" data-testid="dealdesk-turn" id={`turn-${t.turn_id}`}>
      <UserTurn text={t.question} />
      <AssistantTurn trace={t.answer.trace ?? null}
                     actions={{ index: base + i, question: t.question, answerId: t.turn_id, sources: dealdeskSources(t.answer, proposalId) }}>
        <AnswerView answer={t.answer} onAsk={(x) => void ask(x)} busy={busy} chips={false} />
      </AssistantTurn>
    </div>);

  return (
    <div data-testid="dealdesk-thread" data-proposal={p.proposal_id}
         className="flex h-[calc(100dvh-7.75rem)] min-h-[520px] min-w-0 flex-col">
      {/* D6: the view and the new thread scroll inside the panel; the input bar below has its own space. */}
      <div ref={scroller} className="min-h-0 min-w-0 flex-1 overflow-y-auto overflow-x-hidden pb-4 pr-1" data-testid="dealdesk-thread-shell">
        <ThreadActionsProvider value={ta}>
        {header}
        {notice ? <p className="mt-3 rounded-md border border-border bg-surface px-3 py-2 text-[12px] break-words" data-testid="dealdesk-notice">{notice}</p> : null}
        <div className="mt-5 min-w-0 space-y-5 break-words [overflow-wrap:anywhere]" data-testid="dealdesk-conversation" data-new-thread={turns.length || undefined}>
          {turns.length || pending ? <p className="text-[11px] font-medium uppercase tracking-[0.08em] text-text-muted">New thread</p> : null}
          {turns.map((t, i) => turnView(t, i))}
          <MemoCards api={ta} />
          {pending ? (
            <div className="space-y-3" data-testid="dealdesk-live-turn">
              <UserTurn text={pending} />
              <div aria-live="polite" data-testid="dealdesk-working"><LiveTrace base={deskUrl("")} traceId={traceId} /></div>
            </div>) : null}
          <div data-testid="dealdesk-thread-end" />
        </div>
        {history.length ? (
          <details className="mt-5 rounded-lg border border-border bg-surface" data-testid="dealdesk-recent-threads" open={historyOpen}
                   onToggle={(e) => setHistoryOpen((e.target as HTMLDetailsElement).open)}>
            <summary className="cursor-pointer px-4 py-2.5 text-[13px] font-medium text-text-secondary">
              Recent threads on this deal <span className="text-text-muted">({history.length} {history.length === 1 ? "question" : "questions"})</span></summary>
            {historyOpen ? (
              <div className="min-w-0 space-y-5 break-words px-4 pb-4 [overflow-wrap:anywhere]" data-testid="dealdesk-recent-turns">
                {history.map((t, i) => turnView(t, i, 0))}
              </div>) : null}
          </details>) : null}
        </ThreadActionsProvider>
      </div>
      <div className="shrink-0 border-t border-border bg-surface px-1 pt-3 pb-1" data-testid="thread-composer">
        <Composer value={draft} onChange={setDraft} onSubmit={(v) => void ask(v)} busy={busy} chips={chips} onChip={(c) => void ask(c.send)}
                  placeholder="Ask about this deal, e.g. “what are my options?”"
                  testId="dealdesk" inputTestId="dealdesk-composer" sendTestId="dealdesk-send"
                  actions={<DealBarActions proposal={p} hasRecommendation={Boolean(rec)} busy={busy} optimising={busy && pending === "Optimise"}
                                           onOptimise={() => void optimise()} onNotice={setNotice} />} />
      </div>
    </div>
  );
}
