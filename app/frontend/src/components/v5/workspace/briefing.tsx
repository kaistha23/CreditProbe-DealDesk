"use client";

/**
 * PLAN_R9 G4: the Workspace as an Intelligence Briefing.
 *
 * Header (who the reader is, today, the book's as-of), a KPI band, "What our
 * intelligence found this morning", dashboard cards by type of work, four
 * Plotly charts each with its (i), and Mail in a slim side panel. Figures come
 * from the Early Warning service — the same SAR-million books the Cockpit,
 * Borrower 360 and Lenses read — and the work items from the Workspace service.
 */

import Link from "next/link";
import * as React from "react";
import { ArrowUpRight, ClipboardCheck, FileText, Gavel, Mail, Radar } from "lucide-react";

import { Card } from "@/components/ui/card";
import { ChartInfo } from "@/components/v5/core/chart-explain";
import { KpiRow } from "@/components/v5/core/kpi-row";
import { PoweredBy } from "@/components/v5/core/powered-by";
import { useCoreAuth } from "@/components/v5/core/auth";
import { Plot } from "@/components/v5/ews/plot";
import { cn } from "@/lib/utils";
import {
  type Book, type BookSnapshot, type PeriodPoint, eclMovementFigure, findings, kpis, money,
  stageFromRows, stageMixFigure,
} from "@/lib/v5/briefing";
import { type CustomerRow, ews, ewsOrigin } from "@/lib/v5/ews";
import { type Home, useWs, when, ws } from "@/lib/v5/workspace";

import { ErrorBox, Loading } from "./parts";

/** Stage mix (facility level, EAD and ECL by IFRS 9 stage) for one period: the Early Warning grid summary. */
async function feedStage(book: Book, period: string): Promise<Record<string, unknown>[]> {
  const r = await fetch(`${ewsOrigin()}/api/v1/ews-domain/workspace/grid/query`, {
    method: "POST", credentials: "include", cache: "no-store", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ domain: book, period, limit: 1 }),
  });
  if (!r.ok) return [];
  const body = (await r.json().catch(() => null)) as { summary?: { stage_mix?: Record<string, unknown>[] } } | null;
  return body?.summary?.stage_mix ?? [];
}

/** P4 Accepted Risk Watch when the Early Warning service serves it (Session C); null otherwise. */
async function loadWatch(): Promise<BookSnapshot["watch"]> {
  try {
    const r = await fetch(`${ewsOrigin()}/api/v1/ews/intel/watch`, { credentials: "include", cache: "no-store" });
    if (!r.ok) return null;
    const w = (await r.json()) as { names: number; escalations: number; items?: { missed: number; due: number };
      clients?: { watch_id: string; name: string; escalation?: { escalate: boolean; why: string } }[] };
    const top = (w.clients ?? []).filter((c) => c.escalation?.escalate).slice(0, 3)
      .map((c) => ({ id: c.watch_id, name: c.name, why: c.escalation?.why ?? "" }));
    return { names: w.names ?? 0, escalations: w.escalations ?? 0, missed: w.items?.missed ?? 0, due: w.items?.due ?? 0, top };
  } catch {
    return null;
  }
}

