"use client";

/**
 * The Workspace briefing in the Deal Desk edition: the RM's Deal Desk home.
 *
 * "What is waiting on me, in Deal Desk": my deals and their stage (from the Deal Desk landing cards, filtered to the
 * reader where the card rows carry an RM), proposals waiting on me (queries open, to review), conditions due,
 * committee dates, approvals and reports awaiting my review (the Core home), and mail. Noor's Deal Desk brief sits
 * on top. Nothing here reads a service the edition does not run.
 *
 * Reuses Deal Desk's own pieces unchanged: the landing cards' client (r12Api.cards), the conditions line
 * (ConditionsDueLine) and the module brief (NoorModuleBrief).
 */

import * as React from "react";
import Link from "next/link";
import { ArrowUpRight, CalendarClock, ClipboardCheck, FileText, Handshake, MessageSquareWarning } from "lucide-react";

import { useCoreAuth } from "@/components/v5/core/auth";
import { ConditionsDueLine } from "@/components/v5/dealdesk/review-conditions";
import { NoorModuleBrief } from "@/components/noor/module-brief";
import { Card } from "@/components/ui/card";
import { KpiRow } from "@/components/v5/core/kpi-row";
import { type CardRow, type LandingCards, r12Api } from "@/lib/v5/dealdesk-r12";
import { type Home, useWs, ws } from "@/lib/v5/workspace";

import { Loading } from "./parts";
import { paperRowTitle, usePaperRows } from "@/components/v5/dealdesk/paperws/open"; // Round W

const QUEUE_LABEL: Record<string, string> = {
  to_review: "To review", in_review: "In review", committee: "Committee", going_bad: "Going bad", renewals: "Renewals",
  conditions: "Conditions", sme: "SME fast track",
};

function mine(rows: CardRow[], me: { name?: string | null; username?: string | null } | null): CardRow[] {
  const name = (me?.name ?? "").trim().toLowerCase();
  if (!name) return rows;
  const own = rows.filter((r) => (r.rm ?? "").trim().toLowerCase() === name);
  return own.length ? own : rows;   // a reader who holds no deal (an administrator) sees the desk's
}

function fmtAmount(v: number | null): string {
  return v == null ? "" : `SAR ${v.toLocaleString("en-US", { maximumFractionDigits: 1 })}m`;
}

