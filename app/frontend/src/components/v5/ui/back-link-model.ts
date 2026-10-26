/**
 * R14 U (K1, K11): where "← Back to <origin>" goes, free of React so it is unit-tested.
 *
 * Every navigation from Noor (Brief, Ask, the panel), a drawer or a list that sends the reader to another screen
 * carries `from=<origin>` and, when the exact screen matters (a filtered list, a thread), `back=<path>`. The target
 * page shows one line "← Back to <origin>" at the top-left (mounted once in the app shell). Navigations that carry
 * it are pushes, never `router.replace`, so the browser's Back works as well.
 *
 *   withFrom("/regulatory?check=c1", "brief")                       → "/regulatory?check=c1&from=brief"
 *   withFrom("/borrower-360?id=CB00020", "ews", "/early-warning?band=red")
 *                                   → "/borrower-360?id=CB00020&from=ews&back=%2Fearly-warning%3Fband%3Dred"
 *   readFrom(new URLSearchParams("from=brief"))                      → { label: "Brief", href: "/?tab=brief" }
 */

export interface Origin { label: string; href: string }

/** Known origins and their home screens (used when no `back` path was carried). Keys are stable. */
export const ORIGINS: Record<string, Origin> = {
  brief: { label: "Brief", href: "/?tab=brief" },
  ask: { label: "Ask", href: "/?tab=ask" },
  noor: { label: "Noor", href: "/?tab=brief" },
  cockpit: { label: "Cockpit", href: "/" },
  ews: { label: "Early Warning", href: "/early-warning" },
  b360: { label: "Borrower 360", href: "/borrower-360" },
  "deal-desk": { label: "Deal Desk", href: "/deal-desk" },
  deal: { label: "the deal", href: "/deal-desk" },
  pipeline: { label: "Proposal pipeline", href: "/deal-desk" },
  book: { label: "Book", href: "/deal-desk?tab=book" },
  monitoring: { label: "Monitoring", href: "/deal-desk" },
  whatif: { label: "What-If", href: "/what-if" },
  lenses: { label: "Lenses", href: "/lenses" },
  governance: { label: "Governance", href: "/deal-desk" },
  "who-to-call": { label: "Who to call", href: "/early-warning" },
  contagion: { label: "Contagion map", href: "/borrower-360" },
  event: { label: "Event translator", href: "/what-if" },
  employer: { label: "Employer exposure", href: "/what-if" },
  inspection: { label: "Inspection responder", href: "/deal-desk" },
  "renewal-autopilot": { label: "Renewal autopilot", href: "/deal-desk?tab=book" },
  regulatory: { label: "Regulatory intelligence", href: "/intelligence" },
  tour: { label: "the tour", href: "/" },
  panel: { label: "the panel", href: "/" },
  drawer: { label: "the panel", href: "/" },
};

/** A same-origin relative path only: "/x", never "//host", "http:", "javascript:" or a backslash trick. */
export function isInternal(path: string | null | undefined): path is string {
  if (!path || typeof path !== "string") return false;
  if (!path.startsWith("/") || path.startsWith("//") || path.startsWith("/\\")) return false;
  return !/[\u0000-\u001f]/.test(path);
}

function splitHref(href: string): { path: string; query: string; hash: string } {
  const hashAt = href.indexOf("#");
  const hash = hashAt >= 0 ? href.slice(hashAt) : "";
  const noHash = hashAt >= 0 ? href.slice(0, hashAt) : href;
  const qAt = noHash.indexOf("?");
  return { path: qAt >= 0 ? noHash.slice(0, qAt) : noHash, query: qAt >= 0 ? noHash.slice(qAt + 1) : "", hash };
}

/** Remove `from` / `back` from a URL (so a back path never nests another back path). */
export function stripFrom(href: string): string {
  const { path, query, hash } = splitHref(href);
  const sp = new URLSearchParams(query);
  sp.delete("from");
  sp.delete("back");
  const q = sp.toString();
  return `${path}${q ? `?${q}` : ""}${hash}`;
}

/**
 * Append `from=<origin>` (and `back=<path>` when given) to an internal href. External hrefs come back unchanged; an
 * href that already carries `from` keeps it (the first origin wins: Brief → module → drawer still says Brief),
 * unless `override` is set. The back path itself is stripped of its own from/back.
 */
export function withFrom(href: string, from: string, back?: string | null, override = false): string {
  if (!isInternal(href) || !from) return href;
  const { path, query, hash } = splitHref(href);
  const sp = new URLSearchParams(query);
  if (sp.has("from") && !override) return href;
  sp.set("from", from);
  if (back && isInternal(back)) {
    const b = stripFrom(back);
    if (b !== stripFrom(href)) sp.set("back", b);
    else sp.delete("back");
  } else sp.delete("back");
  return `${path}?${sp.toString()}${hash}`;
}

/** The Back target a page shows, or null (no `from`, or an unknown origin with no usable back path). */
export function readFrom(params: { get(name: string): string | null }): Origin | null {
  const from = params.get("from");
  if (!from) return null;
  const back = params.get("back");
  const known = ORIGINS[from];
  const label = known?.label ?? (/^[a-z0-9-]{1,32}$/i.test(from) ? from.replace(/-/g, " ") : null);
  if (!label) return null;
  if (isInternal(back)) return { label, href: back };
  if (known) return known;
  return null;
}

/** "Back to Brief" (with "the" kept lower-case: "Back to the deal"). */
export function backLabel(o: Origin): string {
  return `Back to ${o.label}`;
}

/** The current location as a back path (pathname + search, without from/back). */
export function herePath(loc: { pathname: string; search: string } | null | undefined): string | null {
  if (!loc) return null;
  return stripFrom(`${loc.pathname}${loc.search}`);
}

/**
 * Should Back be the browser's history.back()? Yes when the previous in-app entry is the target screen (same path
 * and query, ignoring from/back), so Back keeps scroll and state. Otherwise push the target (a pasted link, a new tab).
 */
export function shouldHistoryBack(previous: string | null | undefined, target: string): boolean {
  if (!previous) return false;
  const prev = previous.replace(/^https?:\/\/[^/]+/, "");
  return stripFrom(prev) === stripFrom(target);
}
