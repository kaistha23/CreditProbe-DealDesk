"use client";

/**
 * Step 2 of the tour (K36): CreditProbe as the intelligence layer above the bank's systems of record. Built from the
 * house tokens (no image, no vendor names): five systems, each with what it does (records, posts, scores, chases,
 * flags); one band above that reads them all; what it gives the team on top.
 */
import * as React from "react";
import { ArrowUp, Sparkles } from "lucide-react";

import { cn } from "@/lib/utils";

import { LABELS, type TourLang } from "./tour-model";

export function TourDiagram({ lang }: { lang: TourLang }) {
  const L = LABELS[lang];
  const systems: [string, string][] = [
    [L.los, L.records], [L.cbs, L.posts], [L.rating, L.scores], [L.collections, L.chases], [L.ews, L.flags],
  ];
  return (
    <div data-tour="tour-diagram" data-testid="tour-diagram" dir={lang === "ar" ? "rtl" : "ltr"}
         className="w-[min(640px,calc(100vw-2rem))] rounded-xl border border-border bg-surface p-5 shadow-xl">
      <div className="rounded-lg border border-border bg-surface-sunken px-4 py-2 text-center text-[12.5px] text-text-secondary">
        {L.out}
      </div>
      <div className="flex justify-center py-1.5 text-text-muted"><ArrowUp size={16} aria-hidden /></div>
      <div className="flex items-center justify-center gap-2 rounded-lg bg-accent px-4 py-3 text-accent-contrast shadow-sm">
        <Sparkles size={16} aria-hidden />
        <div className="text-center">
          <p className="text-[15px] font-semibold leading-tight">{L.diagramTop}</p>
          <p className="text-[12px] opacity-90">{L.diagramNoor}</p>
        </div>
      </div>
      <div className="grid grid-cols-5 gap-2 pt-1.5">
        {systems.map(([name]) => (
          <div key={name} className="flex justify-center text-text-muted"><ArrowUp size={14} aria-hidden /></div>
        ))}
        {systems.map(([name, verb]) => (
          <div key={`${name}-box`}
               className={cn("flex min-h-[64px] flex-col items-center justify-center rounded-lg border border-border-strong",
                             "bg-surface-raised px-1.5 py-2 text-center")}>
            <p className="text-[12.5px] font-medium leading-tight text-text-primary">{name}</p>
            <p className="mt-0.5 text-[11px] text-text-muted">{verb}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
