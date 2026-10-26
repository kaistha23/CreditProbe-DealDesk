"use client";

/**
 * PLAN_R9 Session B: P2 SICR & Default Intelligence in Borrower 360.
 *
 * - TopCards (B1): SICR, UTP, EWS Critical/High, Stage 2/3, Restructured, Accepted Risk Watch,
 *   Bank Watchlist, Missing financials; count, exposure and % of book; a click filters the list.
 * - ClassificationPanel (B4): each SICR and UTP reason with its CBUAE CRM article, evidence, value,
 *   date and source, with "Powered by P2".
 * - SendToWhatIf (B5): the filtered list or one borrower, opened in What-If as a frozen population.
 *
 * Nothing is computed here: every figure is the Borrower 360 service's (GET /cards, /classification).
 */

import * as React from "react";
import { useRouter } from "next/navigation";
import { FlaskConical } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { PoweredBy as SharedPoweredBy } from "@/components/v5/core/powered-by";
import { KpiRow, type KpiTile } from "@/components/v5/core/kpi-row";
import { ofNLine } from "@/components/v5/ews/tile-format";
import { InfoPopover } from "@/components/ui/info-popover";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import {
  type BookCard, type BookCards, type Classification, type DomainId, type PoweredBy, type Reason, b360, b360Origin, useB360,
} from "@/lib/v5/b360";
import { count, pct, sar } from "@/lib/v5/ews";

/** "Powered by" (G's shared component): the pack, the rules or articles, a confidence level and the Trace. */
export function PoweredByLine({ p, testId, href }: { p: PoweredBy; testId?: string; href?: string }) {
  const refs = (p.articles?.length ? p.articles : p.rules ?? []).slice(0, 4);
  const conf = (p.confidence || "").toLowerCase();
  return (
    <span className="inline-flex flex-wrap items-center gap-2" data-trace={p.trace}>
      <SharedPoweredBy pack={p.id} article={refs.join(", ") || null}
                 confidence={conf === "high" || conf === "medium" || conf === "low" ? conf : null}
                 trace={{ href: href ?? (typeof window !== "undefined" ? window.location.pathname + window.location.search : null) }}
                 testId={testId ?? "powered-by"} />
    </span>
  );
}

const TILE_KEYS = ["sicr", "utp", "ews_critical", "ews_high", "stage3"];

/** EWS Critical + EWS High as one tile when the service has no combined card (the bands are disjoint). */
function combineCards(a?: BookCard, b?: BookCard): BookCard | undefined {
  if (!a || !b) return a ?? b;
  return { ...a, key: "ews_crit_high", label: "EWS Critical+High", count: a.count + b.count, ead: a.ead + b.ead,
           ecl: a.ecl + b.ecl, pct_book: a.pct_book + b.pct_book };
}

export function TopCards({ domain, period, active, onPick }: {
  domain: DomainId; period: string; active: string; onPick: (card: string) => void;
}) {
  const { data, error } = useB360<BookCards>(() => b360.cards(domain, period), `cards|${domain}|${period}`);
  if (error) return <p className="text-sm text-negative" data-testid="b360-cards-error">{error}</p>;
  if (!data) return <Skeleton className="h-24 w-full" />;
  // PLAN_R10 E2: at most 4 tiles in one row (SICR, UTP, EWS Critical+High, Stage 3), each "n of N · x% of book";
  // every other cohort is a filter chip.
  const byKey = new Map(data.cards.map((c) => [c.key, c] as const));
  const combined = byKey.get("ews_crit_high") ?? combineCards(byKey.get("ews_critical"), byKey.get("ews_high"));
  const tiles = [byKey.get("sicr"), byKey.get("utp"), combined, byKey.get("stage3")].filter((c): c is BookCard => !!c);
  const chips = data.cards.filter((c) => !TILE_KEYS.includes(c.key) && c.key !== "ews_crit_high");
  const N = data.book.count;
  return (
    <div className="space-y-2" data-testid="b360-cards">
      <KpiRow testId="b360-tiles" tiles={tiles.map((c): KpiTile => ({
        label: c.label, value: count(c.count), testId: `b360-card-${c.key}`, active: active === c.key,
        onClick: () => onPick(active === c.key ? "" : c.key),
        sub: `${ofNLine(c.count, N, c.pct_book * 100, "book")} · ${sar(c.ead)}`,
      }))} />
      <div className="flex flex-wrap items-center gap-1.5" data-testid="b360-chips">
        {chips.map((c) => {
          const on = active === c.key;
          return (
            <button key={c.key} type="button" onClick={() => onPick(on ? "" : c.key)} aria-pressed={on}
                    data-testid={`b360-card-${c.key}`} data-count={c.count}
                    title={`${count(c.count)} of ${count(N)} · ${pct(c.pct_book * 100, 1)} of book · ${sar(c.ead)}`}
                    className={cn("rounded-full border px-2.5 py-0.5 text-[11px] transition-colors",
                                  on ? "border-accent bg-accent text-accent-contrast"
                                     : "border-border text-text-secondary hover:border-accent hover:text-text-primary")}>
              {c.label} <b className="tabular-nums">{count(c.count)}</b>
            </button>
          );
        })}
        <span className="ml-auto" />
        <PoweredByLine p={data.powered_by} testId="b360-cards-powered" href={`/borrower-360?domain=${domain}`} />
        <InfoPopover title="Top cards">
          <p>Each card counts the {domain === "corporate" ? "borrowers" : "customers"} on the book at {data.period} (as of {data.as_of}) that meet it,
            with their EAD and its share of the book EAD ({sar(data.book.ead)}). Click a card to filter the list; click again to clear.</p>
          <p>SICR and UTP follow CBUAE CRM Articles 7 and 6: each flagged name carries its reasons, article and evidence in its client card.</p>
        </InfoPopover>
      </div>
    </div>
  );
}

