"use client";

/**
 * My workspace as each user's home page (PLAN_R3 S3-4).
 *
 * One read of what is waiting on the signed-in user: tasks and assignments,
 * mentions, unread mail, reports awaiting their review (Playbook), Early
 * Warning alerts on the books they cover, their analyses, investigations and
 * projects, and what changed recently. It does not repeat Mail or the module
 * pages: every list is short and every row opens the page that owns it.
 */

import Link from "next/link";
import * as React from "react";
import { AlertTriangle, AtSign, ClipboardList, FileCheck2, FolderKanban, Mail, Microscope, Sigma } from "lucide-react";

import { Card } from "@/components/ui/card";
import { type CustomerRow, type DomainId, type Level, ews } from "@/lib/v5/ews";
import { type Home, type HomeItem, type InboxItem, useWs, when, ws } from "@/lib/v5/workspace";

import { edition } from "@/lib/navigation";
import { type CardRow, r12Api } from "@/lib/v5/dealdesk-r12";

import { Empty, ErrorBox, Loading, SectionTitle, StatusPill } from "./parts";

const KIND_HREF: Record<string, string> = { analysis: "/analyses", investigation: "/investigations", project: "/projects",
                                            document: "/documents" };

/** Deal Desk edition: the deals waiting on me, from Deal Desk's landing cards (no Early Warning service runs). */
function useMyDeals(viewer: string, name: string) {
  const [rows, setRows] = React.useState<CardRow[] | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  React.useEffect(() => {
    if (edition() !== "dealdesk") return;
    let live = true;
    r12Api.cards().then((c) => {
      if (!live) return;
      const all = c.cards.filter((x) => x.key === "to_review" || x.key === "in_review").flatMap((x) => x.rows);
      const me = name.trim().toLowerCase();
      const own = me ? all.filter((r) => (r.rm ?? "").trim().toLowerCase() === me) : [];
      setRows(own.length ? own : all);
    }, (e) => { if (live) setError(String(e?.message ?? e)); });
    return () => { live = false; };
  }, [viewer, name]);
  return { data: rows, error };
}

/** Early Warning on the books I cover: the headline and the critical names with the most exposure. */
function useAlerts(booksKey: string, viewer: string) {
  const [state, setState] = React.useState<{ book: DomainId; level: Level; top: CustomerRow[] }[] | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  React.useEffect(() => {
    if (!booksKey || edition() === "dealdesk") return;
    let live = true;
    Promise.all(booksKey.split(",").filter((b): b is DomainId => b === "corporate" || b === "retail").map(async (book) => {
      const [level, list] = await Promise.all([ews.level({ domain: book }),
                                               ews.customers({ domain: book, band_min: "critical", limit: 5 })]);
      return { book, level, top: list.customers };
    })).then((x) => { if (live) setState(x); }).catch((e) => { if (live) setError(String(e?.message ?? e)); });
    return () => { live = false; };
  }, [booksKey, viewer]);
  return { data: state, error };
}

