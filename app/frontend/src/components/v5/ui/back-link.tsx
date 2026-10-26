"use client";

/**
 * R14 U (K1, K11): "← Back to <origin>".
 *
 *   <OriginBackLink />                        mounted once in the app shell: shows when the URL carries from=<origin>
 *   <BackLink from="ews" />                   an explicit back control (with an optional fallback when no from)
 *   withFrom(href, "brief" [, backPath])      build a link that carries its origin (re-exported from the model)
 *   useFromHere("ews")                        (href) => href + from=ews + back=<this exact screen>
 *   pushFrom(router, href, "ask", back?)      router.push with the origin (never replace)
 *
 * Back is the browser's history.back() when the previous in-app entry is the target screen (scroll and filters kept),
 * else a push to the target (a pasted link, a new tab). Stable API for sessions g, i, f, p; add props, never rename.
 * Test ids: `origin-back-link` (shell) and `back-link` (explicit).
 */

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { ArrowLeft } from "lucide-react";

import { cn } from "@/lib/utils";
import { previousInApp } from "@/lib/v5/back-trail";

import { ORIGINS, type Origin, backLabel, herePath, readFrom, shouldHistoryBack, withFrom } from "./back-link-model";

export { ORIGINS, withFrom, readFrom, stripFrom, herePath, isInternal } from "./back-link-model";
export type { Origin } from "./back-link-model";

/** A link builder that carries this screen as the way back: `const link = useFromHere("ews"); <a href={link(x)} />`. */
export function useFromHere(from: string): (href: string) => string {
  const pathname = usePathname();
  const params = useSearchParams();
  const q = params.toString();
  return React.useCallback((href: string) => withFrom(href, from, herePath({ pathname, search: q ? `?${q}` : "" })),
    [from, pathname, q]);
}

/** Same as useFromHere but without hooks (event handlers, stores): reads window.location. */
export function fromHere(href: string, from: string): string {
  const here = typeof window !== "undefined" ? herePath(window.location) : null;
  return withFrom(href, from, here);
}

/** Navigate with the origin carried (a push: Back works in the browser too). */
export function pushFrom(router: { push: (href: string) => void }, href: string, from: string, back?: string | null) {
  router.push(withFrom(href, from, back ?? (typeof window !== "undefined" ? herePath(window.location) : null)));
}

function BackButton({ origin, testId, className }: { origin: Origin; testId: string; className?: string }) {
  const router = useRouter();
  const onClick = (e: React.MouseEvent) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return; // a new tab keeps the link
    e.preventDefault();
    const prev = previousInApp();
    if (prev && shouldHistoryBack(prev.url, origin.href)) window.history.go(-prev.delta);
    else router.push(origin.href);
  };
  return (
    <Link href={origin.href} onClick={onClick} data-testid={testId} data-origin-href={origin.href}
          className={cn("inline-flex h-7 items-center gap-1.5 rounded-md pl-1 pr-2 text-[12.5px] font-medium text-text-secondary transition-colors hover:bg-surface-hover hover:text-text-primary", className)}>
      <ArrowLeft className="size-3.5" aria-hidden />
      {backLabel(origin)}
    </Link>
  );
}

function OriginInner({ className }: { className?: string }) {
  const params = useSearchParams();
  const pathname = usePathname();
  const origin = readFrom(params);
  if (!origin) return null;
  // The deal page's pipeline banner already carries "Back to pipeline" (PLAN_R12 I21).
  if (params.get("from") === "pipeline" && pathname.startsWith("/deal-desk/")) return null;
  return (
    <div className={cn("-mt-4 mb-3", className)} data-testid="origin-back">
      <BackButton origin={origin} testId="origin-back-link" />
    </div>
  );
}

/** Mounted once in the app shell, above every page: shows only when the URL carries from=<origin>. */
export function OriginBackLink({ className }: { className?: string }) {
  return (
    <React.Suspense fallback={null}>
      <OriginInner className={className} />
    </React.Suspense>
  );
}

function ExplicitInner({ from, back, fallback, className }: { from?: string; back?: string; fallback?: Origin; className?: string }) {
  const params = useSearchParams();
  const fromUrl = readFrom(params);
  const known = from ? ORIGINS[from] : undefined;
  const origin = fromUrl ?? (known ? { label: known.label, href: back ?? known.href } : fallback ?? null);
  if (!origin) return null;
  return <BackButton origin={origin} testId="back-link" className={className} />;
}

/**
 * An explicit back control: the URL's origin if it carries one, else the given origin (`from` + optional `back`), else
 * `fallback`; nothing when none applies. Use it on a page that is not under the shell's content column (dialogs).
 */
export function BackLink(props: { from?: string; back?: string; fallback?: Origin; className?: string }) {
  return (
    <React.Suspense fallback={null}>
      <ExplicitInner {...props} />
    </React.Suspense>
  );
}

/**
 * A Next link that carries its origin and this exact screen as the way back (K1). Use it for any link out of a panel,
 * drawer or list to another module: `<FromLink href={row.href} from="who-to-call">Open DD-03</FromLink>`.
 */
export function FromLink({ href, from, children, className, testId, onClick, title }: {
  href: string; from: string; children: React.ReactNode; className?: string; testId?: string; title?: string;
  onClick?: (e: React.MouseEvent<HTMLAnchorElement>) => void;
}) {
  const link = useFromHere(from);
  return <Link href={link(href)} className={className} data-testid={testId} title={title} onClick={onClick}>{children}</Link>;
}
