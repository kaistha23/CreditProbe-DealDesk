"use client";

/**
 * Early Warning, drilled: portfolio to the named customer, in one book.
 *
 * The ladder is the point. A number on a portfolio card is only actionable if
 * you can walk it down to the customers inside it, so Corporate goes
 * sector -> sub-sector (or rating) -> borrower -> facility and Retail goes
 * product -> sub-product (or arrears bucket) -> customer -> account, and every
 * rung is read from the SAME canonical adapter at the SAME period, so the
 * counts at the bottom add up to the card at the top.
 *
 * Two things this screen refuses to blur:
 *
 *   Grain. "Customers" and "accounts" are different numbers and are shown as
 *   different numbers. A customer with four warned accounts is one warned
 *   customer. The counts are distinct counts of owners, never a count of
 *   alert rows.
 *
 *   Already-bad versus still-performing. Stage 3 and defaults are a loss that
 *   has happened; the warned-but-performing population is what early warning
 *   is for. They are two cards, because adding them would count the same
 *   borrower twice and reading them as one hides whether anything is
 *   actionable.
 *
 * The rule metadata panel shows the rule set exactly as applied -- each rule's
 * expression, its inputs, whether the open release can evaluate it, and the
 * population it actually tripped. A rule whose input the release does not
 * publish says so instead of rendering as a zero.
 */

import * as React from "react";

/** The surfaces of the rule-set panel. Exported for the dedicated model route. */
export type EwsSurface = "model" | "sources" | "signals" | "tree" | "reference" | "log";

import { ReferenceSurface, SourcesSurface } from "@/ews-preview/components/early-warning/signal-catalogue";
import { useRouter } from "next/navigation";
import { ChevronRight, ExternalLink, Loader2 } from "lucide-react";

import {
  borrower360Href,
  drill as drillRead,
  modelMeta,
  type Drill,
  type LevelPoint,
  type LevelReason,
  type LevelRow,
  type ModelMeta,
  type OverviewPoint,
  type OwnerRow,
} from "@/ews-preview/lib/workspace/canonical";
import { modelIdentity, modelIsCurrent } from "@/ews-preview/lib/workspace/model-identity";
import type { DomainId } from "@/ews-preview/lib/workspace/objects";
import { count, pct, sar, sarFull } from "@/ews-preview/lib/viz/format";
import { SEVERITY_COLORS } from "@/ews-preview/lib/viz/palette";
import { currentAddress } from "@/ews-preview/lib/workspace/nav";

/** "facility" -> "facilities", "account" -> "accounts". */
function grainPlural(grain: string): string {
  return grain.endsWith("y") ? `${grain.slice(0, -1)}ies` : `${grain}s`;
}

const BANDS = ["critical", "high", "moderate", "low"] as const;

/** A value as it reads in a path, never an empty string pretending to be one. */
function label(value: string | number | null): string {
  return value === null || value === "" ? "(not recorded)" : String(value);
}

