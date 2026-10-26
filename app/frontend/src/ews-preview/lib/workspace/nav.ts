/**
 * Navigation that remembers where it came from.
 *
 * A cross-module handoff (issue → What-If, What-If → Scenario Library, a Lens
 * → What-If, ...) carries its origin as `back=<path>`, so the destination can
 * offer an explicit "Back to ..." that lands on the exact origin state, and
 * pages keep their own view state in the URL so browser Back restores it.
 */

/** A same-origin path, or "" — never an absolute or protocol-relative URL. */
export function safeBack(raw: string | null | undefined): string {
  if (!raw) return "";
  const v = raw.trim();
  if (!v.startsWith("/") || v.startsWith("//") || v.includes("\\") || /^\/\s/.test(v)) return "";
  // Nested origins (Home → issue → thread → What-If → …) stay well under
  // what browsers and Next accept in a URL.
  if (v.length > 6000) return "";
  return v;
}

// The address this page has asked the router for and the browser has not
// committed yet (set by `useAddress`). A link rendered in that window is
// rendered once, before the commit, and nothing re-renders it after: read
// from `window.location` it kept the previous address as its origin, so
// Back from it restored a state the page had already left (VAL-DEF-044).
let requested = "";
// The address the page was showing when `requested` was asked for. A request
// only describes the page it was made from: arriving at the SAME path with a
// different query (Scenario Library -> "Use in What-If") is a new page, and
// the old request must not become its base. It did, and a corporate template
// opened on the Retail book with its scenario parameter dropped, because the
// stale `?domain=retail` address was used as the base of the first write.
let requestedFrom = "";

/** Record (or, with "", clear) the address in flight. */
export function setRequestedAddress(path: string): void {
  requested = path;
  requestedFrom = typeof window === "undefined" ? "" : `${window.location.pathname}${window.location.search}`;
}

/** Clear the address in flight once the browser shows it. */
export function settleRequestedAddress(): void {
  if (typeof window === "undefined") return;
  const live = `${window.location.pathname}${window.location.search}`;
  // Landed, or overtaken by a real navigation to somewhere neither the
  // request nor the page it was made from. Either way the request is spent.
  if (requested === live || (requested && requestedFrom && live !== requestedFrom && live !== requested)) {
    requested = "";
    requestedFrom = "";
  }
}

/** True while this page's own address write has not landed yet. */
export function addressInFlight(): boolean {
  return typeof window !== "undefined" && currentAddress() !== `${window.location.pathname}${window.location.search}`;
}

/** This page's address: the one in flight, else the committed one. */
export function currentAddress(): string {
  if (typeof window === "undefined") return "";
  const live = `${window.location.pathname}${window.location.search}`;
  // A request is this page's address only while the browser still shows the
  // page it was made from. Once the location has moved on, the live address
  // is the truth -- otherwise a write built on the request would restore
  // query state the reader had already navigated away from.
  if (requested && requested !== live && requested.split("?")[0] === window.location.pathname && (!requestedFrom || requestedFrom === live)) {
    return requested;
  }
  return live;
}

/** `href` with `back=<origin>` appended (origin defaults to the current URL). */
export function withBack(href: string, origin?: string): string {
  const from = origin ?? currentAddress();
  const back = safeBack(from);
  if (!back) return href;
  return `${href}${href.includes("?") ? "&" : "?"}back=${encodeURIComponent(back)}`;
}

/** What a back target is, in words. */
export function backLabel(path: string): string {
  const p = path.split("?")[0];
  if (p === "/" || p === "") return "Cockpit";
  if (p.startsWith("/issues/")) return "the issue";
  if (p.startsWith("/cockpit/thread/")) return "the investigation";
  if (p.startsWith("/cockpit/trace/")) return "the run's trace";
  if (p.startsWith("/what-if/result/")) return "the result";
  if (p.startsWith("/what-if/compare/")) return "the comparison";
  if (p.startsWith("/what-if")) return "What-If";
  if (p.startsWith("/scenarios/")) return "the scenario";
  if (p.startsWith("/scenarios")) return "the Scenario Library";
  if (p.startsWith("/lenses/")) return "the Lens";
  if (p.startsWith("/lenses")) return "Lenses";
  if (p.startsWith("/monitoring")) return "the Monitoring Centre";
  if (p.startsWith("/messages")) return "Messages";
  if (p.startsWith("/early-warning")) return "Early Warning";
  if (p.startsWith("/trace")) return "Trace";
  if (p.startsWith("/ai-model-lab")) return "the AI Model Lab";
  return "the previous page";
}

/** Replace one query parameter in the current URL (null removes it). */
export function urlWith(params: Record<string, string | null | undefined>): string {
  if (typeof window === "undefined") return "";
  const url = new URL(window.location.href);
  for (const [k, v] of Object.entries(params)) {
    if (v === null || v === undefined || v === "") url.searchParams.delete(k);
    else url.searchParams.set(k, v);
  }
  return `${url.pathname}${url.search}`;
}
