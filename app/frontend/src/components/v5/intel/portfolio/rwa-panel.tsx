"use client";

/** PLAN_R13 §I ID, backlog #16: RWA finder — capital savings in the book, each with its SAR RWA and capital effect. */

import * as React from "react";

import { Chip, tableCls, tdCls, thCls } from "@/components/v5/dealdesk/kit";
import { cn } from "@/lib/utils";
import { type Rwa, type RwaStatus, STATUS_LABEL, sarM, toolPath } from "@/lib/v5/intel-portfolio";

import { PanelWords } from "@/components/v5/panels-g/panel-words";
import { writeRwa } from "@/lib/v5/plain-words-g/book";

import { Footnotes, Interpretation, Loading, PanelError, Strip, useIntel } from "./shell";

const tone = (s: RwaStatus) => (s === "recognisable" ? "positive" : s === "after_action" ? "accent" : "warning") as "positive" | "accent" | "warning";

export function RwaPanel({ limit = 30 }: { limit?: number }) {
  const { data, error, loading } = useIntel<Rwa>(toolPath("rwa", { limit }));
  const [cat, setCat] = React.useState("");
  const rows = data ? data.rows.filter((r) => !cat || r.category === cat).slice(0, 15) : [];
  return (
    <div className="space-y-3" data-testid="intel-rwa">
      <PanelWords panel="rwa" lines={data ? () => writeRwa(data) : error ? [] : null} />
      {error ? <PanelError error={error} /> : null}
      {loading ? <Loading what="Searching the book for capital savings…" /> : null}
      {data ? (<>
        <Interpretation lines={data.summary} testId="intel-rwa-summary" />
        <Strip kpis={data.kpis} pick={["rwa_saving", "capital_saving", "recognisable", "at_risk"]} testId="intel-rwa-kpis" />
        <div className="overflow-x-auto">
          <table className={tableCls} data-testid="intel-rwa-categories">
            <thead><tr><th className={thCls}>Source</th><th className={thCls}>Status</th><th className={cn(thCls, "text-right")}>Facilities</th>
              <th className={cn(thCls, "text-right")}>RWA saving</th><th className={cn(thCls, "text-right")}>Capital</th></tr></thead>
            <tbody>{data.by_category.map((c) => (
              <tr key={c.category} onClick={() => setCat(cat === c.category ? "" : c.category)} aria-selected={cat === c.category}
                  className={cn("cursor-pointer hover:bg-surface-hover", cat === c.category && "bg-accent-muted")} data-testid={`intel-rwa-cat-${c.category}`}>
                <td className={tdCls}>{c.label}</td><td className={tdCls}><Chip tone={tone(c.status)}>{STATUS_LABEL[c.status]}</Chip></td>
                <td className={cn(tdCls, "text-right")}>{c.facilities.toLocaleString("en-US")}</td>
                <td className={cn(tdCls, "text-right font-medium")}>{sarM(c.rwa_saving_sar_mn, 0)}</td>
                <td className={cn(tdCls, "text-right")}>{sarM(c.capital_saving_sar_mn, 1)}</td>
              </tr>))}</tbody>
          </table>
        </div>
        <div className="overflow-x-auto">
          <h3 className="mb-1 text-[12px] font-medium text-text-secondary">Largest items{cat ? `: ${data.by_category.find((c) => c.category === cat)?.label ?? ""}` : ""}</h3>
          {rows.length ? (
            <table className={tableCls} data-testid="intel-rwa-items">
              <thead><tr><th className={thCls}>Facility</th><th className={thCls}>What</th><th className={cn(thCls, "text-right")}>RWA saving</th></tr></thead>
              <tbody>{rows.map((r) => (
                <tr key={`${r.facility_id}-${r.category}`}>
                  <td className={tdCls}><span className="font-medium text-text-primary">{r.borrower_name}</span><span className="ml-1 text-text-muted">{r.facility_id} · {r.rating}</span></td>
                  <td className="border-b border-border/60 px-2 py-2 text-[12px] text-text-secondary">{r.detail}</td>
                  <td className={cn(tdCls, "text-right font-medium")}>{sarM(r.rwa_saving_sar_mn, 1)}</td>
                </tr>))}</tbody>
            </table>) : <p className="text-[12px] text-text-muted">The largest items of this source are below the top {limit} of the book; the category total is above.</p>}
        </div>
        <Footnotes env={data} testId="intel-rwa-notes" />
      </>) : null}
    </div>
  );
}
