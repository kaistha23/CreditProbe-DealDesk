"use client";

/**
 * New proposal: a short form, or a credit memo (.docx) the assistant reads
 * into the proposal schema. Every extracted field shows where in the memo it
 * came from and a confidence chip; the user corrects and confirms before
 * anything is analysed.
 */

import * as React from "react";
import { FileUp, X } from "lucide-react";

import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { type IngestField, type Ingested, FACILITY, RATINGS, STRUCTURE, dealdesk } from "@/lib/v5/dealdesk";

import { Chip, PrimaryButton, SecondaryButton, tableCls, tdCls, thCls } from "./kit";
import { type LongState, LongForm, emptyLong, longBody, longFromExtract, validateLong } from "./long-form";
import { friendlyMessage } from "@/lib/v5/errors";
import { InfoPopover } from "@/components/ui/info-popover"; // R13 X: notes behind the (i)
import { NewFromDocuments } from "./intake"; // R16 i: start from the customer's documents

const FORM: { key: string; label: string; kind: "text" | "number" | "select" | "group"; options?: string[]; def: string }[] = [
  { key: "name", label: "Obligor", kind: "text", def: "" },
  { key: "cr_number", label: "CR number", kind: "text", def: "" },
  { key: "group_name", label: "Group (type to search the book)", kind: "group", def: "" },
  { key: "sector", label: "Sector", kind: "select", def: "Wholesale Trade",
    options: ["Agriculture and Agri-processing", "Chemicals", "Construction", "Healthcare", "Hospitality", "Information Technology", "Manufacturing",
              "Metals and Mining", "Power and Utilities", "Real Estate", "Retail Trade", "Telecommunications", "Transport and Logistics", "Wholesale Trade"] },
  { key: "internal_rating", label: "Internal rating", kind: "select", options: [...RATINGS], def: "BBB" },
  { key: "external_rating", label: "External rating", kind: "select", options: ["", ...RATINGS], def: "" },
  { key: "facility_type", label: "Facility", kind: "select", options: Object.keys(FACILITY), def: "term_loan" },
  { key: "structure", label: "Structure", kind: "select", options: Object.keys(STRUCTURE), def: "murabaha" },
  { key: "currency", label: "Currency", kind: "select", options: ["SAR", "USD"], def: "SAR" },
  { key: "amount", label: "Amount (million)", kind: "number", def: "100" },
  { key: "tenor_years", label: "Tenor (years)", kind: "number", def: "5" },
  { key: "margin_bps", label: "Margin (bps)", kind: "number", def: "200" },
  { key: "upfront_fee_bps", label: "Upfront fee (bps)", kind: "number", def: "50" },
  { key: "revenue", label: "Revenue (million)", kind: "number", def: "" },
  { key: "ebitda", label: "EBITDA (million)", kind: "number", def: "" },
  { key: "total_debt", label: "Total debt (million)", kind: "number", def: "" },
  { key: "collateral_type", label: "Collateral type", kind: "select", def: "",
    options: ["", "real estate", "receivables", "cash", "shares", "plant and equipment", "vehicles"] },
  { key: "collateral_value", label: "Collateral value (million)", kind: "number", def: "" },
  { key: "guarantee_type", label: "Guarantee type", kind: "select", def: "", options: ["", "corporate", "personal", "bank", "government", "kafalah"] },
  { key: "guarantor", label: "Guarantor", kind: "text", def: "" },
  { key: "dscr_min", label: "Covenant: DSCR minimum (x)", kind: "number", def: "" },
  { key: "leverage_max", label: "Covenant: Debt/EBITDA maximum (x)", kind: "number", def: "" },
];
const OPTION_LABEL: Record<string, string> = { "": "None" };

function confTone(c: number): "positive" | "warning" | "negative" {
  return c >= 0.9 ? "positive" : c >= 0.7 ? "warning" : "negative";
}

