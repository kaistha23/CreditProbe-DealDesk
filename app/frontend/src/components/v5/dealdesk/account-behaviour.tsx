"use client";

/**
 * PLAN_R9 Session E (E2): deposits in Deal Desk. The "Account behaviour" panel for the proposal's obligor:
 * 24 months of balances and turnover, returned cheques, top counterparties; the deposit value added to
 * relationship RAROC (average balances × (FTP credit − profit paid) + flow fees); and cash-flow debt
 * capacity beside the EBITDA-based capacity.
 */

import * as React from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { Plot } from "@/components/v5/ews/plot";
import { cn } from "@/lib/utils";
import { dealdeskOrigin, useLoad } from "@/lib/v5/dealdesk";
import { fmt } from "@/lib/v5/format";
import { capacitySub, enginesApi, pct1, sarMn } from "@/lib/v5/dealdesk-engines";
import { PlainWords } from "@/components/v5/ui/plain-words";

import { ReturnViewSwitch } from "./deal-story";

import { Kpi, Section, tableCls, tdCls, thCls } from "./kit";

interface Behaviour {
  obligor: string; new_to_bank: boolean; source: string; deposit_value_sar_mn: number; deposit_formula?: string;
  raroc: { lifetime: number; relationship: number; relationship_with_deposits: number; hurdle: number };
  debt_capacity: { ebitda_based_sar_mn: number; cash_flow_based_sar_mn: number; ask_sar_mn: number; max_leverage: number; cash_flow_cover: number };
  months: { month: string; avg_balance_sar_mn: number; credit_turnover_sar_mn: number; cheques_returned_count: number }[];
  counterparties: { rank: number; counterparty_name: string; direction: string; amount_sar_mn: number; category: string }[];
  metrics: { avg_balance_12m_sar_mn: number; credit_turnover_12m_sar_mn: number; turnover_to_revenue: number | null; returned_cheques_12m: number;
             balance_volatility: number | null; profit_rate: number; ftp_credit: number;
             behavioural_haircut?: number; stable_balance_sar_mn?: number; pv_deposit_value_sar_mn?: number } | null;
}

async function load(pid: string): Promise<Behaviour> {
  const r = await fetch(`${dealdeskOrigin()}/api/v1/dealdesk/proposals/${encodeURIComponent(pid)}/account_behaviour`, { credentials: "include", cache: "no-store" });
  if (!r.ok) throw new Error("Account behaviour is temporarily unavailable.");
  return (await r.json()) as Behaviour;
}

/** R15 b (L8 (a)): the deposit treatment in plain words. */
function depositPlainLines(b: Behaviour, rule?: string, capacityLine?: string): string[] {
  const out: string[] = [];
  if (b.metrics) {
    const hc = b.metrics.behavioural_haircut != null ? `${Math.round(b.metrics.behavioural_haircut * 100)}%` : null;
    out.push(`The client keeps about ${fmt.sar(b.metrics.avg_balance_12m_sar_mn)} with us on average${hc ? `; we count only the stable part (${hc} haircut for money that may leave)` : ""}.`);
    out.push(`Those balances earn the bank the funding credit less the profit we pay the client, plus flow fees: ${fmt.sar(b.deposit_value_sar_mn)} a year.`);
  } else {
    out.push("New to bank: no account history yet, so deposits add nothing.");
  }
  out.push(rule ?? "The approval test uses the deal's own RAROC; deposits are for pricing talks.");
  if (capacityLine) out.push(`${capacityLine}.`);
  return out;
}

