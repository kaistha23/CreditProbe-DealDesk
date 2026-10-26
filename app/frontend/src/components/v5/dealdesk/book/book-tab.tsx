"use client";

/**
 * PLAN_R12 Session I (I7, I8, I29, I31): the **Book** tab of Deal Desk — existing customers.
 *
 * Every approved facility with its monitoring tier, RAROC at origination against now (and why it drifted), Early Warning
 * status, covenants and conditions due, promises against delivery and the renewal date. Filters: going bad, repricing
 * list, promises unmet, tier High, renewals due, covenants and conditions. From a row: raise or lower the tier (with a
 * reason), open the deal, start the renewal (reopens the deal on Proposal) or send it to Early Warning.
 * Views: Facilities · RAROC drift (renamed from Portfolio RAROC at origination) · Feedback to origination.
 *
 * Exported for U's shell: `BookTab` (props: `initialFilter`, `facility`) and, from ./index, `fetchBookCounts`.
 */

import * as React from "react";

import { Borrower360Button, BorrowerNameLink } from "@/components/v5/ui/borrower-360-link"; // R14 U (K11)
import { useRouter } from "next/navigation";

import { Skeleton } from "@/components/ui/skeleton";
import { KpiRow } from "@/components/v5/core/kpi-row";
import { cn } from "@/lib/utils";
import { useLoad } from "@/lib/v5/dealdesk";
import { fmt } from "@/lib/v5/format";

import { RarocDriftView, DriftWaterfall } from "../portfolio-raroc";
import { Chip, Empty, PrimaryButton, SecondaryButton, Section, tableCls, tdCls, thCls } from "../kit";
import { type BookFilter, type BookRow, bookApi, dataDomainsHref, DRIFT_LABELS, FILTERS, type FacilityDetail, type Tier } from "./api";
import { FeedbackView } from "./feedback-view";
import { FinQualityPanel } from "../fin-quality"; // R13 Q: the Book renewal row
import { InfoPopover } from "@/components/ui/info-popover"; // R13 X: notes behind the (i)
import { RenewalAutopilotPanel } from "../../intel/ib"; // R13 IB: Book tools
import { PortfolioToolsMenu } from "@/components/v5/intel/portfolio"; // R13 ID: portfolio tools menu
import { ProposeMonitoringButton } from "../flow-monitoring"; // R14 F (K35)

type View = "facilities" | "drift" | "feedback" | "renewals";
const PAGE = 25;
const MAIN: BookFilter[] = ["going_bad", "repricing", "promises_unmet", "tier_high"];

const tierTone = (t: string) => (t === "High" ? "negative" : t === "Medium" ? "warning" : t === "Standard" ? "positive" : "neutral") as
  "negative" | "warning" | "positive" | "neutral";
const bandTone = (b: string) => (b === "critical" || b === "high" ? "negative" : b === "moderate" ? "warning" : "neutral") as
  "negative" | "warning" | "neutral";

function TierDialog({ row, onDone, onCancel }: { row: BookRow; onDone: (msg: string) => void; onCancel: () => void }) {
  const tiers: Tier[] = ["High", "Medium", "Standard"];
  const [tier, setTier] = React.useState<Tier>(row.tier === "High" ? "Medium" : "High");
  const [reason, setReason] = React.useState("");
  const [err, setErr] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const submit = async () => {
    setBusy(true); setErr("");
    try { onDone((await bookApi.setTier(row.facility_id, tier, reason)).text); } catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
    setBusy(false);
  };
  return (
    <div className="mt-3 rounded-md border border-border bg-surface p-3" data-testid="book-tier-dialog">
      <p className="flex flex-wrap items-center gap-1 text-[12px] text-text-secondary">Monitoring tier for <b>{row.borrower_name}</b> ({row.facility_id}): now <b>{row.tier}</b>.
        <InfoPopover title="Monitoring tiers">High = quarterly review and tighter Early Warning thresholds; Medium = semi-annual; Standard = annual.</InfoPopover></p>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        {tiers.map((t) => (
          <button key={t} type="button" onClick={() => setTier(t)} aria-pressed={tier === t} data-testid={`book-tier-${t.toLowerCase()}`}
                  className={cn("h-7 rounded-full border px-3 text-[12px]", tier === t ? "border-accent bg-accent-muted text-accent" : "border-border text-text-secondary")}>{t}</button>
        ))}
        <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Reason (required, logged)" aria-label="Reason"
               data-testid="book-tier-reason" className="h-8 min-w-[260px] flex-1 rounded-md border border-border bg-background px-2 text-[12px]" />
        <PrimaryButton disabled={!reason.trim() || busy || tier === row.tier} onClick={submit} data-testid="book-tier-save">Save tier</PrimaryButton>
        <SecondaryButton onClick={onCancel}>Cancel</SecondaryButton>
      </div>
      {err ? <p role="alert" className="mt-2 text-[12px] text-negative">{err}</p> : null}
    </div>
  );
}

