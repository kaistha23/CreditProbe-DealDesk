"use client";

/**
 * The What-If model cards (Delta and XGBoost), in the Early Warning model
 * card's layout: summary, data, inputs, how it works / training, validation,
 * sensitivities, limitations, version log. Plain words first; the detail
 * behind expand controls.
 */

import Link from "next/link";
import { BackButton } from "@/components/v5/core/back-button";
import * as React from "react";

import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Plot } from "@/components/v5/ews/plot";
import { type DomainId, pct, useLoad, whatif } from "@/lib/v5/whatif";

import { Explained } from "./charts";
import { beeswarmExplain, calibrationExplain, cycleExplain, importanceExplain, sensitivitiesExplain } from "./explain";
import { InfoPopover } from "@/components/ui/info-popover"; // R13 X: notes behind the (i)

/* eslint-disable @typescript-eslint/no-explicit-any */
type AnyCard = Record<string, any>;

function Section({ n, title, children, testId }: { n: number; title: string; children: React.ReactNode; testId: string }) {
  return (
    <Card className="space-y-3 p-4" data-testid={testId}>
      <h2 className="text-[15px] font-semibold text-text-primary">{n}. {title}</h2>
      {children}
    </Card>
  );
}

const th = "px-2 py-1 text-left text-[11px] font-semibold text-text-muted";
const td = "px-2 py-1 text-[12px] tabular-nums text-text-secondary";
const f3 = (v: number) => (Number.isFinite(v) ? v.toFixed(3) : "—");
const f4 = (v: number) => (Number.isFinite(v) ? v.toFixed(4) : "—");

function Metrics({ rows }: { rows: { label: string; m: AnyCard }[] }) {
  return (
    <table className="w-full border-collapse">
      <thead><tr className="border-b border-border"><th className={th}>Split</th><th className={th}>Rows</th><th className={th}>RMSE</th>
        <th className={th}>MAE</th><th className={th}>R²</th><th className={th}>Mean actual</th><th className={th}>Mean predicted</th></tr></thead>
      <tbody>{rows.map(({ label, m }) => (
        <tr key={label} className="border-b border-border/50"><td className={td}>{label}</td><td className={td}>{m.rows?.toLocaleString("en-US")}</td>
          <td className={td}>{f4(m.rmse)}</td><td className={td}>{f4(m.mae)}</td><td className={td}>{f3(m.r2)}</td>
          <td className={td}>{f4(m.mean_actual)}</td><td className={td}>{f4(m.mean_predicted)}</td></tr>))}</tbody>
    </table>
  );
}

function Calibration({ cal, oot, testId, title }: { cal: AnyCard[]; oot: AnyCard[]; testId: string; title: string }) {
  const max = Math.max(...cal.map((c) => Math.max(c.actual, c.predicted)), ...oot.map((c) => Math.max(c.actual, c.predicted)));
  return <Explained title={`Calibration: ${title}`} explain={calibrationExplain(title, cal as never[], oot as never[])}><Plot testId={testId} height={260} filename={testId} ariaLabel={`Calibration: ${title}`}
               data={[{ type: "scatter", mode: "lines+markers", name: "Random 30% test", x: cal.map((c) => c.predicted), y: cal.map((c) => c.actual), line: { color: "var(--ipm-chart-1)" } },
                      { type: "scatter", mode: "lines+markers", name: "Out-of-time test", x: oot.map((c) => c.predicted), y: oot.map((c) => c.actual), line: { color: "var(--ipm-chart-2)" } },
                      { type: "scatter", mode: "lines", name: "Perfect", x: [0, max], y: [0, max], line: { color: "var(--ipm-border)", dash: "dot" } }]}
               layout={{ hovermode: "closest", xaxis: { title: { text: "Predicted (decile mean)" } }, yaxis: { title: { text: "Actual (decile mean)" } } }} /></Explained>;
}

function Importance({ rows, testId, title }: { rows: AnyCard[]; testId: string; title: string }) {
  const top = rows.slice(0, 12).reverse();
  const kind = title.startsWith("Mean |SHAP|") ? "shap" : "gain";
  return <Explained title={title} explain={importanceExplain(kind, title.split(": ").pop() ?? "", rows as never[])}><Plot testId={testId} height={300} filename={testId} ariaLabel={title}
               data={[{ type: "bar", orientation: "h", y: top.map((r) => r.feature), x: top.map((r) => r.share_pct ?? 0), marker: { color: "var(--ipm-chart-3)" },
                        hovertemplate: "%{y}: %{x:.1f}%<extra></extra>" }]}
               layout={{ hovermode: "closest", margin: { l: 140, r: 16, t: 12, b: 40 }, xaxis: { title: { text: "Share, %" } } }} /></Explained>;
}

