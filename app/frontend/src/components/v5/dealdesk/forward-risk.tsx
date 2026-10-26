"use client";

/**
 * PLAN_R11 Session F (F4): forward risk under the Optimise structures. Answer first (one line), then at most four
 * tiles, then three charts (the 4-quarter stage path, the structure comparison with the ECL-optimal structure
 * marked, the drivers), the early warning rules fired on the post-deal obligor and the best lever, each with its (i),
 * and the transition models' card. Every figure comes from POST /proposals/{id}/forward-risk.
 */

import * as React from "react";
import { X } from "lucide-react";

import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { KpiRow } from "@/components/v5/core/kpi-row";
import { Plot } from "@/components/v5/ews/plot";
import { cn } from "@/lib/utils";
import { DealDeskError, dealdeskOrigin, money, rate } from "@/lib/v5/dealdesk";
import {
  type ForwardRiskResult, type ForwardStructure, type ForwardStructureInput, type TransitionCard,
  askedStructure, bandLabel, bandTone, checkResult, comparisonRows, driverBars, driverValue, headlineStructure, leverLine, prob,
  requestBody, stage2PlusPath, vsBook, wrapLabel,
} from "@/lib/v5/dealdesk-forward";
import { friendlyError } from "@/lib/v5/errors";

import { C } from "./charts";
import { Explainer } from "./explain";
import { ChartTitle, Chip, SecondaryButton, Section, tableCls, tdCls, thCls } from "./kit";

