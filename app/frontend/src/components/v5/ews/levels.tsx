"use client";

/**
 * Early Warning card levels and drill journeys (PLAN_R4 B4).
 *
 * The level toggle cuts the top cards by another dimension (corporate: region, branch, rating grade,
 * RM / business unit, product; retail: region, branch, score band, salaried, vintage). Each level is a
 * journey, e.g. Region -> Branch -> Sector -> borrowers. The drill filter lives in the address as
 * `lv` plus one `f_<dim>` per step, so Back, breadcrumbs and deep links work, and the same filter
 * travels to the customer list, the Excel workbook and Export to What-If.
 * Cards are the same cards as the Sector / Product view (ChildCard), on the service's figures.
 */

import * as React from "react";
import { ArrowLeft, ChevronRight, ListChecks } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { InfoPopover } from "@/components/ui/info-popover";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { type DomainId, type ExcelParams, type Level, count, ewsOrigin, sar, useEws } from "@/lib/v5/ews";

import { CHART_HINT, ComparePlot, RatingPlot } from "./charts";
import { ChartInfo } from "@/components/v5/core/chart-explain";
import { compareExplain, ratingExplain } from "./explain";
import { ExcelLink, ExportToWhatIf, TopReasons, TrendChart } from "./parts";
import { HeadlineTiles } from "./headline-tiles";
import { friendlyError } from "@/lib/v5/errors";

export const DIM_KEYS = ["sector", "region", "branch", "rating", "bu", "rm", "product", "band", "salaried", "vintage"] as const;
export type DimKey = (typeof DIM_KEYS)[number];
export type Dims = Partial<Record<DimKey, string>>;

export interface LevelInfo { key: string; label: string; journey: DimKey[]; journey_labels: string[] }
export interface LevelsMeta {
  domain_id: DomainId; default: string; levels: LevelInfo[];
  dims: Record<string, { label: string; plural: string; owner: boolean }>;
}
export interface DimLevel extends Level {
  level: string; level_label: string; journey: DimKey[]; journey_labels: string[]; dims: Dims; depth: number;
  next_dim: DimKey | null; next_label: string | null; leaf: boolean;
  breadcrumbs: { label: string; dim?: DimKey; dims: Dims; scope: Level["breadcrumbs"][number]["scope"] }[];
  reconcile: { exposure: number; facilities: number; customers: number; customers_add_up: boolean } | null;
}

/** The planned levels, known before the service answers, so the toggle never jumps. */
export const LEVELS: Record<DomainId, { key: string; label: string; journey: DimKey[] }[]> = {
  corporate: [
    { key: "sector", label: "Sector", journey: ["sector"] },
    { key: "region", label: "Region", journey: ["region", "branch", "sector"] },
    { key: "branch", label: "Branch", journey: ["branch", "sector"] },
    { key: "rating", label: "Rating grade", journey: ["rating", "sector"] },
    { key: "rm", label: "RM / business unit", journey: ["bu", "rm"] },
    { key: "product", label: "Product", journey: ["product", "sector"] },
  ],
  retail: [
    { key: "product", label: "Product", journey: ["product"] },
    { key: "region", label: "Region", journey: ["region", "branch", "product"] },
    { key: "branch", label: "Branch", journey: ["branch", "product"] },
    { key: "band", label: "Score band", journey: ["band", "product"] },
    { key: "salaried", label: "Salaried / Non-Salaried", journey: ["salaried", "product"] },
    { key: "vintage", label: "Vintage", journey: ["vintage", "product"] },
  ],
};
export const DEFAULT_LEVEL: Record<DomainId, string> = { corporate: "sector", retail: "product" };

export function isDimLevel(domain: DomainId, lv: string): boolean {
  return !!lv && lv !== DEFAULT_LEVEL[domain] && LEVELS[domain].some((l) => l.key === lv);
}

export function journeyOf(domain: DomainId, lv: string): DimKey[] {
  return LEVELS[domain].find((l) => l.key === lv)?.journey ?? [];
}

/** The drill filter in the address: the journey's prefix that is set, in journey order. */
export function dimsFromQuery(domain: DomainId, lv: string, get: (k: string) => string): Dims {
  const out: Dims = {};
  for (const d of journeyOf(domain, lv)) {
    const v = get(`f_${d}`);
    if (!v) break;
    out[d] = v;
  }
  return out;
}

