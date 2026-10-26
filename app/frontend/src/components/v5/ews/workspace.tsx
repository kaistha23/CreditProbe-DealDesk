"use client";

/**
 * v5 Early Warning: one screen, every level, both books.
 *
 *   Corporate:  TOTAL -> SECTOR -> SUB-SECTOR -> BORROWERS -> BORROWER
 *   Retail:     TOTAL -> PRODUCT -> SALARIED / NON-SALARIED -> SUB-PRODUCT
 *               -> CUSTOMERS -> CUSTOMER
 *
 * The drill-down screens are the Retail Demo's (c0db151f) -- KPI tiles,
 * interpretation, cards with six-period charts, top reasons, materiality, the
 * customer list and the customer -- running on the Early Warning service's
 * rule set (gw-ews-1.1.0; 1.0.0 recorded) over the v5 books. The level lives in the address,
 * so Back walks up, a link opens the exact view, and Borrower 360 can send a
 * reader straight to a customer.
 */

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { ArrowLeft, BookOpenCheck, ChevronRight, ListChecks, MessageSquareText, Microscope } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { InfoPopover } from "@/components/ui/info-popover";
import { Skeleton } from "@/components/ui/skeleton";
import { ShareCurrent } from "@/components/v5/mail/share";
import { AddCurrentToReport } from "@/components/v5/playbook/add-current";
import { PanelActions } from "@/components/v5/thread/panel-actions";
import { ewsSources } from "@/lib/v5/thread-actions";
import { type Card as LevelCard, type DomainId, type Level, count, ews, pct, signed, useEws } from "@/lib/v5/ews";
import { cn } from "@/lib/utils";
import { ToolsMenu, WhoToCallPanel } from "@/components/v5/intel/ib"; // R13 IB: EWS tools
import { useUrlPanel } from "@/components/v5/ui/url-state"; // R14 U (K1)
import { backOr } from "@/lib/v5/back";

import { CrmComplianceCard } from "./crm-card";
import { EclImpactPanel } from "./ecl-impact";
import { CustomerDetail } from "./customer-detail";
import { EwsSaveInvestigation } from "./workspace-save";
import { CustomerList, type ListFilters } from "./customers";
import { SegmentAnalysisView } from "./segment-analysis";
import {
  AsOf, BookToggle, BySource, CardTrends, Commentary, CountsRow, ExcelLink, ExportToWhatIf, Interpretation,
  Materiality, TopReasons, TrendChart, askCockpitHref, recallBook, rememberBook,
} from "./parts";
import { CHART_HINT, ComparePlot } from "./charts";
import { HeadlineTiles } from "./headline-tiles";
import { TriageInbox, TriageWithAgent } from "./agent-triage";
import { ChartInfo } from "@/components/v5/core/chart-explain";
import { compareExplain } from "./explain";
import { CockpitAskBar } from "@/components/v5/landing/module-landing";
import {
  DIM_KEYS, DimCrumbs, DimLevelView, type Dims, LevelToggle, dimsFromQuery, dimsLabel, dimsToQuery, isDimLevel,
  listParentDims,
} from "./levels";

const LIST_KEYS = ["cohort", "reason", "layer", "dpd", "stage", "band", "q"] as const;
const DIM_PARAMS = DIM_KEYS.map((d) => `f_${d}` as const);
// R16 m (M2): `analysis` opens the segment analysis of the scope in the address (a card's primary action), so Back
// returns to the cards.
const ALL_KEYS = ["domain", "period", "lv", ...DIM_PARAMS, "segment", "cls", "sub", "analysis", "customer", ...LIST_KEYS] as const;
type State = Record<(typeof ALL_KEYS)[number], string>;

