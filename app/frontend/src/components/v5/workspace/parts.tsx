"use client";

/**
 * The pieces every v5 Workspace page is built from: the page top (title), Back, deep-link chips, status
 * pills and the loading / error / empty states.
 *
 * Visual vocabulary follows the v5 modules (components/v5/ews/parts.tsx) and the
 */

import Link from "next/link";
import { BackButton } from "@/components/v5/core/back-button";
import * as React from "react";
import { ArrowUpRight, Loader2 } from "lucide-react";

import { InfoPopover } from "@/components/ui/info-popover";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { useCoreAuth } from "@/components/v5/core/auth";
import { type Person, type RequestStatus, type RequestType, type WsLink, words } from "@/lib/v5/workspace";

/** The signed-in user the workspace is shown for (the Administrator's view-as target while viewing as). */
export function useViewer(): string {
  return useCoreAuth().effective?.username ?? "";
}

export function PageTop({ eyebrow = "Work", title, subtitle, about, actions, back }: {
  eyebrow?: string; title: React.ReactNode; subtitle?: React.ReactNode; actions?: React.ReactNode;
  /** What the screen is for: behind the (i) next to the title, never a line of standfirst (PLAN_R4 G1). */
  about?: React.ReactNode;
  back?: { href: string; label: string };
}) {
  return (
    <header className="space-y-2">
      {back ? <BackTo href={back.href} label={back.label} /> : null}
      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-0">
          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-text-muted">{eyebrow}</p>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-semibold text-text-primary">{title}</h1>
            {about ? <InfoPopover title="About this screen">{about}</InfoPopover> : null}
          </div>
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-2 pb-1">
          {actions}
        </div>
      </div>
      {subtitle ? <p className="max-w-3xl text-sm text-text-secondary">{subtitle}</p> : null}
    </header>
  );
}

/** R7: the exact previous screen when there is one in this tab, else `href` (the list this item belongs to). */
export function BackTo({ href, label }: { href: string; label: string }) {
  return <BackButton fallback={{ href, label }} testId="ws-back" />;
}

/** Links into the live modules and between workspace items, said in words. */
export function LinkChips({ links, className }: { links: WsLink[]; className?: string }) {
  if (!links.length) return null;
  return (
    <div className={cn("flex flex-wrap gap-1.5", className)}>
      {links.map((l) => (
        <Link key={`${l.href}|${l.label}`} href={l.href} data-testid="ws-link" data-href={l.href}
              className="inline-flex items-center gap-1 rounded-md border border-border bg-surface px-2 py-1 text-xs text-accent transition-colors hover:bg-surface-hover">
          {l.label}
          <ArrowUpRight className="size-3" aria-hidden />
        </Link>
      ))}
    </div>
  );
}

const STATUS_TONE: Record<string, string> = {
  open: "bg-accent-muted text-accent border-accent/30",
  active: "bg-accent-muted text-accent border-accent/30",
  in_review: "bg-warning-muted text-warning border-warning/30",
  in_progress: "bg-warning-muted text-warning border-warning/30",
  draft: "bg-surface-muted text-text-secondary border-border",
  todo: "bg-surface-muted text-text-secondary border-border",
  escalated: "bg-negative-muted text-negative border-negative/30",
  responded: "bg-positive-muted text-positive border-positive/30",
  done: "bg-positive-muted text-positive border-positive/30",
  closed: "bg-surface-muted text-text-muted border-border",
};

export function StatusPill({ status, testId }: { status: string; testId?: string }) {
  return (
    <span className={cn("inline-flex shrink-0 items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.06em]",
                        STATUS_TONE[status] ?? "bg-surface-muted text-text-secondary border-border")}
          data-testid={testId}>
      {words(status)}
    </span>
  );
}

export function Who({ person, className }: { person: Person | null | undefined; className?: string }) {
  if (!person) return <span className={cn("font-medium text-accent", className)}>CreditProbe</span>;
  return (
    <span className={cn("inline-flex items-baseline gap-1.5", className)}>
      <span className="font-medium text-text-primary">{person.name}</span>
      {person.title ? <span className="text-text-muted">· {person.title}</span> : null}
    </span>
  );
}

export function Avatar({ person }: { person: Person | null | undefined }) {
  return (
    <span aria-hidden className="inline-flex size-7 shrink-0 items-center justify-center rounded-full bg-accent-muted text-[10px] font-semibold text-accent">
      {person?.initials ?? "CP"}
    </span>
  );
}

export function Loading({ what = "Loading…" }: { what?: string }) {
  return (
    <p className="flex items-center gap-2 py-8 text-sm text-text-muted">
      <Loader2 className="size-4 animate-spin" aria-hidden /> {what}
    </p>
  );
}

export function ErrorBox({ error }: { error: string }) {
  return (
    <Card className="border-negative/30 p-4 text-sm text-negative" role="alert" data-testid="ws-error">{error}</Card>
  );
}

export function Empty({ children }: { children: React.ReactNode }) {
  return (
    <p className="rounded-lg border border-dashed border-border py-8 text-center text-sm text-text-secondary">{children}</p>
  );
}

export function SectionTitle({ children, right }: { children: React.ReactNode; right?: React.ReactNode }) {
  return (
    <div className="mb-2 flex items-baseline justify-between gap-2">
      <h2 className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-muted">{children}</h2>
      {right}
    </div>
  );
}

export function Stat({ label, value, href, testId }: { label: string; value: React.ReactNode; href?: string; testId?: string }) {
  const body = (
    <>
      <p className="text-[10px] font-semibold uppercase tracking-[0.1em] text-text-muted">{label}</p>
      <p className="mt-1 text-[22px] font-semibold leading-tight tabular-nums text-text-primary">{value}</p>
    </>
  );
  if (!href) return <Card className="p-3.5" data-testid={testId}>{body}</Card>;
  return (
    <Card className="p-0" data-testid={testId}>
      <Link href={href} className="block p-3.5 transition-colors hover:bg-surface-hover">{body}</Link>
    </Card>
  );
}

/** Plain text with paragraphs and line breaks kept. */
export function Prose({ text, className }: { text: string; className?: string }) {
  return (
    <div className={cn("space-y-2 text-sm leading-[1.65] text-text-primary", className)}>
      {text.split(/\n{2,}/).map((p, i) => <p key={i} className="whitespace-pre-line">{p}</p>)}
    </div>
  );
}

export const inputClass =
  "w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:border-accent focus:outline-none";