export function AccountBehaviour({ proposalId }: { proposalId: string }) {
  const r = useLoad(() => load(proposalId), `acct:${proposalId}`);
  const b = r.data;
  // R14 E (K22): capacity by product and the one RAROC bridge, from the engines
  const cap = useLoad(() => enginesApi.capacity(proposalId), `eng-cap:${proposalId}`).data;
  const br = useLoad(() => enginesApi.bridge(proposalId), `eng-bridge:${proposalId}`).data;
  // R15 b (L8 (a), L13 (2)): the three labelled return views and the capacity cross-check, from the engines summary
  const sum = useLoad(() => enginesApi.summary(proposalId), `eng-sum-ab:${proposalId}`).data ?? null;
  return (
    <Section title="Account behaviour and deposit value" testId="dealdesk-account-behaviour"
             info={<><p>The obligor&apos;s accounts with the bank over 24 months: average balances, credit turnover and returned cheques, and the top counterparties.</p>
               <p className="mt-2">Deposit value = average balances × (deposit FTP credit − profit paid) + flow fees; it is added to relationship RAROC over the tenor. Cash-flow debt capacity = (EBITDA ÷ cover − existing debt service) as an annuity over the tenor, beside the EBITDA-based capacity (maximum leverage × EBITDA − debt). Parameters: Admin → Deal Desk Parameters.</p>
               {b ? <p className="mt-2">Source: {b.source}.</p> : null}</>}>
      {r.error ? <p role="alert" className="text-[12px] text-negative">{r.error}</p> : null}
      {!b && !r.error ? <Skeleton className="h-40 w-full" /> : null}
      {b ? (<>
        <div className="grid gap-3 md:grid-cols-5">
          <Kpi label="Relationship + deposits (pricing talks)" value={fmt.pct(br?.steps[2]?.raroc ?? b.raroc.relationship_with_deposits)}
               sub={br ? <>approval uses deal only <b>{pct1(br.steps[0].raroc)}</b> · hurdle {pct1(br.hurdle)}</>
                       : <>relationship, without deposits <b>{fmt.pct(b.raroc.relationship)}</b> · hurdle {fmt.pct(b.raroc.hurdle)}</>}
               info={`A view for pricing negotiation, not the approval test. ${sum?.return_views?.rule ?? "The approval test uses the deal's own RAROC."}`
                     + (br ? ` ${br.steps.map((x) => `${x.step}: ${pct1(x.raroc)} (PV ${sarMn(x.pv_sar_mn, 2)}; ${x.what})`).join(" · ")}` : "")}
               tone={(br?.steps[2]?.raroc ?? b.raroc.relationship_with_deposits) >= b.raroc.hurdle ? "positive" : "negative"} testId="dealdesk-raroc-deposits" />
          <Kpi label="Deposit value a year" value={fmt.sar(b.deposit_value_sar_mn)}
               sub={b.metrics ? <>stable balance <b>{fmt.sar(b.metrics.stable_balance_sar_mn ?? b.metrics.avg_balance_12m_sar_mn)}</b>
                 {b.metrics.behavioural_haircut != null ? <> · {Math.round(b.metrics.behavioural_haircut * 100)}% haircut</> : null}</> : "New to bank"}
               info={b.deposit_formula ?? "Average balances × (FTP credit − profit paid) + flow fees."} testId="dealdesk-deposit-value" />
          {cap ? (
            <Kpi label={cap.method === "borrowing_base" ? "Capacity: borrowing base" : "Capacity: DSCR and leverage"} value={sarMn(cap.capacity_sar_mn)}
                 sub={capacitySub(cap)} tone={cap.within ? "positive" : "negative"} info={`${cap.formula}${cap.note ? ` ${cap.note}` : ""}`}
                 testId="dealdesk-capacity" />
          ) : <Kpi label="Capacity" value="…" />}
          <Kpi label="Cross-check: leverage limit alone" value={fmt.sar(b.debt_capacity.ebitda_based_sar_mn)}
               sub={<>not a second answer · sizing is the Capacity tile</>} testId="dealdesk-capacity-cross-check"
               info={`${fmt.num(b.debt_capacity.max_leverage)}× EBITDA less debt; cash flow = (EBITDA ÷ ${fmt.num(b.debt_capacity.cash_flow_cover)} − existing debt service) as an annuity over the tenor. The sizing method for this product is the Capacity tile.`} />
          <Kpi label="Returned cheques" value={b.metrics ? fmt.count(b.metrics.returned_cheques_12m) : "–"}
               sub={b.metrics?.turnover_to_revenue != null ? <>12 months · turnover ÷ revenue <b>{fmt.pct(b.metrics.turnover_to_revenue)}</b></> : undefined} />
        </div>
        {br || cap ? (
          <div className="mt-2 space-y-1 text-[12px] text-text-secondary" data-testid="dealdesk-raroc-bridge">
            {br ? <p><span className="font-medium text-text-primary">RAROC bridge</span> (lifetime, one capital base {sarMn(br.pv_capital_sar_mn, 1)} PV):{" "}
              {br.steps.map((x, i) => <span key={x.step}>{i ? " → " : ""}{x.step.replace(/^\+\s*/, "+ ")} {i ? <>(+{sarMn(x.pv_sar_mn, 2)}) </> : null}<b>{pct1(x.raroc)}</b></span>)}
              {" "}· hurdle {pct1(br.hurdle)}</p> : null}
            {cap && !cap.within ? <p className="text-negative" data-testid="dealdesk-capacity-finding">{cap.finding_title}: a critical finding; the counter-offer cuts the amount to capacity.</p> : null}
          </div>) : null}
        <div className="mt-3 grid gap-3 lg:grid-cols-2">
          <PlainWords testId="dealdesk-deposit-plain" lines={depositPlainLines(b, sum?.return_views?.rule, cap?.finding_title)} />
          {sum?.return_views ? <div className="rounded-md border border-border bg-surface px-3 py-2"><p className="mb-1 text-[12px] font-medium text-text-primary">Return view</p>
            <ReturnViewSwitch e={sum} testId="dealdesk-ab-return-view" /></div> : null}
        </div>
        {b.months.length ? (
          <div className="mt-3 grid gap-3 lg:grid-cols-2">
            <Plot ariaLabel="Average balance and credit turnover" filename="account-behaviour" height={240}
                  data={[{ type: "bar", name: "Credit turnover", x: b.months.map((m) => m.month), y: b.months.map((m) => m.credit_turnover_sar_mn), marker: { color: "#C9BC9C" },
                           hovertemplate: fmt.hoverTemplate("sar_mn") },
                         { type: "scatter", mode: "lines", name: "Average balance", x: b.months.map((m) => m.month), y: b.months.map((m) => m.avg_balance_sar_mn), line: { color: "#1F4E79", width: 2 },
                           hovertemplate: fmt.hoverTemplate("sar_mn") }] as never[]}
                  layout={{ margin: { l: 48, r: 10, t: 10, b: 40 }, legend: { orientation: "h", y: -0.25 }, yaxis: { title: { text: "SAR m" } } } as never} />
            <table className={tableCls}><thead><tr>{["#", "Top counterparty (latest month)", "Direction", "Amount", "Category"].map((h) => <th key={h} className={thCls}>{h}</th>)}</tr></thead>
              <tbody>{b.counterparties.map((c) => <tr key={c.rank}><td className={tdCls}>{c.rank}</td><td className={cn(tdCls, "whitespace-normal")}>{c.counterparty_name}</td>
                <td className={tdCls}>{c.direction === "in" ? "Inflow" : "Outflow"}</td><td className={cn(tdCls, "text-right")}>{fmt.sar(c.amount_sar_mn)}</td><td className={tdCls}>{c.category}</td></tr>)}</tbody></table>
          </div>) : <p className="mt-3 text-[12px] text-text-muted">New to bank: no account history yet. Deposit value is not counted.</p>}
      </>) : null}
    </Section>
  );
}