function ReasonAction({ label, placeholder, testId, run, onDone }: {
  label: string; placeholder: string; testId: string; run: (reason: string) => Promise<{ text: string }>; onDone: (msg: string) => void;
}) {
  const [open, setOpen] = React.useState(false);
  const [reason, setReason] = React.useState("");
  const [err, setErr] = React.useState("");
  if (!open) return <SecondaryButton onClick={() => setOpen(true)} data-testid={testId}>{label}</SecondaryButton>;
  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder={placeholder} aria-label={placeholder}
             data-testid={`${testId}-reason`} className="h-8 min-w-[220px] rounded-md border border-border bg-background px-2 text-[12px]" />
      <PrimaryButton disabled={!reason.trim()} data-testid={`${testId}-go`} onClick={async () => {
        setErr("");
        try { onDone((await run(reason)).text); setOpen(false); } catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
      }}>{label}</PrimaryButton>
      {err ? <span role="alert" className="text-[12px] text-negative">{err}</span> : null}
    </span>
  );
}

function Detail({ fid, onChanged }: { fid: string; onChanged: (msg: string) => void }) {
  const router = useRouter();
  const [nonce, setNonce] = React.useState(0);
  const r = useLoad(() => bookApi.facility(fid), `book-facility-${fid}-${nonce}`);
  const [tierOpen, setTierOpen] = React.useState(false);
  const [msg, setMsg] = React.useState("");
  const [err, setErr] = React.useState("");
  const d: FacilityDetail | null = r.data;
  if (r.error) return <p role="alert" className="text-[12px] text-negative">{r.error}</p>;
  if (!d) return <Skeleton className="h-64 w-full" />;
  const f = d.facility;
  const done = (m: string) => { setMsg(m); setTierOpen(false); setNonce((n) => n + 1); onChanged(m); };
  const rp = d.repricing;
  return (
    <div className="space-y-3" data-testid="book-detail">
      <div className="flex flex-wrap items-center gap-2" data-testid="book-actions">
        <PrimaryButton onClick={() => setTierOpen((o) => !o)} data-testid="book-action-tier">Raise or lower tier</PrimaryButton>
        <ProposeMonitoringButton testId="book-action-monitor" subject={{ obligorId: f.borrower_id, obligorName: f.borrower_name, facilityRef: f.facility_id,
                                 proposalId: f.proposal_id ?? null, source: "book" }} />{/* R14 F (K35) */}
        <SecondaryButton disabled={!f.proposal_id} title={f.proposal_id ? undefined : "No Deal Desk file for this facility"}
                         onClick={() => f.proposal_id && router.push(`/deal-desk/${f.proposal_id}`)} data-testid="book-action-open">Open deal</SecondaryButton>
        <SecondaryButton data-testid="book-action-renewal" onClick={async () => {
          setErr("");
          try { const x = await bookApi.startRenewal(f.facility_id); done(x.text); router.push(x.url); } catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
        }}>Start renewal</SecondaryButton>
        <ReasonAction label="Send to Early Warning" placeholder="Why Early Warning should watch it" testId="book-action-ews"
                      run={(reason) => bookApi.sendToEws(f.facility_id, reason)} onDone={done} />
      </div>
      {tierOpen ? <TierDialog row={f} onDone={done} onCancel={() => setTierOpen(false)} /> : null}
      {msg ? <p className="text-[12px] text-positive" data-testid="book-action-message">{msg}</p> : null}
      {err ? <p role="alert" className="text-[12px] text-negative">{err}</p> : null}
      <div className="grid gap-3 xl:grid-cols-2">
        <Section title="Why RAROC moved" info={<>One-year RAROC at origination ({f.orig_date}, {f.orig_rating}) against now ({f.rating_now ?? "—"}), one driver at a time. LGD at origination {fmt.pct(d.inputs.lgd_orig)} → now {fmt.pct(d.inputs.lgd_now)}; PD {fmt.pct(d.inputs.orig_pd_pct, { scale: "points" })} → {fmt.pct(d.inputs.pd_now_pct, { scale: "points" })}; FTP at origination {fmt.pct(d.inputs.ftp_orig_pct, { scale: "points" })}.</>}>
          {d.waterfall.length ? (
            <DriftWaterfall title={`RAROC drift ${f.facility_id}`} height={240} start={d.waterfall[0].value} end={d.waterfall[d.waterfall.length - 1].value}
                            steps={d.waterfall.slice(1, -1).map((w) => ({ label: w.step, value: w.value }))} />
          ) : <Empty>RAROC drift is not published for this deal yet.</Empty>}
          <p className="mt-1 text-[11px] text-text-muted" data-testid="book-drift-sources">Source: {d.drift_source}. Open in Data Domains:{" "}
            {d.waterfall.filter((w) => w.source).map((w, i) => (
              <React.Fragment key={w.step}>{i ? " · " : ""}<a className="underline hover:text-text-secondary" href={dataDomainsHref(w.source!)}
                title={`${w.source!.domain}.${w.source!.relation} ${w.source!.column ?? ""}`}>{w.step}</a></React.Fragment>))}
          </p>
        </Section>
        <Section title="Renewal: reprice or restructure" info={rp.method}>
          {rp.action === "None" ? <p className="text-[12px] text-text-secondary">{f.raroc_now == null ? "No RAROC published for this deal yet: no repricing computed." : <>Clears its {fmt.pct(f.hurdle)} hurdle now: no repricing needed at the {f.renewal_kind.toLowerCase()} on {f.renewal_date}.</>}</p> : (
            <div className="space-y-1 text-[12px]">
              <p><Chip tone={rp.action === "Reprice" ? "warning" : "negative"}>{rp.action}</Chip> <span className="ml-1">{rp.text}.</span></p>
              <p className="text-text-secondary">Recovers {fmt.pp(rp.recoverable_raroc * 100, { signed: true })} of RAROC{rp.recoverable_sva_sar_mn != null ? <> ({fmt.sar(rp.recoverable_sva_sar_mn)} a year above the cost of capital)</> : null}, capped at the hurdle. {f.renewal_kind} on <b>{f.renewal_date}</b>.</p>
              {rp.optimiser && !rp.text.includes("optimiser") ? (rp.optimiser.available && rp.optimiser.feasible
                ? <p data-testid="book-optimiser">Deal Desk optimiser on the deal file ({rp.optimiser.proposal_id}): {rp.optimiser.label}{(rp.optimiser.changes ?? []).length ? <>: {(rp.optimiser.changes ?? []).map((c) => `${c.field.replace(/_/g, " ")} ${c.ask ?? "—"} → ${c.value ?? "—"}${c.unit ? ` ${c.unit}` : ""}`).join(", ")}</> : null}; margin {fmt.bps(rp.optimiser.terms?.margin_bps ?? null)}, lifetime RAROC {fmt.pct(rp.optimiser.lifetime_raroc ?? null)}.</p>
                : <p className="text-text-muted" data-testid="book-optimiser">Deal Desk optimiser on {rp.optimiser.proposal_id}: {rp.optimiser.available ? "no feasible structure; " + (rp.optimiser.relaxation ?? []).map((x) => x.label ?? x.lever).join(", ") : rp.optimiser.why}.</p>) : null}
            </div>)}
        </Section>
        <FinQualityPanel facilityId={f.facility_id} compact />
        <Section title="Promises against delivery" info="Measured on the deposits data (trailing 12 months of credit turnover, 3-month average balance, payroll months).">
          {d.promises.length ? (
            <table className={tableCls}><thead><tr>{["Promise", "Promised", "Delivered", "Share", "Status"].map((h) => <th key={h} className={thCls}>{h}</th>)}</tr></thead>
              <tbody>{d.promises.map((p) => <tr key={p.promise_id}><td className={cn(tdCls, "whitespace-normal")}>{p.description}</td>
                <td className={cn(tdCls, "text-right")}>{p.unit.startsWith("SAR") ? fmt.sar(p.promised_value) : fmt.num(p.promised_value)}</td>
                <td className={cn(tdCls, "text-right")}>{p.unit.startsWith("SAR") ? fmt.sar(p.measured_value) : fmt.num(p.measured_value)}</td>
                <td className={cn(tdCls, "text-right")}>{fmt.pct(p.realisation)}</td>
                <td className={tdCls}><Chip tone={p.status === "Met" ? "positive" : p.status === "Unmet" ? "negative" : "warning"}>{p.status}</Chip></td></tr>)}</tbody></table>
          ) : <Empty>No promises recorded for this customer.</Empty>}
        </Section>
        <Section title="Covenants, conditions and Early Warning" info="Covenants at the last Early Warning test; conditions from the approval (Deal Desk conditions).">
          <div className="space-y-2 text-[12px]">
            <p>Early Warning <Chip tone={bandTone(f.ews_band)}>{f.ews_band}</Chip> score {fmt.count(f.ews_score)}{f.watch_status ? <> · {f.watch_status}</> : null}{f.ews_reasons ? <>: {f.ews_reasons}</> : null}</p>
            {d.covenants.length ? (
              <table className={tableCls}><thead><tr>{["Covenant", "Threshold", "Observed", "Headroom", "Status"].map((h) => <th key={h} className={thCls}>{h}</th>)}</tr></thead>
                <tbody>{d.covenants.map((c) => <tr key={c.covenant_id}><td className={tdCls}>{c.covenant_type}</td><td className={cn(tdCls, "text-right")}>{fmt.ratio(c.threshold_value)}</td>
                  <td className={cn(tdCls, "text-right")}>{fmt.ratio(c.observed_value)}</td><td className={cn(tdCls, "text-right", c.headroom_pct < 0 && "text-negative")}>{fmt.pct(c.headroom_pct, { scale: "points" })}</td>
                  <td className={tdCls}>{c.test_status}</td></tr>)}</tbody></table>
            ) : <p className="text-text-muted">No covenants tested on this facility.</p>}
            <p>Next covenant test {f.covenant_next_test}. Conditions open {f.conditions_open}, due this month {f.conditions_due}, overdue {f.conditions_overdue}.</p>
            {d.plan_history.length ? <p className="text-text-secondary">Monitoring plan: {d.plan_history.length} version(s); last set by {f.plan_set_by ?? "—"} on {f.plan_set_on ?? "—"}{f.plan_reason ? `: ${f.plan_reason}` : ""}.</p> : null}
          </div>
        </Section>
      </div>
      {d.pending.length ? <p className="text-[11px] text-text-muted">Not in Data Domains yet: {d.pending.join(", ")}.</p> : null}
    </div>
  );
}

