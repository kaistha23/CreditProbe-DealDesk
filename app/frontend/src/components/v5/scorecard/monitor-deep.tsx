"use client";

/**
 * R16 M8: one scorecard's deep dive (opened from a front-page line, a health card or Noor's brief with ?scorecard=).
 * Plain words; every MMSG criterion with its lead metric, limit, trend, since and owner; the root-cause note and the
 * recommended actions with the model-risk tier; tests over time; segment drill; grades; characteristics; overrides;
 * the findings register for this scorecard; the validation history with each conclusion's maker-checker state.
 */

import * as React from "react";
import { FlaskConical, MessageSquare } from "lucide-react";

import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { PlainWords } from "@/components/v5/ui/plain-words";
import { cn } from "@/lib/utils";
import { fmt, useLoad, when } from "@/lib/v5/scorecard";
import { type DeepDive, monitor } from "@/lib/v5/scorecard-monitor";

import { FindingsTable } from "./monitor-register";
import { CRITERION_SHORT, day, fullValidationAsk, person } from "./monitor-model";
import { Sparkline } from "./monitor-front";
import { Chart, InfoTip, Rag } from "./validation-view";

const TH = "px-3 py-1.5 text-left text-[10px] font-semibold uppercase tracking-wide text-text-muted";
const TD = "px-3 py-1.5 align-top";

function H({ children, info, testId }: { children: React.ReactNode; info?: string; testId?: string }) {
  return (
    <div className="flex items-center justify-between gap-2" data-testid={testId}>
      <h3 className="text-[14px] font-semibold text-text-primary">{children}</h3>
      {info ? <InfoTip text={info} /> : null}
    </div>
  );
}

