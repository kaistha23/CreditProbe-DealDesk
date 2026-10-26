"use client";

/** R14 p: one renderer for the bank-form blocks on screen (the Word and PDF carry the same content model). */

import * as React from "react";

import { cn } from "@/lib/utils";

import { tableCls, tdCls, thCls } from "../kit";
import { type Block, richRuns } from "./model";

export function Rich({ text }: { text: string }) {
  return (
    <>{richRuns(text).map((r, i) => (r.underline
      ? <strong key={i} className="font-semibold underline decoration-negative/70 underline-offset-2" data-concern="1">{r.text}</strong>
      : r.bold ? <strong key={i} className="font-semibold">{r.text}</strong> : <React.Fragment key={i}>{r.text}</React.Fragment>))}</>
  );
}

const NUM = /^[\s(+\-–]*[\d,.]+%?x?\)?$/;

export function BlockView({ b, dense }: { b: Block; dense?: boolean }) {
  const txt = dense ? "text-[11px] leading-[1.45]" : "text-[12px] leading-[1.5]";
  switch (b.t) {
    case "p":
      return <p className={cn(txt, b.exempt ? "text-text-muted" : "text-text-primary")}><Rich text={b.text} /></p>;
    case "h":
      return <h5 className="pt-1 text-[11.5px] font-semibold text-accent">{b.text}</h5>;
    case "bullets":
    case "numbered": {
      const L = b.t === "numbered" ? "ol" : "ul";
      return (
        <L className={cn("space-y-0.5 pl-5 text-text-primary", txt, b.t === "numbered" ? "list-decimal" : "list-disc")}>
          {b.items.map((x, i) => <li key={i}><Rich text={x} /></li>)}
        </L>);
    }
    case "table":
      return (
        <div className="space-y-0.5">
          <div className="max-w-full overflow-x-auto">
            <table className={cn(tableCls, "text-[10.5px]")}>
              <thead><tr>{b.header.map((h, i) => <th key={i} className={cn(thCls, "bg-accent px-1.5 py-1 text-[10px] text-accent-contrast")}>{h}</th>)}</tr></thead>
              <tbody>{b.rows.map((r, i) => (
                <tr key={i} className={i % 2 ? "bg-surface-sunken" : undefined}>
                  {r.map((c, j) => <td key={j} className={cn(tdCls, "whitespace-normal px-1.5 py-1 align-top", j > 0 && NUM.test(String(c).replace(/\*\*/g, "")) && "text-right")}>
                    {String(c).startsWith("    ") ? <span className="pl-3" /> : null}<Rich text={String(c).trimStart()} /></td>)}
                </tr>))}
              </tbody>
            </table>
          </div>
          {b.source ? <p className="text-[10px] italic text-text-muted">Source: {b.source}</p> : null}
        </div>);
    case "kv":
      return (
        <div className="grid grid-cols-2 border-l border-t border-border text-[10.5px] lg:grid-cols-4">
          {b.pairs.map(([k, v]) => (
            <React.Fragment key={k}>
              <div className="border-b border-r border-border bg-surface-sunken px-1.5 py-1 font-semibold text-text-muted">{k}</div>
              <div className="border-b border-r border-border px-1.5 py-1 text-text-primary">{v}</div>
            </React.Fragment>))}
        </div>);
    case "sign":
      return (
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
          {b.rows.map(([role, name]) => (
            <div key={role} className="rounded-sm border border-text-secondary/50 p-2.5 text-[10.5px] text-text-muted">
              <div className="font-semibold text-text-secondary">{role}</div>
              {name ? <div className="text-text-primary">{name}</div> : null}
              <div className="mt-6 border-t border-border pt-1">Signature · Date</div></div>))}
        </div>);
    case "box":
      return <div className="rounded-sm border border-text-secondary/60 p-2.5 text-[11px] font-semibold text-text-secondary">{b.title}<div className="h-12" />
        <div className="text-[10px] font-normal text-text-muted">Signature ____________  Name ____________  Date ________</div></div>;
    default:
      return null;
  }
}
