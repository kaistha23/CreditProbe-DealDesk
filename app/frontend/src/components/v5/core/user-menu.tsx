"use client";

import Link from "next/link";
import * as React from "react";
import { ListChecks, Bell, Eye, Inbox, LogOut, Mail, Settings, X } from "lucide-react";

import { Dropdown } from "@/components/v5/ui/dropdown"; // R14 U (K28)

import { useCoreAuth } from "@/components/v5/core/auth";
import { MAIL_CHANGED, core, mailChanged, mailWhen, useMailCounts, type Notification, type User } from "@/lib/v5/core";
import { cn } from "@/lib/utils";
import { friendlyMessage } from "@/lib/v5/errors";

/** Initials in a circle. */
export function UserAvatar({ user, size = 28 }: { user: Pick<User, "initials" | "name">; size?: number }) {
  return (
    <span aria-hidden style={{ width: size, height: size }}
          className="inline-flex shrink-0 items-center justify-center rounded-full bg-accent-muted text-[10px] font-semibold text-accent">
      {user.initials}
    </span>
  );
}

/** The header's mail bell: the unread count, opening Mail. */
export function MailBell() {
  const { status } = useCoreAuth();
  const counts = useMailCounts(status === "authenticated");
  const unread = counts?.unread ?? 0;
  return (
    <Link href="/messages" aria-label={unread ? `Mail, ${unread} unread` : "Mail"} title="CreditProbe Mail"
          data-testid="header-mail"
          className="relative flex size-8 items-center justify-center rounded-md text-text-muted transition-colors hover:bg-surface-hover hover:text-text-primary">
      <Mail className="size-[15px]" aria-hidden />
      {unread > 0 ? (
        <span data-testid="header-mail-unread"
              className="absolute -right-0.5 -top-0.5 min-w-[16px] rounded-full bg-accent px-1 text-center text-[10px] font-semibold leading-4 text-accent-contrast">
          {unread}
        </span>
      ) : null}
    </Link>
  );
}

/** Notifications from Mail: shares and new messages, each opening its conversation. Polled every 15 s; a new one
 *  also shows a toast for a few seconds and makes the unread badges re-read (the sidebar and the header mail icon). */