const ENGINE = "/api/v1/dealdesk";

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${dealdeskOrigin()}${ENGINE}${path}`, {
      ...init, credentials: "include", cache: "no-store", headers: { "Content-Type": "application/json" },
    });
  } catch {
    throw new DealDeskError(0, "Deal Desk is temporarily unavailable. Please try again in a moment.");
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new DealDeskError(response.status, friendlyError("Deal Desk", response.status, body));
  return body as T;
}

export const forwardApi = {
  run: (proposalId: string, structures: readonly ForwardStructureInput[], signal?: AbortSignal) =>
    call<ForwardRiskResult>(`/proposals/${encodeURIComponent(proposalId)}/forward-risk`,
                            { method: "POST", body: JSON.stringify(requestBody(structures)), signal }),
  card: () => call<TransitionCard>("/forward-risk/model-card"),
};

const layoutBase = { hovermode: "closest", margin: { l: 52, r: 12, t: 30, b: 36 },
  legend: { orientation: "h", x: 0, y: 1.02, yanchor: "bottom", font: { size: 10 } } };

// ------------------------------------------------------------------ charts

function PathChart({ rec, asked }: { rec: ForwardStructure; asked?: ForwardStructure }) {
  const q = rec.stage_path.map((p) => (p.quarter === 0 ? "Today" : `Q+${p.quarter}`));
  const series = (s: ForwardStructure, name: string, color: string, dash: string) => {
    const p = stage2PlusPath(s);
    return [
      { type: "scatter", mode: "lines+markers", name: `${name} S2`, x: q, y: p.map((r) => r.s2), line: { color, width: 2, dash },
        marker: { size: 6, color }, hovertemplate: `${name}<br>%{x}: Stage 2 %{y:.2%}<extra></extra>` },
      { type: "scatter", mode: "lines", name: `${name} S3`, x: q, y: p.map((r) => r.s3), line: { color: C.down, width: 1.5, dash },
        hovertemplate: `${name}<br>%{x}: Stage 3 %{y:.2%}<extra></extra>` },
    ];
  };
  const data = [...series(rec, rec.role === "asked" ? "Ask" : "Recommended", C.rec, "solid")];
  if (asked && asked !== rec) data.push(...series(asked, "Ask", C.ask, "dot"));
  return <Plot data={data} height={230} testId="dealdesk-forward-path" filename="deal-desk-stage-path"
               ariaLabel="Probability of Stage 2 and Stage 3 over the next four quarters, recommended and asked structures"
               layout={{ ...layoutBase, yaxis: { tickformat: ".1%", rangemode: "tozero", title: { text: "Probability" } } }} />;
}

function ComparisonChart({ r }: { r: ForwardRiskResult }) {
  const rows = comparisonRows(r);
  const x = rows.map((s) => wrapLabel(s.label));
  const data = [
    { type: "bar", name: "P(Stage 2)", x, y: rows.map((s) => s.pStage2), marker: { color: rows.map((s) => (s.role === "asked" ? C.ask : C.rec)) },
      hovertemplate: "P(Stage 2) %{y:.2%}<extra></extra>" },
    { type: "scatter", mode: "markers", name: "ECL in 4 quarters (★ optimal)", x, y: rows.map((s) => s.eclQ4), yaxis: "y2",
      marker: { size: rows.map((s) => (s.optimal ? 15 : 10)), symbol: rows.map((s) => (s.optimal ? "star" : "circle")),
                color: rows.map((s) => (s.optimal ? C.up : C.hurdle)), line: { width: 1, color: "#fff" } },
      hovertemplate: "Expected ECL in 4 quarters SAR %{y:,.3f}m<extra></extra>" },
  ];
  return <Plot data={data} height={230} testId="dealdesk-forward-compare" filename="deal-desk-structure-forward-risk"
               ariaLabel="P(Stage 2) next quarter and expected ECL in four quarters for each structure; the ECL-optimal structure is starred"
               layout={{ ...layoutBase, margin: { l: 52, r: 56, t: 30, b: 36 },
                         xaxis: { automargin: true, tickangle: 0, tickfont: { size: 10 } },
                         yaxis: { tickformat: ".1%", rangemode: "tozero", title: { text: "P(Stage 2)" } },
                         yaxis2: { overlaying: "y", side: "right", rangemode: "tozero", tickformat: ",.2f", title: { text: "ECL, SAR m" } } }} />;
}

function DriverChart({ s }: { s: ForwardStructure }) {
  const d = driverBars(s).reverse();
  const data = [{
    type: "bar", orientation: "h", x: d.map((r) => r.contribution), y: d.map((r) => `${r.label} (${driverValue(r)})`),
    marker: { color: d.map((r) => (r.contribution > 0 ? C.down : C.up)) },
    hovertemplate: "%{y}<br>%{x:+.2f} log-odds against the book average<extra></extra>",
  }];
  return <Plot data={data} height={230} testId="dealdesk-forward-drivers" filename="deal-desk-forward-drivers"
               ariaLabel="The five features that move P(Stage 2) most for this structure, in log-odds against the book average"
               layout={{ ...layoutBase, showlegend: false, margin: { l: 8, r: 12, t: 30, b: 36 },
                         yaxis: { automargin: true, tickfont: { size: 10 } }, xaxis: { zeroline: true, title: { text: "Log-odds" } } }} />;
}

// ------------------------------------------------------------------ explanations

function PathInfo({ s, r }: { s: ForwardStructure; r: ForwardRiskResult }) {
  const m = s.chain.matrix;
  return <Explainer
    shows="The chance that the facility sits in Stage 2 or Stage 3 at the end of each of the next four quarters, for the recommended structure and the ask."
    formulas={[
      <>Stage 1 to Stage 2 each quarter: {prob(m[0][1])} ({s.chain.basis.s1_to_s2}).</>,
      <>Stage 1 to Stage 3: {prob(m[0][2])} ({s.chain.basis.s1_to_s3}).</>,
      <>Stage 2 back to Stage 1: {prob(m[1][0])} ({s.chain.basis.s2_to_s1}); Stage 2 to Stage 3: {prob(m[1][2])} ({s.chain.basis.s2_to_s3}).</>,
      <>Each quarter&apos;s mix is last quarter&apos;s mix times this matrix; the three stages sum to 100% at every point.</>,
    ]}
    read={<>After four quarters {prob(s.stage_path[4].s2)} in Stage 2 and {prob(s.stage_path[4].s3)} in Stage 3, against the book&apos;s {prob(r.book.p_stage2_next_q)} a quarter into Stage 2.</>}
    act="A path that climbs faster than the ask's points at a structure that adds risk; collateral and a shorter tenor usually flatten it."
    testId="dealdesk-forward-path-info" />;
}

function CompareInfo({ r }: { r: ForwardRiskResult }) {
  return <Explainer
    shows="P(Stage 2) next quarter (bars) and expected ECL in four quarters (markers, right axis) for every structure in Optimise."
    formulas={[
      <>Expected ECL = P(Stage 1) × 12-month EL + P(Stage 2) × lifetime EL + P(Stage 3) × EAD × LGD, with the engine&apos;s PD, LGD and EAD for each structure.</>,
      <>Day-1 ECL is the same sum with the facility in Stage 1 for certain: the engine&apos;s Day-1 ECL.</>,
      <>The ECL-optimal structure (star) has the lowest expected ECL in four quarters among the structures that clear the hurdle.</>,
    ]}
    read={r.ecl_optimal ? <>ECL-optimal: <b>{r.ecl_optimal.label}</b>, {money(r.ecl_optimal.ecl_q4)} expected in four quarters at {rate(r.ecl_optimal.lifetime_raroc)} RAROC.</>
      : <>No structure clears the hurdle, so none is marked ECL-optimal.</>}
    act="Prefer the starred structure when RAROC is close; the gap in expected ECL is what the cheaper-looking structure costs in provisions."
    testId="dealdesk-forward-compare-info" />;
}

function DriverInfo({ s }: { s: ForwardStructure }) {
  return <Explainer
    shows={`The five features that move ${s.label.toLowerCase()}'s P(Stage 2) furthest from the book average.`}
    formulas={[
      <>Each bar is the feature&apos;s contribution in log-odds, summed over the model&apos;s trees along this deal&apos;s path (red raises the probability, green lowers it).</>,
      <>Structure terms (utilisation, collateral cover, size, product) move with the structure; the rest describe the obligor before the deal (rating, ratios, arrears, early-warning signals) and its sector. Post-deal leverage and DSCR act through the limits and the early-warning covenant test.</>,
    ]}
    read="A long red bar on a structure term is a lever; a long red bar on the obligor is a risk the structure cannot change."
    act="Use the lever line under the charts to see what cutting the largest structure driver costs in RAROC."
    testId="dealdesk-forward-drivers-info" />;
}

