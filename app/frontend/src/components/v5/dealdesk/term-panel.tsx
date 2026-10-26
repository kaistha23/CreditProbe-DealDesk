"use client";

/**
 * The term panel (PLAN_R5 D4): every lever the risk manager has, grouped as Anne's list (Pricing, Structure,
 * Risk mitigation, Covenants and conditions, Relationship) and collapsed by group. Each lever shows its channel
 * and owned parameter table behind a tooltip, and moves inside its market and policy bounds
 * (`GET /levers?proposal_id=`). Moving one recomputes through the engine at once (no model call); the newest
 * request wins, so dragging never shows a stale figure. `data-ms` carries the last round trip for the gate's
 * 300 ms check.
 *
 * PLAN_R12 G (I14): the panel is "Structure it yourself" (`StructureItYourself`, the Section U mounts in the Structure
 * step) with the subtitle "Move any lever; RAROC, limits and approval update live." and, when the recommended structure is
 * given, a live "vs recommended" strip: RAROC, SVA, ECL (day one) and P(Stage 2) next quarter for the structure on the
 * panel against the optimiser's recommendation, both scored in one forward-risk run (newest request wins).
 */

import * as React from "react";
import { ChevronDown, ChevronRight, RotateCcw } from "lucide-react";

import { cn } from "@/lib/utils";
import {
  type Analysis, type Lever, type LeverCatalogue, type Proposal, type Terms,
  AMORTISATION, COLLATERAL, COVENANT_ITEM, CROSS_SELL, FACILITY, STRUCTURE, bps, dealdesk, isFunded, money, pctPts, rate, withNeutral, years,
} from "@/lib/v5/dealdesk";

import { DEPOSIT_TYPE, depositRead, hasDeposit } from "@/lib/v5/dealdesk-deposit";  // Round D
import { type VsFigures, type VsRow, sameAsRecommended, vsRows, vsVerdict } from "@/lib/v5/dealdesk-vs";
import type { Metrics } from "@/lib/v5/dealdesk";
import { prob } from "@/lib/v5/dealdesk-forward";

import { forwardApi } from "./forward-risk";
import { Chip, Section, SecondaryButton } from "./kit";

export const STRUCTURE_TITLE = "Structure it yourself";
export const STRUCTURE_SUBTITLE = "Move any lever; RAROC, limits and approval update live.";

/** The structure the panel is judged against: the optimiser's recommendation (a Solution or an Analysis). */
export interface Recommended { terms: Terms; metrics: Metrics }

const YOURS = "Your structure";
const REC = "Recommended";

function fromMetrics(m: Metrics | undefined | null): VsFigures | null {
  return m ? { raroc: m.lifetime_raroc, sva: m.sva, ecl: m.day_one_ecl, p_stage2: null } : null;
}

function show(r: VsRow, v: number | null): string {
  if (v === null) return "–";
  return r.key === "raroc" ? rate(v) : r.key === "p_stage2" ? prob(v) : money(v);
}

function showDelta(r: VsRow): string {
  if (r.delta === null) return "";
  if (r.delta === 0) return "same";
  const sign = r.delta > 0 ? "+" : "−";
  const a = Math.abs(r.delta);
  if (r.key === "raroc" || r.key === "p_stage2") return `${sign}${(a * 100).toFixed(r.key === "raroc" ? 1 : 2)} pts`;
  return `${sign}${money(a).replace(/^−/, "")}`;
}