export function EarlyWarningWorkspace() {
  const query = useSearchParams();
  const router = useRouter();
  const state = React.useMemo(() => {
    const s = {} as State;
    for (const k of ALL_KEYS) s[k] = query.get(k) ?? "";
    return s;
  }, [query]);
  const domain: DomainId = state.domain === "retail" ? "retail" : "corporate";

  const push = React.useCallback((next: Partial<State>) => {
    const params = new URLSearchParams();
    for (const [k, v] of Object.entries(next)) if (v) params.set(k, v);
    const search = params.toString();
    if (search === new URLSearchParams(window.location.search).toString()) return;
    window.history.pushState({}, "", search ? `?${search}` : window.location.pathname);
  }, []);

  // A first visit with no book in the address opens on the book the reader
  // last chose in the Cockpit (same key), or Corporate.
  React.useEffect(() => {
    if (!state.domain) {
      const remembered = recallBook();
      if (remembered && remembered !== "corporate") push({ ...state, domain: remembered });
    }
  }, [state, push]);

  const go = React.useCallback((next: Partial<State>) => push({ ...state, domain, ...next }), [push, state, domain]);
  /** Open a level: keep book and period, clear everything below. */
  const open = React.useCallback((next: Partial<State>) => push({ domain, period: state.period, ...next }),
    [push, domain, state.period]);

  const listOpen = LIST_KEYS.some((k) => state[k]);
  // PLAN_R4 B4: the level toggle and its drill journeys. `lv` names the level, `f_<dim>` the drill filter.
  const lv = isDimLevel(domain, state.lv) ? state.lv : "";
  const dims: Dims = lv ? dimsFromQuery(domain, lv, (k) => state[k as keyof State] ?? "") : {};
  const openDims = (d: Dims, extra: Partial<State> = {}) =>
    push({ domain, period: state.period, lv, ...dimsToQuery(d), ...extra } as Partial<State>);
  const listDims = (d: Dims, cohort: string, extra: { reason?: string } = {}) => openDims(d, { cohort, ...extra });
  const dimLabel = dimsLabel(dims, domain);

  return (
    <div className="space-y-4" data-testid="ews-workspace">
      <Header domain={domain} period={state.period}
              onBook={(d) => { rememberBook(d); push({ domain: d }); }}
              onPeriod={(p) => go({ period: p })} />
      {!state.customer && !listOpen ? (
        <LevelToggle domain={domain} level={lv || state.lv}
                     onChange={(next) => push({ domain, period: state.period, ...(isDimLevel(domain, next) ? { lv: next } : {}) })} />
      ) : null}
      {lv && (state.customer || listOpen) ? (
        <DimCrumbs domain={domain} lv={lv} dims={dims}
                   tail={state.customer ? [domain === "corporate" ? "Borrowers" : "Customers", state.customer]
                                        : [domain === "corporate" ? "Borrowers" : "Customers"]}
                   onDims={(d) => openDims(d)} onTail={() => go({ customer: "" })} />
      ) : null}
      {state.customer ? (
        // R7: Back returns to the exact previous screen of this tab (the list, Borrower 360, Workspace, Mail…); with
        // none (a pasted link), up one level -- to the list the customer belongs to.
        <CustomerDetail domain={domain} id={state.customer} period={state.period}
                        onBack={() => backOr(router, () => go({ customer: "" }))} />
      ) : listOpen ? (
        <CustomerList domain={domain} period={state.period} segment={state.segment} classification={state.cls}
                      subsegment={state.sub} dims={lv ? dims : undefined}
                      scopeLabel={lv ? dimLabel : [state.segment, state.cls, state.sub].filter(Boolean).join(" › ")
                        || (domain === "corporate" ? "Total corporate" : "Total retail")}
                      filters={{ cohort: state.cohort, reason: state.reason, layer: state.layer, dpd: state.dpd,
                                 stage: state.stage, band: state.band, q: state.q } as ListFilters}
                      onFilters={(f) => go({ cohort: state.cohort || "warned", ...f })}
                      onOpen={(id) => go({ customer: id })}
                      onBack={() => backOr(router, () => (lv ? openDims(listParentDims(domain, lv, dims))
                                        : open({ segment: state.segment, cls: state.cls, sub: state.sub })))}
                      onUp={() => (lv ? openDims(listParentDims(domain, lv, dims))
                                      : open({ segment: state.segment, cls: state.cls, sub: state.sub }))} />
      ) : state.analysis ? (
        <SegmentAnalysisView domain={domain} period={state.period} segment={state.segment} cls={state.cls} sub={state.sub}
                             dims={lv ? (dims as Record<string, string>) : undefined}
                             onBack={() => backOr(router, () => (lv ? openDims(Object.fromEntries(Object.entries(dims).slice(0, -1)) as Dims)
                               : open(state.sub ? { segment: state.segment, cls: state.cls }
                                        : state.cls ? { segment: state.segment } : {})))}
                             onOpenCustomer={(id) => go({ customer: id })}
                             onList={(cohort, extra = {}) => (lv ? listDims(dims, cohort, extra)
                               : open({ segment: state.segment, cls: state.cls, sub: state.sub, cohort, ...extra }))} />
      ) : lv ? (
        <DimLevelView domain={domain} period={state.period} level={lv} dims={dims}
                      onDims={(d) => openDims(d)} onList={listDims} ChildCard={ChildCard}
                      onAnalyse={(d) => openDims(d, { analysis: "1" })} />
      ) : (
        <LevelView domain={domain} period={state.period} segment={state.segment} cls={state.cls} sub={state.sub}
                   open={open} />
      )}
    </div>
  );
}