function PanelInfo({ r }: { r: ForwardRiskResult }) {
  return <Explainer
    shows="The chance this deal moves to Stage 2 or reaches 30 days past due next quarter, its expected ECL over the next year, and the Early Warning rules on the obligor after the deal."
    formulas={[
      <>Two gradient-boosted tree models trained on the corporate facility-quarter book, calibrated isotonically: P(Stage 2 or worse at q+1 | Stage 1 at q) and P(30+ DPD at q+1).</>,
      <>P(Stage 2) is never below P(30+ DPD): 30 days past due is a Stage 2 backstop.</>,
      <>Book rate: the model&apos;s mean over the book&apos;s performing facilities at {r.as_of} ({prob(r.book.p_stage2_next_q)}); observed in {r.book.observed_quarter}: {prob(r.book.observed_stage2)}.</>,
      <>{r.method}</>,
    ]}
    read="Below the book is a deal that should stay performing; above it, plan for Stage 2 provisioning from the first quarter."
    act="Open the model card for the validation; compare structures before choosing one to recommend."
    testId="dealdesk-forward-info" />;
}

// ------------------------------------------------------------------ model card

function TransitionCardDialog({ onClose }: { onClose: () => void }) {
  const [card, setCard] = React.useState<TransitionCard | null>(null);
  const [error, setError] = React.useState("");
  React.useEffect(() => {
    let live = true;
    forwardApi.card().then((c) => { if (live) setCard(c); }, (e: unknown) => { if (live) setError(e instanceof Error ? e.message : String(e)); });
    return () => { live = false; };
  }, []);
  const targets = card ? (["stage2", "dpd30"] as const) : [];
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-auto bg-black/30 p-8" role="dialog" aria-modal="true"
         aria-label="Transition model card" data-testid="dealdesk-forward-model-card">
      <Card className="w-full max-w-4xl space-y-4 p-6">
        <div className="flex items-center gap-2">
          <h2 className="text-[16px] font-semibold text-text-primary">Transition model card</h2>
          {card ? <Chip>{card.version} · trained {card.trained} · book {card.as_of}</Chip> : null}
          <button type="button" onClick={onClose} aria-label="Close" data-testid="dealdesk-forward-model-card-close"
                  className="ml-auto rounded-md p-1 text-text-muted hover:bg-surface-hover"><X size={16} /></button>
        </div>
        {error ? <p className="text-[12px] text-negative" role="alert">{error}</p> : null}
        {!card && !error ? <Skeleton className="h-64 w-full" /> : null}
        {card ? (
          <>
            <dl className="grid grid-cols-[140px_1fr] gap-x-4 gap-y-1.5 text-[12px]">
              <dt className="text-text-muted">Method</dt><dd className="text-text-primary">{card.card.method}</dd>
              <dt className="text-text-muted">Validation</dt><dd className="text-text-primary">{card.card.split}</dd>
            </dl>
            <table className={tableCls} data-testid="dealdesk-forward-model-card-metrics">
              <thead><tr><th className={thCls}>Model</th><th className={cn(thCls, "text-right")}>AUC in / out of time</th>
                <th className={cn(thCls, "text-right")}>Gini out of time</th><th className={cn(thCls, "text-right")}>KS out of time</th>
                <th className={cn(thCls, "text-right")}>PSI train vs OOT</th><th className={cn(thCls, "text-right")}>OOT rate: actual / predicted</th></tr></thead>
              <tbody>{targets.map((t) => {
                const k = card.card.targets[t];
                return (
                  <tr key={t}><td className={tdCls}>{k.target}</td>
                    <td className={cn(tdCls, "text-right")}>{k.in_time.auc.toFixed(3)} / {k.out_of_time.auc.toFixed(3)}</td>
                    <td className={cn(tdCls, "text-right")}>{k.out_of_time.gini.toFixed(3)}</td>
                    <td className={cn(tdCls, "text-right")}>{k.out_of_time.ks.toFixed(3)}</td>
                    <td className={cn(tdCls, "text-right")}>{k.psi_train_vs_oot.toFixed(2)}</td>
                    <td className={cn(tdCls, "text-right")}>{prob(k.out_of_time.event_rate)} / {prob(k.out_of_time.mean_predicted)}</td></tr>);
              })}</tbody>
            </table>
            <div className="grid gap-4 md:grid-cols-2">
              {targets.map((t) => {
                const b = card.backtest[t];
                return (
                  <div key={t} className="min-w-0">
                    <ChartTitle title={t === "stage2" ? "Back-test: Stage 2 next quarter" : "Back-test: 30+ DPD next quarter"}
                                info={<>Predicted (served calibration) against the actual rate by origin quarter. Training: {card.card.targets[t].train_quarters}; out of time: {card.card.targets[t].oot_quarters}. {card.card.targets[t].calibration_note}</>} />
                    <Plot height={200} testId={`dealdesk-forward-backtest-${t}`} filename={`deal-desk-backtest-${t}`}
                          ariaLabel={`Predicted against actual ${t === "stage2" ? "Stage 2" : "30+ DPD"} rate by quarter`}
                          data={[
                            { type: "bar", name: "Actual", x: b.map((r) => r.quarter), y: b.map((r) => r.actual), marker: { color: b.map((r) => (r.sample === "out-of-time" ? C.ask : C.muted)) },
                              hovertemplate: "%{x}: actual %{y:.2%}<extra></extra>" },
                            { type: "scatter", mode: "lines+markers", name: "Predicted", x: b.map((r) => r.quarter), y: b.map((r) => r.predicted), line: { color: C.rec, width: 2 },
                              hovertemplate: "%{x}: predicted %{y:.2%}<extra></extra>" }]}
                          layout={{ ...layoutBase, margin: { l: 44, r: 8, t: 30, b: 44 }, yaxis: { tickformat: ".1%", rangemode: "tozero" }, xaxis: { tickfont: { size: 9 }, tickangle: -60 } }} />
                  </div>);
              })}
            </div>
            <table className={tableCls} data-testid="dealdesk-forward-model-card-deciles">
              <thead><tr><th className={thCls}>Score decile, out of time</th>
                <th className={cn(thCls, "text-right")}>Stage 2 predicted</th><th className={cn(thCls, "text-right")}>Stage 2 actual</th>
                <th className={cn(thCls, "text-right")}>30+ DPD predicted</th><th className={cn(thCls, "text-right")}>30+ DPD actual</th></tr></thead>
              <tbody>{card.card.targets.stage2.calibration_deciles_oot.map((d, i) => {
                const e = card.card.targets.dpd30.calibration_deciles_oot[i];
                return (
                  <tr key={d.decile}><td className={cn(tdCls, "py-1")}>{d.decile}</td>
                    <td className={cn(tdCls, "py-1 text-right")}>{prob(d.predicted)}</td><td className={cn(tdCls, "py-1 text-right")}>{prob(d.actual)}</td>
                    <td className={cn(tdCls, "py-1 text-right")}>{e ? prob(e.predicted) : "–"}</td><td className={cn(tdCls, "py-1 text-right")}>{e ? prob(e.actual) : "–"}</td></tr>);
              })}</tbody>
            </table>
            <div className="grid gap-4 md:grid-cols-2">
              {targets.map((t) => (
                <div key={t} className="text-[12px]">
                  <p className="font-medium text-text-secondary">Feature importance, {t === "stage2" ? "Stage 2" : "30+ DPD"} (share of gain)</p>
                  <ul className="mt-1 space-y-0.5 text-text-secondary">
                    {card.card.targets[t].importance.slice(0, 8).map((f) => (
                      <li key={f.feature} className="flex justify-between gap-2"><span className="truncate">{f.label}</span><span className="tabular-nums">{prob(f.share)}</span></li>))}
                  </ul>
                </div>))}
            </div>
            <div className="text-[12px]">
              <p className="font-medium text-text-secondary">Limitations</p>
              <ul className="mt-1 list-disc space-y-0.5 pl-4 text-text-secondary">{card.card.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
            </div>
          </>) : null}
      </Card>
    </div>
  );
}

