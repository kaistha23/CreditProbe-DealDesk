"use client";

/**
 * PLAN_R13 §I session ID: the shared frame of the five portfolio panels — interpretation first (the engine's
 * deterministic 3–5 lines), a compact KPI strip, the panel's own table, then folded "What the data cannot tell us",
 * "Method" and "Sources" (each relation opens in Data Domains). House kit only; no raw JSON, no free notes.
 */

import { FromLink } from "@/components/v5/ui/back-link"; // R14 U (K1): Data Domains source, with the way back
import * as React from "react";
import { ExternalLink, Loader2 } from "lucide-react";

import { KpiRow } from "@/components/v5/core/kpi-row";
import { friendlyError } from "@/lib/v5/errors";
import { dealdeskOrigin } from "@/lib/v5/dealdesk";
import { type IntelEnvelope, type IntelKpi, kpiValue, lineageHref } from "@/lib/v5/intel-portfolio";

export async function getIntel<T>(path: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${dealdeskOrigin()}${path}`, { credentials: "include", cache: "no-store" });
  } catch {
    throw new Error("Portfolio intelligence is temporarily unavailable. Please try again in a moment.");
  }
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new Error(friendlyError("Portfolio intelligence", res.status, body));
  return body as T;
}

export function useIntel<T>(path: string | null): { data: T | null; error: string | null; loading: boolean } {
  const [state, setState] = React.useState<{ key: string | null; data: T | null; error: string | null }>({ key: null, data: null, error: null });
  React.useEffect(() => {
    if (!path) return;
    let live = true;
    getIntel<T>(path).then(
      (data) => { if (live) setState({ key: path, data, error: null }); },
      (e: unknown) => { if (live) setState({ key: path, data: null, error: e instanceof Error ? e.message : String(e) }); },
    );
    return () => { live = false; };
  }, [path]);
  const current = state.key === path;
  return { data: current ? state.data : null, error: current ? state.error : null, loading: !!path && !current };
}

export function Loading({ what }: { what: string }) {
  return <p className="flex items-center gap-2 py-3 text-[12px] text-text-secondary"><Loader2 className="h-4 w-4 animate-spin" />{what}</p>;
}

export function Interpretation({ lines, testId }: { lines: string[]; testId?: string }) {
  return (
    <div className="rounded-md border border-border bg-surface px-3 py-2" data-testid={testId}>
      <p className="text-[13px] font-medium leading-5 text-text-primary">{lines[0]}</p>
      {lines.slice(1).map((l) => <p key={l} className="mt-1 text-[12px] leading-5 text-text-secondary">{l}</p>)}
    </div>
  );
}

export function Strip({ kpis, pick, testId }: { kpis: IntelKpi[]; pick?: string[]; testId?: string }) {
  const chosen = (pick ? pick.map((k) => kpis.find((x) => x.key === k)).filter((x): x is IntelKpi => !!x) : kpis).slice(0, 4);
  return <KpiRow testId={testId} tiles={chosen.map((k) => ({ label: k.label, value: kpiValue(k), sub: k.text ?? undefined }))} />;
}

export function Footnotes<R>({ env, testId }: { env: IntelEnvelope<R>; testId?: string }) {
  return (
    <div className="space-y-1 text-[12px]" data-testid={testId}>
      <details>
        <summary className="cursor-pointer select-none text-text-secondary hover:text-text-primary">What the data cannot tell us</summary>
        <ul className="mt-1 list-disc space-y-1 pl-5 text-text-secondary">{env.data_limits.map((l) => <li key={l}>{l}</li>)}</ul>
      </details>
      <details>
        <summary className="cursor-pointer select-none text-text-secondary hover:text-text-primary">Method</summary>
        <ul className="mt-1 list-disc space-y-1 pl-5 text-text-secondary">{env.method.map((l) => <li key={l}>{l}</li>)}</ul>
      </details>
      <details>
        <summary className="cursor-pointer select-none text-text-secondary hover:text-text-primary">Sources ({env.lineage.length})</summary>
        <ul className="mt-1 space-y-1 pl-1">
          {env.lineage.map((l) => {
            const href = lineageHref(l);
            const name = `${l.domain} · ${l.relation}`;
            return (
              <li key={name} className="flex flex-wrap items-center gap-2 text-text-secondary">
                {href ? <FromLink href={href} from="panel" className="inline-flex items-center gap-1 text-accent hover:underline">{name}<ExternalLink size={11} aria-hidden /></FromLink>
                      : <span className="text-text-primary">{name}</span>}
                {l.period ? <span className="text-text-muted">{String(l.period)}</span> : null}
                {l.rows !== null && l.rows !== undefined ? <span className="tabular-nums text-text-muted">{l.rows.toLocaleString("en-US")} rows</span> : null}
                {l.note ? <span className="text-text-muted">{l.note}</span> : null}
              </li>);
          })}
        </ul>
        <p className="mt-1 text-text-muted">As of {env.as_of} · ECL run {env.ecl_run} · {env.version} · digest {env.digest}</p>
      </details>
    </div>
  );
}

export function PanelError({ error }: { error: string }) {
  return <p role="alert" className="text-[12px] text-negative">{error}</p>;
}