function Header({ domain, period, onBook, onPeriod }: {
  domain: DomainId; period: string; onBook: (d: DomainId) => void; onPeriod: (p: string) => void;
}) {
  const meta = useEws(() => ews.meta(domain), domain);
  const shown = period || meta.data?.as_of || "";
  const [tool, setTool] = useUrlPanel("tool"); // R14 U (K1): the Who to call drawer is in the address, so Back reopens it
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-3">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-text-muted">Intelligence</p>
          <h1 className="text-2xl font-semibold text-text-primary">Early Warning</h1>
        </div>
        <BookToggle domain={domain} onChange={onBook} />
        <label className="text-[10px] uppercase tracking-[0.08em] text-text-muted">
          {domain === "corporate" ? "Quarter" : "Month"}
          <select value={shown} onChange={(e) => onPeriod(e.target.value)} data-testid="ews-period"
                  className="mt-0.5 block rounded border border-border bg-surface px-2 py-1 text-[13px] normal-case tracking-normal text-text-primary">
            {[...(meta.data?.periods ?? [])].reverse().map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </label>
        <Link href={`/early-warning/model?domain=${domain}${shown ? `&period=${shown}` : ""}`} data-testid="ews-link-model"
              className="ml-auto inline-flex h-8 items-center gap-1 rounded-md border border-border px-3 text-xs font-medium text-text-primary hover:bg-surface-muted">
          <BookOpenCheck className="size-3.5" aria-hidden /> Model details
        </Link>
        <TriageWithAgent domain={domain} period={shown} />
        <ToolsMenu testId="ews-tools" items={[{ key: "calls", label: "Who to call today", hint: "Names needing a call this week, with reason and action" }]}
                   onPick={setTool} />
      </div>
      {tool === "calls" ? <WhoToCallPanel onClose={() => setTool("")} /> : null}
      {shown ? <AsOf domain={domain} period={shown} release={meta.data?.release_id} /> : null}
      {/* R13 X (J7): table-first module; the ask box is one line above the table. */}
      <CockpitAskBar ids="ews" before={() => rememberBook(domain)}
                     placeholder={domain === "corporate" ? "Ask about early warning: “which sectors drove the rise?”"
                       : "Ask about early warning: “which products drove the rise?”"} />
      {meta.error ? <p className="text-sm text-negative" data-testid="ews-service-error">{meta.error}</p> : null}
    </div>
  );
}

