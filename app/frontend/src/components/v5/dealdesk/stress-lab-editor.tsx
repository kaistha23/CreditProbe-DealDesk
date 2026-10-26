"use client";

/**
 * PLAN_R12 Session D (I22-3, I19-3, I19-4): build your own scenario, for this deal or for the bank, and load the bank's
 * ICAAP or regulator set (SAMA, CBUAE, CBO) from the CSV or JSON template. Every save is a new version in
 * dd_stress_scenario; a bank scenario waits for a checker other than its maker. Exported for Session U:
 *
 *   ScenarioEditor   the form, the pending approvals and the set import (a dialog body or a panel)
 */

import * as React from "react";
import { Check, Download, Upload, X } from "lucide-react";

import { cn } from "@/lib/utils";
import { SHOCK_FIELDS, Stress2Error, shocksFrom, stress2Api, type ScenarioDef } from "@/lib/v5/dealdesk-stress2";

import { Chip, PrimaryButton, SecondaryButton, Section } from "./kit";

const FAMILIES = [["macro", "Macro"], ["sector", "Sector"], ["borrower", "Borrower"], ["collateral", "Collateral"], ["rating", "Rating"],
  ["combined", "Combined"], ["custom", "Your scenarios"]] as const;
const SEVERITIES = ["mild", "moderate", "severe"] as const;
const AUTHORITIES = ["ICAAP", "SAMA", "CBUAE", "CBO", "Internal"] as const;

const inputCls = "h-8 w-full rounded-md border border-border bg-surface px-2 text-[12px] text-text-primary placeholder:text-text-muted focus:border-accent focus:outline-none";
const labelCls = "text-[11px] font-medium text-text-secondary";

function Field({ label, children, htmlFor }: { label: string; children: React.ReactNode; htmlFor: string }) {
  return <label htmlFor={htmlFor} className="flex min-w-0 flex-col gap-1"><span className={labelCls}>{label}</span>{children}</label>;
}

function errorsOf(e: unknown): string[] {
  if (e instanceof Stress2Error && e.errors.length) return e.errors.map((x) => `${x.field}: ${x.message}`);
  return [e instanceof Error ? e.message : String(e)];
}