/** PLAN_R10 E2 (less scrolling): the first reasons show; the rest open with "Show all". */
const REASONS_SHOWN = 3;

function ReasonTable({ title, reasons, testId, tone }: { title: string; reasons: Reason[]; testId: string; tone: "warn" | "neg" }) {
  const [all, setAll] = React.useState(false);
  const shown = all ? reasons : reasons.slice(0, REASONS_SHOWN);
  return (
    <div data-testid={testId}>
      <h4 className={cn("text-[13px] font-semibold", tone === "neg" ? "text-negative" : "text-warning")}>
        {title} <span className="font-normal text-text-muted">· {reasons.length ? `${reasons.length} reason${reasons.length > 1 ? "s" : ""}` : "no indicator"}</span>
      </h4>
      {reasons.length ? (
        <div className="mt-1 overflow-x-auto">
          <table className="w-full text-[12px]">
            <thead className="bg-surface-sunken text-left text-[11px] text-text-muted">
              <tr><th className="px-2 py-1">Reason</th><th className="px-2 py-1">CBUAE article</th><th className="px-2 py-1">Value</th>
                <th className="px-2 py-1">Evidence</th><th className="px-2 py-1">Date</th><th className="px-2 py-1">Source</th></tr>
            </thead>
            <tbody>
              {shown.map((r, i) => (
                <tr key={`${r.code}-${i}`} className="border-t border-border/70" data-testid={`${testId}-${r.code}`}>
                  <td className="px-2 py-1.5 font-medium text-text-primary">{r.text}</td>
                  <td className="whitespace-nowrap px-2 py-1.5 font-mono text-[11px]">{r.article}</td>
                  <td className="px-2 py-1.5"><b>{r.value}</b></td>
                  <td className="px-2 py-1.5 text-text-secondary">{r.evidence}</td>
                  <td className="whitespace-nowrap px-2 py-1.5 tabular-nums">{r.date}</td>
                  <td className="px-2 py-1.5 text-text-secondary">{r.source}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {reasons.length > REASONS_SHOWN ? (
            <button type="button" onClick={() => setAll(!all)} data-testid={`${testId}-all`}
                    className="mt-1 text-[11px] text-accent hover:underline">
              {all ? "Show fewer" : `Show all ${reasons.length} reasons`}
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export function ClassificationPanel({ domain, id, period }: { domain: DomainId; id: string; period: string }) {
  const { data, error } = useB360<Classification>(() => b360.classification(domain, id, period), `cls|${domain}|${id}|${period}`);
  if (error) return <p className="text-sm text-negative" data-testid="b360-classification-error">{error}</p>;
  if (!data) return <Skeleton className="h-24 w-full" />;
  return (
    <Card className="space-y-3 p-4" data-testid="b360-classification">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-[15px] font-semibold text-text-primary">SICR and default judgement</h3>
        <span className="text-[11px] text-text-muted">as of {data.as_of} · Stage <b>{data.stage}</b></span>
        {data.watch_status !== "None" ? (
          <span className="rounded bg-warning-muted px-1.5 py-0.5 text-[10px] text-warning" data-testid="b360-watch-status">{data.watch_status}</span>
        ) : null}
        {data.restructured ? <span className="rounded bg-surface-sunken px-1.5 py-0.5 text-[10px]">Restructured</span> : null}
        <span className="ml-auto"><SendToWhatIf domain={domain} period={data.period} ids={[id]} label="Send to What-If" testId="b360-whatif-one" /></span>
      </div>
      {data.assessment ? (
        <p className="rounded border border-warning/40 bg-warning-muted/40 px-3 py-2 text-[12px] text-text-primary" data-testid="b360-assessment">
          {data.assessment}
        </p>
      ) : null}
      <ReasonTable title="Significant increase in credit risk (SICR)" reasons={data.sicr} testId="b360-sicr" tone="warn" />
      <ReasonTable title="Unlikeliness to pay (UTP)" reasons={data.utp} testId="b360-utp" tone="neg" />
      <PoweredByLine p={data.powered_by} testId="b360-classification-powered"
                     href={`/borrower-360?domain=${domain}&customer_id=${encodeURIComponent(id)}&period=${data.period}`} />
    </Card>
  );
}

/**
 * B5: freeze the population (the filtered list, or the ids given) in the Borrower 360 service and open
 * What-If on it: the thread starts with the population's current ECL and runs stresses against it.
 */
export function SendToWhatIf({ domain, period, ids, query, label, testId }: {
  domain: DomainId; period: string; ids?: string[]; query?: Record<string, string | number>; label: string; testId: string;
}) {
  const router = useRouter();
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const send = async () => {
    setBusy(true);
    setError("");
    try {
      const res = await fetch(`${b360Origin()}/api/v1/b360/cohort`, {
        method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ domain, period, ids: ids ?? [], query: query ?? {} }),
      });
      if (!res.ok) throw new Error((await res.json().catch(() => ({})))?.detail ?? `The population could not be frozen (${res.status}).`);
      const c = (await res.json()) as { object_id: string };
      router.push(`/what-if?domain=${domain}&cohort=${encodeURIComponent(c.object_id)}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  };
  return (
    <span className="inline-flex items-center gap-2">
      <Button size="sm" variant="outline" onClick={send} disabled={busy} data-testid={testId}>
        <FlaskConical aria-hidden /> {busy ? "Opening What-If…" : label}
      </Button>
      {error ? <span className="text-[11px] text-negative" role="alert">{error}</span> : null}
    </span>
  );
}
