"use client";

/**
 * The v5 shell's route guard (PLAN_R5 A1). It reads the signed-in (or viewed-as) user's effective data access
 * policy from the Admin service and:
 *   - shows a "not in your access" panel instead of a module the policy does not open;
 *   - enforces the frozen Cockpit at book level: the Cockpit opens on a book the user has, and the Cockpit API is
 *     not called for a book the user lacks (row-level enforcement inside the Cockpit would need a registered
 *     exception; it is proposed in docs/STATUS_R5_ADMIN.md, not applied).
 * Every v5 service also enforces the policy server-side (backend/access); this guard is the shell's half.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import * as React from "react";
import { Lock } from "lucide-react";

import { useCoreAuth } from "@/components/v5/core/auth";
import { MODULE_LABEL, admin } from "@/lib/v5/admin";

type Me = Awaited<ReturnType<typeof admin.me>>;

const ROUTES: [RegExp, string][] = [
  [/^\/$|^\/cockpit(\/|$)/, "cockpit"], [/^\/early-warning/, "early_warning"], [/^\/borrower-360/, "borrower_360"],
  [/^\/what-if/, "what_if"], [/^\/scorecard-validation/, "scorecard"], [/^\/deal-desk/, "deal_desk"], [/^\/lenses/, "lenses"],
  [/^\/playbook/, "playbook"], [/^\/policy-docs/, "policy_docs"], [/^\/(projects|analyses|investigations|workspace)(\/|$)/, "projects"],
  [/^\/messages/, "mail"], [/^\/data-builder/, "data_builder"],
  [/^\/(workflow|users|agent-operations|ai-studio|settings|audit-log)(\/|$)/, "admin"],
];

export function moduleOf(path: string): string | null {
  for (const [re, m] of ROUTES) if (re.test(path)) return m;
  return null;
}

const COCKPIT_DOMAIN_KEY = "cockpit-v4:domain";
let books: string[] | null = null;
let patched = false;

/** The Cockpit API is not called for a book the user lacks (the shell's book-level guard). */
function guardCockpitFetch() {
  if (patched || typeof window === "undefined") return;
  patched = true;
  const orig = window.fetch.bind(window);
  window.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
    try {
      if (books && books.length < 2) {
        const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
        if (/:8500\//.test(url)) {
          const body = typeof init?.body === "string" ? init.body : "";
          const other = books.includes("corporate") ? "retail" : "corporate";
          if (new RegExp(`domain(_id)?["=:]+\\s*"?${other}\\b`).test(url + " " + body)) {
            return Promise.resolve(new Response(JSON.stringify({ detail: { error_code: "ACCESS_BOOK", message: `Your data access policy does not include the ${other} book.` } }),
              { status: 403, headers: { "Content-Type": "application/json" } }));
          }
        }
      }
    } catch { /* never break a request because the guard could not read it */ }
    return orig(input, init);
  };
}

export function AccessGuard({ children }: { children: React.ReactNode }) {
  const { effective } = useCoreAuth();
  const pathname = usePathname();
  const who = effective?.username ?? "";
  const [me, setMe] = React.useState<{ who: string; me: Me | null } | null>(null);
  React.useEffect(() => {
    let live = true;
    if (!who) return;
    void admin.me().then((m) => { if (live) setMe({ who, me: m }); }).catch(() => { if (live) setMe({ who, me: null }); });
    return () => { live = false; };
  }, [who]);
  const cur = me && me.who === who ? me.me : null;
  React.useEffect(() => {
    if (!cur?.authenticated) return;
    books = cur.cockpit_books ?? ["corporate", "retail"];
    guardCockpitFetch();
    if (books.length === 1) {
      try { sessionStorage.setItem(COCKPIT_DOMAIN_KEY, books[0]); } catch { /* storage blocked: the Cockpit opens on its default */ }
    }
  }, [cur]);
  const mod = moduleOf(pathname);
  // Until the policy is known, a module page does not render (so it never calls a service it may not use).
  if (who && mod && !(me && me.who === who)) return <div className="min-h-[50vh]" aria-busy="true" data-testid="access-checking" />;
  if (cur?.authenticated && mod && cur.modules[mod] === false) {
    return (
      <div className="mx-auto mt-16 max-w-md space-y-3 rounded-lg border border-border bg-surface p-6 text-center" data-testid="access-denied" data-module={mod}>
        <Lock className="mx-auto text-text-muted" size={22} />
        <p className="text-[15px] font-semibold text-text-primary">{MODULE_LABEL[mod] ?? mod} is not in your data access</p>
        <p className="text-[13px] text-text-secondary">Your access policy ({cur.policy.policies.map((p) => p.name).join(", ") || "your profile"}) does not open this module. Ask your administrator if you need it.</p>
        <Link href="/" className="inline-block rounded-md bg-accent px-3 py-1.5 text-[13px] font-medium text-accent-contrast" data-testid="access-denied-home">Go to the Cockpit</Link>
      </div>
    );
  }
  return <>{children}</>;
}
