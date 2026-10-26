"use client";

/**
 * R14 Session F (K20, K23): Stress, a header button from Structure on, over the structures the user chooses.
 *
 *   1. choose the structures (multi: the ask, the recommended, alternatives, your own; default the selected one and the ask)
 *   2. one run: the matrix structures × mild / moderate / severe on the deal's relevant drivers in the current regime,
 *      pass/fail, RAROC, DSCR, covenant headroom, stage and limits; a structure that fails before stress is marked
 *      "fails before stress" and stressed only on request
 *   3. stress-proofing: target severity (default moderate), the smallest change set, added as "Stress-proofed (target)",
 *      re-run automatically; the interpreter says per structure what breaks first, why, and what the proofed one changes and costs
 * The R12 Stress Lab (ladder, chain, editor, verdict) stays one click away below, on the selected structure (N1).
 */

import * as React from "react";
import { Activity, ShieldCheck } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { PlainWords } from "@/components/v5/ui/plain-words";
import { cn } from "@/lib/utils";
import {
  type MatrixCell, type MatrixStructure, type Severity, type StressMatrix, type StressProof, type StructureSet, SEVERITIES,
  defaultStressKeys, flowApi, interpretationLines, pct, survivalLabel, survivalTone, x,
} from "@/lib/v5/dealdesk-flow";
import { friendlyMessage } from "@/lib/v5/errors";

import { Chip, PrimaryButton, SecondaryButton, Section, tableCls, tdCls, thCls } from "./kit";

function CellView({ c }: { c: MatrixCell }) {
  if (!c.scenarios) return <span className="text-[12px] text-text-muted">No applicable scenario</span>;
  return (
    <div className="space-y-0.5 text-[12px]" data-testid={`flow-cell-${c.severity}`} data-passes={c.passes ? "true" : "false"}>
      <Chip tone={c.passes ? "positive" : "negative"}>{c.passes ? "Pass" : "Fail"}</Chip>
      {c.first_break ? <p className="line-clamp-2 text-[11px] text-negative" title={c.first_break.label}>{c.first_break.label}: {c.first_break.test_labels.join(", ")}</p> : null}
      <p className="text-text-secondary">RAROC {pct(c.worst_raroc)} · DSCR {x(c.min_dscr)}</p>
      <p className="text-text-secondary">Cov. headroom {c.min_covenant_headroom == null ? "–" : pct(c.min_covenant_headroom, 0)} · Stage {c.worst_stage ?? "–"}</p>
      {c.limits.length ? <p className="line-clamp-1 text-[11px] text-warning" title={c.limits.join(" · ")}>Limits: {c.limits.length} broken</p> : null}
    </div>
  );
}

export function StressMatrixTable({ m, onForce, busy }: { m: StressMatrix; onForce?: (key: string) => void; busy?: boolean }) {
  return (
    <div className="overflow-x-auto">
      {m.how_to_read?.length ? (
        <ul className="mb-2 space-y-0.5 rounded-md border border-border bg-surface-sunken px-3 py-2 text-[12px] text-text-secondary" data-testid="flow-stress-how-to-read">
          {m.how_to_read.map((l) => <li key={l}>{l}</li>)}</ul>) : null}
      <table className={cn(tableCls, "table-fixed min-w-[880px]")} data-testid="flow-stress-matrix">
        <colgroup><col className="w-[22%]" /><col className="w-[12%]" /><col className="w-[22%]" /><col className="w-[22%]" /><col className="w-[22%]" /></colgroup>
        <thead><tr>{["Structure", "Base", "Mild", "Moderate", "Severe"].map((h) => <th key={h} className={thCls}>{h}</th>)}</tr></thead>
        <tbody>{m.structures.map((s) => (
          <tr key={s.key} data-testid={`flow-matrix-row-${s.key}`} data-status={s.status}>
            <td className={cn(tdCls, "whitespace-normal align-top")}>
              <p className="font-medium text-text-primary">{s.label}</p>
              <Chip tone={survivalTone(s)} testId={`flow-matrix-survival-${s.key}`}>{survivalLabel(s)}</Chip>
              {s.tier ? <p className="mt-0.5 text-[11px] text-text-muted">Tier {s.tier}{s.verdict ? ` · ${s.verdict}` : ""}</p> : null}</td>
            <td className={cn(tdCls, "whitespace-normal align-top text-[12px]")}>
              <p className={cn("font-semibold", s.raroc >= s.hurdle - 1e-9 ? "text-positive" : "text-negative")}>{pct(s.raroc, 2)}</p>
              <p className="text-text-muted">DSCR {x(s.dscr)}</p>
              <p className="text-text-muted">Cov. headroom {s.covenant_headroom == null ? "–" : pct(s.covenant_headroom, 0)}</p></td>
            {s.status === "fails_before_stress" ? (
              <td colSpan={3} className={cn(tdCls, "whitespace-normal align-top")}>
                <p className="text-[12px] text-text-secondary"><b className="text-negative">Fails before stress</b>: {s.base_reason}. Not stressed.</p>
                {onForce ? <SecondaryButton className="mt-1" disabled={busy} onClick={() => onForce(s.key)} data-testid={`flow-matrix-force-${s.key}`}>Stress it anyway</SecondaryButton> : null}
              </td>) : SEVERITIES.map((sev) => {
                const c = s.cells.find((z) => z.severity === sev);
                return <td key={sev} className={cn(tdCls, "whitespace-normal align-top")}>{c ? <CellView c={c} /> : "–"}</td>;
              })}
          </tr>))}</tbody>
      </table>
    </div>
  );
}

