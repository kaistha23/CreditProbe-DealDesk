"use client";

/**
 * PLAN_R10 S2: the shared compact KPI tile row (G-TILES). Use it on every screen that shows KPI tiles:
 *
 *   <KpiRow tiles={[
 *     { label: "Warned borrowers", value: count(214), share: { n: 214, of: 1250, exposure: 840, exposureTotal: 4560 } },
 *     { label: "Exposure warned", value: sar(840), sub: "Stage 2 and 3" },
 *   ]} />
 *
 * At most 4 tiles (extras are dropped, never wrapped), one row side by side with even spacing; 2×2 only below
 * 900 px. Each tile: a short label, one bold key number, one short sub-line ("n of N · x% of exposure" for a
 * subset, via `share`), an optional (i) and an optional click.
 */

import * as React from "react";
import { Info } from "lucide-react";

import { cn } from "@/lib/utils";
import { KPI_ROW_MAX, clampTiles, gridClass, shareLine, type KpiShare } from "@/lib/v5/kpi-row";

export type KpiTone = "neutral" | "positive" | "negative" | "warning";

export interface KpiTile {
  label: string;
  /** Already formatted (use lib/v5/format). Rendered bold. */
  value: React.ReactNode;
  /** One short sub-line. Used when `share` is absent, or after it. */
  sub?: React.ReactNode;
  /** For a subset: renders "n of N · x% of exposure". */
  share?: KpiShare;
  /** The (i) text: what the figure is and how it is computed. */
  info?: React.ReactNode;
  tone?: KpiTone;
  onClick?: () => void;
  href?: string;
  /** Marks the tile as the active filter. */
  active?: boolean;
  testId?: string;
}

const TONE: Record<KpiTone, string> = {
  neutral: "text-text-primary",
  positive: "text-positive",
  negative: "text-negative",
  warning: "text-warning",
};

function TileInfo({ label, info }: { label: string; info: React.ReactNode }) {
  const [open, setOpen] = React.useState(false);
  return (
    <span className="relative inline-flex">
      <button type="button" aria-label={`About ${label}`} onClick={(e) => { e.stopPropagation(); e.preventDefault(); setOpen((o) => !o); }}
              className="inline-flex size-4 items-center justify-center rounded-full text-text-muted hover:text-text-secondary">
        <Info className="size-3" aria-hidden />
      </button>
      {open ? (
        <span role="dialog" className="absolute right-0 top-5 z-40 w-64 max-w-[80vw] rounded-md border border-border bg-surface-raised p-2.5 text-[11px] font-normal normal-case leading-relaxed tracking-normal text-text-secondary shadow-lg">
          {info}
        </span>
      ) : null}
    </span>
  );
}

function Tile({ t }: { t: KpiTile }) {
  const line = t.share ? shareLine(t.share) : "";
  const body = (
    <>
      <span className="flex items-center justify-between gap-2">
        <span className="truncate text-[11px] font-medium uppercase tracking-wide text-text-muted" title={t.label}>{t.label}</span>
        {t.info ? <TileInfo label={t.label} info={t.info} /> : null}
      </span>
      <span className={cn("mt-1 block truncate text-[20px] font-bold leading-tight tabular-nums", TONE[t.tone ?? "neutral"])}
            data-testid={t.testId ? `${t.testId}-value` : undefined}>
        {t.value}
      </span>
      {(line || t.sub) ? (
        <span className="mt-0.5 block truncate text-[11px] text-text-secondary" data-kpi-sub>
          {line}{line && t.sub ? " · " : ""}{t.sub}
        </span>
      ) : null}
    </>
  );
  const cls = cn("block min-w-0 rounded-lg border bg-surface-raised px-3 py-2.5 text-left",
                 t.active ? "border-accent ring-1 ring-accent/40" : "border-border",
                 (t.onClick || t.href) && "transition-colors hover:border-accent/60 hover:bg-surface-hover");
  if (t.href) return <a href={t.href} className={cls} data-testid={t.testId} data-kpi-tile>{body}</a>;
  if (t.onClick) return <button type="button" onClick={t.onClick} className={cls} aria-pressed={t.active} data-testid={t.testId} data-kpi-tile>{body}</button>;
  return <div className={cls} data-testid={t.testId} data-kpi-tile>{body}</div>;
}

export function KpiRow({ tiles, className, testId = "kpi-row" }: { tiles: readonly KpiTile[]; className?: string; testId?: string }) {
  if (process.env.NODE_ENV !== "production" && tiles.length > KPI_ROW_MAX) {
    console.warn(`KpiRow: ${tiles.length} tiles given; G-TILES allows ${KPI_ROW_MAX}. Extra tiles are dropped.`);
  }
  const shown = clampTiles(tiles);
  if (!shown.length) return null;
  return (
    <div className={cn("grid gap-3", gridClass(shown.length), className)} data-testid={testId} data-kpi-count={shown.length}>
      {shown.map((t, i) => <Tile key={`${t.label}-${i}`} t={t} />)}
    </div>
  );
}

export { nOfN, shareLine, shareOf } from "@/lib/v5/kpi-row";
export type { KpiShare } from "@/lib/v5/kpi-row";