function LevelView({ domain, period, segment, cls, sub, open }: {
  domain: DomainId; period: string; segment: string; cls: string; sub: string;
  open: (next: Partial<State>) => void;
}) {
  const key = [domain, period, segment, cls, sub].join("|");
  const { data, error, loading } = useEws<Level>(
    () => ews.level({ domain, period, segment, classification: cls, subsegment: sub }), key);
  if (error) return <p className="text-sm text-negative" data-testid="ews-level-error">{error}</p>;
  if (loading || !data) return <Skeleton className="h-96 w-full" />;
  const L = data.labels;
  const h = data.headline;
  const here = { segment, cls, sub };
  const list = (cohort: string, extra: Partial<State> = {}) => open({ ...here, cohort, ...extra });
  const scopeBody = { domain, period: data.period, segment, classification: cls, subsegment: sub };
  // The comparison chart: the cards below it (sub-levels first, else the classifications).
  const compare = data.children.length ? data.children : data.classifications;
  const compareTitle = data.children.length
    ? (data.children_kind === "segment" ? L.segments : L.subsegments)
    : (L.classification ? `${L.classification}s` : "Classifications");
  const openCompared = (key: string) => {
    if (!data.children.length) open({ segment, cls: key });
    else if (data.children_kind === "segment") open({ segment: key });
    else open({ segment, cls, sub: key });
  };
  const question = data.scope.level === "portfolio"
    ? `Where is risk building across the ${domain} book this ${L.period}?`
    : `Why is ${data.name} deteriorating this ${L.period}, and which ${L.owners} drive it?`;

  return (
    <div className="space-y-4" data-testid={`ews-level-${data.scope.level}`}>
      <nav className="flex flex-wrap items-center gap-1 text-[13px]" data-testid="ews-breadcrumbs">
        {data.breadcrumbs.map((b, i) => {
          const last = i === data.breadcrumbs.length - 1;
          return (
            <React.Fragment key={b.label}>
              {i ? <ChevronRight className="size-3.5 text-text-muted" aria-hidden /> : null}
              {last ? <span className="font-semibold text-text-primary">{b.label}</span> : (
                <button type="button" className="text-accent hover:underline" data-testid={`ews-crumb-${i}`}
                        onClick={() => open({ segment: b.scope.segment ?? "", cls: b.scope.classification ?? "",
                                              sub: b.scope.subsegment ?? "" })}>{b.label}</button>
              )}
            </React.Fragment>
          );
        })}
        {data.scope.level !== "portfolio" ? (
          <Button variant="outline" size="sm" className="ml-3" data-testid="ews-level-back"
                  onClick={() => { const up = data.breadcrumbs[data.breadcrumbs.length - 2].scope;
                                   open({ segment: up.segment ?? "", cls: up.classification ?? "", sub: up.subsegment ?? "" }); }}>
            <ArrowLeft className="mr-1 size-3.5" aria-hidden /> Up
          </Button>
        ) : null}
      </nav>

      {data.interpretation ? <Interpretation level={data} onOpen={(s) => open({ segment: s })} /> : null}

      {/* PLAN_R10 E1: one row of 4 small tiles, then the cards (visible without scrolling at 1440×900), then the
          ECL impact panel; the other figures and the six-period trend sit below. */}
      <HeadlineTiles headline={h} onList={(c) => list(c)} />
      <TriageInbox domain={domain} />

      {data.classifications.length ? (
        <section className="space-y-2" data-testid="ews-classifications">
          <p className="text-sm font-semibold text-text-primary">Salaried and Non-Salaried</p>
          <div className="grid gap-3 lg:grid-cols-2">
            {data.classifications.map((c) => (
              <ChildCard key={c.key} card={c} labels={L} parent={data.name}
                         scope={{ ...scopeBody, classification: c.key }} note={c.derivation}
                         onOpen={() => open({ segment, cls: c.key })}
                         onAnalyse={() => open({ segment, cls: c.key, analysis: "1" })}
                         onReason={(reason) => open({ segment, cls: c.key, cohort: "warned", reason })} />
            ))}
          </div>
        </section>
      ) : null}

      {data.children.length ? (
        <section className="space-y-2" data-testid="ews-children">
          <div className="flex items-center gap-2">
            <p className="text-sm font-semibold text-text-primary">{data.children_kind === "segment" ? L.segments : L.subsegments}</p>
            <InfoPopover title="Cards">
              Ordered by high/critical exposure.{domain === "retail" && data.scope.level === "portfolio" ? ` ${data.definitions.overlap}` : ""}
            </InfoPopover>
          </div>
          <div className="grid gap-3 lg:grid-cols-2">
            {data.children.map((c) => {
              const nextScope = data.children_kind === "segment" ? { segment: c.key }
                : { segment, cls, sub: c.key };
              return (
                <ChildCard key={c.key} card={c} labels={L} parent={data.name}
                           scope={{ ...scopeBody, ...(data.children_kind === "segment" ? { segment: c.key } : { subsegment: c.key }) }}
                           onOpen={() => open(nextScope)}
                           onAnalyse={() => open({ ...nextScope, analysis: "1" })}
                           onReason={(reason) => open({ ...nextScope, cohort: "warned", reason })} />
              );
            })}
          </div>
        </section>
      ) : null}

      {/* PLAN_R9 C1 (P3): the ECL if the current warnings come true, for the book or one sector / product. */}
      {!cls && !sub ? (
        <EclImpactPanel domain={domain} period={data.period} segment={segment}
                        onOpenCustomer={(id) => open({ ...here, customer: id })} />
      ) : null}

      <TrendChart trend={data.trend} owners={L.owners} />

      {data.scope.level === "portfolio" ? <CrmComplianceCard domain={domain} /> : null}

      {compare.length > 1 ? (
        <Card className="p-4" data-testid="ews-compare">
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <p className="text-sm font-semibold text-text-primary">{compareTitle} compared</p>
            <p className="text-[10px] text-text-muted">Warned {L.owners} (left axis) and high/critical exposure (right axis)</p>
            <ChartInfo title={`${compareTitle} compared`} explain={compareExplain(compare, L.owners, compareTitle.toLowerCase())} hint={CHART_HINT} />
          </div>
          <ComparePlot cards={compare} owners={L.owners} kind={compareTitle.toLowerCase()} testId="ews-compare-chart"
                       onOpen={openCompared} />
        </Card>
      ) : null}

      <Card className="space-y-3 p-4" data-testid="ews-level-summary">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-sm font-semibold text-text-primary">{data.name}</p>
          <Button variant="outline" size="sm" onClick={() => list("warned")} data-testid="ews-open-warned">
            <ListChecks className="mr-1 size-3.5" aria-hidden /> Open the {count(h.customers_warned)} warned {L.owners}
          </Button>
          <ExportToWhatIf testId="ews-export-level" body={{ ...scopeBody, cohort: "warned" }}
                          label={`Export warned ${L.owners} to What-If`} />
          <ExcelLink testId="ews-excel-level" params={{ ...scopeBody, cohort: "all" }} />
          <ShareCurrent type="early-warning-list" testId="ews-share-level" id={`${domain}|${data.period}|${data.name}`}
                        label={`Early Warning: ${data.name}, ${data.period}`}
                        summary={`${count(h.customers_warned)} warned ${L.owners} of ${count(h.customers)}; ${count(h.high_or_critical)} high or critical.`}
                        meta={{ domain, period: data.period }} />
          <EwsSaveInvestigation level={data} />
          <AddCurrentToReport type="early-warning-list" testId="ews-add-report-level"
                              id={domain === "retail" ? "retail" : segment ? `corporate:${segment}` : "corporate"}
                              label={`Early Warning: ${data.name}, ${data.period}`} />
          {/* R16 t (M7): Trace and Word on this answer (Share and Add to report are the buttons beside it) */}
          <PanelActions module="ews" id={`${domain}|${data.period}|${data.name}`} title={`Early Warning: ${data.name}, ${data.period}`}
                        container='[data-testid="ews-level-summary"]' share={false} report={false} testId="ews-level-actions"
                        sources={ewsSources({ id: `${domain}|${data.period}|${data.name}`, domain })} />
          <Link href={askCockpitHref(question)} onClick={() => rememberBook(domain)} data-testid="ews-ask-cockpit"
                className="inline-flex h-8 items-center gap-1 rounded-md border border-border px-3 text-xs font-medium text-text-primary hover:bg-surface-muted">
            <MessageSquareText className="size-3.5" aria-hidden /> Ask the Cockpit
          </Link>
        </div>
        <BySource sources={h.by_source} testId="ews-by-source" />
        <Commentary text={data.commentary} testId="ews-level-commentary" />
        <div>
          <p className="mb-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-text-muted">Top warning reasons</p>
          <TopReasons reasons={data.top_reasons} owners={L.owners} period={L.period} testId="ews-top-reasons"
                      onOpen={(reason) => list("warned", { reason })} />
        </div>
      </Card>

      <details className="rounded-md border border-border p-3 text-[11px] text-text-secondary" data-testid="ews-definitions">
        <summary className="cursor-pointer font-medium text-text-primary">Definitions · rule set {data.ruleset}</summary>
        <ul className="mt-2 list-disc space-y-1 pl-4">
          {Object.entries(data.definitions).map(([k, v]) => <li key={k}>{v}</li>)}
        </ul>
      </details>
    </div>
  );
}