function Interpreter({ s }: { s: MatrixStructure }) {
  return (
    <div className="rounded-md border border-border bg-surface px-3 py-2" data-testid={`flow-interpreter-${s.key}`}>
      <p className="text-[12px] font-semibold text-text-primary">{s.label}</p>
      <ul className="mt-0.5 space-y-0.5 text-[12px] text-text-secondary">{interpretationLines(s.interpretation).map((l) => <li key={l}>{l}</li>)}</ul>
    </div>
  );
}

export function StressOverStructures({ proposalId, set, onSetChange, below }: {
  proposalId: string; set: StructureSet | null; onSetChange: (s: StructureSet) => void; below?: React.ReactNode;
}) {
  const [keys, setKeys] = React.useState<string[] | null>(null);
  const [force, setForce] = React.useState<string[]>([]);
  const [m, setM] = React.useState<StressMatrix | null>(null);
  const [busy, setBusy] = React.useState("");
  const [err, setErr] = React.useState("");
  const [target, setTarget] = React.useState<Severity>("moderate");
  const [from, setFrom] = React.useState("");
  const [proof, setProof] = React.useState<StressProof | null>(null);
  const chosen = keys ?? (set ? defaultStressKeys(set) : []);
  const fromKey = from || set?.selected || "ask";
  const run = React.useCallback(async (ks: string[], fs: string[]) => {
    setBusy("stress");
    setErr("");
    try { setM(await flowApi.matrix(proposalId, ks, fs)); } catch (e) { setErr(friendlyMessage(e, "Deal Desk")); } finally { setBusy(""); }
  }, [proposalId]);
  const toggle = (k: string) => setKeys((ks) => { const cur = ks ?? chosen; return cur.includes(k) ? cur.filter((z) => z !== k) : [...cur, k]; });
  const doProof = async () => {
    setBusy("proof");
    setErr("");
    try {
      const r = await flowApi.proof(proposalId, fromKey, target);
      setProof(r);
      setM(r.matrix);
      onSetChange(r.structure_set);
      setKeys(r.matrix.keys);
    } catch (e) { setErr(friendlyMessage(e, "Deal Desk")); } finally { setBusy(""); }
  };
  if (!set) return <Skeleton className="h-64 w-full" />;
  return (
    <div className="space-y-4" data-testid="flow-stress">
      <Section title="Stress the structures" testId="flow-stress-chooser"
               info="One run stresses every structure you tick, on the scenarios that apply to this deal, mild, moderate and severe, in today's macro regime. A structure that already fails before any stress is not stressed unless you ask.">
        <div className="space-y-3">
          <PlainWords lines={m ? m.plain_words : [
            "Pick the structures to put under stress: the client's ask, our recommendation and any you built.",
            `${chosen.length} structure${chosen.length === 1 ? "" : "s"} ticked; each goes through mild, moderate and severe shocks in one run.`,
            "A structure that already fails without stress is shown as such and not stressed unless you ask.",
          ]} speak testId="flow-stress-plain-words" />
          {m ? <p className="text-[12px] text-text-secondary" data-testid="flow-regime-line"><b className="text-text-primary">Current regime.</b> {m.regime_line}</p> : null}
          <div className="flex flex-wrap gap-2" data-testid="flow-stress-choices">
            {set.rows.map((r) => (
              <label key={r.key} className={cn("inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-md border px-2.5 text-[12px]",
                                               chosen.includes(r.key) ? "border-accent bg-accent-muted text-accent" : "border-border text-text-secondary")}>
                <input type="checkbox" className="accent-current" checked={chosen.includes(r.key)} onChange={() => toggle(r.key)}
                       data-testid={`flow-stress-pick-${r.key}`} />
                {r.label}{r.fails_before_stress ? <span className="text-[10.5px] text-text-muted"> (fails before stress)</span> : null}
              </label>))}
            <PrimaryButton onClick={() => void run(chosen, force)} disabled={!chosen.length || Boolean(busy)} data-testid="flow-stress-run">
              <Activity size={14} /> {busy === "stress" ? "Stressing…" : `Stress ${chosen.length} structure${chosen.length === 1 ? "" : "s"}`}</PrimaryButton>
          </div>
          {err ? <p role="alert" className="text-[12px] text-negative">{err}</p> : null}
          {busy === "stress" && !m ? <Skeleton className="h-40 w-full" /> : null}
          {m ? <>
            <StressMatrixTable m={m} busy={Boolean(busy)} onForce={(k) => { const f = [...force, k]; setForce(f); void run(m.keys, f); }} />
            <p className="text-[11px] text-text-muted" data-testid="flow-survival-rule">{m.survival_rule} Sensitivities {m.sensitivity_version ?? "current"}; {m.basis}</p>
            <div className="grid gap-2 xl:grid-cols-2" data-testid="flow-interpreters">{m.structures.map((s) => <Interpreter key={s.key} s={s} />)}</div>
          </> : null}
        </div>
      </Section>
      <Section title="Stress-proof a structure" testId="flow-stress-proof"
               info="The reverse solver finds the smallest change set that lets a structure survive the target severity: amount to capacity, covenant reset with headroom and step-downs, amount, cash margin, receivables assignment, a better-rated guarantee, pricing and a margin ratchet. Severe is monitored, not designed for, else the deal is over-structured.">
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2 text-[12px]">
            <span className="text-text-secondary">Start from</span>
            <select value={fromKey} onChange={(e) => setFrom(e.target.value)} data-testid="flow-proof-from"
                    className="h-8 rounded-md border border-border bg-background px-2 text-[12px]">
              {set.rows.map((r) => <option key={r.key} value={r.key}>{r.label}</option>)}</select>
            <span className="text-text-secondary">survive</span>
            <div className="inline-flex rounded-md border border-border p-0.5" role="radiogroup" aria-label="Target severity">
              {SEVERITIES.map((sv) => (
                <button key={sv} type="button" role="radio" aria-checked={target === sv} onClick={() => setTarget(sv)} data-testid={`flow-proof-target-${sv}`}
                        className={cn("h-7 rounded px-3 capitalize", target === sv ? "bg-accent font-medium text-accent-contrast" : "text-text-secondary hover:bg-surface-hover")}>{sv}</button>))}
            </div>
            <PrimaryButton onClick={() => void doProof()} disabled={Boolean(busy)} data-testid="flow-proof-run">
              <ShieldCheck size={14} /> {busy === "proof" ? "Finding the smallest change…" : "Stress-proof"}</PrimaryButton>
          </div>
          {busy === "proof" ? <Skeleton className="h-24 w-full" /> : null}
          {proof ? (
            <div className="space-y-2" data-testid="flow-proof-result" data-survives={proof.survives ? "true" : "false"}>
              <PlainWords lines={proof.plain_words} speak testId="flow-proof-plain-words" />
              <div className="flex flex-wrap items-center gap-2">
                <Chip tone={proof.survives ? "positive" : "negative"} testId="flow-proof-chip">{proof.label}: {proof.survives ? `survives ${proof.proof.target_severity}` : `does not survive ${proof.proof.target_severity}`}</Chip>
                {proof.added ? <span className="text-[12px] text-text-secondary">Added to Your structures; select it on the Structure step to recommend it.</span>
                  : <span className="text-[12px] text-text-secondary">Nothing was added: no change to the structure helps.</span>}
              </div>
              {proof.changes.length ? (
                <table className={tableCls} data-testid="flow-proof-changes">
                  <thead><tr>{["Change", "Asks of the client", "Cost"].map((h) => <th key={h} className={thCls}>{h}</th>)}</tr></thead>
                  <tbody>{proof.changes.map((c, i) => (
                    <tr key={`${c.lever}-${i}`}><td className={cn(tdCls, "whitespace-normal")}>{c.text}</td><td className={cn(tdCls, "whitespace-normal")}>{c.client || "–"}</td>
                      <td className={cn(tdCls, "whitespace-normal")}>{c.cost}</td></tr>))}</tbody>
                </table>) : null}
              <ul className="space-y-0.5 text-[12px] text-text-secondary">{proof.interpretation.lines.map((l) => <li key={l}>{l}</li>)}</ul>
            </div>) : null}
        </div>
      </Section>
      {below}
    </div>
  );
}