function Beeswarm({ shap, testId }: { shap: AnyCard; testId: string }) {
  const feats: string[] = (shap.top ?? []).slice(0, 10).filter((f: string) => shap.beeswarm?.[f]);
  const data = feats.map((f, i) => {
    const pts = shap.beeswarm[f];
    return { type: "scatter", mode: "markers", name: f, showlegend: false,
             x: pts.shap, y: pts.shap.map((_: number, j: number) => feats.length - i + ((j * 37) % 100 - 50) / 260),
             marker: { size: 4, color: pts.value_norm, colorscale: [[0, "#2b6cb0"], [1, "#e53e3e"]], cmin: 0, cmax: 1, opacity: 0.7 },
             hovertemplate: `${f}: SHAP %{x:.4f}<extra></extra>` };
  });
  return <Explained title="SHAP summary" explain={beeswarmExplain(feats)}><Plot testId={testId} height={340} filename={testId} ariaLabel="SHAP summary: each dot a test row, colour the feature value (blue low, red high)"
               data={data} layout={{ hovermode: "closest", margin: { l: 140, r: 16, t: 12, b: 40 },
                                     yaxis: { tickvals: feats.map((_, i) => feats.length - i), ticktext: feats, zeroline: false },
                                     xaxis: { title: { text: "SHAP value (effect on the model output)" } } }} /></Explained>;
}