/** The live "vs recommended" strip (I14). Falls back to the engine's own RAROC, SVA and ECL when forward risk is not exported. */
export function VsRecommendedStrip({ proposalId, terms, mine, recommended }: {
  proposalId: string; terms: Terms; mine: Metrics | null; recommended: Recommended;
}) {
  const [fw, setFw] = React.useState<{ key: string; mine: VsFigures; rec: VsFigures } | null>(null);
  const tKey = JSON.stringify(terms);
  const rKey = JSON.stringify(recommended.terms);
  React.useEffect(() => {
    const ctl = new AbortController();
    const h = window.setTimeout(() => {
      forwardApi.run(proposalId, [{ key: "recommended", label: REC, role: "recommended", terms: recommended.terms },
                                  { key: "yours", label: YOURS, role: "alternative", terms }], ctl.signal).then((r) => {
        const pick = (label: string) => r.structures.find((x) => x.label === label || (x.also ?? []).includes(label));
        const b = pick(REC);
        // the service scores identical terms once: when the panel holds the recommendation, "yours" is that same row
        const a = pick(YOURS) ?? (tKey === rKey ? b : undefined);
        if (!a || !b) return;
        const f = (x: typeof a): VsFigures => ({ raroc: x.metrics.lifetime_raroc, sva: x.metrics.sva, ecl: x.metrics.day_one_ecl, p_stage2: x.p_stage2_next_q });
        setFw({ key: `${tKey}|${rKey}`, mine: f(a), rec: f(b) });
      }).catch(() => { /* forward risk not exported: the engine's figures stand, P(Stage 2) shows a dash */ });
    }, 300);
    return () => { window.clearTimeout(h); ctl.abort(); };
    // the newest terms win: tKey / rKey carry the structures by value
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [proposalId, tKey, rKey]);
  const live = fw && fw.key === `${tKey}|${rKey}` ? fw : null;
  const rows = vsRows(live?.mine ?? fromMetrics(mine), live?.rec ?? fromMetrics(recommended.metrics));
  const same = sameAsRecommended(rows);
  return (
    <div className="mb-3 rounded-lg border border-border bg-surface-sunken/40 px-3 py-2" data-testid="dealdesk-vs-recommended" data-live={live ? "true" : "false"}>
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">Against the recommended structure</p>
        <p className="text-[12px] text-text-secondary" data-testid="dealdesk-vs-verdict">{vsVerdict(rows)}</p>
      </div>
      <div className="mt-2 grid grid-cols-2 gap-2 xl:grid-cols-4">
        {rows.map((r) => (
          <div key={r.key} className="min-w-0 rounded-md border border-border bg-surface px-2.5 py-1.5" data-testid={`dealdesk-vs-${r.key}`}>
            <p className="truncate text-[11px] text-text-muted" title={r.label}>{r.label}</p>
            <div className="flex min-w-0 items-baseline gap-2">
              <span className="truncate text-[15px] font-semibold tabular-nums text-text-primary">{show(r, r.mine)}</span>
              {!same && r.delta !== null ? <Chip tone={r.better === null ? "neutral" : r.better ? "positive" : "negative"}>{showDelta(r)}</Chip> : null}
            </div>
            <p className="truncate text-[11px] tabular-nums text-text-secondary">Recommended {show(r, r.rec)}</p>
          </div>))}
      </div>
    </div>
  );
}

/** I14: the manual structuring panel as its own Section, titled so the manual choice is clear. U mounts it in Structure. */
export function StructureItYourself({ proposal, terms, onResult, recommended, action, className }: {
  proposal: Proposal; terms: Terms; onResult: (r: Analysis) => void; recommended?: Recommended | null; action?: React.ReactNode; className?: string;
}) {
  return (
    <Section title={STRUCTURE_TITLE} className={cn("min-w-0", className)} testId="dealdesk-structure-yourself" action={action}
             info="Every lever recomputes through the engine at once, inside its market and policy bounds. The strip on top compares your structure with the optimiser's recommended one on RAROC, SVA, ECL and the chance of Stage 2 next quarter.">
      <p className="-mt-2 mb-3 text-[12px] text-text-secondary" data-testid="dealdesk-structure-subtitle">{STRUCTURE_SUBTITLE}</p>
      <TermPanel proposal={proposal} terms={terms} onResult={onResult} recommended={recommended ?? null} />
    </Section>
  );
}

const GROUPS = ["Pricing", "Structure", "Risk mitigation", "Covenants and conditions", "Relationship"] as const;

function tip(l: Lever | undefined): string | undefined {
  if (!l) return undefined;
  const b = l.bounds && "min" in l.bounds ? ` · bounds ${l.bounds.min}–${l.bounds.max}${l.unit === "%" ? "%" : l.unit ? ` ${l.unit}` : ""} (${l.bounds.source})` : "";
  return `${l.channel} · ${l.parameters.table} (${l.parameters.owner}, ${l.parameters.version})${b}`;
}

function Slider({ label, value, min, max, step, read, onChange, testId, changed, lever }: {
  label: string; value: number; min: number; max: number; step: number; read: string; onChange: (v: number) => void; testId: string;
  changed: boolean; lever?: Lever;
}) {
  return (
    <label className="block" data-testid={testId} title={tip(lever)}>
      <span className="flex items-baseline justify-between text-[12px]">
        <span className="text-text-secondary">{label}</span>
        <span className={cn("font-medium tabular-nums", changed ? "text-accent" : "text-text-primary")}>{read}</span></span>
      <input type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))}
             aria-label={label} className="mt-1 w-full accent-[var(--ipm-accent)]" />
    </label>
  );
}

