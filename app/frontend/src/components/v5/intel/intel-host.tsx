"use client";

/**
 * R13 M (PLAN_R13 §I): the drawer that shows one intelligence panel over any page when the URL carries
 * `?intel=<key>` (Noor's panel sends a routed question here; links under Ask answers point here). Mounted once in the
 * app header beside Noor. Closing it removes the parameter; nothing is added to any first screen.
 */

import * as React from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { IntelAnswer, matchFromParams } from "./intel-panel";

function HostInner() {
  const sp = useSearchParams();
  const pathname = usePathname();
  const router = useRouter();
  const dealId = /^\/deal-desk\/([^/?#]+)$/.exec(pathname ?? "")?.[1];
  const m = React.useMemo(() => matchFromParams(new URLSearchParams(sp?.toString() ?? ""), { dealId: dealId ? decodeURIComponent(dealId) : null }),
                          [sp, dealId]);
  const close = React.useCallback(() => {
    const next = new URLSearchParams(sp?.toString() ?? "");
    for (const k of ["intel", "deal", "borrower", "employer"]) next.delete(k);
    if (!next.get("thread")) next.delete("q");
    const qs = next.toString();
    router.replace(`${pathname}${qs ? `?${qs}` : ""}`, { scroll: false });
  }, [sp, pathname, router]);
  const setDeal = React.useCallback((d: string) => {
    const next = new URLSearchParams(sp?.toString() ?? "");
    next.set("deal", d);
    router.replace(`${pathname}?${next.toString()}`, { scroll: false });
  }, [sp, pathname, router]);
  React.useEffect(() => {
    if (!m) return;
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") close(); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [m, close]);
  if (!m) return null;
  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true" aria-label={m.route.label} data-testid="intel-host">
      <button type="button" aria-label="Close" className="absolute inset-0 bg-black/25" onClick={close} tabIndex={-1} />
      <aside className="relative h-full w-[min(860px,calc(100vw-2rem))] overflow-y-auto border-l border-border bg-surface-sunken p-3 shadow-xl">
        <IntelAnswer m={m} onClose={close} onDeal={setDeal} />
      </aside>
    </div>
  );
}

export function IntelHost() {
  return <React.Suspense fallback={null}><HostInner /></React.Suspense>;
}
