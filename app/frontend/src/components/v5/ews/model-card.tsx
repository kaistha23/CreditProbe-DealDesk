"use client";

/**
 * The Early Warning rule set as a standard MODEL CARD, for a credit-committee
 * reader who is not a modeller.
 *
 * Top-down: (1) what the model is, (2) what it reads -- by source, then risk
 * layer, then rule, (3) how a score becomes a band, (4) how it is performing
 * now and over the last six periods against its targets, (5) what it cannot
 * do, (6) how it has changed. Plain English first; the SQL and the inputs sit
 * behind a "technical detail" control on each rule.
 *
 * Every number is served live by the Early Warning service
 * (GET /api/v1/ews/model-card); nothing is computed or fixed here.
 */

import * as React from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { AlertTriangle, CheckCircle2, CircleSlash, Loader2, XCircle } from "lucide-react";

import { shareBarFigure } from "@/components/answer/bar-figure";
import { Card } from "@/components/ui/card";
import { Plot } from "@/components/v5/ews/plot";
import { cn } from "@/lib/utils";
import { type DomainId, asOfLabel, count, ewsOrigin, pct, sar, shortPeriod } from "@/lib/v5/ews";

import { Band, Figure } from "./parts";
import { friendlyError, friendlyMessage } from "@/lib/v5/errors";
import { InfoPopover } from "@/components/ui/info-popover"; // R13 X: notes behind the (i)

const BAND_FILL: Record<string, string> = {
  critical: "var(--ipm-negative)", high: "var(--ipm-warning)", moderate: "var(--ipm-accent)", low: "var(--ipm-border-strong)",
  none: "var(--ipm-surface-sunken)",
};

// ---------------------------------------------------------------- payload

export interface McRule {
  id: string; name: string; condition: string; review: string; threshold: string; threshold_kind: string;
  weight: number; live: boolean; not_live_reason: string; limitation: string; proxy: boolean;
  customers: number | null; exposures: number | null; exposure_sar_mn: number | null;
  source: string; family: string; catalogued: boolean;
  technical: {
    expression: string; missing_columns: string[]; evaluated_on: string;
    inputs: { column: string; label: string; unit: string; meaning: string; present: boolean }[];
  };
}
export interface McLayer {
  key: string; label: string; means: string; risk_layer: string; risk_layer_label: string;
  rules: McRule[]; rules_total: number; rules_live: number;
}
export interface McSource {
  key: string; label: string; description: string; status: string; connected: boolean;
  catalogue_connected: boolean; absent_because: string; requires: string[];
  rules_total: number; rules_live: number; layers: McLayer[];
}
export interface McBandRow {
  band: string; floor: number; ceiling: number | null; score_range: string; warned: boolean; means: string;
  customers: number; customers_pct: number; exposures: number; exposure_sar_mn: number;
}
export interface McPerfRow {
  period: string; customers: number; warned: number; warned_pct: number; high_or_critical: number;
  high_or_critical_pct: number; already_bad: number; already_bad_warned: number;
  capture_pct: number | null; forward_risk: number;
}
export type McStabilityRow = McPerfRow & { targets_met: boolean };
export interface McTarget { key: string; label: string; value: number | null; met: boolean | null; statement: string }
export interface McVersion {
  version: string; status: string; effective: string; change: string; current: boolean;
  band_floors: { critical: number; high: number; moderate: number }; rules_total: number;
  rules: { id: string; label: string; weight: number; sql: string }[];
  changes: { added: string[]; removed: string[]; reweighted: string[]; redefined: string[] } | null;
}
export interface ModelCardPayload {
  domain_id: DomainId; period: string; periods: string[]; stability_periods: string[];
  summary: {
    name: string; model_id: string; kind: string; purpose: string; intended_users: string; not_for: string;
    how_it_works: string; release_id: string; source_release_id: string; ruleset_version: string;
    catalogue_version: string; as_of: string; prior_period: string; status: string;
    rules_total: number; rules_live: number; sources_connected: number;
    sources_total: number; warned: number; warned_pct: number;
    scope: {
      book: string; grain: string; owner_grain: string; owners_label: string; exposures_label: string;
      customers: number; exposures: number; exposure_sar_mn: number; frequency: string; period_label: string;
    };
  };
  sources: McSource[];
  bands: { floors: Record<string, number>; rows: McBandRow[]; customers: number; how: string };
  performance: McPerfRow & {
    targets: McTarget[]; targets_met: number; targets_total: number; stability: McStabilityRow[];
    definitions: Record<string, string>; backtest: { available: boolean; statement: string };
  };
  limitations: { key: string; title: string; text: string }[];
  version_log: McVersion[];
  score_parity: { exposures: number | null; differ: number | null; scored_with: string; checked: boolean };
}

