"use client";

/**
 * PLAN_R9 Session E (E3): Proposal review, P7 Proposal & Regulatory Response Intelligence.
 * Upload a proposal (.docx or .pdf) or open one of the prepared cases; the outputs follow in order:
 * summary, arithmetic checks, quality score, information gaps (each "Send as query to RM"),
 * weakness → mitigant map (uncovered in red), pre-deal analysis, counter-proposals, the proposed
 * Accepted Risk Watch entry and the reviewer opinion in Word. Every figure comes from the Deal Desk engine.
 */

import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { Download, FileUp, Send, Settings2 } from "lucide-react";

import { InfoPopover } from "./explain"; // R12 G (I6): the bounded Deal Desk (i)
import { Skeleton } from "@/components/ui/skeleton";
import { BackButton } from "@/components/v5/core/back-button";
import { Plot } from "@/components/v5/ews/plot";
import { cn } from "@/lib/utils";
import { useLoad } from "@/lib/v5/dealdesk";
import { type Review, aed, pc, review } from "@/lib/v5/proposal-review";

import { PoweredBy } from "@/components/v5/core/powered-by";
import { Chip, Kpi, PrimaryButton, Section, SecondaryButton, tableCls, tdCls, thCls } from "./kit";
import { ConditionsPage } from "./review-conditions";
import { ReviewRules } from "./review-rules";
import { ReviewSubjects } from "./review-subjects";
import { ReviewWorkspace } from "./review-workspace";
import { KpiRow } from "@/components/v5/core/kpi-row";

const wrap = "whitespace-normal";

function CaseList({ onOpen, onWorkspace }: { onOpen: (id: string) => void; onWorkspace: (id: string) => void }) {
  const r = useLoad(() => review.cases(), "cases");
  return (
    <Section title="Proposals for review" testId="review-cases"
             info="The proposals received for credit review. Open one to run the review; the verdict compares RAROC (with fees and deposits) with the hurdle in Admin → Deal Desk Parameters.">
      {r.error ? <p role="alert" className="text-[12px] text-negative">{r.error}</p> : null}
      {!r.data && !r.error ? <Skeleton className="h-20 w-full" /> : null}
      {r.data ? (
        <table className={tableCls} data-testid="review-cases-table">
          <thead><tr>{["Borrower", "Sector", "Tier", "Proposed limits", "Quality", "RAROC", "Hurdle", "Verdict", ""].map((h) => <th key={h} className={thCls}>{h}</th>)}</tr></thead>
          <tbody>{r.data.cases.map((c) => (
            <tr key={c.case_id} className="cursor-pointer hover:bg-surface-muted" onClick={() => onOpen(c.case_id)} data-testid="review-case-row">
              <td className={cn(tdCls, "font-medium")}>{c.borrower}</td><td className={tdCls}>{c.sector}</td><td className={tdCls}>{c.tier}</td>
              <td className={cn(tdCls, "text-right")}>{aed(c.total_proposed)}</td><td className={cn(tdCls, "text-right")}><b>{c.score}</b>/100</td>
              <td className={cn(tdCls, "text-right")}><b>{pc(c.raroc)}</b></td><td className={cn(tdCls, "text-right")}>{pc(c.hurdle)}</td>
              <td className={tdCls}><Chip tone={c.verdict.startsWith("Clears") ? "positive" : "negative"}>{c.verdict}</Chip></td>
              <td className={tdCls}><div className="flex gap-1.5"><SecondaryButton onClick={(e) => { e.stopPropagation(); onOpen(c.case_id); }}>Review</SecondaryButton>
                <SecondaryButton onClick={(e) => { e.stopPropagation(); onWorkspace(c.case_id); }} data-testid="review-open-workspace">Workspace</SecondaryButton></div></td>
            </tr>))}</tbody>
        </table>) : null}
    </Section>
  );
}

