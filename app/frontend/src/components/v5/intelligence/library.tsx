"use client";

import Link from "next/link";
import * as React from "react";
import { ArrowUpRight, Library } from "lucide-react";

import { Card } from "@/components/ui/card";
import { PageTop } from "@/components/v5/workspace/parts";
import { INTELLIGENCE_PACKS } from "@/lib/v5/intelligence-packs";
import { cn } from "@/lib/utils";

/** PLAN_R9 G1: the Intelligence Library. */
export function IntelligenceLibrary() {
  const [open, setOpen] = React.useState<string | null>(null);
  const totalRules = INTELLIGENCE_PACKS.reduce((n, p) => n + p.rules.length, 0);

  // Deep links from "Powered by" (#p1 … #p7) open and scroll to that pack.
  React.useEffect(() => {
    const read = () => {
      const id = window.location.hash.replace("#", "").toUpperCase();
      if (INTELLIGENCE_PACKS.some((p) => p.id === id)) {
        setOpen(id);
        requestAnimationFrame(() => document.getElementById(id.toLowerCase())?.scrollIntoView({ block: "start" }));
      }
    };
    read();
    window.addEventListener("hashchange", read);
    return () => window.removeEventListener("hashchange", read);
  }, []);

  return (
    <div className="mx-auto max-w-6xl space-y-8 px-6 py-6" data-testid="intelligence-library">
      <PageTop
        eyebrow="Functionalities"
        title="Intelligence Library"
        back={{ href: "/workspace", label: "Workspace" }}
        about={
          <p>
            CreditProbe is the system; the Intelligence Packs are the product. Each pack is credit risk
            knowledge written once — rules, methods and calibrations aligned to CBUAE CRM — and run on your
            bank&apos;s data beside your LOS, rating and ECL systems. Every answer in CreditProbe names the pack,
            the rule and its article, a confidence level and the Trace.
          </p>
        }
      />

      <section className="rounded-xl border border-border bg-surface px-6 py-6">
        <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-text-muted">What you license</p>
        <p className="mt-2 max-w-3xl text-lg leading-7 text-text-primary">
          You have the data. We bring the credit risk intelligence — CBUAE rules, SICR and default judgement, early
          warning, ECL diagnostics and regulatory defence — running on your data in minutes.
        </p>
        <div className="mt-5 flex flex-wrap gap-8 text-sm text-text-secondary">
          <span><b className="text-xl text-text-primary">{INTELLIGENCE_PACKS.length}</b> Intelligence Packs</span>
          <span><b className="text-xl text-text-primary">{totalRules}</b> registered rules</span>
          <span><b className="text-xl text-text-primary">100%</b> of answers traceable</span>
        </div>
      </section>

      <div className="grid gap-4 md:grid-cols-2">
        {INTELLIGENCE_PACKS.map((p) => {
          const expanded = open === p.id;
          return (
            <Card key={p.id} id={p.id.toLowerCase()} data-testid={`pack-${p.id}`}
                  className={cn("scroll-mt-6 p-5 transition-shadow", expanded && "md:col-span-2 ring-1 ring-accent/40")}>
              <div className="flex items-start gap-3">
                <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-accent-muted text-sm font-bold text-accent">
                  {p.id}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-baseline gap-2">
                    <h2 className="text-base font-semibold text-text-primary">{p.name}</h2>
                    <span className="text-[11px] text-text-muted">v{p.version} · {p.rules.length} rules</span>
                  </div>
                  <p className="mt-1 text-sm text-text-secondary">{p.knows}</p>
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {p.usedIn.map((u) => (
                      <Link key={u.label} href={u.href} data-testid="pack-used-in"
                            className="inline-flex items-center gap-1 rounded-md border border-border bg-surface px-2 py-1 text-xs text-accent hover:bg-surface-hover">
                        {u.label}<ArrowUpRight className="size-3" aria-hidden />
                      </Link>
                    ))}
                  </div>
                </div>
                <button type="button" onClick={() => setOpen(expanded ? null : p.id)} data-testid={`pack-toggle-${p.id}`}
                        aria-expanded={expanded}
                        className="shrink-0 rounded-md border border-border px-2.5 py-1 text-xs text-text-secondary hover:bg-surface-hover">
                  {expanded ? "Hide rules" : "Rules"}
                </button>
              </div>
              {expanded ? (
                <div className="mt-4 overflow-x-auto">
                  <table className="w-full text-left text-[13px]" data-testid={`pack-rules-${p.id}`}>
                    <thead className="text-[11px] uppercase tracking-wide text-text-muted">
                      <tr><th className="py-2 pr-3">Rule</th><th className="py-2 pr-3">Decides</th><th className="py-2 pr-3">Metric</th><th className="py-2 pr-3">Threshold</th><th className="py-2">Source</th></tr>
                    </thead>
                    <tbody>
                      {p.rules.map((r) => (
                        <tr key={r.id} className="border-t border-border align-top">
                          <td className="whitespace-nowrap py-2 pr-3 font-mono text-xs font-semibold text-text-primary">{r.id}</td>
                          <td className="py-2 pr-3 text-text-primary">{r.title}</td>
                          <td className="py-2 pr-3 text-text-secondary">{r.metric}</td>
                          <td className="py-2 pr-3 text-text-secondary">{r.threshold}</td>
                          <td className="py-2 text-text-secondary">{r.source}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : null}
            </Card>
          );
        })}
      </div>

      <p className="flex items-center gap-2 text-xs text-text-muted">
        <Library className="size-3.5" aria-hidden />
        CreditProbe AI by Quantalpha · packs are versioned; a rule change is a new version with its own Trace.
      </p>
    </div>
  );
}
