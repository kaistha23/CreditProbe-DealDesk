/**
 * The Early Warning -> Borrower 360 deep link, and what a Borrower 360 URL
 * selects. One module, no API client, so it is unit-testable on its own.
 *
 * The acceptance finding this answers: opening a customer from an Early
 * Warning row used to drop everything already established -- Borrower 360
 * opened on its landing list at whatever period happened to be latest, and
 * the officer retyped the id they had just clicked, then read a different
 * period from the one the signal fired in. So the link carries the domain,
 * the id, the period AND the release, and this is the single place that knows
 * their names: two surfaces agreeing on a URL by coincidence is how a deep
 * link quietly stops working.
 *
 * The release is carried to be CHECKED, never to open a book. A link made
 * against a superseded release is refused by the server rather than answered
 * with different numbers under the same URL.
 */

import { safeBack } from "./nav.ts";

export type LinkDomain = "corporate" | "retail";

export const DOMAIN_PARAM = "domain";
/** Named as the mandate names it, and as `lib/borrower-link.ts` named it. */
export const OWNER_PARAM = "customer_id";
/** Its earlier spelling, still honoured so existing links keep landing. */
export const LEGACY_OWNER_PARAM = "borrower";
export const PERIOD_PARAM = "period";
export const RELEASE_PARAM = "release";
export const BACK_PARAM = "back";

/** A minimal view of URLSearchParams, so a plain object can be tested. */
export type Params = { get(name: string): string | null };

/**
 * Where an Early Warning row points.
 *
 * Periods are written verbatim (`2026Q2`, `2026-08`): the canonical releases
 * already spell their periods URL-safely, so nothing is reformatted on the
 * way out and nothing has to be guessed on the way back in.
 */
export function borrower360Href(args: {
  domain: LinkDomain;
  ownerId: string;
  period?: string | null;
  release?: string | null;
  back?: string | null;
}): string {
  const id = (args.ownerId ?? "").trim();
  if (!id) return "/borrower-360";
  const params = new URLSearchParams({ [DOMAIN_PARAM]: args.domain, [OWNER_PARAM]: id });
  // An empty period is omitted rather than sent: `?period=` asks the book for
  // a period called nothing.
  if (args.period) params.set(PERIOD_PARAM, args.period);
  if (args.release) params.set(RELEASE_PARAM, args.release);
  const back = safeBack(args.back);
  if (back) params.set(BACK_PARAM, back);
  return `/borrower-360?${params.toString()}`;
}

/** What a Borrower 360 URL selects. A domain it does not know is Retail. */
export function selectionFrom(params: Params | null | undefined): {
  domain: LinkDomain;
  ownerId: string;
  period: string;
  release: string;
} {
  const get = (n: string) => (params?.get(n) ?? "").trim();
  return {
    domain: get(DOMAIN_PARAM) === "corporate" ? "corporate" : "retail",
    ownerId: get(OWNER_PARAM) || get(LEGACY_OWNER_PARAM),
    period: get(PERIOD_PARAM),
    release: get(RELEASE_PARAM),
  };
}

/**
 * The selection after a domain switch.
 *
 * A borrower id means nothing in the Retail book, so switching domain drops
 * the selected owner -- and with it the period, since a quarter is not a
 * month. Carrying an identity into a book that has no such row is how a
 * screen ends up showing somebody else's exposure under the id that was
 * clicked.
 */
export function afterDomainSwitch(
  next: LinkDomain,
  current: { domain: LinkDomain; ownerId: string },
): { domain: LinkDomain; ownerId: string; cleared: boolean } {
  if (next === current.domain) return { ...current, cleared: false };
  return { domain: next, ownerId: "", cleared: Boolean(current.ownerId) };
}
