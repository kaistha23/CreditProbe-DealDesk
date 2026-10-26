"use client";

/**
 * Custom shocks: an optional structured editor inside a thread (PLAN_R2 6.7).
 * It sends the same structured shocks the statement reader produces, so a
 * custom step and a typed one are the same thing to the engine.
 */

import * as React from "react";
import { X } from "lucide-react";

import { type DomainId, type Meta, useLoad, whatif } from "@/lib/v5/whatif";

const field = "w-24 rounded border border-border bg-surface px-2 py-1 text-[12px] tabular-nums";

export function CustomShocks({ domain, hasScenario, disabled, onSubmit, onClose }: {
  domain: DomainId; hasScenario: boolean; disabled: boolean;
  onSubmit: (body: Record<string, unknown>) => void; onClose: () => void;
}) {
  const meta = useLoad<Meta>(() => whatif.meta(domain), `meta-${domain}`);
  const [pd, setPd] = React.useState("");
  const [lgd, setLgd] = React.useState("");
  const [ccf, setCcf] = React.useState("");
  const [rating, setRating] = React.useState("");
  const [sector, setSector] = React.useState("");
  const [segment, setSegment] = React.useState("");
  const [exposure, setExposure] = React.useState("");
  const [mevs, setMevs] = React.useState<Record<string, string>>({});
  const [mode, setMode] = React.useState<"new" | "stack">(hasScenario ? "stack" : "new");
  const m = meta.data;
  const lab = m?.labels;

  const build = () => {
    const shocks: Record<string, unknown> = {};
    if (pd) shocks.pd = { mode: "relative", value: Number(pd) };
    if (lgd) shocks.lgd = { mode: "pp", value: Number(lgd) };
    if (ccf) shocks.ccf = { mode: "pp", value: Number(ccf) };
    if (rating) shocks.rating = Math.round(Number(rating));
    if (sector) shocks.sector = Number(sector);
    const mev = Object.fromEntries(Object.entries(mevs).filter(([, v]) => v !== "").map(([k, v]) => [k, Number(v)]));
    if (Object.keys(mev).length) shocks.mev = mev;
    const scope: Record<string, string[]> = {};
    if (segment) scope.segments = [segment];
    if (exposure.trim()) scope.exposures = [exposure.trim().toUpperCase()];
    return { shocks, scope, mode };
  };
  const body = build();
  const empty = !Object.keys(body.shocks).length;

  return (
    <div className="space-y-2 rounded-md border border-border bg-surface p-3" data-testid="whatif-custom">
      <div className="flex items-center justify-between">
        <p className="text-[12px] font-semibold text-text-primary">Custom shocks</p>
        <button type="button" onClick={onClose} aria-label="Close custom shocks"><X size={14} /></button>
      </div>
      {!m ? <p className="text-[12px] text-text-muted">Loading…</p> : (
        <div className="grid gap-3 md:grid-cols-2">
          <div className="space-y-1.5 text-[12px]">
            <label className="flex items-center justify-between gap-2">PD change (%)<input className={field} value={pd} onChange={(e) => setPd(e.target.value)} data-testid="whatif-custom-pd" inputMode="decimal" /></label>
            <label className="flex items-center justify-between gap-2">LGD change (pp)<input className={field} value={lgd} onChange={(e) => setLgd(e.target.value)} data-testid="whatif-custom-lgd" inputMode="decimal" /></label>
            <label className="flex items-center justify-between gap-2">CCF change (pp)<input className={field} value={ccf} onChange={(e) => setCcf(e.target.value)} inputMode="decimal" /></label>
            <label className="flex items-center justify-between gap-2">{lab?.grade} move ({lab?.grade_notch}es, + worse)<input className={field} value={rating} onChange={(e) => setRating(e.target.value)} data-testid="whatif-custom-rating" inputMode="numeric" /></label>
            <label className="flex items-center justify-between gap-2">{lab?.segment} stress (sd)<input className={field} value={sector} onChange={(e) => setSector(e.target.value)} inputMode="decimal" /></label>
            <label className="flex items-center justify-between gap-2">Only {lab?.segment.toLowerCase()}
              <select className="w-44 rounded border border-border bg-surface px-1 py-1 text-[12px]" value={segment} onChange={(e) => setSegment(e.target.value)} data-testid="whatif-custom-segment">
                <option value="">Whole book in scope</option>{m.segments.map((s) => <option key={s} value={s}>{s}</option>)}</select></label>
            <label className="flex items-center justify-between gap-2">Only {lab?.exposure.toLowerCase()} (ID)<input className="w-44 rounded border border-border bg-surface px-2 py-1 text-[12px] font-mono" value={exposure} onChange={(e) => setExposure(e.target.value)} placeholder="optional" /></label>
          </div>
          <div className="space-y-1.5 text-[12px]">
            <p className="text-[11px] text-text-muted">Macroeconomic variables (move against the base path, every year)</p>
            {m.mev.map((s) => (
              <label key={s.key} className="flex items-center justify-between gap-2">{s.name} ({s.shock_unit === "pct" ? "%" : s.shock_unit})
                <input className={field} value={mevs[s.key] ?? ""} onChange={(e) => setMevs((x) => ({ ...x, [s.key]: e.target.value }))}
                       data-testid={`whatif-custom-mev-${s.key}`} inputMode="decimal" /></label>))}
          </div>
        </div>)}
      <div className="flex items-center justify-between gap-2">
        {hasScenario ? (
          <div className="inline-flex rounded border border-border p-0.5 text-[11px]">
            {(["stack", "new"] as const).map((v) => (
              <button key={v} type="button" aria-pressed={mode === v} onClick={() => setMode(v)}
                      className={mode === v ? "rounded bg-accent px-2 py-0.5 text-accent-contrast" : "px-2 py-0.5"}>
                {v === "stack" ? "Add to the current scenario" : "As a new scenario"}</button>))}
          </div>) : <span />}
        <button type="button" disabled={disabled || empty} onClick={() => onSubmit(body)} data-testid="whatif-custom-run"
                className="rounded-md bg-accent px-3 py-1 text-[12px] font-medium text-accent-contrast disabled:opacity-40">Run these shocks</button>
      </div>
    </div>
  );
}