export function WhatIfModelCard({ book, method }: { book: DomainId; method: "delta" | "xgboost" }) {
  const card = useLoad<AnyCard>(() => whatif.card(book, method), `card-${book}-${method}`);
  const c = card.data;
  return (
    <div className="space-y-4" data-testid={`whatif-model-card-${method}`}>
      <div className="flex flex-wrap items-center gap-3">
        <BackButton fallback={{ href: `/what-if?domain=${book}`, label: "What-If" }} testId="whatif-card-back" />
        <h1 className="text-xl font-semibold text-text-primary">{c?.name ?? "Model card"}</h1>
        <div className="ml-auto flex gap-2 text-[12px]">
          <Link className="text-accent hover:underline" href={`/what-if/models/${book}/${method === "delta" ? "xgboost" : "delta"}`} data-testid="whatif-card-other">
            {method === "delta" ? "XGBoost" : "Delta method"} card</Link>
          <Link className="text-accent hover:underline" href={`/what-if/models/${book === "corporate" ? "retail" : "corporate"}/${method}`} data-testid="whatif-card-book">
            {book === "corporate" ? "Retail" : "Corporate"}</Link>
        </div>
      </div>
      {card.error ? <p className="text-sm text-negative" role="alert">{card.error}</p> : null}
      {!c ? <Skeleton className="h-96 w-full" /> : (
        <>
          <Section n={1} title="Model summary" testId="whatif-mc-summary">
            <p className="text-[13px] text-text-secondary">{c.summary.purpose}</p>
            <dl className="grid gap-x-6 gap-y-1 text-[12px] md:grid-cols-2">
              <div><dt className="text-text-muted">Kind</dt><dd>{c.summary.kind}</dd></div>
              <div><dt className="text-text-muted">Version · status</dt><dd>{c.version} · {c.status}</dd></div>
              <div><dt className="text-text-muted">Book · as of</dt><dd>{c.book} · {c.as_of}</dd></div>
              <div><dt className="text-text-muted">Scenario weights</dt><dd>base {pct(c.scenario_weights.base * 100, 0)} · upturn {pct(c.scenario_weights.upturn * 100, 0)} · downturn {pct(c.scenario_weights.downturn * 100, 0)}</dd></div>
              <div><dt className="text-text-muted">Intended users</dt><dd>{c.summary.intended_users}</dd></div>
              <div><dt className="text-text-muted">Not for</dt><dd>{c.summary.not_for}</dd></div>
            </dl>
          </Section>
          <Section n={2} title="Data" testId="whatif-mc-data">
            <p className="flex flex-wrap items-center gap-1 text-[12px] text-text-secondary">{c.periods.length} periods ({c.periods[0]} to {c.periods[c.periods.length - 1]}) · {c.rows.toLocaleString("en-US")} rows · horizon {c.horizon_years} years
              <InfoPopover title="Data">The What-If IFRS 9 domain: {c.grain}, built from {c.source_release}; final ECL equals the books&apos; ECL row by row. Horizon {c.horizon_years} years under base, upturn and downturn.</InfoPopover></p>
            <table className="w-full border-collapse" data-testid="whatif-mc-mev">
              <thead><tr className="border-b border-border"><th className={th}>Macroeconomic variable</th><th className={th}>Unit</th><th className={th}>Coverage</th>
                <th className={th}>Source</th><th className={th}>Elasticity (prior → estimated)</th></tr></thead>
              <tbody>{c.mev.map((m: AnyCard) => (
                <tr key={m.key} className="border-b border-border/50"><td className={td}>{m.name}</td><td className={td}>{m.unit}</td>
                  <td className={td}>{m.coverage}</td><td className={td}>{String(m.source).slice(0, 90)}{m.vintage ? ` (${String(m.vintage).slice(0, 40)})` : ""} · retrieved {m.retrieved}</td>
                  <td className={td}>{f3(m.elasticity_prior)} → {f3(m.elasticity)}</td></tr>))}</tbody>
            </table>
            <p className="text-[11px] text-text-muted">{c.mev_access_note}</p>
          </Section>
          <Section n={3} title="Inputs" testId="whatif-mc-inputs">
            <ul className="space-y-1 text-[12px]">{c.inputs.map((i: AnyCard) => <li key={i.group}><span className="font-semibold text-text-primary">{i.group}:</span> {i.fields}</li>)}</ul>
          </Section>
          {method === "delta" ? (
            <>
              <Section n={4} title="How it works" testId="whatif-mc-how">
                <ol className="list-decimal space-y-1 pl-5 text-[12px] text-text-secondary">{c.how_it_works.map((h: string, i: number) => <li key={i}>{h}</li>)}</ol>
                <details className="text-[12px]"><summary className="cursor-pointer text-text-muted">The credit-cycle (MEV) model</summary>
                  <p className="mt-1 text-text-secondary">{c.cycle_model.how} Fit R² {f3(c.cycle_model.r2)} over {c.cycle_model.periods.length} periods.</p>
                  <Explained title="Credit-cycle fit" explain={cycleExplain(c.cycle_model.book_z, c.cycle_model.fitted_z)}><Plot testId="whatif-mc-cycle" height={240} ariaLabel="Credit-cycle index from observed defaults, and its MEV fit" filename="whatif-cycle-fit"
                        data={[{ type: "scatter", mode: "lines+markers", name: "From observed defaults", x: Object.keys(c.cycle_model.book_z), y: Object.values(c.cycle_model.book_z), line: { color: "var(--ipm-chart-1)" } },
                               { type: "scatter", mode: "lines+markers", name: "Fitted on the MEVs", x: Object.keys(c.cycle_model.fitted_z), y: Object.values(c.cycle_model.fitted_z), line: { color: "var(--ipm-chart-2)" } }]}
                        layout={{ yaxis: { title: { text: "Cycle index Z (higher = better)" } } }} /></Explained>
                  <table className="mt-2 w-full border-collapse"><thead><tr className="border-b border-border"><th className={th}>Segment</th><th className={th}>Beta (used)</th><th className={th}>Beta (history only)</th></tr></thead>
                    <tbody>{c.cycle_model.segments.map((s: AnyCard) => <tr key={s.segment} className="border-b border-border/50"><td className={td}>{s.segment}</td><td className={td}>{f3(s.beta)}</td><td className={td}>{f3(s.beta_data_only)}</td></tr>)}</tbody></table>
                </details>
              </Section>
              <Section n={5} title="Validation" testId="whatif-mc-validation">
                <ValidationChecks v={c.validation} />
              </Section>
            </>
          ) : (
            <>
              <Section n={4} title="Training" testId="whatif-mc-training">
                <p className="text-[12px] text-text-secondary">{c.training.algorithm}; {c.training.rounds} rounds; seed {c.training.seed}; trained {c.training.trained}. {c.training.splits} {c.training.determinism}</p>
                <ul className="text-[12px]">{Object.entries(c.training.targets).map(([k, v]) => <li key={k}><span className="font-mono">{k}</span>: {String(v)} · <span className="font-mono text-text-muted">{c.training.files[k]?.sha256.slice(0, 16)}…</span></li>)}</ul>
              </Section>
              <Section n={5} title="Validation on the test sets" testId="whatif-mc-validation">
                {(["pd", "lgd", "ecl12", "ecllt"] as const).map((k) => {
                  const v = c.validation[k];
                  const rows = k === "pd" ? [{ label: "Random 30% test (probability)", m: v.random.test_probability }, { label: "Random 30% test (log-odds)", m: v.random.test_logit },
                                             { label: "Out-of-time test (probability)", m: v.out_of_time.test_probability }]
                    : [{ label: "Random 30% test", m: v.random.test }, { label: "Out-of-time test", m: v.out_of_time.test }];
                  return (
                    <div key={k} className="space-y-2" data-testid={`whatif-mc-target-${k}`}>
                      <h3 className="text-[13px] font-semibold text-text-primary">{c.training.targets[k]}</h3>
                      <Metrics rows={rows} />
                      <div className="grid gap-3 xl:grid-cols-3">
                        <Calibration cal={v.calibration} oot={v.calibration_out_of_time} testId={`whatif-mc-cal-${k}`} title={k} />
                        <Importance rows={c.importance[k]} testId={`whatif-mc-imp-${k}`} title={`Gain importance: ${k}`} />
                        <Importance rows={c.shap[k].features} testId={`whatif-mc-shapbar-${k}`} title={`Mean |SHAP|: ${k}`} />
                      </div>
                      {k === "pd" ? <Beeswarm shap={c.shap.pd} testId="whatif-mc-beeswarm" /> : null}
                    </div>);
                })}
                <ValidationChecks v={c.engine_validation} />
              </Section>
            </>
          )}
          <Section n={6} title="Sensitivities" testId="whatif-mc-sensitivities">
                        <Explained title="Sensitivities" explain={sensitivitiesExplain(c.sensitivities)}><Plot testId="whatif-mc-sens" height={300} filename="whatif-sensitivities" ariaLabel="ECL change for a one-sd adverse move in each MEV"
                  data={[{ type: "bar", orientation: "h", y: c.sensitivities.map((s: AnyCard) => s.name), x: c.sensitivities.map((s: AnyCard) => s.ecl_change_pct),
                           marker: { color: "var(--ipm-negative)" }, hovertemplate: "%{y}: %{x:.2f}%<extra></extra>" }]}
                  layout={{ hovermode: "closest", margin: { l: 210, r: 16, t: 12, b: 40 }, xaxis: { title: { text: "ECL change, %" } } }} /></Explained>
          </Section>
          <Section n={7} title="Limitations" testId="whatif-mc-limitations">
            <ul className="list-disc space-y-1 pl-5 text-[12px] text-text-secondary">{c.limitations.map((l: string, i: number) => <li key={i}>{l}</li>)}</ul>
          </Section>
          <Section n={8} title="Version log" testId="whatif-mc-versions">
            <ul className="space-y-1 text-[12px]">{c.versions.map((v: AnyCard) => <li key={v.version}><span className="font-mono">{v.version}</span> · {v.date} · {v.change}</li>)}</ul>
          </Section>
        </>)}
    </div>
  );
}

