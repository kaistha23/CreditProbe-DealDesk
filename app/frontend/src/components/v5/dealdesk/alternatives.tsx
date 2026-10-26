"use client";

/**
 * PLAN_R5 D4: alternative structures that clear the hurdle and the minimum change on each single lever.
 *
 * Each card shows the changed terms (highlighted), lifetime RAROC, SVA, the approval level and *why it works*:
 * the lever contribution bars (Shapley values over the changed levers, so they add up to the RAROC gain).
 * Every figure is an engine result (`POST /optimize` carries `alternatives` and `single_lever`).
 */

import * as React from "react";

import { Plot } from "@/components/v5/ews/plot";
import { cn } from "@/lib/utils";
import { type Alternative, type SingleLever, type Terms, leverRead, money, rate } from "@/lib/v5/dealdesk";
import { fmt } from "@/lib/v5/format";

import { C } from "./charts";
import { Chip, Section, tableCls, tdCls, thCls } from "./kit";

export const SHORT: Record<string, string> = {
  margin_bps: "Margin", upfront_fee_bps: "Upfront fee", commitment_fee_bps: "Commitment fee", commission_bps: "Commission",
  prepayment_fee_bps: "Prepayment fee", tenor_years: "Tenor", grace_years: "Grace", amortisation: "Amortisation", balloon_pct: "Balloon",
  amount: "Amount", hold_pct: "Hold level", facility_type: "Facility type", funded_share_pct: "Funded share", structure: "Structure",
  rate_type: "Rate", cash_margin_pct: "Cash margin", collateral_ids: "Collateral", guarantee_id: "Guarantee", guarantee_coverage_pct: "Guarantee cover",
  insurance_cover_pct: "Credit insurance", receivables_assignment_pct: "Assigned receivables", covenant_package: "Covenant package",
  covenant_items: "Covenants", review_cycle_months: "Review cycle", cross_sell: "Cross-sell",
};
const short = (k: string, fallback: string) => SHORT[k] ?? fallback;

function ContributionBars({ a, testId }: { a: Alternative; testId: string }) {
  const rows = [...a.contributions].reverse().map((c) => ({ ...c, label: short(c.lever, c.label) }));
  return (
    <Plot testId={testId} filename="deal-desk-lever-contributions" height={Math.max(110, 40 + rows.length * 26)}
          ariaLabel="Contribution of each changed lever to the RAROC gain"
          data={[{ type: "bar", orientation: "h", y: rows.map((c) => c.label), x: rows.map((c) => c.raroc_pts),
                   marker: { color: rows.map((c) => (c.raroc_pts >= 0 ? C.up : C.down)) },
                   text: rows.map((c) => fmt.pct(c.raroc_pts, { signed: true })), textposition: "auto",
                   hovertemplate: "%{y}<br>%{text} RAROC<extra></extra>" }]}
          layout={{ margin: { l: 112, r: 12, t: 6, b: 24 }, xaxis: { tickformat: ".1%", zeroline: true }, yaxis: { automargin: true }, showlegend: false }} />
  );
}

