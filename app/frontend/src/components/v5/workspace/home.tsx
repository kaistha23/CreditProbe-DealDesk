"use client";

/**
 * My workspace and the Inbox: one person's own working state.
 *
 * Not a second dashboard. The Cockpit answers "what is happening in the book";
 * this answers "what is waiting on me": unread conversations, mentions,
 * assignments and notifications, and the work in hand. Every number here is a
 * count of rows the reader can click through to.
 */

import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { AtSign, Bell, ClipboardList, Mail } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { type InboxItem, type InboxKind, KIND_LABEL, useWs, when, ws } from "@/lib/v5/workspace";

import { edition } from "@/lib/navigation";

import { IntelligenceBriefing } from "./briefing";
import { DealDeskBriefing } from "./briefing-dealdesk";
import { HomeOverview } from "./my-home";
import { Empty, ErrorBox, Loading, PageTop, Who, useViewer } from "./parts";

// PLAN_R9 G4: the Intelligence Briefing is the landing view; "My work" keeps the R3 home (?tab=work).
type Tab = "briefing" | "workspace" | "inbox";
const KINDS: InboxKind[] = ["message", "mention", "assignment", "notification"];
const KIND_ICON: Record<InboxKind, React.ComponentType<{ className?: string }>> = {
  message: Mail, mention: AtSign, assignment: ClipboardList, notification: Bell,
};

export function WorkspaceHome() {
  const query = useSearchParams();
  const tab: Tab = query.get("tab") === "inbox" ? "inbox" : query.get("tab") === "work" ? "workspace" : "briefing";
  const kind = (KINDS as string[]).includes(query.get("kind") ?? "") ? (query.get("kind") as InboxKind) : "";
  const viewer = useViewer();
  const [reload, setReload] = React.useState(0);
  const inbox = useWs(() => ws.inbox(), `inbox|${viewer}|${reload}`);

  const go = (next: { tab: Tab; kind?: string }) => {
    const p = new URLSearchParams();
    if (next.tab === "inbox") p.set("tab", "inbox");
    if (next.tab === "workspace") p.set("tab", "work");
    if (next.kind) p.set("kind", next.kind);
    const s = p.toString();
    window.history.pushState(null, "", s ? `?${s}` : window.location.pathname);
  };

  const unread = inbox.data?.unread_total ?? 0;
  return (
    <div className="space-y-5" data-testid="ws-home" data-tour="workspace-home">
      {tab !== "briefing" ? (
        <PageTop eyebrow="Workspace" title="Workspace"
                 about="Your home page: what is waiting on you, what colleagues have sent, and the work in hand." />
      ) : null}
      <div className="flex gap-1 border-b border-border" role="tablist">
        {(["briefing", "workspace", "inbox"] as Tab[]).map((t) => (
          <button key={t} type="button" role="tab" aria-selected={tab === t} data-testid={`ws-tab-${t}`}
                  onClick={() => go({ tab: t })}
                  className={cn("-mb-px border-b-2 px-3 py-2 text-sm font-medium transition-colors",
                                tab === t ? "border-accent text-accent" : "border-transparent text-text-secondary hover:text-text-primary")}>
            {t === "briefing" ? "Briefing" : t === "workspace" ? "My work" : "Inbox"}
            {t === "inbox" && unread > 0 ? (
              <span className="ml-1.5 rounded-full bg-accent px-1.5 py-0.5 text-[10px] font-semibold tabular-nums text-accent-contrast"
                    data-testid="ws-inbox-unread">{unread}</span>
            ) : null}
          </button>
        ))}
      </div>
      {inbox.error ? <ErrorBox error={inbox.error} /> : null}
      {tab === "briefing" ? (
        // Deal Desk edition: the RM's Deal Desk home; the full product: the book's intelligence briefing.
        edition() === "dealdesk" ? <DealDeskBriefing /> : <IntelligenceBriefing />
      ) : tab === "inbox" ? (
        <InboxView items={inbox.data?.items ?? null} counts={inbox.data?.unread} kind={kind} viewer={viewer}
                   onKind={(k) => go({ tab: "inbox", kind: k })} onChanged={() => setReload((n) => n + 1)} />
      ) : (
        <HomeOverview viewer={viewer} onInbox={(k) => go({ tab: "inbox", kind: k })} />
      )}
    </div>
  );
}