function Select({ label, value, options, onChange, testId, changed, lever }: {
  label: string; value: string; options: [string, string][]; onChange: (v: string) => void; testId: string; changed: boolean; lever?: Lever;
}) {
  return (
    <label className="block text-[12px] text-text-secondary" title={tip(lever)}>{label}
      <select value={value} onChange={(e) => onChange(e.target.value)} data-testid={testId}
              className={cn("mt-1 h-8 w-full rounded-md border border-border bg-surface px-2 text-[13px]", changed ? "text-accent" : "text-text-primary")}>
        {options.map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
  );
}

function Toggle({ on, onClick, children, testId, title }: { on: boolean; onClick: () => void; children: React.ReactNode; testId: string; title?: string }) {
  return (
    <button type="button" aria-pressed={on} onClick={onClick} data-testid={testId} title={title}
            className={cn("h-7 rounded-full border px-3 text-[12px]", on ? "border-accent bg-accent-muted text-accent" : "border-border text-text-secondary hover:border-accent")}>
      {children}</button>
  );
}

function Group({ name, open, onToggle, changed, children }: { name: string; open: boolean; onToggle: () => void; changed: number; children: React.ReactNode }) {
  const slug = name.toLowerCase().replace(/\W+/g, "-");
  return (
    <div className="rounded-lg border border-border" data-testid={`dealdesk-group-${slug}`} data-open={open ? "true" : "false"}>
      <button type="button" onClick={onToggle} aria-expanded={open} data-testid={`dealdesk-group-toggle-${slug}`}
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-[13px] font-semibold text-text-primary hover:bg-surface-hover">
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}{name}
        {changed ? <span className="ml-auto rounded-full bg-accent-muted px-2 text-[11px] font-medium text-accent">{changed} changed</span> : null}
      </button>
      {open ? <div className="grid gap-x-6 gap-y-4 border-t border-border px-3 py-3 md:grid-cols-2">{children}</div> : null}
    </div>
  );
}

const eq = (a: unknown, b: unknown) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);

