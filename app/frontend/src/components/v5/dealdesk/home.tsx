"use client";

/**
 * PLAN_R12 §1.1 (Session U, I30): the Ask Deal Desk box at the top, the six work-queue cards under it, then the tabs
 * Origination (the R11 Single deal | Pipeline toggle, unchanged), Book (Session I) and Parameters & policy (Session G).
 * The header buttons Portfolio RAROC and Proposal review moved into the Book and Origination tabs.
 *
 * Before R12: the Deal Desk home (DEAL_DESK_PROMPT section 4): the What-If pattern. A chat
 * box at the top (the Deal Desk conversation, scoped to the Deal Desk domain
 * and read-only portfolio headroom), and below it the proposal pipeline with
 * its statuses and filters, the New proposal entry (form or memo), and Recent
 * analyses with "Continue where you left off" (PLAN_R5 D3).
 * Asking opens a thread (PLAN_R5 G4, screen 13). R14 n (K16): every question
 * opens a NEW thread at /deal-desk/thread/<id> (title from the question, top of
 * Recent work); the fixed `thread=desk` is gone. A question naming a proposal
 * opens that proposal's page with the question.
 */

import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";

import { findNamedDeal, searchDeals } from "@/lib/v5/deal-search"; // R14 U (K17)

import { backOr } from "@/lib/v5/back";
import { ArrowLeft, ArrowRight, Eye, FileText, Plus, Search, SlidersHorizontal, TrendingDown } from "lucide-react";


import { InfoPopover } from "./explain";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import {
  type ProposalSummary, type RecentRow, type Status, FACILITY, RATINGS, STATUSES, STATUS_LABEL, STRUCTURE, dealdesk, dealdeskOrigin,
  money, rate, useLoad,
} from "@/lib/v5/dealdesk";

import { Chip, PrimaryButton, Section, SecondaryButton, tableCls, tdCls, thCls } from "./kit";
import { GovernanceTools } from "@/components/v5/intel/governance";
import { NewProposal } from "./new-proposal";
import { PipelineMode } from "./pipeline-view";
import { ConditionsDueLine } from "./review-conditions";
import { TABS, type TabKey, parseTab } from "@/lib/v5/dealdesk-r12";
import { LandingCards } from "./landing-cards";
import { TryDocsEntry } from "./try-docs";
import { Slot, hasSlot } from "./r12-slots";
import { MonitoringPage } from "./flow-monitoring"; // R14 F (K35)
import { ModuleLanding } from "@/components/v5/landing/module-landing";
import { openDeskThread } from "./desk-thread";
import { BusinessRequestStudio, customerIn, isBusinessAsk, stripCustomer } from "./business-request"; // R16 b: RM business request
import { getJson } from "./papers/paper-view";
import { IntelligenceStudioLink } from "./intelligence-studio"; // Round S
import { usePaperRows } from "./paperws/open"; // Round W: papers in Recent work

export const STATUS_TONE: Record<Status, "neutral" | "accent" | "warning" | "positive" | "negative"> = {
  new: "neutral", in_review: "accent", counter_offered: "warning", approved: "positive", declined: "negative",
};
const SIZES = [
  { key: "", label: "Any size" }, { key: "s", label: "Up to 100m", lo: 0, hi: 100 },
  { key: "m", label: "100m to 500m", lo: 100, hi: 500 }, { key: "l", label: "Over 500m", lo: 500, hi: Infinity },
];

function Select({ value, onChange, label, children, testId }: {
  value: string; onChange: (v: string) => void; label: string; children: React.ReactNode; testId: string;
}) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} aria-label={label} data-testid={testId}
            className="h-8 rounded-md border border-border bg-surface px-2 text-[12px] text-text-secondary">{children}</select>
  );
}