function KindIcon({ kind }: { kind: InboxKind }) {
  const Icon = KIND_ICON[kind];
  return (
    <span className="mt-0.5 inline-flex size-7 shrink-0 items-center justify-center rounded-full bg-surface-sunken text-text-secondary">
      <Icon className="size-3.5" />
    </span>
  );
}

function InboxView({ items, counts, kind, viewer, onKind, onChanged }: {
  items: InboxItem[] | null; counts: Record<InboxKind, number> | undefined; kind: InboxKind | "";
  viewer: string; onKind: (k: string) => void; onChanged: () => void;
}) {
  const router = useRouter();
  const [busy, setBusy] = React.useState<string | null>(null);
  const shown = (items ?? []).filter((i) => !kind || i.kind === kind);

  async function open(item: InboxItem) {
    // Stored items are marked read before leaving, so the request is never cut
    // off by the navigation. A conversation marks itself read when it opens.
    if (item.kind !== "message" && !item.read) {
      setBusy(item.id);
      try { await ws.inboxRead(item.id); } catch { /* still open it */ }
    }
    router.push(item.href);
  }

  async function markRead(item: InboxItem) {
    setBusy(item.id);
    try { await ws.inboxRead(item.id); } finally { setBusy(null); onChanged(); }
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-1.5" data-testid="ws-inbox-filters">
        {[{ k: "", label: "All" }, ...KINDS.map((k) => ({ k, label: `${KIND_LABEL[k]}s` }))].map(({ k, label }) => (
          <button key={k || "all"} type="button" onClick={() => onKind(k)} data-testid={`ws-inbox-filter-${k || "all"}`}
                  aria-pressed={kind === k}
                  className={cn("rounded-full px-3 py-1.5 text-xs font-medium transition-colors",
                                kind === k ? "bg-accent-muted text-accent" : "text-text-secondary hover:text-text-primary")}>
            {label}
            {k && counts?.[k as InboxKind] ? <span className="ml-1.5 tabular-nums">{counts[k as InboxKind]}</span> : null}
          </button>
        ))}
      </div>
      {items === null ? <Loading what="Loading the inbox…" /> : shown.length === 0 ? (
        <div data-testid="ws-inbox"><Empty>{kind ? `No ${KIND_LABEL[kind].toLowerCase()}s.` : "Your inbox is empty."}</Empty></div>
      ) : (
        <ul className="divide-y divide-border rounded-lg border border-border bg-surface" data-testid="ws-inbox">
          {shown.map((i) => (
            <li key={i.id} data-testid={`ws-inbox-item-${i.id}`} data-kind={i.kind} data-read={i.read ? "true" : "false"}
                className="flex items-start gap-3 px-4 py-3">
              <span aria-hidden className={cn("mt-2.5 size-2 shrink-0 rounded-full", i.read ? "bg-transparent" : "bg-accent")} />
              <KindIcon kind={i.kind} />
              <button type="button" onClick={() => open(i)} disabled={busy === i.id}
                      className="min-w-0 flex-1 text-left">
                <span className={cn("block text-sm", i.read ? "text-text-primary" : "font-semibold text-text-primary")}>
                  {i.title}
                  {i.unread > 1 ? <span className="ml-1.5 text-xs font-normal text-text-muted">{i.unread} new</span> : null}
                </span>
                <span className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-text-secondary">
                  <span>{KIND_LABEL[i.kind]}</span>
                  <Who person={i.actor} />
                  <span className="text-text-muted">{when(i.created_at)}</span>
                </span>
                {i.body ? <span className="mt-1 block line-clamp-2 text-xs text-text-muted">{i.body}</span> : null}
              </button>
              <span className="flex shrink-0 flex-col items-end gap-1.5">
                {!i.read && i.kind !== "message" ? (
                  <Button size="sm" variant="ghost" onClick={() => markRead(i)} disabled={busy === i.id}
                          data-testid={`ws-inbox-read-${i.id}`}>
                    Mark read
                  </Button>
                ) : null}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