async function loadSnapshot(book: Book): Promise<{ snap: BookSnapshot; critical: CustomerRow[]; crmTop: { title: string; detail: string; id: string }[] }> {
  const meta = await ews.meta(book);
  const periods = meta.periods.slice(-4);
  const [levels, stages, crm, crit, watch] = await Promise.all([
    Promise.all(periods.map((p) => ews.level({ domain: book, period: p }))),
    Promise.all(periods.map((p) => feedStage(book, p).catch(() => []))),
    ews.crm(book).catch(() => null),
    ews.customers({ domain: book, band_min: "critical", limit: 3 }).catch(() => null),
    book === "corporate" ? loadWatch() : Promise.resolve(null),
  ]);
  const cur = levels[levels.length - 1];
  const prev = levels.length > 1 ? levels[levels.length - 2] : null;
  const trend: PeriodPoint[] = levels.map((l, i) => ({
    period: l.period, stage: stageFromRows(stages[i]),
    critical: l.headline.critical, high: l.headline.high, moderate: l.headline.moderate, low: l.headline.low,
    ecl: l.headline.ecl, exposure: l.headline.exposure,
  }));
  const topArt = crm ? [...crm.by_article].sort((a, b) => b.breaches - a.breaches)[0] : null;
  const reason = cur.top_reasons[0];
  const snap: BookSnapshot = {
    book, period: cur.period, priorPeriod: prev?.period ?? (cur.prior_period || null), moneyUnit: cur.money_unit,
    exposure: cur.headline.exposure, ecl: cur.headline.ecl, prevEcl: prev?.headline.ecl ?? cur.previous?.ecl ?? null,
    critical: cur.headline.critical, high: cur.headline.high, warnedExposure: cur.headline.exposure_warned,
    topReason: reason ? { name: reason.name, customers: reason.customers, change: reason.change } : null,
    stage: trend[trend.length - 1].stage,
    // ECL change per segment against the prior period's own level (the service's movement does not carry ECL).
    segments: cur.children.map((c) => {
      const before = prev?.children.find((x) => x.key === c.key || x.label === c.label);
      return { label: c.label, exposure: c.exposure, ecl: c.ecl, severe: c.exposure_severe,
               eclChange: before ? c.ecl - before.ecl : typeof c.movement?.ecl === "number" ? c.movement.ecl : null };
    }),
    trend,
    crm: crm ? { breaches: crm.breaches, high: crm.high, checksInBreach: crm.checks_in_breach,
                 topArticle: topArt?.article ?? null, topTitle: topArt?.title ?? null, shortfall: crm.shortfall_sar_mn } : null,
    watch,
  };
  return { snap, critical: crit?.customers ?? [],
           crmTop: (crm?.top ?? []).slice(0, 3).map((b) => ({ id: b.check_id + b.entity_id, title: `${b.borrower_id || b.entity_id} · ${b.title}`, detail: b.detail })) };
}

const EXPLAIN = {
  stage: { shows: "The share of exposure in Stage 1, 2 and 3 for the last four periods.", formula: ["Stage k share = exposure in Stage k / total exposure"],
           read: "Each bar is one period and adds to 100%.", lookFor: "Stage 2 and 3 growing period on period: credit quality is migrating." },
  ecl: { shows: "How ECL moved from the prior period to now, by segment.", formula: ["Bar = ECL change of the segment", "Last bar = ECL now"],
         read: "Red bars added ECL, green bars released it.", lookFor: "One segment driving most of the movement." },
  ews: { shows: "Customers in each early warning bucket over the last four periods.", formula: ["Bucket = worst early warning band of the customer"],
         read: "One line per bucket.", lookFor: "Critical and High rising while Low falls." },
  sector: { shows: "The largest segments of the book by exposure.", formula: ["Exposure = sum of EAD in the segment, SAR m"],
            read: "Longest bar is the largest concentration; hover shows the share of the book.", lookFor: "One segment dominating the book." },
};

export function IntelligenceBriefing() {
  const { effective } = useCoreAuth();
  const books = (effective?.books?.length ? effective.books : ["corporate", "retail"]) as Book[];
  const [book, setBook] = React.useState<Book>(books[0] ?? "corporate");
  const [loaded, setLoaded] = React.useState<Awaited<ReturnType<typeof loadSnapshot>> | null>(null);
  const [failed, setFailed] = React.useState<{ book: Book; error: string } | null>(null);
  const home = useWs(() => ws.home(), `home|${effective?.username ?? ""}`);

  React.useEffect(() => {
    let live = true;
    loadSnapshot(book).then((s) => { if (live) setLoaded(s); },
                            (e) => { if (live) setFailed({ book, error: String(e?.message ?? e) }); });
    return () => { live = false; };
  }, [book]);

  // Only the selected book's results are shown; switching books shows the loader until its own arrive.
  const state = loaded && loaded.snap.book === book ? loaded : null;
  const error = failed && failed.book === book && !state ? failed.error : null;
  const first = (effective?.name ?? "").split(" ")[0] || effective?.username || "";
  const role = [effective?.title || effective?.role, effective?.department].filter(Boolean).join(", ");
  const today = new Date().toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" });

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_280px]" data-testid="ws-briefing">
      <div className="min-w-0 space-y-6">
        <header className="flex flex-wrap items-end gap-4">
          <div className="min-w-0">
            <h1 className="text-[26px] font-semibold tracking-tight text-text-primary" data-testid="ws-welcome">
              Welcome, {first}{role ? <span className="font-normal text-text-secondary"> · {role}</span> : null}
            </h1>
            <p className="mt-1 text-sm text-text-muted" data-testid="ws-asof">
              {today}{state ? <> · book as of <b className="text-text-secondary">{state.snap.period}</b></> : null}
            </p>
          </div>
          {books.length > 1 ? (
            <div className="ml-auto inline-flex rounded-md border border-border p-0.5" role="group" aria-label="Book" data-testid="ws-book-toggle">
              {books.map((b) => (
                <button key={b} type="button" onClick={() => setBook(b)} aria-pressed={book === b} data-testid={`ws-book-${b}`}
                        className={cn("rounded px-3 py-1 text-xs font-medium capitalize", book === b ? "bg-accent-muted text-accent" : "text-text-secondary hover:text-text-primary")}>
                  {b}
                </button>
              ))}
            </div>
          ) : null}
        </header>

        {error ? <ErrorBox error={error} /> : null}
        {!state && !error ? <Loading what="Preparing this morning's briefing…" /> : null}
        {state ? <BriefingBody snap={state.snap} critical={state.critical} crmTop={state.crmTop} home={home.data} book={book} /> : null}
      </div>
      <MailPanel home={home.data} />
    </div>
  );
}