function when(t: number): string {
  const d = new Date(t * 1000);
  return d.toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

/** D3: every saved or optimised analysis, newest first, with a link back to its thread; and the continue row. */
function RecentAnalyses({ version, onOpen }: { version: number; onOpen: (href: string) => void }) {
  const r = useLoad(() => dealdesk.recent(20), `recent-${version}`);
  const c = r.data?.continue;
  const rows = r.data?.recent ?? [];
  return (
    <Section title="Recent analyses" testId="dealdesk-recent"
             info="Every saved or optimised analysis with its time, user, proposal, outcome and RAROC. Open goes back to its thread.">
      {c ? (
        <button type="button" onClick={() => onOpen(c.href)} data-testid="dealdesk-continue"
                className="mb-3 flex w-full items-center gap-3 rounded-lg border border-accent/40 bg-accent-muted px-4 py-3 text-left hover:border-accent">
          <div className="min-w-0 flex-1">
            <p className="text-[11px] font-medium uppercase tracking-[0.08em] text-accent">Continue where you left off</p>
            <p className="truncate text-[13px] font-semibold text-text-primary">{c.proposal_id === "desk" ? (c.title || "Deal Desk thread") : `${c.proposal_id} · ${c.obligor}`}</p>
            <p className="truncate text-[12px] text-text-secondary">“{c.question}” · {when(c.time)} · {c.turns} turn{c.turns === 1 ? "" : "s"}</p>
          </div>
          <ArrowRight size={16} className="text-accent" />
        </button>) : null}
      {r.error ? <p className="text-[12px] text-negative" role="alert">{r.error}</p> : null}
      {!r.data && !r.error ? <Skeleton className="h-24 w-full" /> : null}
      {r.data && !rows.length ? <p className="text-[12px] text-text-muted" data-testid="dealdesk-recent-empty">No analysis saved or optimised yet.</p> : null}
      {rows.length ? (
        <div className="overflow-auto">
          <table className={tableCls} data-testid="dealdesk-recent-table">
            <thead><tr><th className={thCls}>Time</th><th className={thCls}>User</th><th className={thCls}>Proposal</th><th className={thCls}>Analysis</th>
              <th className={thCls}>Outcome</th><th className={cn(thCls, "text-right")}>Lifetime RAROC</th><th className={thCls}>Approval</th><th className={thCls} /></tr></thead>
            <tbody>{rows.map((x: RecentRow) => (
              <tr key={`${x.kind}-${x.id}`} data-testid={`dealdesk-recent-${x.id}`} className="hover:bg-surface-hover">
                <td className={cn(tdCls, "whitespace-nowrap")}>{when(x.time)}</td>
                <td className={tdCls}>{x.user || "–"}</td>
                <td className={tdCls}><span className="font-medium text-accent">{x.proposal_id}</span> · {x.obligor}</td>
                <td className={tdCls}><Chip tone={x.kind === "saved" ? "accent" : "neutral"}>{x.kind === "saved" ? "Saved" : "Optimised"}</Chip>
                  {x.kind === "saved" ? <span className="ml-2 text-text-secondary">{x.name}</span> : null}</td>
                <td className={tdCls}><Chip tone={/clears|found/i.test(x.outcome) ? "positive" : /no structure|below/i.test(x.outcome) ? "negative" : "neutral"}>{x.outcome}</Chip></td>
                <td className={cn(tdCls, "text-right tabular-nums")}>{rate(x.lifetime_raroc)}</td>
                <td className={tdCls}>{x.approval ?? "–"}</td>
                <td className={cn(tdCls, "whitespace-nowrap")}>
                  <button type="button" onClick={() => onOpen(x.href)} data-testid={`dealdesk-recent-open-${x.id}`} className="text-[12px] text-accent hover:underline">Open thread</button>
                  {x.report ? <a href={`${dealdeskOrigin()}${x.report}`} title="Word report" aria-label="Word report"
                                 className="ml-2 inline-flex rounded-md border border-border p-1 align-middle hover:bg-surface-hover"><FileText size={13} /></a> : null}
                </td>
              </tr>))}</tbody>
          </table>
        </div>) : null}
    </Section>
  );
}

export function DealDeskHome() {
  const router = useRouter();
  const params = useSearchParams();
  const [version, setVersion] = React.useState(0);
  // R14 U (K17): every deal the desk knows (dd_deal: DD, R12 reference deals, PL; plus uploads), not only the R11 store.
  const list = useLoad(() => dealdesk.deals(), `deals-${version}`);
  // R7: the pipeline filters live in the address (replaced, not pushed), so Back from a deal returns to the
  // pipeline exactly as it was filtered.
  const setParam = React.useCallback((key: string, value: string) => {
    const q = new URLSearchParams(window.location.search);
    if (value) q.set(key, value); else q.delete(key);
    window.history.replaceState(null, "", `/deal-desk${q.size ? `?${q}` : ""}`);
  }, []);
  const status = (params.get("status") ?? "") as "" | "pending" | Status;
  const source = params.get("source") ?? "";
  const setSource = (v: string) => setParam("source", v);
  const sector = params.get("sector") ?? "";
  const rating = params.get("rating") ?? "";
  const size = params.get("size") ?? "";
  const rm = params.get("rm") ?? "";
  const query = params.get("search") ?? "";
  const setStatus = (v: "" | "pending" | Status) => setParam("status", v);
  const setSector = (v: string) => setParam("sector", v);
  const setRating = (v: string) => setParam("rating", v);
  const setSize = (v: string) => setParam("size", v);
  const setRm = (v: string) => setParam("rm", v);
  const setQuery = (v: string) => setParam("search", v);
  const [draft, setDraft] = React.useState("");
  // R16 b: the business request studio, opened from the header button, from an ask typed in the chat box, or from a shared
  // link (?br=<request id>) / a customer file (?brc=<customer>&ask=)
  const [br, setBr] = React.useState<{ customer?: string; ask?: string; rid?: string } | null>(() => {
    const rid = params.get("br"), c = params.get("brc");
    return rid ? { rid } : c ? { customer: c, ask: params.get("ask") ?? undefined } : null;
  });
  const closeBr = () => { setBr(null); setParam("br", ""); setParam("brc", ""); setParam("ask", ""); };
  // R7: the New proposal dialog is a step (?new=1): browser Back closes it, and closing it is a Back.
  const adding = params.get("new") === "1";
  const setAdding = (on: boolean) => {
    if (on) { const q = new URLSearchParams(window.location.search); q.set("new", "1"); window.history.pushState(null, "", `/deal-desk?${q}`); }
    else backOr(router, () => setParam("new", ""));
  };
  const recentHome = useLoad(() => dealdesk.recent(6), `recent-home-${version}`);
  const papers = usePaperRows(2, { mine: true }); // Round W: the reader's living documents first
  const recentCards = React.useMemo(() => {
    const d = recentHome.data;
    const out: { key: string; title: string; sub: string; meta: string; onOpen: () => void; testId: string }[] = [];
    for (const w of papers ?? []) out.push({ key: `paper-${w.ws_id}`, title: `${w.proposal_id} · ${w.customer}`, sub: `${w.kind_label} · v${w.current_version}${w.final_version ? ` · final v${w.final_version}` : ""}`,
      meta: when(w.updated), onOpen: () => router.push(w.href), testId: `dealdesk-paper-card-${w.ws_id}` });
    // K16: the reader's newest threads first (each its own question), then saved and optimised analyses.
    for (const t of d?.threads ?? []) {
      if (out.length >= 3) break;
      out.push({ key: `thread-${t.thread_id}`, title: t.title, sub: `Deal Desk thread · ${t.turns} turn${t.turns === 1 ? "" : "s"}`,
        meta: when(t.updated), onOpen: () => router.push(t.href), testId: `dealdesk-thread-card-${t.thread_id}` });
    }
    if (d?.continue && d.continue.proposal_id !== "desk") out.push({ key: "continue", title: `${d.continue.proposal_id} · ${d.continue.obligor}`,
      sub: `“${d.continue.question}”`, meta: `Continue · ${when(d.continue.time)}`, onOpen: () => router.push(d.continue!.href), testId: "dealdesk-continue-card" });
    for (const x of d?.recent ?? []) {
      if (out.length >= 6) break;
      out.push({ key: `${x.kind}-${x.id}`, title: `${x.proposal_id} · ${x.obligor}`, sub: x.kind === "saved" ? `Saved · ${x.name}` : `Optimised · ${x.outcome}`,
        meta: `${when(x.time)} · RAROC ${rate(x.lifetime_raroc)}`, onOpen: () => router.push(x.href), testId: `dealdesk-recent-card-${x.id}` });
    }
    return out;
  }, [recentHome.data, router, papers]);
  // R11 L1: Single deal | Pipeline, in the address (?mode=pipeline) so Back returns to the same mode.
  const mode = params.get("mode") === "pipeline" ? "pipeline" : "single";
  const setMode = (m: "single" | "pipeline") => setParam("mode", m === "pipeline" ? "pipeline" : "");

  const rows = React.useMemo(() => list.data?.proposals ?? [], [list.data]);
  const sectors = [...new Set(rows.map((r) => r.sector))].sort();
  const rms = [...new Set(rows.map((r) => r.rm))].sort();
  const sources = [...new Set(rows.map((r) => r.source_label ?? ""))].filter(Boolean);
  const sz = SIZES.find((s) => s.key === size);
  // R14 U (K17): the same filters over every deal; search is fuzzy on name and id ("al sahal" → Al Sahel), best match first.
  const shown = searchDeals(rows.filter((r) => (!status || (status === "pending" ? r.pending : r.status === status)) && (!sector || r.sector === sector)
    && (!rating || r.rating === rating) && (!rm || r.rm === rm) && (!source || r.source_label === source)
    && (!sz?.key || (r.amount_sar_mn >= (sz.lo ?? 0) && r.amount_sar_mn < (sz.hi ?? Infinity)))), query);
  const counts: Record<string, number> = { ...Object.fromEntries(STATUSES.map((s) => [s, rows.filter((r) => r.status === s).length])),
                                            pending: rows.filter((r) => r.pending).length };

  const open = (id: string, question?: string) =>
    router.push(`/deal-desk/${encodeURIComponent(id)}${question ? `?q=${encodeURIComponent(question)}` : ""}`);
  // PLAN_R12 I21: a deal opened from the pipeline carries ?from=pipeline, so its page shows the banner and the way back.
  const openFromPipeline = (id: string) => router.push(`/deal-desk/${encodeURIComponent(id)}?from=pipeline`);
  // PLAN_R12 I30: the tab and the open card live in the address, so Back returns to the same place.
  const tab: TabKey = parseTab(params.get("tab"));
  const setTab = (t: TabKey) => {
    const q = new URLSearchParams(window.location.search);
    if (t === "origination") q.delete("tab"); else q.set("tab", t);
    q.delete("filter");
    window.history.pushState(null, "", `/deal-desk${q.size ? `?${q}` : ""}`);
  };
  const card = params.get("card") ?? "";
  const bookFilter = params.get("filter") ?? "";

  const ask = async (text: string) => {
    const question = text.trim();
    if (!question) return;
    // A question naming a proposal (its ID or its obligor) opens that proposal's thread with the question.
    // R14 U (K17): fuzzy ("Why does Al Sahal fail?" opens R12-TWA), over every deal (read first if the list is still loading).
    const all = rows.length ? rows : ((await dealdesk.deals().catch(() => null))?.proposals ?? []);
    // R16 b: an RM's ask ("renew all and increase the overdraft to SAR 60m") writes a business request, not a thread
    if (isBusinessAsk(question)) {
      const cs = (await getJson<{ customers: Parameters<typeof customerIn>[1] }>("/api/v1/dealdesk/business-requests/customers").catch(() => null))?.customers ?? [];
      const c = customerIn(question, cs);
      setDraft("");
      setBr({ customer: c?.key, ask: stripCustomer(question, c) });
      return;
    }
    const named = findNamedDeal(question, all);
    if (named) { open(named.proposal_id, question); return; }
    // Otherwise the question opens a NEW Deal Desk thread (R14 n, K16): its own id, title from the question.
    setDraft("");
    void openDeskThread(router, question);
  };

  // R13 X (J9, J10): the R11 landing again. Book and Parameters & policy are header buttons that open their views (?tab=);
  // the R12 work-queue cards are one line of small counters under the centred chat box.
  const onSide = tab !== "origination";
  return (
    <div className="space-y-4" data-testid="dealdesk-home">
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-text-muted">Intelligence</p>
          <div className="flex items-center gap-2">
            {onSide ? (
              <button type="button" onClick={() => setTab("origination")} data-testid="dealdesk-back-home" aria-label="Back to Deal Desk"
                      className="inline-flex size-7 items-center justify-center rounded-md text-text-muted hover:bg-surface-hover"><ArrowLeft size={15} /></button>) : null}
            <h1 className="text-2xl font-semibold text-text-primary">Deal Desk{onSide ? <span className="text-text-muted"> · {TABS.find((t) => t.key === tab)?.label}</span> : null}</h1>
            <InfoPopover title="Deal Desk">
              Pre-deal analysis: each credit proposal is measured against the RAROC hurdle, risk appetite and the regulatory
              limits on the live corporate book, and restructured into the counter-offer closest to the client&apos;s ask.
              Every figure comes from the Deal Desk engine; the assistant explains and drafts.
            </InfoPopover>
          </div>
        </div>
        <div className="ml-auto flex flex-wrap gap-2" data-testid="dealdesk-header-actions">
          <SecondaryButton onClick={() => setTab(tab === "book" ? "origination" : "book")} aria-pressed={tab === "book"} data-testid="dealdesk-tab-book"
                           className={cn(tab === "book" && "border-accent bg-accent-muted text-accent")}>
            <TrendingDown size={13} /> Book</SecondaryButton>
          {/* R14 F (K35): the Monitoring page, next to Book */}
          <SecondaryButton onClick={() => setTab(tab === "monitoring" ? "origination" : "monitoring")} aria-pressed={tab === "monitoring"} data-testid="dealdesk-tab-monitoring" data-tour="dd-monitoring"
                           className={cn(tab === "monitoring" && "border-accent bg-accent-muted text-accent")}>
            <Eye size={13} /> Monitoring</SecondaryButton>
          <SecondaryButton onClick={() => setTab(tab === "params" ? "origination" : "params")} aria-pressed={tab === "params"} data-testid="dealdesk-tab-params"
                           className={cn(tab === "params" && "border-accent bg-accent-muted text-accent")}>
            <SlidersHorizontal size={13} /> Parameters &amp; policy</SecondaryButton>
          <SecondaryButton onClick={() => setBr({})} data-testid="dealdesk-business-request"><FileText size={13} /> Business request</SecondaryButton>
          <PrimaryButton onClick={() => router.push("/deal-desk/review")} data-testid="dealdesk-review-link"><FileText size={14} /> Proposal review</PrimaryButton>
          <GovernanceTools origin="dealdesk" menu="dealdesk-tools" />{/* R13 IE */}
        </div>
      </div>

      {tab === "book" ? (
        <div className="space-y-4" data-testid="dealdesk-tab-book-panel">
          <Slot name="BookTab" props={{ filter: bookFilter }} />
          {!hasSlot("BookTab") ? (
            <Section title="Book" testId="dealdesk-book-fallback"
                     info="Every approved facility with its monitoring tier, RAROC drift, EWS status, conditions, promises and renewal.">
              <SecondaryButton onClick={() => router.push("/deal-desk/portfolio-raroc")} data-testid="dealdesk-portfolio-raroc-link">
                <TrendingDown size={13} /> RAROC drift</SecondaryButton>
            </Section>) : null}
        </div>) : null}

      {tab === "monitoring" ? <div data-testid="dealdesk-tab-monitoring-panel"><MonitoringPage /></div> : null}

      {tab === "params" ? (
        <div className="space-y-4" data-testid="dealdesk-tab-params-panel">
          <Slot name="ParametersTab" props={{}} />
          {!hasSlot("ParametersTab") ? (
            <Section title="Parameters & policy" testId="dealdesk-params-fallback"
                     info="The Deal Desk parameters (hurdles, appetite, pricing grids) with their versions, and the parameters learned from the bank's policy documents.">
              <div className="flex flex-wrap gap-2">
                <SecondaryButton onClick={() => router.push("/deal-desk/parameters")} data-testid="dealdesk-params-link"><SlidersHorizontal size={13} /> Deal Desk Parameters</SecondaryButton>
                <SecondaryButton onClick={() => router.push("/deal-desk/parameters/learn")} data-testid="dealdesk-params-learn-link"><FileText size={13} /> Learn from documents</SecondaryButton>
              </div>
            </Section>) : null}
        </div>) : null}

      {tab === "origination" ? (<>

      <div className="flex flex-wrap items-center gap-3">
      <div className="inline-flex rounded-md border border-border p-0.5" role="tablist" aria-label="Deal Desk mode" data-testid="dealdesk-mode">
        {([["single", "Single deal"], ["pipeline", "Pipeline"]] as const).map(([k, label]) => (
          <button key={k} type="button" role="tab" aria-selected={mode === k} onClick={() => setMode(k)} data-testid={`dealdesk-mode-${k}`}
                  className={cn("h-8 rounded px-4 text-[13px]", mode === k ? "bg-accent font-medium text-accent-contrast" : "text-text-secondary hover:bg-surface-hover")}>
            {label}</button>))}
      </div>
      {/* R14 p (K33): "Check all pending proposals" on the landing and the Pipeline tab. */}
      <Slot name="BatchCheck" props={{}} />
      {/* PLAN_R11 R4 (mounted by U): conditions due across the reviewed deals, one line, Single deal mode only. */}
      {mode === "single" ? <ConditionsDueLine /> : null}
      </div>

      {mode === "single" ? (<>
        {/* R13 X (J7): the centred chat box with small cards of recent work (one ModuleLanding for Deal Desk, What-If, Lenses). */}
        <ModuleLanding ids="dealdesk" title="Ask Deal Desk" value={draft} onChange={setDraft} onAsk={ask}
                       placeholder="Ask Deal Desk, e.g. “Why does DD-03 fail?”"
                       examples={["How much real-estate headroom is left this quarter?", "Which proposals breach a hard limit?", "How much sector headroom is left?"]}
                       recentTitle="Recent work" recentLoading={!recentHome.data && !recentHome.error}
                       recent={recentCards} />
        {/* R13 X (J9): the work queues as one line of small counters (material names for the Book counters). */}
        <LandingCards open={card} onOpenCard={(k) => setParam("card", k)} />
        {card === "sme" ? <div id="sme-fast-track"><Slot name="SmeFastTrack" props={{}} /></div> : null}
      </>) : null}

      {mode === "pipeline" ? <PipelineMode onOpen={openFromPipeline} /> : (<>
      <Section title="Proposal pipeline" testId="dealdesk-pipeline"
               action={<div className="flex flex-wrap gap-2">
                 <TryDocsEntry variant="secondary" />
                 {/* R16 c: business request in, credit division's response out */}
                 <SecondaryButton onClick={() => router.push("/deal-desk/credit-response?from=deal-desk")} data-testid="dealdesk-credit-response"
                                  title="Upload an RM's business request with the documents: CreditProbe writes the RM feedback and the credit division's response">
                   <FileText size={14} /> Credit response</SecondaryButton>
                 <SecondaryButton onClick={() => setAdding(true)} data-testid="dealdesk-new"><Plus size={14} /> New proposal</SecondaryButton></div>}>
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <div className="inline-flex rounded-md border border-border p-0.5" role="tablist" aria-label="Status">
            {(["", "pending", ...STATUSES] as const).map((s) => (
              <button key={s || "all"} type="button" role="tab" aria-selected={status === s} onClick={() => setStatus(s)}
                      data-testid={`dealdesk-status-${(s || "all").replace(/\W+/g, "-")}`}
                      title={s === "pending" ? "New, in review or counter-offered: the deals the Pipeline tab optimises" : undefined}
                      className={cn("h-7 rounded px-2.5 text-[12px]", status === s ? "bg-accent text-accent-contrast" : "text-text-secondary hover:bg-surface-hover")}>
                {s === "pending" ? "Pending" : s ? STATUS_LABEL[s] : "All"} <span className="tabular-nums opacity-70" data-testid={`dealdesk-count-${s || "all"}`}>{s ? counts[s] : rows.length}</span></button>))}
          </div>
          <Select value={sector} onChange={setSector} label="Sector" testId="dealdesk-filter-sector">
            <option value="">All sectors</option>{sectors.map((s) => <option key={s} value={s}>{s}</option>)}</Select>
          <Select value={rating} onChange={setRating} label="Rating" testId="dealdesk-filter-rating">
            <option value="">All ratings</option>{RATINGS.filter((r) => rows.some((x) => x.rating === r)).map((r) => <option key={r} value={r}>{r}</option>)}</Select>
          <Select value={size} onChange={setSize} label="Size" testId="dealdesk-filter-size">
            {SIZES.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}</Select>
          <Select value={rm} onChange={setRm} label="Relationship manager" testId="dealdesk-filter-rm">
            <option value="">All RMs</option>{rms.map((r) => <option key={r} value={r}>{r}</option>)}</Select>
          {sources.length > 1 ? (
            <Select value={source} onChange={setSource} label="Source" testId="dealdesk-filter-source">
              <option value="">All sources</option>{sources.map((r) => <option key={r} value={r}>{r} ({list.data?.by_source?.[r] ?? 0})</option>)}</Select>) : null}
          <label className="ml-auto inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-surface px-2 text-text-muted">
            <Search size={13} /><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search name or ID" aria-label="Search proposals"
                                       data-testid="dealdesk-search" className="w-40 bg-transparent text-[12px] text-text-primary outline-none" /></label>
        </div>
        {list.error ? <p className="text-[12px] text-negative" role="alert">{list.error}</p> : null}
        {!list.data ? <Skeleton className="h-64 w-full" /> : (
          <div className="overflow-auto">
            <table className={tableCls} data-testid="dealdesk-table">
              <thead><tr>
                <th className={thCls}>Proposal</th><th className={thCls}>Obligor</th><th className={thCls}>Sector</th>
                <th className={cn(thCls, "text-center")}>Rating</th><th className={thCls}>Facility</th>
                <th className={cn(thCls, "text-right")}>Amount</th><th className={cn(thCls, "text-right")}>Tenor</th>
                <th className={thCls}>RM</th><th className={thCls}>Status</th></tr></thead>
              <tbody>
                {shown.map((r: ProposalSummary) => (
                  <tr key={r.proposal_id} onClick={() => open(r.proposal_id)} data-testid={`dealdesk-row-${r.proposal_id}`}
                      className="cursor-pointer hover:bg-surface-hover">
                    <td className={cn(tdCls, "font-medium text-accent")}>{r.proposal_id}</td>
                    <td className={cn(tdCls, "whitespace-normal")}><span className="text-text-primary">{r.obligor_name}</span>
                      {!r.existing ? <span className="ml-2 inline-block"><Chip>New to bank</Chip></span> : null}
                      {r.source === "r12_demo" || r.source === "pipeline" || r.source === "r16_customer" ? <span className="ml-2 inline-block" data-testid="dealdesk-row-source"><Chip>{r.source_label}</Chip></span> : null}</td>
                    <td className={cn(tdCls, "whitespace-normal")}>{r.sector}</td>
                    <td className={cn(tdCls, "text-center font-medium")}>{r.rating}</td>
                    <td className={cn(tdCls, "whitespace-normal")}>{FACILITY[r.facility_type] ?? r.facility_type} · {STRUCTURE[r.structure] ?? r.structure}</td>
                    <td className={cn(tdCls, "text-right")}>{money(r.amount, r.currency)}</td>
                    <td className={cn(tdCls, "text-right")}>{r.tenor_years}y</td>
                    <td className={cn(tdCls, "whitespace-normal")}>{r.rm}</td>
                    <td className={tdCls}><Chip tone={STATUS_TONE[r.status]}>{STATUS_LABEL[r.status] ?? r.status}</Chip></td>
                  </tr>))}
                {!shown.length ? <tr><td colSpan={9} className="px-2 py-6 text-center text-[12px] text-text-muted">No proposal matches these filters.</td></tr> : null}
              </tbody>
            </table>
          </div>)}
        {/* R16 d: the customer packs (documents to upload, what to type, the Bank's file) */}
        <button type="button" onClick={() => router.push("/deal-desk/customer-packs")} data-testid="dealdesk-customer-packs-link"
                className="mt-2 inline-flex items-center gap-1 text-[12px] text-accent hover:underline">Customer packs: documents to upload and what to type →</button>
        <IntelligenceStudioLink className="ml-4" /> {/* Round S */}
      </Section>

      <RecentAnalyses version={version} onOpen={(href) => router.push(href)} />
      </>)}
      </>) : null}

      {br ? <BusinessRequestStudio initialCustomer={br.customer} initialAsk={br.ask} requestId={br.rid} onClose={closeBr} /> : null}
      {adding ? <NewProposal onClose={() => setAdding(false)} onCreated={(id) => {
        // The new deal replaces the dialog's step, so Back from the deal returns to the pipeline, not the dialog.
        setVersion((v) => v + 1); router.replace(`/deal-desk/${encodeURIComponent(id)}`); }} /> : null}
    </div>
  );
}
