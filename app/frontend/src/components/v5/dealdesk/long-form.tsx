"use client";

/**
 * PLAN_R6 D1: the long-form credit application on screen, in eight collapsible
 * sections. An uploaded memo opens here prefilled: each field read from the
 * file carries a "from file" mark, and empty fields are highlighted so the user
 * reviews and confirms before anything is analysed.
 */

import * as React from "react";
import { ChevronDown, Plus, Trash2 } from "lucide-react";

import { cn } from "@/lib/utils";
import { FACILITY, RATINGS, STRUCTURE } from "@/lib/v5/dealdesk";
import { fmt } from "@/lib/v5/format";
import { InfoPopover } from "@/components/ui/info-popover"; // R13 X: notes behind the (i)

export interface LongLine {
  facility_type: string; structure: string; currency: string; amount: string; tenor_years: string; margin_bps: string;
  upfront_fee_bps: string; commitment_fee_bps: string; commission_bps: string; amortisation: string; grace_years: string; purpose: string;
}
export interface LongCollateral { type: string; value: string; valuation_date: string }
export interface LongGuarantee { type: string; guarantor: string; coverage_pct: string }
export interface LongYear { year: string; [metric: string]: string }
export interface LongState {
  connected_parties: string; ownership: { holder: string; share: string }[];
  rating_date: string; external_agency: string;
  years: LongYear[]; lines: LongLine[]; collateral: LongCollateral[]; guarantees: LongGuarantee[];
  receivables_assignment: boolean; cash_margin_pct: string;
  covenants: { type: string; threshold: string }[]; conditions: string;
  existing_exposure: string; ancillary: Record<string, string>;
  rm: string; business_unit: string;
}

export const METRICS: [string, string][] = [
  ["revenue", "Revenue"], ["ebitda", "EBITDA"], ["net_income", "Net income"], ["total_debt", "Total debt"], ["cash", "Cash"],
  ["equity", "Equity"], ["operating_cash_flow", "Operating cash flow"], ["capex", "Capex"], ["interest", "Interest"],
  ["debt_service", "Debt service (optional)"],
];
const ANCILLARY: [string, string][] = [["cash_management", "Cash management"], ["payroll", "Payroll"], ["fx", "FX"], ["trade", "Trade"], ["deposits", "Deposits"]];
const COLLATERAL = ["real estate", "receivables", "cash", "shares", "plant and equipment", "vehicles"];
const GUARANTEES = ["corporate", "personal", "bank", "government", "kafalah"];
const AMORT = ["equal", "balloon", "bullet"];
const UNFUNDED = ["performance_lg", "financial_lg", "trade_lc"];

export const emptyLine = (): LongLine => ({ facility_type: "term_loan", structure: "murabaha", currency: "SAR", amount: "", tenor_years: "5", margin_bps: "",
  upfront_fee_bps: "", commitment_fee_bps: "", commission_bps: "", amortisation: "equal", grace_years: "0", purpose: "" });

export function emptyLong(): LongState {
  return { connected_parties: "", ownership: [], rating_date: "", external_agency: "",
    years: ["2023", "2024", "2025"].map((y) => ({ year: y, ...Object.fromEntries(METRICS.map(([k]) => [k, ""])) })),
    lines: [emptyLine()], collateral: [], guarantees: [], receivables_assignment: false, cash_margin_pct: "",
    covenants: [], conditions: "", existing_exposure: "", ancillary: {}, rm: "", business_unit: "Corporate Banking" };
}

const s = (v: unknown) => (v === null || v === undefined ? "" : String(v));