export function HomeOverview({ viewer, onInbox }: { viewer: string; onInbox: (kind: string) => void }) {
  const home = useWs(() => ws.home(), `home|${viewer}`);
  const h = home.data;
  const booksKey = h ? h.user.books.join(",") : "";
  const books = h?.user.books;
  const alerts = useAlerts(booksKey, viewer);
  const dd = edition() === "dealdesk";
  const deals = useMyDeals(viewer, h?.user?.name ?? "");
  if (home.error) return <ErrorBox error={home.error} />;
  if (!h) return <Loading what="Gathering what is waiting on you…" />;
  const critical = (alerts.data ?? []).reduce((n, a) => n + (a.level.headline.critical ?? 0), 0);

  return (
    <div className="space-y-6" data-testid="ws-home-overview">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Tile icon={ClipboardList} label="My tasks" value={h.tasks.total} testId="ws-home-tasks-count"
              onClick={() => document.getElementById("ws-home-tasks")?.scrollIntoView({ behavior: "smooth" })} />
        <Tile icon={AtSign} label="Unread mentions" value={h.mentions.unread} testId="ws-home-mentions-count"
              onClick={() => onInbox("mention")} />
        <Tile icon={Mail} label="Unread mail" value={h.mail.unread} href="/messages" testId="ws-home-mail-count" />
        <Tile icon={FileCheck2} label="Reports to review" value={h.reviews.available ? h.reviews.items.length : "—"}
              href="/playbook" testId="ws-home-reviews-count" />
        {dd ? (
          <Tile icon={AlertTriangle} label="Deals waiting on me" value={deals.data ? deals.data.length : "…"}
                href="/deal-desk" testId="ws-home-deals-count" tone="warn" />
        ) : (
          <Tile icon={AlertTriangle} label="Critical on Early Warning" value={alerts.data ? critical : "…"}
                href={`/early-warning?domain=${books?.[0] ?? "corporate"}`} testId="ws-home-ews-count" tone="warn" />
        )}
        <Tile icon={FolderKanban} label="My projects" value={h.mine.counts.projects} href="/projects" testId="ws-home-projects-count" />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Panel id="ws-home-tasks" title="My tasks and assignments" link={{ href: "/projects", label: "All projects" }}>
          {h.tasks.open.length === 0 && h.tasks.assignments.length === 0 ? <Empty>No open tasks.</Empty> : (
            <ul className="divide-y divide-border">
              {h.tasks.open.map((t) => (
                <Row key={`t${t.id}`} href={t.href} testId="ws-home-task" title={t.title}
                     meta={`${t.project.name} · ${t.status.replace("_", " ")}`} />
              ))}
              {h.tasks.assignments.map((a) => <InboxRow key={a.id} item={a} testId="ws-home-assignment" />)}
            </ul>
          )}
        </Panel>
        <Panel id="ws-home-mentions" title="Mentions" link={{ onClick: () => onInbox("mention"), label: "All mentions" }}>
          {h.mentions.items.length === 0 ? <Empty>Nobody has mentioned you.</Empty> : (
            <ul className="divide-y divide-border">
              {h.mentions.items.map((m) => <InboxRow key={m.id} item={m} testId="ws-home-mention" />)}
            </ul>
          )}
        </Panel>
        <Panel id="ws-home-mail" title="Unread mail" link={{ href: "/messages", label: "Open Mail" }}>
          {h.mail.items.length === 0 ? <Empty>No unread mail.</Empty> : (
            <ul className="divide-y divide-border">
              {h.mail.items.map((m) => <InboxRow key={m.id} item={m} testId="ws-home-mail-row" />)}
            </ul>
          )}
        </Panel>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel id="ws-home-reviews" title="Reports awaiting my review" link={{ href: "/playbook", label: "Playbook" }}>
          {!h.reviews.available ? (
            <Empty>Playbook is temporarily unavailable.</Empty>
          ) : h.reviews.items.length === 0 ? <Empty>No report is waiting on your review.</Empty> : (
            <ul className="divide-y divide-border">
              {h.reviews.items.map((r) => (
                <Row key={r.id} href={r.href} testId="ws-home-review" title={r.title}
                     meta={`${r.owner?.name ?? ""}${r.due_date ? ` · due ${r.due_date}` : ""}`} right={<StatusPill status={r.status} />} />
              ))}
            </ul>
          )}
        </Panel>
        {dd ? (
        <Panel id="ws-home-deals" title="My deals in Deal Desk" link={{ href: "/deal-desk", label: "Deal Desk" }}>
          {deals.error ? <ErrorBox error={deals.error} /> : !deals.data ? <Loading /> : deals.data.length === 0 ? <Empty>No deal is waiting on you.</Empty> : (
            <ul className="divide-y divide-border">
              {deals.data.slice(0, 8).map((r) => (
                <Row key={r.proposal_id} testId="ws-home-deal" href={r.href}
                     title={`${r.proposal_id} · ${r.obligor_name}`}
                     meta={`${r.state_label}${r.amount_sar_mn != null ? ` · SAR ${r.amount_sar_mn.toLocaleString("en-US", { maximumFractionDigits: 1 })}m` : ""}${r.queries_open ? ` · ${r.queries_open} open quer${r.queries_open === 1 ? "y" : "ies"}` : ""}${r.committee_date ? ` · committee ${r.committee_date}` : ""}`} />
              ))}
            </ul>
          )}
        </Panel>
        ) : (
        <Panel id="ws-home-ews" title="Early Warning on my portfolio" link={{ href: "/early-warning", label: "Early Warning" }}>
          {alerts.error ? <ErrorBox error={alerts.error} /> : !alerts.data ? <Loading /> : (
            <div className="divide-y divide-border">
              {alerts.data.map((a) => (
                <div key={a.book} data-testid={`ws-home-ews-${a.book}`}>
                  <p className="border-b border-border bg-surface-hover/40 px-3 py-2 text-xs text-text-secondary">
                    <span className="font-semibold capitalize text-text-primary">{a.book}</span> as of {a.level.period}:{" "}
                    <span data-testid={`ws-home-ews-${a.book}-warned`}>{a.level.headline.customers_warned.toLocaleString("en-US")}</span> warned ·{" "}
                    <span data-testid={`ws-home-ews-${a.book}-critical`}>{a.level.headline.critical.toLocaleString("en-US")}</span> critical
                  </p>
                  <ul className="divide-y divide-border">
                    {a.top.map((c) => (
                      <Row key={c.customer_id} testId="ws-home-ews-name"
                           href={`/borrower-360?domain=${a.book}&customer_id=${c.customer_id}&period=${a.level.period}&tab=ews`}
                           title={`${c.customer_id} ${c.customer_name ?? ""}`.trim()}
                           meta={`score ${c.score} · ${c.band} · SAR ${c.exposure.toLocaleString("en-US", { maximumFractionDigits: 1 })}m`} />
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          )}
        </Panel>
        )}
      </div>

      <div className="grid gap-4 lg:grid-cols-4">
        <MineList title="My analyses" icon={Sigma} items={h.mine.analyses} kind="analysis" />
        <MineList title="My investigations" icon={Microscope} items={h.mine.investigations} kind="investigation" />
        <MineList title="My projects" icon={FolderKanban} items={h.mine.projects} kind="project" />
        <Panel id="ws-home-recent" title="Recent" link={null}>
          {h.recent.length === 0 ? <Empty>Nothing yet.</Empty> : (
            <ul className="divide-y divide-border">
              {h.recent.map((r) => (
                <Row key={`${r.kind}${r.id}`} href={r.href} testId="ws-home-recent-row" title={r.title}
                     meta={`${r.kind} · ${when(r.when)}`} />
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </div>
  );
}

function Tile({ icon: Icon, label, value, href, onClick, testId, tone }: {
  icon: React.ComponentType<{ className?: string }>; label: string; value: React.ReactNode; href?: string;
  onClick?: () => void; testId: string; tone?: "warn";
}) {
  const body = (
    <>
      <span className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.1em] text-text-muted">
        <Icon className={tone === "warn" ? "size-3.5 text-warning" : "size-3.5 text-accent"} />{label}
      </span>
      <span className="mt-1 block text-[22px] font-semibold leading-tight tabular-nums" data-testid={`${testId}-value`}>{value}</span>
    </>
  );
  const cls = "block w-full p-3.5 text-left transition-colors hover:bg-surface-hover";
  return (
    <Card className="p-0" data-testid={testId}>
      {href ? <Link href={href} className={cls}>{body}</Link> : <button type="button" onClick={onClick} className={cls}>{body}</button>}
    </Card>
  );
}

function Panel({ id, title, link, children }: {
  id: string; title: string; link: { href?: string; onClick?: () => void; label: string } | null; children: React.ReactNode;
}) {
  return (
    <section id={id} data-testid={id}>
      <SectionTitle right={link ? (link.href
        ? <Link href={link.href} className="text-xs text-accent hover:underline">{link.label}</Link>
        : <button type="button" onClick={link.onClick} className="text-xs text-accent hover:underline">{link.label}</button>) : null}>
        {title}
      </SectionTitle>
      <Card className="p-0">{children}</Card>
    </section>
  );
}

function Row({ href, title, meta, right, testId }: { href: string; title: string; meta: string; right?: React.ReactNode; testId: string }) {
  return (
    <li data-testid={testId}>
      <Link href={href} className="flex items-center gap-3 px-3 py-2.5 hover:bg-surface-hover">
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium text-text-primary">{title}</span>
          <span className="block truncate text-xs text-text-muted">{meta}</span>
        </span>
        {right}
      </Link>
    </li>
  );
}

function InboxRow({ item, testId }: { item: InboxItem; testId: string }) {
  return <Row href={item.href} testId={testId} title={item.title}
              meta={`${item.actor?.name ?? ""}${item.actor ? " · " : ""}${when(item.created_at)}`} />;
}

function MineList({ title, icon: Icon, items, kind }: {
  title: string; icon: React.ComponentType<{ className?: string }>; items: HomeItem[]; kind: string;
}) {
  return (
    <Panel id={`ws-home-mine-${kind}`} title={title} link={{ href: KIND_HREF[kind], label: "All" }}>
      {items.length === 0 ? <Empty>None yet.</Empty> : (
        <ul className="divide-y divide-border">
          {items.map((i) => (
            <li key={i.id} data-testid={`ws-home-mine-${kind}-item`}>
              <Link href={i.href} className="flex items-center gap-2 px-3 py-2.5 hover:bg-surface-hover">
                <Icon className="size-3.5 shrink-0 text-text-muted" />
                <span className="min-w-0 flex-1 truncate text-sm">{i.title}</span>
                {i.status ? <StatusPill status={i.status} /> : null}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

export type { Home };
