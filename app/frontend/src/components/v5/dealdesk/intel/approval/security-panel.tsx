"use client";

/**
 * R13 IA (backlog #3): the security optimiser. The cheapest package that clears first, then each item's recovery value,
 * LGD and RWA effect and CRM eligibility, most value per SAR tied up first.
 *
 * R14 G (K30): opens with "In plain words" and a purpose line; "tied up" explained with the client's own figures; column
 * help in plain words; the combinations evaluated (not only each item alone); the items the obligor could add (parent
 * guarantee, real estate, assignment of contract proceeds) with their effect; and, when no package clears, the reverse
 * solver's result one click away ("the rest has to come from price").
 */

import * as React from "react";

import { PanelWords } from "@/components/v5/panels-g/panel-words";
import { writeSecurity } from "@/lib/v5/plain-words-g/security";

import { Chip, Section, tableCls, tdCls, thCls } from "../../kit";
import { useSecurity } from "./api";
import { ReverseSolverPanel } from "./reverse-panel";
import { type AddOn, type Package, type Security, delta, pct, rankItems, sarm } from "./model";
import { Answer, FigText, Lineage, Loading } from "./parts";

function PackageLine({ p }: { p: Package }) {
  return (
    <div className="text-[12px] text-text-secondary">
      <span className="font-medium text-text-primary">{p.label}:</span> {p.text} · <FigText f={p.cost_sar_mn}>{sarm(p.cost_sar_mn.value)} tied up</FigText>
      {" "}· <FigText f={p.lifetime_raroc}>RAROC {pct(p.lifetime_raroc.value)}</FigText> · {p.clears ? "clears" : "does not clear"}
      {p.hard_breaches.length ? ` (${p.hard_breaches.join(", ")})` : ""}
    </div>
  );
}

export const SECURITY_PURPOSE = "What each piece of security is worth to the bank: the cash it would recover, the loss it saves, the capital it frees "
  + "and the value it adds a year, and the cheapest package that clears the hurdle.";
export const SECURITY_HELP: [string, string][] = [
  ["Recovery", "cash the bank expects to get from the item after the haircut and the time it takes"],
  ["LGD", "change in the share of the loan lost if the client defaults"],
  ["RWA", "capital relief, only for items the regulator recognises"],
  ["SVA", "value added a year after the cost of capital"],
  ["Tied up", "the client's own assets pledged, which it cannot use elsewhere"],
];

function Help() {
  return (
    <p className="mt-1.5 text-[11px] leading-4 text-text-muted" data-testid="ia-security-help">
      {SECURITY_HELP.map(([k, h], i) => <span key={k}>{i ? " · " : ""}<span className="font-medium text-text-secondary">{k}</span> = {h}</span>)}.
    </p>
  );
}

function Combinations({ list }: { list: Package[] }) {
  if (!list.length) return null;
  return (
    <div className="mt-4" data-testid="ia-security-combinations">
      <p className="text-[12px] font-medium text-text-primary">Combinations, cheapest first</p>
      <div className="mt-1 overflow-x-auto"><table className={tableCls}>
        <thead><tr><th className={thCls}>Package</th><th className={thCls}>Tied up</th><th className={thCls}>LGD</th><th className={thCls}>RAROC</th>
          <th className={thCls}>SVA</th><th className={thCls}>Clears</th></tr></thead>
        <tbody>{list.slice(0, 10).map((p, i) => (
          <tr key={`${p.text}-${i}`}>
            <td className={`${tdCls} whitespace-normal text-text-primary`}>{p.text}</td>
            <td className={tdCls}><FigText f={p.cost_sar_mn}>{sarm(p.cost_sar_mn.value)}</FigText></td>
            <td className={tdCls}><FigText f={p.lgd_y1}>{pct(p.lgd_y1.value)}</FigText></td>
            <td className={tdCls}><FigText f={p.lifetime_raroc}>{pct(p.lifetime_raroc.value)}</FigText></td>
            <td className={tdCls}><FigText f={p.sva}>{sarm(p.sva.value)}</FigText></td>
            <td className={tdCls}>{p.clears ? <Chip tone="positive">clears</Chip> : <Chip>no</Chip>}</td>
          </tr>))}</tbody>
      </table></div>
    </div>
  );
}