/** The long-form state from an extraction (`long` from the server). */
export function longFromExtract(long: Record<string, unknown> | undefined): LongState {
  const base = emptyLong();
  if (!long) return base;
  const L = long as Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
  const years = Array.isArray(L.years) && L.years.length
    ? L.years.map((y: Record<string, unknown>) => ({ year: s(y.year), ...Object.fromEntries(METRICS.map(([k]) => [k, s(y[k])])) }))
    : base.years;
  return {
    ...base,
    connected_parties: s(L.connected_parties), ownership: Array.isArray(L.ownership) ? L.ownership.map((o: any) => ({ holder: s(o.holder), share: s(o.share) })) : [], // eslint-disable-line @typescript-eslint/no-explicit-any
    rating_date: s(L.rating_date), external_agency: s(L.external_agency), years,
    lines: Array.isArray(L.lines) && L.lines.length ? L.lines.map((l: Record<string, unknown>) => ({ ...emptyLine(), ...Object.fromEntries(Object.entries(l).map(([k, v]) => [k, s(v)])) })) : base.lines,
    collateral: Array.isArray(L.collateral) ? L.collateral.map((c: Record<string, unknown>) => ({ type: s(c.type).replace("_", " ").replace("plant equipment", "plant and equipment"), value: s(c.value), valuation_date: s(c.valuation_date) })) : [],
    guarantees: Array.isArray(L.guarantees) ? L.guarantees.map((g: Record<string, unknown>) => ({ type: s(g.type), guarantor: s(g.guarantor), coverage_pct: s(g.coverage_pct) })) : [],
    receivables_assignment: Boolean(L.receivables_assignment), cash_margin_pct: s(L.cash_margin_pct),
    conditions: s(L.conditions), existing_exposure: s(L.existing_exposure), rm: s(L.rm), business_unit: s(L.business_unit) || base.business_unit,
  };
}

const n = (v: string) => (v.trim() === "" ? null : Number(v.replace(/,/g, "")));
const bad = (v: string) => v.trim() !== "" && !Number.isFinite(Number(v.replace(/,/g, "")));

/** Plain-word validation messages; empty when the form can be confirmed. */
export function validateLong(flat: Record<string, string>, L: LongState): string[] {
  const m: string[] = [];
  if (!flat.name?.trim()) m.push("1 Obligor: enter the obligor's name.");
  if (!flat.sector?.trim()) m.push("1 Obligor: choose a sector.");
  if (!RATINGS.includes(flat.internal_rating as (typeof RATINGS)[number])) m.push("2 Ratings: choose the internal rating.");
  if (L.rating_date && !/^\d{4}-\d{2}-\d{2}$/.test(L.rating_date)) m.push("2 Ratings: the internal rating date must be a date (YYYY-MM-DD).");
  L.years.forEach((y) => METRICS.forEach(([k, lab]) => { if (bad(y[k] ?? "")) m.push(`3 Financials: ${lab} ${y.year} must be a number (SAR million).`); }));
  if (!L.lines.length) m.push("4 Facility lines: add at least one line.");
  L.lines.forEach((l, i) => {
    const a = n(l.amount), t = n(l.tenor_years), g = n(l.grace_years) ?? 0;
    if (a === null || !(a > 0)) m.push(`4 Line ${i + 1}: the amount must be a number above zero (million).`);
    if (t === null || !Number.isInteger(t) || t < 1 || t > 10) m.push(`4 Line ${i + 1}: the tenor must be a whole number of years from 1 to 10.`);
    else if (g >= t) m.push(`4 Line ${i + 1}: the grace period must be shorter than the tenor.`);
    if (!UNFUNDED.includes(l.facility_type) && (n(l.margin_bps) === null || bad(l.margin_bps))) m.push(`4 Line ${i + 1}: state the margin in basis points.`);
    (["upfront_fee_bps", "commitment_fee_bps", "commission_bps"] as const).forEach((k) => { if (bad(l[k])) m.push(`4 Line ${i + 1}: fees must be numbers in basis points.`); });
  });
  L.collateral.forEach((c, i) => {
    if (!c.type) m.push(`5 Collateral ${i + 1}: choose a type.`);
    const v = n(c.value);
    if (v === null || !(v >= 0)) m.push(`5 Collateral ${i + 1}: the value must be a number of zero or more (million).`);
    if (c.valuation_date && !/^\d{4}-\d{2}-\d{2}$/.test(c.valuation_date)) m.push(`5 Collateral ${i + 1}: the valuation date must be a date (YYYY-MM-DD).`);
  });
  L.guarantees.forEach((g, i) => {
    const c = n(g.coverage_pct);
    if (c !== null && !(c >= 0 && c <= 100)) m.push(`5 Guarantee ${i + 1}: the cover must be between 0% and 100%.`);
  });
  const cm = n(L.cash_margin_pct);
  if (cm !== null && !(cm >= 0 && cm <= 100)) m.push("5 Security: the cash margin must be between 0% and 100%.");
  if (bad(L.existing_exposure)) m.push("7 Relationship: the existing exposure must be a number (SAR million).");
  return Array.from(new Set(m));
}