async function fetchModelCard(domain: DomainId, period: string): Promise<ModelCardPayload> {
  const qs = new URLSearchParams({ domain });
  if (period) qs.set("period", period);
  let response: Response;
  try {
    response = await fetch(`${ewsOrigin()}/api/v1/ews/model-card?${qs.toString()}`, { cache: "no-store", credentials: "include" });
  } catch {
    throw new Error(`Early Warning is temporarily unavailable. Please try again in a moment.`);
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(friendlyError("Early Warning", response.status, body));
  }
  return body as ModelCardPayload;
}

// ---------------------------------------------------------------- small parts

function Section({ n, title, lead, testId, children, aside }: {
  n: number; title: string; lead?: React.ReactNode; testId: string; children: React.ReactNode; aside?: React.ReactNode;
}) {
  return (
    <section className="space-y-3" data-testid={testId} aria-labelledby={`${testId}-title`}>
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-b border-border pb-1.5">
        <span className="font-mono text-[11px] text-text-muted">{n}</span>
        <h2 id={`${testId}-title`} className="text-[15px] font-semibold text-text-primary">{title}</h2>
        {/* R13 X (N4): the section's explanation sits behind the (i), not as a paragraph on the screen. */}
        {lead ? <InfoPopover title={title}><p>{lead}</p></InfoPopover> : null}
        {aside ? <span className="ml-auto text-[11px] text-text-muted">{aside}</span> : null}
      </div>
      {children}
    </section>
  );
}

function Pill({ tone, children, testId }: {
  tone: "positive" | "negative" | "warning" | "muted" | "accent"; children: React.ReactNode; testId?: string;
}) {
  const tones = {
    positive: "border-positive/30 bg-positive-muted text-positive",
    negative: "border-negative/30 bg-negative-muted text-negative",
    warning: "border-warning/30 bg-warning-muted text-warning",
    accent: "border-accent/30 bg-accent-muted text-accent",
    muted: "border-border bg-surface-muted text-text-secondary",
  } as const;
  return (
    <span data-testid={testId}
          className={cn("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold"
                        + " uppercase tracking-[0.08em]", tones[tone])}>
      {children}
    </span>
  );
}

function Met({ met }: { met: boolean | null }) {
  if (met === null) return <Pill tone="muted"><CircleSlash className="size-3" aria-hidden />Not applicable</Pill>;
  return met
    ? <Pill tone="positive"><CheckCircle2 className="size-3" aria-hidden />Met</Pill>
    : <Pill tone="negative"><XCircle className="size-3" aria-hidden />Not met</Pill>;
}

const TH = "px-2 py-1.5 text-left text-[10px] font-semibold uppercase tracking-[0.06em] text-text-muted";
const TD = "px-2 py-2 align-top";

// ---------------------------------------------------------------- the card