function AddOns({ list }: { list: AddOn[] }) {
  if (!list.length) return null;
  return (
    <div className="mt-4" data-testid="ia-security-addons">
      <p className="text-[12px] font-medium text-text-primary">Security the client could add</p>
      <div className="mt-1 overflow-x-auto"><table className={tableCls}>
        <thead><tr><th className={thCls}>Item</th><th className={thCls}>Tied up</th><th className={thCls}>LGD on the ask</th><th className={thCls}>SVA on the ask</th>
          <th className={thCls}>RAROC with it</th><th className={thCls}>Clears</th></tr></thead>
        <tbody>{list.map((a) => {
          const d = a.on_ask ?? a.standalone;
          return (
            <tr key={a.id} data-testid={`ia-security-addon-${a.id}`}>
              <td className={`${tdCls} whitespace-normal`}><span className="text-text-primary">{a.label}</span>
                <span className="block text-[11px] text-text-muted">{a.detail}</span></td>
              <td className={tdCls}><FigText f={a.cost_sar_mn}>{sarm(a.cost_sar_mn.value)}</FigText></td>
              <td className={tdCls}><FigText f={d.lgd_y1}>{delta(d.lgd_y1)}</FigText></td>
              <td className={tdCls}><FigText f={d.sva}>{delta(d.sva)}</FigText></td>
              <td className={tdCls}>{a.on_ask_raroc ? <FigText f={a.on_ask_raroc}>{pct(a.on_ask_raroc.value)}</FigText> : "–"}</td>
              <td className={tdCls}>{(a.clears_on_ask ?? a.clears_alone) ? <Chip tone="positive">clears</Chip> : <Chip>no</Chip>}</td>
            </tr>);
        })}</tbody>
      </table></div>
      <p className="mt-1 text-[11px] text-text-muted">What-ifs on a copy of the deal, to negotiate with the client: not items on file.</p>
    </div>
  );
}

export function SecurityView({ s, proposalId }: { s: Security; proposalId?: string }) {
  const items = rankItems(s.items);
  const pk = s.cheapest_package ?? s.best_package;
  const [reverse, setReverse] = React.useState(false);
  return (<>
    <PanelWords panel="security" lines={() => writeSecurity(s)} />
    <p className="mb-2 text-[12px] text-text-secondary" data-testid="ia-security-purpose">{SECURITY_PURPOSE}</p>
    <Answer testId="ia-security-answer">{s.headline}</Answer>
    {s.tied_up_text ? <p className="mt-1 text-[12px] text-text-secondary" data-testid="ia-security-tied">{s.tied_up_text}</p> : null}
    <div className="mt-2 space-y-1">
      {pk ? <PackageLine p={pk} /> : null}
      {s.ask_package ? <PackageLine p={s.ask_package} /> : null}
    </div>
    <div className="mt-3 overflow-x-auto">
      <table className={tableCls} data-testid="ia-security-items">
        <thead><tr>
          <th className={thCls}>Item</th><th className={thCls}>Recovery</th><th className={thCls}>LGD</th><th className={thCls}>RWA</th>
          <th className={thCls}>SVA</th><th className={thCls}>Capital relief</th>
        </tr></thead>
        <tbody>{items.map((it) => (
          <tr key={it.id}>
            <td className={`${tdCls} whitespace-normal`}>
              <span className="text-text-primary">{it.label}</span>{it.in_ask ? <span className="ml-1 text-[11px] text-text-muted">in the ask</span> : null}
            </td>
            <td className={tdCls}><FigText f={it.recovery_value}>{sarm(it.recovery_value?.value)}</FigText></td>
            <td className={tdCls}><FigText f={it.standalone.lgd_y1}>{delta(it.standalone.lgd_y1)}</FigText></td>
            <td className={tdCls}><FigText f={it.standalone.rwa_y1}>{delta(it.standalone.rwa_y1)}</FigText></td>
            <td className={tdCls}><FigText f={it.standalone.sva}>{delta(it.standalone.sva)}</FigText></td>
            <td className={tdCls}>
              <span className="inline-flex items-center gap-1">
                <Chip tone={it.crm.eligible ? "positive" : "neutral"}>{it.crm.eligible ? "eligible" : "LGD only"}</Chip>
                <Lineage title="Credit risk mitigation" sources={[]}><p>{it.crm.basis}</p></Lineage>
              </span>
            </td>
          </tr>))}</tbody>
      </table>
    </div>
    <p className="mt-2 text-[11px] text-text-muted">Each item alone against no security, other terms as asked.</p>
    <Help />
    <Combinations list={s.combinations ?? []} />
    <AddOns list={s.add_ons ?? []} />
    {s.needs_price && proposalId ? (
      <div className="mt-4" data-testid="ia-security-reverse">
        <button type="button" onClick={() => setReverse((x) => !x)} aria-expanded={reverse} data-testid="ia-security-reverse-toggle"
                className="text-[12px] font-medium text-accent hover:underline">
          {reverse ? "Hide" : "The rest has to come from price or structure: show"} the smallest change that makes it approvable</button>
        {reverse ? <div className="mt-2"><ReverseSolverPanel proposalId={proposalId} /></div> : null}
      </div>) : null}
  </>);
}

/** Deal page, More menu: "Security value". */
export function SecurityOptimiserPanel({ proposalId }: { proposalId: string }) {
  const r = useSecurity(proposalId);
  return (
    <Section title="Security value" testId="ia-security-panel"
             info={<p>What each security item is worth: its recognised recovery value and LGD effect, and its capital effect (whether the
               standardised approach recognises it, and the RWA it saves). The cheapest package is the one that ties up the least client value
               (collateral at market value, guarantees at the covered amount, cash at the cash blocked) and still clears the hurdle and every limit.</p>}>
      {r.data ? <SecurityView s={r.data} proposalId={proposalId} /> : <><PanelWords panel="security" lines={r.error ? [] : null} /><Loading error={r.error} /></>}
    </Section>
  );
}