/** The body the server expects: `long` with numbers as numbers. */
export function longBody(L: LongState): Record<string, unknown> {
  const num = (v: string) => (v.trim() === "" ? null : Number(v.replace(/,/g, "")));
  const body: Record<string, unknown> = {
    connected_parties: L.connected_parties, ownership: L.ownership.filter((o) => o.holder.trim()),
    rating_date: L.rating_date, external_agency: L.external_agency,
    years: L.years.map((y) => ({ year: Number(y.year), ...Object.fromEntries(METRICS.map(([k]) => [k, num(y[k] ?? "")])) })),
    lines: L.lines.map((l) => ({ ...l, amount: num(l.amount), tenor_years: num(l.tenor_years), margin_bps: num(l.margin_bps),
      upfront_fee_bps: num(l.upfront_fee_bps), commitment_fee_bps: num(l.commitment_fee_bps), commission_bps: num(l.commission_bps), grace_years: num(l.grace_years) })),
    collateral: L.collateral.map((c) => ({ ...c, value: num(c.value) })),
    guarantees: L.guarantees.map((g) => ({ ...g, coverage_pct: num(g.coverage_pct) })),
    receivables_assignment: L.receivables_assignment, cash_margin_pct: num(L.cash_margin_pct),
    covenants: L.covenants.filter((c) => c.type.trim()).map((c) => ({ type: c.type, threshold: num(c.threshold) })),
    conditions: L.conditions, existing_exposure: num(L.existing_exposure),
    ancillary: Object.fromEntries(Object.entries(L.ancillary).map(([k, v]) => [k, num(v)])), rm: L.rm, business_unit: L.business_unit,
  };
  return body;
}

const inputCls = "h-8 rounded-md border bg-surface px-2 text-[13px] text-text-primary";

function Field({ label, k, marks, value, children, wide }: {
  label: string; k: string; marks: Marks; value: string; children: React.ReactNode; wide?: boolean;
}) {
  const fromFile = marks.found.has(k);
  const missing = marks.active && !fromFile && value.trim() === "";
  return (
    <label className={cn("flex flex-col gap-1 text-[12px] text-text-secondary", wide && "col-span-2 md:col-span-4")} data-testid={`longform-field-${k}`}
           data-from-file={fromFile ? "yes" : undefined} data-missing={missing ? "yes" : undefined}>
      <span className="flex items-center gap-1">{label}
        {fromFile ? <span className="rounded bg-positive/10 px-1 text-[10px] text-positive">from file</span> : null}
        {missing ? <span className="rounded bg-warning/15 px-1 text-[10px] text-warning">missing</span> : null}</span>
      <span className={cn("contents", missing && "[&>*]:border-warning [&>*]:bg-warning/5", fromFile && "[&>*]:border-positive/50")}>{children}</span>
    </label>);
}

export interface Marks { active: boolean; found: Set<string> }

function Section({ n: no, title, open, onToggle, children, summary }: { n: number; title: string; open: boolean; onToggle: () => void; children: React.ReactNode; summary?: string }) {
  return (
    <section className="rounded-lg border border-border" data-testid={`longform-section-${no}`}>
      <button type="button" onClick={onToggle} aria-expanded={open} className="flex w-full items-center gap-2 px-3 py-2 text-left">
        <span className="flex h-5 w-5 items-center justify-center rounded-full bg-accent text-[11px] text-accent-contrast">{no}</span>
        <span className="text-[13px] font-medium text-text-primary">{title}</span>
        {summary ? <span className="ml-2 truncate text-[12px] text-text-muted">{summary}</span> : null}
        <ChevronDown size={14} className={cn("ml-auto text-text-muted transition-transform", open && "rotate-180")} />
      </button>
      {open ? <div className="border-t border-border px-3 py-3">{children}</div> : null}
    </section>);
}

const SECTOR_OPTIONS = ["Agriculture and Agri-processing", "Chemicals", "Construction", "Healthcare", "Hospitality", "Information Technology", "Manufacturing",
  "Metals and Mining", "Power and Utilities", "Real Estate", "Retail Trade", "Telecommunications", "Transport and Logistics", "Wholesale Trade"];