function BriefingBody({ snap, critical, crmTop, home, book }: {
  snap: BookSnapshot; critical: CustomerRow[]; crmTop: { id: string; title: string; detail: string }[]; home: Home | null; book: Book;
}) {
  const band = kpis(snap);
  const found = findings(snap);
  const approvals = [...(home?.tasks.open ?? []).map((t) => ({ id: `t${t.id}`, title: t.title, href: t.href })),
                     ...(home?.tasks.assignments ?? []).map((a) => ({ id: a.id, title: a.title, href: a.href }))];
  const reviews = (home?.reviews.items ?? []).map((r) => ({ id: r.id, title: r.title, href: r.href }));

  return (
    <>
      {/* PLAN_R10 S6 / G-TILES: four tiles, one row (shared KpiRow). */}
      <KpiRow testId="ws-kpis" tiles={band.map((k) => ({
        label: k.label, value: k.value, sub: k.sub, href: k.href, testId: `ws-kpi-${k.key}`,
        tone: k.tone === "bad" ? "negative" : k.tone === "warn" ? "warning" : "neutral",
      }))} />

      <section className="rounded-xl border border-border bg-surface p-5" data-testid="ws-findings">
        <div className="flex flex-wrap items-baseline gap-3">
          <h2 className="text-base font-semibold text-text-primary">What our intelligence found this morning</h2>
        </div>
        <ol className="mt-3 divide-y divide-border">
          {found.slice(0, 5).map((f) => (
            <li key={f.id} className="flex flex-wrap items-start gap-3 py-3" data-testid={`ws-finding-${f.id}`}>
              <span className="mt-0.5 w-40 shrink-0 whitespace-nowrap text-lg font-bold tabular-nums text-text-primary">{f.figure}</span>
              <div className="min-w-0 flex-1 space-y-1.5">
                <p className="text-sm text-text-primary">{f.headline}</p>
                <PoweredBy pack={f.pack} rule={f.rule || null} article={f.article ?? null} confidence="high" compact className="inline-flex border-transparent bg-transparent px-0 py-0" testId={`ws-finding-${f.id}-pb`} />
              </div>
              <Link href={f.href} className="inline-flex shrink-0 items-center gap-1 text-xs font-medium text-accent hover:underline">
                {f.action}<ArrowUpRight className="size-3" aria-hidden />
              </Link>
            </li>
          ))}
        </ol>
      </section>

      <section className="grid gap-4 md:grid-cols-2 2xl:grid-cols-4" data-testid="ws-cards">
        <WorkCard icon={ClipboardCheck} title="Approvals" count={approvals.length} href="/workspace?tab=inbox&kind=assignment"
                  rows={approvals} testId="ws-card-approvals" />
        <WorkCard icon={Radar} title="EWS escalations" count={snap.critical} href="/early-warning"
                  rows={critical.map((c) => ({ id: c.customer_id, title: `${c.customer_name ?? c.customer_id} · ${money(c.exposure)}`,
                    href: `/borrower-360?domain=${book}&customer_id=${c.customer_id}&period=${snap.period}&tab=ews` }))}
                  testId="ws-card-ews" />
        <WorkCard icon={Gavel} title="CBUAE breaches" count={snap.crm?.breaches} href="/early-warning"
                  rows={crmTop.map((b) => ({ id: b.id, title: b.title, href: "/early-warning" }))} testId="ws-card-crm" />
        <WorkCard icon={FileText} title="Board & committee packs" count={reviews.length} href="/playbook"
                  rows={reviews} empty="No packs awaiting your review." testId="ws-card-packs" />
      </section>

      <section className="grid gap-4 lg:grid-cols-2" data-testid="ws-charts">
        <ChartCard title="Stage mix trend" explain={EXPLAIN.stage} fig={stageMixFigure(snap)} testId="ws-chart-stage" />
        <ChartCard title="ECL movement" explain={EXPLAIN.ecl} fig={eclMovementFigure(snap)} testId="ws-chart-ecl" />
      </section>
    </>
  );
}

