"use client";

/**
 * PLAN_R10 G-TILES on Early Warning: a thin adapter over Session S's shared `KpiRow` (max 4, one row, 2×2 only below
 * 900 px). Callers pass a ready sub-line ("n of N · x% of exposure" from ./tile-format).
 */

import * as React from "react";

import { KpiRow, type KpiTile } from "@/components/v5/core/kpi-row";

export { ofN, ofNLine } from "./tile-format";

export interface Tile {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  tone?: "negative" | "warning" | "default";
  onClick?: () => void;
  /** What a click does; shown as the tile's (i). */
  hint?: string;
  testId?: string;
}

export const MAX_TILES = 4;

export function toKpiTile(t: Tile): KpiTile {
  return {
    label: t.label, value: t.value, sub: t.sub, onClick: t.onClick, testId: t.testId,
    tone: t.tone === "negative" ? "negative" : t.tone === "warning" ? "warning" : "neutral",
    // KpiRow renders a clickable tile as a <button>; its (i) is a button too, so a clickable tile carries no (i).
    info: t.onClick ? undefined : t.hint,
  };
}

export function TileRow({ tiles, testId, className }: { tiles: Tile[]; testId?: string; className?: string }) {
  return <KpiRow tiles={tiles.slice(0, MAX_TILES).map(toKpiTile)} testId={testId} className={className} />;
}