function Rows({ rows, open, setOpen, filter }: { rows: BookRow[]; open: string; setOpen: (f: string) => void; filter: BookFilter }) {
  const head = ["Customer and facility", "Tier", "RAROC then → now", "Main driver", "EWS", "Covenants", "Promises", "Renewal",
    ...(filter === "repricing" ? ["Recoverable"] : [])];
  return (
    <table className={cn(tableCls, "table-fixed")} data-testid="book-table">
      <colgroup><col className={filter === "repricing" ? "w-[24%]" : "w-[26%]"} /><col className="w-[8%]" /><col className="w-[13%]" /><col className="w-[11%]" /><col className="w-[8%]" />
        <col className="w-[9%]" /><col className="w-[11%]" /><col className="w-[10%]" />{filter === "repricing" ? <col className="w-[10%]" /> : null}</colgroup>
      <thead><tr>{head.map((h) => <th key={h} className={cn(thCls, "whitespace-normal")}>{h}</th>)}</tr></thead>
      <tbody>{rows.map((r) => {
        const why = filter === "repricing" ? r.action_text : r.reasons.join("; ");
        const toggle = () => setOpen(open === r.facility_id ? "" : r.facility_id);
        return (
          <React.Fragment key={r.facility_id}>
            <tr className={cn("cursor-pointer hover:bg-surface-hover", open === r.facility_id && "bg-surface-hover")} onClick={toggle}
                data-testid="book-row" aria-expanded={open === r.facility_id}>
              <td className={cn(tdCls, "truncate border-b-0 pb-0 font-medium")} title={r.borrower_name}>
                <span className="flex items-center gap-1.5"><BorrowerNameLink customerId={r.borrower_id} name={r.borrower_name} from="book" className="min-w-0 truncate" />
                  <Borrower360Button customerId={r.borrower_id} from="book" label="360" className="ml-auto h-5 px-1.5 text-[10.5px]" />{/* R14 U (K11) */}
                  <ProposeMonitoringButton compact testId="book-row-monitor" subject={{ obligorId: r.borrower_id, obligorName: r.borrower_name, facilityRef: r.facility_id,
                    proposalId: r.proposal_id ?? null,
                    source: filter.includes("going_bad") ? "going_bad" : filter.includes("renewals") ? "renewals" : "book", reason: why }} />{/* R14 F (K35) */}</span>
                <div className="truncate text-[11px] font-normal text-text-muted">{r.source === "deal_desk" ? "Deal Desk deal · " : ""}{r.facility_id} · {fmt.sar(r.limit_sar_mn)} · {r.product_type.replace(/_/g, " ")}{r.sector ? ` · ${r.sector}` : ""}</div></td>
              <td className={cn(tdCls, "border-b-0 pb-0")}><Chip tone={tierTone(r.tier)}>{r.tier}</Chip></td>
              <td className={cn(tdCls, "border-b-0 pb-0")}>{r.raroc_now == null && !r.defaulted ? <span className="text-text-muted">not published</span> : <>{fmt.pct(r.raroc_orig)} → <b className={cn(r.raroc_now != null && r.hurdle != null && r.raroc_now < r.hurdle && "text-negative")}>{r.defaulted ? "in default" : fmt.pct(r.raroc_now)}</b></>}
                <div className="text-[11px] text-text-muted">hurdle {fmt.pct(r.hurdle)}</div></td>
              <td className={cn(tdCls, "truncate border-b-0 pb-0")}>{r.defaulted ? "—" : DRIFT_LABELS[r.main_driver] ?? r.main_driver}
                <div className="text-[11px] text-text-muted">{r.rating_now ? `${r.orig_rating} → ${r.rating_now}` : r.orig_rating}</div></td>
              <td className={cn(tdCls, "border-b-0 pb-0")}><Chip tone={bandTone(r.ews_band)}>{r.ews_band}</Chip></td>
              <td className={cn(tdCls, "border-b-0 pb-0")}>{r.covenants_breached ? <span className="text-negative">{r.covenants_breached} breached</span> : r.covenants ? `${r.covenants} tested` : "none"}
                {r.conditions_due ? <div className="whitespace-normal text-[11px] leading-4 text-warning">{r.conditions_due} condition{r.conditions_due > 1 ? "s" : ""} due</div> : null}</td>
              <td className={cn(tdCls, "border-b-0 pb-0")}>{r.promise_status ? <Chip tone={r.promise_status === "Met" ? "positive" : r.promise_status === "Unmet" ? "negative" : "warning"}>{r.promise_status}{r.promise_realisation != null ? ` ${fmt.pct(r.promise_realisation, { dp: 1 })}` : ""}</Chip> : "—"}</td>
              <td className={cn(tdCls, "border-b-0 pb-0")}>{r.renewal_date}<div className="text-[11px] text-text-muted">{r.renewal_kind}</div></td>
              {filter === "repricing" ? <td className={cn(tdCls, "border-b-0 pb-0 text-right")}>{fmt.pp(r.recoverable_raroc * 100, { signed: true })}</td> : null}
            </tr>
            <tr className={cn("cursor-pointer", open === r.facility_id && "bg-surface-hover")} onClick={toggle}>
              <td colSpan={head.length} className="border-b border-border/60 px-2 pb-2 pt-0.5 text-[11px] leading-4 text-text-secondary" data-testid="book-row-why">
                {why ? <>{filter === "repricing" ? <b className="font-medium">{r.action}: </b> : <span className="text-text-muted">Why listed: </span>}{why}</> : null}
              </td>
            </tr>
            {open === r.facility_id ? <tr><td colSpan={head.length} className="border-b border-border p-3"><Detail fid={r.facility_id} onChanged={() => undefined} /></td></tr> : null}
          </React.Fragment>
        );
      })}</tbody>
    </table>
  );
}