/** "+N warned" / "−N warned" on the prior period: red when more are warned, green when fewer (PLAN_R5 E). */
export function WarnedMove({ value, testId }: { value: number | null | undefined; testId?: string }) {
  const v = value ?? null;
  const direction = v === null || v === 0 ? "flat" : v > 0 ? "up" : "down";
  return (
    <span data-testid={testId} data-direction={direction}
          className={cn("rounded-full px-2 py-0.5 text-[11px] font-medium tabular-nums",
                        direction === "up" ? "bg-negative-muted text-negative"
                          : direction === "down" ? "bg-positive-muted text-positive" : "text-text-muted")}>
      {signed(v)} warned
    </span>
  );
}

export function ChildCard({ card, labels, parent, scope, note, onOpen, onReason, onAnalyse }: {
  card: LevelCard; labels: Level["labels"]; parent: string;
  scope: Record<string, unknown>; note?: string; onOpen: () => void; onReason: (reason: string) => void;
  /** R16 m (M2): the card's primary action, the segment analysis of its population (drivers, rules fired, top names,
   *  ECL and stage effect, actions). "Stress this cohort" (the What-If export) lives inside the analysis. */
  onAnalyse?: () => void;
}) {
  return (
    <Card className="space-y-3 p-4" data-testid={`ews-card-${card.key}`}>
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" onClick={onOpen} className="text-left text-[15px] font-semibold text-accent hover:underline"
                data-testid={`ews-open-${card.key}`}>
          {card.label}
        </button>
        <span className="rounded-full border border-border px-2 py-0.5 text-[10px] tabular-nums text-text-secondary">
          {pct(card.exposure_severe_pct)} high/critical
        </span>
        <WarnedMove value={card.movement.customers_warned} testId={`ews-warned-move-${card.key}`} />
        <span className="ml-auto">
          {onAnalyse ? (
            <Button size="sm" onClick={onAnalyse} data-testid={`ews-analyse-${card.key}`}
                    title={`Analyse the warned ${labels.owners} of ${card.label}: drivers, rules fired, top names, ECL effect, actions`}>
              <Microscope className="mr-1 size-3.5" aria-hidden /> Analyse
            </Button>
          ) : (
            <ExportToWhatIf size="sm" testId={`ews-export-${card.key}`} label="Stress this cohort" body={{ ...scope, cohort: "warned" }} />
          )}
        </span>
      </div>
      {note ? <p className="text-[10px] text-text-muted">{card.meaning} ({note})</p> : null}
      <CountsRow counts={card} owners={labels.owners} />
      <BySource sources={card.by_source} testId={`ews-by-source-${card.key}`} />
      <CardTrends trend={card.trend} owners={labels.owners} testId={`ews-trends-${card.key}`}
                  cardKey={card.key} title={card.label} />
      <TopReasons reasons={card.top_reasons} owners={labels.owners} period={labels.period} onOpen={onReason}
                  testId={`ews-reasons-${card.key}`} />
      <Materiality card={card} parent={parent} labels={labels} testId={`ews-materiality-${card.key}`} />
      <Commentary text={card.commentary} />
      <div className="flex justify-end">
        <Button variant="outline" size="sm" onClick={onOpen} data-testid={`ews-open-bottom-${card.key}`}>Open {card.label} <ChevronRight className="ml-1 size-3.5" aria-hidden /></Button>
      </div>
    </Card>
  );
}
