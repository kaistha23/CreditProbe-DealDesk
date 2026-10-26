"use client";

/**
 * PLAN_R9 C1: Admin → Settings, "Early Warning: PD by warning bucket" (P3). The 12-month default probability of a
 * name in each Early Warning bucket, a management estimate, used by the "ECL impact of current warnings" panel and
 * What-If. Saved by the Early Warning service, versioned with who and when; applied immediately.
 */

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import * as React from "react";

import { Card } from "@/components/ui/card";
import { InfoPopover } from "@/components/ui/info-popover";
import { useEws } from "@/lib/v5/ews";
import { BUCKETS, BUCKET_LABEL, type Bucket, type PdConfig, intel } from "@/lib/v5/risk-intel";

export function EwsPdCard() {
  const params = useSearchParams();
  const ref = React.useRef<HTMLDivElement | null>(null);
  const [tick, setTick] = React.useState(0);
  const { data, error } = useEws<PdConfig>(() => intel.pd(), `pd|${tick}`);
  const [draft, setDraft] = React.useState<Record<Bucket, number> | null>(null);
  const [msg, setMsg] = React.useState("");
  React.useEffect(() => {
    if (params.get("tab") === "ews-pd" && ref.current) ref.current.scrollIntoView({ block: "start" });
  }, [params, data]);
  const values = draft ?? data?.values ?? null;
  const save = async () => {
    if (!values) return;
    setMsg("");
    try {
      const saved = await intel.setPd(values);
      setDraft(null); setTick((t) => t + 1);
      setMsg(`Saved as version ${saved.version}; Early Warning and What-If use it now.`);
    } catch (e) { setMsg(e instanceof Error ? e.message : String(e)); }
  };
  return (
    <div ref={ref} id="ews-pd">
      <Card className="space-y-3 p-4" data-testid="admin-ews-pd">
        <div className="flex items-center gap-2">
          <p className="text-[14px] font-semibold text-text-primary">Early Warning: PD by warning bucket</p>
          <InfoPopover title="PD by warning bucket">
            The probability that a name in each Early Warning bucket defaults within 12 months. It drives the expected ECL
            of current warnings: Σ [p × ECL if defaulted + (1 − p) × current ECL]. A management estimate, reviewed at the
            ECL committee; it must not increase from Critical down to Low.
          </InfoPopover>
          <span className="ml-auto text-[11px] italic text-text-muted">management estimate</span>
        </div>
        {error ? <p className="text-[12px] text-negative">{error}</p> : null}
        {values ? (
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            {BUCKETS.map((b) => (
              <label key={b} className="text-[12px] text-text-muted">{BUCKET_LABEL[b]}
                <span className="mt-0.5 flex items-center gap-1">
                  <input type="number" min={0} max={100} step={1} value={values[b]} data-testid={`admin-ews-pd-${b}`}
                         onChange={(e) => setDraft({ ...values, [b]: Number(e.target.value) })}
                         className="w-20 rounded border border-border bg-surface px-2 py-1 text-[13px] font-semibold text-text-primary" />%
                </span>
              </label>
            ))}
          </div>
        ) : null}
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" onClick={() => void save()} disabled={!draft} data-testid="admin-ews-pd-save"
                  className="rounded-md bg-accent px-3 py-1 text-[12px] text-accent-contrast disabled:opacity-40">Save and apply</button>
          <button type="button" onClick={() => setDraft({ critical: 70, high: 40, moderate: 15, low: 3 })} data-testid="admin-ews-pd-defaults"
                  className="rounded-md border border-border px-3 py-1 text-[12px]">Restore defaults</button>
          <Link href="/early-warning" className="text-[12px] text-accent hover:underline" data-testid="admin-ews-pd-open">Open Early Warning</Link>
          {data ? <span className="text-[11px] text-text-muted">v{data.version} · {data.updated_at ? `${data.updated_at.slice(0, 16).replace("T", " ")} by ${data.updated_by}` : "default"}</span> : null}
        </div>
        {msg ? <p className="text-[12px] text-text-secondary" data-testid="admin-ews-pd-msg">{msg}</p> : null}
      </Card>
    </div>
  );
}