export function NewProposal({ onClose, onCreated }: { onClose: () => void; onCreated: (id: string) => void }) {
  const [mode, setMode] = React.useState<"docs" | "form" | "long" | "memo">("docs"); // R16 i: documents first
  const [long, setLong] = React.useState<LongState>(emptyLong);
  const [tried, setTried] = React.useState(false);
  const [values, setValues] = React.useState<Record<string, string>>(Object.fromEntries(FORM.map((f) => [f.key, f.def])));
  const [ingested, setIngested] = React.useState<Ingested | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const [groups, setGroups] = React.useState<{ group_id: string; group_name: string; ead_sar_mn: number }[]>([]);
  React.useEffect(() => {
    const q = values.group_name ?? "";
    const t = setTimeout(() => { void dealdesk.groups(q).then((r) => setGroups(r.groups)).catch(() => setGroups([])); }, 150);
    return () => clearTimeout(t);
  }, [values.group_name]);

  const upload = async (file: File | undefined) => {
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const r = await dealdesk.ingest(file);
      setIngested(r);
      setValues((v) => ({ ...v, ...Object.fromEntries(r.fields.map((f) => [f.field, f.value === null || f.value === undefined ? "" : String(f.value)])) }));
      // PLAN_R6 D1: the file opens in the form it belongs to, prefilled, for review before anything is analysed
      setLong(longFromExtract(r.long));
      setMode(r.form === "short" ? "form" : "long");
    } catch (e) {
      setError(friendlyMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const problems = mode === "long" ? validateLong(values, long) : [];
  const marks = React.useMemo(() => ({
    active: ingested !== null,
    found: new Set<string>([...(ingested?.fields ?? []).filter((f) => f.value !== null && f.value !== undefined).map((f) => f.field), ...(ingested?.long_found ?? [])]),
  }), [ingested]);

  const create = async () => {
    if (mode === "long" && problems.length) { setTried(true); return; }
    setBusy(true);
    setError("");
    try {
      const source = ingested ? { filename: ingested.filename, fields: ingested.fields, form: mode === "long" ? "long" : "short" } : { form: mode === "long" ? "long" : true };
      const p = await dealdesk.createFromFields(values, source, mode === "long" ? longBody(long) : undefined);
      onCreated(p.proposal_id);
    } catch (e) {
      setError(friendlyMessage(e));
      setBusy(false);
    }
  };

  const field = (f: (typeof FORM)[number]) => (
    <label key={f.key} className="flex flex-col gap-1 text-[12px] text-text-secondary">{f.label}
      {f.kind === "group" ? (<>
        <input value={values[f.key]} list="dealdesk-groups" onChange={(e) => setValues({ ...values, [f.key]: e.target.value })} data-testid={`dealdesk-form-${f.key}`}
               placeholder="New to bank: leave empty" className="h-8 rounded-md border border-border bg-surface px-2 text-[13px] text-text-primary" />
        <datalist id="dealdesk-groups">{groups.map((g) => <option key={g.group_id} value={`${g.group_name} (${g.group_id})`}>{`SAR ${g.ead_sar_mn.toFixed(1)}m in the book`}</option>)}</datalist>
      </>) : f.kind === "select" ? (
        <select value={values[f.key]} onChange={(e) => setValues({ ...values, [f.key]: e.target.value })} data-testid={`dealdesk-form-${f.key}`}
                className="h-8 rounded-md border border-border bg-surface px-2 text-[13px] text-text-primary">
          {f.options?.map((o) => <option key={o} value={o}>{OPTION_LABEL[o] ?? FACILITY[o] ?? STRUCTURE[o] ?? o}</option>)}</select>
      ) : (
        <input value={values[f.key]} onChange={(e) => setValues({ ...values, [f.key]: e.target.value })} data-testid={`dealdesk-form-${f.key}`}
               inputMode={f.kind === "number" ? "decimal" : undefined}
               className="h-8 rounded-md border border-border bg-surface px-2 text-[13px] text-text-primary" />)}
    </label>);

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-auto bg-black/30 p-8" role="dialog" aria-modal="true"
         aria-label="New proposal" data-testid="dealdesk-new-dialog">
      <Card className="w-full max-w-5xl p-6">
        <div className="mb-4 flex items-center gap-3">
          <h2 className="text-[16px] font-semibold text-text-primary">New proposal</h2>
          <div className="inline-flex rounded-md border border-border p-0.5" role="tablist">
            {(["docs", "form", "long", "memo"] as const).map((m) => (
              <button key={m} type="button" role="tab" aria-selected={mode === m} onClick={() => setMode(m)} data-testid={`dealdesk-new-${m}`}
                      className={cn("h-7 rounded px-3 text-[12px]", mode === m ? "bg-accent text-accent-contrast" : "text-text-secondary")}>
                {m === "docs" ? "Customer documents" : m === "form" ? "Short form" : m === "long" ? "Long form" : "Upload a memo"}</button>))}
          </div>
          <button type="button" onClick={onClose} aria-label="Close" className="ml-auto rounded-md p-1 text-text-muted hover:bg-surface-hover"><X size={16} /></button>
        </div>

        {mode === "docs" ? (
          <NewFromDocuments base={Object.fromEntries(FORM.map((f) => [f.key, f.def]))}
                            sectors={FORM.find((f) => f.key === "sector")?.options ?? []} onCreated={onCreated} />) : null}

        {mode === "memo" && !ingested ? (
          <label className="flex h-40 cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-border text-[13px] text-text-secondary hover:border-accent"
                 data-testid="dealdesk-memo-drop">
            <FileUp size={20} />{busy ? "Reading the file…" : "Choose a long-form credit memo (.docx) or a short-form sheet (.xlsx)"}
            <input type="file" accept=".docx,.xlsx" className="sr-only" data-testid="dealdesk-memo-file" onChange={(e) => void upload(e.target.files?.[0])} />
          </label>) : null}

        {ingested && mode !== "memo" ? (
          <p className="mb-3 rounded-md bg-surface-hover px-3 py-2 text-[13px] text-text-primary" data-testid="dealdesk-ingested-summary">
            <span className="font-medium">{ingested.fields.filter((f) => f.value !== null && f.value !== undefined).length} of {ingested.fields.length} fields read from {ingested.filename}; please confirm.</span>{" "}
            <InfoPopover title="Read from the file">Fields marked from file were read from it; fields highlighted missing were not stated. Review, then Confirm and open.</InfoPopover>{" "}
            <button type="button" className="text-accent underline" onClick={() => setMode("memo")}>Show where each field came from</button></p>) : null}

        {mode === "memo" && ingested ? (
          <div className="mb-4 overflow-auto" data-testid="dealdesk-ingested">
            <p className="mb-2 text-[13px] font-medium text-text-primary" data-testid="dealdesk-ingested-summary">
              {ingested.fields.filter((f) => f.value !== null && f.value !== undefined).length} of {ingested.fields.length} fields read from {ingested.filename}; please confirm</p>
            <table className={tableCls}>
              <thead><tr><th className={thCls}>Field</th><th className={thCls}>Value</th><th className={thCls}>Source in the memo</th><th className={thCls}>Confidence</th></tr></thead>
              <tbody>{ingested.fields.map((f: IngestField) => (
                <tr key={f.field} data-testid={`dealdesk-ingested-${f.field}`}>
                  <td className={tdCls}>{f.label}</td>
                  <td className={tdCls}><input value={values[f.field] ?? ""} onChange={(e) => setValues({ ...values, [f.field]: e.target.value })}
                                               className="h-7 w-full rounded border border-border bg-surface px-2 text-[12px]" /></td>
                  <td className={cn(tdCls, "text-text-muted")}>{f.source}</td>
                  <td className={tdCls}><Chip tone={confTone(f.confidence)}>{Math.round(f.confidence * 100)}%</Chip></td>
                </tr>))}</tbody>
            </table>
          </div>) : null}

        {mode === "form" ? <div className="grid grid-cols-2 gap-x-4 gap-y-2 md:grid-cols-4" data-testid="dealdesk-short-form">{FORM.map((f) => {
          const fromFile = marks.found.has(f.key);
          const missing = marks.active && !fromFile && !(values[f.key] ?? "").trim();
          return <div key={f.key} data-from-file={fromFile ? "yes" : undefined} data-missing={missing ? "yes" : undefined}
                      className={cn("rounded-md", missing && "ring-1 ring-warning", fromFile && "ring-1 ring-positive/40")}>{field(f)}</div>;
        })}</div> : null}

        {mode === "long" ? <LongForm flat={values} setFlat={setValues} long={long} setLong={setLong} marks={marks} groups={groups} /> : null}
        {mode === "long" && tried && problems.length ? (
          <ul className="mt-3 list-disc pl-5 text-[12px] text-negative" role="alert" data-testid="longform-errors">{problems.map((m) => <li key={m}>{m}</li>)}</ul>) : null}

        {error ? <p className="mt-3 text-[12px] text-negative" role="alert">{error}</p> : null}
        {mode !== "docs" ? <div className="mt-6 flex justify-end gap-2">
          <SecondaryButton onClick={onClose}>Cancel</SecondaryButton>
          <PrimaryButton onClick={() => void create()} disabled={busy || (mode !== "long" && !values.name?.trim()) || (mode === "memo" && !ingested)} data-testid="dealdesk-new-create">
            Confirm and open</PrimaryButton>
        </div> : null}
      </Card>
    </div>
  );
}
