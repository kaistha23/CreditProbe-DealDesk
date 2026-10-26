"use client";

/**
 * PLAN_R11 R2: the review rule book as the bank configured it (data/dealdesk/review/rules.json): what each rule tests,
 * its threshold, severity, verdict on failure, policy clause, CBUAE CRM article and Delegation of Authority level.
 */

import * as React from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { useLoad } from "@/lib/v5/dealdesk";
import { CATEGORY_LABEL, type Category, SEVERITY_TONE, type Severity, reviewApi } from "@/lib/v5/dealdesk-review";

import { Chip, Section, tableCls, tdCls, thCls } from "./kit";

const DOA: Record<number, string> = { 1: "Corporate Credit Manager", 2: "Head of Credit", 3: "Chief Risk Officer", 4: "Executive Credit Committee", 5: "Board Credit Committee" };

function thr(v: unknown, unit: string | null): string {
  if (v === null || v === undefined) return "–";
  if (typeof v === "string") return v.startsWith("param:") ? `Admin parameter (${v.slice(6).split(".").pop()?.replace(/_/g, " ")})` : v;
  if (typeof v === "number") return unit === "share" ? `${(v * 100).toFixed(0)}%` : `${v}${unit ? ` ${unit}` : ""}`;
  return String(v);
}

export function ReviewRules() {
  const r = useLoad(() => reviewApi.rules(), "review-rules");
  const [cat, setCat] = React.useState<Category | "all">("all");
  const rows = (r.data?.rules ?? []).filter((x) => cat === "all" || x.category === cat);
  return (
    <Section title="Review rule book" testId="review-rules"
             info={<>Every check the review runs is a row here, configured by the bank: the bank adds or changes a rule
               there without code. A failed rule is <b>contradicted</b> (the data contradicts the memo) or an <b>exception</b> (a policy departure
               needing the approval level shown).</>}
             action={r.data ? <span className="text-[11px] text-text-muted">Version {r.data.version} · effective {r.data.effective_from}</span> : null}>
      {r.error ? <p role="alert" className="text-[12px] text-negative">{r.error}</p> : null}
      {!r.data && !r.error ? <Skeleton className="h-40 w-full" /> : null}
      {r.data ? (
        <>
          <div className="mb-2 flex flex-wrap gap-1.5">
            {(["all", "data", "consistency", "policy", "connected"] as const).map((k) => (
              <button key={k} type="button" onClick={() => setCat(k)}
                      className={cn("h-6 rounded-full border px-2 text-[11px]", cat === k ? "border-accent bg-accent-muted text-accent" : "border-border text-text-secondary hover:border-accent")}>
                {k === "all" ? "All" : CATEGORY_LABEL[k]} {k === "all" ? r.data!.rules.length : r.data!.rules.filter((x) => x.category === k).length}</button>))}
          </div>
          <div className="max-h-[560px] overflow-auto">
            <table className={tableCls} data-testid="review-rules-table">
              <thead className="sticky top-0 bg-surface"><tr>{["Rule", "Tests", "Threshold", "Severity", "On failure", "Reference", "Approval"].map((h) => <th key={h} className={thCls}>{h}</th>)}</tr></thead>
              <tbody>{rows.map((x) => (
                <tr key={x.id}>
                  <td className={cn(tdCls, "whitespace-normal")}><span className="font-medium text-text-primary">{x.title}</span><span className="block text-[10px] text-text-muted">{x.id} · {CATEGORY_LABEL[x.category]}</span></td>
                  <td className={cn(tdCls, "min-w-[240px] whitespace-normal text-text-secondary")}>{x.tests}</td>
                  <td className={cn(tdCls, "whitespace-normal")}>{thr(x.threshold, x.unit)}</td>
                  <td className={tdCls}>{x.severity ? <Chip tone={SEVERITY_TONE[x.severity as Severity]}>{x.severity}</Chip> : "–"}</td>
                  <td className={tdCls}>{x.on_fail === "exception" ? "Exception" : "Contradicted"}</td>
                  <td className={cn(tdCls, "min-w-[160px] whitespace-normal text-text-secondary")}>{x.crm_article}{x.policy_ref ? <span className="block text-[11px] text-text-muted">{x.policy_ref}</span> : null}</td>
                  <td className={cn(tdCls, "whitespace-normal")}>{x.doa_rank ? DOA[x.doa_rank] ?? `Level ${x.doa_rank}` : "–"}</td>
                </tr>))}</tbody>
            </table>
          </div>
        </>) : null}
    </Section>
  );
}
