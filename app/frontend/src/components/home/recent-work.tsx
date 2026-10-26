"use client";

/**
 * Small cards of recent work under the Ask box (PLAN_R13 Session H). R14 n (K16): one list, newest first, across the
 * Cockpit conversations, the reader's What-If and Deal Desk threads and lenses, so a question just asked anywhere is the
 * first card. Each source is read through its own client; one that cannot be read is left out quietly.
 */

import * as React from "react";

import { withFrom } from "@/components/v5/ui/back-link-model"; // R14 U (K1)
import Link from "next/link";
import { BarChart3, Handshake, MessageSquare, TrendingDown } from "lucide-react";

import type { DomainId, RecentThread } from "@/components/cockpit-v4/client";
import { dealdesk } from "@/lib/v5/dealdesk";
import { lenses } from "@/lib/v5/lenses";
import { recentFirst } from "@/lib/v5/thread-rule";
import { whatif } from "@/lib/v5/whatif";
import { edition } from "@/lib/navigation";

interface WorkCard {
  key: string; kind: "Cockpit" | "What-If" | "Lens" | "Deal Desk"; title: string; when: string; updated: number;
  href?: string; onOpen?: () => void;
}

function ago(ms: number): string {
  if (!Number.isFinite(ms) || ms <= 0) return "";
  const minutes = Math.round((Date.now() - ms) / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return days < 8 ? `${days}d ago` : new Date(ms).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

const ICON = { Cockpit: MessageSquare, "What-If": TrendingDown, Lens: BarChart3, "Deal Desk": Handshake } as const;

export function RecentWork({ threads, onReopen, domain }: {
  threads: RecentThread[] | null; onReopen: (t: RecentThread) => void; domain: DomainId;
}) {
  const [extra, setExtra] = React.useState<WorkCard[]>([]);
  React.useEffect(() => {
    let live = true;
    const dd = edition() === "dealdesk";   // the edition runs neither What-If nor Lenses: Deal Desk threads only
    void Promise.allSettled([dd ? Promise.reject(new Error("not in edition")) : whatif.threads(domain),
                             dd ? Promise.reject(new Error("not in edition")) : lenses.list(domain),
                             dealdesk.deskThreads(dd ? 6 : 3)]).then(([w, l, d]) => {
      if (!live) return;
      const out: WorkCard[] = [];
      if (w.status === "fulfilled") {
        for (const t of w.value.threads.slice(0, 2)) {
          out.push({ key: `w-${t.thread_id}`, kind: "What-If", title: t.title || "What-If thread", when: ago(t.updated_at * 1000),
                     updated: t.updated_at, href: withFrom(`/what-if/thread/${encodeURIComponent(t.thread_id)}`, "ask", "/?tab=ask") });
        }
      }
      if (l.status === "fulfilled") {
        for (const c of l.value.mine.slice(0, 2)) {
          out.push({ key: `l-${c.lens_id}`, kind: "Lens", title: c.name, when: ago(c.updated_at * 1000),
                     updated: c.updated_at, href: withFrom(`/lenses/${encodeURIComponent(c.lens_id)}`, "ask", "/?tab=ask") });
        }
      }
      if (d.status === "fulfilled") {
        for (const t of d.value.threads.slice(0, 3)) {
          out.push({ key: `d-${t.thread_id}`, kind: "Deal Desk", title: t.title, when: ago(t.updated * 1000), updated: t.updated,
                     href: withFrom(t.href, "ask", "/?tab=ask") });  // R14 x: n's desk threads + u's back link (K1, K16)
        }
      }
      setExtra(out);
    });
    return () => { live = false; };
  }, [domain]);
  const cockpit: WorkCard[] = (threads ?? []).slice(0, 4).map((t) => ({
    key: `c-${t.thread_id}`, kind: "Cockpit", title: t.attention_item || t.title || t.last_question,
    when: ago(Date.parse(t.last_activity_at)), updated: Date.parse(t.last_activity_at) / 1000 || 0, onOpen: () => onReopen(t),
  }));
  const cards = recentFirst([...cockpit, ...extra]).slice(0, 6);
  if (!cards.length) return null;
  return (
    <section className="space-y-3" data-testid="home-recent-work" aria-label="Recent work">
      <h2 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-text-muted">Recent work</h2>
      <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
        {cards.map((c) => {
          const Icon = ICON[c.kind];
          const body = (
            <>
              <span className="flex items-center gap-1.5 text-[10.5px] font-medium uppercase tracking-[0.1em] text-text-muted">
                <Icon className="size-3" aria-hidden />{c.kind}
                {c.when ? <span className="ml-auto font-normal normal-case tracking-normal">{c.when}</span> : null}
              </span>
              <span className="mt-1.5 line-clamp-2 text-[13px] leading-snug text-text-primary" dir="auto">{c.title}</span>
            </>
          );
          const cls = "flex h-full flex-col rounded-lg border border-border bg-surface px-3.5 py-3 text-left transition-colors hover:border-border-strong hover:bg-surface-hover focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent";
          return c.href ? (
            <Link key={c.key} href={c.href} className={cls} data-testid="home-work-card" data-kind={c.kind}>{body}</Link>
          ) : (
            <button key={c.key} type="button" onClick={c.onOpen} className={cls} data-testid="home-work-card" data-kind={c.kind}>{body}</button>
          );
        })}
      </div>
    </section>
  );
}