export function AlternativeCards({ alts, ccy, base, onUse, picked }: {
  alts: Alternative[]; ccy: string; base: { lifetime_raroc: number; sva: number }; onUse: (t: Terms, label: string) => void; picked: string;
}) {
  if (!alts.length) return null;
  return (
    <Section title="Alternative structures that clear the hurdle" testId="dealdesk-alternatives"
             info="Each structure mixes levers from different groups and is closed by the smallest move of one lever. The bars show why it works: each changed lever's share of the RAROC gain over the ask (they add up to the gain).">
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {alts.map((a, i) => {
          const slug = a.label.toLowerCase().replace(/\W+/g, "-");
          return (
            <div key={`${a.label}-${i}`} data-testid={`dealdesk-alt-${slug}`}
                 className={cn("flex flex-col rounded-lg border bg-surface p-4", picked === a.label ? "border-accent ring-1 ring-accent" : "border-border")}>
              <p className="text-[13px] font-semibold text-text-primary">{a.label}</p>
              <div className="mt-2 flex items-baseline gap-2">
                <p className="text-[20px] font-semibold tabular-nums text-positive" data-testid={`dealdesk-alt-${slug}-raroc`}>{rate(a.metrics.lifetime_raroc)}</p>
                <p className="text-[12px] tabular-nums text-text-muted">from {rate(base.lifetime_raroc)}</p></div>
              <p className="text-[12px] tabular-nums text-text-secondary">SVA {money(a.metrics.sva)} · {a.approval.level}</p>
              {a.soft_breaches.length ? <div className="mt-1"><Chip tone="warning">{a.soft_breaches.length} soft breach{a.soft_breaches.length > 1 ? "es" : ""}</Chip></div> : null}
              <table className="mt-3 w-full text-[12px]" data-testid={`dealdesk-alt-${slug}-changes`}>
                <tbody>{a.changes.filter((c) => !(c.field === "guarantee_coverage_pct" && a.changes.some((x) => x.field === "guarantee_id") && false)).map((c) => (
                  <tr key={c.field} data-changed="true">
                    <td className="py-0.5 pr-2 text-text-muted">{short(c.field, c.label)}</td>
                    <td className="py-0.5 text-right tabular-nums"><span className="text-text-muted line-through">{leverRead(c.field, c.ask, ccy)}</span>{" "}
                      <span className="rounded bg-accent-muted px-1 font-semibold text-accent">{leverRead(c.field, c.value, ccy)}</span></td>
                  </tr>))}</tbody>
              </table>
              <p className="mt-3 text-[11px] font-medium uppercase tracking-[0.08em] text-text-muted">Why it works</p>
              <ContributionBars a={a} testId={`dealdesk-alt-${slug}-why`} />
              <button type="button" onClick={() => onUse(a.terms, a.label)} data-testid={`dealdesk-alt-${slug}-use`}
                      className="mt-auto inline-flex h-8 items-center justify-center rounded-md border border-border text-[12px] text-text-secondary hover:border-accent hover:text-accent">
                Load in the term panel</button>
            </div>);
        })}
      </div>
    </Section>
  );
}

export function SingleLeverTable({ rows, ccy, onUse }: { rows: SingleLever[]; ccy: string; onUse: (lever: SingleLever) => void }) {
  if (!rows.length) return null;
  const sorted = [...rows].sort((a, b) => Number(b.clears_alone) - Number(a.clears_alone));
  return (
    <Section title="Minimum change on one lever" testId="dealdesk-single-lever"
             info="For each lever alone, the smallest move from the ask that clears the hurdle without breaching a hard limit, inside its market and policy bounds. A lever that cannot do it alone says so.">
      <div className="overflow-auto">
        <table className={tableCls}>
          <thead><tr><th className={thCls}>Lever</th><th className={thCls}>Group</th><th className={cn(thCls, "text-right")}>Now</th>
            <th className={cn(thCls, "text-right")}>Clears at</th><th className={cn(thCls, "text-right")}>Lifetime RAROC</th><th className={thCls}>Approval</th><th className={thCls} /></tr></thead>
          <tbody>{sorted.map((r) => (
            <tr key={`${r.lever}-${r.guarantee_id ?? ""}`} data-testid={`dealdesk-single-${r.lever}`}>
              <td className={tdCls}>{r.label}{r.note && r.clears_alone ? <span className="ml-1 text-text-muted">· {r.note}</span> : null}</td>
              <td className={cn(tdCls, "text-text-muted")}>{r.group}</td>
              <td className={cn(tdCls, "text-right tabular-nums")}>{leverRead(r.lever, r.from, ccy)}</td>
              <td className={cn(tdCls, "text-right tabular-nums")}>{r.clears_alone
                ? <span className="font-semibold text-accent">{leverRead(r.lever, r.to, ccy)}</span>
                : <span className="text-text-muted" title={r.note}>Not alone</span>}</td>
              <td className={cn(tdCls, "text-right tabular-nums")}>{r.clears_alone ? rate(r.lifetime_raroc) : "–"}</td>
              <td className={tdCls}>{r.approval ?? "–"}</td>
              <td className={tdCls}>{r.clears_alone ? <button type="button" onClick={() => onUse(r)} data-testid={`dealdesk-single-${r.lever}-use`}
                                                             className="text-[12px] text-accent hover:underline">Load</button> : null}</td>
            </tr>))}</tbody>
        </table>
      </div>
    </Section>
  );
}