export function TermPanel({ proposal, terms, onResult, recommended = null }: {
  proposal: Proposal; terms: Terms; onResult: (r: Analysis) => void; recommended?: Recommended | null;
}) {
  const ask = withNeutral(proposal.ask);
  const [t, setT] = React.useState<Terms>(withNeutral(terms));
  const [cat, setCat] = React.useState<LeverCatalogue | null>(null);
  const [open, setOpen] = React.useState<Record<string, boolean>>({ Pricing: true });
  const seq = React.useRef(0);
  const [ms, setMs] = React.useState<number | null>(null);
  const [res, setRes] = React.useState<Analysis | null>(null);

  React.useEffect(() => {
    let live = true;
    void dealdesk.levers(proposal.proposal_id).then((c) => { if (live) setCat(c); }).catch(() => null);
    return () => { live = false; };
  }, [proposal.proposal_id]);

  const apply = React.useCallback(async (next: Terms) => {
    setT(next);
    const mine = ++seq.current;
    const t0 = performance.now();
    try {
      const r = await dealdesk.compute(proposal.proposal_id, next);
      if (mine !== seq.current) return;
      setMs(Math.round(performance.now() - t0));
      setRes(r);
      onResult(r);
    } catch { /* the next move recomputes */ }
  }, [proposal.proposal_id, onResult]);

  const set = <K extends keyof Terms>(k: K, v: Terms[K]) => void apply({ ...t, [k]: v });
  const L = (k: string) => cat?.levers.find((l) => l.key === k);
  const bound = (k: string, lo: number, hi: number): [number, number] => {
    const b = L(k)?.bounds;
    return b && "min" in b ? [Math.min(lo, b.min), Math.max(b.max, lo)] : [lo, hi];
  };
  const funded = isFunded(t);
  const term = t.facility_type === "term_loan";
  const hasUnfunded = !funded || (t.funded_share_pct ?? 100) < 100;
  const step = Math.max(1, Math.round(ask.amount / 100));
  const changedIn = (keys: (keyof Terms)[]) => keys.filter((k) => !eq(t[k], ask[k])).length;
  const toggleGroup = (g: string) => setOpen((o) => ({ ...o, [g]: !o[g] }));
  const listToggle = (k: "covenant_items" | "cross_sell", v: string) => {
    const cur = (t[k] ?? []) as string[];
    set(k, (cur.includes(v) ? cur.filter((x) => x !== v) : [...cur, v]) as Terms[typeof k]);
  };
  const gOpts = cat?.guarantee_options ?? proposal.security.guarantees.map((g) => ({ id: g.guarantee_id, label: `${g.guarantor} (${g.type})`, type: g.type, rating: g.guarantor_rating, offered: g.offered_in_ask, requested: false }));

  const [mLo, mHi] = bound("margin_bps", 50, 600);
  const depBy = (L("deposit_pct")?.bounds as { by_type?: Record<string, [number, number]> } | undefined)?.by_type;
  // a size with no type is lien-marked cash (the "require a deposit" lever's default, as the single-lever table applies it)
  const depType = (t.deposit_type ?? "none") === "none" ? (hasDeposit(t) ? "lien_cash" : "none") : (t.deposit_type as string);
  const depositMax = Math.max(depBy?.[depType === "none" ? "lien_cash" : depType]?.[1] ?? 50, t.deposit_pct ?? 0);  // Round D: the parameter's bound
  const fHi = bound("upfront_fee_bps", 0, 200)[1];
  const keys: Record<(typeof GROUPS)[number], (keyof Terms)[]> = {
    Pricing: ["margin_bps", "upfront_fee_bps", "commitment_fee_bps", "commission_bps", "prepayment_fee_bps"],
    Structure: ["amount", "hold_pct", "tenor_years", "grace_years", "amortisation", "balloon_pct", "facility_type", "funded_share_pct", "structure", "rate_type"],
    "Risk mitigation": ["cash_margin_pct", "deposit_type", "deposit_pct", "collateral_ids", "guarantee_id", "guarantee_coverage_pct", "insurance_cover_pct", "receivables_assignment_pct"],
    "Covenants and conditions": ["covenant_package", "covenant_items", "review_cycle_months"],
    Relationship: ["cross_sell"],
  };

  return (
    <div className="space-y-3" data-testid="dealdesk-term-panel" data-ms={ms ?? ""}>
      {recommended ? <VsRecommendedStrip proposalId={proposal.proposal_id} terms={t} mine={res?.metrics ?? null} recommended={recommended} /> : null}
      <Group name="Pricing" open={Boolean(open.Pricing)} onToggle={() => toggleGroup("Pricing")} changed={changedIn(keys.Pricing)}>
        {funded ? <Slider label="Margin" value={t.margin_bps} min={Math.min(mLo, 50)} max={Math.max(mHi + 100, 600)} step={5} read={bps(t.margin_bps)} lever={L("margin_bps")}
                          onChange={(v) => set("margin_bps", v)} testId="dealdesk-lever-margin" changed={t.margin_bps !== ask.margin_bps} /> : null}
        <Slider label="Upfront / arrangement fee" value={t.upfront_fee_bps} min={0} max={Math.max(fHi + 50, 200)} step={5} read={bps(t.upfront_fee_bps)} lever={L("upfront_fee_bps")}
                onChange={(v) => set("upfront_fee_bps", v)} testId="dealdesk-lever-upfront" changed={t.upfront_fee_bps !== ask.upfront_fee_bps} />
        {t.facility_type === "revolver" ? <Slider label="Commitment fee on undrawn" value={t.commitment_fee_bps} min={0} max={100} step={5} read={bps(t.commitment_fee_bps)}
                          lever={L("commitment_fee_bps")} onChange={(v) => set("commitment_fee_bps", v)} testId="dealdesk-lever-commitment" changed={t.commitment_fee_bps !== ask.commitment_fee_bps} /> : null}
        {hasUnfunded ? <Slider label="LG/LC commission" value={t.commission_bps} min={0} max={300} step={5} read={bps(t.commission_bps)} lever={L("commission_bps")}
                          onChange={(v) => set("commission_bps", v)} testId="dealdesk-lever-commission" changed={t.commission_bps !== ask.commission_bps} /> : null}
        {term ? <Slider label="Prepayment / early settlement fee" value={t.prepayment_fee_bps ?? 0} min={0} max={200} step={10} read={bps(t.prepayment_fee_bps ?? 0)}
                        lever={L("prepayment_fee_bps")} onChange={(v) => set("prepayment_fee_bps", v)} testId="dealdesk-lever-prepayment"
                        changed={(t.prepayment_fee_bps ?? 0) !== (ask.prepayment_fee_bps ?? 0)} /> : null}
      </Group>

      <Group name="Structure" open={Boolean(open.Structure)} onToggle={() => toggleGroup("Structure")} changed={changedIn(keys.Structure)}>
        <Slider label="Amount" value={t.amount} min={Math.round(ask.amount * 0.4)} max={Math.round(ask.amount * 1.2)} step={step} lever={L("amount")}
                read={money(t.amount, t.currency)} onChange={(v) => set("amount", v)} testId="dealdesk-lever-amount" changed={t.amount !== ask.amount} />
        <Slider label="Hold level (sell-down)" value={t.hold_pct ?? 100} min={40} max={100} step={5} read={pctPts(t.hold_pct ?? 100)} lever={L("hold_pct")}
                onChange={(v) => set("hold_pct", v)} testId="dealdesk-lever-hold" changed={(t.hold_pct ?? 100) !== 100} />
        <Slider label="Tenor" value={t.tenor_years} min={1} max={10} step={1} read={years(t.tenor_years)} lever={L("tenor_years")}
                onChange={(v) => void apply({ ...t, tenor_years: v, grace_years: Math.min(t.grace_years ?? 0, v - 1) })}
                testId="dealdesk-lever-tenor" changed={t.tenor_years !== ask.tenor_years} />
        {funded ? <Slider label="Grace period" value={t.grace_years ?? 0} min={0} max={Math.max(0, t.tenor_years - 1)} step={1} read={years(t.grace_years ?? 0)} lever={L("grace_years")}
                          onChange={(v) => set("grace_years", v)} testId="dealdesk-lever-grace" changed={(t.grace_years ?? 0) !== (ask.grace_years ?? 0)} /> : null}
        {term ? <Select label="Amortisation profile" value={t.amortisation} lever={L("amortisation")} testId="dealdesk-lever-amortisation"
                        options={Object.entries(AMORTISATION)} changed={t.amortisation !== ask.amortisation}
                        onChange={(v) => void apply({ ...t, amortisation: v, balloon_pct: v === "balloon" ? (t.balloon_pct || 30) : 0 })} /> : null}
        {term && t.amortisation === "balloon" ? <Slider label="Balloon share" value={t.balloon_pct} min={5} max={50} step={5} read={pctPts(t.balloon_pct)} lever={L("balloon_pct")}
                          onChange={(v) => set("balloon_pct", v)} testId="dealdesk-lever-balloon" changed={t.balloon_pct !== ask.balloon_pct} /> : null}
        <Select label="Facility type" value={t.facility_type} lever={L("facility_type")} testId="dealdesk-lever-facility" changed={t.facility_type !== ask.facility_type}
                options={Object.entries(FACILITY)} onChange={(v) => set("facility_type", v)} />
        {funded ? <Slider label="Funded share (rest unfunded through CCF)" value={t.funded_share_pct ?? 100} min={0} max={100} step={10} read={pctPts(t.funded_share_pct ?? 100)}
                          lever={L("funded_share_pct")} onChange={(v) => set("funded_share_pct", v)} testId="dealdesk-lever-funded"
                          changed={(t.funded_share_pct ?? 100) !== (ask.funded_share_pct ?? 100)} /> : null}
        <Select label="Islamic structure" value={t.structure} lever={L("structure")} testId="dealdesk-lever-structure" changed={t.structure !== ask.structure}
                options={Object.entries(STRUCTURE)} onChange={(v) => set("structure", v)} />
        {funded ? <Select label="Rate" value={t.rate_type ?? "floating"} lever={L("rate_type")} testId="dealdesk-lever-rate" changed={(t.rate_type ?? "floating") !== "floating"}
                          options={[["floating", "Floating"], ["fixed", "Fixed"]]} onChange={(v) => set("rate_type", v as Terms["rate_type"])} /> : null}
      </Group>

      <Group name="Risk mitigation" open={Boolean(open["Risk mitigation"])} onToggle={() => toggleGroup("Risk mitigation")} changed={changedIn(keys["Risk mitigation"])}>
        <Slider label="Cash margin / cash collateral" value={t.cash_margin_pct ?? 0} min={0} max={50} step={5} read={pctPts(t.cash_margin_pct ?? 0)} lever={L("cash_margin_pct")}
                onChange={(v) => set("cash_margin_pct", v)} testId="dealdesk-lever-cash" changed={(t.cash_margin_pct ?? 0) !== (ask.cash_margin_pct ?? 0)} />
        {/* Round D: "require a deposit": lien-marked cash (EAD, LGD, RWA) or operating balances (relationship RAROC) */}
        <Select label="Deposit requirement" value={depType} lever={L("deposit_type")} testId="dealdesk-lever-deposit-type"
                changed={(t.deposit_type ?? "none") !== (ask.deposit_type ?? "none")} options={Object.entries(DEPOSIT_TYPE)}
                onChange={(v) => void apply({ ...t, deposit_type: v, deposit_pct: v === "none" ? 0 : (t.deposit_pct || 20), deposit_amount: v === "none" ? 0 : (t.deposit_amount ?? 0) })} />
        {depType !== "none" ? (
          <Slider label="Deposit (% of limit)" value={t.deposit_pct ?? 0} min={0} max={depositMax} step={5} read={depositRead(t)}
                  lever={L("deposit_pct")} onChange={(v) => void apply({ ...t, deposit_pct: v, deposit_amount: 0 })} testId="dealdesk-lever-deposit"
                  changed={(t.deposit_pct ?? 0) !== (ask.deposit_pct ?? 0)} />) : null}
        <Select label="Guarantee" value={t.guarantee_id ?? ""} lever={L("guarantee_id")} testId="dealdesk-lever-guarantee" changed={(t.guarantee_id ?? null) !== (ask.guarantee_id ?? null)}
                options={[["", "None"], ...gOpts.map((g) => [g.id, `${g.label}${g.rating ? ` · ${g.rating}` : ""}`] as [string, string])]}
                onChange={(v) => void apply({ ...t, guarantee_id: v || null, guarantee_coverage_pct: v ? (t.guarantee_coverage_pct || 50) : 0 })} />
        {t.guarantee_id ? <Slider label="Guarantee cover" value={t.guarantee_coverage_pct} min={0} max={100} step={5} read={pctPts(t.guarantee_coverage_pct)} lever={L("guarantee_coverage_pct")}
                                  onChange={(v) => set("guarantee_coverage_pct", v)} testId="dealdesk-lever-guarantee-cover" changed={t.guarantee_coverage_pct !== ask.guarantee_coverage_pct} /> : null}
        <Slider label="Credit insurance cover" value={t.insurance_cover_pct ?? 0} min={0} max={90} step={5} read={pctPts(t.insurance_cover_pct ?? 0)} lever={L("insurance_cover_pct")}
                onChange={(v) => set("insurance_cover_pct", v)} testId="dealdesk-lever-insurance" changed={(t.insurance_cover_pct ?? 0) !== 0} />
        <Slider label="Assignment of contract proceeds" value={t.receivables_assignment_pct ?? 0} min={0} max={100} step={10} read={pctPts(t.receivables_assignment_pct ?? 0)}
                lever={L("receivables_assignment_pct")} onChange={(v) => set("receivables_assignment_pct", v)} testId="dealdesk-lever-receivables"
                changed={(t.receivables_assignment_pct ?? 0) !== 0} />
        <div className="flex flex-wrap items-center gap-2 md:col-span-2" title={tip(L("collateral_ids"))}>
          {proposal.security.collateral.map((c) => {
            const on = (t.collateral_ids ?? []).includes(c.collateral_id);
            return (
              <Toggle key={c.collateral_id} on={on} testId={`dealdesk-lever-collateral-${c.collateral_id}`}
                      onClick={() => set("collateral_ids", on ? t.collateral_ids.filter((x) => x !== c.collateral_id) : [...(t.collateral_ids ?? []), c.collateral_id])}>
                {COLLATERAL[c.type] ?? c.type} · {money(c.value, c.currency)}</Toggle>);
          })}
          {!proposal.security.collateral.length ? <span className="text-[12px] text-text-muted">No collateral available</span> : null}
        </div>
      </Group>

      <Group name="Covenants and conditions" open={Boolean(open["Covenants and conditions"])} onToggle={() => toggleGroup("Covenants and conditions")}
             changed={changedIn(keys["Covenants and conditions"])}>
        <Select label="Covenant package" value={t.covenant_package} lever={L("covenant_package")} testId="dealdesk-lever-covenants" changed={t.covenant_package !== ask.covenant_package}
                options={[["none", "None"], ["standard", "Standard"], ["enhanced", "Enhanced"]]} onChange={(v) => set("covenant_package", v)} />
        <Select label="Review cycle" value={String(t.review_cycle_months ?? 12)} lever={L("review_cycle_months")} testId="dealdesk-lever-review"
                changed={(t.review_cycle_months ?? 12) !== 12} options={[["12", "Annual"], ["6", "Semi-annual"], ["3", "Quarterly"]]}
                onChange={(v) => set("review_cycle_months", Number(v))} />
        <div className="flex flex-wrap gap-2 md:col-span-2" title={tip(L("covenant_items"))}>
          {Object.entries(COVENANT_ITEM).map(([k, v]) => (
            <Toggle key={k} on={(t.covenant_items ?? []).includes(k)} testId={`dealdesk-lever-covenant-${k}`} onClick={() => listToggle("covenant_items", k)}>{v}</Toggle>))}
        </div>
      </Group>

      <Group name="Relationship" open={Boolean(open.Relationship)} onToggle={() => toggleGroup("Relationship")} changed={changedIn(keys.Relationship)}>
        <div className="flex flex-wrap gap-2 md:col-span-2" title={tip(L("cross_sell"))}>
          {Object.keys(proposal.business_case?.ancillary_income_sar_mn_pa ?? {}).map((k) => (
            <Toggle key={k} on={(t.cross_sell ?? []).includes(k)} testId={`dealdesk-lever-crosssell-${k}`} onClick={() => listToggle("cross_sell", k)}>
              {CROSS_SELL[k] ?? k} · {money(proposal.business_case.ancillary_income_sar_mn_pa[k])} a year</Toggle>))}
        </div>
        {res ? (
          <p className="text-[12px] text-text-secondary md:col-span-2" data-testid="dealdesk-relationship-raroc">
            Deal RAROC <span className="font-semibold tabular-nums text-text-primary">{rate(res.metrics.lifetime_raroc)}</span> · relationship RAROC{" "}
            <span className="font-semibold tabular-nums text-text-primary">{rate(res.metrics.relationship_raroc)}</span></p>) : null}
      </Group>

      <div className="flex items-center justify-end border-t border-border pt-3">
        <SecondaryButton onClick={() => void apply({ ...ask })} data-testid="dealdesk-lever-reset"><RotateCcw size={13} /> Back to the ask</SecondaryButton>
      </div>
    </div>
  );
}
