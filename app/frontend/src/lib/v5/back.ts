"use client";

/**
 * R7: the Back every v5 screen uses. See `back-trail.ts` for the rule:
 * the exact previous screen and step when there is one in this tab, else the carried `returnTo`, else the parent.
 */
import * as React from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { readReturn, type ReturnTo } from "@/lib/return-context";
import { previousInApp } from "@/lib/v5/back-trail";

export { previousInApp, recordVisit } from "@/lib/v5/back-trail";

export function useBack(fallback: ReturnTo): { label: string; href: string; go: (e?: React.MouseEvent) => void } {
  const router = useRouter();
  const p = useSearchParams();
  const ctx = readReturn(p.get("returnTo"), p.get("returnLabel"), p.get("returnType"), fallback);
  const go = React.useCallback((e?: React.MouseEvent) => {
    // A new-tab click keeps its browser meaning.
    if (e && (e.metaKey || e.ctrlKey || e.shiftKey || e.button === 1)) return;
    e?.preventDefault();
    const prev = previousInApp();
    if (!prev) router.push(ctx.href);
    else if (prev.delta === 1) router.back();
    else window.history.go(-prev.delta);
  }, [router, ctx.href]);
  return { label: ctx.label, href: ctx.href, go };
}

/** Back for a screen that already knows its parent but should prefer the exact previous step. */
export function backOr(router: { back: () => void }, parent: () => void): void {
  const prev = previousInApp();
  if (!prev) parent();
  else if (prev.delta === 1) router.back();
  else window.history.go(-prev.delta);
}

/**
 * R7: a piece of screen state held in the address, so Back restores it. `push` makes each change a step that Back
 * walks (tabs); `replace` refines the current step (filters, search). The default value is left out of the URL.
 */
export function useUrlState<T extends string>(key: string, def: T, mode: "push" | "replace" = "replace"): [T, (v: T) => void] {
  const p = useSearchParams();
  const value = (p.get(key) ?? def) as T;
  const set = React.useCallback((v: T) => {
    const q = new URLSearchParams(window.location.search);
    if (v === def || v === "") q.delete(key); else q.set(key, v);
    const url = `${window.location.pathname}${q.size ? `?${q}` : ""}${window.location.hash}`;
    if (url === window.location.pathname + window.location.search + window.location.hash) return;
    if (mode === "push") window.history.pushState(null, "", url); else window.history.replaceState(null, "", url);
  }, [key, def, mode]);
  return [value, set];
}