const isFilter = (x: string | undefined): x is BookFilter => FILTERS.some((f) => f.key === x);
/** The landing cards' filter words (U's shell: going-bad, renewals, conditions …) onto the Book's filters. */
const ALIAS: Record<string, BookFilter> = { "going-bad": "going_bad", renewals: "renewals_due", "renewals-due": "renewals_due",
  conditions: "conditions_due", covenants: "conditions_due", "promises-unmet": "promises_unmet", "tier-high": "tier_high", high: "tier_high" };
const toFilter = (x: string | undefined): BookFilter | undefined => (isFilter(x) ? x : x ? ALIAS[x] : undefined);

/** `filter` (U's slot prop, from ?filter=) or `initialFilter` picks the list; `view=drift|feedback` opens those views. */
export function BookTab({ initialFilter, filter: given, facility = "", view: initialView }: {
  initialFilter?: BookFilter; filter?: string; facility?: string; view?: string;
}) {
  const start: BookFilter = toFilter(given) ?? initialFilter ?? (facility ? "all" : "going_bad");
  const [view, setView] = React.useState<View>(initialView === "drift" || initialView === "feedback" ? initialView : "facilities");
  const [filter, setFilter] = React.useState<BookFilter>(start);
  const [q, setQ] = React.useState(facility);
  const [sector, setSector] = React.useState("");
  const [offset, setOffset] = React.useState(0);
  const [open, setOpen] = React.useState(facility);
  const [nonce, setNonce] = React.useState(0);
  const counts = useLoad(() => bookApi.counts(), `book-counts-${nonce}`);
  const list = useLoad(() => bookApi.list({ filter, q, sector, limit: PAGE, offset }), `book-${filter}-${q}-${sector}-${offset}-${nonce}`);
  const c = counts.data;
  const d = list.data;
  const pick = (f: BookFilter) => { setFilter(f); setOffset(0); setOpen(""); };
  return (
    <div className="space-y-4" data-testid="book-tab">
      <div className="flex flex-wrap items-center gap-2" role="tablist" aria-label="Book views">
        {([["facilities", "Facilities"], ["drift", "RAROC drift"], ["feedback", "Feedback to origination"]] as const).map(([k, l]) => (
          <button key={k} type="button" role="tab" aria-selected={view === k} onClick={() => setView(k)} data-testid={`book-view-${k}`}
                  className={cn("h-8 rounded-md border px-3 text-[12px] font-medium", view === k ? "border-accent bg-accent-muted text-accent" : "border-border text-text-secondary hover:bg-surface-hover")}>{l}</button>
        ))}
        {c ? <span className="ml-auto text-[11px] text-text-muted">Book as of {c.as_of}{c.defaulted ? ` · ${fmt.count(c.defaulted)} defaulted facilities in workout` : ""}</span> : null}
        {/* R13 IB + ID, one Tools menu (M): Renewal autopilot, then the portfolio tools. */}
        <span className={c ? "" : "ml-auto"}><PortfolioToolsMenu menu="book" label="Tools" extra={[{ key: "renewals", title: "Renewal autopilot",
          question: "Renewals due in 90 days, prepared: clean on one page, exceptions with the full paper", onPick: () => setView("renewals") }]} /></span>
      </div>
      {view === "renewals" ? <RenewalAutopilotPanel onClose={() => setView("facilities")} /> : null}
      {view === "drift" ? <RarocDriftView /> : null}
      {view === "feedback" ? <FeedbackView /> : null}
      {view === "facilities" ? (<>
        {counts.error ? <p role="alert" className="text-[12px] text-negative">{counts.error}</p> : null}
        {c ? (
          <KpiRow testId="book-filters" tiles={FILTERS.filter((x) => MAIN.includes(x.key)).map((x) => ({
            label: x.label, value: fmt.count(c[x.key]), active: filter === x.key, onClick: () => pick(x.key), testId: `book-filter-${x.key}`,
            tone: (x.key === "going_bad" || x.key === "promises_unmet") && c[x.key] > 0 ? "negative" : undefined,
            sub: x.key === "going_bad" ? <>{fmt.sar(c.going_bad_ead_sar_mn)} EAD</> : x.key === "repricing" ? <>renewal in 3–6 months</> : undefined,
          }))} />
        ) : <Skeleton className="h-20 w-full" />}
        {c ? (
          <div className="flex flex-wrap items-center gap-2 text-[12px]" data-testid="book-more-filters">
            <span className="text-text-muted">Also:</span>
            {FILTERS.filter((x) => !MAIN.includes(x.key)).map((x) => (
              <button key={x.key} type="button" title={x.info} onClick={() => pick(x.key)} aria-pressed={filter === x.key} data-testid={`book-filter-${x.key}`}
                      className={cn("h-7 rounded-full border px-3", filter === x.key ? "border-accent bg-accent-muted text-accent" : "border-border text-text-secondary hover:bg-surface-hover")}>
                {x.label} <b className="tabular-nums">{fmt.count(c[x.key])}</b>{x.key === "renewals_due" ? <span className="text-text-muted"> · {fmt.count(c.renewals_due_repricing)} below hurdle</span> : null}
              </button>))}
          </div>) : null}
        <Section title={FILTERS.find((x) => x.key === filter)?.label ?? "Book"} testId="book-list" info={FILTERS.find((x) => x.key === filter)?.info}
                 action={<>
                   <input value={q} onChange={(e) => { setQ(e.target.value); setOffset(0); }} placeholder="Customer or facility" aria-label="Search the Book"
                          data-testid="book-search" className="h-8 w-48 rounded-md border border-border bg-background px-2 text-[12px]" />
                   <select value={sector} onChange={(e) => { setSector(e.target.value); setOffset(0); }} aria-label="Sector" data-testid="book-sector"
                           className="h-8 rounded-md border border-border bg-background px-2 text-[12px]">
                     <option value="">All sectors</option>{(d?.sectors ?? []).map((s) => <option key={s} value={s}>{s}</option>)}
                   </select>
                 </>}>
          {list.error ? <p role="alert" className="text-[12px] text-negative">{list.error}</p> : null}
          {!d && !list.error ? <Skeleton className="h-64 w-full" /> : null}
          {d ? (<>
            <p className="mb-2 text-[12px] text-text-secondary" title="Click a row for why it drifted, its promises and covenants, and the actions."><b>{fmt.count(d.total)}</b> facilities, {fmt.sar(d.ead_sar_mn)} EAD</p>
            {d.rows.length ? <Rows rows={d.rows} open={open} setOpen={setOpen} filter={filter} /> : <Empty>No facility on this list.</Empty>}
            <div className="mt-2 flex items-center gap-2">
              <SecondaryButton disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))} data-testid="book-prev">Previous</SecondaryButton>
              <span className="text-[12px] text-text-muted">{d.total ? `${offset + 1}–${Math.min(offset + PAGE, d.total)} of ${fmt.count(d.total)}` : ""}</span>
              <SecondaryButton disabled={offset + PAGE >= d.total} onClick={() => setOffset(offset + PAGE)} data-testid="book-next">Next</SecondaryButton>
              <SecondaryButton className="ml-auto" onClick={() => setNonce((n) => n + 1)} data-testid="book-refresh">Refresh</SecondaryButton>
            </div>
            {d.pending.length ? <p className="mt-2 text-[11px] text-text-muted" data-testid="book-pending">Not in Data Domains yet: {d.pending.join(", ")}.</p> : null}
            <p className="mt-1 text-[11px] text-text-muted" data-testid="book-sources">Sources (open in Data Domains):{" "}
              {d.sources.filter((s, i, a) => a.findIndex((x) => x.domain === s.domain && x.relation === s.relation) === i).map((s, i) => (
                <React.Fragment key={`${s.domain}.${s.relation}`}>{i ? ", " : ""}<a className="underline hover:text-text-secondary" href={dataDomainsHref({ domain: s.domain, relation: s.relation })}>{s.domain}.{s.relation}</a></React.Fragment>))}.</p>
          </>) : null}
        </Section>
      </>) : null}
    </div>
  );
}
