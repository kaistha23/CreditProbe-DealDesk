"use client";

/**
 * Home (PLAN_R13 Session H, R12_FEEDBACK J2): two tabs. **Brief** first, Noor's complete brief and the landing page
 * after sign-in; **Ask**, the centred chat box. The tab lives in the address (`?tab=ask`), so Back and a shared link
 * open the same tab. Mounted by the Cockpit home through FX-R13-01; all the Cockpit's own state stays there.
 */

import * as React from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { cn } from "@/lib/utils";

import { HomeAsk, type HomeAskProps } from "./home-ask";
import { HomeBrief } from "./home-brief";
import { type HomeTab, tabFrom } from "./starters";

export interface HomeTabsProps extends Omit<HomeAskProps, "onBrief"> {
  greeting: React.ReactNode;
  onEvidence: (attentionItemId: string) => void;
  /** Behind the Brief tab's disclosure: the ECL panel and Sent to you. */
  more?: React.ReactNode;
}

const TABS: { id: HomeTab; label: string }[] = [{ id: "brief", label: "Brief" }, { id: "ask", label: "Ask" }];

export function HomeTabs({ greeting, onEvidence, more, ...ask }: HomeTabsProps) {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const tab = tabFrom(params);
  const go = React.useCallback((next: HomeTab) => {
    const sp = new URLSearchParams(params.toString());
    sp.set("tab", next);
    if (next === "brief") sp.delete("q");
    sp.delete("attention");
    router.replace(`${pathname}?${sp.toString()}`, { scroll: false });
  }, [params, router, pathname]);

  const onKey = (e: React.KeyboardEvent, i: number) => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    e.preventDefault();
    const next = TABS[(i + (e.key === "ArrowRight" ? 1 : TABS.length - 1)) % TABS.length];
    go(next.id);
    document.getElementById(`home-tab-${next.id}`)?.focus();
  };

  return (
    <div data-testid="home-tabs" data-tab={tab}>
      <header className="mx-auto flex w-full max-w-[46rem] flex-wrap items-end justify-between gap-x-6 gap-y-3">
        <div className="min-w-0">{greeting}</div>
        <div role="tablist" aria-label="Home" className="flex items-center gap-1 rounded-lg border border-border bg-surface p-0.5">
          {TABS.map((t, i) => (
            <button key={t.id} id={`home-tab-${t.id}`} type="button" role="tab" aria-selected={tab === t.id}
                    aria-controls={`home-panel-${t.id}`} tabIndex={tab === t.id ? 0 : -1}
                    data-testid={`home-tab-${t.id}`} onClick={() => go(t.id)} onKeyDown={(e) => onKey(e, i)}
                    className={cn("rounded-md px-4 py-1.5 text-[13px] font-medium transition-colors",
                      tab === t.id ? "bg-accent text-accent-contrast shadow-sm" : "text-text-secondary hover:text-text-primary")}>
              {t.label}
            </button>
          ))}
        </div>
      </header>
      <div id={`home-panel-${tab}`} role="tabpanel" aria-labelledby={`home-tab-${tab}`} className="pb-16">
        {tab === "brief" ? (
          <HomeBrief domain={ask.domain} onEvidence={onEvidence} onAsk={() => go("ask")} more={more} />
        ) : (
          <HomeAsk {...ask} onBrief={() => go("brief")} />
        )}
      </div>
    </div>
  );
}