function Network({ r }: { r: Review }) {
  if (!r.graph.length) return null;
  const names = Array.from(new Set(r.graph.flatMap((e) => [e.from, e.to])));
  const pos = Object.fromEntries(names.map((n, i) => [n, { x: Math.cos((2 * Math.PI * i) / names.length), y: Math.sin((2 * Math.PI * i) / names.length) }]));
  const bad = (n: string) => /Marwan|Loss|staff/i.test(n);
  const edges = r.graph.map((e) => ({ type: "scatter", mode: "lines", x: [pos[e.from].x, pos[e.to].x], y: [pos[e.from].y, pos[e.to].y],
    line: { color: "#B8A98A", width: 1.5 }, hoverinfo: "text", text: `${e.from} → ${e.to}: ${e.label}`, showlegend: false }));
  const nodes = { type: "scatter", mode: "markers+text", x: names.map((n) => pos[n].x), y: names.map((n) => pos[n].y), text: names,
    textposition: "bottom center", hovertext: names, hoverinfo: "text", showlegend: false,
    marker: { size: 16, color: names.map((n) => (bad(n) ? "#B4443C" : n === r.summary.borrower ? "#1F4E79" : "#8A7F6A")) } };
  return (
    <Section title="Connected parties" testId="review-graph"
             info="Borrower, related parties, sponsors, connected obligors and guarantors from the proposal and CBRBR. Red: classified, at Loss or a conflict of interest. Cross-default under CBUAE CRM Art 6.12.">
      <Plot ariaLabel="Connected parties" filename="connected-parties" height={340} scrollZoom
            data={[...edges, nodes] as never[]} layout={{ xaxis: { visible: false, range: [-1.6, 1.6] }, yaxis: { visible: false, range: [-1.4, 1.3] }, margin: { l: 10, r: 10, t: 10, b: 10 } } as never} />
      <ul className="mt-2 space-y-1 text-[12px] text-text-secondary">{r.graph.map((e, i) => <li key={i}>{e.from} → {e.to}: {e.label}</li>)}</ul>
    </Section>
  );
}