function ValidationChecks({ v }: { v: AnyCard }) {
  if (!v || !v.zero_shock) return null;
  const ok = (b: boolean) => <span className={b ? "text-positive" : "text-negative"}>{b ? "pass" : "fail"}</span>;
  return (
    <ul className="space-y-1 text-[12px] text-text-secondary" data-testid="whatif-mc-checks">
      <li>No shock: starting ECL {v.zero_shock.start.toFixed(1)} against {v.zero_shock.reported.toFixed(1)} reported (difference {v.zero_shock.start_minus_reported.toFixed(2)}); scenario = start {ok(Math.abs(v.zero_shock.scenario_minus_start) < 1e-6)}.</li>
      <li>ECL rises with the PD shock (+10%, +25%, +50%, +100%): {ok(v.pd_monotonic.pass)} ({v.pd_monotonic.steps.map((s: AnyCard) => `${s.ecl_change_pct.toFixed(1)}%`).join(", ")}).</li>
      <li>ECL rises with each further notch (1, 2, 3): {ok(v.rating_monotonic.pass)} ({v.rating_monotonic.steps.map((s: AnyCard) => `${s.ecl_change_pct.toFixed(1)}%`).join(", ")}).</li>
      <li>The waterfall adds up for a seven-driver scenario: difference {Number(v.shapley_additivity.difference).toExponential(1)} {ok(v.shapley_additivity.pass)}.</li>
      <li>Same inputs, same output (run twice): {ok(v.determinism.pass)}.</li>
    </ul>
  );
}