export function NotificationBell() {
  const { status } = useCoreAuth();
  const [open, setOpen] = React.useState(false);
  const [items, setItems] = React.useState<Awaited<ReturnType<typeof core.notifications>> | null>(null);
  const [fresh, setFresh] = React.useState<Notification | null>(null);
  const seen = React.useRef<number | null>(null);
  const ref = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (status !== "authenticated") return;
    let live = true;
    const load = () => core.notifications().then((n) => {
      if (!live) return;
      setItems(n);
      const top = n.notifications.reduce((m, x) => Math.max(m, x.id), 0);
      if (seen.current !== null && top > seen.current) {
        const newest = n.notifications.find((x) => x.id === top && !x.read);
        if (newest) { setFresh(newest); mailChanged(); }
      }
      seen.current = Math.max(seen.current ?? 0, top);
    }, () => undefined);
    void load();
    const t = window.setInterval(load, 15000);
    window.addEventListener(MAIL_CHANGED, load);
    return () => { live = false; window.clearInterval(t); window.removeEventListener(MAIL_CHANGED, load); };
  }, [status, open]);
  React.useEffect(() => {
    if (!fresh) return;
    const t = window.setTimeout(() => setFresh(null), 8000);
    return () => window.clearTimeout(t);
  }, [fresh]);
  React.useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  const unread = items?.unread ?? 0;
  return (
    <div className="relative" ref={ref}>
      <button type="button" onClick={() => setOpen((o) => !o)} aria-label={unread ? `Notifications, ${unread} unread` : "Notifications"}
              aria-expanded={open} data-testid="header-notifications"
              className="relative flex size-8 items-center justify-center rounded-md text-text-muted transition-colors hover:bg-surface-hover hover:text-text-primary">
        <Bell className="size-[15px]" aria-hidden />
        {unread > 0 ? (
          <span data-testid="header-notifications-count"
                className="absolute -right-0.5 -top-0.5 min-w-[16px] rounded-full bg-negative px-1 text-center text-[10px] font-semibold leading-4 text-white">
            {unread > 99 ? "99+" : unread}
          </span>
        ) : null}
      </button>
      {open ? (
        <div className="absolute right-0 z-50 mt-1 w-[340px] rounded-lg border border-border bg-surface p-2 shadow-lg" data-testid="notifications-panel">
          <div className="flex items-center justify-between px-2 py-1">
            <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">Notifications</p>
            {unread > 0 ? (
              <button type="button" className="text-xs text-accent hover:underline" data-testid="notifications-mark-all"
                      onClick={() => { void core.notificationsRead().then(() => core.notifications().then(setItems)); }}>
                Mark all read
              </button>
            ) : null}
          </div>
          {!items || items.notifications.length === 0 ? (
            <p className="px-2 py-4 text-sm text-text-muted" data-testid="notifications-empty">Nothing new.</p>
          ) : (
            <ul className="max-h-[360px] overflow-y-auto">
              {items.notifications.slice(0, 12).map((n) => (
                <li key={n.id}>
                  <Link href={n.href} onClick={() => { setOpen(false); void core.notificationsRead(n.id).then(() => mailChanged()); }}
                        data-testid="notification-item" data-read={n.read ? "true" : "false"} data-href={n.href}
                        className={cn("flex items-start gap-2 rounded-md px-2 py-2 text-sm hover:bg-surface-hover", !n.read && "bg-accent-muted/40")}>
                    {n.from ? <UserAvatar user={n.from} size={22} /> : null}
                    <span className="min-w-0">
                      <span className={cn("block text-text-primary", !n.read && "font-medium")}>{n.title}</span>
                      <span className="block text-[11px] text-text-muted">{mailWhen(n.created_at)} UTC</span>
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
          <Link href="/messages" onClick={() => setOpen(false)} className="mt-1 block rounded-md px-2 py-1.5 text-center text-xs text-accent hover:bg-surface-hover" data-testid="notifications-open-mail">Open Mail</Link>
        </div>
      ) : null}
      {fresh ? (
        <div role="status" aria-live="polite" data-testid="mail-new-toast"
             className="fixed bottom-4 right-4 z-[70] flex w-[340px] items-start gap-2 rounded-lg border border-border bg-surface p-3 text-sm shadow-xl">
          {fresh.from ? <UserAvatar user={fresh.from} size={28} /> : <Mail className="size-4 text-accent" aria-hidden />}
          <span className="min-w-0 flex-1">
            <span className="block text-[10px] font-semibold uppercase tracking-[0.08em] text-text-muted">New mail</span>
            <span className="block text-text-primary" data-testid="mail-new-toast-title">{fresh.title}</span>
            <Link href={fresh.href} onClick={() => { setFresh(null); void core.notificationsRead(fresh.id).then(() => mailChanged()); }}
                  className="mt-1 inline-block text-xs text-accent hover:underline" data-testid="mail-new-toast-open">Open</Link>
          </span>
          <button type="button" onClick={() => setFresh(null)} aria-label="Dismiss" data-testid="mail-new-toast-dismiss" className="text-text-muted hover:text-text-primary"><X className="size-3.5" /></button>
        </div>
      ) : null}
    </div>
  );
}

/** Who is signed in; sign out; and, for the Administrator, view as any user.
 *  R14 U (K28): the house dropdown — name and role, Viewing as, then My workspace · Settings · Sign out. */
export function UserMenu() {
  const { status, user, effective, viewingAs, isAdmin, signOut, viewAs } = useCoreAuth();
  const [open, setOpen] = React.useState(false);
  const [users, setUsers] = React.useState<User[]>([]);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!open || !isAdmin || users.length) return;
    void core.users().then((r) => setUsers(r.users), () => undefined);
  }, [open, isAdmin, users.length]);

  if (status !== "authenticated" || !user || !effective) return null;

  async function change(username: string | null) {
    setError(null);
    try {
      await viewAs(username);
      window.location.reload();
    } catch (e) {
      setError(friendlyMessage(e));
    }
  }

  const header = (
    <div data-testid="user-menu-who">
      <p className="truncate text-[13px] font-medium text-text-primary">{user.name}</p>
      <p className="truncate text-[11.5px] text-text-muted">{user.role}{user.title && user.title !== user.role ? ` · ${user.title}` : ""}</p>
      {user.books?.length ? <p className="truncate text-[11.5px] text-text-muted">Covers {user.books.join(" and ")}</p> : null}
      {viewingAs ? (
        <p className="mt-1 truncate text-[11.5px] font-medium text-warning" data-testid="user-menu-viewing-as">Viewing as {viewingAs.name} · read only</p>
      ) : null}
      {isAdmin ? (
        <div className="mt-2">
          <label className="flex items-center gap-1.5 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-text-muted" htmlFor="view-as">
            <Eye className="size-3" aria-hidden /> Viewing as
          </label>
          <select id="view-as" data-testid="view-as" value={viewingAs?.username ?? ""}
                  onChange={(e) => void change(e.target.value || null)} onKeyDown={(e) => e.stopPropagation()}
                  className="mt-1 h-8 w-full rounded-md border border-border bg-surface px-2 text-[13px] text-text-primary">
            <option value="">Myself (Administrator)</option>
            {users.filter((u) => u.username !== user.username).map((u) => (
              <option key={u.username} value={u.username}>{u.name} · {u.role}</option>
            ))}
          </select>
          {error ? <p className="mt-1 text-xs text-negative">{error}</p> : null}
        </div>
      ) : null}
    </div>
  );

  return (
    <div className="relative">
      <Dropdown open={open} onOpenChange={setOpen} align="end" width={290} menuTestId="user-menu-panel" ariaLabel="Account"
                header={header}
                renderTrigger={({ ref, props }) => (
                  <button ref={ref} {...props} data-testid="user-menu"
                          className="flex items-center gap-2 rounded-md px-1.5 py-1 text-left transition-colors hover:bg-surface-hover">
                    <UserAvatar user={effective} />
                    <span className="hidden min-w-0 leading-tight sm:block">
                      <span className="block max-w-[150px] truncate text-[12px] font-medium text-text-primary" data-testid="user-menu-name">
                        {effective.name}
                      </span>
                      <span className="block max-w-[150px] truncate text-[10px] text-text-muted">{effective.role}</span>
                    </span>
                  </button>
                )}
                sections={[
                  { items: [
                    ...(isAdmin ? [{ key: "admin-mail", label: "All mailboxes and audit log", icon: <Inbox />, href: "/messages?admin=1", testId: "menu-admin-mail" }] : []),
                    /* PLAN_R10 S1: the Cockpit is home; My workspace stays one click away here and under Work. */
                    { key: "workspace", label: "My workspace", icon: <Inbox />, href: "/workspace", testId: "menu-workspace" },
                    { key: "rules", label: "My rules", icon: <ListChecks />, href: "/deal-desk/rules", testId: "menu-my-rules" },  /* Round K */
                    { key: "settings", label: "Settings", icon: <Settings />, href: "/settings", testId: "menu-settings" },
                  ] },
                  { items: [
                    { key: "sign-out", label: "Sign out", icon: <LogOut />, testId: "sign-out",
                      onSelect: () => { void signOut().then(() => { window.location.href = "/login"; }); } },
                  ] },
                ]} />
      {viewingAs ? (
        <span data-testid="viewing-as-chip" className="absolute -bottom-3 left-0 whitespace-nowrap text-[9px] font-semibold uppercase tracking-[0.06em] text-warning">
          Viewing as {viewingAs.name}
        </span>
      ) : null}
    </div>
  );
}
