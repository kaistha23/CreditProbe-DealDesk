"use client";

/**
 * The active signal catalogue, rendered once and reused.
 *
 * Three surfaces live here and they all read the SAME server objects:
 *
 *   * `SourcesSurface` -- Bank Internal / Bureau / Open Banking, each with
 *     the signals it carries and, where it carries none, the sentence saying
 *     what feed is missing. A declared-but-empty group must not look like a
 *     group whose observations are merely filtered out;
 *   * `ReferenceSurface` -- the richer four-layer reference model, as
 *     definitions and per-input compatibility verdicts. It is labelled NOT
 *     deployed because none of its numbers produce anything here;
 *   * `CustomerSignals` -- the signals one customer or borrower actually
 *     fires, with the observed value in its own unit.
 *
 * No condition, threshold or unit is restated in this file: every one of them
 * comes from the catalogue the server served, so the model screen and a
 * customer's alert cannot word the same evidence differently.
 */

import * as React from "react";

import type {
  CatalogueSignal,
  EntitySignals,
  ReferenceCompatibility,
  SignalCatalogue,
} from "@/ews-preview/lib/workspace/canonical";
import { EAD_NOT_ADDITIVE, type RuleSummary } from "@/ews-preview/components/guided/customer-issues";

const num = new Intl.NumberFormat("en-US");

function count(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : num.format(value);
}

/** An observed value in its own unit. Never reformatted into another one. */
export function observedValue(value: unknown, unit: string): string {
  if (value === null || value === undefined || value === "") return "—";
  if (unit === "flag") return value === 1 || value === true ? "Yes" : "No";
  if (typeof value !== "number") return String(value);
  if (unit === "percent") return `${num.format(Math.round(value * 10) / 10)}%`;
  if (unit === "days" || unit === "count" || unit === "notches") return num.format(value);
  return num.format(Math.round(value * 100) / 100);
}

