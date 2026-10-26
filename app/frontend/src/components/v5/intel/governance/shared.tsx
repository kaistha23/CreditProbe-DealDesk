"use client";

/** R13 IE shared pieces: the writer's lines, the load hook, a compact table, the download button and the method note. */

import * as React from "react";
import { ChevronDown, Download, Loader2 } from "lucide-react";

import { InfoPopover } from "@/components/ui/info-popover";
import { SecondaryButton, tdCls, thCls } from "@/components/v5/dealdesk/kit";
import { cn } from "@/lib/utils";
import type { GovOrigin } from "@/lib/v5/intel-governance";

export const GovOriginContext = React.createContext<GovOrigin>("dealdesk");
export const useGovOrigin = () => React.useContext(GovOriginContext);

export function useGov<T>(load: () => Promise<T>, deps: React.DependencyList): { data: T | null; error: string; busy: boolean } {
  const key = JSON.stringify(deps);
  const [state, set] = React.useState<{ key: string; data: T | null; error: string }>({ key: "", data: null, error: "" });
  React.useEffect(() => {
    let live = true;
    load().then((data) => live && set({ key, data, error: "" }))
      .catch((e: unknown) => live && set({ key, data: null, error: e instanceof Error ? e.message : "Something went wrong." }));
    return () => { live = false; };
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps
  const busy = state.key !== key;
  return { data: busy ? null : state.data, error: busy ? "" : state.error, busy };
}

export function Lines({ lines, testId }: { lines: string[]; testId: string }) {
  return (
    <ul className="space-y-1.5 text-[13px] leading-5 text-text-primary" data-testid={testId}>
      {lines.map((l, i) => (
        <li key={i} className={cn("flex gap-2", i === 0 && "font-medium")}>
          <span aria-hidden className="mt-[7px] size-1.5 shrink-0 rounded-full bg-accent" />
          <span>{l}</span>
        </li>))}
    </ul>
  );
}

export function Loading({ label }: { label: string }) {
  return <p className="flex items-center gap-2 py-6 text-[13px] text-text-muted"><Loader2 size={14} className="animate-spin" />{label}</p>;
}

export function Failure({ message }: { message: string }) {
  return <p className="rounded-md border border-negative/30 bg-negative-muted px-3 py-2 text-[13px] text-negative" role="alert">{message}</p>;
}

export function DownloadButton({ label, run, testId }: { label: string; run: () => Promise<void>; testId: string }) {
  const [busy, setBusy] = React.useState(false);
  const [err, setErr] = React.useState("");
  return (
    <span className="inline-flex items-center gap-2">
      <SecondaryButton data-testid={testId} disabled={busy}
                       onClick={async () => { setBusy(true); setErr(""); try { await run(); } catch (e) { setErr(e instanceof Error ? e.message : "Download failed."); } finally { setBusy(false); } }}>
        {busy ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />}{label}
      </SecondaryButton>
      {err ? <span className="text-[12px] text-negative">{err}</span> : null}
    </span>
  );
}

export function MethodNote({ method, data, title }: { method?: string; data: string; title: string }) {
  return (
    <InfoPopover title={`${title}: method and data`} align="right">
      {method ? <p className="mb-2">{method}</p> : null}
      <p className="text-text-muted">{data}</p>
    </InfoPopover>
  );
}

export function Th({ children, right, className }: { children: React.ReactNode; right?: boolean; className?: string }) {
  return <th className={cn(thCls, right && "text-right", className)}>{children}</th>;
}

export function Td({ children, right, className, title }: { children: React.ReactNode; right?: boolean; className?: string; title?: string }) {
  return <td title={title} className={cn(tdCls, right && "text-right", className)}>{children}</td>;
}

export function Stat({ label, value, sub, tone, testId }: { label: string; value: React.ReactNode; sub?: React.ReactNode; tone?: "negative" | "positive"; testId?: string }) {
  return (
    <div className="min-w-0 rounded-md border border-border bg-surface px-3 py-2" data-testid={testId}>
      <p className="truncate text-[11px] font-medium uppercase tracking-[0.08em] text-text-muted">{label}</p>
      <p className={cn("truncate text-[18px] font-semibold tabular-nums leading-6",
                       tone === "negative" ? "text-negative" : tone === "positive" ? "text-positive" : "text-text-primary")}>{value}</p>
      {sub ? <p className="truncate text-[11px] tabular-nums text-text-secondary">{sub}</p> : null}
    </div>
  );
}

/** A folded block: one line with a chevron; opens in place (no first-screen clutter). */
export function Fold({ title, meta, children, testId }: { title: string; meta?: React.ReactNode; children: React.ReactNode; testId: string }) {
  const [open, setOpen] = React.useState(false);
  return (
    <div className="rounded-md border border-border" data-testid={testId} data-open={open ? "true" : "false"}>
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} data-testid={`${testId}-toggle`}
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-[13px] font-semibold text-text-primary hover:bg-surface-hover">
        <ChevronDown size={14} className={cn("text-text-muted transition-transform", !open && "-rotate-90")} />
        {title}
        {meta ? <span className="ml-auto text-[12px] font-normal text-text-muted">{meta}</span> : null}
      </button>
      {open ? <div className="border-t border-border px-3 py-2">{children}</div> : null}
    </div>
  );
}