export function MonitorDeepDive({ sid, focus, onAsk, busy }: { sid: string; focus?: string; onAsk: (q: string) => void; busy: boolean }) {
  const [version, setVersion] = React.useState(0);
  const load = useLoad(() => monitor.scorecard(sid), `monitor-${sid}-${version}`);
  const focusRef = React.useRef<HTMLTableRowElement | null>(null);
  React.useEffect(() => { if (load.data && focus) focusRef.current?.scrollIntoView({ block: "center" }); }, [load.data, focus]);
  if (load.error) return <p className="text-sm text-negative" role="alert" data-testid="sm-deep-error">{load.error}</p>;
  if (!load.data) return <div className="space-y-3"><Skeleton className="h-24 w-full" /><Skeleton className="h-64 w-full" /></div>;
  const d: DeepDive = load.data;
  const inv = d.inventory;
  return (
    <div className="space-y-5" data-testid="sm-deep" data-scorecard={d.scorecard_id} data-status={d.overall}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-text-muted">Deep dive · {d.tier} · owner {person(String(inv.model_owner))}</p>
          <h2 className="text-[22px] font-semibold text-text-primary" data-testid="sm-deep-title">{d.name} <span className="font-normal text-text-muted">v{d.version}</span></h2>
          <p className="text-[12px] text-text-secondary">{d.line}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Rag status={d.overall} testId="sm-deep-rag" />
          <button type="button" disabled={busy} onClick={() => onAsk(fullValidationAsk(d.name))} data-testid="sm-deep-validate"
                  className="inline-flex items-center gap-1 rounded-md bg-accent px-3 py-1.5 text-[12px] font-medium text-accent-contrast disabled:opacity-40">
            <FlaskConical size={13} /> Run a full MMSG validation</button>
          <button type="button" disabled={busy} onClick={() => onAsk(`Validate the ${d.name}`)} data-testid="sm-deep-ask"
                  className="inline-flex items-center gap-1 rounded-md border border-border px-3 py-1.5 text-[12px] hover:border-accent disabled:opacity-40">
            <MessageSquare size={13} /> Plan a validation</button>
        </div>
      </div>
      <PlainWords lines={d.plain_words} speak testId="sm-deep-plain-words" source={<span>From {d.sources.join(", ")}</span>} />

      <Card className="space-y-2 p-3" data-testid="sm-criteria">
        <H info="Each MMSG monitoring criterion with its lead metric today. Red and amber lines show since when they have been outside the green band.">MMSG criteria today</H>
        <div className="overflow-x-auto">
          <table className="w-full text-[12px]">
            <thead className="bg-surface-sunken"><tr><th className={TH}>Criterion</th><th className={TH}>Verdict</th><th className={TH}>Lead metric</th><th className={TH}>Value</th>
              <th className={TH}>Limit</th><th className={TH}>Trend</th><th className={TH}>Since</th><th className={TH}>Owner</th></tr></thead>
            <tbody>
              {d.criteria.map((c) => (
                <React.Fragment key={c.criterion}>
                  <tr ref={focus === c.criterion ? focusRef : undefined} data-testid="sm-criterion" data-criterion={c.criterion} data-status={c.status}
                      className={cn("border-t border-border", focus === c.criterion && "bg-accent/5")}>
                    <td className={cn(TD, "font-medium text-text-primary")}>{CRITERION_SHORT[c.criterion]}</td>
                    <td className={TD}><Rag status={c.status} /></td>
                    <td className={TD}>{c.label}</td>
                    <td className={cn(TD, "whitespace-nowrap tabular-nums font-semibold")}>{c.display}</td>
                    <td className={cn(TD, "text-text-muted")}>{c.threshold || "—"}</td>
                    <td className={TD}><Sparkline line={c} /></td>
                    <td className={cn(TD, "whitespace-nowrap")}>{c.since ? day(c.since) : "—"}</td>
                    <td className={TD}>{person(c.owner)}</td>
                  </tr>
                  <tr className="text-text-secondary"><td />
                    <td colSpan={7} className="px-3 pb-2 text-[11.5px]">{c.sentence}{c.also.length ? ` Also: ${c.also.join("; ")}.` : ""}</td></tr>
                </React.Fragment>))}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="grid gap-3 lg:grid-cols-2">
        <Card className="space-y-2 p-3" data-testid="sm-root-cause">
          <H info="Rules over the criteria above, in order: ranking vs level, population shift by characteristic, use outside scope, grades, overrides, cycle.">Root cause</H>
          <ul className="list-disc space-y-1 pl-5 text-[12.5px] text-text-secondary">{d.root_cause.map((r) => <li key={r}>{r}</li>)}</ul>
        </Card>
        <Card className="space-y-2 p-3" data-testid="sm-actions">
          <H info={`Decisions in MMS 4.3.3 terms. Model-risk tier: ${d.tier}. ${d.tier_reason}`}>Recommended actions · {d.tier}</H>
          <ol className="space-y-2 text-[12.5px]">
            {d.actions.map((a, i) => (
              <li key={`${a.decision}-${i}`} className="rounded-md border border-border p-2" data-testid="sm-action" data-decision={a.decision}>
                <p className="font-semibold text-text-primary">{i + 1}. {a.title} <span className="font-normal text-text-muted">· {a.severity} · {a.reference}</span></p>
                <p className="text-text-secondary">{a.why}</p>
                <p className="text-[11px] text-text-muted">Owner {person(a.owner)} · by {day(a.due)}</p>
              </li>))}
          </ol>
        </Card>
      </div>

      <section className="space-y-2" data-testid="sm-charts">
        <H>Tests over time</H>
        <div className="grid gap-3 lg:grid-cols-2">{d.charts.map((c) => <Chart key={c.id} chart={c} />)}</div>
      </section>

      <Card className="space-y-2 p-3" data-testid="sm-segments">
        <H info={`Gini and observed / expected on ${d.segments.window}; PSI at the latest period against the segment's development distribution.`}>
          Segment drill by {d.segments.by.replace(/_/g, " ")}</H>
        <div className="overflow-x-auto">
          <table className="w-full text-[12px]">
            <thead className="bg-surface-sunken"><tr><th className={TH}>Segment</th><th className={TH}>Approved scope</th><th className={cn(TH, "text-right")}>Obs.</th>
              <th className={cn(TH, "text-right")}>Defaults</th><th className={cn(TH, "text-right")}>Gini</th><th className={cn(TH, "text-right")}>Observed</th>
              <th className={cn(TH, "text-right")}>Expected</th><th className={cn(TH, "text-right")}>O / E</th><th className={TH}>Light</th><th className={cn(TH, "text-right")}>Scored now</th>
              <th className={cn(TH, "text-right")}>PSI now</th></tr></thead>
            <tbody>
              {d.segments.rows.map((r) => (
                <tr key={r.segment} className="border-t border-border" data-testid="sm-segment" data-in-scope={r.in_scope}>
                  <td className={cn(TD, "font-medium")}>{r.segment}</td>
                  <td className={TD}>{r.in_scope ? "yes" : <span className="font-semibold text-negative">outside</span>}</td>
                  <td className={cn(TD, "text-right tabular-nums")}>{fmt(r.n ?? null, "int")}</td>
                  <td className={cn(TD, "text-right tabular-nums")}>{fmt(r.defaults ?? null, "int")}</td>
                  <td className={cn(TD, "text-right tabular-nums")}>{fmt(r.gini ?? null, "pct")}</td>
                  <td className={cn(TD, "text-right tabular-nums")}>{fmt(r.observed ?? null, "pct2")}</td>
                  <td className={cn(TD, "text-right tabular-nums")}>{fmt(r.expected ?? null, "pct2")}</td>
                  <td className={cn(TD, "text-right tabular-nums")}>{fmt(r.oe ?? null, "num")}</td>
                  <td className={TD}>{r.oe_status ? <Rag status={r.oe_status} /> : "—"}</td>
                  <td className={cn(TD, "text-right tabular-nums")}>{fmt(r.n_now ?? null, "int")}</td>
                  <td className={cn(TD, "text-right tabular-nums")}>{r.psi === null || r.psi === undefined ? (r.in_scope ? "—" : "no development data") : fmt(r.psi, "num4")}</td>
                </tr>))}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="grid gap-3 lg:grid-cols-2">
        <Card className="space-y-2 p-3" data-testid="sm-grades">
          <H info="Observed default rate against the grade PD on the latest matured window; light = one-sided binomial test.">Calibration by grade</H>
          <table className="w-full text-[12px]">
            <thead className="bg-surface-sunken"><tr><th className={TH}>Grade</th><th className={cn(TH, "text-right")}>Obs.</th><th className={cn(TH, "text-right")}>Observed</th>
              <th className={cn(TH, "text-right")}>Grade PD</th><th className={cn(TH, "text-right")}>O / E</th><th className={TH}>Light</th></tr></thead>
            <tbody>{d.grades.map((g) => (
              <tr key={g.grade} className="border-t border-border" data-testid="sm-grade" data-status={g.status}>
                <td className={TD}>{g.grade}</td><td className={cn(TD, "text-right tabular-nums")}>{fmt(g.n, "int")}</td>
                <td className={cn(TD, "text-right tabular-nums")}>{fmt(g.observed, "pct2")}</td><td className={cn(TD, "text-right tabular-nums")}>{fmt(g.expected, "pct2")}</td>
                <td className={cn(TD, "text-right tabular-nums")}>{fmt(g.oe, "num")}</td><td className={TD}><Rag status={g.status} /></td></tr>))}</tbody>
          </table>
        </Card>
        <Card className="space-y-2 p-3" data-testid="sm-characteristics">
          <H info={`At ${d.characteristics_period}. CSI against development; outside ranges = a value in a bin empty at development; IV on development and on the matured monitoring sample.`}>
            Characteristics</H>
          <div className="max-h-[340px] overflow-auto">
            <table className="w-full text-[12px]">
              <thead className="sticky top-0 bg-surface-sunken"><tr><th className={TH}>Characteristic</th><th className={cn(TH, "text-right")}>CSI</th><th className={cn(TH, "text-right")}>Missing</th>
                <th className={cn(TH, "text-right")}>Outside ranges</th><th className={cn(TH, "text-right")}>IV dev → now</th></tr></thead>
              <tbody>{d.characteristics.map((c) => (
                <tr key={c.variable} className="border-t border-border" data-testid="sm-characteristic" data-status={c.status}>
                  <td className={TD}>{c.label}{c.in_model ? "" : <span className="text-text-muted"> (candidate)</span>}</td>
                  <td className={cn(TD, "text-right tabular-nums", c.status === "red" && "font-semibold text-negative", c.status === "amber" && "text-warning")}>{fmt(c.csi, "num4")}</td>
                  <td className={cn(TD, "text-right tabular-nums")}>{fmt(c.missing_pct, "pct")}</td>
                  <td className={cn(TD, "text-right tabular-nums")}>{fmt(c.unseen_pct, "pct")}</td>
                  <td className={cn(TD, "whitespace-nowrap text-right tabular-nums")}>{c.iv_dev === null ? "—" : `${fmt(c.iv_dev, "num4")}${c.iv_mon === null ? "" : ` → ${fmt(c.iv_mon, "num4")}`}`}</td></tr>))}</tbody>
            </table>
          </div>
        </Card>
      </div>

      {d.override_reasons.length ? (
        <Card className="space-y-2 p-3" data-testid="sm-overrides">
          <H info="Share of the latest period's overrides by reason; observed / expected on matured monitoring overrides with that reason.">Overrides by reason</H>
          <table className="w-full text-[12px]">
            <thead className="bg-surface-sunken"><tr><th className={TH}>Reason</th><th className={cn(TH, "text-right")}>Share</th><th className={cn(TH, "text-right")}>Observed default rate</th>
              <th className={cn(TH, "text-right")}>Expected</th></tr></thead>
            <tbody>{d.override_reasons.map((r) => (
              <tr key={r.reason} className="border-t border-border"><td className={TD}>{r.reason}</td><td className={cn(TD, "text-right tabular-nums")}>{fmt(r.share, "pct")}</td>
                <td className={cn(TD, "text-right tabular-nums")}>{fmt(r.observed, "pct2")}</td><td className={cn(TD, "text-right tabular-nums")}>{fmt(r.expected, "pct2")}</td></tr>))}</tbody>
          </table>
        </Card>) : null}

      <Card className="space-y-2 p-3" data-testid="sm-deep-findings">
        <H info="The findings register for this scorecard: earlier validations and monitoring reports, and every red or amber test of a CreditProbe validation.">Findings register</H>
        <FindingsTable rows={d.findings} onChanged={() => setVersion((n) => n + 1)} compact />
      </Card>

      <Card className="space-y-2 p-3" data-testid="sm-history">
        <H info="Kept as history. A conclusion counts as the independent validation only when a checker has approved it.">Validation history</H>
        <p className="text-[12px] text-text-secondary">Inventory: last full independent validation {String(inv.last_validation_ref)} on {day(String(inv.last_full_validation))};
          approved by {String(inv.approved_by)} on {day(String(inv.approved_on))}; cycle every {String(inv.validation_cycle_months)} months.</p>
        {d.validations.length ? (
          <table className="w-full text-[12px]">
            <thead className="bg-surface-sunken"><tr><th className={TH}>Validation</th><th className={TH}>As of</th><th className={TH}>Verdict</th><th className={TH}>Conclusion</th><th className={TH}>Run</th></tr></thead>
            <tbody>{d.validations.map((v) => (
              <tr key={v.validation_id} className="border-t border-border" data-testid="sm-history-row">
                <td className={TD}><a className="text-accent hover:underline" href={`/scorecard-validation/thread/${v.thread_id}`}>{v.title}</a></td>
                <td className={TD}>{v.as_of}</td><td className={TD}><Rag status={v.overall} /></td>
                <td className={TD}>{v.maker_checker?.state === "approved" ? `Approved: ${v.maker_checker.conclusion?.replace("_", " ")}` :
                  v.maker_checker?.state === "proposed" ? "Waiting for the checker" : v.review.status === "reviewed" ? `Reviewed (single step): ${v.review.conclusion.replace("_", " ")}` : "Not concluded"}</td>
                <td className={TD}>{when(v.created_at)}</td></tr>))}</tbody>
          </table>) : <p className="text-[12px] text-text-muted">No CreditProbe validation of this scorecard yet.</p>}
      </Card>
    </div>
  );
}