export function DealDeskBriefing() {
  const { effective } = useCoreAuth();
  const home = useWs(() => ws.home(), `home|${effective?.username ?? ""}`);
  const [cards, setCards] = React.useState<LandingCards | null>(null);
  const [failed, setFailed] = React.useState("");
  React.useEffect(() => {
    let live = true;
    r12Api.cards().then((c) => { if (live) setCards(c); }, (e) => { if (live) setFailed(String(e?.message ?? e)); });
    return () => { live = false; };
  }, []);

  const first = (effective?.name ?? "").split(" ")[0] || effective?.username || "";
  const role = [effective?.title || effective?.role, effective?.department].filter(Boolean).join(", ");
  const today = new Date().toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" });

  const byKey = Object.fromEntries((cards?.cards ?? []).map((c) => [c.key, c]));
  const review = mine(byKey.to_review?.rows ?? [], effective);
  const inReview = mine(byKey.in_review?.rows ?? [], effective);
  const committee = (byKey.committee?.rows ?? []).slice().sort((a, b) => (a.committee_date ?? "").localeCompare(b.committee_date ?? ""));
  const queries = [...review, ...inReview].filter((r) => r.queries_open > 0);
  const myDeals = [...review, ...inReview];
  const approvals = [...(home.data?.tasks.open ?? []).map((t) => ({ id: `t${t.id}`, title: t.title, href: t.href })),
                     ...(home.data?.tasks.assignments ?? []).map((a) => ({ id: a.id, title: a.title, href: a.href }))];
  const reviews = (home.data?.reviews.items ?? []).map((r) => ({ id: r.id, title: r.title, href: r.href }));
  const papers = usePaperRows(8, { mine: true }); // Round W

  const tiles = [
    { key: "deals", label: "My deals in hand", value: String(myDeals.length), sub: `${review.length} to review · ${inReview.length} in review`, href: "/deal-desk", testId: "ws-kpi-deals" },
    { key: "queries", label: "Open queries from Credit", value: String(queries.reduce((n, r) => n + r.queries_open, 0)), sub: queries.length ? `on ${queries.length} deal${queries.length === 1 ? "" : "s"}` : "none open", href: "/deal-desk/review", testId: "ws-kpi-queries", tone: queries.length ? "warning" as const : "neutral" as const },
    { key: "committee", label: "Going to committee", value: String(committee.length), sub: committee[0]?.committee_date ? `first ${committee[0].committee_date}` : "next 30 days", href: "/deal-desk?card=committee", testId: "ws-kpi-committee" },
    { key: "conditions", label: "Conditions due", value: String(byKey.conditions?.count ?? 0), sub: byKey.conditions?.sub ?? "", href: "/deal-desk/review?view=conditions", testId: "ws-kpi-conditions", tone: (byKey.conditions?.count ?? 0) ? "warning" as const : "neutral" as const },
  ];

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_280px]" data-testid="ws-briefing" data-edition="dealdesk">
      <div className="min-w-0 space-y-6">
        <header className="flex flex-wrap items-end gap-4">
          <div className="min-w-0">
            <h1 className="text-[26px] font-semibold tracking-tight text-text-primary" data-testid="ws-welcome">
              Welcome, {first}{role ? <span className="font-normal text-text-secondary"> · {role}</span> : null}
            </h1>
            <p className="mt-1 text-sm text-text-muted" data-testid="ws-asof">
              {today}{cards ? <> · Deal Desk as of <b className="text-text-secondary">{cards.as_of}</b></> : null}
            </p>
          </div>
          <div className="ml-auto"><ConditionsDueLine /></div>
        </header>

        {!cards && !failed ? <Loading what="Reading your deals…" /> : null}
        {cards ? <KpiRow testId="ws-kpis" tiles={tiles} /> : null}

        <NoorModuleBrief module="dealdesk" limit={5} />

        <section className="grid gap-4 md:grid-cols-2 2xl:grid-cols-4" data-testid="ws-cards">
          <WorkCard icon={Handshake} title="My deals" count={myDeals.length} href="/deal-desk"
                    rows={myDeals.map((r) => ({ id: r.proposal_id, href: r.href,
                      title: `${r.proposal_id} · ${r.obligor_name} · ${r.state_label}${r.amount_sar_mn != null ? ` · ${fmtAmount(r.amount_sar_mn)}` : ""}` }))}
                    empty="No deal is waiting on you." testId="ws-card-deals" />
          <WorkCard icon={MessageSquareWarning} title="Queries from Credit" count={queries.length} href="/deal-desk/review"
                    rows={queries.map((r) => ({ id: r.proposal_id, href: r.href, title: `${r.proposal_id} · ${r.obligor_name} · ${r.queries_open} open` }))}
                    empty="No open query." testId="ws-card-queries" />
          <WorkCard icon={CalendarClock} title="Committee" count={committee.length} href="/deal-desk?card=committee"
                    rows={committee.map((r) => ({ id: r.proposal_id, href: r.href,
                      title: `${r.committee_date ?? "date tbc"} · ${r.proposal_id} · ${r.obligor_name}` }))}
                    empty="Nothing scheduled." testId="ws-card-committee" />
          <WorkCard icon={ClipboardCheck} title="Approvals and assignments" count={approvals.length} href="/workspace?tab=inbox&kind=assignment"
                    rows={approvals} testId="ws-card-approvals" />
        </section>

        <section className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3" data-testid="ws-cards-2">
          <WorkCard icon={FileText} title="Papers awaiting my review" count={reviews.length} href="/playbook"
                    rows={reviews} empty="No paper awaiting your review." testId="ws-card-packs" />
          {/* Round W: my living documents (credit proposals and business requests), reopened where I left them */}
          <WorkCard icon={FileText} title="My papers in progress" count={papers?.length ?? null} href="/deal-desk"
                    rows={(papers ?? []).map((w) => ({ id: w.ws_id, href: w.href, title: paperRowTitle(w) }))}
                    empty="No credit proposal or business request in progress." testId="ws-card-papers" />
          <WorkCard icon={Handshake} title="Deal Desk work queues" href="/deal-desk"
                    rows={(cards?.cards ?? []).filter((c) => c.available).map((c) => ({ id: c.key, href: c.href,
                      title: `${QUEUE_LABEL[c.key] ?? c.title} · ${c.count}` }))}
                    testId="ws-card-queues" />
        </section>
      </div>
      <MailPanelDd home={home.data} />
    </div>
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
        {rows.slice(0, 4).map((r) => (
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

function MailPanelDd({ home }: { home: Home | null }) {
  const items = home?.mail.items ?? [];
  return (
    <aside className="space-y-2 xl:sticky xl:top-4 xl:self-start" data-testid="ws-mail-panel">
      <div className="flex items-center gap-2">
        <h2 className="text-sm font-semibold text-text-primary">Mail</h2>
        <span className="ml-auto text-xs text-text-muted">{home ? `${home.mail.unread} unread` : ""}</span>
      </div>
      <ul className="divide-y divide-border rounded-xl border border-border bg-surface">
        {items.slice(0, 6).map((m) => (
          <li key={m.id}>
            <Link href={m.href} className="block px-3 py-2 hover:bg-surface-hover">
              <p className="truncate text-[13px] font-medium text-text-primary">{m.title}</p>
              <p className="truncate text-xs text-text-muted">{m.actor?.name ?? m.source}</p>
            </Link>
          </li>
        ))}
        {items.length === 0 ? <li className="px-3 py-3 text-xs text-text-muted">No mail.</li> : null}
      </ul>
      <Link href="/messages" className="inline-flex items-center gap-1 text-xs font-medium text-accent hover:underline">Open Mail<ArrowUpRight className="size-3" aria-hidden /></Link>
    </aside>
  );
}