function ReviewView({ r, onBack, onWorkspace }: { r: Review; onBack: () => void; onWorkspace?: (id: string) => void }) {
  const [sent, setSent] = React.useState<Record<string, string>>({});
  const [err, setErr] = React.useState("");
  const id = r.case_id as string;
  const p = r.pre_deal;
  const s = r.summary;
  const send = (gap: string) => review.query(id, gap).then((x) => setSent((m) => ({ ...m, [gap]: `${x.status}: ${x.to}` })), (e: unknown) => setErr(e instanceof Error ? e.message : String(e)));
  return (
    <div className="space-y-4" data-testid="review-view">
      <div className="flex flex-wrap items-center gap-3">
        <SecondaryButton onClick={onBack} data-testid="review-back-list">All proposals</SecondaryButton>
        <h2 className="text-xl font-semibold text-text-primary">{s.borrower}</h2>
        <Chip>{s.tier}</Chip><Chip>{s.sector}</Chip><Chip>Rating {s.rating}</Chip>
        <div className="ml-auto flex gap-2">
          {onWorkspace ? <SecondaryButton onClick={() => onWorkspace(id)} data-testid="review-to-workspace">Review workspace</SecondaryButton> : null}
          <a href={review.proposalUrl(id)} data-testid="review-proposal-file"><SecondaryButton><Download size={14} /> Proposal</SecondaryButton></a>
          <a href={review.opinionUrl(id)} data-testid="review-opinion"><PrimaryButton><Download size={14} /> Reviewer opinion (Word)</PrimaryButton></a>
        </div>
      </div>
      <PoweredBy pack="P7" rule="P7-PRO-01" article={r.powered_by.rules.join(", ")} confidence="high" trace={{ href: `/deal-desk/review?case=${encodeURIComponent(id)}#review-checks` }} testId="review-powered-by" />
      {err ? <p role="alert" className="text-[12px] text-negative">{err}</p> : null}

      <Section title="1. Extracted summary" testId="review-summary" info="What the proposal asks for, read from the uploaded file: the request, the facilities and the recommendation.">
        <p className="mb-2 text-[13px] text-text-secondary">{s.profile}. Group: {s.group}. Recommendation: <b>{s.recommendation}</b>. CRO box: <b>{s.cro_box}</b>.</p>
        <ul className="mb-3 list-disc pl-5 text-[13px]">{s.request.map((x) => <li key={x}>{x}</li>)}</ul>
        <table className={tableCls}><thead><tr>{["Facility", "Existing", "Proposed", "Pricing"].map((h) => <th key={h} className={thCls}>{h}</th>)}</tr></thead>
          <tbody>{s.facilities.map((f) => <tr key={f.name}><td className={cn(tdCls, wrap)}>{f.name}</td><td className={cn(tdCls, "text-right")}>{aed(f.existing)}</td>
            <td className={cn(tdCls, "text-right")}>{aed(f.proposed)}</td><td className={cn(tdCls, "text-right")}>{f.bps} bps</td></tr>)}
            <tr><td className={cn(tdCls, "font-semibold")}>Total limits</td><td className={cn(tdCls, "text-right font-semibold")}>{aed(s.total_existing)}</td>
              <td className={cn(tdCls, "text-right font-semibold")}>{aed(s.total_proposed)}</td><td className={tdCls} /></tr></tbody></table>
        {s.projects.length ? <ul className="mt-3 list-disc pl-5 text-[12px] text-text-secondary">{s.projects.map((x) => <li key={x.name}><b>{x.name}</b>: {x.status}</li>)}</ul> : null}
      </Section>

      <div id="review-checks" /><Section title="2. Arithmetic and reconciliation" testId="review-checks" info="Every total re-added, every ratio recomputed, and the proposal reconciled with the bureau (CBRBR) and the stress case it contains.">
        <table className={tableCls}><thead><tr>{["Check", "Result", "Detail"].map((h) => <th key={h} className={thCls}>{h}</th>)}</tr></thead>
          <tbody>{r.checks.map((c) => <tr key={c.check} data-testid="review-check"><td className={cn(tdCls, wrap)}>{c.check}</td>
            <td className={tdCls}><Chip tone={c.result === "Pass" ? "positive" : "negative"}>{c.result}</Chip></td><td className={cn(tdCls, wrap, "text-text-secondary")}>{c.detail}</td></tr>)}</tbody></table>
      </Section>

      <Section title="3. Quality score" testId="review-score" info="Out of 100: completeness, arithmetic, risk identification, structure and mitigants, governance. Below 60 is weak.">
        {/* R10 D7 (G-TILES): one score tile; the sub-scores in one compact table beside it. */}
        <div className="grid gap-3 md:grid-cols-[220px_1fr]">
          <Kpi label="Quality score" value={<>{r.score.total}<span className="text-[14px] text-text-muted"> / 100</span></>} sub={r.score.band} tone={r.score.total >= 60 ? "positive" : "negative"} />
          <div className="min-w-0 overflow-x-auto"><table className={tableCls} data-testid="review-subscores">
            <thead><tr>{r.score.subscores.map((x) => <th key={x.name} className={cn(thCls, "whitespace-normal")}>{x.name}</th>)}</tr></thead>
            <tbody><tr>{r.score.subscores.map((x) => <td key={x.name} className={cn(tdCls, "font-semibold")}>{x.score} / {x.max}</td>)}</tr></tbody></table></div>
        </div>
      </Section>

      <Section title="4. Information gap register" testId="review-gaps" info="What the reviewer needs before deciding. Send as query to RM records the query against the proposal.">
        <table className={tableCls}><thead><tr>{["#", "Information required", "Context", "Reference", ""].map((h) => <th key={h} className={thCls}>{h}</th>)}</tr></thead>
          <tbody>{r.gaps.map((g) => <tr key={g.id} data-testid="review-gap"><td className={tdCls}>{g.id.split("-").pop()}</td><td className={cn(tdCls, wrap)}>{g.item}</td>
            <td className={cn(tdCls, wrap, "text-text-secondary")}>{g.context}</td><td className={tdCls}>{g.ref.replace("CBUAE CRM ", "")}</td>
            <td className={tdCls}>{sent[g.id] ? <Chip tone="positive">{sent[g.id]}</Chip>
              : <SecondaryButton onClick={() => void send(g.id)} data-testid="review-send-query"><Send size={12} /> Send as query to RM</SecondaryButton>}</td></tr>)}</tbody></table>
      </Section>

      <Section title="5. Weakness → mitigant map" testId="review-weak" info="Each weakness found and the mitigant that covers it. Uncovered findings are in red: nothing in the proposal addresses them.">
        <table className={tableCls}><thead><tr>{["Weakness", "Mitigant"].map((h) => <th key={h} className={thCls}>{h}</th>)}</tr></thead>
          <tbody>{r.weaknesses.map((w) => <tr key={w.weakness} data-testid={w.covered ? "review-weak-covered" : "review-weak-uncovered"}>
            <td className={cn(tdCls, wrap, !w.covered && "font-medium text-negative")}>{w.weakness}</td>
            <td className={cn(tdCls, wrap, !w.covered && "text-negative")}>{w.mitigant ?? "Not covered"}</td></tr>)}</tbody></table>
      </Section>

      <Section title="6. Pre-deal analysis" testId="review-predeal"
               info="Relationship RAROC including fees and deposit value (average balances × (FTP credit − profit paid) + flow fees), after 9% corporate tax, against the hurdle in Admin → Deal Desk Parameters; the stressed cash flow against funded lines; the approval route by DOA; the CRO review flag (CBUAE CRM Art 4.9).">
        <KpiRow testId="review-predeal-tiles" tiles={[
          { label: "RAROC with fees and deposits", value: pc(p.raroc.raroc), sub: <>Hurdle <b>{pc(p.raroc.hurdle)}</b> · {p.verdict}</>, tone: p.raroc.clears_hurdle ? "positive" : "negative", testId: "review-raroc" },
          { label: "RAROC without deposits", value: pc(p.raroc_without_deposits.raroc), sub: <>Deposit value <b>{aed(p.raroc.deposit_value)}</b> a year</> },
          { label: "Stressed peak deficit", value: aed(p.stressed_cash_flow.peak_deficit), sub: <>Month {p.stressed_cash_flow.month} · funded lines <b>{aed(p.stressed_cash_flow.funded_lines)}</b></>,
            tone: p.stressed_cash_flow.shortfall > 0 ? "negative" : "positive" },
          { label: "Approval route", value: <span className="text-[15px]" title={p.approval_route.level}>{p.approval_route.level}</span>, sub: <>{aed(p.approval_route.amount_aed_mn)} proposed</> },
        ]} />
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          <table className={tableCls} data-testid="review-debt-capacity"><tbody>
            <tr><td className={tdCls}>Debt capacity, EBITDA-based</td><td className={cn(tdCls, "text-right font-semibold")}>{aed(p.debt_capacity.ebitda_based)}</td></tr>
            <tr><td className={tdCls}>Debt capacity, cash-flow based</td><td className={cn(tdCls, "text-right font-semibold")}>{aed(p.debt_capacity.cash_flow_based)}</td></tr>
          </tbody></table>
          <div className="rounded-lg border border-negative/40 bg-negative-muted px-4 py-3 text-[12px]" data-testid="review-cro">
            <p className="font-semibold text-negative">CRO review required ({p.cro_review.ref.replace("CBUAE CRM ", "")})</p>
            <p className="mt-1 text-text-secondary">{p.cro_review.reason}</p></div>
        </div>
      </Section>

      <Section title="7. Counter-proposals" testId="review-counters" info="Restructurings that address the uncovered weaknesses, each with its RAROC and exposure effect, computed by the same engine.">
        <div className="grid gap-3 md:grid-cols-3">{r.counter_proposals.map((c) => (
          <div key={c.title} className="rounded-lg border border-border bg-surface p-4" data-testid="review-counter">
            <p className="text-[13px] font-semibold text-text-primary">{c.title}</p>
            <p className="mt-1 text-[12px]">RAROC <b>{pc(c.raroc)}</b> ({fmtPp(c.raroc_change)}) · <Chip tone={c.clears_hurdle ? "positive" : "negative"}>{c.clears_hurdle ? "Clears the hurdle" : "Below the hurdle"}</Chip></p>
            <p className="mt-1 text-[12px] text-text-secondary">Limits <b>{aed(c.total_limits)}</b> ({aed(c.exposure_change)} vs ask){c.group_cap ? <> · group cap <b>{aed(c.group_cap)}</b></> : null}</p>
            <ul className="mt-2 list-disc pl-4 text-[12px] text-text-secondary">{c.terms.map((t) => <li key={t}>{t}</li>)}</ul>
          </div>))}</div>
      </Section>

      <Section title="8. Proposed Accepted Risk Watch entry" testId="review-watch" info="The concerns accepted at approval become dated watch items that escalate when they worsen (P4).">
        <p className="text-[13px]"><Chip tone="warning">{r.watch_entry.status}</Chip> Stage <b>{r.watch_entry.stage}</b>. {r.watch_entry.conclusion}</p>
        <p className="mt-1 text-[12px] text-text-secondary">{r.watch_entry.rationale}</p>
        <table className={cn(tableCls, "mt-2")}><thead><tr>{["Watch item", "Due", "Status"].map((h) => <th key={h} className={thCls}>{h}</th>)}</tr></thead>
          <tbody>{r.watch_entry.items.map((w) => <tr key={w.item}><td className={cn(tdCls, wrap)}>{w.item}</td><td className={tdCls}>{w.due}</td><td className={tdCls}>{w.status}</td></tr>)}</tbody></table>
      </Section>

      <Network r={r} />

      <Section title="9. Reviewer opinion" testId="review-opinion-section" info="The opinion in Word: verdict, checks, gaps, mitigants, counter-proposals and the watch entry.">
        <a href={review.opinionUrl(id)}><PrimaryButton><Download size={14} /> Download the reviewer opinion (Word)</PrimaryButton></a>
      </Section>
    </div>
  );
}

