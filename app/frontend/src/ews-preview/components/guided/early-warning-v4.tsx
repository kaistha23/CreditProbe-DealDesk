"use client";

/**
 * Early Warning in the V4 runtime: the governed EWS rule set (gw-ews-1.0.0)
 * over the book the Cockpit is serving. Every card can freeze its EXACT
 * population as a governed cohort, export it, or open a Cockpit investigation
 * on it -- the same cohort id then travels to What-If and Lenses.
 *
 * A warning reason is a cross-filter (§27): clicking a rule in "Why
 * exposures are warned" -- or pressing Enter on its data row -- narrows the
 * bands, the segment cards, the underlying grid and every cohort /
 * investigation / What-If handoff to exposures tripping that rule. The server
 * applies it; the reasons chart itself stays whole so any rule can be chosen.
 */

import * as React from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Download, Loader2, Save, Search, SlidersHorizontal } from "lucide-react";

import { DomainSwitchPlain } from "@/ews-preview/components/guided/domain-toggle";
import { EwsDrill } from "@/ews-preview/components/guided/ews-drill";
import { ChartCard } from "@/ews-preview/components/viz/chart-card";
import { DataGrid } from "@/ews-preview/components/workspace/data-grid";
import { trend } from "@/ews-preview/lib/viz/figures";
import { count, sar, sarFull } from "@/ews-preview/lib/viz/format";
import { SEVERITY_COLORS, SEMANTIC } from "@/ews-preview/lib/viz/palette";
import { workspaceUrl, wsGet, wsSend } from "@/ews-preview/lib/workspace/client";
import type { DomainId, Filter } from "@/ews-preview/lib/workspace/objects";
import { fullMoneyCol } from "@/ews-preview/lib/viz/format";
import { urlWith, withBack } from "@/ews-preview/lib/workspace/nav";
import { modelDetailHref } from "@/ews-preview/lib/workspace/model-identity";

interface EwFeed {
  domain_id: DomainId;
  release_id: string;
  period: string;
  periods: string[];
  ruleset: string;
  rules: { id: string; label: string; weight: number; limitation?: string }[];
  segment_dimension: string;
  bands: { value: string; n: number; ead_sar_mn: number; ecl_sar_mn: number }[];
  by_segment: { segment: string; bands: { value: string; n: number; ead_sar_mn: number; ecl_sar_mn: number }[] }[];
  reasons: { reason: string; n: number; ead: number }[];
  top: Record<string, string | number | null>[];
  severe_total: number;
  severe_ead_trend: { period: string; value: number | null }[];
  reason: string;
  /** The delinquency band filtering the page, "" when none is. */
  dpd: string;
  dpd_available: boolean;
  dpd_overlap: string;
  dpd_bands: {
    key: string; label: string; low: number; high: number;
    bands: { value: string; n: number; ead_sar_mn: number; ecl_sar_mn: number }[];
    n: number; ead_sar_mn: number;
    severe_n: number; severe_ead_sar_mn: number;
  }[];
  filters: Filter[];
}

const BANDS = ["critical", "high", "moderate", "low"] as const;

/** The context a queued receiver will be handed, as the domain API states it. */
interface HandoffContext {
  domain_id: string;
  release_id: string;
  period: string;
  exposure_id_field: string;
  owner_id_field: string;
  exposure_grain: string;
  owner_grain: string;
  filter: { segment: string; bands: string[]; reason: string; dpd: string; segment_dimension: string };
  signals_live: string[];
  signals_not_live: string[];
  cohort_id: string;
  cohort_digest: string;
  counts: { exposures: number; owners: number };
  receivers: Record<string, { module: string; status: string }>;
  availability: string;
}

const RECEIVER_LABEL: Record<string, string> = {
  investigation: "Cockpit investigation",
  what_if: "What-If",
  borrower_360: "Borrower 360",
};