export function LongForm({ flat, setFlat, long, setLong, marks, groups }: {
  flat: Record<string, string>; setFlat: (v: Record<string, string>) => void;
  long: LongState; setLong: (v: LongState) => void; marks: Marks;
  groups: { group_id: string; group_name: string; ead_sar_mn: number }[];
}) {
  const [open, setOpen] = React.useState<Record<number, boolean>>({ 1: true, 2: true, 3: true, 4: true, 5: true, 6: true, 7: true, 8: true });
  const tog = (i: number) => setOpen({ ...open, [i]: !open[i] });
  const up = (patch: Partial<LongState>) => setLong({ ...long, ...patch });
  const text = (k: string, label: string, opts?: { wide?: boolean; placeholder?: string }) => (
    <Field key={k} label={label} k={k} marks={marks} value={flat[k] ?? ""} wide={opts?.wide}>
      <input value={flat[k] ?? ""} placeholder={opts?.placeholder} onChange={(e) => setFlat({ ...flat, [k]: e.target.value })} data-testid={`longform-${k}`}
             className={cn(inputCls, "border-border")} /></Field>);
  const select = (k: string, label: string, options: string[], labels: Record<string, string> = {}) => (
    <Field key={k} label={label} k={k} marks={marks} value={flat[k] ?? ""}>
      <select value={flat[k] ?? ""} onChange={(e) => setFlat({ ...flat, [k]: e.target.value })} data-testid={`longform-${k}`} className={cn(inputCls, "border-border")}>
        {options.map((o) => <option key={o} value={o}>{labels[o] ?? (o || "None")}</option>)}</select></Field>);
  const lt = (k: keyof LongState, label: string, opts?: { wide?: boolean; placeholder?: string }) => (
    <Field key={k} label={label} k={k} marks={marks} value={String(long[k] ?? "")} wide={opts?.wide}>
      <input value={String(long[k] ?? "")} placeholder={opts?.placeholder} onChange={(e) => up({ [k]: e.target.value } as Partial<LongState>)}
             data-testid={`longform-${k}`} className={cn(inputCls, "border-border")} /></Field>);
  const cell = (k: string, value: string, onChange: (v: string) => void, opts?: { w?: string; testId?: string; placeholder?: string }) => {
    const fromFile = marks.found.has(k);
    const missing = marks.active && !fromFile && value.trim() === "";
    return <input value={value} onChange={(e) => onChange(e.target.value)} data-testid={opts?.testId ?? `longform-${k}`} placeholder={opts?.placeholder}
                  data-from-file={fromFile ? "yes" : undefined} data-missing={missing ? "yes" : undefined} title={fromFile ? "Read from the file" : missing ? "Missing: please fill in or confirm" : undefined}
                  className={cn("h-7 rounded border px-1.5 text-[12px] tabular-nums", opts?.w ?? "w-24", missing ? "border-warning bg-warning/5" : fromFile ? "border-positive/50 bg-surface" : "border-border bg-surface")} />;
  };
  const totalAmount = long.lines.reduce((a, l) => a + (n(l.amount) ?? 0), 0);
  const totalColl = long.collateral.reduce((a, c) => a + (n(c.value) ?? 0), 0);
  const grid = "grid grid-cols-2 gap-x-4 gap-y-2 md:grid-cols-4";
  const rm = (k: "ownership" | "collateral" | "guarantees" | "covenants" | "lines", i: number) => up({ [k]: (long[k] as unknown[]).filter((_, j) => j !== i) } as Partial<LongState>);
  const addBtn = (label: string, onClick: () => void, testId: string) => (
    <button type="button" onClick={onClick} data-testid={testId} className="mt-2 inline-flex items-center gap-1 text-[12px] text-accent hover:underline"><Plus size={12} />{label}</button>);
  const del = (onClick: () => void, label: string) => (
    <button type="button" onClick={onClick} aria-label={label} className="rounded p-1 text-text-muted hover:bg-surface-hover"><Trash2 size={13} /></button>);

  return (
    <div className="flex max-h-[62vh] flex-col gap-2 overflow-y-auto pr-1" data-testid="dealdesk-long-form">
      <Section n={1} title="Obligor and group" open={open[1]} onToggle={() => tog(1)} summary={flat.name}>
        <div className={grid}>
          {text("name", "Obligor")}{text("cr_number", "CR number")}
          <Field label="Group (type to search the book)" k="group_name" marks={marks} value={flat.group_name ?? ""}>
            <input value={flat.group_name ?? ""} list="longform-groups" onChange={(e) => setFlat({ ...flat, group_name: e.target.value })} data-testid="longform-group_name"
                   placeholder="New to bank: leave empty" className={cn(inputCls, "border-border")} /></Field>
          <datalist id="longform-groups">{groups.map((g) => <option key={g.group_id} value={`${g.group_name} (${g.group_id})`}>{`${fmt.sar(g.ead_sar_mn)} in the book`}</option>)}</datalist>
          {select("sector", "Sector", ["", ...SECTOR_OPTIONS])}{text("region", "Region")}
          {lt("connected_parties", "Connected parties (separate with ;)", { wide: true })}
        </div>
        <p className="mt-3 text-[12px] font-medium text-text-secondary">Ownership</p>
        {long.ownership.map((o, i) => (
          <div key={i} className="mt-1 flex items-center gap-2" data-testid={`longform-owner-${i}`}>
            {cell("ownership", o.holder, (v) => up({ ownership: long.ownership.map((x, j) => (j === i ? { ...x, holder: v } : x)) }), { w: "w-72", testId: `longform-owner-${i}-holder`, placeholder: "Shareholder" })}
            {cell("ownership", o.share, (v) => up({ ownership: long.ownership.map((x, j) => (j === i ? { ...x, share: v } : x)) }), { testId: `longform-owner-${i}-share`, placeholder: "Share" })}
            {del(() => rm("ownership", i), "Remove shareholder")}</div>))}
        {addBtn("Add shareholder", () => up({ ownership: [...long.ownership, { holder: "", share: "" }] }), "longform-add-owner")}
      </Section>

      <Section n={2} title="Ratings" open={open[2]} onToggle={() => tog(2)} summary={flat.internal_rating}>
        <div className={grid}>
          {select("internal_rating", "Internal rating", ["", ...RATINGS])}{lt("rating_date", "Internal rating date", { placeholder: "YYYY-MM-DD" })}
          {lt("external_agency", "External agency", { placeholder: "e.g. Fitch, Moody's, S&P" })}{select("external_rating", "External grade", ["", ...RATINGS], { "": "Unrated" })}
          {select("simah_flag", "SIMAH", ["clear", "watch", "default", ""], { "": "Not stated", clear: "Clear", watch: "Watch", default: "Default" })}
        </div>
      </Section>

      <Section n={3} title="Financials, 3 years (SAR million)" open={open[3]} onToggle={() => tog(3)}>
        <table className="border-collapse text-[12px]" data-testid="longform-financials">
          <thead><tr><th className="px-2 py-1 text-left font-medium text-text-muted">SAR million</th>
            {long.years.map((y, yi) => <th key={yi} className="px-1 py-1">{cell("year", y.year, (v) => up({ years: long.years.map((x, j) => (j === yi ? { ...x, year: v } : x)) }), { w: "w-20", testId: `longform-year-${yi}` })}</th>)}</tr></thead>
          <tbody>{METRICS.map(([k, lab]) => (
            <tr key={k}><td className="px-2 py-0.5 text-text-secondary">{lab}</td>
              {long.years.map((y, yi) => <td key={yi} className="px-1 py-0.5">{cell(`fin.${y.year}.${k}`, y[k] ?? "", (v) => up({ years: long.years.map((x, j) => (j === yi ? { ...x, [k]: v } : x)) }), { w: "w-20", testId: `longform-fin-${yi}-${k}` })}</td>)}</tr>))}
          </tbody></table>
      </Section>

      <Section n={4} title="Facility lines" open={open[4]} onToggle={() => tog(4)} summary={`${long.lines.length} line${long.lines.length === 1 ? "" : "s"}, ${fmt.sar(totalAmount)}`}>
        <div className="overflow-x-auto"><table className="border-collapse text-[12px]" data-testid="longform-lines">
          <thead><tr className="text-left text-[11px] text-text-muted">{["Facility", "Structure", "Currency", "Amount (m)", "Tenor (y)", "Margin (bps)", "Upfront (bps)", "Commitment (bps)", "Commission (bps)", "Repayment", "Grace (y)", "Purpose", ""].map((h) => <th key={h} className="px-1 py-1 font-medium">{h}</th>)}</tr></thead>
          <tbody>{long.lines.map((l, i) => {
            const set = (k: keyof LongLine) => (v: string) => up({ lines: long.lines.map((x, j) => (j === i ? { ...x, [k]: v } : x)) });
            const sel = (k: keyof LongLine, options: string[], labels: Record<string, string> = {}) => (
              <select value={l[k]} onChange={(e) => set(k)(e.target.value)} data-testid={`longform-line-${i}-${k}`} data-from-file={marks.found.has(`line.${i}.${k}`) ? "yes" : undefined}
                      className={cn("h-7 rounded border bg-surface px-1 text-[12px]", marks.found.has(`line.${i}.${k}`) ? "border-positive/50" : "border-border")}>
                {options.map((o) => <option key={o} value={o}>{labels[o] ?? o}</option>)}</select>);
            return (
              <tr key={i} data-testid={`longform-line-${i}`}>
                <td className="px-1 py-0.5">{sel("facility_type", Object.keys(FACILITY), FACILITY)}</td>
                <td className="px-1 py-0.5">{sel("structure", Object.keys(STRUCTURE), STRUCTURE)}</td>
                <td className="px-1 py-0.5">{sel("currency", ["SAR", "USD"])}</td>
                {(["amount", "tenor_years", "margin_bps", "upfront_fee_bps", "commitment_fee_bps", "commission_bps"] as const).map((k) => (
                  <td key={k} className="px-1 py-0.5">{cell(`line.${i}.${k}`, l[k], set(k), { w: "w-20", testId: `longform-line-${i}-${k}` })}</td>))}
                <td className="px-1 py-0.5">{sel("amortisation", AMORT)}</td>
                <td className="px-1 py-0.5">{cell(`line.${i}.grace_years`, l.grace_years, set("grace_years"), { w: "w-14", testId: `longform-line-${i}-grace_years` })}</td>
                <td className="px-1 py-0.5">{cell(`line.${i}.purpose`, l.purpose, set("purpose"), { w: "w-56", testId: `longform-line-${i}-purpose` })}</td>
                <td>{long.lines.length > 1 ? del(() => rm("lines", i), `Remove line ${i + 1}`) : null}</td>
              </tr>);
          })}</tbody></table></div>
        {addBtn("Add a facility line", () => up({ lines: [...long.lines, emptyLine()] }), "longform-add-line")}
        {long.lines.length > 1 ? <p className="mt-1 flex items-center gap-1 text-[11px] text-text-muted">Priced as one ask<InfoPopover title="Several lines">Several lines are priced as one ask: amounts added, margin and fees weighted by amount, the longest tenor.</InfoPopover></p> : null}
      </Section>

      <Section n={5} title="Security" open={open[5]} onToggle={() => tog(5)}
               summary={long.collateral.length ? `${fmt.sar(totalColl)} collateral, LTV ${totalColl ? fmt.pct(totalAmount / totalColl) : "–"}` : "unsecured"}>
        <p className="text-[12px] font-medium text-text-secondary">Collateral</p>
        {long.collateral.map((c, i) => (
          <div key={i} className="mt-1 flex flex-wrap items-center gap-2" data-testid={`longform-coll-${i}`}>
            <select value={c.type} onChange={(e) => up({ collateral: long.collateral.map((x, j) => (j === i ? { ...x, type: e.target.value } : x)) })} data-testid={`longform-coll-${i}-type`}
                    className="h-7 rounded border border-border bg-surface px-1 text-[12px]"><option value="">Type</option>{COLLATERAL.map((o) => <option key={o} value={o}>{o}</option>)}</select>
            {cell(`coll.${i}.value`, c.value, (v) => up({ collateral: long.collateral.map((x, j) => (j === i ? { ...x, value: v } : x)) }), { testId: `longform-coll-${i}-value`, placeholder: "Value (m)" })}
            {cell(`coll.${i}.valuation_date`, c.valuation_date, (v) => up({ collateral: long.collateral.map((x, j) => (j === i ? { ...x, valuation_date: v } : x)) }), { w: "w-28", testId: `longform-coll-${i}-valuation_date`, placeholder: "YYYY-MM-DD" })}
            <span className="text-[12px] text-text-muted" data-testid={`longform-coll-${i}-ltv`}>LTV {n(c.value) ? fmt.pct(totalAmount / (n(c.value) as number)) : "–"}</span>
            {del(() => rm("collateral", i), `Remove collateral ${i + 1}`)}</div>))}
        {addBtn("Add collateral", () => up({ collateral: [...long.collateral, { type: "", value: "", valuation_date: "" }] }), "longform-add-collateral")}
        {long.collateral.length > 1 ? <p className="mt-1 text-[12px] text-text-secondary" data-testid="longform-ltv-total">LTV on all collateral: {fmt.pct(totalColl ? totalAmount / totalColl : null)}</p> : null}
        <p className="mt-3 text-[12px] font-medium text-text-secondary">Guarantees</p>
        {long.guarantees.map((g, i) => (
          <div key={i} className="mt-1 flex flex-wrap items-center gap-2" data-testid={`longform-guar-${i}`}>
            <select value={g.type} onChange={(e) => up({ guarantees: long.guarantees.map((x, j) => (j === i ? { ...x, type: e.target.value } : x)) })} data-testid={`longform-guar-${i}-type`}
                    className="h-7 rounded border border-border bg-surface px-1 text-[12px]"><option value="">Type</option>{GUARANTEES.map((o) => <option key={o} value={o}>{o}</option>)}</select>
            {cell(`guar.${i}.guarantor`, g.guarantor, (v) => up({ guarantees: long.guarantees.map((x, j) => (j === i ? { ...x, guarantor: v } : x)) }), { w: "w-64", testId: `longform-guar-${i}-guarantor`, placeholder: "Guarantor" })}
            {cell(`guar.${i}.coverage_pct`, g.coverage_pct, (v) => up({ guarantees: long.guarantees.map((x, j) => (j === i ? { ...x, coverage_pct: v } : x)) }), { w: "w-20", testId: `longform-guar-${i}-coverage_pct`, placeholder: "Cover %" })}
            {del(() => rm("guarantees", i), `Remove guarantee ${i + 1}`)}</div>))}
        {addBtn("Add a guarantee", () => up({ guarantees: [...long.guarantees, { type: "", guarantor: "", coverage_pct: "" }] }), "longform-add-guarantee")}
        <div className={cn(grid, "mt-3")}>
          <label className="flex items-center gap-2 text-[12px] text-text-secondary">
            <input type="checkbox" checked={long.receivables_assignment} onChange={(e) => up({ receivables_assignment: e.target.checked })} data-testid="longform-receivables_assignment" />
            Assignment of receivables</label>
          {lt("cash_margin_pct", "Cash margin (%)")}
        </div>
      </Section>

      <Section n={6} title="Covenants and conditions" open={open[6]} onToggle={() => tog(6)}>
        <div className={grid}>{text("dscr_min", "DSCR minimum (x)")}{text("leverage_max", "Debt/EBITDA maximum (x)")}</div>
        {long.covenants.map((c, i) => (
          <div key={i} className="mt-1 flex items-center gap-2" data-testid={`longform-cov-${i}`}>
            {cell("covenants", c.type, (v) => up({ covenants: long.covenants.map((x, j) => (j === i ? { ...x, type: v } : x)) }), { w: "w-64", testId: `longform-cov-${i}-type`, placeholder: "Covenant, e.g. Current ratio minimum" })}
            {cell("covenants", c.threshold, (v) => up({ covenants: long.covenants.map((x, j) => (j === i ? { ...x, threshold: v } : x)) }), { w: "w-20", testId: `longform-cov-${i}-threshold`, placeholder: "Level" })}
            {del(() => rm("covenants", i), `Remove covenant ${i + 1}`)}</div>))}
        {addBtn("Add a covenant", () => up({ covenants: [...long.covenants, { type: "", threshold: "" }] }), "longform-add-covenant")}
        <Field label="Conditions (precedent and subsequent, reporting)" k="conditions" marks={marks} value={long.conditions} wide>
          <textarea value={long.conditions} onChange={(e) => up({ conditions: e.target.value })} rows={3} data-testid="longform-conditions"
                    className="rounded-md border border-border bg-surface px-2 py-1 text-[13px] text-text-primary" /></Field>
      </Section>

      <Section n={7} title="Relationship" open={open[7]} onToggle={() => tog(7)}>
        <div className={grid}>
          {lt("existing_exposure", "Existing exposure (SAR million)")}
          {ANCILLARY.map(([k, lab]) => (
            <Field key={k} label={`Ancillary: ${lab} (SAR m p.a.)`} k={`anc.${k}`} marks={{ active: false, found: marks.found }} value={long.ancillary[k] ?? ""}>
              <input value={long.ancillary[k] ?? ""} onChange={(e) => up({ ancillary: { ...long.ancillary, [k]: e.target.value } })} data-testid={`longform-anc-${k}`}
                     className={cn(inputCls, "border-border")} /></Field>))}
        </div>
      </Section>

      <Section n={8} title="RM and business unit" open={open[8]} onToggle={() => tog(8)}>
        <div className={grid}>{text("rm", "Relationship manager")}{lt("business_unit", "Business unit")}</div>
      </Section>
    </div>);
}
