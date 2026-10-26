"use client";

/**
 * PLAN_R11_AGENTS E4: the Early Warning triage agent (`ews.triage`) in Early Warning, with the smallest UI:
 *
 *   <TriageWithAgent domain period />   the header button ("Triage with agent"), opens the shared drawer
 *   <TriageInbox domain />              a collapsible line under the tiles (recent and scheduled runs)
 *   <VerdictChip verdict … />           the Agent verdict on each row of the list; opens the drawer for that name
 *
 * Verdicts are read from the latest period run of the book (its findings); a name's chip starts a borrower run so
 * the drawer shows that name's plan, evidence, ECL impact, RM action and proposal. SICR and UTP stay proposals in
 * the approvals queue: nothing here changes a stage. Both books (retail at customer level, worst names first).
 */

import * as React from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Bot } from "lucide-react";

import { AgentInbox, AgentRunButton, AgentRunDrawer, ProposalRow } from "@/components/v5/core/agent-run";
import { b360LinkFor, backWithRun, ewsDetailHref, sourceLegend } from "@/components/v5/core/agent-finding-model";
import { KpiRow, type KpiTile } from "@/components/v5/core/kpi-row";
import { type AgentRun, type AgentRunSummary, agentsOrigin, isFinished, listApprovals, listRuns, startRun } from "@/lib/v5/agents";
import { type DomainId, count, sar } from "@/lib/v5/ews";
import { cn } from "@/lib/utils";

import {
  AGENT_ID, TRIAGE_GOAL, VERDICT_LABEL, type Verdict, periodRuns, runPeriod, verdictMap, verdictTone,
} from "./agent-verdict-core";

const UPDATED = "ews-triage-updated";

async function compactRun(runId: string): Promise<AgentRun | null> {
  try {
    const r = await fetch(`${agentsOrigin()}/api/v1/agents/runs/${encodeURIComponent(runId)}?compact=true`,
                          { credentials: "include", cache: "no-store" });
    return r.ok ? ((await r.json()) as AgentRun) : null;
  } catch {
    return null;
  }
}

/** Wait for a run to finish, then tell the list to re-read its verdicts. */
function watch(runId: string) {
  const tick = async (n: number) => {
    const r = await compactRun(runId);
    if (r && isFinished(r.status)) window.dispatchEvent(new Event(UPDATED));
    else if (n < 120) setTimeout(() => void tick(n + 1), 2000);
  };
  void tick(0);
}

/** `{borrower_id: verdict}` from the latest finished period run of this book and period ("" = the latest period). */
export function useTriageVerdicts(domain: DomainId, period: string): { verdicts: Record<string, Verdict>; runId: string } {
  const [state, setState] = React.useState<{ key: string; verdicts: Record<string, Verdict>; runId: string }>(
    { key: "", verdicts: {}, runId: "" });
  const [nonce, setNonce] = React.useState(0);
  const key = `${domain}|${period}|${nonce}`;
  React.useEffect(() => {
    const on = () => setNonce((n) => n + 1);
    window.addEventListener(UPDATED, on);
    return () => window.removeEventListener(UPDATED, on);
  }, []);
  React.useEffect(() => {
    let live = true;
    (async () => {
      let rows: AgentRunSummary[] = [];
      try {
        rows = (await listRuns({ agent: AGENT_ID, scope: domain, limit: 12 })).runs;
      } catch {
        return;  // the agents service is optional: no verdicts, the list is unchanged
      }
      for (const row of periodRuns(rows, domain).slice(0, 4)) {
        const run = await compactRun(row.run_id);
        if (!live || !run) continue;
        const p = runPeriod(run as never);
        if (period && p && p !== period) continue;
        setState({ key, verdicts: verdictMap(run.findings as never), runId: run.run_id });
        return;
      }
      if (live) setState({ key, verdicts: {}, runId: "" });
    })();
    return () => { live = false; };
  }, [domain, period, key]);
  return state.key === key ? state : { verdicts: {}, runId: "" };
}

/** R15 L4: what the triage agent is, before it has a result (the run's own lines replace these when it ends). */
export const TRIAGE_PLAIN_WORDS = [
  "Reads every borrower flagged this period and tests each against the CBUAE rules for SICR and unlikely to pay.",
  "Produces a verdict per borrower, the ECL each proposal adds and an action for the RM.",
  "Nothing changes on its own: a credit officer approves or rejects every proposal.",
  "Takes about 10–30 seconds; a slow model is dropped after 40 seconds.",
];

/** The header button: triage this period's warnings. Back from Borrower 360 / Early Warning detail reopens the run
 *  (agent_run=<id> on the page's URL). */