export function EarlyWarningV4() {
  const router = useRouter();
  // The book and the rule filter live in the address, so Back from any
  // handoff (What-If, an investigation) restores exactly this view.
  const params = useSearchParams();
  const domain: DomainId = params.get("domain") === "corporate" ? "corporate" : "retail";
  const reason = params.get("reason") ?? "";
  // The delinquency band is in the address beside the rule, for the same
  // reason: the drill, the cards, the grid and every handoff read one
  // population, and a shared link opens that population rather than the book.
  const dpd = params.get("dpd") ?? "";
  // Which severity bands the grid and every handoff below are about. Empty is
  // the page default, high and critical together; clicking one severity card
  // narrows to that band alone. It is a CLIENT narrowing of a population the
  // server already supports (`/early-warning/cohort` takes the band list), so
  // no rule, threshold or score changes -- only which of them is on screen.
  // Only a published severity is honoured. An unknown `?band=` is NOT passed
  // on: the grid would lock to a value the book has no rows for while the
  // cohort endpoint fell back to high/critical, so the two halves of one
  // screen would be two populations. It is reported instead.
  const rawBand = params.get("band") ?? "";
  const band = (BANDS as readonly string[]).includes(rawBand) ? rawBand : "";
  const badBand = rawBand && !band ? rawBand : "";
  // The period is part of the address so the drill, the cards, the charts and
  // the grid are all one period, and so a shared link opens the same one.
  const period = params.get("period") ?? "";
  const [loaded, setLoaded] = React.useState<{ key: string; feed: EwFeed | null }>({ key: "", feed: null });
  const key = `${domain}|${reason}|${period}|${dpd}`;
  const feed = loaded.key === key ? loaded.feed : null;
  const bandsInUse = React.useMemo(() => (band ? [band] : ["critical", "high"]), [band]);
  const bandsLabel = band || "high/critical";
  const gridLocked = React.useMemo<Filter[]>(
    () => [{ column: "ews_band", op: "in", values: bandsInUse }, ...(feed?.filters ?? [])],
    [feed, bandsInUse],
  );
  const [error, setError] = React.useState("");
  const [note, setNote] = React.useState("");
  const [pending, setPending] = React.useState<{ target: string; cohort: string; context: HandoffContext } | null>(null);
  const [busy, setBusy] = React.useState(false);

  React.useEffect(() => {
    let live = true;
    wsGet<EwFeed>(
      `/early-warning?domain=${domain}${reason ? `&reason=${encodeURIComponent(reason)}` : ""}${
        period ? `&period=${encodeURIComponent(period)}` : ""
      }${dpd ? `&dpd=${encodeURIComponent(dpd)}` : ""}`,
    )
      .then((f) => live && setLoaded({ key, feed: f }))
      .catch((e: unknown) => live && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      live = false;
    };
  }, [domain, reason, period, dpd, key]);

  // Switching book clears the rule filter AND the period: a Retail rule is
  // not a Corporate rule and a month is not a quarter, so carrying either
  // across would ask the new book for something it does not have.
  function changeDomain(next: DomainId) {
    router.replace(urlWith({ domain: next === "retail" ? null : next, reason: null, period: null, dpd: null, band: null }), { scroll: false });
  }
  const changePeriod = (p: string) => router.replace(urlWith({ period: p }), { scroll: false });

  // A rule filter is a drill: it adds a history entry, so browser Back undoes it.
  const toggleReason = (r: string) => router.push(urlWith({ reason: reason === r ? null : r }), { scroll: false });
  const clearReason = () => router.push(urlWith({ reason: null }), { scroll: false });
  // A delinquency band is a drill too: it adds a history entry, so browser
  // Back undoes it and lands on the unfiltered page rather than the book.
  const toggleDpd = (k: string) => router.push(urlWith({ dpd: dpd === k ? null : k }), { scroll: false });
  const toggleBand = (b: string) => router.push(urlWith({ band: band === b ? null : b }), { scroll: false });

  // The cohort frozen for one population (book, segment, bands, rule) is
  // reused: Save, Export and What-If on the same population never mint a
  // second governed cohort, and a double-click is a no-op (single flight).
  const frozen = React.useRef(new Map<string, { object_id: string; body: { counts: { entities: number } } }>());
  const inFlight = React.useRef(false);

  async function guarded(fn: () => Promise<void>) {
    if (inFlight.current) return;
    inFlight.current = true;
    try {
      await fn();
    } catch (e) {
      setNote(`Not done: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      inFlight.current = false;
    }
  }

  async function saveCohort(segment = "", bands: string[] = bandsInUse) {
    const key = JSON.stringify([domain, segment, [...bands].sort(), reason, dpd]);
    const known = frozen.current.get(key);
    if (known) {
      setNote(`This population is already saved as cohort ${known.object_id} (${count(known.body.counts.entities)} exposures).`);
      return known;
    }
    const c = await wsSend<{ object_id: string; body: { counts: { entities: number } } }>("/early-warning/cohort", { domain, segment, bands, reason, dpd });
    frozen.current.set(key, c);
    setNote(`Saved ${count(c.body.counts.entities)} exposures as cohort ${c.object_id}.`);
    return c;
  }

  async function exportCohort(segment = "") {
    const c = await saveCohort(segment);
    const response = await fetch(workspaceUrl(`/cohorts/${c.object_id}/export`), { credentials: "include" });
    if (!response.ok) throw new Error(`export failed (${response.status})`);
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${c.object_id}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  /* THE QUEUED RECEIVERS. Borrower 360, What-If and the Cockpit
     investigation thread are not restored yet. These buttons do the half that
     exists -- they freeze this exact population and read back the context the
     receiving screen will be handed -- and then say so, instead of opening a
     route that would 404 or pretending a scenario ran. Nothing here reads or
     writes the Cockpit. */
  async function handoff(target: "investigation" | "what_if" | "borrower_360", segment = "") {
    setBusy(true);
    try {
      const out = await wsSend<{ cohort: { object_id: string; counts: { entities: number; owners: number } }; context: HandoffContext }>(
        "/early-warning/handoff",
        { domain, segment, bands: bandsInUse, reason, dpd, period: feed?.period ?? period, target },
      );
      setPending({ target, context: out.context, cohort: out.cohort.object_id });
      setNote("");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }
  const investigate = (segment = "") => handoff("investigation", segment);
  const whatIf = (segment = "") => handoff("what_if", segment);

  if (error) return <p role="alert" className="text-sm text-negative">{error}</p>;
  const severeTrend = feed ? trend([{ name: "High/critical EWS EAD", points: feed.severe_ead_trend, unit: "SAR_mn", color: SEMANTIC.increase }]) : null;
  return (
    <div className="space-y-5" data-testid="early-warning-v4">
      <header className="flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold text-text-primary">Early Warning</h1>
        <DomainSwitchPlain value={domain} onChange={changeDomain} />
        {feed && (
          <span className="text-xs text-text-muted">
            {feed.release_id} · {feed.period} · rule set {feed.ruleset} · no model call
          </span>
        )}
        {/* The model on its own page -- the PREVIEW's page, not the Cockpit's
            early-warning route, which is served by another app against another
            backend. It carries THIS book and THIS period, so the rule set read
            there is the one applied here, and `withBack` carries this exact
            address -- rule, severity and past-due filter included -- so
            returning lands on the view it was opened from. */}
        <Link
          href={withBack(modelDetailHref(domain, feed?.period ?? period))}
          className="ml-auto inline-flex items-center gap-1 rounded-md border border-border px-2.5 py-1 text-xs text-text-secondary hover:border-accent"
          data-testid="ew-view-model"
        >
          <SlidersHorizontal className="h-3.5 w-3.5" /> View model
        </Link>
      </header>
      {!feed ? (
        <p className="flex items-center gap-2 text-sm text-text-muted">
          <Loader2 className="h-4 w-4 animate-spin" /> Applying the early-warning rules…
        </p>
      ) : (
        <>
          {dpd && (
            <p className="flex flex-wrap items-center gap-2 rounded-md border border-accent bg-accent-muted px-3 py-2 text-xs" data-testid="ew-dpd-filter" data-dpd={dpd}>
              Showing <span className="font-semibold">{feed.dpd_bands.find((b) => b.key === dpd)?.label ?? dpd}</span> —
              bands, segments, the drill, the grid and every Save / Investigate / What-If below use this filter.
              <button type="button" onClick={() => toggleDpd(dpd)} className="text-accent underline" data-testid="ew-dpd-clear">
                Clear
              </button>
            </p>
          )}
          {badBand && (
            <p role="alert" className="rounded-md border border-warning bg-warning-muted px-3 py-2 text-xs" data-testid="ew-band-refused" data-band={badBand}>
              <span className="font-semibold">{badBand}</span> is not a published warning severity, so it was not applied.
              The page is showing {bandsLabel}. The severities are {BANDS.join(", ")}.
            </p>
          )}
          {band && (
            <p className="flex flex-wrap items-center gap-2 rounded-md border border-accent bg-accent-muted px-3 py-2 text-xs" data-testid="ew-band-filter" data-band={band}>
              Showing <span className="font-semibold">{band}</span> severity only — the drill, the segment cards, the grid and
              every Save / Investigate / Export / What-If below use this filter.
              <button type="button" onClick={() => toggleBand(band)} className="text-accent underline" data-testid="ew-band-filter-clear">
                Clear
              </button>
            </p>
          )}
          {reason && (
            <p className="flex flex-wrap items-center gap-2 rounded-md border border-accent bg-accent-muted px-3 py-2 text-xs" data-testid="ew-reason-filter" data-reason={reason}>
              Showing exposures that trip <span className="font-semibold">{reason}</span> — bands, segments, the grid and every
              Save / Investigate / What-If below use this filter.
              <button type="button" onClick={clearReason} className="text-accent underline" data-testid="ew-reason-clear">
                Clear
              </button>
            </p>
          )}
          <EwsDrill
            domain={domain}
            period={feed.period}
            reason={reason}
            dpd={dpd}
            bands={bandsInUse}
            onPeriod={changePeriod}
            onReason={(r) => router.push(urlWith({ reason: r || null }), { scroll: false })}
          />
          {feed.dpd_available && feed.dpd_bands.length ? (
            <section data-testid="ew-dpd-section">
              <h2 className="mb-1 text-sm font-semibold">
                Past due
                {/* WHAT THE NUMBERS ON THESE CARDS COUNT. The same grain the
                    severity cards state: one row per exposure, so a reader
                    cannot take 221 past-due accounts for 221 customers. */}
                <span className="ml-2 font-normal text-text-muted">
                  per {domain === "corporate" ? "facility" : "account"}, not per customer · click a band to filter the page to it
                </span>
              </h2>
              {/* The bands OVERLAP: the server says so and so does the
                  screen, because a reader who added the three cards up would
                  be wrong and nothing would have told them. */}
              <p className="mb-2 text-xs text-text-muted" data-testid="ew-dpd-overlap">{feed.dpd_overlap}</p>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {feed.dpd_bands.map((band) => {
                  const active = dpd === band.key;
                  return (
                    <button
                      key={band.key}
                      type="button"
                      onClick={() => toggleDpd(band.key)}
                      aria-pressed={active}
                      className={`rounded-xl border p-3 text-left ${active ? "border-accent bg-accent/10" : "border-border bg-surface hover:border-accent"}`}
                      data-testid={`ew-dpd-${band.key}`}
                      data-dpd={band.key}
                    >
                      <div className="flex items-baseline justify-between gap-2">
                        <span className="text-xs font-semibold uppercase text-text-secondary">{band.label}</span>
                        <span className="text-[10px] uppercase tracking-wide text-text-muted">{active ? "filtering" : "filter"}</span>
                      </div>
                      <div className="mt-1 text-lg font-semibold tabular" style={{ color: SEVERITY_COLORS.high }}>
                        {count(band.severe_n)}
                      </div>
                      <div className="text-xs text-text-muted" title={`High/critical EAD exactly ${sarFull(band.severe_ead_sar_mn)}`}>
                        high/critical of {count(band.n)} · EAD {sar(band.severe_ead_sar_mn)}
                      </div>
                      {/* Severity inside the band, in the one order the rest
                          of the page uses. The split is the server's. */}
                      <div className="mt-2 flex h-2 overflow-hidden rounded-full bg-surface-sunken">
                        {BANDS.map((severity) => {
                          const row = band.bands.find((b) => b.value === severity);
                          const total = band.n || 1;
                          return (
                            <div
                              key={severity}
                              style={{ width: `${((row?.n ?? 0) / total) * 100}%`, background: SEVERITY_COLORS[severity] }}
                              title={`${severity}: ${count(row?.n ?? 0)}`}
                            />
                          );
                        })}
                      </div>
                      <div className="mt-1 text-[11px] text-text-muted" title={`Band EAD exactly ${sarFull(band.ead_sar_mn)}`}>
                        Band EAD {sar(band.ead_sar_mn)}
                      </div>
                    </button>
                  );
                })}
              </div>
            </section>
          ) : null}
          <div className="flex flex-wrap items-baseline gap-2 pt-2">
            <h2 className="text-sm font-semibold">Severity</h2>
            <span className="text-xs text-text-muted">
              per {domain === "corporate" ? "facility" : "account"} · click a band to focus the grid and handoffs
            </span>
            {band && (
              <button type="button" onClick={() => toggleBand(band)} className="text-xs text-accent underline" data-testid="ew-band-clear">
                Clear focus ({band})
              </button>
            )}
          </div>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {BANDS.map((severity) => {
              const row = feed.bands.find((b) => b.value === severity);
              const on = band === severity;
              return (
                <button
                  key={severity}
                  type="button"
                  onClick={() => toggleBand(severity)}
                  aria-pressed={on}
                  className={`rounded-xl border p-3 text-left transition-colors ${on ? "border-accent bg-accent/10" : "border-border bg-surface hover:border-accent"}`}
                  data-testid={`ew-band-${severity}`}
                  data-band={severity}
                  data-active={on}
                >
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="text-xs font-semibold uppercase" style={{ color: SEVERITY_COLORS[severity] }}>
                      {severity}
                    </span>
                    <span className="text-[10px] uppercase tracking-wide text-text-muted">{on ? "focused" : "focus"}</span>
                  </div>
                  <div className="mt-1 text-lg font-semibold tabular">{count(row?.n ?? 0)}</div>
                  <div className="text-xs text-text-muted" title={`EAD ${sarFull(row?.ead_sar_mn ?? 0)} · ECL ${sarFull(row?.ecl_sar_mn ?? 0)}`}>
                    EAD {sar(row?.ead_sar_mn ?? 0)} · ECL {sar(row?.ecl_sar_mn ?? 0)}
                  </div>
                </button>
              );
            })}
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="button" disabled={busy} onClick={() => void investigate()} className="inline-flex items-center gap-1 rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-accent-contrast" data-testid="ew-investigate">
              <Search className="h-4 w-4" /> Investigate {bandsLabel}{reason ? " (this rule)" : ""} in Cockpit
            </button>
            <button type="button" onClick={() => void guarded(async () => void (await saveCohort()))} className="inline-flex items-center gap-1 rounded-md border border-border px-3 py-1.5 text-sm" data-testid="ew-save-cohort">
              <Save className="h-4 w-4" /> Save {bandsLabel} cohort
            </button>
            <button type="button" onClick={() => void guarded(() => exportCohort())} className="inline-flex items-center gap-1 rounded-md border border-border px-3 py-1.5 text-sm" data-testid="ew-export">
              <Download className="h-4 w-4" /> Export cohort
            </button>
            <button type="button" onClick={() => void guarded(() => whatIf())} className="inline-flex items-center gap-1 rounded-md border border-border px-3 py-1.5 text-sm" data-testid="ew-whatif">
              Run What-If on this cohort
            </button>
            {note && <span className="self-center text-xs text-positive" data-testid="ew-note">{note}</span>}
          </div>
          {pending && (
            <section className="rounded-lg border border-warning bg-warning-muted p-3 text-xs" data-testid="ew-handoff-pending" data-target={pending.target}>
              <h2 className="text-sm font-semibold">
                {RECEIVER_LABEL[pending.target] ?? pending.target} is not restored yet
              </h2>
              <p className="mt-1">This population is frozen and ready to hand over. {pending.context.availability}</p>
              <dl className="mt-2 grid gap-x-6 gap-y-1 sm:grid-cols-2">
                <div className="flex gap-2"><dt className="text-text-muted">Population</dt>
                  <dd className="tabular">{count(pending.context.counts.exposures)} {pending.context.exposure_grain}s · {count(pending.context.counts.owners)} {pending.context.owner_grain}s</dd></div>
                <div className="flex gap-2"><dt className="text-text-muted">Period</dt><dd>{pending.context.period}</dd></div>
                <div className="flex gap-2"><dt className="text-text-muted">Severity</dt><dd>{pending.context.filter.bands.join(", ")}</dd></div>
                <div className="flex gap-2"><dt className="text-text-muted">Rule filter</dt><dd>{pending.context.filter.reason || "none"}</dd></div>
                <div className="flex gap-2"><dt className="text-text-muted">Past due</dt><dd>{pending.context.filter.dpd || "none"}</dd></div>
                <div className="flex gap-2"><dt className="text-text-muted">{pending.context.filter.segment_dimension}</dt><dd>{pending.context.filter.segment || "all"}</dd></div>
              </dl>
              <button type="button" onClick={() => setPending(null)} className="mt-2 text-accent underline" data-testid="ew-handoff-dismiss">Close</button>
            </section>
          )}
          <div className="grid gap-4 lg:grid-cols-2">
            {severeTrend && (
              <ChartCard
                title="High/critical EWS EAD over time"
                subtitle="Metric M063 · governed rule set"
                data={severeTrend.data}
                layout={severeTrend.layout}
                testId="ew-trend"
                table={{ columns: [{ key: "period", label: "Period" }, fullMoneyCol("value", "EAD", feed.severe_ead_trend as unknown as Record<string, unknown>[])], rows: feed.severe_ead_trend as unknown as Record<string, unknown>[] }}
              />
            )}
            <ChartCard
              title="Why exposures are warned"
              // The rule filter is this chart's own, so it is not applied
              // here; the PAST-DUE filter is not, so it is -- and the
              // subtitle says which population these bars are of.
              subtitle={`Rules tripped (an exposure can trip several)${
                dpd ? ` within ${feed.dpd_bands.find((b) => b.key === dpd)?.label ?? dpd}` : ""
              }. Click a rule to filter the page to it; again to clear.`}
              data={[
                {
                  type: "bar",
                  orientation: "h",
                  y: feed.reasons.map((r) => r.reason).reverse(),
                  x: feed.reasons.map((r) => r.n).reverse(),
                  customdata: feed.reasons.map((r) => [r.reason, sar(r.ead)]).reverse(),
                  marker: {
                    color: feed.reasons.map((r) => (reason && r.reason !== reason ? `${SEMANTIC.stage}55` : SEMANTIC.stage)).reverse(),
                    line: { color: feed.reasons.map((r) => (r.reason === reason ? SEMANTIC.increase : "rgba(0,0,0,0)")).reverse(), width: 2 },
                  },
                  hovertemplate: "%{y}: %{x:,} exposures · EAD %{customdata[1]}<extra></extra>",
                },
              ]}
              layout={{ margin: { l: 280, r: 20, t: 10, b: 40 }, xaxis: { title: { text: "Exposures" } } }}
              testId="ew-reasons"
              context={{ releaseId: feed.release_id, period: feed.period, source: `EWS rule set ${feed.ruleset}` }}
              onPointClick={(p) => {
                const r = Array.isArray(p.customdata) ? String(p.customdata[0]) : String(p.y ?? "");
                if (r) toggleReason(r);
              }}
              table={{
                columns: [{ key: "reason", label: "Rule" }, { key: "n", label: "Exposures", align: "right" }, fullMoneyCol("ead", "EAD", feed.reasons as unknown as Record<string, unknown>[])],
                rows: feed.reasons as unknown as Record<string, unknown>[],
                onRowActivate: (row) => toggleReason(String(row.reason)),
                activateLabel: "Filter the page to the rule",
              }}
            />
          </div>
          <section>
            <h2 className="mb-2 text-sm font-semibold">By {feed.segment_dimension}</h2>
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {feed.by_segment.map((s) => {
                // The focused severities, not a fixed high/critical: this
                // card's own Investigate / Save / Export / What-If freeze
                // `bandsInUse`, so its headline count has to be the same
                // population or the button does not do what the card says.
                const severe = s.bands.filter((b) => bandsInUse.includes(b.value));
                const n = severe.reduce((a, b) => a + b.n, 0);
                const ead = severe.reduce((a, b) => a + (b.ead_sar_mn ?? 0), 0);
                return (
                  <div key={s.segment} className="rounded-xl border border-border bg-surface p-3" data-testid="ew-segment-card">
                    <div className="flex items-baseline justify-between">
                      <span className="font-medium">{s.segment}</span>
                      <span className="text-xs text-text-muted">
                        {count(n)} {bandsLabel} · {sar(ead)}
                      </span>
                    </div>
                    <div className="mt-2 flex h-2 overflow-hidden rounded-full bg-surface-sunken">
                      {BANDS.map((band) => {
                        const row = s.bands.find((b) => b.value === band);
                        const total = s.bands.reduce((a, b) => a + b.n, 0) || 1;
                        return <div key={band} style={{ width: `${((row?.n ?? 0) / total) * 100}%`, background: SEVERITY_COLORS[band] }} title={`${band}: ${row?.n ?? 0}`} />;
                      })}
                    </div>
                    <div className="mt-2 flex flex-wrap gap-1.5 text-xs">
                      <button type="button" disabled={!n || busy} onClick={() => void investigate(s.segment)} className="rounded border border-border px-2 py-0.5 disabled:opacity-40" data-testid="ew-seg-investigate" data-segment={s.segment}>
                        Investigate
                      </button>
                      <button type="button" disabled={!n} onClick={() => void guarded(async () => void (await saveCohort(s.segment)))} className="rounded border border-border px-2 py-0.5 disabled:opacity-40" data-testid="ew-seg-save" data-segment={s.segment}>
                        Save cohort
                      </button>
                      <button type="button" disabled={!n} onClick={() => void guarded(() => exportCohort(s.segment))} className="rounded border border-border px-2 py-0.5 disabled:opacity-40" data-testid="ew-seg-export" data-segment={s.segment}>
                        Export
                      </button>
                      <button type="button" disabled={!n} onClick={() => void guarded(() => whatIf(s.segment))} className="rounded border border-border px-2 py-0.5 disabled:opacity-40" data-testid="ew-seg-whatif" data-segment={s.segment}>
                        What-If
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
          <section className="space-y-2">
            <h2 className="text-sm font-semibold">
              <span className="capitalize">{bandsLabel}</span> exposures
              {reason ? <span className="font-normal text-text-muted"> tripping {reason}</span> : null}
              {dpd ? <span className="font-normal text-text-muted"> · {feed.dpd_bands.find((b) => b.key === dpd)?.label ?? dpd}</span> : null}
            </h2>
            <DataGrid
              key={`${key}|${band}`}
              domain={domain}
              lockedFilters={gridLocked}
              testId="ew-grid"
              compact
            />
          </section>
          <section className="rounded-lg border border-border bg-surface p-3 text-xs">
            <h2 className="mb-1 text-sm font-semibold">Rule set {feed.ruleset}</h2>
            <ul className="list-disc pl-5">
              {feed.rules.map((r) => (
                <li key={r.id}>
                  <span className="font-medium">{r.id}</span> {r.label} (weight {r.weight})
                  {r.limitation ? <span className="text-warning"> — {r.limitation}</span> : null}
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
    </div>
  );
}