export function dimsToQuery(dims: Dims): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(dims)) if (v) out[`f_${k}`] = v;
  return out;
}

const PRODUCT_TYPES: Record<string, string> = {
  asset_finance: "Asset finance", overdraft: "Overdraft", project_finance: "Project finance",
  revolving_credit: "Revolving credit", supply_chain_finance: "Supply chain finance", term_loan: "Term loan",
  trade_finance: "Trade finance", working_capital: "Working capital",
};

/** A drill value as the cards name it (the service's dim_value_label). */
export function dimValueLabel(domain: DomainId, dim: string, value: string): string {
  if (dim === "band") return `Band ${value}`;
  if (dim === "salaried") return value === "SALARIED" ? "Salaried" : value === "NON_SALARIED" ? "Non-Salaried" : value;
  if (dim === "product" && domain === "corporate") return PRODUCT_TYPES[value] ?? value;
  return value;
}

export function dimsLabel(dims: Dims, domain: DomainId): string {
  const vals = Object.entries(dims).map(([k, v]) => dimValueLabel(domain, k, v ?? ""));
  return vals.join(" › ") || (domain === "corporate" ? "Total corporate" : "Total retail");
}

/** Where Back from the list goes: the level the list was opened from. */
export function listParentDims(domain: DomainId, lv: string, dims: Dims): Dims {
  const journey = journeyOf(domain, lv);
  const keys = Object.keys(dims) as DimKey[];
  if (keys.length < journey.length) return dims;
  const out: Dims = {};
  for (const k of keys.slice(0, -1)) out[k] = dims[k];
  return out;
}

/** Breadcrumbs above the list and the customer on a journey: every step is a link back. */
export function DimCrumbs({ domain, lv, dims, tail, onDims, onTail }: {
  domain: DomainId; lv: string; dims: Dims; tail: string[]; onDims: (d: Dims) => void; onTail?: () => void;
}) {
  const level = LEVELS[domain].find((l) => l.key === lv);
  const portfolio = `${domain === "corporate" ? "Total corporate" : "Total retail"} by ${(level?.label ?? lv).toLowerCase()}`;
  const journey = journeyOf(domain, lv);
  const full = Object.keys(dims).length >= journey.length;
  const crumbs: { label: string; dims: Dims }[] = [{ label: portfolio, dims: {} }];
  const acc: Dims = {};
  for (const d of journey) {
    const v = dims[d];
    if (!v) break;
    acc[d] = v;
    crumbs.push({ label: dimValueLabel(domain, d, v), dims: { ...acc } });
  }
  return (
    <nav className="flex flex-wrap items-center gap-1 text-[13px]" data-testid="ews-breadcrumbs">
      {crumbs.map((c, i) => {
        // The full journey is the list itself: its crumb is not a level to open.
        const clickable = !(full && i === crumbs.length - 1);
        return (
          <React.Fragment key={`${i}-${c.label}`}>
            {i ? <ChevronRight className="size-3.5 text-text-muted" aria-hidden /> : null}
            {clickable ? (
              <button type="button" className="text-accent hover:underline" data-testid={`ews-crumb-${i}`}
                      onClick={() => onDims(c.dims)}>{c.label}</button>
            ) : <span className="text-text-primary">{c.label}</span>}
          </React.Fragment>
        );
      })}
      {tail.map((t, i) => (
        <React.Fragment key={`t-${t}`}>
          <ChevronRight className="size-3.5 text-text-muted" aria-hidden />
          {i === tail.length - 1 ? <span className="font-semibold text-text-primary" data-testid="ews-crumb-current">{t}</span> : (
            <button type="button" className="text-accent hover:underline" data-testid="ews-crumb-list" onClick={onTail}>{t}</button>
          )}
        </React.Fragment>
      ))}
    </nav>
  );
}

async function getView(domain: DomainId, level: string, period: string, dims: Dims): Promise<DimLevel> {
  const q = new URLSearchParams({ domain, level });
  if (period) q.set("period", period);
  if (Object.keys(dims).length) q.set("dims", JSON.stringify(dims));
  let r: Response;
  try {
    r = await fetch(`${ewsOrigin()}/api/v1/ews/levels/view?${q.toString()}`, { cache: "no-store", credentials: "include" });
  } catch {
    throw new Error("Early Warning is temporarily unavailable. Please try again in a moment.");
  }
  const body = await r.json().catch(() => null);
  if (!r.ok) {
    throw new Error(friendlyError("Early Warning", r.status, body));
  }
  return body as DimLevel;
}