export function EwsDrill({
  domain,
  period,
  reason,
  dpd = "",
  bands = [],
  onPeriod,
  onReason,
}: {
  domain: DomainId;
  period: string;
  reason: string;
  /**
   * The delinquency band filtering the page above, applied to every rung.
   *
   * Passed rather than read from the address here so there is one owner of
   * the filter: the cards, this ladder and the grid are one population or
   * the screen is lying about which customers are warned.
   */
  dpd?: string;
  /**
   * The WARNING SEVERITIES the page above is focused on, applied to every
   * rung, for the same one-owner reason as `dpd`.
   *
   * Early Warning's cards, grid and handoffs are high + critical (or the one
   * band a reader clicked). Before this was passed, the ladder underneath
   * them read EVERY severity, so a reader who clicked "critical" was shown
   * critical headline numbers above a drill that still contained moderate
   * and low exposures. Empty means no severity filter at all.
   */
  bands?: string[];
  onPeriod: (p: string) => void;
  onReason: (r: string) => void;
}) {
  const router = useRouter();
  // The drill position belongs to a BOOK: a Retail product is not a
  // Corporate sector, so the position is stored with the domain it was taken
  // in and derived back to the portfolio when the book changes. Deriving it
  // (rather than resetting it from an effect) means the first render after a
  // switch is already at the portfolio, never one frame of the wrong book.
  const [picked, setPicked] = React.useState<{ domain: DomainId; path: Drill["path"]; search: string }>({
    domain,
    path: [],
    search: "",
  });
  const here = picked.domain === domain ? picked : { domain, path: [] as Drill["path"], search: "" };
  const path = here.path;
  const search = here.search;
  const [alternate, setAlternate] = React.useState(false);
  /* Cards, not a thin table, are the default: a row of six numbers does not
     tell a reader whether a sector is worth opening. A card carries both
     grains, the already-bad / still-performing split, the move since last
     period with the series it came from, and the rules actually driving it.
     The table stays one button away for anyone comparing many values. */
  const [asTable, setAsTable] = React.useState(false);
  const [surface, setSurface] = React.useState<EwsSurface>("model");
  const [loaded, setLoaded] = React.useState<{ key: string; feed: Drill | null }>({ key: "", feed: null });
  const [model, setModel] = React.useState<ModelMeta | null>(null);
  const [error, setError] = React.useState("");
  const [showModel, setShowModel] = React.useState(false);
  const [ownerPending, setOwnerPending] = React.useState("");

  // The book, the period, the position, the rule filter and the search decide
  // the whole payload, so the payload is keyed by all of them: a reply that
  // arrives after the reader has moved on is ignored rather than rendered.
  const bandKey = React.useMemo(() => [...bands].sort().join(","), [bands]);
  const key = JSON.stringify([domain, period, path, reason, dpd, bandKey, alternate, search]);
  const feed = loaded.key === key ? loaded.feed : null;

  React.useEffect(() => {
    let live = true;
    drillRead({ domain, period, path, reason, dpd, bands, alternate, search, limit: 50 })
      .then((d) => {
        if (!live) return;
        setLoaded({ key, feed: d });
        setError("");
      })
      .catch((e: unknown) => live && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      live = false;
    };
    // `bands` is covered by `bandKey`: an array literal from the parent is a
    // new reference every render and would re-read the book on every one.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [domain, period, path, reason, dpd, bandKey, alternate, search, key]);

  /**
   * The rule set is identified by the book it was applied to, not by the
   * domain: the same domain has several releases and every release has many
   * periods, and coverage ("evaluable on this release", "scored exposures")
   * is a fact about ONE of them. Keying the cache on the domain alone left
   * last period's coverage on screen after a period switch.
   */
  const want = modelIdentity(domain, period);
  const have = modelIsCurrent(model, want);
  React.useEffect(() => {
    if (!showModel || have) return;
    let live = true;
    modelMeta({ domain, period })
      .then((m) => live && setModel(m))
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [showModel, domain, period, have, want]);

  if (error) {
    return (
      <p role="alert" className="rounded-md border border-negative bg-negative-muted px-3 py-2 text-sm text-negative">
        {error}
      </p>
    );
  }
  if (!feed) {
    return (
      <p className="flex items-center gap-2 text-sm text-text-muted">
        <Loader2 className="h-4 w-4 animate-spin" /> Reading the book…
      </p>
    );
  }

  const id = feed.overview;
  const t = id.totals;
  const ownerNoun = id.owner_grain === "borrower" ? "borrowers" : "customers";
  const exposureNoun = id.exposure_grain === "facility" ? "facilities" : "accounts";

  function go(level: string, value: string | number | null) {
    setPicked({ domain, path: [...path, { level, value }], search: "" });
  }
  function upTo(depth: number) {
    setPicked({ domain, path: path.slice(0, depth), search: "" });
  }
  const setSearch = (s: string) => setPicked({ domain, path, search: s });

  return (
    <div className="space-y-5" data-testid="ews-drill">
      {ownerPending && (
        <p className="rounded-md border border-warning bg-warning-muted px-3 py-2 text-xs" data-testid="ews-360-pending" data-href={ownerPending}>
          Borrower 360 is not restored yet. The context this button carries is{" "}
          <span className="font-medium">{ownerPending}</span> — the same owner id, book and period.{" "}
          <button type="button" onClick={() => setOwnerPending("")} className="text-accent underline">Close</button>
        </p>
      )}
      <div className="flex flex-wrap items-center gap-3 text-xs text-text-muted">
        <label className="flex items-center gap-1.5">
          <span className="font-medium text-text-primary">Period</span>
          <select
            value={id.period}
            onChange={(e) => onPeriod(e.target.value)}
            className="rounded border border-border bg-surface px-2 py-1 text-xs"
            data-testid="ews-period"
          >
            {id.periods.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>
        <span
          data-testid="ews-identity"
          data-release={id.release_id}
          data-period={id.period}
          data-bands={bandKey}
        >
          {id.release_id} · rule set {id.ruleset} · one row per {id.exposure_grain} · no model call
        </span>
        {/* WHICH POPULATION THIS LADDER IS. Stated on the ladder itself,
            because the numbers below are only the cards' numbers if the
            filters above were actually applied to them. */}
        {bands.length ? (
          <span
            className="rounded border border-accent bg-accent-muted px-2 py-0.5 text-[11px] text-text-primary"
            data-testid="ews-drill-bands"
            data-bands={bandKey}
          >
            {bands.join(" + ")} only
            {reason ? ` · ${reason}` : ""}
            {dpd ? ` · ${dpd}` : ""}
          </span>
        ) : null}
        <button
          type="button"
          onClick={() => setShowModel((v) => !v)}
          className="rounded border border-border px-2 py-0.5 text-xs"
          data-testid="ews-model-toggle"
        >
          {showModel ? "Hide" : "Show"} rules, signals and coverage
        </button>
      </div>

      {/* ---- the overview: both grains, bad kept apart from warned ---- */}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" data-testid="ews-overview">
        <Card
          title={`${ownerNoun} in scope`}
          value={count(t.owners)}
          lines={[`${count(t.exposures)} ${exposureNoun}`, `EAD ${sar(t.ead_sar_mn)} · ECL ${sar(t.ecl_sar_mn)}`]}
          testId="ews-card-scope"
        />
        <Card
          title="Already bad"
          value={count(t.bad_owners)}
          lines={[
            `${count(t.bad_exposures)} ${exposureNoun} · Stage 3 or in default`,
            `EAD ${sar(t.bad_ead_sar_mn)} (${pct(t.ead_sar_mn ? t.bad_ead_sar_mn / t.ead_sar_mn : null, 1)} of EAD)`,
          ]}
          colour={SEVERITY_COLORS.critical}
          testId="ews-card-bad"
        />
        <Card
          title="Still performing, warned"
          value={count(t.warned_performing_owners)}
          lines={[
            `${count(t.warned_performing_exposures)} ${exposureNoun} · high or critical, no default`,
            `EAD ${sar(t.warned_performing_ead_sar_mn)} (${pct(t.ead_sar_mn ? t.warned_performing_ead_sar_mn / t.ead_sar_mn : null, 1)} of EAD)`,
          ]}
          colour={SEVERITY_COLORS.high}
          testId="ews-card-warned"
        />
        <div className="rounded-xl border border-border bg-surface p-3" data-testid="ews-card-bands">
          <div className="text-xs font-medium text-text-muted">{ownerNoun} by severity</div>
          <div className="text-[10px] leading-tight text-text-muted">
            Worst band held · adds to {count(t.owners)}
          </div>
          <table className="mt-1 w-full text-xs">
            <tbody>
              {BANDS.map((band) => {
                const row = id.bands.find((b) => b.value === band);
                return (
                  <tr key={band} data-testid={`ews-band-${band}`}>
                    <td className="py-0.5">
                      <span className="inline-block h-2 w-2 rounded-full align-middle" style={{ background: SEVERITY_COLORS[band] }} />{" "}
                      {band}
                    </td>
                    <td className="py-0.5 text-right tabular">{count(row?.owners ?? 0)}</td>
                    <td className="py-0.5 text-right tabular text-text-muted">{count(row?.exposures ?? 0)} {id.exposure_grain}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* ---- how the rung itself moved, from the same read at each period ---- */}
      {feed.history && feed.history.length > 1 ? (
        <PortfolioHistory history={feed.history} ownerNoun={ownerNoun} period={id.period} />
      ) : null}

      {/* ---- the ladder ---- */}
      <nav className="flex flex-wrap items-center gap-1 text-sm" aria-label="Drill path" data-testid="ews-breadcrumb">
        <button type="button" onClick={() => upTo(0)} className="rounded px-1.5 py-0.5 underline-offset-2 hover:underline">
          Whole portfolio
        </button>
        {feed.path.map((step, i) => (
          <React.Fragment key={`${step.level}-${i}`}>
            <ChevronRight className="h-3.5 w-3.5 text-text-muted" />
            <button
              type="button"
              onClick={() => upTo(i + 1)}
              className="rounded px-1.5 py-0.5 font-medium underline-offset-2 hover:underline"
              data-testid="ews-crumb"
            >
              {label(step.value)}
            </button>
          </React.Fragment>
        ))}
      </nav>

      {/* ---- the next rung, or the owners themselves ---- */}
      {feed.next_level ? (
        <section className="space-y-2">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-sm font-semibold">
              By {feed.level.label.toLowerCase()}
              <span className="ml-2 font-normal text-text-muted">{feed.next_level.length} values · click one to drill</span>
            </h2>
            <div className="flex items-center gap-2">
              {feed.level.alternate && (
                <button
                  type="button"
                  onClick={() => setAlternate((v) => !v)}
                  className="rounded border border-border px-2 py-0.5 text-xs"
                  data-testid="ews-alternate"
                >
                  Break down by {alternate ? feed.level.label.toLowerCase() : feed.level.alternate.replace(/_/g, " ")}
                </button>
              )}
              <button
                type="button"
                onClick={() => setAsTable((v) => !v)}
                className="rounded border border-border px-2 py-0.5 text-xs"
                data-testid="ews-level-layout"
              >
                {asTable ? "Show as cards" : "Show as table"}
              </button>
            </div>
          </div>
          {asTable ? (
            <LevelTable
              rows={feed.next_level}
              ownerNoun={ownerNoun}
              exposureNoun={exposureNoun}
              onPick={(v) => go(feed.level.column_in_use, v)}
            />
          ) : (
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3" data-testid="ews-level-cards">
              {feed.next_level.map((row) => (
                <LevelCard
                  key={label(row.value)}
                  row={row}
                  series={feed.level_history?.[row.value === null ? "" : String(row.value)] ?? []}
                  reasons={feed.level_reasons?.[row.value === null ? "" : String(row.value)] ?? []}
                  ownerNoun={ownerNoun}
                  exposureNoun={exposureNoun}
                  period={id.period}
                  onPick={() => go(feed.level.column_in_use, row.value)}
                />
              ))}
            </div>
          )}
        </section>
      ) : null}

      {feed.owners ? (
        <section className="space-y-2" data-testid="ews-owners">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-sm font-semibold">
              {count(feed.owners.total.owners)} {ownerNoun} here
              <span className="ml-2 font-normal text-text-muted">
                {count(feed.owners.total.exposures)} {exposureNoun} · EAD {sar(feed.owners.total.ead_sar_mn)}
              </span>
            </h2>
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={`Search ${ownerNoun} by id or name`}
              className="w-64 rounded border border-border bg-surface px-2 py-1 text-xs"
              data-testid="ews-owner-search"
            />
          </div>
          <OwnerTable
            rows={feed.owners.rows}
            fields={feed.owners.fields}
            domain={domain}
            release={id.release_id}
            period={id.period}
            exposureNoun={exposureNoun}
            /* Borrower 360 is queued for restoration, so the button carries
               the owner's context and says so rather than opening a route the
               preview does not serve. */
            onOpen={(href) => setOwnerPending(href)}
          />
          {feed.owners.total.owners > feed.owners.rows.length && (
            <p className="text-xs text-text-muted">
              Showing the {feed.owners.rows.length} largest by EAD of {count(feed.owners.total.owners)}. Narrow the path or
              search to see the rest.
            </p>
          )}
        </section>
      ) : null}

      {/* ---- why, with materiality ---- */}
      <section className="space-y-2">
        <div className="flex flex-wrap items-baseline gap-2">
          <h2 className="text-sm font-semibold">Why they are warned</h2>
          <span className="text-xs text-text-muted">rules do not sum to the warned total</span>
          <details className="text-xs text-text-muted" data-testid="ews-reasons-basis">
            <summary className="cursor-pointer">Basis</summary>
            <p className="mt-1 max-w-prose">
              One {id.exposure_grain} can trip several rules of {id.ruleset}, so a {id.exposure_grain} appears under each
              rule it trips and the rows deliberately do not add to the warned population. Share of warned EAD divides by
              the warned and already-bad EAD of the rung on screen.
            </p>
          </details>
        </div>
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-xs">
            <thead className="bg-surface-sunken text-left">
              <tr>
                <th className="px-2 py-1.5">Rule</th>
                <th className="px-2 py-1.5 text-right">{ownerNoun}</th>
                <th className="px-2 py-1.5 text-right">{exposureNoun}</th>
                <th className="px-2 py-1.5 text-right">EAD (SAR)</th>
                <th className="px-2 py-1.5 text-right">Share of warned EAD</th>
                <th className="px-2 py-1.5 text-right">Weight</th>
                <th className="px-2 py-1.5" />
              </tr>
            </thead>
            <tbody>
              {feed.reasons.map((r) => {
                const total = t.warned_performing_ead_sar_mn + t.bad_ead_sar_mn;
                return (
                  <tr
                    key={r.id}
                    className={`border-t border-border ${r.reason === reason ? "bg-accent-muted" : ""}`}
                    data-testid="ews-reason-row"
                    data-rule={r.id}
                  >
                    <td className="px-2 py-1.5">
                      <span className="font-medium">{r.id}</span> {r.reason}
                      {r.limitation ? <span className="block text-warning">{r.limitation}</span> : null}
                    </td>
                    <td className="px-2 py-1.5 text-right tabular">{count(r.owners)}</td>
                    <td className="px-2 py-1.5 text-right tabular">{count(r.exposures)}</td>
                    <td className="px-2 py-1.5 text-right tabular">{sarFull(r.ead_sar_mn)}</td>
                    <td className="px-2 py-1.5 text-right tabular">{pct(total ? r.ead_sar_mn / total : null, 1)}</td>
                    <td className="px-2 py-1.5 text-right tabular">{r.weight}</td>
                    <td className="px-2 py-1.5 text-right">
                      <button
                        type="button"
                        onClick={() => onReason(r.reason === reason ? "" : r.reason)}
                        className="rounded border border-border px-2 py-0.5"
                        data-testid="ews-reason-filter"
                      >
                        {r.reason === reason ? "Clear" : "Filter"}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {showModel && (
        <ModelPanel model={model} identity={want} surface={surface} onSurface={setSurface} ownerNoun={ownerNoun} />
      )}
    </div>
  );
}

function Card({
  title,
  value,
  lines,
  colour,
  testId,
}: {
  title: string;
  value: string;
  lines: string[];
  colour?: string;
  testId: string;
}) {
  return (
    <div className="rounded-xl border border-border bg-surface p-3" data-testid={testId}>
      <div className="text-xs font-medium" style={colour ? { color: colour } : undefined}>
        {title}
      </div>
      <div className="mt-0.5 text-2xl font-semibold tabular">{value}</div>
      {lines.map((line) => (
        <div key={line} className="text-xs text-text-muted">
          {line}
        </div>
      ))}
    </div>
  );
}

function LevelTable({
  rows,
  ownerNoun,
  exposureNoun,
  onPick,
}: {
  rows: LevelRow[];
  ownerNoun: string;
  exposureNoun: string;
  onPick: (value: string | number | null) => void;
}) {
  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full text-xs">
        <thead className="bg-surface-sunken text-left">
          <tr>
            <th className="px-2 py-1.5">Value</th>
            <th className="px-2 py-1.5 text-right">{ownerNoun}</th>
            <th className="px-2 py-1.5 text-right">{exposureNoun}</th>
            <th className="px-2 py-1.5 text-right">EAD (SAR)</th>
            <th className="px-2 py-1.5 text-right">Warned {ownerNoun}</th>
            <th className="px-2 py-1.5 text-right">Warned EAD (SAR)</th>
            <th className="px-2 py-1.5 text-right">Already bad {ownerNoun}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr
              key={label(r.value)}
              className="cursor-pointer border-t border-border hover:bg-surface-sunken"
              onClick={() => onPick(r.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onPick(r.value);
                }
              }}
              tabIndex={0}
              data-testid="ews-level-row"
              data-value={label(r.value)}
            >
              <td className="px-2 py-1.5 font-medium">{label(r.value)}</td>
              <td className="px-2 py-1.5 text-right tabular">{count(r.owners)}</td>
              <td className="px-2 py-1.5 text-right tabular">{count(r.exposures)}</td>
              <td className="px-2 py-1.5 text-right tabular">{sarFull(r.ead_sar_mn)}</td>
              <td className="px-2 py-1.5 text-right tabular">{count(r.warned_owners)}</td>
              <td className="px-2 py-1.5 text-right tabular">{sarFull(r.warned_ead_sar_mn)}</td>
              <td className="px-2 py-1.5 text-right tabular">{count(r.bad_owners)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function OwnerTable({
  rows,
  fields,
  domain,
  release,
  period,
  exposureNoun,
  onOpen,
}: {
  rows: OwnerRow[];
  fields: string[];
  domain: DomainId;
  release: string;
  period: string;
  exposureNoun: string;
  onOpen: (href: string) => void;
}) {
  // Two or three descriptive fields, not all ten: the row is for choosing a
  // customer, and Borrower 360 is for reading one.
  const shown = fields.filter((f) =>
    domain === "corporate"
      ? ["borrower_name", "group_name", "rating_current"].includes(f)
      : ["customer_segment", "score_band", "region"].includes(f),
  );
  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full text-xs">
        <thead className="bg-surface-sunken text-left">
          <tr>
            <th className="px-2 py-1.5">{domain === "corporate" ? "Borrower" : "Customer"}</th>
            {shown.map((f) => (
              <th key={f} className="px-2 py-1.5">
                {f.replace(/_/g, " ")}
              </th>
            ))}
            <th className="px-2 py-1.5 text-right">{exposureNoun}</th>
            <th className="px-2 py-1.5 text-right">EAD (SAR)</th>
            <th className="px-2 py-1.5 text-right">ECL (SAR)</th>
            <th className="px-2 py-1.5 text-right">Worst stage</th>
            <th className="px-2 py-1.5 text-right">Worst DPD</th>
            <th className="px-2 py-1.5">Severity</th>
            <th className="px-2 py-1.5">Reasons</th>
            <th className="px-2 py-1.5" />
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const href = borrower360Href({
              domain,
              ownerId: row.owner_id,
              period,
              release,
              back: currentAddress(),
            });
            return (
              <tr key={row.owner_id} className="border-t border-border" data-testid="ews-owner-row" data-owner={row.owner_id}>
                <td className="px-2 py-1.5 font-medium">{row.owner_id}</td>
                {shown.map((f) => (
                  <td key={f} className="px-2 py-1.5">
                    {row[f] === null || row[f] === undefined ? "—" : String(row[f])}
                  </td>
                ))}
                <td className="px-2 py-1.5 text-right tabular">{count(row.exposures)}</td>
                <td className="px-2 py-1.5 text-right tabular">{sarFull(row.ead_sar_mn)}</td>
                <td className="px-2 py-1.5 text-right tabular">{sarFull(row.ecl_sar_mn)}</td>
                <td className="px-2 py-1.5 text-right tabular">{row.worst_stage ?? "—"}</td>
                <td className="px-2 py-1.5 text-right tabular">{row.worst_dpd_days ?? "—"}</td>
                <td className="px-2 py-1.5">
                  <span
                    className="rounded px-1.5 py-0.5 text-[11px] font-medium"
                    style={{ background: `${SEVERITY_COLORS[row.ews_band as keyof typeof SEVERITY_COLORS] ?? "#999"}22` }}
                  >
                    {row.ews_band} ({row.ews_score ?? 0})
                  </span>
                </td>
                <td className="max-w-[20rem] px-2 py-1.5 text-text-muted">{row.ews_reasons || "—"}</td>
                <td className="px-2 py-1.5 text-right">
                  <button
                    type="button"
                    onClick={() => onOpen(href)}
                    className="inline-flex items-center gap-1 rounded border border-accent px-2 py-0.5 text-accent"
                    data-testid="ews-open-360"
                    data-href={href}
                  >
                    <ExternalLink className="h-3 w-3" /> View Borrower 360
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/**
 * Model, Signals, Tree and Log -- four surfaces over ONE read.
 *
 * They describe the governed rule set that actually produced the bands on
 * this screen, and nothing else. In particular:
 *
 *   * "Tree" is an OBSERVATION of the one scoring layer that ran -- rule
 *     weights summed in SQL, cut by `ews.BANDS` -- with the score range each
 *     band actually came out at. It is not a four-layer model diagram,
 *     because no four-layer model ran;
 *   * "Log" shows the active version and states plainly that this release
 *     publishes no rule-set change log, rather than composing an approval
 *     trail that does not exist.
 */
export function ModelPanel({
  model,
  identity,
  surface,
  onSurface,
  ownerNoun,
}: {
  model: ModelMeta | null;
  identity: string;
  surface: EwsSurface;
  onSurface: (s: EwsSurface) => void;
  ownerNoun: string;
}) {
  // `identity` is domain|period: a model read for another book is stale, not
  // a model to display, so it shows as still loading rather than as current.
  // The test lives in `modelIsCurrent` so a caller cannot satisfy this guard
  // by inventing its own string -- a presentation sentence passed here read as
  // "still loading" for ever.
  if (!model || !modelIsCurrent(model, identity)) {
    return (
      <p className="flex items-center gap-2 text-xs text-text-muted">
        <Loader2 className="h-3.5 w-3.5 animate-spin" /> Reading the rule set…
      </p>
    );
  }
  const status = {
    live: { text: "Live", tone: "text-positive" },
    live_no_match: { text: "Live · matches nothing on this release", tone: "text-warning" },
    not_evaluated: { text: "Not evaluated · input not published", tone: "text-negative" },
  } as const;
  return (
    <section className="space-y-2 rounded-lg border border-border bg-surface p-3" data-testid="ews-model">
      <div className="flex flex-wrap items-baseline gap-2">
        <h2 className="text-sm font-semibold">Rule set {model.ruleset}</h2>
        <span className="text-xs text-text-muted">
          {model.rules_live} of {model.rules_total} rules live · {model.rules_evaluated} evaluable on {model.release_id}{" "}
          {model.period} ·{" "}
          {count(model.coverage.exposures)} {grainPlural(model.exposure_grain)} scored, {count(model.coverage.unscored_exposures)} unscored ·{" "}
          {model.model_calls} model calls
        </span>
      </div>
      <p className="text-xs text-text-muted">{model.basis}</p>

      <div className="flex flex-wrap gap-1.5" role="tablist" aria-label="Rule set surfaces" data-testid="ews-surfaces">
        {([
          ["model", "Model"],
          ["sources", "Sources"],
          ["signals", "Signals"],
          ["tree", "Tree"],
          ["reference", "Reference model"],
          ["log", "Log"],
        ] as const).map(([k, text]) => (
          <button
            key={k}
            type="button"
            role="tab"
            aria-selected={surface === k}
            onClick={() => onSurface(k)}
            className={`rounded-full border px-2.5 py-0.5 text-xs ${
              surface === k ? "border-accent bg-accent-muted font-medium" : "border-border"
            }`}
            data-testid={`ews-surface-${k}`}
          >
            {text}
          </button>
        ))}
      </div>

      {surface === "sources" ? (
        model.catalogue ? (
          <SourcesSurface catalogue={model.catalogue} ownerNoun={ownerNoun} />
        ) : (
          <p className="text-xs text-text-muted">This release served no signal catalogue.</p>
        )
      ) : null}
      {surface === "reference" ? (
        model.reference ? (
          <ReferenceSurface reference={model.reference} />
        ) : (
          <p className="text-xs text-text-muted">No reference model comparison is served.</p>
        )
      ) : null}
      {surface === "signals" ? <Signals model={model} ownerNoun={ownerNoun} /> : null}
      {surface === "tree" ? <Tree model={model} ownerNoun={ownerNoun} /> : null}
      {surface === "log" ? <RulesetLog model={model} /> : null}

      <div className={`overflow-x-auto ${surface === "model" ? "" : "hidden"}`}>
        <table className="w-full text-xs">
          <thead className="bg-surface-sunken text-left">
            <tr>
              <th className="px-2 py-1.5">Rule</th>
              <th className="px-2 py-1.5">Expression as applied</th>
              <th className="px-2 py-1.5">Inputs</th>
              <th className="px-2 py-1.5 text-right">Weight</th>
              <th className="px-2 py-1.5 text-right">Tripped</th>
              <th className="px-2 py-1.5">Status</th>
            </tr>
          </thead>
          <tbody>
            {model.rules.map((r) => (
              <tr key={r.id} className="border-t border-border" data-testid="ews-model-rule" data-rule={r.id} data-status={r.status}>
                <td className="px-2 py-1.5">
                  <span className="font-medium">{r.id}</span> {r.label}
                </td>
                <td className="px-2 py-1.5 font-mono text-[11px] text-text-muted">{r.expression}</td>
                <td className="px-2 py-1.5 text-text-muted">
                  {r.inputs.join(", ")}
                  {r.missing_columns.length ? (
                    <span className="block text-negative">not published: {r.missing_columns.join(", ")}</span>
                  ) : null}
                </td>
                <td className="px-2 py-1.5 text-right tabular">{r.weight}</td>
                <td className="px-2 py-1.5 text-right tabular">
                  {r.exposures_tripped === null ? "—" : count(r.exposures_tripped)}
                </td>
                <td className={`px-2 py-1.5 ${status[r.status].tone}`}>
                  {status[r.status].text}
                  {r.limitation ? <span className="block text-warning">{r.limitation}</span> : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className={`text-xs text-text-muted ${surface === "model" ? "" : "hidden"}`}>
        Severity bands:{" "}
        {model.bands.map((b) => `${b.band} ≥ ${b.min_score}`).join(" · ")}. A rule that is not evaluated contributes nothing
        to the score and is NOT counted as zero.
      </div>
    </section>
  );
}

/** Each rule as a SIGNAL: its inputs, whether the release carries them, and who it caught. */
function Signals({ model, ownerNoun }: { model: ModelMeta; ownerNoun: string }) {
  return (
    <div className="space-y-2" data-testid="ews-signals">
      <p className="text-xs text-text-muted">
        One signal per rule, as evaluated on {model.release_id} {model.period}. A signal whose input this release does not
        publish is marked as such and contributes nothing — it is never shown as a zero catch.
      </p>
      <div className="grid gap-2 md:grid-cols-2">
        {model.rules.map((r) => (
          <div
            key={r.id}
            className="rounded-lg border border-border p-2"
            data-testid="ews-signal"
            data-rule={r.id}
            data-status={r.status}
          >
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-xs font-medium">
                {r.id} · {r.label}
              </span>
              <span className="text-[11px] tabular text-text-muted">weight {r.weight}</span>
            </div>
            <div className="mt-0.5 text-[11px] text-text-muted">
              Inputs: {r.inputs.join(", ") || "none declared"}
            </div>
            {r.missing_columns.length ? (
              <div className="text-[11px] text-negative">
                Not evaluable here — {model.release_id} does not publish {r.missing_columns.join(", ")}.
              </div>
            ) : (
              <div className="text-[11px]">
                Caught {r.owners_tripped === null ? "—" : count(r.owners_tripped)} {ownerNoun} ·{" "}
                {r.exposures_tripped === null ? "—" : count(r.exposures_tripped)} {grainPlural(model.exposure_grain)}
                {r.status === "live_no_match" ? (
                  <span className="block text-warning">
                    Live but matches nothing on this release — the governed literal and the published category differ. The
                    rule is not edited to fit; this is reported for the model owner.
                  </span>
                ) : null}
              </div>
            )}
            {r.limitation ? <div className="text-[11px] text-warning">{r.limitation}</div> : null}
          </div>
        ))}
      </div>
    </div>
  );
}

/** How a band was reached: the one layer that ran, and what it observed. */
function Tree({ model, ownerNoun }: { model: ModelMeta; ownerNoun: string }) {
  const obs = model.score_observations;
  if (!obs) {
    return (
      <p className="text-xs text-text-muted" data-testid="ews-tree">
        The scoring observation is not published by this read.
      </p>
    );
  }
  return (
    <div className="space-y-2" data-testid="ews-tree" data-layers={obs.layers}>
      <ol className="space-y-1 text-xs">
        <li className="rounded-lg border border-border p-2">
          <span className="font-medium">1. Each live rule is evaluated in SQL</span> on the published{" "}
          {model.exposure_grain} row — {model.rules_live} of {model.rules_total} rules are live here,{" "}
          {model.rules_total - model.rules_evaluated} cannot be evaluated on {model.release_id}.
        </li>
        <li className="rounded-lg border border-border p-2">
          <span className="font-medium">2. The weights of the rules that are true are summed</span> into{" "}
          <code className="font-mono">ews_score</code>. That is the whole computation: {obs.layers} layer,{" "}
          {obs.model_calls} model calls.
        </li>
        <li className="rounded-lg border border-border p-2">
          <span className="font-medium">3. The sum is cut into bands</span> by the rule set&apos;s own thresholds. The
          observed score range in each band below is what actually came out, not an assumed range.
        </li>
      </ol>
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full text-xs">
          <thead className="bg-surface-sunken text-left">
            <tr>
              <th className="px-2 py-1.5">Band</th>
              <th className="px-2 py-1.5 text-right">Score ≥</th>
              <th className="px-2 py-1.5 text-right">Observed score (min–max)</th>
              <th className="px-2 py-1.5 text-right">Mean</th>
              <th className="px-2 py-1.5 text-right">{grainPlural(model.exposure_grain)}</th>
              <th className="px-2 py-1.5 text-right">{ownerNoun}</th>
              <th className="px-2 py-1.5 text-right">EAD (SAR)</th>
            </tr>
          </thead>
          <tbody>
            {obs.bands.map((b) => (
              <tr key={b.band} className="border-t border-border" data-testid="ews-tree-band" data-band={b.band}>
                <td className="px-2 py-1.5 font-medium">{b.band}</td>
                <td className="px-2 py-1.5 text-right tabular">
                  {b.min_score_required === null ? "not a rule-set band" : b.min_score_required}
                </td>
                <td className="px-2 py-1.5 text-right tabular">
                  {b.observed_min_score === null ? "—" : `${b.observed_min_score}–${b.observed_max_score}`}
                </td>
                <td className="px-2 py-1.5 text-right tabular">
                  {b.observed_mean_score === null ? "—" : b.observed_mean_score.toFixed(2)}
                </td>
                <td className="px-2 py-1.5 text-right tabular">{count(b.exposures)}</td>
                <td className="px-2 py-1.5 text-right tabular">{count(b.owners)}</td>
                <td className="px-2 py-1.5 text-right tabular">{sarFull(b.ead_sar_mn)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-[11px] text-text-muted">{obs.how}</p>
    </div>
  );
}

/** The rule set's version history, or the honest absence of one. */
function RulesetLog({ model }: { model: ModelMeta }) {
  const log = model.log;
  if (!log) {
    return (
      <p className="text-xs text-text-muted" data-testid="ews-log">
        The rule-set log is not published by this read.
      </p>
    );
  }
  return (
    <div className="space-y-2" data-testid="ews-log" data-history-available={log.history_available}>
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full text-xs">
          <thead className="bg-surface-sunken text-left">
            <tr>
              <th className="px-2 py-1.5">Version</th>
              <th className="px-2 py-1.5">Status</th>
              <th className="px-2 py-1.5">Applied to</th>
              <th className="px-2 py-1.5">Source</th>
            </tr>
          </thead>
          <tbody>
            {log.entries.map((e) => (
              <tr key={e.version} className="border-t border-border" data-testid="ews-log-entry" data-version={e.version}>
                <td className="px-2 py-1.5 font-medium">{e.version}</td>
                <td className="px-2 py-1.5">{e.status}</td>
                <td className="px-2 py-1.5 text-text-muted">
                  {e.applied_to_periods.length
                    ? `${e.applied_to_periods.length} periods · ${e.applied_to_periods[0]} → ${e.applied_to_periods[e.applied_to_periods.length - 1]}`
                    : "not applied to this release (recorded)"}
                </td>
                <td className="px-2 py-1.5 font-mono text-[11px] text-text-muted">{e.source}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {log.disclosure ? (
        <p
          className="rounded-md border border-warning bg-warning-muted px-2 py-1.5 text-[11px] text-warning"
          data-testid="ews-log-disclosure"
        >
          {log.disclosure}
        </p>
      ) : null}
      <p className="text-[11px] text-text-muted">
        Bound to {log.release_id} · fingerprint {log.fingerprint.slice(0, 12)} · read at {log.period}.
      </p>
    </div>
  );
}


/* ------------------------------------------------------------------------- */
/* Period movement, drawn from the series it is computed from.               */
/* ------------------------------------------------------------------------- */

/**
 * A sparkline over a series that may have holes.
 *
 * A period a value is not in is ABSENT from the series, not zero, so the line
 * is drawn over the points that exist and the caption says how many periods
 * those are. Nothing is interpolated into a gap.
 */
function Spark({ points, colour, title }: { points: number[]; colour: string; title: string }) {
  if (points.length < 2) return null;
  const lo = Math.min(...points);
  const hi = Math.max(...points);
  const span = hi - lo || 1;
  const w = 72;
  const h = 20;
  const d = points
    .map((v, i) => `${(i / (points.length - 1)) * w},${h - ((v - lo) / span) * (h - 2) - 1}`)
    .join(" ");
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} role="img" aria-label={title} data-testid="ews-spark" className="shrink-0">
      <title>{title}</title>
      <polyline points={d} fill="none" stroke={colour} strokeWidth="1.5" />
    </svg>
  );
}

/** A move between two periods, in the reader's direction language. */
function Move({ now, before, unit, testId }: { now: number; before: number | null; unit: string; testId?: string }) {
  if (before === null || before === undefined) {
    return (
      <span className="text-[11px] text-text-muted" data-testid={testId}>
        no earlier period published
      </span>
    );
  }
  const d = now - before;
  const tone = d > 0 ? "text-negative" : d < 0 ? "text-positive" : "text-text-muted";
  const sign = d > 0 ? "+" : "";
  const shown = unit === "SAR" ? sar(Math.abs(d)) : count(Math.abs(d));
  return (
    <span className={`text-[11px] tabular ${tone}`} data-testid={testId} data-change={d}>
      {d === 0 ? "unchanged" : `${sign}${d > 0 ? "" : "−"}${shown} vs last period`}
    </span>
  );
}

function PortfolioHistory({
  history,
  ownerNoun,
  period,
}: {
  history: OverviewPoint[];
  ownerNoun: string;
  period: string;
}) {
  const now = history[history.length - 1];
  const before = history.length > 1 ? history[history.length - 2] : null;
  const rows: { label: string; value: string; series: number[]; now: number; before: number | null; unit: string; colour: string }[] = [
    {
      label: `Still performing, warned ${ownerNoun}`,
      value: count(now.warned_performing_owners),
      series: history.map((h) => h.warned_performing_owners),
      now: now.warned_performing_owners,
      before: before ? before.warned_performing_owners : null,
      unit: "n",
      colour: SEVERITY_COLORS.high,
    },
    {
      label: `Already bad ${ownerNoun}`,
      value: count(now.bad_owners),
      series: history.map((h) => h.bad_owners),
      now: now.bad_owners,
      before: before ? before.bad_owners : null,
      unit: "n",
      colour: SEVERITY_COLORS.critical,
    },
    {
      label: "Warned EAD",
      value: sar(now.warned_ead_sar_mn),
      series: history.map((h) => h.warned_ead_sar_mn),
      now: now.warned_ead_sar_mn,
      before: before ? before.warned_ead_sar_mn : null,
      unit: "SAR",
      colour: SEVERITY_COLORS.high,
    },
    {
      label: "ECL",
      value: sar(now.ecl_sar_mn),
      series: history.map((h) => h.ecl_sar_mn),
      now: now.ecl_sar_mn,
      before: before ? before.ecl_sar_mn : null,
      unit: "SAR",
      colour: SEVERITY_COLORS.moderate,
    },
  ];
  return (
    <section className="rounded-xl border border-border bg-surface p-3" data-testid="ews-history">
      <div className="flex flex-wrap items-baseline gap-2">
        <h2 className="text-sm font-semibold">How this changed</h2>
        <span className="text-xs text-text-muted">
          {history[0].period} → {period} · {history.length} periods
        </span>
        <details className="text-xs text-text-muted" data-testid="ews-history-basis">
          <summary className="cursor-pointer">Basis</summary>
          <p className="mt-1 max-w-prose">
            Every period is read the same way from the same canonical adapter, so the movement is a movement in the book
            and not in the method. A period this release does not carry is absent, not zero.
          </p>
        </details>
      </div>
      <div className="mt-2 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {rows.map((r) => (
          <div key={r.label} className="flex items-center gap-2" data-testid="ews-history-metric" data-metric={r.label}>
            <div className="min-w-0 flex-1">
              <div className="truncate text-[11px] text-text-muted">{r.label}</div>
              <div className="text-lg font-semibold tabular">{r.value}</div>
              <Move now={r.now} before={r.before} unit={r.unit} />
            </div>
            <Spark points={r.series} colour={r.colour} title={`${r.label}, ${history.length} periods`} />
          </div>
        ))}
      </div>
    </section>
  );
}

/**
 * One ladder value as a CARD.
 *
 * Everything on it is read from the same canonical adapter at the same period
 * as the card above it: both grains kept apart, already-bad kept apart from
 * still-performing-warned, the move since the previous period with the series
 * it was computed from, and the rules that are actually driving the warned
 * population with the EAD behind each. Nothing here is a placeholder: a value
 * with no earlier period says so, and a value with no tripped rule says so.
 */
function LevelCard({
  row,
  series,
  reasons,
  ownerNoun,
  exposureNoun,
  period,
  onPick,
}: {
  row: LevelRow;
  series: LevelPoint[];
  reasons: LevelReason[];
  ownerNoun: string;
  exposureNoun: string;
  period: string;
  onPick: () => void;
}) {
  const prior = series.length > 1 ? series[series.length - 2] : null;
  const warnedShare = row.ead_sar_mn ? row.warned_performing_ead_sar_mn / row.ead_sar_mn : null;
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onPick}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onPick();
        }
      }}
      className="cursor-pointer rounded-xl border border-border bg-surface p-3 text-left hover:border-accent"
      data-testid="ews-level-card"
      data-value={label(row.value)}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold">{label(row.value)}</div>
          <div className="text-[11px] text-text-muted">
            {count(row.owners)} {ownerNoun} · {count(row.exposures)} {exposureNoun}
          </div>
        </div>
        <Spark
          points={series.map((s) => s.warned_ead_sar_mn)}
          colour={SEVERITY_COLORS.high}
          title={`Warned EAD, ${series.length} periods`}
        />
      </div>

      <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
        <div>
          <dt className="text-[11px] text-text-muted">EAD</dt>
          <dd className="tabular" title={`Exactly ${sarFull(row.ead_sar_mn)}`}>{sar(row.ead_sar_mn)}</dd>
        </div>
        <div>
          <dt className="text-[11px] text-text-muted">ECL</dt>
          <dd className="tabular" title={`Exactly ${sarFull(row.ecl_sar_mn)}`}>{sar(row.ecl_sar_mn)}</dd>
        </div>
        <div>
          <dt className="text-[11px]" style={{ color: SEVERITY_COLORS.critical }}>
            Already bad
          </dt>
          <dd className="tabular" data-testid="ews-card-bad-owners" title={`EAD exactly ${sarFull(row.bad_ead_sar_mn)}`}>
            {count(row.bad_owners)} {ownerNoun} · {sar(row.bad_ead_sar_mn)}
          </dd>
        </div>
        <div>
          <dt className="text-[11px]" style={{ color: SEVERITY_COLORS.high }}>
            Still performing, warned
          </dt>
          <dd className="tabular" data-testid="ews-card-warned-owners" title={`EAD exactly ${sarFull(row.warned_performing_ead_sar_mn)}`}>
            {count(row.warned_performing_owners)} {ownerNoun} · {sar(row.warned_performing_ead_sar_mn)}
          </dd>
        </div>
      </dl>

      <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-text-muted">
        <span>{pct(warnedShare, 1)} of EAD warned and still performing</span>
        <span>· {count(row.critical_owners)} critical</span>
      </div>

      <div className="mt-1" data-testid="ews-card-change" data-period={period}>
        <Move
          now={row.warned_owners}
          before={prior ? prior.warned_owners : null}
          unit="n"
          testId="ews-card-change-warned"
        />
      </div>

      <div className="mt-2 border-t border-border pt-1.5">
        <div className="text-[11px] font-medium text-text-secondary">Top reasons here</div>
        {reasons.length === 0 ? (
          <p className="text-[11px] text-text-muted" data-testid="ews-card-no-reason">
            No rule in {label(row.value)} tripped on this release at {period}.
          </p>
        ) : (
          <ul className="space-y-0.5" data-testid="ews-card-reasons">
            {reasons.map((r) => (
              <li key={r.id} className="flex items-baseline justify-between gap-2 text-[11px]" data-rule={r.id}>
                <span className="truncate">
                  <span className="font-medium">{r.id}</span> {r.reason}
                </span>
                <span className="shrink-0 tabular text-text-muted">
                  {count(r.owners)} · {sar(r.ead_sar_mn)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