/** A served status token as words. The contract value is never shown raw. */
function statusWords(status: string): string {
  const words = status.replace(/_/g, " ").toLowerCase();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

const STATUS: Record<string, { text: string; tone: string }> = {
  live: { text: "Live", tone: "text-positive" },
  live_no_match: { text: "Live · matches nothing here", tone: "text-warning" },
  not_evaluated: { text: "Not evaluated · input not published", tone: "text-negative" },
};

function SignalRow({ signal, ownerNoun }: { signal: CatalogueSignal; ownerNoun: string }) {
  const status = STATUS[signal.status ?? "live"] ?? STATUS.live;
  return (
    <details className="border-t border-border px-2 py-1.5" data-testid="ews-catalogue-signal" data-signal={signal.id}>
      <summary className="flex cursor-pointer flex-wrap items-baseline gap-x-2 gap-y-0.5 text-xs">
        <span className="font-medium">{signal.id}</span>
        <span>{signal.label}</span>
        <span className="text-text-muted">{signal.family_label}</span>
        {signal.proxy ? <span className="text-warning">proxy</span> : null}
        <span className={`ml-auto ${status.tone}`}>{status.text}</span>
        <span className="tabular text-text-muted">
          {count(signal.owners_tripped)} {ownerNoun}
        </span>
      </summary>
      <div className="space-y-1.5 py-1.5 pl-3 text-xs text-text-muted">
        <p>{signal.condition}</p>
        <p className="font-mono text-[11px]">{signal.expression}</p>
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5">
          <dt>Source</dt>
          <dd>
            {signal.source_label}
            {signal.source_connected ? "" : " · not published in this release"}
          </dd>
          <dt>Risk layer</dt>
          <dd data-testid="ews-catalogue-layer" data-layer={signal.layer}>
            {signal.layer_label || signal.layer}
            {signal.layer_means ? <span className="block">{signal.layer_means}</span> : null}
          </dd>
          <dt>Rule weight</dt>
          <dd className="tabular">{signal.weight}</dd>
          <dt>Recommended review</dt>
          <dd>{signal.review}</dd>
        </dl>
        <table className="w-full">
          <thead className="text-left text-text-secondary">
            <tr>
              <th className="py-0.5 pr-3 font-medium">Input</th>
              <th className="py-0.5 pr-3 font-medium">Unit</th>
              <th className="py-0.5 pr-3 font-medium">Grain</th>
              <th className="py-0.5 font-medium">Meaning</th>
            </tr>
          </thead>
          <tbody>
            {signal.inputs.map((one) => (
              <tr key={one.column} className="align-top">
                <td className="py-0.5 pr-3 font-mono text-[11px]">{one.column}</td>
                <td className="py-0.5 pr-3">{one.unit}</td>
                <td className="py-0.5 pr-3">{one.grain}</td>
                <td className="py-0.5">
                  {one.meaning}
                  {one.published === false ? (
                    <span className="block text-negative">not published by this release</span>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {signal.limitation ? <p className="text-warning">{signal.limitation}</p> : null}
      </div>
    </details>
  );
}

/** Source → signal family → signal. The navigation the user asked for. */
export function SourcesSurface({
  catalogue,
  ownerNoun,
}: {
  catalogue: SignalCatalogue;
  ownerNoun: string;
}) {
  const byId = React.useMemo(
    () => new Map(catalogue.signals.map((s) => [s.id, s])),
    [catalogue.signals],
  );
  return (
    <div className="space-y-2" data-testid="ews-sources">
      <p className="text-xs text-text-muted">{catalogue.axes}</p>
      {catalogue.sources.map((source) => {
        const families = catalogue.families
          .map((family) => ({
            ...family,
            members: family.signals
              .filter((id) => source.signals.includes(id))
              .map((id) => byId.get(id))
              .filter((s): s is CatalogueSignal => Boolean(s)),
          }))
          .filter((family) => family.members.length > 0);
        return (
          <section
            key={source.key}
            className="rounded-lg border border-border"
            data-testid="ews-source-group"
            data-source={source.key}
            data-connected={source.connected ? "yes" : "no"}
          >
            <header className="flex flex-wrap items-baseline gap-2 px-2 py-1.5">
              <h3 className="text-xs font-semibold">{source.label}</h3>
              <span className={`text-xs ${source.connected ? "text-positive" : "text-negative"}`}>
                {source.availability}
              </span>
              <span className="ml-auto text-xs tabular text-text-muted">
                {source.evaluable_count ?? source.signal_count} of {source.signal_count} signals evaluable
              </span>
            </header>
            <p className="px-2 pb-1.5 text-xs text-text-muted">{source.means}</p>
            <details className="px-2 pb-1.5 text-xs" data-testid="ews-source-availability">
              <summary className="cursor-pointer text-text-muted">
                {source.connected
                  ? "What this release publishes for this group"
                  : `Why no signal here is evaluated (${source.requires.length} inputs needed)`}
              </summary>
              <p className={`pt-1 ${source.connected ? "text-text-muted" : "text-warning"}`}>
                {source.connected ? source.availability_means : source.absent_because}
              </p>
              {source.connected || !source.requires.length ? null : (
                <ul className="mt-0.5 list-disc pl-4 text-text-muted">
                  {source.requires.map((one) => (
                    <li key={one}>{one}</li>
                  ))}
                </ul>
              )}
            </details>
            {families.map((family) => (
              <div key={family.key} className="border-t border-border">
                <div className="bg-surface-sunken px-2 py-1 text-[11px] font-medium text-text-secondary">
                  {family.label} · {family.means}
                </div>
                {family.members.map((signal) => (
                  <SignalRow key={signal.id} signal={signal} ownerNoun={ownerNoun} />
                ))}
              </div>
            ))}
          </section>
        );
      })}
    </div>
  );
}

/** The reference model: definitions, and why its inputs do or do not map. */
export function ReferenceSurface({ reference }: { reference: ReferenceCompatibility }) {
  const [onlyGaps, setOnlyGaps] = React.useState(true);
  if (!reference.available) {
    return (
      <p className="text-xs text-text-muted" data-testid="ews-reference-absent">
        No reference model is carried in this checkout.
      </p>
    );
  }
  const counts = reference.summary.by_canonical_status ?? {};
  const rows = reference.inputs.filter((one) => !onlyGaps || one.canonical_status !== "EXACT");
  return (
    <div className="space-y-2" data-testid="ews-reference">
      <div className="rounded-lg border border-warning/60 bg-warning/5 p-2 text-xs">
        <p className="font-medium">
          {reference.model.model_name} {reference.model.model_version} · {statusWords(reference.status)}
        </p>
        <p className="text-text-muted">{reference.means}</p>
        {reference.applies_to_domain ? null : (
          <p className="pt-1 text-warning" data-testid="ews-reference-domain-note">
            {reference.domain_note}
          </p>
        )}
      </div>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs text-text-muted">
        <dt>Shape</dt>
        <dd className="tabular">
          {count(reference.summary.reference_layers)} layers · {count(reference.summary.reference_triggers)} triggers ·{" "}
          {count(reference.summary.reference_classifiers)} classifiers ·{" "}
          {count(reference.summary.reference_hard_triggers)} hard triggers
        </dd>
        <dt>Inputs audited</dt>
        <dd className="tabular">
          {Object.entries(counts)
            .map(([status, n]) => `${status.toLowerCase().replace(/_/g, " ")} ${n}`)
            .join(" · ")}
        </dd>
      </dl>
      <p className="text-xs">{reference.summary.verdict}</p>
      <label className="flex items-center gap-1.5 text-xs text-text-muted">
        <input type="checkbox" checked={onlyGaps} onChange={(e) => setOnlyGaps(e.target.checked)} />
        Show only inputs that do not map exactly
      </label>
      <div className="max-h-96 overflow-auto rounded-lg border border-border">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-surface-sunken text-left">
            <tr>
              <th className="px-2 py-1.5">Reference input</th>
              <th className="px-2 py-1.5">Where it sits</th>
              <th className="px-2 py-1.5">True source</th>
              <th className="px-2 py-1.5">Canonical field</th>
              <th className="px-2 py-1.5">Verdict</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((one) => (
              <tr
                key={`${one.reference_key}:${one.reference_column}:${one.role}`}
                className="border-t border-border align-top"
                data-testid="ews-reference-input"
                data-status={one.canonical_status}
              >
                <td className="px-2 py-1.5">
                  <span className="font-mono text-[11px]">{one.reference_column}</span>
                  <span className="block text-text-muted">
                    {one.reference_name} · {one.reference_kind}
                  </span>
                </td>
                <td className="px-2 py-1.5 text-text-muted">
                  {one.reference_layer} / {one.reference_sublayer}
                </td>
                <td className="px-2 py-1.5 text-text-muted">
                  {one.true_source_group.replace(/_/g, " ")}
                  {one.source_group_connected ? "" : " · not published in this release"}
                </td>
                <td className="px-2 py-1.5">
                  {one.canonical_field ? (
                    <>
                      <span className="font-mono text-[11px]">{one.canonical_field}</span>
                      <span className="block text-text-muted">
                        {one.canonical_label} {one.canonical_unit ? `· ${one.canonical_unit}` : ""}
                      </span>
                    </>
                  ) : (
                    <span className="text-text-muted">—</span>
                  )}
                </td>
                <td className="px-2 py-1.5">
                  <span
                    className={
                      one.canonical_status === "MISSING"
                        ? "text-negative"
                        : one.canonical_status === "EXACT"
                          ? "text-positive"
                          : "text-warning"
                    }
                  >
                    {one.canonical_status.toLowerCase().replace(/_/g, " ")}
                  </span>
                  <span className="block text-text-muted">{one.note}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <details className="text-xs text-text-muted" data-testid="ews-reference-provenance">
        <summary className="cursor-pointer">Provenance of this comparison</summary>
        <p className="pt-1">
          Captured read-only from {reference.model.source} at {reference.model.captured_utc}, digest{" "}
          <span className="font-mono">{(reference.model.file_sha256 ?? "").slice(0, 16)}</span>. Definitions only: no
          score, band, customer or row count from that instance is carried, and none of its numbers appear anywhere in
          this product.
        </p>
      </details>
    </div>
  );
}

/**
 * One customer's or borrower's FIRED signals, from the same catalogue.
 *
 * Only fired signals appear. Each carries its id, source, family, the
 * observed value in its own unit, the period it was observed in and the
 * condition it met. The rule WEIGHT is shown as a rule weight, because
 * gw-ews-1.0.0 is a rule set: there is no fitted contribution to show and
 * none is composed.
 */
export function CustomerSignals({
  signals,
  onInvestigate,
  summary,
}: {
  signals: EntitySignals | null;
  onInvestigate?: (signalId: string, label: string) => void;
  /**
   * The profile's half of the same rule, keyed by rule id: how many of this
   * owner's exposures tripped it and their EAD. Optional, because the model
   * screen reads the catalogue without a profile open.
   */
  summary?: Record<string, RuleSummary>;
}) {
  if (!signals) return null;
  if (!signals.found) {
    return (
      <p className="text-xs text-text-muted" data-testid="ews-customer-absent">
        {signals.entity_id} has no exposure on {signals.release_id} at {signals.period}.
      </p>
    );
  }
  return (
    <section className="space-y-2" data-testid="ews-customer-signals">
      <div className="flex flex-wrap items-baseline gap-2">
        <h3 className="text-xs font-semibold">Signals firing for {signals.entity_id}</h3>
        <span className="text-xs text-text-muted">
          {signals.fired_count} fired · {signals.active_model.name} {signals.active_model.version} · observed{" "}
          {signals.period} on {signals.release_id}
        </span>
        <span
          className={`ml-auto text-xs ${signals.truncated ? "text-warning" : "text-text-muted"}`}
          data-testid="ews-customer-coverage"
          data-truncated={signals.truncated ? "yes" : "no"}
        >
          {signals.exposures_shown} of {signals.exposures_total} rows
        </span>
      </div>
      {signals.truncated ? (
        <p className="text-xs text-warning" data-testid="ews-customer-truncated">
          {signals.truncation_note}
        </p>
      ) : null}
      {signals.fired_signals.length === 0 ? (
        <p className="text-xs text-text-muted" data-testid="ews-customer-none">
          No governed signal fires here at {signals.period}.
        </p>
      ) : (
        <ul className="space-y-1.5">
          {signals.fired_signals.map((one) => (
            <li
              key={one.id}
              className="rounded-lg border border-border p-2"
              data-testid="ews-customer-signal"
              data-signal={one.id}
            >
              <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 text-xs">
                <span className="font-medium">{one.id}</span>
                <span>{one.label}</span>
                <span className="text-text-muted" data-testid="ews-customer-layer" data-layer={one.layer}>
                  {one.source_label} · {one.family_label} · {one.layer_label || one.layer}
                </span>
                {one.proxy ? <span className="text-warning">proxy</span> : null}
                {onInvestigate ? (
                  <button
                    type="button"
                    className="ml-auto rounded border border-border px-1.5 py-0.5 text-[11px]"
                    onClick={() => onInvestigate(one.id, one.label)}
                    data-testid="ews-customer-investigate"
                  >
                    Investigate
                  </button>
                ) : null}
              </div>
              <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs text-text-muted">
                <dt>Condition met</dt>
                <dd>{one.condition}</dd>
                <dt>Rule weight</dt>
                <dd className="tabular">
                  {one.weight} · {one.contribution_kind.replace(/_/g, " ")}
                </dd>
                {summary?.[one.id] ? (
                  <>
                    <dt>Tripped by</dt>
                    <dd
                      className="tabular"
                      data-testid="ews-customer-rule-population"
                      data-rule={one.id}
                    >
                      {summary[one.id].exposures} exposure
                      {summary[one.id].exposures === 1 ? "" : "s"} · EAD{" "}
                      {summary[one.id].ead_sar_mn.toLocaleString(undefined, {
                        maximumFractionDigits: 2,
                      })}
                      mn SAR
                    </dd>
                  </>
                ) : null}
                <dt>Recommended review</dt>
                <dd>{one.review}</dd>
              </dl>
              {/* One dated observation per exposure that fired this rule. The
                  worst-scoring exposure's value is never shown as the whole
                  borrower's evidence. */}
              <table className="mt-1 w-full text-xs" data-testid="ews-customer-observations">
                <thead className="text-left text-text-secondary">
                  <tr>
                    <th className="py-0.5 pr-3 font-medium">{one.observed_exposures > 1 ? "Exposure" : "On"}</th>
                    <th className="py-0.5 pr-3 font-medium">Observed</th>
                    <th className="py-0.5 pr-3 font-medium">Observed at</th>
                    <th className="py-0.5 font-medium">Severity there</th>
                  </tr>
                </thead>
                <tbody>
                  {one.observations.map((obs) => (
                    <tr
                      key={obs.exposure}
                      className="border-t border-border align-top text-text-muted"
                      data-testid="ews-customer-observation"
                      data-exposure={obs.exposure}
                    >
                      <td className="py-0.5 pr-3 font-mono text-[11px]">{obs.exposure}</td>
                      <td className="py-0.5 pr-3 tabular">
                        {obs.values.map((v) => `${v.label} ${observedValue(v.value, v.unit)}`).join(" · ")}
                      </td>
                      <td className="py-0.5 pr-3">{obs.observed_period}</td>
                      <td className="py-0.5 tabular">
                        {obs.ews_band || "—"}
                        {obs.ews_score === null ? "" : ` ${obs.ews_score}`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {/* The primary row carries the observation; the field behind it
                  -- column, unit, grain and how it is dated -- stays one
                  disclosure away rather than crowding the finding. */}
              <details className="mt-1 text-xs text-text-muted" data-testid="ews-customer-fields">
                <summary className="cursor-pointer">Fields this signal read</summary>
                <ul className="pt-1">
                  {one.observed.map((v) => (
                    <li key={v.column} data-testid="ews-customer-field" data-column={v.column}>
                      <span className="font-mono text-[11px]">{v.column}</span> · {v.label} · {v.unit} · per{" "}
                      {v.grain} · dated {v.observed_as} · {one.source_label}
                    </li>
                  ))}
                </ul>
                <p className="pt-1">{one.layer_means}</p>
              </details>
              {one.limitation ? <p className="mt-1 text-xs text-warning">{one.limitation}</p> : null}
            </li>
          ))}
        </ul>
      )}
      <details className="text-xs text-text-muted" data-testid="ews-customer-basis">
        <summary className="cursor-pointer">How these are scored</summary>
        <p className="pt-1">{signals.active_model.scoring}</p>
        <p className="pt-1">{signals.aggregation}</p>
        <p className="pt-1">{signals.contribution_disclosure}</p>
        <p className="pt-1">{signals.override_disclosure}</p>
        <p className="pt-1">{signals.truncation_note}</p>
        {summary ? <p className="pt-1">{EAD_NOT_ADDITIVE}</p> : null}
        {signals.sources
          .filter((s) => !s.connected)
          .map((s) => (
            <p key={s.key} className="pt-1">
              <span className="font-medium">{s.label}:</span> {s.absent_because}
            </p>
          ))}
      </details>
    </section>
  );
}