/** View by: one segmented control at the top of Early Warning. */
export function LevelToggle({ domain, level, onChange }: {
  domain: DomainId; level: string; onChange: (lv: string) => void;
}) {
  const current = level || DEFAULT_LEVEL[domain];
  return (
    <div className="flex flex-wrap items-center gap-2" data-testid="ews-level-toggle">
      <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-text-muted">View by</span>
      <div role="tablist" aria-label="View by" className="inline-flex flex-wrap rounded-md border border-border bg-surface p-0.5">
        {LEVELS[domain].map((l) => (
          <button key={l.key} type="button" role="tab" aria-selected={current === l.key}
                  data-testid={`ews-lv-${l.key}`} onClick={() => onChange(l.key)}
                  className={cn("rounded px-3 py-1 text-[12px] font-medium transition-colors",
                                current === l.key ? "bg-accent text-accent-contrast"
                                  : "text-text-secondary hover:bg-surface-muted")}>
            {l.label}
          </button>
        ))}
      </div>
      <InfoPopover title="Levels and drill journeys" className="ml-1">
        <ul className="space-y-1 text-[12px]">
          {LEVELS[domain].map((l) => (
            <li key={l.key}><span className="font-medium">{l.label}:</span>{" "}
              {[...l.journey.map((d) => DIM_LABEL[d]), domain === "corporate" ? "Borrowers" : "Customers"].join(" → ")}</li>
          ))}
        </ul>
      </InfoPopover>
    </div>
  );
}

const DIM_LABEL: Record<DimKey, string> = {
  sector: "Sector", region: "Region", branch: "Branch", rating: "Rating grade", bu: "Business unit",
  rm: "Relationship manager", product: "Product", band: "Score band", salaried: "Salaried / Non-Salaried",
  vintage: "Vintage",
};

type CardProps = {
  card: Level["children"][number]; labels: Level["labels"]; parent: string; scope: Record<string, unknown>;
  onOpen: () => void; onReason: (reason: string) => void;
  /** R16 m (M2): the card's primary action, the segment analysis of its population. */
  onAnalyse?: () => void;
};