export function TriageWithAgent({ domain, period }: { domain: DomainId; period: string }) {
  const q = useSearchParams();
  const again = q?.get("agent_run") || null;
  return (
    <AgentRunButton agent={AGENT_ID} goal={TRIAGE_GOAL} context={{ domain, period }} label="Triage with agent"
                    primary={false} testId="ews-triage-agent" onRun={watch} initialRunId={again}
                    plainWords={TRIAGE_PLAIN_WORDS} renderOutput={(run) => <TriageOutput run={run} />} />
  );
}

/** The collapsible line under the tiles: recent and scheduled triage runs of the book. */
export function TriageInbox({ domain }: { domain: DomainId }) {
  return <AgentInbox agent={AGENT_ID} scope={domain} title="Triage agent" limit={5}
                     renderOutput={(run) => <TriageOutput run={run} />} />;
}

/** The Agent verdict chip on a list row. Click: a borrower run for that name, in the drawer. */
export function VerdictChip({ verdict, domain, period, customerId }: {
  verdict?: Verdict; domain: DomainId; period: string; customerId: string;
}) {
  const [runId, setRunId] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  if (!verdict) return null;
  const open = async (e: React.MouseEvent | React.KeyboardEvent) => {
    e.stopPropagation();
    if (busy) return;
    setBusy(true);
    try {
      const r = await startRun(AGENT_ID, `Triage ${customerId}`, { domain, period, borrower: customerId }, "auto");
      setRunId(r.run_id);
    } catch {
      // the agents service is optional; the chip stays as it is
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <button type="button" onClick={open} data-testid={`ews-agent-verdict-${customerId}`}
              title="Agent verdict: open the triage for this name"
              className={cn("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em]",
                            verdictTone(verdict), busy && "opacity-60")}>
        <Bot className="size-3" aria-hidden /> {VERDICT_LABEL[verdict]}
      </button>
      {runId ? (
        <span onClick={(e) => e.stopPropagation()}>
          <AgentRunDrawer runId={runId} onClose={() => setRunId(null)} renderOutput={(run) => <TriageOutput run={run} />} />
        </span>
      ) : null}
    </>
  );
}

interface Summary {
  warned: number; reviewed: number; stage3_outside: number; noise: number; watch: number; watchlist: number;
  sicr: number; utp: number; sicr_ead: number; sicr_ecl: number; utp_ead: number; utp_ecl: number;
}

interface NameData {
  borrower_id: string; borrower_name?: string; verdict: Verdict; label: string; confidence: string; articles: string[];
  indicators: { code: string; label: string; article: string; strength: string; in_basis?: boolean; excerpt?: string }[];
  ecl_impact?: { ead: number; current_ecl: number; proposal_move: number; expected_uplift: number; pd_pct: number } | null;
  action_note?: { owner: string; owner_role: string; due: string; action: string; drivers: string[] } | null;
  followup?: { outcome?: string; why?: string } | null;
}

interface TableRow {
  borrower_id: string; borrower_name: string; verdict: Verdict; verdict_plain: string; sector?: string; stage?: number;
  ead?: number | null; ecl_move?: number | null; action: string; owner: string; due: string; rule: string;
  articles: string[]; evidence: string[]; approval_id?: string | null;
}

/** R15 L5: the ranked table: borrower (→ Borrower 360), EAD, ECL move, recommended action, rule, evidence, decision. */
function TriageTable({ run }: { run: AgentRun }) {
  const rows = (run.output?.table ?? []) as TableRow[];
  const terms = (run.output?.terms ?? {}) as Record<string, string>;
  const sources = (run.output?.sources ?? null) as Record<string, string> | null;
  const [here, setHere] = React.useState("");
  React.useEffect(() => { setHere(`${window.location.pathname}${window.location.search}`); }, []);
  const [nonce, setNonce] = React.useState(0);
  const [approvals, setApprovals] = React.useState(run.approvals ?? []);
  const [queued, setQueued] = React.useState<NonNullable<AgentRun["approvals"]>>([]);
  React.useEffect(() => { setApprovals(run.approvals ?? []); }, [run.approvals]);
  // proposals still pending from an earlier run are not raised again; read them from the queue so they can be decided here
  const loadQueue = React.useCallback(async () => {
    try { setQueued((await listApprovals({ agent: AGENT_ID, status: "pending" })).approvals ?? []); } catch { /* optional */ }
  }, []);
  React.useEffect(() => { void loadQueue(); }, [loadQueue, run.run_id]);
  const refresh = async () => {
    const r = await compactRun(run.run_id);
    if (r?.approvals) setApprovals(r.approvals);
    await loadQueue();
    setNonce((n) => n + 1);
  };
  if (!rows.length) return null;
  const domain = (run.context?.domain as string) === "retail" ? "retail" : "corporate";
  const period = String(run.output?.period ?? run.context?.period ?? "");
  const back = backWithRun(here || "/early-warning", run.run_id);
  const byId = new Map([...queued, ...approvals].map((a) => [a.id, a]));
  return (
    <section className="border-t border-border px-4 py-3" data-testid="ews-triage-table" data-nonce={nonce}>
      <h3 className="mb-1 text-[11px] font-medium uppercase tracking-[0.08em] text-text-muted">Ranked proposals</h3>
      <p className="mb-2 text-[11px] text-text-muted" data-testid="ews-triage-terms">
        <span title={terms.UTP}><b className="text-text-secondary">UTP</b> = unlikely to pay → Stage 3</span> ·{" "}
        <span title={terms.SICR}><b className="text-text-secondary">SICR</b> = significant increase in credit risk → Stage 2</span> ·{" "}
        <span title={terms.EAD}><b className="text-text-secondary">EAD</b> = exposure at default</span> ·{" "}
        <span title={terms["ECL move"]}><b className="text-text-secondary">ECL move</b> = provision added if approved</span> · amounts SAR m
      </p>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[760px] border-collapse text-[12px]">
          <thead>
            <tr className="border-b border-border text-left text-[11px] text-text-muted">
              <th className="py-1 pr-2 font-medium">#</th>
              <th className="py-1 pr-2 font-medium">Borrower</th>
              <th className="py-1 pr-2 text-right font-medium">EAD</th>
              <th className="py-1 pr-2 text-right font-medium">ECL move</th>
              <th className="py-1 pr-2 font-medium">Recommended action</th>
              <th className="py-1 pr-2 font-medium">Rule</th>
              <th className="py-1 pr-2 font-medium">Evidence</th>
              <th className="py-1 font-medium">Decision</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => {
              const subj = { id: r.borrower_id, name: r.borrower_name, domain: domain as "corporate" | "retail", period };
              const href = b360LinkFor(subj, "ews", back) ?? ewsDetailHref(subj, "ews", back);
              const a = r.approval_id ? byId.get(r.approval_id) : undefined;
              return (
                <tr key={r.borrower_id} className="border-b border-border/60 align-top" data-testid="ews-triage-row">
                  <td className="py-1.5 pr-2 tabular-nums text-text-muted">{i + 1}</td>
                  <td className="py-1.5 pr-2">
                    <Link href={href} className="font-medium text-accent hover:underline" data-testid="ews-triage-row-b360"
                          title={href.startsWith("/borrower-360") ? "Open Borrower 360" : "Open the Early Warning detail"}>{r.borrower_name}</Link>
                    <div className="mt-0.5 flex flex-wrap items-center gap-1">
                      <span className={cn("inline-flex rounded-full border px-1.5 py-px text-[10px] font-semibold", verdictTone(r.verdict))} title={terms[VERDICT_LABEL[r.verdict]] ?? r.verdict_plain}>{r.verdict_plain}</span>
                      <span className="text-[10px] text-text-muted">{r.borrower_id}{r.sector ? ` · ${r.sector}` : ""}</span>
                    </div>
                  </td>
                  <td className="py-1.5 pr-2 text-right tabular-nums">{r.ead != null ? r.ead.toLocaleString("en-GB", { maximumFractionDigits: 1 }) : "–"}</td>
                  <td className="py-1.5 pr-2 text-right tabular-nums text-warning">{r.ecl_move ? `+${r.ecl_move.toLocaleString("en-GB", { maximumFractionDigits: 2 })}` : "–"}</td>
                  <td className="max-w-[220px] py-1.5 pr-2 text-text-secondary"><p className="line-clamp-3" title={r.action}>{r.action || "–"}</p>{r.owner ? <p className="text-[10px] text-text-muted">{r.owner}{r.due ? ` · due ${r.due}` : ""}</p> : null}</td>
                  <td className="max-w-[200px] py-1.5 pr-2 text-text-secondary"><p className="line-clamp-3" title={r.rule}>{r.rule || r.articles.join(", ") || "–"}</p></td>
                  <td className="py-1.5 pr-2">
                    <div className="flex flex-wrap gap-0.5">{r.evidence.map((sid) => <span key={sid} title={sourceLegend(sid, sources)} className="rounded border border-border px-1 text-[10px] text-text-secondary">{sid}</span>)}</div>
                  </td>
                  <td className="min-w-[150px] py-1.5">{a ? <ul className="list-none"><ProposalRow a={a} compact onDecided={() => void refresh()} /></ul> : <span className="text-[11px] text-text-muted">{r.approval_id ? "in the approvals queue" : "no proposal"}</span>}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

/** The module's part of the drawer (every figure from the run): the portfolio summary, or for one borrower its
 *  CBUAE indicators, ECL impact and RM action. */
function TriageOutput({ run }: { run: AgentRun }) {
  const one = run.findings.find((f) => f.kind?.startsWith("ews.verdict."));
  if (run.scope.includes(":") && one && run.findings.filter((f) => f.kind?.startsWith("ews.verdict.")).length === 1) {
    return <NameOutput d={one.data as unknown as NameData} />;
  }
  const s = (run.output?.summary ?? null) as Summary | null;
  if (!s) return null;
  const tiles: KpiTile[] = [
    { label: "Reviewed", value: count(s.reviewed), sub: `of ${count(s.warned)} warned · ${count(s.stage3_outside)} Stage 3 set aside` },
    { label: "SICR (→ Stage 2)", value: count(s.sicr), sub: `EAD ${sar(s.sicr_ead)} · ECL +${sar(s.sicr_ecl)}`, tone: s.sicr ? "warning" : "neutral" },
    { label: "UTP (→ Stage 3)", value: count(s.utp), sub: `EAD ${sar(s.utp_ead)} · ECL +${sar(s.utp_ecl)}`, tone: s.utp ? "negative" : "neutral" },
    { label: "Watchlist · watch · noise", value: `${count(s.watchlist)} · ${count(s.watch)} · ${count(s.noise)}`, sub: "kept under review or explained" },
  ];
  return (
    <>
      <div className="border-t border-border px-4 py-3" data-testid="ews-triage-summary"><KpiRow tiles={tiles} /></div>
      <TriageTable run={run} />
    </>
  );
}

function NameOutput({ d }: { d: NameData }) {
  const e = d.ecl_impact;
  const tiles: KpiTile[] = e ? [
    { label: "EAD", value: sar(e.ead), sub: `ECL now ${sar(e.current_ecl)}` },
    { label: "ECL if approved", value: `+${sar(e.proposal_move)}`, sub: d.verdict === "utp" ? "Stage 3: EAD × LGD floor" : d.verdict === "sicr" ? "Stage 2: lifetime ECL" : "no stage move", tone: e.proposal_move > 0 ? "warning" : "neutral" },
    { label: "Expected uplift", value: `+${sar(e.expected_uplift)}`, sub: `EWS method · PD ${e.pd_pct}%` },
  ] : [];
  const n = d.action_note;
  return (
    <div className="space-y-3 border-t border-border px-4 py-3" data-testid="ews-triage-name">
      <div className="flex flex-wrap items-center gap-2">
        <span className={cn("inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em]", verdictTone(d.verdict))}>
          {VERDICT_LABEL[d.verdict]}
        </span>
        <span className="text-[12px] text-text-secondary">{d.confidence} confidence{d.articles.length ? ` · ${d.articles.join(", ")}` : ""}</span>
      </div>
      {tiles.length ? <KpiRow tiles={tiles} /> : null}
      {d.indicators.length ? (
        <ul className="space-y-1" data-testid="ews-triage-indicators">
          {d.indicators.map((i) => (
            <li key={i.code} className="text-[12px]">
              <span className={cn("mr-1.5 font-mono text-[10px]", i.in_basis ? "text-text-primary" : "text-text-muted")}>{i.article}</span>
              <span className={i.in_basis ? "text-text-primary" : "text-text-secondary"}>{i.label}</span>
              {i.strength === "context" ? <span className="ml-1 text-[11px] text-text-muted">(context)</span> : null}
              {i.excerpt ? <p className="mt-0.5 line-clamp-2 text-[11px] text-text-muted">{i.excerpt}</p> : null}
            </li>
          ))}
        </ul>
      ) : null}
      {n ? (
        <div className="rounded-md border border-border bg-surface-muted/40 p-2.5 text-[12px]" data-testid="ews-triage-action">
          <p className="font-medium text-text-primary">Action · {n.owner} · due {n.due}</p>
          <p className="mt-0.5 text-text-secondary">{n.action}</p>
        </div>
      ) : null}
      {d.followup?.why ? <p className="text-[12px] text-text-secondary">Follow-up: {d.followup.why}</p> : null}
    </div>
  );
}