const isCaseId = (id: string) => id.startsWith("PRP-");

const fmtPp = (v: number) => `${v > 0 ? "+" : ""}${(v * 100).toFixed(1)}pp`;

export function ProposalReviewPage() {
  const router = useRouter();
  const params = useSearchParams();
  const id = params.get("case") ?? params.get("proposal") ?? "";
  const view = params.get("view") ?? "";
  const [uploaded, setUploaded] = React.useState<Review | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [err, setErr] = React.useState("");
  const r = useLoad(() => (id && isCaseId(id) && view !== "workspace" ? review.get(id) : Promise.resolve(null)), `review:${id}:${view}`);
  const open = (cid: string) => { setUploaded(null); router.replace(`/deal-desk/review?case=${encodeURIComponent(cid)}`, { scroll: false }); };
  const workspace = (cid: string) => { setUploaded(null); router.replace(`/deal-desk/review?case=${encodeURIComponent(cid)}&view=workspace`, { scroll: false }); };
  const isCase = id.startsWith("PRP-");
  const onFile = (f: File | undefined) => {
    if (!f) return;
    setBusy(true); setErr("");
    review.upload(f).then((x) => { setBusy(false); if (x.case_id) open(x.case_id); else setUploaded(x); },
      (e: unknown) => { setBusy(false); setErr(e instanceof Error ? e.message : String(e)); });
  };
  return (
    <div className="space-y-4" data-testid="proposal-review">
      <BackButton fallback={{ href: "/deal-desk", label: "Deal Desk" }} testId="review-back" />
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-text-muted">Deal Desk</p>
          <div className="flex items-center gap-2"><h1 className="text-2xl font-semibold text-text-primary">Proposal review</h1>
            <InfoPopover title="Proposal review">Proposal intelligence reads a credit proposal and returns, in order: the summary, arithmetic checks, a quality score, the information gaps, the weakness → mitigant map, the pre-deal analysis, counter-proposals, a proposed Accepted Risk Watch entry and the reviewer opinion in Word.</InfoPopover></div>
        </div>
        <div className="ml-auto flex gap-2">
          <SecondaryButton onClick={() => router.replace("/deal-desk/review?view=rules", { scroll: false })} data-testid="review-rulebook">Rule book</SecondaryButton>
          <SecondaryButton onClick={() => router.push("/deal-desk/parameters")} data-testid="review-params"><Settings2 size={14} /> Deal Desk Parameters</SecondaryButton>
          <label className="inline-flex h-8 cursor-pointer items-center gap-2 rounded-md bg-accent px-3 text-[12px] font-medium text-accent-contrast" data-testid="review-upload">
            <FileUp size={14} /> {busy ? "Reading…" : "Upload a proposal (.docx or .pdf)"}
            <input type="file" accept=".docx,.pdf" className="hidden" onChange={(e) => onFile(e.target.files?.[0])} /></label>
        </div>
      </div>
      {err ? <p role="alert" className="text-[12px] text-negative">{err}</p> : null}
      {uploaded ? (
        <Section title="Uploaded proposal" testId="review-uploaded" info="The file was read; the amounts found are listed.">
          <p className="text-[13px]">{uploaded.uploaded?.file}: {uploaded.message}</p>
        </Section>) : null}
      {view === "rules" ? (
        <div className="space-y-3">
          <SecondaryButton onClick={() => router.replace("/deal-desk/review", { scroll: false })} data-testid="review-back-list">All proposals</SecondaryButton>
          <ReviewRules />
        </div>
      ) : view === "conditions" ? (
        <div className="space-y-3">
          <SecondaryButton onClick={() => router.replace("/deal-desk/review", { scroll: false })} data-testid="review-back-list">All proposals</SecondaryButton>
          <ConditionsPage />
        </div>
      ) : id && (view === "workspace" || !isCase) ? (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <SecondaryButton onClick={() => router.replace("/deal-desk/review", { scroll: false })} data-testid="review-back-list">All proposals</SecondaryButton>
            {isCase ? <SecondaryButton onClick={() => open(id)} data-testid="review-to-r9">Proposal intelligence</SecondaryButton> : null}
          </div>
          <ReviewWorkspace proposalId={id} />
        </div>
      ) : !id ? (
        <div className="space-y-4"><CaseList onOpen={open} onWorkspace={workspace} /><ReviewSubjects onOpen={workspace} /></div>
      ) : r.error ? <p role="alert" className="text-[12px] text-negative">{r.error}</p>
        : !r.data ? <Skeleton className="h-96 w-full" /> : <ReviewView r={r.data} onBack={() => router.replace("/deal-desk/review", { scroll: false })} onWorkspace={workspace} />}
    </div>
  );
}
