"use client";

/**
 * PLAN_R12 Session F: one renderer for the blocks of a paper (bank-form proposal, committee paper). Used inside the
 * WriteProposalDialog and the CommitteePaperDialog; the Word and PDF files carry the same content.
 */

import * as React from "react";

import { cn } from "@/lib/utils";
import { dealdeskOrigin, DealDeskError } from "@/lib/v5/dealdesk";
import { friendlyMessage } from "@/lib/v5/errors";

import { Chip, tableCls, tdCls, thCls } from "../kit";
import { boldRuns, type Block, type PaperSection, sectionNumber, voiceLabel } from "./model";

export async function getJson<T>(url: string, init?: RequestInit): Promise<T> {
  let r: Response;
  try {
    r = await fetch(`${dealdeskOrigin()}${url}`, { credentials: "include", cache: "no-store", ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) } });
  } catch {
    throw new DealDeskError(0, "Deal Desk is temporarily unavailable. Please try again in a moment.");
  }
  const body = await r.json().catch(() => null);
  if (!r.ok) throw new DealDeskError(r.status, (body && typeof body.detail === "string" ? body.detail : "") || "The paper could not be written.");
  return body as T;
}

export const errorText = (e: unknown) => friendlyMessage(e);
export const fileHref = (url: string) => `${dealdeskOrigin()}${url}`;

function Rich({ text }: { text: string }) {
  return <>{boldRuns(text).map(([c, b], i) => (b ? <strong key={i} className="font-semibold">{c}</strong> : <React.Fragment key={i}>{c}</React.Fragment>))}</>;
}

function BlockView({ b }: { b: Block }) {
  switch (b.t) {
    case "p":
      return <p className="text-[12px] leading-[1.5] text-text-primary"><Rich text={b.text} /></p>;
    case "h":
      return <h4 className="pt-1 text-[12px] font-semibold text-accent">{b.text}</h4>;
    case "bullets":
    case "numbered": {
      const L = b.t === "numbered" ? "ol" : "ul";
      return (
        <L className={cn("space-y-1 pl-5 text-[12px] leading-[1.5] text-text-primary", b.t === "numbered" ? "list-decimal" : "list-disc")}>
          {b.items.map((x, i) => <li key={i}><Rich text={x} /></li>)}
        </L>);
    }
    case "table":
      return (
        <div className="space-y-1">
          <div className="max-w-full overflow-x-auto">
            <table className={tableCls}>
              <thead><tr>{b.header.map((h, i) => <th key={i} className={thCls}>{h}</th>)}</tr></thead>
              <tbody>{b.rows.map((r, i) => (
                <tr key={i}>{r.map((c, j) => <td key={j} className={cn(tdCls, "whitespace-normal align-top", j > 0 && /^[\s(+\-–]*[\d,.]+%?x?\)?$/.test(String(c)) && "text-right")}><Rich text={String(c)} /></td>)}</tr>))}
              </tbody>
            </table>
          </div>
          {b.source ? <p className="text-[11px] italic text-text-muted">Source: {b.source}</p> : null}
        </div>);
    case "kv":
      return (
        <dl className="grid grid-cols-1 gap-x-4 gap-y-1 text-[12px] sm:grid-cols-[160px_1fr_160px_1fr]">
          {b.pairs.map(([k, v]) => (<React.Fragment key={k}><dt className="text-text-muted">{k}</dt><dd className="text-text-primary">{v}</dd></React.Fragment>))}
        </dl>);
    case "sign":
      return (
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
          {b.rows.map(([role]) => (
            <div key={role} className="rounded-md border border-border p-3 text-[11px] text-text-muted"><div className="font-medium text-text-secondary">{role}</div>
              <div className="mt-6 border-t border-border pt-1">Signature and date</div></div>))}
        </div>);
    case "box":
      return <div className="rounded-md border border-border p-3 text-[12px] font-medium text-text-secondary">{b.title}<div className="h-10" /></div>;
    default:
      return null;
  }
}

export function SectionView({ s, index, numbered = true, testId }: { s: PaperSection; index: number; numbered?: boolean; testId?: string }) {
  return (
    <section className="space-y-2 border-b border-border/60 pb-4" data-testid={testId ?? `paper-section-${s.key}`}>
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-[13px] font-semibold text-text-primary">{sectionNumber(index, numbered)}{s.heading}</h3>
        {s.voice !== "form" ? <Chip tone={s.part === "creditprobe" ? "accent" : s.voice === "business" ? "neutral" : "positive"}>{voiceLabel(s)}</Chip> : null}
        {s.gaps?.length ? <Chip tone="warning" title={s.gaps.join(", ")}>Data not available</Chip> : null}
      </div>
      {s.blocks.map((b, i) => <BlockView key={i} b={b} />)}
    </section>);
}
