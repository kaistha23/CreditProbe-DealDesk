"use client";

import Link from "next/link";
import * as React from "react";
import {
  BarChart3, BriefcaseBusiness, ClipboardCheck, ExternalLink, FileText, FlaskConical, Gauge, Handshake, LayoutList, MessagesSquare, Radar,
  Search, UserRound, X,
} from "lucide-react";

import { OBJECT_LABEL, core, embedHref, fileSize, type MailAttachment, type MailObject, type ObjectType } from "@/lib/v5/core";
import { cn } from "@/lib/utils";

const ICON: Record<ObjectType, React.ComponentType<{ className?: string }>> = {
  investigation: Search, project: BriefcaseBusiness, "cockpit-thread": MessagesSquare, "attention-item": Gauge,
  "early-warning-list": Radar, borrower: UserRound, "whatif-thread": FlaskConical, "whatif-scenario": FlaskConical,
  report: FileText, analysis: BarChart3, document: FileText, "scorecard-validation": ClipboardCheck,
  "dealdesk-proposal": Handshake, "dealdesk-analysis": Handshake, lens: BarChart3, "crm-compliance": ClipboardCheck,
  "thread-answer": MessagesSquare,
};

export function ObjectIcon({ type, className }: { type: ObjectType; className?: string }) {
  const Icon = ICON[type] ?? LayoutList;
  return <Icon className={className ?? "size-4"} />;
}

/** One attached CreditProbe object or file. A click opens an object in place, a file downloads. */
export function AttachmentCard({ att, onOpen, onRemove }: {
  att: MailAttachment | { kind: "file"; file_id: string; name: string; size: number };
  onOpen?: (o: MailObject) => void; onRemove?: () => void;
}) {
  if (att.kind === "file") {
    return (
      <span className="inline-flex max-w-full items-center gap-2 rounded-md border border-border bg-surface px-2.5 py-1.5 text-xs" data-testid="mail-file">
        <FileText className="size-4 shrink-0 text-text-muted" aria-hidden />
        <a href={core.fileUrl(att.file_id)} download className="min-w-0 truncate text-accent hover:underline" data-testid="mail-file-link" title={`Download ${att.name}`}>
          {att.name}
        </a>
        <span className="shrink-0 text-text-muted">{fileSize(att.size)}</span>
        {onRemove ? <button type="button" onClick={onRemove} aria-label={`Remove ${att.name}`} className="text-text-muted hover:text-negative"><X className="size-3.5" /></button> : null}
      </span>
    );
  }
  const o = att.object;
  return (
    <span className="inline-flex max-w-full items-stretch overflow-hidden rounded-md border border-border bg-surface text-left" data-testid="mail-object" data-object-type={o.type} data-object-id={o.id}>
      <button type="button" onClick={() => onOpen?.(o)} data-testid="mail-object-open"
              className="flex min-w-0 items-start gap-2 px-2.5 py-1.5 text-left transition-colors hover:bg-surface-hover">
        <span className="mt-0.5 rounded bg-accent-muted p-1 text-accent"><ObjectIcon type={o.type} className="size-3.5" /></span>
        <span className="min-w-0">
          <span className="block text-[10px] font-semibold uppercase tracking-[0.08em] text-text-muted">{OBJECT_LABEL[o.type]}</span>
          <span className="block truncate text-sm font-medium text-text-primary">{o.label}</span>
          {o.summary ? <span className="mt-0.5 block max-w-[420px] text-xs text-text-secondary">{o.summary}</span> : null}
        </span>
      </button>
      {onRemove ? <button type="button" onClick={onRemove} aria-label={`Remove ${o.label}`} className="border-l border-border px-2 text-text-muted hover:text-negative"><X className="size-3.5" /></button>
        : onOpen ? (
          <Link href={o.href} title="Open full page" aria-label={`Open ${o.label} full page`} data-testid="mail-object-full"
                className="flex items-center border-l border-border px-2 text-text-muted hover:bg-surface-hover hover:text-accent">
            <ExternalLink className="size-3.5" aria-hidden />
          </Link>
        ) : null}
    </span>
  );
}

/** A label chip in its colour. */
export function LabelChip({ name, color, testId = "row-label" }: { name: string; color?: string; testId?: string }) {
  const c = color ?? "#6366f1";
  return (
    <span data-testid={testId} data-label={name} className="inline-flex items-center gap-1 rounded-full border px-1.5 text-[10px] font-medium leading-4"
          style={{ borderColor: `${c}66`, color: c, background: `${c}14` }}>
      <span className="size-1.5 rounded-full" style={{ background: c }} aria-hidden />{name}
    </span>
  );
}


/** An object opened in place: the app page framed without its navigation, with a way to open it full size. */
export function ObjectPanel({ object, onClose }: { object: MailObject; onClose: () => void }) {
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <aside role="dialog" aria-label={object.label} data-testid="object-panel"
           className="fixed inset-y-0 right-0 z-40 flex w-full max-w-[min(920px,92vw)] flex-col border-l border-border bg-canvas shadow-2xl">
      <header className="flex items-center gap-3 border-b border-border bg-surface px-4 py-2.5">
        <ObjectIcon type={object.type} className="size-4 text-accent" />
        <div className="min-w-0 flex-1">
          <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-text-muted">{OBJECT_LABEL[object.type]}</p>
          <p className="truncate text-sm font-medium text-text-primary" data-testid="object-panel-title">{object.label}</p>
        </div>
        <Link href={object.href} data-testid="object-panel-full"
              className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-xs text-accent hover:bg-surface-hover">
          Open full page <ExternalLink className="size-3" aria-hidden />
        </Link>
        <button type="button" onClick={onClose} aria-label="Close" data-testid="object-panel-close"
                className="rounded-md p-1.5 text-text-muted hover:bg-surface-hover hover:text-text-primary"><X className="size-4" /></button>
      </header>
      <iframe title={object.label} src={embedHref(object.href)} className={cn("min-h-0 flex-1 border-0 bg-canvas")} />
    </aside>
  );
}