export function ScenarioEditor({ proposalId, canApprove = true, onSaved, onClose }: {
  proposalId?: string; canApprove?: boolean; onSaved?: (s: ScenarioDef) => void; onClose?: () => void;
}) {
  const [label, setLabel] = React.useState("");
  const [family, setFamily] = React.useState<string>("custom");
  const [severity, setSeverity] = React.useState<string>("moderate");
  const [scope, setScope] = React.useState<"deal" | "bank">(proposalId ? "deal" : "bank");
  const [basis, setBasis] = React.useState("");
  const [reason, setReason] = React.useState("");
  const [vals, setVals] = React.useState<Record<string, string>>({});
  const [gv, setGv] = React.useState(false);
  const [msg, setMsg] = React.useState<{ ok: boolean; lines: string[] } | null>(null);
  const [pending, setPending] = React.useState<ScenarioDef[]>([]);
  const [busy, setBusy] = React.useState(false);
  const loadPending = React.useCallback(() => { stress2Api.pending().then((p) => setPending(p.pending)).catch(() => setPending([])); }, []);
  React.useEffect(() => { loadPending(); }, [loadPending]);

  const save = async () => {
    setBusy(true);
    setMsg(null);
    try {
      const r = await stress2Api.save({ scope, proposal_id: scope === "deal" ? proposalId : undefined, reason,
        scenario: { label, family, severity: severity as ScenarioDef["severity"], basis, shocks: shocksFrom(vals, gv) } });
      setMsg({ ok: true, lines: [r.scenario.status === "approved" ? `Saved: ${r.scenario.label} (version ${r.scenario.version}) is in this deal's ladder.`
        : `Sent for approval: ${r.scenario.label} (version ${r.scenario.version}) waits for a checker.`] });
      onSaved?.(r.scenario);
      loadPending();
    } catch (e) {
      setMsg({ ok: false, lines: errorsOf(e) });
    } finally {
      setBusy(false);
    }
  };
  const decide = async (s: ScenarioDef, approve: boolean) => {
    try {
      await stress2Api.decide(s.scenario_id, s.version, approve, approve ? "Checked" : "Returned to the maker");
      loadPending();
    } catch (e) {
      setMsg({ ok: false, lines: errorsOf(e) });
    }
  };
  return (
    <Section title="Build a scenario" testId="stress2-editor"
             action={onClose ? <button type="button" onClick={onClose} aria-label="Close" className="rounded p-1 text-text-muted hover:bg-surface-hover"><X size={16} /></button> : undefined}>
      <div className="grid gap-3 md:grid-cols-4">
        <div className="md:col-span-2"><Field label="Name" htmlFor="se-label"><input id="se-label" className={inputCls} value={label} onChange={(e) => setLabel(e.target.value)} placeholder="Key contract not renewed" data-testid="stress2-editor-label" /></Field></div>
        <Field label="Family" htmlFor="se-family">
          <select id="se-family" className={inputCls} value={family} onChange={(e) => setFamily(e.target.value)}>{FAMILIES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
        </Field>
        <Field label="Severity" htmlFor="se-sev">
          <select id="se-sev" className={inputCls} value={severity} onChange={(e) => setSeverity(e.target.value)}>{SEVERITIES.map((k) => <option key={k} value={k}>{k}</option>)}</select>
        </Field>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6" data-testid="stress2-editor-shocks">
        {SHOCK_FIELDS.map((f) => (
          <Field key={f.key} label={`${f.label} (${f.unit})`} htmlFor={`se-${f.key}`}>
            <input id={`se-${f.key}`} inputMode="decimal" className={inputCls} value={vals[f.key] ?? ""} placeholder={f.placeholder}
                   onChange={(e) => setVals((v) => ({ ...v, [f.key]: e.target.value }))} />
          </Field>))}
      </div>
      <label className="mt-2 inline-flex items-center gap-2 text-[12px] text-text-secondary">
        <input type="checkbox" checked={gv} onChange={(e) => setGv(e.target.checked)} /> Guarantee unenforceable
      </label>
      <div className="mt-3 grid gap-3 md:grid-cols-3">
        <Field label="Basis (what the scenario represents)" htmlFor="se-basis"><input id="se-basis" className={inputCls} value={basis} onChange={(e) => setBasis(e.target.value)} /></Field>
        <Field label="Reason for this version" htmlFor="se-reason"><input id="se-reason" className={inputCls} value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
        <div className="flex flex-col gap-1">
          <span className={labelCls}>Scope</span>
          <div className="flex gap-1.5">
            {proposalId ? <button type="button" onClick={() => setScope("deal")} className={cn("h-8 rounded-md border px-3 text-[12px]", scope === "deal" ? "border-accent bg-accent-muted text-accent" : "border-border text-text-secondary")}>This deal</button> : null}
            <button type="button" onClick={() => setScope("bank")} className={cn("h-8 rounded-md border px-3 text-[12px]", scope === "bank" ? "border-accent bg-accent-muted text-accent" : "border-border text-text-secondary")}>The bank (maker-checker)</button>
          </div>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <PrimaryButton onClick={save} disabled={busy || !label.trim()} data-testid="stress2-editor-save">{scope === "bank" ? "Send for approval" : "Save to this deal"}</PrimaryButton>
        {msg ? <div className={cn("text-[12px]", msg.ok ? "text-positive" : "text-negative")} data-testid="stress2-editor-msg">{msg.lines.map((l) => <p key={l}>{l}</p>)}</div> : null}
      </div>
      {pending.length ? (
        <div className="mt-4" data-testid="stress2-pending">
          <h4 className="mb-1 text-[12px] font-medium text-text-secondary">Waiting for a checker</h4>
          <ul className="space-y-1 text-[12px]">
            {pending.map((s) => (
              <li key={`${s.scenario_id}-${s.version}`} className="flex flex-wrap items-center gap-2">
                <span className="min-w-0 flex-1 truncate text-text-primary" title={s.basis}>{s.label} · v{s.version} · by {s.maker}</span>
                <Chip>{s.set_id}</Chip>
                {canApprove ? (<>
                  <SecondaryButton onClick={() => decide(s, true)}><Check size={12} /> Approve</SecondaryButton>
                  <SecondaryButton onClick={() => decide(s, false)}><X size={12} /> Return</SecondaryButton>
                </>) : null}
              </li>))}
          </ul>
        </div>) : null}
      <ImportSet onDone={loadPending} />
    </Section>
  );
}

function ImportSet({ onDone }: { onDone: () => void }) {
  const [content, setContent] = React.useState("");
  const [setName, setSetName] = React.useState("");
  const [auth, setAuth] = React.useState<string>("ICAAP");
  const [msg, setMsg] = React.useState<{ ok: boolean; lines: string[] } | null>(null);
  const tpl = async (fmt: "csv" | "json") => {
    const t = await stress2Api.template(fmt);
    const blob = new Blob([t.content], { type: fmt === "csv" ? "text/csv" : "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `stress-scenario-set-template.${fmt}`;
    a.click();
    URL.revokeObjectURL(a.href);
  };
  const file = (f: File | undefined) => { if (f) f.text().then(setContent).catch(() => setContent("")); };
  const run = async () => {
    setMsg(null);
    try {
      const r = await stress2Api.importSet(content, setName, auth);
      setMsg({ ok: true, lines: [`${r.rows} scenarios loaded as ${r.set_id}; they wait for a checker.`] });
      setContent("");
      onDone();
    } catch (e) {
      setMsg({ ok: false, lines: errorsOf(e) });
    }
  };
  return (
    <div className="mt-5 border-t border-border pt-3" data-testid="stress2-import">
      <h4 className="text-[12px] font-medium text-text-secondary">Load an ICAAP or regulator set</h4>
      <div className="mt-2 grid gap-3 md:grid-cols-4">
        <Field label="Authority" htmlFor="si-auth">
          <select id="si-auth" className={inputCls} value={auth} onChange={(e) => setAuth(e.target.value)}>{AUTHORITIES.map((a) => <option key={a} value={a}>{a}</option>)}</select>
        </Field>
        <Field label="Set name" htmlFor="si-name"><input id="si-name" className={inputCls} value={setName} onChange={(e) => setSetName(e.target.value)} placeholder="ICAAP 2026" /></Field>
        <Field label="File (CSV or JSON)" htmlFor="si-file"><input id="si-file" type="file" accept=".csv,.json,text/csv,application/json" className="text-[12px]" onChange={(e) => file(e.target.files?.[0])} /></Field>
        <div className="flex items-end gap-1.5">
          <SecondaryButton onClick={() => tpl("csv")}><Download size={12} /> CSV template</SecondaryButton>
          <SecondaryButton onClick={() => tpl("json")}><Download size={12} /> JSON</SecondaryButton>
        </div>
      </div>
      <textarea aria-label="Scenario set" className={cn(inputCls, "mt-2 h-24 py-1.5 font-mono")} value={content} onChange={(e) => setContent(e.target.value)}
                placeholder="Paste the filled template here, or choose the file" />
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <SecondaryButton onClick={run} disabled={!content.trim() || !setName.trim()} data-testid="stress2-import-run"><Upload size={12} /> Load set</SecondaryButton>
        {msg ? <div className={cn("text-[12px]", msg.ok ? "text-positive" : "text-negative")}>{msg.lines.slice(0, 6).map((l) => <p key={l}>{l}</p>)}</div> : null}
      </div>
    </div>
  );
}