/** One step of a journey: headline, trend, the next dimension's cards. */
export function DimLevelView({ domain, period, level, dims, onDims, onList, onAnalyse, ChildCard }: {
  domain: DomainId; period: string; level: string; dims: Dims;
  onDims: (dims: Dims) => void;
  onAnalyse?: (dims: Dims) => void;
  onList: (dims: Dims, cohort: string, extra?: { reason?: string }) => void;
  ChildCard: (p: CardProps) => React.ReactElement;
}) {
  const key = [domain, period, level, JSON.stringify(dims)].join("|");
  const { data, error, loading } = useEws<DimLevel>(() => getView(domain, level, period, dims), key);
  if (error) return <p className="text-sm text-negative" data-testid="ews-level-error">{error}</p>;
  if (loading || !data) return <Skeleton className="h-96 w-full" />;
  const L = data.labels;
  const h = data.headline;
  const scopeBody = { domain, period: data.period, dims };
  const next = data.next_dim;
  const step = (k: string): Dims => (next ? { ...dims, [next]: k } : dims);
  const openCard = (k: string) => {
    const nd = step(k);
    const last = Object.keys(nd).length >= data.journey.length;
    if (last) onList(nd, "warned");
    else onDims(nd);
  };
  const up = data.breadcrumbs.length > 1 ? data.breadcrumbs[data.breadcrumbs.length - 2].dims : null;
  const childLabels = { ...L };

  return (
    <div className="space-y-4" data-testid={`ews-dim-level-${data.depth}`} data-level={level}>
      <nav className="flex flex-wrap items-center gap-1 text-[13px]" data-testid="ews-breadcrumbs">
        {data.breadcrumbs.map((b, i) => {
          const last = i === data.breadcrumbs.length - 1;
          return (
            <React.Fragment key={`${i}-${b.label}`}>
              {i ? <ChevronRight className="size-3.5 text-text-muted" aria-hidden /> : null}
              {last ? <span className="font-semibold text-text-primary" data-testid="ews-crumb-current">{b.label}</span> : (
                <button type="button" className="text-accent hover:underline" data-testid={`ews-crumb-${i}`}
                        onClick={() => onDims(b.dims)}>{b.label}</button>
              )}
            </React.Fragment>
          );
        })}
        {up ? (
          <Button variant="outline" size="sm" className="ml-3" data-testid="ews-level-back" onClick={() => onDims(up)}>
            <ArrowLeft className="mr-1 size-3.5" aria-hidden /> Up
          </Button>
        ) : null}
      </nav>

      {/* PLAN_R10 E1: one row of 4 small tiles, then the cards without scrolling; summary and charts below. */}
      <HeadlineTiles headline={h} onList={(c) => onList(dims, c)} />

      {data.children.length ? (
        <section className="space-y-2" data-testid="ews-children" data-dim={next ?? ""}>
          <div className="flex items-center gap-2">
            <p className="text-sm font-semibold text-text-primary">{data.next_label}</p>
            {data.reconcile ? (
              <InfoPopover title={`${data.next_label} add up to ${data.name}`}>
                <p className="text-[12px]" data-testid="ews-reconcile">
                  {data.children.length} cards · exposure {sar(data.reconcile.exposure)} of {sar(h.exposure)} ·{" "}
                  {count(data.reconcile.facilities)} of {count(h.facilities)} {L.exposures}
                  {data.reconcile.customers_add_up
                    ? ` · ${count(data.reconcile.customers)} of ${count(h.customers)} ${L.owners}.`
                    : `. A ${L.owner} with ${L.exposures} in two ${(data.next_label ?? "").toLowerCase()} is counted in each.`}
                </p>
              </InfoPopover>
            ) : null}

      <Card className="space-y-3 p-4" data-testid="ews-level-summary">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-sm font-semibold text-text-primary" data-testid="ews-level-name">{data.name}</p>
          <Button size="sm" onClick={() => onList(dims, "warned")} data-testid="ews-open-warned">
            <ListChecks className="mr-1 size-3.5" aria-hidden /> Open the {count(h.customers_warned)} warned {L.owners}
          </Button>
          <ExportToWhatIf testId="ews-export-level" body={{ ...scopeBody, cohort: "warned" }}
                          label={`Export warned ${L.owners} to What-If`} />
          <ExcelLink testId="ews-excel-level"
                     params={{ domain, period: data.period, cohort: "all", dims: JSON.stringify(dims) } as ExcelParams} />
        </div>
        <div>
          <p className="mb-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-text-muted">Top warning reasons</p>
          <TopReasons reasons={data.top_reasons} owners={L.owners} period={L.period} testId="ews-top-reasons"
                      onOpen={(reason) => onList(dims, "warned", { reason })} />
        </div>
      </Card>

      <TrendChart trend={data.trend} owners={L.owners} />

      {data.children.length > 1 ? (
        <Card className="p-4" data-testid="ews-compare">
          <div className="flex items-center gap-2"><p className="text-sm font-semibold text-text-primary">{data.next_label} compared</p>
            <ChartInfo title={`${data.next_label} compared`} explain={compareExplain(data.children, L.owners, (data.next_label ?? "").toLowerCase())} hint={CHART_HINT} /></div>
          <ComparePlot cards={data.children} owners={L.owners} kind={(data.next_label ?? "").toLowerCase()}
                       testId="ews-compare-chart" onOpen={openCard} />
        </Card>
      ) : null}

      {/* PLAN_R5 P4: each level shows only its own charts; the rating chart belongs to View by = Rating. */}
      {domain === "corporate" && level === "rating" && next === "rating" && data.rating_mix?.length ? (
        <Card className="p-4" data-testid="ews-ratings">
          <div className="flex items-center gap-2"><p className="text-sm font-semibold text-text-primary">Borrowers by rating</p>
            <ChartInfo title="Borrowers by rating" explain={ratingExplain(data.rating_mix, L.owners)} hint={CHART_HINT} /></div>
          <RatingPlot mix={data.rating_mix} owners={L.owners} testId="ews-rating-chart" />
        </Card>
      ) : null}

          </div>
          <div className="grid gap-3 lg:grid-cols-2">
            {data.children.map((c) => (
              <ChildCard key={c.key} card={c} labels={childLabels} parent={data.name}
                         scope={{ ...scopeBody, dims: step(c.key) }}
                         onOpen={() => openCard(c.key)}
                         onAnalyse={onAnalyse ? () => onAnalyse(step(c.key)) : undefined}
                         onReason={(reason) => onList(step(c.key), "warned", { reason })} />
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}