// ------------------------------------------------------------------ the panel

export function ForwardRiskPanel({ proposalId, structures }: { proposalId: string; structures: readonly ForwardStructureInput[] }) {
  const [got, setGot] = React.useState<{ key: string; res: ForwardRiskResult | null; error: string } | null>(null);
  const [card, setCard] = React.useState(false);
  const key = React.useMemo(() => `${proposalId}|${JSON.stringify(requestBody(structures))}`, [proposalId, structures]);
  React.useEffect(() => {
    const ctl = new AbortController();
    const body = JSON.parse(key.slice(key.indexOf("|") + 1)) as { structures: ForwardStructureInput[] };
    forwardApi.run(proposalId, body.structures, ctl.signal).then(
      (r) => { if (!ctl.signal.aborted) setGot({ key, res: r, error: "" }); },
      (e: unknown) => { if (!ctl.signal.aborted) setGot({ key, res: null, error: e instanceof Error ? e.message : String(e) }); });
    return () => ctl.abort();
  }, [proposalId, key]);
  const current = got && got.key === key ? got : null;
  const res = current?.res ?? null;
  const error = current?.error ?? "";

  const action = <SecondaryButton onClick={() => setCard(true)} data-testid="dealdesk-forward-model-card-open">Model card</SecondaryButton>;
  const title = "Forward risk: Stage 2, 30+ DPD and ECL from day one";
  if (error) {
    return <Section title={title} testId="dealdesk-forward-risk" action={action}>
      <p className="text-[12px] text-negative" role="alert" data-testid="dealdesk-forward-error">{error}</p>
      {card ? <TransitionCardDialog onClose={() => setCard(false)} /> : null}
    </Section>;
  }
  if (!res) {
    return <Section title={title} testId="dealdesk-forward-risk" action={action}>
      <div className="space-y-3" data-testid="dealdesk-forward-loading"><Skeleton className="h-5 w-2/3" /><Skeleton className="h-16 w-full" /><Skeleton className="h-48 w-full" /></div>
    </Section>;
  }
  const problems = checkResult(res);
  const rec = headlineStructure(res);
  const asked = askedStructure(res);
  if (!rec || problems.length) {
    return <Section title={title} testId="dealdesk-forward-risk" action={action}>
      <p className="text-[12px] text-negative" role="alert">Forward risk could not be shown: {problems.join("; ") || "no structure returned"}.</p>
    </Section>;
  }
  const ews = res.ews;
  const s2Tone = vsBook(rec.p_stage2_next_q, res.book.p_stage2_next_q);
  const d30Tone = vsBook(rec.p_dpd30_next_q, res.book.p_dpd30_next_q);
  const tone = (t: "below" | "above" | "at") => (t === "below" ? "positive" : t === "above" ? "negative" : "neutral") as "positive" | "negative" | "neutral";
  const lever = leverLine(res);
  return (
    <Section title={title} testId="dealdesk-forward-risk" info={<PanelInfo r={res} />} action={action}>
      <p className="mb-3 break-words text-[13px] text-text-primary" data-testid="dealdesk-forward-answer">{res.answer}</p>
      <KpiRow testId="dealdesk-forward-tiles" tiles={[
        { label: "Stage 2 next quarter", value: prob(rec.p_stage2_next_q), tone: tone(s2Tone), testId: "dealdesk-forward-tile-stage2",
          sub: <>book {prob(res.book.p_stage2_next_q)}{rec.backstop_applied ? " · 30+ backstop" : ""}</>,
          info: <>P(Stage 2 or worse at the end of next quarter | Stage 1 today) for {rec.label.toLowerCase()}, calibrated. Book: the model&apos;s mean over the performing book at {res.as_of}.</> },
        { label: "30+ DPD next quarter", value: prob(rec.p_dpd30_next_q), tone: tone(d30Tone), testId: "dealdesk-forward-tile-dpd30",
          sub: <>book {prob(res.book.p_dpd30_next_q)}</>,
          info: <>P(30 or more days past due at the end of next quarter | under 30 today), calibrated. Observed book rate in {res.book.observed_quarter}: {prob(res.book.observed_dpd30)}.</> },
        { label: "Expected ECL in 4 quarters", value: money(rec.ecl.q4), testId: "dealdesk-forward-tile-ecl",
          tone: rec.ecl.q4 > rec.ecl.day1 * 1.5 ? "warning" : "neutral",
          sub: <>Day-1 {money(rec.ecl.day1)} · next quarter {money(rec.ecl.next_q)}</>,
          info: <>Σ stage probability × stage ECL from the engine&apos;s PD, LGD and EAD. Day-1 ECL is the engine&apos;s 12-month EL ({money(rec.ecl.engine_day_one_ecl)}).</> },
        { label: "Early warning band", value: bandLabel(ews.band), tone: bandTone(ews.band) === "neutral" ? "neutral" : bandTone(ews.band), testId: "dealdesk-forward-tile-ews",
          sub: <>score {ews.score}{ews.current ? ` · today ${bandLabel(ews.current.band)}` : " · new to bank"}</>,
          info: <>The live {ews.ruleset} corporate rules on the obligor after the deal ({ews.basis}). {ews.book.share_at_or_below !== null ? `${prob(ews.book.share_at_or_below)} of the book's ${ews.book.borrowers.toLocaleString("en-US")} borrowers score at or below this.` : ""}</> },
      ]} />
      <div className="mt-4 grid gap-4 xl:grid-cols-3" data-testid="dealdesk-forward-charts">
        <div className="min-w-0">
          <ChartTitle title="Stage path, next 4 quarters" info={<PathInfo s={rec} r={res} />} />
          <PathChart rec={rec} asked={asked} />
        </div>
        <div className="min-w-0">
          <ChartTitle title="Structures: P(Stage 2) and expected ECL" info={<CompareInfo r={res} />} />
          <ComparisonChart r={res} />
        </div>
        <div className="min-w-0">
          <ChartTitle title={`What drives it: ${rec.label}`} info={<DriverInfo s={rec} />} />
          <DriverChart s={rec} />
        </div>
      </div>
      <div className="mt-3 space-y-1.5 text-[12px] text-text-secondary" data-testid="dealdesk-forward-notes">
        <p className="flex flex-wrap items-center gap-1.5" data-testid="dealdesk-forward-ews-rules">
          <span className="text-text-muted">Early warning after the deal:</span>
          {ews.fired.length ? ews.fired.map((f) => (
            <Chip key={f.id} tone={f.weight >= 2 ? "warning" : "neutral"} title={`${f.rule} · ${Object.entries(f.values).map(([k, v]) => `${k} ${v}`).join(", ")}`}>
              {f.label} (+{f.weight})</Chip>)) : <Chip tone="positive">No rule fires</Chip>}
          {ews.current ? <span className="text-text-muted">· today {bandLabel(ews.current.band)} ({ews.current.score})</span> : null}
        </p>
        {res.ecl_optimal ? (
          <p data-testid="dealdesk-forward-optimal">ECL-optimal structure: <b className="text-text-primary">{res.ecl_optimal.label}</b>, {money(res.ecl_optimal.ecl_q4)} expected in 4 quarters at {rate(res.ecl_optimal.lifetime_raroc)} RAROC.
            {lever ? <> Best lever on {res.best_lever?.reference.toLowerCase()}: {lever}.</> : null}</p>
        ) : lever ? <p data-testid="dealdesk-forward-lever">Best lever on {res.best_lever?.reference.toLowerCase()}: {lever}.</p> : null}
      </div>
      {card ? <TransitionCardDialog onClose={() => setCard(false)} /> : null}
    </Section>
  );
}
