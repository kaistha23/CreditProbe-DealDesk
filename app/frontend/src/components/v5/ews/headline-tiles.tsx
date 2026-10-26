"use client";

import { type Counts, count, pct, sar } from "@/lib/v5/ews";

import { type Tile, TileRow } from "./tile-row";
import { ofNLine, shareOf } from "./tile-format";

/**
 * PLAN_R10 E1: the Early Warning headline as one row of 4 small tiles. Warned, high or critical and already bad are
 * subsets of the book: "n of N · x% of exposure". Exposure warned closes the row. Default-entry rate, 30+ DPD exposure,
 * forward risk and the rest live in the cards, the trend and the definitions below.
 */
export function headlineTiles(h: Counts, onList: (cohort: string) => void): Tile[] {
  return [
    { label: "Warned", value: count(h.customers_warned), testId: "ews-kpi-warned", onClick: () => onList("warned"),
      sub: ofNLine(h.customers_warned, h.customers, h.exposure_warned_pct) },
    { label: "High or critical", value: count(h.high_or_critical), tone: "warning", testId: "ews-kpi-high",
      onClick: () => onList("high_or_critical"), sub: ofNLine(h.high_or_critical, h.customers, h.exposure_severe_pct) },
    { label: "Already bad", value: count(h.current_bad), tone: "negative", testId: "ews-kpi-bad",
      onClick: () => onList("current_bad"), hint: "90+ DPD, Stage 3 or default: open the list",
      sub: ofNLine(h.current_bad, h.customers, h.exposure_bad_pct ?? shareOf(h.exposure_bad, h.exposure)) },
    { label: "Exposure warned", value: sar(h.exposure_warned), testId: "ews-kpi-warned-exposure",
      sub: `${pct(h.exposure_warned_pct)} of ${sar(h.exposure)}` },
  ];
}

export function HeadlineTiles({ headline, onList }: { headline: Counts; onList: (cohort: string) => void }) {
  return <TileRow testId="ews-kpis" tiles={headlineTiles(headline, onList)} />;
}
