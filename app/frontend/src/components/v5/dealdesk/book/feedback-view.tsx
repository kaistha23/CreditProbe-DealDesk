"use client";

/**
 * PLAN_R12 Session I (I8 part 4): feedback from the Book to origination — sector hurdle overrides proposed from the
 * observed drift (maker-checker), the rating-linked margin ratchet lever and the promise realisation relationship RAROC uses.
 */

import * as React from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { KpiRow } from "@/components/v5/core/kpi-row";
import { cn } from "@/lib/utils";
import { useLoad } from "@/lib/v5/dealdesk";
import { fmt } from "@/lib/v5/format";

import { Chip, PrimaryButton, SecondaryButton, Section, tableCls, tdCls, thCls } from "../kit";
import { bookApi, type HurdleSector } from "./api";

function Propose({ s, onDone }: { s: HurdleSector; onDone: (m: string) => void }) {
  const [reason, setReason] = React.useState("");
  const [err, setErr] = React.useState("");
  return (
    <span className="inline-flex items-center gap-2">
      <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Reason" aria-label={`Reason for ${s.sector}`}
             className="h-7 w-40 rounded-md border border-border bg-background px-2 text-[12px]" data-testid={`book-hurdle-reason-${s.sector}`} />
      <PrimaryButton disabled={!reason.trim() || s.proposed_hurdle == null} data-testid={`book-hurdle-propose-${s.sector}`} onClick={async () => {
        setErr("");
        try { const p = await bookApi.proposeHurdle(s.sector, s.proposed_hurdle as number, reason); onDone(`${p.id}: ${p.sector} hurdle ${fmt.pct(p.proposed_hurdle)} proposed, waiting for a checker`); }
        catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
      }}>Propose</PrimaryButton>
      {err ? <span role="alert" className="text-[11px] text-negative">{err}</span> : null}
    </span>
  );
}

export function FeedbackView() {
  const [nonce, setNonce] = React.useState(0);
  const [msg, setMsg] = React.useState("");
  const [err, setErr] = React.useState("");
  const r = useLoad(() => bookApi.feedback(), `book-feedback-${nonce}`);
  const d = r.data;
  if (r.error) return <p role="alert" className="text-[12px] text-negative">{r.error}</p>;
  if (!d) return <Skeleton className="h-96 w-full" />;
  const done = (m: string) => { setMsg(m); setNonce((n) => n + 1); };
  const rl = d.realisation;
  return (
    <div className="space-y-4" data-testid="book-feedback">
      <KpiRow testId="book-feedback-tiles" tiles={[
        { label: "Promise realisation in use", value: fmt.pct(rl.in_use), sub: <>basis: {rl.basis === "actual" ? "actual delivery" : "flat parameter"}</>,
          info: "The share of committed cross-sell income relationship RAROC counts. Flat = the approved parameter; actual = the realised share of due, measured promises (switch in the relationship parameter table)." },
        { label: "Actual realisation (measured)", value: fmt.pct(rl.actual), sub: <>{fmt.count(rl.promises)} promises due and measured</>,
          tone: rl.actual != null && rl.actual < rl.flat ? "negative" : undefined, info: "Delivered against promised, capped at 100% per promise, weighted by the promised amount." },
        { label: "Margin ratchet", value: `up to ${fmt.bps(d.ratchet.max_bps_per_notch)} per notch`, info: d.ratchet.text },
        { label: "Sectors with a proposed hurdle", value: fmt.count(d.hurdles.sectors.filter((s) => s.proposed_hurdle != null).length) },
      ]} />
      {msg ? <p className="text-[12px] text-positive" data-testid="book-feedback-message">{msg}</p> : null}
      {err ? <p role="alert" className="text-[12px] text-negative">{err}</p> : null}
      <Section title="Sector hurdle overrides from observed drift" testId="book-hurdles" info={d.hurdles.method}>
        <div className="overflow-x-auto">
          <table className={tableCls}>
            <thead><tr>{["Sector", "Seasoned facilities", "EAD", "Lost to migration a year", "Below hurdle now", "Hurdle now", "Proposed", ""].map((h) => <th key={h} className={thCls}>{h}</th>)}</tr></thead>
            <tbody>{d.hurdles.sectors.map((s) => (
              <tr key={s.sector} title={s.text}>
                <td className={cn(tdCls, "font-medium")}>{s.sector}</td><td className={cn(tdCls, "text-right")}>{fmt.count(s.facilities)}</td>
                <td className={cn(tdCls, "text-right")}>{fmt.sar(s.ead_sar_mn)}</td>
                <td className={cn(tdCls, "text-right", s.pd_migration_drift_pa < 0 && "text-negative")}>{fmt.pp(s.pd_migration_drift_pa * 100, { signed: true })}</td>
                <td className={cn(tdCls, "text-right")}>{fmt.pct(s.share_below_hurdle_now)}</td>
                <td className={cn(tdCls, "text-right")}>{fmt.pct(s.current_hurdle)}</td>
                <td className={cn(tdCls, "text-right")}><b>{s.proposed_hurdle != null ? fmt.pct(s.proposed_hurdle) : "—"}</b></td>
                <td className={tdCls}>{s.proposed_hurdle != null ? <Propose s={s} onDone={done} /> : null}</td>
              </tr>))}</tbody>
          </table>
        </div>
      </Section>
      <Section title="Proposals waiting for a checker" testId="book-hurdle-proposals"
               info="Maker-checker: the person who approves must be different from the person who proposed. Approval writes the next version of the returns table (sector hurdle) with the reason.">
        {d.hurdles.proposals.length ? (
          <table className={tableCls}>
            <thead><tr>{["", "Sector", "From", "To", "Maker", "Reason", "Status", ""].map((h, i) => <th key={i} className={thCls}>{h}</th>)}</tr></thead>
            <tbody>{d.hurdles.proposals.map((p) => (
              <tr key={p.id}><td className={tdCls}>{p.id}</td><td className={tdCls}>{p.sector}</td><td className={cn(tdCls, "text-right")}>{fmt.pct(p.current_hurdle)}</td>
                <td className={cn(tdCls, "text-right")}><b>{fmt.pct(p.proposed_hurdle)}</b></td><td className={tdCls}>{p.maker}</td>
                <td className={cn(tdCls, "whitespace-normal")}>{p.reason}</td>
                <td className={tdCls}><Chip tone={p.status === "approved" ? "positive" : p.status === "rejected" ? "negative" : "warning"}>{p.status}{p.checker ? ` by ${p.checker}` : ""}</Chip></td>
                <td className={tdCls}>{p.status === "proposed" ? <span className="inline-flex gap-2">
                  <PrimaryButton data-testid={`book-hurdle-approve-${p.id}`} onClick={async () => { setErr(""); try { const x = await bookApi.decideHurdle(p.id, true); done(`${x.id} approved: returns ${x.returns_version ?? ""}`); } catch (e) { setErr(e instanceof Error ? e.message : String(e)); } }}>Approve</PrimaryButton>
                  <SecondaryButton onClick={async () => { setErr(""); try { const x = await bookApi.decideHurdle(p.id, false); done(`${x.id} rejected`); } catch (e) { setErr(e instanceof Error ? e.message : String(e)); } }}>Reject</SecondaryButton>
                </span> : null}</td></tr>))}</tbody>
          </table>
        ) : <p className="text-[12px] text-text-muted">No proposals yet. Propose a sector hurdle from the table above.</p>}
      </Section>
    </div>
  );
}