export function EwsModelCard() {
  const router = useRouter();
  const pathname = usePathname();
  const query = useSearchParams();
  const domain: DomainId = query.get("domain") === "retail" ? "retail" : "corporate";
  const period = query.get("period") ?? "";
  const key = `${domain}|${period}`;

  const [state, setState] = React.useState<{ key: string | null; data: ModelCardPayload | null; error: string }>(
    { key: null, data: null, error: "" });
  const [attempt, setAttempt] = React.useState(0);

  React.useEffect(() => {
    let live = true;
    fetchModelCard(domain, period).then(
      (data) => { if (live) setState({ key, data, error: "" }); },
      (err: unknown) => { if (live) setState({ key, data: null, error: friendlyMessage(err) }); },
    );
    return () => { live = false; };
  }, [domain, period, key, attempt]);

  const current = state.key === key;
  const data = current ? state.data : null;
  const error = current ? state.error : "";

  const go = React.useCallback((next: { domain: DomainId; period?: string }) => {
    const qs = new URLSearchParams({ domain: next.domain });
    if (next.period) qs.set("period", next.period);
    router.push(`${pathname}?${qs.toString()}`, { scroll: false });
  }, [router, pathname]);

  const shownPeriod = data?.period ?? period;

  return (
    <div className="space-y-6" data-testid="ews-model-card" data-domain={domain} data-period={shownPeriod}
         data-state={data ? "ready" : error ? "error" : "loading"}>
      <header className="flex flex-wrap items-end gap-3">
        <div className="mr-auto">
          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-text-muted">Early Warning · Model card</p>
          <h1 className="text-2xl font-semibold text-text-primary">
            {data ? data.summary.name : `Early Warning rule set — ${domain === "corporate" ? "Corporate" : "Retail"}`}
          </h1>
        </div>
        <div className="inline-flex rounded-md border border-border p-0.5" role="tablist" aria-label="Book">
          {(["corporate", "retail"] as const).map((d) => (
            <button key={d} type="button" role="tab" aria-selected={domain === d}
                    onClick={() => { if (d !== domain) go({ domain: d }); }}
                    data-testid={`ews-mc-book-${d}`}
                    className={cn("rounded px-3 py-1 text-[13px] font-medium transition-colors",
                                  domain === d ? "bg-accent text-accent-contrast" : "text-text-secondary hover:bg-surface-muted")}>
              {d === "corporate" ? "Corporate" : "Retail"}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-2 text-[12px] text-text-secondary">
          <span className="text-[10px] font-semibold uppercase tracking-[0.08em] text-text-muted">As of</span>
          <select value={shownPeriod} disabled={!data}
                  onChange={(e) => go({ domain, period: e.target.value })}
                  data-testid="ews-mc-period-select"
                  className="rounded-md border border-border bg-surface px-2 py-1 text-[12px] text-text-primary">
            {(data?.periods ?? (shownPeriod ? [shownPeriod] : [])).slice().reverse().map((p) => (
              <option key={p} value={p}>{asOfLabel(p)}</option>
            ))}
          </select>
        </label>
      </header>
      <p className="-mt-4 text-[11px] text-text-muted">
        Period: <span className="font-mono text-text-secondary" data-testid="ews-mc-period">{shownPeriod || "latest"}</span>
      </p>

      {error ? (
        <div role="alert" data-testid="ews-mc-error"
             className="space-y-2 rounded-md border border-negative bg-negative-muted px-3 py-2 text-sm text-negative">
          <p>The model card for the {domain} book{period ? ` at ${period}` : ""} could not be read: {error}</p>
          <button type="button" onClick={() => setAttempt((n) => n + 1)} data-testid="ews-mc-retry"
                  className="rounded-md border border-negative px-2.5 py-1 text-xs">Try again</button>
        </div>
      ) : null}
      {!data && !error ? (
        <p className="flex items-center gap-2 text-sm text-text-muted" data-testid="ews-mc-loading">
          <Loader2 className="size-4 animate-spin" aria-hidden />
          Reading the {domain} rule set{period ? ` for ${period}` : ""}…
        </p>
      ) : null}
      {data ? <Body data={data} /> : null}
    </div>
  );
}

function Body({ data }: { data: ModelCardPayload }) {
  const s = data.summary;
  const owners = s.scope.owners_label;
  return (
    <>
      <Summary data={data} />
      <Section n={2} title="Inputs by source" testId="ews-mc-sources"
               aside={`${s.rules_live} of ${s.rules_total} rules live · ${s.sources_connected} of ${s.sources_total} sources connected`}
               lead={<>Where each signal comes from, grouped by the kind of risk it speaks to. A rule is <b>live</b> when
                 every field it needs is in this release; “fires on now” counts the {owners} for whom the rule is true
                 at {asOfLabel(data.period)}.</>}>
        <div className="space-y-4">
          {data.sources.map((src) => <SourceBlock key={src.key} src={src} owners={owners} exposures={s.scope.exposures_label} />)}
        </div>
      </Section>
      <Bands data={data} />
      <Performance data={data} />
      <Section n={5} title="Limitations" testId="ews-mc-limitations"
               lead="What this model cannot do, and what a reader should not conclude from it.">
        <Card className="p-0">
          <ul className="divide-y divide-border">
            {data.limitations.map((l) => (
              <li key={l.key} className="flex gap-3 px-4 py-3" data-testid="ews-mc-limitation" data-key={l.key}>
                <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden />
                <div>
                  <p className="text-[13px] font-medium text-text-primary">{l.title}</p>
                  <p className="mt-0.5 text-[12px] leading-relaxed text-text-secondary">{l.text}</p>
                </div>
              </li>
            ))}
          </ul>
        </Card>
      </Section>
      <Versions data={data} />
    </>
  );
}

// ---------------------------------------------------------------- 1 summary

function Summary({ data }: { data: ModelCardPayload }) {
  const s = data.summary;
  const sc = s.scope;
  return (
    <Section n={1} title="Model summary" testId="ews-mc-summary">
      <Card className="space-y-4 p-5">
        <div className="flex flex-wrap items-center gap-2">
          <Pill tone="positive" testId="ews-mc-status">{s.status}</Pill>
          <Pill tone="muted">{s.kind}</Pill>
          <span className="ml-auto font-mono text-[11px] text-text-muted" data-testid="ews-mc-ruleset">{s.ruleset_version}</span>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-text-muted">Purpose</p>
            <p className="mt-1 text-[13px] leading-relaxed text-text-primary" data-testid="ews-mc-purpose">{s.purpose}</p>
          </div>
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-text-muted">How it works</p>
            <p className="mt-1 text-[13px] leading-relaxed text-text-primary" data-testid="ews-mc-how">{s.how_it_works}</p>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-x-6 gap-y-3 border-t border-border pt-4 sm:grid-cols-4" data-testid="ews-mc-scope">
          <Figure label="Book" value={`${sc.book} · ${sc.frequency}`} />
          <Figure label={`${sc.owners_label} in scope`} value={count(sc.customers)} />
          <Figure label={sc.exposures_label} value={count(sc.exposures)} />
          <Figure label="Exposure (EAD)" value={sar(sc.exposure_sar_mn)} />
          <Figure label="As of" value={asOfLabel(s.as_of)} />
          <Figure label="Warned now" value={`${count(s.warned)} (${pct(s.warned_pct)})`} tone="warning" />
          <Figure label="Rules live" value={`${s.rules_live} of ${s.rules_total}`} />
          <Figure label="Sources connected" value={`${s.sources_connected} of ${s.sources_total}`} />
        </div>
        <div className="grid gap-4 border-t border-border pt-4 md:grid-cols-2">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-text-muted">Intended users</p>
            <p className="mt-1 text-[12px] text-text-secondary">{s.intended_users}</p>
          </div>
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-text-muted">Not to be used for</p>
            <p className="mt-1 text-[12px] text-text-secondary">{s.not_for}</p>
          </div>
        </div>
        <p className="border-t border-border pt-3 text-[11px] text-text-muted" data-testid="ews-mc-identity">
          Release <span className="font-mono">{s.release_id}</span> (from{" "}
          <span className="font-mono">{s.source_release_id}</span>) · rule set{" "}
          <span className="font-mono">{s.ruleset_version}</span> · catalogue{" "}
          <span className="font-mono">{s.catalogue_version}</span> · no model call.
        </p>
      </Card>
    </Section>
  );
}

// ---------------------------------------------------------------- 2 sources

function SourceBlock({ src, owners, exposures }: { src: McSource; owners: string; exposures: string }) {
  return (
    <Card className="p-0" data-testid={`ews-mc-source-${src.key}`} data-status={src.connected ? "connected" : "declared"}>
      <div className="flex flex-wrap items-center gap-2 border-b border-border px-4 py-3">
        <h3 className="text-[14px] font-semibold text-text-primary">{src.label}</h3>
        {src.connected
          ? <Pill tone="positive">Connected</Pill>
          : <Pill tone="muted">Declared, no live rule</Pill>}
        <span className="ml-auto text-[11px] text-text-muted">{src.rules_live} of {src.rules_total} rules live</span>
        <p className="w-full text-[12px] text-text-secondary">{src.description}</p>
      </div>
      {src.layers.length === 0 ? (
        <div className="space-y-1.5 px-4 py-3 text-[12px] text-text-secondary">
          <p>{src.absent_because}</p>
          {src.requires.length ? (
            <>
              <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-text-muted">What would have to arrive</p>
              <ul className="list-disc space-y-0.5 pl-5">{src.requires.map((r) => <li key={r}>{r}</li>)}</ul>
            </>
          ) : null}
        </div>
      ) : (
        <div className="divide-y divide-border">
          {src.layers.map((layer) => <LayerBlock key={layer.key} layer={layer} owners={owners} exposures={exposures} />)}
        </div>
      )}
    </Card>
  );
}

function LayerBlock({ layer, owners, exposures }: { layer: McLayer; owners: string; exposures: string }) {
  return (
    <div className="px-4 py-3" data-testid={`ews-mc-layer-${layer.key}`}>
      <div className="flex flex-wrap items-baseline gap-x-2">
        <h4 className="text-[13px] font-semibold text-text-primary">{layer.label}</h4>
        {layer.risk_layer_label ? <span className="text-[11px] text-text-muted">· {layer.risk_layer_label} risk</span> : null}
        <span className="text-[12px] text-text-secondary">— {layer.means}</span>
      </div>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full min-w-[760px] table-fixed text-[12px]">
          <thead>
            <tr className="border-b border-border">
              <th className={cn(TH, "w-[25%]")}>Rule</th>
              <th className={cn(TH, "w-[29%]")}>What it checks</th>
              <th className={cn(TH, "w-[17%]")}>Threshold</th>
              <th className={cn(TH, "w-[7%] text-right")}>Weight</th>
              <th className={cn(TH, "w-[10%]")}>Live</th>
              <th className={cn(TH, "w-[12%] text-right")}>Fires on now</th>
            </tr>
          </thead>
          <tbody>
            {layer.rules.map((r) => <RuleRow key={r.id} rule={r} owners={owners} exposures={exposures} />)}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function RuleRow({ rule, owners, exposures }: { rule: McRule; owners: string; exposures: string }) {
  return (
    <tr className="border-b border-border/60 last:border-b-0" data-testid={`ews-mc-rule-${rule.id}`}
        data-live={rule.live ? "true" : "false"} data-fires={rule.customers ?? ""}>
      <td className={TD}>
        <p className="font-medium text-text-primary">{rule.name}</p>
        <p className="mt-0.5 flex flex-wrap items-center gap-1.5">
          <span className="rounded border border-border px-1 font-mono text-[10px] text-text-muted">{rule.id}</span>
          {rule.proxy ? <Pill tone="warning">Proxy</Pill> : null}
          {!rule.catalogued ? <Pill tone="muted">Not catalogued</Pill> : null}
        </p>
        <details className="group mt-1.5" data-testid={`ews-mc-technical-${rule.id}`}>
          <summary className="cursor-pointer select-none text-[11px] text-accent hover:underline">Technical detail</summary>
          <div className="mt-1.5 space-y-1.5 rounded-md border border-border bg-surface-sunken p-2 text-[11px] text-text-secondary">
            <p className="text-[9px] font-semibold uppercase tracking-[0.08em] text-text-muted">Expression</p>
            <code className="block whitespace-pre-wrap break-words font-mono text-[11px] text-text-primary">
              {rule.technical.expression}
            </code>
            <p className="text-[9px] font-semibold uppercase tracking-[0.08em] text-text-muted">Inputs</p>
            <ul className="space-y-0.5">
              {rule.technical.inputs.map((i) => (
                <li key={i.column}>
                  <span className="font-mono">{i.column}</span> · {i.label}
                  {i.present ? "" : <span className="text-negative"> · not in this release</span>}
                  {i.meaning ? <span className="text-text-muted"> — {i.meaning}</span> : null}
                </li>
              ))}
            </ul>
            <p className="text-text-muted">Evaluated on {rule.technical.evaluated_on}.</p>
          </div>
        </details>
      </td>
      <td className={cn(TD, "text-text-secondary")}>
        {rule.condition}
        {rule.review ? <p className="mt-1 text-[11px] text-text-muted">Review: {rule.review}</p> : null}
      </td>
      <td className={cn(TD, "text-text-primary")}>{rule.threshold}</td>
      <td className={cn(TD, "text-right font-semibold tabular-nums")}>{rule.weight}</td>
      <td className={TD}>
        {rule.live ? <Pill tone="positive">Live</Pill> : <Pill tone="negative">Not live</Pill>}
        {!rule.live && rule.not_live_reason ? (
          <p className="mt-1 text-[10px] leading-snug text-text-muted">{rule.not_live_reason}</p>
        ) : null}
      </td>
      <td className={cn(TD, "text-right tabular-nums")}>
        {rule.customers === null ? <span className="text-text-muted">—</span> : (
          <>
            <p className="font-semibold text-text-primary">
              {count(rule.customers)}{" "}
              <span className="font-normal text-text-muted">{rule.customers === 1 ? owners.replace(/s$/, "") : owners}</span>
            </p>
            <p className="text-[10px] text-text-muted">{count(rule.exposures)} {exposures}</p>
            <p className="text-[10px] text-text-muted">{sar(rule.exposure_sar_mn)}</p>
          </>
        )}
      </td>
    </tr>
  );
}

// ---------------------------------------------------------------- 3 bands

function Bands({ data }: { data: ModelCardPayload }) {
  const owners = data.summary.scope.owners_label;
  const total = data.bands.customers || 1;
  const fig = shareBarFigure({ height: 22, segments: data.bands.rows.filter((r) => r.customers > 0).map((r) => ({
    label: r.band, value: r.customers, color: BAND_FILL[r.band] ?? "var(--ipm-surface-sunken)",
    text: `${count(r.customers)} ${owners} (${pct(r.customers_pct)})`,
  })) });
  return (
    <Section n={3} title="Score bands" testId="ews-mc-bands" lead={data.bands.how}>
      <Card className="space-y-3 p-4">
        <Plot data={fig.data} layout={{ ...fig.layout, xaxis: { visible: false, fixedrange: true, range: [0, total] } }}
              height={fig.height} ariaLabel={`Distribution of ${owners} by band`} filename="ews-score-bands" testId="ews-mc-bands-chart" />
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-[12px]">
            <thead>
              <tr className="border-b border-border">
                <th className={TH}>Band</th>
                <th className={TH}>Score</th>
                <th className={TH}>What it means</th>
                <th className={cn(TH, "text-right")}>{owners}</th>
                <th className={cn(TH, "text-right")}>Share</th>
                <th className={cn(TH, "text-right")}>{data.summary.scope.exposures_label}</th>
                <th className={cn(TH, "text-right")}>Exposure</th>
              </tr>
            </thead>
            <tbody>
              {data.bands.rows.map((r) => (
                <tr key={r.band} className="border-b border-border/60 last:border-b-0"
                    data-testid={`ews-mc-band-${r.band}`} data-customers={r.customers}>
                  <td className={TD}><Band band={r.band} />{r.warned ? <span className="ml-1.5 text-[10px] text-text-muted">warned</span> : null}</td>
                  <td className={cn(TD, "tabular-nums")}>{r.score_range}</td>
                  <td className={cn(TD, "text-text-secondary")}>{r.means}</td>
                  <td className={cn(TD, "text-right font-semibold tabular-nums")}>{count(r.customers)}</td>
                  <td className={cn(TD, "text-right tabular-nums")}>{pct(r.customers_pct)}</td>
                  <td className={cn(TD, "text-right tabular-nums")}>{count(r.exposures)}</td>
                  <td className={cn(TD, "text-right tabular-nums")}>{sar(r.exposure_sar_mn)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </Section>
  );
}

// ---------------------------------------------------------------- 4 performance

function Performance({ data }: { data: ModelCardPayload }) {
  const p = data.performance;
  const owners = data.summary.scope.owners_label;
  const tiles = [
    { key: "warned", label: "Warned rate", value: pct(p.warned_pct), sub: `${count(p.warned)} of ${count(p.customers)} ${owners}`,
      means: p.definitions.warned_rate },
    { key: "high_or_critical", label: "High or critical", value: pct(p.high_or_critical_pct),
      sub: `${count(p.high_or_critical)} ${owners}`, means: p.definitions.high_or_critical_rate },
    { key: "capture", label: "Already-bad captured", value: pct(p.capture_pct),
      sub: `${count(p.already_bad_warned)} of ${count(p.already_bad)} already bad`, means: p.definitions.already_bad_capture },
    { key: "forward_risk", label: "Forward risk", value: count(p.forward_risk), sub: `warned, still performing`,
      means: p.definitions.forward_risk },
  ];
  return (
    <Section n={4} title="Calibration and performance" testId="ews-mc-performance"
             aside={`${p.targets_met} of ${p.targets_total} targets met`}
             lead={<>How the rules sort the book at {asOfLabel(data.period)}, against the targets the rule set was calibrated
               to, and whether that held over the last {p.stability.length} {data.summary.scope.period_label}s.</>}>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {tiles.map((t) => (
          <Card key={t.key} className="p-3.5" data-testid={`ews-mc-kpi-${t.key}`}>
            <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-text-muted">{t.label}</p>
            <p className="mt-1 text-[22px] font-semibold leading-tight tabular-nums">{t.value}</p>
            <p className="mt-0.5 text-[11px] text-text-muted">{t.sub}</p>
            <p className="mt-1.5 text-[10px] leading-snug text-text-muted">{t.means}</p>
          </Card>
        ))}
      </div>
      <Card className="p-0" data-testid="ews-mc-targets">
        <p className="border-b border-border px-4 py-2.5 text-[13px] font-semibold text-text-primary">Targets</p>
        <ul className="divide-y divide-border">
          {p.targets.map((t) => (
            <li key={t.key} className="flex flex-wrap items-center gap-3 px-4 py-2.5"
                data-testid={`ews-mc-target-${t.key}`} data-met={t.met === null ? "na" : String(t.met)}>
              <span className="min-w-[220px] text-[13px] text-text-primary">{t.label}</span>
              <Met met={t.met} />
              <span className="text-[12px] text-text-secondary">{t.statement}</span>
            </li>
          ))}
        </ul>
      </Card>
      <Card className="p-4" data-testid="ews-mc-stability">
        <p className="text-[13px] font-semibold text-text-primary">Stability over the last {p.stability.length} {data.summary.scope.period_label}s</p>
        <div className="mt-2 overflow-x-auto">
          <table className="w-full min-w-[640px] text-[12px]">
            <thead>
              <tr className="border-b border-border">
                <th className={TH}>Period</th>
                <th className={cn(TH, "text-right")}>{owners}</th>
                <th className={cn(TH, "text-right")}>Warned rate</th>
                <th className={cn(TH, "text-right")}>High or critical</th>
                <th className={cn(TH, "text-right")}>Already-bad captured</th>
                <th className={cn(TH, "text-right")}>Forward risk</th>
                <th className={TH}>All targets</th>
              </tr>
            </thead>
            <tbody>
              {p.stability.map((r) => (
                <tr key={r.period} className={cn("border-b border-border/60 last:border-b-0",
                                                 r.period === data.period && "bg-accent-muted/30")}
                    data-testid="ews-mc-stability-row" data-period={r.period}>
                  <td className={cn(TD, "font-medium")}>{shortPeriod(r.period)}</td>
                  <td className={cn(TD, "text-right tabular-nums")}>{count(r.customers)}</td>
                  <td className={cn(TD, "text-right tabular-nums")}>{pct(r.warned_pct)}</td>
                  <td className={cn(TD, "text-right tabular-nums")}>{pct(r.high_or_critical_pct)}</td>
                  <td className={cn(TD, "text-right tabular-nums")}>{pct(r.capture_pct)}</td>
                  <td className={cn(TD, "text-right tabular-nums")}>{count(r.forward_risk)}</td>
                  <td className={TD}><Met met={r.targets_met} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-3 rounded-md border border-border bg-surface-muted/40 p-2.5 text-[12px] text-text-secondary"
           data-testid="ews-mc-backtest">{p.backtest.statement}</p>
      </Card>
    </Section>
  );
}

// ---------------------------------------------------------------- 6 versions

function Versions({ data }: { data: ModelCardPayload }) {
  return (
    <Section n={6} title="Version log" testId="ews-mc-versions"
             lead="Every rule set this service has run, newest first, with what changed and the band floors it used.">
      <Card className="p-0">
        <ul className="divide-y divide-border">
          {data.version_log.map((v) => (
            <li key={v.version} className="space-y-1.5 px-4 py-3" data-testid="ews-mc-version" data-version={v.version}>
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-[13px] font-semibold text-text-primary">{v.version}</span>
                <Pill tone={v.status === "active" ? "positive" : "muted"}>{v.status}</Pill>
                <span className="text-[11px] text-text-muted">effective {v.effective}</span>
                <span className="ml-auto text-[11px] text-text-muted">
                  Floors: critical {v.band_floors.critical}+ · high {v.band_floors.high}+ · moderate {v.band_floors.moderate}+ · {v.rules_total} rules
                </span>
              </div>
              <p className="text-[12px] text-text-secondary">{v.change}</p>
              {v.changes ? (
                <p className="text-[11px] text-text-muted">
                  {[v.changes.added.length ? `Added ${v.changes.added.join(", ")}` : "",
                    v.changes.removed.length ? `Removed ${v.changes.removed.join(", ")}` : "",
                    v.changes.reweighted.length ? `Re-weighted ${v.changes.reweighted.join(", ")}` : "",
                    v.changes.redefined.length ? `Redefined ${v.changes.redefined.join(", ")}` : ""]
                    .filter(Boolean).join(" · ") || "No rule changes against the previous version."}
                </p>
              ) : null}
              <details data-testid={`ews-mc-version-rules-${v.version}`}>
                <summary className="cursor-pointer select-none text-[11px] text-accent hover:underline">Rules in this version</summary>
                <table className="mt-1.5 w-full text-[11px]">
                  <tbody>
                    {v.rules.map((r) => (
                      <tr key={r.id} className="border-t border-border/60">
                        <td className="py-1 pr-2 font-mono text-text-muted">{r.id}</td>
                        <td className="py-1 pr-2 text-text-primary">{r.label}</td>
                        <td className="py-1 pr-2 text-right tabular-nums">{r.weight}</td>
                        <td className="py-1 font-mono text-text-muted">{r.sql}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </details>
            </li>
          ))}
        </ul>
      </Card>
      {data.score_parity.checked ? (
        <p className="flex items-center gap-1 text-[11px] text-text-muted" data-testid="ews-mc-parity">
          Score check: {data.score_parity.differ === 0 ? "matches the live rules"
            : `${count(data.score_parity.differ)} of ${count(data.score_parity.exposures)} ${data.summary.scope.exposures_label} differ from the live rules`}
          <InfoPopover title="Score check">{data.score_parity.differ === 0
            ? `The release's stored score equals the live rules on all ${count(data.score_parity.exposures)} ${data.summary.scope.exposures_label} at this period`
            : "The release's stored score is compared with the live rules on every exposure at this period"} (scored with {data.score_parity.scored_with}).</InfoPopover>
        </p>
      ) : null}
    </Section>
  );
}