function WorkCard({ icon: Icon, title, count, href, rows, empty = "Nothing waiting.", testId }: {
  icon: React.ComponentType<{ className?: string }>; title: string; count?: number | null; href: string;
  rows: { id: string; title: string; href: string }[]; empty?: string; testId: string;
}) {
  return (
    <Card className="flex flex-col p-4" data-testid={testId}>
      <div className="flex items-center gap-2">
        <Icon className="size-4 text-accent" aria-hidden />
        <h3 className="text-sm font-semibold text-text-primary">{title}</h3>
        {typeof count === "number" ? <span className="ml-auto text-lg font-bold tabular-nums text-text-primary" data-testid={`${testId}-count`}>{count.toLocaleString("en-US")}</span> : null}
      </div>
      <ul className="mt-2 flex-1 space-y-1">
        {rows.slice(0, 3).map((r) => (
          <li key={r.id}>
            <Link href={r.href} className="block truncate rounded px-1 py-1 text-[13px] text-text-secondary hover:bg-surface-hover hover:text-text-primary">{r.title}</Link>
          </li>
        ))}
        {rows.length === 0 ? <li className="px-1 py-1 text-xs text-text-muted">{empty}</li> : null}
      </ul>
      <Link href={href} className="mt-2 inline-flex items-center gap-1 self-start text-xs font-medium text-accent hover:underline" data-testid={`${testId}-open`}>
        Open<ArrowUpRight className="size-3" aria-hidden />
      </Link>
    </Card>
  );
}

function ChartCard({ title, explain, fig, testId }: {
  title: string; explain: typeof EXPLAIN.stage; fig: { data: Record<string, unknown>[]; layout: Record<string, unknown> }; testId: string;
}) {
  return (
    <Card className="p-4" data-testid={testId}>
      <div className="mb-1 flex items-center gap-2">
        <h3 className="text-sm font-semibold text-text-primary">{title}</h3>
        <ChartInfo title={title} explain={explain} />
      </div>
      <Plot data={fig.data} layout={fig.layout} height={260} ariaLabel={title} filename={testId} />
    </Card>
  );
}

function MailPanel({ home }: { home: Home | null }) {
  const items = home?.mail.items ?? [];
  return (
    <aside className="space-y-2 xl:sticky xl:top-4 xl:self-start" data-testid="ws-mail-panel">
      <div className="flex items-center gap-2">
        <Mail className="size-4 text-accent" aria-hidden />
        <h2 className="text-sm font-semibold text-text-primary">Mail</h2>
        <span className="ml-auto text-xs text-text-muted">{home ? `${home.mail.unread} unread` : ""}</span>
      </div>
      <ul className="divide-y divide-border rounded-xl border border-border bg-surface">
        {items.slice(0, 8).map((m) => (
          <li key={m.id}>
            <Link href={m.href} className="block px-3 py-2.5 hover:bg-surface-hover">
              <span className={cn("block truncate text-[13px]", m.read ? "text-text-secondary" : "font-semibold text-text-primary")}>{m.title}</span>
              <span className="text-[11px] text-text-muted">{when(m.created_at)}</span>
            </Link>
          </li>
        ))}
        {home && items.length === 0 ? <li className="px-3 py-3 text-xs text-text-muted">No mail.</li> : null}
      </ul>
      <Link href="/messages" className="inline-flex items-center gap-1 text-xs font-medium text-accent hover:underline">Open Mail<ArrowUpRight className="size-3" aria-hidden /></Link>
    </aside>
  );
}
